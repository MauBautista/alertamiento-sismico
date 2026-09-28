"""Modelo de la exportación PDF por incidente (T-1.20 · B5)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ReportOut(BaseModel):
    """Evidencia ``report_pdf`` recién generada + presigned GET de descarga."""

    evidence_id: UUID
    #: [T-7.48] La huella del ARCHIVO, en espejo con `DrillReportOut`.
    #:
    #: ⚠️ **No es la misma que la del contenido**, y confundirlas es el defecto que
    #: `T-7.43` cerró. La de CONTENIDO identifica una exportación concreta y no se
    #: puede comparar entre dos, porque exportar inserta una fila que la siguiente
    #: exportación ya imprime. Ésta es la del objeto que se subió a S3: vive en
    #: `evidence_objects`, la vigila `uq_evidence_incident_sha256`, la tabla es
    #: append-only y el verificador la re-calcula. Es la única de las dos que un
    #: perito puede usar para comprobar que el PDF que tiene en la mano es el que
    #: el sistema emitió.
    #:
    #: Faltaba por descuido, no por decisión: el router ya la calculaba para
    #: insertar la evidencia y la tiraba. Dos documentos hermanos con contratos
    #: distintos.
    sha256: str
    url: str
    expires_in: int


class PostEventReportOut(BaseModel):
    """[T-9.42 · D-48] El informe posterior al evento que el worker genera SOLO.

    Es la fila de `post_event_reports` tal cual. El PDF no viaja aquí: con `ok`,
    `evidence_id` es la evidencia, y se descarga con sesión por la ruta de siempre
    (un enlace prefirmado reenviado abriría el PDF a cualquiera).
    """

    state: Literal["pendiente", "ok", "fallido"]
    #: Lo que llegó PRIMERO: la cabeza firmada, el cierre o el plazo.
    trigger: Literal["firma", "cierre", "plazo"]
    #: `True` = la cabeza de la cadena NO estaba firmada al generarlo. `None`
    #: mientras no hay PDF (no se sabe todavía qué dirá).
    preliminar: bool | None
    variant: str
    evidence_id: UUID | None
    attempts: int
    #: La causa del último fallo (clase y mensaje recortado), tal cual: sólo la ve
    #: personal del cliente con acceso al incidente.
    error: str | None
    created_at: datetime
    updated_at: datetime
