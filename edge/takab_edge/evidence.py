"""evidence — subida idempotente de la ventana miniSEED de un evento a S3.

T-1.11: en un evento confirmado, la ventana miniSEED extraída por `buffer` (T-1.7) se
sube a S3 (URL pre-firmada solicitada por MQTT/API) y se registra como `EvidenceObject`
con `sha256` — **idempotente** (mismo contenido = mismo objeto). El waveform crudo NO se
sube en continuo (regla de oro 9): sólo esta ventana de eventos.

El uploader real (S3 presigned PUT + solicitud de URL por MQTT/API) es **gate AWS**;
`FakeEvidenceUploader` prueba el pipeline extract→sha256→upload sin nube.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Protocol, runtime_checkable

from takab_edge.contracts import EvidenceObject


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evidence_key(event_id: str, digest: str) -> str:
    """Clave S3 determinista → idempotencia por contenido (mismo sha256 = misma clave)."""
    return f"evidence/{event_id}/{digest}.mseed"


@runtime_checkable
class EvidenceUploader(Protocol):
    """Sube la ventana miniSEED y devuelve el `EvidenceObject`. Impl real = S3 (gate AWS)."""

    def upload(self, event_id: str, miniseed: bytes) -> EvidenceObject: ...


class FakeEvidenceUploader:
    """Uploader en memoria para tests: calcula sha256 y es idempotente por contenido."""

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def upload(self, event_id: str, miniseed: bytes) -> EvidenceObject:
        digest = sha256_hex(miniseed)
        self.objects[(event_id, digest)] = miniseed  # re-subir el mismo contenido no duplica
        return EvidenceObject(
            event_id=event_id,
            s3_key=evidence_key(event_id, digest),
            sha256=digest,
            size_bytes=len(miniseed),
        )


def collect_evidence(
    buffer, uploader: EvidenceUploader, event_id: str, start: datetime, end: datetime
) -> EvidenceObject | None:
    """Extrae la ventana [start, end] del `buffer` y la sube. `None` si no hay datos."""
    miniseed = buffer.extract_window(start, end)
    if not miniseed:
        return None
    return uploader.upload(event_id, miniseed)
