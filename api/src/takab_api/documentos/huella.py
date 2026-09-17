"""[T-7.42] La huella de CONTENIDO, en un solo sitio.

Identifica **qué afirma** un documento, no qué bytes tiene su archivo. El sha256
del archivo no cabe dentro de sí mismo; éste sí, y por eso es el que se imprime.

## Por qué vive aquí y no en `dictamen/model.py`

Porque ya no es del dictamen. Desde `T-7.42` el reporte de simulacro tiene la
suya, y la receta son cuatro líneas que, copiadas, darían **dos definiciones de
«huella de contenido»** que divergirían — y divergirían justo en el número que
los dos papeles mandan verificar.

`dictamen/model.py` la reexporta para no romper lo que ya la importaba de allí.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict


def para_la_huella(valor: object) -> str:
    """Cómo se serializa lo que `json` no sabe.

    [T-7.22] Los BYTES de una fotografía se sustituyen por su tamaño. No es una
    omisión: la huella de esa misma derivada (`FotoFila.sha256_impreso`) SÍ entra
    en el payload, así que dos informes con fotografías distintas siguen dando
    huellas distintas. Lo que se evita es arrastrar megabytes de `repr` por el
    serializador en CADA llamada, y ahora se llama dos veces por documento — la
    portada y el pie.
    """
    if isinstance(valor, bytes):
        return f"<{len(valor)} bytes>"
    return str(valor)


def content_sha256(modelo: object) -> str:
    """Huella del CONTENIDO de un modelo de documento.

    `sort_keys` para que el orden de los campos no la mueva, y `separators` sin
    espacios para que un cambio de formato de `json` tampoco.
    """
    payload = json.dumps(
        asdict(modelo),  # type: ignore[call-overload]
        sort_keys=True,
        separators=(",", ":"),
        default=para_la_huella,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
