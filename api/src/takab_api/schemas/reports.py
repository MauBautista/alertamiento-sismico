"""Modelo de la exportación PDF por incidente (T-1.20 · B5)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ReportOut(BaseModel):
    """Evidencia ``report_pdf`` recién generada + presigned GET de descarga."""

    evidence_id: UUID
    url: str
    expires_in: int
