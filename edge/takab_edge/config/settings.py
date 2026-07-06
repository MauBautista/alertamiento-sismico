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
    """Asignación BCM de pines (placeholder; se valida con hardware en T-1.3)."""

    wr1_contact: int = 16
    relay_siren: int = 17
    relay_strobe: int = 27
    relay_gas_valve: int = 22
    relay_elevator: int = 23
    relay_door_retainer: int = 24


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

    # --- Cloud (AWS IoT Core) ---
    mqtt_endpoint: str = ""
    mqtt_port: int = 8883

    # --- local_api (dashboard LAN, sin internet) ---
    local_api_host: str = "0.0.0.0"  # noqa: S104 — LAN del gabinete por diseño
    local_api_port: int = 8080

    # --- Perfil de relés, umbrales y pines ---
    failsafe: dict[ActuatorChannel, FailSafeMode] = Field(
        default_factory=lambda: dict(DEFAULT_FAILSAFE)
    )
    thresholds: ThresholdBand = Field(default_factory=ThresholdBand)
    pins: GpioPins = Field(default_factory=GpioPins)


def load_settings() -> EdgeSettings:
    """Carga la configuración desde entorno/defaults."""
    return EdgeSettings()
