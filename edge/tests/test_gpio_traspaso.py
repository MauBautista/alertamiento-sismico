"""[T-2.70.a · D3] EL TRASPASO: el dueño de los pines sale de `takab-edge`.

D2/P1 puso la costura, D2/P2 el transporte, y los dos dejaron el gabinete
exactamente como estaba: un proceso, una llamada directa, ni un pin movido. Aquí
se mueve la propiedad: `takab-gpio` pasa a sostener el cerrojo, los cinco relés y
los tres botones, y `takab-edge` deja de instanciar su `GpioController` para
hablarle por el socket.

**Estos tests corren en UN solo proceso Python, y eso es una limitación
DECLARADA.** El dueño es un `GpioController` construido por `run_gpio_process`
(el entry point real de `takab-gpio`) y el cliente es un `EdgeSupervisor`
completo que NO tiene controlador: entre ellos hay un socket `AF_UNIX` de
verdad, un códec de verdad y dos hilos de verdad. Lo que NO hay es una frontera
de proceso, así que lo que estos tests **no pueden medir** es lo que depende de
que sean dos PIDs: el aislamiento de memoria, el coste real del cambio de
contexto en el Pi 4 y el comportamiento de systemd. Eso es `GATE-HW`/`G-05` y no
se marca desde software (no existe un segundo Pi).

Lo que SÍ se mide aquí, criterio por criterio de la ficha:

1. `takab-edge` no instancia `GpioController` y los cinco consumidores reciben la
   costura del socket.
4. **La transición SÍ suelta los relés, y está MEDIDO.** No hay forma en software
   de que la línea conserve su nivel entre dueños — ver
   `test_cambiar_de_dueno_DESENERGIZA_gas_y_puertas` y
   `test_el_backend_de_produccion_DEVUELVE_la_linea_a_entrada_al_cerrar`. Lo que
   sí se mide y se acota es el TAMAÑO de la ventana: exactamente un ciclo
   eléctrico, el mismo que cuesta hoy cualquier despliegue, y el ÚLTIMO.
5. SPOF-02 cruza la frontera: un contacto SOSTENIDO al arrancar el dueño llega
   hasta la nube por el socket.
6. El reflejo punta a punta sigue bajo 100 ms **medido en los cinco pines** con
   el dueño fuera del supervisor.
7. Reiniciar `takab-edge` no mueve un solo pin.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

import gpiozero
import pytest
from gpiozero import Device
from takab_edge.contracts import ActuatorChannel
from takab_edge.gpio import GpioController, active_energized, normal_energized
from takab_edge.gpio.__main__ import run_gpio_process
from takab_edge.gpio_link import GpioLinkUnavailable, LocalGpioLink
from takab_edge.pinlink import IpcGpioLink
from takab_edge.supervisor import ACKS_TOPIC, EVENTS_TOPIC, EdgeSupervisor

_RELES = (
    ActuatorChannel.SIREN,
    ActuatorChannel.STROBE,
    ActuatorChannel.GAS_VALVE,
    ActuatorChannel.ELEVATOR,
    ActuatorChannel.DOOR_RETAINER,
)

#: Los dos que REPOSAN ENERGIZADOS y por tanto los que el traspaso mueve:
#: `GAS_VALVE` es FAIL_CLOSE y `DOOR_RETAINER` es NORMALLY_CLOSED.
_REPOSAN_ENERGIZADOS = (ActuatorChannel.GAS_VALVE, ActuatorChannel.DOOR_RETAINER)


def _numero_de_pin(settings, canal: ActuatorChannel) -> int:
    return {
        ActuatorChannel.SIREN: settings.pins.relay_siren,
        ActuatorChannel.STROBE: settings.pins.relay_strobe,
        ActuatorChannel.GAS_VALVE: settings.pins.relay_gas_valve,
        ActuatorChannel.ELEVATOR: settings.pins.relay_elevator,
        ActuatorChannel.DOOR_RETAINER: settings.pins.relay_door_retainer,
    }[canal]


def _pin(settings, canal: ActuatorChannel):  # noqa: ANN202 — MockPin de gpiozero
    return Device.pin_factory.pin(_numero_de_pin(settings, canal))


def _transiciones(pin) -> list[bool]:  # noqa: ANN001
    """Niveles eléctricos por los que pasó el pin, en orden (`MockPin.states`)."""
    return [estado.state for estado in pin.states]


def _esperar(condicion, timeout: float = 5.0) -> bool:  # noqa: ANN001
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        try:
            if condicion():
                return True
        except GpioLinkUnavailable:
            pass
        time.sleep(0.005)
    return False


@pytest.fixture
def cfg_separado(settings):  # noqa: ANN001, ANN201
    """La configuración de D3: el dueño de los pines vive FUERA de `takab-edge`.

    `gpio_link` se deja a propósito en su valor de fábrica (`local`): parte de lo
    que este paso tiene que demostrar es que un `edge.env` al que se le olvidó
    esa línea NO deja al supervisor con una costura que llama a un controlador
    inexistente.
    """
    return settings.model_copy(update={"gpio_owner": "gpio"})


@pytest.fixture
def dueno(cfg_separado):  # noqa: ANN001, ANN201
    """`takab-gpio`: el entry point REAL del proceso dedicado, ya de pie."""
    controlador = run_gpio_process(cfg_separado, block=False)
    try:
        yield controlador
    finally:
        controlador.stop()


@pytest.fixture
def edge_separado(cfg_separado, dueno):  # noqa: ANN001, ANN201
    """`takab-edge` SIN pines: habla con `dueno` por el socket."""
    sup = EdgeSupervisor(cfg_separado, seedlink_source=None)
    sup.start()
    try:
        yield sup
    finally:
        sup.stop()


# ---------------------------------------------------------------------------
# Criterio 1 · `takab-edge` deja de instanciar su `GpioController`
# ---------------------------------------------------------------------------


def test_el_supervisor_ya_no_instancia_su_propio_dueno_de_pines(edge_separado, dueno) -> None:  # noqa: ANN001
    """CRITERIO 1. Con el dueño fuera, `takab-edge` no tiene `GpioController`.

    Y no basta con que `self.gpio` sea `None`: lo que importa es que ningún
    consumidor tenga una vía directa a los pines. Los cinco reciben la MISMA
    costura y esa costura es la del socket.
    """
    sup = edge_separado
    assert sup.gpio is None, "el supervisor volvió a instanciar un GpioController"
    assert isinstance(sup.gpio_link, IpcGpioLink), (
        f"la costura del supervisor es {type(sup.gpio_link).__name__}: con el dueño "
        "fuera del proceso, una llamada directa no puede existir"
    )
    assert "gpio" not in sup._modules, (
        "el módulo `gpio` sigue en el supervisor: arrancarlo reclamaría el cerrojo "
        "que ya sostiene takab-gpio y tumbaría el edge (critical=True)"
    )
    for nombre, consumidor in (
        ("actuators.relay", sup.actuators._relay),
        ("audio", sup.audio),
        ("drill", sup.drill),
        ("health", sup.health),
        ("local_api", sup.local_api),
    ):
        assert consumidor._link is sup.gpio_link, f"{nombre} no recibió la costura del socket"

    # …y el dueño es el otro proceso: el cerrojo lo sostiene él, no el supervisor.
    assert dueno._lock_fd is not None
    assert dueno.running is True
    # NO-VACUIDAD: el gabinete de fábrica sigue siendo el de hoy.
    de_fabrica = EdgeSupervisor(sup.settings.model_copy(update={"gpio_owner": "edge"}))
    de_fabrica.build()
    assert isinstance(de_fabrica.gpio, GpioController)
    assert isinstance(de_fabrica.gpio_link, LocalGpioLink)
    assert "gpio" in de_fabrica._modules


def test_una_errata_en_GPIO_OWNER_deja_el_dueno_donde_estaba(settings, caplog) -> None:  # noqa: ANN001
    """La dirección del degradado, y por qué es ésta y no la contraria.

    Con `gpio_owner` ilegible hay dos salidas y sólo una es tolerable:

    * degradar a `gpio` ⇒ si `takab-gpio` no corre, **NADIE** es dueño de los
      pines y el edificio se queda sin alertamiento EN SILENCIO;
    * degradar a `edge` ⇒ el supervisor reclama el cerrojo. Si `takab-gpio` ya lo
      tiene, el arranque truena RUIDOSO (`gpio` es `critical=True`) sin tocar un
      pin — D1.1 — y el edificio sigue protegido por quien ya lo protegía.
    """
    raro = settings.model_copy(update={"gpio_owner": "takab-gpio.service"})
    assert raro.edge_owns_pins is True
    with caplog.at_level(logging.ERROR, logger="takab_edge.supervisor"):
        sup = EdgeSupervisor(raro, seedlink_source=None)
        sup.build()
    assert isinstance(sup.gpio, GpioController)
    assert "takab-gpio.service" in caplog.text, "la errata se degradó EN SILENCIO"


def _criticos(caplog) -> list[str]:  # noqa: ANN001
    """CRITICALs del SUPERVISOR, no de todo el proceso.

    `health` también grita en CRITICAL cuando no puede leer los relés, y su
    texto es suyo (contrato del latido, deuda 1 de D2/P1). Mezclarlos haría que
    estos tests aprobaran o suspendieran por un mensaje de otro módulo.
    """
    return [
        r.message
        for r in caplog.records
        if r.levelno >= logging.CRITICAL and r.name == "takab_edge.supervisor"
    ]


def test_un_edge_sin_nadie_al_otro_lado_lo_declara_CRITICO(cfg_separado, caplog) -> None:  # noqa: ANN001
    """El peor estado alcanzable de D3, y tiene que ser RUIDOSO.

    `gpio_owner=gpio` con `takab-gpio` caído = **nadie** gobierna la sirena, el
    gas ni las puertas. El supervisor no puede arreglarlo (tomar los pines él
    revertiría la topología en silencio y bloquearía el arranque del dueño de
    verdad, que es quien tiene `Restart=always` y cero dependencias pesadas),
    pero no puede callarlo.
    """
    sup = EdgeSupervisor(cfg_separado, seedlink_source=None)
    with caplog.at_level(logging.CRITICAL, logger="takab_edge.supervisor"):
        sup.start()
    try:
        assert sup.gpio is None
        assert any("dueño de los pines" in mensaje for mensaje in _criticos(caplog)), (
            "el gabinete arrancó sin NADIE sosteniendo los pines y no lo dijo en "
            f"CRITICAL. Registros vistos: {[r.message[:60] for r in caplog.records]}"
        )
        # …y ESTE es el caso en que la remediación `GPIO_OWNER=edge` es correcta:
        # no hay nadie con el cerrojo, así que el supervisor puede tomarlo.
        # (En el caso de al lado —dueño de pie, puerta cerrada— sería un bucle
        # infinito contra el cerrojo; por eso los dos mensajes no pueden ser uno.)
        assert any("NADIE" in mensaje for mensaje in _criticos(caplog))
        assert any("TAKAB_EDGE_GPIO_OWNER=edge" in mensaje for mensaje in _criticos(caplog))
    finally:
        sup.stop()


def test_un_dueno_DE_PIE_con_la_puerta_CERRADA_no_se_reporta_como_gabinete_sin_proteccion(  # noqa: ANN201
    settings,  # noqa: ANN001
    caplog,  # noqa: ANN001
    tmp_path,  # noqa: ANN001
) -> None:
    """[T-2.70.a·D3·m2] El `log.critical` que MENTÍA, y que empujaba a hacer daño.

    Escenario medido: `takab-gpio` de pie y protegiendo —sirena sonando, gas y
    retenedores energizados— con un `gpio_socket_path` que `AF_UNIX` no puede
    atar (la ruta pasa de los 108 bytes de `sun_path`). La puerta de servicio no
    se abre; el cliente no puede hablar; `snapshot()` lanza. Y el supervisor
    gritaba *«el gabinete no tiene sirena, ni cierre de gas, ni retorno de
    ascensores, ni retenedores»* sobre un gabinete que SÍ protege.

    Lo caro no es la imprecisión, son los dos remedios que ofrecía:
      · `TAKAB_EDGE_GPIO_OWNER=edge` deja a `takab-edge` reclamando un cerrojo
        que otro proceso sostiene: crash-loop contra el cerrojo PARA SIEMPRE
        (ruidoso, eléctricamente mudo… y sin nube, sin SeedLink y sin panel);
      · y el movimiento natural que sigue —`systemctl stop takab-gpio` para
        «liberar» los pines— SÍ es una actuación física sobre gas y puertas.
    Un mensaje de alarma que induce a provocar el daño que denuncia.

    Distinguir «no contesta» de «no hay dueño» no necesita nada nuevo:
    `deploy.sh` ya interroga el registro del cerrojo (pid + unidad) y comprueba
    `/proc`. El supervisor puede saberlo igual — y sin tomar el `flock`, que es
    lo único que no puede hacer: interrogarlo exige tomarlo, y en esa ventana el
    arranque legítimo de `takab-gpio` fracasaría.
    """
    # Ruta imposible para AF_UNIX (sun_path tiene 108 bytes contando el NUL).
    inatable = tmp_path / ("d" * 100) / "gpio.sock"
    assert len(str(inatable).encode()) > 108, "premisa: la ruta no cabe en sun_path"
    cfg = settings.model_copy(update={"gpio_owner": "gpio", "gpio_socket_path": str(inatable)})

    dueno = run_gpio_process(cfg, block=False)
    try:
        assert dueno.servidor_de_pines is None, (
            "premisa: la puerta de servicio NO se pudo atar (si se ató, la ruta "
            "dejó de ser imposible y este test no mide nada)"
        )
        # LA PREMISA QUE EL MENSAJE NEGABA: el gabinete PROTEGE.
        Device.pin_factory.pin(cfg.pins.wr1_contact).drive_low()
        assert dueno.siren_sounding is True
        for canal in _REPOSAN_ENERGIZADOS:
            assert dueno.relay_state(canal).energized is True, (
                f"premisa: {canal.value} está energizado y por tanto protegido"
            )

        sup = EdgeSupervisor(cfg, seedlink_source=None)
        with caplog.at_level(logging.CRITICAL, logger="takab_edge.supervisor"):
            sup.start()
        try:
            mensajes = _criticos(caplog)
            assert mensajes, (
                "el enlace con el dueño está roto y el supervisor no dijo nada: "
                "el panel queda en S/D y el latido sin relés sin que nadie sepa "
                "por qué"
            )
            texto = "\n".join(mensajes)
            assert "no tiene sirena" not in texto, (
                "sigue declarando que el gabinete no tiene sirena, gas ni "
                f"retenedores mientras los tiene y están energizados:\n{texto}"
            )
            assert "TAKAB_EDGE_GPIO_OWNER=edge" not in texto, (
                "ofrece devolver el dueño a este proceso con el cerrojo TOMADO "
                "por otro: eso es un crash-loop contra el cerrojo, para siempre"
            )
            assert "stop takab-gpio" not in texto, (
                "empuja a detener al dueño, que es actuación física sobre gas y "
                "retenedores — el daño que el propio mensaje denuncia"
            )
            # Y dice la verdad: hay dueño, con nombre, y lo que falta es la puerta.
            assert "DE PIE" in texto or "sí protege" in texto.lower(), (
                f"no distingue «no contesta» de «no hay dueño»:\n{texto}"
            )
            assert str(os.getpid()) in texto, (
                "y tiene que nombrar al proceso que los tiene: en este test el "
                "dueño corre en este mismo PID (limitación declarada del archivo)"
            )
            assert str(cfg.gpio_lock_file) in texto, (
                "el diagnóstico tiene que nombrar el cerrojo del que sale la "
                f"prueba de que hay dueño:\n{texto}"
            )
        finally:
            sup.stop()
    finally:
        dueno.stop()


def test_los_dos_servicios_a_la_vez_no_mueven_un_solo_pin(settings, monkeypatch) -> None:  # noqa: ANN001
    """Lo que reemplaza al `Conflicts=` retirado, medido POR LOS PINES.

    Retirar la exclusión mutua deja alcanzable un estado que antes systemd hacía
    imposible: las dos unidades habilitadas a la vez. El caso realista es un
    `edge.env` que se olvidó de `TAKAB_EDGE_GPIO_OWNER=gpio`, y entonces los dos
    procesos se creen dueños. Ese estado tiene que ser RUIDOSO Y ELÉCTRICAMENTE
    MUDO en las dos direcciones: un crash-loop caro en el journal y gratis en el
    edificio.

    [T-2.70.a·D3·m1] LA ATRIBUCIÓN, CORREGIDA. Este docstring decía que las 0
    transiciones se deben a que «el `flock` truena antes de la pin factory». **El
    0 es real; esa atribución no la medía nadie**, y la auditoría la refutó
    desactivando el cerrojo entero: siguen siendo 0. En UN SOLO PROCESO quien
    para al segundo es gpiozero, cuya `pin_factory` se niega a entregar dos veces
    el mismo pin BCM (`GPIOPinInUse`) — y eso ocurre igual sin cerrojo.

    Lo que sí distingue a las dos causas, y es lo que se mide abajo, es DÓNDE
    muere el segundo: con el cerrojo no llega ni a pedir la pin factory (0
    llamadas ⇒ ni siquiera se abre el gpiochip); con `GPIOPinInUse` la factory ya
    está instanciada y el fallo aparece a mitad de la construcción de los relés,
    que es la ruta donde un canal anterior ya pudo quedar energizado (el punto 4
    de la auditoría de D1).

    Lo que este archivo **no puede** medir sigue siendo lo de siempre: con DOS
    PIDs no hay una `pin_factory` compartida, así que ahí el que rechazaría es el
    kernel (EBUSY al reclamar la línea) y ya con el gpiochip abierto. Que también
    salgan 0 transiciones con dos procesos de verdad es `GATE-HW`/`G-05`.
    """
    pines = {canal: _pin(settings, canal) for canal in _REPOSAN_ENERGIZADOS}

    # Espía de la pin factory: es lo que separa «lo paró el cerrojo» de «lo paró
    # gpiozero». `_on_start` la pide en `_arrancar_hardware`, DESPUÉS del flock.
    import takab_edge.gpio as modulo_gpio

    pedidos_de_factory: list[str] = []
    for nombre in ("ensure_dev_pin_factory", "ensure_prod_pin_factory"):
        real = getattr(modulo_gpio, nombre)

        def _espia(*args, _real=real, _nombre=nombre):  # noqa: ANN002, ANN202
            pedidos_de_factory.append(_nombre)
            return _real(*args)

        monkeypatch.setattr(modulo_gpio, nombre, _espia)

    # (i) el dueño dedicado llega segundo.
    edge = EdgeSupervisor(settings.model_copy(update={"gpio_owner": "edge"}), seedlink_source=None)
    edge.start()
    try:
        historial = {canal: len(_transiciones(pin)) for canal, pin in pines.items()}
        pedidos_de_factory.clear()
        for _ in range(3):  # tres vueltas del `Restart=always` de takab-gpio
            with pytest.raises(Exception, match="ya tienen dueño"):
                run_gpio_process(settings.model_copy(update={"gpio_owner": "gpio"}), block=False)
        for canal, pin in pines.items():
            assert len(_transiciones(pin)) == historial[canal], (
                f"{canal.value}: el crash-loop de `takab-gpio` contra un cerrojo ya "
                "tomado movió el pin. Con las dos unidades habilitadas eso sería "
                "ciclado físico indefinido sobre gas y puertas."
            )
        assert pedidos_de_factory == [], (
            "el segundo reclamante llegó a pedir la pin factory "
            f"({pedidos_de_factory}): entonces el cerrojo NO es lo que lo paró y "
            "el gpiochip se abrió antes de descubrir que estos pines son de otro"
        )
    finally:
        edge.stop()

    # (ii) …y al revés: el supervisor llega segundo (errata de `gpio_owner`).
    dedicado = run_gpio_process(settings.model_copy(update={"gpio_owner": "gpio"}), block=False)
    try:
        historial = {canal: len(_transiciones(pin)) for canal, pin in pines.items()}
        pedidos_de_factory.clear()
        for _ in range(3):
            tarde = EdgeSupervisor(
                settings.model_copy(update={"gpio_owner": "edge"}), seedlink_source=None
            )
            with pytest.raises(Exception, match="ya tienen dueño"):
                tarde.start()
            tarde.stop()
        for canal, pin in pines.items():
            assert len(_transiciones(pin)) == historial[canal], (
                f"{canal.value}: el crash-loop de `takab-edge` contra el cerrojo del "
                "dueño dedicado movió el pin"
            )
        assert pedidos_de_factory == [], (
            f"el supervisor tardío pidió la pin factory ({pedidos_de_factory}) "
            "pese a que los pines ya tenían dueño"
        )
        # …y el dueño de verdad siguió protegiendo todo el rato.
        assert dedicado.running is True
        assert all(pin.state is True for pin in pines.values())
    finally:
        dedicado.stop()


# ---------------------------------------------------------------------------
# Criterio 4 · LA MEDICIÓN: qué le pasa de verdad a gas y puertas al traspasar
# ---------------------------------------------------------------------------


def test_el_backend_de_produccion_DEVUELVE_la_linea_a_entrada_al_cerrar() -> None:
    """CRITERIO 4, la mitad que decide el veredicto: **no hay «keep state»**.

    Se lee del CÓDIGO INSTALADO, no de memoria. `gpiozero.pins.lgpio.LGPIOPin.
    close()` —el backend de producción del Pi, el que fija
    `ensure_prod_pin_factory`— no hace «soltar y ya»: **re-reclama la línea como
    ENTRADA con el bias deshabilitado** (`gpio_claim_input(..., SET_PULL_NONE)`).
    O sea que el nivel no se conserva ni por accidente: se pone en alta
    impedancia explícitamente, y el relé se desenergiza.

    Y no es una peculiaridad de gpiozero que se pueda esquivar bajando de capa:
    el uAPI v2 del kernel (`/usr/include/linux/gpio.h`, verificado en esta
    máquina) declara TRECE `GPIO_V2_LINE_FLAG_*` —USED, ACTIVE_LOW, INPUT,
    OUTPUT, EDGE_*, OPEN_DRAIN, OPEN_SOURCE, BIAS_*, EVENT_CLOCK_*— y **ninguna
    conserva el nivel al liberar la línea**. Ese archivo no se asierta aquí
    porque no existe en toda máquina de CI; lo que sí existe siempre es el
    backend que este repo declara como dependencia, y es el que se mide.

    La única vía que el kernel dejaría abierta —pasar el descriptor de la
    petición de línea por `SCM_RIGHTS` para que la línea nunca se libere— exige
    reimplementar el cdev a mano dentro del proceso mínimo del camino de vida
    (regla de oro 4) y tener DOS procesos sosteniendo la misma línea a la vez,
    que es justo lo que el cerrojo de D1.1 existe para impedir. No se hace.
    """
    fuente = (Path(gpiozero.__file__).parent / "pins" / "lgpio.py").read_text(encoding="utf-8")
    # Se acota a la clase del PIN: `LGPIOFactory` tiene su propio `close()` (que
    # además cierra el gpiochip entero, o sea que tampoco conserva nada) y un
    # `re.search` sobre el archivo se quedaba con ese.
    _, _, clase_pin = fuente.partition("class LGPIOPin(")
    assert clase_pin, "el gpiozero instalado ya no define `LGPIOPin`: re-mide el traspaso"
    cuerpo = re.search(r"\n    def close\(self\):\n(.*?)\n    def ", clase_pin, re.DOTALL)
    assert cuerpo is not None, (
        "no se encontró `LGPIOPin.close` en el gpiozero instalado: el veredicto de "
        "este test dejaría de estar respaldado por el backend real"
    )
    texto = cuerpo.group(1)
    assert "gpio_claim_input" in texto, (
        "`LGPIOPin.close()` cambió y ya no re-reclama la línea como ENTRADA: "
        f"vuelve a leer si el nivel se conserva entre dueños.\n{texto}"
    )
    assert "SET_PULL_NONE" in texto, (
        "`LGPIOPin.close()` ya no deshabilita el bias al cerrar; el nivel de reposo "
        f"de la línea liberada cambió y hay que re-medir el traspaso.\n{texto}"
    )


def test_cambiar_de_dueno_DESENERGIZA_gas_y_puertas(settings) -> None:  # noqa: ANN001
    """CRITERIO 4, MEDIDO — y el resultado es que la ventana EXISTE.

    Secuencia real del traspaso en un gabinete cableado, con el historial
    eléctrico completo de los dos pines que reposan energizados:

        (1) `takab-edge` dueño          → gas y retenedores ENERGIZADOS
        (2) `systemctl stop takab-edge` → **se sueltan** (ventana ABIERTA)
        (3) `systemctl start takab-gpio`→ vuelven a energizarse (ventana CERRADA)
        (4) `systemctl start takab-edge`→ **cero** transiciones

    Son DOS transiciones por pin, o sea **exactamente un ciclo eléctrico**: ni
    más ni menos que el que cuesta hoy cualquier `deploy.sh`
    (`test_cada_ciclo_de_proceso_es_un_ciclo_fisico_de_gas_y_puertas` mide 2 por
    ciclo de proceso). La diferencia es que éste es el ÚLTIMO: a partir del paso
    (4), reiniciar `takab-edge` cuesta cero — que es el criterio 7.

    Y la ventana tiene DOS causas, no una, las dos deliberadas:
      · `_apagar_hardware_locked()` ORDENA el estado seguro (`drive_all_safe()`)
        antes de cerrar. Quitarlo no cerraría la ventana y rompería SPOF-07.
      · cerrar el `DigitalOutputDevice` devuelve la línea a entrada — ver
        `test_el_backend_de_produccion_DEVUELVE_la_linea_a_entrada_al_cerrar`.

    **Conclusión que este test deja anclada: no existe respuesta en software.**
    Cerrar la ventana exige hardware (enclavamiento del relé, o un pull-up en la
    entrada del driver que sostenga la bobina con la línea liberada — decisión
    que cambia SPOF-07 y no se toma desde aquí) o una ventana de mantenimiento
    con el edificio avisado. `GATE-HW`.
    """
    pines = {canal: _pin(settings, canal) for canal in _REPOSAN_ENERGIZADOS}
    for canal, pin in pines.items():
        assert pin.state is False, f"premisa: {canal.value} arranca de-energizado"

    # (1) Hoy: el supervisor de 16 módulos es el dueño.
    hoy = EdgeSupervisor(settings.model_copy(update={"gpio_owner": "edge"}), seedlink_source=None)
    hoy.start()
    for canal, pin in pines.items():
        assert pin.state is True, f"{canal.value} debería reposar ENERGIZADO con el dueño de hoy"

    # (2) El traspaso empieza parando al dueño viejo.
    hoy.stop()
    soltados = {canal: pin.state for canal, pin in pines.items()}
    assert not any(soltados.values()), (
        "el traspaso NO soltó gas ni retenedores; si esto pasa a ser cierto, hay "
        f"que re-medir toda la conclusión del criterio 4: {soltados}"
    )

    # (3) …y termina cuando el dueño nuevo los reclama.
    separado = settings.model_copy(update={"gpio_owner": "gpio"})
    nuevo = run_gpio_process(separado, block=False)
    try:
        for canal, pin in pines.items():
            assert pin.state is True, f"{canal.value} no volvió a su reposo con el dueño nuevo"

        # (4) Y el edge vuelve SIN tocar un pin.
        antes = {canal: len(_transiciones(pin)) for canal, pin in pines.items()}
        edge = EdgeSupervisor(separado, seedlink_source=None)
        edge.start()
        try:
            assert _esperar(lambda: edge.gpio_link.snapshot().running is True), (
                "el edge separado no llegó a leer al dueño de los pines"
            )
        finally:
            edge.stop()
        for canal, pin in pines.items():
            assert len(_transiciones(pin)) == antes[canal], (
                f"{canal.value}: arrancar y parar `takab-edge` movió el pin con el "
                "dueño fuera; el criterio 7 no se cumple"
            )
    finally:
        nuevo.stop()

    for canal, pin in pines.items():
        # [False inicial] + [True al arrancar edge, False al pararlo]
        #                 + [True al arrancar gpio, False al pararlo]
        assert _transiciones(pin) == [False, True, False, True, False], (
            f"{canal.value}: el traspaso costó {_transiciones(pin)}. Se esperaban DOS "
            "transiciones (un ciclo) atribuibles al cambio de dueño; más ciclos "
            "significan que el traspaso mueve el edificio más de una vez"
        )


# ---------------------------------------------------------------------------
# Criterio 5 · SPOF-02 con la frontera de por medio
# ---------------------------------------------------------------------------


def test_la_semilla_del_contacto_sostenido_corre_con_la_puerta_YA_abierta(settings) -> None:  # noqa: ANN001
    """El mecanismo que hace posible el criterio 5, aislado.

    `_seed_from_held_contact` es la mitad SOFTWARE del traspaso hardware→software
    de SPOF-02: tras un reinicio con el contacto latcheado no hay flanco nuevo,
    así que se lee el NIVEL. Vivía al final de `_arrancar_hardware`, o sea ANTES
    de que el servidor existiera, y con el dueño en otro proceso eso significa
    que **nadie se entera**: el reflejo suena, pero `PinLinkServer._al_sasmex`
    todavía no está registrado, no se acuña `episode_id`, y el cliente que
    conecta después recibe una instantánea con `sasmex_active=True` y
    `episode_id: None` — que `_reconciliar_episodio` descarta por diseño (sin
    identidad de episodio, sintetizar por estado abriría un incidente nuevo por
    cada instantánea, veinte por segundo).

    Resultado del defecto: sirena sonando en el edificio y CERO incidentes,
    notificaciones y push. Aquí se ancla el orden que lo cierra.
    """
    controlador = GpioController(settings.model_copy(update={"gpio_serve_enabled": True}))
    orden: list[str] = []
    real_servidor = controlador.arrancar_servidor_de_pines
    real_semilla = controlador._seed_from_held_contact

    def _servidor() -> None:
        orden.append("puerta")
        real_servidor()

    def _semilla() -> None:
        orden.append("semilla")
        real_semilla()

    controlador.arrancar_servidor_de_pines = _servidor
    controlador._seed_from_held_contact = _semilla
    controlador.start()
    try:
        assert orden == ["puerta", "semilla"], (
            f"orden de arranque {orden}: la semilla de SPOF-02 tiene que correr con "
            "la puerta de servicio YA abierta, o el episodio nace sin `episode_id` "
            "y el dueño de los pines protege sin que nadie fuera se entere"
        )
        assert controlador._lock_fd is not None, "la semilla corrió sin ser dueño"
        assert controlador._relays, "la semilla corrió sin relés construidos"
    finally:
        controlador.stop()


def test_si_la_semilla_revienta_no_queda_una_puerta_atada_sin_dueno(settings) -> None:  # noqa: ANN001
    """La ventana NUEVA que abre el orden de arriba, cerrada en el mismo sitio.

    Mover la semilla DETRÁS de la puerta crea un tramo de arranque que puede
    fallar con el socket YA ATADO. Sin cerrarlo, la ruta de rescate soltaría el
    cerrojo dejando el socket vivo: el sucesor —`Restart=always` en segundos—
    toma el cerrojo, encuentra que `_preparar_ruta` ve a «alguien VIVO» detrás de
    la ruta y se niega a robársela, así que acaba siendo dueño de los pines **con
    la puerta cerrada**. Un dueño con el que nadie puede hablar: `takab-edge` sin
    lectura de estado ni actuación posterior sobre gas, ascensor y puertas.

    Por eso el rescate cierra la puerta PRIMERO, igual que `_on_stop`.
    """
    cfg = settings.model_copy(update={"gpio_serve_enabled": True})
    ruta = Path(cfg.gpio_socket_file)
    pines = {canal: _pin(cfg, canal) for canal in _REPOSAN_ENERGIZADOS}

    controlador = GpioController(cfg)

    def _semilla_rota() -> None:
        raise RuntimeError("el contacto del WR-1 no se pudo leer")

    controlador._seed_from_held_contact = _semilla_rota
    with pytest.raises(RuntimeError, match="WR-1"):
        controlador.start()

    assert controlador.servidor_de_pines is None, "la puerta quedó atada tras el rescate"
    assert not ruta.exists(), f"el socket {ruta} sobrevivió al arranque fallido"
    assert controlador._lock_fd is None, "el cerrojo no se soltó"
    for canal, pin in pines.items():
        assert pin.state is False, f"{canal.value} quedó energizado por un proceso muerto"

    # …y el sucesor arranca ENTERO: dueño de los pines Y con la puerta abierta.
    sucesor = GpioController(cfg)
    sucesor.start()
    try:
        assert sucesor.servidor_de_pines is not None, (
            "el sucesor tomó los pines pero se quedó SIN puerta de servicio: "
            "`takab-edge` no podría leer estado ni comandar gas, ascensor ni puertas"
        )
        assert ruta.exists()
    finally:
        sucesor.stop()


def test_SPOF_02_el_contacto_SOSTENIDO_cruza_hasta_la_nube(cfg_separado, monkeypatch) -> None:  # noqa: ANN001
    """CRITERIO 5. Reinicio del Pi con alerta viva, y los procesos separados.

    El contacto del WR-1 ya está CERRADO cuando arranca `takab-gpio`: no habrá
    flanco. El dueño tiene que (a) sonar en local por su cuenta —el reflejo vive
    entero de su lado, gate #6— y (b) dejar el episodio identificado para que
    `takab-edge`, que arranca después, lo reconcile UNA vez y abra el incidente.

    **Cómo se monta el escenario, y por qué no vale bajar el pin y ya.** Dos
    trampas, la segunda ya documentada en `test_gpio.py::test_el_traspaso_hw_
    software_tras_reinicio_no_lo_gatea_el_estado_administrativo`:

    1. `Button(...)` configura `pull='up'` al construirse y la `MockFactory`
       RESETEA el nivel del pin al hacerlo, así que un `drive_low()` anterior al
       arranque se pierde;
    2. un `drive_low()` posterior SÍ dispara `when_pressed`, o sea que el flanco
       llega al software y el test mediría el reflejo normal en vez del traspaso.

    En el reinicio real el flanco ocurrió con el Pi APAGADO y nadie se lo entregó
    a nadie. Se reproduce desconectando el manejador de flanco, cerrando el
    contacto y volviéndolo a conectar —sin flanco nuevo— justo antes de que
    `_on_start` llame a la semilla.
    """
    real_hardware = GpioController._arrancar_hardware

    def _arrancar_con_el_contacto_ya_cerrado(self) -> None:  # noqa: ANN001
        real_hardware(self)
        self._button.when_pressed = None  # el flanco ocurrió con el Pi apagado
        self._button.pin.drive_low()
        assert self._button.is_pressed is True
        assert self.siren_sounding is False, (
            "el flanco llegó al software: este test estaría midiendo `when_pressed` "
            "y no el traspaso HW→software"
        )
        self._button.when_pressed = self._on_contact_closed  # sin flanco nuevo

    monkeypatch.setattr(GpioController, "_arrancar_hardware", _arrancar_con_el_contacto_ya_cerrado)

    dueno = run_gpio_process(cfg_separado, block=False)
    try:
        # (a) protección LOCAL inmediata, sin nadie escuchando todavía.
        assert dueno.sasmex_active is True, "el traspaso HW→software no sembró la alerta"
        assert dueno.siren_sounding is True
        assert dueno.servidor_de_pines is not None
        assert dueno.servidor_de_pines._episodio, (
            "el episodio SASMEX nació SIN identidad: el cliente no podrá "
            "reconciliarlo y el sismo no llegará a la nube"
        )

        # (b) el edge llega tarde a la fiesta y aun así se entera, una sola vez.
        #     El espía se pone ANTES de `start()`: la reconciliación llega en el
        #     primer empuje del dueño y con el espía puesto después el evento ya
        #     había volado (medido: el test fallaba con el episodio reconciliado
        #     en el journal).
        sup = EdgeSupervisor(cfg_separado, seedlink_source=None)
        publicados: list[str] = []
        sup.build()
        sup.cloud.publish = lambda topic, payload: publicados.append(topic)
        sup.start()
        try:
            assert _esperar(lambda: EVENTS_TOPIC in publicados), (
                "el contacto SOSTENIDO no llegó a la nube con los procesos separados: "
                "el gabinete estaría sonando y la nube sin incidente ni notificación"
            )

            # [T-2.70.a·D3·m3] Aquí había `assert _esperar(lambda: all(
            # snapshot().relays)), None`, que NO ESPERABA NADA: `all([])` es
            # `True`, así que la espera se satisfacía con CERO relés y lo único
            # que comprobaba era que `snapshot()` dejara de lanzar. El bucle de
            # abajo quedaba entonces sin garantía —si la lista viene vacía, el
            # `next(...)` revienta con StopIteration en vez de decir qué canal
            # falta— y el mensaje del assert era literalmente `None`.
            def _los_cinco_protegiendo() -> bool:
                estados = sup.gpio_link.snapshot().relays
                return len(estados) == len(_RELES) and all(e.activated for e in estados)

            assert _esperar(_los_cinco_protegiendo), (
                "los cinco relés no llegaron a proteger tras el traspaso "
                "HW→software con los procesos separados. Último estado leído por "
                f"la costura: {sup.gpio_link.snapshot().relays}"
            )
            for canal in _RELES:
                estado = next(r for r in sup.gpio_link.snapshot().relays if r.channel is canal)
                assert estado.activated is True, (
                    f"{canal.value} no acabó protegiendo tras el traspaso HW→software"
                )
            assert publicados.count(EVENTS_TOPIC) == 1, (
                f"el episodio sembrado se entregó {publicados.count(EVENTS_TOPIC)} veces: "
                "una reconexión durante un sismo no puede reabrir el incidente"
            )
        finally:
            sup.stop()
    finally:
        dueno.stop()


# ---------------------------------------------------------------------------
# Criterio 6 · el reflejo, medido en los CINCO pines, con el dueño fuera
# ---------------------------------------------------------------------------

#: Misma cota de sondeo que `test_e2e.py`: 5× el presupuesto §4.3. No es un plazo
#: que se cumpla por los pelos, es el techo tras el cual se declara que la cadena
#: NO llegó.
COTA_SONDEO_S = 0.5
COTA_ACUSES_S = 0.5


def test_el_reflejo_sigue_bajo_100ms_con_el_dueno_en_otro_proceso(edge_separado, dueno) -> None:  # noqa: ANN001
    """CRITERIO 6. <100 ms punta a punta MEDIDO EN LOS RELÉS, no afirmado.

    Misma disciplina que `test_e2e.py::test_latencia_contacto_wr1_a_los_cinco_
    reles_bajo_presupuesto`, que se re-ancló ayer pensando en este momento: el
    reloj para en el instante ELÉCTRICO de los cinco pines, no cuando una llamada
    retorna, y cede el GIL en cada vuelta para que una implementación que actúe
    desde otro hilo —o desde el otro lado de un socket, que es exactamente lo que
    pasa aquí— quede MEDIDA y no penalizada.

    La cadena que se cronometra ahora cruza la costura:

        flanco del WR-1 → `_dispatch_sasmex` (DUEÑO) → reflejo sirena+estrobo
          → `PinLinkServer._al_sasmex` → socket → hilo lector del cliente
          → hilo `pinlink-observadores` → `supervisor._on_sasmex`
          → `rules.evaluate_sasmex` → `actuators.execute_sequence`
          → `RelayActuator` → `link.apply` → socket → `apply_demands` (DUEÑO)
          → gas, ascensor y retenedores de puerta

    Sólo los dos primeros pasos son el reflejo del gate #6; todo lo demás es
    actuación POSTERIOR y es la que D3 mueve al otro lado. Si esa travesía se
    degrada, este número sube y lo dice.
    """
    from time import perf_counter, sleep

    sup = edge_separado
    s = sup.settings
    pines = {canal: _pin(s, canal) for canal in _RELES}
    for canal, pin in pines.items():
        assert pin.state is normal_energized(s.failsafe[canal]), (
            f"premisa rota: {canal.value} no arrancó en su nivel de reposo"
        )
    assert _esperar(lambda: sup.gpio_link.snapshot().running is True), (
        "premisa rota: el edge no llegó a hablar con el dueño antes de cronometrar"
    )

    def sin_proteger() -> list[str]:
        return [
            canal.value
            for canal, pin in pines.items()
            if pin.state is not active_energized(s.failsafe[canal])
        ]

    contacto = Device.pin_factory.pin(s.pins.wr1_contact)
    inicio = perf_counter()
    contacto.drive_low()
    retorno = perf_counter()
    faltan = sin_proteger()
    while faltan and perf_counter() - inicio < COTA_SONDEO_S:
        sleep(0)
        faltan = sin_proteger()
    transcurrido = perf_counter() - inicio
    despues_del_retorno = transcurrido - (retorno - inicio)

    assert not faltan, (
        f"{COTA_SONDEO_S * 1000:.0f} ms después del flanco del WR-1 estos canales "
        f"seguían SIN protección con el dueño en otro proceso: {faltan}. La cadena "
        "quedó colgada al otro lado del socket."
    )
    assert transcurrido < 0.100, (
        f"SASMEX→los 5 canales tardó {transcurrido * 1000:.1f} ms con el dueño "
        f"separado (presupuesto §4.3: <100 ms), de los cuales "
        f"{despues_del_retorno * 1000:.1f} ms ocurrieron DESPUÉS de que "
        "`drive_low()` retornara — o sea, al otro lado de la costura."
    )
    # Guardarraíl anti-teatro: lo medido CONTIENE al reflejo in-process del dueño.
    assert dueno.last_reflex_latency_s is not None
    assert transcurrido >= dueno.last_reflex_latency_s, (
        f"punta a punta ({transcurrido * 1000:.3f} ms) salió MENOR que el reflejo "
        f"del dueño ({dueno.last_reflex_latency_s * 1000:.3f} ms)"
    )
    # …y la cadena RINDIÓ CUENTAS: cinco `ActuatorAck`. Un fire-and-forget llega a
    # los pines igual de rápido y deja a la nube sin acuse.
    assert _esperar(lambda: sup.cloud.queued_by_topic(ACKS_TOPIC) == len(pines), COTA_ACUSES_S), (
        f"los 5 pines llegaron en {transcurrido * 1000:.1f} ms pero la actuación "
        f"sólo rindió {sup.cloud.queued_by_topic(ACKS_TOPIC)} de {len(pines)} "
        "`ActuatorAck`: la travesía del socket se comió la rendición de cuentas"
    )


def test_el_reflejo_NO_cruza_el_socket_aunque_el_dueno_este_separado(edge_separado, dueno) -> None:  # noqa: ANN001
    """El invariante del gate #6, re-medido en la topología nueva.

    El reflejo SASMEX→sirena vive ENTERO dentro del dueño, así que su latencia no
    puede depender de que haya cliente, ni de que el socket esté vivo. Se mide
    con `takab-edge` conectado y suscrito, que es el caso peor.
    """
    sup = edge_separado
    assert _esperar(lambda: sup.gpio_link.snapshot().running is True)
    contacto = Device.pin_factory.pin(sup.settings.pins.wr1_contact)
    contacto.drive_low()
    assert dueno.siren_sounding is True
    assert dueno.last_reflex_latency_s is not None
    assert dueno.last_reflex_latency_s < 0.010, (
        f"el reflejo in-process del dueño tardó {dueno.last_reflex_latency_s * 1000:.3f} ms "
        "con un suscriptor conectado: el transporte se metió en el camino de vida"
    )


# ---------------------------------------------------------------------------
# Criterio 7 · reiniciar `takab-edge` NO detiene la protección
# ---------------------------------------------------------------------------


def test_reiniciar_takab_edge_no_detiene_la_proteccion(cfg_separado, dueno) -> None:  # noqa: ANN001
    """CRITERIO 7 — el que desbloquea T-2.70.

    Con el dueño fuera, un despliegue (`systemctl restart takab-edge`) deja de
    ser una ventana de desprotección: los pines no se sueltan, el reflejo sigue
    de pie mientras el edge no existe, y al volver el edge se re-suscribe y ve el
    estado real.
    """
    pines = {canal: _pin(cfg_separado, canal) for canal in _RELES}
    historial = {canal: len(_transiciones(pin)) for canal, pin in pines.items()}

    sup = EdgeSupervisor(cfg_separado, seedlink_source=None)
    sup.start()
    assert _esperar(lambda: sup.gpio_link.snapshot().running is True)
    sup.stop()  # ← el despliegue

    # 1) Ni un pin se movió por el reinicio del edge.
    for canal, pin in pines.items():
        assert len(_transiciones(pin)) == historial[canal], (
            f"{canal.value}: reiniciar `takab-edge` movió el pin. La ventana de "
            "desprotección de cada despliegue sigue existiendo."
        )

    # 2) Y la protección responde CON EL EDGE CAÍDO: es el punto entero de D3.
    contacto = Device.pin_factory.pin(cfg_separado.pins.wr1_contact)
    contacto.drive_low()
    assert dueno.siren_sounding is True, (
        "con `takab-edge` detenido, un SASMEX real no hizo sonar la sirena: el "
        "reflejo dejó de vivir en el dueño"
    )
    assert _pin(cfg_separado, ActuatorChannel.SIREN).state is active_energized(
        cfg_separado.failsafe[ActuatorChannel.SIREN]
    )
    contacto.drive_high()
    dueno.reset()

    # 3) El edge vuelve y recupera la lectura del dueño sin reclamar nada.
    sup2 = EdgeSupervisor(cfg_separado, seedlink_source=None)
    sup2.start()
    try:
        assert _esperar(lambda: sup2.gpio_link.snapshot().running is True), (
            "`takab-edge` no volvió a hablar con el dueño tras reiniciarse"
        )
        assert sup2.gpio is None
        assert len(sup2.gpio_link.snapshot().relays) == len(_RELES)
    finally:
        sup2.stop()


def test_el_CRASH_LOOP_DEL_DUENO_es_la_ventana_recurrente_QUE_QUEDA(cfg_separado) -> None:  # noqa: ANN001
    """[T-2.70.a·D3·m4] LA CUARTA DIRECCIÓN, que no tenía test.

    Las otras tres están medidas: `takab-edge` reiniciándose (criterio 7: cero
    transiciones), el traspaso `edge`→`gpio` (un ciclo, el ÚLTIMO) y los dos
    procesos chocando contra el cerrojo (cero). Falta la que D3 deja como **única
    ventana recurrente**: el DUEÑO en crash-loop.

    Y es la que más importa precisamente porque D3 volvió gratis la otra. Antes,
    un crash-loop del dueño era indistinguible de un crash-loop de `takab-edge`;
    ahora `takab-edge` puede ciclar todo lo que quiera sin mover un pin, y este
    proceso —el mínimo, el del camino de vida, el que `Restart=always` reintenta
    para siempre— es el único cuyo ciclo de vida sigue moviendo el edificio.

    Medido aquí: **6 reinicios = 12 transiciones** por pin en `GAS_VALVE` y
    `DOOR_RETAINER` (2 por ciclo). Lo que acota el daño no es este test sino el
    backoff de la unidad (`RestartSteps=`/`RestartMaxDelaySec=`, anclados en
    `test_el_backoff_no_queda_ignorado_en_silencio_por_systemd` con un suelo de
    60 s de techo): con el techo de hoy, 12 ciclos/hora a régimen en vez de 3600.

    DICTAMEN SOBRE `FileDescriptorStoreMax=` + `FDSTORE=1` (evaluado, NO
    implementado). El informe de D3 lo descartó diciendo que «exigiría
    reimplementar el cdev»; eso es MEDIA VERDAD y conviene dejar la otra mitad
    escrita:

    · Lo que la corrige: el `SCM_RIGHTS` lo hace systemd. Un proceso manda su fd
      al gestor con `sd_pid_notify_with_fds(FDSTORE=1)` y lo recupera en el
      arranque siguiente; systemd 259 de esta máquina ya conoce las dos
      directivas (`FileDescriptorStoreMax=0` por defecto y
      `FileDescriptorStorePreserve=restart`). Y el fd que importaría existe: en
      la uAPI v2 del kernel, la petición de línea ES un descriptor, y mientras
      alguien lo mantenga abierto la línea sigue reclamada Y A SU NIVEL. O sea
      que, en principio, gas y retenedores NO se soltarían entre reinicios.
    · Lo que la confirma: no hay por dónde meter ese fd sin bajar de gpiozero.
      Medido en el gpiozero instalado — `LGPIOFactory.__init__(self, chip=None)`
      hace `self._handle = lgpio.gpiochip_open(chip)`: abre por NÚMERO DE CHIP y
      no acepta un descriptor. Adoptar un fd heredado exige hablar el `ioctl`
      del cdev a mano DENTRO del proceso mínimo del camino de vida, que es
      exactamente donde la regla de oro 4 pide menos código y más auditable.
    · Alcance real, y es menor de lo que suena: cubriría los reinicios de LA
      MISMA unidad (el crash-loop de arriba), no el traspaso único entre
      unidades distintas —que es el ciclo que D3 paga una vez— ni un reinicio
      del Pi. Y `FileDescriptorStorePreserve=restart` no guarda nada ante un
      `stop` de verdad, que es lo que hace `deploy.sh --ventana-de-mantenimiento`.
    · El contra que decide, y que no es de implementación: un fd retenido
      **congela el ÚLTIMO nivel sin nadie que lo gobierne**. Si el dueño muere en
      mitad de una alerta, la sirena se queda SONANDO —y no hay proceso al que
      pedirle `silence`— hasta que un sucesor adopte el fd; si el sucesor no
      llega (que es la definición de crash-loop), el edificio se queda con el
      estado de emergencia clavado y `drive_all_safe()` sin correr jamás. Hoy esa
      misma muerte devuelve las líneas a entrada y el edificio cae al fail-safe,
      que es la dirección que este proyecto eligió en todas partes.

    Conclusión: **merece ficha propia, y NO es un refinamiento de D3.** Es
    «bajar de gpiozero en el camino de vida» + «política de retención POR CANAL»
    (congelar gas y retenedores puede ser correcto; congelar la sirena no lo es)
    + acreditación en el Pi. Nada de eso se decide desde software ni cabe en
    esta ficha.
    """
    pines = {canal: _pin(cfg_separado, canal) for canal in _REPOSAN_ENERGIZADOS}
    for canal, pin in pines.items():
        assert pin.state is False, f"premisa: {canal.value} arranca de-energizado"

    ciclos = 6
    for _ in range(ciclos):  # seis vueltas del `Restart=always` de takab-gpio
        dueno = run_gpio_process(cfg_separado, block=False)
        dueno.stop()

    for canal, pin in pines.items():
        assert _transiciones(pin) == [False] + [True, False] * ciclos, (
            f"{canal.value}: {ciclos} ciclos del DUEÑO produjeron "
            f"{len(_transiciones(pin)) - 1} transiciones y se esperaban "
            f"{2 * ciclos}. Si el número cambia, cambia con él el argumento del "
            "backoff de takab-gpio.service"
        )

    # EL CONTRASTE, que es lo que hace de esto la ÚNICA ventana recurrente: con
    # un dueño estable, seis ciclos del CLIENTE no mueven nada.
    dueno = run_gpio_process(cfg_separado, block=False)
    try:
        historial = {canal: len(_transiciones(pin)) for canal, pin in pines.items()}
        for _ in range(ciclos):
            cliente = EdgeSupervisor(cfg_separado, seedlink_source=None)
            cliente.start()
            cliente.stop()
        for canal, pin in pines.items():
            assert len(_transiciones(pin)) == historial[canal], (
                f"{canal.value}: reiniciar `takab-edge` {ciclos} veces movió el "
                "pin con el dueño fuera; entonces el crash-loop del dueño NO es "
                "la única ventana que queda"
            )
    finally:
        dueno.stop()


def test_el_directorio_del_socket_queda_en_0700_aunque_ya_existiera(settings, tmp_path) -> None:  # noqa: ANN001
    """[T-2.70.a · M13 de la auditoría D1] `mkdir(mode=…)` NO toca lo preexistente.

    El aislamiento del socket del dueño se apoya en un directorio 0700, y
    `Path.mkdir(mode=0o700, exist_ok=True)` sólo aplica el modo cuando CREA. Un
    directorio que ya existiera con 0755 —lo deja un despliegue viejo, un `mkdir
    -p` a mano, un `umask` distinto— se quedaba en 0755 y nadie lo decía.

    El fallo es de defensa en profundidad, no de acceso: `SO_PEERCRED` sigue
    rechazando a cualquier uid que no sea el del dueño (o root). Pero el
    directorio es la primera de las dos capas y tiene que valer lo que dice.

    Se cierra en el DUEÑO (`GpioController.arrancar_servidor_de_pines`) y no en
    el servidor: así cubre a los dos dueños posibles —`takab-gpio` y el
    `takab-edge` de la etapa intermedia— sin tocar el transporte.
    """
    raiz = tmp_path / "pinlink-preexistente"
    raiz.mkdir(mode=0o755)
    raiz.chmod(0o755)  # explícito: el `mode=` del mkdir lo filtra el umask
    assert raiz.stat().st_mode & 0o777 == 0o755, "premisa: el directorio existe con 0755"

    cfg = settings.model_copy(
        update={"gpio_serve_enabled": True, "gpio_socket_path": str(raiz / "g.sock")}
    )
    controlador = GpioController(cfg)
    controlador.start()
    try:
        assert controlador.servidor_de_pines is not None, "la puerta no llegó a abrirse"
        assert raiz.stat().st_mode & 0o777 == 0o700, (
            f"el directorio del socket se quedó en "
            f"{raiz.stat().st_mode & 0o777:04o}: el `mode=` del `mkdir` no se impone "
            "sobre un directorio que ya existía"
        )
    finally:
        controlador.stop()


def test_el_panel_y_el_latido_siguen_diciendo_la_verdad_con_el_dueno_fuera(edge_separado) -> None:  # noqa: ANN001
    """Lo que el operador MIRA tiene que seguir midiendo al dueño de verdad.

    Sin esto, D3 podría «cumplir» dejando al panel en `S/D` permanente y al
    latido con la lista de relés vacía — que la nube no distingue de «gabinete
    apagado» (deuda 1 de D2/P1, todavía abierta en el contrato).
    """
    import json
    import urllib.request

    sup = edge_separado
    assert _esperar(lambda: sup.gpio_link.snapshot().running is True)

    _host, port = sup.local_api.address
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5) as resp:
        estado = json.loads(resp.read())
    assert estado["relays_status"]["reason"] not in ("gpio_unreachable", "gpio_error"), (
        f"el panel LAN no puede leer al dueño separado: {estado['relays_status']}"
    )
    assert len(estado["relays"]) == len(_RELES)

    latido = sup.health.snapshot("test")
    assert len(latido.relays) == len(_RELES), (
        f"el latido salió con {len(latido.relays)} relés: desde la nube eso es "
        "indistinguible de «módulo detenido»"
    )
