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

from fpdf.enums import XPos, YPos

from takab_api.compliance import compliance_block
from takab_api.dictamen import plot, sketch
from takab_api.dictamen.espectrograma import leyenda as leyenda_espectrograma
from takab_api.dictamen.layout import CONTENT_W, MARGIN, MUTED, RULE, TakabPDF
from takab_api.dictamen.model import (
    ABSENT,
    CENTROID_NOTE,
    DISCLAIMER,
    ENVELOPE_NOTE,
    FELT_LABELS,
    NARRATIVE_AI_NOTE,
    NO_CALIBRATION,
    NO_GEOMETRY,
    NO_MMI,
    NO_SPECTRUM,
    SIN_CORRELACION_EN_CATALOGO,
    SKETCH_NOTE,
    STATUS_ACTIONS,
    STATUS_LABELS,
    TS_FMT,
    ReportModel,
    huella_de_custodia,
    lead_time_text,
    num,
)

_TRACE_H = 18.0
_SKETCH_H = 78.0


def render(model: ReportModel, variant: str = "technical") -> bytes:
    """Dictamen en PDF. ``variant`` ∈ {``technical``, ``executive``}."""
    if variant == "executive":
        return _render_executive(model)
    return _render_technical(model)


# --- documento técnico --------------------------------------------------------


def _render_technical(m: ReportModel) -> bytes:
    pdf = TakabPDF(m.folio, f"DICTAMEN OPERATIVO PRELIMINAR · {m.site_name} ({m.site_code})")
    pdf.seal(m.opened_at)
    pdf.add_page()

    _cover(pdf, m)
    _sketch_section(pdf, m)
    _envelope_section(pdf, m)
    _raw_section(pdf, m)
    _channels_section(pdf, m)
    _intensity_section(pdf, m)
    _quorum_section(pdf, m)
    _post_event_section(pdf, m)
    _sensors_section(pdf, m)
    _chain_section(pdf, m)
    _custody_section(pdf, m)
    _cctv_section(pdf, m)  # 11
    _narrative_section(pdf, m)
    _compliance_section(pdf, m)
    _closing(pdf, m)
    return bytes(pdf.output())


def _cover(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.verdict_banner(m.verdict_status or "", m.verdict_label, m.verdict_signed)
    pdf.field("INMUEBLE", f"{m.site_name} ({m.site_code})")
    pdf.field("INCIDENTE", m.incident_id)
    pdf.field("APERTURA", f"{m.opened_at:{TS_FMT}}")
    pdf.field("CIERRE", f"{m.closed_at:{TS_FMT}}" if m.closed_at else "EN CURSO")
    pdf.field("SEVERIDAD · DISPARO", f"{m.severity} · {m.trigger}")
    pdf.field("EVENTO DE RED", m.event_id or "SIN EVENTO ASOCIADO")
    pdf.field("FOLIO", m.folio)
    # Se imprime la huella del CONTENIDO; la del archivo no cabe dentro de sí mismo.
    pdf.field("HASH DE CONTENIDO", m.content_sha256())
    pdf.ln(1)
    pdf.para(
        "El SHA-256 de este archivo queda registrado como evidencia inmutable del "
        "incidente. Verifíquelo desde la consola o con sha256sum contra ese registro.",
        size=7.5,
        muted=True,
    )
    if not m.calibrated:
        pdf.callout(NO_CALIBRATION, (196, 48, 43))


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
    if m.event_source == "local_quorum":
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
    pdf: TakabPDF, channel: str, values: list[float | None], flags: list[bool], unit: str
) -> None:
    """Una traza con escala propia. Escala común aplastaría los canales pequeños."""
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
    pdf.set_draw_color(20, 24, 30)
    for seg in plot.segments(values, box, scale):
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
        pdf.callout(m.raw_unavailable_reason or NO_SPECTRUM)
        return

    rate = m.raw_sample_rate or 100.0
    pdf.para(
        f"Decodificada del miniSEED archivado del evento · {rate:g} sps · cuentas del ADC.",
        size=7,
        muted=True,
    )
    for channel, samples in sorted(m.raw_waveform.items()):
        # Se diezma para el dibujo: 18 000 muestras no caben en 180 mm y fpdf2
        # tardaría más en trazarlas que la propia consulta.
        step = max(1, len(samples) // 900)
        thinned: list[float | None] = [float(v) for v in samples[::step]]
        _trace(pdf, channel, thinned, [False] * len(thinned), unit="cuentas")

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


def _post_event_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("7", "DESEMPEÑO DE LA RED")
    pdf.field("TIEMPO DE AVISO GANADO", lead_time_text(m.lead_time_s, m.lead_time_reason))
    pdf.field("ESTACIONES QUE CONTRIBUYERON", str(m.station_count))
    # [T-5.11] El rótulo dice CORRELACIÓN y no «contraste»: contrastar exige un
    # epicentro propio, y en la ruta del receptor —la normal— no lo hay. Es la
    # línea la que declara si hubo contraste de verdad o no fue verificable.
    pdf.field("CORRELACIÓN CON CATÁLOGO", m.catalog_line or SIN_CORRELACION_EN_CATALOGO)


def _sensors_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("8", "INSTRUMENTACIÓN")
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
    pdf.section("9", "CADENA DE DICTÁMENES")
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
    pdf.section("10", "CADENA DE CUSTODIA")
    if m.actions:
        pdf.set_font(pdf.mono_font, "", 6.5)
        for a in m.actions:
            pdf.cell(
                0,
                3.6,
                pdf.text_of(f"{a.ts:%Y-%m-%d %H:%M:%S}  {a.kind:<22} {a.actor}"),
                new_x=XPos.LMARGIN,
                new_y=YPos.NEXT,
            )
    else:
        pdf.para("Sin acciones registradas.", size=7.5, muted=True)

    pdf.ln(1)
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
        pdf.para("Sin objetos de evidencia archivados.", size=7.5, muted=True)


def _cctv_section(pdf: TakabPDF, m: ReportModel) -> None:
    """[T-3.12.c] Analítica de evacuación y custodia del vídeo.

    Va DESPUÉS de la cadena de custodia y no antes: sus objetos son custodia también, y
    leerlos seguidos deja claro que el clip y el miniSEED son el mismo tipo de evidencia
    con distinta política de retención.

    **Sin cámara la sección existe igual.** Omitirla dejaría al lector sin saber si este
    inmueble no tiene CCTV o si el generador se lo saltó, que es exactamente la ambigüedad
    que `NO_CCTV` está escrito para cerrar.
    """
    pdf.section("11", "EVACUACIÓN OBSERVADA (CCTV)")
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
    pdf.section("12", "ANÁLISIS")
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
    pdf.section("13", "MARCO NORMATIVO DECLARADO POR EL CLIENTE")
    block = compliance_block(m.compliance)
    for label, value in block.rows:
        pdf.field(label, value)
    if block.rows:
        pdf.ln(1)
    for note in block.notes:
        pdf.callout(note)


def _closing(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("14", "FIRMA Y DESLINDE")
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
    pdf.callout(DISCLAIMER, (20, 24, 30))


# --- documento ejecutivo ------------------------------------------------------


def _render_executive(m: ReportModel) -> bytes:
    """Una o dos páginas para quien decide, no para quien peritea."""
    pdf = TakabPDF(m.folio, f"RESUMEN EJECUTIVO · {m.site_name} ({m.site_code})")
    pdf.seal(m.opened_at)
    pdf.add_page()

    pdf.verdict_banner(m.verdict_status or "", m.verdict_label, m.verdict_signed)

    pdf.section("", "QUÉ PASÓ")
    pdf.para(
        f"El {m.opened_at:%d/%m/%Y} a las {m.opened_at:%H:%M UTC} se abrió un incidente "
        f"en {m.site_name} por {m.trigger}. "
        + (
            f"El sensor del inmueble midió un pico de {num(m.peak_pga_g, 3, 'g')}."
            if m.peak_pga_g is not None
            else "El sensor del inmueble no registró aceleración en la ventana del evento."
        )
    )

    pdf.section("", "QUÉ SIGNIFICA")
    pdf.para(FELT_LABELS.get(m.felt_band, m.felt_band.upper()))
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
    # [T-5.26] La huella también aquí. Este es el documento que lee QUIEN DECIDE,
    # y era el único de los dos que no traía con qué verificarse: el técnico la
    # imprime en portada desde siempre. Es la MISMA huella en los dos —sale del
    # contenido, no del archivo—, que es justo lo que permite comprobar que el
    # resumen y el pericial hablan del mismo incidente sin abrirlos a la vez.
    pdf.field("HASH DE CONTENIDO", m.content_sha256())
    pdf.para(
        "Esta huella identifica el CONTENIDO del dictamen, no este archivo. Es la "
        "misma que imprime la variante técnica del mismo incidente.",
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
    pdf.callout(DISCLAIMER, (20, 24, 30))
    return bytes(pdf.output())
