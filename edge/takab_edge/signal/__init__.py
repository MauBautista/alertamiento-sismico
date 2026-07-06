"""signal — features agregadas a 1 s (PGA, PGV, RMS, STA/LTA, clipping, health).

Scaffold de T-1.2: cómputo determinista mínimo por ventana para que la cadena
seedlink→signal→rules funcione en dev. Los features **validados contra ObsPy de
referencia (error <1%)** y las sensibilidades reales por canal (EHZ velocidad,
ENx aceleración) son **T-1.6**. Las sensibilidades de abajo son PLACEHOLDER.
"""

from __future__ import annotations

import logging

import numpy as np

from takab_edge.contracts import Feature1s, WaveformPacket
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.signal")

# PLACEHOLDER — se reemplazan por la respuesta instrumental real del RS4D en T-1.6.
_ACCEL_SENSITIVITY_G_PER_COUNT = 1.0e-6
_VEL_SENSITIVITY_CMS_PER_COUNT = 1.0e-4
_CLIP_COUNT = 2_000_000  # ~saturación del ADC de 24 bits (placeholder)
_STA_WINDOW = 20  # muestras (0.2 s a 100 sps)


def compute_features(packet: WaveformPacket) -> Feature1s:
    """Calcula features de 1 s a partir de un paquete de muestras (placeholder T-1.6)."""
    if not packet.samples:
        return Feature1s(
            station=packet.station,
            channel=packet.channel,
            window_start=packet.starttime,
            pga=0.0,
            pgv=0.0,
            rms=0.0,
            sta_lta=0.0,
            health_score=0.0,
        )

    data = np.asarray(packet.samples, dtype=np.float64)
    demeaned = data - data.mean()
    peak = float(np.abs(demeaned).max())
    rms = float(np.sqrt(np.mean(demeaned**2)))

    # STA/LTA simple (relación de energía ventana corta / ventana larga).
    lta = rms if rms > 0 else 1.0
    sta = float(np.sqrt(np.mean(demeaned[-_STA_WINDOW:] ** 2))) if data.size >= _STA_WINDOW else rms
    sta_lta = sta / lta if lta > 0 else 0.0

    clipping = bool(np.abs(data).max() >= _CLIP_COUNT)

    return Feature1s(
        station=packet.station,
        channel=packet.channel,
        window_start=packet.starttime,
        pga=peak * _ACCEL_SENSITIVITY_G_PER_COUNT,
        pgv=peak * _VEL_SENSITIVITY_CMS_PER_COUNT,
        rms=rms,
        sta_lta=sta_lta,
        clipping=clipping,
        health_score=0.5 if clipping else 1.0,
    )


class FeatureExtractor(EdgeModule):
    """Consume `WaveformPacket` y emite `Feature1s` (una por ventana de 1 s)."""

    name = "signal"
    depends_on = ("seedlink",)

    def __init__(self) -> None:
        super().__init__()
        self._last: Feature1s | None = None

    @property
    def last(self) -> Feature1s | None:
        return self._last

    def process(self, packet: WaveformPacket) -> Feature1s:
        feature = compute_features(packet)
        self._last = feature
        return feature

    def _on_start(self) -> None:
        log.info("extractor de features activo")
