"""Vectores HMAC compartidos edge↔nube (T-1.23): drift imposible.

Los vectores se GENERARON con el ``SecurityManager`` real del edge; esta suite
prueba que la firma de la nube (``takab_api.commands.signing``) los reproduce
byte a byte. Si cualquiera de los dos lados cambia el framing, su suite truena.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from takab_api.commands.signing import canonical_payload, sign_command, sign_config

VECTORS_PATH = Path(__file__).resolve().parents[3] / "shared/schemas/tests/hmac_vectors.json"
VECTORS = json.loads(VECTORS_PATH.read_text())
KEY = bytes.fromhex(VECTORS["key_hex"])


@pytest.mark.parametrize("case", VECTORS["command"], ids=lambda c: c["name"])
def test_command_vectors(case: dict) -> None:
    body = bytes.fromhex(case["payload_canonical_hex"])
    assert sign_command(KEY, body, case["nonce"], case["ts"]) == case["sig"]


@pytest.mark.parametrize("case", VECTORS["command"], ids=lambda c: c["name"])
def test_command_canonicalization(case: dict) -> None:
    """La canonicalización de la nube reproduce los bytes firmados del vector."""
    assert canonical_payload(case["payload"]).hex() == case["payload_canonical_hex"]


@pytest.mark.parametrize("case", VECTORS["config"], ids=lambda c: c["name"])
def test_config_vectors(case: dict) -> None:
    body = bytes.fromhex(case["payload_canonical_hex"])
    assert sign_config(KEY, body, case["version"]) == case["sig"]


def test_tampering_changes_signature() -> None:
    case = VECTORS["command"][0]
    body = bytes.fromhex(case["payload_canonical_hex"])
    assert sign_command(KEY, body, case["nonce"] + "x", case["ts"]) != case["sig"]
    assert sign_command(KEY, body + b" ", case["nonce"], case["ts"]) != case["sig"]
    assert sign_command(b"otra-clave", body, case["nonce"], case["ts"]) != case["sig"]
