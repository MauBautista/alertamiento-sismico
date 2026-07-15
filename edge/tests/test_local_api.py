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


# --- Prueba LOCAL de actuación por LAN (T-1.67) ------------------------------
# El comportamiento eléctrico completo se prueba en test_gpio.py; aquí solo el
# CABLEADO del panel: endpoint, PIN, y que el resultado aflore en status().

_CANNED_ACTUATION = {
    "ok": True,
    "reason": None,
    "relays": {
        "siren": {"held": True, "readback_ok": True},
        "gas_valve": {"pulsed": True, "readback_ok": True},
    },
}


def test_lan_actuator_test_surfaces_results_in_status(supervisor, monkeypatch):
    monkeypatch.setattr(supervisor.gpio, "run_local_actuation_test", lambda: _CANNED_ACTUATION)
    supervisor.local_api.run_actuator_test()
    section = supervisor.local_api.status()["actuation_test"]
    assert section["results"] == _CANNED_ACTUATION
    assert "active" in section


def test_http_actuator_test_command(supervisor, monkeypatch):
    monkeypatch.setattr(supervisor.gpio, "run_local_actuation_test", lambda: _CANNED_ACTUATION)
    assert _post(supervisor.local_api, "/api/actuator-test") == 200


def test_actuator_test_is_pin_gated(pinned, supervisor, monkeypatch):
    monkeypatch.setattr(supervisor.gpio, "run_local_actuation_test", lambda: _CANNED_ACTUATION)
    assert _post(pinned, "/api/actuator-test") == 401  # sin PIN no ejercita nada
    assert _post(pinned, "/api/actuator-test", pin="424242") == 200


# --- Modo prueba del WR-1 por LAN (T-1.69): toggle armar/desarmar ------------


def test_test_mode_toggle_y_status(supervisor):
    assert supervisor.local_api.status()["test_mode"]["active"] is False
    assert _post(supervisor.local_api, "/api/test-mode") == 200  # arma
    assert supervisor.gpio.test_mode_active is True
    section = supervisor.local_api.status()["test_mode"]
    assert section["active"] is True and section["remaining_s"] > 0
    assert _post(supervisor.local_api, "/api/test-mode") == 200  # segundo toque desarma
    assert supervisor.gpio.test_mode_active is False


def test_test_mode_is_pin_gated(pinned, supervisor):
    assert _post(pinned, "/api/test-mode") == 401  # sin PIN no arma
    assert supervisor.gpio.test_mode_active is False
    assert _post(pinned, "/api/test-mode", pin="424242") == 200
    assert supervisor.gpio.test_mode_active is True


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


# --- Mini-consola (T-1.53): status enriquecido, honesto y defensivo ------------


def test_status_does_not_publish_health(supervisor):
    """REGRESIÓN del bug: cada GET ejecutaba las sondas Y publicaba a la nube."""
    published = []
    supervisor.health.on_snapshot(published.append)
    for _ in range(10):
        supervisor.local_api.status()
    assert published == []  # el panel lee el CACHE; solo el heartbeat publica


def test_status_includes_signal_per_channel(supervisor):
    from takab_edge.contracts import WaveformPacket, utcnow

    for channel, amp in (("EHZ", 5), ("ENZ", 7)):
        supervisor.signal.process(
            WaveformPacket(
                station="R4F74", channel=channel, starttime=utcnow(), samples=[0, amp] * 50
            )
        )
    status = supervisor.local_api.status()
    channels = status["signal"]["channels"]
    assert set(channels) == {"EHZ", "ENZ"}
    ch = channels["ENZ"]
    assert {"pga_g", "pgv_cms", "clipping", "age_s", "received_at"} <= set(ch)
    assert ch["age_s"] >= 0.0
    assert status["signal"]["stale_after_s"] == 5.0


def test_status_without_features_is_honest(supervisor):
    status = supervisor.local_api.status()
    assert status["signal"]["channels"] == {}
    assert status["signal"]["last_received_at"] is None  # "SIN SEÑAL", no un invento


def test_status_includes_health_cloud_and_identity(supervisor):
    status = supervisor.local_api.status()
    # salud del CACHE (el _on_start del monitor tomó el snapshot de arranque)
    assert status["health"] is not None
    assert "disk_used_pct" in status["health"]
    assert status["health"]["age_s"] >= 0.0
    # enlace a nube: en dev sin transporte no hay conexión — se dice tal cual
    assert status["cloud"]["online"] is False
    assert isinstance(status["cloud"]["queued"], int)
    # identidad viva desde settings (no depende del snapshot)
    assert status["gateway_id"] == supervisor.settings.gateway_id
    assert status["uptime_s"] >= 0.0
    assert status["refresh_ms"] == supervisor.settings.local_api_refresh_ms


def test_status_survives_broken_modules(supervisor, monkeypatch):
    """El panel del guardia NO muere porque un módulo no-crítico falle."""

    class _Roto:
        def __get__(self, *_):
            raise RuntimeError("kaput")

    monkeypatch.setattr(type(supervisor.rules), "last_decision", _Roto())
    monkeypatch.setattr(type(supervisor.health), "last_snapshot", _Roto())
    code, body = _get(supervisor.local_api, "/api/status")
    assert code == 200
    payload = json.loads(body)
    assert payload["last_tier"] is None
    assert payload["health"] is None


def test_events_merge_transitions_and_lan_actions(supervisor):
    from takab_edge.contracts import SasmexSignal

    supervisor.rules.evaluate_sasmex(SasmexSignal(active=True))
    assert _post(supervisor.local_api, "/api/siren-test") == 200
    events = supervisor.local_api.status()["events"]
    assert len(events) <= 10
    kinds = {e.get("action") or e.get("to_tier") for e in events}
    assert "siren_test" in kinds  # acción LAN registrada
    assert "evacuate_or_hold" in kinds  # transición SASMEX registrada
    # más recientes primero
    ats = [e["at"] for e in events]
    assert ats == sorted(ats, reverse=True)


def test_index_has_no_external_resources(supervisor):
    """La LAN no tiene internet: el HTML no puede referenciar NADA externo."""
    code, body = _get(supervisor.local_api, "/")
    assert code == 200
    html = body.decode()
    assert "ALERTA S" in html and "PROTÉJASE" in html  # banner MVP intacto
    for forbidden in ("googleapis", "cdn.", "https://", "http://"):
        assert forbidden not in html, f"recurso externo en el panel: {forbidden}"
    # sin countdown ni magnitud preliminar (blueprint §14)
    assert "T-MINUS" not in html
    assert "countdown" not in html.lower()
