"""security — verificación de comandos firmados + store de nonces (anti-replay).

Scaffold de T-1.2: verificación HMAC de comandos remotos con nonce de un solo uso
(rechaza comando no firmado o repetido). El mTLS/X.509 por gateway, la config
entrante por **JWT firmado** y la rotación de credenciales sin downtime son
**T-1.12**. La clave se inyecta (Secrets Manager/env); NUNCA se hardcodea
(CLAUDE.md §2.6).
"""

from __future__ import annotations

import hmac
import logging
from hashlib import sha256

from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.security")


class SecurityManager(EdgeModule):
    """Verifica firmas de comandos y consume nonces (un solo uso)."""

    name = "security"

    def __init__(self, hmac_key: bytes) -> None:
        super().__init__()
        if not hmac_key:
            raise ValueError("hmac_key vacía: inyecta la clave desde Secrets Manager/env")
        self._key = hmac_key
        self._used_nonces: set[str] = set()

    def sign(self, payload: bytes, nonce: str) -> str:
        """Firma de referencia (la contraparte cloud firma igual — T-1.23)."""
        return hmac.new(self._key, nonce.encode() + b"." + payload, sha256).hexdigest()

    def verify_command(self, payload: bytes, nonce: str, signature: str) -> bool:
        """True sólo si la firma es válida y el nonce no se ha usado antes."""
        if not signature or not nonce:
            return False
        if nonce in self._used_nonces:
            log.warning("comando rechazado: nonce repetido (replay)")
            return False
        expected = self.sign(payload, nonce)
        if not hmac.compare_digest(expected, signature):
            log.warning("comando rechazado: firma inválida")
            return False
        self._used_nonces.add(nonce)
        return True

    def _on_start(self) -> None:
        log.info("gestor de seguridad activo")
