"""¿El mensaje entregado DOS VECES deja rastro doble? (T-2.136, criterio 3).

Una consulta de worker más lenta que el ``VisibilityTimeout`` de su cola hace
que SQS entregue el mensaje **otra vez** mientras el primero sigue trabajando.
La regla de oro 3 dice que la idempotencia debe absorberlo — pero eso es una
afirmación sobre el esquema, y **este fichero la MIDE**: entrega el mismo cuerpo
dos veces por los handlers REALES contra la DB real y cuenta las filas.

Por qué dos cuerpos idénticos y no un truco de visibilidad: para el consumidor,
una reentrega ES literalmente el mismo ``MessageBody`` otra vez (cambia el
``ReceiptHandle``, que no toca ninguna escritura). Y tienen que ser **idénticos
byte a byte**: ``meta_ts_iot`` alimenta el ``ts`` de ``device_health`` y del
beacon, así que regenerarlo produciría dos filas LEGÍTIMAS y el test mediría su
propio arnés en vez del sistema.

El arnés se confirma a sí mismo (lección de T-2.131): cada caso comprueba
primero que la PRIMERA entrega hizo lo que se esperaba —y que la fila existe—
antes de mirar la segunda. Si el escenario no se monta, el test lo dice; no se
infiere de un conteo que también valdría 0.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime

import boto3
import psycopg
import pytest
from moto import mock_aws

from conftest import _dsn
from takab_api.ingest.consumer import SqsConsumer
from takab_api.ingest.handlers import HANDLERS
from takab_api.ingest.registry import Registry
from takab_api.settings import Settings

REGION = "us-east-2"

# Flota propia de este módulo (sufijo `dup`): no se reutiliza la de
# `test_ingest_e2e.py` porque aquí hace falta un gabinete RETIRADO, y retirar el
# de otro módulo sería contaminarlo.
TENANT = uuid.UUID("dd000000-0000-0000-0000-000000000001")
SITE = uuid.UUID("dd100000-0000-0000-0000-000000000000")
GW = uuid.UUID("dd200000-0000-0000-0000-000000000000")
SENSOR = uuid.UUID("dd300000-0000-0000-0000-000000000000")
GW_RETIRED = uuid.UUID("dd200000-0000-0000-0000-000000000001")
THING = "gw-dup-0001"
THING_RETIRED = "gw-dup-ret-1"
STATION = "DUP001"


# ---------------------------------------------------------------- fixtures


def _limpiar() -> None:
    """Borra SOLO lo de este módulo. `audit_log` e `incident_actions` son
    append-only por trigger; en la DB de test la evidencia SINTÉTICA se retira en
    modo replica (superusuario), que es lo que desactiva ese trigger."""
    with psycopg.connect(_dsn()) as conn:
        conn.execute("DELETE FROM waveform_features_1s WHERE tenant_id = %s", (TENANT,))
        conn.execute("DELETE FROM device_health WHERE tenant_id = %s", (TENANT,))
        conn.execute("SET session_replication_role = 'replica'")
        conn.execute("DELETE FROM incident_actions WHERE tenant_id = %s", (TENANT,))
        conn.execute("DELETE FROM audit_log WHERE tenant_id = %s", (TENANT,))
        conn.execute("SET session_replication_role = 'origin'")
        conn.execute("DELETE FROM incidents WHERE tenant_id = %s", (TENANT,))
        conn.execute("DELETE FROM commands WHERE tenant_id = %s", (TENANT,))
        conn.commit()


@pytest.fixture(scope="module")
def flota():
    """Flota COMMITEADA (idempotente): el registry y los handlers la leen desde
    sus propias conexiones, no desde la transacción del test."""
    with psycopg.connect(_dsn()) as conn:
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s, 'tenant-dup', 'Dup') "
            "ON CONFLICT DO NOTHING",
            (TENANT,),
        )
        conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
            "(%s, %s, 'site-dup', 'Sitio Dup', "
            "ST_SetSRID(ST_MakePoint(-99.13, 19.43), 4326)::geography) ON CONFLICT DO NOTHING",
            (SITE, TENANT),
        )
        for gw, thing, status in ((GW, THING, "online"), (GW_RETIRED, THING_RETIRED, "retired")):
            conn.execute(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing, status) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (gateway_id) DO UPDATE "
                "SET status = EXCLUDED.status, metadata = '{}'::jsonb",
                (gw, TENANT, SITE, thing, thing, status),
            )
        conn.execute(
            "INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, model, serial) "
            "VALUES (%s, %s, %s, %s, 'structural', 'RS4D', %s) ON CONFLICT DO NOTHING",
            (SENSOR, TENANT, SITE, GW, STATION),
        )
        conn.commit()
    _limpiar()
    yield
    _limpiar()


@pytest.fixture
def sqs():
    with mock_aws():
        yield boto3.client("sqs", region_name=REGION)


@pytest.fixture
def colas(sqs) -> tuple[str, str]:
    dlq = sqs.create_queue(QueueName="q-dup-dlq")["QueueUrl"]
    arn = sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    q = sqs.create_queue(
        QueueName="q-dup",
        Attributes={
            "VisibilityTimeout": "0",
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": arn, "maxReceiveCount": "5"}),
        },
    )["QueueUrl"]
    return q, dlq


def _conn_ingest() -> psycopg.Connection:
    """Conexión con el rol REAL del worker (BYPASSRLS), como en producción."""
    conn = psycopg.connect(_dsn())
    conn.execute("SET ROLE takab_ingest")
    conn.commit()
    return conn


@pytest.fixture
def consumidor(sqs, colas) -> SqsConsumer:
    return SqsConsumer(
        colas[0],
        colas[1],
        HANDLERS,
        Registry(_conn_ingest),
        _conn_ingest,
        Settings(),
        per_message_commit=True,
        sqs_client=sqs,
        wait_time_s=0,
    )


# ----------------------------------------------------------------- helpers


def _cuerpo(payload: dict, topic: str, thing: str = THING) -> str:
    """Enriquecimiento de la IoT Rule. Se llama UNA vez y el resultado se
    reenvía: dos cuerpos con `meta_ts_iot` distinto no son una reentrega."""
    meta = {
        "meta_principal": thing,
        "meta_topic": topic,
        "meta_ts_iot": int(time.time() * 1000),
    }
    return json.dumps(payload | meta)


def _entregar(consumidor, sqs, url: str, cuerpo: str) -> dict:
    """UNA entrega del cuerpo: lo que ve el consumidor en una reentrega de SQS."""
    sqs.send_message(QueueUrl=url, MessageBody=cuerpo)
    return consumidor.process_once()


def _contar(sql: str, params: tuple) -> int:
    with psycopg.connect(_dsn()) as check:
        return check.execute(sql, params).fetchone()[0]


def _n_dlq(sqs, url: str) -> int:
    attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])
    return int(attrs["Attributes"]["ApproximateNumberOfMessages"])


# ============================================ los rastros que SÍ son idempotentes


def test_feature_1s_duplicado_deja_UNA_fila(flota, sqs, colas, consumidor) -> None:
    """PK natural `(ts, sensor_id, channel)` + ON CONFLICT DO NOTHING."""
    ts = datetime.now(tz=UTC)
    cuerpo = _cuerpo(
        {
            "station": STATION,
            "channel": "ENZ",
            "window_start": ts.isoformat(),
            "pga": 0.0021,
            "pgv": 0.043,
            "rms": 0.0007,
            "sta_lta": 1.3,
        },
        "takab/features",
    )
    sql = "SELECT count(*) FROM waveform_features_1s WHERE sensor_id = %s AND ts = %s"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_ok"] == 1
    assert _contar(sql, (SENSOR, ts)) == 1, "el arnés no escribió la primera fila"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_ok"] == 1
    assert _contar(sql, (SENSOR, ts)) == 1


def test_local_event_duplicado_deja_UN_incidente(flota, sqs, colas, consumidor) -> None:
    """UPSERT por `event_uuid`: la segunda entrega no crea incidente ni degrada."""
    event_id = uuid.uuid4().hex
    cuerpo = _cuerpo(
        {
            "event_id": event_id,
            "tenant_id": "tenant-dup",
            "site_id": "site-dup",
            "source": "local_threshold",
            "tier": "evacuate_or_hold",
            "created_at": datetime.now(tz=UTC).isoformat(),
        },
        "takab/events",
    )
    sql = "SELECT count(*) FROM incidents WHERE event_uuid = %s"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_ok"] == 1
    assert _contar(sql, (uuid.UUID(event_id),)) == 1, "el arnés no abrió el incidente"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_ok"] == 1
    assert _contar(sql, (uuid.UUID(event_id),)) == 1


def test_health_snapshot_duplicado_deja_UNA_fila(flota, sqs, colas, consumidor) -> None:
    """`(ts, gateway_id)` — y por eso el cuerpo tiene que ser el MISMO: el `ts`
    sale de `captured_at`, no del reloj del worker."""
    captured = datetime.now(tz=UTC)
    cuerpo = _cuerpo(
        {
            "gateway_id": THING,
            "captured_at": captured.isoformat(),
            "seedlink_lag_s": 0.4,
            "temperature_c": 44.2,
            "ups_status": "line",
        },
        "takab/health",
    )
    sql = "SELECT count(*) FROM device_health WHERE gateway_id = %s AND ts = %s"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_ok"] == 1
    assert _contar(sql, (GW, captured)) == 1, "el arnés no escribió el latido"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_ok"] == 1
    assert _contar(sql, (GW, captured)) == 1


def test_actuator_ack_duplicado_deja_UNA_accion(flota, sqs, colas, consumidor) -> None:
    """`uq_incident_actions_ack (incident_id, kind, actor, ts)` — y la tabla es
    append-only, así que un duplicado aquí sería INSUBSANABLE: no hay DELETE."""
    event_id = uuid.uuid4().hex
    executed = datetime.now(tz=UTC)
    incidente = _cuerpo(
        {
            "event_id": event_id,
            "tenant_id": "tenant-dup",
            "site_id": "site-dup",
            "source": "sasmex",
            "tier": "evacuate_or_hold",
            "created_at": executed.isoformat(),
        },
        "takab/events",
    )
    assert _entregar(consumidor, sqs, colas[0], incidente)["n_ok"] == 1

    cuerpo = _cuerpo(
        {
            "event_id": event_id,
            "channel": "siren",
            "action": "activate",
            "success": True,
            "latency_s": 0.007,
            "executed_at": executed.isoformat(),
        },
        "takab/acks",
    )
    sql = (
        "SELECT count(*) FROM incident_actions a JOIN incidents i USING (incident_id) "
        "WHERE i.event_uuid = %s AND a.kind = 'siren_on'"
    )

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_ok"] == 1
    assert _contar(sql, (uuid.UUID(event_id),)) == 1, "el arnés no registró el acuse"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_ok"] == 1
    assert _contar(sql, (uuid.UUID(event_id),)) == 1


def test_command_ack_duplicado_no_duplica_la_bitacora(flota, sqs, colas, consumidor) -> None:
    """El acuse de comando SÍ escribe en `audit_log`, y aun así no se duplica:
    la guarda `status = 'pending'` corta ANTES de auditar. Es el contraejemplo
    que hace precisa la conclusión — no es que la ingesta no audite."""
    nonce = uuid.uuid4().hex
    command_id = uuid.uuid4()
    with psycopg.connect(_dsn()) as conn:
        conn.execute(
            "INSERT INTO commands (command_id, tenant_id, site_id, gateway_id, issued_by, "
            "channel, action, nonce, expires_at) VALUES (%s, %s, %s, %s, %s, 'siren', "
            "'activate', %s, now() + interval '10 min')",
            (command_id, TENANT, SITE, GW, uuid.uuid4(), nonce),
        )
        conn.commit()

    cuerpo = _cuerpo(
        {
            "kind": "command_ack",
            "command_id": str(command_id),
            "nonce": nonce,
            "channel": "siren",
            "action": "activate",
            "success": True,
            "latency_s": 0.01,
        },
        "takab/acks",
    )
    sql = "SELECT count(*) FROM audit_log WHERE object = %s AND verb = 'command_acked'"
    obj = f"command:{command_id}"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_ok"] == 1
    assert _contar(sql, (obj,)) == 1, "el arnés no dejó la bitácora del acuse"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_ok"] == 1
    assert _contar(sql, (obj,)) == 1


def test_beacon_de_retirado_duplicado_no_duplica_la_bitacora(flota, sqs, colas, consumidor) -> None:
    """El OTRO camino de la ingesta que audita: «sigue vivo aunque esté dado de
    baja» (T-2.65·B1). Lo protege la guarda monotónica sobre `status_ts`, que la
    reentrega ya no supera — por eso la segunda entrega no escribe."""
    cuerpo = _cuerpo({"status": "online"}, f"takab/status/{THING_RETIRED}", thing=THING_RETIRED)
    sql = (
        "SELECT count(*) FROM audit_log WHERE object = %s AND verb = 'gateway_alive_while_retired'"
    )
    obj = f"gateway:{GW_RETIRED}"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_ok"] == 1
    assert _contar(sql, (obj,)) == 1, "el arnés no montó el beacon del retirado"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_ok"] == 1
    assert _contar(sql, (obj,)) == 1


# ============================================ el rastro que NO es idempotente


def test_el_rechazo_de_identidad_duplicado_SI_deja_rastro_doble(
    flota, sqs, colas, consumidor
) -> None:
    """**El hallazgo de la ficha.** Todo lo que la ingesta escribe en tablas de
    negocio tiene PK natural… salvo un camino: el rechazo de identidad.

    `audit_log` es `audit_id GENERATED ALWAYS AS IDENTITY` + `ts DEFAULT now()`
    y **no tiene clave natural**, así que `_audit_reject` inserta una fila por
    ENTREGA, no por hecho. Dos entregas del mismo mensaje falsificado ⇒ dos
    renglones en una bitácora que es append-only por trigger y que **nunca se
    poda** (regla de oro 11): el rastro doble no se puede deshacer nunca.

    Se pinta el número medido a propósito. El arreglo vive en `audit.py` —
    escritor ÚNICO de la tabla, vetado por contract-test— y en una migración con
    índice único parcial; no cabe en la superficie de esta ficha. Cuando llegue,
    **este test se pone rojo**, y esa es exactamente la señal que se busca.
    """
    forjado = f"tenant-evil-{uuid.uuid4().hex[:8]}"
    cuerpo = _cuerpo(
        {
            "event_id": uuid.uuid4().hex,
            "tenant_id": forjado,
            "site_id": "site-dup",
            "source": "local_threshold",
            "tier": "evacuate_or_hold",
            "created_at": datetime.now(tz=UTC).isoformat(),
        },
        "takab/events",
    )
    sql = "SELECT count(*) FROM audit_log WHERE verb = 'ingest_reject' AND meta->>'reason' LIKE %s"
    patron = f"%{forjado}%"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_reject"] == 1
    assert _contar(sql, (patron,)) == 1, "el arnés no produjo el rechazo de identidad"

    assert _entregar(consumidor, sqs, colas[0], cuerpo)["n_reject"] == 1
    assert _contar(sql, (patron,)) == 2, (
        "si esto vale 1, el rastro doble ya está arreglado: actualiza el test y cierra la ficha"
    )
    # La DLQ recibe también las dos copias. Eso NO es el defecto: la DLQ es una
    # cola de mensajes por procesar, no una bitácora de compliance, y se drena.
    assert _n_dlq(sqs, colas[1]) == 2
