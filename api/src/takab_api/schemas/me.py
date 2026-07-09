"""Modelo de respuesta de GET /me — identidad para los guards del SOC web (T-1.26)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MeActions(BaseModel):
    """Acciones sensibles del SOC web (espejo de ``matrix.ACTIONS``, default-deny)."""

    ack_incident: bool
    sign_dictamen: bool
    export: bool
    generate_report: bool
    edit_thresholds: bool
    siren_test: bool
    manage_fleet: bool


class MeResponse(BaseModel):
    """Perfil del portador del token: qué ve y qué puede hacer (RBAC §2/§7).

    ``site_scope``: ``"*"`` = todo el tenant; lista ordenada de sitios en otro
    caso (vacía = default-deny). Rol móvil-only ⇒ ``allowed_routes`` vacías.
    """

    sub: str
    tenant_id: str
    role: str
    site_scope: Literal["*"] | list[str]
    surface: str
    allowed_routes: list[str]
    allowed_actions: MeActions
