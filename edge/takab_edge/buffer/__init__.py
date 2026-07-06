"""buffer — ring buffer de paquetes crudos + extracción de ventana de evento.

Scaffold de T-1.2: ring en memoria con capacidad acotada y extracción de la
ventana temporal de un evento. El ring **miniSEED en NVMe con retención 7–14 días**
(~0.5–4 GB reales a 100 sps × 4 canales — [ANALISIS-00]/[PLAN-MAESTRO-01]) y la
subida de la ventana a S3 son **T-1.7**.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime

from takab_edge.contracts import WaveformPacket
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.buffer")

_DEFAULT_CAPACITY = 6000  # ~1 min a 100 sps × 1 canal (placeholder; NVMe en T-1.7)


class RingBuffer(EdgeModule):
    """Almacena los últimos N paquetes y extrae la ventana de un evento."""

    name = "buffer"
    depends_on = ("seedlink",)

    def __init__(self, capacity: int = _DEFAULT_CAPACITY) -> None:
        super().__init__()
        self._packets: deque[WaveformPacket] = deque(maxlen=capacity)

    def append(self, packet: WaveformPacket) -> None:
        self._packets.append(packet)

    def __len__(self) -> int:
        return len(self._packets)

    def extract_window(self, start: datetime, end: datetime) -> list[WaveformPacket]:
        """Devuelve los paquetes cuyo `starttime` cae en [start, end]."""
        return [p for p in self._packets if start <= p.starttime <= end]

    def _on_start(self) -> None:
        log.info("ring buffer activo (capacidad %d paquetes)", self._packets.maxlen or 0)
