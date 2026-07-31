#!/usr/bin/env python3
"""Genera la geografía inline del panel del gabinete (T-2.23).

Fuente: Natural Earth 1:50m (DOMINIO PÚBLICO) — espejo oficial en GitHub
(nvkelso/natural-earth-vector). Se bajan dos capas de LÍNEAS:

- ne_50m_coastline            → costas
- ne_50m_admin_1_states_provinces_lines → límites estatales (se filtra México)

y se recortan al bbox de México (+contexto), se simplifican con
Douglas-Peucker (~2 km de tolerancia — sobra para un mapa regional de
100-800 km) y se cuantizan a 3 decimales (~110 m). La salida es UN bloque JS
(`const GEO = {...}`) que se pega inline en `edge/takab_edge/local_api/index.html`
— el panel es offline por diseño: cero tiles, cero peticiones.

Uso (one-time, documentado en el PR de T-2.23):
    python3 takab-docs/design/edge-panel/tools/gen-geografia-mexico.py > /tmp/geo-mexico.js

El panel NO ejecuta esto jamás; es una herramienta de generación de activos.
"""

from __future__ import annotations

import json
import sys
import urllib.request

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
COAST = f"{BASE}/ne_50m_coastline.geojson"
# Los límites estatales de México NO existen en la capa 1:50m (solo países
# grandes); se toman de la 1:10m y la simplificación DP los deja del mismo peso.
STATES = f"{BASE}/ne_10m_admin_1_states_provinces_lines.geojson"

# bbox México + contexto (Guatemala/Belice/EEUU fronterizos quedan cortados a línea)
LON_MIN, LON_MAX = -120.0, -84.0
LAT_MIN, LAT_MAX = 12.0, 35.0

TOL_DEG = 0.02  # Douglas-Peucker ≈ 2 km
QUANT = 3  # decimales ≈ 110 m


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 — fuente fija NE
        return json.load(r)


def clip_segments(coords: list) -> list[list]:
    """Corta una línea al bbox: fuera ⇒ el segmento se parte (sin unir con recta)."""
    out: list[list] = []
    cur: list = []
    for lon, *rest in [(p[0], p[1]) for p in coords]:
        lat = rest[0]
        if LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX:
            cur.append((lon, lat))
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [s for s in out if len(s) >= 2]


def dp(points: list, tol: float) -> list:
    """Douglas-Peucker iterativo (sin recursión: las costas traen miles de puntos)."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
        worst, wd = -1, 0.0
        for i in range(a + 1, b):
            px, py = points[i]
            d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
            if d > wd:
                worst, wd = i, d
        if wd > tol and worst > 0:
            keep[worst] = True
            stack.append((a, worst))
            stack.append((worst, b))
    return [p for p, k in zip(points, keep) if k]


def lines_of(feature: dict) -> list[list]:
    g = feature["geometry"]
    if g is None:
        return []
    if g["type"] == "LineString":
        return [g["coordinates"]]
    if g["type"] == "MultiLineString":
        return list(g["coordinates"])
    return []


def process(url: str, keep_feature) -> list[list]:
    data = fetch(url)
    out: list[list] = []
    for feature in data["features"]:
        if not keep_feature(feature):
            continue
        for line in lines_of(feature):
            for seg in clip_segments(line):
                slim = dp(seg, TOL_DEG)
                if len(slim) >= 2:
                    out.append([[round(x, QUANT), round(y, QUANT)] for x, y in slim])
    return out


def is_mexico_border(feature: dict) -> bool:
    p = {k.lower(): v for k, v in (feature.get("properties") or {}).items()}
    return "MEX" in str(p.get("adm0_a3") or "") or "Mexico" in str(p.get("adm0_name") or "")


def main() -> None:
    coast = process(COAST, lambda f: True)
    states = process(STATES, is_mexico_border)
    npts = sum(len(s) for s in coast) + sum(len(s) for s in states)
    payload = json.dumps({"c": coast, "e": states}, separators=(",", ":"))
    sys.stderr.write(
        f"costas: {len(coast)} segmentos · estados: {len(states)} · "
        f"{npts} puntos · {len(payload) / 1024:.0f} KB\n"
    )
    print("/* GEOGRAFÍA: NATURAL EARTH 1:50m · DOMINIO PÚBLICO · recorte México,")
    print(f"   DP {TOL_DEG}° + cuantización {QUANT} dec — generado por")
    print("   takab-docs/design/edge-panel/tools/gen-geografia-mexico.py */")
    print("const GEO = " + payload + ";")


if __name__ == "__main__":
    main()
