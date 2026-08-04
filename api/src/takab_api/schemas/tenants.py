"""Modelos del catálogo de tenants: lectura (T-1.22 · B1), alta (T-1.72) y
edición (T-2.51).

``row_version`` es el ``xmin`` de la fila — mismo testigo de concurrencia
optimista que ``sites``/``gateways``. El cliente lo devuelve como
``base_row_version`` al editar: si otro superadmin guardó entre medias, la API
responde 409 en vez de revertir en silencio la visibilidad de un cliente.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Espejo de los CHECK del DDL (db/schema.sql:74-75).
TenantStatus = Literal["trial", "active", "suspended"]
TenantVisibility = Literal["private", "gov_shared"]


class TenantOut(BaseModel):
    """Fila de tenant. RLS decide qué filas ve cada rol (ver router/tenants)."""

    tenant_id: UUID
    code: str
    name: str
    isolation_mode: str
    vertical: str | None = None
    visibility: str
    status: str
    plan_code: str
    row_version: str
    created_at: datetime


class TenantCreate(BaseModel):
    """Alta de un cliente (T-1.72). Solo ``takab_superadmin`` (acción ``manage_tenants``).

    ``visibility`` y ``status`` NO se aceptan aquí: nacen con los defaults del schema
    (``private``/``active``). Compartir con gobierno (``gov_shared``) es una decisión
    aparte; la visibilidad configurable entre clientes vive en T-1.73.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    vertical: str | None = Field(default=None, max_length=64)
    plan_code: str = Field(default="mvp", min_length=1, max_length=32)
    isolation_mode: Literal["logical", "dedicated"] = "logical"


#: Campos que ``PATCH /tenants/{id}`` puede escribir. Allowlist explícita: el SET
#: del UPDATE se arma con ella, así que nada que no esté aquí llega al SQL.
TENANT_PATCH_FIELDS: tuple[str, ...] = ("name", "vertical", "plan_code", "status", "visibility")


class TenantUpdate(BaseModel):
    """Edición PARCIAL de un cliente (T-2.51). Solo ``takab_superadmin``.

    Es un PATCH, no un PUT: la pantalla Multi-Tenant edita una ficha campo a campo y
    un reemplazo total obligaría a reenviar valores que el operador no tocó (y a
    pisarlos si otro admin los cambió mientras el formulario estaba abierto).

    ``code`` NO es editable: es la llave que TAKAB entrega fuera de banda y que
    aparece en runbooks, tickets y en el ``edge.env`` de los gabinetes. ``tenant_id``
    tampoco (``extra='forbid'`` los rechaza con 422). ``isolation_mode`` queda fuera
    a propósito: pasar de ``logical`` a ``dedicated`` es una migración de datos, no
    una casilla — anunciarlo aquí prometería un aislamiento que nadie ejecutó.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    vertical: str | None = Field(default=None, max_length=64)
    plan_code: str | None = Field(default=None, min_length=1, max_length=32)
    status: TenantStatus | None = None
    visibility: TenantVisibility | None = None
    #: ``xmin`` leído por el cliente; ausente ⇒ sin guardia de concurrencia.
    base_row_version: str | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> TenantUpdate:
        if not (set(self.model_fields_set) & set(TENANT_PATCH_FIELDS)):
            raise ValueError(
                "PATCH sin campos: envía al menos uno de " + ", ".join(TENANT_PATCH_FIELDS)
            )
        return self

    def changes(self) -> dict[str, str | None]:
        """Solo los campos REALMENTE enviados (``None`` explícito incluido)."""
        return {f: getattr(self, f) for f in TENANT_PATCH_FIELDS if f in self.model_fields_set}
