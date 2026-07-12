"""audio — voceo del gabinete (hallazgo A-6): canal ADVISORY, jamás de vida.

La alerta primaria audible es y seguirá siendo la SIRENA DE RELÉ (camino de vida,
determinista, `gpio`). Este módulo solo la COMPLEMENTA con un mensaje hablado por
la salida de audio del Pi (DAC/amplificador/bocina externos — el Pi 5 no trae
jack 3.5 mm): instrucciones de SISMO en alerta real y de SIMULACRO en drills.

Reglas del canal:
- **Nunca en el camino crítico**: se dispara DESPUÉS de actuar los relés
  (`supervisor._act_and_publish`) y cualquier fallo se registra y se aísla —
  jamás propaga al hilo de detección/actuación (``critical = False``).
- **Apagado por default** (``audio_enabled=False``): se enciende por gabinete
  cuando el hardware exista físicamente (gate de hardware de A-6).
- **Subordinado al silencio**: con los audibles silenciados no vocea, y el
  silencio (botón físico o panel LAN) DETIENE el voceo en curso vía el observer
  ``gpio.on_silence``.
- **Assets auditables**: sismo y simulacro son archivos DISTINTOS; al arrancar
  se registra la ruta y el sha256 de cada uno (qué mensaje exacto puede sonar).
- Sin dependencias pesadas: la reproducción real es ``aplay`` (alsa-utils) en un
  subproceso; en dev/tests un backend simulado en memoria.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from takab_edge.config import EdgeSettings
from takab_edge.contracts import Tier, TierDecision
from takab_edge.module import EdgeModule

if TYPE_CHECKING:
    from takab_edge.gpio import GpioController

log = logging.getLogger("takab_edge.audio")


class AudioBackend(Protocol):
    """Superficie mínima de reproducción: un archivo a la vez."""

    def play(self, path: str) -> None: ...

    def stop(self) -> None: ...

    @property
    def playing(self) -> str | None: ...


class SimulatedAudioBackend:
    """Backend en memoria (dev/tests): registra reproducciones, no suena."""

    def __init__(self) -> None:
        self.plays: list[str] = []
        self.stops = 0
        self._playing: str | None = None

    def play(self, path: str) -> None:
        self._playing = path
        self.plays.append(path)

    def stop(self) -> None:
        self.stops += 1
        self._playing = None

    @property
    def playing(self) -> str | None:
        return self._playing


class AplayBackend:
    """Reproducción real vía ``aplay`` (alsa-utils) en subproceso, no bloqueante.

    Un solo voceo a la vez: ``play`` corta el anterior. stdout/err van a DEVNULL
    (el panel/health no dependen de esto); el proceso muere solo al terminar el
    archivo o con ``stop()``.
    """

    def __init__(self, device: str = "default") -> None:
        self._device = device
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._path: str | None = None

    def play(self, path: str) -> None:
        with self._lock:
            self._terminate_locked()
            self._proc = subprocess.Popen(  # noqa: S603 — binario fijo, ruta validada al arrancar
                ["aplay", "-q", "-D", self._device, path],  # noqa: S607
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._path = path

    def stop(self) -> None:
        with self._lock:
            self._terminate_locked()

    def _terminate_locked(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self._path = None

    @property
    def playing(self) -> str | None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return self._path
            return None


class AudioNotifier(EdgeModule):
    """Vocea SISMO en el tier audible y SIMULACRO bajo demanda (drill del panel)."""

    name = "audio"
    critical = False  # advisory: su caída aísla, el gabinete sigue protegiendo
    depends_on = ("gpio",)

    def __init__(
        self,
        settings: EdgeSettings,
        gpio: GpioController,
        backend: AudioBackend | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self._gpio = gpio
        if backend is None:
            backend = (
                SimulatedAudioBackend()
                if settings.dev_mode
                else AplayBackend(settings.audio_device)
            )
        self._backend = backend

    @property
    def enabled(self) -> bool:
        return self.settings.audio_enabled

    @property
    def sounding(self) -> bool:
        try:
            return self._backend.playing is not None
        except Exception:  # noqa: BLE001 — sección advisory
            return False

    def _on_start(self) -> None:
        if not self.enabled:
            log.info("voceo por audio DESHABILITADO (audio_enabled=false; gate de hardware A-6)")
            return
        for kind, path in (
            ("sismo", self.settings.audio_sismo_path),
            ("simulacro", self.settings.audio_simulacro_path),
        ):
            p = Path(path) if path else None
            if p is None or not p.is_file():
                raise RuntimeError(
                    f"audio: el asset de {kind} no existe ({path!r}) y audio_enabled=true — "
                    "configura TAKAB_EDGE_AUDIO_SISMO_PATH/SIMULACRO_PATH con archivos reales "
                    "o apaga el voceo. El módulo es no-crítico: el gabinete sigue protegiendo."
                )
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            log.info("asset de voceo %s: %s sha256=%s", kind, path, digest)
        # El silencio (botón físico o panel) calla TAMBIÉN la voz, no solo la sirena.
        self._gpio.on_silence(self._on_silence)

    def _on_stop(self) -> None:
        self.stop_playback()

    # ------------------------------------------------------------------ disparo
    def on_tier(self, decision: TierDecision) -> None:
        """Hook del supervisor tras ACTUAR los relés: solo el tier audible vocea."""
        if decision.tier is Tier.EVACUATE_OR_HOLD:
            self.play_sismo()

    def play_sismo(self) -> None:
        self._play("sismo", self.settings.audio_sismo_path)

    def play_simulacro(self) -> None:
        """Drill del panel LAN (con PIN): mensaje de SIMULACRO, sin tocar relés."""
        self._play("simulacro", self.settings.audio_simulacro_path)

    def stop_playback(self) -> None:
        """Corta el voceo en curso. NO confundir con ``stop()`` (ciclo de vida
        de EdgeModule): este método solo calla la bocina."""
        try:
            self._backend.stop()
        except Exception:  # noqa: BLE001 — advisory: jamás propagar
            log.exception("audio.stop_playback() falló (aislado)")

    def _play(self, kind: str, path: str) -> None:
        if not self.enabled:
            return
        if self._gpio.audible_silenced:
            log.warning("voceo %s omitido: audibles SILENCIADOS por el operador", kind)
            return
        try:
            self._backend.stop()
            self._backend.play(path)
            log.warning("voceo %s reproduciendo (%s)", kind, path)
        except Exception:  # noqa: BLE001 — la sirena de relé es la primaria; esto jamás propaga
            log.exception("el voceo %s falló — canal advisory aislado", kind)

    def _on_silence(self, silenced: bool) -> None:
        if silenced:
            self.stop_playback()
