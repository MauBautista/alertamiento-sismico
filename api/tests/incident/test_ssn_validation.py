"""Soft-gate #2 (T-1.19 · G7): la herramienta de validacion del quorum corre y,
con los params por defecto, TODOS los sismos del catalogo SSN alcanzan quorum.

Es un SOFT-gate: INFORMA, no bloquea el merge del engine (que ya lee
``rule_sets.config.quorum``). Un fallo aqui significa "recalibrar los params",
no "el codigo esta mal". La herramienta reusa la logica real de
``takab_api.incident.quorum`` (no la re-implementa).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_API_DIR = Path(__file__).resolve().parents[2]
_TOOL_PATH = _API_DIR / "tools" / "quorum_ssn_validation.py"
_CATALOG = _API_DIR / "tests" / "incident" / "fixtures" / "ssn_catalog.json"


def _load_tool():
    """Carga la herramienta (fuera de src/) por ruta; se registra en sys.modules
    antes de ejecutar porque los dataclass con anotaciones diferidas lo requieren."""
    spec = importlib.util.spec_from_file_location("quorum_ssn_validation", _TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOOL = _load_tool()


def test_catalog_is_well_formed() -> None:
    data = json.loads(_CATALOG.read_text(encoding="utf-8"))
    quakes = data["earthquakes"]
    assert 3 <= len(quakes) <= 5
    station_ids = {s["id"] for s in data["reference_stations"]}
    assert len(station_ids) == len(data["reference_stations"])  # ids unicos
    for q in quakes:
        assert q["stations"], q["event_id"]
        assert set(q["stations"]) <= station_ids  # sin estaciones colgadas
        assert -120 < q["epicenter"]["lon"] < -85
        assert 10 < q["epicenter"]["lat"] < 33  # dentro de Mexico


def test_tool_runs_and_all_quakes_reach_quorum() -> None:
    v = TOOL.run_validation(_CATALOG)
    assert v.results, "el catalogo no produjo resultados"
    # Con los defaults del blueprint (v_P=6.5, margen=3, tope=30, min_nodes=3)
    # cada sismo real debe asociar >= min_nodes estaciones.
    for r in v.results:
        assert r.quorum_daw, f"{r.event_id} NO alcanza quorum distance-aware"
        assert r.n_assoc_daw >= v.params.min_nodes, r.event_id
    assert v.all_quorum is True


def test_main_exit_code_zero_with_defaults(capsys: pytest.CaptureFixture[str]) -> None:
    rc = TOOL.main(["--catalog", str(_CATALOG)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "VEREDICTO: PASA" in out


def test_soft_gate_reproduces_analisis_00() -> None:
    # [ANALISIS-00]: una ventana fija de 5 s NO alcanza quorum a distancias
    # inter-ciudad, mientras la distance-aware SI. Debe existir al menos un
    # sismo que lo demuestre; si no, la fixture perdio su valor de gate.
    v = TOOL.run_validation(_CATALOG)
    demostradores = [r for r in v.results if r.quorum_daw and not r.quorum_fixed]
    assert demostradores, "ningun sismo contrasta distance-aware vs ventana fija"


def test_quorum_matches_pure_correlate_count() -> None:
    # La herramienta usa quorum.correlate como autoridad; el conteo por fila
    # (n_assoc_daw) debe ser coherente con esa decision (>= min_nodes iff quorum).
    v = TOOL.run_validation(_CATALOG)
    for r in v.results:
        assert r.quorum_daw == (r.n_assoc_daw >= v.params.min_nodes), r.event_id


def test_derived_p_arrivals_match_tool() -> None:
    # Los arribos P documentados en la fixture deben coincidir con lo que la
    # herramienta computa (guard de regresion del modelo de tiempo de viaje).
    data = json.loads(_CATALOG.read_text(encoding="utf-8"))
    documented = {q["event_id"]: q.get("derived_p_arrival_s", {}) for q in data["earthquakes"]}
    v = TOOL.run_validation(_CATALOG)
    for r in v.results:
        computed = {row.station_id: row.arrival_s for row in r.rows}
        for sid, expected in documented[r.event_id].items():
            assert computed[sid] == pytest.approx(expected, abs=0.2), (r.event_id, sid)


def test_tighter_window_can_break_quorum() -> None:
    # Recalibracion: forzar margen=0 y un tope pequeno debe poder romper el
    # quorum de algun sismo -> la herramienta detecta y devolveria exit !=0.
    v = TOOL.run_validation(_CATALOG, overrides={"margin_s": 0.0, "max_window_s": 5.0})
    assert not v.all_quorum
