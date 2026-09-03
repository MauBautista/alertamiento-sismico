#!/usr/bin/env python3
"""Genera el tono de SIMULACRO (T-5.17): takab_edge/audio/assets/simulacro.wav.

**Esto es un TONO, no el mensaje hablado.** El voceo grabado de simulacro
(`audio_simulacro_path`) sigue siendo un asset local y sigue bloqueado por su
gate de hardware: `RUNBOOK-gate-hw-movil-y-voceo.md §C.2` exige que el mensaje de
sismo y el de simulacro sean **distinguibles a oído**, y eso son dos grabaciones
que nadie ha hecho todavía. Lo que este archivo aporta es lo que la nube SÍ puede
elegir por identificador de catálogo mientras tanto.

Y está construido para que NO se pueda confundir con la sirena. La sirena es
hi-lo continuo (960/770 Hz, 0.5 s por tono, sin silencios): urgencia. Este es un
carillón de TRES pulsos ascendentes seguidos de dos segundos de silencio —el
patrón que usan los avisos de megafonía, no las alarmas—, así que quien lo oye en
un pasillo distingue el ensayo de la emergencia antes de entender ninguna
palabra. Un simulacro que suena a sismo es una falsa alarma provocada por el
propio sistema, que es justo lo que `T-2.49` eliminó para el self-test.

A 48 kHz cada tono completa un número ENTERO de ciclos ⇒ cruce por cero en cada
borde ⇒ el bucle no produce clics (misma razón que `gen_siren.py`).

Uso:  python edge/scripts/gen_simulacro.py
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SR = 48000  # coincide con el jack del Pi
#: Carillón ascendente: tres pulsos cortos, claramente NO una sirena.
PULSOS = (587.5, 740.0, 880.0)  # re5 · fa#5 · la5 — un acorde, no una alarma
PULSO_S = 0.25
SILENCIO_S = 2.0  # el hueco es la mitad del mensaje: una alarma no calla
CICLOS = 4  # 4 × (3×0.25 + 2.0) = 11 s
AMP = 0.45  # más bajo que la sirena a propósito: esto avisa, no alarma

OUT = Path(__file__).resolve().parent.parent / "takab_edge" / "audio" / "assets" / "simulacro.wav"


def _tono(f: float, segundos: float) -> bytearray:
    """Un tono de `f` Hz redondeado al ciclo entero más próximo (sin clics)."""
    n = int(SR * segundos)
    ciclos = max(1, round(f * segundos))
    f_ajustada = ciclos * SR / n
    out = bytearray()
    for k in range(n):
        # Envolvente de subida/bajada: un pulso con bordes duros chasquea.
        borde = min(1.0, min(k, n - 1 - k) / (SR * 0.01))
        muestra = AMP * borde * math.sin(2 * math.pi * f_ajustada * (k / SR))
        out += struct.pack("<h", int(muestra * 32767))
    return out


def main() -> None:
    frames = bytearray()
    silencio = bytes(2 * int(SR * SILENCIO_S))
    for _ in range(CICLOS):
        for f in PULSOS:
            frames += _tono(f, PULSO_S)
        frames += silencio
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))
    print(f"escrito {OUT} ({len(frames) // 2} muestras, {(len(frames) // 2) / SR:.1f} s)")


if __name__ == "__main__":
    main()
