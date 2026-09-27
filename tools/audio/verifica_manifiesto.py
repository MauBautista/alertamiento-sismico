#!/usr/bin/env python3
"""Compara ``shared/audio/MANIFEST.json`` con los audios empaquetados (T-9.10 · D-40).

Solo stdlib (``wave``, ``hashlib``, ``json``): corre en CI y en el test de censo
sin instalar nada. Comprueba, en las dos direcciones:

1. Cada ruta de cada entrada existe y coincide con su sha256, duración (±5 ms),
   frecuencia de muestreo y canales declarados.
2. Ningún audio empaquetado (``.wav``/``.mp3``/``.ogg``/``.caf``) en
   ``mobile/assets``, ``edge/`` o ``shared/audio`` falta en el manifiesto.

Sale 0 si todo cuadra; 1 con un mensaje por discrepancia si no.

Uso:  python3 tools/audio/verifica_manifiesto.py [RAIZ_DEL_REPO]
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import wave
from pathlib import Path

MANIFIESTO = Path("shared") / "audio" / "MANIFEST.json"

#: Dónde se empaqueta audio que suena en el edificio o en el teléfono.
ZONAS = (Path("mobile") / "assets", Path("edge"), Path("shared") / "audio")
EXTENSIONES = (".wav", ".mp3", ".ogg", ".caf", ".m4a", ".aac", ".flac", ".opus")
#: Nunca se barren: dependencias, compilados y la carpeta ``audios/`` de la raíz
#: (material de terceros que NO entra al repo).
PODA = {"node_modules", ".venv", "venv", ".git", "dist", "build", "__pycache__", "audios"}
TOLERANCIA_DURACION_S = 0.005


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 16), b""):
            h.update(bloque)
    return h.hexdigest()


def empaquetados(raiz: Path) -> set[str]:
    """Rutas relativas (POSIX) de todo audio empaquetado en las zonas vigiladas."""
    hallados: set[str] = set()
    for zona in ZONAS:
        base = raiz / zona
        if not base.is_dir():
            continue
        for carpeta, subdirs, ficheros in os.walk(base):
            subdirs[:] = [d for d in subdirs if d not in PODA]
            for f in ficheros:
                if f.lower().endswith(EXTENSIONES):
                    hallados.add((Path(carpeta) / f).relative_to(raiz).as_posix())
    return hallados


def _compara_wav(raiz: Path, ruta: str, e: dict) -> list[str]:
    errores: list[str] = []
    fichero = raiz / ruta
    if not fichero.is_file():
        return [f"{e['id']}: la ruta {ruta} no existe"]
    real = sha256(fichero)
    if real != e.get("sha256"):
        errores.append(
            f"{e['id']}: sha256 de {ruta} es {real}, el manifiesto dice {e.get('sha256')}"
        )
    if not ruta.lower().endswith(".wav"):
        return errores + [f"{e['id']}: {ruta} no es WAV; este verificador solo mide WAV"]
    try:
        with wave.open(str(fichero), "rb") as w:
            sr, canales, n = w.getframerate(), w.getnchannels(), w.getnframes()
    except (wave.Error, EOFError) as exc:
        return errores + [f"{e['id']}: {ruta} no es un WAV PCM legible ({exc})"]
    duracion = n / sr
    if abs(duracion - float(e.get("duracion_s", -1))) > TOLERANCIA_DURACION_S:
        errores.append(
            f"{e['id']}: {ruta} dura {duracion:.4f} s, el manifiesto dice {e.get('duracion_s')}"
        )
    if sr != e.get("sample_rate"):
        errores.append(f"{e['id']}: {ruta} a {sr} Hz, el manifiesto dice {e.get('sample_rate')}")
    if canales != e.get("canales"):
        errores.append(f"{e['id']}: {ruta} con {canales} canal(es), manifiesto {e.get('canales')}")
    return errores


def verificar(raiz: Path) -> list[str]:
    """Lista de discrepancias; vacía si el manifiesto y el árbol coinciden."""
    manifiesto = raiz / MANIFIESTO
    if not manifiesto.is_file():
        return [f"falta {MANIFIESTO.as_posix()}"]
    try:
        entradas = json.loads(manifiesto.read_text(encoding="utf-8"))["audios"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return [f"{MANIFIESTO.as_posix()} ilegible: {exc}"]

    errores: list[str] = []
    declaradas: set[str] = set()
    ids: set[str] = set()
    for e in entradas:
        if e.get("id") in ids:
            errores.append(f"id duplicado: {e.get('id')}")
        ids.add(e.get("id"))
        if not e.get("rutas"):
            errores.append(f"{e.get('id')}: sin rutas")
        for ruta in e.get("rutas", []):
            if ruta in declaradas:
                errores.append(f"{e['id']}: la ruta {ruta} ya figura en otra entrada")
            declaradas.add(ruta)
            errores += _compara_wav(raiz, ruta, e)

    for ruta in sorted(empaquetados(raiz) - declaradas):
        errores.append(f"{ruta} está empaquetado y NO figura en {MANIFIESTO.as_posix()}")
    return errores


def main(argv: list[str]) -> int:
    raiz = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[2]
    errores = verificar(raiz)
    if errores:
        print(f"✗ el manifiesto de audio NO coincide ({len(errores)}):", file=sys.stderr)
        for err in errores:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(
        f"✓ manifiesto de audio: {len(empaquetados(raiz))} fichero(s) empaquetado(s), todos al día"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
