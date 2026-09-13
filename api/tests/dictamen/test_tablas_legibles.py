"""[T-7.32] Las tablas del dictamen no pueden salir pintadas de negro.

MEDIDO EN EL REPORTE REAL del acto 4 (2026-09-12): las tres tablas del
documento —métricas por canal, cadena de dictámenes y la del croquis— se
imprimían como **barras negras**. Los datos estaban: `pdftotext` los saca
enteros (EHZ 0.0000 g, ENE 0.0015 g, …), pero en el papel no se ve una cifra.

La causa no está en las tablas: `_map_section` pinta el marcador del inmueble
con `set_fill_color(20, 24, 30)` —casi negro— y **nunca lo restaura**. `fpdf2`
arrastra ese color como estado del documento, así que todo lo que se rellene
después hereda el negro. El croquis es la §1: viene antes que las tres tablas.

Por eso el test no mira una tabla concreta, sino el ESTADO: en el instante en
que se abre una tabla, el color de relleno tiene que ser claro. Un elemento
nuevo que se olvide de restaurar el color vuelve a ponerlo en rojo.
"""

from __future__ import annotations

from takab_api.dictamen.layout import TakabPDF
from takab_api.dictamen.pdf import render
from tests.dictamen.test_pdf import model

#: Un relleno con esta luminancia o menos se come el texto negro de la celda.
LUMINANCIA_MINIMA = 0.6


def _luminancia(color: object) -> float:
    """Luminancia relativa aproximada del color de relleno actual de fpdf2."""
    for attr in ("colors", "rgb"):
        if hasattr(color, attr):
            r, g, b = getattr(color, attr)[:3]
            break
    else:
        # DeviceGray expone un solo canal.
        g_ = float(getattr(color, "g", 1.0))
        r, g, b = g_, g_, g_
    escala = 255.0 if max(r, g, b) > 1.0 else 1.0
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / escala


def _rellenos_al_abrir_tablas(variante: str) -> list[float]:
    vistos: list[float] = []
    original = TakabPDF.table

    def espia(self: TakabPDF, *args: object, **kwargs: object):  # noqa: ANN202
        vistos.append(_luminancia(self.fill_color))
        return original(self, *args, **kwargs)

    TakabPDF.table = espia  # type: ignore[method-assign]
    try:
        render(model(), variante)
    finally:
        TakabPDF.table = original  # type: ignore[method-assign]
    return vistos


def test_ninguna_tabla_se_abre_con_el_relleno_oscuro() -> None:
    for variante in ("technical", "executive"):
        rellenos = _rellenos_al_abrir_tablas(variante)
        oscuras = [round(x, 3) for x in rellenos if x < LUMINANCIA_MINIMA]
        assert not oscuras, (
            f"en la variante '{variante}' hay {len(oscuras)} tabla(s) que se abren con un "
            f"relleno oscuro (luminancias {oscuras}).\n"
            "  Las celdas salen como barras negras y el dato, que SÍ está en el PDF, no se\n"
            "  lee en el papel. Suele ser un `set_fill_color` de otra sección sin restaurar."
        )


def test_el_espia_NO_esta_ciego() -> None:
    """Sin esto, el test de arriba pasaría igual si no se abriera ninguna tabla."""
    assert _rellenos_al_abrir_tablas("technical"), "el render no abrió ninguna tabla"
