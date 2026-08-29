"""Descubrimiento ONVIF de la cámara y manejo seguro de su URL (T-3.11).

QUÉ SE LE PIDE A LA CÁMARA, Y POR QUÉ TAN POCO
──────────────────────────────────────────────
Dos cosas y nada más: la **URL RTSP** de un perfil (Profile S) y, si la ofrece, la **URI de
instantánea**. No se le pide PTZ, ni eventos, ni analítica de la propia cámara: cada
capacidad que se usa es una capacidad que puede colgarse, y este proceso tiene prohibido
por `B.1` colgarse de forma que se note fuera.

La instantánea importa más de lo que parece. Si la cámara la ofrece, el goteo de capturas
es un `GET` de un JPEG ya codificado: **cero decodificación de vídeo**. Si no la ofrece,
hay que sacar un fotograma del RTSP, que sí decodifica. Misma foto, coste muy distinto.

LA CREDENCIAL NO SE GUARDA Y NO SE REGISTRA
───────────────────────────────────────────
La URL que devuelve una cámara ONVIF es del tipo ``rtsp://usuario:clave@host/stream``. Eso
significa que:

* **no puede persistirse** —ni en la tabla `cameras`, ni en el config sync, ni en un
  fichero de estado—, y por eso las credenciales viven solo en el entorno del proceso; y
* **no puede registrarse**, que es la parte que se olvida. Un `log.info("grabando %s", url)`
  deja la contraseña de las cámaras del cliente en el journal del gabinete, en la salida de
  `journalctl` que alguien pega en un ticket, y en cualquier envío de diagnóstico. Ningún
  detector de PII del proyecto reconoce esa cadena: es una fuga que **ningún censo ve**.

Por eso todo lo que este módulo devuelve pasa por :func:`sin_credenciales` antes de tocar un
log, y hay un test que lo fija.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

log = logging.getLogger("takab_edge.cctv")


class OnvifNoDisponible(RuntimeError):
    """No se pudo hablar con la cámara (o falta el extra `cctv`). Siempre esta excepción."""


@dataclass(frozen=True)
class Fuentes:
    """De dónde sale el vídeo y de dónde las capturas. **Contiene credenciales.**"""

    rtsp_principal: str
    rtsp_substream: str
    snapshot: str | None = None

    def rtsp(self, perfil: str) -> str:
        """La URL del perfil pedido. `substream` es el default de `CctvConfig` a propósito."""
        return self.rtsp_principal if perfil == "main" else self.rtsp_substream


def sin_credenciales(url: str) -> str:
    """La misma URL con el usuario y la clave sustituidos. **Úsala en TODO log.**

    Devuelve la cadena tal cual si no se puede analizar: una URL rara no es motivo para
    perder la traza, pero tampoco para imprimirla entera — por eso lo ilegible se reduce a
    un marcador en vez de pasar de largo.
    """
    try:
        partes = urlsplit(url)
    except ValueError:
        return "<url ilegible>"
    if not partes.hostname:
        return "<url ilegible>"
    puerto = f":{partes.port}" if partes.port else ""
    autoridad = (
        f"***@{partes.hostname}{puerto}" if partes.username else f"{partes.hostname}{puerto}"
    )
    return urlunsplit((partes.scheme, autoridad, partes.path, partes.query, partes.fragment))


def con_credenciales(url: str, usuario: str, clave: str) -> str:
    """Inyecta la credencial en una URL que no la trae. En memoria y en el momento de usar.

    Existe para el caso normal: la cámara se declara en config como
    ``rtsp://192.168.3.50/sub`` —sin secreto, apta para persistirse y sincronizarse— y la
    credencial se añade justo antes de dársela a ffmpeg.
    """
    if not usuario:
        return url
    partes = urlsplit(url)
    if partes.username:  # ya la traía: no se pisa
        return url
    puerto = f":{partes.port}" if partes.port else ""
    autoridad = f"{usuario}:{clave}@{partes.hostname or ''}{puerto}"
    return urlunsplit((partes.scheme, autoridad, partes.path, partes.query, partes.fragment))


def descubrir(
    host: str,
    puerto: int,
    usuario: str,
    clave: str,
    *,
    timeout_s: float = 10.0,
) -> Fuentes:
    """Interroga la cámara por ONVIF y devuelve sus fuentes.

    El import es **perezoso** y vive dentro de la función: `onvif-zeep` va en el extra
    `cctv`, que no se instala ni en CI ni en el gabinete mientras el CCTV esté apagado. Un
    import arriba del fichero rompería la instalación del núcleo, que tiene que seguir
    funcionando en x86-64 sin cámara — misma disciplina que `AwsIotMqttTransport` y `lora`.
    """
    try:
        from onvif import ONVIFCamera  # noqa: PLC0415 — perezoso a propósito (extra `cctv`)
    except ImportError as exc:  # pragma: no cover — depende del extra
        raise OnvifNoDisponible(
            "falta el extra `cctv` (onvif-zeep). Instálalo con `uv sync --extra cctv` "
            "en la máquina que corre takab-cctv"
        ) from exc

    try:
        camara = ONVIFCamera(host, puerto, usuario, clave)
        media = camara.create_media_service()
        perfiles = media.GetProfiles()
        if not perfiles:
            raise OnvifNoDisponible(f"la cámara {host}:{puerto} no declara un solo perfil")
        # Por convención de Profile S el primero es el principal y el último el de menor
        # resolución. Si solo hay uno, los dos apuntan al mismo sitio: es correcto, y mejor
        # que inventar un substream que no existe.
        principal, substream = perfiles[0], perfiles[-1]
        urls = [
            media.GetStreamUri(
                {
                    "StreamSetup": {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}},
                    "ProfileToken": p.token,
                }
            ).Uri
            for p in (principal, substream)
        ]
        instantanea = _snapshot_opcional(media, principal.token)
    except OnvifNoDisponible:
        raise
    except Exception as exc:  # noqa: BLE001 — la librería ONVIF lanza de todo
        raise OnvifNoDisponible(f"no se pudo interrogar la cámara {host}:{puerto}: {exc}") from exc

    fuentes = Fuentes(rtsp_principal=urls[0], rtsp_substream=urls[1], snapshot=instantanea)
    log.info(
        "cctv: cámara %s:%d lista (substream=%s, instantánea=%s)",
        host,
        puerto,
        sin_credenciales(fuentes.rtsp_substream),
        "sí" if fuentes.snapshot else "no — el goteo tendrá que decodificar",
    )
    return fuentes


def _snapshot_opcional(media, token: str) -> str | None:
    """`GetSnapshotUri` es OPCIONAL en Profile S: que falle no es un error, es un dato.

    Sin instantánea el goteo sigue funcionando —saca el fotograma del RTSP— pero cuesta
    decodificar. Degradar en silencio sería tapar por qué de pronto sube la CPU.
    """
    try:
        return media.GetSnapshotUri({"ProfileToken": token}).Uri
    except Exception:  # noqa: BLE001
        log.info("cctv: la cámara no ofrece GetSnapshotUri; el goteo saldrá del RTSP")
        return None
