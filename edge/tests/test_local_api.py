"""local_api — estado del gabinete, control por LAN y servidor HTTP sin internet."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC

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
    before = supervisor.local_api.status()
    assert before["alert_latched"] is True
    assert before["last_tier"] == "evacuate_or_hold"
    supervisor.local_api.reset_alert()
    assert supervisor.gpio.sasmex_active is False
    assert supervisor.gpio.siren_sounding is False
    # [T-2.26] El reset también re-arma el MOTOR: sin esto el banner del panel
    # quedaba en alerta para siempre si SeedLink no traía features nuevas.
    after = supervisor.local_api.status()
    assert after["last_tier"] == "normal"
    assert after["alert_latched"] is False


def test_status_exposes_alert_latched_for_rules_demand_only(supervisor):
    # El estado irrecuperable del 2026-08-01: tier normal, relés aún enclavados.
    from takab_edge.contracts import ActuatorChannel

    supervisor.gpio.activate(ActuatorChannel.GAS_VALVE)
    status = supervisor.local_api.status()
    assert status["alert_latched"] is True
    assert status["sasmex_active"] is False


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


def test_http_reset_releases_tier_and_latch(supervisor):
    supervisor.gpio.simulate_sasmex(active=True)
    assert _post(supervisor.local_api, "/api/reset") == 200
    _, body = _get(supervisor.local_api, "/api/status")
    data = json.loads(body)
    assert data["last_tier"] == "normal"
    assert data["alert_latched"] is False


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


# --- Fase 2.1 · T-2.16/17/18/21: exponer la memoria viva en /api/status --------
# Contrato CONGELADO en la §5.1 de la spec de diseño del panel: claves, unidades
# y semántica de null. Toda sección nueva es defensiva (roto ⇒ null, GET 200).


class _RotoAttr:
    """Descriptor de DATOS (get+set): rompe atributos de instancia, no solo properties."""

    def __get__(self, *_):
        raise RuntimeError("kaput")

    def __set__(self, *_):
        raise RuntimeError("kaput")


def _panel_minimo(supervisor):
    """Panel SIN seedlink/config/signal cableados (instalación parcial)."""
    from takab_edge.local_api import LocalDashboard

    return LocalDashboard(supervisor.gpio, supervisor.rules, supervisor.health)


def test_status_exposes_live_thresholds_and_config_version(supervisor):
    status = supervisor.local_api.status()
    band = supervisor.settings.thresholds
    assert status["thresholds"] == {
        "pga_watch_g": band.pga_watch_g,
        "pga_trip_g": band.pga_trip_g,
        "pgv_watch_cms": band.pgv_watch_cms,
        "pgv_trip_cms": band.pgv_trip_cms,
    }
    assert status["config_version"] == 0  # jamás sincronizada: corre sus defaults


def test_thresholds_reflect_signed_update(supervisor):
    """T-1.71: el panel pinta los umbrales VIGENTES en el motor, no los estáticos."""
    updated = supervisor.settings.model_copy(deep=True)
    updated.thresholds.pga_trip_g = 0.123
    raw = updated.model_dump_json().encode()
    signature = supervisor.security.sign_config(raw, 7)
    supervisor.config.apply_signed_update(raw, signature, 7)
    status = supervisor.local_api.status()
    assert status["thresholds"]["pga_trip_g"] == 0.123
    assert status["config_version"] == 7


def test_thresholds_null_when_rules_broken(supervisor, monkeypatch):
    # raising=False: `thresholds` vive en la instancia; el descriptor de DATOS en
    # la clase lo eclipsa (los data descriptors ganan al __dict__ de la instancia).
    monkeypatch.setattr(type(supervisor.rules), "thresholds", _RotoAttr(), raising=False)
    code, body = _get(supervisor.local_api, "/api/status")
    assert code == 200
    assert json.loads(body)["thresholds"] is None


def test_latencies_budgets_declared_and_null_before_measurement(supervisor):
    """Sin medición ⇒ null (S/D). JAMÁS un 0.0 fabricado que se lea 'instantáneo'."""
    assert supervisor.local_api.status()["latencies"] == {
        "reflex_s": None,
        "reflex_budget_s": 0.100,
        "rules_s": None,
        "rules_budget_s": 0.200,
    }


def test_latencies_after_measurement(supervisor):
    from takab_edge.contracts import WaveformPacket, utcnow

    supervisor.gpio.simulate_sasmex(active=True)  # mide el reflejo SASMEX→relé
    supervisor.seedlink.feed(  # mide la evaluación del motor de reglas
        WaveformPacket(station="R4F74", channel="ENZ", starttime=utcnow(), samples=[0, 5] * 50)
    )
    latencies = supervisor.local_api.status()["latencies"]
    assert latencies["reflex_s"] is not None and latencies["reflex_s"] > 0.0
    assert latencies["rules_s"] is not None and latencies["rules_s"] > 0.0
    assert latencies["reflex_budget_s"] == 0.100  # los presupuestos no cambian


def test_seedlink_counters_exposed_since_boot(supervisor):
    from takab_edge.contracts import WaveformPacket, utcnow

    supervisor.seedlink.feed(
        WaveformPacket(station="R4F74", channel="EHZ", starttime=utcnow(), samples=[0, 1] * 50)
    )
    section = supervisor.local_api.status()["seedlink"]
    assert set(section) == {"packets_seen", "reconnects", "duplicates", "gaps"}
    assert section["packets_seen"] >= 1  # acumulado DESDE EL ARRANQUE
    assert all(isinstance(v, int) and v >= 0 for v in section.values())


def test_seedlink_section_null_without_client(supervisor):
    assert _panel_minimo(supervisor).status()["seedlink"] is None


def test_calibration_default_deny(supervisor):
    """Sin procedencia declarada NUNCA se reporta calibrado (espejo de la nube)."""
    calibration = supervisor.local_api.status()["calibration"]
    assert calibration["calibrated"] is False  # defaults placeholder ⇒ SIN CALIBRAR
    assert calibration["source"] is None
    assert calibration["vel_sensitivity_ms_per_count"] == pytest.approx(1.0e-9)
    assert calibration["accel_sensitivity_ms2_per_count"] == pytest.approx(1.0e-6)
    # Procedencia de puro espacio en blanco tampoco cuenta (default-deny estricto).
    supervisor.signal.config = supervisor.signal.config.model_copy(
        update={"calibration_source": "   "}
    )
    assert supervisor.local_api.status()["calibration"]["calibrated"] is False
    # Panel sin módulo de señal: la sección NUNCA es null — degrada a no-calibrado.
    degraded = _panel_minimo(supervisor).status()["calibration"]
    assert degraded == {
        "calibrated": False,
        "source": None,
        "vel_sensitivity_ms_per_count": None,
        "accel_sensitivity_ms2_per_count": None,
    }


def test_status_health_includes_ups_runtime(supervisor):
    """[T-2.22] `health.ups_runtime_s` llega al panel (hereda el age_s del cache)."""
    health = supervisor.local_api.status()["health"]
    assert "ups_runtime_s" in health
    # En dev no hay upsc ⇒ None; con UPS real es una medición en segundos.
    assert health["ups_runtime_s"] is None or isinstance(health["ups_runtime_s"], float)


def test_calibration_with_source_is_true(supervisor):
    supervisor.signal.config = supervisor.signal.config.model_copy(
        update={
            "calibration_source": "StationXML FDSN AM.R4F74 2026-07-09",
            "vel_sensitivity_ms_per_count": 2.5021894e-9,
            "accel_sensitivity_ms2_per_count": 2.6007802e-6,
        }
    )
    calibration = supervisor.local_api.status()["calibration"]
    assert calibration["calibrated"] is True
    assert calibration["source"] == "StationXML FDSN AM.R4F74 2026-07-09"
    assert calibration["vel_sensitivity_ms_per_count"] == pytest.approx(2.5021894e-9)
    assert calibration["accel_sensitivity_ms2_per_count"] == pytest.approx(2.6007802e-6)


# --- Fase 2.1 · T-2.15: /api/waveform sobre HTTP ------------------------------


def _feed_wave(supervisor, channel: str = "EHZ", index: int = 0) -> None:
    from datetime import datetime, timedelta

    from takab_edge.contracts import WaveformPacket

    t0 = datetime(2026, 7, 30, 12, 0, 0, tzinfo=UTC)
    supervisor.seedlink.feed(
        WaveformPacket(
            station="R4F74",
            channel=channel,
            starttime=t0 + timedelta(seconds=index),
            samples=[0, 7] * 50,
        )
    )


def test_waveform_endpoint_incremental_over_http(supervisor):
    _feed_wave(supervisor, index=0)
    code, body = _get(supervisor.local_api, "/api/waveform?max_points=6000")
    assert code == 200
    first = json.loads(body)
    assert first["reset"] is True
    assert first["channels"]["EHZ"]["encoding"] == "raw"
    assert len(first["channels"]["EHZ"]["samples"]) == 100
    _feed_wave(supervisor, index=1)
    code, body = _get(
        supervisor.local_api,
        f"/api/waveform?since={first['cursor']}&channels=EHZ&max_points=6000",
    )
    incremental = json.loads(body)
    assert incremental["reset"] is False
    assert len(incremental["channels"]["EHZ"]["samples"]) == 100  # SOLO lo nuevo
    assert incremental["cursor"] > first["cursor"]


def test_waveform_with_signal_broken_returns_200_empty(supervisor, monkeypatch):
    """Módulo de señal caído + parámetros basura ⇒ 200 degradado, jamás 500/400."""
    monkeypatch.setattr(supervisor.local_api, "_signal", None)
    code, body = _get(supervisor.local_api, "/api/waveform?since=abc&max_points=zz")
    assert code == 200
    assert json.loads(body) == {
        "cursor": 0,
        "reset": True,
        "sample_rate": None,
        "decimation": 1,
        "channels": {},
    }


def test_waveform_does_not_publish_nor_probe(supervisor, monkeypatch):
    """Regresión hermana de test_status_does_not_publish_health: esto es SOLO LAN."""
    leaked = []
    supervisor.health.on_snapshot(leaked.append)
    monkeypatch.setattr(supervisor.cloud, "publish", lambda *a, **k: leaked.append(a))
    for _ in range(10):
        code, _ = _get(supervisor.local_api, "/api/waveform")
        assert code == 200
    assert leaked == []  # ni sondas ni publicaciones: el GET del guardia es pasivo


def test_index_has_no_external_resources(supervisor):
    """La LAN no tiene internet: el HTML no puede referenciar NADA externo.

    [T-2.23] Extendido: tampoco almacenamiento del navegador ni canales vivos —
    el PIN vive SOLO en memoria y el servidor de hilos no admite streams.
    """
    code, body = _get(supervisor.local_api, "/")
    assert code == 200
    html = body.decode()
    assert "ALERTA S" in html and "PROTÉJASE" in html  # banner MVP intacto
    for forbidden in (
        "googleapis",
        "cdn.",
        "https://",
        "http://",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "new WebSocket",
        "EventSource",
    ):
        assert forbidden not in html, f"recurso vetado en el panel: {forbidden}"
    # sin countdown ni magnitud preliminar (blueprint §14)
    assert "T-MINUS" not in html
    assert "countdown" not in html.lower()


def test_status_relays_empty_when_gpio_stopped(supervisor):
    """REGRESIÓN (journal 2026-07-30): GET durante el shutdown ⇒ 200, no 500.

    Reproduce la ventana real: el server HTTP sigue sirviendo (hilos daemon)
    cuando gpio ya ejecutó su `_on_stop`. `relays` degrada a [] — el panel pinta
    S/D — y el resto del status sobrevive.
    """
    supervisor.gpio.stop()
    code, body = _get(supervisor.local_api, "/api/status")
    assert code == 200
    payload = json.loads(body)
    assert payload["relays"] == []
    assert payload["gateway_id"] == supervisor.settings.gateway_id  # el resto vive


def test_status_relays_degrade_when_gpio_broken(supervisor, monkeypatch):
    """Último cinturón en el panel: si relay_states LANZA, la sección degrada a []."""

    def _kaput():
        raise RuntimeError("kaput")

    monkeypatch.setattr(supervisor.gpio, "relay_states", _kaput)
    code, body = _get(supervisor.local_api, "/api/status")
    assert code == 200
    assert json.loads(body)["relays"] == []


# --- Fase 2.1 · T-2.23: panel rediseñado + estáticos + catálogo ----------------

_DEMO_SCENES = (
    "reposo",
    "vigilancia",
    "alerta",
    "simulacro",
    "prueba_actuadores",
    "wr1",
    "sin_senal",
    "sin_nube",
    "arranque_frio",
    "dato_retenido",
)


def test_index_declares_demo_scenes(supervisor):
    """Las 10 escenas de §13.2 se pueden forzar con ?demo=<escena>."""
    _, body = _get(supervisor.local_api, "/")
    html = body.decode()
    for scene in _DEMO_SCENES:
        assert f"{scene}:" in html or f"'{scene}'" in html or f'"{scene}"' in html, scene
    assert "DEMO · NO ES ESTADO REAL" in html  # el modo demo se declara, jamás se disfraza


def test_index_contains_frozen_contract_hooks(supervisor):
    """Literales del contrato §5.1/§9 que el panel DEBE hablar tal cual."""
    _, body = _get(supervisor.local_api, "/")
    html = body.decode()
    hooks = (
        "SIN CALIBRAR",
        "SIN UBICACIÓN PROVISIONADA",
        "CATÁLOGO NO DISPONIBLE",
        "DATO RETENIDO",
        "DESDE EL ARRANQUE",
        "ALERTA SÍSMICA · PROTÉJASE",
        "gap_before",
        "minmax",
        "X-Takab-Pin",
        # los cinco rótulos de tier, literales de §9.2
        "✓ NORMAL · SIN ALERTA",
        "▲ VIGILANCIA",
        "■ ACCESO RESTRINGIDO",
        "■ EVACUAR / RESGUARDO",
        "⚠ MODO MANUAL — SENSORES DEGRADADOS",
        "SIN PIN CONFIGURADO",
        "PROTECCIÓN LOCAL ACTIVA",
        # [T-2.26] enclave visible: sin estos hooks el gabinete queda irrecuperable
        # desde el panel cuando el tier decae con relés aún enclavados.
        "alert_latched",
        "ACTUADORES ENCLAVADOS",
    )
    for hook in hooks:
        assert hook in html, hook


def test_index_pin_failure_is_loud(supervisor):
    """[UX post-incidente 2026-07-31] Un rechazo de PIN se GRITA, no se susurra.

    El disparo real del WR-1 salió a la nube porque un armado falló con 401 y el
    mensajito junto al input fue invisible a distancia de muro. El panel debe
    declarar el rechazo en un banner (`role=alert`) con el NOMBRE de la orden.
    """
    _, body = _get(supervisor.local_api, "/")
    html = body.decode()
    assert 'id="action-toast"' in html
    assert 'role="alert"' in html
    for hook in (
        "ORDEN RECHAZADA",
        "CAPTURE EL PIN DE 6 DÍGITOS",
        "LA ORDEN NO SE EJECUTÓ",
        "ORDEN NO ENVIADA",
    ):
        assert hook in html, hook


# --- T-2.29: calibrador del PUNTO 0 de la brújula --------------------------


def _feed_en_channels(supervisor, seconds: int = 3) -> None:
    from datetime import UTC, datetime, timedelta

    from simulators.rs4d import RS4DSimulator

    sim = RS4DSimulator(station=supervisor.settings.station)
    start = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
    for i in range(seconds):
        for ch in ("ENZ", "ENN", "ENE"):
            supervisor.seedlink.feed(sim.packet(ch, start + timedelta(seconds=i)))


@pytest.fixture
def zero_supervisor(settings, tmp_path):
    """Supervisor con rose_zero_path escribible (el default apunta a /var/lib)."""
    from takab_edge.supervisor import EdgeSupervisor

    s = settings.model_copy(update={"rose_zero_path": str(tmp_path / "rose-zero.json")})
    sup = EdgeSupervisor(s, seedlink_source=None)
    sup.start()
    try:
        yield sup
    finally:
        sup.stop()


def test_rose_zero_captures_dc_and_persists(zero_supervisor, tmp_path):
    """El PUNTO 0 captura la media por canal EN* (gravedad + bias) y persiste."""
    _feed_en_channels(zero_supervisor)
    assert _post(zero_supervisor.local_api, "/api/rose-zero") == 200
    status = zero_supervisor.local_api.status()
    zero = status["rose_zero"]
    assert zero is not None and zero["set_at"]
    # DC del simulador: ENZ ≈ 3.77e6 (gravedad), ENN > 0, ENE < 0.
    assert abs(zero["channels"]["ENZ"] - 3_770_000) < 40_000
    assert zero["channels"]["ENN"] > 5_000
    assert zero["channels"]["ENE"] < -3_000
    # Persistencia atómica: otro panel que lea el MISMO archivo ve el punto 0
    # (equivale a un reinicio del servicio).
    from takab_edge.local_api import LocalDashboard

    reread = LocalDashboard(
        zero_supervisor.gpio,
        zero_supervisor.rules,
        zero_supervisor.health,
        port=0,
        dev_mode=True,
        rose_zero_path=str(tmp_path / "rose-zero.json"),
    )
    zero2 = reread.status()["rose_zero"]
    assert zero2 is not None
    assert zero2["channels"] == zero["channels"]


def test_rose_zero_without_signal_is_409_and_does_not_set(supervisor):
    """Sin datos en el ring no hay nada que calibrar: 409 y rose_zero sigue null."""
    assert _post(supervisor.local_api, "/api/rose-zero") == 409
    assert supervisor.local_api.status()["rose_zero"] is None


def test_rose_zero_requires_pin_when_configured(pinned):
    assert _post(pinned, "/api/rose-zero") == 401


def test_index_rose_zero_hooks(supervisor):
    """[T-2.29] La brújula declara su cero y su escala; el botón exige PIN."""
    _, body = _get(supervisor.local_api, "/")
    html = body.decode()
    for hook in (
        "CALIBRAR BRÚJULA",
        "PUNTO 0",
        "rose_zero",
        "MEDIA RODANTE",
        "PUNTO 0 FIJADO",
        "api/rose-zero",
    ):
        assert hook in html, hook


def test_index_comparativa_hooks(supervisor):
    """[T-2.27] Comparativa sismo↔estación: hooks congelados del contrato.

    La curva es una ESTIMACIÓN determinista (ley ATTEN-LAW v1, espejo de
    ``_plausible_pga_g`` — jamás en el camino de disparo) y NUNCA se presenta
    como dato medido; el medido solo aparece con los tres candados (estación
    propia + bucket temporal + calibración). NO es el mini-ShakeMap del
    blueprint §14: cero interpolación espacial, cero IA.
    """
    _, body = _get(supervisor.local_api, "/")
    html = body.decode()
    for hook in (
        "ESTIMACIÓN TEÓRICA · LEY DE ATENUACIÓN SIMPLE — NO ES DATO MEDIDO",
        "ATTEN-LAW v1: log10(PGA_g) = 0.5*M - 2.8 - log10(max(R_hipo_km, 1))",
        "DISTANCIA EPICENTRAL",
        "DISTANCIA HIPOCENTRAL",
        "ARRIBO P TEÓRICO",
        "V_P_KM_S",
        "SSN_UTC_OFFSET_H",
        "SELECCIONE UN SISMO PARA COMPARAR",
        "SOLO LA ESTACIÓN PROPIA MIDE",
        "SIN DATO MEDIDO EN ESTA VENTANA",
        "PGA RELATIVO · SIN CALIBRAR — NO COMPARABLE",
        "SIN PROFUNDIDAD REPORTADA",
        "BANDA ILUSTRATIVA",
        'id="cmp-drawer"',
        'id="cmp-canvas"',
    ):
        assert hook in html, hook


def test_index_removes_dc_before_physical_units(supervisor):
    """[T-2.25] El panel resta la media rodante DC ANTES de convertir a unidades
    físicas: counts crudos (gravedad ≈1 g en ENZ + bias MEMS en ENN/ENE) contra
    una escala en g de-media clavaban brújula y sismograma al máximo permanente.
    """
    _, body = _get(supervisor.local_api, "/")
    html = body.decode()
    assert "media rodante DC" in html
    assert html.count("- b.dc") >= 3  # windowOf (min y max) + lastCounts de la rosa
    assert "dcReady" in html


def test_index_polls_single_chained_tick(supervisor):
    """UN solo tick secuencial encadenado (hilos del Pi): cero bucles paralelos."""
    _, body = _get(supervisor.local_api, "/")
    html = body.decode()
    assert html.count("setTimeout(tick") == 1
    assert "setInterval" not in html


def test_static_fonts_served_with_mime_and_cache(supervisor):
    for path, mime in (("/fonts/geist.ttf", "font/ttf"), ("/fonts/jbmono.woff2", "font/woff2")):
        with urllib.request.urlopen(_url(supervisor.local_api, path), timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == mime
            assert "max-age=86400" in response.headers.get("Cache-Control", "")
            assert len(response.read()) > 1000  # la fuente de verdad viaja, no un stub


def test_static_unknown_path_is_404(supervisor):
    for path in ("/fonts/otra.ttf", "/fonts/../__init__.py", "/fonts/", "/assets/x.svg"):
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(_url(supervisor.local_api, path), timeout=5)
        assert exc.value.code == 404, path


def test_catalog_endpoint_degrades_honestly(supervisor, tmp_path):
    """Sin archivo ⇒ available:false y el panel rotula CATÁLOGO NO DISPONIBLE."""
    code, body = _get(supervisor.local_api, "/api/catalog")
    assert code == 200
    payload = json.loads(body)
    assert payload["available"] is False
    assert payload["events"] == [] and payload["references"] == []
    # Con la instantánea instalada (formato del entregable de diseño): se normaliza.
    snapshot = {
        "fuente": "Servicio Sismológico Nacional (SSN) · Instituto de Geofísica, UNAM",
        "capturado": "2026-05-17T08:11:22-06:00",
        "replicas_nota": "réplicas en curso",
        "eventos": [
            {
                "m": 4.0,
                "fecha": "2026-05-17",
                "hora": "08:11:22",
                "lat": 16.623,
                "lon": -93.275,
                "prof": 214.2,
                "loc": "19 km al SURESTE de OCOZOCOAUTLA, CHIS.",
            }
        ],
        "referencias": [{"n": "CDMX", "lat": 19.4326, "lon": -99.1332}],
    }
    catalog_file = tmp_path / "ssn-catalog.json"
    catalog_file.write_text(json.dumps(snapshot), "utf-8")
    from takab_edge.local_api import LocalDashboard

    dash = LocalDashboard(
        supervisor.gpio,
        supervisor.rules,
        supervisor.health,
        catalog_path=str(catalog_file),
    )
    served = dash.catalog()
    assert served["available"] is True
    assert served["captured_at"] == "2026-05-17T08:11:22-06:00"
    event = served["events"][0]
    assert event["m"] == 4.0 and event["depth_km"] == 214.2
    assert event["at"] == "2026-05-17 08:11:22"
    assert event["place"].endswith("CHIS.")
    assert served["references"][0]["n"] == "CDMX"
    # Corrupto ⇒ degradación idéntica a ausente (jamás un 500 al construir).
    catalog_file.write_text("esto{no-es-json", "utf-8")
    broken = LocalDashboard(
        supervisor.gpio,
        supervisor.rules,
        supervisor.health,
        catalog_path=str(catalog_file),
    )
    assert broken.catalog()["available"] is False


# --- T-2.31 · perfil de equipamiento ----------------------------------------


def test_status_relays_filtered_by_equipment(supervisor):
    """[T-2.31] El panel pinta SOLO los actuadores instalados en el sitio; el
    cambio aplica EN CALIENTE (el store reemplaza el settings) y gpio conserva
    sus 5 relés (el filtro es de presentación/secuencia, no de hardware)."""
    from takab_edge.config import EquipmentProfile

    baseline = {r["channel"] for r in supervisor.local_api.status()["relays"]}
    assert baseline == {"siren", "strobe", "gas_valve", "elevator", "door_retainer"}

    supervisor.config.settings = supervisor.config.settings.model_copy(
        update={"equipment": EquipmentProfile(gas_valve=False, elevator=False)}
    )
    filtered = {r["channel"] for r in supervisor.local_api.status()["relays"]}
    assert filtered == {"siren", "strobe", "door_retainer"}
    assert len(supervisor.gpio.relay_states()) == 5


# --- T-2.32 · política de quórum -------------------------------------------


def test_status_exposes_network_alert_and_reset_clears_it(supervisor):
    """[T-2.32] La fuente «QUÓRUM RED» viaja en status() y CERRAR ALERTA la
    cierra junto con el resto (gpio→rules→network)."""
    assert supervisor.local_api.status()["network_alert"] is None
    supervisor.dispatch._network_alert = {
        "event_id": "EVT-QRED-9",
        "at": "2026-08-03T12:00:00+00:00",
        "channels": ["siren"],
    }
    assert supervisor.local_api.status()["network_alert"]["event_id"] == "EVT-QRED-9"

    supervisor.local_api.reset_alert()
    assert supervisor.local_api.status()["network_alert"] is None


def test_index_quorum_policy_hooks(supervisor):
    """[T-2.32] Rótulos congelados de la política: el rojo es exclusivo de
    actuación real (SASMEX/QUÓRUM RED); el umbral instrumental es AVISO ámbar."""
    _, body = _get(supervisor.local_api, "/")
    html = body.decode()
    for hook in (
        'id="banner-aviso"',
        "AVISO SÍSMICO · MOVIMIENTO FUERTE (UMBRAL INSTRUMENTAL)",
        "SOLO AVISO · SIN ACTUACIÓN",
        "QUÓRUM RED",
        "network_alert",
        "aviso:",  # escena demo nueva (las 10 originales quedan intactas)
    ):
        assert hook in html, hook


# --- T-2.30 · responsive / solapamientos -----------------------------------


def test_index_responsive_overlap_fixes(supervisor):
    """[T-2.30] Fixes de layout verificados por el barrido headless multi-viewport:
    el overlay del mapa se apila en modo CAMPO (columna fija de 420px desbordaba
    en teléfono), el cajón comparativo se acota, la bitácora desplaza en vez de
    recortar y los relés fluyen con auto-fit (pre-habilita perfiles de
    equipamiento con menos de 5 actuadores).
    """
    _, body = _get(supervisor.local_api, "/")
    html = body.decode()
    for hook in (
        "repeat(auto-fit,minmax(",  # relés fluyen: 5 hoy, 4/6 mañana sin tocar CSS
        'id="overlay-side"',  # panel derecho del modal con identidad propia
        "body.mode-campo #overlay",  # el modal TIENE reglas campo (apilado)
        "body.mode-campo #cmp-drawer",  # cajón acotado en pantallas bajas
        "overflow:hidden auto",  # bitácora: x oculto, y desplazable
        "body.mode-campo #rose-wrap",  # la brújula colapsaba a 0 px en teléfono
        "body.mode-muro header",  # muro forzado en angosto: crece, no desborda
        "@media (max-width:699px)",  # modal apilado en angosto SEA CUAL SEA el modo
    ):
        assert hook in html, hook
