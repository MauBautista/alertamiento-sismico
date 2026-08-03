"""LoraLink (T-2.33): registry por heartbeat, repeat-until-ack y transiciones.

Transporte simulado en proceso (cero radio): la pérdida de paquetes es
DETERMINISTA (``drop_next``) y los heartbeats se inyectan cuando el guion lo
pide. Los tiempos de reintento se encogen para que la suite vuele.
"""

from __future__ import annotations

import time

import pytest
from simulators.lora import FakeSecondaryCabinet, SimulatedLoraTransport
from takab_edge.config import LoraConfig, SecondaryCabinet, load_settings
from takab_edge.lora import LoraLink
from takab_edge.lora import frame as fr

SITE_KEY = b"clave-lora-de-sitio-0123456789ab"


def _settings(**lora_over):
    defaults = {
        "enabled": True,
        "heartbeat_s": 60.0,
        "heartbeat_timeout_factor": 3.0,
        "alarm_retry_max": 5,
        "alarm_retry_s": 0.05,
        "secondaries": [
            SecondaryCabinet(id=258, name="AZOTEA-NORTE", zone="Torre B"),
            SecondaryCabinet(id=259, name="PATIO-SUR", zone="Patio"),
        ],
    }
    return load_settings().model_copy(update={"lora": LoraConfig(**{**defaults, **lora_over})})


def _wait(condition, timeout_s: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


@pytest.fixture
def link():
    transport = SimulatedLoraTransport()
    cab1 = transport.attach(FakeSecondaryCabinet(SITE_KEY, 258, battery_mv=3870))
    cab2 = transport.attach(FakeSecondaryCabinet(SITE_KEY, 259, battery_mv=4020))
    lora = LoraLink(_settings(), transport, SITE_KEY)
    lora.start()
    try:
        yield lora, transport, cab1, cab2
    finally:
        lora.stop()


def _sec(lora: LoraLink, cab_id: int) -> dict:
    return next(s for s in lora.snapshot()["secondaries"] if s["id"] == cab_id)


def test_heartbeat_updates_registry(link):
    lora, transport, cab1, _cab2 = link
    assert _sec(lora, 258)["link"] == "never"
    transport.deliver(cab1.heartbeat())
    row = _sec(lora, 258)
    assert row["link"] == "online"
    assert row["battery_mv"] == 3870
    assert row["rssi_dbm"] == pytest.approx(-92.0)
    assert row["snr_db"] == pytest.approx(7.5)
    assert row["age_s"] is not None and row["age_s"] < 5.0


def test_propagate_activate_reaches_all_and_acks(link):
    lora, _transport, cab1, cab2 = link
    lora.propagate("activate", siren=True, strobe=True)
    assert _wait(lambda: cab1.alarm_active and cab2.alarm_active)
    assert _wait(lambda: _sec(lora, 258)["acked"] is True and _sec(lora, 259)["acked"] is True)
    assert cab1.flags_seen & fr.FLAG_SIREN and cab1.flags_seen & fr.FLAG_STROBE
    assert _sec(lora, 258)["alarm_active"] is True


def test_lost_frames_retry_until_ack(link):
    lora, transport, cab1, _cab2 = link
    transport.drop_next(2)  # el aire se come los 2 primeros downlinks
    lora.propagate("activate", siren=True)
    assert _wait(lambda: cab1.alarm_active)
    assert _wait(lambda: _sec(lora, 258)["acked"] is True)
    # hubo reintentos: se emitieron MÁS tramas de las que llegaron
    assert len(transport.sent) > 2


def test_retry_cap_leaves_sin_ack_visible():
    transport = SimulatedLoraTransport()
    cab = transport.attach(FakeSecondaryCabinet(SITE_KEY, 258))
    lora = LoraLink(
        _settings(alarm_retry_max=3, secondaries=[SecondaryCabinet(id=258)]), transport, SITE_KEY
    )
    lora.start()
    try:
        transport.drop_next(999)  # enlace muerto
        lora.propagate("activate", siren=True)
        assert _wait(lambda: len(transport.sent) >= 3)
        time.sleep(0.2)  # margen: no debe emitir más allá del tope
        assert len(transport.sent) == 3
        assert _sec(lora, 258)["acked"] is False
        assert cab.alarm_active is False
    finally:
        lora.stop()


def test_propagate_clear_releases_secondaries(link):
    lora, _transport, cab1, _cab2 = link
    lora.propagate("activate", siren=True, strobe=True)
    assert _wait(lambda: cab1.alarm_active)
    lora.propagate("clear")
    assert _wait(lambda: not cab1.alarm_active)
    assert _wait(lambda: _sec(lora, 258)["alarm_active"] is False)


def test_heartbeat_timeout_marks_offline_and_recovers():
    transport = SimulatedLoraTransport()
    cab = transport.attach(FakeSecondaryCabinet(SITE_KEY, 258))
    lora = LoraLink(
        _settings(
            heartbeat_s=0.05,
            heartbeat_timeout_factor=1.0,
            secondaries=[SecondaryCabinet(id=258, name="AZOTEA")],
        ),
        transport,
        SITE_KEY,
    )
    lora.start()
    try:
        transport.deliver(cab.heartbeat())
        assert _sec(lora, 258)["link"] == "online"
        assert _wait(lambda: _sec(lora, 258)["link"] == "offline")  # ENLACE PERDIDO
        transport.deliver(cab.heartbeat())
        assert _sec(lora, 258)["link"] == "online"  # recupera con el siguiente latido
    finally:
        lora.stop()


def test_forged_and_replayed_uplinks_are_ignored(link):
    lora, transport, cab1, _cab2 = link
    hb = cab1.heartbeat()
    transport.deliver(hb)
    first_age = _sec(lora, 258)["age_s"]
    tampered = bytearray(hb)
    tampered[13] = 0xFF  # inflar batería sin re-firmar
    transport.deliver(bytes(tampered))
    transport.deliver(hb)  # replay exacto (misma sesión, mismo seq)
    assert _sec(lora, 258)["battery_mv"] == 3870
    assert first_age is not None


def test_propagate_never_blocks(link):
    lora, _transport, _cab1, _cab2 = link
    started = time.monotonic()
    lora.propagate("activate", siren=True)
    assert time.monotonic() - started < 0.05  # encola y regresa


def test_lifecycle_is_idempotent():
    transport = SimulatedLoraTransport()
    lora = LoraLink(_settings(), transport, SITE_KEY)
    lora.start()
    lora.start()
    assert transport.opened is True
    lora.stop()
    lora.stop()
    assert transport.opened is False
