"""Simulador del receptor WR-1 — contacto seco (SASMEX) hacia el módulo `gpio`.

Modela las dos señales del WR-1:
- **alerta SASMEX**: cierre del contacto → reflejo in-process a sirena (blueprint §4.5).
- **pulso de prueba de CIRES**: heartbeat periódico que NO debe actuar (SPOF-03).

Entrega las aserciones vía ``GpioController.simulate_sasmex`` — la MISMA ruta
determinista que ``when_pressed`` del contacto real (ambas confluyen en el reflejo
in-process). La semántica real (latching, duración, cadencia de pruebas) se valida
con hardware en T-1.3.
"""

from __future__ import annotations

from takab_edge.contracts import SasmexSignal
from takab_edge.gpio import GpioController


class WR1Simulator:
    """Inyecta aserciones del contacto seco del WR-1 en el controlador GPIO."""

    def __init__(self, gpio: GpioController) -> None:
        self._gpio = gpio

    def alert(self) -> SasmexSignal:
        """Cierre del contacto de alerta SASMEX (dispara el reflejo a sirena)."""
        return self._gpio.simulate_sasmex(active=True, is_test=False)

    def clear(self) -> SasmexSignal:
        """Apertura del contacto (fin de la aserción)."""
        return self._gpio.simulate_sasmex(active=False, is_test=False)

    def test_pulse(self) -> SasmexSignal:
        """Pulso de prueba periódica de CIRES — heartbeat, sin actuación."""
        return self._gpio.simulate_sasmex(active=True, is_test=True)
