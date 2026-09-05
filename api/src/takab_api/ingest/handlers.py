"""Handlers de ingesta SQS→Timescale (T-1.17).

Interfaz: cada handler recibe ``(conn, payload, meta, ctx)`` — payload ya
validado contra ``shared/schemas/`` y SIN claves ``meta_*`` — y devuelve un
``HandlerResult``. No hace commit/rollback: eso lo decide el consumer (que
también construye el ``GatewayCtx`` desde el registro vía ``meta_principal``).

Regla de identidad (cross-check payload↔registro, db/schema.sql §1–§2 y
db/seeds/prod_fleet.sql + sim_fleet.sql): los IDs que viajan en el payload del edge son los
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


def _insert_feature(conn: psycopg.Connection, feature: dict, ctx: GatewayCtx) -> str | None:
    """UN Feature1s → fila idempotente; devuelve la razón del rechazo o None.

    Compartido por ``handle_feature_1s`` (1 Hz) y ``handle_feature_batch``
    (T-1.56): mismo mapeo, misma PK ``(ts, sensor_id, channel)``.
    """
    station = feature.get("station")
    sensor = ctx.sensors.get(station)
    if sensor is None:
        return f"station desconocida para el gateway: {station!r}"
    try:
        ts = _dt(feature["window_start"])
    except ValueError as exc:
        return f"window_start inválido ({exc})"
    # Atribución al sitio del SENSOR (sensors.site_id), no al del gateway:
    # los gateways sim atienden 5 sitios (sim_fleet.sql).
    conn.execute(
        _FEATURE_SQL,
        (
            ts,
            ctx.tenant_id,
            sensor.site_id,
            sensor.sensor_id,
            feature["channel"],
            feature["pga"],
            feature["pgv"],
            feature["rms"],
            feature["sta_lta"],
            feature.get("clipping", False),
        ),
    )
    return None


def handle_feature_1s(
    conn: psycopg.Connection, payload: dict, meta: Meta, ctx: GatewayCtx
) -> HandlerResult:
    """Feature1s → waveform_features_1s (unidades ya alineadas: g y cm/s).

    Sin columna destino: health_score. Sin fuente edge: energy (queda NULL).
    """
    if (rej := _identity_reject(conn, payload, meta, ctx, "feature_1s")) is not None:
        return rej
    if (reason := _insert_feature(conn, payload, ctx)) is not None:
        return reject(f"feature_1s: {reason}")
    return OK


def handle_feature_batch(
    conn: psycopg.Connection, payload: dict, meta: Meta, ctx: GatewayCtx
) -> HandlerResult:
    """FeatureBatch (T-1.56) → N filas idempotentes en la MISMA transacción.

    Lote parcialmente inválido: las features válidas SE INSERTAN y se devuelve
    REJECT con la razón — el consumer commitea lo escrito (``handler_ran=True``)
    y manda el original a la DLQ (evidencia forense completa, cero pérdida de
    las buenas; el reproceso es idempotente por PK).
    """
    if (rej := _identity_reject(conn, payload, meta, ctx, "feature_batch")) is not None:
        return rej
    features = payload["features"]
    bad: list[str] = []
    for i, feature in enumerate(features):
        if (reason := _insert_feature(conn, feature, ctx)) is not None:
            bad.append(f"[{i}] {reason}")
    if bad:
        detail = "; ".join(bad[:5])
        reason = f"feature_batch: {len(bad)}/{len(features)} inválidas: {detail}"
        _audit_reject(conn, ctx, meta, "feature_batch", reason)
        return reject(reason)
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
   cpu_temp_c, power_status, battery_pct, cert_days_remaining, battery_min_left,
   relays_state, packet_loss_pct)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (ts, gateway_id) DO NOTHING
"""

# --------------------------------------------------------------------------
# [T-2.70.a·B1] El censo de relés: tres hechos que eran uno
# --------------------------------------------------------------------------

#: El gabinete publicó su censo de relés.
RELAYS_REPORTED = "reported"
#: Preguntó al dueño de los pines y no hay filas: el módulo no corre, o este
#: gabinete no tiene relés cableados. Es un HECHO.
RELAYS_STOPPED = "stopped"
#: **No pudo preguntar.** Nadie contesta como dueño de los pines. Con
#: `gpio_owner=gpio` y `takab-gpio` caído esto significa un edificio sin sirena,
#: sin cierre de gas, sin retorno de ascensores y sin retenedores — mientras
#: `takab-edge` late perfectamente y `gateway_offline` no dispara.
RELAYS_UNREADABLE = "unreadable"


def _relays_state(payload: dict) -> str | None:
    """Qué dice el latido sobre los relés. ``None`` = el gabinete no opina.

    Misma disciplina ausente/null/basura que ``_fw_field``, y por la misma razón:
    la nube NO confía en el dispositivo, y las tres situaciones piden respuestas
    distintas.

    · **La clave no viene** — no opina. Se persiste NULL y la consola pinta S/D.
    · **``null``** — contrato 1.10.0 diciendo *«no pude preguntar al dueño de los
      pines»*. Es el hecho grave y el único que degrada el estado de flota.
    · **``[]``** — *«pregunté y no hay filas»*. Neutro. Es TAMBIÉN lo que manda un
      gabinete ≤1.9.0 cuando su lectura falla (ese firmware no sabe emitir el
      ``null``), así que degradar sobre este valor sería degradar sobre un dato
      ambiguo y teñiría de ámbar a la flota vieja sin saber si le pasa algo.
    · **lista con filas** — el censo medido.
    · **cualquier otra cosa** — basura. NO opina: un payload manipulado no puede
      escribir en la columna un rótulo que la consola sabe pintar.

    La distinción sólo existe porque ``edge/takab_edge/cloud`` publica con
    ``model_dump(mode="json")`` **sin** ``exclude_none``: el ``null`` explícito
    llega al cable. Hay un test del lado del edge que lo vigila.
    """
    if "relays" not in payload:
        return None
    crudo = payload["relays"]
    if crudo is None:
        return RELAYS_UNREADABLE
    # `bool` es subclase de `int` pero no de `list`; aun así se excluye cualquier
    # cosa que no sea lista para que el rótulo no dependa de una coerción.
    if not isinstance(crudo, list):
        return None
    return RELAYS_REPORTED if crudo else RELAYS_STOPPED


#: `IS DISTINCT FROM` ⇒ el UPDATE no escribe fila cuando la version no cambio, que es
#: el 99.99% de los heartbeats (llega 1/min por gabinete). Registro por TRANSICION, no
#: por intervalo (regla de oro 10).
_FW_VERSION_SQL = """
UPDATE gateways SET fw_version = %s
WHERE gateway_id = %s AND fw_version IS DISTINCT FROM %s
"""

#: [T-2.70] Idem para el codigo que el proceso EJECUTA. Columna aparte porque son
#: dos hechos distintos: fundirlos hacia indetectable el despliegue a medias.
_FW_RUNNING_SQL = """
UPDATE gateways SET fw_running = %s
WHERE gateway_id = %s AND fw_running IS DISTINCT FROM %s
"""

#: Un SHA corto o una etiqueta. La ingesta NO confia en el dispositivo: un payload
#: manipulado no puede escribir un parrafo en la ficha de la flota.
_FW_VERSION_MAX_LEN = 64


def _fw_field(payload: dict, key: str = "fw_version") -> tuple[bool, str | None]:
    """(¿el gabinete OPINA sobre este campo de versión?, valor).

    [T-2.70] Sirve a los DOS campos de versión del latido —``fw_version`` (qué
    código hay en el disco) y ``fw_running`` (cuál ejecuta el proceso)— porque la
    disciplina ausente/null/basura tiene que ser LA MISMA en ambos. Si difiriera,
    el campo más laxo decidiría el criterio de éxito de una actualización.

    [T-2.69] Antes esto devolvía un solo ``None`` y con él colapsaba DOS hechos
    incompatibles:

    · **La clave NO viene** — contrato pre-1.6.0. El gabinete no sabe hablar de
      versiones; no opina, y lo conocido se conserva.
    · **La clave viene con ``null``** — contrato 1.6.0 diciendo *«late y NO SABE
      qué versión corre»* (``FW_VERSION`` borrado por un ``rsync --delete`` a
      medias, un reaprovisionamiento, un archivo ilegible). **Eso SÍ es un hecho
      nuevo**: la ficha pasa a S/D. Conservar el valor viejo lo congelaba para
      siempre y la consola lo pintaba como actual — el defecto que T-2.69
      prohíbe (regla de oro 7: un dato de hace tres semanas no es "lo que corre").

    La distinción es posible porque ``edge/takab_edge/cloud`` publica con
    ``model_dump(mode="json")`` **sin** ``exclude_none``, así que el ``null``
    explícito llega al cable. Si alguien añadiera ``exclude_none`` "por limpieza",
    esta separación moriría EN SILENCIO — por eso hay un test del lado del edge
    que afirma que la clave viaja aunque valga null.

    Basura (tipo raro, cadena vacía, 200 caracteres) NO opina: un payload
    manipulado no puede escribir un párrafo en la ficha **ni borrar** la versión
    buena — eso convertiría el vandalismo en un botón de S/D remoto.
    """
    if key not in payload:
        return (False, None)
    crudo = payload[key]
    if crudo is None:
        return (True, None)
    if not isinstance(crudo, str):
        return (False, None)
    version = crudo.strip()
    if not version or len(version) > _FW_VERSION_MAX_LEN:
        return (False, None)
    return (True, version)


def handle_health_snapshot(
    conn: psycopg.Connection, payload: dict, meta: Meta, ctx: GatewayCtx
) -> HandlerResult:
    """HealthSnapshot → device_health con conversión de unidades.

    Mapeos: captured_at→ts, ntp_offset_s×1000→ntp_offset_ms, ups_status→
    power_status, temperature_c→cpu_temp_c, transition_reason→reason
    ('heartbeat' literal ⇒ heartbeat; cualquier otra razón ⇒ transition —
    default del contrato: 'heartbeat'). Desde T-1.40 el contrato es honesto:
    ntp/battery/cert/mqtt_rtt llegan ``None`` cuando la fuente no existe y se
    persisten como NULL — la flota pinta S/D, no un invento. Desde
    T-5.24 `packet_loss_pct` SÍ aterriza: era la señal que se degrada antes de
    que falten datos y el SOC no podía verla de ningún sitio. Sin columna
    destino queda `disk_used_pct` (T-1.53, consumo local del panel LAN). De
    ``relays`` no se persiste el censo canal a canal (sin consumidor en la nube)
    sino **si el gabinete pudo obtenerlo**, en ``relays_state``
    (T-2.70.a·B1) — ver ``_relays_state`` para los tres hechos que ese campo
    separa y por qué. `ups_runtime_s` (T-2.22, segundos) aterriza en
    `battery_min_left` (minutos): la columna existía desde el schema inicial y
    era SIEMPRE NULL porque el edge no mandaba la fuente.
    """
    if (rej := _identity_reject(conn, payload, meta, ctx, "health_snapshot")) is not None:
        return rej
    try:
        ts = _dt(payload.get("captured_at")) or _fallback_ts(meta)
    except ValueError as exc:
        return reject(f"health_snapshot: captured_at inválido ({exc})")
    ntp_s = payload.get("ntp_offset_s")
    # T-2.22: contrato ADITIVO — payloads 1.6.0 sin la clave ⇒ NULL, como siempre.
    # bool es subclase de int: un `true` manipulado NO se convierte en "0 min".
    runtime_s = payload.get("ups_runtime_s")
    if isinstance(runtime_s, bool) or not isinstance(runtime_s, (int, float)):
        battery_min_left = None
    else:
        battery_min_left = int(round(runtime_s / 60.0))
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
            battery_min_left,
            # [T-2.70.a·B1] Y si el gabinete pudo mirarse los relés siquiera. Va
            # en la fila FECHADA, no en `gateways`: importa cuándo se quedó sin
            # dueño de pines y cuándo volvió. Como la fila es idempotente por
            # `(ts, gateway_id)`, un reenvío no pisa lo escrito y este valor no
            # puede borrar un censo bueno anterior — sólo añade su instante.
            _relays_state(payload),
            # [T-5.24] La pérdida de paquetes del enlace sensor→Pi. El gabinete
            # la publicaba desde siempre y aquí se tiraba: el SOC no podía verla
            # de ningún sitio y había que ir al inmueble. `None` sigue siendo
            # «el gabinete no opina» ⇒ S/D, nunca un cero — que aquí diría
            # «enlace perfecto», que es la mentira cara.
            payload.get("packet_loss_pct"),
        ),
    )
    # `gateways.fw_version` (T-1.74): la version la DECLARA el gabinete. Antes se
    # llenaba a mano y se quedaba obsoleta en silencio en el siguiente despliegue.
    # [T-2.69] Se escribe SOLO cuando el gabinete opina — y entonces se escribe lo
    # que diga, incluido el NULL de «no se que version corro». `IS DISTINCT FROM`
    # sigue haciendo que esto no toque la fila en el 99.99% de los latidos, y
    # tambien cubre la transicion a NULL (regla de oro 10: por transicion, no por
    # intervalo). Ver `_fw_version` para por que ausencia != null.
    opina, version = _fw_field(payload, "fw_version")
    if opina:
        conn.execute(_FW_VERSION_SQL, (version, ctx.gateway_id, version))
    # [T-2.70] Y el codigo que el proceso EJECUTA, en su propia columna. Cuando
    # difiere del de arriba hay codigo escrito que nadie corre: un despliegue a
    # medias. Ese es el unico criterio honesto de "la actualizacion se aplico" —
    # el ack del comando solo dice que la orden llego (llega ANTES de reiniciar,
    # y tras el reinicio el nonce ya no existe para re-ackear).
    opina, corriendo = _fw_field(payload, "fw_running")
    if opina:
        conn.execute(_FW_RUNNING_SQL, (corriendo, ctx.gateway_id, corriendo))
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
                    # [T-2.116] El estado RECALCULADO del relé, junto al verbo.
                    # `kind` (siren_on/siren_off) es la ORDEN que se ejecutó, y
                    # la spec §2.1 pide justo lo contrario para el checklist
                    # BMS: «lo mostrado es el estado del relé recalculado por el
                    # arbitraje de demandas, no la última orden enviada». Sin
                    # esto, un `siren_off` de una orden arbitrada (alerta
                    # vigente) pintaba la sirena apagada mientras sonaba.
                    # `None` = el gabinete no lo declara (firmware viejo, BACnet).
                    "channel_state": payload.get("channel_state"),
                }
            ),
        ),
    )
    return OK


# --------------------------------------------------------------------------
# actuation_record → actuation_records (T-2.86.a: el hueco `RO-4.e`)
# --------------------------------------------------------------------------

# `ON CONFLICT DO NOTHING` sobre la PK que pone EL GABINETE. No es defensa contra
# la re-entrega de SQS (que también): el edge NO borra su copia local al subir
# —el perito la lee meses después—, avanza una marca de agua, y si esa marca se
# pierde re-sube filas ya ingeridas. Regla de oro 3, y aquí la duplicación no
# sería un renglón de más: sería una bitácora que un perito lee como dos
# actuaciones donde hubo una.
_ACTUATION_RECORD_SQL = """
INSERT INTO actuation_records (
  record_id, tenant_id, site_id, gateway_id, seq, occurred_at,
  cause, actor, channel, action, success, detail, event_id, online
) VALUES (
  %(record_id)s, %(tenant_id)s, %(site_id)s, %(gateway_id)s, %(seq)s, %(occurred_at)s,
  %(cause)s, %(actor)s, %(channel)s, %(action)s, %(success)s, %(detail)s,
  %(event_id)s, %(online)s
)
ON CONFLICT (record_id) DO NOTHING
"""


def handle_actuation_record(
    conn: psycopg.Connection, payload: dict, meta: Meta, ctx: GatewayCtx
) -> HandlerResult:
    """ActuationRecord → actuation_records. La constancia del gabinete, en la nube.

    Las tres identidades se toman del REGISTRO (`ctx`) y no del payload, aunque el
    payload las traiga: lo que trae sirve para `check_identity` —que rechaza y
    audita el cruce de tenant— y ahí se queda. Escribir la identidad que declara
    el mensaje sería dejar que un gabinete comprometido plantara evidencia en el
    tenant de otro cliente, en la tabla que menos se puede permitir.
    """
    if (rej := _identity_reject(conn, payload, meta, ctx, "actuation_record")) is not None:
        return rej
    try:
        record_id = uuid.UUID(payload["record_id"])
    except (KeyError, ValueError, TypeError):
        return reject(f"actuation_record: record_id inválido: {payload.get('record_id')!r}")
    try:
        occurred_at = _dt(payload["at"])
    except (KeyError, ValueError, TypeError) as exc:
        return reject(f"actuation_record: 'at' inválido ({exc})")
    conn.execute(
        _ACTUATION_RECORD_SQL,
        {
            "record_id": record_id,
            "tenant_id": ctx.tenant_id,
            "site_id": ctx.site_id,
            "gateway_id": ctx.gateway_id,
            "seq": payload["seq"],
            "occurred_at": occurred_at,
            "cause": payload["cause"],
            "actor": payload["actor"],
            "channel": payload["channel"],
            "action": payload["action"],
            "success": payload["success"],
            "detail": payload.get("detail", ""),
            "event_id": payload.get("event_id", ""),
            # `online` NO lleva default: `None` significa «el gabinete no pudo
            # saber si tenía enlace», y colapsarlo a `False` inventaría justo el
            # dato que esta tabla existe para no inventar.
            "online": payload.get("online"),
        },
    )
    return OK


# --------------------------------------------------------------------------
# command_ack → commands.status (T-1.23: ACK de ejecución obligatorio)
# --------------------------------------------------------------------------

_COMMAND_BY_NONCE_SQL = """
SELECT command_id, tenant_id, gateway_id, status FROM commands WHERE nonce = %s
"""

# Transición SOLO desde pending (re-entrega SQS = no-op idempotente).
# [T-5.14] `acked_at` lo pone la BASE, con el mismo reloj que `issued_at`. El
# `executed_at` que viaja dentro del `ack` lo manda el gabinete y su reloj es
# justo lo que el sistema vigila (`ntp_offset_s`): restarle `issued_at` mezclaría
# dos relojes y el «tardó 4 min 12 s» de un post-simulacro no significaría nada.
# Los dos se conservan — el del gabinete dice cuándo ACTUÓ, éste cuándo se supo.
_COMMAND_ACK_SQL = """
UPDATE commands
   SET status = %(status)s, ack = %(ack)s, acked_at = now()
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
                    # [T-1.59] Resultados del self_test (por relé + salud del
                    # cache); None en acks de activate/deactivate.
                    "results": payload.get("results"),
                    # [T-2.116 · spec móvil §2.2] EL ESTADO DEL CANAL TRAS EL
                    # ARBITRAJE, que es lo que la app necesita para dejar de
                    # inferirlo de la fase: «el resultado real llega en el
                    # command_ack con el estado recalculado del relé».
                    #
                    # `status='acked'` describe LA ORDEN («la demanda manual se
                    # retiró»), no el relé: un `siren/deactivate` con la alerta
                    # vigente se ejecuta con éxito y la sirena sigue sonando.
                    # Colapsar las dos cosas era leer «silenciada» un edificio
                    # que seguía sonando (regla de oro 7).
                    #
                    # `None` = el gabinete NO lo declara (firmware ≤ schema
                    # 1.10.0, o ack de rechazo sin ejecución). Jamás «en reposo».
                    "channel_state": payload.get("channel_state"),
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
#
# [T-2.65 · B1] `status <> 'retired'`: el retiro es un acto ADMINISTRATIVO de la
# consola y esto es un mensaje del PROPIO aparato — dejarlo escribir aquí era una
# inversión de autoridad, y deshacía T-2.65 sola. La cadena medida contra Postgres
# el 2026-08-06: retiro → sobre firmado con cloud_admin_state='retired' y cartel
# DADO DE BAJA en el panel → el gabinete (que sigue vivo A PROPÓSITO, opción (A))
# flapea su sesión MQTT → beacon retenido `{"status":"online"}` → esta UPDATE
# borraba el retiro → trigger 0027 → sobre FIRMADO v+1 con
# cloud_admin_state='active' que APAGABA el cartel. Sin que nadie restaurara nada.
# El agujero es PREEXISTENTE (T-1.17): el mismo camino borraba el retiro que
# T-2.60.a usa para detectar fantasmas y el que T-2.35 usa para dejar de mandar
# comandos a hardware fuera de catálogo. Sobrevivió sin que se notara porque el
# beacon solo se publica al CONECTAR (edge/cloud::_publish_online), no en el
# latido de 60 s (`takab/health` no toca esta columna): el 2026-08-04 `gw-dev-0001`
# se quedó en 'retired' horas por no flapear, no por estar protegido.
#
# El beacon informa de que el gabinete está VIVO, no de que esté dado de alta:
# la vida se sigue registrando abajo (device_health + bitácora).
_STATUS_SQL = """
UPDATE gateways
   SET status = %(status)s,
       metadata = metadata || jsonb_build_object('status_ts', %(ts)s::timestamptz)
 WHERE gateway_id = %(gateway_id)s
   AND status <> 'retired'
   AND COALESCE((metadata->>'status_ts')::timestamptz, '-infinity') < %(ts)s
"""

# Consume el ts del mensaje suprimido SIN mover `status`: hace la huella
# idempotente (SQS reentrega; la reentrega ya no pasa la guarda monotónica) y
# distingue "lo bloqueó el retiro" de "llegó viejo", que son cosas distintas.
# `RETURNING` ⇒ una fila solo cuando de verdad era un mensaje nuevo de un retirado.
_STATUS_RETIRED_SQL = """
UPDATE gateways
   SET metadata = metadata || jsonb_build_object('status_ts', %(ts)s::timestamptz)
 WHERE gateway_id = %(gateway_id)s
   AND status = 'retired'
   AND COALESCE((metadata->>'status_ts')::timestamptz, '-infinity') < %(ts)s
RETURNING 1
"""


def handle_status(
    conn: psycopg.Connection, payload: dict, meta: Meta, ctx: GatewayCtx
) -> HandlerResult:
    """LWT/beacon de presencia: 'online'/'offline' (dentro del CHECK del DDL).

    Un mensaje con ts ≤ al último aplicado no toca gateways.status (no-op
    idempotente); su fila histórica en device_health sí se conserva.

    [T-2.65 · B1] Un gabinete RETIRADO sigue retirado aunque reconecte, pero no se
    le calla: la fila de ``device_health`` (abajo, incondicional) es de donde salen
    "retirado + latiendo" de T-2.60.a y el contador de fantasmas de T-2.65. Encima
    de eso, cada RECONEXIÓN de un retirado deja constancia en la bitácora
    append-only — es la señal de "sigue vivo ahí fuera" y la evidencia de que un
    mensaje del aparato intentó revertir a la consola. Solo el beacon 'online' la
    escribe: el LWT 'offline' no dice nada sobre seguir vivo y duplicaría el
    volumen en cada flap (regla de oro 10: por transición, no por intervalo).
    """
    if (rej := _identity_reject(conn, payload, meta, ctx, "status")) is not None:
        return rej
    ts = _fallback_ts(meta)
    cur = conn.execute(
        _STATUS_SQL,
        {"status": payload["status"], "gateway_id": ctx.gateway_id, "ts": ts},
    )
    if cur.rowcount == 0 and payload["status"] == "online":
        params = {"gateway_id": ctx.gateway_id, "ts": ts}
        if conn.execute(_STATUS_RETIRED_SQL, params).fetchone() is not None:
            audit(
                conn,
                tenant_id=str(ctx.tenant_id),
                actor=f"edge:{ctx.gateway_serial}",
                verb="gateway_alive_while_retired",
                obj=f"gateway:{ctx.gateway_id}",
                meta={"ignored_status": payload["status"], "topic": meta.topic},
            )
    conn.execute(_STATUS_HEALTH_SQL, (ts, ctx.tenant_id, ctx.gateway_id))
    return OK


# Despacho por clase de contrato (kind_for_topic → handler); lo usa consumer.py.
Handler = Callable[[psycopg.Connection, dict, Meta, GatewayCtx], HandlerResult]

HANDLERS: dict[str, Handler] = {
    "feature_1s": handle_feature_1s,
    "feature_batch": handle_feature_batch,  # T-1.56: lote de tier normal
    "local_event": handle_local_event,
    "health_snapshot": handle_health_snapshot,
    "actuator_ack": handle_actuator_ack,
    "actuation_record": handle_actuation_record,  # T-2.86.a: hueco RO-4.e
    "command_ack": handle_command_ack,
    "status": handle_status,
}
