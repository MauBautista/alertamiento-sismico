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


# ---- catálogo · el criterio de IDENTIDAD (T-5.11) -----------------------------
#
# El sitio de estos tests está en la Ciudad de México (-99.13, 19.43): el conftest
# lo siembra ahí, y aquí importa porque el criterio que decide es la distancia
# del epicentro AL SITIO.


async def _catalogo(clave: str, *, origin_time, magnitude, lat, lon, depth=20) -> None:
    """Siembra una fila del catálogo de referencia."""
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO reference_earthquakes "
                "(catalog_key, origin_time, magnitude, place, epicenter, depth_km, "
                " source, source_ref) "
                "VALUES (:k, :ts, :m, 'sismo de prueba', "
                "ST_SetSRID(ST_MakePoint(:lon, :lat),4326)::geography, :d, 'SSN', 'test')"
            ),
            {"k": clave, "ts": origin_time, "m": magnitude, "lat": lat, "lon": lon, "d": depth},
        )


async def test_casa_con_el_catalogo_dentro_de_la_ventana(
    client, app, make_incident, make_event
) -> None:
    """Costa de Guerrero: 295 km del sitio, sacudida a ~82 s del origen."""
    _app_with_forensics(app)
    eid = await make_event(detected_at=_OPENED)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED, event_id=eid)
    await _catalogo(
        "SSN-TEST-1",
        origin_time=_OPENED - timedelta(seconds=82),
        magnitude=7.1,
        lat=16.8,
        lon=-99.5,
    )

    body = (await _get(client, iid)).json()
    assert body["catalog"]["catalog_key"] == "SSN-TEST-1"
    assert body["catalog_delta"]["dt_s"] == 82.0
    # [T-5.11] La distancia AL SITIO es la que decidió, y viaja con el acierto.
    assert body["catalog"]["km_al_sitio"] == pytest.approx(295, abs=5)
    assert body["catalog_correlation"]["estado"] == "sin_dato_externo"
    assert body["catalog_correlation"]["descartes"] == []


async def test_UN_SISMO_LEJANO_EN_LA_VENTANA_TEMPORAL_ya_no_casa(
    client, app, make_incident, make_event
) -> None:
    """**El caso de la ficha T-5.11**, extremo a extremo y contra la base.

    Un M8.3 en la costa de Chile, ocurrido 60 s antes de nuestra detección. HOY
    casaba —el criterio era estar dentro de ±120 s y nada más— y se imprimía con
    su magnitud y su lugar en un dictamen FIRMADO bajo el rótulo «contraste con
    catálogo». Con la ficha no casa, y además el sistema puede DECIR por qué.
    """
    _app_with_forensics(app)
    eid = await make_event(detected_at=_OPENED)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED, event_id=eid)
    await _catalogo(
        "SSN-CHILE",
        origin_time=_OPENED - timedelta(seconds=60),
        magnitude=8.3,
        lat=-31.57,
        lon=-71.67,
    )

    body = (await _get(client, iid)).json()
    assert body["catalog"] is None
    assert body["catalog_delta"] is None

    # Y esto es lo que no se sabía decir: «hay un evento en el catálogo pero no
    # es el nuestro». Sin ello el descarte es indistinguible de un catálogo vacío.
    corr = body["catalog_correlation"]
    assert corr["estado"] == "sin_correlacion"
    assert [d["catalog_key"] for d in corr["descartes"]] == ["SSN-CHILE"]
    assert corr["descartes"][0]["motivo"] == "fuera_de_radio"
    assert corr["descartes"][0]["km_al_sitio"] > corr["criterio"]["radio_km"]


async def test_gana_el_que_casa_y_no_el_mas_cercano_en_el_tiempo(
    client, app, make_incident, make_event
) -> None:
    """La consulta ya no elige: trae candidatos y decide el criterio.

    El intruso está MÁS cerca en el tiempo que el legítimo. Con el `LIMIT 1` por
    Δt de antes era el único que llegaba a evaluarse.
    """
    _app_with_forensics(app)
    eid = await make_event(detected_at=_OPENED)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED, event_id=eid)
    await _catalogo(
        "SSN-JAPON", origin_time=_OPENED - timedelta(seconds=5), magnitude=9.0, lat=38.3, lon=142.37
    )
    await _catalogo(
        "SSN-BUENO", origin_time=_OPENED - timedelta(seconds=82), magnitude=7.1, lat=16.8, lon=-99.5
    )

    body = (await _get(client, iid)).json()
    assert body["catalog"]["catalog_key"] == "SSN-BUENO"
    assert [d["catalog_key"] for d in body["catalog_correlation"]["descartes"]] == ["SSN-JAPON"]


async def test_un_sismo_PEQUENO_y_lejano_no_pudo_sacudir_este_edificio(
    client, app, make_incident, make_event
) -> None:
    """Dentro del radio y de la ventana, y aun así imposible: M4.0 a 295 km."""
    _app_with_forensics(app)
    eid = await make_event(detected_at=_OPENED)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED, event_id=eid)
    await _catalogo(
        "SSN-CHICO", origin_time=_OPENED - timedelta(seconds=82), magnitude=4.0, lat=16.8, lon=-99.5
    )

    body = (await _get(client, iid)).json()
    assert body["catalog"] is None
    assert body["catalog_correlation"]["descartes"][0]["motivo"] == "magnitud_incoherente"


async def test_un_origen_posterior_a_la_deteccion_no_casa(
    client, app, make_incident, make_event
) -> None:
    """Un edificio no detecta un sismo antes de que ocurra.

    Este caso —origen 90 s DESPUÉS de la detección— es el que sembraba el test
    de esta suite antes de `T-5.11`, y casaba: el criterio comparaba el valor
    ABSOLUTO del desfase.
    """
    _app_with_forensics(app)
    eid = await make_event(detected_at=_OPENED)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED, event_id=eid)
    await _catalogo(
        "SSN-FUTURO",
        origin_time=_OPENED + timedelta(seconds=90),
        magnitude=7.1,
        lat=16.8,
        lon=-99.5,
    )

    body = (await _get(client, iid)).json()
    assert body["catalog"] is None
    assert body["catalog_correlation"]["descartes"][0]["motivo"] == "anterior_a_su_origen"


async def test_sin_epicentro_propio_el_acierto_NO_se_presenta_como_contraste(
    client, app, make_incident, make_event
) -> None:
    """La ruta del receptor —la normal— no tiene epicentro propio que comparar.

    La identidad sí se estableció (ventana + radio + coherencia), pero llamar
    «contraste» a eso prometería una verificación que no ocurrió.
    """
    _app_with_forensics(app)
    eid = await make_event(detected_at=_OPENED)  # sin epicentro: es lo normal
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED, event_id=eid)
    await _catalogo(
        "SSN-TEST-1",
        origin_time=_OPENED - timedelta(seconds=82),
        magnitude=7.1,
        lat=16.8,
        lon=-99.5,
    )

    body = (await _get(client, iid)).json()
    assert body["catalog_correlation"]["verificacion"] == "no_verificable"
    assert body["catalog_delta"]["km"] is None


async def test_un_sismo_lejano_en_el_tiempo_no_casa(client, app, make_incident, make_event) -> None:
    """A 295 km la sacudida llega a ~82 s: a los 600 s ya no puede ser el nuestro."""
    _app_with_forensics(app)
    eid = await make_event(detected_at=_OPENED)
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED, event_id=eid)
    await _catalogo(
        "SSN-TEST-FAR",
        origin_time=_OPENED - timedelta(seconds=600),
        magnitude=6.0,
        lat=16.8,
        lon=-99.5,
    )

    body = (await _get(client, iid)).json()
    assert body["catalog"] is None
    assert body["catalog_delta"] is None
    # Más allá de la cota de la consulta ni siquiera llega a evaluarse, y eso
    # también es correcto: nada que a 600 s pueda ser un sismo de 295 km.
    assert body["catalog_correlation"]["estado"] == "sin_correlacion"


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
