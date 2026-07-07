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
