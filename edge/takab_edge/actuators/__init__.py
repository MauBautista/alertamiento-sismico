"""actuators — interfaz `Actuator` única + driver de relés + adaptador BACnet/IP.

[SUPUESTO plan-maestro-01 #4] Driver primario = **relés fail-safe** del módulo
`gpio`; el adaptador **BACnet/IP** (gas, ascensores, puertas) vive detrás de la
MISMA interfaz `Actuator`, **activable por contrato** (`bacnet_channels`). Un override
del supuesto sólo cambia qué driver es el primario, nunca el motor de reglas.

La **sirena y el estrobo** (alerta audible/visual de vida) van SIEMPRE por relé local
directo — nunca por BACnet, para no depender de una pasarela de terceros en el camino
de vida. Cada acción devuelve un `ActuatorAck` con timestamp relativo al comando
(`T+0.42s`). En dev/tests el adaptador BACnet usa el simulador (mock, sin hardware);
el driver real (`bacpypes3`/`BAC0`) es el extra ``[bacnet]`` (gate hardware).
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from takab_edge.contracts import (
    ActuatorAck,
    ActuatorChannel,
    ActuatorCommand,
    utcnow,
)
from takab_edge.gpio import GpioController
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.actuators")

#: Canales que NUNCA se enrutan a BACnet (vida audible/visual = relé local directo).
RELAY_ONLY: tuple[ActuatorChannel, ...] = (ActuatorChannel.SIREN, ActuatorChannel.STROBE)


def _ack(command: ActuatorCommand, *, success: bool, detail: str) -> ActuatorAck:
    # Latencia = tiempo desde que `rules` emitió el comando hasta su ejecución (T+X.XXs).
    latency_s = max(0.0, (utcnow() - command.issued_at).total_seconds())
    return ActuatorAck(
        channel=command.channel,
        action=command.action,
        event_id=command.event_id,
        success=success,
        latency_s=latency_s,
        detail=detail,
    )


@runtime_checkable
class Actuator(Protocol):
    """Contrato único que `rules`/`ActuatorManager` consumen para accionar un canal."""

    channels: tuple[ActuatorChannel, ...]

    def execute(self, command: ActuatorCommand) -> ActuatorAck:
        """Ejecuta el comando y devuelve un ACK con latencia medida."""
        ...


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
        on = command.action == command.action.ACTIVATE
        self._gpio.set_relay(command.channel, on)
        return _ack(command, success=True, detail="relay")


@runtime_checkable
class BacnetClient(Protocol):
    """Cliente BACnet/IP mínimo (implementado por el simulador y, en prod, por BAC0)."""

    def write_present_value(self, channel: ActuatorChannel, active: bool) -> bool: ...


class BacnetActuator:
    """Adaptador BACnet/IP (gas/ascensores/puertas), detrás de la misma interfaz.

    En dev usa el simulador BACnet (mock). El driver real con `bacpypes3`/`BAC0` es el
    extra ``[bacnet]`` (gate hardware).
    """

    channels = (
        ActuatorChannel.GAS_VALVE,
        ActuatorChannel.ELEVATOR,
        ActuatorChannel.DOOR_RETAINER,
    )

    def __init__(self, client: BacnetClient) -> None:
        self._client = client

    def execute(self, command: ActuatorCommand) -> ActuatorAck:
        on = command.action == command.action.ACTIVATE
        ok = self._client.write_present_value(command.channel, on)
        return _ack(command, success=ok, detail="bacnet")


class ActuatorManager(EdgeModule):
    """Enruta cada comando a su driver (relé por defecto; BACnet por contrato) y colecciona ACKs."""

    name = "actuators"
    depends_on = ("gpio",)
    critical = True  # driver de relés/BACnet que toca sirena/gas/puertas; fail-fast

    def __init__(
        self,
        relay: Actuator,
        bacnet: Actuator | None = None,
        bacnet_channels: Iterable[ActuatorChannel] = (),
    ) -> None:
        super().__init__()
        self._relay = relay
        self._bacnet = bacnet
        # La sirena/estrobo nunca van por BACnet (vida audible = relé local directo).
        self._bacnet_channels = {c for c in bacnet_channels if c not in RELAY_ONLY}
        # Ventana rodante de ACKs (evita crecimiento sin límite en un EVACUATE sostenido).
        self._acks: deque[ActuatorAck] = deque(maxlen=256)

    def _driver_for(self, channel: ActuatorChannel) -> Actuator:
        if self._bacnet is not None and channel in self._bacnet_channels:
            return self._bacnet
        return self._relay

    def execute(self, command: ActuatorCommand) -> ActuatorAck:
        # Aislamiento de fallo: un actuador que LANZA (p.ej. BACnet real por timeout) NO
        # debe abortar la secuencia; devolvemos un ACK fallido y seguimos (best-effort).
        try:
            ack = self._driver_for(command.channel).execute(command)
        except Exception as exc:  # noqa: BLE001 — vida: nunca abortar el resto de la secuencia
            ack = _ack(command, success=False, detail=f"excepción: {exc}")
            log.exception("actuador %s lanzó excepción", command.channel.value)
        self._acks.append(ack)
        if ack.success:
            log.info(
                "actuador %s %s vía %s (%s)",
                command.channel.value,
                command.action.value,
                ack.detail,
                ack.relative_label,
            )
        else:
            log.warning(
                "actuador %s %s FALLÓ (%s, %s)",
                command.channel.value,
                command.action.value,
                ack.detail,
                ack.relative_label,
            )
        return ack

    def execute_sequence(self, commands: Sequence[ActuatorCommand]) -> list[ActuatorAck]:
        """Ejecuta la secuencia del tier best-effort (cada canal se intenta y se ACKea)."""
        return [self.execute(command) for command in commands]

    @property
    def last_acks(self) -> list[ActuatorAck]:
        return list(self._acks)

    def _on_start(self) -> None:
        bacnet = sorted(c.value for c in self._bacnet_channels) if self._bacnet else []
        log.info("actuadores listos (BACnet por contrato: %s; resto por relé local)", bacnet or "—")
