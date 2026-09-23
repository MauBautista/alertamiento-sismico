"""[T-7.17] La red de estaciones, en el dictamen firmado.

Del PDF no se raspa texto —no se puede leer—: se **espía** `text_of`, que es el
punto por el que pasa todo lo que se dibuja. Lo que se demuestra es que la
llamada que imprime cada celda SE HIZO con ese valor.

Lo que se fija, por orden de lo que costaría equivocarse:

1. **`None` se imprime como ausencia, nunca como cero.** Un `0.0000 g` en un
   dictamen firmado afirma que la estación midió calma; no haber medido es otra
   cosa, y la diferencia importa cuando alguien defiende el documento.
2. **Sin estaciones, la sección lo DICE** en vez de quedarse vacía.
3. **El ancla de los arribos se declara en el papel**, como en la pantalla.
4. **La sección 6 y la 7 son distintas**: aquélla dice quién votó en el cuórum,
   ésta qué midió cada inmueble. En una reproducción no hay votos y la 7 es la
   única que cuenta lo que pasó en la red.
"""

from __future__ import annotations

from dataclasses import replace

from takab_api.dictamen import rotulos
from takab_api.dictamen.model import EstacionFila, ReportModel
from takab_api.dictamen.pdf import render
from takab_api.documentos.membrete import MembretePDF
from tests.dictamen.test_pdf import model

RED = [
    EstacionFila(
        site_name="Edificio Central",
        site_code="site-dev",
        sensor_code="AM.R4F74",
        dist_km=78.7,
        t_teorico_s=19.7,
        t_medido_s=20.1,
        peak_pga_g=0.0712,
        tier="evacuate_or_hold",
    ),
    EstacionFila(
        site_name="Centro Tlaxcala",
        site_code="site-sim-101",
        sensor_code=None,
        dist_km=None,
        t_teorico_s=None,
        t_medido_s=None,
        peak_pga_g=None,
        tier=None,
    ),
]


def _dibujado(m: ReportModel, variante: str = "technical") -> str:
    visto: list[str] = []
    # ⚠️ [T-7.21] Se espía la BASE `MembretePDF`, no `TakabPDF`. Parchear la
    # SUBCLASE y luego «restaurar» le instala un atributo PROPIO que sombrea la base
    # PARA SIEMPRE —medido: `'text_of' in TakabPDF.__dict__` pasa de False a True—, y
    # a partir de ahí cualquier otro espía puesto sobre el membrete recoge CERO. No
    # rompía nada mientras el único espía era éste; con el espía general de
    # `tests/documentos/test_membrete_compartido.py` sale «verde en aislado, rojo en
    # la suite». Lo vigila `test_la_subclase_NO_sombrea_el_text_of_de_la_base`.
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


def test_la_seccion_imprime_una_fila_por_estacion() -> None:
    texto = _dibujado(replace(model(), estaciones=RED, estaciones_ancla="event"))
    assert "RED DE ESTACIONES" in texto
    assert "Edificio Central (AM.R4F74)" in texto
    assert "Centro Tlaxcala" in texto
    # [T-8.12 · A-144] El nivel en castellano, con el rótulo del panel del gabinete:
    # aquí se exigía `evacuate_or_hold` CRUDO, que es el defecto que la ficha cierra.
    for celda in ("79", "19.7", "20.1", "0.0712", rotulos.NIVEL["evacuate_or_hold"]):
        assert celda in texto, celda


def test_lo_que_NO_se_midio_no_se_imprime_como_cero() -> None:
    """Un `0.0000 g` en un dictamen firmado afirma que la estación midió calma."""
    texto = _dibujado(replace(model(), estaciones=RED[1:], estaciones_ancla="event"))
    assert "Centro Tlaxcala" in texto
    assert "0.0000" not in texto
    assert "0.0 " not in texto


def test_el_ANCLA_de_los_arribos_se_declara_en_el_papel() -> None:
    con_evento = _dibujado(replace(model(), estaciones=RED, estaciones_ancla="event"))
    assert "Arribos contados desde el origen del sismo." in con_evento

    sin_evento = _dibujado(replace(model(), estaciones=RED, estaciones_ancla="incident"))
    assert "Arribos contados desde la apertura del incidente." in sin_evento


def test_sin_estaciones_la_seccion_lo_DICE() -> None:
    texto = _dibujado(replace(model(), estaciones=[]))
    assert "RED DE ESTACIONES" in texto
    assert "SIN ESTACIONES CON GABINETE ACTIVO" in texto


def test_el_cuorum_y_la_red_son_secciones_DISTINTAS() -> None:
    """Quién votó y qué midió cada uno no son la misma pregunta."""
    texto = _dibujado(replace(model(), estaciones=RED))
    assert "CORROBORACIÓN MULTI-ESTACIÓN" in texto
    assert "RED DE ESTACIONES" in texto


def test_el_espia_NO_esta_ciego() -> None:
    """Si el render fallara en silencio, todo lo de arriba pasaría por vacuidad."""
    texto = _dibujado(replace(model(), estaciones=RED))
    assert len(texto) > 2000, f"el espía solo capturó {len(texto)} caracteres"
