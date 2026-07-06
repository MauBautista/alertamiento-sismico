"""Fixtures compartidos — todo corre sin hardware (gpiozero MockFactory)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory
from takab_edge.config import EdgeSettings, load_settings


@pytest.fixture(autouse=True)
def mock_pin_factory() -> Iterator[None]:
    """Aísla el estado de pines por test con una MockFactory fresca."""
    previous = Device.pin_factory
    Device.pin_factory = MockFactory()
    try:
        yield
    finally:
        Device.pin_factory.reset()
        Device.pin_factory = previous


@pytest.fixture
def settings() -> EdgeSettings:
    return load_settings()  # dev_mode=True por defecto


@pytest.fixture
def supervisor(settings: EdgeSettings):
    """Supervisor construido y arrancado, sin fuente SeedLink automática."""
    from takab_edge.supervisor import EdgeSupervisor

    sup = EdgeSupervisor(settings, seedlink_source=None)
    sup.start()
    try:
        yield sup
    finally:
        sup.stop()
