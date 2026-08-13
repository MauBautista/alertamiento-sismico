"""[T-2.129] El servidor sabe decir «tu live está degradado» SIN cerrar el canal.

`T-2.121` dejó la degradación visible, pero por el único camino que había: el
estado del TRANSPORTE. El hub cerraba el socket con un code propio (4503) porque
`shared/sdk-ts/src/live.ts` descarta los frames `error` y todo `type` que no
conozca — o sea que del servidor a la pantalla del operador no llegaba nada que
no fuera «conectado o no».

Funcionaba, y era desproporcionado: **un tropiezo de UNA consulta tiraba la
conexión entera**, con su re-handshake, su re-subscribe de todos los topics y su
ventana de reconexión con backoff. Aquí se fija la conducta nueva:

  · con la tabla bloqueada el canal SIGUE ABIERTO y el suscriptor recibe un
    `live_health` con `degraded: true` y el topic afectado;
  · el frame NO se repite mientras la degradación siga en pie (un aviso, no una
    tormenta);
  · y **sabe apagarse**: en cuanto la lectura vuelve a ser posible sale el
    `degraded: false`. Por dos caminos, y los dos están medidos abajo — con el
    siguiente notify, y SOLO (la sonda de recuperación), que es lo que impide
    que el aviso se quede encendido para siempre en un rato de silencio.

Lo que NO cambia: el 4401 del handshake (`routers/ws.py`) sigue cerrando. Un
token vencido no es una degradación del canal, es una sesión que se acabó.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any

import pytest
from sqlalchemy import text
from starlette.websockets import WebSocketState

from takab_api.auth.claims import ALL_SITES, Claims
from takab_api.db.engine import get_engine
from takab_api.ws.hub import hub
from tests.ws import _wsutil as w
from tests.ws.conftest import WS_GW_A, WS_SENSOR_A, WS_SITE_A, WS_TENANT_A

pytestmark = pytest.mark.asyncio

#: `takab_api.ws.__init__` re-exporta el SINGLETON con el nombre `hub`, así que
#: `from takab_api.ws import hub` devuelve el objeto y no el módulo. Para tocar
#: la constante de la sonda hace falta el módulo de verdad.
hub_mod = sys.modules[type(hub).__module__]

_fake = w.load_fake_ingest()

#: Techo del TEST (mismo criterio que `test_ws_hub_lock.py`): muy por encima del
#: `lock_timeout` de segundo plano (3 s) y muy por debajo de «para siempre».
_TOPE_TEST_S = 25.0

_LOCK_INCIDENTS = text("LOCK TABLE incidents IN ACCESS EXCLUSIVE MODE")
_ESPERANDO_LECTURA = text(
    "SELECT count(*) FROM pg_locks WHERE relation = CAST(:t AS regclass) "
    "AND mode = 'AccessShareLock' AND NOT granted"
)


class _SocketDeMentira:
    """WebSocket falso: apunta lo que se le manda y si lo cerraron (con qué code)."""

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
        sub="u-health",
        groups=(role,),
        tenant_id=tenant,
        role=role,
        site_scope=ALL_SITES,
        zone_id="",
        surface="web",
    )


def _quake() -> dict[str, str]:
    conn = _fake.connect(_fake.raw_dsn(os.environ["DATABASE_URL"]))
    try:
        return _fake.insert_quake(
            conn, tenant=WS_TENANT_A, site=WS_SITE_A, sensor=WS_SENSOR_A, gateway=WS_GW_A
        )
    finally:
        conn.close()


async def _esperar_encolado(tabla: str, tope_s: float = 10.0) -> None:
    """Bloquea hasta ver en `pg_locks` a alguien ESPERANDO leer `tabla`."""
    engine = get_engine()
    limite = time.monotonic() + tope_s
    while time.monotonic() < limite:
        async with engine.connect() as vigia:
            if (await vigia.execute(_ESPERANDO_LECTURA, {"t": tabla})).scalar_one():
                return
        await asyncio.sleep(0.05)
    pytest.fail(f"nadie se encoló por el ACCESS SHARE de {tabla}: el escenario no se montó")


def _suscriptor(topic: str, tenant: str = WS_TENANT_A) -> tuple[Any, _SocketDeMentira]:
    ws = _SocketDeMentira()
    sub = hub.register(ws, _claims(tenant))
    sub.topics.add(topic)
    return sub, ws


def _salud(ws: _SocketDeMentira) -> list[dict]:
    return [f for f in ws.frames if f["type"] == "live_health"]


@pytest.fixture(autouse=True)
async def _hub_limpio():
    """El hub es un singleton de proceso: ni suscriptores ni sondas heredadas."""
    await hub._cancelar_sondas()
    hub._subs.clear()
    hub._visibility.clear()
    yield
    await hub._cancelar_sondas()
    hub._subs.clear()
    hub._visibility.clear()


@pytest.fixture
def sonda_dormida(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aparta la sonda de recuperación: estos tests miden el OTRO camino."""
    monkeypatch.setattr(hub_mod, "_RECOVERY_PROBE_S", 3600.0)


async def test_la_degradacion_se_DECLARA_sin_cerrar_el_canal(ws_seed, sonda_dormida) -> None:
    """Criterio 1: el servidor puede decirlo sin tirarle el socket al operador.

    Antes de esta ficha, este mismo escenario terminaba en `close(4503)`. El
    socket se caía, el SDK reconectaba con backoff y el operador veía
    «CONECTANDO…» — que es verdad, pero es la verdad EQUIVOCADA: su sesión live
    estaba perfectamente sana, lo que falló fue UNA lectura.
    """
    ids = await asyncio.to_thread(_quake)
    sub, ws = _suscriptor("incidents")
    engine = get_engine()
    async with engine.connect() as bloqueo:
        await bloqueo.execute(_LOCK_INCIDENTS)
        await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
        await _esperar_encolado("incidents")
        await asyncio.wait_for(hub.drain(), _TOPE_TEST_S)
        await bloqueo.rollback()

    assert ws.cerrado is None, "el canal se cerró: eso es justo lo que esta ficha quita"
    assert sub in hub._subs, "el suscriptor salió del registro: dejaría de recibir sin razón"
    assert _salud(ws) == [
        {
            "type": "live_health",
            "degraded": True,
            "topic": "incidents",
            "detail": "incident: LockTimeout",
        }
    ]


async def test_no_se_repite_el_aviso_mientras_la_degradacion_siga_en_pie(
    ws_seed, sonda_dormida
) -> None:
    """Un aviso, no una tormenta: dos invalidaciones perdidas = un solo frame."""
    ids = await asyncio.to_thread(_quake)
    _, ws = _suscriptor("incidents")
    engine = get_engine()
    async with engine.connect() as bloqueo:
        await bloqueo.execute(_LOCK_INCIDENTS)
        await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
        await _esperar_encolado("incidents")
        await asyncio.wait_for(hub.drain(), _TOPE_TEST_S)
        await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
        await asyncio.wait_for(hub.drain(), _TOPE_TEST_S)
        await bloqueo.rollback()

    assert len(_salud(ws)) == 1, f"el operador recibió {len(_salud(ws))} avisos del mismo problema"


async def test_la_degradacion_SABE_APAGARSE_con_el_siguiente_notify(ws_seed, sonda_dormida) -> None:
    """Criterio: un banner que se queda encendido para siempre es otra mentira.

    Liberada la tabla, la primera lectura que vuelve a funcionar APAGA el aviso
    (`degraded: false`) y entrega el frame de datos. El apagado va primero a
    propósito: lo que se acaba de demostrar es que el canal lee, y el frame que
    viene detrás es la prueba.
    """
    ids = await asyncio.to_thread(_quake)
    _, ws = _suscriptor("incidents")
    engine = get_engine()
    async with engine.connect() as bloqueo:
        await bloqueo.execute(_LOCK_INCIDENTS)
        await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
        await _esperar_encolado("incidents")
        await asyncio.wait_for(hub.drain(), _TOPE_TEST_S)
        await bloqueo.rollback()

    await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
    await asyncio.wait_for(hub.drain(), _TOPE_TEST_S)

    assert [f["type"] for f in ws.frames] == ["live_health", "live_health", "incident"]
    assert _salud(ws)[-1] == {
        "type": "live_health",
        "degraded": False,
        "topic": "incidents",
        "detail": None,
    }


async def test_la_degradacion_se_apaga_SOLA_aunque_no_llegue_otro_notify(
    ws_seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La sonda de recuperación, y por qué no basta con esperar al siguiente notify.

    Un SOC puede pasar horas sin una sola invalidación de incidentes — es, de
    hecho, el estado normal. Si el aviso sólo se apagara con el notify siguiente,
    un bloqueo de treinta segundos a las 03:00 dejaría «LIVE DEGRADADO» encendido
    hasta el próximo sismo. La sonda reintenta LA MISMA lectura que falló, así
    que al apagarse **entrega también la invalidación que se había perdido**.
    """
    monkeypatch.setattr(hub_mod, "_RECOVERY_PROBE_S", 0.25)
    ids = await asyncio.to_thread(_quake)
    _, ws = _suscriptor("incidents")
    engine = get_engine()
    async with engine.connect() as bloqueo:
        await bloqueo.execute(_LOCK_INCIDENTS)
        await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
        await _esperar_encolado("incidents")
        await asyncio.wait_for(hub.drain(), _TOPE_TEST_S)
        assert _salud(ws) == [
            {
                "type": "live_health",
                "degraded": True,
                "topic": "incidents",
                "detail": "incident: LockTimeout",
            }
        ]
        await bloqueo.rollback()

    # NADIE despacha nada más: el apagado tiene que venir de la sonda.
    limite = time.monotonic() + _TOPE_TEST_S
    while time.monotonic() < limite and len(_salud(ws)) < 2:
        await asyncio.sleep(0.1)

    assert len(_salud(ws)) == 2, "el aviso se quedó encendido sin que nadie volviera a despachar"
    assert _salud(ws)[-1]["degraded"] is False
    assert [f["type"] for f in ws.frames if f["type"] == "incident"] == ["incident"], (
        "la sonda apagó el aviso pero no entregó la invalidación que se había perdido"
    )


async def test_un_frame_que_NO_lee_la_base_no_puede_apagar_el_aviso(ws_seed, sonda_dormida) -> None:
    """La trampa fina: `checkin` se arma del payload, sin re-consulta (T-2.11).

    Va por el topic `incidents`, así que si su éxito contara como «el canal ya
    lee», un check-in llegando con la tabla bloqueada apagaría el aviso sin haber
    demostrado nada — y el operador vería «canal sano» mientras sigue perdiendo
    invalidaciones de incidentes. Exactamente la mentira que la ficha cierra,
    reintroducida por la puerta de atrás.
    """
    ids = await asyncio.to_thread(_quake)
    _, ws = _suscriptor("incidents")
    engine = get_engine()
    async with engine.connect() as bloqueo:
        await bloqueo.execute(_LOCK_INCIDENTS)
        await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
        await _esperar_encolado("incidents")
        await asyncio.wait_for(hub.drain(), _TOPE_TEST_S)
        assert len(_salud(ws)) == 1 and _salud(ws)[0]["degraded"] is True

        await hub.dispatch(
            {
                "t": "checkin",
                "tenant": WS_TENANT_A,
                "site": WS_SITE_A,
                "incident_id": ids["incident_id"],
            }
        )
        await asyncio.wait_for(hub.drain(), _TOPE_TEST_S)
        await bloqueo.rollback()

    # El roster SÍ se entrega (no necesitaba la base: regla de oro 2 en pequeño).
    assert [f["type"] for f in ws.frames] == ["live_health", "roster"]
    # Y el aviso SIGUE encendido, que es lo que aquí se mide.
    assert len(_salud(ws)) == 1


async def test_sin_bloqueo_no_se_declara_nada(ws_seed, sonda_dormida) -> None:
    """El canal sano no gana ruido: cero `live_health` cuando todo funciona."""
    ids = await asyncio.to_thread(_quake)
    _, ws = _suscriptor("incidents")
    await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
    await hub.drain()
    assert [f["type"] for f in ws.frames] == ["incident"]
    assert _salud(ws) == []


async def test_el_frame_es_el_del_CONTRATO_no_un_diccionario_suelto() -> None:
    """El frame nuevo es un modelo del protocolo, así que viaja al OpenAPI solo.

    `api/scripts/export_openapi.py` inyecta en `components/schemas` TODO modelo
    Pydantic declarado en `ws/protocol.py`. Es lo que hace que el tipo llegue al
    SDK sin escribirlo a mano — y lo que impide que este frame nazca fuera del
    contrato, como un `dict` improvisado en el hub.
    """
    from takab_api.ws import protocol as p

    frame = p.LiveHealthFrame(degraded=True, topic="incidents", detail="x")
    assert frame.model_dump(mode="json") == {
        "type": "live_health",
        "degraded": True,
        "topic": "incidents",
        "detail": "x",
    }
    assert "live_health" in p.SERVER_FRAME_TYPES
    # El censo es DERIVADO, no una lista: los frames de cliente→servidor (que
    # exigen su `type`) quedan fuera solos.
    assert {"ready", "error", "incident", "live_health"} <= p.SERVER_FRAME_TYPES
    assert "auth" not in p.SERVER_FRAME_TYPES
    assert "subscribe" not in p.SERVER_FRAME_TYPES
