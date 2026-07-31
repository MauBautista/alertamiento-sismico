"""SiteLocationCache — la ubicación del sitio con overlay «last known good» (T-2.20).

El hueco que cierra: el gabinete literalmente no sabía dónde estaba — sin lat/lon
no hay mapa de ninguna clase en el panel.

Por qué el overlay vive AQUÍ y no en `ConfigStore`: `apply_signed_update` hace
`EdgeSettings.model_validate_json` — **reemplazo total** — y la nube publica
documentos **parciales por diseño** (`commands/sync.py`): un sync que solo traiga
umbrales dejaría `site_lat` en `None`. La regla es *merge de solo-no-nulos*: un
config parcial **nunca** puede anular la ubicación aprendida.

Prioridad de fuentes (de mayor a menor):
1. **`edge.env`** (`EdgeSettings.site_lat/lon`) — fuente de verdad; sobrevive
   reinicios sin WAN gratis.
2. **Config firmada** (overlay al aplicarse, vía `add_apply_listener`).
3. **Caché en disco estrecha** (`site_location.json`) — se escribe SOLO al
   aprender una ubicación no-nula distinta (tmp + `os.replace`, 0644) y se lee
   **UNA vez al construir**, jamás desde `status()`. Deliberadamente NO es un
   caché del `ConfigStore` completo: persistir config firmada obligaría a
   persistir el `high_water` anti-replay, y cachear umbrales sí tocaría la
   actuación. La ubicación no dispara nada.

NO es un EdgeModule: no tiene ciclo de vida ni hilos; es un objeto plano que el
supervisor cablea al store y al panel. Los vecinos siguen la regla «última lista
no-vacía» y son PURAMENTE informativos (el quórum vive en la NUBE — SPOF-01).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from takab_edge.config.settings import EdgeSettings, NeighborStation
from takab_edge.contracts import utcnow

log = logging.getLogger("takab_edge.config")


class SiteLocationCache:
    """Ubicación viva del sitio: env > sync firmado (overlay) > caché de disco."""

    def __init__(self, settings: EdgeSettings) -> None:
        self._lock = threading.Lock()
        self._path = Path(settings.site_location_cache)
        self._lat = settings.site_lat
        self._lon = settings.site_lon
        self._neighbors = [n.model_dump(mode="json") for n in settings.neighbors]
        # La caché solo completa lo que el env NO trae — y se lee UNA sola vez.
        if self._lat is None or self._lon is None or not self._neighbors:
            self._read_cache_once()

    def _read_cache_once(self) -> None:
        try:
            data = json.loads(self._path.read_text("utf-8"))
            lat, lon = data.get("site_lat"), data.get("site_lon")
            if (
                self._lat is None
                and self._lon is None
                and isinstance(lat, (int, float))
                and isinstance(lon, (int, float))
                and -90.0 <= lat <= 90.0
                and -180.0 <= lon <= 180.0
            ):
                self._lat, self._lon = float(lat), float(lon)
            if not self._neighbors and isinstance(data.get("neighbors"), list):
                self._neighbors = [
                    NeighborStation.model_validate(n).model_dump(mode="json")
                    for n in data["neighbors"]
                ]
        except FileNotFoundError:
            return  # primer arranque: aún no se aprendió nada
        except Exception:  # noqa: BLE001 — caché corrupta = caché ausente, jamás un crash
            log.warning("caché de ubicación ilegible (%s); se ignora", self._path, exc_info=True)

    def on_config_applied(self, cfg: EdgeSettings) -> None:
        """Listener del ConfigStore (T-1.71): merge de SOLO-no-nulos.

        La lat/lon solo cuentan como PAR completo (una coordenada suelta no ubica
        nada). Al aprender un par no-nulo DISTINTO se escribe la caché — escritura
        por evento, no por intervalo. Un listener no debe lanzar: todo es
        best-effort y el fallo se queda en un warning.
        """
        try:
            with self._lock:
                learned = False
                if cfg.site_lat is not None and cfg.site_lon is not None:
                    pair = (float(cfg.site_lat), float(cfg.site_lon))
                    if pair != (self._lat, self._lon):
                        self._lat, self._lon = pair
                        learned = True
                if cfg.neighbors:  # «última lista no-vacía»: parcial sin vecinos no borra
                    fresh = [n.model_dump(mode="json") for n in cfg.neighbors]
                    if fresh != self._neighbors:
                        self._neighbors = fresh
                        learned = True
                if learned and self._lat is not None:
                    self._write_cache()
        except Exception:  # noqa: BLE001 — contrato de add_apply_listener: jamás lanzar
            log.warning("overlay de ubicación falló (aislado)", exc_info=True)

    def _write_cache(self) -> None:
        """tmp + os.replace (atómico), 0644. Best-effort: en dev la ruta no existe."""
        try:
            payload = json.dumps(
                {
                    "site_lat": self._lat,
                    "site_lon": self._lon,
                    "neighbors": self._neighbors,
                    "learned_at": utcnow().isoformat(),
                },
                ensure_ascii=False,
            )
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(payload, "utf-8")
            os.chmod(tmp, 0o644)  # legible: no es secreto, y lo lee el panel de a pie
            os.replace(tmp, self._path)
            log.info("ubicación aprendida y cacheada en %s", self._path)
        except OSError:
            log.warning("no se pudo escribir la caché de ubicación (%s)", self._path)

    def current(self) -> dict:
        """Ubicación viva para `status()` — JAMÁS lee disco."""
        with self._lock:
            return {
                "site_lat": self._lat,
                "site_lon": self._lon,
                "neighbors": list(self._neighbors),
            }


__all__ = ["SiteLocationCache"]
