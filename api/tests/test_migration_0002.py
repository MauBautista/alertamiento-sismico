"""Migración 0002 (T-1.17): índices únicos de idempotencia para la ingesta.

* ``uq_incident_actions_ack``: un ActuatorAck re-entregado (mismo incidente,
  kind, actor y ts) NO duplica el timeline; acks distintos sí entran.
* ``uq_evidence_incident_sha256`` (parcial): dedup de evidencia por
  (incident_id, sha256); las filas sin sha256 quedan fuera del índice.

Se ejercita como takab_ingest (el rol que escribe estos datos en producción).
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import INC_A, TENANT_A, use

TS_ACK = "2026-07-06 12:34:56.789+00"
SHA = "a" * 64

ACK_SQL = (
    "INSERT INTO incident_actions (incident_id, tenant_id, ts, kind, actor, payload) "
    "VALUES (%s,%s,%s,%s,%s,'{}')"
)
EVID_SQL = (
    "INSERT INTO evidence_objects (tenant_id, incident_id, kind, s3_key, sha256) "
    "VALUES (%s,%s,'miniseed',%s,%s)"
)


def _count_acks(conn: psycopg.Connection) -> int:
    return conn.execute(
        "SELECT count(*) FROM incident_actions WHERE incident_id = %s AND ts = %s",
        (INC_A, TS_ACK),
    ).fetchone()[0]


def test_ack_reinsert_is_idempotent(seeded: psycopg.Connection) -> None:
    # Re-entrega SQS: mismo ack ⇒ ON CONFLICT DO NOTHING no duplica.
    use(seeded, "takab_ingest")
    row = (INC_A, TENANT_A, TS_ACK, "siren_on", "edge:gw-dev-0001")
    assert seeded.execute(ACK_SQL + " ON CONFLICT DO NOTHING", row).rowcount == 1
    assert seeded.execute(ACK_SQL + " ON CONFLICT DO NOTHING", row).rowcount == 0
    assert _count_acks(seeded) == 1


def test_ack_exact_duplicate_rejected(seeded: psycopg.Connection) -> None:
    # Sin ON CONFLICT el índice único rechaza el duplicado exacto.
    use(seeded, "takab_ingest")
    row = (INC_A, TENANT_A, TS_ACK, "gas_closed", "edge:gw-dev-0001")
    assert seeded.execute(ACK_SQL, row).rowcount == 1
    with pytest.raises(psycopg.errors.UniqueViolation, match="uq_incident_actions_ack"):
        seeded.execute(ACK_SQL, row)


def test_ack_distinct_acks_allowed(seeded: psycopg.Connection) -> None:
    # Cambiar cualquier componente de la clave natural ⇒ ack distinto, entra.
    use(seeded, "takab_ingest")
    base = (INC_A, TENANT_A, TS_ACK, "siren_on", "edge:gw-dev-0001")
    variants = [
        base,
        (INC_A, TENANT_A, "2026-07-06 12:34:57+00", "siren_on", "edge:gw-dev-0001"),
        (INC_A, TENANT_A, TS_ACK, "gas_closed", "edge:gw-dev-0001"),
        (INC_A, TENANT_A, TS_ACK, "siren_on", "edge:gw-sim-0001"),
    ]
    for row in variants:
        assert seeded.execute(ACK_SQL, row).rowcount == 1
    assert _count_acks(seeded) == 3  # la variante 2 tiene otro ts


def test_evidence_dedup_by_incident_and_sha256(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_ingest")
    row = (TENANT_A, INC_A, "s3://ev/1", SHA)
    assert seeded.execute(EVID_SQL + " ON CONFLICT DO NOTHING", row).rowcount == 1
    # mismo contenido re-entregado (aunque cambie la s3_key) ⇒ dedup
    dup = (TENANT_A, INC_A, "s3://ev/1-retry", SHA)
    assert seeded.execute(EVID_SQL + " ON CONFLICT DO NOTHING", dup).rowcount == 0
    # otro sha256 en el mismo incidente ⇒ evidencia distinta, entra
    other = (TENANT_A, INC_A, "s3://ev/2", "b" * 64)
    assert seeded.execute(EVID_SQL + " ON CONFLICT DO NOTHING", other).rowcount == 1
    n = seeded.execute(
        "SELECT count(*) FROM evidence_objects WHERE incident_id = %s AND sha256 IS NOT NULL",
        (INC_A,),
    ).fetchone()[0]
    assert n == 2


def test_evidence_null_sha256_outside_partial_index(seeded: psycopg.Connection) -> None:
    # Sin sha256 no hay dedup por contenido: el índice parcial no las cubre.
    use(seeded, "takab_ingest")
    row = (TENANT_A, INC_A, "s3://ev/no-hash", None)
    assert seeded.execute(EVID_SQL, row).rowcount == 1
    assert seeded.execute(EVID_SQL, row).rowcount == 1


def test_evidence_exact_duplicate_rejected(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_ingest")
    row = (TENANT_A, INC_A, "s3://ev/3", "c" * 64)
    assert seeded.execute(EVID_SQL, row).rowcount == 1
    with pytest.raises(psycopg.errors.UniqueViolation, match="uq_evidence_incident_sha256"):
        seeded.execute(EVID_SQL, row)
