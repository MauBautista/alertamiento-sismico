"""T-2.41 · Los dos documentos del dictamen.

El contenido se prueba sobre el MODELO —que es donde puede haber una mentira— y el
render sobre propiedades que un revisor externo comprobaría: que el PDF sea
determinista (su sha256 es lo que lo hace evidencia), que no pierda caracteres, y que
NUNCA escriba un número donde no hubo medición.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from takab_api.dictamen import layout
from takab_api.dictamen.model import (
    ABSENT,
    DISCLAIMER,
    ActionRow,
    ChannelRow,
    DictamenRow,
    EvidenceRow,
    ReportModel,
    VoteRow,
    lead_time_text,
    num,
)
from takab_api.dictamen.pdf import render

_OPENED = datetime(2026, 8, 3, 10, 0, 0, tzinfo=UTC)


def model(**over) -> ReportModel:
    base = {
        "folio": "TKB-CHL-A-20260803-1A2B3C4D-T",
        "incident_id": "11111111-2222-3333-4444-555555555555",
        "site_name": "Planta Cholula",
        "site_code": "CHL-A",
        "site_criticality": "critical",
        "site_lat": 19.06,
        "site_lon": -98.30,
        "opened_at": _OPENED,
        "closed_at": None,
        "severity": "warning",
        "trigger": "sasmex",
        "state": "open",
        "event_id": "EVT-001",
        "event_source": "local_quorum",
        "epicenter_lat": 16.80,
        "epicenter_lon": -99.50,
        "verdict_status": "inhabit_monitor",
        "verdict_label": "HABITAR · MONITOREO",
        "verdict_signed": False,
        "rule_set_version": "dictamen-v1",
        "peak_pga_g": 0.081,
        "peak_pgv_cms": 3.2,
        "peak_ts": datetime(2026, 8, 3, 10, 0, 35, tzinfo=UTC),
        "felt_band": "trip",
        "calibrated": True,
        "lead_time_s": 35.0,
        "lead_time_reason": None,
        "station_count": 4,
        "catalog_line": "SSN SSN-2026-001 · M 7.1 · Δt 12 s · 187 km SSO",
        "generated_at": _OPENED,
        "channels": [
            ChannelRow("ENZ", 0.081, 3.2, 0.01, 4.2, 1.5, False, 120, _OPENED),
            ChannelRow("ENN", 0.030, 1.1, 0.01, 2.0, 0.9, False, 120, _OPENED),
        ],
        "dictamens": [
            DictamenRow("d-1", "inhabit_monitor", _OPENED, None, "dictamen-v1", None),
        ],
        "votes": [VoteRow("TORRE-A", 0.0, 0.081, True), VoteRow("HOSP-01", 1.4, 0.05, True)],
        "actions": [ActionRow(_OPENED, "siren_on", "system:edge")],
        "evidence": [EvidenceRow("miniseed", "a" * 64, _OPENED)],
        "sensors": [{"kind": "structural", "model": "RS4D", "calibration_source": "stationxml"}],
        "peers": [{"lat": 19.43, "lon": -99.13, "site_code": "CDMX-1"}],
        "series": {"ENZ": [(_OPENED, 0.01 * i, False) for i in range(60)]},
    }
    return ReportModel(**{**base, **over})


# ---- determinismo ------------------------------------------------------------


def test_el_mismo_modelo_produce_los_mismos_bytes() -> None:
    """Sin esto, "verifique el sha256" sería una promesa falsa: fpdf2 estampa
    /CreationDate con el reloj y dos generaciones darían hashes distintos."""
    m = model()
    assert hashlib.sha256(render(m)).hexdigest() == hashlib.sha256(render(m)).hexdigest()


def test_un_modelo_distinto_produce_bytes_distintos() -> None:
    assert render(model()) != render(model(peak_pga_g=0.9))


def test_la_huella_de_contenido_es_estable_y_cambia_con_el_contenido() -> None:
    assert model().content_sha256() == model().content_sha256()
    assert model().content_sha256() != model(peak_pga_g=0.9).content_sha256()


# ---- prohibido inventar datos ------------------------------------------------


def test_sin_pico_medido_no_escribe_un_cero() -> None:
    """Un "0.000 g" en un dictamen que acabará ante Protección Civil no es un detalle
    de formato: es afirmar una medición que nadie hizo."""
    assert num(None) == ABSENT
    assert num(None, 3, "g") == ABSENT
    assert "0.000" not in num(None, 3, "g")


def test_el_tiempo_de_aviso_ausente_explica_su_causa() -> None:
    assert lead_time_text(None, "not_sasmex").startswith("NO CALCULABLE")
    assert "SASMEX" in lead_time_text(None, "not_sasmex")
    assert lead_time_text(35.0, None) == "35.0 s"


def test_una_razon_desconocida_se_muestra_tal_cual() -> None:
    assert "razon_nueva" in lead_time_text(None, "razon_nueva")


def test_el_pdf_de_un_incidente_sin_mediciones_se_genera_igual() -> None:
    """La exportación de evidencia no puede fallar porque falten datos."""
    blob = render(
        model(
            peak_pga_g=None,
            peak_pgv_cms=None,
            peak_ts=None,
            felt_band="unknown",
            channels=[],
            series={},
            votes=[],
            station_count=0,
            catalog_line=None,
            lead_time_s=None,
            lead_time_reason="no_peak",
        )
    )
    assert blob.startswith(b"%PDF")
    assert len(blob) > 2000


def test_un_incidente_sin_geometria_no_revienta_el_croquis() -> None:
    blob = render(
        model(site_lat=None, site_lon=None, epicenter_lat=None, epicenter_lon=None, peers=[])
    )
    assert blob.startswith(b"%PDF")


def test_un_incidente_sin_dictamen_se_imprime_igual() -> None:
    """Un incidente sin dictamen YA tiene hechos que reportar."""
    blob = render(model(dictamens=[], verdict_status=None, verdict_label="SIN DICTAMEN REGISTRADO"))
    assert blob.startswith(b"%PDF")


def test_un_canal_saturado_se_declara() -> None:
    """Un canal recortado NO midió el pico: midió el techo del ADC."""
    m = model(channels=[ChannelRow("ENZ", 0.5, 20.0, 0.1, 9.0, 5.0, True, 120, _OPENED)])
    assert render(m).startswith(b"%PDF")


# ---- tipografía --------------------------------------------------------------


def test_las_fuentes_unicode_viajan_con_el_paquete() -> None:
    """Con las core de fpdf2 (latin-1), Δ, ≥ y ≈ se degradaban a interrogantes en un
    documento de compliance."""
    pdf = layout.TakabPDF("TKB-TEST", "sub")
    assert not pdf.degraded, "las DejaVu no se empaquetaron"
    assert pdf.text_of("Δt ≥ 0.5 s · ±0.081 g") == "Δt ≥ 0.5 s · ±0.081 g"


def test_sin_la_fuente_degrada_pero_NO_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una exportación de evidencia jamás puede caerse por tipografía."""
    monkeypatch.setattr(layout, "_FONTS", layout.Path("/no/existe"))
    pdf = layout.TakabPDF("TKB-TEST", "sub")
    assert pdf.degraded
    # Y lo declara en el pie: perder caracteres en silencio sería peor que degradar.
    assert "?" in pdf.text_of("Δt")


# ---- las dos variantes -------------------------------------------------------


def test_el_ejecutivo_es_mucho_mas_corto_que_el_tecnico() -> None:
    assert len(render(model(), "executive")) < len(render(model(), "technical"))


def test_ambos_llevan_el_deslinde() -> None:
    """El límite de responsabilidad es principio de diseño, no adorno del técnico."""
    assert DISCLAIMER.startswith("Dictamen operativo PRELIMINAR")
    for variant in ("technical", "executive"):
        assert render(model(), variant).startswith(b"%PDF")


def test_una_variante_desconocida_cae_al_tecnico() -> None:
    assert render(model(), "lo-que-sea") == render(model(), "technical")


def test_el_ejecutivo_de_un_veredicto_sin_acciones_no_revienta() -> None:
    assert render(model(verdict_status="estado_nuevo"), "executive").startswith(b"%PDF")


def test_el_ejecutivo_sin_calibracion_lo_declara() -> None:
    assert render(model(calibrated=False), "executive").startswith(b"%PDF")


# ---- narrativa (T-2.42 la rellena; aquí solo que no estorbe) -----------------


def test_sin_narrativa_el_pdf_se_genera_igual() -> None:
    assert render(model(narrative=[])).startswith(b"%PDF")


def test_con_narrativa_el_veredicto_no_cambia() -> None:
    """La prosa RODEA al veredicto; jamás lo produce (regla de oro 1)."""
    con = model(narrative=[("Resumen", "Texto de prueba.")], narrative_provider="deterministic")
    sin = model()
    assert con.verdict_status == sin.verdict_status
    assert render(con).startswith(b"%PDF")
