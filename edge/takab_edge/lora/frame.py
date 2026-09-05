"""Trama LoRa v1 — códec binario firmado de los gabinetes secundarios (T-2.33).

Trama FIJA de 29 bytes (cabe de sobra en un payload LoRa a SF10/125 kHz):

    off  len  campo
    0    1    ver         (0x01; cambiar el layout exige 0x02)
    1    1    msg_type    (1=HEARTBEAT 2=ALARM_ACT 3=ALARM_CLEAR 4=ACK 5=TEST
                             6=SILENCE)
    2    2    cabinet_id  u16 BE — emisor (uplink) / destino (downlink)
    4    4    session     u32 BE — aleatoria al boot del EMISOR
    8    4    seq         u32 BE — contador monótono dentro de la sesión
    12   1    flags       bit0=siren bit1=strobe bit2=alarm_active bit3=test
    13   2    battery_mv  u16 BE — 0 = sin dato (solo uplink)
    15   4    arg         u32 BE — ACK: seq confirmado; resto 0
    19   10   hmac        HMAC-SHA256(k_cab, b"lora-v1" + trama[0:19])[:10]

Seguridad (espejo del estilo de ``security/``, dominio propio ``b"lora-v1"``):
- **Clave por gabinete DERIVADA** de la clave de sitio:
  ``k_i = HMAC(site_key, b"lora-cab" + id_be16)`` — un ESP32 comprometido no
  expone la clave de sitio ni las de sus hermanos.
- **Anti-replay SIN RTC** (el ESP32 no tiene reloj confiable): nada de TTL
  wall-clock. El receptor guarda ``(session, max_seq)`` por gabinete: mismo
  ``session`` con ``seq`` no creciente ⇒ rechazo; sesión nueva (boot) resetea el
  contador sin persistir nada. El replay cruzado de sesiones cae porque la
  sesión va FIRMADA.

Los vectores dorados de ``tests/test_lora_frame.py`` (espejados en
``takab-docs/design/LORA-SECUNDARIOS.md``) anclan la paridad byte-exacta con el
firmware ESP32 futuro.
"""

from __future__ import annotations

import hmac
import struct
from dataclasses import dataclass
from hashlib import sha256

VERSION = 0x01
_DOMAIN = b"lora-v1"
_MAC_LEN = 10
_BODY_LEN = 19
FRAME_LEN = _BODY_LEN + _MAC_LEN  # 29
_BODY_FMT = ">BBHIIBHI"

# Tipos de mensaje
HEARTBEAT = 1
ALARM_ACT = 2
ALARM_CLEAR = 3
ACK = 4
TEST = 5
#: [T-5.25] Silencio del operador: **corta los audibles YA**, deja el estrobo y
#: NO toca ``alarm_active``. Es el espejo exacto de ``gpio.silence_audibles()``
#: en el gabinete principal.
#:
#: Va como tipo PROPIO y no como un ``ALARM_ACT`` sin el bit de sirena por dos
#: razones que apuntan en la misma dirección —la peor—:
#:
#: 1. El contrato publicado dice que ``ALARM_ACT`` **enciende** (``LORA-
#:    SECUNDARIOS.md §2``). Un firmware escrito contra esa frase engancha la
#:    sirena y no la suelta con otro ``ALARM_ACT``; la ambigüedad cae del lado
#:    de «la sirena sigue sonando», que es justo el fallo que esto arregla.
#: 2. En el emisor, dos ``ALARM_ACT`` seguidos **SUMAN** flags a propósito (los
#:    comandos de red llegan por canal separado), así que un silencio disfrazado
#:    de activación se lo tragaría el ``merged |= pending["flags"]``.
#:
#: ADITIVO sobre v1: el layout no cambia, así que ``ver`` sigue en ``0x01``. Un
#: firmware que no conozca el tipo 6 lo rechaza y NO ackea ⇒ el panel lo declara
#: «SILENCIO SIN CONFIRMAR», que es la verdad y no un silencio fingido.
SILENCE = 6
_TYPES = (HEARTBEAT, ALARM_ACT, ALARM_CLEAR, ACK, TEST, SILENCE)

# Flags
FLAG_SIREN = 0x01
FLAG_STROBE = 0x02
FLAG_ALARM_ACTIVE = 0x04
FLAG_TEST = 0x08


class FrameError(Exception):
    """Trama rechazada (tamaño/versión/tipo/firma)."""


def derive_key(site_key: bytes, cabinet_id: int) -> bytes:
    """Clave por gabinete: ``HMAC(site_key, b"lora-cab" + id_be16)`` (32 B)."""
    if not 0 < cabinet_id <= 0xFFFF:
        raise ValueError(f"cabinet_id fuera de u16: {cabinet_id}")
    return hmac.new(site_key, b"lora-cab" + cabinet_id.to_bytes(2, "big"), sha256).digest()


@dataclass(frozen=True)
class LoraFrame:
    """Trama decodificada/por codificar (sin la firma; la pone el códec)."""

    msg_type: int
    cabinet_id: int
    session: int
    seq: int
    flags: int = 0
    battery_mv: int = 0
    arg: int = 0

    def encode(self, key: bytes) -> bytes:
        """Serializa y FIRMA con la clave del gabinete (29 bytes)."""
        if self.msg_type not in _TYPES:
            raise FrameError(f"msg_type desconocido: {self.msg_type}")
        body = struct.pack(
            _BODY_FMT,
            VERSION,
            self.msg_type,
            self.cabinet_id,
            self.session,
            self.seq,
            self.flags,
            self.battery_mv,
            self.arg,
        )
        return body + _mac(key, body)


def _mac(key: bytes, body: bytes) -> bytes:
    return hmac.new(key, _DOMAIN + body, sha256).digest()[:_MAC_LEN]


def decode(raw: bytes, key: bytes) -> LoraFrame:
    """Verifica la firma y decodifica. Lanza ``FrameError`` si no verifica.

    La verificación es lo PRIMERO (``compare_digest``): una trama forjada o
    alterada jamás llega a interpretarse.
    """
    if len(raw) != FRAME_LEN:
        raise FrameError(f"tamaño inválido: {len(raw)} != {FRAME_LEN}")
    body, mac = raw[:_BODY_LEN], raw[_BODY_LEN:]
    if not hmac.compare_digest(mac, _mac(key, body)):
        raise FrameError("firma inválida (rechazada)")
    ver, msg_type, cabinet_id, session, seq, flags, battery_mv, arg = struct.unpack(_BODY_FMT, body)
    if ver != VERSION:
        raise FrameError(f"versión desconocida: {ver:#x}")
    if msg_type not in _TYPES:
        raise FrameError(f"msg_type desconocido: {msg_type}")
    return LoraFrame(
        msg_type=msg_type,
        cabinet_id=cabinet_id,
        session=session,
        seq=seq,
        flags=flags,
        battery_mv=battery_mv,
        arg=arg,
    )


class ReplayGuard:
    """Anti-replay por gabinete: ``(session, max_seq)`` en memoria.

    ``accept()`` decide ANTES de consumir la trama: misma sesión exige ``seq``
    estrictamente creciente; una sesión distinta (boot del emisor) resetea el
    contador. Nada se persiste — el peor caso tras un reinicio del receptor es
    aceptar una trama vieja UNA vez, cuya firma sigue siendo válida y cuyo
    contenido es idempotente (heartbeat/ack)."""

    def __init__(self) -> None:
        self._seen: dict[int, tuple[int, int]] = {}

    def accept(self, frame: LoraFrame) -> bool:
        last = self._seen.get(frame.cabinet_id)
        if last is not None:
            session, max_seq = last
            if frame.session == session and frame.seq <= max_seq:
                return False
        self._seen[frame.cabinet_id] = (frame.session, frame.seq)
        return True
