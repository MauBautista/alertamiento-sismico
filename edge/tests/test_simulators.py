"""Simuladores RS4D / WR-1 / BACnet — el edge se levanta sin hardware físico."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO

import numpy as np
import pytest
from simulators.bacnet import BacnetSimulator
from simulators.rs4d import DEFAULT_CHANNELS, RS4DSimulator
from simulators.wr1 import WR1Simulator
from takab_edge.contracts import ActuatorChannel
from takab_edge.gpio import GpioController

START = datetime(2026, 1, 1, tzinfo=UTC)


def test_rs4d_packet_is_100_sps():
    sim = RS4DSimulator()
    packet = sim.packet("EHZ", START)
    assert packet.sample_rate == 100.0
    assert packet.npts == 100
    assert DEFAULT_CHANNELS == ("EHZ", "ENZ", "ENN", "ENE")


def test_rs4d_event_injection_raises_amplitude():
    sim = RS4DSimulator(seed=7)
    quiet = np.abs(sim.packet("ENZ", START).samples).max()
    loud = np.abs(sim.packet("ENZ", START, peak_counts=200_000.0).samples).max()
    assert loud > quiet * 10


def test_rs4d_stream_advances_time_and_is_finite():
    sim = RS4DSimulator()
    packets = list(sim.stream(channel="EHZ", start=START, seconds=3))
    assert len(packets) == 3
    assert (packets[1].starttime - packets[0].starttime).total_seconds() == 1.0


def test_rs4d_miniseed_is_parseable_by_obspy():
    from obspy import read

    sim = RS4DSimulator(station="TAKAB")
    packet = sim.packet("EHZ", START, peak_counts=50_000.0)
    raw = sim.to_miniseed_bytes(packet)
    stream = read(BytesIO(raw))
    assert stream[0].stats.sampling_rate == 100.0
    assert stream[0].stats.station == "TAKAB"
    assert stream[0].stats.npts == 100


def test_wr1_alert_triggers_reflex_and_test_pulse_does_not(settings):
    gpio = GpioController(settings)
    gpio.start()
    try:
        wr1 = WR1Simulator(gpio)
        wr1.alert()
        assert gpio.relay_state(ActuatorChannel.SIREN).energized is True

        gpio.set_relay(ActuatorChannel.SIREN, False)
        wr1.test_pulse()  # heartbeat CIRES → NO actúa (SPOF-03)
        assert gpio.relay_state(ActuatorChannel.SIREN).energized is False
    finally:
        gpio.stop()


def test_bacnet_simulator_acks_and_records_writes():
    sim = BacnetSimulator()
    assert sim.write_present_value(ActuatorChannel.GAS_VALVE, True) is True
    assert sim.present_values[ActuatorChannel.GAS_VALVE] is True
    assert sim.writes == [(ActuatorChannel.GAS_VALVE, True)]

    sim.online = False
    assert sim.write_present_value(ActuatorChannel.ELEVATOR, True) is False


@pytest.mark.parametrize("channel", DEFAULT_CHANNELS)
def test_rs4d_all_channels_emit(channel):
    sim = RS4DSimulator()
    assert sim.packet(channel, START).channel == channel
