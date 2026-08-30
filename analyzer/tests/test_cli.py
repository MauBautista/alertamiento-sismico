"""El pipeline de punta a punta, sin modelo y sin red (T-3.12).

Criterio literal de la ficha: «corre en local con un backend falso; cero descargas de pesos
en CI». Esto lo ejerce entero — nombres de fichero del gabinete, lectura, detección, curva,
métricas y elección de capturas — sobre un directorio de JPEG como el que deja el goteo.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from takab_cctv.__main__ import FfmpegNoApto, fotogramas_del_goteo, main, verificar_ffmpeg
from takab_cctv.aforo import a_muestras, serie_de
from takab_cctv.capturas import elegir
from takab_cctv.detector import Caja, DetectorFalso
from takab_cctv.metricas import Sacudida, calcular

T0 = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
EVENTO = "ev-aaa"


def _goteo(carpeta: Path, cuantos: int, *, cada_s: int = 30) -> None:
    """Escribe capturas con el nombre EXACTO que pone `takab-cctv`."""
    for i in range(cuantos):
        ts = T0 + timedelta(seconds=i * cada_s)
        nombre = f"still-{ts.strftime('%Y%m%dT%H%M%SZ')}-{EVENTO}.jpg"
        (carpeta / nombre).write_bytes(b"\xff\xd8\xff\xe0jpeg-falso")


# ------------------------------------------------------ lectura del goteo


def test_el_instante_sale_del_NOMBRE_y_no_del_mtime(tmp_path: Path) -> None:
    """El mtime cambia al copiar y miente después de un `aws s3 sync`. Aquí lo que se está
    fechando es el reingreso de un edificio."""
    import os

    _goteo(tmp_path, 3)
    for jpg in tmp_path.glob("*.jpg"):  # mtimes al revés
        os.utime(jpg, (1_000_000, 1_000_000))
    fotogramas = fotogramas_del_goteo(tmp_path)
    assert [f[0] for f in fotogramas] == [
        T0,
        T0 + timedelta(seconds=30),
        T0 + timedelta(seconds=60),
    ]


def test_lo_que_no_es_una_captura_se_ignora(tmp_path: Path) -> None:
    _goteo(tmp_path, 2)
    (tmp_path / "clip-20260829T120000Z-ev-aaa.mp4").write_bytes(b"video")
    (tmp_path / "still-nofecha-ev.jpg").write_bytes(b"basura")
    assert len(fotogramas_del_goteo(tmp_path)) == 2


# --------------------------------------------------- el pipeline completo


def test_el_pipeline_ENTERO_produce_la_analitica_sin_modelo_y_sin_red(tmp_path: Path) -> None:
    """De ficheros en disco a `t90`, veredicto de reingreso y las cuatro capturas."""
    _goteo(tmp_path, 13, cada_s=10)

    # Un guion que dibuja una evacuación: sube, hace pico, se vacía. Las cajas van
    # SEPARADAS 60 px para que NMS no las colapse — si se solaparan, el conteo sería 1.
    def cajas(n: int) -> list[Caja]:
        return [Caja(400 + i * 60, 400, 440 + i * 60, 500, 0.9) for i in range(n)]

    guion = [cajas(n) for n in (0, 2, 8, 12, 12, 11, 9, 3, 2, 1, 1, 0, 0)]

    fotogramas = fotogramas_del_goteo(tmp_path)
    curva = serie_de(fotogramas, DetectorFalso(guion), ancho=1920, alto=1080)
    muestras = a_muestras(curva)
    evac = calcular(
        muestras,
        t0=T0,
        t_dictamen=T0 + timedelta(seconds=300),
        checkins=14,
        sacudida=Sacudida(max_pga_g=0.187, max_pgv_cms=12.4),
    )

    assert evac.peak_n == 12
    assert evac.t90_s is not None
    assert "PGA 0.187 g" in evac.correlacion() and "salió en" in evac.correlacion()
    assert "MÁS en el pase de lista" in evac.discrepancia.lectura
    # El reingreso empieza antes de que se firme el dictamen: hallazgo, no número.
    assert evac.reingreso_antes_del_dictamen
    assert "sin certificación de habitabilidad" in evac.veredicto_reingreso()

    papeles = {e.papel: e for e in elegir(muestras, evac, t0=T0)}
    assert papeles["peak"].ts == evac.peak_at
    assert papeles["reentry"].ts == evac.reentry_start_at
    # Sin pre-roll en el goteo, la foto del «antes» se declara ausente en vez de inventarse.
    assert papeles["pre"].ts is None


def test_el_CLI_corre_de_punta_a_punta_y_escupe_JSON(tmp_path: Path, capsys) -> None:
    """Con `--stills` no hace falta ffmpeg: es lo que permite ejercerlo en una máquina que
    no lo tenga, y es además el modo con el que se fecha el reingreso."""
    _goteo(tmp_path, 5)
    codigo = main(
        ["--stills", str(tmp_path), "--t0", "2026-08-29T12:00:00Z", "--detector", "falso"]
    )
    assert codigo == 0
    salida = json.loads(capsys.readouterr().out)
    assert salida["muestras"] == 5
    assert salida["detector"] == "falso"
    # El backend falso no ve a nadie, y el motor lo DICE en vez de devolver ceros.
    assert "SIN EVACUACIÓN" in " ".join(salida["evacuacion"]["notas"])
    assert [c["papel"] for c in salida["capturas"]] == ["pre", "egress", "peak", "reentry"]


def test_el_CLI_exige_una_fuente_y_solo_una(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--t0", "2026-08-29T12:00:00Z"])
    with pytest.raises(SystemExit):
        main(["--clip", "x.mp4", "--stills", str(tmp_path), "--t0", "2026-08-29T12:00:00Z"])


def test_un_detector_desconocido_no_se_adivina() -> None:
    with pytest.raises(SystemExit):
        main(["--stills", ".", "--t0", "2026-08-29T12:00:00Z", "--detector", "magia"])


# ------------------------------------------------------- ffmpeg, otra vez


def test_el_analizador_tambien_rechaza_un_ffmpeg_GPL(tmp_path: Path) -> None:
    """La comprobación está duplicada respecto al gabinete a propósito —son dos paquetes que
    no pueden importarse— y lo que NO puede pasar es que solo una de las dos compruebe."""
    falso = tmp_path / "ffmpeg"
    falso.write_text(
        "#!/bin/sh\n"
        "echo 'ffmpeg version 7.1'\n"
        "echo '  configuration: --enable-gpl --enable-libx264'\n"
    )
    falso.chmod(0o755)
    with pytest.raises(FfmpegNoApto, match="enable-gpl"):
        verificar_ffmpeg(str(falso))


def test_un_ffmpeg_lgpl_pasa(tmp_path: Path) -> None:
    bueno = tmp_path / "ffmpeg"
    bueno.write_text(
        "#!/bin/sh\n"
        "echo 'ffmpeg version n7.1-lgpl'\n"
        "echo '  configuration: --disable-gpl --enable-shared'\n"
    )
    bueno.chmod(0o755)
    verificar_ffmpeg(str(bueno))  # no lanza


def test_un_ffmpeg_que_no_declara_su_configuracion_TAMPOCO_pasa(tmp_path: Path) -> None:
    mudo = tmp_path / "ffmpeg"
    mudo.write_text("#!/bin/sh\necho 'ffmpeg version 6.0'\n")
    mudo.chmod(0o755)
    with pytest.raises(FfmpegNoApto):
        verificar_ffmpeg(str(mudo))
