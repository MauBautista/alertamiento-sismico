"""Anti-drift de los contratos DOWNLINK nube→edge (T-1.45, ítem #25 de la auditoría).

Los contratos UPLINK (edge→nube) se regeneran de los modelos Pydantic del edge y
``edge/tests/test_schemas.py`` los ancla. Los DOWNLINK —``command``,
``config_update``, ``backfill_grant``— son artesanales en ``shared/schemas`` y
hasta hoy NADA los pinneaba: la nube podía cambiar la forma del sobre sin tocar
el contrato publicado y el drift solo se descubría en el gabinete. Aquí cada
sobre se construye EXACTAMENTE como lo emite el código real de la nube
(``routers/commands.py``, ``commands/sync.py``, ``backfill/grants.py``) y se
valida contra su schema publicado. Sin DB ni AWS.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, ValidationError

from takab_api.commands.signing import canonical_payload, sign_command, sign_config

_SCHEMAS = Path(__file__).resolve().parents[3] / "shared" / "schemas"


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((_SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_command_envelope_matches_published_contract() -> None:
    """Sobre idéntico al que arma ``issue_command`` (T-1.23/T-1.38)."""
    now = datetime.now(tz=UTC)
    nonce = uuid4().hex
    payload = {"channel": "siren", "action": "activate", "event_id": "EVT-CONTRACT-1"}
    envelope = {
        "kind": "command",
        "command_id": str(uuid4()),
        "nonce": nonce,
        "ts": now.isoformat(),
        "payload": payload,
        "sig": sign_command(b"clave", canonical_payload(payload), nonce, now.isoformat()),
    }
    _validator("command").validate(envelope)


def test_config_update_envelope_matches_published_contract() -> None:
    """Sobre idéntico al que arma ``run_config_sync_pass``."""
    doc = {"command_enabled": True, "command_ttl_s": 30.0}
    envelope = {
        "kind": "config_update",
        "version": 1,
        "payload": doc,
        "sig": sign_config(b"clave", canonical_payload(doc), 1),
    }
    _validator("config_update").validate(envelope)


def test_el_nombre_de_la_clave_administrativa_es_el_mismo_en_los_dos_lados() -> None:
    """[T-2.65] `cloud_admin_state` cruza el contrato POR NOMBRE y nada lo validaba.

    `config_update.schema.json` tipa `payload` como un objeto libre, y `EdgeSettings`
    usa `extra="ignore"`: un typo en la nube (`cloud_admin_status`) no rompería el
    schema, no rompería la validación del edge y el gabinete descartaría el campo
    EN SILENCIO PARA SIEMPRE — el aviso de baja no llegaría nunca y nadie lo sabría.
    Este test es el único punto del repo donde las dos mitades se miran a la cara.
    """
    # Lado NUBE: el literal que `commands/sync.py` fusiona en el doc firmado.
    sql = (Path(__file__).resolve().parents[2] / "src/takab_api/commands/sync.py").read_text(
        encoding="utf-8"
    )
    assert "'cloud_admin_state', b.admin_state" in sql
    assert "CASE WHEN g.status = 'retired' THEN 'retired' ELSE 'active' END" in sql

    # Lado EDGE: el campo declarado en EdgeSettings, leído del fuente para no
    # importar el paquete del edge desde la suite de la nube.
    edge = (Path(__file__).resolve().parents[3] / "edge/takab_edge/config/settings.py").read_text(
        encoding="utf-8"
    )
    assert 'cloud_admin_state: str = "active"' in edge, (
        "el edge no declara `cloud_admin_state`, o lo hace con otro tipo/nombre"
    )
    # Y sigue siendo `str`, no un Literal/Enum: un valor fuera del enum tumbaría el
    # DOCUMENTO ENTERO (umbrales incluidos) en vez de solo ese campo.
    assert "cloud_admin_state: Literal" not in edge

    # El sobre con la clave nueva sigue validando contra el contrato publicado.
    doc = {"command_enabled": True, "cloud_admin_state": "retired"}
    _validator("config_update").validate(
        {
            "kind": "config_update",
            "version": 2,
            "payload": doc,
            "sig": sign_config(b"clave", canonical_payload(doc), 2),
        }
    )


def test_backfill_grant_envelope_matches_published_contract() -> None:
    """Sobre idéntico al que arma ``handle_backfill_request`` (T-1.25)."""
    now = datetime.now(tz=UTC)
    grant = {
        "kind": "backfill_grant",
        "request_id": "req-contract-1",
        "mode": "backfill",
        "url": "https://bucket.s3.amazonaws.com/presigned?X-Amz-Signature=x",
        "key": "backfill/gw-dev-0001/000000000001.ndjson",
        "expires_at": (now + timedelta(seconds=900)).isoformat(),
    }
    _validator("backfill_grant").validate(grant)


def test_contracts_reject_envelopes_without_signature_or_kind() -> None:
    """Los required del contrato muerden: un sobre sin firma NO valida."""
    with pytest.raises(ValidationError):
        _validator("command").validate({"kind": "command", "nonce": "n"})
    with pytest.raises(ValidationError):
        _validator("config_update").validate({"version": 1, "payload": {}})
    with pytest.raises(ValidationError):
        _validator("backfill_grant").validate({"kind": "backfill_grant", "mode": "backfill"})
