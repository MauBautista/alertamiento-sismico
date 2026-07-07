"""SQL del command service (T-1.23 · B9). Corre bajo RLS con la sesión del
usuario (``takab_app`` + GUCs): la visibilidad del sitio y la escritura de la
fila del comando las decide la policy (``commands_write``, sin gov_operator).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import TextClause, text

_COLS = (
    "command_id, tenant_id, site_id, gateway_id, issued_by, channel, action, "
    "event_id, nonce, issued_at, expires_at, status, ack, error"
)

# Sitio visible para el tenant (RLS) → 404 sin fuga si no.
SELECT_SITE = text("SELECT site_id, tenant_id FROM sites WHERE site_id = :site_id")

# Gateway comandable del sitio: con thing IoT y no retirado; online preferente.
SELECT_GATEWAY = text(
    "SELECT gateway_id, iot_thing FROM gateways "
    "WHERE site_id = :site_id AND status <> 'retired' AND iot_thing IS NOT NULL "
    "ORDER BY (status = 'online') DESC, gateway_id LIMIT 1"
)

# Lazy-expire de los pendientes vencidos del sitio (ack obligatorio por TTL).
EXPIRE_SITE = text(
    "UPDATE commands SET status = 'expired', error = 'sin ack dentro del TTL' "
    "WHERE site_id = :site_id AND status = 'pending' AND expires_at < :now"
)

# Rate-limit por usuario+sitio y por sitio (RBAC §4.3.3), ventana deslizante.
COUNT_USER_SITE = text(
    "SELECT count(*) FROM commands "
    "WHERE issued_by = CAST(:user_id AS uuid) AND site_id = :site_id "
    "AND issued_at > :since"
)
COUNT_SITE = text("SELECT count(*) FROM commands WHERE site_id = :site_id AND issued_at > :since")


def insert_command(
    *,
    tenant_id: str,
    site_id: str,
    gateway_id: str,
    issued_by: str,
    channel: str,
    action: str,
    event_id: str | None,
    nonce: str,
    issued_at: Any,
    expires_at: Any,
) -> tuple[TextClause, dict[str, Any]]:
    sql = (
        "INSERT INTO commands (tenant_id, site_id, gateway_id, issued_by, channel, "
        "action, event_id, nonce, issued_at, expires_at) "
        "VALUES (CAST(:tenant AS uuid), CAST(:site AS uuid), CAST(:gateway AS uuid), "
        "CAST(:user_id AS uuid), :channel, :action, :event_id, :nonce, :issued_at, "
        f":expires_at) RETURNING {_COLS}"
    )
    return text(sql), {
        "tenant": tenant_id,
        "site": site_id,
        "gateway": gateway_id,
        "user_id": issued_by,
        "channel": channel,
        "action": action,
        "event_id": event_id,
        "nonce": nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


LIST_COMMANDS = text(
    f"SELECT {_COLS} FROM commands WHERE site_id = :site_id "
    "ORDER BY issued_at DESC, command_id LIMIT :limit"
)
