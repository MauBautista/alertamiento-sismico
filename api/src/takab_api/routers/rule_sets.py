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
)

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
    """rule_sets del tenant (RLS): versiones activas primero."""
    stmt, params = q.select_rule_sets()
    rows = (await conn.execute(stmt, params)).mappings().all()
    return RuleSetList(items=[RuleSetOut(**dict(r)) for r in rows])


@router.put("/rule-sets", response_model=RuleSetOut, status_code=201)
async def put_rule_set(
    body: RuleSetPutIn,
    claims: Claims = Depends(_require_edit),
    conn: AsyncConnection = Depends(read_session),
) -> RuleSetOut:
    """Crea una NUEVA versión activa del alcance (version+1) y apaga las previas."""
    if body.scope_type not in SCOPE_TYPES:
        raise http_error(400, "scope_type inválido")

    deact_stmt, deact_params = q.deactivate_scope(body.scope_type, str(body.scope_id))
    await conn.execute(deact_stmt, deact_params)

    ins_stmt, ins_params = q.insert_new_version(
        tenant_id=claims.tenant_id,
        scope_type=body.scope_type,
        scope_id=str(body.scope_id),
        config=json.dumps(body.config),
        created_by=claims.sub,
    )
    created = (await conn.execute(ins_stmt, ins_params)).mappings().one()
    return RuleSetOut(**dict(created))


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
