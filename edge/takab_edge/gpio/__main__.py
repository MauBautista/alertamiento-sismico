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
from takab_edge.pinlink.server import notificar_systemd

log = logging.getLogger("takab_edge.gpio")


def run_gpio_process(settings: EdgeSettings | None = None, *, block: bool = True) -> GpioController:
    """Arranca el controlador GPIO. Si ``block``, espera hasta SIGINT/SIGTERM.

    [T-2.70.a·D2/P2] `controller.start()` deja hechas, EN ESTE ORDEN, las cuatro
    cosas que definen ser dueño: tomar el cerrojo de pines (D1.1), fijar la pin
    factory, construir los cinco relés y armar los tres botones, y sembrar el
    reflejo si el contacto ya estaba cerrado (SPOF-02). Sólo DESPUÉS abre la
    puerta de servicio y sólo DESPUÉS se avisa a systemd.

    `sd_notify(READY=1)` aquí y no antes: con `Type=simple`, `systemctl start`
    vuelve cuando el proceso arrancó, no cuando es DUEÑO — y el traspaso de
    propiedad de D3 se daría por terminado antes de serlo.

    Y la puerta de servicio va FORZADA aquí, aunque de fábrica esté cerrada
    (`gpio_serve_enabled=False` desde el cierre de la auditoría de D2/P2): este
    proceso existe para SER el dueño de los pines de todo lo demás. Un dueño con
    el que nadie puede hablar no es un traspaso, es un apagón — `takab-edge` sin
    lectura de estado ni actuación posterior, y `deploy.sh` sin `takab-gpioctl`
    para preguntar quién manda.
    """
    cfg = settings or load_settings()
    if not cfg.gpio_serve_enabled:
        cfg = cfg.model_copy(update={"gpio_serve_enabled": True})
    # [T-2.70.a·D3] Este proceso SIEMPRE reclama los pines: no consulta
    # `gpio_owner` para decidir si arranca, y es deliberado. Rechazar el arranque
    # por lo que diga un archivo de configuración añadiría un segundo modo de «el
    # camino de vida no arranca» al que la auditoría de D1 ya dijo que no
    # (`_failsafe`, punto 5): en el gabinete, «fallar al leer la config» y «fallar
    # al tocar un pin» tienen el mismo desenlace físico. Quien arbitra la
    # propiedad es el cerrojo del kernel (D1.1), que no se puede teclear mal.
    # Lo que sí se hace es DECIRLO, porque un `edge.env` que nombre a otro dueño
    # significa que `takab-edge` también va a reclamar y uno de los dos va a morir.
    if cfg.edge_owns_pins:
        log.warning(
            "takab-gpio arranca como DUEÑO DEDICADO de los pines, pero la config de "
            "este gabinete dice TAKAB_EDGE_GPIO_OWNER=%r: `takab-edge` va a reclamar "
            "el mismo cerrojo y uno de los dos NO arrancará (sin tocar un pin, D1.1). "
            "Pon TAKAB_EDGE_GPIO_OWNER=gpio en /etc/takab/edge.env o deshabilita esta "
            "unidad.",
            cfg.gpio_owner,
        )
    controller = GpioController(cfg)
    controller.start()
    notificar_systemd("READY=1")
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
