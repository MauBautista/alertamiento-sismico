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


def test_unknown_role_denied() -> None:
    assert allowed_routes("ghost") == []
    assert allowed_actions("ghost") == {
        "ack_incident": False,
        "sign_dictamen": False,
        "export": False,
        "edit_thresholds": False,
        "siren_test": False,
    }


def test_action_anchors_from_rbac() -> None:
    assert allowed_actions("inspector")["sign_dictamen"] is True
    gov = allowed_actions("gov_operator")
    assert gov["export"] is True
    assert gov["ack_incident"] is True
    assert gov["edit_thresholds"] is False
    assert gov["siren_test"] is False
    assert allowed_actions("building_admin")["siren_test"] is True


def test_ack_incident_roles() -> None:
    can_ack = {r for r in RBAC_SECTION_2 if allowed_actions(r)["ack_incident"]}
    assert can_ack == {"takab_superadmin", "tenant_admin", "soc_operator", "gov_operator"}


def test_mobile_only_roles_have_no_actions() -> None:
    for role in MOBILE_ONLY:
        assert allowed_actions(role) == {
            "ack_incident": False,
            "sign_dictamen": False,
            "export": False,
            "edit_thresholds": False,
            "siren_test": False,
        }
