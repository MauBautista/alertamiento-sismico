"""drill — modo SIMULACRO institucional del gabinete (T-1.60 · cierra M-1).

Un simulacro es OBSERVADOR puro: pinta el banner "SIMULACRO — NO ES REAL" en el
panel LAN y (si hay hardware de audio) vocea el mensaje de simulacro. JAMÁS
toca gpio/relés — la sirena, el gas y las puertas no saben que hay drill.

LO REAL GANA, sin excepciones:
- se RECHAZA el arranque si hay una alerta SASMEX enclavada;
- un SASMEX real (no pulso de prueba) o un tier instrumental ≥ RESTRICTED en
  medio del drill lo ABORTA visiblemente (corta el voceo, banner de aborto) —
  el camino crítico ni se entera: el reflejo ya actuó antes de que este módulo
  observe nada.

El fin llega por ventana (`threading.Timer`), por `drill_stop` firmado o por
aborto. Módulo no-crítico: si falla, el gabinete sigue protegiendo.
"""

from __future__ import annotations

import logging
import threading

from takab_edge.contracts import SasmexSignal, Tier, TierDecision, utcnow
from takab_edge.gpio_link import as_link
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.drill")

#: Tiers instrumentales que abortan un simulacro (protección real en curso).
_ABORT_TIERS = (Tier.RESTRICTED, Tier.EVACUATE_OR_HOLD, Tier.MANUAL_ONLY)


def _evidencia_de_audio(audio) -> dict:  # noqa: ANN001 — módulo advisory opcional
    """Qué sonará en el simulacro, o por qué no sonará nada.

    **Nunca devuelve `None`.** Un `audio: null` y un «no había módulo de audio»
    son indistinguibles para quien lee el reporte al día siguiente, y el segundo
    es un hecho declarable: el voceo es advisory y el simulacro vive igual —
    banner y registro—, así que su ausencia no es un fallo que esconder.
    """
    if audio is None:
        return {
            "asset_id": None,
            "path": None,
            "sha256": None,
            "will_sound": False,
            "reason": "el gabinete no tiene módulo de audio: el simulacro corre sin voceo",
        }
    try:
        return dict(audio.simulacro_evidence())
    except Exception as exc:  # noqa: BLE001 — advisory: jamás al camino de vida
        log.exception("no se pudo resolver la evidencia de audio del simulacro (aislado)")
        return {
            "asset_id": None,
            "path": None,
            "sha256": None,
            "will_sound": False,
            "reason": f"no se pudo resolver el asset de voceo: {exc}",
        }


class DrillController(EdgeModule):
    """Estado del simulacro para el panel LAN + voceo advisory. Cero relés."""

    name = "drill"
    depends_on = ("gpio",)
    critical = False

    def __init__(self, settings, gpio, audio=None) -> None:
        super().__init__()
        self._settings = settings
        self._link = as_link(gpio)
        self._audio = audio
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._state: dict = {"active": False}

    # ------------------------------------------------------------------ estado
    def status(self) -> dict:
        """Sección `drill` del panel LAN (copia; el aborto queda visible)."""
        with self._lock:
            return dict(self._state)

    @property
    def active(self) -> bool:
        with self._lock:
            return bool(self._state.get("active"))

    # ------------------------------------------------------------------ control
    def start_drill(self, drill_id: str, duration_s: float) -> tuple[bool, str]:
        """Arranca el simulacro. (ok, motivo) — rechaza con alerta real viva.

        [T-2.70.a·D2/P1] El guard falla CERRADO. La lectura del enclave SASMEX
        cruza la costura, y si no se puede hacer el simulacro se RECHAZA: abrir
        arrancaría un simulacro institucional encima de un sismo real.

        Y devuelve `(False, motivo)` en vez de propagar: `dispatch` sólo atrapaba
        `(TypeError, ValueError)` alrededor de esta llamada, así que un `OSError`
        escapaba a su `except` genérico de `on_command` y el comando FIRMADO de la
        nube se quedaba SIN ACK — esperando el TTL sin saber por qué.
        """
        try:
            alerta_real = self._link.snapshot().sasmex_active
        except Exception:  # noqa: BLE001 — fail-closed: sin poder comprobar, no hay simulacro
            log.exception("no se pudo comprobar el enclave SASMEX; simulacro RECHAZADO")
            return False, (
                "no se pudo comprobar si hay una alerta SASMEX viva; simulacro "
                "rechazado (fail-closed)"
            )
        if alerta_real:
            return False, "alerta SASMEX real en curso; simulacro rechazado"
        duration = max(1.0, float(duration_s))
        started = utcnow()
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._state = {
                "active": True,
                "drill_id": drill_id,
                "started_at": started.isoformat(),
                "duration_s": duration,
                "aborted": False,
                "abort_reason": None,
                # [T-5.17] QUÉ va a sonar, resuelto UNA vez y aquí: de este mismo
                # sitio leen el panel y el acuse a la nube. Con dos resoluciones,
                # el documento de cumplimiento podría citar un asset y el altavoz
                # sacar otro.
                "audio": _evidencia_de_audio(self._audio),
            }
            timer = threading.Timer(duration, self._on_window_end)
            timer.daemon = True
            self._timer = timer
        timer.start()
        if self._audio is not None:
            try:
                # Voceo condicional al hardware (A-6): sin audio el drill vive
                # igual — banner + registro. play_simulacro ya es no-op si
                # audio_enabled=false.
                self._audio.play_simulacro()
            except Exception:  # noqa: BLE001 — advisory, jamás al camino de vida
                log.exception("voceo de simulacro falló (aislado)")
        log.warning("SIMULACRO iniciado (%s, %.0f s) — NO ES UNA ALERTA REAL", drill_id, duration)
        return True, "simulacro iniciado"

    def end_drill(self, drill_id: str | None = None, reason: str = "fin manual") -> bool:
        """Termina el drill (drill_stop firmado o fin manual). No es `stop()`
        del ciclo de vida de EdgeModule (lección A-6)."""
        with self._lock:
            if not self._state.get("active"):
                return False
            if drill_id is not None and self._state.get("drill_id") != drill_id:
                return False
            self._state = {**self._state, "active": False, "ended_reason": reason}
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._stop_voice()
        log.warning("SIMULACRO terminado (%s)", reason)
        return True

    def abort(self, reason: str) -> None:
        """Lo real GANA: corta el voceo y deja el aborto VISIBLE en el panel."""
        with self._lock:
            if not self._state.get("active"):
                return
            self._state = {
                **self._state,
                "active": False,
                "aborted": True,
                "abort_reason": reason,
                "ended_reason": f"abortado: {reason}",
            }
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._stop_voice()
        log.warning("SIMULACRO ABORTADO — %s (la alerta real manda)", reason)

    # ------------------------------------------------------------ observadores
    def on_sasmex(self, signal: SasmexSignal) -> None:
        """Cableado por el supervisor a gpio.on_sasmex: SASMEX real ⇒ aborto."""
        if signal.active and not signal.is_test:
            self.abort("SASMEX real")

    def on_tier(self, decision: TierDecision) -> None:
        """Hook del supervisor TRAS actuar los relés (como audio.on_tier)."""
        if decision.tier in _ABORT_TIERS:
            self.abort(f"tier instrumental {decision.tier.value}")

    # ------------------------------------------------------------------ interno
    def _on_window_end(self) -> None:
        self.end_drill(reason="fin de ventana")

    def _stop_voice(self) -> None:
        if self._audio is None:
            return
        try:
            self._audio.stop_playback()
        except Exception:  # noqa: BLE001 — advisory
            log.exception("no se pudo cortar el voceo del drill (aislado)")

    def _on_start(self) -> None:
        log.info("controlador de simulacros listo (observador; cero relés)")

    def _on_stop(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._state = {"active": False}
