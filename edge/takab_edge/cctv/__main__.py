"""`takab-cctv` — el proceso del CCTV del gabinete (T-3.11).

Es un proceso **aparte** de `takab-edge` y de `takab-gpio`, con su propia unidad systemd y
sus propios límites de CPU y memoria (`B.3`). Esa separación no es organización: es lo que
hace que un OOM del decodificador de vídeo mate **a este proceso y a nadie más**.

Ejecutar:  ``python -m takab_edge.cctv``  ·  o el script ``takab-cctv``.

LO QUE COMPRUEBA ANTES DE GRABAR UN SOLO FOTOGRAMA
──────────────────────────────────────────────────
1. Que el CCTV esté **encendido** para este gabinete (de fábrica no lo está — `D-25`).
2. Que el **conteo local** siga apagado. Ver abajo: la negativa es deliberada.
3. Que el ffmpeg disponible sea **LGPL** (`D-24`). Fail-closed.
4. Que la cámara conteste.

Las cuatro fallan *hacia no arrancar*. Un CCTV que no arranca deja un reporte sin vídeo;
uno que arranca mal deja imágenes de personas donde no debían estar.

Y una **quinta que avisa en vez de impedir**: que el reloj de la cámara —el que quema el
sello en los píxeles— concuerde con el del gabinete. Va aparte de las cuatro a propósito.
Cuando ese sello miente, el vídeo sigue siendo bueno y nuestras horas siguen siendo
correctas; lo que se rompe es la evidencia, porque el fotograma que va al dictamen se
contradice con la fecha del incidente. Negarse a grabar por eso cambiaría un rótulo
torcido por un incidente sin vídeo. Ver :func:`_revisar_reloj_de_la_camara`.
"""

from __future__ import annotations

import logging
import signal as _signal
import subprocess  # noqa: S404 — ffmpeg por subproceso: es el requisito de licencia de D-24
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from takab_edge.cctv.cliente import ClienteCctv
from takab_edge.cctv.ffmpeg import FfmpegNoApto, verificar
from takab_edge.cctv.onvif import (
    Fuentes,
    OnvifNoDisponible,
    con_credenciales,
    descubrir,
    reloj_de,
    revisar_reloj,
    sin_credenciales,
)
from takab_edge.cctv.recorder import cmd_anillo
from takab_edge.config import EdgeSettings, load_settings

log = logging.getLogger("takab_edge.cctv")

#: Espera entre reintentos de levantar el anillo cuando ffmpeg se cae. Espaciado y con
#: techo, por la misma razón que las unidades del gabinete: reintentar sin espaciar contra
#: una cámara apagada llena el journal y calienta la CPU sin arreglar nada.
_REINTENTO_MIN_S = 2.0
_REINTENTO_MAX_S = 60.0


class ArranqueRechazado(RuntimeError):
    """Una de las cuatro comprobaciones dijo que no. El mensaje explica cuál y por qué."""


def _fuentes_de(cfg, usuario: str, clave: str) -> Fuentes:
    """Resuelve de dónde sale el vídeo: de la URL declarada, o preguntándole a la cámara.

    La URL de config **no lleva credencial** —es apta para persistirse y para viajar en el
    config sync firmado— y se le inyecta aquí, en memoria, justo antes de usarla. La
    declarada gana sobre ONVIF a propósito: si alguien la escribió es porque el
    descubrimiento no le sirvió, y volver a intentarlo solo añade una espera y un fallo.
    """
    if cfg.rtsp_url:
        url = con_credenciales(cfg.rtsp_url, usuario, clave)
        log.info("cctv: usando la URL declarada (%s); no se interroga ONVIF", sin_credenciales(url))
        # Sin ONVIF no hay forma de saber si hay instantánea: el goteo saldrá del RTSP.
        return Fuentes(rtsp_principal=url, rtsp_substream=url, snapshot=None)
    if cfg.host:
        return descubrir(cfg.host, cfg.onvif_port, usuario, clave)
    raise ArranqueRechazado(
        "CCTV encendido pero sin cámara: declara `TAKAB_EDGE_CCTV__RTSP_URL` "
        "o `TAKAB_EDGE_CCTV__HOST` para descubrirla por ONVIF"
    )


def _comprobar(settings: EdgeSettings) -> None:
    cfg = settings.cctv
    if not cfg.enabled:
        raise ArranqueRechazado(
            "el CCTV está apagado en este gabinete (TAKAB_EDGE_CCTV__ENABLED=false). "
            "Encenderlo espera a G-04 acreditado y a la medición de B.2 — ver D-25"
        )
    if cfg.conteo_local:
        raise ArranqueRechazado(
            "TAKAB_EDGE_CCTV__CONTEO_LOCAL=true, y el conteo preliminar en el gabinete "
            "está APLAZADO hasta que exista el equipo de campo (Pi 5 8 GB o Pi 4 8 GB, sin "
            "comprar) y se mida B.2 EN ÉL. No es que no quepa: es que no se puede medir en "
            "una máquina que no es la que va a ejecutar. Hoy cuenta la nube — ver D-24"
        )
    if cfg.perfil != cfg.perfil_efectivo:
        # La config degradó sola; se dice en voz alta aquí porque `settings.py` es config
        # pura y no registra nada.
        log.warning("cctv: perfil %r desconocido; se graba %r", cfg.perfil, cfg.perfil_efectivo)


def _revisar_reloj_de_la_camara(cfg, usuario: str, clave: str) -> list[str]:
    """La QUINTA comprobación: que el sello que la cámara quema en la imagen no mienta.

    **Avisa, no impide arrancar**, y la diferencia es deliberada. Las otras cuatro fallan
    hacia no grabar porque lo que está mal es el vídeo o el permiso para tenerlo. Aquí el
    vídeo está bien: lo que va torcido es el rótulo. Nuestras horas —el nombre del fichero,
    `captured_at`, las métricas— salen del gabinete y son correctas, así que negarse a
    grabar cambiaría un rótulo torcido por un incidente sin vídeo, que es peor.

    Lo que no puede pasar es que nadie se entere. Ver el bloque de `onvif.py`: la cámara del
    sitio llegó rotulando catorce horas y un día por delante del incidente.

    Sin `host` no hay a quién preguntarle —la URL declarada a mano no lleva servicio ONVIF—
    y eso **no es un hallazgo**: es una cámara declarada de la otra forma.
    """
    if not cfg.host:
        log.info("cctv: sin host ONVIF no se puede revisar el reloj de la cámara")
        return []
    try:
        reloj = reloj_de(cfg.host, cfg.onvif_port, usuario, clave)
    except OnvifNoDisponible as exc:
        # No se le niega el arranque por esto: la cámara ya contestó a `descubrir()`.
        log.warning("cctv: no se pudo leer el reloj de la cámara (%s); se graba igual", exc)
        return []

    offset = datetime.now().astimezone().utcoffset() or timedelta(0)
    hallazgos = revisar_reloj(reloj, datetime.now(UTC), offset.total_seconds())
    for h in hallazgos:
        log.warning("cctv: RELOJ DE LA CÁMARA — %s", h)
    if not hallazgos:
        log.info("cctv: el reloj de la cámara concuerda con el del gabinete (%s)", reloj.tz)
    return hallazgos


def run_cctv_process(settings: EdgeSettings | None = None, *, block: bool = True) -> ClienteCctv:
    """Arranca el CCTV. Si ``block``, sondea hasta SIGINT/SIGTERM."""
    cfg_all = settings or load_settings()
    cfg = cfg_all.cctv
    _comprobar(cfg_all)

    info = verificar(cfg.ffmpeg_path)  # lanza FfmpegNoApto si no es LGPL
    log.info("cctv: ffmpeg %s (%s) apto", info.version, info.licencia)

    import os  # noqa: PLC0415 — solo para leer la credencial, y no se guarda en ningún sitio

    usuario = os.environ.get("TAKAB_EDGE_CCTV_USER", "")
    clave = os.environ.get("TAKAB_EDGE_CCTV_PASS", "")
    fuentes = _fuentes_de(cfg, usuario, clave)
    _revisar_reloj_de_la_camara(cfg, usuario, clave)

    directorio = (
        Path(cfg_all.state_dir) / "cctv"
        if hasattr(cfg_all, "state_dir")
        else Path("/var/lib/takab/cctv")
    )
    directorio.mkdir(parents=True, exist_ok=True)

    clave_grant = os.environ.get("TAKAB_EDGE_CCTV_KEY", "").encode()
    if not clave_grant:
        # Se AVISA y se sigue: sin clave no se sube, pero grabar sigue teniendo sentido —
        # la evidencia se acumula en `pendientes/` y sube el día que alguien provisione la
        # clave. Negarse a arrancar aquí convertiría un problema de aprovisionamiento en
        # un incidente sin vídeo.
        log.warning(
            "cctv: sin TAKAB_EDGE_CCTV_KEY no se puede pedir grant; se graba y se acumula "
            "en %s hasta que se provisione",
            directorio / "pendientes",
        )

    cliente = ClienteCctv(
        config=cfg,
        fuentes=fuentes,
        directorio=directorio,
        leer_status=_lector_de_status(cfg.edge_api_base),
        correr=_correr,
        pedir_grant=_pedidor_de_grant(cfg.edge_api_base, clave_grant) if clave_grant else None,
        subir=_subir_presignado if clave_grant else None,
    )
    if not block:
        return cliente

    parar = threading.Event()
    for sig in (_signal.SIGINT, _signal.SIGTERM):
        _signal.signal(sig, lambda *_: parar.set())

    anillo = _AnilloVivo(cfg, fuentes, directorio)
    try:
        while not parar.is_set():
            anillo.vigilar()
            cliente.paso()
            parar.wait(cfg.poll_s)
    finally:
        anillo.detener()
        log.info("cctv: proceso detenido")
    return cliente


class _AnilloVivo:
    """Mantiene vivo el ffmpeg del anillo, con reintento espaciado si se cae."""

    def __init__(self, cfg, fuentes: Fuentes, directorio: Path) -> None:
        self._cfg = cfg
        self._url = fuentes.rtsp(cfg.perfil_efectivo)
        self._directorio = directorio
        self._proc: subprocess.Popen | None = None
        self._espera = _REINTENTO_MIN_S
        self._proximo_intento = datetime.now(UTC)

    def vigilar(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._espera = _REINTENTO_MIN_S  # lleva rato vivo: se reinicia el backoff
            return
        if self._proc is not None:
            log.warning("cctv: el anillo murió (código %s); se relanza", self._proc.returncode)
            self._proc = None
        if datetime.now(UTC) < self._proximo_intento:
            return
        try:
            self._proc = subprocess.Popen(  # noqa: S603 — comando construido por nosotros
                cmd_anillo(self._cfg.ffmpeg_path, self._url, self._directorio),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.info("cctv: anillo grabando desde %s", sin_credenciales(self._url))
        except OSError as exc:
            log.error("cctv: no se pudo lanzar el anillo: %s", exc)
        self._espera = min(self._espera * 2, _REINTENTO_MAX_S)
        self._proximo_intento = datetime.now(UTC) + timedelta(seconds=self._espera)

    def detener(self) -> None:
        if self._proc is None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._proc = None


def _lector_de_status(base: str):
    """Cliente HTTP mínimo del panel LAN. Sin dependencias: es `urllib` de la stdlib."""
    import json  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    url = base.rstrip("/") + "/api/status"

    def leer() -> dict:
        with urllib.request.urlopen(url, timeout=5.0) as r:  # noqa: S310 — URL de config, http local
            return json.loads(r.read().decode("utf-8"))

    return leer


def _pedidor_de_grant(base: str, clave: bytes):
    """Cliente del `POST /api/cctv/grant` del panel LAN, firmado con el dominio `cctv`.

    El gabinete es el único con identidad X.509 y enlace MQTT, así que es él quien le pide
    la URL a la nube. Nosotros le mandamos cinco campos y nos llevamos una URL: **el vídeo
    no pasa por él**.
    """
    import json  # noqa: PLC0415
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    from takab_edge.security import SecurityManager  # noqa: PLC0415

    firmante = SecurityManager(hmac_key=clave)
    url = base.rstrip("/") + "/api/cctv/grant"

    def pedir(*, mode: str, event_id: str, sha256: str, ts_from, ts_to) -> dict | None:
        cuerpo = json.dumps(
            {
                "mode": mode,
                "event_id": event_id,
                "sha256": sha256,
                "ts_from": ts_from.isoformat(),
                "ts_to": ts_to.isoformat(),
            }
        ).encode()
        peticion = urllib.request.Request(  # noqa: S310 — http local, base de config
            url,
            data=cuerpo,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Takab-Cctv-Sig": firmante.sign_cctv(cuerpo),
            },
        )
        try:
            with urllib.request.urlopen(peticion, timeout=45.0) as r:  # noqa: S310
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 409 es «no hay enlace todavía», y es el caso NORMAL durante un corte: se
            # registra en info para no llenar el journal de errores que no lo son.
            nivel = log.info if exc.code == 409 else log.warning
            nivel("cctv: el gabinete no otorgó grant (%s)", exc.code)
            return None
        except (OSError, ValueError) as exc:
            log.warning("cctv: no se pudo pedir grant: %s", exc)
            return None

    return pedir


def _subir_presignado(url: str, datos: bytes, content_type: str) -> bool:
    """PUT directo a S3. Reutiliza el helper del backfill: mismo camino, mismo tope."""
    from takab_edge.backfill import default_http_put  # noqa: PLC0415

    return default_http_put(url, datos, content_type, timeout_s=300.0)


def _correr(cmd: list[str]) -> int:
    """Ejecuta un ffmpeg de un disparo (recorte o captura) y devuelve su código."""
    try:
        return subprocess.run(cmd, capture_output=True, timeout=300, check=False).returncode  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("cctv: ffmpeg no completó: %s", exc)
        return 1


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        run_cctv_process()
    except (ArranqueRechazado, FfmpegNoApto, OnvifNoDisponible) as exc:
        log.error("cctv: NO arranca — %s", exc)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
