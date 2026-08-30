"""La guarda de licencia de ffmpeg (T-3.10.b) — y sobre todo lo que NO deja pasar."""

from __future__ import annotations

import subprocess

import pytest
from takab_edge.cctv.ffmpeg import (
    BANDERAS_PROHIBIDAS,
    FfmpegNoApto,
    clasificar,
    verificar,
)

_LGPL = """ffmpeg version n7.1-lgpl Copyright (c) 2000-2024 the FFmpeg developers
  built with gcc 14 (GCC)
  configuration: --prefix=/ffbuild/prefix --disable-debug --enable-shared --enable-libvpx
  libavutil      59. 39.100
"""

_GPL_DEBIAN = """ffmpeg version 7.1.1-1+b1 Copyright (c) 2000-2025 the FFmpeg developers
  built with gcc 14 (Debian 14.2.0-19)
  configuration: --prefix=/usr --enable-gpl --enable-libx264 --enable-shared
"""

_NONFREE = """ffmpeg version N-126277 Copyright (c) 2000-2026 the FFmpeg developers
  configuration: --enable-gpl --enable-nonfree --enable-libfdk-aac
"""

_SIN_CONFIGURACION = """ffmpeg version 6.0 Copyright (c) 2000-2023 the FFmpeg developers
  libavutil      58.  2.100
"""


def _doble(salida: str):
    def interrogar(ruta: str, timeout_s: float) -> str:  # noqa: ARG001
        return salida

    return interrogar


# --------------------------------------------------------------- clasificar


def test_un_build_lgpl_se_reconoce_como_apto() -> None:
    assert clasificar(_LGPL) == ("lgpl", ())


def test_el_ffmpeg_de_debian_se_reconoce_como_gpl() -> None:
    """El camino natural (`apt install ffmpeg`) es justo el que no sirve, y por eso se prueba
    con la línea `configuration:` literal de Debian y no con una inventada."""
    licencia, banderas = clasificar(_GPL_DEBIAN)
    assert licencia == "gpl"
    assert banderas == ("--enable-gpl",)


def test_nonfree_pesa_mas_que_gpl_porque_ni_siquiera_es_redistribuible() -> None:
    licencia, banderas = clasificar(_NONFREE)
    assert licencia == "nonfree"
    assert set(banderas) == set(BANDERAS_PROHIBIDAS)


def test_un_binario_que_no_declara_su_configuracion_NO_es_apto() -> None:
    """«Desconocida» no es «bien». Un estado sin clasificar pide que alguien lo mire; tratarlo
    como apto convierte la guarda en decoración."""
    assert clasificar(_SIN_CONFIGURACION) == ("desconocida", ())


def test_disable_gpl_no_se_confunde_con_enable_gpl() -> None:
    """La frontera de palabra importa: sin ella, `--disable-gpl` casaría contra `-gpl`."""
    assert clasificar("  configuration: --prefix=/usr --disable-gpl --enable-shared")[0] == "lgpl"


# ----------------------------------------------------------------- verificar


def test_verificar_devuelve_la_version_de_un_build_apto() -> None:
    info = verificar("/opt/takab/bin/ffmpeg", interrogar=_doble(_LGPL))
    assert info.licencia == "lgpl"
    assert info.version == "n7.1-lgpl"
    assert info.ruta == "/opt/takab/bin/ffmpeg"


@pytest.mark.parametrize("salida", [_GPL_DEBIAN, _NONFREE, _SIN_CONFIGURACION])
def test_verificar_LANZA_ante_cualquier_build_no_apto(salida: str) -> None:
    with pytest.raises(FfmpegNoApto):
        verificar("/usr/bin/ffmpeg", interrogar=_doble(salida))


def test_el_mensaje_de_error_dice_como_desbloquearse() -> None:
    """Una guarda que bloquea sin decir cómo salir se acaba desactivando, que es el peor
    desenlace posible para ésta."""
    with pytest.raises(FfmpegNoApto) as exc:
        verificar("/usr/bin/ffmpeg", interrogar=_doble(_GPL_DEBIAN))
    mensaje = str(exc.value)
    assert "BtbN" in mensaje
    assert "--enable-gpl" in mensaje


def test_binario_ausente_es_FfmpegNoApto_y_no_FileNotFoundError() -> None:
    """Fail-closed uniforme: quien llama solo tiene que capturar una excepción, no tres."""

    def interrogar(ruta: str, timeout_s: float) -> str:  # noqa: ARG001
        raise FileNotFoundError(ruta)

    with pytest.raises(FfmpegNoApto, match="no hay ffmpeg"):
        verificar("/no/existe/ffmpeg", interrogar=interrogar)


def test_un_ffmpeg_colgado_tampoco_pasa() -> None:
    def interrogar(ruta: str, timeout_s: float) -> str:  # noqa: ARG001
        raise subprocess.TimeoutExpired(cmd=ruta, timeout=timeout_s)

    with pytest.raises(FfmpegNoApto, match="no respondió"):
        verificar("/opt/takab/bin/ffmpeg", interrogar=interrogar)
