"""Decodificar un JPEG sin meter una librería de imagen (T-3.12.d).

POR QUÉ FFMPEG Y NO PILLOW NI OPENCV
────────────────────────────────────
El detector necesita píxeles, y este paquete no tenía con qué obtenerlos: sus únicas
dependencias son `onnxruntime` y `numpy`, las dos del extra `onnx`. Las salidas obvias
—Pillow, `opencv-python`— añaden una dependencia grande al contenedor del Lambda para hacer
una cosa que **ya sabe hacer un binario que este proyecto obliga a tener**: ffmpeg.

Y hay una razón de licencia además de la de tamaño. `D-24` exige ffmpeg **LGPL invocado como
subproceso, nunca enlazado**; ese binario ya viaja al gabinete y ya va a viajar a la imagen
de la nube, porque sin él no se extrae un fotograma de un clip. Reutilizarlo para decodificar
un JPEG no añade superficie de licencia: usa la que ya se auditó.

`opencv-python` merece una nota aparte: sus ruedas empaquetan FFmpeg **compilado dentro**, y
la variante que traen no es la que este proyecto auditó. Meterlo sería introducir por la
puerta de atrás justo lo que `D-24` vigila por la de delante.

EL COSTE, MEDIDO Y ACEPTADO
───────────────────────────
Un subproceso por fotograma cuesta más que una llamada en proceso. Para el goteo —una
captura cada 30 s— es irrelevante. Para un clip de once minutos a 15 fps sería absurdo, y por
eso el clip **no se decodifica fotograma a fotograma por aquí**: ffmpeg extrae los fotogramas
que interesan en UNA sola invocación y este módulo solo toca JPEG sueltos.
"""

from __future__ import annotations

import subprocess  # noqa: S404 — ffmpeg por subproceso: es el requisito de licencia de D-24

#: Cabecera de un JPEG. Se comprueba antes de gastar un proceso: un fichero truncado del
#: goteo es un caso REAL —viaja por red desde una cámara— y arrancar ffmpeg para que falle
#: cuesta más que mirar dos bytes.
_SOI = b"\xff\xd8"


class ImagenIlegible(ValueError):
    """No se pudo decodificar. **Siempre esta excepción**, venga de donde venga el fallo."""


def dimensiones(jpeg: bytes) -> tuple[int, int]:
    """`(ancho, alto)` leídos del propio JPEG, sin decodificarlo entero.

    Se leen de la cabecera y no se asumen de la configuración: el perfil de la cámara puede
    cambiar sin que nadie actualice una fila, y un tamaño supuesto convierte las coordenadas
    del detector en ruido silencioso — la clase de fallo que este árbol persigue.
    """
    if not jpeg.startswith(_SOI):
        raise ImagenIlegible("no empieza por la cabecera de un JPEG")
    i = 2
    n = len(jpeg)
    while i + 9 < n:
        if jpeg[i] != 0xFF:
            i += 1
            continue
        marcador = jpeg[i + 1]
        # SOF0..SOF15 llevan el tamaño; se saltan SOF4 (DHT), SOF8 (JPG) y SOF12 (DAC),
        # que comparten rango y NO son marcos de inicio de fotograma.
        if 0xC0 <= marcador <= 0xCF and marcador not in (0xC4, 0xC8, 0xCC):
            alto = int.from_bytes(jpeg[i + 5 : i + 7], "big")
            ancho = int.from_bytes(jpeg[i + 7 : i + 9], "big")
            if ancho and alto:
                return ancho, alto
            raise ImagenIlegible("la cabecera declara un tamaño de cero")
        if marcador in (0xD8, 0x01) or 0xD0 <= marcador <= 0xD7:
            i += 2
            continue
        largo = int.from_bytes(jpeg[i + 2 : i + 4], "big")
        if largo < 2:
            raise ImagenIlegible("segmento con longitud imposible")
        i += 2 + largo
    raise ImagenIlegible("no se encontró el marcador de tamaño (¿JPEG truncado?)")


def a_rgb(jpeg: bytes, *, ffmpeg: str, timeout_s: float = 20.0):
    """JPEG → array `(alto, ancho, 3)` en RGB. Devuelve también sus dimensiones.

    El import de numpy es **perezoso**: el núcleo de este paquete tiene que seguir
    importándose sin el extra `onnx`, que es lo que permite probar el motor de métricas sin
    tocar un modelo ni un fotograma.
    """
    try:
        import numpy as np  # noqa: PLC0415 — perezoso a propósito (extra `onnx`)
    except ImportError as exc:  # pragma: no cover — depende del extra
        raise ImagenIlegible(
            "falta el extra `onnx` del analizador (numpy). `uv sync --extra onnx`"
        ) from exc

    ancho, alto = dimensiones(jpeg)
    try:
        proc = subprocess.run(  # noqa: S603 — comando construido por nosotros
            [
                ffmpeg,
                "-nostdin",
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ],
            input=jpeg,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ImagenIlegible(f"no se pudo ejecutar {ffmpeg!r}: {exc}") from exc

    if proc.returncode != 0:
        detalle = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ImagenIlegible(f"ffmpeg falló: {detalle[-1] if detalle else proc.returncode}")

    esperado = ancho * alto * 3
    if len(proc.stdout) != esperado:
        # Un tamaño distinto del declarado significa que la cabecera y los píxeles no
        # concuerdan. Reinterpretarlo daría una imagen desplazada —y un conteo sobre una
        # imagen desplazada es un número que nadie puede auditar.
        raise ImagenIlegible(
            f"ffmpeg devolvió {len(proc.stdout)} bytes y la cabecera declara {esperado} "
            f"({ancho}×{alto}×3)"
        )
    return np.frombuffer(proc.stdout, np.uint8).reshape(alto, ancho, 3), (ancho, alto)
