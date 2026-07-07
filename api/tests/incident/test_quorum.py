"""Quórum distance-aware — matemática PURA (T-1.19 · G1). Sin DB.

Verifica la ventana |Δt| ≤ dist/v_P + margin con tope duro max_window, la
correlación con quórum, el determinismo orden-independiente y la resolución de
parámetros desde ``rule_sets.config`` con caída a defaults.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from takab_api.incident.quorum import (
    Detection,
    QuorumParams,
    associates,
    correlate,
    resolve_params,
)
from takab_api.settings import Settings

T0 = datetime(2026, 7, 7, 10, 0, 0, tzinfo=UTC)

# Parámetros canónicos (blueprint §4.5): v_P=6.5 km/s, margin=3 s, tope 30 s.
P = QuorumParams(min_nodes=3, v_p_km_s=6.5, margin_s=3.0, max_window_s=30.0)

# Distancias inter-sitio (km) para el dist_fn inyectado (simétricas).
_DIST = {
    ("S1", "S2"): 40.0,
    ("S1", "S3"): 90.0,
    ("S2", "S3"): 55.0,
    ("S1", "S4"): 110.0,
}


def _dist_fn(a: Detection, b: Detection) -> float:
    if a.site_id == b.site_id:
        return 0.0
    key = (a.site_id, b.site_id)
    return _DIST.get(key) or _DIST[(b.site_id, a.site_id)]


def _det(site: str, offset_s: float, *, pga: float = 0.05) -> Detection:
    return Detection(
        site_id=site,
        sensor_id=f"sensor-{site}",
        detected_at=T0 + timedelta(seconds=offset_s),
        pga_g=pga,
        lon=-99.0,
        lat=19.0,
    )


def test_associates_within_distance_window() -> None:
    # 90 km → dist/v_P = 13.85 s; +margin 3 → ventana 16.85 s. Δt=13 → asocia.
    anchor, other = _det("S1", 0), _det("S3", 13)
    assert associates(anchor, other, _dist_fn(anchor, other), P) is True


def test_associates_outside_distance_window() -> None:
    # Mismo par a 90 km (ventana 16.85 s) pero Δt=20 (< tope 30) → NO asocia.
    anchor, other = _det("S1", 0), _det("S3", 20)
    assert associates(anchor, other, _dist_fn(anchor, other), P) is False


def test_associates_hard_cap_max_window() -> None:
    # Distancia enorme haría la ventana física amplia, pero el tope duro manda.
    capped = QuorumParams(min_nodes=3, v_p_km_s=6.5, margin_s=3.0, max_window_s=5.0)
    anchor, other = _det("S1", 0), _det("S4", 10)  # 110 km, Δt=10 > tope 5
    assert associates(anchor, other, _dist_fn(anchor, other), capped) is False


def test_associates_anchor_with_itself() -> None:
    anchor = _det("S1", 0)
    assert associates(anchor, anchor, 0.0, P) is True


def test_correlate_three_detections_form_cluster() -> None:
    dets = [_det("S1", 0), _det("S2", 6), _det("S3", 13)]
    cluster = correlate(dets, _dist_fn, P)
    assert cluster is not None
    assert cluster.anchor.site_id == "S1"
    assert [d.site_id for d in cluster.members] == ["S1", "S2", "S3"]
    deltas = {v.detection.site_id: v.delta_s for v in cluster.votes}
    assert deltas["S1"] == pytest.approx(0.0)
    assert deltas["S2"] == pytest.approx(6.0)
    assert deltas["S3"] == pytest.approx(13.0)


def test_correlate_two_nodes_returns_none() -> None:
    dets = [_det("S1", 0), _det("S2", 6)]
    assert correlate(dets, _dist_fn, P) is None


def test_correlate_out_of_window_drops_below_quorum() -> None:
    # S3 a Δt=25 (> ventana 16.85 s) no asocia → sólo S1,S2 → conteo 2 < 3.
    dets = [_det("S1", 0), _det("S2", 6), _det("S3", 25)]
    assert correlate(dets, _dist_fn, P) is None


def test_correlate_is_order_independent() -> None:
    base = [_det("S1", 0), _det("S2", 6), _det("S3", 13)]
    shuffled = [base[2], base[0], base[1]]
    assert correlate(base, _dist_fn, P) == correlate(shuffled, _dist_fn, P)


def test_correlate_late_anchor_out_of_order() -> None:
    # La más temprana (S1@0) es la ancla aunque venga al final de la lista.
    dets = [_det("S3", 13), _det("S2", 6), _det("S1", 0)]
    cluster = correlate(dets, _dist_fn, P)
    assert cluster is not None
    assert cluster.anchor.site_id == "S1"


def test_resolve_params_reads_config() -> None:
    cfg = {"quorum": {"min_nodes": 4, "v_p_km_s": 7.0, "margin_s": 2.0, "max_window_s": 25.0}}
    p = resolve_params(cfg, Settings())
    assert (p.min_nodes, p.v_p_km_s, p.margin_s, p.max_window_s) == (4, 7.0, 2.0, 25.0)


def test_resolve_params_defaults_when_absent() -> None:
    s = Settings()
    for cfg in (None, {}, {"quorum": None}, {"other": 1}):
        p = resolve_params(cfg, s)
        assert p.min_nodes == s.quorum_min_nodes
        assert p.v_p_km_s == s.quorum_v_p_km_s
        assert p.margin_s == s.quorum_margin_s
        assert p.max_window_s == s.quorum_max_window_s


def test_resolve_params_invalid_field_falls_back() -> None:
    # v_P ≤ 0 y min_nodes < 2 son inválidos → cada uno cae a su default; los
    # campos válidos del config se respetan.
    s = Settings()
    cfg = {"quorum": {"v_p_km_s": -1.0, "min_nodes": 1, "margin_s": 2.5, "max_window_s": 20.0}}
    p = resolve_params(cfg, s)
    assert p.v_p_km_s == s.quorum_v_p_km_s
    assert p.min_nodes == s.quorum_min_nodes
    assert p.margin_s == 2.5
    assert p.max_window_s == 20.0


def test_resolve_params_non_numeric_falls_back() -> None:
    s = Settings()
    cfg = {"quorum": {"v_p_km_s": "fast", "margin_s": None}}
    p = resolve_params(cfg, s)
    assert p.v_p_km_s == s.quorum_v_p_km_s
    assert p.margin_s == s.quorum_margin_s


def test_resolve_params_caps_max_window() -> None:
    # Una ventana absurda de un tenant se recorta al tope físico (no suprime, acota
    # el alcance del fail-open cross-tenant §4.5) (#7).
    from takab_api.incident.quorum import _MAX_WINDOW_CEILING_S

    p = resolve_params({"quorum": {"max_window_s": 1000.0}}, Settings())
    assert p.max_window_s == _MAX_WINDOW_CEILING_S
    # Un valor por debajo del tope se respeta tal cual.
    p2 = resolve_params({"quorum": {"max_window_s": 25.0}}, Settings())
    assert p2.max_window_s == 25.0
