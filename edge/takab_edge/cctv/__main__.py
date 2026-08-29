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

    directorio = (
        Path(cfg_all.state_dir) / "cctv"
        if hasattr(cfg_all, "state_dir")
        else Path("/var/lib/takab/cctv")
    )
    directorio.mkdir(parents=True, exist_ok=True)

    cliente = ClienteCctv(
        config=cfg,
        fuentes=fuentes,
        directorio=directorio,
        leer_status=_lector_de_status(cfg.edge_api_base),
        correr=_correr,
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
