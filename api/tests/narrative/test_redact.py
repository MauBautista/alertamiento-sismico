"""T-2.42 · Qué sale de la nube hacia un proveedor de prosa.

La prueba que importa no es "¿se redactó el nombre?", sino "¿aparece el nombre en el
payload que se manda?". Por eso se serializa la petición completa y se busca la cadena
literal: es exactamente lo que viajaría por la red.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from takab_api.narrative.prompts import user_prompt
from takab_api.narrative.redact import absences_of, facts_from, redact_basis
from tests.dictamen.test_pdf import model

BASIS = {
    "rule_set_version": "dictamen-v1",
    "evidence": {
        "severity": "warning",
        "pga_g": 0.081,
        "node_count": 4,
        "corroborated": True,
        "event_id": "EVT-001",
        "trigger": "sasmex",
        "pga_source": "features",
        "insufficient_data": False,
    },
    "params": {"pga_no_inhabit_g": 0.25, "pga_monitor_g": 0.05},
    "notes": "dictamen automático preliminar",
}


def _payload(m) -> str:
    return json.dumps(asdict(facts_from(m)), ensure_ascii=False, default=str)


def test_el_nombre_del_inmueble_no_sale_de_la_nube() -> None:
    m = model(site_name="Planta Cholula", site_code="CHL-A")
    assert "Planta Cholula" not in _payload(m)


def test_las_coordenadas_no_salen_de_la_nube() -> None:
    """El sitio es un edificio con gente dentro; su posición no se manda a un tercero."""
    m = model(site_lat=19.06, site_lon=-98.30, epicenter_lat=16.80, epicenter_lon=-99.50)
    payload = _payload(m)
    for coord in ("19.06", "-98.3", "16.8", "-99.5"):
        assert coord not in payload
    # Pero sí se dice SI hay epicentro: la prosa tiene que poder mencionarlo.
    assert facts_from(m).has_epicenter is True


def test_el_identificador_del_incidente_no_sale() -> None:
    m = model(incident_id="11111111-2222-3333-4444-555555555555")
    assert "11111111" not in _payload(m).replace(facts_from(m).folio, "")


def test_quien_firmo_no_sale() -> None:
    """`signed_by` es un usuario de Cognito. Sale el HECHO de que hay firma, no quién."""
    from takab_api.dictamen.model import DictamenRow

    row = model().dictamens[0]
    firmado = DictamenRow(
        row.dictamen_id, row.status, row.created_at, "usr-cognito-abc", row.rule_set_version, None
    )
    m = model(dictamens=[firmado], verdict_signed=True)
    payload = _payload(m)
    assert "usr-cognito-abc" not in payload
    assert facts_from(m).verdict_signed is True


def test_los_hashes_de_evidencia_no_salen() -> None:
    assert "a" * 64 not in _payload(model())


def test_el_basis_solo_deja_pasar_umbrales_y_evidencia_numerica() -> None:
    out = redact_basis(BASIS)
    assert out["params"] == {"pga_no_inhabit_g": 0.25, "pga_monitor_g": 0.05}
    assert out["evidence"]["pga_g"] == 0.081
    # `event_id` es correlacionable y la prosa no lo necesita para explicar un umbral.
    assert "event_id" not in out["evidence"]
    assert "notes" not in out


def test_un_basis_ausente_o_roto_no_revienta() -> None:
    assert redact_basis(None) == {}
    assert redact_basis({"evidence": "no es un dict"}) == {}


def test_el_prompt_de_usuario_es_exactamente_los_hechos_redactados() -> None:
    """Sin interpretación previa: lo que hay es lo que se midió."""
    m = model(site_name="Planta Cholula")
    prompt = user_prompt(facts_from(m))
    assert "Planta Cholula" not in prompt
    assert m.folio in prompt


# ---- ausencias ---------------------------------------------------------------


def test_un_incidente_completo_declara_pocas_ausencias() -> None:
    gaps = absences_of(model())
    # El modelo de prueba no trae onda cruda: esa ausencia SÍ debe estar.
    assert any("miniSEED" in g or "onda cruda" in g or "espectral" in g.lower() for g in gaps)


def test_cada_hueco_produce_su_razon() -> None:
    gaps = absences_of(
        model(
            peak_pga_g=None,
            peak_pgv_cms=None,
            calibrated=False,
            felt_band="unknown",
            lead_time_s=None,
            lead_time_reason="no_peak",
            channels=[],
            station_count=0,
            catalog_line=None,
            epicenter_lat=None,
            epicenter_lon=None,
            dictamens=[],
        )
    )
    texto = " ".join(gaps)
    assert "aceleración pico" in texto.lower()
    assert "calibración" in texto.lower()
    assert "no hubo pico medido" in texto.lower()
    assert "dictamen" in texto.lower()
    assert len(gaps) >= 9


def test_un_canal_saturado_se_declara_como_ausencia_de_medicion() -> None:
    """Un canal recortado no midió el pico: midió el techo del ADC."""
    from takab_api.dictamen.model import ChannelRow

    ch = model().channels[0]
    saturado = ChannelRow("ENZ", 0.5, 20.0, 0.1, 9.0, 5.0, True, 120, ch.peak_ts)
    gaps = absences_of(model(channels=[saturado]))
    assert any("satura" in g.lower() and "ENZ" in g for g in gaps)
