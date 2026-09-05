"""Guarda de licencias del árbol (T-3.10.b · `D-24`).

Falla el build si aparece software copyleft fuerte —GPL o AGPL— en el árbol **transitivo**,
o si aparece por su nombre alguno de los paquetes explícitamente prohibidos.

POR QUÉ EXISTE
──────────────
TAKAB es un SaaS comercial cerrado. `ultralytics` —el camino más rápido y mejor documentado
para contar personas— es **AGPL-3.0**: usarlo obliga a abrir todo el código o a comprar una
licencia Enterprise. La decisión (`D-24`) fue no tocarlo en ningún entorno, ni siquiera para
comparar. Una decisión así, escrita solo en un documento, dura hasta que alguien tenga prisa.

POR QUÉ NO SE BUSCA LA CADENA «GPL» Y YA
────────────────────────────────────────
Porque produce falsos positivos, y un guard que grita en falso enseña a ignorarlo. Medido en
este mismo árbol: **matplotlib y scipy** vuelcan el TEXTO COMPLETO de su licencia en el campo
`License`, y ese texto menciona la GPL —para hablar de compatibilidad, no porque lo sean—.
Con un `grep GPL` los dos salían marcados.

Así que se clasifica por los **classifiers Trove**, que son vocabulario controlado
(`License :: OSI Approved :: …`), y solo se cae al campo `License` cuando no hay ninguno —y
ahí se exigen identificadores SPDX con frontera de palabra, no subcadenas.

LGPL NO ES MOTIVO DE FALLO, Y ESO TAMBIÉN ES UNA DECISIÓN
─────────────────────────────────────────────────────────
La LGPL permite el uso sin contagiar siempre que no se enlace estáticamente. Es justo lo que
hace el subsistema de CCTV con ffmpeg: **subproceso, nunca enlazado** (`D-24`). Marcarla como
prohibida haría fallar el build por el binario que la propia decisión eligió.

POR QUÉ `importlib.metadata` Y NO `pip-licenses`
────────────────────────────────────────────────
La ficha nombraba `pip-licenses`. Hace lo mismo, pero es **una dependencia más que auditar**
en la guarda que audita dependencias, y hay que instalarla en cada job. `importlib.metadata`
es de la biblioteca estándar, lee exactamente los mismos metadatos y ya está en todos los
entornos. El criterio —fallar ante GPL/AGPL en el árbol transitivo— se cumple igual.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from importlib.metadata import distributions
from pathlib import Path

#: Prohibidos POR NOMBRE, con su razón. No basta con la licencia: un paquete puede cambiar
#: de metadatos, o venir de un fork, y estos son casos concretos que ya se decidieron.
PROHIBIDOS: dict[str, str] = {
    "ultralytics": "AGPL-3.0 — incluye YOLOv8, YOLO11 y su implementación de RT-DETR",
    "deep-sort-realtime": "GPL-3.0",
    "deep_sort_realtime": "GPL-3.0",
    "yolov6": "GPL-3.0",
    "yolov7": "GPL-3.0",
    "super-gradients": "YOLO-NAS: pesos con licencia no comercial",
}

#: Nombres de licencia (en classifier Trove) que hacen fallar. `Lesser` NO está, y su
#: ausencia es la decisión: ver la cabecera.
COPYLEFT_FUERTE = (
    "GNU General Public License",
    "GNU Affero General Public License",
)

#: Identificadores SPDX, solo para paquetes SIN classifier. La frontera por la izquierda es
#: lo que impide que `LGPL-3.0` cuente como `GPL-3.0`.
_SPDX = re.compile(r"(?<![A-Za-z-])(A?GPL)-?[v]?[23]", re.IGNORECASE)

#: Excepciones, cada una con su razón escrita. Vacía a propósito: el día que haga falta una,
#: que cueste escribirla.
EXCEPCIONES: dict[str, str] = {}


def licencia_de(dist) -> tuple[str, str]:
    """`(veredicto, evidencia)` de una distribución instalada.

    Veredicto: ``"copyleft-fuerte"``, ``"permisiva"`` o ``"sin-declarar"``.
    """
    meta = dist.metadata
    clasificadores = [c for c in (meta.get_all("Classifier") or []) if c.startswith("License ::")]
    if clasificadores:
        for c in clasificadores:
            if any(nombre in c for nombre in COPYLEFT_FUERTE):
                return "copyleft-fuerte", c
        return "permisiva", "; ".join(clasificadores)

    # Sin classifier: solo entonces se mira el campo libre, y con SPDX estricto. Se recorta
    # porque algunos paquetes meten la licencia ENTERA aquí (matplotlib, scipy).
    declarada = (meta.get("License-Expression") or meta.get("License") or "").strip()
    corta = declarada.splitlines()[0][:120] if declarada else ""
    if _SPDX.search(corta):
        return "copyleft-fuerte", corta
    return ("permisiva", corta) if corta else ("sin-declarar", "")


def revisar_entorno() -> tuple[list[str], list[tuple[str, str, str]]]:
    """`(fallos, inventario)` del entorno Python activo."""
    fallos: list[str] = []
    inventario: list[tuple[str, str, str]] = []
    for dist in distributions():
        nombre = dist.metadata.get("Name") or "?"
        veredicto, evidencia = licencia_de(dist)
        inventario.append((nombre, dist.version or "?", evidencia or veredicto))
        if nombre.lower().replace("_", "-") in PROHIBIDOS:
            fallos.append(
                f"{nombre} está PROHIBIDO: {PROHIBIDOS[nombre.lower().replace('_', '-')]}"
            )
        elif veredicto == "copyleft-fuerte" and nombre not in EXCEPCIONES:
            fallos.append(f"{nombre} {dist.version} es copyleft fuerte ({evidencia})")
    return fallos, sorted(inventario)


def revisar_lock(lock: Path) -> list[str]:
    """Prohibidos por nombre sobre `uv.lock`. **Sin instalar nada.**

    El lock lista la resolución COMPLETA, así que esto ve también lo transitivo — y lo ve
    aunque el entorno de este job no tenga instalado ese extra.
    """
    if not lock.exists():
        return []
    datos = tomllib.loads(lock.read_text(encoding="utf-8"))
    fallos = []
    for paquete in datos.get("package", []):
        nombre = str(paquete.get("name", "")).lower().replace("_", "-")
        if nombre in PROHIBIDOS:
            fallos.append(f"{lock}: resuelve `{nombre}`, PROHIBIDO ({PROHIBIDOS[nombre]})")
    return fallos


def revisar_onnx(raiz: Path) -> list[str]:
    """Metadatos de los pesos `.onnx`.

    Un modelo no trae `setup.py`, así que **ningún escáner de paquetes lo ve**: un peso
    AGPL entraría al árbol sin que nada se quejara. Los `.onnx` son protobuf y los
    `metadata_props` viajan como texto plano dentro, así que basta con leer los bytes.
    """
    fallos = []
    for peso in raiz.rglob("*.onnx"):
        crudo = peso.read_bytes()
        for marca in (b"AGPL", b"agpl", b"GPL-3", b"GPLv3"):
            if marca in crudo and b"LGPL" not in crudo:
                fallos.append(f"{peso}: sus metadatos mencionan {marca.decode()}")
                break
    return fallos


def escribir_avisos(inventario: list[tuple[str, str, str]], destino: Path) -> None:
    """`THIRD_PARTY_NOTICES.txt`, **generado**. Escrito a mano envejecería en silencio."""
    lineas = [
        "TAKAB Ailert — software de terceros",
        "=" * 60,
        "GENERADO por ci/licencias.py. No editar a mano: se regenera en cada build.",
        "",
    ]
    lineas += [f"{n} {v}\n    {lic}" for n, v, lic in inventario]
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Guarda de licencias (T-3.10.b)")
    ap.add_argument("--lock", action="append", type=Path, default=[], help="uv.lock a revisar")
    ap.add_argument("--onnx-root", type=Path, help="raíz donde buscar pesos .onnx")
    ap.add_argument("--notices", type=Path, help="dónde escribir THIRD_PARTY_NOTICES.txt")
    ap.add_argument("--json", action="store_true", help="salida en JSON (para los tests)")
    args = ap.parse_args()

    fallos, inventario = revisar_entorno()
    for lock in args.lock:
        fallos += revisar_lock(lock)
    if args.onnx_root:
        fallos += revisar_onnx(args.onnx_root)
    if args.notices:
        escribir_avisos(inventario, args.notices)

    if args.json:
        print(json.dumps({"fallos": fallos, "revisadas": len(inventario)}, ensure_ascii=False))
    else:
        print(f"licencias: {len(inventario)} distribuciones revisadas")
        for f in fallos:
            print(f"  ✗ {f}", file=sys.stderr)
        if not fallos:
            print("  ✓ sin GPL/AGPL ni paquetes prohibidos")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
