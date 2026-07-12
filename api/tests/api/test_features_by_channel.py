"""Strip multicanal (T-1.34): un canal por traza, agrupado server-side.

El RS4D entrega EHZ (geófono, velocidad) y ENZ/ENN/ENE (acelerómetro, 3 ejes). El strip
de la consola los colapsa en un pico por segundo; la vista del edificio los separa. Todo
sigue siendo features 1 s de la vista segura — **nunca waveform crudo** (regla de oro 9).
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import psycopg

import auth_utils as au
from _telemetry_fixtures import (  # noqa: F401  (fixtures cargadas por nombre)
    S_A,
    S_B,
    SENSOR_A,
    T_PRIV_A,
    T_PRIV_B,
    _dsn,
    seed,
    telemetry_app,
    telemetry_client,
    ts_engine,
)


def _auth(role: str = "soc_operator", tenant: str = T_PRIV_A) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*", surface="web"))


def _seed_channels(*channels: str) -> None:
    """Añade una muestra reciente por canal al sitio A."""
    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        for i, ch in enumerate(channels):
            cur.execute(
                "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, "
                "channel, pga_g, pgv_cms, stalta, clipping) VALUES "
                "(now() - (%s || ' seconds')::interval, %s, %s, %s, %s, "
                "0.2, 2.0, 3.0, false) ON CONFLICT DO NOTHING",
                (str(10 + i), T_PRIV_A, S_A, SENSOR_A, ch),
            )


async def test_groups_by_channel_in_a_single_request(telemetry_client, seed) -> None:
    _seed_channels("ENZ", "ENN", "ENE")
    r = await telemetry_client.get(f"/telemetry/sites/{S_A}/features/by-channel", headers=_auth())
    assert r.status_code == 200, r.text
    body = r.json()

    names = [c["channel"] for c in body["channels"]]
    assert names == sorted(names), "orden estable: la UI no reordena trazas entre polls"
    assert set(names) == {"EHZ", "ENZ", "ENN", "ENE"}

    ehz = next(c for c in body["channels"] if c["channel"] == "EHZ")
    assert len(ehz["ts"]) == len(ehz["pga"]) == len(ehz["clipping"]) == 3
    assert ehz["ts"] == sorted(ehz["ts"]), "cada traza va en orden temporal ascendente"
    # El seed clipea la muestra más VIEJA (offset 90 s) ⇒ primera en orden ascendente.
    assert ehz["clipping"] == [True, False, False]


async def test_absent_channel_is_absent_not_flat(telemetry_client, seed) -> None:
    """Un canal sin datos NO aparece. Una traza plana en cero sería un sensor mintiendo
    'todo tranquilo' cuando en realidad no está reportando."""
    r = await telemetry_client.get(f"/telemetry/sites/{S_A}/features/by-channel", headers=_auth())
    assert [c["channel"] for c in r.json()["channels"]] == ["EHZ"]


async def test_carries_the_calibration_flag(telemetry_client, seed) -> None:
    assert (
        await telemetry_client.get(f"/telemetry/sites/{S_A}/features/by-channel", headers=_auth())
    ).json()["calibrated"] is False


async def test_span_over_two_hours_rejected(telemetry_client, seed) -> None:
    r = await telemetry_client.get(
        f"/telemetry/sites/{S_A}/features/by-channel",
        params={"from": "2026-07-01T00:00:00Z", "to": "2026-07-01T03:00:00Z"},
        headers=_auth(),
    )
    assert r.status_code == 422


async def test_cross_tenant_site_returns_no_channels(telemetry_client, seed) -> None:
    """RLS (por la vista segura) tapa las features de B: cero canales, nunca un 500."""
    r = await telemetry_client.get(f"/telemetry/sites/{S_B}/features/by-channel", headers=_auth())
    assert r.status_code == 200
    assert r.json()["channels"] == []


async def test_mobile_only_role_forbidden(telemetry_client, seed) -> None:
    r = await telemetry_client.get(
        f"/telemetry/sites/{S_A}/features/by-channel",
        headers=au.bearer(
            au.make_token("occupant", tenant=T_PRIV_A, site_scope="*", surface="mobile")
        ),
    )
    assert r.status_code == 403
