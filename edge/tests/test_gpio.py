"""gpio — reflejo SASMEX→sirena in-process, fail-safe por canal y cableado WR-1."""

from __future__ import annotations

import pytest
from takab_edge.contracts import ActuatorChannel, FailSafeMode, SasmexSignal
from takab_edge.gpio import REFLEX_CHANNELS, GpioController


@pytest.fixture
def gpio(settings):
    controller = GpioController(settings)
    controller.start()
    try:
        yield controller
    finally:
        controller.stop()


def test_sasmex_reflex_energizes_siren_and_strobe(gpio):
    gpio.simulate_sasmex(active=True)
    for channel in REFLEX_CHANNELS:
        assert gpio.relay_state(channel).energized is True
    assert gpio.sasmex_active is True


def test_silence_button_inhibits_reflex_but_still_notifies(gpio):
    received: list[SasmexSignal] = []
    gpio.on_sasmex(received.append)
    gpio.set_reflex_enabled(False)

    gpio.simulate_sasmex(active=True)
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is False
    assert received and received[0].active is True  # rules/cloud sí se enteran


def test_cires_test_pulse_does_not_actuate(gpio):
    gpio.simulate_sasmex(active=True, is_test=True)
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is False


def test_relay_states_carry_failsafe_profile(gpio):
    by_channel = {r.channel: r for r in gpio.relay_states()}
    assert by_channel[ActuatorChannel.SIREN].fail_safe is FailSafeMode.NORMALLY_OPEN
    assert by_channel[ActuatorChannel.DOOR_RETAINER].fail_safe is FailSafeMode.NORMALLY_CLOSED
    assert by_channel[ActuatorChannel.GAS_VALVE].fail_safe is FailSafeMode.FAIL_CLOSE
    assert len(by_channel) == 5


def test_unknown_relay_channel_raises(gpio):
    class Fake:
        value = "nope"

    with pytest.raises(KeyError):
        gpio.set_relay(Fake(), True)  # type: ignore[arg-type]


def test_wr1_mock_pin_wiring(gpio):
    # El contacto seco cierra a masa (pull-up): pin en LOW ⇒ contacto cerrado.
    assert gpio._button is not None
    gpio._button.pin.drive_high()
    assert gpio._button.is_pressed is False
    gpio._button.pin.drive_low()
    assert gpio._button.is_pressed is True
