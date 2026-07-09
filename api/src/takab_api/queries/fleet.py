"""SQL de la flota edge (T-1.22 · B1/G7).

Gateways del tenant + LATERAL al último ``device_health`` de cada gateway. La
edad del heartbeat (``age_s``) se calcula con ``now()`` de la transacción para no
depender del reloj de la app. La derivación del estado vive en
``schemas.fleet.derive_fleet_state`` (verdad única). Ambas tablas tienen RLS por
tenant → un tenant nunca ve la flota de otro.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

_LIST = text(
    """
    SELECT g.gateway_id, g.site_id, g.serial, g.fw_version, g.iot_thing,
           g.status, g.has_wr1, g.installed_at,
           h.ts AS health_ts, h.power_status,
           h.battery_pct::float8       AS battery_pct,
           h.cert_days_remaining,
           h.mqtt_rtt_ms::float8       AS mqtt_rtt_ms,
           h.seedlink_lag_s::float8    AS seedlink_lag_s,
           h.ntp_offset_ms::float8     AS ntp_offset_ms,
           EXTRACT(EPOCH FROM (now() - h.ts))::float8 AS age_s
    FROM gateways g
    LEFT JOIN LATERAL (
        SELECT dh.ts, dh.power_status, dh.battery_pct, dh.cert_days_remaining,
               dh.mqtt_rtt_ms, dh.seedlink_lag_s, dh.ntp_offset_ms
        FROM device_health dh
        WHERE dh.gateway_id = g.gateway_id
        ORDER BY dh.ts DESC
        LIMIT 1
    ) h ON true
    ORDER BY g.serial, g.gateway_id
    """
)


async def list_gateways_with_health(conn: AsyncConnection) -> Sequence[Row]:
    """Gateways del tenant + su último heartbeat (RLS por tenant en ambas tablas)."""
    return (await conn.execute(_LIST)).all()


# Estado del sync firmado de UN gateway. El rule_set se resuelve EXACTAMENTE como
# en ``commands/sync.py`` (scope site preferente sobre tenant, versión más alta,
# LIMIT 1 ANTES de exigir el bloque 'edge'), para que ``in_sync`` sea la negación
# del predicado de publicación del worker y no una segunda opinión.
_CONFIG_STATE = text(
    """
    -- COALESCE obligatorio: sin rule_set activo el LEFT JOIN deja rs.config NULL, y
    -- `NULL::jsonb ? 'edge'` es NULL (jsonb_exists es STRICT), no false. Ese NULL
    -- reventaría los bool no-opcionales de GatewayConfigStateOut con un 500 en un
    -- endpoint que promete 200 + PENDIENTE.
    SELECT g.gateway_id,
           st.version,
           st.published_at,
           st.sig,
           COALESCE(rs.config ? 'edge', false)        AS has_edge_config,
           (g.status <> 'retired' AND g.iot_thing IS NOT NULL) AS is_syncable,
           COALESCE(st.gateway_id IS NOT NULL
            AND rs.config ? 'edge'
            AND st.payload IS NOT DISTINCT FROM rs.config->'edge', false) AS in_sync
    FROM gateways g
    LEFT JOIN LATERAL (
        SELECT r.config
        FROM rule_sets r
        WHERE r.is_active
          AND ( (r.scope_type = 'site'   AND r.scope_id = g.site_id)
             OR (r.scope_type = 'tenant' AND r.scope_id = g.tenant_id) )
        ORDER BY (r.scope_type = 'site') DESC, r.version DESC
        LIMIT 1
    ) rs ON true
    LEFT JOIN gateway_config_state st ON st.gateway_id = g.gateway_id
    WHERE g.gateway_id = :gateway_id
    """
)


async def get_config_state(conn: AsyncConnection, gateway_id: str) -> Row | None:
    """Estado del config firmado del gateway. ``None`` si RLS no lo deja verlo."""
    return (await conn.execute(_CONFIG_STATE, {"gateway_id": gateway_id})).first()
