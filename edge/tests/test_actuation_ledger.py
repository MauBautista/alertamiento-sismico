"""[T-2.86.a · hueco `RO-4.e`] La bitácora LOCAL de actuación: actor y causa.

El caso exacto para el que existe el gabinete —**regla de oro 2, el edge opera sin
nube**— era precisamente el que no dejaba constancia. `ActuatorAck` lleva canal,
acción, `event_id`, éxito y latencia, y **no lleva actor**; el `audit_log` vivía
sólo en la nube. Si el gas se cerraba durante un corte de internet, después nadie
podía decir **quién lo ordenó ni con qué causa**.

Es la mitad no construida de la **regla de oro 4**: «el proceso GPIO es mínimo *y
auditable*».

Lo que estos tests fijan, y por qué cada uno:

1. **La causa no se inventa: se DERIVA.** Los orígenes de una actuación son dos
   conjuntos ya cerrados en el código —`AlertSource` (lo que decide `rules`) y
   `GPIO_ACTIONS` (la lista blanca de la costura, o sea lo que puede pedir un
   operador)— más los dos orígenes que viajan DENTRO de un comando firmado. Un
   origen nuevo entra en la comprobación **solo**: añadir un miembro a cualquiera
   de esos conjuntos sin declarar su causa pone el build en rojo.
2. **Sobrevive al reinicio, y no cae en la trampa de `T-2.67.b`.** Aquel spool se
   evaporaba porque `_default_pending_dir()` cae a un `mkdtemp` NUEVO por arranque
   cuando falta `cloud_spool_dir`. Aquí el directorio es DERIVADO y estable, y
   cuando no puede ser durable de verdad **se declara**, no se calla.
3. **No tumba el camino de vida.** Disco lleno, directorio ilegible o sink roto: la
   sirena suena igual. Pero «no tumbar» no es «callar» — el fallo se cuenta y se
   declara.
4. **Sube sin duplicarse (regla de oro 3).** Marca de agua durable: lo ya subido no
   se vuelve a subir, ni siquiera después de reiniciar.
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime

import pytest
from simulators.wr1 import WR1Simulator
from takab_edge.audit import (
    ALERT_SOURCES_SIN_CAUSA,
    CAUSE_BY_ALERT_SOURCE,
    CAUSE_BY_COMMAND_ORIGIN,
    CAUSE_BY_GPIO_ACTION,
    GPIO_ACTIONS_SIN_CAUSA,
    ActuationLedger,
)
from takab_edge.config import EdgeSettings
from takab_edge.contracts import (
    ActuationCause,
    ActuatorAction,
    ActuatorChannel,
    AlertSource,
    Tier,
    TierDecision,
)
from takab_edge.gpio_link import GPIO_ACTIONS
from takab_edge.supervisor import EdgeSupervisor

NOW = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)


def _ledger(tmp_path, **kwargs) -> ActuationLedger:
    settings = EdgeSettings(dev_mode=True, cloud_spool_dir=str(tmp_path / "spool"))
    return ActuationLedger(settings, **kwargs)


def _anotar(ledger: ActuationLedger, **kwargs) -> None:
    base = {
        "cause": ActuationCause.SASMEX,
        "actor": "wr-1",
        "channel": ActuatorChannel.GAS_VALVE,
        "action": ActuatorAction.ACTIVATE,
        "success": True,
        "detail": "relé",
        "event_id": "evt-1",
    }
    ledger.record(**{**base, **kwargs})


# ---------------------------------------------------------------------------
# 1 · El conjunto de causas es DERIVADO, no una lista escrita a mano
# ---------------------------------------------------------------------------


def test_toda_accion_de_la_costura_declara_su_causa():
    """`GPIO_ACTIONS` es la lista BLANCA de lo que un operador puede pedirle al
    dueño de los pines. Es el censo autoritativo de los orígenes «humanos» de una
    actuación, y ya existe en el código: derivar de él es lo que hace que una
    acción nueva —la que sea— no pueda entrar sin declarar con qué causa queda
    escrita en la bitácora.
    """
    assert set(CAUSE_BY_GPIO_ACTION) == set(GPIO_ACTIONS), (
        "hay acciones de la costura sin causa declarada (o al revés): "
        f"{sorted(set(CAUSE_BY_GPIO_ACTION) ^ set(GPIO_ACTIONS))}. Toda acción que "
        "pueda mover un relé tiene que decir con qué causa se escribe en la "
        "bitácora — si no, un origen nuevo actúa sin dejar constancia de por qué."
    )
    # …y el mismo hecho, calculado por el módulo, para que el hueco también se vea
    # en el gabinete (log al importar) y no sólo aquí.
    assert GPIO_ACTIONS_SIN_CAUSA == frozenset()
    assert ALERT_SOURCES_SIN_CAUSA == frozenset()


def test_todo_origen_de_alerta_declara_su_causa():
    """`AlertSource` es el otro conjunto cerrado: lo que hace que `rules` ordene
    una secuencia de tier. Un cuarto origen (p.ej. el quórum comandado localmente)
    pondría esto en rojo hasta que alguien decida cómo se audita."""
    assert set(CAUSE_BY_ALERT_SOURCE) == set(AlertSource), (
        "hay orígenes de alerta sin causa declarada: "
        f"{sorted(str(x) for x in set(CAUSE_BY_ALERT_SOURCE) ^ set(AlertSource))}"
    )


def test_el_comando_firmado_distingue_quorum_de_operador():
    """Los dos orígenes que viajan DENTRO de la firma (`origin`) son causas
    distintas para un perito: «la red de estaciones lo confirmó» no es «alguien
    en la consola lo pulsó». `None` = comando firmado sin `origin` declarado."""
    assert CAUSE_BY_COMMAND_ORIGIN["quorum"] is ActuationCause.NETWORK_QUORUM
    assert CAUSE_BY_COMMAND_ORIGIN[None] is ActuationCause.CLOUD_COMMAND


def test_ninguna_causa_declarada_es_la_de_relleno():
    """`UNDECLARED` existe para que un origen que nadie mapeó quede ESCRITO como
    tal y grite, jamás para ser el valor normal de nada."""
    declaradas = (
        set(CAUSE_BY_GPIO_ACTION.values())
        | set(CAUSE_BY_ALERT_SOURCE.values())
        | set(CAUSE_BY_COMMAND_ORIGIN.values())
    )
    assert ActuationCause.UNDECLARED not in declaradas


# ---------------------------------------------------------------------------
# 2 · La constancia local: existe, nombra la causa, y sobrevive al reinicio
# ---------------------------------------------------------------------------


def test_una_actuacion_con_la_nube_caida_deja_constancia_que_nombra_la_causa(settings, tmp_path):
    """EL CRITERIO 3 DE LA FICHA, medido de punta a punta.

    Gabinete real (supervisor cableado), **sin enlace** (`cloud.online is False`),
    WR-1 real simulado. Después: el registro existe EN DISCO, nombra la causa
    (`sasmex`), nombra al actor y nombra el canal del gas — que es literalmente lo
    que pediría un perito o un seguro.
    """
    sup = EdgeSupervisor(
        settings.model_copy(update={"cloud_spool_dir": str(tmp_path / "spool")}),
        seedlink_source=None,
    )
    sup.start()
    try:
        assert sup.cloud.online is False, "este test mide el caso SIN nube"
        WR1Simulator(sup.gpio).alert()

        registros = sup.ledger.read_all()
        assert registros, (
            "el gas se cerró con el enlace caído y NO quedó constancia local: "
            "es exactamente el hueco RO-4.e"
        )
        gas = [r for r in registros if r["channel"] == ActuatorChannel.GAS_VALVE.value]
        assert gas, f"no hay fila del gas; canales registrados: {[r['channel'] for r in registros]}"
        fila = gas[-1]
        assert fila["cause"] == ActuationCause.SASMEX.value
        assert fila["actor"], "una fila sin actor no responde «quién lo ordenó»"
        assert fila["action"] == ActuatorAction.ACTIVATE.value
        assert fila["success"] is True
        assert fila["online"] is False, "la fila tiene que decir que no había enlace"
        assert fila["gateway_id"] == sup.settings.gateway_id
        # …y está EN DISCO, no sólo en memoria: eso es lo que sobrevive al corte.
        en_disco = list(sup.ledger.directory.glob("*.ndjson"))
        assert en_disco, "la constancia vive sólo en RAM: un corte de energía se la lleva"
        crudo = en_disco[0].read_text("utf-8")
        assert ActuationCause.SASMEX.value in crudo
    finally:
        sup.stop()


def test_el_registro_sobrevive_al_reinicio_del_proceso(tmp_path):
    """Un segundo `ActuationLedger` con la MISMA config lee lo que escribió el
    primero. Sin esto la bitácora es una lista en RAM con nombre de bitácora."""
    primero = _ledger(tmp_path)
    _anotar(primero, event_id="evt-antes-del-reinicio")

    segundo = _ledger(tmp_path)  # «reinicio»: proceso nuevo, misma config
    ids = [r["event_id"] for r in segundo.read_all()]
    assert "evt-antes-del-reinicio" in ids
    assert segundo.directory == primero.directory


def test_sin_cloud_spool_dir_el_directorio_sigue_siendo_EL_MISMO(tmp_path, monkeypatch):
    """[trampa `T-2.67.b`] El spool de evidencia se pierde al reiniciar porque
    `_default_pending_dir()` cae a un **`mkdtemp` nuevo por arranque** cuando falta
    `cloud_spool_dir` —que es el estado del Pi real, porque `provision_gateway.sh`
    no escribe esa clave—. Un registro que repitiera ese error sería como no
    tenerlo.

    Aquí el default es DERIVADO del gabinete (mismo patrón que `gpio_lock_file`):
    dos arranques consecutivos resuelven al MISMO directorio, así que el registro
    sobrevive al reinicio del proceso incluso sin configurar nada. Lo que NO puede
    prometer sin `cloud_spool_dir` es sobrevivir a un reinicio del SISTEMA (el
    directorio temporal se limpia al arrancar), y eso se DECLARA en vez de callarse.
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    sin_spool = EdgeSettings(dev_mode=True, cloud_spool_dir="")

    uno = ActuationLedger(sin_spool)
    dos = ActuationLedger(sin_spool)
    assert uno.directory == dos.directory, (
        "el directorio del registro cambia entre arranques: es la trampa de "
        f"T-2.67.b otra vez ({uno.directory} != {dos.directory})"
    )
    _anotar(uno, event_id="evt-sin-spool")
    assert "evt-sin-spool" in [r["event_id"] for r in ActuationLedger(sin_spool).read_all()]

    # …y la mitad honesta: sin `cloud_spool_dir` NO se promete durabilidad.
    assert uno.state()["durable"] is False
    assert "cloud_spool_dir" in uno.state()["durable_reason"]
    con_spool = ActuationLedger(EdgeSettings(dev_mode=True, cloud_spool_dir=str(tmp_path / "s")))
    assert con_spool.state()["durable"] is True


def test_dos_gabinetes_distintos_no_comparten_registro(tmp_path, monkeypatch):
    """Agravante fichado en `T-2.67.b`: `/tmp/backfill-pending` es COMPARTIDO
    entre procesos y corridas. Una bitácora compartida entre gabinetes mezclaría
    las actuaciones de dos edificios en un mismo archivo."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    uno = ActuationLedger(EdgeSettings(dev_mode=True, gateway_id="gw-a", cloud_spool_dir=""))
    dos = ActuationLedger(EdgeSettings(dev_mode=True, gateway_id="gw-b", cloud_spool_dir=""))
    assert uno.directory != dos.directory


# ---------------------------------------------------------------------------
# 3 · Jamás tumba el camino de vida — pero tampoco calla
# ---------------------------------------------------------------------------


def test_un_registro_que_no_se_puede_escribir_no_lanza_y_se_declara(tmp_path):
    """Disco lleno / directorio imposible: `record()` NO lanza, cuenta el fallo y
    lo dice. La doctrina es la del registro del cerrojo: informativo a propósito.
    """
    fichero = tmp_path / "soy-un-fichero"
    fichero.write_text("no soy un directorio")
    settings = EdgeSettings(dev_mode=True, cloud_spool_dir=str(fichero / "spool"))

    ledger = ActuationLedger(settings)  # el CONSTRUCTOR tampoco puede lanzar
    _anotar(ledger)  # ni esto

    estado = ledger.state()
    assert estado["write_failures"] == 1
    assert estado["last_error"], "un fallo silencioso es peor que no tener registro"
    assert estado["writable"] is False


def test_con_el_registro_averiado_la_sirena_suena_igual(settings, tmp_path):
    """El invariante de fondo (regla de oro 2 + doctrina del cerrojo): la bitácora
    es informativa. Con su directorio imposible, el WR-1 sigue energizando la
    sirena y cerrando el gas, y el gabinete no se cae."""
    # Se avería SOLO la bitácora (un fichero donde tendría que ir su directorio),
    # dejando el resto del gabinete intacto: eso es lo que hace de este test una
    # medida del aislamiento y no del apocalipsis.
    (tmp_path / "actuation-ledger").write_text("no soy un directorio")
    sup = EdgeSupervisor(
        settings.model_copy(update={"cloud_spool_dir": str(tmp_path / "spool")}),
        seedlink_source=None,
    )
    sup.start()
    try:
        assert sup.ledger.state()["writable"] is False  # la avería está puesta
        WR1Simulator(sup.gpio).alert()
        assert sup.gpio.relay_state(ActuatorChannel.SIREN).energized is True
        assert sup.gpio.relay_state(ActuatorChannel.GAS_VALVE).activated is True
        estado = sup.ledger.state()
        assert estado["write_failures"] >= 1  # …y se DECLARA, no se calla
        assert estado["last_error"]
    finally:
        sup.stop()


# ---------------------------------------------------------------------------
# 4 · Sube al volver el enlace, sin duplicarse (regla de oro 3)
# ---------------------------------------------------------------------------


def test_la_constancia_sube_al_volver_el_enlace_y_no_se_duplica(tmp_path):
    subidos: list[dict] = []
    ledger = _ledger(tmp_path, sink=lambda record: (subidos.append(record), True)[1])

    _anotar(ledger, event_id="evt-a")
    _anotar(ledger, event_id="evt-b")
    assert subidos == [], "la subida ocurre al VOLVER el enlace, no al escribir"

    assert ledger.drain() == 2
    assert [r["event_id"] for r in subidos] == ["evt-a", "evt-b"]
    assert ledger.drain() == 0, "un segundo drenado re-subió lo ya subido"
    assert len(subidos) == 2

    # …y tras un REINICIO tampoco: la marca de agua es durable.
    reiniciado = _ledger(tmp_path, sink=lambda record: (subidos.append(record), True)[1])
    assert reiniciado.drain() == 0
    assert len(subidos) == 2
    # Lo local NO se borra al subir: el perito lo lee meses después.
    assert len(reiniciado.read_all()) == 2


def test_un_sink_que_falla_deja_el_pendiente_pendiente(tmp_path):
    """Sin esto, un enlace a medias «confirmaría» subidas que nadie recibió."""
    ledger = _ledger(tmp_path, sink=lambda record: False)
    _anotar(ledger, event_id="evt-perdido")
    assert ledger.drain() == 0
    assert ledger.state()["pending"] == 1

    recibidos: list[dict] = []
    ledger.sink = lambda record: (recibidos.append(record), True)[1]
    assert ledger.drain() == 1
    assert [r["event_id"] for r in recibidos] == ["evt-perdido"]


def test_un_sink_que_LANZA_no_tumba_el_drenado(tmp_path):
    def _revienta(record):
        raise RuntimeError("el transporte se cayó a mitad")

    ledger = _ledger(tmp_path, sink=_revienta)
    _anotar(ledger)
    assert ledger.drain() == 0  # no propaga
    assert ledger.state()["pending"] == 1


def test_cada_fila_lleva_su_propio_identificador_para_el_dedup_de_la_nube(tmp_path):
    """Regla de oro 3 del lado de la nube: la PK natural con la que hacer
    `ON CONFLICT DO NOTHING`. Dos actuaciones del MISMO evento en el MISMO canal
    (reintento tras fallo) son filas distintas y deben seguir siéndolo."""
    ledger = _ledger(tmp_path)
    _anotar(ledger, event_id="evt-1", success=False)
    _anotar(ledger, event_id="evt-1", success=True)
    filas = ledger.read_all()
    ids = [r["record_id"] for r in filas]
    assert len(set(ids)) == 2, "dos actuaciones distintas colapsaron en un id"
    assert [r["seq"] for r in filas] == [1, 2], "el orden tiene que ser reconstruible"


# ---------------------------------------------------------------------------
# 5 · Los orígenes reales, cada uno con la causa que le toca
# ---------------------------------------------------------------------------


def test_el_umbral_instrumental_con_opt_in_queda_registrado_como_instrumental(settings, tmp_path):
    """Política T-2.32: sin opt-in el umbral es SOLO AVISO (no hay actuación que
    registrar); con `instrumental_actuation` sí actúa, y entonces la causa NO
    puede ser «sasmex» — es el umbral de esta estación sola."""
    s = settings.model_copy(
        update={"cloud_spool_dir": str(tmp_path / "spool"), "instrumental_actuation": True}
    )
    sup = EdgeSupervisor(s, seedlink_source=None)
    sup.start()
    try:
        sup._act_and_publish(
            TierDecision(tier=Tier.EVACUATE_OR_HOLD, source=AlertSource.THRESHOLD), None
        )
        causas = {r["cause"] for r in sup.ledger.read_all()}
        assert causas == {ActuationCause.LOCAL_THRESHOLD.value}, causas
    finally:
        sup.stop()


def test_el_aviso_instrumental_sin_opt_in_no_inventa_una_actuacion(settings, tmp_path):
    """El reverso: la política de T-2.32 dice que no se actúa NADA. Una bitácora
    que escribiera filas ahí estaría afirmando actuaciones que no ocurrieron."""
    sup = EdgeSupervisor(
        settings.model_copy(update={"cloud_spool_dir": str(tmp_path / "spool")}),
        seedlink_source=None,
    )
    sup.start()
    try:
        sup._act_and_publish(
            TierDecision(tier=Tier.EVACUATE_OR_HOLD, source=AlertSource.THRESHOLD), None
        )
        assert sup.ledger.read_all() == []
    finally:
        sup.stop()


def test_la_prueba_local_por_lan_queda_registrada_como_prueba(settings, tmp_path):
    """T-1.67: la prueba local ejercita TODO el gabinete —sirena, gas, puertas—.
    Que no sea una alerta real no la hace invisible: alguien movió los relés de un
    edificio y eso tiene que estar escrito, con su causa de PRUEBA (jamás con la
    de un sismo)."""
    sup = EdgeSupervisor(
        settings.model_copy(update={"cloud_spool_dir": str(tmp_path / "spool")}),
        seedlink_source=None,
    )
    sup.start()
    try:
        sup.local_api.run_actuator_test()
        filas = sup.ledger.read_all()
        assert filas, "la prueba local movió relés y no dejó constancia"
        assert filas[-1]["cause"] == ActuationCause.LAN_ACTUATION_TEST.value
        assert filas[-1]["actor"].startswith("lan")
        assert filas[-1]["cause"] != ActuationCause.SASMEX.value
    finally:
        sup.stop()


def test_el_silencio_y_el_cierre_de_alerta_por_lan_quedan_registrados(settings, tmp_path):
    """Silenciar los audibles y cerrar la alerta enclavada son actuaciones: alguien
    apagó la sirena de un edificio durante un episodio. Es de lo primero que se
    pregunta después."""
    sup = EdgeSupervisor(
        settings.model_copy(update={"cloud_spool_dir": str(tmp_path / "spool")}),
        seedlink_source=None,
    )
    sup.start()
    try:
        WR1Simulator(sup.gpio).alert()
        sup.local_api.silence()
        sup.local_api.reset_alert()
        causas = [r["cause"] for r in sup.ledger.read_all()]
        assert ActuationCause.LAN_SILENCE.value in causas
        assert ActuationCause.LAN_RESET.value in causas
    finally:
        sup.stop()


def test_la_salud_de_la_bitacora_esta_disponible_para_quien_la_pinte(settings, tmp_path):
    """«No tumbar» no es «callar». Como una bitácora averiada NO detiene nada (a
    propósito), hace falta que su estado sea legible desde fuera.

    **`status()` NO la lleva todavía, y es deliberado:** el panel tiene una guarda
    derivada que exige que toda clave de `status()` se RENDERICE, y una tarjeta nueva
    del kiosco no es esta tarea. Mientras tanto el fallo se declara por `log.error`
    y por este método, que es lo que consumirá la tarjeta cuando se haga."""
    (tmp_path / "actuation-ledger").write_text("no soy un directorio")
    sup = EdgeSupervisor(
        settings.model_copy(update={"cloud_spool_dir": str(tmp_path / "spool")}),
        seedlink_source=None,
    )
    sup.start()
    try:
        seccion = sup.local_api.audit_state()
        assert seccion["writable"] is False
        assert seccion["last_error"]
        assert seccion["uploads_enabled"] is False  # la subida está declarada, no oculta
        assert "audit" not in sup.local_api.status(), (
            "la clave entró en status() sin tarjeta que la pinte: el kiosco la "
            "ignoraría en silencio (la clase de defecto de T-2.59)"
        )
    finally:
        sup.stop()


def test_el_comando_firmado_del_quorum_se_registra_con_su_command_id(
    settings, tmp_path, monkeypatch
):
    """El edge NO puede saber qué persona pulsó en la consola —ni debe fingirlo—.
    Lo que sí sabe, y es lo que necesita el perito para cerrar la cadena, es el
    `command_id` firmado: la nube lo une a su operador en `commands`."""
    import takab_edge.dispatch as dispatch_mod
    from takab_edge.security import SecurityManager

    key = b"clave-de-test-ledger"
    monkeypatch.setenv("TAKAB_EDGE_HMAC_KEY", key.decode())
    s = settings.model_copy(
        update={
            "cloud_spool_dir": str(tmp_path / "spool"),
            "command_enabled": True,
        }
    )
    sup = EdgeSupervisor(s, seedlink_source=None)
    sup.start()
    try:
        firmante = SecurityManager(key)
        ahora = datetime.now(UTC)
        payload = {
            "channel": ActuatorChannel.GAS_VALVE.value,
            "action": ActuatorAction.ACTIVATE.value,
            "event_id": "evt-quorum",
            "origin": "quorum",
        }
        cuerpo = dispatch_mod.canonical_payload(payload)
        nonce = "nonce-quorum-0001"
        envelope = {
            "kind": "command",
            "command_id": "cmd-abc-123",
            "nonce": nonce,
            "ts": ahora.isoformat(),
            "payload": payload,
            "sig": firmante.sign(cuerpo, nonce, ahora),
        }
        sup.dispatch.on_command("takab/cmd/x", json.dumps(envelope).encode())

        filas = [r for r in sup.ledger.read_all() if r["event_id"] == "evt-quorum"]
        assert filas, "un comando firmado movió el gas y no dejó constancia local"
        assert filas[-1]["cause"] == ActuationCause.NETWORK_QUORUM.value
        assert "cmd-abc-123" in filas[-1]["actor"]
    finally:
        sup.stop()


def test_una_actuacion_sin_causa_declarada_se_escribe_como_no_declarada(tmp_path):
    """Fail-loud, no fail-silent: si mañana alguien construye un `ActuatorCommand`
    sin declarar causa, la fila existe y dice `undeclared` — que es una pregunta
    para el que revisa, no un hueco invisible."""
    from takab_edge.actuators import ActuatorManager
    from takab_edge.contracts import ActuatorCommand

    class _Rele:
        channels = (ActuatorChannel.GAS_VALVE,)

        def execute(self, command):
            from takab_edge.contracts import ActuatorAck

            return ActuatorAck(
                channel=command.channel,
                action=command.action,
                event_id=command.event_id,
                success=True,
                latency_s=0.0,
                detail="fake",
            )

    ledger = _ledger(tmp_path)
    manager = ActuatorManager(_Rele(), ledger=ledger)
    manager.execute(
        ActuatorCommand(
            channel=ActuatorChannel.GAS_VALVE,
            action=ActuatorAction.ACTIVATE,
            event_id="evt-huerfano",
        )
    )
    filas = ledger.read_all()
    assert [r["cause"] for r in filas] == [ActuationCause.UNDECLARED.value]


# ---------------------------------------------------------------------------
# 6 · El archivo no crece sin límite, y lo que se pierde se declara
# ---------------------------------------------------------------------------


def test_el_registro_rota_y_no_llena_el_disco(tmp_path):
    """El Pi no tiene disco infinito y llenarlo sería tumbar el camino de vida por
    la puerta de atrás. Rota por tamaño; el drenado sigue leyendo lo rotado."""
    subidos: list[dict] = []
    ledger = _ledger(
        tmp_path,
        sink=lambda record: (subidos.append(record), True)[1],
        max_bytes=900,
        keep=3,
    )
    for i in range(40):
        _anotar(ledger, event_id=f"evt-{i:03d}")

    archivos = sorted(p.name for p in ledger.directory.glob("*.ndjson*"))
    assert 1 < len(archivos) <= 3, archivos
    assert ledger.drain() >= 1
    # Lo que la rotación se llevó SIN subir se cuenta y se nombra.
    assert ledger.state()["dropped_unsent"] > 0


def test_una_linea_corrupta_no_impide_leer_el_resto(tmp_path):
    """Un corte de energía a mitad de escritura no puede cegar la bitácora
    entera — mismo criterio que la cuarentena de `DurableSpool`."""
    ledger = _ledger(tmp_path)
    _anotar(ledger, event_id="evt-bueno")
    archivo = next(iter(ledger.directory.glob("*.ndjson")))
    with archivo.open("a", encoding="utf-8") as fh:
        fh.write('{"seq": 2, "cortado a la mit\n')
    _anotar(ledger, event_id="evt-posterior")

    ids = [r["event_id"] for r in ledger.read_all()]
    assert ids == ["evt-bueno", "evt-posterior"]
    assert ledger.state()["unreadable_lines"] == 1


@pytest.mark.parametrize("campo", ["cause", "actor", "channel", "action", "at", "record_id"])
def test_ninguna_fila_puede_salir_sin_los_campos_que_la_hacen_evidencia(tmp_path, campo):
    ledger = _ledger(tmp_path)
    _anotar(ledger)
    fila = ledger.read_all()[0]
    assert fila.get(campo), f"la fila salió sin `{campo}`: no sirve como evidencia"


def test_la_fila_es_json_de_una_sola_linea(tmp_path):
    """NDJSON: una fila por línea. Un `json.dumps` con saltos rompería el
    formato y con él la lectura forense por `grep`/`tail` en el propio gabinete."""
    ledger = _ledger(tmp_path)
    _anotar(ledger)
    _anotar(ledger)
    crudo = next(iter(ledger.directory.glob("*.ndjson"))).read_text("utf-8")
    lineas = [ln for ln in crudo.splitlines() if ln.strip()]
    assert len(lineas) == 2
    for linea in lineas:
        assert json.loads(linea)["cause"] == ActuationCause.SASMEX.value
