"""[T-9.53 · D-45] La cartografía del PDF viaja DENTRO del paquete instalado.

Es la trampa de `T-7.22`: el `api/Dockerfile` instala `api/*` como paquete, y un
fichero de datos que no esté en `[tool.setuptools.package-data]` no llega a la
imagen. En local todo pasa —el árbol fuente está al lado— y en la nube la §8 sale
sin contornos ni atribuciones. Por eso se prueban las DOS mitades: que
`importlib.resources` los encuentra (lo que el código usa) y que el `pyproject`
los declara (lo que el wheel empaqueta).
"""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path

from takab_api import geodatos

FICHEROS = ("estados_mex.geojson", "ntc_cdmx.geojson", "atribuciones.json")


def test_importlib_resources_encuentra_los_TRES_ficheros() -> None:
    raiz = resources.files("takab_api.geodatos")
    for nombre in FICHEROS:
        assert raiz.joinpath(nombre).is_file(), f"`{nombre}` no está en el paquete"


def test_el_pyproject_los_declara_como_package_data() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    datos = tomllib.loads(pyproject.read_text())["tool"]["setuptools"]["package-data"]
    patrones = datos.get("takab_api.geodatos", [])
    for nombre in FICHEROS:
        assert any(Path(nombre).match(p) for p in patrones), (
            f"`{nombre}` no casa con ningún patrón de package-data de `takab_api.geodatos`: "
            "el wheel saldría sin él y la imagen de la nube no lo tendría"
        )


def test_carga_devuelve_el_json_y_lo_cachea() -> None:
    estados = geodatos.carga("estados_mex.geojson")
    assert estados["type"] == "FeatureCollection"
    assert estados["features"], "los contornos de los estados llegaron vacíos"
    assert geodatos.carga("estados_mex.geojson") is estados, "sin caché: se relee en cada PDF"
    zonas = {f["properties"]["zona"] for f in geodatos.carga("ntc_cdmx.geojson")["features"]}
    assert zonas == {"lomas", "transicion", "lago"}
    atrib = geodatos.carga("atribuciones.json")
    for clave in ("estados", "ntc_cdmx"):
        assert atrib[clave]["corta"], f"la atribución `{clave}` no trae su forma corta"
