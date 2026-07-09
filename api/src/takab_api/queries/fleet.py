"""SQL de la flota edge (T-1.22 · B1/G7).

Gateways del tenant + LATERAL al último ``device_health`` de cada gateway. La
edad del heartbeat (``age_s``) se calcula con ``now()`` de la transacción para no
depender del reloj de la app. La derivación del estado vive en
``schemas.fleet.derive_fleet_state`` (verdad única). Ambas tablas tienen RLS por
tenant → un tenant nunca ve la flota de otro.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

_LIST = text(
    """
    SELECT g.gateway_id, g.site_id, g.serial, g.fw_version, g.iot_thing,
           g.status, g.has_wr1, g.installed_at, g.xmin::text AS row_version,
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


# --- Administración de gabinetes (T-1.32) ------------------------------------
# El ``tenant_id`` no es parámetro del cuerpo: lo hereda del sitio padre, que el
# router ya validó contra los claims. ``xmin::text`` es el testigo de concurrencia.

_ROW_COLS = (
    "gateway_id, tenant_id, site_id, serial, fw_version, iot_thing, "
    "status, has_wr1, installed_at, xmin::text AS row_version"
)

_GET_ROW = text(f"SELECT {_ROW_COLS} FROM gateways WHERE gateway_id = :id")

# Alta SIEMPRE en 'provisioned': el gabinete no está online hasta que su primer
# heartbeat lo demuestre. La API no crea certificados X.509 (eso es Terraform).
_INSERT = text(
    "INSERT INTO gateways (tenant_id, site_id, serial, fw_version, iot_thing, "
    "status, has_wr1, installed_at) "
    "VALUES (CAST(:tenant_id AS uuid), :site_id, :serial, :fw_version, :iot_thing, "
    "'provisioned', :has_wr1, :installed_at) "
    f"RETURNING {_ROW_COLS}"
)

_UPDATE = text(
    "UPDATE gateways SET site_id = :site_id, serial = :serial, fw_version = :fw_version, "
    "iot_thing = :iot_thing, has_wr1 = :has_wr1, installed_at = :installed_at "
    "WHERE gateway_id = :id "
    "  AND (CAST(:base_row_version AS text) IS NULL "
    "       OR xmin::text = CAST(:base_row_version AS text)) "
    f"RETURNING {_ROW_COLS}"
)

_SET_STATUS = text(
    f"UPDATE gateways SET status = :status WHERE gateway_id = :id RETURNING {_ROW_COLS}"
)


async def get_gateway_row(conn: AsyncConnection, gateway_id: UUID) -> Row | None:
    """Fila cruda del gateway, o ``None`` si RLS no lo deja verla."""
    return (await conn.execute(_GET_ROW, {"id": gateway_id})).first()


async def insert_gateway(conn: AsyncConnection, *, tenant_id: str, values: dict) -> Row:
    """Inserta el gabinete en 'provisioned'. ``serial``/``iot_thing`` son únicos GLOBALES."""
    return (await conn.execute(_INSERT, {**values, "tenant_id": tenant_id})).one()


async def update_gateway(
    conn: AsyncConnection, *, gateway_id: UUID, values: dict, base_row_version: str | None
) -> Row | None:
    """Reemplaza el gabinete. ``None`` = otro escritor ganó la carrera (⇒ 409)."""
    params = {**values, "id": gateway_id, "base_row_version": base_row_version}
    return (await conn.execute(_UPDATE, params)).first()


async def set_gateway_status(conn: AsyncConnection, gateway_id: UUID, status: str) -> Row | None:
    """Fija ``status`` (solo 'retired' o 'provisioned' desde la API). Idempotente."""
    return (await conn.execute(_SET_STATUS, {"id": gateway_id, "status": status})).first()
