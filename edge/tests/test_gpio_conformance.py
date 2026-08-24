"""[T-2.70.a · D2/P2] CONFORMIDAD: las dos costuras no pueden divergir en silencio.

Todo lo que hay en este archivo corre **DOS veces**: contra `LocalGpioLink` (la
llamada directa de D2/P1) y contra `IpcGpioLink` conectado a un servidor real que
envuelve **ESE MISMO** `GpioController`. Mismo dueño, mismos pines, mismo estado:
lo único que cambia es si la operación cruza un socket. Es lo único que impide
que la implementación nueva se desvíe de la vieja sin que nada se queje.

CÓMO SE DERIVA (y por qué no es una lista escrita a mano)
---------------------------------------------------------
Van cinco casos en esta sesión de guardas que ENUMERAN y se quedan ciegas ante el
siguiente elemento. Aquí la suite se deriva por tres vías, y ninguna es una lista
de tests:

1. **Por implementación.** El fixture `enlace` está parametrizado (`local`/`ipc`),
   así que cualquier test que lo pida corre en las dos. Y
   `test_meta_toda_prueba_de_este_modulo_corre_en_LAS_DOS_implementaciones`
   comprueba que **todo** test del módulo se haya COLECTADO en las dos variantes
   (`item.callspec.params`, censado en `conftest.pytest_itemcollected`) — no que
   su firma nombre el fixture, que es lo que medía antes y no distinguía «pide el
   fixture» de «lo sombrea con un `@parametrize`». La lista es de EXCEPCIONES
   declaradas (:data:`_NO_SON_DE_CONFORMIDAD`), no de miembros — un test nuevo es
   conforme por defecto y, si no lo es, pone la corrida en rojo hasta que alguien
   escriba aquí por qué.

2. **Por superficie.** Los casos salen de las tablas del contrato, no de nombres:
   `GPIO_ACTIONS` (una acción nueva estrena caso el día que se declara),
   `GPIO_EVENTS` (con su tabla de disparadores cruzada contra ella) y
   `GpioSnapshot.__dataclass_fields__` (un campo nuevo se compara solo).

3. **Por oráculo.** El comparador campo a campo se prueba CONTRA SÍ MISMO: para
   cada campo del contrato existe un caso que le da una costura mentirosa **en
   ese campo** y exige que el oráculo la cace. Un oráculo que se saltara un campo
   —o que dejara de comparar— se delata ahí, no dentro de un test verde.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from takab_edge.contracts import ActuatorChannel, SasmexSignal
from takab_edge.gpio import GpioController
from takab_edge.gpio_link import (
    GPIO_ACTIONS,
    GPIO_EVENTS,
    ChannelOutcome,
    GpioActionNotAllowed,
    GpioEventNotAllowed,
    GpioLink,
    GpioSnapshot,
    LocalGpioLink,
)
from takab_edge.pinlink import IpcGpioLink, PinLinkServer

from conftest import SIN_ENLACE

_RELES = (
    ActuatorChannel.SIREN,
    ActuatorChannel.STROBE,
    ActuatorChannel.GAS_VALVE,
    ActuatorChannel.ELEVATOR,
    ActuatorChannel.DOOR_RETAINER,
)

#: Tests de este módulo que NO son de conformidad, con su razón. Todo lo demás
#: tiene que correr en las DOS implementaciones (ver el docstring del módulo).
_NO_SON_DE_CONFORMIDAD: dict[str, str] = {
    "test_meta_toda_prueba_de_este_modulo_corre_en_LAS_DOS_implementaciones": (
        "es la guarda de pertenencia: se mide a sí misma y a sus hermanas, así "
        "que no puede exigirse el enlace a sí misma"
    ),
    "test_meta_la_guarda_de_pertenencia_no_esta_podrida": (
        "no-vacuidad de la guarda anterior: corre sobre censos de mentira, no sobre el gabinete"
    ),
    "test_meta_la_tabla_de_disparadores_cubre_TODOS_los_eventos": (
        "cruza dos tablas del contrato (`GPIO_EVENTS` × disparadores); no toca ninguna costura"
    ),
    "test_meta_el_oraculo_caza_una_divergencia_en_CUALQUIER_campo": (
        "prueba el ORÁCULO contra una costura mentirosa fabricada, no una "
        "implementación real: parametrizarlo por implementación mediría lo mismo "
        "dos veces"
    ),
}


# ---------------------------------------------------------------------------
# El montaje: un dueño, un registrador, dos costuras
# ---------------------------------------------------------------------------


class _Registrador:
    """Delegador que ANOTA qué métodos del dueño se llamaron, y desde dónde.

    Se interpone entre las dos costuras y el `GpioController`, no dentro de una
    de ellas: así «la acción llegó al dueño» se mide igual en las dos, y una
    costura que devolviera un resultado plausible sin haber tocado el gabinete
    (una caché de escritura, un stub) se ve.
    """

    def __init__(self, real: Any) -> None:
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "llamadas", [])

    def __getattr__(self, nombre: str) -> Any:
        real = object.__getattribute__(self, "_real")
        atributo = getattr(real, nombre)
        if not callable(atributo):
            return atributo

        def _anotado(*args: Any, **kwargs: Any) -> Any:
            object.__getattribute__(self, "llamadas").append(nombre)
            return atributo(*args, **kwargs)

        return _anotado


@pytest.fixture
def ajustes(settings):  # noqa: ANN001, ANN201
    """Mismos ajustes de siempre, con las esperas del gabinete ENCOGIDAS.

    Las acciones de la lista blanca DUERMEN por diseño (5 s de sostenimiento en
    la prueba local, ~1.6 s de recorrido en el self-test). Encogerlas no cambia
    lo que se mide —el camino de la orden y su resultado— y evita que la suite de
    conformidad tarde un minuto por implementación.
    """
    return settings.model_copy(
        update={
            "siren_test_duration_s": 0.05,
            "actuation_test_hold_s": 0.05,
            "self_test_pulse_ms": 1,
            "self_test_gap_ms": 0,
            "sasmex_test_window_s": 0.5,
        }
    )


@pytest.fixture
def gpio(ajustes):  # noqa: ANN001, ANN201
    controlador = GpioController(ajustes)
    controlador.start()
    # La puerta de servicio que el propio dueño abre envuelve al controlador
    # CRUDO; aquí se monta una que envuelve al registrador, para poder medir que
    # la orden llegó de verdad al gabinete.
    controlador.detener_servidor_de_pines()
    try:
        yield controlador
    finally:
        controlador.stop()


@pytest.fixture
def registrador(gpio) -> _Registrador:  # noqa: ANN001
    return _Registrador(gpio)


@pytest.fixture(params=["local", "ipc"])
def enlace(request, registrador, ajustes):  # noqa: ANN001, ANN201
    """LA costura bajo prueba. Dos implementaciones, UN dueño de pines."""
    if request.param == "local":
        yield LocalGpioLink(registrador)
        return
    servidor = PinLinkServer(registrador, ajustes.gpio_socket_file)
    servidor.start()
    cliente = IpcGpioLink(ruta=servidor.ruta)
    cliente.start()
    try:
        yield cliente
    finally:
        cliente.stop()
        servidor.stop()


def _esperar(condicion, timeout: float = 3.0) -> bool:  # noqa: ANN001
    """Converge la caché del cliente. Con `LocalGpioLink` vuelve al primer intento."""
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        try:
            if condicion():
                return True
        except Exception:  # noqa: BLE001 — la caché puede no existir todavía
            pass
        time.sleep(0.005)
    return False


# ---------------------------------------------------------------------------
# El ORÁCULO: la instantánea, campo a campo, derivada del contrato
# ---------------------------------------------------------------------------

#: Campos que no se comparan contra el dueño, con su razón. `age_s` es el único:
#: mide el tiempo transcurrido desde que el dato llegó a quien lo lee, así que
#: por definición vale 0.0 en la costura local y algo mayor en la del socket —
#: exigir igualdad ahí sería exigir que el transporte no tarde nada.
_CAMPOS_NO_COMPARABLES: dict[str, str] = {
    "age_s": "es la EDAD medida por el lector; en la costura local siempre es 0.0",
    # [T-2.165] Lo rellena QUIEN LEE comparando lo que el dueño dijo saber con lo
    # que este cliente espera, así que en la costura LOCAL es siempre vacío (no
    # hay dos versiones) y en la del socket depende del otro lado. Compararlo
    # contra el dueño sería preguntarle algo que él no puede responder.
    "campos_desconocidos": (
        "lo deriva el lector de la declaración del dueño; el dueño no lo conoce"
    ),
}

#: Campos que SÍ se comparan, pero con tolerancia, porque CORREN SOLOS entre las
#: dos lecturas del oráculo. Es una tolerancia, no una exención: una divergencia
#: real (la del test de no-vacuidad, 7.5 s) sigue cayendo.
_TOLERANCIAS: dict[str, float] = {
    "test_mode_remaining_s": 0.5,  # cuenta atrás monotónica de la ventana WR-1
}


def comparar_instantanea(snap: GpioSnapshot, esperado: GpioSnapshot) -> None:
    """Oráculo de conformidad: campo a campo, derivado de `__dataclass_fields__`.

    No enumera: si mañana `GpioSnapshot` gana un campo, este oráculo lo compara
    sin que nadie lo toque, y el códec del transporte tiene que llevarlo o el
    caso `ipc` se cae.
    """
    diferencias = []
    for campo in GpioSnapshot.__dataclass_fields__:
        if campo in _CAMPOS_NO_COMPARABLES:
            continue
        visto, quiero = getattr(snap, campo), getattr(esperado, campo)
        tolerancia = _TOLERANCIAS.get(campo)
        if (
            tolerancia is not None
            and isinstance(visto, (int, float))
            and isinstance(quiero, (int, float))
        ):
            if abs(float(visto) - float(quiero)) <= tolerancia:
                continue
        elif visto == quiero:
            continue
        diferencias.append(f"{campo}: costura={visto!r} dueño={quiero!r}")
    assert not diferencias, "la costura no dice lo mismo que el dueño de los pines:\n" + "\n".join(
        f"  · {d}" for d in diferencias
    )


class _Mentirosa:
    """Costura que copia al dueño salvo en UN campo. Instrumento del oráculo."""

    def __init__(self, real: Any, campo: str, valor: Any) -> None:
        self._real, self._campo, self._valor = real, campo, valor

    def snapshot(self) -> GpioSnapshot:
        base = self._real.snapshot()
        campos = {
            n: getattr(base, n) for n in GpioSnapshot.__dataclass_fields__ if n != self._campo
        }
        return GpioSnapshot(**campos, **{self._campo: self._valor})


# ---------------------------------------------------------------------------
# 1 · Conformidad derivada de la SUPERFICIE del contrato
# ---------------------------------------------------------------------------


def test_la_instantanea_coincide_campo_a_campo_con_el_dueno(enlace, gpio) -> None:  # noqa: ANN001
    """Toda la instantánea, en un gabinete con estado de verdad.

    Se espera a la ÚLTIMA mutación (`test_mode_active`) y no a la primera, y eso
    dice algo del diseño que conviene tener escrito: un cambio hecho DIRECTAMENTE
    sobre el dueño —no a través de la costura— tarda en llegar a la caché lo que
    tarde el siguiente empuje (sondeo a 20 Hz, la misma granularidad que ya tenía
    el watcher de sirena leyendo en memoria). Lo que NO tiene retraso es lo que se
    ordena por la propia costura: la respuesta llega después del empuje del estado
    posterior, así que leer lo propio escrito es inmediato.

    Y como la instantánea es ATÓMICA, esperar al último cambio basta: cualquier
    instantánea con el modo prueba armado se tomó después del `set_relay`.
    """
    gpio.simulate_sasmex(active=True)
    gpio.set_relay(ActuatorChannel.GAS_VALVE, True)
    gpio.arm_test_mode(30.0)
    assert _esperar(lambda: enlace.snapshot().test_mode_active is True)
    comparar_instantanea(enlace.snapshot(), gpio.snapshot())
    assert {r.channel for r in enlace.snapshot().relays} == set(_RELES)


@pytest.mark.parametrize("accion", sorted(GPIO_ACTIONS))
def test_cada_accion_de_la_lista_blanca_llega_al_dueno(enlace, gpio, registrador, accion) -> None:  # noqa: ANN001
    """DERIVADO de `GPIO_ACTIONS`: una acción nueva estrena caso el día que se
    declara, en las dos implementaciones, sin que nadie escriba un test.

    Se mide lo que de verdad importa de una orden: que **llegó al dueño** (el
    registrador la vio) y que **lo que devolvió sobrevivió al viaje** idéntico a
    lo que devuelve una llamada directa.
    """
    directo = getattr(gpio, GPIO_ACTIONS[accion])()
    registrador.llamadas.clear()

    por_la_costura = enlace.action(accion)

    assert GPIO_ACTIONS[accion] in registrador.llamadas, (
        f"la acción {accion!r} no llegó al dueño de los pines: la costura contestó "
        "sin tocar el gabinete"
    )
    assert _json(por_la_costura) == _json(directo), (
        f"lo que devuelve {accion!r} cambió al cruzar la costura"
    )


def _json(valor: Any) -> Any:
    """Normaliza a JSON: una tupla y una lista son el mismo resultado."""
    return json.loads(json.dumps(valor, default=str))


#: Cómo se provoca cada evento EN EL DUEÑO. Cruzada contra `GPIO_EVENTS` por
#: `test_meta_la_tabla_de_disparadores_cubre_TODOS_los_eventos`: un evento nuevo
#: sin disparador pone la corrida en rojo en vez de quedarse sin medir.
_DISPARADORES: dict[str, Any] = {
    "sasmex": lambda gpio: gpio.simulate_sasmex(active=True),
    "silence": lambda gpio: gpio.silence_audibles(True),
}


@pytest.mark.parametrize("evento", sorted(GPIO_EVENTS))
def test_cada_evento_de_la_costura_llega_al_observador(enlace, gpio, evento) -> None:  # noqa: ANN001
    """DERIVADO de `GPIO_EVENTS`. Son los dos observadores que el supervisor
    cablea: `_on_sasmex` (que publica el evento a la nube y abre incidente) y
    `drill.on_sasmex` (que aborta el simulacro ante una alerta real)."""
    recibidos: list[Any] = []
    enlace.subscribe(evento, recibidos.append)
    assert _esperar(lambda: enlace.snapshot().running is True)

    _DISPARADORES[evento](gpio)

    assert _esperar(lambda: len(recibidos) == 1), (
        f"el observador de {evento!r} no se enteró a través de la costura"
    )


def test_la_costura_rechaza_lo_que_no_esta_declarado(enlace) -> None:  # noqa: ANN001
    """La tabla es CERRADA en las dos implementaciones, y `drive_all_safe` no está.

    Exponerlo dejaría el gas cerrado y las puertas sueltas hasta que alguien
    fuera físicamente al gabinete (`_safed` es durable: solo `reset()` lo levanta).
    """
    assert "drive_all_safe" not in GPIO_ACTIONS
    with pytest.raises(GpioActionNotAllowed):
        enlace.action("drive_all_safe")
    with pytest.raises(GpioEventNotAllowed):
        enlace.subscribe("cualquier_cosa", lambda *_: None)
    assert not hasattr(enlace, "drive_all_safe")


# ---------------------------------------------------------------------------
# 2 · Conformidad de COMPORTAMIENTO: el gabinete hace lo mismo por las dos vías
# ---------------------------------------------------------------------------


def test_es_una_costura_de_pleno_derecho(enlace) -> None:  # noqa: ANN001
    assert isinstance(enlace, GpioLink)


def test_el_lote_de_tier_entero_cruza_como_UNA_peticion(enlace, gpio) -> None:  # noqa: ANN001
    """La secuencia de actuación: cinco canales, una orden, cinco resultados."""
    resultados = enlace.apply([(c, True) for c in _RELES])
    assert [r.channel for r in resultados] == list(_RELES)
    assert all(isinstance(r, ChannelOutcome) and r.ok for r in resultados)
    assert all(gpio.is_activated(c) for c in _RELES)


def test_un_canal_malo_del_lote_no_aborta_a_los_demas(enlace, gpio) -> None:  # noqa: ANN001
    """Aislamiento POR CANAL: un lote todo-o-nada dejaría el gas, el ascensor y
    las puertas sin comandar por culpa de un canal desconocido."""
    resultados = enlace.apply(
        [
            (ActuatorChannel.SIREN, True),
            (ActuatorChannel.SYSTEM, True),  # canal LÓGICO: no gobierna relé
            (ActuatorChannel.GAS_VALVE, True),
        ]
    )
    assert [r.ok for r in resultados] == [True, False, True]
    assert gpio.is_activated(ActuatorChannel.SIREN)
    assert gpio.is_activated(ActuatorChannel.GAS_VALVE)


def test_el_reflejo_sasmex_se_ve_por_la_costura_pero_NO_pasa_por_ella(enlace, gpio) -> None:  # noqa: ANN001
    """Gate #6, medido en las dos implementaciones.

    El reflejo energiza sirena y estrobo DENTRO del dueño, antes de que ningún
    observador corra y sin tocar el transporte. La costura solo lo REPORTA. Aquí
    se mide que lo reporta igual por las dos vías y que la latencia medida por el
    propio dueño sigue bajo presupuesto — el socket no participa.
    """
    gpio.simulate_sasmex(active=True)
    for canal in (ActuatorChannel.SIREN, ActuatorChannel.STROBE):
        assert gpio.relay_state(canal).energized is True
    assert _esperar(lambda: enlace.snapshot().siren_sounding is True)
    snap = enlace.snapshot()
    assert snap.sasmex_active is True and snap.alert_latched is True
    assert snap.last_reflex_latency_s is not None and snap.last_reflex_latency_s < 0.100


def test_el_silencio_del_operador_calla_la_sirena_y_deja_el_estrobo(enlace, gpio) -> None:  # noqa: ANN001
    """NFPA-72: silenciar es del canal AUDIBLE; la alerta visual sigue."""
    gpio.simulate_sasmex(active=True)
    assert _esperar(lambda: enlace.snapshot().siren_sounding is True)

    enlace.action("silence", silenced=True)
    snap = enlace.snapshot()
    assert snap.siren_sounding is False and snap.audible_silenced is True
    assert snap.alert_latched is True, "silenciar borró la alerta"
    estrobo = {r.channel: r for r in snap.relays}[ActuatorChannel.STROBE]
    assert estrobo.activated is True, "el silencio apagó la alerta VISUAL"


def test_cerrar_la_alerta_desde_la_costura_devuelve_el_gabinete_a_reposo(enlace, gpio) -> None:  # noqa: ANN001
    gpio.simulate_sasmex(active=True)
    assert _esperar(lambda: enlace.snapshot().alert_latched is True)
    enlace.action("reset")
    snap = enlace.snapshot()
    assert snap.sasmex_active is False and snap.alert_latched is False
    assert snap.siren_sounding is False
    assert not any(r.activated for r in snap.relays)


def test_el_modo_prueba_del_wr1_se_arma_y_se_desarma_por_la_costura(enlace) -> None:  # noqa: ANN001
    """Lo que decide si un disparo se publica a la nube (T-1.69): leerlo mal
    despierta un edificio o calla un sismo."""
    ventana = enlace.action("arm_test_mode")
    assert ventana > 0
    snap = enlace.snapshot()
    assert snap.test_mode_active is True and 0 < snap.test_mode_remaining_s <= ventana
    enlace.action("disarm_test_mode")
    assert enlace.snapshot().test_mode_active is False


def test_el_autodiagnostico_jamas_energiza_la_sirena(enlace, gpio) -> None:  # noqa: ANN001
    """T-1.59: un self-test que sonara sería una falsa alarma provocada por
    nosotros. La sirena solo se REPORTA."""
    resultado = enlace.action("cabinet_self_test")
    assert resultado["ok"] is True
    assert resultado["relays"]["siren"]["pulsed"] is False
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is False


def test_la_prueba_local_sostiene_los_audibles_y_no_alerta_a_nadie(enlace, gpio) -> None:  # noqa: ANN001
    """T-1.67: ejercita el gabinete SIN abrir incidente ni notificar."""
    avisos: list[SasmexSignal] = []
    enlace.subscribe("sasmex", avisos.append)
    assert _esperar(lambda: enlace.snapshot().running is True)

    resultado = enlace.action("actuation_test")

    assert resultado["ok"] is True
    assert resultado["relays"]["siren"]["held"] is True
    time.sleep(0.2)
    assert avisos == [], "la prueba local se publicó como alerta"
    assert enlace.snapshot().sasmex_active is False


def test_una_alerta_viva_rechaza_las_pruebas(enlace, gpio) -> None:  # noqa: ANN001
    """El guard de seguridad cruza igual: nada de pulsar relés sobre un sismo."""
    gpio.simulate_sasmex(active=True)
    assert _esperar(lambda: enlace.snapshot().sasmex_active is True)
    for accion in ("cabinet_self_test", "actuation_test"):
        resultado = enlace.action(accion)
        assert resultado["ok"] is False
        assert "alerta" in resultado["reason"]


def test_el_estado_de_los_reles_conserva_su_polaridad_fail_safe(enlace) -> None:  # noqa: ANN001
    """NO/NC/fail_close: invertir esto en el viaje dejaría el gas al revés."""
    estados = {r.channel: r for r in enlace.snapshot().relays}
    assert estados[ActuatorChannel.SIREN].energized is False
    assert estados[ActuatorChannel.GAS_VALVE].energized is True  # abierto = energizado
    assert estados[ActuatorChannel.DOOR_RETAINER].energized is True  # retiene
    assert not any(r.activated for r in estados.values())

    enlace.apply([(ActuatorChannel.GAS_VALVE, True)])
    gas = {r.channel: r for r in enlace.snapshot().relays}[ActuatorChannel.GAS_VALVE]
    assert gas.energized is False and gas.activated is True  # CERRADO


def test_dos_lectores_concurrentes_ven_estados_coherentes(enlace, gpio) -> None:  # noqa: ANN001
    """La instantánea es atómica en las dos implementaciones: jamás un enclave
    vivo con la sirena en reposo (que el panel pintaría como avería)."""
    parar = threading.Event()
    incoherentes: list[GpioSnapshot] = []

    def _leer() -> None:
        while not parar.is_set():
            try:
                snap = enlace.snapshot()
            except Exception:  # noqa: BLE001
                continue
            if snap.sasmex_active and not (snap.siren_sounding or snap.audible_silenced):
                incoherentes.append(snap)

    hilos = [threading.Thread(target=_leer, daemon=True) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for _ in range(20):
        gpio.simulate_sasmex(active=True)
        time.sleep(0.005)
        gpio.reset()
    parar.set()
    for hilo in hilos:
        hilo.join(2.0)
    assert incoherentes == [], "instantánea con el enclave y el relé de dos momentos distintos"


# ---------------------------------------------------------------------------
# 3 · Meta: las guardas que impiden que esta suite se quede ciega
# ---------------------------------------------------------------------------


#: Las dos variantes que TIENE que haber instanciado cada test de este archivo.
_VARIANTES = frozenset({"local", "ipc"})


def variantes_huerfanas(censo: dict[str, set], exentos: dict[str, str]) -> list[str]:
    """Tests del censo que NO se colectaron en las dos variantes, con lo que sí.

    Mide lo que pytest **colectó**, no lo que la firma promete. Es la diferencia
    que importa: una guarda que lee nombres en una firma no distingue «pide el
    fixture `enlace`» de «lo SOMBREA con un `@parametrize`», y la variante que
    sombrea jamás instancia `local`/`ipc`. Aquí eso se ve solo, porque lo que se
    compara son los valores con los que el ítem existe de verdad.
    """
    huerfanos = []
    for nombre, variantes in sorted(censo.items()):
        if not nombre.startswith("test_") or nombre in exentos:
            continue
        faltan = _VARIANTES - variantes
        if faltan:
            visto = sorted(variantes, key=repr)
            huerfanos.append(f"{nombre} (le falta {sorted(faltan)}; colectado con {visto})")
    return huerfanos


def test_meta_toda_prueba_de_este_modulo_corre_en_LAS_DOS_implementaciones() -> None:
    """LA GUARDA DE PERTENENCIA, medida sobre lo COLECTADO.

    La versión anterior infería la pertenencia de `inspect.signature(...)` sobre
    `vars(modulo)` filtrado por `inspect.isfunction`, y tenía DOS agujeros por los
    que pytest colectaba y ejecutaba tests que sólo veían una costura:

    * un método dentro de `class TestIntruso:` — una clase no es `isfunction`, así
      que ni se miraba;
    * un `@pytest.mark.parametrize("enlace", [...])` que **SOMBREA** el fixture —
      el nombre sí está en la firma, y la guarda decía «conforme» mientras las
      variantes `local`/`ipc` no se instanciaban NUNCA. Ésta es la peligrosa: se
      cuela **pareciendo** conforme.

    Medir `item.callspec.params` tapa las dos y, de paso, la tercera (firmas con
    `**kwargs`): lo que existe es lo que pytest instanció.

    Es fail-CLOSED: la lista es de excepciones DECLARADAS, no de miembros.
    """
    from conftest import VARIANTES_COLECTADAS

    censo = VARIANTES_COLECTADAS.get(Path(__file__).name, {})
    assert censo, "el censo de variantes llegó vacío: la guarda no está midiendo nada"
    huerfanos = variantes_huerfanas(censo, _NO_SON_DE_CONFORMIDAD)
    assert not huerfanos, (
        f"estos tests viven en la suite de CONFORMIDAD pero NO se colectaron contra "
        f"las dos costuras: {huerfanos}. O piden el fixture `enlace` sin sombrearlo "
        "(y entonces corren contra la costura local y contra el socket, que es de lo "
        "que va este archivo), o se declaran en `_NO_SON_DE_CONFORMIDAD` con su razón."
    )
    # …y las excepciones declaradas existen de verdad: una lista con nombres
    # muertos autorizaría de más sin que nada lo dijera.
    fantasmas = [n for n in _NO_SON_DE_CONFORMIDAD if n not in censo]
    assert not fantasmas, f"exenciones declaradas para tests que ya no existen: {fantasmas}"


def test_meta_la_guarda_de_pertenencia_no_esta_podrida() -> None:
    """NO-VACUIDAD de la guarda: se la hace correr sobre censos de mentira.

    Los tres casos son los tres que la guarda anterior dejaba pasar o cazaba, para
    que se vea que el cambio no relaja nada y cierra dos agujeros.
    """
    conforme = {"test_bueno": {"local", "ipc"}}
    assert variantes_huerfanas(conforme, {}) == []

    # 1 · método dentro de una clase: pytest lo colecta, `isfunction` no lo veía.
    intruso = {**conforme, "test_dentro_de_una_clase": {SIN_ENLACE}}
    assert variantes_huerfanas(intruso, {}), "un método de clase se cuela sin costura"

    # 2 · EL PELIGROSO: `@parametrize("enlace", ...)` que sombrea el fixture. El
    #     nombre está en la firma —la guarda vieja decía «conforme»— y las dos
    #     variantes reales no se instancian jamás.
    sombra = {**conforme, "test_sombra": {1, 2}}
    assert variantes_huerfanas(sombra, {}), "un parametrize que sombrea el fixture se cuela"

    # 3 · media conformidad es no-conformidad: colectado sólo contra `local`.
    assert variantes_huerfanas({"test_a_medias": {"local"}}, {})

    # …y la exención DECLARADA sigue siendo la única vía de salir.
    assert variantes_huerfanas(intruso, {"test_dentro_de_una_clase": "razón"}) == []


def test_meta_la_tabla_de_disparadores_cubre_TODOS_los_eventos() -> None:
    """Cruce de tablas: un evento nuevo en `GPIO_EVENTS` sin forma de provocarlo
    dejaría su caso de conformidad sin medir nada."""
    assert set(_DISPARADORES) == set(GPIO_EVENTS), (
        f"la tabla de disparadores y `GPIO_EVENTS` divergieron: "
        f"{set(GPIO_EVENTS) ^ set(_DISPARADORES)}"
    )


@pytest.mark.parametrize(
    "campo", sorted(set(GpioSnapshot.__dataclass_fields__) - set(_CAMPOS_NO_COMPARABLES))
)
def test_meta_el_oraculo_caza_una_divergencia_en_CUALQUIER_campo(gpio, campo: str) -> None:  # noqa: ANN001
    """NO-VACUIDAD del oráculo, campo a campo y DERIVADA del contrato.

    Para cada campo comparable se fabrica una costura que miente **solo en ese
    campo** y se exige que `comparar_instantanea` la cace. Un oráculo que dejara
    de mirar un campo —o que dejara de comparar del todo— se cae aquí, en vez de
    dar por conformes dos implementaciones que ya divergieron.
    """
    verdad = gpio.snapshot()
    mentirosa = _Mentirosa(gpio, campo, _valor_distinto(campo, getattr(verdad, campo)))
    with pytest.raises(AssertionError) as fallo:
        comparar_instantanea(mentirosa.snapshot(), verdad)
    assert campo in str(fallo.value), "el oráculo cazó la mentira pero no dice en qué campo"
    # …y sin mentira, no hay falso positivo.
    comparar_instantanea(gpio.snapshot(), gpio.snapshot())


def _valor_distinto(campo: str, valor: Any) -> Any:
    """Un valor distinto para ese campo, elegido por su tipo DECLARADO."""
    from typing import get_type_hints

    from takab_edge.contracts import FailSafeMode, RelayState, SirenReason

    anotacion = str(get_type_hints(GpioSnapshot)[campo])
    if "bool" in anotacion:
        return not valor
    if "SirenReason" in anotacion:
        return SirenReason.TEST if valor is not SirenReason.TEST else SirenReason.ALERT
    if "RelayState" in anotacion:
        return (
            RelayState(
                channel=ActuatorChannel.SIREN,
                energized=True,
                activated=True,
                fail_safe=FailSafeMode.NORMALLY_OPEN,
            ),
        )
    if "float" in anotacion or "int" in anotacion:
        return float(valor or 0.0) + 7.5
    raise AssertionError(f"el oráculo no sabe fabricar una mentira para {campo}: {anotacion}")
