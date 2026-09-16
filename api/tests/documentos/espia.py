"""[T-7.22] El espía del render, POR SECCIÓN — y por qué es uno solo y compartido.

Del PDF no se raspa texto: el flujo va comprimido y las fuentes van subconjuntadas.
Lo que este repositorio hace desde `T-5.26` es espiar el RENDER — demostrar que la
llamada que imprime algo **se hizo** y con qué texto. Lo nuevo de `T-7.22` es
saber *en qué sección* se hizo, porque la ficha lo pide como criterio y porque un
aviso impreso en la sección equivocada es un defecto que el espía de documento
entero no puede ver.

## Por qué un helper y no un sexto espía copiado

Había cinco espías casi idénticos, cada uno con el mismo comentario de aviso
pegado encima. **Un comentario no se ejecuta.** `T-7.21` pagó exactamente eso:
los cinco parcheaban `TakabPDF` —la SUBCLASE— y «restauraban» reasignando, lo que
instala un atributo propio que sombrea la base **para siempre**; el resultado era
«verde en aislado, rojo en la suite» según qué hubiera corrido antes. Con un solo
helper la regla deja de ser prosa y pasa a ser una propiedad de UNA
implementación: nadie puede reintroducir el sombreado sin tocar el fichero que la
guarda vigila.

⚠️ **Se parchea `MembretePDF`, la BASE.** Por ahí pasa todo lo que escribe
cualquier documento: un espía sobre `TakabPDF` no vería el reporte de simulacro
ni la hoja en blanco.

## Las dos trampas que el troceo por sección tiene, y que están medidas

1. **La numeración no basta para delimitar.** El ejecutivo imprime `. QUÉ PASÓ`
   —número vacío—, así que una expresión regular sobre `^\\d+\\.` no encuentra
   allí ninguna sección. Se marca la posición **en la llamada a `section()`**,
   que es universal: la usan el dictamen, el ejecutivo y el reporte de simulacro.
2. **El membrete cae DENTRO de las rebanadas.** Cabecera y pie se dibujan al
   saltar de página, o sea en mitad de una sección; sin distinguirlos, un
   `assert "TAKAB AILERT" not in seccion` fallaría por el pie y no por la
   sección. Se marcan envolviendo `header()`/`footer()`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from takab_api.documentos.membrete import MembretePDF


@dataclass
class Capturado:
    """Lo que el render escribió, entero y troceado por sección."""

    #: Cada fragmento con su procedencia: `chrome` = cabecera o pie.
    fragmentos: list[tuple[bool, str]] = field(default_factory=list)
    #: `(indice_del_titulo, indice_del_cuerpo, numero, titulo)` por cada
    #: `section()` emitida. Son DOS índices y no uno: `section()` escribe ella
    #: misma el `«n. TÍTULO»`, así que una rebanada que empezara en el marcador
    #: contendría siempre el título y NUNCA saldría vacía — medido, así se
    #: escapaba una sección con rótulo y sin contenido, que es peor que no tener
    #: la sección porque promete un dato.
    marcadores: list[tuple[int, int, str, str]] = field(default_factory=list)

    # --- lecturas -----------------------------------------------------------

    @property
    def texto(self) -> str:
        """Todo el cuerpo, sin el membrete. Es el espía de documento completo."""
        return "\n".join(v for chrome, v in self.fragmentos if not chrome)

    @property
    def membrete(self) -> str:
        """Solo cabecera y pie, que es lo que el espía general comprueba."""
        return "\n".join(v for chrome, v in self.fragmentos if chrome)

    @property
    def numeros(self) -> list[str]:
        """Los números de sección EMITIDOS, en orden de impresión."""
        return [n for _, _, n, _ in self.marcadores]

    @property
    def titulos(self) -> list[str]:
        return [t for _, _, _, t in self.marcadores]

    def portada(self) -> str:
        """Lo escrito ANTES de la primera sección. `_cover` no llama a `section()`."""
        fin = self.marcadores[0][0] if self.marcadores else len(self.fragmentos)
        return "\n".join(v for chrome, v in self.fragmentos[:fin] if not chrome)

    def seccion(self, titulo: str) -> str:
        """El cuerpo de esa sección, sin el membrete que le cayera encima.

        Se busca por TÍTULO y no por número porque los números renumeran cuando
        se inserta una sección, y una prueba que se rompa al renumerar no está
        comprobando lo que dice comprobar. Lanza si el título no se emitió: una
        rebanada vacía haría pasar en verde todos los `not in` de quien la use,
        que es el único modo de fallo que el troceo añade sobre el espía entero.
        """
        for i, (_titulo_idx, cuerpo, _numero, t) in enumerate(self.marcadores):
            if t != titulo:
                continue
            fin = (
                self.marcadores[i + 1][0] if i + 1 < len(self.marcadores) else len(self.fragmentos)
            )
            return "\n".join(v for chrome, v in self.fragmentos[cuerpo:fin] if not chrome)
        raise AssertionError(
            f"el render NO emitió la sección {titulo!r}; emitió {self.titulos}. "
            "Una rebanada vacía dejaría pasar cualquier aserción sobre ella."
        )

    def emitio(self, titulo: str) -> bool:
        return titulo in self.titulos


@contextmanager
def espia_del_render() -> Iterator[Capturado]:
    """Recoge TODO lo que se escribe, venga del documento que venga.

    Se restaura sobre `MembretePDF` —la MISMA clase que se parcheó—, nunca sobre
    una subclase: reasignar sobre la subclase le instala un atributo propio que
    sombrea la base y no se va. Lo vigila
    `test_NINGUNA_subclase_sombrea_un_metodo_del_membrete`.
    """
    cap = Capturado()
    en_chrome = False

    text_of = MembretePDF.text_of
    section = MembretePDF.section
    header = MembretePDF.header
    footer = MembretePDF.footer

    def _text_of(self: MembretePDF, value: str) -> str:
        cap.fragmentos.append((en_chrome, value))
        return text_of(self, value)

    def _section(self: MembretePDF, number: str, title: str) -> None:
        inicio = len(cap.fragmentos)
        resultado = section(self, number, title)
        # El cuerpo empieza DESPUÉS del rótulo que `section()` acaba de escribir.
        cap.marcadores.append((inicio, len(cap.fragmentos), number, title))
        return resultado

    def _header(self: MembretePDF) -> None:
        nonlocal en_chrome
        en_chrome = True
        try:
            return header(self)
        finally:
            en_chrome = False

    def _footer(self: MembretePDF) -> None:
        nonlocal en_chrome
        en_chrome = True
        try:
            return footer(self)
        finally:
            en_chrome = False

    MembretePDF.text_of = _text_of  # type: ignore[method-assign]
    MembretePDF.section = _section  # type: ignore[method-assign]
    MembretePDF.header = _header  # type: ignore[method-assign]
    MembretePDF.footer = _footer  # type: ignore[method-assign]
    try:
        yield cap
    finally:
        MembretePDF.text_of = text_of  # type: ignore[method-assign]
        MembretePDF.section = section  # type: ignore[method-assign]
        MembretePDF.header = header  # type: ignore[method-assign]
        MembretePDF.footer = footer  # type: ignore[method-assign]
