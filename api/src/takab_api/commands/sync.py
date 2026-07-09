"""Config sync firmada nube→edge (T-1.23 · B9).

Publica a ``takab/cfg/<thing>`` el documento ``rule_sets.config.edge`` del
rule_set ACTIVO de cada gateway (scope site preferente sobre tenant), firmado
con versión MONÓTONA por gateway (``gateway_config_state``: el edge rechaza
toda versión ya vista — high_water de T-1.12). Idempotente: si el payload
publicado no cambió, no se republica ni sube versión.

SLA ≤60 s: el trigger de la migración 0006 emite NOTIFY ``takab_live``
(``t='rule_set'``) al activar/cambiar un rule_set y el worker despierta al
instante; el poll de respaldo (≤30 s) cubre un NOTIFY perdido.

[DECISION]: el payload es el documento EdgeSettings de ``config.edge``; un
documento parcial valida con los defaults del contrato del edge (T-1.12).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import psycopg

from takab_api.audit import audit
from takab_api.commands.keys import CommandKeyProvider
from takab_api.commands.publisher import CommandPublisher, PublishError
from takab_api.commands.signing import canonical_payload, sign_config
from takab_api.settings import Settings

logger = logging.getLogger("takab_api.commands")

# Advisory lock propio (≠ engine/dictamen/notify).
_SYNC_LOCK_KEY = 0x7A4B_1123

# Gateways comandables cuyo rule_set activo trae 'edge' y difiere del último
# estado publicado (o nunca se publicó). El rule_set se resuelve por gateway:
# scope site (el del gateway) preferente sobre tenant, versión más alta.
_CANDIDATES_SQL = """
SELECT g.gateway_id,
       g.tenant_id,
       g.iot_thing,
       rs.config->'edge' AS edge_config,
       st.version AS state_version,
       st.payload AS state_payload
FROM gateways g
JOIN LATERAL (
  SELECT r.config
  FROM rule_sets r
  WHERE r.is_active
    AND ( (r.scope_type = 'site'   AND r.scope_id = g.site_id)
       OR (r.scope_type = 'tenant' AND r.scope_id = g.tenant_id) )
  ORDER BY (r.scope_type = 'site') DESC, r.version DESC
  LIMIT 1
) rs ON rs.config ? 'edge'
LEFT JOIN gateway_config_state st ON st.gateway_id = g.gateway_id
WHERE g.status <> 'retired'
  AND g.iot_thing IS NOT NULL
  AND (st.gateway_id IS NULL OR st.payload IS DISTINCT FROM rs.config->'edge')
ORDER BY g.gateway_id
"""

_UPSERT_STATE_SQL = """
INSERT INTO gateway_config_state (gateway_id, tenant_id, version, payload, sig, published_at)
VALUES (%(gateway)s, %(tenant)s, %(version)s, %(payload)s::jsonb, %(sig)s, %(now)s)
ON CONFLICT (gateway_id) DO UPDATE
SET version = EXCLUDED.version,
    payload = EXCLUDED.payload,
    sig = EXCLUDED.sig,
    published_at = EXCLUDED.published_at
"""

_EXPIRE_COMMANDS_SQL = """
UPDATE commands SET status = 'expired', error = 'sin ack dentro del TTL'
WHERE status = 'pending' AND expires_at < %(now)s
"""


def run_config_sync_pass(
    conn: psycopg.Connection,
    settings: Settings,
    publisher: CommandPublisher,
    keys: CommandKeyProvider,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Publica la config firmada pendiente; expira comandos sin ack (TTL).

    Devuelve los ``gateway_id`` (str) publicados en esta pasada. Un COMMIT al
    final si hubo escrituras. Fail-closed POR GATEWAY (T-1.38): un candidato
    sin clave resoluble se salta SIN quemar versión y entra cuando su clave
    exista (provisión tardía / rotación) — jamás se firma con una compartida.
    """
    now = now or datetime.now(tz=UTC)
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SYNC_LOCK_KEY,))
    expired = conn.execute(_EXPIRE_COMMANDS_SQL, {"now": now}).rowcount

    published: list[str] = []
    for row in conn.execute(_CANDIDATES_SQL).fetchall():
        edge_config = row["edge_config"]
        if not isinstance(edge_config, dict):
            logger.warning("config sync: config.edge no es objeto (gw %s)", row["gateway_id"])
            continue
        key = keys.key_for(row["iot_thing"])
        if key is None:
            logger.warning(
                "config sync: sin clave HMAC para %s (fail-closed, skip)", row["iot_thing"]
            )
            continue
        version = (row["state_version"] or 0) + 1
        body = canonical_payload(edge_config)
        signature = sign_config(key, body, version)
        envelope = {
            "kind": "config_update",
            "version": version,
            "payload": edge_config,
            "sig": signature,
        }
        try:
            publisher.publish(f"takab/cfg/{row['iot_thing']}", json.dumps(envelope).encode())
        except PublishError as exc:
            # Sin upsert: el gateway sigue candidato y se reintenta en el
            # siguiente pass (la versión no se quema: aún no se publicó).
            logger.warning("config sync: publish falló (gw %s): %s", row["gateway_id"], exc)
            continue
        conn.execute(
            _UPSERT_STATE_SQL,
            {
                "gateway": row["gateway_id"],
                "tenant": row["tenant_id"],
                "version": version,
                "payload": json.dumps(edge_config),
                "sig": signature,
                "now": now,
            },
        )
        # Huella de compliance (T-1.24): qué config firmada salió a qué gateway.
        audit(
            conn,
            tenant_id=str(row["tenant_id"]),
            actor="system:config_sync",
            verb="config_published",
            obj=f"gateway:{row['gateway_id']}",
            meta={"version": version, "sig": signature[:16]},
        )
        published.append(str(row["gateway_id"]))
        logger.info("config sync: gw %s → v%d (%s)", row["gateway_id"], version, row["iot_thing"])

    _finish(conn, wrote=bool(published) or expired > 0)
    return published


def _finish(conn: psycopg.Connection, *, wrote: bool) -> None:
    if wrote:
        conn.commit()
    else:
        conn.rollback()
