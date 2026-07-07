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
from datetime import datetime

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
