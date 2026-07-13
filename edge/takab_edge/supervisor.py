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
from datetime import timedelta

from takab_edge.actuators import ActuatorManager, BacnetActuator, RelayActuator
from takab_edge.audio import AudioNotifier
from takab_edge.backfill import BackfillManager
from takab_edge.buffer import RingBuffer
from takab_edge.cloud import AwsIotMqttTransport, CloudConnector, MqttTransport
from takab_edge.config import ConfigStore, EdgeSettings, load_settings
from takab_edge.contracts import (
    Feature1s,
    HealthSnapshot,
    LocalEvent,
    SasmexSignal,
    Tier,
    TierDecision,
    WaveformPacket,
    utcnow,
)
from takab_edge.dispatch import CommandDispatcher
from takab_edge.drill import DrillController
from takab_edge.gpio import GpioController
from takab_edge.health import HealthMonitor
from takab_edge.local_api import LocalDashboard
from takab_edge.module import EdgeModule
from takab_edge.rules import RuleEngine, commands_for
from takab_edge.security import SecurityManager
from takab_edge.seedlink import ObsPySeedLinkTransport, SeedLinkClient
from takab_edge.signal import FeatureExtractor
from takab_edge.telemetry import FEATURES_BATCH_TOPIC, FeatureBatcher

log = logging.getLogger("takab_edge.supervisor")

EVENTS_TOPIC = "takab/events"
HEALTH_TOPIC = "takab/health"
ACKS_TOPIC = "takab/acks"
FEATURES_TOPIC = "takab/features"


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
        mqtt_transport: MqttTransport | None = None,
    ) -> None:
        self.settings = settings
        self._seedlink_source = seedlink_source
        self._mqtt_transport = mqtt_transport
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

    def _build_mqtt_transport(self, s: EdgeSettings) -> MqttTransport | None:
        """Transporte MQTT: inyectado (tests) > real con endpoint+certs > ninguno (dev/CI).

        Convención fija (T-1.15/T-1.17): client_id = thing name IoT (fallback al serial
        del gateway) y presencia retained en `takab/status/<thing>`. Sin certs, el
        conector arranca offline y sólo encola (comportamiento previo, T-1.11).
        """
        if self._mqtt_transport is not None:
            return self._mqtt_transport
        if s.mqtt_endpoint and s.mqtt_cert_path and s.mqtt_key_path and s.mqtt_ca_path:
            return AwsIotMqttTransport(
                s,
                s.mqtt_cert_path,
                s.mqtt_key_path,
                s.mqtt_ca_path,
                client_id=s.thing_name,
                status_topic=s.status_topic,
            )
        return None

    def build(self) -> EdgeSupervisor:
        from simulators.bacnet import BacnetSimulator

        s = self.settings
        self.gpio = GpioController(s)
        self.seedlink = self._build_seedlink(s)
        self.signal = FeatureExtractor(s.signal)
        self.buffer = RingBuffer(s.buffer)
        self.rules = RuleEngine(s.thresholds)
        self.bacnet = BacnetSimulator()
        self.actuators = ActuatorManager(
            RelayActuator(self.gpio), BacnetActuator(self.bacnet), s.bacnet_channels
        )
        self.cloud = CloudConnector(
            s,
            transport=self._build_mqtt_transport(s),
            status_topic=s.status_topic,
            # Cota SOLO para telemetría reponible: un offline largo no debe agotar
            # RAM/disco ni volver el backfill de minutos. Eventos/ACKs sin cota.
            # El topic batch (T-1.56) usa una cota DERIVADA (cap // batch_max):
            # un registro batch vale hasta batch_max features — misma cota en
            # features-equivalentes, sin perilla nueva.
            topic_caps={
                FEATURES_TOPIC: s.cloud_telemetry_cap,
                HEALTH_TOPIC: s.cloud_telemetry_cap,
                FEATURES_BATCH_TOPIC: max(1, s.cloud_telemetry_cap // s.cloud_features_batch_max),
            },
        )
        # Batcheo escalonado por tier (T-1.56): SOLO publicación de features.
        self.telemetry = FeatureBatcher(s, cloud=self.cloud)
        self.health = HealthMonitor(
            s,
            gpio=self.gpio,
            seedlink=self.seedlink,
            cloud=self.cloud,  # RTT del PUBACK real en el heartbeat (T-1.40)
            heartbeat_s=s.health_heartbeat_s,
        )
        self.security = SecurityManager(_resolve_hmac_key(s), command_ttl_s=s.command_ttl_s)
        self.config = ConfigStore(s, security=self.security)
        # Voceo por audio (A-6): canal ADVISORY subordinado al camino de vida —
        # se dispara DESPUÉS de actuar y jamás bloquea ni condiciona los relés.
        self.audio = AudioNotifier(s, gpio=self.gpio)
        # Simulacro institucional (T-1.60): observador puro — banner + voceo,
        # CERO relés; lo real (SASMEX o tier instrumental) lo aborta. Se crea
        # ANTES que dispatch (que le enruta drill_start/drill_stop).
        self.drill = DrillController(s, gpio=self.gpio, audio=self.audio)
        self.dispatch = CommandDispatcher(
            s,
            self.security,
            self.config,
            self.actuators,
            self.cloud,
            acks_topic=ACKS_TOPIC,
            # T-1.59: salud CACHEADA para el ack del self_test (jamás sondas).
            health=self.health,
            # T-1.60: ramas drill_start/drill_stop del canal system.
            drill=self.drill,
        )
        # Backfill S3 + evidencia offline (T-1.25): se auto-cablea al conector
        # (router del flush, on_online, suscripción al grant).
        self.backfill = BackfillManager(s, self.cloud, buffer=self.buffer)
        self.local_api = LocalDashboard(
            self.gpio,
            self.rules,
            self.health,
            host=s.local_api_host,
            port=s.local_api_port,
            pin=s.local_api_pin,
            dev_mode=s.dev_mode,
            # T-1.53: mini-consola — PGA vivo, enlace a nube e identidad viva.
            signal=self.signal,
            cloud=self.cloud,
            gateway_id=s.gateway_id,
            site_name=s.site_name,
            refresh_ms=s.local_api_refresh_ms,
            audio=self.audio,
            drill=self.drill,
        )

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
                self.telemetry,
                self.health,
                self.config,
                self.security,
                self.dispatch,
                self.backfill,
                self.audio,
                self.drill,
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
        # T-1.60: un SASMEX real aborta el simulacro (observador aislado en gpio).
        self.gpio.on_sasmex(self.drill.on_sasmex)
        # Salud → nube: transición Y heartbeat (T-1.17 G6; sin event_id → sin dedup).
        self.health.on_snapshot(self._on_health_snapshot)
        # Comandos/config firmados nube→edge (T-1.23): el conector (re)suscribe
        # en cada conexión; el dispatcher verifica TODO antes de tocar nada.
        self.cloud.subscribe(self.settings.command_topic, self.dispatch.on_command)
        self.cloud.subscribe(self.settings.config_topic, self.dispatch.on_config)

    def _on_packet(self, packet: WaveformPacket) -> None:
        # Detección y actuación PRIMERO: el camino umbral→actuador (regla de oro 1/2)
        # jamás depende de I/O de disco. La persistencia del waveform crudo (para la
        # evidencia) va DESPUÉS y best-effort — un disco lleno (ENOSPC) no debe cegar
        # la detección ni enmascararse como una desconexión de SeedLink.
        feature = self.signal.process(packet)
        decision = self.rules.evaluate_features(feature)
        self._act_and_publish(decision, feature)
        try:
            self.buffer.append(packet)
        except OSError:
            log.exception("buffer.append falló (¿disco lleno?); la detección continúa")
        # Telemetría 1 s → nube DESPUÉS de actuar (sin dedup, como los heartbeats;
        # publicar jamás bloquea ni condiciona la vía de actuación — §4.2).
        # T-1.56: el batcher decide la ruta por tier (normal → lote; watch+ → 1 Hz).
        self.telemetry.submit(feature, decision.tier)

    def _on_health_snapshot(self, snapshot: HealthSnapshot) -> None:
        self.cloud.publish(HEALTH_TOPIC, snapshot)

    def _on_sasmex(self, signal: SasmexSignal) -> None:
        decision = self.rules.evaluate_sasmex(signal)
        if decision is not None:
            self._act_and_publish(decision, None)
            # T-1.56: la escalación por SASMEX no pasa por _on_packet — drenar el
            # acumulado YA para que el contexto pre-evento llegue antes que el 1 Hz.
            self.telemetry.notify_tier(decision.tier)

    def _act_and_publish(self, decision: TierDecision, feature: Feature1s | None) -> None:
        # Secuencia de actuación del tier. En evacuate incluye la sirena general:
        # en la ruta SASMEX es idempotente con el reflejo in-process de gpio; en la
        # ruta instrumental (umbral, sin SASMEX) es la única alerta audible (§4.5).
        acks = self.actuators.execute_sequence(commands_for(decision))
        failed = [ack.channel.value for ack in acks if not ack.success]
        if failed:
            # Actuación de vida fallida: avisar de inmediato. La escalación a la nube como
            # alarma (T-1.11) y el fallback por contrato al relé (T-1.10) van aparte.
            log.warning("actuación con fallo(s) en %s (event_id=%s)", failed, decision.event_id)
        # Voceo ADVISORY (A-6) tras actuar los relés: nunca antes, nunca bloqueante,
        # y sus fallos se aíslan dentro del propio módulo.
        self.audio.on_tier(decision)
        # T-1.60: un tier instrumental de protección aborta el simulacro en curso.
        self.drill.on_tier(decision)
        # ACK de cada actuador → nube, tras actuar (dedup por event_id+canal+acción).
        for ack in acks:
            self.cloud.publish(ACKS_TOPIC, ack)
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
        # Evidencia miniSEED del evento (T-1.25): se ENCOLA durable y se sube
        # cuando la ventana está completa y hay enlace (offline ⇒ al reconectar).
        # Best-effort: los actuadores YA dispararon; un fallo de disco al encolar la
        # evidencia jamás debe propagar al hilo de detección (mismo I/O que el buffer).
        if decision.tier in (Tier.EVACUATE_OR_HOLD, Tier.RESTRICTED):
            now = utcnow()
            try:
                self.backfill.queue_evidence(
                    decision.event_id,
                    now - timedelta(seconds=self.settings.evidence_pre_s),
                    now + timedelta(seconds=self.settings.evidence_post_s),
                )
            except OSError:
                log.exception("queue_evidence falló (¿disco lleno?); la actuación ya ocurrió")

    # --- Ciclo de vida ---
    def modules(self) -> list[EdgeModule]:
        return _toposort(self._modules)

    def start(self) -> None:
        if not self._built:
            self.build()
        # Aislamiento por módulo (blueprint §4.2, regla de oro 2): un módulo NO
        # crítico que falla al arrancar (p.ej. el dashboard LAN con el puerto
        # ocupado) NO debe tumbar el gabinete — el camino de vida sigue arriba en
        # modo degradado. Un módulo `critical` que falla SÍ propaga: un gabinete
        # que no puede accionar debe crashear ruidoso (systemd reinicia), no correr
        # mudo. Espeja el aislamiento de `stop()`.
        started = 0
        for module in self.modules():
            try:
                module.start()
                started += 1
            except Exception:
                if module.critical:
                    log.critical("módulo CRÍTICO %s no arrancó; se propaga", module.name)
                    raise
                log.exception("módulo no-crítico %s no arrancó; el gabinete sigue", module.name)
        log.info("gabinete arrancado (%d/%d módulos)", started, len(self._modules))

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
