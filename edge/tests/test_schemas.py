"""schemas — anti-drift: los JSON Schema comprometidos coinciden con los modelos."""

from __future__ import annotations

import json

import pytest
from takab_edge.schemas import (
    HUELLA_POR_VERSION,
    MODELS,
    SCHEMA_VERSION,
    huella_del_contenido,
    output_dir,
    schema_for,
)


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
    # features / eventos / health / ACKs / waveform — los payloads que cruzan edge→nube.
    assert set(MODELS) == {
        "waveform_packet",
        "feature_1s",
        "feature_batch",  # T-1.56: lote de tier normal
        "local_event",
        "health_snapshot",
        "actuator_ack",
        "command_ack",
        "backfill_request",
        "evidence_object",
        "lora_secondary_state",
        "actuation_record",  # T-2.33: gabinete secundario LoRa
    }


# --------------------------------------------------- la versión, atada al contenido


def test_la_version_declarada_tiene_huella() -> None:
    assert SCHEMA_VERSION in HUELLA_POR_VERSION, (
        f"`SCHEMA_VERSION` vale {SCHEMA_VERSION} y no hay huella para esa versión. "
        "Al subirla, añade su entrada en `HUELLA_POR_VERSION` (y su línea en el "
        "registro de cambios de `schemas.py`)."
    )


def test_un_contrato_no_puede_cambiar_SIN_subir_la_version() -> None:
    """La guarda del desfase que mandó un latido a la cola de mensajes muertos.

    El 2026-09-10 el gabinete emitía `packet_loss_pct: null` y la nube servía el
    esquema que aún lo exigía `number`. Los dos ficheros declaraban `1.14.0`, así
    que **no había forma de notar el desfase**: la relajación (`d67d079`, T-5.24)
    no subió la versión, y tampoco lo hicieron los otros dos cambios que viajaron
    bajo ese número. La versión es un literal que nadie estaba obligado a tocar.

    Esto la obliga: la huella se calcula del contenido de los 11 esquemas —sin
    `$id` ni `version`, para que subir el número no la «arregle» sola—, así que
    tocar cualquier contrato pone esto en rojo hasta que alguien suba
    `SCHEMA_VERSION` y declare la huella nueva. Que es, exactamente, el momento en
    que se escribe qué cambió y en qué sentido rompe.
    """
    esperada = HUELLA_POR_VERSION.get(SCHEMA_VERSION)
    assert huella_del_contenido() == esperada, (
        f"los contratos cambiaron y `SCHEMA_VERSION` sigue en {SCHEMA_VERSION}.\n"
        "  Sube la versión, añade su huella en `HUELLA_POR_VERSION` y anota el cambio "
        "en el registro de `schemas.py` diciendo si es ADITIVO o RELAJACIÓN — y, si es "
        "relajación, que el sentido peligroso es un consumidor viejo con un emisor "
        "nuevo.\n"
        "  Comando: uv run --directory edge python -c "
        "'from takab_edge.schemas import huella_del_contenido; print(huella_del_contenido())'"
    )


def test_la_huella_IGNORA_la_version_o_seria_circular() -> None:
    """Si `$id`/`version` entraran en la huella, cualquier bump la validaría sola
    y la guarda de arriba no mediría nada."""
    import json as _json

    cuerpo = schema_for("health_snapshot", MODELS["health_snapshot"])
    assert cuerpo["version"] == SCHEMA_VERSION
    sin_version = _json.dumps(
        {k: v for k, v in cuerpo.items() if k not in ("$id", "version")}, sort_keys=True
    )
    assert SCHEMA_VERSION not in sin_version
