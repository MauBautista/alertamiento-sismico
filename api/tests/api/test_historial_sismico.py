"""[T-9.66 · D-46] `GET /sites/{id}/historial-sismico`: lo que vivió el inmueble.

Una sola lista, por fecha descendente, con dos tipos:

* ``incidente`` — lo que MIDIÓ el gabinete de ese sitio, con su PGA medida;
* ``sismo`` — lo que el catálogo publicó y que en el sitio se habría sentido: sólo
  si la MMI ESTIMADA ahí llega a III, y nunca dos veces: el sismo que ya es un
  incidente del sitio aparece una sola vez, como incidente.
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

SITIO_LAT, SITIO_LON = 19.43, -99.13
AHORA = datetime.now(tz=UTC)


def _hdr(role: str = "tenant_admin", *, tenant: str = au.DB_TENANT_PRIV, **over):
    return au.bearer(au.make_token(role, tenant=tenant, user_id=str(uuid.uuid4()), **over))


async def _sismo(clave: str, *, hace: timedelta, mag: float, lat: float, lon: float) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO reference_earthquakes (catalog_key, origin_time, magnitude, place,"
                " epicenter, depth_km, source, source_ref, provider_event_id, origen, usgs_url)"
                " VALUES (:k, :t, :m, :p, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,"
                " 20, 'USGS', 'cita', :k, 'catalog_sync', :u)"
            ),
            {
                "k": clave,
                "t": AHORA - hace,
                "m": mag,
                "p": f"lugar {clave}",
                "lon": lon,
                "lat": lat,
                "u": f"https://earthquake.usgs.gov/earthquakes/eventpage/{clave}",
            },
        )


async def _incidente(
    *,
    hace: timedelta,
    site: str = au.DB_SITE_PRIV,
    tenant: str = au.DB_TENANT_PRIV,
    pga: float | None = 0.012,
    clasificacion: str | None = None,
    catalog_key: str | None = None,
) -> str:
    inc = str(uuid.uuid4())
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at,"
                " severity, state, trigger, max_pga_g) VALUES (:i, gen_random_uuid(), :t, :s,"
                " :o, 'warning', 'in_review', 'sasmex', :pga)"
            ),
            {"i": inc, "t": tenant, "s": site, "o": AHORA - hace, "pga": pga},
        )
        if clasificacion:
            await conn.execute(
                text(
                    "INSERT INTO incident_classifications (tenant_id, incident_id,"
                    " classification, classified_by) VALUES (:t, :i, :c, gen_random_uuid())"
                ),
                {"t": tenant, "i": inc, "c": clasificacion},
            )
        if catalog_key:
            # Lo que deja la consulta por incidente de T-7.25 cuando el sismo publicado
            # ES el nuestro.
            await conn.execute(
                text(
                    "INSERT INTO catalog_consultations (incident_id, provider, tenant_id,"
                    " asked_at, last_attempt_at, answered_at, outcome, catalog_key)"
                    " VALUES (:i, 'USGS', :t, :o, :o, :o, 'correlacionado', :k)"
                ),
                {"i": inc, "t": tenant, "o": AHORA - hace, "k": catalog_key},
            )
    return inc


def _mmi_en_el_sitio(mag: float, lat: float, lon: float) -> float:
    dist = geo.haversine_km(SITIO_LAT, SITIO_LON, lat, lon)
    return gmice.mmi_de_pga(geo.pga_law_g(mag, geo.hypo_km(dist, 20.0)))


async def test_mezcla_ordenada_de_incidentes_y_sismos(client) -> None:
    await _sismo("usCERCA", hace=timedelta(days=10), mag=5.8, lat=18.6, lon=-98.5)
    inc = await _incidente(hace=timedelta(days=3), pga=0.021, clasificacion="real")
    await _sismo("usOTRO", hace=timedelta(days=1), mag=6.0, lat=18.9, lon=-99.2)

    r = await client.get(f"/sites/{au.DB_SITE_PRIV}/historial-sismico", headers=_hdr())
    assert r.status_code == 200, r.text
    eventos = r.json()["eventos"]
    assert [e["tipo"] for e in eventos] == ["sismo", "incidente", "sismo"]
    assert eventos[0]["place"] == "lugar usOTRO"
    medio = eventos[1]
    assert medio["incident_id"] == inc
    assert medio["pga_medida_g"] == pytest.approx(0.021)
    assert medio["clasificacion"] == "real"
    assert (medio["severity"], medio["trigger"], medio["estado"]) == (
        "warning",
        "sasmex",
        "in_review",
    )
    ultimo = eventos[2]
    assert ultimo["mmi_estimada"] == pytest.approx(_mmi_en_el_sitio(5.8, 18.6, -98.5), abs=0.01)
    assert ultimo["mmi_romano"] == gmice.romano(ultimo["mmi_estimada"])
    assert ultimo["usgs_url"].endswith("/usCERCA")
    assert ultimo["dist_km"] > 0


async def test_el_umbral_de_mmi_iii(client) -> None:
    # Un M4.0 a ~600 km no se siente en la CDMX; un M5.8 a ~110 km sí.
    lejos = _mmi_en_el_sitio(4.0, 15.0, -94.5)
    cerca = _mmi_en_el_sitio(5.8, 18.6, -98.5)
    assert lejos < 3.0 <= cerca, "el escenario tiene que caer a los dos lados del umbral"
    await _sismo("usLEJOS", hace=timedelta(days=5), mag=4.0, lat=15.0, lon=-94.5)
    await _sismo("usCERCA", hace=timedelta(days=6), mag=5.8, lat=18.6, lon=-98.5)
    eventos = (
        await client.get(f"/sites/{au.DB_SITE_PRIV}/historial-sismico", headers=_hdr())
    ).json()["eventos"]
    assert [e["place"] for e in eventos] == ["lugar usCERCA"]


async def test_no_duplica_el_sismo_que_ya_es_incidente(client) -> None:
    await _sismo("usMIO", hace=timedelta(days=4), mag=6.2, lat=18.6, lon=-98.5)
    inc = await _incidente(hace=timedelta(days=4) - timedelta(seconds=40), catalog_key="usMIO")
    eventos = (
        await client.get(f"/sites/{au.DB_SITE_PRIV}/historial-sismico", headers=_hdr())
    ).json()["eventos"]
    assert [(e["tipo"], e.get("incident_id")) for e in eventos] == [("incidente", inc)]


async def test_el_incidente_de_otro_sitio_no_esconde_el_sismo(client) -> None:
    """La exclusión es por incidente DEL SITIO: que otro inmueble lo midiera no
    quiere decir que éste lo tenga ya en su lista."""
    await _sismo("usAJENO", hace=timedelta(days=4), mag=6.2, lat=18.6, lon=-98.5)
    await _incidente(
        hace=timedelta(days=4),
        site=au.DB_SITE_PRIV2,
        tenant=au.DB_TENANT_PRIV2,
        catalog_key="usAJENO",
    )
    eventos = (
        await client.get(f"/sites/{au.DB_SITE_PRIV}/historial-sismico", headers=_hdr())
    ).json()["eventos"]
    assert [e["tipo"] for e in eventos] == ["sismo"]


async def test_cruce_de_tenant_es_404(client) -> None:
    await _incidente(hace=timedelta(days=1))
    r = await client.get(
        f"/sites/{au.DB_SITE_PRIV}/historial-sismico",
        headers=_hdr("tenant_admin", tenant=au.DB_TENANT_PRIV2),
    )
    assert r.status_code == 404


async def test_lo_leen_la_web_y_el_movil(client) -> None:
    web = await client.get(f"/sites/{au.DB_SITE_PRIV}/historial-sismico", headers=_hdr("inspector"))
    movil = await client.get(
        f"/sites/{au.DB_SITE_PRIV}/historial-sismico",
        headers=_hdr("brigadista", surface="mobile"),
    )
    assert web.status_code == movil.status_code == 200


async def test_la_ventana_es_de_dias(client) -> None:
    await _incidente(hace=timedelta(days=400))
    body = (
        await client.get(f"/sites/{au.DB_SITE_PRIV}/historial-sismico?dias=365", headers=_hdr())
    ).json()
    assert body["eventos"] == []
    r = await client.get(f"/sites/{au.DB_SITE_PRIV}/historial-sismico?dias=0", headers=_hdr())
    assert r.status_code == 422


def test_el_umbral_es_el_GRADO_que_se_ensena_y_no_el_numero_crudo() -> None:
    """2.87 se enseña «III»: si se enseña así, entra en el historial."""
    from takab_api.routers import sismos_del_sitio as R

    assert gmice.romano(2.87) == "III"
    assert R._grado(2.87) >= R._grado_de(R.GRADO_MINIMO_HISTORIAL)  # noqa: SLF001
    assert R._grado(2.49) < R._grado_de(R.GRADO_MINIMO_HISTORIAL)  # noqa: SLF001
