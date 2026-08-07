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
- **T-2.66 · la instantánea declara su EDAD y su PROCEDENCIA** (`provenance()`):
  hasta aquí, una captura de hace tres semanas se veía IDÉNTICA a una recién
  firmada — la regla de oro 7 sin cumplir en el gabinete. Se rotula, no se
  borra: a diferencia de un canal de señal fuera de plazo (T-2.58), el catálogo
  es explícitamente una instantánea FECHADA cuyos datos no se pudren (magnitud,
  coordenadas y profundidad de un sismo del 31-jul siguen siendo verdad hoy), y
  además ancla el mapa (`references`) y la comparativa T-2.27. Lo que la edad
  vuelve falso son solo las afirmaciones de ACTUALIDAD, y eso lo arregla un
  rótulo — apagarlo apagaría dos vistas sanas.

NO es un EdgeModule: objeto plano sin hilos, como `SiteLocationCache`. Nada de
esto toca el camino de actuación; el catálogo es información, no disparo. Un
catálogo viejo NO degrada ninguna capacidad de protección: degrada una
AFIRMACIÓN de pantalla.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from takab_edge.contracts import utcnow

log = logging.getLogger("takab_edge.catalog")

#: Clave (dentro del archivo) que acarrea el high-water del feed firmado.
_FEED_VERSION_KEY = "feed_version"

#: [T-2.66] Umbral de vejez, medido sobre `captured_at`. VIAJA en el payload
#: (mismo patrón que `_SIGNAL_STALE_S` del panel): el número se ve en pantalla,
#: no se esconde en una constante de JS. 48 h porque la instantánea sale del
#: feed de "últimos sismos" del SSN, que rota en horas-días — más allá de eso es
#: demostrablemente incompleta. Regla para moverlo: 2× la cadencia del job que
#: lo refresque; mientras ese job no exista (ver T-2.66.b), generoso y con el
#: rótulo permanente.
CATALOG_STALE_AFTER_S = 48 * 3600.0

#: De dónde salió la instantánea instalada. Cambia la reacción del operador:
#: `provisioned_file` NO se actualiza solo (y `_load_once` solo lo relee al
#: REINICIAR el servicio); `signed_feed` llegó por la nube y trae versión.
ORIGIN_SIGNED_FEED = "signed_feed"
ORIGIN_PROVISIONED_FILE = "provisioned_file"
ORIGIN_ABSENT = "absent"


def _absent_provenance() -> dict:
    return {
        "version": 0,
        "origin": ORIGIN_ABSENT,
        "installed_at": None,
        "captured_at": None,
        "captured_age_s": None,
        "installed_age_s": None,
        "stale_after_s": CATALOG_STALE_AFTER_S,
    }


DEGRADED: dict = {
    "available": False,
    "source": None,
    "captured_at": None,
    "note": None,
    "events": [],
    "references": [],
    # Contrato ADITIVO: el caso degradado también describe su procedencia, para
    # que el panel jamás reciba `undefined` donde espera una edad.
    "provenance": _absent_provenance(),
}


def _parse_ts(value: object) -> datetime | None:
    """Parseo DEFENSIVO de un timestamp del catálogo.

    `captured_at` es un string LIBRE: la nube solo valida que sea truthy
    (`push_catalog`) y en el propio repo conviven formatos con y sin zona.
    Ilegible ⇒ ``None`` (el panel rotula EDAD DESCONOCIDA), jamás 0 y jamás una
    excepción. Sin zona ⇒ se lee como UTC: es la lectura CONSERVADORA — en
    México eso hace la instantánea 6 h más VIEJA, nunca más joven.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _age_s(now: datetime, then: datetime | None) -> float | None:
    """Edad en segundos, nunca negativa: un reloj del Pi atrasado (o un
    `capturado` en el futuro) no puede rejuvenecer la instantánea."""
    if then is None:
        return None
    return max(0.0, (now - then).total_seconds())


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

    def __init__(
        self,
        path: str,
        security: object | None = None,
        clock: object | None = None,
    ) -> None:
        self._path = Path(path) if path else None
        self._security = security
        # [T-2.66] Reloj INYECTABLE (mismo patrón que `SecurityManager`,
        # `BackfillManager` y `RuleEngine`): sin esta costura, un test de
        # "catálogo envejecido" envejecería con el calendario.
        self._clock = clock or utcnow
        self._lock = threading.Lock()
        self._version = 0
        self._current = dict(DEGRADED)
        self._origin = ORIGIN_ABSENT
        self._installed_at: datetime | None = None
        self._load_once()

    @property
    def version(self) -> int:
        return self._version

    def _load_once(self) -> None:
        """Lee el archivo UNA vez al construir. Ausente/corrupto ⇒ degradado.

        Único punto de disco del módulo (`current()`/`provenance()` corren a la
        cadencia del kiosco y no pueden tocarlo), así que también es el sitio
        donde se toma el `mtime`: la hora en que el archivo llegó al gabinete.
        Corolario para el runbook: reemplazar el archivo a mano con el servicio
        corriendo NO se ve hasta reiniciar `takab-edge` — ni el contenido ni la
        procedencia.
        """
        if self._path is None:
            return
        try:
            raw = json.loads(self._path.read_text("utf-8"))
            self._current = normalize_catalog(raw)
            feed_version = raw.get(_FEED_VERSION_KEY, 0)
            self._version = feed_version if isinstance(feed_version, int) else 0
            # `feed_version` dentro del archivo es la huella INEQUÍVOCA del feed
            # firmado: `provision_gateway.sh --catalog` (cp/tee) jamás la escribe.
            self._origin = ORIGIN_SIGNED_FEED if self._version > 0 else ORIGIN_PROVISIONED_FILE
            self._installed_at = datetime.fromtimestamp(self._path.stat().st_mtime, tz=UTC)
        except FileNotFoundError:
            log.info("catálogo SSN no instalado (%s); el panel lo declara", self._path)
        except Exception:  # noqa: BLE001 — catálogo ilegible = ausente, jamás un crash
            log.warning("catálogo SSN ilegible (%s); se degrada", self._path, exc_info=True)

    def current(self) -> dict:
        """Instantánea normalizada (§5.1). Lectura pura, jamás toca disco."""
        with self._lock:
            return self._current

    def provenance(self) -> dict:
        """[T-2.66] Edad y procedencia de la instantánea que se está sirviendo.

        Lectura pura (ni disco ni red: corre a la cadencia del kiosco). La edad
        se calcula AQUÍ, en Python, y viaja resuelta en el payload junto al
        umbral — el panel solo compara `captured_age_s > stale_after_s`. No es
        un capricho: el navegador del kiosco puede tener la hora corrida, y el
        arnés de test del panel expone el `Date` real, así que una edad
        calculada en JS daría un test que caduca con el calendario.

        Dos hechos DISTINTOS y ambos útiles: `captured_at` responde "de cuándo
        son estos sismos" (y es el que gobierna el umbral) e `installed_at`
        responde "cuándo llegó al gabinete". En el gabinete real difieren casi
        dos horas; con un archivo provisionado, pueden diferir meses.
        """
        with self._lock:
            version = self._version
            origin = self._origin
            installed_at = self._installed_at
            captured_at = self._current.get("captured_at")
        now = self._clock()
        return {
            "version": version,
            "origin": origin,
            "installed_at": installed_at.isoformat() if installed_at else None,
            "captured_at": captured_at,
            "captured_age_s": _age_s(now, _parse_ts(captured_at)),
            "installed_age_s": _age_s(now, installed_at),
            "stale_after_s": CATALOG_STALE_AFTER_S,
        }

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
            # [T-2.66] `installed_at` sale del RELOJ, no del mtime: `_write_atomic`
            # es best-effort (puede caer por OSError) y el swap en memoria ocurre
            # igual — un mtime que no se escribió mentiría sobre esta instalación.
            self._origin = ORIGIN_SIGNED_FEED
            self._installed_at = self._clock()
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


__all__ = [
    "CATALOG_STALE_AFTER_S",
    "DEGRADED",
    "ORIGIN_ABSENT",
    "ORIGIN_PROVISIONED_FILE",
    "ORIGIN_SIGNED_FEED",
    "CatalogError",
    "CatalogStore",
    "normalize_catalog",
]
