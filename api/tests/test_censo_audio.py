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


# ---------------------------------------------------------------------------
# [T-9.70 · D-50] El sonido OFICIAL del SASMEX viaja FUERA de git.
#
# Suena con SASMEX y con el cuórum, pero el fichero nunca entra al repositorio: se
# inyecta al compilar la APK y al publicar la release del gabinete. El manifiesto lo
# DECLARA (huella, formato, fuente) con `fuera_de_git`, y aquí se vigila que siga
# fuera.
# ---------------------------------------------------------------------------

OFICIAL_ID = "sasmex-oficial-v1"


def _oficial() -> dict:
    [e] = [e for e in _entradas() if e["id"] == OFICIAL_ID]
    return e


def test_el_oficial_se_declara_fuera_de_git_con_su_huella() -> None:
    e = _oficial()
    assert e.get("fuera_de_git") is True
    assert len(e["sha256"]) == 64 and e["sample_rate"] and e["canales"] == 1
    assert "CIRES" in e["licencia"]["audio"] and "D-50" in e["licencia"]["audio"]


def test_ningun_fichero_del_repositorio_es_el_oficial() -> None:
    """Por NOMBRE y por HUELLA: ni el mp3 recibido ni el WAV derivado, se llamen como
    se llamen. Un `git add -A` en el checkout principal lo subía: `audios/` no estaba
    ignorado."""
    import hashlib
    import subprocess

    e = _oficial()
    prohibidas = {e["sha256"], e["fuente"]["original_sha256"]}
    rastreados = (
        subprocess.run(["git", "-C", str(RAIZ), "ls-files", "-z"], capture_output=True, check=True)
        .stdout.decode()
        .split("\0")
    )
    nombres = {Path(r).name for r in e["rutas"]} | {"Sonido_Alerta_Sismica_Oficial.mp3"}
    for rel in filter(None, rastreados):
        ruta = RAIZ / rel
        assert ruta.name not in nombres, f"{rel}: el sonido oficial no se comitea (D-50)"
        if ruta.suffix.lower() in (".wav", ".mp3", ".ogg", ".caf", ".m4a") and ruta.is_file():
            huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
            assert huella not in prohibidas, f"{rel} ES el sonido oficial (D-50)"


def test_las_rutas_del_oficial_estan_ignoradas_por_git() -> None:
    import subprocess

    e = _oficial()
    locales = ["audios/Sonido_Alerta_Sismica_Oficial.mp3", "audios/sasmex_oficial.wav"]
    for rel in [*e["rutas"], *locales]:
        r = subprocess.run(["git", "-C", str(RAIZ), "check-ignore", "-q", rel])
        assert r.returncode == 0, f"{rel} no está en .gitignore: un `git add -A` lo subiría"


def test_el_verificador_acepta_el_oficial_ausente_y_mide_el_presente(tmp_path: Path) -> None:
    import shutil

    v = _verificador()
    (tmp_path / "shared" / "audio").mkdir(parents=True)
    wav = tmp_path / "edge" / "assets" / "oficial.wav"
    entrada = {
        "id": "x-oficial",
        "fuera_de_git": True,
        "rutas": ["edge/assets/oficial.wav"],
        "sha256": "0" * 64,
        "duracion_s": 1.0,
        "sample_rate": 22050,
        "canales": 1,
    }
    (tmp_path / "shared" / "audio" / "MANIFEST.json").write_text(
        json.dumps({"audios": [entrada]}), encoding="utf-8"
    )
    assert v.verificar(tmp_path) == [], "ausente: es lo normal en CI y en un clon"

    wav.parent.mkdir(parents=True)
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * 22050)
    errores = v.verificar(tmp_path)
    assert any("sha256" in err for err in errores), "presente: se mide como cualquier otro"
    shutil.rmtree(wav.parent)
