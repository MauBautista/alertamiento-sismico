"""[T-2.70.a · D1.1] EL CERROJO DE PROPIEDAD DE LOS PINES.

Nada impide por sí solo que DOS procesos abran los mismos pines BCM a la vez.
Hasta D3, lo único que lo evitaba era `Conflicts=takab-gpio.service` en las
unidades — una promesa de systemd que se cumplía sólo si systemd era quien
arrancaba los dos procesos y si nadie editaba esa línea. Un
`python -m takab_edge.gpio` a mano en una sesión SSH mientras `takab-edge` corre
abría dos `DigitalOutputDevice` sobre la válvula de gas, y `Conflicts=` no lo
veía siquiera.

**Y desde D3 esa promesa YA NO EXISTE**: el `Conflicts=` se retiró, porque con el
dueño de los pines en `takab-gpio` la exclusión mutua convertía cada arranque del
otro servicio en una ventana de desprotección
(`test_deploy_artifacts.py::test_las_dos_unidades_YA_NO_son_mutuamente_
excluyentes`). Lo que separa hoy a los dos procesos es EXCLUSIVAMENTE lo que
ancla este archivo.

Lo que este archivo ancla:

* **(a)** con el cerrojo ocupado, el segundo controlador LANZA y no toca UN SOLO
  PIN — `_relays` vacío, `relay_states()` vacío — y lo dice en CRITICAL con el
  PID y la unidad del dueño;
* **(b)** el cerrojo se suelta DESPUÉS de cerrar los relés, no antes: si se
  soltara primero, existiría una ventana en la que el sucesor puede abrir los
  pines que el saliente todavía sostiene;
* **(c)** el cerrojo es DEL KERNEL, no una bandera de clase de Python. Sin este
  tercer test, (a) pasaría igual con un `set()` de módulo — y una bandera de
  clase no ve al proceso de al lado, que es el único escenario que importa;
* **(d)** un `_on_start` que truena DESPUÉS de tomar el cerrojo lo SUELTA.
  `EdgeModule.start()` sólo marca `_running` si `_on_start` volvió, y `stop()`
  sale en seco si no está `_running`: sin la liberación explícita el descriptor
  quedaba colgado en un proceso TODAVÍA VIVO, y con `Restart=always` el
  reintento se auto-bloquearía para siempre;
* **(e)** el mensaje distingue un dueño **VIVO** de un registro **RANCIO**. Es
  `/proc`, y sin las dos ramas medidas por separado un «vivo» constante manda al
  operador a matar a un PID reciclado;
* **(f)** el registro (pid + unidad) es INFORMATIVO: que su E/S falle —`ENOSPC`,
  `EIO` de una SD muriéndose— no puede quitarle al gabinete la propiedad de sus
  pines, ni perderse en silencio;
* **(g)** el cerrojo es fail-closed EN EL GABINETE sin convertir dev y demo en un
  campo minado: `make edge` arranca en una máquina sin /var/lib/takab y los TRES
  gabinetes simulados de `demo/run.py` conviven en el mismo host. Estos tests
  APAGAN el fixture `cerrojo_de_pines_por_test`, porque el agujero vivía justo
  fuera de donde miraba la suite.

Por qué el cerrojo va ANTES de `ensure_*_pin_factory()`: esa función instancia
`LGPIOFactory`, que ABRE el gpiochip. Cualquier orden posterior significaría que
el intruso ya tocó el hardware antes de enterarse de que no le tocaba.
"""

from __future__ import annotations

import errno
import fcntl
import logging
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from takab_edge.config import load_settings
from takab_edge.contracts import ActuatorChannel
from takab_edge.gpio import LOCAL_RELAY_CHANNELS, GpioController, GpioOwnershipError

#: La variable con la que `tests/conftest.py` le da a CADA test su propio
#: gabinete. Los tests de la sección B1 la quitan a propósito.
_ENV_CERROJO = "TAKAB_EDGE_GPIO_LOCK_PATH"


def _pines_de_los_reles(settings) -> dict[ActuatorChannel, object]:  # noqa: ANN001 — EdgeSettings
    """Los pines REALES (MockFactory) de los cinco relés, por canal.

    Derivado de `LOCAL_RELAY_CHANNELS` y del perfil de pines: un sexto relé
    mañana entra aquí solo, sin que nadie recuerde ampliar una lista.
    """
    from gpiozero import Device

    return {
        canal: Device.pin_factory.pin(getattr(settings.pins, f"relay_{canal.value}"))
        for canal in LOCAL_RELAY_CHANNELS
    }


def _pid_que_no_puede_existir() -> int:
    """Un PID que el kernel NO ha podido asignar jamás.

    `999999` (lo que había aquí) NO es imposible: `/proc/sys/kernel/pid_max`
    vale 4194304 en cualquier kernel de 64 bits reciente, así que ese PID puede
    ser el de un proceso VIVO y el test mediría lo contrario de lo que dice.
    `pid_max` es exclusivo: ningún PID lo alcanza, y `pid_max + 1` menos.
    """
    try:
        tope = int(Path("/proc/sys/kernel/pid_max").read_text())
    except (OSError, ValueError):  # pragma: no cover — Linux siempre lo expone
        tope = 4_194_304
    return tope + 1


def _tomar_cerrojo_en_otro_proceso(ruta: Path) -> subprocess.Popen:
    """Proceso hijo que sostiene el `flock` de `ruta` hasta que se le mate.

    Escribe `listo` en stdout cuando ya lo tiene, para que el test no compita.
    """
    codigo = textwrap.dedent(
        """
        import fcntl, os, sys, time
        fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.ftruncate(fd, 0)
        os.pwrite(fd, f"pid={os.getpid()}\\nunit=intruso-de-prueba\\n".encode(), 0)
        sys.stdout.write("listo\\n")
        sys.stdout.flush()
        time.sleep(120)
        """
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", codigo, str(ruta)],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "listo", "el hijo no logró el cerrojo"
    return proc


def _cerrojo_libre(ruta: Path) -> bool:
    """¿Puede OTRO PROCESO tomar el `flock` de `ruta` ahora mismo?

    En subproceso a propósito: preguntarlo desde este mismo intérprete mediría
    algo distinto en cuanto el cerrojo dejara de ser del kernel.
    """
    codigo = textwrap.dedent(
        """
        import fcntl, os, sys
        fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.stdout.write("OCUPADO")
        else:
            sys.stdout.write("LIBRE")
        """
    )
    salida = subprocess.run(
        [sys.executable, "-c", codigo, str(ruta)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert salida.stdout in ("LIBRE", "OCUPADO"), salida.stderr
    return salida.stdout == "LIBRE"


# --------------------------------------------------------------------- (a)


def test_un_segundo_dueno_no_toca_un_solo_pin_y_lo_grita(settings, caplog) -> None:
    """(a) El cerrojo ocupado ⇒ el intruso truena ANTES del primer pin.

    Las dos aserciones que hacen que esto no sea decorativo: `_relays` vacío y
    `relay_states()` vacío. Si el cerrojo se tomara DESPUÉS de construir los
    relés, ambas tendrían 5 elementos y la válvula de gas ya habría cambiado de
    nivel — el daño que este mecanismo existe para no hacer.
    """
    dueno = GpioController(settings)
    dueno.start()
    try:
        intruso = GpioController(settings)
        with caplog.at_level(logging.CRITICAL, logger="takab_edge.gpio"):
            with pytest.raises(GpioOwnershipError) as excinfo:
                intruso.start()

        assert intruso._relays == {}, (
            "el intruso construyó relés: el cerrojo se está tomando DESPUÉS de "
            "abrir los pines, que es justo lo que no puede pasar"
        )
        assert intruso.relay_states() == []
        assert intruso.running is False

        criticos = [r for r in caplog.records if r.levelno >= logging.CRITICAL]
        assert criticos, "un intruso sobre los pines del camino de vida no puede ser un WARNING"
        texto = "\n".join(r.getMessage() for r in criticos)
        assert str(os.getpid()) in texto, "el CRITICAL debe nombrar el PID del dueño"
        assert "takab" in texto or "pytest" in texto, "el CRITICAL debe nombrar la unidad del dueño"
        assert str(settings.gpio_lock_file) in str(excinfo.value)
    finally:
        dueno.stop()


def test_el_dueno_recupera_los_pines_cuando_el_anterior_para(settings) -> None:
    """No-vacuidad de (a): el cerrojo no es un «siempre truena».

    Sin esto, un `_on_start` que lanzara SIEMPRE pasaría el test de arriba.
    """
    primero = GpioController(settings)
    primero.start()
    primero.stop()

    segundo = GpioController(settings)
    segundo.start()  # no truena: el cerrojo quedó libre
    try:
        assert len(segundo.relay_states()) == len(segundo._relays) == 5
    finally:
        segundo.stop()


# --------------------------------------------------------------------- (b)


class _ControladorEspia(GpioController):
    """Anota, EN EL INSTANTE DE SOLTAR EL CERROJO, si los relés ya estaban cerrados."""

    def __init__(self, settings) -> None:  # noqa: ANN001 — EdgeSettings
        super().__init__(settings)
        self.relays_capturados: list = []
        self.cerrados_al_soltar: list[bool] | None = None
        self.liberaciones = 0

    def _on_start(self) -> None:
        super()._on_start()
        # Los objetos, no el dict: `_on_stop` lo VACÍA antes del `finally`.
        self.relays_capturados = list(self._relays.values())

    def _release_pin_ownership(self) -> None:
        # LA PRIMERA liberación, no la última. `_release_pin_ownership` es
        # IDEMPOTENTE (segunda llamada = `return` con `_lock_fd is None`), así
        # que sobrescribir en cada llamada dejaba la aserción apoyada en una
        # invocación que ya no suelta nada: con el cerrojo soltado ANTES de
        # `close()` —el defecto que este test existe para cazar— la segunda
        # llamada sí vería los relés cerrados y el test seguiría verde.
        self.liberaciones += 1
        if self.liberaciones == 1 and self.relays_capturados:
            self.cerrados_al_soltar = [bool(r.closed) for r in self.relays_capturados]
        super()._release_pin_ownership()


def test_el_cerrojo_se_suelta_DESPUES_de_cerrar_los_reles(settings) -> None:
    """(b) EL ORDEN. Soltar el cerrojo antes de `close()` abre una ventana en la
    que el proceso entrante puede reclamar unos pines que el saliente todavía
    tiene abiertos — dos dueños simultáneos sobre la válvula de gas, que es
    exactamente lo que el cerrojo existe para impedir.
    """
    controlador = _ControladorEspia(settings)
    controlador.start()
    assert controlador.relays_capturados, "premisa: el arranque construyó relés"
    assert not any(r.closed for r in controlador.relays_capturados)

    controlador.stop()

    assert controlador.liberaciones >= 1, "no se soltó el cerrojo en la parada"
    assert controlador.cerrados_al_soltar is not None, "no se soltó el cerrojo en la parada"
    assert all(controlador.cerrados_al_soltar), (
        "el cerrojo se soltó con relés TODAVÍA ABIERTOS: en ese instante otro "
        "proceso puede reclamar los pines que éste sigue sosteniendo"
    )


# --------------------------------------------------------------------- (c)


def test_el_cerrojo_lo_sostiene_el_KERNEL_y_no_una_bandera_de_clase(settings) -> None:
    """(c) EL TEST QUE IMPIDE EL TEATRO.

    Un `set()` de módulo con los paths ya reclamados haría pasar (a) y (b) y
    NO PROTEGERÍA NADA: el escenario real es un segundo PROCESO —un
    `python -m takab_edge.gpio` a mano por SSH, o `takab-gpio.service` desde que
    D3 retiró el `Conflicts=`— y una variable de Python no cruza la frontera del
    proceso. Aquí el veredicto lo da el kernel, desde fuera.

    Las dos mitades importan: ocupado mientras el dueño vive (o el cerrojo no
    sirve) y LIBRE cuando para (o sería un cerrojo que nadie puede heredar, y el
    gabinete no volvería a arrancar tras un reinicio del proceso).
    """
    ruta = Path(settings.gpio_lock_file)
    assert _cerrojo_libre(ruta), "premisa: nadie sostiene el cerrojo antes de arrancar"

    dueno = GpioController(settings)
    dueno.start()
    try:
        assert not _cerrojo_libre(ruta), (
            "OTRO PROCESO pudo tomar el cerrojo mientras el dueño corre: lo que "
            "protege los pines no es del kernel — una bandera de Python no ve al "
            "proceso de al lado"
        )
    finally:
        dueno.stop()

    assert _cerrojo_libre(ruta), "el cerrojo no se liberó al parar: nadie podría sucederle"


def test_un_proceso_ajeno_con_el_cerrojo_bloquea_a_este_gabinete(settings) -> None:
    """(c, la simétrica) El dueño puede ser un proceso que este intérprete no
    controla — que es el caso real: `takab-gpio.service` frente a `takab-edge`.
    """
    ruta = Path(settings.gpio_lock_file)
    ajeno = _tomar_cerrojo_en_otro_proceso(ruta)
    try:
        controlador = GpioController(settings)
        with pytest.raises(GpioOwnershipError) as excinfo:
            controlador.start()
        assert str(ajeno.pid) in str(excinfo.value), "el error debe nombrar al PID que manda"
        assert "intruso-de-prueba" in str(excinfo.value), "…y la unidad que dejó escrita"
        assert controlador._relays == {}
    finally:
        ajeno.kill()
        ajeno.wait(timeout=30)


def test_un_registro_rancio_no_bloquea_el_arranque(settings, caplog) -> None:
    """El registro sobrevive al proceso que lo escribió (un SIGKILL no lo borra).

    Quien manda es el `flock`, no el texto: con el registro apuntando a un PID
    que no existe y NADIE sosteniendo el cerrojo, el gabinete arranca y reescribe
    el registro a su nombre.
    """
    ruta = Path(settings.gpio_lock_file)
    ruta.write_text(f"pid={_pid_que_no_puede_existir()}\nunit=takab-gpio\n")

    dueno = GpioController(settings)
    with caplog.at_level(logging.WARNING, logger="takab_edge.gpio"):
        dueno.start()  # el registro rancio NO bloquea: nadie sostiene el flock
    try:
        assert len(dueno._relays) == 5
        # Y el registro quedó reescrito con el dueño de verdad.
        assert f"pid={os.getpid()}" in ruta.read_text()
    finally:
        dueno.stop()


def test_el_mensaje_distingue_un_dueno_VIVO_de_un_registro_RANCIO(settings) -> None:
    """[B3] EL ANCLA DE `_proceso_vivo`: las DOS ramas, medidas por separado.

    La aserción que decía cubrir esto era `assert "vivo" in str(...).lower()`, y
    pasa en las dos ramas — la rama rancia también dice «…pero el cerrojo lo
    sostiene alguien VIVO». O sea que invertir el condicional, o simplificar
    `_describir_dueno` a un «vivo» constante, dejaba la suite entera en verde
    (gate #3 incluido) mientras el gabinete le dice al operador *«takab-gpio
    (pid 4711, vivo) sostiene el cerrojo»* con 4711 muerto por SIGKILL y el
    número ya reciclado por otro programa. El operador va y mata a un inocente:
    esa es la razón por la que `/proc` se consulta, escrita en el propio código.

    El escenario rancio es REAL y no de laboratorio: el `flock` es del kernel y
    muere con el proceso, pero el TEXTO del registro no — y escribirlo no exige
    tener el cerrojo (`flock` es advisory), que es justo lo que pasa cuando el
    dueño murió por SIGKILL y otro proceso tomó el relevo del archivo.
    """
    ruta = Path(settings.gpio_lock_file)
    ajeno = _tomar_cerrojo_en_otro_proceso(ruta)
    muerto = _pid_que_no_puede_existir()
    try:
        # (1) DUEÑO VIVO: el registro nombra al PID que de verdad sostiene el flock.
        with pytest.raises(GpioOwnershipError) as vivo:
            GpioController(settings).start()

        # (2) REGISTRO RANCIO: el mismo proceso sigue sosteniendo el flock, pero
        #     el registro apunta a un PID que el kernel no puede haber asignado.
        ruta.write_text(f"pid={muerto}\nunit=takab-gpio\n")
        with pytest.raises(GpioOwnershipError) as rancio:
            GpioController(settings).start()
    finally:
        ajeno.kill()
        ajeno.wait(timeout=30)

    texto_vivo, texto_rancio = str(vivo.value), str(rancio.value)

    assert re.search(rf"pid {ajeno.pid}, vivo\)", texto_vivo), (
        "un dueño que EXISTE en /proc tiene que reportarse como vivo y con su "
        f"PID; el mensaje fue: {texto_vivo}"
    )
    assert "RANCIO" not in texto_vivo, (
        "el dueño está vivo: llamar rancio a su registro mandaría al operador a "
        f"buscar un proceso muerto que no lo está; mensaje: {texto_vivo}"
    )

    assert "RANCIO" in texto_rancio, (
        "el registro apunta a un PID que NO existe y el mensaje no lo dice: el "
        f"operador iría a matar a ese PID —hoy de otro programa—; mensaje: {texto_rancio}"
    )
    assert f"pid {muerto}, vivo)" not in texto_rancio, (
        f"el mensaje declara VIVO al pid {muerto}, que no existe en /proc"
    )


# --------------------------------------------------------------------- (d)


def test_un_arranque_que_truena_despues_del_cerrojo_lo_suelta(settings, monkeypatch) -> None:
    """(d) La trampa de `EdgeModule`: `start()` marca `_running` DESPUÉS de
    `_on_start()`, y `stop()` retorna en seco si no está `_running`. O sea que un
    arranque a medias NUNCA pasa por `_on_stop` — y el descriptor con el cerrojo
    se quedaría colgado en un proceso todavía vivo.

    Con `Restart=always` eso es lo peor posible: el proceso reintenta, se
    encuentra su PROPIO cerrojo del intento anterior, y el gabinete no vuelve a
    proteger nunca aunque la causa original desaparezca.
    """
    import takab_edge.gpio as modulo_gpio

    def revienta() -> None:
        raise RuntimeError("lgpio ausente (venv podado)")

    monkeypatch.setattr(modulo_gpio, "ensure_dev_pin_factory", revienta)
    with pytest.raises(RuntimeError, match="lgpio ausente"):
        GpioController(settings).start()

    monkeypatch.undo()
    assert _cerrojo_libre(Path(settings.gpio_lock_file)), (
        "el arranque fallido se quedó con el cerrojo: el reintento de systemd se "
        "bloquearía a sí mismo para siempre"
    )
    # Y de verdad se puede volver a arrancar (no sólo desde fuera).
    sucesor = GpioController(settings)
    sucesor.start()
    sucesor.stop()


class _EspiaDelRescate(GpioController):
    """Fotografía el NIVEL ELÉCTRICO REAL de los cinco pines al soltar el cerrojo.

    No mira `_relays` ni `_energized` a propósito: la contabilidad interna se
    vacía en el propio rescate, así que apoyarse en ella daría verde con los
    pines todavía energizados. Lo que se lee es el pin de la MockFactory —
    `state` (nivel) y `function` ('output' = este proceso lo está gobernando).
    """

    def __init__(self, settings) -> None:  # noqa: ANN001 — EdgeSettings
        super().__init__(settings)
        self.pines_al_soltar: dict[ActuatorChannel, tuple[bool, str]] = {}
        self.liberaciones = 0

    def _release_pin_ownership(self) -> None:
        # LA PRIMERA liberación, por la misma razón que `_ControladorEspia`:
        # `_release_pin_ownership` es idempotente y la segunda llamada ya no
        # suelta nada, así que sobrescribir dejaría la medida en una invocación
        # inocua.
        self.liberaciones += 1
        if self.liberaciones == 1:
            self.pines_al_soltar = {
                canal: (bool(pin.state), str(pin.function))
                for canal, pin in _pines_de_los_reles(self.settings).items()
            }
        super()._release_pin_ownership()


def test_un_arranque_fallido_deja_los_reles_EN_SEGURO_antes_de_soltar_el_cerrojo(
    settings, monkeypatch
) -> None:
    """[D1·auditoría 2026-08-08] (d) SOLTAR EL CERROJO NO ERA SUFICIENTE.

    El rescate de (d) soltaba el cerrojo y ya: ni `drive_all_safe()` ni
    `close()`. O sea que dejaba el cerrojo LIBRE mientras este proceso seguía
    gobernando los cinco pines, y con `GAS_VALVE` (FAIL_CLOSE) y
    `DOOR_RETAINER` (NORMALLY_CLOSED) **ENERGIZADOS**, que es su nivel de
    reposo. El sucesor —`Restart=always` en dos segundos, o `takab-gpio` a
    mano— toma el cerrojo, se cree dueño, y hay DOS procesos gobernando la
    válvula de gas: exactamente la ventana que `_on_stop` documenta y ordena su
    `finally` para evitar, sólo que en el camino de arranque, que es el que
    corre cada vez que systemd reintenta.

    El fallo inyectado es real y del gabinete: el pin del contacto WR-1 ocupado
    (`Button` no se puede abrir) DESPUÉS de que los cinco relés ya se
    construyeron. Es el orden del código: relés primero, entradas después.

    Se mide EN EL PIN y en el instante exacto de soltar, no después: después,
    cualquier `close()` tardío lo taparía.
    """
    # (premisa, medida) En un gabinete SANO el gas y el retenedor reposan
    # ENERGIZADOS. Sin esto, «ningún pin energizado» podría ser trivialmente
    # cierto y el test no mediría nada.
    sano = GpioController(settings)
    sano.start()
    try:
        pines = _pines_de_los_reles(settings)
        assert pines[ActuatorChannel.GAS_VALVE].state is True, (
            "premisa rota: FAIL_CLOSE reposa ENERGIZADO (válvula abierta)"
        )
        assert pines[ActuatorChannel.DOOR_RETAINER].state is True, (
            "premisa rota: NORMALLY_CLOSED reposa ENERGIZADO (reteniendo la puerta)"
        )
    finally:
        sano.stop()

    def contacto_ocupado(*_args, **_kwargs):
        raise RuntimeError("GPIO busy: el pin del contacto WR-1 ya está tomado")

    monkeypatch.setattr("gpiozero.Button", contacto_ocupado)
    controlador = _EspiaDelRescate(settings)
    with pytest.raises(RuntimeError, match="GPIO busy"):
        controlador.start()
    monkeypatch.undo()

    assert controlador.liberaciones >= 1, "el arranque fallido no soltó el cerrojo"
    assert controlador.pines_al_soltar, "no se llegó a fotografiar el estado de los pines"

    energizados = sorted(c.value for c, (nivel, _f) in controlador.pines_al_soltar.items() if nivel)
    assert energizados == [], (
        f"el cerrojo se soltó con {energizados} TODAVÍA ENERGIZADOS por este "
        "proceso: en ese instante el sucesor puede tomar el cerrojo y abrir sus "
        "propios DigitalOutputDevice sobre la válvula de gas y los retenedores"
    )
    gobernados = sorted(
        c.value for c, (_n, funcion) in controlador.pines_al_soltar.items() if funcion == "output"
    )
    assert gobernados == [], (
        f"el cerrojo se soltó con los pines {gobernados} todavía en 'output': el "
        "proceso los sigue gobernando y ya no tiene con qué defenderlos"
    )

    # Y lo que (d) ya exigía sigue en pie: el sucesor puede arrancar de verdad.
    assert _cerrojo_libre(Path(settings.gpio_lock_file))
    sucesor = GpioController(settings)
    sucesor.start()
    try:
        assert len(sucesor.relay_states()) == 5
    finally:
        sucesor.stop()


def test_un_cerrojo_que_no_se_puede_abrir_no_arranca_a_ciegas(settings, tmp_path) -> None:
    """Fail-CLOSED, no fail-open. Si el archivo del cerrojo no se puede ni abrir
    (directorio inexistente, permisos, ruta mal provisionada), NO se sabe si otro
    proceso tiene los pines. Arrancar «porque el cerrojo no estorbó» es
    exactamente el fallback silencioso que la lección 9361e27 dejó VETADO en este
    módulo: el error tiene que llevar su remediación, como el de `lgpio`.
    """
    imposible = settings.model_copy(
        update={"gpio_lock_path": str(tmp_path / "no-existe" / "gpio.lock")}
    )
    controlador = GpioController(imposible)
    with pytest.raises(GpioOwnershipError, match="WorkingDirectory|edge.env"):
        controlador.start()
    assert controlador._relays == {}


# --------------------------------------------------------- el cerrojo va primero


def test_el_cerrojo_se_toma_antes_de_abrir_el_gpiochip(settings, monkeypatch) -> None:
    """El ORDEN dentro de `_on_start`, medido y no leído.

    `ensure_*_pin_factory()` instancia la factory y con ella ABRE el gpiochip. Si
    el cerrojo llegara después, el intruso ya habría tocado el hardware cuando se
    entera de que no le tocaba. Se comprueba preguntando, DESDE DENTRO de
    `ensure_dev_pin_factory`, si el cerrojo ya está tomado.
    """
    import takab_edge.gpio as modulo_gpio

    original = modulo_gpio.ensure_dev_pin_factory
    visto: dict[str, bool] = {}

    def espiada() -> None:
        fd = os.open(settings.gpio_lock_file, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            visto["cerrojo_ya_tomado"] = True
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            visto["cerrojo_ya_tomado"] = False
        finally:
            os.close(fd)
        original()

    monkeypatch.setattr(modulo_gpio, "ensure_dev_pin_factory", espiada)
    controlador = GpioController(settings)
    controlador.start()
    try:
        assert visto.get("cerrojo_ya_tomado") is True, (
            "la pin factory se instancia (y abre el gpiochip) ANTES de reclamar la "
            "propiedad de los pines"
        )
    finally:
        controlador.stop()


# ------------------------------------------- el registro es INFORMATIVO (B2)


def test_un_registro_que_no_se_puede_escribir_no_tumba_la_propiedad(
    settings, monkeypatch, caplog
) -> None:
    """[B2] El registro (pid + unidad) es INFORMATIVO; el veredicto lo da el flock.

    Entre `flock()` y `self._lock_fd = fd` había un `ftruncate` + `pwrite` SIN
    GUARDA, y ese par es E/S falible de verdad en este gabinete: `ENOSPC` con
    /var/lib/takab lleno por el spool offline, la evidencia o el journal; `EIO`
    de una microSD empezando a morir. Cuando fallaba:

    * `_on_start` lanzaba CON EL CERROJO YA TOMADO y `_lock_fd = None`, así que
      `_release_pin_ownership()` era un no-op y el descriptor quedaba colgado en
      un proceso TODAVÍA VIVO — con `Restart=always`, el reintento se bloquea
      contra su propio cerrojo para siempre;
    * y lanzaba un `OSError` pelado, ni siquiera `GpioOwnershipError`.

    O sea: un dato que el propio código documenta como informativo desprotegía
    el edificio. Aquí se mide lo contrario: el fallo del registro NO impide ser
    dueño, y no se pierde en silencio.
    """
    ruta = Path(settings.gpio_lock_file)
    controlador = GpioController(settings)
    fd_al_escribir: list = []

    def sin_espacio(*_args, **_kwargs) -> int:
        # EL ORDEN, medido desde DENTRO del fallo: cuando la E/S falible ocurre,
        # ¿ya está guardado el descriptor? Si no, este `raise` —o cualquier otro
        # que se añada aquí mañana— deja el cerrojo tomado y a `_lock_fd = None`.
        fd_al_escribir.append(controlador._lock_fd)
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "pwrite", sin_espacio)

    with caplog.at_level(logging.WARNING, logger="takab_edge.gpio"):
        controlador.start()  # NO truena: el cerrojo ya es suyo
    try:
        assert fd_al_escribir and fd_al_escribir[0] is not None, (
            "el descriptor del cerrojo NO estaba guardado cuando se intentó la "
            "E/S del registro: los pines ya son de este proceso desde el flock, "
            "así que cualquier `raise` en esa ventana deja el fd colgado en un "
            "proceso vivo y `_release_pin_ownership()` no tiene nada que soltar"
        )
        assert controlador._lock_fd is not None
        assert len(controlador.relay_states()) == 5, (
            "el gabinete no arrancó por no poder escribir un dato informativo"
        )
        assert not _cerrojo_libre(ruta), "es dueño de los pines, así que el cerrojo está tomado"

        avisos = [r for r in caplog.records if r.levelno >= logging.WARNING]
        texto = "\n".join(r.getMessage() for r in avisos)
        assert "registro" in texto.lower(), (
            "el fallo del registro se perdió en silencio: el operador verá un "
            f"cerrojo sin dueño escrito y no sabrá por qué. Avisos: {texto!r}"
        )
        assert "No space left" in texto, "el aviso debe llevar el errno real, no una paráfrasis"
    finally:
        monkeypatch.undo()  # `_release_pin_ownership` no usa pwrite, pero que quede limpio
        controlador.stop()

    assert _cerrojo_libre(ruta), (
        "el cerrojo no se soltó al parar: el descriptor se quedó colgado por un "
        "fallo del registro INFORMATIVO"
    )


# --------------------------------------------- B1: el cerrojo fuera del Pi
#
# El cerrojo tiene que ser fail-closed EN EL GABINETE —ahí «no puedo garantizar
# que soy el dueño» debe impedir tocar pines— sin convertir el desarrollo y la
# demo en un campo minado. Toda esta suite corre con `cerrojo_de_pines_por_test`
# inyectando una ruta por test, y el agujero vivía JUSTO FUERA de donde miran
# los tests: `make edge` y `demo/gabinete.py` no tienen ese fixture.


@pytest.fixture
def sin_ruta_por_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Apaga, SÓLO en este test, la ruta que `conftest` inyecta por entorno.

    Sin esto no se puede medir lo que ve un arranque real: cada test de esta
    suite es un gabinete con su cerrojo en un `tmp_path`, y esa comodidad es
    exactamente la que escondía que el default no era arrancable fuera del Pi.
    """
    monkeypatch.delenv(_ENV_CERROJO, raising=False)


def test_make_edge_arranca_en_una_maquina_sin_var_lib_takab(sin_ruta_por_test) -> None:
    """[B1] El arranque de `make edge`, sin ninguna ruta inyectada.

    `make edge` es `uv run takab-edge`, o sea `load_settings()` a secas en una
    máquina de desarrollo donde /var/lib/takab NO existe. Con el cerrojo
    apuntando ahí por defecto —y la apertura siendo fail-closed, como debe ser—
    el camino de vida dejaba de arrancar fuera del Pi, y `demo/gabinete.py` con
    él. La salida NO es que el fallo de apertura se vuelva benigno (eso es el
    default-benigno que esta tarea persigue): es que en `dev_mode` el cerrojo
    viva donde el desarrollador SÍ puede escribir, derivado de la identidad del
    gabinete y no de una ruta aprovisionada que nadie provisionó.
    """
    ajustes = load_settings()  # exactamente lo que hace el entry point `takab-edge`
    assert ajustes.gpio_lock_path == "", "premisa: nadie configuró la ruta del cerrojo"
    assert ajustes.dev_mode is True, "premisa: `make edge` corre en modo dev"

    ruta = Path(ajustes.gpio_lock_file)
    assert ruta.parent.is_dir(), (
        f"el cerrojo derivado para dev vive en {ruta.parent}, que no existe: el "
        "camino de vida no arrancaría en ninguna máquina de desarrollo"
    )

    controlador = GpioController(ajustes)
    controlador.start()  # ← lo que tronaba
    try:
        assert len(controlador.relay_states()) == 5
        assert not _cerrojo_libre(ruta), "arrancó, así que el cerrojo tiene que estar tomado"
    finally:
        controlador.stop()


def test_tres_gabinetes_simulados_en_el_mismo_host_no_se_matan_entre_si(sin_ruta_por_test) -> None:
    """[B1] `demo/run.py` lanza TRES gabinetes en el mismo host.

    Con una única ruta por defecto arrancaba uno y morían dos — y ese arnés es
    el que acreditó el hito de la Fase 1 (35/35 ×3). Compartirles el cerrojo
    tampoco vale: son tres gabinetes DISTINTOS, cada uno con sus pines (en la
    demo, mock; en el mundo, tres edificios). Por eso el cerrojo derivado se
    indexa por la identidad del gabinete, que es lo que `demo/gabinete.py` pasa
    como `gateway_id`.

    Y la mitad que impide que esto sea un cerrojo de mentira: el MISMO gabinete
    dos veces sigue chocando.
    """
    identidades = ("gw-sim-0001", "gw-sim-0002", "gw-sim-0003")  # las de demo/run.py
    base = load_settings()
    rutas = [Path(base.model_copy(update={"gateway_id": g}).gpio_lock_file) for g in identidades]
    assert len({str(r) for r in rutas}) == 3, (
        f"los tres gabinetes de la demo comparten cerrojo ({rutas}): arrancaría uno y morirían dos"
    )

    primero = _tomar_cerrojo_en_otro_proceso(rutas[0])
    try:
        segundo = GpioController(base.model_copy(update={"gateway_id": identidades[1]}))
        segundo.start()  # el gabinete de al lado no le quita los pines
        try:
            assert len(segundo.relay_states()) == 5
        finally:
            segundo.stop()

        mismo = GpioController(base.model_copy(update={"gateway_id": identidades[0]}))
        with pytest.raises(GpioOwnershipError):
            mismo.start()
        assert mismo._relays == {}, (
            "dos procesos del MISMO gabinete tienen que seguir chocando: el "
            "cerrojo es por gabinete, no por proceso"
        )
    finally:
        primero.kill()
        primero.wait(timeout=30)


def test_en_produccion_el_cerrojo_sigue_siendo_el_aprovisionado(sin_ruta_por_test) -> None:
    """[B1] La mitad que NO puede relajarse: el gabinete real.

    En `dev_mode=False` —que es lo que ponen EXPLÍCITAMENTE las dos unidades
    systemd— la ruta no se deriva de nada: es el archivo fijo dentro del
    /var/lib/takab que ambas unidades declaran como `WorkingDirectory=` y
    `ReadWritePaths=`. Ahí los dos procesos que pueden pelearse por los pines
    (`takab-edge` y `takab-gpio`) tienen que aterrizar en el MISMO archivo o el
    cerrojo no protege nada. Se comprueba además que no depende de que el
    directorio exista: la respuesta es la misma ruta, y si no se puede abrir, se
    truena (ver `test_un_cerrojo_que_no_se_puede_abrir_no_arranca_a_ciegas`).
    """
    produccion = load_settings().model_copy(update={"dev_mode": False})
    assert produccion.gpio_lock_file == "/var/lib/takab/gpio.lock"

    # Y no se indexa por gabinete: un Pi tiene UN gabinete y DOS procesos.
    otro = produccion.model_copy(update={"gateway_id": "gw-prod-9999"})
    assert otro.gpio_lock_file == produccion.gpio_lock_file


def test_el_cerrojo_DERIVADO_no_cruza_un_tmp_privado(sin_ruta_por_test, tmp_path, monkeypatch):
    """[D1·auditoría 2026-08-08] LA AFIRMACIÓN QUE ERA FALSA, ahora medida.

    El docstring de `gpio_lock_file` sostenía que un Pi con `dev_mode` mal puesto
    dejaría a `takab-edge` y `takab-gpio` «colisionando igual, porque comparten
    `gateway_id` y por tanto cerrojo derivado». No: `takab-edge.service` corre
    con `PrivateTmp=true` y `takab-gpio.service` no, así que la MISMA ruta
    derivada aterriza en DOS `/tmp` distintos — dos archivos, dos `flock`, dos
    dueños que no se ven.

    Aquí se mide esa dependencia del temporal, que es la razón de fondo, sin
    tocar las unidades: el cerrojo derivado NO es un mecanismo entre espacios de
    nombres de `/tmp`, y quien vuelva a escribir lo contrario se encontrará este
    test. Lo que sí protege a los dos procesos es la ruta FIJA de producción, que
    es la que ambas unidades usan (`TAKAB_EDGE_DEV_MODE=false`).
    """
    import tempfile

    base = load_settings()
    assert base.dev_mode is True, "premisa: es el cerrojo DERIVADO el que se mide"

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp-privado-de-takab-edge"))
    desde_edge = base.gpio_lock_file
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp-global-de-takab-gpio"))
    desde_gpio = base.gpio_lock_file

    assert desde_edge != desde_gpio, (
        "el cerrojo derivado NO depende del temporal: si eso cambiara, la nota del "
        "docstring habría que reescribirla otra vez — y hoy es al revés"
    )

    produccion = base.model_copy(update={"dev_mode": False})
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "otro-tmp-todavia"))
    assert produccion.gpio_lock_file == "/var/lib/takab/gpio.lock", (
        "la ruta de producción tiene que ser INDIFERENTE al temporal: es lo único "
        "que hace que los dos procesos del Pi se vean"
    )


def test_en_produccion_un_cerrojo_inabrible_tampoco_cae_a_un_scratch(settings, tmp_path) -> None:
    """[B1] La derivación es por MODO, jamás un fallback ante un fallo.

    El riesgo de dar una salida al dev es reintroducir «ante lo desconocido,
    asume la causa más benigna»: que un cerrojo que no se puede abrir se
    resuelva solo cayendo a un archivo de scratch. Aquí se mide que NO: en
    producción, con la ruta aprovisionada inabrible, el arranque truena y no
    toca un pin — ni siquiera llega a instanciar la pin factory de producción,
    que en esta máquina no existe (`lgpio`).
    """
    imposible = settings.model_copy(
        update={
            "dev_mode": False,
            "gpio_lock_path": str(tmp_path / "no-existe" / "gpio.lock"),
        }
    )
    controlador = GpioController(imposible)
    with pytest.raises(GpioOwnershipError, match="WorkingDirectory|edge.env"):
        controlador.start()
    assert controlador._relays == {}
