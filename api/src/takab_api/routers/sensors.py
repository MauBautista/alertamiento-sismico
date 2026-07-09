"""Catálogo de sensores: lectura (T-1.22 · B1) y administración (T-1.32).

Misma autz de lectura que el catálogo de sitios (rol web + RLS por tenant). Un
``site_id`` de otro tenant devuelve lista vacía (RLS tapa sus sensores), nunca datos
ajenos.

La escritura exige ``manage_fleet``. El tenant del sensor se hereda del sitio padre; el
gabinete y la zona que se le asignen deben pertenecer al MISMO tenant — las claves
foráneas de PostgreSQL no comparan ``tenant_id`` y sin esa comprobación un admin podría
colgar su sensor del gabinete de otro cliente.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import require_roles, require_web_surface
from takab_api.auth.matrix import ROLE_ACTION_MATRIX, ROLE_ROUTE_MATRIX
from takab_api.queries import sensors as q
from takab_api.routers._common import (
    http_error,
    integrity_error,
    read_session,
    require_same_tenant,
    tenant_of_parent_site,
)
from takab_api.schemas.sensors import SensorCreate, SensorOut, SensorUpdate

_WEB_ROLES: tuple[str, ...] = tuple(sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if routes))

_MANAGE_FLEET_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, a in ROLE_ACTION_MATRIX.items() if a["manage_fleet"])
)

_require_manage = require_roles(*_MANAGE_FLEET_ROLES)

router = APIRouter(dependencies=[Depends(require_web_surface), Depends(require_roles(*_WEB_ROLES))])

_WRITE_FIELDS = (
    "site_id",
    "gateway_id",
    "zone_id",
    "kind",
    "model",
    "serial",
    "channels",
    "sample_rate",
    "mount",
    "lat",
    "lon",
)


def _out(row) -> SensorOut:
    return SensorOut(**dict(row._mapping))


async def _check_refs(
    conn: AsyncConnection, claims: Claims, body: SensorCreate | SensorUpdate
) -> str:
    """Valida sitio/gabinete/zona contra un único tenant y lo devuelve."""
    tenant_id = await tenant_of_parent_site(conn, claims, body.site_id)
    if body.gateway_id is not None:
        await require_same_tenant(
            conn, table="gateways", row_id=body.gateway_id, tenant_id=tenant_id, label="gateway"
        )
    if body.zone_id is not None:
        await require_same_tenant(
            conn, table="zones", row_id=body.zone_id, tenant_id=tenant_id, label="zona"
        )
    return tenant_id


@router.get("/sensors", response_model=list[SensorOut])
async def list_sensors(
    site_id: UUID, conn: AsyncConnection = Depends(read_session)
) -> list[SensorOut]:
    """Sensores del sitio ``site_id`` (RLS por tenant)."""
    rows = await q.list_sensors(conn, site_id)
    return [_out(r) for r in rows]


@router.post("/sensors", response_model=SensorOut, status_code=201)
async def create_sensor(
    body: SensorCreate,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> SensorOut:
    """Da de alta un sensor. Sin ``lat``/``lon`` hereda la ubicación del sitio en el mapa."""
    tenant_id = await _check_refs(conn, claims, body)
    values = {f: getattr(body, f) for f in _WRITE_FIELDS}
    try:
        row = await q.insert_sensor(conn, tenant_id=tenant_id, values=values)
    except IntegrityError as exc:
        raise integrity_error(exc) from exc

    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="sensor_create",
        obj=f"sensor:{row.sensor_id}",
        meta={"kind": body.kind, "model": body.model, "site_id": str(body.site_id)},
    )
    return _out(row)


@router.put("/sensors/{sensor_id}", response_model=SensorOut)
async def update_sensor(
    sensor_id: UUID,
    body: SensorUpdate,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> SensorOut:
    """Reemplaza el sensor. ``base_row_version`` viejo ⇒ 409."""
    current_tenant = await q.get_sensor_tenant(conn, sensor_id)
    if current_tenant is None:
        raise http_error(404, "sensor no encontrado")

    ref_tenant = await _check_refs(conn, claims, body)
    if ref_tenant != current_tenant:
        raise http_error(403, "el sitio destino pertenece a otro tenant")

    values = {f: getattr(body, f) for f in _WRITE_FIELDS} | {"status": body.status}
    try:
        row = await q.update_sensor(
            conn, sensor_id=sensor_id, values=values, base_row_version=body.base_row_version
        )
    except IntegrityError as exc:
        raise integrity_error(exc) from exc
    if row is None:
        raise http_error(409, "el sensor cambió en el servidor; recarga y reintenta")

    await audit_async(
        conn,
        tenant_id=current_tenant,
        actor=f"user:{claims.sub}",
        verb="sensor_update",
        obj=f"sensor:{sensor_id}",
        meta={"kind": body.kind, "status": body.status, "site_id": str(body.site_id)},
    )
    return _out(row)


@router.delete("/sensors/{sensor_id}", response_model=SensorOut)
async def retire_sensor(
    sensor_id: UUID,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> SensorOut:
    """Retiro lógico (idempotente). Sus features históricas siguen siendo consultables."""
    tenant_id = await q.get_sensor_tenant(conn, sensor_id)
    if tenant_id is None:
        raise http_error(404, "sensor no encontrado")
    row = await q.retire_sensor(conn, sensor_id)
    if row is None:
        raise http_error(403, "sin permiso para retirar este sensor")

    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="sensor_retire",
        obj=f"sensor:{sensor_id}",
        meta={"model": row.model},
    )
    return _out(row)
