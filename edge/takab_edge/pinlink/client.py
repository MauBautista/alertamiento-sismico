"""[T-2.70.a·D2/P2] `IpcGpioLink` — la costura por socket, CACHÉ-FIRST.

**Sin dependencias de terceros**: stdlib (`socket`, `threading`, `queue`, `json`
por el códec) más los contratos de este repo. No es «stdlib puro» al pie de la
letra —`takab_edge.contracts` y el códec son Pydantic— y decirlo así era una
exageración que la allowlist de D1.3 desmiente: lo que esa allowlist garantiza es
que el proceso mínimo no gana dependencias NUEVAS, no que no tenga ninguna.

La pieza clave del paso, y su porqué:

**El cliente NUNCA consulta al servidor para LEER.** Un hilo lector posee la
suscripción y mantiene la última instantánea; `snapshot()` la devuelve de memoria.
Las lecturas del gabinete ocurren en el hilo de SeedLink (`supervisor.
_modo_prueba_activo`, por cada paquete), en el watcher de sirena a 20 Hz
(`audio._reconcile_siren`) y en cada refresco del kiosco (~11 Hz): un round-trip
por lectura metería el transporte en tres caminos que hoy son un acceso a memoria,
y uno de ellos —el de SeedLink— disfraza cualquier excepción de «Shake caído».

**Y la instantánea declara su EDAD.** Una caché que no dice cuándo se llenó es un
dato congelado con la firma de un dato vivo: exactamente el defecto del 14-jul.
Pasado :data:`EDAD_MAXIMA_S`, la lectura deja de devolver estado y lanza
`GpioLinkUnavailable` — **fuera de plazo el dato NO EXISTE** (doctrina T-2.58), y
esa es justo la causa que los consumidores ya tratan desde D2/P1: `S/D` +
`gpio_unreachable` en el panel, `[]` en el latido, fail-cerrado en el voceo y en
el simulacro, fail-ABIERTO deliberado en el hilo de SeedLink.

**`critical = False`, y es una inversión deliberada.** `GpioController.critical`
es `True` porque para el DUEÑO «no puedo tocar los pines» debe ser un arranque
que truena. Heredarlo aquí significaría «el dueño no contesta ⇒ `takab-edge`
propaga el fallo ⇒ `Restart=always` ⇒ ciclo infinito», y con él se irían SeedLink,
la nube, el backfill, la evidencia y el panel — por una avería del transporte que
NO afecta al reflejo SASMEX→sirena, que vive del otro lado. El cliente degrada y
lo dice; el dueño truena.

Las escrituras (`apply`, `action`) SÍ cruzan siempre: son órdenes, y una orden
servida desde una caché no es una orden.

**Y los observadores NO corren en el hilo lector.** Corren en un hilo propio
(`pinlink-observadores`), y es la corrección que hace utilizable este transporte:
el observador `sasmex` que cablea el supervisor ACTÚA —`_act_and_publish` →
`RelayActuator` → `apply`—, y `apply` espera una respuesta que **sólo el hilo
lector puede leer**. Despacharlo en ese mismo hilo era un interbloqueo con
timeout garantizado en cada sismo: los cinco ACKs decían «la orden NO se puede
dar por ejecutada» mientras los relés SÍ se accionaban (el servidor ejecutó el
lote; el cliente nunca leyó la respuesta). Mentir en las dos direcciones a la vez
es lo peor que puede hacer un gabinete, y :class:`ReentradaDelHiloLector` está
para que, si alguien vuelve a meter una orden en el hilo lector, se sepa en 0 ms
en vez de en 2 s.
"""

from __future__ import annotations

import logging
import queue
import socket
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from takab_edge.contracts import ActuatorChannel, SasmexSignal
from takab_edge.gpio_link import (
    GPIO_ACTIONS,
    GPIO_EVENTS,
    ChannelOutcome,
    GpioActionNotAllowed,
    GpioEventNotAllowed,
    GpioLinkUnavailable,
    GpioSnapshot,
)
from takab_edge.module import EdgeModule
from takab_edge.pinlink import codec as cd

log = logging.getLogger("takab_edge.pinlink.client")

#: Plazo de la caché. Más allá de esto el estado del gabinete NO EXISTE.
#:
#: El servidor empuja al cambiar (sondeo 20 Hz) y, pase lo que pase, cada 0.5 s.
#: 2 s = cuatro keepalives perdidos seguidos: un pico de carga o una pausa de GC
#: en el Pi 4 no puede convertirse en «el gabinete no existe» para el panel,
#: pero un dueño que se calla sí tiene que dejar de sostener lecturas.
#:
#: Aguas abajo el efecto es acotado y conocido: el watcher de sirena calla el
#: altavoz tras 20 conciliaciones ilegibles seguidas (1 s a 20 Hz), o sea ~3 s
#: desde que el dueño enmudece — con la sirena de RELÉ, que es la primaria,
#: sosteniendo su enclave del otro lado todo el tiempo.
EDAD_MAXIMA_S = 2.0

#: Cuánto espera `start()` a la primera instantánea. No es fatal agotarlo: el
#: cliente arranca igual y las lecturas dicen «no existe» hasta que llegue.
ESPERA_INICIAL_S = 2.0

#: Un lote de relés es un lock y cinco escrituras: si tarda segundos, no es
#: lentitud, es un dueño atascado y el llamador necesita saberlo YA (está en la
#: secuencia de actuación).
TIMEOUT_APPLY_S = 2.0

#: Las acciones DUERMEN por diseño, pero no tanto como decía la premisa anterior.
#:
#: Decía «`actuation_test` sostiene sirena+estrobo `actuation_test_hold_s` (5 s de
#: fábrica)» y de ahí salían los 30 s. **Es falso**: ese sostenimiento va en un
#: `threading.Timer` (`gpio.run_actuation_test`) y NO bloquea la llamada. Lo que
#: bloquea de verdad son los bucles de pulsos, medidos con los ajustes de fábrica
#: (`self_test_pulse_ms=250`, `self_test_gap_ms=150`): `actuation_test` ~1.2 s y
#: `cabinet_self_test` ~1.6 s. 30 s eran ~19× el peor caso real.
#:
#: 5 s = ~3× el peor caso medido en x86-64, que es el margen que deja el Pi 4 ARM
#: (sin medir todavía — ficha de D2/P2) y sigue acotando a 5 s el daño de un dueño
#: atascado. Anclado por `test_el_plazo_de_las_acciones_sale_de_lo_que_TARDAN`,
#: que MIDE cada acción declarada en vez de creerse este comentario.
#:
#: Lo que este número NO arregla: mientras una acción cuelga, `snapshot()` sigue
#: FRESCO (lo refresca el hilo emisor del dueño) y sólo mueren los `apply` — y
#: `snapshot()` es justo lo que todos usan para decidir «¿está bien gpio?». Ese es
#: el bloqueo en cabeza de línea, fichado aparte en T-2.70.a.
TIMEOUT_ACTION_S = 5.0

#: Reintento de conexión: primer intento inmediato, backoff exponencial CAPADO.
#: El exponente va acotado a propósito (lección de `737dd73`: el hilo de
#: reconexión de `cloud` murió con `OverflowError` tras ~1024 intentos y el
#: gabinete se quedó mudo EN SILENCIO).
ESPERA_MINIMA_S = 0.05
ESPERA_MAXIMA_S = 5.0

#: Eventos del dueño esperando a los observadores. Acotada porque vive en el hilo
#: lector, que JAMÁS puede bloquearse: si se llena (256 eventos sin despachar =
#: un observador colgado) se grita y se descarta, porque parar el hilo lector
#: congelaría además la caché de TODO el gabinete.
BUZON_MAX = 256


class _Pendiente:
    """Una petición esperando respuesta, con su propio evento."""

    __slots__ = ("evento", "respuesta")

    def __init__(self) -> None:
        self.evento = threading.Event()
        self.respuesta: dict | None = None


#: Excepciones del dueño que el cliente vuelve a levantar TAL CUAL. Es una tabla
#: pequeña a propósito: solo lo que la tabla CERRADA de operaciones puede lanzar
#: y que algún llamador distingue. Lo demás llega como `GpioRemoteError`, que
#: conserva el nombre original en el mensaje — inventar la clase equivocada sería
#: peor que declarar honestamente que fue el otro lado.
_EXCEPCIONES: dict[str, type[BaseException]] = {
    "GpioActionNotAllowed": GpioActionNotAllowed,
    "GpioEventNotAllowed": GpioEventNotAllowed,
    "KeyError": KeyError,
    "ValueError": ValueError,
    "TypeError": TypeError,
}


class GpioRemoteError(RuntimeError):
    """El dueño de los pines contestó, y contestó que NO."""


class ReentradaDelHiloLector(GpioLinkUnavailable):
    """Alguien pidió una ORDEN desde el hilo que tiene que leer la respuesta.

    Es un interbloqueo, no una indisponibilidad, y por eso tiene nombre propio;
    hereda de `GpioLinkUnavailable` para que los consumidores que ya la tratan
    (todos) degraden igual en vez de propagar algo nuevo al camino de vida.

    Hoy no debería ocurrir jamás: los observadores corren en `pinlink-
    observadores`. Está para que el día que alguien vuelva a llamar a `apply()`
    desde `_servir` se sepa **en 0 ms y por su nombre**, en vez de en 2 s
    disfrazado de «el dueño de los pines no contestó».
    """


class IpcGpioLink(EdgeModule):
    """Costura `GpioLink` contra el dueño de los pines de OTRO proceso."""

    name = "gpio_link"
    #: El dueño arranca antes, cuando vive en este mismo proceso. Cuando D3 lo
    #: saque a `takab-gpio`, `gpio` no estará entre los módulos y `_toposort` lo
    #: ignora sin más — la dependencia deja de existir, no se rompe.
    depends_on = ("gpio",)
    #: Requisito 4 de D2/P2, explícito e invertido respecto del dueño. Ver el
    #: docstring del módulo: heredar `critical=True` convertiría una avería del
    #: transporte en un `takab-edge` reiniciándose en bucle.
    critical = False

    def __init__(
        self,
        settings: Any = None,
        *,
        ruta: str | None = None,
        edad_maxima_s: float = EDAD_MAXIMA_S,
        espera_inicial_s: float = ESPERA_INICIAL_S,
    ) -> None:
        super().__init__()
        if ruta is None:
            if settings is None:
                raise ValueError("IpcGpioLink necesita `settings` o `ruta`")
            ruta = settings.gpio_socket_file
        self.ruta = str(ruta)
        self._edad_maxima_s = edad_maxima_s
        self._espera_inicial_s = espera_inicial_s
        self._espera_maxima_s = ESPERA_MAXIMA_S
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._conectado = threading.Event()
        #: Se arma con la PRIMERA instantánea, no con la conexión: estar
        #: conectado y no tener estado son cosas distintas, y `start()` sólo
        #: puede decir «listo» de la segunda.
        self._hay_estado = threading.Event()
        #: (instantánea, monotónico de LLEGADA). La edad se mide aquí, no allá.
        self._cache: tuple[GpioSnapshot, float] | None = None
        self._episodio_entregado: str | None = None
        self._observadores: dict[str, list[Callable[..., None]]] = {e: [] for e in GPIO_EVENTS}
        self._pendientes: dict[int, _Pendiente] = {}
        self._siguiente_id = 0
        #: Los avisos a los observadores, para el hilo que SÍ puede bloquearse.
        self._buzon: queue.Queue[tuple[str, Any] | None] = queue.Queue(maxsize=BUZON_MAX)
        self._despachador: threading.Thread | None = None
        self.avisos_descartados = 0  # instrumento; no decide nada

    # ------------------------------------------------------------------ vida
    def _on_start(self) -> None:
        self._parar.clear()
        self._despachador = threading.Thread(
            target=self._despachar, name="pinlink-observadores", daemon=True
        )
        self._despachador.start()
        self._hilo = threading.Thread(target=self._bucle, name="pinlink-cliente", daemon=True)
        self._hilo.start()
        if not self._hay_estado.wait(self._espera_inicial_s):
            # NO es fatal, y la razón es el requisito 4: el cliente no puede
            # tumbar `takab-edge` porque el dueño tarde en levantar su socket.
            log.warning(
                "pinlink: el dueño de los pines no contestó en %.1fs (%s). El edge "
                "arranca igual y las lecturas dirán «no existe» hasta que conteste; "
                "el reflejo SASMEX→sirena vive del otro lado y no depende de esto.",
                self._espera_inicial_s,
                self.ruta,
            )

    def _on_stop(self) -> None:
        self._parar.set()
        with self._lock:
            sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        hilo, self._hilo = self._hilo, None
        if hilo is not None and hilo.is_alive():
            hilo.join(timeout=3.0)
        despachador, self._despachador = self._despachador, None
        if despachador is not None and despachador.is_alive():
            try:
                self._buzon.put_nowait(None)  # centinela: despierta y termina
            except queue.Full:
                pass
            despachador.join(timeout=3.0)
        while True:  # un `start()` posterior no puede heredar avisos de otra vida
            try:
                self._buzon.get_nowait()
            except queue.Empty:
                break
        self._conectado.clear()
        self._hay_estado.clear()
        self._cache = None
        for pendiente in list(self._pendientes.values()):
            pendiente.evento.set()

    def _espera_de_reintento(self, intento: int) -> float:
        """Backoff exponencial con el EXPONENTE capado (no solo el resultado).

        `2**intento` con `intento` grande no es «un número grande»: en Python es
        un entero de miles de dígitos, y el `float(...)` que venía después
        levantaba `OverflowError` dentro del hilo de reconexión — que moría, y
        con él la única vía de volver a hablar con el dueño de los pines.
        """
        exponente = min(max(intento, 0), 10)
        return min(self._espera_maxima_s, ESPERA_MINIMA_S * (2.0**exponente))

    # ------------------------------------------------------------ hilo lector
    def _bucle(self) -> None:
        """Conecta, sirve y reconecta. El backoff cuenta SESIONES, no `connect()`.

        Reseteaba `intento = 0` en cuanto `connect()` volvía, y en `AF_UNIX` el
        kernel completa el `connect` aunque el servidor cierre acto seguido: con
        el dueño rechazando por uid (`SO_PEERCRED`), cada vuelta era conectar,
        recibir `b""` y volver a empezar tras `ESPERA_MINIMA_S`. Medido: **20.6
        reconexiones por segundo, indefinidamente**, con el journal a ~62
        líneas/s. El backoff existía y no enganchaba nunca.

        Ahora sólo una sesión que SIRVIÓ ALGO (al menos un mensaje del dueño)
        cuenta como éxito. El cap del exponente sigue donde estaba — lección de
        `737dd73`, ver :meth:`_espera_de_reintento`.
        """
        intento = 0
        while not self._parar.is_set():
            try:
                self._conectar()
            except OSError as exc:
                if intento == 0 or intento % 20 == 0:
                    log.warning(
                        "pinlink: el dueño de los pines no contesta en %s (%s)", self.ruta, exc
                    )
                if self._parar.wait(self._espera_de_reintento(intento)):
                    return
                intento += 1
                continue
            sirvio = False
            try:
                sirvio = self._servir()
            except Exception:  # noqa: BLE001 — el hilo lector NUNCA muere por un mensaje
                log.warning("pinlink: enlace con el dueño de los pines interrumpido", exc_info=True)
            finally:
                self._desconectar()
            if sirvio:
                intento = 0
            else:
                if intento == 0 or intento % 20 == 0:
                    log.warning(
                        "pinlink: el dueño de los pines acepta y cuelga sin decir nada en %s "
                        "(¿uid rechazado?); se reintenta con backoff, no en bucle cerrado",
                        self.ruta,
                    )
                intento += 1
            if self._parar.wait(ESPERA_MINIMA_S if sirvio else self._espera_de_reintento(intento)):
                return

    def _conectar(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(self.ruta)
        sock.settimeout(None)
        with self._lock:
            self._sock = sock
            self._cache = None  # el estado de ANTES de la caída no es el de ahora
        # La suscripción la pide el HILO LECTOR, que es su dueño: así hay
        # exactamente un flujo de empujes y un solo sitio que lo consume.
        eventos = sorted(GPIO_EVENTS)
        sock.sendall(cd.enmarcar({"id": self._nuevo_id(), "op": "subscribe", "events": eventos}))
        self._conectado.set()
        log.info("pinlink: suscrito al dueño de los pines en %s", self.ruta)

    def _desconectar(self) -> None:
        self._conectado.clear()
        self._hay_estado.clear()
        with self._lock:
            sock, self._sock = self._sock, None
            self._cache = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        for pendiente in list(self._pendientes.values()):
            pendiente.evento.set()

    def _servir(self) -> bool:
        """Consume el flujo del dueño. Devuelve si la sesión SIRVIÓ algún mensaje."""
        desenmarcador = cd.Desenmarcador()
        servidos = 0
        while not self._parar.is_set():
            sock = self._sock
            if sock is None:
                return servidos > 0
            datos = sock.recv(65536)
            if not datos:
                return servidos > 0
            for mensaje in desenmarcador.alimentar(datos):
                servidos += 1
                self._encajar(mensaje)
        return servidos > 0

    def _encajar(self, mensaje: dict) -> None:
        empuje = mensaje.get("push")
        if empuje == "snapshot":
            self._guardar(mensaje.get("snapshot") or {}, mensaje.get("episode_id"))
            return
        if empuje == "event":
            self._al_evento(mensaje)
            return
        ident = mensaje.get("id")
        pendiente = self._pendientes.get(ident) if isinstance(ident, int) else None
        if pendiente is None:
            return  # respuesta de una petición que ya expiró: se descarta en silencio
        pendiente.respuesta = mensaje
        pendiente.evento.set()

    def _guardar(self, crudo: dict, episodio: Any) -> None:
        try:
            snap = cd.instantanea_desde_json(crudo, edad_s=0.0)
        except cd.ProtocolError:
            log.warning("pinlink: instantánea ilegible del dueño de los pines", exc_info=True)
            return
        with self._lock:
            self._cache = (snap, time.monotonic())
        self._hay_estado.set()
        self._reconciliar_episodio(episodio, snap)

    def _reconciliar_episodio(self, episodio: Any, snap: GpioSnapshot) -> None:
        """Un episodio SASMEX que empezó con el enlace CAÍDO llega igual — una vez.

        Sin esto habría dos formas de equivocarse, y las dos son graves:

        * no sintetizar nada ⇒ un sismo que ocurre mientras el socket está caído
          NO abre incidente en la nube ni notifica a nadie, aunque el reflejo
          local sí haya sonado (vive del otro lado);
        * sintetizar por ESTADO (`sasmex_active`) ⇒ cada instantánea con el
          enclave puesto abre un incidente nuevo: veinte por segundo.

        La reconciliación es por `episode_id`, que el dueño acuña en el flanco de
        la alerta: se entrega la primera vez que se ve y nunca más. Es la misma
        idempotencia por nonce de la regla de oro 3, aplicada al transporte.
        """
        if not isinstance(episodio, str) or not episodio:
            return
        if episodio == self._episodio_entregado:
            return
        self._episodio_entregado = episodio
        if not snap.sasmex_active:
            return  # episodio ya cerrado: no hay nada que reabrir
        log.warning(
            "pinlink: episodio SASMEX %s reconciliado tras (re)conectar; se entrega "
            "UNA vez a los observadores (evita duplicar el incidente en la nube)",
            episodio,
        )
        self._avisar("sasmex", SasmexSignal(active=True, is_test=False))

    def _al_evento(self, mensaje: dict) -> None:
        evento = mensaje.get("event")
        if evento == "sasmex":
            episodio = mensaje.get("episode_id")
            if isinstance(episodio, str) and episodio:
                if episodio == self._episodio_entregado:
                    return  # ya reconciliado por instantánea: no se entrega dos veces
                self._episodio_entregado = episodio
            try:
                signal = SasmexSignal.model_validate(mensaje.get("signal") or {})
            except Exception:  # noqa: BLE001 — un evento ilegible no mata el hilo
                log.warning("pinlink: señal SASMEX ilegible", exc_info=True)
                return
            self._avisar("sasmex", signal)
            return
        if evento == "silence":
            self._avisar("silence", bool(mensaje.get("silenced")))

    def _avisar(self, evento: str, argumento: Any) -> None:
        """Encola el aviso. **Nunca invoca nada desde el hilo lector.**

        Es la corrección de fondo de D2/P2: `supervisor._on_sasmex` se registra
        aquí y ACTÚA (`_act_and_publish` → `apply`), y `apply` espera una
        respuesta que sólo el hilo lector puede leer. Invocarlo aquí era esperarse
        a uno mismo.
        """
        try:
            self._buzon.put_nowait((evento, argumento))
        except queue.Full:
            # No se bloquea NUNCA: parar el hilo lector congelaría la caché del
            # gabinete entero (panel a `S/D`, latido con relés vacíos). Se grita
            # y se descarta — con 256 avisos sin despachar el problema no es este
            # aviso, es el observador que lleva colgado desde hace rato.
            self.avisos_descartados += 1
            log.error(
                "pinlink: buzón de observadores LLENO (%d): se descarta un aviso de %r. "
                "Hay un observador colgado; el reflejo SASMEX→sirena vive del otro "
                "lado y sigue protegiendo.",
                BUZON_MAX,
                evento,
            )

    def _despachar(self) -> None:
        """Hilo propio de los observadores: el único sitio donde pueden bloquear.

        Uno solo y en FIFO a propósito: conserva el ORDEN de los eventos y el
        orden de registro dentro de cada uno, que es la conducta de
        `gpio._dispatch_sasmex` (la costura local) y de la que depende el
        gabinete.
        """
        while not self._parar.is_set():
            try:
                # Con `timeout` y no bloqueando para siempre: el centinela de
                # `_on_stop` se pierde si el buzón está LLENO, y un hilo que sólo
                # sabe morir por centinela se quedaría vivo justo en el caso que
                # el buzón acotado existe para sobrevivir.
                aviso = self._buzon.get(timeout=0.2)
            except queue.Empty:
                continue
            if aviso is None:
                return
            evento, argumento = aviso
            for callback in list(self._observadores.get(evento, ())):
                try:
                    callback(argumento)
                except Exception:  # noqa: BLE001 — mismo aislamiento que `gpio.on_silence`
                    log.exception("pinlink: observador de %s falló (aislado)", evento)

    # ------------------------------------------------------------- peticiones
    def _nuevo_id(self) -> int:
        with self._lock:
            self._siguiente_id += 1
            return self._siguiente_id

    def _pedir(self, mensaje: dict, timeout: float, *, esperar: bool = True) -> dict:
        """Una ida y vuelta por el socket. Las ESCRITURAS siempre cruzan."""
        if esperar and threading.current_thread() is self._hilo:
            # Cable trampa, no defensa: hoy los observadores corren en
            # `pinlink-observadores` y aquí no puede llegar nadie. Si vuelve a
            # llegar, que se sepa por su nombre y en 0 ms — el defecto original
            # se leía como «el dueño de los pines no contestó en 2.0s», que
            # apunta al dueño y el dueño estaba perfecto.
            raise ReentradaDelHiloLector(
                f"se pidió {mensaje.get('op')!r} DESDE el hilo lector del enlace: "
                "esa respuesta sólo puede leerla este mismo hilo, así que esperarla "
                "es un interbloqueo. Los observadores corren en «pinlink-observadores» "
                "justamente para poder cursar órdenes."
            )
        sock = self._sock
        if sock is None or not self._conectado.is_set():
            raise GpioLinkUnavailable(
                f"el dueño de los pines no contesta en {self.ruta}: no hay enlace "
                "para cursar la orden (el reflejo SASMEX→sirena vive del otro lado "
                "y sigue protegiendo)"
            )
        ident = self._nuevo_id()
        pendiente = _Pendiente()
        self._pendientes[ident] = pendiente
        try:
            try:
                sock.sendall(cd.enmarcar({**mensaje, "id": ident}))
            except OSError as exc:
                raise GpioLinkUnavailable(f"el dueño de los pines cortó el enlace: {exc}") from exc
            if not esperar:
                return {"id": ident, "ok": True, "result": None}
            if not pendiente.evento.wait(timeout):
                raise GpioLinkUnavailable(
                    f"el dueño de los pines no contestó a {mensaje.get('op')!r} en "
                    f"{timeout:.1f}s; la orden NO se puede dar por ejecutada"
                )
            if pendiente.respuesta is None:
                raise GpioLinkUnavailable(
                    "el enlace con el dueño de los pines se cayó a media orden"
                )
            return pendiente.respuesta
        finally:
            self._pendientes.pop(ident, None)

    def _resultado(self, respuesta: dict) -> Any:
        if respuesta.get("ok"):
            return respuesta.get("result")
        error = respuesta.get("error") or {}
        tipo, texto = error.get("type", "?"), error.get("message", "")
        clase = _EXCEPCIONES.get(tipo)
        if clase is not None:
            raise clase(texto)
        raise GpioRemoteError(f"el dueño de los pines rechazó la orden [{tipo}]: {texto}")

    # ------------------------------------------------- las cuatro operaciones
    def snapshot(self) -> GpioSnapshot:
        """La ÚLTIMA instantánea recibida, con su edad. Cero round-trips."""
        with self._lock:
            entrada = self._cache
        if entrada is None:
            raise GpioLinkUnavailable(
                f"todavía no hay ninguna instantánea del dueño de los pines ({self.ruta}). "
                "No se inventa un gabinete en reposo: un estado sin medir no existe."
            )
        snap, llegada = entrada
        edad = time.monotonic() - llegada
        if edad > self._edad_maxima_s:
            raise GpioLinkUnavailable(
                f"la última instantánea del gabinete tiene {edad:.1f}s y el plazo es "
                f"{self._edad_maxima_s:.1f}s: fuera de plazo el dato NO EXISTE, no se "
                "sirve viejo (el dueño de los pines lleva ese tiempo sin empujar)"
            )
        return GpioSnapshot(
            **{
                nombre: getattr(snap, nombre)
                for nombre in GpioSnapshot.__dataclass_fields__
                if nombre != "age_s"
            },
            age_s=edad,
        )

    def apply(self, demands: Sequence[tuple[ActuatorChannel, bool]]) -> tuple[ChannelOutcome, ...]:
        respuesta = self._pedir(
            {"op": "apply", "demands": [[ActuatorChannel(c).value, bool(v)] for c, v in demands]},
            TIMEOUT_APPLY_S,
        )
        crudos = self._resultado(respuesta) or []
        return tuple(cd.resultado_desde_json(r) for r in crudos)

    def action(self, name: str, **params: Any) -> Any:
        if name not in GPIO_ACTIONS:
            # Se rechaza EN EL CLIENTE además de en el servidor: un nombre que no
            # existe no merece un viaje, y el mensaje es el mismo de D2/P1.
            raise GpioActionNotAllowed(
                f"acción no admitida por la costura del gabinete: {name!r}. "
                f"Admitidas: {sorted(GPIO_ACTIONS)}. La lista es BLANCA a propósito: "
                "es lo que mantiene `drive_all_safe()` (estado seguro DURABLE) fuera "
                "del alcance de los consumidores."
            )
        respuesta = self._pedir({"op": "action", "name": name, "params": params}, TIMEOUT_ACTION_S)
        return self._resultado(respuesta)

    def subscribe(self, event: str, callback: Callable[..., None]) -> None:
        if event not in GPIO_EVENTS:
            raise GpioEventNotAllowed(
                f"evento no admitido por la costura del gabinete: {event!r}. "
                f"Admitidos: {sorted(GPIO_EVENTS)}."
            )
        self._observadores[event].append(callback)
