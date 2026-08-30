"""Guarda de licencia de ffmpeg — la condición para que el CCTV arranque (T-3.10.b).

`D-24` fija que el vídeo se manipula con **FFmpeg LGPL invocado como subproceso, nunca
enlazado**, y **sin `--enable-gpl`** (que es lo que arrastra x264). Este módulo es lo que
convierte esa frase en algo que el programa comprueba en vez de algo que alguien recuerda.

POR QUÉ NO BASTA CON `apt install ffmpeg`
─────────────────────────────────────────
El paquete de Debian se compila **con** `--enable-gpl`. O sea que la forma más natural de
tener ffmpeg en el Pi es justamente la que no sirve, y el fallo sería silencioso: el binario
funciona igual de bien y nadie se entera hasta una auditoría de licencias. Por eso la
comprobación ocurre al arrancar y **cierra el paso**.

El build que sí sirve existe y es de descarga directa:
``ffmpeg-master-latest-linuxarm64-lgpl.tar.xz`` de https://github.com/BtbN/FFmpeg-Builds
(arm64, estático, compilación diaria) desplegado en ``/opt/takab/bin/ffmpeg``.

Funcionalmente no perdemos nada: este subsistema **no encodea nunca**. Solo remuxea con
``-c copy`` y extrae fotogramas ya comprimidos. x264 no le hace falta a nadie aquí.

FAIL-CLOSED, Y «DESCONOCIDA» NO ES «BIEN»
─────────────────────────────────────────
Si el binario no está, no responde, o no declara su línea ``configuration:``, la respuesta es
la misma que si declarase GPL: **no arranca**. Un estado sin clasificar pide que alguien lo
mire; tratarlo como apto convierte la guarda en decoración. Es la misma doctrina que el resto
del árbol: un fallback no puede ser ``ok``.
"""

from __future__ import annotations

import logging
import re
import subprocess  # noqa: S404 — invocación de ffmpeg por subproceso, que es el requisito
from dataclasses import dataclass

log = logging.getLogger("takab_edge.cctv")

#: Banderas de compilación que sacan a un build de LGPL. `--enable-gpl` arrastra GPL-2.0+
#: (x264 y compañía) y `--enable-nonfree` produce un binario que **no es redistribuible**.
BANDERAS_PROHIBIDAS: tuple[str, ...] = ("--enable-gpl", "--enable-nonfree")

#: Dónde conseguir uno válido. Va en el mensaje de error: una guarda que bloquea sin decir
#: cómo desbloquearse se acaba desactivando, que es el peor desenlace posible para ésta.
COMO_OBTENERLO = (
    "descarga ffmpeg-master-latest-linuxarm64-lgpl.tar.xz de "
    "https://github.com/BtbN/FFmpeg-Builds/releases y despliégalo en /opt/takab/bin/ffmpeg "
    "(el `ffmpeg` de Debian trae --enable-gpl y por eso no sirve)"
)

_RE_VERSION = re.compile(r"^ffmpeg version (\S+)", re.MULTILINE)
_RE_CONFIG = re.compile(r"^\s*configuration:(.*)$", re.MULTILINE)


class FfmpegNoApto(RuntimeError):
    """El ffmpeg encontrado no cumple la condición de licencia (o no se pudo interrogar)."""


@dataclass(frozen=True)
class FfmpegInfo:
    """Lo que sabemos del binario tras interrogarlo. `licencia` nunca es una suposición."""

    ruta: str
    version: str
    licencia: str  # "lgpl" — el único valor que deja arrancar


def clasificar(salida: str) -> tuple[str, tuple[str, ...]]:
    """Clasifica la salida de ``ffmpeg -version``.

    Devuelve ``(licencia, banderas_encontradas)``. La licencia es ``"lgpl"``,
    ``"gpl"``/``"nonfree"`` según lo que aparezca, o ``"desconocida"`` si el binario no
    declara su configuración — que **no** es un aprobado.
    """
    m = _RE_CONFIG.search(salida)
    if m is None:
        return "desconocida", ()
    configuracion = m.group(1)
    # Frontera de palabra por la derecha: `--enable-gpl` no debe casar dentro de
    # `--enable-gpl-something` inventado, ni `--enable-gpl` dentro de `--disable-gpl`.
    halladas = tuple(
        b
        for b in BANDERAS_PROHIBIDAS
        if re.search(rf"(?<![\w-]){re.escape(b)}(?![\w-])", configuracion)
    )
    if not halladas:
        return "lgpl", ()
    # `--enable-nonfree` es el peor de los dos: ni siquiera es redistribuible.
    licencia = "nonfree" if "--enable-nonfree" in halladas else "gpl"
    return licencia, halladas


def _interrogar(ruta: str, timeout_s: float) -> str:
    """Ejecuta ``ffmpeg -version`` y devuelve lo que escupa. **No traduce errores**: eso lo
    hace `verificar`, que es la guarda. Si la traducción viviera aquí, un doble inyectado en
    los tests se la saltaría entera — y la guarda quedaría probada por el camino que nunca
    corre en producción."""
    proc = subprocess.run(  # noqa: S603 — ruta de configuración, argumento fijo
        [ruta, "-version"],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    if proc.returncode != 0:
        raise FfmpegNoApto(f"{ruta!r} devolvió código {proc.returncode} a -version")
    return proc.stdout + proc.stderr


def verificar(ruta: str, *, timeout_s: float = 10.0, interrogar=_interrogar) -> FfmpegInfo:
    """Interroga el binario y **lanza** si no es LGPL. El happy path devuelve su versión.

    `interrogar` se inyecta por parámetro para que los tests no dependan de que haya un
    ffmpeg instalado — el árbol prueba con dobles inyectados, nunca parcheando.

    **Todo camino de fallo sale como `FfmpegNoApto`**, incluidos los del sistema operativo:
    quien llama tiene una sola excepción que capturar, y no puede olvidarse de una.
    """
    try:
        salida = interrogar(ruta, timeout_s)
    except FfmpegNoApto:
        raise
    except FileNotFoundError as exc:
        raise FfmpegNoApto(f"no hay ffmpeg en {ruta!r}: {COMO_OBTENERLO}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FfmpegNoApto(f"{ruta!r} no respondió a -version en {timeout_s:g}s") from exc
    except OSError as exc:
        raise FfmpegNoApto(f"no se pudo ejecutar {ruta!r}: {exc}") from exc

    licencia, banderas = clasificar(salida)
    if licencia != "lgpl":
        detalle = " ".join(banderas) if banderas else "no declara su línea `configuration:`"
        raise FfmpegNoApto(
            f"ffmpeg en {ruta!r} no es LGPL (licencia={licencia}: {detalle}). "
            f"El CCTV NO arranca con él: {COMO_OBTENERLO}"
        )
    m = _RE_VERSION.search(salida)
    version = m.group(1) if m else "desconocida"
    log.info("ffmpeg apto en %s (versión %s, LGPL)", ruta, version)
    return FfmpegInfo(ruta=ruta, version=version, licencia=licencia)
