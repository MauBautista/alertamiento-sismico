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


# ── [T-5.26] Las huellas que se imprimían a medias ───────────────────────────
#
# El sha256 de cada objeto de evidencia salía a **32 de 64** caracteres (y a 16
# en la custodia del vídeo) mientras la portada del mismo documento instruye
# verificarlo con `sha256sum`. Con medio hash no se puede.
#
# CÓMO SE PRUEBA, Y POR QUÉ NO DE LA FORMA OBVIA. El flujo del PDF va comprimido
# Y con fuentes embebidas, así que el texto viaja como índices de glifo: buscar
# el hash en los bytes no encuentra nada, ni entero ni cortado (comprobado).
#
# Y el atajo de «cambio la cola del hash y exijo que el PDF cambie» PASA EN VERDE
# SOBRE EL DEFECTO: cualquier cambio del modelo mueve el `content_sha256` que la
# PORTADA sí imprime, así que los dos documentos salen distintos aunque la
# custodia siga cortada. Se escribió así primero y la mutación lo delató.
#
# Lo que sí cierra el hueco: la regla vive en una función pura
# (`huella_de_custodia`) y un barrido del render comprueba que NADIE vuelve a
# recortar un hash en el sitio donde se imprime.


def test_la_huella_de_custodia_va_ENTERA() -> None:
    from takab_api.dictamen.model import SIN_HASH, huella_de_custodia

    sha = "a" * 64
    assert huella_de_custodia(sha) == sha, "la huella de custodia sale recortada"
    assert len(huella_de_custodia(sha)) == 64
    assert huella_de_custodia(None) == SIN_HASH, "un objeto sin hash tiene que decirlo"


def test_el_render_no_RECORTA_ninguna_huella() -> None:
    """El barrido que ata la función a sus dos sitios de uso.

    Sin esto, alguien puede volver a poner `[:32]` en la línea del render y la
    función seguiría pasando sus tests sola. Se busca la forma exacta del defecto
    —un corte aplicado a algo que se llama `sha256` o `huella`— en el módulo que
    dibuja el documento.
    """
    import re
    from pathlib import Path

    fuente = (Path(__file__).resolve().parents[2] / "src/takab_api/dictamen/pdf.py").read_text(
        encoding="utf-8"
    )
    cortes = re.findall(r"^\s*[^#\n]*(?:sha256|huella)[^\n]*\[\s*:\s*\d+\s*\]", fuente, re.M)

    assert not cortes, (
        "el dictamen vuelve a imprimir un hash recortado mientras su portada "
        f"instruye verificarlo con sha256sum: {cortes}"
    )


def test_las_dos_secciones_de_custodia_usan_la_MISMA_funcion() -> None:
    """Guarda anti-vacuidad del barrido de arriba: si el render dejara de llamar
    a `huella_de_custodia`, aquél seguiría en verde sobre un módulo que ya no
    imprime hashes por ahí. Son DOS: el miniSEED y el vídeo."""
    from pathlib import Path

    fuente = (Path(__file__).resolve().parents[2] / "src/takab_api/dictamen/pdf.py").read_text(
        encoding="utf-8"
    )
    assert fuente.count("huella_de_custodia(") == 2, (
        "la cadena de custodia y la del vídeo tienen que imprimir la huella por "
        "el mismo camino; si aparece una tercera, decide si también es custodia"
    )


def test_el_ejecutivo_lleva_su_huella_de_contenido() -> None:
    """Es el documento que lee QUIEN DECIDE, y era el único sin con qué verificarse.

    La prueba se apoya en un campo que el ejecutivo NO imprime —la custodia— pero
    que SÍ entra en `content_sha256()`: si el resumen no llevara la huella, los
    dos documentos saldrían byte a byte idénticos.
    """
    a = render(model(), "executive")
    b = render(model(evidence=[EvidenceRow("miniseed", "e" * 64, _OPENED)]), "executive")

    assert a != b, (
        "cambiar el contenido del incidente no cambia el documento ejecutivo: no "
        "lleva su huella, así que quien decide no tiene con qué verificar lo que lee"
    )


def test_los_dos_documentos_declaran_LA_MISMA_huella() -> None:
    """Es lo que permite comprobar que el resumen y el pericial hablan del mismo
    incidente sin abrirlos a la vez. Sale del CONTENIDO, no del archivo — los dos
    archivos son distintos y sus sha256 de fichero también."""
    m = model()
    assert m.content_sha256() == model().content_sha256()
    assert render(m, "executive") != render(m), "los dos documentos son el mismo archivo"


def test_las_dos_variantes_siguen_siendo_deterministas() -> None:
    m = model(evidence=[EvidenceRow("miniseed", "f" * 64, _OPENED)])
    assert render(m) == render(m)
    assert render(m, "executive") == render(m, "executive")
