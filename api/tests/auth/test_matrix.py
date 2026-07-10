"""La matriz de código debe ser idéntica a RBAC-TAKAB.md §2 (copia a mano).

Si el código y el documento divergen, este test FALLA. La tabla de abajo se
transcribió celda por celda de §2: True = la celda NO es "—".
"""

from __future__ import annotations

from takab_api.auth.matrix import (
    BUILDING,
    CONSOLE,
    FLEET,
    ROLE_ROUTE_MATRIX,
    TENANTS,
    TRIAGE,
    allowed_actions,
    allowed_routes,
)

# Columnas §2 → (Consola C4I, Flota Edge, Triage, Multi-Tenant, Dash Edificio).
COLS = (CONSOLE, FLEET, TRIAGE, TENANTS, BUILDING)

# Copiado A MANO de RBAC-TAKAB.md §2 (matriz web), celda por celda.
RBAC_SECTION_2 = {
    #                    console fleet triage tenants building
    "takab_superadmin": (True, True, True, True, True),
    "takab_support": (True, True, True, True, True),
    "tenant_admin": (True, True, True, True, True),
    "soc_operator": (True, True, True, False, True),
    "gov_operator": (True, True, True, False, True),
    "inspector": (True, False, True, False, True),
    "building_admin": (True, False, True, False, True),
    "brigadista": (False, False, False, False, False),
    "security_guard": (False, False, False, False, False),
    "occupant": (False, False, False, False, False),
}

MOBILE_ONLY = ("brigadista", "security_guard", "occupant")


def _expected_routes(role: str) -> list[str]:
    return [col for col, granted in zip(COLS, RBAC_SECTION_2[role], strict=True) if granted]


def test_route_matrix_matches_rbac_section_2() -> None:
    assert set(ROLE_ROUTE_MATRIX) == set(RBAC_SECTION_2)
    for role in RBAC_SECTION_2:
        expected = _expected_routes(role)
        assert allowed_routes(role) == expected, role
        assert ROLE_ROUTE_MATRIX[role] == frozenset(expected), role


def test_mobile_only_roles_have_no_web_routes() -> None:
    for role in MOBILE_ONLY:
        assert allowed_routes(role) == []


def test_allowed_routes_are_ordered() -> None:
    # Superadmin cubre todas: el orden debe ser el de COLS.
    assert allowed_routes("takab_superadmin") == list(COLS)


DENY_ALL = {
    "ack_incident": False,
    "sign_dictamen": False,
    "export": False,
    "generate_report": False,
    "edit_thresholds": False,
    "siren_test": False,
    "manage_fleet": False,
    "relocate_epicenter": False,
    "request_dictamen": False,
}


def test_unknown_role_denied() -> None:
    assert allowed_routes("ghost") == []
    assert allowed_actions("ghost") == DENY_ALL


def test_action_anchors_from_rbac() -> None:
    assert allowed_actions("inspector")["sign_dictamen"] is True
    gov = allowed_actions("gov_operator")
    assert gov["export"] is True
    assert gov["ack_incident"] is True
    assert gov["edit_thresholds"] is False
    assert gov["siren_test"] is False
    assert allowed_actions("building_admin")["siren_test"] is True


def test_sign_dictamen_is_inspector_only() -> None:
    """Acto profesional del inspector: el "Total" de §2 NO lo concede (decisión
    de seguridad documentada en matrix.py). ``routers/dictamens`` deriva de aquí."""
    can_sign = {r for r in RBAC_SECTION_2 if allowed_actions(r)["sign_dictamen"]}
    assert can_sign == {"inspector"}


def test_generate_report_is_distinct_from_export() -> None:
    """``export`` = descargar evidencia ya archivada (miniSEED). ``generate_report``
    = CREAR evidencia nueva (PDF) en el tenant. gov_operator lee y descarga
    evidencia ajena (gov_shared) pero no escribe filas en un tenant que no es suyo,
    así que tiene export sin generate_report. Un solo flag para ambos haría que la
    consola le pintara un botón que siempre da 403 (regla de oro 7)."""
    can_export = {r for r in RBAC_SECTION_2 if allowed_actions(r)["export"]}
    can_report = {r for r in RBAC_SECTION_2 if allowed_actions(r)["generate_report"]}
    assert can_export == {"takab_superadmin", "gov_operator", "inspector"}
    assert can_report == {"takab_superadmin", "inspector"}
    assert can_report < can_export


def test_manage_fleet_excludes_takab_support() -> None:
    """§2 da "Total" a ``takab_support`` en Flota Edge, pero el código NO le concede
    ``manage_fleet`` ([DECISION 2026-07-09], documentada en matrix.py y RBAC-TAKAB.md).

    Mover la ubicación de una estación reencuadra la ventana de asociación del quórum
    (``|Δt| ≤ dist/v_P + margen``): es un acto de dueño del tenant, no de soporte.
    """
    can_manage = {r for r in RBAC_SECTION_2 if allowed_actions(r)["manage_fleet"]}
    assert can_manage == {"takab_superadmin", "tenant_admin"}
    assert allowed_actions("takab_support")["manage_fleet"] is False
    # Y sigue viendo /fleet: la divergencia es de escritura, no de lectura.
    assert FLEET in ROLE_ROUTE_MATRIX["takab_support"]


def test_ack_incident_roles() -> None:
    can_ack = {r for r in RBAC_SECTION_2 if allowed_actions(r)["ack_incident"]}
    assert can_ack == {"takab_superadmin", "tenant_admin", "soc_operator", "gov_operator"}


def test_relocate_epicenter_is_tenant_operator_action() -> None:
    """[T-1.48] Reubicar el epicentro reescribe un dato de RED compartido
    (seismic_events): acto de operador del tenant + dueño de plataforma. Ni gov
    (solo lectura+acuse) ni inspector (juzga, no edita la física del evento)."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["relocate_epicenter"]}
    assert can == {"takab_superadmin", "tenant_admin", "soc_operator"}


def test_request_dictamen_excludes_gov() -> None:
    """[T-1.48] ``ack_incident`` menos gov: la RLS ``actions_insert`` impide a
    gov_operator insertar en incident_actions — concederle la acción pintaría
    un botón que siempre da 403 (regla de oro 7). Divergencia anotada en
    RBAC-TAKAB.md §2."""
    can = {r for r in RBAC_SECTION_2 if allowed_actions(r)["request_dictamen"]}
    assert can == {"takab_superadmin", "tenant_admin", "soc_operator"}


def test_mobile_only_roles_have_no_actions() -> None:
    for role in MOBILE_ONLY:
        assert allowed_actions(role) == DENY_ALL
