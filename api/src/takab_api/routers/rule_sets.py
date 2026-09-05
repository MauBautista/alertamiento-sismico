"""Routers de rule_sets (T-1.22 · B2): versionado + intención de publicación.

Lectura del catálogo del tenant (RLS). Escritura (nueva versión) y publish exigen
``edit_thresholds`` (RBAC §2 = superadmin/tenant_admin). ``publish`` NO sincroniza al
edge (eso es T-1.23); solo marca la intención y responde 202 ``pending_sync``.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import require_roles, require_web_surface
from takab_api.auth.matrix import ROLE_ACTION_MATRIX
from takab_api.queries import rule_sets as q
from takab_api.routers._common import http_error, read_session
from takab_api.schemas.rule_sets import (
    SCOPE_TYPES,
    RuleSetList,
    RuleSetOut,
    RuleSetPublishOut,
    RuleSetPutIn,
    RuleSetRollbackIn,
    merge_secrets,
    redact_config,
)
from takab_api.schemas.tipologia import BuildingTypeCatalog, BuildingTypeOut
from takab_api.sites import tipologia

# Roles que administran umbrales (RBAC §2 vía la matriz de acciones).
EDIT_THRESHOLDS_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, a in ROLE_ACTION_MATRIX.items() if a["edit_thresholds"])
)

_require_edit = require_roles(*EDIT_THRESHOLDS_ROLES)

router = APIRouter()


@router.get(
    "/rule-sets",
    response_model=RuleSetList,
    dependencies=[Depends(require_web_surface)],
)
async def list_rule_sets(
    conn: AsyncConnection = Depends(read_session),
) -> RuleSetList:
    """rule_sets del tenant (RLS): versiones activas primero. Secretos redactados."""
    stmt, params = q.select_rule_sets()
    rows = (await conn.execute(stmt, params)).mappings().all()
    return RuleSetList(items=[_out(dict(r)) for r in rows])


def _out(row: dict) -> RuleSetOut:
    """``RuleSetOut`` con el ``config`` sin secretos (nunca salen del servidor)."""
    return RuleSetOut(**{**row, "config": redact_config(row["config"])})


@router.put("/rule-sets", response_model=RuleSetOut, status_code=201)
async def put_rule_set(
    body: RuleSetPutIn,
    claims: Claims = Depends(_require_edit),
    conn: AsyncConnection = Depends(read_session),
) -> RuleSetOut:
    """Crea una NUEVA versión activa del alcance (version+1) y apaga las previas.

    El alcance DEBE pertenecer al tenant del token: la fila nueva se inserta con
    ``tenant_id = claims.tenant_id`` mientras el ``scope_id`` lo elige el cuerpo, así
    que un alcance ajeno produciría un rule_set con el tenant de A y el alcance de B
    — invisible para B (RLS filtra por ``tenant_id``) pero aplicado a sus gabinetes
    por el worker de sync, que resuelve por alcance. 403 (o 404 si RLS lo oculta).
    """
    if body.scope_type not in SCOPE_TYPES:
        raise http_error(400, "scope_type inválido")

    owner_stmt, owner_params = q.select_scope_tenant(body.scope_type, str(body.scope_id))
    owner = (await conn.execute(owner_stmt, owner_params)).first()
    if owner is None:
        raise http_error(404, "alcance no encontrado")
    if str(owner.tenant_id) != claims.tenant_id:
        raise http_error(403, "el alcance pertenece a otro tenant")

    active_stmt, active_params = q.select_active_scope(body.scope_type, str(body.scope_id))
    active = (await conn.execute(active_stmt, active_params)).mappings().first()

    # Concurrencia optimista: el PUT reemplaza el blob ENTERO del alcance.
    if body.base_version is not None:
        current_version = active["version"] if active else None
        if current_version != body.base_version:
            raise http_error(409, "el rule_set cambió en el servidor; recarga y reintenta")

    # El cliente nunca vio los secretos: se reinyectan los vigentes.
    config = merge_secrets(body.config, active["config"] if active else None)

    deact_stmt, deact_params = q.deactivate_scope(
        body.scope_type, str(body.scope_id), claims.tenant_id
    )
    await conn.execute(deact_stmt, deact_params)

    ins_stmt, ins_params = q.insert_new_version(
        tenant_id=claims.tenant_id,
        scope_type=body.scope_type,
        scope_id=str(body.scope_id),
        config=json.dumps(config),
        created_by=claims.sub,
    )
    created = (await conn.execute(ins_stmt, ins_params)).mappings().one()
    return _out(dict(created))


@router.post("/rule-sets/{rule_set_id}/publish", status_code=202)
async def publish_rule_set(
    rule_set_id: UUID,
    response: Response,
    claims: Claims = Depends(_require_edit),
    conn: AsyncConnection = Depends(read_session),
) -> RuleSetPublishOut:
    """Marca la intención de sincronizar el rule_set al edge (202 pending_sync)."""
    stmt, params = q.select_rule_set(str(rule_set_id))
    row = (await conn.execute(stmt, params)).mappings().first()
    if row is None:
        raise http_error(404, "rule_set no encontrado")

    await audit_async(
        conn,
        tenant_id=row["tenant_id"],
        actor=f"user:{claims.sub}",
        verb="rule_set_publish",
        obj=f"rule_set:{rule_set_id}",
        meta={"version": row["version"], "status": "pending_sync"},
    )
    response.status_code = 202
    return RuleSetPublishOut(rule_set_id=rule_set_id, version=row["version"])


# ─────────────────────────────────────────── [T-5.16 · D-28] la tipología


@router.get(
    "/building-types",
    response_model=BuildingTypeCatalog,
    dependencies=[Depends(require_web_surface)],
)
async def list_building_types() -> BuildingTypeCatalog:
    """Catálogo cerrado de tipología, con su banda de umbral **de referencia**.

    Sale con `resuelve_umbrales: false` en el cuerpo, y no como comentario: la
    consola tiene que poder decir en pantalla que esto SUGIERE. Un catálogo que
    llegara pelado invitaría a que la siguiente pantalla lo aplicara sola, que es
    justo lo que `D-28` prohíbe.
    """
    cat = tipologia.catalogo()
    return BuildingTypeCatalog(
        resuelve_umbrales=cat["resuelve_umbrales"],
        por_que_no_resuelve=list(cat["por_que_no_resuelve"]),
        sin_referencia_de_pgv=cat["sin_referencia_de_pgv"],
        items=[
            BuildingTypeOut(
                value=t["value"],
                label=t["label"],
                banda=t["banda"],
                sin_banda_por_que=t.get("sin_banda_por_que"),
            )
            for t in cat["tipos"]
        ],
    )


# ───────────────────────────────────────────── [T-5.16] volver atrás


@router.post("/rule-sets/{rule_set_id}/rollback", response_model=RuleSetOut, status_code=201)
async def rollback_rule_set(
    rule_set_id: UUID,
    body: RuleSetRollbackIn,
    claims: Claims = Depends(_require_edit),
    conn: AsyncConnection = Depends(read_session),
) -> RuleSetOut:
    """Vuelve a una versión anterior CREANDO una nueva que declara a cuál vuelve.

    El histórico es evidencia (regla de oro 11) y no se reescribe: volver atrás
    **avanza** el contador. Hasta hoy la única forma de volver era teclear los
    valores viejos, que además perdía la constancia de que aquello fue una
    reversión y no una edición cualquiera.

    Los secretos NO se restauran. Un `secret` de webhook puede haberse rotado
    justamente porque se filtró, y resucitarlo al revertir un umbral sería
    devolver al aire una credencial retirada: se conservan los VIGENTES, que es
    la misma regla que ya aplica el PUT desde el otro lado.
    """
    stmt, params = q.select_rule_set(str(rule_set_id))
    destino = (await conn.execute(stmt, params)).mappings().first()
    if destino is None:
        raise http_error(404, "rule_set no encontrado")
    if str(destino["tenant_id"]) != claims.tenant_id:
        raise http_error(403, "el rule_set pertenece a otro tenant")

    scope_type, scope_id = destino["scope_type"], str(destino["scope_id"])

    active_stmt, active_params = q.select_active_scope(scope_type, scope_id)
    active = (await conn.execute(active_stmt, active_params)).mappings().first()
    actual = active["version"] if active else None
    if actual != body.base_version:
        raise http_error(409, "el rule_set cambió en el servidor; recarga y reintenta")
    if destino["version"] == actual:
        raise http_error(409, "esa versión ya es la activa: no hay a dónde volver")

    # `redact_config` quita los secretos de la versión vieja y `merge_secrets`
    # reinyecta los vigentes: el resultado son los VALORES de entonces con las
    # CREDENCIALES de ahora. Se reutilizan las dos funciones que ya gobiernan
    # esto en el PUT en vez de escribir una tercera regla de secretos.
    config = merge_secrets(redact_config(destino["config"]), active["config"] if active else None)

    deact_stmt, deact_params = q.deactivate_scope(scope_type, scope_id, claims.tenant_id)
    await conn.execute(deact_stmt, deact_params)

    ins_stmt, ins_params = q.insert_new_version(
        tenant_id=claims.tenant_id,
        scope_type=scope_type,
        scope_id=scope_id,
        config=json.dumps(config),
        created_by=claims.sub,
        rolled_back_to=str(rule_set_id),
    )
    created = (await conn.execute(ins_stmt, ins_params)).mappings().one()

    await audit_async(
        conn,
        tenant_id=destino["tenant_id"],
        actor=f"user:{claims.sub}",
        verb="rule_set_rollback",
        obj=f"rule_set:{created['rule_set_id']}",
        meta={
            "desde_version": actual,
            "a_version": destino["version"],
            "nueva_version": created["version"],
            "scope_type": scope_type,
            "scope_id": scope_id,
        },
    )
    return _out(dict(created))
