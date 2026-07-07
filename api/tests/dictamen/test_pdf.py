"""Reporte PDF del dictamen (T-1.20 · B5): contenido puro + render fpdf2."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from takab_api.dictamen.pdf import STATUS_LABELS, build_report_lines, render_pdf

TS = datetime(2026, 7, 7, 12, 0, 0, tzinfo=UTC)


def _incident() -> dict:
    return {
        "incident_id": uuid4(),
        "site_name": "Torre Angelópolis",
        "site_code": "CHL-A",
        "opened_at": TS,
        "closed_at": None,
        "severity": "warning",
        "state": "acked",
        "trigger": "local_threshold",
        "max_pga_g": 0.12,
        "max_pgv_cms": 3.4,
        "event_id": "EVT-20260707-1200-abc123",
    }


def _dictamen(status: str, *, signed: bool) -> dict:
    return {
        "dictamen_id": uuid4(),
        "status": status,
        "basis": {"rule_set_version": "dictamen-v1", "evidence": {"node_count": 3}},
        "signed_by": uuid4() if signed else None,
        "supersedes_dictamen_id": None,
        "created_at": TS,
    }


def _vote(delta_s: float) -> dict:
    return {
        "sensor_id": uuid4(),
        "detected_at": TS,
        "pga_g": 0.08,
        "delta_s": delta_s,
        "counted": True,
    }


def test_status_labels_are_the_three_operative_states() -> None:
    assert STATUS_LABELS["no_inhabit_inspect"] == "NO HABITAR · INSPECCIÓN"
    assert STATUS_LABELS["inhabit_monitor"] == "HABITAR · MONITOREO"
    assert STATUS_LABELS["normal_operation"] == "OPERACIÓN NORMAL"
    assert "restricted" in STATUS_LABELS  # estado manual del CHECK del DDL


def test_lines_carry_dictamen_chain_and_quorum() -> None:
    lines = build_report_lines(
        _incident(),
        [_dictamen("no_inhabit_inspect", signed=True), _dictamen("inhabit_monitor", signed=False)],
        [_vote(0.0), _vote(8.2), _vote(16.9)],
    )
    text = "\n".join(lines)
    assert "NO HABITAR · INSPECCIÓN" in text
    assert "HABITAR · MONITOREO" in text
    assert "dictamen-v1" in text
    assert "PRELIMINAR" in text  # fila sin firma
    assert "FIRMADO" in text
    assert "Torre Angelópolis" in text
    assert "EVT-20260707-1200-abc123" in text
    assert "+16.9 s" in text  # offsets del quórum (blueprint §7.3)
    assert "3 nodos" in text.lower() or "nodos: 3" in text.lower()


def test_lines_include_liability_disclaimer() -> None:
    """Blueprint §1: dictamen preliminar; NO sustituye la evaluación formal."""
    text = "\n".join(build_report_lines(_incident(), [], []))
    assert "no sustituye" in text.lower()


def test_render_pdf_returns_pdf_bytes() -> None:
    lines = build_report_lines(_incident(), [_dictamen("inhabit_monitor", signed=False)], [])
    pdf = render_pdf(lines)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 800
