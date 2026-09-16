"""[T-7.22] CENSO POR SECCIÓN · qué secciones emite el informe, y con qué dentro.

El criterio de la ficha pide «espía del render por sección». Las suites que ya
existían espían el documento ENTERO: demuestran que un texto se imprimió, no
*dónde*. Un aviso que sale en la sección equivocada —la leyenda de reproducción
bajo «MARCO NORMATIVO», pongamos— pasa todas ellas en verde.

## Las dos mitades, y por qué ninguna basta sola

**(a) En ejecución.** Se espía `MembretePDF.section` y se trocea lo escrito por
sus marcas (`tests/documentos/espia.py`). Caza una sección que deja de dibujarse
y una que dibuja lo que no le toca.

**(b) Por AST, sobre el LITERAL que cada función pasa a `section()`.** Caza lo
contrario: una función de sección que existe y a la que ya no llama nadie. Se lee
el literal y no el nombre de la llamada porque los dos ya divergen en el árbol:
`_render_technical` llama a `_cctv_section` con el comentario `# 11` y esa
función imprime `section("12", …)`. Un censo que leyera los nombres de las
llamadas habría dado por bueno el comentario equivocado.

## El hueco de la numeración es REAL y se declara

Medido: el pericial imprime `1…12`, **14**, `15`. La 13 es el ANÁLISIS, que solo
se dibuja si hay prosa (`_narrative_section` sale antes si `m.narrative` está
vacío). Eso no es un defecto del render —un documento sin prosa no puede tener
sección de prosa— pero sí lo es callarlo: un lector que recibe un dictamen
firmado que salta de la 12 a la 14 no puede saber si le falta una página. Aquí se
fija cuáles pueden faltar y por qué; cualquier otro hueco pone la prueba roja.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from takab_api.dictamen import pdf as pdf_mod
from takab_api.dictamen.model import REPRODUCCION_NOTE, SIN_GEOMETRIA_DE_RED
from takab_api.dictamen.pdf import render
from tests.dictamen.test_pdf import model
from tests.documentos.espia import espia_del_render

FUENTE = Path(pdf_mod.__file__)

#: Secciones del pericial que pueden NO emitirse, con la condición que las quita.
#: Va por título y no por número: renumerar no puede convertir una ausencia
#: declarada en una muda.
CONDICIONALES: dict[str, str] = {
    "ANÁLISIS": "solo con prosa: `_narrative_section` sale antes si `m.narrative` está vacío",
}


def _capturado(m=None, variante: str = "technical"):
    with espia_del_render() as cap:
        render(m if m is not None else model(), variante)
    return cap


def _literales_de_seccion() -> list[tuple[str, str]]:
    """Cada `pdf.section("n", "TÍTULO")` que el módulo escribe, por AST.

    Devuelve `(numero, titulo)` de las llamadas con los dos argumentos literales.
    Una llamada con el número calculado no se vería, y por eso la mitad (a) mide
    lo que realmente se emitió: las dos se cruzan.
    """
    arbol = ast.parse(FUENTE.read_text(encoding="utf-8"), filename=str(FUENTE))
    salida: list[tuple[str, str]] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
            continue
        if nodo.func.attr != "section" or len(nodo.args) != 2:
            continue
        if not all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in nodo.args):
            continue
        salida.append((nodo.args[0].value, nodo.args[1].value))
    return salida


# ─────────────────────────────────────────── guardas de no-vacuidad, primero


def test_el_espia_por_seccion_NO_esta_ciego() -> None:
    """Si el troceo dejara de ver secciones, todo lo de abajo pasaría por vacuidad.

    Es el ÚNICO modo de fallo que el troceo añade sobre el espía entero: una
    rebanada `[]` hace pasar cualquier `not in`.
    """
    cap = _capturado()
    assert len(cap.marcadores) > 10, f"el espía solo vio {len(cap.marcadores)} secciones"
    assert len(cap.texto) > 3000, f"el espía solo recogió {len(cap.texto)} caracteres"
    # Y separa el membrete del cuerpo: si no lo hiciera, cada rebanada llevaría
    # el pie pegado y las aserciones medirían el membrete, no la sección.
    assert "EVIDENCIA INMUTABLE" in cap.membrete
    assert "EVIDENCIA INMUTABLE" not in cap.texto


def test_el_barrido_AST_lee_el_modulo_de_verdad() -> None:
    literales = _literales_de_seccion()
    assert len(literales) > 10, f"el AST solo encontró {len(literales)} llamadas a section()"
    assert ("7", "RED DE ESTACIONES") in literales


# ───────────────────────────────────────────────── el censo, en sus dos mitades


def test_TODA_seccion_escrita_se_EMITE_o_esta_declarada_como_condicional() -> None:
    """La mitad que caza una sección huérfana: escrita y a la que nadie llama."""
    emitidos = set(_capturado().titulos)
    # El ejecutivo tiene sus propias secciones, sin número: se miran aparte.
    del_ejecutivo = set(_capturado(variante="executive").titulos)
    huerfanas = [
        f"{numero}. {titulo}"
        for numero, titulo in _literales_de_seccion()
        if titulo not in emitidos and titulo not in del_ejecutivo and titulo not in CONDICIONALES
    ]
    assert not huerfanas, (
        "hay secciones escritas que ningún render emite —o dejaron de llamarse, o "
        f"son condicionales sin declarar—: {huerfanas}"
    )


def test_TODA_seccion_emitida_esta_ESCRITA_en_el_modulo() -> None:
    """Y la contraria: nada se imprime desde un literal que el censo no ve."""
    escritos = {t for _, t in _literales_de_seccion()}
    sueltas = [t for t in _capturado().titulos if t not in escritos]
    assert not sueltas, f"secciones emitidas que el barrido AST no ve: {sueltas}"


def test_la_numeracion_del_pericial_NO_tiene_huecos_MUDOS() -> None:
    """Consecutiva desde 1; lo que falte, declarado con su condición y su razón."""
    cap = _capturado()
    numeros = [int(n) for n in cap.numeros]
    assert numeros == sorted(numeros), f"las secciones salen desordenadas: {numeros}"
    assert len(numeros) == len(set(numeros)), f"hay un número repetido: {numeros}"
    assert numeros[0] == 1, f"el pericial no empieza en 1: {numeros}"

    faltan = set(range(1, numeros[-1] + 1)) - set(numeros)
    # Los huecos permitidos son los de las secciones declaradas condicionales, y
    # se comprueba que el hueco sea EL SUYO: declarar una condicional no autoriza
    # a que falte cualquier otra.
    permitidos = {
        int(n) for n, titulo in _literales_de_seccion() if titulo in CONDICIONALES and n.isdigit()
    }
    assert faltan <= permitidos, (
        f"el pericial salta del {sorted(faltan)} sin declararlo. Un dictamen firmado "
        "que salta un número deja al lector sin saber si le falta una página. "
        f"Condicionales declaradas: {sorted(permitidos)}"
    )


def test_la_condicional_declarada_SI_aparece_cuando_se_cumple_su_condicion() -> None:
    """Una condicional que NUNCA se emite no es condicional: está muerta.

    Sin esto, `CONDICIONALES` sería una lista de excusas donde esconder una
    sección rota.
    """
    cap = _capturado(model(narrative=[("Resumen", "Prosa de prueba.")]))
    assert cap.emitio("ANÁLISIS"), (
        "la §13 está declarada condicional a que haya prosa, y con prosa tampoco sale"
    )
    assert "Prosa de prueba." in cap.seccion("ANÁLISIS")


def test_el_ejecutivo_deja_el_numero_VACIO_a_proposito() -> None:
    """Y se fija, porque es lo que impide troceárlo con una expresión regular.

    El ejecutivo no es un documento numerado: son cuatro preguntas. Si algún día
    llevara números, el troceo por marca los recogería igual — pero esta prueba
    obliga a que el cambio sea deliberado.
    """
    cap = _capturado(variante="executive")
    assert cap.marcadores, "el ejecutivo no emitió ninguna sección"
    assert all(n == "" for n in cap.numeros), (
        f"el ejecutivo empezó a numerar secciones: {cap.numeros}"
    )
    assert "QUÉ PASÓ" in cap.titulos


# ──────────────────────────────── lo que T-7.22 mete DENTRO de «RED DE ESTACIONES»


def test_la_leyenda_de_REPRODUCCION_sale_en_la_seccion_de_la_RED() -> None:
    """Y no en cualquier parte del papel: la condiciona a ella.

    Un lector que llega a la tabla de arribos sin haber leído la leyenda está
    midiendo la respuesta de un edificio a un sismo que no ocurrió.
    """
    cap = _capturado(model(reproduccion=True))
    assert REPRODUCCION_NOTE in cap.seccion("RED DE ESTACIONES")


def test_sin_reproduccion_la_leyenda_NO_aparece() -> None:
    """El lado negativo. Rotular de reproducción un incidente real es igual de falso."""
    assert REPRODUCCION_NOTE not in _capturado().texto


def test_la_tabla_de_la_red_lleva_el_UMBRAL_con_su_procedencia() -> None:
    """[T-7.35] Un pico sin umbral es un número sin escala, y un umbral sin
    procedencia parece del edificio aunque sea el de referencia."""
    seccion = _capturado().seccion("RED DE ESTACIONES")
    assert "UMBRAL (g)" in seccion
    assert "de referencia" in seccion, "el origen del umbral no llegó al papel"
    assert "del inmueble" in seccion


def test_sin_coordenadas_la_ausencia_del_mapa_se_DECLARA_en_su_seccion() -> None:
    """Una caja vacía se leería como «no hay estaciones», que es lo contrario de
    lo que dice la tabla que va justo debajo."""
    from dataclasses import replace

    ciego = model(
        site_lat=None,
        site_lon=None,
        epicenter_lat=None,
        epicenter_lon=None,
        estaciones=[replace(e, lat=None, lon=None) for e in model().estaciones],
    )
    seccion = _capturado(ciego).seccion("RED DE ESTACIONES")
    assert SIN_GEOMETRIA_DE_RED in seccion
    # Y la tabla sigue estando: la ausencia del mapa no se lleva por delante los
    # arribos, que no dependen de la geometría.
    assert "ESPERADO (s)" in seccion


@pytest.mark.parametrize("variante", ["technical", "executive"])
def test_ninguna_seccion_se_queda_VACIA(variante: str) -> None:
    """Un título con nada debajo es peor que no tener la sección: promete un dato.

    Se mide sobre el cuerpo, sin el membrete: la cabecera y el pie caen dentro de
    las rebanadas al saltar de página y harían pasar esto por el motivo
    equivocado.
    """
    cap = _capturado(variante=variante)
    vacias = [t for t in cap.titulos if not cap.seccion(t).strip()]
    assert not vacias, f"secciones con título y sin contenido en {variante}: {vacias}"
