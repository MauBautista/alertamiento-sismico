"""CommandDispatcher (T-1.23): comandos/config firmados nube→edge.

Todo se verifica ANTES de tocar actuadores/config (regla de oro 8):
- firma inválida / replay / fuera de ventana / malformado ⇒ ni ejecuta ni ACKea
  (la nube expira el pendiente por TTL);
- verificado con ``command_enabled=false`` (default de fábrica) ⇒ ack rejected;
- config: la aplica ConfigStore (versión monótona; vieja/replay rechazada).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from takab_edge.config import ConfigStore, EdgeSettings
from takab_edge.contracts import ActuatorAck, ActuatorAction, ActuatorChannel, ActuatorCommand
from takab_edge.dispatch import CommandDispatcher, canonical_payload
from takab_edge.security import SecurityManager

KEY = b"clave-de-test-dispatch"
NOW = datetime(2026, 7, 7, 12, 0, 0, tzinfo=UTC)
CMD_TOPIC = "takab/cmd/gw-test"


class _FakeCloud:
    """Registro mínimo de publicaciones (sustituye a CloudConnector)."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def publish(self, topic: str, payload) -> bool:
        self.published.append((topic, payload.model_dump(mode="json")))
        return True


class _FakeActuators:
    """Ejecuta y registra (sustituye a ActuatorManager; el driver real es de T-1.9)."""

    def __init__(self) -> None:
        self.executed: list[ActuatorCommand] = []
        self.self_tests = 0
        self.self_test_result: dict = {
            "ok": True,
            "reason": None,
            "relays": {"gas_valve": {"pulsed": True, "readback_ok": True}},
        }

    # [T-2.86.a] `actor` acompaña a la firma real de `ActuatorManager`: el self-test
    # pulsa relés y deja fila en la bitácora local con QUIÉN lo pidió (el
    # `command_id` firmado). Este doble sólo tiene que aceptarlo.
    def cabinet_self_test(self, actor: str = "") -> dict:
        self.self_tests += 1
        return self.self_test_result

    def execute(self, command: ActuatorCommand) -> ActuatorAck:
        self.executed.append(command)
        return ActuatorAck(
            channel=command.channel,
            action=command.action,
            event_id=command.event_id,
            success=True,
            latency_s=0.01,
            detail="relé (fake)",
        )


def _sign_command(security: SecurityManager, payload: dict, nonce: str, ts: datetime) -> bytes:
    envelope = {
        "kind": "command",
        "command_id": f"cid-{nonce[:8]}",
        "nonce": nonce,
        "ts": ts.isoformat(),
        "payload": payload,
        "sig": security.sign(canonical_payload(payload), nonce, ts),
    }
    return json.dumps(envelope).encode()


def _dispatcher(
    *,
    command_enabled: bool = True,
    equipment: dict | None = None,
    cloud_admin_state: str = "active",
):
    extra = {"equipment": equipment} if equipment is not None else {}
    settings = EdgeSettings(
        dev_mode=True,
        command_enabled=command_enabled,
        cloud_admin_state=cloud_admin_state,
        **extra,
    )
    security = SecurityManager(KEY, clock=lambda: NOW)
    signer = SecurityManager(KEY, clock=lambda: NOW)  # lado "nube" (nonce-store aparte)
    config_store = ConfigStore(settings, security=security)
    actuators = _FakeActuators()
    cloud = _FakeCloud()
    dispatcher = CommandDispatcher(settings, security, config_store, actuators, cloud)
    return dispatcher, signer, cloud, config_store, actuators


def _siren_payload() -> dict:
    return {"channel": "siren", "action": "activate", "event_id": "EVT-TEST-1"}


def _acks(cloud: _FakeCloud) -> list[dict]:
    return [p for t, p in cloud.published if t == "takab/acks"]


# ------------------------------------------------------------------ comandos


def test_signed_command_executes_and_acks() -> None:
    dispatcher, signer, cloud, _store, actuators = _dispatcher(command_enabled=True)
    raw = _sign_command(signer, _siren_payload(), "n-1", NOW)
    dispatcher.on_command(CMD_TOPIC, raw)

    acks = _acks(cloud)
    assert len(acks) == 1
    ack = acks[0]
    assert ack["kind"] == "command_ack"
    assert ack["command_id"] == "cid-n-1"
    assert ack["nonce"] == "n-1"
    assert ack["channel"] == "siren"
    assert ack["action"] == "activate"
    assert ack["success"] is True


def test_command_enabled_false_rejects_with_ack() -> None:
    """Default de fábrica (regla de oro 8): verificado pero NO habilitado."""
    dispatcher, signer, cloud, _store, actuators = _dispatcher(command_enabled=False)
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, _siren_payload(), "n-2", NOW))

    acks = _acks(cloud)
    assert len(acks) == 1
    assert acks[0]["success"] is False
    assert "command_enabled" in acks[0]["detail"]
    assert actuators.executed == []  # jamás tocó el actuador


def test_command_on_uninstalled_channel_is_rejected_with_honest_ack() -> None:
    """[T-2.31] El sitio no tiene gas: un comando firmado a gas_valve no ejecuta
    nada y ACKea el rechazo con la razón — la nube marca rejected, no expired."""
    dispatcher, signer, cloud, _store, actuators = _dispatcher(equipment={"gas_valve": False})
    payload = {"channel": "gas_valve", "action": "activate", "event_id": "EVT-EQ-1"}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-eq", NOW))

    acks = _acks(cloud)
    assert len(acks) == 1
    assert acks[0]["success"] is False
    assert "no instalado" in acks[0]["detail"]
    assert actuators.executed == []


def test_gabinete_retirado_sigue_obedeciendo_el_comando_firmado_del_quorum() -> None:
    """[T-2.65 · REGLA DE ORO 1] La baja administrativa tampoco cierra ESTE canal.

    Tercer primo hermano de la familia, y el menos evidente: desde T-2.32 la
    actuación instrumental ya no la decide el gabinete solo — **la comanda la nube**
    con una orden FIRMADA cuando el quórum ≥3 confirma (regla de oro 8). Es decir,
    este dispatcher es hoy una vía de actuación de pleno derecho, no un canal
    administrativo. Un `if …current().is_retired: rechazar` puesto junto a los dos
    filtros legítimos que ya viven aquí sería la línea más natural del mundo de
    escribir —y dejaba al gabinete sordo al quórum con la suite del edge en «661
    passed, 5 skipped», ya con los guardianes nuevos del reflejo y de
    `_act_and_publish` dentro.

    La misma distinción que en `test_e2e.py`, medida en la misma corrida:

    * `command_enabled=false` (default de fábrica) y **equipamiento ausente** SÍ
      rechazan: el primero es una habilitación explícita de seguridad, el segundo un
      hecho físico. Los dos tienen ya sus tests y siguen vivos.
    * **`cloud_admin_state='retired'` NO rechaza**: es inventario. El edificio sigue
      en pie mientras el quórum de la red confirma un sismo.
    """
    dispatcher, signer, cloud, store, actuators = _dispatcher(
        cloud_admin_state="retired", equipment={"gas_valve": False}
    )
    assert store.current().is_retired is True  # guardarraíl del escenario

    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, _siren_payload(), "n-ret", NOW))
    acks = _acks(cloud)
    assert len(acks) == 1
    assert acks[0]["success"] is True, (
        f"el gabinete RETIRADO rechazó la orden firmada del quórum: {acks[0]['detail']!r}. "
        "Desde T-2.32 el quórum de red es la vía por la que llega la actuación "
        "instrumental; cerrarla por un acto de inventario deja al edificio sin la "
        "única actuación que la política dejó viva fuera de SASMEX."
    )
    assert [c.channel for c in actuators.executed] == [ActuatorChannel.SIREN]

    # …y el filtro FÍSICO de T-2.31 sigue rechazando lo que no existe.
    gas = {"channel": "gas_valve", "action": "activate", "event_id": "EVT-RET-2"}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, gas, "n-ret-2", NOW))
    acks = _acks(cloud)
    assert len(acks) == 2
    assert acks[1]["success"] is False and "no instalado" in acks[1]["detail"], (
        "se perdió el rechazo honesto del canal no instalado al blindar el estado "
        "administrativo: equipamiento (físico) y baja (inventario) son cosas distintas"
    )
    assert len(actuators.executed) == 1  # el gas jamás se tocó


def test_quorum_command_sets_network_alert_and_clear() -> None:
    """[T-2.32] Un comando firmado con origin=quorum ejecuta Y registra la
    fuente «QUÓRUM RED» (canales acumulados por evento); clear la cierra."""
    dispatcher, signer, _cloud, _store, actuators = _dispatcher()
    for i, channel in enumerate(("siren", "strobe")):
        payload = {
            "channel": channel,
            "action": "activate",
            "event_id": "EVT-QRED-1",
            "origin": "quorum",
        }
        dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, f"n-q{i}", NOW))
    assert len(actuators.executed) == 2

    alert = dispatcher.network_alert()
    assert alert is not None
    assert alert["event_id"] == "EVT-QRED-1"
    assert alert["channels"] == ["siren", "strobe"]

    dispatcher.clear_network_alert()
    assert dispatcher.network_alert() is None


def test_command_without_origin_does_not_claim_network_alert() -> None:
    """Un comando manual del SOC (sin origin) jamás se rotula como quórum."""
    dispatcher, signer, _cloud, _store, _actuators = _dispatcher()
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, _siren_payload(), "n-man", NOW))
    assert dispatcher.network_alert() is None


def test_bad_signature_neither_executes_nor_acks() -> None:
    dispatcher, signer, cloud, _store, actuators = _dispatcher()
    raw = _sign_command(signer, _siren_payload(), "n-3", NOW)
    tampered = json.loads(raw)
    tampered["payload"]["action"] = "deactivate"  # altera SIN re-firmar
    dispatcher.on_command(CMD_TOPIC, json.dumps(tampered).encode())
    assert _acks(cloud) == []
    assert actuators.executed == []


def test_replayed_nonce_rejected_silently() -> None:
    dispatcher, signer, cloud, _store, actuators = _dispatcher()
    raw = _sign_command(signer, _siren_payload(), "n-4", NOW)
    dispatcher.on_command(CMD_TOPIC, raw)
    dispatcher.on_command(CMD_TOPIC, raw)  # replay byte-idéntico
    assert len(_acks(cloud)) == 1  # solo la primera ejecución


def test_expired_command_rejected_silently() -> None:
    dispatcher, signer, cloud, _store, actuators = _dispatcher()
    old = NOW - timedelta(seconds=120)  # >> command_ttl_s=30
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, _siren_payload(), "n-5", old))
    assert _acks(cloud) == []


def test_malformed_messages_never_raise() -> None:
    dispatcher, _signer, cloud, _store, actuators = _dispatcher()
    for raw in (b"", b"no-json", b"[1,2]", b'{"kind":"command"}', b'{"payload":{}}'):
        dispatcher.on_command(CMD_TOPIC, raw)
    assert _acks(cloud) == []
    assert actuators.executed == []


def test_unknown_channel_rejected_silently() -> None:
    dispatcher, signer, cloud, _store, actuators = _dispatcher()
    payload = {"channel": "nuke", "action": "activate"}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-6", NOW))
    assert _acks(cloud) == []


def test_ack_channels_match_enums() -> None:
    dispatcher, signer, cloud, _store, actuators = _dispatcher()
    payload = {"channel": ActuatorChannel.GAS_VALVE.value, "action": ActuatorAction.ACTIVATE.value}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-7", NOW))
    assert _acks(cloud)[0]["channel"] == "gas_valve"


# -------------------------------------------------------------------- config


def _sign_config(signer: SecurityManager, payload: dict, version: int) -> bytes:
    return json.dumps(
        {
            "kind": "config_update",
            "version": version,
            "payload": payload,
            "sig": signer.sign_config(canonical_payload(payload), version),
        }
    ).encode()


def test_signed_config_applies_versioned() -> None:
    dispatcher, signer, _cloud, store, _act = _dispatcher()
    payload = {"dev_mode": True, "command_enabled": True}
    dispatcher.on_config("takab/cfg/gw-test", _sign_config(signer, payload, 1))
    assert store.version == 1
    assert store.current().command_enabled is True


def test_config_old_version_rejected() -> None:
    dispatcher, signer, _cloud, store, _act = _dispatcher()
    dispatcher.on_config("takab/cfg/gw-test", _sign_config(signer, {"dev_mode": True}, 5))
    assert store.version == 5
    # Versión vieja (replay de config anterior) → NO se aplica.
    dispatcher.on_config("takab/cfg/gw-test", _sign_config(signer, {"dev_mode": True}, 3))
    assert store.version == 5


def test_config_bad_signature_rejected() -> None:
    dispatcher, signer, _cloud, store, _act = _dispatcher()
    raw = json.loads(_sign_config(signer, {"dev_mode": True}, 1))
    raw["payload"]["command_enabled"] = True  # altera SIN re-firmar
    dispatcher.on_config("takab/cfg/gw-test", json.dumps(raw).encode())
    assert store.version == 0


def test_config_malformed_never_raises() -> None:
    dispatcher, _signer, _cloud, store, _act = _dispatcher()
    for raw in (b"", b"{}", b'{"version":"x","payload":{},"sig":"y"}'):
        dispatcher.on_config("takab/cfg/gw-test", raw)
    assert store.version == 0


# --- self_test (T-1.59): canal system, hilo corto, ack con results ---------------


def _wait_acks(cloud, n: int, timeout_s: float = 2.0) -> list[dict]:
    import time as _time

    deadline = _time.monotonic() + timeout_s
    while _time.monotonic() < deadline:
        acks = _acks(cloud)
        if len(acks) >= n:
            return acks
        _time.sleep(0.01)
    return _acks(cloud)


def test_signed_self_test_runs_and_acks_with_results() -> None:
    dispatcher, signer, cloud, _store, actuators = _dispatcher(command_enabled=True)
    payload = {"channel": "system", "action": "self_test", "event_id": None}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-st1", NOW))
    acks = _wait_acks(cloud, 1)
    assert len(acks) == 1 and actuators.self_tests == 1
    ack = acks[0]
    assert ack["channel"] == "system" and ack["action"] == "self_test"
    assert ack["success"] is True
    assert ack["results"]["relays"]["gas_valve"]["readback_ok"] is True
    assert actuators.executed == []  # jamás pasa por execute() de actuadores


def test_self_test_failure_reports_reason() -> None:
    dispatcher, signer, cloud, _store, actuators = _dispatcher(command_enabled=True)
    actuators.self_test_result = {"ok": False, "reason": "alerta viva", "relays": {}}
    payload = {"channel": "system", "action": "self_test", "event_id": None}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-st2", NOW))
    acks = _wait_acks(cloud, 1)
    assert acks[0]["success"] is False and "alerta viva" in acks[0]["detail"]


def test_self_test_on_actuator_channel_rejected() -> None:
    dispatcher, signer, cloud, _store, actuators = _dispatcher(command_enabled=True)
    payload = {"channel": "siren", "action": "self_test", "event_id": None}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-st3", NOW))
    acks = _acks(cloud)
    assert len(acks) == 1 and acks[0]["success"] is False
    assert "system" in acks[0]["detail"] and actuators.self_tests == 0


def test_activate_on_system_channel_rejected() -> None:
    dispatcher, signer, cloud, _store, actuators = _dispatcher(command_enabled=True)
    payload = {"channel": "system", "action": "activate", "event_id": None}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-st4", NOW))
    acks = _acks(cloud)
    assert len(acks) == 1 and acks[0]["success"] is False
    assert actuators.executed == []


class _FakeDrill:
    def __init__(self) -> None:
        self.started: list[tuple[str, float]] = []
        self.ended: list[str] = []
        self.start_result: tuple[bool, str] = (True, "simulacro iniciado")

    audio_evidence: dict = {
        "asset_id": "takab-simulacro-v1",
        "path": "/opt/takab/assets/simulacro.wav",
        "sha256": "a" * 64,
        "will_sound": True,
        "reason": "",
    }

    def start_drill(self, drill_id: str, duration_s: float) -> tuple[bool, str]:
        self.started.append((drill_id, duration_s))
        return self.start_result

    def end_drill(self, drill_id: str | None = None, reason: str = "") -> bool:
        self.ended.append(drill_id or "")
        return True

    def status(self) -> dict:
        """[T-5.17] El controlador real resuelve la evidencia de audio AL
        ARRANCAR y la deja aquí; el dispatcher la copia al acuse."""
        return {"active": True, "audio": self.audio_evidence}


def _drill_dispatcher():
    settings = EdgeSettings(dev_mode=True, command_enabled=True)
    security = SecurityManager(KEY, clock=lambda: NOW)
    signer = SecurityManager(KEY, clock=lambda: NOW)
    config_store = ConfigStore(settings, security=security)
    actuators = _FakeActuators()
    cloud = _FakeCloud()
    drill = _FakeDrill()
    dispatcher = CommandDispatcher(settings, security, config_store, actuators, cloud, drill=drill)
    return dispatcher, signer, cloud, actuators, drill


def test_signed_drill_start_reaches_controller_with_duration() -> None:
    dispatcher, signer, cloud, actuators, drill = _drill_dispatcher()
    payload = {
        "channel": "system",
        "action": "drill_start",
        "event_id": "DRILL-abc",
        "duration_s": 120,
    }
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-dr1", NOW))
    assert drill.started == [("DRILL-abc", 120.0)]
    acks = _acks(cloud)
    assert acks[0]["success"] is True and acks[0]["action"] == "drill_start"
    assert actuators.executed == []  # cero relés


def test_drill_start_rejected_by_live_alert_acks_reason() -> None:
    dispatcher, signer, cloud, _actuators, drill = _drill_dispatcher()
    drill.start_result = (False, "alerta SASMEX real en curso; simulacro rechazado")
    payload = {"channel": "system", "action": "drill_start", "event_id": "DRILL-x"}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-dr2", NOW))
    acks = _acks(cloud)
    assert acks[0]["success"] is False and "SASMEX" in acks[0]["detail"]


def test_signed_drill_stop_is_idempotent_ack() -> None:
    dispatcher, signer, cloud, _actuators, drill = _drill_dispatcher()
    payload = {"channel": "system", "action": "drill_stop", "event_id": "DRILL-abc"}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-dr3", NOW))
    assert drill.ended == ["DRILL-abc"]
    assert _acks(cloud)[0]["success"] is True


def test_drill_on_actuator_channel_rejected() -> None:
    dispatcher, signer, cloud, _actuators, drill = _drill_dispatcher()
    payload = {"channel": "siren", "action": "drill_start", "event_id": "DRILL-x"}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-dr4", NOW))
    assert drill.started == []
    assert _acks(cloud)[0]["success"] is False


def test_self_test_rejected_when_command_disabled() -> None:
    dispatcher, signer, cloud, _store, actuators = _dispatcher(command_enabled=False)
    payload = {"channel": "system", "action": "self_test", "event_id": None}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-st5", NOW))
    acks = _acks(cloud)
    assert len(acks) == 1 and acks[0]["success"] is False
    assert "command_enabled" in acks[0]["detail"] and actuators.self_tests == 0


# ------------------------------------------- [T-2.70] actualización remota


def _actualizacion(tmp_path, monkeypatch, *, ejecutable: bool = True):
    """Dispatcher con un agente de activación FALSO que sólo deja rastro.

    El agente de verdad reinicia `takab-edge`; aquí lo que se mide es qué se le
    ordena y —sobre todo— que el ack salga ANTES, porque en el gabinete real ese
    reinicio mata al proceso que lo lanzó.
    """
    rastro = tmp_path / "invocado.txt"
    guion = tmp_path / "canary.sh"
    guion.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{rastro}"\n')
    if ejecutable:
        guion.chmod(0o755)
    else:
        guion.chmod(0o644)
    dispatcher, signer, cloud, store, actuators = _dispatcher(command_enabled=True)
    monkeypatch.setattr(dispatcher._settings, "canary_script", str(guion), raising=False)
    return dispatcher, signer, cloud, rastro


def _esperar_rastro(rastro, intentos: int = 100) -> str:
    import time

    for _ in range(intentos):
        if rastro.exists() and rastro.read_text().strip():
            return rastro.read_text()
        time.sleep(0.05)
    return rastro.read_text() if rastro.exists() else ""


def test_una_orden_de_activacion_se_acusa_ANTES_de_lanzar_nada(tmp_path, monkeypatch) -> None:
    """EL ORDEN ES EL DISEÑO, y sin él la nube se queda ciega.

    Activar reinicia `takab-edge` — el proceso que ejecuta el despachador. Un
    ack posterior al lanzamiento no se publicaría jamás y la nube esperaría el
    TTL sin poder distinguir «rechazado» de «no contestó».
    """
    dispatcher, signer, cloud, rastro = _actualizacion(tmp_path, monkeypatch)
    payload = {
        "channel": "system",
        "action": "update_activate",
        "event_id": None,
        "release_id": "20260823T120000Z-abc1234",
    }
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-up-1", NOW))

    acks = _acks(cloud)
    assert len(acks) == 1, "sin ack, la nube no sabe si la orden llegó"
    assert acks[0]["success"] is True
    assert acks[0]["action"] == "update_activate"
    # …y el ack dice lo que SABE, no lo que espera que pase.
    assert "latido" in acks[0]["detail"]
    assert "20260823T120000Z-abc1234" in _esperar_rastro(rastro)


def test_la_orden_de_revertir_llega_al_agente_con_su_motivo(tmp_path, monkeypatch) -> None:
    """El fallo que el remojo NO puede ver es el que se descubre media hora
    después desde el SOC. Por eso revertir tiene que poder venir de fuera, y por
    eso el motivo viaja: es lo que queda escrito en el veredicto del gabinete."""
    dispatcher, signer, cloud, rastro = _actualizacion(tmp_path, monkeypatch)
    payload = {
        "channel": "system",
        "action": "update_rollback",
        "event_id": None,
        "motivo": "el SOC vio latencias raras",
    }
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-up-2", NOW))

    assert _acks(cloud)[0]["success"] is True
    rastro_txt = _esperar_rastro(rastro)
    assert "revertir" in rastro_txt
    assert "el SOC vio latencias raras" in rastro_txt


def test_un_release_id_que_no_es_un_id_no_llega_a_ejecutarse(tmp_path, monkeypatch) -> None:
    """Esta es la única superficie que ejecuta un proceso en el gabinete por
    orden de la nube. Los argumentos van por `execve` sin shell, así que una
    inyección no prospera igualmente — pero se valida antes, y el rechazo se
    ACUSA en vez de quedar en el journal."""
    dispatcher, signer, cloud, rastro = _actualizacion(tmp_path, monkeypatch)
    payload = {
        "channel": "system",
        "action": "update_activate",
        "event_id": None,
        "release_id": "../../etc; rm -rf /",
    }
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-up-3", NOW))

    acks = _acks(cloud)
    assert acks[0]["success"] is False
    assert "release_id inválido" in acks[0]["detail"]
    assert not rastro.exists(), "se invocó el agente con un id que no es un id"


def test_sin_agente_de_activacion_se_dice_AHORA_y_no_media_hora_despues(
    tmp_path, monkeypatch
) -> None:
    """Un gabinete todavía sin layout A/B no puede activar nada. Decirlo aquí es
    barato; lo contrario sería lanzar al vacío y dejar que el operador lo
    dedujera de un `fw_running` que no cambia."""
    dispatcher, signer, cloud, rastro = _actualizacion(tmp_path, monkeypatch, ejecutable=False)
    payload = {
        "channel": "system",
        "action": "update_activate",
        "event_id": None,
        "release_id": "20260823T120000Z-abc1234",
    }
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-up-4", NOW))

    acks = _acks(cloud)
    assert acks[0]["success"] is False
    assert "sin agente de activación" in acks[0]["detail"]


def test_una_actualizacion_por_un_canal_de_rele_se_rechaza(tmp_path, monkeypatch) -> None:
    """`update_*` es del canal lógico `system`. Aceptarla sobre `siren` sería
    aceptar una orden cuyo enrutado nadie decidió."""
    dispatcher, signer, cloud, rastro = _actualizacion(tmp_path, monkeypatch)
    payload = {
        "channel": "siren",
        "action": "update_activate",
        "event_id": None,
        "release_id": "20260823T120000Z-abc1234",
    }
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-up-5", NOW))

    acks = _acks(cloud)
    assert acks[0]["success"] is False
    assert "canal system" in acks[0]["detail"]
    assert not rastro.exists()


def test_una_actualizacion_sin_command_enabled_no_se_ejecuta(tmp_path, monkeypatch) -> None:
    """El default de fábrica (regla de oro 8) gobierna también a esta acción: un
    gabinete verificado pero NO habilitado no estrena código por orden remota."""
    rastro = tmp_path / "invocado.txt"
    guion = tmp_path / "canary.sh"
    guion.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{rastro}"\n')
    guion.chmod(0o755)
    dispatcher, signer, cloud, _store, _act = _dispatcher(command_enabled=False)
    monkeypatch.setattr(dispatcher._settings, "canary_script", str(guion), raising=False)
    payload = {
        "channel": "system",
        "action": "update_activate",
        "event_id": None,
        "release_id": "20260823T120000Z-abc1234",
    }
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-up-6", NOW))

    assert _acks(cloud)[0]["success"] is False
    assert "command_enabled" in _acks(cloud)[0]["detail"]
    assert not rastro.exists()


def test_el_acuse_del_drill_start_LLEVA_lo_que_va_a_sonar() -> None:
    """[T-5.17] Sin esto, «qué sonó en la torre B» solo vivía en el journal de la torre B.

    El acuse ya viajaba a la nube y ya se guardaba por sitio; lo que faltaba era
    que dijera QUÉ. `results` existe en el contrato del acuse desde siempre, así
    que esto no abre superficie nueva hacia el gabinete: solo la usa.
    """
    dispatcher, signer, cloud, _actuators, _drill = _drill_dispatcher()
    payload = {"channel": "system", "action": "drill_start", "event_id": "DRILL-audio"}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-dr-audio", NOW))

    ack = _acks(cloud)[0]
    assert ack["success"] is True
    audio = (ack.get("results") or {}).get("audio")
    assert audio is not None, "el acuse no dice qué sonó"
    assert audio["asset_id"] == "takab-simulacro-v1"
    assert len(audio["sha256"]) == 64


def test_un_drill_RECHAZADO_no_afirma_que_sono_nada() -> None:
    """Un `results.audio` en un rechazo diría que hubo voceo donde no hubo."""
    dispatcher, signer, cloud, _actuators, drill = _drill_dispatcher()
    drill.start_result = (False, "alerta SASMEX real en curso; simulacro rechazado")
    payload = {"channel": "system", "action": "drill_start", "event_id": "DRILL-no"}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-dr-no", NOW))

    ack = _acks(cloud)[0]
    assert ack["success"] is False
    assert (ack.get("results") or {}).get("audio") is None
