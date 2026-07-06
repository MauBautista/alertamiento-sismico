"""security — comandos firmados (HMAC + nonce + ventana temporal) + config firmada."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from takab_edge.security import SecurityManager

KEY = b"clave-de-prueba-inyectada-no-hardcodeada"
PAYLOAD = b'{"channel":"siren","action":"activate"}'
NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)


def _mgr(ttl: float = 30.0, now: datetime = NOW) -> SecurityManager:
    return SecurityManager(KEY, command_ttl_s=ttl, clock=lambda: now)


# --- Comandos firmados ---


def test_valid_signed_command_is_accepted():
    mgr = _mgr()
    sig = mgr.sign(PAYLOAD, "n1", NOW)
    assert mgr.verify_command(PAYLOAD, "n1", sig, NOW) is True


def test_unsigned_command_is_rejected():
    assert _mgr().verify_command(PAYLOAD, "n1", "", NOW) is False


def test_replayed_nonce_is_rejected():
    mgr = _mgr()
    sig = mgr.sign(PAYLOAD, "n2", NOW)
    assert mgr.verify_command(PAYLOAD, "n2", sig, NOW) is True
    assert mgr.verify_command(PAYLOAD, "n2", sig, NOW) is False  # replay


def test_tampered_payload_is_rejected():
    mgr = _mgr()
    sig = mgr.sign(PAYLOAD, "n3", NOW)
    assert mgr.verify_command(PAYLOAD + b"x", "n3", sig, NOW) is False


def test_expired_command_is_rejected_even_with_fresh_nonce():
    mgr = _mgr(ttl=30.0)
    old = NOW - timedelta(seconds=120)  # comando de hace 2 min
    sig = mgr.sign(PAYLOAD, "n4", old)
    assert mgr.verify_command(PAYLOAD, "n4", sig, old) is False  # fuera de ventana ("JWT corto")


def test_nonce_store_is_pruned_by_expiry():
    mgr = _mgr(ttl=30.0)
    sig = mgr.sign(PAYLOAD, "n5", NOW)
    assert mgr.verify_command(PAYLOAD, "n5", sig, NOW) is True
    assert "n5" in mgr._nonces
    later = NOW + timedelta(seconds=120)  # más allá del TTL
    mgr._clock = lambda: later
    sig2 = mgr.sign(PAYLOAD, "n6", later)
    assert mgr.verify_command(PAYLOAD, "n6", sig2, later) is True
    assert "n5" not in mgr._nonces  # podado → store acotado


def test_empty_key_is_rejected_at_construction():
    with pytest.raises(ValueError):
        SecurityManager(b"")


# --- Config firmada ---


def test_valid_config_signature_is_accepted():
    mgr = _mgr()
    raw = b'{"tenant_id":"t1"}'
    assert mgr.verify_config(raw, mgr.sign_config(raw, 1), 1) is True


def test_config_signature_is_bound_to_version():
    # Una firma para v1 NO vale re-etiquetada como v999 (anti-replay/relabeleo de versión).
    mgr = _mgr()
    raw = b'{"tenant_id":"t1"}'
    sig = mgr.sign_config(raw, 1)
    assert mgr.verify_config(raw, sig, 1) is True
    assert mgr.verify_config(raw, sig, 999) is False


def test_unsigned_or_tampered_config_is_rejected():
    mgr = _mgr()
    raw = b'{"tenant_id":"t1"}'
    assert mgr.verify_config(raw, "", 1) is False
    assert mgr.verify_config(raw + b"x", mgr.sign_config(raw, 1), 1) is False


def test_config_and_command_signatures_are_distinct_domains():
    # Una firma de config NO sirve como firma de comando (dominios separados anti-confusión).
    mgr = _mgr()
    raw = b"payload"
    config_sig = mgr.sign_config(raw, 1)
    assert mgr.verify_command(raw, "n", config_sig, NOW) is False


def test_malformed_signature_returns_false_not_raises():
    # Una firma con caracteres no-ASCII no debe lanzar (DoS), sólo rechazar.
    mgr = _mgr()
    assert mgr.verify_command(PAYLOAD, "n", "ñoño", NOW) is False
    assert mgr.verify_config(b"x", "ñoño", 1) is False


def test_future_dated_command_beyond_skew_is_rejected():
    mgr = _mgr(ttl=30.0)  # clock_skew por defecto 5 s
    future = NOW + timedelta(seconds=60)  # comando fechado en el futuro > skew
    sig = mgr.sign(PAYLOAD, "nf", future)
    assert mgr.verify_command(PAYLOAD, "nf", sig, future) is False
