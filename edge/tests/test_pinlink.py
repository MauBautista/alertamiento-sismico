"""[T-2.70.a · D2/P2] El TRANSPORTE entre el dueño de los pines y sus clientes.

Todavía no mueve un pin: el servidor vive DENTRO del dueño actual, así que en
esta suite el mismo proceso es dueño y cliente. Lo que se construye aquí es el
socket, el códec y el cliente CACHÉ-FIRST, para que D3 pueda encenderlo con una
línea y acreditarlo en el Pi real sin traspasar la propiedad.

Las tres propiedades que este archivo defiende, y por qué cada una:

1. **El códec no puede perder un campo en silencio.** Se deriva de
   `GpioSnapshot.__dataclass_fields__`: un campo nuevo que el códec no sepa
   llevar pone la corrida en rojo, y cada campo se mide POR SEPARADO (dos
   instantáneas que difieren solo en él tienen que seguir difiriendo al otro
   lado).
2. **La lectura NUNCA cruza el socket.** Las lecturas ocurren en el hilo de
   SeedLink, en el watcher de sirena a 20 Hz y en cada refresco del kiosco. Un
   round-trip por lectura metería el transporte en caminos que hoy son un acceso
   a memoria.
3. **La caché declara su EDAD, y fuera de plazo el dato NO EXISTE.** Servir una
   instantánea congelada como si fuera viva es el defecto del 14-jul y la
   doctrina de T-2.58; aquí se convierte en `GpioLinkUnavailable`, que es la
   causa que los consumidores ya saben tratar desde D2/P1.
"""

from __future__ import annotations

import errno
import json
import os
import socket
import threading
import time
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest
from takab_edge.contracts import ActuatorChannel, RelayState, SasmexSignal, SirenReason
from takab_edge.gpio import GpioController
from takab_edge.gpio_link import (
    GPIO_ACTIONS,
    ChannelOutcome,
    GpioActionNotAllowed,
    GpioLink,
    GpioLinkUnavailable,
    GpioSnapshot,
    LocalGpioLink,
)
from takab_edge.pinlink import IpcGpioLink, PinLinkServer
from takab_edge.pinlink import codec as cd

_RELES = (
    ActuatorChannel.SIREN,
    ActuatorChannel.STROBE,
    ActuatorChannel.GAS_VALVE,
    ActuatorChannel.ELEVATOR,
    ActuatorChannel.DOOR_RETAINER,
)


# ---------------------------------------------------------------------------
# Fixtures: un dueño de pines de verdad, un servidor de verdad, un socket real
# ---------------------------------------------------------------------------


@pytest.fixture
def sirviendo(settings):  # noqa: ANN001, ANN201
    """Ajustes con la puerta de servicio FORZADA abierta.

    De fábrica está cerrada desde el cierre de la auditoría de D2/P2 (ver
    `test_de_fabrica_el_gabinete_ni_siquiera_ATA_el_socket`): el gabinete real
    con `GPIO_LINK=local` no ata el socket ni registra el observador del
    servidor en el reflejo. Los casos que miden el SERVIDOR tienen que pedirlo.
    """
    return settings.model_copy(update={"gpio_serve_enabled": True})


@pytest.fixture
def gpio(sirviendo):  # noqa: ANN001, ANN201
    controller = GpioController(sirviendo)
    controller.start()
    try:
        yield controller
    finally:
        controller.stop()


@pytest.fixture
def ruta_socket(settings) -> str:  # noqa: ANN001
    return settings.gpio_socket_file


@pytest.fixture
def servidor(gpio, ruta_socket):  # noqa: ANN001, ANN201
    """El servidor del gabinete, SIN el que trae `GpioController` por su cuenta.

    `gpio` ya levantó el suyo (es lo que hará en producción); aquí se para y se
    monta uno explícito para poder instrumentarlo (contar peticiones, congelar
    el envío, negar el uid). Es el MISMO controlador debajo: el objetivo del paso
    es que cliente y dueño no puedan divergir.
    """
    gpio.detener_servidor_de_pines()
    srv = PinLinkServer(gpio, ruta_socket)
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture
def cliente(servidor):  # noqa: ANN001, ANN201
    link = IpcGpioLink(ruta=servidor.ruta)
    link.start()
    try:
        yield link
    finally:
        link.stop()


def _esperar(condicion, timeout: float = 3.0) -> bool:  # noqa: ANN001
    """Espera activa corta: el cliente converge por PUSH, no por petición."""
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        try:
            if condicion():
                return True
        except GpioLinkUnavailable:
            pass
        time.sleep(0.005)
    return False


def _espiar_la_secuencia(sup) -> list:  # noqa: ANN001
    """Anota los ACKs de cada secuencia de actuación que el gabinete dispare.

    Se interpone en `actuators.execute_sequence` —la llamada que hace
    `supervisor._act_and_publish`— y NO en la costura: lo que hay que medir es lo
    que el gabinete acaba reportando de sí mismo, no si un socket contestó.
    """
    disparados: list = []
    original = sup.actuators.execute_sequence

    def _anotado(comandos):  # noqa: ANN001, ANN202
        resultado = original(comandos)
        disparados.extend(resultado)
        return resultado

    sup.actuators.execute_sequence = _anotado
    return disparados


# ---------------------------------------------------------------------------
# 1 · El códec, derivado del contrato (no de una lista escrita a mano)
# ---------------------------------------------------------------------------


def test_el_codec_lleva_TODOS_los_campos_de_la_instantanea(gpio: GpioController) -> None:
    """Derivado de `__dataclass_fields__`: un campo nuevo no puede quedarse fuera.

    La única excepción admitida es la DECLARADA (`age_s`), que se recalcula en el
    reloj de quien lee — transportar la edad medida en el reloj del otro proceso
    sería exactamente la mentira que esta pieza existe para impedir.
    """
    gpio.simulate_sasmex(active=True)
    original = gpio.snapshot()
    ida = cd.instantanea_a_json(original)
    vuelta = cd.instantanea_desde_json(ida, edad_s=0.0)

    campos = set(GpioSnapshot.__dataclass_fields__)
    declarados = set(cd.CAMPOS_RECALCULADOS_AL_LLEGAR)
    assert declarados <= campos, "se declara como recalculado un campo que no existe"
    for campo in sorted(campos - declarados):
        assert campo in ida, f"el códec no transporta {campo!r}"
        assert getattr(vuelta, campo) == getattr(original, campo), f"{campo} no sobrevivió"
    assert isinstance(vuelta, GpioSnapshot)
    assert all(isinstance(r, RelayState) for r in vuelta.relays)
    assert vuelta.siren_reason is SirenReason.ALERT


@pytest.mark.parametrize(
    "campo", sorted(set(GpioSnapshot.__dataclass_fields__) - {"age_s", "relays"})
)
def test_dos_instantaneas_que_difieren_en_UN_campo_siguen_difiriendo_al_otro_lado(
    gpio: GpioController, campo: str
) -> None:
    """NO-VACUIDAD del códec, campo a campo.

    Un códec que dejara caer un campo pasaría el test de arriba en cuanto el
    valor coincidiera por casualidad con el default. Aquí se construyen DOS
    instantáneas que solo difieren en ese campo y se exige que al otro lado
    sigan siendo distintas: si el campo no viaja, las dos llegan iguales.
    """
    base = gpio.snapshot()
    otro = replace(base, **{campo: _otro_valor(campo, getattr(base, campo))})
    ida = cd.instantanea_desde_json(cd.instantanea_a_json(base), edad_s=0.0)
    vuelta = cd.instantanea_desde_json(cd.instantanea_a_json(otro), edad_s=0.0)
    assert getattr(ida, campo) != getattr(vuelta, campo), (
        f"el códec colapsó dos estados distintos: {campo} no viaja"
    )


def _otro_valor(campo: str, valor: object) -> object:
    """Un valor DISTINTO para ese campo, elegido por su tipo DECLARADO.

    Por el tipo y no por el valor: `last_reflex_latency_s` vale `None` en un
    gabinete recién arrancado, y variarlo «según lo que hay» lo confundiría con
    `siren_reason`, que también vale `None`. Un campo nuevo de un tipo que este
    ayudante no sepa variar hace fallar su propio caso — que es lo correcto:
    significa que nadie está midiendo si ese campo viaja.
    """
    from typing import get_type_hints

    anotacion = str(get_type_hints(GpioSnapshot)[campo])
    if "bool" in anotacion:
        return not valor
    if "SirenReason" in anotacion:
        return SirenReason.TEST if valor is not SirenReason.TEST else SirenReason.ALERT
    if "float" in anotacion or "int" in anotacion:
        return float(valor or 0.0) + 7.5
    raise AssertionError(f"el test no sabe variar un campo {campo}: {anotacion}")


def test_los_resultados_por_canal_del_lote_sobreviven_al_transporte() -> None:
    original = (
        ChannelOutcome(channel=ActuatorChannel.SIREN, ok=True, detail="relay"),
        ChannelOutcome(channel=ActuatorChannel.SYSTEM, ok=False, detail="excepción: x"),
    )
    vuelta = tuple(cd.resultado_desde_json(cd.resultado_a_json(r)) for r in original)
    assert vuelta == original


def test_el_marco_reensambla_lo_que_llega_partido() -> None:
    """TCP sobre AF_UNIX entrega bytes, no mensajes: el marco es del códec."""
    mensajes = [{"op": "snapshot", "id": 1}, {"push": "snapshot", "n": 2}]
    crudo = b"".join(cd.enmarcar(m) for m in mensajes)
    lector = cd.Desenmarcador()
    recibidos: list[dict] = []
    for i in range(0, len(crudo), 3):  # troceado a propósito, 3 bytes cada vez
        recibidos.extend(lector.alimentar(crudo[i : i + 3]))
    assert recibidos == mensajes
    # …y un marco entero de golpe también.
    assert cd.Desenmarcador().alimentar(crudo) == mensajes


def test_un_marco_gigante_se_rechaza_en_vez_de_reventar_la_memoria() -> None:
    """Cota explícita: un `length` corrupto no puede pedir 4 GiB al asignador."""
    cabecera = (cd.MAX_MARCO + 1).to_bytes(4, "big")
    with pytest.raises(cd.ProtocolError):
        cd.Desenmarcador().alimentar(cabecera)
    with pytest.raises(cd.ProtocolError):
        cd.enmarcar({"basura": "x" * (cd.MAX_MARCO + 10)})


def test_un_cuerpo_que_no_es_json_no_tumba_al_dueno_de_los_pines() -> None:
    marco = (5).to_bytes(4, "big") + b"{{{{{"
    with pytest.raises(cd.ProtocolError):
        cd.Desenmarcador().alimentar(marco)


# ---------------------------------------------------------------------------
# 2 · El servidor: tabla CERRADA, uid del par, rate-limit
# ---------------------------------------------------------------------------


def test_la_tabla_de_operaciones_es_la_lista_BLANCA_de_la_costura(cliente, gpio) -> None:  # noqa: ANN001
    """`drive_all_safe` no está, y no puede estarlo: es estado seguro DURABLE.

    NO-VACUIDAD: las siete acciones declaradas SÍ cruzan (ver la suite de
    conformidad, que las recorre una a una); aquí se mide que lo que no está
    declarado se rechaza NOMBRANDO la lista, y que el rechazo no mata la conexión.
    """
    assert "drive_all_safe" not in GPIO_ACTIONS
    with pytest.raises(GpioActionNotAllowed):
        cliente.action("drive_all_safe")
    with pytest.raises(GpioActionNotAllowed):
        cliente.action("cualquier_cosa")
    # La conexión sigue viva y el gabinete intacto: un rechazo no es una avería.
    assert cliente.snapshot().running is True
    assert gpio._safed is False


def test_una_operacion_desconocida_no_derriba_la_conexion(cliente) -> None:  # noqa: ANN001
    respuesta = cliente._pedir({"op": "inventada"}, timeout=2.0, esperar=True)
    assert respuesta["ok"] is False
    assert "inventada" in respuesta["error"]["message"]
    assert cliente.snapshot() is not None


def test_el_socket_solo_admite_al_uid_del_dueno_o_a_root(gpio, ruta_socket) -> None:  # noqa: ANN001
    """`SO_PEERCRED`, no una promesa de permisos de archivo.

    En producción dueño y cliente son root y el conjunto es `{0}`. Aquí se monta
    un servidor cuya política nombra un uid AJENO para poder medir el rechazo sin
    ser root, y se comprueba que la conexión se cierra sin contestar una sola
    operación.

    NO-VACUIDAD: el mismo servidor, con la política por defecto, contesta.
    """
    gpio.detener_servidor_de_pines()
    ajeno = PinLinkServer(gpio, ruta_socket, uids_permitidos=frozenset({os.getuid() + 4242}))
    ajeno.start()
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect(ruta_socket)  # `connect` a un AF_UNIX siempre lo acepta el kernel
        try:
            s.sendall(cd.enmarcar({"id": 1, "op": "snapshot"}))
            assert s.recv(4096) == b"", "el servidor contestó a un uid que no es el suyo"
        except (ConnectionResetError, BrokenPipeError):
            pass  # el servidor cerró antes de leer: también es «no te contesto»
        finally:
            s.close()
        assert ajeno.rechazos_por_uid == 1
    finally:
        ajeno.stop()

    propio = PinLinkServer(gpio, ruta_socket)
    propio.start()
    try:
        link = IpcGpioLink(ruta=ruta_socket)
        link.start()
        try:
            assert link.snapshot().running is True
        finally:
            link.stop()
    finally:
        propio.stop()


def test_el_rate_limit_frena_un_cliente_desbocado_sin_soltar_los_pines(gpio, ruta_socket) -> None:  # noqa: ANN001
    """Cinturón contra un bucle de un cliente, no contra un atacante (ya es root).

    Lo que NO puede pasar es que el freno mate al único cliente: se contesta
    error y la conexión sigue, porque cerrarla dejaría al gabinete sin actuación
    posterior por culpa de un bug de conteo.
    """
    gpio.detener_servidor_de_pines()
    srv = PinLinkServer(gpio, ruta_socket, ops_por_s=5)
    srv.start()
    try:
        link = IpcGpioLink(ruta=ruta_socket)
        link.start()
        try:
            frenadas = 0
            for _ in range(40):
                r = link._pedir({"op": "action", "name": "reset", "params": {}}, 2.0, esperar=True)
                if not r["ok"] and r["error"]["type"] == "RateLimited":
                    frenadas += 1
            assert frenadas > 0, "el rate-limit no frenó nada: no está midiendo"
            # …y la conexión SIGUE viva, que es la mitad que importa.
            assert link.snapshot().running is True
        finally:
            link.stop()
    finally:
        srv.stop()


def test_el_rate_limit_no_ahoga_el_journal_que_lo_diagnostica(gpio, ruta_socket, caplog) -> None:  # noqa: ANN001
    """Regla de oro 10: una línea por petición frenada eran 417 líneas/s medidas.

    El cinturón que existe para sobrevivir a un cliente desbocado se comía el
    journal donde se diagnostica ese mismo cliente. `audio._reconcile_siren` se
    autolimita a ~1/s por esta razón exacta; aquí igual, y diciendo cuántas
    frenó mientras callaba (un contador es información; 400 líneas iguales, no).
    """
    gpio.detener_servidor_de_pines()
    srv = PinLinkServer(gpio, ruta_socket, ops_por_s=5)
    srv.start()
    try:
        link = IpcGpioLink(ruta=ruta_socket)
        link.start()
        try:
            caplog.clear()
            with caplog.at_level("WARNING", logger="takab_edge.pinlink.server"):
                # Se machaca DURANTE 1.5 s, no N veces: lo que se mide es una
                # tasa (417 líneas/s), y una ráfaga instantánea no la vería.
                limite = time.monotonic() + 1.5
                while time.monotonic() < limite:
                    link._pedir({"op": "action", "name": "reset", "params": {}}, 2.0)
            lineas = [r for r in caplog.records if "rate-limit" in r.getMessage()]
            assert srv.frenadas > 100, f"el rate-limit apenas frenó {srv.frenadas}: no mide nada"
            assert len(lineas) <= 5, (
                f"{len(lineas)} líneas para {srv.frenadas} frenadas: el freno ahoga el journal"
            )
            # …y NO se calla del todo: el operador tiene que enterarse, y de cuántas.
            assert lineas, "el rate-limit frenó en silencio: nadie puede diagnosticarlo"
            assert any("frenadas sin registrar" in r.getMessage() for r in lineas), (
                "la línea no dice cuántas frenó mientras callaba"
            )
        finally:
            link.stop()
    finally:
        srv.stop()


def test_el_backoff_ENGANCHA_cuando_el_dueno_acepta_y_cuelga(gpio, ruta_socket) -> None:  # noqa: ANN001
    """El backoff existía y no enganchaba NUNCA. `connect()` no es una sesión.

    `intento = 0` se reseteaba en cuanto `connect()` volvía, y en `AF_UNIX` el
    kernel completa el `connect` aunque el servidor cierre acto seguido. Con el
    dueño rechazando por uid (`SO_PEERCRED`): **20.6 reconexiones/s
    indefinidamente**, ~62 líneas/s de journal. Ahora sólo cuenta como éxito una
    sesión que SIRVIÓ algo.
    """
    gpio.detener_servidor_de_pines()
    ajeno = PinLinkServer(gpio, ruta_socket, uids_permitidos=frozenset({os.getuid() + 4242}))
    ajeno.start()
    try:
        link = IpcGpioLink(ruta=ruta_socket, espera_inicial_s=0.05)
        link.start()
        try:
            time.sleep(1.5)
            intentos = ajeno.rechazos_por_uid
        finally:
            link.stop()
    finally:
        ajeno.stop()
    # A 20.6/s serían ~30 en 1.5 s; con el backoff capado a 5 s son un puñado.
    assert intentos <= 10, f"{intentos} reconexiones en 1.5 s: el backoff no engancha"
    # NO-VACUIDAD: y NO se rinde — el hilo sigue vivo reintentando (lección `737dd73`).
    assert intentos >= 2, f"sólo {intentos} intentos: el cliente dejó de reconectar"


def test_el_dueno_de_los_pines_no_reparte_hilos_sin_limite(gpio, ruta_socket) -> None:  # noqa: ANN001
    """`listen(8)` es el backlog de aceptación, NO una cota de conexiones vivas.

    Medido antes: 200 conexiones parqueadas a media trama ⇒ **+400 hilos**
    (lector + escritor por cliente) dentro del proceso que toca la sirena,
    sostenidos indefinidamente. Dos cierres, y los dos hacen falta: una cota de
    conexiones vivas y un corte al que abre, manda medio marco y se calla.
    """
    gpio.detener_servidor_de_pines()
    srv = PinLinkServer(gpio, ruta_socket, max_conexiones=3, timeout_ocioso_s=0.3)
    srv.start()
    parqueados = []
    try:
        antes = threading.active_count()
        rebotados = 0
        for _ in range(20):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(2.0)
            try:
                s.connect(ruta_socket)
                # Cabecera de 64 bytes… y ni un byte de cuerpo: el cliente que
                # abre, manda medio marco y se calla.
                s.sendall(b"\x00\x00\x00\x40")
            except OSError:
                # Con la cota puesta el backlog se llena y el kernel ya ni deja
                # conectar: también es «no repartes hilos», y cuenta igual.
                rebotados += 1
                s.close()
                continue
            parqueados.append(s)
        assert _esperar(lambda: srv.rechazos_por_cota + rebotados >= 15), (
            f"la cota no frenó a nadie ({srv.rechazos_por_cota} rechazos + {rebotados} rebotes "
            "de 20 intentos)"
        )
        # …y los que SÍ entraron se caen solos por ociosos, sin dejar los hilos.
        assert _esperar(lambda: threading.active_count() <= antes + 2, timeout=5.0), (
            f"quedaron hilos de clientes parqueados: {threading.active_count()} > {antes}"
        )
        # NO-VACUIDAD: el dueño sigue atendiendo a un cliente sano después de todo esto.
        link = IpcGpioLink(ruta=ruta_socket)
        link.start()
        try:
            assert _esperar(lambda: link.snapshot().running is True), (
                "la cota dejó fuera al cliente legítimo: peor que no tenerla"
            )
        finally:
            link.stop()
    finally:
        for s in parqueados:
            s.close()
        srv.stop()


def test_un_suscriptor_CALLADO_no_es_un_cliente_ocioso(gpio, ruta_socket) -> None:  # noqa: ANN001
    """NO-VACUIDAD del corte anterior: el flujo va del dueño al cliente.

    Un cliente sano se suscribe UNA vez y luego no vuelve a hablar nunca. Cortar
    por «no dice nada» dejaría al gabinete sin panel ni actuación posterior cada
    30 s — un cierre peor que el agujero que viene a tapar.
    """
    gpio.detener_servidor_de_pines()
    srv = PinLinkServer(gpio, ruta_socket, timeout_ocioso_s=0.3)
    srv.start()
    try:
        link = IpcGpioLink(ruta=ruta_socket)
        link.start()
        try:
            assert _esperar(lambda: link.snapshot().running is True)
            time.sleep(1.2)  # cuatro veces el plazo del ocioso, sin decir ni mu
            assert link.snapshot().running is True, "cortaron a un suscriptor sano por callado"
            assert link.apply([(ActuatorChannel.GAS_VALVE, True)])[0].ok is True
        finally:
            link.stop()
    finally:
        srv.stop()


def test_un_observador_del_reflejo_que_revienta_no_calla_a_los_demas(gpio) -> None:  # noqa: ANN001
    """`_dispatch_sasmex` invocaba los observadores SIN `try`, uno tras otro.

    Y desde D2/P2 el callback #0 de esa lista es `PinLinkServer._al_sasmex`: el
    dueño se suscribe a sí mismo para servir su propia puerta. Si ese primero
    lanzaba, no llegaban a correr `supervisor._on_sasmex` —que publica el evento
    a la NUBE y abre incidente— ni `drill.on_sasmex` —que aborta el simulacro
    ante una alerta real—. Un fallo del transporte apagando la notificación de un
    sismo es exactamente lo que el hilo NO crítico existe para impedir.
    """
    assert gpio._sasmex_callbacks, "el dueño no tiene observadores: el caso no mide nada"
    assert type(getattr(gpio._sasmex_callbacks[0], "__self__", None)).__name__ == "PinLinkServer", (
        "el callback #0 ya no es el del transporte; este caso hay que reescribirlo"
    )
    nube: list = []
    simulacro: list = []

    def _revienta(_s) -> None:  # noqa: ANN001
        raise RuntimeError("el transporte se cayó a media notificación")

    gpio.on_sasmex(_revienta)
    gpio.on_sasmex(nube.append)
    gpio.on_sasmex(simulacro.append)

    gpio.simulate_sasmex(active=True)

    assert len(nube) == 1, "el evento no llegó a la nube: un observer se llevó a los demás"
    assert len(simulacro) == 1, "el simulacro no se enteró de la alerta real"
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is True


def test_una_lectura_ilegible_del_estado_no_tumba_al_hilo_del_reflejo(  # noqa: ANN001
    gpio,
    servidor,
    cliente,
) -> None:
    """La otra mitad: `_empujar_estado` leía el estado SIN guarda.

    Lo llama `_al_sasmex`, que corre en el hilo del REFLEJO justo después de
    energizar la sirena. El emisor ya tenía esta guarda; ésta era la que faltaba.

    Se mide **en el servidor**, llamando a `_al_sasmex` a pelo, y no sólo de
    punta a punta: el aislamiento de `gpio._dispatch_sasmex` taparía este agujero
    desde fuera y el caso quedaría verde para siempre sin medir nada de aquí. Las
    dos defensas existen a propósito, y cada una se prueba por su cuenta.
    """
    llegadas: list = []
    gpio.on_sasmex(llegadas.append)
    assert _esperar(lambda: cliente.snapshot().running is True)

    def _ilegible():  # noqa: ANN202
        raise RuntimeError("estado del gabinete ilegible")

    gpio.snapshot = _ilegible
    try:
        # 1 · el observador del transporte, a pelo: NO puede propagar.
        servidor._al_sasmex(SasmexSignal(active=True, is_test=False))
        # 2 · y de punta a punta el gabinete sigue haciendo lo suyo.
        gpio.simulate_sasmex(active=True)
        assert llegadas, "la lectura ilegible del transporte calló al observador siguiente"
        assert gpio.relay_state(ActuatorChannel.SIREN).energized is True
    finally:
        del gpio.snapshot


def test_el_servidor_que_no_puede_bindear_NO_impide_el_reflejo(sirviendo, tmp_path) -> None:  # noqa: ANN001
    """El hilo del servidor es NO crítico: es lo que lo hace desplegable sin riesgo.

    Se le da una ruta imposible (un directorio que no se puede crear) y se exige
    que el gabinete arranque igual y que el reflejo SASMEX→sirena siga
    energizando los relés.

    La puerta va FORZADA abierta: con el default de fábrica (cerrada) el caso
    mediría que un servidor apagado no estorba, que no es lo mismo que un
    servidor que lo intentó y no pudo.
    """
    imposible = tmp_path / "archivo-no-directorio"
    imposible.write_text("no soy un directorio")
    cfg = sirviendo.model_copy(update={"gpio_socket_path": str(imposible / "gpio.sock")})
    controlador = GpioController(cfg)
    controlador.start()
    try:
        assert controlador.running is True
        assert controlador.servidor_de_pines is None, (
            "el servidor dice estar en marcha con una ruta imposible"
        )
        controlador.simulate_sasmex(active=True)
        assert controlador.relay_state(ActuatorChannel.SIREN).energized is True
        assert controlador.relay_state(ActuatorChannel.STROBE).energized is True
    finally:
        controlador.stop()


def test_el_dueno_levanta_su_servidor_al_arrancar_y_lo_retira_al_parar(sirviendo) -> None:  # noqa: ANN001
    """Requisito 2: el servidor vive DENTRO del dueño actual."""
    settings = sirviendo
    controlador = GpioController(settings)
    controlador.start()
    try:
        assert controlador.servidor_de_pines is not None
        assert Path(settings.gpio_socket_file).exists()
        link = IpcGpioLink(ruta=settings.gpio_socket_file)
        link.start()
        try:
            assert link.snapshot().running is True
        finally:
            link.stop()
    finally:
        controlador.stop()
    assert not Path(settings.gpio_socket_file).exists(), (
        "el socket sobrevivió al dueño: el siguiente arranque hablaría con un muerto"
    )


def test_un_socket_rancio_no_impide_arrancar_al_dueno_siguiente(sirviendo) -> None:  # noqa: ANN001
    """Un `SIGKILL` deja el archivo del socket: el sucesor tiene que poder atar.

    Y el caso contrario NO puede colar: si al otro lado hay alguien VIVO, no se
    le roba la ruta — el `flock` de D1.1 es el que decide la propiedad, y aquí se
    respeta el mismo veredicto.
    """
    ruta = Path(sirviendo.gpio_socket_file)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"")  # archivo rancio, nadie escuchando
    controlador = GpioController(sirviendo)
    controlador.start()
    try:
        assert controlador.servidor_de_pines is not None
    finally:
        controlador.stop()


# ---------------------------------------------------------------------------
# 3 · El cliente CACHÉ-FIRST y la EDAD de la instantánea
# ---------------------------------------------------------------------------


def test_las_lecturas_NO_cruzan_el_socket(cliente, servidor, gpio) -> None:  # noqa: ANN001
    """LA PIEZA CLAVE. El watcher de sirena lee a 20 Hz y el kiosco a ~11 Hz.

    NO-VACUIDAD: el contador del servidor sí sube con una operación que SÍ tiene
    que cruzar (`action`), así que no está midiendo un cero muerto.
    """
    assert _esperar(lambda: cliente.snapshot().running is True)
    antes = servidor.peticiones_atendidas
    for _ in range(200):
        cliente.snapshot()
    assert servidor.peticiones_atendidas == antes, (
        f"{servidor.peticiones_atendidas - antes} lecturas cruzaron el socket"
    )
    cliente.action("reset")
    assert servidor.peticiones_atendidas > antes, "el contador no mide nada"


def test_la_instantanea_declara_su_EDAD(cliente) -> None:  # noqa: ANN001
    """Una caché que no dice cuándo se llenó es un dato congelado disfrazado."""
    assert _esperar(lambda: cliente.snapshot().running is True)
    edad = cliente.snapshot().age_s
    assert 0.0 <= edad < 2.0
    time.sleep(0.15)
    assert cliente.snapshot().age_s > edad, "la edad no corre: es un adorno"


def test_fuera_de_plazo_el_dato_NO_EXISTE(cliente, servidor) -> None:  # noqa: ANN001
    """Doctrina de T-2.58: pasado el plazo no se pinta viejo, se declara ausente.

    Se congela el emisor del servidor (deja de empujar) y se exige que, superada
    la edad máxima, la lectura pase a ser `GpioLinkUnavailable` — la causa que
    los consumidores ya tratan desde D2/P1 (`gpio_unreachable` en el panel,
    fail-cerrado en el voceo y en el simulacro).

    NO-VACUIDAD: ANTES del plazo la misma lectura devuelve estado.
    """
    cliente._edad_maxima_s = 0.3
    assert _esperar(lambda: cliente.snapshot().running is True)
    assert cliente.snapshot() is not None  # dentro de plazo: existe

    servidor.congelar_emision(True)
    limite = time.monotonic() + 3.0
    while time.monotonic() < limite:
        try:
            cliente.snapshot()
        except GpioLinkUnavailable as exc:
            assert "edad" in str(exc).lower() or "plazo" in str(exc).lower()
            break
        time.sleep(0.02)
    else:
        pytest.fail("la caché sirvió un dato rancio como si fuera vivo")

    servidor.congelar_emision(False)
    assert _esperar(lambda: cliente.snapshot().running is True), (
        "la caché no se recuperó cuando el dueño volvió a hablar"
    )


def test_sin_una_sola_instantanea_la_lectura_no_INVENTA_un_gabinete(servidor) -> None:  # noqa: ANN001
    """Arranque en frío: nunca un `GpioSnapshot` de ceros."""
    link = IpcGpioLink(ruta=servidor.ruta + ".no-existe", espera_inicial_s=0.2)
    link.start()
    try:
        with pytest.raises(GpioLinkUnavailable):
            link.snapshot()
    finally:
        link.stop()


def test_el_cliente_es_NO_critico_y_el_dueno_SI(cliente) -> None:  # noqa: ANN001
    """Requisito 4, explícito y con su razón.

    `GpioController.critical=True` significa «si no puedo tocar los pines,
    crashea ruidoso», y para el DUEÑO es correcto. Heredarlo en el cliente
    significaría «gpio inalcanzable ⇒ `takab-edge` crashea en bucle»: el
    supervisor propaga el fallo de un módulo crítico y `Restart=always` lo
    reintenta para siempre, con el gabinete perdiendo SeedLink, nube, backfill y
    panel por una avería del transporte que NO afecta al reflejo.
    """
    assert GpioController.critical is True
    assert IpcGpioLink.critical is False
    assert cliente.critical is False


def test_lo_que_se_escribe_por_el_socket_se_lee_ya_en_la_cache(cliente, gpio) -> None:  # noqa: ANN001
    """Leer lo propio escrito: el panel hace `action()` y lee en el mismo request.

    El servidor empuja la instantánea POSTERIOR a la mutación ANTES de contestar,
    y el cliente procesa el flujo en orden con un solo hilo lector: cuando la
    respuesta vuelve, la caché ya es la nueva. Sin esta ordenación el operador
    aprieta SILENCIO y el panel le sigue diciendo que la sirena suena.
    """
    gpio.simulate_sasmex(active=True)
    assert _esperar(lambda: cliente.snapshot().siren_sounding is True)
    cliente.action("silence", silenced=True)
    snap = cliente.snapshot()  # SIN esperar
    assert snap.audible_silenced is True and snap.siren_sounding is False

    resultados = cliente.apply([(ActuatorChannel.GAS_VALVE, True)])
    assert resultados[0].ok is True
    assert cliente.snapshot().relays  # SIN esperar
    estados = {r.channel: r for r in cliente.snapshot().relays}
    assert estados[ActuatorChannel.GAS_VALVE].activated is True


# ---------------------------------------------------------------------------
# 4 · Reconexión: sin duplicar el incidente y sin desbordar el backoff
# ---------------------------------------------------------------------------


def test_el_backoff_de_reconexion_no_desborda_nunca(cliente) -> None:  # noqa: ANN001
    """Lección de `737dd73`: el hilo de reconexión moría por `OverflowError` tras
    ~1024 intentos y el gabinete callaba EN SILENCIO. El exponente va CAPADO."""
    esperas = [cliente._espera_de_reintento(n) for n in (0, 1, 5, 50, 5000, 10**6)]
    assert all(0 < e <= cliente._espera_maxima_s for e in esperas)
    assert esperas[-1] == cliente._espera_maxima_s
    assert esperas[0] < esperas[2], "el backoff no crece: reintenta a ciegas"


def test_una_reconexion_NO_duplica_el_incidente_en_la_nube(gpio, ruta_socket) -> None:  # noqa: ANN001
    """Reconciliación por `episode_id`.

    El observador `sasmex` del cliente es lo que abre incidente en la nube. Si al
    reconectar el cliente sintetizara un evento por ver el enclave vivo, cada
    caída del socket abriría un incidente NUEVO del MISMO sismo — y con la
    instantánea llegando a 20 Hz, veinte por segundo.

    Las dos mitades:
      · un episodio que ya se entregó NO se repite al reconectar;
      · un episodio que empezó MIENTRAS el enlace estaba caído SÍ se entrega
        (exactamente una vez): es el mismo traspaso que `_seed_from_held_contact`
        hace en el arranque del hardware, ahora en el transporte.
    """
    gpio.detener_servidor_de_pines()
    srv = PinLinkServer(gpio, ruta_socket)
    srv.start()
    link = IpcGpioLink(ruta=ruta_socket)
    recibidos: list = []
    link.subscribe("sasmex", recibidos.append)
    link.start()
    try:
        assert _esperar(lambda: link.snapshot().running is True)
        gpio.simulate_sasmex(active=True)
        assert _esperar(lambda: len(recibidos) == 1)

        # Se cae el enlace y vuelve, con el enclave VIVO todo el tiempo.
        srv.stop()
        srv = PinLinkServer(gpio, ruta_socket)
        srv.start()
        assert _esperar(lambda: link.snapshot().running is True, timeout=10.0)
        time.sleep(0.3)  # varias instantáneas con el enclave puesto
        assert len(recibidos) == 1, (
            f"la reconexión volvió a abrir el incidente ({len(recibidos)} entregas)"
        )

        # Ahora al revés: episodio NUEVO nacido con el cliente ciego.
        link.stop()
        gpio.reset()
        gpio.simulate_sasmex(active=True)
        link.start()
        assert _esperar(lambda: len(recibidos) == 2, timeout=10.0), (
            "un episodio que empezó con el enlace caído no llegó nunca a la nube"
        )
        time.sleep(0.3)
        assert len(recibidos) == 2, "el episodio recuperado se entregó más de una vez"
    finally:
        link.stop()
        srv.stop()


def test_el_observador_de_silencio_tambien_cruza(cliente, gpio) -> None:  # noqa: ANN001
    """`audio._on_silence` calla el voceo cuando el operador silencia."""
    vistos: list[bool] = []
    cliente.subscribe("silence", vistos.append)
    assert _esperar(lambda: cliente.snapshot().running is True)
    gpio.silence_audibles(True)
    assert _esperar(lambda: vistos == [True])
    gpio.silence_audibles(False)
    assert _esperar(lambda: vistos == [True, False])


def test_un_observador_roto_no_tumba_al_hilo_lector(cliente, gpio) -> None:  # noqa: ANN001
    """Mismo aislamiento que `gpio.on_silence`: un observer no toca el transporte."""
    buenos: list = []

    def _explota(_s) -> None:  # noqa: ANN001
        raise RuntimeError("observer roto")

    cliente.subscribe("sasmex", _explota)
    cliente.subscribe("sasmex", buenos.append)
    assert _esperar(lambda: cliente.snapshot().running is True)
    gpio.simulate_sasmex(active=True)
    assert _esperar(lambda: len(buenos) == 1)
    assert _esperar(lambda: cliente.snapshot().sasmex_active is True), (
        "el hilo lector murió con el observer: la caché dejó de refrescarse"
    )


def test_los_observadores_NO_corren_en_el_hilo_lector(cliente, gpio) -> None:  # noqa: ANN001
    """EL DEFECTO QUE RECHAZÓ EL PASO, en su forma mínima.

    `supervisor._on_sasmex` se registra por esta misma vía y lo primero que hace
    es ACTUAR: `_act_and_publish` → `RelayActuator` → `link.apply(...)`, que
    espera una respuesta que **sólo el hilo lector puede leer**. Despachar los
    observadores en ese hilo era esperarse a uno mismo: timeout garantizado.

    Se miden las tres propiedades del arreglo a la vez:
      · el observador NO corre en `pinlink-cliente`;
      · desde él SÍ se puede cursar una orden, y llega al dueño de verdad;
      · el ORDEN de registro se conserva (la costura local invoca en ese orden y
        el gabinete depende de ello: primero la nube, después el simulacro).
    """
    hilos: list[str] = []
    orden: list[str] = []
    resultados: list = []

    def _primero(_s) -> None:  # noqa: ANN001
        hilos.append(threading.current_thread().name)
        orden.append("primero")
        resultados.extend(cliente.apply([(ActuatorChannel.GAS_VALVE, True)]))

    def _segundo(_s) -> None:  # noqa: ANN001
        orden.append("segundo")

    cliente.subscribe("sasmex", _primero)
    cliente.subscribe("sasmex", _segundo)
    assert _esperar(lambda: cliente.snapshot().running is True)

    gpio.simulate_sasmex(active=True)

    assert _esperar(lambda: orden == ["primero", "segundo"]), (
        f"los observadores no corrieron, o no en orden de registro: {orden}"
    )
    assert hilos and all(nombre != "pinlink-cliente" for nombre in hilos), (
        f"el observador corrió EN el hilo lector: {hilos}"
    )
    assert resultados and all(r.ok for r in resultados), (
        f"la orden cursada desde el observador no se pudo ejecutar: {resultados}"
    )
    assert gpio.is_activated(ActuatorChannel.GAS_VALVE) is True, (
        "el ACK dijo que sí y el relé no se movió"
    )


def test_una_orden_desde_el_hilo_lector_se_DECLARA_en_vez_de_colgarse(cliente) -> None:  # noqa: ANN001
    """El cable trampa: si la reentrada vuelve, que se sepa en 0 ms y por su nombre.

    El defecto original se leía en el journal como «el dueño de los pines no
    contestó a 'apply' en 2.0s», que apunta al dueño — y el dueño estaba
    perfecto, ejecutando el lote. Dos segundos por sismo y un diagnóstico que
    señala al inocente.
    """
    from takab_edge.pinlink.client import ReentradaDelHiloLector

    assert issubclass(ReentradaDelHiloLector, GpioLinkUnavailable), (
        "una causa nueva que los consumidores no traten llegaría cruda al camino de vida"
    )
    assert _esperar(lambda: cliente.snapshot().running is True)

    # Se suplanta la identidad del hilo lector: es la forma barata de recorrer el
    # cable trampa sin fabricar el interbloqueo que existe para impedir.
    real, cliente._hilo = cliente._hilo, threading.current_thread()
    try:
        t0 = time.perf_counter()
        with pytest.raises(ReentradaDelHiloLector):
            cliente.apply([(ActuatorChannel.GAS_VALVE, True)])
        tardanza = time.perf_counter() - t0
    finally:
        cliente._hilo = real
    assert tardanza < 0.2, f"tardó {tardanza * 1000:.0f} ms: eso no es declarar, es esperar"
    # NO-VACUIDAD: sin la suplantación, la MISMA orden pasa y mueve el relé.
    assert cliente.apply([(ActuatorChannel.GAS_VALVE, True)])[0].ok is True


def test_el_plazo_de_las_acciones_sale_de_lo_que_TARDAN(cliente, gpio) -> None:  # noqa: ANN001
    """`TIMEOUT_ACTION_S` se justificaba con una premisa FALSA. Ahora se MIDE.

    Decía «`actuation_test` sostiene sirena+estrobo `actuation_test_hold_s` (5 s
    de fábrica)» y de ahí salían 30 s. Ese sostenimiento va en un
    `threading.Timer` y **no bloquea la llamada**: lo que bloquea son los bucles
    de pulsos. 30 s eran ~19× el peor caso real, o sea 30 s de `apply` muertos
    ante un dueño atascado por creerse un comentario.

    Se recorre `GPIO_ACTIONS` entera —derivado, no una lista— con los ajustes de
    FÁBRICA, que es donde vive el caso lento.
    """
    from takab_edge.pinlink.client import TIMEOUT_ACTION_S

    assert gpio.settings.self_test_pulse_ms == 250, "sin los tiempos de fábrica no se mide nada"
    assert _esperar(lambda: cliente.snapshot().running is True)

    medidas: dict[str, float] = {}
    for nombre in sorted(GPIO_ACTIONS):
        cliente.action("reset")  # cada acción se mide sola, no tras la anterior
        inicio = time.perf_counter()
        cliente.action(nombre)
        medidas[nombre] = time.perf_counter() - inicio
    peor, quien = max((v, k) for k, v in medidas.items())

    assert peor < TIMEOUT_ACTION_S, (
        f"el plazo ({TIMEOUT_ACTION_S}s) es MENOR que lo que tarda {quien!r} ({peor:.2f}s): "
        "el panel reportaría fallo de algo que está funcionando"
    )
    assert TIMEOUT_ACTION_S <= peor * 6.0, (
        f"el plazo ({TIMEOUT_ACTION_S}s) es {TIMEOUT_ACTION_S / peor:.0f}× el peor caso "
        f"medido ({quien!r}, {peor:.2f}s): un dueño atascado bloquearía al llamador "
        "todo ese tiempo sin ninguna razón medida"
    )
    # NO-VACUIDAD: alguna acción TIENE que bloquear de verdad, o esto no mide nada.
    assert peor > 0.5, f"ninguna acción bloqueó lo suficiente para acotar el plazo: {medidas}"


def test_el_cliente_es_una_costura_de_pleno_derecho(cliente) -> None:  # noqa: ANN001
    """Mismas cuatro operaciones que `LocalGpioLink`, ni una más en la interfaz."""
    assert isinstance(cliente, GpioLink)
    for operacion in ("snapshot", "apply", "action", "subscribe"):
        assert callable(getattr(cliente, operacion))


def test_el_transporte_no_paga_dependencias_de_terceros() -> None:
    """Regla de oro 4: el proceso mínimo no crece por tener IPC.

    La allowlist de D1.3 ya vigila el proceso ENTERO (el servidor entra por
    `takab_edge.gpio`); esto mide el paquete `pinlink` por su cuenta, cliente
    incluido, que es el que NO vive dentro del dueño.
    """
    import subprocess
    import sys

    from test_gpio_process import _dependencias_no_autorizadas

    codigo = (
        "import sys, takab_edge.pinlink, takab_edge.pinlink.cli;"
        "sys.stdout.write('RAICES:' + ' '.join(sorted({m.split('.')[0] for m in sys.modules})))"
    )
    r = subprocess.run(  # noqa: S603
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        env={**os.environ, "GPIOZERO_PIN_FACTORY": "mock"},
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    raices = set(r.stdout.split("RAICES:")[1].split())
    assert _dependencias_no_autorizadas(raices) == []


# ---------------------------------------------------------------------------
# 5 · El proceso dueño y la CLI
# ---------------------------------------------------------------------------


def test_el_proceso_minimo_sirve_el_socket_tras_tomar_el_cerrojo(settings) -> None:  # noqa: ANN001
    """Requisito 7: `gpio/__main__` arranca el servidor con los relés ya construidos.

    El orden es el mecanismo: quien conteste por el socket tiene que ser ya el
    dueño de los pines, no un proceso que aún está decidiendo si lo es.

    Y sirve **aunque la puerta esté cerrada de fábrica**: este proceso existe
    para SER el dueño de los pines de todo lo demás, y un dueño con el que nadie
    puede hablar no es un traspaso, es un apagón.
    """
    from takab_edge.gpio.__main__ import run_gpio_process

    assert settings.gpio_serves_pins is False, "sin la puerta cerrada esto no mide nada"
    controlador = run_gpio_process(settings, block=False)
    try:
        assert controlador.servidor_de_pines is not None
        assert controlador._lock_fd is not None, "sirve el socket sin ser dueño de los pines"
        assert controlador._relays, "sirve el socket sin haber construido los relés"
    finally:
        controlador.stop()


def test_sd_notify_solo_avisa_LISTO_con_el_gabinete_de_pie(settings, tmp_path) -> None:  # noqa: ANN001
    """`Type=notify`: `systemctl start` debe volver cuando el proceso es DUEÑO.

    Con `Type=simple` vuelve cuando el proceso arrancó, que es otra cosa: el
    traspaso de propiedad de D3 se declararía terminado antes de serlo.
    """
    from takab_edge.gpio.__main__ import run_gpio_process

    ruta = tmp_path / "notify.sock"
    escucha = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    escucha.bind(str(ruta))
    escucha.settimeout(3.0)
    previo = os.environ.get("NOTIFY_SOCKET")
    os.environ["NOTIFY_SOCKET"] = str(ruta)
    try:
        controlador = run_gpio_process(settings, block=False)
        try:
            assert b"READY=1" in escucha.recv(256)
        finally:
            controlador.stop()
    finally:
        escucha.close()
        if previo is None:
            os.environ.pop("NOTIFY_SOCKET", None)
        else:
            os.environ["NOTIFY_SOCKET"] = previo


def test_sin_NOTIFY_SOCKET_el_aviso_es_un_no_op(settings) -> None:  # noqa: ANN001
    """NO-VACUIDAD del anterior: sin systemd delante no se escribe a ningún lado
    (y desde luego no se truena el arranque del camino de vida)."""
    from takab_edge.pinlink.server import notificar_systemd

    previo = os.environ.pop("NOTIFY_SOCKET", None)
    try:
        assert notificar_systemd("READY=1") is False
    finally:
        if previo is not None:
            os.environ["NOTIFY_SOCKET"] = previo


def test_la_cli_interroga_al_dueno_y_devuelve_su_estado(servidor, capsys) -> None:  # noqa: ANN001
    """`takab-gpioctl`: lo que `deploy.sh` y el traspaso necesitan desde el shell."""
    import json

    from takab_edge.pinlink.cli import main

    codigo = main(["--socket", servidor.ruta, "--json"])
    salida = capsys.readouterr().out
    assert codigo == 0
    estado = json.loads(salida)
    assert estado["running"] is True
    assert len(estado["relays"]) == 5


def test_la_cli_no_finge_un_gabinete_cuando_nadie_contesta(tmp_path, capsys) -> None:  # noqa: ANN001
    """Exit code ≠ 0 y sin JSON de mentira: `deploy.sh` decide con esto."""
    from takab_edge.pinlink.cli import main

    codigo = main(["--socket", str(tmp_path / "no-existe.sock"), "--json", "--timeout", "0.5"])
    capturado = capsys.readouterr()
    assert codigo != 0
    assert capturado.out.strip() == ""
    assert "no contesta" in capturado.err.lower() or "unreachable" in capturado.err.lower()


def test_la_cli_no_puede_ACTUAR_sobre_el_gabinete(servidor) -> None:  # noqa: ANN001
    """Decisión: la CLI INTERROGA, no acciona.

    Una CLI que accione es una segunda puerta a los actuadores, sin PIN, sin el
    registro de acciones del panel y sin el ack firmado de la nube. `deploy.sh`
    necesita PREGUNTAR quién es el dueño y cómo está, no silenciar sirenas.
    """
    from takab_edge.pinlink import cli

    fuente = Path(cli.__file__).read_text(encoding="utf-8")
    assert ".action(" not in fuente and ".apply(" not in fuente


# ---------------------------------------------------------------------------
# 6 · Coste: el transporte no puede comerse el presupuesto del reflejo
# ---------------------------------------------------------------------------


def test_una_ida_y_vuelta_por_el_socket_es_barata(gpio, ruta_socket) -> None:  # noqa: ANN001
    """Se MIDE, no se afirma — y se mide en ESTA máquina.

    La cota es holgada a propósito (10 ms de mediana): el reconocimiento midió
    0.017 ms de p50 en x86-64 y esto tiene que seguir pasando en el Pi 4 ARM, que
    **no se ha medido**. Lo que la cota defiende no es el número, es el orden de
    magnitud: si una operación costara decenas de ms, la secuencia de tier entera
    (que ya es UN solo lote desde D2/P1) dejaría de ser gratis.

    El reflejo SASMEX→sirena NO cruza el socket y por eso su presupuesto de
    <100 ms no depende de esta medición (gate #6, anclado aparte).

    El rate-limit se sube para esta medición y SOLO para ella: 50 lotes seguidos
    a toda velocidad no es un patrón de uso —la secuencia de tier es uno— y
    medir el freno en vez del transporte no diría nada de ninguno de los dos.
    """
    gpio.detener_servidor_de_pines()
    srv = PinLinkServer(gpio, ruta_socket, ops_por_s=2000)
    srv.start()
    try:
        cliente = IpcGpioLink(ruta=ruta_socket)
        cliente.start()
        try:
            assert _esperar(lambda: cliente.snapshot().running is True)
            muestras = []
            for _ in range(50):
                t0 = time.perf_counter()
                cliente.apply([(ActuatorChannel.SIREN, False)])
                muestras.append(time.perf_counter() - t0)
            muestras.sort()
            p50 = muestras[len(muestras) // 2]
            assert p50 < 0.010, f"ida y vuelta p50 = {p50 * 1000:.2f} ms"
        finally:
            cliente.stop()
    finally:
        srv.stop()


def test_el_dueno_no_gasta_nada_mientras_nadie_lo_escuche(gpio, servidor) -> None:  # noqa: ANN001
    """Sin suscriptores no hay emisor: 800 tests no pagan un sondeo a 20 Hz.

    NO-VACUIDAD: con un cliente conectado, el emisor SÍ existe y empuja.
    """
    assert servidor.emisor_vivo is False
    link = IpcGpioLink(ruta=servidor.ruta)
    link.start()
    try:
        assert _esperar(lambda: servidor.emisor_vivo is True)
        empujes = servidor.instantaneas_empujadas
        gpio.simulate_sasmex(active=True)
        assert _esperar(lambda: servidor.instantaneas_empujadas > empujes)
    finally:
        link.stop()


def test_un_cliente_que_no_drena_no_bloquea_el_camino_de_vida(gpio, servidor) -> None:  # noqa: ANN001
    """El empuje JAMÁS espera al cliente: la cola es acotada y se cierra al lleno.

    Un cliente colgado (proceso parado con SIGSTOP, disco de logs bloqueado) no
    puede convertirse en un `send()` bloqueante dentro del observador `sasmex`
    del dueño de los pines — que corre en el hilo del reflejo, justo después de
    energizar la sirena.
    """
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(servidor.ruta)
    s.sendall(cd.enmarcar({"id": 1, "op": "subscribe", "events": ["sasmex"]}))
    try:
        assert _esperar(lambda: servidor.emisor_vivo is True)
        # No se lee NADA del socket: el buffer del kernel se llena y el servidor
        # tiene que desahuciar al cliente en vez de bloquearse.
        limite = time.monotonic() + 20.0
        while time.monotonic() < limite and servidor.desahucios == 0:
            gpio.simulate_sasmex(active=True)
            gpio.reset()
            time.sleep(0.01)
        assert servidor.desahucios >= 1, "el servidor no desahució a un cliente que no drena"
        # …y el dueño sigue vivo y reflejando.
        gpio.simulate_sasmex(active=True)
        assert gpio.relay_state(ActuatorChannel.SIREN).energized is True
    finally:
        s.close()


def test_el_cierre_del_servidor_no_deja_hilos_sueltos(gpio, ruta_socket) -> None:  # noqa: ANN001
    gpio.detener_servidor_de_pines()
    antes = threading.active_count()
    srv = PinLinkServer(gpio, ruta_socket)
    srv.start()
    link = IpcGpioLink(ruta=ruta_socket)
    link.start()
    assert _esperar(lambda: link.snapshot().running is True)
    link.stop()
    srv.stop()
    assert _esperar(lambda: threading.active_count() <= antes, timeout=5.0), (
        f"quedaron hilos vivos: {threading.active_count()} > {antes}"
    )


def test_el_cliente_sobrevive_a_que_el_dueno_desaparezca(gpio, ruta_socket) -> None:  # noqa: ANN001
    """Y lo DICE: nada de seguir sirviendo la última instantánea para siempre."""
    gpio.detener_servidor_de_pines()
    srv = PinLinkServer(gpio, ruta_socket)
    srv.start()
    link = IpcGpioLink(ruta=ruta_socket, edad_maxima_s=0.3)
    link.start()
    try:
        assert _esperar(lambda: link.snapshot().running is True)
        srv.stop()
        limite = time.monotonic() + 3.0
        while time.monotonic() < limite:
            try:
                link.snapshot()
            except GpioLinkUnavailable:
                break
            time.sleep(0.02)
        else:
            pytest.fail("el cliente siguió sirviendo el estado de un dueño que ya no existe")
        with pytest.raises(GpioLinkUnavailable):
            link.action("reset")
        with pytest.raises(GpioLinkUnavailable):
            link.apply([(ActuatorChannel.SIREN, True)])
    finally:
        link.stop()


# ---------------------------------------------------------------------------
# 7 · El ensayo de D3: el gabinete ENTERO hablándole a su propio dueño
# ---------------------------------------------------------------------------


def test_de_fabrica_el_gabinete_sigue_con_la_costura_LOCAL(settings) -> None:  # noqa: ANN001
    """LÍMITE del paso: D2/P2 construye el transporte, **no lo enciende**."""
    from takab_edge.config import EdgeSettings
    from takab_edge.gpio_link import build_gpio_link

    assert EdgeSettings().gpio_link == "local"
    assert settings.gpio_link == "local"
    assert isinstance(build_gpio_link(settings, None), LocalGpioLink)
    # …y un valor con errata degrada a lo SEGURO, no deja al gabinete sin costura.
    raro = settings.model_copy(update={"gpio_link": "zmq"})
    assert isinstance(build_gpio_link(raro, None), LocalGpioLink)


def test_de_fabrica_el_gabinete_ni_siquiera_ATA_el_socket(settings) -> None:  # noqa: ANN001
    """La otra mitad del LÍMITE, que faltaba: «no lo enciende» incluye el SERVIDOR.

    `gpio_serve_enabled` venía en `True`, así que todo gabinete ataba el socket,
    levantaba el hilo aceptador y registraba `PinLinkServer._al_sasmex` como
    **callback #0 del reflejo** — con un coste en el hilo del botón que la
    latencia anclada del gate #6 **no puede ver**, porque esa medición termina
    antes de invocar callbacks. «Nadie se conecta todavía» no es lo mismo que
    «no está encendido».

    NO-VACUIDAD: la puerta se abre SOLA con `GPIO_LINK=ipc`, así que D3 sigue
    siendo UN interruptor y no dos — y el fallo peligroso (cliente encendido,
    servidor apagado) es inalcanzable por construcción.
    """
    from takab_edge.config import EdgeSettings

    assert EdgeSettings().gpio_serve_enabled is False
    assert settings.gpio_serves_pins is False
    controlador = GpioController(settings)
    controlador.start()
    try:
        assert controlador.servidor_de_pines is None, "el gabinete de fábrica ató el socket"
        assert not Path(settings.gpio_socket_file).exists()
        # …y el reflejo no tiene ni un observador del transporte delante.
        assert not any(
            type(getattr(cb, "__self__", None)).__name__ == "PinLinkServer"
            for cb in controlador._sasmex_callbacks
        ), "el servidor se coló como callback del reflejo con la puerta cerrada"
    finally:
        controlador.stop()

    # NO-VACUIDAD 1 · con `ipc` la puerta se abre sin tocar ninguna otra perilla.
    assert settings.model_copy(update={"gpio_link": "ipc"}).gpio_serves_pins is True
    # NO-VACUIDAD 2 · y la perilla explícita sigue sirviendo para el diagnóstico.
    assert settings.model_copy(update={"gpio_serve_enabled": True}).gpio_serves_pins is True


def test_el_gabinete_ENTERO_funciona_hablando_por_el_socket(settings) -> None:  # noqa: ANN001
    """El ensayo general de D3, con `GPIO_LINK=ipc` y el dueño AQUÍ DENTRO.

    Es la forma del primer paso de D3: el mismo proceso es dueño y cliente, así
    que el transporte se acredita en el Pi real **sin traspasar la propiedad de
    los pines** (que es un paso aparte, con gate físico). Aquí se comprueba que
    el gabinete completo —los cinco consumidores, los dos observadores, el panel
    LAN y la secuencia de actuación— funciona con la costura del socket puesta.
    """
    from takab_edge.supervisor import EdgeSupervisor

    cfg = settings.model_copy(update={"gpio_link": "ipc"})
    sup = EdgeSupervisor(cfg, seedlink_source=None)
    sup.start()
    try:
        costura = sup.gpio_link
        assert isinstance(costura, IpcGpioLink)
        for nombre, consumidor in (
            ("actuators.relay", sup.actuators._relay),
            ("audio", sup.audio),
            ("drill", sup.drill),
            ("health", sup.health),
            ("local_api", sup.local_api),
        ):
            assert consumidor._link is costura, f"{nombre} no recibió la costura del socket"

        # 1) El panel LAN sirve estado REAL leído por el socket.
        _host, port = sup.local_api.address
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5) as resp:
            estado = json.loads(resp.read())
        assert estado["relays_status"]["reason"] not in ("gpio_unreachable", "gpio_error")
        assert len(estado["relays"]) == 5

        # 2) El reflejo sigue siendo del DUEÑO (no cruza), y el observador del
        #    supervisor —el que publica a la nube— sí cruza.
        publicados: list[str] = []
        sup.cloud.publish = lambda topic, payload: publicados.append(topic)
        disparados = _espiar_la_secuencia(sup)
        sup.gpio.simulate_sasmex(active=True)
        assert sup.gpio.relay_state(ActuatorChannel.SIREN).energized is True
        assert _esperar(lambda: "takab/events" in publicados), (
            "el evento SASMEX no llegó a la nube a través del socket"
        )
        # …y la SECUENCIA QUE ESA ALERTA DISPARÓ se ejecutó de verdad.
        #
        # Sin estas líneas este test era TEATRO: recorría exactamente el camino
        # que se autobloqueaba —observador del supervisor en el hilo lector del
        # cliente ⇒ `apply` esperando una respuesta que sólo ese hilo puede
        # leer— y pasaba igual, porque sólo miraba si el evento llegó a
        # `takab/events`. Los cinco ACKs de la secuencia decían «la orden NO se
        # puede dar por ejecutada» y nadie los leía. La actuación que sí
        # verificaba (punto 3) se lanza desde el hilo principal, donde no hay
        # reentrada.
        assert _esperar(lambda: len(disparados) >= len(_RELES)), (
            f"la alerta SASMEX no disparó la secuencia por el socket ({len(disparados)} ACKs)"
        )
        fallidos = [f"{a.channel.value}: {a.detail}" for a in disparados if not a.success]
        assert not fallidos, (
            "la alerta SASMEX reportó la protección CAÍDA por el socket: " + "; ".join(fallidos)
        )

        # 3) La secuencia de actuación comanda relés de verdad por el socket.
        sup.gpio.reset()
        from takab_edge.contracts import ActuatorAction, ActuatorCommand

        acks = sup.actuators.execute_sequence(
            [
                ActuatorCommand(channel=c, action=ActuatorAction.ACTIVATE, event_id="EV-IPC")
                for c in _RELES
            ]
        )
        assert all(a.success for a in acks)
        assert all(sup.gpio.is_activated(c) for c in _RELES)
    finally:
        sup.stop()


def _un_sismo_en_el_gabinete_entero(settings, costura: str) -> dict:  # noqa: ANN001
    """Un SASMEX real en un `EdgeSupervisor` de verdad, por la costura pedida.

    Devuelve lo que el gabinete REPORTA y lo que el gabinete HIZO, para poder
    compararlos entre las dos costuras: son las dos mitades que se contradecían.
    """
    from takab_edge.supervisor import EdgeSupervisor

    cfg = settings.model_copy(update={"gpio_link": costura})
    sup = EdgeSupervisor(cfg, seedlink_source=None)
    sup.start()
    publicados: list[str] = []
    sup.cloud.publish = lambda topic, payload: publicados.append(topic)
    disparados = _espiar_la_secuencia(sup)
    try:
        assert sup.drill.start_drill("DRILL-IPC", 60.0)[0] is True
        t0 = time.monotonic()
        sup.gpio.simulate_sasmex(active=True)
        _esperar(lambda: len(disparados) >= len(_RELES))
        _esperar(lambda: sup.drill.status().get("aborted") is True)
        abortado_en = time.monotonic() - t0
        _esperar(lambda: "takab/events" in publicados)
        return {
            "acks_ok": sorted(a.channel.value for a in disparados if a.success),
            "acks_fallidos": sorted(a.channel.value for a in disparados if not a.success),
            "reles": {c.value: sup.gpio.is_activated(c) for c in _RELES},
            "evento_en_la_nube": "takab/events" in publicados,
            "simulacro_abortado": sup.drill.status().get("aborted") is True,
            "abortado_en_s": abortado_en,
        }
    finally:
        sup.stop()


@pytest.mark.parametrize("costura", ["local", "ipc"])
def test_un_SASMEX_actua_IGUAL_por_las_dos_costuras(settings, costura: str) -> None:  # noqa: ANN001
    """LA PRUEBA QUE CIERRA D3. Un sismo por el socket tiene que hacer lo mismo.

    El defecto que cierra: `supervisor._on_sasmex` se registra por la costura y,
    con `ipc`, el cliente lo invocaba EN SU ÚNICO HILO LECTOR. Ese observador
    actúa (`_act_and_publish` → `RelayActuator` → `link.apply`) y `apply` espera
    una respuesta que sólo ese hilo puede leer: **timeout garantizado**.

    Y mentía en las DOS direcciones a la vez, que es lo peor que puede hacer un
    gabinete: los cinco ACKs decían «la orden NO se puede dar por ejecutada» —la
    nube ve la protección caída— **mientras los relés SÍ se accionaban**, porque
    el servidor ejecutó el lote y el cliente nunca llegó a leer la respuesta.

    Se mide contra `local`, que es el gabinete de hoy: la conformidad no es «no
    truena», es «hace lo mismo».
    """
    visto = _un_sismo_en_el_gabinete_entero(settings, costura)
    esperado = sorted(c.value for c in _RELES)
    assert visto["acks_fallidos"] == [], (
        f"[{costura}] la alerta reportó la protección CAÍDA en {visto['acks_fallidos']}"
    )
    assert visto["acks_ok"] == esperado, f"[{costura}] ACKs con éxito: {visto['acks_ok']}"
    assert all(visto["reles"].values()), f"[{costura}] relés sin energizar: {visto['reles']}"
    assert visto["evento_en_la_nube"] is True, f"[{costura}] el evento no llegó a la nube"
    # El aborto del simulacro es el otro observador de la misma cadena, y con el
    # autobloqueo se retrasaba 2 s (el plazo entero de `apply`) — dos segundos de
    # voceo diciéndole al edificio «ES UN SIMULACRO» durante un sismo real.
    assert visto["simulacro_abortado"] is True, f"[{costura}] el simulacro no se abortó"
    assert visto["abortado_en_s"] < 1.0, (
        f"[{costura}] el aborto del simulacro tardó {visto['abortado_en_s']:.3f}s"
    )


def test_la_ruta_del_socket_sale_de_la_config_y_es_atable(settings) -> None:  # noqa: ANN001
    """`AF_UNIX` corta la ruta a ~108 bytes: si no cabe, se dice, no se trunca."""
    assert len(settings.gpio_socket_file.encode()) < 100
    largo = "/tmp/" + "x" * 120 + "/gpio.sock"  # noqa: S108
    with pytest.raises(OSError) as exc:
        PinLinkServer(None, largo).start()
    assert "108" in str(exc.value) or exc.value.errno in (errno.ENAMETOOLONG, errno.EINVAL)
