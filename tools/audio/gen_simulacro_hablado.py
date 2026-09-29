#!/usr/bin/env python3
"""El simulacro HABLADO del gabinete (T-9.71 · D-41).

D-41: el audio abre con **2,5 s de voz sola** («Esto es un simulacro.») y después la
voz se repite **al menos cuatro veces** encima del **tono de alerta** atenuado 15 dB.
Se ensaya con el sonido que la gente va a oír de verdad; la voz primero y encima es lo
que impide confundirlo con una alerta real.

⚠️ El tono de fondo es el de ALERTA vigente (``takab-siren-v1``), no el carillón del
simulacro v1: el candidato del 2026-09-28 (``simulacro_hablado_v2.wav``) usó el
carillón, y eso no es lo que D-41 decidió. Si T-9.70 cambia el tono de alerta, este
fichero se regenera con el nuevo (``TONO``).

Niveles: la voz se iguala en RMS activo al tono, y el tono se atenúa 15 dB; así el
tono queda 15 dB por debajo de su nivel propio Y de la voz. Luego la mezcla entera se
normaliza para el edge (``normaliza.OBJETIVO_EDGE_LUFS``, pico verdadero ≤ −1 dBTP),
que escala todo por igual y no toca esa relación. El fichero termina con la voz: lo
último que se oye es «simulacro», no el tono.

Corre en el mismo entorno aislado que ``normaliza.py``::

    uv run --no-project --python 3.12 \\
      --with numpy==2.5.3 --with scipy==1.18.1 --with pyloudnorm==0.2.0 \\
      python tools/audio/gen_simulacro_hablado.py

Lee la voz que ``gen_voces.sh`` deja en ``VOZ`` (entrada ``takab-voz-simulacro-v1`` de
``voces.json``). Determinista: mismas versiones, mismos bytes. Después hay que
regenerar el manifiesto con ``manifiesto.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parent))
import normaliza  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
VOZ = Path("shared") / "audio" / "fuentes" / "voz_simulacro.wav"
TONO = Path("edge") / "takab_edge" / "audio" / "assets" / "siren.wav"
DESTINO = Path("edge") / "takab_edge" / "audio" / "assets" / "simulacro_hablado.wav"
SR = 22050

VOZ_SOLA_S = 2.5
PRIMERA_S = 0.2
PERIODO_S = 4.5
REPETICIONES_SOBRE_TONO = 4
ATENUACION_DB = 15.0
COLA_S = 0.4

#: Lo que el manifiesto declara como parámetros (una sola fuente de verdad).
PARAMETROS = (
    f"voz «Esto es un simulacro.» sola en {PRIMERA_S} s; desde {VOZ_SOLA_S} s el tono de "
    f"alerta ({TONO.as_posix()}) atenuado {ATENUACION_DB:g} dB y la voz encima "
    f"{REPETICIONES_SOBRE_TONO} veces cada {PERIODO_S} s; voz igualada en RMS activo al "
    f"tono; termina {COLA_S} s después de la última voz; {SR} Hz mono PCM16"
)


def _a_sr(x: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR:
        return x
    mcd = np.gcd(SR, sr)
    return resample_poly(x, SR // mcd, sr // mcd)


def _rms_activo(x: np.ndarray, umbral_db: float = -40.0) -> float:
    """RMS de las tramas de 20 ms que no son silencio (relativo al pico)."""
    n = int(0.02 * SR)
    tramas = x[: len(x) // n * n].reshape(-1, n)
    rms = np.sqrt(np.mean(tramas**2, axis=1))
    activas = rms[rms >= rms.max() * 10 ** (umbral_db / 20)]
    return float(np.sqrt(np.mean(activas**2)))


def inicios_de_la_voz() -> list[float]:
    """Dónde empieza cada frase, en segundos: una sola y las demás sobre el tono."""
    return [PRIMERA_S] + [VOZ_SOLA_S + 0.7 + k * PERIODO_S for k in range(REPETICIONES_SOBRE_TONO)]


def mezcla() -> np.ndarray:
    """El simulacro en float64, sin normalizar."""
    voz, sr_voz = normaliza.leer(RAIZ / VOZ)
    tono, sr_tono = normaliza.leer(RAIZ / TONO)
    voz, tono = _a_sr(voz, sr_voz), _a_sr(tono, sr_tono)
    voz = voz * (_rms_activo(tono) / _rms_activo(voz))

    inicios = inicios_de_la_voz()
    n = int(round((inicios[-1] + COLA_S) * SR)) + len(voz)
    fondo = np.zeros(n)
    desde = int(round(VOZ_SOLA_S * SR))
    fondo[desde:] = np.resize(tono, n - desde) * 10 ** (-ATENUACION_DB / 20)
    cola = int(round(COLA_S * SR))
    fondo[n - cola :] *= 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, cola)))

    salida = fondo.copy()
    for inicio in inicios:
        i = int(round(inicio * SR))
        salida[i : i + len(voz)] += voz
    return salida


def main() -> int:
    pcm, sr = normaliza.normaliza(mezcla(), SR, objetivo_lufs=normaliza.OBJETIVO_EDGE_LUFS)
    normaliza.escribir(RAIZ / DESTINO, pcm, sr)
    print(json.dumps(normaliza.mide(RAIZ / DESTINO), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
