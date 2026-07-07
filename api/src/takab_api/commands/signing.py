"""Firma HMAC de comandos/config — espejo BYTE-IDÉNTICO del edge (T-1.23).

El framing es el de ``takab_edge.security.SecurityManager``: cada campo va
length-prefixed (8 bytes big-endian) para que los límites sean inequívocos, con
dominios separados ``b"command"`` y ``b"config"``. Los vectores compartidos
(``shared/schemas/tests/hmac_vectors.json``, generados con el SecurityManager
REAL del edge) fijan el framing en las suites de AMBOS lados: cualquier drift
truena en CI. [DECISION T-1.23]: HMAC, no JWT — el edge (T-1.12) pinea HMAC y
RBAC §4.3 acepta "HMAC/JWT corto".

La clave se inyecta (Secrets Manager/env); NUNCA se hardcodea (regla de oro 6).
"""

from __future__ import annotations

import hmac
import json
from hashlib import sha256


def canonical_payload(payload: dict) -> bytes:
    """JSON canónico (claves ordenadas, sin espacios) — base estable de la firma."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _frame(*parts: bytes) -> bytes:
    out = bytearray()
    for part in parts:
        out += len(part).to_bytes(8, "big") + part
    return bytes(out)


def _hmac(key: bytes, *parts: bytes) -> str:
    return hmac.new(key, _frame(*parts), sha256).hexdigest()


def sign_command(key: bytes, payload: bytes, nonce: str, ts_iso: str) -> str:
    """Firma de un comando sobre (dominio, nonce, ts, payload).

    ``ts_iso`` es el string EXACTO que viaja en el envelope: el edge lo parsea
    con ``fromisoformat`` y re-serializa con ``isoformat()`` — round-trip
    exacto para el formato canónico de ``datetime.isoformat``.
    """
    return _hmac(key, b"command", nonce.encode(), ts_iso.encode(), payload)


def sign_config(key: bytes, payload: bytes, version: int) -> str:
    """Firma de una config atada a su VERSIÓN (dominio separado, anti-relabeleo)."""
    return _hmac(key, b"config", str(version).encode(), payload)
