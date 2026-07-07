"""Modelos de respuesta de exportación de evidencia (T-1.22 · B4)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EvidenceObject(BaseModel):
    """Puntero a un objeto de evidencia en S3 (metadatos; el binario vive en S3)."""

    evidence_id: UUID
    incident_id: UUID | None = None
    sensor_id: UUID | None = None
    kind: str
    s3_key: str
    ts_from: datetime | None = None
    ts_to: datetime | None = None
    sha256: str | None = None
    created_at: datetime


class EvidenceList(BaseModel):
    """Lista de evidencias de un incidente (ya filtrada por RLS)."""

    items: list[EvidenceObject]


class PresignedDownload(BaseModel):
    """URL GET presignada de vida corta para descargar un objeto de evidencia."""

    url: str
    expires_in: int
