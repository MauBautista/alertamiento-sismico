"""[T-9.75] Re-armar devuelve a los secundarios lo que el silencio les quitó.

El re-armado de los audibles viaja por radio desde T-5.25, y decidía con
`alert_latched`: «hay alguna alerta enclavada». Eso también es verdad con una
alerta que no pide la sirena —un escalón RESTRICTED que sólo manda el ascensor,
un cuórum en un sitio declarado sin sirena—. Medido el 2026-10-23: el principal
no hacía sonar la suya, porque nadie la pidió, y mandaba `activate {siren: True}`
a todo el inmueble.

Ahora hay sirena que devolver si se les MANDÓ desde el último cierre de alerta
(`LoraLink.sirena_enviada`) o si una alerta del principal la PIDE
(`siren_demanded`, del dueño de los pines). Ninguna de las dos la cambia el
silencio.

El arreglo ingenuo («propaga si la sirena suena») deja MUDOS a los secundarios
durante un SASMEX real en D3: el aviso de silencio llega ANTES que el estado
nuevo, así que el observador puede ver la instantánea de antes del re-armado, y
con los audibles silenciados `siren_reason` vale `None`. Es una carrera y no un
orden fijo, así que se prueba con esa instantánea a mano.

Los casos de punta a punta corren con las dos costuras, la local y la del socket
(D3).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from simulators.lora import FakeSecondaryCabinet, SimulatedLoraTransport
from simulators.quake import quake_packets
from simulators.rs4d import RS4DSimulator
from takab_edge.config import EdgeSettings, EquipmentProfile, LoraConfig, SecondaryCabinet
from takab_edge.contracts import ActuatorChannel, Tier
from takab_edge.gpio import GpioController
from takab_edge.gpio_link import GpioSnapshot
from takab_edge.pinlink import codec as cd
from takab_edge.supervisor import EdgeSupervisor

_CLAVE = b"clave-lora-de-sitio-0123456789ab"
_SUENA = ("activate", {"siren": True, "strobe": True})


def _hasta(condicion: Callable[[], bool], timeout: float = 3.0) -> bool:
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return condicion()


class _Gabinete:
    """Un `EdgeSupervisor` de verdad con un secundario simulado por radio."""

    def __init__(self, settings: EdgeSettings, costura: str, **ajustes: object) -> None:
        transporte = SimulatedLoraTransport()
        self.nodo = transporte.attach(FakeSecondaryCabinet(_CLAVE, 258))
        cfg = settings.model_copy(
            update={
                **ajustes,
                "gpio_link": costura,
                "lora": LoraConfig(
                    enabled=True,
                    alarm_retry_s=0.05,
                    secondaries=[SecondaryCabinet(id=258, name="AZOTEA")],
                ),
            }
        )
        self.sup = EdgeSupervisor(
            cfg, seedlink_source=None, lora_transport=transporte, lora_site_key=_CLAVE
        )
        self.sup.start()
        # Lo que sale hacia la antena, orden por orden.
        self.ordenes: list[tuple[str, dict]] = []
        propagar = self.sup.lora.propagate

        def _anotada(action: str, **flags: bool) -> None:
            self.ordenes.append((action, flags))
            propagar(action, **flags)

        self.sup.lora.propagate = _anotada
        # Se registra DESPUÉS del espejo a los secundarios, y la costura avisa en el
        # orden de registro: cuando este observador ve un aviso, el espejo ya decidió.
        self.avisos: list[bool] = []
        self.sup.gpio_link.subscribe("silence", self.avisos.append)

    def silenciar_y_rearmar(self) -> None:
        """Por el camino real: `silence_audibles()` es lo que llaman el botón del
        panel y el pulsador físico del gabinete."""
        self.sup.gpio.silence_audibles(True)
        assert _hasta(lambda: self.avisos == [True]), "el aviso de silencio no llegó"
        self.sup.gpio.silence_audibles(False)
        assert _hasta(lambda: self.avisos == [True, False]), "el aviso de re-armado no llegó"

    def parar(self) -> None:
        self.sup.stop()


@pytest.fixture(params=["local", "ipc"])
def gabinete(request: pytest.FixtureRequest, settings: EdgeSettings) -> Iterator[_Gabinete]:
    g = _Gabinete(settings, request.param)
    try:
        yield g
    finally:
        g.parar()


def test_una_alerta_SIN_sirena_no_la_hace_sonar_a_distancia_al_rearmar(gabinete) -> None:  # noqa: ANN001
    """El defecto medido el 2026-10-23: el ascensor solo, y la sirena del inmueble
    entero sonando al re-armar."""
    gabinete.sup.gpio_link.apply([(ActuatorChannel.ELEVATOR, True)])
    snap = gabinete.sup.gpio_link.snapshot()
    assert snap.alert_latched and not snap.siren_sounding, (
        "premisa: hay una alerta enclavada y nadie pidió la sirena"
    )

    gabinete.silenciar_y_rearmar()

    assert gabinete.ordenes == [("silence", {})], (
        "re-armar mandó a los secundarios algo más que el silencio, con la sirena "
        f"del principal callada porque nadie la pidió: {gabinete.ordenes}"
    )
    time.sleep(0.2)
    assert gabinete.nodo.siren_on is False, "la sirena del secundario suena sin que nadie la pida"


def test_un_SASMEX_enclavado_vuelve_a_sonar_a_distancia_al_rearmar(gabinete) -> None:  # noqa: ANN001
    """La otra mitad, y la que cuesta vidas: callar a los secundarios en un sismo."""
    gabinete.sup.gpio.simulate_sasmex(active=True)
    assert _hasta(lambda: gabinete.nodo.siren_on), "premisa: el SASMEX suena a distancia"

    gabinete.sup.gpio.silence_audibles(True)
    assert _hasta(lambda: not gabinete.nodo.siren_on), "premisa: el silencio llega al secundario"
    gabinete.sup.gpio.silence_audibles(False)

    assert _hasta(lambda: gabinete.nodo.siren_on), (
        "re-armar durante un SASMEX enclavado dejó MUDO al secundario: el principal "
        f"vuelve a sonar y el resto del inmueble no (órdenes: {gabinete.ordenes})"
    )


def test_la_sirena_pedida_por_el_cuorum_vuelve_a_sonar_a_distancia(gabinete) -> None:  # noqa: ANN001
    """Un cuórum (o una regla) que pide la sirena: llega al dueño como demanda de
    `takab-edge`, la misma que aplica `RelayActuator`."""
    gabinete.sup.gpio_link.apply([(ActuatorChannel.SIREN, True), (ActuatorChannel.STROBE, True)])

    gabinete.silenciar_y_rearmar()

    assert _SUENA in gabinete.ordenes, f"re-armar no devolvió la sirena: {gabinete.ordenes}"
    assert _hasta(lambda: gabinete.nodo.siren_on), "la sirena pedida no volvió al secundario"


def test_silenciar_SIN_alerta_no_enciende_nada_a_distancia(gabinete) -> None:  # noqa: ANN001
    """El silencio sin alerta de la visita del 2026-10-21, ahora con radio.

    El silencio viaja con el bit del estrobo puesto («deja el estrobo»), y el
    simulador —que es la especificación ejecutable del firmware— lo ENCENDÍA. Un
    silencio que enciende el estrobo de todo el inmueble es una alarma inventada.
    """
    gabinete.silenciar_y_rearmar()

    assert gabinete.ordenes == [("silence", {})], gabinete.ordenes
    assert _hasta(lambda: gabinete.nodo.received), "premisa: el silencio llegó al secundario"
    time.sleep(0.2)
    assert (gabinete.nodo.siren_on, gabinete.nodo.strobe_on, gabinete.nodo.alarm_active) == (
        False,
        False,
        False,
    ), "silenciar un gabinete en calma encendió algo en el secundario"


def test_con_un_dueno_que_no_sabe_decirlo_rearmar_se_pasa_de_mas(settings, monkeypatch) -> None:  # noqa: ANN001
    """La ventana del layout A/B: `takab-edge` nuevo y `takab-gpio` sin reiniciar.

    El dueño viejo no conoce `siren_demanded`, y el códec lo deja en
    `campos_desconocidos` con un `False` que no significa nada. Leerlo como «la
    sirena no está pedida» callaría a los secundarios en un SASMEX. Se hace lo de
    antes, que se pasa de más y nunca se queda corto.
    """
    transportar = cd.instantanea_a_json

    def _dueno_anterior(snap):  # noqa: ANN001, ANN202
        datos = transportar(snap)
        datos.pop("siren_demanded")
        datos[cd.CLAVE_CAMPOS_DEL_DUENO].remove("siren_demanded")
        return datos

    monkeypatch.setattr(cd, "instantanea_a_json", _dueno_anterior)
    g = _Gabinete(settings, "ipc")
    try:
        g.sup.gpio_link.apply([(ActuatorChannel.ELEVATOR, True)])
        assert "siren_demanded" in g.sup.gpio_link.snapshot().campos_desconocidos

        g.silenciar_y_rearmar()

        assert _SUENA in g.ordenes, (
            f"con un dueño que no sabe decir si la sirena está pedida, re-armar calló a "
            f"los secundarios: {g.ordenes}"
        )
    finally:
        g.parar()


def test_el_dueno_dice_si_la_sirena_esta_pedida_y_el_silencio_no_lo_cambia(settings) -> None:  # noqa: ANN001
    """`siren_demanded` es la demanda de ALERTA sobre la sirena, no si suena."""
    gpio = GpioController(settings)
    gpio.start()
    try:
        assert gpio.snapshot().siren_demanded is False
        gpio.activate(ActuatorChannel.ELEVATOR)
        assert gpio.snapshot().siren_demanded is False, "el ascensor no pide la sirena"
        gpio.run_siren_test()
        snap = gpio.snapshot()
        assert snap.siren_sounding and not snap.siren_demanded, "una prueba no es una alerta"
        gpio.reset()

        gpio.simulate_sasmex(active=True)
        gpio.silence_audibles(True)
        snap = gpio.snapshot()
        assert not snap.siren_sounding and snap.siren_demanded, (
            "el silencio calla la sirena, no retira la alerta que la pide"
        )
        gpio.reset()
        assert gpio.snapshot().siren_demanded is False, "CERRAR ALERTA suelta la demanda"

        gpio.activate(ActuatorChannel.SIREN)
        assert gpio.snapshot().siren_demanded is True, "la demanda de una regla o del cuórum"
        gpio.deactivate(ActuatorChannel.SIREN)
        assert gpio.snapshot().siren_demanded is False, "retirada desde la consola"
    finally:
        gpio.stop()


def test_lo_que_se_les_MANDO_vuelve_aunque_el_principal_no_tenga_sirena(settings) -> None:  # noqa: ANN001
    """El hueco que encontró la revisión: un principal sin sirena instalada.

    Con la actuación instrumental activada, un EVACUATE manda la sirena por radio
    sin mirar el equipo del principal, que no la pide porque no la tiene. Si el
    re-armado preguntara sólo al dueño de los pines, el secundario se quedaría
    callado tras el silencio, y antes de esta ficha volvía a sonar.
    """
    for costura in ("local", "ipc"):
        g = _Gabinete(
            settings,
            costura,
            instrumental_actuation=True,
            equipment=EquipmentProfile(siren=False),
        )
        try:
            sim = RS4DSimulator(station=g.sup.settings.station)
            for paquete in quake_packets(sim, datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)):
                g.sup.seedlink.feed(paquete)
            assert g.sup.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
            assert _hasta(lambda g=g: g.nodo.siren_on), "premisa: el EVACUATE suena a distancia"
            assert g.sup.gpio_link.snapshot().siren_demanded is False, (
                "premisa: el principal no pide la sirena que no tiene"
            )

            g.silenciar_y_rearmar()

            assert _hasta(lambda g=g: g.nodo.siren_on), (
                f"[{costura}] re-armar dejó callado al secundario que el silencio "
                f"había callado: {g.ordenes}"
            )
        finally:
            g.parar()


def test_cerrar_alerta_olvida_la_sirena_que_se_les_mando(gabinete) -> None:  # noqa: ANN001
    """La memoria del radio no puede inventar la alarma siguiente."""
    gabinete.sup.gpio.simulate_sasmex(active=True)
    assert _hasta(lambda: gabinete.nodo.siren_on), "premisa: el SASMEX suena a distancia"
    gabinete.sup.gpio.simulate_sasmex(active=False)
    gabinete.sup.local_api.reset_alert()
    assert _hasta(lambda: not gabinete.nodo.alarm_active), "premisa: el CLEAR llegó"
    del gabinete.ordenes[:]

    gabinete.silenciar_y_rearmar()

    assert gabinete.ordenes == [("silence", {})], (
        f"re-armar en calma, después de cerrar la alerta, volvió a mandar algo: {gabinete.ordenes}"
    )


class _Radio:
    def __init__(self, *, sirena_enviada: bool) -> None:
        self.sirena_enviada = sirena_enviada
        self.ordenes: list[tuple[str, dict]] = []

    def propagate(self, action: str, **flags: bool) -> None:
        self.ordenes.append((action, flags))


class _Costura:
    def __init__(self, snap: GpioSnapshot) -> None:
        self._snap = snap

    def snapshot(self) -> GpioSnapshot:
        return self._snap


def _rearmar_con(snap: GpioSnapshot, *, sirena_enviada: bool) -> list[tuple[str, dict]]:
    radio = _Radio(sirena_enviada=sirena_enviada)
    supervisor = SimpleNamespace(lora=radio, gpio_link=_Costura(snap))
    EdgeSupervisor._al_silencio_de_los_secundarios(supervisor, False)
    return radio.ordenes


def test_en_D3_decide_bien_con_la_instantanea_de_ANTES_del_rearmado(settings) -> None:  # noqa: ANN001
    """La trampa de D3, sin depender de quién gane la carrera.

    El aviso de silencio puede llegar con la instantánea silenciada todavía en la
    caché. Aquí se le da ésa a propósito, y con la memoria del radio vacía, como
    tras un reinicio de `takab-edge`: el SASMEX sigue enclavado en el dueño.
    """
    gpio = GpioController(settings)
    gpio.start()
    try:
        gpio.simulate_sasmex(active=True)
        gpio.silence_audibles(True)
        antes = gpio.snapshot()
        gpio.reset()
        gpio.activate(ActuatorChannel.ELEVATOR)
        gpio.silence_audibles(True)
        sin_sirena = gpio.snapshot()
    finally:
        gpio.stop()
    assert not antes.siren_sounding and antes.siren_reason is None, (
        "premisa: la instantánea silenciada no dice que la sirena suene"
    )

    assert _rearmar_con(antes, sirena_enviada=False) == [_SUENA], (
        "con la instantánea de antes del re-armado, un SASMEX enclavado dejó MUDOS a "
        "los secundarios"
    )
    assert _rearmar_con(sin_sirena, sirena_enviada=False) == [], "el ascensor no pide la sirena"
    assert _rearmar_con(sin_sirena, sirena_enviada=True) == [_SUENA], (
        "lo que se les mandó vuelve aunque el principal no la pida"
    )
