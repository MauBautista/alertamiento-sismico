"""seedlink — cliente SeedLink contra el RS4D (TCP 18000) → bus local.

Scaffold de T-1.2: interfaz de suscripción a paquetes y bombeo desde una fuente
inyectada (el simulador RS4D en dev, sin hardware). El cliente TCP real con
reconexión/backoff y medición de lag, y "cero pérdida al reiniciar el Shake",
son **T-1.5**. El RS4D muestrea a **100 sps** (no 200 Hz) — [ANALISIS-00].
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator

from takab_edge.config import EdgeSettings
from takab_edge.contracts import WaveformPacket
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.seedlink")

PacketCallback = Callable[[WaveformPacket], None]


class SeedLinkClient(EdgeModule):
    """Publica `WaveformPacket` al bus local. En dev consume del simulador RS4D."""

    name = "seedlink"

    def __init__(
        self,
        settings: EdgeSettings,
        source: Iterator[WaveformPacket] | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self._source = source
        self._subscribers: list[PacketCallback] = []
        self._packets_seen = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def on_packet(self, callback: PacketCallback) -> None:
        self._subscribers.append(callback)

    def feed(self, packet: WaveformPacket) -> None:
        """Empuja un paquete a los suscriptores (usado por tests/simulador)."""
        self._packets_seen += 1
        for callback in self._subscribers:
            callback(packet)

    def pump(self, count: int = 1) -> int:
        """Extrae `count` paquetes de la fuente de forma síncrona (determinista)."""
        if self._source is None:
            return 0
        pulled = 0
        for _ in range(count):
            try:
                packet = next(self._source)
            except StopIteration:
                break
            self.feed(packet)
            pulled += 1
        return pulled

    @property
    def packets_seen(self) -> int:
        return self._packets_seen

    def _on_start(self) -> None:
        # En dev con fuente disponible, arranca un hilo de bombeo continuo.
        if self._source is not None and self.settings.dev_mode:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="seedlink", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        for packet in self._source or iter(()):
            if self._stop.is_set():
                break
            self.feed(packet)
            # Cadencia de pared: un paquete de 1 s se emite en ~1 s reales. Evita el
            # busy-loop (100% CPU) y mantiene el reloj simulado en sincronía con el
            # real. `wait` es interrumpible: para limpio ante stop.
            interval = packet.npts / packet.sample_rate if packet.sample_rate else 1.0
            if self._stop.wait(interval):
                break

    def _on_stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
