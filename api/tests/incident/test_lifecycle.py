"""Ciclo de vida del incidente con DB (T-1.19 · B2 · G5). Fixtures por SQL.

Transición válida actualiza state (+ traza en incident_actions/audit_log); cerrar
fija closed_at; inválida / terminal / inexistente lanzan; close_resolved cierra en
bloque los incidentes NO cerrados de un evento. Corre como ``takab_ingest``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import psycopg
import pytest
from psycopg.rows import dict_row

from takab_api.incident.lifecycle import (
    IncidentNotFound,
    close_resolved,
    transition_incident,
)
from takab_api.incident.transitions import InvalidTransition

NOW = datetime(2026, 7, 7, 12, 0, 0, tzinfo=UTC)
EVENT_ID = "EVT-B2-LIFECYCLE"
OTHER_EVENT_ID = "EVT-B2-OTHER"
TENANT = "10000000-0000-0000-0000-0000000000c1"
SITE = "40000000-0000-0000-0000-000000000001"
MISSING = "deadbeef-0000-0000-0000-000000000000"


def _dsn() -> str:
    url = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab"
    )
    return url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def dconn() -> psycopg.Connection:
    """Conexión dict_row transaccional (rollback); rol takab_ingest para las ops."""
    c = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def _base(c: psycopg.Connection) -> None:
    c.execute("RESET ROLE")
    c.execute(
        "INSERT INTO tenants (tenant_id, code, name, visibility) VALUES (%s,'B2C','B2','private')",
        (TENANT,),
    )
    c.execute(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
        "(%s,%s,'C1','S',ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography)",
        (SITE, TENANT),
    )
    for ev in (EVENT_ID, OTHER_EVENT_ID):
        c.execute(
            "INSERT INTO seismic_events (event_id, source, detected_at) "
            "VALUES (%s,'local_quorum',%s)",
            (ev, NOW),
        )
    c.execute("RESET ROLE")
    c.execute('SET ROLE "takab_ingest"')


def _mk_incident(
    c: psycopg.Connection, inc_id: str, state: str, *, event_id: str = EVENT_ID
) -> None:
    c.execute("RESET ROLE")
    c.execute(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, event_id, "
        "opened_at, severity, state, trigger) VALUES "
        "(%s, gen_random_uuid(), %s, %s, %s, %s, 'warning', %s, 'quorum')",
        (inc_id, TENANT, SITE, event_id, NOW, state),
    )
    c.execute("RESET ROLE")
    c.execute('SET ROLE "takab_ingest"')


def _state(c: psycopg.Connection, inc_id: str) -> dict:
    return c.execute(
        "SELECT state, closed_at FROM incidents WHERE incident_id = %s", (inc_id,)
    ).fetchone()


def test_transition_open_to_in_review(dconn: psycopg.Connection) -> None:
    _base(dconn)
    inc = "50000000-0000-0000-0000-000000000001"
    _mk_incident(dconn, inc, "open")
    out = transition_incident(dconn, inc, "in_review", "user:op1")
    assert out == "in_review"
    row = _state(dconn, inc)
    assert row["state"] == "in_review"
    assert row["closed_at"] is None
    action = dconn.execute(
        "SELECT kind, actor FROM incident_actions WHERE incident_id = %s", (inc,)
    ).fetchone()
    assert action["kind"] == "in_review"
    assert action["actor"] == "user:op1"
    audit = dconn.execute(
        "SELECT verb, object FROM audit_log WHERE object = %s", (f"incident:{inc}",)
    ).fetchone()
    assert audit["verb"] == "in_review"


def test_transition_open_to_acked_uses_ack_kind(dconn: psycopg.Connection) -> None:
    _base(dconn)
    inc = "50000000-0000-0000-0000-000000000002"
    _mk_incident(dconn, inc, "open")
    transition_incident(dconn, inc, "acked", "user:op1")
    assert _state(dconn, inc)["state"] == "acked"
    kind = dconn.execute(
        "SELECT kind FROM incident_actions WHERE incident_id = %s", (inc,)
    ).fetchone()["kind"]
    assert kind == "ack"


def test_close_sets_closed_at(dconn: psycopg.Connection) -> None:
    _base(dconn)
    inc = "50000000-0000-0000-0000-000000000003"
    _mk_incident(dconn, inc, "acked")
    transition_incident(dconn, inc, "closed", "system")
    row = _state(dconn, inc)
    assert row["state"] == "closed"
    assert row["closed_at"] is not None
    kind = dconn.execute(
        "SELECT kind FROM incident_actions WHERE incident_id = %s", (inc,)
    ).fetchone()["kind"]
    assert kind == "close"


def test_invalid_transition_raises_and_leaves_state(dconn: psycopg.Connection) -> None:
    _base(dconn)
    inc = "50000000-0000-0000-0000-000000000004"
    _mk_incident(dconn, inc, "closed")
    with pytest.raises(InvalidTransition):
        transition_incident(dconn, inc, "open", "user:op1")
    assert _state(dconn, inc)["state"] == "closed"


def test_retreat_transition_raises(dconn: psycopg.Connection) -> None:
    _base(dconn)
    inc = "50000000-0000-0000-0000-000000000005"
    _mk_incident(dconn, inc, "in_review")
    with pytest.raises(InvalidTransition):
        transition_incident(dconn, inc, "acked", "user:op1")


def test_closed_is_terminal(dconn: psycopg.Connection) -> None:
    _base(dconn)
    inc = "50000000-0000-0000-0000-000000000006"
    _mk_incident(dconn, inc, "closed")
    with pytest.raises(InvalidTransition):
        transition_incident(dconn, inc, "closed", "system")


def test_missing_incident_raises(dconn: psycopg.Connection) -> None:
    _base(dconn)
    with pytest.raises(IncidentNotFound):
        transition_incident(dconn, MISSING, "acked", "user:op1")


def test_close_resolved_closes_open_incidents_of_event(dconn: psycopg.Connection) -> None:
    _base(dconn)
    open_inc = "60000000-0000-0000-0000-000000000001"
    acked_inc = "60000000-0000-0000-0000-000000000002"
    closed_inc = "60000000-0000-0000-0000-000000000003"
    other_inc = "60000000-0000-0000-0000-000000000004"
    _mk_incident(dconn, open_inc, "open")
    _mk_incident(dconn, acked_inc, "acked")
    _mk_incident(dconn, closed_inc, "closed")
    _mk_incident(dconn, other_inc, "open", event_id=OTHER_EVENT_ID)

    closed = close_resolved(dconn, EVENT_ID)
    assert set(closed) == {open_inc, acked_inc}
    for inc in (open_inc, acked_inc):
        row = _state(dconn, inc)
        assert row["state"] == "closed"
        assert row["closed_at"] is not None
    # El incidente de otro evento no se toca.
    assert _state(dconn, other_inc)["state"] == "open"
    # Auditoría: una fila 'close' por incidente cerrado en esta pasada.
    n = dconn.execute(
        "SELECT count(*) AS n FROM audit_log WHERE verb = 'close'",
    ).fetchone()["n"]
    assert n == 2


def test_close_resolved_is_idempotent(dconn: psycopg.Connection) -> None:
    _base(dconn)
    inc = "60000000-0000-0000-0000-000000000010"
    _mk_incident(dconn, inc, "open")
    first = close_resolved(dconn, EVENT_ID)
    second = close_resolved(dconn, EVENT_ID)
    assert first == [inc]
    assert second == []
