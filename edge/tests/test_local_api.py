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


def _post(dashboard, path: str, pin: str | None = None) -> int:
    headers = {"X-Takab-Pin": pin} if pin is not None else {}
    request = urllib.request.Request(_url(dashboard, path), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


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


# --- PIN de las acciones (T-1.43): la LAN dejó de ser la única barrera ---


@pytest.fixture
def pinned(supervisor):
    """Panel con PIN configurado (modo producción de facto para las acciones)."""
    from takab_edge.local_api import LocalDashboard

    dash = LocalDashboard(
        supervisor.gpio,
        supervisor.rules,
        supervisor.health,
        host="127.0.0.1",
        port=0,
        pin="424242",
        dev_mode=False,
    )
    dash.start()
    try:
        yield dash
    finally:
        dash.stop()


def test_pin_required_when_configured(pinned, supervisor):
    """Sin header ⇒ 401 y la acción NO se ejecuta (la sirena no se toca)."""
    assert _post(pinned, "/api/siren-test") == 401
    assert supervisor.gpio.siren_sounding is False


def test_pin_wrong_is_401_right_is_200(pinned, supervisor):
    assert _post(pinned, "/api/siren-test", pin="000000") == 401
    assert supervisor.gpio.siren_sounding is False
    assert _post(pinned, "/api/siren-test", pin="424242") == 200
    assert supervisor.gpio.siren_sounding is True


def test_pin_lockout_after_five_failures(pinned):
    for _ in range(5):
        assert _post(pinned, "/api/silence", pin="mal") == 401
    # Con lockout activo NI el PIN correcto entra (429), sin esperas en el test.
    assert _post(pinned, "/api/silence", pin="424242") == 429


def test_missing_header_does_not_count_towards_lockout(pinned, supervisor):
    """El sondeo de la página (sin header) pregunta el PIN; no es un intento."""
    for _ in range(10):
        assert _post(pinned, "/api/silence") == 401
    assert _post(pinned, "/api/siren-test", pin="424242") == 200
    assert supervisor.gpio.siren_sounding is True


def test_get_status_stays_open_with_pin(pinned):
    status, body = _get(pinned, "/api/status")
    assert status == 200
    assert b"gateway_id" in body


def test_production_without_pin_is_fail_closed(supervisor):
    """Prod sin PIN provisionado: acciones 403 — nunca abiertas por accidente."""
    from takab_edge.local_api import LocalDashboard

    dash = LocalDashboard(
        supervisor.gpio,
        supervisor.rules,
        supervisor.health,
        host="127.0.0.1",
        port=0,
        pin="",
        dev_mode=False,
    )
    dash.start()
    try:
        assert _post(dash, "/api/siren-test") == 403
        assert supervisor.gpio.siren_sounding is False
        status, _ = _get(dash, "/api/status")
        assert status == 200  # la lectura del guardia sigue viva
    finally:
        dash.stop()
