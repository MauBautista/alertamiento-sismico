"""gpio — WR-1 (contacto seco) + relés locales fail-safe + reflejo SASMEX→sirena.

[RATIFICADO 2026-07-09 · T-1.45 · gate #6] Proceso mínimo y auditable (regla de oro 4). El
reflejo SASMEX→sirena ocurre **in-process** (<100 ms, blueprint §4.3), sin cruzar
IPC ni depender de la nube ni de IA. **Canal primario de alertamiento.**

T-1.3: reflejo con latencia medida, debounce 50 ms, botones de silencio y prueba,
relés fail-safe NO/NC/fail-close por canal con estado seguro (SPOF-07), y proceso
standalone mínimo (`python -m takab_edge.gpio`) sin dependencias pesadas.

**Estado por DEMANDAS (no escritura directa).** El estado eléctrico de cada canal
se RECALCULA (`_desired_energized`) a partir de demandas independientes —el reflejo
SASMEX enclavado, la secuencia de `rules`, el self-test del operador y el silencio—
y se aplica bajo un `RLock`. Así una demanda (p.ej. el fin de un self-test) NUNCA
puede llevar la sirena por debajo de la protección exigida por una alerta viva, y el
silencio apaga de inmediato lo que ya suena. Todas las transiciones se serializan
(hay varios hilos: callbacks de gpiozero, el `Timer` del self-test y `rules`).

**Modelo fail-safe (SPOF-07, blueprint §4.7).** El estado SEGURO es siempre el
DE-ENERGIZADO (una falla del Pi corta la energía del relé → contacto en reposo):
- `NO` (sirena/estrobo/ascensor): reposo de-energizado = inactivo; **activar = energizar**.
- `NC` (retenedor de puerta): reposo energizado (retiene); **activar = de-energizar** (libera).
- `fail_close` (gas): reposo energizado (abierto); **activar = de-energizar** (cierra).
La polaridad eléctrica real de cada relé se re-valida con hardware (**gate #3**).
"""

from __future__ import annotations

import fcntl
import logging
import os
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter

from takab_edge.config import EdgeSettings
from takab_edge.contracts import (
    ActuatorChannel,
    FailSafeMode,
    RelayState,
    SasmexSignal,
    SirenReason,
)
from takab_edge.gpio_link import ChannelOutcome, GpioSnapshot
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.gpio")

#: Canales gobernados por relés locales de este módulo (SPOF-07).
LOCAL_RELAY_CHANNELS: tuple[ActuatorChannel, ...] = (
    ActuatorChannel.SIREN,
    ActuatorChannel.STROBE,
    ActuatorChannel.GAS_VALVE,
    ActuatorChannel.ELEVATOR,
    ActuatorChannel.DOOR_RETAINER,
)

#: Canales que dispara el reflejo inmediato SASMEX.
REFLEX_CHANNELS: tuple[ActuatorChannel, ...] = (
    ActuatorChannel.SIREN,
    ActuatorChannel.STROBE,
)

#: Canales AUDIBLES — el silencio del operador los inhibe (NFPA 72: silenciar audible).
AUDIBLE_CHANNELS: tuple[ActuatorChannel, ...] = (ActuatorChannel.SIREN,)

SasmexCallback = Callable[[SasmexSignal], None]


class UndeclaredFailSafeError(KeyError):
    """[T-2.70.a·D1.2] Canal de RELÉ sin modo fail-safe declarado en la config.

    Hereda de ``KeyError`` por continuidad: ``set_relay`` ya lanzaba ``KeyError``
    ante un canal fuera del mapa de relés y quien lo capturaba sigue capturándolo.
    """


class GpioOwnershipError(RuntimeError):
    """[T-2.70.a·D1.1] Otro proceso VIVO ya es dueño de los pines del gabinete."""


#: Variable de entorno que nombra la unidad systemd de este proceso en el
#: registro del cerrojo. Sin ella se deriva de ``sys.argv[0]``, que en el Pi es
#: ``/opt/takab/edge/.venv/bin/takab-edge`` o ``…/takab-gpio`` — o sea, el nombre
#: de la unidad. NO es un campo de `EdgeSettings` a propósito: es una etiqueta de
#: diagnóstico, y meterla en el documento firmado la convertiría en algo que la
#: nube puede reescribir.
UNIT_ENV_VAR = "TAKAB_GPIO_UNIT"


def _unidad_de_este_proceso() -> str:
    """Nombre con el que este proceso se identifica como dueño de los pines."""
    override = os.environ.get(UNIT_ENV_VAR, "").strip()
    if override:
        return override
    return Path(sys.argv[0]).name or "desconocida"


def _proceso_vivo(pid: int) -> bool:
    """¿Sigue existiendo ese PID? (Linux: `/proc/<pid>`.)

    Un registro rancio —el proceso murió por SIGKILL sin poder limpiar— señalaría
    a un PID que hoy puede ser de otro programa. Reportarlo como dueño vivo manda
    al operador a matar a un inocente.
    """
    return pid > 0 and Path(f"/proc/{pid}").exists()


def normal_energized(mode: FailSafeMode) -> bool:
    """Estado eléctrico en operación normal (no-emergencia) para un modo fail-safe."""
    # NC/fail_close se sostienen ENERGIZADOS en reposo (retienen/mantienen abierto);
    # NO reposa de-energizado. Ver docstring del módulo.
    return mode in (FailSafeMode.NORMALLY_CLOSED, FailSafeMode.FAIL_CLOSE)


def active_energized(mode: FailSafeMode) -> bool:
    """Estado eléctrico en emergencia (acción de protección tomada)."""
    return not normal_energized(mode)


def ensure_dev_pin_factory() -> None:
    """En dev/CI usa la MockFactory de gpiozero (sin hardware físico).

    Idempotente: no reemplaza una MockFactory ya activa. En el Pi 5 real
    (``dev_mode=False``) se llama a :func:`ensure_prod_pin_factory`, que fija
    LGPIOFactory EXPLÍCITA o truena — jamás auto-selección de backend.
    """
    from gpiozero import Device
    from gpiozero.pins.mock import MockFactory

    if not isinstance(Device.pin_factory, MockFactory):
        Device.pin_factory = MockFactory()


def ensure_prod_pin_factory() -> None:
    """Producción: LGPIOFactory EXPLÍCITA o tronar — jamás auto-selección (A-2).

    Lección de 9361e27: si ``LGPIOFactory`` no puede instanciarse (p.ej. no puede
    crear su FIFO ``.lgd-nfy*`` porque el CWD es de solo lectura bajo
    ``ProtectSystem=strict``), la auto-selección de gpiozero cae EN SILENCIO al
    backend ``native`` (sysfs), que en Pi 5 muere con EINVAL — o peor, medio
    funciona. Este módulo es el camino de vida (``critical=True``): un backend
    equivocado debe tirar el arranque, no callarse.

    Contrato:
    - ``GPIOZERO_PIN_FACTORY`` explícita ⇒ se respeta con warning (gpiozero ya
      truena por sí solo si ese nombre no carga; es la vía de tests/CI).
    - Factory ya fijada en el proceso ⇒ se respeta con warning (harness de
      pruebas). En un proceso fresco de producción SIEMPRE es ``None``.
    - Proceso fresco (sin env, factory ``None``) ⇒ ``LGPIOFactory()`` explícita;
      cualquier fallo ⇒ ``RuntimeError`` ruidoso con la remediación.
    """
    from gpiozero import Device

    override = os.environ.get("GPIOZERO_PIN_FACTORY")
    if override:
        log.warning(
            "GPIOZERO_PIN_FACTORY=%r fija la pin factory por env; se respeta "
            "(gpiozero truena solo si ese backend no carga)",
            override,
        )
        return
    if Device.pin_factory is not None:
        actual = type(Device.pin_factory).__name__
        if actual != "LGPIOFactory":
            log.warning(
                "pin factory ya fijada a %s antes de gpio._on_start; se respeta "
                "(esperado solo en harness de pruebas — en el Pi arranca en None)",
                actual,
            )
        return
    try:
        from gpiozero.pins.lgpio import LGPIOFactory
    except Exception as exc:
        raise RuntimeError(
            "gpio: no se pudo importar gpiozero.pins.lgpio y en producción el "
            "camino de vida exige lgpio EXPLÍCITO (sin fallback silencioso a "
            "native/sysfs). ¿El deploy corrió `uv sync --extra hardware --extra "
            "aws`? (lección 9361e27: `--extra hardware` a secas poda paquetes)"
        ) from exc
    try:
        Device.pin_factory = LGPIOFactory()
    except Exception as exc:
        raise RuntimeError(
            "gpio: LGPIOFactory no pudo instanciarse y NO se permite caer a "
            "native/sysfs. Causa típica (9361e27): no puede crear su FIFO "
            ".lgd-nfy* porque el CWD es de solo lectura — la unidad systemd debe "
            "tener WorkingDirectory=/var/lib/takab (escribible) bajo "
            "ProtectSystem=strict. Revisa también permisos de /dev/gpiochip*."
        ) from exc
    log.info("pin factory de producción fijada: LGPIOFactory (lgpio)")


class GpioController(EdgeModule):
    """Controla la entrada WR-1 y los relés locales, y ejecuta el reflejo.

    El reflejo se dispara por ``when_pressed`` del contacto (evento, con debounce)
    y, de forma equivalente y determinista, vía :meth:`simulate_sasmex` (usado por
    el simulador WR-1 y los tests, sin depender del hilo de gpiozero).
    """

    name = "gpio"
    critical = True  # WR-1 + relés = el reflejo de vida; su fallo debe fail-fast

    def __init__(self, settings: EdgeSettings) -> None:
        super().__init__()
        self.settings = settings
        self._lock = threading.RLock()
        self._sasmex_callbacks: list[SasmexCallback] = []
        self._silence_callbacks: list[Callable[[bool], None]] = []
        self._button = None  # gpiozero.Button (WR-1)
        self._silence_button = None
        self._test_button = None
        self._relays: dict[ActuatorChannel, object] = {}  # gpiozero.DigitalOutputDevice
        self._energized: dict[ActuatorChannel, bool] = {}
        # --- Demandas independientes que determinan el estado de cada canal ---
        self._sasmex_latched = False  # alerta SASMEX real asertada (enclavada)
        self._audible_silenced = False  # operador silenció los canales audibles
        self._siren_test_active = False  # self-test del operador energizando la sirena
        self._actuation_test_active = False  # prueba LOCAL: sirena+estrobo sostenidos (T-1.67)
        self._rules_demand: dict[ActuatorChannel, bool] = {}  # protección ordenada por `rules`
        self._safed = (
            False  # estado seguro forzado (drive_all_safe): todo de-energizado hasta reset()
        )
        self._last_reflex_latency_s: float | None = None
        self._test_timer: threading.Timer | None = None
        self._actuation_test_timer: threading.Timer | None = None
        self._test_mode_until = 0.0  # [T-1.69] deadline monotónico del modo prueba WR-1
        #: [D1.1] Descriptor del cerrojo de propiedad de pines mientras se sostiene.
        self._lock_fd: int | None = None
        #: [D2/P2] Puerta de servicio del dueño (socket AF_UNIX). Se construye UNA
        #: vez por controlador y se reutiliza entre arranques: `gpio` no sabe
        #: desregistrar observadores, y un servidor nuevo por arranque los iría
        #: acumulando en `_sasmex_callbacks`.
        self._servidor_de_pines = None

    # --- Observadores + silencio ---
    def on_sasmex(self, callback: SasmexCallback) -> None:
        """Registra un callback no-reflejo (rules evalúa; cloud publica)."""
        self._sasmex_callbacks.append(callback)

    def on_silence(self, callback: Callable[[bool], None]) -> None:
        """Observer del silencio (A-6: el voceo debe callarse con la sirena).

        Se invoca DESPUÉS de recalcular los relés y FUERA del lock; cada callback
        se aísla — un observer roto jamás toca el camino de vida.
        """
        self._silence_callbacks.append(callback)

    def silence_audibles(self, silenced: bool = True) -> None:
        """Silencio/re-armado del operador: apaga/reactiva los canales AUDIBLES.

        Actúa YA sobre lo que suena (no sólo inhibe futuros): recalcula la sirena.
        NO afecta al estrobo (alerta visual) ni al estado de alerta (`sasmex_active`
        sigue vigente), sólo al aviso audible. El re-armado vuelve a sonar si la
        alerta sigue enclavada. El botón físico alterna silencio↔re-armado.
        """
        with self._lock:
            self._audible_silenced = silenced
            for channel in AUDIBLE_CHANNELS:
                self._apply(channel)
        log.warning("audibles %s", "SILENCIADOS" if silenced else "RE-ARMADOS")
        for callback in list(self._silence_callbacks):
            try:
                callback(silenced)
            except Exception:  # noqa: BLE001 — observer advisory, jamás al camino de vida
                log.exception("observer de silencio falló (aislado)")

    @property
    def audible_silenced(self) -> bool:
        return self._audible_silenced

    @property
    def actuation_test_active(self) -> bool:
        """True mientras una prueba LOCAL sostiene la sirena/estrobo (T-1.67)."""
        return self._actuation_test_active

    # --- Modo prueba del WR-1 (T-1.69): la nube NO recibe alertas, el local SÍ ---
    def arm_test_mode(self, window_s: float | None = None) -> float:
        """Arma la ventana de prueba del WR-1. Devuelve los segundos que durará.

        Durante la ventana el gabinete protege en LOCAL exactamente igual (el reflejo
        y los actuadores actúan), pero el supervisor NO publica el evento a la nube:
        ni incidente ni notificación. Auto-expira (ventana corta) porque dejarlo
        armado silenciaría a la nube ante una alerta REAL. gpio solo guarda el estado;
        la supresión de la publicación vive en el supervisor.
        """
        window = window_s if window_s is not None else self.settings.sasmex_test_window_s
        self._test_mode_until = time.monotonic() + window
        log.warning(
            "MODO PRUEBA WR-1 ARMADO %.0fs: protección LOCAL intacta; la nube NO "
            "recibirá alertas (sin incidente ni notificación) hasta que expire.",
            window,
        )
        return window

    def disarm_test_mode(self) -> None:
        self._test_mode_until = 0.0
        log.warning("MODO PRUEBA WR-1 DESARMADO: la nube vuelve a recibir alertas.")

    @property
    def test_mode_active(self) -> bool:
        return time.monotonic() < self._test_mode_until

    @property
    def test_mode_remaining_s(self) -> float:
        return max(0.0, self._test_mode_until - time.monotonic())

    @property
    def last_reflex_latency_s(self) -> float | None:
        """Latencia medida de la última ruta software del reflejo (SASMEX→relé)."""
        return self._last_reflex_latency_s

    @property
    def debounce_s(self) -> float:
        """Debounce del contacto WR-1 en segundos (parte del presupuesto §4.3)."""
        return self.settings.debounce_ms / 1000.0

    # --- [D1.1] Propiedad de los pines: un cerrojo del KERNEL, no una promesa ---
    def _acquire_pin_ownership(self) -> None:
        """Reclama la propiedad EXCLUSIVA de los pines, o truena sin tocar nada.

        `flock(LOCK_EX|LOCK_NB)` y no una bandera de proceso: el escenario real es
        un SEGUNDO PROCESO —`takab-gpio.service` frente a `takab-edge`, o un
        `python -m takab_edge.gpio` a mano por SSH— y una variable de Python no
        cruza la frontera del proceso. Hasta D3 lo único que separaba a esos dos
        era `Conflicts=takab-gpio.service` en las unidades: una promesa que sólo
        se cumplía si systemd arrancaba a los dos —nunca frente a la sesión SSH—
        y que **D3 RETIRÓ**, porque con el dueño de los pines en `takab-gpio` la
        exclusión mutua convertía cada arranque del otro servicio en una ventana
        de desprotección. Desde entonces esto es lo ÚNICO que lo impide.

        `flock` colisiona incluso entre dos descriptores del MISMO proceso (son
        dos «open file descriptions» distintas), así que también atrapa a un
        supervisor que instanciara dos `GpioController`.

        La ruta sale de `EdgeSettings.gpio_lock_file` (la EFECTIVA, no el campo
        crudo): en el gabinete es el archivo aprovisionado de /var/lib/takab y
        en dev/demo uno por gabinete en el directorio temporal. Ver allí por qué
        — y por qué eso no relaja en nada el fail-closed de aquí abajo.
        """
        ruta = Path(self.settings.gpio_lock_file)
        unidad = _unidad_de_este_proceso()
        try:
            fd = os.open(ruta, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError as exc:
            # Fail-closed y con remediación, como `ensure_prod_pin_factory`: si no
            # se puede ni ABRIR el cerrojo, no hay forma de saber si otro proceso
            # tiene los pines, y arrancar a ciegas es lo único inaceptable.
            raise GpioOwnershipError(
                f"no se pudo abrir el cerrojo de pines {ruta} ({exc}). El camino de "
                "vida no arranca sin poder comprobar quién es dueño del GPIO. "
                "¿Existe el directorio (las unidades usan WorkingDirectory="
                "/var/lib/takab y ReadWritePaths=/var/lib/takab)? ¿`gpio_lock_path` "
                "(TAKAB_EDGE_GPIO_LOCK_PATH) está bien provisionado en "
                "/etc/takab/edge.env? Nadie elige otra ruta por su cuenta: si esta "
                "no se puede abrir, no se toca un pin."
            ) from exc
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            detalle = self._describir_dueno(fd)
            os.close(fd)
            log.critical(
                "PINES YA RECLAMADOS: %s (pid %s) NO tomará el GPIO porque %s "
                "sostiene el cerrojo %s. NO se ha tocado un solo pin — dos dueños "
                "sobre la válvula de gas es peor que un proceso que no arranca.",
                unidad,
                os.getpid(),
                detalle,
                ruta,
            )
            raise GpioOwnershipError(
                f"los pines del gabinete ya tienen dueño: {detalle} sostiene el "
                f"cerrojo {ruta}; este proceso ({unidad}, pid {os.getpid()}) aborta "
                "sin tocar hardware"
            ) from exc
        # PRIMERO el descriptor, que es lo que ES la propiedad: desde el `flock`
        # de arriba estos pines ya son nuestros, y cualquier `raise` que ocurra
        # sin haberlo guardado deja el fd colgado en un proceso VIVO —
        # `_release_pin_ownership()` es un no-op con `_lock_fd = None`— y con
        # `Restart=always` el reintento se bloquea contra su propio cerrojo.
        self._lock_fd = fd
        # El registro es informativo (quién manda ahora); el veredicto de
        # propiedad lo da SIEMPRE el flock, que muere con el proceso pase lo que
        # pase — incluido un SIGKILL, donde este texto quedaría rancio.
        #
        # Por eso su E/S va guardada y NO tumba la propiedad: `ENOSPC` con
        # /var/lib/takab lleno (spool offline, evidencia, journal) o un `EIO` de
        # una microSD muriéndose son fallos REALES de este gabinete, y ninguno
        # es razón para dejar la sirena, el gas y los retenedores sin dueño.
        # Ruidoso, eso sí: sin este WARNING el operador leería un cerrojo con el
        # dueño ANTERIOR escrito —o vacío— y no sabría por qué.
        try:
            os.ftruncate(fd, 0)
            os.pwrite(fd, f"pid={os.getpid()}\nunit={unidad}\n".encode(), 0)
        except OSError as exc:
            log.warning(
                "PINES TOMADOS por %s (pid %s), pero el registro informativo de %s "
                "NO se pudo escribir (%s): el cerrojo es válido (lo sostiene el "
                "kernel), pero su contenido puede estar vacío o nombrar al dueño "
                "anterior. Revisa el disco del gabinete.",
                unidad,
                os.getpid(),
                ruta,
                exc,
            )
        log.info("propiedad de los pines tomada por %s (pid %s) en %s", unidad, os.getpid(), ruta)

    @staticmethod
    def _describir_dueno(fd: int) -> str:
        """`'<unidad> (pid N, vivo)'` leído del registro, o lo que se sepa.

        Se lee del MISMO descriptor que ya está abierto (no se re-abre el
        archivo) y se comprueba `/proc`: un registro rancio no puede reportarse
        como dueño vivo — el PID pudo reciclarse y el operador iría a matar a
        otro programa.
        """
        try:
            crudo = os.pread(fd, 4096, 0).decode("utf-8", "replace")
        except OSError:
            crudo = ""
        campos = dict(linea.split("=", 1) for linea in crudo.splitlines() if linea.count("=") >= 1)
        unidad = campos.get("unit", "").strip() or "un proceso sin unidad declarada"
        crudo_pid = campos.get("pid", "").strip()
        if not crudo_pid.isdigit():
            return f"{unidad} (sin PID en el registro; el cerrojo lo sostiene alguien VIVO)"
        pid = int(crudo_pid)
        estado = (
            "vivo"
            if _proceso_vivo(pid)
            else "RANCIO en el registro, pero el cerrojo lo sostiene alguien VIVO"
        )
        return f"{unidad} (pid {pid}, {estado})"

    def _release_pin_ownership(self) -> None:
        """Suelta el cerrojo. Idempotente: llamarlo dos veces no rompe nada."""
        fd = self._lock_fd
        if fd is None:
            return
        self._lock_fd = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:  # cerrar el fd lo suelta igual; no hay nada que rescatar
            log.warning("flock(LOCK_UN) falló al soltar los pines; se cierra el descriptor")
        finally:
            os.close(fd)

    # --- Ciclo de vida ---
    def _on_start(self) -> None:
        # PRIMERA SENTENCIA, y el orden es el mecanismo: `ensure_*_pin_factory()`
        # instancia LGPIOFactory y con ella ABRE el gpiochip. Reclamar la
        # propiedad después significaría que el intruso ya tocó el hardware
        # cuando se entera de que no le tocaba.
        self._acquire_pin_ownership()
        try:
            self._arrancar_hardware()
            # DESPUÉS del hardware, y NO crítico: quien conteste por el socket ya
            # es dueño de los pines, con los cinco relés construidos y los tres
            # botones armados.
            self.arrancar_servidor_de_pines()
            # [T-2.70.a·D3] …y la semilla de SPOF-02 va DESPUÉS de la puerta.
            #
            # Estaba al final de `_arrancar_hardware`, o sea antes de que el
            # servidor existiera, y con el dueño en OTRO PROCESO eso deja mudo el
            # traspaso hardware→software: `PinLinkServer._al_sasmex` todavía no
            # está registrado, así que el episodio nace sin `episode_id`, y el
            # cliente que conecta después recibe una instantánea con
            # `sasmex_active=True` y `episode_id: None` — que
            # `_reconciliar_episodio` descarta POR DISEÑO (sin identidad de
            # episodio, sintetizar por estado abriría un incidente nuevo por cada
            # instantánea, veinte por segundo). Resultado: sirena sonando en el
            # edificio y CERO incidente, notificación y push.
            #
            # Lo que se pierde con el orden nuevo es que un cliente que conecte en
            # el hueco de microsegundos entre el bind y la semilla vea una
            # instantánea sin la alerta. Es inocuo: el evento le llega detrás por
            # el mismo socket, y esa es la vía por la que llegan todas las demás.
            self._seed_from_held_contact()
        except BaseException:
            # La puerta PRIMERO, como en `_on_stop` y por la misma razón: soltar
            # el cerrojo con el socket todavía atado dejaría al sucesor sin poder
            # atarlo (`_preparar_ruta` ve a alguien vivo detrás y se niega a
            # robarle la ruta), o sea un dueño de pines con el que nadie puede
            # hablar. Es idempotente y no lanza.
            self.detener_servidor_de_pines()
            # [D1·auditoría 2026-08-08] PRIMERO el hardware a seguro, DESPUÉS el
            # cerrojo — el MISMO orden que `_on_stop` documenta en su `finally`,
            # y por la misma razón. Aquí sólo se soltaba el cerrojo: quedaba
            # LIBRE mientras este proceso seguía gobernando cinco pines, con
            # `GAS_VALVE` (FAIL_CLOSE) y `DOOR_RETAINER` (NORMALLY_CLOSED)
            # ENERGIZADOS, que es su nivel de reposo. El sucesor —`Restart=always`
            # en segundos, o un `takab-gpio` a mano— tomaba el cerrojo y abría sus
            # propios `DigitalOutputDevice` sobre esos mismos pines: dos procesos
            # gobernando la válvula de gas, que es lo único que el cerrojo existe
            # para impedir.
            self._rescatar_hardware_a_medio_montar()
            # `EdgeModule.start()` sólo marca `_running` si `_on_start` VOLVIÓ, y
            # `stop()` retorna en seco si no está `_running`: sin esto el
            # descriptor quedaría colgado en un proceso TODAVÍA VIVO y, con
            # `Restart=always`, el reintento se bloquearía contra su propio
            # cerrojo para siempre.
            self._release_pin_ownership()
            raise

    def _rescatar_hardware_a_medio_montar(self) -> None:
        """[D1·auditoría] Deja en SEGURO lo que el arranque alcanzó a construir.

        Se llama con el cerrojo TODAVÍA en la mano, que es lo que hace legítimo
        tocar los pines: mientras este proceso es el dueño, nadie más los
        gobierna. Nunca lanza — el arranque ya viene con una excepción viva y
        taparla dejaría al operador sin la causa —, pero un rescate que no pueda
        completarse es CRITICAL: significa un relé posiblemente energizado por un
        proceso que se está muriendo.
        """
        try:
            with self._lock:
                self._apagar_hardware_locked()
        except Exception:
            log.critical(  # noqa: TRY400 — el stacktrace va en exc_info; el titular es este
                "gpio: el arranque falló y el rescate a estado seguro TAMPOCO pudo "
                "completarse. Puede quedar algún relé energizado por un proceso que "
                "ya no existe: revisa físicamente sirena, gas, ascensores y puertas.",
                exc_info=True,
            )

    def _apagar_hardware_locked(self) -> None:
        """De-energiza TODO y cierra los dispositivos. **Llamar con `_lock` tomado.**

        Compartido por la parada limpia (`_on_stop`) y por el rescate del arranque
        fallido: eran el mismo trabajo escrito una sola vez, y el camino de
        arranque se quedó sin él.

        `drive_all_safe()` va PRIMERO y explícito. Cerrar un `DigitalOutputDevice`
        devuelve el pin a entrada, que en este cableado también de-energiza, pero
        apoyarse en eso sería apoyarse en un efecto colateral del backend: el
        estado seguro se ORDENA, no se hereda de un `close()`.
        """
        self.drive_all_safe()
        for device in (self._button, self._silence_button, self._test_button):
            if device is not None:
                device.close()
        for relay in self._relays.values():
            relay.close()
        self._relays.clear()
        self._energized.clear()
        self._button = self._silence_button = self._test_button = None

    def _arrancar_hardware(self) -> None:
        # [D1·auditoría 2026-08-08] EL PERFIL COMPLETO, ANTES DE ENERGIZAR NADA.
        # El bucle de abajo resolvía el modo relé a relé, así que un perfil al que
        # le faltara un canal que NO fuera el primero ya había energizado los
        # anteriores —`GAS_VALVE` incluido, que reposa ENERGIZADO— cuando tronaba.
        # De las dos salidas posibles se elige la fuerte: validar entero antes de
        # tocar hardware. La otra —de-energizar en la ruta de fallo— convierte un
        # `edge.env` mal tecleado en un ciclo REAL sobre contactores de gas,
        # ascensores y retenedores: las puertas se sueltan de verdad. Esto no
        # sustituye al rescate de `_on_start`, que sigue siendo la red para los
        # fallos que no se pueden prever leyendo la config (un pin ocupado, lgpio).
        modos = {canal: self._failsafe(canal) for canal in LOCAL_RELAY_CHANNELS}

        if self.settings.dev_mode:
            ensure_dev_pin_factory()
        else:
            ensure_prod_pin_factory()

        from gpiozero import Button, DigitalOutputDevice

        pins = self.settings.pins
        relay_pins = {
            ActuatorChannel.SIREN: pins.relay_siren,
            ActuatorChannel.STROBE: pins.relay_strobe,
            ActuatorChannel.GAS_VALVE: pins.relay_gas_valve,
            ActuatorChannel.ELEVATOR: pins.relay_elevator,
            ActuatorChannel.DOOR_RETAINER: pins.relay_door_retainer,
        }
        with self._lock:
            for channel, pin in relay_pins.items():
                # Estado inicial = operación normal por modo (NC/fail_close arrancan
                # energizados = reteniendo/abierto; NO arranca de-energizado = inactivo).
                # El modo ya está resuelto ARRIBA para los cinco canales: aquí no
                # puede aparecer una consulta que truene a mitad del bucle.
                initial = normal_energized(modos[channel])
                self._relays[channel] = DigitalOutputDevice(
                    pin, active_high=True, initial_value=initial
                )
                self._energized[channel] = initial

        # WR-1 dry-contact: cierre → LOW (pull-up). Debounce = presupuesto §4.3.
        bounce_s = self.debounce_s
        self._button = Button(pins.wr1_contact, pull_up=True, bounce_time=bounce_s)
        self._button.when_pressed = self._on_contact_closed
        self._button.when_released = self._on_contact_open

        # Botones locales: silencio (alterna) y prueba (self-test de sirena).
        self._silence_button = Button(pins.silence_button, pull_up=True, bounce_time=bounce_s)
        self._silence_button.when_pressed = self._on_silence_button
        self._test_button = Button(pins.test_button, pull_up=True, bounce_time=bounce_s)
        self._test_button.when_pressed = self._on_test_button
        # [T-2.70.a·D3] La semilla de SPOF-02 ya NO va aquí: la invoca `_on_start`
        # DESPUÉS de abrir la puerta de servicio, para que el episodio nazca con
        # `episode_id` y el traspaso hardware→software cruce hasta la nube con el
        # dueño en otro proceso. La razón larga está en `_on_start`.

    # --- [D2/P2] La puerta de servicio del dueño ---
    @property
    def servidor_de_pines(self):  # noqa: ANN201 — PinLinkServer | None (import perezoso)
        """El servidor si está atado, o `None` si no pudo/no debe estarlo."""
        return self._servidor_de_pines

    def arrancar_servidor_de_pines(self) -> None:
        """Abre el socket del transporte. **Hilo NO crítico: jamás tumba el reflejo.**

        Es lo que hace este paso desplegable sin riesgo. Un socket que no se puede
        atar —directorio ausente, ruta demasiado larga para `AF_UNIX`, permisos,
        un dueño anterior VIVO— deja al gabinete exactamente como está hoy:
        protegiendo, con `takab-edge` hablándole a su `GpioController` por la
        costura LOCAL. Lo único que se pierde es la puerta de servicio, y eso se
        grita en el journal en vez de callarse.

        El import es PEREZOSO y a propósito: mantiene el grafo de `takab_edge.gpio`
        libre de sorpresas para quien lo lea, aunque `pinlink` no añada ninguna
        dependencia nueva y la allowlist de D1.3 lo vigile de todos modos.
        """
        if not getattr(self.settings, "gpio_serves_pins", False):
            log.info(
                "gpio: puerta de servicio CERRADA (GPIO_LINK=%s, GPIO_SERVE_ENABLED=%s). "
                "Se abre sola con GPIO_LINK=ipc; el proceso dedicado `takab-gpio` "
                "sirve siempre.",
                getattr(self.settings, "gpio_link", "?"),
                getattr(self.settings, "gpio_serve_enabled", "?"),
            )
            return
        try:
            from takab_edge.pinlink.server import PinLinkServer

            self._asegurar_directorio_del_socket()
            if self._servidor_de_pines is None:
                self._servidor_de_pines = PinLinkServer(self, self.settings.gpio_socket_file)
            self._servidor_de_pines.start()
        except Exception as exc:  # noqa: BLE001 — NO crítico por diseño
            self._servidor_de_pines = None
            log.error(  # noqa: TRY400 — el stacktrace va en el exc_info, el titular no
                "gpio: la puerta de servicio NO se pudo abrir (%s). El gabinete "
                "sigue protegiendo y el reflejo SASMEX→sirena es intocado; lo que "
                "no habrá es lectura ni actuación posterior desde otro proceso.",
                exc,
                exc_info=True,
            )

    def _asegurar_directorio_del_socket(self) -> None:
        """[T-2.70.a · M13] El 0700 del directorio del socket, IMPUESTO.

        `Path.mkdir(mode=0o700, exist_ok=True)` sólo aplica el modo cuando CREA:
        un directorio preexistente con 0755 —un despliegue viejo, un `mkdir -p` a
        mano, otro `umask`— se quedaba en 0755 y nadie lo decía. El aislamiento
        del socket son DOS capas (directorio + `SO_PEERCRED`) y la primera tiene
        que valer lo que dice; con `SO_PEERCRED` intacto, el fallo es de defensa
        en profundidad y no de acceso, pero es un `chmod`.

        Vive en el DUEÑO y no en el servidor a propósito: así cubre a los dos
        dueños posibles —`takab-gpio` y el `takab-edge` de la etapa intermedia—
        sin tocar el transporte. Nunca lanza: la puerta de servicio no es crítica
        y un `chmod` que no se pueda hacer (directorio de otro usuario) lo decide
        el `bind` de después, no esto.
        """
        directorio = Path(self.settings.gpio_socket_file).parent
        try:
            directorio.mkdir(parents=True, exist_ok=True, mode=0o700)
            directorio.chmod(0o700)
        except OSError as exc:
            log.warning(
                "gpio: no se pudo imponer 0700 sobre %s (%s); el aislamiento del "
                "socket queda sólo en `SO_PEERCRED`",
                directorio,
                exc,
            )

    def detener_servidor_de_pines(self) -> None:
        """Cierra la puerta de servicio. Idempotente y nunca lanza."""
        servidor, self._servidor_de_pines = self._servidor_de_pines, None
        if servidor is None:
            return
        try:
            servidor.stop()
        except Exception:  # noqa: BLE001 — parar la puerta jamás impide parar los pines
            log.warning("gpio: la puerta de servicio no cerró limpio", exc_info=True)

    def _seed_from_held_contact(self) -> None:
        """Siembra el reflejo si el contacto de alerta ya está cerrado al arrancar (SPOF-02).

        Tras un reinicio del Pi durante un evento con contacto latcheado NO habrá un flanco
        nuevo, así que leemos el NIVEL del contacto para no dejar la sirena muda en el
        traspaso HW→software. Dirección segura: sonar (el operador puede silenciar).
        """
        if self._button is not None and self._button.is_pressed:
            self._dispatch_sasmex(active=True, is_test=False)

    def _on_stop(self) -> None:
        # PRIMERO la puerta de servicio, y FUERA del lock. Antes, porque a partir
        # de aquí el gabinete va a estado seguro y cerrar dispositivos: un cliente
        # comandando a media parada escribiría sobre relés que ya se están
        # cerrando. Fuera del lock, porque parar el servidor JOINea hilos que
        # pueden estar dentro de `snapshot()` esperando ese mismo lock.
        self.detener_servidor_de_pines()
        try:
            with self._lock:
                for attr in ("_test_timer", "_actuation_test_timer"):
                    timer = getattr(self, attr)
                    if timer is not None:
                        timer.cancel()
                        setattr(self, attr, None)
                # Parada limpia → todo a estado seguro (de-energizado) antes de soltar
                # pines. Es el MISMO trabajo que el rescate del arranque fallido, y
                # por eso vive en un solo sitio: el camino de arranque se quedó sin
                # él precisamente porque estaba escrito sólo aquí.
                self._apagar_hardware_locked()
        finally:
            # [D1.1] DESPUÉS del bucle de `close()`, y en `finally`. Soltar el
            # cerrojo antes abriría una ventana en la que el proceso entrante
            # puede reclamar unos pines que éste todavía sostiene abiertos; no
            # soltarlo ante una excepción del cierre dejaría el gabinete sin
            # poder sucederse a sí mismo.
            self._release_pin_ownership()

    # --- Reflejo (camino de vida, in-process, con latencia medida) ---
    def _on_contact_closed(self) -> None:
        self._dispatch_sasmex(active=True, is_test=False)

    def _on_contact_open(self) -> None:
        self._dispatch_sasmex(active=False, is_test=False)

    def simulate_sasmex(self, active: bool, is_test: bool = False) -> SasmexSignal:
        """Entrada determinista equivalente a ``when_pressed`` (tests/simulador)."""
        return self._dispatch_sasmex(active=active, is_test=is_test)

    def _dispatch_sasmex(self, *, active: bool, is_test: bool) -> SasmexSignal:
        signal = SasmexSignal(active=active, is_test=is_test)
        with self._lock:
            # El pulso de prueba de CIRES NO actúa (SPOF-03: sólo heartbeat).
            # La apertura del contacto (active=False) NO desenclava: la alerta persiste
            # hasta que el operador silencie/re-arme (semántica de latching real = gate #3).
            if active and not is_test:
                started = perf_counter()
                # Una alarma NUEVA (flanco del contacto) siempre RE-SUENA (NFPA-72:
                # el silencio del operador acusa el episodio actual, no muta futuros).
                self._audible_silenced = False
                self._sasmex_latched = True
                for channel in REFLEX_CHANNELS:
                    self._apply(channel)
                self._last_reflex_latency_s = perf_counter() - started
                log.warning(
                    "REFLEJO SASMEX→sirena in-process (%.2f ms)",
                    self._last_reflex_latency_s * 1000.0,
                )
            callbacks = list(self._sasmex_callbacks)
        # Fuera del lock: pueden re-entrar (rules/cloud). Y AISLADOS uno a uno,
        # igual que `on_silence` desde siempre.
        #
        # [T-2.70.a·D2/P2] Iban sin `try`, y desde D2/P2 el callback #0 de esta
        # lista es `PinLinkServer._al_sasmex` —el dueño se suscribe a sí mismo
        # para servir su propia puerta—. Si ese primero lanzaba, los que vienen
        # detrás no llegaban a correr: `supervisor._on_sasmex` (que publica el
        # evento a la NUBE y abre incidente) y `drill.on_sasmex` (que aborta el
        # simulacro ante una alerta real). Un fallo del transporte apagando la
        # notificación de un sismo es exactamente lo que el hilo NO crítico
        # existe para impedir.
        for callback in callbacks:
            try:
                callback(signal)
            except Exception:  # noqa: BLE001 — un observer jamás corta a los demás
                log.exception("observer de SASMEX falló (aislado); los demás siguen")
        return signal

    # --- Botones locales ---
    def _on_silence_button(self) -> None:
        self.silence_audibles(not self._audible_silenced)

    def _on_test_button(self) -> None:
        self.run_siren_test()

    def run_siren_test(self, duration_s: float | None = None) -> None:
        """Self-test de sirena iniciado por el operador (suena aun si está silenciada).

        A diferencia del pulso de prueba de CIRES (heartbeat, no actúa), es una prueba
        deliberada. Se modela como una demanda aparte (`_siren_test_active`), así que su
        fin NUNCA apaga una alerta viva: sólo retira la demanda de prueba y recalcula.
        """
        duration = duration_s if duration_s is not None else self.settings.siren_test_duration_s
        with self._lock:
            self._siren_test_active = True
            self._apply(ActuatorChannel.SIREN)
            if self._test_timer is not None:
                self._test_timer.cancel()
            timer = threading.Timer(duration, self._end_siren_test)
            timer.daemon = True
            self._test_timer = timer
        timer.start()
        log.warning("self-test de sirena (%.1f s)", duration)

    def _end_siren_test(self) -> None:
        with self._lock:
            self._siren_test_active = False
            self._apply(ActuatorChannel.SIREN)  # vuelve al estado que exija la protección vigente

    def run_cabinet_self_test(
        self, pulse_s: float | None = None, gap_s: float | None = None
    ) -> dict:
        """Autodiagnóstico del gabinete (T-1.59/M-2): recorrido de relés NO audibles.

        Vive aquí — el dueño del modelo de demandas — porque es el ÚNICO lugar
        donde pulsar un relé no puede pisar una protección: se RECHAZA en seco si
        hay SASMEX enclavado, cualquier demanda de `rules` o estado seguro
        forzado, y el regreso de cada pulso es un ``_apply`` (el recálculo desde
        las demandas, respetando NO/NC/fail_close), jamás un estado recordado.
        La sirena NUNCA se energiza: solo se reporta su estado eléctrico.

        Devuelve ``{"ok", "reason", "relays": {canal: {pulsed, readback_ok,
        fail_safe, energized}}}`` — el readback compara ``relay.value`` de
        gpiozero contra el objetivo tras CADA transición (ida y regreso).
        """
        pulse = pulse_s if pulse_s is not None else self.settings.self_test_pulse_ms / 1000.0
        gap = gap_s if gap_s is not None else self.settings.self_test_gap_ms / 1000.0
        results: dict[str, dict] = {}
        for channel in LOCAL_RELAY_CHANNELS:
            mode = self._failsafe(channel)
            if channel in AUDIBLE_CHANNELS:
                # Solo LECTURA: un autodiagnóstico jamás hace sonar la sirena.
                state = self.relay_state(channel)
                results[channel.value] = {
                    "pulsed": False,
                    "readback_ok": True,
                    "fail_safe": mode.value,
                    "energized": state.energized,
                }
                continue
            with self._lock:
                if self._sasmex_latched or self._safed or any(self._rules_demand.values()):
                    return {
                        "ok": False,
                        "reason": "alerta o protección viva; self-test rechazado",
                        "relays": results,
                    }
                relay = self._relays.get(channel)
                if relay is None:
                    results[channel.value] = {
                        "pulsed": False,
                        "readback_ok": False,
                        "fail_safe": mode.value,
                        "energized": None,
                    }
                    continue
                # Ida: estado de protección DEL MODO (polaridad respetada)…
                target = active_energized(mode)
                relay.on() if target else relay.off()
                went_ok = bool(relay.value) == target
            time.sleep(pulse)  # fuera del lock: el reflejo SASMEX jamás espera al test
            with self._lock:
                # …regreso por RECÁLCULO: si una alerta llegó a media prueba, el
                # _apply materializa la protección vigente, no un estado viejo.
                self._apply(channel)
                back_ok = bool(relay.value) == self._energized[channel]
                energized = self._energized[channel]
            results[channel.value] = {
                "pulsed": True,
                "readback_ok": went_ok and back_ok,
                "fail_safe": mode.value,
                "energized": energized,
            }
            time.sleep(gap)
        failed = [c for c, r in results.items() if not r["readback_ok"]]
        ok = not failed
        reason = None if ok else f"readback falló en: {', '.join(failed)}"
        log.warning(
            "self-test de gabinete: %s (%s)",
            "OK" if ok else "FALLO",
            reason or f"{len(results)} relés verificados",
        )
        return {"ok": ok, "reason": reason, "relays": results}

    def run_local_actuation_test(
        self,
        hold_s: float | None = None,
        pulse_s: float | None = None,
        gap_s: float | None = None,
    ) -> dict:
        """Prueba LOCAL de actuación (T-1.67): ejercita el gabinete SIN alertar al sistema.

        Los canales del reflejo (sirena + estrobo) se SOSTIENEN unos segundos —para
        oírlos/verlos— mientras gas/ascensor/puertas hacen un PULSO breve con readback
        (verificar que responden sin cortar el gas ni retener el ascensor de verdad).

        A diferencia de una alerta real, es puramente in-process: NO invoca los
        callbacks SASMEX, así que NO llega a `rules`, NO publica a `takab/events` y
        NO abre incidente ni dispara la cascada de notificaciones. Se RECHAZA en seco
        si hay una alerta o protección viva, y una alerta real que llegue a media
        prueba GANA por recálculo (nunca compite con el camino de vida).

        Devuelve ``{"ok", "reason", "relays": {canal: {...}}}`` — los sostenidos con
        ``held``/``readback_ok``; los pulsados con ``pulsed``/``readback_ok`` (ida+regreso).
        """
        hold = hold_s if hold_s is not None else self.settings.actuation_test_hold_s
        pulse = pulse_s if pulse_s is not None else self.settings.self_test_pulse_ms / 1000.0
        gap = gap_s if gap_s is not None else self.settings.self_test_gap_ms / 1000.0
        results: dict[str, dict] = {}

        # 1) Guard + arranque del sostenimiento de sirena+estrobo (bajo lock).
        with self._lock:
            if self._sasmex_latched or self._safed or any(self._rules_demand.values()):
                return {
                    "ok": False,
                    "reason": "alerta o protección viva; prueba local rechazada",
                    "relays": {},
                }
            self._audible_silenced = False  # que la sirena suene de verdad
            self._actuation_test_active = True
            for channel in REFLEX_CHANNELS:
                self._apply(channel)
                relay = self._relays.get(channel)
                target = active_energized(self._failsafe(channel))
                results[channel.value] = {
                    "held": True,
                    "readback_ok": relay is not None and bool(relay.value) == target,
                    "fail_safe": self._failsafe(channel).value,
                    "energized": self._energized[channel],
                }
            if self._actuation_test_timer is not None:
                self._actuation_test_timer.cancel()
            timer = threading.Timer(hold, self._end_actuation_test)
            timer.daemon = True
            self._actuation_test_timer = timer
        timer.start()

        # 2) Pulso de verificación de los protectores (gas/ascensor/puertas), MISMO
        #    patrón que el self-test: ida a protección, readback, regreso por _apply.
        for channel in LOCAL_RELAY_CHANNELS:
            if channel in REFLEX_CHANNELS:
                continue  # sostenidos arriba, no se pulsan
            mode = self._failsafe(channel)
            with self._lock:
                if self._sasmex_latched or self._safed:
                    break  # alerta real a media prueba: se aborta el pulso (la real gana)
                relay = self._relays.get(channel)
                if relay is None:
                    results[channel.value] = {
                        "pulsed": False,
                        "readback_ok": False,
                        "fail_safe": mode.value,
                        "energized": None,
                    }
                    continue
                target = active_energized(mode)
                relay.on() if target else relay.off()
                went_ok = bool(relay.value) == target
            time.sleep(pulse)  # fuera del lock: el reflejo SASMEX jamás espera al test
            with self._lock:
                self._apply(channel)  # regreso por RECÁLCULO (respeta una alerta que haya llegado)
                back_ok = bool(relay.value) == self._energized[channel]
                energized = self._energized[channel]
            results[channel.value] = {
                "pulsed": True,
                "readback_ok": went_ok and back_ok,
                "fail_safe": mode.value,
                "energized": energized,
            }
            time.sleep(gap)

        failed = [c for c, r in results.items() if not r["readback_ok"]]
        ok = not failed
        reason = None if ok else f"readback falló en: {', '.join(failed)}"
        log.warning(
            "prueba local de actuación: %s (%s)",
            "OK" if ok else "FALLO",
            reason or f"{len(results)} canales — NO es alerta real",
        )
        return {"ok": ok, "reason": reason, "relays": results}

    def _end_actuation_test(self) -> None:
        """Fin del sostenimiento de la prueba local: recalcula sirena+estrobo.

        Si una alerta real llegó durante la prueba, el recálculo la respeta (los
        canales siguen energizados); sin alerta, vuelven a reposo.
        """
        with self._lock:
            self._actuation_test_active = False
            for channel in REFLEX_CHANNELS:
                self._apply(channel)

    # --- Relés: demandas de `rules` (capa lógica) + recálculo (capa eléctrica) ---
    def activate(self, channel: ActuatorChannel) -> None:
        """Ordena la PROTECCIÓN (emergencia) del canal desde `rules`/`actuators`."""
        with self._lock:
            self._activate_locked(channel)

    def _activate_locked(self, channel: ActuatorChannel) -> None:
        # Una orden NUEVA de alarma audible (flanco de la demanda de rules) re-suena,
        # aun si el operador silenció un episodio anterior (§4.5 instrumental; NFPA-72).
        # La semántica de episodio para alertas rules sostenidas se afina en T-1.8.
        if channel in AUDIBLE_CHANNELS and not self._rules_demand.get(channel, False):
            self._audible_silenced = False
        self._rules_demand[channel] = True
        self._apply(channel)

    def deactivate(self, channel: ActuatorChannel) -> None:
        """Retira la orden de protección de `rules` (vuelve a normal si nadie más la exige)."""
        with self._lock:
            self._deactivate_locked(channel)

    def _deactivate_locked(self, channel: ActuatorChannel) -> None:
        self._rules_demand[channel] = False
        self._apply(channel)

    def set_relay(self, channel: ActuatorChannel, on: bool) -> None:
        """Comanda un canal (usado por `actuators`/`rules`): on=activar la protección."""
        with self._lock:
            self._set_relay_locked(channel, on)

    def _set_relay_locked(self, channel: ActuatorChannel, on: bool) -> None:
        if channel not in self._energized:
            raise KeyError(f"canal de relé desconocido: {channel}")
        self._activate_locked(channel) if on else self._deactivate_locked(channel)

    def apply_demands(
        self, demands: Sequence[tuple[ActuatorChannel, bool]]
    ) -> list[ChannelOutcome]:
        """[T-2.70.a·D2/P1] La secuencia de tier ENTERA, bajo UNA sola toma del lock.

        Hoy `ActuatorManager` llama a `set_relay` canal a canal y cada llamada toma
        el lock por su cuenta: cinco ventanas en las que el resultado físico se
        decide en cinco sitios que pueden intercalarse entre sí. Aquí se decide en
        uno. En memoria la diferencia es sutil; con un socket detrás son cinco
        round-trips que ninguna capa de arriba puede volver a juntar.

        Aislamiento POR CANAL, que es el que `ActuatorManager` ya tenía: un canal
        que lanza no aborta el lote — devuelve su :class:`ChannelOutcome` fallido y
        el resto se aplica igual. Un lote todo-o-nada dejaría el gas, el ascensor y
        las puertas sin comandar por culpa de un canal desconocido.

        NO respeta `_safed` ni ninguna otra regla por su cuenta: delega en
        `_set_relay_locked` → `_apply`, o sea el MISMO recálculo desde demandas de
        siempre (polaridad NO/NC/fail_close incluida).
        """
        resultados: list[ChannelOutcome] = []
        with self._lock:
            for channel, on in demands:
                try:
                    self._set_relay_locked(channel, on)
                except Exception as exc:  # noqa: BLE001 — vida: nunca abortar el resto del lote
                    log.warning("canal %s no se pudo comandar en el lote: %s", channel, exc)
                    resultados.append(
                        ChannelOutcome(channel=channel, ok=False, detail=f"excepción: {exc}")
                    )
                else:
                    resultados.append(ChannelOutcome(channel=channel, ok=True, detail="relay"))
        return resultados

    def snapshot(self) -> GpioSnapshot:
        """[T-2.70.a·D2/P1] TODO el estado del gabinete, bajo UNA sola toma del lock.

        Los consumidores leían propiedad a propiedad —`sasmex_active`,
        `siren_sounding`, `siren_reason`, `audible_silenced`, `alert_latched`,
        `relay_states()`…— y cada lectura tomaba el lock por separado. Entre dos de
        ellas cabe un cambio de demanda, así que el panel podía pintar un enclave
        vivo con la sirena en reposo: una incoherencia que no existe en el gabinete
        y que el operador leería como avería. Con un socket detrás son además dos
        respuestas de dos momentos distintos.

        `running` se lee DENTRO del lock a propósito: `_on_stop` vacía `_relays` y
        `_energized` bajo el mismo lock, así que «detenido» y «lista vacía» salen
        del mismo instante y no de dos.
        """
        with self._lock:
            ahora = time.monotonic()
            return GpioSnapshot(
                running=self.running,
                sasmex_active=self._sasmex_latched,
                siren_sounding=self._siren_sounding_locked(),
                siren_reason=self._siren_reason_locked(),
                audible_silenced=self._audible_silenced,
                alert_latched=self._sasmex_latched or any(self._rules_demand.values()),
                actuation_test_active=self._actuation_test_active,
                test_mode_active=ahora < self._test_mode_until,
                test_mode_remaining_s=max(0.0, self._test_mode_until - ahora),
                last_reflex_latency_s=self._last_reflex_latency_s,
                relays=tuple(self._relay_states_locked()),
            )

    def drive_all_safe(self) -> None:
        """Estado seguro DURABLE: de-energiza todo (corte de energía) hasta `reset()`.

        Fija `_safed`, así que un `_apply` posterior NO revierte el estado seguro
        (p.ej. no reabre el gas). Sólo un `reset()` explícito vuelve a operación normal.
        """
        with self._lock:
            self._safed = True
            for channel in LOCAL_RELAY_CHANNELS:
                self._apply(channel)

    def reset(self) -> None:
        """Vuelve a operación normal idle: limpia alerta, silencio, prueba, demandas y safe."""
        with self._lock:
            self._sasmex_latched = False
            self._audible_silenced = False
            self._siren_test_active = False
            self._actuation_test_active = False
            self._safed = False
            self._rules_demand.clear()
            for attr in ("_test_timer", "_actuation_test_timer"):
                timer = getattr(self, attr)
                if timer is not None:
                    timer.cancel()
                    setattr(self, attr, None)
            for channel in LOCAL_RELAY_CHANNELS:
                self._apply(channel)

    def _alert_demand(self, channel: ActuatorChannel) -> bool:
        """¿Alguna alerta (reflejo SASMEX enclavado o `rules`) exige proteger el canal?"""
        reflex = self._sasmex_latched and channel in REFLEX_CHANNELS
        return reflex or self._rules_demand.get(channel, False)

    def _desired_energized(self, channel: ActuatorChannel) -> bool:
        """Estado eléctrico objetivo del canal según sus demandas (bajo lock)."""
        if self._safed:
            return False  # estado seguro forzado: todo de-energizado hasta reset()
        demand = self._alert_demand(channel)
        # La prueba local (T-1.67) SOSTIENE los canales del reflejo (sirena+estrobo);
        # es una demanda más, así que una alerta real que llegue a media prueba se
        # SUMA (jamás baja la protección) y el fin de la prueba NUNCA calla lo que
        # una alerta viva exige (mismo modelo que el self-test de sirena).
        test_hold = self._actuation_test_active and channel in REFLEX_CHANNELS
        if channel in AUDIBLE_CHANNELS:
            protective = (
                (demand and not self._audible_silenced) or self._siren_test_active or test_hold
            )
        else:
            protective = demand or test_hold  # visuales/fail-safe: el silencio no los toca
        mode = self._failsafe(channel)
        return active_energized(mode) if protective else normal_energized(mode)

    def _apply(self, channel: ActuatorChannel) -> None:
        """Recalcula y aplica el estado eléctrico del canal (llamar bajo `_lock`)."""
        target = self._desired_energized(channel)
        relay = self._relays.get(channel)
        if relay is not None:
            relay.on() if target else relay.off()
        self._energized[channel] = target

    def _failsafe(self, channel: ActuatorChannel) -> FailSafeMode:
        """Modo fail-safe DECLARADO del canal. Sin default silencioso para relés.

        [T-2.70.a·D1.2] Aquí vivía `.get(channel, NORMALLY_OPEN)`, y ese default
        NO era benigno: para `GAS_VALVE` (FAIL_CLOSE) y `DOOR_RETAINER`
        (NORMALLY_CLOSED) **invierte los dos extremos del canal** — el nivel de
        reposo y el de protección. Un mapa `failsafe` al que le faltara una clave
        (edge.env mal provisionado, o el doc firmado del config sync, que es un
        `EdgeSettings` entero) dejaba la válvula de gas al revés en reposo y la
        comandaba al revés ante una alerta real, en silencio y con la suite en
        verde. Medido en `tests/test_gpio.py::test_el_default_de_failsafe_
        invertia_el_gas_y_ahora_truena`.

        El gate es sobre canales **de relé**, NO sobre «canal desconocido»:
        `ActuatorChannel.SYSTEM` es un canal LÓGICO (self_test / drill_start del
        dispatcher firmado) que por diseño jamás entra en `LOCAL_RELAY_CHANNELS`
        ni tiene entrada en `DEFAULT_FAILSAFE`, y para él `NORMALLY_OPEN` es el
        modo inocuo correcto: no gobierna ningún relé, así que no hay polaridad
        que invertir.

        CORRECCIÓN de la justificación que había aquí, que era falsa: decía que
        tronar ante cualquier miembro del enum «convertiría en avería consultas
        legítimas que llegan desde FUERA (payload de un comando de nube)», y ese
        camino NO EXISTE. Un comando firmado con `channel=system` lo resuelve
        `dispatch` antes de tocar `gpio`: `self_test`/`drill_*` van a
        `_run_self_test`/`_drill`, que sólo recorren `LOCAL_RELAY_CHANNELS`, y
        cualquier otra acción sobre `system` se rechaza con ack («canal system
        solo admite self_test»); además `set_relay` levanta `KeyError` antes de
        consultar el modo. Lo que este `return` sostiene es otra cosa: que
        `_failsafe` siga siendo TOTAL sobre el enum para los caminos de LECTURA
        (`relay_state`, `is_activated`) y para el próximo canal lógico que se
        declare, sin obligar a inventarle una polaridad a algo que no toca
        hardware. El gate vive donde el defecto es FÍSICO, y sólo ahí.
        """
        mode = self.settings.failsafe.get(channel)
        if mode is not None:
            return mode
        if channel in LOCAL_RELAY_CHANNELS:
            raise UndeclaredFailSafeError(
                f"canal de relé sin modo fail-safe declarado: {channel.value}. "
                f"El perfil `failsafe` de este gabinete declara "
                f"{sorted(c.value for c in self.settings.failsafe)} y le falta "
                f"{channel.value}. NO se elige un default: para FAIL_CLOSE/"
                "NORMALLY_CLOSED eso INVIERTE la polaridad de reposo y la de "
                "protección (gas y retenedores de puerta reposan ENERGIZADOS). "
                "Declara el modo en /etc/takab/edge.env (TAKAB_EDGE_FAILSAFE)."
            )
        return FailSafeMode.NORMALLY_OPEN

    def is_activated(self, channel: ActuatorChannel) -> bool:
        """True si el canal está en su estado de protección (agnóstico de polaridad)."""
        with self._lock:
            return self._energized[channel] == active_energized(self._failsafe(channel))

    def relay_state(self, channel: ActuatorChannel) -> RelayState:
        with self._lock:
            energized = self._energized[channel]
            return RelayState(
                channel=channel,
                energized=energized,
                activated=energized == active_energized(self._failsafe(channel)),
                fail_safe=self._failsafe(channel),
            )

    def relay_states(self) -> list[RelayState]:
        """Estado de los relés VIVOS, bajo un solo lock (seguro durante el shutdown).

        `_on_stop` vacía `_relays`/`_energized`, pero los hilos HTTP del panel son
        daemon y pueden pedir un `status()` en esa ventana (pasó el 2026-07-30:
        KeyError ⇒ 500 al kiosco). Se itera el dict REAL en vez de indexar los 5
        canales esperados: módulo detenido ⇒ lista vacía — los dispositivos están
        cerrados y su estado eléctrico ya no se mide; inventar filas sería peor
        que no tener filas (regla de oro 7). El orden de inserción de `_on_start`
        preserva el orden canónico de LOCAL_RELAY_CHANNELS.
        """
        with self._lock:
            return self._relay_states_locked()

    def _relay_states_locked(self) -> list[RelayState]:
        return [
            RelayState(
                channel=channel,
                energized=energized,
                activated=energized == active_energized(self._failsafe(channel)),
                fail_safe=self._failsafe(channel),
            )
            for channel, energized in self._energized.items()
        ]

    @property
    def sasmex_active(self) -> bool:
        """Alerta SASMEX real asertada (enclavada) — NO derivada del estado del relé."""
        return self._sasmex_latched

    @property
    def alert_latched(self) -> bool:
        """¿Alguna demanda de ALERTA sigue enclavada (SASMEX o `rules`)? (T-2.26)

        Es el campo que decide en el panel si CERRAR ALERTA debe ofrecerse
        aunque el tier ya haya decaído a normal (el enclave es monótono por
        diseño: solo `reset()` lo suelta). Excluye a propósito las pruebas
        (no son alertas) y `_safed` (estado seguro durable, condición aparte).
        `any(values())` y no `bool(dict)`: `deactivate()` deja la llave en
        False sin borrarla.
        """
        with self._lock:
            return self._sasmex_latched or any(self._rules_demand.values())

    @property
    def siren_sounding(self) -> bool:
        """¿La sirena audible está sonando físicamente ahora mismo?"""
        with self._lock:
            return self._siren_sounding_locked()

    def _siren_sounding_locked(self) -> bool:
        energized = self._energized.get(ActuatorChannel.SIREN, False)
        return energized == active_energized(self._failsafe(ActuatorChannel.SIREN))

    @property
    def siren_reason(self) -> SirenReason | None:
        """[T-2.49] POR QUÉ suena la sirena, o ``None`` si no suena.

        Se DERIVA de los enclaves que ya deciden el estado eléctrico; no se lleva un
        estado paralelo que pudiera desincronizarse del relé (que es el que manda).

        La precedencia es la de la seguridad: una alerta real durante una prueba se
        reporta como ``ALERT``. Al revés —rotular de prueba una alerta viva— haría que
        el gabinete tranquilizara a un edificio que se está moviendo.
        """
        with self._lock:
            return self._siren_reason_locked()

    def _siren_reason_locked(self) -> SirenReason | None:
        if not self._siren_sounding_locked():
            return None
        if self._sasmex_latched or self._rules_demand.get(ActuatorChannel.SIREN, False):
            return SirenReason.ALERT
        if self._safed:
            return SirenReason.SAFE_STATE
        if self._siren_test_active or self._actuation_test_active:
            return SirenReason.TEST
        # Suena pero ninguna demanda conocida lo explica: es un estado que no
        # debería existir. Se reporta como ALERTA a propósito — ante la duda, el
        # sonido que NO minimiza lo que está pasando.
        log.warning("sirena sonando sin demanda conocida; se rotula como ALERTA")
        return SirenReason.ALERT
