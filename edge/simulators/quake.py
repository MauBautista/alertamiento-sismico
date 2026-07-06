"""Generador de sismo — secuencia de paquetes SeedLink que modela un evento real.

Ruido de fondo → **onda P** (moderada, sobre todo vertical) → **onda S** (fuerte, sobre
disparo en varios ejes). Permite la demo E2E y los tests de carga sin sismo real (T-1.14),
ejercitando el pipeline completo seedlink→signal→buffer→rules→actuadores con la nube apagada.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from takab_edge.contracts import WaveformPacket

from simulators.rs4d import RS4DSimulator

DEFAULT_CHANNELS = ("EHZ", "ENZ", "ENN", "ENE")


def quake_packets(
    sim: RS4DSimulator,
    start: datetime,
    *,
    channels: tuple[str, ...] = DEFAULT_CHANNELS,
    pre_s: int = 2,
    p_s: int = 2,
    s_s: int = 3,
    s_peak_counts: float = 1_000_000.0,
) -> list[WaveformPacket]:
    """Paquetes ordenados (1 s por canal) de un sismo: ruido → P (cautela) → S (disparo).

    `s_peak_counts` satura la onda S por encima del umbral de disparo en los ejes de
    aceleración → corrobora (≥2 canales) → `evacuate_or_hold`. La onda P queda en cautela.
    """
    packets: list[WaveformPacket] = []
    moment = start

    def _burst(peak_for) -> None:
        nonlocal moment
        for channel in channels:
            packets.append(sim.packet(channel, moment, peak_counts=peak_for(channel)))
        moment += timedelta(seconds=1)

    for _ in range(pre_s):  # ruido de fondo
        _burst(lambda _ch: 0.0)
    for _ in range(p_s):  # onda P: moderada (más en los verticales), por debajo de disparo
        _burst(lambda ch: s_peak_counts * (0.15 if ch in ("EHZ", "ENZ") else 0.05))
    for _ in range(s_s):  # onda S: fuerte, sobre disparo en varios ejes
        _burst(lambda _ch: s_peak_counts)

    return packets


def quake_window(start: datetime, *, pre_s: int = 2, p_s: int = 2, s_s: int = 3) -> tuple:
    """Ventana [inicio, fin] del sismo generado (para extraer la evidencia miniSEED)."""
    return start, start + timedelta(seconds=pre_s + p_s + s_s)
