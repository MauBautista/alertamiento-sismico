"""signal — features agregadas a 1 s (PGA, PGV, RMS, STA/LTA, clipping, health).

T-1.6: cómputo determinista con **NumPy/SciPy** (blueprint §4.3; el módulo NO
importa ObsPy → ligero). Los algoritmos se validan contra ObsPy de referencia
(error <1%) en traza sintética y real:
- STA/LTA idéntico a `obspy.signal.trigger.classic_sta_lta`.
- integración/diferenciación idénticas a `Trace.integrate()/differentiate()`.

Por convención SEED, el 2º caracter del canal indica el instrumento: `H`
(seismometer → velocidad, p.ej. EHZ) o `N` (accelerometer → aceleración, p.ej.
ENZ). PGA se obtiene de la aceleración; PGV de la velocidad; la que no es nativa
del canal se deriva por integración/diferenciación.

La escala física depende de las sensibilidades (config, PLACEHOLDER hasta calibrar
con la respuesta StationXML del RS4D); el algoritmo es correcto con o sin esa
calibración.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

import numpy as np
from scipy.integrate import cumulative_trapezoid

from takab_edge.config import SignalConfig
from takab_edge.contracts import Feature1s, WaveformPacket, utcnow
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.signal")

_G = 9.80665  # m/s² por g


def classic_sta_lta(a: np.ndarray, nsta: int, nlta: int) -> np.ndarray:
    """STA/LTA clásico — idéntico a `obspy.signal.trigger.classic_sta_lta`."""
    a = np.asarray(a, dtype=np.float64)
    sta = np.cumsum(a**2)
    lta = sta.copy()
    sta[nsta:] = sta[nsta:] - sta[:-nsta]
    sta /= nsta
    lta[nlta:] = lta[nlta:] - lta[:-nlta]
    lta /= nlta
    sta[: nlta - 1] = 0
    tiny = np.finfo(0.0).tiny
    lta[lta < tiny] = tiny
    return sta / lta


def integrate(data: np.ndarray, dt: float) -> np.ndarray:
    """Integración trapezoidal acumulada — como `Trace.integrate()` (cumtrapz)."""
    return cumulative_trapezoid(np.asarray(data, dtype=np.float64), dx=dt, initial=0.0)


def differentiate(data: np.ndarray, dt: float) -> np.ndarray:
    """Diferenciación por gradiente — como `Trace.differentiate()` (gradient)."""
    return np.gradient(np.asarray(data, dtype=np.float64), dt)


def is_acceleration(channel: str) -> bool:
    """True si el canal mide aceleración (código de instrumento SEED `N`/`G`)."""
    return len(channel) >= 2 and channel[1] in ("N", "G")


def _windows(config: SignalConfig, sr: float) -> tuple[int, int]:
    """Ventanas STA/LTA en muestras; nlta ≥ nsta+1 ≥ 2 (acota el contexto y evita
    divisiones/gradientes degenerados). Fuente única usada por compute_features y
    por el contexto rodante para que NO diverjan."""
    nsta = max(1, int(round(config.sta_seconds * sr)))
    nlta = max(nsta + 1, int(round(config.lta_seconds * sr)))
    return nsta, nlta


def _health_score(clipping: bool, rms: float) -> float:
    if rms == 0.0:
        return 0.0  # canal plano/muerto (dropout)
    if clipping:
        return 0.5  # saturación → dato degradado
    return 1.0


def compute_features(
    packet: WaveformPacket,
    config: SignalConfig | None = None,
    preceding: np.ndarray | None = None,
) -> Feature1s:
    """Features de 1 s del paquete. `preceding` = muestras previas (contexto STA/LTA)."""
    config = config or SignalConfig()
    sr = packet.sample_rate
    # <2 muestras es degenerado: la diferenciación (np.gradient) exige ≥2 y las
    # features no tienen sentido en un solo punto → devuelve un snapshot en cero.
    if len(packet.samples) < 2 or sr <= 0:
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

    raw = np.asarray(packet.samples, dtype=np.float64)
    demeaned = raw - raw.mean()
    dt = 1.0 / sr

    accel_ch = is_acceleration(packet.channel)
    sens = (
        config.accel_sensitivity_ms2_per_count if accel_ch else config.vel_sensitivity_ms_per_count
    )
    native = demeaned * sens  # m/s² (accel) o m/s (velocidad)
    if accel_ch:
        accel, vel = native, integrate(native, dt)
    else:
        vel, accel = native, differentiate(native, dt)

    pga = float(np.abs(accel).max()) / _G  # g
    pgv = float(np.abs(vel).max()) * 100.0  # cm/s
    rms = float(np.sqrt(np.mean(demeaned**2)))  # counts

    # STA/LTA sobre (contexto + paquete) para que el LTA tenga historia suficiente.
    if preceding is not None and len(preceding):
        series = np.concatenate([np.asarray(preceding, dtype=np.float64), raw])
    else:
        series = raw
    series = series - series.mean()
    nsta, nlta = _windows(config, sr)
    if len(series) >= nlta:
        ratio = classic_sta_lta(series, nsta, nlta)
        sta_lta = float(np.max(ratio[-len(raw) :]))  # pico en la región del paquete nuevo
    else:
        sta_lta = 0.0

    clipping = bool(np.abs(raw).max() >= config.clip_count)
    return Feature1s(
        station=packet.station,
        channel=packet.channel,
        window_start=packet.starttime,
        pga=pga,
        pgv=pgv,
        rms=rms,
        sta_lta=sta_lta,
        clipping=clipping,
        health_score=_health_score(clipping, rms),
    )


class FeatureExtractor(EdgeModule):
    """Consume `WaveformPacket` y emite `Feature1s`, con contexto rodante por canal."""

    name = "signal"
    depends_on = ("seedlink",)

    def __init__(self, config: SignalConfig | None = None) -> None:
        super().__init__()
        self.config = config or SignalConfig()
        self._context: dict[str, np.ndarray] = {}
        self._last: Feature1s | None = None
        # [T-1.53] Última feature POR CANAL + hora de RECEPCIÓN (reloj de pared
        # del Pi): el panel local mide staleness contra esto — window_start es
        # el reloj de datos del Shake y no sirve para detectar "sin señal".
        self._by_channel: dict[str, tuple[Feature1s, datetime]] = {}
        self._live_lock = threading.Lock()

    @property
    def last(self) -> Feature1s | None:
        return self._last

    def live_by_channel(self) -> dict[str, tuple[Feature1s, datetime]]:
        """Copia del último `Feature1s` por canal con su hora de llegada.

        Para el panel LAN (T-1.53): lectura barata desde los hilos HTTP sin
        tocar el camino caliente (el lock solo protege el dict, nanosegundos).
        """
        with self._live_lock:
            return dict(self._by_channel)

    def process(self, packet: WaveformPacket) -> Feature1s:
        preceding = self._context.get(packet.channel)
        feature = compute_features(packet, self.config, preceding)
        self._update_context(packet)
        self._last = feature
        with self._live_lock:
            self._by_channel[packet.channel] = (feature, utcnow())
        return feature

    def _update_context(self, packet: WaveformPacket) -> None:
        if len(packet.samples) < 2 or packet.sample_rate <= 0:
            return
        raw = np.asarray(packet.samples, dtype=np.float64)
        prev = self._context.get(packet.channel)
        buf = raw if prev is None else np.concatenate([prev, raw])
        # Mismo nlta que compute_features (≥2) → el contexto SIEMPRE se acota.
        _, nlta = _windows(self.config, packet.sample_rate)
        self._context[packet.channel] = buf[-nlta:]

    def _on_start(self) -> None:
        log.info(
            "extractor de features activo (STA/LTA %.1fs/%.1fs)",
            self.config.sta_seconds,
            self.config.lta_seconds,
        )
