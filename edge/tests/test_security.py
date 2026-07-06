"""security — comandos firmados HMAC + nonce anti-replay."""

from __future__ import annotations

import pytest
from takab_edge.security import SecurityManager

KEY = b"clave-de-prueba-inyectada-no-hardcodeada"
PAYLOAD = b'{"channel":"siren","action":"activate"}'


def test_valid_signed_command_is_accepted():
    mgr = SecurityManager(KEY)
    sig = mgr.sign(PAYLOAD, nonce="n1")
    assert mgr.verify_command(PAYLOAD, "n1", sig) is True


def test_unsigned_command_is_rejected():
    mgr = SecurityManager(KEY)
    assert mgr.verify_command(PAYLOAD, "n1", "") is False


def test_replayed_nonce_is_rejected():
    mgr = SecurityManager(KEY)
    sig = mgr.sign(PAYLOAD, nonce="n2")
    assert mgr.verify_command(PAYLOAD, "n2", sig) is True
    assert mgr.verify_command(PAYLOAD, "n2", sig) is False  # replay


def test_tampered_payload_is_rejected():
    mgr = SecurityManager(KEY)
    sig = mgr.sign(PAYLOAD, nonce="n3")
    assert mgr.verify_command(PAYLOAD + b"x", "n3", sig) is False


def test_empty_key_is_rejected_at_construction():
    with pytest.raises(ValueError):
        SecurityManager(b"")
