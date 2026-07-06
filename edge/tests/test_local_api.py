"""local_api — estado del gabinete, control por LAN y servidor HTTP sin internet."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest


def _url(dashboard, path: str) -> str:
    # El servidor bindea 0.0.0.0; el cliente entra por loopback + el puerto efímero real.
    _host, port = dashboard.address
    return f"http://127.0.0.1:{port}{path}"


def _get(dashboard, path: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(_url(dashboard, path), timeout=5) as response:
        return response.status, response.read()


def _post(dashboard, path: str) -> int:
    request = urllib.request.Request(_url(dashboard, path), method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


# --- Lógica de estado/control ---


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


# --- Servidor HTTP en LAN (sin internet) ---


def test_http_index_served(supervisor):
    status, body = _get(supervisor.local_api, "/")
    assert status == 200
    assert b"ALERTA S" in body  # banner MVP "ALERTA SÍSMICA · PROTÉJASE"


def test_http_status_endpoint(supervisor):
    _, body = _get(supervisor.local_api, "/api/status")
    data = json.loads(body)
    assert data["gateway_id"] == supervisor.settings.gateway_id
    assert data["sasmex_active"] is False
    assert len(data["relays"]) == 5


def test_http_silence_command(supervisor):
    supervisor.gpio.simulate_sasmex(active=True)
    assert supervisor.gpio.siren_sounding is True
    assert _post(supervisor.local_api, "/api/silence") == 200
    assert supervisor.gpio.audible_silenced is True
    assert supervisor.gpio.siren_sounding is False


def test_http_siren_test_command(supervisor):
    assert _post(supervisor.local_api, "/api/siren-test") == 200
    assert supervisor.gpio.siren_sounding is True  # el self-test enciende la sirena


def test_http_reset_command(supervisor):
    supervisor.gpio.simulate_sasmex(active=True)
    assert _post(supervisor.local_api, "/api/reset") == 200
    assert supervisor.gpio.sasmex_active is False


def test_http_unknown_route_is_404(supervisor):
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(_url(supervisor.local_api, "/nope"), timeout=5)
    assert exc.value.code == 404
