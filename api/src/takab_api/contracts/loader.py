"""Validación de payloads IoT contra los JSON Schema compartidos.

Fuente de verdad: ``shared/schemas/*.schema.json`` (generados del edge y
protegidos anti-drift por ``edge/tests/test_schemas.py``). No se inventan
contratos aquí: solo se cargan y aplican.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

# api/src/takab_api/contracts/loader.py → raíz del repo (parents[4]).
SCHEMAS_DIR = Path(__file__).resolve().parents[4] / "shared" / "schemas"

KINDS = (
    "feature_1s",
    "feature_batch",  # T-1.56: lote de features de tier normal
    "local_event",
    "health_snapshot",
    "actuator_ack",
    "command_ack",
    "backfill_request",
    "waveform_packet",
    "evidence_object",
)

# Topic MQTT → clase de contrato. `takab/status/+` (LWT) no tiene schema en
# archivo; se valida inline en `validate`. `takab/acks` transporta DOS
# contratos (ActuatorAck y CommandAck, T-1.23): ver ``discriminate``.
_TOPIC_KIND = {
    "takab/events": "local_event",
    "takab/features": "feature_1s",
    # T-1.56: el filtro exacto de la regla IoT de takab/features NO matchea el
    # sub-topic (sin comodines); el batch tiene regla propia → la misma cola.
    "takab/features/batch": "feature_batch",
    "takab/health": "health_snapshot",
    "takab/acks": "actuator_ack",
}

_STATUS_VALUES = frozenset({"online", "offline"})


class ContractError(Exception):
    """Payload no conforme al contrato — el consumer lo enruta a DLQ con razón."""


@cache
def _validators() -> dict[str, Draft202012Validator]:
    """Carga los schemas de KINDS una sola vez por proceso."""
    validators: dict[str, Draft202012Validator] = {}
    for kind in KINDS:
        schema = json.loads((SCHEMAS_DIR / f"{kind}.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validators[kind] = Draft202012Validator(schema)
    return validators


def kind_for_topic(topic: str) -> str:
    """Clase de contrato para un topic; desconocido ⇒ ContractError (→ DLQ)."""
    if topic in _TOPIC_KIND:
        return _TOPIC_KIND[topic]
    if topic.startswith("takab/status/") and len(topic) > len("takab/status/"):
        return "status"
    prefix = "takab/backfill/request/"
    if topic.startswith(prefix) and len(topic) > len(prefix):
        return "backfill_request"
    raise ContractError(f"topic sin contrato conocido: {topic!r}")


def discriminate(kind: str, payload: object) -> str:
    """Refina la clase por el discriminador del payload (T-1.23).

    ``takab/acks`` transporta ``ActuatorAck`` (histórico, sin ``kind``) y
    ``CommandAck`` (``kind: "command_ack"``): el campo decide el contrato a
    validar y el handler que lo procesa.
    """
    if (
        kind == "actuator_ack"
        and isinstance(payload, dict)
        and payload.get("kind") == "command_ack"
    ):
        return "command_ack"
    return kind


def validate(kind: str, payload: object) -> None:
    """Valida ``payload`` contra el schema de ``kind``; lanza ContractError."""
    if kind == "status":
        _validate_status(payload)
        return
    validator = _validators().get(kind)
    if validator is None:
        raise ContractError(f"clase de contrato desconocida: {kind!r}")
    error = best_match(validator.iter_errors(payload))
    if error is not None:
        where = "/".join(str(p) for p in error.absolute_path) or "$"
        raise ContractError(f"{kind}: {error.message} (en {where})")


def _validate_status(payload: object) -> None:
    """LWT/status inline: ``{"status": "online"|"offline"}``."""
    if not isinstance(payload, dict):
        raise ContractError(f"status: se esperaba objeto, llegó {type(payload).__name__}")
    value = payload.get("status")
    if value not in _STATUS_VALUES:
        raise ContractError(f"status: valor inválido {value!r} (esperado online|offline)")
