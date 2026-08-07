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
from takab_api.routers.tenants import router as tenants_router

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
    text("DELETE FROM tenant_retire_codes WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM gateway_config_state WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM rule_sets WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM device_health WHERE tenant_id = ANY(:t)"),
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
    await _arm_retire_code(T_A)
    await _arm_retire_code(T_B)
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


async def _get(path: str, token: dict[str, str] | None = None):
    async with au.client_for(_app()) as c:
        return await c.get(path, headers=token or _tok())


async def _post(path: str, body: dict, token: dict[str, str] | None = None):
    async with au.client_for(_app()) as c:
        return await c.post(path, json=body, headers=token or _tok())


async def _put(path: str, body: dict, token: dict[str, str] | None = None):
    async with au.client_for(_app()) as c:
        return await c.put(path, json=body, headers=token or _tok())


# [T-2.36] Retirar exige doble fricción; aquí es ruido de fondo, no el objeto del
# test, así que se encapsula. Su semántica propia se prueba en test_retire_code.py.
RETIRE_CODE = "GHOSTS-RETIRO-2026"


async def _arm_retire_code(tenant: str = T_A) -> None:
    resp = await _put(
        f"/tenants/{tenant}/retire-code",
        {"code": RETIRE_CODE},
        _tok("takab_superadmin", tenant=tenant),
    )
    assert resp.status_code == 200, resp.text


async def _retire_gateway(gateway_id: str, serial: str, token: dict[str, str] | None = None):
    return await _post(
        f"/fleet/gateways/{gateway_id}/retire",
        {"confirm_serial": serial, "retire_code": RETIRE_CODE},
        token,
    )


async def _retire_site(site_id: str, code: str, token: dict[str, str] | None = None):
    return await _post(
        f"/sites/{site_id}/retire",
        {"confirm_code": code, "retire_code": RETIRE_CODE},
        token,
    )


async def _ids(path: str = "/fleet/gateways", token: dict[str, str] | None = None) -> set[str]:
    resp = await _get(path, token)
    assert resp.status_code == 200, resp.text
    return {g["gateway_id"] for g in resp.json()}


# ---- el hueco exacto por el que entró el bug ---------------------------------


async def test_retirar_un_gabinete_lo_saca_del_inventario(seed: None) -> None:
    """El test que faltaba: ``test_fleet_admin`` retiraba y nunca volvía a listar."""
    assert G_A in await _ids()

    retired = await _retire_gateway(G_A, "SN-GHOST-A1")
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
    resp = await _retire_site(S_A, "TORRE-A")
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
    await _retire_gateway(G_A, "SN-GHOST-A1")

    resp = await _get("/fleet/gateways?include_retired=true")
    assert resp.status_code == 200, resp.text
    rows = {g["gateway_id"]: g for g in resp.json()}
    assert G_A in rows
    assert rows[G_A]["status"] == "retired"
    assert rows[G_A]["site_status"] == "active", "el sitio sigue vivo: solo cayó el gabinete"


async def test_restaurar_devuelve_el_gabinete_al_inventario(seed: None) -> None:
    await _retire_gateway(G_A, "SN-GHOST-A1")
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


async def test_retirar_el_sitio_deja_a_su_gabinete_pendiente_de_recibir_la_baja(
    seed: None,
) -> None:
    """``is_syncable`` es el espejo del predicado de publicación de ``commands/sync.py``.

    [T-2.65] REESCRITO A PROPÓSITO (antes: ``…deja_su_gabinete_no_sincronizable``).
    Retirar el sitio ya NO lo saca del flujo de config de inmediato: el gabinete
    sigue siendo candidato hasta que reciba su sobre de baja — el aviso que
    T-2.58 §2.3 documentó como imposible y que costó el fantasma del 2026-08-04.
    Que salga de la lista ANTES de avisarle es exactamente el defecto arreglado.
    """
    before = await _get(f"/fleet/gateways/{G_A}/config-state")
    assert before.json()["is_syncable"] is True

    await _retire_site(S_A, "TORRE-A")

    after = await _get(f"/fleet/gateways/{G_A}/config-state")
    assert after.status_code == 200, after.text
    assert after.json()["is_syncable"] is True  # queda el aviso por entregar
    assert after.json()["in_sync"] is False


async def test_el_retiro_del_sitio_audita_cada_gabinete(seed: None) -> None:
    """La bitácora tiene que decir QUÉ hardware se apagó, no solo que cayó el sitio."""
    await _retire_site(S_A, "TORRE-A")

    async with get_engine().connect() as conn:
        rows = (
            await conn.execute(text("SELECT verb, object FROM audit_log ORDER BY audit_id"))
        ).all()
    verbs = [r.verb for r in rows]
    assert "site_retire" in verbs
    assert f"gateway:{G_A}" in {r.object for r in rows if r.verb == "gateway_retire"}


# ---- aislamiento entre tenants (regla de oro 5) ------------------------------


async def test_el_tenant_b_no_ve_los_retirados_del_tenant_a(seed: None) -> None:
    await _retire_gateway(G_A, "SN-GHOST-A1")

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


# ---- T-2.60.a · el fantasma VIVO -------------------------------------------
#
# T-2.35 enseñó a esconder lo retirado y estuvo bien: un gabinete desmontado no
# puede quedarse en el grid para siempre. Pero esconder por estado, sin mirar si
# el aparato sigue hablando, creó el fallo simétrico — y se cobró su víctima el
# 2026-08-04: `gw-dev-0001` llevaba HORAS publicando latidos cada 60 s mientras
# era invisible en la consola, porque el 03-08 se retiró su sitio y la migración
# 0024 heredó el retiro. Se detectó porque el operador preguntó por su estación,
# no porque el sistema dijera nada.
#
# La regla que estos tests fijan: **esconder al mudo, delatar al que late**.
# "Late" no se inventa aquí — es la misma frontera de `derive_fleet_state`
# (`SIN ENLACE` ⇔ sin latido o más viejo que `sin_enlace_min`), para que no haya
# dos definiciones de "vivo" que puedan divergir.


async def _latido(gateway_id: str, tenant: str, *, hace_s: float) -> None:
    """Un heartbeat a medida, para poder fabricar vivos y mudos."""
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, mqtt_rtt_ms) "
                "VALUES (now() - make_interval(secs => :age), :t, :g, 'heartbeat', 40)"
            ),
            {"age": hace_s, "t": tenant, "g": gateway_id},
        )


async def _fila(gateway_id: str, path: str = "/fleet/gateways") -> dict | None:
    resp = await _get(path)
    assert resp.status_code == 200, resp.text
    return next((g for g in resp.json() if g["gateway_id"] == gateway_id), None)


async def test_el_retirado_que_sigue_latiendo_NO_desaparece(seed: None) -> None:
    """El corazón de T-2.60.a: retirar no puede silenciar a un aparato que habla."""
    await _latido(G_A, T_A, hace_s=5)  # latió hace 5 s: está vivo
    assert (await _retire_gateway(G_A, "SN-GHOST-A1")).status_code == 200

    fila = await _fila(G_A)
    assert fila is not None, (
        "el gabinete retirado SIGUE LATIENDO y aun así desapareció del inventario: "
        "es exactamente el fallo del 2026-08-04"
    )
    assert fila["is_ghost"] is True
    assert fila["status"] == "retired"
    assert fila["derived_state"] != "SIN ENLACE"


async def test_el_retirado_y_mudo_si_desaparece(seed: None) -> None:
    """La otra mitad: T-2.35 sigue vigente para el hardware realmente desmontado."""
    await _latido(G_A, T_A, hace_s=3600)  # una hora callado: desmontado
    assert (await _retire_gateway(G_A, "SN-GHOST-A1")).status_code == 200
    assert await _fila(G_A) is None


async def test_el_retirado_que_nunca_latio_si_desaparece(seed: None) -> None:
    """Sin un solo heartbeat no hay nada que delatar: se esconde y ya."""
    assert (await _retire_gateway(G_A, "SN-GHOST-A1")).status_code == 200
    assert await _fila(G_A) is None


async def test_el_fantasma_dice_CUANDO_y_QUIEN_lo_retiro(seed: None) -> None:
    """Delatarlo sin decir quién ni cuándo obliga a irse a la auditoría a mano."""
    await _latido(G_A, T_A, hace_s=5)
    assert (await _retire_gateway(G_A, "SN-GHOST-A1")).status_code == 200

    fila = await _fila(G_A)
    assert fila is not None
    assert fila["retired_at"] is not None, "el fantasma no dice cuándo lo retiraron"
    assert fila["retired_by"], "el fantasma no dice quién lo retiró"


async def test_retirar_el_SITIO_tambien_delata_al_gabinete_vivo(seed: None) -> None:
    """El caso REAL del 2026-08-04: el retiro llegó por herencia del sitio."""
    await _latido(G_A, T_A, hace_s=5)
    assert (await _retire_site(S_A, "TORRE-A")).status_code == 200

    fila = await _fila(G_A)
    assert fila is not None, "el gabinete vivo se perdió al retirar su sitio"
    assert fila["is_ghost"] is True


async def test_un_gabinete_normal_no_es_fantasma(seed: None) -> None:
    """La bandera tiene que ser rara: si se enciende siempre, no informa de nada."""
    await _latido(G_A, T_A, hace_s=5)
    fila = await _fila(G_A)
    assert fila is not None
    assert fila["is_ghost"] is False
    assert fila["retired_at"] is None


async def test_el_tenant_B_no_ve_el_fantasma_del_tenant_A(seed: None) -> None:
    """Delatar no puede abrir un boquete en el aislamiento (regla de oro 5)."""
    await _latido(G_A, T_A, hace_s=5)
    assert (await _retire_gateway(G_A, "SN-GHOST-A1")).status_code == 200
    assert G_A not in await _ids(token=_tok("tenant_admin", tenant=T_B))


# ---- B3 · `is_ghost` NO se acota con el aviso -------------------------------
#
# T-2.65 acotó la MÉTRICA (deja de paginar cuando consta que el sobre pudo
# llegarle) y no tocó `is_ghost`. La asimetría es deliberada y hasta hoy no la
# fijaba ningún test, así que una limpieza futura "por coherencia" habría apagado
# el rótulo sin que nada se quejara — y es la ÚLTIMA señal automática que le
# queda al retirado que late y ya fue avisado.
#
# La razón: `is_ghost` no es un nivel de urgencia, es un HECHO —"dado de baja y
# aun así enchufado y hablando"— y ese hecho no cambia porque el gabinete se haya
# enterado. Bajo la opción (A) sigue protegiendo (correcto) y sigue exigiendo una
# decisión: o se desmonta de verdad, o se restaura. Quitarlo de la pantalla sería
# volver a esconder un edificio, que es el fallo del 2026-08-04. La alarma se
# calla porque pagina a las 3 de la mañana; la consola no, porque se mira cuando
# alguien está delante y ahí no hay coste de fatiga.


async def _publica_baja(gateway_id: str, tenant: str) -> None:
    """La nube publicó el sobre firmado que le DECLARA la baja (T-2.65)."""
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO gateway_config_state (gateway_id, tenant_id, version, "
                "payload, sig) VALUES (:g, :t, 5, CAST(:p AS jsonb), 'sig-b3') "
                "ON CONFLICT (gateway_id) DO UPDATE SET payload = EXCLUDED.payload"
            ),
            {"g": gateway_id, "t": tenant, "p": '{"cloud_admin_state": "retired"}'},
        )


async def test_el_retirado_YA_AVISADO_que_late_SIGUE_siendo_fantasma_en_la_consola(
    seed: None,
) -> None:
    """El estado que quedó sin ninguna otra señal automática tras T-2.65."""
    await _latido(G_A, T_A, hace_s=5)
    assert (await _retire_gateway(G_A, "SN-GHOST-A1")).status_code == 200
    await _publica_baja(G_A, T_A)

    fila = await _fila(G_A)
    assert fila is not None, (
        "el gabinete retirado, ya avisado y SIGUIENDO PROTEGIENDO desapareció del "
        "inventario: volver a esconder un edificio con hardware enchufado es el "
        "fallo del 2026-08-04, no su arreglo"
    )
    assert fila["is_ghost"] is True, (
        "se apagó el rótulo de fantasma porque al gabinete ya se le avisó. El "
        "aviso no desmonta el hardware ni cierra la contradicción de inventario: "
        "es la ÚLTIMA señal automática de ese estado (la métrica ya no pagina por "
        "él a propósito) y sin ella el edificio vuelve a ser invisible"
    )
