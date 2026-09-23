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
import math
from datetime import UTC

from fpdf.enums import MethodReturnValue, XPos, YPos

from takab_api.compliance import compliance_block
from takab_api.dictamen import plot, rotulos, sketch
from takab_api.dictamen.bitacora import rotulo as rotulo_de_accion
from takab_api.dictamen.espectrograma import leyenda as leyenda_espectrograma
from takab_api.dictamen.layout import (
    CONTENT_W,
    INK,
    MARGIN,
    MUTED,
    PRIMER_BLOQUE_MM,
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
    LEYENDA_ANILLO,
    LEYENDA_CRUZ,
    LEYENDA_DISCO,
    LEYENDA_SIN_DATO,
    MODELO_Y_RESIDUO,
    NARRATIVE_AI_NOTE,
    NO_CALIBRATION,
    NO_GEOMETRY,
    NO_MMI,
    NO_SPECTRUM,
    ONDA_NO_LEIDA,
    PERSONAS_EN_RIESGO,
    REPRODUCCION_NOTE,
    ROL_NO_RESUELTO,
    SHAKEMAP_DEGRADADO,
    SHAKEMAP_LEYENDA,
    SHAKEMAP_NO_LEIDO,
    SHAKEMAP_PENDIENTE,
    SHAKEMAP_SIN_ANILLOS,
    SHAKEMAP_SIN_COBERTURA,
    SHAKEMAP_SIN_DATOS,
    SHAKEMAP_SIN_GEOMETRIA,
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
from takab_api.geo import EARTH_RADIUS_KM
from takab_api.shakemap import calculo as shk

#: [T-7.44] Los altos de las figuras del análisis instrumental, en un solo sitio.
#: Los saltos de página se derivan de aquí con `reserva()`, no de números
#: absolutos calibrados contra el alto de A4 — que es lo que había y lo que la
#: migración a Carta dejó ciego: la hoja se acortó 17,6 mm y ninguno de los cuatro
#: topes se movió.
#:
#: ⚠️ [T-7.24] **No están todos aquí.** Los dos croquis geográficos —`_MAPA_RED_H`
#: (§7) y `_MAPA_SACUDIDA_H` (§8)— viven junto a su sección, porque su alto se
#: razona contra la tabla que va debajo y no contra las demás figuras.
#:
#: Lo que era deuda y **ya no lo es**: el censo que hace entrar a cada figura en
#: cada milímetro del tramo bajo de la página enumeraba CINCO a mano y los dos
#: croquis nunca estuvieron dentro. Desde la 2ª vuelta de esta ficha están los
#: siete (`tests/documentos/test_geometria.py::_las_figuras_del_dictamen`), el
#: barrido sabe leer círculos —un círculo sale como curvas Bézier y hasta entonces
#: no existía para la guarda— y `test_el_censo_de_figuras_las_tiene_TODAS` deriva
#: del propio `pdf.py` quién dibuja, para que la lista no vuelva a quedarse atrás.
_TRACE_H = 18.0
#: Lo que ocupa la nota de la envolvente (`ENVELOPE_NOTE`, 7 pt, dos renglones).
_NOTA_ENVOLVENTE_MM = 8.0
_SKETCH_H = 78.0
_ESPECTRO_H = 26.0
_ESPECTROGRAMA_H = 32.0

#: Lo que cada figura ocupa ADEMÁS de su recuadro: el `ln(2)` de separación, el
#: rótulo y el pie de la figura. Va explícito porque reservar sólo el recuadro
#: deja el rótulo huérfano al final de una página, que es el otro defecto que
#: estos topes evitaban sin decirlo.
_ROTULO_Y_PIE = 12.0


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
    _shakemap_section(pdf, m)
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


def _clasificacion(m: ReportModel) -> str:
    """[T-8.12 · A-053] La MISMA línea en la portada y en el ejecutivo."""
    return rotulos.clasificacion(
        m.clasificacion,
        m.clasificacion_en,
        legible=m.clasificacion_legible,
        zona=m.zona_horaria,
    )


def _cierre(m: ReportModel) -> str:
    """El campo CIERRE: la hora con su local, o los dos casos sin hora de `cierre_text`."""
    if m.closed_at is not None:
        return rotulos.instante(m.closed_at, m.zona_horaria)
    return cierre_text(None, m.state, m.cierre_sin_hora, TS_FMT)


def _cover(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.verdict_banner(m.verdict_status or "", m.verdict_label, m.verdict_signed)
    # [T-8.12 · A-053] La leyenda de la reproducción TAMBIÉN aquí, debajo del
    # veredicto: la portada es lo que se lee de un vistazo, y sin la frase afirma
    # un veredicto sobre una sacudida que no ocurrió. Es ADITIVA: se deriva igual
    # que en la §7 (`seismic_events.meta.reproduccion`) y la §7 no cambia.
    if m.reproduccion:
        pdf.callout(REPRODUCCION_NOTE)
    pdf.field("INMUEBLE", f"{m.site_name} ({m.site_code})")
    pdf.field("INCIDENTE", m.incident_id)
    # [T-8.12 · A-150] La UTC primero —es la que casa con la consola y con el
    # pie— y la hora local del inmueble al lado, que es la que lee el cliente.
    pdf.field("APERTURA", rotulos.instante(m.opened_at, m.zona_horaria))
    pdf.field("CIERRE", _cierre(m))
    # [T-8.12 · A-053] Lo que una PERSONA decidió que fue esto. Aditiva a la
    # leyenda de reproducción: aquélla la deriva el evento y ésta la pone alguien.
    pdf.field("CLASIFICACIÓN", _clasificacion(m))
    pdf.field(
        "SEVERIDAD · DISPARO",
        f"{rotulos.rotulo(rotulos.SEVERIDAD, m.severity)} · "
        f"{disparo_line(m.opened_trigger, m.trigger)}",
    )
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
    # ⚠️ Aquí decía además «compárelo contra ese registro desde la consola», y en
    # su día era falso por tres vías medidas (la consola sólo buscaba miniSEED,
    # `ReportOut` no devolvía el sha del archivo y `verify` daba 404 a un
    # `report_pdf`). [T-8.12 · A-246] `T-7.48` construyó las tres —la huella en
    # Triage, `verify` de `report_pdf` y `ReportOut.sha256`—, y por eso la frase
    # de abajo SÍ remite a Triage. Lo que no se promete es que cualquier rol
    # pueda re-verificar: `verify` de un `report_pdf` exige `dictamen_read`
    # (hallazgo `A-052`, ficha `T-8.08`).
    pdf.para(
        "Esta huella identifica ESTA EXPORTACIÓN: no el incidente, y no este archivo "
        "—el SHA-256 de un archivo no cabe dentro de sí mismo—. Es la misma que va al "
        "pie de todas las páginas. Dos exportaciones del mismo incidente NO comparten "
        "huella, y es correcto: exportar añade este documento a la cadena de custodia "
        "que imprime la §12. También la mueven una sección que no se pudo leer —el "
        "papel declara cuál y por qué— y una redacción rehecha por el asesor "
        "automático. Una huella distinta NO prueba que el dato haya cambiado. Del "
        "ARCHIVO se registra su propio SHA-256 como evidencia inmutable del incidente; "
        "ése es el que devuelve sha256sum, y la consola lo imprime ENTERO junto a este "
        "dictamen en Triage, donde además se puede re-verificar contra el objeto "
        "archivado.",
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
    # [T-8.12 · 2ª vuelta] Se proyecta ANTES del título para que el título viaje
    # con la figura: sin geometría, con su aviso.
    pdf.section(
        "1", "CROQUIS DEL EVENTO", con=_SKETCH_H + 6 if drawn is not None else PRIMER_BLOQUE_MM
    )
    if drawn is None:
        pdf.callout(NO_GEOMETRY)
        return

    # ⚠️ [T-7.44] Ésta es la caja MÁS ALTA del documento (78 mm) y era la única de
    # las cinco figuras SIN guarda de ninguna clase: ni `reserva()`, ni siquiera
    # uno de los cuatro topes absolutos. La ficha hablaba de «las cuatro»; los
    # topes eran cuatro, pero las figuras son cinco. Va DESPUÉS del `return` por
    # ausencia: un croquis sin geometría no debe saltar de página para no dibujar.
    pdf.reserva(_SKETCH_H + 6)
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
            # ⚠️ El CENTRO, no la esquina: ver la nota de `MARCA_ESTACION_MM`.
            pdf.circle(x, y, MARCA_ESTACION_MM, style="F")
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
    # El título viaja con la nota y la PRIMERA traza, que es lo que titula.
    pdf.section(
        "2",
        "ENVOLVENTE DE ACELERACIÓN POR CANAL",
        con=_NOTA_ENVOLVENTE_MM + _TRACE_H + 3 if m.series else PRIMER_BLOQUE_MM,
    )
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
    # [T-7.44] Derivado del alto real, no el `> 240` calibrado contra A4.
    pdf.reserva(_TRACE_H + 3)
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
    d = m.shaking_duration
    if d is None:
        texto = (
            "SIN DATO · no se pudo medir sobre la onda archivada. No es cero: es que no "
            "hubo traza suficiente de la que medirla."
        )
    else:
        texto = (
            f"{d.etiqueta} — intervalo en el que se acumula del 5 % al 95 % de la Intensidad "
            f"de Arias, medido sobre el canal {d.canal} del miniSEED archivado "
            f"({d.muestras} muestras, de t+{d.desde_s:.1f} s a t+{d.hasta_s:.1f} s desde el "
            "inicio de la traza). Definición de Trifunac & Brady (1975); NO es comparable con "
            "una duración «bracketed», que se mide entre cruces de un umbral de aceleración."
        )

    # ⚠️ [T-7.44] Éste es el distinto de los cuatro topes, y por eso lleva su
    # razón escrita: **este bloque no dibuja nada**. Es `cell` + `multi_cell`, las
    # dos texto, y el texto ya lo parte `set_auto_page_break`. Su `> 240` no era
    # una guarda de colisión con el pie: era una guarda de **rótulo huérfano** —
    # que el título no se quedara solo al final de una página con su párrafo en la
    # siguiente.
    #
    # Y su alto NO es constante: el párrafo lleva dentro la etiqueta, el canal,
    # las muestras y los dos instantes, y la rama de ausencia es mucho más corta
    # (medido: 16,2 mm con dato contra 9,4 sin él). Por eso se MIDE con `dry_run`
    # en vez de teclear un número — que además se ajusta solo cuando el modo
    # degradado cambia la tipografía y el texto refluye.
    pdf.set_font(pdf.body_font, "", 7)
    alto_parrafo = pdf.multi_cell(0, 3.4, texto, dry_run=True, output=MethodReturnValue.HEIGHT)
    pdf.reserva(2 + 4 + alto_parrafo)  # el `ln(2)`, el rótulo y el párrafo medido

    pdf.ln(2)
    pdf.set_font(pdf.body_font, "B", 8)
    pdf.cell(0, 4, "DURACIÓN INSTRUMENTAL DE LA SACUDIDA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(pdf.body_font, "", 7)
    pdf.multi_cell(0, 3.4, texto, new_x="LMARGIN", new_y="NEXT")


def _spectrum(pdf: TakabPDF, freqs: list[float], amps: list[float], peak_hz: float | None) -> None:
    pdf.reserva(_ESPECTRO_H + _ROTULO_Y_PIE)
    pdf.ln(2)
    pdf.set_font(pdf.body_font, "B", 8)
    pdf.cell(0, 5, pdf.text_of("ESPECTRO DE AMPLITUD"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    top = pdf.get_y()
    box = plot.Box(MARGIN + 20, top, CONTENT_W - 22, _ESPECTRO_H)
    scale = plot.scale_of([float(a) for a in amps])
    pdf.set_draw_color(*RULE)
    pdf.rect(box.x, box.y, box.w, box.h)
    pdf.set_draw_color(20, 24, 30)
    for seg in plot.segments([float(a) for a in amps], box, scale):
        pdf.polyline(seg)
    pdf.set_y(top + _ESPECTRO_H + 1)
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
    # Va DESPUÉS del `return` por figura vacía de arriba: un espectrograma sin
    # celdas no debe saltar de página para luego no dibujar nada.
    pdf.reserva(_ESPECTROGRAMA_H + _ROTULO_Y_PIE)
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
    alto = _ESPECTROGRAMA_H
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
    # ⚠️ La segunda frase se AÑADE, y sólo cuando el mapa de la sacudida de verdad
    # va a imprimir un modelo y un residuo. Iba dentro de `NO_MMI` y se imprimía
    # siempre: un documento cuyo mapa está `pendiente` —el caso NORMAL, porque se
    # calcula por evento— prometía aquí modelo y residuo y tres secciones más
    # abajo decía «NO CALCULADO TODAVÍA». Se deriva del bloque, no de la intención.
    pdf.callout(f"{NO_MMI} {MODELO_Y_RESIDUO}" if _reporta_modelo_y_residuo(m.shakemap) else NO_MMI)


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


def _dibujo_de_la_red(m: ReportModel) -> sketch.Sketch | None:
    """La proyección del mapa de la §7, o `None` si no hay geometría que situar."""
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
    return sketch.project(puntos, CONTENT_W, _MAPA_RED_H)


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
    dibujo = _dibujo_de_la_red(m)
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
            # ⚠️ El CENTRO, no la esquina: ver la nota de `MARCA_ESTACION_MM`.
            pdf.circle(x, y, MARCA_ESTACION_MM)
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
    # [T-8.12 · 2ª vuelta] Sin la leyenda de reproducción, lo primero es el MAPA:
    # el título viaja con él (se quedaba solo al pie con el mapa en la otra hoja).
    abre_con_mapa = not m.reproduccion and m.estaciones and _dibujo_de_la_red(m) is not None
    pdf.section(
        "7", "RED DE ESTACIONES", con=_MAPA_RED_H + 6 if abre_con_mapa else PRIMER_BLOQUE_MM
    )
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
    # [T-8.12 · A-144] «NIVEL» y no «TIER», y el nivel en castellano: la columna
    # imprimía `evacuate_or_hold` partido en dos renglones. Se ensancha lo que
    # pierde ESTACIÓN porque sus rótulos son los del panel del gabinete.
    with pdf.table(col_widths=(36, 17, 20, 20, 20, 24, 21), text_align="LEFT") as table:
        head = table.row()
        for h in (
            "ESTACIÓN",
            "DIST (km)",
            "ESPERADO (s)",
            "MEDIDO (s)",
            "PICO (g)",
            "UMBRAL (g)",
            "NIVEL",
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
            row.cell(pdf.text_of(rotulos.rotulo(rotulos.NIVEL, e.tier) if e.tier else "S/D"))


#: [T-7.24] Título de la sección del mapa de la sacudida, en un solo sitio.
#:
#: Es constante porque la prueba lo usa para trocear el render por sección, y
#: `Capturado.seccion()` busca por TÍTULO y no por número —los números renumeran
#: en cuanto se inserta una sección, y una prueba que se rompa al renumerar no
#: está comprobando lo que dice comprobar—.
MAPA_SACUDIDA = "MAPA DE LA SACUDIDA"

#: Alto del mapa de la sacudida, en mm. El mismo que el mapa de la red (62 mm) y
#: por la misma razón: debajo va su tabla, y las dos tienen que caber juntas para
#: poder leerse de una vez. Un mapa en una página y su tabla en la siguiente
#: obliga a pasar hojas para saber qué punto es qué fila — y aquí, además, la
#: tabla es la que trae el residuo, que es el producto de la figura.
_MAPA_SACUDIDA_H = 62.0

#: Radio, en mm, del marcador de un inmueble en los croquis. Se nombra porque la
#: guarda de los anillos separa por él lo que es marcador de lo que es anillo del
#: modelo, y un número mágico compartido entre el render y su prueba se
#: desincroniza sin avisar.
#:
#: ⚠️ **Y porque las tres figuras geográficas centraban el marcador de dos maneras
#: distintas.** `_sketch_section` y `_mapa_de_la_red` escribían
#: `circle(x=x - 1.3, y=y - 1.3, radius=1.3)` —la convención de ESQUINA—, y en
#: fpdf2 2.8.7 `circle(x, y, r)` hace `ellipse(x - r, y - r, 2r, 2r)`: `x, y` es el
#: CENTRO, así que esas dos figuras dibujaban cada estación 1.3 mm arriba y a la
#: izquierda de su punto proyectado. (La documentación de fpdf2 dice «upper-left
#: bounding box» y su propio código la desmiente; el cambio fue en su 2.8.1.) Lo
#: que prueba la semántica es
#: `tests/documentos/test_geometria.py::test_el_barrido_de_geometria_VE_los_CIRCULOS`,
#: que planta `circle(100, 100, 20)` y encuentra el borde en 120 mm; que ninguna
#: llamada vuelva a compensar el radio a mano lo vigila
#: `test_ninguna_figura_dibuja_un_circulo_por_su_ESQUINA`.
MARCA_ESTACION_MM = 1.3

#: Radio del marcador del inmueble de ESTE dictamen: es el sujeto del documento,
#: no un testigo, y se distingue por tamaño. **No por dejar de ser un disco
#: lleno**: el relleno significa «esto es una medición» y eso vale para los dos.
MARCA_PROPIA_MM = MARCA_ESTACION_MM * 1.6

#: Grados de latitud por kilómetro, para ENCUADRAR (nunca para medir).
#:
#: ⚠️ La distinción importa: lo que se mide sale de `haversine_km` y de la barra de
#: escala del propio croquis. Esto sólo decide qué trozo de mundo entra en el
#: recuadro, y por eso una aproximación esférica basta y se dice que lo es.
_KM_POR_GRADO = math.pi * EARTH_RADIUS_KM / 180.0

#: Margen del encuadre sobre el anillo más grande. Sin él, el círculo exterior
#: queda tangente al marco y la línea se confunde con el borde del recuadro.
_MARGEN_ENCUADRE = 1.05

#: [T-7.24 · 2ª vuelta] Las columnas de la tabla de la sacudida, EN ORDEN.
#:
#: Se nombran aquí y no dentro del bucle porque la prueba que casa cada celda con
#: su columna necesita la misma lista: las dos celdas centrales —MEDIDO (g) y
#: MODELO (g)— se podían intercambiar sin que nada se pusiera rojo, y el papel
#: habría impreso la predicción del modelo bajo el rótulo «MEDIDO». Es
#: literalmente «el dictamen presenta lo modelado como medido», la frase que
#: `RO-7.f` dice impedir. Medido el 2026-09-21 con las dos líneas intercambiadas:
#: 373 passed.
COLUMNAS_DE_LA_SACUDIDA = (
    "INMUEBLE",
    "DIST (km)",
    "MEDIDO (g)",
    "MODELO (g)",
    "MEDIDO (cm/s)",
    "RESIDUO log10",
)

#: Rótulo del estado del mapa en la ficha de cabecera de la sección.
_ESTADO_MAPA = {
    shk.ESTADO_COMPLETO: "COMPLETO · medido y modelado",
    shk.ESTADO_SOLO_OBSERVADO: "DEGRADADO · sólo medido",
    shk.ESTADO_SIN_DATOS: "SIN MEDIDAS EN LA VENTANA",
    shk.ESTADO_PENDIENTE: "NO CALCULADO TODAVÍA",
}


def _residuo_celda(residuo: float | None) -> str:
    """El residuo CON SU SIGNO, o la ausencia declarada.

    El signo es todo lo que dice: positivo = ese inmueble sacudió MÁS de lo que la
    ley predice a su distancia. Sin él, `0.30` y `-0.30` se imprimen casi igual y
    afirman lo contrario. `+` explícito por eso.
    """
    if residuo is None:
        return ABSENT
    return f"{residuo:+.2f}"


def _epicentro_del_mapa(b) -> str:  # noqa: ANN001 - model.ShakemapBlock
    """De dónde salió el epicentro con que se modeló, y con qué estado.

    `fuente` es quién lo localizó y `procedencia` es el estado del glosario
    compartido: son cosas distintas y las dos hacen falta. El centroide de nuestro
    propio cuórum es un epicentro NUESTRO, y presentarlo sin decirlo lo
    confundiría con la solución de una agencia — el mismo defecto que
    `EPICENTRO_REUBICADO` cazó en la §1.
    """
    if b.epicentro_lat is None or b.epicentro_lon is None:
        return "NO CITADO · sin él no hay capa modelada"
    magnitud = "M " + num(b.epicentro_magnitud, 1) if b.epicentro_magnitud is not None else ABSENT
    # [T-8.12 · A-144] `seismic_events.source` en castellano; una fuente libre
    # («SSN») se imprime tal cual, que ya es un nombre propio.
    fuente = (
        rotulos.FUENTE_DEL_EVENTO.get(b.epicentro_fuente, b.epicentro_fuente)
        if b.epicentro_fuente
        else "fuente no declarada"
    )
    procedencia = b.epicentro_procedencia or "procedencia no declarada"
    return f"{b.epicentro_lat:.2f}, {b.epicentro_lon:.2f} · {magnitud} · {fuente} · {procedencia}"


def _reporta_modelo_y_residuo(b) -> bool:  # noqa: ANN001 - model.ShakemapBlock
    """¿Va a imprimir de verdad este documento una predicción del modelo y su residuo?

    **Derivado de lo que la sección va a poder imprimir**, no de una intención
    escrita a mano: es lo que impide que la §5 prometa lo que la §8 no calcula.
    Las tres puertas son las mismas por las que la sección se rinde —la lectura
    falló, el cálculo no ha corrido, o corrió y no hay medidas—; la que de verdad
    decide es la última, y exige LAS DOS COSAS que la frase promete.

    ⚠️ Exigía sólo la columna modelada, y la frase promete «lo que predice … y el
    residuo entre las dos». No es lo mismo: `calculo._punto` le da `pga_g_modelada`
    a un inmueble MUDO con distancia —el modelo no necesita que nadie midiera— y
    le deja el residuo en `None`, porque un residuo exige la medida. Un documento
    cuyo modelo llegara sólo por inmuebles mudos prometía en la §5 un residuo con
    la columna RESIDUO entera en SIN DATO. Prometer de menos no es una falsedad;
    prometer un número que no está, sí.
    """
    if b.fallo_de_lectura is not None or b.estado == shk.ESTADO_PENDIENTE:
        return False
    if b.estado == shk.ESTADO_SIN_DATOS or not b.puntos:
        return False
    return _hay_modelo_por_punto(b) and any(p.residuo_log10 is not None for p in b.puntos)


def _hay_modelo_por_punto(b) -> bool:  # noqa: ANN001 - model.ShakemapBlock
    """¿Imprime la tabla la predicción del modelo para algún inmueble?

    Es la capa 3, y vive POR PUNTO: los anillos son la capa 2 y pueden faltar sin
    que falte el modelo. Confundir las dos es lo que hacía que el papel negara el
    residuo que imprimía en la fila de al lado.
    """
    return any(p.pga_g_modelada is not None for p in b.puntos)


def _estado_derivado(b) -> str:  # noqa: ANN001 - model.ShakemapBlock
    """El estado que ESTE documento imprime, en el vocabulario del cálculo.

    Se deriva en el vocabulario —y no directamente en el rótulo— para que se
    pueda comparar con `b.estado` sin traducir: comparar rótulos obligaba a que
    cada matiz nuevo del rótulo pareciera una discrepancia con el snapshot.
    """
    if b.estado == shk.ESTADO_PENDIENTE:
        return shk.ESTADO_PENDIENTE
    if b.estado == shk.ESTADO_SIN_DATOS or not b.puntos:
        return shk.ESTADO_SIN_DATOS
    # ⚠️ El modelo son las DOS capas, y basta una para que el papel lo imprima.
    # Con `not b.anillos` a secas, el caso REAL del M5.0 con el foco a 48 km
    # —todos los niveles bajo la superficie, y la tabla con su MODELO y su
    # RESIDUO— se rotulaba «DEGRADADO · sólo medido».
    if b.anillos or _hay_modelo_por_punto(b):
        return shk.ESTADO_COMPLETO
    return shk.ESTADO_SOLO_OBSERVADO


def _estado_del_mapa(b) -> str:  # noqa: ANN001 - model.ShakemapBlock
    """El rótulo dice lo que ESTE documento imprime, no cómo se llama el snapshot.

    ⚠️ Se derivaba de `b.estado` a secas, y un snapshot incoherente imprimía
    «COMPLETO · medido y modelado» y seis líneas después «MAPA DEGRADADO: … no se
    dibuja la capa modelada». Medido el 2026-09-21 con `estado='completo'`,
    `anillos=[]` y sin epicentro. El criterio ya existía en la sección —un
    `completo` con cero medidas se imprime como SIN MEDIDAS, con su prueba— y
    estaba aplicado a la mitad de los casos.

    ⚠️ Y la primera versión de esa derivación miraba sólo `b.anillos`, así que
    **denunciaba como incoherente un snapshot coherente**: el M5.0 con el foco a
    48 km deja los dos niveles bajo la superficie y aun así modela cada inmueble.
    La coletilla acusa al dato de origen; acusarlo en falso es peor que no
    acusarlo, porque enseña a ignorar la coletilla.

    Lo que dice el snapshot **no se tira**: si discrepa del documento, se imprime
    al lado. Un dictamen es evidencia y esa discrepancia es un hecho auditable.
    """
    if b.fallo_de_lectura is not None:
        return "NO DISPONIBLE · la lectura del snapshot falló"
    derivado = _estado_derivado(b)
    rotulo = _ESTADO_MAPA[derivado]
    if derivado == b.estado:
        return rotulo
    return f"{rotulo} · el snapshot se declara «{b.estado}»"


def _falta_para_modelar(b) -> str:  # noqa: ANN001 - model.ShakemapBlock
    """Qué falta EXACTAMENTE para dibujar la capa modelada, nombrado uno a uno.

    ⚠️ La frase del aviso decía siempre «sin epicentro y magnitud citados», y el
    caso que el criterio de la ficha nombra —«degradado y declarado cuando no hay
    magnitud»— imprime el epicentro dos líneas más arriba. Medido el 2026-09-21
    sobre la fixture que monta ese caso, `tests/dictamen/test_mapa_de_la_sacudida
    .py::_degradado_sin_magnitud(sin_epicentro=False)` —`epicentro_lat=16.80`,
    `epicentro_lon=-99.50`, `epicentro_magnitud=None`—: el papel imprimía
    «EPICENTRO DEL MODELO · 16.80, -99.50 · SIN DATO · SSN · confirmado» y justo
    debajo «sin epicentro y magnitud citados». Se nombra la fixture y no sólo los
    tres parámetros porque la PROCEDENCIA no está entre ellos y sale de ella: esta
    cita decía «preliminar», que con esos parámetros no sale.

    ⚠️ **Y aquí NO hay una rama para `b.fuera_de_alcance`.** La hubo, con un
    comentario que decía que «no es teórica», y era teórica. Medido el 2026-09-21
    de dos maneras: (1) quitándola y volviéndola a poner,
    `tests/dictamen/test_mapa_de_la_sacudida.py` da `30 passed` **en los dos
    casos** — ningún test distingue el papel con la rama del papel sin ella;
    (2) con un espía en esta función sobre
    `tests/dictamen` + `tests/documentos` + `tests/shakemap` enteros (573 pruebas),
    el censo de ramas ejercidas salió `sin epicentro NI magnitud → 8`,
    `sin magnitud → 1` y las otras tres —`sin epicentro` sola, `fuera_de_alcance`
    y el cierre— a **cero**.

    Y no es una casualidad del muestreo: `fuera_de_alcance` sólo se puebla si
    `modelable` (`shakemap/calculo.py::calcula` — hubo medida, hay epicentro y hay
    magnitud), y con eso `_punto` modela todo inmueble que traiga `dist_km` — que
    por la ruta real los trae todos, porque esa distancia sólo falta cuando no hay
    epicentro (`estaciones.py`: `dist` sale del mismo `sismo` del que sale
    `epicentro_lat`). Así que `_hay_modelo_por_punto` es cierto y quien habla es
    `SHAKEMAP_SIN_ANILLOS` dos ramas antes de llegar aquí. Lo fija
    `tests/shakemap/test_calculo.py::
    test_declarar_NIVELES_SUPRIMIDOS_implica_haber_MODELADO_cada_inmueble`: el día
    que ese invariante se rompa, esa guarda se pone roja y esta rama vuelve — con
    su caso construido a propósito, no supuesto.

    Las dos ramas que quedan sin ejercer (`sin epicentro` sola y el cierre) se
    conservan porque totalizan la función sobre un `ShakemapBlock` cualquiera y no
    afirman nada que el dato pueda desmentir; la que se fue afirmaba cobertura.
    """
    sin_epicentro = b.epicentro_lat is None or b.epicentro_lon is None
    sin_magnitud = b.epicentro_magnitud is None
    if sin_epicentro and sin_magnitud:
        return "el epicentro y la magnitud citados."
    if sin_epicentro:
        return "el epicentro citado; la magnitud sola no sitúa la capa."
    if sin_magnitud:
        return "la magnitud citada; el epicentro solo no da un nivel de PGA."
    return "la capa modelada del snapshot, pese a estar citados el epicentro y la magnitud."


def _niveles_suprimidos(b) -> str:  # noqa: ANN001 - model.ShakemapBlock
    """Los niveles que el modelo consideró y no pudo dibujar, cada uno con su razón.

    La frase de cada motivo sale de `calculo.MOTIVOS_FUERA` —el mismo diccionario
    que la consola— y no se escribe aquí: dos redacciones del mismo motivo
    acabarían discrepando sobre el mismo mapa.

    Con la lista vacía **no se inventa una razón**. Un snapshot puede no
    declararlos (los anteriores a `T-7.24`, o un modelo sin un solo nivel), y eso
    es exactamente lo que se dice.
    """
    if not b.fuera_de_alcance:
        return "el snapshot no declara cuáles."
    return (
        "; ".join(
            f"{rotulos.rotulo(rotulos.UMBRAL, n.umbral)} ({num(n.pga_g, 3, 'g')}) — "
            f"{shk.MOTIVOS_FUERA.get(n.motivo, n.motivo)}"
            for n in b.fuera_de_alcance
        )
        + "."
    )


def _puntos_del_mapa(b):  # noqa: ANN001, ANN202 - model.ShakemapBlock
    """Lo que hay que proyectar: los inmuebles, el epicentro y el ENCUADRE.

    Los puntos `bounds` no se dibujan: existen para que `project` meta en el
    recuadro el anillo más grande del modelo. Sin ellos el encuadre lo marcarían
    los inmuebles —que están juntos— y un anillo de 100 km se saldría de la caja y
    se pintaría encima del resto de la página, porque `rect`/`circle` no recortan.

    Se declaran aquí, y no ensanchando el recuadro, porque lo que hay que
    conservar es que **una sola escala** valga para los puntos, los anillos y la
    barra: dos encuadres distintos serían dos escalas que acabarían discrepando.

    ⚠️ **El sufijo `_mudo` viaja hasta el dibujo a propósito.** Un inmueble sin
    `pga_g` no midió, y hasta la 2ª vuelta de `T-7.24` se pintaba como DISCO
    LLENO, que la leyenda define como «SACUDIDA MEDIDA en ese inmueble», mientras
    la tabla de debajo decía «SIN DATO» de ese mismo inmueble. La figura afirmaba
    lo que la tabla negaba. `sketch.Projected` sólo lleva `kind`, así que la
    ausencia viaja en el `kind` — que es el campo que el dibujo mira.
    """
    puntos = [
        sketch.Point(
            p.lat,
            p.lon,
            p.site_code,
            ("site" if p.propio else "station") + ("" if p.pga_g is not None else "_mudo"),
        )
        for p in b.puntos
        if p.lat is not None and p.lon is not None
    ]
    if b.epicentro_lat is None or b.epicentro_lon is None:
        return puntos
    puntos.append(sketch.Point(b.epicentro_lat, b.epicentro_lon, "EPICENTRO", "epicenter"))
    if not b.anillos:
        return puntos
    radio = max(a.radio_km for a in b.anillos) * _MARGEN_ENCUADRE
    dlat = radio / _KM_POR_GRADO
    kx = math.cos(math.radians(b.epicentro_lat))
    dlon = dlat / kx if kx else dlat
    puntos += [
        sketch.Point(b.epicentro_lat + dlat, b.epicentro_lon, "", "bounds"),
        sketch.Point(b.epicentro_lat - dlat, b.epicentro_lon, "", "bounds"),
        sketch.Point(b.epicentro_lat, b.epicentro_lon + dlon, "", "bounds"),
        sketch.Point(b.epicentro_lat, b.epicentro_lon - dlon, "", "bounds"),
    ]
    return puntos


def _leyenda_del_mapa(b, dibujo) -> str:  # noqa: ANN001 - model.ShakemapBlock, sketch.Sketch
    """La leyenda nombra SÓLO los símbolos que esta figura dibuja.

    ⚠️ Era una frase cerrada que se imprimía pasara lo que pasara. Medido el
    2026-09-21: un documento DEGRADADO —sin capa modelada y sin epicentro—
    prometía «ANILLO DISCONTINUO …» y «La cruz es el epicentro» sobre una figura
    sin un solo anillo y sin cruz; y en el caso SIN COORDENADAS la leyenda se
    imprimía igual, porque iba ANTES de la figura y la figura se rendía por
    dentro. Una leyenda que nombra símbolos ausentes enseña a leer una figura que
    no está, y es peor que no tener leyenda: la que sobra no se distingue de la
    que falta.

    Se decide sobre `dibujo.points`, que es lo PROYECTADO, no sobre el bloque: un
    punto sin coordenadas no llega a la figura y por tanto no tiene símbolo que
    explicar.
    """
    clases = {p.kind for p in dibujo.points}
    piezas = [SHAKEMAP_LEYENDA]
    if clases & {"site", "station"}:
        piezas.append(LEYENDA_DISCO)
    if clases & {"site_mudo", "station_mudo"}:
        piezas.append(LEYENDA_SIN_DATO)
    if "epicenter" in clases and b.anillos:
        piezas.append(LEYENDA_ANILLO)
    if "epicenter" in clases:
        piezas.append(LEYENDA_CRUZ)
    return " ".join(piezas)


def _mapa_de_la_sacudida(pdf: TakabPDF, b, dibujo) -> None:  # noqa: ANN001 - ShakemapBlock
    """La figura: discos MEDIDOS sobre anillos MODELADOS, con una sola escala.

    [T-7.24] Vectorial y sin una sola petición externa, por la misma razón que el
    mapa de la red: un documento de evidencia que dependa de que un servidor de
    tiles siga en pie dentro de cinco años no es evidencia. Y con la MISMA
    proyección (`sketch.project`), así que las tres figuras geográficas del
    documento miden igual.

    **Lo medido y lo modelado no comparten codificación** (`D-08 · §A.3`): disco
    lleno para lo que un sensor registró, anillo de trazo discontinuo para lo que
    la ley predice, y círculo VACÍO para el inmueble que no publicó — que no es
    ninguna de las dos cosas. La procedencia viaja en el dato y también en la
    tinta.

    ⚠️ **El radio de los anillos sale de la escala del croquis**, no de una
    constante de página. Es la lección que costó la guarda que esta ficha
    sustituye: dos capas de MapLibre con `circle-radius` en píxeles afirmaban
    ~22 km a zoom 8.5 y ~1 km a zoom 13, o sea que la misma figura cambiaba de
    significado físico con cada rueda del ratón.

    `dibujo` llega YA proyectado y no se recalcula aquí: quien llama necesita
    saber si hay figura **antes** de imprimir la leyenda, y dos proyecciones del
    mismo bloque son dos escalas que acabarían discrepando.
    """
    # ⚠️ `rect`/`circle`/`line` NO disparan el salto de página de fpdf2
    # (`set_auto_page_break` sólo mira texto): sin esto la figura se pinta encima
    # del filete del pie.
    pdf.reserva(_MAPA_SACUDIDA_H + 6)
    top = pdf.get_y()
    pdf.set_draw_color(*RULE)
    pdf.rect(MARGIN, top, CONTENT_W, _MAPA_SACUDIDA_H)

    epicentro = next((p for p in dibujo.points if p.kind == "epicenter"), None)
    if epicentro is not None:
        _anillos_del_modelo(pdf, b, dibujo, MARGIN + epicentro.x, top + epicentro.y)

    for p in dibujo.points:
        if p.kind == "bounds":
            continue
        x, y = MARGIN + p.x, top + p.y
        if p.kind == "epicenter":
            pdf.set_draw_color(196, 48, 43)
            pdf.set_line_width(0.5)
            pdf.line(x - 2.4, y, x + 2.4, y)
            pdf.line(x, y - 2.4, x, y + 2.4)
            pdf.set_line_width(0.2)
            pdf.set_draw_color(*RULE)
        elif p.kind.endswith("_mudo"):
            # Círculo VACÍO: ese inmueble NO publicó. Rellenarlo lo convertiría en
            # una medición —es lo que hacía— y un cero por un silencio afirma que
            # no se movió (regla de oro 7). Trazo CONTINUO, para que tampoco se
            # confunda con el anillo discontinuo del modelo.
            pdf.set_draw_color(*INK)
            radio = MARCA_PROPIA_MM if p.kind == "site_mudo" else MARCA_ESTACION_MM
            pdf.circle(x, y, radio, style="D")
            pdf.set_draw_color(*RULE)
        else:
            # Disco LLENO = medición, siempre: el inmueble del dictamen se
            # distingue por el tamaño, no por dejar de ser una medida.
            pdf.set_fill_color(*INK)
            radio = MARCA_PROPIA_MM if p.kind == "site" else MARCA_ESTACION_MM
            pdf.circle(x, y, radio, style="F")
        pdf.set_xy(x + 2.5, y - 2)
        pdf.set_font(pdf.body_font, "", 6)
        pdf.cell(28, 3, pdf.text_of(p.label))

    _relleno_por_defecto(pdf)
    pdf.set_draw_color(*INK)
    bar_y = top + _MAPA_SACUDIDA_H - 6
    pdf.line(MARGIN + 5, bar_y, MARGIN + 5 + dibujo.scale_bar_mm, bar_y)
    pdf.set_xy(MARGIN + 5, bar_y + 0.5)
    pdf.set_font(pdf.body_font, "", 6)
    pdf.cell(30, 3, pdf.text_of(f"{dibujo.scale_bar_km:g} km"))
    pdf.set_xy(MARGIN + CONTENT_W - 12, top + 3)
    pdf.set_font(pdf.body_font, "B", 7)
    pdf.cell(8, 4, pdf.text_of("N ↑"))
    pdf.set_y(top + _MAPA_SACUDIDA_H + 2)


def _anillos_del_modelo(pdf: TakabPDF, b, dibujo, cx: float, cy: float) -> None:  # noqa: ANN001
    """Los niveles de PGA del modelo, en trazo discontinuo y con su valor.

    Discontinuo a propósito y no «más claro»: un color pálido se lee como una
    medición con menos confianza, y esto no es una medición de nada — es lo que
    la ley predice a esa distancia. La forma dice lo que el color no puede
    (misma doctrina que `T-6.09` con la banda de sacudida).
    """
    pdf.set_draw_color(*MUTED)
    pdf.set_dash_pattern(dash=1.2, gap=1.2)
    for anillo in sorted(b.anillos, key=lambda a: a.radio_km):
        radio_mm = anillo.radio_km * dibujo.mm_por_km
        pdf.circle(cx, cy, radio_mm, style="D")
        pdf.set_xy(cx - 12, cy - radio_mm - 3.4)
        pdf.set_font(pdf.body_font, "", 6)
        pdf.cell(24, 3, pdf.text_of(f"{num(anillo.pga_g, 3, 'g')} · {anillo.radio_km:g} km"))
    pdf.set_dash_pattern()
    pdf.set_draw_color(*RULE)


def _shakemap_section(pdf: TakabPDF, m: ReportModel) -> None:
    """[T-7.24] Cuánto sacudió en cada inmueble, y cuánto tocaba a esa distancia.

    Es la sección que ejecuta `T-3.09` en el papel. Lo que la justifica no es la
    figura: es el **residuo**. Un punto que sacude el triple de lo que la ley
    predice para su distancia es lo único que el modelo no sabía —puede ser suelo
    blando, puede ser el edificio— y es lo que un ingeniero necesita ver.

    El snapshot se lee UNA vez, en el builder, con la misma función que sirve al
    endpoint (`takab_api.shakemap.lectura.leer`). Aquí no se calcula nada: si esta
    sección recalculara, el papel y la consola dibujarían cada uno su mapa del
    mismo sismo y el que discrepa lleva una firma debajo.

    ⚠️ **La proyección se hace ANTES de la leyenda.** Lo que hay que saber para
    imprimir una leyenda honesta es qué símbolos va a haber, y eso sólo lo sabe el
    croquis proyectado. Con la leyenda delante y la figura rindiéndose por dentro,
    el papel describía un dibujo que no existía.
    """
    pdf.section("8", MAPA_SACUDIDA)
    b = m.shakemap
    pdf.field("ESTADO DEL MAPA", _estado_del_mapa(b))
    if b.fallo_de_lectura is not None:
        # El anexo no puede costar el dictamen (misma doctrina que `_cctv_block` y
        # que la onda cruda). Se declara el fallo y el documento sigue.
        pdf.callout(SHAKEMAP_NO_LEIDO)
        return
    if b.estado == shk.ESTADO_PENDIENTE:
        # No es un fallo: el mapa se calcula POR EVENTO, no en vivo. Callarlo
        # dejaría un hueco que se lee como «no sacudió en ninguna parte».
        pdf.callout(SHAKEMAP_PENDIENTE)
        return

    pdf.field("CALCULADO", f"{b.calculado_en:{TS_FMT}}" if b.calculado_en else ABSENT)
    # Con qué ley, para que un dictamen regenerado dentro de un año no presente el
    # modelo de hoy como si fuera el que se usó entonces.
    pdf.field("LEY DEL MODELO", b.ley or "NO SE MODELÓ")
    pdf.field("RADIO DE COBERTURA", num(b.cobertura_km, 0, "km"))
    pdf.field("EPICENTRO DEL MODELO", _epicentro_del_mapa(b))

    if b.estado == shk.ESTADO_SIN_DATOS or not b.puntos:
        # El `or not b.puntos` no es redundante: un snapshot que se declarase
        # `completo` con cero medidas es incoherente, y sin esto la sección
        # dibujaría una tabla con sólo cabecera — un rótulo que promete un dato
        # que no hay, que es peor que no tener la sección. Se dice lo único
        # verificable: no hay medidas que imprimir.
        pdf.callout(SHAKEMAP_SIN_DATOS)
        return
    if not b.anillos and _hay_modelo_por_punto(b):
        # ⚠️ NO es el caso degradado, y por eso no lleva su frase. El modelo
        # corrió y la tabla de debajo imprime su predicción y el residuo; lo que
        # no hay es un nivel dibujable. Es el caso REAL del M5.0 con el foco a
        # 48 km, y con la frase del degradado el documento negaba —ocho líneas
        # antes— el residuo +1.35 que él mismo imprime.
        pdf.callout(f"{SHAKEMAP_SIN_ANILLOS} {_niveles_suprimidos(b)}")
    elif not b.anillos:
        # Sin con qué comparar no hay capa modelada, y el mapa DICE qué falta —en
        # vez de recitar siempre la misma pareja— para no desmentir al campo del
        # epicentro que acaba de imprimirse dos líneas más arriba.
        pdf.callout(f"{SHAKEMAP_DEGRADADO} {_falta_para_modelar(b)}")

    dibujo = sketch.project(_puntos_del_mapa(b), CONTENT_W, _MAPA_SACUDIDA_H)
    if dibujo is None or dibujo.mm_por_km <= 0:
        # Declarar la ausencia, no dejar el hueco: un marco vacío se lee como «no
        # hay inmuebles», que es lo contrario de lo que dice la tabla de debajo. Y
        # sin figura no se imprime leyenda de figura: describiría un dibujo que no
        # está.
        pdf.callout(SHAKEMAP_SIN_GEOMETRIA)
    else:
        # La leyenda va ANTES de la figura: condiciona todo lo que se lee debajo.
        # Un anillo y un disco en la misma caja, sin esta frase, se leen como dos
        # medidas de lo mismo.
        pdf.callout(_leyenda_del_mapa(b, dibujo))
        pdf.callout(SHAKEMAP_SIN_COBERTURA)
        _mapa_de_la_sacudida(pdf, b, dibujo)

    if b.anillos:
        # ⚠️ Los niveles van TAMBIÉN como texto, y no sólo rotulados sobre su
        # anillo. El rótulo de un anillo se coloca en `cy - radio_mm - 3.4` y el
        # de un inmueble en su punto proyectado: ninguno mira al otro, y el papel
        # no tiene motor de etiquetado que resuelva colisiones.
        #
        # Medido el 2026-09-21 sobre las CAJAS DE TEXTO del propio render (espía
        # de `cell`, sin rasterizar). El escenario ya no se cuenta de memoria: lo
        # monta y lo vuelve a medir `tests/dictamen/test_mapa_de_la_sacudida.py::
        # test_el_rotulo_del_ANILLO_y_la_etiqueta_de_un_INMUEBLE_se_pisan` —los dos
        # inmuebles de siempre y un tercero a 100 km al NORTE del epicentro, o sea
        # justo encima del anillo de ese nivel—: el rótulo «0.020 g · 100 km» ocupa
        # una caja de 24 × 3 mm que empieza en x = 94.64, y la etiqueta «NORTE-1»
        # otra de 28 × 3 mm en x = 109.14 y 1.40 mm más abajo; se pisan en
        # 9.50 × 1.60 mm. La `y` ABSOLUTA no se cita porque depende de dónde caiga
        # la §8 en la página —la versión anterior de este comentario daba una
        # (86.87 / 88.27) que este árbol no reproduce—. Un rótulo tapado es un dato
        # perdido, así que el dato vive además donde nada lo pisa.
        pdf.para(
            "NIVELES DEL MODELO · "
            + " · ".join(
                f"{num(a.pga_g, 3, 'g')} a {a.radio_km:g} km"
                for a in sorted(b.anillos, key=lambda a: a.radio_km)
            ),
            size=7.5,
            muted=True,
        )

    pdf.set_font(pdf.body_font, "", 7)
    with pdf.table(col_widths=(46, 22, 24, 24, 24, 26), text_align="LEFT") as table:
        head = table.row()
        for h in COLUMNAS_DE_LA_SACUDIDA:
            head.cell(pdf.text_of(h))
        for p in b.puntos:
            row = table.row()
            etiqueta = f"{p.site_name} ({p.site_code})"
            # ⚠️ El ORDEN de estas celdas ES el significado de la tabla: la
            # cabecera dice cuál es MEDIDO y cuál MODELO, y una celda en la
            # columna de al lado imprime la predicción bajo el rótulo de la
            # medición. Lo vigila `test_cada_celda_sale_BAJO_SU_COLUMNA`, que casa
            # cabecera y fila por posición.
            row.cell(pdf.text_of(etiqueta + (" ·" if p.propio else "")))
            row.cell(pdf.text_of(num(p.dist_km, 0)))
            row.cell(pdf.text_of(num(p.pga_g, 4)))
            row.cell(pdf.text_of(num(p.pga_g_modelada, 4)))
            row.cell(pdf.text_of(num(p.pgv_cms, 2)))
            row.cell(pdf.text_of(_residuo_celda(p.residuo_log10)))


def _post_event_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("9", "DESEMPEÑO DE LA RED")
    pdf.field("TIEMPO DE AVISO GANADO", lead_time_text(m.lead_time_s, m.lead_time_reason))
    pdf.field("ESTACIONES QUE CONTRIBUYERON", str(m.station_count))
    # [T-5.11] El rótulo dice CORRELACIÓN y no «contraste»: contrastar exige un
    # epicentro propio, y en la ruta del receptor —la normal— no lo hay. Es la
    # línea la que declara si hubo contraste de verdad o no fue verificable.
    pdf.field("CORRELACIÓN CON CATÁLOGO", m.catalog_line or SIN_CORRELACION_EN_CATALOGO)
    # [T-7.25] A quién se le puede preguntar, y por qué el SSN no está.
    pdf.field("CONSULTA A FUENTES EXTERNAS", m.fuentes_externas)


def _sensors_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("10", "INSTRUMENTACIÓN")
    if not m.sensors:
        pdf.callout("SIN SENSORES ACTIVOS REGISTRADOS PARA ESTE INMUEBLE.")
        return
    for sn in m.sensors:
        # [T-8.12 · A-144] `STRUCTURAL` y `concrete_column` salían crudos. Y el
        # MODELO pasa al valor: en el rótulo, un nombre de modelo largo —un dato de
        # la base— empujaba el rótulo sobre el valor (A-146).
        montaje = sn.get("mount")
        pdf.field(
            rotulos.rotulo(rotulos.SENSOR, sn.get("kind")),
            f"{sn.get('model') or 'modelo no declarado'} · "
            f"serie {sn.get('serial') or 'S/N'} · {sn.get('sample_rate') or '?'} sps · "
            f"montaje {rotulos.rotulo(rotulos.MONTAJE, montaje) if montaje else 'no declarado'} · "
            f"calibración {sn.get('calibration_source') or 'NO DECLARADA'}",
        )


def _chain_section(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("11", "CADENA DE DICTÁMENES")
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
            # [T-8.12 · A-150] Con su «UTC»: era la única fecha del papel sin zona.
            row.cell(pdf.text_of(f"{d.created_at.astimezone(UTC):%Y-%m-%d %H:%M} UTC"))
            row.cell(pdf.text_of(d.rule_set_version))
            row.cell(pdf.text_of((d.supersedes or "—")[:8]))
    pdf.ln(1)
    pdf.para(
        "Las correcciones INSERTAN una versión nueva; ninguna fila se reescribe.",
        size=7,
        muted=True,
    )


def _custody_section(pdf: TakabPDF, m: ReportModel) -> None:
    """[T-7.22] Solo los OBJETOS de evidencia.

    La bitácora se fue a la §13 (CRONOLOGÍA DEL INCIDENTE).

    ⚠️ Decía «§12», que es ESTA sección: la renumeración de `T-7.24` —el mapa de
    la sacudida entró como §8 y corrió a todas las de abajo— movió la bitácora de
    la §12 a la §13 y esta referencia se quedó apuntándose a sí misma. La cita
    lleva ahora el TÍTULO entre paréntesis, que es lo que la hace comprobable:
    `test_toda_CITA_a_una_seccion_del_dictamen_casa_con_su_numero_real`.

    Imprimía además, en monoespaciada y sin rótulo, las filas de
    `incident_actions` con su `kind` CRUDO: el papel decía `gas_closed` donde la
    pantalla dice «VÁLVULAS DE GAS CERRADAS». Son dos cosas distintas —qué se
    archivó y qué pasó— y estaban bajo un mismo título que solo nombra a una.

    Se MUEVEN y no se duplican: imprimir las mismas filas en dos secciones de un
    documento de evidencia obliga al lector a contarlas dos veces o a decidir
    cuál de las dos apariciones creer.
    """
    pdf.section("12", "CADENA DE CUSTODIA")
    if m.evidence:
        pdf.set_font(pdf.body_font, "", 7.5)
        for e in m.evidence:
            # [T-5.26] El sha256 ENTERO. Se imprimía a 32 de 64 caracteres
            # mientras la portada de este mismo documento instruye verificarlo
            # con `sha256sum`: con medio hash no se puede, y un dato inverificable
            # presentado como verificable es peor que no imprimirlo.
            # No había razón de espacio — 64 hex miden 108.7 mm de los 128 que
            # deja la columna, así que entran en una sola línea.
            # [T-8.12 · A-144] `REPORT_PDF`/`MINISEED` en castellano.
            pdf.field(rotulos.rotulo(rotulos.EVIDENCIA, e.kind), huella_de_custodia(e.sha256))
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
    pdf.section("13", "CRONOLOGÍA DEL INCIDENTE")
    if not m.actions:
        pdf.callout(SIN_CRONOLOGIA)
        return
    pdf.set_font(pdf.body_font, "", 7)
    sin_rotulo = 0
    # Quien firmó un dictamen de la cadena NO es «OPERADOR»: se nombra por su rol,
    # y quien firmó la cabeza exactamente como en el FIRMÓ.
    firmantes = rotulos.firmantes_de_la_cadena(
        [(d.signed_by, d.firmante_nombre) for d in m.dictamens]
    )
    with pdf.table(col_widths=(38, 82, 38), text_align="LEFT") as table:
        head = table.row()
        for h in ("INSTANTE (UTC · LOCAL)", "QUÉ PASÓ", "QUIÉN"):
            head.cell(pdf.text_of(h))
        for a in m.actions:
            texto, conocido = rotulo_de_accion(a.kind)
            sin_rotulo += 0 if conocido else 1
            row = table.row()
            # [T-8.12 · A-150] La UTC y, debajo, la hora local del inmueble.
            row.cell(pdf.text_of(rotulos.instante(a.ts, m.zona_horaria).replace(" · ", "\n", 1)))
            row.cell(pdf.text_of(texto))
            # [T-8.12 · A-144] `system:edge` → «SISTEMA · gabinete»; una persona,
            # como en la consola, por los ocho primeros caracteres de su `sub`.
            row.cell(pdf.text_of(rotulos.actor(a.actor, firmantes)))
    if sin_rotulo:
        # Declarar el recuento, no solo marcar las filas: quien audite tiene que
        # poder saber de un vistazo cuánto del documento no se supo traducir.
        pdf.callout(f"{CRONOLOGIA_SIN_ROTULO}{sin_rotulo} de {len(m.actions)}.")


#: Lo que se reserva para que la cabecera de un reporte de daños (su renglón y el
#: arranque de su tabla) no se parta del resto.
_CABECERA_DE_REPORTE = 24.0

#: Ancho de la COLUMNA de cada fotografía. Dos por fila en el ancho útil, con aire
#: entre ellas. Más pequeñas no dejan ver una grieta; más grandes obligan a una
#: página por foto y el documento deja de poder hojearse.
_FOTO_W = 88.0
_FOTO_GAP = (CONTENT_W - 2 * _FOTO_W) / 1.0
#: [T-8.12 · A-051] La CAJA donde se encaja cada foto: 88 × 88 mm, conservando la
#: proporción. El comentario de la reserva anterior decía que «una foto de retrato
#: a 1024×1024 sale cuadrada», y era falso: `preparar()` conserva la proporción y
#: una foto 3:4 de teléfono salía a 768×1024 → 88 × 117 mm, con 98 mm reservados.
#: `pdf.image()` no salta de página, así que según dónde empezara la fila la foto
#: bajaba hasta 19 mm dentro del pie. Encajada en la caja, la más alta mide 88.
_FOTO_CAJA = 88.0
#: El pie de cada foto: mono 5.2 pt en renglones de 2.4 mm.
_PIE_FOTO_PT = 5.2
_PIE_FOTO_RENGLON = 2.4


def _caja_de_foto(foto) -> tuple[float, float]:  # noqa: ANN001 - FotoFila
    """`(ancho, alto)` en mm de la foto ENCAJADA en `_FOTO_CAJA`, sin deformarla."""
    if not (foto.ancho and foto.alto):
        return _FOTO_CAJA, _FOTO_CAJA
    escala = min(_FOTO_CAJA / foto.ancho, _FOTO_CAJA / foto.alto)
    return foto.ancho * escala, foto.alto * escala


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
    # El título viaja con la cabecera del PRIMER reporte, que reserva lo suyo.
    pdf.section(
        "14", "DAÑOS REPORTADOS EN CAMPO", con=_CABECERA_DE_REPORTE if m.danos else PRIMER_BLOQUE_MM
    )
    if not m.danos:
        pdf.callout(SIN_DANOS)
        return
    for dano in m.danos:
        pdf.reserva(_CABECERA_DE_REPORTE)
        # [T-8.12 · A-144] El rol en castellano (`security_guard` salía crudo).
        quien = rotulos.rotulo(rotulos.ROL, dano.rol) if dano.rol else ROL_NO_RESUELTO
        donde = dano.zona or "zona no declarada"
        cuando = rotulos.instante(dano.ts, m.zona_horaria, segundos=False)
        pdf.field("REPORTE", f"{quien} · {donde} · {cuando}")
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
                    # [T-8.12 · A-144] Las claves de la app en castellano, con
                    # las MISMAS palabras que eligió quien reportó.
                    row.cell(pdf.text_of(rotulos.rotulo(rotulos.CATEGORIA_DE_DANO, cat.get("key"))))
                    row.cell(
                        pdf.text_of(rotulos.rotulo(rotulos.SEVERIDAD_DE_DANO, cat.get("severity")))
                    )
                    row.cell(pdf.text_of(str(cat.get("note") or "")))
            # La foto no puede empezar pegada al borde de la tabla.
            pdf.ln(2)
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
    pie, sobre el sha256 y la paginación.

    [T-8.12] La fila se reserva ENTERA —la foto más alta, su aire y el pie de foto
    más largo, MEDIDO con `dry_run`— y el cursor acaba en el FONDO del pie más
    bajo. Antes:

    * **A-050** — el pie de la foto de la izquierda se escribía con
      `new_y=YPos.TOP`, pensando en que la de la derecha lo bajaría. Con UNA foto,
      o con la última de un número impar, no había foto de la derecha: el cursor
      volvía ARRIBA del pie, y el reporte siguiente —o el título de la §15— se
      imprimía encima de las huellas DECLARADA, MEDIDA e IMPRESA.
    * **A-051** — se reservaban 98 mm con fotos de hasta 117 mm de alto.

    Lo vigilan `test_NADA_se_imprime_encima_de_otra_cosa_desde_los_DANOS` (texto
    contra texto y contra foto, con 1, 3 y 4 fotos, apaisadas y en vertical) y
    `test_las_fotos_respetan_el_PIE_ENTRE_DONDE_ENTREN`.
    """
    impresas = [f for f in dano.fotos if f.jpeg is not None]
    ausentes = [f for f in dano.fotos if f.jpeg is None]

    for i in range(0, len(impresas), 2):
        fila = impresas[i : i + 2]
        cajas = [_caja_de_foto(f) for f in fila]
        alto_fotos = max(alto for _, alto in cajas)
        pdf.set_font(pdf.mono_font, "", _PIE_FOTO_PT)
        pies = [pdf.text_of(_pie_de_foto(foto)) for foto in fila]
        alto_pies = max(
            pdf.multi_cell(
                _FOTO_W,
                _PIE_FOTO_RENGLON,
                pie,
                dry_run=True,
                output=MethodReturnValue.HEIGHT,
            )
            for pie in pies
        )
        pdf.reserva(alto_fotos + 1 + alto_pies)
        top = pdf.get_y()
        for j, (foto, (ancho, alto)) in enumerate(zip(fila, cajas, strict=True)):
            x = MARGIN + j * (_FOTO_W + _FOTO_GAP)
            pdf.image(io.BytesIO(foto.jpeg), x=x, y=top, w=ancho, h=alto)
        # El pie de cada foto va DEBAJO de la fila entera, no al lado: dos fotos
        # de alto distinto dejarían los pies desalineados y sin saber cuál es cuál.
        y_pies = top + alto_fotos + 1
        fondo = y_pies
        pdf.set_text_color(*MUTED)
        for j, pie in enumerate(pies):
            pdf.set_xy(MARGIN + j * (_FOTO_W + _FOTO_GAP), y_pies)
            pdf.multi_cell(_FOTO_W, _PIE_FOTO_RENGLON, pie, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            fondo = max(fondo, pdf.get_y())
        pdf.set_text_color(*INK)
        # El cursor, al FONDO del pie más bajo de la fila — nunca arriba de ninguno.
        pdf.set_y(fondo)
        pdf.ln(2)

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
    pdf.section("15", "EVACUACIÓN OBSERVADA (CCTV)")
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
        # [T-8.12 · A-144 · A-146] El papel del still en castellano, y la HORA al
        # valor: `«egress» · AAAA-MM-DD HH:MM:SS UTC` no cabía en la columna de
        # rótulos (52 mm) y se montaba sobre el estado.
        etiqueta = (
            rotulos.rotulo(rotulos.PAPEL_CCTV, obj.papel)
            if obj.papel
            else rotulos.rotulo(rotulos.TIPO_CCTV, obj.tipo)
        )
        cuando = rotulos.instante(obj.momento, m.zona_horaria) if obj.momento else ABSENT
        pdf.field(etiqueta, f"{cuando} · {obj.estado}")
        # [T-5.26] Entero y en su propia línea. Iba a 16 de 64 con puntos
        # suspensivos: honesto sobre estar cortado, e igual de inútil para
        # verificar. Y son custodia igual que el miniSEED —lo dice esta misma
        # sección cuatro líneas más arriba—, así que se imprimen igual.
        pdf.field("", huella_de_custodia(obj.sha256))


def _narrative_section(pdf: TakabPDF, m: ReportModel) -> None:
    """Prosa opcional (T-2.42). Rodea al veredicto; nunca lo produce."""
    if not m.narrative:
        return
    pdf.section("16", "ANÁLISIS")
    for title, body in m.narrative:
        pdf.set_font(pdf.body_font, "B", 8)
        pdf.cell(0, 5, pdf.text_of(title.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.para(body)
    if m.narrative_provider and m.narrative_provider != "deterministic":
        pdf.callout(
            f"{NARRATIVE_AI_NOTE} ({m.rule_set_version or 'sin versión'}) y no dependen de ella."
        )
    # [T-8.12 · A-149] QUIÉN redactó la prosa, dicho en el papel. Hasta aquí sólo
    # quedaba en `audit_log` (`narrative_generated`), y la meta de F6 buscaba
    # «Narrativa: openrouter» en el texto de un PDF que no la imprimía.
    if m.narrative_provider:
        pdf.para(f"Narrativa: {_proveedor(m.narrative_provider)}", size=7, muted=True)
    if m.narrative_degraded:
        pdf.para(f"NARRATIVA DEGRADADA · {m.narrative_degraded}", size=7, muted=True)


#: [T-8.12 · A-149] Cómo se llama en el papel cada redactor de la prosa. Lo que
#: no está aquí es el nombre del proveedor externo (`openrouter`, `bedrock`), que
#: se imprime tal cual: es un nombre propio y es lo que consta en `audit_log`.
_REDACTOR = {"deterministic": "determinista · sin asistencia de IA"}


def _proveedor(proveedor: str) -> str:
    return _REDACTOR.get(proveedor, proveedor)


def _compliance_section(pdf: TakabPDF, m: ReportModel) -> None:
    """[T-2.82] Marco normativo DECLARADO por el cliente.

    Va INMEDIATAMENTE antes de la firma y del deslinde, y no en la portada, a
    propósito: quien firma tiene que leer, en el mismo golpe de vista, que este
    apartado no lo respalda TAKAB. El título nombra al autor de las afirmaciones para
    que no haga falta llegar a la nota para saber de quién son.
    """
    pdf.section("17", "MARCO NORMATIVO DECLARADO POR EL CLIENTE")
    block = compliance_block(m.compliance)
    for label, value in block.rows:
        pdf.field(label, value)
    if block.rows:
        pdf.ln(1)
    for note in block.notes:
        pdf.callout(note)


def _closing(pdf: TakabPDF, m: ReportModel) -> None:
    pdf.section("18", "FIRMA Y DESLINDE")
    head = m.dictamens[0] if m.dictamens else None
    if head and head.signed_by:
        # [T-8.12 · A-145] El rol y, si lo hay, el nombre de `user_profiles`. Se
        # imprimía el `sub` de Cognito —un UUID entero— en la línea de más peso
        # del documento. `D-36` no cambia: el renglón de firma del emisor sigue
        # siendo la persona moral; ésta es la línea de QUIÉN firmó el dictamen.
        pdf.field("FIRMÓ", rotulos.firmante(head.firmante_nombre))
        pdf.field("FECHA DE FIRMA", rotulos.instante(head.created_at, m.zona_horaria))
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
    # [T-8.12 · A-053] La clasificación humana, igual que en la portada.
    pdf.field("CLASIFICACIÓN", _clasificacion(m))
    # [T-8.12 · A-139] Y la leyenda de la reproducción. El censo la eximía del
    # ejecutivo porque «no tiene tabla de red que rotular», pero lo que la
    # justifica no es la tabla: es que el papel AFIRMA una sacudida —«el sensor
    # del inmueble midió un pico de…»— que no ocurrió. Eso el ejecutivo lo dice
    # en su segunda frase.
    if m.reproduccion:
        pdf.callout(REPRODUCCION_NOTE)

    pdf.section("", "QUÉ PASÓ")
    utc = m.opened_at.astimezone(UTC)
    pdf.para(
        f"El {utc:%d/%m/%Y} a las {utc:%H:%M} UTC "
        f"({rotulos.hora_local(m.opened_at, m.zona_horaria)}) se abrió un incidente "
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
