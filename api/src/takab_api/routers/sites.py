"""Catálogo de sitios: lectura (T-1.22 · B1) y administración (T-1.32).

Autz de lectura (RBAC §2): cualquier rol con superficie web y acceso a alguna vista SOC
ve el catálogo (todos tienen al menos MONITOREO). Los roles móvil-only quedan fuera
(conjunto de rutas vacío). RLS filtra las filas por tenant.

Autz de escritura: acción ``manage_fleet`` (superadmin + tenant_admin). El ``tenant_id``
de un sitio nuevo lo resuelve ``resolve_write_tenant`` contra los claims — jamás se toma
del cuerpo tal cual, porque la política ``sites_admin`` tiene ``WITH CHECK
(app_is_takab_internal())`` sin filtro de tenant y la DB no detendría a un interno.

Un sitio no se borra: se retira (``status='retired'``). Sus incidentes, dictámenes y
evidencia lo referencian y no se podan nunca (regla de oro 11).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_console_scope, require_roles, require_web_surface
from takab_api.auth.matrix import ROLE_ACTION_MATRIX, ROLE_ROUTE_MATRIX
from takab_api.auth.scope import ConsoleScope
from takab_api.queries import sites as q
from takab_api.retire_code import check_confirmation, require_retire_code
from takab_api.routers._common import (
    http_error,
    integrity_error,
    read_session,
    resolve_write_tenant,
)
from takab_api.schemas.retire import SiteRetire
from takab_api.schemas.sites import (
    SiteCreate,
    SiteDetailOut,
    SiteOut,
    SiteUpdate,
    ZoneOut,
)

# Roles con al menos una vista web (espejo de RBAC §2 vía matrix.py).
_WEB_ROLES: tuple[str, ...] = tuple(sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if routes))

# Roles que administran la flota (RBAC §2 + [DECISION 2026-07-09] vía matrix.py).
MANAGE_FLEET_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, a in ROLE_ACTION_MATRIX.items() if a["manage_fleet"])
)

_require_manage = require_roles(*MANAGE_FLEET_ROLES)

router = APIRouter(dependencies=[Depends(require_web_surface), Depends(require_roles(*_WEB_ROLES))])

# Campos que viajan tal cual del cuerpo al SQL (el resto se resuelve en el router).
_WRITE_FIELDS = (
    "code",
    "name",
    "lat",
    "lon",
    "timezone",
    "criticality",
    "address",
    "building_type",
)


def _out(row) -> SiteOut:
    return SiteOut(**dict(row._mapping))


@router.get("/sites", response_model=list[SiteOut])
async def list_sites(
    include_retired: bool = False,
    scope: ConsoleScope = Depends(get_console_scope),
    conn: AsyncConnection = Depends(read_session),
) -> list[SiteOut]:
    """Sitios del tenant (superadmin/support ven todos vía RLS). Activos por defecto.

    [T-2.45] Acotado además por el ``site_scope`` del claim.
    """
    rows = await q.list_sites(conn, include_retired=include_retired, scope=scope)
    return [_out(r) for r in rows]


@router.get("/sites/{site_id}", response_model=SiteDetailOut)
async def get_site(
    site_id: UUID,
    scope: ConsoleScope = Depends(get_console_scope),
    conn: AsyncConnection = Depends(read_session),
) -> SiteDetailOut:
    """Detalle de un sitio con sus zonas. 404 si no existe, no es visible o está
    fuera del alcance del portador (T-2.45: 404, nunca 403)."""
    row = await q.get_site(conn, site_id)
    if row is None or not scope.allows(str(site_id)):
        raise http_error(404, "sitio no encontrado")
    zones = await q.list_zones_for_site(conn, site_id)
    return SiteDetailOut(
        **dict(row._mapping),
        zones=[ZoneOut(**dict(z._mapping)) for z in zones],
    )


@router.post("/sites", response_model=SiteOut, status_code=201)
async def create_site(
    body: SiteCreate,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> SiteOut:
    """Da de alta un sitio con su ubicación. ``code`` es único DENTRO del tenant ⇒ 409."""
    tenant_id = await resolve_write_tenant(conn, claims, body.tenant_id)
    values = {f: getattr(body, f) for f in _WRITE_FIELDS}
    try:
        row = await q.insert_site(conn, tenant_id=tenant_id, values=values)
    except IntegrityError as exc:
        raise integrity_error(exc) from exc

    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="site_create",
        obj=f"site:{row.site_id}",
        meta={"code": body.code, "lat": body.lat, "lon": body.lon},
    )
    return _out(row)


@router.put("/sites/{site_id}", response_model=SiteOut)
async def update_site(
    site_id: UUID,
    body: SiteUpdate,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> SiteOut:
    """Reemplaza el sitio. ``base_row_version`` viejo ⇒ 409 (lost update).

    Mover un sitio cambia la distancia entre estaciones, y con ella la ventana de
    asociación del quórum (``|Δt| ≤ dist/v_P + margen``). Un guardado ciego que
    revirtiera en silencio la posición de una estación degradaría la correlación
    sin que nadie se enterara: por eso la carrera se resuelve con un 409, no con el
    último que escriba.
    """
    current = await q.get_site(conn, site_id)
    if current is None:
        raise http_error(404, "sitio no encontrado")

    values = {f: getattr(body, f) for f in _WRITE_FIELDS} | {"status": body.status}
    try:
        row = await q.update_site(
            conn, site_id=site_id, values=values, base_row_version=body.base_row_version
        )
    except IntegrityError as exc:
        raise integrity_error(exc) from exc
    if row is None:
        raise http_error(409, "el sitio cambió en el servidor; recarga y reintenta")

    await audit_async(
        conn,
        tenant_id=row.tenant_id,
        actor=f"user:{claims.sub}",
        verb="site_update",
        obj=f"site:{site_id}",
        meta={"code": body.code, "lat": body.lat, "lon": body.lon, "status": body.status},
    )
    return _out(row)


@router.post("/sites/{site_id}/retire", response_model=SiteOut)
async def retire_site(
    site_id: UUID,
    body: SiteRetire,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> SiteOut:
    """Retiro lógico (idempotente). Nunca borra: la evidencia del sitio es inmutable.

    [T-2.35] Retira TAMBIÉN sus gabinetes, en la misma transacción. Antes no lo hacía y
    el hardware quedaba huérfano: invisible en el catálogo de sitios, pero todavía
    candidato de config firmada y de comandos de actuación (ambos predicados miran
    ``gateways.status``, no ``sites.status``). Restaurar el sitio NO los devuelve:
    volver a encender hardware es un acto explícito, no un efecto colateral.

    [T-2.36] Doble fricción: teclear el ``code`` del sitio (no el ``name``, que no es
    único) y el código de retiro del cliente. Retirar un sitio arrastra su hardware, así
    que la fricción es la misma que la del gabinete, no menor.
    """
    current = await q.get_site(conn, site_id)
    if current is None:
        raise http_error(404, "sitio no encontrado")

    check_confirmation(typed=body.confirm_code, expected=current.code, label="código")
    await require_retire_code(
        conn,
        claims,
        tenant_id=str(current.tenant_id),
        code=body.retire_code,
        obj=f"site:{site_id}",
    )

    row = await q.retire_site(conn, site_id)
    if row is None:  # visible por RLS de lectura, no escribible: no debería ocurrir
        raise http_error(403, "sin permiso para retirar este sitio")

    retired_gateways = await q.retire_site_gateways(conn, site_id)

    await audit_async(
        conn,
        tenant_id=row.tenant_id,
        actor=f"user:{claims.sub}",
        verb="site_retire",
        obj=f"site:{site_id}",
        meta={"code": row.code, "gateways_retired": len(retired_gateways)},
    )
    # Una fila por gabinete: la bitácora debe decir QUÉ hardware se apagó, no solo
    # cuántos. Los retirados de una pasada previa no reaparecen (RETURNING vacío).
    for gw in retired_gateways:
        await audit_async(
            conn,
            tenant_id=row.tenant_id,
            actor=f"user:{claims.sub}",
            verb="gateway_retire",
            obj=f"gateway:{gw.gateway_id}",
            meta={"serial": gw.serial, "reason": "retiro del sitio", "site_code": row.code},
        )
    return _out(row)
