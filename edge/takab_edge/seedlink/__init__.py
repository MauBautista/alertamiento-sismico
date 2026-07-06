"""seedlink — cliente SeedLink contra el RS4D (TCP 18000) → bus local.

T-1.5: cliente real vía ObsPy con **reconexión** (backoff exponencial + jitter),
**medición de lag**, **cero-pérdida** al reconectar (**resume por número de
secuencia** de SeedLink + dedup por `(canal, starttime)`) y **detección de gaps**.
La ingesta corre en su propio hilo, desacoplada del resto del edge. 100 sps.

Validado contra el Shake real (`AM.R4F74`, ringserver OSOP):
- lag mediano ~0.4 s (gate #3 latencia — el presupuesto instrumental ≤2 s es
  alcanzable; el fallback UDP datacast NO hace falta).
- El resume por **seqnum** reproduce el histórico del ring (cero-pérdida); el
  resume por **tiempo** (timestamp) NO lo hace en este ringserver — por eso el
  transporte usa seqnum.

El transporte está abstraído (`SeedLinkTransport`) para probar la lógica de
reconexión/lag/dedup/gaps SIN hardware (`FakeTransport`); `ObsPySeedLinkTransport`
es el driver real.
"""

from __future__ import annotations

import logging
import random
import threading
from collections import deque
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Protocol, runtime_checkable

from takab_edge.config import EdgeSettings
from takab_edge.contracts import WaveformPacket, utcnow
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.seedlink")

PacketCallback = Callable[[WaveformPacket], None]

#: Tolerancia para clasificar un salto de tiempo como gap (además de 1 muestra).
_GAP_TOLERANCE_S = 0.5
#: Ventana de claves recientes para deduplicar el solape del resume.
_DEDUP_WINDOW = 1024


@runtime_checkable
class SeedLinkTransport(Protocol):
    """Conecta al servidor SeedLink y transmite paquetes vía ``emit``.

    Bloquea hasta que ``stop`` se active (retorno limpio) o hasta una desconexión
    (retorno o excepción). El transporte gestiona su propia reanudación (el driver
    real reanuda por número de secuencia para no perder datos).
    """

    def run(self, emit: Callable[[WaveformPacket], None], stop: threading.Event) -> None: ...


class SeedLinkClient(EdgeModule):
    """Publica `WaveformPacket` al bus local desde un transporte SeedLink.

    En dev sin transporte real, consume del simulador RS4D (`source`) con cadencia
    de pared. Los tests inyectan un `FakeTransport` o usan `feed`/`pump`.
    """

    name = "seedlink"

    def __init__(
        self,
        settings: EdgeSettings,
        source: Iterator[WaveformPacket] | None = None,
        transport: SeedLinkTransport | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self._source = source
        self._transport = transport
        self._subscribers: list[PacketCallback] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        # Métricas / estado de ingesta
        self._packets_seen = 0
        self._reconnects = 0
        self._duplicates = 0
        self._gaps = 0
        self._last_lag_s: float | None = None
        self._backoff = settings.seedlink_backoff_initial_s
        self._last_end: dict[str, datetime] = {}
        self._recent: deque[tuple[str, datetime]] = deque(maxlen=_DEDUP_WINDOW)
        self._recent_set: set[tuple[str, datetime]] = set()

    # --- Suscripción / publicación ---
    def on_packet(self, callback: PacketCallback) -> None:
        self._subscribers.append(callback)

    def feed(self, packet: WaveformPacket) -> None:
        """Publica un paquete a los suscriptores (crudo; usado por tests/simulador)."""
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

    def ingest(self, packet: WaveformPacket) -> None:
        """Deduplica, detecta gaps, mide lag y publica (ruta de transporte)."""
        key = (packet.channel, packet.starttime)
        if key in self._recent_set:
            self._duplicates += 1
            return  # solape de resume → cero duplicados (idempotencia)

        last_end = self._last_end.get(packet.channel)
        if last_end is not None:
            gap_s = (packet.starttime - last_end).total_seconds()
            sample_dt = 1.0 / packet.sample_rate if packet.sample_rate else 0.0
            if gap_s > sample_dt + _GAP_TOLERANCE_S:
                self._gaps += 1
                log.warning("gap en %s: %.2fs", packet.channel, gap_s)

        self._last_end[packet.channel] = packet.next_starttime
        self._last_lag_s = (utcnow() - packet.endtime).total_seconds()
        self._backoff = self.settings.seedlink_backoff_initial_s  # datos → resetea backoff
        self._remember(key)
        self.feed(packet)

    def _remember(self, key: tuple[str, datetime]) -> None:
        if len(self._recent) == self._recent.maxlen:
            self._recent_set.discard(self._recent[0])  # evicta la más antigua
        self._recent.append(key)
        self._recent_set.add(key)

    # --- Métricas ---
    @property
    def packets_seen(self) -> int:
        return self._packets_seen

    @property
    def reconnects(self) -> int:
        return self._reconnects

    @property
    def duplicates(self) -> int:
        return self._duplicates

    @property
    def gaps(self) -> int:
        return self._gaps

    @property
    def last_lag_s(self) -> float | None:
        return self._last_lag_s

    # --- Ciclo de vida ---
    def _on_start(self) -> None:
        self._stop.clear()
        if self._transport is not None:
            self._thread = threading.Thread(
                target=self._run_transport, name="seedlink", daemon=True
            )
            self._thread.start()
        elif self._source is not None and self.settings.dev_mode:
            self._thread = threading.Thread(target=self._run_pump, name="seedlink", daemon=True)
            self._thread.start()

    def _on_stop(self) -> None:
        self._stop.set()
        close = getattr(self._transport, "close", None)
        if callable(close):
            close()  # interrumpe un collect() bloqueado en el transporte real
        if self._thread is not None:
            self._thread.join(timeout=6.0)
            self._thread = None

    def _run_transport(self) -> None:
        while not self._stop.is_set():
            reason: object = None
            try:
                self._transport.run(self.ingest, self._stop)
            except Exception as exc:  # noqa: BLE001 — toda falla del transporte = desconexión
                reason = exc
            if self._stop.is_set():
                break
            # Sin stop ⇒ desconexión (retorno limpio o excepción): reconectar con backoff.
            self._reconnects += 1
            log.warning(
                "SeedLink desconectado (%s); reconectando en %.1fs",
                reason or "fin de stream",
                self._backoff,
            )
            jitter = random.uniform(0.0, self._backoff * 0.25)  # noqa: S311 — jitter, no cripto
            if self._stop.wait(self._backoff + jitter):
                break
            self._backoff = min(self._backoff * 2, self.settings.seedlink_backoff_max_s)

    def _run_pump(self) -> None:
        # Bombeo del simulador RS4D con cadencia de pared (dev, sin hardware).
        for packet in self._source or iter(()):
            if self._stop.is_set():
                break
            self.ingest(packet)
            interval = packet.npts / packet.sample_rate if packet.sample_rate else 1.0
            if self._stop.wait(interval):
                break


class ObsPySeedLinkTransport:
    """Driver real: `SeedLinkConnection` de ObsPy contra el ringserver del Shake.

    Reanuda por **número de secuencia** (`_resume_seq`), lo que en este ringserver
    reproduce el histórico del ring tras una desconexión (cero-pérdida). El resume
    por tiempo NO lo hace, por eso no se usa.
    """

    def __init__(
        self,
        host: str,
        port: int,
        network: str,
        station: str,
        location: str,
        channels: list[str],
        timeout: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.network = network
        self.station = station
        self.location = location
        self.channels = channels
        # Timeout corto: acota el bloqueo de collect() para que el bucle re-chequee
        # `stop` con prontitud durante silencio/apagado (stop-responsiveness).
        self.timeout = timeout
        self._resume_seq = -1  # -1 = desde ahora (primera conexión)
        self._conn = None

    def run(self, emit: Callable[[WaveformPacket], None], stop: threading.Event) -> None:
        from obspy.clients.seedlink.client.seedlinkconnection import SeedLinkConnection
        from obspy.clients.seedlink.slpacket import SLPacket

        conn = SeedLinkConnection(timeout=self.timeout)
        conn.netto = self.timeout  # timeout del recv del socket (default 120 s = muy alto)
        conn.set_sl_address(f"{self.host}:{self.port}")
        for channel in self.channels:
            conn.add_stream(
                self.network, self.station, channel, seqnum=self._resume_seq, timestamp=None
            )
        self._conn = conn
        try:
            while not stop.is_set():
                packet = conn.collect()
                # SLTERMINATE y SLERROR son centinelas de bytes (no SLPacket): ambos =
                # desconexión → retornar para que el cliente reconecte con backoff y cuente.
                if packet in (SLPacket.SLTERMINATE, SLPacket.SLERROR):
                    return
                if not isinstance(packet, SLPacket):
                    continue
                try:
                    trace = packet.get_trace()
                except Exception:  # noqa: BLE001 — paquete no-dato (INFO/keepalive)
                    continue
                seq = packet.get_sequence_number()
                if isinstance(seq, int) and seq >= 0:
                    self._resume_seq = seq  # próxima reconexión reanuda desde aquí
                emit(self._to_packet(trace))
        finally:
            self._conn = None
            conn.close()

    def close(self) -> None:
        """Cierra la conexión actual (interrumpe un `collect()` bloqueado desde otro hilo)."""
        conn = self._conn
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — cierre best-effort
                pass

    def _to_packet(self, trace) -> WaveformPacket:
        from datetime import UTC

        return WaveformPacket(
            network=trace.stats.network or self.network,
            station=trace.stats.station,
            location=trace.stats.location or "",
            channel=trace.stats.channel,
            starttime=trace.stats.starttime.datetime.replace(tzinfo=UTC),
            sample_rate=float(trace.stats.sampling_rate),
            samples=[int(x) for x in trace.data],
        )
