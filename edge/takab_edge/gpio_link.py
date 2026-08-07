"""gpio_link — la COSTURA entre el dueño de los pines y todo lo que le pregunta.

[T-2.70.a · D2/P1] Hoy la sirena la toca el mismo proceso que hace todo lo demás:
`supervisor.build()` instancia su `GpioController` y se lo reparte a cinco
consumidores (`RelayActuator`, `AudioNotifier`, `DrillController`, `HealthMonitor`,
`LocalDashboard`), dos observadores `on_sasmex` y el modo prueba. Este módulo
interpone una interfaz entre unos y otro **sin mover un solo pin**: sigue siendo un
proceso, sigue siendo una llamada directa, y el gabinete se comporta exactamente
igual. Lo que cambia es que a partir de aquí existe UN sitio por donde pasa todo,
que es el que el paso siguiente convierte en IPC.

Cuatro operaciones, y ni una más:

- :meth:`GpioLink.snapshot` — el estado COMPLETO en una sola lectura atómica.
- :meth:`GpioLink.apply` — una secuencia de demandas en LOTE.
- :meth:`GpioLink.action` — las acciones del operador, por lista BLANCA.
- :meth:`GpioLink.subscribe` — los observadores (`sasmex`, `silence`).

**Lo que NO cruza, y por eso esto es viable.** El reflejo SASMEX→sirena vive
ENTERO dentro de `gpio._dispatch_sasmex`, bajo su propio lock y con la medición de
latencia ANTES de invocar callbacks (gate #6, <100 ms, blueprint §4.3). Aquí no hay
—ni puede haber— una operación que asierte SASMEX. Lo que cruza es actuación
posterior (gas, ascensor, puertas), lectura de estado para el panel, simulacro y
modo prueba: ninguno está en el camino crítico.

**Lo que tampoco se expone: `drive_all_safe()`.** Es estado seguro DURABLE (fija
`_safed` y solo `reset()` lo levanta). Ofrecerlo por la costura significaría que
cualquier consumidor —o, mañana, cualquier cliente del socket— puede dejar el gas
cerrado y las puertas sueltas hasta que alguien vaya al gabinete. Sigue siendo del
ciclo de vida del propio módulo (`_on_stop`), donde ya estaba.

**Cero dependencias nuevas.** Sólo stdlib y `takab_edge.contracts`: el proceso
mínimo del camino de vida (regla de oro 4) no paga nada por esto, y la allowlist
de `tests/test_gpio_process.py` lo vigila.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from takab_edge.contracts import ActuatorChannel, RelayState, SirenReason

log = logging.getLogger("takab_edge.gpio_link")


class GpioLinkUnavailable(OSError):
    """El dueño de los pines NO CONTESTA.

    Hereda de ``OSError`` porque eso es lo que será cuando haya un socket detrás
    (``ConnectionRefusedError``, ``BrokenPipeError`` y ``TimeoutError`` ya lo son),
    y así quien la atrape hoy sigue atrapándola entonces.

    Es una causa DISTINTA de «el módulo está detenido» y de «el módulo está en
    marcha y su lectura reventó»: las tres piden reacciones distintas de quien
    está de pie frente al gabinete, y colapsarlas fue el defecto que T-2.68
    arregló para las otras dos. Con la implementación LOCAL de hoy no puede
    ocurrir —una llamada directa no tiene transporte que caerse—, y aun así los
    consumidores la tratan ya: endurecer ahora, mientras no puede fallar, es
    exactamente cuando se puede hacer sin prisa.
    """


class GpioActionNotAllowed(ValueError):
    """Acción que la costura no admite (lista blanca :data:`GPIO_ACTIONS`)."""


class GpioEventNotAllowed(ValueError):
    """Evento que la costura no admite (:data:`GPIO_EVENTS`)."""


@dataclass(frozen=True, slots=True)
class GpioSnapshot:
    """Estado del gabinete leído de UNA vez, bajo UNA sola toma del lock.

    Hoy cada consumidor lee propiedad a propiedad y cada lectura toma el lock por
    su cuenta: entre `sasmex_active` y `siren_sounding` cabe un cambio de demanda,
    y el panel puede pintar un enclave vivo con la sirena en reposo. En memoria
    eso es una rareza; con un socket detrás son dos respuestas de dos momentos
    distintos, o sea una incoherencia INVENTADA (regla de oro 7).
    """

    running: bool
    sasmex_active: bool
    siren_sounding: bool
    siren_reason: SirenReason | None
    audible_silenced: bool
    alert_latched: bool
    actuation_test_active: bool
    test_mode_active: bool
    test_mode_remaining_s: float
    last_reflex_latency_s: float | None
    relays: tuple[RelayState, ...]


@dataclass(frozen=True, slots=True)
class ChannelOutcome:
    """Resultado POR CANAL de un lote: el aislamiento de hoy, conservado.

    `ActuatorManager` ACKea canal a canal y un actuador que lanza no aborta la
    secuencia. Si el lote fuera todo-o-nada, un canal desconocido dejaría el gas,
    el ascensor y las puertas sin comandar — peor que las cinco llamadas sueltas
    que sustituye.
    """

    channel: ActuatorChannel
    ok: bool
    detail: str


#: Acción de la costura → método del dueño de los pines. Lista BLANCA: lo que no
#: está aquí no se puede pedir, y eso es lo que mantiene `drive_all_safe()` fuera.
GPIO_ACTIONS: dict[str, str] = {
    "silence": "silence_audibles",
    "siren_test": "run_siren_test",
    "actuation_test": "run_local_actuation_test",
    "arm_test_mode": "arm_test_mode",
    "disarm_test_mode": "disarm_test_mode",
    "reset": "reset",
    # No es del panel: la pide `RelayActuator` cuando llega un `self_test` firmado.
    "cabinet_self_test": "run_cabinet_self_test",
}

#: Evento de la costura → registrador de observadores del dueño de los pines.
GPIO_EVENTS: dict[str, str] = {
    "sasmex": "on_sasmex",
    "silence": "on_silence",
}


@runtime_checkable
class GpioLink(Protocol):
    """Contrato único que los consumidores usan para hablar con los pines."""

    def snapshot(self) -> GpioSnapshot:
        """Estado completo del gabinete, atómico."""
        ...

    def apply(self, demands: Sequence[tuple[ActuatorChannel, bool]]) -> tuple[ChannelOutcome, ...]:
        """Aplica una secuencia de demandas de protección como UNA petición."""
        ...

    def action(self, name: str, **params: Any) -> Any:
        """Ejecuta una acción de :data:`GPIO_ACTIONS` y devuelve lo que devuelva."""
        ...

    def subscribe(self, event: str, callback: Callable[..., None]) -> None:
        """Registra un observador de :data:`GPIO_EVENTS`."""
        ...


class LocalGpioLink:
    """Implementación LOCAL: el dueño de los pines está en ESTE proceso.

    Conducta idéntica a la de hoy — cada operación es una llamada directa al
    `GpioController`, sin serializar, sin copiar y sin poder fallar por
    transporte. Es a propósito: D2/P1 introduce la costura y NADA más, para que
    cualquier diferencia de comportamiento que aparezca después sea atribuible al
    IPC y no a este paso.
    """

    __slots__ = ("_gpio",)

    def __init__(self, controller: Any) -> None:
        self._gpio = controller

    def snapshot(self) -> GpioSnapshot:
        return self._gpio.snapshot()

    def apply(self, demands: Sequence[tuple[ActuatorChannel, bool]]) -> tuple[ChannelOutcome, ...]:
        return tuple(self._gpio.apply_demands(demands))

    def action(self, name: str, **params: Any) -> Any:
        metodo = GPIO_ACTIONS.get(name)
        if metodo is None:
            raise GpioActionNotAllowed(
                f"acción no admitida por la costura del gabinete: {name!r}. "
                f"Admitidas: {sorted(GPIO_ACTIONS)}. La lista es BLANCA a propósito: "
                "es lo que mantiene `drive_all_safe()` (estado seguro DURABLE) fuera "
                "del alcance de los consumidores."
            )
        return getattr(self._gpio, metodo)(**params)

    def subscribe(self, event: str, callback: Callable[..., None]) -> None:
        registrador = GPIO_EVENTS.get(event)
        if registrador is None:
            raise GpioEventNotAllowed(
                f"evento no admitido por la costura del gabinete: {event!r}. "
                f"Admitidos: {sorted(GPIO_EVENTS)}."
            )
        getattr(self._gpio, registrador)(callback)


def as_link(target: Any) -> Any:
    """Devuelve una costura: la que ya es, o el controlador crudo envuelto.

    Existe por los tests y por `demo/gabinete.py`, que construyen consumidores
    pasándoles un `GpioController` de verdad; envolverlo aquí los deja
    funcionando sin tocar 177 tests, y el que manda en producción sigue siendo el
    supervisor, que construye la costura UNA vez y se la pasa a los cinco.

    No relaja nada: si alguien pasara un controlador donde debería ir la costura
    del socket, lo que obtiene es un segundo dueño de los pines en su propio
    proceso — y eso lo caza el `flock` de D1.1, que colisiona incluso entre dos
    descriptores del mismo proceso.
    """
    if target is None or isinstance(target, GpioLink):
        return target
    return LocalGpioLink(target)
