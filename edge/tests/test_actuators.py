"""actuators — interfaz única, driver de relés primario y adaptador BACnet por contrato."""

from __future__ import annotations

from datetime import timedelta

import pytest
from simulators.bacnet import BacnetSimulator
from takab_edge.actuators import (
    ActuatorManager,
    BacnetActuator,
    RelayActuator,
)
from takab_edge.contracts import (
    ActuatorAction,
    ActuatorChannel,
    ActuatorCommand,
    utcnow,
)
from takab_edge.gpio import GpioController

EXTENDED = [
    ActuatorChannel.GAS_VALVE,
    ActuatorChannel.ELEVATOR,
    ActuatorChannel.DOOR_RETAINER,
]


@pytest.fixture
def gpio(settings):
    controller = GpioController(settings)
    controller.start()
    try:
        yield controller
    finally:
        controller.stop()


def _cmd(channel, action=ActuatorAction.ACTIVATE):
    return ActuatorCommand(channel=channel, action=action, event_id="evt-1")


def test_relay_actuator_energizes_and_acks(gpio):
    ack = RelayActuator(gpio).execute(_cmd(ActuatorChannel.SIREN))
    assert ack.success is True
    assert ack.latency_s >= 0.0
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is True


def test_bacnet_actuator_writes_via_simulator():
    sim = BacnetSimulator()
    ack = BacnetActuator(sim).execute(_cmd(ActuatorChannel.GAS_VALVE))
    assert ack.success is True
    assert ack.detail == "bacnet"
    assert sim.present_values[ActuatorChannel.GAS_VALVE] is True


def test_manager_routes_to_relay_by_default(gpio):
    # [SUPUESTO #4] sin contrato BACnet, todo va por relé local fail-safe.
    manager = ActuatorManager(RelayActuator(gpio), BacnetActuator(BacnetSimulator()))
    ack = manager.execute(_cmd(ActuatorChannel.GAS_VALVE))
    assert ack.detail == "relay"
    # Gas es fail-close: activar = CERRAR = de-energizar. El canal queda "activado".
    state = gpio.relay_state(ActuatorChannel.GAS_VALVE)
    assert state.activated is True
    assert state.energized is False


def test_extended_sequence_routes_to_bacnet_by_contract(gpio):
    sim = BacnetSimulator()
    manager = ActuatorManager(RelayActuator(gpio), BacnetActuator(sim), bacnet_channels=EXTENDED)
    gas = manager.execute(_cmd(ActuatorChannel.GAS_VALVE))
    assert gas.detail == "bacnet"
    assert sim.present_values[ActuatorChannel.GAS_VALVE] is True
    # La sirena, aun con contrato BACnet, va SIEMPRE por relé local (vida audible).
    siren = manager.execute(_cmd(ActuatorChannel.SIREN))
    assert siren.detail == "relay"
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is True


def test_siren_never_routes_to_bacnet_even_if_misconfigured(gpio):
    sim = BacnetSimulator()
    manager = ActuatorManager(
        RelayActuator(gpio),
        BacnetActuator(sim),
        bacnet_channels=[ActuatorChannel.SIREN, ActuatorChannel.GAS_VALVE],  # sirena mal puesta
    )
    ack = manager.execute(_cmd(ActuatorChannel.SIREN))
    assert ack.detail == "relay"  # filtrada de BACnet
    assert ActuatorChannel.SIREN not in sim.present_values


def test_ack_latency_relative_to_issued_at(gpio):
    # El ACK reporta T+X.XXs desde que `rules` emitió el comando (no la duración del driver).
    cmd = ActuatorCommand(
        channel=ActuatorChannel.SIREN,
        action=ActuatorAction.ACTIVATE,
        event_id="evt-1",
        issued_at=utcnow() - timedelta(seconds=0.5),
    )
    ack = RelayActuator(gpio).execute(cmd)
    assert ack.latency_s >= 0.4
    assert ack.relative_label.startswith("T+")


def test_execute_sequence_returns_and_collects_acks(gpio):
    manager = ActuatorManager(RelayActuator(gpio))
    acks = manager.execute_sequence(
        [_cmd(ActuatorChannel.ELEVATOR), _cmd(ActuatorChannel.DOOR_RETAINER)]
    )
    assert len(acks) == 2
    assert all(a.success for a in acks)
    assert len(manager.last_acks) == 2


def test_bacnet_write_failure_surfaces_in_ack(gpio):
    sim = BacnetSimulator()
    sim.online = False  # pasarela BACnet caída
    manager = ActuatorManager(RelayActuator(gpio), BacnetActuator(sim), bacnet_channels=EXTENDED)
    ack = manager.execute(_cmd(ActuatorChannel.GAS_VALVE))
    assert ack.success is False  # el fallo de ejecución se refleja en el ACK


class _RaisingDriver:
    """Driver que LANZA al ejecutar (simula el BACnet real con timeout de comms)."""

    channels = (ActuatorChannel.ELEVATOR,)

    def execute(self, command):
        raise RuntimeError("BACnet timeout")


def test_execute_sequence_isolates_a_raising_driver(gpio):
    # Aislamiento de fallo (vida): un driver que lanza NO debe abortar el resto de la
    # secuencia; los canales siguientes (gas) DEBEN accionarse igual (best-effort).
    manager = ActuatorManager(
        RelayActuator(gpio), _RaisingDriver(), bacnet_channels=[ActuatorChannel.ELEVATOR]
    )
    acks = manager.execute_sequence(
        [_cmd(ActuatorChannel.ELEVATOR), _cmd(ActuatorChannel.GAS_VALVE)]
    )
    assert len(acks) == 2
    assert acks[0].success is False and "excepción" in acks[0].detail
    assert acks[1].success is True  # el gas se accionó pese al fallo del ascensor
