"""Utilidades de test de auth: keypair RSA de sesión, JWKS inline y make_token.

Sin Cognito real: firmamos ID tokens RS256 con una clave de sesión y verificamos
contra un ``StaticJWKS`` construido de su clave pública (``AUTH_JWKS_JSON``).
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from takab_api.settings import Settings

ISSUER = "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_TESTPOOL"
AUDIENCE = "test-client-id"
KID = "test-key"
TENANT_A = "11111111-1111-1111-1111-111111111111"  # claim de token (no se commitea)

# UUIDs dedicados a filas COMMITEADAS por los tests async de fase B. Prefijo 7 →
# nunca colisionan con los UUID fijos del conftest sync de T-1.16 (1/2/3/9/a/b/c)
# ni con los de test_db_session (d/5). Patrón: mismo criterio que test_db_session.
DB_TENANT_PRIV = "71111111-1111-1111-1111-111111111111"  # private
DB_TENANT_PRIV2 = "72222222-2222-2222-2222-222222222222"  # private (fuga cross-tenant)
DB_TENANT_GOV = "73333333-3333-3333-3333-333333333333"  # gov_shared
DB_TENANT_AGENCY = "79999999-9999-9999-9999-999999999999"  # agencia gov (no es tenant cliente)
DB_SITE_PRIV = "7a000000-0000-0000-0000-0000000000a1"
DB_SITE_PRIV2 = "7b000000-0000-0000-0000-0000000000b1"
DB_SITE_GOV = "7c000000-0000-0000-0000-0000000000c1"

# Clave que firma los tokens válidos (su pública va al JWKS).
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
# Clave ajena para tokens con firma inválida (mismo kid, pública distinta).
_WRONG_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks_json(kid: str = KID) -> str:
    """JWKS ``{"keys": [...]}`` con la clave pública de sesión."""
    jwk = json.loads(RSAAlgorithm.to_jwk(_KEY.public_key()))
    jwk.update(kid=kid, use="sig", alg="RS256")
    return json.dumps({"keys": [jwk]})


def dev_private_key_pem() -> str:
    """PEM PKCS8 de la clave de sesión (para ``TAKAB_API_AUTH_DEV_PRIVATE_KEY``).

    Su pública ya está en ``jwks_json``; ``/dev/token`` firma con ella y
    ``decode_verify`` valida contra el mismo JWKS.
    """
    from cryptography.hazmat.primitives import serialization

    return _KEY.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def test_settings(**over: Any) -> Settings:
    """Settings con issuer/audience/JWKS inline de test."""
    values: dict[str, Any] = {
        "auth_issuer": ISSUER,
        "auth_audience": AUDIENCE,
        "auth_jwks_json": jwks_json(),
    }
    values.update(over)
    return Settings(**values)


def _base_claims(
    role: str,
    *,
    tenant: str = TENANT_A,
    site_scope: str = "*",
    user_id: str | None = None,
    surface: str = "web",
    zone_id: str = "",
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    token_use: str = "id",
    iat_delta: int = 0,
    nbf_delta: int = 0,
    exp_delta: int = 3600,
    **over: Any,
) -> dict[str, Any]:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": user_id or str(uuid.uuid4()),
        "iss": issuer,
        "aud": audience,
        "token_use": token_use,
        "iat": now + iat_delta,
        "nbf": now + nbf_delta,
        "exp": now + exp_delta,
        "cognito:groups": [role],
        "custom:role": role,
        "custom:tenant_id": tenant,
        "custom:site_scope": site_scope,
        "custom:surface": surface,
        "custom:zone_id": zone_id,
    }
    claims.update(over)
    return claims


def make_token(role: str, *, key: rsa.RSAPrivateKey = _KEY, kid: str = KID, **over: Any) -> str:
    """ID token RS256 válido (kid=test-key), con overrides de claims."""
    claims = _base_claims(role, **over)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def expired_token(role: str = "soc_operator", **over: Any) -> str:
    return make_token(role, iat_delta=-7200, nbf_delta=-7200, exp_delta=-3600, **over)


def badsig_token(role: str = "soc_operator", **over: Any) -> str:
    return make_token(role, key=_WRONG_KEY, **over)


def wrongiss_token(role: str = "soc_operator", **over: Any) -> str:
    return make_token(role, issuer="https://wrong.example/pool", **over)


def wrongaud_token(role: str = "soc_operator", **over: Any) -> str:
    return make_token(role, audience="wrong-client-id", **over)


def access_token(role: str = "soc_operator", **over: Any) -> str:
    return make_token(role, token_use="access", **over)


def _b64(data: dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def none_token(role: str = "soc_operator", **over: Any) -> str:
    """Token sin firma (alg=none) — debe rechazarse antes de decodificar."""
    header = {"alg": "none", "typ": "JWT", "kid": KID}
    return f"{_b64(header)}.{_b64(_base_claims(role, **over))}."


def bearer(token: str) -> dict[str, str]:
    """Header ``Authorization: Bearer <token>`` para las peticiones de test."""
    return {"Authorization": f"Bearer {token}"}


def client_for(app: Any) -> Any:
    """``httpx.AsyncClient`` sobre el transporte ASGI de ``app`` (sin red real)."""
    import httpx

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
