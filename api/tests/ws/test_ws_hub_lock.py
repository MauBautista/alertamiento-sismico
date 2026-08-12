"""[T-2.121] Qué le pasa al hub del WebSocket con la tabla bloqueada. MEDIDO.

`T-2.112` dejó fichadas dos conexiones más sin tope de espera: `ws/hub.py` (la
re-consulta por suscriptor y la de visibilidad del tenant) y `ws/poller.py`.
**No** forman el ciclo indetectable de `T-2.73.c` —no cuelgan de la transacción
de un request—, así que la ficha pedía primero lo que nadie había hecho:
**medir**, en vez de suponer.

Lo medido (2026-08-11, contra el código anterior al arreglo):

    · El hub abre su conexión, pide el ACCESS SHARE de `incidents` y **se encola
      detrás del ACCESS EXCLUSIVE ajeno**. Comprobado en `pg_locks`: encolado,
      no concedido.
    · `hub.dispatch` NO VUELVE. Con un techo de 25 s en el test, la espera
      seguía viva; sin techo es la del lock ajeno — un `VACUUM FULL`, una
      migración, un `TRUNCATE` de mantenimiento— o sea, indefinida.
    · `run_listener` despacha los NOTIFY **en serie** (`await hub.dispatch` por
      cada uno), así que ese cuelgue no pierde un frame: **para el fan-out del
      proceso entero**. Ningún socket de ningún tenant recibe nada más mientras
      dure el bloqueo, incluidos los frames que no tocan la tabla bloqueada.
    · Y nadie se entera: el socket sigue abierto, la consola sigue pintando
      «SISTEMA OPERATIVO · CONECTADO» (`web/src/shell/Topbar.tsx`) y la cola de
      incidentes sigue diciendo «● LIVE» (`web/src/features/console/
      IncidentTable.tsx`). Un SOC que dejó de recibir sin decirlo es la regla de
      oro 7 en el peor sitio posible.

Lo que fija este archivo tras el arreglo: la espera es ACOTADA (la política de
segundo plano, 3 s — la misma que ya usan las dos laterales, no un número
nuevo), el fan-out del resto SIGUE, y al suscriptor al que no se le pudo servir
**se le dice**, cerrando su canal con un code propio en vez de dejarlo
creyéndose al día.

[T-2.128] La serialización que se describe arriba **ya no existe**: `dispatch`
encola en el carril de su `(tenant, topic)` y vuelve, y quien quiera el reparto
terminado llama a `hub.drain()`. Los tres tests de este fichero que esperaban a
`dispatch` para dar por entregado el frame documentaban exactamente esa
conducta, así que esperan a `drain`. La política del tope vive ahora en
`db/session.py` (T-2.130); `audit.LATERAL_LOCK_TIMEOUT_MS` sigue siendo su alias.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from typing import Any

import pytest
from sqlalchemy import text
from starlette.websockets import WebSocketState

from takab_api.audit import LATERAL_LOCK_TIMEOUT_MS
from takab_api.auth.claims import ALL_SITES, Claims
from takab_api.db.engine import get_engine
from takab_api.ws.hub import WS_LIVE_DEGRADED, hub
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

#: Techo del TEST, no del producto. Muy por encima del `lock_timeout` del hub
#: (3 s) para que un CI lento no invente un rojo, y muy por debajo de «para
#: siempre» para que el rojo llegue con nombre y no como un proceso colgado.
#: Mismo criterio que `tests/api/test_rejection_audit_deadlock.py` (T-2.112).
_TOPE_TEST_S = 25.0

_LOCK_INCIDENTS = text("LOCK TABLE incidents IN ACCESS EXCLUSIVE MODE")
_LOCK_FEATURES = text("LOCK TABLE waveform_features_1s IN ACCESS EXCLUSIVE MODE")

#: ¿Hay alguien ESPERANDO el ACCESS SHARE de la tabla? Es la prueba de que el
#: escenario es real y no una simulación: el hub está encolado, no lento.
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
        sub="u-lock",
        groups=(role,),
        tenant_id=tenant,
        role=role,
        site_scope=ALL_SITES,
        zone_id="",
        surface="web",
    )


def _dsn() -> str:
    return _fake.raw_dsn(os.environ["DATABASE_URL"])


def _quake() -> dict[str, str]:
    conn = _fake.connect(_dsn())
    try:
        return _fake.insert_quake(
            conn, tenant=WS_TENANT_A, site=WS_SITE_A, sensor=WS_SENSOR_A, gateway=WS_GW_A
        )
    finally:
        conn.close()


def _feature() -> None:
    conn = _fake.connect(_dsn())
    try:
        _fake.insert_feature(
            conn, tenant=WS_TENANT_A, site=WS_SITE_A, sensor=WS_SENSOR_A, pga_g=0.2
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


@pytest.fixture(autouse=True)
def _hub_limpio():
    """El hub es un singleton de proceso: ningún test puede heredar suscriptores."""
    hub._subs.clear()
    hub._visibility.clear()
    yield
    hub._subs.clear()
    hub._visibility.clear()


async def test_MEDIDO_el_hub_encolado_CEDE_en_vez_de_colgarse(ws_seed) -> None:
    """La medición del criterio 1, y la no-regresión del arreglo.

    Con `incidents` bajo ACCESS EXCLUSIVE ajeno, la re-consulta del hub queda
    ENCOLADA (se comprueba en `pg_locks`, no se supone). Antes del tope, el
    `dispatch` no volvía nunca; ahora cede en cuanto vence la política.
    """
    ids = await asyncio.to_thread(_quake)
    sub, ws = _suscriptor("incidents")
    engine = get_engine()
    async with engine.connect() as bloqueo:
        await bloqueo.execute(_LOCK_INCIDENTS)

        inicio = time.monotonic()
        # [T-2.128] `dispatch` encola y vuelve; quien espera al reparto es
        # `drain`. Antes de la ficha, esperar a `dispatch` era lo mismo — y ESO
        # era el defecto: el listener también esperaba, y con él todo lo demás.
        await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
        despacho = asyncio.create_task(hub.drain())
        try:
            await _esperar_encolado("incidents")
            assert not despacho.done(), "el hub no debería tener el lock: el tercero lo veta"
            await asyncio.wait_for(despacho, _TOPE_TEST_S)
        except TimeoutError:
            despacho.cancel()
            with contextlib.suppress(BaseException):
                await despacho
            pytest.fail(
                f"el hub siguió esperando el lock de `incidents` tras {_TOPE_TEST_S:.0f} s. "
                "Sin tope la espera dura lo que dure el lock ajeno y el fan-out del proceso "
                "entero se queda parado (T-2.121)."
            )
        tardanza = time.monotonic() - inicio
        await bloqueo.rollback()

    assert tardanza < _TOPE_TEST_S, f"el hub esperó {tardanza:.1f} s: el tope no actúa"
    assert ws.frames == [], "no había fila legible: no se inventa un frame"
    assert sub not in hub._subs


async def test_al_suscriptor_al_que_no_se_le_pudo_servir_SE_LE_DICE(ws_seed) -> None:
    """Criterio 2: la degradación no puede ser silenciosa.

    El hub tenía una invalidación para este socket y no pudo leerla. Callarse
    deja al operador con una consola que dice «CONECTADO · ● LIVE» mientras se
    le escapa un incidente. Se le cierra el canal con un code propio: el
    `LiveSocket` del SDK reconecta con backoff y, entretanto, la topbar pinta
    «CONECTANDO…» y la cola de incidentes «● SIN LIVE» — que es la verdad.
    """
    ids = await asyncio.to_thread(_quake)
    sub, ws = _suscriptor("incidents")
    engine = get_engine()
    async with engine.connect() as bloqueo:
        await bloqueo.execute(_LOCK_INCIDENTS)
        await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
        await _esperar_encolado("incidents")
        await asyncio.wait_for(hub.drain(), _TOPE_TEST_S)  # [T-2.128] el reparto va por carril
        await bloqueo.rollback()

    assert ws.cerrado is not None, "el socket siguió abierto creyéndose al día (regla de oro 7)"
    assert ws.cerrado[0] == WS_LIVE_DEGRADED
    assert sub not in hub._subs, "un canal degradado no se queda en el registro del hub"


async def test_el_bloqueo_no_deja_MUDO_al_resto_del_SOC(ws_seed) -> None:
    """Lo que convertía un lock en un apagón: el listener despacha EN SERIE.

    `run_listener` hace `await hub.dispatch(payload)` notify a notify, así que un
    dispatch colgado no pierde un frame: para todos los demás, de todos los
    tenants, incluidos los que ni tocan la tabla bloqueada. Aquí se reproduce esa
    serie con dos notifies —uno contra la tabla bloqueada y otro que no necesita
    la base (`checkin`)— y se exige que el segundo llegue.

    El segundo suscriptor es de OTRO tenant a propósito: al primero se le declara
    el canal degradado (es a quien no se pudo servir) y sale del registro. Que el
    de al lado siga recibiendo es justamente la diferencia entre «se perdió una
    invalidación» y «se apagó el SOC».
    """
    ids = await asyncio.to_thread(_quake)
    _, ws_incidente = _suscriptor("incidents")
    _, ws_roster = _suscriptor("incidents", tenant=WS_TENANT_B)
    engine = get_engine()
    inicio = time.monotonic()
    async with engine.connect() as bloqueo:
        await bloqueo.execute(_LOCK_INCIDENTS)

        async def _serie() -> None:
            await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
            await hub.dispatch(
                {
                    "t": "checkin",
                    "tenant": WS_TENANT_B,
                    "site": WS_SITE_B,
                    "incident_id": ids["incident_id"],
                }
            )

        serie = asyncio.create_task(_serie())
        await _esperar_encolado("incidents")
        try:
            await asyncio.wait_for(serie, _TOPE_TEST_S)
        except TimeoutError:
            serie.cancel()
            with contextlib.suppress(BaseException):
                await serie
            pytest.fail(
                f"tras {_TOPE_TEST_S:.0f} s el segundo notify seguía sin despacharse: un lock "
                "sobre `incidents` deja mudo al SOC entero (T-2.121)."
            )
        await bloqueo.rollback()
    tardanza = time.monotonic() - inicio

    assert ws_roster.frames, "el frame que NO tocaba la tabla bloqueada nunca salió"
    assert ws_roster.frames[-1]["type"] == "roster"
    assert ws_incidente.frames == []
    assert tardanza < _TOPE_TEST_S


async def test_sin_bloqueo_el_hub_reparte_como_siempre(ws_seed) -> None:
    """El tope no puede volverse una excusa para dejar de repartir."""
    ids = await asyncio.to_thread(_quake)
    _, ws = _suscriptor("incidents")
    await hub.dispatch({"t": "incident", "tenant": WS_TENANT_A, "id": ids["incident_id"]})
    await hub.drain()  # [T-2.128] el reparto ocurre en el carril, no en el `dispatch`
    assert [f["type"] for f in ws.frames] == ["incident"]
    assert ws.cerrado is None


async def test_el_poller_bloqueado_no_se_queda_colgado_y_SE_RECUPERA(ws_seed) -> None:
    """El poller de features, que degrada por otra vía y a propósito.

    Aquí no se cierra el canal: la ausencia de frames de features YA es visible
    —`DetailPanel` declara «SIN LIVE» pasada `FEATURES_STALE_MS`— y tumbar el
    socket del SOC por un tropiezo del strip sería desproporcionado. Lo que el
    tope arregla es lo otro: que el ciclo no se quede indefinidamente dentro de
    la consulta reteniendo su conexión del pool (5+5) y que vuelva solo en
    cuanto la tabla se libere.
    """
    await asyncio.to_thread(_feature)
    ws = _SocketDeMentira()
    sub = hub.register(ws, _claims())
    engine = get_engine()
    topic = f"features:{WS_SITE_A}"
    async with engine.connect() as bloqueo:
        await bloqueo.execute(_LOCK_FEATURES)
        await hub.subscribe(sub, topic)
        tarea = sub.pollers[topic]
        await _esperar_encolado("waveform_features_1s")
        # El tope vence, el ciclo lo registra y sigue vivo: ni frames inventados
        # ni tarea muerta.
        await asyncio.sleep(LATERAL_LOCK_TIMEOUT_MS / 1000.0 + 1.5)
        assert not tarea.done(), "el poller murió con la tabla bloqueada"
        assert ws.frames == [], "no se pudo leer: no se inventa un strip"
        await bloqueo.rollback()

    # Liberada la tabla, el ciclo siguiente vuelve a empujar sin que nadie
    # re-suscriba nada. La muestra se re-inserta porque la ventana del poller es
    # de 2 s: la de antes del bloqueo ya es pasado, y un strip viejo no debe
    # aparecer (esa parte de la regla de oro 7 la fija el propio `_WINDOW_S`).
    await asyncio.to_thread(_feature)
    for _ in range(60):
        if ws.frames:
            break
        await asyncio.sleep(0.1)
    await hub.unregister(sub)
    assert ws.frames and ws.frames[0]["type"] == "features", "el poller no se recuperó"
