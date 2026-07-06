"""Visibilidad y escritura de gov_operator (schema §8).

gov_operator: ve tenants gov_shared (no los private), NO escribe a nivel de fila, y
su ÚNICA vía de escritura es la función SECURITY DEFINER gov_ack_incident (acuse
open→acked con validación de gov_shared + traza en audit_log).
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import (
    GOV_AGENCY,
    INC_A,
    INC_G,
    TENANT_G,
    use,
)


def test_gov_sees_gov_shared_incident(seeded: psycopg.Connection) -> None:
    # app.tenant_id = agencia (≠ G) → la visibilidad depende solo de la rama gov_shared.
    use(seeded, "takab_app", tenant=GOV_AGENCY, app_role="gov_operator")
    rows = seeded.execute("SELECT tenant_id FROM incidents").fetchall()
    tenants = {str(r[0]) for r in rows}
    assert TENANT_G in tenants, "gov ve el incidente del tenant gov_shared"


def test_gov_cannot_see_private_incident(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=GOV_AGENCY, app_role="gov_operator")
    n = seeded.execute(
        "SELECT count(*) FROM incidents WHERE incident_id = %s", (INC_A,)
    ).fetchone()[0]
    assert n == 0, "gov NO ve incidentes de tenants private"


def test_gov_cannot_write_incident_directly(seeded: psycopg.Connection) -> None:
    # La política de escritura excluye a gov_operator → el UPDATE afecta 0 filas
    # (RLS filtra la fila para escritura aunque gov pueda leerla).
    use(seeded, "takab_app", tenant=GOV_AGENCY, app_role="gov_operator")
    cur = seeded.execute("UPDATE incidents SET state = 'acked' WHERE incident_id = %s", (INC_G,))
    assert cur.rowcount == 0, "gov no puede escribir incidents por RLS"
    use(seeded, "takab_ingest")
    state = seeded.execute(
        "SELECT state FROM incidents WHERE incident_id = %s", (INC_G,)
    ).fetchone()[0]
    assert state == "open"


def test_gov_ack_incident_success(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=GOV_AGENCY, app_role="gov_operator", user_id=GOV_AGENCY)
    seeded.execute("SELECT gov_ack_incident(%s)", (INC_G,))
    # verificar como ingest (bypass) el efecto: estado acked + traza en audit_log
    use(seeded, "takab_ingest")
    state = seeded.execute(
        "SELECT state FROM incidents WHERE incident_id = %s", (INC_G,)
    ).fetchone()[0]
    assert state == "acked"
    n = seeded.execute(
        "SELECT count(*) FROM audit_log WHERE verb = 'ack' AND object = %s",
        (f"incident:{INC_G}",),
    ).fetchone()[0]
    assert n == 1, "gov_ack_incident deja traza en audit_log"


def test_gov_ack_rejects_private_tenant(seeded: psycopg.Connection) -> None:
    # gov_ack sobre un incidente de tenant private debe fallar (no gov_shared).
    use(seeded, "takab_app", tenant=GOV_AGENCY, app_role="gov_operator", user_id=GOV_AGENCY)
    with pytest.raises(psycopg.errors.RaiseException, match="gov_shared"):
        seeded.execute("SELECT gov_ack_incident(%s)", (INC_A,))


def test_gov_ack_requires_gov_role(seeded: psycopg.Connection) -> None:
    # Un rol no-gov no puede usar la función aunque tenga EXECUTE.
    use(seeded, "takab_app", tenant=TENANT_G, app_role="soc_operator")
    with pytest.raises(psycopg.errors.RaiseException, match="gov_operator"):
        seeded.execute("SELECT gov_ack_incident(%s)", (INC_G,))


def test_gov_ack_rejects_double_ack(seeded: psycopg.Connection) -> None:
    # Transición inválida: acusar dos veces (open→acked, luego acked→acked).
    use(seeded, "takab_app", tenant=GOV_AGENCY, app_role="gov_operator", user_id=GOV_AGENCY)
    seeded.execute("SELECT gov_ack_incident(%s)", (INC_G,))
    with pytest.raises(psycopg.errors.RaiseException, match="transicion"):
        seeded.execute("SELECT gov_ack_incident(%s)", (INC_G,))
