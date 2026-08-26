"""E2E — sismo simulado → actuación autónoma COMPLETA sin nube (cierra la Fase E)."""

from __future__ import annotations

import warnings
from datetime import UTC, datetime

from simulators.quake import quake_packets, quake_window
from simulators.rs4d import RS4DSimulator
from simulators.wr1 import WR1Simulator
from takab_edge.contracts import ActuatorChannel, Tier
from takab_edge.evidence import FakeEvidenceUploader, collect_evidence
from takab_edge.supervisor import EVENTS_TOPIC, FEATURES_TOPIC
from takab_edge.telemetry import FEATURES_BATCH_TOPIC

FULL_SEQUENCE = (
    ActuatorChannel.SIREN,
    ActuatorChannel.STROBE,
    ActuatorChannel.GAS_VALVE,
    ActuatorChannel.ELEVATOR,
    ActuatorChannel.DOOR_RETAINER,
)
QUAKE_START = datetime(2026, 7, 6, 12, 0, 0, tzinfo=UTC)


def _feed_quake(supervisor, start: datetime = QUAKE_START) -> datetime:
    sim = RS4DSimulator(station=supervisor.settings.station)
    for packet in quake_packets(sim, start):
        supervisor.seedlink.feed(packet)
    return start


def test_instrumental_quake_visual_only_no_actuation(supervisor):
    # [T-2.32 · REESCRITURA DELIBERADA del contrato de T-1.14, política ratificada
    # 2026-08-03] Una sola estación moviéndose NO activa nada: la detección
    # instrumental local es SOLO AVISO (online y offline). La actuación viene de
    # SASMEX (intacta) o del comando firmado de quórum ≥3 de la nube.
    assert supervisor.cloud.online is False  # sin nube el aviso sigue siendo solo aviso
    _feed_quake(supervisor)
    # El tier SÍ se eleva (el panel lo muestra como AVISO)…
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    # …pero NINGÚN actuador dispara por umbral local.
    for channel in FULL_SEQUENCE:
        assert supervisor.gpio.relay_state(channel).activated is False, channel
    assert supervisor.gpio.alert_latched is False
    # El evento SÍ viaja a la nube (offline-first): es lo que alimenta el quórum.
    assert supervisor.cloud.queued_by_topic(EVENTS_TOPIC) >= 1
    assert supervisor.cloud.sent == 0
    # El waveform crudo quedó en el buffer (evidencia S3 en evento confirmado, T-1.7/1.11).
    assert len(supervisor.buffer) > 0


def test_instrumental_actuation_optin_restores_sequence(settings):
    # [T-2.32] El opt-in explícito por sitio (config firmada) restaura la
    # actuación instrumental autónoma completa — la de la Fase 1.
    from takab_edge.supervisor import EdgeSupervisor

    optin = settings.model_copy(update={"instrumental_actuation": True})
    sup = EdgeSupervisor(optin, seedlink_source=None)
    sup.start()
    try:
        _feed_quake(sup)
        assert sup.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
        for channel in FULL_SEQUENCE:
            assert sup.gpio.relay_state(channel).activated is True, channel
    finally:
        sup.stop()


def test_quake_event_reflected_in_panel_status(supervisor):
    # [T-2.30, renegociado en T-2.32] El eslabón sim→tier→PANEL: /api/status
    # cuenta la verdad del AVISO — tier elevado, relés SIN activar, sin enclave.
    _feed_quake(supervisor)
    status = supervisor.local_api.status()
    assert status["last_tier"] == "evacuate_or_hold"
    assert status["alert_latched"] is False
    by_channel = {relay["channel"]: relay for relay in status["relays"]}
    for channel in FULL_SEQUENCE:
        assert by_channel[channel.value]["activated"] is False, channel


def test_actuation_latency_within_budget(supervisor):
    _feed_quake(supervisor)
    assert supervisor.rules.last_latency_s is not None
    assert supervisor.rules.last_latency_s < 0.2  # presupuesto §4.3


#: Cota del sondeo de pines del cronómetro punta a punta. Es 5× el presupuesto
#: §4.3 a propósito: no es un plazo que se pueda cumplir por los pelos, es el
#: techo tras el cual se declara que la cadena NO llegó — y el número que salga
#: de ahí revienta el presupuesto por sí solo, con los canales que faltan
#: nombrados. Un `sleep` fijo mediría el sleep; esto mide el hecho.
COTA_SONDEO_S = 0.5

#: [T-2.170] El presupuesto §4.3, con nombre. Sale del blueprint, NO de lo que el
#: CI consiga: un presupuesto que se ajusta a su instrumento deja de serlo.
PRESUPUESTO_S = 0.100

#: Intentos de medición antes de dar veredicto. Existe porque el reloj de pared
#: sobre un runner compartido mide *código + planificación* y el ruido de
#: planificación sólo SUMA — el 2026-08-26 puso `main` en rojo con 165.8 ms, y el
#: mismo commit relanzado pasó. El veredicto se da sobre el MEJOR intento, así que
#: esto NO afloja el presupuesto: si el código se degradó, ni el mejor llega.
INTENTOS_DE_MEDICION = 5

#: Lo mismo para la rendición de cuentas de la actuación (los `ActuatorAck`).
#: Va aparte del cronómetro FÍSICO a propósito: el presupuesto §4.3 es el nivel
#: eléctrico del relé, no el encolado a la nube.
COTA_ACUSES_S = 0.25


def test_latencia_contacto_wr1_a_los_cinco_reles_bajo_presupuesto(supervisor, request):
    """[T-2.70.a·D1.4 · RE-ANCLADO por la auditoría adversarial D1, 2026-08-08]

    EL <100 ms MEDIDO PUNTA A PUNTA, y medido sobre el HECHO FÍSICO.

    Antes de D1.4 esto medía otra cosa: `gpio._dispatch_sasmex` calcula su propia
    latencia ANTES de invocar los callbacks, así que `last_reflex_latency_s` es,
    POR CONSTRUCCIÓN, el coste de dos `_apply()` sobre sirena y estrobo — un
    número que no puede empeorar aunque todo lo que viene después se hunda.

    D1.4 amplió el cronómetro a la cadena entera, pero lo paraba **cuando
    `contacto.drive_low()` RETORNABA**, que es la misma constante con otro
    disfraz: sólo coincide con el final de la cadena mientras la cadena sea
    síncrona y viva en este proceso. MEDIDO por la auditoría sobre una copia del
    árbol: moviendo `supervisor._act_and_publish` → `actuators.execute_sequence`
    a un `threading.Thread` **sin `join`**, el test pasaba 5/5 declarando 0.9 ms
    — el coste del reflejo más el de ARRANCAR un hilo — y el guardarraíl
    anti-teatro no lo veía (0.9 ms ≥ 0.02 ms). D3 mueve exactamente esa
    actuación posterior (gas, ascensor, puertas) al otro lado de un socket, con
    el round-trip en un hilo: el test habría seguido verde declarando «<100 ms
    punta a punta» mientras cronometraba el reflejo más el envío de un mensaje.

    Aquí el reloj **para cuando los CINCO PINES están en su nivel de
    protección**, sondeados con una cota. El número es el instante del hecho
    eléctrico, no la duración de una llamada, así que sigue significando lo mismo
    el día que la actuación posterior cruce un hilo, un socket o una red — y si
    esa travesía se hunde, el número SUBE, que es justo lo que un presupuesto
    tiene que poder hacer.

    Cadena cronometrada, completa y real:

        flanco del contacto seco WR-1  (pin BCM, `drive_low()`)
          → `when_pressed` → `_dispatch_sasmex` → reflejo sirena+estrobo
          → callbacks del supervisor → `rules.evaluate_sasmex`
          → `actuators.execute_sequence` → `RelayActuator` → `gpio.set_relay`
          → gas, ascensor y retenedores de puerta

    El veredicto se lee en los CINCO PINES, no en la contabilidad interna: lo que
    salva vidas es el nivel eléctrico del relé, y cada canal se comprueba contra
    la polaridad que le toca por su modo fail-safe (gas y puertas PROTEGEN
    de-energizándose; sirena, estrobo y ascensor energizándose).

    Y la última aserción cierra la otra mitad del hilo suelto, que un cronómetro
    honesto NO puede ver: una actuación disparada y olvidada llega a los pines
    igual (medido: en ~1 ms), pero no devuelve `ActuatorAck` a nadie — así que
    `_act_and_publish` se queda sin saber si algún canal falló, la nube sin
    acuse, y el operador con una latencia preciosa de una actuación que nadie
    comprobó. Actuar a ciegas rápido no es actuar medido.
    """
    from time import perf_counter, sleep

    from gpiozero import Device
    from takab_edge.gpio import active_energized, normal_energized
    from takab_edge.supervisor import ACKS_TOPIC

    s = supervisor.settings
    pines = {
        ActuatorChannel.SIREN: Device.pin_factory.pin(s.pins.relay_siren),
        ActuatorChannel.STROBE: Device.pin_factory.pin(s.pins.relay_strobe),
        ActuatorChannel.GAS_VALVE: Device.pin_factory.pin(s.pins.relay_gas_valve),
        ActuatorChannel.ELEVATOR: Device.pin_factory.pin(s.pins.relay_elevator),
        ActuatorChannel.DOOR_RETAINER: Device.pin_factory.pin(s.pins.relay_door_retainer),
    }

    def sin_proteger() -> list[str]:
        """Canales que TODAVÍA no están en su nivel de protección, por polaridad."""
        return [
            canal.value
            for canal, pin in pines.items()
            if pin.state is not active_energized(s.failsafe[canal])
        ]

    contacto = Device.pin_factory.pin(s.pins.wr1_contact)

    # [T-2.170] La medición se repite y el veredicto se da sobre el MEJOR intento.
    # No es tolerancia al presupuesto —sigue en 100 ms y no se mueve—: es tolerancia
    # al INSTRUMENTO. El reloj de pared sobre un runner compartido mide *código +
    # planificación*, y el ruido de planificación sólo SUMA; por eso una única
    # medición alta no distingue «el código se degradó» de «el runner estaba
    # ocupado», y la mejor de N sí: si el código se degradó, ni la mejor llega.
    #
    # Lo caro de esto sería medir sobre un gabinete que YA estaba protegido y
    # cantar 0 ms. Lo impide la premisa, que se re-comprueba en cada intento: si el
    # rearme no devolvió los cinco relés a reposo, el test falla ahí y no mide.
    intentos: list[float] = []
    transcurrido = despues_del_retorno = 0.0
    for _ in range(INTENTOS_DE_MEDICION):
        for canal, pin in pines.items():
            assert pin.state is normal_energized(s.failsafe[canal]), (
                f"premisa rota antes del intento {len(intentos) + 1}: {canal.value} no está "
                "en su nivel de reposo. Medir desde aquí daría una latencia falsamente baja."
            )
        inicio = perf_counter()
        contacto.drive_low()  # WR-1: contacto seco CERRADO = alerta SASMEX
        retorno = perf_counter()  # …y esto es SÓLO cuando la llamada volvió
        # El reloj de verdad: se para cuando los CINCO pines llegaron, no cuando la
        # llamada volvió. `sleep(0)` cede el GIL en cada vuelta a propósito: una
        # implementación que actúe desde otro hilo tiene que quedar MEDIDA, no
        # penalizada por un sondeo que la deja sin intérprete.
        faltan = sin_proteger()
        while faltan and perf_counter() - inicio < COTA_SONDEO_S:
            sleep(0)
            faltan = sin_proteger()
        transcurrido = perf_counter() - inicio
        despues_del_retorno = transcurrido - (retorno - inicio)
        intentos.append(transcurrido)

        assert not faltan, (
            f"{COTA_SONDEO_S * 1000:.0f} ms después del flanco del WR-1 estos canales "
            f"seguían SIN protección: {faltan}. La cadena punta a punta está rota o "
            "quedó colgada en algo que nadie espera; el número de latencia no "
            "significaría nada."
        )
        if transcurrido < PRESUPUESTO_S:
            break
        # Rearme por el camino que `test_manual_reset_closes_alert_end_to_end` ya
        # acredita: abrir el contacto ANTES de cerrar la alerta (con el contacto aún
        # cerrado, el sembrado del contacto sostenido volvería a enclavar en el acto).
        contacto.drive_high()
        supervisor.local_api.reset_alert()

    # La serie se publica SIEMPRE, también en verde (ver `pytest_terminal_summary`):
    # sin ella, una degradación gradual —de 5 ms a 80 ms— no se ve hasta que cruza el
    # umbral de golpe, y entonces parece repentina.
    request.config._latencias_camino_de_vida = {
        "serie": list(intentos),
        "presupuesto_s": PRESUPUESTO_S,
    }
    if len(intentos) > 1:
        # Que hiciera falta reintentar es un dato SOBRE EL INSTRUMENTO, y callarlo es
        # cómo se normaliza el ruido hasta que tapa una degradación de verdad.
        warnings.warn(
            f"[T-2.170] el presupuesto del camino de vida necesitó {len(intentos)} "
            f"intentos: {[f'{t * 1000:.1f} ms' for t in intentos]}. El veredicto es del "
            "mejor, pero un instrumento que pide reintentos merece una mirada.",
            stacklevel=1,
        )

    mejor = min(intentos)
    assert mejor < PRESUPUESTO_S, (
        f"SASMEX→los 5 canales tardó {mejor * 1000:.1f} ms en su MEJOR intento de "
        f"{len(intentos)} (presupuesto §4.3: <{PRESUPUESTO_S * 1000:.0f} ms). Serie "
        f"completa: {[f'{t * 1000:.1f} ms' for t in intentos]}. Que ni el mejor llegue "
        "descarta el ruido del runner: esto es la cadena, no el planificador. Del "
        f"último intento, {despues_del_retorno * 1000:.1f} ms ocurrieron DESPUÉS de que "
        "`drive_low()` retornara. Esto es el camino de vida completo medido en los "
        "pines, no sólo el reflejo ni la duración de una llamada.\n"
        "NO subas el presupuesto para arreglar esto: el número sale de `blueprint §4.3`, "
        "no de lo que el CI consiga."
    )
    # Guardarraíl anti-teatro: lo medido aquí tiene que CONTENER al reflejo
    # in-process. Si algún día este número fuera menor que aquél, es que se está
    # cronometrando otra cosa (o que el reflejo dejó de estar dentro).
    assert supervisor.gpio.last_reflex_latency_s is not None
    assert transcurrido >= supervisor.gpio.last_reflex_latency_s, (
        f"punta a punta ({transcurrido * 1000:.3f} ms) salió MENOR que el reflejo "
        f"solo ({supervisor.gpio.last_reflex_latency_s * 1000:.3f} ms): el "
        "cronómetro no está midiendo la cadena que dice medir"
    )
    # La otra mitad: la cadena RINDIÓ CUENTAS de los cinco canales. Un
    # fire-and-forget llega a los pines igual de rápido y se lleva por delante
    # los `ActuatorAck` — la detección de fallo de actuación (`failed`) y el
    # acuse a la nube. Fuera del cronómetro: encolar acuses no es §4.3.
    #
    # Son 5 POR INTENTO, medido: el cierre de alerta del rearme libera los relés
    # sin encolar acuses propios. Si algún día los encolara, este número lo dice.
    esperados = len(pines) * len(intentos)
    limite = perf_counter() + COTA_ACUSES_S
    while supervisor.cloud.queued_by_topic(ACKS_TOPIC) < esperados and perf_counter() < limite:
        sleep(0)
    assert supervisor.cloud.queued_by_topic(ACKS_TOPIC) == esperados, (
        f"los 5 pines llegaron a protección en {mejor * 1000:.1f} ms, pero "
        f"la actuación sólo rindió {supervisor.cloud.queued_by_topic(ACKS_TOPIC)} "
        f"de {esperados} `ActuatorAck` ({len(pines)} por cada uno de los "
        f"{len(intentos)} intentos). Una actuación disparada y olvidada mide "
        "una latencia preciosa y deja a `_act_and_publish` sin saber si algún "
        "canal falló y a la nube sin acuse: el número de arriba estaría "
        "cronometrando una cadena que nadie comprobó."
    )


def test_sasmex_reflex_and_sequence_cloud_off(supervisor):
    assert supervisor.cloud.online is False
    WR1Simulator(supervisor.gpio).alert()
    assert supervisor.gpio.siren_sounding is True  # reflejo local inmediato (sin nube)
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    assert supervisor.cloud.queued_by_topic(EVENTS_TOPIC) == 1  # UN evento (T-1.17: por topic)


def test_no_duplicate_event_explosion_within_episode(supervisor):
    _feed_quake(supervisor)
    # Todo el sismo es UN episodio: los eventos se deduplican por (event_id, tier), así que
    # no hay explosión de duplicados aunque lluevan paquetes (idempotencia, regla de oro 3).
    assert supervisor.cloud.queued_by_topic(EVENTS_TOPIC) <= 3  # a lo sumo watch/restr/evacuate


def test_evidence_window_extractable_after_quake(supervisor):
    start = _feed_quake(supervisor)
    obj = collect_evidence(
        supervisor.buffer, FakeEvidenceUploader(), "quake-1", *quake_window(start)
    )
    assert obj is not None
    assert obj.size_bytes > 0
    assert obj.sha256


def test_manual_reset_closes_alert_end_to_end(supervisor):
    # [T-2.26] SASMEX real → protección completa → CERRAR ALERTA libera TODO
    # (relés + tier + latch); un SASMEX NUEVO re-enclava (latch monótono intacto).
    WR1Simulator(supervisor.gpio).alert()
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
    for channel in FULL_SEQUENCE:
        assert supervisor.gpio.relay_state(channel).activated is True, channel

    supervisor.local_api.reset_alert()
    status = supervisor.local_api.status()
    assert status["last_tier"] == "normal"
    assert status["alert_latched"] is False
    for channel in FULL_SEQUENCE:
        assert supervisor.gpio.relay_state(channel).activated is False, channel

    WR1Simulator(supervisor.gpio).alert()  # alerta NUEVA tras el cierre
    assert supervisor.gpio.alert_latched is True
    assert supervisor.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD


def test_quake_sequence_skips_uninstalled_channels(settings):
    # [T-2.31] Sitio sin gas ni ascensores: la secuencia de tier comanda SOLO lo
    # instalado; gpio conserva sus 5 relés (hardware intocado) pero los canales
    # ausentes jamás se activan. [T-2.32] Con opt-in instrumental explícito: el
    # filtro de equipamiento se prueba en la ruta que SÍ actúa.
    from takab_edge.config import EquipmentProfile
    from takab_edge.supervisor import EdgeSupervisor

    site = settings.model_copy(
        update={
            "equipment": EquipmentProfile(gas_valve=False, elevator=False),
            "instrumental_actuation": True,
        }
    )
    sup = EdgeSupervisor(site, seedlink_source=None)
    sup.start()
    try:
        _feed_quake(sup)
        assert sup.rules.last_decision.tier is Tier.EVACUATE_OR_HOLD
        for channel in (
            ActuatorChannel.SIREN,
            ActuatorChannel.STROBE,
            ActuatorChannel.DOOR_RETAINER,
        ):
            assert sup.gpio.relay_state(channel).activated is True, channel
        for channel in (ActuatorChannel.GAS_VALVE, ActuatorChannel.ELEVATOR):
            assert sup.gpio.relay_state(channel).activated is False, channel
        assert len(sup.gpio.relay_states()) == 5  # el hardware sigue completo
    finally:
        sup.stop()


def test_sasmex_propagates_to_lora_secondaries_and_reset_clears(settings):
    # [T-2.33] Los secundarios son ESPEJOS de la actuación real: SASMEX ⇒
    # ALARM_ACT firmada (sirena+estrobo remotos) hasta ACK; CERRAR ALERTA ⇒
    # ALARM_CLEAR. La detección instrumental (solo aviso, T-2.32) NO propaga.
    import time as _time

    from simulators.lora import FakeSecondaryCabinet, SimulatedLoraTransport
    from takab_edge.config import LoraConfig, SecondaryCabinet
    from takab_edge.supervisor import EdgeSupervisor

    site_key = b"clave-lora-de-sitio-0123456789ab"
    transport = SimulatedLoraTransport()
    cab = transport.attach(FakeSecondaryCabinet(site_key, 258))
    lora_settings = settings.model_copy(
        update={
            "lora": LoraConfig(
                enabled=True,
                alarm_retry_s=0.05,
                secondaries=[SecondaryCabinet(id=258, name="AZOTEA")],
            )
        }
    )
    sup = EdgeSupervisor(
        lora_settings, seedlink_source=None, lora_transport=transport, lora_site_key=site_key
    )
    sup.start()
    try:
        _feed_quake(sup)  # instrumental = solo aviso ⇒ nada viaja a secundarios
        _time.sleep(0.2)
        assert cab.alarm_active is False

        WR1Simulator(sup.gpio).alert()  # SASMEX real ⇒ espejo remoto
        deadline = _time.monotonic() + 3.0
        while _time.monotonic() < deadline and not cab.alarm_active:
            _time.sleep(0.01)
        assert cab.alarm_active is True
        row = sup.local_api.status()["lora"]["secondaries"][0]
        assert row["acked"] is True

        sup.local_api.reset_alert()  # CERRAR ALERTA libera también a distancia
        deadline = _time.monotonic() + 3.0
        while _time.monotonic() < deadline and cab.alarm_active:
            _time.sleep(0.01)
        assert cab.alarm_active is False
    finally:
        sup.stop()


def test_load_many_noise_packets_no_spurious_alert(supervisor):
    sim = RS4DSimulator(station=supervisor.settings.station)
    stream = sim.stream(channel="EHZ")
    for _ in range(300):  # carga: 300 paquetes de ruido de fondo
        supervisor.seedlink.feed(next(stream))
    # El ruido de fondo NO dispara alertas espurias; el buffer los guardó todos.
    assert supervisor.rules.last_decision.tier is Tier.NORMAL
    assert len(supervisor.buffer) >= 300
    assert supervisor.cloud.queued_by_topic(EVENTS_TOPIC) == 0  # sin eventos que encolar
    # T-1.56: en tier normal la telemetría fluye BATCHEADA — 300 features son
    # unos pocos lotes encolados + el resto acumulado en el batcher, no 300 publishes.
    assert supervisor.cloud.queued_by_topic(FEATURES_TOPIC) == 0
    batch_max = supervisor.settings.cloud_features_batch_max
    queued_batches = supervisor.cloud.queued_by_topic(FEATURES_BATCH_TOPIC)
    assert queued_batches >= 300 // batch_max
    assert queued_batches * batch_max + supervisor.telemetry.pending >= 300


# ---------------------------------------------------------------------------
# [T-2.65 · REGLA DE ORO 1] La baja administrativa no desarma NADA
# ---------------------------------------------------------------------------


def test_gabinete_retirado_actua_todos_los_canales_instalados_y_vocea(settings, tmp_path):
    """El criterio 4 de T-2.65, extendido a los canales que el reflejo NO cubre.

    El reflejo in-process solo toca DOS de los cinco canales (sirena y estrobo) y
    ya tiene sus dos guardianes (`test_config.py::…sigue_actuando_la_sirena…` sobre
    un `GpioController` suelto y `test_supervisor.py::…jamas_se_cablea_al_reflejo`
    sobre el cableado real). **Gas, ascensor, retenedores de puerta, voceo A-6 y
    espejo LoRa cuelgan de `EdgeSupervisor._act_and_publish`**, que sí lee la config
    VIVA que publica la nube (`self.config.current()`), y ahí no había un solo test
    que impidiera un gate administrativo. Medido antes de escribir esto: dos líneas
    (`if live.is_retired: return`) dejan mudo todo eso con la suite del edge en
    «657 passed, 5 skipped» — verde, y un edificio sin gas cerrado ni ascensores en
    planta porque alguien hizo clic en «retirar» en la consola.

    **EL MATIZ, que es la parte difícil**: en `_act_and_publish` SÍ existe —y debe
    seguir existiendo— una arista desde la config de la nube hasta la actuación: el
    filtro de equipamiento de T-2.31 (`live.equipment.has(c.channel)`). Así que el
    invariante NO es «ninguna config puede tocar estos canales» (eso rompería
    T-2.31), sino uno más fino, y este test lo separa MIDIENDO las dos cosas a la vez
    en el mismo escenario:

    * **equipamiento = hecho FÍSICO.** Este sitio no tiene relé de gas cableado;
      mandarle la orden no protegería a nadie. GAS **no** se energiza.
    * **estado administrativo = acto de INVENTARIO.** Alguien dio de baja el
      gabinete en la consola; el edificio sigue en pie y con gente dentro. Sirena,
      estrobo, ascensor y puertas se energizan IGUAL, el voceo suena y los
      secundarios LoRa replican.

    Un test que confundiera ambas cosas o no cazaría nada (con el equipamiento
    completo, un gate administrativo sería indistinguible del filtro legítimo) o
    rompería T-2.31 (si exigiera que el gas actuara). Por eso el sitio está retirado
    **y** sin gas a la vez.

    Hostil por los dos extremos, como sus hermanos: arranca retirado (así queda tras
    un reinicio, con la caché firmada de T-2.34 y `TAKAB_EDGE_CLOUD_ADMIN_STATE` en
    `edge.env`) y la nube aplica encima otro sobre retirado — este además con
    umbrales absurdos de 99 g, para que el filtro de equipamiento copiado hacia los
    umbrales («si el sitio no dispararía por instrumentación, no actúes») tampoco
    pase por aquí.
    """
    import time as _time

    from simulators.lora import FakeSecondaryCabinet, SimulatedLoraTransport
    from takab_edge.config import EquipmentProfile, LoraConfig, SecondaryCabinet, ThresholdBand
    from takab_edge.supervisor import EdgeSupervisor

    sismo = tmp_path / "sismo.wav"
    sismo.write_bytes(b"RIFF-sismo-fake-wav")
    simulacro = tmp_path / "simulacro.wav"
    simulacro.write_bytes(b"RIFF-simulacro-fake-wav")

    site_key = b"clave-lora-de-sitio-0123456789ab"
    transport = SimulatedLoraTransport()
    secundario = transport.attach(FakeSecondaryCabinet(site_key, 258))

    retirado = settings.model_copy(
        update={
            "cloud_admin_state": "retired",
            # Sitio SIN gas cableado: el filtro de T-2.31 tiene que seguir vivo.
            "equipment": EquipmentProfile(gas_valve=False),
            # Voceo A-6 encendido con assets propios: sin esto el canal no es medible.
            "audio_enabled": True,
            "audio_sismo_path": str(sismo),
            "audio_simulacro_path": str(simulacro),
            "lora": LoraConfig(
                enabled=True,
                alarm_retry_s=0.05,
                secondaries=[SecondaryCabinet(id=258, name="AZOTEA")],
            ),
            # Caché propia: el default apunta a /var/lib/takab (gabinete real).
            "config_cache_path": str(tmp_path / "config-cache.json"),
        }
    )
    sup = EdgeSupervisor(
        retirado, seedlink_source=None, lora_transport=transport, lora_site_key=site_key
    )
    sup.start()
    try:
        # Guardarraíles del propio test: si alguien "simplifica" el escenario y deja
        # de ser hostil, esto cae AQUÍ en vez de seguir pasando sin proteger nada.
        assert sup.gpio.settings.is_retired is True
        assert sup.audio.enabled is True

        doc = retirado.model_copy(
            update={"thresholds": ThresholdBand(pga_trip_g=99.0, pgv_trip_cms=99.0)}
        )
        raw = doc.model_dump_json().encode()
        version = sup.config.version + 1
        sup.config.apply_signed_update(raw, sup.security.sign_config(raw, version), version)
        live = sup.config.current()
        assert live.is_retired is True
        assert live.equipment.gas_valve is False
        assert live.thresholds.pga_trip_g == 99.0

        WR1Simulator(sup.gpio).alert()  # SASMEX real sobre un gabinete dado de baja

        instalados = (
            ActuatorChannel.SIREN,
            ActuatorChannel.STROBE,
            ActuatorChannel.ELEVATOR,
            ActuatorChannel.DOOR_RETAINER,
        )
        mudos = [c.value for c in instalados if not sup.gpio.is_activated(c)]
        assert not mudos, (
            f"el gabinete RETIRADO dejó de proteger estos canales: {mudos}. "
            "La baja en la nube es un acto de INVENTARIO, no una orden de desarme: "
            "el edificio sigue en pie y con gente dentro (reglas de oro 1 y 2). "
            "Si lo que se quería era filtrar hardware ausente, eso es `equipment` "
            "(T-2.31), que es un hecho físico y se comprueba aquí mismo."
        )
        # …y el filtro de equipamiento de T-2.31 SIGUE VIVO: un canal no instalado
        # no se energiza. Esta es la mitad del test que impide "ignorar toda la
        # config" como forma barata de pasar la mitad de arriba.
        assert sup.gpio.is_activated(ActuatorChannel.GAS_VALVE) is False, (
            "se energizó el relé de GAS en un sitio que no lo tiene instalado: el "
            "filtro de equipamiento de T-2.31 se perdió al blindar el estado "
            "administrativo. Son cosas distintas: el equipamiento es físico "
            "(no existe el relé), la baja administrativa es de inventario."
        )
        acked = {ack.channel for ack in sup.actuators.last_acks}
        assert acked == set(instalados), (
            f"la secuencia de tier ACKeó {sorted(c.value for c in acked)}; "
            f"se esperaba exactamente {sorted(c.value for c in instalados)}"
        )

        # Voceo A-6: se MIDE en el backend (qué asset exacto salió), no se afirma.
        assert sup.audio.sounding is True, (
            "el voceo «protéjase» quedó mudo en un gabinete retirado: es el mismo "
            "acto de inventario, y el mensaje hablado es lo que la gente entiende "
            "cuando la sirena suena"
        )
        assert sup.audio._backend.plays == [str(sismo)]

        # Espejo LoRa (T-2.33): los secundarios son protección LOCAL a distancia.
        deadline = _time.monotonic() + 3.0
        while _time.monotonic() < deadline and not secundario.alarm_active:
            _time.sleep(0.01)
        assert secundario.alarm_active is True, (
            "el gabinete secundario no replicó la alarma: un gabinete retirado dejó "
            "sin sirena a la zona que cubre el espejo LoRa"
        )
    finally:
        sup.stop()
