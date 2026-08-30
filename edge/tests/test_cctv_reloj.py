"""El reloj de la cámara y el sello que quema en la imagen (T-3.11).

La cámara del sitio llegó con el huso de fábrica —`GMT+08:00`— y el UTC correcto. Medido el
2026-08-30: el gabinete fechaba las 11:57 del día 30 y la foto decía **01:57 del día 31**.
Catorce horas y un día, quemados en un fotograma que va al dictamen con su `sha256`.

Lo que este control persigue no es el vídeo —el vídeo está bien— sino el **rótulo**, que es
lo único de la evidencia que no sale del gabinete y que nadie estaba mirando.
"""

from __future__ import annotations

from datetime import UTC, datetime

from takab_edge.cctv.onvif import RelojCamara, revisar_reloj

#: Lo que el gabinete tenía en el momento de la medición.
_AHORA = datetime(2026, 8, 30, 17, 57, 14, tzinfo=UTC)
_OFFSET_MX = -6 * 3600.0


def test_el_huso_de_fabrica_se_caza_y_se_dice_que_cambia_hasta_el_dia() -> None:
    """El caso real. El UTC es correcto: quien miente es el sello."""
    reloj = RelojCamara(utc_epoch=_AHORA.timestamp(), tz="GMT+08:00", ntp=False)
    hallazgos = revisar_reloj(reloj, _AHORA, _OFFSET_MX)

    sello = [h for h in hallazgos if "rotula" in h]
    assert len(sello) == 1
    assert "+14 h" in sello[0]  # +8 contra −6
    assert "puede cambiar hasta el día" in sello[0]


def test_un_reloj_bien_puesto_no_dice_nada() -> None:
    """Lista vacía es la única forma de decir «no hay nada que declarar»."""
    reloj = RelojCamara(utc_epoch=_AHORA.timestamp(), tz="GMT-06:00", ntp=True)
    assert revisar_reloj(reloj, _AHORA, _OFFSET_MX) == []


def test_el_modo_manual_se_declara_porque_va_a_derivar() -> None:
    reloj = RelojCamara(utc_epoch=_AHORA.timestamp(), tz="GMT-06:00", ntp=False)
    hallazgos = revisar_reloj(reloj, _AHORA, _OFFSET_MX)

    assert len(hallazgos) == 1
    assert "Manual" in hallazgos[0]
    assert "NTP" in hallazgos[0]


def test_un_utc_desviado_se_caza_aunque_el_huso_este_bien() -> None:
    """Si el UTC de la cámara está mal, su sello fecha mal el incidente entero."""
    reloj = RelojCamara(utc_epoch=_AHORA.timestamp() + 3600, tz="GMT-06:00", ntp=True)
    hallazgos = revisar_reloj(reloj, _AHORA, _OFFSET_MX)

    assert len(hallazgos) == 1
    assert "3600 s desviado" in hallazgos[0]


def test_medio_minuto_no_es_un_hallazgo() -> None:
    """La tolerancia existe para no gritar por lo que no cambia el sello."""
    reloj = RelojCamara(utc_epoch=_AHORA.timestamp() + 30, tz="GMT-06:00", ntp=True)
    assert revisar_reloj(reloj, _AHORA, _OFFSET_MX) == []


def test_un_huso_ilegible_se_declara_ilegible_y_no_se_da_por_bueno() -> None:
    """ONVIF admite husos POSIX con reglas de verano que no resolvemos. Callar sobre uno
    que no se sabe leer sería exactamente el fallback que dice `ok` sin serlo."""
    reloj = RelojCamara(utc_epoch=_AHORA.timestamp(), tz="CST6CDT,M4.1.0/2,M10.5.0/2", ntp=True)
    hallazgos = revisar_reloj(reloj, _AHORA, _OFFSET_MX)

    assert len(hallazgos) == 1
    assert "ilegible" in hallazgos[0]


def test_una_camara_que_no_dice_su_hora_tampoco_pasa_en_silencio() -> None:
    reloj = RelojCamara(utc_epoch=None, tz="GMT-06:00", ntp=True)
    hallazgos = revisar_reloj(reloj, _AHORA, _OFFSET_MX)

    assert len(hallazgos) == 1
    assert "no declara su hora UTC" in hallazgos[0]


def test_los_hallazgos_se_acumulan_no_se_quedan_en_el_primero() -> None:
    """Una cámara recién sacada de la caja tiene los tres a la vez, y arreglar uno solo
    porque fue el único que se dijo deja los otros dos vivos."""
    reloj = RelojCamara(utc_epoch=_AHORA.timestamp() + 999, tz="GMT+08:00", ntp=False)
    assert len(revisar_reloj(reloj, _AHORA, _OFFSET_MX)) == 3
