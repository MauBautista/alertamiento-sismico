"""[T-2.146] EL LATIDO DE KEEP-ALIVE DE SPOF-02, Y POR QUÉ NO ES UN `while True: toggle`.

El latido existe para que un **monoestable retriggerable** de hardware sepa si el
Pi puede todavía gobernar la sirena. Su salida energiza `K_wd`, y `K_wd`
**inhibe** la ruta de hardware que hace sonar la sirena directamente desde el
contacto del WR-1 (variante B, `D-10`).

De ahí sale la única propiedad que este módulo tiene que probar, y es una
propiedad NEGATIVA:

    un reflejo que no puede ejecutarse NO DEBE PODER LATIR

Porque si late igual, `K_wd` sigue energizado, la ruta de hardware sigue
inhibida, y la sirena queda **muda ante una alerta real** — que es exactamente
el fallo que SPOF-02 existe para impedir, reintroducido por su propia
mitigación.

EL CONTRAEJEMPLO QUE GOBIERNA EL DISEÑO
----------------------------------------
El reflejo de T-1.3 es *event-driven* y serializa TODAS sus transiciones en un
único `RLock`. Un **cuelgue parcial** —el hilo del reflejo bloqueado con el lock
tomado, los demás hilos del proceso vivos y felices— deja el reflejo muerto sin
matar el proceso. Un latido emitido desde su propio bucle no se enteraría:
seguiría latiendo sobre un gabinete que ya no puede sonar.

`test_el_latido_CESA_con_el_lock_del_reflejo_tomado` es ese contraejemplo, y es
el test que un latido ingenuo no pasa. Todo lo demás de este archivo son sus
guardas.

LA DIRECCIÓN DEL FALLO
----------------------
Ante CUALQUIER duda el latido calla, y callar **habilita** la ruta de hardware.
El modo de fallo es «el WR-1 puede sonar la sirena por sí mismo», nunca «nadie
puede». Por eso los tests de fallo de este archivo asertan AUSENCIA de latido y
no una excepción: la ausencia es la conducta correcta.
"""

from __future__ import annotations

import threading
import time

import pytest
from gpiozero import Device
from takab_edge.config import EdgeSettings
from takab_edge.contracts import ActuatorChannel
from takab_edge.gpio import GpioController

#: Medio periodo del latido en los tests. Corto para que una prueba no dure
#: segundos, pero no tanto como para que el planificador la haga inestable.
SEMIPERIODO_S = 0.02

#: Cuánto se observa el pin para decidir «late» o «no late». Diez semiperiodos:
#: con margen de sobra para ver varias transiciones, y aun así ~0.2 s.
VENTANA_S = SEMIPERIODO_S * 10


@pytest.fixture
def ajustes(settings: EdgeSettings) -> EdgeSettings:
    """`settings` con el latido ENCENDIDO y rápido.

    El default de producción es apagado (el hardware de `K_wd` no existe), así
    que cada test que quiera observar el latido tiene que pedirlo — y el que
    prueba el default lo verifica contra `EdgeSettings()` a pelo.
    """
    return settings.model_copy(
        update={
            "gpio_keepalive_enabled": True,
            "gpio_keepalive_period_s": SEMIPERIODO_S,
            "gpio_keepalive_lock_timeout_s": SEMIPERIODO_S * 2,
        }
    )


def _pin_del_latido(cfg: EdgeSettings):  # noqa: ANN202 — MockPin (import perezoso)
    return Device.pin_factory.pin(cfg.pins.keepalive)


def _transiciones(cfg: EdgeSettings, ventana_s: float = VENTANA_S) -> int:
    """Cuántas veces cambió de nivel el pin del latido en `ventana_s`.

    Se mide muestreando el pin, no contando llamadas: lo que el monoestable ve
    es el NIVEL de la línea, así que es lo que hay que observar. Un latido que
    llamara a `toggle()` sin mover el pin daría 0 aquí, que es lo correcto.
    """
    pin = _pin_del_latido(cfg)
    ultimo = pin.state
    cambios = 0
    fin = time.monotonic() + ventana_s
    while time.monotonic() < fin:
        actual = pin.state
        if actual != ultimo:
            cambios += 1
            ultimo = actual
        time.sleep(SEMIPERIODO_S / 10)
    return cambios


def _esperar(predicado, timeout_s: float = 2.0) -> bool:  # noqa: ANN001
    """Espera activa acotada. Devuelve si el predicado se cumplió."""
    fin = time.monotonic() + timeout_s
    while time.monotonic() < fin:
        if predicado():
            return True
        time.sleep(SEMIPERIODO_S / 4)
    return False


@pytest.fixture
def gpio(ajustes: EdgeSettings):  # noqa: ANN201 — GpioController
    """Controlador arrancado y parado, con el latido vivo."""
    controlador = GpioController(ajustes)
    controlador.start()
    try:
        yield controlador
    finally:
        controlador.stop()


# --- La propiedad positiva: en operación normal, late -----------------------


def test_en_operacion_normal_el_pin_alterna(gpio: GpioController, ajustes: EdgeSettings) -> None:
    """La premisa de todo lo demás: sin nada roto, el latido late.

    Si este test fallara, los tests negativos de abajo pasarían por la razón
    equivocada — «no late» es trivial de conseguir no latiendo nunca.
    """
    cambios = _transiciones(ajustes)
    assert cambios >= 2, (
        f"el pin del latido cambió {cambios} veces en {VENTANA_S:.2f} s: con el "
        "gabinete sano el monoestable no vería pulsos y `K_wd` liberaría la ruta "
        "de hardware sin motivo"
    )


def test_el_contador_de_reflejo_avanza_mientras_late(gpio: GpioController) -> None:
    """El latido no es un temporizador: cada pulso acredita el camino del reflejo.

    El contador es lo que separa «el hilo del latido sigue corriendo» de «el
    camino SASMEX→relé se pudo ejecutar». Un latido que avanzara el pin sin
    avanzar el contador estaría mintiendo sobre lo único que le importa al
    monoestable.
    """
    inicial = gpio.reflex_progress
    assert _esperar(lambda: gpio.reflex_progress > inicial + 2), (
        f"el contador de reflejo no avanzó (quedó en {gpio.reflex_progress}): "
        "el latido no está sondeando el camino, solo alternando un pin"
    )


def test_el_latido_es_observable_desde_fuera(gpio: GpioController) -> None:
    """Un latido que no se puede mirar no se puede diagnosticar (regla de oro 7).

    El día que la sirena no suene con el Pi vivo, la primera pregunta será si
    `K_wd` estaba energizado — y eso se contesta mirando si el gabinete cree
    estar latiendo.
    """
    assert _esperar(lambda: gpio.keepalive_beating is True), (
        "el controlador no declara estar latiendo, así que el panel no puede "
        "distinguir «Pi vivo» de «ruta de hardware habilitada»"
    )


# --- LA PROPIEDAD QUE JUSTIFICA LA FICHA -----------------------------------


def test_el_latido_CESA_con_el_lock_del_reflejo_tomado(
    gpio: GpioController, ajustes: EdgeSettings
) -> None:
    """EL CONTRAEJEMPLO. Cuelgue PARCIAL: el reflejo muere, el proceso no.

    Se toma el `RLock` del reflejo desde otro hilo y no se suelta. El proceso
    sigue vivo, sus demás hilos también, y `takab-gpio` seguiría apareciendo
    `active` en systemd. Pero **el reflejo ya no puede ejecutarse**: un flanco
    del WR-1 se quedaría esperando el lock.

    Un latido ingenuo (`while True: toggle; sleep`) seguiría latiendo aquí, y
    ése es justo el fallo: `K_wd` energizado ⇒ ruta de hardware INHIBIDA ⇒
    **sirena muda ante una alerta real**.

    Se comprueba primero que latía (para no aprobar por no haber arrancado
    nunca) y luego que dejó de latir.
    """
    assert _transiciones(ajustes) >= 2, "premisa: latía antes de bloquear el reflejo"

    gpio._lock.acquire()  # noqa: SLF001 — simular el cuelgue exige tomar ESE lock
    try:
        # Margen para que el hilo agote su espera del lock y decida no pulsar.
        time.sleep(ajustes.gpio_keepalive_lock_timeout_s * 3)
        cambios = _transiciones(ajustes)
    finally:
        gpio._lock.release()  # noqa: SLF001

    assert cambios == 0, (
        f"el pin siguió alternando {cambios} veces con el reflejo INTERBLOQUEADO. "
        "El monoestable leería «Pi vivo», `K_wd` mantendría inhibida la ruta de "
        "hardware, y la sirena quedaría MUDA ante una alerta real: el fallo que "
        "SPOF-02 existe para impedir, reintroducido por su propia mitigación"
    )


def test_el_latido_SE_REANUDA_cuando_el_reflejo_se_desbloquea(
    gpio: GpioController, ajustes: EdgeSettings
) -> None:
    """La otra mitad: cesar no puede ser un estado absorbente.

    Un latido que se rinde al primer bloqueo transitorio deja la ruta de
    hardware habilitada para siempre — y con ella una sirena que el operador ya
    no puede silenciar, que es precisamente lo que la variante B compra
    (`D-10`).
    """
    gpio._lock.acquire()  # noqa: SLF001
    try:
        time.sleep(ajustes.gpio_keepalive_lock_timeout_s * 3)
        assert _transiciones(ajustes) == 0, "premisa: cesó con el lock tomado"
    finally:
        gpio._lock.release()  # noqa: SLF001

    assert _esperar(lambda: _transiciones(ajustes) >= 2, timeout_s=3.0), (
        "el latido no volvió tras liberarse el reflejo: un bloqueo transitorio "
        "dejaría la ruta de hardware habilitada indefinidamente"
    )


def test_sin_rele_de_sirena_no_late(ajustes: EdgeSettings) -> None:
    """Sin sirena que gobernar, el Pi no puede afirmar que gobierna la sirena.

    Es el mismo criterio que el cuelgue: el latido acredita el CAMINO COMPLETO.
    Un gabinete cuyo relé de sirena no se construyó no tiene ese camino, y
    declararse vivo sería mentirle al monoestable en la dirección peligrosa.
    """
    controlador = GpioController(ajustes)
    controlador.start()
    try:
        with controlador._lock:  # noqa: SLF001
            relay = controlador._relays.pop(ActuatorChannel.SIREN)  # noqa: SLF001
            relay.close()
        time.sleep(ajustes.gpio_keepalive_lock_timeout_s * 3)
        cambios = _transiciones(ajustes)
    finally:
        controlador.stop()

    assert cambios == 0, (
        f"latió {cambios} veces sin relé de sirena construido: el monoestable "
        "leería «Pi vivo» sobre un gabinete que no puede sonar"
    )


# --- Guardas del ciclo de vida ---------------------------------------------


def test_arranca_DESHABILITADO_y_no_reclama_el_pin(settings: EdgeSettings) -> None:
    """El default de producción: apagado, y sin tocar el pin.

    El hardware de `K_wd` no existe todavía. Un pin latiendo contra nada no
    protege a nadie, y reclamarlo se lo quitaría a quien lo necesite. Se
    enciende por gabinete **al cablear**.
    """
    assert EdgeSettings().gpio_keepalive_enabled is False, (
        "el latido no puede nacer encendido: exige hardware que todavía no está montado"
    )

    controlador = GpioController(settings)
    controlador.start()
    try:
        assert controlador.keepalive_beating is False
        assert controlador._keepalive_thread is None, (  # noqa: SLF001
            "hay hilo de latido con el latido deshabilitado"
        )
        assert controlador._keepalive_device is None, (  # noqa: SLF001
            "se construyó el dispositivo del latido con el latido deshabilitado: "
            "eso RECLAMA el pin BCM y se lo quita a quien lo vaya a usar"
        )
    finally:
        controlador.stop()


def test_la_parada_no_se_interbloquea_con_el_hilo_del_latido(ajustes: EdgeSettings) -> None:
    """`stop()` toma `_lock`; el hilo del latido también. El orden importa.

    `_on_stop` ya documenta por qué la puerta de servicio se detiene FUERA del
    lock: pararla dentro JOINea hilos que esperan ese mismo lock. El latido
    tiene exactamente la misma forma, así que hereda la misma regla — y si
    alguien la olvida, esto se cuelga en vez de fallar.
    """
    controlador = GpioController(ajustes)
    controlador.start()
    assert _esperar(lambda: controlador.keepalive_beating is True), "premisa: arrancó latiendo"

    terminado = threading.Event()

    def parar() -> None:
        controlador.stop()
        terminado.set()

    hilo = threading.Thread(target=parar, daemon=True)
    hilo.start()
    assert terminado.wait(timeout=5.0), (
        "`stop()` no volvió en 5 s: el hilo del latido se está deteniendo DENTRO "
        "del `_lock` y se interbloquea con él"
    )
    assert controlador.keepalive_beating is False, "sigue declarándose latiendo tras parar"


def test_tras_parar_el_pin_deja_de_alternar(ajustes: EdgeSettings) -> None:
    """Un gabinete parado no debe seguir diciéndole al monoestable que vive.

    Es el caso del despliegue: `takab-gpio` se detiene para arrancar la versión
    nueva. Durante esa ventana el Pi NO gobierna, y la ruta de hardware debe
    quedar habilitada — que es justo lo que SPOF-02 quiere.
    """
    controlador = GpioController(ajustes)
    controlador.start()
    assert _esperar(lambda: controlador.keepalive_beating is True), "premisa: arrancó latiendo"
    controlador.stop()

    assert _transiciones(ajustes) == 0, (
        "el pin del latido siguió alternando tras `stop()`: el monoestable "
        "mantendría `K_wd` energizado con el gabinete sin gobierno"
    )
