"""handle_command_ack (T-1.23): transición de ``commands`` por nonce.

Usa el ``seeded``/``use`` del conftest (transaccional). El ack DEBE venir del
gateway al que se emitió el comando (identidad X.509 del principal); la
re-entrega SQS es no-op idempotente y un ack tardío no revive un expired.
"""

from __future__ import annotations

import uuid

import psycopg

from conftest import GW_A, GW_B, SITE_A, SITE_B, TENANT_A, TENANT_B, use
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


# ----------------------------------------------------------------------------
# [T-6.17] El ABORTO de un simulacro viaja como SEGUNDO acuse del `drill_start`
# (`results.aborted`). Hasta aquí ese segundo mensaje era un no-op silencioso:
# la nube derivaba `active` del reloj y el teléfono anunciaba «SIMULACRO EN
# CURSO» minutos después de que el gabinete lo cortara (INFORME-UIUX U-01/U-03).
# ----------------------------------------------------------------------------

DRILL_ID = "d6000000-0000-0000-0000-000000000017"


def _seed_drill(conn: psycopg.Connection, sites: list[tuple[str, str, str, str]]) -> dict[str, str]:
    """Un simulacro de 300 s con un `drill_start` por sitio: (site, gateway, tenant, nonce)."""
    conn.execute("RESET ROLE")
    conn.execute(
        "INSERT INTO drills (drill_id, tenant_id, initiated_by, duration_s) "
        "VALUES (%s, %s, %s, 300)",
        (DRILL_ID, TENANT_A, USER),
    )
    commands: dict[str, str] = {}
    for site, gateway, tenant, nonce in sites:
        row = conn.execute(
            "INSERT INTO commands (tenant_id, site_id, gateway_id, issued_by, channel, "
            "action, nonce, expires_at, status) "
            "VALUES (%s,%s,%s,%s,'system','drill_start',%s, now() + interval '30 seconds', "
            "'pending') RETURNING command_id",
            (tenant, site, gateway, USER, nonce),
        ).fetchone()
        commands[site] = str(row[0])
        conn.execute(
            "INSERT INTO drill_sites (drill_id, site_id, tenant_id, command_id) "
            "VALUES (%s, %s, %s, %s)",
            (DRILL_ID, site, TENANT_A, commands[site]),
        )
    return commands


def _ack_drill(*, nonce: str, aborted: bool = False, reason: str = "SASMEX real") -> dict:
    ack = {
        "kind": "command_ack",
        "command_id": "cid-drill",
        "nonce": nonce,
        "channel": "system",
        "action": "drill_start",
        "success": True,
        "latency_s": 0.2,
        "executed_at": "2026-09-06T15:00:00+00:00",
        "detail": "simulacro iniciado",
    }
    if aborted:
        ack["detail"] = f"simulacro abortado: {reason}"
        ack["results"] = {
            "aborted": True,
            "abort_reason": reason,
            "aborted_at": "2026-09-06T15:00:30+00:00",
            "drill_id": DRILL_ID,
        }
    return ack


def _drill_row(conn: psycopg.Connection) -> tuple:
    conn.execute("RESET ROLE")
    return conn.execute(
        "SELECT stopped_at, stop_reason FROM drills WHERE drill_id = %s", (DRILL_ID,)
    ).fetchone()


def _site_row(conn: psycopg.Connection, site: str) -> tuple:
    conn.execute("RESET ROLE")
    return conn.execute(
        "SELECT aborted_at, abort_reason FROM drill_sites WHERE drill_id = %s AND site_id = %s",
        (DRILL_ID, site),
    ).fetchone()


def test_el_aborto_marca_el_sitio_y_cierra_el_simulacro_cuando_nadie_lo_ejecuta(
    seeded: psycopg.Connection,
) -> None:
    commands = _seed_drill(seeded, [(SITE_A, GW_A, TENANT_A, "n-drill-a")])
    use(seeded, "takab_ingest")
    assert handle_command_ack(seeded, _ack_drill(nonce="n-drill-a"), META, _ctx()).is_ok
    assert _status(seeded, commands[SITE_A]) == "acked"
    assert _drill_row(seeded) == (None, None)  # sonando: nadie lo ha cerrado

    use(seeded, "takab_ingest")
    result = handle_command_ack(seeded, _ack_drill(nonce="n-drill-a", aborted=True), META, _ctx())
    assert result.is_ok
    aborted_at, reason = _site_row(seeded, SITE_A)
    assert aborted_at is not None and reason == "SASMEX real"
    stopped_at, stop_reason = _drill_row(seeded)
    assert stopped_at is not None and stop_reason == "aborted"
    assert _status(seeded, commands[SITE_A]) == "acked"  # el acuse original no se reescribe
    seeded.execute("RESET ROLE")
    verbs = [
        v[0]
        for v in seeded.execute(
            "SELECT verb FROM audit_log WHERE tenant_id = %s AND object = %s",
            (TENANT_A, f"drill:{DRILL_ID}"),
        ).fetchall()
    ]
    assert "drill_site_aborted" in verbs


def test_el_aborto_de_un_sitio_no_cierra_el_simulacro_si_otro_sigue_sonando(
    seeded: psycopg.Connection,
) -> None:
    _seed_drill(
        seeded,
        [(SITE_A, GW_A, TENANT_A, "n-drill-a"), (SITE_B, GW_B, TENANT_B, "n-drill-b")],
    )
    ctx_b = _ctx(gateway=GW_B, tenant=TENANT_B, serial="SER-B")
    use(seeded, "takab_ingest")
    handle_command_ack(seeded, _ack_drill(nonce="n-drill-a"), META, _ctx())
    use(seeded, "takab_ingest")
    handle_command_ack(seeded, _ack_drill(nonce="n-drill-b"), META, ctx_b)

    use(seeded, "takab_ingest")
    handle_command_ack(seeded, _ack_drill(nonce="n-drill-a", aborted=True), META, _ctx())
    assert _site_row(seeded, SITE_A)[0] is not None
    assert _site_row(seeded, SITE_B)[0] is None
    assert _drill_row(seeded) == (None, None)  # B sigue ejecutándolo: el simulacro vive

    use(seeded, "takab_ingest")
    handle_command_ack(
        seeded, _ack_drill(nonce="n-drill-b", aborted=True, reason="tier instrumental"), META, ctx_b
    )
    assert _site_row(seeded, SITE_B)[1] == "tier instrumental"
    assert _drill_row(seeded)[1] == "aborted"


def test_el_aborto_reentregado_es_idempotente(seeded: psycopg.Connection) -> None:
    _seed_drill(seeded, [(SITE_A, GW_A, TENANT_A, "n-drill-a")])
    use(seeded, "takab_ingest")
    handle_command_ack(seeded, _ack_drill(nonce="n-drill-a"), META, _ctx())
    use(seeded, "takab_ingest")
    handle_command_ack(seeded, _ack_drill(nonce="n-drill-a", aborted=True), META, _ctx())
    primero = _site_row(seeded, SITE_A)
    use(seeded, "takab_ingest")
    assert handle_command_ack(
        seeded, _ack_drill(nonce="n-drill-a", aborted=True, reason="otra"), META, _ctx()
    ).is_ok
    assert _site_row(seeded, SITE_A) == primero  # ni la hora ni la razón se reescriben
    seeded.execute("RESET ROLE")
    n = seeded.execute(
        "SELECT count(*) FROM audit_log WHERE verb = 'drill_site_aborted' AND object = %s",
        (f"drill:{DRILL_ID}",),
    ).fetchone()[0]
    assert n == 1


def test_un_aborto_que_llega_antes_que_el_arranque_hace_las_dos_cosas(
    seeded: psycopg.Connection,
) -> None:
    """SQS estándar no ordena: el segundo acuse puede adelantar al primero."""
    commands = _seed_drill(seeded, [(SITE_A, GW_A, TENANT_A, "n-drill-a")])
    use(seeded, "takab_ingest")
    handle_command_ack(seeded, _ack_drill(nonce="n-drill-a", aborted=True), META, _ctx())
    assert _status(seeded, commands[SITE_A]) == "acked"  # el simulacro SÍ arrancó
    assert _site_row(seeded, SITE_A)[0] is not None
    assert _drill_row(seeded)[1] == "aborted"


def test_un_aborto_sobre_un_comando_que_no_es_simulacro_es_un_no_op(
    seeded: psycopg.Connection,
) -> None:
    command_id = _seed_command(seeded)  # siren/activate
    use(seeded, "takab_ingest")
    handle_command_ack(seeded, _payload(success=True), META, _ctx())
    payload = _payload(success=True)
    payload["results"] = {"aborted": True, "abort_reason": "x"}
    use(seeded, "takab_ingest")
    assert handle_command_ack(seeded, payload, META, _ctx()).is_ok
    assert _status(seeded, command_id) == "acked"


def test_un_aborto_de_otro_gateway_se_rechaza_con_auditoria(seeded: psycopg.Connection) -> None:
    _seed_drill(seeded, [(SITE_A, GW_A, TENANT_A, "n-drill-a")])
    use(seeded, "takab_ingest")
    handle_command_ack(seeded, _ack_drill(nonce="n-drill-a"), META, _ctx())
    use(seeded, "takab_ingest")
    result = handle_command_ack(
        seeded,
        _ack_drill(nonce="n-drill-a", aborted=True),
        META,
        _ctx(gateway=GW_B, tenant=TENANT_B, serial="SER-B"),
    )
    assert not result.is_ok
    assert _site_row(seeded, SITE_A)[0] is None
    assert _drill_row(seeded) == (None, None)
