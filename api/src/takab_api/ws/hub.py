"""Hub de fan-out del WebSocket live (T-1.22 · B4).

Registra sockets por ``(claims, topics)`` y, ante cada NOTIFY del canal
``takab_live`` (ver migración 0004), reparte el cambio a los suscriptores que
tengan derecho a verlo. El payload del NOTIFY es SOLO una señal de invalidación
(tenant/site/id); el hub **re-consulta la fila con los GUCs del suscriptor** y
Postgres/RLS decide qué se ve — el payload crudo NUNCA se reenvía al cliente.

Ruta de un notify:
0. ``dispatch`` lo encola en el carril de su ``(tenant, topic)`` y VUELVE; una
   tarea por carril reparte en orden (T-2.128, ver abajo).
1. ``_repartir`` mapea el tipo a un topic (``incident``/``incident_action`` →
   ``incidents``; ``device_health``/``rule_evaluation`` → ``site_state``).
2. Prefiltra suscriptores por visibilidad de tenant (propio ∪ takab-interno ∪
   gov sobre tenants ``gov_shared``), cacheando ``tenants.visibility`` ~60 s.
3. Agrupa los candidatos por clase ``(tenant_id, role)`` → UNA re-consulta por
   clase (no por socket) con esos GUCs. Si RLS oculta la fila, no se envía.

Presupuesto <2 s edge→browser: nuestra mitad (commit→NOTIFY→fetch→push) es
<100 ms; el resto es latencia de ingesta (T-1.17 commitea ``q-events`` ≤1.5 s).

[T-2.121] **Las re-consultas del hub tienen tope de espera, y el suscriptor al
que no se le puede servir se entera.** Medido antes de arreglarlo: con un ACCESS
EXCLUSIVE ajeno sobre ``incidents`` (una migración, un ``VACUUM FULL``, un
``TRUNCATE`` de mantenimiento) la re-consulta se encolaba detrás y ``dispatch``
no volvía nunca. Como ``run_listener`` despacha los NOTIFY **en serie**, eso no
perdía un frame: paraba el fan-out del proceso entero, para todos los tenants —
y encima retenía conexiones del pool (5+5), así que a los 10 bloqueos el REST
también se quedaba sin conexión (30 s hasta el ``TimeoutError`` del pool).
Ninguna de las dos cosas se veía: el socket seguía abierto y la consola seguía
pintando «CONECTADO · ● LIVE».

[T-2.128] **El reparto ya no es una sola fila india: hay un carril por
``(tenant, topic)``.** El tope de T-2.121 dejó el apagón en 3 s en vez de
indefinido, pero la serialización seguía entera — medido: con ``incidents``
bloqueada, el frame de OTRO tenant que ni tocaba la base tardaba **3.06 s**.
Ahora sale en <0.05 s porque va por su propio carril.

El corte es ``(tenant, topic)`` y no más fino a propósito: dentro de un carril el
orden queda igual que siempre, que es lo que necesita una consola que indexa por
id y se queda con el ÚLTIMO frame. Ver ``_lane_key`` para el censo de quién
depende del orden.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.websockets import WebSocket

from takab_api.auth.claims import Claims, scope_filter
from takab_api.db.session import BACKGROUND_LOCK_TIMEOUT_MS, SessionCtx, get_tenant_conn
from takab_api.ws import protocol as p

logger = logging.getLogger("takab_api.ws")

#: [T-2.121] Cierre por CANAL LIVE DEGRADADO: el hub tenía algo que entregarle a
#: este socket y no pudo leerlo. No es un error del cliente ni de su token (4401
#: es eso), así que el ``LiveSocket`` del SDK lo trata como cualquier caída y
#: reconecta con backoff; entretanto la topbar pinta «CONECTANDO…» y la cola de
#: incidentes «● SIN LIVE», que es la verdad, y el REST sigue sirviendo el dato
#: (regla de oro 2). Callarse era dejar al operador con un «● LIVE» mintiendo.
WS_LIVE_DEGRADED = 4503

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


@dataclass(eq=False)
class _Lane:
    """[T-2.128] Cola ordenada de un ``(tenant, topic)`` + su tarea drenadora."""

    cola: deque[dict[str, Any]] = field(default_factory=deque)
    tarea: asyncio.Task[Any] | None = None
    descartados: int = 0


def _lane_key(payload: dict[str, Any]) -> str | None:
    """Carril de un notify: ``(tenant, topic)``. ``None`` = payload que se descarta.

    **El corte es el resultado del criterio 1 de T-2.128, no una comodidad.** El
    topic es exactamente la unidad a la que un cliente se suscribe, así que:

    · Dentro del carril el orden queda **idéntico al de hoy**. Eso es obligatorio:
      la consola indexa por id y **el último frame gana** (``mergeIncidents``,
      ``liveHealth.store``), así que adelantar dos invalidaciones de la misma
      entidad dejaría pintado el estado viejo hasta el refetch de 30 s — regla de
      oro 7 en la pantalla donde se manda una brigada. Y conserva además la
      secuencia CRUZADA que hoy se asume y se prueba: el frame del incidente va
      antes que las acciones de ese incidente.
    · Entre carriles no hay nada que correlacionar: todo estado de cliente está
      indexado por un id que pertenece a un solo tenant y viaja por un solo
      topic, así que ningún consumidor puede observar el reordenamiento.

    Cortar más fino (un carril por entidad) rompería lo primero para ganar poco;
    cortar más grueso (un carril y ya) es exactamente el defecto que cierra la
    ficha.
    """
    topic = _TOPIC_BY_TYPE.get(payload.get("t") or "")
    tenant = payload.get("tenant")
    if topic is None or tenant is None:
        return None
    return f"{tenant}|{topic}"


#: Notifies en espera que aguanta UN carril antes de tirar los más viejos. Un
#: carril solo se llena si su tabla lleva rato bloqueada, y entonces la cola es
#: memoria que crece sin techo con un proceso que no puede vaciarla: 32 sobra
#: para cualquier ráfaga real (el presupuesto edge→browser es <2 s) y acota el
#: daño de la patológica.
_LANE_MAX = 32


class Hub:
    """Singleton de proceso: LISTEN de fondo + registro de sockets + fan-out."""

    def __init__(self) -> None:
        self._subs: set[Subscriber] = set()
        self._listener: asyncio.Task[Any] | None = None
        self._ready = asyncio.Event()
        self._visibility: dict[str, tuple[str, float]] = {}
        self._running = False
        #: [T-2.128] Un carril por ``(tenant, topic)`` vivo; se crean al vuelo y
        #: se recogen en cuanto se vacían (si no, serían una fuga por tenant).
        self._lanes: dict[str, _Lane] = {}

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
        """Cancela la tarea LISTEN, los carriles y los pollers; limpia el registro."""
        self._running = False
        if self._listener is not None:
            self._listener.cancel()
            try:
                await self._listener
            except asyncio.CancelledError:
                pass
            self._listener = None
        # [T-2.128] Los carriles se cancelan, no se drenan: al parar el proceso lo
        # que queda en cola es reparto que ya no tiene a quién llegar.
        for lane in list(self._lanes.values()):
            if lane.tarea is not None:
                lane.tarea.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await lane.tarea
        self._lanes.clear()
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
        """[T-2.128] Encola el notify en SU carril y vuelve. No espera al reparto.

        Antes esto repartía en línea, y como ``run_listener`` hace ``await
        hub.dispatch`` notify a notify, un solo reparto lento paraba el fan-out
        del proceso entero — todos los topics, todos los tenants, incluidos los
        frames que ni tocaban la tabla en cuestión (medido en T-2.121: 25 s sin
        tope, 3.06 s con él). Volver rápido de aquí es lo que rompe esa cadena
        sin tocar ``listener.py``: la cola vive en el hub, que es de quien es el
        problema.

        Quien necesite el reparto TERMINADO (los tests) llama a ``drain()``.
        """
        key = _lane_key(payload)
        if key is None:
            return  # tipo desconocido o sin tenant: mismo descarte de siempre
        lane = self._lanes.get(key)
        if lane is None:
            lane = _Lane()
            self._lanes[key] = lane
        if len(lane.cola) >= _LANE_MAX:
            # Tirar el MÁS VIEJO y no el nuevo: cada frame se re-consulta contra
            # la fila actual, así que el reciente describe mejor la realidad que
            # el que lleva minutos en la cola. Se registra porque una cola llena
            # significa que algo lleva mucho rato sin poder leer.
            lane.cola.popleft()
            lane.descartados += 1
            logger.warning(
                "ws: carril %s lleno (%d): se descarta el notify más viejo (%d en total)",
                key,
                _LANE_MAX,
                lane.descartados,
            )
        lane.cola.append(payload)
        if lane.tarea is None:
            lane.tarea = asyncio.create_task(self._drenar_carril(key))

    async def _drenar_carril(self, key: str) -> None:
        """Reparte los notifies de UN carril, en orden y de uno en uno."""
        lane = self._lanes.get(key)
        if lane is None:
            return
        try:
            while lane.cola:
                payload = lane.cola.popleft()
                try:
                    await self._repartir(payload)
                except Exception:  # noqa: BLE001 - un notify no puede matar el carril
                    logger.exception("ws: fallo despachando notify en el carril %s", key)
        finally:
            # Sin await entre la salida del ``while`` y esto: ningún ``dispatch``
            # puede colarse en medio y quedarse con un carril sin drenador.
            lane.tarea = None
            if not lane.cola:
                self._lanes.pop(key, None)

    async def drain(self, timeout_s: float = 30.0) -> None:
        """Espera a que todos los carriles queden vacíos (tests y ``stop``)."""
        limite = monotonic() + timeout_s
        while monotonic() < limite:
            tareas = [ln.tarea for ln in self._lanes.values() if ln.tarea is not None]
            if not tareas:
                return
            await asyncio.wait(tareas, timeout=max(0.0, limite - monotonic()))
        logger.warning("ws: drain no vació los carriles en %.1f s", timeout_s)

    async def _repartir(self, payload: dict[str, Any]) -> None:
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
        visibility = "private"
        if need_vis:
            try:
                visibility = await self._tenant_visibility(tenant)
            except SQLAlchemyError as exc:
                # [T-2.121] Sin poder leer `tenants` no se sabe si este tenant
                # comparte con gobierno. Seguir con "private" entregaría de menos
                # EN SILENCIO justo a quien depende de ese metadato, así que se
                # le declara el canal degradado; el resto de suscriptores no
                # necesitaba la visibilidad y no se toca.
                await self._degradar(
                    [s for s in subs if s.claims.role == "gov_operator"],
                    f"visibilidad del tenant ilegible: {exc.__class__.__name__}",
                )
                subs = [s for s in subs if s.claims.role != "gov_operator"]

        candidates = [s for s in subs if _can_maybe_see(s.claims, tenant, visibility)]
        if not candidates:
            return

        groups: dict[tuple[str, str], list[Subscriber]] = defaultdict(list)
        for s in candidates:
            groups[(s.claims.tenant_id, s.claims.role)].append(s)

        for (tenant_id, role), members in groups.items():
            ctx = SessionCtx(tenant_id=tenant_id, role=role, user_id="")
            try:
                frame = await self._build_frame(ctx, t or "", payload)
            except SQLAlchemyError as exc:
                # [T-2.121] La base no dejó leer la fila (lock ajeno vencido por
                # el tope, o la DB caída). Estos suscriptores acaban de perderse
                # una invalidación y NO pueden saberlo: se les declara.
                await self._degradar(members, f"{t}: {exc.__class__.__name__}")
                continue
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
        # [T-2.121] Tope de espera por lock, escalón de SEGUNDO PLANO. Es la MISMA
        # política que aplican las dos laterales de auditoría (`audit.py`,
        # T-2.73.c / T-2.112) y se reutiliza a propósito en vez de inventar un
        # número: el día que cambie, cambia para todas. Sin él, un ACCESS
        # EXCLUSIVE ajeno paraba el fan-out del proceso entero (medido: no
        # volvía). [T-2.130] la política se declara ahora en `db/session.py` y se
        # pide por parámetro: una llamada menos y un sitio menos donde derivar.
        async with get_tenant_conn(ctx, lock_timeout_ms=BACKGROUND_LOCK_TIMEOUT_MS) as conn:
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
        # [T-2.121] mismo tope de segundo plano que arriba.
        async with get_tenant_conn(
            _VISIBILITY_CTX, lock_timeout_ms=BACKGROUND_LOCK_TIMEOUT_MS
        ) as conn:
            row = (await conn.execute(_SQL_VISIBILITY, {"t": _uuid(tenant_id)})).first()
        vis = row.visibility if row is not None else "private"
        self._visibility[str(tenant_id)] = (vis, now + _VISIBILITY_TTL_S)
        return vis

    async def _degradar(self, subs: list[Subscriber], motivo: str) -> None:
        """[T-2.121] Declara el canal DEGRADADO a quien no se le pudo servir.

        La alternativa —seguir con el ``continue`` de siempre— deja al operador
        con un socket abierto, una topbar que dice CONECTADO y una cola de
        incidentes que dice ● LIVE mientras se le escapó una invalidación. Eso es
        exactamente el dato congelado presentado como vivo que prohíbe la regla
        de oro 7, y en la superficie donde se decide a quién se manda una brigada.

        Se cierra con ``WS_LIVE_DEGRADED`` y no se manda un ``ErrorFrame``
        porque el ``LiveSocket`` compartido (``shared/sdk-ts/src/live.ts``)
        descarta los frames ``error`` y cualquier ``type`` que no conozca: hoy el
        ÚNICO canal que llega a la pantalla del operador es el estado del
        transporte. Un frame propio de degradación —más fino que tumbar el
        socket— exige tocar el SDK compartido y la consola; queda declarado en el
        informe de la ficha, no simulado aquí.

        El cierre no pierde dato: el REST sigue sirviendo (regla de oro 2), la
        consola refresca por TanStack Query y el SDK reconecta con backoff.
        """
        for sub in subs:
            logger.error(
                "ws: canal live DEGRADADO para tenant=%s role=%s (%s) — se cierra con %d",
                sub.claims.tenant_id,
                sub.claims.role,
                motivo,
                WS_LIVE_DEGRADED,
            )
            await self.unregister(sub)
            # El socket puede estar ya medio-muerto: el cierre es cortesía, no
            # condición del registro (que ya se limpió arriba).
            with contextlib.suppress(Exception):
                await sub.ws.close(
                    code=WS_LIVE_DEGRADED, reason="canal live degradado: la nube no pudo leer"
                )

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
