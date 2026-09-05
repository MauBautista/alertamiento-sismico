"""T-5.24 · La métrica que delata un reloj a la deriva, sin que nadie mire.

El desfase de reloj se medía de verdad (el edge lo publica en cada latido), se
persistía (`device_health.ntp_offset_ms`), y hasta degradaba el estado del sitio
en la consola. Y aun así solo se veía si alguien estaba MIRANDO la pantalla:
ninguna de las 13 alarmas de `modules/observability` era de reloj.

Importa porque **sin hora confiable ninguna evidencia sirve**. El sello de un
check-in, de un dictamen y de un acuse salen todos de ese reloj, y un dictamen
que dice que se firmó a las 14:02 cuando fue a las 14:05 no ordena los hechos:
los desordena. Es un fallo silencioso por construcción — el gabinete sigue
latiendo, la consola sigue verde, y lo único que cambia es que las horas mienten.

Los tres contratos que fijan estos tests, y por qué cada uno:

1. **El cero se publica.** Igual que en `test_ghost_gauge.py`: si la métrica solo
   apareciera cuando alguien va a la deriva, la alarma viviría en
   INSUFFICIENT_DATA y todo dependería de `treat_missing_data`, que ya nos falló
   de cuatro maneras distintas. Con un 0 cada minuto, "sin datos" pasa a
   significar UNA sola cosa: el worker que publica está muerto — que es un fallo
   que `gateway_offline` NO ve, porque los gabinetes siguen latiendo contra el
   worker de ingesta, que es otro proceso.
2. **La consulta se ejecuta contra la DB real.** La lección del 2026-08-05 en
   este mismo módulo: diez tests en verde sobre un `counter` inyectado no tocaban
   la SQL, y la SQL era la que estaba rota (`row[0]` sobre un `dict_row`).
3. **`abs()`, `MAX` y el gabinete VIVO.** Las tres decisiones que hacen que la
   cifra signifique algo: un reloj adelantado miente igual que uno atrasado; el
   peor de la flota no puede desaparecer en un promedio; y un gabinete apagado
   hace meses no puede dejar la alarma sonando para siempre.
"""

from __future__ import annotations

import logging

import psycopg
import pytest

from conftest import _dsn
from takab_api.db import pool
from takab_api.ops.metrics import (
    METRIC_NAME_CLOCK_DRIFT,
    GhostGauge,
    max_clock_drift_ms,
)
from takab_api.settings import Settings

# ---- el ARNÉS: qué se publica ------------------------------------------------


class _FakeCW:
    def __init__(self) -> None:
        self.puestas: list[dict] = []

    def put_metric_data(self, **kw: object) -> None:
        self.puestas.append(kw)


def _dato_de_reloj(cw: _FakeCW) -> dict | None:
    for puesta in cw.puestas:
        for dato in puesta["MetricData"]:
            if dato["MetricName"] == METRIC_NAME_CLOCK_DRIFT:
                return dato
    return None


def _gauge(cw: _FakeCW, *, desfase: float | None) -> GhostGauge:
    return GhostGauge(
        namespace="Takab/Test",
        every_s=60.0,
        client=cw,
        clock=lambda: 1000.0,
        counter=lambda _c: 0,
        drift_gauge=None if desfase is None else (lambda _c: desfase),
    )


def test_publica_el_CERO_para_que_la_ausencia_signifique_UNA_cosa() -> None:
    """Sin cero publicado, `breaching` sería exactamente el fallo de `iot_rule_errors`.

    Aquella alarma pasó **14 días clavada en ALARM** —o sea MUDA, porque SNS solo
    notifica transiciones— precisamente porque su filtro no publicaba el cero y su
    `treat_missing_data` era `breaching`. Aquí el cero SÍ sale, y por eso
    `breaching` es correcto: no queda ninguna otra lectura para el silencio.
    """
    cw = _FakeCW()
    _gauge(cw, desfase=0.0).maybe_publish(conn=object())

    dato = _dato_de_reloj(cw)
    assert dato is not None, (
        "con CERO desfase no publicó nada: la alarma nacería en INSUFFICIENT_DATA "
        "y su `breaching` alarmaría sobre la flota SANA"
    )
    assert dato["Value"] == 0.0
    assert dato["Unit"] == "Milliseconds", (
        "la unidad miente: CloudWatch la muestra en los correos y en las gráficas, "
        f"y quien lea '{dato['Unit']}' no sabrá si 150 es mucho o poco"
    )


def test_publica_el_desfase_real() -> None:
    cw = _FakeCW()
    _gauge(cw, desfase=430.5).maybe_publish(conn=object())
    assert _dato_de_reloj(cw)["Value"] == 430.5  # type: ignore[index]


def test_viaja_en_la_MISMA_publicacion_que_las_otras_dos() -> None:
    """Una sola llamada a CloudWatch: misma fotografía y mismo periodo.

    No es solo ahorro. Las tres cifras se leen juntas cuando alguien reconstruye
    un incidente, y tres llamadas independientes pueden dejar una fuera sin que
    nada lo diga.
    """
    cw = _FakeCW()
    g = GhostGauge(
        namespace="Takab/Test",
        every_s=60.0,
        client=cw,
        clock=lambda: 1000.0,
        counter=lambda _c: 0,
        total_counter=lambda _c: 0,
        drift_gauge=lambda _c: 12.0,
    )
    g.maybe_publish(conn=object())

    assert len(cw.puestas) == 1, f"partió la fotografía en {len(cw.puestas)} llamadas"
    nombres = [d["MetricName"] for d in cw.puestas[0]["MetricData"]]
    assert METRIC_NAME_CLOCK_DRIFT in nombres, f"el reloj no viajó: {nombres}"


def test_si_la_DB_falla_NO_sale_ninguna_de_las_tres(caplog: pytest.LogCaptureFixture) -> None:
    """Publicar dos de tres se lee como flota sana, que es la mentira a evitar.

    Es el mismo argumento que ya defendía el par `fantasmas`/`total`: un hueco
    donde va una cifra no se ve; un 0 junto a las otras dos, sí.
    """
    cw = _FakeCW()

    def _explota(_conn: object) -> float:
        raise RuntimeError("la DB dice que no")

    g = GhostGauge(
        namespace="Takab/Test",
        every_s=60.0,
        client=cw,
        clock=lambda: 1000.0,
        counter=lambda _c: 0,
        drift_gauge=_explota,
    )
    with caplog.at_level(logging.WARNING):
        g.maybe_publish(conn=object())  # no propaga: el worker avisa de sismos

    assert cw.puestas == [], "publicó las otras cifras tras fallar la del reloj"
    assert caplog.records, "se tragó el fallo SIN dejar rastro en el journal"


def test_el_worker_real_la_cablea() -> None:
    """El enganche, no la clase: sin esto la métrica existe y nadie la publica.

    Es la forma de quedarse mudo que más veces ha pasado en este repo — código
    correcto que nadie invoca (el worker de backfill del CCTV, sin ir más lejos).
    """
    from takab_api.notify.worker import build_ghost_gauge

    cw = _FakeCW()
    gauge = build_ghost_gauge(Settings())
    gauge._client = cw  # type: ignore[attr-defined]  # en local no hay CloudWatch

    class _Conn:
        def execute(self, *_a: object, **_k: object) -> _Conn:
            return self

        def fetchone(self) -> dict:
            # Las tres consultas con la forma de fila que devuelve `dict_row`.
            return {"ghosts": 0, "retired_alive": 0, "drift_ms": 0.0}

    gauge.maybe_publish(conn=_Conn())

    assert _dato_de_reloj(cw) is not None, (
        "`build_ghost_gauge` no cableó el desfase de reloj: la consulta existe, "
        "la alarma existe, y nadie publica el dato que las une"
    )


# ---- la CONSULTA, contra la DB real -----------------------------------------
#
# Prefijo f2: libre (f0 lo usa `test_ghost_gauge.py`).

_TENANT = "f2000000-0000-0000-0000-000000000001"
_SITIO = "f2100000-0000-0000-0000-000000000001"
_GW = "f2200000-0000-0000-0000-00000000000a"
_GW_2 = "f2200000-0000-0000-0000-00000000000b"

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"

# El mismo umbral de "vivo" que resuelve `notify/worker.py::build_ghost_gauge`,
# no un 300 escrito a mano.
_ALIVE_S = Settings().sin_enlace_min * 60.0

# Un valor deliberadamente ENORME (medio minuto). No es realista y da igual: lo
# que se mide es si la fila entra en el MAX o no, y con un número que domina
# cualquier residuo de otros tests la aserción se lee sin ambigüedad.
_ENORME = 30_000.0


def _limpia(conn: psycopg.Connection) -> None:
    for tabla in ("device_health", "gateways", "sites", "tenants"):
        conn.execute(f"DELETE FROM {tabla} WHERE tenant_id = %s", (_TENANT,))


@pytest.fixture
def db() -> psycopg.Connection:
    """Conexión IGUAL que la del worker: la que fabrica `pool.connect` (`dict_row`).

    No es comodidad: `count_ghosts` leía la fila por posición sobre un `dict_row`
    y eso dejó la métrica sin publicar UN DÍA ENTERO, en silencio. El
    `row_factory` es parte del contrato que se prueba aquí.
    """
    conn = pool.connect(_dsn())
    try:
        _limpia(conn)
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name, visibility) "
            "VALUES (%s, 'F2-RELOJ', 'T-5.24 reloj', 'private')",
            (_TENANT,),
        )
        conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
            f"VALUES (%s, %s, 'F2-TORRE', 'Sitio F2', {_GEOM})",
            (_SITIO, _TENANT),
        )
        for gid, serial in ((_GW, "SN-F2-A"), (_GW_2, "SN-F2-B")):
            conn.execute(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                "VALUES (%s, %s, %s, %s, %s)",
                (gid, _TENANT, _SITIO, serial, f"thing-{serial}"),
            )
        conn.commit()
        yield conn
    finally:
        conn.rollback()
        _limpia(conn)
        conn.commit()
        conn.close()


def _latido(
    conn: psycopg.Connection,
    gateway_id: str,
    *,
    hace_s: float,
    desfase_ms: float | None,
) -> None:
    conn.execute(
        "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, mqtt_rtt_ms, ntp_offset_ms) "
        "VALUES (now() - make_interval(secs => %s), %s, %s, 'heartbeat', 40, %s)",
        (hace_s, _TENANT, gateway_id, desfase_ms),
    )


def _desfase(conn: psycopg.Connection) -> float:
    return max_clock_drift_ms(conn, alive_s=_ALIVE_S)


# La cifra es de PLATAFORMA (el worker conecta con BYPASSRLS), así que no se
# afirma el absoluto: se afirma contra el `base` medido justo antes. Un `MAX` no
# admite deltas, pero sí `max(base, lo_mio)`, que es exacto en las dos
# direcciones y muere igual si alguien muta la SQL a `SELECT 0`.


def test_el_reloj_a_la_DERIVA_se_publica(db: psycopg.Connection) -> None:
    base = _desfase(db)
    _latido(db, _GW, hace_s=5, desfase_ms=_ENORME)

    assert _desfase(db) == max(base, _ENORME), (
        "un gabinete VIVO con el reloj medio minuto fuera no llegó a la métrica: "
        "es exactamente el estado que la alarma existe para delatar"
    )


def test_el_reloj_ADELANTADO_cuenta_IGUAL(db: psycopg.Connection) -> None:
    """`abs()`. Un reloj que va por delante desordena los hechos igual de bien.

    Sin el valor absoluto, la mitad de los desfases posibles —los negativos— no
    solo no alarman: **rebajan** el MAX de la flota, así que un gabinete muy
    adelantado podría enmascarar a otro atrasado.
    """
    base = _desfase(db)
    _latido(db, _GW, hace_s=5, desfase_ms=-_ENORME)

    assert _desfase(db) == max(base, _ENORME), (
        "un reloj ADELANTADO 30 s se contó como sano: sin `abs()` la alarma solo "
        "vigila la mitad de las formas de tener mal la hora"
    )


def test_el_PEOR_de_la_flota_no_se_diluye(db: psycopg.Connection) -> None:
    """`MAX`, no promedio. Un gabinete a la deriva entre veinte sanos desaparece de una media."""
    base = _desfase(db)
    _latido(db, _GW, hace_s=5, desfase_ms=1.0)
    _latido(db, _GW_2, hace_s=5, desfase_ms=_ENORME)

    assert _desfase(db) == max(base, _ENORME), (
        "el gabinete a la deriva se diluyó entre los sanos: la alarma tiene que "
        "sonar por el PEOR de la flota, no por su promedio"
    )


def test_el_gabinete_MUDO_no_deja_la_alarma_sonando_para_siempre(db: psycopg.Connection) -> None:
    """Un latido viejo no cuenta.

    Es el mismo argumento del filtro de T-2.35: sin esto, un gabinete desmontado
    con el reloj mal deja la alarma encendida para siempre, y una alarma que
    siempre suena deja de leerse. Del silencio de ese gabinete ya habla
    `gateway_offline`.
    """
    base = _desfase(db)
    _latido(db, _GW, hace_s=_ALIVE_S + 60, desfase_ms=_ENORME)

    assert _desfase(db) == base, (
        "contó el reloj de un gabinete que lleva sin latir más que el umbral de "
        "SIN ENLACE: quien pagina por ese silencio es `gateway_offline`"
    )


def test_solo_cuenta_el_ULTIMO_latido_de_cada_gabinete(db: psycopg.Connection) -> None:
    """Un desfase que YA SE CORRIGIÓ no puede seguir alarmando.

    `device_health` es una serie: el gabinete que se resincronizó hace un minuto
    tiene en su historia las horas en que estuvo mal. Mirar la serie entera en vez
    del último latido convierte la alarma en un archivo histórico que no se apaga.
    """
    base = _desfase(db)
    _latido(db, _GW, hace_s=120, desfase_ms=_ENORME)  # estuvo mal…
    _latido(db, _GW, hace_s=5, desfase_ms=2.0)  # …y se corrigió

    # La cifra que se espera es la CORREGIDA (2 ms), no un cero: el gabinete sí
    # tiene un desfase medido, solo que ya es sano. Lo que no puede sobrevivir es
    # el de hace dos minutos.
    assert _desfase(db) == max(base, 2.0), (
        "siguió alarmando por un desfase ya corregido: la consulta está mirando "
        "la serie histórica en vez del ÚLTIMO latido de cada gabinete"
    )


def test_el_RETIRADO_no_cuenta(db: psycopg.Connection) -> None:
    """De los retirados que siguen latiendo ya habla `GhostGatewaysAlive`.

    Cada alarma dice UNA cosa: el reloj de un gabinete dado de baja no es un
    problema de hora, es un problema de inventario, y tiene su propio vigilante.
    """
    base = _desfase(db)
    _latido(db, _GW, hace_s=5, desfase_ms=_ENORME)
    db.execute("UPDATE gateways SET status = 'retired' WHERE gateway_id = %s", (_GW,))

    assert _desfase(db) == base, (
        "el reloj de un gabinete RETIRADO alarmaría como si operara: de ése habla "
        "la métrica de fantasmas, y dos alarmas por el mismo hecho enseñan a leer "
        "los correos por encima"
    )


def test_SIN_DATO_de_reloj_no_es_lo_mismo_que_reloj_en_hora(db: psycopg.Connection) -> None:
    """`NULL` se excluye; no se cuenta como 0.

    No saber la hora no es tenerla bien. De esa ausencia habla el `S/D` del panel
    del gabinete; contarla como un cero aquí sería fabricar la buena noticia de
    que el reloj está sincronizado cuando lo que pasa es que no hay medición.
    """
    base = _desfase(db)
    _latido(db, _GW, hace_s=5, desfase_ms=None)

    assert _desfase(db) == base, "un latido SIN medición de reloj movió la métrica"


def test_con_la_flota_EN_HORA_devuelve_CERO_no_nulo(db: psycopg.Connection) -> None:
    """El cero de la consulta, que es lo que hace publicable el cero de la métrica.

    Si aquí saliera `None`, `maybe_publish` no incluiría el dato y la alarma
    volvería a INSUFFICIENT_DATA con la flota perfectamente sana — el fallo de
    `iot_rule_errors`, otra vez.
    """
    valor = _desfase(db)  # la flota sembrada aún no ha latido

    assert isinstance(valor, float), f"la consulta devolvió {valor!r}, no un float"
    assert valor >= 0.0
