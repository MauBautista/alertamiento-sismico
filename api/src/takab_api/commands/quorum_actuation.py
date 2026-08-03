"""Actuación por quórum confirmado (T-2.32 · política ratificada 2026-08-03).

La detección instrumental de UNA estación es solo aviso (edge T-2.32). Cuando la
correlación de red confirma quórum ≥3 (``seismic_events.source='local_quorum'``),
ESTA pasada emite comandos de actuación FIRMADOS (regla de oro 8: HMAC por
gateway + nonce + TTL + ack) a los gateways de los sitios miembro, a nivel
evacuación e intersectados con su equipamiento (T-2.31).

Idempotencia: la tabla ``commands`` ES el ledger — índice único parcial
``(gateway_id, event_id, channel) WHERE issued_by = QUORUM_ACTOR_UUID``
(migración 0023). Un publish fallido NO inserta su fila y reintenta en la
siguiente pasada (patrón ``commands/sync.py``); una fila ya insertada no se
re-publica. Fail-closed por gateway: sin clave HMAC resoluble no se firma nada.

Corre en el proceso del IncidentEngine, DESPUÉS de ``run_correlation`` y en su
PROPIA transacción: un fallo aquí jamás revierte el evento de red ni bloquea
nada local (el edge ya protegió por SASMEX si aplicaba).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import psycopg

from takab_api.audit import audit
from takab_api.commands.keys import CommandKeyProvider
from takab_api.commands.publisher import CommandPublisher, PublishError
from takab_api.commands.signing import canonical_payload, sign_command
from takab_api.settings import Settings

logger = logging.getLogger("takab_api.commands")

#: Actor sistema del quórum en ``commands.issued_by`` (uuid NOT NULL). Es una
#: constante documentada, NO un usuario: la consola lo pinta como «QUÓRUM RED».
#: Espejo en la migración 0023 y db/schema.sql — cambiar uno exige cambiar los tres.
QUORUM_ACTOR_UUID = "00000000-0000-4000-8000-00000000c092"

#: Quórum confirmado ⇒ nivel evacuación (TIER_ACTUATION[EVACUATE] del edge);
#: por gateway se intersecta con su equipamiento (T-2.31).
_EVACUATE_CHANNELS = ("siren", "strobe", "gas_valve", "elevator", "door_retainer")

# Advisory lock propio (≠ correlación/sync/dictamen/notify).
_QUORUM_ACT_LOCK_KEY = 0x7A4B_2232

# Eventos de quórum recientes × gateways comandables de los sitios miembro
# (membresía = incidents linkeados por run_correlation en la misma pasada).
_CANDIDATES_SQL = """
SELECT e.event_id,
       e.detected_at,
       g.gateway_id,
       g.tenant_id,
       g.site_id,
       g.iot_thing,
       g.equipment
FROM seismic_events e
JOIN incidents i ON i.event_id = e.event_id
JOIN gateways g ON g.site_id = i.site_id
WHERE e.source = 'local_quorum'
  AND e.detected_at >= %(since)s
  AND g.status <> 'retired'
  AND g.iot_thing IS NOT NULL
GROUP BY e.event_id, e.detected_at, g.gateway_id
ORDER BY e.detected_at, g.gateway_id
"""

_LEDGER_SQL = """
SELECT gateway_id::text AS gateway_id, event_id, channel
FROM commands
WHERE issued_by = %(actor)s AND issued_at >= %(since)s
"""

_INSERT_SQL = """
INSERT INTO commands (command_id, tenant_id, site_id, gateway_id, issued_by,
                      channel, action, event_id, nonce, issued_at, expires_at)
VALUES (%(command_id)s, %(tenant)s, %(site)s, %(gateway)s, %(actor)s,
        %(channel)s, 'activate', %(event)s, %(nonce)s, %(now)s, %(expires)s)
ON CONFLICT DO NOTHING
"""


def run_quorum_actuation_pass(
    conn: psycopg.Connection,
    settings: Settings,
    publisher: CommandPublisher,
    keys: CommandKeyProvider,
    *,
    now: datetime | None = None,
    lookback_s: float = 300.0,
) -> list[str]:
    """Emite los comandos de quórum pendientes. Devuelve los ``command_id`` emitidos.

    Un COMMIT al final si hubo escrituras. El ledger (``commands`` bajo el índice
    parcial de 0023) hace la pasada idempotente por (gateway, evento, canal).
    """
    now = now or datetime.now(tz=UTC)
    since = now - timedelta(seconds=lookback_s)
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_QUORUM_ACT_LOCK_KEY,))
    rows = conn.execute(_CANDIDATES_SQL, {"since": since}).fetchall()
    if not rows:
        conn.rollback()
        return []
    seen = {
        (r["gateway_id"], r["event_id"], r["channel"])
        for r in conn.execute(_LEDGER_SQL, {"actor": QUORUM_ACTOR_UUID, "since": since})
    }

    issued: list[str] = []
    for row in rows:
        key = keys.key_for(row["iot_thing"])
        if key is None:
            # Fail-closed POR GATEWAY (T-1.38): jamás se firma con una compartida.
            logger.warning(
                "quorum actuation: sin clave HMAC para %s (fail-closed, skip)", row["iot_thing"]
            )
            continue
        equipment = row["equipment"] if isinstance(row["equipment"], dict) else {}
        channels = [c for c in _EVACUATE_CHANNELS if equipment.get(c, True)]
        commanded: list[str] = []
        for channel in channels:
            triple = (str(row["gateway_id"]), row["event_id"], channel)
            if triple in seen:
                continue
            command_id = str(uuid.uuid4())
            nonce = uuid.uuid4().hex
            ts_iso = now.isoformat()
            # ``origin`` viaja DENTRO de la firma: el edge rotula la fuente
            # («QUÓRUM RED») sin que nadie pueda inyectarla sin la clave.
            payload = {
                "channel": channel,
                "action": "activate",
                "event_id": row["event_id"],
                "origin": "quorum",
            }
            signature = sign_command(key, canonical_payload(payload), nonce, ts_iso)
            envelope = {
                "kind": "command",
                "command_id": command_id,
                "nonce": nonce,
                "ts": ts_iso,
                "payload": payload,
                "sig": signature,
            }
            try:
                publisher.publish(f"takab/cmd/{row['iot_thing']}", json.dumps(envelope).encode())
            except PublishError as exc:
                # Sin insert: el (gateway, evento, canal) sigue candidato y se
                # reintenta en la siguiente pasada (la fila jamás nace fantasma).
                logger.warning(
                    "quorum actuation: publish falló (gw %s, %s): %s",
                    row["gateway_id"],
                    channel,
                    exc,
                )
                continue
            conn.execute(
                _INSERT_SQL,
                {
                    "command_id": command_id,
                    "tenant": row["tenant_id"],
                    "site": row["site_id"],
                    "gateway": row["gateway_id"],
                    "actor": QUORUM_ACTOR_UUID,
                    "channel": channel,
                    "event": row["event_id"],
                    "nonce": nonce,
                    "now": now,
                    "expires": now + timedelta(seconds=settings.command_ttl_s),
                },
            )
            seen.add(triple)
            commanded.append(channel)
            issued.append(command_id)
        if commanded:
            # Huella de compliance: qué burst firmado salió a qué gabinete.
            audit(
                conn,
                tenant_id=str(row["tenant_id"]),
                actor="system:quorum_engine",
                verb="quorum_actuation_commanded",
                obj=f"gateway:{row['gateway_id']}",
                meta={"event_id": row["event_id"], "channels": commanded},
            )
            logger.warning(
                "quorum actuation: gw %s ← %s (evento %s)",
                row["gateway_id"],
                ",".join(commanded),
                row["event_id"],
            )

    if issued:
        conn.commit()
    else:
        conn.rollback()
    return issued
