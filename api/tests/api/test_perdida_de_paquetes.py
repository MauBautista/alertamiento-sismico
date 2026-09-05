"""La pérdida de paquetes llega al centro de operaciones (T-5.24).

El gabinete la mide y la publica en CADA latido, y la ingesta la tiraba a
propósito: `device_health` no tenía columna. Consecuencia medida: **el SOC no
podía ver la pérdida de paquetes de ningún gabinete**, y para diagnosticar un
enlace sensor→Pi degradado había que ir al sitio o abrir el panel por red local —
justo el viaje que la flota existe para evitar.

Y es la señal que se degrada **antes** de que falten datos: cuando el hueco
aparece en `seedlink_lag_s`, la ventana de evidencia ya se perdió.
"""

# ruff: noqa: F811
from __future__ import annotations

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine


async def _sql(sql: str, **p):
    engine = get_engine()
    async with engine.begin() as conn:
        r = await conn.execute(text(sql), p)
        return r.fetchall() if r.returns_rows else []


@pytest.fixture(autouse=True)
async def _limpio():
    yield
    await _sql("DELETE FROM device_health WHERE gateway_id = :g", g=GW)
    await _sql("DELETE FROM gateways WHERE gateway_id = :g", g=GW)


async def _latido(gateway: str, *, perdida: float | None) -> None:
    await _sql(
        "INSERT INTO device_health (ts, tenant_id, gateway_id, reason, seedlink_lag_s,"
        " packet_loss_pct) VALUES (now(), :t, :g, 'heartbeat', 0.4, :p)",
        t=au.DB_TENANT_PRIV,
        g=gateway,
        p=perdida,
    )


#: Gabinete propio del módulo: el seed de `base_data` no trae ninguno, y
#: apoyarse en uno ajeno haría que este test dependiera del orden de la suite.
GW = "7d000000-0000-0000-0000-0000000000d1"


async def _gateway() -> str:
    await _sql(
        "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) "
        "VALUES (:g, :t, :s, 'GW-T524') ON CONFLICT DO NOTHING",
        g=GW,
        t=au.DB_TENANT_PRIV,
        s=au.DB_SITE_PRIV,
    )
    return GW


async def test_la_perdida_de_paquetes_LLEGA_a_la_flota(client, base_data):
    gw = await _gateway()
    await _latido(gw, perdida=7.5)

    r = await client.get(
        "/fleet/gateways",
        headers=au.bearer(au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, site_scope="*")),
    )
    assert r.status_code == 200, r.text
    fila = next(g for g in r.json() if g["gateway_id"] == gw)
    assert fila["packet_loss_pct"] == pytest.approx(7.5)


async def test_sin_dato_sale_NULL_y_no_un_cero(client, base_data):
    """Un cero diría «enlace perfecto», que es lo contrario de «no sabemos»."""
    gw = await _gateway()
    await _latido(gw, perdida=None)

    r = await client.get(
        "/fleet/gateways",
        headers=au.bearer(au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, site_scope="*")),
    )
    fila = next(g for g in r.json() if g["gateway_id"] == gw)
    assert fila["packet_loss_pct"] is None


async def test_la_perdida_NO_degrada_el_estado_por_su_cuenta(client, base_data):
    """Deliberado, y escrito: falta el umbral de SERVIDOR, no cualquier umbral.

    El gabinete tiene el suyo —su panel pinta ámbar al 1 % y rojo al 10 %—, pero
    ése es consejo para quien está delante del Pi. Degradar `derived_state`
    arrastra la pill del SOC, la app móvil y el reparto de alarmas: es otra
    decisión, y no la ha tomado nadie.

    Lo que esta tarea pedía es que se pueda VER. El día que se decida, entra en
    `fleet_degrade_reasons` con su ajuste, como las demás métricas.
    """
    gw = await _gateway()
    await _latido(gw, perdida=99.0)

    r = await client.get(
        "/fleet/gateways",
        headers=au.bearer(au.make_token("soc_operator", tenant=au.DB_TENANT_PRIV, site_scope="*")),
    )
    fila = next(g for g in r.json() if g["gateway_id"] == gw)
    assert fila["packet_loss_pct"] == pytest.approx(99.0)
    assert "packet_loss" not in " ".join(fila.get("degrade_reasons", []))


def test_el_handler_de_salud_PERSISTE_la_perdida():
    """El mapeo que faltaba, en el sitio donde se decidía tirarla."""
    from takab_api.ingest import handlers

    assert "packet_loss_pct" in handlers._HEALTH_SQL
    # Y el docstring ya no dice que sea consumo local: decía las dos cosas.
    assert "T-5.24" in (handlers.handle_health_snapshot.__doc__ or ""), (
        "el docstring sigue afirmando que la pérdida no tiene columna destino"
    )
