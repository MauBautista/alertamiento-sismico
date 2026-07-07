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
