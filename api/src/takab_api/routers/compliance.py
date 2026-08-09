"""Etiquetas de cumplimiento por tenant (T-2.82): alta, edición y lectura.

La tabla existe desde el schema y **nadie la cargaba**. Esto la carga, y lo hace con
las cerraduras de ``takab_api.compliance``: catálogo cerrado de clases, referencia
citable obligatoria y cero huecos donde escribir "verificado por TAKAB".

**Quién escribe.** Solo ``takab_superadmin`` (acción ``manage_tenants``). El DDL es
más ancho —``cl_admin`` deja escribir a cualquier identidad interna, y su comentario
lo justifica: *"escritura interna hasta ratificar el marco citable — GATE-LEGAL"*—,
pero la API estrecha esa puerta a la mitad, igual que ``routers/dictamens`` estrecha
``dictamens_admin``. Cargar una afirmación normativa en la ficha de un cliente es
administrar esa ficha, y eso ya es del dueño de la plataforma: es exactamente el mismo
acto que ``PATCH /tenants/{id}``, que ya usa ``manage_tenants``. No se inventa una
acción nueva para no abrir una frontera nueva donde la existente encaja.

Se toma el tenant de la RUTA y no de los claims a propósito: ``cl_admin`` **no filtra
por tenant** (``USING (app_is_takab_internal())`` a secas), así que la base no
detendría a un superadmin que escriba en el cliente equivocado. Mismo patrón que
documenta ``routers/_common.INTERNAL_ROLES``.

**Quién lee.** Quien vea al cliente; la RLS ``cl_read`` decide (tenant propio ∪
interno ∪ rama gov). No hay acción de lectura porque no hay secreto: estas mismas
etiquetas se sirven a la app de cada ocupante en ``GET /sites/{id}/mobile-state``.
Un cliente que no existe *para quien pregunta* devuelve **404, nunca un documento
vacío**: "no tienes permiso" y "no declaró nada" son hechos distintos, y presentar el
segundo cuando ocurre el primero es fabricar una afirmación sobre un tercero.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import require_roles, require_web_surface
from takab_api.auth.matrix import roles_with_action
from takab_api.compliance import (
    PROVENANCE,
    ComplianceDocument,
    ComplianceError,
    build_claims,
    parse_document,
    to_storage,
)
from takab_api.queries import compliance as q
from takab_api.routers._common import http_error, read_session
from takab_api.schemas.compliance import ComplianceLabelsIn, ComplianceLabelsOut, doc_out

#: Misma acción que edita la ficha del cliente: SOLO ``takab_superadmin``.
_require_manage = require_roles(*roles_with_action("manage_tenants"))

router = APIRouter(dependencies=[Depends(require_web_surface)])

_PATH = "/tenants/{tenant_id}/compliance-labels"


def _out(
    tenant_id: UUID, doc: ComplianceDocument, updated_at=None, updated_by=None
) -> ComplianceLabelsOut:
    """Mismo cuerpo que sirve el forense (``doc_out``) + quién lo tocó y cuándo."""
    return ComplianceLabelsOut(
        **doc_out(doc).model_dump(),
        tenant_id=tenant_id,
        updated_at=updated_at,
        updated_by=updated_by,
    )


async def _require_visible_tenant(conn: AsyncConnection, tenant_id: UUID) -> None:
    if (await conn.execute(q.TENANT_VISIBLE, {"tenant": str(tenant_id)})).first() is None:
        raise http_error(404, "cliente no encontrado")


@router.get(_PATH, response_model=ComplianceLabelsOut)
async def get_compliance_labels(
    tenant_id: UUID,
    conn: AsyncConnection = Depends(read_session),
) -> ComplianceLabelsOut:
    """Marco normativo DECLARADO por el cliente, con su deslinde pegado.

    Sin fila devuelve un documento vacío —con su ``notice``—, no un 404: el cliente
    existe y no ha declarado nada, que es el estado normal mientras GATE-LEGAL siga
    abierto.
    """
    await _require_visible_tenant(conn, tenant_id)
    row = (await conn.execute(q.SELECT_LABELS, {"tenant": str(tenant_id)})).first()
    if row is None:
        return _out(tenant_id, ComplianceDocument())
    return _out(tenant_id, parse_document(row.labels), row.updated_at, row.updated_by)


@router.put(_PATH, response_model=ComplianceLabelsOut)
async def put_compliance_labels(
    tenant_id: UUID,
    body: ComplianceLabelsIn,
    claims: Claims = Depends(_require_manage),
    conn: AsyncConnection = Depends(read_session),
) -> ComplianceLabelsOut:
    """Reemplaza el documento completo del cliente. SOLO ``takab_superadmin``.

    La bitácora se lleva el TEXTO ÍNTEGRO de lo declarado, no un "cambió": el
    ``audit_log`` no se poda nunca (regla de oro 11) y es lo único que permitirá
    saber, dentro de dos años, qué decía exactamente la etiqueta el día en que se
    firmó un dictamen que la imprimió. Y va al tenant TOCADO, no al de los claims del
    operador: el cliente afectado tiene que tener el rastro en su propia bitácora.
    """
    await _require_visible_tenant(conn, tenant_id)

    try:
        claims_doc = build_claims([item.model_dump() for item in body.items])
    except ComplianceError as exc:
        raise http_error(422, f"etiqueta de cumplimiento inválida: {exc}") from exc

    current = (await conn.execute(q.SELECT_LABELS, {"tenant": str(tenant_id)})).first()
    if body.base_updated_at is not None and (
        current is None or current.updated_at != body.base_updated_at
    ):
        raise http_error(409, "las etiquetas cambiaron en el servidor; recarga y reintenta")
    previous = parse_document(current.labels) if current is not None else ComplianceDocument()

    row = (
        await conn.execute(
            q.UPSERT_LABELS,
            {
                "tenant": str(tenant_id),
                "labels": json.dumps(to_storage(claims_doc)),
                "actor": claims.sub,
            },
        )
    ).first()
    if row is None:  # pragma: no cover - la RLS ya dejó pasar el rol; red de seguridad
        raise http_error(403, "la base rechazó la escritura de etiquetas")

    await audit_async(
        conn,
        tenant_id=str(tenant_id),
        actor=f"user:{claims.sub}",
        verb="compliance_labels_update",
        obj=f"tenant:{tenant_id}",
        meta={
            "provenance": PROVENANCE,
            "items": [
                {"key": c.key, "claim": c.claim, "reference": c.reference} for c in claims_doc
            ],
            "replaced": len(previous.items),
            "replaced_unreadable": previous.unreadable is not None,
        },
    )
    return _out(tenant_id, parse_document(row.labels), row.updated_at, row.updated_by)
