"""Simulador del Raspberry Shake RS4D — feed sintético 100 sps (miniSEED).

Genera paquetes de 1 s con ruido de fondo e inyección opcional de un evento
(transitorio amortiguado) para elevar PGA/PGV. Emite `WaveformPacket` (contrato
interno) y, de forma faithful, `obspy.Stream`/miniSEED para el cliente SeedLink
real de T-1.5. El RS4D muestrea a **100 sps** — [ANALISIS-00].

Determinista: el generador de ruido usa una semilla fija (reproducible en tests).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

import numpy as np
from takab_edge.contracts import WaveformPacket, utcnow

#: Canales del RS4D: EHZ (velocidad, vertical) + ENZ/ENN/ENE (aceleración MEMS).
DEFAULT_CHANNELS: tuple[str, ...] = ("EHZ", "ENZ", "ENN", "ENE")

#: [T-2.25] Offsets DC realistas por canal (counts del ADC): un acelerómetro real
#: NUNCA es de media cero — ENZ ve la gravedad (≈1 g ≈ 9.80665 / 2.6007802e-6 ≈
#: 3.77e6 counts con la sensibilidad real de AM.R4F74) y los horizontales llevan
#: el bias de cero-g del MEMS. EHZ (geófono, AC-coupled) sí es ≈0. El ruido de
#: media cero enmascaraba el bug de la brújula del panel (counts crudos contra
#: escala de-media): el default realista lo hace imposible de re-ocultar. Valores
#: ENTEROS a propósito: `rint(ruido + c) == rint(ruido) + c` ⇒ las features
#: (que de-median) quedan idénticas con o sin offset salvo ULPs de float64.
DEFAULT_DC_OFFSETS: dict[str, float] = {
    "EHZ": 0.0,
    "ENZ": 3_770_000.0,
    "ENN": 15_000.0,
    "ENE": -9_000.0,
}


class RS4DSimulator:
    """Fuente de forma de onda sintética 100 sps por canal."""

    def __init__(
        self,
        station: str = "TAKAB",
        network: str = "AM",
        location: str = "",
        sample_rate: float = 100.0,
        channels: tuple[str, ...] = DEFAULT_CHANNELS,
        noise_counts: float = 500.0,
        seed: int = 1234,
        dc_offsets: dict[str, float] | None = None,
    ) -> None:
        self.station = station
        self.network = network
        self.location = location
        self.sample_rate = sample_rate
        self.channels = channels
        self.noise_counts = noise_counts
        # None ⇒ default realista; media cero se pide EXPLÍCITA con dc_offsets={}.
        self.dc_offsets = DEFAULT_DC_OFFSETS if dc_offsets is None else dc_offsets
        self._rng = np.random.default_rng(seed)

    def _samples(self, peak_counts: float = 0.0, dc: float = 0.0) -> list[int]:
        n = int(round(self.sample_rate))  # una ventana de 1 s
        noise = self._rng.normal(0.0, self.noise_counts, n)
        signal = np.zeros(n)
        if peak_counts:
            t = np.arange(n) / self.sample_rate
            envelope = np.exp(-3.0 * t)  # decaimiento del transitorio
            signal = peak_counts * envelope * np.sin(2.0 * np.pi * 5.0 * t)
        data = np.rint(noise + signal + dc).astype(np.int32)
        return data.tolist()

    def packet(self, channel: str, start: datetime, peak_counts: float = 0.0) -> WaveformPacket:
        """Un paquete de 1 s para un canal (con o sin evento inyectado)."""
        return WaveformPacket(
            network=self.network,
            station=self.station,
            location=self.location,
            channel=channel,
            starttime=start,
            sample_rate=self.sample_rate,
            samples=self._samples(peak_counts, dc=self.dc_offsets.get(channel, 0.0)),
        )

    def stream(
        self,
        channel: str = "EHZ",
        start: datetime | None = None,
        seconds: int | None = None,
        event_onset_s: int | None = None,
        event_peak_counts: float = 0.0,
    ) -> Iterator[WaveformPacket]:
        """Genera paquetes de 1 s. Si ``seconds`` es None, el stream es infinito.

        Un evento se inyecta en el segundo ``event_onset_s`` con amplitud
        ``event_peak_counts`` (PGA ≈ counts × sensibilidad; ver `signal`).
        """
        current = start or utcnow()
        index = 0
        while seconds is None or index < seconds:
            peak = (
                event_peak_counts if event_onset_s is not None and index == event_onset_s else 0.0
            )
            yield self.packet(channel, current, peak_counts=peak)
            current = current + timedelta(seconds=1)
            index += 1

    def to_stream(self, packet: WaveformPacket):
        """Convierte un `WaveformPacket` a `obspy.Stream` (miniSEED-capable, T-1.5)."""
        from obspy import Stream, Trace, UTCDateTime

        trace = Trace(np.asarray(packet.samples, dtype=np.int32))
        trace.stats.network = packet.network
        trace.stats.station = packet.station
        trace.stats.location = packet.location
        trace.stats.channel = packet.channel
        trace.stats.sampling_rate = packet.sample_rate
        trace.stats.starttime = UTCDateTime(packet.starttime)
        return Stream([trace])

    def to_miniseed_bytes(self, packet: WaveformPacket) -> bytes:
        """Serializa un paquete a miniSEED (lo que el Shake real entrega por SeedLink)."""
        from io import BytesIO

        buffer = BytesIO()
        self.to_stream(packet).write(buffer, format="MSEED")
        return buffer.getvalue()
