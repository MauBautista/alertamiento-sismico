"""gpio — reflejo SASMEX→sirena in-process, fail-safe por canal y cableado WR-1."""

from __future__ import annotations

import pytest
from takab_edge.contracts import ActuatorChannel, FailSafeMode, SasmexSignal
from takab_edge.gpio import LOCAL_RELAY_CHANNELS, REFLEX_CHANNELS, GpioController


@pytest.fixture
def gpio(settings):
    controller = GpioController(settings)
    controller.start()
    try:
        yield controller
    finally:
        controller.stop()


def test_sasmex_reflex_energizes_siren_and_strobe(gpio):
    gpio.simulate_sasmex(active=True)
    for channel in REFLEX_CHANNELS:
        assert gpio.relay_state(channel).energized is True
    assert gpio.sasmex_active is True


def test_new_alert_resounds_despite_prior_silence_and_notifies(gpio):
    # Un silencio PREVIO no muta una alarma nueva (NFPA-72); rules/cloud sí se enteran.
    received: list[SasmexSignal] = []
    gpio.on_sasmex(received.append)
    gpio.silence_audibles(True)  # silencio de un episodio anterior

    gpio.simulate_sasmex(active=True)  # ALARMA NUEVA → re-suena
    assert gpio.siren_sounding is True
    assert received and received[0].active is True


def test_cires_test_pulse_does_not_actuate(gpio):
    gpio.simulate_sasmex(active=True, is_test=True)
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is False
    assert gpio.sasmex_active is False  # heartbeat CIRES: sin alerta fantasma (regla de oro 7)


def test_relay_states_carry_failsafe_profile(gpio):
    by_channel = {r.channel: r for r in gpio.relay_states()}
    assert by_channel[ActuatorChannel.SIREN].fail_safe is FailSafeMode.NORMALLY_OPEN
    assert by_channel[ActuatorChannel.DOOR_RETAINER].fail_safe is FailSafeMode.NORMALLY_CLOSED
    assert by_channel[ActuatorChannel.GAS_VALVE].fail_safe is FailSafeMode.FAIL_CLOSE
    assert len(by_channel) == 5


def test_unknown_relay_channel_raises(gpio):
    class Fake:
        value = "nope"

    with pytest.raises(KeyError):
        gpio.set_relay(Fake(), True)  # type: ignore[arg-type]


def test_wr1_mock_pin_wiring(gpio):
    # El contacto seco cierra a masa (pull-up): pin en LOW ⇒ contacto cerrado.
    assert gpio._button is not None
    gpio._button.pin.drive_high()
    assert gpio._button.is_pressed is False
    gpio._button.pin.drive_low()
    assert gpio._button.is_pressed is True


# --- T-1.3: fail-safe NO/NC/fail-close por canal (SPOF-07) ---


def test_initial_states_are_normal_operation(gpio):
    # NO reposa de-energizado (inactivo); NC/fail_close reposan energizados (retienen).
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is False
    assert gpio.relay_state(ActuatorChannel.ELEVATOR).energized is False
    assert gpio.relay_state(ActuatorChannel.DOOR_RETAINER).energized is True
    assert gpio.relay_state(ActuatorChannel.GAS_VALVE).energized is True
    # Ninguno está en estado de protección al arrancar.
    assert not any(r.activated for r in gpio.relay_states())


def test_no_channel_activates_by_energizing(gpio):
    gpio.activate(ActuatorChannel.SIREN)
    state = gpio.relay_state(ActuatorChannel.SIREN)
    assert state.energized is True and state.activated is True
    gpio.deactivate(ActuatorChannel.SIREN)
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is False


def test_nc_channel_activates_by_deenergizing(gpio):
    # Retenedor de puerta (NC): activar (emergencia) = LIBERAR = de-energizar.
    gpio.activate(ActuatorChannel.DOOR_RETAINER)
    state = gpio.relay_state(ActuatorChannel.DOOR_RETAINER)
    assert state.energized is False and state.activated is True
    gpio.deactivate(ActuatorChannel.DOOR_RETAINER)
    assert gpio.relay_state(ActuatorChannel.DOOR_RETAINER).energized is True


def test_failclose_channel_activates_by_deenergizing(gpio):
    gpio.activate(ActuatorChannel.GAS_VALVE)
    state = gpio.relay_state(ActuatorChannel.GAS_VALVE)
    assert state.energized is False and state.activated is True  # gas CERRADO


def test_drive_all_safe_is_safe_for_every_channel(gpio):
    # Energiza/activa varios y luego lleva todo a estado seguro (corte de energía).
    gpio.activate(ActuatorChannel.SIREN)
    gpio.deactivate(ActuatorChannel.GAS_VALVE)  # gas energizado (abierto)
    gpio.drive_all_safe()
    # Estado seguro = de-energizado en TODOS los canales; y los fail-safe (gas/puerta)
    # quedan en su acción protectora (cerrado/liberado).
    assert all(r.energized is False for r in gpio.relay_states())
    assert gpio.relay_state(ActuatorChannel.GAS_VALVE).activated is True
    assert gpio.relay_state(ActuatorChannel.DOOR_RETAINER).activated is True
    assert gpio.relay_state(ActuatorChannel.SIREN).activated is False


# --- T-1.3: latencia, debounce, botones, 1000 ciclos ---


def test_reflex_latency_is_measured_and_under_budget(gpio):
    gpio.simulate_sasmex(active=True)
    assert gpio.last_reflex_latency_s is not None
    # Ruta software del reflejo: muy por debajo del presupuesto (el 50 ms de debounce
    # y el interrupt/relé reales son parte del <100 ms total, medidos en hardware).
    assert gpio.last_reflex_latency_s < 0.05


def test_debounce_configured_to_50ms(gpio):
    assert gpio.debounce_s == 0.05
    assert gpio.settings.debounce_ms == 50


def test_silence_button_toggles_arm(gpio):
    gpio._on_silence_button()
    assert gpio.audible_silenced is True
    gpio._on_silence_button()
    assert gpio.audible_silenced is False


def test_test_button_self_test_sounds_siren_even_when_silenced(gpio):
    gpio.silence_audibles(True)  # silenciado
    gpio.run_siren_test(duration_s=10)  # prueba deliberada del operador
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is True


def test_reflex_survives_1000_cycles(gpio):
    for _ in range(1000):
        gpio.reset()
        gpio.simulate_sasmex(active=True)
        assert gpio.is_activated(ActuatorChannel.SIREN)
    assert gpio.last_reflex_latency_s is not None


# --- T-1.3: arbitraje de demandas (hallazgos de la revisión adversarial) ---


def test_silence_stops_an_already_sounding_siren(gpio):
    # HALLAZGO B: el silencio debe apagar YA lo que suena, no sólo inhibir futuros.
    gpio.simulate_sasmex(active=True)
    assert gpio.siren_sounding is True
    gpio.silence_audibles(True)
    assert gpio.siren_sounding is False
    # ...pero la ALERTA sigue viva (dashboard/estrobo), no se perdió el evento.
    assert gpio.sasmex_active is True


def test_self_test_end_never_silences_a_live_alert(gpio):
    # HALLAZGO A (crítico): fin del self-test NO puede callar una alerta real en curso.
    gpio.simulate_sasmex(active=True)  # alerta real → sirena sonando
    gpio.run_siren_test(duration_s=100)
    gpio._end_siren_test()  # fin de la prueba (determinista)
    assert gpio.siren_sounding is True  # la alerta viva mantiene la sirena


def test_self_test_end_turns_off_siren_when_no_alert(gpio):
    gpio.run_siren_test(duration_s=100)
    assert gpio.siren_sounding is True
    gpio._end_siren_test()
    assert gpio.siren_sounding is False  # sin alerta → se apaga


def test_self_test_does_not_raise_phantom_sasmex_alert(gpio):
    # HALLAZGO D: la prueba energiza la sirena pero NO es una alerta SASMEX.
    gpio.run_siren_test(duration_s=100)
    assert gpio.siren_sounding is True
    assert gpio.sasmex_active is False  # sin alerta fantasma en el dashboard


def test_silence_keeps_visual_strobe(gpio):
    # HALLAZGO E: silenciar el audible NO debe apagar el estrobo (accesibilidad).
    gpio.simulate_sasmex(active=True)  # alerta: sirena + estrobo
    gpio.silence_audibles(True)  # silenciar sólo el audible
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is False
    assert gpio.relay_state(ActuatorChannel.STROBE).energized is True  # visual persiste


def test_new_sasmex_alert_resounds_after_silence(gpio):
    # RE-REVISIÓN #1: un silencio previo NO puede mutar una alarma NUEVA (NFPA-72).
    gpio.simulate_sasmex(active=True)
    gpio.silence_audibles(True)
    assert gpio.siren_sounding is False  # episodio actual silenciado
    gpio.simulate_sasmex(active=True)  # flanco de contacto NUEVO
    assert gpio.siren_sounding is True  # re-suena


def test_alert_latches_across_contact_open(gpio):
    # RE-REVISIÓN #2: la apertura del contacto NO desenclava la alerta (hasta silencio/reset).
    gpio.simulate_sasmex(active=True)
    assert gpio.siren_sounding is True
    gpio.simulate_sasmex(active=False)  # el contacto se abre
    assert gpio.siren_sounding is True
    assert gpio.sasmex_active is True


def test_drive_all_safe_is_durable(gpio):
    # RE-REVISIÓN #3: un comando posterior NO debe revertir el estado seguro (reabrir el gas).
    gpio.activate(ActuatorChannel.GAS_VALVE)  # gas cerrado (protección)
    gpio.drive_all_safe()
    assert gpio.relay_state(ActuatorChannel.GAS_VALVE).energized is False
    gpio.deactivate(ActuatorChannel.GAS_VALVE)
    assert gpio.relay_state(ActuatorChannel.GAS_VALVE).energized is False  # sigue cerrado
    gpio.reset()  # sólo un reset explícito restaura operación normal
    assert gpio.relay_state(ActuatorChannel.GAS_VALVE).energized is True


# --- T-2.26: alert_latched — decide si CERRAR ALERTA se ofrece en el panel ---


def test_alert_latched_true_while_rules_demand_active(gpio):
    # El estado real observado el 2026-08-01: tier ya normal, relés aún enclavados.
    gpio.activate(ActuatorChannel.GAS_VALVE)
    assert gpio.alert_latched is True
    assert gpio.sasmex_active is False


def test_alert_latched_true_while_sasmex_latched_even_if_silenced(gpio):
    gpio.simulate_sasmex(active=True)
    gpio.silence_audibles(True)  # silenciar el audible NO cierra la alerta
    assert gpio.alert_latched is True


def test_alert_latched_false_after_reset_and_when_idle(gpio):
    assert gpio.alert_latched is False  # idle
    gpio.simulate_sasmex(active=True)
    gpio.activate(ActuatorChannel.GAS_VALVE)
    gpio.reset()
    assert gpio.alert_latched is False


def test_deactivated_demand_does_not_count_as_latched(gpio):
    # deactivate() deja la llave en False sin borrarla: any(values), no bool(dict).
    gpio.activate(ActuatorChannel.ELEVATOR)
    gpio.deactivate(ActuatorChannel.ELEVATOR)
    assert gpio.alert_latched is False


def test_siren_test_does_not_set_alert_latched(gpio):
    gpio.run_siren_test(duration_s=100)
    assert gpio.alert_latched is False  # una prueba NO es una alerta


def test_concurrent_transitions_keep_state_coherent(gpio):
    # HALLAZGO C / RE-REVISIÓN #4: bajo contención en el MISMO canal, la sombra
    # (_energized) y el relé físico nunca divergen de las demandas (un torn update
    # sin lock lo violaría). Ejercita el RLock de verdad.
    import threading

    errors: list[BaseException] = []
    stop = threading.Event()

    def churn(fn):
        try:
            while not stop.is_set():
                fn()
        except BaseException as exc:  # noqa: BLE001 — recolecta cualquier fallo del hilo
            errors.append(exc)

    gas = ActuatorChannel.GAS_VALVE
    ops = [
        lambda: gpio.activate(gas),
        lambda: gpio.deactivate(gas),
        lambda: gpio.simulate_sasmex(active=True),
        lambda: gpio.silence_audibles(True),
        lambda: gpio.silence_audibles(False),
        lambda: gpio.relay_states(),
    ]
    threads = [threading.Thread(target=churn, args=(op,)) for op in ops]
    for t in threads:
        t.start()
    for _ in range(3000):
        gpio.relay_states()  # el hilo principal también contiende
    stop.set()
    for t in threads:
        t.join()
    assert not errors, errors
    # Quiesce: sombra y relé físico coinciden con las demandas en TODOS los canales.
    with gpio._lock:
        for channel in LOCAL_RELAY_CHANNELS:
            desired = gpio._desired_energized(channel)
            assert gpio._energized[channel] == desired, channel
            assert bool(gpio._relays[channel].value) == desired, channel


def test_held_alert_contact_seeds_reflex(gpio):
    # SPOF-02: si el contacto de alerta ya está cerrado al arrancar (alerta sostenida a
    # través de un reinicio del Pi), no hay flanco nuevo → el reflejo se siembra leyendo
    # el NIVEL del contacto (lo que `_on_start` invoca), para no quedar mudo en el traspaso.
    gpio._button.pin.drive_low()  # contacto de alerta cerrado (sostenido)
    assert gpio._button.is_pressed is True
    gpio._seed_from_held_contact()
    assert gpio.sasmex_active is True
    assert gpio.siren_sounding is True


# --- Autodiagnóstico del gabinete (T-1.59 / M-2) --------------------------------


def test_self_test_pulsa_no_audibles_con_readback_y_restaura(gpio):
    before = {c: gpio.relay_state(c).energized for c in LOCAL_RELAY_CHANNELS}
    result = gpio.run_cabinet_self_test(pulse_s=0.01, gap_s=0.0)
    assert result["ok"] is True and result["reason"] is None
    for channel in ("strobe", "gas_valve", "elevator", "door_retainer"):
        relay = result["relays"][channel]
        assert relay["pulsed"] is True and relay["readback_ok"] is True
    # La sirena SOLO se lee, jamás se pulsa.
    assert result["relays"]["siren"]["pulsed"] is False
    # Todo regresó al estado que exige el modelo de demandas (reposo).
    after = {c: gpio.relay_state(c).energized for c in LOCAL_RELAY_CHANNELS}
    assert after == before


def test_self_test_jamas_energiza_la_sirena(gpio):
    """El relé de la sirena no cambia eléctricamente en NINGÚN momento del test."""
    siren = gpio._relays[ActuatorChannel.SIREN]
    transitions: list[bool] = []
    original_on, original_off = siren.on, siren.off

    def spy_on():
        transitions.append(True)
        original_on()

    def spy_off():
        transitions.append(False)
        original_off()

    siren.on, siren.off = spy_on, spy_off
    try:
        result = gpio.run_cabinet_self_test(pulse_s=0.01, gap_s=0.0)
    finally:
        siren.on, siren.off = original_on, original_off
    assert result["ok"] is True
    assert transitions == []  # cero llamadas eléctricas a la sirena
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is False


def test_self_test_rechaza_con_alerta_sasmex_viva(gpio):
    gpio.simulate_sasmex(active=True)
    result = gpio.run_cabinet_self_test(pulse_s=0.01, gap_s=0.0)
    assert result["ok"] is False
    assert "alerta" in result["reason"]
    # La protección sigue intacta: la sirena sigue sonando.
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is True


def test_self_test_rechaza_con_demanda_de_rules(gpio):
    gpio.activate(ActuatorChannel.GAS_VALVE)  # protección instrumental viva
    result = gpio.run_cabinet_self_test(pulse_s=0.01, gap_s=0.0)
    assert result["ok"] is False and "alerta" in result["reason"]


def test_self_test_rechaza_en_estado_seguro_forzado(gpio):
    gpio.drive_all_safe()
    result = gpio.run_cabinet_self_test(pulse_s=0.01, gap_s=0.0)
    assert result["ok"] is False


# --- Prueba LOCAL de actuación (T-1.67) --------------------------------------
# Ejercicio completo del gabinete disparado en LOCAL (panel LAN), SIN alertar al
# sistema: sirena+estrobo SUENAN/se ven, gas/ascensor/puertas hacen PULSO de
# verificación. Jamás publica evento ni abre incidente (eso es cloud-side, atado
# a que se disparen los callbacks SASMEX — que aquí NO se tocan).


def test_prueba_local_sostiene_audibles_y_pulsa_protectores(gpio):
    before = {c: gpio.relay_state(c).energized for c in LOCAL_RELAY_CHANNELS}
    result = gpio.run_local_actuation_test(hold_s=100, pulse_s=0.01, gap_s=0.0)
    assert result["ok"] is True and result["reason"] is None
    # Sirena + estrobo SOSTENIDOS (se oyen/ven durante la prueba).
    for channel in ("siren", "strobe"):
        assert result["relays"][channel]["held"] is True
        assert result["relays"][channel]["readback_ok"] is True
    assert gpio.siren_sounding is True
    assert gpio.relay_state(ActuatorChannel.STROBE).energized is True
    # Gas/ascensor/puertas: PULSO de verificación con readback, ya de regreso a seguro.
    for channel in ("gas_valve", "elevator", "door_retainer"):
        assert result["relays"][channel]["pulsed"] is True
        assert result["relays"][channel]["readback_ok"] is True
    for channel in (
        ActuatorChannel.GAS_VALVE,
        ActuatorChannel.ELEVATOR,
        ActuatorChannel.DOOR_RETAINER,
    ):
        assert gpio.relay_state(channel).energized == before[channel]
    gpio.reset()


def test_prueba_local_no_es_alerta_fantasma(gpio):
    """Suena la sirena pero NO es una alerta SASMEX (regla de oro 7)."""
    gpio.run_local_actuation_test(hold_s=100, pulse_s=0.01, gap_s=0.0)
    assert gpio.siren_sounding is True
    assert gpio.sasmex_active is False
    gpio.reset()


def test_prueba_local_jamas_dispara_callbacks_sasmex(gpio):
    """La garantía de aislamiento: sin callbacks SASMEX no hay rules→cloud→incidente."""
    disparos: list[SasmexSignal] = []
    gpio.on_sasmex(disparos.append)
    gpio.run_local_actuation_test(hold_s=100, pulse_s=0.01, gap_s=0.0)
    assert disparos == []  # NADA se propaga: la prueba es puramente in-process
    gpio.reset()


def test_prueba_local_rechazada_con_alerta_viva(gpio):
    gpio.simulate_sasmex(active=True)
    result = gpio.run_local_actuation_test(hold_s=1, pulse_s=0.01, gap_s=0.0)
    assert result["ok"] is False and "alerta" in result["reason"]
    assert gpio.relay_state(ActuatorChannel.SIREN).energized is True  # protección intacta


def test_fin_de_prueba_local_jamas_silencia_alerta_viva(gpio):
    gpio.run_local_actuation_test(hold_s=100, pulse_s=0.01, gap_s=0.0)
    gpio.simulate_sasmex(active=True)  # alerta real durante la prueba
    gpio._end_actuation_test()  # el temporizador vence
    assert gpio.siren_sounding is True  # la alerta real GANA


def test_fin_de_prueba_local_apaga_audibles_sin_alerta(gpio):
    gpio.run_local_actuation_test(hold_s=100, pulse_s=0.01, gap_s=0.0)
    assert gpio.siren_sounding is True
    gpio._end_actuation_test()
    assert gpio.siren_sounding is False
    assert gpio.relay_state(ActuatorChannel.STROBE).energized is False


# --- Modo prueba del WR-1 (T-1.69) -------------------------------------------
# Ventana corta y auto-expirable: el gabinete protege en LOCAL igual (reflejo)
# pero el supervisor NO publica a la nube. gpio solo GUARDA la bandera; la
# supresión de la publicación vive en el supervisor (test aparte).


def test_modo_prueba_se_arma_activo_y_se_desarma(gpio):
    assert gpio.test_mode_active is False
    gpio.arm_test_mode(100.0)
    assert gpio.test_mode_active is True
    assert 0.0 < gpio.test_mode_remaining_s <= 100.0
    gpio.disarm_test_mode()
    assert gpio.test_mode_active is False
    assert gpio.test_mode_remaining_s == 0.0


def test_modo_prueba_expira_solo(gpio):
    gpio.arm_test_mode(0.0)  # ventana nula ⇒ ya vencido
    assert gpio.test_mode_active is False


def test_modo_prueba_no_altera_el_reflejo(gpio):
    """En modo prueba el WR-1 SIGUE sonando la sirena en local (confirma el cableado)."""
    gpio.arm_test_mode(100.0)
    gpio.simulate_sasmex(active=True)
    assert gpio.siren_sounding is True  # protección local intacta
    assert gpio.sasmex_active is True


def test_relay_states_tras_stop_queda_vacio_sin_keyerror(gpio):
    """REGRESIÓN (journal 2026-07-30): un GET del panel DURANTE el shutdown reventaba.

    `_on_stop` vacía `_relays`/`_energized`, pero los hilos HTTP del panel son
    daemon y pueden servir un `status()` en esa ventana: `relay_states()` hacía
    `self._energized[channel]` sobre el dict vaciado ⇒ KeyError ⇒ 500 al kiosco.
    Tras el stop la respuesta honesta es VACÍO — los dispositivos están cerrados
    y su estado eléctrico ya no se mide; inventar 5 filas sería peor (regla 7).
    """
    assert len(gpio.relay_states()) == len(LOCAL_RELAY_CHANNELS)  # vivo: 5 relés
    gpio.stop()
    assert gpio.relay_states() == []  # detenido: vacío, JAMÁS un KeyError
    gpio.stop()  # doble stop sigue siendo inocuo
    assert gpio.relay_states() == []


# ---------------------------------------------------------------------------
# [T-2.65 · REGLA DE ORO 1] Ninguna config de la nube alcanza el reflejo
# ---------------------------------------------------------------------------


def _sin_equipamiento():
    from takab_edge.config import EquipmentProfile

    return EquipmentProfile(
        siren=False, strobe=False, gas_valve=False, elevator=False, door_retainer=False
    )


def test_el_traspaso_hw_software_tras_reinicio_no_lo_gatea_el_estado_administrativo(settings):
    """SPOF-02 con el gabinete DADO DE BAJA — y con el flanco perdido DE VERDAD.

    Escenario real: el Pi se reinicia **durante** una alerta. El contacto del WR-1
    sigue cerrado, la sirena ya suena por la ruta eléctrica y el software tiene que
    recogerla al arrancar; si no lo hace, el estado queda inconsistente justo en el
    peor momento (y el operador no puede ni silenciarla desde el panel). `_on_start`
    lo resuelve leyendo el NIVEL del contacto — `_seed_from_held_contact`.

    Dos agujeros medidos que este test cierra:

    1. **El gate administrativo.** Un `if self.settings.is_retired: return` al
       principio de `_seed_from_held_contact` deja mudo ese traspaso y la suite
       entera sigue en «657 passed, 5 skipped»: ningún test le daba a `gpio` una
       config retirada EN ESTE camino.
    2. **Que el test que ya existía no mide el traspaso.** En
       `test_held_alert_contact_seeds_reflex`, el `drive_low()` sobre un controlador
       YA ARRANCADO dispara `when_pressed` —el flanco llega al software— así que el
       reflejo ya está encendido antes de llamar a `_seed_from_held_contact()`, y la
       aserción pasa aunque la siembra no haga nada. Medido: BORRAR el cuerpo entero
       de `_seed_from_held_contact` (`return` a secas) deja la suite en «657 passed,
       5 skipped». Aquí el manejador de flanco se desconecta ANTES de cerrar el
       contacto: eso es exactamente lo que pasa en el reinicio real —el flanco
       ocurrió con el Pi apagado y NADIE se lo entregó al software— y se comprueba
       midiendo que la sirena sigue apagada hasta que la siembra corre.
    """
    from takab_edge.gpio import GpioController

    retirado = settings.model_copy(
        update={"cloud_admin_state": "retired", "equipment": _sin_equipamiento()}
    )
    controller = GpioController(retirado)
    controller.start()
    try:
        assert controller.settings.is_retired is True  # guardarraíl del escenario

        # El flanco ocurrió con el Pi APAGADO: el software no lo ve nunca.
        controller._button.when_pressed = None
        controller._button.pin.drive_low()  # contacto de alerta sostenido
        assert controller._button.is_pressed is True
        assert controller.siren_sounding is False, (
            "el flanco llegó al software: este test estaría midiendo `when_pressed` "
            "y no el traspaso HW→software, que es lo único que corre tras el reinicio"
        )

        controller._seed_from_held_contact()  # lo que invoca `_on_start` al arrancar

        assert controller.sasmex_active is True, (
            "el gabinete se reinició con el contacto SOSTENIDO y el software no "
            "recogió la alerta: el estado administrativo no puede gatear el "
            "traspaso HW→software (SPOF-02)"
        )
        assert controller.siren_sounding is True, "la sirena quedó muda tras el reinicio"
        assert controller.is_activated(ActuatorChannel.STROBE) is True
    finally:
        controller.stop()


class _SettingsEspiadas:
    """Proxy que registra QUÉ campos de `EdgeSettings` lee quien lo sostiene.

    No es un mock: delega TODO en el objeto real, así que el controlador se
    comporta exactamente igual. Solo mide.
    """

    def __init__(self, real) -> None:  # noqa: ANN001 — EdgeSettings, sin importarlo aquí
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "leidos", [])

    def __getattr__(self, nombre: str):
        self.leidos.append(nombre)
        return getattr(self._real, nombre)


#: Únicos campos que el reflejo puede consultar: el CABLEADO FÍSICO del gabinete,
#: que vive en `edge.env` y describe cómo está conectado cada relé. `failsafe` dice
#: si el canal es NO/NC/fail-close, o sea qué nivel eléctrico significa "protegiendo";
#: sin leerlo el reflejo no sabría ni en qué dirección mover el relé.
_CAMPOS_DE_CABLEADO_FISICO = frozenset({"failsafe"})


def test_el_reflejo_no_lee_ni_un_campo_que_publique_la_nube(settings):
    """La versión EXHAUSTIVA del invariante, en vez de una config hostil por campo.

    Los guardianes previos son campo-a-campo: uno da a `gpio` umbrales de 99 g
    (`test_config.py::test_threshold_config_never_affects_sasmex_path`), otro un
    `cloud_admin_state='retired'` y un `equipment` todo-ausente. Eso deja impune
    cualquier OTRO campo del documento firmado, y el documento firmado es un
    `EdgeSettings` COMPLETO: `commands/sync.py` publica `rule_sets.config->'edge'`
    tal cual, así que la consola puede autorizar cualquier clave del modelo. Ir
    campo por campo nunca termina.

    Aquí se mide al revés: se registran TODOS los atributos que el reflejo lee del
    `EdgeSettings` y se exige que sean solo los del cableado físico. Cualquier
    lectura nueva —`is_retired`, `equipment`, `thresholds`, `command_enabled`,
    `instrumental_actuation`, `lora`, la que sea— cae aquí aunque su gate esté
    escrito de forma que hoy no dispare con los defaults (que es justo como se
    cuela: latente, verde, y mortal el día que la nube empuje el valor).

    Complementa —no sustituye— a `test_supervisor.py::…jamas_se_cablea_al_reflejo`:
    aquel prueba que `gpio` sostiene el objeto de ARRANQUE y que la nube nunca se lo
    rebindea; este, que ni siquiera el objeto de arranque se usa para decidir si
    proteger. Hacen falta los dos: el de arranque también viene de un archivo que se
    aprovisiona.
    """
    from takab_edge.gpio import GpioController

    espia = _SettingsEspiadas(settings)
    controller = GpioController(espia)
    controller.start()
    try:
        espia.leidos.clear()  # lo que lee `_on_start` (pines, factory) no es el reflejo
        controller.simulate_sasmex(active=True)

        # Guardarraíl: sin esto, "no leyó nada" pasaría también con el reflejo roto.
        assert controller.siren_sounding is True
        assert controller.is_activated(ActuatorChannel.STROBE) is True

        leidos = set(espia.leidos)
        intrusos = sorted(leidos - _CAMPOS_DE_CABLEADO_FISICO)
        assert not intrusos, (
            f"el reflejo SASMEX→relé consultó {intrusos} de la configuración. Todo "
            "campo de `EdgeSettings` puede llegar EMPUJADO POR LA NUBE (el doc "
            "firmado del config sync es un EdgeSettings entero), así que leerlo en "
            "el camino de vida crea un interruptor remoto para la sirena — aunque "
            "el gate no dispare con los valores de hoy. Solo se permite "
            f"{sorted(_CAMPOS_DE_CABLEADO_FISICO)}: cableado físico de `edge.env`."
        )
    finally:
        controller.stop()


def test_inventario_de_lo_que_estos_guardianes_NO_cubren(settings):
    """Inventario HONESTO: un "todo cerrado" falso es peor que un agujero conocido.

    Lo que SÍ queda medido contra un gate administrativo: el reflejo in-process
    (aquí y en `test_config.py`/`test_supervisor.py`), el traspaso HW→software tras
    reinicio (arriba), la secuencia de tier completa + voceo A-6 + espejo LoRa
    (`test_e2e.py::test_gabinete_retirado_actua_todos_los_canales_instalados_y_vocea`)
    y el comando FIRMADO del quórum de red
    (`test_dispatch.py::test_gabinete_retirado_sigue_obedeciendo_el_comando_firmado_del_quorum`).

    Lo que NO, y por qué:

    - **Canales enrutados a BACnet/IP.** Con `bacnet_channels` no vacío, gas /
      ascensor / puertas salen por la pasarela del sitio y no por el relé local, así
      que no se leen en `gpio`. Un gate administrativo dentro de `BacnetActuator`
      quedaría fuera de todo lo anterior. Se deja abierto porque el default es vacío
      (todo por relé local) y el simulador BACnet no representa una pasarela real;
      lo cubre el gate #4 con hardware. La aserción de abajo lo ancla: si el default
      dejara de ser vacío, este inventario deja de ser cierto y el test lo dice.
    - **La sirena por el jack 3.5 mm (T-1.68).** Su watcher sigue
      `gpio.siren_sounding` cada 50 ms; medirla exige una ventana de polling y hoy
      nace apagada (`audio_siren_enabled=False`). La sirena de RELÉ es la primaria y
      esa sí está medida.
    - **El firmware de los gabinetes secundarios LoRa (ESP32).** El espejo se mide
      hasta el ACK del secundario simulado; lo que el secundario real haga con la
      orden vive fuera de este repo.
    - **El panel LAN.** Silenciar, cerrar alerta o armar una prueba desde el kiosco
      va con PIN y es una acción del operador PRESENTE en el sitio: no es un valor
      empujado por la nube, que es la familia que estos guardianes vigilan.
    """
    assert settings.bacnet_channels == [], (
        "el default dejó de ser 'todo por relé local': con canales por BACnet, los "
        "guardianes de T-2.65 ya no ven gas/ascensor/puertas y este inventario "
        "miente. Extiende la medición al actuador BACnet antes de cambiarlo."
    )
    assert settings.audio_siren_enabled is False, (
        "la sirena por jack ya nace encendida: pasa a ser un canal de protección "
        "vivo y sin red — mídela contra el gate administrativo o documenta por qué no"
    )
