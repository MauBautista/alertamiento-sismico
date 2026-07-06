"""config — configuración del edge (settings + store local + sync firmada)."""

from takab_edge.config.settings import (
    DEFAULT_FAILSAFE,
    BufferConfig,
    EdgeSettings,
    GpioPins,
    SignalConfig,
    ThresholdBand,
    load_settings,
)
from takab_edge.config.store import ConfigStore

__all__ = [
    "DEFAULT_FAILSAFE",
    "BufferConfig",
    "ConfigStore",
    "EdgeSettings",
    "GpioPins",
    "SignalConfig",
    "ThresholdBand",
    "load_settings",
]
