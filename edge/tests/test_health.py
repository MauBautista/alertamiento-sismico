"""health — snapshot del gabinete: relés, probes, UPS, transición discreta y heartbeat."""

from __future__ import annotations

import logging
import threading

import pytest
from takab_edge.contracts import ActuatorChannel, UpsStatus
from takab_edge.gpio import GpioController
from takab_edge.health import HealthMonitor, UpsReading, ups_label


class _FakeProbes:
    def __init__(self, temp=25.0, ntp=0.01, ups=None, cert=365):
        self._temp = temp
        self._ntp = ntp
        self._ups = ups or UpsReading()
        self._cert = cert

    def temperature_c(self):
        return self._temp

    def ntp_offset_s(self):
        return self._ntp

    def ups(self):
        return self._ups

    def cert_days_remaining(self):
        return self._cert


class _FakeSeedlink:
    def __init__(self, lag=0.4, seen=1000, gaps=5):
        self.last_lag_s = lag
        self.packets_seen = seen
        self.gaps = gaps


# --- Estado de relés (desde gpio) ---


def test_snapshot_includes_relay_states(settings):
    gpio = GpioController(settings)
    gpio.start()
    health = HealthMonitor(settings, gpio=gpio, probes=_FakeProbes())
    health.start()
    try:
        snap = health.snapshot()
        assert snap.gateway_id == settings.gateway_id
        assert len(snap.relays) == 5
    finally:
        health.stop()
        gpio.stop()


def test_snapshot_reflects_sasmex_actuation(settings):
    gpio = GpioController(settings)
    gpio.start()
    try:
        health = HealthMonitor(settings, gpio=gpio, probes=_FakeProbes())
        gpio.simulate_sasmex(active=True)
        snap = health.snapshot(transition_reason="sasmex")
        siren = next(r for r in snap.relays if r.channel == ActuatorChannel.SIREN)
        assert siren.energized is True
        assert snap.transition_reason == "sasmex"
    finally:
        gpio.stop()


def test_snapshot_without_gpio_is_empty(settings):
    snap = HealthMonitor(settings, probes=_FakeProbes()).snapshot()
    assert snap.relays == []


# --- Composición desde probes/seedlink ---


def test_snapshot_composes_from_probes_and_seedlink(settings):
    probes = _FakeProbes(
        temp=42.0, ntp=0.02, ups=UpsReading(UpsStatus.BATTERY, 55.0, 3600), cert=12
    )
    monitor = HealthMonitor(
        settings, seedlink=_FakeSeedlink(lag=0.4, seen=995, gaps=5), probes=probes
    )
    snap = monitor.snapshot("test")
    assert snap.temperature_c == 42.0
    assert snap.ntp_offset_s == 0.02
    assert snap.ups_status is UpsStatus.BATTERY
    assert snap.battery_pct == 55.0
    assert snap.cert_days_remaining == 12
    assert snap.seedlink_lag_s == 0.4
    assert snap.packet_loss_pct == pytest.approx(0.5)  # 5 / (995 + 5) * 100


def test_ups_label_variants():
    assert ups_label(UpsReading(UpsStatus.LINE, 100.0)) == "RED ELÉCTRICA 100%"
    assert "RESPALDO 1h 0m" in ups_label(UpsReading(UpsStatus.BATTERY, 50.0, 3600))
    assert ups_label(UpsReading(UpsStatus.BATTERY, 50.0)) == "EN BATERÍA"


def test_packet_loss_zero_without_seedlink(settings):
    monitor = HealthMonitor(settings, probes=_FakeProbes())
    assert monitor.snapshot().packet_loss_pct == 0.0


# --- Logging por transición + heartbeat ---


def test_transition_logged_only_on_discrete_change(settings, caplog):
    probes = _FakeProbes(temp=25.0)
    monitor = HealthMonitor(settings, probes=probes)
    with caplog.at_level(logging.INFO, logger="takab_edge.health"):
        monitor.snapshot("a")  # None → estado: transición
        probes._temp = 30.0  # drift continuo bajo umbral → NO es transición
        monitor.snapshot("b")
        probes._ups = UpsReading(UpsStatus.BATTERY, 80.0)  # cambio discreto → transición
        monitor.snapshot("c")
    logs = [r for r in caplog.records if "transición de salud" in r.getMessage()]
    assert len(logs) == 2


def test_heartbeat_thread_emits_periodic_snapshots(settings):
    seen: list = []
    got = threading.Event()
    monitor = HealthMonitor(settings, probes=_FakeProbes(), heartbeat_s=0.05)
    monitor.on_snapshot(lambda snap: (seen.append(snap), len(seen) >= 3 and got.set()))
    monitor.start()
    try:
        assert got.wait(2.0)  # startup + ≥2 heartbeats
    finally:
        monitor.stop()
    assert len(seen) >= 3
