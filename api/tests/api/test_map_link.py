"""T-2.46 · El enlace del gabinete viaja en el estado del mapa.

El mapa coloreaba cada estación por la sacudida que MIDIÓ (`felt`) y no decía
absolutamente nada sobre si ese gabinete sigue vivo. Un punto verde podía
significar "todo bien" o "llevo seis horas sin datos y este color es un
recuerdo" — que es exactamente lo que prohíbe la regla de oro 7.

Aquí se prueba que el servidor entrega el enlace ya derivado (misma verdad que
`derive_fleet_state`, jamás una segunda opinión) y que **SIN GABINETE no se
colapsa con SIN ENLACE**: "no hay hardware instalado" y "el hardware perdió el
enlace" son hechos distintos y accionables de forma distinta.
"""

# Los fixtures se importan por nombre y se reciben como parámetros de test: ruff lo
# lee como redefinición del import (F811). Patrón estándar de pytest.
# ruff: noqa: F811
from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

import auth_utils as au
from _telemetry_fixtures import (  # noqa: F401  (fixtures cargadas por nombre)
    S_A,
    T_PRIV_A,
    _dsn,
    seed,
    telemetry_app,
    telemetry_client,
    ts_engine,
)

# Sitios propios de este archivo (prefijo 8a46 → no colisiona con los del fixture).
SITE_SIN_GW = "8a460000-0000-0000-0000-000000000001"
SITE_SIN_HB = "8a460000-0000-0000-0000-000000000002"
SITE_OK = "8a460000-0000-0000-0000-000000000003"
SITE_DEG = "8a460000-0000-0000-0000-000000000004"
SITE_VIEJO = "8a460000-0000-0000-0000-000000000005"
SITE_GW_RETIRADO = "8a460000-0000-0000-0000-000000000006"

GW_SIN_HB = "8a461000-0000-0000-0000-000000000002"
GW_OK = "8a461000-0000-0000-0000-000000000003"
GW_DEG = "8a461000-0000-0000-0000-000000000004"
GW_VIEJO = "8a461000-0000-0000-0000-000000000005"
GW_RETIRADO = "8a461000-0000-0000-0000-000000000006"

_GEOM = "ST_SetSRID(ST_MakePoint(-98.20, 19.04), 4326)::geography"


def _auth() -> dict[str, str]:
    return au.bearer(au.make_token("soc_operator", tenant=T_PRIV_A, site_scope="*", surface="web"))


@pytest.fixture
def enlaces(seed) -> Iterator[None]:
    """Seis estaciones del tenant A, una por cada estado de enlace posible.

    Se limpia ANTES que el teardown de ``ts_engine`` (que borra sitios del tenant):
    con gateways colgando, ese DELETE reventaría por la FK.
    """
    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        for sid in (
            SITE_SIN_GW,
            SITE_SIN_HB,
            SITE_OK,
            SITE_DEG,
            SITE_VIEJO,
            SITE_GW_RETIRADO,
        ):
            cur.execute(
                "INSERT INTO sites (site_id, tenant_id, code, name, geom) "
                f"VALUES (%s, %s, %s, 'Estación enlace', {_GEOM}) "
                "ON CONFLICT (site_id) DO NOTHING",
                (sid, T_PRIV_A, sid[-6:]),
            )
        for gid, sid, status in (
            (GW_SIN_HB, SITE_SIN_HB, "online"),
            (GW_OK, SITE_OK, "online"),
            (GW_DEG, SITE_DEG, "online"),
            (GW_VIEJO, SITE_VIEJO, "online"),
            (GW_RETIRADO, SITE_GW_RETIRADO, "retired"),
        ):
            cur.execute(
                "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, status) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (gateway_id) DO NOTHING",
                (gid, T_PRIV_A, sid, f"SN-{gid[-6:]}", status),
            )
        # Latidos: sano / degradado por RTT / viejo (fuera de sin_enlace_min = 5 min).
        for gid, age_s, rtt in ((GW_OK, 20, 42.0), (GW_DEG, 20, 3000.0), (GW_VIEJO, 3600, 42.0)):
            cur.execute(
                "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, "
                "mqtt_rtt_ms, seedlink_lag_s, ntp_offset_ms, power_status, battery_pct, "
                "cert_days_remaining) VALUES "
                "(now() - (%s || ' seconds')::interval, %s, %s, 'heartbeat', "
                "%s, 1.2, 8.0, 'mains', 100, 300) ON CONFLICT DO NOTHING",
                (str(age_s), T_PRIV_A, gid, rtt),
            )
    yield
    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM device_health WHERE tenant_id = %s", (T_PRIV_A,))
        cur.execute("DELETE FROM gateways WHERE tenant_id = %s", (T_PRIV_A,))
        cur.execute(
            "DELETE FROM sites WHERE site_id = ANY(%s)",
            (
                [
                    SITE_SIN_GW,
                    SITE_SIN_HB,
                    SITE_OK,
                    SITE_DEG,
                    SITE_VIEJO,
                    SITE_GW_RETIRADO,
                ],
            ),
        )


async def _sites(telemetry_client) -> dict[str, dict]:
    r = await telemetry_client.get("/telemetry/map/state", headers=_auth())
    assert r.status_code == 200, r.text
    return {s["site_id"]: s for s in r.json()["sites"]}


async def test_sitio_sin_gabinete_no_se_confunde_con_enlace_caido(
    telemetry_client, enlaces
) -> None:
    """El cuarto valor NECESARIO: no hay hardware ≠ el hardware calló.

    Colapsarlos mandaría a un técnico a revisar la antena de un edificio donde
    todavía no se ha instalado nada.
    """
    sites = await _sites(telemetry_client)
    assert sites[SITE_SIN_GW]["link_state"] == "SIN GABINETE"
    assert sites[SITE_SIN_HB]["link_state"] == "SIN ENLACE"
    assert sites[SITE_SIN_GW]["link_state"] != sites[SITE_SIN_HB]["link_state"]


async def test_gabinete_retirado_es_SIN_GABINETE_no_un_enlace_muerto(
    telemetry_client, enlaces
) -> None:
    """Un gabinete dado de baja dejó de ser hardware de la estación."""
    sites = await _sites(telemetry_client)
    assert sites[SITE_GW_RETIRADO]["link_state"] == "SIN GABINETE"
    assert sites[SITE_GW_RETIRADO]["last_heartbeat_ts"] is None


async def test_enlace_vivo_y_sano_es_OPERATIVO_con_sus_metricas(telemetry_client, enlaces) -> None:
    sites = await _sites(telemetry_client)
    site = sites[SITE_OK]
    assert site["link_state"] == "OPERATIVO"
    assert site["link_reasons"] == []
    assert site["last_heartbeat_ts"] is not None
    assert site["mqtt_rtt_ms"] == pytest.approx(42.0, abs=0.5)
    assert site["seedlink_lag_s"] == pytest.approx(1.2, abs=0.1)


async def test_metrica_fuera_de_rango_es_DEGRADADO_y_DICE_cual(telemetry_client, enlaces) -> None:
    """Las razones son la misma lista de `fleet_degrade_reasons`: verdad única.

    Sin ellas el operador ve "DEGRADADO" y tiene que adivinar cuál de seis
    métricas se salió de rango.
    """
    sites = await _sites(telemetry_client)
    site = sites[SITE_DEG]
    assert site["link_state"] == "DEGRADADO"
    assert any(r.startswith("MQTT") for r in site["link_reasons"]), site["link_reasons"]


async def test_latido_viejo_es_SIN_ENLACE_y_sin_razones(telemetry_client, enlaces) -> None:
    """En SIN ENLACE el problema es el SILENCIO, no una métrica: razones vacías.

    Y el último latido conocido SIGUE viajando: es lo que permite a la UI decir
    "hace 1 h" en vez de dejar el color como si fuera una lectura viva.
    """
    sites = await _sites(telemetry_client)
    site = sites[SITE_VIEJO]
    assert site["link_state"] == "SIN ENLACE"
    assert site["link_reasons"] == []
    assert site["last_heartbeat_ts"] is not None


async def test_el_enlace_no_toca_el_color_de_sacudida(telemetry_client, enlaces) -> None:
    """`felt` y `link_state` son ortogonales: uno mide el suelo, otro la red.

    Si el enlace pudiera cambiar `felt`, el mapa estaría mintiendo sobre lo que
    el edificio sintió cada vez que se cae una antena.
    """
    sites = await _sites(telemetry_client)
    # S_A midió por encima de su umbral y NO tiene gabinete sembrado aquí.
    assert sites[S_A]["felt"] == "trip"
    assert sites[S_A]["link_state"] == "SIN GABINETE"


async def test_el_enlace_es_aditivo_no_rompe_el_contrato_previo(telemetry_client, enlaces) -> None:
    """Los campos viejos del mapa siguen exactamente donde estaban."""
    sites = await _sites(telemetry_client)
    site = sites[S_A]
    assert {"site_id", "name", "lon", "lat", "felt", "calibrated", "open_incident"} <= set(site)
    assert {"link_state", "link_reasons", "last_heartbeat_ts", "mqtt_rtt_ms", "seedlink_lag_s"} <= (
        set(site)
    )
