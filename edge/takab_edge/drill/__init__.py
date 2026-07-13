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
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.drill")

#: Tiers instrumentales que abortan un simulacro (protección real en curso).
_ABORT_TIERS = (Tier.RESTRICTED, Tier.EVACUATE_OR_HOLD, Tier.MANUAL_ONLY)


class DrillController(EdgeModule):
    """Estado del simulacro para el panel LAN + voceo advisory. Cero relés."""

    name = "drill"
    depends_on = ("gpio",)
    critical = False

    def __init__(self, settings, gpio, audio=None) -> None:
        super().__init__()
        self._settings = settings
        self._gpio = gpio
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
        """Arranca el simulacro. (ok, motivo) — rechaza con alerta real viva."""
        if self._gpio.sasmex_active:
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
