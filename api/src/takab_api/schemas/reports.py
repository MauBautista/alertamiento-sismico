"""Modelo de la exportación PDF por incidente (T-1.20 · B5)."""

from __future__ import annotations

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
