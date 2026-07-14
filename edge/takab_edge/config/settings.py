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
    sta_seconds: float = Field(default=0.5, gt=0)
    lta_seconds: float = Field(default=5.0, gt=0)
    clip_count: int = Field(default=8_300_000, gt=0)  # ~±2^23 (ADC 24-bit del RS4D)


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

    # --- audio de voceo (A-6; canal ADVISORY — la sirena de RELÉ es la primaria) ---
    #: El voceo arranca DESHABILITADO: se enciende por gabinete cuando el hardware
    #: de audio (DAC/amplificador/bocina; el Pi 5 no trae jack) exista físicamente.
    audio_enabled: bool = False
    #: Dispositivo ALSA para ``aplay -D`` (p.ej. "default", "hw:1,0" con DAC USB).
    audio_device: str = "default"
    #: Mensajes hablados: DEBEN ser dos audios claramente DISTINTOS (sismo real vs
    #: simulacro). Con audio_enabled=true, ambos archivos deben existir al arrancar.
    audio_sismo_path: str = ""
    audio_simulacro_path: str = ""

    # --- gpio / camino de vida (blueprint §4.3; presupuesto SASMEX→actuación <100 ms) ---
    debounce_ms: int = 50  # rebote del contacto WR-1 (parte del presupuesto)
    siren_test_duration_s: float = 2.0  # duración del self-test del botón de prueba
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
    thresholds: ThresholdBand = Field(default_factory=ThresholdBand)
    pins: GpioPins = Field(default_factory=GpioPins)
    signal: SignalConfig = Field(default_factory=SignalConfig)
    buffer: BufferConfig = Field(default_factory=BufferConfig)
    #: Canales de la secuencia extendida enrutados a **BACnet/IP** por contrato del sitio
    #: (gas/ascensores/puertas). Vacío = todo por relé local [SUPUESTO plan-maestro-01 #4].
    #: La sirena/estrobo NUNCA van por BACnet (vida audible = relé local directo).
    bacnet_channels: list[ActuatorChannel] = Field(default_factory=list)
    #: Periodo del heartbeat de salud (beacon de vida); las transiciones se loguean aparte.
    health_heartbeat_s: float = Field(default=60.0, gt=0)
    #: Punto de montaje que reporta la sonda de disco del panel (T-1.53).
    health_disk_path: str = "/"


def load_settings() -> EdgeSettings:
    """Carga la configuración desde entorno/defaults."""
    return EdgeSettings()
