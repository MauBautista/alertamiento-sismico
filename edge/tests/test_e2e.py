"""E2E — sismo simulado → actuación autónoma COMPLETA sin nube (cierra la Fase E)."""

from __future__ import annotations

from datetime import UTC, datetime

from simulators.quake import quake_packets, quake_window
from simulators.rs4d import RS4DSimulator
from simulators.wr1 import WR1Simulator
from takab_edge.contracts import ActuatorChannel, Tier
from takab_edge.evidence import FakeEvidenceUploader, collect_evidence
from takab_edge.supervisor import EVENTS_TOPIC, FEATURES_TOPIC
from takab_edge.telemetry import FEATURES_BATCH_TOPIC

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


def test_instrumental_quake_visual_only_no_actuation(supervisor):
    # [T-2.32 · REESCRITURA DELIBERADA del contrato de T-1.14, política ratificada
    # 2026-08-03] Una sola estación moviéndose NO activa nada: la detección
    # instrumental local es SOLO AVISO (online y offline). La actuación viene de
    # SASMEX (intacta) o del comando firmado de quórum ≥3 de la nube.
    assert supervisor.cloud.online is False  # sin nube el aviso sigue siendo solo aviso
    _feed_quake(supervisor)
    # El tier SÍ se eleva (el panel lo muestra como AVISO)…
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    # …pero NINGÚN actuador dispara por umbral local.
    for channel in FULL_SEQUENCE:
        assert supervisor.gpio.relay_state(channel).activated is False, channel
    assert supervisor.gpio.alert_latched is False
    # El evento SÍ viaja a la nube (offline-first): es lo que alimenta el quórum.
    assert supervisor.cloud.queued_by_topic(EVENTS_TOPIC) >= 1
    assert supervisor.cloud.sent == 0
    # El waveform crudo quedó en el buffer (evidencia S3 en evento confirmado, T-1.7/1.11).
    assert len(supervisor.buffer) > 0


def test_instrumental_actuation_optin_restores_sequence(settings):
    # [T-2.32] El opt-in explícito por sitio (config firmada) restaura la
    # actuación instrumental autónoma completa — la de la Fase 1.
    from takab_edge.supervisor import EdgeSupervisor

    optin = settings.model_copy(update={"instrumental_actuation": True})
    sup = EdgeSupervisor(optin, seedlink_source=None)
    sup.start()
    try:
        _feed_quake(sup)
        assert sup.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
        for channel in FULL_SEQUENCE:
            assert sup.gpio.relay_state(channel).activated is True, channel
    finally:
        sup.stop()


def test_quake_event_reflected_in_panel_status(supervisor):
    # [T-2.30, renegociado en T-2.32] El eslabón sim→tier→PANEL: /api/status
    # cuenta la verdad del AVISO — tier elevado, relés SIN activar, sin enclave.
    _feed_quake(supervisor)
    status = supervisor.local_api.status()
    assert status["last_tier"] == "evacuate_or_hold"
    assert status["alert_latched"] is False
    by_channel = {relay["channel"]: relay for relay in status["relays"]}
    for channel in FULL_SEQUENCE:
        assert by_channel[channel.value]["activated"] is False, channel


def test_actuation_latency_within_budget(supervisor):
    _feed_quake(supervisor)
    assert supervisor.rules.last_latency_s is not None
    assert supervisor.rules.last_latency_s < 0.2  # presupuesto §4.3


def test_sasmex_reflex_and_sequence_cloud_off(supervisor):
    assert supervisor.cloud.online is False
    WR1Simulator(supervisor.gpio).alert()
    assert supervisor.gpio.siren_sounding is True  # reflejo local inmediato (sin nube)
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    assert supervisor.cloud.queued_by_topic(EVENTS_TOPIC) == 1  # UN evento (T-1.17: por topic)


def test_no_duplicate_event_explosion_within_episode(supervisor):
    _feed_quake(supervisor)
    # Todo el sismo es UN episodio: los eventos se deduplican por (event_id, tier), así que
    # no hay explosión de duplicados aunque lluevan paquetes (idempotencia, regla de oro 3).
    assert supervisor.cloud.queued_by_topic(EVENTS_TOPIC) <= 3  # a lo sumo watch/restr/evacuate


def test_evidence_window_extractable_after_quake(supervisor):
    start = _feed_quake(supervisor)
    obj = collect_evidence(
        supervisor.buffer, FakeEvidenceUploader(), "quake-1", *quake_window(start)
    )
    assert obj is not None
    assert obj.size_bytes > 0
    assert obj.sha256


def test_manual_reset_closes_alert_end_to_end(supervisor):
    # [T-2.26] SASMEX real → protección completa → CERRAR ALERTA libera TODO
    # (relés + tier + latch); un SASMEX NUEVO re-enclava (latch monótono intacto).
    WR1Simulator(supervisor.gpio).alert()
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    for channel in FULL_SEQUENCE:
        assert supervisor.gpio.relay_state(channel).activated is True, channel

    supervisor.local_api.reset_alert()
    status = supervisor.local_api.status()
    assert status["last_tier"] == "normal"
    assert status["alert_latched"] is False
    for channel in FULL_SEQUENCE:
        assert supervisor.gpio.relay_state(channel).activated is False, channel

    WR1Simulator(supervisor.gpio).alert()  # alerta NUEVA tras el cierre
    assert supervisor.gpio.alert_latched is True
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD


def test_quake_sequence_skips_uninstalled_channels(settings):
    # [T-2.31] Sitio sin gas ni ascensores: la secuencia de tier comanda SOLO lo
    # instalado; gpio conserva sus 5 relés (hardware intocado) pero los canales
    # ausentes jamás se activan. [T-2.32] Con opt-in instrumental explícito: el
    # filtro de equipamiento se prueba en la ruta que SÍ actúa.
    from takab_edge.config import EquipmentProfile
    from takab_edge.supervisor import EdgeSupervisor

    site = settings.model_copy(
        update={
            "equipment": EquipmentProfile(gas_valve=False, elevator=False),
            "instrumental_actuation": True,
        }
    )
    sup = EdgeSupervisor(site, seedlink_source=None)
    sup.start()
    try:
        _feed_quake(sup)
        assert sup.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
        for channel in (
            ActuatorChannel.SIREN,
            ActuatorChannel.STROBE,
            ActuatorChannel.DOOR_RETAINER,
        ):
            assert sup.gpio.relay_state(channel).activated is True, channel
        for channel in (ActuatorChannel.GAS_VALVE, ActuatorChannel.ELEVATOR):
            assert sup.gpio.relay_state(channel).activated is False, channel
        assert len(sup.gpio.relay_states()) == 5  # el hardware sigue completo
    finally:
        sup.stop()


def test_sasmex_propagates_to_lora_secondaries_and_reset_clears(settings):
    # [T-2.33] Los secundarios son ESPEJOS de la actuación real: SASMEX ⇒
    # ALARM_ACT firmada (sirena+estrobo remotos) hasta ACK; CERRAR ALERTA ⇒
    # ALARM_CLEAR. La detección instrumental (solo aviso, T-2.32) NO propaga.
    import time as _time

    from simulators.lora import FakeSecondaryCabinet, SimulatedLoraTransport
    from takab_edge.config import LoraConfig, SecondaryCabinet
    from takab_edge.supervisor import EdgeSupervisor

    site_key = b"clave-lora-de-sitio-0123456789ab"
    transport = SimulatedLoraTransport()
    cab = transport.attach(FakeSecondaryCabinet(site_key, 258))
    lora_settings = settings.model_copy(
        update={
            "lora": LoraConfig(
                enabled=True,
                alarm_retry_s=0.05,
                secondaries=[SecondaryCabinet(id=258, name="AZOTEA")],
            )
        }
    )
    sup = EdgeSupervisor(
        lora_settings, seedlink_source=None, lora_transport=transport, lora_site_key=site_key
    )
    sup.start()
    try:
        _feed_quake(sup)  # instrumental = solo aviso ⇒ nada viaja a secundarios
        _time.sleep(0.2)
        assert cab.alarm_active is False

        WR1Simulator(sup.gpio).alert()  # SASMEX real ⇒ espejo remoto
        deadline = _time.monotonic() + 3.0
        while _time.monotonic() < deadline and not cab.alarm_active:
            _time.sleep(0.01)
        assert cab.alarm_active is True
        row = sup.local_api.status()["lora"]["secondaries"][0]
        assert row["acked"] is True

        sup.local_api.reset_alert()  # CERRAR ALERTA libera también a distancia
        deadline = _time.monotonic() + 3.0
        while _time.monotonic() < deadline and cab.alarm_active:
            _time.sleep(0.01)
        assert cab.alarm_active is False
    finally:
        sup.stop()


def test_load_many_noise_packets_no_spurious_alert(supervisor):
    sim = RS4DSimulator(station=supervisor.settings.station)
    stream = sim.stream(channel="EHZ")
    for _ in range(300):  # carga: 300 paquetes de ruido de fondo
        supervisor.seedlink.feed(next(stream))
    # El ruido de fondo NO dispara alertas espurias; el buffer los guardó todos.
    assert supervisor.rules.last_decision.tier is Tier.NORMAL
    assert len(supervisor.buffer) >= 300
    assert supervisor.cloud.queued_by_topic(EVENTS_TOPIC) == 0  # sin eventos que encolar
    # T-1.56: en tier normal la telemetría fluye BATCHEADA — 300 features son
    # unos pocos lotes encolados + el resto acumulado en el batcher, no 300 publishes.
    assert supervisor.cloud.queued_by_topic(FEATURES_TOPIC) == 0
    batch_max = supervisor.settings.cloud_features_batch_max
    queued_batches = supervisor.cloud.queued_by_topic(FEATURES_BATCH_TOPIC)
    assert queued_batches >= 300 // batch_max
    assert queued_batches * batch_max + supervisor.telemetry.pending >= 300
