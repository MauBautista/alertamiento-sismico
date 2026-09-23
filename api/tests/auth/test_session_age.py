"""T-8.02 · D-38 — tope ABSOLUTO de sesión contado desde el login real.

Cognito fija la vida del refresh token **por app client**, no por rol, así que
«brigadista 30 d / SOC 24 h» no se puede decir en Cognito: lo dice la API. La
cuenta arranca en ``auth_time`` —la hora en que la persona tecleó contraseña y
código—, que el refresco NO renueva. ``iat`` sí se renueva en cada refresco y por
eso **no** sirve de sustituto: con ``iat`` la sesión no caducaría nunca.

Contrato fijo entre carriles (no cambiar sin mover web/móvil a la vez):

- REST, sesión caducada ⇒ ``401`` · ``{"detail": "sesion_expirada"}`` ·
  ``WWW-Authenticate: Bearer error="invalid_token", error_description="sesion_expirada"``.
  Cualquier otro 401 conserva su forma (``WWW-Authenticate: Bearer``).
- ``GET /me`` publica ``session_expires_at`` y ``session_max_age_s``.
"""

from __future__ import annotations

import time
from datetime import datetime

import pytest
from fastapi import Depends, FastAPI

import auth_utils as au
from takab_api.auth import deps
from takab_api.auth.claims import Claims
from takab_api.auth.jwks import select_jwks
from takab_api.auth.matrix import ROLE_ACTION_MATRIX, ROLE_ROUTE_MATRIX, SESSION_MAX_AGE_S
from takab_api.auth.mfa import require_mfa
from takab_api.auth.session_age import (
    SESSION_EXPIRED,
    SessionExpired,
    enforce_session_age,
    session_deadline,
)
from takab_api.auth.tokens import AuthError, decode_verify

DAY = 86_400

#: D-38 tal como la tomó Mauricio. Copia A MANO a propósito: si alguien cambia la
#: tabla de ``matrix.py`` sin pasar por la decisión, este test se pone rojo.
D38 = {
    "brigadista": 30 * DAY,
    "inspector": 30 * DAY,
    "occupant": 90 * DAY,
    "takab_superadmin": DAY,
    "takab_support": DAY,
    "tenant_admin": DAY,
    "soc_operator": DAY,
    "gov_operator": DAY,
    "building_admin": DAY,
    "security_guard": DAY,
}

SESSION_CHALLENGE = 'Bearer error="invalid_token", error_description="sesion_expirada"'


# --- la tabla -------------------------------------------------------------------


def test_censo_el_tope_cubre_EXACTAMENTE_los_roles_de_la_matriz() -> None:
    """Un rol nuevo en la matriz sin tope sería default-deny (401 perpetuo); un tope
    de un rol que ya no existe es basura que alguien acabará leyendo como vigente."""
    assert set(SESSION_MAX_AGE_S) == set(ROLE_ROUTE_MATRIX)
    assert set(SESSION_MAX_AGE_S) == set(ROLE_ACTION_MATRIX)


def test_los_valores_son_los_de_D38() -> None:
    assert SESSION_MAX_AGE_S == D38
    assert all(isinstance(v, int) and v > 0 for v in SESSION_MAX_AGE_S.values())


# --- la regla, sin HTTP ---------------------------------------------------------


def _claims(role: str, auth_time: int) -> Claims:
    return Claims(
        sub="u",
        groups=(role,),
        tenant_id=au.TENANT_A,
        role=role,
        site_scope=frozenset(),
        zone_id="",
        surface="web",
        auth_time=auth_time,
    )


def test_el_plazo_es_auth_time_mas_el_tope_del_rol() -> None:
    assert session_deadline(_claims("soc_operator", 1_000)) == 1_000 + DAY
    assert session_deadline(_claims("brigadista", 1_000)) == 1_000 + 30 * DAY
    assert session_deadline(_claims("occupant", 1_000)) == 1_000 + 90 * DAY


def test_el_limite_es_cerrado_en_el_instante_del_plazo() -> None:
    """``now >= deadline`` ⇒ caducada: en el segundo exacto ya no hay sesión."""
    c = _claims("soc_operator", 1_000)
    enforce_session_age(c, now=1_000 + DAY - 1)  # un segundo antes: vale
    with pytest.raises(SessionExpired):
        enforce_session_age(c, now=1_000 + DAY)


def test_rol_desconocido_es_caducado_default_deny() -> None:
    c = _claims("rol_que_no_existe", int(time.time()))
    assert session_deadline(c) is None
    with pytest.raises(SessionExpired):
        enforce_session_age(c, now=time.time())


def test_la_caducidad_es_un_AuthError_401_con_su_motivo() -> None:
    """Es un error de AUTENTICACIÓN del módulo (mismo manejo que el resto)."""
    exc = SessionExpired()
    assert isinstance(exc, AuthError)
    assert exc.status == 401
    assert exc.reason == SESSION_EXPIRED == "sesion_expirada"


# --- el token -------------------------------------------------------------------


def test_decode_exige_auth_time() -> None:
    settings = au.test_settings()
    with pytest.raises(AuthError):
        decode_verify(
            au.make_token("soc_operator", drop=("auth_time",)), settings, select_jwks(settings)
        )


@pytest.mark.parametrize("valor", ["1700000000", True, 1.5e300])
def test_auth_time_que_no_es_un_entero_razonable_es_401(valor: object) -> None:
    settings = au.test_settings()
    verified = decode_verify(
        au.make_token("soc_operator", auth_time=valor), settings, select_jwks(settings)
    )
    with pytest.raises(AuthError):
        Claims.from_verified(verified)


def test_from_verified_puebla_auth_time_y_NO_usa_iat() -> None:
    settings = au.test_settings()
    verified = decode_verify(
        au.make_token("soc_operator", auth_age=5_000), settings, select_jwks(settings)
    )
    claims = Claims.from_verified(verified)
    assert claims.auth_time == verified["auth_time"]
    assert claims.auth_time == verified["iat"] - 5_000


def test_un_auth_time_POSTERIOR_a_iat_no_alarga_la_sesion() -> None:
    """Nadie se autentica después de que le emitan el token. Un ``auth_time`` futuro
    empujaría el plazo hacia adelante; se recorta a ``iat`` (acorta, jamás alarga)."""
    settings = au.test_settings()
    verified = decode_verify(
        au.make_token("soc_operator", auth_age=-10 * DAY), settings, select_jwks(settings)
    )
    claims = Claims.from_verified(verified)
    assert claims.auth_time == verified["iat"]


# --- por HTTP: el contrato ------------------------------------------------------


async def _me(client, token: str):
    return await client.get("/me", headers=au.bearer(token))


def _assert_expired(resp) -> None:
    assert resp.status_code == 401, resp.text
    assert resp.json() == {"detail": "sesion_expirada"}
    assert resp.headers.get("WWW-Authenticate") == SESSION_CHALLENGE


async def test_soc_operator_un_segundo_pasado_el_dia_es_401_sesion_expirada(
    client, db_engine
) -> None:
    _assert_expired(await _me(client, au.make_token("soc_operator", auth_age=DAY + 1)))


def _freeze_check_clock(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    """Fija el reloj con el que ``get_claims`` mide la sesión al ``iat`` del token.

    Con 86 399 s de sesión consumidos queda UN segundo de margen, y entre acuñar el
    token y comprobarlo puede cruzarse la frontera del segundo: sin esto la prueba
    del borde sería una moneda al aire. Solo se congela el reloj del tope (el
    ``exp`` lo sigue midiendo PyJWT con el suyo).
    """
    import types

    import jwt

    iat = jwt.decode(token, options={"verify_signature": False})["iat"]
    monkeypatch.setattr(deps, "time", types.SimpleNamespace(time=lambda: float(iat)))


async def test_soc_operator_un_segundo_antes_del_dia_entra(
    client, db_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = au.make_token("soc_operator", auth_age=DAY - 1)
    _freeze_check_clock(monkeypatch, token)
    resp = await _me(client, token)
    assert resp.status_code == 200, resp.text


async def test_soc_operator_en_el_segundo_exacto_del_dia_ya_no_entra(
    client, db_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = au.make_token("soc_operator", auth_age=DAY)
    _freeze_check_clock(monkeypatch, token)
    _assert_expired(await _me(client, token))


@pytest.mark.parametrize(
    "role", ["takab_superadmin", "tenant_admin", "gov_operator", "building_admin"]
)
async def test_los_demas_roles_de_consola_tambien_24h(client, db_engine, role: str) -> None:
    _assert_expired(await _me(client, au.make_token(role, auth_age=DAY + 1)))


async def test_brigadista_29_dias_entra_y_31_no(client, db_engine) -> None:
    ok = await _me(client, au.make_token("brigadista", surface="mobile", auth_age=29 * DAY))
    assert ok.status_code == 200, ok.text
    _assert_expired(
        await _me(client, au.make_token("brigadista", surface="mobile", auth_age=31 * DAY))
    )


async def test_inspector_29_dias_entra_y_31_no(client, db_engine) -> None:
    ok = await _me(client, au.make_token("inspector", auth_age=29 * DAY))
    assert ok.status_code == 200, ok.text
    _assert_expired(await _me(client, au.make_token("inspector", auth_age=31 * DAY)))


async def test_occupant_del_pool_de_ocupantes_89_dias_entra_y_91_no(
    monkeypatch: pytest.MonkeyPatch, db_engine
) -> None:
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    from takab_api.main import create_app

    async with au.client_for(create_app()) as client:
        ok = await _me(client, au.occupant_token(auth_age=89 * DAY))
        assert ok.status_code == 200, ok.text
        assert ok.json()["role"] == "occupant"
        _assert_expired(await _me(client, au.occupant_token(auth_age=91 * DAY)))


async def test_token_sin_auth_time_es_401_generico(client, db_engine) -> None:
    """Sin ``auth_time`` no hay de dónde contar: se rechaza. Y NO es «sesión
    expirada» — no sabemos cuándo empezó; el 401 conserva su forma de siempre."""
    resp = await _me(client, au.make_token("soc_operator", drop=("auth_time",)))
    assert resp.status_code == 401
    assert resp.json()["detail"] != "sesion_expirada"
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


async def test_los_demas_401_conservan_su_forma(client, db_engine) -> None:
    """El reto especial es SOLO para la sesión caducada: un token vencido (renovable)
    sigue diciendo ``Bearer`` a secas — el cliente lo distingue por eso."""
    resp = await _me(client, au.expired_token("soc_operator"))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "token expired"
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


async def test_me_publica_el_plazo_coherente(client, db_engine) -> None:
    antes = int(time.time())
    resp = await _me(client, au.make_token("soc_operator", auth_age=3_600))
    despues = int(time.time())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session_max_age_s"] == DAY
    fin = datetime.fromisoformat(body["session_expires_at"].replace("Z", "+00:00"))
    assert fin.utcoffset() is not None and fin.utcoffset().total_seconds() == 0
    # auth_time = emisión − 3600 ⇒ plazo = emisión + 23 h (± el segundo de la prueba)
    assert antes - 3_600 + DAY <= fin.timestamp() <= despues - 3_600 + DAY


async def test_me_de_un_brigadista_publica_30_dias(client, db_engine) -> None:
    resp = await _me(client, au.make_token("brigadista", surface="mobile"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["session_max_age_s"] == 30 * DAY


# --- orden frente a la guarda de MFA (regla de oro 8) ---------------------------


def _mfa_app() -> FastAPI:
    """Ruta mínima con la MISMA composición que el camino de comando."""
    app = FastAPI()
    guard = deps.require_roles("occupant", "soc_operator", inner=require_mfa(deps.get_claims))

    @app.get("/probe")
    def probe(claims: Claims = Depends(guard)) -> dict[str, str]:
        return {"role": claims.role}

    return app


async def test_sesion_caducada_es_401_ANTES_que_el_403_de_MFA(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    async with au.client_for(_mfa_app()) as client:
        # Del pool SIN MFA y fresco ⇒ la guarda de MFA lo para (403): intacta.
        fresco = await client.get("/probe", headers=au.bearer(au.occupant_token()))
        assert fresco.status_code == 403
        # Del pool sin MFA y caducado ⇒ ni siquiera llega a la guarda de MFA.
        viejo = await client.get("/probe", headers=au.bearer(au.occupant_token(auth_age=91 * DAY)))
        _assert_expired(viejo)
        # Del pool CON MFA y fresco ⇒ pasa.
        ok = await client.get("/probe", headers=au.bearer(au.make_token("soc_operator")))
        assert ok.status_code == 200
