"""Superficie móvil · recursos del PORTADOR (T-2.03 · spec §5).

- ``/me/push-tokens``  — registro/rotación/revocación del token FCM/APNs.
- ``/me/device-keys``  — registro de la llave pública respaldada por hardware
  (§2.1-B: el teléfono firma INTENCIONES; la nube firma comandos — T-2.09).
- ``/me/enrollment``   — alta por código de sitio (R2: crea la asignación de
  zona; el alcance móvil se resuelve server-side, sin tocar claims de Cognito).

Todo exige superficie móvil (``mobile``/``both``). RLS + políticas ``*_self``
acotan cada fila al portador; aquí solo se orquesta y se audita.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit_async
from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_mobile_surface
from takab_api.queries import mobile as q
from takab_api.routers._common import http_error, integrity_error
from takab_api.schemas.mobile import (
    DeviceKeyIn,
    DeviceKeyOut,
    EnrollmentIn,
    EnrollmentOut,
    PushTokenIn,
    PushTokenOut,
)

router = APIRouter(dependencies=[Depends(require_mobile_surface)])


@router.post("/me/push-tokens", response_model=PushTokenOut, status_code=201)
async def register_push_token(
    body: PushTokenIn,
    claims: Claims = Depends(require_mobile_surface),
    conn: AsyncConnection = Depends(get_session),
) -> PushTokenOut:
    """Upsert por ``token``: re-registrar un token existente lo revive y sella
    ``last_seen_at`` (rotación de FCM/APNs sin filas fantasma)."""
    row = (
        await conn.execute(
            q.UPSERT_PUSH_TOKEN,
            {
                "tenant": claims.tenant_id,
                "sub": claims.sub,
                "platform": body.platform,
                "token": body.token,
                "site": str(body.site_id) if body.site_id else None,
            },
        )
    ).first()
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="push_token_register",
        obj=f"push_token:{row.push_token_id}",
        meta={"platform": body.platform},
    )
    return PushTokenOut(**dict(row._mapping))


@router.get("/me/push-tokens", response_model=list[PushTokenOut])
async def list_push_tokens(
    conn: AsyncConnection = Depends(get_session),
) -> list[PushTokenOut]:
    """Tokens vivos del portador (la política ``pt_self`` acota las filas)."""
    rows = (await conn.execute(q.LIST_PUSH_TOKENS)).all()
    return [PushTokenOut(**dict(r._mapping)) for r in rows]


@router.delete("/me/push-tokens/{push_token_id}", status_code=204)
async def revoke_push_token(
    push_token_id: UUID,
    claims: Claims = Depends(require_mobile_surface),
    conn: AsyncConnection = Depends(get_session),
) -> None:
    row = (await conn.execute(q.REVOKE_PUSH_TOKEN, {"id": str(push_token_id)})).first()
    if row is None:
        raise http_error(404, "token no encontrado")
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="push_token_revoke",
        obj=f"push_token:{push_token_id}",
        meta={},
    )


@router.post("/me/device-keys", response_model=DeviceKeyOut, status_code=201)
async def register_device_key(
    body: DeviceKeyIn,
    claims: Claims = Depends(require_mobile_surface),
    conn: AsyncConnection = Depends(get_session),
) -> DeviceKeyOut:
    """Registra la llave pública del dispositivo. El material privado JAMÁS
    sale del Secure Enclave/Keystore; aquí solo llega el SPKI público."""
    row = (
        await conn.execute(
            q.INSERT_DEVICE_KEY,
            {
                "tenant": claims.tenant_id,
                "sub": claims.sub,
                "platform": body.platform,
                "public_key": body.public_key,
                "attestation": json.dumps(body.attestation),
            },
        )
    ).first()
    await audit_async(
        conn,
        tenant_id=claims.tenant_id,
        actor=f"user:{claims.sub}",
        verb="device_key_register",
        obj=f"device_key:{row.key_id}",
        meta={"platform": body.platform},
    )
    return DeviceKeyOut(**dict(row._mapping))


@router.get("/me/device-keys", response_model=list[DeviceKeyOut])
async def list_device_keys(
    conn: AsyncConnection = Depends(get_session),
) -> list[DeviceKeyOut]:
    rows = (await conn.execute(q.LIST_DEVICE_KEYS)).all()
    return [DeviceKeyOut(**dict(r._mapping)) for r in rows]


@router.post("/me/enrollment", response_model=EnrollmentOut)
async def enroll(
    body: EnrollmentIn,
    claims: Claims = Depends(require_mobile_surface),
    conn: AsyncConnection = Depends(get_session),
) -> EnrollmentOut:
    """Consume un código de alta y vincula al portador con el sitio/zona.

    El consumo es ATÓMICO (UPDATE condicional): un código expirado, agotado o
    inactivo devuelve el MISMO 404 que uno inexistente — no se filtra cuál era
    el problema ni la existencia de códigos ajenos (RLS ya oculta otros tenants).
    """
    code_row = (await conn.execute(q.CONSUME_CODE, {"code": body.code})).first()
    if code_row is None:
        raise http_error(404, "código inválido, vencido o agotado")

    try:
        await conn.execute(
            q.UPSERT_ASSIGNMENT,
            {
                "sub": claims.sub,
                "tenant": str(code_row.tenant_id),
                "site": str(code_row.site_id),
                "zone": str(code_row.zone_id) if code_row.zone_id else None,
                "role": code_row.grants_role,
            },
        )
    except IntegrityError as exc:
        raise integrity_error(exc) from exc

    site = await q.site_or_404(conn, code_row.site_id)
    assignment = await q.my_assignment(conn, claims.sub, code_row.site_id)
    await audit_async(
        conn,
        tenant_id=str(code_row.tenant_id),
        actor=f"user:{claims.sub}",
        verb="enrollment",
        obj=f"site:{code_row.site_id}",
        meta={"code": body.code, "zone_id": str(code_row.zone_id) if code_row.zone_id else None},
    )
    return EnrollmentOut(
        site_id=code_row.site_id,
        site_name=site.name,
        zone_id=code_row.zone_id,
        zone_name=assignment.zone_name if assignment else None,
        evac_policy=assignment.evac_policy if assignment else None,
        role=code_row.grants_role,
    )
