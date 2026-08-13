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

[T-2.129] **La degradación ya no se dice cerrando el socket.** T-2.121 lo hizo
así porque no había otra forma de hablar: el SDK descartaba los frames ``error``
y todo ``type`` desconocido, así que el estado del transporte era el único canal
servidor→pantalla. Ahora el hub manda un ``LiveHealthFrame`` (``degraded``
true/false, con el topic afectado) y el canal SIGUE ABIERTO — el resto de topics
ni se entera, y el aviso sabe apagarse: con el siguiente notify que sí lea, o
solo, por la sonda de recuperación (``_sondear``). El cierre 4503 desapareció;
el 4401 del handshake (``routers/ws.py``) sigue igual, porque un token vencido
no es una degradación del canal.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
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

_INTERNAL_ROLES = frozenset({"takab_superadmin", "takab_support"})
_VISIBILITY_TTL_S = 60.0
_LISTEN_READY_TIMEOUT_S = 5.0

#: [T-2.129] Primera espera de la SONDA antes de reintentar la lectura que falló.
#: Existe para que el aviso sepa apagarse SIN depender de que llegue otro notify:
#: un SOC pasa horas sin una sola invalidación —es su estado normal—, así que
#: atar el apagado al tráfico dejaría «LIVE DEGRADADO» encendido hasta el próximo
#: sismo.
_RECOVERY_PROBE_S = 2.0

#: Y el tope al que crece esa espera, que NO es cosmético. Cada intento retiene
#: una conexión del pool del request (5+5) hasta que vence el tope de segundo
#: plano (3 s). Con espera fija de 2 s, un lock que afecte a muchos grupos
#: ``(tenant, rol, topic)`` tendría a casi todas las sondas dentro de la base a
#: la vez: la sonda de recuperación se convertiría en la misma forma de
#: agotamiento del pool que acaban de cerrar `T-2.130` y `T-2.131`. Con el
#: crecimiento exponencial hasta 30 s, el ciclo de trabajo de cada sonda cae a
#: ~10 % y el apagado sigue llegando en menos de medio minuto.
_RECOVERY_PROBE_MAX_S = 30.0

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

#: [T-2.129] Tipos que ``_build_frame`` resuelve SIN tocar la base. Su éxito no
#: es evidencia de que el canal pueda leer, así que no apaga una degradación.
#: Es el espejo de la rama ``t == "checkin"`` de ``_build_frame``: si algún día
#: hay un segundo frame sin re-consulta, tiene que aparecer aquí.
_TIPOS_SIN_LECTURA = frozenset({"checkin"})

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
    #: [T-2.129] Topics que YA se le declararon degradados. Sin esta memoria el
    #: aviso saldría por cada notify perdido: una tormenta de frames diciendo lo
    #: mismo, y ningún `degraded: false` que la cierre.
    degradado: set[str] = field(default_factory=set)


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
        #: [T-2.129] Sondas de recuperación vivas, una por ``(tenant, rol, topic)``
        #: degradado. Se auto-recogen al apagar su degradación.
        self._sondas: dict[str, asyncio.Task[Any]] = {}

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
        await self._cancelar_sondas()
        for sub in list(self._subs):
            await self._cancel_pollers(sub)
        self._subs.clear()
        self._visibility.clear()

    async def _cancelar_sondas(self) -> None:
        """[T-2.129] Mata las sondas de recuperación (parada del proceso y tests)."""
        for tarea in list(self._sondas.values()):
            tarea.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await tarea
        self._sondas.clear()

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
                #
                # [T-2.129] Esta rama NO arma sonda: los afectados pueden ser de
                # varios tenants a la vez y la sonda es por grupo. Se apaga en la
                # primera repartición que vuelva a leer `tenants` — que ocurre en
                # el notify siguiente de este mismo topic, unas líneas más abajo.
                await self._degradar(
                    [s for s in subs if s.claims.role == "gov_operator"],
                    topic,
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
                # [T-2.129] Y se arma la sonda con ESTA MISMA lectura: cuando
                # vuelva a funcionar, además de apagar el aviso entrega la
                # invalidación que se había perdido.
                await self._degradar(
                    members,
                    topic,
                    f"{t}: {exc.__class__.__name__}",
                    reintento=lambda ctx=ctx: self._build_frame(ctx, t or "", payload),
                    grupo=(tenant_id, role),
                )
                continue
            # La lectura funcionó: eso APAGA el aviso, lo haya o no. Va antes de
            # `frame is None` a propósito — que la fila no sea visible tras RLS no
            # quita que el canal esté leyendo bien.
            #
            # ...pero SOLO si de verdad hubo lectura. `checkin` se arma del propio
            # payload sin tocar la base (T-2.11), así que un check-in llegando con
            # `incidents` bloqueada apagaría el aviso sin haber demostrado nada:
            # el operador vería «canal sano» mientras sigue perdiendo
            # invalidaciones de incidentes. La degradación sólo la levanta una
            # lectura real.
            if t not in _TIPOS_SIN_LECTURA:
                await self._recuperar(members, topic)
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

    async def _degradar(
        self,
        subs: list[Subscriber],
        topic: str,
        motivo: str,
        reintento: Callable[[], Awaitable[dict[str, Any] | None]] | None = None,
        grupo: tuple[str, str] | None = None,
    ) -> None:
        """[T-2.121 · rehecho en T-2.129] Declara DEGRADADO el topic, sin cerrar.

        La alternativa —seguir con el ``continue`` de siempre— deja al operador
        con un socket abierto, una topbar que dice CONECTADO y una cola de
        incidentes que dice ● LIVE mientras se le escapó una invalidación. Eso es
        exactamente el dato congelado presentado como vivo que prohíbe la regla
        de oro 7, y en la superficie donde se decide a quién se manda una brigada.

        **T-2.121 lo dijo cerrando el socket (code 4503), y no por elección:** el
        ``LiveSocket`` compartido descartaba los frames ``error`` y todo ``type``
        que no conociera, así que el estado del transporte era el único canal
        servidor→pantalla que existía. Tirar la conexión por un tropiezo de UNA
        consulta arrastra re-handshake, re-subscribe de todos los topics y una
        ventana de backoff — y encima dice la verdad equivocada: la sesión estaba
        sana. Ahora se manda un ``LiveHealthFrame`` y el canal sigue vivo, con lo
        que el resto de topics ni se entera.

        El aviso se manda UNA vez por topic (``sub.degradado``): un bloqueo largo
        pierde muchas invalidaciones y ninguna añade información a la primera.

        ``reintento`` es la lectura que falló. Con ella se arma la sonda que
        apaga el aviso sola —ver ``_sondear``—; sin ella el apagado espera al
        siguiente notify que sí pueda leer.
        """
        nuevos = [s for s in subs if topic not in s.degradado]
        for sub in nuevos:
            sub.degradado.add(topic)
            logger.error(
                "ws: canal live DEGRADADO en topic=%s para tenant=%s role=%s (%s)",
                topic,
                sub.claims.tenant_id,
                sub.claims.role,
                motivo,
            )
            await self._send(
                sub, p.LiveHealthFrame(degraded=True, topic=topic, detail=motivo).model_dump()
            )
        if reintento is not None and grupo is not None:
            self._armar_sonda(grupo, topic, reintento)

    async def _recuperar(self, subs: list[Subscriber], topic: str) -> None:
        """[T-2.129] Apaga el aviso: el canal volvió a poder leer este topic.

        Un banner que se enciende y no sabe apagarse es la misma regla de oro 7
        del revés — al tercer día el operador deja de leerlo.
        """
        for sub in subs:
            if topic not in sub.degradado:
                continue
            sub.degradado.discard(topic)
            logger.info(
                "ws: canal live RECUPERADO en topic=%s para tenant=%s role=%s",
                topic,
                sub.claims.tenant_id,
                sub.claims.role,
            )
            await self._send(sub, p.LiveHealthFrame(degraded=False, topic=topic).model_dump())

    def _armar_sonda(
        self,
        grupo: tuple[str, str],
        topic: str,
        reintento: Callable[[], Awaitable[dict[str, Any] | None]],
    ) -> None:
        """Una sola sonda por ``(tenant, rol, topic)``; la primera manda."""
        key = f"{grupo[0]}|{grupo[1]}|{topic}"
        if key in self._sondas:
            return
        self._sondas[key] = asyncio.create_task(self._sondear(key, grupo, topic, reintento))

    async def _sondear(
        self,
        key: str,
        grupo: tuple[str, str],
        topic: str,
        reintento: Callable[[], Awaitable[dict[str, Any] | None]],
    ) -> None:
        """[T-2.129] Reintenta LA MISMA lectura hasta que vuelva a funcionar.

        Reintentar la lectura concreta —y no un ``SELECT 1`` de cortesía— tiene
        una consecuencia que justifica la sonda por sí sola: al apagar el aviso
        **entrega la invalidación que se había perdido**, en vez de dejar al
        operador esperando al refetch REST de 30 s.

        El grupo ``(tenant, rol)`` acota a quién se le entrega ese frame: se
        construyó con los GUCs de ESE grupo y mandárselo a otro sería una fuga
        entre tenants. Que el aviso se apague sólo para su grupo es correcto: el
        de al lado tiene su propia sonda si de verdad falló.

        La espera CRECE (``_RECOVERY_PROBE_MAX_S``) porque cada reintento retiene
        una conexión del pool del request mientras dura el tope de lock: una
        sonda impaciente por grupo sería la misma forma de agotamiento del pool
        que cerraron ``T-2.130`` y ``T-2.131``, reintroducida por el lado del WS.
        """
        intento = 0
        try:
            while True:
                # Espera creciente: ver `_RECOVERY_PROBE_MAX_S`. Cada reintento
                # cuesta una conexión del pool durante el tope de lock.
                await asyncio.sleep(min(_RECOVERY_PROBE_S * 2**intento, _RECOVERY_PROBE_MAX_S))
                intento += 1
                afectados = [
                    s
                    for s in self._subs
                    if topic in s.degradado
                    and (s.claims.tenant_id, s.claims.role) == grupo
                    and topic in s.topics
                ]
                if not afectados:
                    return  # se fueron o ya se recuperaron por otra vía
                try:
                    frame = await reintento()
                except SQLAlchemyError:
                    continue  # sigue bloqueado: se vuelve a intentar
                await self._recuperar(afectados, topic)
                if frame is None:
                    return
                for sub in afectados:
                    if _frame_in_scope(sub.claims, frame):
                        await self._send(sub, frame)
                return
        finally:
            self._sondas.pop(key, None)

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
