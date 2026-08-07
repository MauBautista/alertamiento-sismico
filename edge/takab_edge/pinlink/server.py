"""[T-2.70.a·D2/P2] El servidor que vive DENTRO del dueño de los pines.

**Sin dependencias de terceros**: stdlib más los contratos de este repo (ver la
nota del códec — el rótulo «stdlib puro» era literalmente falso).

Qué es y qué NO es:

* **Es** una puerta de servicio del proceso que ya sostiene los pines, para que
  el resto del edge pueda leer estado y pedir actuación POSTERIOR (gas, ascensor,
  puertas), simulacro y modo prueba sin instanciar un segundo `GpioController`.
* **No es** parte del camino de vida. El reflejo SASMEX→sirena vive entero dentro
  de `gpio._dispatch_sasmex` y no cruza esto (gate #6). Por eso el hilo es NO
  crítico: si no puede atar el socket, el gabinete arranca igual y sigue
  protegiendo — es lo que hace desplegable este paso sin riesgo.

Lo que estaba decidido antes de escribirlo, y no se re-decide aquí:

* **Solo el dueño (o root) habla por el socket.** Directorio propio 0700, socket
  0660 y `SO_PEERCRED` verificado en cada conexión. Ambos extremos ya corren como
  root en el gabinete y quien es root puede escribir `/dev/gpiochip0`: este socket
  **no ensancha el privilegio**, solo evita que lo use quien no debería.
* **Tabla de operaciones CERRADA**: cuatro operaciones y, dentro de `action`, la
  lista blanca `GPIO_ACTIONS` de D2/P1 — sin `drive_all_safe()`, que es estado
  seguro DURABLE y dejaría el gas cerrado hasta que alguien fuera al gabinete.
* **Sin HMAC**: firmar entre dos procesos root del mismo host no añade nada que
  el `SO_PEERCRED` no dé ya, y sí añade una clave que gestionar en el camino de
  vida.
* **Rate-limit** como cinturón contra un bucle de un cliente, no contra un
  atacante.

El empuje NUNCA bloquea al dueño: cada conexión tiene una cola acotada y un hilo
escritor propio. Un cliente que no drena se DESAHUCIA (se le cierra), porque la
alternativa —un `send()` bloqueante dentro del observador `sasmex`, que corre en
el hilo del reflejo justo después de energizar la sirena— es inaceptable.
"""

from __future__ import annotations

import logging
import os
import queue
import socket
import struct
import threading
import time
from pathlib import Path
from typing import Any

from takab_edge.contracts import ActuatorChannel, new_event_id
from takab_edge.gpio_link import (
    GPIO_ACTIONS,
    GPIO_EVENTS,
    GpioActionNotAllowed,
    GpioEventNotAllowed,
)
from takab_edge.pinlink import codec as cd

log = logging.getLogger("takab_edge.pinlink.server")

#: Cadencia del sondeo del emisor. 20 Hz = exactamente el watcher de sirena
#: (`audio._SIREN_POLL_S`), que es el consumidor más rápido: así ningún lector
#: pierde granularidad respecto de lo que ya tenía leyendo en memoria.
SONDEO_S = 0.05

#: Empuje aunque NADA cambie. Es la prueba de vida que permite al cliente
#: distinguir «quieto» de «mudo»: sin ella, un gabinete en reposo y un dueño
#: muerto se ven exactamente igual desde la caché. 10× el sondeo = 2 mensajes por
#: segundo, y cuatro oportunidades de llegar dentro del plazo del cliente.
KEEPALIVE_S = 0.5

#: Operaciones por segundo y conexión antes de frenar (token bucket con ráfaga
#: 2×). El panel es humano y la secuencia de tier entera es UN lote desde D2/P1:
#: 20/s es holgura de dos órdenes sobre el uso real y sigue cortando un bucle.
OPS_POR_S = 20

#: Mensajes encolados por conexión antes del desahucio. A 20 Hz son ~3 s de
#: atraso: un cliente que no drenó 64 mensajes no está lento, está muerto.
COLA_MAX = 64

#: Cada cuánto se puede quejar el rate-limit, POR CONEXIÓN. Una línea por
#: petición frenada son 417 líneas/s medidas: el cinturón que existe para
#: sobrevivir a un cliente desbocado ahogaba el journal donde se diagnostica ese
#: mismo cliente. Regla de oro 10 (registro por transición, no por intervalo), y
#: el mismo autolímite de ~1/s que `audio._reconcile_siren`.
AVISO_FRENADO_S = 1.0

#: Conexiones VIVAS a la vez. `listen(8)` es el backlog de aceptación, no una
#: cota: 200 clientes parqueados a media trama eran +400 hilos (lector+escritor)
#: dentro del proceso que toca la sirena, sostenidos indefinidamente. En el
#: gabinete el uso real es UNO (`takab-edge`) más algún `takab-gpioctl` de
#: diagnóstico; 16 son dos órdenes de holgura y siguen siendo una cota.
MAX_CONEXIONES = 16

#: Un cliente que abre, manda media trama y se calla no puede quedarse un hilo
#: para siempre. NO mata a un suscriptor ocioso —el flujo va del dueño al
#: cliente, y un cliente sano puede no volver a hablar nunca—: sólo se corta a
#: quien lleva este tiempo con un marco A MEDIAS o sin haber dicho nunca nada.
TIMEOUT_OCIOSO_S = 30.0

_TAM_UCRED = struct.calcsize("3i")


def notificar_systemd(estado: str) -> bool:
    """`sd_notify` sin dependencias. Devuelve si de verdad se avisó.

    Con `Type=notify`, `systemctl start` vuelve cuando el proceso dice `READY=1`
    — no cuando arrancó. Es la diferencia entre «el proceso existe» y «el proceso
    es DUEÑO de los pines», que es lo único que el traspaso de D3 puede aceptar
    como terminado.

    Sin `NOTIFY_SOCKET` (ejecución a mano, dev, `Type=simple`) es un no-op: el
    camino de vida no puede tronar por no tener systemd delante.
    """
    ruta = os.environ.get("NOTIFY_SOCKET", "")
    if not ruta:
        return False
    if ruta.startswith("@"):  # espacio de nombres abstracto de Linux
        ruta = "\0" + ruta[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(ruta)
            s.sendall(estado.encode("utf-8"))
    except OSError as exc:
        log.warning("sd_notify(%s) falló: %s", estado, exc)
        return False
    return True


class _Cubeta:
    """Token bucket monótono. Sin hilos: se rellena al consultarlo."""

    __slots__ = ("_capacidad", "_ritmo", "_fichas", "_ultimo")

    def __init__(self, ritmo: int) -> None:
        self._ritmo = float(max(1, ritmo))
        self._capacidad = self._ritmo * 2.0  # ráfaga: el arranque pide varias cosas de golpe
        self._fichas = self._capacidad
        self._ultimo = time.monotonic()

    def consumir(self) -> bool:
        ahora = time.monotonic()
        self._fichas = min(self._capacidad, self._fichas + (ahora - self._ultimo) * self._ritmo)
        self._ultimo = ahora
        if self._fichas < 1.0:
            return False
        self._fichas -= 1.0
        return True


class _Conexion:
    """Un cliente: hilo lector (peticiones) + hilo escritor (respuestas y empujes)."""

    def __init__(self, servidor: PinLinkServer, sock: socket.socket) -> None:
        self.servidor = servidor
        self.sock = sock
        self.suscrito: set[str] = set()
        self.cola: queue.Queue[bytes | None] = queue.Queue(maxsize=COLA_MAX)
        self.cubeta = _Cubeta(servidor.ops_por_s)
        self.viva = True
        #: Autolímite del aviso de rate-limit (ver :data:`AVISO_FRENADO_S`).
        self.frenadas = 0
        self._frenadas_avisadas = 0
        self._ultimo_aviso = 0.0
        #: ¿Llegó a completarse alguna trama? Lo usa el corte del ocioso.
        self._mensajes_recibidos = 0
        self._lector = threading.Thread(target=self._leer, name="pinlink-lector", daemon=True)
        self._escritor = threading.Thread(
            target=self._escribir, name="pinlink-escritor", daemon=True
        )

    def arrancar(self) -> None:
        self._escritor.start()
        self._lector.start()

    # --- salida ---
    def encolar(self, mensaje: dict, *, critico: bool) -> None:
        """Encola SIN bloquear jamás. Lleno ⇒ desahucio (nunca esperar al cliente).

        `critico` distingue lo que no se puede perder (respuestas y eventos) de
        lo que sí (una instantánea, porque en 50 ms viene otra más nueva). Aun
        así, una cola llena significa que el cliente no drena: eso es un
        desahucio en los dos casos, y el que se salva es el DUEÑO.
        """
        if not self.viva:
            return
        try:
            self.cola.put_nowait(cd.enmarcar(mensaje))
        except queue.Full:
            del critico  # la reacción es la misma; el parámetro documenta la intención
            self.servidor.desahucios += 1
            log.warning(
                "pinlink: cliente desahuciado — %d mensajes encolados sin drenar. El "
                "dueño de los pines JAMÁS espera a un cliente.",
                COLA_MAX,
            )
            self.cerrar()

    def _escribir(self) -> None:
        while True:
            dato = self.cola.get()
            if dato is None:
                return
            try:
                self.sock.sendall(dato)
            except OSError:
                self.cerrar()
                return

    def aviso_de_frenado(self) -> str | None:
        """Texto del aviso de rate-limit, o `None` si toca callar (~1/s).

        Una línea por petición frenada eran **417 líneas/s medidas**: el cinturón
        contra un cliente desbocado ahogaba el journal donde se diagnostica ese
        mismo cliente. Cuando vuelve a hablar, dice CUÁNTAS frenó mientras
        callaba — un contador es información; 417 líneas iguales, no.
        """
        self.frenadas += 1
        ahora = time.monotonic()
        if self._ultimo_aviso and (ahora - self._ultimo_aviso) < AVISO_FRENADO_S:
            return None
        silenciadas = self.frenadas - self._frenadas_avisadas - 1
        self._ultimo_aviso = ahora
        self._frenadas_avisadas = self.frenadas
        if silenciadas > 0:
            return f" (+{silenciadas} frenadas sin registrar en el último segundo)"
        return ""

    # --- entrada ---
    def _leer(self) -> None:
        desenmarcador = cd.Desenmarcador()
        ocioso = self.servidor.timeout_ocioso_s
        self.sock.settimeout(ocioso)
        try:
            while self.viva:
                try:
                    datos = self.sock.recv(65536)
                except TimeoutError:
                    if self._mensajes_recibidos and not desenmarcador.a_medias:
                        continue  # suscriptor sano y callado: el flujo va al revés
                    log.warning(
                        "pinlink: cliente OCIOSO cerrado tras %.0fs (%d mensajes, "
                        "%d bytes de marco a medias). `listen()` es backlog, no cota: "
                        "sin esto un cliente parqueado se queda dos hilos del proceso "
                        "que toca la sirena para siempre.",
                        ocioso,
                        self._mensajes_recibidos,
                        desenmarcador.a_medias,
                    )
                    return
                if not datos:
                    return
                for mensaje in desenmarcador.alimentar(datos):
                    self._mensajes_recibidos += 1
                    self.encolar(self.servidor.atender(self, mensaje), critico=True)
        except cd.ProtocolError as exc:
            log.warning("pinlink: cliente hablando otro protocolo (%s); se cierra", exc)
        except OSError:
            pass
        finally:
            self.cerrar()

    def cerrar(self) -> None:
        if not self.viva:
            return
        self.viva = False
        self.servidor.olvidar(self)
        try:
            self.cola.put_nowait(None)
        except queue.Full:
            pass
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class PinLinkServer:
    """Sirve las cuatro operaciones de la costura sobre un socket `AF_UNIX`."""

    def __init__(
        self,
        controlador: Any,
        ruta: str,
        *,
        uids_permitidos: frozenset[int] | None = None,
        sondeo_s: float = SONDEO_S,
        keepalive_s: float = KEEPALIVE_S,
        ops_por_s: int = OPS_POR_S,
        max_conexiones: int = MAX_CONEXIONES,
        timeout_ocioso_s: float = TIMEOUT_OCIOSO_S,
    ) -> None:
        self._gpio = controlador
        self.ruta = str(ruta)
        # En el gabinete dueño y cliente son root y esto es exactamente `{0}`.
        # Fuera del Pi (dev, demo, la suite) el dueño no es root y el conjunto es
        # `{0, uid del dueño}`: nadie más que quien sostiene los pines —o root—
        # puede hablar. No es una puerta de dev: es la MISMA regla escrita sin
        # suponer que el dueño siempre sea el 0.
        self.uids_permitidos = (
            frozenset({0, os.getuid()}) if uids_permitidos is None else frozenset(uids_permitidos)
        )
        self.ops_por_s = ops_por_s
        self.max_conexiones = max(1, int(max_conexiones))
        self.timeout_ocioso_s = float(timeout_ocioso_s)
        self._sondeo_s = sondeo_s
        self._keepalive_s = keepalive_s
        self._escucha: socket.socket | None = None
        self._aceptador: threading.Thread | None = None
        self._emisor: threading.Thread | None = None
        self._parar = threading.Event()
        self._lock = threading.Lock()
        self._conexiones: list[_Conexion] = []
        self._congelado = False
        #: Episodio SASMEX vivo. Lo que impide que una reconexión durante un
        #: sismo abra un incidente NUEVO del MISMO sismo en la nube.
        self._episodio: str | None = None
        self._observadores_puestos = False
        # Instrumentos (los leen los tests; ninguno decide nada aquí).
        self.peticiones_atendidas = 0
        self.instantaneas_empujadas = 0
        self.rechazos_por_uid = 0
        self.desahucios = 0
        self.frenadas = 0
        self.rechazos_por_cota = 0

    # ------------------------------------------------------------------ vida
    def start(self) -> None:
        escucha = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._preparar_ruta()
            escucha.bind(self.ruta)
        except OSError as exc:
            escucha.close()
            raise OSError(
                exc.errno,
                f"pinlink: no se pudo atar {self.ruta!r} ({exc}). AF_UNIX corta la "
                "ruta en ~108 bytes y el directorio tiene que existir y ser "
                "escribible por el dueño de los pines. Este servidor es NO "
                "crítico: el reflejo SASMEX→sirena vive igual sin él.",
            ) from exc
        os.chmod(self.ruta, 0o660)  # noqa: S103 — el aislamiento lo da el directorio 0700 + SO_PEERCRED
        escucha.listen(8)
        escucha.settimeout(0.2)
        self._escucha = escucha
        self._parar.clear()
        self._poner_observadores()
        self._aceptador = threading.Thread(target=self._aceptar, name="pinlink-accept", daemon=True)
        self._aceptador.start()
        log.info("pinlink: sirviendo el estado del gabinete en %s", self.ruta)

    def _preparar_ruta(self) -> None:
        ruta = Path(self.ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not ruta.exists():
            return
        # Un archivo de socket sobrevive a un SIGKILL del dueño. Antes de
        # quitarlo se comprueba que no haya NADIE VIVO detrás: robarle la ruta a
        # un dueño en marcha dejaría a sus clientes hablando con un socket que ya
        # no atiende nadie, sin que ni uno de los dos se entere.
        sonda = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sonda.settimeout(0.5)
        try:
            sonda.connect(self.ruta)
        except OSError:
            ruta.unlink(missing_ok=True)
        else:
            raise OSError(
                f"pinlink: {self.ruta} ya lo atiende alguien VIVO; este proceso no "
                "le roba la ruta. La propiedad la decide el cerrojo de pines "
                "(D1.1), y quien no lo tenga no debe estar sirviendo."
            )
        finally:
            sonda.close()

    def stop(self) -> None:
        self._parar.set()
        escucha, self._escucha = self._escucha, None
        if escucha is not None:
            try:
                escucha.close()
            except OSError:
                pass
        for hilo in (self._aceptador, self._emisor):
            if hilo is not None and hilo.is_alive():
                hilo.join(timeout=2.0)
        self._aceptador = self._emisor = None
        with self._lock:
            conexiones, self._conexiones = list(self._conexiones), []
        for conexion in conexiones:
            conexion.cerrar()
        try:
            Path(self.ruta).unlink(missing_ok=True)
        except OSError:  # el archivo no es el veredicto de nada; no vale tronar
            log.warning("pinlink: no se pudo retirar %s", self.ruta)

    @property
    def emisor_vivo(self) -> bool:
        emisor = self._emisor
        return emisor is not None and emisor.is_alive()

    def congelar_emision(self, congelado: bool) -> None:
        """Deja de empujar SIN cerrar nada — un dueño vivo pero mudo.

        Existe para poder medir qué hace la caché del cliente cuando envejece:
        es el único fallo que no se puede provocar matando el proceso, y es
        precisamente el que un cliente ingenuo no distingue de «todo en orden».
        """
        self._congelado = congelado

    # ------------------------------------------------------------- conexiones
    def _aceptar(self) -> None:
        while not self._parar.is_set():
            escucha = self._escucha
            if escucha is None:
                return
            try:
                sock, _ = escucha.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            if not self._par_autorizado(sock):
                sock.close()
                continue
            with self._lock:
                lleno = len(self._conexiones) >= self.max_conexiones
                if lleno:
                    self.rechazos_por_cota += 1
                else:
                    conexion = _Conexion(self, sock)
                    self._conexiones.append(conexion)
            if lleno:
                # `listen(8)` acota la COLA de aceptación, no las conexiones
                # vivas: sin esta cota, 200 clientes parqueados eran +400 hilos
                # dentro del proceso que toca la sirena.
                #
                # El aviso va autolimitado por la misma razón que el del
                # rate-limit: quien satura la cota está, por definición,
                # reintentando en bucle, y una línea por intento ahogaría el
                # journal donde se diagnostica (regla de oro 10).
                if self.rechazos_por_cota % 100 == 1:
                    log.warning(
                        "pinlink: conexión RECHAZADA — ya hay %d vivas (cota %d); "
                        "%d rechazos acumulados. El dueño de los pines no reparte "
                        "hilos sin límite.",
                        self.max_conexiones,
                        self.max_conexiones,
                        self.rechazos_por_cota,
                    )
                sock.close()
                continue
            conexion.arrancar()

    def _par_autorizado(self, sock: socket.socket) -> bool:
        """`SO_PEERCRED`: quién hay al otro lado, según el KERNEL."""
        if not hasattr(socket, "SO_PEERCRED"):
            # Fail-CLOSED: sin poder comprobar quién llama, no se contesta. Es la
            # misma dirección que el cerrojo de pines de D1.1.
            log.error("pinlink: esta plataforma no expone SO_PEERCRED; no se admite a nadie")
            return False
        try:
            crudo = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _TAM_UCRED)
            pid, uid, _gid = struct.unpack("3i", crudo)
        except OSError:
            log.exception("pinlink: no se pudo leer la credencial del par; se rechaza")
            return False
        if uid in self.uids_permitidos:
            return True
        self.rechazos_por_uid += 1
        log.warning(
            "pinlink: conexión RECHAZADA de uid=%s pid=%s — el estado y la actuación "
            "del gabinete solo se sirven al dueño de los pines (uids %s)",
            uid,
            pid,
            sorted(self.uids_permitidos),
        )
        return False

    def olvidar(self, conexion: _Conexion) -> None:
        with self._lock:
            if conexion in self._conexiones:
                self._conexiones.remove(conexion)

    def _suscriptores(self) -> list[_Conexion]:
        with self._lock:
            return [c for c in self._conexiones if c.suscrito and c.viva]

    # ------------------------------------------------------------ operaciones
    def atender(self, conexion: _Conexion, mensaje: dict) -> dict:
        """Ejecuta UNA petición de la tabla cerrada y devuelve su respuesta."""
        ident = mensaje.get("id")
        op = mensaje.get("op")
        if not conexion.cubeta.consumir():
            self.frenadas += 1
            aviso = conexion.aviso_de_frenado()
            if aviso is not None:
                log.warning(
                    "pinlink: cliente frenado por rate-limit (%s ops/s)%s", self.ops_por_s, aviso
                )
            return {
                "id": ident,
                "ok": False,
                "error": _error("RateLimited", "demasiadas peticiones"),
            }
        self.peticiones_atendidas += 1
        try:
            resultado = self._despachar(conexion, op, mensaje)
        except Exception as exc:  # noqa: BLE001 — el fallo VIAJA; jamás tumba al dueño
            log.warning("pinlink: la operación %r falló: %s", op, exc)
            return {"id": ident, "ok": False, "error": _error(type(exc).__name__, str(exc))}
        return {"id": ident, "ok": True, "result": resultado}

    def _despachar(self, conexion: _Conexion, op: Any, mensaje: dict) -> Any:
        if op == "snapshot":
            return cd.instantanea_a_json(self._gpio.snapshot())
        if op == "apply":
            demandas = [(ActuatorChannel(c), bool(v)) for c, v in mensaje.get("demands", [])]
            resultados = [cd.resultado_a_json(r) for r in self._gpio.apply_demands(demandas)]
            self._empujar_estado()  # leer-lo-propio-escrito: la caché ya es la nueva
            return resultados
        if op == "action":
            nombre = mensaje.get("name")
            metodo = GPIO_ACTIONS.get(nombre)
            if metodo is None:
                raise GpioActionNotAllowed(
                    f"acción no admitida por la costura del gabinete: {nombre!r}. "
                    f"Admitidas: {sorted(GPIO_ACTIONS)}. La lista es BLANCA a "
                    "propósito: es lo que mantiene `drive_all_safe()` (estado "
                    "seguro DURABLE) fuera del alcance de los clientes."
                )
            params = mensaje.get("params") or {}
            if not isinstance(params, dict):
                raise ProtocoloDeAccion(f"parámetros de {nombre!r} que no son un objeto")
            resultado = getattr(self._gpio, metodo)(**params)
            self._empujar_estado()
            return resultado
        if op == "subscribe":
            eventos = list(mensaje.get("events") or [])
            for evento in eventos:
                if evento not in GPIO_EVENTS:
                    raise GpioEventNotAllowed(
                        f"evento no admitido por la costura del gabinete: {evento!r}. "
                        f"Admitidos: {sorted(GPIO_EVENTS)}."
                    )
            conexion.suscrito.update(eventos)
            self._asegurar_emisor()
            snap = self._gpio.snapshot()
            conexion.encolar(self._sobre_estado(snap), critico=True)
            return {"episode_id": self._episodio}
        raise GpioActionNotAllowed(
            f"operación no admitida por el transporte de pines: {op!r}. La tabla es "
            f"CERRADA: {sorted(('snapshot', 'apply', 'action', 'subscribe'))}."
        )

    # ---------------------------------------------------------------- empujes
    def _sobre_estado(self, snap: Any) -> dict:
        return {
            "push": "snapshot",
            "snapshot": cd.instantanea_a_json(snap),
            "episode_id": self._episodio,
        }

    def _empujar_estado(self) -> None:
        suscriptores = self._suscriptores()
        if not suscriptores or self._congelado:
            return
        try:
            snap = self._gpio.snapshot()
        except Exception:  # noqa: BLE001 — el empuje JAMÁS tumba a quien lo llamó
            # Lo llama `_al_sasmex`, que corre en el hilo del REFLEJO justo
            # después de energizar la sirena, y también `_despachar` tras un
            # `apply`. Sin esta guarda, una lectura que reventara aquí se
            # propagaba al hilo del reflejo y se llevaba por delante a los
            # observadores que vienen detrás — la nube y el aborto del simulacro.
            # El emisor ya tenía esta misma guarda; esta era la que faltaba.
            log.exception("pinlink: no se pudo leer el estado del gabinete para empujarlo")
            return
        sobre = self._sobre_estado(snap)
        self.instantaneas_empujadas += 1
        for conexion in suscriptores:
            conexion.encolar(sobre, critico=False)

    def _asegurar_emisor(self) -> None:
        """Arranca el emisor con el PRIMER suscriptor, no antes.

        Sin clientes no hay sondeo: los ~800 tests de la suite y el gabinete de
        hoy —donde nadie se suscribe todavía— no pagan un `snapshot()` a 20 Hz
        por tener el transporte construido.
        """
        with self._lock:
            if self._emisor is not None and self._emisor.is_alive():
                return
            self._emisor = threading.Thread(target=self._emitir, name="pinlink-emisor", daemon=True)
            self._emisor.start()

    def _emitir(self) -> None:
        ultimo: Any = None
        ultimo_envio = 0.0
        while not self._parar.wait(self._sondeo_s):
            if not self._suscriptores():
                return  # el último cliente se fue: el emisor se apaga solo
            if self._congelado:
                continue
            try:
                snap = self._gpio.snapshot()
            except Exception:  # noqa: BLE001 — el emisor jamás tumba al dueño
                log.exception("pinlink: no se pudo leer el estado del gabinete")
                continue
            ahora = time.monotonic()
            if snap == ultimo and (ahora - ultimo_envio) < self._keepalive_s:
                continue
            ultimo, ultimo_envio = snap, ahora
            sobre = self._sobre_estado(snap)
            self.instantaneas_empujadas += 1
            for conexion in self._suscriptores():
                conexion.encolar(sobre, critico=False)

    # ------------------------------------------------------------ observadores
    def _poner_observadores(self) -> None:
        """Se enganchan UNA vez por controlador: `gpio` no sabe desregistrar.

        Los callbacks comprueban `_parar`, así que un servidor detenido es un
        no-op aunque su observador siga en la lista del controlador.
        """
        if self._observadores_puestos or self._gpio is None:
            return
        self._gpio.on_sasmex(self._al_sasmex)
        self._gpio.on_silence(self._al_silencio)
        self._observadores_puestos = True

    def _al_sasmex(self, signal: Any) -> None:
        """Observador del dueño. Corre en el hilo del reflejo, DESPUÉS de los relés.

        Aquí no se puede bloquear: `encolar` es `put_nowait` y un cliente que no
        drena se desahucia. Lo único que este método hace antes de encolar es
        acuñar el `episode_id` del episodio nuevo, que es lo que permite al
        cliente reconciliar sin duplicar el incidente en la nube.
        """
        if self._parar.is_set():
            return
        if getattr(signal, "active", False) and not getattr(signal, "is_test", False):
            self._episodio = new_event_id()
        sobre = {
            "push": "event",
            "event": "sasmex",
            "signal": signal.model_dump(mode="json"),
            "episode_id": self._episodio,
        }
        for conexion in self._suscriptores():
            if "sasmex" in conexion.suscrito:
                conexion.encolar(sobre, critico=True)
        self._empujar_estado()

    def _al_silencio(self, silenciado: bool) -> None:
        if self._parar.is_set():
            return
        sobre = {"push": "event", "event": "silence", "silenced": bool(silenciado)}
        for conexion in self._suscriptores():
            if "silence" in conexion.suscrito:
                conexion.encolar(sobre, critico=True)
        self._empujar_estado()


class ProtocoloDeAccion(ValueError):
    """Petición sintácticamente admisible pero con parámetros imposibles."""


def _error(tipo: str, mensaje: str) -> dict:
    return {"type": tipo, "message": mensaje}
