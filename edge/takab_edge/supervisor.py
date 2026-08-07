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
from takab_edge.catalog import CatalogStore
from takab_edge.cloud import AwsIotMqttTransport, CloudConnector, MqttTransport
from takab_edge.config import ConfigStore, EdgeSettings, SiteLocationCache, load_settings
from takab_edge.contracts import (
    AlertSource,
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
from takab_edge.gpio_link import build_gpio_link
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
        lora_transport=None,
        lora_site_key: bytes | None = None,
    ) -> None:
        self.settings = settings
        self._seedlink_source = seedlink_source
        self._mqtt_transport = mqtt_transport
        # [T-2.33] Radio LoRa: inyectado (tests/simulador) > serial real si
        # lora.enabled > ninguno (módulo dormido). La clave de sitio viaja por
        # env (TAKAB_EDGE_LORA_KEY) o inyectada en tests.
        self._lora_transport = lora_transport
        self._lora_site_key = lora_site_key
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

    def _build_lora(self, s: EdgeSettings):
        """[T-2.33] Enlace LoRa: inyectado > serial real (lora.enabled) > None.

        No-crítico y fuera del camino GPIO (regla de oro 4): sin radio ni
        secundarios el gabinete opera exactamente igual que antes.
        """
        from takab_edge.lora import LoraLink, SerialLoraTransport

        transport = self._lora_transport
        if transport is None:
            if not s.lora.enabled:
                return None
            transport = SerialLoraTransport(s.lora.port, s.lora.baud)
        key = self._lora_site_key
        if key is None:
            key = os.environ.get("TAKAB_EDGE_LORA_KEY", "").encode()
            if not key:
                if s.dev_mode:
                    key = os.urandom(32)  # efímera, sólo desarrollo
                else:
                    raise RuntimeError("TAKAB_EDGE_LORA_KEY es obligatoria con lora.enabled")
        return LoraLink(s, transport, key)

    def build(self) -> EdgeSupervisor:
        from simulators.bacnet import BacnetSimulator

        s = self.settings
        self.gpio = GpioController(s)
        # [T-2.70.a·D2/P1] LA COSTURA. Se construye UNA vez y es lo único que
        # reciben los cinco consumidores; el `GpioController` de arriba se queda
        # como el DUEÑO de los pines y nadie más que esta costura le habla.
        # Todavía en un solo proceso: `LocalGpioLink` es una llamada directa y el
        # gabinete se comporta exactamente igual. Lo que cambia es que a partir de
        # aquí existe UN sitio por donde pasa todo, que es el que el paso
        # siguiente convierte en IPC.
        # [T-2.70.a·D2/P2] `local` de fábrica: exactamente la llamada directa de
        # D2/P1. Con `TAKAB_EDGE_GPIO_LINK=ipc` la misma costura pasa a ir por el
        # socket del dueño — que hoy es ESTE proceso, así que el gabinete es dueño
        # y cliente a la vez y no se mueve un pin. Eso es lo que D3 enciende.
        self.gpio_link = build_gpio_link(s, self.gpio)
        self.seedlink = self._build_seedlink(s)
        self.signal = FeatureExtractor(s.signal)
        self.buffer = RingBuffer(s.buffer)
        self.rules = RuleEngine(s.thresholds)
        self.bacnet = BacnetSimulator()
        self.actuators = ActuatorManager(
            RelayActuator(self.gpio_link), BacnetActuator(self.bacnet), s.bacnet_channels
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
            gpio=self.gpio_link,
            seedlink=self.seedlink,
            cloud=self.cloud,  # RTT del PUBACK real en el heartbeat (T-1.40)
            heartbeat_s=s.health_heartbeat_s,
        )
        self.security = SecurityManager(_resolve_hmac_key(s), command_ttl_s=s.command_ttl_s)
        # [T-2.34] La config firmada sobrevive reinicios (caché re-verificada al arrancar).
        self.config = ConfigStore(s, security=self.security, cache_path=s.config_cache_path)
        # T-1.71: umbral por sitio aplicado EN VIVO. Al llegar una config firmada
        # (o un rollback), el motor de reglas adopta la banda nueva en la próxima
        # ventana, sin reconstruirse. El camino SASMEX es inmune (evaluate_sasmex
        # ignora umbrales) y la actuación local nunca depende de la nube.
        self.config.add_apply_listener(lambda cfg: self.rules.apply_thresholds(cfg.thresholds))
        # T-2.20: ubicación del sitio con overlay solo-no-nulos («last known
        # good») — un sync parcial jamás la anula; la caché estrecha sobrevive
        # reinicios sin WAN. No es EdgeModule: objeto plano sin ciclo de vida.
        self.location = SiteLocationCache(s)
        self.config.add_apply_listener(self.location.on_config_applied)
        # Voceo por audio (A-6): canal ADVISORY subordinado al camino de vida —
        # se dispara DESPUÉS de actuar y jamás bloquea ni condiciona los relés.
        self.audio = AudioNotifier(s, gpio=self.gpio_link)
        # [T-2.49] El latido reporta QUÉ tonos puede sonar este gabinete, para poder
        # ver desde la flota quién se quedó atrás de un cambio de catálogo.
        self.health.set_audio(self.audio)
        # Un cambio de perfil desde la nube se adopta EN VIVO, sin reiniciar.
        self.config.add_apply_listener(
            lambda cfg: self.audio.apply_audio_profile(cfg.audio.model_dump())
        )
        # Simulacro institucional (T-1.60): observador puro — banner + voceo,
        # CERO relés; lo real (SASMEX o tier instrumental) lo aborta. Se crea
        # ANTES que dispatch (que le enruta drill_start/drill_stop).
        self.drill = DrillController(s, gpio=self.gpio_link, audio=self.audio)
        # T-2.24: catálogo SSN con feed firmado — el archivo provisionado sigue
        # siendo la base; el feed solo lo REFRESCA (mismo HMAC, dominio propio).
        self.catalog = CatalogStore(s.catalog_path, security=self.security)
        # [T-2.33] Espejos de sirena/estrobo a distancia (None sin radio/inyección).
        self.lora = self._build_lora(s)
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
            catalog=self.catalog,
            lora=self.lora,  # T-2.33: comando de red → espejo a secundarios
        )
        # Backfill S3 + evidencia offline (T-1.25): se auto-cablea al conector
        # (router del flush, on_online, suscripción al grant).
        self.backfill = BackfillManager(s, self.cloud, buffer=self.buffer)
        self.local_api = LocalDashboard(
            self.gpio_link,
            self.rules,
            self.health,
            host=s.local_api_host,
            port=s.local_api_port,
            pin=s.local_api_pin,
            dev_mode=s.dev_mode,
            # T-1.53: mini-consola — PGA vivo, enlace a nube e identidad viva.
            signal=self.signal,
            cloud=self.cloud,
            # Fase 2.1: contadores SeedLink (T-2.18) y umbrales/versión vigentes
            # (T-2.16) — el panel lee la MEMORIA VIVA, jamás sondea ni publica.
            seedlink=self.seedlink,
            config=self.config,
            location=self.location,  # T-2.20: lat/lon + vecinos (overlay vivo)
            catalog=self.catalog,  # T-2.23/24: instantánea SSN (+feed firmado)
            rose_zero_path=s.rose_zero_path,  # T-2.29: punto 0 de la brújula
            gateway_id=s.gateway_id,
            site_name=s.site_name,
            refresh_ms=s.local_api_refresh_ms,
            audio=self.audio,
            drill=self.drill,
            dispatch=self.dispatch,  # T-2.32: fuente «QUÓRUM RED» + su cierre
            lora=self.lora,  # T-2.33: salud de secundarios + CLEAR/TEST
            # T-2.67: evidencia pendiente y desenlace del respaldo (instantánea
            # EN MEMORIA del manager; el panel jamás recorre el directorio).
            backfill=self.backfill,
        )

        # [T-2.70.a·D2/P2] Si la costura es la del socket, es un módulo NO
        # crítico y arranca JUSTO DESPUÉS del dueño: los cinco consumidores
        # dependen de `gpio` pero no de ella, así que sin este orden `health`
        # tomaría su instantánea de arranque contra una caché todavía vacía y el
        # primer latido saldría sin relés.
        costura = self.gpio_link if isinstance(self.gpio_link, EdgeModule) else None
        self._modules: dict[str, EdgeModule] = {
            m.name: m
            for m in (
                self.gpio,
                *((costura,) if costura is not None else ()),
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
        if self.lora is not None:
            # [T-2.33] Solo con radio (real o simulado): módulo no-crítico.
            self._modules[self.lora.name] = self.lora
        self._wire()
        self._built = True
        return self

    # --- Cableado del pipeline ---
    def _wire(self) -> None:
        self.seedlink.on_packet(self._on_packet)
        # [T-2.70.a·D2/P1] Los DOS observadores se registran por la costura. El
        # reflejo SASMEX→sirena NO pasa por aquí: vive entero dentro de
        # `gpio._dispatch_sasmex`, bajo su lock y con la latencia medida ANTES de
        # invocar callbacks (gate #6). Lo que cruza es lo que ocurre DESPUÉS.
        self.gpio_link.subscribe("sasmex", self._on_sasmex)
        # T-1.60: un SASMEX real aborta el simulacro (observador aislado en gpio).
        self.gpio_link.subscribe("sasmex", self.drill.on_sasmex)
        # Salud → nube: transición Y heartbeat (T-1.17 G6; sin event_id → sin dedup).
        self.health.on_snapshot(self._on_health_snapshot)
        # Comandos/config firmados nube→edge (T-1.23): el conector (re)suscribe
        # en cada conexión; el dispatcher verifica TODO antes de tocar nada.
        self.cloud.subscribe(self.settings.command_topic, self.dispatch.on_command)
        self.cloud.subscribe(self.settings.config_topic, self.dispatch.on_config)
        # T-2.24: catálogo SSN firmado. OJO política IoT: takab/catalog/<thing>
        # debe estar en Subscribe/Receive de la política de flota ANTES de
        # desplegar esto al Pi (terraform), o el broker rechaza la suscripción.
        self.cloud.subscribe(self.settings.catalog_topic, self.dispatch.on_catalog)

    def _on_packet(self, packet: WaveformPacket) -> None:
        # Detección y actuación PRIMERO: el camino umbral→actuador (regla de oro 1/2)
        # jamás depende de I/O de disco. La persistencia del waveform crudo (para la
        # evidencia) va DESPUÉS y best-effort — un disco lleno (ENOSPC) no debe cegar
        # la detección ni enmascararse como una desconexión de SeedLink.
        feature = self.signal.process(packet)
        decision = self.rules.evaluate_features(feature)
        self._act_and_publish(decision, feature)
        self._observe_shake(decision)
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
            self._observe_shake(decision)

    def _observe_shake(self, decision: TierDecision) -> None:
        """[T-2.19] Observador del agregado del panel: best-effort, DESPUÉS de actuar.

        Vive aquí y no dentro de `RuleEngine` (módulo crítico intocable) ni antes
        de `_act_and_publish`: contar eventos jamás compite con la actuación.
        """
        try:
            self.signal.aggregate.observe_decision(decision)
        except Exception:  # noqa: BLE001 — el conteo del panel nunca tumba el pipeline
            log.warning("agregador de sacudida no disponible (aislado)", exc_info=True)

    def _modo_prueba_activo(self, decision: TierDecision) -> bool:
        """¿Hay ventana de prueba del WR-1 armada? (T-1.69) — y JAMÁS lanza.

        [T-2.70.a·D2/P1] Esta lectura ocurre EN EL HILO DE SEEDLINK. La cadena es
        `_transport.run(...)` → `ingest` → `feed` (sin try) → `_on_packet` →
        `_act_and_publish`, y `_run_transport` atrapa `except Exception`
        rotulándolo «SeedLink desconectado» con reconexión y backoff: una lectura
        que lanzara haría que el gabinete **reportara el Shake caído y encendiera
        la alarma de sensor mudo —la del 14-jul— con el sensor perfectamente
        vivo**. Es el peor de los sitios que cruzan la costura.

        Falla ABIERTO, y la dirección está elegida, no heredada. Las dos ramas, sin
        adornos:

        * Tratarlo como ARMADO suprimiría la publicación de un sismo REAL — la
          nube no abriría incidente ni notificaría a nadie. Irrecuperable.
        * Tratarlo como DESARMADO **despierta el edificio**. No es «ruido», y
          escribirlo así sería mentir en el registro sobre el que se decide D2/P2:
          el `LocalEvent` abre `incidents`, el trigger `trg_incidents_notify`
          levanta al orquestador, y su consulta de incidentes nuevos **no filtra
          por severidad ni por disparo** (`notify/orchestrator.py`); `plan_jobs`
          emite la push **en paralelo a t0, clase CRISIS**, y esa push es
          «ALERTA SÍSMICA» con `interruption-level: time-sensitive`, sonido
          `seismic_alert.caf` a volumen 1.0 y `critical: 1` en APNS, canal Android
          `seismic_alert` en prioridad alta, a **todos** los dispositivos
          registrados del sitio; al abrir la app, `mobile-state` deriva
          `phase = alert_active` y la pantalla se toma entera. Encima va la
          cascada configurada (correo, SMS, webhook).

        Y **no hay filtro aguas abajo que lo recorte**: `LocalEvent` no lleva
        `is_test` ni `drill` —ni el contrato Pydantic ni `local_event.schema.json`
        tienen dónde ponerlo— y T-2.05 fija la garantía como **server-side, «cero
        lógica local de modo prueba»**. El `return` de esta función es la ÚNICA
        defensa que existe hoy contra despertar un edificio por una prueba del
        WR-1.

        Aun así se publica, porque la otra rama es peor y porque la premisa que
        justificaba callar tampoco se sostiene: **es falso que «la protección local
        ya ocurrió» en el caso que hará fallar esta lectura**. Con el IPC de D2/P2,
        que `snapshot()` no conteste significa que el dueño de los pines no
        contesta, y entonces `RelayActuator` tampoco pudo comandar gas, ascensor ni
        retenedores — cruzan exactamente la misma costura. Lo único que sobrevive
        es el reflejo SASMEX→sirena+estrobo, que vive DENTRO del dueño de los pines
        (gate #6). O sea: en el escenario real de este `except`, la protección local
        está a medias y la nube es lo último que queda para que alguien se entere.

        [T-2.70.a·D2/P1] Endurecimiento PROSPECTIVO: con `LocalGpioLink` esta
        lectura es una llamada directa en el mismo proceso, sin transporte que
        pueda caerse, y hoy no hay camino que la haga lanzar. Se escribe ahora
        —mientras no puede fallar— precisamente porque después no habrá tiempo.
        """
        try:
            snap = self.gpio_link.snapshot()
        except Exception:  # noqa: BLE001 — jamás al hilo de SeedLink
            log.exception(
                "no se pudo leer el modo prueba del WR-1; se PUBLICA a la nube. "
                "Fail-open DELIBERADO: esto puede abrir incidente y disparar la "
                "push CRISIS a los teléfonos del sitio, y aun así callar un sismo "
                "real es peor. event_id=%s",
                decision.event_id,
            )
            return False
        if not snap.test_mode_active:
            return False
        log.warning(
            "MODO PRUEBA WR-1: actuación LOCAL ejecutada, NADA publicado a la nube "
            "(tier=%s, %.0fs restantes)",
            decision.tier.value,
            snap.test_mode_remaining_s,
        )
        return True

    def _act_and_publish(self, decision: TierDecision, feature: Feature1s | None) -> None:
        # Secuencia de actuación del tier. En evacuate incluye la sirena general:
        # en la ruta SASMEX es idempotente con el reflejo in-process de gpio; en la
        # ruta instrumental (umbral, sin SASMEX) es la única alerta audible (§4.5).
        # [T-2.31] Solo canales INSTALADOS en el sitio. Se lee del store vivo
        # (config.current(): apply_signed_update REEMPLAZA el objeto settings) —
        # jamás de self.settings, que queda congelado al del arranque. El reflejo
        # SASMEX in-process de gpio no pasa por aquí y queda intocado.
        live = self.config.current()
        # [T-2.32 · política ratificada 2026-08-03] El umbral instrumental LOCAL
        # es SOLO AVISO: con source=THRESHOLD y sin opt-in del sitio no se
        # comanda NINGÚN actuador ni voceo — el panel muestra el aviso, el
        # evento viaja a la nube (alimenta el quórum) y la evidencia se guarda.
        # SASMEX y MANUAL no entran por esta rama (source distinto).
        visual_only = decision.source is AlertSource.THRESHOLD and not live.instrumental_actuation
        if visual_only:
            acks = []
            if decision.tier in (Tier.EVACUATE_OR_HOLD, Tier.RESTRICTED):
                log.warning(
                    "AVISO instrumental SIN actuación (política T-2.32): tier=%s event_id=%s",
                    decision.tier.value,
                    decision.event_id,
                )
        else:
            commands = [c for c in commands_for(decision) if live.equipment.has(c.channel)]
            acks = self.actuators.execute_sequence(commands)
        failed = [ack.channel.value for ack in acks if not ack.success]
        if failed:
            # Actuación de vida fallida: avisar de inmediato. La escalación a la nube como
            # alarma (T-1.11) y el fallback por contrato al relé (T-1.10) van aparte.
            log.warning("actuación con fallo(s) en %s (event_id=%s)", failed, decision.event_id)
        # Voceo ADVISORY (A-6) tras actuar los relés: nunca antes, nunca bloqueante,
        # y sus fallos se aíslan dentro del propio módulo. En solo-aviso NO hay
        # voceo: «no activa nada, solo un aviso visual en la pantalla».
        if not visual_only:
            # [T-2.70.a·D2/P1] AISLADO. Iba sin try, y dentro `audio._play`
            # consultaba el silencio del operador FUERA de su propio try: una
            # excepción ahí abortaba TODO lo que viene después —espejo LoRa a los
            # secundarios, aborto del simulacro, ACKs a la nube, `LocalEvent` y
            # encolado de evidencia—. Un canal declarado ADVISORY (A-6) no puede
            # tumbar la publicación del evento.
            try:
                self.audio.on_tier(decision)
            except Exception:  # noqa: BLE001 — advisory: jamás al camino de vida
                log.exception("voceo del tier falló (aislado); la actuación sigue")
        # [T-2.33] Espejo a gabinetes secundarios SOLO cuando el principal ACTÚA
        # (SASMEX u opt-in instrumental): evacuate ⇒ sirena+estrobo remotos;
        # restricted ⇒ estrobo. Fire-and-forget tras la actuación local — y ANTES
        # del corte de nube del modo prueba WR-1: los secundarios son protección
        # local, como la sirena que SÍ suena en la prueba.
        if self.lora is not None and not visual_only:
            if decision.tier is Tier.EVACUATE_OR_HOLD:
                self.lora.propagate("activate", siren=True, strobe=True)
            elif decision.tier is Tier.RESTRICTED:
                self.lora.propagate("activate", strobe=True)
        # T-1.60: un tier instrumental de protección aborta el simulacro en curso.
        self.drill.on_tier(decision)
        # [T-1.69] Modo prueba del WR-1: la protección LOCAL ya ocurrió (relés +
        # reflejo + voceo); se SUPRIME todo lo que va a la nube (acks + evento +
        # evidencia) para probar el WR-1 sin abrir incidente ni notificar. La
        # ventana auto-expira: ante una alerta REAL, el local protege igual.
        if self._modo_prueba_activo(decision):
            return
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
