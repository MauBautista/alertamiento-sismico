"""Configuración: identidad, perfil fail-safe por canal (SPOF-07) y umbrales."""

from __future__ import annotations

from takab_edge.config import EdgeSettings, load_settings
from takab_edge.contracts import ActuatorChannel, FailSafeMode


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
