"""Idempotencia por PK natural (regla de oro 3).

Nada se duplica al reinsertar la misma fila (edge→nube reconecta y reenvía): el
doble INSERT con ON CONFLICT DO NOTHING sobre la PK natural no crea duplicados.
"""

from __future__ import annotations

import psycopg

from conftest import SENSOR_A, SITE_A, TENANT_A, use


def test_waveform_double_insert_dedup(seeded: psycopg.Connection) -> None:
    # waveform_features_1s: PK natural (ts, sensor_id, channel). Lo escribe ingest.
    use(seeded, "takab_ingest")
    ts = "2026-07-06 11:11:11+00"
    row = (ts, TENANT_A, SITE_A, SENSOR_A, "EHZ", 0.42)
    sql = (
        "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, channel, pga_g) "
        "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING"
    )
    first = seeded.execute(sql, row)
    assert first.rowcount == 1
    second = seeded.execute(sql, row)
    assert second.rowcount == 0, "el reinsert por PK no debe duplicar"
    n = seeded.execute(
        "SELECT count(*) FROM waveform_features_1s WHERE ts = %s AND sensor_id = %s",
        (ts, SENSOR_A),
    ).fetchone()[0]
    assert n == 1


def test_incident_event_uuid_idempotent(seeded: psycopg.Connection) -> None:
    # incidents.event_uuid es UNIQUE (UUIDv7 del edge) → idempotencia del incidente.
    use(seeded, "takab_ingest")
    evt = "d5d5d5d5-0000-0000-0000-000000000005"
    sql = (
        "INSERT INTO incidents (event_uuid, tenant_id, site_id, opened_at, severity, trigger) "
        "VALUES (%s,%s,%s,%s,'warning','sasmex') ON CONFLICT (event_uuid) DO NOTHING"
    )
    args = (evt, TENANT_A, SITE_A, "2026-07-06 12:00:00+00")
    assert seeded.execute(sql, args).rowcount == 1
    assert seeded.execute(sql, args).rowcount == 0
    n = seeded.execute("SELECT count(*) FROM incidents WHERE event_uuid = %s", (evt,)).fetchone()[0]
    assert n == 1
