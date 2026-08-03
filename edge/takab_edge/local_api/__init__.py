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
import os
import threading
import time
import urllib.parse
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path

from takab_edge.catalog import DEGRADED as _CATALOG_DEGRADED
from takab_edge.catalog import CatalogStore
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

#: Presupuestos de la cadena crítica (§4.3 del blueprint): la UI pinta las
#: latencias MEDIDAS contra estos, no en el vacío. Nacen aquí (T-2.17) porque
#: son un contrato del panel, no un parámetro operable del gabinete.
_REFLEX_BUDGET_S = 0.100  # reflejo SASMEX→relé, p95
_RULES_BUDGET_S = 0.200  # evaluación del motor de reglas, p95

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


class ActionUnavailable(RuntimeError):
    """[T-2.29] Orden válida que AHORA no puede cumplirse (p.ej. sin señal).

    El handler la traduce a 409: el operador ve por qué no pasó nada, en vez
    de un OK mentiroso o un 500 al kiosco.
    """


class RoseZeroStore:
    """[T-2.29] PUNTO 0 de la brújula del panel (presentación pura).

    Media de counts por canal EN* capturada con el gabinete YA instalado y
    nivelado: la brújula pasa a medir desviaciones respecto a la INSTALACIÓN,
    no respecto a una media rodante que absorbe inclinaciones sostenidas.
    Misma doctrina de archivo que `CatalogStore`: carga única, escritura
    atómica (tmp + os.replace), sin path ⇒ solo memoria (tests/parcial), y un
    archivo ilegible degrada a "sin calibrar" — jamás un cero inventado.
    Jamás toca umbrales, rules ni actuadores.
    """

    def __init__(self, path: str = "") -> None:
        self._path = Path(path) if path else None
        self._lock = threading.Lock()
        self._current: dict | None = None
        self._load_once()

    def _load_once(self) -> None:
        if self._path is None:
            return
        try:
            raw = json.loads(self._path.read_text("utf-8"))
            channels = raw.get("channels")
            if isinstance(channels, dict) and channels and raw.get("set_at"):
                self._current = {
                    "channels": {str(k): float(v) for k, v in channels.items()},
                    "set_at": str(raw["set_at"]),
                }
        except FileNotFoundError:
            log.info("punto 0 de la brújula aún no fijado (%s)", self._path)
        except Exception:  # noqa: BLE001 — presentación; ilegible ⇒ sin calibrar
            log.warning("punto 0 de la brújula ilegible (%s); se ignora", self._path, exc_info=True)

    def current(self) -> dict | None:
        with self._lock:
            return dict(self._current) if self._current else None

    def set(self, channels: dict[str, float]) -> dict:
        snapshot = {
            "channels": {str(k): float(v) for k, v in channels.items()},
            "set_at": utcnow().isoformat(),
        }
        with self._lock:
            self._current = snapshot
            if self._path is not None:
                try:
                    tmp = self._path.with_suffix(self._path.suffix + ".tmp")
                    tmp.write_text(json.dumps(snapshot), "utf-8")
                    os.replace(tmp, self._path)
                except Exception:  # noqa: BLE001 — sin disco sigue vivo en memoria
                    log.warning(
                        "no se pudo persistir el punto 0 (%s); queda en memoria",
                        self._path,
                        exc_info=True,
                    )
        return snapshot


def _waveform_params(query: str) -> tuple[int | None, list[str] | None, int | None]:
    """Parámetros de /api/waveform (T-2.15): ilegales ⇒ defaults, jamás 400 al kiosco."""
    params = urllib.parse.parse_qs(query)

    def _int(name: str) -> int | None:
        try:
            return int(params[name][0])
        except (KeyError, IndexError, ValueError):
            return None

    raw_channels = params.get("channels", [""])[0]
    channels = [c for c in raw_channels.split(",") if c] or None
    return _int("since"), channels, _int("max_points")


def _load_index_html() -> str:
    try:
        return resources.files("takab_edge.local_api").joinpath("index.html").read_text("utf-8")
    except OSError:
        log.error("index.html del panel LAN no encontrado; se sirve el fallback")
        return _FALLBACK_HTML


def _load_static_fonts() -> dict[str, tuple[str, bytes]]:
    """[T-2.23] Whitelist de estáticos, cargada UNA vez al construir el panel.

    Dict por ruta EXACTA ⇒ inmune a path traversal por construcción: cualquier
    otra ruta (incluido `/fonts/../`) es 404. Una fuente ausente simplemente no
    entra a la whitelist y la pila CSS cae a la del sistema.
    """
    served: dict[str, tuple[str, bytes]] = {}
    for name, mime in (("geist.ttf", "font/ttf"), ("jbmono.woff2", "font/woff2")):
        try:
            data = resources.files("takab_edge.local_api").joinpath(f"fonts/{name}").read_bytes()
            served[f"/fonts/{name}"] = (mime, data)
        except OSError:
            log.warning("fuente %s no empaquetada; la pila CSS cae al sistema", name)
    return served


# [T-2.24] La carga/normalización del catálogo vive en `takab_edge.catalog`
# (CatalogStore): mismo archivo, mismo contrato §5.1, y ahora con feed FIRMADO
# nube→edge. El panel solo LEE la instantánea viva del store.


class _DashboardHandler(BaseHTTPRequestHandler):
    # keep-alive: un hilo por kiosco en vez de hilo por request (menos churn).
    protocol_version = "HTTP/1.1"

    def _send(
        self,
        code: int,
        body: str | bytes,
        content_type: str = "application/json",
        cache_control: str | None = None,
    ) -> None:
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if cache_control is not None:
            self.send_header("Cache-Control", cache_control)
        elif content_type.startswith("application/json"):
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        dashboard = self.server.dashboard  # type: ignore[attr-defined]
        path, _, query = self.path.partition("?")
        if path in ("/", "/index.html"):
            self._send(200, dashboard.index_html, "text/html; charset=utf-8")
        elif path == "/api/status":
            # El GET del guardia no puede reventar por un módulo caído: status()
            # ya es defensivo por sección; esto es el último cinturón.
            try:
                self._send(200, json.dumps(dashboard.status()))
            except Exception:  # noqa: BLE001 — panel no-crítico, jamás traceback al socket
                log.exception("status() del panel LAN falló")
                self._send(500, json.dumps({"error": "status"}))
        elif path == "/api/waveform":
            # T-2.15: lectura abierta como /api/status (es el panel del guardia).
            # waveform() es defensivo de punta a punta: signal roto ⇒ 200 degradado.
            self._send(200, json.dumps(dashboard.waveform(*_waveform_params(query))))
        elif path == "/api/catalog":
            # T-2.23: instantánea SSN cacheada en memoria (leída UNA vez al construir).
            self._send(200, json.dumps(dashboard.catalog()))
        elif path in dashboard.static_files:
            # T-2.23: whitelist EXACTA (traversal imposible por construcción).
            mime, data = dashboard.static_files[path]
            self._send(200, data, mime, cache_control="public, max-age=86400")
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self) -> None:
        dashboard = self.server.dashboard  # type: ignore[attr-defined]
        actions = {
            "/api/silence": dashboard.silence,
            "/api/siren-test": dashboard.run_siren_test,
            "/api/actuator-test": dashboard.run_actuator_test,
            "/api/test-mode": dashboard.toggle_test_mode,
            "/api/reset": dashboard.reset_alert,
            "/api/drill-audio": dashboard.drill_audio,
            "/api/rose-zero": dashboard.set_rose_zero,  # T-2.29
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
        try:
            action()
        except ActionUnavailable as exc:
            # [T-2.29] La orden es válida pero AHORA no puede cumplirse (p.ej.
            # calibrar sin señal): 409 honesto, jamás un OK que no hizo nada.
            self._send(409, json.dumps({"error": str(exc)}))
            return
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
        seedlink: object | None = None,
        config: object | None = None,
        location: object | None = None,
        catalog: object | None = None,
        catalog_path: str = "",
        rose_zero_path: str = "",
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
        self._seedlink = seedlink
        self._config = config
        self._location = location
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
        self._last_actuation_test: dict | None = None  # T-1.67: resultado por relé
        self.index_html = _load_index_html()
        # T-2.23: estáticos y catálogo se cargan UNA vez — servir jamás toca disco.
        # T-2.24: el store compartido del supervisor trae el feed firmado; un
        # panel suelto (tests/parcial) construye uno de solo-lectura por path.
        self.static_files = _load_static_fonts()
        self._catalog_store = catalog if catalog is not None else CatalogStore(catalog_path)
        self._rose_zero = RoseZeroStore(rose_zero_path)  # T-2.29

    def catalog(self) -> dict:
        """[T-2.23/24] Instantánea SSN normalizada (§5.1). Lectura pura del store."""
        try:
            return self._catalog_store.current()
        except Exception:  # noqa: BLE001 — sección no-crítica
            log.warning("panel LAN: catálogo no disponible", exc_info=True)
            return dict(_CATALOG_DEGRADED)

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
            "ups_runtime_s": snap.ups_runtime_s,
            "temperature_c": snap.temperature_c,
            "cert_days_remaining": snap.cert_days_remaining,
            "disk_used_pct": snap.disk_used_pct,
            "captured_at": snap.captured_at.isoformat(),
            "age_s": max(0.0, (now - snap.captured_at).total_seconds()),
        }

    def waveform(
        self,
        since: int | None,
        channels: list[str] | None = None,
        max_points: int | None = None,
    ) -> dict:
        """[T-2.15] Ventana incremental de forma de onda (§5.1). SOLO LAN.

        Defensivo de punta a punta: sin módulo de señal, sin ring o con el ring
        roto responde la forma degradada con 200 — el kiosco pinta "sin ondas",
        jamás recibe un 500. Nada de esto publica ni sondea.
        """
        try:
            ring = getattr(self._signal, "waveform", None)
            if ring is None:
                raise RuntimeError("módulo de señal sin ring de waveform")
            return ring.serve(since, channels=channels, max_points=max_points)
        except Exception:  # noqa: BLE001 — panel no-crítico
            log.warning("panel LAN: waveform no disponible", exc_info=True)
            return {
                "cursor": since or 0,
                "reset": True,
                "sample_rate": None,
                "decimation": 1,
                "channels": {},
            }

    def _relays_section(self) -> list[dict]:
        """Relés para el panel — era la ÚNICA pieza de status() sin cinturón.

        gpio.relay_states() ya es seguro en shutdown (devuelve []); este guard
        cubre cualquier otro fallo: roto ⇒ [] y el panel pinta S/D, jamás un 500
        al kiosco (misma doctrina que el resto de las secciones).

        [T-2.31] Se pintan SOLO los actuadores instalados (perfil vivo del
        config store): mostrar un relé de gas en un sitio sin gas es un dato
        falso (regla de oro 7). gpio conserva sus 5 relés; el filtro es de
        presentación.
        """
        try:
            states = self._gpio.relay_states()
            if self._config is not None:
                equipment = self._config.current().equipment
                states = [r for r in states if equipment.has(r.channel)]
            return [r.model_dump(mode="json") for r in states]
        except Exception:  # noqa: BLE001 — sección no-crítica
            log.warning("panel LAN: relés no disponibles", exc_info=True)
            return []

    def _thresholds_section(self) -> dict | None:
        """[T-2.16] Umbrales VIGENTES en el motor (T-1.71: se reemplazan en vivo).

        No son los de `EdgeSettings` estáticos: tras un `apply_signed_update` el
        panel debe pintar la línea de umbral que de verdad dispara.
        """
        try:
            band = self._rules.thresholds
            return {
                "pga_watch_g": band.pga_watch_g,
                "pga_trip_g": band.pga_trip_g,
                "pgv_watch_cms": band.pgv_watch_cms,
                "pgv_trip_cms": band.pgv_trip_cms,
            }
        except Exception:  # noqa: BLE001 — sección no-crítica
            log.warning("panel LAN: umbrales no disponibles", exc_info=True)
            return None

    def _config_version(self) -> int | None:
        """[T-2.16] Versión de la config firmada aplicada (0 = corre defaults)."""
        try:
            return int(self._config.version) if self._config is not None else None
        except Exception:  # noqa: BLE001
            log.warning("panel LAN: versión de config no disponible", exc_info=True)
            return None

    def _latencies_section(self) -> dict:
        """[T-2.17] Latencias MEDIDAS de la cadena crítica, contra presupuesto.

        `null` = sin medición todavía (la UI pinta S/D). JAMÁS un 0.0 fabricado:
        un cero se leería como "instantáneo" y sería una mentira.
        """
        try:
            reflex = self._gpio.last_reflex_latency_s
        except Exception:  # noqa: BLE001
            log.warning("panel LAN: latencia de reflejo no disponible", exc_info=True)
            reflex = None
        try:
            rules = self._rules.last_latency_s
        except Exception:  # noqa: BLE001
            log.warning("panel LAN: latencia del motor no disponible", exc_info=True)
            rules = None
        return {
            "reflex_s": reflex,
            "reflex_budget_s": _REFLEX_BUDGET_S,
            "rules_s": rules,
            "rules_budget_s": _RULES_BUDGET_S,
        }

    def _seedlink_section(self) -> dict | None:
        """[T-2.18] Contadores del flujo SeedLink, acumulados DESDE EL ARRANQUE.

        Distinguen "el enlace se cae y se levanta" (`reconnects`) de "el Shake
        manda con huecos" (`gaps`) — lo que nadie pudo ver en las 15 h ciegas.
        """
        try:
            if self._seedlink is None:
                return None
            return {
                "packets_seen": int(self._seedlink.packets_seen),
                "reconnects": int(self._seedlink.reconnects),
                "duplicates": int(self._seedlink.duplicates),
                "gaps": int(self._seedlink.gaps),
            }
        except Exception:  # noqa: BLE001
            log.warning("panel LAN: contadores SeedLink no disponibles", exc_info=True)
            return None

    def _site_location(self) -> dict:
        """[T-2.20] Ubicación viva del sitio. `null` ⇒ SIN UBICACIÓN PROVISIONADA.

        Jamás un punto inventado ni un centro por defecto: un mapa centrado en
        el Zócalo cuando el gabinete está en Puebla es peor que no tener mapa.
        """
        empty = {"site_lat": None, "site_lon": None, "neighbors": []}
        try:
            return empty if self._location is None else self._location.current()
        except Exception:  # noqa: BLE001 — sección no-crítica
            log.warning("panel LAN: ubicación no disponible", exc_info=True)
            return empty

    def _shake_history_section(self) -> dict | None:
        """[T-2.19] Agregado rodante de sacudida (RAM, rotulado DESDE EL ARRANQUE)."""
        try:
            aggregate = getattr(self._signal, "aggregate", None)
            return None if aggregate is None else aggregate.snapshot()
        except Exception:  # noqa: BLE001 — sección no-crítica
            log.warning("panel LAN: shake_history no disponible", exc_info=True)
            return None

    def _calibration_section(self) -> dict:
        """[T-2.21] Calibración instrumental. NUNCA null; default-deny estricto.

        `calibrated` se DERIVA de la procedencia (`calibration_source` no vacío)
        — no existe un checkbox de "calibrado", igual que en la nube. Sin señal
        o roto ⇒ degrada a no-calibrado con sensibilidades null, jamás a null.
        """
        degraded = {
            "calibrated": False,
            "source": None,
            "vel_sensitivity_ms_per_count": None,
            "accel_sensitivity_ms2_per_count": None,
        }
        try:
            config = self._signal.config if self._signal is not None else None
            if config is None:
                return degraded
            source = config.calibration_source.strip()
            return {
                "calibrated": bool(source),
                "source": source or None,
                "vel_sensitivity_ms_per_count": config.vel_sensitivity_ms_per_count,
                "accel_sensitivity_ms2_per_count": config.accel_sensitivity_ms2_per_count,
            }
        except Exception:  # noqa: BLE001
            log.warning("panel LAN: calibración no disponible", exc_info=True)
            return degraded

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
        site = self._site_location()
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
            # [T-2.26] Enclave vivo (SASMEX o rules): el panel ofrece CERRAR
            # ALERTA mientras esto sea true, aunque el tier ya haya decaído.
            "alert_latched": self._gpio.alert_latched,
            "last_tier": last_tier,
            "relays": self._relays_section(),
            # Compat con el panel previo: hora del último dato de salud (o ahora).
            "captured_at": (health or {}).get("captured_at", now.isoformat()),
            # Fase 2.1 (contrato §5.1 de la spec del panel): memoria viva expuesta.
            "site_lat": site["site_lat"],
            "site_lon": site["site_lon"],
            "neighbors": site["neighbors"],
            "config_version": self._config_version(),
            "thresholds": self._thresholds_section(),
            "latencies": self._latencies_section(),
            "seedlink": self._seedlink_section(),
            "calibration": self._calibration_section(),
            # [T-2.29] Punto 0 de la brújula (o null: el panel usa media rodante).
            "rose_zero": self._rose_zero.current(),
            "shake_history": self._shake_history_section(),
            "signal": self._signal_section(now),
            "health": health,
            "cloud": self._cloud_section(),
            "drill": self._drill_section(),
            "actuation_test": self._actuation_test_section(),
            "test_mode": self._test_mode_section(),
            "audio": self._audio_section(),
            "events": self._events_section(),
        }

    def _test_mode_section(self) -> dict:
        """Modo prueba del WR-1 (T-1.69): banner + cuenta atrás mientras la nube está muda."""
        try:
            return {
                "active": bool(self._gpio.test_mode_active),
                "remaining_s": round(self._gpio.test_mode_remaining_s, 1),
            }
        except Exception:  # noqa: BLE001 — sección no-crítica del panel
            log.warning("panel LAN: estado de modo prueba no disponible", exc_info=True)
            return {"active": False, "remaining_s": 0.0}

    def _actuation_test_section(self) -> dict:
        """Prueba local de actuación (T-1.67): banner mientras sostiene + resultado."""
        try:
            active = bool(self._gpio.actuation_test_active)
        except Exception:  # noqa: BLE001 — sección no-crítica del panel
            log.warning("panel LAN: estado de prueba de actuación no disponible", exc_info=True)
            active = False
        with self._actions_lock:
            results = self._last_actuation_test
        return {"active": active, "results": results}

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

    def run_actuator_test(self) -> None:
        """Prueba LOCAL de actuación por LAN (T-1.67): ejercita TODO el gabinete.

        Sirena+estrobo suenan/se ven; gas/ascensor/puertas hacen su pulso de
        verificación. NO es una alerta real: no publica evento ni abre incidente
        (el gpio jamás dispara los callbacks SASMEX). Corre síncrono en el hilo
        de ESTE request (el servidor es multihilo; el reflejo nunca lo espera);
        el pulso dura ~1 s y la sirena sigue sonando hasta que vence el sostén.
        El resultado por relé aflora en ``status()`` para que el panel lo pinte.
        """
        result = self._gpio.run_local_actuation_test()
        with self._actions_lock:
            self._last_actuation_test = result
        self._record_action("actuator_test")
        log.warning("prueba local de actuación por LAN (NO es alerta real)")

    def toggle_test_mode(self) -> None:
        """Modo prueba del WR-1 por LAN (T-1.69): arma/desarma la ventana.

        Armado: un disparo (WR-1 real o instrumental) protege en LOCAL igual que
        siempre, pero NO se publica a la nube (sin incidente ni notificación). Es
        un toggle: el primer toque arma (ventana corta auto-expirable), el segundo
        desarma. Sirve para probar el WR-1 sin generar ruido en producción.
        """
        if self._gpio.test_mode_active:
            self._gpio.disarm_test_mode()
            self._record_action("test_mode_off")
        else:
            self._gpio.arm_test_mode()
            self._record_action("test_mode_on")

    def reset_alert(self) -> None:
        """Cierra/re-arma la alerta enclavada por LAN (vuelve a operación normal)."""
        # Orden gpio→rules a propósito (falla seguro ante un disparo concurrente):
        # si un sismo vivo re-enclava entre ambas llamadas, los relés QUEDAN en
        # protección y la siguiente ventana de features re-emite el tier.
        self._gpio.reset()
        # [T-2.26] Sin esto, last_tier quedaba congelado en el tier del episodio
        # hasta la siguiente feature — con SeedLink caído, PARA SIEMPRE.
        self._rules.reset()
        if self._audio is not None:
            # La alerta terminó: la voz también se calla (A-6).
            try:
                self._audio.stop_playback()
            except Exception:  # noqa: BLE001 — advisory
                log.exception("audio.stop_playback() en reset falló (aislado)")
        self._record_action("reset")
        log.warning("alerta cerrada/re-armada por LAN")

    def set_rose_zero(self) -> None:
        """[T-2.29] Fija/restablece el PUNTO 0 de la brújula por LAN (con PIN).

        Media por canal EN* de la ventana reciente del ring (counts crudos:
        gravedad + bias MEMS + inclinación de la instalación). Se invoca con el
        gabinete YA instalado lo más nivelado posible; volver a pulsarlo
        RESTABLECE el cero. Sin señal ⇒ `ActionUnavailable` (409): jamás se
        fija un cero inventado. Presentación pura — no toca actuación.
        """
        data = self.waveform(None, channels=["ENZ", "ENN", "ENE"], max_points=600)
        channels: dict[str, float] = {}
        for name, payload in (data.get("channels") or {}).items():
            flat: list[float] = []
            for sample in payload.get("samples") or []:
                # encoding "raw" = enteros sueltos; "minmax" = pares [min, max].
                if isinstance(sample, (list, tuple)):
                    flat.extend(float(v) for v in sample)
                else:
                    flat.append(float(sample))
            if flat:
                channels[name] = sum(flat) / len(flat)
        if not channels:
            raise ActionUnavailable("sin señal para calibrar el punto 0")
        self._rose_zero.set(channels)
        self._record_action("rose_zero")
        log.warning(
            "PUNTO 0 de la brújula fijado por LAN: %s",
            {name: round(value) for name, value in channels.items()},
        )

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
