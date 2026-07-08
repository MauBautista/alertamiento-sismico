"""Ciclo de vida común de los módulos del edge (blueprint §4.2).

Cada módulo es un servicio supervisado con responsabilidad única y contrato
claro. `supervisor` los arranca en orden de dependencias y los detiene en
orden inverso, aislando fallos.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

log = logging.getLogger("takab_edge")


class EdgeModule(ABC):
    """Servicio supervisado con arranque/parada idempotentes."""

    #: Nombre estable del módulo (clave en el supervisor).
    name: str = "module"
    #: Nombres de módulos que deben iniciar antes que éste.
    depends_on: tuple[str, ...] = ()
    #: ¿Módulo del camino de vida? Si un módulo `critical` no arranca, el gabinete
    #: NO puede proteger: el supervisor propaga el fallo (systemd reinicia) en vez
    #: de correr mudo. Uno NO crítico que falla se aísla y el gabinete sigue en
    #: modo degradado (blueprint §4.2: el reflejo SASMEX vive aunque el resto no
    #: arranque). Default: no crítico.
    critical: bool = False

    def __init__(self) -> None:
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._on_start()
        self._running = True
        log.info("módulo iniciado: %s", self.name)

    def stop(self) -> None:
        if not self._running:
            return
        self._on_stop()
        self._running = False
        log.info("módulo detenido: %s", self.name)

    @abstractmethod
    def _on_start(self) -> None:
        """Inicializa recursos del módulo."""

    def _on_stop(self) -> None:  # noqa: B027 — hook opcional concreto (default no-op)
        """Libera recursos. Override si hace falta (default: no-op)."""
