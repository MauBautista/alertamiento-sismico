"""ConfigStore — store local de umbrales/reglas/tenant + sync firmada, versionada y reversible.

T-1.12: aplica actualizaciones de config **firmadas** (verificadas por `security` — rechaza
no firmada o alterada), con **versión monótona** (anti-replay de config vieja) e **historial
para rollback** (reversible: una config mala se revierte a la anterior). El transporte de la
sync desde la nube (JWT ≤60 s por MQTT/API) es gate AWS; aquí vive la verificación + aplicación.

[T-2.34] La config aplicada + su ``high_water`` PERSISTEN en disco (patrón CatalogStore:
tmp + ``os.replace``): el corte de energía del 2026-08-03 demostró en vivo que al reiniciar
el edge arrancaba en v0 y la nube no re-publica si nada cambió — umbrales de sitio,
equipamiento y ``command_enabled`` regresaban a defaults hasta el siguiente cambio. Al
arrancar, la caché se RE-VERIFICA (firma sobre payload+versión, fail-closed a defaults) y
el ``high_water`` sobrevive: un reinicio ya no reabre la ventana de replay de configs viejas.
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from takab_edge.config.settings import EdgeSettings
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.config")


class ConfigError(Exception):
    """Actualización de config rechazada (firma inválida o versión no monótona)."""


class ConfigStore(EdgeModule):
    """Store versionado y reversible de la configuración activa del gabinete."""

    name = "config"
    depends_on = ("security",)

    def __init__(
        self,
        settings: EdgeSettings,
        security=None,
        max_history: int = 10,
        cache_path: str = "",
    ) -> None:
        super().__init__()
        self.settings = settings
        self._security = security
        self._version = 0
        # Mayor versión JAMÁS aceptada: NUNCA baja (ni con rollback) → piso anti-replay que
        # veta re-aplicar cualquier versión ya vista, incluida una revertida.
        self._high_water = 0
        # [T-2.34] Caché en disco de la config aplicada (vacío = sin persistencia,
        # conducta pre-T-2.34: unit tests y stores sueltos no tocan disco).
        self._cache_path = cache_path
        self._applied_raw: bytes | None = None
        self._applied_sig: str | None = None
        self._history: deque[tuple[int, EdgeSettings, bytes | None, str | None]] = deque(
            maxlen=max_history
        )
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
        self._history.append((self._version, self.settings, self._applied_raw, self._applied_sig))
        self.settings = new_settings
        self._version = version
        self._high_water = version
        self._applied_raw, self._applied_sig = raw, signature
        self._persist()
        log.info("config actualizada a v%d", version)
        self._notify_listeners()
        return version

    def rollback(self) -> int:
        """Revierte el CONTENIDO a la versión anterior; el `high_water` NO baja (anti-replay).

        [T-2.34] La caché en disco también se revierte: un reinicio tras el
        rollback NO resucita la config mala (y el high_water persistido la
        sigue vetando).
        """
        if not self._history:
            raise ConfigError("no hay versión previa a la que revertir")
        self._version, self.settings, self._applied_raw, self._applied_sig = self._history.pop()
        self._persist()
        log.warning(
            "config revertida a v%d (high_water sigue en v%d)", self._version, self._high_water
        )
        self._notify_listeners()
        return self._version

    # --- [T-2.34] caché en disco -------------------------------------------

    def _persist(self) -> None:
        """Escritura atómica y fail-soft: sin disco la config sigue EN MEMORIA."""
        if not self._cache_path:
            return
        doc = {
            "applied_version": self._version,
            "high_water": self._high_water,
            "payload": self._applied_raw.decode() if self._applied_raw is not None else None,
            "sig": self._applied_sig,
        }
        try:
            path = Path(self._cache_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(doc), "utf-8")
            os.replace(tmp, path)
        except OSError:
            log.warning("caché de config no persistida (sigue en memoria)", exc_info=True)

    def _load_cache(self) -> None:
        """Restaura la config aplicada al arrancar. Fail-closed: cualquier duda
        (archivo ausente/ilegible, firma inválida, contrato incompatible) deja
        los defaults de arranque — jamás una config no verificada."""
        if not self._cache_path:
            return
        try:
            doc = json.loads(Path(self._cache_path).read_text("utf-8"))
            high_water = int(doc["high_water"])
            version = int(doc["applied_version"])
            payload = doc.get("payload")
            sig = doc.get("sig")
        except FileNotFoundError:
            return
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("caché de config ilegible: arranque con defaults", exc_info=True)
            return
        # El piso anti-replay sobrevive aunque el payload no aplique.
        self._high_water = max(self._high_water, high_water)
        if payload is None:
            return
        # Fail-closed también con los TIPOS. El `except` de arriba cubre un `doc`
        # que no sea objeto, pero no un objeto BIEN formado con `payload`/`sig` no
        # textuales: `payload.encode()` levantaba AttributeError fuera del `try` y
        # el módulo se quedaba sin arrancar (aislado por `start()`, pero mudo y
        # sin caché). Mismo pecado que `_scan_pending` en backfill.
        if not isinstance(payload, str) or not isinstance(sig, (str, type(None))):
            log.warning("caché de config con payload/firma no textual: se ignora")
            return
        raw = payload.encode()
        if self._security is None or not self._security.verify_config(raw, sig or "", version):
            log.warning("caché de config NO verifica (¿alterada o clave rotada?): se ignora")
            return
        try:
            restored = EdgeSettings.model_validate_json(raw)
        except ValidationError:
            log.warning("caché de config incompatible con el contrato actual: se ignora")
            return
        self._history.append((self._version, self.settings, self._applied_raw, self._applied_sig))
        self.settings = restored
        self._version = version
        self._applied_raw, self._applied_sig = raw, sig
        log.info("config v%d restaurada del disco (high_water v%d)", version, self._high_water)
        self._notify_listeners()

    def _on_start(self) -> None:
        self._load_cache()
        log.info("config store activo (v%d)", self._version)
