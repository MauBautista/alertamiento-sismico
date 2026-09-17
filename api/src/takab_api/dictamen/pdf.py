"""Render del dictamen PDF (T-1.20 · B5, reescrito en T-2.41).

Dos documentos del MISMO modelo:

- ``technical``  — pericial. Croquis, trazas, forma de onda cruda y espectro cuando hay
  miniSEED, tablas por canal, quórum, cadena de custodia y deslinde.
- ``executive``  — una o dos páginas: semáforo, qué pasó, qué significa, qué hacer.

Todo el dibujo es vectorial (``polyline``/``rect``/``circle``): pesa menos, no pixela al
imprimir y es determinista byte a byte — que es lo que hace del sha256 una promesa
cumplible.

El VEREDICTO nunca se calcula aquí. Llega en el modelo desde ``dictamen/rules.py``,
determinista y versionado; este módulo solo lo pinta.
"""

from __future__ import annotations

import io

from fpdf.enums import XPos, YPos

from takab_api.compliance import compliance_block
from takab_api.dictamen import plot, sketch
from takab_api.dictamen.bitacora import rotulo as rotulo_de_accion
from takab_api.dictamen.espectrograma import leyenda as leyenda_espectrograma
from takab_api.dictamen.layout import (
    CONTENT_W,
    INK,
    MARGIN,
    MUTED,
    RULE,
    VERDICT_COLORS,
    TakabPDF,
)
from takab_api.dictamen.model import (
    ABSENT,
    CENTROID_NOTE,
    CRONOLOGIA_SIN_ROTULO,
    DISCLAIMER,
    DISCLAIMER_ESTADO,
    ENVELOPE_NOTE,
    EPICENTRO_REUBICADO,
    EPICENTRO_REUBICADO_AQUI,
    EPICENTRO_REUBICADO_EN_LA_RED,
    FELT_LABELS,
    FOTOS_OMITIDAS,
    NARRATIVE_AI_NOTE,
    NO_CALIBRATION,
    NO_GEOMETRY,
    NO_MMI,
    NO_SPECTRUM,
    ONDA_NO_LEIDA,
    PERSONAS_EN_RIESGO,
    REPRODUCCION_NOTE,
    ROL_NO_RESUELTO,
    SIN_CATEGORIAS,
    SIN_CORRELACION_EN_CATALOGO,
    SIN_CRONOLOGIA,
    SIN_DANOS,
    SIN_GEOMETRIA_DE_RED,
    SKETCH_NOTE,
    STATUS_ACTIONS,
    STATUS_LABELS,
    TS_FMT,
    ReportModel,
    cierre_text,
    disparo_line,
    huella_de_custodia,
    lead_time_text,
    num,
    umbral_line,
)
from takab_api.felt import ORIGEN_INMUEBLE, ORIGEN_REFERENCIA, umbral_desde_dict

_TRACE_H = 18.0
_SKETCH_H = 78.0


def render(model: ReportModel, variant: str = "technical") -> bytes:
    """Dictamen en PDF. ``variant`` ∈ {``technical``, ``executive``}."""
    if variant == "executive":
        return _render_executive(model)
    return _render_technical(model)


# --- documento técnico --------------------------------------------------------


def _firmado(m: ReportModel) -> bool:
    """¿El dictamen vigente lleva firma? El encabezado y el deslinde salen de aquí."""
    return bool(m.dictamens and m.dictamens[0].signed_by)


def _render_technical(m: ReportModel) -> bytes:
    # [T-7.33] El estado va DERIVADO, no escrito a fuego: el encabezado se
    # repite en todas las páginas, y decía PRELIMINAR encima del banner que
    # decía FIRMADO. En un papel con peso legal eso no es una errata.
    estado = "FIRMADO" if _firmado(m) else "PRELIMINAR"
    # [T-7.42] La huella Y el instante del suceso van al PIE, no sólo a la portada.
    #
    # Hasta esta ficha ninguno de los dos se pasaba: el pie declaraba «SIN HUELLA
    # DE CONTENIDO · ESTE DOCUMENTO NO AFIRMA DATOS» en TODAS las páginas de un
    # papel que imprime su hash dos líneas más abajo y manda verificarlo, y los
    # 62 mm de su columna derecha salían VACÍOS. Un dictamen se cita por páginas
    # sueltas, y una página suelta sin huella ni fecha no se puede casar con su
    # registro.
    #
    # El instante es el de APERTURA del incidente, no el de generación: si fuera
    # el segundo, dos exportaciones del mismo modelo darían pies distintos.
    pdf = TakabPDF(
        m.folio,
        f"DICTAMEN OPERATIVO {estado} · {m.site_name} ({m.site_code})",
        sellado=m.opened_at,
        huella=m.content_sha256(),
    )
    pdf.seal(m.opened_at)
    pdf.add_page()

    _cover(pdf, m)
    _sketch_section(pdf, m)
    _envelope_section(pdf, m)
    _raw_section(pdf, m)
    _channels_section(pdf, m)
    _intensity_section(pdf, m)
    _quorum_section(pdf, m)
    _estaciones_section(pdf, m)
    _post_event_section(pdf, m)
    _sensors_section(pdf, m)
    _chain_section(pdf, m)
    _custody_section(pdf, m)
    _cronologia_section(pdf, m)
    _danos_section(pdf, m)
    _cctv_section(pdf, m)
    _narrative_section(pdf, m)
    _compliance_section(pdf, m)
    _closing(pdf, m)
    return bytes(pdf.output())


def _cover(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.verdict_banner(m.verdict_status or "", m.verdict_label, m.verdict_signed)
    pdf.field("INMUEBLE", f"{m.site_name} ({m.site_code})")
    pdf.field("INCIDENTE", m.incident_id)
    pdf.field("APERTURA", f"{m.opened_at:{TS_FMT}}")
    pdf.field("CIERRE", cierre_text(m.closed_at, m.state, m.cierre_sin_hora, TS_FMT))
    pdf.field("SEVERIDAD · DISPARO", f"{m.severity} · {disparo_line(m.opened_trigger, m.trigger)}")
    pdf.field("EVENTO DE RED", m.event_id or "SIN EVENTO ASOCIADO")
    pdf.field("FOLIO", m.folio)
    # Se imprime la huella del CONTENIDO; la del archivo no cabe dentro de sí mismo.
    pdf.field("HASH DE CONTENIDO", m.content_sha256())
    pdf.ln(1)
    # ⚠️ [T-7.42] Este párrafo decía «el SHA-256 de este archivo queda registrado…
    # verifíquelo con sha256sum», cuatro milímetros debajo de un número rotulado
    # «HASH DE CONTENIDO». Son DOS números distintos, y el papel invitaba a
    # confundirlos: quien corriera `sha256sum` sobre el PDF obtendría otra cosa y
    # concluiría que la evidencia no casa. Es la misma clase de defecto que
    # `T-5.26` —un dato inverificable presentado como verificable—, sólo que por
    # ambigüedad en vez de por truncamiento. La variante ejecutiva ya lo decía
    # bien desde `T-7.38·I`; la pericial, que es la que lee un perito, no.
    # [T-7.43] Y dice QUÉ identifica, con las puertas por las que se mueve. Un
    # número que cambia sin explicar por qué se lee como inestable, y un perito que
    # compare dos exportaciones concluiría que alguien tocó el expediente.
    #
    # ⚠️ Aquí decía además «compárelo contra ese registro desde la consola», y era
    # falso por tres vías medidas: la consola sólo busca `kind === "miniseed"`,
    # `ReportOut` no devuelve el sha del archivo —`DrillReportOut` sí— y
    # `POST /evidence/{id}/verify` filtra `kind = 'photo'`, así que para un
    # `report_pdf` da 404. El sha del archivo de un dictamen HOY no lo puede
    # obtener nadie. La superficie que falta está fichada; hasta que exista, el
    # papel no manda hacer lo que no se puede.
    pdf.para(
        "Esta huella identifica ESTA EXPORTACIÓN: no el incidente, y no este archivo "
        "—el SHA-256 de un archivo no cabe dentro de sí mismo—. Es la misma que va al "
        "pie de todas las páginas. Dos exportaciones del mismo incidente NO comparten "
        "huella, y es correcto: exportar añade este documento a la cadena de custodia "
        "que imprime la §11. También la mueven una sección que no se pudo leer —el "
        "papel declara cuál y por qué— y una redacción rehecha por el asesor "
        "automático. Una huella distinta NO prueba que el dato haya cambiado. Del "
        "ARCHIVO se registra su propio SHA-256 como evidencia inmutable del incidente; "
        "ése es el que devuelve sha256sum.",
        size=7.5,
        muted=True,
    )
    if not m.calibrated:
        pdf.callout(NO_CALIBRATION, (196, 48, 43))


#: [T-7.32] El relleno vuelve a BLANCO en cuanto una figura termina de usarlo.
#:
#: `fpdf2` guarda el color de relleno como ESTADO del documento: todo lo que se
#: rellene después lo hereda. El croquis (§1) dejaba puesto el color del
#: marcador —`20,24,30` para el inmueble, `110,120,132` para los vecinos—, así
#: que las TRES tablas del dictamen, que vienen detrás, se imprimían como barras
#: oscuras con el dato dentro, ilegible. Medido en el reporte real del acto 4 de
#: la demostración, el 2026-09-12: `pdftotext` sacaba las cifras enteras y en el
#: papel no se veía una sola.
def _relleno_por_defecto(pdf: TakabPDF) -> None:
    pdf.set_fill_color(255, 255, 255)


def _sketch_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("1", "CROQUIS DEL EVENTO")
    points: list[sketch.Point] = []
    if m.site_lat is not None and m.site_lon is not None:
        points.append(sketch.Point(m.site_lat, m.site_lon, m.site_code, "site"))
    if m.epicenter_lat is not None and m.epicenter_lon is not None:
        points.append(sketch.Point(m.epicenter_lat, m.epicenter_lon, "EPICENTRO", "epicenter"))
    for peer in m.peers:
        if peer.get("lat") is not None and peer.get("lon") is not None:
            points.append(
                sketch.Point(peer["lat"], peer["lon"], peer.get("site_code") or "?", "peer")
            )

    drawn = sketch.project(points, CONTENT_W, _SKETCH_H)
    if drawn is None:
        pdf.callout(NO_GEOMETRY)
        return

    top = pdf.get_y()
    pdf.set_draw_color(*RULE)
    pdf.rect(MARGIN, top, CONTENT_W, _SKETCH_H)

    site = next((p for p in drawn.points if p.kind == "site"), None)
    epi = next((p for p in drawn.points if p.kind == "epicenter"), None)
    if site and epi:
        pdf.set_draw_color(*MUTED)
        pdf.set_dash_pattern(dash=1.5, gap=1.5)
        pdf.line(MARGIN + site.x, top + site.y, MARGIN + epi.x, top + epi.y)
        pdf.set_dash_pattern()

    for p in drawn.points:
        x, y = MARGIN + p.x, top + p.y
        if p.kind == "site":
            pdf.set_fill_color(20, 24, 30)
            pdf.rect(x - 1.6, y - 1.6, 3.2, 3.2, style="F")
        elif p.kind == "epicenter":
            pdf.set_draw_color(196, 48, 43)
            pdf.set_line_width(0.5)
            pdf.line(x - 2.4, y, x + 2.4, y)
            pdf.line(x, y - 2.4, x, y + 2.4)
            pdf.set_line_width(0.2)
        else:
            pdf.set_fill_color(110, 120, 132)
            pdf.circle(x=x - 1.2, y=y - 1.2, radius=1.2, style="F")
        pdf.set_xy(x + 2.5, y - 2)
        pdf.set_font(pdf.body_font, "", 6)
        pdf.cell(28, 3, pdf.text_of(p.label))

    # Barra de escala y norte: sin ellas el croquis invita a medir sobre el papel.
    _relleno_por_defecto(pdf)
    pdf.set_draw_color(20, 24, 30)
    bar_y = top + _SKETCH_H - 6
    pdf.line(MARGIN + 5, bar_y, MARGIN + 5 + drawn.scale_bar_mm, bar_y)
    pdf.set_xy(MARGIN + 5, bar_y + 0.5)
    pdf.set_font(pdf.body_font, "", 6)
    pdf.cell(30, 3, pdf.text_of(f"{drawn.scale_bar_km:g} km"))
    pdf.set_xy(MARGIN + CONTENT_W - 12, top + 3)
    pdf.set_font(pdf.body_font, "B", 7)
    pdf.cell(8, 4, pdf.text_of("N ↑"))

    pdf.set_y(top + _SKETCH_H + 2)
    pdf.para(SKETCH_NOTE, size=7, muted=True)
    # [T-7.38·H] Excluyentes a propósito: los dos avisos juntos dejan al lector sin
    # saber cuál creer. Un epicentro que movió una persona NO es el centroide de las
    # estaciones, y el papel lo llamaba así por `event_source` sin mirar si alguien
    # lo había reubicado después.
    if m.epicenter_relocated:
        aqui = any(a.kind == "epicenter_relocate" for a in m.actions)
        pdf.callout(
            EPICENTRO_REUBICADO
            + (EPICENTRO_REUBICADO_AQUI if aqui else EPICENTRO_REUBICADO_EN_LA_RED)
        )
    elif m.event_source == "local_quorum":
        pdf.callout(CENTROID_NOTE)


def _envelope_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("2", "ENVOLVENTE DE ACELERACIÓN POR CANAL")
    if not m.series:
        pdf.callout("SIN FEATURES EN LA VENTANA DEL INCIDENTE.")
        return
    pdf.para(ENVELOPE_NOTE, size=7, muted=True)
    for channel, rows in sorted(m.series.items()):
        values = [pga for _, pga, _ in rows]
        flags = [clip for _, _, clip in rows]
        _trace(pdf, channel, values, flags, unit="g")


def _trace(
    pdf: TakabPDF,
    channel: str,
    values: list[float | None],
    flags: list[bool],
    unit: str,
    *,
    centrada: bool = False,
) -> None:
    """Una traza con escala propia. Escala común aplastaría los canales pequeños.

    `centrada` pone el cero en la MITAD del recuadro, que es lo que corresponde a
    una señal con signo (el crudo del ADC sin su continua). En falso el cero queda
    abajo, que es lo correcto para magnitudes positivas como el PGA.
    """
    if pdf.get_y() > 240:
        pdf.add_page()
    top = pdf.get_y()
    box = plot.Box(MARGIN + 20, top, CONTENT_W - 22, _TRACE_H)
    scale = plot.scale_of(values)

    pdf.set_font(pdf.mono_font, "", 6.5)
    pdf.set_xy(MARGIN, top + _TRACE_H / 2 - 2)
    pdf.cell(19, 4, pdf.text_of(channel))
    pdf.set_xy(MARGIN, top + _TRACE_H / 2 + 1)
    pdf.set_font(pdf.body_font, "", 5.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(19, 3, pdf.text_of(f"±{scale:.3g} {unit}"))
    pdf.set_text_color(20, 24, 30)

    pdf.set_draw_color(*RULE)
    pdf.rect(box.x, box.y, box.w, box.h)
    if centrada:
        pdf.set_draw_color(*RULE)
        pdf.line(box.x, box.y + box.h / 2, box.x + box.w, box.y + box.h / 2)
    pdf.set_draw_color(20, 24, 30)
    for seg in plot.segments(values, box, scale, baseline=centrada):
        pdf.polyline(seg)
    # El recorte del ADC se marca aparte: un canal saturado NO midió el pico, midió
    # el techo del conversor, y leerlo como aceleración real sería un error grave.
    pdf.set_draw_color(196, 48, 43)
    for x in plot.clipping_marks(flags, box):
        pdf.line(x, box.y, x, box.y + 2)
    pdf.set_draw_color(20, 24, 30)
    pdf.set_y(top + _TRACE_H + 3)


def _raw_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("3", "FORMA DE ONDA CRUDA Y CONTENIDO ESPECTRAL")
    if not m.raw_waveform:
        # [T-7.38·L] El fallback afirmaba «este incidente no tiene miniSEED
        # archivado» SIN mirar nunca la lista de custodia — que este mismo
        # documento imprime, con su sha256, cuarenta líneas más abajo. Son dos
        # estados distintos: no haberlo, y no haber podido leerlo.
        consta = any(e.kind == "miniseed" for e in m.evidence)
        pdf.callout(m.raw_unavailable_reason or (ONDA_NO_LEIDA if consta else NO_SPECTRUM))
        return

    rate = m.raw_sample_rate or 100.0
    pdf.para(
        f"Decodificada del miniSEED archivado del evento · {rate:g} sps · cuentas del ADC, "
        "sin su componente continua (el cero de cada traza es su propia media).",
        size=7,
        muted=True,
    )
    for channel, samples in sorted(m.raw_waveform.items()):
        # Se diezma para el dibujo: 18 000 muestras no caben en la banda útil
        # (185.9 mm en Carta desde `T-7.21`; eran 180 en A4) y fpdf2
        # tardaría más en trazarlas que la propia consulta.
        step = max(1, len(samples) // 900)
        crudas = [float(v) for v in samples[::step]]
        # [T-7.39] Se le quita la CONTINUA. El crudo del ADC trae un offset enorme
        # —del orden de 10^6 cuentas— y la traza se escalaba contra él con el cero
        # abajo: salía una línea plana bajo la etiqueta «±3.86e+06 cuentas», que es
        # el offset, no la sacudida. Restar la media y centrar en el cero es lo que
        # hace visible la señal, y la etiqueta pasa a decir su amplitud real.
        continua = sum(crudas) / len(crudas) if crudas else 0.0
        sin_dc: list[float | None] = [v - continua for v in crudas]
        _trace(pdf, channel, sin_dc, [False] * len(sin_dc), unit="cuentas", centrada=True)

    _duracion(pdf, m)

    if m.spectrum:
        freqs, amps = m.spectrum
        _spectrum(pdf, freqs, amps, m.spectrum_peak_hz)
    if m.spectrogram is not None:
        _spectrogram(pdf, m.spectrogram)


def _duracion(pdf: TakabPDF, m) -> None:
    """[T-3.14] La duración instrumental, con su definición pegada al número.

    **Nunca dice «duración» a secas.** Existen varias definiciones —la bracketed es la que
    la gente espera— y dan números distintos para el mismo sismo; un número sin su
    definición invita a compararlo con otro que se midió de otra forma.

    Y cuando no se pudo medir, lo dice. Un `0.0 s` aquí se leería como «no tembló», que es
    lo contrario de lo que pasó: lo que faltó fue la onda, no la sacudida.
    """
    if pdf.get_y() > 240:
        pdf.add_page()
    pdf.ln(2)
    pdf.set_font(pdf.body_font, "B", 8)
    pdf.cell(0, 4, "DURACIÓN INSTRUMENTAL DE LA SACUDIDA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(pdf.body_font, "", 7)
    d = m.shaking_duration
    if d is None:
        pdf.multi_cell(
            0,
            3.4,
            "SIN DATO · no se pudo medir sobre la onda archivada. No es cero: es que no "
            "hubo traza suficiente de la que medirla.",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        return
    pdf.multi_cell(
        0,
        3.4,
        f"{d.etiqueta} — intervalo en el que se acumula del 5 % al 95 % de la Intensidad "
        f"de Arias, medido sobre el canal {d.canal} del miniSEED archivado "
        f"({d.muestras} muestras, de t+{d.desde_s:.1f} s a t+{d.hasta_s:.1f} s desde el "
        "inicio de la traza). Definición de Trifunac & Brady (1975); NO es comparable con "
        "una duración «bracketed», que se mide entre cruces de un umbral de aceleración.",
        new_x="LMARGIN",
        new_y="NEXT",
    )


def _spectrum(pdf: TakabPDF, freqs: list[float], amps: list[float], peak_hz: float | None) -> None:
    if pdf.get_y() > 220:
        pdf.add_page()
    pdf.ln(2)
    pdf.set_font(pdf.body_font, "B", 8)
    pdf.cell(0, 5, pdf.text_of("ESPECTRO DE AMPLITUD"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    top = pdf.get_y()
    box = plot.Box(MARGIN + 20, top, CONTENT_W - 22, 26.0)
    scale = plot.scale_of([float(a) for a in amps])
    pdf.set_draw_color(*RULE)
    pdf.rect(box.x, box.y, box.w, box.h)
    pdf.set_draw_color(20, 24, 30)
    for seg in plot.segments([float(a) for a in amps], box, scale):
        pdf.polyline(seg)
    pdf.set_y(top + 27)
    pdf.set_font(pdf.body_font, "", 6.5)
    pdf.set_text_color(*MUTED)
    top_hz = freqs[-1] if freqs else 0.0
    peak = f"pico {peak_hz:.2f} Hz" if peak_hz else "sin pico dominante"
    pdf.cell(
        0,
        4,
        pdf.text_of(f"0 – {top_hz:.1f} Hz · {peak}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.set_text_color(20, 24, 30)


#: [T-5.23] Rampa de la figura, de frío a caliente. Se declara aquí y no se
#: interpola en el trazado: una rampa continua sugiere una resolución que estas
#: celdas no tienen, y un espectrograma de papel se lee por bandas.
_RAMPA: tuple[tuple[int, int, int], ...] = (
    (14, 20, 28),  # fondo: casi el negro del documento
    (23, 55, 92),
    (30, 110, 140),
    (70, 165, 130),
    (190, 180, 70),
    (220, 120, 45),
    (200, 55, 45),  # máximo de la ventana
)


def _spectrogram(pdf: TakabPDF, esp) -> None:  # noqa: ANN001 - Espectrograma
    """[T-5.23] Tiempo × frecuencia del canal dominante.

    LO QUE ESTA FIGURA NO PROMETE, y por eso se dibuja así: **la escala es
    RELATIVA**. El crudo del RS4D llega en cuentas del ADC y la calibración
    instrumental sigue pendiente (`blueprint §4.4`), así que no hay dB
    referenciados a nada físico. Pintar una barra con unidades sería prometer una
    calibración que no existe — la misma guarda que ya vigila el mapa de sacudida.

    Por eso la leyenda dice «relativo al máximo de esta ventana» y no lleva
    números: el color contesta *dónde y cuándo hubo más energía*, que es lo que
    un perito busca, y no *cuánta* — que nadie ha medido.
    """
    filas, columnas = len(esp.frecuencias_hz), len(esp.celdas)
    if filas == 0 or columnas == 0:
        return
    if pdf.get_y() > 200:
        pdf.add_page()
    pdf.ln(2)
    pdf.set_font(pdf.body_font, "B", 8)
    pdf.cell(
        0,
        5,
        pdf.text_of(f"ESPECTROGRAMA · CANAL {esp.canal}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    top = pdf.get_y()
    alto = 32.0
    box = plot.Box(MARGIN + 20, top, CONTENT_W - 22, alto)
    dx, dy = box.w / columnas, box.h / filas

    # Se dibuja celda a celda con el relleno apagado: `fpdf2` no tiene mapa de
    # bits sin traer una dependencia de imagen, y 120 × 48 rectángulos son
    # deterministas y pesan poco. La frecuencia CRECE hacia arriba, como se lee.
    for i, columna in enumerate(esp.celdas):
        for j, valor in enumerate(columna):
            pdf.set_fill_color(*_RAMPA[min(len(_RAMPA) - 1, int(valor * len(_RAMPA)))])
            pdf.rect(box.x + i * dx, box.y + box.h - (j + 1) * dy, dx + 0.05, dy + 0.05, style="F")

    pdf.set_draw_color(*RULE)
    pdf.rect(box.x, box.y, box.w, box.h)
    pdf.set_draw_color(20, 24, 30)
    _relleno_por_defecto(pdf)

    # Los ejes, con su magnitud: sin ellas la figura es una mancha bonita.
    pdf.set_font(pdf.body_font, "", 6.0)
    pdf.set_text_color(*MUTED)
    pdf.text(MARGIN, box.y + 2.5, pdf.text_of(f"{esp.frecuencias_hz[-1]:.0f} Hz"))
    pdf.text(MARGIN, box.y + box.h, pdf.text_of(f"{esp.frecuencias_hz[0]:.1f} Hz"))
    pdf.set_y(top + alto + 1)
    pdf.cell(
        0,
        4,
        pdf.text_of(leyenda_espectrograma(esp)),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.set_text_color(20, 24, 30)


def _channels_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("4", "MÉTRICAS POR CANAL")
    if not m.channels:
        pdf.callout("SIN MEDICIONES REGISTRADAS EN LA VENTANA DEL INCIDENTE.")
        return
    headers = ("CANAL", "PGA (g)", "PGV (cm/s)", "RMS", "STA/LTA", "MUESTRAS", "RECORTE")
    pdf.set_font(pdf.body_font, "", 7)
    with pdf.table(col_widths=(20, 24, 26, 20, 22, 22, 22), text_align="LEFT") as table:
        head = table.row()
        for h in headers:
            head.cell(pdf.text_of(h))
        for c in m.channels:
            row = table.row()
            row.cell(pdf.text_of(c.channel))
            row.cell(pdf.text_of(num(c.peak_pga_g, 4)))
            row.cell(pdf.text_of(num(c.peak_pgv_cms, 2)))
            row.cell(pdf.text_of(num(c.peak_rms, 4)))
            row.cell(pdf.text_of(num(c.peak_stalta, 2)))
            row.cell(pdf.text_of(str(c.samples)))
            row.cell(pdf.text_of("SÍ" if c.clipped else "no"))
    if any(c.clipped for c in m.channels):
        pdf.callout(
            "UN CANAL SATURÓ EL CONVERTIDOR: su pico es el techo del ADC, no la "
            "aceleración real del inmueble.",
            (214, 132, 20),
        )


def _intensity_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("5", "INTENSIDAD MEDIDA EN EL INMUEBLE")
    pdf.field("PGA PICO", num(m.peak_pga_g, 4, "g"))
    pdf.field("PGV PICO", num(m.peak_pgv_cms, 2, "cm/s"))
    pdf.field("INSTANTE DEL PICO", f"{m.peak_ts:{TS_FMT}}" if m.peak_ts else "SIN DATO")
    pdf.field("BANDA", FELT_LABELS.get(m.felt_band, m.felt_band.upper()))
    # [T-7.35] Contra qué números. Sin esta línea, «SACUDIDA FUERTE» es una
    # palabra sin escala — y durante meses el rótulo atribuyó al inmueble un
    # umbral que no era el suyo.
    pdf.field("UMBRAL DE COMPARACIÓN", umbral_line(umbral_desde_dict(m.felt_thresholds)))
    pdf.callout(NO_MMI)


def _quorum_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("6", "CORROBORACIÓN MULTI-ESTACIÓN")
    if not m.votes:
        pdf.callout("SIN CORROBORACIÓN MULTI-ESTACIÓN PARA ESTE INCIDENTE.")
        return
    pdf.set_font(pdf.body_font, "", 7)
    with pdf.table(col_widths=(50, 30, 30, 30), text_align="LEFT") as table:
        head = table.row()
        for h in ("ESTACIÓN", "Δt (s)", "PGA (g)", "CONTADO"):
            head.cell(pdf.text_of(h))
        for v in m.votes:
            row = table.row()
            row.cell(pdf.text_of(v.label))
            row.cell(pdf.text_of(num(v.delta_s, 2)))
            row.cell(pdf.text_of(num(v.pga_g, 4)))
            row.cell(pdf.text_of("sí" if v.counted else "no"))


#: [T-7.22] Alto del mapa de la red. Más bajo que el croquis del evento (78 mm)
#: porque debajo va la tabla de arribos y las dos tienen que caber juntas para
#: poder leerse de una vez: un mapa en una página y su tabla en la siguiente
#: obliga a pasar hojas para saber qué punto es qué fila.
_MAPA_RED_H = 62.0

#: Rótulo del origen del umbral, en la celda de la tabla de la red.
_ORIGEN_CORTO = {ORIGEN_INMUEBLE: "del inmueble", ORIGEN_REFERENCIA: "de referencia"}


def _umbral_celda(e) -> str:  # noqa: ANN001 - EstacionFila
    """El umbral de esa estación con su procedencia, o la ausencia declarada.

    [T-7.35] El número solo no vale: durante meses el papel atribuyó al edificio
    un umbral que era el de fábrica. Y un umbral ausente no es cero — significa
    que no se sabe contra qué se comparó ese pico.
    """
    if e.umbral_pga_g is None:
        return "SIN DATO"
    origen = _ORIGEN_CORTO.get(e.umbral_origen or "", "origen no declarado")
    return f"{num(e.umbral_pga_g, 4)} {origen}"


def _mapa_de_la_red(pdf: TakabPDF, m: ReportModel) -> None:
    """Mapa estático VECTORIAL de la red: dónde está cada estación y el epicentro.

    [T-7.22] Vectorial y sin una sola petición externa —ni tiles, ni cartografía
    base—: un documento de evidencia que dependa de que un servidor de mapas siga
    en pie dentro de cinco años no es evidencia. Se dibuja con la MISMA
    proyección que el croquis del evento (`sketch.project`), así que las dos
    figuras del documento miden igual; portar el renderizador del panel habría
    dado un segundo proyector que acabaría discrepando del primero.

    **Es distinto del croquis de la §1.** Aquél pinta a quienes VOTARON en el
    cuórum (`m.peers`), que es un hecho del motor; en una reproducción no hay
    votos y sale con dos puntos. Éste pinta las estaciones que MIDIERON, que es
    lo que la §7 narra — y es justo el caso de la demostración.

    Sin cartografía base el dibujo es un croquis rotulado, no un mapa geográfico,
    y el papel lo dice: lleva barra de escala y norte, que es lo que permite leer
    distancias sin fingir que hay costas.
    """
    puntos: list[sketch.Point] = []
    # El inmueble del dictamen se distingue de las demás estaciones aunque
    # aparezca en las dos listas: es el sujeto del documento, no un testigo.
    propio = m.site_code
    if m.site_lat is not None and m.site_lon is not None:
        puntos.append(sketch.Point(m.site_lat, m.site_lon, propio, "site"))
    if m.epicenter_lat is not None and m.epicenter_lon is not None:
        puntos.append(sketch.Point(m.epicenter_lat, m.epicenter_lon, "EPICENTRO", "epicenter"))
    for e in m.estaciones:
        if e.lat is None or e.lon is None or e.site_code == propio:
            continue
        puntos.append(sketch.Point(e.lat, e.lon, e.site_code, "station"))

    dibujo = sketch.project(puntos, CONTENT_W, _MAPA_RED_H)
    if dibujo is None:
        # Declarar la ausencia, no dejar el hueco: sin geometría no se puede
        # situar nada, y un mapa vacío se lee como «no hay estaciones».
        pdf.callout(SIN_GEOMETRIA_DE_RED)
        return

    # ⚠️ `rect`/`line` NO disparan el salto de página de fpdf2 (`set_auto_page_break`
    # sólo mira texto): sin esto la figura se pinta encima del filete del pie.
    pdf.reserva(_MAPA_RED_H + 6)
    top = pdf.get_y()
    pdf.set_draw_color(*RULE)
    pdf.rect(MARGIN, top, CONTENT_W, _MAPA_RED_H)

    for p in dibujo.points:
        x, y = MARGIN + p.x, top + p.y
        if p.kind == "site":
            pdf.set_fill_color(*INK)
            pdf.rect(x - 1.6, y - 1.6, 3.2, 3.2, style="F")
        elif p.kind == "epicenter":
            pdf.set_draw_color(196, 48, 43)
            pdf.set_line_width(0.5)
            pdf.line(x - 2.4, y, x + 2.4, y)
            pdf.line(x, y - 2.4, x, y + 2.4)
            pdf.set_line_width(0.2)
            pdf.set_draw_color(*RULE)
        else:
            # Anillo, no disco: una estación que midió es un testigo, y el disco
            # relleno ya significa «el inmueble de este dictamen».
            pdf.set_draw_color(110, 120, 132)
            pdf.circle(x=x - 1.3, y=y - 1.3, radius=1.3)
            pdf.set_draw_color(*RULE)
        pdf.set_xy(x + 2.5, y - 2)
        pdf.set_font(pdf.body_font, "", 6)
        pdf.cell(28, 3, pdf.text_of(p.label))

    _relleno_por_defecto(pdf)
    pdf.set_draw_color(*INK)
    bar_y = top + _MAPA_RED_H - 6
    pdf.line(MARGIN + 5, bar_y, MARGIN + 5 + dibujo.scale_bar_mm, bar_y)
    pdf.set_xy(MARGIN + 5, bar_y + 0.5)
    pdf.set_font(pdf.body_font, "", 6)
    pdf.cell(30, 3, pdf.text_of(f"{dibujo.scale_bar_km:g} km"))
    pdf.set_xy(MARGIN + CONTENT_W - 12, top + 3)
    pdf.set_font(pdf.body_font, "B", 7)
    pdf.cell(8, 4, pdf.text_of("N ↑"))
    pdf.set_y(top + _MAPA_RED_H + 2)


def _estaciones_section(pdf: TakabPDF, m: ReportModel) -> None:
    """[T-7.17] Qué midió cada estación de la red, junto a lo que le tocaba.

    Distinta de la sección 6: aquélla dice QUIÉN VOTÓ en el cuórum —un hecho del
    motor—, y ésta dice QUÉ MIDIÓ cada inmueble. En una reproducción no hay votos
    y esta tabla es la única que cuenta lo que pasó en la red.
    """
    pdf.section("7", "RED DE ESTACIONES")
    # [T-7.22] La leyenda va ANTES que nada: condiciona todo lo que sigue. Un
    # lector que llegue a la tabla de arribos sin haberla leído está midiendo la
    # respuesta de un edificio a un sismo que no ocurrió.
    if m.reproduccion:
        pdf.callout(REPRODUCCION_NOTE)
    if not m.estaciones:
        pdf.callout("SIN ESTACIONES CON GABINETE ACTIVO EN ESTE CLIENTE.")
        return
    _mapa_de_la_red(pdf, m)
    pdf.para(
        "Arribos contados desde "
        + (
            "el origen del sismo."
            if m.estaciones_ancla == "event"
            else "la apertura del incidente."
        ),
        size=7.5,
        muted=True,
    )
    pdf.set_font(pdf.body_font, "", 7)
    with pdf.table(col_widths=(40, 17, 20, 20, 20, 24, 17), text_align="LEFT") as table:
        head = table.row()
        for h in (
            "ESTACIÓN",
            "DIST (km)",
            "ESPERADO (s)",
            "MEDIDO (s)",
            "PICO (g)",
            "UMBRAL (g)",
            "TIER",
        ):
            head.cell(pdf.text_of(h))
        for e in m.estaciones:
            row = table.row()
            etiqueta = e.site_name if e.sensor_code is None else f"{e.site_name} ({e.sensor_code})"
            row.cell(pdf.text_of(etiqueta))
            row.cell(pdf.text_of(num(e.dist_km, 0)))
            row.cell(pdf.text_of(num(e.t_teorico_s, 1)))
            row.cell(pdf.text_of(num(e.t_medido_s, 1)))
            row.cell(pdf.text_of(num(e.peak_pga_g, 4)))
            # [T-7.22] El pico sin su umbral es un número sin escala, y el umbral
            # sin su procedencia parece del edificio aunque sea el de referencia
            # (`T-7.35`). Van en la misma celda porque separan mal: una columna
            # más estrecha partiría el rótulo de procedencia en dos líneas.
            row.cell(pdf.text_of(_umbral_celda(e)))
            # Vacío no es `normal`: el gabinete no dijo que estuviera en calma.
            row.cell(pdf.text_of(e.tier or "S/D"))


def _post_event_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("8", "DESEMPEÑO DE LA RED")
    pdf.field("TIEMPO DE AVISO GANADO", lead_time_text(m.lead_time_s, m.lead_time_reason))
    pdf.field("ESTACIONES QUE CONTRIBUYERON", str(m.station_count))
    # [T-5.11] El rótulo dice CORRELACIÓN y no «contraste»: contrastar exige un
    # epicentro propio, y en la ruta del receptor —la normal— no lo hay. Es la
    # línea la que declara si hubo contraste de verdad o no fue verificable.
    pdf.field("CORRELACIÓN CON CATÁLOGO", m.catalog_line or SIN_CORRELACION_EN_CATALOGO)


def _sensors_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("9", "INSTRUMENTACIÓN")
    if not m.sensors:
        pdf.callout("SIN SENSORES ACTIVOS REGISTRADOS PARA ESTE INMUEBLE.")
        return
    for sn in m.sensors:
        pdf.field(
            f"{sn.get('kind', '?').upper()} · {sn.get('model', '?')}",
            f"serie {sn.get('serial') or 'S/N'} · {sn.get('sample_rate') or '?'} sps · "
            f"montaje {sn.get('mount') or 'no declarado'} · "
            f"calibración {sn.get('calibration_source') or 'NO DECLARADA'}",
        )


def _chain_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("10", "CADENA DE DICTÁMENES")
    if not m.dictamens:
        pdf.callout("SIN DICTAMEN REGISTRADO PARA ESTE INCIDENTE.")
        return
    pdf.set_font(pdf.body_font, "", 7)
    with pdf.table(col_widths=(28, 46, 40, 26, 30), text_align="LEFT") as table:
        head = table.row()
        for h in ("ESTADO", "VEREDICTO", "FECHA", "REGLAS", "SUCEDE A"):
            head.cell(pdf.text_of(h))
        for d in m.dictamens:
            row = table.row()
            row.cell(pdf.text_of("FIRMADO" if d.signed_by else "PRELIMINAR"))
            row.cell(pdf.text_of(STATUS_LABELS.get(d.status, d.status)))
            row.cell(pdf.text_of(f"{d.created_at:%Y-%m-%d %H:%M}"))
            row.cell(pdf.text_of(d.rule_set_version))
            row.cell(pdf.text_of((d.supersedes or "—")[:8]))
    pdf.ln(1)
    pdf.para(
        "Las correcciones INSERTAN una versión nueva; ninguna fila se reescribe.",
        size=7,
        muted=True,
    )


def _custody_section(pdf: TakabPDF, m: ReportModel) -> None:
    """[T-7.22] Solo los OBJETOS de evidencia. La bitácora se fue a la §12.

    Imprimía además, en monoespaciada y sin rótulo, las filas de
    `incident_actions` con su `kind` CRUDO: el papel decía `gas_closed` donde la
    pantalla dice «VÁLVULAS DE GAS CERRADAS». Son dos cosas distintas —qué se
    archivó y qué pasó— y estaban bajo un mismo título que solo nombra a una.

    Se MUEVEN y no se duplican: imprimir las mismas filas en dos secciones de un
    documento de evidencia obliga al lector a contarlas dos veces o a decidir
    cuál de las dos apariciones creer.
    """
    pdf.section("11", "CADENA DE CUSTODIA")
    if m.evidence:
        pdf.set_font(pdf.body_font, "", 7.5)
        for e in m.evidence:
            # [T-5.26] El sha256 ENTERO. Se imprimía a 32 de 64 caracteres
            # mientras la portada de este mismo documento instruye verificarlo
            # con `sha256sum`: con medio hash no se puede, y un dato inverificable
            # presentado como verificable es peor que no imprimirlo.
            # No había razón de espacio — 64 hex miden 108.7 mm de los 128 que
            # deja la columna, así que entran en una sola línea.
            pdf.field(e.kind.upper(), huella_de_custodia(e.sha256))
    else:
        # [T-7.38·K] Esta sección solo lee `evidence_objects`. El material de vídeo
        # es custodia igual —el apartado siguiente lo relaciona con su sha256— y
        # vive en otras tablas, así que «sin objetos» a secas contradecía a la
        # página de al lado. La frase DECLARA SU ALCANCE y remite; no dice del
        # vídeo más que dónde mirar, así que vale igual para un clip archivado y
        # para uno ya purgado.
        pdf.para(
            "Sin objetos de evidencia archivados para este incidente."
            + (
                " El material de vídeo no se contabiliza aquí: su custodia y su "
                "estado se relacionan en el apartado siguiente."
                if m.cctv.objetos
                else ""
            ),
            size=7.5,
            muted=True,
        )


def _cronologia_section(pdf: TakabPDF, m: ReportModel) -> None:
    """[T-7.22] Qué pasó y cuándo, en castellano.

    El criterio de la ficha pide «cronología desde `incident_actions`». Las filas
    ya viajaban en el modelo y ya se imprimían —dentro de la CADENA DE CUSTODIA, en
    monoespaciada y con el `kind` en crudo—. Lo que faltaba no era el dato: era
    que se pudiera leer.

    Los rótulos son el ESPEJO de los de la consola (`dictamen/bitacora.py`), para
    que el papel y la pantalla no cuenten lo mismo con dos vocabularios. Un verbo
    que el registro no sepa rotular sale con su identificador **y con el aviso de
    que no tiene rótulo**: `incident_actions` es append-only y exenta de poda, así
    que puede traer verbos de hace dos años, y un dato crudo declarado como tal es
    honesto donde uno crudo a secas no lo es.
    """
    pdf.section("12", "CRONOLOGÍA DEL INCIDENTE")
    if not m.actions:
        pdf.callout(SIN_CRONOLOGIA)
        return
    pdf.set_font(pdf.body_font, "", 7)
    sin_rotulo = 0
    with pdf.table(col_widths=(34, 86, 38), text_align="LEFT") as table:
        head = table.row()
        for h in ("INSTANTE (UTC)", "QUÉ PASÓ", "QUIÉN"):
            head.cell(pdf.text_of(h))
        for a in m.actions:
            texto, conocido = rotulo_de_accion(a.kind)
            sin_rotulo += 0 if conocido else 1
            row = table.row()
            row.cell(pdf.text_of(f"{a.ts:{TS_FMT}}"))
            row.cell(pdf.text_of(texto))
            row.cell(pdf.text_of(a.actor))
    if sin_rotulo:
        # Declarar el recuento, no solo marcar las filas: quien audite tiene que
        # poder saber de un vistazo cuánto del documento no se supo traducir.
        pdf.callout(f"{CRONOLOGIA_SIN_ROTULO}{sin_rotulo} de {len(m.actions)}.")


#: Ancho de cada fotografía impresa. Dos por fila en el ancho útil, con aire
#: entre ellas. Más pequeñas no dejan ver una grieta; más grandes obligan a una
#: página por foto y el documento deja de poder hojearse.
_FOTO_W = 88.0
_FOTO_GAP = (CONTENT_W - 2 * _FOTO_W) / 1.0
#: Alto que se RESERVA por fila de fotos: el máximo posible (una foto de retrato
#: a 1024×1024 sale cuadrada) más el pie de dos líneas.
_FOTO_FILA_H = _FOTO_W + 10.0


def _danos_section(pdf: TakabPDF, m: ReportModel) -> None:
    """[T-7.22] Lo que vio quien entró al edificio, con sus fotografías.

    Es la mitad del valor del documento que las cifras no dan: una grieta, un
    plafón caído, una ruta bloqueada (`D-32`). Hasta ahora `damage_reports` no la
    leía nadie del lado del papel, y las fotografías aparecían sólo como una línea
    de `PHOTO <sha256>` en la cadena de custodia — el documento afirmaba que
    existían y no enseñaba ninguna.

    **Por ROL y nunca por nombre**, que es lo que fija `D-32`. El rol es lo único
    que este documento necesita para que la observación tenga procedencia.

    **Cada foto lleva TRES huellas** y la diferencia importa: la que DECLARÓ el
    dispositivo (nunca verificada en servidor), la que se MIDIÓ al leer el blob, y
    la de lo IMPRESO —que es una derivada redimensionada y sin EXIF, no el
    original—. Imprimir sólo la del original junto a píxeles que no son ese
    original convertiría «verifique el sha256» en falso, que es el defecto que
    `T-5.26` ya cazó una vez con el hash truncado.
    """
    pdf.section("13", "DAÑOS REPORTADOS EN CAMPO")
    if not m.danos:
        pdf.callout(SIN_DANOS)
        return
    for dano in m.danos:
        pdf.reserva(24.0)
        quien = dano.rol or ROL_NO_RESUELTO
        donde = dano.zona or "zona no declarada"
        pdf.field("REPORTE", f"{quien} · {donde} · {dano.ts:{TS_FMT}}")
        if dano.personas_en_riesgo:
            # Lo más importante que puede decir un reporte de campo, y no puede
            # quedar como una casilla más de la tabla de categorías.
            pdf.callout(PERSONAS_EN_RIESGO, color=VERDICT_COLORS.get("evacuate", MUTED))
        if dano.categorias:
            pdf.set_font(pdf.body_font, "", 7)
            with pdf.table(col_widths=(60, 34, 92), text_align="LEFT") as table:
                head = table.row()
                for h in ("QUÉ", "SEVERIDAD", "NOTA"):
                    head.cell(pdf.text_of(h))
                for cat in dano.categorias:
                    row = table.row()
                    row.cell(pdf.text_of(str(cat.get("key", "—"))))
                    row.cell(pdf.text_of(str(cat.get("severity", "—"))))
                    row.cell(pdf.text_of(str(cat.get("note") or "")))
        else:
            pdf.para(SIN_CATEGORIAS, size=7.5, muted=True)
        if dano.notas:
            pdf.para(dano.notas, size=7.5)
        _fotos_del_reporte(pdf, dano)
        if dano.fotos_omitidas:
            # El rótulo dice IMPRESAS, así que el número es el de las impresas.
            # Escribí aquí el de las omitidas y el papel decía «Impresas: 2 de 5»
            # con tres fotografías delante: un recuento que se contradice con lo
            # que el lector tiene a la vista es peor que no ponerlo.
            pdf.callout(
                f"{FOTOS_OMITIDAS}{len(dano.fotos)} de {len(dano.fotos) + dano.fotos_omitidas}."
            )
        pdf.ln(2)


def _fotos_del_reporte(pdf: TakabPDF, dano) -> None:  # noqa: ANN001 - DanoFila
    """Las fotografías, dos por fila, o la razón de que no estén.

    ⚠️ `pdf.image()` NO dispara el salto de página automático de fpdf2, igual que
    `rect` y `line`: sin `reserva()` la fotografía se pinta encima del filete del
    pie, sobre el sha256 y la paginación. Lo vigila `test_NINGUNA_caja_pisa_el_PIE`,
    que desde `T-7.22` sabe leer el operador de imagen.
    """
    impresas = [f for f in dano.fotos if f.jpeg is not None]
    ausentes = [f for f in dano.fotos if f.jpeg is None]

    for i in range(0, len(impresas), 2):
        pdf.reserva(_FOTO_FILA_H)
        fila = impresas[i : i + 2]
        top = pdf.get_y()
        alto_fila = 0.0
        for j, foto in enumerate(fila):
            x = MARGIN + j * (_FOTO_W + _FOTO_GAP)
            alto = _FOTO_W * (foto.alto / foto.ancho) if foto.ancho and foto.alto else _FOTO_W
            pdf.image(io.BytesIO(foto.jpeg), x=x, y=top, w=_FOTO_W)
            alto_fila = max(alto_fila, alto)
        # El pie de cada foto va DEBAJO de la fila entera, no al lado: dos fotos
        # de alto distinto dejarían los pies desalineados y sin saber cuál es cuál.
        pdf.set_y(top + alto_fila + 1)
        for j, foto in enumerate(fila):
            pdf.set_x(MARGIN + j * (_FOTO_W + _FOTO_GAP))
            pdf.set_font(pdf.mono_font, "", 5.2)
            pdf.set_text_color(*MUTED)
            pdf.multi_cell(
                _FOTO_W,
                2.4,
                pdf.text_of(_pie_de_foto(foto)),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT if j else YPos.TOP,
            )
        pdf.set_text_color(*INK)
        pdf.ln(1)

    for foto in ausentes:
        pdf.callout(f"FOTOGRAFÍA {foto.evidence_id[:8]} NO IMPRESA · {foto.motivo}")


def _pie_de_foto(foto) -> str:  # noqa: ANN001 - FotoFila
    """Las tres huellas y el veredicto sobre si la declarada casa con la medida.

    El desajuste es lo más importante que esta sección puede decir de una
    fotografía de evidencia: significa que el archivo que hay en el almacén no es
    el que el dispositivo dijo haber subido.
    """
    partes = [f"{foto.ancho}×{foto.alto} px · DERIVADA SIN METADATOS"]
    partes.append(f"DECLARADA {foto.sha256_declarado or 'SIN DATO'}")
    if foto.sha256_medido is None:
        partes.append("MEDIDA: no se pudo leer el archivo")
    elif foto.sha256_declarado and foto.sha256_medido != foto.sha256_declarado:
        partes.append(f"⚠ MEDIDA {foto.sha256_medido} · NO COINCIDE CON LA DECLARADA")
    else:
        partes.append("MEDIDA: coincide con la declarada")
    partes.append(f"IMPRESA {foto.sha256_impreso}")
    return "\n".join(partes)


def _cctv_section(pdf: TakabPDF, m: ReportModel) -> None:
    """[T-3.12.c] Analítica de evacuación y custodia del vídeo.

    Va DESPUÉS de la cadena de custodia y no antes: sus objetos son custodia también, y
    leerlos seguidos deja claro que el clip y el miniSEED son el mismo tipo de evidencia
    con distinta política de retención.

    **Sin cámara la sección existe igual.** Omitirla dejaría al lector sin saber si este
    inmueble no tiene CCTV o si el generador se lo saltó, que es exactamente la ambigüedad
    que `NO_CCTV` está escrito para cerrar.
    """
    pdf.section("14", "EVACUACIÓN OBSERVADA (CCTV)")
    bloque = m.cctv

    if bloque.t90_s is None:
        pdf.callout(bloque.estado)
    else:
        pdf.field("Aforo máximo observado", num(bloque.peak_n))
        pdf.field(
            "Mitad del aforo alcanzada",
            f"{bloque.t50_s:.0f} s tras la señal" if bloque.t50_s is not None else ABSENT,
        )
        pdf.field("La mayor parte fuera", f"{bloque.t90_s:.0f} s tras la señal")
        if bloque.correlacion:
            pdf.para(bloque.correlacion)
        if bloque.discrepancia:
            # El cruce con el pase de lista se muestra como DISCREPANCIA, jamás promediado
            # en un número único: la diferencia ES la información (T-3.12).
            pdf.field("Cruce con el pase de lista", bloque.discrepancia)
        if bloque.veredicto_reingreso:
            if bloque.reingreso_antes_del_dictamen:
                # Recuadro y no celda: que la gente reentrara antes del dictamen no es un
                # número negativo en una tabla, es un hallazgo que alguien tiene que leer.
                pdf.callout(bloque.veredicto_reingreso)
            else:
                pdf.field("Reingreso", bloque.veredicto_reingreso)

    if not bloque.objetos:
        return
    pdf.para("Custodia del material de vídeo:", size=9, muted=True)
    for obj in bloque.objetos:
        etiqueta = obj.papel or obj.tipo
        cuando = obj.momento.strftime(TS_FMT) if obj.momento else ABSENT
        pdf.field(f"{etiqueta} · {cuando}", obj.estado)
        # [T-5.26] Entero y en su propia línea. Iba a 16 de 64 con puntos
        # suspensivos: honesto sobre estar cortado, e igual de inútil para
        # verificar. Y son custodia igual que el miniSEED —lo dice esta misma
        # sección cuatro líneas más arriba—, así que se imprimen igual.
        pdf.field("", huella_de_custodia(obj.sha256))


def _narrative_section(pdf: TakabPDF, m: ReportModel) -> None:
    """Prosa opcional (T-2.42). Rodea al veredicto; nunca lo produce."""
    if not m.narrative:
        return
    pdf.section("15", "ANÁLISIS")
    for title, body in m.narrative:
        pdf.set_font(pdf.body_font, "B", 8)
        pdf.cell(0, 5, pdf.text_of(title.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.para(body)
    if m.narrative_provider and m.narrative_provider != "deterministic":
        pdf.callout(
            f"{NARRATIVE_AI_NOTE} ({m.rule_set_version or 'sin versión'}) y no dependen de ella."
        )
    if m.narrative_degraded:
        pdf.para(f"NARRATIVA DEGRADADA · {m.narrative_degraded}", size=7, muted=True)


def _compliance_section(pdf: TakabPDF, m: ReportModel) -> None:
    """[T-2.82] Marco normativo DECLARADO por el cliente.

    Va INMEDIATAMENTE antes de la firma y del deslinde, y no en la portada, a
    propósito: quien firma tiene que leer, en el mismo golpe de vista, que este
    apartado no lo respalda TAKAB. El título nombra al autor de las afirmaciones para
    que no haga falta llegar a la nota para saber de quién son.
    """
    pdf.section("16", "MARCO NORMATIVO DECLARADO POR EL CLIENTE")
    block = compliance_block(m.compliance)
    for label, value in block.rows:
        pdf.field(label, value)
    if block.rows:
        pdf.ln(1)
    for note in block.notes:
        pdf.callout(note)


def _closing(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("17", "FIRMA Y DESLINDE")
    head = m.dictamens[0] if m.dictamens else None
    if head and head.signed_by:
        pdf.field("FIRMÓ", head.signed_by)
        pdf.para(
            "Firma de usuario autenticado (Cognito). NO es una firma criptográfica ni "
            "un sello de tiempo de HSM.",
            size=7,
            muted=True,
        )
    else:
        pdf.field("FIRMA", "PRELIMINAR · SIN FIRMA DE INSPECTOR")
    pdf.ln(2)
    pdf.callout(f"{DISCLAIMER_ESTADO[_firmado(m)]} {DISCLAIMER}", (20, 24, 30))


# --- documento ejecutivo ------------------------------------------------------


def _render_executive(m: ReportModel) -> bytes:
    """Una o dos páginas para quien decide, no para quien peritea."""
    # [T-7.42] Misma razón que el pericial. Y la huella es DISTINTA de la suya a
    # propósito —son dos documentos y dicen cosas distintas—; lo que los empareja
    # es el FOLIO, que el pie también lleva (`T-7.38·I`).
    pdf = TakabPDF(
        m.folio,
        f"RESUMEN EJECUTIVO · {m.site_name} ({m.site_code})",
        sellado=m.opened_at,
        huella=m.content_sha256(),
    )
    pdf.seal(m.opened_at)
    pdf.add_page()

    pdf.verdict_banner(m.verdict_status or "", m.verdict_label, m.verdict_signed)

    pdf.section("", "QUÉ PASÓ")
    pdf.para(
        f"El {m.opened_at:%d/%m/%Y} a las {m.opened_at:%H:%M UTC} se abrió un incidente "
        f"en {m.site_name} por {disparo_line(m.opened_trigger, m.trigger)}. "
        + (
            f"El sensor del inmueble midió un pico de {num(m.peak_pga_g, 3, 'g')}."
            if m.peak_pga_g is not None
            # [T-7.38·J] «No registró» AFIRMA sobre el sensor; lo único que consta es
            # que el documento no tiene la medición. Y dos líneas más abajo, «QUÉ
            # SIGNIFICA» clasifica la sacudida con un pico —el que `build_forensics`
            # saca del incidente— que esta misma frase acababa de negar.
            else "No consta medición de aceleración del sensor del inmueble en la "
            "ventana del evento."
        )
    )

    pdf.section("", "QUÉ SIGNIFICA")
    pdf.para(FELT_LABELS.get(m.felt_band, m.felt_band.upper()))
    pdf.para(umbral_line(umbral_desde_dict(m.felt_thresholds)), size=7, muted=True)
    if not m.calibrated:
        pdf.callout(NO_CALIBRATION, (196, 48, 43))

    pdf.section("", "QUÉ HACER AHORA")
    for action in STATUS_ACTIONS.get(m.verdict_status or "", ("Sin acciones derivadas.",)):
        pdf.para(f"·  {action}")

    pdf.section("", "EN NÚMEROS")
    pdf.field("PGA PICO", num(m.peak_pga_g, 4, "g"))
    pdf.field("ESTACIONES QUE CORROBORARON", str(m.station_count))
    pdf.field("TIEMPO DE AVISO GANADO", lead_time_text(m.lead_time_s, m.lead_time_reason))
    pdf.field("FOLIO", m.folio)
    # [T-5.26] La huella también aquí. Este es el documento que lee QUIEN DECIDE, y
    # era el único de los dos que no traía con qué verificarse.
    #
    # [T-7.38·I] Y NO es la misma que la del pericial. Nunca lo fue: el folio lleva
    # el sufijo de variante (-E / -T) y entra en `content_sha256()`, igual que la
    # onda cruda y `generated_at`. El papel prometía que coincidían, y la guarda que
    # debía cazarlo comparaba `model()` CONSIGO MISMO. Lo que sí empareja los dos
    # documentos es el folio sin su letra final.
    pdf.field("HASH DE CONTENIDO", m.content_sha256())
    pdf.para(
        "Esta huella identifica ESTA EXPORTACIÓN: no el incidente, y no este archivo. "
        "La variante técnica del mismo incidente lleva su propio folio y su propia "
        "huella: NO coinciden. Tampoco coinciden dos exportaciones de este mismo "
        "resumen, porque exportar lo añade a la cadena de custodia y porque una "
        "sección que no se pudo leer se declara y mueve el número. Lo que empareja "
        "los dos documentos es el FOLIO de arriba, idéntico salvo la letra final "
        "(-E resumen, -T pericial).",
        size=7,
        muted=True,
    )

    # [T-2.82] También en el ejecutivo: es el documento que lee quien DECIDE, y quien
    # decide es justo el que más fácilmente confundiría una declaración del cliente
    # con una certificación de la plataforma.
    pdf.section("", "MARCO NORMATIVO DECLARADO POR EL CLIENTE")
    block = compliance_block(m.compliance)
    for label, value in block.rows:
        pdf.field(label, value)
    for note in block.notes:
        pdf.callout(note)

    pdf.ln(3)
    pdf.callout(f"{DISCLAIMER_ESTADO[_firmado(m)]} {DISCLAIMER}", (20, 24, 30))
    return bytes(pdf.output())
