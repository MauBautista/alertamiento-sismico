"""Catálogo de tonos del gabinete (T-2.49).

La nube elige QUÉ tono suena, pero **solo por identificador de este catálogo**. Nunca
manda binarios ni rutas:

- **Binarios no**: el documento de config viaja FIRMADO por MQTT hacia un dispositivo
  que toca sirena, gas, ascensores y puertas (regla de oro 8). Un WAV arbitrario en ese
  canal convierte una superficie de configuración en una de ejecución de contenido.
- **Rutas absolutas no**: la nube no conoce el disco del gabinete. Una ruta que allá no
  existe deja al inmueble mudo sin que nadie lo note.

Los IDs se resuelven contra archivos que viajan EMPAQUETADOS con la release del edge,
así que el gabinete solo puede sonar lo que se auditó antes de desplegarlo.

**``sasmex-oficial-v1`` está reservado y AUSENTE a propósito.** El tono oficial de la
Alerta Sísmica Mexicana es propiedad de CIRES; reproducirlo sin licencia escrita es un
problema legal, y hacerlo sonar en un edificio ajeno además confunde a la población
sobre quién está alertando. Que el ID no exista en el catálogo es lo que lo hace seguro:
la ruta "ID desconocido ⇒ conservar el asset anterior" impide que se cuele por descuido.
Bloquea GATE-STORE y GATE-LEGAL.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("takab_edge.audio")

_ASSETS = Path(__file__).parent / "assets"

#: ID de catálogo → archivo empaquetado. Añadir uno exige empaquetar su WAV.
CATALOG: dict[str, str] = {
    "takab-siren-v1": "siren.wav",
    "takab-prueba-v1": "prueba.wav",
}

#: IDs que existen como concepto pero NO se pueden servir. Se distinguen de un ID
#: inventado para poder decir POR QUÉ no suena, en vez de un "desconocido" opaco.
RESERVED: dict[str, str] = {
    "sasmex-oficial-v1": (
        "el tono oficial de SASMEX es propiedad de CIRES y no se empaqueta sin "
        "licencia escrita (GATE-LEGAL)"
    ),
}


def resolve(asset_id: str) -> Path | None:
    """Ruta del tono, o ``None`` si el ID no se puede servir.

    ``None`` NUNCA significa "suena otra cosa": el llamador conserva el asset que ya
    tenía (ver ``AudioProfile.apply``). Sustituir en silencio un tono por otro es
    exactamente cómo un gabinete acaba sonando distinto de lo que su config declara.
    """
    if asset_id in RESERVED:
        log.warning("audio: el tono %r está reservado — %s", asset_id, RESERVED[asset_id])
        return None
    name = CATALOG.get(asset_id)
    if name is None:
        log.warning(
            "audio: tono %r desconocido para esta versión del edge (catálogo: %s); "
            "se conserva el tono anterior",
            asset_id,
            ", ".join(sorted(CATALOG)),
        )
        return None
    path = _ASSETS / name
    if not path.is_file():
        log.error(
            "audio: el tono %r está en el catálogo pero su archivo falta (%s)", asset_id, path
        )
        return None
    return path
