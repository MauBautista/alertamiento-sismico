"""[T-2.128] El fan-out deja de ser una sola fila india. MEDIDO.

`T-2.121` midió que `run_listener` despacha los NOTIFY **en serie** (`await
hub.dispatch` uno a uno) y que por eso un `dispatch` colgado no perdía un frame:
**paraba el reparto del proceso entero, para todos los tenants**. Acotar la
espera a 3 s dejó el apagón en 3 s en vez de indefinido, pero la serialización
seguía intacta — y ese es el mecanismo, no el síntoma.

**La investigación del criterio 1: ¿quién depende del orden?** Censo de los
consumidores reales, no de lo que parece:

    · `useLiveIncidents` (web) — `mergeIncidents` hace `byId.set(incident_id,
      frame)`: **último que llega, gana**. Dos frames del MISMO incidente fuera
      de orden dejarían pintado el estado viejo hasta el refetch REST (30 s).
      Depende del orden, por incidente.
    · `liveHealth.store` / `useSiteSoh` (web) — `heartbeats[gateway_id] = frame`
      y `setSoh(frame)`: mismo último-gana, por gateway.
    · `useIncidentActions` (web) — dedup por `action_id` y **re-ordena por
      `ts`**: inmune al orden de llegada.
    · `roster`/checkin y `useMapState` — pura invalidación (refetch): inmunes.
    · Y una expectativa CRUZADA que sí existe y no está en ningún consumidor
      sino en el protocolo tal como se usa hoy: el frame del incidente llega
      ANTES que las acciones de ese incidente
      (`test_ws_incidents.py::test_incident_action_frames_follow`).

De ahí sale el carril: **uno por `(tenant, topic)`**. El `topic` es exactamente
la unidad que el cliente se suscribe, así que dentro de un carril el orden queda
**idéntico al de hoy** —incluida la secuencia incidente→sus acciones— y entre
carriles no hay nada que correlacionar: todo estado de cliente está indexado por
un id que pertenece a un solo tenant y llega por un solo topic.

Lo que este fichero fija: que un carril atascado **no calla a los demás**, y que
dentro de un carril el orden se conserva.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import psycopg
import pytest
from starlette.websockets import WebSocketState

from takab_api.auth.claims import ALL_SITES, Claims
from takab_api.ws.hub import hub
from tests.ws import _wsutil as w
from tests.ws.conftest import (
    WS_GW_A,
    WS_SENSOR_A,
    WS_SITE_A,
    WS_SITE_B,
    WS_TENANT_A,
    WS_TENANT_B,
)

pytestmark = pytest.mark.asyncio

_fake = w.load_fake_ingest()

#: Cuánto se le da al carril libre para entregar mientras el otro está atascado.
#: El carril atascado tarda 3 s (la política de segundo plano); si el libre no
#: entrega MUCHO antes, es que sigue detrás de él.
_TOPE_CARRIL_LIBRE_S = 1.0

_LOCK_INCIDENTS = "LOCK TABLE incidents IN ACCESS EXCLUSIVE MODE"
_ESPERANDO_LECTURA = (
    "SELECT count(*) FROM pg_locks WHERE relation = 'incidents'::regclass "
    "AND mode = 'AccessShareLock' AND NOT granted"
)


class _SocketDeMentira:
    """WebSocket falso: apunta lo que se le manda y si lo cerraron."""

    application_state = WebSocketState.CONNECTED

    def __init__(self) -> None:
        self.frames: list[dict] = []
        self.cerrado: tuple[int, str | None] | None = None

    async def send_json(self, frame: dict) -> None:
        self.frames.append(frame)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.cerrado = (code, reason)


def _claims(tenant: str = WS_TENANT_A, role: str = "soc_operator") -> Claims:
    return Claims(
        sub="u-carril",
        groups=(role,),
        tenant_id=tenant,
        role=role,
        site_scope=ALL_SITES,
        zone_id="",
        surface="web",
    )


def _raw_dsn() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


def _quake() -> dict[str, str]:
    conn = _fake.connect(_fake.raw_dsn(os.environ["DATABASE_URL"]))
    try:
        return _fake.insert_quake(
            conn, tenant=WS_TENANT_A, site=WS_SITE_A, sensor=WS_SENSOR_A, gateway=WS_GW_A
        )
    finally:
        conn.close()


def _salud() -> None:
    conn = _fake.connect(_fake.raw_dsn(os.environ["DATABASE_URL"]))
    try:
        _fake.insert_health_transition(conn, tenant=WS_TENANT_A, gateway=WS_GW_A)
    finally:
        conn.close()


def _suscriptor(topic: str, tenant: str = WS_TENANT_A) -> tuple[Any, _SocketDeMentira]:
    ws = _SocketDeMentira()
    sub = hub.register(ws, _claims(tenant))
    sub.topics.add(topic)
    return sub, ws


async def _esperar_encolado(tope_s: float = 10.0) -> None:
    limite = time.monotonic() + tope_s
    async with await psycopg.AsyncConnection.connect(_raw_dsn()) as vigia:
        while time.monotonic() < limite:
            cur = await vigia.execute(_ESPERANDO_LECTURA)
            fila = await cur.fetchone()
            if fila and fila[0]:
                return
            await asyncio.sleep(0.05)
    pytest.fail("nadie se encoló por el ACCESS SHARE de incidents: el escenario no se montó")


async def _esperar_frames(ws: _SocketDeMentira, tope_s: float) -> float:
    """Devuelve cuánto tardó en llegar el primer frame, o falla."""
    limite = time.monotonic() + tope_s
    inicio = time.monotonic()
    while time.monotonic() < limite:
        if ws.frames:
            return time.monotonic() - inicio
        await asyncio.sleep(0.01)
    return -1.0


@pytest.fixture(autouse=True)
async def _hub_limpio():
    """El hub es singleton de proceso: ni suscriptores ni carriles se heredan."""
    hub._subs.clear()
    hub._visibility.clear()
    await hub.drain()
    yield
    await hub.drain()
    hub._subs.clear()
    hub._visibility.clear()


async def test_MEDIDO_un_carril_atascado_NO_calla_a_los_demas(ws_seed) -> None:
    """Criterio 2, y la medición que lo justifica.

    Antes: `run_listener` hacía `await hub.dispatch(...)` uno detrás de otro, así
    que el segundo notify —de otro tenant y sin tocar la base— **no salía hasta
    que el primero terminaba** (medido en T-2.121: ni en 25 s sin tope; 3 s con
    él). Ahora cada `(tenant, topic)` tiene su carril y el segundo sale de
    inmediato mientras el primero sigue encolado en Postgres.
    """
    ids = await asyncio.to_thread(_quake)
    _, ws_atascado = _suscriptor("incidents")
    _, ws_libre = _suscriptor("incidents", tenant=WS_TENANT_B)

    conn = await psycopg.AsyncConnection.connect(_raw_dsn())
    await conn.execute(_LOCK_INCIDENTS)
    try:
        # La misma SERIE que hace el listener: uno detrás de otro, sin concurrencia
        # propia del test. Si el reparto sigue siendo en serie, el segundo espera.
        await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
        await hub.dispatch(
            {
                "t": "checkin",
                "tenant": WS_TENANT_B,
                "site": WS_SITE_B,
                "incident_id": ids["incident_id"],
            }
        )
        await _esperar_encolado()
        tardanza = await _esperar_frames(ws_libre, _TOPE_CARRIL_LIBRE_S)
        assert tardanza >= 0, (
            f"el frame del carril libre no salió en {_TOPE_CARRIL_LIBRE_S} s mientras el otro "
            "esperaba un lock: el fan-out sigue siendo en serie (T-2.128)"
        )
        assert ws_libre.frames[-1]["type"] == "roster"
        assert ws_atascado.frames == [], "el carril atascado no debe inventarse un frame"
    finally:
        await conn.rollback()
        await conn.close()
        await hub.drain()


async def test_un_carril_atascado_no_para_OTRO_TOPIC_del_mismo_tenant(ws_seed) -> None:
    """El corte fino: `(tenant, topic)`, no solo `tenant`.

    El sismograma y la salud del gabinete de un inmueble no tienen por qué
    callarse porque la cola de incidentes de ESE MISMO inmueble tropiece: son
    dos suscripciones distintas y ningún cliente las correlaciona.
    """
    ids = await asyncio.to_thread(_quake)
    await asyncio.to_thread(_salud)
    _, ws_incidentes = _suscriptor("incidents")
    _, ws_estado = _suscriptor("site_state")

    conn = await psycopg.AsyncConnection.connect(_raw_dsn())
    await conn.execute(_LOCK_INCIDENTS)
    try:
        await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
        await hub.dispatch({"t": "device_health", "tenant": WS_TENANT_A, "gateway_id": WS_GW_A})
        await _esperar_encolado()
        tardanza = await _esperar_frames(ws_estado, _TOPE_CARRIL_LIBRE_S)
        assert tardanza >= 0, (
            "la salud del gabinete se quedó detrás de la cola de incidentes del mismo tenant"
        )
        assert ws_estado.frames[-1]["type"] == "site_state"
        assert ws_incidentes.frames == []
    finally:
        await conn.rollback()
        await conn.close()
        await hub.drain()


async def test_DENTRO_de_un_carril_el_orden_se_conserva(ws_seed) -> None:
    """Criterio 1: desacoplar no puede reordenar lo que alguien lee por último-gana.

    `useLiveIncidents` indexa por `incident_id` y **el último frame gana**; si dos
    invalidaciones del mismo incidente se adelantaran, la consola se quedaría
    pintando el estado viejo hasta el refetch de 30 s. Aquí se despachan dos
    seguidas y se exige que salgan en el orden en que entraron.
    """
    primero = await asyncio.to_thread(_quake)
    segundo = await asyncio.to_thread(_quake)
    _, ws = _suscriptor("incidents")

    await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": primero["incident_id"]})
    await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": segundo["incident_id"]})
    await hub.drain()

    entregados = [f["incident_id"] for f in ws.frames]
    assert entregados == [primero["incident_id"], segundo["incident_id"]], (
        "el carril reordenó dos invalidaciones del mismo topic y tenant"
    )


async def test_los_carriles_se_recogen_cuando_terminan(ws_seed) -> None:
    """Un carril por entidad viva sería una fuga: se crean y se tiran."""
    ids = await asyncio.to_thread(_quake)
    _suscriptor("incidents")
    await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
    await hub.drain()
    assert hub._lanes == {}, f"carriles huérfanos tras drenar: {list(hub._lanes)}"


async def test_un_notify_ilegible_no_abre_carril(ws_seed) -> None:
    """El descarte de siempre (tipo desconocido / sin tenant) sigue siendo gratis."""
    await hub.dispatch({"t": "no_existe", "tenant": WS_TENANT_A})
    await hub.dispatch({"t": "incident"})
    assert hub._lanes == {}
