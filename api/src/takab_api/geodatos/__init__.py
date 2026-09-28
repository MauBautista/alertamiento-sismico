"""[T-9.53 · D-45] Cartografía base embebida en el paquete: sin tiles, sin red.

La lee el PDF del dictamen (§8) para dibujar contornos estatales y la zonificación
geotécnica de la CDMX bajo la superficie estimada. Viaja DENTRO del paquete
(`pyproject.toml`, `package-data`) porque un documento de evidencia no puede
depender de que un servidor de mapas siga en pie. Las atribuciones salen de
`atribuciones.json` —la misma fuente que la consola y la app— y nunca se escriben
a mano.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources


@cache
def carga(nombre: str) -> dict:
    """El JSON ``nombre`` del paquete, leído UNA vez por proceso.

    ⚠️ Lo devuelto es compartido: quien lo use no lo muta.
    """
    return json.loads(resources.files(__name__).joinpath(nombre).read_text(encoding="utf-8"))
