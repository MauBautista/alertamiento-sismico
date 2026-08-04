"""T-2.36 · Retirar una estación exige doble fricción.

Retirar un gabinete apaga la protección sísmica de un edificio: deja de recibir
config firmada y de ser destinatario de comandos de actuación. Un clic no basta.

Dos factores independientes:
1. Teclear el identificador exacto del objeto (``serial`` del gabinete, ``code`` del
   sitio). No es secreto — está en pantalla — y por eso se comprueba PRIMERO: un
   dedazo no debe quemar un intento del segundo factor.
2. El **código de retiro del tenant**, que TAKAB entrega fuera de banda y solo el
   superadmin rota. Se guarda hasheado con bcrypt en Postgres (``pgcrypto``) y jamás
   sale de la base: la verificación entra por función ``SECURITY DEFINER``.

Fail-closed: un tenant sin código configurado NO puede retirar (409). La ausencia de
credencial nunca es un bypass.
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.routers.fleet import router as fleet_router
from takab_api.routers.sites import router as sites_router
from takab_api.routers.tenants import router as tenants_router

# Prefijo 4: libre (1/2/3/9/a/b/c sync, 7 async, 8 B1, 6 fleet_admin, 5 ghosts).
T_A = "41111111-1111-1111-1111-111111111111"
T_B = "42222222-2222-2222-2222-222222222222"
S_A = "4a000000-0000-0000-0000-0000000000a1"
S_B = "4b000000-0000-0000-0000-0000000000b1"
G_A = "4d000000-0000-0000-0000-0000000000d1"
G_B = "4d000000-0000-0000-0000-0000000000d2"

CODE = "TAKAB-RETIRO-2026"
SERIAL_A = "SN-RC-A1"
SITE_CODE_A = "TORRE-RC"

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"
_TENANTS = (T_A, T_B)
_CLEANUP = (
    text("DELETE FROM tenant_retire_codes WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM gateways WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM sites WHERE tenant_id = ANY(:t)"),
    text("TRUNCATE audit_log"),
    text("DELETE FROM tenants WHERE tenant_id = ANY(:t)"),
)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_AUTH_ISSUER", au.ISSUER)
    monkeypatch.setenv("TAKAB_API_AUTH_AUDIENCE", au.AUDIENCE)
    monkeypatch.setenv("TAKAB_API_AUTH_JWKS_JSON", au.jwks_json())
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        monkeypatch.setenv("TAKAB_API_DATABASE_URL", dsn)
    deps._reset_caches()
    get_engine.cache_clear()
    yield
    deps._reset_caches()


async def _cleanup() -> None:
    async with get_engine().begin() as conn:
        for stmt in _CLEANUP:
            await conn.execute(stmt, {"t": list(_TENANTS)})


@pytest.fixture
async def seed() -> None:
    """Dos tenants con un sitio y un gabinete cada uno. SIN código configurado."""
    await _cleanup()
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code in ((T_A, "RC_A"), (T_B, "RC_B")):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) "
                    "VALUES (:id, :code, 'T-2.36', 'private')"
                ),
                {"id": tid, "code": code},
            )
        for sid, tid, code in ((S_A, T_A, SITE_CODE_A), (S_B, T_B, "AJENA-RC")):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM})"
                ),
                {"sid": sid, "tid": tid, "code": code},
            )
        for gid, tid, sid, serial in ((G_A, T_A, S_A, SERIAL_A), (G_B, T_B, S_B, "SN-RC-B1")):
            await conn.execute(
                text(
                    "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) "
                    "VALUES (:g, :t, :s, :sn)"
                ),
                {"g": gid, "t": tid, "s": sid, "sn": serial},
            )
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(sites_router)
    app.include_router(fleet_router)
    app.include_router(tenants_router)
    return app


def _tok(role: str = "tenant_admin", tenant: str = T_A) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _post(path: str, body: dict, token: dict[str, str] | None = None):
    async with au.client_for(_app()) as c:
        return await c.post(path, json=body, headers=token or _tok())


async def _put(path: str, body: dict, token: dict[str, str] | None = None):
    async with au.client_for(_app()) as c:
        return await c.put(path, json=body, headers=token or _tok())


async def _get(path: str, token: dict[str, str] | None = None):
    async with au.client_for(_app()) as c:
        return await c.get(path, headers=token or _tok())


async def _set_code(tenant: str = T_A, code: str = CODE) -> None:
    """Rota el código como superadmin (única vía: el hash lo calcula la DB)."""
    resp = await _put(
        f"/tenants/{tenant}/retire-code",
        {"code": code},
        _tok("takab_superadmin", tenant=tenant),
    )
    assert resp.status_code == 200, resp.text


async def _audit(verb: str) -> list[dict]:
    async with get_engine().connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT object, meta::text FROM audit_log WHERE verb = :v ORDER BY audit_id"),
                {"v": verb},
            )
        ).all()
    return [{"object": r.object, "meta": r[1]} for r in rows]


def _retire_gw(**over) -> dict:
    return {"confirm_serial": SERIAL_A, "retire_code": CODE} | over


# ---- rotación del código -----------------------------------------------------


async def test_solo_el_superadmin_rota_el_codigo(seed: None) -> None:
    """El código lo entrega TAKAB, no el cliente: un tenant_admin no se lo cambia."""
    assert (await _put(f"/tenants/{T_A}/retire-code", {"code": CODE})).status_code == 403
    assert (
        await _put(f"/tenants/{T_A}/retire-code", {"code": CODE}, _tok("takab_support", tenant=T_A))
    ).status_code == 403
    assert (
        await _put(
            f"/tenants/{T_A}/retire-code", {"code": CODE}, _tok("takab_superadmin", tenant=T_A)
        )
    ).status_code == 200


async def test_la_rotacion_no_devuelve_ni_el_codigo_ni_el_hash(seed: None) -> None:
    resp = await _put(
        f"/tenants/{T_A}/retire-code", {"code": CODE}, _tok("takab_superadmin", tenant=T_A)
    )
    body = resp.json()
    assert body["version"] == 1
    assert CODE not in resp.text
    assert not any("hash" in k for k in body)

    audited = await _audit("retire_code_rotate")
    assert len(audited) == 1
    assert CODE not in audited[0]["meta"], "el código jamás entra en la bitácora"


async def test_rotar_invalida_el_codigo_anterior(seed: None) -> None:
    await _set_code()
    await _set_code(code="OTRO-CODIGO-2027")

    viejo = await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw())
    assert viejo.status_code == 403

    nuevo = await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw(retire_code="OTRO-CODIGO-2027"))
    assert nuevo.status_code == 200, nuevo.text

    estado = (await _get(f"/tenants/{T_A}/retire-code")).json()
    assert estado["version"] == 2


async def test_el_estado_del_codigo_es_legible_sin_filtrar_el_hash(seed: None) -> None:
    sin = (await _get(f"/tenants/{T_A}/retire-code")).json()
    assert sin == {"tenant_id": T_A, "configured": False, "version": None, "rotated_at": None}

    await _set_code()
    con = (await _get(f"/tenants/{T_A}/retire-code")).json()
    assert con["configured"] is True
    assert con["version"] == 1
    assert con["rotated_at"] is not None
    assert set(con) == {"tenant_id", "configured", "version", "rotated_at"}


async def test_el_hash_no_es_legible_por_el_rol_de_la_api(seed: None) -> None:
    """RLS sin política de lectura para roles de tenant: ni el admin ve su hash."""
    await _set_code()
    async with get_engine().connect() as conn:
        await conn.execute(text('SET LOCAL ROLE "takab_app"'))
        await conn.execute(text("SELECT set_config('app.tenant_id', :v, true)"), {"v": T_A})
        await conn.execute(text("SELECT set_config('app.role', 'tenant_admin', true)"))
        visible = (
            await conn.execute(text("SELECT count(*) FROM tenant_retire_codes"))
        ).scalar_one()
    assert visible == 0


# ---- la doble fricción -------------------------------------------------------


async def test_sin_codigo_configurado_no_se_puede_retirar(seed: None) -> None:
    """Fail-closed: la ausencia de credencial NUNCA es un bypass."""
    resp = await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw())
    assert resp.status_code == 409, resp.text
    assert "código de retiro" in resp.json()["detail"].lower()

    async with get_engine().connect() as conn:
        status = await conn.scalar(
            text("SELECT status FROM gateways WHERE gateway_id = :g"), {"g": G_A}
        )
    assert status == "provisioned"


async def test_codigo_incorrecto_es_403_y_no_retira_nada(seed: None) -> None:
    await _set_code()
    resp = await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw(retire_code="ADIVINADO"))
    assert resp.status_code == 403, resp.text

    async with get_engine().connect() as conn:
        status = await conn.scalar(
            text("SELECT status FROM gateways WHERE gateway_id = :g"), {"g": G_A}
        )
    assert status == "provisioned"


async def test_serial_que_no_coincide_es_400_y_no_quema_un_intento(seed: None) -> None:
    """El serial está en pantalla: un dedazo no debe consumir un intento del código."""
    await _set_code()
    resp = await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw(confirm_serial="SN-EQUIVOCADO"))
    assert resp.status_code == 400, resp.text
    assert await _audit("retire_code_denied") == []


async def test_serial_y_codigo_correctos_retiran_y_auditan(seed: None) -> None:
    await _set_code()
    resp = await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw())
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "retired"

    audited = await _audit("gateway_retire")
    assert [a["object"] for a in audited] == [f"gateway:{G_A}"]
    assert CODE not in audited[0]["meta"]


async def test_el_retiro_es_idempotente(seed: None) -> None:
    await _set_code()
    first = await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw())
    again = await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw())
    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json()["status"] == "retired"


# ---- rate-limit --------------------------------------------------------------


async def test_el_intento_fallido_queda_registrado_pese_al_rollback(seed: None) -> None:
    """Sin esto el rate-limit NUNCA armaría.

    El request vive en una sola transacción: al lanzar el 403 hace rollback y la fila
    de auditoría se perdería con él. La denegación se escribe en una conexión aparte
    que sí commitea.
    """
    await _set_code()
    await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw(retire_code="MAL"))
    assert len(await _audit("retire_code_denied")) == 1


async def test_cinco_intentos_fallidos_bloquean_con_429(seed: None) -> None:
    await _set_code()
    for _ in range(5):
        resp = await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw(retire_code="MAL"))
        assert resp.status_code == 403

    bloqueado = await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw(retire_code="MAL"))
    assert bloqueado.status_code == 429, bloqueado.text

    # Y el código BUENO tampoco pasa mientras dura el bloqueo: si no, bastaría con
    # agotar los intentos para saber que el sexto es el correcto.
    con_codigo_bueno = await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw())
    assert con_codigo_bueno.status_code == 429


async def test_el_bloqueo_de_un_tenant_no_alcanza_a_otro(seed: None) -> None:
    await _set_code(T_A)
    await _set_code(T_B, code="CODIGO-B")
    for _ in range(6):
        await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw(retire_code="MAL"))

    otro = await _post(
        f"/fleet/gateways/{G_B}/retire",
        {"confirm_serial": "SN-RC-B1", "retire_code": "CODIGO-B"},
        _tok("tenant_admin", tenant=T_B),
    )
    assert otro.status_code == 200, otro.text


# ---- sitios ------------------------------------------------------------------


async def test_retirar_un_sitio_exige_su_code_y_el_codigo_del_tenant(seed: None) -> None:
    await _set_code()

    sin_codigo = await _post(
        f"/sites/{S_A}/retire", {"confirm_code": SITE_CODE_A, "retire_code": "MAL"}
    )
    assert sin_codigo.status_code == 403

    mal_code = await _post(f"/sites/{S_A}/retire", {"confirm_code": "OTRO", "retire_code": CODE})
    assert mal_code.status_code == 400

    ok = await _post(f"/sites/{S_A}/retire", {"confirm_code": SITE_CODE_A, "retire_code": CODE})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "retired"

    # Y sigue propagando a los gabinetes (T-2.35).
    async with get_engine().connect() as conn:
        status = await conn.scalar(
            text("SELECT status FROM gateways WHERE gateway_id = :g"), {"g": G_A}
        )
    assert status == "retired"


# ---- autorización ------------------------------------------------------------


async def test_el_codigo_no_sustituye_al_permiso(seed: None) -> None:
    """Conocer el código no da permiso: ``manage_fleet`` sigue siendo obligatorio."""
    await _set_code()
    resp = await _post(f"/fleet/gateways/{G_A}/retire", _retire_gw(), _tok("soc_operator"))
    assert resp.status_code == 403

    assert await _audit("gateway_retire") == []


async def test_no_se_puede_retirar_hardware_de_otro_tenant(seed: None) -> None:
    await _set_code(T_A)
    resp = await _post(
        f"/fleet/gateways/{G_B}/retire",
        {"confirm_serial": "SN-RC-B1", "retire_code": CODE},
        _tok("tenant_admin", tenant=T_A),
    )
    assert resp.status_code == 404, resp.text
