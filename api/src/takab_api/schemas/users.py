"""Modelos de la gestión de usuarios (T-2.54).

Ningún modelo de esta superficie tiene un campo de contraseña, token o secreto —
ni de entrada ni de salida. La clave temporal la genera y entrega Cognito por
correo; la API no la pide, no la ve y no la devuelve. ``test_users`` lo ancla
comparando los campos de ``UserOut`` contra una lista negra de nombres.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: Superficies válidas del token (espejo de ``auth/claims._SURFACES``).
Surface = Literal["web", "mobile", "both"]

#: Forma mínima de un correo. Deliberadamente NO se usa ``EmailStr``: exigiría la
#: dependencia ``email-validator``, y esta tarea no añade ninguna. La validación
#: definitiva la hace Cognito al enviar la invitación — este patrón solo evita el
#: viaje de ida y vuelta por un dedazo evidente.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: Roles que esta pantalla puede asignar. ``occupant`` NO está: vive en un pool
#: aparte con ancla pool→rol (``auth/deps.get_claims``), así que crearlo aquí
#: produciría una cuenta que se autentica y recibe 401 en cada request. Los
#: ocupantes se dan de alta con un código de enrolamiento (T-2.53).
ASSIGNABLE_ROLES: tuple[str, ...] = (
    "takab_superadmin",
    "takab_support",
    "tenant_admin",
    "soc_operator",
    "gov_operator",
    "inspector",
    "building_admin",
    "brigadista",
    "security_guard",
)

#: Roles internos de plataforma: SOLO un ``takab_superadmin`` puede otorgarlos. Sin
#: esta frontera, un ``tenant_admin`` se fabricaría un superadmin y saldría de su
#: propio tenant en un POST — escalada de privilegios de libro.
PLATFORM_ROLES: frozenset[str] = frozenset({"takab_superadmin", "takab_support"})


def _validate_site_scope(value: str) -> str:
    """``"*"`` (todo el tenant), CSV de UUID, o ``""`` (sin alcance declarado).

    Se normaliza y se valida aquí porque este texto acaba siendo el claim
    ``custom:site_scope``, del que dependen el filtro de la consola (T-2.45) y el
    de la app móvil. Un UUID mal tecleado no debe convertirse en "cero sitios" sin
    que nadie se entere.
    """
    raw = value.strip()
    if raw in ("", "*"):
        return raw
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for part in parts:
        try:
            UUID(part)
        except ValueError as exc:
            raise ValueError(f"site_scope: {part!r} no es un site_id") from exc
    # Orden estable y sin duplicados: el claim es una cadena y dos escrituras con
    # los mismos sitios deben producir el mismo texto (diffs de auditoría legibles).
    return ",".join(sorted(set(parts)))


class UserOut(BaseModel):
    """Usuario del directorio. Sin credenciales, por construcción."""

    username: str
    email: str
    tenant_id: str
    role: str
    #: Crudo del claim: ``"*"``, CSV de site_id, o ``""`` (sin alcance declarado).
    site_scope: str
    zone_id: str
    surface: str
    enabled: bool
    #: ``UserStatus`` de Cognito (FORCE_CHANGE_PASSWORD, CONFIRMED, RESET_REQUIRED…).
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserPage(BaseModel):
    items: list[UserOut]
    next_cursor: str | None = None
    #: ``cognito`` o ``simulated``. La consola lo rotula: un directorio simulado no
    #: puede presentarse como el real (regla de oro 7).
    backend: str


class UserCreate(BaseModel):
    """Alta de usuario. La contraseña la genera Cognito y viaja por correo."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    role: str
    site_scope: str = "*"
    zone_id: str = ""
    surface: Surface = "web"
    #: SOLO roles internos TAKAB: un rol de tenant escribe siempre en el suyo.
    tenant_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        raw = v.strip().lower()
        if not _EMAIL_RE.match(raw):
            raise ValueError("email inválido")
        return raw

    @field_validator("role")
    @classmethod
    def _known_role(cls, v: str) -> str:
        if v not in ASSIGNABLE_ROLES:
            raise ValueError(f"rol no asignable desde la consola: {v!r}")
        return v

    @field_validator("site_scope")
    @classmethod
    def _scope(cls, v: str) -> str:
        return _validate_site_scope(v)

    @field_validator("zone_id")
    @classmethod
    def _zone(cls, v: str) -> str:
        raw = v.strip()
        if raw:
            UUID(raw)  # ValueError ⇒ 422
        return raw


class UserUpdate(BaseModel):
    """Edición PARCIAL. ``email`` no se toca: es el identificador de acceso y
    cambiarlo desde aquí rompería el vínculo con la invitación ya enviada."""

    model_config = ConfigDict(extra="forbid")

    role: str | None = None
    site_scope: str | None = None
    zone_id: str | None = None
    surface: Surface | None = None
    enabled: bool | None = None

    @field_validator("role")
    @classmethod
    def _known_role(cls, v: str | None) -> str | None:
        if v is not None and v not in ASSIGNABLE_ROLES:
            raise ValueError(f"rol no asignable desde la consola: {v!r}")
        return v

    @field_validator("site_scope")
    @classmethod
    def _scope(cls, v: str | None) -> str | None:
        return None if v is None else _validate_site_scope(v)

    @field_validator("zone_id")
    @classmethod
    def _zone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        raw = v.strip()
        if raw:
            UUID(raw)
        return raw

    @model_validator(mode="after")
    def _at_least_one_field(self) -> UserUpdate:
        if not self.model_fields_set:
            raise ValueError("PATCH sin campos: envía al menos uno")
        return self


class UserActionOut(BaseModel):
    """Acuse de reset/reenvío. NO trae contraseña ni código: el correo lo lleva."""

    username: str
    action: Literal["password_reset", "invitation_resent"]
    detail: str = Field(
        description="Qué pasó, en lenguaje de operador. Jamás una credencial.",
    )
