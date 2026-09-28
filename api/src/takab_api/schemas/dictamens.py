"""Modelos de dictámenes: cadena de versiones + firma del inspector (T-1.22 · B2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, model_validator

# Estados válidos del CHECK de dictamens.status (db/schema.sql).
DICTAMEN_STATUS = frozenset(
    {"normal_operation", "inhabit_monitor", "restricted", "no_inhabit_inspect"}
)


def rol_de_confirmacion(signature_kind: str | None, basis: object) -> str | None:
    """[F3·r2 · D-43] El ROL de quien confirmó (``basis.confirmacion.rol``), sólo en
    filas ``signature_kind='confirmation'``. UNA copia: la web (``DictamenOut``) y el
    certificado móvil (``MobileDictamenOut``) lo leen de aquí."""
    if signature_kind != "confirmation" or not isinstance(basis, dict):
        return None
    conf = basis.get("confirmacion")
    rol = conf.get("rol") if isinstance(conf, dict) else None
    return rol if isinstance(rol, str) and rol else None


class DictamenOut(BaseModel):
    """Fila de ``dictamens``: ``signed_by`` NULL = preliminar; cadena vía supersedes."""

    dictamen_id: UUID
    tenant_id: UUID
    incident_id: UUID
    status: str
    basis: dict[str, Any]
    signed_by: UUID | None
    supersedes_dictamen_id: UUID | None
    created_at: datetime
    #: [T-9.30 · D-43] QUIÉN firmó: ``inspector`` / ``system`` / ``confirmation``.
    #: NULL = preliminar sin firmar o fila histórica anterior a la 0073. ``signed_by``
    #: sólo dice «firmado»; el rótulo del firmante se lee SIEMPRE de aquí.
    signature_kind: str | None = None
    #: [T-9.30 · D-43] ``verde`` / ``amarillo`` / ``rojo``. NULL en filas históricas.
    band: str | None = None
    #: [F3·r2 · D-43] ROL de quien CONFIRMÓ (``basis.confirmacion.rol``), sólo en filas
    #: ``signature_kind='confirmation'``; None en el resto. La web y el papel lo
    #: rotulan («CONFIRMADO POR …») sin leer la bitácora ni un id interno.
    confirmed_by_role: str | None = None

    @model_validator(mode="after")
    def _rol_de_la_confirmacion(self) -> DictamenOut:
        if self.confirmed_by_role is None:
            self.confirmed_by_role = rol_de_confirmacion(self.signature_kind, self.basis)
        return self


class DictamenList(BaseModel):
    """Cadena de dictámenes de un incidente (más reciente primero)."""

    items: list[DictamenOut]


class DictamenSignIn(BaseModel):
    """Firma manual del inspector: estado del dictamen + notas mínimas (basis)."""

    status: str
    notes: str | None = None
