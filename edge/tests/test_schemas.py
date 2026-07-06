"""schemas — anti-drift: los JSON Schema comprometidos coinciden con los modelos."""

from __future__ import annotations

import json

import pytest
from takab_edge.schemas import MODELS, output_dir, schema_for


@pytest.mark.parametrize("name", list(MODELS))
def test_committed_schema_matches_model(name):
    model = MODELS[name]
    committed = json.loads((output_dir() / f"{name}.schema.json").read_text())
    current = schema_for(name, model)
    assert committed == current, (
        f"'{name}' cambió sin regenerar el schema. "
        f"Corre: uv run --directory edge python -m takab_edge.schemas"
    )


def test_all_contract_families_are_exported():
    # features / eventos / health / ACK / waveform — los payloads que cruzan edge→nube.
    assert set(MODELS) == {
        "waveform_packet",
        "feature_1s",
        "local_event",
        "health_snapshot",
        "actuator_ack",
        "evidence_object",
    }
