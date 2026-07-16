"""T-2.03 · Dual-issuer con ANCLA pool→rol (decisión #7, specs/cognito-pool-v1 §5.2).

Dos pools de Cognito: el principal (mfa=ON, roles no-occupant) y el de
ocupantes (mfa=OPTIONAL, SOLO occupant). La API valida ambos issuers y ancla:
un token del pool de ocupantes solo puede portar ``role=occupant``; un
``occupant`` solo puede venir de ese pool. El cruce en cualquier dirección es
401. Con el pool de ocupantes SIN configurar, el comportamiento single-issuer
histórico queda intacto (los tests viejos que acuñan occupant contra el issuer
principal no se tocan).

``GET /me`` no toca la DB → endpoint perfecto para ejercitar solo la capa auth.
"""

from __future__ import annotations

import pytest

import auth_utils as au
from takab_api.auth import deps
from takab_api.main import create_app


@pytest.fixture
def _env_dual(monkeypatch: pytest.MonkeyPatch):
    """App con AMBOS pools habilitados (JWKS compartido, claves de test)."""
    monkeypatch.setenv("TAKAB_API_AUTH_ISSUER", au.ISSUER)
    monkeypatch.setenv("TAKAB_API_AUTH_AUDIENCE", au.AUDIENCE)
    monkeypatch.setenv("TAKAB_API_AUTH_JWKS_JSON", au.jwks_json())
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


@pytest.fixture
def _env_single(monkeypatch: pytest.MonkeyPatch):
    """App SIN pool de ocupantes (compat: single-issuer histórico)."""
    monkeypatch.setenv("TAKAB_API_AUTH_ISSUER", au.ISSUER)
    monkeypatch.setenv("TAKAB_API_AUTH_AUDIENCE", au.AUDIENCE)
    monkeypatch.setenv("TAKAB_API_AUTH_JWKS_JSON", au.jwks_json())
    monkeypatch.delenv("TAKAB_API_AUTH_OCCUPANTS_ISSUER", raising=False)
    monkeypatch.delenv("TAKAB_API_AUTH_OCCUPANTS_AUDIENCE", raising=False)
    deps._reset_caches()
    yield
    deps._reset_caches()


async def _me(token: str):
    async with au.client_for(create_app()) as client:
        return await client.get("/me", headers=au.bearer(token))


@pytest.mark.anyio
async def test_occupant_del_pool_de_ocupantes_entra(_env_dual) -> None:
    resp = await _me(au.occupant_token())
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "occupant"
    assert body["surface"] == "mobile"
    # default-deny real del occupant: su alcance móvil se resuelve server-side (R2)
    assert body["site_scope"] == []
    assert body["allowed_actions"]["checkin_submit"] is True
    assert body["allowed_actions"]["panic_vote"] is True
    assert body["allowed_actions"]["siren_silence"] is False


@pytest.mark.anyio
async def test_occupant_del_pool_principal_es_401(_env_dual) -> None:
    """Con el pool de ocupantes HABILITADO, un occupant acuñado por el issuer
    principal es un cruce (alta en el pool equivocado o token forjado)."""
    resp = await _me(au.make_token("occupant", surface="mobile"))
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_rol_tactico_del_pool_de_ocupantes_es_401(_env_dual) -> None:
    """El pool de ocupantes SOLO emite occupant: un brigadista ahí es cruce."""
    token = au.make_token(
        "brigadista", issuer=au.OCC_ISSUER, audience=au.OCC_AUDIENCE, surface="mobile"
    )
    resp = await _me(token)
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_tactico_del_pool_principal_sigue_entrando(_env_dual) -> None:
    resp = await _me(au.make_token("brigadista", surface="mobile"))
    assert resp.status_code == 200
    assert resp.json()["allowed_actions"]["siren_silence"] is True


@pytest.mark.anyio
async def test_audiencia_equivocada_en_pool_de_ocupantes_es_401(_env_dual) -> None:
    """El enrutado por iss NO relaja la verificación dura: aud del pool exacto."""
    token = au.make_token("occupant", issuer=au.OCC_ISSUER, audience=au.AUDIENCE)
    resp = await _me(token)
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_sin_pool_de_ocupantes_el_single_issuer_queda_intacto(_env_single) -> None:
    """Compat: sin segundo pool, occupant por el issuer principal sigue entrando
    (suites históricas) y el issuer de ocupantes es simplemente inválido."""
    resp = await _me(au.make_token("occupant", surface="mobile"))
    assert resp.status_code == 200

    resp = await _me(au.occupant_token())
    assert resp.status_code == 401
