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
        path.write_text(
            json.dumps({"event_id": event_id, "start": start.isoformat(), "end": end.isoformat()})
        )
        if self._cloud.online:
            self._kick_evidence()

    def pending_evidence(self) -> list[str]:
        return sorted(p.stem for p in self._pending_dir.glob("*.json"))

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
            self._evidence_in_progress.clear()

    def _process_pending_evidence(self) -> None:
        if self._buffer is None:
            return
        now = self._clock()
        for path in sorted(self._pending_dir.glob("*.json")):
            try:
                spec = json.loads(path.read_text())
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
        miniseed = self._buffer.extract_window(start, end)
        if not miniseed:
            log.warning("backfill: evento %s sin datos en el ring; descartado", spec["event_id"])
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
        grant = self._request_grant(request)
        if grant is None:
            return None
        if not self._http_put(grant["url"], miniseed, "application/vnd.fdsn.mseed"):
            return None
        log.info("backfill: evidencia %s subida (%s)", spec["event_id"], grant.get("key"))
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
        log.info(
            "backfill activo (umbral %.0fs, jitter ≤%.0fs, %d evidencias pendientes)",
            self._settings.backfill_threshold_s,
            self._settings.backfill_jitter_max_s,
            len(self.pending_evidence()),
        )
