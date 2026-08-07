"""``GET /fleet/gateways/{id}/config-state`` — observabilidad del sync firmado (T-1.30).

``POST /rule-sets/{id}/publish`` solo registra la INTENCIÓN (202 ``pending_sync``);
quien firma y publica de verdad es el worker de T-1.23, que hace UPSERT en
``gateway_config_state``. Sin este endpoint la consola no podía distinguir
"pendiente" de "ya llegó al gabinete" y habría tenido que mentir.

``in_sync`` se calcula con el MISMO predicado del worker (``commands/sync.py``:
``st.payload IS DISTINCT FROM rs.config->'edge'``), invertido → verdad única.
La firma HMAC cruda JAMÁS sale del servidor: solo su huella sha256.
"""

from __future__ import annotations

import hashlib
import json
import os

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.auth import deps
from takab_api.db.engine import get_engine
from takab_api.routers.fleet import router as fleet_router

pytestmark = pytest.mark.asyncio

T_A = "91111111-1111-1111-1111-111111111111"
T_B = "92222222-2222-2222-2222-222222222222"
S_A = "9a000000-0000-0000-0000-0000000000a1"
# Sitio con rule_set propio SIN bloque 'edge' (el de sitio gana al de tenant).
S_A_NOEDGE = "9a000000-0000-0000-0000-0000000000a2"
S_B = "9b000000-0000-0000-0000-0000000000b1"

GW_SYNCED = "9d000000-0000-0000-0000-0000000000d1"  # publicado y al día
GW_STALE = "9d000000-0000-0000-0000-0000000000d2"  # publicado, rule_set cambió
GW_NEVER = "9d000000-0000-0000-0000-0000000000d3"  # nunca publicado
GW_NOEDGE = "9d000000-0000-0000-0000-0000000000d4"  # rule_set sin bloque 'edge'
GW_RETIRED = "9d000000-0000-0000-0000-0000000000d5"  # retirado y SIN iot_thing
GW_B = "9d000000-0000-0000-0000-0000000000d6"  # otro tenant (RLS)
# [T-2.65] Retirado CON identidad IoT: el aviso de baja todavía tiene que salirle.
GW_RETIRED_PENDING = "9d000000-0000-0000-0000-0000000000d7"
# [T-2.65] Retirado y YA avisado (su doc publicado declara la baja).
GW_RETIRED_TOLD = "9d000000-0000-0000-0000-0000000000d8"

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"
_TENANTS = (T_A, T_B)

EDGE_CFG = {"thresholds": {"pga_trip_g": 0.08}, "sample_rate": 100}
EDGE_CFG_NEW = {"thresholds": {"pga_trip_g": 0.05}, "sample_rate": 100}
RAW_SIG = "deadbeefcafe1234567890abcdef"

_CLEANUP = (
    text("DELETE FROM gateway_config_state WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM rule_sets WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM gateways WHERE tenant_id = ANY(:t)"),
    text("DELETE FROM sites WHERE tenant_id = ANY(:t)"),
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
    await _cleanup()
    engine = get_engine()
    async with engine.begin() as conn:
        for tid, code in ((T_A, "CFGST_A"), (T_B, "CFGST_B")):
            await conn.execute(
                text("INSERT INTO tenants (tenant_id, code, name) VALUES (:id, :code, 'CFG')"),
                {"id": tid, "code": code},
            )
        # `code` es UNIQUE por tenant: los dos sitios de T_A comparten prefijo, así
        # que se etiquetan a mano en vez de recortar el uuid.
        for sid, tid, code in ((S_A, T_A, "SA"), (S_A_NOEDGE, T_A, "SA-NOEDGE"), (S_B, T_B, "SB")):
            await conn.execute(
                text(
                    "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                    f"VALUES (:sid, :tid, :code, 'Sitio', {_GEOM})"
                ),
                {"sid": sid, "tid": tid, "code": code},
            )
        # status ∈ (provisioned, online, degraded, offline, retired) — db/schema.sql.
        for gw, tid, sid, serial, status, thing in (
            (GW_SYNCED, T_A, S_A, "GW-SYNCED", "online", "thing-1"),
            (GW_STALE, T_A, S_A, "GW-STALE", "online", "thing-2"),
            (GW_NEVER, T_A, S_A, "GW-NEVER", "online", "thing-3"),
            (GW_NOEDGE, T_A, S_A_NOEDGE, "GW-NOEDGE", "online", "thing-4"),
            (GW_RETIRED, T_A, S_A, "GW-RETIRED", "retired", None),
            (GW_RETIRED_PENDING, T_A, S_A, "GW-RET-PEND", "retired", "thing-5"),
            (GW_RETIRED_TOLD, T_A, S_A, "GW-RET-TOLD", "retired", "thing-6"),
            (GW_B, T_B, S_B, "GW-B", "online", "thing-b"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, "
                    "status, iot_thing) VALUES (:gw, :t, :s, :serial, :st, :thing)"
                ),
                {"gw": gw, "t": tid, "s": sid, "serial": serial, "st": status, "thing": thing},
            )

        # NB: `:param::jsonb` NO liga en SQLAlchemy (su regex de bindparams lleva
        # un lookahead (?!:) para no morder los casts `::`). Usar CAST(... AS jsonb).
        _RS = text(
            "INSERT INTO rule_sets (tenant_id, scope_type, scope_id, version, "
            "is_active, config) VALUES (:t, :scope, :sid, 1, true, CAST(:cfg AS jsonb))"
        )
        # rule_set activo a nivel TENANT con bloque 'edge' → aplica a todos los de T_A…
        await conn.execute(
            _RS,
            {"t": T_A, "scope": "tenant", "sid": T_A, "cfg": json.dumps({"edge": EDGE_CFG})},
        )
        # …salvo GW_NOEDGE, que vive en un sitio cuyo rule_set (más específico, gana
        # sobre el de tenant) no trae 'edge'.
        await conn.execute(
            _RS,
            {
                "t": T_A,
                "scope": "site",
                "sid": S_A_NOEDGE,
                "cfg": json.dumps({"relays": {"siren": "NO"}}),
            },
        )
        await conn.execute(
            _RS,
            {"t": T_B, "scope": "tenant", "sid": T_B, "cfg": json.dumps({"edge": EDGE_CFG})},
        )

        # Estado publicado: SYNCED coincide con el rule_set; STALE quedó atrás.
        # [T-2.31] El worker guarda el doc FUSIONADO con gateways.equipment
        # (default DB = todo-true): el seed refleja lo que el worker escribe hoy.
        _EQ_ALL = {
            "siren": True,
            "strobe": True,
            "gas_valve": True,
            "elevator": True,
            "door_retainer": True,
        }
        # [T-2.65] …y con `cloud_admin_state`, que el doc firmado ahora transporta.
        for gw, tid, ver, payload in (
            (GW_SYNCED, T_A, 7, {**EDGE_CFG, "equipment": _EQ_ALL, "cloud_admin_state": "active"}),
            (
                GW_STALE,
                T_A,
                3,
                {**EDGE_CFG_NEW, "equipment": _EQ_ALL, "cloud_admin_state": "active"},
            ),
            (GW_B, T_B, 1, {**EDGE_CFG, "equipment": _EQ_ALL, "cloud_admin_state": "active"}),
            # Ya avisado: su doc publicado DECLARA la baja.
            (
                GW_RETIRED_TOLD,
                T_A,
                9,
                {**EDGE_CFG, "equipment": _EQ_ALL, "cloud_admin_state": "retired"},
            ),
        ):
            await conn.execute(
                text(
                    "INSERT INTO gateway_config_state (gateway_id, tenant_id, version, "
                    "payload, sig) VALUES (:gw, :t, :v, CAST(:p AS jsonb), :sig)"
                ),
                {"gw": gw, "t": tid, "v": ver, "p": json.dumps(payload), "sig": RAW_SIG},
            )
    yield
    await _cleanup()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(fleet_router)
    return app


async def _get(gateway_id: str, token: str):
    async with au.client_for(_app()) as c:
        return await c.get(f"/fleet/gateways/{gateway_id}/config-state", headers=au.bearer(token))


# ---- estado del sync --------------------------------------------------------


async def test_synced_gateway_reports_in_sync(seed: None) -> None:
    """Payload publicado == config.edge del rule_set activo ⇒ SINCRONIZADO."""
    resp = await _get(GW_SYNCED, au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["in_sync"] is True
    assert body["version"] == 7
    assert body["has_edge_config"] is True
    assert body["is_syncable"] is True
    assert body["published_at"] is not None


async def test_stale_gateway_is_not_in_sync(seed: None) -> None:
    """El rule_set cambió y el gabinete sigue con el payload viejo ⇒ PENDIENTE."""
    body = (await _get(GW_STALE, au.make_token("soc_operator", tenant=T_A))).json()
    assert body["in_sync"] is False
    assert body["version"] == 3  # la versión vieja se muestra tal cual


async def test_never_published_is_200_not_404(seed: None) -> None:
    """Sin fila en gateway_config_state la consola pinta PENDIENTE, no un error."""
    resp = await _get(GW_NEVER, au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] is None
    assert body["published_at"] is None
    assert body["sig_fingerprint"] is None
    assert body["in_sync"] is False
    assert body["has_edge_config"] is True


async def test_gateway_without_edge_config_never_syncs(seed: None) -> None:
    """El rule_set de sitio (preferente) no trae 'edge': el worker jamás lo publica.
    Mostrar PENDIENTE eternamente sería mentir; has_edge_config lo explica."""
    body = (await _get(GW_NOEDGE, au.make_token("soc_operator", tenant=T_A))).json()
    assert body["has_edge_config"] is False
    assert body["in_sync"] is False


async def test_gateway_without_any_active_rule_set_is_200_not_500(seed: None) -> None:
    """Sin rule_set activo el LEFT JOIN deja ``rs.config`` NULL y ``NULL ? 'edge'``
    es NULL (jsonb_exists es STRICT), no false: sin COALESCE el bool no-opcional de
    Pydantic reventaba con un 500 en el endpoint que promete 200 + PENDIENTE.

    Es un estado alcanzable: ``rule_sets.is_active`` nace en false y nada garantiza
    que un gateway recién aprovisionado tenga un rule_set activo.
    """
    async with get_engine().begin() as conn:
        await conn.execute(
            text("UPDATE rule_sets SET is_active = false WHERE tenant_id = :t"), {"t": T_A}
        )

    # Con estado publicado (in_sync sería TRUE AND NULL AND … = NULL sin COALESCE).
    resp = await _get(GW_SYNCED, au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # [B3] …y aquí `has_edge_config` es TRUE, no false. Sin rule_set activo el
    # worker recompone la base desde el último doc publicado (T-2.31/T-2.65), así
    # que SÍ hay documento que publicar: decir "SIN CONFIG EDGE" —cuyo copy afirma
    # "no hay nada que publicar"— era negar lo que el worker está haciendo. Lo que
    # el operador ve pasa a ser SINCRONIZADO v7, que es la verdad: el gabinete
    # tiene exactamente el documento que la nube volvería a mandarle. Que su
    # rule_set esté inactivo es un hecho de otra pantalla (Multi-Tenant).
    assert body["has_edge_config"] is True
    # [T-2.65] `in_sync` es la negación EXACTA del predicado de diferencia del
    # worker: no hay nada pendiente ⇒ True.
    assert body["in_sync"] is True
    assert body["version"] == 7  # el gabinete sigue con su config vieja

    # Y sin estado publicado tampoco explota: ahí sí no hay NADA que publicar
    # (ni rule_set del que sacar la base ni doc anterior) y el badge acierta.
    never = await _get(GW_NEVER, au.make_token("soc_operator", tenant=T_A))
    assert never.status_code == 200
    assert never.json()["has_edge_config"] is False
    assert never.json()["in_sync"] is False


# ---- B3 · `has_edge_config` significa "hay algo que publicar" ----------------
#
# El contrato publicado del campo decía «el rule_set activo trae bloque edge» y
# `SyncBadge` traduce su falsedad a "no hay nada que publicar". Desde que el
# worker recompone la base con un COALESCE (rule_set activo O último doc
# publicado), las dos frases dejaron de ser la misma: había gabinetes a los que
# el worker estaba publicando MIENTRAS la consola pintaba SIN CONFIG EDGE.
#
# El campo pasa a ser el espejo exacto del gate de publicación del worker
# (`commands/sync.py`: `b.base IS NOT NULL`). El nombre se conserva —es contrato
# publicado y el SDK lo consume— pero su documentación ya no promete otra cosa.


async def _candidatos_del_worker() -> set[str]:
    """Los gateways que `commands/sync.py` publicaría AHORA, con su SQL real.

    Se importa el SQL en vez de copiarlo: una copia se desincroniza y este test
    empezaría a validar código muerto.
    """
    from takab_api.commands.sync import _CANDIDATES_SQL

    async with get_engine().connect() as conn:
        rows = (await conn.exec_driver_sql(_CANDIDATES_SQL)).all()
    return {str(r.gateway_id) for r in rows}


async def test_has_edge_config_no_dice_que_NO_HAY_NADA_QUE_PUBLICAR_mientras_el_worker_publica(
    seed: None,
) -> None:
    """El gabinete al que el worker le está publicando en este mismo instante.

    Se desactiva el rule_set (así `rs.config ? 'edge'` es falso) y se cambia el
    equipamiento, que es un cambio real que el worker firma y entrega apoyándose
    en el último doc publicado. Con el contrato viejo la consola decía "no hay
    nada que publicar" sobre un gabinete que estaba en la cola de publicación:
    el operador no tenía forma de saber que su cambio SÍ iba a llegar.
    """
    async with get_engine().begin() as conn:
        await conn.execute(
            text("UPDATE rule_sets SET is_active = false WHERE tenant_id = :t"), {"t": T_A}
        )
        await conn.execute(
            text("UPDATE gateways SET equipment = CAST(:e AS jsonb) WHERE gateway_id = :g"),
            {"g": GW_SYNCED, "e": json.dumps({"siren": True, "gas_valve": False})},
        )

    assert GW_SYNCED in await _candidatos_del_worker(), (
        "el montaje del test no reproduce el caso: el worker no considera candidato a este gabinete"
    )

    body = (await _get(GW_SYNCED, au.make_token("soc_operator", tenant=T_A))).json()
    assert body["has_edge_config"] is True, (
        "la consola pinta SIN CONFIG EDGE ('no hay nada que publicar') sobre un "
        "gabinete que el worker tiene EN COLA de publicación ahora mismo"
    )
    assert body["in_sync"] is False


async def test_has_edge_config_sigue_siendo_falso_cuando_no_hay_NADA_de_donde_partir(
    seed: None,
) -> None:
    """La otra mitad: sin rule_set con 'edge' y sin doc previo no habrá publish nunca.

    Es el caso para el que se inventó el rótulo, y tiene que seguir distinguiéndose
    de un PENDIENTE que sí se va a resolver solo.
    """
    body = (await _get(GW_NOEDGE, au.make_token("soc_operator", tenant=T_A))).json()
    assert body["has_edge_config"] is False
    assert GW_NOEDGE not in await _candidatos_del_worker()


async def test_has_edge_config_es_el_espejo_del_gate_de_publicacion_del_worker(
    seed: None,
) -> None:
    """El invariante, sobre TODA la flota visible y sin enumerar casos a mano.

    `has_edge_config=false` tiene que implicar que el worker NO publicará: si un
    gabinete apareciera a la vez como "sin nada que publicar" y como candidato,
    la consola estaría contradiciendo al worker sobre su propio trabajo.
    """
    async with get_engine().begin() as conn:
        # Se ensucia el inventario de varias maneras a la vez para que el barrido
        # tenga algo que barrer: sin rule_set, con doc previo, sin nada.
        await conn.execute(
            text("UPDATE rule_sets SET is_active = false WHERE scope_type = 'tenant'"),
        )
        await conn.execute(
            text("UPDATE gateways SET equipment = CAST(:e AS jsonb) WHERE tenant_id = :t"),
            {"t": T_A, "e": json.dumps({"siren": False})},
        )

    candidatos = await _candidatos_del_worker()
    lote = (await _get_all(au.make_token("soc_operator", tenant=T_A))).json()
    assert lote, "el lote vino vacío: el test no está midiendo nada"

    sin_nada_que_publicar = {r["gateway_id"] for r in lote if r["has_edge_config"] is False}
    assert sin_nada_que_publicar & candidatos == set(), (
        "hay gabinetes marcados 'sin nada que publicar' que el worker tiene en "
        f"cola: {sorted(sin_nada_que_publicar & candidatos)}"
    )


async def test_gateway_sin_identidad_iot_nunca_es_sincronizable(seed: None) -> None:
    """Sin ``iot_thing`` no hay topic al que publicar: la UI no debe prometer sync.

    [T-2.65] Antes este test se llamaba ``test_retired_gateway_is_not_syncable`` y
    afirmaba las DOS cosas a la vez sobre un gabinete que además no tenía
    ``iot_thing``, así que la mitad del retiro nunca se probó de verdad.
    """
    body = (await _get(GW_RETIRED, au.make_token("soc_operator", tenant=T_A))).json()
    assert body["is_syncable"] is False


async def test_el_retirado_que_aun_no_recibio_su_baja_sigue_siendo_sincronizable(
    seed: None,
) -> None:
    """[T-2.65] REESCRITO A PROPÓSITO. Retirar ya no lo saca del flujo de config
    de inmediato: primero hay que AVISARLE. Mientras el aviso no salga, la consola
    debe decir PENDIENTE, no ``NO SINCRONIZABLE`` — que es justo lo que dejaba al
    gabinete latiendo invisible (víctima real: `gw-dev-0001`, 2026-08-04)."""
    body = (await _get(GW_RETIRED_PENDING, au.make_token("soc_operator", tenant=T_A))).json()
    assert body["is_syncable"] is True
    assert body["in_sync"] is False  # el sobre de baja está pendiente


async def test_el_retirado_ya_avisado_deja_el_flujo_de_config(seed: None) -> None:
    """[T-2.65] Recibido el sobre de baja, el gabinete sale de la lista: el aviso
    sale EXACTAMENTE UNA VEZ y la consola deja de prometer más config."""
    body = (await _get(GW_RETIRED_TOLD, au.make_token("soc_operator", tenant=T_A))).json()
    assert body["is_syncable"] is False
    assert body["in_sync"] is True  # su doc publicado ya declara la baja
    assert body["version"] == 9


# ---- seguridad --------------------------------------------------------------


async def test_raw_hmac_signature_never_leaves_the_server(seed: None) -> None:
    """La firma cruda junto al payload es material de ataque offline contra la
    clave HMAC. Solo sale su huella sha256 truncada."""
    resp = await _get(GW_SYNCED, au.make_token("soc_operator", tenant=T_A))
    raw = resp.text
    assert RAW_SIG not in raw
    body = resp.json()
    assert "sig" not in body
    assert "payload" not in body
    assert body["sig_fingerprint"] == hashlib.sha256(RAW_SIG.encode()).hexdigest()[:12]


async def test_rls_blocks_other_tenant_gateway(seed: None) -> None:
    """Tenant A no ve el config-state de un gateway de B: 404, no 403 (no revela
    que exista)."""
    resp = await _get(GW_B, au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 404


async def test_unknown_gateway_is_404(seed: None) -> None:
    resp = await _get(
        "9f000000-0000-0000-0000-0000000000ff", au.make_token("soc_operator", tenant=T_A)
    )
    assert resp.status_code == 404


@pytest.mark.parametrize("role", ["inspector", "building_admin"])
async def test_role_without_fleet_forbidden(seed: None, role: str) -> None:
    resp = await _get(GW_SYNCED, au.make_token(role, tenant=T_A))
    assert resp.status_code == 403


async def test_unauthenticated_rejected(seed: None) -> None:
    async with au.client_for(_app()) as c:
        resp = await c.get(f"/fleet/gateways/{GW_SYNCED}/config-state")
    assert resp.status_code == 401


# ---- estado en LOTE (T-2.37) -------------------------------------------------
#
# La consola pedía el estado de N gabinetes con N peticiones cada 10 s. Con 500
# gabinetes eso son ~50 req/s desde un solo navegador, y como el pie solo se toma
# por bueno cuando responden TODAS, a esa escala habría dicho "desconocido" siempre.


async def _get_all(token: str):
    async with au.client_for(_app()) as c:
        return await c.get("/fleet/config-state", headers=au.bearer(token))


async def test_el_lote_devuelve_lo_mismo_que_el_endpoint_por_gabinete(seed: None) -> None:
    token = au.make_token("soc_operator", tenant=T_A)
    batch = await _get_all(token)
    assert batch.status_code == 200, batch.text
    by_id = {row["gateway_id"]: row for row in batch.json()}

    for gid in (GW_SYNCED, GW_STALE):
        single = (await _get(gid, token)).json()
        assert by_id[gid] == single, "el lote y el detalle no pueden discrepar"


async def test_el_lote_respeta_la_rls_por_tenant(seed: None) -> None:
    rows = (await _get_all(au.make_token("soc_operator", tenant=T_A))).json()
    assert GW_B not in {r["gateway_id"] for r in rows}


async def test_el_lote_exige_acceso_a_la_flota(seed: None) -> None:
    resp = await _get_all(au.make_token("inspector", tenant=T_A))
    assert resp.status_code == 403
