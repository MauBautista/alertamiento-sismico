"""Simulador de device BACnet/IP — gas / ascensores / puertas (sin hardware).

Implementa el protocolo mínimo `BacnetClient` que consume `BacnetActuator`:
registra las escrituras de present-value y confirma la ejecución (ACK). El stack
BACnet/IP real (`bacpypes3`/`BAC0`, extra ``[bacnet]``) es T-1.9.
"""

from __future__ import annotations

from takab_edge.contracts import ActuatorChannel


class BacnetSimulator:
    """Device BACnet/IP mock que confirma escrituras de present-value."""

    def __init__(self) -> None:
        self.present_values: dict[ActuatorChannel, bool] = {}
        self.writes: list[tuple[ActuatorChannel, bool]] = []
        self.online = True

    def write_present_value(self, channel: ActuatorChannel, active: bool) -> bool:
        """Escribe el present-value del objeto BACnet y confirma (ACK=True si online)."""
        if not self.online:
            return False
        self.present_values[channel] = active
        self.writes.append((channel, active))
        return True
