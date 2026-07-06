"""local_api — estado del gabinete y silencio por LAN."""

from __future__ import annotations

from takab_edge.contracts import ActuatorChannel


def test_status_reports_gateway_and_relays(supervisor):
    status = supervisor.local_api.status()
    assert status["gateway_id"] == supervisor.settings.gateway_id
    assert len(status["relays"]) == 5
    assert "captured_at" in status


def test_silence_inhibits_reflex(supervisor):
    supervisor.local_api.silence()
    supervisor.gpio.simulate_sasmex(active=True)
    assert supervisor.gpio.relay_state(ActuatorChannel.SIREN).energized is False
