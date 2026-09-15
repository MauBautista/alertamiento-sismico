"""[T-7.14] Armar la reproducción por la API, y leer su plan de arribos.

Lo que fija, por orden de lo que costaría equivocarse:

* **No se arma sobre un cliente sin sitios de demostración.** Es LA guarda: sin
  ella, armar una reproducción haría que los incidentes de un edificio con gente
  dentro salieran rotulados como demostración.
* **No se arma un sismo que no esté en el catálogo.** La cifra que se enseña sale
  de una fila citable con su procedencia (`T-7.12`), no de un parámetro.
* **Solo `takab_superadmin`.** No es simetría con el modo demostración: allí el
  administrador del cliente puede APAGAR porque quedarse sin avisos le perjudica
  a él; aquí no hay nada que apagar por seguridad.
* **La ventana se recorta al techo, no se rechaza.** Pedir doce horas es querer
  más tiempo, no un error.
* **`GET /incidents/{id}/reproduccion` contesta 404 si el incidente NO es una
  reproducción**, en vez de calcular un plan sobre un epicentro estimado y
  presentarlo como si fuera la medición.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.replay.service import VENTANA_MAXIMA_S
from takab_api.routers.demo_mode import router as demo_mode_router
from takab_api.routers.reproduccion import router as reproduccion_router

CATALOGO = f"T714R-{uuid.uuid4().hex[:8]}"
ORIGEN_REAL = datetime(2017, 9, 19, 18, 14, 38, tzinfo=UTC)


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.include_router(demo_mode_router)
    application.include_router(reproduccion_router)
    return application


def _token(role: str = "takab_superadmin", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _sql(sql: str, **p):
    engine = get_engine()
    async with engine.begin() as conn:
        r = await conn.execute(text(sql), p)
        return r.fetchall() if r.returns_rows else []


@pytest.fixture(autouse=True)
async def _catalogo():
    """Una fila propia del catálogo: no se depende de que alguien haya sembrado."""
    await _sql(
        "INSERT INTO reference_earthquakes (catalog_key, origin_time, magnitude, place,"
        " epicenter, depth_km, source, source_ref)"
        " VALUES (:k, :t, 7.1, '19-S 2017 (fixture)',"
        " ST_SetSRID(ST_MakePoint(-98.4887, 18.5499), 4326)::geography, 48, 'USGS', 'fixture')"
        " ON CONFLICT (catalog_key) DO NOTHING",
        k=CATALOGO,
        t=ORIGEN_REAL,
    )
    yield
    await _sql("DELETE FROM demo_replay")
    await _sql("SET session_replication_role = 'replica'")
    await _sql(
        "DELETE FROM seismic_events WHERE event_id IN"
        " (SELECT event_id FROM incidents WHERE trigger = 'sasmex' AND severity = 'critical'"
        "   AND event_id IS NOT NULL)"
    )
    await _sql("DELETE FROM incidents WHERE trigger = 'sasmex' AND severity = 'critical'")
    await _sql("SET session_replication_role = 'origin'")
    await _sql("DELETE FROM reference_earthquakes WHERE catalog_key = :k", k=CATALOGO)


async def _sitio_demo(code: str = "site-sim-901") -> str:
    """Un sitio DEMO **con gabinete** en el tenant de las pruebas.

    El gabinete no es decorado: el plan de arribos solo incluye sitios con
    gabinete no retirado, porque una estación que no publica nada no siente la
    onda ni puede enseñarla.
    """
    sid = str(uuid.uuid4())
    await _sql(
        "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES"
        " (:s, :t, :c, 'Demo T-7.14',"
        "  ST_SetSRID(ST_MakePoint(-98.2404, 19.3139), 4326)::geography)",
        s=sid,
        t=au.DB_TENANT_PRIV,
        c=code,
    )
    await _sql(
        "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, status)"
        " VALUES (:g, :t, :s, :ser, 'online')",
        g=str(uuid.uuid4()),
        t=au.DB_TENANT_PRIV,
        s=sid,
        ser=f"SER-{code}",
    )
    return sid


async def _borra_sitio(sid: str) -> None:
    await _sql("DELETE FROM gateways WHERE site_id = :s", s=sid)
    await _sql("DELETE FROM sites WHERE site_id = :s", s=sid)


async def test_sin_sitios_DEMO_no_se_arma(client, base_data):
    """La guarda de la ficha: rotular de demostración un edificio real."""
    r = await client.post(
        "/demo-mode/replay",
        json={"catalog_key": CATALOGO},
        headers=_token(),
    )
    assert r.status_code == 409, r.text
    assert "demostración" in r.json()["detail"]


async def test_con_un_sitio_DEMO_se_arma_y_se_lee(client, base_data):
    sid = await _sitio_demo()
    try:
        r = await client.post(
            "/demo-mode/replay",
            json={"catalog_key": CATALOGO, "duration_s": 1800, "note": "ensayo"},
            headers=_token(),
        )
        assert r.status_code == 201, r.text
        cuerpo = r.json()
        assert cuerpo["armed"] is True
        assert cuerpo["catalog_key"] == CATALOGO
        assert 0 < cuerpo["remaining_s"] <= 1800

        leido = await client.get("/demo-mode/replay", headers=_token("soc_operator"))
        assert leido.status_code == 200
        assert leido.json()["armed"] is True, "quien va a mirar la consola tiene derecho a saberlo"
    finally:
        await _borra_sitio(sid)


async def test_un_sismo_FUERA_del_catalogo_se_rechaza(client, base_data):
    sid = await _sitio_demo()
    try:
        r = await client.post(
            "/demo-mode/replay",
            json={"catalog_key": "SSN-1900-01-01-INVENTADO"},
            headers=_token(),
        )
        assert r.status_code == 404, r.text
        assert "procedencia" in r.json()["detail"]
    finally:
        await _borra_sitio(sid)


async def test_la_ventana_se_RECORTA_al_techo(client, base_data):
    """Pedir doce horas es querer más tiempo, no un error."""
    sid = await _sitio_demo()
    try:
        r = await client.post(
            "/demo-mode/replay",
            json={"catalog_key": CATALOGO, "duration_s": 12 * 3600},
            headers=_token(),
        )
        assert r.status_code == 201, r.text
        assert r.json()["remaining_s"] <= VENTANA_MAXIMA_S
    finally:
        await _borra_sitio(sid)


async def test_solo_el_SUPERADMIN_arma(client, base_data):
    sid = await _sitio_demo()
    try:
        for rol in ("tenant_admin", "soc_operator"):
            r = await client.post(
                "/demo-mode/replay",
                json={"catalog_key": CATALOGO},
                headers=_token(rol),
            )
            assert r.status_code == 403, f"{rol} pudo armar: {r.text}"
    finally:
        await _borra_sitio(sid)


async def test_desarmar_es_IDEMPOTENTE(client, base_data):
    sid = await _sitio_demo()
    try:
        await client.post("/demo-mode/replay", json={"catalog_key": CATALOGO}, headers=_token())
        primera = await client.delete("/demo-mode/replay", headers=_token())
        segunda = await client.delete("/demo-mode/replay", headers=_token())
        assert primera.status_code == segunda.status_code == 200
        assert segunda.json()["armed"] is False
    finally:
        await _borra_sitio(sid)


async def test_el_plan_de_arribos_SALE_de_un_incidente_vestido(client, base_data):
    sid = await _sitio_demo()
    event_id = f"EVT-REP-{uuid.uuid4().hex[:12]}"
    inc = str(uuid.uuid4())
    try:
        await _sql(
            "INSERT INTO seismic_events (event_id, source, magnitude, epicenter, depth_km,"
            " detected_at, meta) VALUES (:e, 'external', 7.1,"
            " ST_SetSRID(ST_MakePoint(-98.4887, 18.5499), 4326)::geography, 48, now(),"
            " CAST(:m AS jsonb))",
            e=event_id,
            m=json.dumps(
                {
                    "reproduccion": {
                        "catalog_key": CATALOGO,
                        "t0_real": "2017-09-19T18:14:38+00:00",
                        "t0_demo": "2026-09-15T12:00:00+00:00",
                    },
                    "node_count": 2,
                    "v_p_km_s": 6.928203230275509,
                    "v_s_km_s": 4.0,
                }
            ),
        )
        await _sql(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, event_id,"
            " opened_at, severity, state, trigger)"
            " VALUES (:i, :u, :t, :s, :e, now(), 'critical', 'open', 'sasmex')",
            i=inc,
            u=str(uuid.uuid4()),
            t=au.DB_TENANT_PRIV,
            s=au.DB_SITE_PRIV,
            e=event_id,
        )

        r = await client.get(f"/incidents/{inc}/reproduccion", headers=_token("soc_operator"))
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert cuerpo["catalog_key"] == CATALOGO
        assert cuerpo["t0_real"].startswith("2017-09-19")
        assert cuerpo["t0_demo"].startswith("2026-09-15")
        assert cuerpo["v_s_km_s"] == pytest.approx(4.0)
        arribos = cuerpo["arrivals"]
        assert arribos, "el plan salió vacío: ninguna estación"
        assert "site-sim-901" in [a["site_code"] for a in arribos]
        assert [a["t_p_s"] for a in arribos] == sorted(a["t_p_s"] for a in arribos)
        for a in arribos:
            assert a["t_p_s"] < a["t_s_s"]
    finally:
        await _borra_sitio(sid)


async def test_un_incidente_que_NO_es_reproduccion_da_404(client, base_data):
    """Calcular un plan sobre un epicentro estimado y devolverlo sería presentar
    una simulación como si fuera la medición."""
    inc = str(uuid.uuid4())
    event_id = f"EVT-REAL-{uuid.uuid4().hex[:8]}"
    await _sql(
        "INSERT INTO seismic_events (event_id, source, detected_at) VALUES (:e,'sasmex',now())",
        e=event_id,
    )
    await _sql(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, event_id,"
        " opened_at, severity, state, trigger)"
        " VALUES (:i, :u, :t, :s, :e, now(), 'critical', 'open', 'sasmex')",
        i=inc,
        u=str(uuid.uuid4()),
        t=au.DB_TENANT_PRIV,
        s=au.DB_SITE_PRIV,
        e=event_id,
    )

    r = await client.get(f"/incidents/{inc}/reproduccion", headers=_token("soc_operator"))

    assert r.status_code == 404
    assert "no es una reproducción" in r.json()["detail"]
