"""Modelos de GET /me (identidad, T-1.26) y /me/profile (presentación, T-1.48)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator


class MeActions(BaseModel):
    """Acciones sensibles (espejo de ``matrix.ACTIONS``, default-deny).

    Desde T-2.03 incluye la superficie MÓVIL: la app deriva su UI de estos
    booleanos (server-driven), igual que la consola.
    """

    ack_incident: bool
    sign_dictamen: bool
    export: bool
    generate_report: bool
    edit_thresholds: bool
    siren_test: bool
    manage_fleet: bool
    relocate_epicenter: bool
    request_dictamen: bool
    read_audit: bool
    self_test: bool
    drill_start: bool
    manage_tenants: bool
    manage_visibility: bool
    checkin_submit: bool
    roster_read: bool
    damage_report_submit: bool
    evidence_upload: bool
    siren_silence: bool
    manual_activate: bool
    enrollment_manage: bool
    panic_vote: bool
    dictamen_read: bool
    #: [T-2.08] Dashboard táctico 2.1 (RBAC §3): traza BMS + canal live móvil.
    panel_read: bool


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


class ProfileOut(BaseModel):
    """Perfil de presentación del operador (T-1.48). Sin fila ⇒ campos null
    (200, no 404): "sin nombre configurado" es un estado normal, no un error.

    [T-2.03·R4] ``phone``: PII con consentimiento — alimenta la llamada de un
    toque del roster (headcount 2.6)."""

    user_sub: UUID
    display_name: str | None
    phone: str | None
    updated_at: datetime | None


class ProfilePutIn(BaseModel):
    """Cuerpo de PUT /me/profile: el nombre se normaliza (trim + colapso de
    espacios internos) ANTES de validar longitud — "   " no es un nombre.

    [T-2.03·R4] ``phone`` opcional (E.164 laxo): proporcionarlo ES el
    consentimiento de aparecer en el roster; ``null`` lo retira."""

    display_name: str
    phone: str | None = None

    @field_validator("display_name")
    @classmethod
    def _normalize(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v).strip()
        if not v:
            raise ValueError("display_name vacío")
        if len(v) > 80:
            raise ValueError("display_name supera 80 caracteres")
        return v

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = re.sub(r"[\s().-]+", "", v.strip())
        if not v:
            return None
        if not re.fullmatch(r"\+?[0-9]{7,15}", v):
            raise ValueError("phone inválido (7-15 dígitos, prefijo + opcional)")
        return v
