"""[T-7.21] MembretePDF: el membrete que lleva todo papel que sale del sistema.

Promoción de lo que era `dictamen/layout.py::TakabPDF`. Lo hereda el dictamen
pericial, el reporte de simulacro y el informe del evento (`T-7.22`).

Todo el dibujo sale de fpdf2 —``line``, ``rect``, ``polyline``, ``circle``,
``table``— sin rasterizar más que el logotipo. Un vector pesa menos, no pixela al
imprimir y, sobre todo, es DETERMINISTA byte a byte: el sha256 del documento es
lo que lo hace evidencia.

**Determinismo**: fpdf2 estampa ``/CreationDate`` con el reloj. Sin fijarlo, dos
generaciones del mismo modelo darían hashes distintos y la promesa de «verifique
el sha256» sería falsa. ``seal`` lo fija a un instante del propio suceso.

## Tres decisiones de esta ficha, con su razón

**1 · La geometría se DERIVA de fpdf2, no se teclea.** `PAGE_W`/`CONTENT_W` eran
constantes de módulo paralelas a las de fpdf2 (`w`/`epw`), y las dos fuentes
podían divergir sin que nada las cruzara — de hecho ya divergían: el A4 de fpdf2
mide 210.0016 mm y la constante decía 210.0. A escala invisible, pero el
mecanismo es el que arruina una migración de formato hecha a medias: las tablas
usan `epw` y los filetes usaban la constante, así que cambiar sólo el formato
dibujaba las tablas 5.9 mm FUERA de su propio marco, en todas las páginas y con
la suite en verde. Ahora las dos salen de `PAGE_FORMATS`, que es de dónde las
saca fpdf2, y `tests/documentos/test_geometria.py` las cruza.

**2 · El pie se reparte POR ARITMÉTICA, no por gusto.** La ficha de `T-7.21`
pedía identidad, tipo, folio, fecha, `build`, paginación y sha256 — el `build`
salió después, medido, y su razón es la decisión 4. Sobre la banda útil de Carta
(185.9 mm) con el peor folio real: identidad 114.5 mm, paginación 15.5, sha256
118.7 (mono 6.5), evento 39.0, aviso de tipografía degradada 63.8.
Las dos primeras caben emparejadas y las dos siguientes también; el aviso de
degradada no cabe con ninguna, así que ocupa su propio renglón **y sólo cuando
hace falta**. ⚠️ `cell()` de fpdf2 **no envuelve**: lo que sobra se dibuja encima
de lo de al lado sin poner nada en rojo. Truncar el hash no es opción — `T-5.26`
existe justo porque los sha salían a 32 de 64 caracteres.

**3 · La fecha del pie es la SELLADA, nunca la de generación.** `generated_at`
del dictamen es `datetime.now(tz=UTC)` (`routers/reports.py`), así que imprimirla
haría que dos generaciones del mismo modelo dieran archivos distintos. El pie
lleva el instante del SUCESO —el mismo que recibe `seal()`— y por eso su rótulo
dice «EVENTO», no «generado el»: no es lo mismo y el papel no puede insinuarlo.

**4 · [T-7.42] El `build` NO entra en el pie.** Se evaluó y se descartó, y éstas
son las medidas, para que no se re-decida a ciegas:

* **No cabría con garantía.** La celda del sello mide 62 mm y «EVENTO … UTC»
  ocupa 38.97. Un build de 9 caracteres cabe (61.81); uno de 10 se pisa (63.32);
  el sha entero pide 108.73. Y lo que lo alimentaría es `git rev-parse --short
  HEAD` —así lo inyecta `deploy/cloud/deploy.sh` en `TAKAB_API_BUILD_SHA`—, cuyo
  largo **git alarga solo** a medida que el repositorio crece. Sería un
  desbordamiento esperando a que haya commits, y `cell()` no envuelve: se
  dibujaría encima de la huella.
* **Dejaría inverificable evidencia ya registrada.** El reporte de simulacro se
  guarda bajo una clave FIJA —`evidence/<tenant>/drills/<id>/reporte.pdf`— y
  cada exportación inserta una fila nueva con el sha256 del archivo. Medido: hoy
  dos exportaciones del mismo simulacro dan los MISMOS bytes. Con el build
  dentro, la primera exportación posterior a un despliegue sobrescribiría el
  objeto y dejaría a todas las filas anteriores citando un sha256 que ya no casa
  con lo que hay en esa clave. Por la regla de oro 11 esas filas no se podan
  nunca: se quedarían ahí, apuntando a nada verificable.
* **La trazabilidad del binario ya existe, y no viaja en el papel.** `/health`
  publica `build`, y `test_gate_despliegue_nube` juzga con él si lo desplegado es
  lo que el repositorio dice.
* **Y en la demostración valdría `unknown`.** `build_sha` sólo lo inyecta el
  despliegue de nube. Un dictamen pericial que imprima «build unknown» afirma
  menos que uno que no lo mencione.

Por eso `__init__` ya **no acepta `build=`**. Aceptar un parámetro que nadie pasa
es exactamente la forma del defecto que esta ficha vino a cerrar —`huella=`
llevaba así desde `T-7.21`, y el pie de todos los dictámenes decía «ESTE
DOCUMENTO NO AFIRMA DATOS» mientras su portada imprimía el hash—, así que dejar
el segundo armado al lado del primero sería no haber aprendido nada.

Si algún día se revoca: la aritmética de arriba hay que rehacerla entera. La
celda del sello tendría que crecer y la de la huella encoger, y la de la huella
sólo tiene **5.2 mm** de holgura (5.6 con las fuentes core).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fpdf import PAGE_FORMATS

from takab_api.documentos.identidad import TAKAB

_ARTE = Path(__file__).parent

#: [T-6.33] El logotipo de la cabecera, en su variante POSITIVA. Es el único
#: destino de la marca en positivo del repo, y no es un capricho: éste es el
#: único PAPEL BLANCO que el producto entrega, y va firmado. Sobre blanco, la
#: variante negativa —la de la consola, el panel y la app— se perdería.
#: Lo deriva `shared/brand/generar.py`; aquí no se edita.
LOGOTIPO = _ARTE / "marca" / "logotipo.png"
_FONTS = _ARTE / "fonts"

#: Ancho impreso de la marca, en mm.
_LOGO_MM = 34.0

#: [T-7.21] CARTA, y derivada de la tabla de fpdf2 en vez de tecleada. Es el
#: tamaño de papel de oficina en México, que es donde se imprime este documento.
_PT_A_MM = 25.4 / 72.0
_FORMATO = "letter"
PAGE_W = round(PAGE_FORMATS[_FORMATO][0] * _PT_A_MM, 4)
PAGE_H = round(PAGE_FORMATS[_FORMATO][1] * _PT_A_MM, 4)

MARGIN = 15.0
CONTENT_W = round(PAGE_W - 2 * MARGIN, 4)

#: Altos de los renglones del pie, en mm, EN ORDEN. De aquí sale la reserva:
#: era un `20.0` tecleado que había que recordar subir a mano cada vez que el
#: pie ganaba una línea, y el pie acaba de ganar dos (`T-7.21`, el emisor legal).
#: Un número paralelo al contenido que describe es el mecanismo que ya arruinó
#: la migración de formato de esta misma ficha.
_PIE_RENGLONES = (
    3.6,  # identidad de producto · tipo · folio · franja  +  paginación
    3.4,  # SHA-256 del contenido  +  sello del evento
    2.8,  # [T-7.21] razón social
    2.8,  # [T-7.21] domicilio
)
#: El aviso de tipografía degradada va aparte: sólo aparece cuando hace falta,
#: pero la reserva tiene que contemplarlo SIEMPRE o el día que aparezca se sale.
_PIE_DEGRADADA = 3.4
#: Aire bajo el último renglón. No es estética: por debajo de ~5 mm una
#: impresora de oficina recorta.
_PIE_AIRE = 6.0
#: Separación entre el filete del pie y su primer renglón.
_PIE_TRAS_FILETE = 1.0

#: Alto que el pie reserva. `set_auto_page_break(margin=…)` marca el corte por
#: debajo del cual fpdf2 salta de página SOLO para texto: `rect` y `polyline` no
#: lo disparan, y de ahí `reserva()`.
PIE_MM = round(_PIE_TRAS_FILETE + sum(_PIE_RENGLONES) + _PIE_DEGRADADA + _PIE_AIRE, 4)
#: La y donde el cuerpo empieza en cada página, bajo el filete de cabecera.
CUERPO_Y = 32.0
#: La y del filete de la cabecera.
_FILETE_Y = 26.0

#: Anchos de las dos columnas derechas del pie, en mm. Medidos sobre el peor
#: caso real («Pág. 9 de 99» y «EVENTO … UTC»), no elegidos.
#:
#: ⚠️ [T-7.42] Los 62 mm del sello se midieron cuando el peor caso incluía un
#: `build`, que ya no existe (decisión 4). NO se encogen a los 39 que hoy bastan:
#: la celda va alineada a la derecha, así que la holgura no se ve, y encogerla
#: movería los bytes de TODO documento —incluida la hoja comiteada de
#: `shared/brand/membrete`— a cambio de nada. Lo que no puede es CRECER: la celda
#: de la huella es lo que queda, y sólo le sobran 5.2 mm.
_ANCHO_PAGINA = 18.0
_ANCHO_SELLO = 62.0

#: Lo que el pie dice cuando la tipografía Unicode no viajó. Ocupa su propio
#: renglón: medido, no cabe emparejado con ninguna de las otras dos líneas.
AVISO_DEGRADADA = "TIPOGRAFÍA DEGRADADA (fuente Unicode ausente)"

#: Paleta del documento. Sobria a propósito: un dictamen no es un tablero.
#: ⚠️ `INK`/`MUTED`/`RULE` son tintas de PAPEL y no salen de `shared/brand`:
#: aquélla es la paleta de PANTALLA (`NAVY` #0B1D3A sobre fondo oscuro) y este
#: es el único soporte blanco que entrega el producto. Un navy de marca sobre
#: blanco da un gris azulado que no es el negro de un documento impreso. Se
#: declara aquí en vez de heredarse mal.
INK = (20, 24, 30)
MUTED = (110, 120, 132)
RULE = (200, 206, 214)


class MembretePDF(FPDF):
    """Carta con cabecera, pie paginado y tipografía Unicode.

    ``degraded`` queda en ``True`` si las fuentes vendorizadas no viajaron en la
    imagen: el documento se genera igual con las core de fpdf2 y lo DECLARA en el
    pie. Una exportación de evidencia no puede fallar por tipografía, pero
    tampoco puede perder un carácter en silencio.
    """

    #: Rótulo del tipo de documento en el pie. Lo fija cada subclase.
    tipo: str = "DOCUMENTO"

    #: [T-7.42] ¿Este documento AFIRMA datos? Decide qué dice su pie: el que
    #: afirma imprime su huella de contenido; el que no, declara la ausencia.
    #:
    #: Viaja con la clase —como `tipo`— y no en una lista de exentos, porque una
    #: lista de exentos crece y acaba tapando justo lo que el censo vigila. Lo
    #: cruza `test_el_pie_NO_contradice_al_CUERPO` contra el render REAL de cada
    #: documento: una subclase nueva sin declararlo pone la suite en rojo.
    afirma_datos: bool = True

    def __init__(
        self,
        folio: str,
        subtitle: str,
        *,
        sellado: datetime | None = None,
        huella: str | None = None,
    ) -> None:
        super().__init__(format=_FORMATO.capitalize())
        self.folio = folio
        self.subtitle = subtitle
        #: El instante del SUCESO, el mismo que recibe `seal()`. No es la hora de
        #: generación: ver la decisión 3 del módulo.
        self.sellado = sellado
        #: Huella del CONTENIDO (no del archivo: no cabe dentro de sí mismo).
        #: `None` es legítimo —una hoja en blanco no tiene contenido— y se
        #: DECLARA en el pie en vez de dejar un hueco mudo.
        self.huella = huella
        self.degraded = False
        # Misma regla que la tipografía: si el arte no viajó con el paquete el
        # documento SALE IGUAL, con la palabra compuesta. Una exportación de
        # evidencia no puede caerse por un adorno.
        self.sin_marca = not LOGOTIPO.exists()
        self.set_margins(MARGIN, 18, MARGIN)
        self.set_auto_page_break(auto=True, margin=PIE_MM)
        self._install_fonts()
        self.alias_nb_pages()

    def _install_fonts(self) -> None:
        try:
            self.add_font("dejavu", "", str(_FONTS / "DejaVuSans.ttf"))
            self.add_font("dejavu", "B", str(_FONTS / "DejaVuSans-Bold.ttf"))
            self.add_font("dejavumono", "", str(_FONTS / "DejaVuSansMono.ttf"))
            self.body_font = "dejavu"
            self.mono_font = "dejavumono"
        except (FileNotFoundError, RuntimeError):
            self.degraded = True
            self.body_font = "helvetica"
            self.mono_font = "courier"

    def text_of(self, value: str) -> str:
        """Con fuentes core hay que degradar a latin-1; con DejaVu pasa todo."""
        if not self.degraded:
            return value
        return value.encode("latin-1", "replace").decode("latin-1")

    # --- chasis ---------------------------------------------------------------

    def header(self) -> None:  # noqa: D102 - contrato de fpdf2
        if self.sin_marca:
            # Respaldo: la palabra compuesta con la tipografía del documento.
            self.set_font(self.body_font, "B", 9)
            self.set_text_color(*INK)
            self.cell(0, 5, self.text_of("TAKAB AILERT"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            # `x`/`y` explícitos: `header()` corre en CADA página y el cursor no
            # llega aquí en el mismo sitio en todas. fpdf2 embebe el PNG una sola
            # vez y lo reutiliza, así que repetirlo no engorda el documento.
            self.image(str(LOGOTIPO), x=MARGIN, y=10, w=_LOGO_MM)
            self.set_y(20)
        self.set_font(self.body_font, "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 4, self.text_of(self.subtitle), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*RULE)
        self.line(MARGIN, _FILETE_Y, PAGE_W - MARGIN, _FILETE_Y)
        self.set_y(CUERPO_Y)
        self.set_text_color(*INK)

    #: [T-7.21] ¿El pie lleva el emisor legal? La hoja membretada en blanco lo
    #: apaga: ya imprime los CUATRO datos en el cuerpo, que es su razón de ser,
    #: y repetir dos de ellos abajo sería ruido en el único papel cuyo cuerpo
    #: está vacío a propósito.
    emisor_en_pie = True

    def footer(self) -> None:  # noqa: D102 - contrato de fpdf2
        """El membrete, repartido en líneas POR ARITMÉTICA.

        Medido sobre la banda útil de Carta (185.9 mm) con el peor folio real:

            identidad · tipo · folio · franja  114.5 mm   +  paginación  15.5
            SHA-256 del contenido               118.7 mm   +  evento       39.0
            tipografía degradada                 63.8 mm

        Las dos primeras caben emparejadas; la tercera no cabe con ninguna, y por
        eso sólo aparece cuando hace falta. ⚠️ `cell()` de fpdf2 **no envuelve**:
        lo que no cabe se dibuja encima de lo de al lado sin poner nada en rojo,
        así que esto no es una preferencia de diseño — es la única forma de que
        el pie no se pise a sí mismo. Lo vigila `test_el_pie_CABE_en_su_celda`.
        """
        # Derivado, no tecleado: el filete va 1 mm por debajo del corte de
        # página. Era `set_y(-19)` contra un `PIE_MM = 20.0`, dos números que
        # había que mover juntos y a mano.
        self.set_y(-(PIE_MM - _PIE_TRAS_FILETE))
        self.set_draw_color(*RULE)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.ln(_PIE_TRAS_FILETE)
        self.set_font(self.body_font, "", 7)
        self.set_text_color(*MUTED)
        # [T-6.33] El NOMBRE, en texto y en todas las páginas. La cabecera lleva
        # el logotipo como arte, y un lector de pantalla —o un `pypdf` de la
        # contraparte que revisa el dictamen— no lee un PNG. En un documento
        # firmado, de quién es la firma no puede vivir sólo en una imagen.
        self.cell(CONTENT_W - _ANCHO_PAGINA, 3.6, self.text_of(self._linea_identidad()))
        self.cell(_ANCHO_PAGINA, 3.6, f"Pág. {self.page_no()} de {{nb}}", align="R")
        self.ln(3.6)

        # La huella del CONTENIDO, entera. Truncarla es el defecto que `T-5.26`
        # arregló: un sha a medias no verifica nada.
        self.set_font(self.mono_font, "", 6.5)
        self.cell(
            CONTENT_W - _ANCHO_SELLO,
            3.4,
            self.text_of(self._linea_huella()),
        )
        self.set_font(self.body_font, "", 7)
        self.cell(_ANCHO_SELLO, 3.4, self.text_of(self._sello()), align="R")

        # [T-7.21 · PENDIENTES §4.8] QUIÉN EMITE, en letra de pie y en todas las
        # páginas. Hasta hoy el papel que se lleva el cliente sólo decía «TAKAB
        # AILERT», que es la marca del producto, no la persona moral que
        # responde de lo que el documento afirma. Un dictamen pericial sin
        # emisor legal es un papel que nadie ha firmado.
        #
        # ⚠️ DOS RENGLONES, y es aritmética, no gusto: medido a 7 pt sobre la
        # banda útil de 185.9 mm, la razón social ocupa 117.0 mm y el domicilio
        # 117.3 — cada una cabe sola, juntas suman 236.7 y `cell()` no envuelve.
        # A 6 pt son 100.3 y 100.6: el tamaño de letra chica de pie es el que
        # deja holgura de sobra en el peor caso.
        #
        # La CLASIFICACIÓN no baja al pie a propósito: hoy vale «USO INTERNO» y
        # estamparla en un dictamen que se entrega a un tercero diría de ese
        # papel lo contrario de lo que es.
        if self.emisor_en_pie:
            self.set_font(self.body_font, "", 6)
            for texto in self._lineas_emisor():
                self.ln(2.8)
                self.cell(0, 2.8, self.text_of(texto))

        if self.degraded:
            # No se calla: un dictamen al que le faltan caracteres tiene que
            # decirlo, y no cabe emparejado con nada. Su propia línea.
            self.ln(3.4)
            self.set_font(self.body_font, "", 7)
            self.cell(0, 3.4, self.text_of("TIPOGRAFÍA DEGRADADA (fuente Unicode ausente)"))

    def _lineas_emisor(self) -> tuple[str, ...]:
        """Razón social y domicilio, o nada si aún no se supieran.

        Devuelve sólo lo que se SABE: si un día se revoca un dato y vuelve a
        `None`, el pie no imprime `PENDIENTE` —ese trabajo es del bloque de
        emisor de la hoja membretada, que tiene sitio para explicarlo—, se
        calla esa línea y el aviso sigue estando donde se puede leer entero.
        """
        return tuple(v for v in (TAKAB.razon_social, TAKAB.domicilio) if v)

    def _linea_identidad(self) -> str:
        """Quién firma, qué tipo de papel es y su folio. En TODAS las páginas."""
        return f"TAKAB AILERT · {self.tipo} · {self.folio} · EVIDENCIA INMUTABLE"

    def _linea_huella(self) -> str:
        """La huella del contenido, o su ausencia DECLARADA."""
        if self.huella:
            return f"SHA-256 DEL CONTENIDO {self.huella}"
        return "SIN HUELLA DE CONTENIDO · ESTE DOCUMENTO NO AFIRMA DATOS"

    def _sello(self) -> str:
        """El instante del SUCESO. Nada más — ver la decisión 4 del módulo.

        `EVENTO` y no «generado el»: es el instante que recibe `seal()` —el del
        incidente o el del arranque del simulacro—, no la hora de impresión. La
        diferencia no es pedante: `generated_at` es `datetime.now()`, y meterlo
        aquí haría que dos generaciones del mismo modelo dieran archivos
        distintos, con lo que «verifique el sha256» dejaría de ser cierto.

        Vacío cuando no hay instante sellado, y vacío es lo correcto: una hoja en
        blanco no es de ningún suceso, y ponerle una fecha sería inventarle uno.
        """
        if self.sellado is None:
            return ""
        return f"EVENTO {self.sellado:%Y-%m-%d %H:%M} UTC"

    def seal(self, created_at) -> None:
        """Metadatos fijos ⇒ mismas entradas, mismos bytes (y mismo sha256)."""
        self.set_creation_date(created_at)
        self.set_producer("TAKAB Ailert")
        self.set_creator("takab-api")
        self.set_title(self.folio)

    # --- primitivas de contenido ---------------------------------------------

    def reserva(self, alto: float) -> None:
        """Salta de página si `alto` mm no caben bajo el cursor.

        ⚠️ **fpdf2 no hace esto solo para el dibujo.** `set_auto_page_break` sólo
        mira el texto; `rect`, `line` y `polyline` se pintan donde se les diga,
        incluso encima del filete del pie.

        [T-7.44] Las cinco figuras del dictamen —la traza, la duración, el
        espectro, el espectrograma y el croquis— **ya pasan por aquí**. Hasta
        entonces cuatro decidían con un número absoluto calibrado a ojo contra el
        corte de A4, que la migración a Carta dejó ciego sin que nada avisara (la
        hoja se acortó 17,6 mm y ninguno se movió); y el croquis, que es la caja
        más alta del documento con sus 78 mm, no tenía ni eso. Que no vuelva a
        aparecer un tope absoluto lo vigila un censo por AST sobre todo
        `api/src/takab_api`, en `tests/documentos/test_geometria.py`.
        """
        if self.get_y() + alto > PAGE_H - PIE_MM:
            self.add_page()

    def section(self, number: str, title: str) -> None:
        self.ln(3)
        self.set_font(self.body_font, "B", 10)
        self.set_text_color(*INK)
        self.cell(0, 6, self.text_of(f"{number}. {title}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*RULE)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.ln(2)

    def para(self, text: str, *, size: float = 8.5, muted: bool = False) -> None:
        self.set_font(self.body_font, "", size)
        self.set_text_color(*(MUTED if muted else INK))
        self.multi_cell(0, 4.4, self.text_of(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*INK)

    def field(self, label: str, value: str) -> None:
        self.set_font(self.body_font, "", 8)
        self.set_text_color(*MUTED)
        self.cell(52, 4.8, self.text_of(label))
        self.set_font(self.mono_font, "", 8)
        self.set_text_color(*INK)
        # ⚠️ [T-7.21] `align="L"` EXPLÍCITO: `multi_cell` justifica por defecto
        # (`Align.J`). Nadie lo había visto porque ningún valor había envuelto
        # jamás —los cuatro medían los 36 caracteres de `PENDIENTE`—, y el
        # primero que envuelve es el domicilio real: fpdf2 repartía los 9.6 mm
        # sobrantes entre sus 9 espacios y cada uno pasaba de 1.699 a 2.763 mm,
        # deformando la rejilla monoespaciada que es justo lo que hace legible
        # un dato así. Una tipografía mono justificada no es mono.
        self.multi_cell(0, 4.8, self.text_of(value), align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def callout(self, text: str, color: tuple[int, int, int] = MUTED) -> None:
        """Recuadro de AUSENCIA: por qué un dato no está, en vez de un hueco mudo."""
        self.ln(1)
        y = self.get_y()
        self.set_draw_color(*color)
        self.set_line_width(0.4)
        self.line(MARGIN, y, MARGIN, y + 8)
        self.set_line_width(0.2)
        self.set_x(MARGIN + 3)
        self.set_font(self.body_font, "", 7.5)
        self.set_text_color(*color)
        self.multi_cell(CONTENT_W - 3, 4, self.text_of(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*INK)
        self.ln(1)
