"""Handlers de ingesta SQS→Timescale (T-1.17).

Interfaz: cada handler recibe ``(conn, payload, meta, ctx)`` — payload ya
validado contra ``shared/schemas/`` y SIN claves ``meta_*`` — y devuelve un
``HandlerResult``. No hace commit/rollback: eso lo decide el consumer (que
también construye el ``GatewayCtx`` desde el registro vía ``meta_principal``).

Regla de identidad (cross-check payload↔registro, db/schema.sql §1–§2 y
db/seeds/dev_fleet.sql): los IDs que viajan en el payload del edge son los
CÓDIGOS/SERIALES legibles, no UUIDs —
  * ``payload.tenant_id``  ≡ ``tenants.code``     (p.ej. 'tenant-dev')
  * ``payload.site_id``    ≡ ``sites.code``       (p.ej. 'site-dev')
  * ``payload.gateway_id`` ≡ ``gateways.serial``  (= iot_thing, 'gw-dev-0001')
  * ``Feature1s.station``  ≡ ``sensors.serial``   ('R4F74', 'SIMNNN')
Los UUIDs que se escriben en la DB salen SIEMPRE del ctx (registro), jamás
del payload. Mismatch ⇒ REJECT (→ DLQ) + fila en audit_log.

Idempotencia (regla de oro 3, SQS at-least-once): PKs naturales +
ON CONFLICT; incidents es el único UPSERT (escalada de severidad solo
hacia arriba, nunca degrada — G3).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

import psycopg
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb

from takab_api.audit import audit
from takab_api.contracts.meta import Meta
from takab_api.settings import RANK, SEVERITY_RANK, TIER_SEVERITY

# --------------------------------------------------------------------------
# Resultado tipado y contexto de gateway (los construye/consume registry.py)
# --------------------------------------------------------------------------


class Outcome(StrEnum):
    OK = "ok"  # procesado (o duplicado inocuo) — borrar de la cola
    REJECT = "reject"  # dato malo permanente — a DLQ con razón
    RETRY = "retry"  # transitorio (p.ej. ack antes que su incidente) — reintentar


@dataclass(frozen=True)
class HandlerResult:
    outcome: Outcome
    reason: str = ""

    @property
    def is_ok(self) -> bool:
        return self.outcome is Outcome.OK


OK = HandlerResult(Outcome.OK)


def reject(reason: str) -> HandlerResult:
    return HandlerResult(Outcome.REJECT, reason)


def retry(reason: str) -> HandlerResult:
    return HandlerResult(Outcome.RETRY, reason)


@dataclass(frozen=True)
class SensorRef:
    """Sensor publicable del gateway, con SU sitio (≠ sitio del gateway)."""

    sensor_id: uuid.UUID
    site_id: uuid.UUID
    site_code: str


@dataclass(frozen=True)
class GatewayCtx:
    """Identidad resuelta en registro a partir de ``meta_principal``.

    ``site_id``/``site_code`` son el sitio PROPIO del gateway (gateways.site_id);
    un gateway sim atiende varios sitios vía sus sensores, así que la atribución
    de datos usa ``sensors``/``served_sites``, nunca solo el sitio del gateway.
    """

    gateway_id: uuid.UUID
    gateway_serial: str
    iot_thing: str
    tenant_id: uuid.UUID
    tenant_code: str
    site_id: uuid.UUID
    site_code: str
    sensors: dict[str, SensorRef]  # serial de sensor (estación) → ref con su sitio

    @property
    def served_sites(self) -> dict[str, uuid.UUID]:
        """code → site_id de todos los sitios que atiende el gateway."""
        sites = {self.site_code: self.site_id}
        for ref in self.sensors.values():
            sites[ref.site_code] = ref.site_id
        return sites


# --------------------------------------------------------------------------
# Cross-check de identidad
# --------------------------------------------------------------------------


def check_identity(payload: dict, ctx: GatewayCtx, kind: str) -> str | None:
    """None si el payload es coherente con el registro; si no, la razón.

    Solo se comparan las claves que el contrato de ``kind`` trae (LocalEvent
    lleva tenant/site; HealthSnapshot lleva gateway; Feature1s lleva station;
    ActuatorAck y status no llevan identidad propia).
    """
    if "tenant_id" in payload and payload["tenant_id"] != ctx.tenant_code:
        return f"tenant mismatch: payload={payload['tenant_id']!r} registro={ctx.tenant_code!r}"
    # El sitio del payload debe ser UNO de los que atiende el gateway (vía sensores);
    # exigir el sitio propio del gateway rechazaría 4 de cada 5 sitios sim.
    if "site_id" in payload and payload["site_id"] not in ctx.served_sites:
        return (
            f"site mismatch: payload={payload['site_id']!r} no atendido por {ctx.gateway_serial!r}"
        )
    if "gateway_id" in payload and payload["gateway_id"] != ctx.gateway_serial:
        return (
            f"gateway mismatch: payload={payload['gateway_id']!r} registro={ctx.gateway_serial!r}"
        )
    if kind == "feature_1s" and payload.get("station") not in ctx.sensors:
        return f"station desconocida para el gateway: {payload.get('station')!r}"
    return None


def _audit_reject(
    conn: psycopg.Connection, ctx: GatewayCtx, meta: Meta, kind: str, reason: str
) -> None:
    """Deja evidencia del rechazo de identidad (no se auditan los OK — regla 10)."""
    audit(
        conn,
        tenant_id=str(ctx.tenant_id),
        actor="system:ingest",
        verb="ingest_reject",
        obj=f"{kind}@{meta.topic or '?'}",
        meta={"reason": reason, "principal": meta.principal},
    )


def _identity_reject(
    conn: psycopg.Connection, payload: dict, meta: Meta, ctx: GatewayCtx, kind: str
) -> HandlerResult | None:
    mismatch = check_identity(payload, ctx, kind)
    if mismatch is None:
        return None
    _audit_reject(conn, ctx, meta, kind, mismatch)
    return reject(mismatch)


def _dt(value: str | None) -> datetime | None:
    """ISO-8601 del JSON → datetime aware; None si el campo no vino."""
    return None if value is None else datetime.fromisoformat(value)


def _fallback_ts(meta: Meta) -> datetime:
    return meta.ts_iot or datetime.now(UTC)


# --------------------------------------------------------------------------
# feature_1s → waveform_features_1s
# --------------------------------------------------------------------------

_FEATURE_SQL = """
INSERT INTO waveform_features_1s
  (ts, tenant_id, site_id, sensor_id, channel, pga_g, pgv_cms, rms, stalta, clipping)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (ts, sensor_id, channel) DO NOTHING
"""


def handle_feature_1s(
    conn: psycopg.Connection, payload: dict, meta: Meta, ctx: GatewayCtx
) -> HandlerResult:
    """Feature1s → waveform_features_1s (unidades ya alineadas: g y cm/s).

    Sin columna destino: health_score. Sin fuente edge: energy (queda NULL).
    """
    if (rej := _identity_reject(conn, payload, meta, ctx, "feature_1s")) is not None:
        return rej
    try:
        ts = _dt(payload["window_start"])
    except ValueError as exc:
        return reject(f"feature_1s: window_start inválido ({exc})")
    # Atribución al sitio del SENSOR (sensors.site_id), no al del gateway:
    # los gateways sim atienden 5 sitios (dev_fleet.sql).
    sensor = ctx.sensors[payload["station"]]
    conn.execute(
        _FEATURE_SQL,
        (
            ts,
            ctx.tenant_id,
            sensor.site_id,
            sensor.sensor_id,
            payload["channel"],
            payload["pga"],
            payload["pgv"],
            payload["rms"],
            payload["sta_lta"],
            payload.get("clipping", False),
        ),
    )
    return OK


# --------------------------------------------------------------------------
# local_event → incidents (UPSERT que solo escala)
# --------------------------------------------------------------------------

# Órdenes totales para la escalada, derivados de settings (fuente única).
_SEV_ORDER = [s for s, _ in sorted(SEVERITY_RANK.items(), key=lambda kv: kv[1])]
_TIER_ORDER = [t for t, _ in sorted(RANK.items(), key=lambda kv: kv[1])]

# El tier vive en summary (incidents no tiene columna tier); la escalada compara
# severity y desempata por tier (evacuate_or_hold→manual_only actualiza summary
# aunque ambos sean 'critical'). El guard de tenant impide que una colisión de
# event_uuid entre tenants toque el incidente ajeno. Nunca degrada (G3).
_EVENT_SQL = """
INSERT INTO incidents
  (event_uuid, tenant_id, site_id, opened_at, severity, state, trigger, summary)
VALUES (%(event_uuid)s, %(tenant_id)s, %(site_id)s, %(opened_at)s,
        %(severity)s, 'open', %(trigger)s, %(summary)s)
ON CONFLICT (event_uuid) DO UPDATE SET
  severity = EXCLUDED.severity,
  trigger  = EXCLUDED.trigger,
  summary  = incidents.summary || EXCLUDED.summary
WHERE incidents.tenant_id = EXCLUDED.tenant_id
  AND (
    array_position(%(sev_order)s::text[], EXCLUDED.severity)
      > array_position(%(sev_order)s::text[], incidents.severity)
    OR (
      EXCLUDED.severity = incidents.severity
      AND COALESCE(array_position(%(tier_order)s::text[], EXCLUDED.summary->>'tier'), 0)
        > COALESCE(array_position(%(tier_order)s::text[], incidents.summary->>'tier'), 0)
    )
  )
"""


def handle_local_event(
    conn: psycopg.Connection, payload: dict, meta: Meta, ctx: GatewayCtx
) -> HandlerResult:
    """LocalEvent → incidents, idempotente por event_uuid (hex del edge)."""
    if (rej := _identity_reject(conn, payload, meta, ctx, "local_event")) is not None:
        return rej
    try:
        event_uuid = uuid.UUID(payload["event_id"])
    except (KeyError, ValueError, TypeError):
        return reject(f"local_event: event_id inválido o ausente: {payload.get('event_id')!r}")
    try:
        opened_at = _dt(payload.get("created_at")) or _fallback_ts(meta)
    except ValueError as exc:
        return reject(f"local_event: created_at inválido ({exc})")
    tier = payload["tier"]
    conn.execute(
        _EVENT_SQL,
        {
            "event_uuid": event_uuid,
            "tenant_id": ctx.tenant_id,
            # El incidente se atribuye al sitio del EVENTO (ya validado contra
            # los sitios atendidos por el gateway), no al sitio del gateway.
            "site_id": ctx.served_sites[payload["site_id"]],
            "opened_at": opened_at,
            "severity": TIER_SEVERITY[tier],
            "trigger": payload["source"],  # AlertSource ≡ CHECK de incidents.trigger
            "summary": Jsonb({"tier": tier, "source": payload["source"]}),
            "sev_order": _SEV_ORDER,
            "tier_order": _TIER_ORDER,
        },
    )
    return OK


# --------------------------------------------------------------------------
# health_snapshot → device_health
# --------------------------------------------------------------------------

_HEALTH_SQL = """
INSERT INTO device_health
  (ts, tenant_id, gateway_id, reason, seedlink_lag_s, ntp_offset_ms, mqtt_rtt_ms,
   cpu_temp_c, power_status, battery_pct, cert_days_remaining)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (ts, gateway_id) DO NOTHING
"""


def handle_health_snapshot(
    conn: psycopg.Connection, payload: dict, meta: Meta, ctx: GatewayCtx
) -> HandlerResult:
    """HealthSnapshot → device_health con conversión de unidades.

    Mapeos: captured_at→ts, ntp_offset_s×1000→ntp_offset_ms, ups_status→
    power_status, temperature_c→cpu_temp_c, transition_reason→reason
    ('heartbeat' literal ⇒ heartbeat; cualquier otra razón ⇒ transition —
    default del contrato: 'heartbeat'). Desde T-1.40 el contrato es honesto:
    ntp/battery/cert/mqtt_rtt llegan ``None`` cuando la fuente no existe y se
    persisten como NULL — la flota pinta S/D, no un invento. Sin columna
    destino: packet_loss_pct, relays. Sin fuente edge: battery_min_left.
    """
    if (rej := _identity_reject(conn, payload, meta, ctx, "health_snapshot")) is not None:
        return rej
    try:
        ts = _dt(payload.get("captured_at")) or _fallback_ts(meta)
    except ValueError as exc:
        return reject(f"health_snapshot: captured_at inválido ({exc})")
    ntp_s = payload.get("ntp_offset_s")
    is_hb = payload.get("transition_reason", "heartbeat") == "heartbeat"
    reason = "heartbeat" if is_hb else "transition"
    conn.execute(
        _HEALTH_SQL,
        (
            ts,
            ctx.tenant_id,
            ctx.gateway_id,
            reason,
            payload.get("seedlink_lag_s"),
            None if ntp_s is None else ntp_s * 1000.0,
            payload.get("mqtt_rtt_ms"),
            payload.get("temperature_c"),
            payload.get("ups_status"),
            payload.get("battery_pct"),
            payload.get("cert_days_remaining"),
        ),
    )
    return OK


# --------------------------------------------------------------------------
# actuator_ack → incident_actions
# --------------------------------------------------------------------------

# (channel, action) → incident_actions.kind. El DDL no tiene CHECK sobre kind;
# la convención sigue sus ejemplos ('siren_on', 'gas_closed') y la semántica
# fail-safe del contrato: activar la protección = gas CERRADO, puerta LIBERADA,
# ascensor LLAMADO a planta baja.
ACK_KIND: dict[tuple[str, str], str] = {
    ("siren", "activate"): "siren_on",
    ("siren", "deactivate"): "siren_off",
    ("strobe", "activate"): "strobe_on",
    ("strobe", "deactivate"): "strobe_off",
    ("gas_valve", "activate"): "gas_closed",
    ("gas_valve", "deactivate"): "gas_open",
    ("elevator", "activate"): "elevator_recalled",
    ("elevator", "deactivate"): "elevator_released",
    ("door_retainer", "activate"): "door_released",
    ("door_retainer", "deactivate"): "door_retained",
}

# ON CONFLICT sin arbitro explícito: el único índice único aplicable es
# uq_incident_actions_ack (migración 0002) sobre (incident_id, kind, actor, ts).
_ACK_SQL = """
INSERT INTO incident_actions (incident_id, tenant_id, ts, kind, actor, payload)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING
"""


def handle_actuator_ack(
    conn: psycopg.Connection, payload: dict, meta: Meta, ctx: GatewayCtx
) -> HandlerResult:
    """ActuatorAck → incident_actions, resolviendo el incidente por event_uuid.

    SQS standard no ordena: si el incidente del ack aún no llegó ⇒ RETRY
    (el mensaje vuelve a la cola, no a DLQ).
    """
    if (rej := _identity_reject(conn, payload, meta, ctx, "actuator_ack")) is not None:
        return rej
    try:
        event_uuid = uuid.UUID(payload["event_id"])
    except (KeyError, ValueError, TypeError):
        return reject(f"actuator_ack: event_id inválido: {payload.get('event_id')!r}")
    kind = ACK_KIND.get((payload["channel"], payload["action"]))
    if kind is None:
        return reject(
            f"actuator_ack: (channel, action) sin mapeo: "
            f"({payload['channel']!r}, {payload['action']!r})"
        )
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT incident_id, tenant_id FROM incidents WHERE event_uuid = %s",
            (event_uuid,),
        )
        row = cur.fetchone()
    if row is None:
        return retry(f"actuator_ack: incidente {event_uuid} aún no ingerido")
    incident_id, incident_tenant = row
    if incident_tenant != ctx.tenant_id:
        mismatch = f"ack apunta a incidente de otro tenant (event_uuid={event_uuid})"
        _audit_reject(conn, ctx, meta, "actuator_ack", mismatch)
        return reject(mismatch)
    try:
        ts = _dt(payload.get("executed_at")) or _fallback_ts(meta)
    except ValueError as exc:
        return reject(f"actuator_ack: executed_at inválido ({exc})")
    conn.execute(
        _ACK_SQL,
        (
            incident_id,
            ctx.tenant_id,
            ts,
            kind,
            f"edge:{ctx.gateway_serial}",
            Jsonb(
                {
                    "channel": payload["channel"],
                    "action": payload["action"],
                    "success": payload["success"],
                    "latency_s": payload["latency_s"],
                    "detail": payload.get("detail", ""),
                }
            ),
        ),
    )
    return OK


# --------------------------------------------------------------------------
# command_ack → commands.status (T-1.23: ACK de ejecución obligatorio)
# --------------------------------------------------------------------------

_COMMAND_BY_NONCE_SQL = """
SELECT command_id, tenant_id, gateway_id, status FROM commands WHERE nonce = %s
"""

# Transición SOLO desde pending (re-entrega SQS = no-op idempotente).
_COMMAND_ACK_SQL = """
UPDATE commands
   SET status = %(status)s, ack = %(ack)s
 WHERE command_id = %(command_id)s AND status = 'pending'
"""


def handle_command_ack(
    conn: psycopg.Connection, payload: dict, meta: Meta, ctx: GatewayCtx
) -> HandlerResult:
    """CommandAck → transición de ``commands`` (pending→acked/rejected) por nonce.

    El ack DEBE venir del MISMO gateway al que se emitió el comando (identidad
    X.509 del principal, no falsificable); un nonce desconocido se rechaza con
    huella de auditoría. SQS standard reentrega: un comando ya no-pending es
    no-op (idempotente). El 'expired' lo pone el worker por TTL — aquí un ack
    tardío sobre expired NO revive el comando.
    """
    nonce = payload.get("nonce")
    if not isinstance(nonce, str) or not nonce:
        return reject("command_ack: sin nonce")
    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(_COMMAND_BY_NONCE_SQL, (nonce,))
        row = cur.fetchone()
    if row is None:
        reason = f"command_ack: nonce desconocido ({nonce[:16]}…)"
        _audit_reject(conn, ctx, meta, "command_ack", reason)
        return reject(reason)
    command_id, tenant_id, gateway_id, status = row
    if gateway_id != ctx.gateway_id or tenant_id != ctx.tenant_id:
        reason = f"command_ack: gateway/tenant no coincide (comando {command_id})"
        _audit_reject(conn, ctx, meta, "command_ack", reason)
        return reject(reason)
    if status != "pending":
        return OK  # re-entrega o ack tardío: no-op idempotente (nunca revive)
    new_status = "acked" if payload.get("success") else "rejected"
    conn.execute(
        _COMMAND_ACK_SQL,
        {
            "status": new_status,
            "command_id": command_id,
            "ack": Jsonb(
                {
                    "channel": payload["channel"],
                    "action": payload["action"],
                    "success": payload["success"],
                    "latency_s": payload.get("latency_s", 0.0),
                    "executed_at": payload.get("executed_at"),
                    "detail": payload.get("detail", ""),
                }
            ),
        },
    )
    audit(
        conn,
        tenant_id=str(tenant_id),
        actor=f"edge:{ctx.gateway_serial}",
        verb=f"command_{new_status}",
        obj=f"command:{command_id}",
    )
    return OK


# --------------------------------------------------------------------------
# status (LWT) → gateways.status + device_health(reason='transition')
# --------------------------------------------------------------------------

_STATUS_HEALTH_SQL = """
INSERT INTO device_health (ts, tenant_id, gateway_id, reason)
VALUES (%s, %s, %s, 'transition')
ON CONFLICT (ts, gateway_id) DO NOTHING
"""

# Guarda monotónica: SQS standard reordena y reentrega, así que un LWT viejo
# NUNCA debe pisar un estado más nuevo (regla de oro 7: dato congelado ≠ live).
# El último ts aplicado vive en gateways.metadata->>'status_ts'.
_STATUS_SQL = """
UPDATE gateways
   SET status = %(status)s,
       metadata = metadata || jsonb_build_object('status_ts', %(ts)s::timestamptz)
 WHERE gateway_id = %(gateway_id)s
   AND COALESCE((metadata->>'status_ts')::timestamptz, '-infinity') < %(ts)s
"""


def handle_status(
    conn: psycopg.Connection, payload: dict, meta: Meta, ctx: GatewayCtx
) -> HandlerResult:
    """LWT/beacon de presencia: 'online'/'offline' (dentro del CHECK del DDL).

    Un mensaje con ts ≤ al último aplicado no toca gateways.status (no-op
    idempotente); su fila histórica en device_health sí se conserva.
    """
    if (rej := _identity_reject(conn, payload, meta, ctx, "status")) is not None:
        return rej
    ts = _fallback_ts(meta)
    conn.execute(
        _STATUS_SQL,
        {"status": payload["status"], "gateway_id": ctx.gateway_id, "ts": ts},
    )
    conn.execute(_STATUS_HEALTH_SQL, (ts, ctx.tenant_id, ctx.gateway_id))
    return OK


# Despacho por clase de contrato (kind_for_topic → handler); lo usa consumer.py.
Handler = Callable[[psycopg.Connection, dict, Meta, GatewayCtx], HandlerResult]

HANDLERS: dict[str, Handler] = {
    "feature_1s": handle_feature_1s,
    "local_event": handle_local_event,
    "health_snapshot": handle_health_snapshot,
    "actuator_ack": handle_actuator_ack,
    "command_ack": handle_command_ack,
    "status": handle_status,
}
