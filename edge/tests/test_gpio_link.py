"""[T-2.70.a · D2/P1] La COSTURA entre el dueño de los pines y sus consumidores.

Todavía en UN SOLO PROCESO: no hay socket, no hay segundo proceso, no se mueve un
pin. Lo que cambia es que los cinco consumidores y los dos observadores dejan de
hablarle al `GpioController` y le hablan a una interfaz —`GpioLink`— cuya única
implementación de hoy (`LocalGpioLink`) es una llamada directa.

Dos mitades, y la segunda es la que importa:

1. **La costura** — `snapshot()` bajo UNA sola toma de `_lock`, `apply()` en LOTE
   (la secuencia de tier entera como una petición), `action()` sobre una lista
   BLANCA de acciones y `subscribe()` para los dos observadores.

2. **Los sitios que hoy fallarían MAL.** Cada uno se endurece AHORA, mientras la
   implementación local no puede fallar, que es cuando se puede hacer sin prisa.
   Todos se miden rompiendo el CONTROLADOR de abajo: así el test es significativo
   antes del refactor (donde el consumidor lee el controlador directo) y después
   (donde lo lee a través de la costura).
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

import pytest
from takab_edge.actuators import ActuatorManager, RelayActuator
from takab_edge.audio import AudioNotifier, SimulatedAudioBackend
from takab_edge.contracts import (
    ActuatorAction,
    ActuatorChannel,
    ActuatorCommand,
    AlertSource,
    SirenReason,
    Tier,
    TierDecision,
    WaveformPacket,
)
from takab_edge.drill import DrillController
from takab_edge.gpio import GpioController
from takab_edge.gpio_link import (
    GPIO_ACTIONS,
    ChannelOutcome,
    GpioActionNotAllowed,
    GpioLink,
    GpioLinkUnavailable,
    GpioSnapshot,
    LocalGpioLink,
    as_link,
)
from takab_edge.health import HealthMonitor

_RELES = (
    ActuatorChannel.SIREN,
    ActuatorChannel.STROBE,
    ActuatorChannel.GAS_VALVE,
    ActuatorChannel.ELEVATOR,
    ActuatorChannel.DOOR_RETAINER,
)


class _LockContado:
    """Envoltorio de un `RLock` que CUENTA cada toma.

    Es el instrumento de las dos afirmaciones centrales de este paso: «una sola
    toma» para `snapshot()` y «una sola toma» para el lote. Cuenta `__enter__`,
    que es lo que hace un `with self._lock:` — incluida la re-entrada, porque un
    `RLock` re-entrante que se tomara cinco veces seguiría siendo cinco ventanas
    de intercalado desde fuera del proceso.
    """

    def __init__(self, real) -> None:  # noqa: ANN001
        self._real = real
        self.tomas = 0

    def __enter__(self):  # noqa: ANN204
        self.tomas += 1
        return self._real.__enter__()

    def __exit__(self, *args) -> bool | None:  # noqa: ANN002
        return self._real.__exit__(*args)

    def acquire(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        self.tomas += 1
        return self._real.acquire(*args, **kwargs)

    def release(self):  # noqa: ANN201
        return self._real.release()


@pytest.fixture
def gpio(settings):  # noqa: ANN001, ANN201
    controller = GpioController(settings)
    controller.start()
    yield controller
    controller.stop()


@pytest.fixture
def link(gpio) -> LocalGpioLink:  # noqa: ANN001
    return LocalGpioLink(gpio)


def _cmd(channel: ActuatorChannel, action=ActuatorAction.ACTIVATE) -> ActuatorCommand:  # noqa: ANN001
    return ActuatorCommand(channel=channel, action=action, event_id="EV-COSTURA")


def _evacuate() -> TierDecision:
    return TierDecision(tier=Tier.EVACUATE_OR_HOLD, source=AlertSource.SASMEX)


def _packet() -> WaveformPacket:
    return WaveformPacket(
        station="R4F74",
        channel="EHZ",
        starttime=datetime.now(UTC),
        sample_rate=100.0,
        samples=[0] * 100,
    )


class _Averiado:
    """Delegador que hace EXPLOTAR los atributos nombrados y pasa el resto.

    Rompe el CONTROLADOR, no la costura: así el mismo test mide el defecto tanto
    en el código de hoy (el consumidor lee el controlador) como en el de mañana
    (lo lee a través de la costura, que le pasa la excepción tal cual).
    """

    def __init__(self, real, rotos: tuple[str, ...], exc: BaseException | None = None) -> None:  # noqa: ANN001
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_rotos", frozenset(rotos))
        object.__setattr__(self, "_exc", exc or OSError("el dueño de los pines no contesta"))
        object.__setattr__(self, "lecturas_rotas", 0)

    def __getattr__(self, name: str):  # noqa: ANN204
        if name in object.__getattribute__(self, "_rotos"):
            object.__setattr__(
                self, "lecturas_rotas", object.__getattribute__(self, "lecturas_rotas") + 1
            )
            raise object.__getattribute__(self, "_exc")
        return getattr(object.__getattribute__(self, "_real"), name)


def _romper(controlador, *atributos: str, exc: BaseException | None = None):  # noqa: ANN001, ANN202
    return _Averiado(controlador, atributos, exc)


# ---------------------------------------------------------------------------
# 1 · La interfaz y su implementación local
# ---------------------------------------------------------------------------


def test_la_costura_declara_exactamente_cuatro_operaciones(link: LocalGpioLink) -> None:
    """`snapshot` · `apply` · `action` · `subscribe`. Ni una más."""
    assert isinstance(link, GpioLink)
    publicas = {n for n in dir(link) if not n.startswith("_")}
    assert publicas == {"snapshot", "apply", "action", "subscribe"}


def test_snapshot_devuelve_el_estado_completo_que_los_consumidores_leen(
    gpio: GpioController, link: LocalGpioLink
) -> None:
    """Conducta IDÉNTICA a las lecturas propiedad-a-propiedad de hoy."""
    gpio.simulate_sasmex(active=True)
    snap = link.snapshot()
    assert isinstance(snap, GpioSnapshot)
    assert snap.running is gpio.running
    assert snap.sasmex_active is gpio.sasmex_active is True
    assert snap.siren_sounding is gpio.siren_sounding is True
    assert snap.siren_reason is gpio.siren_reason is SirenReason.ALERT
    assert snap.audible_silenced is gpio.audible_silenced
    assert snap.alert_latched is gpio.alert_latched is True
    assert snap.actuation_test_active is gpio.actuation_test_active
    assert snap.test_mode_active is gpio.test_mode_active
    assert snap.last_reflex_latency_s == gpio.last_reflex_latency_s
    assert [r.channel for r in snap.relays] == [r.channel for r in gpio.relay_states()]


def test_snapshot_es_UNA_sola_toma_del_lock(gpio: GpioController, link: LocalGpioLink) -> None:
    """Requisito 3: la instantánea es ATÓMICA.

    Hoy cada consumidor lee propiedad a propiedad y cada lectura toma el lock por
    separado: siete ventanas en las que una demanda puede cambiar a media lectura.
    Con un socket detrás, cada una de esas ventanas es una incoherencia inventada.

    NO-VACUIDAD: el mismo contador, sobre la forma VIEJA de leer, cuenta ≥6. Si el
    instrumento no contara nada, este segundo `assert` no podría distinguirlas.
    """
    contador = _LockContado(gpio._lock)
    gpio._lock = contador

    contador.tomas = 0
    link.snapshot()
    tomas_costura = contador.tomas

    contador.tomas = 0
    for _ in (
        gpio.sasmex_active,  # sin lock (lectura de un bool suelto)
        gpio.siren_sounding,
        gpio.siren_reason,
        gpio.audible_silenced,  # sin lock
        gpio.alert_latched,
        gpio.relay_states(),
    ):
        pass
    tomas_viejas = contador.tomas

    assert tomas_costura == 1, f"la instantánea tomó el lock {tomas_costura} veces"
    # Cuatro de las seis lecturas de arriba toman el lock; las otras dos leen un
    # bool suelto SIN tomarlo, que con un socket detrás es igual de intercalable.
    assert tomas_viejas >= 4, (
        "el contador no está midiendo nada: la forma vieja de leer tiene que "
        f"costar varias tomas y midió {tomas_viejas}"
    )


def test_snapshot_no_puede_intercalarse_con_un_cambio_de_demanda(gpio: GpioController) -> None:
    """La atomicidad, medida contra un hilo que cambia DOS cosas a la vez.

    Un cambio de demanda mueve el enclave Y el estado eléctrico de la sirena. Sin
    una sola toma, una instantánea puede salir con el enclave nuevo y la sirena
    vieja — una incoherencia que el panel pintaría como avería del gabinete.
    """
    link = LocalGpioLink(gpio)
    dentro = threading.Event()
    suelta = threading.Event()
    resultado: list[GpioSnapshot] = []

    def mutador() -> None:
        with gpio._lock:
            dentro.set()
            suelta.wait(5.0)
            gpio.simulate_sasmex(active=True)  # enclave + sirena, bajo el MISMO lock

    hilo = threading.Thread(target=mutador, daemon=True)
    hilo.start()
    assert dentro.wait(5.0)

    lector = threading.Thread(target=lambda: resultado.append(link.snapshot()), daemon=True)
    lector.start()
    time.sleep(0.05)
    assert not resultado, "la instantánea NO está tomando el lock: leyó a media mutación"
    suelta.set()
    hilo.join(5.0)
    lector.join(5.0)

    snap = resultado[0]
    assert snap.sasmex_active is True and snap.siren_sounding is True, (
        "instantánea incoherente: el enclave y el estado eléctrico salieron de "
        "dos momentos distintos"
    )


def test_apply_aplica_la_secuencia_entera_en_UNA_sola_toma(
    gpio: GpioController, link: LocalGpioLink
) -> None:
    """Requisito 4: cinco cruces se vuelven uno.

    NO-VACUIDAD: la ruta vieja (un `set_relay` por canal) cuesta ≥5 tomas con el
    mismo contador.
    """
    contador = _LockContado(gpio._lock)
    gpio._lock = contador

    contador.tomas = 0
    resultados = link.apply([(c, True) for c in _RELES])
    tomas_lote = contador.tomas

    contador.tomas = 0
    for canal in _RELES:
        gpio.set_relay(canal, False)
    tomas_sueltas = contador.tomas

    assert tomas_lote == 1, f"el lote tomó el lock {tomas_lote} veces"
    assert tomas_sueltas >= 5, (
        f"el contador no mide: cinco set_relay sueltos midieron {tomas_sueltas} tomas"
    )
    assert [r.channel for r in resultados] == list(_RELES)
    assert all(isinstance(r, ChannelOutcome) and r.ok for r in resultados)


def test_un_canal_malo_del_lote_no_aborta_a_los_demas(link: LocalGpioLink) -> None:
    """Aislamiento por canal, igual que hoy: `ActuatorManager` ACKea uno a uno.

    Sin esto, un canal desconocido en la secuencia dejaría el gas, el ascensor y
    las puertas SIN comandar — un lote que falla entero es peor que cinco
    llamadas sueltas.
    """
    demandas = [
        (ActuatorChannel.SIREN, True),
        (ActuatorChannel.SYSTEM, True),  # canal LÓGICO: no gobierna ningún relé
        (ActuatorChannel.GAS_VALVE, True),
    ]
    resultados = link.apply(demandas)
    assert [r.ok for r in resultados] == [True, False, True]
    assert "system" in resultados[1].detail or "system" in str(resultados[1].detail)
    snap = link.snapshot()
    activos = {r.channel for r in snap.relays if r.activated}
    assert ActuatorChannel.SIREN in activos and ActuatorChannel.GAS_VALVE in activos


def test_la_costura_NO_expone_drive_all_safe(link: LocalGpioLink) -> None:
    """`drive_all_safe()` es estado seguro DURABLE (`_safed`, solo `reset()` lo
    levanta): exponerlo dejaría el gas cerrado y las puertas sueltas en cada
    reinicio de `takab-edge`.

    NO-VACUIDAD: las siete acciones que SÍ están se resuelven; ésta no existe ni
    por la lista blanca ni por atributo.
    """
    assert "drive_all_safe" not in GPIO_ACTIONS
    with pytest.raises(GpioActionNotAllowed):
        link.action("drive_all_safe")
    assert not hasattr(link, "drive_all_safe")
    link.action("reset")  # …y lo declarado sí pasa: no es un freno de mano


class _CosturaMuerta:
    """Costura de pleno derecho cuyas CUATRO operaciones no contestan."""

    def snapshot(self):  # noqa: ANN202
        raise GpioLinkUnavailable("muerta")

    def apply(self, demands):  # noqa: ANN001, ANN202
        raise GpioLinkUnavailable("muerta")

    def action(self, name, **params):  # noqa: ANN001, ANN003, ANN202
        raise GpioLinkUnavailable("muerta")

    def subscribe(self, event, callback) -> None:  # noqa: ANN001
        raise GpioLinkUnavailable("muerta")


def test_el_reflejo_sasmex_no_cruza_la_costura(supervisor) -> None:  # noqa: ANN001
    """Gate #6: el reflejo vive ENTERO dentro de `gpio._dispatch_sasmex`.

    Con la costura del supervisor CABLEADA a los cinco consumidores y MUERTA —las
    cuatro operaciones lanzan—, el flanco del contacto seco del WR-1 sigue
    energizando sirena y estrobo dentro del presupuesto. Si el reflejo pasara por
    la costura, o si `_dispatch_sasmex` leyera cualquier cosa a través de ella,
    este test no podría pasar.

    Se dispara sobre el PIN del WR-1 y se lee el estado ELÉCTRICO de los cinco
    relés, no `siren_sounding`: el veredicto del gate #6 es el nivel del relé.

    NO-VACUIDAD, y es la mitad que faltaba: los tres canales que SÍ cruzan la
    costura —gas, ascensor y retenedores— se quedan en su nivel de REPOSO, porque
    `RelayActuator` los pide por `apply()` y `apply()` no contesta. O sea, la
    costura está de verdad rota y de verdad es portante; lo que sobrevive lo hace
    por vivir del otro lado, no porque el test no haya roto nada.

    COMPLEMENTA, no duplica, a `test_e2e.py::test_latencia_contacto_wr1_a_los_
    cinco_reles_bajo_presupuesto` (D1.4): aquél cronometra la cadena ENTERA con la
    costura SANA y exige los cinco canales; éste exige que los dos del reflejo no
    dependan de ella.
    """
    from time import perf_counter

    from gpiozero import Device
    from takab_edge.gpio import active_energized, normal_energized

    muerta = _CosturaMuerta()
    assert isinstance(muerta, GpioLink)
    supervisor.gpio_link = muerta
    for nombre, consumidor in (
        ("actuators.relay", supervisor.actuators._relay),
        ("audio", supervisor.audio),
        ("drill", supervisor.drill),
        ("health", supervisor.health),
        ("local_api", supervisor.local_api),
    ):
        assert hasattr(consumidor, "_link"), nombre
        consumidor._link = muerta

    s = supervisor.settings
    pines = {
        ActuatorChannel.SIREN: Device.pin_factory.pin(s.pins.relay_siren),
        ActuatorChannel.STROBE: Device.pin_factory.pin(s.pins.relay_strobe),
        ActuatorChannel.GAS_VALVE: Device.pin_factory.pin(s.pins.relay_gas_valve),
        ActuatorChannel.ELEVATOR: Device.pin_factory.pin(s.pins.relay_elevator),
        ActuatorChannel.DOOR_RETAINER: Device.pin_factory.pin(s.pins.relay_door_retainer),
    }
    for canal, pin in pines.items():
        assert pin.state is normal_energized(s.failsafe[canal]), (
            f"premisa rota: {canal.value} no arrancó en su nivel de reposo"
        )

    # Lo que hace la independencia ESTRUCTURAL, y no sólo circunstancial: el
    # reflejo ocurre ANTES de invocar a los observadores. Lo que corre después
    # —supervisor, rules, actuators, y mañana el IPC— ya no puede impedirlo.
    al_llamar: list[bool] = []
    supervisor.gpio.on_sasmex(
        lambda _sig: al_llamar.append(
            all(
                pines[c].state is active_energized(s.failsafe[c])
                for c in (ActuatorChannel.SIREN, ActuatorChannel.STROBE)
            )
        )
    )

    contacto = Device.pin_factory.pin(s.pins.wr1_contact)
    inicio = perf_counter()
    contacto.drive_low()  # WR-1: contacto seco CERRADO = alerta SASMEX
    transcurrido = perf_counter() - inicio

    assert al_llamar and all(al_llamar), (
        "sirena y estrobo NO estaban energizados cuando se invocó al primer "
        "observador: el reflejo dejó de ir por delante de los callbacks y pasó a "
        "depender de lo que corre después de él"
    )
    for canal in (ActuatorChannel.SIREN, ActuatorChannel.STROBE):
        assert pines[canal].state is active_energized(s.failsafe[canal]), (
            f"{canal.value} NO quedó en su nivel de protección con la costura muerta: "
            "el reflejo del gate #6 depende de algo que cruza el futuro IPC"
        )
    assert transcurrido < 0.100, (
        f"el reflejo tardó {transcurrido * 1000:.1f} ms con la costura muerta "
        "(presupuesto §4.3: <100 ms)"
    )
    assert supervisor.gpio.last_reflex_latency_s is not None
    assert supervisor.gpio.last_reflex_latency_s < 0.100

    for canal in (
        ActuatorChannel.GAS_VALVE,
        ActuatorChannel.ELEVATOR,
        ActuatorChannel.DOOR_RETAINER,
    ):
        assert pines[canal].state is normal_energized(s.failsafe[canal]), (
            f"{canal.value} actuó con la costura MUERTA: el test no rompió nada y "
            "no está midiendo lo que dice"
        )


def test_as_link_envuelve_al_controlador_y_respeta_una_costura_ya_hecha(
    gpio: GpioController, link: LocalGpioLink
) -> None:
    """La coerción que mantiene vivos los 177 tests acoplados a `gpio`."""
    assert as_link(link) is link
    envuelto = as_link(gpio)
    assert isinstance(envuelto, LocalGpioLink) and isinstance(envuelto, GpioLink)
    assert envuelto.snapshot().running is True
    assert as_link(None) is None


def test_el_supervisor_cablea_la_COSTURA_a_los_cinco_y_a_los_dos_observadores(
    supervisor,  # noqa: ANN001
) -> None:
    """NO-VACUIDAD de la migración: la coerción de `as_link` no puede estar
    tapando un consumidor sin migrar.

    Si alguno siguiera recibiendo el controlador crudo, aquí se ve: se compara
    IDENTIDAD contra la costura del supervisor, no `isinstance`.
    """
    costura = supervisor.gpio_link
    assert isinstance(costura, LocalGpioLink)
    consumidores = {
        "actuators.relay": supervisor.actuators._relay._link,
        "audio": supervisor.audio._link,
        "drill": supervisor.drill._link,
        "health": supervisor.health._link,
        "local_api": supervisor.local_api._link,
    }
    for nombre, recibido in consumidores.items():
        assert recibido is costura, f"{nombre} no recibió la costura del supervisor"
        assert recibido is not supervisor.gpio, f"{nombre} sigue con el controlador crudo"
    # …y los DOS observadores `on_sasmex` siguen cableados (supervisor + drill).
    #
    # [T-2.70.a·D2/P2] Se comprueban por IDENTIDAD y no por CUENTA, y el cambio
    # no relaja nada: desde D2/P2 el dueño de los pines tiene un tercer
    # observador legítimo —el `PinLinkServer` que sirve su propia puerta— y un
    # `== 2` se habría "arreglado" subiendo el número, que es como se pierde una
    # guarda. Aquí se exige que los dos del supervisor estén Y que cualquier otro
    # sea del transporte: un consumidor que se colara enganchándose al
    # controlador crudo sigue cayendo.
    callbacks = supervisor.gpio._sasmex_callbacks
    assert supervisor._on_sasmex in callbacks, "el observador del supervisor se perdió"
    assert supervisor.drill.on_sasmex in callbacks, "el observador del simulacro se perdió"
    ajenos = [
        cb
        for cb in callbacks
        if cb not in (supervisor._on_sasmex, supervisor.drill.on_sasmex)
        and type(getattr(cb, "__self__", None)).__name__ != "PinLinkServer"
    ]
    assert ajenos == [], f"observadores enganchados al controlador CRUDO: {ajenos}"


# ---------------------------------------------------------------------------
# 2 · Los sitios que hoy fallarían MAL
# ---------------------------------------------------------------------------


def test_el_modo_prueba_ilegible_no_reporta_el_shake_caido(supervisor) -> None:  # noqa: ANN001
    """EL PEOR. `_act_and_publish` lee el modo prueba EN EL HILO DE SEEDLINK.

    La cadena es `_transport.run` → `ingest` → `feed` (sin try) → `_on_packet` →
    `_act_and_publish`, y `_run_transport` atrapa `except Exception` rotulándolo
    «SeedLink desconectado» con reconexión y backoff. Una lectura que lance haría
    que el gabinete reportara el Shake caído y encendiera la alarma de sensor
    mudo —la del 14-jul— con el sensor perfectamente vivo.

    Y falla ABIERTO **a sabiendas de lo que cuesta**: el evento abre incidente y
    dispara la push CRISIS —«ALERTA SÍSMICA», sonido crítico, toma de pantalla— a
    los teléfonos del sitio, y `LocalEvent` no tiene dónde llevar un `is_test` que
    la nube pudiera filtrar (T-2.05: la garantía es server-side). Se elige igual,
    porque la otra rama CALLA un sismo real y porque con el IPC una lectura que no
    contesta significa que gas, ascensor y puertas tampoco actuaron: ahí la nube es
    lo último que queda. Ver `supervisor._modo_prueba_activo`.
    """
    publicados: list[tuple[str, object]] = []
    supervisor.cloud.publish = lambda topic, payload: publicados.append((topic, payload))
    controlador = supervisor.gpio
    roto = _romper(controlador, "test_mode_active", "test_mode_remaining_s", "snapshot")
    # Se rompe por los DOS caminos —el atributo directo de hoy y la instantánea de
    # la costura— para que el test mida el defecto antes y después del refactor.
    supervisor.gpio = roto
    supervisor.gpio_link = LocalGpioLink(roto)

    antes = supervisor.seedlink.reconnects
    controlador.simulate_sasmex(active=True)  # decisión evacuate por la vía SASMEX
    supervisor.seedlink.feed(_packet())  # la cadena EXACTA del hilo de SeedLink

    assert supervisor.seedlink.reconnects == antes, (
        "una lectura rota del modo prueba se disfrazó de desconexión de SeedLink"
    )
    assert roto.lecturas_rotas > 0, "el test no rompió nada: no midió el defecto"
    assert any(topic == "takab/events" for topic, _ in publicados), (
        "falló CERRADO: la nube se quedó sin el evento por no poder leer el modo prueba"
    )


def test_el_panel_degrada_a_S_D_en_vez_de_dar_500_al_kiosco(supervisor) -> None:  # noqa: ANN001
    """Las cuatro lecturas sin envolver de `status()` (sasmex_active,
    siren_sounding, audible_silenced, alert_latched).

    El único cinturón era el `except` de `do_GET`, que responde 500 — no una
    sección en S/D, sino la pantalla en blanco del kiosco.
    """
    roto = _romper(
        supervisor.gpio,
        "sasmex_active",
        "siren_sounding",
        "audible_silenced",
        "alert_latched",
        "siren_reason",
        "relay_states",
        "running",
        "snapshot",
        exc=GpioLinkUnavailable("el dueño de los pines no contesta"),
    )
    supervisor.local_api._link = LocalGpioLink(roto)

    _host, port = supervisor.local_api.address
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5) as resp:
        assert resp.status == 200, "el kiosco recibió un 500 en vez de una sección S/D"
        estado = json.loads(resp.read())

    for campo in ("sasmex_active", "siren_sounding", "audible_silenced", "alert_latched"):
        assert estado[campo] is None, f"{campo} inventó un valor que nadie pudo medir"
    assert estado["relays_status"]["reason"] == "gpio_unreachable"
    # …y el RESTO del panel sobrevive: degradar una sección no apaga la pantalla.
    assert estado["gateway_id"] == supervisor.settings.gateway_id
    assert estado["thresholds"] is not None
    assert estado["seedlink"] is not None


@pytest.mark.parametrize(
    "ruta",
    ["/api/silence", "/api/siren-test", "/api/actuator-test", "/api/test-mode", "/api/reset"],
)
def test_las_acciones_del_panel_tienen_camino_honesto_de_fallo(supervisor, ruta: str) -> None:  # noqa: ANN001
    """`silence()` daba 500 —o la conexión cortada— al operador que aprieta
    SILENCIO: `do_POST` solo traducía `ActionUnavailable`→409 y cualquier otra
    excepción escapaba a `BaseHTTPRequestHandler`.

    503 y no 500: «el dueño de los pines no contesta» es indisponibilidad del
    servicio de abajo, no una avería del panel.
    """
    roto = _romper(
        supervisor.gpio,
        "silence_audibles",
        "run_siren_test",
        "run_local_actuation_test",
        "arm_test_mode",
        "disarm_test_mode",
        "test_mode_active",
        "reset",
        "snapshot",
        exc=GpioLinkUnavailable("el dueño de los pines no contesta"),
    )
    supervisor.local_api._link = LocalGpioLink(roto)

    _host, port = supervisor.local_api.address
    peticion = urllib.request.Request(f"http://127.0.0.1:{port}{ruta}", method="POST")
    try:
        with urllib.request.urlopen(peticion, timeout=5) as resp:
            codigo = resp.status
    except urllib.error.HTTPError as exc:
        codigo = exc.code
    assert codigo == 503, f"{ruta} respondió {codigo}; el operador merece un 503 honesto"


def test_un_voceo_roto_no_puede_abortar_el_resto_de_la_actuacion(supervisor) -> None:  # noqa: ANN001
    """`supervisor:410` llamaba a `audio.on_tier` SIN try, y dentro `_play`
    consultaba `gpio.audible_silenced` FUERA de su propio try.

    Lo que venía después y se perdía: espejo LoRa a los secundarios, aborto del
    simulacro, ACKs a la nube, `LocalEvent` y encolado de evidencia. Un canal
    declarado ADVISORY tumbando la publicación del evento.
    """
    publicados: list[str] = []
    supervisor.cloud.publish = lambda topic, payload: publicados.append(topic)
    encolados: list[str] = []
    supervisor.backfill.queue_evidence = lambda ev, a, b: encolados.append(ev)
    supervisor.drill.start_drill("SIM-1", 300.0)
    assert supervisor.drill.active is True

    def _explota(_decision) -> None:  # noqa: ANN001
        raise RuntimeError("el voceo explotó")

    supervisor.audio.on_tier = _explota

    supervisor._act_and_publish(_evacuate(), None)

    assert "takab/events" in publicados, "el evento se perdió por un canal advisory"
    assert encolados, "la evidencia no se encoló por un canal advisory"
    assert supervisor.drill.active is False, "el simulacro no se abortó"


def test_el_voceo_no_revienta_por_no_poder_leer_el_silencio(settings, tmp_path) -> None:  # noqa: ANN001
    """`audio._play` leía `self._gpio.audible_silenced` FUERA de su try.

    Fail-CERRADO en el advisory: sin poder saber si el operador silenció, no se
    vocea. La sirena de RELÉ —la primaria— no depende de esto y sigue sonando.
    """
    sismo = tmp_path / "sismo.wav"
    sismo.write_bytes(b"RIFF-sismo")
    cfg = settings.model_copy(
        update={"audio_enabled": True, "audio_sismo_path": str(sismo)},
    )
    controlador = GpioController(cfg)
    controlador.start()
    try:
        backend = SimulatedAudioBackend()
        roto = _romper(controlador, "audible_silenced", "snapshot")
        notifier = AudioNotifier(cfg, gpio=roto, backend=backend)
        notifier.on_tier(_evacuate())  # NO debe lanzar
        assert backend.plays == [], "voceó sin poder comprobar el silencio del operador"
        assert roto.lecturas_rotas > 0
    finally:
        controlador.stop()


def test_la_sirena_por_jack_no_se_queda_sonando_para_siempre(settings, tmp_path) -> None:  # noqa: ANN001
    """`audio._reconcile_siren` atrapaba todo y, al fallar, NO paraba el WAV.

    Con `siren_reason` al otro lado de un enlace caído, el altavoz seguiría
    sonando después de cerrarse la alerta y nadie en el edificio podría
    distinguirlo de una alerta viva.

    Las dos mitades: un fallo TRANSITORIO no corta el sonido (cortar y reanudar
    a 20 Hz sería un tartamudeo en el altavoz de un inmueble), pero uno SOSTENIDO
    sí — porque a partir de ahí el sonido ya no representa nada medido.
    """
    wav = tmp_path / "siren.wav"
    wav.write_bytes(b"RIFF-siren")
    cfg = settings.model_copy(
        update={"audio_siren_enabled": True, "audio_siren_path": str(wav)},
    )
    controlador = GpioController(cfg)
    controlador.start()
    try:
        sirena = SimulatedAudioBackend()
        notifier = AudioNotifier(cfg, gpio=controlador, siren_backend=sirena)
        controlador.simulate_sasmex(active=True)
        notifier._reconcile_siren()
        assert sirena.playing == str(wav)

        roto = _romper(controlador, "siren_reason", "snapshot")
        notifier._link = as_link(roto)
        notifier._reconcile_siren()
        assert sirena.playing == str(wav), "un parpadeo transitorio tartamudeó el altavoz"
        for _ in range(60):
            notifier._reconcile_siren()
        assert sirena.playing is None, (
            "el altavoz siguió sonando con el dueño de los pines mudo: nadie en el "
            "edificio puede distinguirlo de una alerta viva"
        )
    finally:
        controlador.stop()


class _CorteQueFalla(SimulatedAudioBackend):
    """Altavoz cuyo ``stop()`` REVIENTA las primeras veces, y sigue sonando.

    No es hipotético: `AplayBackend._terminate_locked` pone `self._proc = None`
    **después** de `terminate()`/`wait()`/`kill()`, así que si cualquiera de los
    tres lanza (`ProcessLookupError`, `PermissionError`, un `TimeoutExpired` que
    el `kill()` tampoco resuelve), el proceso de `aplay` queda registrado, el WAV
    sigue saliendo por el altavoz y `playing` sigue devolviendo la ruta.
    """

    def __init__(self, fallos: int) -> None:
        super().__init__()
        self._por_fallar = fallos
        self.intentos_de_corte = 0

    def stop(self) -> None:
        self.intentos_de_corte += 1
        if self._por_fallar > 0:
            self._por_fallar -= 1
            raise OSError("aplay no murió: el WAV sigue saliendo por el altavoz")
        super().stop()


def test_la_sirena_REINTENTA_callar_cuando_el_primer_corte_falla(settings, tmp_path) -> None:  # noqa: ANN001
    """El corte se intentaba UNA sola vez — y por eso podía no ocurrir NUNCA.

    La condición era una IGUALDAD (`self._siren_fallos == N`), y el `stop()` va
    envuelto en su propio `try/except` que traga. Un corte que falla en ese único
    instante deja `_siren_fallos` subiendo para siempre y la condición no vuelve a
    cumplirse jamás: 500 conciliaciones mudas después, **un intento de corte y el
    altavoz sonando**. Exactamente el fallo que el umbral se introdujo para cerrar.

    Ahora el umbral es un SUELO (`>=`) y el guard es `playing`, no un contador:
    mientras el altavoz siga sonando y el estado siga ilegible, se reintenta.

    NO-VACUIDAD, las dos direcciones:

    * si el reintento no ocurriera, `intentos_de_corte` se quedaría en 1 y
      `playing` seguiría siendo el WAV — que es lo que medía el `==`;
    * si el corte se disparara a ciegas en cada conciliación, `intentos_de_corte`
      llegaría a ~480 (un `stop()` cada 50 ms sobre un altavoz ya callado, y con
      `AplayBackend` un `terminate()` por vuelta). Son exactamente 2.
    """
    wav = tmp_path / "siren.wav"
    wav.write_bytes(b"RIFF-siren")
    cfg = settings.model_copy(
        update={"audio_siren_enabled": True, "audio_siren_path": str(wav)},
    )
    controlador = GpioController(cfg)
    controlador.start()
    try:
        sirena = _CorteQueFalla(fallos=1)  # el PRIMER corte revienta; el segundo funciona
        notifier = AudioNotifier(cfg, gpio=controlador, siren_backend=sirena)
        controlador.simulate_sasmex(active=True)
        notifier._reconcile_siren()
        assert sirena.playing == str(wav)

        notifier._link = as_link(_romper(controlador, "siren_reason", "snapshot"))
        for _ in range(500):
            notifier._reconcile_siren()

        assert sirena.playing is None, (
            "el altavoz se quedó sonando PARA SIEMPRE: el único intento de corte "
            "falló y la condición de igualdad no volvió a cumplirse nunca"
        )
        assert sirena.intentos_de_corte == 2, (
            "se esperaban dos intentos —el que falla y el reintento que funciona— "
            f"y hubo {sirena.intentos_de_corte}"
        )
    finally:
        controlador.stop()


def test_la_salud_sobrevive_a_un_estado_de_reles_ilegible(settings) -> None:  # noqa: ANN001
    """`health._relay_states` devolvía `[]` sin distinguir «detenido» de «no pude
    preguntar», y una lectura que LANCE mataba el snapshot entero: `_on_start`
    llama a `snapshot("startup")` sin try, así que el latido no arrancaría nunca
    y el gabinete se vería FANTASMA desde la nube.
    """
    controlador = GpioController(settings)
    controlador.start()
    try:
        roto = _romper(controlador, "relay_states", "snapshot", exc=GpioLinkUnavailable("mudo"))
        monitor = HealthMonitor(settings, gpio=roto, heartbeat_s=3600.0)
        monitor.start()  # el latido tiene que ARRANCAR
        try:
            assert monitor.running is True
            snap = monitor.snapshot("test")
            assert snap.relays == []
            assert snap.gateway_id == settings.gateway_id  # el resto del latido, intacto
            assert roto.lecturas_rotas > 0
        finally:
            monitor.stop()
    finally:
        controlador.stop()


def test_relays_status_distingue_no_contesta_de_averia_y_de_detenido(supervisor) -> None:  # noqa: ANN001
    """La enumeración de `_relays_view` tenía seis causas y «el dueño de los
    pines no contesta» no era ninguna: mapearla a `gpio_error` o `gpio_stopped`
    es rotular mal y manda al operador a revisar el journal equivocado.

    NO-VACUIDAD: las otras dos causas siguen distinguiéndose. Si el rótulo nuevo
    se comiera cualquier fallo, `gpio_error` y `gpio_stopped` desaparecerían.
    """
    panel = supervisor.local_api

    mudo = _romper(
        supervisor.gpio, "relay_states", "running", "snapshot", exc=GpioLinkUnavailable("mudo")
    )
    panel._link = LocalGpioLink(mudo)
    _filas, estado = panel._relays_view()
    assert estado["reason"] == "gpio_unreachable"

    averiado = _romper(supervisor.gpio, "relay_states", "snapshot", exc=RuntimeError("avería"))
    panel._link = LocalGpioLink(averiado)
    _filas, estado = panel._relays_view()
    assert estado["reason"] == "gpio_error", "una avería EN MARCHA se disfrazó de mudez"

    supervisor.gpio.stop()
    panel._link = supervisor.gpio_link
    _filas, estado = panel._relays_view()
    assert estado["reason"] == "gpio_stopped", "un módulo detenido se disfrazó de mudez"


def _mandar_drill_firmado(supervisor, command_id: str, event_id: str) -> list:  # noqa: ANN001
    """Publica un `drill_start` FIRMADO y devuelve los ACKs que salieron.

    Habilita `command_enabled` a propósito: es `False` de fábrica, y el
    dispatcher rechaza con ack ANTES de llegar a la rama del simulacro. Sin esto
    el test pasaría por el camino equivocado — verde y sin medir nada (medido:
    los dos tests de abajo pasaban vacíos hasta que se añadió esta línea).
    """
    from takab_edge.dispatch import canonical_payload

    store = supervisor.config
    store.settings = store.settings.model_copy(update={"command_enabled": True})

    acks: list = []
    supervisor.cloud.publish = lambda topic, payload: acks.append((topic, payload))
    payload = {
        "channel": "system",
        "action": "drill_start",
        "event_id": event_id,
        "duration_s": 60,
    }
    ts = datetime.now(UTC)
    nonce = f"nonce-{command_id}"
    sobre = {
        "command_id": command_id,
        "nonce": nonce,
        "ts": ts.isoformat(),
        "sig": supervisor.security.sign(canonical_payload(payload), nonce, ts),
        "payload": payload,
    }
    supervisor.dispatch.on_command("takab/cmd/x", json.dumps(sobre).encode())
    enviados = [p for topic, p in acks if topic == "takab/acks"]
    assert enviados, "la nube se quedó sin ack y esperará el TTL"
    detalle = str(getattr(enviados[-1], "detail", ""))
    assert "command_enabled" not in detalle, (
        "el comando se rechazó ANTES de llegar al simulacro: este test no está "
        f"midiendo lo que dice ({detalle!r})"
    )
    return enviados


def test_el_simulacro_firmado_falla_CERRADO_y_la_nube_recibe_su_ack(settings) -> None:  # noqa: ANN001
    """`drill.start_drill` lee `gpio.sasmex_active`; `dispatch` solo atrapaba
    `(TypeError, ValueError)`, así que un `OSError` escapaba al `except` genérico
    de `on_command`: sin ack, la nube espera el TTL.

    Y el guard falla CERRADO: sin poder comprobar si hay alerta real viva, el
    simulacro se RECHAZA. Abrir arrancaría un simulacro sobre un sismo.
    """
    controlador = GpioController(settings)
    controlador.start()
    try:
        roto = _romper(controlador, "sasmex_active", "snapshot")
        drill = DrillController(settings, gpio=roto)
        ok, motivo = drill.start_drill("SIM-CAIDO", 120.0)
        assert ok is False, "el simulacro arrancó sin poder comprobar si hay alerta real"
        assert "no" in motivo.lower()
        assert drill.active is False
        assert roto.lecturas_rotas > 0
    finally:
        controlador.stop()


def test_el_drill_start_firmado_ackea_aunque_el_guard_no_pueda_leer(supervisor) -> None:  # noqa: ANN001
    """La otra mitad del anterior, en la ruta REAL del comando firmado."""
    roto = _romper(supervisor.gpio, "sasmex_active", "snapshot")
    supervisor.drill._link = as_link(roto)

    enviados = _mandar_drill_firmado(supervisor, "CMD-DRILL-COSTURA", "SIM-FIRMADO")
    assert getattr(enviados[-1], "success", None) is False
    assert "comprobar" in str(getattr(enviados[-1], "detail", ""))
    assert supervisor.drill.active is False
    assert roto.lecturas_rotas > 0


def test_un_drill_start_que_LANZA_tampoco_deja_a_la_nube_sin_ack(supervisor) -> None:  # noqa: ANN001
    """Cinturón del cinturón, en el sitio que el reconocimiento nombró.

    `start_drill` ya falla cerrado por su cuenta, pero el `except` de `dispatch`
    seguía siendo `(TypeError, ValueError)`: cualquier otra excepción del
    controlador de simulacros escapa al `except` genérico de `on_command`, que
    registra y calla — y la nube espera el TTL sin saber por qué. Un comando
    FIRMADO siempre se ACKea, aunque la respuesta sea «no».
    """

    def _explota(_id, _dur):  # noqa: ANN001, ANN202
        raise OSError("el controlador de simulacros reventó")

    supervisor.drill.start_drill = _explota

    enviados = _mandar_drill_firmado(supervisor, "CMD-DRILL-EXPLOTA", "SIM-EXPLOTA")
    assert getattr(enviados[-1], "success", None) is False


# ---------------------------------------------------------------------------
# 3 · Conducta idéntica: el lote no cambia lo que el gabinete hace
# ---------------------------------------------------------------------------


def test_la_secuencia_de_tier_cruza_como_UNA_peticion(gpio: GpioController) -> None:
    """`ActuatorManager.execute_sequence` agrupa los canales de relé en un lote.

    NO-VACUIDAD: se cuentan las llamadas a `apply` de la costura — cinco comandos,
    UNA petición— y se comprueba que los ACKs siguen siendo cinco, uno por canal
    y en el mismo orden.
    """
    llamadas: list[int] = []
    real = LocalGpioLink(gpio)

    class _Contadora:
        def snapshot(self):  # noqa: ANN202
            return real.snapshot()

        def apply(self, demands):  # noqa: ANN001, ANN202
            demandas = list(demands)
            llamadas.append(len(demandas))
            return real.apply(demandas)

        def action(self, name, **params):  # noqa: ANN001, ANN003, ANN202
            return real.action(name, **params)

        def subscribe(self, event, callback) -> None:  # noqa: ANN001
            real.subscribe(event, callback)

    manager = ActuatorManager(RelayActuator(_Contadora()))
    manager.start()
    comandos = [_cmd(c) for c in _RELES]
    acks = manager.execute_sequence(comandos)

    assert llamadas == [5], f"la secuencia cruzó {len(llamadas)} veces en vez de una"
    assert [a.channel for a in acks] == list(_RELES)
    assert all(a.success for a in acks)
    assert all(gpio.is_activated(c) for c in _RELES)


def test_el_lote_no_se_come_los_canales_de_bacnet(gpio: GpioController) -> None:
    """Con BACnet por contrato, esos canales NO entran en el lote de relés y el
    orden de los ACKs sigue siendo el de los comandos."""
    from simulators.bacnet import BacnetSimulator
    from takab_edge.actuators import BacnetActuator

    sim = BacnetSimulator()
    manager = ActuatorManager(
        RelayActuator(gpio),
        BacnetActuator(sim),
        bacnet_channels=[ActuatorChannel.GAS_VALVE, ActuatorChannel.ELEVATOR],
    )
    manager.start()
    comandos = [_cmd(c) for c in _RELES]
    acks = manager.execute_sequence(comandos)
    assert [a.channel for a in acks] == list(_RELES)
    detalles = {a.channel: a.detail for a in acks}
    assert detalles[ActuatorChannel.GAS_VALVE] == "bacnet"
    assert detalles[ActuatorChannel.ELEVATOR] == "bacnet"
    assert detalles[ActuatorChannel.SIREN] == "relay"


def test_un_lote_entero_caido_ackea_fallo_por_canal(gpio: GpioController) -> None:
    """Si la costura entera no contesta, cada canal recibe su ACK fallido — nunca
    un `execute_sequence` que lanza al hilo de detección."""

    class _Muerta:
        def snapshot(self):  # noqa: ANN202
            raise GpioLinkUnavailable("muerta")

        def apply(self, demands):  # noqa: ANN001, ANN202
            raise GpioLinkUnavailable("muerta")

        def action(self, name, **params):  # noqa: ANN001, ANN003, ANN202
            raise GpioLinkUnavailable("muerta")

        def subscribe(self, event, callback) -> None:  # noqa: ANN001
            pass

    manager = ActuatorManager(RelayActuator(_Muerta()))
    manager.start()
    acks = manager.execute_sequence([_cmd(c) for c in _RELES])
    assert [a.channel for a in acks] == list(_RELES)
    assert not any(a.success for a in acks)


@pytest.mark.parametrize("devueltos", [0, 1, 4, 6])
def test_una_costura_que_devuelve_OTRA_cantidad_de_resultados_ackea_fallo(
    gpio: GpioController, devueltos: int
) -> None:
    """El guard de `RelayActuator.execute_batch`: hoy inalcanzable, MAÑANA el
    contrato del socket.

    Con `LocalGpioLink` es imposible que la cuenta no cuadre (`apply` envuelve el
    resultado del propio controlador). Con un socket detrás, «me devolvieron menos
    resultados de los que pedí» es un mensaje truncado, una respuesta de otra
    petición o una versión de protocolo distinta — y es la forma NORMAL de fallar.

    Lo que el guard impide es emparejar A CIEGAS. La medida se toma sobre
    `RelayActuator.execute_batch` DIRECTAMENTE, sin el `except Exception` de
    `ActuatorManager.execute_sequence`, y es a propósito: sin el guard, el
    `zip(..., strict=True)` de abajo lanza un `ValueError` que hoy tapa el `except`
    del manager — pero el manager es su llamador de hoy, no su contrato. Un driver
    del camino de vida que solo devuelve ACKs porque alguien más lo envuelve es un
    driver que lanza en cuanto lo llame otro (el `self_test` firmado ya usa la
    misma clase por otra puerta). Y si el `strict=True` se relajara alguna vez, el
    fallo sería peor que una excepción: el ACK de la SIRENA colgado del GAS.

    NO-VACUIDAD, dos direcciones: quitando el guard, la llamada directa LANZA (el
    driver deja de cumplir «un ACK por comando, jamás una excepción») y el detalle
    que ve el operador pasa a ser un mensaje de `zip()` en vez de nombrar la
    costura, que es a lo que hay que ir a mirar.
    """
    real = LocalGpioLink(gpio)

    class _Descuadrada:
        def snapshot(self):  # noqa: ANN202
            return real.snapshot()

        def apply(self, demands):  # noqa: ANN001, ANN202
            del demands
            return tuple(
                ChannelOutcome(channel=ActuatorChannel.SIREN, ok=True, detail="relay")
                for _ in range(devueltos)
            )

        def action(self, name, **params):  # noqa: ANN001, ANN003, ANN202
            return real.action(name, **params)

        def subscribe(self, event, callback) -> None:  # noqa: ANN001
            real.subscribe(event, callback)

    driver = RelayActuator(_Descuadrada())
    comandos = [_cmd(c) for c in _RELES]
    acks = driver.execute_batch(comandos)  # SIN el paraguas del manager

    assert [a.channel for a in acks] == list(_RELES), (
        "los ACKs no salieron uno por canal y en orden: alguien emparejó a ciegas"
    )
    assert not any(a.success for a in acks), (
        "se ACKeó ÉXITO con una respuesta que no se pudo emparejar con su canal"
    )
    assert all("costura incoherente" == a.detail for a in acks), (
        "el detalle no nombra la costura: manda al operador a leer un mensaje de "
        f"`zip()` en vez de al proceso que no cumplió el contrato ({acks[0].detail!r})"
    )
    # …y ningún relé se movió por una respuesta que no se pudo atribuir.
    assert not any(gpio.is_activated(c) for c in _RELES)
    # La ruta REAL (por el manager) sigue dando lo mismo, ACK a ACK.
    manager = ActuatorManager(driver)
    manager.start()
    assert [(a.channel, a.success) for a in manager.execute_sequence(comandos)] == [
        (a.channel, a.success) for a in acks
    ]


def test_el_panel_sigue_accionando_por_la_costura(supervisor) -> None:  # noqa: ANN001
    """Conducta idéntica: las seis acciones siguen tocando el gabinete real."""
    panel, gpio = supervisor.local_api, supervisor.gpio
    gpio.simulate_sasmex(active=True)
    assert gpio.siren_sounding is True
    panel.silence()
    assert gpio.siren_sounding is False and gpio.audible_silenced is True
    panel.reset_alert()
    assert gpio.sasmex_active is False
    panel.run_siren_test()
    assert gpio.siren_sounding is True
    gpio.reset()
    panel.toggle_test_mode()
    assert gpio.test_mode_active is True
    panel.toggle_test_mode()
    assert gpio.test_mode_active is False


def test_el_dashboard_lee_el_gabinete_con_UNA_sola_instantanea(supervisor) -> None:  # noqa: ANN001
    """El panel poll­ea a 1 Hz: pedir siete propiedades por request son siete
    cruces del futuro IPC donde basta uno."""
    costura = supervisor.gpio_link
    llamadas: list[int] = []
    original = costura.snapshot

    def _contar():  # noqa: ANN202
        llamadas.append(1)
        return original()

    supervisor.local_api._link = type(
        "_Espia",
        (),
        {
            "snapshot": staticmethod(_contar),
            "apply": staticmethod(costura.apply),
            "action": staticmethod(costura.action),
            "subscribe": staticmethod(costura.subscribe),
        },
    )()
    supervisor.local_api.status()
    assert len(llamadas) == 1, f"el panel pidió {len(llamadas)} instantáneas por request"
