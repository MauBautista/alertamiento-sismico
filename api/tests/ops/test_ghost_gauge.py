"""T-2.60.a · La métrica que delata al gabinete retirado que sigue latiendo.

La consola ya lo pinta arriba y en rojo (PR #51), pero eso solo funciona si
alguien está mirando la pantalla. El fallo del 2026-08-04 duró horas justamente
porque nadie miraba: se supo cuando el operador preguntó por su estación.

Esta métrica es la mitad que no depende de que haya un humano delante.

Lo que estos tests fijan, y por qué cada uno existe:

1. **Se publica SIEMPRE, también el cero.** Es la lección de la alarma de
   gabinete mudo: si la métrica solo aparece cuando hay algo que contar, la
   alarma vive en INSUFFICIENT_DATA y todo depende de `treat_missing_data`, que
   ya nos falló de cuatro maneras distintas. Con un 0 cada minuto, "sin datos"
   pasa a significar UNA sola cosa —el worker está caído—, que es un problema
   distinto y ya vigilado.
2. **Nunca puede tumbar al worker.** `notify` existe para avisar de incidentes
   sísmicos. Una métrica de operación que reventase su bucle cambiaría un
   problema de inventario por uno de alertamiento; el trueque es inaceptable.
3. **Estrangulada.** El bucle de notify despierta cada 2 s. Publicar ahí sería
   ~43 000 llamadas al día por una cifra que CloudWatch agrega por minuto.
4. **La CUENTA se ejerce contra la DB real** (bloque final del archivo). Los tres
   puntos anteriores prueban el arnés con el contador inyectado; hasta el
   2026-08-05 eso era TODO lo que había, y el arnés puede estar impecable
   mientras la consulta no devuelve nada. Ahí vivía el fallo de verdad.
"""

from __future__ import annotations

import logging
from functools import partial

import psycopg
import pytest

from conftest import _dsn
from takab_api.db import pool
from takab_api.ops.metrics import GhostGauge, count_ghosts
from takab_api.schemas.fleet import SIN_ENLACE, derive_fleet_state
from takab_api.settings import Settings


class _FakeClock:
    """Reloj de mentira: el estrangulamiento se mide, no se espera dormido."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def avanza(self, s: float) -> None:
        self.t += s


class _FakeCW:
    def __init__(self, *, revienta: bool = False) -> None:
        self.puestas: list[dict] = []
        self._revienta = revienta

    def put_metric_data(self, **kw: object) -> None:
        if self._revienta:
            raise RuntimeError("CloudWatch dice que no")
        self.puestas.append(kw)


def _gauge(cw: _FakeCW, clock: _FakeClock, *, cuenta: int = 0, every_s: float = 60.0) -> GhostGauge:
    return GhostGauge(
        namespace="Takab/Test",
        every_s=every_s,
        client=cw,
        clock=clock,
        counter=lambda _conn: cuenta,
    )


def test_publica_el_CERO_para_que_la_alarma_no_viva_en_sin_datos() -> None:
    cw, clock = _FakeCW(), _FakeClock()
    _gauge(cw, clock, cuenta=0).maybe_publish(conn=object())

    assert len(cw.puestas) == 1, "no publicó nada con cero fantasmas"
    dato = cw.puestas[0]["MetricData"][0]
    assert dato["Value"] == 0
    assert dato["MetricName"] == "GhostGatewaysAlive"
    assert dato["Unit"] == "Count"


def test_publica_la_cuenta_real() -> None:
    cw, clock = _FakeCW(), _FakeClock()
    _gauge(cw, clock, cuenta=3).maybe_publish(conn=object())
    assert cw.puestas[0]["MetricData"][0]["Value"] == 3


def test_con_fantasmas_lo_DEJA_ESCRITO_y_con_cero_se_calla(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """La huella local del hallazgo, y su contrapartida: el cero no ensucia.

    El correo de CloudWatch llega a quien esté de guardia; el journal del EC2 es lo
    que lee quien ya entró por SSM a averiguar QUÉ pasó y CUÁNDO empezó. Si esta
    línea desaparece, ese rastro se pierde sin que nada se ponga rojo (mutación
    comprobada el 2026-08-05: borrarla dejaba los 25 tests en verde).

    La otra mitad es igual de deliberada: con cero fantasmas NO se registra nada.
    Una línea por minuto diciendo "0" es logging por intervalo —lo que la regla de
    oro 10 prohíbe— y ahoga el journal justo donde luego hay que buscar.
    """
    cw, clock = _FakeCW(), _FakeClock()

    with caplog.at_level(logging.WARNING):
        _gauge(cw, clock, cuenta=0).maybe_publish(conn=object())
    assert caplog.records == [], (
        "con CERO fantasmas dejó línea en el journal: a 1/min eso es logging por "
        f"intervalo (regla de oro 10). Registró: {[r.getMessage() for r in caplog.records]}"
    )

    caplog.clear()
    cw2, clock2 = _FakeCW(), _FakeClock()
    with caplog.at_level(logging.WARNING):
        _gauge(cw2, clock2, cuenta=3).maybe_publish(conn=object())

    avisos = [r for r in caplog.records if "3" in r.getMessage()]
    assert avisos, (
        "publicó la métrica pero no dejó rastro local de CUÁNTOS fantasmas había: "
        "quien entre por SSM tras el correo no puede reconstruir desde cuándo ni "
        f"cuántos. Registró: {[r.getMessage() for r in caplog.records]}"
    )


def test_estrangula_no_publica_en_cada_vuelta_del_bucle() -> None:
    cw, clock = _FakeCW(), _FakeClock()
    g = _gauge(cw, clock, cuenta=1, every_s=60.0)

    g.maybe_publish(conn=object())  # primera: publica
    # 29 vueltas de 2 s = 58 s. Se queda DEBAJO del intervalo a propósito: a los
    # 60 s exactos volver a publicar es la cadencia correcta, no una fuga (eso lo
    # cubre `test_pasado_el_intervalo_vuelve_a_publicar`). Aquí se mide lo otro:
    # que las vueltas intermedias del bucle no publiquen.
    for _ in range(29):
        clock.avanza(2.0)
        g.maybe_publish(conn=object())

    assert len(cw.puestas) == 1, (
        f"publicó {len(cw.puestas)} veces en 58 s con 30 vueltas de bucle: el "
        "estrangulador no está reteniendo, y a 2 s por vuelta esto serían "
        "~43 000 llamadas al día por una cifra que CloudWatch agrega por minuto"
    )


def test_pasado_el_intervalo_vuelve_a_publicar() -> None:
    cw, clock = _FakeCW(), _FakeClock()
    g = _gauge(cw, clock, cuenta=1, every_s=60.0)
    g.maybe_publish(conn=object())
    clock.avanza(61.0)
    g.maybe_publish(conn=object())
    assert len(cw.puestas) == 2


def test_un_fallo_de_cloudwatch_NO_tumba_al_worker(caplog: pytest.LogCaptureFixture) -> None:
    """`notify` avisa de sismos. Una métrica de ops no puede llevárselo por delante."""
    cw, clock = _FakeCW(revienta=True), _FakeClock()
    g = _gauge(cw, clock, cuenta=1)

    with caplog.at_level(logging.WARNING):
        g.maybe_publish(conn=object())  # no debe propagar

    assert any("fantasma" in r.message.lower() for r in caplog.records), (
        "se tragó el fallo SIN dejar rastro: un error silencioso aquí es peor "
        "que el propio fallo, porque la alarma parece sana y no lo está"
    )


def test_un_fallo_de_la_consulta_TAMPOCO_lo_tumba(caplog: pytest.LogCaptureFixture) -> None:
    """No propaga… y DEJA RASTRO. Esta es, literalmente, la rama que estuvo muda.

    Por aquí pasó el fallo del 2026-08-04/05: `count_ghosts` lanzaba `KeyError: 0`
    en cada llamada y este `except` lo absorbía. Que no propague es correcto
    —`notify` avisa de sismos y una métrica de inventario no puede llevárselo por
    delante—, pero entonces el `logger.warning` es la ÚNICA huella que queda del
    fallo, y el módulo se defiende por escrito diciendo que "un fallo se REGISTRA".
    Hasta el 2026-08-05 esa frase no la sostenía ningún test: borrar el warning
    dejaba los 25 en verde (mutación comprobada), o sea que el sistema podía volver
    a quedarse ciego EN SILENCIO sin que nada se pusiera rojo.

    Se exige también el `exc_info`: el mensaje es genérico a propósito, así que sin
    traza el que entra por SSM lee "no se pudo contar" y no puede saber si es un
    `KeyError: 0`, un permiso de `takab_ingest` o la DB caída. La traza es lo que
    convirtió aquel warning en diagnóstico.

    Y el nivel importa: se captura en WARNING, así que degradar esto a `info`/`debug`
    —que en un journal de producción es como borrarlo— también pone este test en rojo.
    """
    cw, clock = _FakeCW(), _FakeClock()

    def _explota(_conn: object) -> int:
        raise RuntimeError("la DB dice que no")

    g = GhostGauge(
        namespace="Takab/Test",
        every_s=60.0,
        client=cw,
        clock=clock,
        counter=_explota,
    )
    with caplog.at_level(logging.WARNING):
        g.maybe_publish(conn=object())  # no propaga
    assert cw.puestas == [], "publicó un valor inventado tras fallar la consulta"

    avisos = [r for r in caplog.records if "contar" in r.getMessage()]
    assert avisos, (
        "se tragó el fallo de la CUENTA sin registrar nada: es la rama exacta por "
        "la que la métrica no se publicó durante un día entero, y en silencio la "
        "alarma parece sana mientras deja de recibir datos. Warnings vistos: "
        f"{[r.getMessage() for r in caplog.records]}"
    )
    assert avisos[0].exc_info is not None, (
        "el warning va sin traza: 'no se pudo contar los gabinetes fantasma' no "
        "distingue un KeyError: 0 de un permiso revocado ni de la DB caída, y esa "
        "traza es lo único que hay para diagnosticar desde el EC2"
    )


def test_sin_cliente_no_hace_nada_y_no_revienta() -> None:
    """En local no hay CloudWatch: el worker tiene que correr igual."""
    clock = _FakeClock()
    g = GhostGauge(
        namespace="Takab/Test", every_s=60.0, client=None, clock=clock, counter=lambda _c: 5
    )
    g.maybe_publish(conn=object())  # y ya está: sin excepción


def test_el_fallo_de_una_vuelta_no_bloquea_la_siguiente() -> None:
    """Tras un error, el estrangulador no puede quedarse trabado para siempre."""
    cw, clock = _FakeCW(revienta=True), _FakeClock()
    g = _gauge(cw, clock, cuenta=1, every_s=60.0)
    g.maybe_publish(conn=object())
    clock.avanza(61.0)
    cw._revienta = False
    g.maybe_publish(conn=object())
    assert len(cw.puestas) == 1, "el estrangulador se quedó trabado tras el fallo"


# ---- el enganche al bucle de notify ----------------------------------------


def test_el_worker_arranca_INERTE_sin_la_metrica_habilitada() -> None:
    """Por defecto no se habla con AWS: en local no hay CloudWatch."""
    from takab_api.notify.worker import build_ghost_gauge
    from takab_api.settings import Settings

    gauge = build_ghost_gauge(Settings())
    gauge.maybe_publish(conn=object())  # no revienta, no publica, no pide credenciales


def test_sin_cliente_de_CLOUDWATCH_queda_inerte_pero_lo_DEJA_DICHO(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    """La tercera forma de quedarse mudo, y la más silenciosa de las tres.

    `build_ghost_gauge` (`notify/worker.py:40-49`) atrapa cualquier fallo al armar el
    cliente —credenciales ausentes, rol sin `PutMetricData`, boto3 roto— y sigue con
    `client=None`. A partir de ahí `maybe_publish` retorna en su primera línea: sin
    excepción, sin métrica y sin ruido. Desde CloudWatch se ve EXACTAMENTE igual que
    el worker caído o que la consulta lanzando: la alarma nace en `INSUFFICIENT_DATA`
    y se queda ahí — y como `insufficient_data_actions` solo dispara EN TRANSICIÓN,
    tampoco manda correo. Este warning es lo único que distingue el caso.

    Se cierra aquí porque es la misma rama de siempre en otro archivo: borrarlo dejaba
    la suite entera en verde (mutación comprobada el 2026-08-05).
    """
    import boto3

    from takab_api.notify.worker import build_ghost_gauge

    def _sin_credenciales(*_a: object, **_k: object) -> object:
        raise RuntimeError("no hay credenciales")

    monkeypatch.setattr(boto3, "client", _sin_credenciales)

    with caplog.at_level(logging.WARNING):
        gauge = build_ghost_gauge(Settings(ops_metrics_enabled=True))
        gauge.maybe_publish(conn=object())  # inerte: ni publica ni propaga

    assert any("CloudWatch" in r.getMessage() for r in caplog.records), (
        "se quedó sin cliente de CloudWatch SIN decir nada: el worker sigue "
        "notificando sismos (correcto) pero la métrica no sale nunca, y eso desde "
        "AWS es indistinguible de un worker muerto. Registró: "
        f"{[r.getMessage() for r in caplog.records]}"
    )


def test_la_metrica_NO_puede_tumbar_el_aviso_de_un_sismo(monkeypatch) -> None:
    """El contrato que de verdad importa de este enganche.

    `notify` existe para avisar de incidentes sísmicos. Si un fallo publicando
    una métrica de inventario propagara, cambiaríamos un problema administrativo
    por uno de alertamiento. Aquí se comprueba en el BUCLE real, no en la clase.
    """
    from takab_api.notify.worker import NotifyWorker
    from takab_api.settings import Settings

    pases: list[int] = []

    class _GaugeQueRevienta:
        def maybe_publish(self, *, conn: object) -> None:
            raise RuntimeError("CloudWatch caído")

    class _Conn:
        closed = False

        def execute(self, *_a: object, **_k: object) -> _Conn:
            return self

        # Filas DICT, como las devuelve `db/pool.py::connect` (`row_factory=dict_row`),
        # que es de donde sale la conexión real del worker. Este doble decía `(0,)`
        # y ese modelo mental equivocado es parte de por qué el `row[0]` de
        # `count_ghosts` sobrevivió a diez tests en verde.
        #
        # La clave es `ghosts` porque es el alias de `_COUNT_SQL`
        # (`SELECT count(*) AS ghosts`): este doble existe para ENSEÑAR el contrato,
        # así que devolver `{"count": 0}` —como hacía hasta el 2026-08-05— volvía a
        # dejar por escrito una forma de fila que la consulta real no produce.
        def fetchone(self) -> dict:
            return {"ghosts": 0}

        def fetchall(self) -> list:
            return []

        def rollback(self) -> None: ...
        def close(self) -> None: ...
        def notifies(self, **_k: object) -> list:
            return []

    worker = NotifyWorker(
        lambda: _Conn(),  # type: ignore[arg-type,return-value]
        Settings(),
        poll_s=0.0,
        providers={},
        ghost_gauge=_GaugeQueRevienta(),  # type: ignore[arg-type]
    )

    def _pass(*_a: object, **_k: object) -> None:
        pases.append(1)
        if len(pases) >= 3:
            worker.stop()

    monkeypatch.setattr("takab_api.notify.worker.run_notify_pass", _pass)
    worker.run()  # no debe propagar el fallo del gauge

    assert len(pases) >= 3, (
        f"el bucle solo dio {len(pases)} pases: un fallo de la métrica de "
        "inventario está frenando el despacho de notificaciones de sismo"
    )


# ---- la CONSULTA, contra la DB real -----------------------------------------
#
# Todo lo de arriba inyecta el contador (`counter=lambda _conn: n`): mide el
# ARNÉS, no la consulta. La auditoría del 2026-08-05 lo demostró sustituyendo
# `_COUNT_SQL` entera por `SELECT 0` — los diez tests siguieron en verde, porque
# ninguno la ejecutaba.
#
# Y lo que ese hueco escondía era peor que una SQL mal escrita: `count_ghosts`
# leía la fila POR POSICIÓN (`row[0]`) mientras la conexión REAL del worker sale
# de `db/pool.py::connect`, que la abre con `row_factory=dict_row`
# (`notify/__main__.py:31` → `worker.py:141` → `worker.py:101`; nadie cambia el
# row_factory por el camino). Un dict no se indexa por 0: `KeyError: 0` en CADA
# llamada, tragado por el `except` de `maybe_publish`, que retorna ANTES del
# `put_metric_data`. Resultado en producción: la métrica no se publicaba NUNCA
# —ni el cero, que era justo el mecanismo con el que esta alarma se defendía de
# `treat_missing_data`—, así que la alarma no podía sonar. Es el fallo del
# 2026-08-04 otra vez, esta vez en su vigilante.
#
# Por eso estos tests conectan por `pool.connect` y NO por `psycopg.connect` a
# secas: el `row_factory` no es un detalle de comodidad, es parte del contrato
# que se está probando.

# Prefijo f0: libre (sync usa 1/2/3/9/a/b/c, async 7, B1 8, fleet_admin 6,
# ghosts 5, retire_code 4, registry e9).
_TENANT = "f0000000-0000-0000-0000-000000000001"
_SITIO = "f0100000-0000-0000-0000-000000000001"
_SITIO_2 = "f0100000-0000-0000-0000-000000000002"
_GW = "f0200000-0000-0000-0000-00000000000a"
_GW_2 = "f0200000-0000-0000-0000-00000000000b"

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"

# El umbral se resuelve EXACTAMENTE como en `notify/worker.py::build_ghost_gauge`
# (`sin_enlace_min * 60`), no con un 300 escrito a mano: si mañana se mueve la
# frontera de SIN ENLACE, este test tiene que moverse con ella en vez de quedarse
# midiendo un umbral que ya no existe.
_ALIVE_S = Settings().sin_enlace_min * 60.0


def _limpia(conn: psycopg.Connection) -> None:
    # En orden de FK: salud → gabinetes → sitios → tenant.
    for tabla in ("device_health", "gateways", "sites", "tenants"):
        conn.execute(f"DELETE FROM {tabla} WHERE tenant_id = %s", (_TENANT,))


def _siembra(conn: psycopg.Connection) -> None:
    """Dos sitios vivos con un gabinete cada uno; todo activo y mudo de partida.

    Cada test fabrica desde aquí SU caso (retirar el gabinete, retirar el sitio,
    latir fresco o viejo), que es como se distinguen los cuatro escenarios que
    definen qué es un fantasma.
    """
    conn.execute(
        "INSERT INTO tenants (tenant_id, code, name, visibility) "
        "VALUES (%s, 'F1-GHOST', 'T-2.60.a metrica', 'private')",
        (_TENANT,),
    )
    for sid, code in ((_SITIO, "F1-TORRE"), (_SITIO_2, "F1-NAVE")):
        conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
            f"VALUES (%s, %s, %s, 'Sitio F1', {_GEOM})",
            (sid, _TENANT, code),
        )
    for gid, sid, serial in ((_GW, _SITIO, "SN-F1-A"), (_GW_2, _SITIO_2, "SN-F1-B")):
        conn.execute(
            "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
            "VALUES (%s, %s, %s, %s, %s)",
            (gid, _TENANT, sid, serial, f"thing-{serial}"),
        )


@pytest.fixture
def db() -> psycopg.Connection:
    """Conexión IGUAL que la del worker en producción: la que fabrica `pool.connect`.

    La siembra se COMMITEA y lo de cada test se queda en su transacción abierta
    (rollback al terminar). Efecto lateral buscado: dentro del test `now()` está
    congelado en el instante de su primera sentencia, así que la edad de un
    latido es EXACTA y el límite del umbral se puede tocar con el dedo.
    """
    conn = pool.connect(_dsn())
    try:
        _limpia(conn)
        _siembra(conn)
        conn.commit()
        yield conn
    finally:
        conn.rollback()
        _limpia(conn)
        conn.commit()
        conn.close()


def _latido(
    conn: psycopg.Connection, gateway_id: str, *, hace_s: float, power: str = "line"
) -> None:
    """Un heartbeat a medida, para poder fabricar vivos y mudos."""
    conn.execute(
        "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, mqtt_rtt_ms, power_status) "
        "VALUES (now() - make_interval(secs => %s), %s, %s, 'heartbeat', 40, %s)",
        (hace_s, _TENANT, gateway_id, power),
    )


def _retira_gateway(conn: psycopg.Connection, gateway_id: str) -> None:
    conn.execute("UPDATE gateways SET status = 'retired' WHERE gateway_id = %s", (gateway_id,))


def _retira_sitio(conn: psycopg.Connection, site_id: str) -> None:
    conn.execute("UPDATE sites SET status = 'retired' WHERE site_id = %s", (site_id,))


def _cuenta(conn: psycopg.Connection) -> int:
    return count_ghosts(conn, alive_s=_ALIVE_S)


# La cifra es de PLATAFORMA: `_COUNT_SQL` no filtra por tenant a propósito
# (metrics.py lo documenta: el worker conecta con BYPASSRLS y la cifra por tenant
# ya la da la consola). Por eso se mide el DELTA y no el absoluto: lo que este
# archivo siembra no puede depender de que la base esté vacía. Un delta también
# muere con la SQL mutada a `SELECT 0` — antes y después darían 0 y el delta 0.


def test_el_retirado_que_SIGUE_LATIENDO_se_cuenta(db: psycopg.Connection) -> None:
    """Caso 1: el fantasma canónico. Sin esto la métrica no vigila nada."""
    base = _cuenta(db)
    _latido(db, _GW, hace_s=5)
    _retira_gateway(db, _GW)

    assert _cuenta(db) - base == 1, (
        "un gabinete RETIRADO que latió hace 5 s no se contó: es exactamente el "
        "estado que la alarma existe para delatar"
    )


def test_el_retirado_y_MUDO_no_se_cuenta(db: psycopg.Connection) -> None:
    """Caso 2: el filtro de T-2.35, intacto.

    Hardware desmontado de verdad. Contarlo convertiría la alarma en un contador
    de inventario histórico que ya no se apaga nunca — y una alarma que siempre
    suena deja de leerse.
    """
    base = _cuenta(db)
    _latido(db, _GW, hace_s=3600)  # una hora callado
    _retira_gateway(db, _GW)

    assert _cuenta(db) - base == 0, "un gabinete retirado y CALLADO no es un fantasma"


def test_el_retirado_que_NUNCA_latio_no_se_cuenta(db: psycopg.Connection) -> None:
    """Sin una sola fila en `device_health` no hay nada que delatar.

    El LATERAL devuelve `ts` NULL y la comparación es NULL (ni true ni false):
    esta es la prueba de que ese NULL no se cuela como verdadero.
    """
    base = _cuenta(db)
    _retira_gateway(db, _GW)

    assert _cuenta(db) - base == 0


def test_el_gabinete_ACTIVO_que_late_no_se_cuenta(db: psycopg.Connection) -> None:
    """Caso 3: la flota sana. Si la bandera se enciende con todo el mundo, no informa."""
    base = _cuenta(db)
    _latido(db, _GW, hace_s=5)

    assert _cuenta(db) - base == 0, (
        "un gabinete en servicio y latiendo se contó como fantasma: con la flota "
        "entera dentro, la alarma quedaría en ALARMA para siempre"
    )


def test_el_SITIO_retirado_con_el_gabinete_VIVO_se_cuenta(db: psycopg.Connection) -> None:
    """Caso 4 — el REAL del 2026-08-04, y el que ninguna prueba miraba.

    El retiro no llegó por el gabinete: se retiró el SITIO el 03-08 y la
    migración 0024 heredó el retiro al gabinete mientras el Pi seguía publicando
    latidos cada 60 s. Se descubrió porque un operador preguntó por su estación,
    no porque el sistema dijera nada. Si la SQL mirara solo `gateways.status`,
    este caso —el único que ha ocurrido de verdad— pasaría invisible otra vez.
    """
    base = _cuenta(db)
    _latido(db, _GW, hace_s=5)
    _retira_sitio(db, _SITIO)

    assert _cuenta(db) - base == 1, (
        "el gabinete VIVO de un sitio retirado no se contó: es el fallo del "
        "2026-08-04 literal, con el retiro heredado del sitio"
    )


def test_un_fantasma_con_MIL_latidos_cuenta_UNA_vez(db: psycopg.Connection) -> None:
    """El LATERAL colapsa el historial a un solo `max(ts)`.

    Con un JOIN plano a `device_health` la cuenta se multiplicaría por el número
    de heartbeats — y con 1/min, un fantasma de un día valdría 1440. La alarma
    seguiría "funcionando" (>0), pero el número dejaría de significar gabinetes
    y nadie podría dimensionar el problema al leer el correo.
    """
    base = _cuenta(db)
    for hace in (5.0, 65.0, 125.0, 4000.0):
        _latido(db, _GW, hace_s=hace)
    _retira_gateway(db, _GW)

    assert _cuenta(db) - base == 1, "la cuenta es de GABINETES, no de latidos"


def test_dos_fantasmas_cuentan_DOS(db: psycopg.Connection) -> None:
    """El valor tiene que ser la magnitud del problema, no un booleano disfrazado."""
    base = _cuenta(db)
    _latido(db, _GW, hace_s=5)
    _latido(db, _GW_2, hace_s=5)
    _retira_gateway(db, _GW)
    _retira_sitio(db, _SITIO_2)  # el otro, por herencia del sitio

    assert _cuenta(db) - base == 2


def test_en_el_LIMITE_EXACTO_no_se_cuenta_porque_la_consola_tampoco_lo_pinta(
    db: psycopg.Connection,
) -> None:
    """Trampa nombrada: el borde del umbral tiene DOS operadores en el repo.

    - `queries/fleet.py:82` (lo que el operador VE en la vista por defecto) usa
      `h.ts > now() - alive_s`: estricto. A `alive_s` exactos, la fila no se pinta.
    - `schemas/fleet.py:50` (`derive_fleet_state`) usa `age_s > sin_enlace_s`: no
      estricto. A `alive_s` exactos diría "vivo".

    `_COUNT_SQL` sigue al FILTRO, no a la bandera, y eso es lo correcto: la
    métrica debe contar lo mismo que un humano puede ir a mirar en la consola.
    Contar un fantasma invisible sería mandar a alguien a buscar una tarjeta que
    no está en pantalla. Este test existe para que nadie "alinee" la SQL con
    `derive_fleet_state` creyendo que arregla una incoherencia.

    MATIZ medido el 2026-08-05, para que este docstring no mienta: "la consola
    tampoco lo pinta" vale para la vista por DEFECTO. Con el conmutador «ver
    retirados» activo la fila sí sale —`include_retired` cortocircuita el `OR` del
    `WHERE` (`queries/fleet.py:71`), así que el operador estricto ni se evalúa— y
    ahí el rótulo de fantasma lo pone `routers/fleet.py:270`, que se deriva del
    operador NO estricto. O sea que en el borde exacto la métrica dice 0 y esa
    vista dice fantasma. La divergencia dura UN microsegundo (la resolución de
    `timestamptz`) contra un heartbeat cada 60 s: operativamente, nada. Se deja
    escrita porque el borde exacto es inalcanzable en producción y aquí solo es
    determinista porque `now()` está congelado en la transacción del test.
    """
    base = _cuenta(db)
    _latido(db, _GW, hace_s=_ALIVE_S)  # ni un microsegundo de margen
    _retira_gateway(db, _GW)

    assert _cuenta(db) - base == 0, (
        "en el límite exacto la métrica contó un gabinete que la consola NO pinta "
        "en su vista por defecto: la alarma mandaría a buscar una tarjeta invisible"
    )


@pytest.mark.parametrize(
    ("hace_s", "power", "es_fantasma"),
    [
        (5.0, "line", True),  # recién latió
        (_ALIVE_S - 1.0, "line", True),  # vivo por un segundo
        (_ALIVE_S + 1.0, "line", False),  # mudo por un segundo
        (3600.0, "line", False),  # una hora callado: desmontado
        # DEGRADADO también es "vivo": el gabinete habla, solo que mal. Si la SQL
        # se estrechara a los OPERATIVO, un fantasma en batería —el más probable
        # de todos, porque nadie fue a desenchufarlo— dejaría de contarse.
        (5.0, "battery", True),
    ],
)
def test_la_metrica_y_la_consola_llaman_fantasma_a_LO_MISMO(
    db: psycopg.Connection, hace_s: float, power: str, es_fantasma: bool
) -> None:
    """Cruce de las dos definiciones de fantasma que existen en el producto.

    La consola lo decide en Python (`routers/fleet.py`: retirado él o su sitio, y
    `derived_state != SIN ENLACE`); la métrica lo decide en SQL. Son dos
    implementaciones de la misma frase, en dos lenguajes, en dos archivos: la
    única defensa contra que diverjan es compararlas. Aquí el veredicto de la
    consola NO se copia — se calcula con `derive_fleet_state`, la función real.
    """
    base = _cuenta(db)
    _latido(db, _GW, hace_s=hace_s, power=power)
    _retira_gateway(db, _GW)

    metrica = (_cuenta(db) - base) == 1

    # Las mismas entradas que el router pasa a `derive_fleet_state`, leídas con
    # la misma forma que `queries/fleet.py::_LIST` (último heartbeat por LATERAL).
    fila = db.execute(
        """
        SELECT g.status, s.status AS site_status,
               EXTRACT(EPOCH FROM (now() - h.ts))::float8 AS age_s,
               h.power_status,
               h.battery_pct::float8    AS battery_pct,
               h.cert_days_remaining,
               h.mqtt_rtt_ms::float8    AS mqtt_rtt_ms,
               h.seedlink_lag_s::float8 AS seedlink_lag_s,
               h.ntp_offset_ms::float8  AS ntp_offset_ms
        FROM gateways g
        JOIN sites s ON s.site_id = g.site_id
        LEFT JOIN LATERAL (
            SELECT dh.ts, dh.power_status, dh.battery_pct, dh.cert_days_remaining,
                   dh.mqtt_rtt_ms, dh.seedlink_lag_s, dh.ntp_offset_ms
            FROM device_health dh
            WHERE dh.gateway_id = g.gateway_id
            ORDER BY dh.ts DESC LIMIT 1
        ) h ON true
        WHERE g.gateway_id = %s
        """,
        (_GW,),
    ).fetchone()
    assert fila is not None

    s = Settings()
    estado = derive_fleet_state(
        age_s=fila["age_s"],
        power_status=fila["power_status"],
        battery_pct=fila["battery_pct"],
        cert_days_remaining=fila["cert_days_remaining"],
        mqtt_rtt_ms=fila["mqtt_rtt_ms"],
        seedlink_lag_s=fila["seedlink_lag_s"],
        ntp_offset_ms=fila["ntp_offset_ms"],
        sin_enlace_s=s.sin_enlace_min * 60.0,
        battery_min_pct=s.fleet_battery_min_pct,
        cert_min_days=s.fleet_cert_min_days,
        mqtt_rtt_max_ms=s.fleet_mqtt_rtt_max_ms,
        seedlink_lag_max_s=s.fleet_seedlink_lag_max_s,
        ntp_offset_max_ms=s.fleet_ntp_offset_max_ms,
    )
    consola = (
        fila["status"] == "retired" or fila["site_status"] == "retired"
    ) and estado != SIN_ENLACE

    assert metrica == consola == es_fantasma, (
        f"con un latido de hace {hace_s} s (power={power}) la métrica dice "
        f"fantasma={metrica} y la consola dice fantasma={consola} "
        f"(derived_state={estado!r}): dos definiciones de lo mismo que ya "
        "divergieron. La alarma y la pantalla contarían cosas distintas."
    )


def test_el_ROL_DE_PRODUCCION_ve_la_misma_cuenta(db: psycopg.Connection) -> None:
    """Local cuenta como superusuario; el worker, como `takab_ingest`.

    `_COUNT_SQL` no filtra por tenant a propósito —es una señal de plataforma— y
    eso SOLO funciona porque `takab_ingest` es el único rol con BYPASSRLS
    (db/schema.sql:49) y tiene SELECT sobre las tres tablas. Si mañana se le
    quitara cualquiera de las dos cosas, la cuenta sería 0 EN LA NUBE y verde en
    local: la misma trampa que ya nos costó una migración (verde local puede ser
    imposible en nube).
    """
    _latido(db, _GW, hace_s=5)
    _retira_gateway(db, _GW)
    como_superusuario = _cuenta(db)
    assert como_superusuario >= 1

    db.execute("SET LOCAL ROLE takab_ingest")
    try:
        assert _cuenta(db) == como_superusuario, (
            "el rol REAL del worker cuenta distinto que el superusuario: en la "
            "nube la métrica publicaría ceros con fantasmas latiendo"
        )
    finally:
        db.execute("RESET ROLE")


def test_el_gauge_PUBLICA_con_la_conexion_REAL_del_worker(
    db: psycopg.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    """El fallo del 2026-08-05 de punta a punta, con el cableado del worker.

    Se arma el medidor con el MISMO contador que `build_ghost_gauge`
    (`partial(count_ghosts, alive_s=…)`, worker.py:54) y se le entrega la
    conexión que fabrica `pool.connect`, que es la que el bucle le pasa
    (worker.py:101). Con la fila leída por posición esto no publica NADA:
    `KeyError: 0` dentro del `try`, `logger.warning`, `return` — y la alarma de
    Terraform, esperando datos que no llegan.
    """
    _latido(db, _GW, hace_s=5)
    _retira_gateway(db, _GW)

    cw, clock = _FakeCW(), _FakeClock()
    gauge = GhostGauge(
        namespace="Takab/Test",
        every_s=60.0,
        client=cw,
        clock=clock,
        counter=partial(count_ghosts, alive_s=_ALIVE_S),
    )
    with caplog.at_level(logging.WARNING):
        gauge.maybe_publish(conn=db)

    assert cw.puestas, (
        "el medidor no publicó NADA con la conexión real del worker "
        f"(row_factory=dict_row). Warnings: {[r.message for r in caplog.records]}"
    )
    assert cw.puestas[0]["MetricData"][0]["Value"] >= 1
