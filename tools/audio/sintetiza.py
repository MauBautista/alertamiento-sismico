#!/usr/bin/env python3
"""Sintetiza UNA voz con Piper, con semilla fija (T-9.10 · D-40).

Corre SOLO dentro del entorno aislado que monta ``gen_voces.sh``::

    uv run --no-project --python 3.12 --with piper-tts==1.3.0 \\
      --with onnxruntime==1.30.0 python tools/audio/sintetiza.py MODELO.onnx SALIDA.wav \\
      --texto "..." --semilla 40 --length-scale 1.0 --noise-scale 0.667 --noise-w-scale 0.8

Por qué la API y no el CLI de ``piper``: el modelo VITS inyecta ruido gaussiano
(``noise_scale``/``noise_w``) desde ``onnxruntime``, así que dos corridas del CLI dan
bytes distintos (medido). ``onnxruntime.set_seed`` fija ese ruido y la síntesis pasa
a ser reproducible en la misma máquina y versiones.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import sys
import wave

import onnxruntime
from piper import PiperVoice, SynthesisConfig


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("modelo")
    p.add_argument("salida")
    p.add_argument("--texto", required=True)
    p.add_argument("--semilla", type=int, required=True)
    p.add_argument("--length-scale", type=float, required=True)
    p.add_argument("--noise-scale", type=float, required=True)
    p.add_argument("--noise-w-scale", type=float, required=True)
    a = p.parse_args(argv)

    onnxruntime.set_seed(a.semilla)
    voz = PiperVoice.load(a.modelo)
    cfg = SynthesisConfig(
        length_scale=a.length_scale,
        noise_scale=a.noise_scale,
        noise_w_scale=a.noise_w_scale,
    )
    with wave.open(a.salida, "wb") as w:
        voz.synthesize_wav(a.texto, w, syn_config=cfg)
    print(
        f"piper-tts {importlib.metadata.version('piper-tts')} · "
        f"onnxruntime {onnxruntime.__version__} · {a.salida}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
