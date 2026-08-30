"""El goteo de capturas por HTTP, sin pasar por ffmpeg (T-3.11).

POR QUÉ ESTO NO LO HACE FFMPEG, QUE ERA EL PLAN
───────────────────────────────────────────────
`GetSnapshotUri` es la rama barata del goteo: un `GET` de un JPEG **ya codificado**, cero
decodificación. El cliente le pasaba esa URL a ffmpeg como se la pasa la del RTSP, y contra
la cámara del sitio eso **no funciona**. Medido el 2026-08-30, con ffmpeg LGPL de verdad:

    cmd_captura <- instantánea HTTP   ->  401 Unauthorized
    cmd_captura <- RTSP substream     ->  0 (bien)
    cmd_captura <- RTSP principal     ->  0 (bien)

Y la causa no es la que parece. ffmpeg **sí** hace Digest, y manda una cabecera correcta;
lo que pasa es que el analizador de la cámara **depende del orden de los parámetros**:

    nc=… antes de cnonce=…   ->  200      (lo que manda urllib)
    cnonce=… antes de nc=…   ->  401      (lo que manda ffmpeg)

Comprobado en cruz —factorial sobre `opaque`, `algorithm` y el entrecomillado de `qop`— y
el orden es el único factor que decide. La RFC 7616 dice que la lista de parámetros **no**
tiene orden, así que quien está mal es la cámara; pero la cámara es la que hay.

Eso importa más de lo que parece porque `_gotear` **prefiere** la instantánea cuando existe:
en esta cámara habrían fallado **todas** las capturas del goteo, dejando el clip bien y el
**reingreso sin fechar nunca** — y el reingreso es justamente lo que solo el goteo puede
fechar. Habría goteado avisos en el journal para siempre sin producir una sola imagen.

Así que la instantánea se baja aquí, con `urllib`, que manda el orden que la cámara acepta.
No hay conflicto con `D-24`: la condición de licencia es sobre **decodificar vídeo**, y esto
no decodifica nada — mueve un JPEG de un sitio a otro.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from takab_edge.cctv.onvif import sin_credenciales

log = logging.getLogger("takab_edge.cctv")

#: Techo del `GET`. Un goteo que se cuelga no puede retrasar el tick del cliente: el
#: intervalo de fábrica son 30 s y el cliente sondea a 1 Hz.
TIMEOUT_S = 10.0

#: Tamaño por encima del cual la respuesta deja de parecer una foto y empieza a parecer un
#: error. Una página de error de estas cámaras cabe en 1 kB; un JPEG de 640×480 no.
_MINIMO_JPEG = 1024


def _abrir(url: str, usuario: str, clave: str, timeout_s: float) -> bytes:
    """`GET` con Digest. Aislado para que el test no necesite red ni cámara."""
    gestor = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    gestor.add_password(None, url, usuario, clave)
    opener = urllib.request.build_opener(
        urllib.request.HTTPDigestAuthHandler(gestor),
        urllib.request.HTTPBasicAuthHandler(gestor),
    )
    with opener.open(url, timeout=timeout_s) as respuesta:
        return respuesta.read()


def bajar(
    url: str,
    destino: Path,
    *,
    timeout_s: float = TIMEOUT_S,
    abrir: Callable[[str, str, str, float], bytes] = _abrir,
) -> bool:
    """Baja la instantánea a `destino`. Devuelve si quedó un fichero utilizable.

    La credencial viaja **dentro** de `url` —así la devuelve `descubrir()`— y se saca aquí
    para dársela al gestor de contraseñas: urllib no la lee del `userinfo`. Nada de esto
    toca un log; todo lo que se registra pasa por `sin_credenciales`.

    **No lanza.** El goteo es una foto cada treinta segundos durante horas: un fallo puntual
    —la cámara ocupada, un corte de un segundo— no puede tumbar el proceso ni contar como
    captura buena. Devolver `False` deja que quien llama decida, y quien llama cae al RTSP.
    """
    partes = urlsplit(url)
    limpia = urlunsplit(
        (
            partes.scheme,
            f"{partes.hostname or ''}{f':{partes.port}' if partes.port else ''}",
            partes.path,
            partes.query,
            partes.fragment,
        )
    )
    try:
        cuerpo = abrir(limpia, partes.username or "", partes.password or "", timeout_s)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.warning("cctv: la instantánea %s falló: %s", sin_credenciales(url), exc)
        return False

    # Un 200 con una página de error dentro es el caso que más engaña: el fichero existe,
    # pesa poco y no es una foto. Escribirlo dejaría un JPEG roto en la cadena de custodia.
    if len(cuerpo) < _MINIMO_JPEG or not cuerpo.startswith(b"\xff\xd8"):
        log.warning(
            "cctv: la instantánea %s devolvió %d bytes que no son un JPEG",
            sin_credenciales(url),
            len(cuerpo),
        )
        return False

    destino.write_bytes(cuerpo)
    return True
