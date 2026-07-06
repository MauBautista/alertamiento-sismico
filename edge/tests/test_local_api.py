"""local_api — estado del gabinete y silencio por LAN."""

from __future__ import annotations


def test_status_reports_gateway_and_relays(supervisor):
    status = supervisor.local_api.status()
    assert status["gateway_id"] == supervisor.settings.gateway_id
    assert len(status["relays"]) == 5
    assert "captured_at" in status


def test_lan_silence_stops_the_siren(supervisor):
    supervisor.gpio.simulate_sasmex(active=True)  # alerta suena
    assert supervisor.gpio.siren_sounding is True
    supervisor.local_api.silence()  # silenciar por LAN
    assert supervisor.gpio.siren_sounding is False
    assert supervisor.gpio.sasmex_active is True  # la alerta sigue viva


def test_lan_reset_clears_latched_alert(supervisor):
    supervisor.gpio.simulate_sasmex(active=True)
    supervisor.local_api.reset_alert()
    assert supervisor.gpio.sasmex_active is False
    assert supervisor.gpio.siren_sounding is False
