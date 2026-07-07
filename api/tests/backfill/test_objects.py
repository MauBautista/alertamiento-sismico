"""Ingesta de objetos S3 del backfill contra Postgres real (T-1.25).

El NDJSON es EXACTAMENTE el spool del edge ({topic, payload, spooled_at}); las
líneas pasan por ingest.handlers verbatim ⇒ re-proceso = CERO deltas. La
evidencia se verifica por sha256 REAL y se linkea por incidents.event_uuid.
Tenant/flota frescos por test + limpieza (el worker COMMITEA).
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.backfill.objects import process_s3_object
from takab_api.ingest.handlers import GatewayCtx, Outcome, SensorRef
from takab_api.settings import Settings

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
BUCKET_TRANSFER = "takab-dev-transfer"
BUCKET_EVIDENCE = "takab-dev-evidence"
TS0 = datetime(2026, 7, 7, 6, 0, 0, tzinfo=UTC)


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    return url.replace("postgresql+psycopg://", "postgresql://")


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put(self, bucket: str, key: str, body: bytes) -> None:
        self.objects[(bucket, key)] = body

    def get_object(self, Bucket: str, Key: str) -> dict:  # noqa: N803 — firma boto3
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


class _FakeRegistry:
    def __init__(self, ctx_by_thing: dict[str, GatewayCtx]) -> None:
        self._ctx = ctx_by_thing

    def resolve(self, principal: str) -> GatewayCtx | None:
        return self._ctx.get(principal)


class _Scenario:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
        self.tenant = str(uuid.uuid4())
        self.site = str(uuid.uuid4())
        self.gateway = str(uuid.uuid4())
        self.sensor = str(uuid.uuid4())
        self.station = f"BF{uuid.uuid4().hex[:5].upper()}"
        self.thing = f"gw-bf-{self.gateway[:8]}"

    def seed(self) -> None:
        c = self.conn
        c.execute("RESET ROLE")
        c.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'BF Test')",
            (self.tenant, self.tenant[:8]),
        )
        c.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
            "(%s,%s,%s,'S', ST_SetSRID(ST_MakePoint(-101.5,11.5),4326)::geography)",
            (self.site, self.tenant, f"BF-{self.site[:8]}"),
        )
        c.execute(
            "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
            "VALUES (%s,%s,%s,%s,%s)",
            (self.gateway, self.tenant, self.site, self.thing, self.thing),
        )
        c.execute(
            "INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, "
            "model, serial) VALUES (%s,%s,%s,%s,'structural','RS4D',%s)",
            (self.sensor, self.tenant, self.site, self.gateway, self.station),
        )
        c.commit()
        c.execute("SET ROLE takab_ingest")  # paridad con el worker real

    def ctx(self) -> GatewayCtx:
        return GatewayCtx(
            gateway_id=uuid.UUID(self.gateway),
            gateway_serial=self.thing,
            iot_thing=self.thing,
            tenant_id=uuid.UUID(self.tenant),
            tenant_code=self.tenant[:8],
            site_id=uuid.UUID(self.site),
            site_code="BF",
            sensors={
                self.station: SensorRef(
                    sensor_id=uuid.UUID(self.sensor),
                    site_id=uuid.UUID(self.site),
                    site_code="BF",
                )
            },
        )

    def count(self, sql: str, *params: object) -> int:
        return self.conn.execute(sql, params).fetchone()["count"]

    def counts(self) -> dict[str, int]:
        return {
            "features": self.count(
                "SELECT count(*) FROM waveform_features_1s WHERE tenant_id = %s", self.tenant
            ),
            "incidents": self.count(
                "SELECT count(*) FROM incidents WHERE tenant_id = %s", self.tenant
            ),
            "actions": self.count(
                "SELECT count(*) FROM incident_actions WHERE tenant_id = %s", self.tenant
            ),
            "evidence": self.count(
                "SELECT count(*) FROM evidence_objects WHERE tenant_id = %s", self.tenant
            ),
        }


@pytest.fixture
def scenario() -> Iterator[_Scenario]:
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    sc = _Scenario(conn)
    try:
        sc.seed()
        yield sc
    finally:
        _cleanup(conn, sc.tenant)
        conn.close()


def _cleanup(conn: psycopg.Connection, tenant: str) -> None:
    conn.rollback()
    conn.execute("RESET ROLE")
    try:
        conn.execute("SET session_replication_role = 'replica'")
        for table in (
            "evidence_objects",
            "incident_actions",
            "incidents",
            "waveform_features_1s",
            "sensors",
            "gateways",
            "sites",
            "tenants",
        ):
            conn.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (tenant,))  # noqa: S608
        conn.execute("SET session_replication_role = 'origin'")
        conn.commit()
    except psycopg.Error:
        conn.rollback()


# ------------------------------------------------------------ payloads NDJSON


def _feature_line(sc: _Scenario, second: int) -> dict:
    ts = TS0 + timedelta(seconds=second)
    return {
        "topic": "takab/features",
        "event_id": "",
        "payload": {
            "station": sc.station,
            "channel": "ENZ",
            "window_start": ts.isoformat(),
            "pga": 0.01,
            "pgv": 0.1,
            "rms": 0.001,
            "sta_lta": 1.0,
            "clipping": False,
            "health_score": 1.0,
        },
        "spooled_at": (ts + timedelta(seconds=1)).isoformat(),
    }


def _event_line(sc: _Scenario, event_hex: str) -> dict:
    return {
        "topic": "takab/events",
        "event_id": event_hex,
        "payload": {
            # El edge publica CÓDIGOS (no UUIDs): check_identity compara contra
            # ctx.tenant_code y los sitios atendidos (por código, vía sensores).
            "event_id": event_hex,
            "tenant_id": sc.tenant[:8],
            "site_id": "BF",
            "source": "local_threshold",
            "tier": "evacuate_or_hold",
            "created_at": (TS0 + timedelta(seconds=30)).isoformat(),
        },
        "spooled_at": (TS0 + timedelta(seconds=31)).isoformat(),
    }


def _ack_line(sc: _Scenario, event_hex: str) -> dict:
    return {
        "topic": "takab/acks",
        "event_id": event_hex,
        "payload": {
            "channel": "siren",
            "action": "activate",
            "event_id": event_hex,
            "success": True,
            "latency_s": 0.42,
            "executed_at": (TS0 + timedelta(seconds=31)).isoformat(),
            "detail": "relé",
        },
        "spooled_at": (TS0 + timedelta(seconds=32)).isoformat(),
    }


def _ndjson_gz(lines: list[dict]) -> bytes:
    return gzip.compress(
        ("\n".join(json.dumps(line, separators=(",", ":")) for line in lines) + "\n").encode()
    )


def _process(sc: _Scenario, s3: _FakeS3, bucket: str, key: str):
    registry = _FakeRegistry({sc.thing: sc.ctx()})
    return process_s3_object(sc.conn, bucket, key, registry, Settings(), s3_client=s3)


# --------------------------------------------------------------- NDJSON gzip


def test_ndjson_object_ingests_completely(scenario: _Scenario) -> None:
    event_hex = uuid.uuid4().hex
    # El ACK va ANTES que su evento (SQS/spool no garantiza orden semántico):
    # la ronda de RETRY dentro del objeto lo resuelve.
    lines = [
        _ack_line(scenario, event_hex),
        *(_feature_line(scenario, i) for i in range(3)),
        _event_line(scenario, event_hex),
    ]
    key = f"backfill/{scenario.thing}/x.ndjson.gz"
    s3 = _FakeS3()
    s3.put(BUCKET_TRANSFER, key, _ndjson_gz(lines))

    result = _process(scenario, s3, BUCKET_TRANSFER, key)

    assert result.outcome is Outcome.OK, result.reason
    assert result.ok == 5
    got = scenario.counts()
    assert got["features"] == 3
    assert got["incidents"] == 1
    assert got["actions"] == 1


def test_reprocess_is_zero_deltas(scenario: _Scenario) -> None:
    """Re-entrega SQS del MISMO objeto ⇒ idempotente (PK/ON CONFLICT)."""
    event_hex = uuid.uuid4().hex
    lines = [
        *(_feature_line(scenario, i) for i in range(3)),
        _event_line(scenario, event_hex),
        _ack_line(scenario, event_hex),
    ]
    key = f"backfill/{scenario.thing}/x.ndjson.gz"
    s3 = _FakeS3()
    s3.put(BUCKET_TRANSFER, key, _ndjson_gz(lines))

    assert _process(scenario, s3, BUCKET_TRANSFER, key).outcome is Outcome.OK
    before = scenario.counts()
    assert _process(scenario, s3, BUCKET_TRANSFER, key).outcome is Outcome.OK
    assert scenario.counts() == before  # cero deltas


def test_unknown_thing_in_key_rejected(scenario: _Scenario) -> None:
    key = "backfill/gw-fantasma/x.ndjson.gz"
    s3 = _FakeS3()
    s3.put(BUCKET_TRANSFER, key, _ndjson_gz([_feature_line(scenario, 0)]))
    result = _process(scenario, s3, BUCKET_TRANSFER, key)
    assert result.outcome is Outcome.REJECT


def test_malformed_lines_rejected_rest_ingested(scenario: _Scenario) -> None:
    key = f"backfill/{scenario.thing}/x.ndjson.gz"
    body = gzip.compress(
        (
            json.dumps(_feature_line(scenario, 0))
            + "\nno-es-json\n"
            + json.dumps({"topic": "takab/desconocido", "payload": {}})
            + "\n"
        ).encode()
    )
    s3 = _FakeS3()
    s3.put(BUCKET_TRANSFER, key, body)
    result = _process(scenario, s3, BUCKET_TRANSFER, key)
    assert result.outcome is Outcome.OK
    assert result.ok == 1 and result.rejected == 2
    assert scenario.counts()["features"] == 1


def test_plain_ndjson_without_gz_suffix(scenario: _Scenario) -> None:
    key = f"backfill/{scenario.thing}/x.ndjson"
    s3 = _FakeS3()
    s3.put(BUCKET_TRANSFER, key, (json.dumps(_feature_line(scenario, 0)) + "\n").encode())
    assert _process(scenario, s3, BUCKET_TRANSFER, key).outcome is Outcome.OK


# ----------------------------------------------------------------- evidencia


def _seed_incident(sc: _Scenario, event_hex: str) -> str:
    sc.conn.execute("RESET ROLE")
    row = sc.conn.execute(
        "INSERT INTO incidents (event_uuid, tenant_id, site_id, opened_at, severity, "
        "trigger) VALUES (%s,%s,%s,%s,'warning','local_threshold') RETURNING incident_id",
        (uuid.UUID(event_hex), sc.tenant, sc.site, TS0),
    ).fetchone()
    sc.conn.commit()
    sc.conn.execute("SET ROLE takab_ingest")
    return str(row["incident_id"])


def test_evidence_object_registered_and_linked(scenario: _Scenario) -> None:
    event_hex = uuid.uuid4().hex
    incident_id = _seed_incident(scenario, event_hex)
    body = b"MSEED-DE-PRUEBA"
    digest = hashlib.sha256(body).hexdigest()
    key = f"evidence/{scenario.tenant}/{event_hex}/{digest}.mseed"
    s3 = _FakeS3()
    s3.put(BUCKET_EVIDENCE, key, body)

    result = _process(scenario, s3, BUCKET_EVIDENCE, key)

    assert result.outcome is Outcome.OK, result.reason
    row = scenario.conn.execute(
        "SELECT incident_id::text, kind, sha256 FROM evidence_objects WHERE s3_key = %s",
        (key,),
    ).fetchone()
    assert row["incident_id"] == incident_id
    assert row["kind"] == "miniseed" and row["sha256"] == digest

    # Re-entrega: idempotente (uq parcial incident+sha256).
    assert _process(scenario, s3, BUCKET_EVIDENCE, key).outcome is Outcome.OK
    assert scenario.counts()["evidence"] == 1


def test_evidence_sha_mismatch_rejected(scenario: _Scenario) -> None:
    event_hex = uuid.uuid4().hex
    _seed_incident(scenario, event_hex)
    key = f"evidence/{scenario.tenant}/{event_hex}/{'b' * 64}.mseed"
    s3 = _FakeS3()
    s3.put(BUCKET_EVIDENCE, key, b"CONTENIDO-QUE-NO-CUADRA")
    result = _process(scenario, s3, BUCKET_EVIDENCE, key)
    assert result.outcome is Outcome.REJECT
    assert scenario.counts()["evidence"] == 0


def test_evidence_before_incident_is_retry(scenario: _Scenario) -> None:
    """El evento pudo venir en el MISMO backfill: sin incidente aún ⇒ RETRY."""
    body = b"MSEED"
    digest = hashlib.sha256(body).hexdigest()
    key = f"evidence/{scenario.tenant}/{uuid.uuid4().hex}/{digest}.mseed"
    s3 = _FakeS3()
    s3.put(BUCKET_EVIDENCE, key, body)
    assert _process(scenario, s3, BUCKET_EVIDENCE, key).outcome is Outcome.RETRY


# ------------------------------------------------------- cola sintética larga


@pytest.mark.skipif(
    not os.environ.get("TAKAB_SLOW_TESTS"),
    reason="cola 6 h completa (86 400 líneas): correr con TAKAB_SLOW_TESTS=1",
)
def test_six_hour_queue_ingests_completely_and_idempotent(scenario: _Scenario) -> None:
    """Criterio T-1.25 al pie de la letra: 6 h × 4 canales = 86 400 features."""
    lines = []
    for channel in ("ENZ", "ENE", "ENN", "EHZ"):  # 6 h × 4 canales = 86 400
        for i in range(21_600):
            line = _feature_line(scenario, i)
            line["payload"]["channel"] = channel
            lines.append(line)
    key = f"backfill/{scenario.thing}/6h.ndjson.gz"
    s3 = _FakeS3()
    s3.put(BUCKET_TRANSFER, key, _ndjson_gz(lines))

    result = _process(scenario, s3, BUCKET_TRANSFER, key)
    assert result.outcome is Outcome.OK
    assert result.ok == 86_400
    assert scenario.counts()["features"] == 86_400

    assert _process(scenario, s3, BUCKET_TRANSFER, key).outcome is Outcome.OK
    assert scenario.counts()["features"] == 86_400  # cero deltas
