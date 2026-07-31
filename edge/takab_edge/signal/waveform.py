"""WaveformRing — 60 s de muestras crudas en RAM por canal + serve incremental (T-2.15).

El hueco que cierra: las muestras (`WaveformPacket.samples`, counts del ADC) cruzaban
`seedlink → signal → buffer` y jamás llegaban al panel — lo único graficable era una
envolvente de features a 1 Hz, que no es un sismograma. Este ring guarda resolución
completa (int32, ~96 KB los 4 canales) y **decima al servir, no al almacenar**.

Decisiones de diseño (contrato §5.1 de la spec del panel, congelado):

- **Cursor global** (`_gc` = total de muestras appendeadas, todos los canales):
  stateless — el servidor no guarda estado por cliente; el kiosco manda su cursor.
- **`reset: true`** cuando el cursor no sirve (primera petición, cursor de otra vida
  del proceso, o ya se cayó del ring): el cliente REDIBUJA, jamás empalma.
- **Decimación min/max por bucket** con pares APLANADOS (longitud siempre par): el
  submuestreo ingenuo se salta el pico y dibuja un sismo más chico del que fue.
- **`gap_before` es un corte honesto**: un hueco del sensor a mitad del rango pedido
  sirve SOLO el tramo posterior al último hueco — unir dos tramos discontinuos con
  una línea recta inventa movimiento que no ocurrió.
- **Marks a paquete completo**: en cuanto una muestra de un paquete se sobrescribe,
  el paquete entero deja de servirse (≤1 s de cola perdida sobre una ventana de 60 s)
  y el piso de reset sube. Simplifica el ring y nunca sirve un tramo a medias.

El camino de features JAMÁS muere por el ring: `FeatureExtractor.process` lo alimenta
dentro de un try/except y este módulo no toca red, disco ni actuadores.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from takab_edge.contracts import WaveformPacket

#: Clamp del parámetro max_points (peticiones del kiosco): jamás 400, se acota.
_MAX_POINTS_MIN = 50
_MAX_POINTS_MAX = 6000
_MAX_POINTS_DEFAULT = 1500

#: Tolerancia de contigüidad entre paquetes, en fracción del periodo de muestreo.
_GAP_TOLERANCE_SAMPLES = 0.6


@dataclass
class _Mark:
    """Metadatos de un paquete appendeado (para serve incremental y gaps)."""

    gc_end: int  # cursor global al terminar este paquete
    start_abs: int  # índice absoluto (por canal) de su primera muestra
    npts: int
    starttime: datetime
    gap: bool  # hubo hueco del sensor ANTES de este paquete


class _ChannelRing:
    """Buffer circular int32 de un canal, dimensionado con su primer paquete."""

    def __init__(self, sample_rate: float, window_s: float) -> None:
        self.sample_rate = sample_rate
        self.capacity = max(1, int(round(window_s * sample_rate)))
        self.data = np.zeros(self.capacity, dtype=np.int32)
        self.end_abs = 0  # total de muestras jamás appendeadas al canal
        self.expected_next: datetime | None = None
        self.marks: deque[_Mark] = deque()

    @property
    def filled(self) -> int:
        return min(self.end_abs, self.capacity)

    def append(self, packet: WaveformPacket, gc_end: int) -> int:
        """Escribe las muestras (copia circular en ≤2 slices) y registra el mark.

        Devuelve el gc_end del mark MÁS NUEVO que quedó podado (0 si ninguno):
        el ring global sube su piso de reset con eso.
        """
        samples = np.asarray(packet.samples, dtype=np.int32)
        npts = int(samples.size)
        if npts == 0:
            return 0
        gap = False
        if self.expected_next is not None:
            drift_s = abs((packet.starttime - self.expected_next).total_seconds())
            gap = drift_s > _GAP_TOLERANCE_SAMPLES / self.sample_rate
        self.expected_next = packet.next_starttime

        if npts >= self.capacity:
            # Paquete gigante (no ocurre con miniSEED real): queda solo su cola.
            self.data[:] = samples[-self.capacity :]
            self.end_abs += npts
        else:
            pos = self.end_abs % self.capacity
            first = min(npts, self.capacity - pos)
            self.data[pos : pos + first] = samples[:first]
            if npts > first:
                self.data[: npts - first] = samples[first:]
            self.end_abs += npts

        self.marks.append(
            _Mark(
                gc_end=gc_end,
                start_abs=self.end_abs - npts,
                npts=npts,
                starttime=packet.starttime,
                gap=gap,
            )
        )
        # Poda: un paquete con CUALQUIER muestra sobrescrita deja de servirse entero.
        floor_abs = self.end_abs - self.filled
        pruned_gc = 0
        while self.marks and self.marks[0].start_abs < floor_abs:
            pruned_gc = self.marks.popleft().gc_end
        return pruned_gc

    def segment_since(self, since: int | None) -> tuple[list[_Mark], bool] | None:
        """Marks del tramo a servir (corte honesto en el último gap del rango).

        `since=None` ⇒ ventana completa. Devuelve None si no hay nada que servir.
        """
        candidates = [m for m in self.marks if since is None or m.gc_end > since]
        if not candidates:
            return None
        start = 0
        for i, mark in enumerate(candidates):
            if mark.gap:
                start = i  # el ÚLTIMO tramo continuo; lo anterior no se empalma
        segment = candidates[start:]
        gap_before = segment[0].gap
        return segment, gap_before

    def extract(self, segment: list[_Mark]) -> np.ndarray:
        """Copia (defensiva) de las muestras contiguas que cubren el segmento."""
        start_abs = segment[0].start_abs
        end_abs = segment[-1].start_abs + segment[-1].npts
        count = end_abs - start_abs
        pos = start_abs % self.capacity
        first = min(count, self.capacity - pos)
        out = np.empty(count, dtype=np.int32)
        out[:first] = self.data[pos : pos + first]
        if count > first:
            out[first:] = self.data[: count - first]
        return out


def _decimate_minmax(samples: np.ndarray, factor: int) -> np.ndarray:
    """Envolvente min/max por bucket, APLANADA [min0, max0, min1, max1, …]."""
    n = samples.size
    buckets = math.ceil(n / factor)
    pad = buckets * factor - n
    if pad:
        # Repetir la última muestra no inventa amplitud: min y max quedan iguales.
        samples = np.concatenate([samples, np.full(pad, samples[-1], dtype=samples.dtype)])
    grid = samples.reshape(buckets, factor)
    out = np.empty(buckets * 2, dtype=samples.dtype)
    out[0::2] = grid.min(axis=1)
    out[1::2] = grid.max(axis=1)
    return out


class WaveformRing:
    """Ring multi-canal con cursor global y serve decimado (thread-safe).

    `append` corre en el hilo de SeedLink (µs: una copia de slices); `serve` corre
    en los hilos HTTP del panel — el lock cubre solo el snapshot; la decimación y
    la serialización ocurren FUERA, sobre copias.
    """

    def __init__(self, window_s: float = 60.0) -> None:
        self.window_s = window_s
        self._channels: dict[str, _ChannelRing] = {}
        self._gc = 0  # cursor global: total de muestras appendeadas (todos los canales)
        self._floor = 0  # cursores < floor perdieron datos podados ⇒ reset
        self._lock = threading.Lock()

    def append(self, packet: WaveformPacket) -> None:
        if not packet.samples or packet.sample_rate <= 0:
            return
        with self._lock:
            ring = self._channels.get(packet.channel)
            if ring is None:
                ring = _ChannelRing(packet.sample_rate, self.window_s)
                self._channels[packet.channel] = ring
            self._gc += len(packet.samples)
            pruned_gc = ring.append(packet, self._gc)
            if pruned_gc > self._floor:
                self._floor = pruned_gc

    def serve(
        self,
        since: int | None,
        channels: list[str] | None = None,
        max_points: int | None = None,
    ) -> dict:
        """Respuesta completa del contrato §5.1 (lista para serializar a JSON)."""
        points = max_points if max_points is not None else _MAX_POINTS_DEFAULT
        points = max(_MAX_POINTS_MIN, min(_MAX_POINTS_MAX, points))

        with self._lock:
            reset = since is None or since > self._gc or since < self._floor
            effective_since = None if reset else since
            cursor = self._gc
            base_sr: float | None = None
            extracted: dict[str, tuple[np.ndarray, bool, datetime]] = {}
            for name, ring in self._channels.items():
                if channels is not None and name not in channels:
                    continue
                if base_sr is None:
                    base_sr = ring.sample_rate
                found = ring.segment_since(effective_since)
                if found is None:
                    continue
                segment, gap_before = found
                extracted[name] = (ring.extract(segment), gap_before, segment[0].starttime)

        # Fuera del lock: decimar y serializar sobre las copias.
        longest = max((arr.size for arr, _, _ in extracted.values()), default=0)
        factor = max(1, math.ceil(longest / points))
        payload: dict[str, dict] = {}
        for name, (arr, gap_before, first_at) in extracted.items():
            data = arr if factor == 1 else _decimate_minmax(arr, factor)
            payload[name] = {
                # .tolist() SIEMPRE: numpy int32 no serializa a JSON.
                "samples": data.tolist(),
                "encoding": "raw" if factor == 1 else "minmax",
                "first_sample_at": first_at.isoformat(),
                "gap_before": gap_before,
            }
        return {
            "cursor": cursor,
            "reset": reset,
            "sample_rate": None if base_sr is None else base_sr / factor,
            "decimation": factor,
            "channels": payload,
        }


__all__ = ["WaveformRing"]
