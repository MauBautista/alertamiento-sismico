"""Soft-gate #2 (T-1.19 · G7): valida los parametros del quorum distance-aware
contra un catalogo de sismos del SSN.  NO bloquea el merge: informa si
(v_P, margen, tope) permiten que >= min_nodes estaciones ASOCIEN un mismo sismo.

Reusa la MISMA logica determinista de ``takab_api.incident.quorum`` (blueprint
4.5): aqui solo se derivan los arribos P teoricos (modelo de una capa
t = t0 + hipocentro/v_P) y las distancias inter-sitio (haversine).  Origen del
gate: [ANALISIS-00] pregunta abierta #2 — una ventana fija de 2-5 s era
fisicamente inalcanzable a 90-110 km (Dt de arribo de 10-20 s).

Uso:
    cd api && uv run python tools/quorum_ssn_validation.py
    (--catalog, --v-p-km-s, --margin-s, --max-window-s, --min-nodes,
     --v-p-travel-km-s, --fixed-window-s para recalibrar/experimentar)

Codigo de salida: 0 si TODOS los sismos alcanzan quorum con los params dados;
!=0 si alguno no (senal de recalibracion para el humano).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from takab_api.incident.quorum import (
    Detection,
    QuorumParams,
    associates,
    correlate,
    resolve_params,
)
from takab_api.settings import Settings

EARTH_RADIUS_KM = 6371.0
# Ventana fija "antigua" (tope de la vieja regla 2-5 s) para el contraste [ANALISIS-00].
FIXED_WINDOW_S = 5.0
DEFAULT_CATALOG = (
    Path(__file__).resolve().parent.parent / "tests" / "incident" / "fixtures" / "ssn_catalog.json"
)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia de circulo maximo (km) entre dos puntos lat/lon (grados)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _p_travel_s(epi_km: float, depth_km: float, v_p_travel: float) -> float:
    """Arribo P teorico (s tras el origen): hipocentro / v_P (modelo de una capa)."""
    return math.hypot(epi_km, depth_km) / v_p_travel


def _plausible_pga_g(magnitude: float, hypo_km: float) -> float:
    """PGA ilustrativa (decaimiento tipo GMPE simple). NO interviene en la
    asociacion (quorum.py no usa pga); solo puebla Detection.pga_g de forma
    plausible."""
    return round(10 ** (0.5 * magnitude - 2.8) / max(hypo_km, 1.0), 5)


@dataclass(frozen=True)
class StationRow:
    """Fila de reporte por estacion, relativa a la ancla (deteccion mas temprana)."""

    station_id: str
    name: str
    epi_km: float
    arrival_s: float  # tras el origen
    delta_anchor_s: float  # detected_at - ancla
    dist_to_anchor_km: float
    window_s: float  # dist/v_P + margen (sin aplicar tope; el tope se ve en assoc_daw)
    assoc_daw: bool  # distance-aware (misma regla que quorum.associates)
    assoc_fixed: bool  # ventana fija de contraste


@dataclass(frozen=True)
class QuakeResult:
    """Resultado por sismo: si alcanza quorum distance-aware vs. ventana fija."""

    event_id: str
    name: str
    magnitude: float
    n_stations: int
    n_assoc_daw: int
    quorum_daw: bool
    n_assoc_fixed: int
    quorum_fixed: bool
    rows: list[StationRow]


def _build_detections(
    quake: dict, stations_by_id: dict, v_p_travel: float
) -> list[tuple[Detection, float, float]]:
    """Deriva por estacion del sismo: (Detection, distancia epicentral km,
    arribo P en s tras el origen)."""
    epi_lat = quake["epicenter"]["lat"]
    epi_lon = quake["epicenter"]["lon"]
    origin = datetime.fromisoformat(quake["origin_time_utc"].replace("Z", "+00:00"))
    depth = float(quake["depth_km"])
    mag = float(quake["magnitude"])
    out: list[tuple[Detection, float, float]] = []
    for sid in quake["stations"]:
        st = stations_by_id[sid]
        epi_km = haversine_km(epi_lat, epi_lon, st["lat"], st["lon"])
        arrival = _p_travel_s(epi_km, depth, v_p_travel)
        det = Detection(
            site_id=sid,
            sensor_id=st.get("sensor_id", f"RS-{sid}"),
            detected_at=origin + timedelta(seconds=arrival),
            pga_g=_plausible_pga_g(mag, math.hypot(epi_km, depth)),
            lon=st["lon"],
            lat=st["lat"],
        )
        out.append((det, epi_km, arrival))
    return out


def _dist_fn(a: Detection, b: Detection) -> float:
    return haversine_km(a.lat, a.lon, b.lat, b.lon)


def evaluate_quake(
    quake: dict,
    stations_by_id: dict,
    params: QuorumParams,
    *,
    fixed_window_s: float,
    v_p_travel: float,
) -> QuakeResult:
    """Evalua un sismo: correlaciona con la logica real de quorum.py y arma el
    reporte (incluye el contraste con la ventana fija)."""
    dets = _build_detections(quake, stations_by_id, v_p_travel)
    detections = [d for d, _, _ in dets]
    epi_by_det = {id(d): epi for d, epi, _ in dets}
    arrival_by_det = {id(d): arr for d, _, arr in dets}

    # Autoridad: la MISMA correlacion determinista del engine (quorum.correlate).
    cluster = correlate(detections, _dist_fn, params)
    quorum_daw = cluster is not None
    # Ancla = mas temprana, con el mismo desempate que correlate.
    anchor = min(detections, key=lambda d: (d.detected_at, d.site_id, d.sensor_id))

    rows: list[StationRow] = []
    n_assoc_daw = 0
    n_assoc_fixed = 0
    for det in sorted(detections, key=lambda d: (d.detected_at, d.site_id, d.sensor_id)):
        dt = (det.detected_at - anchor.detected_at).total_seconds()
        dist_anchor = _dist_fn(anchor, det)
        window = dist_anchor / params.v_p_km_s + params.margin_s
        # Misma regla que quorum.correlate: la ancla cuenta por identidad.
        a_daw = det is anchor or associates(anchor, det, dist_anchor, params)
        a_fixed = abs(dt) <= fixed_window_s
        n_assoc_daw += 1 if a_daw else 0
        n_assoc_fixed += 1 if a_fixed else 0
        rows.append(
            StationRow(
                station_id=det.site_id,
                name=stations_by_id[det.site_id]["name"],
                epi_km=epi_by_det[id(det)],
                arrival_s=arrival_by_det[id(det)],
                delta_anchor_s=dt,
                dist_to_anchor_km=dist_anchor,
                window_s=window,
                assoc_daw=a_daw,
                assoc_fixed=a_fixed,
            )
        )

    return QuakeResult(
        event_id=quake["event_id"],
        name=quake["name"],
        magnitude=float(quake["magnitude"]),
        n_stations=len(detections),
        n_assoc_daw=n_assoc_daw,
        quorum_daw=quorum_daw,
        n_assoc_fixed=n_assoc_fixed,
        quorum_fixed=n_assoc_fixed >= params.min_nodes,
        rows=rows,
    )


@dataclass(frozen=True)
class Validation:
    """Salida agregada de run_validation (testable, sin efectos de impresion)."""

    results: list[QuakeResult]
    params: QuorumParams
    v_p_travel: float
    fixed_window_s: float
    all_quorum: bool


def _config_from_overrides(overrides: dict | None) -> dict | None:
    """Empaqueta overrides CLI como un ``rule_sets.config`` parcial; los campos
    ausentes caen a defaults en resolve_params. Sin overrides -> None (defaults)."""
    if not overrides:
        return None
    quorum = {k: v for k, v in overrides.items() if v is not None}
    return {"quorum": quorum} if quorum else None


def run_validation(
    catalog_path: Path | str = DEFAULT_CATALOG,
    *,
    overrides: dict | None = None,
    v_p_travel: float | None = None,
    fixed_window_s: float = FIXED_WINDOW_S,
    settings: Settings | None = None,
) -> Validation:
    """Carga el catalogo y evalua cada sismo con los params resueltos.

    ``overrides`` (dict con min_nodes/v_p_km_s/margin_s/max_window_s) simula un
    ``rule_sets.config.quorum``; None -> defaults de Settings. La herramienta LEE
    config, no constantes."""
    data = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    params = resolve_params(_config_from_overrides(overrides), settings or Settings())
    v_travel = v_p_travel if v_p_travel is not None else params.v_p_km_s
    stations_by_id = {s["id"]: s for s in data["reference_stations"]}
    results = [
        evaluate_quake(
            q, stations_by_id, params, fixed_window_s=fixed_window_s, v_p_travel=v_travel
        )
        for q in data["earthquakes"]
    ]
    return Validation(
        results=results,
        params=params,
        v_p_travel=v_travel,
        fixed_window_s=fixed_window_s,
        all_quorum=all(r.quorum_daw for r in results),
    )


def _fmt_report(v: Validation) -> str:
    """Reporte legible (tabla por sismo) del resultado de la validacion."""
    p = v.params
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("Soft-gate #2 · Quorum distance-aware vs. catalogo SSN (T-1.19 · G7)")
    lines.append(
        f"params: min_nodes={p.min_nodes}  v_P={p.v_p_km_s} km/s  "
        f"margen={p.margin_s} s  tope={p.max_window_s} s  |  "
        f"v_P_viaje={v.v_p_travel} km/s  ventana_fija={v.fixed_window_s} s"
    )
    lines.append("=" * 78)
    for r in v.results:
        lines.append("")
        lines.append(f"[{r.event_id}] {r.name} (M{r.magnitude})  · {r.n_stations} estaciones")
        lines.append(
            f"  {'estacion':<18}{'epi_km':>8}{'arribo_s':>10}"
            f"{'d_ancla_s':>11}{'d_ancla_km':>12}{'ventana_s':>11}{'asoc':>6}{'fijo':>6}"
        )
        for row in r.rows:
            lines.append(
                f"  {row.station_id:<18}{row.epi_km:>8.1f}{row.arrival_s:>10.1f}"
                f"{row.delta_anchor_s:>11.2f}{row.dist_to_anchor_km:>12.1f}"
                f"{row.window_s:>11.2f}{_yn(row.assoc_daw):>6}{_yn(row.assoc_fixed):>6}"
            )
        daw = "SI " if r.quorum_daw else "NO "
        fix = "SI " if r.quorum_fixed else "NO "
        lines.append(
            f"  -> quorum distance-aware: {daw}({r.n_assoc_daw}/{r.n_stations} >= "
            f"{p.min_nodes})   |   ventana fija {v.fixed_window_s:g}s: {fix}"
            f"({r.n_assoc_fixed}/{r.n_stations})"
        )
    lines.append("")
    lines.append("-" * 78)
    ok = sum(1 for r in v.results if r.quorum_daw)
    fix_ok = sum(1 for r in v.results if r.quorum_fixed)
    lines.append(
        f"RESUMEN: distance-aware {ok}/{len(v.results)} sismos con quorum  |  "
        f"ventana fija {v.fixed_window_s:g}s {fix_ok}/{len(v.results)}"
    )
    if v.all_quorum:
        lines.append("VEREDICTO: PASA. Los params asocian >= min_nodes en todos los sismos.")
    else:
        lines.append("VEREDICTO: REVISAR. Algun sismo NO alcanza quorum -> recalibrar params.")
    lines.append("-" * 78)
    return "\n".join(lines)


def _yn(b: bool) -> str:
    return "si" if b else "no"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida params del quorum vs. catalogo SSN.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--min-nodes", type=int, default=None)
    parser.add_argument("--v-p-km-s", type=float, default=None)
    parser.add_argument("--margin-s", type=float, default=None)
    parser.add_argument("--max-window-s", type=float, default=None)
    parser.add_argument(
        "--v-p-travel-km-s",
        type=float,
        default=None,
        help="v_P para derivar arribos; default = v_P de asociacion",
    )
    parser.add_argument("--fixed-window-s", type=float, default=FIXED_WINDOW_S)
    args = parser.parse_args(argv)

    overrides = {
        "min_nodes": args.min_nodes,
        "v_p_km_s": args.v_p_km_s,
        "margin_s": args.margin_s,
        "max_window_s": args.max_window_s,
    }
    v = run_validation(
        args.catalog,
        overrides=overrides,
        v_p_travel=args.v_p_travel_km_s,
        fixed_window_s=args.fixed_window_s,
    )
    print(_fmt_report(v))
    return 0 if v.all_quorum else 1


if __name__ == "__main__":
    sys.exit(main())
