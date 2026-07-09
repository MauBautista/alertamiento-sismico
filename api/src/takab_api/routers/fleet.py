"""Flota edge: estado derivado + estado del config firmado (T-1.22 · B1/G7, T-1.30 · C4).

- ``GET /fleet/gateways`` — inventario con ``OPERATIVO|DEGRADADO|SIN ENLACE``.
- ``GET /fleet/gateways/{id}/config-state`` — qué config firmada tiene realmente el
  gabinete, para que la Matriz Multi-Tenant distinga PENDIENTE de SINCRONIZADO.
- ``POST/PUT/DELETE /fleet/gateways`` — administración del inventario (T-1.32).

Autz (RBAC §2 · columna Flota Edge): superficie web + rol con acceso a /fleet
(superadmin/support Total; tenant_admin/soc_operator/gov_operator Lectura). Tanto el
estado de flota (``schemas.fleet.derive_fleet_state``) como ``in_sync`` (mismo
predicado que ``commands/sync.py``) se derivan server-side: la UI solo pinta.

La escritura exige además la acción ``manage_fleet`` (superadmin + tenant_admin), y el
``tenant_id`` del gabinete se hereda del sitio padre: nunca viaja en el cuerpo.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import require_roles, require_web_surface
from takab_api.auth.matrix import FLEET, ROLE_ACTION_MATRIX, ROLE_ROUTE_MATRIX
from takab_api.queries import fleet as q
from takab_api.routers._common import (
    http_error,
    integrity_error,
    read_session,
    tenant_of_parent_site,
)
from takab_api.schemas.fleet import (
    DEGRADADO,
    GatewayConfigStateOut,
    GatewayCreate,
    GatewayOut,
    GatewayRowOut,
    GatewayUpdate,
    derive_fleet_state,
    fleet_degrade_reasons,
    sig_fingerprint,
)
from takab_api.settings import Settings

# Roles con /fleet en RBAC §2 (vía matrix.py).
_FLEET_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if FLEET in routes)
)

_MANAGE_FLEET_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, a in ROLE_ACTION_MATRIX.items() if a["manage_fleet"])
)

_require_manage = require_roles(*_MANAGE_FLEET_ROLES)

router = APIRouter(
    dependencies=[Depends(require_web_surface), Depends(require_roles(*_FLEET_ROLES))]
)

_WRITE_FIELDS = ("site_id", "serial", "fw_version", "iot_thing", "has_wr1", "installed_at")


def _row_out(row) -> GatewayRowOut:
    return GatewayRowOut(**dict(row._mapping))


@router.get(
    "/fleet/gateways/{gateway_id}/config-state",
    response_model=GatewayConfigStateOut,
)
async def get_gateway_config_state(
    gateway_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> GatewayConfigStateOut:
    """Config firmada que el gabinete tiene REALMENTE. 404 si RLS no lo deja verlo.

    Nunca publicado ⇒ 200 con ``version=null, in_sync=false``: la consola pinta
    PENDIENTE, no un error.
    """
    row = await q.get_config_state(conn, str(gateway_id))
    if row is None:
        raise http_error(404, "gateway no encontrado")
    m = dict(row._mapping)
    return GatewayConfigStateOut(
        gateway_id=m["gateway_id"],
        version=m["version"],
        published_at=m["published_at"],
        sig_fingerprint=sig_fingerprint(m["sig"]),
        in_sync=m["in_sync"],
        has_edge_config=m["has_edge_config"],
        is_syncable=m["is_syncable"],
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
        # Las razones solo aplican a DEGRADADO: en SIN ENLACE el problema es el
        # silencio, no una métrica; en OPERATIVO son vacías por definición.
        reasons = (
            fleet_degrade_reasons(
                power_status=m["power_status"],
                battery_pct=m["battery_pct"],
                cert_days_remaining=m["cert_days_remaining"],
                mqtt_rtt_ms=m["mqtt_rtt_ms"],
                seedlink_lag_s=m["seedlink_lag_s"],
                ntp_offset_ms=m["ntp_offset_ms"],
                battery_min_pct=s.fleet_battery_min_pct,
                cert_min_days=s.fleet_cert_min_days,
                mqtt_rtt_max_ms=s.fleet_mqtt_rtt_max_ms,
                seedlink_lag_max_s=s.fleet_seedlink_lag_max_s,
                ntp_offset_max_ms=s.fleet_ntp_offset_max_ms,
            )
            if state == DEGRADADO
            else []
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
                row_version=m["row_version"],
                derived_state=state,
                degrade_reasons=reasons,
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


# --- Administración del inventario (T-1.32) ----------------------------------


@router.post("/fleet/gateways", response_model=GatewayRowOut, status_code=201)
async def create_gateway(
    body: GatewayCreate,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> GatewayRowOut:
    """Da de alta un gabinete en ``provisioned``. Cero llamadas a AWS.

    ``serial`` e ``iot_thing`` son únicos GLOBALES (no por tenant): un serial repetido
    devuelve 409. Sin ``iot_thing`` el gabinete no es sincronizable y la consola lo
    muestra como PENDIENTE DE APROVISIONAR — que es la verdad hasta que Terraform emita
    su certificado.
    """
    tenant_id = await tenant_of_parent_site(conn, claims, body.site_id)
    values = {f: getattr(body, f) for f in _WRITE_FIELDS}
    try:
        row = await q.insert_gateway(conn, tenant_id=tenant_id, values=values)
    except IntegrityError as exc:
        raise integrity_error(exc) from exc

    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="gateway_create",
        obj=f"gateway:{row.gateway_id}",
        meta={"serial": body.serial, "site_id": str(body.site_id)},
    )
    return _row_out(row)


@router.put("/fleet/gateways/{gateway_id}", response_model=GatewayRowOut)
async def update_gateway(
    gateway_id: UUID,
    body: GatewayUpdate,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> GatewayRowOut:
    """Reemplaza el gabinete. ``base_row_version`` viejo ⇒ 409.

    El sitio destino debe ser del mismo tenant que el gabinete: mudarlo a un sitio ajeno
    haría que su telemetría (y sus actuadores) quedaran bajo otro tenant.
    """
    current = await q.get_gateway_row(conn, gateway_id)
    if current is None:
        raise http_error(404, "gateway no encontrado")

    site_tenant = await tenant_of_parent_site(conn, claims, body.site_id)
    if site_tenant != str(current.tenant_id):
        raise http_error(403, "el sitio destino pertenece a otro tenant")

    values = {f: getattr(body, f) for f in _WRITE_FIELDS}
    try:
        row = await q.update_gateway(
            conn, gateway_id=gateway_id, values=values, base_row_version=body.base_row_version
        )
    except IntegrityError as exc:
        raise integrity_error(exc) from exc
    if row is None:
        raise http_error(409, "el gateway cambió en el servidor; recarga y reintenta")

    await audit_async(
        conn,
        tenant_id=row.tenant_id,
        actor=f"user:{claims.sub}",
        verb="gateway_update",
        obj=f"gateway:{gateway_id}",
        meta={"serial": body.serial, "site_id": str(body.site_id)},
    )
    return _row_out(row)


@router.delete("/fleet/gateways/{gateway_id}", response_model=GatewayRowOut)
async def retire_gateway(
    gateway_id: UUID,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> GatewayRowOut:
    """Retiro lógico (idempotente). Un gabinete retirado deja de ser sincronizable."""
    if await q.get_gateway_row(conn, gateway_id) is None:
        raise http_error(404, "gateway no encontrado")
    row = await q.set_gateway_status(conn, gateway_id, "retired")
    if row is None:
        raise http_error(403, "sin permiso para retirar este gateway")

    await audit_async(
        conn,
        tenant_id=row.tenant_id,
        actor=f"user:{claims.sub}",
        verb="gateway_retire",
        obj=f"gateway:{gateway_id}",
        meta={"serial": row.serial},
    )
    return _row_out(row)


@router.post("/fleet/gateways/{gateway_id}/restore", response_model=GatewayRowOut)
async def restore_gateway(
    gateway_id: UUID,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> GatewayRowOut:
    """Deshace un retiro: vuelve a ``provisioned``, NO a ``online``.

    El estado vivo lo demuestra el siguiente heartbeat; la API no puede afirmarlo.
    """
    if await q.get_gateway_row(conn, gateway_id) is None:
        raise http_error(404, "gateway no encontrado")
    row = await q.set_gateway_status(conn, gateway_id, "provisioned")
    if row is None:
        raise http_error(403, "sin permiso para restaurar este gateway")

    await audit_async(
        conn,
        tenant_id=row.tenant_id,
        actor=f"user:{claims.sub}",
        verb="gateway_restore",
        obj=f"gateway:{gateway_id}",
        meta={"serial": row.serial},
    )
    return _row_out(row)
