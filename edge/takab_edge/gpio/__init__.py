"""gpio — WR-1 (contacto seco) + relés locales fail-safe + reflejo SASMEX→sirena.

[SUPUESTO plan-maestro-01 #6] Proceso mínimo y auditable (regla de oro 4). El
reflejo SASMEX→sirena ocurre **in-process** (<100 ms, blueprint §4.3), sin cruzar
IPC ni depender de la nube ni de IA. **Canal primario de alertamiento.**

Scaffold de T-1.2: establece la interfaz, el cableado gpiozero (real o MockFactory
en dev/CI) y el reflejo determinista. El endurecimiento —debounce 50 ms medido,
1000 ciclos, latencia <100 ms verificada, botón silencio/prueba, semántica real de
contactos del WR-1— es **T-1.3** (gate de hardware #3).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

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

#: Canales que dispara el reflejo inmediato SASMEX→(sirena+estrobo).
REFLEX_CHANNELS: tuple[ActuatorChannel, ...] = (
    ActuatorChannel.SIREN,
    ActuatorChannel.STROBE,
)

SasmexCallback = Callable[[SasmexSignal], None]


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

    El reflejo se dispara por ``when_pressed`` del contacto (evento) y, de forma
    equivalente y determinista, vía :meth:`simulate_sasmex` (usado por el
    simulador WR-1 y por los tests, sin depender del hilo de gpiozero).
    """

    name = "gpio"

    def __init__(self, settings: EdgeSettings) -> None:
        super().__init__()
        self.settings = settings
        self._reflex_enabled = True
        self._sasmex_callbacks: list[SasmexCallback] = []
        self._button = None  # gpiozero.Button (WR-1)
        self._relays: dict[ActuatorChannel, object] = {}  # gpiozero.DigitalOutputDevice
        self._energized: dict[ActuatorChannel, bool] = dict.fromkeys(LOCAL_RELAY_CHANNELS, False)

    # --- Registro de observadores (rules/cloud reciben la señal, no la reflejan) ---
    def on_sasmex(self, callback: SasmexCallback) -> None:
        """Registra un callback no-reflejo (rules evalúa; cloud publica)."""
        self._sasmex_callbacks.append(callback)

    def set_reflex_enabled(self, enabled: bool) -> None:
        """Botón de silencio: habilita/inhibe los canales audibles (sirena/estrobo).

        Al inhibir, NINGUNA ruta los (re)energiza —ni el reflejo SASMEX ni la
        secuencia de `rules`—; apagar siempre se permite. El re-armado y la
        escalada (una alerta mayor debe volver a sonar) son **T-1.3**.
        """
        self._reflex_enabled = enabled

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
        for channel, pin in relay_pins.items():
            # active_high=True: energizar → HIGH. La semántica fail-safe real
            # (NO/NC/fail-close) se cablea al relé físico en T-1.3/T-1.9.
            self._relays[channel] = DigitalOutputDevice(pin, active_high=True, initial_value=False)
            self._energized[channel] = False

        # WR-1 dry-contact: cierre → LOW (pull-up). bounce_time real = T-1.3.
        self._button = Button(pins.wr1_contact, pull_up=True)
        self._button.when_pressed = self._on_contact_closed
        self._button.when_released = self._on_contact_open

    def _on_stop(self) -> None:
        for relay in self._relays.values():
            relay.close()  # gpiozero: libera el pin
        if self._button is not None:
            self._button.close()
        self._relays.clear()
        self._button = None

    # --- Reflejo (camino de vida, in-process) ---
    def _on_contact_closed(self) -> None:
        self._dispatch_sasmex(active=True, is_test=False)

    def _on_contact_open(self) -> None:
        self._dispatch_sasmex(active=False, is_test=False)

    def simulate_sasmex(self, active: bool, is_test: bool = False) -> SasmexSignal:
        """Entrada determinista equivalente a ``when_pressed`` (tests/simulador)."""
        return self._dispatch_sasmex(active=active, is_test=is_test)

    def _dispatch_sasmex(self, *, active: bool, is_test: bool) -> SasmexSignal:
        signal = SasmexSignal(active=active, is_test=is_test)
        # El pulso de prueba de CIRES NO dispara actuadores (SPOF-03: sólo heartbeat).
        if active and not is_test and self._reflex_enabled:
            for channel in REFLEX_CHANNELS:
                self._energize(channel, True)
            log.warning("REFLEJO SASMEX→sirena (in-process)")
        for callback in self._sasmex_callbacks:
            callback(signal)
        return signal

    # --- Relés ---
    def _energize(self, channel: ActuatorChannel, on: bool) -> None:
        # Silencio activo: no (re)energizar canales audibles por NINGUNA ruta
        # (reflejo o secuencia de rules). Apagar (on=False) siempre se permite.
        if on and channel in REFLEX_CHANNELS and not self._reflex_enabled:
            return
        relay = self._relays.get(channel)
        if relay is not None:
            relay.on() if on else relay.off()
        self._energized[channel] = on

    def set_relay(self, channel: ActuatorChannel, on: bool) -> None:
        """Comanda un relé (usado por `actuators`/`rules` para secuencias)."""
        if channel not in self._energized:
            raise KeyError(f"canal de relé desconocido: {channel}")
        self._energize(channel, on)

    def relay_state(self, channel: ActuatorChannel) -> RelayState:
        return RelayState(
            channel=channel,
            energized=self._energized[channel],
            fail_safe=self.settings.failsafe.get(channel, FailSafeMode.NORMALLY_OPEN),
        )

    def relay_states(self) -> list[RelayState]:
        return [self.relay_state(channel) for channel in LOCAL_RELAY_CHANNELS]

    @property
    def sasmex_active(self) -> bool:
        return any(self._energized[channel] for channel in REFLEX_CHANNELS)
