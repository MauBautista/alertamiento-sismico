"""Aislamiento cross-tenant por RLS (regla de oro 5).

Un intento de cruzar tenants DEBE fallar: como takab_app (ENABLE) y también como
takab_migrator, el OWNER de las tablas (FORCE ROW LEVEL SECURITY — sin FORCE el
dueño saltaría RLS). Incluye el crudo waveform_features_1s, aislado por la vista
security_barrier (no puede llevar RLS por tener caggs).
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import (
    INC_A,
    TENANT_A,
    TENANT_B,
    use,
)


def test_app_only_sees_own_tenant_incidents(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator")
    rows = seeded.execute("SELECT tenant_id FROM incidents").fetchall()
    assert rows, "el tenant A debe ver su propio incidente"
    assert {str(r[0]) for r in rows} == {TENANT_A}


def test_owner_force_rls_isolates(seeded: psycopg.Connection) -> None:
    # takab_migrator es DUEÑO de incidents; FORCE lo sujeta igual a RLS.
    use(seeded, "takab_migrator", tenant=TENANT_A, app_role="soc_operator")
    rows = seeded.execute("SELECT tenant_id FROM incidents").fetchall()
    assert {str(r[0]) for r in rows} == {TENANT_A}, "FORCE RLS debe aislar al owner"


def test_app_cannot_read_other_tenant(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator")
    rows = seeded.execute(
        "SELECT count(*) FROM incidents WHERE tenant_id = %s", (TENANT_A,)
    ).fetchone()
    assert rows[0] == 0, "tenant B no puede ver filas del tenant A"


def test_device_health_rls_isolates(seeded: psycopg.Connection) -> None:
    # device_health conserva RLS (no tiene caggs) — se lee directo con RLS.
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator")
    rows = seeded.execute("SELECT tenant_id FROM device_health").fetchall()
    assert {str(r[0]) for r in rows} == {TENANT_A}


def test_app_cannot_write_other_tenant(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator")
    # Insertar una acción etiquetada con el tenant B viola el WITH CHECK de RLS.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute(
            "INSERT INTO incident_actions (incident_id, tenant_id, kind, actor) "
            "VALUES (%s,%s,'siren_on','user:x')",
            (INC_A, TENANT_B),
        )


def test_waveform_view_isolates_by_tenant(seeded: psycopg.Connection) -> None:
    # El crudo se lee por la vista security_barrier (JOIN a sites con RLS+FORCE).
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator")
    rows = seeded.execute("SELECT DISTINCT tenant_id FROM waveform_features_1s_secure").fetchall()
    assert {str(r[0]) for r in rows} == {TENANT_A}


def test_waveform_base_table_denied_to_app(seeded: psycopg.Connection) -> None:
    # takab_app NO tiene acceso a la tabla base: solo puede leer por la vista.
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute("SELECT count(*) FROM waveform_features_1s").fetchone()


@pytest.mark.parametrize("cagg", ["site_metrics_1m", "site_metrics_1h"])
def test_cagg_base_denied_to_app(seeded: psycopg.Connection, cagg: str) -> None:
    # Los caggs no llevan RLS: sin el REVOKE, un tenant leería las métricas de
    # TODOS (hallazgo CRÍTICO de la auditoría pre-frontend). takab_app solo puede
    # leerlos por la vista *_secure (JOIN sites con RLS).
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute(f"SELECT count(*) FROM {cagg}").fetchone()  # noqa: S608


def test_ingest_bypasses_rls(seeded: psycopg.Connection) -> None:
    # takab_ingest (BYPASSRLS) ve todos los tenants: escribe series ya etiquetadas.
    use(seeded, "takab_ingest")
    n = seeded.execute("SELECT count(*) FROM device_health").fetchone()[0]
    assert n == 2, "ingest ve las filas de ambos tenants"
