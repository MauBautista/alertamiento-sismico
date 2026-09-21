"""T-2.42 · Proveedor determinista: el suelo del que la prosa nunca baja.

Lo que se prueba no es que "suene bien", sino lo verificable: que estén las seis
secciones, que el "por qué este veredicto" cite el umbral REAL del basis, y que jamás
escriba un número donde no hubo medición.
"""

from __future__ import annotations

from datetime import UTC, datetime

from takab_api.dictamen.model import ABSENT
from takab_api.narrative import build_narrative
from takab_api.narrative.base import NarrativeRequest
from takab_api.narrative.deterministic import (
    _TRIGGER_TEXT,
    DeterministicProvider,
    sections_for,
)
from takab_api.narrative.prompts import SECTION_TITLES
from takab_api.narrative.redact import facts_from
from takab_api.settings import Settings
from tests.dictamen.test_pdf import model
from tests.narrative.test_redact import BASIS


def _cadena(n: int) -> list:
    """`n` filas de dictamen, para que `dictamen_count` sea real."""
    from takab_api.dictamen.model import DictamenRow

    return [
        DictamenRow(
            dictamen_id=f"d{i}",
            status="normal_operation",
            created_at=datetime(2026, 8, 3, 10, i, tzinfo=UTC),
            signed_by=None,
            rule_set_version="sin versión",
            supersedes=None,
        )
        for i in range(n)
    ]


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
    # [T-7.26] Esta guarda era CIEGA: pasaba igual con `degraded_reason=None`, que es
    # justo el defecto que tenía el código («un fallback no puede ser ok»).
    assert "RuntimeError" in (out.degraded_reason or "")


async def test_el_proveedor_determinista_no_necesita_red_ni_clave() -> None:
    req = NarrativeRequest(facts=facts_from(model()))
    out = await DeterministicProvider().generate(req)
    assert out.provider == "deterministic"
    assert out.model is None


# ---- [T-7.36] la apertura no es la escalada ----------------------------------


def test_la_prosa_atribuye_la_APERTURA_a_quien_la_abrio() -> None:
    """«El incidente se abrió … a partir de X» salía de `trigger`, que la ingesta
    sobrescribe con el disparo de la ÚLTIMA ESCALADA.

    Con SASMEX abriendo y el cuórum corroborando, el papel decía que lo abrió el
    cuórum — y en el caso contrario (umbral local abre, SASMEX escala) inflaba el
    tiempo de aviso ganado con segundos anteriores a que SASMEX dijera nada.
    """
    texto = _secs(opened_trigger="sasmex", trigger="quorum")["Qué pasó"]
    assert _TRIGGER_TEXT["sasmex"] in texto, "la apertura no se atribuye al SASMEX"


def test_la_prosa_DECLARA_la_escalada() -> None:
    """Se dice, no se sustituye: callarla cambiaría una frase falsa por una
    incompleta, y el cuórum es justo lo que autoriza a evacuar."""
    texto = _secs(opened_trigger="sasmex", trigger="quorum")["Qué pasó"]
    assert _TRIGGER_TEXT["quorum"] in texto, "la prosa se calla que el incidente escaló"


def test_sin_escalada_la_prosa_no_INVENTA_una() -> None:
    texto = _secs(opened_trigger="sasmex", trigger="sasmex")["Qué pasó"]
    assert "escaló" not in texto.lower()
    assert _TRIGGER_TEXT["sasmex"] in texto


def test_los_dos_TEXTOS_de_disparo_son_distinguibles() -> None:
    """Control de ceguera: si dos entradas del mapa fueran iguales, los tres tests
    de arriba no podrían distinguir apertura de escalada."""
    assert len(set(_TRIGGER_TEXT.values())) == len(_TRIGGER_TEXT)
    assert all(v.strip() for v in _TRIGGER_TEXT.values())


# ---- [T-7.38·D] el veredicto FIRMADO no lo produjo el motor ------------------


def _firmado(**over) -> dict[str, str]:
    """La fila que produce de verdad `sign_dictamen`: status de la persona,
    `signed_by` puesto y un `basis` que NO trae evidencia ni parámetros."""
    base = {
        "verdict_signed": True,
        "verdict_status": "normal_operation",
        "verdict_label": "OPERACIÓN NORMAL",
        # Lo que pone `builder.py` cuando el basis firmado no trae versión.
        "rule_set_version": "sin versión",
        "verdict_basis": {},
    }
    base.update(over)
    return dict(sections_for(facts_from(model(**base))))


def test_un_veredicto_FIRMADO_no_se_le_atribuye_a_las_reglas() -> None:
    """Lo eligió y lo firmó UNA PERSONA, y el papel se lo colgaba al motor.

    Vivo en el PDF que se enseñó el 2026-09-13: «El veredicto «OPERACIÓN NORMAL»
    lo produjo el conjunto de reglas sin versión», cuatro líneas encima de «Este
    dictamen lo firmó un inspector» y de la huella del firmante en la §14. Y de
    paso nombraba un conjunto de reglas —«sin versión»— que no existe: el
    `ABSENT` nunca se alcanza porque el builder ya metió esa cadena.
    """
    texto = _firmado()["Por qué este veredicto"]
    assert "conjunto de reglas" not in texto, "sigue atribuyéndole el veredicto al motor"
    assert "firmó" in texto


def test_la_rama_firmada_NO_se_come_la_cadena_de_dictamenes() -> None:
    """La salida temprana dejaba la sección en dos frases y callaba un hecho que
    la §9 del MISMO papel enseña en una tabla."""
    texto = _firmado(dictamens=_cadena(4))["Por qué este veredicto"]
    assert "dictámenes en la cadena" in texto


def test_sin_firmar_se_sigue_citando_la_version_de_reglas() -> None:
    """Control: el dictamen automático no puede perder su trazabilidad."""
    texto = dict(sections_for(facts_from(model(verdict_basis=BASIS))))["Por qué este veredicto"]
    assert "conjunto de reglas" in texto and "dictamen-v1" in texto


# ---- [T-7.38·E] «no quedó guardado» sobre un fundamento que SÍ se guardó -----


def test_una_razon_ESCRITA_al_firmar_no_se_declara_perdida() -> None:
    """El inspector escribió su razón y el papel decía que no quedó guardada.

    Presentaba como accidente —se perdió— lo que es de diseño: una firma humana
    no registra umbral instrumental, nunca lo tuvo. Son dos estados distintos y
    el papel los confundía en uno.
    """
    texto = _firmado(verdict_basis={"notes": "revisión en sitio, sin daño visible"})[
        "Por qué este veredicto"
    ]
    assert "no quedó guardado" not in texto, "declara perdido un fundamento que consta"
    assert "nota" in texto.lower()


def test_firmar_SIN_escribir_nada_sigue_diciendo_que_no_consta() -> None:
    """`body.notes is None` produce `basis = {}` exacto: un firmado sin razón es
    indistinguible de uno con razón si solo se mira `verdict_signed`. Por eso el
    hecho es el DATO, no la inferencia."""
    texto = _firmado(verdict_basis={})["Por qué este veredicto"]
    assert "nota" not in texto.lower()


def test_el_dictamen_AUTOMATICO_no_declara_nota_de_nadie() -> None:
    """`rules.py` mete `notes` ENLATADO en todo dictamen automático («dictamen
    automático preliminar»): tomarlo por la razón de una persona convertiría una
    cadena de fábrica en el fundamento de un veredicto."""
    texto = dict(sections_for(facts_from(model(verdict_basis=BASIS))))["Por qué este veredicto"]
    assert "nota" not in texto.lower()
