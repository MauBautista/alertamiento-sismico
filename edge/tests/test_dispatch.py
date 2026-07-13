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

    def cabinet_self_test(self) -> dict:
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


def _dispatcher(*, command_enabled: bool = True):
    settings = EdgeSettings(dev_mode=True, command_enabled=command_enabled)
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


def test_self_test_rejected_when_command_disabled() -> None:
    dispatcher, signer, cloud, _store, actuators = _dispatcher(command_enabled=False)
    payload = {"channel": "system", "action": "self_test", "event_id": None}
    dispatcher.on_command(CMD_TOPIC, _sign_command(signer, payload, "n-st5", NOW))
    acks = _acks(cloud)
    assert len(acks) == 1 and acks[0]["success"] is False
    assert "command_enabled" in acks[0]["detail"] and actuators.self_tests == 0
