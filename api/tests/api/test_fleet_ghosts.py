"""T-2.35 · Las estaciones fantasma no existen: el inventario filtra lo retirado.

El defecto que estos tests cierran vivía en ``queries/fleet.py::_LIST``, la ÚNICA
query del repo que no filtraba nada (compárese con ``queries/sites.py``,
``queries/telemetry.py``, ``queries/commands.py``, ``queries/mobile.py``,
``commands/sync.py`` y el propio ``queries/fleet.py::_CONFIG_STATE``). Como además
``retire_site`` no tocaba ``gateways``, cada retiro de estación dejaba en el grid una
tarjeta indeleble y anónima — el cliente veía "estaciones fantasma duplicadas".

Ninguna suite anterior lo habría cazado: ``test_fleet_admin.py`` comprobaba el status
que devuelve el retiro, pero nunca volvía a listar el inventario. Por eso el primer
test de este archivo es exactamente esa vuelta.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.routers.fleet import router as fleet_router
from takab_api.routers.sites import router as sites_router

# Prefijo 5: libre (sync usa 1/2/3/9/a/b/c, async 7, B1 8, fleet_admin 6).
T_A = "51111111-1111-1111-1111-111111111111"
T_B = "52222222-2222-2222-2222-222222222222"
S_A = "5a000000-0000-0000-0000-0000000000a1"
S_A2 = "5a000000-0000-0000-0000-0000000000a2"
S_B = "5b000000-0000-0000-0000-0000000000b1"
G_A = "5d000000-0000-0000-0000-0000000000d1"
G_A2 = "5d000000-0000-0000-0000-0000000000d2"
G_B = "5d000000-0000-0000-0000-0000000000d3"

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"
_TENANTS = (T_A, T_B)
_CLEANUP = (
    text("DELETE FROM gateway_config_state WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM rule_sets WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM gateways WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM sites WHERE tenant_id = ANY(:t)"),
    text("TRUNCATE audit_log"),  # append-only: DELETE lo veta un trigger
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
    """Tenant A con dos sitios (dos gabinetes) y tenant B con uno, para el cruce RLS."""
    await _cleanup()
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code in ((T_A, "GHOST_A"), (T_B, "GHOST_B")):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) "
                    "VALUES (:id, :code, 'T-2.35', 'private')"
                ),
                {"id": tid, "code": code},
            )
        for sid, tid, code, name in (
            (S_A, T_A, "TORRE-A", "Torre Norte"),
            (S_A2, T_A, "TORRE-B", "Torre Sur"),
            (S_B, T_B, "AJENA", "Sitio del otro"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, :name, {_GEOM})"
                ),
                {"sid": sid, "tid": tid, "code": code, "name": name},
            )
        for gid, tid, sid, serial in (
            (G_A, T_A, S_A, "SN-GHOST-A1"),
            (G_A2, T_A, S_A2, "SN-GHOST-A2"),
            (G_B, T_B, S_B, "SN-GHOST-B1"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
                    "VALUES (:g, :t, :s, :sn, :thing)"
                ),
                {"g": gid, "t": tid, "s": sid, "sn": serial, "thing": f"thing-{serial}"},
            )
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(sites_router)
    app.include_router(fleet_router)
    return app


def _tok(role: str = "tenant_admin", tenant: str = T_A) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _get(path: str, token: dict[str, str] | None = None):
    async with au.client_for(_app()) as c:
        return await c.get(path, headers=token or _tok())


async def _delete(path: str, token: dict[str, str] | None = None):
    async with au.client_for(_app()) as c:
        return await c.delete(path, headers=token or _tok())


async def _post(path: str, body: dict, token: dict[str, str] | None = None):
    async with au.client_for(_app()) as c:
        return await c.post(path, json=body, headers=token or _tok())


async def _ids(path: str = "/fleet/gateways", token: dict[str, str] | None = None) -> set[str]:
    resp = await _get(path, token)
    assert resp.status_code == 200, resp.text
    return {g["gateway_id"] for g in resp.json()}


# ---- el hueco exacto por el que entró el bug ---------------------------------


async def test_retirar_un_gabinete_lo_saca_del_inventario(seed: None) -> None:
    """El test que faltaba: ``test_fleet_admin`` retiraba y nunca volvía a listar."""
    assert G_A in await _ids()

    retired = await _delete(f"/fleet/gateways/{G_A}")
    assert retired.status_code == 200, retired.text
    assert retired.json()["status"] == "retired"

    assert G_A not in await _ids(), "un gabinete retirado NO puede seguir pintándose"
    assert G_A2 in await _ids(), "y el retiro no arrastra a sus hermanos"


async def test_retirar_el_sitio_retira_sus_gabinetes(seed: None) -> None:
    """Retirar la estación apaga su gabinete: si no, sobrevive fuera de todo catálogo.

    No es cosmético — ``commands/sync.py`` y ``queries/commands.py`` filtran por
    ``gateways.status``, no por ``sites.status``: un gabinete huérfano seguiría siendo
    candidato de config firmada y de comandos de actuación.
    """
    resp = await _delete(f"/sites/{S_A}")
    assert resp.status_code == 200, resp.text

    assert G_A not in await _ids()

    async with get_engine().connect() as conn:
        status = await conn.scalar(
            text("SELECT status FROM gateways WHERE gateway_id = :g"), {"g": G_A}
        )
    assert status == "retired", "la fila del gabinete quedó viva tras retirar su sitio"


async def test_gabinete_activo_de_sitio_retirado_tampoco_se_pinta(seed: None) -> None:
    """Defensa en profundidad: aunque el estado quede sucio, el inventario lo tapa.

    Se ensucia a mano (retiro del sitio SIN propagar, que es exactamente el estado en
    el que quedó la base de producción antes de esta tarea).
    """
    async with get_engine().begin() as conn:
        await conn.execute(
            text("UPDATE sites SET status = 'retired' WHERE site_id = :s"), {"s": S_A}
        )

    assert G_A not in await _ids(), "el filtro debe mirar también el estado del sitio padre"


async def test_include_retired_los_devuelve_rotulados(seed: None) -> None:
    """Se pueden ver para restaurarlos, pero nunca por defecto y siempre etiquetados."""
    await _delete(f"/fleet/gateways/{G_A}")

    resp = await _get("/fleet/gateways?include_retired=true")
    assert resp.status_code == 200, resp.text
    rows = {g["gateway_id"]: g for g in resp.json()}
    assert G_A in rows
    assert rows[G_A]["status"] == "retired"
    assert rows[G_A]["site_status"] == "active", "el sitio sigue vivo: solo cayó el gabinete"


async def test_restaurar_devuelve_el_gabinete_al_inventario(seed: None) -> None:
    await _delete(f"/fleet/gateways/{G_A}")
    assert G_A not in await _ids()

    restored = await _post(f"/fleet/gateways/{G_A}/restore", {})
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "provisioned"
    assert G_A in await _ids()


# ---- el nombre lo pone el servidor, no lo inventa el cliente -----------------


async def test_el_inventario_trae_el_nombre_del_sitio(seed: None) -> None:
    """Sin esto la web caía a ``SITIO <8 hex>`` y dos huérfanos parecían el mismo."""
    rows = {g["gateway_id"]: g for g in (await _get("/fleet/gateways")).json()}
    assert rows[G_A]["site_name"] == "Torre Norte"
    assert rows[G_A]["site_code"] == "TORRE-A"
    assert rows[G_A]["site_status"] == "active"
    assert rows[G_A2]["site_name"] == "Torre Sur"


async def test_el_inventario_ordena_por_nombre_de_sitio(seed: None) -> None:
    """Orden estable y legible: el operador busca por edificio, no por serial."""
    names = [g["site_name"] for g in (await _get("/fleet/gateways")).json()]
    assert names == sorted(names)


# ---- consecuencias aguas abajo ----------------------------------------------


async def test_retirar_el_sitio_deja_su_gabinete_no_sincronizable(seed: None) -> None:
    """``is_syncable`` es el espejo del predicado de publicación de ``commands/sync.py``."""
    before = await _get(f"/fleet/gateways/{G_A}/config-state")
    assert before.json()["is_syncable"] is True

    await _delete(f"/sites/{S_A}")

    after = await _get(f"/fleet/gateways/{G_A}/config-state")
    assert after.status_code == 200, after.text
    assert after.json()["is_syncable"] is False


async def test_el_retiro_del_sitio_audita_cada_gabinete(seed: None) -> None:
    """La bitácora tiene que decir QUÉ hardware se apagó, no solo que cayó el sitio."""
    await _delete(f"/sites/{S_A}")

    async with get_engine().connect() as conn:
        rows = (
            await conn.execute(text("SELECT verb, object FROM audit_log ORDER BY audit_id"))
        ).all()
    verbs = [r.verb for r in rows]
    assert "site_retire" in verbs
    assert f"gateway:{G_A}" in {r.object for r in rows if r.verb == "gateway_retire"}


# ---- aislamiento entre tenants (regla de oro 5) ------------------------------


async def test_el_tenant_b_no_ve_los_retirados_del_tenant_a(seed: None) -> None:
    await _delete(f"/fleet/gateways/{G_A}")

    visible = await _ids("/fleet/gateways?include_retired=true", _tok(tenant=T_B))
    assert visible == {G_B}, "include_retired no puede ser una rendija cross-tenant"


# ---- la migración de saneamiento (0024) --------------------------------------
#
# Se ejerce el SQL REAL de la migración, no una copia: una copia se desincroniza y
# el test empezaría a validar código muerto.


def _migration_sql() -> str:
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "0024_retire_ghost_gateways.py"
    )
    spec = importlib.util.spec_from_file_location("_mig_0024", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._UP


async def _audit_count(verb: str) -> int:
    async with get_engine().connect() as conn:
        return await conn.scalar(
            text("SELECT count(*) FROM audit_log WHERE verb = :v"), {"v": verb}
        )


async def test_la_migracion_0024_retira_los_fantasmas_ya_existentes(seed: None) -> None:
    """El estado sucio que la base viva arrastra: sitio retirado, gabinete activo."""
    async with get_engine().begin() as conn:
        await conn.execute(
            text("UPDATE sites SET status = 'retired' WHERE site_id = :s"), {"s": S_A}
        )
        await conn.exec_driver_sql(_migration_sql())

    async with get_engine().connect() as conn:
        rows = {
            str(r.gateway_id): r.status
            for r in (
                await conn.execute(
                    text("SELECT gateway_id, status FROM gateways WHERE tenant_id = :t"),
                    {"t": T_A},
                )
            ).all()
        }
    assert rows[G_A] == "retired"
    assert rows[G_A2] == "provisioned", "el saneamiento no toca gabinetes de sitios vivos"
    assert await _audit_count("gateway_retire") == 1, "cada gabinete apagado deja rastro"


async def test_la_migracion_0024_es_idempotente(seed: None) -> None:
    """Re-correrla no actualiza nada ni duplica auditoría (invariante T-1.45)."""
    sql = _migration_sql()
    async with get_engine().begin() as conn:
        await conn.execute(
            text("UPDATE sites SET status = 'retired' WHERE site_id = :s"), {"s": S_A}
        )
        await conn.exec_driver_sql(sql)
    first = await _audit_count("gateway_retire")

    async with get_engine().begin() as conn:
        await conn.exec_driver_sql(sql)

    assert await _audit_count("gateway_retire") == first == 1


def test_la_migracion_0024_conserva_el_guc_de_rls() -> None:
    """Sin ``SET LOCAL app.role`` el UPDATE toca 0 filas EN SILENCIO en la nube.

    ``gateways`` lleva FORCE RLS y el dueño (``takab_migrator``) es el mismo usuario
    con el que se migra en producción. En local no se vería: el superusuario ignora la
    RLS y la migración parecería verde sin haber hecho nada. Este test evita que la
    línea desaparezca en una limpieza futura.
    """
    assert "SET LOCAL app.role = 'takab_superadmin'" in _migration_sql()
