"""Loader de contratos (T-1.17): validación contra los schemas reales + meta_*.

Los payloads válidos se CONSTRUYEN leyendo cada schema comprometido en
``shared/schemas/`` (required + tipos + enums) — cero copias petrificadas.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from takab_api.contracts import ContractError, Meta, kind_for_topic, split_meta, validate
from takab_api.contracts.loader import KINDS, SCHEMAS_DIR

REPO_ROOT = Path(__file__).resolve().parents[2]


def _schema(kind: str) -> dict:
    return json.loads((SCHEMAS_DIR / f"{kind}.schema.json").read_text())


def _value_for(prop: dict, defs: dict) -> object:
    """Valor mínimo válido para una propiedad del schema (recursivo)."""
    if "$ref" in prop:
        return _value_for(defs[prop["$ref"].rsplit("/", 1)[-1]], defs)
    if "enum" in prop:
        return prop["enum"][0]
    match prop.get("type"):
        case "string":
            if prop.get("format") == "date-time":
                return "2026-07-06T10:00:00+00:00"
            return "x"
        case "number":
            return 0.5
        case "integer":
            return 7
        case "boolean":
            return True
        case "array":
            return [_value_for(prop["items"], defs)]
        case "object":
            return _minimal_instance(prop, defs)
    raise AssertionError(f"tipo de schema no soportado: {prop}")


def _minimal_instance(schema: dict, defs: dict) -> dict:
    return {key: _value_for(schema["properties"][key], defs) for key in schema.get("required", [])}


def test_schemas_dir_points_to_shared() -> None:
    assert SCHEMAS_DIR == REPO_ROOT / "shared" / "schemas"
    assert SCHEMAS_DIR.is_dir()


@pytest.mark.parametrize("kind", KINDS)
def test_valid_payload_from_real_schema_passes(kind: str) -> None:
    schema = _schema(kind)
    payload = _minimal_instance(schema, schema.get("$defs", {}))
    validate(kind, payload)  # no lanza


@pytest.mark.parametrize("kind", KINDS)
def test_missing_required_rejected_with_reason(kind: str) -> None:
    schema = _schema(kind)
    payload = _minimal_instance(schema, schema.get("$defs", {}))
    dropped = schema["required"][0]
    del payload[dropped]
    with pytest.raises(ContractError, match=dropped):
        validate(kind, payload)


def test_wrong_type_rejected_with_reason() -> None:
    schema = _schema("feature_1s")
    payload = _minimal_instance(schema, schema.get("$defs", {}))
    payload["pga"] = "alto"  # number esperado
    with pytest.raises(ContractError, match="pga"):
        validate("feature_1s", payload)


def test_unknown_kind_rejected() -> None:
    with pytest.raises(ContractError, match="desconocida"):
        validate("no_existe", {})


# --- topic → kind (mapa total, incluyendo status/+) ------------------------


@pytest.mark.parametrize(
    ("topic", "kind"),
    [
        ("takab/events", "local_event"),
        ("takab/features", "feature_1s"),
        ("takab/features/batch", "feature_batch"),  # T-1.56
        ("takab/health", "health_snapshot"),
        ("takab/acks", "actuator_ack"),
        ("takab/status/gw-x", "status"),
        ("takab/status/gw-dev-0001", "status"),
    ],
)
def test_kind_for_topic_total(topic: str, kind: str) -> None:
    assert kind_for_topic(topic) == kind


def test_feature_batch_rechaza_lote_vacio_y_features_invalidas() -> None:
    """T-1.56: minItems=1 y cada elemento valida como Feature1s completo."""
    schema = _schema("feature_batch")
    payload = _minimal_instance(schema, schema.get("$defs", {}))
    payload["features"] = []
    with pytest.raises(ContractError, match="features"):
        validate("feature_batch", payload)
    payload["features"] = [{"station": "R4F74"}]  # sin channel/window_start/pga…
    with pytest.raises(ContractError):
        validate("feature_batch", payload)


@pytest.mark.parametrize("topic", ["takab/nope", "otra/cosa", "takab/status/", ""])
def test_kind_for_topic_unknown_raises(topic: str) -> None:
    with pytest.raises(ContractError):
        kind_for_topic(topic)


# --- status/LWT inline ------------------------------------------------------


@pytest.mark.parametrize("value", ["online", "offline"])
def test_status_inline_valid(value: str) -> None:
    validate("status", {"status": value})


@pytest.mark.parametrize("payload", [{"status": "degraded"}, {}, ["online"], "online"])
def test_status_inline_invalid(payload: object) -> None:
    with pytest.raises(ContractError, match="status"):
        validate("status", payload)


# --- split_meta -------------------------------------------------------------


def test_split_meta_separates_enrichment() -> None:
    ts_ms = 1751791800123  # epoch ms
    raw = {
        "gateway_id": "gw-dev-0001",
        "meta_principal": "gw-dev-0001",
        "meta_topic": "takab/health",
        "meta_ts_iot": ts_ms,
    }
    payload, meta = split_meta(raw)
    assert payload == {"gateway_id": "gw-dev-0001"}
    assert "meta_principal" not in payload
    assert meta.principal == "gw-dev-0001"
    assert meta.topic == "takab/health"
    assert meta.ts_iot == datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
    assert meta.ts_iot.tzinfo is UTC


def test_split_meta_tolerates_absent_meta() -> None:
    raw = {"status": "online"}
    payload, meta = split_meta(raw)
    assert payload == {"status": "online"}
    assert meta == Meta(principal=None, topic=None, ts_iot=None)


def test_split_meta_does_not_mutate_input() -> None:
    raw = {"a": 1, "meta_topic": "takab/acks"}
    split_meta(raw)
    assert raw == {"a": 1, "meta_topic": "takab/acks"}


# Contratos que el edge GENERA pero la nube no ingiere por sí solos, con su razón.
# La lista es corta a propósito: si crece, la pregunta es por qué el gabinete
# publica algo que nadie lee.
_SIN_INGESTA = {
    # --- NUBE → GABINETE: los publica la nube y los consume el edge. Entran por
    # `edge/takab_edge/dispatch/`, no por esta cola.
    "command",  # T-1.23: orden firmada a un actuador
    "config_update",  # T-1.28: empujón de configuración firmado
    "backfill_grant",  # T-1.25: URL pre-firmada de subida
    # --- GABINETE → ..., pero no por MQTT ni por su propio topic:
    # El waveform crudo NO se sube en continuo (regla de oro 9): el miniSEED viaja
    # a S3 por URL pre-firmada. El schema existe para el panel local.
    "waveform_packet",
    # T-2.33: estado de gabinete secundario LoRa. Lo consume el gabinete PRINCIPAL
    # por radio y viaja a la nube dentro de su `HealthSnapshot`, no por su topic.
    "lora_secondary_state",
}


def test_TODO_schema_compartido_tiene_su_clase_de_contrato() -> None:
    """[T-7.30] Un schema sin `KIND` es un mensaje que muere en la DLQ.

    `KINDS` se parametriza sobre sí misma, así que los tests de arriba pasan sin
    enterarse de que falta una clase: el contrato nuevo de esta ficha estaba
    generado, discriminado por topic, con handler y con cinco pruebas verdes — y
    `validate()` lo habría rechazado como «clase de contrato desconocida»
    mandando a la DLQ el único mensaje que le dice a la nube que la sacudida
    terminó. Lo cazó la prueba de costura, no las unitarias.

    Es el defecto de censo que `TRASPASO-SESION.md` ya tiene escrito: **una lista
    enumerada a mano acaba divergiendo de lo que enumera.**
    """
    en_disco = {p.name.removesuffix(".schema.json") for p in SCHEMAS_DIR.glob("*.schema.json")}
    huerfanos = en_disco - set(KINDS) - _SIN_INGESTA
    assert not huerfanos, (
        f"schemas sin clase de contrato: {sorted(huerfanos)}. Añádelos a `KINDS` en "
        "`contracts/loader.py` (y a `_TOPIC_KIND` o a `discriminate`), o a `_SIN_INGESTA` "
        "con la razón por la que la nube no los ingiere."
    )


def test_el_censo_de_exentos_no_INVENTA_schemas() -> None:
    """Control de ceguera: un exento que ya no existe vacía la guarda en silencio."""
    en_disco = {p.name.removesuffix(".schema.json") for p in SCHEMAS_DIR.glob("*.schema.json")}
    assert _SIN_INGESTA <= en_disco, f"exentos que no existen: {sorted(_SIN_INGESTA - en_disco)}"
