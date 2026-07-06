"""ConfigStore — store local de umbrales/reglas/tenant + sync firmada.

Scaffold de T-1.2. La sincronización real desde la nube (JWT firmado, ≤60 s,
versionada y reversible) es **T-1.12**; aquí sólo se establece la interfaz y el
estado en memoria para que `supervisor` y los demás módulos arranquen en dev.
"""

from __future__ import annotations

import logging

from takab_edge.config.settings import EdgeSettings
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.config")


class ConfigStore(EdgeModule):
    """Store versionado de la configuración activa del gabinete."""

    name = "config"

    def __init__(self, settings: EdgeSettings) -> None:
        super().__init__()
        self.settings = settings
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def current(self) -> EdgeSettings:
        """Configuración activa (los módulos leen de aquí)."""
        return self.settings

    def apply_signed_update(self, settings: EdgeSettings) -> int:
        """Aplica una config firmada verificada. Sync real: T-1.12.

        Devuelve la nueva versión. La verificación de firma vive en `security`.
        """
        self.settings = settings
        self._version += 1
        log.info("config actualizada a v%d", self._version)
        return self._version

    def _on_start(self) -> None:
        log.info("config store activo (v%d)", self._version)
