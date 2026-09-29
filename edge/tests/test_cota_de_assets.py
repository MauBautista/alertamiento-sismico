"""Cota de peso de los audios empaquetados en el edge (T-9.72).

Por qué: todo lo que vive en ``edge/takab_edge/audio/assets`` viaja ENTERO en cada
release del gabinete (``deploy/edge/deploy.sh`` hace ``rsync`` de ``edge/`` a una
release nueva por despliegue, y el Pi guarda varias) y además se versiona en el
repo, que NO tiene Git LFS: un WAV pesado se queda para siempre en la historia de
git y se copia a cada release. Un WAV de 22 050 Hz mono PCM16 son ~2,6 MB por
minuto; 6 MB por fichero (≈ 2 min) y 12 MB en total dan margen a lo que hay (sirena,
tono de prueba, simulacro, música de prueba) sin dejar pasar una grabación a 48 kHz
estéreo por descuido.

Y porque el ``rsync`` del despliegue tiene exclusiones, se comprueba también que
ninguna de ellas deja un asset fuera de la release.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

EDGE = Path(__file__).resolve().parents[1]
ASSETS = EDGE / "takab_edge" / "audio" / "assets"
DEPLOY = EDGE.parent / "deploy" / "edge" / "deploy.sh"

MB = 1024 * 1024
COTA_FICHERO = 6 * MB
COTA_TOTAL = 12 * MB


def _assets() -> list[Path]:
    return sorted(p for p in ASSETS.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def test_hay_assets_que_medir() -> None:
    # Sin esto, una carpeta movida dejaría la cota en verde sin medir nada.
    assert _assets(), f"no hay ficheros en {ASSETS.relative_to(EDGE.parent)}"


def test_cada_asset_pesa_6_mb_o_menos() -> None:
    pesados = [
        f"{p.relative_to(EDGE.parent)} pesa {p.stat().st_size / MB:.2f} MB "
        f"(cota {COTA_FICHERO / MB:.0f} MB)"
        for p in _assets()
        if p.stat().st_size > COTA_FICHERO
    ]
    assert pesados == [], "asset del edge demasiado pesado:\n" + "\n".join(pesados)


def test_los_assets_suman_12_mb_o_menos() -> None:
    tamanos = {p.relative_to(EDGE.parent).as_posix(): p.stat().st_size for p in _assets()}
    total = sum(tamanos.values())
    detalle = "\n".join(f"  {r}: {t / MB:.2f} MB" for r, t in sorted(tamanos.items()))
    assert total <= COTA_TOTAL, (
        f"los assets del edge suman {total / MB:.2f} MB (cota {COTA_TOTAL / MB:.0f} MB):\n{detalle}"
    )


def test_ninguna_exclusion_del_rsync_deja_un_asset_fuera_de_la_release() -> None:
    texto = DEPLOY.read_text(encoding="utf-8")
    bloque = re.search(r"rsync -az --delete \\\n(.*?)\"\$ROOT/edge/\"", texto, re.S)
    assert bloque, "no encuentro el rsync de edge/ en deploy/edge/deploy.sh"
    exclusiones = re.findall(r"--exclude '([^']+)'", bloque.group(1))
    atrapados = [
        f"{p.relative_to(EDGE.parent)} ← --exclude '{patron}'"
        for p in _assets()
        for patron in exclusiones
        if any(fnmatch.fnmatch(parte, patron) for parte in p.relative_to(EDGE).parts)
    ]
    assert atrapados == [], "asset que NO viajaría en la release:\n" + "\n".join(atrapados)
