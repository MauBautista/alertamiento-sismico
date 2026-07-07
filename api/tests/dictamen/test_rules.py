"""Reglas PURAS del dictamen automático preliminar (T-1.20 · B5).

Mapeo severidad/PGA → status + regla de nodos (el quórum corroborado ELEVA la
prudencia, nunca la degrada — blueprint §4.5: "eleva la confianza … y alimenta
el dictamen"). Sin DB; espejo del patrón ``incident.quorum``.
"""

from __future__ import annotations

from takab_api.dictamen.rules import (
    RULE_SET_VERSION,
    DictamenParams,
    EvalInput,
    evaluate,
    resolve_params,
)
from takab_api.settings import Settings

PARAMS = DictamenParams(pga_no_inhabit_g=0.25, pga_monitor_g=0.05)


def _inp(**kw: object) -> EvalInput:
    base: dict = {
        "severity": "info",
        "pga_g": 0.0,
        "node_count": 0,
        "quorum_min_nodes": 3,
        "trigger": "local_threshold",
        "event_id": None,
    }
    base.update(kw)
    return EvalInput(**base)


# ------------------------------------------------------------- severidad/PGA


def test_critical_severity_is_no_inhabit() -> None:
    d = evaluate(_inp(severity="critical", pga_g=0.01), PARAMS)
    assert d.status == "no_inhabit_inspect"


def test_pga_at_no_inhabit_threshold_is_no_inhabit() -> None:
    d = evaluate(_inp(severity="info", pga_g=0.25), PARAMS)
    assert d.status == "no_inhabit_inspect"


def test_warning_severity_is_inhabit_monitor() -> None:
    d = evaluate(_inp(severity="warning", pga_g=0.0), PARAMS)
    assert d.status == "inhabit_monitor"


def test_pga_at_monitor_threshold_is_inhabit_monitor() -> None:
    d = evaluate(_inp(severity="watch", pga_g=0.05), PARAMS)
    assert d.status == "inhabit_monitor"


def test_low_pga_low_severity_is_normal_operation() -> None:
    for sev in ("info", "watch"):
        d = evaluate(_inp(severity=sev, pga_g=0.01), PARAMS)
        assert d.status == "normal_operation"


def test_missing_pga_treated_as_zero() -> None:
    d = evaluate(_inp(severity="info", pga_g=None), PARAMS)
    assert d.status == "normal_operation"


# ------------------------------------------------------------ regla de nodos


def test_quorum_corroboration_elevates_normal_to_monitor() -> None:
    d = evaluate(_inp(severity="info", pga_g=0.01, node_count=3), PARAMS)
    assert d.status == "inhabit_monitor"
    assert d.basis["evidence"]["corroborated"] is True


def test_quorum_below_min_does_not_elevate() -> None:
    d = evaluate(_inp(severity="info", pga_g=0.01, node_count=2), PARAMS)
    assert d.status == "normal_operation"
    assert d.basis["evidence"]["corroborated"] is False


def test_quorum_never_degrades_no_inhabit() -> None:
    d = evaluate(_inp(severity="critical", pga_g=0.4, node_count=5), PARAMS)
    assert d.status == "no_inhabit_inspect"


# ------------------------------------------------------------------- basis


def test_basis_carries_version_evidence_and_params() -> None:
    d = evaluate(
        _inp(severity="warning", pga_g=0.07, node_count=4, event_id="EVT-X", trigger="quorum"),
        PARAMS,
    )
    assert d.basis["rule_set_version"] == RULE_SET_VERSION
    ev = d.basis["evidence"]
    assert ev["severity"] == "warning"
    assert ev["pga_g"] == 0.07
    assert ev["node_count"] == 4
    assert ev["event_id"] == "EVT-X"
    assert ev["trigger"] == "quorum"
    assert d.basis["params"] == {"pga_no_inhabit_g": 0.25, "pga_monitor_g": 0.05}


# ----------------------------------------------------------- resolve_params


def test_resolve_params_defaults_when_absent() -> None:
    s = Settings()
    p = resolve_params(None, s)
    assert p.pga_no_inhabit_g == s.dictamen_pga_no_inhabit_g
    assert p.pga_monitor_g == s.dictamen_pga_monitor_g


def test_resolve_params_reads_config() -> None:
    cfg = {"dictamen": {"pga_no_inhabit_g": 0.30, "pga_monitor_g": 0.10}}
    p = resolve_params(cfg, Settings())
    assert p.pga_no_inhabit_g == 0.30
    assert p.pga_monitor_g == 0.10


def test_resolve_params_invalid_field_falls_back() -> None:
    s = Settings()
    cfg = {"dictamen": {"pga_no_inhabit_g": -1, "pga_monitor_g": "alto"}}
    p = resolve_params(cfg, s)
    assert p.pga_no_inhabit_g == s.dictamen_pga_no_inhabit_g
    assert p.pga_monitor_g == s.dictamen_pga_monitor_g


def test_resolve_params_inverted_thresholds_fall_back() -> None:
    """monitor ≥ no_inhabit invertiría la escala → se descarta el par completo."""
    s = Settings()
    cfg = {"dictamen": {"pga_no_inhabit_g": 0.05, "pga_monitor_g": 0.25}}
    p = resolve_params(cfg, s)
    assert p.pga_no_inhabit_g == s.dictamen_pga_no_inhabit_g
    assert p.pga_monitor_g == s.dictamen_pga_monitor_g
