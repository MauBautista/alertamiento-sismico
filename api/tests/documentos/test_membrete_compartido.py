"""[T-7.21] Los documentos COMPARTEN cabecera y pie, y se comprueba espiándolos.

Es el «espía del render» que pide el Goal de F4. Espía `MembretePDF.text_of` —la
BASE, no `TakabPDF`— porque por ahí pasa todo lo que cualquier documento escribe:
un espía puesto sobre la subclase del dictamen no vería el reporte de simulacro,
ni la hoja en blanco, ni el informe del evento de `T-7.22`.

⚠️ **Y las otras tres suites que espían tuvieron que cambiar, aunque parecían
correctas.** Parcheaban `TakabPDF` y «restauraban» reasignando sobre la SUBCLASE,
lo que instala un atributo propio que sombrea la base **para siempre**: medido,
`'text_of' in TakabPDF.__dict__` pasa de `False` a `True` y no vuelve. Mientras
aquél era el único espía no rompía nada; en cuanto existe éste, el resultado es
«verde en aislado, rojo en la suite» — el espía general recogía CERO caracteres
según qué hubiera corrido antes. Ahora las cuatro parchean la base, y
`test_la_subclase_NO_sombrea_el_text_of_de_la_base` impide que vuelva.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from takab_api.documentos.hoja import hoja_en_blanco
from takab_api.documentos.membrete import MembretePDF
from tests.dictamen.test_pdf import model


@contextmanager
def espia() -> Iterator[list[str]]:
    """Recoge TODO lo que se escribe, venga del documento que venga."""
    visto: list[str] = []
    original = MembretePDF.text_of

    def capturado(self: MembretePDF, value: str) -> str:
        visto.append(value)
        return original(self, value)

    MembretePDF.text_of = capturado  # type: ignore[method-assign]
    try:
        yield visto
    finally:
        MembretePDF.text_of = original  # type: ignore[method-assign]


def _dictamen() -> list[str]:
    from takab_api.dictamen.pdf import render

    with espia() as visto:
        render(model())
    return visto


def _simulacro() -> list[str]:
    from takab_api.drill_report import render as render_simulacro
    from tests.api.test_drill_report import _rep

    with espia() as visto:
        render_simulacro(_rep())
    return visto


def _hoja() -> list[str]:
    with espia() as visto:
        hoja_en_blanco()
    return visto


def test_el_espia_NO_esta_ciego() -> None:
    """Si el espía dejara de recoger, todo lo de abajo pasaría por vacuidad.

    Es el patrón que ya usan las otras suites de render: el umbral no es
    decorativo, es lo que distingue «no encontró el defecto» de «no miró».
    """
    texto = "\n".join(_dictamen())
    assert len(texto) > 1000, f"el espía sólo recogió {len(texto)} caracteres"


@pytest.mark.parametrize(
    "documento",
    [
        pytest.param(_dictamen, id="dictamen"),
        pytest.param(_simulacro, id="reporte-de-simulacro"),
        pytest.param(_hoja, id="hoja-en-blanco"),
    ],
)
def test_todo_papel_lleva_el_MISMO_membrete(documento) -> None:
    """La identidad, la franja y la paginación, vengan del documento que vengan."""
    visto = documento()
    texto = "\n".join(visto)
    assert "TAKAB AILERT" in texto, "un papel sin el nombre de quien lo firma"
    assert "EVIDENCIA INMUTABLE" in texto
    assert any(v.startswith("SHA-256 DEL CONTENIDO") or "SIN HUELLA" in v for v in visto), (
        "el pie no dice ni la huella ni su ausencia"
    )


def test_cada_documento_DECLARA_su_tipo() -> None:
    """Dos papeles distintos no pueden parecer el mismo en el pie."""
    from takab_api.dictamen.layout import TakabPDF
    from takab_api.documentos.hoja import _Hoja
    from takab_api.drill_report import ReportePDF

    tipos = {TakabPDF.tipo, ReportePDF.tipo, _Hoja.tipo}
    assert len(tipos) == 3, f"dos documentos comparten rótulo de tipo: {tipos}"
    # ⚠️ Esto encontró un defecto vivo: el reporte de simulacro usaba `TakabPDF` y
    # su pie decía «DICTAMEN», que es falso — un simulacro no dictamina la
    # habitabilidad de nada. Ninguna prueba de `drill_report` miraba el pie.
    assert "DICTAMEN" in "\n".join(_dictamen())
    assert "REPORTE DE SIMULACRO" in "\n".join(_simulacro())
    assert "HOJA EN BLANCO" in "\n".join(_hoja())


def test_la_hoja_en_blanco_NO_afirma_datos() -> None:
    """Un papel sin contenido no puede llevar una huella de contenido.

    Sería una firma sobre nada: el hash de un documento vacío verifica que el
    vacío no cambió, que no es lo mismo que respaldar un dato.
    """
    visto = _hoja()
    assert any("SIN HUELLA DE CONTENIDO" in v for v in visto)
    assert not any("SHA-256 DEL CONTENIDO" in v for v in visto)


def test_el_sellado_de_la_hoja_NO_es_el_reloj() -> None:
    """Si lo fuera, el artefacto comiteado cambiaría cada día y `make drift`
    pasaría a ser ruido que todo el mundo aprende a ignorar."""
    from takab_api.documentos.hoja import SELLO_DE_LA_HOJA

    assert SELLO_DE_LA_HOJA < datetime.now(tz=UTC)
    assert hoja_en_blanco() == hoja_en_blanco()


def test_la_subclase_NO_sombrea_el_text_of_de_la_base() -> None:
    """La guarda del defecto de arriba, y la razón de que exista.

    Si alguien vuelve a parchear `TakabPDF.text_of` y a «restaurarlo»
    reasignando, la subclase se queda con un atributo propio y el espía general
    deja de ver nada — **en silencio y sólo según el orden de la suite**, que es
    la peor forma de fallar. Esto lo caza en cualquier orden.
    """
    from takab_api.dictamen.layout import TakabPDF
    from takab_api.documentos.hoja import _Hoja
    from takab_api.drill_report import ReportePDF

    for clase in (TakabPDF, ReportePDF, _Hoja):
        assert "text_of" not in clase.__dict__, (
            f"{clase.__name__} define su propio `text_of` y sombrea al membrete: "
            "algún espía parcheó la subclase en vez de la base"
        )
