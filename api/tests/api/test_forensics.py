"""T-2.40 · `GET /incidents/{id}/forensics`: los hechos medidos, una sola fuente.

Alimenta la pantalla Y el dictamen PDF. Dos rutas distintas para los mismos números
acabarían discrepando, y un dictamen que no coincide con lo que el operador vio en la
consola es peor que ninguno.

El invariante que más importa aquí: **este endpoint lee por la VISTA SEGURA**. Corre
como `takab_app` bajo la RLS del request, y `waveform_features_1s_secure` es lo único
que impide leer la telemetría de otro cliente desde HTTP. El contract-test
`tests/contracts/test_waveform_view.py` lo ancla estáticamente; aquí se comprueba en
caliente con dos tenants.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.routers.forensics import router as forensics_router
from tests.api.conftest import SENSOR_PRIV, SENSOR_PRIV2

_OPENED = datetime(2026, 8, 3, 10, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
async def _clean_features(base_data):
    """`waveform_features_1s` NO está en el TRUNCATE del conftest.

    Es una hypertable con caggs encima y el conftest la deja fuera a propósito. Sin
    esta limpieza, las features de un test se filtran al siguiente y chocan con la PK
    `(ts, sensor_id, channel)` — o peor, contaminan un pico y el fallo parece de la
    consulta.
    """
    yield
    async with get_engine().begin() as conn:
        await conn.execute(
            text("DELETE FROM waveform_features_1s WHERE ts >= :from"),
            {"from": _OPENED - timedelta(days=1)},
        )


def _token(role: str = "soc_operator", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _features(site_id: str, rows: list[tuple[int, str, float, float]]) -> None:
    """Siembra features de 1 s: `(offset_s, canal, pga_g, pgv_cms)` desde `_OPENED`."""
    async with get_engine().begin() as conn:
        for offset, channel, pga, pgv in rows:
            await conn.execute(
                text(
                    "INSERT INTO waveform_features_1s "
                    "(ts, tenant_id, site_id, sensor_id, channel, pga_g, pgv_cms, "
                    " rms, stalta, energy, clipping) "
                    "SELECT :ts, s.tenant_id, :site, :sensor, :ch, :pga, :pgv, "
                    "       0.01, 4.2, 1.5, false FROM sites s WHERE s.site_id = :site"
                ),
                {
                    "ts": _OPENED + timedelta(seconds=offset),
                    "site": site_id,
                    "sensor": SENSOR_PRIV if site_id == au.DB_SITE_PRIV else SENSOR_PRIV2,
                    "ch": channel,
                    "pga": pga,
                    "pgv": pgv,
                },
            )


async def _get(client, incident_id: str, token: dict[str, str] | None = None):
    return await client.get(f"/incidents/{incident_id}/forensics", headers=token or _token())


def _app_with_forensics(app):
    app.include_router(forensics_router)
    return app


# ---- picos por canal ---------------------------------------------------------


async def test_devuelve_el_pico_por_canal_en_la_ventana(client, app, make_incident) -> None:
    _app_with_forensics(app)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED)
    await _features(
        au.DB_SITE_PRIV,
        [(10, "ENZ", 0.081, 3.2), (20, "ENZ", 0.045, 1.1), (10, "ENN", 0.030, 0.9)],
    )

    resp = await _get(client, iid)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    by_channel = {c["channel"]: c for c in body["channels"]}
    assert by_channel["ENZ"]["peak_pga_g"] == pytest.approx(0.081)
    assert by_channel["ENN"]["peak_pga_g"] == pytest.approx(0.030)
    assert body["peak_pga_g"] == pytest.approx(0.081)


async def test_la_ventana_es_asimetrica_como_la_del_dictamen(client, app, make_incident) -> None:
    """La sacudida llega DESPUÉS de la alerta: una ventana centrada perdería el pico."""
    _app_with_forensics(app)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED)
    # +120 s entra (post = 180 s); −60 s no (pre = 5 s).
    await _features(au.DB_SITE_PRIV, [(120, "ENZ", 0.2, 6.0), (-60, "ENZ", 0.9, 20.0)])

    body = (await _get(client, iid)).json()
    assert body["peak_pga_g"] == pytest.approx(0.2), (
        "el pico anterior a la ventana no debe contarse"
    )


async def test_sin_features_no_inventa_ceros(client, app, make_incident) -> None:
    """Regla de oro 7: "no se midió" y "se midió 0" son hechos distintos."""
    _app_with_forensics(app)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED)

    body = (await _get(client, iid)).json()
    assert body["channels"] == []
    assert body["peak_pga_g"] is None
    assert body["peak_ts"] is None


# ---- tiempo de aviso ganado --------------------------------------------------


async def test_el_tiempo_de_aviso_solo_existe_con_sasmex(client, app, make_incident) -> None:
    _app_with_forensics(app)
    iid = await make_incident(
        au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED, trigger="sasmex"
    )
    await _features(au.DB_SITE_PRIV, [(35, "ENZ", 0.1, 4.0)])

    body = (await _get(client, iid)).json()
    assert body["lead_time_s"] == 35.0
    assert body["lead_time_reason"] is None


async def test_sin_sasmex_el_tiempo_de_aviso_es_null_con_razon(client, app, make_incident) -> None:
    """Con umbral local la "alerta" ES la sacudida: el número sería 0 por
    construcción y presentarlo como tiempo ganado sería una cifra inventada."""
    _app_with_forensics(app)
    iid = await make_incident(
        au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED, trigger="local_threshold"
    )
    await _features(au.DB_SITE_PRIV, [(35, "ENZ", 0.1, 4.0)])

    body = (await _get(client, iid)).json()
    assert body["lead_time_s"] is None
    assert body["lead_time_reason"] == "not_sasmex"


async def test_sin_pico_el_tiempo_de_aviso_dice_por_que(client, app, make_incident) -> None:
    _app_with_forensics(app)
    iid = await make_incident(
        au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED, trigger="sasmex"
    )
    body = (await _get(client, iid)).json()
    assert (body["lead_time_s"], body["lead_time_reason"]) == (None, "no_peak")


# ---- calibración -------------------------------------------------------------


async def test_un_sensor_sin_procedencia_deja_el_sitio_no_calibrado(
    client, app, make_incident
) -> None:
    """Sin calibración el PGA es RELATIVO: afirmar gravedades sería inventar física."""
    _app_with_forensics(app)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED)

    body = (await _get(client, iid)).json()
    assert body["calibrated"] is False
    assert any(sn["calibration_source"] is None for sn in body["sensors"])


# ---- catálogo ----------------------------------------------------------------


async def test_casa_con_el_catalogo_dentro_de_la_ventana(
    client, app, make_incident, make_event
) -> None:
    _app_with_forensics(app)
    eid = await make_event(detected_at=_OPENED)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED, event_id=eid)
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO reference_earthquakes "
                "(catalog_key, origin_time, magnitude, place, epicenter, depth_km, "
                " source, source_ref) "
                "VALUES ('SSN-TEST-1', :ts, 7.1, 'Costa de Guerrero', "
                "ST_SetSRID(ST_MakePoint(-99.5, 16.8),4326)::geography, 20, 'SSN', 'test')"
            ),
            {"ts": _OPENED + timedelta(seconds=90)},
        )

    body = (await _get(client, iid)).json()
    assert body["catalog"]["catalog_key"] == "SSN-TEST-1"
    assert body["catalog_delta"]["dt_s"] == 90.0


async def test_un_sismo_lejano_en_el_tiempo_no_casa(client, app, make_incident, make_event) -> None:
    """±120 s: holgado para el desfase real, estrecho para no casar dos sismos."""
    _app_with_forensics(app)
    eid = await make_event(detected_at=_OPENED)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED, event_id=eid)
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO reference_earthquakes "
                "(catalog_key, origin_time, magnitude, place, epicenter, depth_km, "
                " source, source_ref) "
                "VALUES ('SSN-TEST-FAR', :ts, 6.0, 'Otro sismo', "
                "ST_SetSRID(ST_MakePoint(-99.5, 16.8),4326)::geography, 20, 'SSN', 'test')"
            ),
            {"ts": _OPENED + timedelta(seconds=600)},
        )

    body = (await _get(client, iid)).json()
    assert body["catalog"] is None
    assert body["catalog_delta"] is None


# ---- aislamiento (regla de oro 5) --------------------------------------------


async def test_otro_tenant_no_ve_el_incidente_ni_sus_features(client, app, make_incident) -> None:
    _app_with_forensics(app)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED)
    await _features(au.DB_SITE_PRIV, [(10, "ENZ", 0.081, 3.2)])

    resp = await _get(client, iid, _token(tenant=au.DB_TENANT_PRIV2))
    # 404 y no 403: un 403 confirmaría que el incidente existe.
    assert resp.status_code == 404


async def test_las_features_de_otro_sitio_no_se_cuelan(client, app, make_incident) -> None:
    """La vista segura hace JOIN a `sites` con RLS: el pico ajeno no debe aparecer."""
    _app_with_forensics(app)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED)
    await _features(au.DB_SITE_PRIV, [(10, "ENZ", 0.05, 1.0)])
    await _features(au.DB_SITE_PRIV2, [(10, "ENZ", 9.99, 99.0)])

    body = (await _get(client, iid)).json()
    assert body["peak_pga_g"] == pytest.approx(0.05)


async def test_un_incidente_inexistente_es_404(client, app) -> None:
    _app_with_forensics(app)
    resp = await _get(client, "00000000-0000-4000-8000-0000000000ff")
    assert resp.status_code == 404
