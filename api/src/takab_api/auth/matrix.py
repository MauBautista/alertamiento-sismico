"""Matriz de acceso web como DATO — espejo programático de RBAC-TAKAB.md §2/§7.

Fuente única de verdad para rutas y acciones por rol. Si el documento cambia,
cambia aquí; ``test_matrix`` compara esta tabla contra una copia a mano de §2 y
falla ante cualquier divergencia.

Rutas (columnas §2 → ruta §7): Consola C4I=/console, Flota Edge=/fleet,
Triage=/triage, Multi-Tenant=/tenants, Dash Edificio=/building. Una ruta está
concedida si la celda de §2 no es "—".

Divergencia doc conocida: §7 lista ``building_admin`` en ``/fleet`` pero §2 le da
"—" en Flota Edge. Seguimos §2 (celda a celda, como el test) → building_admin
NO tiene /fleet. Pendiente de resolver en el documento.

Acciones (derivadas de §2 + notas §4):
- ``ack_incident``  ← Consola C4I ∈ {Total, "Lectura + ack"}.
- ``sign_dictamen`` ← Triage dice "firma dictamen" (acto profesional del inspector;
  no se deriva del "Total" de superadmin — decisión de seguridad, ver notas).
- ``export``        ← Triage ∈ {Total, "Lectura + export"}.
- ``edit_thresholds`` ← administra umbrales (§1/§2: tenant_admin) + dueño de plataforma.
- ``siren_test``    ← Dash Edificio == Total (dueño del sitio); §2 lo concede
  explícitamente a building_admin y lo niega a gov_operator.
"""

from __future__ import annotations

CONSOLE = "/console"
FLEET = "/fleet"
TRIAGE = "/triage"
TENANTS = "/tenants"
BUILDING = "/building"

# Orden estable de rutas para allowed_routes().
ROUTE_ORDER: tuple[str, ...] = (CONSOLE, FLEET, TRIAGE, TENANTS, BUILDING)

# Rutas concedidas por rol (espejo de §2, celda ≠ "—").
ROLE_ROUTE_MATRIX: dict[str, frozenset[str]] = {
    "takab_superadmin": frozenset({CONSOLE, FLEET, TRIAGE, TENANTS, BUILDING}),
    "takab_support": frozenset({CONSOLE, FLEET, TRIAGE, TENANTS, BUILDING}),
    "tenant_admin": frozenset({CONSOLE, FLEET, TRIAGE, TENANTS, BUILDING}),
    "soc_operator": frozenset({CONSOLE, FLEET, TRIAGE, BUILDING}),
    "gov_operator": frozenset({CONSOLE, FLEET, TRIAGE, BUILDING}),
    "inspector": frozenset({CONSOLE, TRIAGE, BUILDING}),
    "building_admin": frozenset({CONSOLE, TRIAGE, BUILDING}),
    "brigadista": frozenset(),
    "security_guard": frozenset(),
    "occupant": frozenset(),
}

# Acciones sensibles del SOC web.
ACTIONS: tuple[str, ...] = (
    "ack_incident",
    "sign_dictamen",
    "export",
    "edit_thresholds",
    "siren_test",
)


def _actions(
    *,
    ack_incident: bool = False,
    sign_dictamen: bool = False,
    export: bool = False,
    edit_thresholds: bool = False,
    siren_test: bool = False,
) -> dict[str, bool]:
    return {
        "ack_incident": ack_incident,
        "sign_dictamen": sign_dictamen,
        "export": export,
        "edit_thresholds": edit_thresholds,
        "siren_test": siren_test,
    }


ROLE_ACTION_MATRIX: dict[str, dict[str, bool]] = {
    "takab_superadmin": _actions(
        ack_incident=True, export=True, edit_thresholds=True, siren_test=True
    ),
    "takab_support": _actions(),
    "tenant_admin": _actions(ack_incident=True, edit_thresholds=True, siren_test=True),
    "soc_operator": _actions(ack_incident=True),
    "gov_operator": _actions(ack_incident=True, export=True),
    "inspector": _actions(sign_dictamen=True, export=True),
    "building_admin": _actions(siren_test=True),
    "brigadista": _actions(),
    "security_guard": _actions(),
    "occupant": _actions(),
}


def allowed_routes(role: str) -> list[str]:
    """Rutas web del rol, en ``ROUTE_ORDER``. Rol desconocido/móvil-only ⇒ []."""
    granted = ROLE_ROUTE_MATRIX.get(role, frozenset())
    return [route for route in ROUTE_ORDER if route in granted]


def allowed_actions(role: str) -> dict[str, bool]:
    """Acciones booleanas del rol. Rol desconocido ⇒ todo False (default-deny)."""
    base = dict.fromkeys(ACTIONS, False)
    base.update(ROLE_ACTION_MATRIX.get(role, {}))
    return base
