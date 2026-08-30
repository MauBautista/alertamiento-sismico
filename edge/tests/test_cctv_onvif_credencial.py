"""La credencial en lo que devuelve ONVIF — medido contra la cámara real (T-3.11).

POR QUÉ EXISTE ESTE FICHERO
───────────────────────────
`onvif.py` daba por hecho que «la URL que devuelve una cámara ONVIF es del tipo
``rtsp://usuario:tu-clave@host/stream``», y el simulador la devolvía así. Las dos cosas
eran la misma suposición escrita dos veces, así que las ocho pruebas del módulo pasaban
sin comprobar nada.

La cámara del sitio —una Dahua en `192.168.3.132`, ONVIF en el 80— la desmiente. Medido
el 2026-08-30:

* ``GetStreamUri``   → ``rtsp://192.168.3.132:554/cam/realmonitor?channel=1&subtype=1&…``
* ``GetSnapshotUri`` → ``http://192.168.3.132:80/onvifsnapshot/media_service/snapshot?…``

**Las dos vienen peladas**, y las dos exigen **Digest**: sin credencial el RTSP contesta
`401 Unauthorized` y la instantánea también (con Basic también, comprobado: solo pasa
Digest). Como `descubrir()` no inyectaba nada, el camino de descubrimiento entregaba a
ffmpeg URLs que ninguna cámara iba a servir: **cero clips y cero capturas**, y el fallo
solo aparecía con hardware delante.

Que `con_credenciales()` sea idempotente —si ya trae usuario, no lo pisa— es lo que
permite arreglarlo sin romper a la cámara que sí la trae embebida.
"""

from __future__ import annotations

import sys
import types

import pytest
from takab_edge.cctv.onvif import OnvifNoDisponible, descubrir

#: Lo que contestó la cámara real, copiado tal cual.
_RTSP_MAIN = "rtsp://192.168.3.132:554/cam/realmonitor?channel=1&subtype=0&unicast=true&proto=Onvif"
_RTSP_SUB = "rtsp://192.168.3.132:554/cam/realmonitor?channel=1&subtype=1&unicast=true&proto=Onvif"
_SNAP = "http://192.168.3.132:80/onvifsnapshot/media_service/snapshot?channel=1&subtype=0"


class _Uri:
    def __init__(self, uri: str) -> None:
        self.Uri = uri  # noqa: N815 — así se llama en el WSDL de ONVIF


class _Perfil:
    def __init__(self, token: str) -> None:
        self.token = token


class _Media:
    """Media service de mentira. Devuelve lo que devolvió la Dahua."""

    def __init__(self, uris: dict[str, str], *, snapshot: str | None) -> None:
        self._uris = uris
        self._snapshot = snapshot

    def GetProfiles(self):  # noqa: N802 — nombre del WSDL
        return [_Perfil("MediaProfile00000"), _Perfil("MediaProfile00001")]

    def GetStreamUri(self, req):  # noqa: N802 — nombre del WSDL
        return _Uri(self._uris[req["ProfileToken"]])

    def GetSnapshotUri(self, req):  # noqa: N802 — nombre del WSDL
        if self._snapshot is None:
            raise RuntimeError("esta cámara no ofrece GetSnapshotUri")
        return _Uri(self._snapshot)


@pytest.fixture
def camara_falsa(monkeypatch):
    """Instala un módulo `onvif` de mentira: el import de `descubrir()` es perezoso."""

    def _instalar(uris: dict[str, str], *, snapshot: str | None = _SNAP):
        class _ONVIFCamera:
            def __init__(self, host, puerto, usuario, clave):  # noqa: ARG002
                self.credencial = (usuario, clave)

            def create_media_service(self):
                return _Media(uris, snapshot=snapshot)

        modulo = types.ModuleType("onvif")
        modulo.ONVIFCamera = _ONVIFCamera
        monkeypatch.setitem(sys.modules, "onvif", modulo)

    return _instalar


_PELADAS = {"MediaProfile00000": _RTSP_MAIN, "MediaProfile00001": _RTSP_SUB}


def test_las_urls_peladas_de_la_camara_real_salen_con_credencial(camara_falsa) -> None:
    """El caso medido. Sin esto, ffmpeg recibe una URL que la cámara contesta con 401."""
    camara_falsa(_PELADAS)
    f = descubrir("192.168.3.132", 80, "admin", "no-es-un-secreto")

    assert f.rtsp_principal.startswith("rtsp://admin:no-es-un-secreto@192.168.3.132:554/")
    assert f.rtsp_substream.startswith("rtsp://admin:no-es-un-secreto@192.168.3.132:554/")
    assert f.snapshot is not None
    assert f.snapshot.startswith("http://admin:no-es-un-secreto@192.168.3.132:80/")


def test_la_query_de_la_url_sobrevive_a_la_inyeccion(camara_falsa) -> None:
    """`subtype` es lo que distingue el substream del principal: perderlo grabaría el
    stream grande y multiplicaría por ocho el disco, en silencio."""
    camara_falsa(_PELADAS)
    f = descubrir("192.168.3.132", 80, "admin", "no-es-un-secreto")

    assert "subtype=1" in f.rtsp_substream
    assert "subtype=0" in f.rtsp_principal
    assert "unicast=true&proto=Onvif" in f.rtsp_substream


def test_a_la_camara_que_ya_la_trae_embebida_no_se_le_pisa(camara_falsa) -> None:
    """El caso que suponía el módulo. Sigue siendo válido y no puede duplicarse."""
    con_credencial = {
        "MediaProfile00000": "rtsp://suyo:ejemplo@camara.local/main",
        "MediaProfile00001": "rtsp://suyo:ejemplo@camara.local/sub",
    }
    camara_falsa(con_credencial, snapshot="http://suyo:ejemplo@camara.local/snap.jpg")
    f = descubrir("camara.local", 80, "admin", "no-es-un-secreto")

    assert f.rtsp_substream == "rtsp://suyo:ejemplo@camara.local/sub"
    assert f.snapshot == "http://suyo:ejemplo@camara.local/snap.jpg"
    assert "no-es-un-secreto" not in f.rtsp_substream


def test_sin_instantanea_no_se_inventa_una(camara_falsa) -> None:
    """`GetSnapshotUri` es opcional en Profile S: que falte es un dato, no un error."""
    camara_falsa(_PELADAS, snapshot=None)
    f = descubrir("192.168.3.132", 80, "admin", "no-es-un-secreto")

    assert f.snapshot is None
    assert f.rtsp_substream.startswith("rtsp://admin:no-es-un-secreto@")


def test_la_credencial_no_aparece_en_el_log(camara_falsa, caplog) -> None:
    """La línea de `descubrir()` registra la URL del substream: es la que más cerca está
    de filtrar la clave de las cámaras del cliente al journal."""
    camara_falsa(_PELADAS)
    with caplog.at_level("INFO", logger="takab_edge.cctv"):
        descubrir("192.168.3.132", 80, "admin", "no-es-un-secreto")

    assert caplog.text  # la traza existe: no estamos comprobando el vacío
    assert "no-es-un-secreto" not in caplog.text
    assert "***@192.168.3.132" in caplog.text


def test_una_camara_sin_perfiles_sigue_siendo_OnvifNoDisponible(camara_falsa) -> None:
    camara_falsa({})

    class _Vacio(_Media):
        def GetProfiles(self):  # noqa: N802
            return []

    modulo = sys.modules["onvif"]
    modulo.ONVIFCamera.create_media_service = lambda self: _Vacio({}, snapshot=None)  # noqa: ARG005
    with pytest.raises(OnvifNoDisponible, match="ni un solo perfil|un solo perfil"):
        descubrir("192.168.3.132", 80, "admin", "no-es-un-secreto")
