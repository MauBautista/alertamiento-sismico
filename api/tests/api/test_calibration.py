"""Honestidad de calibración (T-1.33): PGA/PGV no son ``g``/``cm/s`` hasta probarlo.

Las sensibilidades de ``edge/takab_edge/config/settings.py`` (``SignalConfig``) son
PLACEHOLDER hasta que llegue el StationXML del RS4D. El algoritmo de las features está
validado contra ObsPy; la escala física NO. Estos tests fijan la única regla que impide
que la consola mienta: un sitio está calibrado **solo si todos sus sensores activos
declaran de dónde salió su respuesta instrumental**, y ante la duda no lo está.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

from sqlalchemy import text

import auth_utils as au
from _telemetry_fixtures import (  # noqa: F401  (fixtures cargadas por nombre)
    S_A,
    SENSOR_A,
    T_PRIV_A,
    seed,
    telemetry_app,
    telemetry_client,
    ts_engine,
)
from takab_api.db.engine import get_engine


def _auth(role: str = "soc_operator", tenant: str = T_PRIV_A) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*", surface="web"))


async def _set_calibration(sensor_id: str, source: str | None) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            text("UPDATE sensors SET calibration_source = :src WHERE sensor_id = :id"),
            {"src": source, "id": sensor_id},
        )


async def _add_sensor(sensor_id: str, *, source: str | None, status: str = "active") -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model, "
                "status, calibration_source) "
                "VALUES (:id, :t, :s, 'structural', 'RS4D', :st, :src)"
            ),
            {"id": sensor_id, "t": T_PRIV_A, "s": S_A, "st": status, "src": source},
        )


async def _features_calibrated(telemetry_client) -> bool:
    r = await telemetry_client.get(f"/telemetry/sites/{S_A}/features", headers=_auth())
    assert r.status_code == 200, r.text
    return r.json()["calibrated"]


async def test_uncalibrated_by_default(telemetry_client, seed) -> None:
    """El sensor sembrado no declara procedencia ⇒ el sitio NO está calibrado.

    Este es el estado real del sistema hoy: T-1.6 (metadata del RS4D) está diferida.
    """
    assert await _features_calibrated(telemetry_client) is False


async def test_declaring_the_source_calibrates_the_site(telemetry_client, seed) -> None:
    await _set_calibration(SENSOR_A, "stationxml:AM.R4F74.2026-07-09")
    assert await _features_calibrated(telemetry_client) is True


async def test_one_uncalibrated_sensor_uncalibrates_the_whole_site(telemetry_client, seed) -> None:
    """Un solo sensor sin respuesta instrumental basta: el strip del sitio los mezcla.

    Presentar el máximo de un canal calibrado y otro sin calibrar como una sola cifra
    en ``g`` sería un número sin significado físico.
    """
    await _set_calibration(SENSOR_A, "stationxml:AM.R4F74")
    await _add_sensor("8d100000-0000-0000-0000-0000000000d9", source=None)
    assert await _features_calibrated(telemetry_client) is False


async def test_retired_sensors_do_not_block_calibration(telemetry_client, seed) -> None:
    """Un sensor retirado ya no mide: no puede impedir que el sitio se declare calibrado."""
    await _set_calibration(SENSOR_A, "stationxml:AM.R4F74")
    await _add_sensor("8d200000-0000-0000-0000-0000000000da", source=None, status="retired")
    assert await _features_calibrated(telemetry_client) is True


async def test_metrics_carry_the_same_flag(telemetry_client, seed) -> None:
    """El histórico (caggs) hereda el mismo `max_pga_g` sin calibrar: mismo aviso."""
    r = await telemetry_client.get(f"/telemetry/sites/{S_A}/metrics", headers=_auth())
    assert r.status_code == 200, r.text
    assert r.json()["calibrated"] is False

    await _set_calibration(SENSOR_A, "stationxml:AM.R4F74")
    r2 = await telemetry_client.get(f"/telemetry/sites/{S_A}/metrics", headers=_auth())
    assert r2.json()["calibrated"] is True


async def test_site_without_visible_sensors_is_not_calibrated(telemetry_client, seed) -> None:
    """``bool_and`` sobre cero filas devuelve NULL. Default-deny: NULL ⇒ False, no True."""
    async with get_engine().begin() as conn:
        await conn.execute(
            text("UPDATE sensors SET status = 'retired' WHERE sensor_id = :id"),
            {"id": SENSOR_A},
        )
    assert await _features_calibrated(telemetry_client) is False
