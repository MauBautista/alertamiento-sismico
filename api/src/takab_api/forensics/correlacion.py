"""T-5.11 · Criterio de IDENTIDAD entre un sismo del catálogo y el que abrió el incidente.

**El problema que resuelve.** Hasta esta ficha la correlación era *solo temporal*:
se tomaba el evento del catálogo más cercano en el tiempo dentro de ±120 s y se
imprimía en un dictamen firmado bajo el rótulo «contraste con catálogo», con su
magnitud y su lugar. **No había distancia máxima, ni magnitud mínima, ni filtro
geográfico.** La distancia se calculaba *después* del acierto, solo para
describirlo, nunca para rechazar. Hoy el riesgo está acotado por accidente —trece
filas mexicanas sembradas a mano—; con el feed vivo de `T-2.149` un sismo de
Chile, Japón o Indonesia ocurrido dentro de la ventana se firmaría como nuestro.

Y faltaba lo contrario: el sistema **no tenía forma de decir «hay un evento en el
catálogo pero no es el nuestro»**. Ese es el estado ``sin_correlacion`` de
`T-5.10`, y este módulo es quien lo produce: cada candidato descartado sale con
su motivo, para que la pantalla y el papel puedan afirmarlo en vez de dejar un
hueco que el operador lee como «no pasó nada».

Módulo **puro**: no toca la base ni la red, y por eso se puede probar entero sin
Postgres. Determinista, sin IA (regla de oro 1). No decide nada operativo: la
correlación es descriptiva, jamás gatea una actuación.

--------------------------------------------------------------------------------
LOS TRES CRITERIOS, Y LA RAZÓN DE CADA UNO
--------------------------------------------------------------------------------

**1 · Ventana temporal CONSCIENTE DE LA DISTANCIA — y por qué la fija estaba mal.**
La sacudida viaja. Entre el origen del sismo y el instante en que este edificio lo
detecta pasa el tiempo de propagación, que depende de a cuántos kilómetros ocurrió.
Un ±120 s fijo no es «holgado»: es **físicamente incorrecto en los dos sentidos**.

*Se pasa de largo cerca* —a 30 km caben dos sismos distintos dentro de la ventana—
*y se queda corto lejos*, que es el fallo que muerde: el M8.2 de Chiapas (2017,
epicentro 14.85 N 94.11 W) está a **737 km** de la Ciudad de México, y su onda S
llegó unos **205 s** después del origen. Con la ventana fija de ±120 s, **el sismo
que vació la ciudad no habría casado con su propia entrada del catálogo.**

Es exactamente el hallazgo que el blueprint §4.5 ya hizo para la asociación del
quórum —«una ventana fija de 2–5 s era físicamente inalcanzable a 90–110 km»— y se
resuelve con la misma forma: ``Δ ≤ dist/v + margen``.

Aquí la ventana es además **ASIMÉTRICA**, y esa es la diferencia con el quórum:
entre estaciones el desfase puede tener cualquier signo, pero un edificio **no
puede detectar un sismo antes de que ocurra**. El límite inferior es ``-margen``
—solo tolerancia de reloj y de revisión de la hora de origen—, no la ventana
entera. Un evento del catálogo cuyo origen sea *posterior* a nuestra detección no
es el nuestro, y hasta hoy casaba porque el criterio comparaba valores absolutos.

Se usa **v_S y no v_P**: el disparo local lo produce la sacudida fuerte (onda S y
superficiales), no el primer arribo P. Con v_P la cota superior se quedaría corta
justo en los sismos lejanos y grandes, que son los que importan. En un incidente
SASMEX la detección llega **antes** que cualquier onda —viaja por telemetría—, y
por eso el borde que la admite es el inferior, que llega hasta ``-margen``.

**2 · Radio máximo epicentro↔SITIO.**
La distancia que decide es la que va del epicentro **al edificio**, no la que va
del epicentro al epicentro que estimó nuestra red. Es deliberado: en la ruta del
receptor —que es la normal, y la única que existe hoy en producción— **no hay
epicentro propio**, así que un criterio epicentro↔epicentro no se podría aplicar
donde más falta hace. El sitio siempre tiene coordenadas (``sites.geom`` es
``NOT NULL``), de modo que este criterio se puede exigir SIEMPRE.

El tope es generoso a propósito: medido desde la Ciudad de México cubre la zona
sismogénica que de verdad la sacude —Michoacán 1985 a **428 km**, Puebla-Morelos
2017 a **122 km**, Chiapas 2017 a **737 km**, y hasta Tapachula a 883 km— y
excluye de forma terminante lo que esta ficha existe para excluir: Chile está a
6 389 km y Japón a 10 945 km del mismo punto.

**3 · PGA coherente con la distancia (ATTEN-LAW v1).**
No una «magnitud mínima» plana: una magnitud mínima **que depende de la
distancia**, que es lo que la hace defendible. Un M4.0 a 30 km es perfectamente
capaz de abrir un incidente (0.0044 g estimados); el mismo M4.0 a 300 km predice
**0.0005 g** —no movió este edificio— y casarlo sería firmar una causa
imposible. La ley determinista ya existía en el sistema para pintar la
comparativa (`geo.pga_law_g`) y aquí se le da su primer uso con consecuencia.

El piso es **muy bajo a propósito, un orden de magnitud por debajo del umbral de
cautela del gabinete** (`pga_watch_g = 0.040 g`). No se pregunta «¿habría
disparado?» sino «¿pudo notarse siquiera aquí?». La diferencia no es un matiz: en
un incidente SASMEX el edificio puede no haber sentido casi nada y el evento del
catálogo **sí es** el que la alerta anunció. Un piso puesto en el umbral de
disparo rechazaría precisamente las correlaciones del camino primario.

Sin magnitud publicada el criterio **no rechaza**: «desconocida» no es
«incoherente». La fila entra si pasa los otros dos, y se marca que su coherencia
no pudo verificarse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from takab_api.geo import bearing16, haversine_km, hypo_km, pga_law_g

#: Motivos de descarte. Son el vocabulario cerrado que la pantalla y el papel
#: citan para decir «hay un evento en el catálogo pero no es el nuestro».
FUERA_DE_VENTANA = "fuera_de_ventana"
ANTERIOR_A_SU_ORIGEN = "anterior_a_su_origen"
FUERA_DE_RADIO = "fuera_de_radio"
MAGNITUD_INCOHERENTE = "magnitud_incoherente"
SIN_EPICENTRO_EN_EL_CATALOGO = "sin_epicentro_en_el_catalogo"
SITIO_SIN_COORDENADAS = "sitio_sin_coordenadas"

MOTIVOS: dict[str, str] = {
    FUERA_DE_VENTANA: "el origen es demasiado antiguo para la distancia a la que ocurrió",
    ANTERIOR_A_SU_ORIGEN: "se habría detectado antes de que el sismo ocurriera",
    FUERA_DE_RADIO: "el epicentro está fuera del radio máximo al sitio",
    MAGNITUD_INCOHERENTE: "a esa distancia su magnitud no pudo sacudir este edificio",
    SIN_EPICENTRO_EN_EL_CATALOGO: "la fila del catálogo no trae epicentro que comparar",
    SITIO_SIN_COORDENADAS: "el sitio no tiene coordenadas con las que verificar la identidad",
}

#: Cómo se presenta un acierto. `contrastado` = hay epicentro propio y el delta es
#: un contraste de verdad. `no_verificable` = la identidad se estableció (ventana +
#: radio + coherencia) pero **no hay nada nuestro que contrastar**, y decirlo
#: «contraste» sería prometer una verificación que no ocurrió.
CONTRASTADO = "contrastado"
NO_VERIFICABLE = "no_verificable"


@dataclass(frozen=True)
class Criterio:
    """Los tres umbrales, con sus unidades. Se construye de ``Settings``."""

    v_s_km_s: float
    margen_s: float
    radio_km: float
    pga_minima_g: float

    @property
    def retraso_maximo_s(self) -> float:
        """Cota dura del retraso: la del evento más lejano admisible.

        Es lo que acota la consulta a la base — más allá de esto ninguna fila
        puede pasar el criterio, así que no hace falta traerla.
        """
        return self.radio_km / self.v_s_km_s + self.margen_s

    def retraso_admisible_s(self, epi_km: float) -> float:
        """Retraso máximo tolerado para un epicentro a ``epi_km`` del sitio."""
        return epi_km / self.v_s_km_s + self.margen_s


@dataclass(frozen=True)
class Candidato:
    """Fila del catálogo tal como llega de la base, sin interpretar."""

    catalog_key: str
    origin_time: datetime
    magnitude: float | None
    lat: float | None
    lon: float | None
    depth_km: float | None


@dataclass(frozen=True)
class Veredicto:
    """Resultado de evaluar UN candidato. ``casa`` o ``motivo``, nunca ambos."""

    catalog_key: str
    casa: bool
    motivo: str | None = None
    #: Distancia epicentro↔sitio (km). ``None`` solo si falta alguna coordenada.
    km_al_sitio: float | None = None
    #: Rumbo del sitio hacia el epicentro, en la rosa de 16.
    rumbo_al_sitio: str | None = None
    #: Retraso medido, con signo: detección − origen. Negativo = imposible.
    retraso_s: float | None = None
    #: Cota que se le aplicó a ese retraso, para poder leer el rechazo.
    retraso_admisible_s: float | None = None
    #: PGA que la ley ATTEN-LAW v1 predice en el sitio. ``None`` sin magnitud.
    pga_esperada_g: float | None = None

    @property
    def detalle(self) -> str:
        """Una línea legible del rechazo, con el número que lo motivó."""
        if self.casa:
            return ""
        base = MOTIVOS.get(self.motivo or "", self.motivo or "")
        if self.motivo == FUERA_DE_RADIO and self.km_al_sitio is not None:
            return f"{base} ({self.km_al_sitio:.0f} km)"
        if self.motivo in (FUERA_DE_VENTANA, ANTERIOR_A_SU_ORIGEN) and self.retraso_s is not None:
            return f"{base} (Δt {self.retraso_s:+.0f} s)"
        if self.motivo == MAGNITUD_INCOHERENTE and self.pga_esperada_g is not None:
            return f"{base} ({self.pga_esperada_g:.2}g esperados)"
        return base


@dataclass(frozen=True)
class Resultado:
    """Lo que produjo el criterio: el acierto si lo hubo, y todo lo descartado."""

    criterio: Criterio
    acierto: Veredicto | None = None
    descartes: tuple[Veredicto, ...] = field(default_factory=tuple)

    @property
    def hubo_candidatos(self) -> bool:
        """¿Había algo en la ventana? Distingue «no es el nuestro» de «no hay nada»."""
        return self.acierto is not None or bool(self.descartes)


def evalua(
    cand: Candidato,
    *,
    detectado_en: datetime,
    sitio_lat: float | None,
    sitio_lon: float | None,
    criterio: Criterio,
) -> Veredicto:
    """Aplica los tres criterios a un candidato. Default-deny: la duda no casa."""
    retraso = (detectado_en - cand.origin_time).total_seconds()

    if sitio_lat is None or sitio_lon is None:
        return Veredicto(cand.catalog_key, False, SITIO_SIN_COORDENADAS, retraso_s=retraso)
    if cand.lat is None or cand.lon is None:
        return Veredicto(cand.catalog_key, False, SIN_EPICENTRO_EN_EL_CATALOGO, retraso_s=retraso)

    km = haversine_km(sitio_lat, sitio_lon, cand.lat, cand.lon)
    rumbo = bearing16(sitio_lat, sitio_lon, cand.lat, cand.lon)
    tope = criterio.retraso_admisible_s(km)
    pga = (
        pga_law_g(cand.magnitude, hypo_km(km, cand.depth_km))
        if cand.magnitude is not None
        else None
    )
    hechos = dict(
        km_al_sitio=km,
        rumbo_al_sitio=rumbo,
        retraso_s=retraso,
        retraso_admisible_s=tope,
        pga_esperada_g=pga,
    )

    # Radio primero: es el criterio que esta ficha existe para introducir, y el que
    # de forma más terminante separa «un sismo de otro continente» de «el nuestro».
    if km > criterio.radio_km:
        return Veredicto(cand.catalog_key, False, FUERA_DE_RADIO, **hechos)
    # Un origen POSTERIOR a la detección no es tolerancia de reloj: es imposible.
    if retraso < -criterio.margen_s:
        return Veredicto(cand.catalog_key, False, ANTERIOR_A_SU_ORIGEN, **hechos)
    if retraso > tope:
        return Veredicto(cand.catalog_key, False, FUERA_DE_VENTANA, **hechos)
    # Sin magnitud NO se rechaza: «desconocida» no es «incoherente».
    if pga is not None and pga < criterio.pga_minima_g:
        return Veredicto(cand.catalog_key, False, MAGNITUD_INCOHERENTE, **hechos)
    return Veredicto(cand.catalog_key, True, **hechos)


def correlaciona(
    candidatos: list[Candidato],
    *,
    detectado_en: datetime,
    sitio_lat: float | None,
    sitio_lon: float | None,
    criterio: Criterio,
) -> Resultado:
    """Elige el evento del catálogo que ES el nuestro, o declara que no lo hay.

    Se evalúan TODOS los candidatos —no solo el más cercano en el tiempo— porque
    el más cercano puede ser precisamente el intruso: el sismo de otro continente
    dentro de la ventana. Gana el que pasa el criterio y queda más cerca en el
    tiempo; los demás salen en ``descartes`` con su motivo, para poder afirmar
    «hay un evento en el catálogo pero no es el nuestro».
    """
    veredictos = [
        evalua(
            c,
            detectado_en=detectado_en,
            sitio_lat=sitio_lat,
            sitio_lon=sitio_lon,
            criterio=criterio,
        )
        for c in candidatos
    ]
    aciertos = [v for v in veredictos if v.casa]
    ganador = min(aciertos, key=lambda v: abs(v.retraso_s or 0.0)) if aciertos else None
    return Resultado(
        criterio=criterio,
        acierto=ganador,
        descartes=tuple(v for v in veredictos if v is not ganador and not v.casa),
    )
