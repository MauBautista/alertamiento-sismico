"""[T-7.24] La sección del mapa de la sacudida, comprobada SOBRE EL DOCUMENTO.

Lo que esta suite defiende no es que la figura salga bonita: es que **el papel no
presente un modelo como si fuera una medición**. Ésa es la afirmación que
`DIF-shakemap.a` sostenía en negativo —«la consola no promete una escala de
intensidad que no existe»— mientras no había mapa; con el mapa construido, la
afirmación correcta es positiva y hay que comprobarla en las dos superficies que
lo pintan. Ésta es la del papel (`RO-7.f`); la de la consola vive en
`web/src/features/console/MapPanel.test.tsx` (`RO-7.g`).

## Las dos cosas que se miden, y por qué ninguna sobra

**(a) Qué DICE el papel.** Por el espía del render troceado por sección: que la
leyenda de procedencia esté ANTES de la figura, que cada estado del mapa —
pendiente, sin datos, degradado, sin geometría— salga con su frase propia, y que
ninguna de ellas se cuele donde significa lo contrario.

**(b) Qué MIDE la figura.** Ésta es la lección que costó la guarda que se
sustituye: había dos capas de MapLibre con `circle-radius` de 55 y 100 **píxeles
de pantalla** rotuladas «INTENSIDAD MMI», así que el mismo anillo afirmaba ~22 km
a zoom 8.5 y ~1 km a zoom 13. Un texto correcto encima de una figura cuyo radio
no significa kilómetros sigue siendo una mentira, así que el radio DIBUJADO se
comprueba contra la barra de escala del propio croquis.

**(c) Qué AFIRMA la figura, y si la tabla dice lo mismo.** Es lo que faltaba
entero hasta la 2ª vuelta de `T-7.24`, y era justo la mitad de `RO-7.f`. Medido el
2026-09-21 con tres mutaciones dirigidas, las tres en VERDE sobre la suite
anterior: pintar la capa modelada como un disco negro relleno —exactamente igual
que una medición— con la leyenda prometiendo un anillo discontinuo; intercambiar
las celdas `MEDIDO (g)` y `MODELO (g)`, o sea imprimir la predicción bajo el
rótulo de la medición; y desligar el radio de los anillos de la escala del
croquis, porque la única guarda medía la RAZÓN entre dos anillos, que es
invariante ante cualquier factor de escala. Lo que se mide ahora es la
**codificación** (relleno y trazo discontinuo), la **posición** de cada celda bajo
su columna, y el radio contra la barra — no contra el otro anillo.
"""

from __future__ import annotations

import asyncio
import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

import fpdf
import pytest

from takab_api.dictamen import pdf as pdf_mod
from takab_api.dictamen.builder import bloque_de_shakemap
from takab_api.dictamen.model import (
    LEYENDA_ANILLO,
    LEYENDA_CRUZ,
    LEYENDA_DISCO,
    LEYENDA_SIN_DATO,
    MODELO_Y_RESIDUO,
    NO_MMI,
    SHAKEMAP_DEGRADADO,
    SHAKEMAP_LEYENDA,
    SHAKEMAP_PENDIENTE,
    SHAKEMAP_SIN_ANILLOS,
    SHAKEMAP_SIN_COBERTURA,
    SHAKEMAP_SIN_DATOS,
    SHAKEMAP_SIN_GEOMETRIA,
    AnilloFila,
    SacudidaFila,
    ShakemapBlock,
)
from takab_api.dictamen.pdf import MAPA_SACUDIDA, render
from takab_api.shakemap import calculo as shk
from takab_api.shakemap.lectura import leer
from tests.dictamen.test_pdf import model
from tests.documentos.espia import espia_del_render

# ⚠️ Las cifras del sismo de referencia se IMPORTAN de la suite del cálculo, no
# se copian: son la solución USGS del Puebla-Morelos 2017 con su procedencia
# (`tests/shakemap/test_calculo.py`), y una segunda copia aquí acabaría midiendo
# otro sismo que el de allí sin que nadie se entere.
from tests.shakemap.test_calculo import (  # noqa: E402 - va detrás de los imports del paquete
    EPICENTRO as EPICENTRO_REF,
)
from tests.shakemap.test_calculo import (
    NIVELES as NIVELES_REF,
)
from tests.shakemap.test_calculo import (
    TOPE_KM as TOPE_REF,
)
from tests.shakemap.test_calculo import (
    _medida as _medida_ref,
)

_CALCULADO = datetime(2026, 8, 3, 10, 5, 0, tzinfo=UTC)

#: Radios del modelo, elegidos con una razón NO redonda (2.5) y lejos de los
#: milímetros del marcador del inmueble propio: si alguien dibujara los anillos con un radio
#: fijo de página, la razón entre los dos círculos se iría a 1 y se vería.
_R_CERCA_KM = 40.0
_R_LEJOS_KM = 100.0


def _puntos() -> list[SacudidaFila]:
    """Dos inmuebles que midieron: el del dictamen y un testigo lejano.

    El residuo del propio es POSITIVO y el del testigo NEGATIVO a propósito: el
    signo es lo que informa —sacudió más o menos de lo previsible a esa
    distancia— y un papel que perdiera el signo por el camino diría lo contrario.
    """
    return [
        SacudidaFila(
            site_code="CHL-A",
            site_name="Planta Cholula",
            lat=19.06,
            lon=-98.30,
            pga_g=0.081,
            pgv_cms=3.2,
            dist_km=187.0,
            pga_g_modelada=0.041,
            residuo_log10=0.31,
            propio=True,
        ),
        SacudidaFila(
            site_code="CDMX-1",
            site_name="Torre CDMX",
            lat=19.43,
            lon=-99.13,
            pga_g=0.012,
            pgv_cms=0.6,
            dist_km=112.0,
            pga_g_modelada=0.068,
            residuo_log10=-0.753,
        ),
    ]


def _completo(**over) -> ShakemapBlock:
    base = {
        "estado": "completo",
        "ley": "ATTEN-LAW v1",
        "calculado_en": _CALCULADO,
        "cobertura_km": 25.0,
        "epicentro_lat": 16.80,
        "epicentro_lon": -99.50,
        "epicentro_magnitud": 7.1,
        "epicentro_fuente": "SSN",
        "epicentro_procedencia": "confirmado",
        "puntos": _puntos(),
        "anillos": [
            AnilloFila(pga_g=0.070, radio_km=_R_CERCA_KM, umbral="pga_watch_g"),
            AnilloFila(pga_g=0.020, radio_km=_R_LEJOS_KM, umbral="correlacion_min_pga_g"),
        ],
    }
    return ShakemapBlock(**{**base, **over})


def _capturado(bloque: ShakemapBlock, variante: str = "technical"):
    with espia_del_render() as cap:
        render(model(shakemap=bloque), variante)
    return cap


def _seccion(bloque: ShakemapBlock) -> str:
    return _capturado(bloque).seccion(MAPA_SACUDIDA)


# ───────────────────────────────────────────── (a) lo que el papel DICE


def test_el_mapa_de_la_sacudida_es_una_seccion_del_PERICIAL() -> None:
    """Y sólo del pericial: el ejecutivo son cuatro preguntas, no una figura."""
    assert _capturado(_completo()).emitio(MAPA_SACUDIDA)
    assert not _capturado(_completo(), "executive").emitio(MAPA_SACUDIDA)


def test_la_leyenda_de_PROCEDENCIA_sale_en_esa_seccion_y_no_en_otra() -> None:
    """El invariante de `D-08 · §A.3` escrito en el papel.

    Va DENTRO de la sección del mapa porque condiciona lo que se lee debajo: un
    anillo y un disco en la misma figura, sin esta frase, se leen como dos
    medidas de lo mismo.
    """
    seccion = _seccion(_completo())
    assert SHAKEMAP_LEYENDA in seccion
    assert SHAKEMAP_SIN_COBERTURA in seccion


def test_la_tabla_lleva_MEDIDO_MODELADO_y_RESIDUO_con_su_signo() -> None:
    """El residuo es el producto de la ficha, no un adorno.

    Un punto que sacude el triple de lo que la ley predice para su distancia es
    lo único que el modelo no sabía; sin el signo, «0.295» y «-0.753» dicen lo
    mismo y no dicen nada.
    """
    seccion = _seccion(_completo())
    assert "MEDIDO" in seccion
    assert "MODELO" in seccion
    assert "RESIDUO" in seccion
    assert "0.081" in seccion, "no salió la PGA medida del inmueble"
    assert "0.041" in seccion, "no salió la PGA que el modelo predice ahí"
    assert "+0.31" in seccion, "el residuo positivo perdió su signo"
    assert "-0.75" in seccion, "el residuo negativo no llegó al papel"


def test_los_NIVELES_del_modelo_van_como_TEXTO_ademas_de_sobre_la_figura() -> None:
    """Un rótulo tapado es un dato perdido, y el papel no resuelve colisiones.

    El escenario que lo justifica está COMITEADO —
    `test_el_rotulo_del_ANILLO_y_la_etiqueta_de_un_INMUEBLE_se_pisan`, aquí
    abajo— y no descrito de memoria: dos anillos y un tercer inmueble a 100 km al
    norte del epicentro, o sea encima del anillo de ese nivel. Medido el
    2026-09-21 sobre las cajas de texto del render (espía de `cell`, sin
    rasterizar): «0.020 g · 100 km» ocupa 24 × 3 mm desde x = 94.64 y «NORTE-1»
    ocupa 28 × 3 mm desde x = 109.14, 1.40 mm más abajo; se pisan en 9.50 × 1.60
    mm. La figura sigue rotulando el anillo —es donde se lee de un vistazo cuál es
    cuál— pero el número vive además en una línea que nada puede pisar.
    """
    seccion = _seccion(_completo())
    assert "NIVELES DEL MODELO" in seccion
    assert f"{_R_CERCA_KM:g} km" in seccion
    assert f"{_R_LEJOS_KM:g} km" in seccion


@dataclass(frozen=True)
class CajaDeTexto:
    """Una celda del render, con la caja que RESERVA, en mm desde el borde de la hoja."""

    x: float
    y: float
    ancho: float
    alto: float
    texto: str

    def pisa(self, otra: CajaDeTexto) -> tuple[float, float]:
        """Cuánto se solapan las dos cajas, en mm. `(0.0, 0.0)` = no se tocan."""
        ancho = min(self.x + self.ancho, otra.x + otra.ancho) - max(self.x, otra.x)
        alto = min(self.y + self.alto, otra.y + otra.alto) - max(self.y, otra.y)
        return (max(0.0, ancho), max(0.0, alto))


def _cajas_de_texto_de_la_figura(bloque: ShakemapBlock) -> list[CajaDeTexto]:
    """Las celdas impresas DENTRO del recuadro de la figura, con su caja.

    Se espía `cell` en vez de raspar el PDF porque lo que se pisa no es el glifo:
    es la caja que el render RESERVA para cada rótulo, y ésa no viaja al texto
    extraído. Mismo molde que `_figura_espiada`: el interruptor lo abre y lo
    cierra `_mapa_de_la_sacudida`, así que la cabecera y la tabla no entran.
    """
    cajas: list[CajaDeTexto] = []
    dentro = False
    original_cell = fpdf.FPDF.cell
    original_mapa = pdf_mod._mapa_de_la_sacudida

    def espia(self, *a, **k):  # noqa: ANN001, ANN002, ANN003, ANN202
        if dentro:
            ancho = a[0] if a else k.get("w", 0.0)
            alto = a[1] if len(a) > 1 else k.get("h", 0.0)
            texto = a[2] if len(a) > 2 else k.get("text", k.get("txt", ""))
            cajas.append(
                CajaDeTexto(
                    float(self.get_x()), float(self.get_y()), float(ancho), float(alto), str(texto)
                )
            )
        return original_cell(self, *a, **k)

    def marca(pdf, b, dibujo):  # noqa: ANN001, ANN202
        nonlocal dentro
        dentro = True
        try:
            return original_mapa(pdf, b, dibujo)
        finally:
            dentro = False

    fpdf.FPDF.cell = espia  # type: ignore[method-assign]
    pdf_mod._mapa_de_la_sacudida = marca  # type: ignore[assignment]
    try:
        render(model(shakemap=bloque), "technical")
    finally:
        fpdf.FPDF.cell = original_cell  # type: ignore[method-assign]
        pdf_mod._mapa_de_la_sacudida = original_mapa  # type: ignore[assignment]
    return cajas


def _sobre_el_anillo_lejano(b: ShakemapBlock) -> SacudidaFila:
    """Un inmueble a `_R_LEJOS_KM` al NORTE del epicentro: encima de ese anillo.

    El desplazamiento se DERIVA de la misma constante con la que la figura
    proyecta (`pdf._KM_POR_GRADO`) en vez de teclear una latitud: si cambiara el
    radio de la Tierra del croquis, este inmueble seguiría estando donde esta
    prueba dice que está, que es lo único que hace reproducible la colisión.
    """
    return SacudidaFila(
        site_code="NORTE-1",
        site_name="Nave Norte",
        lat=b.epicentro_lat + _R_LEJOS_KM / pdf_mod._KM_POR_GRADO,
        lon=b.epicentro_lon,
        pga_g=0.019,
        pgv_cms=0.5,
        dist_km=_R_LEJOS_KM,
        pga_g_modelada=0.020,
        residuo_log10=-0.02,
    )


def test_el_rotulo_del_ANILLO_y_la_etiqueta_de_un_INMUEBLE_se_pisan() -> None:
    """El escenario que justifica la línea de arriba, COMITEADO y no contado.

    La razón por la que los niveles van también como texto era prosa con dos
    cajas citadas de memoria, y el escenario del que salían no existía en el
    repositorio: no había ninguna fixture con tres inmuebles ni con `NORTE-1`, así
    que la medición no se podía recuperar sin rehacerla a mano. Y dos de sus seis
    cifras —las `y`— no se reproducían en este árbol, porque la `y` de la figura
    depende de dónde caiga la §8 en la página.

    Aquí se monta el caso y se vuelve a medir. Medido el 2026-09-21: «0.020 g ·
    100 km» reserva 24 × 3 mm desde x = 94.64 y «NORTE-1» reserva 28 × 3 mm desde
    x = 109.14, 1.40 mm más abajo; se pisan en 9.50 × 1.60 mm. Lo que se fija es
    lo REPRODUCIBLE —las x, los tamaños, el Δy y el solape—; la `y` absoluta no,
    porque no dice nada del rótulo y cambiaría con cualquier párrafo de más.

    El papel no tiene motor de etiquetado: el rótulo del anillo se coloca respecto
    del CENTRO del anillo y el del inmueble respecto de SU punto, y ninguno de los
    dos mira al otro. Mientras esto sea cierto, el número tiene que vivir además
    donde nada lo pise.
    """
    base = _completo()
    con_testigo = _completo(puntos=[*_puntos(), _sobre_el_anillo_lejano(base)])
    cajas = _cajas_de_texto_de_la_figura(con_testigo)

    rotulo = next(c for c in cajas if "0.020" in c.texto and f"{_R_LEJOS_KM:g} km" in c.texto)
    etiqueta = next(c for c in cajas if c.texto == "NORTE-1")

    # Primero el HECHO que sostiene el argumento, y después las cifras citadas: si
    # se comprobaran al revés, un rótulo que dejara de pisar al otro se reportaría
    # como «un número cambió» en vez de como lo que es.
    solape = rotulo.pisa(etiqueta)
    assert solape[0] > 0 and solape[1] > 0, (
        f"el rótulo del anillo y la etiqueta del inmueble ya no se pisan ({rotulo} vs "
        f"{etiqueta}): el comentario de `pdf._shakemap_section` cita esta colisión como "
        "la razón de imprimir los niveles también como texto, así que o se re-mide o "
        "se quita — una cifra con procedencia falsa es peor que ninguna cifra"
    )

    assert (rotulo.ancho, rotulo.alto) == (24, 3)
    assert (etiqueta.ancho, etiqueta.alto) == (28, 3)
    assert rotulo.x == pytest.approx(94.64, abs=0.01)
    assert etiqueta.x == pytest.approx(109.14, abs=0.01)
    assert etiqueta.y - rotulo.y == pytest.approx(1.40, abs=0.01)
    assert solape == pytest.approx((9.50, 1.60), abs=0.01)


def test_sin_anillos_no_se_anuncian_NIVELES_de_un_modelo_que_no_hay() -> None:
    """El lado negativo: un encabezado sin nada debajo promete un dato."""
    degradado = _completo(
        estado="solo_observado",
        ley=None,
        epicentro_lat=None,
        epicentro_lon=None,
        epicentro_magnitud=None,
        anillos=[],
    )
    assert "NIVELES DEL MODELO" not in _seccion(degradado)


def test_el_radio_de_COBERTURA_se_imprime_con_su_numero() -> None:
    """`SIN COBERTURA` sin el radio es una palabra: con él es verificable."""
    assert "25" in _seccion(_completo())


def test_la_LEY_y_el_instante_del_calculo_van_en_el_papel() -> None:
    """Un mapa viejo tiene que decir con qué ley se hizo, no con la de hoy.

    Y cuándo se calculó: es lo que dice con qué información se hizo. Un dictamen
    regenerado el año que viene sobre el mismo incidente puede traer otro mapa
    porque llegó el catálogo, y sin la fecha nadie puede saber cuál es cuál.
    """
    seccion = _seccion(_completo())
    assert "ATTEN-LAW v1" in seccion
    assert "2026-08-03" in seccion


def test_el_epicentro_del_mapa_va_con_su_FUENTE_y_su_procedencia() -> None:
    """El centroide de nuestro propio cuórum es un epicentro NUESTRO.

    Presentarlo sin decirlo lo confundiría con la solución de una agencia, que es
    el mismo defecto que `EPICENTRO_REUBICADO` cazó en la §1.
    """
    seccion = _seccion(_completo())
    assert "SSN" in seccion
    assert "confirmado" in seccion
    assert "7.1" in seccion


@pytest.mark.parametrize(
    "bloque,esperado,prohibidos",
    [
        pytest.param(
            ShakemapBlock(),
            SHAKEMAP_PENDIENTE,
            (SHAKEMAP_SIN_DATOS, SHAKEMAP_DEGRADADO, SHAKEMAP_LEYENDA),
            id="pendiente",
        ),
        pytest.param(
            ShakemapBlock(estado="sin_datos", calculado_en=_CALCULADO, cobertura_km=25.0),
            SHAKEMAP_SIN_DATOS,
            (SHAKEMAP_PENDIENTE, SHAKEMAP_DEGRADADO, SHAKEMAP_LEYENDA),
            id="sin_datos",
        ),
        pytest.param(
            ShakemapBlock(
                estado="solo_observado",
                calculado_en=_CALCULADO,
                cobertura_km=25.0,
                puntos=[
                    SacudidaFila(
                        site_code="CHL-A",
                        site_name="Planta Cholula",
                        lat=19.06,
                        lon=-98.30,
                        pga_g=0.081,
                        pgv_cms=3.2,
                        dist_km=None,
                        pga_g_modelada=None,
                        residuo_log10=None,
                        propio=True,
                    )
                ],
            ),
            SHAKEMAP_DEGRADADO,
            (SHAKEMAP_PENDIENTE, SHAKEMAP_SIN_DATOS),
            id="solo_observado",
        ),
    ],
)
def test_cada_estado_del_mapa_dice_LO_SUYO_y_no_lo_del_vecino(
    bloque: ShakemapBlock, esperado: str, prohibidos: tuple[str, ...]
) -> None:
    """Los cuatro estados significan cosas distintas y se leerían igual con un hueco.

    «Todavía no se ha calculado», «se calculó y nadie midió» y «se midió y no hay
    con qué compararlo» son tres hechos diferentes sobre el incidente. Dos avisos
    a la vez dejarían al lector sin saber cuál creer — la misma regla que los tres
    estados del CCTV.
    """
    seccion = _seccion(bloque)
    assert esperado in seccion
    for otro in prohibidos:
        assert otro not in seccion, "dos avisos que se contradicen en la misma sección"


def test_sin_coordenadas_se_declara_y_la_TABLA_sigue() -> None:
    """La ausencia de la figura no se lleva por delante los números.

    Mismo criterio que `SIN_GEOMETRIA_DE_RED` en la §7: un marco vacío parece un
    fallo de impresión y se lee como «no hay inmuebles», que es lo contrario de lo
    que dice la tabla de debajo.
    """
    ciego = _completo(
        puntos=[
            SacudidaFila(
                site_code="CHL-A",
                site_name="Planta Cholula",
                lat=None,
                lon=None,
                pga_g=0.081,
                pgv_cms=3.2,
                dist_km=187.0,
                pga_g_modelada=0.041,
                residuo_log10=0.31,
                propio=True,
            )
        ],
        epicentro_lat=None,
        epicentro_lon=None,
    )
    seccion = _seccion(ciego)
    assert SHAKEMAP_SIN_GEOMETRIA in seccion
    assert "0.081" in seccion, "la tabla se fue con la figura"


def test_con_geometria_NO_sale_el_aviso_de_que_falta() -> None:
    """El lado negativo: un aviso que sale siempre enseña a ignorar el aviso."""
    assert SHAKEMAP_SIN_GEOMETRIA not in _seccion(_completo())


def test_un_snapshot_COMPLETO_sin_medidas_no_imprime_una_tabla_vacia() -> None:
    """El caso incoherente, que es el que deja un rótulo prometiendo un dato.

    `completo` significa, por definición del cálculo, epicentro y magnitud citados
    **y al menos un inmueble que midió**. Un snapshot que dijera lo primero sin lo
    segundo dibujaría una tabla con sólo cabecera — y una cabecera sin filas no es
    un vacío, es una promesa. El papel dice lo único verificable: no hay medidas.
    """
    seccion = _seccion(_completo(puntos=[]))
    assert SHAKEMAP_SIN_DATOS in seccion
    assert "RESIDUO" not in seccion, "la tabla salió con cabecera y sin una sola fila"


def test_el_papel_ya_no_anuncia_como_DIFERIDO_el_mapa_que_imprime() -> None:
    """`NO_MMI` decía «el cálculo está DIFERIDO y su ficha es T-7.24».

    Esta ficha ES T-7.24. Un documento firmado que anuncia como aplazado algo que
    imprime dos secciones más abajo se desmiente a sí mismo, que es la familia de
    defectos que costó `T-7.34`, `T-7.38` y `T-7.39`.

    Lo que NO cambia, y por eso se comprueba en el mismo test: que se sigue sin
    reportar intensidad macrosísmica ni isosistas. Eso está impreso en documentos
    ya firmados y sigue siendo verdad.
    """
    texto = _capturado(_completo()).texto
    assert NO_MMI in texto
    assert "DIFERIDO" not in texto.upper(), "el papel sigue anunciando algo como diferido"
    assert "isosistas" in NO_MMI
    assert "MMI" in NO_MMI


# ─────────────────────────────────────────── (b) lo que la figura MIDE


def _radios_dibujados(bloque: ShakemapBlock) -> list[float]:
    """Sólo los radios, en mm de página, de los círculos de esta figura.

    Se apoya en `_circulos_dibujados` y no espía por su cuenta: eran dos espías
    casi idénticos sobre `fpdf.FPDF.circle`, y de los dos **sólo uno acotaba a la
    figura** — que es la forma en que un espía copiado se queda atrás. Ver allí
    por qué el estilo y el patrón de trazo no se pueden tirar.
    """
    return [c.radio_mm for c in _circulos_dibujados(bloque)]


def test_los_anillos_del_modelo_miden_KILOMETROS_no_pixeles_de_pagina() -> None:
    """**La lección que costó la guarda que esta ficha sustituye.**

    Dos anillos cuyos radios físicos están en razón 100/40 = 2.5 tienen que salir
    dibujados en esa misma razón. Si alguien los pintara con un radio constante de
    página —que es exactamente lo que hacían las capas `mmi-severa`/`mmi-alta` con
    `circle-radius` en píxeles— la razón se iría a 1 y el papel afirmaría que el
    modelo predice lo mismo a 40 y a 100 km.

    ⚠️ **Y esto es todo lo que esta prueba mide.** Una razón es invariante ante
    cualquier factor de escala global: con `mm_por_km` fijado a una constante de
    página los dos anillos siguen en razón 2.5 y esto sigue verde. Lo que ata el
    radio a los kilómetros es
    `test_el_radio_dibujado_se_mide_con_la_BARRA_DE_ESCALA_del_propio_croquis`.
    """
    radios = [r for r in _radios_dibujados(_completo()) if r > pdf_mod.MARCA_PROPIA_MM]
    assert len(radios) == 2, f"se esperaban los dos anillos del modelo, se dibujaron {radios}"
    grande, pequeno = max(radios), min(radios)
    assert pequeno > 0
    assert grande / pequeno == pytest.approx(_R_LEJOS_KM / _R_CERCA_KM, rel=1e-6), (
        "los dos anillos NO están en la razón de sus radios físicos: el radio dibujado "
        "no significa kilómetros"
    )


def test_sin_capa_modelada_no_se_dibuja_ni_un_anillo() -> None:
    """Degradado es degradado: sin epicentro y magnitud no hay modelo que pintar.

    El lado que de verdad importa del `SHAKEMAP_DEGRADADO`: decirlo y dibujarlo
    igual sería peor que no decirlo, porque el lector creería al dibujo.
    """
    degradado = _completo(
        estado="solo_observado",
        ley=None,
        epicentro_lat=None,
        epicentro_lon=None,
        epicentro_magnitud=None,
        anillos=[],
    )
    radios = [r for r in _radios_dibujados(degradado) if r > pdf_mod.MARCA_PROPIA_MM]
    assert radios == [], f"se dibujaron anillos de un modelo que no existe: {radios}"


def test_el_espia_de_circulos_NO_esta_ciego() -> None:
    """Guarda de no-vacuidad: si `circle` dejara de ser por donde pasan los anillos,
    los dos tests de arriba pasarían por vacuidad — uno exige `== []`."""
    assert len(_radios_dibujados(_completo())) > 2, (
        "el espía no vio ni los marcadores de estación: `circle` ya no es el punto "
        "por el que se dibujan los círculos del documento"
    )


# ─────────────────── (c) lo que la figura AFIRMA, y si la tabla lo confirma


@dataclass(frozen=True)
class Circulo:
    """Un círculo tal y como llegó al PDF, con su CODIFICACIÓN.

    ⚠️ `estilo` y `discontinuo` son la mitad que faltaba: el espía anterior
    recibía `style` como parámetro y lo tiraba (`vistos.append(float(radius))`),
    así que pintar la capa modelada como disco negro relleno dejaba las 460
    pruebas en verde mientras la leyenda impresa encima seguía diciendo «ANILLO
    DISCONTINUO … es un modelo, no una medición, y por eso se dibuja distinto».
    """

    x: float
    y: float
    radio_mm: float
    estilo: str
    #: ¿Se dibujó con patrón de guiones activo? Es la forma que separa el modelo
    #: de la medida, y no se puede leer del `style`: vive en el estado del PDF.
    discontinuo: bool

    @property
    def relleno(self) -> bool:
        return "F" in self.estilo


def _circulos_dibujados(bloque: ShakemapBlock) -> list[Circulo]:
    """Los círculos que dibujó **la figura del mapa de la sacudida**, y sólo ella.

    Se espía `fpdf.FPDF.circle` y no un ayudante nuestro: lo que hay que vigilar
    es lo que llega al documento. Un cálculo correcto que no se usara al dibujar
    pasaría cualquier prueba sobre la función pura.

    ⚠️ **Y se acota a la llamada de esta figura.** El dictamen dibuja círculos en
    más sitios —el mapa de la red de la §7 usa uno por estación— y medidos el
    2026-09-21 se colaban cuatro marcadores donde la figura sólo pinta dos. Una
    prueba que cuente marcadores de otra sección no mide lo que dice medir, y el
    día que la §7 cambie se pondría roja por el sitio equivocado.
    """
    return _figura_espiada(bloque)[1]


def _figura_espiada(bloque: ShakemapBlock):
    """`(marco, círculos)` de la figura del mapa: su recuadro y lo que dibujó dentro.

    El marco es el PRIMER `rect` que emite `_mapa_de_la_sacudida`, que es el que la
    enmarca. Hace falta para poder comprobar que nada se sale de él — y nada lo
    comprobaba: `rect`/`circle` no recortan en PDF, así que un círculo mayor que su
    caja se pinta sobre el resto del documento.
    """
    vistos: list[Circulo] = []
    marcos: list[tuple[float, float, float, float]] = []
    dentro = False
    original = fpdf.FPDF.circle
    original_rect = fpdf.FPDF.rect
    original_mapa = pdf_mod._mapa_de_la_sacudida

    def espia(self, x, y, radius, style=None):  # noqa: ANN001, ANN202
        if dentro:
            patron = getattr(self, "dash_pattern", None) or {}
            vistos.append(
                Circulo(
                    x=float(x),
                    y=float(y),
                    radio_mm=float(radius),
                    estilo="" if style is None else str(style),
                    discontinuo=float(patron.get("dash") or 0.0) > 0,
                )
            )
        return original(self, x, y, radius, style)

    def espia_rect(self, x, y, w, h, *a, **k):  # noqa: ANN001, ANN202
        if dentro and not marcos:
            marcos.append((float(x), float(y), float(w), float(h)))
        return original_rect(self, x, y, w, h, *a, **k)

    def marca(pdf, b, dibujo):  # noqa: ANN001, ANN202
        nonlocal dentro
        dentro = True
        try:
            return original_mapa(pdf, b, dibujo)
        finally:
            dentro = False

    fpdf.FPDF.circle = espia  # type: ignore[method-assign]
    fpdf.FPDF.rect = espia_rect  # type: ignore[method-assign]
    pdf_mod._mapa_de_la_sacudida = marca  # type: ignore[assignment]
    try:
        render(model(shakemap=bloque), "technical")
    finally:
        fpdf.FPDF.circle = original  # type: ignore[method-assign]
        fpdf.FPDF.rect = original_rect  # type: ignore[method-assign]
        pdf_mod._mapa_de_la_sacudida = original_mapa  # type: ignore[assignment]
    return (marcos[0] if marcos else None), vistos


def test_NADA_de_la_figura_se_sale_de_SU_RECUADRO() -> None:
    """Para esto existen los cuatro puntos de ENCUADRE, y nada lo comprobaba.

    `_puntos_del_mapa` lo lleva escrito —«sin ellos el encuadre lo marcarían los
    inmuebles, que están juntos, y un anillo de 100 km se saldría de la caja y se
    pintaría encima del resto de la página, porque `rect`/`circle` no recortan»— y
    era prosa. MEDIDO el 2026-09-21 quitando los cuatro puntos, sobre el marco real
    de esta figura (185.9 × 62.0 mm en (15.0, 183.2)): el anillo de 100 km pasa de
    11.574 mm de radio en (106.64, 225.00) a 15.730 mm en (97.99, 237.16), o sea
    `y 221.43..252.89`, y **se sale por ABAJO 7.73 mm**. Los otros tres círculos
    siguen dentro. Con esa mutación puesta, en `tests/dictamen` +
    `tests/documentos` esta prueba es la ÚNICA que cambia de color (`9 failed, 487
    passed` contra `8 failed, 488 passed` sin mutar; las otras ocho son un rojo
    ajeno, de `test_shakemap_en_el_builder.py`) — incluida la guarda del pie, que
    sigue verde porque el desbordamiento cabe dentro de la página aunque no dentro
    de la figura.

    ⚠️ Este mismo docstring decía «se sale … por arriba y por abajo», y el dato lo
    desmiente: por arriba le sobran 38.27 mm, y el mensaje de la propia guarda
    lista UN solo círculo. Una frase geométrica escrita de memoria, en el docstring
    de la guarda que existe precisamente para no fiarse de la prosa.

    Un anillo fuera de su marco no es un problema estético: la barra de escala está
    DENTRO del marco, y un círculo que la rebasa se mide contra un croquis que ya no
    lo contiene.
    """
    marco, circulos = _figura_espiada(_completo())
    assert marco is not None, "la figura salió sin recuadro: no hay contra qué medir"
    assert circulos, "la figura no dibujó ni un círculo: esta prueba aprobaría sobre el vacío"
    x0, y0, ancho, alto = marco

    fuera = [
        c
        for c in circulos
        if c.x - c.radio_mm < x0 - 0.05
        or c.x + c.radio_mm > x0 + ancho + 0.05
        or c.y - c.radio_mm < y0 - 0.05
        or c.y + c.radio_mm > y0 + alto + 0.05
    ]
    assert not fuera, (
        f"hay dibujo fuera del recuadro de la figura ({ancho:.1f} × {alto:.1f} mm en "
        f"({x0:.1f}, {y0:.1f})): {fuera}. `rect`/`circle` no recortan en PDF, así que eso "
        "se pinta encima del resto del documento"
    )


def _croquis_y_anillos(bloque: ShakemapBlock):
    """El croquis con el que se dibujó la capa modelada, y los anillos dibujados.

    Se captura el `Sketch` que recibe `_anillos_del_modelo` —no se reproyecta
    aquí— porque lo que hay que comprobar es que el radio que llegó al papel se
    puede medir con **la barra que ese mismo papel imprime al lado**. Una
    reproyección en la prueba mediría contra otra escala y no diría nada.
    """
    croquis = []
    original = pdf_mod._anillos_del_modelo

    def espia(pdf, b, dibujo, cx, cy):  # noqa: ANN001, ANN202
        croquis.append(dibujo)
        return original(pdf, b, dibujo, cx, cy)

    pdf_mod._anillos_del_modelo = espia  # type: ignore[assignment]
    try:
        circulos = _circulos_dibujados(bloque)
    finally:
        pdf_mod._anillos_del_modelo = original  # type: ignore[assignment]
    return croquis, [c for c in circulos if c.discontinuo]


def test_el_radio_dibujado_se_mide_con_la_BARRA_DE_ESCALA_del_propio_croquis() -> None:
    """**La cabecera de este módulo lo afirmaba y NADIE lo comprobaba.**

    La guarda que había comparaba `grande / pequeño == 100 / 40`, una razón que es
    invariante ante CUALQUIER factor de escala global — incluido uno catastrófico.
    Medido el 2026-09-21 con `Sketch.mm_por_km` fijado a `0.15` (una constante de
    página, que es exactamente el defecto que mató a `mmi-severa`): 460 passed. Con
    la barra real de ese documento —23.148 mm = 200 km— el anillo rotulado «40 km»
    salía de 6.000 mm, o sea **51.8 km leídos con la regla**, un 29.6 % de más.

    Lo que se mide aquí es lo único que hace honesta la figura: que el radio
    dibujado, medido con la barra impresa al lado, dé los kilómetros que el
    rótulo dice.
    """
    bloque = _completo()
    croquis, anillos = _croquis_y_anillos(bloque)

    assert len(croquis) == 1, f"se esperaba UNA capa modelada dibujada, hubo {len(croquis)}"
    dibujo = croquis[0]
    assert dibujo.scale_bar_km > 0 and dibujo.scale_bar_mm > 0, (
        "el croquis salió sin barra de escala: sin ella el radio no se puede medir "
        "sobre el papel y la figura no significa kilómetros"
    )
    esperados = sorted(
        a.radio_km * dibujo.scale_bar_mm / dibujo.scale_bar_km for a in bloque.anillos
    )
    medidos = sorted(c.radio_mm for c in anillos)
    assert medidos == pytest.approx(esperados, rel=1e-9), (
        f"los anillos miden {medidos} mm y con la barra impresa ({dibujo.scale_bar_mm:.3f} mm "
        f"= {dibujo.scale_bar_km:g} km) tendrían que medir {esperados} mm: el radio dibujado "
        "no se puede medir con la escala que el propio documento imprime"
    )


def test_lo_MEDIDO_y_lo_MODELADO_no_comparten_CODIFICACION() -> None:
    """El invariante central de `D-08 · §A.3`, que ninguna prueba del papel medía.

    Medido el 2026-09-21: cambiando `set_dash_pattern(...)` por `set_fill_color(*INK)`
    y `style="D"` por `style="F"` en `_anillos_del_modelo` —o sea pintando la
    predicción del modelo exactamente igual que una medición— la suite entera
    seguía en VERDE, 460 passed, con la leyenda impresa encima diciendo «ANILLO
    DISCONTINUO … es un modelo, no una medición, y por eso se dibuja distinto».

    Se comprueban las dos mitades: que cada clase tenga su codificación y que las
    dos codificaciones sean DISTINTAS. La segunda es la que no se puede satisfacer
    por accidente.
    """
    circulos = _circulos_dibujados(_completo())
    anillos = [c for c in circulos if c.discontinuo]
    medidas = [c for c in circulos if c.relleno]

    assert len(anillos) == 2, (
        f"la capa modelada no se dibujó con trazo discontinuo: {len(anillos)} anillos "
        "discontinuos para dos niveles de modelo"
    )
    assert not any(c.relleno for c in anillos), (
        "un anillo del modelo se pintó RELLENO: el relleno significa «esto lo midió "
        "un sensor», y esto es lo que una ley de atenuación predice"
    )
    assert medidas, "no se dibujó ni un disco lleno: la figura perdió las mediciones"
    assert not any(c.discontinuo for c in medidas), (
        "una medición se dibujó con trazo discontinuo, que es la forma reservada al modelo"
    )

    codificacion = lambda c: (c.relleno, c.discontinuo)  # noqa: E731
    assert {codificacion(c) for c in anillos}.isdisjoint({codificacion(c) for c in medidas}), (
        "lo modelado y lo medido comparten codificación visual: la leyenda promete "
        "que se dibujan distinto y la figura los dibuja igual"
    )


def test_un_inmueble_que_NO_publico_no_se_pinta_como_una_MEDICION() -> None:
    """La regla de oro 7 en la tinta, y la figura desmentía a su propia tabla.

    Medido el 2026-09-21: un inmueble con coordenadas y sin `pga_g` —que es lo que
    trae el fixture del lector— se pintaba como DISCO LLENO, que la leyenda define
    como «SACUDIDA MEDIDA en ese inmueble», mientras la tabla de debajo imprimía
    «SIN DATO» de ese mismo inmueble. `SacudidaFila.pga_g` ya documenta que `None`
    **no es 0 g**; el dibujo lo estaba convirtiendo en una medición.
    """
    con_mudo = _completo(
        anillos=[],
        epicentro_lat=None,
        epicentro_lon=None,
        epicentro_magnitud=None,
        puntos=[
            _puntos()[0],
            SacudidaFila(
                site_code="MUDO-1",
                site_name="Torre Muda",
                lat=19.43,
                lon=-99.13,
                pga_g=None,
                pgv_cms=None,
                dist_km=112.0,
                pga_g_modelada=None,
                residuo_log10=None,
            ),
        ],
    )
    marcadores = [
        c
        for c in _circulos_dibujados(con_mudo)
        if c.radio_mm <= pdf_mod.MARCA_PROPIA_MM + 1e-9 and not c.discontinuo
    ]
    assert len(marcadores) == 2, (
        f"la figura dibujó {len(marcadores)} marcadores para dos inmuebles: {marcadores}"
    )
    rellenos = [c for c in marcadores if c.relleno]
    huecos = [c for c in marcadores if not c.relleno]
    assert len(rellenos) == 1 and len(huecos) == 1, (
        "el inmueble que NO publicó y el que midió se pintaron igual: la figura "
        f"afirma una medición que la tabla niega — rellenos={rellenos}, huecos={huecos}"
    )

    seccion = _seccion(con_mudo)
    assert LEYENDA_SIN_DATO in seccion, "se dibuja un símbolo que la leyenda no nombra"
    assert "SIN DATO" in seccion, "la tabla dejó de declarar la ausencia del inmueble mudo"

    # El lado negativo: sin ningún inmueble mudo, ni símbolo ni leyenda de ausencia.
    todos_midieron = _circulos_dibujados(_completo())
    solo_marcadores = [
        c
        for c in todos_midieron
        if c.radio_mm <= pdf_mod.MARCA_PROPIA_MM + 1e-9 and not c.discontinuo
    ]
    assert all(c.relleno for c in solo_marcadores), (
        "se dibujó un círculo vacío en un documento donde todos los inmuebles midieron"
    )
    assert LEYENDA_SIN_DATO not in _seccion(_completo()), (
        "la leyenda nombra el símbolo de la ausencia en una figura que no lo dibuja"
    )


def _celdas_de(seccion: str, primera: str, cuantas: int) -> list[str]:
    """Las `cuantas` celdas consecutivas del flujo que empiezan en `primera`."""
    lineas = seccion.split("\n")
    i = lineas.index(primera)
    return lineas[i : i + cuantas]


def test_cada_celda_de_la_tabla_sale_BAJO_SU_COLUMNA() -> None:
    """Intercambiar `MEDIDO (g)` y `MODELO (g)` dejaba 373 passed.

    Es literalmente «el dictamen presenta lo modelado como medido», la frase que
    `RO-7.f` dice impedir: el papel imprimiría la predicción de la ley bajo el
    rótulo de la medición del sensor, y el residuo de al lado seguiría siendo
    correcto, así que nada chirriaría. La guarda que había sólo pedía que las
    cadenas «0.081» y «0.041» aparecieran en ALGÚN punto del texto de la sección.

    Se casa cabecera y fila POR POSICIÓN, que es lo que la tabla significa.
    """
    seccion = _seccion(_completo())
    columnas = list(pdf_mod.COLUMNAS_DE_LA_SACUDIDA)

    cabecera = _celdas_de(seccion, columnas[0], len(columnas))
    assert cabecera == columnas, f"la cabecera salió como {cabecera}"

    fila = dict(
        zip(
            columnas,
            _celdas_de(seccion, "Planta Cholula (CHL-A) ·", len(columnas)),
            strict=True,
        )
    )
    assert fila["DIST (km)"] == "187"
    assert fila["MEDIDO (g)"] == "0.0810", (
        f"bajo «MEDIDO (g)» se imprimió {fila['MEDIDO (g)']!r}, y lo que el sensor midió "
        "es 0.0810 g: el papel está presentando lo modelado como medido"
    )
    assert fila["MODELO (g)"] == "0.0410", (
        f"bajo «MODELO (g)» se imprimió {fila['MODELO (g)']!r}, y lo que la ley predice "
        "a esa distancia es 0.0410 g"
    )
    assert fila["MEDIDO (cm/s)"] == "3.20"
    assert fila["RESIDUO log10"] == "+0.31"


def test_la_frase_del_MODELO_solo_sale_si_el_documento_reporta_un_modelo() -> None:
    """La §5 prometía modelo y residuo en un documento cuyo mapa está sin calcular.

    Medido el 2026-09-21 con el espía del render sobre el pericial de un incidente
    **sin snapshot** —la condición NORMAL, porque el mapa se calcula por evento—:
    la §5 imprimía «la que el modelo de atenuación predice a su distancia, y el
    residuo entre ambas» y tres secciones más abajo el mismo documento imprimía
    «MAPA DE LA SACUDIDA NO CALCULADO TODAVÍA». Es la familia que costó `T-7.34`,
    `T-7.38` y `T-7.39`, invertida.

    Lo que NO cambia y se comprueba en el mismo sitio: la parte invariante de
    `NO_MMI` —ni MMI ni isosistas— sale SIEMPRE, porque está impresa en documentos
    ya firmados y sigue siendo verdad.
    """
    completo = _capturado(_completo()).texto
    assert NO_MMI in completo
    assert MODELO_Y_RESIDUO in completo, "el documento que SÍ modela dejó de decirlo"

    pendiente = _capturado(ShakemapBlock()).texto
    assert NO_MMI in pendiente
    assert SHAKEMAP_PENDIENTE in pendiente
    assert MODELO_Y_RESIDUO not in pendiente, (
        "la §5 promete modelo y residuo en un documento cuyo mapa dice «NO CALCULADO "
        "TODAVÍA»: el papel se desmiente a sí mismo seis líneas después"
    )

    degradado = _capturado(_degradado_sin_magnitud(sin_epicentro=True)).texto
    assert MODELO_Y_RESIDUO not in degradado, (
        "la §5 promete un residuo en un documento DEGRADADO, donde no hay con qué "
        "compararlo y la propia sección lo declara"
    )

    # Y el caso fino: hay MODELO y no hay RESIDUO. `calculo._punto` le da su PGA
    # modelada a un inmueble MUDO con distancia —el modelo no necesita que nadie
    # midiera— y le deja el residuo en `None`; el que sí midió, si no tiene
    # geometría, no tiene distancia y por tanto no tiene modelo. Un documento así
    # imprime la columna MODELO con la columna RESIDUO entera en SIN DATO, y la §5
    # prometía «el residuo entre las dos».
    solo_modelo = _completo(
        puntos=[
            SacudidaFila(
                site_code="CHL-A",
                site_name="Planta Cholula",
                lat=19.06,
                lon=-98.30,
                pga_g=0.081,
                pgv_cms=3.2,
                dist_km=None,
                pga_g_modelada=None,
                residuo_log10=None,
                propio=True,
            ),
            SacudidaFila(
                site_code="CDMX-1",
                site_name="Torre CDMX",
                lat=19.43,
                lon=-99.13,
                pga_g=None,
                pgv_cms=None,
                dist_km=112.0,
                pga_g_modelada=0.068,
                residuo_log10=None,
            ),
        ]
    )
    sin_residuo = _capturado(solo_modelo)
    assert MODELO_Y_RESIDUO not in sin_residuo.texto, (
        "la §5 promete «el residuo entre las dos» en un documento cuya columna RESIDUO "
        "está entera en SIN DATO"
    )
    assert "0.0680" in sin_residuo.seccion(MAPA_SACUDIDA), (
        "el escenario dejó de tener modelo: entonces no mide lo que dice medir"
    )


def _degradado_sin_magnitud(*, sin_epicentro: bool) -> ShakemapBlock:
    """Un mapa con medidas y SIN capa modelada, coherente de punta a punta.

    Los puntos pierden también `pga_g_modelada` y `residuo_log10`: dejarlos
    puestos sería un snapshot que dice «no modelé» trayendo el modelo dentro, y
    una prueba montada sobre un dato imposible no mide el caso que dice medir.
    """
    return _completo(
        estado="solo_observado",
        ley=None,
        epicentro_lat=None if sin_epicentro else 16.80,
        epicentro_lon=None if sin_epicentro else -99.50,
        epicentro_magnitud=None,
        anillos=[],
        puntos=[
            SacudidaFila(
                site_code="CHL-A",
                site_name="Planta Cholula",
                lat=19.06,
                lon=-98.30,
                pga_g=0.081,
                pgv_cms=3.2,
                dist_km=None,
                pga_g_modelada=None,
                residuo_log10=None,
                propio=True,
            )
        ],
    )


def test_el_aviso_de_DEGRADADO_dice_QUE_falta_y_no_desmiente_al_campo_de_al_lado() -> None:
    """El caso literal del criterio de la ficha: «degradado cuando no hay magnitud».

    Con el epicentro CITADO y la magnitud ausente, el papel imprimía el epicentro
    y acto seguido «MAPA DEGRADADO: sin epicentro y magnitud citados…». Medido el
    2026-09-21 con `epicentro_lat=16.80, epicentro_lon=-99.50,
    epicentro_magnitud=None`. Ningún escenario cubría esa combinación: los
    `solo_observado` de las dos suites ponían epicentro Y magnitud a `None` a la
    vez, así que la frase siempre era cierta por casualidad.
    """
    con_epicentro = _seccion(_degradado_sin_magnitud(sin_epicentro=False))
    assert SHAKEMAP_DEGRADADO in con_epicentro
    assert "16.80, -99.50" in con_epicentro, "el epicentro citado dejó de imprimirse"
    assert "la magnitud citada" in con_epicentro, "el aviso no nombra lo que de verdad falta"
    assert "el epicentro y la magnitud" not in con_epicentro, (
        "el aviso dice que falta el epicentro dos líneas debajo de imprimirlo: un aviso "
        "que el campo de al lado desmiente enseña a ignorar el aviso"
    )

    sin_nada = _seccion(_degradado_sin_magnitud(sin_epicentro=True))
    assert "el epicentro y la magnitud" in sin_nada, (
        "cuando faltan las dos citas el aviso tiene que decirlo: el lado opuesto de la misma guarda"
    )


def test_la_leyenda_nombra_SOLO_los_simbolos_que_la_figura_dibuja() -> None:
    """Una leyenda que describe símbolos ausentes enseña a leer una figura que no está.

    Medido el 2026-09-21: en DEGRADADO —sin capa modelada y sin epicentro— el papel
    imprimía «ANILLO DISCONTINUO = lo que el modelo … PREDICE» y «La cruz es el
    epicentro» sobre una figura sin un solo anillo y sin cruz. Y en el caso SIN
    COORDENADAS, donde no hay figura ninguna, la leyenda se imprimía igual, porque
    los dos `callout` iban ANTES de la figura y la figura se rendía por dentro.

    Cada aserción se cruza con lo que de verdad se dibujó, no con lo que se quiso
    dibujar: el nombre del símbolo y el símbolo salen del mismo documento.
    """
    completo = _seccion(_completo())
    for pieza in (SHAKEMAP_LEYENDA, LEYENDA_DISCO, LEYENDA_ANILLO, LEYENDA_CRUZ):
        assert pieza in completo, "la figura completa perdió una pieza de su leyenda"

    degradado = _degradado_sin_magnitud(sin_epicentro=True)
    texto = _seccion(degradado)
    _croquis, anillos = _croquis_y_anillos(degradado)
    assert anillos == [], "se dibujaron anillos de un modelo que no existe"
    assert SHAKEMAP_LEYENDA in texto, "hay figura y se quedó sin leyenda"
    assert LEYENDA_DISCO in texto
    assert LEYENDA_ANILLO not in texto, (
        "la leyenda describe un ANILLO DISCONTINUO en una figura que no dibuja ninguno"
    )
    assert LEYENDA_CRUZ not in texto, (
        "la leyenda anuncia la cruz del epicentro en una figura sin epicentro"
    )

    ciego = _completo(
        puntos=[
            SacudidaFila(
                site_code="CHL-A",
                site_name="Planta Cholula",
                lat=None,
                lon=None,
                pga_g=0.081,
                pgv_cms=3.2,
                dist_km=187.0,
                pga_g_modelada=0.041,
                residuo_log10=0.31,
                propio=True,
            )
        ],
        epicentro_lat=None,
        epicentro_lon=None,
    )
    sin_figura = _seccion(ciego)
    assert SHAKEMAP_SIN_GEOMETRIA in sin_figura
    for pieza in (SHAKEMAP_LEYENDA, LEYENDA_DISCO, LEYENDA_ANILLO, LEYENDA_CRUZ, LEYENDA_SIN_DATO):
        assert pieza not in sin_figura, (
            "se imprime la leyenda del dibujo donde NO hay dibujo: describe una figura "
            "que el propio documento acaba de declarar imposible"
        )
    assert SHAKEMAP_SIN_COBERTURA not in sin_figura, (
        "se declara qué no afirma la figura en un documento que no tiene figura"
    )


def test_el_rotulo_del_ESTADO_se_DERIVA_de_lo_que_el_documento_imprime() -> None:
    """Un snapshot incoherente imprimía «COMPLETO · medido y modelado» y, seis líneas
    después, «MAPA DEGRADADO: … no se dibuja la capa modelada».

    Medido el 2026-09-21 con `estado='completo'`, `anillos=[]` y sin epicentro. El
    criterio ya existía en la sección —un `completo` con cero medidas se imprime
    como SIN MEDIDAS, con su prueba— y estaba aplicado a la mitad de los casos.

    Lo que el snapshot dice de sí mismo NO se tira: si discrepa, se imprime al
    lado. Un dictamen es evidencia y esa discrepancia es un hecho auditable.
    """
    # ⚠️ Los puntos pierden TAMBIÉN el modelo. Con `pga_g_modelada` puesta y sin
    # epicentro el snapshot es imposible por partida doble, y sobre todo deja de
    # ser el caso que esta prueba dice medir: un documento que imprime la columna
    # MODELO **sí** es un documento que modela, aunque no dibuje anillos, y
    # llamarlo DEGRADADO es la falsedad que cierra
    # `test_un_mapa_SIN_ANILLOS_pero_CON_MODELO_no_es_un_mapa_DEGRADADO`.
    incoherente = _completo(
        anillos=[],
        epicentro_lat=None,
        epicentro_lon=None,
        epicentro_magnitud=None,
        puntos=[
            SacudidaFila(
                site_code="CHL-A",
                site_name="Planta Cholula",
                lat=19.06,
                lon=-98.30,
                pga_g=0.081,
                pgv_cms=3.2,
                dist_km=None,
                pga_g_modelada=None,
                residuo_log10=None,
                propio=True,
            )
        ],
    )
    seccion = _seccion(incoherente)
    assert "DEGRADADO · sólo medido" in seccion
    assert "COMPLETO · medido y modelado" not in seccion, (
        "el rótulo dice COMPLETO en un documento que declara, seis líneas más abajo, "
        "que no dibuja la capa modelada"
    )
    assert "«completo»" in seccion, (
        "la discrepancia con el snapshot se tiró en vez de declararse: es un hecho "
        "auditable sobre el dato de origen"
    )
    # Y el caso coherente NO lleva la coletilla: un aviso que sale siempre no informa.
    assert "el snapshot se declara" not in _seccion(_completo())


def _bloque_por_la_ruta_real(magnitud: float) -> ShakemapBlock:
    """El bloque del papel construido como en producción, sin fixture a mano.

    `calculo.calcula` → la forma persistida (`anillos_json`/`puntos_json`) →
    `lectura.leer` → `builder.bloque_de_shakemap`. Se hace la vuelta entera porque
    el defecto que cierran las dos guardas de abajo **nació de una fixture**: la
    del caso degradado limpia a mano `pga_g_modelada` y `residuo_log10` «porque
    dejarlos puestos sería un snapshot que dice no modelé trayendo el modelo
    dentro», y con eso esquivaba el único snapshot que el cálculo produce de
    verdad sin anillos y con modelo — uno que se declara `completo`.

    La conexión es falsa y la lectura es la de verdad: lo que hay que ejercer es
    la traducción de la fila a `ShakemapOut` —que es donde `modelado` se vuelve
    `None` y los niveles suprimidos se separan de los dibujados—, no el SQL.
    """
    epicentro = dataclasses.replace(EPICENTRO_REF, magnitud=magnitud)
    mapa = shk.calcula(
        [_medida_ref()],
        epicentro=epicentro,
        niveles=NIVELES_REF,
        cobertura_km=5.0,
        radio_max_km=TOPE_REF,
    )
    fila = SimpleNamespace(
        incident_id="11111111-2222-3333-4444-555555555555",
        estado=mapa.estado,
        calculado_en=_CALCULADO,
        ley=mapa.ley,
        cobertura_km=mapa.cobertura_km,
        epicentro=shk.epicentro_json(mapa),
        puntos=shk.puntos_json(mapa),
        anillos=shk.anillos_json(mapa),
    )

    class _Conn:
        async def execute(self, *_a, **_k):  # noqa: ANN002, ANN003, ANN202
            return SimpleNamespace(first=lambda: fila)

    return bloque_de_shakemap(asyncio.run(leer(_Conn(), fila.incident_id)), "CDMX-01")


def test_un_mapa_SIN_ANILLOS_pero_CON_MODELO_no_es_un_mapa_DEGRADADO() -> None:
    """El papel acusaba de incoherente a un snapshot coherente, y negaba lo que imprimía.

    El caso lo acredita el propio repositorio:
    `tests/shakemap/test_calculo.py::test_un_anillo_que_no_corta_la_superficie_no_se_publica_pero_se_DECLARA`.
    Con el foco a 48 km, los dos niveles de la banda de un M5.0 sólo se
    alcanzarían BAJO la superficie, así que no hay un solo anillo — y el mapa
    sigue siendo `completo`, porque hubo medida, epicentro y magnitud, y cada
    inmueble tiene su PGA modelada y su residuo.

    Medido el 2026-09-21 por esta misma ruta, antes del arreglo, TRES afirmaciones
    que el mismo documento desmiente ocho líneas después:

      ESTADO DEL MAPA: DEGRADADO · sólo medido · el snapshot se declara «completo»
      MAPA DEGRADADO: … ni se calcula el residuo … sin nada con qué compararlas.
      FALTA: la capa modelada del snapshot, pese a estar citados el epicentro y la magnitud.
      …
      Corporativo Reforma (CDMX-01) · / 122 / 0.0858 / 0.0038 / 3.20 / +1.35

    Es la familia de `T-7.34`/`T-7.38`/`T-7.39` —el papel desmintiéndose a sí
    mismo— reintroducida por el arreglo del rótulo, que derivaba el estado de
    `b.anillos` cuando el modelo vive por punto.
    """
    b = _bloque_por_la_ruta_real(5.0)
    assert b.estado == "completo" and b.anillos == [], "el escenario dejó de ser el que se mide"
    assert b.puntos[0].pga_g_modelada is not None and b.puntos[0].residuo_log10 is not None
    assert [n.motivo for n in b.fuera_de_alcance] == [shk.FUERA_BAJO_LA_SUPERFICIE] * 2, (
        "los niveles suprimidos no llegaron al papel: sin ellos la sección no puede "
        "decir por qué no hay anillos y se inventa una razón"
    )

    cap = _capturado(b)
    seccion = cap.seccion(MAPA_SACUDIDA)
    assert "COMPLETO · medido y modelado" in seccion
    assert "el snapshot se declara" not in seccion, (
        "el papel denuncia como incoherente un snapshot coherente: la coletilla acusa "
        "al dato de origen y acusarlo en falso enseña a ignorarla"
    )
    assert SHAKEMAP_DEGRADADO not in seccion, (
        "el documento dice «ni se calcula el residuo … sin nada con qué compararlas» "
        "y la tabla imprime MODELO y RESIDUO ocho líneas más abajo"
    )
    assert "pese a estar citados el epicentro y la magnitud" not in seccion, (
        "el aviso manda a buscar una capa modelada que nadie puede traer: los niveles "
        "quedaron bajo la superficie y el snapshot lo dice"
    )
    assert SHAKEMAP_SIN_ANILLOS in seccion
    assert shk.MOTIVOS_FUERA[shk.FUERA_BAJO_LA_SUPERFICIE] in seccion, (
        "no se dice POR QUÉ no hay anillos, que es lo único que evita leer el hueco "
        "como «esos umbrales no existían»"
    )
    # [T-8.12 · A-144] Por su rótulo en castellano: el identificador `pga_trip_g`
    # salía crudo en el papel. Lo que se vigila sigue siendo lo mismo —que el
    # nivel suprimido se NOMBRE— y ahora además que se nombre en la lengua del papel.
    # (Import local: uno arriba correría las líneas que cita la matriz RO-7.f.)
    from takab_api.dictamen import rotulos

    for umbral in (shk.UMBRAL_TRIP, shk.UMBRAL_WATCH):
        assert rotulos.UMBRAL[umbral] in seccion, "un nivel suprimido desapareció en silencio"
        assert umbral not in seccion, f"el nivel sale con su identificador crudo `{umbral}`"
    assert "0.0038" in seccion and "+1.35" in seccion, (
        "el modelo y el residuo que la sección negaba dejaron de imprimirse"
    )
    # Y la §5 promete exactamente lo que la §8 imprime: las dos salen del mismo bloque.
    assert MODELO_Y_RESIDUO in cap.texto

    # El otro lado: con el sismo de referencia entero los niveles SÍ se dibujan, y
    # entonces esta frase no tiene nada que explicar.
    con_anillos = _seccion(_bloque_por_la_ruta_real(7.1))
    assert SHAKEMAP_SIN_ANILLOS not in con_anillos
    assert "NIVELES DEL MODELO" in con_anillos

    # Y el degradado de verdad —sin modelo por ninguna parte— conserva SU frase.
    degradado = _seccion(_degradado_sin_magnitud(sin_epicentro=True))
    assert SHAKEMAP_DEGRADADO in degradado
    assert SHAKEMAP_SIN_ANILLOS not in degradado, (
        "un mapa sin modelo se anuncia como si tuviera uno"
    )


def test_un_snapshot_ILEGIBLE_lo_dice_y_no_se_disfraza_de_PENDIENTE() -> None:
    """«No ha corrido el cálculo» y «no pude leerlo» son dos hechos distintos.

    El builder lee el mapa best-effort desde la 2ª vuelta de `T-7.24` —un anexo no
    puede costar el dictamen— y lo que no puede hacer es degradar el fallo a
    `pendiente`: el papel afirmaría sobre el incidente algo que no sabe.
    """
    seccion = _seccion(ShakemapBlock(fallo_de_lectura="la lectura del snapshot falló"))
    assert "NO DISPONIBLE" in seccion
    assert SHAKEMAP_PENDIENTE not in seccion, (
        "un snapshot ilegible se imprime como «no calculado todavía», que es una "
        "afirmación sobre el incidente y no sobre este documento"
    )
