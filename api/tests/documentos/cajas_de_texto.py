"""[T-8.12] Dónde cae cada renglón de TEXTO y cada imagen, para medir SOLAPES.

## Por qué hacía falta, y por qué no bastaba con lo que había

`test_geometria.cajas_dibujadas` lee los operadores de DIBUJO del flujo del PDF
(rectángulos, trazos, curvas, imágenes) y mide dos bordes: el derecho y el de
abajo. Es ciego al texto a propósito —la matriz de texto de `pypdf` da dónde
EMPIEZA un fragmento, no dónde acaba—, así que **ninguna guarda del repositorio
podía ver un texto impreso encima de otro**. Es exactamente el defecto `A-050`:
con una sola fotografía, el título «15. EVACUACIÓN OBSERVADA (CCTV)» se
imprimía encima de las huellas del pie de foto, en el 100 % de los incidentes con
foto, con la suite en verde (`test_fotos_en_el_papel.py` sólo probaba 4 fotos y
sólo medía imágenes contra el pie).

## Cómo se mide: en el punto por el que pasa TODO renglón

En fpdf2 2.8.7 `cell()` y cada renglón de `multi_cell()` acaban en
`FPDF._render_styled_text_line`, y ésta, ya resuelto el salto de página, llama a
`_add_quad_points(x, y, w, h)` cuando `_record_text_quad_points` está puesto: son
la página y la caja DEFINITIVAS del renglón. Se enciende sólo durante la
llamada, se captura, y NO se llama al original (que crearía anotaciones de
resaltado). Del renglón se toma además el ANCHO DEL TEXTO, no el de la celda: un
`cell(0, …)` ocupa hasta el margen derecho aunque su texto mida 20 mm, y medir
la celda daría solapes que en el papel no existen.

Las imágenes se capturan envolviendo `FPDF.image`, que devuelve el tamaño con el
que las colocó.

⚠️ Se parchea `FPDF`, la BASE, y se restaura sobre la MISMA clase: reasignar en
una subclase le instala un atributo propio que sombrea la base para siempre
(`test_membrete_compartido.py::test_NINGUNA_subclase_sombrea_un_metodo_HEREDADO`).
"""

from __future__ import annotations

import types
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from fpdf import FPDF
from fpdf.enums import Align


@dataclass(frozen=True)
class Caja:
    """Algo impreso, en mm desde la esquina superior izquierda de su página."""

    clase: str  # "texto" | "imagen"
    pagina: int
    x0: float
    y0: float
    x1: float
    y1: float
    texto: str = ""

    def pisa(self, otra: Caja, *, tolerancia: float = 0.3) -> bool:
        """¿Se solapan más de `tolerancia` mm en LOS DOS ejes, en la misma página?

        La tolerancia no es holgura de diseño: dos renglones consecutivos se tocan
        exactamente en su borde, y el redondeo de fpdf2 los junta por centésimas.
        """
        if self.pagina != otra.pagina:
            return False
        ancho = min(self.x1, otra.x1) - max(self.x0, otra.x0)
        alto = min(self.y1, otra.y1) - max(self.y0, otra.y0)
        return ancho > tolerancia and alto > tolerancia


@dataclass
class Capturadas:
    cajas: list[Caja] = field(default_factory=list)

    @property
    def textos(self) -> list[Caja]:
        return [c for c in self.cajas if c.clase == "texto"]

    @property
    def imagenes(self) -> list[Caja]:
        return [c for c in self.cajas if c.clase == "imagen"]

    def desde(self, marca: str) -> list[Caja]:
        """Todo lo impreso a partir del primer renglón que contiene `marca`.

        Lanza si la marca no se imprimió: una rebanada vacía haría pasar en verde
        cualquier aserción de «no hay solapes».
        """
        for i, c in enumerate(self.cajas):
            if c.clase == "texto" and marca in c.texto:
                return self.cajas[i:]
        raise AssertionError(f"no se imprimió ningún renglón con {marca!r}")

    @staticmethod
    def solapes(cajas: list[Caja]) -> list[tuple[Caja, Caja]]:
        return [
            (a, b)
            for i, a in enumerate(cajas)
            for b in cajas[i + 1 :]
            if not (a.clase == "imagen" and b.clase == "imagen") and a.pisa(b)
        ]


def _ancho_del_texto(linea) -> float:  # noqa: ANN001 - fpdf.line_break.TextLine
    ancho = linea.text_width
    if not ancho:
        ancho = sum(f.get_width(initial_cs=i != 0) for i, f in enumerate(linea.fragments))
    return float(ancho)


@contextmanager
def cajas_impresas() -> Iterator[Capturadas]:
    """Captura la caja de cada renglón de texto y de cada imagen colocada."""
    cap = Capturadas()
    render_original = FPDF._render_styled_text_line
    quad_original = FPDF._add_quad_points
    image_original = FPDF.image

    # ⚠️ Una PILA y no un atributo suelto: un renglón que no cabe dispara el salto
    # de página DENTRO de `_render_styled_text_line`, y el salto dibuja el pie y la
    # cabecera —más renglones— antes de que el de fuera llegue a sus coordenadas.
    # Medido con un atributo suelto: el título «14. DAÑOS REPORTADOS EN CAMPO», que
    # abre página, no se capturaba nunca, y la rebanada entera quedaba sin marca.
    def _render(self: FPDF, text_line, *args, **kwargs):  # noqa: ANN001, ANN202
        previo = self._record_text_quad_points
        self._record_text_quad_points = True
        pila = self.__dict__.setdefault("_lineas_espiadas", [])
        pila.append([text_line, False])
        try:
            return render_original(self, text_line, *args, **kwargs)
        finally:
            pila.pop()
            self._record_text_quad_points = previo

    def _quad(self: FPDF, x: float, y: float, w: float, h: float) -> None:
        pila = self.__dict__.get("_lineas_espiadas") or []
        if not pila or pila[-1][1]:  # un resaltado de verdad, o un `text()`: no es nuestro
            return quad_original(self, x, y, w, h)
        pila[-1][1] = True
        # Las pasadas en SECO no imprimen nada: `multi_cell(dry_run=True)` y la
        # primera pasada de `table()` —que mide el alto de cada fila— renderizan con
        # `_out` desactivado. Medido: sin esto, cada cabecera de tabla aparecía dos
        # veces, la fantasma en x≈1 mm, y «pisaba» a su propia fila.
        if not isinstance(self._out, types.MethodType):
            return None
        linea = pila[-1][0]
        texto = "".join(f.string for f in linea.fragments)
        if not texto.strip():
            return None
        ancho = _ancho_del_texto(linea)
        margen = self.c_margin
        if linea.align == Align.R:
            x0 = x + w - margen - ancho
        elif linea.align in (Align.C, Align.X):
            x0 = x + (w - ancho) / 2
        elif linea.align == Align.J:
            x0, ancho = x + margen, w - 2 * margen
        else:
            x0 = x + margen
        # El alto es el de la TINTA, no el de la celda: fpdf2 centra el renglón en
        # su celda con la línea base en `y + h/2 + 0.3·cuerpo`, y el ojo de DejaVu
        # sube ~0.76 del cuerpo sobre ella y baja ~0.24. Medido con el alto de la
        # celda, el pie de página «se pisaba» a sí mismo (una celda de 3.4 mm
        # seguida de `ln(2.8)`) sin que en el papel se toque una letra con otra.
        cuerpo = max((f.font_size for f in linea.fragments), default=h)
        base = y + h / 2 + 0.3 * cuerpo
        y0, y1 = base - 0.76 * cuerpo, base + 0.24 * cuerpo
        cap.cajas.append(Caja("texto", self.page, x0, y0, x0 + ancho, y1, texto))
        return None

    def _image(self: FPDF, *args, **kwargs):  # noqa: ANN202
        info = image_original(self, *args, **kwargs)
        x = kwargs.get("x", args[1] if len(args) > 1 else None)
        y = kwargs.get("y", args[2] if len(args) > 2 else None)
        w, h = info["rendered_width"], info["rendered_height"]
        if x is not None and y is not None:
            cap.cajas.append(Caja("imagen", self.page, float(x), float(y), x + w, y + h))
        return info

    FPDF._render_styled_text_line = _render  # type: ignore[method-assign]
    FPDF._add_quad_points = _quad  # type: ignore[method-assign]
    FPDF.image = _image  # type: ignore[method-assign]
    try:
        yield cap
    finally:
        FPDF._render_styled_text_line = render_original  # type: ignore[method-assign]
        FPDF._add_quad_points = quad_original  # type: ignore[method-assign]
        FPDF.image = image_original  # type: ignore[method-assign]
