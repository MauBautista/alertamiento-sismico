#!/usr/bin/env python3
"""Genera el asset de la sirena por audio (T-1.68): takab_edge/audio/assets/siren.wav.

Sirena hi-lo de emergencia (960/770 Hz, 0.5 s por tono). A 48 kHz cada tono completa
un número ENTERO de ciclos en 24000 muestras ⇒ cruce por cero en cada borde ⇒ el bucle
del watcher no produce clics. Committeado el WAV para no depender de generarlo; este
script lo hace reproducible y auditable (asset advisory: la sirena de RELÉ es la primaria).

Uso:  python edge/scripts/gen_siren.py
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SR = 48000  # coincide con el jack del Pi
TONE_S = 0.5
TONES = (960.0, 770.0)
PAIRS = 6  # 6 s en total (loop)
AMP = 0.6  # headroom, sin clipping

OUT = Path(__file__).resolve().parent.parent / "takab_edge" / "audio" / "assets" / "siren.wav"


def main() -> None:
    frames = bytearray()
    n = int(SR * TONE_S)
    for i in range(PAIRS * len(TONES)):
        f = TONES[i % len(TONES)]
        for k in range(n):
            frames += struct.pack("<h", int(AMP * math.sin(2 * math.pi * f * (k / SR)) * 32767))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))
    print(f"escrito {OUT} ({len(frames) // 2} muestras, {(len(frames) // 2) / SR:.1f} s)")


if __name__ == "__main__":
    main()
