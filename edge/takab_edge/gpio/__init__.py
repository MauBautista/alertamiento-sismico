"""gpio — WR-1 (contacto seco) + relés locales fail-safe + reflejo SASMEX→sirena.

[SUPUESTO plan-maestro-01 #6] Proceso mínimo y auditable (regla de oro 4). El
reflejo SASMEX→sirena ocurre **in-process** (<100 ms, blueprint §4.3), sin cruzar
IPC ni depender de la nube ni de IA. **Canal primario de alertamiento.**

T-1.3: reflejo con latencia medida, debounce 50 ms, botones de silencio y prueba,
relés fail-safe NO/NC/fail-close por canal con estado seguro (SPOF-07), y proceso
standalone mínimo (`python -m takab_edge.gpio`) sin dependencias pesadas.

**Estado por DEMANDAS (no escritura directa).** El estado eléctrico de cada canal
se RECALCULA (`_desired_energized`) a partir de demandas independientes —el reflejo
SASMEX enclavado, la secuencia de `rules`, el self-test del operador y el silencio—
y se aplica bajo un `RLock`. Así una demanda (p.ej. el fin de un self-test) NUNCA
puede llevar la sirena por debajo de la protección exigida por una alerta viva, y el
silencio apaga de inmediato lo que ya suena. Todas las transiciones se serializan
(hay varios hilos: callbacks de gpiozero, el `Timer` del self-test y `rules`).

**Modelo fail-safe (SPOF-07, blueprint §4.7).** El estado SEGURO es siempre el
DE-ENERGIZADO (una falla del Pi corta la energía del relé → contacto en reposo):
- `NO` (sirena/estrobo/ascensor): reposo de-energizado = inactivo; **activar = energizar**.
- `NC` (retenedor de puerta): reposo energizado (retiene); **activar = de-energizar** (libera).
- `fail_close` (gas): reposo energizado (abierto); **activar = de-energizar** (cierra).
La polaridad eléctrica real de cada relé se re-valida con hardware (**gate #3**).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from time import perf_counter

from takab_edge.config import EdgeSettings
from takab_edge.contracts import (
    ActuatorChannel,
    FailSafeMode,
    RelayState,
    SasmexSignal,
)
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.gpio")

#: Canales gobernados por relés locales de este módulo (SPOF-07).
LOCAL_RELAY_CHANNELS: tuple[ActuatorChannel, ...] = (
    ActuatorChannel.SIREN,
    ActuatorChannel.STROBE,
    ActuatorChannel.GAS_VALVE,
    ActuatorChannel.ELEVATOR,
    ActuatorChannel.DOOR_RETAINER,
)

#: Canales que dispara el reflejo inmediato SASMEX.
REFLEX_CHANNELS: tuple[ActuatorChannel, ...] = (
    ActuatorChannel.SIREN,
    ActuatorChannel.STROBE,
)

#: Canales AUDIBLES — el silencio del operador los inhibe (NFPA 72: silenciar audible).
AUDIBLE_CHANNELS: tuple[ActuatorChannel, ...] = (ActuatorChannel.SIREN,)

SasmexCallback = Callable[[SasmexSignal], None]


def normal_energized(mode: FailSafeMode) -> bool:
    """Estado eléctrico en operación normal (no-emergencia) para un modo fail-safe."""
    # NC/fail_close se sostienen ENERGIZADOS en reposo (retienen/mantienen abierto);
    # NO reposa de-energizado. Ver docstring del módulo.
    return mode in (FailSafeMode.NORMALLY_CLOSED, FailSafeMode.FAIL_CLOSE)


def active_energized(mode: FailSafeMode) -> bool:
    """Estado eléctrico en emergencia (acción de protección tomada)."""
    return not normal_energized(mode)


def ensure_dev_pin_factory() -> None:
    """En dev/CI usa la MockFactory de gpiozero (sin hardware físico).

    Idempotente: no reemplaza una MockFactory ya activa. En el Pi 5 real
    (``dev_mode=False``) NO se llama y gpiozero elige el backend nativo (lgpio).
    """
    from gpiozero import Device
    from gpiozero.pins.mock import MockFactory

    if not isinstance(Device.pin_factory, MockFactory):
        Device.pin_factory = MockFactory()


class GpioController(EdgeModule):
    """Controla la entrada WR-1 y los relés locales, y ejecuta el reflejo.

    El reflejo se dispara por ``when_pressed`` del contacto (evento, con debounce)
    y, de forma equivalente y determinista, vía :meth:`simulate_sasmex` (usado por
    el simulador WR-1 y los tests, sin depender del hilo de gpiozero).
    """

    name = "gpio"
    critical = True  # WR-1 + relés = el reflejo de vida; su fallo debe fail-fast

    def __init__(self, settings: EdgeSettings) -> None:
        super().__init__()
        self.settings = settings
        self._lock = threading.RLock()
        self._sasmex_callbacks: list[SasmexCallback] = []
        self._button = None  # gpiozero.Button (WR-1)
        self._silence_button = None
        self._test_button = None
        self._relays: dict[ActuatorChannel, object] = {}  # gpiozero.DigitalOutputDevice
        self._energized: dict[ActuatorChannel, bool] = {}
        # --- Demandas independientes que determinan el estado de cada canal ---
        self._sasmex_latched = False  # alerta SASMEX real asertada (enclavada)
        self._audible_silenced = False  # operador silenció los canales audibles
        self._siren_test_active = False  # self-test del operador energizando la sirena
        self._rules_demand: dict[ActuatorChannel, bool] = {}  # protección ordenada por `rules`
        self._safed = (
            False  # estado seguro forzado (drive_all_safe): todo de-energizado hasta reset()
        )
        self._last_reflex_latency_s: float | None = None
        self._test_timer: threading.Timer | None = None

    # --- Observadores + silencio ---
    def on_sasmex(self, callback: SasmexCallback) -> None:
        """Registra un callback no-reflejo (rules evalúa; cloud publica)."""
        self._sasmex_callbacks.append(callback)

    def silence_audibles(self, silenced: bool = True) -> None:
        """Silencio/re-armado del operador: apaga/reactiva los canales AUDIBLES.

        Actúa YA sobre lo que suena (no sólo inhibe futuros): recalcula la sirena.
        NO afecta al estrobo (alerta visual) ni al estado de alerta (`sasmex_active`
        sigue vigente), sólo al aviso audible. El re-armado vuelve a sonar si la
        alerta sigue enclavada. El botón físico alterna silencio↔re-armado.
        """
        with self._lock:
            self._audible_silenced = silenced
            for channel in AUDIBLE_CHANNELS:
                self._apply(channel)
        log.warning("audibles %s", "SILENCIADOS" if silenced else "RE-ARMADOS")

    @property
    def audible_silenced(self) -> bool:
        return self._audible_silenced

    @property
    def last_reflex_latency_s(self) -> float | None:
        """Latencia medida de la última ruta software del reflejo (SASMEX→relé)."""
        return self._last_reflex_latency_s

    @property
    def debounce_s(self) -> float:
        """Debounce del contacto WR-1 en segundos (parte del presupuesto §4.3)."""
        return self.settings.debounce_ms / 1000.0

    # --- Ciclo de vida ---
    def _on_start(self) -> None:
        if self.settings.dev_mode:
            ensure_dev_pin_factory()

        from gpiozero import Button, DigitalOutputDevice

        pins = self.settings.pins
        relay_pins = {
            ActuatorChannel.SIREN: pins.relay_siren,
            ActuatorChannel.STROBE: pins.relay_strobe,
            ActuatorChannel.GAS_VALVE: pins.relay_gas_valve,
            ActuatorChannel.ELEVATOR: pins.relay_elevator,
            ActuatorChannel.DOOR_RETAINER: pins.relay_door_retainer,
        }
        with self._lock:
            for channel, pin in relay_pins.items():
                # Estado inicial = operación normal por modo (NC/fail_close arrancan
                # energizados = reteniendo/abierto; NO arranca de-energizado = inactivo).
                initial = normal_energized(self._failsafe(channel))
                self._relays[channel] = DigitalOutputDevice(
                    pin, active_high=True, initial_value=initial
                )
                self._energized[channel] = initial

        # WR-1 dry-contact: cierre → LOW (pull-up). Debounce = presupuesto §4.3.
        bounce_s = self.debounce_s
        self._button = Button(pins.wr1_contact, pull_up=True, bounce_time=bounce_s)
        self._button.when_pressed = self._on_contact_closed
        self._button.when_released = self._on_contact_open

        # Botones locales: silencio (alterna) y prueba (self-test de sirena).
        self._silence_button = Button(pins.silence_button, pull_up=True, bounce_time=bounce_s)
        self._silence_button.when_pressed = self._on_silence_button
        self._test_button = Button(pins.test_button, pull_up=True, bounce_time=bounce_s)
        self._test_button.when_pressed = self._on_test_button

        self._seed_from_held_contact()

    def _seed_from_held_contact(self) -> None:
        """Siembra el reflejo si el contacto de alerta ya está cerrado al arrancar (SPOF-02).

        Tras un reinicio del Pi durante un evento con contacto latcheado NO habrá un flanco
        nuevo, así que leemos el NIVEL del contacto para no dejar la sirena muda en el
        traspaso HW→software. Dirección segura: sonar (el operador puede silenciar).
        """
        if self._button is not None and self._button.is_pressed:
            self._dispatch_sasmex(active=True, is_test=False)

    def _on_stop(self) -> None:
        with self._lock:
            if self._test_timer is not None:
                self._test_timer.cancel()
                self._test_timer = None
            # Parada limpia → todo a estado seguro (de-energizado) antes de soltar pines.
            self.drive_all_safe()
            for device in (self._button, self._silence_button, self._test_button):
                if device is not None:
                    device.close()
            for relay in self._relays.values():
                relay.close()
            self._relays.clear()
            self._energized.clear()
            self._button = self._silence_button = self._test_button = None

    # --- Reflejo (camino de vida, in-process, con latencia medida) ---
    def _on_contact_closed(self) -> None:
        self._dispatch_sasmex(active=True, is_test=False)

    def _on_contact_open(self) -> None:
        self._dispatch_sasmex(active=False, is_test=False)

    def simulate_sasmex(self, active: bool, is_test: bool = False) -> SasmexSignal:
        """Entrada determinista equivalente a ``when_pressed`` (tests/simulador)."""
        return self._dispatch_sasmex(active=active, is_test=is_test)

    def _dispatch_sasmex(self, *, active: bool, is_test: bool) -> SasmexSignal:
        signal = SasmexSignal(active=active, is_test=is_test)
        with self._lock:
            # El pulso de prueba de CIRES NO actúa (SPOF-03: sólo heartbeat).
            # La apertura del contacto (active=False) NO desenclava: la alerta persiste
            # hasta que el operador silencie/re-arme (semántica de latching real = gate #3).
            if active and not is_test:
                started = perf_counter()
                # Una alarma NUEVA (flanco del contacto) siempre RE-SUENA (NFPA-72:
                # el silencio del operador acusa el episodio actual, no muta futuros).
                self._audible_silenced = False
                self._sasmex_latched = True
                for channel in REFLEX_CHANNELS:
                    self._apply(channel)
                self._last_reflex_latency_s = perf_counter() - started
                log.warning(
                    "REFLEJO SASMEX→sirena in-process (%.2f ms)",
                    self._last_reflex_latency_s * 1000.0,
                )
            callbacks = list(self._sasmex_callbacks)
        for callback in callbacks:  # fuera del lock: pueden re-entrar (rules/cloud)
            callback(signal)
        return signal

    # --- Botones locales ---
    def _on_silence_button(self) -> None:
        self.silence_audibles(not self._audible_silenced)

    def _on_test_button(self) -> None:
        self.run_siren_test()

    def run_siren_test(self, duration_s: float | None = None) -> None:
        """Self-test de sirena iniciado por el operador (suena aun si está silenciada).

        A diferencia del pulso de prueba de CIRES (heartbeat, no actúa), es una prueba
        deliberada. Se modela como una demanda aparte (`_siren_test_active`), así que su
        fin NUNCA apaga una alerta viva: sólo retira la demanda de prueba y recalcula.
        """
        duration = duration_s if duration_s is not None else self.settings.siren_test_duration_s
        with self._lock:
            self._siren_test_active = True
            self._apply(ActuatorChannel.SIREN)
            if self._test_timer is not None:
                self._test_timer.cancel()
            timer = threading.Timer(duration, self._end_siren_test)
            timer.daemon = True
            self._test_timer = timer
        timer.start()
        log.warning("self-test de sirena (%.1f s)", duration)

    def _end_siren_test(self) -> None:
        with self._lock:
            self._siren_test_active = False
            self._apply(ActuatorChannel.SIREN)  # vuelve al estado que exija la protección vigente

    # --- Relés: demandas de `rules` (capa lógica) + recálculo (capa eléctrica) ---
    def activate(self, channel: ActuatorChannel) -> None:
        """Ordena la PROTECCIÓN (emergencia) del canal desde `rules`/`actuators`."""
        with self._lock:
            # Una orden NUEVA de alarma audible (flanco de la demanda de rules) re-suena,
            # aun si el operador silenció un episodio anterior (§4.5 instrumental; NFPA-72).
            # La semántica de episodio para alertas rules sostenidas se afina en T-1.8.
            if channel in AUDIBLE_CHANNELS and not self._rules_demand.get(channel, False):
                self._audible_silenced = False
            self._rules_demand[channel] = True
            self._apply(channel)

    def deactivate(self, channel: ActuatorChannel) -> None:
        """Retira la orden de protección de `rules` (vuelve a normal si nadie más la exige)."""
        with self._lock:
            self._rules_demand[channel] = False
            self._apply(channel)

    def set_relay(self, channel: ActuatorChannel, on: bool) -> None:
        """Comanda un canal (usado por `actuators`/`rules`): on=activar la protección."""
        if channel not in self._energized:
            raise KeyError(f"canal de relé desconocido: {channel}")
        self.activate(channel) if on else self.deactivate(channel)

    def drive_all_safe(self) -> None:
        """Estado seguro DURABLE: de-energiza todo (corte de energía) hasta `reset()`.

        Fija `_safed`, así que un `_apply` posterior NO revierte el estado seguro
        (p.ej. no reabre el gas). Sólo un `reset()` explícito vuelve a operación normal.
        """
        with self._lock:
            self._safed = True
            for channel in LOCAL_RELAY_CHANNELS:
                self._apply(channel)

    def reset(self) -> None:
        """Vuelve a operación normal idle: limpia alerta, silencio, prueba, demandas y safe."""
        with self._lock:
            self._sasmex_latched = False
            self._audible_silenced = False
            self._siren_test_active = False
            self._safed = False
            self._rules_demand.clear()
            if self._test_timer is not None:
                self._test_timer.cancel()
                self._test_timer = None
            for channel in LOCAL_RELAY_CHANNELS:
                self._apply(channel)

    def _alert_demand(self, channel: ActuatorChannel) -> bool:
        """¿Alguna alerta (reflejo SASMEX enclavado o `rules`) exige proteger el canal?"""
        reflex = self._sasmex_latched and channel in REFLEX_CHANNELS
        return reflex or self._rules_demand.get(channel, False)

    def _desired_energized(self, channel: ActuatorChannel) -> bool:
        """Estado eléctrico objetivo del canal según sus demandas (bajo lock)."""
        if self._safed:
            return False  # estado seguro forzado: todo de-energizado hasta reset()
        demand = self._alert_demand(channel)
        if channel in AUDIBLE_CHANNELS:
            protective = (demand and not self._audible_silenced) or self._siren_test_active
        else:
            protective = demand  # visuales/fail-safe: el silencio no los toca
        mode = self._failsafe(channel)
        return active_energized(mode) if protective else normal_energized(mode)

    def _apply(self, channel: ActuatorChannel) -> None:
        """Recalcula y aplica el estado eléctrico del canal (llamar bajo `_lock`)."""
        target = self._desired_energized(channel)
        relay = self._relays.get(channel)
        if relay is not None:
            relay.on() if target else relay.off()
        self._energized[channel] = target

    def _failsafe(self, channel: ActuatorChannel) -> FailSafeMode:
        return self.settings.failsafe.get(channel, FailSafeMode.NORMALLY_OPEN)

    def is_activated(self, channel: ActuatorChannel) -> bool:
        """True si el canal está en su estado de protección (agnóstico de polaridad)."""
        with self._lock:
            return self._energized[channel] == active_energized(self._failsafe(channel))

    def relay_state(self, channel: ActuatorChannel) -> RelayState:
        with self._lock:
            energized = self._energized[channel]
            return RelayState(
                channel=channel,
                energized=energized,
                activated=energized == active_energized(self._failsafe(channel)),
                fail_safe=self._failsafe(channel),
            )

    def relay_states(self) -> list[RelayState]:
        return [self.relay_state(channel) for channel in LOCAL_RELAY_CHANNELS]

    @property
    def sasmex_active(self) -> bool:
        """Alerta SASMEX real asertada (enclavada) — NO derivada del estado del relé."""
        return self._sasmex_latched

    @property
    def siren_sounding(self) -> bool:
        """¿La sirena audible está sonando físicamente ahora mismo?"""
        with self._lock:
            energized = self._energized.get(ActuatorChannel.SIREN, False)
            return energized == active_energized(self._failsafe(ActuatorChannel.SIREN))
