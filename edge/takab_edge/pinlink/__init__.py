"""pinlink — el TRANSPORTE entre el dueño de los pines y sus clientes.

[T-2.70.a · D2/P2] D2/P1 dejó la costura (`takab_edge.gpio_link`): cuatro
operaciones y una implementación LOCAL que es una llamada directa. Aquí está la
segunda implementación —socket `AF_UNIX`— **sin encenderla todavía**: el servidor
vive DENTRO del dueño actual, así que hoy el mismo proceso es dueño y cliente y
no se mueve un solo pin. D3 lo enciende con una línea y lo acredita en el Pi real
sin traspasar la propiedad.

Tres módulos y nada más:

* :mod:`~takab_edge.pinlink.codec` — marco y traducción del contrato, derivada de
  la propia declaración de `GpioSnapshot`.
* :mod:`~takab_edge.pinlink.server` — la puerta de servicio del dueño, hilo NO
  crítico: si no puede atar el socket, el reflejo vive igual.
* :mod:`~takab_edge.pinlink.client` — `IpcGpioLink`, caché-first y `critical=False`.

**Ninguna dependencia NUEVA.** No «stdlib puro»: `codec` importa
`pydantic.BaseModel` porque los contratos del gabinete son modelos Pydantic. Lo
que la allowlist de D1.3 (`tests/test_gpio_process.py`) garantiza —y sí caza,
nombrando por dónde entró— es que el proceso mínimo no gane dependencias que no
estén declaradas ahí; este paquete tiene que seguir pasando por ella.
"""

from __future__ import annotations

from takab_edge.pinlink.client import (
    EDAD_MAXIMA_S,
    GpioRemoteError,
    IpcGpioLink,
)
from takab_edge.pinlink.server import KEEPALIVE_S, SONDEO_S, PinLinkServer, notificar_systemd

__all__ = [
    "EDAD_MAXIMA_S",
    "KEEPALIVE_S",
    "SONDEO_S",
    "GpioRemoteError",
    "IpcGpioLink",
    "PinLinkServer",
    "notificar_systemd",
]
