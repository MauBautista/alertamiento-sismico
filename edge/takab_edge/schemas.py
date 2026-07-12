"""Contratos versionados: genera JSON Schema de los modelos Pydantic del edge.

Contracts-first ([ANALISIS-00], blueprint §0.1): la nube y los simuladores validan
contra estos schemas versionados (`shared/schemas/`), generados de los modelos Pydantic
del edge — que son la fuente de verdad. Como los payloads se construyen SIEMPRE como
esos modelos (validados por Pydantic al instanciar), la conformidad es por construcción;
`tests/test_schemas.py` falla si un modelo cambia sin regenerar el schema (anti-drift).

Regenerar: `uv run --directory edge python -m takab_edge.schemas`.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from takab_edge.contracts import (
    ActuatorAck,
    BackfillRequest,
    CommandAck,
    EvidenceObject,
    Feature1s,
    FeatureBatch,
    HealthSnapshot,
    LocalEvent,
    WaveformPacket,
)

#: Versión de los contratos publicados (semver). Súbela ante cambios incompatibles.
#: 1.1.0 (T-1.40): health_snapshot honesto — ntp_offset_s/battery_pct/
#: cert_days_remaining nullable («sin dato»), + mqtt_rtt_ms, ups_status default
#: unknown. Aditivo/relajante: un payload 1.0.0 sigue validando contra 1.1.0.
#: 1.2.0 (T-1.53): health_snapshot + disk_used_pct nullable (panel LAN). ADITIVO:
#: el ingest de la nube ignora la clave (sin columna destino) y un payload 1.1.0
#: sigue validando contra 1.2.0.
#: 1.3.0 (T-1.56): + feature_batch (batcheo escalonado por tier, topic
#: takab/features/batch). ADITIVO: familia nueva; todo payload 1.2.0 sigue
#: validando y la nube acepta feature_1s suelto indefinidamente.
SCHEMA_VERSION = "1.3.0"

#: Familias de payload que cruzan edge→nube (features, eventos, health, ACK).
MODELS: dict[str, type[BaseModel]] = {
    "waveform_packet": WaveformPacket,
    "feature_1s": Feature1s,
    "feature_batch": FeatureBatch,  # T-1.56: lote de tier normal (takab/features/batch)
    "local_event": LocalEvent,
    "health_snapshot": HealthSnapshot,
    "actuator_ack": ActuatorAck,
    "command_ack": CommandAck,  # T-1.23: ack de comando remoto (takab/acks)
    "backfill_request": BackfillRequest,  # T-1.25: solicitud de URL pre-firmada
    "evidence_object": EvidenceObject,
}


def schema_for(name: str, model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://takab.mx/schemas/{name}/v{SCHEMA_VERSION}"
    schema["version"] = SCHEMA_VERSION
    return schema


def output_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "shared" / "schemas"


def generate() -> None:
    out = output_dir()
    out.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        text = json.dumps(schema_for(name, model), indent=2, ensure_ascii=False) + "\n"
        (out / f"{name}.schema.json").write_text(text)
    print(f"generados {len(MODELS)} schemas v{SCHEMA_VERSION} en {out}")


if __name__ == "__main__":
    generate()
