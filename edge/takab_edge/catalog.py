"""CatalogStore — instantánea SSN del panel, con feed FIRMADO nube→edge (T-2.24).

Hasta T-2.23 el catálogo era un archivo provisionado a mano
(`provision_gateway.sh --catalog`). Este módulo lo mantiene — el archivo sigue
siendo la verdad en disco y el formato del entregable de diseño sigue siendo el
formato — y añade la actualización remota firmada:

- **Mismo mecanismo que la config firmada** (T-1.12/T-1.23): HMAC por gabinete
  con dominio propio ``b"catalog"``, versión MONÓTONA anti-replay, fail-closed
  sin verificador. El sobre llega por ``takab/catalog/<thing>`` vía dispatch.
- **El high-water SOBREVIVE reinicios sin costo**: viaja dentro del propio
  archivo (`feed_version`) — a diferencia de la config, aquí persistir no abre
  ninguna ventana de replay ni toca la actuación (la ubicación de T-2.20 hizo
  la misma cuenta). Un archivo instalado a mano (sin `feed_version`) es v0.
- **Escritura atómica** (tmp + ``os.replace``, 0644) y hot-swap en memoria: el
  contrato de ``GET /api/catalog`` NO cambia — el panel solo ve la instantánea
  más fresca con su `captured_at` visible.

NO es un EdgeModule: objeto plano sin hilos, como `SiteLocationCache`. Nada de
esto toca el camino de actuación; el catálogo es información, no disparo.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger("takab_edge.catalog")

#: Clave (dentro del archivo) que acarrea el high-water del feed firmado.
_FEED_VERSION_KEY = "feed_version"

DEGRADED: dict = {
    "available": False,
    "source": None,
    "captured_at": None,
    "note": None,
    "events": [],
    "references": [],
}


class CatalogError(Exception):
    """Actualización de catálogo rechazada (firma/versión/payload inválidos)."""


def normalize_catalog(raw: dict) -> dict:
    """Normaliza el formato del entregable de diseño al contrato §5.1.

    Lanza (KeyError/TypeError/ValueError) si la forma no da: el que llama
    decide si eso degrada (carga de archivo) o rechaza (feed firmado).
    """
    events = [
        {
            "m": float(e["m"]),
            "at": f"{e.get('fecha', '')} {e.get('hora', '')}".strip(),
            "lat": float(e["lat"]),
            "lon": float(e["lon"]),
            "depth_km": float(e["prof"]) if e.get("prof") is not None else None,
            "place": str(e.get("loc", "")),
        }
        for e in raw.get("eventos", [])
    ]
    references = [
        {"n": str(r["n"]), "lat": float(r["lat"]), "lon": float(r["lon"])}
        for r in raw.get("referencias", [])
    ]
    return {
        "available": True,
        "source": raw.get("fuente"),
        "captured_at": raw.get("capturado"),
        "note": raw.get("replicas_nota"),
        "events": events,
        "references": references,
    }


class CatalogStore:
    """Instantánea viva del catálogo: archivo en disco + feed firmado opcional."""

    def __init__(self, path: str, security: object | None = None) -> None:
        self._path = Path(path) if path else None
        self._security = security
        self._lock = threading.Lock()
        self._version = 0
        self._current = dict(DEGRADED)
        self._load_once()

    @property
    def version(self) -> int:
        return self._version

    def _load_once(self) -> None:
        """Lee el archivo UNA vez al construir. Ausente/corrupto ⇒ degradado."""
        if self._path is None:
            return
        try:
            raw = json.loads(self._path.read_text("utf-8"))
            self._current = normalize_catalog(raw)
            feed_version = raw.get(_FEED_VERSION_KEY, 0)
            self._version = feed_version if isinstance(feed_version, int) else 0
        except FileNotFoundError:
            log.info("catálogo SSN no instalado (%s); el panel lo declara", self._path)
        except Exception:  # noqa: BLE001 — catálogo ilegible = ausente, jamás un crash
            log.warning("catálogo SSN ilegible (%s); se degrada", self._path, exc_info=True)

    def current(self) -> dict:
        """Instantánea normalizada (§5.1). Lectura pura, jamás toca disco."""
        with self._lock:
            return self._current

    def apply_signed_update(self, raw: bytes, signature: str, version: int) -> int:
        """Verifica firma+frescura, persiste ATÓMICO y hace el hot-swap.

        Fail-closed en todo: sin verificador se RECHAZA; la firma cubre
        (payload, version); la versión debe superar el high-water (que
        sobrevive reinicios dentro del archivo). Lanza `CatalogError` si algo
        no verifica — y en ese caso NO se escribe ni un byte.
        """
        if self._security is None:
            raise CatalogError("sin verificador de firma: se rechaza (fail-closed)")
        if not self._security.verify_catalog(raw, signature, version):
            raise CatalogError("firma de catálogo inválida (rechazada)")
        with self._lock:
            if version <= self._version:
                raise CatalogError(f"versión no fresca: {version} <= {self._version} (replay)")
            try:
                payload = json.loads(raw)
                normalized = normalize_catalog(payload)
            except Exception as exc:  # noqa: BLE001 — payload firmado pero malformado
                raise CatalogError(f"payload de catálogo inválido: {exc}") from exc
            self._write_atomic(payload, version)
            self._current = normalized
            self._version = version
        log.info("catálogo SSN actualizado por feed firmado: v%d", version)
        return version

    def _write_atomic(self, payload: dict, version: int) -> None:
        """tmp + os.replace, 0644 (lo lee el panel de a pie). Best-effort en dev."""
        if self._path is None:
            return
        try:
            on_disk = dict(payload)
            on_disk[_FEED_VERSION_KEY] = version
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(on_disk, ensure_ascii=False), "utf-8")
            os.chmod(tmp, 0o644)
            os.replace(tmp, self._path)
        except OSError:
            # La ruta puede no existir en dev: el swap en memoria vale igual,
            # solo se pierde la persistencia (y el high-water) ante un reinicio.
            log.warning("no se pudo persistir el catálogo (%s)", self._path)


__all__ = ["CatalogError", "CatalogStore", "DEGRADED", "normalize_catalog"]
