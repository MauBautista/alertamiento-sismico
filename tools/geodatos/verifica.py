#!/usr/bin/env python3
"""Compara ``shared/geodatos/MANIFEST.json`` con la cartografía empaquetada (T-9.54 · D-45).

Solo stdlib: corre en CI sin instalar nada. Comprueba:

1. Cada salida de cada capa existe y coincide con su sha256 y su tamaño.
2. Ningún ``.geojson`` de ``web/public/geodatos`` ni de ``api/src/takab_api/geodatos`` falta
   en el manifiesto: una capa sin fuente declarada no tiene licencia que la ampare.
3. Cada capa nombra una atribución que existe en ``shared/geodatos/atribuciones.json``, y
   ésta trae ``corta``, ``larga``, ``licencia`` y ``url``. El relieve, que no se empaqueta
   (se pide a AWS), también tiene la suya.
4. La copia de las atribuciones que lleva la API es idéntica byte a byte a la de ``shared``.
5. Los topes de tamaño: la cartografía de la API ≤ 2 MB y cada capa de la web ≤ 6 MB.

Sale 0 si todo cuadra; 1 con un mensaje por discrepancia si no.

Uso:  python3 tools/geodatos/verifica.py [RAIZ_DEL_REPO]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

MANIFIESTO = Path("shared") / "geodatos" / "MANIFEST.json"
ATRIBUCIONES = Path("shared") / "geodatos" / "atribuciones.json"
COPIA_API = Path("api") / "src" / "takab_api" / "geodatos" / "atribuciones.json"
ZONAS = {
    Path("web") / "public" / "geodatos": 6_000_000,  # tope por capa
    Path("api") / "src" / "takab_api" / "geodatos": None,  # tope conjunto, abajo
}
TOPE_API_TOTAL = 2_000_000
CAMPOS_ATRIBUCION = ("corta", "larga", "licencia", "url")
#: Capas que no se empaquetan pero se pintan: también necesitan su atribución.
SIN_FICHERO = ("relieve",)


def sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def verifica(raiz: Path) -> list[str]:
    errores: list[str] = []
    manifiesto = json.loads((raiz / MANIFIESTO).read_text())
    atribuciones = json.loads((raiz / ATRIBUCIONES).read_text())

    declaradas: set[str] = set()
    for capa, e in manifiesto["capas"].items():
        for ruta, huella in e["salidas"].items():
            declaradas.add(ruta)
            p = raiz / ruta
            if not p.is_file():
                errores.append(f"{capa}: falta {ruta}")
                continue
            if sha256(p) != huella["sha256"]:
                errores.append(f"{capa}: {ruta} no coincide con su sha256 del manifiesto")
            if p.stat().st_size != huella["bytes"]:
                errores.append(f"{capa}: {ruta} no pesa lo que dice el manifiesto")
        if e.get("atribucion") not in atribuciones:
            errores.append(f"{capa}: su atribución {e.get('atribucion')!r} no existe")
        if not e.get("fuente", {}).get("sha256"):
            errores.append(f"{capa}: la fuente no declara su sha256")

    for capa in (*SIN_FICHERO, *(e["atribucion"] for e in manifiesto["capas"].values())):
        a = atribuciones.get(capa)
        if not isinstance(a, dict):
            errores.append(f"atribución {capa!r} ausente")
            continue
        errores += [f"atribución {capa!r} sin {c}" for c in CAMPOS_ATRIBUCION if not a.get(c)]

    total_api = 0
    for zona, tope in ZONAS.items():
        base = raiz / zona
        for p in sorted(base.glob("*.geojson")) if base.is_dir() else []:
            rel = p.relative_to(raiz).as_posix()
            if rel not in declaradas:
                errores.append(f"{rel} no está en el manifiesto")
            if tope is not None and p.stat().st_size > tope:
                errores.append(f"{rel} pesa {p.stat().st_size} B (> {tope})")
            if tope is None:
                total_api += p.stat().st_size
    if total_api > TOPE_API_TOTAL:
        errores.append(f"la cartografía de la API pesa {total_api} B (> {TOPE_API_TOTAL})")

    if (raiz / COPIA_API).read_bytes() != (raiz / ATRIBUCIONES).read_bytes():
        errores.append(f"{COPIA_API} no es idéntica a {ATRIBUCIONES}")
    return errores


def main(argv: list[str]) -> int:
    raiz = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[2]
    errores = verifica(raiz)
    for e in errores:
        print(f"✗ {e}")
    if not errores:
        print("✓ cartografía, manifiesto y atribuciones cuadran")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
