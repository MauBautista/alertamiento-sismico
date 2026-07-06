"""E2E — sismo simulado → actuación autónoma COMPLETA sin nube (cierra la Fase E)."""

from __future__ import annotations

from datetime import UTC, datetime

from simulators.quake import quake_packets, quake_window
from simulators.rs4d import RS4DSimulator
from simulators.wr1 import WR1Simulator
from takab_edge.contracts import ActuatorChannel, Tier
from takab_edge.evidence import FakeEvidenceUploader, collect_evidence

FULL_SEQUENCE = (
    ActuatorChannel.SIREN,
    ActuatorChannel.STROBE,
    ActuatorChannel.GAS_VALVE,
    ActuatorChannel.ELEVATOR,
    ActuatorChannel.DOOR_RETAINER,
)
QUAKE_START = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)


def _feed_quake(supervisor, start: datetime = QUAKE_START) -> datetime:
    sim = RS4DSimulator(station=supervisor.settings.station)
    for packet in quake_packets(sim, start):
        supervisor.seedlink.feed(packet)
    return start


def test_instrumental_quake_full_autonomous_actuation_cloud_off(supervisor):
    assert supervisor.cloud.online is False  # NUBE APAGADA (criterio central de T-1.14)
    _feed_quake(supervisor)
    # Actuación autónoma COMPLETA (evacuate) sin depender de la nube:
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    for channel in FULL_SEQUENCE:
        assert supervisor.gpio.relay_state(channel).activated is True, channel
    # La nube sólo encoló (offline-first); nunca fue prerequisito para actuar (§4.2).
    assert supervisor.cloud.queued >= 1
    assert supervisor.cloud.sent == 0
    # El waveform crudo quedó en el buffer (evidencia S3 en evento confirmado, T-1.7/1.11).
    assert len(supervisor.buffer) > 0


def test_actuation_latency_within_budget(supervisor):
    _feed_quake(supervisor)
    assert supervisor.rules.last_latency_s is not None
    assert supervisor.rules.last_latency_s < 0.2  # presupuesto §4.3


def test_sasmex_reflex_and_sequence_cloud_off(supervisor):
    assert supervisor.cloud.online is False
    WR1Simulator(supervisor.gpio).alert()
    assert supervisor.gpio.siren_sounding is True  # reflejo local inmediato (sin nube)
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    assert supervisor.cloud.queued == 1


def test_no_duplicate_event_explosion_within_episode(supervisor):
    _feed_quake(supervisor)
    # Todo el sismo es UN episodio: los eventos se deduplican por (event_id, tier), así que
    # no hay explosión de duplicados aunque lluevan paquetes (idempotencia, regla de oro 3).
    assert supervisor.cloud.queued <= 3  # a lo sumo watch/restricted/evacuate


def test_evidence_window_extractable_after_quake(supervisor):
    start = _feed_quake(supervisor)
    obj = collect_evidence(
        supervisor.buffer, FakeEvidenceUploader(), "quake-1", *quake_window(start)
    )
    assert obj is not None
    assert obj.size_bytes > 0
    assert obj.sha256


def test_load_many_noise_packets_no_spurious_alert(supervisor):
    sim = RS4DSimulator(station=supervisor.settings.station)
    stream = sim.stream(channel="EHZ")
    for _ in range(300):  # carga: 300 paquetes de ruido de fondo
        supervisor.seedlink.feed(next(stream))
    # El ruido de fondo NO dispara alertas espurias; el buffer los guardó todos.
    assert supervisor.rules.last_decision.tier is Tier.NORMAL
    assert len(supervisor.buffer) >= 300
    assert supervisor.cloud.queued == 0  # sin eventos → nada que encolar
