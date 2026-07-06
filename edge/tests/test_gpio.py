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
