"""backfill — ruta S3 del spool + evidencia miniSEED de eventos offline (T-1.25).

Regla FASE-0 capa 4: un spool con **más de 15 min de datos** al reconectar va
por S3 en bloque (NDJSON.gz + URL pre-firmada) en vez de MQTT mensaje-a-mensaje
(el flush actual cubre ≤15 min). Anti-thundering-herd tras un apagón regional:
**jitter 0–120 s** antes del request, **un objeto por gateway a la vez**, y si
el grant no llega o el PUT falla, el spool VUELVE a la ruta MQTT — los datos
jamás se atoran (la nube deduplica por PK, así que el solape es inocuo).

Flujo (requiere el subscribe de T-1.23):
  edge → ``takab/backfill/request/<thing>`` {mode, ts_from, ts_to, …}
  nube → ``takab/backfill/grant/<thing>`` {request_id, url, key, expires_at}
  edge → HTTP PUT pre-firmado → S3 event → ``q-backfill`` → ingest verbatim.

La KEY es autoridad de la NUBE (v1.1.0: supersede el ``evidence/{event_id}/…``
pineado en T-1.11): el edge registra la key que llegó en el grant.

Evidencia offline: los eventos confirmados sin enlace se ENCOLAN durables
(archivos JSON, patrón spool); al reconectar se extrae la ventana miniSEED del
ring (T-1.7), se pide grant ``mode='evidence'`` con su sha256 y se sube.
"""

from __future__ import annotations

import gzip
import json
import logging
import threading
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from takab_edge.contracts import BackfillRequest, EvidenceObject, utcnow
from takab_edge.evidence import sha256_hex
from takab_edge.module import EdgeModule

if TYPE_CHECKING:
    from takab_edge.buffer import RingBuffer
    from takab_edge.cloud import CloudConnector
    from takab_edge.config import EdgeSettings

log = logging.getLogger("takab_edge.backfill")

#: Enfriamiento tras un intento S3 fallido: mientras corre, flush drena por MQTT.
_FAIL_COOLDOWN_S = 60.0

#: [T-2.67] Pendientes que viajan NOMBRADOS al panel (el resto solo cuenta).
_EVIDENCE_LIST_MAX = 8
#: [T-2.67] Un pendiente más viejo que esto ya no está "en camino": está ATASCADO.
#: El post-roll de la ventana son minutos y el grant vence en 30 s, así que una
#: hora no es impaciencia — es la frontera entre "va a subir" y "no va a subir".
_EVIDENCE_STUCK_AFTER_S = 3600.0

#: Sufijo de CUARENTENA de un pendiente cuyo contenido es irreparable.
#: Mismo patrón que `DurableSpool.load` (`.corrupt`): sale de la ruta de subida
#: pero NO del disco — se conserva para el forense y sigue contando en el panel.
#: Deja de casar con el glob `*.json`, así que `_scan_pending` lo cuenta aparte.
_QUARANTINE_SUFFIX = ".unreadable"


def _stamp(raw: object) -> datetime | None:
    """Fecha de un `start` guardado, o ``None`` si no se puede leer."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _oldest_first(item: dict) -> tuple[int, datetime]:
    """Orden del más VIEJO al más nuevo; lo ilegible va al final, jamás rompe."""
    stamp = _stamp(item.get("start"))
    return (1, datetime.max.replace(tzinfo=UTC)) if stamp is None else (0, stamp)


def default_http_put(url: str, body: bytes, content_type: str, timeout_s: float = 60.0) -> bool:
    """PUT pre-firmado con stdlib (sin deps nuevas en el Pi). True si 2xx."""
    request = urllib.request.Request(  # noqa: S310 — URL pre-firmada emitida por la nube
        url, data=body, method="PUT", headers={"Content-Type": content_type}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
            return 200 <= response.status < 300
    except OSError as exc:
        log.warning("PUT pre-firmado falló: %s", exc)
        return False


class BackfillManager(EdgeModule):
    """Ruta S3 del spool + evidencia offline. Un upload a la vez (por gateway)."""

    name = "backfill"
    depends_on = ("cloud", "buffer")

    def __init__(
        self,
        settings: EdgeSettings,
        cloud: CloudConnector,
        buffer: RingBuffer | None = None,
        pending_dir: str | Path | None = None,
        http_put: Callable[[str, bytes, str], bool] | None = None,
        jitter_s: Callable[[], float] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._cloud = cloud
        self._buffer = buffer
        self._http_put = http_put or default_http_put
        self._jitter_s = jitter_s or self._default_jitter
        self._clock = clock or utcnow
        self._pending_dir = Path(pending_dir or self._default_pending_dir())
        self._pending_dir.mkdir(parents=True, exist_ok=True)
        self._in_progress = threading.Event()
        self._evidence_in_progress = threading.Event()
        self._cooldown_until: datetime | None = None
        self._grants: dict[str, dict] = {}
        self._grant_arrived = threading.Condition()
        # [T-2.67] Instantánea del estado de la evidencia para el panel LAN.
        # Se REEMPLAZA por asignación atómica (nunca se muta en sitio): el panel
        # corre a la cadencia del kiosco y no puede tomar locks ni tocar disco.
        # Se siembra AQUÍ leyendo el directorio: un contador que arrancara en
        # cero con el directorio lleno mentiría tras cada reinicio.
        self._evidence_lock = threading.Lock()
        self._evidence_state: dict = {
            "pending": 0,
            "items": (),
            "oldest_pending_at": None,
            # Pendientes que NO se pueden leer (contenido irreparable ya apartado
            # + errores de E/S). Cuentan aparte de `pending` porque no van a
            # subir jamás, y se NOMBRAN: un número a secas no dice qué borrar.
            "unreadable": 0,
            "unreadable_items": (),
            "checked_at": None,
            "phase": "idle",
            # Sin `cloud_spool_dir` el pendiente vive en un tempdir NUEVO por
            # arranque: la evidencia se evapora al reiniciar y el conteo diría 0
            # honestamente para siempre. El panel lo declara en vez de callarlo.
            "durable": bool(pending_dir or settings.cloud_spool_dir),
            "uploaded_total": 0,
            "discarded_no_data_total": 0,
            "failed_total": 0,
            "extract_failed_total": 0,
            "last_result": None,
            "last_result_at": None,
            "stale_after_s": _EVIDENCE_STUCK_AFTER_S,
        }
        self._refresh_pending_state()
        # Cableado: decisor de ruta del flush + reintento de evidencia al reconectar.
        self._cloud.set_backfill_router(self)
        self._cloud.on_online(self._on_online)
        self._cloud.subscribe(self._settings.backfill_grant_topic, self.on_grant)

    def _default_jitter(self) -> float:
        import random

        return random.uniform(0.0, self._settings.backfill_jitter_max_s)  # noqa: S311

    def _default_pending_dir(self) -> str:
        import tempfile

        base = self._settings.cloud_spool_dir or tempfile.mkdtemp(prefix="takab-backfill-")
        return str(Path(base).parent / "backfill-pending")

    # ------------------------------------------------ router del flush (T-1.25)

    def should_take(self, connector: CloudConnector) -> bool:
        """S3 si hay upload en curso o el spool supera el umbral (y sin cooldown)."""
        if self._in_progress.is_set():
            return True  # un objeto por gateway a la vez; MQTT no compite
        now = self._clock()
        if self._cooldown_until is not None and now < self._cooldown_until:
            return False  # el último intento S3 falló: deja drenar por MQTT
        return connector.spool_span_s(now) > self._settings.backfill_threshold_s

    def kick(self) -> None:
        """Dispara el upload del spool en su propio hilo (idempotente)."""
        if self._in_progress.is_set():
            return
        self._in_progress.set()
        threading.Thread(target=self._run_spool_upload, name="backfill", daemon=True).start()

    # ------------------------------------------------------- spool → NDJSON.gz

    def ndjson_payload(self, records: list[tuple[str | None, dict]]) -> bytes:
        """NDJSON.gz del spool, en orden (una línea por registro, tal cual)."""
        lines = "\n".join(json.dumps(record, separators=(",", ":")) for _n, record in records)
        return gzip.compress((lines + "\n").encode())

    def _run_spool_upload(self) -> None:
        try:
            ok = self._upload_spool()
        except Exception:  # noqa: BLE001 — el hilo de backfill jamás mata al proceso
            log.exception("backfill: error inesperado subiendo el spool")
            ok = False
        finally:
            if not ok:
                self._cooldown_until = self._clock() + timedelta(seconds=_FAIL_COOLDOWN_S)
            self._in_progress.clear()
        if ok:
            log.info("backfill: spool subido por S3; MQTT vuelve a la normalidad")
        self._cloud.flush()  # retoma la ruta MQTT (resto del spool o cooldown)

    def _upload_spool(self) -> bool:
        self._sleep(self._jitter_s())  # anti-thundering-herd regional
        records = self._cloud.peek_spool()
        if not records:
            return True
        span = self._window(records)
        request = BackfillRequest(
            mode="backfill", ts_from=span[0], ts_to=span[1], lines=len(records)
        )
        grant = self._request_grant(request)
        if grant is None:
            log.warning("backfill: sin grant a tiempo; fallback a MQTT")
            return False
        body = self.ndjson_payload(records)
        if not self._http_put(grant["url"], body, "application/x-ndjson"):
            return False
        dropped = self._cloud.drop_spool([name for name, _r in records])
        log.info(
            "backfill: %d registros → s3://%s (%d retirados del spool)",
            len(records),
            grant.get("key", "?"),
            dropped,
        )
        return True

    @staticmethod
    def _window(records: list[tuple[str | None, dict]]) -> tuple[datetime, datetime]:
        stamps = []
        for _name, record in records:
            raw = record.get("spooled_at")
            if raw:
                try:
                    stamps.append(datetime.fromisoformat(raw))
                except ValueError:
                    continue
        if not stamps:
            now = datetime.now(UTC)
            return now, now
        return min(stamps), max(stamps)

    # ------------------------------------------------------ evidencia offline

    def queue_evidence(self, event_id: str, start: datetime, end: datetime) -> None:
        """Encola durable la evidencia de un evento (se sube al reconectar)."""
        path = self._pending_dir / f"{event_id}.json"
        nuevo = not path.exists()  # re-encolar el MISMO evento no suma dos veces
        # ATÓMICO (tmp + replace, como `DurableSpool.append` y `CatalogStore.
        # _write_atomic`): un corte de energía a media escritura —el escenario
        # típico, porque esto corre justo después de actuar en un sismo— dejaba
        # un `.json` TRUNCADO. Con la cuarentena de `_load_spec` eso sería
        # apartar evidencia legítima, y el `.tmp` intermedio también podía verse
        # desde una pasada concurrente. Ahora el fichero aparece entero o no
        # aparece. Sin `fsync`: esto está en el hilo de detección y la ventana
        # de post-roll da minutos de margen; la durabilidad dura la da el rename.
        tmp = path.with_name(path.name + ".tmp")  # fuera del glob `*.json`
        tmp.write_text(
            json.dumps({"event_id": event_id, "start": start.isoformat(), "end": end.isoformat()})
        )
        tmp.replace(path)
        if nuevo:
            # Alta EN MEMORIA: esto corre en el hilo de detección, justo después
            # de confirmar un evento — releer el directorio aquí sería pagar
            # disco en el peor momento posible.
            self._add_pending(event_id, start)
        if self._cloud.online:
            self._kick_evidence()

    def pending_evidence(self) -> list[str]:
        return sorted(p.stem for p in self._pending_dir.glob("*.json"))

    # ------------------------------------------- instantánea del panel (T-2.67)

    def evidence_snapshot(self) -> dict:
        """Estado de la evidencia SIN tocar disco (lo lee `LocalDashboard.status`).

        Fuera de este proceso solo existía UN bit observable —el `.json` está o
        no está— y ese bit colapsaba el mejor caso con el peor: una subida
        confirmada y un DESCARTE POR RING VACÍO (que pierde la evidencia) borran
        el fichero igual. De ahí los contadores acumulados, y no solo el último
        resultado. Las fechas viajan en ISO; la EDAD la calcula el panel contra
        el reloj del gabinete, no contra el del navegador del kiosco.
        """
        snap = self._evidence_state  # lectura atómica de la referencia
        return {**snap, "items": [dict(item) for item in snap["items"]]}

    def _set_evidence(self, **changes: object) -> None:
        with self._evidence_lock:
            self._evidence_state = {**self._evidence_state, **changes}

    def _load_spec(self, path: Path) -> dict | None:
        """Spec de un pendiente, o ``None`` si no se puede usar. **Jamás lanza.**

        Antes esto era `json.loads(path.read_text()).get(...)` con un `except
        (OSError, ValueError, TypeError)`: un fichero con `null`, `[]`, `"x"` o
        `42` —JSON VÁLIDO que no es un objeto— levantaba `AttributeError`, que no
        estaba en la lista, y se escapaba por el CONSTRUCTOR (dentro de
        `EdgeSupervisor.build()`, que no aísla por módulo ⇒ el gabinete entero no
        arrancaba) y por el `finally` de la pasada de evidencia (⇒ el testigo
        nunca se liberaba y el respaldo moría mudo).

        Dos fallos DISTINTOS y con desenlace distinto a propósito:

        * **Contenido irreparable** (no es un objeto JSON, truncado, no UTF-8,
          vacío): no va a mejorar nunca —`spec["end"]` fallaría en CADA pasada,
          reintento infinito sin progresar— ⇒ **cuarentena**.
        * **Error de E/S** (permisos, EIO, un fichero que otra pasada acaba de
          borrar): puede ser TRANSITORIO ⇒ no se toca nada; sólo se declara.
          Renombrar aquí podría apartar evidencia perfectamente buena.
        """
        try:
            raw = path.read_bytes()
        except OSError:
            # Incluye el directorio y el symlink roto con nombre `*.json`.
            log.warning("backfill: pendiente %s ilegible (E/S); se conserva", path.name)
            return None
        try:
            spec = json.loads(raw)  # `json.loads` acepta bytes y exige UTF-8
        except (ValueError, UnicodeDecodeError):
            spec = None
        if isinstance(spec, dict):
            return spec
        self._quarantine(path)
        return None

    def _quarantine(self, path: Path) -> None:
        """Aparta un pendiente irreparable SIN borrarlo (patrón `DurableSpool.load`).

        `log.error`, no `warning`: alguien escribió basura en el directorio que
        guarda la prueba de un sismo, y eso se investiga.
        """
        destino = path.with_name(path.name + _QUARANTINE_SUFFIX)
        try:
            path.rename(destino)
        except OSError:
            log.error("backfill: pendiente ILEGIBLE %s (no se pudo apartar)", path.name)
            return
        log.error(
            "backfill: pendiente ILEGIBLE apartado como %s; NO se subirá "
            "(el panel lo declara: revísalo y bórralo)",
            destino.name,
        )

    def _scan_pending(self) -> dict:
        """Recorre el directorio pendiente. SOLO en arranque y al cerrar pasada."""
        # Los ya apartados se cuentan PRIMERO y con el glob materializado antes
        # del bucle: si no se contaran, el hallazgo se evaporaría en la pasada
        # siguiente (ya no casan con `*.json`) y el operador no vería nada — el
        # pecado exacto que esta corrección viene a cerrar. El orden evita
        # además contar dos veces el que se aparte durante este mismo bucle.
        ilegibles: list[str] = [
            path.name.removesuffix(_QUARANTINE_SUFFIX).removesuffix(".json")
            for path in sorted(self._pending_dir.glob(f"*{_QUARANTINE_SUFFIX}"))
        ]
        items: list[dict] = []
        for path in sorted(self._pending_dir.glob("*.json")):
            spec = self._load_spec(path)
            if spec is None:
                ilegibles.append(path.stem)
                continue
            items.append({"event_id": path.stem, "start": str(spec.get("start") or "")})
        items.sort(key=_oldest_first)
        oldest = _stamp(items[0]["start"]) if items else None
        return {
            "pending": len(items),
            "items": tuple(items[:_EVIDENCE_LIST_MAX]),
            "oldest_pending_at": items[0]["start"] if oldest is not None else None,
            "unreadable": len(ilegibles),
            "unreadable_items": tuple(ilegibles[:_EVIDENCE_LIST_MAX]),
            "checked_at": self._clock().isoformat(),
        }

    def _refresh_pending_state(self) -> None:
        # `Exception`, no `OSError`: este método corre en el CONSTRUCTOR (dentro
        # de `EdgeSupervisor.build()`) y en el `finally` de la pasada. Es el
        # patrón de casa de `CatalogStore._load_once` / `RoseZeroStore._load_once`
        # / `SiteLocationCache._read_cache_once` — que este módulo no siguió.
        try:
            self._set_evidence(**self._scan_pending())
        except Exception:  # noqa: BLE001 — el conteo anterior sigue siendo el mejor dato
            log.warning("backfill: no se pudo verificar el directorio de evidencia", exc_info=True)

    def _add_pending(self, event_id: str, start: datetime) -> None:
        # Alta incremental: exacta salvo que el "más viejo" anterior fuera
        # ilegible (entonces gana el nuevo, y la siguiente pasada lo corrige
        # contra disco). Nunca inventa un pendiente que no exista.
        with self._evidence_lock:
            state = self._evidence_state
            nuevo = {"event_id": event_id, "start": start.isoformat()}
            items = sorted([*state["items"], nuevo], key=_oldest_first)[:_EVIDENCE_LIST_MAX]
            oldest = _stamp(state["oldest_pending_at"])
            if oldest is None or _oldest_first(nuevo)[1] < oldest:
                oldest_iso = nuevo["start"]
            else:
                oldest_iso = state["oldest_pending_at"]
            self._evidence_state = {
                **state,
                "pending": state["pending"] + 1,
                "items": tuple(items),
                "oldest_pending_at": oldest_iso,
            }

    #: Desenlace de UNA evidencia → contador acumulado que lo registra.
    _EVIDENCE_COUNTERS = {
        "uploaded": "uploaded_total",
        "discarded_no_data": "discarded_no_data_total",
        "extract_failed": "extract_failed_total",
        "grant_timeout": "failed_total",
        "put_failed": "failed_total",
    }

    def _record_evidence(self, result: str) -> None:
        counter = self._EVIDENCE_COUNTERS[result]
        with self._evidence_lock:
            state = self._evidence_state
            self._evidence_state = {
                **state,
                counter: state[counter] + 1,
                "last_result": result,
                "last_result_at": self._clock().isoformat(),
            }

    def _on_online(self) -> None:
        self._kick_evidence()

    def _kick_evidence(self) -> None:
        """Procesa las evidencias pendientes en su propio hilo (una pasada a la
        vez): el flujo request→grant→PUT BLOQUEA esperando el grant y jamás debe
        colgar el hilo del broker/reconexión."""
        if self._evidence_in_progress.is_set():
            return
        self._evidence_in_progress.set()
        threading.Thread(
            target=self._run_pending_evidence, name="backfill-evidence", daemon=True
        ).start()

    def _run_pending_evidence(self) -> None:
        try:
            self._process_pending_evidence()
        except Exception:  # noqa: BLE001 — el hilo de evidencia jamás mata al proceso
            log.exception("backfill: error inesperado procesando evidencias")
        finally:
            # [T-2.67] El conteo se re-verifica contra disco al CERRAR la pasada
            # (aunque haya reventado), y solo entonces se libera el testigo: quien
            # espere a que la pasada termine ve el estado ya verificado.
            self._refresh_pending_state()
            self._set_evidence(phase="idle")
            self._evidence_in_progress.clear()

    def _process_pending_evidence(self) -> None:
        if self._buffer is None:
            return
        now = self._clock()
        for path in sorted(self._pending_dir.glob("*.json")):
            spec = self._load_spec(path)
            if spec is None:
                continue  # ilegible: ya declarado (y apartado si era irreparable)
            try:
                if datetime.fromisoformat(spec["end"]) > now:
                    continue  # ventana aún incompleta (post-roll): reintentar luego
                uploaded = self._upload_evidence(spec)
            except Exception:  # noqa: BLE001 — una evidencia mala no bloquea las demás
                log.exception("backfill: evidencia %s falló; se reintentará", path.stem)
                continue
            if uploaded is not None:
                path.unlink(missing_ok=True)

    def _upload_evidence(self, spec: dict) -> EvidenceObject | None:
        start = datetime.fromisoformat(spec["start"])
        end = datetime.fromisoformat(spec["end"])
        try:
            miniseed = self._buffer.extract_window(start, end)
        except Exception:
            # [T-2.67] La extracción revienta con huecos en el ring (masked
            # arrays) y el pendiente se reintenta PARA SIEMPRE sin progresar.
            # El llamador ya loguea y conserva el fichero; aquí solo se declara.
            self._record_evidence("extract_failed")
            raise
        if not miniseed:
            log.warning("backfill: evento %s sin datos en el ring; descartado", spec["event_id"])
            # OJO: se borra el pendiente igual que si se hubiera subido — la
            # evidencia SE PIERDE. Su propio contador es lo único que separa
            # este caso del éxito para quien mira el panel.
            self._record_evidence("discarded_no_data")
            return EvidenceObject(  # se da por atendido (no hay nada que subir)
                event_id=spec["event_id"], s3_key="", sha256="", size_bytes=0
            )
        digest = sha256_hex(miniseed)
        request = BackfillRequest(
            mode="evidence",
            ts_from=start,
            ts_to=end,
            event_id=spec["event_id"],
            sha256=digest,
        )
        self._set_evidence(phase="requesting")
        grant = self._request_grant(request)
        if grant is None:
            # La ruta spool sí logueaba su fallback; esta callaba: desde fuera
            # era indistinguible de "no ha pasado nada".
            log.warning(
                "backfill: evidencia %s sin grant a tiempo; sigue pendiente", spec["event_id"]
            )
            self._record_evidence("grant_timeout")
            return None
        self._set_evidence(phase="uploading")
        if not self._http_put(grant["url"], miniseed, "application/vnd.fdsn.mseed"):
            log.warning("backfill: PUT de la evidencia %s falló; sigue pendiente", spec["event_id"])
            self._record_evidence("put_failed")
            return None
        log.info("backfill: evidencia %s subida (%s)", spec["event_id"], grant.get("key"))
        self._record_evidence("uploaded")
        return EvidenceObject(
            event_id=spec["event_id"],
            s3_key=grant.get("key", ""),  # la KEY es autoridad de la nube (v1.1.0)
            sha256=digest,
            size_bytes=len(miniseed),
        )

    # ------------------------------------------------------------- grant flow

    def on_grant(self, _topic: str, raw: bytes) -> None:
        """Callback del topic ``takab/backfill/grant/<thing>``. JAMÁS lanza."""
        try:
            grant = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            log.warning("grant descartado: JSON inválido")
            return
        if not isinstance(grant, dict) or not isinstance(grant.get("request_id"), str):
            log.warning("grant descartado: sin request_id")
            return
        with self._grant_arrived:
            self._grants[grant["request_id"]] = grant
            self._grant_arrived.notify_all()

    def _request_grant(self, request: BackfillRequest) -> dict | None:
        # DIRECTO al transporte (sin spool): un request encolado acabaría
        # DENTRO del NDJSON que intenta subir. Best-effort: sin enlace ⇒ None.
        published = self._cloud.publish_direct(self._settings.backfill_request_topic, request)
        if not published:
            return None
        deadline = self._settings.backfill_grant_timeout_s
        with self._grant_arrived:
            if self._grant_arrived.wait_for(
                lambda: request.request_id in self._grants, timeout=deadline
            ):
                return self._grants.pop(request.request_id)
        return None

    def _sleep(self, seconds: float) -> None:
        if seconds > 0:
            threading.Event().wait(seconds)

    def _on_start(self) -> None:
        self._refresh_pending_state()  # el directorio manda sobre lo que hubiera en memoria
        snap = self._evidence_state
        log.info(
            "backfill activo (umbral %.0fs, jitter ≤%.0fs, %d evidencias pendientes%s)",
            self._settings.backfill_threshold_s,
            self._settings.backfill_jitter_max_s,
            snap["pending"],
            "" if snap["durable"] else "; COLA NO DURABLE (sin cloud_spool_dir)",
        )
