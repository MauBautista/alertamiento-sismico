"""[T-7.24] Leer el mini-ShakeMap ya calculado. **No recalcula nada.**

Y que no recalcule es diseño, no pereza (`design/BLOQUE-IV-ARQUITECTURA.md
§A.4`): el mapa no es en vivo. Si el lector recalculara, dos operadores verían
mapas distintos del mismo sismo según cuándo apretaran F5, y la consola y el PDF
del dictamen dibujarían cada uno el suyo — que es exactamente el modo de fallo
que este repositorio lleva una fase cerrando.

Vive aquí, y no dentro del router, porque **el PDF del dictamen lo reusa**: dos
lecturas del mismo snapshot acabarían discrepando en el detalle que más se mira.

LOS DOS ESTADOS QUE SÓLO EXISTEN AQUÍ
─────────────────────────────────────
* **`pendiente`** — el incidente existe y el worker todavía no ha pasado. Es una
  condición NORMAL y se declara con un 200, no con un 404 ni con un 500 (regla
  de oro 7). El cálculo nunca lo produce: es la ausencia de fila.
* **`None`** — el incidente no existe, **o la RLS no deja verlo**. El router lo
  convierte en 404 y no en 403, porque un 403 confirmaría que existe.

LA GEOMETRÍA DEL CÍRCULO SE MATERIALIZA AQUÍ
────────────────────────────────────────────
La base guarda NÚMEROS (`pga_g`, `radio_km`): guardar 64 vértices sería guardar
un dibujo, no un modelo — y un dibujo hecho a una latitud no vale a otra. Quien
pinta necesita un polígono, y se lo damos ya materializado para que la consola y
el papel no escriban dos versiones de la misma trigonometría.

⚠️ **En grados geográficos, jamás en unidades de pantalla.** Ésta es la lección
que costó la guarda `DIF-shakemap.a`: había dos capas de MapLibre con
`circle-radius` de 55 y 100 PÍXELES rotuladas «INTENSIDAD MMI», así que el mismo
anillo afirmaba ~22 km a zoom 8.5 y ~1 km a zoom 13 — cambiaba de significado
físico con cada rueda del ratón. Los puntos observados sí pueden ser símbolos en
píxeles, porque un marcador no afirma extensión: afirma un valor EN ESE PUNTO.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from sqlalchemy import text

from takab_api.geo import EARTH_RADIUS_KM
from takab_api.schemas.shakemap import (
    AnilloFeature,
    AnilloProps,
    AnillosOut,
    EpicentroOut,
    NivelFueraOut,
    PoligonoGeometry,
    PuntoFeature,
    PuntoGeometry,
    PuntoProps,
    PuntosOut,
    ShakemapOut,
)
from takab_api.settings import Settings
from takab_api.shakemap import calculo as C

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

#: Vértices del anillo exterior de cada círculo. Con 72 (uno cada 5°) la cuerda
#: se separa del arco un 0.1 % del radio —0.13 km en un anillo de 130 km—, muy por
#: debajo de la incertidumbre de la propia ley, y el polígono no se lee como un
#: polígono. Subirlo engorda la respuesta sin decir nada nuevo.
VERTICES = 72

#: El incidente manda: si no existe (o la RLS no lo deja ver) la respuesta es 404
#: aunque hubiera snapshot. El `LEFT JOIN` es lo que separa «no existe» de «no
#: calculado todavía», que son dos respuestas distintas y una de ellas es un 200.
_LEER_SQL = text("""
SELECT i.incident_id::text AS incident_id,
       m.calculado_en, m.estado, m.ley, m.epicentro,
       m.cobertura_km::float8 AS cobertura_km,
       m.puntos, m.anillos
  FROM incidents i
  LEFT JOIN incident_shakemap m ON m.incident_id = i.incident_id
 WHERE i.incident_id = CAST(:i AS uuid)
""")


async def leer(
    conn: AsyncConnection, incident_id: str, settings: Settings | None = None
) -> ShakemapOut | None:
    """El mapa de un incidente, o ``None`` si el incidente no existe para quien pide."""
    s = settings or Settings()
    fila = (await conn.execute(_LEER_SQL, {"i": incident_id})).first()
    if fila is None:
        return None

    if fila.estado is None:
        return ShakemapOut(
            incident_id=fila.incident_id,
            estado=C.ESTADO_PENDIENTE,
            # El radio con el que se VA a calcular. Un cero aquí sería un número
            # inventado sobre un mapa que todavía no existe.
            cobertura_km=s.shakemap_cobertura_km,
            calculado_en=None,
            ley=None,
            epicentro=None,
            modelado=None,
            # Vacíos, pero PRESENTES: quien pinta no tiene que distinguir «no
            # viene la colección» de «la colección no trae nada». Las dos son la
            # misma cosa aquí —todavía no hay mapa— y el estado ya lo dice.
            observado=PuntosOut(features=[]),
            fuera_de_alcance=[],
        )

    epi = fila.epicentro
    return ShakemapOut(
        incident_id=fila.incident_id,
        estado=fila.estado,
        calculado_en=fila.calculado_en,
        ley=fila.ley,
        cobertura_km=fila.cobertura_km,
        epicentro=None if epi is None else EpicentroOut(**epi),
        observado=_observado(fila.puntos or []),
        modelado=_modelado(_dibujados(fila.anillos or []), epi),
        fuera_de_alcance=_fuera_de_alcance(fila.anillos or []),
    )


def _dibujados(anillos: list[dict]) -> list[dict]:
    """Las entradas del censo que SÍ son un anillo.

    La fila guarda el censo entero de niveles —dibujados y suprimidos— en una
    sola lista, para que nadie pueda leer los anillos sin enterarse de cuáles
    faltan (`calculo.anillos_json`). Aquí se separan, y el criterio es el dato y
    no el motivo: sin radio no hay geometría que materializar.
    """
    return [a for a in anillos if a.get("radio_km") is not None]


def _fuera_de_alcance(anillos: list[dict]) -> list[NivelFueraOut]:
    """Los niveles suprimidos, con su motivo. Un hueco sin explicación se lee
    como «ese umbral no existía», y aquí los umbrales son con los que se decide."""
    return [
        NivelFueraOut(
            umbral=a["umbral"],
            pga_g=a["pga_g"],
            motivo=a.get("motivo") or C.FUERA_DEL_ALCANCE,
            radio_max_km=a.get("radio_max_km"),
        )
        for a in anillos
        if a.get("radio_km") is None
    ]


def _observado(puntos: list[dict]) -> PuntosOut:
    """Capa 1+3 como puntos GeoJSON. ⚠️ `[lon, lat]`, en ese orden."""
    return PuntosOut(
        features=[
            PuntoFeature(
                geometry=PuntoGeometry(coordinates=[p["lon"], p["lat"]]),
                properties=PuntoProps(
                    site_id=p["site_id"],
                    site_code=p["site_code"],
                    site_name=p["site_name"],
                    pga_g=p.get("pga_g"),
                    pgv_cms=p.get("pgv_cms"),
                    dist_km=p.get("dist_km"),
                    hypo_km=p.get("hypo_km"),
                    pga_g_modelada=p.get("pga_g_modelada"),
                    residuo_log10=p.get("residuo_log10"),
                    medido_en=p.get("medido_en"),
                    voto_contado=p.get("voto_contado"),
                ),
            )
            for p in puntos
        ]
    )


def _modelado(anillos: list[dict], epi: dict | None) -> AnillosOut | None:
    """Capa 2 como polígonos geográficos, o ``None`` si NO se modeló.

    ``None`` y no una colección vacía: una colección vacía se leería como «se
    modeló y no salió nada», y lo que hay que decir es que no se modeló.
    """
    if not anillos or epi is None:
        return None
    return AnillosOut(
        features=[
            AnilloFeature(
                geometry=PoligonoGeometry(
                    coordinates=[circulo(epi["lat"], epi["lon"], a["radio_km"])]
                ),
                properties=AnilloProps(
                    pga_g=a["pga_g"], radio_km=a["radio_km"], umbral=a["umbral"]
                ),
            )
            for a in anillos
        ]
    )


def circulo(lat: float, lon: float, radio_km: float, vertices: int = VERTICES) -> list[list[float]]:
    """Anillo exterior GeoJSON (`[lon, lat]`) de radio constante sobre la esfera.

    Se usa la fórmula del punto de destino sobre gran círculo y **el mismo radio
    terrestre que `geo.haversine_km`**: así el círculo que se dibuja mide, medido
    con la función que usa todo el sistema, exactamente lo que el anillo afirma.
    Una aproximación plana en grados se estiraría al norte y al sur, y a 130 km de
    radio ya se ve.

    El anillo se cierra repitiendo el primer vértice, que es lo que exige GeoJSON.

    ⚠️ **La longitud se normaliza a [−180, 180]**, que es lo que exige RFC 7946
    §3.1.1 y lo que MapLibre necesita para no dar la vuelta al mundo. La fórmula
    devuelve `lambda1 + atan2(…)`, que cae en `[lambda1−π, lambda1+π]`: para un
    epicentro en lon −98.49 eso llegaba a **−278.49°** (medido el 2026-09-21 con
    un anillo gigante), y −278.49 no es una longitud.

    Normalizar deja cada vértice válido; un anillo que **cruce** el antimeridiano
    seguiría necesitando partirse en dos (RFC 7946 §3.1.9), y no se parte aquí
    porque con el tope del radio no puede pasarle a esta red: medido sobre los
    inmuebles sembrados en `db/seeds/` (longitudes −103.29 a −93.90), un anillo
    de 1 200 km alrededor de los dos extremos queda dentro de [−114.7, −82.5].
    """
    delta = radio_km / EARTH_RADIUS_KM
    phi1, lambda1 = math.radians(lat), math.radians(lon)
    salida: list[list[float]] = []
    for i in range(vertices):
        theta = 2.0 * math.pi * i / vertices
        phi2 = math.asin(
            math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
        )
        lambda2 = lambda1 + math.atan2(
            math.sin(theta) * math.sin(delta) * math.cos(phi1),
            math.cos(delta) - math.sin(phi1) * math.sin(phi2),
        )
        salida.append([_lon_normalizada(math.degrees(lambda2)), math.degrees(phi2)])
    salida.append(salida[0])
    return salida


def _lon_normalizada(grados: float) -> float:
    """La longitud al rango de GeoJSON, `[−180, 180)`.

    El antimeridiano sale en −180 y no en +180. Los dos son válidos y designan el
    mismo meridiano; se elige uno para que dos vértices calculados de la misma
    manera no salgan con nombres distintos.
    """
    return grados - 360.0 * math.floor((grados + 180.0) / 360.0)
