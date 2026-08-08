"""[T-2.70.a · B1] El SOC deja de ver verde un gabinete sin dueño de pines.

Dos planos, como en `test_fleet_versions.py`:

1. **Unit puro de la derivación** — `fleet_degrade_reasons`/`derive_fleet_state`
   son la VERDAD ÚNICA del estado de un gabinete. Si «relés ilegibles» no entra
   ahí, entra en la UI, y entonces la Flota, el mapa y la app móvil pueden contar
   tres historias del mismo edificio.
2. **Endpoint** — el censo de relés viaja en `GET /fleet/gateways` y el gabinete
   huérfano sale DEGRADADO con su pill, no OPERATIVO.

Lo que se está midiendo es una frase, no un campo: *un gabinete cuyo latido no
pudo decir en qué estado están la sirena, el gas, los ascensores y los
retenedores NO es un gabinete operativo*.
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
    DEGRADADO,
    OPERATIVO,
    RELAYS_ILEGIBLES,
    RELAYS_REPORTED,
    RELAYS_STOPPED,
    RELAYS_UNREADABLE,
    SIN_ENLACE,
    derive_fleet_state,
    fleet_degrade_reasons,
)

# ---- unit puro: la derivación (verdad única, sin DB) ------------------------

_SANO: dict = {
    "power_status": "line",
    "battery_pct": 100.0,
    "cert_days_remaining": 300,
    "mqtt_rtt_ms": 40.0,
    "seedlink_lag_s": 0.4,
    "ntp_offset_ms": 5.0,
}
_LIMITES: dict = {
    "battery_min_pct": 30.0,
    "cert_min_days": 30,
    "mqtt_rtt_max_ms": 500.0,
    "seedlink_lag_max_s": 15.0,
    "ntp_offset_max_ms": 250.0,
}


def _razones(**over: object) -> list[str]:
    args: dict = {**_SANO, **_LIMITES}
    args.update(over)
    return fleet_degrade_reasons(**args)


def _estado(**over: object) -> str:
    args: dict = {"age_s": 30.0, "sin_enlace_s": 300.0, **_SANO, **_LIMITES}
    args.update(over)
    return derive_fleet_state(**args)


def test_los_reles_ilegibles_degradan_el_gabinete() -> None:
    """EL CRITERIO, en la función que decide el color de la tarjeta.

    Con `TAKAB_EDGE_GPIO_OWNER=gpio` y `takab-gpio` caído, `takab-edge` late
    perfectamente: todas las métricas están sanas y `gateway_offline` no dispara.
    Lo único que delata al edificio sin protección es este campo.
    """
    assert RELAYS_ILEGIBLES in _razones(relays_state=RELAYS_UNREADABLE)
    assert _estado(relays_state=RELAYS_UNREADABLE) == DEGRADADO


def test_un_gabinete_con_su_censo_de_reles_sigue_operativo() -> None:
    """NO-VACUIDAD: si el rótulo degradara siempre, la flota entera se pondría
    ámbar y el operador aprendería a ignorarlo."""
    assert _razones(relays_state=RELAYS_REPORTED) == []
    assert _estado(relays_state=RELAYS_REPORTED) == OPERATIVO


def test_sin_opinion_sobre_los_reles_no_se_degrada_ni_se_inventa() -> None:
    """Compatibilidad hacia atrás: un firmware que no manda la clave no opina.

    `None` NUNCA degrada — misma regla que el resto de métricas del contrato
    honesto (T-1.40): no tener UPS no es estar en batería, y no saber nada de los
    relés no es saber que están rotos. Lo que NO puede pasar es que se pinte
    verde: eso lo resuelve la consola con S/D, no la derivación.
    """
    assert _razones(relays_state=None) == []
    assert _estado(relays_state=None) == OPERATIVO


def test_el_modulo_detenido_no_degrada_pero_tampoco_es_un_censo() -> None:
    """`[]` es ambiguo en firmware ≤1.9.0 (podía ser también «no pude preguntar»),
    y degradar sobre un dato ambiguo entrena al operador a ignorar la pantalla.

    Se registra como hecho y la consola lo pinta S/D; el rótulo que grita queda
    reservado al caso INEQUÍVOCO.
    """
    assert _razones(relays_state=RELAYS_STOPPED) == []


def test_el_silencio_manda_sobre_los_reles() -> None:
    """Un gabinete callado es SIN ENLACE, no DEGRADADO: su último censo de relés
    es un dato viejo y no describe lo que pasa ahora (misma doctrina que T-2.69).
    """
    assert _estado(age_s=9999.0, relays_state=RELAYS_UNREADABLE) == SIN_ENLACE


def test_los_reles_ilegibles_conviven_con_las_otras_razones() -> None:
    """No sustituye a nada: un gabinete puede estar en batería Y sin dueño de pines."""
    razones = _razones(relays_state=RELAYS_UNREADABLE, power_status="battery")
    assert RELAYS_ILEGIBLES in razones
    assert "EN BATERÍA" in razones


# ---- endpoint ---------------------------------------------------------------

# Prefijo 70 (T-2.70.a): no colisiona con 69 (versiones), 5* (ghosts), 4*
# (health-history), 65* (equipment) ni con los seeds sync/async.
T_A = "70111111-1111-1111-1111-111111111111"
S_A = "70a00000-0000-0000-0000-0000000000a1"
GW_SANO = "70d00000-0000-0000-0000-0000000000d1"  # censo de relés publicado
GW_HUERFANO = "70d00000-0000-0000-0000-0000000000d2"  # late y NADIE tiene los pines
GW_DETENIDO = "70d00000-0000-0000-0000-0000000000d3"  # preguntó y no hay filas
GW_VIEJO = "70d00000-0000-0000-0000-0000000000d4"  # firmware que no opina

_GEOM = "ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography"
_CLEANUP = (
    text("DELETE FROM device_health WHERE tenant_id = :t"),
    text("DELETE FROM gateways WHERE tenant_id = :t"),
    text("DELETE FROM sites WHERE tenant_id = :t"),
    text("DELETE FROM tenants WHERE tenant_id = :t"),
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


async def _limpiar() -> None:
    async with get_engine().begin() as conn:
        for stmt in _CLEANUP:
            await conn.execute(stmt, {"t": T_A})


@pytest.fixture
async def seed() -> None:
    """Cuatro gabinetes idénticos salvo por lo que su latido dice de los relés."""
    await _limpiar()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO tenants (tenant_id, code, name, visibility) "
                "VALUES (:id, 'T270A', 'T-2.70.a', 'private')"
            ),
            {"id": T_A},
        )
        await conn.execute(
            text(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                f"VALUES (:sid, :tid, 'S270A', 'Sitio', {_GEOM})"
            ),
            {"sid": S_A, "tid": T_A},
        )
        for gw, serial, estado in (
            (GW_SANO, "GW-SANO", RELAYS_REPORTED),
            (GW_HUERFANO, "GW-HUERFANO", RELAYS_UNREADABLE),
            (GW_DETENIDO, "GW-DETENIDO", RELAYS_STOPPED),
            (GW_VIEJO, "GW-VIEJO", None),
        ):
            await conn.execute(
                text(
                    "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) "
                    "VALUES (:gw, :t, :s, :serial)"
                ),
                {"gw": gw, "t": T_A, "s": S_A, "serial": serial},
            )
            # Latido FRESCO y por lo demás perfecto: es justo el punto del bug.
            await conn.execute(
                text(
                    "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, "
                    "power_status, battery_pct, cert_days_remaining, mqtt_rtt_ms, "
                    "seedlink_lag_s, ntp_offset_ms, relays_state) "
                    "VALUES (now(), :t, :gw, 'heartbeat', 'line', 100.0, 365, 40.0, "
                    "0.4, 5.0, :estado)"
                ),
                {"t": T_A, "gw": gw, "estado": estado},
            )
    yield
    await _limpiar()
    await engine.dispose()
    get_engine.cache_clear()


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(fleet_router)
    return app


async def _get(path: str, token: str):
    async with au.client_for(_app()) as c:
        return await c.get(path, headers=au.bearer(token))


async def test_la_consola_recibe_el_censo_de_reles_de_cada_gabinete(seed: None) -> None:
    resp = await _get("/fleet/gateways", au.make_token("soc_operator", tenant=T_A))
    assert resp.status_code == 200
    por_serial = {g["serial"]: g["relays_state"] for g in resp.json()}
    assert por_serial == {
        "GW-SANO": RELAYS_REPORTED,
        "GW-HUERFANO": RELAYS_UNREADABLE,
        "GW-DETENIDO": RELAYS_STOPPED,
        "GW-VIEJO": None,
    }


async def test_el_gabinete_huerfano_no_sale_operativo(seed: None) -> None:
    """El defecto medido, de punta a punta: mismo latido sano, distinto veredicto."""
    resp = await _get("/fleet/gateways", au.make_token("soc_operator", tenant=T_A))
    filas = {g["serial"]: g for g in resp.json()}
    assert filas["GW-SANO"]["derived_state"] == OPERATIVO
    assert filas["GW-HUERFANO"]["derived_state"] == DEGRADADO, (
        "un edificio sin sirena, sin cierre de gas, sin retorno de ascensores y "
        "sin retenedores sigue saliendo verde en el SOC"
    )
    assert RELAYS_ILEGIBLES in filas["GW-HUERFANO"]["degrade_reasons"]
    assert filas["GW-SANO"]["degrade_reasons"] == []
    # NO-VACUIDAD: los otros dos no se contagian del rótulo.
    assert filas["GW-DETENIDO"]["derived_state"] == OPERATIVO
    assert filas["GW-VIEJO"]["derived_state"] == OPERATIVO
