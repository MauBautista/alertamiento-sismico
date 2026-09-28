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

[T-9.51 · D-44] LO QUE SE DERIVA AL LEER, Y LO QUE NO
─────────────────────────────────────────────────────
* **La MMI ESTIMADA de cada punto** (`DERIVADOS_AL_LEER`) sale de su PGA con
  `gmice`, aquí y no en la base: es una conversión de un dato que ya está
  guardado, y guardarla sería un segundo sitio donde puede divergir el día que
  cambie la relación citada.
* **El máximo de la superficie** se calcula sobre la zona AJUSTADA, al leer, de
  la malla guardada.
* **La malla NO viaja en el JSON**: viaja en el PNG (`superficie_png`), que se
  pinta con la banda del dictamen DEL SITIO. El PNG tampoco recalcula nada: pinta
  la superficie del snapshot, así que dos operadores ven la misma.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING

from sqlalchemy import text

from takab_api.dictamen.rules import resolve_params_v2
from takab_api.dictamen.service import _RULESET_SQL
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
    SuperficieOut,
)
from takab_api.settings import Settings
from takab_api.shakemap import calculo as C
from takab_api.shakemap import gmice, raster
from takab_api.shakemap import superficie as SUP

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

#: Vértices del anillo exterior de cada círculo. Con 72 (uno cada 5°) la cuerda
#: se separa del arco un 0.1 % del radio —0.13 km en un anillo de 130 km—, muy por
#: debajo de la incertidumbre de la propia ley, y el polígono no se lee como un
#: polígono. Subirlo engorda la respuesta sin decir nada nuevo.
VERTICES = 72

#: [T-9.51 · D-44] Campos de `PuntoProps` que NO están en la fila: los deriva este
#: lector de la PGA guardada. El censo del contrato (`test_pasada.py`) los descuenta
#: de lo que la pasada tiene que escribir.
DERIVADOS_AL_LEER = ("mmi_estimada", "mmi_romano")

#: El incidente manda: si no existe (o la RLS no lo deja ver) la respuesta es 404
#: aunque hubiera snapshot. El `LEFT JOIN` es lo que separa «no existe» de «no
#: calculado todavía», que son dos respuestas distintas y una de ellas es un 200.
_LEER_SQL = text("""
SELECT i.incident_id::text AS incident_id,
       m.calculado_en, m.estado, m.ley, m.epicentro,
       m.cobertura_km::float8 AS cobertura_km,
       m.puntos, m.anillos, m.superficie, m.superficie_motivo
  FROM incidents i
  LEFT JOIN incident_shakemap m ON m.incident_id = i.incident_id
 WHERE i.incident_id = CAST(:i AS uuid)
""")


async def leer(
    conn: AsyncConnection, incident_id: str, settings: Settings | None = None
) -> ShakemapOut | None:
    """El mapa de un incidente, o ``None`` si el incidente no existe para quien pide."""
    return (await leer_con_malla(conn, incident_id, settings))[0]


async def leer_con_malla(
    conn: AsyncConnection, incident_id: str, settings: Settings | None = None
) -> tuple[ShakemapOut | None, SUP.Superficie | None]:
    """[T-9.53 · D-44] `leer` y, además, la MALLA de la superficie del snapshot.

    Es la MISMA consulta y la misma traducción que la consola: el PDF necesita la
    malla para embeber la imagen, y la malla no viaja en el JSON (va en el PNG).
    Abrir otra consulta para sacarla sería un segundo lector del mismo snapshot.
    """
    s = settings or Settings()
    fila = (await conn.execute(_LEER_SQL, {"i": incident_id})).first()
    if fila is None:
        return None, None
    salida = _salida(fila, s)
    if salida.superficie is not None:
        # [T-9.52] Los MISMOS cortes con que `superficie_png` pinta la imagen.
        umbrales = await umbrales_de_banda(conn, incident_id, s)
        if umbrales is not None:
            salida.superficie.verde_max_g, salida.superficie.rojo_min_g = umbrales
    return salida, _malla(fila.superficie if fila.estado is not None else None)


def desde_mapa(
    incident_id: str, mapa: C.Mapa, *, calculado_en: datetime
) -> tuple[ShakemapOut, SUP.Superficie | None]:
    """[T-9.53 · D-44] Un mapa calculado EN MEMORIA, traducido como si se hubiera leído.

    Es lo que usa el PDF cuando el incidente no tiene snapshot (`servicio.calcula_uno`).
    Pasa por la MISMA forma persistida que escribe la pasada (`calculo.*_json` y
    `Superficie.to_json`) y por la misma traducción de la fila: así el papel dibuja
    exactamente lo que la pasada habría escrito, redondeos del micro-g incluidos.
    """
    fila = SimpleNamespace(
        incident_id=incident_id,
        estado=mapa.estado,
        calculado_en=calculado_en,
        ley=mapa.ley,
        epicentro=C.epicentro_json(mapa),
        cobertura_km=mapa.cobertura_km,
        puntos=C.puntos_json(mapa),
        anillos=C.anillos_json(mapa),
        superficie=None if mapa.superficie is None else mapa.superficie.to_json(),
        superficie_motivo=mapa.superficie_motivo,
    )
    return _salida(fila, Settings()), _malla(fila.superficie)


def _malla(crudo: dict | None) -> SUP.Superficie | None:
    return None if crudo is None else SUP.Superficie.from_json(crudo)


def _salida(fila, s: Settings) -> ShakemapOut:  # noqa: ANN001 - fila de SQLAlchemy o su imitación
    """La traducción de UNA fila de `_LEER_SQL` al contrato. Compartida por la lectura
    del snapshot y por el cálculo a demanda (`desde_mapa`)."""
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
            superficie=None,
            superficie_motivo=None,
            superficie_motivo_texto=None,
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
        superficie=_superficie(fila.incident_id, fila.superficie),
        superficie_motivo=fila.superficie_motivo,
        # Un motivo que este lector no conoce se dice tal cual y sin frase: una
        # frase inventada sería peor que ninguna.
        superficie_motivo_texto=SUP.MOTIVOS.get(fila.superficie_motivo or ""),
    )


def ruta_png(incident_id: str) -> str:
    """Ruta RELATIVA del PNG de la superficie: la sirve la API, sin URL prefirmada."""
    return f"/incidents/{incident_id}/shakemap/superficie.png"


def _superficie(incident_id: str, crudo: dict | None) -> SuperficieOut | None:
    """Los metadatos de la superficie, SIN la malla, y su máximo en zona AJUSTADA."""
    if crudo is None:
        return None
    sup = SUP.Superficie.from_json(crudo)
    ajustadas = [
        v
        for fila_v, fila_a in zip(sup.pga_g, sup.ajustada, strict=True)
        for v, a in zip(fila_v, fila_a, strict=True)
        if a
    ]
    pga_max = max(ajustadas) if ajustadas else None
    return SuperficieOut(
        bbox=[sup.oeste, sup.sur, sup.este, sup.norte],
        ancho=sup.ancho,
        alto=sup.alto,
        n_sensores=sup.n_sensores,
        n_calibrados=sup.n_calibrados,
        escala_km=sup.escala_km,
        ley=sup.ley,
        metodo=sup.metodo,
        # La cita que viajó CON la superficie, no la de hoy: un mapa ya impreso no
        # cambia de fuente porque alguien cambie la relación mañana.
        cita_mmi=crudo.get("cita_mmi") or gmice.CITA,
        pga_max_g=pga_max,
        mmi_max_estimada=gmice.mmi_de_pga(pga_max),
        png=ruta_png(incident_id),
        # Los pone `leer_con_malla`, que tiene la conexión para resolver los del sitio.
        verde_max_g=None,
        rojo_min_g=None,
    )


#: La superficie guardada y DÓNDE está el incidente, para la banda del sitio.
_PNG_SQL = text("""
SELECT i.tenant_id::text AS tenant_id, i.site_id::text AS site_id,
       m.superficie
  FROM incidents i
  LEFT JOIN incident_shakemap m ON m.incident_id = i.incident_id
 WHERE i.incident_id = CAST(:i AS uuid)
""")

#: El `rule_set` activo del sitio (sitio sobre cliente), el MISMO texto que usa la
#: pasada del dictamen (`dictamen/service._RULESET_SQL`) traducido a parámetros de
#: SQLAlchemy: una segunda consulta escrita a mano acabaría eligiendo otra fila, y
#: el mapa pintaría ROJO donde el dictamen del mismo sitio dice VERDE.
_RULESET_TEXT = text(re.sub(r"%\((\w+)\)s", r"CAST(:\1 AS uuid)", _RULESET_SQL))

#: Resultado de `superficie_png` cuando el incidente existe pero no tiene superficie.
SIN_SUPERFICIE = "sin_superficie"


async def superficie_png(
    conn: AsyncConnection, incident_id: str, settings: Settings | None = None
) -> bytes | str | None:
    """[T-9.51 · D-44] El PNG de la superficie del snapshot, con la banda DEL SITIO.

    ``None`` si el incidente no existe para quien pide (404, no 403);
    `SIN_SUPERFICIE` si existe y no hay superficie (sin snapshot, anterior a D-44 o
    con motivo). No recalcula nada.
    """
    fila = (await conn.execute(_PNG_SQL, {"i": incident_id})).first()
    if fila is None:
        return None
    if fila.superficie is None:
        return SIN_SUPERFICIE
    verde, rojo = await _umbrales_del_sitio(conn, fila, settings)
    return raster.png(SUP.Superficie.from_json(fila.superficie), verde_max_g=verde, rojo_min_g=rojo)


async def umbrales_de_banda(
    conn: AsyncConnection, incident_id: str, settings: Settings | None = None
) -> tuple[float, float] | None:
    """[T-9.53 · D-43] ``(verde_max_g, rojo_min_g)`` del sitio del incidente, o ``None``.

    Los MISMOS con que se pinta el PNG de la consola: el PDF colorea la superficie
    con ellos, y un papel que pintara ROJO donde la pantalla del mismo sitio pinta
    VERDE sería el defecto que esta función existe para impedir.
    """
    fila = (await conn.execute(_PNG_SQL, {"i": incident_id})).first()
    if fila is None:
        return None
    return await _umbrales_del_sitio(conn, fila, settings)


async def _umbrales_del_sitio(
    conn: AsyncConnection, fila, settings: Settings | None
) -> tuple[float, float]:  # noqa: ANN001 - fila de `_PNG_SQL`
    config = (
        await conn.execute(_RULESET_TEXT, {"site": fila.site_id, "tenant": fila.tenant_id})
    ).scalar()
    params = resolve_params_v2(config, settings or Settings())
    return params.verde_max_g, params.rojo_min_g


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
                    # [T-9.51 · D-44] Derivadas al leer (`DERIVADOS_AL_LEER`).
                    mmi_estimada=(mmi := gmice.mmi_de_pga(p.get("pga_g"))),
                    mmi_romano=None if mmi is None else gmice.romano(mmi),
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
