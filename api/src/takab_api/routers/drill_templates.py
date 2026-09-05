"""T-5.13 · Plantillas de simulacro: se define una vez, se lanza en dos clics.

**Lo que faltaba.** El alta de un simulacro tenía cinco campos y ninguno era una
plantilla. Lo más cercano —ejecutar una agenda ya armada (`from_scheduled`,
T-2.48)— **la consume**: la fila queda con `stop_reason='executed'` y no se puede
volver a usar. Para el macrosimulacro de septiembre había que teclear los sitios,
la duración y la nota **a mano, cada vez**, en el caso de uso más visible que
tiene el producto.

**Sin rol nuevo.** El CRUD entero va con `drill_start`, el mismo permiso que ya
autoriza a disparar un simulacro. Un permiso nuevo habría movido la matriz RBAC y
sus dos espejos sin ganar nada: quien puede lanzar el simulacro puede definir
cómo se lanza.

**Se archiva, no se borra.** El `DELETE` marca `archived_at`. Un borrado de
verdad dejaría huérfana la procedencia de cada simulacro que salió de la
plantilla, y esos registros son evidencia de cumplimiento. Desde fuera se
comporta como un borrado —desaparece de la lista y su nombre vuelve a estar
libre, porque el índice único es parcial sobre las vivas—, que es lo que pide el
CRUD de la ficha.

**El estado de los sitios se evalúa AL LEER, nunca se congela.** Es la misma
decisión que `DrillSiteOut.commandable` (T-2.48) y por la misma razón: una
plantilla se define semanas antes y el inventario se mueve debajo. Y los tres
motivos van **separados** —dado de baja, sin gabinete, ya no visible— porque
significan cosas distintas y colapsarlos en «no disponible» dejaría al operador
sin saber a quién llamar.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_roles
from takab_api.auth.matrix import roles_with_action
from takab_api.routers._common import http_error
from takab_api.schemas.drills import (
    MOTIVO_SITIO,
    SITIO_NO_VISIBLE,
    SITIO_RETIRADO,
    SITIO_SIN_GABINETE,
    SITIO_USABLE,
    DrillTemplateIn,
    DrillTemplateList,
    DrillTemplateOut,
    TemplateSiteOut,
)

#: El mismo permiso que dispara un simulacro (criterio 1 de la ficha).
TEMPLATE_ROLES: tuple[str, ...] = roles_with_action("drill_start")

_require_drill = require_roles(*TEMPLATE_ROLES)

router = APIRouter()

_COLS = "template_id, tenant_id, name, duration_s, note, created_by, created_at, updated_at"

_INSERT = text(
    "INSERT INTO drill_templates (tenant_id, name, duration_s, note, created_by) "
    "VALUES (CAST(:tenant AS uuid), :name, :duration, :note, CAST(:user_id AS uuid)) "
    f"RETURNING {_COLS}"
)

_UPDATE = text(
    "UPDATE drill_templates SET name = :name, duration_s = :duration, note = :note, "
    "updated_at = now() "
    "WHERE template_id = CAST(:template AS uuid) AND archived_at IS NULL "
    f"RETURNING {_COLS}"
)

_ARCHIVE = text(
    "UPDATE drill_templates SET archived_at = now(), updated_at = now() "
    "WHERE template_id = CAST(:template AS uuid) AND archived_at IS NULL "
    "RETURNING template_id, name"
)

# Solo las vivas. Una archivada es, para todos los efectos de esta API, inexistente.
_SELECT_ONE = text(
    f"SELECT {_COLS} FROM drill_templates "
    "WHERE template_id = CAST(:template AS uuid) AND archived_at IS NULL"
)

_SELECT_ALL = text(
    f"SELECT {_COLS} FROM drill_templates WHERE archived_at IS NULL "
    "ORDER BY created_at DESC, template_id"
)

_DELETE_SITES = text("DELETE FROM drill_template_sites WHERE template_id = CAST(:template AS uuid)")

_INSERT_SITE = text(
    "INSERT INTO drill_template_sites (template_id, site_id, tenant_id) "
    "VALUES (CAST(:template AS uuid), CAST(:site AS uuid), CAST(:tenant AS uuid))"
)

# Los sitios de las plantillas dadas, con TODO lo que hace falta para decir si hoy
# se pueden usar. El LEFT JOIN es deliberado: bajo RLS —o bajo `site_scope`— un
# sitio ajeno devuelve nulos, y ese NULL **es el hecho** («ya no es visible para
# este usuario»), no un error de la consulta. Un INNER JOIN lo borraría de la
# lista, que es exactamente la desaparición silenciosa que la ficha prohíbe.
_SELECT_SITES = text(
    """
    SELECT ts.template_id, ts.site_id, s.name AS site_name, s.code AS site_code,
           s.status AS site_status,
           EXISTS (SELECT 1 FROM gateways g WHERE g.site_id = ts.site_id
                     AND g.status <> 'retired' AND g.iot_thing IS NOT NULL) AS commandable
    FROM drill_template_sites ts
    LEFT JOIN sites s ON s.site_id = ts.site_id
    WHERE ts.template_id = ANY(CAST(:templates AS uuid[]))
    ORDER BY ts.template_id, s.code NULLS LAST, ts.site_id
    """
)

# Sitios del tenant con gabinete comandable: lo que el alta acepta como destino.
# Misma condición que `drills._COMMANDABLE_SITES`, y por eso una plantilla no
# puede guardar un sitio que el simulacro no sabría alcanzar.
_COMMANDABLE_SITES = text(
    "SELECT s.site_id FROM sites s WHERE s.status <> 'retired' AND EXISTS "
    "(SELECT 1 FROM gateways g WHERE g.site_id = s.site_id "
    " AND g.status <> 'retired' AND g.iot_thing IS NOT NULL)"
)


def _estado(row: Any) -> tuple[str, str | None]:
    """En qué estado está HOY ese sitio de la plantilla, y por qué.

    Orden deliberado: **no visible** primero, porque cuando la fila no se ve no
    se sabe nada más de ella —ni si está retirada ni si tiene gabinete— y
    afirmar cualquiera de las otras dos cosas sería inventarlas.
    """
    if row["site_status"] is None:
        return SITIO_NO_VISIBLE, MOTIVO_SITIO[SITIO_NO_VISIBLE]
    if row["site_status"] == "retired":
        return SITIO_RETIRADO, MOTIVO_SITIO[SITIO_RETIRADO]
    if not row["commandable"]:
        return SITIO_SIN_GABINETE, MOTIVO_SITIO[SITIO_SIN_GABINETE]
    return SITIO_USABLE, None


async def sites_of_templates(
    conn: AsyncConnection, template_ids: list[str]
) -> dict[str, list[TemplateSiteOut]]:
    """Sitios de esas plantillas, agrupados y con su estado de hoy."""
    if not template_ids:
        return {}
    rows = (await conn.execute(_SELECT_SITES, {"templates": template_ids})).mappings().all()
    out: dict[str, list[TemplateSiteOut]] = {}
    for r in rows:
        estado, motivo = _estado(r)
        out.setdefault(str(r["template_id"]), []).append(
            TemplateSiteOut(
                site_id=r["site_id"],
                site_name=r["site_name"],
                site_code=r["site_code"],
                estado=estado,
                motivo=motivo,
            )
        )
    return out


def _out(row: Any, sites: list[TemplateSiteOut]) -> DrillTemplateOut:
    return DrillTemplateOut(
        **{k: row[k] for k in ("template_id", "tenant_id", "name", "duration_s", "note")},
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        sites=sites,
        # Sin sitios propios se lanzará contra todos los comandables del tenant,
        # que es la misma convención de `DrillCreateIn.site_ids = None`.
        todos_los_sitios=not sites,
        sitios_no_usables=sum(1 for s in sites if s.estado != SITIO_USABLE),
    )


async def _validar_sitios(conn: AsyncConnection, body: DrillTemplateIn) -> None:
    """404 si algún sitio pedido no es un destino válido de simulacro.

    Al **guardar** sí se rechaza: guardar una plantilla contra un sitio que no
    existe o no es alcanzable sería crear la trampa de golpe. Al **usarla** no se
    rechaza —se declara—, porque el inventario cambia entre una cosa y la otra.
    """
    if not body.site_ids:
        return
    validos = {str(r[0]) for r in (await conn.execute(_COMMANDABLE_SITES)).all()}
    fuera = [str(s) for s in body.site_ids if str(s) not in validos]
    if fuera:
        raise http_error(404, f"sitio(s) sin gateway comandable o no visibles: {fuera}")


async def _guardar_sitios(
    conn: AsyncConnection, template_id: Any, body: DrillTemplateIn, tenant_id: str
) -> None:
    """Reemplaza el conjunto entero. Editar una plantilla NO fusiona: quitar un
    sitio de la lista tiene que quitarlo de verdad."""
    await conn.execute(_DELETE_SITES, {"template": str(template_id)})
    for site_id in dict.fromkeys(body.site_ids):
        await conn.execute(
            _INSERT_SITE,
            {"template": str(template_id), "site": str(site_id), "tenant": tenant_id},
        )


def _nombre_repetido(exc: IntegrityError) -> bool:
    return "uq_drill_templates_tenant_name" in str(exc.orig)


@router.get("/drill-templates", response_model=DrillTemplateList)
async def list_templates(
    claims: Claims = Depends(_require_drill),
    conn: AsyncConnection = Depends(get_session),
) -> DrillTemplateList:
    """Las plantillas vivas del tenant, **con su estado de hoy**.

    El conteo de sitios no usables viaja en la LISTA y no solo en el detalle: el
    criterio de la ficha es que se sepa **al usarla**, y quien la elige está
    mirando la lista.
    """
    rows = (await conn.execute(_SELECT_ALL)).mappings().all()
    sites = await sites_of_templates(conn, [str(r["template_id"]) for r in rows])
    return DrillTemplateList(items=[_out(r, sites.get(str(r["template_id"]), [])) for r in rows])


@router.get("/drill-templates/{template_id}", response_model=DrillTemplateOut)
async def get_template(
    template_id: UUID,
    claims: Claims = Depends(_require_drill),
    conn: AsyncConnection = Depends(get_session),
) -> DrillTemplateOut:
    row = (await conn.execute(_SELECT_ONE, {"template": str(template_id)})).mappings().first()
    if row is None:
        # 404 y no 403: un 403 confirmaría que la plantilla de otro cliente existe.
        raise http_error(404, "plantilla no encontrada")
    sites = await sites_of_templates(conn, [str(template_id)])
    return _out(row, sites.get(str(template_id), []))


@router.post("/drill-templates", response_model=DrillTemplateOut, status_code=201)
async def create_template(
    body: DrillTemplateIn,
    claims: Claims = Depends(_require_drill),
    conn: AsyncConnection = Depends(get_session),
) -> DrillTemplateOut:
    await _validar_sitios(conn, body)
    try:
        row = (
            (
                await conn.execute(
                    _INSERT,
                    {
                        "tenant": claims.tenant_id,
                        "name": body.name.strip(),
                        "duration": body.duration_s,
                        "note": body.note,
                        "user_id": claims.sub,
                    },
                )
            )
            .mappings()
            .one()
        )
    except IntegrityError as exc:
        if _nombre_repetido(exc):
            raise http_error(409, f"ya existe una plantilla llamada {body.name.strip()!r}") from exc
        raise
    await _guardar_sitios(conn, row["template_id"], body, claims.tenant_id)
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="drill_template_created",
        obj=f"drill_template:{row['template_id']}",
        meta={"name": row["name"], "sites": len(body.site_ids), "duration_s": body.duration_s},
    )
    sites = await sites_of_templates(conn, [str(row["template_id"])])
    return _out(row, sites.get(str(row["template_id"]), []))


@router.put("/drill-templates/{template_id}", response_model=DrillTemplateOut)
async def update_template(
    template_id: UUID,
    body: DrillTemplateIn,
    claims: Claims = Depends(_require_drill),
    conn: AsyncConnection = Depends(get_session),
) -> DrillTemplateOut:
    """Edita la plantilla. **No toca los simulacros que ya salieron de ella**:
    aquellos copiaron sus valores al lanzarse (criterio 2 de la ficha)."""
    await _validar_sitios(conn, body)
    try:
        row = (
            (
                await conn.execute(
                    _UPDATE,
                    {
                        "template": str(template_id),
                        "name": body.name.strip(),
                        "duration": body.duration_s,
                        "note": body.note,
                    },
                )
            )
            .mappings()
            .first()
        )
    except IntegrityError as exc:
        if _nombre_repetido(exc):
            raise http_error(409, f"ya existe una plantilla llamada {body.name.strip()!r}") from exc
        raise
    if row is None:
        raise http_error(404, "plantilla no encontrada")
    await _guardar_sitios(conn, template_id, body, claims.tenant_id)
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="drill_template_updated",
        obj=f"drill_template:{template_id}",
        meta={"name": row["name"], "sites": len(body.site_ids), "duration_s": body.duration_s},
    )
    sites = await sites_of_templates(conn, [str(template_id)])
    return _out(row, sites.get(str(template_id), []))


@router.delete("/drill-templates/{template_id}", status_code=204)
async def delete_template(
    template_id: UUID,
    claims: Claims = Depends(_require_drill),
    conn: AsyncConnection = Depends(get_session),
) -> None:
    """La archiva. Ver la cabecera: borrarla de verdad dejaría huérfana la
    procedencia de los simulacros que salieron de ella."""
    row = (await conn.execute(_ARCHIVE, {"template": str(template_id)})).mappings().first()
    if row is None:
        raise http_error(404, "plantilla no encontrada")
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="drill_template_archived",
        obj=f"drill_template:{template_id}",
        meta={"name": row["name"]},
    )
