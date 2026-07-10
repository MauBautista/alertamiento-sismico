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
- ``export``        ← Triage ∈ {Total, "Lectura + export"}: DESCARGAR evidencia ya
  archivada (miniSEED/PDF existente).
- ``generate_report`` ← CREAR evidencia nueva (PDF de dictamen) en el tenant. Es un
  subconjunto estricto de ``export``: gov_operator descarga evidencia de tenants
  ``gov_shared`` pero no escribe filas en un tenant ajeno. Separarla de ``export``
  evita que la consola pinte a gov_operator un botón que siempre daría 403
  (regla de oro 7).
- ``edit_thresholds`` ← administra umbrales (§1/§2: tenant_admin) + dueño de plataforma.
- ``siren_test``    ← Dash Edificio == Total (dueño del sitio); §2 lo concede
  explícitamente a building_admin y lo niega a gov_operator.
- ``manage_fleet``  ← alta/edición/retiro de sitios, gabinetes y sensores (T-1.32).
  [DECISION 2026-07-09] §2 da "Total" en Flota Edge a ``takab_support``, pero aquí NO
  recibe la acción: soporte lee la flota, no mueve la geometría de un sitio ajeno.
  Gana el código sobre el documento; la divergencia queda anotada en RBAC-TAKAB.md §2.
  Escribir la ubicación de una estación reencuadra el quórum (la ventana de asociación
  depende de la distancia entre sitios): es una acción de dueño, no de soporte.

Esta tabla es la fuente ÚNICA: ``routers/dictamens`` deriva de ella ``SIGN_ROLES``,
``routers/exports`` deriva ``EXPORT_ROLES`` y ``routers/reports`` deriva
``REPORT_ROLES``. Ningún router vuelve a listar roles a mano.
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
# [T-1.48] ``relocate_epicenter``/``request_dictamen`` — extensiones de la
# Consola C4I (§2 no las lista; anotadas en RBAC-TAKAB.md §2 como divergencia
# documentada): reubicar el epicentro reescribe un dato de RED compartido
# (acto de operador del tenant, jamás de gov/inspector) y solicitar dictamen
# inserta en el timeline (la RLS ``actions_insert`` excluye a gov_operator, así
# que concedérsela pintaría un botón que siempre da 403 — regla de oro 7).
ACTIONS: tuple[str, ...] = (
    "ack_incident",
    "sign_dictamen",
    "export",
    "generate_report",
    "edit_thresholds",
    "siren_test",
    "manage_fleet",
    "relocate_epicenter",
    "request_dictamen",
)


def _actions(
    *,
    ack_incident: bool = False,
    sign_dictamen: bool = False,
    export: bool = False,
    generate_report: bool = False,
    edit_thresholds: bool = False,
    siren_test: bool = False,
    manage_fleet: bool = False,
    relocate_epicenter: bool = False,
    request_dictamen: bool = False,
) -> dict[str, bool]:
    return {
        "ack_incident": ack_incident,
        "sign_dictamen": sign_dictamen,
        "export": export,
        "generate_report": generate_report,
        "edit_thresholds": edit_thresholds,
        "siren_test": siren_test,
        "manage_fleet": manage_fleet,
        "relocate_epicenter": relocate_epicenter,
        "request_dictamen": request_dictamen,
    }


ROLE_ACTION_MATRIX: dict[str, dict[str, bool]] = {
    "takab_superadmin": _actions(
        ack_incident=True,
        export=True,
        generate_report=True,
        edit_thresholds=True,
        siren_test=True,
        manage_fleet=True,
        relocate_epicenter=True,
        request_dictamen=True,
    ),
    "takab_support": _actions(),
    "tenant_admin": _actions(
        ack_incident=True,
        edit_thresholds=True,
        siren_test=True,
        manage_fleet=True,
        relocate_epicenter=True,
        request_dictamen=True,
    ),
    "soc_operator": _actions(ack_incident=True, relocate_epicenter=True, request_dictamen=True),
    # Descarga evidencia de tenants gov_shared, pero no la GENERA en tenant ajeno.
    "gov_operator": _actions(ack_incident=True, export=True),
    "inspector": _actions(sign_dictamen=True, export=True, generate_report=True),
    "building_admin": _actions(siren_test=True),
    "brigadista": _actions(),
    "security_guard": _actions(),
    "occupant": _actions(),
}


def roles_with_action(action: str) -> tuple[str, ...]:
    """Roles con ``action`` concedida, ordenados. Fuente única para los routers."""
    return tuple(sorted(r for r, acts in ROLE_ACTION_MATRIX.items() if acts.get(action)))


def allowed_routes(role: str) -> list[str]:
    """Rutas web del rol, en ``ROUTE_ORDER``. Rol desconocido/móvil-only ⇒ []."""
    granted = ROLE_ROUTE_MATRIX.get(role, frozenset())
    return [route for route in ROUTE_ORDER if route in granted]


def allowed_actions(role: str) -> dict[str, bool]:
    """Acciones booleanas del rol. Rol desconocido ⇒ todo False (default-deny)."""
    base = dict.fromkeys(ACTIONS, False)
    base.update(ROLE_ACTION_MATRIX.get(role, {}))
    return base
