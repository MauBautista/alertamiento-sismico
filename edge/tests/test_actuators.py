"""actuators — interfaz única, driver de relés primario y adaptador BACnet."""

from __future__ import annotations

import pytest
from simulators.bacnet import BacnetSimulator
from takab_edge.actuators import (
    ActuatorManager,
    BacnetActuator,
    RelayActuator,
)
from takab_edge.contracts import ActuatorAction, ActuatorChannel, ActuatorCommand
from takab_edge.gpio import GpioController


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


def test_manager_routes_gas_to_relay_as_primary(gpio):
    # [SUPUESTO #4] el primer driver por canal es el primario = relés.
    manager = ActuatorManager([RelayActuator(gpio), BacnetActuator(BacnetSimulator())])
    ack = manager.execute(_cmd(ActuatorChannel.GAS_VALVE))
    assert ack.detail == "relay"
    assert gpio.relay_state(ActuatorChannel.GAS_VALVE).energized is True


def test_manager_without_driver_fails_gracefully():
    manager = ActuatorManager([])
    ack = manager.execute(_cmd(ActuatorChannel.SIREN))
    assert ack.success is False
    assert "sin driver" in ack.detail


def test_execute_sequence_returns_all_acks(gpio):
    manager = ActuatorManager([RelayActuator(gpio)])
    acks = manager.execute_sequence(
        [_cmd(ActuatorChannel.ELEVATOR), _cmd(ActuatorChannel.DOOR_RETAINER)]
    )
    assert len(acks) == 2
    assert all(a.success for a in acks)
