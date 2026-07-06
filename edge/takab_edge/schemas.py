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
    EvidenceObject,
    Feature1s,
    HealthSnapshot,
    LocalEvent,
    WaveformPacket,
)

#: Versión de los contratos publicados (semver). Súbela ante cambios incompatibles.
SCHEMA_VERSION = "1.0.0"

#: Familias de payload que cruzan edge→nube (features, eventos, health, ACK).
MODELS: dict[str, type[BaseModel]] = {
    "waveform_packet": WaveformPacket,
    "feature_1s": Feature1s,
    "local_event": LocalEvent,
    "health_snapshot": HealthSnapshot,
    "actuator_ack": ActuatorAck,
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
