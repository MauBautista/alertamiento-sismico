"""Lector miniSEED mínimo para el dictamen técnico (T-2.41).

Se escribe aquí en vez de usar ObsPy por una razón concreta: ObsPy arrastra matplotlib,
scipy y lxml — más de 200 MB — a una imagen que corre co-locada con TimescaleDB en un
EC2 Graviton pequeño. Todo eso para leer un formato que **nosotros mismos escribimos**
(``edge/takab_edge/buffer``: int32 vía ObsPy ⇒ codificación STEIM2, big-endian).

El alcance es deliberadamente estrecho: SEED 2.4 de longitud fija con blockette 1000,
encodings 10/11 (STEIM1/STEIM2) y 3 (int32). Cualquier otra cosa lanza ``MseedError`` y
el dictamen declara la sección como no disponible — degradar es correcto; adivinar no.

Referencia del formato: SEED Manual v2.4 §8 (Fixed Section of Data Header) y
Appendix B (Steim compression).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

#: Techo de seguridad: un miniSEED de evento son cientos de KB. Si llega algo mucho
#: mayor, el dictamen prefiere declararlo a masticar 200 MB dentro de un request.
MAX_BYTES = 32 * 1024 * 1024

_FIXED_HEADER = 48
_BLOCKETTE_1000 = 1000


class MseedError(Exception):
    """El blob no es un miniSEED que este lector sepa interpretar."""


@dataclass(frozen=True, slots=True)
class Trace:
    """Una traza continua de un canal."""

    network: str
    station: str
    location: str
    channel: str
    sample_rate: float
    #: Cuentas del ADC, sin calibrar. Convertirlas a g exige la respuesta instrumental.
    samples: list[int]


def _sample_rate(factor: int, multiplier: int) -> float:
    """SEED codifica la tasa como factor/multiplicador con signo (§8, campos 10-11)."""
    rate = float(factor)
    if factor < 0:
        rate = -1.0 / factor
    if multiplier > 0:
        rate *= multiplier
    elif multiplier < 0:
        rate /= -multiplier
    return rate


def _decode_steim(payload: bytes, frames: int, expected: int, steim2: bool) -> list[int]:
    """Descomprime marcos Steim1/Steim2 (big-endian, 64 bytes por marco).

    Cada marco: 16 palabras de 32 bits. W0 lleva 16 pares de "nibbles" que dicen cómo
    interpretar las 15 palabras siguientes. El primer marco trae además X0 (primera
    muestra) y Xn (última, para verificar) en W1 y W2.

    ⚠️ La PRIMERA diferencia del flujo no es una diferencia de este registro: enlaza
    con la última muestra del registro anterior. Sumarla produce una traza desplazada
    en un valor arbitrario —plausible a la vista y completamente falsa—, así que se
    descarta y la reconstrucción arranca de X0.
    """
    x0: int | None = None
    xn: int | None = None
    diffs: list[int] = []

    for f in range(frames):
        base = f * 64
        if base + 64 > len(payload):
            break
        nibbles = struct.unpack_from(">I", payload, base)[0]
        for w in range(1, 16):
            word_off = base + 4 * w
            if word_off + 4 > len(payload):
                break
            nib = (nibbles >> (30 - 2 * w)) & 0b11
            raw = struct.unpack_from(">i", payload, word_off)[0]

            if f == 0 and w == 1:
                x0 = raw
                continue
            if f == 0 and w == 2:
                xn = raw
                continue
            if nib == 0:
                continue  # palabra no-dato (relleno)
            diffs.extend(_diffs(raw, nib, steim2))

    if x0 is None:
        raise MseedError("marco Steim sin X0")

    out = [x0]
    for d in diffs[1:]:  # [1:] = se descarta el enlace con el registro anterior
        if len(out) >= expected:
            break
        out.append(out[-1] + d)

    if xn is not None and len(out) == expected and out[-1] != xn:
        # El manual SEED define Xn justamente para esto: si no cuadra, el bloque está
        # corrupto y devolverlo produciría una traza plausible pero falsa.
        raise MseedError("verificación Xn de Steim fallida: registro corrupto")
    return out[:expected]


def _diffs(word: int, nib: int, steim2: bool) -> list[int]:
    """Diferencias empaquetadas en una palabra, según su nibble de control."""
    unsigned = word & 0xFFFFFFFF
    if nib == 1:  # 4 diferencias de 8 bits
        return [_signed((unsigned >> shift) & 0xFF, 8) for shift in (24, 16, 8, 0)]
    if nib == 2:
        if not steim2:  # Steim1: 2 × 16 bits
            return [_signed((unsigned >> shift) & 0xFFFF, 16) for shift in (16, 0)]
        dnib = unsigned >> 30
        if dnib == 1:  # 1 × 30 bits
            return [_signed(unsigned & 0x3FFFFFFF, 30)]
        if dnib == 2:  # 2 × 15 bits
            return [_signed((unsigned >> shift) & 0x7FFF, 15) for shift in (15, 0)]
        if dnib == 3:  # 3 × 10 bits
            return [_signed((unsigned >> shift) & 0x3FF, 10) for shift in (20, 10, 0)]
        raise MseedError("nibble Steim2 no válido en palabra de 2 bits")
    if nib == 3:
        if not steim2:  # Steim1: 1 × 32 bits
            return [_signed(unsigned, 32)]
        dnib = unsigned >> 30
        if dnib == 0:  # 5 × 6 bits
            return [_signed((unsigned >> shift) & 0x3F, 6) for shift in (24, 18, 12, 6, 0)]
        if dnib == 1:  # 6 × 5 bits
            return [_signed((unsigned >> shift) & 0x1F, 5) for shift in (25, 20, 15, 10, 5, 0)]
        if dnib == 2:  # 7 × 4 bits
            return [_signed((unsigned >> shift) & 0xF, 4) for shift in (24, 20, 16, 12, 8, 4, 0)]
        raise MseedError("nibble Steim2 no válido en palabra de 3 bits")
    return []


def _signed(value: int, bits: int) -> int:
    """Complemento a dos de ``bits`` bits."""
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)


def read_traces(blob: bytes) -> list[Trace]:
    """Traza por canal SEED. Lanza ``MseedError`` ante cualquier cosa inesperada."""
    if len(blob) > MAX_BYTES:
        raise MseedError(f"miniSEED demasiado grande ({len(blob)} bytes)")
    if len(blob) < _FIXED_HEADER:
        raise MseedError("blob más corto que una cabecera SEED")

    by_channel: dict[tuple[str, str, str, str], tuple[float, list[int]]] = {}
    offset = 0
    while offset + _FIXED_HEADER <= len(blob):
        header = blob[offset : offset + _FIXED_HEADER]
        station = header[8:13].decode("ascii", "replace").strip()
        location = header[13:15].decode("ascii", "replace").strip()
        channel = header[15:18].decode("ascii", "replace").strip()
        network = header[18:20].decode("ascii", "replace").strip()
        n_samples = struct.unpack_from(">H", header, 30)[0]
        rate = _sample_rate(*struct.unpack_from(">hh", header, 32))
        n_blockettes = header[39]
        data_offset = struct.unpack_from(">H", header, 44)[0]
        first_blockette = struct.unpack_from(">H", header, 46)[0]

        encoding, record_len = _read_b1000(blob, offset, first_blockette, n_blockettes)
        if data_offset == 0 or data_offset > record_len:
            raise MseedError("offset de datos fuera del registro")

        payload = blob[offset + data_offset : offset + record_len]
        if encoding in (10, 11):
            frames = len(payload) // 64
            samples = _decode_steim(payload, frames, n_samples, steim2=encoding == 11)
        elif encoding == 3:
            count = min(n_samples, len(payload) // 4)
            samples = list(struct.unpack_from(f">{count}i", payload, 0))
        else:
            raise MseedError(f"codificación miniSEED no soportada: {encoding}")

        key = (network, station, location, channel)
        prev = by_channel.get(key)
        by_channel[key] = (rate, (prev[1] if prev else []) + samples)
        offset += record_len

    return [
        Trace(
            network=net,
            station=sta,
            location=loc,
            channel=cha,
            sample_rate=rate,
            samples=samples,
        )
        for (net, sta, loc, cha), (rate, samples) in by_channel.items()
    ]


def _read_b1000(blob: bytes, record_start: int, first: int, count: int) -> tuple[int, int]:
    """Encoding y longitud de registro desde la blockette 1000 (obligatoria en 2.4)."""
    next_off = first
    for _ in range(max(count, 0)):
        if next_off == 0 or record_start + next_off + 8 > len(blob):
            break
        btype, following = struct.unpack_from(">HH", blob, record_start + next_off)
        if btype == _BLOCKETTE_1000:
            encoding = blob[record_start + next_off + 4]
            length_exp = blob[record_start + next_off + 6]
            return encoding, 1 << length_exp
        next_off = following
    raise MseedError("registro sin blockette 1000: no se puede saber su longitud")
