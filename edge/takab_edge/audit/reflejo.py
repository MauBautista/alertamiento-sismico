"""Acta del REFLEJO: la cifra más citada del producto, como artefacto (T-5.22).

EL DEFECTO QUE CIERRA
---------------------
`contacto SASMEX → relé` está medido dos veces con hardware real —**6.65 ms** y
**4.16 ms**— y esa cifra es la más citada del producto. Su evidencia, hasta hoy,
eran **ocho documentos con el número escrito a mano**: ni journal, ni acta, ni
captura del estado del gabinete, ni fixture. Un cliente que pidiera la evidencia
recibía un archivo de texto. Y en el gabinete vivo el campo de latencia está en
`null` mientras no haya pasado nada: la medición no está viva, es histórica.

Esto es el acta. Cada flanco del WR-1 deja **una línea fechada** con la latencia
que el dueño de los pines midió y con el estado de los cinco canales en ese
instante — o sea, lo que hace verificable el número: no «tardó 4 ms», sino «tardó
4 ms **y estos relés quedaron así**».

POR QUÉ NO VIVE DENTRO DEL PROCESO DE LOS PINES
------------------------------------------------
`takab_edge/audit/__init__.py` ya lo dejó escrito: el reflejo vive ENTERO dentro
del dueño de los pines y **no cruza la costura**, y registrarlo desde allí
exigiría meterle dependencias a un proceso que es mínimo y auditable a propósito
(regla de oro 4). Así que el acta la escribe **el supervisor**, que ve la
latencia por la instantánea de la costura y vive del otro lado. El reflejo no se
entera de que esto existe, que es la única forma aceptable de auditarlo.

Y por eso el acta es **advisory**: si el disco está lleno o el fichero no se
puede abrir, se cuenta el fallo y se sigue. Un acta que pudiera tumbar el camino
de vida sería peor que no tener acta.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("takab_edge.audit.reflejo")

#: Cuántas actas se conservan en el fichero vivo. El reflejo ocurre una vez por
#: alerta —no por intervalo—, así que doscientas líneas son años de operación de
#: un gabinete y aun así el fichero cabe en un vistazo.
MAX_ACTAS = 200


@dataclass(frozen=True)
class ActaDeReflejo:
    """Una medición, con lo que hace falta para poder citarla."""

    medido_en: str
    latencia_s: float
    gateway_id: str
    fw_version: str
    #: ¿Fue un pulso de PRUEBA del WR-1? Un acta de prueba no acredita nada del
    #: camino real, y mezclarlas sería exactamente el defecto que esto corrige.
    es_prueba: bool
    #: Estado de los canales en el instante medido. Es lo que convierte el número
    #: en evidencia: no «tardó 4 ms», sino «tardó 4 ms y estos relés quedaron así».
    canales: dict[str, bool]

    def to_json(self) -> dict[str, Any]:
        return {
            "medido_en": self.medido_en,
            "latencia_s": self.latencia_s,
            "latencia_ms": round(self.latencia_s * 1000, 3),
            "gateway_id": self.gateway_id,
            "fw_version": self.fw_version,
            "es_prueba": self.es_prueba,
            "canales": dict(self.canales),
        }


class ActaDeReflejoStore:
    """Fichero append-only de actas. **Nunca lanza** desde `registrar`."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self.fallos = 0

    @property
    def path(self) -> Path:
        return self._path

    def registrar(self, acta: ActaDeReflejo) -> bool:
        """Añade el acta. Devuelve si se pudo; jamás propaga."""
        try:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                lineas = self._leer_crudo()
                lineas.append(json.dumps(acta.to_json(), ensure_ascii=False))
                # Se recorta por el PRINCIPIO: lo último medido es lo que se cita.
                self._path.write_text("\n".join(lineas[-MAX_ACTAS:]) + "\n", encoding="utf-8")
            return True
        except Exception:  # noqa: BLE001 — advisory: el camino de vida no se cae por esto
            self.fallos += 1
            log.exception("no se pudo escribir el acta del reflejo (aislado)")
            return False

    def _leer_crudo(self) -> list[str]:
        if not self._path.is_file():
            return []
        return [ln for ln in self._path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def actas(self) -> list[dict[str, Any]]:
        """Las actas guardadas, de la más vieja a la más nueva."""
        fuera: list[dict[str, Any]] = []
        for linea in self._leer_crudo():
            try:
                fuera.append(json.loads(linea))
            except json.JSONDecodeError:
                # Una línea corrupta no invalida las demás: se salta y se dice.
                log.warning("acta de reflejo ilegible, se omite: %r", linea[:120])
        return fuera

    def ultima(self) -> dict[str, Any] | None:
        actas = self.actas()
        return actas[-1] if actas else None

    def resumen(self) -> dict[str, Any]:
        """Lo que el panel publica. **Sin actas NO devuelve ceros**: dice que no hay.

        Un `0.0 ms` sobre un gabinete que nunca ha visto un flanco sería la mejor
        latencia del catálogo y una mentira; `null` con su conteo en cero es lo
        único cierto.
        """
        actas = [a for a in self.actas() if not a.get("es_prueba")]
        if not actas:
            return {"total": 0, "ultima": None, "mejor_ms": None, "peor_ms": None}
        ms = sorted(float(a["latencia_ms"]) for a in actas)
        return {
            "total": len(actas),
            "ultima": actas[-1],
            # Mejor y PEOR: publicar solo la mejor es cómo una cifra de venta deja
            # de describir al producto. El peor caso es el que un perito mira.
            "mejor_ms": ms[0],
            "peor_ms": ms[-1],
        }
