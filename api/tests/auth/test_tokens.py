"""decode_verify: token válido → claims; inválidos → AuthError 401."""

from __future__ import annotations

import pytest

import auth_utils as au
from takab_api.auth import decode_verify, select_jwks
from takab_api.auth.tokens import AuthError


@pytest.fixture
def settings() -> object:
    return au.test_settings()


@pytest.fixture
def jwks(settings: object) -> object:
    return select_jwks(settings)


def test_valid_token_returns_claims(settings: object, jwks: object) -> None:
    token = au.make_token("soc_operator", tenant=au.TENANT_A, site_scope="*")
    claims = decode_verify(token, settings, jwks)
    assert claims["custom:role"] == "soc_operator"
    assert claims["custom:tenant_id"] == au.TENANT_A
    assert claims["token_use"] == "id"


@pytest.mark.parametrize(
    "factory",
    [
        au.expired_token,
        au.badsig_token,
        au.wrongiss_token,
        au.wrongaud_token,
        au.access_token,
        au.none_token,
    ],
)
def test_invalid_tokens_raise_401(settings: object, jwks: object, factory) -> None:
    with pytest.raises(AuthError) as excinfo:
        decode_verify(factory(), settings, jwks)
    assert excinfo.value.status == 401
    assert excinfo.value.reason


def test_access_token_rejected_for_token_use(settings: object, jwks: object) -> None:
    # Un access token pasa firma/iss/aud pero falla en token_use=='id'.
    with pytest.raises(AuthError) as excinfo:
        decode_verify(au.access_token(), settings, jwks)
    assert "token_use" in excinfo.value.reason


def test_none_alg_rejected(settings: object, jwks: object) -> None:
    with pytest.raises(AuthError) as excinfo:
        decode_verify(au.none_token(), settings, jwks)
    assert "alg" in excinfo.value.reason


def test_unknown_kid_rejected(settings: object, jwks: object) -> None:
    token = au.make_token("soc_operator", kid="other-kid")
    with pytest.raises(AuthError):
        decode_verify(token, settings, jwks)


# --- Audience múltiple: el pool principal lo comparten el cliente web y el móvil.
# (Regresión: los tests históricos acuñaban el token móvil con el MISMO audience
# que el web, así que nunca ejercieron un cliente móvil con `aud` distinto — el
# hueco por el que el login móvil recibía 401 "invalid audience".)

_MOBILE_AUD = "test-mobile-tactical-client"


def test_multi_audience_accepts_each_listed_client(jwks: object) -> None:
    s = au.test_settings(auth_audience=f"{au.AUDIENCE},{_MOBILE_AUD}")
    web = au.make_token("soc_operator", audience=au.AUDIENCE)
    mobile = au.make_token("brigadista", surface="mobile", audience=_MOBILE_AUD)
    assert decode_verify(web, s, jwks)["custom:role"] == "soc_operator"
    assert decode_verify(mobile, s, jwks)["custom:role"] == "brigadista"


def test_multi_audience_still_rejects_unlisted_client(jwks: object) -> None:
    s = au.test_settings(auth_audience=f"{au.AUDIENCE},{_MOBILE_AUD}")
    with pytest.raises(AuthError) as excinfo:
        decode_verify(au.make_token("soc_operator", audience="otro-client"), s, jwks)
    assert "audience" in excinfo.value.reason


def test_single_audience_unchanged(jwks: object) -> None:
    # Un valor único sigue comportándose EXACTO (compatibilidad hacia atrás).
    s = au.test_settings(auth_audience=au.AUDIENCE)
    assert decode_verify(au.make_token("soc_operator"), s, jwks)["custom:role"] == "soc_operator"
    with pytest.raises(AuthError):
        decode_verify(au.make_token("soc_operator", audience=_MOBILE_AUD), s, jwks)
