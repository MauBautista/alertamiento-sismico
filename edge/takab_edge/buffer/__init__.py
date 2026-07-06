"""buffer — ring buffer miniSEED en disco (NVMe) + extracción de ventana de evento.

T-1.7: persiste el waveform crudo como **miniSEED** en archivos por día y canal, con
**retención circular** (poda por antigüedad 7–14 d y por tamaño), y **extrae la
ventana miniSEED** de un evento confirmado para subir a S3 (T-1.11/T-1.25). El
waveform crudo NO se sube en continuo (regla de oro 9): sólo la ventana de eventos.

La lógica de ring/retención/extracción se valida en cualquier filesystem (tests con
tmp); el tamaño real en GB se mide con hardware (gate #3).
"""

from __future__ import annotations

import logging
import tempfile
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

from takab_edge.config import BufferConfig
from takab_edge.contracts import WaveformPacket
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.buffer")

#: Cada cuántos append se ejecuta la poda (evita podar en cada paquete).
_PRUNE_EVERY = 1000


def to_miniseed_bytes(packet: WaveformPacket) -> bytes:
    """Codifica un `WaveformPacket` a un registro miniSEED (int32 = counts del RS4D)."""
    import numpy as np
    from obspy import Stream, Trace, UTCDateTime

    trace = Trace(np.asarray(packet.samples, dtype=np.int32))
    trace.stats.network = packet.network
    trace.stats.station = packet.station
    trace.stats.location = packet.location
    trace.stats.channel = packet.channel
    trace.stats.sampling_rate = packet.sample_rate
    trace.stats.starttime = UTCDateTime(packet.starttime)
    buf = BytesIO()
    Stream([trace]).write(buf, format="MSEED")
    return buf.getvalue()


class RingBuffer(EdgeModule):
    """Ring buffer miniSEED en disco: archivos `<net>.<sta>.<loc>.<cha>.<YYYYMMDD>.mseed`."""

    name = "buffer"
    depends_on = ("seedlink",)

    def __init__(self, config: BufferConfig | None = None) -> None:
        super().__init__()
        self.config = config or BufferConfig()
        self.root = (
            Path(self.config.root)
            if self.config.root
            else Path(tempfile.mkdtemp(prefix="takab-buffer-"))
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self._appended = 0
        self._newest: date | None = None  # fecha del dato más reciente (poda relativa al dato)
        self._since_prune = 0

    # --- Escritura ---
    def append(self, packet: WaveformPacket) -> None:
        if not packet.samples:
            return
        with open(self._dayfile(packet), "ab") as fh:
            fh.write(to_miniseed_bytes(packet))
        self._appended += 1
        pdate = packet.starttime.date()
        if self._newest is None or pdate > self._newest:
            self._newest = pdate
        self._since_prune += 1
        if self._since_prune >= _PRUNE_EVERY:
            self._since_prune = 0
            self.prune()

    def _dayfile(self, packet: WaveformPacket) -> Path:
        stamp = packet.starttime.date().strftime("%Y%m%d")
        name = f"{packet.network}.{packet.station}.{packet.location}.{packet.channel}.{stamp}.mseed"
        return self.root / name

    # --- Poda circular ---
    def prune(self) -> None:
        """Elimina archivos más viejos que la retención y, si sobra tamaño, los más antiguos."""
        if self._newest is not None:
            cutoff = self._newest - timedelta(days=self.config.retention_days)
            for path, fdate, _size in self._files():
                if fdate < cutoff:
                    path.unlink(missing_ok=True)
        files = self._files()
        total = sum(size for _, _, size in files)
        for path, _fdate, size in files:  # más antiguos primero
            if total <= self.config.max_bytes:
                break
            path.unlink(missing_ok=True)
            total -= size

    def _files(self) -> list[tuple[Path, date, int]]:
        out: list[tuple[Path, date, int]] = []
        for path in self.root.glob("*.mseed"):
            fdate = self._date_of(path)
            if fdate is not None:
                out.append((path, fdate, path.stat().st_size))
        out.sort(key=lambda item: item[1])  # por fecha ascendente
        return out

    @staticmethod
    def _date_of(path: Path) -> date | None:
        try:
            return datetime.strptime(path.stem.split(".")[-1], "%Y%m%d").date()
        except (ValueError, IndexError):
            return None

    def total_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.root.glob("*.mseed"))

    # --- Extracción de la ventana de evento ---
    def extract_window(self, start: datetime, end: datetime) -> bytes:
        """miniSEED de la ventana [start, end] de un evento confirmado (para S3)."""
        from obspy import Stream, UTCDateTime, read

        stream = Stream()
        day = start.date()
        while day <= end.date():
            for path in self.root.glob(f"*.{day.strftime('%Y%m%d')}.mseed"):
                try:
                    stream += read(str(path))
                except Exception:  # noqa: BLE001 — archivo dañado: sáltalo, no bloquees el evento
                    log.warning("miniSEED ilegible, omitido: %s", path.name)
            day += timedelta(days=1)
        if len(stream) == 0:
            return b""
        stream.trim(UTCDateTime(start), UTCDateTime(end))
        stream.merge(method=1)
        buf = BytesIO()
        stream.write(buf, format="MSEED")
        return buf.getvalue()

    def __len__(self) -> int:
        """Número de paquetes escritos desde el arranque (métrica de ingesta)."""
        return self._appended

    def _on_start(self) -> None:
        log.info(
            "ring buffer en %s (retención %d d, tope %d MB)",
            self.root,
            self.config.retention_days,
            self.config.max_bytes // 1024**2,
        )
