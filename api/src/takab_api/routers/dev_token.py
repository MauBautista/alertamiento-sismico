"""POST /dev/token — firma un ID token de prueba SIN Cognito (SOLO dev/test).

Guardado por ``main.create_app``: solo se monta cuando ``settings.auth_jwks_json``
no está vacío (señal de entorno dev/test con JWKS inline). En producción el JWKS
es remoto (``auth_jwks_url``) y ``auth_jwks_json`` queda vacío → el endpoint NO
existe. Firma con ``auth_dev_private_key`` (PEM); su ``kid`` sale del JWKS inline
para que ``decode_verify`` valide contra la misma clave. Sirve al frontend/pruebas
para obtener tokens sin el flujo PKCE real.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from takab_api.settings import Settings

router = APIRouter()


class DevTokenRequest(BaseModel):
    """Claims mínimos para forjar un ID token de prueba."""

    role: str
    tenant_id: str
    site_scope: str = "*"
    surface: str = "web"
    zone_id: str = ""
    sub: str | None = None
    groups: list[str] | None = None
    expires_in: int = Field(default=3600, gt=0, le=86400)


class DevTokenResponse(BaseModel):
    id_token: str
    token_use: str = "id"
    expires_in: int


def _dev_kid(jwks_json: str) -> str:
    keys = json.loads(jwks_json).get("keys", [])
    if not keys or not keys[0].get("kid"):
        raise HTTPException(status_code=503, detail="JWKS de dev sin kid")
    return str(keys[0]["kid"])


@router.post("/dev/token", response_model=DevTokenResponse)
def dev_token(body: DevTokenRequest) -> DevTokenResponse:
    settings = Settings()
    if not settings.auth_dev_private_key:
        raise HTTPException(status_code=503, detail="clave de firma dev no configurada")

    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": body.sub or str(uuid.uuid4()),
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
        "token_use": "id",
        "iat": now,
        "nbf": now,
        "exp": now + body.expires_in,
        "cognito:groups": body.groups if body.groups is not None else [body.role],
        "custom:role": body.role,
        "custom:tenant_id": body.tenant_id,
        "custom:site_scope": body.site_scope,
        "custom:surface": body.surface,
        "custom:zone_id": body.zone_id,
    }
    kid = _dev_kid(settings.auth_jwks_json)
    id_token = jwt.encode(
        claims, settings.auth_dev_private_key, algorithm="RS256", headers={"kid": kid}
    )
    return DevTokenResponse(id_token=id_token, expires_in=body.expires_in)
