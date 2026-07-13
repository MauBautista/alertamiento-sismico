"""Pasada del orquestador de notificaciones (T-1.21 · B6).

Dos fases por pasada, bajo un advisory lock propio (serializa instancias):

1. **ENQUEUE**: incidentes recientes (lookback) con ``state≠closed`` y sin
   jobs → ``plan_jobs`` (cascada / crítico paralelo / fail-open) + INSERT
   ``ON CONFLICT DO NOTHING`` (UNIQUE (incident, channel, mode) = idempotente).
2. **DISPATCH**: jobs ``pending`` con ``due_at ≤ now``, en bucle hasta agotar:
   - cascada ya satisfecha (algún cascade 'sent' del incidente) ⇒ ``skipped``;
   - éxito ⇒ ``sent`` + ``incident_actions kind='notify_sent'`` (canal, modo,
     latencia vs t0 y cumplimiento del deadline — evidencia del SLA);
   - fallo ⇒ ``failed`` + el SIGUIENTE cascade pendiente se ADELANTA a ``now``
     (escala ya; con proveedor sano el SMS sale en el mismo pass ≤30 s).
   El éxito de un cascade marca ``skipped`` el resto de su cascada. Los jobs
   ``parallel`` son independientes (fail-open y email crítico no se skipean).

Corre como ``takab_ingest`` (BYPASSRLS) en el worker ``python -m
takab_api.notify``; cloud-only, jamás en el camino de actuación del edge.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import psycopg

from takab_api.notify.config import resolve_destinations, resolve_inspector_emails
from takab_api.notify.plan import plan_jobs, resolve_params
from takab_api.notify.providers import NotifyError, NotifyProvider
from takab_api.settings import Settings

logger = logging.getLogger("takab_api.notify")

# Advisory lock propio (≠ engine 0x…1119, ≠ dictamen 0x…1120).
_NOTIFY_LOCK_KEY = 0x7A4B_1121

_NEW_INCIDENTS_SQL = """
SELECT i.incident_id, i.tenant_id, i.site_id, i.severity, i.trigger, i.opened_at
FROM incidents i
WHERE i.opened_at >= %(since)s
  AND i.opened_at <= %(now)s
  AND i.state <> 'closed'
  AND NOT EXISTS (
    SELECT 1 FROM notification_jobs j WHERE j.incident_id = i.incident_id
  )
ORDER BY i.opened_at, i.incident_id
"""

# rule_set activo del sitio (site preferente sobre tenant) — espejo del engine.
_RULESET_SQL = """
SELECT config
FROM rule_sets
WHERE is_active
  AND ( (scope_type = 'site'   AND scope_id = %(site)s)
     OR (scope_type = 'tenant' AND scope_id = %(tenant)s) )
ORDER BY (scope_type = 'site') DESC, version DESC
LIMIT 1
"""

_INSERT_JOB_SQL = """
INSERT INTO notification_jobs
  (tenant_id, incident_id, channel, mode, position, target, due_at, deadline_at)
VALUES (%(tenant)s, %(incident)s, %(channel)s, %(mode)s, %(position)s,
        %(target)s::jsonb, %(due_at)s, %(deadline_at)s)
ON CONFLICT (incident_id, channel, mode) WHERE action_id IS NULL DO NOTHING
"""

# [T-1.61] Solicitudes de dictamen SIN job y SIN dictamen firmado posterior —
# espejo del _PENDING_REQUEST_SQL de incidents_ops.py (409): una solicitud ya
# satisfecha no molesta al inspector.
_DICTAMEN_REQUESTS_SQL = """
SELECT a.action_id, a.incident_id, a.ts, a.actor, a.payload,
       i.tenant_id, i.site_id
FROM incident_actions a
JOIN incidents i ON i.incident_id = a.incident_id
WHERE a.kind = 'dictamen_request'
  AND a.ts >= %(since)s
  AND a.ts <= %(now)s
  AND NOT EXISTS (
    SELECT 1 FROM notification_jobs j WHERE j.action_id = a.action_id
  )
  AND NOT EXISTS (
    SELECT 1 FROM dictamens d
    WHERE d.incident_id = a.incident_id
      AND d.signed_by IS NOT NULL
      AND d.created_at > a.ts
  )
ORDER BY a.ts, a.action_id
"""

# 1 job por (action_id, channel) — índice único parcial de 0014: los re-runs
# del pass y las re-entregas NOTIFY no duplican el correo del inspector.
_INSERT_ACTION_JOB_SQL = """
INSERT INTO notification_jobs
  (tenant_id, incident_id, channel, mode, position, target, due_at, action_id)
VALUES (%(tenant)s, %(incident)s, 'email', 'parallel', 0,
        %(target)s::jsonb, %(due_at)s, %(action)s)
ON CONFLICT (action_id, channel) WHERE action_id IS NOT NULL DO NOTHING
"""

_DUE_JOBS_SQL = """
SELECT j.job_id, j.tenant_id, j.incident_id, j.channel, j.mode, j.position,
       j.target, j.due_at, j.deadline_at, j.action_id,
       i.severity, i.trigger, i.state, i.opened_at, i.event_id, i.site_id,
       s.name AS site_name, s.code AS site_code,
       a.actor AS action_actor, a.payload AS action_payload
FROM notification_jobs j
JOIN incidents i ON i.incident_id = j.incident_id
JOIN sites s ON s.site_id = i.site_id
LEFT JOIN incident_actions a ON a.action_id = j.action_id
WHERE j.status = 'pending' AND j.due_at <= %(now)s
ORDER BY j.due_at, j.position, j.job_id
"""

_CASCADE_SATISFIED_SQL = """
SELECT 1 FROM notification_jobs
WHERE incident_id = %(incident)s AND mode = 'cascade' AND status = 'sent'
LIMIT 1
"""

_SKIP_PENDING_CASCADE_SQL = """
UPDATE notification_jobs SET status = 'skipped'
WHERE incident_id = %(incident)s AND mode = 'cascade' AND status = 'pending'
"""

_MARK_SENT_SQL = """
UPDATE notification_jobs SET status = 'sent', sent_at = %(now)s
WHERE job_id = %(job)s
"""

_MARK_FAILED_SQL = """
UPDATE notification_jobs SET status = 'failed', error = %(error)s
WHERE job_id = %(job)s
"""

_ADVANCE_NEXT_SQL = """
UPDATE notification_jobs SET due_at = %(now)s
WHERE job_id = (
  SELECT job_id FROM notification_jobs
  WHERE incident_id = %(incident)s AND mode = 'cascade' AND status = 'pending'
    AND position > %(position)s
  ORDER BY position
  LIMIT 1
)
"""

# actor distintivo por canal/modo: la clave natural de idempotencia de acks
# (uq_incident_actions_ack: incident, kind, actor, ts) usa el ts de TRANSACCIÓN,
# y varios envíos del mismo incidente en un pass comparten now() — con actor
# plano 'system' colisionarían entre sí.
_ACTION_SQL = """
INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
VALUES (%(incident)s, %(tenant)s, 'notify_sent', %(actor)s, %(payload)s::jsonb)
"""


def run_notify_pass(
    conn: psycopg.Connection,
    settings: Settings,
    providers: dict[str, NotifyProvider],
    *,
    now: datetime | None = None,
    lookback_s: float | None = None,
) -> dict[str, int]:
    """Encola y despacha; devuelve contadores {enqueued, sent, failed, skipped}.
    Un COMMIT al final si hubo escrituras; si no, ROLLBACK (solo lectura)."""
    now = now or datetime.now(tz=UTC)
    lookback = settings.notify_lookback_s if lookback_s is None else lookback_s
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_NOTIFY_LOCK_KEY,))

    config_cache: dict[tuple[str, str], dict | None] = {}
    counts = {"enqueued": 0, "sent": 0, "failed": 0, "skipped": 0}

    counts["enqueued"] = _enqueue(conn, settings, config_cache, now=now, lookback_s=lookback)
    counts["enqueued"] += _enqueue_dictamen_requests(
        conn, config_cache, now=now, lookback_s=lookback
    )
    _dispatch(conn, providers, config_cache, counts, now=now, base_url=settings.notify_web_base_url)

    if any(counts.values()):
        conn.commit()
    else:
        conn.rollback()
    return counts


# --------------------------------------------------------------------- fases


def _enqueue(
    conn: psycopg.Connection,
    settings: Settings,
    config_cache: dict,
    *,
    now: datetime,
    lookback_s: float,
) -> int:
    params = resolve_params(settings)
    rows = conn.execute(
        _NEW_INCIDENTS_SQL, {"since": now - timedelta(seconds=lookback_s), "now": now}
    ).fetchall()
    inserted = 0
    for row in rows:
        destinations = resolve_destinations(_config_for(conn, config_cache, row))
        if not destinations:
            continue  # tenant sin cascada configurada: nada que encolar
        specs = plan_jobs(
            severity=row["severity"],
            trigger=row["trigger"],
            opened_at=row["opened_at"],
            destinations=destinations,
            params=params,
        )
        for spec in specs:
            result = conn.execute(
                _INSERT_JOB_SQL,
                {
                    "tenant": row["tenant_id"],
                    "incident": row["incident_id"],
                    "channel": spec.channel,
                    "mode": spec.mode,
                    "position": spec.position,
                    "target": json.dumps(spec.target),
                    "due_at": spec.due_at,
                    "deadline_at": spec.deadline_at,
                },
            )
            inserted += result.rowcount
    return inserted


def _enqueue_dictamen_requests(
    conn: psycopg.Connection,
    config_cache: dict,
    *,
    now: datetime,
    lookback_s: float,
) -> int:
    """[T-1.61] Un email al inspector por cada ``dictamen_request`` sin atender.

    El wake sale gratis: el trigger NOTIFY de 0004 ya cubre el INSERT en
    ``incident_actions`` y el worker ya escucha ``takab_live``.
    """
    rows = conn.execute(
        _DICTAMEN_REQUESTS_SQL, {"since": now - timedelta(seconds=lookback_s), "now": now}
    ).fetchall()
    inserted = 0
    for row in rows:
        emails = resolve_inspector_emails(_config_for(conn, config_cache, row))
        if not emails:
            logger.warning(
                "dictamen_request %s sin notifications.inspector_emails: se omite",
                row["action_id"],
            )
            continue
        result = conn.execute(
            _INSERT_ACTION_JOB_SQL,
            {
                "tenant": row["tenant_id"],
                "incident": row["incident_id"],
                "target": json.dumps({"to": emails}),
                "due_at": row["ts"],  # vence YA: paralelo, sin cascada
                "action": row["action_id"],
            },
        )
        inserted += result.rowcount
    return inserted


def _dispatch(
    conn: psycopg.Connection,
    providers: dict[str, NotifyProvider],
    config_cache: dict,
    counts: dict[str, int],
    *,
    now: datetime,
    base_url: str = "",
) -> None:
    # Bucle hasta agotar: cada job procesado sale de 'pending', y un fallo
    # puede ADELANTAR el siguiente cascade a `now` → re-select hasta vacío.
    while True:
        rows = conn.execute(_DUE_JOBS_SQL, {"now": now}).fetchall()
        if not rows:
            return
        for row in rows:
            _dispatch_one(conn, providers, config_cache, counts, row, now=now, base_url=base_url)


def _dispatch_one(
    conn: psycopg.Connection,
    providers: dict[str, NotifyProvider],
    config_cache: dict,
    counts: dict[str, int],
    row: dict,
    *,
    now: datetime,
    base_url: str = "",
) -> None:
    incident_id = row["incident_id"]
    if row["mode"] == "cascade":
        satisfied = conn.execute(_CASCADE_SATISFIED_SQL, {"incident": incident_id}).fetchone()
        if satisfied is not None:
            conn.execute(_SKIP_PENDING_CASCADE_SQL, {"incident": incident_id})
            counts["skipped"] += 1
            return

    provider = providers.get(row["channel"])
    if provider is None:  # canal sin provider cableado: cuenta como fallo
        _fail(conn, counts, row, "provider no configurado", now=now)
        return

    target = dict(row["target"])
    if row["channel"] == "webhook":
        # El secret vive en el rule_set, jamás en el job: se re-resuelve aquí.
        destinations = resolve_destinations(_config_for(conn, config_cache, row))
        secret = destinations.get("webhook", {}).get("secret")
        if secret:
            target["secret"] = secret

    try:
        provider.send(target, _message(row, base_url=base_url))
    except NotifyError as exc:
        _fail(conn, counts, row, str(exc), now=now)
        return

    conn.execute(_MARK_SENT_SQL, {"job": row["job_id"], "now": now})
    if row["mode"] == "cascade":
        counts["skipped"] += conn.execute(
            _SKIP_PENDING_CASCADE_SQL, {"incident": incident_id}
        ).rowcount
    latency_s = (now - row["opened_at"]).total_seconds()
    deadline_met = row["deadline_at"] is None or now <= row["deadline_at"]
    # [T-1.61] Actor único por acción: un email de incidente y uno de dictamen
    # en el MISMO pass comparten el ts de transacción — con actor plano
    # colisionarían contra uq_incident_actions_ack.
    actor_suffix = f":{row['action_id']}" if row.get("action_id") else ""
    conn.execute(
        _ACTION_SQL,
        {
            "incident": incident_id,
            "tenant": row["tenant_id"],
            "actor": f"system:notify:{row['channel']}:{row['mode']}{actor_suffix}",
            "payload": json.dumps(
                {
                    "job_id": str(row["job_id"]),
                    "channel": row["channel"],
                    "mode": row["mode"],
                    "latency_s": latency_s,
                    "deadline_met": deadline_met,
                }
            ),
        },
    )
    counts["sent"] += 1
    logger.info(
        "notify sent %s/%s incidente %s (latencia %.1fs, SLA %s)",
        row["channel"],
        row["mode"],
        incident_id,
        latency_s,
        "OK" if deadline_met else "VENCIDO",
    )


def _fail(
    conn: psycopg.Connection, counts: dict[str, int], row: dict, error: str, *, now: datetime
) -> None:
    conn.execute(_MARK_FAILED_SQL, {"job": row["job_id"], "error": error[:500]})
    if row["mode"] == "cascade":
        conn.execute(
            _ADVANCE_NEXT_SQL,
            {"incident": row["incident_id"], "position": row["position"], "now": now},
        )
    counts["failed"] += 1
    logger.warning(
        "notify failed %s/%s incidente %s: %s",
        row["channel"],
        row["mode"],
        row["incident_id"],
        error,
    )


# ------------------------------------------------------------------ helpers


def _config_for(conn: psycopg.Connection, cache: dict, row: dict) -> dict | None:
    key = (str(row["site_id"]), str(row["tenant_id"]))
    if key not in cache:
        found = conn.execute(
            _RULESET_SQL, {"site": row["site_id"], "tenant": row["tenant_id"]}
        ).fetchone()
        cache[key] = found["config"] if found else None
    return cache[key]


def _message(row: dict, *, base_url: str = "") -> dict:
    """Payload de notificación (MVP §8: sin T-MINUS ni magnitud preliminar).

    [T-1.61] Un job con ``action_id`` es una SOLICITUD DE DICTAMEN al
    inspector: headline propio, quién la pidió, su nota y el link directo al
    Triage (si hay base pública configurada).
    """
    message = {
        "source": "takab-ailert",
        "incident_id": str(row["incident_id"]),
        "site_id": str(row["site_id"]),
        "site_name": row["site_name"],
        "site_code": row["site_code"],
        "severity": row["severity"],
        "trigger": row["trigger"],
        "state": row["state"],
        "opened_at": row["opened_at"].isoformat(),
        "event_id": row["event_id"],
        "headline": f"TAKAB Ailert · Incidente {row['severity']} · {row['site_name']}",
    }
    if row.get("action_id"):
        payload = row.get("action_payload") or {}
        message["headline"] = f"TAKAB Ailert · Solicitud de dictamen · {row['site_name']}"
        message["kind"] = "dictamen_request"
        message["requested_by"] = payload.get("requested_by") or row.get("action_actor")
        message["note"] = payload.get("note")
        if base_url:
            message["link"] = f"{base_url.rstrip('/')}/triage?incident={row['incident_id']}"
    return message
