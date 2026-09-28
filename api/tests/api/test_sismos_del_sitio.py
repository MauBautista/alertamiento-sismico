"""[T-9.61 · D-46] `GET /sites/{id}/sismos` y la paginación de `/catalog/earthquakes`.

Lo que se fija:

* la MMI que la app pinta es la ESTIMADA con la ley (`geo.pga_law_g`, distancia
  hipocentral) y la relación de Wald (`shakemap/gmice`), no otra aritmética;
* un sitio de otro tenant es 404, sin filtrar su existencia;
* `dias` fuera de [1, 365] es 422;
* la atribución viaja siempre, y un catálogo que nunca se sincronizó lo DICE
  (`actualizado` None, `sync_estado` `nunca`): un catálogo congelado no puede
  parecer vivo (regla de oro 7).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api import geo
from takab_api.db.engine import get_engine
from takab_api.shakemap import gmice

pytestmark = pytest.mark.usefixtures("base_data")

#: El sitio compartido de la suite está en el centro de la CDMX.
SITIO_LAT, SITIO_LON = 19.43, -99.13


def _hdr(role: str = "brigadista", *, tenant: str = au.DB_TENANT_PRIV, **over):
    return au.bearer(au.make_token(role, tenant=tenant, user_id=str(uuid.uuid4()), **over))


async def _sismo(
    clave: str,
    *,
    hace: timedelta,
    mag: float,
    lat: float,
    lon: float,
    depth: float | None = 20.0,
    source: str = "USGS",
    origen: str = "catalog_sync",
    review: str | None = "confirmado",
    en: datetime | None = None,
) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO reference_earthquakes (catalog_key, origin_time, magnitude, place,"
                " epicenter, depth_km, source, source_ref, provider_event_id, origen,"
                " usgs_url, review_status) VALUES (:k, :t, :m, :p,"
                " ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :d, :s, 'cita', :k,"
                " :o, :u, :r)"
            ),
            {
                "k": clave,
                "t": en or datetime.now(tz=UTC) - hace,
                "m": mag,
                "p": f"lugar {clave}",
                "lon": lon,
                "lat": lat,
                "d": depth,
                "s": source,
                "o": origen,
                "u": f"https://earthquake.usgs.gov/earthquakes/eventpage/{clave}",
                "r": review,
            },
        )


async def _estado(estado: str, ultimo_ok: datetime | None) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO catalog_sync_state (fuente, estado, ultimo_ok)"
                " VALUES ('USGS', :e, :ok)"
            ),
            {"e": estado, "ok": ultimo_ok},
        )


async def test_la_mmi_estimada_es_la_de_la_ley_y_gmice(client) -> None:
    await _sismo("usOAX", hace=timedelta(days=3), mag=6.1, lat=16.2, lon=-97.9, depth=35.0)
    r = await client.get(f"/sites/{au.DB_SITE_PRIV}/sismos", headers=_hdr())
    assert r.status_code == 200, r.text
    (item,) = r.json()["items"]
    dist = geo.haversine_km(SITIO_LAT, SITIO_LON, 16.2, -97.9)
    pga = geo.pga_law_g(6.1, geo.hypo_km(dist, 35.0))
    mmi = gmice.mmi_de_pga(pga)
    est = item["en_tu_inmueble"]
    assert est["dist_km"] == pytest.approx(dist, abs=0.06)
    assert est["pga_estimada_g"] == pytest.approx(pga, rel=1e-3)
    assert est["mmi_estimada"] == pytest.approx(mmi, abs=0.01)
    assert est["mmi_romano"] == gmice.romano(mmi)
    assert gmice.CITA in est["metodo"]
    assert item["magnitude"] == 6.1
    assert item["usgs_url"].endswith("/usOAX")
    assert item["review_status"] == "confirmado"
    assert (item["lat"], item["lon"], item["depth_km"]) == (16.2, -97.9, 35.0)


async def test_filtra_por_dias_y_magnitud_y_ordena_reciente_primero(client) -> None:
    await _sismo("usVIEJO", hace=timedelta(days=100), mag=5.0, lat=17.0, lon=-99.0)
    await _sismo("usCHICO", hace=timedelta(days=2), mag=3.5, lat=17.0, lon=-99.0)
    await _sismo("usA", hace=timedelta(days=5), mag=4.5, lat=17.0, lon=-99.0)
    await _sismo("usB", hace=timedelta(days=1), mag=4.2, lat=17.0, lon=-99.0)
    # Una fila del SSN no lleva la atribución de USGS: no entra en esta lista.
    await _sismo("SSN-X", hace=timedelta(days=1), mag=5.0, lat=17.0, lon=-99.0, source="SSN")
    r = await client.get(f"/sites/{au.DB_SITE_PRIV}/sismos?dias=90&min_mag=4.0", headers=_hdr())
    assert [i["place"] for i in r.json()["items"]] == ["lugar usB", "lugar usA"]


async def test_acceso_cruzado_de_tenant_es_404(client) -> None:
    r = await client.get(
        f"/sites/{au.DB_SITE_PRIV}/sismos", headers=_hdr("tenant_admin", tenant=au.DB_TENANT_PRIV2)
    )
    assert r.status_code == 404


async def test_un_rol_sin_acceso_movil_al_sitio_es_403(client) -> None:
    r = await client.get(f"/sites/{au.DB_SITE_PRIV}/sismos", headers=_hdr("gov_operator"))
    assert r.status_code == 403


@pytest.mark.parametrize("dias", [0, 366])
async def test_dias_fuera_de_rango_es_422(client, dias: int) -> None:
    r = await client.get(f"/sites/{au.DB_SITE_PRIV}/sismos?dias={dias}", headers=_hdr())
    assert r.status_code == 422


async def test_sin_sincronizar_lo_dice_y_la_atribucion_va_siempre(client) -> None:
    r = await client.get(f"/sites/{au.DB_SITE_PRIV}/sismos", headers=_hdr())
    body = r.json()
    assert body["items"] == []
    assert body["atribucion"] == "Fuente: USGS (dominio público)"
    assert body["actualizado"] is None
    assert body["sync_estado"] == "nunca"


async def test_actualizado_es_el_ultimo_ok_aunque_la_ultima_haya_fallado(client) -> None:
    ok = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
    await _estado("fallido", ok)
    body = (await client.get(f"/sites/{au.DB_SITE_PRIV}/sismos", headers=_hdr())).json()
    assert body["sync_estado"] == "fallido"
    assert datetime.fromisoformat(body["actualizado"]) == ok


# --- /catalog/earthquakes paginado -------------------------------------------------


async def test_el_catalogo_pagina_con_cursor(client) -> None:
    for i in range(5):
        await _sismo(f"usP{i}", hace=timedelta(days=i + 1), mag=4.5, lat=17.0, lon=-99.0)
    hdr = _hdr("tenant_admin")
    r1 = (await client.get("/catalog/earthquakes?limit=2", headers=hdr)).json()
    assert [i["catalog_key"] for i in r1["items"]] == ["usP0", "usP1"]
    assert r1["items"][0]["origen"] == "catalog_sync"
    assert r1["items"][0]["usgs_url"].endswith("/usP0")
    assert r1["siguiente"] is not None

    r2 = (
        await client.get(
            "/catalog/earthquakes", params={"limit": 2, "antes_de": r1["siguiente"]}, headers=hdr
        )
    ).json()
    assert [i["catalog_key"] for i in r2["items"]] == ["usP2", "usP3"]
    r3 = (
        await client.get(
            "/catalog/earthquakes", params={"limit": 2, "antes_de": r2["siguiente"]}, headers=hdr
        )
    ).json()
    assert [i["catalog_key"] for i in r3["items"]] == ["usP4"]
    assert r3["siguiente"] is None


async def test_dos_sismos_con_la_MISMA_hora_no_se_pierden_en_el_borde_de_pagina(client) -> None:
    """El cursor es (hora, id): con la hora sola, el empate en el borde tiraba uno.

    Pasa en la realidad: el SSN y el USGS citan el mismo sismo al mismo segundo.
    """
    hora = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    for clave in ("usT1", "usT2", "usT3"):
        await _sismo(clave, hace=timedelta(0), mag=4.5, lat=17.0, lon=-99.0, en=hora)
    hdr = _hdr("tenant_admin")
    vistos: list[str] = []
    cursor = None
    for _ in range(4):
        params = {"limit": 2, **({"antes_de": cursor} if cursor else {})}
        r = (await client.get("/catalog/earthquakes", params=params, headers=hdr)).json()
        vistos += [i["catalog_key"] for i in r["items"]]
        cursor = r["siguiente"]
        if cursor is None:
            break
    assert sorted(vistos) == ["usT1", "usT2", "usT3"]
    assert len(vistos) == len(set(vistos))


@pytest.mark.parametrize("limit", [0, 501])
async def test_el_limite_del_catalogo_esta_acotado(client, limit: int) -> None:
    r = await client.get(f"/catalog/earthquakes?limit={limit}", headers=_hdr("tenant_admin"))
    assert r.status_code == 422
