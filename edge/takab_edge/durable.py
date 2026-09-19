"""Escribir en disco algo que tenga que seguir ahí después de un corte de luz.

**Por qué existe este módulo, medido y no supuesto** (`T-7.59`): el 2026-09-19 se
desconectó el Pi del gabinete real para moverlo de sitio y, al volver a
encenderlo, `episodio.json` reapareció **vacío**:

    json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)

`char 0` es fichero de cero bytes, no fichero a medias. Y el código que lo
escribía llevaba encima el comentario «rename atómico: nunca a medio escribir».

## Atomicidad y durabilidad no son lo mismo, y el rename sólo da la primera

`os.replace()` garantiza que **ningún lector verá el fichero a medias**: o ve el
contenido viejo entero, o el nuevo entero. Eso protege de un proceso que muere.

No protege de un corte de corriente. El rename toca **metadatos** del directorio
y los datos del fichero van por otro camino; el sistema de ficheros puede
confirmar el primero antes de haber bajado los segundos, y al volver la luz el
nombre nuevo apunta a bloques que nunca se escribieron. Cero bytes.

Para que sobreviva al corte hacen falta **dos** `fsync` y en este orden:

1. del **fichero temporal**, antes del rename — así los datos están en el disco
   cuando el nombre empiece a apuntarlos;
2. del **directorio**, después del rename — así la entrada nueva está en el
   disco, y no sólo en la caché del sistema.

## ⚠️ Esto NO se pone en todas partes

Un `fsync` es I/O bloqueante de milisegundos, y en este gabinete hay caminos
donde eso no se puede pagar: la regla de oro 1 dice que el camino crítico de
activación es determinista y no depende de un disco lento. Un fichero que se
puede reconstruir —una caché, un último valor conocido— **no debe** usar esto:
sería coste sin beneficio.

El criterio, que es lo único estable: **se usa donde el fichero promete
sobrevivir a un reinicio; no se usa donde el fichero se puede reconstruir.**
Quién lo llama hoy lo dice `grep`, y por eso no se enumera aquí — una lista de
llamadores escrita a mano envejece sin que nadie la mire, que es el mismo
defecto que este módulo viene a cerrar en otra forma.
"""

from __future__ import annotations

import os
from pathlib import Path


def fsync_dir(directorio: Path) -> None:
    """Baja al disco la ENTRADA del directorio, que es lo que el rename cambió.

    Sin esto, el fichero puede estar entero en el disco y aun así no existir
    después del corte: el nombre vivía sólo en la caché.
    """
    fd = os.open(directorio, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def escribir_durable(destino: Path, contenido: str, *, encoding: str = "utf-8") -> None:
    """Deja `contenido` en `destino` de forma que sobreviva a un corte de luz.

    Atómica para quien lea (nadie ve un fichero a medias) **y** durable ante el
    corte (los datos y el nombre están los dos en el disco al retornar).

    No captura nada: quien llame decide qué hacer si el disco está lleno o de
    sólo lectura. En el gabinete la respuesta suele ser «seguir sin persistir»,
    porque un disco lleno no puede impedir detectar un sismo — pero ésa es una
    decisión del que llama, no de esta función.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    # ⚠️ `suffix + ".tmp"` y no `with_suffix(".tmp")`: el primero da `x.json.tmp`
    # y el segundo `x.tmp`. `backfill` barre su directorio con `*.json` y manda a
    # cuarentena lo que no parsea, así que un temporal que casara con ese glob
    # sería evidencia legítima apartada. Lo fija `test_durable.py`.
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    with open(tmp, "w", encoding=encoding) as fh:
        fh.write(contenido)
        fh.flush()
        os.fsync(fh.fileno())  # (1) los DATOS, antes de que el nombre los apunte
    tmp.replace(destino)  # rename atómico: nadie lee un fichero a medias
    fsync_dir(destino.parent)  # (2) el NOMBRE, que el rename acaba de crear
