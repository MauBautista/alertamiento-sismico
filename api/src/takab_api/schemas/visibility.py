"""Grants de visibilidad configurable entre clientes (T-1.73).

Solo ``takab_superadmin`` (acción ``manage_visibility``). Un grant AÑADE lectura
cruzada de METADATOS (que existen las estaciones) y/o DATOS en vivo; jamás escritura.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class VisibilityGrantCreate(BaseModel):
    """Alta/actualización (upsert) de un grant. ``target`` es exactamente uno de:
    un cliente específico (``target_tenant_id``) o TODOS (``target_all``)."""

    model_config = ConfigDict(extra="forbid")

    grantee_tenant_id: UUID
    target_tenant_id: UUID | None = None
    target_all: bool = False
    can_view_metadata: bool = False
    can_view_data: bool = False

    @model_validator(mode="after")
    def _shape(self) -> VisibilityGrantCreate:
        # exactamente uno de {target específico, TODOS} (espejo del CHECK vg_target_shape).
        if self.target_all == (self.target_tenant_id is not None):
            raise ValueError("target: da un target_tenant_id O target_all, no ambos ni ninguno")
        if not self.target_all and self.target_tenant_id == self.grantee_tenant_id:
            raise ValueError("un cliente no se concede visibilidad a sí mismo")
        if not (self.can_view_metadata or self.can_view_data):
            raise ValueError("el grant debe conceder metadatos y/o datos")
        return self


class VisibilityGrantOut(BaseModel):
    """Fila de grant. RLS: el grantee ve los suyos; el superadmin todos."""

    grant_id: UUID
    grantee_tenant_id: UUID
    target_tenant_id: UUID | None
    target_all: bool
    can_view_metadata: bool
    can_view_data: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime
