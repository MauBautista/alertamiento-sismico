"""/dev/token: montado SOLO con JWKS inline (dev/test), jamás en prod (G7).

En dev firma un ID token que ``/me`` acepta; en prod (auth_jwks_json vacío) el
endpoint no existe → 404.
"""

from __future__ import annotations

import pytest

import auth_utils as au
from takab_api.main import create_app


async def test_dev_token_mounted_and_roundtrips() -> None:
    app = create_app()  # entorno dev: auth_jwks_json presente (fijado por _auth_env)
    async with au.client_for(app) as client:
        resp = await client.post(
            "/dev/token",
            json={"role": "soc_operator", "tenant_id": au.TENANT_A, "site_scope": "*"},
        )
        assert resp.status_code == 200, resp.text
        token = resp.json()["id_token"]

        me = await client.get("/me", headers=au.bearer(token))
        assert me.status_code == 200
        assert me.json()["role"] == "soc_operator"
        assert me.json()["tenant_id"] == au.TENANT_A


async def test_dev_token_not_mounted_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_AUTH_JWKS_JSON", "")  # prod usa JWKS remoto
    app = create_app()
    async with au.client_for(app) as client:
        resp = await client.post(
            "/dev/token", json={"role": "soc_operator", "tenant_id": au.TENANT_A}
        )
        assert resp.status_code == 404


# --- [T-8.02 · D-38] el token forjado declara SIEMPRE su hora de login ----------

_DAY = 86_400


def _payload(token: str) -> dict:
    import jwt

    return jwt.decode(token, options={"verify_signature": False})


async def _forge(client, **extra) -> tuple[int, dict]:
    body = {"role": "soc_operator", "tenant_id": au.TENANT_A, "site_scope": "*", **extra}
    resp = await client.post("/dev/token", json=body)
    return resp.status_code, resp.json()


async def test_dev_token_lleva_auth_time_por_defecto() -> None:
    """Sin ``auth_time`` la API lo rechaza: un /dev/token que no lo pusiera dejaría a
    toda la consola local y a los E2E en 401."""
    async with au.client_for(create_app()) as client:
        status, body = await _forge(client)
    assert status == 200, body
    claims = _payload(body["id_token"])
    assert claims["auth_time"] == claims["iat"]


async def test_dev_token_auth_age_s_retrasa_el_login() -> None:
    async with au.client_for(create_app()) as client:
        status, body = await _forge(client, auth_age_s=3_600)
    assert status == 200, body
    claims = _payload(body["id_token"])
    assert claims["auth_time"] == claims["iat"] - 3_600


async def test_dev_token_puede_fabricar_una_sesion_caducada(db_engine) -> None:
    """Es para lo que existe el parámetro: ensayar el «RENOVAR AHORA» y el corte
    sin esperar un día."""
    async with au.client_for(create_app()) as client:
        status, body = await _forge(client, auth_age_s=_DAY + 1)
        assert status == 200, body
        me = await client.get("/me", headers=au.bearer(body["id_token"]))
    assert me.status_code == 401
    assert me.json() == {"detail": "sesion_expirada"}


@pytest.mark.parametrize("edad", [-1, 100 * _DAY + 1])
async def test_dev_token_auth_age_s_fuera_de_rango_es_422(edad: int) -> None:
    async with au.client_for(create_app()) as client:
        status, _ = await _forge(client, auth_age_s=edad)
    assert status == 422


async def test_dev_token_auth_age_s_admite_el_tope_de_100_dias() -> None:
    """Un ocupante vive 90 d: el rango tiene que poder pasarse de su tope."""
    async with au.client_for(create_app()) as client:
        status, body = await _forge(client, auth_age_s=100 * _DAY)
    assert status == 200, body
