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


def payload_de_la_huella(modelo: object) -> str:
    """Lo que se hashea, en un sitio donde se pueda MIRAR.

    [T-7.43] Existe porque la guarda que defendía esta receta —
    `test_la_huella_de_CONTENIDO_no_arrastra_los_bytes`— la **reconstruía a mano**
    con `asdict` para poder inspeccionar el payload, así que se habría quedado
    verde sobre cualquier regresión de la receta de verdad. Una guarda que mira
    una copia no vigila el original.

    `sort_keys` para que el orden de los campos no mueva la huella, y `separators`
    sin espacios para que un cambio de formato de `json` tampoco.

    ⚠️ `asdict()` y no `{f.name: getattr(...)}`: aquél aplana los dataclasses
    anidados, y éste los dejaría caer enteros en `default=para_la_huella`, que los
    serializaría con `str()` **arrastrando los bytes JPEG crudos**. Medido sobre un
    modelo con cuatro fotografías: 7 485 caracteres de payload contra 2 209 329.
    """
    return json.dumps(
        asdict(modelo),  # type: ignore[call-overload]
        sort_keys=True,
        separators=(",", ":"),
        default=para_la_huella,
    )


def content_sha256(modelo: object) -> str:
    """Huella del CONTENIDO de un modelo de documento."""
    return hashlib.sha256(payload_de_la_huella(modelo).encode()).hexdigest()
