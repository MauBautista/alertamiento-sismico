"""[T-2.70.a · B1] Un gabinete SIN DUEÑO DE PINES tiene que distinguirse de uno sano.

D3 sacó el dueño de los pines a `takab-gpio`. Con `TAKAB_EDGE_GPIO_OWNER=gpio` y
ese proceso caído, el gabinete **no tiene sirena, ni cierre de gas, ni retorno de
ascensores, ni retenedores** — y `takab-edge` sigue latiendo perfectamente. El
latido salía idéntico al de un gabinete sano salvo por `relays: []`, que en la
nube era indistinguible de «el módulo de relés está detenido»:

* ninguna de las 8 alarmas de observabilidad mira los relés;
* `gateway_offline` NO dispara, porque el que late está vivo;
* el único aviso es un `log.critical` en el journal del Pi.

El SOC veía verde un edificio sin ninguna de sus cuatro protecciones.

**El criterio de este archivo** (el test cabecera es
`test_un_gabinete_sin_dueno_de_pines_no_se_confunde_con_uno_sano`): dos
instantáneas —una con dueño, otra sin nadie al mando— **no pueden confundirse**
después de pasar por el ingest. Lo demás es la disciplina alrededor: el hecho
distinto («módulo detenido»), la ausencia de opinión del firmware viejo, la
basura que no opina, y la idempotencia de la regla de oro 3.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from conftest import use
from takab_api.contracts.meta import Meta
from takab_api.ingest.handlers import (
    RELAYS_REPORTED,
    RELAYS_STOPPED,
    RELAYS_UNREADABLE,
    GatewayCtx,
    SensorRef,
    handle_health_snapshot,
)

# Prefijo b1 (= bloqueante B1): no colisiona con la familia `d…` del seed dev ni
# con los prefijos de las suites de flota (4*/5*/6*/69*).
TENANT = "b1000000-0000-0000-0000-000000000001"
SITE = "b1100000-0000-0000-0000-000000000001"
GW = "b1200000-0000-0000-0000-000000000001"
SENSOR = "b1300000-0000-0000-0000-000000000001"

TS_IOT = datetime(2026, 8, 8, 10, 0, 5, tzinfo=UTC)

_RELE = {
    "channel": "siren",
    "energized": False,
    "activated": False,
    "fail_safe": "NO",
}


@pytest.fixture
def fleet(conn: psycopg.Connection) -> psycopg.Connection:
    """Un tenant/sitio/gabinete propios. La conexión revierte al terminar."""
    conn.execute("RESET ROLE")
    conn.execute(
        "INSERT INTO tenants (tenant_id, code, name) VALUES (%s, 'b1-relays', 'B1') "
        "ON CONFLICT DO NOTHING",
        (TENANT,),
    )
    conn.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s, %s, 'b1-site', 'Sitio B1', "
        "ST_SetSRID(ST_MakePoint(-99.13, 19.43), 4326)::geography) ON CONFLICT DO NOTHING",
        (SITE, TENANT),
    )
    conn.execute(
        "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) VALUES "
        "(%s, %s, %s, 'gw-b1-0001', 'gw-b1-0001') ON CONFLICT DO NOTHING",
        (GW, TENANT, SITE),
    )
    conn.execute(
        "INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, model, serial) "
        "VALUES (%s, %s, %s, %s, 'structural', 'RS4D', 'B1F74') ON CONFLICT DO NOTHING",
        (SENSOR, TENANT, SITE, GW),
    )
    use(conn, "takab_ingest")  # el rol real del worker
    return conn


@pytest.fixture
def ctx() -> GatewayCtx:
    return GatewayCtx(
        gateway_id=uuid.UUID(GW),
        gateway_serial="gw-b1-0001",
        iot_thing="gw-b1-0001",
        tenant_id=uuid.UUID(TENANT),
        tenant_code="b1-relays",
        site_id=uuid.UUID(SITE),
        site_code="b1-site",
        sensors={
            "B1F74": SensorRef(
                sensor_id=uuid.UUID(SENSOR), site_id=uuid.UUID(SITE), site_code="b1-site"
            )
        },
    )


@pytest.fixture
def meta() -> Meta:
    return Meta(principal="gw-b1-0001", topic="takab/health", ts_iot=TS_IOT)


def _health(ts: str, **over: object) -> dict:
    """Latido con el resto de campos SANOS: lo único que varía son los relés."""
    base: dict = {
        "gateway_id": "gw-b1-0001",
        "captured_at": ts,
        "ntp_offset_s": 0.001,
        "seedlink_lag_s": 0.4,
        "packet_loss_pct": 0.0,
        "mqtt_rtt_ms": 40.0,
        "ups_status": "line",
        "battery_pct": 100.0,
        "temperature_c": 48.0,
        "cert_days_remaining": 300,
        "relays": [_RELE],
        "transition_reason": "heartbeat",
    }
    base.update(over)
    return base


def _estado(conn: psycopg.Connection, ts: str) -> object:
    fila = conn.execute(
        "SELECT relays_state FROM device_health WHERE gateway_id = %s AND ts = %s",
        (GW, ts),
    ).fetchone()
    assert fila is not None, f"no se persistió el latido de {ts}"
    return fila[0]


# ---------------------------------------------------------------------------
# EL CRITERIO
# ---------------------------------------------------------------------------


def test_un_gabinete_sin_dueno_de_pines_no_se_confunde_con_uno_sano(fleet, ctx, meta) -> None:  # noqa: ANN001
    """Dos instantáneas, todo igual salvo quién manda en los pines.

    El gabinete sano publica su censo de relés. El huérfano publica `null`
    («no pude preguntar al dueño de los pines»). Si tras el ingest las dos filas
    fueran iguales, la nube no tendría con qué levantar la voz — que es
    exactamente el defecto que esta tarea cierra.
    """
    con_dueno = "2026-08-08T10:00:00+00:00"
    sin_dueno = "2026-08-08T10:01:00+00:00"
    assert handle_health_snapshot(fleet, _health(con_dueno), meta, ctx).is_ok
    assert handle_health_snapshot(fleet, _health(sin_dueno, relays=None), meta, ctx).is_ok

    assert _estado(fleet, con_dueno) == RELAYS_REPORTED
    assert _estado(fleet, sin_dueno) == RELAYS_UNREADABLE
    assert _estado(fleet, con_dueno) != _estado(fleet, sin_dueno), (
        "el gabinete sin dueño de pines aterrizó igual que el sano: desde la nube "
        "un edificio sin sirena, sin gas, sin ascensores y sin retenedores se ve "
        "idéntico a uno protegido"
    )


def test_el_modulo_detenido_es_un_tercer_hecho_y_no_se_funde_con_ninguno(fleet, ctx, meta) -> None:  # noqa: ANN001
    """`[]` = «pregunté y no hay filas». No es lo mismo que «no pude preguntar».

    NO-VACUIDAD del par de arriba: si el rótulo nuevo se comiera cualquier
    ausencia de relés, esta distinción desaparecería y volveríamos a un único
    estado ambiguo, sólo que con otro nombre.
    """
    ts = "2026-08-08T10:02:00+00:00"
    assert handle_health_snapshot(fleet, _health(ts, relays=[]), meta, ctx).is_ok
    assert _estado(fleet, ts) == RELAYS_STOPPED
    assert len({RELAYS_REPORTED, RELAYS_STOPPED, RELAYS_UNREADABLE}) == 3


# ---------------------------------------------------------------------------
# Compatibilidad hacia atrás y payloads hostiles
# ---------------------------------------------------------------------------


def test_un_firmware_viejo_sin_la_clave_no_opina(fleet, ctx, meta) -> None:
    """Ausencia ≠ `null`. Misma disciplina que `_fw_field` (T-2.69/T-2.70).

    Un latido que no trae la clave no está diciendo «no pude preguntar»: no está
    diciendo nada. Se persiste NULL y la consola lo pinta S/D — jamás verde, y
    jamás un rótulo que el gabinete no emitió.
    """
    ts = "2026-08-08T10:03:00+00:00"
    payload = _health(ts)
    del payload["relays"]
    assert handle_health_snapshot(fleet, payload, meta, ctx).is_ok
    assert _estado(fleet, ts) is None


@pytest.mark.parametrize(
    "basura",
    [
        "sin_dueno",  # cadena que IMITA el rótulo interno
        42,
        {"channel": "siren"},  # objeto en vez de lista
        True,
    ],
)
def test_un_payload_manipulado_no_puede_escribir_lo_que_quiera(fleet, ctx, meta, basura) -> None:  # noqa: ANN001
    """El ingest NO confía en el dispositivo: lo que no es lista ni `null` no opina.

    Y en particular no puede escribir un rótulo INVENTADO en la columna: si la
    consola pintara lo que llega, un gabinete comprometido podría teñirse de
    verde (o teñir de rojo a su vecino cuando esto se agregue por sitio).
    """
    ts = "2026-08-08T10:04:00+00:00"
    assert handle_health_snapshot(fleet, _health(ts, relays=basura), meta, ctx).is_ok
    assert _estado(fleet, ts) is None


def test_el_resto_del_latido_entra_igual_con_los_reles_ilegibles(fleet, ctx, meta) -> None:
    """El censo de relés no puede llevarse por delante la salud del gabinete.

    Un `null` en `relays` tiene que dejar la fila con su temperatura, su UPS y su
    lag intactos: si el handler reventara, perderíamos TAMBIÉN el latido — y el
    gabinete pasaría a verse fantasma, que es peor que verse sano.
    """
    ts = "2026-08-08T10:05:00+00:00"
    assert handle_health_snapshot(fleet, _health(ts, relays=None), meta, ctx).is_ok
    fila = fleet.execute(
        "SELECT cpu_temp_c, power_status, battery_pct, seedlink_lag_s, relays_state "
        "FROM device_health WHERE gateway_id = %s AND ts = %s",
        (GW, ts),
    ).fetchone()
    assert fila[0] == pytest.approx(48.0)
    assert fila[1] == "line"
    assert fila[2] == pytest.approx(100.0)
    assert fila[3] == pytest.approx(0.4)
    assert fila[4] == RELAYS_UNREADABLE


# ---------------------------------------------------------------------------
# Regla de oro 3 · idempotencia
# ---------------------------------------------------------------------------


def test_reenviar_el_mismo_latido_no_duplica_ni_reescribe(fleet, ctx, meta) -> None:
    """Reconexión ⇒ el gabinete reenvía. `ON CONFLICT (ts, gateway_id) DO NOTHING`.

    Y la segunda mitad del test es la que importa de verdad: un reenvío con OTRO
    valor de relés sobre el MISMO instante **no pisa** lo que ya se escribió. Una
    fila de salud es un hecho fechado, no una casilla mutable.
    """
    ts = "2026-08-08T10:06:00+00:00"
    assert handle_health_snapshot(fleet, _health(ts, relays=None), meta, ctx).is_ok
    assert handle_health_snapshot(fleet, _health(ts, relays=None), meta, ctx).is_ok
    assert handle_health_snapshot(fleet, _health(ts, relays=[_RELE]), meta, ctx).is_ok
    filas = fleet.execute(
        "SELECT relays_state FROM device_health WHERE gateway_id = %s AND ts = %s",
        (GW, ts),
    ).fetchall()
    assert len(filas) == 1
    assert filas[0][0] == RELAYS_UNREADABLE


def test_la_columna_rechaza_rotulos_que_el_producto_no_conoce(fleet) -> None:
    """El CHECK es la última línea: nadie escribe ahí por SQL directo un estado
    que la consola no sabe pintar."""
    fleet.execute("RESET ROLE")
    with pytest.raises(psycopg.errors.CheckViolation):
        fleet.execute(
            "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, relays_state) "
            "VALUES (%s, %s, %s, 'heartbeat', 'verde')",
            ("2026-08-08T10:07:00+00:00", TENANT, GW),
        )
