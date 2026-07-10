"""E2E fino de ingesta (T-1.17, fase C): moto-SQS + handlers y registry REALES + DB real.

Recorre el pipeline completo del consumer — enriquecimiento ``meta_*`` de la
IoT Rule → split → validación de schema → resolución de identidad en registro →
handler → commit → delete/DLQ — contra la flota dev de la convención fija
(UUIDs de ``db/seeds/prod_fleet.sql`` + ``sim_fleet.sql``). Los handlers corren
como ``takab_ingest``
(BYPASSRLS), igual que el worker real; las filas commiteadas usan event_id/ts
frescos por corrida para no chocar entre ejecuciones.
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
THING = "gw-dev-0001"  # meta_principal = thing name = gateways.iot_thing
SIM_THING = "gw-sim-0001"  # gateway sim: atiende VARIOS sitios (sim_fleet.sql)

# UUIDs fijos de la flota (db/seeds/prod_fleet.sql + sim_fleet.sql, sufijo 00 = dev).
TENANT = "d0000000-0000-0000-0000-000000000001"
SITE = "d1000000-0000-0000-0000-000000000000"
GW = "d2000000-0000-0000-0000-000000000000"
SENSOR = "d3000000-0000-0000-0000-000000000000"
SITE_SIM_1 = "d1000000-0000-0000-0000-000000000001"  # sitio propio de gw-sim-0001
SITE_SIM_2 = "d1000000-0000-0000-0000-000000000002"  # segundo sitio del bloque
GW_SIM = "d2000000-0000-0000-0000-000000000001"
SENSOR_SIM_1 = "d3000000-0000-0000-0000-000000000001"  # SIM001
SENSOR_SIM_2 = "d3000000-0000-0000-0000-000000000002"  # SIM002


# ---------------------------------------------------------------- fixtures


def _cleanup() -> None:
    """Borra SOLO lo que este módulo commitea (filas de negocio de tenant-dev):
    otros tests cuentan tablas globalmente en su transacción y asumen la DB sin
    filas persistidas. La flota (tenants/sites/gateways/sensors) se queda."""
    with psycopg.connect(_dsn()) as conn:
        conn.execute("DELETE FROM waveform_features_1s WHERE tenant_id = %s", (TENANT,))
        conn.execute("DELETE FROM incidents WHERE tenant_id = %s", (TENANT,))
        # audit_log es append-only por trigger; solo en la DB de test se retira
        # la evidencia SINTÉTICA de este módulo (modo replica = superusuario).
        conn.execute("SET session_replication_role = 'replica'")
        conn.execute(
            "DELETE FROM audit_log WHERE tenant_id = %s AND verb = 'ingest_reject'", (TENANT,)
        )
        conn.execute("SET session_replication_role = 'origin'")
        conn.commit()


@pytest.fixture(scope="module")
def fleet():
    """Flota dev mínima COMMITTEADA (idempotente): registry y handlers la ven
    desde sus propias conexiones, a diferencia del fixture transaccional."""
    with psycopg.connect(_dsn()) as conn:
        conn.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s, 'tenant-dev', 'TAKAB Dev') "
            "ON CONFLICT DO NOTHING",
            (TENANT,),
        )
        conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
            "(%s, %s, 'site-dev', 'Sitio Dev Puebla', "
            "ST_SetSRID(ST_MakePoint(-98.2063, 19.0414), 4326)::geography) "
            "ON CONFLICT DO NOTHING",
            (SITE, TENANT),
        )
        conn.execute(
            "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) VALUES "
            "(%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (GW, TENANT, SITE, THING, THING),
        )
        conn.execute(
            "INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, model, serial) "
            "VALUES (%s, %s, %s, %s, 'structural', 'RS4D', 'R4F74') ON CONFLICT DO NOTHING",
            (SENSOR, TENANT, SITE, GW),
        )
        # Bloque sim mínimo: gw-sim-0001 con sensores en DOS sitios (convención fija).
        sim_sites = ((SITE_SIM_1, "site-sim-001", -98.22), (SITE_SIM_2, "site-sim-002", -98.19))
        for site, code, lon in sim_sites:
            conn.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
                "(%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, 19.05), 4326)::geography) "
                "ON CONFLICT DO NOTHING",
                (site, TENANT, code, code, lon),
            )
        conn.execute(
            "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) VALUES "
            "(%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (GW_SIM, TENANT, SITE_SIM_1, SIM_THING, SIM_THING),
        )
        for sensor, site, serial in (
            (SENSOR_SIM_1, SITE_SIM_1, "SIM001"),
            (SENSOR_SIM_2, SITE_SIM_2, "SIM002"),
        ):
            conn.execute(
                "INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, model, "
                "serial) VALUES (%s, %s, %s, %s, 'structural', 'RS4D', %s) "
                "ON CONFLICT DO NOTHING",
                (sensor, TENANT, site, GW_SIM, serial),
            )
        conn.commit()
    _cleanup()  # restos de una corrida anterior abortada
    yield
    _cleanup()  # deja la DB como estaba para el resto de la suite


@pytest.fixture
def sqs():
    with mock_aws():
        yield boto3.client("sqs", region_name=REGION)


@pytest.fixture
def queues(sqs) -> tuple[str, str]:
    """Cola + DLQ con redrive real (como takab-dev-q-events)."""
    dlq = sqs.create_queue(QueueName="q-e2e-dlq")["QueueUrl"]
    dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    q = sqs.create_queue(
        QueueName="q-e2e",
        Attributes={
            "VisibilityTimeout": "0",
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "5"}),
        },
    )["QueueUrl"]
    return q, dlq


def _ingest_conn() -> psycopg.Connection:
    """Conexión con el rol real del worker (SET ROLE es de sesión tras commit)."""
    conn = psycopg.connect(_dsn())
    conn.execute("SET ROLE takab_ingest")
    conn.commit()
    return conn


@pytest.fixture
def consumer(sqs, queues) -> SqsConsumer:
    """Consumer REAL de eventos: handlers reales, registry real, commit por mensaje."""
    return SqsConsumer(
        queues[0],
        queues[1],
        HANDLERS,
        Registry(_ingest_conn),
        _ingest_conn,
        Settings(),
        per_message_commit=True,
        sqs_client=sqs,
        wait_time_s=0,
    )


# ----------------------------------------------------------------- helpers


def _enriched(payload: dict, topic: str, thing: str = THING) -> str:
    """Simula el enriquecimiento de la IoT Rule (T-1.15) sobre el JSON del edge."""
    return json.dumps(
        payload
        | {
            "meta_principal": thing,
            "meta_topic": topic,
            "meta_ts_iot": int(time.time() * 1000),
        }
    )


def _event(
    event_id: str, tier: str, tenant_code: str = "tenant-dev", site_code: str = "site-dev"
) -> dict:
    return {
        "event_id": event_id,
        "tenant_id": tenant_code,
        "site_id": site_code,
        "source": "local_threshold",
        "tier": tier,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }


def _n_messages(sqs, url: str) -> int:
    attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])
    return int(attrs["Attributes"]["ApproximateNumberOfMessages"])


# ------------------------------------------------------------------- tests


def test_feature_1s_ends_as_waveform_row(fleet, sqs, queues, consumer):
    """Feature1s válido con meta_* → fila en waveform_features_1s con los UUIDs
    del registro (jamás del payload)."""
    ts = datetime.now(tz=UTC)
    body = _enriched(
        {
            "station": "R4F74",
            "channel": "ENZ",
            "window_start": ts.isoformat(),
            "pga": 0.0021,
            "pgv": 0.043,
            "rms": 0.0007,
            "sta_lta": 1.3,
        },
        "takab/features",
    )
    sqs.send_message(QueueUrl=queues[0], MessageBody=body)

    stats = consumer.process_once()

    assert stats["n_ok"] == 1 and stats["n_reject"] == 0 and stats["n_retry"] == 0
    with psycopg.connect(_dsn()) as check:
        rows = check.execute(
            "SELECT tenant_id, site_id, channel, pga_g FROM waveform_features_1s "
            "WHERE ts = %s AND sensor_id = %s",
            (ts, SENSOR),
        ).fetchall()
    assert len(rows) == 1
    tenant_id, site_id, channel, pga_g = rows[0]
    assert (tenant_id, site_id, channel) == (uuid.UUID(TENANT), uuid.UUID(SITE), "ENZ")
    assert pga_g == pytest.approx(0.0021)
    assert _n_messages(sqs, queues[0]) == 0 and _n_messages(sqs, queues[1]) == 0


def test_local_event_escalates_into_single_incident(fleet, sqs, queues, consumer):
    """watch → evacuate_or_hold con el MISMO event_id ⇒ UN incidente escalado
    a critical (UPSERT G3), no dos filas."""
    event_id = uuid.uuid4().hex
    for tier in ("watch", "evacuate_or_hold"):
        sqs.send_message(
            QueueUrl=queues[0], MessageBody=_enriched(_event(event_id, tier), "takab/events")
        )
        stats = consumer.process_once()
        assert stats["n_ok"] == 1 and stats["n_reject"] == 0

    with psycopg.connect(_dsn()) as check:
        rows = check.execute(
            "SELECT severity, summary->>'tier', trigger FROM incidents WHERE event_uuid = %s",
            (uuid.UUID(event_id),),
        ).fetchall()
    assert rows == [("critical", "evacuate_or_hold", "local_threshold")]
    assert _n_messages(sqs, queues[1]) == 0


def test_sim_gateway_secondary_site_attributed_end_to_end(fleet, sqs, queues, consumer):
    """Vía registry REAL: gw-sim-0001 publica de site-sim-002 (su segundo sitio).
    Ni el evento ni el feature van a la DLQ, y ambos quedan atribuidos al sitio
    del payload/sensor — no al sitio propio del gateway (site-sim-001)."""
    event_id = uuid.uuid4().hex
    ts = datetime.now(tz=UTC)
    sqs.send_message(
        QueueUrl=queues[0],
        MessageBody=_enriched(
            _event(event_id, "evacuate_or_hold", site_code="site-sim-002"),
            "takab/events",
            thing=SIM_THING,
        ),
    )
    sqs.send_message(
        QueueUrl=queues[0],
        MessageBody=_enriched(
            {
                "station": "SIM002",
                "channel": "ENZ",
                "window_start": ts.isoformat(),
                "pga": 0.05,
                "pgv": 3.1,
                "rms": 0.02,
                "sta_lta": 4.2,
            },
            "takab/features",
            thing=SIM_THING,
        ),
    )

    for _ in range(3):  # moto puede repartir el batch en varias recepciones
        if _n_messages(sqs, queues[0]) == 0:
            break
        stats = consumer.process_once()
        assert stats["n_reject"] == 0 and stats["n_retry"] == 0

    with psycopg.connect(_dsn()) as check:
        inc_site = check.execute(
            "SELECT site_id FROM incidents WHERE event_uuid = %s", (uuid.UUID(event_id),)
        ).fetchone()
        wf_site = check.execute(
            "SELECT site_id FROM waveform_features_1s WHERE ts = %s AND sensor_id = %s",
            (ts, SENSOR_SIM_2),
        ).fetchone()
    assert inc_site == (uuid.UUID(SITE_SIM_2),)  # el sitio del EVENTO
    assert wf_site == (uuid.UUID(SITE_SIM_2),)  # el sitio del SENSOR
    assert _n_messages(sqs, queues[1]) == 0  # nada en la DLQ


def test_forged_tenant_lands_in_dlq_with_reason(fleet, sqs, queues, consumer):
    """tenant_id falsificado en el payload ⇒ REJECT de identidad: DLQ con razón,
    nada en incidents y evidencia commiteada en audit_log."""
    forged = f"tenant-evil-{uuid.uuid4().hex[:8]}"
    event_id = uuid.uuid4().hex
    sqs.send_message(
        QueueUrl=queues[0],
        MessageBody=_enriched(_event(event_id, "evacuate_or_hold", forged), "takab/events"),
    )

    stats = consumer.process_once()

    assert stats["n_reject"] == 1 and stats["n_ok"] == 0
    assert _n_messages(sqs, queues[0]) == 0  # el original se borró
    resp = sqs.receive_message(QueueUrl=queues[1], MessageAttributeNames=["All"])
    msgs = resp.get("Messages", [])
    assert len(msgs) == 1
    attrs = msgs[0]["MessageAttributes"]
    reason = attrs["reason"]["StringValue"]
    assert "tenant mismatch" in reason and forged in reason
    assert attrs["original_topic"]["StringValue"] == "takab/events"

    with psycopg.connect(_dsn()) as check:
        incident = check.execute(
            "SELECT 1 FROM incidents WHERE event_uuid = %s", (uuid.UUID(event_id),)
        ).fetchone()
        audit = check.execute(
            "SELECT 1 FROM audit_log WHERE verb = 'ingest_reject' AND meta->>'reason' LIKE %s",
            (f"%{forged}%",),
        ).fetchone()
    assert incident is None
    assert audit is not None
