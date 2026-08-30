"""Las cuatro comprobaciones de arranque de `takab-cctv` (T-3.11).

Las cuatro fallan *hacia no arrancar*. Un CCTV que no arranca deja un reporte sin vídeo;
uno que arranca mal deja imágenes de personas donde no debían estar.
"""

from __future__ import annotations

import pytest
from takab_edge.cctv.__main__ import ArranqueRechazado, _comprobar, _fuentes_de
from takab_edge.cctv.onvif import sin_credenciales
from takab_edge.config.settings import CctvConfig, EdgeSettings


def _settings(**cctv) -> EdgeSettings:
    return EdgeSettings(cctv=CctvConfig(**cctv))


def test_de_fabrica_el_cctv_esta_apagado_y_lo_dice_citando_la_decision() -> None:
    with pytest.raises(ArranqueRechazado, match="D-25"):
        _comprobar(_settings())


def test_el_conteo_local_esta_APLAZADO_y_el_proceso_se_NIEGA_a_arrancar_con_el() -> None:
    """Una perilla que no hace nada es peor que ninguna: alguien la enciende y cree que
    cuenta. Aquí la negativa es la mitad que importa."""
    with pytest.raises(ArranqueRechazado) as exc:
        _comprobar(_settings(enabled=True, conteo_local=True, host="192.168.3.50"))
    mensaje = str(exc.value)
    assert "D-24" in mensaje
    # La razón no puede ser «no cabe»: con 8 GB cabe. Es que no se puede MEDIR todavía.
    assert "no se puede medir" in mensaje
    assert "8 GB" in mensaje


def test_con_el_cctv_encendido_y_el_conteo_apagado_la_comprobacion_pasa() -> None:
    _comprobar(_settings(enabled=True, host="192.168.3.50"))  # no lanza


def test_sin_camara_declarada_no_arranca_y_dice_las_dos_formas_de_declararla() -> None:
    with pytest.raises(ArranqueRechazado) as exc:
        _fuentes_de(CctvConfig(enabled=True), "u", "c")
    assert "RTSP_URL" in str(exc.value)
    assert "HOST" in str(exc.value)


def test_la_url_declarada_gana_sobre_onvif_y_recibe_la_credencial_en_memoria() -> None:
    """Si alguien la escribió es porque el descubrimiento no le sirvió; reintentarlo solo
    añade una espera y un fallo."""
    cfg = CctvConfig(enabled=True, host="192.168.3.50", rtsp_url="rtsp://192.168.3.50/sub")
    f = _fuentes_de(cfg, "takab", "no-es-un-secreto")  # no toca la red: no llama a descubrir()
    assert f.rtsp_substream == "rtsp://takab:no-es-un-secreto@192.168.3.50/sub"
    assert f.snapshot is None  # sin ONVIF no hay forma de saber si la ofrece


def test_la_url_declarada_en_config_puede_persistirse_porque_no_lleva_secreto() -> None:
    """Es lo que la hace apta para el config sync firmado."""
    cfg = CctvConfig(rtsp_url="rtsp://192.168.3.50/sub")
    assert "@" not in cfg.rtsp_url
    assert "no-es-un-secreto" not in cfg.model_dump_json()


@pytest.mark.parametrize(
    ("url", "esperado"),
    [
        ("rtsp://takab:no-es-un-secreto@192.168.3.50/sub", "rtsp://***@192.168.3.50/sub"),
        ("rtsp://192.168.3.50:554/sub", "rtsp://192.168.3.50:554/sub"),
        ("rtsp://u:p@cam.local:8554/x?y=1", "rtsp://***@cam.local:8554/x?y=1"),
        ("no-es-una-url", "<url ilegible>"),
    ],
)
def test_ninguna_url_llega_a_un_log_con_la_contrasena_dentro(url: str, esperado: str) -> None:
    """Un `log.info("grabando %s", url)` deja la clave de las cámaras del cliente en el
    journal, en el `journalctl` que alguien pega en un ticket, y en cualquier diagnóstico.
    Ningún detector de PII del proyecto reconoce esa cadena."""
    limpia = sin_credenciales(url)
    assert limpia == esperado
    assert "no-es-un-secreto" not in limpia and ":p@" not in limpia


def test_un_perfil_desconocido_no_impide_arrancar() -> None:
    """Degrada a substream: config pura no puede tirar el gabinete por un campo de cámara."""
    _comprobar(_settings(enabled=True, host="h", perfil="4k-ultra"))  # no lanza
