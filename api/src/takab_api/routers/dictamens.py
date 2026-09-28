"""Routers de dictámenes (T-1.22 · B2): cadena de versiones + firma del inspector.

Lectura = quienes tienen Triage en RBAC §2 (matriz de rutas). La firma es un acto
profesional del inspector: ``SIGN_ROLES`` se DERIVA de ``matrix.ROLE_ACTION_MATRIX``
(``sign_dictamen``), que no se la concede al superadmin pese a su "Total" en Triage §2.
La política ``dictamens_admin`` (DDL) sigue permitiendo el INSERT a la identidad interna
para soporte/operación de DB, pero la API no expone la firma a ese rol.

Firmar = INSERTAR una fila nueva que supersede la última de la cadena (nunca UPDATE;
trigger append-only).
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.deps import require_roles
from takab_api.auth.matrix import ROLE_ROUTE_MATRIX, TRIAGE, roles_with_action
from takab_api.dictamen.rules import banda_de
from takab_api.felt import CLAVE_UMBRAL_CONGELADO, umbral_congelado
from takab_api.queries import dictamens as q
from takab_api.queries import mobile as mobile_q
from takab_api.reingreso import HABITABLES
from takab_api.routers._common import http_error, read_session
from takab_api.schemas.dictamens import (
    DICTAMEN_STATUS,
    DictamenList,
    DictamenOut,
    DictamenSignIn,
)

# Dictamen HABITABLE: firma que libera el reingreso (spec §7 · 2.7). [T-9.32 · D-43]
# UNA sola copia, en `reingreso.py`.
_HABITABLE = HABITABLES

# Roles con Triage (celda ≠ "—" en RBAC §2), derivados de la matriz de rutas.
TRIAGE_ROLES: tuple[str, ...] = tuple(
    sorted(r for r, routes in ROLE_ROUTE_MATRIX.items() if TRIAGE in routes)
)

# Firma del dictamen: derivada de la matriz (acto profesional del inspector). El
# "Total" de superadmin en Triage §2 concede LECTURA, no firma.
SIGN_ROLES: tuple[str, ...] = roles_with_action("sign_dictamen")

# [T-9.31 · D-43] Confirmar el dictamen de la regla: brigada, inspector y
# administración (``confirm_dictamen`` en la matriz). El occupant no.
CONFIRM_ROLES: tuple[str, ...] = roles_with_action("confirm_dictamen")

# [F3·r2] Quien CONFIRMA tiene que poder LEER la cadena que confirma: la pantalla
# de la app la lee por aquí. Triage ∪ confirmación, y siempre dentro del alcance
# por inmueble del portador (``_en_alcance``).
READ_ROLES: tuple[str, ...] = tuple(sorted(set(TRIAGE_ROLES) | set(CONFIRM_ROLES)))

_require_read = require_roles(*READ_ROLES)
_require_sign = require_roles(*SIGN_ROLES)
_require_confirm = require_roles(*CONFIRM_ROLES)

router = APIRouter()


def _en_alcance(claims: Claims, site_id: object) -> None:
    """[F3·r2] El inmueble del incidente dentro del ``site_scope`` del portador.

    Mismo criterio que ``_incident_in_scope`` de las rutas móviles (``scope_filter``,
    default-deny), pero con 404: fuera del alcance el incidente NO existe para él,
    igual que fuera del tenant (RLS)."""
    allowed = scope_filter(claims)
    if allowed is not None and str(site_id) not in allowed:
        raise http_error(404, "incidente no encontrado")


@router.get(
    "/incidents/{incident_id}/dictamens",
    response_model=DictamenList,
)
async def list_dictamens(
    incident_id: UUID,
    claims: Claims = Depends(_require_read),
    conn: AsyncConnection = Depends(read_session),
) -> DictamenList:
    """Cadena de dictámenes del incidente (más reciente primero). 404 si no visible
    (otro tenant, o fuera del alcance por inmueble del portador)."""
    tenant_stmt, tenant_params = q.select_incident_tenant(str(incident_id))
    inc = (await conn.execute(tenant_stmt, tenant_params)).first()
    if inc is None:
        raise http_error(404, "incidente no encontrado")
    _en_alcance(claims, inc.site_id)
    stmt, params = q.select_dictamens(str(incident_id))
    rows = (await conn.execute(stmt, params)).mappings().all()
    return DictamenList(items=[DictamenOut(**dict(r)) for r in rows])


@router.post(
    "/incidents/{incident_id}/dictamens",
    response_model=DictamenOut,
    status_code=201,
)
async def sign_dictamen(
    incident_id: UUID,
    body: DictamenSignIn,
    claims: Claims = Depends(_require_sign),
    conn: AsyncConnection = Depends(read_session),
) -> DictamenOut:
    """Firma un dictamen: inserta fila nueva superseeding la última de la cadena."""
    if body.status not in DICTAMEN_STATUS:
        raise http_error(400, "status de dictamen inválido")

    # [T-9.30 · D-43] El incidente FOR UPDATE antes de leer la cabeza: serializa con
    # el worker y con la confirmación, y la cabeza se lee DENTRO de este lock.
    tenant_stmt, tenant_params = q.lock_incident(str(incident_id))
    row = (await conn.execute(tenant_stmt, tenant_params)).first()
    if row is None:
        raise http_error(404, "incidente no encontrado")
    _en_alcance(claims, row.site_id)
    tenant_id = str(row.tenant_id)

    head_stmt, head_params = q.select_chain_head(str(incident_id))
    head = (await conn.execute(head_stmt, head_params)).scalar_one_or_none()
    supersedes = str(head) if head is not None else None

    basis: dict = {}
    if body.notes is not None:
        basis["notes"] = body.notes
    # [T-7.37] Los umbrales congelados se ARRASTRAN VERBATIM a la fila firmada.
    # Sin esto, la firma —que es la fila de más peso legal del sistema— nacería
    # sin la congelación y la cadena quedaría dependiendo de que nadie pode
    # `rule_sets`. No se re-resuelven: qué umbral regía cuando tembló no lo
    # decide el momento de firmar.
    chain_stmt, chain_params = q.select_chain_basis(str(incident_id))
    heredado = umbral_congelado(
        [r.basis for r in (await conn.execute(chain_stmt, chain_params)).all()]
    )
    if heredado is not None:
        basis[CLAVE_UMBRAL_CONGELADO] = heredado

    ins_stmt, ins_params = q.insert_dictamen(
        tenant_id=tenant_id,
        incident_id=str(incident_id),
        status=body.status,
        basis=json.dumps(basis),
        signed_by=claims.sub,
        supersedes=supersedes,
    )
    created = (await conn.execute(ins_stmt, ins_params)).mappings().one()

    # [T-5.20] Y VERBO EN LA BITÁCORA, el acto de mayor peso legal del sistema.
    #
    # Va ANTES del `if` de habitabilidad y no dentro, que es lo que hacía que un
    # dictamen NO habitable firmado no dejara rastro en ninguno de los dos
    # sitios donde se busca: ni en la bitácora (no escribía nunca) ni en el
    # timeline (solo si era habitable). El hecho seguía en `dictamens`, que es
    # append-only, pero el sitio donde un perito, un seguro o una auditoría
    # miran «quién firmó qué y cuándo» es esto.
    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="dictamen_signed",
        obj=f"incident:{incident_id}",
        meta={
            "dictamen_id": str(created["dictamen_id"]),
            # El veredicto en el detalle: sin él la fila dice que alguien firmó y
            # no qué firmó, que es la mitad de la pregunta.
            "status": body.status,
            "habitable": body.status in _HABITABLE,
            # A quién sustituye: la cadena se reconstruye desde la bitácora sin
            # tener que leer la tabla de dictámenes.
            "supersedes": supersedes,
        },
    )

    # [T-2.12] Dictamen HABITABLE firmado ⇒ acción en el timeline: el
    # orchestrator la convierte en push OPS de cambio de fase que libera las
    # pantallas 1.5 del ocupante (reentry_approved lo deriva mobile-state).
    if body.status in _HABITABLE:
        await conn.execute(
            mobile_q.INSERT_DICTAMEN_SIGNED_ACTION,
            {
                "incident": str(incident_id),
                "tenant": tenant_id,
                "actor": f"user:{claims.sub}",
                "payload": json.dumps(
                    {"status": body.status, "folio": str(created["dictamen_id"])}
                ),
            },
        )
    return DictamenOut(**dict(created))


@router.post(
    "/incidents/{incident_id}/dictamens/{dictamen_id}/confirm",
    response_model=DictamenOut,
    status_code=201,
)
async def confirm_dictamen(
    incident_id: UUID,
    dictamen_id: UUID,
    claims: Claims = Depends(_require_confirm),
    conn: AsyncConnection = Depends(read_session),
) -> DictamenOut:
    """[T-9.31 · D-43] CONFIRMA el dictamen vigente que emitió la regla.

    Inserta una fila NUEVA con el mismo status y banda que la cabeza, firmada por
    quien confirma (``signature_kind='confirmation'``) y que la supersede. No es un
    veredicto propio: por eso sólo la CABEZA vigente (409 si no), sólo sin firmar
    (409 si ya lo está), nunca un ROJO (403: ése lo firma el inspector por
    ``POST /incidents/{id}/dictamens``) y SÓLO un AMARILLO (409 con un VERDE —lo
    firma el sistema tras la gracia— o con una fila v1 sin banda). Todo dentro del
    lock del incidente."""
    lock_stmt, lock_params = q.lock_incident(str(incident_id))
    row = (await conn.execute(lock_stmt, lock_params)).first()
    if row is None:
        raise http_error(404, "incidente no encontrado")
    _en_alcance(claims, row.site_id)
    tenant_id = str(row.tenant_id)

    head_stmt, head_params = q.select_chain_head_row(str(incident_id))
    head = (await conn.execute(head_stmt, head_params)).mappings().first()
    if head is None or head["dictamen_id"] != dictamen_id:
        raise http_error(409, "el dictamen no es el vigente: recargue la cadena")
    if head["signed_by"] is not None:
        raise http_error(409, "el dictamen vigente ya está firmado")
    band = banda_de(head["status"], head["band"])
    if band == "rojo":
        raise http_error(403, "un dictamen ROJO lo firma el inspector, no se confirma")
    # [F3·r3 · D-43] Sólo se CONFIRMA un AMARILLO de la regla. Un VERDE confirmado se
    # saltaba la gracia de 300 s y la exigencia de tier normal del VERDE automático
    # (medido: REINGRESO AUTORIZADO en plena sacudida). Una fila histórica sin banda
    # no es una salida de la regla v2: no hay nada que confirmar.
    if head["band"] == "verde":
        raise http_error(
            409, "el VERDE lo firma el sistema tras la gracia (o el inspector); no se confirma"
        )
    if head["band"] != "amarillo":
        raise http_error(
            409, "sólo se confirma un AMARILLO de la regla; este dictamen lo firma el inspector"
        )
    # [F3·r2] Un daño de categoría ROJA reportado que la regla aún no subió a ROJO
    # (su pasada corre cada pocos segundos): confirmar ahora liberaría el reingreso
    # con daño estructural. Leído DENTRO del lock: un reporte en vuelo espera aquí.
    dmg_stmt, dmg_params = q.select_red_damage(str(incident_id))
    rojos = [r.clave for r in (await conn.execute(dmg_stmt, dmg_params)).all()]
    if rojos:
        raise http_error(
            409,
            "hay daños reportados que exigen inspección (" + ", ".join(rojos) + "): "
            "requiere inspector, no se confirma",
        )

    # [F3·r2] El ROL de quien confirma viaja en la fila: web y papel lo rotulan
    # («CONFIRMADO POR …») sin tener que leer la bitácora.
    basis: dict = {"confirma": str(dictamen_id), "confirmacion": {"rol": claims.role}}
    # [T-7.37] La congelación de umbrales se ARRASTRA verbatim, igual que al firmar.
    chain_stmt, chain_params = q.select_chain_basis(str(incident_id))
    heredado = umbral_congelado(
        [r.basis for r in (await conn.execute(chain_stmt, chain_params)).all()]
    )
    if heredado is not None:
        basis[CLAVE_UMBRAL_CONGELADO] = heredado

    ins_stmt, ins_params = q.insert_dictamen(
        tenant_id=tenant_id,
        incident_id=str(incident_id),
        status=head["status"],
        basis=json.dumps(basis),
        signed_by=claims.sub,
        supersedes=str(dictamen_id),
        signature_kind="confirmation",
    )
    created = (await conn.execute(ins_stmt, ins_params)).mappings().one()

    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=f"user:{claims.sub}",
        verb="dictamen_confirmed",
        obj=f"incident:{incident_id}",
        meta={
            "dictamen_id": str(created["dictamen_id"]),
            "status": head["status"],
            "band": band,
            "habitable": head["status"] in _HABITABLE,
            "supersedes": str(dictamen_id),
            "role": claims.role,
        },
    )
    # La acción del timeline: su push OPS de cambio de fase libera las pantallas
    # del ocupante (el orquestador la trata como `dictamen_signed`).
    await conn.execute(
        mobile_q.INSERT_DICTAMEN_CONFIRMED_ACTION,
        {
            "incident": str(incident_id),
            "tenant": tenant_id,
            "actor": f"user:{claims.sub}",
            "payload": json.dumps(
                {
                    "status": head["status"],
                    "band": band,
                    "folio": str(created["dictamen_id"]),
                    "supersedes": str(dictamen_id),
                }
            ),
        },
    )
    return DictamenOut(**dict(created))
