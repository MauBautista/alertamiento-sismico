#!/usr/bin/env python3
"""Música de prueba de los parlantes del gabinete (T-9.72 · D-40).

«Himno a la alegría» (Ludwig van Beethoven, Sinfonía n.º 9, 1824): la COMPOSICIÓN es
de dominio público y aquí se SINTETIZA con numpy (senoides con dos armónicos y
envolvente exponencial). No hay grabación de terceros, así que no hay licencia de
grabación que revisar. Es el mismo contenido musical que el candidato de
F7 (``candidatos_f7.py``, 2026-09-28): la melodía en dos frases, bajo de blancas y
la pieza entera dos veces con medio segundo de silencio entre ellas.

Corre en el mismo entorno aislado que ``normaliza.py``::

    uv run --no-project --python 3.12 \\
      --with numpy==2.5.3 --with scipy==1.18.1 --with pyloudnorm==0.2.0 \\
      python tools/audio/gen_musica.py

Escribe ``edge/takab_edge/audio/assets/musica_prueba.wav`` a 22 050 Hz mono PCM16,
normalizado para el EDGE (``normaliza.OBJETIVO_EDGE_LUFS``, pico verdadero ≤ −1 dBTP).
Determinista: sin aleatoriedad ni dither ⇒ mismas versiones, mismos bytes. Después
hay que regenerar el manifiesto con ``manifiesto.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import normaliza  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = Path("edge") / "takab_edge" / "audio" / "assets" / "musica_prueba.wav"

SR = 22050
NEGRA_S = 0.5
NOTAS = {
    "C4": 261.63,
    "D4": 293.66,
    "E4": 329.63,
    "F4": 349.23,
    "G4": 392.0,
    "C3": 130.81,
    "G3": 196.0,
    "F3": 174.61,
    "E3": 164.81,
}
#: Sufijo «.» = negra con puntillo; «h» = blanca.
MELODIA = (
    "E4 E4 F4 G4 G4 F4 E4 D4 C4 C4 D4 E4 E4. D4h E4 E4 F4 G4 G4 F4 E4 D4 C4 C4 D4 E4 D4. C4h"
).split()
BAJO = ["C3", "G3", "C3", "G3", "F3", "C3", "G3", "G3"] * 2
REPETICIONES = 2
PAUSA_S = 0.5

#: Lo que el manifiesto declara como parámetros (una sola fuente de verdad).
PARAMETROS = (
    f"«Himno a la alegría», melodía en Do mayor ({len(MELODIA)} notas, negra = "
    f"{NEGRA_S} s) con armónicos 2.º (0.3) y 3.º (0.1) y caída exp(-1.8 t); bajo de "
    f"blancas ({len(BAJO)} notas, 0.35, exp(-1.2 t)); {REPETICIONES} vueltas con "
    f"{PAUSA_S} s de silencio; {SR} Hz mono PCM16"
)


def _envolvente(n: int, ataque_s: float, relajo_s: float) -> np.ndarray:
    e = np.ones(n)
    na, nr = int(ataque_s * SR), int(relajo_s * SR)
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr:
        e[-nr:] = np.linspace(1, 0, nr)
    return e


def _duracion(nota: str) -> float:
    if nota.endswith("."):
        return NEGRA_S * 1.5
    if nota.endswith("h"):
        return NEGRA_S * 2
    return NEGRA_S


def sintetiza() -> np.ndarray:
    """La pieza en float64, sin normalizar."""
    voz = []
    for nota in MELODIA:
        f = NOTAS[nota.rstrip(".h")]
        t = np.arange(int(_duracion(nota) * SR)) / SR
        x = (
            np.sin(2 * np.pi * f * t)
            + 0.3 * np.sin(4 * np.pi * f * t)
            + 0.1 * np.sin(6 * np.pi * f * t)
        )
        voz.append(x * np.exp(-1.8 * t) * _envolvente(len(t), 0.01, 0.05))
    melodia = np.concatenate(voz)

    t_bajo = np.arange(int(2 * NEGRA_S * SR)) / SR
    bajo = np.concatenate(
        [0.35 * np.sin(2 * np.pi * NOTAS[n] * t_bajo) * np.exp(-1.2 * t_bajo) for n in BAJO]
    )
    pieza = np.zeros(max(len(melodia), len(bajo)))
    pieza[: len(melodia)] += melodia
    pieza[: len(bajo)] += bajo
    return np.tile(np.concatenate([pieza, np.zeros(int(PAUSA_S * SR))]), REPETICIONES)


def main() -> int:
    pcm, sr = normaliza.normaliza(sintetiza(), SR, objetivo_lufs=normaliza.OBJETIVO_EDGE_LUFS)
    normaliza.escribir(RAIZ / DESTINO, pcm, sr)
    print(json.dumps(normaliza.mide(RAIZ / DESTINO), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
