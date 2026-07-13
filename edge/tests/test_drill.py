"""drill — simulacro institucional (T-1.60): observador puro, lo real GANA."""

from __future__ import annotations

import time

import pytest
from takab_edge.contracts import (
    ActuatorChannel,
    AlertSource,
    SasmexSignal,
    Tier,
    TierDecision,
)
from takab_edge.drill import DrillController
from takab_edge.gpio import LOCAL_RELAY_CHANNELS, GpioController


class _FakeAudio:
    def __init__(self) -> None:
        self.played: list[str] = []
        self.stopped = 0

    def play_simulacro(self) -> None:
        self.played.append("simulacro")

    def stop_playback(self) -> None:
        self.stopped += 1


@pytest.fixture
def gpio(settings):
    controller = GpioController(settings)
    controller.start()
    try:
        yield controller
    finally:
        controller.stop()


@pytest.fixture
def drill(settings, gpio):
    audio = _FakeAudio()
    controller = DrillController(settings, gpio=gpio, audio=audio)
    controller.start()
    try:
        yield controller, audio, gpio
    finally:
        controller.stop()


def test_start_pinta_banner_y_vocea_sin_tocar_relays(drill):
    controller, audio, gpio = drill
    before = {c: gpio.relay_state(c).energized for c in LOCAL_RELAY_CHANNELS}
    ok, reason = controller.start_drill("DRILL-1", 300)
    assert ok is True and "iniciado" in reason
    state = controller.status()
    assert state["active"] is True and state["drill_id"] == "DRILL-1"
    assert audio.played == ["simulacro"]
    # CERO relés: ningún canal cambió de estado eléctrico.
    after = {c: gpio.relay_state(c).energized for c in LOCAL_RELAY_CHANNELS}
    assert after == before
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is False


def test_fin_por_ventana(drill):
    controller, _audio, _gpio = drill
    controller.start_drill("DRILL-2", 0.05)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and controller.active:
        time.sleep(0.01)
    state = controller.status()
    assert state["active"] is False
    assert state["ended_reason"] == "fin de ventana"
    assert state["aborted"] is False


def test_rechaza_con_alerta_sasmex_viva(drill):
    controller, audio, gpio = drill
    gpio.simulate_sasmex(active=True)
    ok, reason = controller.start_drill("DRILL-3", 300)
    assert ok is False and "SASMEX" in reason
    assert controller.active is False
    assert audio.played == []


def test_sasmex_real_aborta_visiblemente(drill):
    controller, audio, gpio = drill
    gpio.on_sasmex(controller.on_sasmex)  # cableado que hace el supervisor
    controller.start_drill("DRILL-4", 300)
    gpio.simulate_sasmex(active=True)
    state = controller.status()
    assert state["active"] is False and state["aborted"] is True
    assert "SASMEX" in state["abort_reason"]
    assert audio.stopped >= 1  # el voceo del drill se corta
    # El reflejo real actuó intacto: la sirena está sonando.
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is True


def test_pulso_de_prueba_cires_no_aborta(drill):
    controller, _audio, gpio = drill
    gpio.on_sasmex(controller.on_sasmex)
    controller.start_drill("DRILL-5", 300)
    gpio.simulate_sasmex(active=True, is_test=True)  # heartbeat CIRES
    assert controller.active is True  # el drill sigue: no hubo alerta real


def test_tier_instrumental_aborta(drill):
    controller, _audio, _gpio = drill
    controller.start_drill("DRILL-6", 300)
    decision = TierDecision(tier=Tier.RESTRICTED, source=AlertSource.THRESHOLD)
    controller.on_tier(decision)
    state = controller.status()
    assert state["aborted"] is True and "restricted" in state["abort_reason"]


def test_tier_watch_no_aborta(drill):
    controller, _audio, _gpio = drill
    controller.start_drill("DRILL-7", 300)
    controller.on_tier(TierDecision(tier=Tier.WATCH, source=AlertSource.THRESHOLD))
    assert controller.active is True


def test_end_drill_por_stop_firmado_e_idempotente(drill):
    controller, _audio, _gpio = drill
    controller.start_drill("DRILL-8", 300)
    assert controller.end_drill("DRILL-8", reason="drill_stop firmado") is True
    assert controller.active is False
    assert controller.end_drill("DRILL-8") is False  # no-op idempotente


def test_end_drill_de_otro_id_no_toca_el_vigente(drill):
    controller, _audio, _gpio = drill
    controller.start_drill("DRILL-9", 300)
    assert controller.end_drill("DRILL-OTRO") is False
    assert controller.active is True


def test_on_sasmex_apertura_de_contacto_no_aborta(drill):
    controller, _audio, _gpio = drill
    controller.start_drill("DRILL-10", 300)
    controller.on_sasmex(SasmexSignal(active=False))
    assert controller.active is True
