"""health — snapshot del gabinete con estado de relés desde gpio."""

from __future__ import annotations

from takab_edge.contracts import ActuatorChannel
from takab_edge.gpio import GpioController
from takab_edge.health import HealthMonitor


def test_snapshot_includes_relay_states(settings):
    gpio = GpioController(settings)
    gpio.start()
    try:
        health = HealthMonitor(settings, gpio=gpio)
        health.start()
        snap = health.snapshot()
        assert snap.gateway_id == settings.gateway_id
        assert len(snap.relays) == 5
    finally:
        gpio.stop()


def test_snapshot_reflects_sasmex_actuation(settings):
    gpio = GpioController(settings)
    gpio.start()
    try:
        health = HealthMonitor(settings, gpio=gpio)
        gpio.simulate_sasmex(active=True)
        snap = health.snapshot(transition_reason="sasmex")
        siren = next(r for r in snap.relays if r.channel == ActuatorChannel.SIREN)
        assert siren.energized is True
        assert snap.transition_reason == "sasmex"
    finally:
        gpio.stop()


def test_snapshot_without_gpio_is_empty(settings):
    snap = HealthMonitor(settings).snapshot()
    assert snap.relays == []
