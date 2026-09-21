"""T-7.24 · `GET /incidents/{id}/shakemap`: lo que la consola y el PDF LEEN.

Lectura pura: el endpoint no recalcula nada, y eso es medio diseño (`§A.4`). Si
recalculara, dos operadores verían mapas distintos del mismo sismo según cuándo
apretaran F5.

Lo que fija, por orden de lo que costaría equivocarse:

1. **«Todavía no calculado» es 200 con `estado: "pendiente"`, no un 404 ni un
   500.** Es una condición normal del sistema —el mapa no es en vivo— y la regla
   de oro 7 exige que se declare en vez de dejar la pantalla en blanco. El 404 se
   reserva para el incidente que no existe (o que la RLS no deja ver: 404 y no
   403, porque un 403 confirmaría que existe).
2. **Cada valor viaja con su procedencia y las dos capas se pintan distinto.**
   `measured` en los puntos, `modeled` en los anillos: un consumidor no tiene que
   adivinar de qué capa vino un número (`D-08` · `§A.3`).
3. ⚠️ **La capa modelada sale como POLÍGONO GEOGRÁFICO, en grados.** Ésta es la
   guarda que sustituye a `DIF-shakemap.a`, y nace de un defecto medido: había
   dos capas de MapLibre con `circle-radius` de 55 y 100 **píxeles de pantalla**
   rotuladas «INTENSIDAD MMI», así que el mismo anillo afirmaba ~22 km a zoom 8.5
   y ~1 km a zoom 13 — cambiaba de significado físico con cada rueda del ratón.
   Aquí se mide el radio del polígono devuelto con `haversine_km` y tiene que
   coincidir con el `radio_km` que el propio anillo declara.
4. **Sin magnitud/epicentro, `modelado` es `null`** y el mapa existe degradado:
   la consola no dibuja un modelo que no se calculó, y lo declara.
5. **El orden de GeoJSON es `[lon, lat]`.** Invertirlo pone los inmuebles en el
   otro hemisferio, y es un fallo que se lee como «el mapa está vacío» — la misma
   trampa que `tests/catalogo/fixtures.py` deja escrita para el epicentro.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.felt import DEFAULT_THRESHOLDS
from takab_api.geo import haversine_km
from takab_api.settings import Settings
from takab_api.shakemap import calculo as C
from takab_api.shakemap.lectura import circulo, leer

T0 = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)
EPI_LAT, EPI_LON, PROF_KM, MAG = 18.5499, -98.4887, 48.0, 7.1
SITIO_LAT, SITIO_LON = 19.43, -99.13  # el sitio de `seed_shared` (Ciudad de México)

#: Los anillos del snapshot se DESPEJAN de la ley con la banda del inmueble, no
#: se escriben a mano. Escribirlos era lo que dejaba a la guarda del polígono
#: midiendo siempre radios pequeños y cómodos (82.4 y 132.2 km), y por eso no
#: veía que la pasada real estaba escribiendo anillos de 5 623 km.
NIVELES = tuple((nombre, getattr(DEFAULT_THRESHOLDS, nombre)) for nombre in C.UMBRALES)
#: El tope del radio, del mismo sitio del que lo saca la pasada.
TOPE_KM = Settings().correlation_max_km


async def _sql(sql: str, **p):
    engine = get_engine()
    async with engine.begin() as conn:
        r = await conn.execute(text(sql), p)
        return r.fetchall() if r.returns_rows else []


async def _incidente(tenant: str = au.DB_TENANT_PRIV, site: str = au.DB_SITE_PRIV) -> str:
    inc = str(uuid.uuid4())
    await _sql(
        "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at,"
        " severity, state, trigger) VALUES (:i, :u, :t, :s, :o, 'critical', 'in_review',"
        " 'sasmex')",
        i=inc,
        u=str(uuid.uuid4()),
        t=tenant,
        s=site,
        o=T0,
    )
    return inc


async def _snapshot(
    inc: str,
    *,
    tenant: str = au.DB_TENANT_PRIV,
    estado: str = C.ESTADO_COMPLETO,
    con_modelo: bool = True,
    fuera: tuple[str, ...] | list[str] = (),
) -> None:
    """Escribe un snapshot A MANO: el endpoint LEE, y aquí se prueba que lee.

    `fuera` son los umbrales que se escriben DECLARADOS en vez de dibujados, que
    es como la pasada guarda un nivel cuyo radio se sale del alcance del modelo.
    """
    epicentro = (
        {
            "lat": EPI_LAT,
            "lon": EPI_LON,
            "depth_km": PROF_KM,
            "magnitud": MAG,
            "fuente": "external",
            "procedencia": "confirmado",
            "catalog_key": "USGS-2017-09-19-PUE",
        }
        if con_modelo
        else None
    )
    puntos = [
        {
            "site_id": au.DB_SITE_PRIV,
            "site_code": "SITE-PRIV",
            "site_name": "Inmueble de prueba",
            "lat": SITIO_LAT,
            "lon": SITIO_LON,
            "procedencia": C.PROC_MEDIDO,
            "pga_g": 0.086,
            "pgv_cms": 6.4,
            "dist_km": 122.0,
            "hypo_km": 131.1,
            "pga_g_modelada": 0.0429 if con_modelo else None,
            "residuo_log10": 0.301 if con_modelo else None,
            "medido_en": (T0 + timedelta(seconds=30)).isoformat(),
            "voto_contado": True,
        }
    ]
    anillos = (
        [
            {
                "umbral": nombre,
                "pga_g": pga,
                "radio_km": (None if nombre in fuera else C.radio_epicentral_km(MAG, pga, PROF_KM)),
                "motivo": C.FUERA_DEL_ALCANCE if nombre in fuera else None,
                "radio_max_km": TOPE_KM,
            }
            for nombre, pga in sorted(NIVELES, key=lambda n: n[1], reverse=True)
        ]
        if con_modelo
        else []
    )
    await _sql(
        "INSERT INTO incident_shakemap (incident_id, tenant_id, calculado_en, estado, ley,"
        " epicentro, cobertura_km, puntos, anillos) VALUES (:i, :t, :c, :e, :l,"
        " CAST(:epi AS jsonb), 5.0, CAST(:p AS jsonb), CAST(:a AS jsonb))",
        i=inc,
        t=tenant,
        c=T0 + timedelta(minutes=10),
        e=estado,
        l=C.LEY if con_modelo else None,
        epi=json.dumps(epicentro),
        p=json.dumps(puntos),
        a=json.dumps(anillos),
    )


def _token(role: str = "soc_operator", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*"))


async def _pide(client, inc: str, **over):
    return await client.get(f"/incidents/{inc}/shakemap", headers=_token(**over))


# ------------------------------------------------------- los estados del lector


async def test_sin_snapshot_es_200_PENDIENTE_y_no_un_404(client, base_data):
    """«El worker aún no ha pasado» es una condición normal, no un error.

    Un 404 aquí haría que la consola pintara «no existe» sobre un incidente que
    existe, y un 500 la pondría en rojo por algo que va a resolverse solo.
    """
    inc = await _incidente()
    r = await _pide(client, inc)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == C.ESTADO_PENDIENTE
    assert cuerpo["calculado_en"] is None
    assert cuerpo["ley"] is None
    assert cuerpo["epicentro"] is None
    assert cuerpo["observado"]["features"] == []
    assert cuerpo["modelado"] is None
    # El radio con el que se VA a calcular, no una afirmación sobre un mapa que
    # todavía no existe. Cero sería un número inventado.
    assert cuerpo["cobertura_km"] > 0


async def test_un_incidente_que_no_existe_es_404(client, base_data):
    r = await _pide(client, str(uuid.uuid4()))
    assert r.status_code == 404


async def test_el_incidente_de_otro_cliente_es_404_y_NO_403(client, base_data):
    """Un 403 confirmaría que ese incidente existe. Regla de oro 5."""
    inc = await _incidente(tenant=au.DB_TENANT_PRIV2, site=au.DB_SITE_PRIV2)
    await _snapshot(inc, tenant=au.DB_TENANT_PRIV2)
    r = await _pide(client, inc)
    assert r.status_code == 404, r.text


# --------------------------------------------------------- las tres capas


async def test_la_capa_observada_es_de_puntos_y_dice_que_esta_MEDIDA(client, base_data):
    inc = await _incidente()
    await _snapshot(inc)

    cuerpo = (await _pide(client, inc)).json()
    assert cuerpo["estado"] == C.ESTADO_COMPLETO
    assert cuerpo["ley"] == C.LEY
    assert cuerpo["calculado_en"] is not None

    fc = cuerpo["observado"]
    assert fc["type"] == "FeatureCollection"
    feature = fc["features"][0]
    assert feature["geometry"]["type"] == "Point"
    # ⚠️ El orden de GeoJSON es [lon, lat]. Invertirlo pone el inmueble en el
    # otro hemisferio y el mapa se lee como vacío.
    assert feature["geometry"]["coordinates"] == [SITIO_LON, SITIO_LAT]
    props = feature["properties"]
    assert props["procedencia"] == C.PROC_MEDIDO
    assert props["pga_g"] == pytest.approx(0.086)
    assert props["residuo_log10"] == pytest.approx(0.301)
    assert props["site_name"] and props["site_id"]
    assert props["medido_en"] is not None


async def test_la_capa_modelada_es_de_POLIGONOS_y_dice_que_es_un_MODELO(client, base_data):
    inc = await _incidente()
    await _snapshot(inc)

    modelado = (await _pide(client, inc)).json()["modelado"]
    assert modelado["type"] == "FeatureCollection"
    assert len(modelado["features"]) == len(NIVELES)
    for f in modelado["features"]:
        assert f["geometry"]["type"] == "Polygon"
        assert f["properties"]["procedencia"] == C.PROC_MODELADO
        assert f["properties"]["umbral"] in C.UMBRALES
        assert f["properties"]["pga_g"] > 0
        assert f["properties"]["radio_km"] > 0


async def test_el_poligono_del_anillo_MIDE_lo_que_el_anillo_AFIRMA(client, base_data):
    """⚠️ LA guarda que sustituye a `DIF-shakemap.a`.

    El anillo se materializa en grados alrededor del epicentro, y cada vértice
    tiene que estar a `radio_km` de él —medido con la misma `haversine_km` que usa
    todo el sistema—. Si el radio fuera una unidad de pantalla, esta comprobación
    no se podría ni escribir: no hay forma de medir en kilómetros algo que se
    define en píxeles.
    """
    inc = await _incidente()
    await _snapshot(inc)

    for f in (await _pide(client, inc)).json()["modelado"]["features"]:
        anillo = f["geometry"]["coordinates"][0]
        assert len(anillo) >= 33, "un círculo con pocos vértices se ve como un polígono"
        assert anillo[0] == anillo[-1], "GeoJSON exige que el anillo esté cerrado"
        radios = [haversine_km(EPI_LAT, EPI_LON, lat, lon) for lon, lat in anillo]
        declarado = f["properties"]["radio_km"]
        assert max(radios) == pytest.approx(declarado, rel=1e-3)
        assert min(radios) == pytest.approx(declarado, rel=1e-3)


@pytest.mark.parametrize("radio_km", [1.0, 132.2, TOPE_KM])
def test_el_poligono_MIDE_lo_que_afirma_TAMBIEN_en_el_radio_mas_grande(
    radio_km: float,
) -> None:
    """El invariante en el borde, que es donde se rompía.

    La guarda anterior sólo ejercía radios escritos a mano de 82.4 y 132.2 km, y
    con los radios que la pasada llegaba a escribir de verdad —5 623 km con el
    piso de coherencia de T-5.11, 19 952 km con el M8.2 de Chiapas— el polígono
    dejaba de medir lo que el anillo declaraba: a M8.3 declaraba 22 387.2 km y
    medía 17 643.0, porque por encima de media circunferencia (20 015 km) el
    círculo se enrolla alrededor del ANTÍPODA. Hoy el tope lo impide, y esta
    guarda mide justo ahí: en el radio más grande que se puede publicar.
    """
    anillo = circulo(EPI_LAT, EPI_LON, radio_km)
    radios = [haversine_km(EPI_LAT, EPI_LON, lat, lon) for lon, lat in anillo]
    assert max(radios) == pytest.approx(radio_km, rel=1e-3)
    assert min(radios) == pytest.approx(radio_km, rel=1e-3)


@pytest.mark.parametrize(
    ("lat", "lon", "radio_km"),
    [
        (EPI_LAT, EPI_LON, TOPE_KM),  # el caso real, en el radio máximo
        (-17.0, 179.0, 300.0),  # uno que CRUZA el antimeridiano
    ],
)
def test_la_longitud_del_poligono_esta_en_el_rango_de_GeoJSON(
    lat: float, lon: float, radio_km: float
) -> None:
    """RFC 7946 §3.1.1 exige `lon ∈ [−180, 180]`, y MapLibre lo necesita.

    La fórmula del punto de destino devuelve `lambda1 + atan2(…)`, que cae en
    `[lambda1−π, lambda1+π]`: sin normalizar, un anillo grande alrededor de un
    epicentro en lon −98.49 llegaba a **−278.49°** (medido el 2026-09-21), que no
    es una longitud. El segundo caso cruza el antimeridiano a propósito: ahí la
    normalización es lo único que mantiene válidos los vértices (partir el
    polígono en dos, §3.1.9, no hace falta porque con el tope no puede pasarle a
    esta red: desde los extremos de longitud de los inmuebles sembrados en
    `db/seeds/` —−103.29 y −93.90— un anillo de 1 200 km queda dentro de
    [−114.7, −82.5]).
    """
    for x, y in circulo(lat, lon, radio_km):
        assert -180.0 <= x <= 180.0, f"longitud fuera del rango de GeoJSON: {x}"
        assert -90.0 <= y <= 90.0


async def test_un_nivel_QUE_NO_SE_DIBUJA_llega_declarado_y_no_desaparece(client, base_data):
    """Un anillo ausente sin explicación se lee como «ese umbral no existía», y
    aquí los umbrales son con los que este sistema decide. El nivel suprimido
    viaja en `fuera_de_alcance` con su motivo y con el tope que lo suprimió."""
    inc = await _incidente()
    await _snapshot(inc, fuera=[C.UMBRAL_WATCH])

    cuerpo = (await _pide(client, inc)).json()
    assert [f["properties"]["umbral"] for f in cuerpo["modelado"]["features"]] == [C.UMBRAL_TRIP]
    assert cuerpo["fuera_de_alcance"] == [
        {
            "umbral": C.UMBRAL_WATCH,
            "pga_g": DEFAULT_THRESHOLDS.pga_watch_g,
            "motivo": C.FUERA_DEL_ALCANCE,
            "radio_max_km": TOPE_KM,
        }
    ]
    assert cuerpo["fuera_de_alcance"][0]["motivo"] in C.MOTIVOS_FUERA


async def test_el_voto_de_cuorum_y_el_PGV_llegan_al_punto(client, base_data):
    """Los dos campos que el contrato prometía y nadie llenaba hasta T-7.24."""
    inc = await _incidente()
    await _snapshot(inc)
    props = (await _pide(client, inc)).json()["observado"]["features"][0]["properties"]
    assert props["voto_contado"] is True
    assert props["pgv_cms"] == pytest.approx(6.4)


async def test_el_radio_de_cobertura_del_PENDIENTE_sale_de_los_ajustes(client, base_data):
    """Sin snapshot, el radio que se declara es con el que se VA a calcular. Con
    el valor de fábrica en los dos lados eso no lo medía nadie: aquí se lee con
    unos ajustes distintos de los de fábrica."""
    inc = await _incidente()
    ajustado = Settings().shakemap_cobertura_km * 1.5
    engine = get_engine()
    async with engine.begin() as conn:
        mapa = await leer(conn, inc, Settings(shakemap_cobertura_km=ajustado))
    assert mapa is not None and mapa.estado == C.ESTADO_PENDIENTE
    assert mapa.cobertura_km == pytest.approx(ajustado)


async def test_sin_modelo_la_capa_modelada_NO_se_dibuja_y_se_declara(client, base_data):
    """`§A.5`: sin magnitud/epicentro el mapa existe DEGRADADO y lo declara."""
    inc = await _incidente()
    await _snapshot(inc, estado=C.ESTADO_SOLO_OBSERVADO, con_modelo=False)

    cuerpo = (await _pide(client, inc)).json()
    assert cuerpo["estado"] == C.ESTADO_SOLO_OBSERVADO
    assert cuerpo["modelado"] is None, "null es «no se modeló»; un FC vacío parecería un modelo"
    assert cuerpo["fuera_de_alcance"] == [], "sin capa 2 no hay niveles que declarar"
    assert cuerpo["ley"] is None
    assert cuerpo["epicentro"] is None
    assert cuerpo["observado"]["features"], "la capa 1 sigue ahí: eso es el degradado"


async def test_el_epicentro_llega_con_su_fuente_y_su_procedencia(client, base_data):
    inc = await _incidente()
    await _snapshot(inc)

    epi = (await _pide(client, inc)).json()["epicentro"]
    assert epi["magnitud"] == pytest.approx(MAG)
    assert epi["depth_km"] == pytest.approx(PROF_KM)
    assert epi["fuente"] == "external"
    assert epi["procedencia"] == "confirmado"
    assert epi["catalog_key"] == "USGS-2017-09-19-PUE"


async def test_la_cobertura_sale_del_SNAPSHOT_y_no_de_los_ajustes_de_hoy(client, base_data):
    """Un mapa ya impreso en un dictamen firmado no puede cambiar de significado
    porque alguien suba el ajuste seis meses después."""
    inc = await _incidente()
    await _snapshot(inc)
    await _sql("UPDATE incident_shakemap SET cobertura_km = 12.5 WHERE incident_id = :i", i=inc)
    assert (await _pide(client, inc)).json()["cobertura_km"] == pytest.approx(12.5)


async def test_el_endpoint_NO_recalcula_nada(client, base_data):
    """Leer no puede escribir: si el endpoint recalculara, dos operadores verían
    mapas distintos del mismo sismo según cuándo apretaran F5."""
    inc = await _incidente()
    await _snapshot(inc)
    lee = "SELECT calculado_en FROM incident_shakemap WHERE incident_id = :i"
    antes = (await _sql(lee, i=inc))[0][0]
    await _pide(client, inc)
    await _pide(client, inc)
    despues = (await _sql(lee, i=inc))[0][0]
    assert antes == despues
