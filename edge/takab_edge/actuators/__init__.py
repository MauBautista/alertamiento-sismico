"""actuators — interfaz `Actuator` única + driver de relés + adaptador BACnet/IP.

[SUPUESTO plan-maestro-01 #4] Driver primario = **relés fail-safe** del módulo
`gpio`; el adaptador **BACnet/IP** (gas, ascensores, puertas) vive detrás de la
MISMA interfaz `Actuator`, activable por contrato. Un override del supuesto sólo
cambia qué driver es el primario, nunca el motor de reglas.

Scaffold de T-1.2: interfaz + driver de relés funcional (sobre gpio) + adaptador
BACnet contra el simulador (mock, sin hardware) + ACK con latencia. La secuencia
extendida y los ACK con timestamps reales son **T-1.9**.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from time import perf_counter
from typing import Protocol, runtime_checkable

from takab_edge.contracts import (
    ActuatorAck,
    ActuatorChannel,
    ActuatorCommand,
)
from takab_edge.gpio import GpioController
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.actuators")


@runtime_checkable
class Actuator(Protocol):
    """Contrato único que `rules` consume para accionar un canal."""

    channels: tuple[ActuatorChannel, ...]

    def execute(self, command: ActuatorCommand) -> ActuatorAck:
        """Ejecuta el comando y devuelve un ACK con latencia medida."""
        ...


def _ack(command: ActuatorCommand, started: float, *, success: bool, detail: str) -> ActuatorAck:
    return ActuatorAck(
        channel=command.channel,
        action=command.action,
        event_id=command.event_id,
        success=success,
        latency_s=perf_counter() - started,
        detail=detail,
    )


class RelayActuator:
    """Driver primario: acciona los relés locales fail-safe vía `gpio`."""

    channels = (
        ActuatorChannel.SIREN,
        ActuatorChannel.STROBE,
        ActuatorChannel.GAS_VALVE,
        ActuatorChannel.ELEVATOR,
        ActuatorChannel.DOOR_RETAINER,
    )

    def __init__(self, gpio: GpioController) -> None:
        self._gpio = gpio

    def execute(self, command: ActuatorCommand) -> ActuatorAck:
        started = perf_counter()
        on = command.action == command.action.ACTIVATE
        self._gpio.set_relay(command.channel, on)
        ack = _ack(command, started, success=True, detail="relay")
        log.info("relé %s %s (%s)", command.channel.value, command.action.value, ack.relative_label)
        return ack


@runtime_checkable
class BacnetClient(Protocol):
    """Cliente BACnet/IP mínimo (implementado por el simulador y, en T-1.9, por BAC0)."""

    def write_present_value(self, channel: ActuatorChannel, active: bool) -> bool: ...


class BacnetActuator:
    """Adaptador BACnet/IP (gas/ascensores/puertas), detrás de la misma interfaz.

    En dev usa el simulador BACnet (mock). El driver real con `bacpypes3`/`BAC0`
    es T-1.9 (extra ``[bacnet]``).
    """

    channels = (
        ActuatorChannel.GAS_VALVE,
        ActuatorChannel.ELEVATOR,
        ActuatorChannel.DOOR_RETAINER,
    )

    def __init__(self, client: BacnetClient) -> None:
        self._client = client

    def execute(self, command: ActuatorCommand) -> ActuatorAck:
        started = perf_counter()
        on = command.action == command.action.ACTIVATE
        ok = self._client.write_present_value(command.channel, on)
        return _ack(command, started, success=ok, detail="bacnet")


class ActuatorManager(EdgeModule):
    """Enruta comandos al driver del canal y colecciona ACKs (fuente única para `rules`)."""

    name = "actuators"
    depends_on = ("gpio",)

    def __init__(self, drivers: Iterable[Actuator]) -> None:
        super().__init__()
        self._by_channel: dict[ActuatorChannel, Actuator] = {}
        for driver in drivers:
            for channel in driver.channels:
                # El primer driver registrado por canal es el primario (relés).
                self._by_channel.setdefault(channel, driver)

    def _on_start(self) -> None:
        log.info("actuadores listos: %s", sorted(c.value for c in self._by_channel))

    def execute(self, command: ActuatorCommand) -> ActuatorAck:
        driver = self._by_channel.get(command.channel)
        if driver is None:
            return ActuatorAck(
                channel=command.channel,
                action=command.action,
                event_id=command.event_id,
                success=False,
                latency_s=0.0,
                detail="sin driver para el canal",
            )
        return driver.execute(command)

    def execute_sequence(self, commands: Sequence[ActuatorCommand]) -> list[ActuatorAck]:
        return [self.execute(command) for command in commands]
