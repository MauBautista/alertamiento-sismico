"""Vectores HMAC compartidos edge↔nube (T-1.23): el framing NO puede driftar.

Los vectores viven en ``shared/schemas/tests/hmac_vectors.json`` y los consume
también la suite de la API: si cualquiera de los dos lados cambia el framing
(length-prefix, dominios, canonicalización), su suite truena aquí.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from takab_edge.security import SecurityManager

VECTORS_PATH = Path(__file__).resolve().parents[2] / "shared/schemas/tests/hmac_vectors.json"
VECTORS = json.loads(VECTORS_PATH.read_text())


def _mgr() -> SecurityManager:
    return SecurityManager(bytes.fromhex(VECTORS["key_hex"]))


@pytest.mark.parametrize("case", VECTORS["command"], ids=lambda c: c["name"])
def test_command_vectors_sign(case: dict) -> None:
    body = bytes.fromhex(case["payload_canonical_hex"])
    ts = datetime.fromisoformat(case["ts"])
    assert _mgr().sign(body, case["nonce"], ts) == case["sig"]


@pytest.mark.parametrize("case", VECTORS["command"], ids=lambda c: c["name"])
def test_command_vectors_canonicalization(case: dict) -> None:
    """La canonicalización local reproduce los bytes firmados del vector."""
    body = json.dumps(case["payload"], separators=(",", ":"), sort_keys=True).encode()
    assert body.hex() == case["payload_canonical_hex"]


@pytest.mark.parametrize("case", VECTORS["command"], ids=lambda c: c["name"])
def test_command_vectors_verify(case: dict) -> None:
    """verify_command acepta el vector con reloj congelado en su ts."""
    ts = datetime.fromisoformat(case["ts"])
    mgr = SecurityManager(bytes.fromhex(VECTORS["key_hex"]), clock=lambda: ts)
    body = bytes.fromhex(case["payload_canonical_hex"])
    assert mgr.verify_command(body, case["nonce"], case["sig"], ts) is True


@pytest.mark.parametrize("case", VECTORS["config"], ids=lambda c: c["name"])
def test_config_vectors_sign_and_verify(case: dict) -> None:
    body = bytes.fromhex(case["payload_canonical_hex"])
    mgr = _mgr()
    assert mgr.sign_config(body, case["version"]) == case["sig"]
    assert mgr.verify_config(body, case["sig"], case["version"]) is True
