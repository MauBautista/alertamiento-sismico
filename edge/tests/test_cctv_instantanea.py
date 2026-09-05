"""El goteo por HTTP y su respaldo (T-3.11 · hallazgo de la cámara real).

Medido el 2026-08-30 con ffmpeg LGPL de verdad contra la cámara del sitio: pasarle a ffmpeg
la URI de instantánea da **401**, y el RTSP va bien. La causa está aislada en cruz y es el
**orden de los parámetros** del Digest —`nc` antes de `cnonce` pasa, al revés no—, que es
justo el que ffmpeg manda al revés.

Lo que eso significaba en producción: `_gotear` **prefiere** la instantánea, así que en esta
cámara habrían fallado TODAS las capturas. El clip habría salido bien y el **reingreso no se
habría fechado nunca**, que es lo único que el goteo puede fechar.
"""

from __future__ import annotations

from pathlib import Path

from takab_edge.cctv.instantanea import bajar

_JPEG = b"\xff\xd8" + b"\x00" * 4000  # cabecera real + relleno para pasar el mínimo


def test_baja_el_jpeg_y_lo_escribe(tmp_path: Path) -> None:
    destino = tmp_path / "still.jpg"
    assert bajar("http://u:c@camara/snap.jpg", destino, abrir=lambda *_: _JPEG) is True
    assert destino.read_bytes() == _JPEG


def test_la_credencial_se_saca_de_la_url_y_no_viaja_en_la_ruta(tmp_path: Path) -> None:
    """urllib no lee el `userinfo` de la URL: hay que dárselo al gestor de contraseñas."""
    vistos: dict[str, str] = {}

    def espia(url, usuario, clave, _timeout):
        vistos.update(url=url, usuario=usuario, clave=clave)
        return _JPEG

    bajar("http://admin:no-es-un-secreto@camara:80/snap.jpg?c=1", tmp_path / "s.jpg", abrir=espia)

    assert vistos["usuario"] == "admin"
    assert vistos["clave"] == "no-es-un-secreto"
    assert vistos["url"] == "http://camara:80/snap.jpg?c=1"
    assert "@" not in vistos["url"]


def test_una_pagina_de_error_con_200_no_cuenta_como_captura(tmp_path: Path) -> None:
    """El caso que más engaña: hay respuesta, hay fichero, y no es una foto."""
    destino = tmp_path / "still.jpg"
    error = b"<html>401 Unauthorized</html>"
    assert bajar("http://u:c@camara/snap.jpg", destino, abrir=lambda *_: error) is False
    assert not destino.exists()


def test_algo_que_pesa_pero_no_es_jpeg_tampoco_pasa(tmp_path: Path) -> None:
    destino = tmp_path / "still.jpg"
    assert bajar("http://u:c@camara/s.jpg", destino, abrir=lambda *_: b"PNG" * 2000) is False
    assert not destino.exists()


def test_un_fallo_de_red_devuelve_False_y_no_lanza(tmp_path: Path) -> None:
    """El goteo son horas de fotos: un fallo puntual no puede tumbar el proceso."""

    def revienta(*_):
        raise OSError("la cámara no contesta")

    assert bajar("http://u:c@camara/s.jpg", tmp_path / "s.jpg", abrir=revienta) is False


def test_la_credencial_no_aparece_cuando_falla(tmp_path: Path, caplog) -> None:
    def revienta(*_):
        raise OSError("timeout")

    with caplog.at_level("WARNING", logger="takab_edge.cctv"):
        bajar("http://admin:no-es-un-secreto@camara/s.jpg", tmp_path / "s.jpg", abrir=revienta)

    assert caplog.text
    assert "no-es-un-secreto" not in caplog.text
    assert "***@camara" in caplog.text
