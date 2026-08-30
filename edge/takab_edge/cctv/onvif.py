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
Unas cámaras devuelven la URL ya con la credencial dentro —``rtsp://usuario:tu-clave@host/
stream``— y otras la devuelven pelada y **luego exigen Digest**. La Dahua del sitio es de
las segundas: sus tres URIs vienen sin credencial y las tres contestan `401` sin ella, así
que :func:`descubrir` la inyecta antes de devolverlas. Sea cual sea el camino, lo que sale
de aquí **lleva el secreto dentro**, y eso significa que:

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
import re
from dataclasses import dataclass
from datetime import UTC, datetime
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

    # La credencial se inyecta AQUÍ porque no todas las cámaras la traen. La Dahua del
    # sitio devuelve las tres URIs peladas y luego exige Digest en las tres: sin esto,
    # ffmpeg recibe una URL que la cámara contesta con 401 y el gabinete no graba nada.
    # `con_credenciales` no pisa a la que sí la trae embebida, que era el caso que este
    # módulo suponía único. Ver `tests/test_cctv_onvif_credencial.py`.
    fuentes = Fuentes(
        rtsp_principal=con_credenciales(urls[0], usuario, clave),
        rtsp_substream=con_credenciales(urls[1], usuario, clave),
        snapshot=con_credenciales(instantanea, usuario, clave) if instantanea else None,
    )
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


# --------------------------------------------------------------------------------------
# EL RELOJ DE LA CÁMARA (T-3.11 · hallazgo de la cámara real, 2026-08-30)
# --------------------------------------------------------------------------------------
#
# La cámara **quema la hora en los píxeles**. Ese rótulo va dentro del clip y dentro de
# cada captura, y las capturas son cuatro de las pruebas del dictamen: viajan al reporte
# con su `sha256` y su cadena de custodia. Si el rótulo contradice a la fecha del
# incidente, el paquete de evidencia se contradice a sí mismo, y quien lo lea no tiene
# forma de saber cuál de las dos horas es la buena.
#
# Y no es hipotético. La cámara del sitio llegó con el huso de fábrica —`GMT+08:00`, la
# zona del fabricante— mientras su UTC era correcto. Resultado medido el 2026-08-30: el
# gabinete fechaba las once y media de la mañana del día 30 y la foto decía **01:57 del
# día 31**. Catorce horas y un día de diferencia, en una imagen destinada a un dictamen.
#
# Por eso esto **avisa y deja grabar** en vez de negarse. La distinción importa: el vídeo
# no está mal, lo está su rótulo, y nuestras horas —nombre de fichero, `captured_at`,
# métricas— salen del gabinete y son correctas. Negarse a grabar convertiría un rótulo
# torcido en un incidente sin vídeo, que es peor. Lo que no puede pasar es que nadie se
# entere: un desajuste callado es el que acaba delante de un juez.


@dataclass(frozen=True)
class RelojCamara:
    """Lo que la cámara dice de su propia hora. Sin credenciales: no las lleva."""

    #: UTC que declara la cámara, en segundos desde época. `None` si no lo dice.
    utc_epoch: float | None
    #: Huso con el que **rotula** la imagen (`GMT+08:00`, `CST6CDT`…).
    tz: str
    #: `True` si se sincroniza por NTP. `Manual` significa que va a derivar sin remedio.
    ntp: bool


def revisar_reloj(reloj: RelojCamara, ahora: datetime, offset_local_s: float) -> list[str]:
    """Compara el reloj de la cámara con el del gabinete. Devuelve hallazgos en claro.

    Función **pura** —recibe el ahora y el huso del gabinete— para que se pueda probar sin
    reloj de pared y sin cámara. Lista vacía significa que no hay nada que decir.

    `offset_local_s` es el desplazamiento del gabinete respecto a UTC. Sale del sistema y no
    de la config a propósito: el Pi está *dentro* del edificio, así que su huso ya es el del
    sitio, y una clave más en el config sync es una clave más que puede quedarse rancia.
    """
    hallazgos: list[str] = []

    if reloj.utc_epoch is None:
        hallazgos.append("la cámara no declara su hora UTC: no se puede comprobar su rótulo")
    else:
        deriva = abs(reloj.utc_epoch - ahora.timestamp())
        if deriva > _DERIVA_UTC_MAX_S:
            hallazgos.append(
                f"el UTC de la cámara va {deriva:.0f} s desviado del gabinete "
                f"(tolerancia {_DERIVA_UTC_MAX_S:.0f} s): su rótulo fecha mal el incidente"
            )

    offset_camara = _offset_de_tz(reloj.tz)
    if offset_camara is None:
        hallazgos.append(f"huso de la cámara ilegible ({reloj.tz!r}): no se puede comparar")
    elif abs(offset_camara - offset_local_s) > 60:
        horas = (offset_camara - offset_local_s) / 3600
        hallazgos.append(
            f"la cámara rotula la imagen en {reloj.tz} y el gabinete vive en UTC"
            f"{offset_local_s / 3600:+g}: el sello quemado en el vídeo va {horas:+g} h "
            "respecto a la hora del incidente — y con eso puede cambiar hasta el día"
        )

    if not reloj.ntp:
        hallazgos.append(
            "la cámara tiene la hora en modo Manual (sin NTP): va a derivar sin que "
            "nada la corrija, y el rótulo se aleja más cada semana"
        )
    return hallazgos


#: Tolerancia del UTC de la cámara. Generosa a propósito: lo que se persigue es un huso
#: mal puesto o un reloj a la deriva, no medio minuto de desajuste que no cambia el sello.
_DERIVA_UTC_MAX_S = 120.0


def _offset_de_tz(tz: str) -> float | None:
    """Segundos respecto a UTC de un `TZ` de ONVIF. Solo entiende la forma `GMT±HH:MM`.

    ONVIF admite también husos POSIX con reglas de horario de verano (`CST6CDT,M4.1.0…`),
    que no se resuelven sin una base de datos de zonas y **no hacen falta**: lo que caza
    este control es el huso de fábrica, que siempre viene en la forma simple. Un `TZ` que
    no se sepa leer se declara ilegible en vez de darse por bueno.
    """
    m = _RE_TZ.match(tz.strip())
    if not m:
        return None
    signo = -1 if m.group("signo") == "-" else 1
    # OJO con la inversión: el `GMT+08:00` de ONVIF es la etiqueta POSIX, donde el signo va
    # al revés que el desplazamiento… salvo que las cámaras lo usan como lo usa la gente.
    # Medido en la del sitio: dice `GMT+08:00` y rotula UTC+8, no UTC−8.
    return signo * (int(m.group("h")) * 3600 + int(m.group("m") or 0) * 60)


_RE_TZ = re.compile(r"^GMT(?P<signo>[+-])(?P<h>\d{1,2})(?::(?P<m>\d{2}))?$", re.IGNORECASE)


def reloj_de(host: str, puerto: int, usuario: str, clave: str) -> RelojCamara:
    """Le pregunta la hora a la cámara por ONVIF. Import perezoso, como `descubrir`."""
    try:
        from onvif import ONVIFCamera  # noqa: PLC0415 — perezoso a propósito (extra `cctv`)
    except ImportError as exc:  # pragma: no cover — depende del extra
        raise OnvifNoDisponible("falta el extra `cctv` (onvif-zeep)") from exc

    try:
        dev = ONVIFCamera(host, puerto, usuario, clave).create_devicemgmt_service()
        d = dev.GetSystemDateAndTime()
        utc = getattr(d, "UTCDateTime", None)
        epoch = None
        if utc is not None:
            epoch = datetime(
                utc.Date.Year,
                utc.Date.Month,
                utc.Date.Day,
                utc.Time.Hour,
                utc.Time.Minute,
                utc.Time.Second,
                tzinfo=UTC,
            ).timestamp()
        tz = getattr(getattr(d, "TimeZone", None), "TZ", "") or ""
        return RelojCamara(utc_epoch=epoch, tz=tz, ntp=str(d.DateTimeType) == "NTP")
    except Exception as exc:  # noqa: BLE001 — la librería ONVIF lanza de todo
        raise OnvifNoDisponible(f"no se pudo leer el reloj de {host}:{puerto}: {exc}") from exc
