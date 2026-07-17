"""Visibilidad configurable entre clientes (T-1.73) — RLS, regla de oro 5.

Prueba a nivel DB (como ``takab_app`` con GUCs de sesión) que un ``visibility_grant``
del superadmin AÑADE lectura cruzada de METADATOS y/o DATOS, preservando default-deny,
la separación metadata≠datos (el crux), la ausencia de escritura cruzada, el revoke
dinámico, y sin regresión de superadmin/gov.

Los grants se siembran como superusuario (bypassa RLS), igual que el resto del seed.
"""

from __future__ import annotations

import psycopg
import pytest

from conftest import (
    GOV_AGENCY,
    INC_A,
    TENANT_A,
    TENANT_B,
    TENANT_G,
    reset,
    use,
)


def _grant(
    conn: psycopg.Connection,
    grantee: str,
    *,
    target: str | None = None,
    target_all: bool = False,
    metadata: bool = False,
    data: bool = False,
) -> None:
    """Siembra un grant como superusuario (created_by = un uuid cualquiera)."""
    reset(conn)
    conn.execute(
        "INSERT INTO visibility_grants (grantee_tenant_id, target_tenant_id, target_all, "
        "can_view_metadata, can_view_data, created_by) VALUES (%s,%s,%s,%s,%s,%s)",
        (grantee, target, target_all, metadata, data, GOV_AGENCY),
    )


def _n(conn: psycopg.Connection, sql: str, *params: object) -> int:
    return conn.execute(sql, params).fetchone()[0]


def test_default_deny_without_grant(seeded: psycopg.Connection) -> None:
    """Sin grant, B no ve NADA de A (regresión del aislamiento base)."""
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator")
    assert _n(seeded, "SELECT count(*) FROM sites WHERE tenant_id=%s", TENANT_A) == 0
    assert _n(seeded, "SELECT count(*) FROM incidents WHERE tenant_id=%s", TENANT_A) == 0
    assert _n(seeded, "SELECT count(*) FROM device_health WHERE tenant_id=%s", TENANT_A) == 0
    assert (
        _n(seeded, "SELECT count(*) FROM waveform_features_1s_secure WHERE tenant_id=%s", TENANT_A)
        == 0
    )


def test_metadata_grant_reveals_existence_not_data(seeded: psycopg.Connection) -> None:
    """CRUX: un grant de SOLO-metadatos deja ver que EXISTEN las estaciones de A,
    pero NUNCA sus datos (formas de onda, salud, incidentes)."""
    _grant(seeded, TENANT_B, target=TENANT_A, metadata=True, data=False)
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator")
    # ve que existen
    assert _n(seeded, "SELECT count(*) FROM sites WHERE tenant_id=%s", TENANT_A) == 1
    assert _n(seeded, "SELECT count(*) FROM sensors WHERE tenant_id=%s", TENANT_A) == 1
    # pero NO los datos — el WHERE de la vista segura tapa el crudo pese al JOIN
    assert (
        _n(seeded, "SELECT count(*) FROM waveform_features_1s_secure WHERE tenant_id=%s", TENANT_A)
        == 0
    ), "un grant de metadatos JAMÁS debe filtrar formas de onda"
    assert _n(seeded, "SELECT count(*) FROM device_health WHERE tenant_id=%s", TENANT_A) == 0
    assert _n(seeded, "SELECT count(*) FROM incidents WHERE tenant_id=%s", TENANT_A) == 0


def test_data_grant_reveals_data_and_existence(seeded: psycopg.Connection) -> None:
    """Un grant de DATOS (sin metadatos) deja ver los datos de A y, como datos⊇existencia,
    también su sitio (el JOIN de la vista resuelve por app_can_view_meta ⊇ data)."""
    _grant(seeded, TENANT_B, target=TENANT_A, metadata=False, data=True)
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator")
    assert _n(seeded, "SELECT count(*) FROM sites WHERE tenant_id=%s", TENANT_A) == 1
    assert (
        _n(seeded, "SELECT count(*) FROM waveform_features_1s_secure WHERE tenant_id=%s", TENANT_A)
        == 1
    )
    assert _n(seeded, "SELECT count(*) FROM device_health WHERE tenant_id=%s", TENANT_A) == 1
    assert _n(seeded, "SELECT count(*) FROM incidents WHERE tenant_id=%s", TENANT_A) == 1
    assert _n(seeded, "SELECT count(*) FROM incident_actions WHERE tenant_id=%s", TENANT_A) == 1


def test_grant_never_allows_cross_tenant_write(seeded: psycopg.Connection) -> None:
    """Un grant AÑADE lectura, jamás escritura: B con datos de A no puede tocar su timeline."""
    _grant(seeded, TENANT_B, target=TENANT_A, metadata=True, data=True)
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute(
            "INSERT INTO incident_actions (incident_id, tenant_id, kind, actor) "
            "VALUES (%s,%s,'siren_on','user:x')",
            (INC_A, TENANT_A),
        )


def test_revoke_restores_default_deny(seeded: psycopg.Connection) -> None:
    """El revoke es dinámico: borrar el grant devuelve a cero en la siguiente consulta."""
    _grant(seeded, TENANT_B, target=TENANT_A, metadata=True, data=True)
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator")
    assert _n(seeded, "SELECT count(*) FROM sites WHERE tenant_id=%s", TENANT_A) == 1

    reset(seeded)
    seeded.execute("DELETE FROM visibility_grants WHERE grantee_tenant_id=%s", (TENANT_B,))
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator")
    assert _n(seeded, "SELECT count(*) FROM sites WHERE tenant_id=%s", TENANT_A) == 0
    assert (
        _n(seeded, "SELECT count(*) FROM waveform_features_1s_secure WHERE tenant_id=%s", TENANT_A)
        == 0
    )


def test_target_all_grant_reveals_every_tenant_metadata(seeded: psycopg.Connection) -> None:
    """target_all (TODOS los clientes) con metadatos: B ve que existen las estaciones de
    todos, pero sigue sin ver datos ajenos."""
    _grant(seeded, TENANT_B, target_all=True, metadata=True)
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator")
    seen = {str(r[0]) for r in seeded.execute("SELECT DISTINCT tenant_id FROM sites").fetchall()}
    assert {TENANT_A, TENANT_B, TENANT_G} <= seen
    assert (
        _n(seeded, "SELECT count(*) FROM waveform_features_1s_secure WHERE tenant_id=%s", TENANT_A)
        == 0
    )


def test_superadmin_unchanged_by_grants(seeded: psycopg.Connection) -> None:
    """El superadmin ve todo por ser interno TAKAB, con o sin grants (sin regresión)."""
    use(seeded, "takab_app", tenant=TENANT_A, app_role="takab_superadmin")
    seen = {str(r[0]) for r in seeded.execute("SELECT DISTINCT tenant_id FROM sites").fetchall()}
    assert {TENANT_A, TENANT_B, TENANT_G} <= seen
    assert _n(seeded, "SELECT count(*) FROM waveform_features_1s_secure") == 2


def test_grant_does_not_alter_gov_visibility(seeded: psycopg.Connection) -> None:
    """Un grant a un cliente private no cambia lo que ve gov_operator (solo gov_shared)."""
    _grant(seeded, TENANT_B, target=TENANT_A, metadata=True, data=True)
    use(seeded, "takab_app", tenant=GOV_AGENCY, app_role="gov_operator")
    assert _n(seeded, "SELECT count(*) FROM incidents WHERE tenant_id=%s", TENANT_G) == 1
    assert _n(seeded, "SELECT count(*) FROM incidents WHERE tenant_id=%s", TENANT_A) == 0
    assert _n(seeded, "SELECT count(*) FROM sites WHERE tenant_id=%s", TENANT_A) == 0


def test_grantee_reads_only_its_own_grants(seeded: psycopg.Connection) -> None:
    """La RLS de la tabla de grants: el grantee ve SOLO los suyos; nadie fisgonea los ajenos."""
    _grant(seeded, TENANT_B, target=TENANT_A, metadata=True)
    _grant(seeded, TENANT_A, target=TENANT_G, metadata=True)
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator")
    rows = seeded.execute("SELECT grantee_tenant_id FROM visibility_grants").fetchall()
    assert {str(r[0]) for r in rows} == {TENANT_B}


def test_self_grant_rejected(seeded: psycopg.Connection) -> None:
    """No tiene sentido concederse a sí mismo; el CHECK lo prohíbe."""
    reset(seeded)
    with pytest.raises(psycopg.errors.CheckViolation):
        seeded.execute(
            "INSERT INTO visibility_grants (grantee_tenant_id, target_tenant_id, "
            "can_view_metadata, created_by) VALUES (%s,%s,true,%s)",
            (TENANT_A, TENANT_A, GOV_AGENCY),
        )


def test_empty_grant_rejected(seeded: psycopg.Connection) -> None:
    """Un grant que no concede nada (ni metadatos ni datos) es un error, no un no-op."""
    reset(seeded)
    with pytest.raises(psycopg.errors.CheckViolation):
        seeded.execute(
            "INSERT INTO visibility_grants (grantee_tenant_id, target_tenant_id, created_by) "
            "VALUES (%s,%s,%s)",
            (TENANT_B, TENANT_A, GOV_AGENCY),
        )
