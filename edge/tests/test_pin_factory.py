"""Producción fija LGPIOFactory EXPLÍCITA y truena si no puede (hallazgo A-2).

Lección de 9361e27: con ``ProtectSystem=strict`` y CWD de solo lectura,
``LGPIOFactory`` no instancia y la auto-selección de gpiozero cae EN SILENCIO al
backend ``native`` (sysfs), que en Pi 5 muere con EINVAL — o peor, medio-funciona.
Contrato de producción (``dev_mode=False``):

- ``GPIOZERO_PIN_FACTORY`` explícita ⇒ se respeta (gpiozero ya truena solo si ese
  nombre no carga; no hay fallback en modo explícito). Es la vía de los tests/CI.
- Factory ya fijada en el proceso (harness de pruebas) ⇒ se respeta con warning.
- Proceso fresco (factory None, sin env) — la realidad del Pi bajo systemd —
  ⇒ ``LGPIOFactory()`` explícita o ``RuntimeError`` ruidoso. Jamás auto-selección.
"""

from __future__ import annotations

import sys
import types

import pytest
from gpiozero import Device
from takab_edge.gpio import GpioController, ensure_prod_pin_factory


@pytest.fixture
def proceso_fresco(monkeypatch) -> None:
    """El estado real del Pi al arrancar: sin env y sin factory previa."""
    monkeypatch.delenv("GPIOZERO_PIN_FACTORY", raising=False)
    # El conftest autouse deja una MockFactory; el modo estricto parte de None.
    monkeypatch.setattr(Device, "pin_factory", None)


def _lgpio_falso(factory_cls: type) -> types.ModuleType:
    mod = types.ModuleType("gpiozero.pins.lgpio")
    mod.LGPIOFactory = factory_cls
    return mod


def test_prod_fija_lgpio_explicita(proceso_fresco, monkeypatch) -> None:
    """Sin env y sin factory previa ⇒ LGPIOFactory queda fijada, no auto-selección."""

    class _FakeLGPIO:
        pass

    monkeypatch.setitem(sys.modules, "gpiozero.pins.lgpio", _lgpio_falso(_FakeLGPIO))
    ensure_prod_pin_factory()
    assert isinstance(Device.pin_factory, _FakeLGPIO)


def test_prod_truena_si_lgpio_no_importa(proceso_fresco, monkeypatch) -> None:
    """lgpio ausente (extra `hardware` sin instalar) ⇒ RuntimeError, factory intacta."""
    monkeypatch.setitem(sys.modules, "gpiozero.pins.lgpio", None)  # import ⇒ ImportError
    with pytest.raises(RuntimeError, match="lgpio"):
        ensure_prod_pin_factory()
    assert Device.pin_factory is None  # jamás quedó otro backend puesto


def test_prod_truena_si_lgpio_no_instancia(proceso_fresco, monkeypatch) -> None:
    """La trampa de 9361e27: el FIFO no se puede crear ⇒ RuntimeError con la pista."""

    class _Explota:
        def __init__(self) -> None:
            raise OSError("no se puede crear .lgd-nfy0 (sistema de archivos de solo lectura)")

    monkeypatch.setitem(sys.modules, "gpiozero.pins.lgpio", _lgpio_falso(_Explota))
    with pytest.raises(RuntimeError, match="WorkingDirectory"):
        ensure_prod_pin_factory()
    assert Device.pin_factory is None


def test_idempotente_no_reinstancia(proceso_fresco, monkeypatch) -> None:
    """Segunda llamada con la factory ya puesta ⇒ cero instancias nuevas."""
    creadas = {"n": 0}

    class _FakeLGPIO:
        def __init__(self) -> None:
            creadas["n"] += 1

    monkeypatch.setitem(sys.modules, "gpiozero.pins.lgpio", _lgpio_falso(_FakeLGPIO))
    ensure_prod_pin_factory()
    ensure_prod_pin_factory()
    assert creadas["n"] == 1


def test_env_explicita_se_respeta(monkeypatch) -> None:
    """GPIOZERO_PIN_FACTORY fijada ⇒ no se toca la factory (vía de tests/CI)."""
    monkeypatch.setenv("GPIOZERO_PIN_FACTORY", "mock")
    antes = Device.pin_factory  # la MockFactory del conftest
    ensure_prod_pin_factory()
    assert Device.pin_factory is antes


def test_factory_previa_se_respeta_sin_reemplazo(monkeypatch) -> None:
    """Factory ya fijada en el proceso (harness) ⇒ se respeta, nunca se pisa."""
    monkeypatch.delenv("GPIOZERO_PIN_FACTORY", raising=False)
    antes = Device.pin_factory  # MockFactory del conftest (≠ None)
    ensure_prod_pin_factory()
    assert Device.pin_factory is antes


def test_gpio_prod_no_arranca_sin_lgpio(proceso_fresco, monkeypatch, settings) -> None:
    """Fin a fin: el módulo crítico NO arranca con lgpio roto — truena, no calla."""
    monkeypatch.setitem(sys.modules, "gpiozero.pins.lgpio", None)
    controller = GpioController(settings.model_copy(update={"dev_mode": False}))
    with pytest.raises(RuntimeError, match="lgpio"):
        controller.start()
    assert controller.running is False
