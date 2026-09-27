#!/usr/bin/env python3
"""Normaliza y mide audio para el teléfono y el gabinete (T-9.10 · D-40).

Corre AISLADO, nunca como dependencia de un proyecto del repo::

    uv run --no-project --python 3.12 \\
      --with numpy==2.5.3 --with scipy==1.18.1 --with pyloudnorm==0.2.0 \\
      python tools/audio/normaliza.py ENTRADA.wav SALIDA.wav
    ... python tools/audio/normaliza.py --mide A.wav [B.wav ...]   # JSON por stdout

Qué hace, en orden (y nada más):

1. Mono (media de canales) y PCM16. Si la entrada no está a 22 050 ni a 44 100 Hz
   se remuestrea a 22 050 Hz con ``resample_poly``.
2. Recorta el silencio de COLA: lo último por encima de ``UMBRAL_REL_DB`` bajo la
   trama más fuerte, más ``COLA_S`` (≤ 100 ms) con un desvanecido de ``FUNDIDO_S``.
3. Ganancia hacia ``-16 LUFS`` integrados (BS.1770 vía pyloudnorm), limitada para
   que el pico verdadero (sobremuestreo ×4) quede ≤ ``-1 dBTP``. Sin limitador ni
   compresor: si el pico manda, la sonoridad queda por debajo del objetivo y la
   medición final lo dice.

Determinista: aritmética float64 sin aleatoriedad ni dither ⇒ misma entrada, mismos
bytes (con las versiones fijadas arriba).
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

import numpy as np
import pyloudnorm
from scipy.signal import resample_poly

OBJETIVO_LUFS = -16.0
PICO_MAX_DBTP = -1.0
MARGEN_PICO_DB = 0.1  # el redondeo a PCM16 puede subir el pico unas centésimas
SOBREMUESTREO = 4
FRECUENCIAS = (22050, 44100)
TRAMA_S = 0.010
UMBRAL_REL_DB = -45.0
COLA_S = 0.100
FUNDIDO_S = 0.010


def leer(ruta: Path) -> tuple[np.ndarray, int]:
    """Mono float64 en [-1, 1] y su frecuencia. Solo PCM16 (lo que empaquetamos)."""
    with wave.open(str(ruta), "rb") as w:
        if w.getsampwidth() != 2:
            raise SystemExit(f"{ruta}: solo PCM16 (sampwidth={w.getsampwidth()})")
        canales, sr = w.getnchannels(), w.getframerate()
        datos = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    x = datos.astype(np.float64).reshape(-1, canales).mean(axis=1) / 32768.0
    return x, sr


def escribir(ruta: Path, pcm: np.ndarray, sr: int) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.astype("<i2").tobytes())


def pico_verdadero_dbtp(x: np.ndarray) -> float:
    pico = float(np.max(np.abs(resample_poly(x, SOBREMUESTREO, 1))))
    return 20.0 * np.log10(pico) if pico > 0 else float("-inf")


def sonoridad_lufs(x: np.ndarray, sr: int) -> float:
    return float(pyloudnorm.Meter(sr).integrated_loudness(x))


def recorta_cola(x: np.ndarray, sr: int) -> np.ndarray:
    n = max(1, int(round(TRAMA_S * sr)))
    tramas = len(x) // n
    if tramas == 0:
        return x
    rms = np.sqrt(np.mean(x[: tramas * n].reshape(tramas, n) ** 2, axis=1))
    db = 20.0 * np.log10(np.maximum(rms, 1e-12))
    activas = np.nonzero(db >= db.max() + UMBRAL_REL_DB)[0]
    fin = min(len(x), (int(activas[-1]) + 1) * n + int(round(COLA_S * sr)))
    y = x[:fin].copy()
    f = min(len(y), int(round(FUNDIDO_S * sr)))
    y[len(y) - f :] *= 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, f)))
    return y


def a_pcm16(x: np.ndarray) -> np.ndarray:
    return np.clip(np.round(x * 32767.0), -32768, 32767).astype(np.int16)


def normaliza(x: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    if sr not in FRECUENCIAS:
        x, sr = resample_poly(x, 22050, sr), 22050
    x = recorta_cola(x, sr)
    ganancia = OBJETIVO_LUFS - sonoridad_lufs(x, sr)
    techo = PICO_MAX_DBTP - MARGEN_PICO_DB - pico_verdadero_dbtp(x)
    ganancia = min(ganancia, techo)
    while True:
        pcm = a_pcm16(x * 10.0 ** (ganancia / 20.0))
        if pico_verdadero_dbtp(pcm / 32768.0) <= PICO_MAX_DBTP:
            return pcm, sr
        ganancia -= 0.05


def mide(ruta: Path) -> dict:
    x, sr = leer(ruta)
    with wave.open(str(ruta), "rb") as w:
        canales, n = w.getnchannels(), w.getnframes()
    return {
        "ruta": str(ruta),
        "duracion_s": round(n / sr, 4),
        "sample_rate": sr,
        "canales": canales,
        "lufs_integrado": round(sonoridad_lufs(x, sr), 2),
        "pico_verdadero_dbtp": round(pico_verdadero_dbtp(x), 2),
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--mide", nargs="+", type=Path, help="solo medir y emitir JSON")
    p.add_argument("entrada", nargs="?", type=Path)
    p.add_argument("salida", nargs="?", type=Path)
    a = p.parse_args(argv)
    if a.mide:
        print(json.dumps([mide(r) for r in a.mide], ensure_ascii=False, indent=2))
        return 0
    if not (a.entrada and a.salida):
        p.error("hacen falta ENTRADA y SALIDA (o --mide)")
    pcm, sr = normaliza(*leer(a.entrada))
    escribir(a.salida, pcm, sr)
    print(json.dumps(mide(a.salida), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
