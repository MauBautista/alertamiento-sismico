"""Directorios temporales de REPUESTO que se borran con su dueño.

Sin ruta configurada, el anillo miniSEED y el spool de la nube caían a un
`mkdtemp` que nadie borraba. En el Pi no pasa —el aprovisionamiento fija sus
rutas en el NVMe—, pero en desarrollo y en la suite sí: el 2026-09-29 había
~2 900 directorios de cada uno en un `/tmp` tmpfs de 3,6 GB, y la suite del edge
murió con «Disk quota exceeded» en una prueba que no tenía nada que ver.

Borrarlos no pierde nada: cada arranque crea uno NUEVO (la trampa de `T-2.67.b`),
así que lo que quedaba dentro no lo iba a leer nadie.

Esto es SÓLO para el repuesto sin configurar. Una ruta configurada es durable y
no pasa por aquí jamás: la borraría al apagar el proceso.
"""

from __future__ import annotations

import shutil
import tempfile
import weakref
from pathlib import Path


def directorio_efimero(prefijo: str, dueno: object) -> Path:
    """Crea un temporal que se borra cuando `dueno` muere o al salir el intérprete."""
    ruta = Path(tempfile.mkdtemp(prefix=prefijo))
    weakref.finalize(dueno, shutil.rmtree, ruta, ignore_errors=True)
    return ruta
