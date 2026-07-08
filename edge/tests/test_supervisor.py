"""supervisor — ensamblaje, orden de dependencias y actuación SIN nube.

El test de "actuación completa con la nube apagada" cierra el DoD de la Fase E
(PLAN-MAESTRO §4, punto 6): P1/P2 probados, no declarados.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from simulators.rs4d import RS4DSimulator
from simulators.wr1 import WR1Simulator
from takab_edge.contracts import ActuatorChannel, AlertSource, Tier, TierDecision
from takab_edge.supervisor import ACKS_TOPIC, EVENTS_TOPIC, EdgeSupervisor

ALL_MODULES = {
    "seedlink",
    "signal",
    "buffer",
    "gpio",
    "rules",
    "actuators",
    "cloud",
    "health",
    "config",
    "security",
    "dispatch",  # T-1.23: consumidor de comandos/config firmados
    "backfill",  # T-1.25: ruta S3 del spool + evidencia offline
    "local_api",
}


def test_build_registers_all_modules(supervisor):
    assert {m.name for m in supervisor.modules()} == ALL_MODULES


def test_toposort_starts_dependencies_first(supervisor):
    order = [m.name for m in supervisor.modules()]
    for module in supervisor.modules():
        for dep in module.depends_on:
            assert order.index(dep) < order.index(module.name)


def test_all_modules_running_then_stopped(settings):
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.start()
    assert all(m.running for m in sup.modules())
    sup.stop()
    assert not any(m.running for m in sup.modules())


def _boom() -> None:
    raise RuntimeError("fallo de arranque simulado")


def test_noncritical_start_failure_keeps_life_path(settings, monkeypatch):
    """El dashboard LAN (no crítico) con el puerto ocupado NO tumba el gabinete:
    el reflejo SASMEX y la actuación siguen arriba (regla de oro 2)."""
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.build()
    monkeypatch.setattr(sup.local_api, "_on_start", _boom)

    sup.start()  # NO propaga: el módulo no-crítico se aísla

    assert sup.gpio.running, "el reflejo SASMEX debe seguir vivo"
    assert sup.rules.running and sup.actuators.running, "el camino de actuación sigue"
    assert not sup.local_api.running, "el módulo que falló queda sin arrancar"
    sup.stop()


def test_critical_start_failure_propagates(settings, monkeypatch):
    """Un módulo del camino de vida (gpio) que no arranca hace fail-fast: el
    gabinete crashea (systemd reinicia) en vez de correr mudo."""
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.build()
    monkeypatch.setattr(sup.gpio, "_on_start", _boom)

    with pytest.raises(RuntimeError):
        sup.start()


def test_life_path_modules_are_marked_critical(settings):
    """El núcleo de actuación (gpio/rules/actuators) es crítico; la coordinación no."""
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.build()
    critical = {m.name for m in sup.modules() if m.critical}
    assert critical == {"gpio", "rules", "actuators"}
    assert not sup.cloud.critical and not sup.local_api.critical


def test_disk_full_does_not_blind_detection(settings, monkeypatch):
    """Un buffer.append que lanza OSError (disco lleno) no debe impedir que las
    reglas evalúen el paquete: la detección va antes que la persistencia."""
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.build()
    sup.start()

    def _disk_full(_packet):
        raise OSError("ENOSPC: sin espacio en disco")

    monkeypatch.setattr(sup.buffer, "append", _disk_full)
    seen = {"rules": False}
    real_eval = sup.rules.evaluate_features

    def _spy(feature):
        seen["rules"] = True
        return real_eval(feature)

    monkeypatch.setattr(sup.rules, "evaluate_features", _spy)

    packet = next(
        RS4DSimulator(station=settings.station, sample_rate=settings.sample_rate).stream(
            channel="EHZ"
        )
    )
    sup._on_packet(packet)  # NO debe propagar el OSError

    assert seen["rules"], "las reglas evaluaron el paquete pese al disco lleno"
    sup.stop()


def test_disk_full_on_evidence_does_not_break_actuation(settings, monkeypatch):
    """queue_evidence que lanza OSError tras un EVACUATE no debe romper el hilo:
    los actuadores ya dispararon; la evidencia es best-effort."""
    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.build()
    sup.start()

    def _disk_full(*_a, **_k):
        raise OSError("ENOSPC")

    monkeypatch.setattr(sup.backfill, "queue_evidence", _disk_full)
    fired = {"n": 0}
    real_exec = sup.actuators.execute_sequence

    def _spy(commands):
        fired["n"] += 1
        return real_exec(commands)

    monkeypatch.setattr(sup.actuators, "execute_sequence", _spy)

    decision = TierDecision(tier=Tier.EVACUATE_OR_HOLD, source=AlertSource.THRESHOLD)
    sup._act_and_publish(decision, None)  # NO debe propagar el OSError

    assert fired["n"] == 1, "la secuencia de actuación se ejecutó antes de la evidencia"
    sup.stop()


def test_sasmex_actuates_with_cloud_offline(supervisor):
    assert supervisor.cloud.online is False
    WR1Simulator(supervisor.gpio).alert()

    # Reflejo local ejecutado sin nube:
    assert supervisor.gpio.relay_state(ActuatorChannel.SIREN).energized is True
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    # La nube sólo encola (offline-first); nunca fue prerequisito para actuar.
    # (Desde T-1.17 la cola también lleva telemetría: se cuenta POR topic.)
    assert supervisor.cloud.queued_by_topic(EVENTS_TOPIC) == 1
    assert supervisor.cloud.queued_by_topic(ACKS_TOPIC) == 5  # secuencia evacuate completa
    assert supervisor.cloud.sent == 0


def test_instrumental_event_drives_tier(supervisor):
    # Sismo local: varios canales sobre disparo (corroboración ≥2), SIN SASMEX.
    sim = RS4DSimulator(station=supervisor.settings.station)
    now = datetime.now(UTC)
    for channel in ("ENZ", "ENN", "ENE"):
        supervisor.seedlink.feed(sim.packet(channel, now, peak_counts=1_000_000.0))
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    assert len(supervisor.buffer) == 3
    # La ruta instrumental debe alertar audiblemente por su cuenta (blueprint §4.5):
    assert supervisor.gpio.relay_state(ActuatorChannel.SIREN).energized is True


def test_production_supervisor_wires_real_seedlink_transport(monkeypatch):
    # En producción (dev_mode=False) el edge DEBE conectar de verdad al Shake.
    from takab_edge.config import EdgeSettings
    from takab_edge.seedlink import ObsPySeedLinkTransport

    monkeypatch.setenv("TAKAB_EDGE_HMAC_KEY", "clave-prod-de-prueba")
    settings = EdgeSettings(dev_mode=False)
    sup = EdgeSupervisor(settings)
    sup.build()  # sólo ensambla; no arranca (no conecta)
    assert isinstance(sup.seedlink._transport, ObsPySeedLinkTransport)
    assert sup.seedlink._transport.station == settings.seedlink_station_code
