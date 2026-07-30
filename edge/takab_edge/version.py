"""Qué código corre este gabinete — declarado por el gabinete, no anotado a mano.

`deploy/edge/deploy.sh` escribe el SHA corto del commit desplegado en un archivo
``FW_VERSION`` junto al código; aquí se lee y el heartbeat lo publica, y la nube lo
persiste en ``gateways.fw_version``.

Por qué no basta con anotarlo: ese campo se llenó a mano una vez (2026-07-30) y a
partir del siguiente despliegue habría empezado a mentir, porque nadie lo actualiza.
Es el mismo agujero que `/api/health` cerró para la nube con ``TAKAB_API_BUILD_SHA``.
Un dato con pinta de correcto es peor que uno vacío (regla de oro 7).

Por qué un archivo y no una variable de ``edge.env``: ese archivo es identidad y
credenciales, y lo instala SOLO `provision_gateway.sh` (regla de oro 6). La versión
la pone quien despliega código, que es otro proceso y otro momento.

Nada de esto puede tumbar el arranque: cualquier fallo de lectura es «no sé».
"""

from __future__ import annotations

import logging
import pathlib

log = logging.getLogger(__name__)

#: Nombre del archivo que escribe el deploy, junto al paquete.
FW_VERSION_FILE = "FW_VERSION"

#: Una versión es un SHA corto (7-40) o una etiqueta corta. Más largo que esto es un
#: archivo corrupto, y prefiero «no sé» a publicar basura en la ficha de la flota.
_MAX_LEN = 64


def _default_root() -> pathlib.Path:
    """Raíz del despliegue: el directorio que contiene al paquete `takab_edge`."""
    return pathlib.Path(__file__).resolve().parent.parent


def fw_version(root: pathlib.Path | None = None) -> str | None:
    """SHA del código desplegado, o ``None`` si no se puede saber.

    ``None`` significa exactamente «este gabinete no sabe qué versión corre» — por
    ejemplo en desarrollo local, donde nadie ejecutó el script de despliegue.
    """
    ruta = (root or _default_root()) / FW_VERSION_FILE
    try:
        crudo = ruta.read_text()
    except (OSError, UnicodeDecodeError):
        # Ausente en local (lo normal) o ilegible (raro). Ni un caso ni el otro
        # justifica ruido en cada arranque, y ninguno puede propagarse.
        return None
    version = crudo.strip()
    if not version or len(version) > _MAX_LEN:
        log.warning(
            "FW_VERSION ilegible o absurdo (%d caracteres); se reporta sin dato", len(version)
        )
        return None
    return version
