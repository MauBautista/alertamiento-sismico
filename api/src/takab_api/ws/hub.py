"""Hub de fan-out del WebSocket live (T-1.22 · B4).

Registra sockets por ``(claims, topics)`` y, ante cada NOTIFY del canal
``takab_live`` (ver migración 0004), reparte el cambio a los suscriptores que
tengan derecho a verlo. El payload del NOTIFY es SOLO una señal de invalidación
(tenant/site/id); el hub **re-consulta la fila con los GUCs del suscriptor** y
Postgres/RLS decide qué se ve — el payload crudo NUNCA se reenvía al cliente.

Ruta de un notify:
1. ``_dispatch`` mapea el tipo a un topic (``incident``/``incident_action`` →
   ``incidents``; ``device_health``/``rule_evaluation`` → ``site_state``).
2. Prefiltra suscriptores por visibilidad de tenant (propio ∪ takab-interno ∪
   gov sobre tenants ``gov_shared``), cacheando ``tenants.visibility`` ~60 s.
3. Agrupa los candidatos por clase ``(tenant_id, role)`` → UNA re-consulta por
   clase (no por socket) con esos GUCs. Si RLS oculta la fila, no se envía.

Presupuesto <2 s edge→browser: nuestra mitad (commit→NOTIFY→fetch→push) es
<100 ms; el resto es latencia de ingesta (T-1.17 commitea ``q-events`` ≤1.5 s).
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from uuid import UUID

from sqlalchemy import text
from starlette.websockets import WebSocket

from takab_api.auth.claims import Claims, scope_filter
from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.ws import protocol as p

logger = logging.getLogger("takab_api.ws")

_INTERNAL_ROLES = frozenset({"takab_superadmin", "takab_support"})
_VISIBILITY_TTL_S = 60.0
_LISTEN_READY_TIMEOUT_S = 5.0

# tipo de NOTIFY → topic del suscriptor.
_TOPIC_BY_TYPE: dict[str, str] = {
    "incident": p.TOPIC_INCIDENTS,
    "incident_action": p.TOPIC_INCIDENTS,
    "device_health": p.TOPIC_SITE_STATE,
    "rule_evaluation": p.TOPIC_SITE_STATE,
    # [T-2.11] La señal de check-in llega por el topic incidents (el headcount
    # táctico ya está suscrito ahí); el frame es una invalidación sin PII.
    "checkin": p.TOPIC_INCIDENTS,
}

_SQL_INCIDENT = text(
    "SELECT incident_id, tenant_id, site_id, event_id, opened_at, closed_at, "
    "severity, state, trigger, max_pga_g, max_pgv_cms "
    "FROM incidents WHERE incident_id = :id"
)
# [T-2.08] La acción viaja con el site_id de su incidente: la entrega se acota
# por site_scope del suscriptor (tácticos móviles con alcance de un sitio).
_SQL_ACTION = text(
    "SELECT a.action_id, a.incident_id, a.tenant_id, i.site_id, a.ts, a.kind, "
    "a.actor, a.payload "
    "FROM incident_actions a JOIN incidents i ON i.incident_id = a.incident_id "
    "WHERE a.action_id = :id"
)
# device_health/rule_evaluations tienen PK compuesto (ts, gateway_id) y el NOTIFY
# no trae ts: re-consultamos la transición más reciente del gateway (RLS aplica).
# [T-2.08] + site_id del gateway (mismo motivo que _SQL_ACTION).
_SQL_DEVICE_HEALTH = text(
    "SELECT dh.ts, dh.tenant_id, dh.gateway_id, g.site_id, dh.reason, "
    "dh.mqtt_rtt_ms, dh.seedlink_lag_s, dh.ntp_offset_ms, dh.cpu_temp_c, "
    "dh.power_status, dh.battery_pct, dh.battery_min_left, dh.cert_days_remaining "
    "FROM device_health dh JOIN gateways g ON g.gateway_id = dh.gateway_id "
    "WHERE dh.gateway_id = :gw AND dh.reason = 'transition' "
    "ORDER BY dh.ts DESC LIMIT 1"
)
_SQL_RULE_EVAL = text(
    "SELECT ts, tenant_id, site_id, gateway_id, prev_tier, new_tier, rule_set_version "
    "FROM rule_evaluations WHERE gateway_id = :gw ORDER BY ts DESC LIMIT 1"
)
_SQL_VISIBILITY = text("SELECT visibility FROM tenants WHERE tenant_id = :t")

# Contexto interno solo-lectura para el prefiltro de visibilidad (metadato tenant
# private/gov_shared). La autoridad de tenancy sigue siendo la re-consulta por
# suscriptor; esto solo decide a qué gov_operator vale la pena re-consultar.
_VISIBILITY_CTX = SessionCtx(tenant_id="", role="takab_superadmin", user_id="")


@dataclass(eq=False)
class Subscriber:
    """Un socket autenticado + sus topics + tareas de poller (features)."""

    ws: WebSocket
    claims: Claims
    topics: set[str] = field(default_factory=set)
    pollers: dict[str, asyncio.Task[Any]] = field(default_factory=dict)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Hub:
    """Singleton de proceso: LISTEN de fondo + registro de sockets + fan-out."""

    def __init__(self) -> None:
        self._subs: set[Subscriber] = set()
        self._listener: asyncio.Task[Any] | None = None
        self._ready = asyncio.Event()
        self._visibility: dict[str, tuple[str, float]] = {}
        self._running = False

    # ---- ciclo de vida (lo llama el lifespan de la app) -------------------
    async def start(self) -> None:
        """Arranca la tarea LISTEN y espera a que el canal quede activo (o timeout)."""
        if self._running:
            return
        self._running = True
        self._ready = asyncio.Event()
        # import diferido para evitar ciclo hub↔listener.
        from takab_api.ws.listener import run_listener

        self._listener = asyncio.create_task(run_listener(self))
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=_LISTEN_READY_TIMEOUT_S)
        except TimeoutError:
            # DB aún no lista: la tarea sigue reintentando; el REST no se bloquea.
            logger.warning("ws: LISTEN takab_live no listo en %ss", _LISTEN_READY_TIMEOUT_S)

    async def stop(self) -> None:
        """Cancela la tarea LISTEN y todos los pollers; limpia el registro."""
        self._running = False
        if self._listener is not None:
            self._listener.cancel()
            try:
                await self._listener
            except asyncio.CancelledError:
                pass
            self._listener = None
        for sub in list(self._subs):
            await self._cancel_pollers(sub)
        self._subs.clear()
        self._visibility.clear()

    # ---- registro de sockets ---------------------------------------------
    def register(self, ws: WebSocket, claims: Claims) -> Subscriber:
        sub = Subscriber(ws=ws, claims=claims)
        self._subs.add(sub)
        return sub

    async def unregister(self, sub: Subscriber) -> None:
        await self._cancel_pollers(sub)
        self._subs.discard(sub)

    async def subscribe(self, sub: Subscriber, topic: str) -> None:
        """Alta a un topic. ``features:<site_id>`` arranca un poller 1 Hz dedicado."""
        if topic in sub.topics:
            return
        sub.topics.add(topic)
        if topic.startswith(p.TOPIC_FEATURES_PREFIX):
            site_id = topic[len(p.TOPIC_FEATURES_PREFIX) :]
            # import diferido para evitar ciclo hub↔poller.
            from takab_api.ws.poller import poll_features

            sub.pollers[topic] = asyncio.create_task(poll_features(self, sub, site_id))

    async def _cancel_pollers(self, sub: Subscriber) -> None:
        current = asyncio.current_task()
        for task in sub.pollers.values():
            task.cancel()
        for task in sub.pollers.values():
            if task is current:
                # El propio poller detectó el socket muerto (_send → unregister →
                # aquí): NO hacemos ``await self`` — awaitarse a sí mismo tragaría
                # el CancelledError recién inyectado y el bucle ``while True``
                # resucitaría como tarea zombie. Al no awaitarlo, el cancel
                # propaga en el próximo await de ``poll_features`` y la tarea muere.
                continue
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 - defensivo en teardown
                logger.exception("ws: poller terminó con error")
        sub.pollers.clear()

    # ---- fan-out ----------------------------------------------------------
    async def dispatch(self, payload: dict[str, Any]) -> None:
        t = payload.get("t")
        tenant = payload.get("tenant")
        topic = _TOPIC_BY_TYPE.get(t or "")
        if topic is None or tenant is None:
            return

        subs = [s for s in self._subs if topic in s.topics]
        if not subs:
            return

        need_vis = any(
            s.claims.role == "gov_operator" and str(s.claims.tenant_id) != str(tenant) for s in subs
        )
        visibility = await self._tenant_visibility(tenant) if need_vis else "private"

        candidates = [s for s in subs if _can_maybe_see(s.claims, tenant, visibility)]
        if not candidates:
            return

        groups: dict[tuple[str, str], list[Subscriber]] = defaultdict(list)
        for s in candidates:
            groups[(s.claims.tenant_id, s.claims.role)].append(s)

        for (tenant_id, role), members in groups.items():
            ctx = SessionCtx(tenant_id=tenant_id, role=role, user_id="")
            frame = await self._build_frame(ctx, t or "", payload)
            if frame is None:
                continue
            for s in members:
                # [T-2.08] site_scope default-deny en la ENTREGA: un suscriptor
                # acotado (p.ej. brigadista de un sitio) no recibe frames de
                # otros sitios de su tenant. scope None = sin filtro ("*").
                if not _frame_in_scope(s.claims, frame):
                    continue
                await self._send(s, frame)

    async def _build_frame(
        self, ctx: SessionCtx, t: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Re-consulta la fila con los GUCs del suscriptor y arma el frame tipado."""
        if t == "checkin":
            # [T-2.11] El frame es una señal SIN PII (solo ids): se arma del
            # payload, sin re-consulta. El prefiltro de tenant y el site_scope
            # de la entrega (T-2.08) ya lo acotan; la PII vive en el REST.
            tenant = payload.get("tenant")
            site = payload.get("site")
            incident = payload.get("incident_id")
            if tenant is None or site is None or incident is None:
                return None
            return p.RosterSignalFrame(
                tenant_id=_uuid(tenant), site_id=_uuid(site), incident_id=_uuid(incident)
            ).model_dump(mode="json")
        async with get_tenant_conn(ctx) as conn:
            if t == "incident":
                row = (await conn.execute(_SQL_INCIDENT, {"id": _uuid(payload.get("id"))})).first()
                if row is None:
                    return None
                return p.IncidentFrame(**row._mapping).model_dump(mode="json")
            if t == "incident_action":
                row = (await conn.execute(_SQL_ACTION, {"id": _uuid(payload.get("id"))})).first()
                if row is None:
                    return None
                return p.IncidentActionFrame(**row._mapping).model_dump(mode="json")
            if t == "device_health":
                row = (
                    await conn.execute(_SQL_DEVICE_HEALTH, {"gw": _uuid(payload.get("gateway_id"))})
                ).first()
                if row is None:
                    return None
                return p.SiteStateFrame(kind="device_health", **row._mapping).model_dump(
                    mode="json"
                )
            if t == "rule_evaluation":
                row = (
                    await conn.execute(_SQL_RULE_EVAL, {"gw": _uuid(payload.get("gateway_id"))})
                ).first()
                if row is None:
                    return None
                return p.SiteStateFrame(kind="rule_evaluation", **row._mapping).model_dump(
                    mode="json"
                )
        return None

    async def _tenant_visibility(self, tenant_id: str) -> str:
        now = monotonic()
        hit = self._visibility.get(str(tenant_id))
        if hit is not None and hit[1] > now:
            return hit[0]
        async with get_tenant_conn(_VISIBILITY_CTX) as conn:
            row = (await conn.execute(_SQL_VISIBILITY, {"t": _uuid(tenant_id)})).first()
        vis = row.visibility if row is not None else "private"
        self._visibility[str(tenant_id)] = (vis, now + _VISIBILITY_TTL_S)
        return vis

    async def _send(self, sub: Subscriber, frame: dict[str, Any]) -> None:
        async with sub.send_lock:
            try:
                await sub.ws.send_json(frame)
            except Exception:  # noqa: BLE001 - socket muerto: lo damos de baja
                await self.unregister(sub)


def _frame_in_scope(claims: Claims, frame: dict[str, Any]) -> bool:
    """True si el frame cae dentro del ``site_scope`` del suscriptor.

    Sin filtro (scope "*" → None) todo pasa. Con filtro, el frame debe traer
    ``site_id`` y estar en el alcance — un frame SIN sitio para un suscriptor
    acotado se descarta (default-deny, jamás "por si acaso").
    """
    allowed = scope_filter(claims)
    if allowed is None:
        return True
    site_id = frame.get("site_id")
    return site_id is not None and str(site_id) in allowed


def _can_maybe_see(claims: Claims, tenant: Any, visibility: str) -> bool:
    """Prefiltro barato de tenancy (la re-consulta RLS es la autoridad final)."""
    if str(claims.tenant_id) == str(tenant):
        return True
    if claims.role in _INTERNAL_ROLES:
        return True
    if claims.role == "gov_operator" and visibility == "gov_shared":
        return True
    return False


def _uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


# Singleton de proceso.
hub = Hub()
