"""[T-2.109] El registro de un token DECLARA si podrá recibir algo.

``POST /me/push-tokens`` sigue aceptando ``site_id`` nulo — el contrato no
cambia: un dispositivo puede pedir permiso y registrarse antes de canjear su
código de enrolamiento. Lo que no puede es pasar por cubierto. El orquestador
elige destinatarios con ``WHERE site_id = <uuid> AND tenant_id = ... AND
revoked_at IS NULL``, y NULL no iguala a un UUID: un token sin inmueble no es
destinatario de NINGÚN sitio.

Eso tiene que quedar dicho donde se pueda leer, no deducirse. El día que
GATE-STORE (T-2.97) encienda APNs/FCM y nadie reciba nada, la primera pregunta
será cuántos teléfonos se registraron sin edificio, y la auditoría es lo único
que sobrevive a esa noche.

El aislamiento multi-tenant de ``assert_site_access`` NO se toca: un token
contra el sitio de otro tenant sigue siendo 404 (se re-verifica aquí para que
esta ficha no lo afloje sin que nadie se entere).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.main import create_app

OCC_USER = "70000000-0000-0000-0000-00000000cc01"
ZONE_PRIV = "7d000000-0000-0000-0000-0000000000d9"


@pytest.fixture(autouse=True)
def _occupants_pool(monkeypatch: pytest.MonkeyPatch):
    """Habilita el pool de ocupantes encima del entorno base (_auth_env)."""
    au.occupants_env(monkeypatch)
    deps._reset_caches()
    yield
    deps._reset_caches()


def _occ() -> str:
    return au.occupant_token(tenant=au.DB_TENANT_PRIV, user_id=OCC_USER)


async def _seed_zone_and_code(code: str = "CODE-T2109") -> None:
    engine = get_engine()
    params = {"zone": ZONE_PRIV, "tenant": au.DB_TENANT_PRIV, "site": au.DB_SITE_PRIV, "code": code}
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO zones (zone_id, tenant_id, site_id, name, level_code, evac_policy) "
                "VALUES (:zone, :tenant, :site, 'P9-A', 'P9', 'shelter') "
                "ON CONFLICT (zone_id) DO NOTHING"
            ),
            params,
        )
        await conn.execute(
            text(
                "INSERT INTO site_enrollment_codes (code, tenant_id, site_id, zone_id, active) "
                "VALUES (:code, :tenant, :site, :zone, true)"
            ),
            params,
        )


async def _audit_meta(push_token_id: str) -> dict:
    """La fila de auditoría del registro (superusuario, solo tests). Se busca por
    el ``object`` del audit trail — el token nativo es material del dispositivo y
    no tiene por qué viajar a una consulta de test."""
    engine = get_engine()
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT meta FROM audit_log WHERE verb = 'push_token_register' "
                    "AND object = :obj ORDER BY ts DESC LIMIT 1"
                ),
                {"obj": f"push_token:{push_token_id}"},
            )
        ).first()
    assert row is not None, "el registro del token no dejó auditoría"
    return row.meta


@pytest.mark.anyio
async def test_registro_con_inmueble_queda_auditado_como_alcanzable(base_data) -> None:
    await _seed_zone_and_code()
    async with au.client_for(create_app()) as client:
        headers = au.bearer(_occ())
        assert (
            await client.post("/me/enrollment", json={"code": "CODE-T2109"}, headers=headers)
        ).status_code == 200

        resp = await client.post(
            "/me/push-tokens",
            json={"platform": "android", "token": "fcm-con-sitio-109", "site_id": au.DB_SITE_PRIV},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["site_id"] == au.DB_SITE_PRIV
        token_id = resp.json()["push_token_id"]

    meta = await _audit_meta(token_id)
    assert meta["site_id"] == au.DB_SITE_PRIV
    assert meta["targetable"] is True


@pytest.mark.anyio
async def test_registro_SIN_inmueble_queda_auditado_como_INALCANZABLE(base_data) -> None:
    """Se acepta (el contrato no cambia) pero se declara: este token no recibirá
    ningún push de sitio mientras siga sin inmueble."""
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            "/me/push-tokens",
            json={"platform": "android", "token": "fcm-sin-sitio-109"},
            headers=au.bearer(_occ()),
        )
        assert resp.status_code == 201
        assert resp.json()["site_id"] is None
        token_id = resp.json()["push_token_id"]

    meta = await _audit_meta(token_id)
    assert meta["site_id"] is None
    # Lo que convierte la mina en algo detectable: la fila lo dice.
    assert meta["targetable"] is False


@pytest.mark.anyio
async def test_el_sitio_ajeno_sigue_siendo_404(base_data) -> None:
    """Regla de oro 5: esta ficha no puede aflojar ``assert_site_access``. Un
    token contra el sitio de OTRO tenant no existe para este portador."""
    async with au.client_for(create_app()) as client:
        resp = await client.post(
            "/me/push-tokens",
            json={"platform": "android", "token": "fcm-ajeno-109", "site_id": au.DB_SITE_PRIV2},
            headers=au.bearer(_occ()),
        )
        assert resp.status_code == 404
