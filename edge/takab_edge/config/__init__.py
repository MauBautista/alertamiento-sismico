"""config — configuración del edge (settings + store local + sync firmada)."""

from takab_edge.config.location import SiteLocationCache
from takab_edge.config.settings import (
    DEFAULT_FAILSAFE,
    BufferConfig,
    EdgeSettings,
    EquipmentProfile,
    GpioPins,
    LoraConfig,
    NeighborStation,
    SecondaryCabinet,
    SignalConfig,
    ThresholdBand,
    load_settings,
)
from takab_edge.config.store import ConfigError, ConfigStore

__all__ = [
    "DEFAULT_FAILSAFE",
    "BufferConfig",
    "ConfigError",
    "ConfigStore",
    "EdgeSettings",
    "EquipmentProfile",
    "GpioPins",
    "LoraConfig",
    "SecondaryCabinet",
    "NeighborStation",
    "SignalConfig",
    "SiteLocationCache",
    "ThresholdBand",
    "load_settings",
]
