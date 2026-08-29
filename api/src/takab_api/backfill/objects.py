"""Ingesta de objetos S3 del backfill (T-1.25).

- ``backfill/{thing}/….ndjson(.gz)`` (bucket transfer): cada línea es un
  registro del spool del edge ``{topic, payload, …}`` y pasa por los
  ``ingest.handlers`` **VERBATIM** (mismo validate + mismo handler + misma
  idempotencia por PK/ON CONFLICT ⇒ re-ingesta = cero deltas). La identidad es
  el ``thing`` de la key: la nube solo pre-firmó esa key para ese principal
  verificado (grant service), así que la key ES la autoridad.
- ``evidence/{tenant}/{event_uuid}/{sha256}.mseed`` (bucket evidence): se
  verifica el sha256 REAL del objeto contra la key y se registra
  ``evidence_objects`` linkeando el incidente por ``event_uuid`` (el evento
  pudo llegar por el MISMO backfill: si aún no está, RETRY vía SQS).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg
from psycopg.rows import tuple_row

from takab_api.contracts.loader import ContractError, discriminate, kind_for_topic, validate
from takab_api.contracts.meta import Meta
from takab_api.ingest.handlers import HANDLERS, Outcome
from takab_api.ingest.registry import Registry
from takab_api.settings import Settings

logger = logging.getLogger("takab_api.backfill")

#: Rondas extra para líneas RETRY dentro del MISMO objeto (p.ej. un ack que
#: precede a su incidente unas líneas más abajo). Lo no resuelto ⇒ RETRY del
#: mensaje SQS completo (idempotente).
_RETRY_ROUNDS = 3


@dataclass(frozen=True)
class ObjectResult:
    outcome: Outcome
    reason: str = ""
    ok: int = 0
    rejected: int = 0
    retried: int = 0


def process_s3_object(
    conn: psycopg.Connection,
    bucket: str,
    key: str,
    registry: Registry,
    settings: Settings,
    *,
    s3_client,
) -> ObjectResult:
    """Procesa un ObjectCreated; commit al final si terminó (OK). RETRY ⇒ el
    consumer NO borra el mensaje (redelivery idempotente)."""
    if key.startswith("backfill/"):
        return _process_ndjson(conn, bucket, key, registry, s3_client=s3_client)
    if key.startswith("evidence/"):
        # [T-3.11.b] El CCTV comparte prefijo con el miniSEED —el bucket solo notifica
        # `evidence/`— así que aquí es donde se separan, por el nombre del objeto.
        nombre = key.rsplit("/", 1)[-1]
        if nombre.startswith(("cctv-", "still-")):
            return _process_cctv(conn, bucket, key, s3_client=s3_client)
        return _process_evidence(conn, bucket, key, s3_client=s3_client)
    return ObjectResult(Outcome.REJECT, f"key sin ruta conocida: {key!r}")


# ------------------------------------------------------------------- NDJSON


def _process_ndjson(
    conn: psycopg.Connection, bucket: str, key: str, registry: Registry, *, s3_client
) -> ObjectResult:
    parts = key.split("/")
    if len(parts) < 3 or not parts[1]:
        return ObjectResult(Outcome.REJECT, f"key de backfill malformada: {key!r}")
    thing = parts[1]
    ctx = registry.resolve(thing)
    if ctx is None:
        return ObjectResult(Outcome.REJECT, f"unknown principal en key: {thing!r}")

    body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
    if key.endswith(".gz"):
        body = gzip.decompress(body)
    lines = [line for line in body.decode().splitlines() if line.strip()]

    ok = rejected = 0
    pending: list[tuple[int, dict]] = []
    for index, line in enumerate(lines):
        outcome, _reason = _ingest_line(conn, line, thing, ctx)
        if outcome is Outcome.OK:
            ok += 1
        elif outcome is Outcome.REJECT:
            rejected += 1
        else:
            try:
                pending.append((index, json.loads(line)))
            except ValueError:
                rejected += 1

    retried = 0
    for _round in range(_RETRY_ROUNDS):
        if not pending:
            break
        still: list[tuple[int, dict]] = []
        for index, record in pending:
            outcome, _reason = _ingest_record(conn, record, thing, ctx)
            if outcome is Outcome.OK:
                ok += 1
                retried += 1
            elif outcome is Outcome.REJECT:
                rejected += 1
            else:
                still.append((index, record))
        pending = still

    if pending:
        conn.rollback()  # nada parcial: el mensaje SQS se reentrega completo
        return ObjectResult(
            Outcome.RETRY,
            f"{len(pending)} líneas aún RETRY (p.ej. dependencias no ingeridas)",
            ok=0,
            rejected=rejected,
        )
    conn.commit()
    logger.info("backfill %s: %d ok, %d rechazadas (de %d)", key, ok, rejected, len(lines))
    return ObjectResult(Outcome.OK, ok=ok, rejected=rejected, retried=retried)


def _ingest_line(conn: psycopg.Connection, line: str, thing: str, ctx) -> tuple[Outcome, str]:
    try:
        record = json.loads(line)
    except ValueError:
        return Outcome.REJECT, "línea NDJSON inválida"
    if not isinstance(record, dict):
        return Outcome.REJECT, "línea no es objeto"
    return _ingest_record(conn, record, thing, ctx)


def _ingest_record(conn: psycopg.Connection, record: dict, thing: str, ctx) -> tuple[Outcome, str]:
    topic = record.get("topic")
    payload = record.get("payload")
    if not isinstance(topic, str) or not isinstance(payload, dict):
        return Outcome.REJECT, "registro sin topic/payload"
    try:
        kind = discriminate(kind_for_topic(topic), payload)
        validate(kind, payload)
    except ContractError as exc:
        return Outcome.REJECT, str(exc)
    handler = HANDLERS.get(kind)
    if handler is None:
        return Outcome.REJECT, f"sin handler para {kind!r}"
    meta = Meta(principal=thing, topic=topic, ts_iot=_spooled_at(record))
    result = handler(conn, payload, meta, ctx)
    return result.outcome, result.reason


def _spooled_at(record: dict) -> datetime | None:
    raw = record.get("spooled_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


# ----------------------------------------------------------------- evidencia


_INSERT_EVIDENCE_SQL = """
INSERT INTO evidence_objects (tenant_id, incident_id, kind, s3_key, sha256)
VALUES (%s, %s, 'miniseed', %s, %s)
ON CONFLICT DO NOTHING
"""


def _process_evidence(
    conn: psycopg.Connection, bucket: str, key: str, *, s3_client
) -> ObjectResult:
    parts = key.split("/")
    if len(parts) != 4 or not parts[3].endswith(".mseed"):
        return ObjectResult(Outcome.REJECT, f"key de evidencia malformada: {key!r}")
    _prefix, tenant_id, event_uuid, filename = parts
    expected_sha = filename.removesuffix(".mseed")

    body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
    digest = hashlib.sha256(body).hexdigest()
    if digest != expected_sha:
        return ObjectResult(
            Outcome.REJECT, f"sha256 no coincide con la key ({digest[:12]}…≠{expected_sha[:12]}…)"
        )

    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT incident_id, tenant_id FROM incidents WHERE event_uuid = %s",
            (event_uuid,),
        )
        row = cur.fetchone()
    if row is None:
        # El evento pudo venir en el MISMO backfill y aún no ingerirse: RETRY.
        conn.rollback()
        return ObjectResult(Outcome.RETRY, f"incidente {event_uuid} aún no ingerido")
    incident_id, incident_tenant = row
    if str(incident_tenant) != tenant_id:
        return ObjectResult(Outcome.REJECT, "tenant de la key ≠ tenant del incidente")

    conn.execute(_INSERT_EVIDENCE_SQL, (incident_tenant, incident_id, key, digest))
    conn.commit()
    logger.info("evidencia %s registrada (incidente %s)", key, incident_id)
    return ObjectResult(Outcome.OK, ok=1)


# --------------------------------------------------------------------- CCTV

#: [T-3.11.b] `ON CONFLICT DO NOTHING` sobre la restricción natural: la key lleva el
#: sha256 dentro, así que re-entregar el mismo objeto —que SQS hace, por diseño at-least-
#: once— no duplica la fila. `analysis_state` nace en 'pending': el clip queda registrado y
#: descargable **antes** de que exista quien lo analice, y el reporte lo declara en vez de
#: fingir un cero.
_INSERT_CLIP_SQL = """
INSERT INTO cctv_clips
  (tenant_id, incident_id, s3_key, sha256, size_bytes, started_at, ended_at, analysis_state)
VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
ON CONFLICT (incident_id, started_at, camera_id) DO NOTHING
"""

_INSERT_STILL_SQL = """
INSERT INTO cctv_stills
  (tenant_id, incident_id, s3_key, sha256, captured_at, role)
VALUES (%s, %s, %s, %s, %s, 'drip')
ON CONFLICT (incident_id, captured_at, camera_id) DO NOTHING
"""


def _process_cctv(conn: psycopg.Connection, bucket: str, key: str, *, s3_client) -> ObjectResult:
    """Registra un clip o una captura de CCTV recién subidos por el gabinete.

    Mismo esqueleto que `_process_evidence` y a propósito: se verifica el sha256 contra la
    key (el objeto es lo que dice ser), se resuelve el incidente por `event_uuid`, y se
    comprueba que el tenant de la key coincida con el del incidente — porque las FK de
    Postgres no comparan tenant y sin esto una key ajena alcanzaría el espacio de otro
    cliente.

    **El `RETRY` cuando el incidente aún no existe no es un detalle.** El clip tarda diez
    minutos en cortarse y puede subir ANTES de que el evento se haya ingerido si el
    gabinete estuvo sin red; devolver `REJECT` mandaría a la DLQ una evidencia buena.
    """
    parts = key.split("/")
    if len(parts) != 4:
        return ObjectResult(Outcome.REJECT, f"key de CCTV malformada: {key!r}")
    _prefix, tenant_id, event_uuid, filename = parts

    partido = _partir_nombre_cctv(filename)
    if partido is None:
        return ObjectResult(Outcome.REJECT, f"key de CCTV malformada: {key!r}")
    es_clip, inicio, fin, expected_sha = partido

    body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
    digest = hashlib.sha256(body).hexdigest()
    if digest != expected_sha:
        return ObjectResult(
            Outcome.REJECT, f"sha256 no coincide con la key ({digest[:12]}…≠{expected_sha[:12]}…)"
        )

    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT incident_id, tenant_id FROM incidents WHERE event_uuid = %s",
            (event_uuid,),
        )
        row = cur.fetchone()
    if row is None:
        conn.rollback()
        return ObjectResult(Outcome.RETRY, f"incidente {event_uuid} aún no ingerido")
    incident_id, incident_tenant = row
    if str(incident_tenant) != tenant_id:
        return ObjectResult(Outcome.REJECT, "tenant de la key ≠ tenant del incidente")

    if es_clip:
        conn.execute(
            _INSERT_CLIP_SQL,
            (incident_tenant, incident_id, key, digest, len(body), inicio, fin),
        )
    else:
        conn.execute(_INSERT_STILL_SQL, (incident_tenant, incident_id, key, digest, inicio))
    conn.commit()
    logger.info("cctv: %s registrado (incidente %s)", key, incident_id)
    return ObjectResult(Outcome.OK, ok=1)


_TS_KEY = "%Y%m%dT%H%M%SZ"


def _partir_nombre_cctv(filename: str) -> tuple[bool, datetime, datetime, str] | None:
    """`(es_clip, inicio, fin, sha256)` del nombre del objeto, o `None` si no cuadra.

    Formatos, fijados por `backfill.grants.canonical_key`:

    * ``cctv-{desde}_{hasta}-{sha256}.mp4``
    * ``still-{cuando}-{sha256}.jpg``

    Se analiza aqui y no se adivina en la base porque la notificacion de S3 **solo ve la
    key**: en este camino es la unica fuente de la ventana del clip.
    """
    if filename.startswith("cctv-") and filename.endswith(".mp4"):
        ventana, _, sha = filename[len("cctv-") : -len(".mp4")].rpartition("-")
        desde, _, hasta = ventana.partition("_")
        if not hasta:
            return None
        try:
            return (
                True,
                datetime.strptime(desde, _TS_KEY).replace(tzinfo=UTC),
                datetime.strptime(hasta, _TS_KEY).replace(tzinfo=UTC),
                sha,
            )
        except ValueError:
            return None
    if filename.startswith("still-") and filename.endswith(".jpg"):
        cuando, _, sha = filename[len("still-") : -len(".jpg")].rpartition("-")
        try:
            ts = datetime.strptime(cuando, _TS_KEY).replace(tzinfo=UTC)
        except ValueError:
            return None
        return (False, ts, ts, sha)
    return None
