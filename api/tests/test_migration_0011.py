"""Migración 0011 (T-1.48): user_profiles, reference_earthquakes y reubicación
de epicentro.

Mismo patrón que test_migration_0005: fixtures ``seeded``/``use`` del conftest
(SET ROLE + GUCs locales a la transacción, rollback al final). Cubre:

- ``app_user_id()``: GUC vacío ⇒ NULL; GUC con sub ⇒ uuid.
- ``user_profiles``: RLS FORCE — lectura tenant-wide, escritura SOLO la fila
  propia (ni otro user_sub ni otro tenant); gov_operator SÍ edita SU nombre
  (excepción documentada: dato personal, no escribe nada ajeno).
- ``reference_earthquakes``: catálogo GLOBAL — lee cualquier rol autenticado,
  takab_app no puede escribir (sin política de escritura).
- ``relocate_incident_epicenter()`` (SECURITY DEFINER, dueño takab_ingest):
  con evento ⇒ UPDATE del epicentro + ``meta.manual_override`` con el previo;
  sin evento ⇒ crea ``EVT-MAN-<md5(incident)[:8]>`` determinista source=manual
  y linkea; guardas de rol, tenant y rango.
"""

from __future__ import annotations

import json
import uuid

import psycopg
import pytest

from conftest import (
    INC_A,
    SITE_A,
    TENANT_A,
    TENANT_B,
    use,
)

U1 = "e1111111-0000-0000-0000-000000000001"
U2 = "e1111111-0000-0000-0000-000000000002"


# ---------------------------------------------------------------- app_user_id()
def test_app_user_id_gucs(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator", user_id=U1)
    assert seeded.execute("SELECT app_user_id()::text").fetchone()[0] == U1
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator", user_id=None)
    assert seeded.execute("SELECT app_user_id()").fetchone()[0] is None


# ---------------------------------------------------------------- user_profiles
def _put_profile(conn: psycopg.Connection, sub: str, tenant: str, name: str) -> None:
    conn.execute(
        "INSERT INTO user_profiles (user_sub, tenant_id, display_name) "
        "VALUES (%s, %s, %s) "
        "ON CONFLICT (user_sub) DO UPDATE SET display_name = EXCLUDED.display_name, "
        "updated_at = now()",
        (sub, tenant, name),
    )


def test_profile_self_write_and_tenant_read(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator", user_id=U1)
    _put_profile(seeded, U1, TENANT_A, "Mauricio B.")
    row = seeded.execute(
        "SELECT display_name FROM user_profiles WHERE user_sub = %s", (U1,)
    ).fetchone()
    assert row[0] == "Mauricio B."

    # Otro usuario del MISMO tenant LEE el perfil (para resolver actores en UI)…
    use(seeded, "takab_app", tenant=TENANT_A, app_role="tenant_admin", user_id=U2)
    assert (
        seeded.execute("SELECT count(*) FROM user_profiles WHERE user_sub = %s", (U1,)).fetchone()[
            0
        ]
        == 1
    )
    # …pero NO puede escribirlo (self-write): el WITH CHECK lo rechaza.
    with pytest.raises(psycopg.errors.Error):
        _put_profile(seeded, U1, TENANT_A, "Impostor")


def test_profile_cross_tenant_invisible_and_unwritable(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator", user_id=U1)
    _put_profile(seeded, U1, TENANT_A, "Mauricio B.")

    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator", user_id=U2)
    assert (
        seeded.execute("SELECT count(*) FROM user_profiles WHERE user_sub = %s", (U1,)).fetchone()[
            0
        ]
        == 0
    )
    # Ni siquiera puede crear una fila "suya" colgada del tenant A.
    with pytest.raises(psycopg.errors.Error):
        _put_profile(seeded, U2, TENANT_A, "Colado")


def test_profile_gov_operator_edits_own_name(seeded: psycopg.Connection) -> None:
    """Excepción documentada al patrón anti-gov: el perfil es dato personal."""
    gov_sub = "e9999999-0000-0000-0000-000000000009"
    use(seeded, "takab_app", tenant=TENANT_A, app_role="gov_operator", user_id=gov_sub)
    _put_profile(seeded, gov_sub, TENANT_A, "Operador PC")
    row = seeded.execute(
        "SELECT display_name FROM user_profiles WHERE user_sub = %s", (gov_sub,)
    ).fetchone()
    assert row[0] == "Operador PC"


# --------------------------------------------------------- reference_earthquakes
def test_catalog_read_any_role_write_denied(seeded: psycopg.Connection) -> None:
    # Siembra como superusuario (los seeds reales van por db/seeds/*.sql).
    seeded.execute(
        "INSERT INTO reference_earthquakes "
        "(catalog_key, origin_time, magnitude, place, epicenter, depth_km, source, source_ref) "
        "VALUES ('TEST-1985', '1985-09-19T13:17:47Z', 8.0, 'Michoacán', "
        "ST_SetSRID(ST_MakePoint(-102.533, 18.19), 4326)::geography, 27.9, 'USGS', 'test')"
        "ON CONFLICT (catalog_key) DO NOTHING"
    )

    for role, tenant in (("soc_operator", TENANT_A), ("building_admin", TENANT_B)):
        use(seeded, "takab_app", tenant=tenant, app_role=role, user_id=U1)
        n = seeded.execute(
            "SELECT count(*) FROM reference_earthquakes WHERE catalog_key = 'TEST-1985'"
        ).fetchone()[0]
        assert n == 1, f"{role} debe leer el catálogo global"

    use(seeded, "takab_app", tenant=TENANT_A, app_role="takab_superadmin", user_id=U1)
    with pytest.raises(psycopg.errors.Error):
        seeded.execute(
            "INSERT INTO reference_earthquakes "
            "(catalog_key, origin_time, magnitude, place, epicenter, source, source_ref) "
            "VALUES ('HACK', now(), 1.0, 'x', "
            "ST_SetSRID(ST_MakePoint(0,0),4326)::geography, 'SSN', 'x')"
        )


# ------------------------------------------------ relocate_incident_epicenter()
_CALL = "SELECT * FROM relocate_incident_epicenter(%s, %s, %s)"


def _event_state(conn: psycopg.Connection, event_id: str) -> tuple[float, float, dict]:
    conn.execute("RESET ROLE")
    row = conn.execute(
        "SELECT ST_X(epicenter::geometry), ST_Y(epicenter::geometry), meta "
        "FROM seismic_events WHERE event_id = %s",
        (event_id,),
    ).fetchone()
    return row[0], row[1], row[2]


def _link_event(conn: psycopg.Connection, incident_id: str, event_id: str) -> None:
    """El seed usa EVT_A como event_uuid (idempotencia), NO como event_id: los
    incidentes sembrados no tienen seismic_event linkeado. Se crea y linkea aquí."""
    conn.execute("RESET ROLE")
    conn.execute(
        "INSERT INTO seismic_events (event_id, source, epicenter, detected_at) "
        "VALUES (%s, 'local_quorum', "
        "ST_SetSRID(ST_MakePoint(-98.20, 19.04), 4326)::geography, now()) "
        "ON CONFLICT (event_id) DO NOTHING",
        (event_id,),
    )
    conn.execute(
        "UPDATE incidents SET event_id = %s WHERE incident_id = %s", (event_id, incident_id)
    )


def test_relocate_with_event_updates_and_keeps_prev(seeded: psycopg.Connection) -> None:
    _link_event(seeded, INC_A, "EVT-T0011-A")
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator", user_id=U1)
    r = seeded.execute(_CALL, (INC_A, -98.50, 18.90)).fetchone()
    event_id, created, prev_lon, prev_lat = r
    assert created is False
    assert event_id == "EVT-T0011-A"
    assert (round(prev_lon, 4), round(prev_lat, 4)) == (-98.20, 19.04)

    lon, lat, meta = _event_state(seeded, event_id)
    assert (round(lon, 4), round(lat, 4)) == (-98.50, 18.90)
    assert "manual_override" in meta
    assert meta["manual_override"]["by"] == U1

    # Segunda reubicación: el previo es el punto anterior.
    use(seeded, "takab_app", tenant=TENANT_A, app_role="tenant_admin", user_id=U2)
    r2 = seeded.execute(_CALL, (INC_A, -98.60, 19.00)).fetchone()
    assert r2[1] is False
    assert (round(r2[2], 4), round(r2[3], 4)) == (-98.50, 18.90)


def test_relocate_without_event_creates_manual_deterministic(
    seeded: psycopg.Connection,
) -> None:
    inc = str(uuid.uuid4())
    seeded.execute("RESET ROLE")
    seeded.execute(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
        "opened_at, severity, state, trigger) "
        "VALUES (%s, gen_random_uuid(), %s, %s, now(), 'critical', 'open', 'sasmex')",
        (inc, TENANT_A, SITE_A),
    )

    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator", user_id=U1)
    r = seeded.execute(_CALL, (inc, -98.21, 19.05)).fetchone()
    event_id, created = r[0], r[1]
    assert created is True
    assert event_id.startswith("EVT-MAN-")
    assert r[2] is None and r[3] is None  # sin epicentro previo

    seeded.execute("RESET ROLE")
    row = seeded.execute(
        "SELECT e.source, e.magnitude, i.event_id FROM seismic_events e "
        "JOIN incidents i ON i.event_id = e.event_id WHERE i.incident_id = %s",
        (inc,),
    ).fetchone()
    assert row[0] == "manual"
    assert row[1] is None  # jamás magnitud inventada
    assert row[2] == event_id

    # Re-POST: mismo evento determinista, ya no "created".
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator", user_id=U1)
    r2 = seeded.execute(_CALL, (inc, -98.22, 19.06)).fetchone()
    assert r2[0] == event_id
    assert r2[1] is False


@pytest.mark.parametrize("role", ["inspector", "gov_operator", "building_admin"])
def test_relocate_role_guard(seeded: psycopg.Connection, role: str) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role=role, user_id=U1)
    with pytest.raises(psycopg.errors.Error, match="rol sin permiso"):
        seeded.execute(_CALL, (INC_A, -98.5, 18.9))


def test_relocate_cross_tenant_is_invisible(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_B, app_role="soc_operator", user_id=U2)
    with pytest.raises(psycopg.errors.Error, match="inexistente"):
        seeded.execute(_CALL, (INC_A, -98.5, 18.9))


def test_relocate_bounds_guard(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator", user_id=U1)
    with pytest.raises(psycopg.errors.Error, match="fuera de rango"):
        seeded.execute(_CALL, (INC_A, 200.0, 18.9))


def test_relocate_audits_nothing_by_itself(seeded: psycopg.Connection) -> None:
    """El audit es del ROUTER (audit.py, single-writer): la función no inserta
    en audit_log — evita doble fila y respeta el contract-test."""
    seeded.execute("RESET ROLE")
    before = seeded.execute("SELECT count(*) FROM audit_log").fetchone()[0]
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator", user_id=U1)
    seeded.execute(_CALL, (INC_A, -98.55, 18.95))
    seeded.execute("RESET ROLE")
    after = seeded.execute("SELECT count(*) FROM audit_log").fetchone()[0]
    assert after == before


def test_relocate_meta_manual_override_shape(seeded: psycopg.Connection) -> None:
    use(seeded, "takab_app", tenant=TENANT_A, app_role="soc_operator", user_id=U1)
    seeded.execute(_CALL, (INC_A, -98.40, 18.80))
    r = seeded.execute(_CALL, (INC_A, -98.41, 18.81)).fetchone()
    _lon, _lat, meta = _event_state(seeded, r[0])
    ov = meta["manual_override"]
    assert set(ov) >= {"prev_lon", "prev_lat", "by", "at"}
    json.dumps(ov)  # serializable
