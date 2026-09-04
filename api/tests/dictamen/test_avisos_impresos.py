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

import pytest

from takab_api.dictamen import model as modelo_mod
from takab_api.dictamen.layout import TakabPDF
from takab_api.dictamen.model import (
    CCTV_PENDIENTE,
    CCTV_SIN_CLIP,
    CctvBlock,
    ReportModel,
)
from takab_api.dictamen.pdf import render
from tests.dictamen.test_pdf import model

_VARIANTES = ("technical", "executive")


def _texto_dibujado(m: ReportModel, variante: str) -> str:
    """Todo lo que el render pasó por `text_of`, que es por donde va el texto.

    Es un espía, no una lectura del PDF: el PDF no se puede leer (ver la cabecera).
    Lo que demuestra es que la llamada que imprime el aviso SE HIZO con ese texto.
    """
    visto: list[str] = []
    original = TakabPDF.text_of

    def espia(self: TakabPDF, value: str) -> str:
        visto.append(value)
        return original(self, value)

    TakabPDF.text_of = espia  # type: ignore[method-assign]
    try:
        render(m, variante)
    finally:
        TakabPDF.text_of = original  # type: ignore[method-assign]
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
    "SKETCH_NOTE": (model, frozenset({"technical"})),
    "NO_SPECTRUM": (model, frozenset({"technical"})),
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
    # [T-5.11] Que el catálogo no tenga un sismo compatible es un HECHO sobre el
    # evento, no un fallo de búsqueda; y sin este aviso el papel deja un hueco
    # que se lee como «no pasó nada».
    "SIN_CORRELACION_EN_CATALOGO": (
        lambda: model(catalog_line=None),
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
    assert len(ESCENARIOS) == 13, "cambió el número de avisos declarados"
    con_variantes = [n for n, (_, v) in ESCENARIOS.items() if v]
    assert len(con_variantes) == 12, "cambió cuántos avisos se comprueban por variante"

    texto = _texto_dibujado(model(), "technical")
    assert len(texto) > 3000, (
        f"el espía solo capturó {len(texto)} caracteres del dictamen técnico: "
        "`text_of` dejó de ser el punto por el que pasa el texto y estos tests no "
        "están comprobando nada"
    )
    # Y captura texto que NO es un aviso: prueba de que ve el documento entero.
    assert "TAKAB AILERT" in texto
