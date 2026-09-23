"""[A-057 · T-8.09] La fila del LWT NO es un latido, y el LWT SÍ es una desconexión.

EL DEFECTO
----------
``handle_status`` (el LWT/beacon de presencia) hace DOS cosas: mueve
``gateways.status`` (con su ``metadata->>'status_ts'``) y escribe en
``device_health`` una fila ``reason='transition'`` con TODAS las métricas en
NULL — para ``online`` y para ``offline``. Todas las lecturas del «último
latido» (flota, mapa, salud móvil, orden de sirena) tomaban la fila MÁS
RECIENTE sin mirar qué era, y NINGUNA miraba ``gateways.status``:

* ``age_s`` ≈ 0 ⇒ ``derive_fleet_state`` decía **OPERATIVO** — un gabinete
  recién CAÍDO pintado vivo durante ``sin_enlace_min``;
* todas las métricas salían S/D, así que un gabinete DEGRADADO (en batería)
  se «curaba» en cuanto reconectaba y publicaba su beacon.

Quitar la fila de presencia de «el último latido» (primer arreglo) no bastaba:
en la secuencia REAL —``keep_alive_secs=30`` en ``edge/cloud`` y un latido cada
60 s— el broker publica el LWT ~45 s después de la caída, cuando el último
latido tiene 45–105 s. Con ``sin_enlace_min=5`` la consola seguía diciendo
OPERATIVO otros 195–255 s con el gabinete YA marcado ``offline`` en la nube.

LO QUE SE FIJA
--------------
1. La fila de presencia se sigue escribiendo, pero **no cuenta como último
   latido** (``LATIDO_REAL``).
2. Un LWT ``offline`` POSTERIOR al último latido real es SIN ENLACE, tenga ese
   latido la edad que tenga (``ENLACE_PERDIDO``). Un latido o un beacon
   ``online`` posteriores lo levantan: el LWT no es una sentencia.

Las filas se escriben con el SQL DEL PROPIO HANDLER (``_STATUS_SQL`` +
``_STATUS_HEALTH_SQL``, con el MISMO ``ts``, como hace ``handle_status``): si el
escritor cambia de forma, este test lo sigue.
"""

# ruff: noqa: F811
from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from fastapi import FastAPI

import auth_utils as au
from _telemetry_fixtures import (  # noqa: F401  (fixtures cargadas por nombre)
    T_PRIV_A,
    _dsn,
    seed,
    ts_engine,
)
from takab_api.db.engine import get_engine
from takab_api.ingest.handlers import _STATUS_HEALTH_SQL, _STATUS_SQL
from takab_api.main import create_app
from takab_api.queries import mobile as qm
from takab_api.routers.fleet import router as fleet_router
from takab_api.routers.telemetry import router as telemetry_router
from takab_api.schemas.fleet import DEGRADADO, OPERATIVO, SIN_ENLACE

# Prefijo e7 (T-8.09): no colisiona con 8* (fixtures de telemetría) ni con 4*…7*.
#: Se cayó: último latido SANO hace 60 s, LWT `offline` hace 5 s.
SITE_CAIDO = "e7a00000-0000-0000-0000-000000000001"
GW_CAIDO = "e7a10000-0000-0000-0000-000000000001"
#: Reconectó: latido EN BATERÍA hace 60 s, beacon `online` hace 5 s.
SITE_DEGRADADO = "e7a00000-0000-0000-0000-000000000002"
GW_DEGRADADO = "e7a10000-0000-0000-0000-000000000002"
#: Control: su último renglón es un snapshot de TRANSICIÓN del propio gabinete
#: (con métricas). Ése SÍ es un latido y no puede caer con el filtro.
SITE_TRANSICION = "e7a00000-0000-0000-0000-000000000003"
GW_TRANSICION = "e7a10000-0000-0000-0000-000000000003"
#: Control: se cayó (LWT hace 40 s) y VOLVIÓ (beacon `online` hace 5 s).
SITE_VOLVIO = "e7a00000-0000-0000-0000-000000000004"
GW_VOLVIO = "e7a10000-0000-0000-0000-000000000004"
#: Control: LWT hace 50 s, beacon de vuelta PERDIDO, pero late hace 10 s. El
#: latido es la prueba de vida: sin el `>= h.ts`, un beacon perdido lo dejaría
#: SIN ENLACE para siempre mientras late.
SITE_SIN_BEACON = "e7a00000-0000-0000-0000-000000000005"
GW_SIN_BEACON = "e7a10000-0000-0000-0000-000000000005"

_SITIOS = [SITE_CAIDO, SITE_DEGRADADO, SITE_TRANSICION, SITE_VOLVIO, SITE_SIN_BEACON]
_GABINETES = [GW_CAIDO, GW_DEGRADADO, GW_TRANSICION, GW_VOLVIO, GW_SIN_BEACON]

_GEOM = "ST_SetSRID(ST_MakePoint(-98.20, 19.04), 4326)::geography"

#: La secuencia REAL del edge (`edge/takab_edge/cloud/__init__.py`): latido cada
#: 60 s y `keep_alive_secs=30` ⇒ el broker da la sesión por muerta a ~45 s de la
#: caída. El último latido tiene entonces 45–105 s: MUY por debajo de
#: `sin_enlace_min` (5 min). Los instantes se fijan AL SEMBRAR, no al importar.
EDAD_ULTIMO_LATIDO = timedelta(seconds=60)
EDAD_LWT = timedelta(seconds=5)


def _auth() -> dict[str, str]:
    return au.bearer(au.make_token("soc_operator", tenant=T_PRIV_A, site_scope="*", surface="web"))


def _latido(cur, gid: str, ts: datetime, *, power: str = "line", battery: float = 95.0) -> None:
    cur.execute(
        "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, "
        "mqtt_rtt_ms, seedlink_lag_s, ntp_offset_ms, cpu_temp_c, power_status, "
        "battery_pct, cert_days_remaining, relays_state) VALUES "
        "(%s, %s, %s, 'heartbeat', 42.0, 0.4, 5.0, 48.0, %s, %s, 300, 'reported')",
        (ts, T_PRIV_A, gid, power, battery),
    )


def _presencia(cur, gid: str, status: str, ts: datetime) -> None:
    """Lo que hace `handle_status` con un LWT/beacon: las DOS escrituras, mismo ts."""
    cur.execute(_STATUS_SQL, {"status": status, "gateway_id": gid, "ts": ts})
    cur.execute(_STATUS_HEALTH_SQL, (ts, T_PRIV_A, gid))


@pytest.fixture
def lwt(seed) -> Iterator[dict[str, datetime]]:
    """Cinco gabinetes; devuelve el instante REAL del último latido de cada uno."""
    ahora = datetime.now(tz=UTC)
    hb = {
        GW_CAIDO: ahora - EDAD_ULTIMO_LATIDO,
        GW_DEGRADADO: ahora - EDAD_ULTIMO_LATIDO,
        GW_TRANSICION: ahora - timedelta(seconds=30),
        GW_VOLVIO: ahora - timedelta(seconds=90),
        GW_SIN_BEACON: ahora - timedelta(seconds=10),
    }
    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        for i, sid in enumerate(_SITIOS):
            cur.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                f"VALUES (%s, %s, %s, 'Estación LWT {i}', {_GEOM}) "
                "ON CONFLICT (site_id) DO NOTHING",
                (sid, T_PRIV_A, f"LWT-{sid[-6:]}"),
            )
        for gid, sid in zip(_GABINETES, _SITIOS, strict=True):
            # Conectado: así lo deja el beacon del arranque.
            cur.execute(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, status) "
                "VALUES (%s, %s, %s, %s, 'online') ON CONFLICT (gateway_id) DO NOTHING",
                (gid, T_PRIV_A, sid, f"SN-{gid[-6:]}"),
            )
        # · el que se cayó
        _latido(cur, GW_CAIDO, hb[GW_CAIDO])
        _presencia(cur, GW_CAIDO, "offline", ahora - EDAD_LWT)
        # · el degradado que reconecta: el beacon (métricas NULL) no lo cura
        _latido(cur, GW_DEGRADADO, hb[GW_DEGRADADO], power="battery", battery=10.0)
        _presencia(cur, GW_DEGRADADO, "online", ahora - EDAD_LWT)
        # · el snapshot de transición DEL GABINETE (`HealthSnapshot.transition_reason`
        #   distinto de 'heartbeat'): `reason='transition'` y CON métricas
        _latido(cur, GW_TRANSICION, ahora - timedelta(minutes=10), battery=90.0)
        cur.execute(
            "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, seedlink_lag_s, "
            "cpu_temp_c, power_status, battery_pct) VALUES "
            "(%s, %s, %s, 'transition', 0.3, 47.0, 'line', 90.0)",
            (hb[GW_TRANSICION], T_PRIV_A, GW_TRANSICION),
        )
        # · el que se cayó y volvió
        _latido(cur, GW_VOLVIO, hb[GW_VOLVIO])
        _presencia(cur, GW_VOLVIO, "offline", ahora - timedelta(seconds=40))
        _presencia(cur, GW_VOLVIO, "online", ahora - EDAD_LWT)
        # · el que volvió sin beacon: el latido posterior manda
        _latido(cur, GW_SIN_BEACON, ahora - timedelta(seconds=120))
        _presencia(cur, GW_SIN_BEACON, "offline", ahora - timedelta(seconds=50))
        _latido(cur, GW_SIN_BEACON, hb[GW_SIN_BEACON])
        # La orden de sirena que la app juzga (`SIREN_ORDER`), sobre el caído.
        cur.execute(
            "INSERT INTO commands (tenant_id, site_id, gateway_id, issued_by, channel, "
            "action, nonce, expires_at, status) VALUES "
            "(%s, %s, %s, %s, 'siren', 'activate', %s, now() + interval '1 hour', 'acked')",
            (T_PRIV_A, SITE_CAIDO, GW_CAIDO, str(uuid.uuid4()), f"lwt-{uuid.uuid4()}"),
        )
    yield hb
    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM commands WHERE gateway_id = ANY(%s)", (_GABINETES,))
        cur.execute("DELETE FROM device_health WHERE gateway_id = ANY(%s)", (_GABINETES,))
        cur.execute("DELETE FROM gateways WHERE gateway_id = ANY(%s)", (_GABINETES,))
        cur.execute("DELETE FROM sites WHERE site_id = ANY(%s)", (_SITIOS,))


@pytest.fixture
async def client(ts_engine):
    app: FastAPI = create_app()
    app.include_router(fleet_router)
    app.include_router(telemetry_router)
    async with au.client_for(app) as c:
        yield c


def _ts(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _flota(client) -> dict[str, dict]:
    r = await client.get("/fleet/gateways", headers=_auth())
    assert r.status_code == 200, r.text
    return {g["gateway_id"]: g for g in r.json()}


async def test_flota_el_lwt_de_un_gabinete_recien_caido_es_SIN_ENLACE(client, lwt) -> None:
    """El defecto medido: latido sano de hace 60 s + LWT de hace 5 s ⇒ OPERATIVO."""
    gw = (await _flota(client))[GW_CAIDO]
    assert gw["status"] == "offline", "el fixture no reprodujo el LWT"
    assert gw["derived_state"] == SIN_ENLACE, (
        "la nube YA sabe que el broker dio la sesión por muerta y la flota lo pinta "
        "OPERATIVO porque su último latido tiene 60 s (< sin_enlace_min)"
    )
    # Y lo que se enseña es el ÚLTIMO LATIDO REAL, no una fila de métricas nulas.
    assert _ts(gw["last_heartbeat_ts"]) == lwt[GW_CAIDO]
    assert gw["battery_pct"] == 95.0
    assert gw["degrade_reasons"] == [], "en SIN ENLACE el problema es el silencio"
    # Perder el enlace no borra que LATIÓ: sin versión declarada es «NO DECLARA»
    # (latió y no la dijo), jamás «SIN REPORTAR» (nunca latió). Pasar `age_s=None`
    # a las derivaciones habría sido el arreglo corto, y habría mentido aquí.
    assert gw["version_state"] == "NO DECLARA"
    assert gw["version_age_s"] is None  # sin versión no hay dato que fechar


async def test_flota_el_beacon_no_cura_a_un_gabinete_degradado(client, lwt) -> None:
    """Con métricas NULL no hay razón que degrade: el beacon «curaba» la batería."""
    gw = (await _flota(client))[GW_DEGRADADO]
    assert gw["derived_state"] == DEGRADADO
    assert gw["degrade_reasons"], "el degradado perdió sus razones"
    assert gw["power_status"] == "battery"
    assert gw["relays_state"] == "reported"


async def test_flota_el_que_se_cayo_y_volvio_esta_operativo(client, lwt) -> None:
    """Control: el LWT no es una sentencia; el beacon `online` posterior lo levanta."""
    gw = (await _flota(client))[GW_VOLVIO]
    assert gw["status"] == "online"
    assert gw["derived_state"] == OPERATIVO


async def test_flota_un_latido_posterior_al_lwt_manda_aunque_se_pierda_el_beacon(
    client, lwt
) -> None:
    """Control: `gateways.status` sigue en `offline` (el beacon se perdió), pero
    el gabinete LATE después del LWT. Latir es estar vivo."""
    gw = (await _flota(client))[GW_SIN_BEACON]
    assert gw["status"] == "offline"
    assert gw["derived_state"] == OPERATIVO


async def test_mapa_el_enlace_sale_del_ultimo_latido_real_y_del_lwt(client, lwt) -> None:
    r = await client.get("/telemetry/map/state", headers=_auth())
    assert r.status_code == 200, r.text
    sites = {s["site_id"]: s for s in r.json()["sites"]}
    assert sites[SITE_CAIDO]["link_state"] == SIN_ENLACE
    assert _ts(sites[SITE_CAIDO]["last_heartbeat_ts"]) == lwt[GW_CAIDO]
    assert sites[SITE_DEGRADADO]["link_state"] == DEGRADADO
    assert sites[SITE_VOLVIO]["link_state"] == OPERATIVO
    assert sites[SITE_SIN_BEACON]["link_state"] == OPERATIVO


async def test_movil_la_salud_del_sitio_ve_el_lwt(lwt) -> None:
    """La app del brigadista lee `SITE_HEALTH`: la misma trampa, otra pantalla.

    `mobile_site._site_health` deriva con `derive_fleet_state(age_s=…)`: una
    edad NULL es SIN ENLACE. El instante del último contacto (`health_ts`) —lo
    que la app enseña como «último contacto hace…»— sigue siendo el real.
    """
    async with get_engine().connect() as conn:
        caido = (await conn.execute(qm.SITE_HEALTH, {"site": SITE_CAIDO})).mappings().all()
        volvio = (await conn.execute(qm.SITE_HEALTH, {"site": SITE_VOLVIO})).mappings().all()
    assert len(caido) == 1
    assert caido[0]["health_ts"] == lwt[GW_CAIDO]
    assert caido[0]["power_status"] == "line"
    assert caido[0]["age_s"] is None, "el LWT posterior al último latido es SIN ENLACE"
    assert volvio[0]["age_s"] is not None and volvio[0]["age_s"] < 300


async def test_movil_la_orden_de_sirena_no_se_corrobora_con_un_gabinete_caido(lwt) -> None:
    """`SIREN_ORDER.gateway_age_s` None ⇒ `alarma_inmueble` no corrobora con él
    (la misma rama que «el latido es viejo»)."""
    async with get_engine().connect() as conn:
        row = (
            (
                await conn.execute(
                    qm.SIREN_ORDER, {"site": SITE_CAIDO, "actor_sistema": str(uuid.uuid4())}
                )
            )
            .mappings()
            .one()
        )
    assert row["gateway_age_s"] is None


async def test_un_snapshot_de_TRANSICION_del_gabinete_si_es_un_latido(client, lwt) -> None:
    """NO-VACUIDAD del filtro: filtrar por `reason='heartbeat'` habría sido más
    corto y habría tirado también los snapshots de transición del gabinete, que
    SÍ traen métricas. Éste llegó hace 30 s: el gabinete está vivo."""
    gw = (await _flota(client))[GW_TRANSICION]
    assert gw["derived_state"] != SIN_ENLACE
    assert gw["battery_pct"] == 90.0


def test_la_fila_de_presencia_se_sigue_escribiendo() -> None:
    """NO-REGRESIÓN del escritor: la fila se conserva (huella de reconexión y de
    «retirado + vivo»); lo que cambia es que las LECTURAS no la toman por latido.
    """
    assert "device_health" in _STATUS_HEALTH_SQL
    assert "'transition'" in _STATUS_HEALTH_SQL
    assert "status_ts" in _STATUS_SQL, "ENLACE_PERDIDO compara contra esta marca"
