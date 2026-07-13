"""handle_command_ack (T-1.23): transición de ``commands`` por nonce.

Usa el ``seeded``/``use`` del conftest (transaccional). El ack DEBE venir del
gateway al que se emitió el comando (identidad X.509 del principal); la
re-entrega SQS es no-op idempotente y un ack tardío no revive un expired.
"""

from __future__ import annotations

import uuid

import psycopg

from conftest import GW_A, GW_B, SITE_A, TENANT_A, TENANT_B, use
from takab_api.contracts.loader import discriminate
from takab_api.contracts.meta import Meta
from takab_api.ingest.handlers import GatewayCtx, handle_command_ack

NONCE = "n-ack-0001"
USER = "9e0aa000-0000-0000-0000-000000000001"

META = Meta(principal="SER-A", topic="takab/acks", ts_iot=1782000000000)


def _ctx(gateway: str = GW_A, tenant: str = TENANT_A, serial: str = "SER-A") -> GatewayCtx:
    return GatewayCtx(
        gateway_id=uuid.UUID(gateway),
        gateway_serial=serial,
        iot_thing=serial,
        tenant_id=uuid.UUID(tenant),
        tenant_code="A",
        site_id=uuid.UUID(SITE_A),
        site_code="site-a",
        sensors={},
    )


def _seed_command(conn: psycopg.Connection, *, status: str = "pending") -> str:
    conn.execute("RESET ROLE")
    row = conn.execute(
        "INSERT INTO commands (tenant_id, site_id, gateway_id, issued_by, channel, "
        "action, nonce, expires_at, status) "
        "VALUES (%s,%s,%s,%s,'siren','activate',%s, now() + interval '30 seconds', %s) "
        "RETURNING command_id",
        (TENANT_A, SITE_A, GW_A, USER, NONCE, status),
    ).fetchone()
    return str(row[0])


def _payload(*, success: bool = True) -> dict:
    return {
        "kind": "command_ack",
        "command_id": "cid-1",
        "nonce": NONCE,
        "channel": "siren",
        "action": "activate",
        "success": success,
        "latency_s": 0.42,
        "executed_at": "2026-07-07T12:00:01+00:00",
        "detail": "relé",
    }


def _status(conn: psycopg.Connection, command_id: str) -> str:
    conn.execute("RESET ROLE")
    return conn.execute(
        "SELECT status FROM commands WHERE command_id = %s", (command_id,)
    ).fetchone()[0]


def test_discriminator_routes_command_ack() -> None:
    assert discriminate("actuator_ack", _payload()) == "command_ack"
    assert discriminate("actuator_ack", {"channel": "siren"}) == "actuator_ack"


def test_success_ack_transitions_to_acked(seeded: psycopg.Connection) -> None:
    command_id = _seed_command(seeded)
    use(seeded, "takab_ingest")
    result = handle_command_ack(seeded, _payload(success=True), META, _ctx())
    assert result.is_ok
    assert _status(seeded, command_id) == "acked"
    ack = seeded.execute(
        "SELECT ack FROM commands WHERE command_id = %s", (command_id,)
    ).fetchone()[0]
    assert ack["success"] is True and ack["latency_s"] == 0.42


def test_failure_ack_transitions_to_rejected(seeded: psycopg.Connection) -> None:
    command_id = _seed_command(seeded)
    use(seeded, "takab_ingest")
    handle_command_ack(seeded, _payload(success=False), META, _ctx())
    assert _status(seeded, command_id) == "rejected"


def test_wrong_gateway_is_rejected_with_audit(seeded: psycopg.Connection) -> None:
    command_id = _seed_command(seeded)
    use(seeded, "takab_ingest")
    result = handle_command_ack(
        seeded, _payload(), META, _ctx(gateway=GW_B, tenant=TENANT_B, serial="SER-B")
    )
    assert not result.is_ok
    assert _status(seeded, command_id) == "pending"  # intacto
    use(seeded, "takab_ingest")
    verbs = seeded.execute(
        "SELECT verb FROM audit_log WHERE tenant_id = %s", (TENANT_B,)
    ).fetchall()
    assert any("reject" in v[0] for v in verbs)


def test_unknown_nonce_is_rejected(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_ingest")
    payload = _payload()
    payload["nonce"] = "n-fantasma"
    result = handle_command_ack(seeded, payload, META, _ctx())
    assert not result.is_ok


def test_redelivery_is_idempotent(seeded: psycopg.Connection) -> None:
    command_id = _seed_command(seeded)
    use(seeded, "takab_ingest")
    handle_command_ack(seeded, _payload(success=True), META, _ctx())
    # Re-entrega SQS del MISMO ack (y hasta con success distinto): no-op.
    result = handle_command_ack(seeded, _payload(success=False), META, _ctx())
    assert result.is_ok
    assert _status(seeded, command_id) == "acked"


def test_late_ack_does_not_revive_expired(seeded: psycopg.Connection) -> None:
    command_id = _seed_command(seeded, status="expired")
    use(seeded, "takab_ingest")
    result = handle_command_ack(seeded, _payload(success=True), META, _ctx())
    assert result.is_ok  # no-op idempotente, sin DLQ
    assert _status(seeded, command_id) == "expired"


def test_self_test_ack_persists_results(seeded: psycopg.Connection) -> None:
    """[T-1.59] El ack del autodiagnóstico guarda `results` (por relé + salud
    del cache) en el jsonb `ack` — es lo que la consola pinta como chips."""
    seeded.execute("RESET ROLE")
    row = seeded.execute(
        "INSERT INTO commands (tenant_id, site_id, gateway_id, issued_by, channel, "
        "action, nonce, expires_at) "
        "VALUES (%s,%s,%s,%s,'system','self_test','n-st-0001', "
        "now() + interval '30 seconds') RETURNING command_id",
        (TENANT_A, SITE_A, GW_A, USER),
    ).fetchone()
    command_id = str(row[0])
    use(seeded, "takab_ingest")
    payload = {
        "kind": "command_ack",
        "command_id": command_id,
        "nonce": "n-st-0001",
        "channel": "system",
        "action": "self_test",
        "success": True,
        "latency_s": 1.6,
        "executed_at": "2026-07-12T12:00:02+00:00",
        "detail": "self-test completado",
        "results": {
            "relays": {"gas_valve": {"pulsed": True, "readback_ok": True}},
            "health": {"ups_status": "line"},
        },
    }
    result = handle_command_ack(seeded, payload, META, _ctx())
    assert result.is_ok
    assert _status(seeded, command_id) == "acked"
    ack = seeded.execute(
        "SELECT ack FROM commands WHERE command_id = %s", (command_id,)
    ).fetchone()[0]
    assert ack["results"]["relays"]["gas_valve"]["readback_ok"] is True
    assert ack["results"]["health"]["ups_status"] == "line"
