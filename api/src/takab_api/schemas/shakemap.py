"""[T-7.24] El mini-ShakeMap de un incidente, tal como lo leen la consola y el PDF.

Sale en **GeoJSON** y en dos colecciones separadas, y esa separación es el
contrato: `observado` son puntos MEDIDOS y `modelado` son anillos de un MODELO.
Jamás la misma codificación visual para los dos (`D-08` · `§A.3`), y para que eso
sea comprobable y no una buena intención, **la procedencia viaja en cada
feature**: quien las mezcle en una lista no puede perderla por el camino.

Lo que NO hay aquí, y cada ausencia tiene su ficha detrás:

* **No hay escala de intensidad.** `dictamen/model.py::NO_MMI` ya está impreso en
  documentos FIRMADOS diciendo que TAKAB no reporta intensidad macrosísmica ni
  isosistas; derivar una MMI de la PGA de un sensor volvería falsa una frase ya
  firmada. Lo que se codifica es PGA en g, que es lo que se mide.
* **No hay malla ni superficie interpolada.** Con unidades de estaciones no se
  interpola una superficie y se le llama medición.
* **No hay forma de onda** (regla de oro 9): el mapa se construye de features.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class EpicentroOut(BaseModel):
    """De dónde salió el sismo, con de dónde salió el dato.

    `fuente` es quién lo localizó (`seismic_events.source`) y `procedencia` es el
    estado del glosario (`shared/glossary/procedencia.json`). Son cosas distintas
    y las dos hacen falta: el centroide de nuestro propio cuórum es un epicentro
    NUESTRO, y presentarlo sin decirlo lo confundiría con la solución de una
    agencia.
    """

    lat: float
    lon: float
    depth_km: float | None = None
    #: `None` = no hay magnitud citable. Sin ella NO hay capa modelada, y eso es
    #: lo que el mapa declara en vez de inventarse un modelo.
    magnitud: float | None = None
    fuente: str
    procedencia: str
    catalog_key: str | None = None


class PuntoGeometry(BaseModel):
    """Punto GeoJSON. ⚠️ `coordinates` es `[lon, lat]`, en ese orden."""

    type: Literal["Point"] = "Point"
    coordinates: list[float]


class PoligonoGeometry(BaseModel):
    """Polígono GeoJSON: un anillo exterior cerrado, en grados.

    ⚠️ **En grados, no en píxeles.** La guarda que T-7.24 sustituye nació de dos
    capas de MapLibre con `circle-radius` en unidades de pantalla rotuladas
    «INTENSIDAD MMI»: el mismo anillo afirmaba ~22 km a zoom 8.5 y ~1 km a zoom
    13. Un anillo que afirma «aquí el modelo predice 0.02 g» tiene que seguir
    afirmándolo a cualquier zoom, y para eso su geometría es geográfica.
    """

    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[list[float]]]


class PuntoProps(BaseModel):
    """Capa 1 (OBSERVADO) + capa 3 (RESIDUO) de un inmueble.

    ⚠️ Ninguno de los campos anulables de abajo lleva ``= None``, y no es
    descuido: un defecto en el esquema sale del generador de OpenAPI como campo
    OPCIONAL, y entonces quien consume tiene que distinguir «la clave no vino»
    de «la clave vino en null» — dos preguntas donde el cable sólo responde
    una. Aquí la clave viaja SIEMPRE; lo que puede faltar es el VALOR, y eso es
    ``null`` con su razón escrita. El constructor de `shakemap/lectura.py` las
    pasa todas, una a una, y `web/src/sdkTypeParity.test.ts` cazó el espejo a
    mano que había divergido justo por esto.
    """

    site_id: str
    #: [T-6.04] El código va SIEMPRE: `SiteLabel` decide con él si pinta la cinta
    #: de demostración. Un nombre sin código no se puede rotular.
    site_code: str
    site_name: str
    procedencia: Literal["measured"] = "measured"
    #: `None` = el gabinete no publicó nada en la ventana. **No es 0 g** (regla
    #: de oro 7): mostrar un cero por un silencio diría que no se movió.
    pga_g: float | None
    pgv_cms: float | None
    dist_km: float | None
    hypo_km: float | None
    #: Lo que ATTEN-LAW v1 predice A ESA DISTANCIA. Va junto al medido a
    #: propósito: un pico suelto no dice si es mucho o poco para esta distancia.
    pga_g_modelada: float | None
    #: **El producto de la ficha.** `log10(medida/modelada)`: positivo = sacudió
    #: MÁS de lo que la ley predice ahí. Es lo único que el mapa dice y una regla
    #: de tres no.
    residuo_log10: float | None
    medido_en: datetime | None
    #: ¿Contó su voto en el cuórum de red? Es el `counted` de la tabla por
    #: estación (`EstacionOut`), sin recalcularlo: viaja en la misma lectura de
    #: la que sale el pico. `None` = no hay evento de red que contar, que **no**
    #: es «no votó». Distingue en el mapa al inmueble que participó en el cuórum
    #: del que sólo estaba ahí — y el cuórum es lo único, con SASMEX, que puede
    #: ordenar evacuar.
    voto_contado: bool | None


class AnilloProps(BaseModel):
    """Capa 2 (MODELADO): un nivel de PGA constante y su radio en kilómetros."""

    procedencia: Literal["modeled"] = "modeled"
    pga_g: float
    radio_km: float
    #: Qué umbral de ESTE sistema es ese nivel (`pga_watch_g`…). No es una escala
    #: inventada: son los números con que el gabinete y el criterio de identidad
    #: ya deciden.
    umbral: str


class NivelFueraOut(BaseModel):
    """Un nivel de la capa 2 que **no se dibujó**, y por qué.

    Existe para que un umbral suprimido se DIGA: un anillo que falta sin
    explicación se lee como «ese umbral no existía», y aquí los umbrales son los
    que este sistema usa para decidir. `motivo` es el vocabulario cerrado de
    `shakemap.calculo.MOTIVOS_FUERA`, que trae también la frase para imprimirlo.
    """

    umbral: str
    pga_g: float
    #: `bajo_la_superficie` · `no_invertible` · `fuera_del_alcance`.
    motivo: str
    #: El tope del radio VIGENTE cuando se calculó, en km. Sin él, «fuera del
    #: alcance» no dice de qué alcance y deja de ser una afirmación.
    radio_max_km: float | None


class PuntoFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: PuntoGeometry
    properties: PuntoProps


class AnilloFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: PoligonoGeometry
    properties: AnilloProps


#: ⚠️ `features` NO lleva valor por defecto, y no es un descuido. Un campo con
#: defecto sale del generador de OpenAPI como OPCIONAL, y entonces la consola
#: tiene que preguntarse si la colección existe antes de mirar si está vacía —
#: dos preguntas donde el cable sólo responde una—. Estas colecciones SIEMPRE
#: viajan: vacías cuando no hay nada, presentes siempre. Lo cazó
#: `web/src/sdkTypeParity.test.ts` al sustituir el espejo a mano por el tipo
#: generado.
class PuntosOut(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[PuntoFeature]


class AnillosOut(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[AnilloFeature]


class ShakemapOut(BaseModel):
    """El mapa entero de un incidente."""

    incident_id: str
    #: `completo` / `solo_observado` / `sin_datos` / **`pendiente`**. El último no
    #: sale del cálculo: lo pone este lector cuando el worker todavía no ha
    #: pasado. «Todavía no» es una condición normal del sistema —el mapa no es en
    #: vivo— y dejarla sin declarar es lo que pone una pantalla en blanco.
    estado: str
    #: `None` en `pendiente`. Cuándo se hizo el mapa, que es lo que dice con qué
    #: información se hizo.
    calculado_en: datetime | None
    #: `'ATTEN-LAW v1'` o `None`. `None` significa que **no se modeló**, no que se
    #: modelara con otra ley.
    ley: str | None
    #: Radio de representatividad de un inmueble instrumentado, en km. Fuera de
    #: él quien pinta declara `SIN COBERTURA`: es una propiedad del ESPACIO, no
    #: un estado del mapa, y no se extrapola color.
    cobertura_km: float
    epicentro: EpicentroOut | None
    #: Siempre presente, vacío incluido: ver la nota de `PuntosOut`.
    observado: PuntosOut
    #: `None` —y no una colección vacía— cuando no hay capa 2. Una colección
    #: vacía se leería como «se modeló y no salió nada»; `null` dice «no se
    #: modeló», que es lo que pasó. Con CERO medidas tampoco hay capa 2 (`§A.3`:
    #: «la capa 2 sola no aporta nada que no se calcule con una regla de tres»).
    modelado: AnillosOut | None
    #: Los niveles que el modelo consideró y **no pudo dibujar**, con su motivo.
    #: Vacío cuando no hubo capa 2 en absoluto —eso lo dice `ley is None`— o
    #: cuando se dibujaron todos.
    fuera_de_alcance: list[NivelFueraOut]
