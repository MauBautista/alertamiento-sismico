"""local_api — mini-consola local del inmueble (LAN, sin internet).

T-1.13: servidor HTTP mínimo (stdlib `http.server`, sin dependencias pesadas) accesible
en la LAN del edificio SIN internet (RBAC §4.2: fallback cuando la WAN está caída).

T-1.43: las ACCIONES (POST) exigen un PIN (`X-Takab-Pin`, comparación constant-time,
lockout tras 5 PINs erróneos) — la segmentación de red dejó de ser la única barrera para
silenciar la sirena de un edificio. La LECTURA (GET) sigue abierta en la LAN: es el panel
del guardia. Sin PIN configurado: `dev_mode` queda abierto (tests/demo); producción
responde 403 fail-closed hasta que `provision_gateway.sh` instale uno.

T-1.53: de panel mínimo a MINI-CONSOLA del inmueble (decisión de Mauricio 2026-07-10):
PGA/PGV en vivo por canal (`signal.live_by_channel`), salud completa del gabinete,
estado del enlace a nube ("SIN ENLACE — PROTECCIÓN LOCAL ACTIVA": aislado ≠ desprotegido)
y últimos eventos locales. Dos reglas de diseño duras:

- **`status()` JAMÁS ejecuta sondas ni publica.** Antes llamaba `health.snapshot()`,
  que lanza subprocesos (chronyc/upsc/openssl, hasta 2 s c/u) Y dispara los callbacks
  cableados a `cloud.publish` — cada GET del panel publicaba un health a la nube
  (~30/min con el poll de 2 s en vez del heartbeat de 60 s). Ahora lee el CACHE
  (`health.last_snapshot`) y declara su edad; la UI la rotula.
- **Secciones DEFENSIVAS**: un módulo caído degrada su sección a `null` y el GET
  responde 200 con lo que sí hay — el panel del guardia no muere porque una pieza
  no-crítica falle (misma doctrina que el aislamiento del supervisor).

El HTML vive como recurso empaquetado (`index.html`, cero build, cero CDN: la LAN no
tiene internet) y el JS hace polling con `setTimeout` encadenado y backoff — sin SSE:
con ThreadingHTTPServer un stream retiene un hilo por kiosco y no aporta nada a 1 Hz.
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
import time
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from takab_edge.contracts import utcnow
from takab_edge.gpio import GpioController
from takab_edge.health import HealthMonitor
from takab_edge.module import EdgeModule
from takab_edge.rules import RuleEngine

log = logging.getLogger("takab_edge.local_api")

#: Lockout del PIN: tras N erróneos, las acciones se bloquean este tiempo.
_PIN_MAX_FAILURES = 5
_PIN_LOCKOUT_S = 60.0

#: Sin feature nueva tras esto, el canal se declara "SIN SEÑAL" en la UI.
_SIGNAL_STALE_S = 5.0

#: Tope de acciones LAN recordadas para la lista de eventos del panel.
_ACTIONS_MAX = 16
#: Tope de filas de la lista de eventos servida por /api/status.
_EVENTS_MAX = 10

# Fallback si el recurso index.html faltara (instalación rota): el panel sigue
# siendo operable vía /api/status y las acciones; jamás un 500 por el HTML.
_FALLBACK_HTML = (
    "<!doctype html><meta charset='utf-8'><title>TAKAB Ailert</title>"
    "<p>Panel sin index.html empaquetado; usa /api/status.</p>"
)


def _load_index_html() -> str:
    try:
        return resources.files("takab_edge.local_api").joinpath("index.html").read_text("utf-8")
    except OSError:
        log.error("index.html del panel LAN no encontrado; se sirve el fallback")
        return _FALLBACK_HTML


class _DashboardHandler(BaseHTTPRequestHandler):
    # keep-alive: un hilo por kiosco en vez de hilo por request (menos churn).
    protocol_version = "HTTP/1.1"

    def _send(self, code: int, body: str, content_type: str = "application/json") -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if content_type.startswith("application/json"):
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        dashboard = self.server.dashboard  # type: ignore[attr-defined]
        if self.path in ("/", "/index.html"):
            self._send(200, dashboard.index_html, "text/html; charset=utf-8")
        elif self.path == "/api/status":
            # El GET del guardia no puede reventar por un módulo caído: status()
            # ya es defensivo por sección; esto es el último cinturón.
            try:
                self._send(200, json.dumps(dashboard.status()))
            except Exception:  # noqa: BLE001 — panel no-crítico, jamás traceback al socket
                log.exception("status() del panel LAN falló")
                self._send(500, json.dumps({"error": "status"}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self) -> None:
        dashboard = self.server.dashboard  # type: ignore[attr-defined]
        actions = {
            "/api/silence": dashboard.silence,
            "/api/siren-test": dashboard.run_siren_test,
            "/api/reset": dashboard.reset_alert,
            "/api/drill-audio": dashboard.drill_audio,
        }
        action = actions.get(self.path)
        if action is None:
            self._send(404, json.dumps({"error": "not found"}))
            return
        # Autorización ANTES de tocar GPIO (T-1.43): silenciar la sirena de un
        # edificio no puede depender solo de estar en la misma LAN.
        code = dashboard.authorize_action(self.headers.get("X-Takab-Pin"))
        if code != 200:
            self._send(code, json.dumps({"error": "pin"}))
            return
        action()
        self._send(200, json.dumps({"ok": True}))

    def log_message(self, *args: object) -> None:  # no spamear stdout del edge
        pass


class _DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[int, int], dashboard: LocalDashboard) -> None:
        self.dashboard = dashboard
        super().__init__(address, _DashboardHandler)


class LocalDashboard(EdgeModule):
    """Mini-consola LAN del inmueble: estado vivo + acciones con PIN (T-1.53)."""

    name = "local_api"
    depends_on = ("gpio", "rules", "health", "signal", "cloud")

    def __init__(
        self,
        gpio: GpioController,
        rules: RuleEngine,
        health: HealthMonitor,
        host: str = "0.0.0.0",  # noqa: S104 — LAN del gabinete por diseño
        port: int = 8080,
        pin: str = "",
        dev_mode: bool = True,
        *,
        signal: object | None = None,
        cloud: object | None = None,
        gateway_id: str = "",
        site_name: str = "",
        refresh_ms: int = 1000,
        audio: object | None = None,
        drill: object | None = None,
    ) -> None:
        super().__init__()
        self._gpio = gpio
        self._rules = rules
        self._health = health
        self._signal = signal
        self._cloud = cloud
        self._audio = audio
        self._drill = drill
        self._gateway_id = gateway_id
        self._site_name = site_name
        self._refresh_ms = refresh_ms
        self._host = host
        self._port = port
        self._pin = pin
        self._dev_mode = dev_mode
        self._auth_lock = threading.Lock()
        self._auth_failures = 0
        self._locked_until = 0.0
        self._server: _DashboardServer | None = None
        self._thread: threading.Thread | None = None
        self._started_at: datetime | None = None
        # Acciones LAN recordadas para la lista de eventos (append desde los
        # hilos HTTP; lectura desde status()): lock propio.
        self._actions: deque[dict] = deque(maxlen=_ACTIONS_MAX)
        self._actions_lock = threading.Lock()
        self.index_html = _load_index_html()

    def authorize_action(self, provided: str | None) -> int:
        """Autoriza un POST del panel (T-1.43). Devuelve el status HTTP.

        - 200: PIN correcto, o sin PIN configurado en ``dev_mode``.
        - 401: sin header (sondeo de la página — NO cuenta para el lockout) o
          PIN erróneo (SÍ cuenta; comparación constant-time).
        - 403: producción sin PIN provisionado — fail-closed hasta que
          ``provision_gateway.sh`` instale uno.
        - 429: lockout activo (5 PINs erróneos ⇒ 60 s bloqueado).
        """
        if not self._pin:
            return 200 if self._dev_mode else 403
        with self._auth_lock:
            if self._locked_until > time.monotonic():
                return 429
            if provided is None:
                return 401  # la página pregunta el PIN; no es un intento fallido
            if hmac.compare_digest(provided.encode(), self._pin.encode()):
                self._auth_failures = 0
                return 200
            self._auth_failures += 1
            if self._auth_failures >= _PIN_MAX_FAILURES:
                self._auth_failures = 0
                self._locked_until = time.monotonic() + _PIN_LOCKOUT_S
                log.warning("panel LAN: lockout por PIN erróneo (%.0f s)", _PIN_LOCKOUT_S)
            return 401

    # ------------------------------------------------------------- secciones
    # Cada sección es defensiva: un módulo roto ⇒ null, jamás un 500 del panel.

    def _signal_section(self, now: datetime) -> dict | None:
        try:
            live = self._signal.live_by_channel() if self._signal is not None else None
        except Exception:  # noqa: BLE001 — sección no-crítica
            log.warning("panel LAN: sección signal falló", exc_info=True)
            return None
        if live is None:
            return None
        channels: dict[str, dict] = {}
        last_received: datetime | None = None
        for channel, (feature, received_at) in sorted(live.items()):
            channels[channel] = {
                "pga_g": feature.pga,
                "pgv_cms": feature.pgv,
                "rms": feature.rms,
                "sta_lta": feature.sta_lta,
                "clipping": feature.clipping,
                "health_score": feature.health_score,
                "window_start": feature.window_start.isoformat(),
                "received_at": received_at.isoformat(),
                "age_s": max(0.0, (now - received_at).total_seconds()),
            }
            if last_received is None or received_at > last_received:
                last_received = received_at
        return {
            "channels": channels,
            "last_received_at": last_received.isoformat() if last_received else None,
            "stale_after_s": _SIGNAL_STALE_S,
        }

    def _health_section(self, now: datetime) -> dict | None:
        try:
            snap = self._health.last_snapshot
        except Exception:  # noqa: BLE001
            log.warning("panel LAN: sección health falló", exc_info=True)
            return None
        if snap is None:
            return None
        return {
            "ntp_offset_s": snap.ntp_offset_s,
            "seedlink_lag_s": snap.seedlink_lag_s,
            "packet_loss_pct": snap.packet_loss_pct,
            "mqtt_rtt_ms": snap.mqtt_rtt_ms,
            "ups_status": snap.ups_status.value,
            "battery_pct": snap.battery_pct,
            "temperature_c": snap.temperature_c,
            "cert_days_remaining": snap.cert_days_remaining,
            "disk_used_pct": snap.disk_used_pct,
            "captured_at": snap.captured_at.isoformat(),
            "age_s": max(0.0, (now - snap.captured_at).total_seconds()),
        }

    def _cloud_section(self) -> dict:
        try:
            if self._cloud is None:
                return {"online": False, "mqtt_rtt_ms": None, "queued": None}
            rtt = getattr(self._cloud, "mqtt_rtt_ms", None)
            return {
                "online": bool(getattr(self._cloud, "online", False)),
                "mqtt_rtt_ms": float(rtt) if rtt is not None else None,
                "queued": int(getattr(self._cloud, "queued", 0)),
            }
        except Exception:  # noqa: BLE001
            log.warning("panel LAN: sección cloud falló", exc_info=True)
            return {"online": False, "mqtt_rtt_ms": None, "queued": None}

    def _drill_section(self) -> dict | None:
        """[T-1.60] Estado del simulacro: banner NO-real y aborto visible."""
        if self._drill is None:
            return None
        try:
            return self._drill.status()
        except Exception:  # noqa: BLE001 — sección defensiva
            log.exception("panel: sección drill falló")
            return None

    def _events_section(self) -> list[dict]:
        try:
            transitions = self._rules.recent_transitions(_EVENTS_MAX)
        except Exception:  # noqa: BLE001
            log.warning("panel LAN: transiciones no disponibles", exc_info=True)
            transitions = []
        with self._actions_lock:
            actions = list(self._actions)
        merged = transitions + actions
        merged.sort(key=lambda item: item.get("at", ""), reverse=True)
        return merged[:_EVENTS_MAX]

    def _record_action(self, action: str) -> None:
        with self._actions_lock:
            self._actions.append({"at": utcnow().isoformat(), "action": action, "via": "lan"})

    def status(self) -> dict:
        """Snapshot para la mini-consola LAN (los 4 estados los rotula la UI)."""
        now = utcnow()
        try:
            decision = self._rules.last_decision
            last_tier = decision.tier.value if decision else None
        except Exception:  # noqa: BLE001
            log.warning("panel LAN: last_decision no disponible", exc_info=True)
            last_tier = None
        health = self._health_section(now)
        uptime = (now - self._started_at).total_seconds() if self._started_at else None
        return {
            # Identidad VIVA (settings), no del snapshot: sobrevive a health caído.
            "gateway_id": self._gateway_id
            or (self._health.last_snapshot.gateway_id if self._health.last_snapshot else ""),
            "site_name": self._site_name,
            "now": now.isoformat(),
            "uptime_s": uptime,
            "refresh_ms": self._refresh_ms,
            # Distinguir alerta REAL vs. sirena sonando vs. silenciado (regla de oro 7):
            "sasmex_active": self._gpio.sasmex_active,
            "siren_sounding": self._gpio.siren_sounding,
            "audible_silenced": self._gpio.audible_silenced,
            "last_tier": last_tier,
            "relays": [r.model_dump(mode="json") for r in self._gpio.relay_states()],
            # Compat con el panel previo: hora del último dato de salud (o ahora).
            "captured_at": (health or {}).get("captured_at", now.isoformat()),
            "signal": self._signal_section(now),
            "health": health,
            "cloud": self._cloud_section(),
            "drill": self._drill_section(),
            "audio": self._audio_section(),
            "events": self._events_section(),
        }

    def _audio_section(self) -> dict | None:
        """Voceo (A-6): la UI solo muestra el botón de drill si está habilitado."""
        try:
            if self._audio is None:
                return None
            return {"enabled": bool(self._audio.enabled), "sounding": bool(self._audio.sounding)}
        except Exception:  # noqa: BLE001
            log.warning("panel LAN: sección de audio no disponible", exc_info=True)
            return None

    def silence(self) -> None:
        """Comando de silencio por LAN: apaga los audibles YA (sin tocar el estrobo)."""
        self._gpio.silence_audibles(True)
        self._record_action("silence")
        log.warning("silencio solicitado por LAN")

    def run_siren_test(self) -> None:
        """Prueba de sirena por LAN (self-test acotado, no es una alerta real)."""
        self._gpio.run_siren_test()
        self._record_action("siren_test")
        log.warning("prueba de sirena solicitada por LAN")

    def reset_alert(self) -> None:
        """Cierra/re-arma la alerta enclavada por LAN (vuelve a operación normal)."""
        self._gpio.reset()
        if self._audio is not None:
            # La alerta terminó: la voz también se calla (A-6).
            try:
                self._audio.stop_playback()
            except Exception:  # noqa: BLE001 — advisory
                log.exception("audio.stop_playback() en reset falló (aislado)")
        self._record_action("reset")
        log.warning("alerta cerrada/re-armada por LAN")

    def drill_audio(self) -> None:
        """Voceo de SIMULACRO por LAN (A-6): mensaje de drill, SIN tocar relés."""
        if self._audio is None:
            log.warning("drill de voceo solicitado sin módulo de audio")
            return
        self._audio.play_simulacro()
        self._record_action("drill_audio")
        log.warning("voceo de SIMULACRO solicitado por LAN")

    @property
    def address(self) -> tuple[str, int] | None:
        """Dirección real de escucha (útil con puerto efímero en tests)."""
        return self._server.server_address if self._server else None

    def _on_start(self) -> None:
        self._started_at = utcnow()
        self._server = _DashboardServer((self._host, self._port), self)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="local-api", daemon=True
        )
        self._thread.start()
        host, port = self._server.server_address
        log.info("mini-consola LAN en http://%s:%d (sin internet)", host, port)

    def _on_stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
