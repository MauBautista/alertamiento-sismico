"""audio — voceo del gabinete (hallazgo A-6): canal ADVISORY, jamás de vida.

La alerta primaria audible es y seguirá siendo la SIRENA DE RELÉ (camino de vida,
determinista, `gpio`). Este módulo solo la COMPLEMENTA con un mensaje hablado por
la salida de audio del Pi: instrucciones de SISMO en alerta real y de SIMULACRO
en drills. El cerebro es un **Pi 4** y **sí trae jack 3.5 mm** —la sirena por jack
está en producción desde T-1.68—; este docstring decía «el Pi 5 no trae jack»,
que era falso por partida doble (ni es un Pi 5, ni carece de jack).

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

from takab_edge.audio import catalog
from takab_edge.config import EdgeSettings
from takab_edge.contracts import SirenReason, Tier, TierDecision
from takab_edge.gpio_link import as_link
from takab_edge.module import EdgeModule

if TYPE_CHECKING:
    from takab_edge.gpio_link import GpioLink

log = logging.getLogger("takab_edge.audio")

#: [T-1.68] Cada cuánto el watcher concilia la sirena por audio con
#: ``gpio.siren_sounding``. 50 ms ⇒ arranque casi inmediato y hueco de bucle
#: imperceptible (la sirena de RELÉ es la primaria; esto es advisory).
_SIREN_POLL_S = 0.05

#: [T-2.70.a·D2/P1] Cuántas conciliaciones seguidas pueden fallar antes de CALLAR
#: el WAV de la sirena. A 20 Hz son ~1 s.
#:
#: Ni 0 ni infinito, y los dos extremos son defectos reales:
#:
#: * **Infinito** era lo de antes: `_reconcile_siren` atrapaba todo y, al fallar,
#:   omitía la reconciliación SIN parar el WAV. Con `siren_reason` al otro lado de
#:   un enlace caído, el altavoz sigue sonando después de cerrarse la alerta y
#:   nadie en el edificio puede distinguirlo de una alerta viva.
#: * **0** (cortar al primer fallo) convertiría un parpadeo de 50 ms en un
#:   tartamudeo del altavoz de un inmueble: `stop()` + `play()` reinicia el WAV
#:   desde el principio.
#:
#: La sirena de RELÉ —la primaria— no depende de esto: la sostiene el dueño de los
#: pines con su enclave, así que callar el altavoz advisory nunca deja al edificio
#: sin alerta audible.
#:
#: Es un SUELO, no un instante: cruzado el umbral se reintenta el corte en cada
#: conciliación mientras el altavoz siga sonando. Con una igualdad, un `stop()`
#: que fallara justo en la conciliación número 20 dejaba el altavoz sonando para
#: siempre — el mismo defecto que la constante venía a cerrar.
_SIREN_FALLOS_ANTES_DE_CALLAR = 20


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
        gpio: GpioLink,
        backend: AudioBackend | None = None,
        siren_backend: AudioBackend | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self._link = as_link(gpio)

        def _default_backend() -> AudioBackend:
            return (
                SimulatedAudioBackend()
                if settings.dev_mode
                else AplayBackend(settings.audio_device)
            )

        self._backend = backend if backend is not None else _default_backend()
        # [T-1.68] La sirena por audio usa un backend PROPIO (no corta el voceo, ni
        # el voceo a ella: con `default`/dmix ambos se mezclan en el mismo jack).
        self._siren_backend = siren_backend if siren_backend is not None else _default_backend()
        self._siren_path = settings.audio_siren_path or str(
            Path(__file__).parent / "assets" / "siren.wav"
        )
        # [T-2.49] Tono de PRUEBA: patrón de bips deliberadamente NO confundible con el
        # barrido de la sirena. `None` si no existe ⇒ la prueba calla (ver `asset_for`).
        test_path = settings.audio_test_path or str(Path(__file__).parent / "assets" / "prueba.wav")
        self._test_path: str | None = test_path if Path(test_path).is_file() else None
        # [T-5.17] El voceo de simulacro deja de leerse de `settings` en cada
        # reproducción y pasa a ser ESTADO del módulo, como la sirena y el tono de
        # prueba: es lo que permite que la nube lo elija por id de catálogo. El
        # valor inicial sigue siendo el asset local (la grabación del sitio, si la
        # hay); un id del catálogo lo sustituye.
        self._simulacro_path: str | None = settings.audio_simulacro_path or None
        self._audio_profile: dict = {
            "applied": {},
            "rejected": {},
            "reserved": {},
            "siren_path": self._siren_path,
            "test_path": self._test_path,
            "simulacro_path": self._simulacro_path,
        }
        self._siren_stop = threading.Event()
        self._siren_thread: threading.Thread | None = None
        #: [T-2.70.a·D2/P1] Conciliaciones seguidas que no pudieron leer el estado.
        self._siren_fallos = 0

    @property
    def enabled(self) -> bool:
        return self.settings.audio_enabled

    @property
    def siren_enabled(self) -> bool:
        """[T-1.68] Sirena por el jack 3.5 mm — toggle propio, aparte del voceo."""
        return self.settings.audio_siren_enabled

    @property
    def sounding(self) -> bool:
        try:
            return self._backend.playing is not None
        except Exception:  # noqa: BLE001 — sección advisory
            return False

    def _on_start(self) -> None:
        # Voceo y sirena por audio son INDEPENDIENTES (T-1.68): el voceo exige WAVs
        # grabados (A-6, aún apagado); la sirena arranca con su asset empaquetado.
        self._start_voice()
        self._start_siren()

    def _start_voice(self) -> None:
        if not self.enabled:
            log.info("voceo por audio DESHABILITADO (audio_enabled=false; gate de hardware A-6)")
            return
        for kind, path in (
            ("sismo", self.settings.audio_sismo_path),
            ("simulacro", self.simulacro_path),
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
        self._link.subscribe("silence", self._on_silence)

    def _start_siren(self) -> None:
        """[T-1.68] Sirena por el jack: watcher que sigue ``gpio.siren_sounding``."""
        if not self.siren_enabled:
            log.info("sirena por audio DESHABILITADA (audio_siren_enabled=false)")
            return
        p = Path(self._siren_path)
        if not p.is_file():
            raise RuntimeError(
                f"audio: el asset de la sirena no existe ({self._siren_path!r}) y "
                "audio_siren_enabled=true — configura TAKAB_EDGE_AUDIO_SIREN_PATH o apágala. "
                "El módulo es no-crítico: la sirena de RELÉ sigue siendo la primaria."
            )
        log.info(
            "sirena por audio: %s sha256=%s",
            self._siren_path,
            hashlib.sha256(p.read_bytes()).hexdigest(),
        )
        # [T-2.49] El tono de prueba se audita igual que la sirena: hay que poder
        # decir QUÉ sonido exacto puede salir por el altavoz de un inmueble.
        if self._test_path is not None:
            log.info(
                "tono de prueba por audio: %s sha256=%s",
                self._test_path,
                hashlib.sha256(Path(self._test_path).read_bytes()).hexdigest(),
            )
        else:
            log.warning(
                "sin tono de PRUEBA empaquetado: los self-test de sirena sonarán en "
                "silencio (nunca con el tono de alerta real)"
            )
        self._siren_stop.clear()
        self._siren_thread = threading.Thread(
            target=self._siren_watch_loop, name="audio-siren", daemon=True
        )
        self._siren_thread.start()

    def _siren_watch_loop(self) -> None:
        while not self._siren_stop.wait(_SIREN_POLL_S):
            self._reconcile_siren()

    def apply_audio_profile(self, profile: dict | None) -> dict:
        """[T-2.49] Aplica `config.edge.audio` de la nube. Devuelve lo que se reporta.

        Contrato de honestidad: un ID que este edge no puede servir **conserva el tono
        anterior** y lo declara. La alternativa —caer a otro tono— haría que el gabinete
        sonara distinto de lo que su propia config dice, que es peor que no cambiar.

        El resultado va a `device_health.meta.audio`, de modo que la flota puede ver
        qué gabinetes quedaron atrás de un cambio de catálogo sin ir uno por uno.
        """
        applied: dict[str, str] = {}
        rejected: dict[str, str] = {}
        reserved: dict[str, str] = {}
        if isinstance(profile, dict):
            for slot, attr in (
                ("siren", "_siren_path"),
                ("test", "_test_path"),
                # [T-5.17] La tercera ranura, con LAS MISMAS reglas: por id de
                # catálogo, y lo que no se puede servir conserva el tono anterior.
                ("simulacro", "_simulacro_path"),
            ):
                asset_id = profile.get(slot)
                if not isinstance(asset_id, str) or not asset_id:
                    continue
                path = catalog.resolve(asset_id)
                if path is None:
                    rejected[slot] = asset_id
                    # [T-5.17] Un id RESERVADO y uno inventado acaban igual —se
                    # conserva el tono— pero no son el mismo hecho: uno es un
                    # tecleo y el otro una infracción de licencia. Sin esto, el
                    # reporte de flota los daba por idénticos.
                    razon = catalog.reason_reserved(asset_id)
                    if razon is not None:
                        reserved[slot] = razon
                    continue
                setattr(self, attr, str(path))
                applied[slot] = asset_id
        self._audio_profile = {
            "applied": applied,
            "rejected": rejected,
            "reserved": reserved,
            "siren_path": self._siren_path,
            "test_path": self._test_path,
            "simulacro_path": self._simulacro_path,
        }
        if rejected:
            log.warning("audio: perfil parcialmente aplicado; tonos conservados: %s", rejected)
        return self._audio_profile

    @property
    def profile_report(self) -> dict:
        """Lo que `health` publica en `device_health.meta.audio`."""
        return dict(self._audio_profile)

    def asset_for(self, reason: SirenReason) -> str | None:
        """[T-2.49] Qué WAV corresponde a cada razón, o ``None`` si no debe sonar.

        Una prueba SIN su tono no cae al tono de alerta: **calla**. Sonar la sirena
        real por un self-test es precisamente la falsa alarma que esta tarea elimina,
        y un edificio en silencio durante una prueba no corre ningún riesgo.
        """
        if reason is SirenReason.TEST:
            if self._test_path is None:
                log.warning(
                    "sirena por audio: no hay tono de PRUEBA disponible; se calla en vez "
                    "de sonar la alerta real (una prueba no puede sonar a sismo)"
                )
            return self._test_path
        return self._siren_path

    def _reconcile_siren(self) -> None:
        """Enciende/apaga el WAV de la sirena según suene —y POR QUÉ— la de relé.

        [T-2.49] Antes se miraba solo `gpio.siren_sounding`, un booleano eléctrico, y
        se reproducía el mismo `siren.wav` en todos los casos: el self-test de sirena
        de un operador sonaba idéntico a un sismo real dentro de un edificio con gente.
        Ahora se consulta `gpio.siren_reason`, que deriva de los mismos enclaves que
        deciden el relé, y se elige el asset. Si la razón cambia mientras suena (una
        alerta real llega durante una prueba), el audio CONMUTA al tono correcto.

        `gpio` ya integra silencio y reset, así que un solo poll cubre el reflejo real,
        la prueba de sirena y la de actuación. Advisory: cualquier fallo se aísla.

        [T-2.70.a·D2/P1] Y el fallo YA NO deja el altavoz sonando para siempre: tras
        `_SIREN_FALLOS_ANTES_DE_CALLAR` conciliaciones seguidas sin poder leer el
        estado, se CALLA — y se SIGUE intentando mientras el altavoz suene, porque
        el corte también puede fallar. Un sonido que ya no representa nada medido es
        indistinguible de una alerta viva para quien está en el edificio, y este
        watcher de 20 Hz es además el mayor consumidor del futuro IPC.
        """
        if not self.siren_enabled:
            return
        try:
            reason = self._link.snapshot().siren_reason
        except Exception:  # noqa: BLE001 — advisory: jamás propaga al camino de vida
            self._siren_fallos += 1
            if self._siren_fallos < _SIREN_FALLOS_ANTES_DE_CALLAR:
                return
            # Umbral CRUZADO ⇒ el corte se intenta en CADA conciliación a partir de
            # aquí. La condición era `== _SIREN_FALLOS_ANTES_DE_CALLAR`, o sea UN
            # solo intento, y el `stop()` va envuelto en un `except` que traga: un
            # corte que falla justo en ese instante —`AplayBackend` deja `_proc`
            # vivo si `terminate()`/`wait()`/`kill()` lanzan— dejaba el contador
            # subiendo y la igualdad no volvía a cumplirse jamás. El altavoz se
            # quedaba sonando PARA SIEMPRE: exactamente el fallo que este umbral
            # existe para cerrar.
            #
            # El guard del reintento es `playing`, no un contador: en cuanto el
            # altavoz calla, no hay `stop()` que repetir a 20 Hz.
            ruidoso = self._siren_fallos % _SIREN_FALLOS_ANTES_DE_CALLAR == 0
            try:
                if self._siren_backend.playing is None:
                    return
                if ruidoso:
                    # Cada ~1 s mientras dure, no 20 veces por segundo (regla de
                    # oro 10): un gabinete ya averiado no puede además ahogar su
                    # propio journal, que es donde se diagnostica la avería.
                    log.exception(
                        "sirena por audio: %d conciliaciones seguidas sin poder leer "
                        "el estado del gabinete; se CALLA el altavoz (la sirena de "
                        "RELÉ, que es la primaria, sigue con su enclave)",
                        self._siren_fallos,
                    )
                self._siren_backend.stop()
            except Exception:  # noqa: BLE001 — advisory
                if ruidoso:
                    log.exception(
                        "sirena por audio: no se pudo callar el altavoz; se REINTENTA "
                        "en la siguiente conciliación"
                    )
            return
        self._siren_fallos = 0
        try:
            wanted = self.asset_for(reason) if reason is not None else None
            playing = self._siren_backend.playing
            if wanted is None:
                if playing is not None:
                    self._siren_backend.stop()
                return
            if playing != wanted:
                # Conmutar de tono exige parar primero: dos WAVs a la vez en el mismo
                # jack se mezclarían y sonaría un híbrido que no es ninguno de los dos.
                if playing is not None:
                    self._siren_backend.stop()
                self._siren_backend.play(wanted)
        except Exception:  # noqa: BLE001 — advisory: jamás propaga al camino de vida
            log.exception("sirena por audio: reconciliación falló (aislada)")

    def _on_stop(self) -> None:
        self.stop_playback()
        self._siren_stop.set()
        if self._siren_thread is not None:
            self._siren_thread.join(timeout=2.0)
            self._siren_thread = None
        try:
            self._siren_backend.stop()
        except Exception:  # noqa: BLE001 — advisory
            log.exception("audio: parada de la sirena por audio falló (aislada)")

    # ------------------------------------------------------------------ disparo
    def on_tier(self, decision: TierDecision) -> None:
        """Hook del supervisor tras ACTUAR los relés: solo el tier audible vocea."""
        if decision.tier is Tier.EVACUATE_OR_HOLD:
            self.play_sismo()

    def play_sismo(self) -> None:
        self._play("sismo", self.settings.audio_sismo_path)

    @property
    def simulacro_path(self) -> str:
        """Lo que sonaría AHORA en un simulacro. Cadena vacía = no hay asset."""
        return self._simulacro_path or ""

    def play_simulacro(self) -> None:
        """Drill del panel LAN (con PIN): mensaje de SIMULACRO, sin tocar relés."""
        self._play("simulacro", self.simulacro_path)

    def simulacro_evidence(self) -> dict:
        """[T-5.17] QUÉ va a sonar en el simulacro, con su sha256, AHORA MISMO.

        Se calcula aquí y no al arrancar el módulo, y la diferencia importa:
        entre el arranque y el simulacro puede haber entrado una config firmada
        que cambió el tono. El sha256 que se registraba hasta hoy era el del
        asset enumerado en el boot, así que podía no ser el del sonido que salió
        por la bocina.

        `sha256: None` NUNCA significa «sonó algo que no pudimos medir»: significa
        que no hay asset, y `reason` lo dice. Un hash inventado en un documento de
        cumplimiento es peor que un hueco declarado.
        """
        ruta = self.simulacro_path
        if not ruta:
            return {
                "asset_id": None,
                "path": None,
                "sha256": None,
                "will_sound": False,
                "reason": "sin asset de voceo de simulacro configurado ni elegido por catálogo",
            }
        asset_id = self._audio_profile.get("applied", {}).get("simulacro")
        p = Path(ruta)
        if not p.is_file():
            return {
                "asset_id": asset_id,
                "path": ruta,
                "sha256": None,
                "will_sound": False,
                "reason": f"el asset de simulacro no existe en el disco del gabinete ({ruta})",
            }
        return {
            "asset_id": asset_id,
            "path": ruta,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            # El voceo puede estar apagado (gate de hardware A-6) y el asset
            # existir igual: son dos hechos y se declaran por separado.
            "will_sound": bool(self.enabled),
            "reason": "" if self.enabled else "voceo por audio deshabilitado (audio_enabled=false)",
        }

    def stop_playback(self) -> None:
        """Corta el voceo en curso. NO confundir con ``stop()`` (ciclo de vida
        de EdgeModule): este método solo calla la bocina."""
        try:
            self._backend.stop()
        except Exception:  # noqa: BLE001 — advisory: jamás propagar
            log.exception("audio.stop_playback() falló (aislado)")

    def _play(self, kind: str, path: str) -> None:
        """[T-2.70.a·D2/P1] La lectura del silencio va DENTRO del try.

        Estaba fuera, y `supervisor._act_and_publish` llama a `on_tier` SIN try:
        una excepción aquí abortaba todo lo que venía después —espejo LoRa a los
        secundarios, aborto del simulacro, ACKs a la nube, `LocalEvent` y encolado
        de evidencia—. Un canal declarado ADVISORY tumbando la publicación del
        evento.

        Fail-CERRADO en el advisory: sin poder comprobar si el operador silenció,
        NO se vocea. La sirena de RELÉ es la alerta primaria y no depende de esto.
        """
        if not self.enabled:
            return
        try:
            if self._link.snapshot().audible_silenced:
                log.warning("voceo %s omitido: audibles SILENCIADOS por el operador", kind)
                return
            self._backend.stop()
            self._backend.play(path)
            log.warning("voceo %s reproduciendo (%s)", kind, path)
        except Exception:  # noqa: BLE001 — la sirena de relé es la primaria; esto jamás propaga
            log.exception("el voceo %s falló — canal advisory aislado", kind)

    def _on_silence(self, silenced: bool) -> None:
        if silenced:
            self.stop_playback()
