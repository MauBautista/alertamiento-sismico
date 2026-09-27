"""Censo del audio empaquetado (T-9.10 · D-40).

Cada audio que suena en el edificio o en el teléfono tiene una entrada en
``shared/audio/MANIFEST.json`` con su huella, su formato, su fuente y su licencia.
La lógica de la comparación vive en ``tools/audio/verifica_manifiesto.py`` (solo
stdlib); aquí se importa por ruta y se añaden los invariantes que no son de huella.

SOLO stdlib y sin fixtures de base de datos: el censo no depende de Postgres.
"""

from __future__ import annotations

import importlib.util
import json
import os
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MANIFIESTO = RAIZ / "shared" / "audio" / "MANIFEST.json"
VERIFICADOR = RAIZ / "tools" / "audio" / "verifica_manifiesto.py"

#: Duración máxima del aviso de movimiento para la brigada (T-9.10, criterio 3).
MAX_MOVIMIENTO_S = 4.0

#: Nombres que delatan la herramienta de síntesis (GPL) o su fonemizador (GPL)
#: metidos como dependencia de un proyecto del repo. Se invocan AISLADOS (uv).
PROHIBIDOS_COMO_DEPENDENCIA = ("piper-tts", "piper_tts", "piper-phonemize", "espeak")

#: Ficheros donde se declaran dependencias.
DECLARACIONES = {"pyproject.toml", "uv.lock", "package.json", "package-lock.json"}

_PODA = {"node_modules", ".venv", ".git", "dist", "build", ".agents", ".claude", "audios"}


def _verificador():
    spec = importlib.util.spec_from_file_location("verifica_manifiesto", VERIFICADOR)
    assert spec is not None and spec.loader is not None, f"falta {VERIFICADOR}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _entradas() -> list[dict]:
    assert MANIFIESTO.is_file(), f"falta {MANIFIESTO.relative_to(RAIZ)}"
    return json.loads(MANIFIESTO.read_text(encoding="utf-8"))["audios"]


def test_el_manifiesto_coincide_con_lo_empaquetado() -> None:
    errores = _verificador().verificar(RAIZ)
    assert errores == [], "\n".join(errores)


def test_el_aviso_de_movimiento_dura_4_s_o_menos() -> None:
    (entrada,) = [e for e in _entradas() if e["id"] == "takab-voz-movimiento-v1"]
    for ruta in entrada["rutas"]:
        with wave.open(str(RAIZ / ruta), "rb") as w:
            duracion = w.getnframes() / w.getframerate()
        assert duracion <= MAX_MOVIMIENTO_S, f"{ruta}: {duracion:.3f} s > {MAX_MOVIMIENTO_S} s"


def test_toda_entrada_declara_licencia_del_audio_y_de_su_fuente() -> None:
    for e in _entradas():
        lic = e.get("licencia") or {}
        assert str(lic.get("audio", "")).strip(), f"{e['id']}: licencia del audio vacía"
        assert str(lic.get("fuente", "")).strip(), f"{e['id']}: licencia de la fuente vacía"


def test_ninguna_herramienta_gpl_es_dependencia_del_repo() -> None:
    hallazgos: list[str] = []
    for carpeta, subdirs, ficheros in os.walk(RAIZ):
        subdirs[:] = [d for d in subdirs if d not in _PODA]
        for nombre in DECLARACIONES.intersection(ficheros):
            ruta = Path(carpeta) / nombre
            texto = ruta.read_text(encoding="utf-8", errors="replace").lower()
            for prohibido in PROHIBIDOS_COMO_DEPENDENCIA:
                if f'"{prohibido}' in texto or f"'{prohibido}" in texto:
                    hallazgos.append(f"{ruta.relative_to(RAIZ)}: {prohibido}")
    assert hallazgos == [], "herramienta GPL declarada como dependencia: " + ", ".join(hallazgos)


def test_ningun_modelo_de_voz_vive_en_el_repo() -> None:
    """El modelo se descarga y se verifica por sha256; no se versiona."""
    modelos: list[str] = []
    for carpeta, subdirs, ficheros in os.walk(RAIZ):
        subdirs[:] = [d for d in subdirs if d not in _PODA]
        modelos += [
            str((Path(carpeta) / f).relative_to(RAIZ))
            for f in ficheros
            if f.startswith("es_MX-") and f.endswith((".onnx", ".onnx.json"))
        ]
    assert modelos == [], f"modelo de voz dentro del repo: {modelos}"
