"""Anillo, ventana del clip y poda (T-3.11).

Lo que se prueba aquí es la POLÍTICA, que es donde vive el requisito de Mauricio: graba
1 min antes y 10 después, y **todo lo demás se borra para no generar espacio**. Nada de
esto necesita un ffmpeg: los comandos se construyen y se comparan, no se ejecutan.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from takab_edge.cctv.recorder import (
    SEGMENTO_S,
    clips_a_soltar,
    cmd_anillo,
    cmd_captura,
    cmd_clip,
    cobertura,
    escribir_lista_concat,
    leer_anillo,
    nombre_de,
    podar_anillo,
    segmentos_de_la_ventana,
)

T0 = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)


def _sembrar(
    directorio: Path, cuantos: int, *, desde: datetime = T0, bytes_cada: int = 1024
) -> list[datetime]:
    """Escribe `cuantos` segmentos contiguos de SEGMENTO_S a partir de `desde`."""
    inicios = [desde + timedelta(seconds=i * SEGMENTO_S) for i in range(cuantos)]
    for ini in inicios:
        (directorio / nombre_de(ini)).write_bytes(b"\0" * bytes_cada)
    return inicios


# ------------------------------------------------------------------- anillo


def test_el_anillo_se_lee_ordenado_y_con_su_ventana(tmp_path: Path) -> None:
    _sembrar(tmp_path, 4)
    segs = leer_anillo(tmp_path)
    assert [s.inicio for s in segs] == sorted(s.inicio for s in segs)
    assert segs[0].fin == segs[1].inicio  # contiguos, sin hueco ni solape


def test_lo_que_no_es_un_segmento_se_ignora_en_silencio(tmp_path: Path) -> None:
    """En ese directorio también aterrizan el temporal de ffmpeg y los clips ya
    recortados. Confundir cualquiera con un segmento haría que la poda borre evidencia."""
    _sembrar(tmp_path, 2)
    (tmp_path / "clip-abc123.mp4").write_bytes(b"evidencia")
    (tmp_path / "seg-a-medias.mp4.tmp").write_bytes(b"parcial")
    (tmp_path / "seg-NO-ES-FECHA.mp4").write_bytes(b"basura")
    assert len(leer_anillo(tmp_path)) == 2
    assert (tmp_path / "clip-abc123.mp4").exists()


def test_el_anillo_se_ordena_por_NOMBRE_y_no_por_mtime(tmp_path: Path) -> None:
    """El mtime cambia al copiar y miente después de un rsync o un restore; el nombre no."""
    inicios = _sembrar(tmp_path, 3)
    # Invertir los mtime: el más nuevo por nombre pasa a ser el más viejo en disco.
    import os

    for i, ini in enumerate(inicios):
        os.utime(tmp_path / nombre_de(ini), (1_000_000 - i, 1_000_000 - i))
    assert [s.inicio for s in leer_anillo(tmp_path)] == inicios


# ------------------------------------------------------------- ventana del clip


def test_la_ventana_toma_exactamente_los_segmentos_que_aportan(tmp_path: Path) -> None:
    _sembrar(tmp_path, 10)  # T0 .. T0+100 s
    segs = leer_anillo(tmp_path)
    elegidos = segmentos_de_la_ventana(segs, T0 + timedelta(seconds=25), T0 + timedelta(seconds=45))
    # 20..30, 30..40, 40..50
    assert [s.inicio for s in elegidos] == [
        T0 + timedelta(seconds=20),
        T0 + timedelta(seconds=30),
        T0 + timedelta(seconds=40),
    ]


def test_un_segmento_que_TERMINA_donde_empieza_la_ventana_no_entra(tmp_path: Path) -> None:
    """No aporta un solo fotograma, y meterlo hincharía el clip con un preámbulo mudo."""
    _sembrar(tmp_path, 4)
    segs = leer_anillo(tmp_path)
    elegidos = segmentos_de_la_ventana(segs, T0 + timedelta(seconds=10), T0 + timedelta(seconds=20))
    assert [s.inicio for s in elegidos] == [T0 + timedelta(seconds=10)]


def test_la_cobertura_DELATA_un_clip_incompleto(tmp_path: Path) -> None:
    """Un clip que dice cubrir T−60 s sin cubrirlo es una mentira en un reporte."""
    _sembrar(tmp_path, 3)  # solo 30 s de anillo
    segs = leer_anillo(tmp_path)
    # Se piden 60 s pero el gabinete lleva 30 grabando.
    assert cobertura(segs, T0 - timedelta(seconds=30), T0 + timedelta(seconds=30)) == 0.5
    assert cobertura(segs, T0, T0 + timedelta(seconds=30)) == 1.0


# --------------------------------------------------------------------- poda


def test_la_poda_borra_lo_que_cae_fuera_del_anillo(tmp_path: Path) -> None:
    """El requisito literal: todo lo demás que grabe se puede ir borrando."""
    _sembrar(tmp_path, 30)  # 300 s
    segs = leer_anillo(tmp_path)
    ahora = T0 + timedelta(seconds=300)
    fuera = podar_anillo(segs, ahora=ahora, ring_s=180.0, cuota_bytes=10**9)
    # 300 − 180 = 120 s de historia sobran ⇒ 12 segmentos
    assert len(fuera) == 12
    assert all(s.fin <= ahora - timedelta(seconds=180) for s in fuera)


def test_la_cuota_muerde_aunque_la_edad_no(tmp_path: Path) -> None:
    """La edad es la política; la cuota es el suelo de seguridad. La microSD es de la que
    arranca el camino de vida."""
    _sembrar(tmp_path, 10, bytes_cada=1000)  # 10 KB vivos
    segs = leer_anillo(tmp_path)
    ahora = T0 + timedelta(seconds=100)
    fuera = podar_anillo(segs, ahora=ahora, ring_s=999.0, cuota_bytes=4500)
    assert len(fuera) == 6  # deja 4 KB ≤ 4500
    assert [s.inicio for s in fuera] == [s.inicio for s in segs[:6]]  # muere el más viejo


def test_sin_presion_la_poda_no_borra_nada(tmp_path: Path) -> None:
    _sembrar(tmp_path, 5)
    segs = leer_anillo(tmp_path)
    ahora = T0 + timedelta(seconds=50)
    assert podar_anillo(segs, ahora=ahora, ring_s=180.0, cuota_bytes=10**9) == []


def test_los_clips_pendientes_tienen_tope_y_muere_el_mas_viejo(tmp_path: Path) -> None:
    """Sin internet es exactamente cuando hay sismos, así que este caso no es hipotético."""
    pendientes = [tmp_path / f"clip-{i:03d}.mp4" for i in range(9)]
    sobran = clips_a_soltar(pendientes, maximo=6)
    assert [p.name for p in sobran] == ["clip-000.mp4", "clip-001.mp4", "clip-002.mp4"]
    assert clips_a_soltar(pendientes[:6], maximo=6) == []


# ----------------------------------------------------------------- comandos


def test_el_anillo_NO_decodifica_un_solo_fotograma() -> None:
    """`-c copy` es la diferencia entre costar un 3 % de un núcleo y costar el gabinete."""
    cmd = cmd_anillo("/opt/takab/bin/ffmpeg", "rtsp://cam/sub", Path("/var/lib/takab/cctv"))
    assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "copy"
    assert "-rtsp_transport" in cmd and cmd[cmd.index("-rtsp_transport") + 1] == "tcp"
    # Ni un flag de encoder: si alguien mete -c:v libx264 aquí, este test cae.
    assert not any(a.startswith("libx264") or a == "-crf" for a in cmd)


def test_el_recorte_del_clip_tampoco_recomprime() -> None:
    cmd = cmd_clip("/f", Path("/tmp/l.txt"), Path("/tmp/c.mp4"), recorte_s=3.5, duracion_s=660)
    assert cmd[cmd.index("-c") + 1] == "copy"
    assert cmd[cmd.index("-ss") + 1] == "3.5"
    assert cmd[cmd.index("-t") + 1] == "660"


def test_la_captura_decodifica_UN_frame_y_solo_uno() -> None:
    cmd = cmd_captura("/f", "rtsp://cam/sub", Path("/tmp/c.jpg"))
    assert cmd[cmd.index("-frames:v") + 1] == "1"


def test_la_lista_de_concat_cita_las_rutas(tmp_path: Path) -> None:
    """Un path con espacios rompe el demuxer `concat` sin comillas."""
    d = tmp_path / "un dir con espacios"
    d.mkdir()
    _sembrar(d, 2)
    lista = escribir_lista_concat(leer_anillo(d), tmp_path / "lista.txt")
    for linea in lista.read_text(encoding="utf-8").splitlines():
        assert linea.startswith("file '") and linea.endswith("'")


def test_nombre_de_es_UTC_aunque_le_den_otro_huso() -> None:
    """El gabinete puede cambiar de huso; el anillo se ordena por ese nombre."""
    from datetime import timezone

    cdmx = timezone(timedelta(hours=-6))
    assert nombre_de(datetime(2026, 8, 29, 6, 0, 0, tzinfo=cdmx)) == "seg-20260829T120000Z.mp4"


def test_segmento_desconocido_no_rompe_la_lectura(tmp_path: Path) -> None:
    (tmp_path / "seg-20261399T999999Z.mp4").write_bytes(b"fecha imposible")
    _sembrar(tmp_path, 1)
    assert len(leer_anillo(tmp_path)) == 1
