"""Trama LoRa v1 (T-2.33): códec byte-exacto, firma derivada y anti-replay.

Los VECTORES DORADOS anclan la paridad con el firmware ESP32 futuro (espejo en
``takab-docs/design/LORA-SECUNDARIOS.md``): cambiar el layout o la derivación
de claves DEBE romper estos tests y exige ``ver=0x02``.
"""

from __future__ import annotations

import pytest
from takab_edge.lora.frame import (
    ACK,
    ALARM_ACT,
    FLAG_ALARM_ACTIVE,
    FLAG_SIREN,
    FLAG_STROBE,
    FRAME_LEN,
    HEARTBEAT,
    FrameError,
    LoraFrame,
    ReplayGuard,
    decode,
    derive_key,
)

SITE_KEY = b"clave-lora-de-sitio-0123456789ab"
CAB = 258  # 0x0102

# --- vectores dorados (byte-exactos; paridad con el firmware) ---------------
K258_HEX = "d6d04c86c73040548bb923c24d63251cd04892bb4499069f4fd8ba36faee71ea"
HB_HEX = "01010102deadbeef00000007040f1e00000000695d15496a56fb0c166e"
ACT_HEX = "010201020102030400000029030000000000006c664dc3f5fa446c1343"
ACK_HEX = "01040102deadbeef0000000800000000000029e6134d8ef72a36d5a18b"


def _key() -> bytes:
    return derive_key(SITE_KEY, CAB)


def test_derived_key_golden_vector():
    assert _key().hex() == K258_HEX


def test_golden_vectors_encode_byte_exact():
    hb = LoraFrame(
        msg_type=HEARTBEAT,
        cabinet_id=CAB,
        session=0xDEADBEEF,
        seq=7,
        flags=FLAG_ALARM_ACTIVE,
        battery_mv=3870,
    )
    act = LoraFrame(
        msg_type=ALARM_ACT,
        cabinet_id=CAB,
        session=0x01020304,
        seq=41,
        flags=FLAG_SIREN | FLAG_STROBE,
    )
    ack = LoraFrame(msg_type=ACK, cabinet_id=CAB, session=0xDEADBEEF, seq=8, arg=41)
    assert hb.encode(_key()).hex() == HB_HEX
    assert act.encode(_key()).hex() == ACT_HEX
    assert ack.encode(_key()).hex() == ACK_HEX
    assert len(bytes.fromhex(HB_HEX)) == FRAME_LEN == 29


def test_roundtrip_decode():
    frame = LoraFrame(
        msg_type=HEARTBEAT,
        cabinet_id=CAB,
        session=123,
        seq=456,
        flags=FLAG_SIREN,
        battery_mv=4100,
        arg=0,
    )
    assert decode(frame.encode(_key()), _key()) == frame


def test_tampered_frame_is_rejected():
    raw = bytearray(bytes.fromhex(ACT_HEX))
    raw[12] = 0x00  # apagar flags SIN re-firmar (quitarle la sirena a la orden)
    with pytest.raises(FrameError, match="firma"):
        decode(bytes(raw), _key())


def test_wrong_key_and_wrong_cabinet_key_are_rejected():
    raw = bytes.fromhex(HB_HEX)
    with pytest.raises(FrameError):
        decode(raw, derive_key(SITE_KEY, 259))  # clave del hermano: NO abre
    with pytest.raises(FrameError):
        decode(raw, b"otra-clave-de-sitio-desconocida!")


def test_truncated_and_bad_version_rejected():
    with pytest.raises(FrameError, match="tamaño"):
        decode(bytes.fromhex(HB_HEX)[:-1], _key())
    frame = LoraFrame(msg_type=HEARTBEAT, cabinet_id=CAB, session=1, seq=1)
    raw = bytearray(frame.encode(_key()))
    raw[0] = 0x02  # versión futura sin re-firmar ⇒ ni siquiera verifica
    with pytest.raises(FrameError):
        decode(bytes(raw), _key())


def test_replay_guard_same_session_requires_growing_seq():
    guard = ReplayGuard()
    f1 = LoraFrame(msg_type=HEARTBEAT, cabinet_id=CAB, session=99, seq=5)
    assert guard.accept(f1) is True
    assert guard.accept(f1) is False  # replay exacto
    assert guard.accept(LoraFrame(msg_type=HEARTBEAT, cabinet_id=CAB, session=99, seq=4)) is False
    assert guard.accept(LoraFrame(msg_type=HEARTBEAT, cabinet_id=CAB, session=99, seq=6)) is True


def test_replay_guard_new_session_resets_counter():
    guard = ReplayGuard()
    assert guard.accept(LoraFrame(msg_type=HEARTBEAT, cabinet_id=CAB, session=99, seq=500))
    # Boot del ESP32: sesión nueva acepta seq=1 (nada que persistir).
    assert guard.accept(LoraFrame(msg_type=HEARTBEAT, cabinet_id=CAB, session=100, seq=1))
    # …y la sesión VIEJA re-entregada cae (guard ya apunta a la nueva y la vieja
    # no crece frente a la última vista de ESA sesión sólo si coincide; una
    # sesión distinta siempre resetea — el replay cruzado lo corta la FIRMA de
    # la sesión + el contador de la sesión activa).
    assert guard.accept(LoraFrame(msg_type=HEARTBEAT, cabinet_id=CAB, session=100, seq=1)) is False


def test_replay_guard_tracks_per_cabinet():
    guard = ReplayGuard()
    assert guard.accept(LoraFrame(msg_type=HEARTBEAT, cabinet_id=1, session=7, seq=3))
    assert guard.accept(LoraFrame(msg_type=HEARTBEAT, cabinet_id=2, session=7, seq=3))
    assert guard.accept(LoraFrame(msg_type=HEARTBEAT, cabinet_id=1, session=7, seq=3)) is False


def test_derive_key_rejects_out_of_range_ids():
    with pytest.raises(ValueError):
        derive_key(SITE_KEY, 0)
    with pytest.raises(ValueError):
        derive_key(SITE_KEY, 70000)
