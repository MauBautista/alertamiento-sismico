"""Proceso mínimo del camino de vida — SOLO `gpio` (WR-1 + relés + reflejo).

Regla de oro 4: el proceso GPIO/actuadores es mínimo y auditable, **sin
dependencias pesadas**. Este entry point NO importa `supervisor`/`seedlink`/
`signal` (que arrastran ObsPy/NumPy/SciPy); arranca en <1 s y sostiene el
reflejo SASMEX→sirena aunque el resto del edge no exista.

Ejecutar:  ``python -m takab_edge.gpio``  ·  o el script ``takab-gpio``.
"""

from __future__ import annotations

import logging
import signal as _signal
import threading

from takab_edge.config import EdgeSettings, load_settings
from takab_edge.gpio import GpioController

log = logging.getLogger("takab_edge.gpio")


def run_gpio_process(settings: EdgeSettings | None = None, *, block: bool = True) -> GpioController:
    """Arranca el controlador GPIO. Si ``block``, espera hasta SIGINT/SIGTERM."""
    controller = GpioController(settings or load_settings())
    controller.start()
    if not block:
        return controller

    stop = threading.Event()
    for sig in (_signal.SIGINT, _signal.SIGTERM):
        _signal.signal(sig, lambda *_: stop.set())
    try:
        stop.wait()
    finally:
        controller.stop()
    return controller


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    run_gpio_process()


if __name__ == "__main__":
    main()
