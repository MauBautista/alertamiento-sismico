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
    #: Spool durable de la cola offline (vacío → dir temporal en dev/tests; en el Pi, NVMe).
    cloud_spool_dir: str = ""
    cloud_backoff_s: float = Field(default=1.0, gt=0)  # base de reconexión
    cloud_backoff_max_s: float = Field(default=60.0, gt=0)  # tope del backoff

    # --- local_api (dashboard LAN, sin internet) ---
    local_api_host: str = "0.0.0.0"  # noqa: S104 — LAN del gabinete por diseño
    local_api_port: int = 8080

    # --- gpio / camino de vida (blueprint §4.3; presupuesto SASMEX→actuación <100 ms) ---
    debounce_ms: int = 50  # rebote del contacto WR-1 (parte del presupuesto)
    siren_test_duration_s: float = 2.0  # duración del self-test del botón de prueba

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


def load_settings() -> EdgeSettings:
    """Carga la configuración desde entorno/defaults."""
    return EdgeSettings()
