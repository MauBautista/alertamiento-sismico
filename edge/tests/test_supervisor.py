"""supervisor — ensamblaje, orden de dependencias y actuación SIN nube.

El test de "actuación completa con la nube apagada" cierra el DoD de la Fase E
(PLAN-MAESTRO §4, punto 6): P1/P2 probados, no declarados.
"""

from __future__ import annotations

from datetime import UTC, datetime

from simulators.rs4d import RS4DSimulator
from simulators.wr1 import WR1Simulator
from takab_edge.contracts import ActuatorChannel, Tier
from takab_edge.supervisor import EdgeSupervisor

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
    "local_api",
}


def test_build_registers_all_eleven_modules(supervisor):
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


def test_sasmex_actuates_with_cloud_offline(supervisor):
    assert supervisor.cloud.online is False
    WR1Simulator(supervisor.gpio).alert()

    # Reflejo local ejecutado sin nube:
    assert supervisor.gpio.relay_state(ActuatorChannel.SIREN).energized is True
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    # La nube sólo encola (offline-first); nunca fue prerequisito para actuar:
    assert supervisor.cloud.queued == 1
    assert supervisor.cloud.sent == 0


def test_instrumental_event_drives_tier(supervisor):
    # Sismo local detectado por umbral, SIN SASMEX (no hay reflejo de gpio).
    packet = RS4DSimulator(station=supervisor.settings.station).packet(
        "ENZ", datetime.now(UTC), peak_counts=200_000.0
    )
    supervisor.seedlink.feed(packet)
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    assert len(supervisor.buffer) == 1
    # La ruta instrumental debe alertar audiblemente por su cuenta (blueprint §4.5):
    assert supervisor.gpio.relay_state(ActuatorChannel.SIREN).energized is True
