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
import math
import threading
import time
import urllib.parse
from collections import deque
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path

from takab_edge.catalog import DEGRADED as _CATALOG_DEGRADED
from takab_edge.catalog import CatalogStore
from takab_edge.contracts import ActuatorChannel, utcnow
from takab_edge.durable import escribir_durable
from takab_edge.gpio_link import GpioLink, GpioLinkUnavailable, GpioSnapshot, as_link
from takab_edge.health import HealthMonitor
from takab_edge.local_api import sismografo
from takab_edge.module import EdgeModule
from takab_edge.reloj import Cronometro, mono
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

#: [T-2.68] Diagnóstico de relés cuando NINGUNA causa conocida explica la lista.
#: Es el default a propósito: sin explicación se asume la PEOR causa (avería del
#: proceso que toca la sirena), jamás la más benigna.
_RELAYS_UNKNOWN = {"reason": "unknown", "installed": None, "missing": []}


class _SinModuloDeSenal(Exception):
    """[T-7.23] «No hay módulo de señal» ≠ «el anillo está vacío».

    Son dos razones distintas y mandan al operador a sitios distintos: la
    primera, al journal del supervisor; la segunda, a mirar el sensor. Un solo
    `reason` para las dos habría sido un fallback disfrazado.
    """


#: Centinela de «este llamador no trae instantánea», distinto de `None` («no se
#: pudo leer»). Sin él, `_relays_view(None, "gpio_unreachable")` y
#: `_relays_view()` serían la misma llamada y la segunda no podría leer nada.
_SIN_INSTANTANEA: object = object()


def _age_s(raw: object, now: datetime) -> float | None:
    """[T-2.67] Edad en segundos de una fecha ISO; ``None`` si no se puede leer.

    La aritmética de relojes se hace AQUÍ y no en el navegador: el kiosco puede
    ir corrido y una edad calculada allí caducaría con su calendario (misma
    doctrina que la procedencia del catálogo, T-2.66). Una fecha ilegible es
    ``None`` — es decir "S/D" en pantalla — jamás un cero que parezca reciente.
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    # reloj: heredado — ⚠️ [T-7.60] Todas las marcas que pasan por aquí
    # (`checked_at`, `last_result_at`, `oldest_pending_at`, el `start` de un
    # pendiente) son fechas ISO que el backfill publica, y algunas sobreviven a
    # un reinicio: no hay monotónico compartido con el proceso que las selló.
    # El tope contra el uptime lo pone quien las enseña; aquí se mide con pared
    # a sabiendas, que es distinto de medirla sin saberlo.
    # reloj: heredado — marcas ISO del backfill; ver arriba
    return max(0.0, (now - stamp).total_seconds())


def _edad_mono(origen: object) -> float | None:
    """Edad de un CRONÓMETRO, no de una fecha. Inmune a los saltos de reloj.

    [T-7.60·disfraz] Hermano de `_age_s`, y la diferencia es todo el asunto: éste
    recibe una marca monotónica que selló ESTE proceso, así que su edad no puede
    llevarse dentro un ajuste de NTP. `_age_s` recibe fechas de pared que a veces
    sobreviven a un reinicio, y por eso está declarado `heredado`.

    Tenerlos separados es lo que permite que la declaración sea por MARCA y no
    por resta: `_age_s` es una sola resta compartida por cuatro marcas de clases
    distintas, y un único marcador ahí las tapaba a todas.
    """
    if not isinstance(origen, (int, float)):
        return None
    # reloj: monotonico — el origen lo selló este proceso
    return max(0.0, mono() - float(origen))


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
    DURABLE (`takab_edge.durable`), sin path ⇒ solo memoria (tests/parcial), y un
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
                    # [T-7.59] El punto 0 se mide UNA vez con el gabinete quieto:
                    # perderlo en un corte obliga a repetir una calibración
                    # presencial, así que es justo lo que tiene que ser durable.
                    escribir_durable(self._path, json.dumps(snapshot))
                except Exception:  # noqa: BLE001 — sin disco sigue vivo en memoria
                    log.warning(
                        "no se pudo persistir el punto 0 (%s); queda en memoria",
                        self._path,
                        exc_info=True,
                    )
        return snapshot


def sanear_no_finitos(valor):
    """[T-7.23 · M1] Deja el cuerpo en JSON que un `JSON.parse` SIEMPRE puede leer.

    `json.dumps` de Python escribe `Infinity`, `-Infinity` y `NaN` tal cual, y
    eso **no es JSON**: el `JSON.parse` del kiosco lanza, la excepción sube al
    `catch` del tick y el panel declara caído un gabinete perfectamente sano —
    peor que el 400 que la doctrina de estos endpoints prohíbe. Entraba por la
    puerta más tonta (`?hours=inf` viajaba crudo en `requested_hours`), pero el
    agujero no era ése: era que NINGÚN flotante de la respuesta estaba mirado.
    Aquí se miran todos, a cualquier profundidad, y un no-finito sale como
    `null` — que es la forma que el contrato ya tiene para «este número no
    existe».

    Se aplica a la respuesta ENTERA y no sólo al campo culpable a propósito: un
    saneador que enumere campos a mano se queda atrás en cuanto alguien añade
    uno.
    """
    if isinstance(valor, float):
        return valor if math.isfinite(valor) else None
    if isinstance(valor, dict):
        return {k: sanear_no_finitos(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [sanear_no_finitos(v) for v in valor]
    return valor


def volcar_json(payload) -> str:
    """[T-7.23 · N3] El cuerpo JSON del panel. El saneo cuesta sólo cuando hay algo que sanear.

    La verja de `sanear_no_finitos` es correcta y se queda; lo que no puede
    quedarse es que la pague el camino caliente por una imposibilidad.
    Reconstruía la respuesta ENTERA en Python, listas de muestras incluidas —y
    en `/api/waveform` son enteros decimados, donde un no-finito no cabe—.
    Medido aquí, con `json.dumps` desnudo como vara [MEDIDO · equipo de
    desarrollo x86-64 · Python 3.12 · 2026-09-20]:

    | Cuerpo | `json.dumps` | saneo + `json.dumps` | `allow_nan=False` |
    |---|---|---|---|
    | `/api/waveform`, 8 000 valores | 0.61 ms | **1.82 ms** | 0.43 ms |
    | helicorder de 6 h, 43 200 valores | 2.43 ms | **9.95 ms** | 2.37 ms |

    `allow_nan=False` hace la comprobación DENTRO del codificador en C, que es
    el mismo recorrido que ya se hacía: sale gratis. Y cuando de verdad hay un
    no-finito, `json.dumps` levanta `ValueError` sin haber escrito nada, así
    que el saneador corre entonces y sólo entonces (12.05 ms medidos sobre el
    peor cuerpo — una vez, no una por petición).

    Lo que NO se hace: enumerar qué endpoints o qué campos pueden traer un
    no-finito. Esa lista se quedaría atrás igual que se quedaría la del
    saneador, y la verja seguiría siendo exacta sólo hasta el siguiente campo.
    """
    try:
        return json.dumps(payload, allow_nan=False)
    except ValueError:
        return json.dumps(sanear_no_finitos(payload))


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


def _spectrogram_params(query: str) -> tuple[str | None, int | None]:
    """[T-7.23] Parámetros de /api/spectrogram: ilegales ⇒ defaults, jamás 400.

    Misma doctrina que `_waveform_params`, y por la misma razón: el que consume
    esto es un kiosco sin teclado colgado en una pared. Un 400 ahí es una
    pantalla en blanco que nadie puede depurar.
    """
    params = urllib.parse.parse_qs(query)
    canal = params.get("channel", [""])[0] or None
    try:
        nperseg: int | None = int(params["nperseg"][0])
    except (KeyError, IndexError, ValueError):
        nperseg = None
    return canal, nperseg


def _helicorder_params(query: str) -> tuple[str | None, float | None]:
    """[T-7.23] Parámetros de /api/helicorder: ilegales ⇒ defaults, jamás 400.

    `float("inf")`, `float("nan")` y `float("1e400")` PARSEAN en Python, así que
    caían fuera del `except` y viajaban crudos hasta `requested_hours`. Se
    tratan como lo que son para este endpoint —un valor que no nombra ninguna
    ventana— y salen como `None`, igual que `?hours=hola`. El saneador de
    arriba es la segunda verja, no la primera: el parámetro se arregla donde se
    lee.
    """
    params = urllib.parse.parse_qs(query)
    canal = params.get("channel", [""])[0] or None
    try:
        horas: float | None = float(params["hours"][0])
    except (KeyError, IndexError, ValueError):
        horas = None
    if horas is not None and not math.isfinite(horas):
        horas = None
    return canal, horas


def _load_index_html() -> str:
    try:
        return resources.files("takab_edge.local_api").joinpath("index.html").read_text("utf-8")
    except OSError:
        log.error("index.html del panel LAN no encontrado; se sirve el fallback")
        return _FALLBACK_HTML


def _load_static() -> dict[str, tuple[str, bytes]]:
    """[T-2.23] Whitelist de estáticos, cargada UNA vez al construir el panel.

    Dict por ruta EXACTA ⇒ inmune a path traversal por construcción: cualquier
    otra ruta (incluido `/fonts/../`) es 404. Un recurso ausente simplemente no
    entra a la whitelist: sin fuente, la pila CSS cae a la del sistema; sin
    favicon, la pestaña sale con el icono genérico. Nada revienta.

    El favicon viaja EMPAQUETADO junto al módulo, igual que las fuentes: el
    panel se sirve sin build y sin red, así que un icono que hubiera que
    descargar no se vería jamás en el gabinete.
    """
    served: dict[str, tuple[str, bytes]] = {}
    recursos = (
        ("fonts/geist.ttf", "/fonts/geist.ttf", "font/ttf"),
        ("fonts/jbmono.woff2", "/fonts/jbmono.woff2", "font/woff2"),
        ("favicon.png", "/favicon.png", "image/png"),
        ("isotipo.png", "/isotipo.png", "image/png"),
    )
    for nombre, ruta, mime in recursos:
        try:
            data = resources.files("takab_edge.local_api").joinpath(nombre).read_bytes()
            served[ruta] = (mime, data)
        except OSError:
            log.warning("estático %s no empaquetado; el panel sigue sin él", nombre)
    return served


# [T-2.24] La carga/normalización del catálogo vive en `takab_edge.catalog`
# (CatalogStore): mismo archivo, mismo contrato §5.1, y ahora con feed FIRMADO
# nube→edge. El panel solo LEE la instantánea viva del store.


#: [T-3.11.b] Tope del cuerpo del grant de CCTV. Es un JSON de cinco campos; 4 KiB es
#: holgura de sobra y evita que un cliente de la LAN haga reservar memoria al gabinete.
_CCTV_GRANT_MAX_BYTES = 4096


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

    def _send_json(self, code: int, payload) -> None:
        """[T-7.23 · M1] La única puerta por la que sale JSON del panel.

        Va por la verja de no-finitos SIEMPRE y para TODAS las respuestas, no
        sólo para el endpoint que tenía el defecto: un `Infinity` o un `NaN` en
        cualquiera de ellas rompe el `JSON.parse` del kiosco igual, y la
        pantalla declara caído un gabinete sano.

        **[T-7.23 · C3] «Única» era una afirmación, no un hecho.** Quedaban
        `json.dumps` sueltos en este manejador —los cuerpos de error de
        `do_GET`, los de `do_POST` y los del grant de CCTV— que salían al
        socket sin pasar por aquí, y ninguna guarda lo impedía. Ahora todos
        pasan, y lo exige un censo que DERIVA la lista del propio árbol de
        sintaxis de esta clase (`test_la_unica_puerta_de_json_lo_es_de_verdad`)
        en vez de enumerarlos.

        **[T-7.23 · Q3] Y CUÁNTOS ERAN NO SE ESCRIBE AQUÍ.** Esta prosa decía
        un número y la del censo decía otro, así que una de las dos mentía por
        construcción — y las dos hablaban del mismo barrido, que ya sabe
        contar. El recuento sale de `_puertas_de_json_del_panel`, que lo
        deriva del `ast`, y una guarda prohíbe que vuelva a teclearse en
        cualquiera de las dos prosas. Misma lección que la de `scipy.signal`:
        una cifra en un comentario no la mide nadie.
        """
        self._send(code, volcar_json(payload))

    def do_GET(self) -> None:
        dashboard = self.server.dashboard  # type: ignore[attr-defined]
        path, _, query = self.path.partition("?")
        if path in ("/", "/index.html"):
            self._send(200, dashboard.index_html, "text/html; charset=utf-8")
        elif path == "/api/status":
            # El GET del guardia no puede reventar por un módulo caído: status()
            # ya es defensivo por sección; esto es el último cinturón.
            try:
                self._send_json(200, dashboard.status())
            except Exception:  # noqa: BLE001 — panel no-crítico, jamás traceback al socket
                log.exception("status() del panel LAN falló")
                self._send_json(500, {"error": "status"})
        elif path == "/api/waveform":
            # T-2.15: lectura abierta como /api/status (es el panel del guardia).
            # waveform() es defensivo de punta a punta: signal roto ⇒ 200 degradado.
            self._send_json(200, dashboard.waveform(*_waveform_params(query)))
        elif path == "/api/spectrogram":
            # [T-7.23] Lectura abierta como /api/waveform: mismo anillo de RAM,
            # misma LAN, mismo guardia mirando. Defensivo de punta a punta.
            self._send_json(200, dashboard.spectrogram(*_spectrogram_params(query)))
        elif path == "/api/helicorder":
            # [T-7.23] Lectura ACOTADA del anillo de disco (nunca el día entero:
            # 2.9 s y 159 MB [PROTOTIPO · Pi 4 · 2026-09-20]). El cerrojo sin
            # espera vive en el método.
            self._send_json(200, dashboard.helicorder(*_helicorder_params(query)))
        elif path == "/api/catalog":
            # T-2.23: instantánea SSN cacheada en memoria (leída UNA vez al construir).
            self._send_json(200, dashboard.catalog())
        elif path in dashboard.static_files:
            # T-2.23: whitelist EXACTA (traversal imposible por construcción).
            mime, data = dashboard.static_files[path]
            self._send(200, data, mime, cache_control="public, max-age=86400")
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        dashboard = self.server.dashboard  # type: ignore[attr-defined]
        # [T-3.11.b] El grant de CCTV va APARTE del diccionario de acciones, y no por
        # orden: aquellas son acciones de una PERSONA de pie en el sitio —autorizadas por
        # PIN, sin cuerpo y sin respuesta— y ésta es máquina a máquina: lleva cuerpo, la
        # autoriza un HMAC y devuelve datos. Meterla en la misma tabla habría obligado a
        # que el PIN del guardia valiera para pedir grants, o al revés.
        if self.path == "/api/cctv/grant":
            self._cctv_grant(dashboard)
            return
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
            self._send_json(404, {"error": "not found"})
            return
        # Autorización ANTES de tocar GPIO (T-1.43): silenciar la sirena de un
        # edificio no puede depender solo de estar en la misma LAN.
        code = dashboard.authorize_action(self.headers.get("X-Takab-Pin"))
        if code != 200:
            self._send_json(code, {"error": "pin"})
            return
        try:
            action()
        except ActionUnavailable as exc:
            # [T-2.29] La orden es válida pero AHORA no puede cumplirse (p.ej.
            # calibrar sin señal): 409 honesto, jamás un OK que no hizo nada.
            self._send_json(409, {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 — el operador merece una respuesta
            # [T-2.70.a·D2/P1] Las SEIS acciones del panel cruzan la costura y
            # ninguna tenía camino honesto de fallo: `do_POST` sólo traducía
            # `ActionUnavailable`, y cualquier otra excepción escapaba a
            # `BaseHTTPRequestHandler` — el operador que aprieta SILENCIO se
            # quedaba con la conexión cortada y sin saber si la sirena se calló.
            #
            # 503 y no 500: esto no es una avería del panel, es que el servicio
            # de abajo —el dueño de los pines— no pudo cumplir. Un 500 mandaría a
            # reiniciar el kiosco; un 503 manda a mirar el gabinete.
            log.exception("acción %s del panel LAN no se pudo ejecutar", self.path)
            self._send_json(
                503,
                {
                    "error": (
                        "el gabinete no pudo ejecutar la acción "
                        f"({type(exc).__name__}); revisa el estado del proceso "
                        "que gobierna los pines"
                    )
                },
            )
            return
        self._send_json(200, {"ok": True})

    def _cctv_grant(self, dashboard) -> None:
        """`POST /api/cctv/grant` — firma HMAC sobre el cuerpo, devuelve la URL."""
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json(400, {"error": "content-length"})
            return
        # Tope duro: esto recibe un JSON de cinco campos. Sin él, un cliente de la LAN
        # podría hacer que el gabinete reserve memoria arbitraria — y este proceso corre
        # en la misma máquina que el resto del edge.
        if largo <= 0 or largo > _CCTV_GRANT_MAX_BYTES:
            self._send_json(413, {"error": "cuerpo fuera de rango"})
            return
        cuerpo = self.rfile.read(largo)
        if not dashboard.verify_cctv_signature(cuerpo, self.headers.get("X-Takab-Cctv-Sig")):
            self._send_json(401, {"error": "firma"})
            return
        try:
            payload = json.loads(cuerpo)
        except ValueError:
            self._send_json(400, {"error": "json"})
            return
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "json"})
            return
        try:
            grant = dashboard.request_cctv_grant(payload)
        except ActionUnavailable as exc:
            # 409: la peticion es valida, lo que falta es enlace. El CCTV reintenta.
            self._send_json(409, {"error": str(exc)})
            return
        except Exception:  # noqa: BLE001
            log.exception("grant de cctv no se pudo tramitar")
            self._send_json(503, {"error": "el gabinete no pudo pedir el grant"})
            return
        self._send_json(200, grant)

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
    depends_on = ("gpio", "rules", "health", "signal", "cloud", "backfill", "buffer")

    def __init__(
        self,
        gpio: GpioLink,
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
        # [T-5.26] La identidad que permite CORRELACIONAR este gabinete con lo
        # que ve la consola, sin abrir el archivo de entorno de pie delante del
        # Pi: el nombre con el que la nube lo conoce y el código de estación con
        # el que firma cada traza el sismógrafo.
        iot_thing: str = "",
        station_code: str = "",
        #: [T-7.23] Identidad COMPLETA `red.estación.loc.canal`, una por canal.
        #: Va APARTE de `station_code` porque aquél es contrato con la nube y no
        #: se toca; ésta la deriva `EdgeSettings.seedlink_nslc` en un solo sitio.
        station_nslc: list[str] | None = None,
        #: [T-7.23] Anillo miniSEED en disco, SOLO para el helicorder. El panel
        #: jamás escribe en él ni usa `extract_window` (lee el día entero).
        buffer: object | None = None,
        refresh_ms: int = 1000,
        audio: object | None = None,
        drill: object | None = None,
        dispatch: object | None = None,
        lora: object | None = None,
        backfill: object | None = None,
        ledger: object | None = None,
        #: [T-5.22] Acta del reflejo. El panel la LEE (`resumen()`), jamás la
        #: escribe: la escribe el supervisor, que es quien ve la latencia por la
        #: costura y vive del lado que sí puede tocar disco.
        acta_reflejo: object | None = None,
        #: [T-3.11.b] Solo para verificar el HMAC del grant de CCTV. El panel NO
        #: firma nada: verifica.
        security: object | None = None,
        keepalive_enabled: bool = False,
    ) -> None:
        super().__init__()
        # [T-2.146] ¿Está montada la ruta de hardware de SPOF-02? Es CONFIGURACIÓN,
        # no estado: por eso entra por el constructor y no por la instantánea del
        # gpio. Meterla en el snapshot sugeriría que puede cambiar entre dos
        # lecturas, y no puede: cambia cuando alguien monta el `K_wd` y redespliega.
        self._keepalive_enabled = keepalive_enabled
        self._link = as_link(gpio)
        # [T-2.86.a · RO-4.e] Bitácora local de actuación: las acciones del panel
        # mueven relés de un edificio y hasta hoy sólo quedaban en una `deque` en
        # RAM (`_actions`), que un reinicio borra. Ver `_accion`.
        self._ledger = ledger
        self._acta_reflejo = acta_reflejo
        self._security = security
        self._rules = rules
        self._health = health
        self._signal = signal
        self._cloud = cloud
        self._seedlink = seedlink
        self._config = config
        self._location = location
        self._audio = audio
        self._drill = drill
        # [T-2.32] Fuente «QUÓRUM RED»: el dispatcher registra la actuación
        # comandada por la nube y CERRAR ALERTA la limpia.
        self._dispatch = dispatch
        # [T-2.33] Enlace a gabinetes secundarios LoRa (salud + CLEAR/TEST).
        self._lora = lora
        # [T-2.67] Respaldo de evidencia miniSEED: se lee su INSTANTANEA EN
        # MEMORIA, nunca su directorio (ver `_evidence_section`).
        self._backfill = backfill
        self._gateway_id = gateway_id
        self._site_name = site_name
        self._iot_thing = iot_thing
        self._station_code = station_code
        self._station_nslc = list(station_nslc or [])
        self._buffer = buffer
        # [T-7.23] Cerrojo SIN ESPERA del helicorder. Una lectura de 6 h son
        # 0.89 s y ~34.5 MB [PROTOTIPO · Pi 4 · 2026-09-20]; tres kioscos
        # abiertos no pueden multiplicar por tres el coste del gabinete, así que
        # la segunda petición concurrente se va declarada como `ocupado` en vez
        # de apilar otra lectura de disco.
        self._heli_lock = threading.Lock()
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
        self._arranque: Cronometro | None = None
        # Acciones LAN recordadas para la lista de eventos (append desde los
        # hilos HTTP; lectura desde status()): lock propio.
        self._actions: deque[dict] = deque(maxlen=_ACTIONS_MAX)
        self._actions_lock = threading.Lock()
        self._last_actuation_test: dict | None = None  # T-1.67: resultado por relé
        # [T-2.85.a] …y cuándo acabó. Un resultado sin fecha no se puede pintar
        # sin mentir: no hay forma de distinguir el de hace tres segundos del de
        # la semana pasada.
        self._last_actuation_test_at: datetime | None = None
        self.index_html = _load_index_html()
        # T-2.23: estáticos y catálogo se cargan UNA vez — servir jamás toca disco.
        # T-2.24: el store compartido del supervisor trae el feed firmado; un
        # panel suelto (tests/parcial) construye uno de solo-lectura por path.
        self.static_files = _load_static()
        self._catalog_store = catalog if catalog is not None else CatalogStore(catalog_path)
        self._rose_zero = RoseZeroStore(rose_zero_path)  # T-2.29

    def catalog(self) -> dict:
        """[T-2.23/24] Instantánea SSN normalizada (§5.1). Lectura pura del store.

        [T-2.66] Viaja además su PROCEDENCIA (`provenance`): edad de la captura,
        edad de la instalación, origen y umbral de vejez — resueltos en Python,
        que es lo único determinista (el navegador del kiosco puede ir corrido).
        Si la procedencia fallara, el catálogo SE SIGUE SIRVIENDO sin ella: es
        peor apagar el mapa y la comparativa que perder un rótulo.
        """
        try:
            snapshot = dict(self._catalog_store.current())
        except Exception:  # noqa: BLE001 — sección no-crítica
            log.warning("panel LAN: catálogo no disponible", exc_info=True)
            return dict(_CATALOG_DEGRADED)
        try:
            snapshot["provenance"] = self._catalog_store.provenance()
        except Exception:  # noqa: BLE001 — el panel lo rotula EDAD DESCONOCIDA
            log.warning("panel LAN: procedencia del catálogo no disponible", exc_info=True)
        return snapshot

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
        for channel, (feature, received_at, recibido_mono) in sorted(live.items()):
            channels[channel] = {
                "pga_g": feature.pga,
                "pgv_cms": feature.pgv,
                "rms": feature.rms,
                "sta_lta": feature.sta_lta,
                "clipping": feature.clipping,
                "health_score": feature.health_score,
                "window_start": feature.window_start.isoformat(),
                # La FECHA se sigue publicando: quien depura un gabinete quiere
                # saber a qué hora llegó el último paquete, y ése es un instante
                # legítimo que el panel enseña junto a su propio `now`.
                "received_at": received_at.isoformat(),
                # [T-7.60·disfraz] Pero la EDAD sale del cronómetro, no de esa
                # fecha. Es la que decide si el canal se pinta o se borra con
                # «SIN SEÑAL DEL SENSOR» (5 s), así que un ajuste de NTP metido
                # en la resta declaraba muerto un sensor que estaba entregando.
                # reloj: monotonico — el origen lo selló `signal` en este proceso
                "age_s": max(0.0, mono() - recibido_mono),
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
            # reloj: heredado — `captured_at` puede ser de otra vida
            "captured_at": snap.captured_at.isoformat(),
            # Declarada APARTE de `captured_at` aunque la razón sea la misma: que
            # un marcador valga para dos entradas es el defecto exacto que este
            # censo persigue (`_age_s` tapaba cuatro marcas con uno solo).
            # reloj: heredado — el latido cacheado puede ser de otra vida
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

    def spectrogram(
        self,
        channel: str | None = None,
        nperseg: int | None = None,
        *,
        ahora: datetime | None = None,
    ) -> dict:
        """[T-7.23] Espectrograma del anillo de RAM (§15.3). SOLO LAN.

        Defensivo de punta a punta, igual que `waveform()`: sin módulo de señal,
        sin anillo o con el cálculo roto responde la forma degradada con 200 y su
        razón escrita — el kiosco pinta «SIN ESPECTROGRAMA», jamás recibe un 500.
        No publica, no sondea, no toca disco.
        """
        nperseg_servido = sismografo.acotar_nperseg(nperseg)
        try:
            if self._signal is None:
                raise _SinModuloDeSenal
            ring = getattr(self._signal, "waveform", None)
            if ring is None:
                raise _SinModuloDeSenal
            return sismografo.espectrograma(ring, channel, nperseg, ahora or utcnow())
        except _SinModuloDeSenal:
            return sismografo._degradado_espectro(
                "sin_modulo_de_senal", canal_pedido=channel, nperseg=nperseg_servido
            )
        except Exception:  # noqa: BLE001 — pantalla no-crítica
            log.warning("panel LAN: espectrograma no disponible", exc_info=True)
            return sismografo._degradado_espectro(
                "error_de_calculo", canal_pedido=channel, nperseg=nperseg_servido
            )

    def helicorder(
        self,
        channel: str | None = None,
        hours: float | None = None,
        *,
        ahora: datetime | None = None,
    ) -> dict:
        """[T-7.23] 1–6 h del anillo de DISCO en mín/máx a 1 Hz (§15.4). SOLO LAN.

        Tres cosas pasan aquí y no en el módulo de cálculo, porque son del panel
        y no del anillo:

        - **el cerrojo sin espera**: si ya hay una lectura en curso, ésta se va
          declarada `ocupado`. Es lo que impide que tres kioscos abiertos
          tripliquen el coste de disco del gabinete;
        - **la ausencia del módulo**, que es distinta de «el anillo no tiene ese
          canal» y manda al operador a otro sitio;
        - **el último cinturón**: cualquier excepción sale como 200 degradado.

        `ahora` sólo lo pasan las pruebas: una ventana anclada en el reloj real
        cruza la medianoche una vez al día y el fallo saldría de madrugada.
        """
        horas = sismografo.acotar_horas(hours)
        if self._buffer is None:
            return sismografo._degradado_heli(
                "sin_anillo",
                canal=None,
                canal_pedido=channel,
                horas=horas,
                horas_pedidas=hours,
            )
        if not self._heli_lock.acquire(blocking=False):
            return sismografo._degradado_heli(
                "ocupado",
                canal=None,
                canal_pedido=channel,
                horas=horas,
                horas_pedidas=hours,
            )
        try:
            raiz = Path(self._buffer.root)
            return sismografo.helicorder(raiz, channel, hours, ahora or utcnow())
        except Exception:  # noqa: BLE001 — pantalla no-crítica: jamás un 500
            log.warning("panel LAN: helicorder no disponible", exc_info=True)
            return sismografo._degradado_heli(
                "anillo_ilegible",
                canal=None,
                canal_pedido=channel,
                horas=horas,
                horas_pedidas=hours,
            )
        finally:
            self._heli_lock.release()

    def _gpio_snapshot(self) -> tuple[GpioSnapshot | None, str | None]:
        """[T-2.70.a·D2/P1] UNA lectura del gabinete por request, y su diagnóstico.

        Devuelve ``(instantánea, None)`` o ``(None, causa)``. El panel poll­ea a 1 Hz
        y pedía SIETE propiedades por request —cada una una toma del lock, cada una
        un cruce del futuro IPC— y, peor, cuatro de ellas SIN envolver: una lectura
        que lanzara caía en el `except` de `do_GET` y el kiosco recibía un **500**,
        o sea la pantalla en blanco en vez de una sección en S/D.

        La causa se separa aquí porque no todas piden lo mismo del operador:
        `gpio_unreachable` (el dueño de los pines no contesta) manda a mirar el
        servicio de los pines; `gpio_error` (reventó una lectura) manda al journal
        del proceso que sí tenemos delante.
        """
        try:
            return self._link.snapshot(), None
        except GpioLinkUnavailable:
            log.warning("panel LAN: el dueño de los pines no contesta", exc_info=True)
            return None, "gpio_unreachable"
        except Exception:  # noqa: BLE001 — sección no-crítica: jamás un 500 al kiosco
            log.warning("panel LAN: estado del gabinete no disponible", exc_info=True)
            return None, "gpio_error"

    def _keepalive_view(self, snap: GpioSnapshot | None) -> dict:
        """[T-2.146 · SPOF-02] Estado de la ruta de hardware de la sirena.

        **Son TRES estados y no dos, y confundirlos cuesta un edificio.** El latido
        del `K_wd` es la única forma de saber, sin un multímetro, quién gobierna la
        sirena:

        - ``sin_ruta`` — el latido está **deshabilitado**, que es el default mientras
          el `K_wd` no esté montado (`D-16` aplazó la compra). No hay ruta de hardware
          que gobernar, así que tampoco hay nada que reprochar: **no es una avería**.
        - ``inhibida`` — hay ruta **y late**: el Pi gobierna, y el operador puede
          silenciar desde el panel.
        - ``habilitada`` — hay ruta y **NO late**: el WR-1 puede sonar la sirena por su
          cuenta **y nadie la calla**. Es el estado que hay que ver de lejos.
        - ``sd`` — no se pudo leer el gpio. No se pinta ninguno de los tres.
        - ``dueno_antiguo`` — [T-2.165] se leyó el gabinete, pero **el dueño de los
          pines corre una versión anterior** a la que introdujo este campo: no es que
          no late, es que **no sabe decirlo**. Es el estado normal de la ventana que
          el layout A/B abre entre activar al cliente y reiniciar al dueño, y se
          resuelve solo en cuanto el dueño estrena la versión nueva.

        Pintar ``sin_ruta`` y ``habilitada`` con el mismo rótulo sería la regla de oro
        7 en su forma más cara: los dos son «no late», y significan cosas opuestas. Y
        pintar ``dueno_antiguo`` como cualquiera de los otros sería peor todavía: ahí
        el valor que trae la instantánea **no lo midió nadie** — lo puso el códec para
        poder construir el objeto.
        """
        if snap is None:
            return {"estado": "sd", "enabled": self._keepalive_enabled, "beating": None}
        if "keepalive_beating" in snap.campos_desconocidos:
            return {"estado": "dueno_antiguo", "enabled": self._keepalive_enabled, "beating": None}
        if not self._keepalive_enabled:
            return {"estado": "sin_ruta", "enabled": False, "beating": snap.keepalive_beating}
        return {
            "estado": "inhibida" if snap.keepalive_beating else "habilitada",
            "enabled": True,
            "beating": snap.keepalive_beating,
        }

    def _relays_view(
        self,
        snap: GpioSnapshot | None | object = _SIN_INSTANTANEA,
        gpio_reason: str | None = None,
    ) -> tuple[list[dict], dict]:
        """Relés para el panel: las filas Y **por qué** son las que son.

        Sin argumentos toma su propia instantánea (tests y llamadas sueltas);
        `status()` le pasa la del request para que las filas, el diagnóstico y los
        cuatro booleanos de arriba salgan todos del MISMO instante.

        gpio.relay_states() ya es seguro en shutdown (devuelve []); este guard
        cubre cualquier otro fallo: roto ⇒ [] y el panel pinta S/D, jamás un 500
        al kiosco (misma doctrina que el resto de las secciones).

        [T-2.31] Se pintan SOLO los actuadores instalados (perfil vivo del
        config store): mostrar un relé de gas en un sitio sin gas es un dato
        falso (regla de oro 7). gpio conserva sus 5 relés; el filtro es de
        presentación.

        [T-2.68] Una lista vacía significaba cuatro cosas distintas bajo un solo
        rótulo, y la reacción correcta del operador es distinta en cada una. Peor:
        el `try` era UNO SOLO sobre DOS módulos —gpio y config—, así que un store
        de config corrupto se disfrazaba de gpio averiado. Aquí van en cajas
        separadas y el diagnóstico viaja en `relays_status` (hermano aditivo,
        molde de `siren_reason`):

        - ``gpio_stopped``  el módulo no corre. Camino SIN excepción y por diseño
          (regresión 2026-07-30): solo ``gpio.running`` lo delata — el guard que
          `health._relay_states()` ya tenía y el panel no.
        - ``gpio_error``    ``relay_states()`` LANZÓ estando en marcha: avería en
          caliente del proceso que toca la sirena.
        - ``config_error``  el perfil de equipamiento no se pudo leer. El estado
          eléctrico SÍ se midió: se sirve sin filtrar y se declara que el filtro
          no se aplicó (tirarlo perdería el dato bueno por culpa del rótulo).
        - ``no_actuators_installed``  el sitio declara los cinco en ``false``.
          Lista vacía LEGÍTIMA — ni la consola ni el env exigen "al menos uno".
        - ``partial``       el perfil declara canales que gpio no reporta. La
          lista corta miente igual que la vacía y nada la disparaba.
        - ``gpio_unreachable`` [T-2.70.a·D2/P1] el DUEÑO DE LOS PINES no contesta.
          Causa NUEVA, y no es ninguna de las anteriores: no es que el módulo esté
          parado (eso lo sabríamos) ni que su lectura reventara en marcha (eso es
          una avería del proceso que sí tenemos delante) — es que no hubo
          respuesta. Mapearla a `gpio_error` o a `gpio_stopped` mandaría al
          operador a revisar el journal equivocado.
        - ``unknown``       nadie sabe. Es el DEFAULT a propósito: el rótulo que
          había ("arranque en frío") se leía como "todo bien, espera" y era el
          único estado que nunca ocurre — gpio puebla sus cinco canales, síncrono
          y bajo lock, antes de que este panel abra su socket.

        Diagnóstico puro sobre memoria ya viva: cero disco, cero red, y NO toca
        el camino SASMEX→relé (regla de oro 4).
        """
        if snap is _SIN_INSTANTANEA:
            snap, gpio_reason = self._gpio_snapshot()
        try:
            return self._relays_view_inner(snap, gpio_reason)
        except Exception:  # noqa: BLE001 — sección no-crítica: degrada a lo PEOR
            log.warning("panel LAN: relés no disponibles", exc_info=True)
            return [], dict(_RELAYS_UNKNOWN)

    def _relays_view_inner(
        self, snap: GpioSnapshot | None, gpio_reason: str | None
    ) -> tuple[list[dict], dict]:
        # --- caja 1: gpio (estado eléctrico medido) ---
        # [T-2.70.a·D2/P1] Sale de la instantánea ÚNICA del request: `running` y las
        # filas ya no son dos lecturas que puedan contradecirse entre sí.
        running: bool | None = None
        states: list = []
        if snap is not None:
            running = bool(snap.running)
            states = list(snap.relays)

        # --- caja 2: config (perfil declarado del sitio) ---
        # Sin config (panel suelto) el perfil es DESCONOCIDO, no vacío: no se
        # filtra nada y no hay contra qué cruzar la lista.
        installed: list[str] | None = None
        config_failed = False
        if self._config is not None:
            try:
                equipment = self._config.current().equipment
                installed = sorted(c.value for c in equipment.installed())
                # Si `has()` reventara a mitad, la asignación no ocurre y `states`
                # conserva la lista COMPLETA de gpio — nunca un filtro a medias.
                states = [r for r in states if equipment.has(r.channel)]
            except Exception:  # noqa: BLE001 — ya no se disfraza de gpio roto
                log.warning("panel LAN: perfil de equipamiento no disponible", exc_info=True)
                config_failed = True
                installed = None

        rows = [r.model_dump(mode="json") for r in states]
        presentes = {r.get("channel") for r in rows}
        missing = [c for c in (installed or ()) if c not in presentes]

        if gpio_reason is not None:
            # «No contesta» y «reventó en marcha» llegan ya distinguidas de arriba
            # (`_gpio_snapshot`); ninguna de las dos puede saber si el módulo corre.
            reason = gpio_reason
        elif running is False:
            reason = "gpio_stopped"
        elif config_failed:
            reason = "config_error"
        elif installed is not None and not installed:
            reason = "no_actuators_installed"
        elif missing:
            reason = "partial"
        elif not rows:
            reason = "unknown"
        else:
            reason = "ok"
        return rows, {"reason": reason, "installed": installed, "missing": missing}

    def _thresholds_section(self) -> dict | None:
        """[T-2.16] Umbrales VIGENTES en el motor (T-1.71: se reemplazan en vivo).

        No son los de `EdgeSettings` estáticos: tras un `apply_signed_update` el
        panel debe pintar la línea de umbral que de verdad dispara.

        [T-5.16 · D-28] Y ADEMÁS DE DÓNDE SALIERON. El default de fábrica es
        0.040–0.060 g, que es la banda de HOSPITAL, y hasta aquí se pintaba
        idéntica a una banda elegida y publicada: un industrial dado de alta hoy
        avisa dos veces por debajo de su banda y la pantalla no lo decía. El
        dato estaba —`config_version: 0`— pero en otra sección y para que la
        correlación la hiciera un humano.

        `sin_resolver` NO apaga nada: los números siguen ahí y el motor sigue
        decidiendo con ellos, porque el gabinete opera sin nube (regla de oro 2).
        Lo que cambia es que deja de hacerse pasar por una decisión.
        """
        try:
            band = self._rules.thresholds
            version = self._config_version()
            return {
                "pga_watch_g": band.pga_watch_g,
                "pga_trip_g": band.pga_trip_g,
                "pgv_watch_cms": band.pgv_watch_cms,
                "pgv_trip_cms": band.pgv_trip_cms,
                "origen": "sincronizado" if version else "sin_resolver",
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

    def _latencies_section(self, snap: GpioSnapshot | None) -> dict:
        """[T-2.17] Latencias MEDIDAS de la cadena crítica, contra presupuesto.

        `null` = sin medición todavía (la UI pinta S/D). JAMÁS un 0.0 fabricado:
        un cero se leería como "instantáneo" y sería una mentira.

        [T-5.22] `reflex_s` es **vivo y volátil**: vuelve a `null` en cuanto el
        proceso reinicia, y ése es literalmente el defecto que la ficha nombra —
        «en el gabinete vivo el campo de latencia está en nulo: la medición no
        está viva, es histórica». Al lado va ahora `acta`, que **sobrevive al
        reinicio** y trae mejor y **peor** caso con su conteo. Sin las dos, quien
        mira el panel en una sesión presencial no tiene de dónde sacar la cifra
        más citada del producto sin entrar por ssh.
        """
        reflex = snap.last_reflex_latency_s if snap is not None else None
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
            "acta": self._acta_section(),
        }

    def _acta_section(self) -> dict | None:
        """[T-5.22] Resumen del acta del reflejo, o ``None`` si no hay acta.

        ``None`` significa **una cosa concreta y no dos**: este gabinete no tiene
        el módulo del acta (firmware anterior a `T-5.22`). Un gabinete que SÍ lo
        tiene y todavía no ha visto ningún flanco devuelve el resumen con
        ``total: 0`` y sus cifras en `null` — que es un hecho distinto y hay que
        poder distinguirlo, porque el primero se arregla desplegando y el segundo
        pulsando el WR-1.
        """
        if self._acta_reflejo is None:
            return None
        try:
            return dict(self._acta_reflejo.resumen())
        except Exception:  # noqa: BLE001 — sección no-crítica, como las demás
            log.warning("panel LAN: acta del reflejo no disponible", exc_info=True)
            return None

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

    def _lora_section(self) -> dict | None:
        """[T-2.33] Salud de gabinetes secundarios LoRa (o ``None`` sin radio).

        ``None`` ⇒ el panel pinta «SIN RADIO LORA · MÓDULO DESHABILITADO»;
        con radio y lista vacía ⇒ «SIN GABINETES SECUNDARIOS PROVISIONADOS».
        """
        try:
            if self._lora is None:
                return None
            return self._lora.snapshot()
        except Exception:  # noqa: BLE001 — sección no-crítica
            log.warning("panel LAN: lora no disponible", exc_info=True)
            return None

    def _network_alert_section(self) -> dict | None:
        """[T-2.32] Actuación comandada por el quórum de red (o ``None``).

        Defensiva como el resto: sin dispatcher (arranques parciales/tests) o
        roto ⇒ ``None`` — el panel simplemente no rotula «QUÓRUM RED».
        """
        try:
            if self._dispatch is None:
                return None
            return self._dispatch.network_alert()
        except Exception:  # noqa: BLE001 — sección no-crítica
            log.warning("panel LAN: network_alert no disponible", exc_info=True)
            return None

    def _cloud_section(self) -> dict:
        """Enlace con la nube + estado ADMINISTRATIVO del gabinete (T-2.65).

        `online` es el flag de la sesión MQTT y nada más: por eso el panel decía
        `ENLACE NUBE · CONECTADO` mientras la consola ya no veía al gabinete —
        media verdad. `admin_state` es el otro dato, y NO se infiere de la edad ni
        del silencio: es un hecho positivo del último documento firmado.

        Se lee del ConfigStore VIVO en cada llamada, jamás de un `EdgeSettings`
        capturado en `__init__`: `apply_signed_update` REEMPLAZA el objeto entero,
        así que una copia guardada se quedaría clavada en "active" para siempre.

        Fail-open hacia proteger-y-callar: sin ConfigStore, con el módulo caído o
        con un valor que no sea exactamente "retired", se reporta `active`. Un
        módulo averiado no puede inventar un `DADO DE BAJA` en un gabinete sano.
        """
        try:
            admin = "active"
            if self._config is not None and self._config.current().is_retired:
                admin = "retired"
            if self._cloud is None:
                return {
                    "online": False,
                    "mqtt_rtt_ms": None,
                    "queued": None,
                    "admin_state": admin,
                }
            rtt = getattr(self._cloud, "mqtt_rtt_ms", None)
            return {
                "online": bool(getattr(self._cloud, "online", False)),
                "mqtt_rtt_ms": float(rtt) if rtt is not None else None,
                "queued": int(getattr(self._cloud, "queued", 0)),
                "admin_state": admin,
            }
        except Exception:  # noqa: BLE001
            log.warning("panel LAN: sección cloud falló", exc_info=True)
            return {"online": False, "mqtt_rtt_ms": None, "queued": None, "admin_state": "active"}

    def _evidence_section(self, now: datetime) -> dict | None:
        """[T-2.67] Evidencia miniSEED pendiente y desenlace del respaldo.

        La consola de nube tiene vista de evidencia desde T-2.43; el panel del
        gabinete —lo único que queda CUANDO NO HAY NUBE, que es cuando importa—
        no tenía ninguna: en el gabinete real hay evidencia pendiente de más de
        dos semanas y `/api/status` no traía ni la palabra.

        Es una vista de ESTADO, no de dato (regla de oro 9): aquí no viaja ni
        una muestra ni la key de S3 (que lleva el `tenant_id`, y el GET del
        panel es abierto en la LAN). Y no toca disco: lee la instantánea en
        memoria del `BackfillManager`, que se re-verifica contra el directorio
        al arrancar y al cerrar cada pasada — `status()` corre a la cadencia del
        kiosco. Las EDADES se resuelven aquí (ver `_age_s`).
        """
        try:
            if self._backfill is None:
                return None
            snap = self._backfill.evidence_snapshot()
            items = [
                {
                    "event_id": str(item.get("event_id", "")),
                    "age_s": _age_s(item.get("start"), now),
                }
                for item in snap.get("items", ())
            ]
            return {
                "pending": int(snap["pending"]),
                "items": items,
                # Pendientes que NO se pueden leer (contenido irreparable ya
                # apartado + errores de E/S). Van NOMBRADOS: quien está de pie
                # frente al gabinete necesita saber QUÉ fichero borrar, y este
                # panel es el único sitio donde se ve sin nube. Es un `event_id`
                # ya conocido por el gabinete, no la key de S3 (que lleva el
                # tenant_id y jamás sale por este GET abierto en la LAN).
                "unreadable": int(snap.get("unreadable") or 0),
                "unreadable_items": [str(name) for name in snap.get("unreadable_items", ())],
                # reloj: heredado — `oldest_pending_at` es el `start` de una ventana
                # leída del `.json` pendiente, que sobrevive a los reinicios. Ésta SÍ
                # es una de las que `_age_s` declara bien.
                "oldest_pending_age_s": _age_s(snap.get("oldest_pending_at"), now),
                # [T-7.60·disfraz] Del cronómetro, no de una fecha: ver `_edad_mono`.
                # reloj: monotonico — la selló ESTE proceso, en memoria, y nunca se guarda
                "checked_age_s": _edad_mono(snap.get("checked_mono")),
                "phase": str(snap.get("phase") or "idle"),
                "durable": bool(snap.get("durable")),
                "uploaded_total": int(snap["uploaded_total"]),
                # El descarte por ring vacío PIERDE la evidencia y borra el
                # pendiente igual que un éxito: sin su propio contador, el panel
                # no podría distinguir "archivada" de "perdida para siempre".
                "discarded_no_data_total": int(snap["discarded_no_data_total"]),
                "failed_total": int(snap["failed_total"]),
                "extract_failed_total": int(snap["extract_failed_total"]),
                "last_result": snap.get("last_result"),
                # [T-7.60·disfraz] Del cronómetro, no de una fecha: ver `_edad_mono`.
                # reloj: monotonico — la selló ESTE proceso, en memoria, y nunca se guarda
                "last_result_age_s": _edad_mono(snap.get("last_result_mono")),
                "stale_after_s": float(snap["stale_after_s"]),
            }
        except Exception:  # noqa: BLE001 — sección no-crítica
            log.warning("panel LAN: sección evidencia no disponible", exc_info=True)
            return None

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

    # ------------------------------------------------------------- CCTV (T-3.11.b)

    def request_cctv_grant(self, payload: dict) -> dict:
        """Pide a la nube la URL pre-firmada de un clip o una captura, y la devuelve.

        Es la ÚNICA puerta del CCTV hacia el gabinete, y es deliberadamente estrecha: entra
        un JSON de cinco campos y sale una URL. **El vídeo no pasa por aquí** — `takab-cctv`
        sube los bytes él mismo a S3 con esa URL. Si esto transportara el clip, un fichero
        de 300 MB cruzaría el proceso que sostiene la telemetría del gabinete.

        Lanza `ActionUnavailable` cuando la nube no contesta a tiempo, que es un 409 y no un
        500: la petición es válida, lo que falta es enlace. El CCTV reintenta con su propio
        ritmo y el clip sigue en `pendientes/` mientras tanto.
        """
        if self._backfill is None:
            raise ActionUnavailable("este gabinete no tiene backfill: no puede pedir grants")
        try:
            mode = str(payload["mode"])
            event_id = str(payload["event_id"])
            sha256 = str(payload["sha256"])
            ts_from = datetime.fromisoformat(str(payload["ts_from"]))
            ts_to = datetime.fromisoformat(str(payload["ts_to"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ActionUnavailable(f"petición de grant malformada: {exc}") from exc

        try:
            grant = self._backfill.request_cctv_grant(
                mode=mode, event_id=event_id, sha256=sha256, ts_from=ts_from, ts_to=ts_to
            )
        except ValueError as exc:  # modo desconocido
            raise ActionUnavailable(str(exc)) from exc
        if grant is None:
            raise ActionUnavailable("la nube no otorgó grant a tiempo (¿sin enlace?)")
        return grant

    def verify_cctv_signature(self, cuerpo: bytes, firma: str | None) -> bool:
        """¿Viene esta petición del CCTV de este sitio? **Fail-closed sin clave.**

        Sin `SecurityManager` provisionado no se verifica nada y por tanto no se concede
        nada: un gabinete sin clave de CCTV no es un gabinete que confía en cualquiera, es
        un gabinete que todavía no tiene CCTV.
        """
        if self._security is None:
            log.warning("grant de cctv rechazado: este gabinete no tiene clave de CCTV")
            return False
        return bool(self._security.verify_cctv(cuerpo, firma or ""))

    def _record_action(self, action: str) -> None:
        with self._actions_lock:
            self._actions.append({"at": utcnow().isoformat(), "action": action, "via": "lan"})

    def _accion(self, nombre: str, **kwargs):
        """[T-2.86.a · RO-4.e] ÚNICA puerta del panel hacia el dueño de los pines.

        Existe para que la bitácora no dependa de que cada endpoint se acuerde: la
        causa se **deriva** del nombre de la acción, que es una clave de la lista
        blanca `GPIO_ACTIONS`, y un test exige que esa lista esté cubierta entera.
        Una acción nueva del panel entra en el registro sola o pone el build en rojo.

        El registro va DESPUÉS de mover los relés y nunca antes: el operador que
        pulsa «probar» no puede quedarse esperando a un fsync. Y un intento FALLIDO
        también deja fila —«lo que se intentó y no pasó» es justo lo que faltaba—,
        pero la excepción se re-lanza igual: el panel la traduce a su código HTTP.
        """
        from takab_edge.audit import ACTOR_LAN, cause_for_gpio_action

        exito, detalle = True, ""
        try:
            return self._link.action(nombre, **kwargs)
        except Exception as exc:
            exito, detalle = False, f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if self._ledger is not None:
                self._ledger.record(
                    cause=cause_for_gpio_action(nombre),
                    actor=ACTOR_LAN,
                    channel=ActuatorChannel.SYSTEM,
                    action=nombre,
                    success=exito,
                    detail=detalle,
                )

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
        # ⚠️ [T-7.60] MONOTÓNICO. Medido el 2026-09-19 en el gabinete real:
        # aquí decía 77 851 s (21.6 h) y el kernel 30 323 s (8.4 h). El Pi no
        # tiene RTC, así que NTP corrigió el reloj 13 h 25 min hacia adelante
        # unos segundos después del arranque y la resta de pared se lo tragó
        # entero. Y no es cosmético: el uptime es lo PRIMERO que se mira para
        # saber si un gabinete se reinició, así que un valor inflado esconde
        # justo el suceso que se está buscando.
        # reloj: monotonico — tiempo encendido de ESTA máquina
        uptime = self._arranque.transcurrido() if self._arranque else None
        # [T-2.68] Filas y diagnóstico salen de UNA sola lectura: pedirlos por
        # separado los dejaría desincronizados entre sí (dos snapshots distintos
        # del mismo lock) y el rótulo explicaría una lista que ya no es esa.
        # [T-2.70.a·D2/P1] Y esa lectura es AHORA la del gabinete entero: los
        # cuatro booleanos de abajo, el motivo de la sirena, las latencias y las
        # dos pruebas salen todos del MISMO instante — y ninguno puede ya tumbar
        # el request entero (`None` = «no se pudo medir», que la UI pinta S/D).
        snap, gpio_reason = self._gpio_snapshot()
        relays, relays_status = self._relays_view(snap, gpio_reason)
        return {
            # Identidad VIVA (settings), no del snapshot: sobrevive a health caído.
            "gateway_id": self._gateway_id
            or (self._health.last_snapshot.gateway_id if self._health.last_snapshot else ""),
            "site_name": self._site_name,
            # [T-5.26] Identidad correlacionable. Cadena vacía ⇒ no configurado;
            # el panel lo declara S/D en vez de dejar el hueco (regla de oro 7).
            "iot_thing": self._iot_thing,
            "station_code": self._station_code,
            # [T-7.23] La identidad COMPLETA del instrumento, `red.estación.loc.
            # canal`, una entrada por canal. `station_code` se queda como está —
            # es contrato con la nube—; esto es lo que la vista sismógrafo rotula
            # sobre la traza, como lo rotula cualquier estación sísmica. Lista
            # vacía = sin provisionar, y el panel lo dice con `S/D`.
            "station_nslc": list(self._station_nslc),
            "now": now.isoformat(),
            # reloj: monotonico — `uptime` es un `Cronometro`; ver el bloque de arriba
            "uptime_s": uptime,
            # [T-7.60] EL ARRANQUE, Y SE DERIVA — jamás se recuerda.
            #
            # Quien llega a un gabinete después de un corte quiere LA HORA a la
            # que arrancó, no una duración que tiene que restar de cabeza; y un
            # `uptime_s` a secas obliga a eso justamente cuando hay prisa.
            #
            # ⚠️ Y la forma de obtenerlo es contraintuitiva: si este proceso
            # guardara su arranque como fecha al iniciarse, guardaría la hora
            # ANTERIOR a que NTP corrigiera —el Pi no tiene RTC—, o sea el error
            # de 13 h 25 min del 2026-09-19 sellado para siempre. Restando el
            # uptime MONOTÓNICO del `now` ya corregido sale la hora verdadera, y
            # además se corrige sola en cuanto NTP sincroniza.
            #
            # Es el defecto de esta ficha visto del revés: allí una fecha se
            # disfrazaba de duración, y aquí la fecha buena sólo se consigue
            # restando la duración buena.
            # reloj: monotonico — `uptime` es un cronómetro; `now` es pared ya corregida
            "booted_at": (
                (now - timedelta(seconds=uptime)).isoformat() if uptime is not None else None
            ),
            "refresh_ms": self._refresh_ms,
            # Distinguir alerta REAL vs. sirena sonando vs. silenciado (regla de oro 7):
            "sasmex_active": snap.sasmex_active if snap is not None else None,
            "siren_sounding": snap.siren_sounding if snap is not None else None,
            "siren_reason": self._siren_reason(snap),
            "audible_silenced": snap.audible_silenced if snap is not None else None,
            # [T-2.26] Enclave vivo (SASMEX o rules): el panel ofrece CERRAR
            # ALERTA mientras esto sea true, aunque el tier ya haya decaído.
            "alert_latched": snap.alert_latched if snap is not None else None,
            "network_alert": self._network_alert_section(),
            "lora": self._lora_section(),
            "last_tier": last_tier,
            "relays": relays,
            # [T-2.68] POR QUÉ la lista es esa. `relays` es un hecho eléctrico y
            # no explica nada: vacía significaba cuatro cosas y corta, ninguna.
            "relays_status": relays_status,
            # [T-2.146] SPOF-02: quién gobierna la sirena. Sale de la MISMA
            # instantánea que los relés y los cuatro booleanos de arriba.
            "keepalive": self._keepalive_view(snap if isinstance(snap, GpioSnapshot) else None),
            # Compat con el panel previo: hora del último dato de salud (o ahora).
            "captured_at": (health or {}).get("captured_at", now.isoformat()),
            # Fase 2.1 (contrato §5.1 de la spec del panel): memoria viva expuesta.
            "site_lat": site["site_lat"],
            "site_lon": site["site_lon"],
            "neighbors": site["neighbors"],
            "config_version": self._config_version(),
            "thresholds": self._thresholds_section(),
            "latencies": self._latencies_section(snap),
            "seedlink": self._seedlink_section(),
            "calibration": self._calibration_section(),
            # [T-2.29] Punto 0 de la brújula (o null: el panel usa media rodante).
            "rose_zero": self._rose_zero.current(),
            "shake_history": self._shake_history_section(),
            "signal": self._signal_section(now),
            "health": health,
            "cloud": self._cloud_section(),
            # [T-2.67] Respaldo de evidencia: estado, jamás muestras (regla 9).
            "evidence": self._evidence_section(now),
            "drill": self._drill_section(),
            "actuation_test": self._actuation_test_section(snap, now),
            "test_mode": self._test_mode_section(snap),
            "audio": self._audio_section(),
            "events": self._events_section(),
        }

    def _test_mode_section(self, snap: GpioSnapshot | None) -> dict:
        """Modo prueba del WR-1 (T-1.69): banner + cuenta atrás mientras la nube está muda."""
        if snap is None:
            return {"active": False, "remaining_s": 0.0}
        return {
            "active": bool(snap.test_mode_active),
            "remaining_s": round(snap.test_mode_remaining_s, 1),
        }

    def _actuation_test_section(self, snap: GpioSnapshot | None, now: datetime) -> dict:
        """Prueba local de actuación (T-1.67): banner mientras sostiene + resultado.

        [T-2.85.a] Viaja además CUÁNDO acabó. Sin eso, el panel pintaba —o mejor
        dicho, podía pintar— un resultado sin saber si era de hace tres segundos
        o de la semana pasada, y un `TODOS CONFIRMARON` de hace nueve días sobre
        el gas y los ascensores es exactamente el dato congelado en verde que
        prohíbe la regla de oro 7.

        `age_s` se deriva aquí y no en el navegador a propósito: el reloj del
        equipo del operador no tiene por qué coincidir con el del gabinete, y
        restar dos relojes distintos ya costó una corrección en este panel.
        """
        active = bool(snap.actuation_test_active) if snap is not None else False
        with self._actions_lock:
            results = self._last_actuation_test
            acabada = self._last_actuation_test_at
        return {
            "active": active,
            "results": results,
            "finished_at": None if acabada is None else acabada.isoformat(),
            # reloj: heredado — la última prueba de actuación se persiste
            "age_s": None
            if acabada is None
            else round(max(0.0, (now - acabada).total_seconds()), 1),
        }

    def _siren_reason(self, snap: GpioSnapshot | None) -> str | None:
        """[T-2.49] POR QUÉ suena la sirena. `siren_sounding` es un booleano
        ELÉCTRICO y no distingue nada.

        T-2.49 derivó `gpio.siren_reason` para que el ALTAVOZ dejara de sonar
        igual en una prueba que en un sismo; el panel se quedó atrás leyendo solo
        el booleano. Quien llega a mitad de un self-test ve «SIRENA: SONANDO» y
        no tiene forma de saber que no está pasando nada — que es exactamente el
        problema que T-2.49 arregló para el oído y no para la vista.

        Sección no-crítica: rota ⇒ ``None`` (el panel no rotula), jamás un 500.
        """
        if snap is None:
            return None
        reason = snap.siren_reason
        return None if reason is None else str(reason.value)

    def _audio_profile(self) -> dict | None:
        """[T-2.49] Perfil de tonos EFECTIVO, en la forma que el panel necesita.

        `applied`/`rejected` mapean slot → id de catálogo. Un ID rechazado (por
        desconocido, o RESERVADO como el tono oficial de SASMEX) deja al gabinete
        sonando el tono ANTERIOR — y una prueba sin tono de prueba CALLA. Eso solo
        se veía en el journal del Pi y en `HealthSnapshot.audio`, que la nube hoy
        descarta por falta de columna: el único que puede actuar sobre ello es
        quien está de pie frente al gabinete.

        Las RUTAS de disco (`siren_path`/`test_path`) NO se publican: `/api/status`
        es una lectura ABIERTA en la LAN y el panel solo necesita saber SI hay
        tono de prueba, no dónde vive.
        """
        try:
            report = self._audio.profile_report
            return {
                "applied": dict(report.get("applied") or {}),
                "rejected": dict(report.get("rejected") or {}),
                "test_tone": bool(report.get("test_path")),
            }
        except Exception:  # noqa: BLE001 — sección no-crítica del panel
            log.warning("panel LAN: perfil de tonos no disponible", exc_info=True)
            return None

    def audit_state(self) -> dict | None:
        """[T-2.86.a] Salud de la bitácora local de actuación, para quien la pinte.

        **Deliberadamente NO está en `status()` todavía.** El panel tiene una guarda
        derivada (`test_local_api_panel.py`) que exige que toda clave de `status()`
        se RENDERICE: añadirla sin su tarjeta sería una clave que el kiosco ignora en
        silencio, que es la clase de defecto que T-2.59 ya costó. La declaración del
        fallo existe mientras tanto por `log.error` en el propio `ActuationLedger`.

        Defensiva como el resto: `None` = no se pudo leer, jamás un cero que parezca
        «todo en orden».
        """
        try:
            if self._ledger is None:
                return None
            return self._ledger.state()
        except Exception:  # noqa: BLE001 — sección no-crítica del panel
            log.warning("panel LAN: estado de la bitácora no disponible", exc_info=True)
            return None

    def _audio_section(self) -> dict | None:
        """Voceo (A-6): la UI solo muestra el botón de drill si está habilitado."""
        try:
            if self._audio is None:
                return None
            return {
                "enabled": bool(self._audio.enabled),
                "sounding": bool(self._audio.sounding),
                "profile": self._audio_profile(),
            }
        except Exception:  # noqa: BLE001
            log.warning("panel LAN: sección de audio no disponible", exc_info=True)
            return None

    def silence(self) -> None:
        """Comando de silencio por LAN: apaga los audibles YA (sin tocar el estrobo)."""
        self._accion("silence", silenced=True)
        self._record_action("silence")
        log.warning("silencio solicitado por LAN")

    def run_siren_test(self) -> None:
        """Prueba de sirena por LAN (self-test acotado, no es una alerta real)."""
        self._accion("siren_test")
        self._record_action("siren_test")
        log.warning("prueba de sirena solicitada por LAN")

    def run_actuator_test(self) -> None:
        """Prueba LOCAL de actuación por LAN (T-1.67): ejercita TODO el gabinete.

        Sirena+estrobo suenan/se ven; gas/ascensor/puertas hacen su pulso de
        verificación. NO es una alerta real: no publica evento ni abre incidente
        (el gpio jamás dispara los callbacks SASMEX). Corre síncrono en el hilo
        de ESTE request (el servidor es multihilo; el reflejo nunca lo espera);
        el pulso dura ~1 s y la sirena sigue sonando hasta que vence el sostén.
        El resultado por relé aflora en ``status()`` —con la hora en que acabó—
        y el panel lo pinta relé a relé (tarjeta «Última prueba de actuadores»,
        T-2.85.a). Un campo que viaja y no se pinta lo caza `test_panel_render_census`.
        """
        result = self._accion("actuation_test")
        with self._actions_lock:
            self._last_actuation_test = result
            self._last_actuation_test_at = utcnow()
        if self._lora is not None:
            # [T-2.33] Los secundarios también se prueban: TEST hace destellar el
            # estrobo remoto SIN sirena (verificación de enlace + actuador).
            try:
                self._lora.propagate("test", strobe=True)
            except Exception:  # noqa: BLE001 — la prueba local jamás falla por esto
                log.exception("lora.propagate('test') falló (aislado)")
        self._record_action("actuator_test")
        log.warning("prueba local de actuación por LAN (NO es alerta real)")

    def toggle_test_mode(self) -> None:
        """Modo prueba del WR-1 por LAN (T-1.69): arma/desarma la ventana.

        Armado: un disparo (WR-1 real o instrumental) protege en LOCAL igual que
        siempre, pero NO se publica a la nube (sin incidente ni notificación). Es
        un toggle: el primer toque arma (ventana corta auto-expirable), el segundo
        desarma. Sirve para probar el WR-1 sin generar ruido en producción.
        """
        if self._link.snapshot().test_mode_active:
            self._accion("disarm_test_mode")
            self._record_action("test_mode_off")
        else:
            self._accion("arm_test_mode")
            self._record_action("test_mode_on")

    def reset_alert(self) -> None:
        """Cierra/re-arma la alerta enclavada por LAN (vuelve a operación normal)."""
        # Orden gpio→rules a propósito (falla seguro ante un disparo concurrente):
        # si un sismo vivo re-enclava entre ambas llamadas, los relés QUEDAN en
        # protección y la siguiente ventana de features re-emite el tier.
        self._accion("reset")
        # [T-2.26] Sin esto, last_tier quedaba congelado en el tier del episodio
        # hasta la siguiente feature — con SeedLink caído, PARA SIEMPRE.
        self._rules.reset()
        if self._dispatch is not None:
            # [T-2.32] La fuente «QUÓRUM RED» también se cierra con la alerta.
            try:
                self._dispatch.clear_network_alert()
            except Exception:  # noqa: BLE001 — el cierre local jamás falla por esto
                log.exception("clear_network_alert() en reset falló (aislado)")
        if self._lora is not None:
            # [T-2.33] CERRAR ALERTA también libera los secundarios (ALARM_CLEAR
            # con repeat-until-ack; el estado de ack queda visible en el panel).
            try:
                self._lora.propagate("clear")
            except Exception:  # noqa: BLE001 — el cierre local jamás falla por esto
                log.exception("lora.propagate('clear') en reset falló (aislado)")
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
        """Voceo de SIMULACRO por LAN (A-6): mensaje de drill, SIN tocar relés.

        [T-5.17] Y deja fila en la BITÁCORA LOCAL, no solo en la `deque` de
        `_actions`, que vive en RAM y la borra un reinicio. Esto sale por el
        altavoz de un edificio con gente dentro; que la única constancia fuera un
        anillo en memoria y una línea del journal significaba que «¿qué sonó el 19
        de septiembre en la torre B?» solo se podía contestar con SSH y suerte.

        La fila lleva el ASSET Y SU HASH, no solo el verbo: «se voceó» sin decir
        qué se voceó no responde a un perito.
        """
        if self._audio is None:
            log.warning("drill de voceo solicitado sin módulo de audio")
            return
        evidencia = {}
        try:
            evidencia = dict(self._audio.simulacro_evidence())
        except Exception:  # noqa: BLE001 — advisory: la evidencia no puede tumbar el voceo
            log.exception("no se pudo resolver la evidencia de audio del voceo LAN (aislado)")
        self._audio.play_simulacro()
        self._record_action("drill_audio")
        self._registrar_voceo(evidencia)
        log.warning("voceo de SIMULACRO solicitado por LAN (%s)", evidencia.get("path"))

    def _registrar_voceo(self, evidencia: dict) -> None:
        """[T-5.17] La fila persistida del voceo. Aislada: jamás tumba el botón."""
        if self._ledger is None:
            return
        from takab_edge.audit import ACTOR_LAN
        from takab_edge.contracts import ActuationCause

        sha = evidencia.get("sha256")
        detalle = (
            f"asset={evidencia.get('asset_id') or 'local'} "
            f"sha256={sha[:16] if sha else 'S/D'} "
            f"path={evidencia.get('path') or 'S/D'}"
        )
        try:
            self._ledger.record(
                cause=ActuationCause.LAN_DRILL_VOICE,
                actor=ACTOR_LAN,
                channel=ActuatorChannel.SYSTEM,
                action="drill_audio",
                # `will_sound=False` NO es un fallo: el voceo puede estar apagado
                # por su gate de hardware y el simulacro corre igual. Se registra
                # como intento no ejecutado para que la fila no afirme un sonido.
                success=bool(evidencia.get("will_sound")),
                detail=detalle,
            )
        except Exception:  # noqa: BLE001 — la bitácora jamás propaga
            log.exception("no se pudo registrar el voceo de simulacro (aislado)")

    @property
    def address(self) -> tuple[str, int] | None:
        """Dirección real de escucha (útil con puerto efímero en tests)."""
        return self._server.server_address if self._server else None

    def _on_start(self) -> None:
        self._started_at = utcnow()  # la FECHA de arranque, que sí se imprime
        self._arranque = Cronometro()  # [T-7.60] y el cronómetro, que la mide
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
