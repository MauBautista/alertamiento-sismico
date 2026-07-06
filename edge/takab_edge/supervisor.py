"""supervisor — arranque, orden de dependencias, cableado y watchdog del edge.

Instancia los módulos, los cablea en el pipeline
``seedlink→signal→(buffer, rules)→actuators/cloud`` y ``gpio(SASMEX)→rules``, y
los arranca en orden topológico (parada en orden inverso, aislando fallos).

Regla de oro (blueprint §4.2): la actuación local NO depende de la nube. `cloud`
sólo transporta; arranca offline y encola. El reflejo SASMEX→sirena vive en `gpio`
y funciona aunque el resto no arranque.
"""

from __future__ import annotations

import logging
import os
import signal as _signal
import threading
from collections.abc import Iterator

from takab_edge.actuators import ActuatorManager, BacnetActuator, RelayActuator
from takab_edge.buffer import RingBuffer
from takab_edge.cloud import CloudConnector
from takab_edge.config import ConfigStore, EdgeSettings, load_settings
from takab_edge.contracts import (
    Feature1s,
    LocalEvent,
    SasmexSignal,
    Tier,
    TierDecision,
    WaveformPacket,
)
from takab_edge.gpio import GpioController
from takab_edge.health import HealthMonitor
from takab_edge.local_api import LocalDashboard
from takab_edge.module import EdgeModule
from takab_edge.rules import RuleEngine, commands_for
from takab_edge.security import SecurityManager
from takab_edge.seedlink import ObsPySeedLinkTransport, SeedLinkClient
from takab_edge.signal import FeatureExtractor

log = logging.getLogger("takab_edge.supervisor")

EVENTS_TOPIC = "takab/events"


def _resolve_hmac_key(settings: EdgeSettings) -> bytes:
    """Clave HMAC desde entorno; efímera sólo en dev. Nunca hardcodeada (§2.6)."""
    key = os.environ.get("TAKAB_EDGE_HMAC_KEY", "").encode()
    if key:
        return key
    if settings.dev_mode:
        return os.urandom(32)  # efímera, sólo desarrollo
    raise RuntimeError("TAKAB_EDGE_HMAC_KEY es obligatoria en producción")


def _toposort(modules: dict[str, EdgeModule]) -> list[EdgeModule]:
    """Orden de arranque respetando `depends_on` (Kahn)."""
    ordered: list[EdgeModule] = []
    visited: set[str] = set()

    def visit(name: str, stack: tuple[str, ...]) -> None:
        if name in visited:
            return
        if name in stack:
            raise ValueError(f"ciclo de dependencias en módulos: {stack + (name,)}")
        module = modules.get(name)
        if module is None:
            return
        for dep in module.depends_on:
            visit(dep, stack + (name,))
        visited.add(name)
        ordered.append(module)

    for name in modules:
        visit(name, ())
    return ordered


class EdgeSupervisor:
    """Ensambla y opera el gabinete completo (con simuladores en dev)."""

    def __init__(
        self,
        settings: EdgeSettings,
        seedlink_source: Iterator[WaveformPacket] | None = None,
    ) -> None:
        self.settings = settings
        self._seedlink_source = seedlink_source
        self._built = False
        self._stop_event = threading.Event()

    def _build_seedlink(self, s: EdgeSettings) -> SeedLinkClient:
        """En dev usa el simulador RS4D; en producción, el transporte SeedLink real.

        (Los drivers reales de BACnet y cloud se cablean en T-1.9/T-1.11.)
        """
        if s.dev_mode:
            return SeedLinkClient(s, source=self._seedlink_source)
        transport = ObsPySeedLinkTransport(
            s.seedlink_host,
            s.seedlink_port,
            s.seedlink_network,
            s.seedlink_station_code,
            s.seedlink_location,
            s.seedlink_channels,
        )
        return SeedLinkClient(s, transport=transport)

    def build(self) -> EdgeSupervisor:
        from simulators.bacnet import BacnetSimulator

        s = self.settings
        self.gpio = GpioController(s)
        self.seedlink = self._build_seedlink(s)
        self.signal = FeatureExtractor()
        self.buffer = RingBuffer()
        self.rules = RuleEngine(s.thresholds)
        self.bacnet = BacnetSimulator()
        self.actuators = ActuatorManager([RelayActuator(self.gpio), BacnetActuator(self.bacnet)])
        self.cloud = CloudConnector(s)
        self.health = HealthMonitor(s, gpio=self.gpio)
        self.config = ConfigStore(s)
        self.security = SecurityManager(_resolve_hmac_key(s))
        self.local_api = LocalDashboard(self.gpio, self.rules, self.health)

        self._modules: dict[str, EdgeModule] = {
            m.name: m
            for m in (
                self.gpio,
                self.seedlink,
                self.signal,
                self.buffer,
                self.rules,
                self.actuators,
                self.cloud,
                self.health,
                self.config,
                self.security,
                self.local_api,
            )
        }
        self._wire()
        self._built = True
        return self

    # --- Cableado del pipeline ---
    def _wire(self) -> None:
        self.seedlink.on_packet(self._on_packet)
        self.gpio.on_sasmex(self._on_sasmex)

    def _on_packet(self, packet: WaveformPacket) -> None:
        self.buffer.append(packet)
        feature = self.signal.process(packet)
        decision = self.rules.evaluate_features(feature)
        self._act_and_publish(decision, feature)

    def _on_sasmex(self, signal: SasmexSignal) -> None:
        decision = self.rules.evaluate_sasmex(signal)
        if decision is not None:
            self._act_and_publish(decision, None)

    def _act_and_publish(self, decision: TierDecision, feature: Feature1s | None) -> None:
        # Secuencia de actuación del tier. En evacuate incluye la sirena general:
        # en la ruta SASMEX es idempotente con el reflejo in-process de gpio; en la
        # ruta instrumental (umbral, sin SASMEX) es la única alerta audible (§4.5).
        self.actuators.execute_sequence(commands_for(decision))
        if decision.tier is Tier.NORMAL:
            return
        # Evento idempotente hacia la nube (offline-first; NO bloquea la actuación).
        event = LocalEvent(
            event_id=decision.event_id,
            tenant_id=self.settings.tenant_id,
            site_id=self.settings.site_id,
            source=decision.source,
            tier=decision.tier,
        )
        self.cloud.publish(EVENTS_TOPIC, event)

    # --- Ciclo de vida ---
    def modules(self) -> list[EdgeModule]:
        return _toposort(self._modules)

    def start(self) -> None:
        if not self._built:
            self.build()
        for module in self.modules():
            module.start()
        log.info("gabinete arrancado (%d módulos)", len(self._modules))

    def stop(self) -> None:
        for module in reversed(self.modules()):
            try:
                module.stop()
            except Exception:  # noqa: BLE001 — aislar fallo de un módulo al detener
                log.exception("fallo al detener %s", module.name)
        self._stop_event.set()

    def run(self) -> None:
        """Arranca y bloquea hasta SIGINT/SIGTERM (uso en el Pi bajo systemd)."""
        self.start()
        for sig in (_signal.SIGINT, _signal.SIGTERM):
            _signal.signal(sig, lambda *_: self._stop_event.set())
        try:
            self._stop_event.wait()
        finally:
            self.stop()


def build_dev_supervisor(settings: EdgeSettings | None = None) -> EdgeSupervisor:
    """Supervisor de desarrollo con el simulador RS4D como fuente SeedLink."""
    from simulators.rs4d import RS4DSimulator

    settings = settings or load_settings()
    sim = RS4DSimulator(station=settings.station, sample_rate=settings.sample_rate)
    source = sim.stream(channel="EHZ")  # stream infinito de ruido de fondo
    return EdgeSupervisor(settings, seedlink_source=source)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    settings = load_settings()
    supervisor = build_dev_supervisor(settings) if settings.dev_mode else EdgeSupervisor(settings)
    supervisor.run()


if __name__ == "__main__":
    main()
