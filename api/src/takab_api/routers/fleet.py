"""GET /fleet/gateways — flota edge con estado derivado (T-1.22 · B1/G7).

Autz (RBAC §2 · columna Flota Edge): superficie web + rol con acceso a /fleet
(superadmin/support Total; tenant_admin/soc_operator/gov_operator Lectura). El
estado ``OPERATIVO|DEGRADADO|SIN ENLACE`` lo deriva el servidor (verdad única en
``schemas.fleet.derive_fleet_state``); la UI solo pinta.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.deps import require_roles, require_web_surface
from takab_api.auth.matrix import FLEET, ROLE_ROUTE_MATRIX
from takab_api.queries import fleet as q
from takab_api.routers._common import read_session
from takab_api.schemas.fleet import GatewayOut, derive_fleet_state
from takab_api.settings import Settings

# Roles con /fleet en RBAC §2 (vía matrix.py).
_FLEET_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if FLEET in routes)
)

router = APIRouter(
    dependencies=[Depends(require_web_surface), Depends(require_roles(*_FLEET_ROLES))]
)


@router.get("/fleet/gateways", response_model=list[GatewayOut])
async def list_gateways(
    conn: AsyncConnection = Depends(read_session),
) -> list[GatewayOut]:
    """Gateways del tenant con su estado derivado del último ``device_health``."""
    s = Settings()
    rows = await q.list_gateways_with_health(conn)
    out: list[GatewayOut] = []
    for r in rows:
        m = dict(r._mapping)
        state = derive_fleet_state(
            age_s=m["age_s"],
            power_status=m["power_status"],
            battery_pct=m["battery_pct"],
            cert_days_remaining=m["cert_days_remaining"],
            mqtt_rtt_ms=m["mqtt_rtt_ms"],
            seedlink_lag_s=m["seedlink_lag_s"],
            ntp_offset_ms=m["ntp_offset_ms"],
            sin_enlace_s=s.sin_enlace_min * 60.0,
            battery_min_pct=s.fleet_battery_min_pct,
            cert_min_days=s.fleet_cert_min_days,
            mqtt_rtt_max_ms=s.fleet_mqtt_rtt_max_ms,
            seedlink_lag_max_s=s.fleet_seedlink_lag_max_s,
            ntp_offset_max_ms=s.fleet_ntp_offset_max_ms,
        )
        out.append(
            GatewayOut(
                gateway_id=m["gateway_id"],
                site_id=m["site_id"],
                serial=m["serial"],
                fw_version=m["fw_version"],
                iot_thing=m["iot_thing"],
                status=m["status"],
                has_wr1=m["has_wr1"],
                installed_at=m["installed_at"],
                derived_state=state,
                last_heartbeat_ts=m["health_ts"],
                power_status=m["power_status"],
                battery_pct=m["battery_pct"],
                cert_days_remaining=m["cert_days_remaining"],
                mqtt_rtt_ms=m["mqtt_rtt_ms"],
                seedlink_lag_s=m["seedlink_lag_s"],
                ntp_offset_ms=m["ntp_offset_ms"],
            )
        )
    return out
