"""Configuración del edge (Pydantic Settings).

Identidad de gateway (multi-tenant), perfil de relés fail-safe por canal
(SPOF-07, blueprint §4.7) y umbrales por edificio. En producción `ConfigStore`
(T-1.12) sincroniza umbrales/reglas firmados desde la nube; aquí viven los
defaults de arranque. Prefijo de entorno: ``TAKAB_EDGE_``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from takab_edge.contracts import ActuatorChannel, FailSafeMode

# Estado seguro por canal ante falla del Pi (SPOF-07).
DEFAULT_FAILSAFE: dict[ActuatorChannel, FailSafeMode] = {
    ActuatorChannel.SIREN: FailSafeMode.NORMALLY_OPEN,
    ActuatorChannel.STROBE: FailSafeMode.NORMALLY_OPEN,
    ActuatorChannel.GAS_VALVE: FailSafeMode.FAIL_CLOSE,
    ActuatorChannel.ELEVATOR: FailSafeMode.NORMALLY_OPEN,
    ActuatorChannel.DOOR_RETAINER: FailSafeMode.NORMALLY_CLOSED,
}


class AudioProfile(BaseModel):
    """[T-2.49] Tonos elegidos por la nube, **solo por ID de catálogo**.

    Nunca binarios (el doc de config viaja firmado hacia un dispositivo que toca
    sirena y gas) ni rutas absolutas (la nube no conoce el disco del gabinete).
    Vacío = conservar lo empaquetado; un ID que este edge no conoce conserva el
    tono anterior y lo declara en el latido (ver ``audio/catalog.py``).
    """

    siren: str = ""
    test: str = ""


class ThresholdBand(BaseModel):
    """Banda de umbral por tipo de instalación (blueprint §4.5).

    Cada umbral tiene banda `cautela` (watch) y `disparo` (trip) para PGA y PGV.
    Default = hospital (0.040–0.060 g); calibrar por tipología/altura.
    """

    pga_watch_g: float = 0.040
    pga_trip_g: float = 0.060
    pgv_watch_cms: float = 2.0
    pgv_trip_cms: float = 4.0


class GpioPins(BaseModel):
    """Asignación BCM de pines (placeholder; la asignación real se valida en gate #3)."""

    wr1_contact: int = 16  # entrada: contacto seco de alerta SASMEX (WR-1)
    silence_button: int = 5  # entrada: botón de silencio (local)
    test_button: int = 6  # entrada: botón de prueba de sirena (self-test)
    relay_siren: int = 17
    relay_strobe: int = 27
    relay_gas_valve: int = 22
    relay_elevator: int = 23
    relay_door_retainer: int = 24


class SignalConfig(BaseModel):
    """Parámetros de las features 1 s (T-1.6).

    Las sensibilidades convierten counts→físico; los valores por defecto son
    PLACEHOLDER — la calibración real proviene de la respuesta instrumental del
    RS4D (StationXML), un paso de metadata pendiente. El *algoritmo* de las
    features se valida contra ObsPy (<1%); la escala física depende de estos.

    [T-1.33] Mientras sigan siendo placeholder, la nube NO presenta estos valores como
    magnitudes físicas: la consola pinta unidades relativas salvo que el sensor declare
    su ``sensors.calibration_source`` en la DB. Al sustituir estos números por los del
    StationXML, hay que declarar la fuente en ese campo — si no, la UI seguirá (con
    razón) diciendo SIN CALIBRAR.
    """

    vel_sensitivity_ms_per_count: float = 1.0e-9  # geophone EH* (velocidad)
    accel_sensitivity_ms2_per_count: float = 1.0e-6  # MEMS EN* (aceleración)
    #: [T-2.21] Procedencia de la calibración (p.ej. "StationXML FDSN AM.R4F74 2026-07-09").
    #: Vacío ⇒ las sensibilidades de arriba son placeholder y todo cliente rotula
    #: SIN CALIBRAR con unidades relativas (default-deny, espejo exacto de
    #: `sensors.calibration_source` en la nube — no existe checkbox de "calibrado").
    #: En el Pi: TAKAB_EDGE_SIGNAL__CALIBRATION_SOURCE en edge.env.
    calibration_source: str = ""
    sta_seconds: float = Field(default=0.5, gt=0)
    lta_seconds: float = Field(default=5.0, gt=0)
    clip_count: int = Field(default=8_300_000, gt=0)  # ~±2^23 (ADC 24-bit del RS4D)


class NeighborStation(BaseModel):
    """Estación vecina de la red — PURAMENTE INFORMATIVA (T-2.20).

    Invariante (blueprint §4.5, SPOF-01, ratificado en Fase 1.10): el quórum se
    correlaciona en la NUBE y jamás gatea la sirena local. Ningún módulo de
    actuación recibe esta lista; solo el panel LAN la pinta en su plano.
    """

    code: str
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    distance_km: float | None = Field(default=None, ge=0.0)


class BufferConfig(BaseModel):
    """Ring buffer miniSEED en disco (T-1.7).

    `root` vacío → directorio temporal (dev/tests); en el Pi 5, la ruta del NVMe.
    Retención 7–14 días (~0.5–4 GB reales a 100 sps × 4 canales — [ANALISIS-00];
    el tamaño real en GB se mide con hardware, gate #3). `max_bytes` es un tope de
    seguridad además de la poda por antigüedad.
    """

    root: str = ""
    retention_days: int = Field(default=14, gt=0)
    max_bytes: int = Field(default=8 * 1024**3, gt=0)  # ~8 GB (holgura ≥15× en NVMe de 64 GB)


class SecondaryCabinet(BaseModel):
    """[T-2.33] Gabinete secundario LoRa provisionado (ESP32 + sirena/estrobo)."""

    id: int = Field(gt=0, le=0xFFFF)  # u16 de la trama; clave HMAC derivada de él
    name: str = ""
    zone: str = ""


class LoraConfig(BaseModel):
    """[T-2.33] Enlace LoRa a gabinetes secundarios (módem ESP32 por USB-serial).

    ``enabled=False`` de fábrica: el Pi aún no tiene radio — el módulo solo vive
    con el simulador/tests hasta que exista el hardware (915 MHz ISM MX). La
    clave de sitio viaja SOLO por env (``TAKAB_EDGE_LORA_KEY``), jamás en este
    modelo serializable.
    """

    enabled: bool = False
    port: str = "/dev/ttyUSB0"
    baud: int = 115200
    #: Cadencia esperada del heartbeat uplink de cada secundario (ellos emiten).
    heartbeat_s: float = Field(default=90.0, gt=0)
    #: Sin heartbeat durante factor×heartbeat_s ⇒ ENLACE PERDIDO (transición).
    heartbeat_timeout_factor: float = Field(default=3.0, gt=0)
    #: Reintentos de una orden hasta ACK (disciplina de aire: espaciados).
    alarm_retry_max: int = Field(default=5, gt=0)
    alarm_retry_s: float = Field(default=2.0, gt=0)
    secondaries: list[SecondaryCabinet] = Field(default_factory=list)


class EquipmentProfile(BaseModel):
    """[T-2.31] Actuadores INSTALADOS físicamente en el sitio.

    No toda estación tiene gas/ascensores/puertas. La nube lo declara
    (``gateways.equipment``) y llega FUSIONADO en el doc firmado del config
    sync. Default todo-true (compat retro: un doc viejo sin la clave = todo
    instalado). Un canal ausente se filtra en la secuencia de tier, en los
    comandos de nube (ack de rechazo honesto) y en la vista del panel — el
    hardware gpio conserva sus 5 relés (un relé sin cablear es inocuo y los
    handles no se reconstruyen en caliente).
    """

    siren: bool = True
    strobe: bool = True
    gas_valve: bool = True
    elevator: bool = True
    door_retainer: bool = True

    def installed(self) -> frozenset[ActuatorChannel]:
        """Canales instalados (los 5 locales; SYSTEM no es un actuador físico)."""
        return frozenset(
            channel
            for channel in (
                ActuatorChannel.SIREN,
                ActuatorChannel.STROBE,
                ActuatorChannel.GAS_VALVE,
                ActuatorChannel.ELEVATOR,
                ActuatorChannel.DOOR_RETAINER,
            )
            if getattr(self, channel.value)
        )

    def has(self, channel: ActuatorChannel) -> bool:
        """True si el canal está instalado (canales fuera del perfil pasan)."""
        return bool(getattr(self, channel.value, True))


class EdgeSettings(BaseSettings):
    """Configuración raíz del gabinete."""

    model_config = SettingsConfigDict(
        env_prefix="TAKAB_EDGE_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # --- Identidad (multi-tenant) ---
    tenant_id: str = "tenant-dev"
    site_id: str = "site-dev"
    gateway_id: str = "gw-dev-0001"
    station: str = "TAKAB"

    # --- Modo dev: simuladores + gpiozero MockFactory (sin hardware) ---
    dev_mode: bool = True

    # --- SeedLink (Raspberry Shake, TCP 18000) ---
    seedlink_host: str = "127.0.0.1"
    seedlink_port: int = 18000
    sample_rate: float = 100.0
    seedlink_network: str = "AM"
    seedlink_station: str = ""  # vacío → usa `station`
    seedlink_location: str = "00"
    seedlink_channels: list[str] = ["EHZ", "ENZ", "ENN", "ENE"]
    seedlink_backoff_initial_s: float = Field(default=1.0, gt=0)  # >0: evita hot-spin
    seedlink_backoff_max_s: float = Field(default=30.0, gt=0)

    @property
    def seedlink_station_code(self) -> str:
        return self.seedlink_station or self.station

    # --- Cloud (AWS IoT Core) ---
    mqtt_endpoint: str = ""
    mqtt_port: int = 8883
    #: mTLS X.509 del gateway (T-1.15). Endpoint + los 3 paths activan el transporte real.
    mqtt_cert_path: str = ""
    mqtt_key_path: str = ""
    mqtt_ca_path: str = ""
    #: Thing name IoT (= client_id MQTT, convención fija); vacío → `gateway_id`.
    iot_thing: str = ""
    #: Spool durable de la cola offline (vacío → dir temporal en dev/tests; en el Pi, NVMe).
    cloud_spool_dir: str = ""
    cloud_backoff_s: float = Field(default=1.0, gt=0)  # base de reconexión
    cloud_backoff_max_s: float = Field(default=60.0, gt=0)  # tope del backoff
    #: Tope de mensajes encolados POR TOPIC de telemetría reponible (features/health):
    #: 48 h offline no deben agotar RAM/inodos del Pi. Eventos/ACKs no llevan cota.
    cloud_telemetry_cap: int = Field(default=10_000, gt=0)
    #: [T-1.56] Batcheo escalonado por tier de la telemetría de features — SOLO la
    #: publicación (la detección/actuación jamás pasa por aquí; el panel LAN sigue
    #: leyendo in-process a 1 Hz). En tier `normal` se acumula y se publica 1 mensaje
    #: batch cada `cloud_features_batch_s`; al escalar a `watch`+ se hace flush
    #: inmediato y se vuelve al 1 Hz individual. `enabled=False` = kill-switch
    #: operativo: passthrough 1 Hz exacto (camino previo a T-1.56).
    cloud_features_batch_enabled: bool = True
    cloud_features_batch_s: float = Field(default=10.0, gt=0)
    #: Features por mensaje batch. le=256 = maxItems del contrato `feature_batch`
    #: (~64 KB « 128 KB del publish de IoT); el default 64 ≈ 16 KB.
    cloud_features_batch_max: int = Field(default=64, gt=0, le=256)

    @property
    def thing_name(self) -> str:
        """Identidad MQTT: thing name IoT o, en su defecto, el serial del gateway."""
        return self.iot_thing or self.gateway_id

    @property
    def status_topic(self) -> str:
        """Topic retained de presencia (LWT offline / online al conectar)."""
        return f"takab/status/{self.thing_name}"

    #: Ventana de validez de un comando remoto firmado (regla de oro 8: "JWT corto").
    command_ttl_s: float = Field(default=30.0, gt=0)
    #: Ejecución de comandos remotos de actuador: APAGADA por defecto por gateway
    #: (regla de oro 8: la superficie más sensible se habilita explícitamente).
    #: Un comando firmado válido con esto en False se RECHAZA con ack 'rejected'.
    command_enabled: bool = False

    @property
    def command_topic(self) -> str:
        """Topic de comandos firmados nube→edge (T-1.23)."""
        return f"takab/cmd/{self.thing_name}"

    @property
    def config_topic(self) -> str:
        """Topic de config firmada nube→edge (T-1.23)."""
        return f"takab/cfg/{self.thing_name}"

    @property
    def catalog_topic(self) -> str:
        """Topic del catálogo SSN firmado nube→edge (T-2.24)."""
        return f"takab/catalog/{self.thing_name}"

    # --- backfill por S3 (T-1.25; regla FASE-0 capa 4) ---
    #: Umbral de la ruta S3: spool con MÁS de esto (s) de datos → S3; si no, MQTT.
    backfill_threshold_s: float = Field(default=900.0, gt=0)  # 15 min
    #: Jitter máximo antes del request (anti-thundering-herd tras apagón regional).
    backfill_jitter_max_s: float = Field(default=120.0, ge=0)
    #: Espera máxima del grant; vencida ⇒ fallback a MQTT (los datos no se atoran).
    backfill_grant_timeout_s: float = Field(default=30.0, gt=0)

    @property
    def backfill_request_topic(self) -> str:
        """Topic de solicitud de URL pre-firmada edge→nube (T-1.25)."""
        return f"takab/backfill/request/{self.thing_name}"

    @property
    def backfill_grant_topic(self) -> str:
        """Topic del grant pre-firmado nube→edge (T-1.25)."""
        return f"takab/backfill/grant/{self.thing_name}"

    #: Ventana de evidencia miniSEED alrededor del evento confirmado (T-1.25):
    #: pre-roll y post-roll en segundos (se sube cuando la ventana está completa).
    evidence_pre_s: float = Field(default=60.0, ge=0)
    evidence_post_s: float = Field(default=120.0, ge=0)

    # --- Ubicación del sitio (T-2.20, P-6) ---
    #: Coordenadas del gabinete. FUENTE DE VERDAD = edge.env (sobreviven reinicios
    #: sin WAN gratis); el sync firmado solo puede COMPLETARLAS, jamás anularlas
    #: (overlay solo-no-nulos en `config/location.py` — `apply_signed_update` es
    #: reemplazo total y la nube publica documentos parciales por diseño).
    #: None = SIN UBICACIÓN PROVISIONADA: el panel no inventa un punto.
    site_lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    site_lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    #: Vecinas de la red (informativas; el quórum vive en la NUBE — ver arriba).
    neighbors: list[NeighborStation] = Field(default_factory=list)
    #: Caché estrecha de la ubicación APRENDIDA por sync (JSON). Deliberadamente
    #: NO un caché general del ConfigStore: persistir config firmada obligaría a
    #: persistir el high_water anti-replay, y cachear umbrales tocaría actuación.
    #: La ubicación no dispara nada. Se lee UNA vez al arrancar, jamás en status().
    site_location_cache: str = "/var/lib/takab/site_location.json"

    # --- local_api (dashboard LAN, sin internet) ---
    local_api_host: str = "0.0.0.0"  # noqa: S104 — LAN del gabinete por diseño
    local_api_port: int = 8080
    #: Nombre del sitio que muestra la mini-consola LAN (T-1.53). Vacío ⇒ se
    #: muestra el gateway_id. En el Pi real: TAKAB_EDGE_SITE_NAME="Sitio Dev Puebla".
    site_name: str = ""
    #: Cadencia (ms) del poll del panel LAN; viaja EN el payload de /api/status.
    local_api_refresh_ms: int = Field(default=1000, gt=249)
    #: PIN de las ACCIONES del panel LAN (T-1.43, header X-Takab-Pin). Vacío +
    #: dev_mode ⇒ abierto (tests/demo); vacío en PRODUCCIÓN ⇒ POST 403
    #: fail-closed hasta provisionarlo (provision_gateway.sh lo genera).
    local_api_pin: str = ""
    #: [T-2.23] Instantánea local del catálogo SSN (JSON, formato del entregable
    #: de diseño) que sirve `GET /api/catalog`. Se lee UNA vez al construir el
    #: panel; ausente/corrupta ⇒ `available: false` y el panel rotula
    #: `CATÁLOGO NO DISPONIBLE · SIN DATOS EN CACHÉ`. La instala
    #: `provision_gateway.sh --catalog FILE`. El feed nube→edge firmado = T-2.24.
    catalog_path: str = "/var/lib/takab/ssn-catalog.json"

    #: [T-2.29] PUNTO 0 de la brújula del panel: media EN* capturada con el
    #: gabinete instalado y nivelado (presentación pura; jamás toca umbrales ni
    #: actuación). Se fija/restablece desde el panel con PIN y sobrevive reinicios.
    rose_zero_path: str = "/var/lib/takab/rose-zero.json"

    # --- audio de voceo (A-6; canal ADVISORY — la sirena de RELÉ es la primaria) ---
    #: El voceo hablado arranca DESHABILITADO: exige dos WAVs grabados (sismo vs
    #: simulacro) que se enciende por gabinete cuando existan. (El "cerebro" real es
    #: un Pi 4 CON jack 3.5 mm; un Pi 5 no lo trae y exigiría DAC USB o HAT I2S.)
    audio_enabled: bool = False
    #: Dispositivo ALSA para ``aplay -D`` (p.ej. "default" = jack 3.5 mm del Pi 4).
    audio_device: str = "default"
    #: Mensajes hablados: DEBEN ser dos audios claramente DISTINTOS (sismo real vs
    #: simulacro). Con audio_enabled=true, ambos archivos deben existir al arrancar.
    audio_sismo_path: str = ""
    audio_simulacro_path: str = ""
    #: [T-1.68] Sirena por AUDIO (jack 3.5 mm): toggle PROPIO, independiente del
    #: voceo. Con el asset sintetizado empaquetado, se enciende SIN grabar nada —
    #: cuando suena la sirena (`gpio.siren_sounding`), se reproduce el WAV en bucle
    #: por el jack. Sigue siendo ADVISORY: la sirena de RELÉ es y será la primaria.
    audio_siren_enabled: bool = False
    #: WAV de la sirena; vacío ⇒ el asset empaquetado (takab_edge/audio/assets/siren.wav).
    audio_siren_path: str = ""
    #: [T-2.49] Tono del SELF-TEST de sirena. Vacío ⇒ `assets/prueba.wav` empaquetado.
    #: Si tampoco existe, una prueba CALLA: jamás cae al tono de alerta real.
    audio_test_path: str = ""

    # --- gpio / camino de vida (blueprint §4.3; presupuesto SASMEX→actuación <100 ms) ---
    debounce_ms: int = 50  # rebote del contacto WR-1 (parte del presupuesto)
    siren_test_duration_s: float = 2.0  # duración del self-test del botón de prueba
    #: [T-1.69] Modo prueba del WR-1: ventana (s) en la que un disparo (SASMEX real o
    #: instrumental) protege en LOCAL igual que siempre (reflejo+sirena+actuadores) pero
    #: NO se publica a la nube (sin incidente ni notificación). Auto-expira: corto a
    #: propósito — dejarlo armado silenciaría a la nube ante una alerta REAL.
    sasmex_test_window_s: float = 120.0
    #: [T-1.67] Prueba LOCAL de actuación: cuánto SOSTIENE la sirena+estrobo (para
    #: oírlos/verlos) mientras gas/ascensor/puertas hacen su pulso de verificación.
    actuation_test_hold_s: float = 5.0
    #: [T-1.59] Autodiagnóstico remoto (self_test): pulso por relé NO audible y
    #: pausa entre relés. ~4 relés × (pulso+pausa) ≈ 1.6 s por recorrido.
    self_test_pulse_ms: int = Field(default=250, gt=0)
    self_test_gap_ms: int = Field(default=150, ge=0)

    # --- Perfil de relés, umbrales y pines ---
    failsafe: dict[ActuatorChannel, FailSafeMode] = Field(
        default_factory=lambda: dict(DEFAULT_FAILSAFE)
    )
    #: [T-2.31] Actuadores INSTALADOS en el sitio (la nube lo declara y viaja
    #: fusionado en el doc firmado del config sync). Default todo-true = compat
    #: retro. gpio conserva sus 5 relés (hardware); el perfil filtra la
    #: secuencia de tier, los comandos de nube y la vista del panel.
    equipment: EquipmentProfile = Field(default_factory=lambda: EquipmentProfile())
    #: [T-2.32 · política ratificada 2026-08-03] La detección instrumental LOCAL
    #: es SOLO AVISO VISUAL por defecto (una estación sola no activa nada, ni
    #: siquiera sin nube). La actuación viene de SASMEX (reflejo gpio, intocado)
    #: o del comando FIRMADO de quórum ≥3 de la nube. `True` = opt-in explícito
    #: por sitio que restaura la actuación instrumental autónoma de Fase 1.
    instrumental_actuation: bool = False
    #: [T-2.65] Estado ADMINISTRATIVO del gabinete en la nube, transportado dentro
    #: del mismo sobre firmado del config sync (ningún topic nuevo). Un gabinete
    #: retirado SIGUE PROTEGIENDO —el retiro es un acto de inventario que viaja
    #: por la nube, y apagar la protección convertiría un clic en la desprotección
    #: física de un edificio con gente dentro (reglas de oro 1 y 2)—; esto solo lo
    #: DECLARA en el panel, para que el silencio deje de ser indistinguible de una
    #: avería. NO actúa sobre nada: el reflejo SASMEX→sirena ni siquiera lo ve.
    #:
    #: `str` PELADO Y A PROPÓSITO, jamás `Literal[...]` ni Enum: `ConfigStore`
    #: valida el documento COMPLETO antes de aplicarlo, así que un valor fuera del
    #: enum (si la nube dejara de colapsar `gateways.status` a dos valores) tiraría
    #: el doc ENTERO —umbrales y `command_enabled` incluidos— y, como `_high_water`
    #: solo sube tras validar, se reintentaría idéntico para siempre. Fail-open
    #: hacia PROTEGER en los dos lados: aquí, todo lo que no sea exactamente
    #: "retired" es activo; allá, el CASE de SQL colapsa a dos valores.
    cloud_admin_state: str = "active"
    thresholds: ThresholdBand = Field(default_factory=ThresholdBand)
    #: [T-2.49] Perfil de tonos. ANIDADO dentro de `config.edge`, de modo que
    #: `commands/sync.py` y el espejo `in_sync` de la nube no cambian.
    audio: AudioProfile = Field(default_factory=AudioProfile)
    pins: GpioPins = Field(default_factory=GpioPins)
    signal: SignalConfig = Field(default_factory=SignalConfig)
    buffer: BufferConfig = Field(default_factory=BufferConfig)
    #: Canales de la secuencia extendida enrutados a **BACnet/IP** por contrato del sitio
    #: (gas/ascensores/puertas). Vacío = todo por relé local
    #: [RATIFICADO 2026-07-09 · T-1.45 · gate #4].
    #: La sirena/estrobo NUNCA van por BACnet (vida audible = relé local directo).
    bacnet_channels: list[ActuatorChannel] = Field(default_factory=list)
    #: [T-2.34] Caché de la config firmada aplicada (+high_water anti-replay):
    #: sobrevive reinicios — sin ella el edge arrancaba en v0 con defaults hasta
    #: el siguiente cambio de config en la nube. Vacío = sin persistencia.
    config_cache_path: str = "/var/lib/takab/config-cache.json"
    #: [T-2.33] Gabinetes secundarios LoRa (espejos de sirena/estrobo a distancia).
    lora: LoraConfig = Field(default_factory=LoraConfig)
    #: Periodo del heartbeat de salud (beacon de vida); las transiciones se loguean aparte.
    health_heartbeat_s: float = Field(default=60.0, gt=0)
    #: Punto de montaje que reporta la sonda de disco del panel (T-1.53).
    health_disk_path: str = "/"

    @property
    def is_retired(self) -> bool:
        """[T-2.65] ¿La nube dio de baja este gabinete? (declarativo, no actúa).

        Comparación EXACTA, sin `strip()` ni `lower()`: un `RETIRED` inesperado
        debe leerse como ACTIVO, no adivinarse. Adivinar aquí solo puede pintar un
        cartel de baja en un gabinete sano.
        """
        return self.cloud_admin_state == "retired"


def load_settings() -> EdgeSettings:
    """Carga la configuración desde entorno/defaults."""
    return EdgeSettings()
