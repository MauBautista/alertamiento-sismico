"""AwsIotMqttTransport (T-1.17 G6): CONNACK antes de `connected`, PUBACK antes de confirmar.

Sin awscrt real (el import es perezoso): se inyectan módulos fake en sys.modules.
Lo que se pinnea: un connect fallido NO deja el transporte "conectado" (el loop de
reconexión debe seguir reintentando) y publish NO confirma sin PUBACK (el spool
"cero pérdida" jamás se limpia sin acuse del broker).
"""

from __future__ import annotations

import sys
import types

import pytest
from takab_edge.cloud import AwsIotMqttTransport, CloudConnector
from takab_edge.contracts import AlertSource, Tier, TierDecision


class _FakeFuture:
    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc
        self.waited = 0

    def result(self, timeout: float | None = None) -> None:
        self.waited += 1
        if self._exc is not None:
            raise self._exc


class _FakeConnection:
    def __init__(
        self, connect_exc: Exception | None = None, publish_exc: Exception | None = None
    ) -> None:
        self._connect_exc = connect_exc
        self.publish_future = _FakeFuture(publish_exc)
        self.published: list[tuple[str, bytes]] = []

    def connect(self) -> _FakeFuture:
        return _FakeFuture(self._connect_exc)

    def disconnect(self) -> _FakeFuture:
        return _FakeFuture()

    def publish(self, topic: str, payload: bytes, qos: object, retain: bool = False):
        self.published.append((topic, payload))
        return (self.publish_future, 1)


@pytest.fixture
def fake_sdk(monkeypatch):
    """awscrt/awsiot falsos; ``holder`` permite configurar la conexión del builder."""
    holder: dict = {"conn": _FakeConnection(), "kwargs": None}

    mqtt_mod = types.ModuleType("awscrt.mqtt")

    class _Will:
        def __init__(self, topic: str, qos: object, payload: bytes, retain: bool) -> None:
            self.topic = topic

    class _QoS:
        AT_LEAST_ONCE = 1

    mqtt_mod.Will = _Will
    mqtt_mod.QoS = _QoS

    awscrt_mod = types.ModuleType("awscrt")
    awscrt_mod.mqtt = mqtt_mod

    builder_mod = types.ModuleType("awsiot.mqtt_connection_builder")

    def mtls_from_path(**kwargs):
        holder["kwargs"] = kwargs
        return holder["conn"]

    builder_mod.mtls_from_path = mtls_from_path
    awsiot_mod = types.ModuleType("awsiot")
    awsiot_mod.mqtt_connection_builder = builder_mod

    monkeypatch.setitem(sys.modules, "awscrt", awscrt_mod)
    monkeypatch.setitem(sys.modules, "awscrt.mqtt", mqtt_mod)
    monkeypatch.setitem(sys.modules, "awsiot", awsiot_mod)
    monkeypatch.setitem(sys.modules, "awsiot.mqtt_connection_builder", builder_mod)
    return holder


def _transport(settings) -> AwsIotMqttTransport:
    return AwsIotMqttTransport(
        settings,
        "/etc/takab/cert.pem",
        "/etc/takab/key.pem",
        "/etc/takab/ca.pem",
        client_id="gw-dev-0001",
        status_topic="takab/status/gw-dev-0001",
    )


def _decision(event_id: str = "e1") -> TierDecision:
    return TierDecision(event_id=event_id, tier=Tier.WATCH, source=AlertSource.THRESHOLD)


def test_failed_connect_is_not_connected(settings, fake_sdk):
    # Pi sin internet al arrancar: connect() lanza y el transporte debe quedar
    # DESCONECTADO (antes quedaba "connected" y el flush vaciaba el spool en vano).
    fake_sdk["conn"] = _FakeConnection(connect_exc=ConnectionError("sin internet"))
    transport = _transport(settings)
    with pytest.raises(ConnectionError):
        transport.connect()
    assert transport.connected is False
    assert transport.publish("takab/events", b"{}") is False  # nada se confirma


def test_connect_registers_interruption_callbacks(settings, fake_sdk):
    transport = _transport(settings)
    transport.connect()
    assert transport.connected is True
    kwargs = fake_sdk["kwargs"]
    assert kwargs["on_connection_interrupted"] is not None
    assert kwargs["on_connection_resumed"] is not None
    assert kwargs["clean_session"] is False  # sesión persistente QoS1


def test_publish_waits_for_puback(settings, fake_sdk):
    transport = _transport(settings)
    transport.connect()
    assert transport.publish("takab/events", b"{}") is True
    assert fake_sdk["conn"].publish_future.waited == 1  # se esperó el PUBACK


def test_publish_without_puback_keeps_message_in_spool(settings, fake_sdk, tmp_path):
    # El escenario del hallazgo: sin PUBACK el flush NO borra el spool durable.
    fake_sdk["conn"] = _FakeConnection(publish_exc=TimeoutError("sin PUBACK"))
    transport = _transport(settings)
    transport.connect()
    cloud = CloudConnector(settings, transport=transport, spool_dir=str(tmp_path))
    assert cloud.publish("takab/events", _decision()) is True  # nunca lanza al llamador
    assert cloud.queued == 1  # sigue encolado para reintento
    assert len(list(tmp_path.glob("*.json"))) == 1  # y sigue en disco (cero pérdida)
    assert cloud.sent == 0


def test_interruption_and_resume_track_link_state(settings, fake_sdk):
    transport = _transport(settings)
    transport.connect()
    transport._on_interrupted(connection=None, error=RuntimeError("corte WAN"))
    assert transport.connected is False  # sin enlace no se confía en publish

    class _Accepted:  # ConnectReturnCode.ACCEPTED
        value = 0

    transport._on_resumed(connection=None, return_code=_Accepted(), session_present=True)
    assert transport.connected is True


def test_disconnect_clears_connection(settings, fake_sdk):
    transport = _transport(settings)
    transport.connect()
    transport.disconnect()
    assert transport.connected is False
