"""T-5.07 · Los avisos del dictamen se comprueban SOBRE EL DOCUMENTO GENERADO.

El test que había decía esto, entero::

    assert DISCLAIMER.startswith("Dictamen operativo PRELIMINAR")
    for variant in ("technical", "executive"):
        assert render(model(), variant).startswith(b"%PDF")

O sea: que una constante empiece por una cadena, y que el archivo sea un PDF.
**Borrar la llamada que imprime el deslinde dejaba el test en verde**, y lo mismo
valía para los otros diez avisos. El deslinde impreso es lo que protege al
proyecto en una reunión comercial, y era la única pieza del documento cuya
desaparición nadie habría notado hasta que hiciera falta.

CÓMO SE COMPRUEBA, Y POR QUÉ NO DE LAS DOS FORMAS OBVIAS.

*Buscar el texto en los bytes* no funciona: el flujo va comprimido **y** con
fuentes embebidas, así que el texto viaja como índices de glifo — la cadena no
aparece ni entera ni cortada (comprobado en `T-5.26`).

*Cambiar el modelo y exigir que los bytes cambien* —el patrón de
`test_compliance_section.py`— **pasa en verde sobre este defecto**: la portada
imprime `content_sha256()`, que se mueve con CUALQUIER cambio del modelo, así que
los dos PDF salen distintos aunque la sección no se dibuje. Además aquí no sirve
de nada: estos avisos son constantes, no hay ningún campo del modelo que los
encienda.

Lo que sí demuestra que el aviso llegó al papel: **espiar el punto por el que pasa
todo el texto que se dibuja** (`TakabPDF.text_of`). Si el `callout` no se llama,
la cadena no pasa por ahí y el test se pone rojo nombrando el aviso.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from takab_api.dictamen import model as modelo_mod
from takab_api.dictamen.model import (
    CCTV_PARCIALMENTE_PURGADO,
    CCTV_PENDIENTE,
    CCTV_PURGADO_SIN_ANALISIS,
    CCTV_SIN_CLIP,
    CONSULTA_EXTERNA_EN_VUELO,
    CORRELACION_EN_DISPUTA,
    ESTADO_DE_CONSULTA_NO_INTERPRETABLE,
    SIN_CONSULTA_A_FUENTE_EXTERNA,
    ActionRow,
    AnilloFila,
    CctvBlock,
    DanoFila,
    EvidenceRow,
    NivelFueraFila,
    ReportModel,
    SacudidaFila,
    ShakemapBlock,
    fuentes_line,
)
from takab_api.dictamen.pdf import render
from takab_api.documentos.membrete import MembretePDF
from tests.dictamen.test_pdf import _OPENED, model

_VARIANTES = ("technical", "executive")


def _texto_dibujado(m: ReportModel, variante: str) -> str:
    """Todo lo que el render pasó por `text_of`, que es por donde va el texto.

    Es un espía, no una lectura del PDF: el PDF no se puede leer (ver la cabecera).
    Lo que demuestra es que la llamada que imprime el aviso SE HIZO con ese texto.
    """
    visto: list[str] = []
    # ⚠️ [T-7.21] La BASE, no la subclase: ver la nota en
    # `tests/documentos/test_membrete_compartido.py`.
    original = MembretePDF.text_of

    def espia(self: MembretePDF, value: str) -> str:
        visto.append(value)
        return original(self, value)

    MembretePDF.text_of = espia  # type: ignore[method-assign]
    try:
        render(m, variante)
    finally:
        MembretePDF.text_of = original  # type: ignore[method-assign]
    return "\n".join(visto)


def _avisos_declarados() -> dict[str, str]:
    """Los avisos que el módulo del modelo declara. DERIVADO, no tecleado.

    Regla: constante de módulo, en mayúsculas, que es una **frase** (≥40 caracteres
    y con espacios). Eso separa los avisos de los rótulos cortos (`ABSENT`,
    `TS_FMT`, `CCTV_PURGADO`, `SIN_HASH`), que son celdas de tabla y no avisos.

    Un aviso nuevo entra solo al censo y `test_el_censo_cubre_TODOS_los_avisos` lo
    obliga a declarar dónde debe salir.
    """
    return {
        nombre: valor
        for nombre, valor in vars(modelo_mod).items()
        if nombre.isupper() and isinstance(valor, str) and len(valor) >= 40 and " " in valor
    }


def _dano(**over) -> DanoFila:
    """El reporte de daños MÍNIMO, al que cada escenario le cambia una cosa.

    Sin fotografías a propósito: los avisos que aquí se comprueban son los del
    reporte, no los de la imagen, y embeber JPEG en cada escenario del censo
    multiplicaría el coste de la suite sin comprobar nada más.
    """
    base = {
        "report_id": "d-1",
        "rol": "brigadista",
        "zona": "Nivel 3",
        "categorias": [{"key": "grieta", "severity": "alta"}],
        "personas_en_riesgo": False,
        "notas": None,
        "ts": _OPENED,
        "fotos": [],
        "fotos_omitidas": 0,
    }
    return DanoFila(**{**base, **over})


def _sacudida(**over) -> ShakemapBlock:
    """[T-7.24] El mapa de la sacudida COMPLETO, al que cada escenario le quita algo.

    Local, como `_dano`, y por la misma razón: el `model()` compartido no trae
    mapa —su estado por defecto es `pendiente`— y ponérselo dejaría sin escenario
    al aviso que declara justamente eso.

    Los dos inmuebles llevan residuo de signo OPUESTO a propósito: es lo que
    obliga a que la tabla se dibuje con datos de verdad y no con un caso trivial.
    """
    base = {
        "estado": "completo",
        "ley": "ATTEN-LAW v1",
        "calculado_en": _OPENED,
        "cobertura_km": 25.0,
        "epicentro_lat": 16.80,
        "epicentro_lon": -99.50,
        "epicentro_magnitud": 7.1,
        "epicentro_fuente": "SSN",
        "epicentro_procedencia": "confirmado",
        "puntos": [
            SacudidaFila(
                "CHL-A", "Planta Cholula", 19.06, -98.30, 0.081, 3.2, 187.0, 0.041, 0.31, True
            ),
            SacudidaFila("CDMX-1", "Torre CDMX", 19.43, -99.13, 0.012, 0.6, 112.0, 0.068, -0.75),
        ],
        "anillos": [
            AnilloFila(pga_g=0.070, radio_km=40.0, umbral="pga_watch_g"),
            AnilloFila(pga_g=0.020, radio_km=100.0, umbral="correlacion_min_pga_g"),
        ],
    }
    return ShakemapBlock(**{**base, **over})


#: Para cada aviso: cómo se fabrica el documento que DEBE llevarlo, y en qué
#: variantes. Las variantes se midieron ejecutando el render, no se supusieron.
#:
#: `frozenset()` = no sale en ninguna de las dos por sí solo; entonces el aviso se
#: comprueba en su test propio (es el caso de la asistencia automatizada, que
#: depende del proveedor de prosa y tiene además su lado negativo).
ESCENARIOS: dict[str, tuple[Callable[[], ReportModel], frozenset[str]]] = {
    # El que protege al proyecto en una reunión: va en LOS DOS documentos.
    "DISCLAIMER": (model, frozenset(_VARIANTES)),
    # Sin fuente de calibración, los números son RELATIVOS. También en el ejecutivo,
    # que es el que lee quien decide.
    "NO_CALIBRATION": (lambda: model(calibrated=False), frozenset(_VARIANTES)),
    # Los cinco del documento pericial.
    "NO_MMI": (model, frozenset({"technical"})),
    "ENVELOPE_NOTE": (model, frozenset({"technical"})),
    "CENTROID_NOTE": (model, frozenset({"technical"})),
    # [T-7.38·H] Y su excluyente: un epicentro que movió una PERSONA no es el
    # centroide de las estaciones, y el papel lo llamaba así por `event_source`.
    # La trazabilidad se añade solo cuando consta AQUÍ: el evento de red es
    # compartido entre inmuebles y la acción puede vivir en el incidente de otro.
    "EPICENTRO_REUBICADO": (
        lambda: model(epicenter_relocated=True),
        frozenset({"technical"}),
    ),
    "EPICENTRO_REUBICADO_AQUI": (
        lambda: model(
            epicenter_relocated=True,
            actions=[ActionRow(ts=_OPENED, kind="epicenter_relocate", actor="user:op")],
        ),
        frozenset({"technical"}),
    ),
    "EPICENTRO_REUBICADO_EN_LA_RED": (
        lambda: model(epicenter_relocated=True, actions=[]),
        frozenset({"technical"}),
    ),
    "SKETCH_NOTE": (model, frozenset({"technical"})),
    # [T-7.38·L] `NO_SPECTRUM` afirma «este incidente no tiene miniSEED archivado»,
    # así que su escenario es justo ése: SIN objeto en la custodia. Con uno
    # registrado y sin traza, el papel decía lo contrario de su propio §10.
    "NO_SPECTRUM": (lambda: model(evidence=[]), frozenset({"technical"})),
    "ONDA_NO_LEIDA": (
        lambda: model(evidence=[EvidenceRow("miniseed", "a" * 64, _OPENED)], raw_waveform=None),
        frozenset({"technical"}),
    ),
    # Sin un solo punto que proyectar no hay croquis, y se dice.
    "NO_GEOMETRY": (
        lambda: model(
            site_lat=None, site_lon=None, epicenter_lat=None, epicenter_lon=None, peers=[]
        ),
        frozenset({"technical"}),
    ),
    # Los tres estados del CCTV: significan cosas OPUESTAS y se leerían igual si el
    # documento solo dijera «sin datos».
    "NO_CCTV": (model, frozenset({"technical"})),
    "CCTV_SIN_CLIP": (
        lambda: model(cctv=CctvBlock(estado=CCTV_SIN_CLIP)),
        frozenset({"technical"}),
    ),
    "CCTV_PENDIENTE": (
        lambda: model(cctv=CctvBlock(estado=CCTV_PENDIENTE)),
        frozenset({"technical"}),
    ),
    # [T-7.38·F] Y los DOS estados de la poda, que antes se leían como «disponible»:
    # el papel anunciaba un clip destruido como archivado y prometía cifras que no
    # van a llegar. «Algunos podados» es una clase propia — decir «el vídeo está
    # archivado» con la mitad destruida es falso.
    "CCTV_PURGADO_SIN_ANALISIS": (
        lambda: model(cctv=CctvBlock(estado=CCTV_PURGADO_SIN_ANALISIS)),
        frozenset({"technical"}),
    ),
    "CCTV_PARCIALMENTE_PURGADO": (
        lambda: model(cctv=CctvBlock(estado=CCTV_PARCIALMENTE_PURGADO)),
        frozenset({"technical"}),
    ),
    # [T-5.11] Que el catálogo no tenga un sismo compatible es un HECHO sobre el
    # evento, no un fallo de búsqueda; y sin este aviso el papel deja un hueco
    # que se lee como «no pasó nada».
    "SIN_CORRELACION_EN_CATALOGO": (
        lambda: model(catalog_line=None),
        frozenset({"technical"}),
    ),
    # [T-7.22] La leyenda que un papel firmado no puede callarse: el epicentro y
    # la magnitud son los de un sismo HISTÓRICO. Solo en el pericial, que es el
    # que lleva la §7; el ejecutivo no tiene tabla de red que rotular.
    "REPRODUCCION_NOTE": (
        lambda: model(reproduccion=True),
        frozenset({"technical"}),
    ),
    # [T-7.22] Y la ausencia del mapa de la red, declarada en vez de dejar el
    # hueco: sin coordenadas en ninguna parte no se puede situar nada, y una caja
    # vacía se leería como «no hay estaciones» — que es lo contrario de lo que
    # dice la tabla que va justo debajo.
    "SIN_GEOMETRIA_DE_RED": (
        lambda: model(
            site_lat=None,
            site_lon=None,
            epicenter_lat=None,
            epicenter_lon=None,
            estaciones=[replace(e, lat=None, lon=None) for e in model().estaciones],
        ),
        frozenset({"technical"}),
    ),
    # [T-7.22] La bitácora vacía. En un incidente con sirena disparada sería un
    # defecto, y por eso se dice en vez de dejar la sección en blanco.
    "SIN_CRONOLOGIA": (lambda: model(actions=[]), frozenset({"technical"})),
    # [T-7.22] Y el recuento de verbos sin rótulo. El `kind` es deliberadamente
    # uno que `bitacora.ROTULOS` no conoce: `incident_actions` es append-only y
    # exenta de poda, así que un documento histórico puede traerlos.
    "CRONOLOGIA_SIN_ROTULO": (
        lambda: model(actions=[ActionRow(_OPENED, "verbo_de_otra_epoca", "system:edge")]),
        frozenset({"technical"}),
    ),
    # [T-7.22] Los daños del brigadista. Sin reportes NO se calla: la ausencia de
    # una inspección no es la ausencia de daños, y el hueco se leería como lo
    # segundo.
    "SIN_DANOS": (lambda: model(danos=[]), frozenset({"technical"})),
    # Los cuatro que dependen de CÓMO viene el reporte. Se fabrican con `_dano`,
    # que es el reporte mínimo al que se le cambia una cosa cada vez.
    "PERSONAS_EN_RIESGO": (
        lambda: model(danos=[_dano(personas_en_riesgo=True)]),
        frozenset({"technical"}),
    ),
    "ROL_NO_RESUELTO": (lambda: model(danos=[_dano(rol=None)]), frozenset({"technical"})),
    "SIN_CATEGORIAS": (lambda: model(danos=[_dano(categorias=[])]), frozenset({"technical"})),
    "FOTOS_OMITIDAS": (
        lambda: model(danos=[_dano(fotos_omitidas=3)]),
        frozenset({"technical"}),
    ),
    # [T-7.25] Y lo que el papel dice mientras la pregunta sigue en vuelo. Va
    # por `catalog_line` porque es la MISMA línea que imprimiría «SIN
    # CORRELACIÓN»: las dos ocupan el campo CORRELACIÓN CON CATÁLOGO, y de eso
    # se trata — que en ese hueco no salga la afirmación equivocada.
    "CONSULTA_EXTERNA_EN_VUELO": (
        lambda: model(catalog_line=CONSULTA_EXTERNA_EN_VUELO),
        frozenset({"technical"}),
    ),
    # [T-7.25] Y la otra mitad, que es el caso NORMAL: a este incidente no se le
    # preguntó a nadie. Ocupa el mismo campo que las otras dos y dice un hecho
    # distinto — «no se preguntó» no es «se preguntó y ninguno es éste».
    "SIN_CONSULTA_A_FUENTE_EXTERNA": (
        lambda: model(catalog_line=SIN_CONSULTA_A_FUENTE_EXTERNA),
        frozenset({"technical"}),
    ),
    # [T-7.25 · 4ª vuelta] Y el cuarto y quinto hecho: la consulta correlacionó y
    # el criterio de identidad de este documento no reconoce el acierto. Mismo
    # campo que los otros tres, que es donde estaba el defecto — ahí salía «SIN
    # CORRELACIÓN» de un incidente que sí correlacionó.
    "CORRELACION_EN_DISPUTA": (
        lambda: model(catalog_line=CORRELACION_EN_DISPUTA),
        frozenset({"technical"}),
    ),
    # [T-7.25 · 4ª vuelta] El suelo de esa misma línea: un estado de procedencia
    # que el papel no sabe traducir. Declara la ignorancia en vez de exonerar al
    # catálogo, que es lo que hacía la caída al final antes de esta vuelta.
    "ESTADO_DE_CONSULTA_NO_INTERPRETABLE": (
        lambda: model(catalog_line=ESTADO_DE_CONSULTA_NO_INTERPRETABLE),
        frozenset({"technical"}),
    ),
    # [T-7.25] A qué fuentes externas puede preguntar este despliegue. Las dos
    # caras se comprueban porque significan cosas opuestas y el papel las imprime
    # en el mismo sitio: «no consta» es el modelo construido a mano (el builder
    # siempre la rellena), y la otra es la línea derivada de la configuración.
    "FUENTES_EXTERNAS_SIN_CONSTANCIA": (model, frozenset({"technical"})),
    # Y la razón por la que el SSN nunca aparece: sin decirla, un lector supondrá
    # que el SSN falló, y lo que pasa es que su atribución está sin cerrar.
    "SSN_NO_SE_CONSULTA": (
        lambda: model(fuentes_externas=fuentes_line(True)),
        frozenset({"technical"}),
    ),
    # [T-7.24] Los del mapa de la sacudida. Sólo en el pericial: el ejecutivo
    # son cuatro preguntas, no una figura.
    #
    # La leyenda de procedencia y el `SIN COBERTURA` salen SIEMPRE que hay figura:
    # son el invariante de presentación de `D-08 · §A.3` escrito en el papel, y sin
    # ellos un anillo y un disco en la misma caja se leen como dos medidas de lo
    # mismo.
    "SHAKEMAP_LEYENDA": (lambda: model(shakemap=_sacudida()), frozenset({"technical"})),
    "SHAKEMAP_SIN_COBERTURA": (
        lambda: model(shakemap=_sacudida()),
        frozenset({"technical"}),
    ),
    # [T-7.24 · 2ª vuelta] Las CUATRO piezas de la leyenda, cada una por su lado.
    # La leyenda era una frase cerrada que se imprimía pasara lo que pasara y
    # describía anillos y cruz sobre figuras que no los dibujan; ahora cada símbolo
    # es una pieza y `pdf._leyenda_del_mapa` elige las que la figura trae. Que
    # existan por separado en el censo no es contabilidad: es lo que obliga a
    # declarar QUÉ documento dibuja cada símbolo.
    "LEYENDA_DISCO": (lambda: model(shakemap=_sacudida()), frozenset({"technical"})),
    "LEYENDA_ANILLO": (lambda: model(shakemap=_sacudida()), frozenset({"technical"})),
    "LEYENDA_CRUZ": (lambda: model(shakemap=_sacudida()), frozenset({"technical"})),
    # El único que NO sale del escenario completo: hace falta un inmueble con
    # coordenadas y SIN `pga_g`, que es el que se pintaba como disco lleno —o sea,
    # como una medición— mientras la tabla decía «SIN DATO» de él.
    "LEYENDA_SIN_DATO": (
        lambda: model(
            shakemap=_sacudida(
                puntos=[
                    SacudidaFila(
                        "CHL-A",
                        "Planta Cholula",
                        19.06,
                        -98.30,
                        0.081,
                        3.2,
                        187.0,
                        0.041,
                        0.31,
                        True,
                    ),
                    SacudidaFila(
                        "MUDO-1", "Torre Muda", 19.43, -99.13, None, None, 112.0, 0.068, None
                    ),
                ]
            )
        ),
        frozenset({"technical"}),
    ),
    # [T-7.24 · 2ª vuelta] La frase que la §5 AÑADE sólo cuando el mapa de verdad
    # trae modelo y residuo. Vivía dentro de `NO_MMI` y se imprimía siempre, o sea
    # también en el caso normal —el mapa se calcula por evento— donde tres
    # secciones más abajo el mismo documento dice «NO CALCULADO TODAVÍA».
    "MODELO_Y_RESIDUO": (lambda: model(shakemap=_sacudida()), frozenset({"technical"})),
    # [T-7.24 · 2ª vuelta] Y el quinto estado, que no es un estado del cálculo sino
    # de ESTE documento: el snapshot no se pudo leer. Lo escribe el builder, que
    # ahora lee best-effort como el CCTV y la onda cruda.
    "SHAKEMAP_NO_LEIDO": (
        lambda: model(shakemap=ShakemapBlock(fallo_de_lectura="la lectura del snapshot falló")),
        frozenset({"technical"}),
    ),
    # Y los cuatro estados, que significan cosas distintas y se leerían igual con
    # un hueco. `pendiente` es el del `model()` pelado: un modelo construido a mano
    # no tiene mapa calculado, y eso es exactamente lo que el papel debe decir.
    "SHAKEMAP_PENDIENTE": (model, frozenset({"technical"})),
    "SHAKEMAP_SIN_DATOS": (
        lambda: model(shakemap=ShakemapBlock(estado="sin_datos", calculado_en=_OPENED)),
        frozenset({"technical"}),
    ),
    # ⚠️ [T-7.24 · 3ª vuelta] Los puntos pierden TAMBIÉN `pga_g_modelada` y el
    # residuo. Un `solo_observado` que los conservara sería un snapshot que dice
    # «no modelé» trayendo el modelo dentro — y desde esta vuelta ya no imprime
    # este aviso, sino `SHAKEMAP_SIN_ANILLOS`, porque un documento que imprime la
    # columna MODELO sí modela aunque no dibuje anillos.
    "SHAKEMAP_DEGRADADO": (
        lambda: model(
            shakemap=_sacudida(
                estado="solo_observado",
                ley=None,
                epicentro_lat=None,
                epicentro_lon=None,
                epicentro_magnitud=None,
                anillos=[],
                puntos=[
                    SacudidaFila(
                        "CHL-A", "Planta Cholula", 19.06, -98.30, 0.081, 3.2, None, None, None, True
                    )
                ],
            )
        ),
        frozenset({"technical"}),
    ),
    # [T-7.24 · 3ª vuelta] Y el caso que NO es degradado aunque lo pareciera: el
    # modelo corrió, va por inmueble en la tabla, y aun así no hay un solo anillo
    # porque todos sus niveles quedaron bajo la superficie. Con el foco a 48 km es
    # lo que devuelve el cálculo para un M5.0 (`tests/shakemap/test_calculo.py`), y
    # con la frase del degradado el papel negaba —ocho líneas antes— el residuo que
    # él mismo imprime.
    "SHAKEMAP_SIN_ANILLOS": (
        lambda: model(
            shakemap=_sacudida(
                anillos=[],
                fuera_de_alcance=[
                    NivelFueraFila(umbral="pga_watch_g", pga_g=0.040, motivo="bajo_la_superficie")
                ],
            )
        ),
        frozenset({"technical"}),
    ),
    "SHAKEMAP_SIN_GEOMETRIA": (
        lambda: model(
            shakemap=_sacudida(
                epicentro_lat=None,
                epicentro_lon=None,
                anillos=[],
                puntos=[
                    SacudidaFila(
                        "CHL-A", "Planta Cholula", None, None, 0.081, 3.2, 187.0, 0.041, 0.31, True
                    )
                ],
            )
        ),
        frozenset({"technical"}),
    ),
    # Depende del PROVEEDOR de prosa, no del documento: ver sus dos tests propios.
    "NARRATIVE_AI_NOTE": (model, frozenset()),
}


def test_el_censo_cubre_TODOS_los_avisos_declarados() -> None:
    """Por igualdad: un aviso nuevo en el modelo obliga a declarar dónde debe salir.

    Es la mitad que impide que esto se quede atrás. Sin ella, el próximo aviso
    nacería sin prueba igual que nacieron estos once.
    """
    declarados = set(_avisos_declarados())
    assert declarados == set(ESCENARIOS), (
        "el censo de avisos impresos no cuadra con los que declara "
        "`dictamen/model.py`. Si has añadido un aviso, di en qué variante(s) debe "
        f"salir y con qué modelo se provoca. Diferencia: {declarados ^ set(ESCENARIOS)}"
    )


@pytest.mark.parametrize("nombre", sorted(n for n, (_, v) in ESCENARIOS.items() if v))
def test_el_aviso_LLEGA_al_documento(nombre: str) -> None:
    texto = _avisos_declarados()[nombre]
    fabrica, variantes = ESCENARIOS[nombre]
    m = fabrica()

    for variante in sorted(variantes):
        assert texto in _texto_dibujado(m, variante), (
            f"`{nombre}` NO se imprime en el documento {variante}. El render no "
            "llegó a dibujarlo: quitar esa llamada dejaba la suite en verde, y este "
            "es el test que existe para impedirlo."
        )


@pytest.mark.parametrize("nombre", sorted(n for n, (_, v) in ESCENARIOS.items() if v))
def test_el_aviso_NO_se_cuela_donde_no_toca(nombre: str) -> None:
    """La otra mitad: un aviso que saliera SIEMPRE no informa, decora.

    Los cinco del pericial no pueden aparecer en el resumen ejecutivo —que es corto
    a propósito— y los tres del CCTV se excluyen entre sí: si un documento llevara
    a la vez «sin cámara» y «clip pendiente», el lector no sabría cuál creer.
    """
    texto = _avisos_declarados()[nombre]
    fabrica, variantes = ESCENARIOS[nombre]
    m = fabrica()

    for variante in _VARIANTES:
        if variante in variantes:
            continue
        assert texto not in _texto_dibujado(m, variante), (
            f"`{nombre}` aparece en el documento {variante}, donde no debe: el "
            "resumen ejecutivo es corto a propósito y un aviso de más lo diluye"
        )


def test_los_TRES_estados_del_cctv_son_excluyentes() -> None:
    """Significan cosas opuestas: sin cámara · con cámara y sin clip · clip sin contar."""
    avisos = _avisos_declarados()
    for nombre in ("NO_CCTV", "CCTV_SIN_CLIP", "CCTV_PENDIENTE"):
        m = ESCENARIOS[nombre][0]()
        dibujado = _texto_dibujado(m, "technical")
        otros = [o for o in ("NO_CCTV", "CCTV_SIN_CLIP", "CCTV_PENDIENTE") if o != nombre]
        for otro in otros:
            assert avisos[otro] not in dibujado, (
                f"con el estado `{nombre}` el documento imprime TAMBIÉN `{otro}`: "
                "dos avisos que se contradicen dejan al lector sin saber cuál creer"
            )


def test_el_aviso_de_ASISTENCIA_AUTOMATIZADA_sale_solo_con_prosa_generada() -> None:
    """Su regla es la más fácil de romper y la que más importa.

    Ponerlo siempre sería mentir sobre un documento escrito por el proveedor
    determinista; no ponerlo nunca sería ocultar que hubo asistencia automatizada
    en un documento pericial. Se comprueban LOS DOS lados.
    """
    texto = _avisos_declarados()["NARRATIVE_AI_NOTE"]
    prosa = [("Resumen", "Texto de prueba.")]

    con_ia = model(narrative=prosa, narrative_provider="bedrock")
    assert texto in _texto_dibujado(con_ia, "technical"), (
        "un dictamen con prosa de un proveedor externo NO declara la asistencia "
        "automatizada: es el aviso que separa lo redactado de lo medido"
    )

    determinista = model(narrative=prosa, narrative_provider="deterministic")
    assert texto not in _texto_dibujado(determinista, "technical"), (
        "el aviso de asistencia automatizada sale con el proveedor DETERMINISTA: "
        "afirma una asistencia que no hubo"
    )

    sin_prosa = model()
    assert texto not in _texto_dibujado(sin_prosa, "technical"), (
        "el aviso sale en un documento SIN prosa generada"
    )


def test_el_espia_NO_esta_ciego() -> None:
    """Guarda de no-vacuidad, y la que sostiene a todas las de arriba.

    Si `text_of` dejara de ser el punto por el que pasa el texto —o si el render
    fallara en silencio— el espía devolvería poco o nada y **todos** los
    `assert ... not in ...` pasarían en verde. Los números van escritos.
    """
    # 13 → 15 en `T-7.38·F`: los dos estados de la poda del vídeo.
    # 19 → 28 en `T-7.22`: leyenda de reproducción, ausencia del mapa de red,
    # bitácora vacía, verbos sin rótulo y los cinco del reporte de daños.
    # 28 → 30 en `T-7.25`: las dos caras de la línea de fuentes externas (la que
    # declara que no consta y la que dice por qué el SSN no se consulta).
    # 30 → 31 al revisar `T-7.25`: lo que el papel dice mientras la pregunta a
    # la fuente sigue en vuelo, en vez de firmar que ningún sismo publicado es
    # éste — que es lo que imprimía con la consulta sin contestar.
    # 31 → 32 en la tercera vuelta de `T-7.25`: y lo que dice cuando NO SE
    # PREGUNTÓ, que es el caso normal (la consulta se despliega apagada) y que
    # imprimía esa misma afirmación sobre el catálogo.
    # 32 → 34 en la cuarta: los hechos eran CINCO y no tres. La consulta que
    # correlacionó y el criterio de identidad de aquí que no reconoce el acierto
    # (`CORRELACION_EN_DISPUTA`, `preliminar` y `confirmado`), y el suelo de esa
    # línea para un estado que el papel no sepa traducir.
    # 34 → 40 en `T-7.24`: los seis del mapa de la sacudida — la leyenda de
    # procedencia, el `SIN COBERTURA`, y los cuatro estados del mapa (no
    # calculado todavía, calculado y sin medidas, medido y sin con qué
    # compararlo, y medido sin coordenadas con las que situarlo).
    # 40 → 46 en la 2ª vuelta de `T-7.24`: la leyenda se partió en sus cuatro
    # símbolos —disco, círculo vacío, anillo y cruz— porque describía símbolos que
    # la figura no dibuja; la frase del modelo y el residuo salió de `NO_MMI`,
    # donde se imprimía aunque el mapa estuviera sin calcular; y el snapshot que
    # no se puede LEER dejó de disfrazarse de `pendiente`.
    # 46 → 47 en la 3ª vuelta de `T-7.24`: un mapa puede modelar cada inmueble y
    # no dibujar un solo anillo —todos los niveles bajo la superficie— y eso NO es
    # el caso degradado: aquel aviso dice «ni se calcula el residuo» sobre un
    # documento que imprime el residuo ocho líneas más abajo.
    assert len(ESCENARIOS) == 47, "cambió el número de avisos declarados"
    con_variantes = [n for n, (_, v) in ESCENARIOS.items() if v]
    assert len(con_variantes) == 46, "cambió cuántos avisos se comprueban por variante"

    texto = _texto_dibujado(model(), "technical")
    assert len(texto) > 3000, (
        f"el espía solo capturó {len(texto)} caracteres del dictamen técnico: "
        "`text_of` dejó de ser el punto por el que pasa el texto y estos tests no "
        "están comprobando nada"
    )
    # Y captura texto que NO es un aviso: prueba de que ve el documento entero.
    assert "TAKAB AILERT" in texto
