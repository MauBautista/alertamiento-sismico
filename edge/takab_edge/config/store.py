"""ConfigStore — store local de umbrales/reglas/tenant + sync firmada, versionada y reversible.

T-1.12: aplica actualizaciones de config **firmadas** (verificadas por `security` — rechaza
no firmada o alterada), con **versión monótona** (anti-replay de config vieja) e **historial
para rollback** (reversible: una config mala se revierte a la anterior). El transporte de la
sync desde la nube (JWT ≤60 s por MQTT/API) es gate AWS; aquí vive la verificación + aplicación.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable

from takab_edge.config.settings import EdgeSettings
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.config")


class ConfigError(Exception):
    """Actualización de config rechazada (firma inválida o versión no monótona)."""


class ConfigStore(EdgeModule):
    """Store versionado y reversible de la configuración activa del gabinete."""

    name = "config"
    depends_on = ("security",)

    def __init__(self, settings: EdgeSettings, security=None, max_history: int = 10) -> None:
        super().__init__()
        self.settings = settings
        self._security = security
        self._version = 0
        # Mayor versión JAMÁS aceptada: NUNCA baja (ni con rollback) → piso anti-replay que
        # veta re-aplicar cualquier versión ya vista, incluida una revertida.
        self._high_water = 0
        self._history: deque[tuple[int, EdgeSettings]] = deque(maxlen=max_history)
        self._apply_listeners: list[Callable[[EdgeSettings], None]] = []

    @property
    def version(self) -> int:
        return self._version

    def current(self) -> EdgeSettings:
        """Configuración activa (los módulos leen de aquí)."""
        return self.settings

    def add_apply_listener(self, listener: Callable[[EdgeSettings], None]) -> None:
        """Registra un observador de la config activa (T-1.71).

        Se invoca con la config vigente tras aplicar una actualización firmada y
        tras un rollback, para que módulos vivos (p.ej. el motor de reglas y sus
        umbrales) adopten la config nueva sin reconstruirse. Un listener NO debe
        lanzar: la config ya viene validada por `apply_signed_update`.
        """
        self._apply_listeners.append(listener)

    def _notify_listeners(self) -> None:
        for listener in self._apply_listeners:
            listener(self.settings)

    def apply_signed_update(self, raw: bytes, signature: str, version: int) -> int:
        """Verifica la firma (que cubre la versión) + frescura y aplica; guarda para rollback.

        Fail-closed: sin verificador (`security`) se RECHAZA. La firma autentica
        `(payload, version)`, y `version` debe superar el `high_water` (ninguna versión ya
        vista se re-aplica). Lanza `ConfigError` si no verifica.
        """
        if self._security is None:
            raise ConfigError("sin verificador de firma: se rechaza (fail-closed)")
        if not self._security.verify_config(raw, signature, version):
            raise ConfigError("firma de config inválida (rechazada)")
        if version <= self._high_water:
            raise ConfigError(f"versión no fresca: {version} <= {self._high_water} (replay)")
        new_settings = EdgeSettings.model_validate_json(raw)
        self._history.append((self._version, self.settings))
        self.settings = new_settings
        self._version = version
        self._high_water = version
        log.info("config actualizada a v%d", version)
        self._notify_listeners()
        return version

    def rollback(self) -> int:
        """Revierte el CONTENIDO a la versión anterior; el `high_water` NO baja (anti-replay)."""
        if not self._history:
            raise ConfigError("no hay versión previa a la que revertir")
        self._version, self.settings = self._history.pop()
        log.warning(
            "config revertida a v%d (high_water sigue en v%d)", self._version, self._high_water
        )
        self._notify_listeners()
        return self._version

    def _on_start(self) -> None:
        log.info("config store activo (v%d)", self._version)
