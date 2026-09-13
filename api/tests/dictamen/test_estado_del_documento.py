"""[T-7.33] Un dictamen FIRMADO no puede llamarse PRELIMINAR en su propia página.

MEDIDO EN EL REPORTE REAL del acto 4 (2026-09-13, tras firmar el inspector): el
banner decía «OPERACIÓN NORMAL · DICTAMEN FIRMADO», la §9 traía la fila
`FIRMADO` sucediendo a la preliminar y la §14 nombraba a quien firmó… y el
encabezado de **las cuatro páginas** seguía diciendo «DICTAMEN OPERATIVO
PRELIMINAR», y el deslinde de la §14, justo debajo del «FIRMÓ», repetía
«Dictamen operativo PRELIMINAR». El mismo papel se contradecía dos veces.

En un documento con peso legal eso no es una errata: es la clase de detalle que
un perito o una aseguradora usan para discutir qué documento estaban leyendo.

Las dos cadenas estaban escritas a fuego mientras el banner y la tabla SÍ se
derivaban del dato. Este test fija que el ESTADO del documento salga de si hay
firma, en los dos sitios que lo dicen con palabras.
"""

from __future__ import annotations

from takab_api.dictamen.layout import TakabPDF
from takab_api.dictamen.model import DictamenRow
from takab_api.dictamen.pdf import render
from tests.dictamen.test_pdf import _OPENED, model

FIRMANTE = "a13b3590-4081-70ae-7d34-ce050f960bda"


def _texto(m, variante: str = "technical") -> str:
    """Lo que el render pasó por `text_of`, que es por donde va el texto."""
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


def _firmado():
    # `verdict_signed` es campo propio del modelo (lo lee la prosa) y la cadena de
    # dictámenes es lo que pinta la §9: un documento firmado trae las dos cosas.
    return model(
        verdict_signed=True,
        verdict_status="normal_operation",
        dictamens=[
            DictamenRow("d-2", "normal_operation", _OPENED, FIRMANTE, "", "d-1"),
            DictamenRow("d-1", "inhabit_monitor", _OPENED, None, "dictamen-v1", None),
        ],
    )


def test_el_encabezado_de_un_dictamen_FIRMADO_no_dice_preliminar() -> None:
    texto = _texto(_firmado())
    encabezados = [ln for ln in texto.splitlines() if ln.startswith("DICTAMEN OPERATIVO")]
    assert encabezados, "el documento perdió su encabezado de estado"
    assert all("PRELIMINAR" not in ln for ln in encabezados), (
        f"el encabezado de un dictamen firmado sigue diciendo PRELIMINAR: {encabezados[0]!r}.\n"
        "  La misma página lleva el banner «DICTAMEN FIRMADO» — el papel se contradice."
    )
    assert any("FIRMADO" in ln for ln in encabezados), encabezados[0]


def test_el_deslinde_de_un_dictamen_FIRMADO_no_lo_llama_preliminar() -> None:
    texto = _texto(_firmado())
    deslinde = [ln for ln in texto.splitlines() if "No sustituye la evaluación" in ln]
    assert deslinde, "desapareció el deslinde de la §14"
    assert "PRELIMINAR" not in deslinde[0], (
        f"el deslinde llama PRELIMINAR a un dictamen firmado: {deslinde[0]!r}"
    )


def test_sin_firma_el_documento_SIGUE_declarandose_preliminar() -> None:
    """El control negativo: la palabra no se ha borrado, se ha hecho derivada."""
    texto = _texto(model())  # el modelo base no lleva firma
    assert "DICTAMEN OPERATIVO PRELIMINAR" in texto
    deslinde = [ln for ln in texto.splitlines() if "No sustituye la evaluación" in ln]
    assert deslinde and "PRELIMINAR" in deslinde[0], deslinde


def test_la_fila_PRELIMINAR_de_la_cadena_sigue_estando() -> None:
    """Lo que NO puede pasar: que 'preliminar' desaparezca de la §9.

    La cadena de dictámenes es histórica — la fila preliminar a la que sucede la
    firmada tiene que seguir ahí, o se pierde qué se corrigió.
    """
    assert "PRELIMINAR" in _texto(_firmado())


def _resumen_de(m) -> str:
    """El resumen ejecutivo tal como lo compone el proveedor determinista.

    No se saca del render: la prosa entra al PDF como dato ya construido, así que
    el sitio donde se decide qué dice es éste.
    """
    from takab_api.narrative.deterministic import sections_for  # noqa: PLC0415
    from takab_api.narrative.redact import facts_from  # noqa: PLC0415

    return dict(sections_for(facts_from(m)))["Resumen ejecutivo"]


def test_el_resumen_ejecutivo_no_se_contradice_a_si_mismo() -> None:
    """El mismo párrafo decía «firmado por un inspector» y, dos frases después,
    «este documento es preliminar». Lo segundo estaba escrito a fuego."""
    resumen = _resumen_de(_firmado())
    assert "firmado por un inspector" in resumen
    assert "es preliminar" not in resumen, f"el resumen se contradice: {resumen!r}"
    assert "no sustituye una evaluación estructural formal" in resumen


def test_sin_firma_el_resumen_SIGUE_diciendo_preliminar() -> None:
    """Control negativo: la frase no se borró, se hizo derivada."""
    resumen = _resumen_de(model())
    assert "sin firma de inspector todavía" in resumen
    assert "Este documento es preliminar" in resumen


def _seccion(m, titulo: str) -> str:
    """Una sección de la prosa, tal como la compone el proveedor determinista."""
    from takab_api.narrative.deterministic import sections_for  # noqa: PLC0415
    from takab_api.narrative.redact import facts_from  # noqa: PLC0415

    return dict(sections_for(facts_from(m)))[titulo]


def test_las_limitaciones_no_llaman_automatico_a_un_dictamen_FIRMADO() -> None:
    """La cuarta, y la peor colocada: es donde el lector busca las salvedades.

    Llamar «preliminar y automático» a un veredicto que acaba de firmar una
    persona contradice la firma en la sección que existe para matizarla.
    """
    limitaciones = _seccion(_firmado(), "Limitaciones y datos ausentes")
    assert "preliminar y automático" not in limitaciones, limitaciones
    assert "lo firmó un inspector" in limitaciones
    # Lo que NO cambia: el alcance de la medición, que es el motivo de la sección.
    assert "no localiza sismos" in limitaciones


def test_sin_firma_las_limitaciones_SIGUEN_diciendo_automatico() -> None:
    assert "Este dictamen es preliminar y automático." in _seccion(
        model(), "Limitaciones y datos ausentes"
    )


# ---------------------------------------------------------------------------
# LA GUARDA: la que habría cazado las cuatro de una vez
# ---------------------------------------------------------------------------


def _frases_con_preliminar(m) -> list[str]:
    """Frases del documento que contienen «preliminar», en sus DOS fuentes.

    El barrido tiene que mirar las dos o no sirve: lo que dibuja el PDF (el
    encabezado, el deslinde) y la PROSA, que entra al documento ya compuesta por
    el proveedor de narrativa y no pasa por el render en las pruebas. Dos de las
    cuatro apariciones vivían justo ahí.

    Se descarta la palabra SUELTA: es el estado de la fila superada en la §9.
    """
    corpus = _texto(m).splitlines()
    from takab_api.narrative.deterministic import sections_for  # noqa: PLC0415
    from takab_api.narrative.redact import facts_from  # noqa: PLC0415

    for _, cuerpo in sections_for(facts_from(m)):
        corpus.extend(cuerpo.splitlines())
    return [
        linea
        for linea in corpus
        if "preliminar" in linea.lower() and linea.strip().upper() != "PRELIMINAR"
    ]


def test_en_un_documento_FIRMADO_la_palabra_preliminar_solo_sobrevive_como_HISTORIA() -> None:
    """Cuatro sitios distintos llamaban PRELIMINAR a un dictamen firmado, y se
    encontraron **de uno en uno**, regenerando el PDF cuatro veces.

    Esta es la afirmación que los habría cazado juntos: en un documento firmado,
    ninguna FRASE puede contener «preliminar». La palabra suelta sí sobrevive —es
    el ESTADO de la fila superada en la cadena de dictámenes de la §9, y esa fila
    es historia: dice qué se corrigió—, así que se permite exactamente como
    celda, y nada más.
    """
    frases = _frases_con_preliminar(_firmado())
    assert not frases, (
        "un documento FIRMADO se llama preliminar a sí mismo en "
        f"{len(frases)} sitio(s):\n  - " + "\n  - ".join(f[:110] for f in frases)
    )


def test_la_guarda_NO_esta_ciega() -> None:
    """Sin firma, esas frases TIENEN que estar: si no, la de arriba no afirma nada."""
    frases = _frases_con_preliminar(model())
    assert frases, "sin firma el documento debería declararse preliminar y no lo hace"
