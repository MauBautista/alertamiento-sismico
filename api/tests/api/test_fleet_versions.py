"""Inventario de versiones de la flota (T-2.69).

Dos planos, como en ``test_fleet.py``:

1. **Unit puro de ``derive_version_drift``** — la VERDAD ÚNICA de "qué versión
   corre este gabinete y cuánto se ha quedado atrás". La UI solo pinta.
2. **Endpoint** — los campos de deriva viajan en ``GET /fleet/gateways``, el
   registro de releases se lee y se publica, y el formulario YA NO puede
   escribir ``fw_version`` a mano.

El eje de todo el archivo es el criterio 3 de la ficha: **``S/D`` cuando no se
sabe, nunca la última versión conocida pintada como actual**. Un ``fw_version``
de hace tres semanas no es la versión que corre: es la última que reportó.
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
from takab_api.schemas.fleet import (
    VERSION_AL_DIA,
    VERSION_ATRASADA,
    VERSION_DESCONOCIDA,
    VERSION_NO_DECLARA,
    VERSION_SIN_REFERENCIA,
    VERSION_SIN_REINICIAR,
    VERSION_SIN_REPORTAR,
    VERSION_ULTIMA_CONOCIDA,
    ReleaseRef,
    derive_version_drift,
)

# Prefijo 69: no colisiona con seeds sync (1/2/3/9/a/b/c), async (7), B1 (8),
# fleet_admin (6*), ghosts (5*), health-history (4*) ni equipment (65*).
T_A = "69111111-1111-1111-1111-111111111111"
T_B = "69222222-2222-2222-2222-222222222222"
S_A = "69a00000-0000-0000-0000-0000000000a1"
S_B = "69b00000-0000-0000-0000-0000000000b1"
GW_DIA = "69d00000-0000-0000-0000-0000000000d1"  # late y corre lo último
GW_ATRAS = "69d00000-0000-0000-0000-0000000000d2"  # late y corre lo anterior
GW_MUDO = "69d00000-0000-0000-0000-0000000000d3"  # late y NO declara versión
GW_OFF = "69d00000-0000-0000-0000-0000000000d4"  # versión vieja y SIN ENLACE
GW_NUEVO = "69d00000-0000-0000-0000-0000000000d5"  # nunca latió
GW_RARO = "69d00000-0000-0000-0000-0000000000d6"  # corre algo fuera del registro
# [T-2.70] Disco con el SHA nuevo, proceso con el viejo: el deploy escribió y
# no reinició (o el reinicio falló). Hasta hoy este gabinete se pintaba AL DÍA.
GW_TRABADO = "69d00000-0000-0000-0000-0000000000d8"
GW_B = "69d00000-0000-0000-0000-0000000000d7"  # otro tenant (RLS)

# SHAs de 7 hex: el ÚNICO formato que `deploy/edge/deploy.sh` puede producir
# (`git describe --always --dirty --abbrev=7` sobre un repo sin tags). Nada de
# semver: no es ordenable, y la única relación decidible es la IGUALDAD.
V_NUEVA = "62f3f1e"
V_VIEJA = "d082095"
V_ANTIGUA = "0458349"
V_SUCIA = "62f3f1e-dirty"  # árbol sucio en el momento del deploy: NO es V_NUEVA

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"
_TENANTS = (T_A, T_B)
_CLEANUP = (
    text("DELETE FROM device_health WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM gateways WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM sites WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM tenants WHERE tenant_id = ANY(:t)"),
)


# ---- unit puro: derive_version_drift (verdad única, sin DB) ------------------

# El registro tal y como lo devuelve la query: MÁS NUEVO PRIMERO.
_REG = (
    ReleaseRef(version=V_NUEVA, age_s=3600.0),
    ReleaseRef(version=V_VIEJA, age_s=90000.0),
    ReleaseRef(version=V_ANTIGUA, age_s=900000.0),
)


def _drift(**over: object):
    args: dict[str, object] = {
        "fw_version": V_NUEVA,
        "age_s": 30.0,
        "sin_enlace_s": 300.0,
        "releases": _REG,
    }
    args.update(over)
    return derive_version_drift(**args)  # type: ignore[arg-type]


def test_al_dia_cuando_corre_el_ultimo_release() -> None:
    d = _drift()
    assert d.state == VERSION_AL_DIA
    assert d.releases_behind == 0
    assert d.release_age_s == 3600.0


def test_atrasada_cuenta_cuantos_releases_hay_por_delante() -> None:
    """«Cuánto atrás» en la única moneda calculable: cuántos releases posteriores
    existen. Los SHAs no son ordenables — sin el registro no habría respuesta."""
    assert _drift(fw_version=V_VIEJA).releases_behind == 1
    assert _drift(fw_version=V_ANTIGUA).releases_behind == 2
    assert _drift(fw_version=V_VIEJA).state == VERSION_ATRASADA
    # …y «cuánto tiempo lleva corriendo código viejo»: la edad de ESE release.
    assert _drift(fw_version=V_ANTIGUA).release_age_s == 900000.0


def test_sin_enlace_jamas_dice_al_dia_aunque_la_version_coincida() -> None:
    """EL CRITERIO 3. Un gabinete que lleva tres semanas callado puede haber sido
    reflasheado, apagado o robado: lo que la consola guarda es la ÚLTIMA versión
    que reportó, no la que corre. Pintarla como actual es el defecto del 14-jul.
    """
    d = _drift(age_s=300.1)
    assert d.state == VERSION_ULTIMA_CONOCIDA
    assert d.state != VERSION_AL_DIA
    # La deriva del valor histórico SÍ se calcula: quien planifica una ola
    # (T-2.70) necesita saber qué se quedó atrás, aunque no pueda alcanzarlo.
    assert d.releases_behind == 0


def test_sin_heartbeat_nunca_pero_con_version_es_ultima_conocida() -> None:
    """Sin ningún latido no hay forma de fechar el dato: no es actual por defecto."""
    assert _drift(age_s=None).state == VERSION_ULTIMA_CONOCIDA


def test_late_y_no_declara_version_es_sin_dato() -> None:
    """El gabinete habla y dice honestamente «no sé qué versión corro». Es un HECHO
    NUEVO, no un silencio: la ficha pasa a S/D en vez de congelar la versión vieja.
    """
    d = _drift(fw_version=None)
    assert d.state == VERSION_NO_DECLARA
    assert d.releases_behind is None
    assert d.release_age_s is None


def test_nunca_reporto_nada_se_distingue_del_que_dejo_de_declarar() -> None:
    assert _drift(fw_version=None, age_s=None).state == VERSION_SIN_REPORTAR


def test_version_fuera_del_registro_es_una_contradiccion_que_grita() -> None:
    """Corre código que nadie publicó. Sin registro esto era INDETECTABLE; con él
    deja de ser una ausencia y pasa a ser una contradicción."""
    d = _drift(fw_version="deadbee")
    assert d.state == VERSION_DESCONOCIDA
    assert d.releases_behind is None


def test_el_sufijo_dirty_no_es_la_version_limpia() -> None:
    """`deploy.sh` produce `-dirty` A PROPÓSITO cuando el árbol está sucio. La
    comparación es por IGUALDAD EXACTA: `62f3f1e-dirty` no es `62f3f1e`, y ese
    gabinete corre algo que no está en ningún registro."""
    assert _drift(fw_version=V_SUCIA).state == VERSION_DESCONOCIDA


def test_registro_vacio_no_permite_hablar_de_deriva() -> None:
    """Sin releases publicados se sabe QUÉ corre pero no si eso es lo actual. Decir
    AL DÍA sería inventar, y decir DESCONOCIDA culparía al gabinete de un vacío
    de la plataforma."""
    d = _drift(releases=())
    assert d.state == VERSION_SIN_REFERENCIA
    assert d.releases_behind is None


def test_el_registro_vacio_no_tapa_el_sin_enlace() -> None:
    """La honestidad sobre la EDAD del dato manda sobre la falta de registro."""
    assert _drift(releases=(), age_s=9999.0).state == VERSION_ULTIMA_CONOCIDA


def test_no_declara_manda_sobre_el_registro_vacio() -> None:
    assert _drift(fw_version=None, releases=()).state == VERSION_NO_DECLARA


# ---- endpoint ---------------------------------------------------------------


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
        # La tabla entera, no una lista de versiones: `fw_releases` es de
        # PLATAFORMA (sin tenant_id) y ninguna otra suite la siembra de forma
        # persistente. Enumerar las versiones dejaba residuos —cualquier valor que
        # un test publique y la lista no prevea— y un solo release huérfano más
        # nuevo que los del fixture reordena la deriva de TODAS las filas.
        await conn.execute(text("DELETE FROM fw_releases"))


async def _hb(conn, tid: str, gw: str, *, age_min: float) -> None:
    await conn.execute(
        text(
            "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, power_status, "
            "battery_pct, cert_days_remaining, mqtt_rtt_ms, seedlink_lag_s, ntp_offset_ms) "
            "VALUES (now() - make_interval(mins => :age), :t, :gw, 'heartbeat', 'mains', "
            "100.0, 365, 50.0, 0.4, 5.0)"
        ),
        {"age": age_min, "t": tid, "gw": gw},
    )


@pytest.fixture
async def seed() -> None:
    """Un tenant con los seis estados de versión + otro tenant para la RLS."""
    await _cleanup()
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code in ((T_A, "T269_A"), (T_B, "T269_B")):
            await conn.execute(
                text(
                    "INSERT INTO tenants (tenant_id, code, name, visibility) "
                    "VALUES (:id, :code, 'T-2.69', 'private')"
                ),
                {"id": tid, "code": code},
            )
        for sid, tid in ((S_A, T_A), (S_B, T_B)):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM})"
                ),
                {"sid": sid, "tid": tid, "code": sid[:6]},
            )
        # (disco, proceso). `run=None` = contrato ≤1.8.0: el gabinete no opina
        # sobre qué ejecuta, y esa ausencia NO puede leerse como desajuste.
        for gw, tid, sid, serial, fw, run in (
            (GW_DIA, T_A, S_A, "GW-DIA", V_NUEVA, V_NUEVA),
            (GW_ATRAS, T_A, S_A, "GW-ATRAS", V_VIEJA, V_VIEJA),
            (GW_MUDO, T_A, S_A, "GW-MUDO", None, None),
            (GW_OFF, T_A, S_A, "GW-OFF", V_VIEJA, V_VIEJA),
            (GW_NUEVO, T_A, S_A, "GW-NUEVO", None, None),
            (GW_RARO, T_A, S_A, "GW-RARO", V_SUCIA, None),
            (GW_TRABADO, T_A, S_A, "GW-TRABADO", V_NUEVA, V_VIEJA),
            (GW_B, T_B, S_B, "GW-B", V_NUEVA, V_NUEVA),
        ):
            await conn.execute(
                text(
                    "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, "
                    "fw_version, fw_running) "
                    "VALUES (:gw, :t, :s, :serial, :fw, :run)"
                ),
                {"gw": gw, "t": tid, "s": sid, "serial": serial, "fw": fw, "run": run},
            )
        for gw in (GW_DIA, GW_ATRAS, GW_MUDO, GW_RARO, GW_TRABADO):
            await _hb(conn, T_A, gw, age_min=0)
        await _hb(conn, T_A, GW_OFF, age_min=60)  # tres semanas cabrían igual
        await _hb(conn, T_B, GW_B, age_min=0)
        # Registro de releases, del más antiguo al más nuevo.
        for i, v in enumerate((V_ANTIGUA, V_VIEJA, V_NUEVA)):
            await conn.execute(
                text(
                    "INSERT INTO fw_releases (version, released_at, published_by) "
                    "VALUES (:v, now() - make_interval(days => :d), 'seed')"
                ),
                {"v": v, "d": 30 - i * 10},
            )
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(fleet_router)
    return app


async def _get(path: str, token: str):
    async with au.client_for(_app()) as c:
        return await c.get(path, headers=au.bearer(token))


async def test_cada_gabinete_dice_en_que_estado_esta_su_version(seed: None) -> None:
    resp = await _get("/fleet/gateways", au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200
    by_serial = {g["serial"]: g["version_state"] for g in resp.json()}
    assert by_serial == {
        "GW-DIA": VERSION_AL_DIA,
        "GW-ATRAS": VERSION_ATRASADA,
        "GW-MUDO": VERSION_NO_DECLARA,
        "GW-OFF": VERSION_ULTIMA_CONOCIDA,
        "GW-NUEVO": VERSION_SIN_REPORTAR,
        "GW-RARO": VERSION_DESCONOCIDA,
        # [T-2.70] El código nuevo está escrito y nadie lo ejecuta.
        "GW-TRABADO": VERSION_SIN_REINICIAR,
    }


async def test_la_edad_del_dato_de_version_viaja_con_la_fila(seed: None) -> None:
    """Criterio 1: «con edad del dato». La versión cabalga en CADA latido, así que
    la edad del dato de versión es la edad del último latido — y es ``None``
    cuando no hay versión que fechar."""
    resp = await _get("/fleet/gateways", au.make_token("soc_operator", tenant=T_A))
    by_serial = {g["serial"]: g for g in resp.json()}
    assert by_serial["GW-DIA"]["version_age_s"] < 120
    assert by_serial["GW-OFF"]["version_age_s"] > 3000  # una hora de silencio
    assert by_serial["GW-MUDO"]["version_age_s"] is None  # no hay versión que fechar
    assert by_serial["GW-NUEVO"]["version_age_s"] is None


async def test_la_deriva_agregada_es_contable(seed: None) -> None:
    """Criterio 2: cuántos están atrás y cuánto."""
    resp = await _get("/fleet/gateways", au.make_token("soc_operator", tenant=T_A))
    rows = resp.json()
    atrasados = [g for g in rows if g["version_state"] == VERSION_ATRASADA]
    assert len(atrasados) == 1
    assert atrasados[0]["releases_behind"] == 1
    assert atrasados[0]["release_age_s"] > 0


async def test_el_registro_de_releases_se_lee(seed: None) -> None:
    resp = await _get("/fleet/releases", au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200
    versions = [r["version"] for r in resp.json()]
    assert versions == [V_NUEVA, V_VIEJA, V_ANTIGUA]  # más nuevo primero


async def test_el_registro_es_de_plataforma_no_de_tenant(seed: None) -> None:
    """Qué firmware existe lo decide TAKAB, no el cliente: los dos tenants ven el
    MISMO registro. La deriva de CADA UNO sigue acotada por la RLS de gateways."""
    a = await _get("/fleet/releases", au.make_token("soc_operator", tenant=T_A))
    b = await _get("/fleet/releases", au.make_token("soc_operator", tenant=T_B))
    assert [r["version"] for r in a.json()] == [r["version"] for r in b.json()]
    flota_b = await _get("/fleet/gateways", au.make_token("soc_operator", tenant=T_B))
    assert {g["serial"] for g in flota_b.json()} == {"GW-B"}


async def _post(path: str, token: str, body: dict):
    async with au.client_for(_app()) as c:
        return await c.post(path, headers=au.bearer(token), json=body)


async def test_publicar_un_release_es_acto_del_dueno_de_la_plataforma(seed: None) -> None:
    resp = await _post(
        "/fleet/releases", au.make_token("takab_superadmin", tenant=T_A), {"version": "9999999"}
    )
    assert resp.status_code == 201
    assert resp.json()["version"] == "9999999"
    lista = await _get("/fleet/releases", au.make_token("soc_operator", tenant=T_A))
    assert [r["version"] for r in lista.json()][0] == "9999999"


@pytest.mark.parametrize("role", ["tenant_admin", "soc_operator", "takab_support"])
async def test_un_cliente_no_publica_firmware(seed: None, role: str) -> None:
    """Ni siquiera su propio tenant_admin: qué código corre el gabinete que protege
    un edificio lo decide TAKAB. `takab_support` lee la plataforma, no la publica."""
    resp = await _post("/fleet/releases", au.make_token(role, tenant=T_A), {"version": "9999999"})
    assert resp.status_code == 403


async def test_la_version_publicada_se_recorta_como_la_recorta_el_gabinete(seed: None) -> None:
    """Dos normalizaciones que no coinciden = un release que no puede coincidir con
    NADIE. El edge recorta al leer `FW_VERSION` y la ingesta recorta al recibir el
    latido, así que un `"62f3f1e "` pegado desde una terminal quedaría aquí para
    siempre (la tabla no admite UPDATE) sin casar jamás, y toda la flota que
    corriera ese código saldría DESCONOCIDA."""
    resp = await _post(
        "/fleet/releases", au.make_token("takab_superadmin", tenant=T_A), {"version": " 9999999 "}
    )
    assert resp.status_code == 201
    assert resp.json()["version"] == "9999999"


async def test_una_version_de_solo_espacios_se_rechaza(seed: None) -> None:
    resp = await _post(
        "/fleet/releases", au.make_token("takab_superadmin", tenant=T_A), {"version": "   "}
    )
    assert resp.status_code == 422


async def test_republicar_el_mismo_release_no_duplica(seed: None) -> None:
    resp = await _post(
        "/fleet/releases", au.make_token("takab_superadmin", tenant=T_A), {"version": V_NUEVA}
    )
    assert resp.status_code == 409


async def test_el_formulario_ya_no_puede_escribir_la_version(seed: None) -> None:
    """SEGUNDO CAMINO A LA MENTIRA, cerrado. El PUT es de reemplazo TOTAL y la
    consola reenviaba `fw_version` con CADA edición: un operador podía anotar (o
    borrar) una versión que el gabinete nunca corrió. En un gabinete vivo el
    siguiente latido lo corregía en ≤60 s; en uno SIN ENLACE la mentira era
    PERMANENTE — y es justo ese sobre el que más importa saber la verdad.

    Se rechaza con 422 (``extra='forbid'``), no se ignora en silencio: un cliente
    viejo tiene que enterarse de que su dato no se guardó.
    """
    async with au.client_for(_app()) as c:
        resp = await c.put(
            f"/fleet/gateways/{GW_OFF}",
            headers=au.bearer(au.make_token("tenant_admin", tenant=T_A)),
            json={
                "site_id": S_A,
                "serial": "GW-OFF",
                "fw_version": V_NUEVA,
                "has_wr1": True,
            },
        )
    assert resp.status_code == 422


async def test_editar_otro_campo_no_toca_la_version_declarada(seed: None) -> None:
    async with au.client_for(_app()) as c:
        resp = await c.put(
            f"/fleet/gateways/{GW_OFF}",
            headers=au.bearer(au.make_token("tenant_admin", tenant=T_A)),
            json={"site_id": S_A, "serial": "GW-OFF-2", "has_wr1": False},
        )
    assert resp.status_code == 200
    assert resp.json()["fw_version"] == V_VIEJA  # la declaró el aparato; nadie la pisa


# --------------------------------------------------------------------------
# [T-2.70] ESCRITO ≠ CORRIENDO. `fw_version` dice qué código hay EN EL DISCO;
# `fw_running` (contrato 1.9.0) dice cuál EJECUTA el proceso. `deploy.sh`
# escribe el archivo ANTES de reiniciar, así que entre ambas cosas —y para
# siempre si el reinicio falla— el gabinete tiene el código nuevo escrito y
# sigue ejecutando el viejo. Medir la deriva contra el DISCO diría «AL DÍA»
# sobre un gabinete que no ha aplicado nada: es el "PUBLICADO ≠ ENTREGADO" de
# esta fase y el que invalidaría el criterio de éxito de un canary.
# --------------------------------------------------------------------------


def test_codigo_escrito_que_nadie_ejecuta_no_es_al_dia() -> None:
    """El caso exacto de un despliegue que se quedó a medias: el rsync dejó el
    SHA nuevo en el disco y el proceso nunca se reinició (o la unidad quedó en
    `failed`). Antes esto era INDISTINGUIBLE de un gabinete al día."""
    d = _drift(fw_version=V_NUEVA, fw_running=V_VIEJA)
    assert d.state == VERSION_SIN_REINICIAR
    assert d.state != VERSION_AL_DIA


def test_la_deriva_se_mide_contra_lo_que_CORRE_no_contra_el_disco() -> None:
    """«Cuántos atrás» describe el código que protege el edificio AHORA."""
    d = _drift(fw_version=V_NUEVA, fw_running=V_ANTIGUA)
    assert d.releases_behind == 2, "V_ANTIGUA es lo que corre, y está 2 atrás"
    assert d.release_age_s == 900000.0, "la edad es la del release que CORRE"


def test_cuando_disco_y_proceso_coinciden_no_hay_nada_que_señalar() -> None:
    """El caso normal: un deploy que sí reinició. No inventa un estado nuevo."""
    assert _drift(fw_version=V_NUEVA, fw_running=V_NUEVA).state == VERSION_AL_DIA
    assert _drift(fw_version=V_VIEJA, fw_running=V_VIEJA).state == VERSION_ATRASADA


def test_un_gabinete_que_no_declara_lo_que_corre_no_inventa_desajuste() -> None:
    """Contrato ≤1.8.0: `fw_running` ausente = «no opino». Tratar ese None como
    un desajuste marcaría SIN REINICIAR a toda la flota vieja de golpe."""
    assert _drift(fw_version=V_NUEVA, fw_running=None).state == VERSION_AL_DIA
    assert _drift(fw_version=V_VIEJA, fw_running=None).state == VERSION_ATRASADA


def test_sin_enlace_manda_sobre_el_desajuste() -> None:
    """Un gabinete callado tres semanas pudo reiniciarse, romperse o ser robado:
    su desajuste es tan histórico como su versión. El rótulo honesto sigue siendo
    ÚLTIMA CONOCIDA — nunca un diagnóstico sobre datos viejos."""
    d = _drift(fw_version=V_NUEVA, fw_running=V_VIEJA, age_s=99999.0)
    assert d.state == VERSION_ULTIMA_CONOCIDA


def test_el_desajuste_se_grita_aunque_el_disco_traiga_algo_no_publicado() -> None:
    """Disco con un SHA fuera del registro + proceso con otro: lo ACCIONABLE es
    que no está corriendo lo que se escribió, no que el registro esté incompleto."""
    d = _drift(fw_version="fffffff", fw_running=V_VIEJA)
    assert d.state == VERSION_SIN_REINICIAR


def test_sin_reiniciar_no_tapa_al_gabinete_que_no_declara_version() -> None:
    """Sin versión de disco no hay nada contra qué comparar: manda NO DECLARA."""
    assert _drift(fw_version=None, fw_running=V_VIEJA).state == VERSION_NO_DECLARA


async def test_la_consola_recibe_los_dos_SHAs_cuando_el_deploy_se_quedo_a_medias(
    seed: None,
) -> None:
    """Criterio de éxito honesto de una actualización (T-2.70).

    No basta el rótulo: con el despliegue trabado el operador necesita ver QUÉ
    quedó escrito y QUÉ se sigue ejecutando, porque son dos SHAs distintos y la
    acción (reiniciar, o ir a ver por qué la unidad quedó en `failed`) depende de
    ambos. Un solo campo obligaba a adivinar cuál de los dos estaba viendo.
    """
    resp = await _get("/fleet/gateways", au.make_token("soc_operator", tenant=T_A))
    fila = next(g for g in resp.json() if g["serial"] == "GW-TRABADO")
    assert fila["fw_version"] == V_NUEVA, "lo que dejó el rsync en el disco"
    assert fila["fw_running"] == V_VIEJA, "lo que el proceso sigue ejecutando"
    assert fila["version_state"] == VERSION_SIN_REINICIAR
    # …y la deriva describe el código QUE CORRE, no el que espera en el disco.
    assert fila["releases_behind"] == 1
