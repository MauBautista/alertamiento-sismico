"""T-2.42 · Proveedor determinista: el suelo del que la prosa nunca baja.

Lo que se prueba no es que "suene bien", sino lo verificable: que estén las seis
secciones, que el "por qué este veredicto" cite el umbral REAL del basis, y que jamás
escriba un número donde no hubo medición.
"""

from __future__ import annotations

from takab_api.dictamen.model import ABSENT
from takab_api.narrative import build_narrative
from takab_api.narrative.base import NarrativeRequest
from takab_api.narrative.deterministic import DeterministicProvider, sections_for
from takab_api.narrative.prompts import SECTION_TITLES
from takab_api.narrative.redact import facts_from
from takab_api.settings import Settings
from tests.dictamen.test_pdf import model
from tests.narrative.test_redact import BASIS


def _secs(**over) -> dict[str, str]:
    return dict(sections_for(facts_from(model(verdict_basis=BASIS, **over))))


def test_son_seis_secciones_en_orden() -> None:
    titulos = [t for t, _ in sections_for(facts_from(model()))]
    assert titulos == list(SECTION_TITLES)
    assert len(titulos) == 6


def test_ninguna_seccion_queda_vacia() -> None:
    for titulo, cuerpo in sections_for(facts_from(model(peak_pga_g=None, channels=[]))):
        assert cuerpo.strip(), f"la sección {titulo} quedó vacía"


def test_los_mismos_hechos_producen_el_mismo_texto() -> None:
    assert sections_for(facts_from(model())) == sections_for(facts_from(model()))


def test_un_hecho_distinto_cambia_el_texto() -> None:
    assert sections_for(facts_from(model())) != sections_for(facts_from(model(peak_pga_g=0.9)))


# ---- por qué este veredicto --------------------------------------------------


def test_cita_la_version_de_reglas_y_los_dos_umbrales() -> None:
    """Trazabilidad literal: qué umbral, con qué valor, de qué versión."""
    texto = _secs()["Por qué este veredicto"]
    assert "dictamen-v1" in texto
    assert "0.250 g" in texto  # umbral de no habitar
    assert "0.050 g" in texto  # umbral de monitoreo
    assert "0.081 g" in texto  # valor evaluado


def test_dice_cual_umbral_se_supero() -> None:
    assert "superó el umbral de monitoreo" in _secs()["Por qué este veredicto"]


def test_un_pico_por_encima_del_umbral_alto_lo_dice_asi() -> None:
    alto = {**BASIS, "evidence": {**BASIS["evidence"], "pga_g": 0.4}}
    texto = dict(sections_for(facts_from(model(verdict_basis=alto))))["Por qué este veredicto"]
    assert "superó el umbral de no habitar" in texto


def test_sin_basis_guardado_lo_declara_en_vez_de_inventarlo() -> None:
    """Un basis perdido es un hueco de trazabilidad; fingirlo sería peor."""
    texto = dict(sections_for(facts_from(model(verdict_basis={}))))["Por qué este veredicto"]
    assert "no quedó guardado" in texto
    assert ABSENT in texto or "sin versión" in texto or "dictamen-v1" in texto


def test_sin_dictamen_no_explica_un_veredicto_que_no_existe() -> None:
    texto = dict(
        sections_for(facts_from(model(dictamens=[], verdict_status=None, verdict_basis={})))
    )["Por qué este veredicto"]
    assert "todavía no tiene dictamen" in texto


def test_la_regla_de_nodos_se_declara_como_elevadora_de_prudencia() -> None:
    texto = _secs()["Por qué este veredicto"]
    assert "nunca rebajarla" in texto


# ---- prohibido inventar ------------------------------------------------------


def test_sin_pico_medido_no_escribe_un_cero() -> None:
    texto = _secs(peak_pga_g=None, peak_pgv_cms=None)["Qué se midió"]
    assert "0.000" not in texto
    assert ABSENT in texto


def test_sin_calibracion_declara_que_los_valores_son_relativos() -> None:
    assert "RELATIVOS" in _secs(calibrated=False)["Qué se midió"]


def test_las_limitaciones_enumeran_cada_ausencia() -> None:
    secciones = _secs(peak_pga_g=None, station_count=0, catalog_line=None)
    texto = secciones["Limitaciones y datos ausentes"]
    assert "(1)" in texto and "(2)" in texto
    assert "no localiza sismos" in texto


def test_que_hacer_ahora_copia_la_tabla_fija_de_acciones() -> None:
    """Son instrucciones de seguridad: no pueden variar entre dos ejecuciones."""
    texto = _secs()["Qué hacer ahora"]
    assert "1. Se puede ocupar el inmueble" in texto


def test_un_estado_desconocido_no_inventa_instrucciones() -> None:
    texto = dict(sections_for(facts_from(model(verdict_status="estado_nuevo"))))["Qué hacer ahora"]
    assert "No hay acciones asociadas" in texto


def test_un_inmueble_critico_lo_menciona() -> None:
    assert "crítico" in _secs(site_criticality="critical")["Qué hacer ahora"]


# ---- orquestador -------------------------------------------------------------


async def test_por_defecto_el_proveedor_es_el_determinista() -> None:
    """Con la configuración que se despliega, la IA no participa."""
    out = await build_narrative(model(), Settings())
    assert out.provider == "deterministic"
    assert out.degraded_reason is None
    assert len(out.sections) == 6


async def test_la_procedencia_va_completa_a_la_auditoria() -> None:
    prov = (await build_narrative(model(), Settings())).provenance()
    assert prov["provider"] == "deterministic"
    assert prov["sections"] == list(SECTION_TITLES)
    assert set(prov) >= {"model", "degraded_reason", "latency_ms", "prompt_tokens", "cost_usd"}


async def test_un_proveedor_que_revienta_degrada_en_vez_de_tumbar_la_evidencia() -> None:
    class Explota:
        name = "explota"

        async def generate(self, req):  # noqa: ANN001, ARG002
            raise RuntimeError("boom")

    out = await build_narrative(model(), Settings(), provider=Explota())
    assert out.provider == "deterministic"
    assert len(out.sections) == 6


async def test_el_proveedor_determinista_no_necesita_red_ni_clave() -> None:
    req = NarrativeRequest(facts=facts_from(model()))
    out = await DeterministicProvider().generate(req)
    assert out.provider == "deterministic"
    assert out.model is None
