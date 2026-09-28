"""[F3·r2 · D-43 §4] La CABEZA de la cadena es UNA: ``created_at DESC, dictamen_id DESC``.

Dos filas con el mismo ``created_at`` (el ``now()`` de dos transacciones que empiezan
a la vez) sin desempate dejan que cada lector elija una cabeza distinta: la app
diría HABITABLE y el reingreso PENDIENTE del mismo incidente. Esta guarda recorre
TODO ``takab_api`` y exige el desempate en cada ``ORDER BY`` sobre ``dictamens``.
"""

from __future__ import annotations

import re
from pathlib import Path

import takab_api

_RAIZ = Path(takab_api.__file__).parent
_DE_DICTAMENS = re.compile(r"FROM\s+dictamens\b")


def _ordenes_sobre_dictamens() -> list[tuple[str, int, str]]:
    hallados = []
    for fichero in sorted(_RAIZ.rglob("*.py")):
        lineas = fichero.read_text(encoding="utf-8").splitlines()
        for i, linea in enumerate(lineas):
            if not _DE_DICTAMENS.search(linea):
                continue
            for j in range(i, min(i + 12, len(lineas))):
                if "ORDER BY" in lineas[j]:
                    if "created_at" in lineas[j]:
                        hallados.append((fichero.name, j + 1, lineas[j].strip()))
                    break
    return hallados


def test_la_guarda_encuentra_las_consultas_de_cabeza() -> None:
    """Sin esto, una guarda que no encuentra nada pasaría siempre."""
    assert len(_ordenes_sobre_dictamens()) >= 6


def test_toda_cabeza_desempata_por_dictamen_id() -> None:
    sin_desempate = [h for h in _ordenes_sobre_dictamens() if "dictamen_id DESC" not in h[2]]
    assert sin_desempate == []
