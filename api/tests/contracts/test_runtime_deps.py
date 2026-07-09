"""Todo import de tercero en runtime debe estar respaldado por una dependencia declarada.

Motivo (T-1.37): ``notify/providers.py`` importaba ``httpx`` a nivel de módulo, pero
``httpx`` vivía SOLO en el extra ``dev``. La suite pasaba —el entorno de test lo instala—
y el worker ``notify`` moría con ``ModuleNotFoundError`` al arrancar en la imagen de
producción. Nadie lo vio hasta ejecutar la imagen de verdad.

Este contract-test cierra el hueco sin necesidad de un entorno limpio: enumera los
módulos de tercer nivel que importa ``src/takab_api`` y exige que cada uno esté en la
lista blanca de abajo, que se deriva a mano de ``[project] dependencies``. Añadir un
import nuevo obliga a decidir —y declarar— de qué paquete viene.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[2]
_SRC = _API_ROOT / "src" / "takab_api"

# módulo importable → distribución que lo provee.
# Las transitivas se declaran EXPLÍCITAMENTE: `starlette` y `botocore` no están en
# pyproject, llegan por fastapi y boto3. Anotarlas aquí documenta esa apuesta en vez
# de dejarla implícita.
_MODULE_TO_DIST: dict[str, str] = {
    "anyio": "fastapi",  # transitiva de starlette (to_thread en routers/commands)
    "boto3": "boto3",
    "botocore": "boto3",  # transitiva de boto3
    "fastapi": "fastapi",
    "fpdf": "fpdf2",
    "httpx": "httpx",
    "jsonschema": "jsonschema",
    "jwt": "pyjwt",
    "psycopg": "psycopg",
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings",
    "sqlalchemy": "sqlalchemy",
    "starlette": "fastapi",  # transitiva de fastapi
    "alembic": "alembic",
    "uvicorn": "uvicorn",
}


def _runtime_imports() -> set[str]:
    """Módulos de primer nivel, ajenos a la stdlib, que importa el código de runtime."""
    roots: set[str] = set()
    for path in _SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return {r for r in roots if r not in sys.stdlib_module_names and r != "takab_api"}


def _declared_runtime_dists() -> set[str]:
    """Distribuciones de ``[project] dependencies``, normalizadas (sin extras ni pins)."""
    data = tomllib.loads((_API_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dists: set[str] = set()
    for spec in data["project"]["dependencies"]:
        name = spec.split("[")[0].split(">")[0].split("=")[0].split("<")[0].split(";")[0]
        dists.add(name.strip().lower().replace("_", "-"))
    return dists


def test_every_runtime_import_maps_to_a_known_distribution() -> None:
    """Un import nuevo sin entrada en el mapa detiene el CI, no el arranque en prod."""
    unknown = _runtime_imports() - set(_MODULE_TO_DIST)
    assert not unknown, (
        f"imports de tercero sin mapear a distribución: {sorted(unknown)}. "
        "Añádelos a _MODULE_TO_DIST y a [project] dependencies si hacen falta en runtime."
    )


def test_runtime_imports_are_declared_as_runtime_dependencies() -> None:
    """El caso `httpx`: importado por el worker `notify`, declarado solo en el extra dev."""
    declared = _declared_runtime_dists()
    missing = {
        module: _MODULE_TO_DIST[module]
        for module in _runtime_imports()
        if _MODULE_TO_DIST[module].lower() not in declared
    }
    assert not missing, (
        "el código de runtime importa módulos cuya distribución NO está en "
        f"[project] dependencies: {missing}. La suite pasaría (el entorno de test las "
        "instala) y el worker moriría en producción."
    )


def test_uvicorn_is_a_runtime_dependency() -> None:
    """La imagen sirve la API con uvicorn: sin él, `docker compose up` no arranca."""
    assert "uvicorn" in _declared_runtime_dists()
