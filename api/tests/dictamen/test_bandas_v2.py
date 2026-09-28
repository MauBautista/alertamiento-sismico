"""Regla ``dictamen-v2`` en tres bandas (T-9.30 · D-43). PURA: sin base.

VERDE ⇒ ``normal_operation``; AMARILLO ⇒ ``inhabit_monitor``; ROJO ⇒
``no_inhabit_inspect``. Deciden SOLO la PGA máxima de los sensores activos, los
reportes de daño y la calibración. SASMEX y la severidad ya no deciden (regla de
oro 1: umbrales fijos con su procedencia escrita en el ``basis``, jamás IA).
"""

from __future__ import annotations

import pytest

from takab_api.dictamen.rules import (
    RULE_SET_VERSION,
    DictamenParamsV2,
    EvalInputV2,
    evaluate_v2,
    resolve_params_v2,
)
from takab_api.settings import Settings

P = DictamenParamsV2(verde_max_g=0.04, rojo_min_g=0.10)


def _inp(**kw: object) -> EvalInputV2:
    base: dict = {
        "pga_g": 0.01,
        "pga_source": "features",
        "active_sensors": 2,
        "uncalibrated_sensors": 0,
        "damage_reports": 0,
        "damage_keys": (),
        "severity": "info",
        "trigger": "local_threshold",
        "event_id": None,
    }
    base.update(kw)
    return EvalInputV2(**base)


# (descripción, entrada, banda esperada)
CASOS: list[tuple[str, dict, str]] = [
    ("pga bajo, calibrado, sin daños", {}, "verde"),
    ("pga justo bajo el verde", {"pga_g": 0.0399}, "verde"),
    ("pga EN el umbral verde ya es amarillo", {"pga_g": 0.04}, "amarillo"),
    ("pga en la banda media", {"pga_g": 0.07}, "amarillo"),
    ("pga EN el umbral rojo", {"pga_g": 0.10}, "rojo"),
    ("pga muy alto", {"pga_g": 0.5}, "rojo"),
    ("sin PGA ⇒ AMARILLO", {"pga_g": None, "pga_source": "none"}, "amarillo"),
    ("un sensor activo sin calibrar", {"uncalibrated_sensors": 1}, "amarillo"),
    ("sin sensores activos ⇒ no hay calibración", {"active_sensors": 0}, "amarillo"),
    (
        "un sensor retirado sin calibrar no impide el VERDE (no llega como activo)",
        {"active_sensors": 1, "uncalibrated_sensors": 0},
        "verde",
    ),
    ("daño estructural", {"damage_reports": 1, "damage_keys": ("structural",)}, "rojo"),
    ("personas atrapadas", {"damage_reports": 1, "damage_keys": ("people_trapped",)}, "rojo"),
    ("fuga de gas", {"damage_reports": 1, "damage_keys": ("gas_leak",)}, "rojo"),
    ("daño no estructural", {"damage_reports": 1, "damage_keys": ("non_structural",)}, "amarillo"),
    ("fuga de agua", {"damage_reports": 1, "damage_keys": ("water_leak",)}, "amarillo"),
    ("eléctrico", {"damage_reports": 1, "damage_keys": ("electrical",)}, "amarillo"),
    ("reporte sin categorías impide el VERDE", {"damage_reports": 1}, "amarillo"),
    ("categoría desconocida: prudente", {"damage_reports": 1, "damage_keys": ("x",)}, "amarillo"),
    (
        "daño estructural gana sobre pga bajo y calibración",
        {"pga_g": 0.001, "damage_reports": 2, "damage_keys": ("water_leak", "structural")},
        "rojo",
    ),
    ("SASMEX crítico con PGA baja YA NO fuerza ROJO", {"severity": "critical"}, "verde"),
    (
        "SASMEX crítico sin PGA ⇒ AMARILLO, no ROJO",
        {"severity": "critical", "trigger": "sasmex", "pga_g": None, "pga_source": "none"},
        "amarillo",
    ),
]

STATUS = {"verde": "normal_operation", "amarillo": "inhabit_monitor", "rojo": "no_inhabit_inspect"}


@pytest.mark.parametrize(("desc", "kw", "banda"), CASOS, ids=[c[0] for c in CASOS])
def test_tabla_de_bandas(desc: str, kw: dict, banda: str) -> None:
    d = evaluate_v2(_inp(**kw), P)
    assert d.band == banda, desc
    assert d.status == STATUS[banda]
    assert d.basis["band"] == banda


def test_verde_max_cero_desactiva_el_automatico() -> None:
    d = evaluate_v2(_inp(pga_g=0.0), DictamenParamsV2(verde_max_g=0.0, rojo_min_g=0.10))
    assert d.band == "amarillo"


def test_el_basis_lleva_version_evidencia_umbrales_y_motivos() -> None:
    d = evaluate_v2(
        _inp(pga_g=0.07, uncalibrated_sensors=1, damage_reports=1, damage_keys=("water_leak",)),
        P,
    )
    b = d.basis
    assert b["rule_set_version"] == RULE_SET_VERSION == "dictamen-v2"
    assert b["params"] == {"verde_max_g": 0.04, "rojo_min_g": 0.10}
    ev = b["evidence"]
    assert ev["pga_g"] == pytest.approx(0.07)
    assert ev["calibrated"] is False
    assert ev["active_sensors"] == 2
    assert ev["uncalibrated_sensors"] == 1
    assert ev["damage_categories"] == ["water_leak"]
    assert ev["insufficient_data"] is False
    # La procedencia de la banda queda ESCRITA: cada motivo que la sostiene.
    assert set(b["motivos"]) == {"pga_banda_amarilla", "sin_calibracion", "dano:water_leak"}


def test_sin_pga_no_se_fabrica_un_cero() -> None:
    d = evaluate_v2(_inp(pga_g=None, pga_source="none"), P)
    assert d.basis["evidence"]["pga_g"] is None
    assert d.basis["evidence"]["insufficient_data"] is True
    assert "sin_pga" in d.basis["motivos"]


def test_la_severidad_no_decide_pero_consta() -> None:
    a = evaluate_v2(_inp(severity="critical", trigger="sasmex"), P)
    b = evaluate_v2(_inp(severity="info"), P)
    assert a.band == b.band == "verde"
    assert a.basis["evidence"]["severity"] == "critical"


# ------------------------------------------------------------- resolve_params_v2


def test_resolve_defaults() -> None:
    p = resolve_params_v2(None, Settings())
    assert p == DictamenParamsV2(verde_max_g=0.04, rojo_min_g=0.10)


def test_resolve_lee_config() -> None:
    cfg = {"dictamen_v2": {"verde_max_g": 0.02, "rojo_min_g": 0.2}}
    assert resolve_params_v2(cfg, Settings()) == DictamenParamsV2(0.02, 0.2)


def test_resolve_admite_verde_cero() -> None:
    cfg = {"dictamen_v2": {"verde_max_g": 0}}
    assert resolve_params_v2(cfg, Settings()).verde_max_g == 0.0


@pytest.mark.parametrize(
    "raw",
    [
        {"verde_max_g": 0.2, "rojo_min_g": 0.1},  # invertido
        {"verde_max_g": 0.1, "rojo_min_g": 0.1},  # banda amarilla vacía = par inválido
        {"verde_max_g": 0.5},  # contra el rojo por defecto, invertido
    ],
)
def test_resolve_par_invalido_cae_a_defaults(raw: dict) -> None:
    p = resolve_params_v2({"dictamen_v2": raw}, Settings())
    assert p == DictamenParamsV2(verde_max_g=0.04, rojo_min_g=0.10)


@pytest.mark.parametrize("bad", [-0.1, "0.02", True, None])
def test_resolve_campo_invalido_cae_a_su_default(bad: object) -> None:
    p = resolve_params_v2({"dictamen_v2": {"verde_max_g": bad, "rojo_min_g": 0.2}}, Settings())
    assert p == DictamenParamsV2(verde_max_g=0.04, rojo_min_g=0.2)


def test_resolve_no_lee_los_umbrales_v1() -> None:
    """La config v1 (``dictamen``) no mueve las bandas v2."""
    cfg = {"dictamen": {"pga_no_inhabit_g": 0.5, "pga_monitor_g": 0.2}}
    assert resolve_params_v2(cfg, Settings()) == DictamenParamsV2(0.04, 0.10)
