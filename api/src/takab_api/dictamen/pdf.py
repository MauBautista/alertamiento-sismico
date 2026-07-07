"""Reporte PDF del incidente + dictamen (T-1.20 · B5).

``build_report_lines`` es PURO (testeable sin renderer); ``render_pdf`` lo
plasma con fpdf2 (pure-python, sin dependencias de sistema). El contenido
sigue la pantalla de Triage Estructural (blueprint §7.3): cadena de dictámenes
inmutable, quórum con offsets y el deslinde del §1 (dictamen operativo
preliminar; no sustituye la evaluación estructural formal).
"""

from __future__ import annotations

from fpdf import FPDF
from fpdf.enums import XPos, YPos

# Etiquetas operativas en español de los estados del CHECK de dictamens.status.
STATUS_LABELS: dict[str, str] = {
    "no_inhabit_inspect": "NO HABITAR · INSPECCIÓN",
    "inhabit_monitor": "HABITAR · MONITOREO",
    "normal_operation": "OPERACIÓN NORMAL",
    "restricted": "ACCESO RESTRINGIDO",  # estado manual (inspector), no automático
}

_DISCLAIMER = (
    "Dictamen operativo PRELIMINAR generado por TAKAB Ailert a partir de "
    "evidencia instrumental. No sustituye la evaluación estructural formal ni "
    "certifica reingreso seguro sin firma de ingeniería."
)

_TS_FMT = "%Y-%m-%d %H:%M:%S UTC"


def build_report_lines(incident: dict, dictamens: list[dict], votes: list[dict]) -> list[str]:
    """Contenido del reporte, línea a línea (cadena más reciente primero)."""
    lines = [
        "TAKAB Ailert — Reporte de incidente y dictamen operativo",
        "",
        f"Incidente: {incident['incident_id']}",
        f"Sitio: {incident['site_name']} ({incident['site_code']})",
        f"Abierto: {incident['opened_at']:{_TS_FMT}} · estado: {incident['state']}",
        f"Severidad: {incident['severity']} · disparo: {incident['trigger']}",
        f"PGA máx: {_num(incident['max_pga_g'])} g · PGV máx: {_num(incident['max_pgv_cms'])} cm/s",
    ]
    if incident.get("closed_at"):
        lines.append(f"Cerrado: {incident['closed_at']:{_TS_FMT}}")
    if incident.get("event_id"):
        lines.append(f"Evento de red: {incident['event_id']}")

    lines += ["", "Cadena de dictámenes (más reciente primero):"]
    if not dictamens:
        lines.append("  (sin dictamen registrado)")
    for d in dictamens:
        signed = "FIRMADO" if d["signed_by"] else "PRELIMINAR"
        version = (d.get("basis") or {}).get("rule_set_version", "—")
        lines.append(
            f"  [{signed}] {STATUS_LABELS.get(d['status'], d['status'])} — "
            f"{d['created_at']:{_TS_FMT}} — reglas: {version} — id {d['dictamen_id']}"
        )

    lines.append("")
    if votes:
        lines.append(f"Quórum de red: {len(votes)} nodos corroborantes")
        for v in votes:
            lines.append(
                f"  estación {v['sensor_id']} · Δt +{float(v['delta_s'] or 0.0):.1f} s "
                f"· PGA {_num(v['pga_g'])} g"
            )
    else:
        lines.append("Quórum de red: sin corroboración multi-estación")

    lines += ["", _DISCLAIMER]
    return lines


def render_pdf(lines: list[str]) -> bytes:
    """PDF A4 simple: título + cuerpo monoespaciado lógico (una línea por fila)."""
    pdf = FPDF(format="A4")
    pdf.set_margins(15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    for i, line in enumerate(lines):
        if not line:
            pdf.ln(6)
            continue
        pdf.set_font("helvetica", style="B" if i == 0 else "", size=14 if i == 0 else 10)
        # Fuentes core de fpdf2 = latin-1; se degrada lo no representable.
        safe = line.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(w=0, h=6, text=safe, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())


def _num(value: object) -> str:
    return "—" if value is None else f"{float(value):g}"
