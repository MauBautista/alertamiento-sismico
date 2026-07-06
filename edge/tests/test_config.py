"""Configuración: identidad, perfil fail-safe por canal (SPOF-07) y umbrales."""

from __future__ import annotations

import pytest
from takab_edge.config import ConfigError, ConfigStore, EdgeSettings, load_settings
from takab_edge.contracts import ActuatorChannel, FailSafeMode
from takab_edge.security import SecurityManager


def test_defaults_are_dev_mode():
    s = load_settings()
    assert s.dev_mode is True
    assert s.sample_rate == 100.0
    assert s.seedlink_port == 18000


def test_failsafe_profile_matches_spof_07():
    s = load_settings()
    # Sirena NO (una falla NO la deja sonando); puerta NC (una falla LIBERA);
    # gas fail-close (una falla la CIERRA). Blueprint §4.7 SPOF-07.
    assert s.failsafe[ActuatorChannel.SIREN] is FailSafeMode.NORMALLY_OPEN
    assert s.failsafe[ActuatorChannel.DOOR_RETAINER] is FailSafeMode.NORMALLY_CLOSED
    assert s.failsafe[ActuatorChannel.GAS_VALVE] is FailSafeMode.FAIL_CLOSE


def test_env_prefix_overrides(monkeypatch):
    monkeypatch.setenv("TAKAB_EDGE_TENANT_ID", "tenant-42")
    monkeypatch.setenv("TAKAB_EDGE_DEV_MODE", "false")
    s = EdgeSettings()
    assert s.tenant_id == "tenant-42"
    assert s.dev_mode is False


def test_threshold_band_hospital_default():
    s = load_settings()
    assert s.thresholds.pga_watch_g == 0.040
    assert s.thresholds.pga_trip_g == 0.060


# --- Sync firmada, versionada y reversible (T-1.12) ---


def _store():
    security = SecurityManager(b"clave-de-config-inyectada")
    return ConfigStore(load_settings(), security=security), security


def _signed(security, tenant_id, version):
    raw = load_settings().model_copy(update={"tenant_id": tenant_id}).model_dump_json().encode()
    return raw, security.sign_config(raw, version)


def test_apply_signed_config_update_bumps_version():
    store, security = _store()
    raw, sig = _signed(security, "tenant-new", 1)
    assert store.apply_signed_update(raw, sig, 1) == 1
    assert store.current().tenant_id == "tenant-new"
    assert store.version == 1


def test_unsigned_config_update_is_rejected():
    store, security = _store()
    raw, _ = _signed(security, "attacker", 1)
    with pytest.raises(ConfigError):
        store.apply_signed_update(raw, "firma-invalida", 1)
    assert store.version == 0  # no se aplicó


def test_fail_closed_without_security_verifier():
    store = ConfigStore(load_settings())  # sin security → NO se puede verificar
    with pytest.raises(ConfigError):
        store.apply_signed_update(b'{"tenant_id":"x"}', "cualquier-firma", 1)


def test_replay_with_relabeled_version_is_rejected():
    # La firma cubre la versión: no se puede re-aplicar una config vieja como una versión mayor.
    store, security = _store()
    raw1, sig1 = _signed(security, "v1", 1)
    store.apply_signed_update(raw1, sig1, 1)
    with pytest.raises(ConfigError):
        store.apply_signed_update(raw1, sig1, 999)  # firmada para v1, re-etiquetada v999


def test_non_monotonic_version_is_rejected():
    store, security = _store()
    raw, sig = _signed(security, "v5", 5)
    store.apply_signed_update(raw, sig, 5)
    raw2, sig2 = _signed(security, "v5b", 5)
    with pytest.raises(ConfigError):
        store.apply_signed_update(raw2, sig2, 5)  # versión ya vista


def test_rollback_does_not_reopen_replay_window():
    store, security = _store()
    good_raw, good_sig = _signed(security, "buena", 1)
    store.apply_signed_update(good_raw, good_sig, 1)
    bad_raw, bad_sig = _signed(security, "mala", 2)
    store.apply_signed_update(bad_raw, bad_sig, 2)
    store.rollback()  # revierte el CONTENIDO a "buena"
    assert store.current().tenant_id == "buena"
    # El frame malo v2 re-entregado (at-least-once) NO se re-aplica (high_water sigue en 2).
    with pytest.raises(ConfigError):
        store.apply_signed_update(bad_raw, bad_sig, 2)
    assert store.current().tenant_id == "buena"
