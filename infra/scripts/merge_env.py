#!/usr/bin/env python3
"""Fusiona un `edge.env` generado con el que ya vive en el gabinete.

Por qué existe: `provision_gateway.sh` instalaba el archivo con `sudo tee`, que
sobrescribe el ARCHIVO ENTERO. El script solo genera tres claves (HMAC, endpoint
MQTT y PIN del panel), pero un gabinete en operación acumula muchas más — la
estación, el host de SeedLink, las rutas de los certificados, la calibración
MEDIDA del sensor, el nombre del sitio. Re-aprovisionar habría dejado el gabinete
sin sensor y sin calibración, y el runbook de alta de estación manda correr
justamente ese script: el arma estaba cargada dentro de un procedimiento.

Regla: este proceso NO decide qué configuración es correcta. Solo actualiza las
claves que el aprovisionamiento genera y deja TODO lo demás intacto, incluidos
comentarios y orden. Lo que no entiende, no lo toca.

Uso:
    merge_env.py --managed <archivo> [--existing <archivo>] --out <archivo>

Nunca escribe valores a stdout: el resumen (solo NOMBRES de clave) va a stderr,
porque estos archivos contienen la clave HMAC del gabinete y el PIN del panel.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys


def _key_of(line: str) -> str | None:
    """Nombre de la variable, o None si la línea no es una asignación.

    Comentarios y líneas en blanco devuelven None y por tanto se copian tal cual.
    """
    if "=" not in line:
        return None
    key = line.split("=", 1)[0].strip()
    if not key or key.startswith("#"):
        return None
    return key


def merge(managed_text: str, existing_text: str | None) -> tuple[str, list[str], list[str]]:
    """Devuelve (contenido_fusionado, claves_actualizadas, claves_conservadas)."""
    managed: dict[str, str] = {}
    for line in managed_text.splitlines():
        key = _key_of(line)
        if key is not None:
            managed[key] = line

    out: list[str] = []
    actualizadas: list[str] = []
    conservadas: list[str] = []

    if existing_text:
        for line in existing_text.splitlines():
            key = _key_of(line)
            if key is not None and key in managed:
                out.append(managed[key])
                actualizadas.append(key)
            else:
                out.append(line)
                if key is not None:
                    conservadas.append(key)

    # Las gestionadas que el archivo previo no tenía se añaden al final.
    for key, line in managed.items():
        if key not in actualizadas:
            out.append(line)
            actualizadas.append(key)

    return "\n".join(out) + "\n", actualizadas, conservadas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--managed", required=True, type=pathlib.Path)
    ap.add_argument("--existing", type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()

    existing_text = None
    if args.existing and args.existing.exists():
        existing_text = args.existing.read_text()

    contenido, actualizadas, conservadas = merge(args.managed.read_text(), existing_text)

    # 0600 desde el nacimiento: nunca existe una ventana en la que el archivo con
    # la clave HMAC y el PIN sea legible por otros.
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(contenido)

    print(f"claves actualizadas por el aprovisionamiento: {', '.join(actualizadas)}", file=sys.stderr)
    if conservadas:
        print(f"claves CONSERVADAS del gabinete ({len(conservadas)}): {', '.join(conservadas)}", file=sys.stderr)
    else:
        print("sin archivo previo: se escribe uno nuevo", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
