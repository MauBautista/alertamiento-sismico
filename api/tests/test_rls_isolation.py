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


# --- fw_releases (T-2.69): registro de PLATAFORMA, no de tenant ---------------
#
# La API ya acota el POST a takab_superadmin. Estas pruebas son la SEGUNDA
# cerradura: qué firmware corre el gabinete que protege un edificio no lo decide
# el cliente, y si un router se despistara la base lo tiene que negar igual.


def test_fw_releases_lo_lee_cualquier_rol_autenticado(seeded: psycopg.Connection) -> None:
    """El catálogo de firmware no es secreto: sin poder leerlo, la deriva que la
    consola pinta a cada cliente no significaría nada. Lo que sí está acotado por
    tenant es QUÉ gabinete corre qué, y eso vive en `gateways`."""
    use(seeded, "takab_app", tenant=TENANT_A, app_role="takab_superadmin")
    seeded.execute("INSERT INTO fw_releases (version) VALUES ('rls0001')")
    # …y lo lee un rol de cliente cualquiera, de OTRO tenant: el registro no es
    # de nadie en particular. (El dueño de la tabla queda sujeto igual por FORCE
    # RLS: ni takab_migrator publica sin ser superadmin de aplicación.)
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator")
    n = seeded.execute("SELECT count(*) FROM fw_releases WHERE version = 'rls0001'").fetchone()
    assert n[0] == 1


@pytest.mark.parametrize("app_role", ["tenant_admin", "soc_operator", "takab_support"])
def test_fw_releases_solo_las_publica_el_dueno_de_la_plataforma(
    seeded: psycopg.Connection, app_role: str
) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role=app_role)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute("INSERT INTO fw_releases (version) VALUES ('rls0002')")


@pytest.mark.parametrize(
    "dml", ["UPDATE fw_releases SET released_at = now()", "DELETE FROM fw_releases"]
)
def test_fw_releases_es_append_only_por_privilegio(seeded: psycopg.Connection, dml: str) -> None:
    """Ni siquiera el superadmin reescribe el registro. Cambiar la fecha —o borrar—
    un release reescribiría A POSTERIORI la deriva de TODA la flota: el "cuánto
    lleva corriendo código viejo" de cada gabinete dejaría de ser comprobable.
    Se consigue no concediendo el privilegio, no con un trigger: el trigger
    `forbid_update_delete` está reservado a evidencia/compliance (regla de oro 11).
    """
    use(seeded, "takab_app", tenant=TENANT_A, app_role="takab_superadmin")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute(dml)
