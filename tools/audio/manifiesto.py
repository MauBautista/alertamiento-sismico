#!/usr/bin/env python3
"""Escribe ``shared/audio/MANIFEST.json`` MIDIENDO los ficheros (T-9.10 · D-40).

La procedencia se DECLARA aquí (tonos existentes) o en ``voces.json`` (voces); las
cifras (sha256, duración, formato, LUFS, dBTP) se MIDEN, nunca se copian a mano.
Corre en el mismo entorno aislado que ``normaliza.py``::

    uv run --no-project --python 3.12 \\
      --with numpy==2.5.3 --with scipy==1.18.1 --with pyloudnorm==0.2.0 \\
      python tools/audio/manifiesto.py

Lo que el repo no documenta se escribe tal cual: «procedencia no documentada en el
repo». Un NO MEDIDO no es un aprobado.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import normaliza  # noqa: E402
from verifica_manifiesto import MANIFIESTO, sha256  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
VOCES = Path(__file__).resolve().parent / "voces.json"
NO_DOCUMENTADA = "procedencia no documentada en el repo"

#: Tonos que ya vivían en el repo antes de T-9.10. Cada frase sale de un comentario,
#: una ficha o un commit que se cita; nada se infiere.
EXISTENTES: list[dict] = [
    {
        "id": "takab-siren-v1",
        "rutas": [
            "edge/takab_edge/audio/assets/siren.wav",
            "mobile/assets/sounds/alerta_sismica.wav",
        ],
        "fuente": {
            "generador": "edge/scripts/gen_siren.py (T-1.68)",
            "parametros": "sirena hi-lo 960/770 Hz, 0.5 s por tono, 6 pares (6 s), "
            "48 kHz mono PCM16, amplitud 0.6",
        },
        "licencia": {
            "audio": "original de TAKAB (tono propio, D-19; sintetizado por gen_siren.py)",
            "fuente": "código del repo (edge/scripts/gen_siren.py), propiedad de TAKAB",
        },
        "notas": "El mismo fichero, byte a byte, es la sirena del gabinete (catálogo del "
        "edge) y el sonido de alerta y de notificación de la app (sound.ts, push.ts). "
        "El tono oficial SASMEX (CIRES) está reservado y ausente (sasmex-oficial-v1). "
        "Medido 2026-09-27: gen_siren.py reproduce este sha256 byte a byte.",
    },
    {
        "id": "takab-prueba-v1",
        "rutas": ["edge/takab_edge/audio/assets/prueba.wav"],
        "fuente": {"generador": NO_DOCUMENTADA, "parametros": NO_DOCUMENTADA},
        "licencia": {
            "audio": "original de TAKAB según T-2.49 (commit 8583feb: «bips graves "
            "espaciados, no confundibles con el barrido de la sirena»)",
            "fuente": NO_DOCUMENTADA,
        },
        "notas": "Tono del self-test de sirena (T-2.49). No hay script generador en el "
        "repo: su procedencia técnica no se puede reproducir desde aquí.",
    },
    {
        "id": "takab-simulacro-v1",
        "rutas": ["edge/takab_edge/audio/assets/simulacro.wav"],
        "fuente": {
            "generador": "edge/scripts/gen_simulacro.py (T-5.17)",
            "parametros": "carillón de 3 pulsos 587.5/740/880 Hz de 0.25 s + 2 s de "
            "silencio, 4 ciclos (11 s), 48 kHz mono PCM16, amplitud 0.45",
        },
        "licencia": {
            "audio": "original de TAKAB (sintetizado por gen_simulacro.py)",
            "fuente": "código del repo (edge/scripts/gen_simulacro.py), propiedad de TAKAB",
        },
        "notas": "Es un TONO, no el mensaje hablado de simulacro (D-41 / T-9.71). Medido "
        "2026-09-27: gen_simulacro.py reproduce este sha256 byte a byte.",
    },
]


def _voces() -> list[dict]:
    cfg = json.loads(VOCES.read_text(encoding="utf-8"))
    piper, modelo = cfg["piper"], cfg["modelo"]
    salida = []
    for v in cfg["voces"]:
        salida.append(
            {
                "id": v["id"],
                "rutas": v["rutas"],
                "fuente": {
                    "generador": "tools/audio/gen_voces.sh → sintetiza.py (Piper) → normaliza.py",
                    "piper": piper["paquete"],
                    "onnxruntime": piper["onnxruntime"],
                    "modelo": modelo["nombre"],
                    "modelo_onnx_sha256": modelo["onnx_sha256"],
                    "modelo_json_sha256": modelo["json_sha256"],
                    "texto": v["texto"],
                    "semilla": v["semilla"],
                    "length_scale": v["length_scale"],
                    "noise_scale": v["noise_scale"],
                    "noise_w_scale": v["noise_w_scale"],
                    "normalizacion": f"{normaliza.OBJETIVO_LUFS} LUFS, pico verdadero ≤ "
                    f"{normaliza.PICO_MAX_DBTP} dBTP (×{normaliza.SOBREMUESTREO}), cola "
                    f"≤ {int(normaliza.COLA_S * 1000)} ms",
                },
                "licencia": {
                    "audio": "TAKAB; generado localmente con un modelo apache-2.0",
                    "fuente": f"modelo: {modelo['licencia']}; herramienta: {piper['licencia']}",
                },
                "notas": f"Alternativa de voz: {modelo['alternativa']}. "
                f"Duración máxima exigida: {v['max_duracion_s']} s.",
            }
        )
    return salida


def construir() -> dict:
    audios = []
    for e in EXISTENTES + _voces():
        primera = RAIZ / e["rutas"][0]
        m = normaliza.mide(primera)
        audios.append(
            {
                "id": e["id"],
                "rutas": e["rutas"],
                "sha256": sha256(primera),
                "duracion_s": m["duracion_s"],
                "sample_rate": m["sample_rate"],
                "canales": m["canales"],
                "lufs_integrado": m["lufs_integrado"],
                "pico_verdadero_dbtp": m["pico_verdadero_dbtp"],
                "fuente": e["fuente"],
                "licencia": e["licencia"],
                "notas": e["notas"],
            }
        )
    return {
        "_doc": "GENERADO por tools/audio/manifiesto.py; lo comprueba "
        "tools/audio/verifica_manifiesto.py y api/tests/test_censo_audio.py (T-9.10 · D-40).",
        "audios": audios,
    }


def main() -> int:
    destino = RAIZ / MANIFIESTO
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(construir(), ensure_ascii=False, indent=2) + "\n"
    destino.write_text(texto, encoding="utf-8")
    print(f"✓ {MANIFIESTO.as_posix()} escrito")
    return 0


if __name__ == "__main__":
    sys.exit(main())
