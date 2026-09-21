"""T-7.24 · Mini-ShakeMap por evento: las TRES capas, en lógica pura.

Módulo **puro**: no toca la base, ni la red, ni el reloj. Es una función de sus
argumentos, igual que `forensics/correlacion.py` y `replay/plan.py`, y por eso se
prueba entero sin Postgres. Determinista, sin IA (regla de oro 1). No decide nada
operativo: este mapa es descriptivo y **jamás** gatea una actuación.

--------------------------------------------------------------------------------
QUÉ ES, Y SOBRE TODO QUÉ NO ES
--------------------------------------------------------------------------------

Es el mapa de la sacudida **observada** en los inmuebles instrumentados de un
cliente durante un evento (`design/BLOQUE-IV-ARQUITECTURA.md §A.1`).

**No** es un ShakeMap del USGS ni del SSN: aquéllos interpolan cientos de
estaciones; aquí hay unidades. **No** hay interpolación, ni suavizado, ni
isosistas. **No** hay escala de intensidad macrosísmica: `dictamen/model.py::
NO_MMI` ya está impreso en documentos FIRMADOS diciendo que TAKAB no reporta
intensidad macrosísmica, y derivar una MMI de la PGA de un sensor volvería falsa
una frase ya firmada — la familia de defectos que costó `T-7.34`, `T-7.38` y
`T-7.39`. Lo que se codifica es **PGA en g**, que es lo que se mide.

--------------------------------------------------------------------------------
LAS TRES CAPAS, Y POR QUÉ NO SE MEZCLAN
--------------------------------------------------------------------------------

Con 3–10 inmuebles no se puede interpolar una superficie de intensidad y llamarla
medición. La salida honesta no es negarse a dibujar: es dibujar capas separadas
que declaran de dónde sale cada número (`§A.3`).

* **CAPA 1 · OBSERVADO** (`Punto.pga_g`, `procedencia = "measured"`) — un punto
  por inmueble instrumentado, con el pico medido en la ventana del incidente.
  Sin interpolar, sin suavizar. Un inmueble que **no** midió entra igual, con
  `pga_g = None`: «no publicó» no es «0 g» (regla de oro 7).

* **CAPA 2 · MODELADO** (`Anillo`, `procedencia = "modeled"`) — ATTEN-LAW v1,
  `geo.pga_law_g(M, geo.hypo_km(R_epi, prof))`. Como la ley **sólo** depende de
  la distancia hipocentral, el campo es radialmente simétrico y se publica como
  ANILLOS de PGA constante, no como una malla. Los niveles son los umbrales con
  que este sistema ya decide, no una escala inventada, y por eso **se DERIVAN**
  de los campos de PGA de `felt.Thresholds` (`UMBRALES`) en vez de escribirse.
  ⚠️ **Y no se publica sobre cero medidas**: ver más abajo.

* **CAPA 3 · RESIDUO** (`Punto.residuo_log10`) — `log10(medido / modelado)` por
  punto. Positivo = sacudió MÁS de lo que la ley predice a esa distancia. **Es el
  producto de la ficha, no un adorno**: la capa 2 sola se calcula con una regla de
  tres y la capa 1 sola no se lee espacialmente; el residuo es lo único que dice
  algo que el modelo no sabía (suelo blando, el edificio, o las dos cosas).

--------------------------------------------------------------------------------
SIN UNA SOLA MEDIDA NO HAY CAPA 2 (y esto es la mitad de la ficha)
--------------------------------------------------------------------------------

`§A.3`: «la capa 2 sola no aporta nada que no se calcule con una regla de tres».
Así que cuando NINGÚN inmueble midió, el mapa **no publica el modelo**: ni la
ley, ni los anillos, ni la PGA modelada de cada punto. Sale `sin_datos` y ya. Sin
esto, un incidente sin una sola medida devolvía epicentro, ley y anillos, o sea
un mapa de puro modelo presentado como el mapa de la sacudida — exactamente lo
que el encabezado de este módulo dice que NO es.

Lo que **sí** sigue viajando es el epicentro, y no es una excepción: el epicentro
no es la capa 2, es el hecho externo que la ancla —con su `fuente` y su
`procedencia`— y sin él el mapa no podría decir siquiera de qué sismo no midió
nada. Lo que se retira es la AFIRMACIÓN del modelo, no la cita de un tercero.

--------------------------------------------------------------------------------
POR QUÉ EL RADIO DEL ANILLO VA EN KILÓMETROS Y SE DESPEJA DE LA LEY
--------------------------------------------------------------------------------

Se despeja invirtiendo la propia ley, `R_hipo = 10**(0.5*M − 2.8) / PGA`, y se
proyecta a la superficie con la profundidad, `R_epi = √(R_hipo² − prof²)`. Así
el anillo y el punto salen del MISMO número: evaluar la ley en `R_epi` devuelve
exactamente el nivel del anillo, y eso lo comprueba una prueba.

⚠️ **Y va en kilómetros a propósito.** La guarda que esta ficha sustituye
(`MapPanel.test.tsx`) nació de dos capas con `circle-radius` en **píxeles de
pantalla** rotuladas «INTENSIDAD MMI»: el mismo anillo afirmaba ~22 km a zoom 8.5
y ~1 km a zoom 13, o sea que cambiaba de significado físico con cada rueda del
ratón. Un anillo que afirma «aquí el modelo predice 0.02 g» tiene que seguir
afirmando lo mismo a cualquier zoom, y la única forma es que su radio sea una
distancia y no una medida de pantalla.

--------------------------------------------------------------------------------
EL RADIO TIENE TOPE, Y UN NIVEL QUE NO SE DIBUJA SE DECLARA
--------------------------------------------------------------------------------

**ATTEN-LAW v1 es ILUSTRATIVA** (`geo.py`), y un anillo de miles de kilómetros no
mide nada: para el M7.1 de referencia, el nivel de 0.001 g —el piso de coherencia
de `T-5.11`, que NUNCA fue un nivel de mapa— despeja **5 623.2 km**, un círculo
que pasa por el Ártico canadiense alrededor de un epicentro mexicano; con el M8.2
de Chiapas, **19 952.6 km**, que sobre la esfera es una tapa alrededor del
ANTÍPODA (medido el 2026-09-21). Por eso el cálculo recibe un tope
(`radio_max_km`) y por encima de él **no dibuja**: lo DECLARA.

El tope no se inventa aquí y no es un ajuste nuevo: lo pone quien llama, y lo
deriva de `correlation_max_km` (1 200 km), que es la distancia máxima
epicentro↔sitio con la que ESTE sistema acepta que un sismo del catálogo sea el
que sacudió este edificio (`forensics/correlacion.py`, con sus cifras: Chiapas
2017 a 737 km, Chile a 6 389 km). Dibujar un anillo más allá afirmaría que el
modelo alcanza donde el propio sistema se niega a atribuir.

Tres razones distintas para NO dibujar un nivel, y las tres se dicen
(`MOTIVOS_FUERA`), porque un nivel que desaparece en silencio se lee como «ese
umbral no existía»:

* `bajo_la_superficie` — `R_hipo ≤ prof`: sólo se alcanzaría dentro de la tierra,
  y dibujarlo como un círculo de radio 0 afirmaría que en el epicentro se llegó a
  él.
* `no_invertible` — `R_hipo < 1 km`: la ley tiene un piso de 1 km
  (`geo.pga_law_g`), y por debajo cualquier radio daría el mismo valor.
* `fuera_del_alcance` — el radio existe pero pasa del tope.

--------------------------------------------------------------------------------
LO QUE ESTE MÓDULO NO DECIDE
--------------------------------------------------------------------------------

`SIN COBERTURA` **no es un estado del mapa**: es una propiedad del espacio —fuera
del radio de representatividad de todo inmueble instrumentado— y la declara quien
pinta. Aquí sólo viaja el radio (`Mapa.cobertura_km`), y el cálculo no recorta
nada con él: un punto medido sigue siendo un hecho aunque su disco sea pequeño.

Cero forma de onda cruda (regla de oro 9): la entrada son features ya agregadas.

--------------------------------------------------------------------------------
UNA DESVIACIÓN DE LA FICHA, ESCRITA
--------------------------------------------------------------------------------

`TASKS.md` dice «cálculo por evento en el worker de incidentes **(numpy)**», y
aquí no hay numpy: son unas decenas de puntos y tres operaciones escalares por
punto, así que `math` puro las hace igual y sin añadir una dependencia al camino
que corre dentro del bucle del worker. Se escribe en vez de callarse, por la
misma razón que la desviación de los tokens `--tk-pga-*`: una diferencia con la
ficha que nadie declara parece un olvido.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from datetime import datetime

from takab_api.felt import Thresholds
from takab_api.geo import hypo_km, pga_law_g

#: La ley que produce la capa 2, citada por su nombre. Se escribe en el snapshot
#: para que un mapa viejo diga con qué se modeló, y no con la ley de hoy.
LEY = "ATTEN-LAW v1"

# --- vocabulario cerrado: el estado del mapa ----------------------------------
#
# Los tres primeros los produce este módulo y se PERSISTEN. El cuarto no: lo pone
# el LECTOR cuando el worker todavía no ha pasado por ese incidente, y por eso no
# está en `ESTADOS_PERSISTIDOS` ni cabe en el CHECK de la tabla.

#: Epicentro y magnitud citados, y al menos un inmueble midió. Las tres capas.
ESTADO_COMPLETO = "completo"
#: Hay medidas, pero no hay epicentro o no hay magnitud: el mapa existe
#: DEGRADADO —capa 1 sola— y lo declara, en vez de inventar un modelo (`§A.5`).
ESTADO_SOLO_OBSERVADO = "solo_observado"
#: Ningún inmueble instrumentado midió en la ventana. Gana sobre «hay modelo»:
#: un mapa de puro modelo no es un mapa de la sacudida.
ESTADO_SIN_DATOS = "sin_datos"
#: El worker aún no lo ha calculado. **Lo pone el lector**, nunca el cálculo.
ESTADO_PENDIENTE = "pendiente"

#: Los que caben en la tabla. `ESTADO_PENDIENTE` es la ausencia de fila.
ESTADOS_PERSISTIDOS = (ESTADO_COMPLETO, ESTADO_SOLO_OBSERVADO, ESTADO_SIN_DATOS)

# --- vocabulario cerrado: la procedencia de cada valor -------------------------
#
# D-08 · §A.3: «jamás se pinta lo estimado con la misma codificación visual que lo
# medido, y el dato lo declara». Viaja EN EL DATO y no en la capa que lo lleva,
# para que un consumidor que mezcle features no pueda perderla por el camino.

PROC_MEDIDO = "measured"
PROC_MODELADO = "modeled"

# --- vocabulario cerrado: los niveles de los anillos ---------------------------
#
# Son **los umbrales con que ESTE sistema decide**, no una escala inventada, y
# por eso no se escriben: se DERIVAN de los campos de PGA de `felt.Thresholds`,
# que es la banda del inmueble —la misma que arma los actuadores del gabinete y
# la que el dictamen imprime—. Consecuencias buscadas:
#
# * si alguien cambia un umbral, el anillo cambia con él;
# * si alguien añade un umbral de PGA a la banda, el mapa lo publica solo;
# * y **no hay dónde teclear un número**: los valores los resuelve quien llama,
#   del `rule_set` que regía en la apertura del incidente y con su procedencia.
#   Un número de fábrica presentado como del edificio es el defecto que cerró
#   `T-7.35`.
#
# ⚠️ Sólo los campos en **g**: el anillo es un nivel de PGA (la ley predice PGA),
# así que `pgv_watch_cms` / `pgv_trip_cms` no pueden ser anillos. El sufijo es el
# criterio porque es la unidad, que es lo que hace o no comparable el número.
#
# ⚠️ Y aquí NO está `correlacion_min_pga_g` (0.001 g). Es el piso de coherencia
# de identidad de `T-5.11` —«¿pudo notarse siquiera aquí?»—, no un umbral con el
# que se decida nada sobre el edificio, y como nivel de mapa producía anillos de
# 5 623 km para el M7.1 de referencia: la unidad era correcta y el significado,
# falso. Retirado el 2026-09-21 por decisión del integrador.

#: Los niveles publicables, derivados de la banda del inmueble por su unidad.
UMBRALES = tuple(f.name for f in dataclasses.fields(Thresholds) if f.name.endswith("_g"))

#: Nombres propios de los dos que existen hoy, para que las guardas y la consola
#: no escriban la cadena a mano. Que sigan siendo exactamente `UMBRALES` lo mide
#: `test_calculo.py::test_los_niveles_publicables_son_los_de_PGA_de_la_banda_del_inmueble`.
UMBRAL_WATCH = "pga_watch_g"
UMBRAL_TRIP = "pga_trip_g"

# --- vocabulario cerrado: por qué un nivel NO se dibuja -------------------------
#
# Molde de `forensics/correlacion.py::MOTIVOS`: cada motivo con su frase, para
# que la consola y el papel puedan AFIRMAR por qué falta un anillo en vez de
# dejar un hueco que se lee como «ese umbral no existía». Ninguno es un error.

#: `R_hipo ≤ prof`: ese valor sólo se alcanza dentro de la tierra.
FUERA_BAJO_LA_SUPERFICIE = "bajo_la_superficie"
#: `R_hipo < 1 km`: la ley tiene piso de 1 km y por debajo no es invertible.
FUERA_NO_INVERTIBLE = "no_invertible"
#: El radio existe pero pasa del tope del modelo (ver el encabezado).
FUERA_DEL_ALCANCE = "fuera_del_alcance"

MOTIVOS_FUERA: dict[str, str] = {
    FUERA_BAJO_LA_SUPERFICIE: (
        "ese nivel sólo se alcanzaría bajo la superficie, más hondo que el foco"
    ),
    FUERA_NO_INVERTIBLE: "ese nivel queda por debajo del piso de 1 km de la ley",
    FUERA_DEL_ALCANCE: "ese nivel caería más lejos de donde el modelo puede afirmar nada",
}

#: Piso de la ley (`geo.pga_law_g` usa `max(R_hipo, 1)`). Por debajo, la ley no es
#: invertible: cualquier radio devuelve el mismo valor.
PISO_DE_LA_LEY_KM = 1.0


@dataclass(frozen=True)
class Nivel:
    """Un nivel de PGA con el nombre del umbral del que sale."""

    umbral: str
    pga_g: float


@dataclass(frozen=True)
class Medida:
    """Lo medido en UN inmueble, tal como llega de la tabla por estación.

    `dist_km` es epicentro↔inmueble y puede faltar (sin epicentro no hay
    distancia). `pga_g`/`pgv_cms` pueden faltar: el gabinete pudo no publicar
    nada en la ventana, y eso no es cero.
    """

    site_id: str
    site_code: str
    site_name: str
    lat: float
    lon: float
    dist_km: float | None
    pga_g: float | None
    pgv_cms: float | None
    medido_en: datetime | None
    #: ¿Contó su voto en el cuórum de red? Es el `counted` de `EstacionOut`, sin
    #: recalcular nada: viaja en la MISMA tabla por estación de la que sale el
    #: pico. `None` = no hay evento de red que contar, que **no** es «no votó»
    #: (regla de oro 7). Es lo que distingue en el mapa a un inmueble que
    #: participó en el cuórum de uno que sólo estaba ahí — y el cuórum es lo
    #: único, con SASMEX, que puede ordenar evacuar.
    voto_contado: bool | None = None


@dataclass(frozen=True)
class Epicentro:
    """El origen del sismo, con de dónde salió. `magnitud` puede faltar.

    `fuente` es quién lo localizó (`seismic_events.source`: `local_quorum`,
    `sasmex`, `catalog`…) y `procedencia` es el estado del glosario
    (`shared/glossary/procedencia.json`). Son cosas distintas y las dos hacen
    falta: el centroide de un cuórum propio es un epicentro **nuestro**, y
    presentarlo sin decirlo lo confundiría con la solución de una agencia.
    """

    lat: float
    lon: float
    depth_km: float | None
    magnitud: float | None
    fuente: str
    procedencia: str
    catalog_key: str | None

    @property
    def modelable(self) -> bool:
        """¿Se puede aplicar la ley? Sin magnitud, no. Y no se inventa una."""
        return self.magnitud is not None


@dataclass(frozen=True)
class Punto:
    """Capa 1 + su modelado + su residuo, en un inmueble concreto."""

    site_id: str
    site_code: str
    site_name: str
    lat: float
    lon: float
    #: Siempre `PROC_MEDIDO`: lo que sitúa este punto es el edificio, y lo que
    #: afirma es el valor EN ESE PUNTO. El campo existe para que la procedencia
    #: viaje en el dato aunque alguien mezcle las dos capas en una lista.
    procedencia: str
    pga_g: float | None
    pgv_cms: float | None
    dist_km: float | None
    hypo_km: float | None
    pga_g_modelada: float | None
    residuo_log10: float | None
    medido_en: datetime | None
    #: El `counted` de la tabla por estación, tal cual (ver `Medida`).
    voto_contado: bool | None = None


@dataclass(frozen=True)
class Anillo:
    """Capa 2: un nivel de PGA constante, con su radio EPICENTRAL en km."""

    umbral: str
    pga_g: float
    radio_km: float
    #: Siempre `PROC_MODELADO`. Es un modelo y se pinta como modelo.
    procedencia: str = PROC_MODELADO


@dataclass(frozen=True)
class NivelFuera:
    """Un nivel que la capa 2 **no dibuja**, y por qué.

    Existe para que un umbral suprimido se DIGA en vez de desaparecer: un anillo
    que falta sin explicación se lee como «ese umbral no existía», y aquí los
    umbrales son los que este sistema usa para decidir.
    """

    umbral: str
    pga_g: float
    #: Uno de `MOTIVOS_FUERA`.
    motivo: str


@dataclass(frozen=True)
class Mapa:
    """El snapshot completo de un incidente. Inmutable y con tuplas.

    ⚠️ Tuplas y no listas, por la lección de `catalogo/consulta.py`: un `frozen`
    cuyas colecciones se rellenan con `.append()` después de construirlo es un
    congelado decorativo.
    """

    estado: str
    ley: str | None
    epicentro: Epicentro | None
    cobertura_km: float
    #: Tope del radio de un anillo VIGENTE al calcular, en km (ver el
    #: encabezado). Va en el snapshot por la misma razón que `cobertura_km`: un
    #: mapa impreso en un dictamen firmado no puede cambiar de significado
    #: porque alguien mueva el ajuste seis meses después.
    radio_max_km: float
    puntos: tuple[Punto, ...]
    anillos: tuple[Anillo, ...]
    #: Los niveles que NO se dibujaron, con su motivo. Vacío no es «no se miró»:
    #: sin capa 2 no hay niveles que declarar, y eso lo dice `ley is None`.
    fuera_de_alcance: tuple[NivelFuera, ...] = ()


def radio_epicentral_km(magnitud: float, pga_g: float, depth_km: float | None) -> float | None:
    """Radio en superficie donde ATTEN-LAW v1 predice exactamente ``pga_g``.

    Se invierte la ley (`PGA = 10**(0.5M − 2.8) / R_hipo`) y se proyecta con la
    profundidad. Devuelve ``None`` cuando ese nivel **no corta la superficie**
    (ver `resuelve_radio`, que además dice por qué). **Sin tope**: ésta es la
    geometría de la ley, y el tope es una decisión sobre hasta dónde se puede
    afirmar — la aplica `_anillos`, no la trigonometría.
    """
    return resuelve_radio(magnitud, pga_g, depth_km)[0]


def resuelve_radio(
    magnitud: float, pga_g: float, depth_km: float | None
) -> tuple[float | None, str | None]:
    """El radio epicentral del nivel, o ``None`` **con el motivo** de por qué no.

    Una sola inversión de la ley para las dos preguntas: si se despejara aquí y
    se volviera a despejar para explicar, las dos respuestas acabarían
    discrepando. Los motivos son los de `MOTIVOS_FUERA`; el tope NO se aplica
    aquí (ver `radio_epicentral_km`).
    """
    if pga_g <= 0:
        # Un nivel de 0 g o negativo no es un nivel: la ley nunca lo alcanza.
        return None, FUERA_NO_INVERTIBLE
    r_hipo = 10 ** (0.5 * magnitud - 2.8) / pga_g
    if r_hipo < PISO_DE_LA_LEY_KM:
        return None, FUERA_NO_INVERTIBLE
    prof = depth_km or 0.0
    if r_hipo <= prof:
        return None, FUERA_BAJO_LA_SUPERFICIE
    return math.sqrt(r_hipo * r_hipo - prof * prof), None


def calcula(
    medidas: list[Medida],
    *,
    epicentro: Epicentro | None,
    niveles: tuple[Nivel, ...],
    cobertura_km: float,
    radio_max_km: float,
) -> Mapa:
    """Las tres capas de un incidente. Default-deny: lo que no se puede afirmar
    sale en ``None``, nunca en cero."""
    # ⚠️ El orden importa y es la mitad de la ficha: **primero** se mira si hubo
    # alguna medida, porque sin ninguna NO se publica la capa 2 (`§A.3`: «la
    # capa 2 sola no aporta nada que no se calcule con una regla de tres»). Si
    # `modelable` no lo exigiera, un incidente sin un solo pico devolvería ley,
    # anillos y una PGA modelada por punto: un mapa de puro modelo.
    hubo_medida = any(m.pga_g is not None for m in medidas)
    modelable = hubo_medida and epicentro is not None and epicentro.modelable
    puntos = tuple(_punto(m, epicentro if modelable else None) for m in medidas)
    anillos, fuera = _anillos(epicentro, niveles, radio_max_km) if modelable else ((), ())

    if not hubo_medida:
        estado = ESTADO_SIN_DATOS
    elif modelable:
        estado = ESTADO_COMPLETO
    else:
        estado = ESTADO_SOLO_OBSERVADO

    return Mapa(
        estado=estado,
        # La ley se cita SÓLO si se aplicó. Citarla con la capa 2 vacía diría que
        # el mapa se modeló con ella cuando no se modeló con nada.
        ley=LEY if modelable else None,
        epicentro=epicentro,
        cobertura_km=cobertura_km,
        radio_max_km=radio_max_km,
        puntos=puntos,
        anillos=anillos,
        fuera_de_alcance=fuera,
    )


def _punto(m: Medida, epicentro: Epicentro | None) -> Punto:
    hipo = modelada = residuo = None
    if epicentro is not None and m.dist_km is not None and epicentro.magnitud is not None:
        hipo = hypo_km(m.dist_km, epicentro.depth_km)
        modelada = pga_law_g(epicentro.magnitud, hipo)
    # El residuo exige las DOS cifras y las dos positivas: `log10(0)` es −inf,
    # que no es un número que se pueda serializar ni pintar. Un pico medido de
    # 0 g es un hecho legítimo (el gabinete publicó y no se movió nada); lo que
    # no existe es su residuo.
    if modelada is not None and m.pga_g is not None and m.pga_g > 0 and modelada > 0:
        residuo = math.log10(m.pga_g / modelada)
    return Punto(
        site_id=m.site_id,
        site_code=m.site_code,
        site_name=m.site_name,
        lat=m.lat,
        lon=m.lon,
        procedencia=PROC_MEDIDO,
        pga_g=m.pga_g,
        pgv_cms=m.pgv_cms,
        dist_km=m.dist_km,
        hypo_km=hipo,
        pga_g_modelada=modelada,
        residuo_log10=residuo,
        medido_en=m.medido_en,
        voto_contado=m.voto_contado,
    )


def _anillos(
    epicentro: Epicentro | None, niveles: tuple[Nivel, ...], radio_max_km: float
) -> tuple[tuple[Anillo, ...], tuple[NivelFuera, ...]]:
    """Los niveles repartidos en dos: los que se dibujan y los que se DECLARAN.

    El orden de los dibujados es el de la coreografía —PGA descendente ⇒ radio
    creciente—, declarado aquí para que ningún consumidor tenga que reordenarlo
    (y para que ninguno se olvide). Los declarados salen en el mismo orden, que
    es el de los niveles por fuerza, no el del azar de un diccionario.
    """
    if epicentro is None or epicentro.magnitud is None:
        return (), ()
    salida: list[Anillo] = []
    fuera: list[NivelFuera] = []
    for nivel in sorted(niveles, key=lambda n: n.pga_g, reverse=True):
        radio, motivo = resuelve_radio(epicentro.magnitud, nivel.pga_g, epicentro.depth_km)
        if radio is not None and radio > radio_max_km:
            # Existe, pero más allá del alcance del modelo. Se dice, no se pinta.
            radio, motivo = None, FUERA_DEL_ALCANCE
        if radio is None:
            fuera.append(
                NivelFuera(
                    umbral=nivel.umbral, pga_g=nivel.pga_g, motivo=motivo or FUERA_DEL_ALCANCE
                )
            )
            continue
        salida.append(Anillo(umbral=nivel.umbral, pga_g=nivel.pga_g, radio_km=radio))
    return tuple(salida), tuple(fuera)


# --------------------------------------------------------------------------
# La forma persistida. Vive AQUÍ, en un solo sitio, porque la escribe el worker
# y la lee el endpoint: dos serializaciones del mismo hecho acaban divergiendo.
# --------------------------------------------------------------------------


def puntos_json(mapa: Mapa) -> list[dict]:
    """La capa 1+3 como JSON. Las horas en ISO-8601, que es lo que `jsonb` admite."""
    return [
        {
            "site_id": p.site_id,
            "site_code": p.site_code,
            "site_name": p.site_name,
            "lat": p.lat,
            "lon": p.lon,
            "procedencia": p.procedencia,
            "pga_g": p.pga_g,
            "pgv_cms": p.pgv_cms,
            "dist_km": p.dist_km,
            "hypo_km": p.hypo_km,
            "pga_g_modelada": p.pga_g_modelada,
            "residuo_log10": p.residuo_log10,
            "medido_en": None if p.medido_en is None else p.medido_en.isoformat(),
            "voto_contado": p.voto_contado,
        }
        for p in mapa.puntos
    ]


def anillos_json(mapa: Mapa) -> list[dict]:
    """El CENSO de los niveles de la capa 2: los dibujados y los declarados.

    Una sola lista y no dos, a propósito: quien lee la fila cruda ve de una vez
    todos los umbrales que el mapa consideró, y no puede leer los anillos sin
    enterarse de cuáles quedaron suprimidos y por qué. Las claves son uniformes
    —`radio_km` nulo ⇔ `motivo` no nulo— para que nadie tenga que adivinar la
    forma de una entrada.

    ⚠️ Sin `procedencia` y sin vértices, y las dos ausencias son a propósito. La
    geometría del círculo la materializa quien pinta —guardar 64 vértices sería
    guardar un dibujo, no un modelo—, y la procedencia de un anillo es constante
    por construcción: la pone `lectura.leer` al vestir la capa, así que no puede
    llegar equivocada desde la base.

    `radio_max_km` viaja en cada entrada porque es lo que hace CITABLE la
    supresión: «fuera del alcance» sin decir de qué alcance no es una afirmación.
    """
    dibujados = [
        {
            "umbral": a.umbral,
            "pga_g": a.pga_g,
            "radio_km": a.radio_km,
            "motivo": None,
            "radio_max_km": mapa.radio_max_km,
        }
        for a in mapa.anillos
    ]
    declarados = [
        {
            "umbral": n.umbral,
            "pga_g": n.pga_g,
            "radio_km": None,
            "motivo": n.motivo,
            "radio_max_km": mapa.radio_max_km,
        }
        for n in mapa.fuera_de_alcance
    ]
    return dibujados + declarados


def epicentro_json(mapa: Mapa) -> dict | None:
    if mapa.epicentro is None:
        return None
    e = mapa.epicentro
    return {
        "lat": e.lat,
        "lon": e.lon,
        "depth_km": e.depth_km,
        "magnitud": e.magnitud,
        "fuente": e.fuente,
        "procedencia": e.procedencia,
        "catalog_key": e.catalog_key,
    }
