"""security — verificación de comandos firmados + config firmada (anti-replay).

T-1.12: verifica comandos remotos firmados con **HMAC + nonce de un solo uso + ventana
temporal corta** (regla de oro 8: "JWT corto"; rechaza no firmado, repetido o expirado)
y verifica **actualizaciones de config firmadas** (aplicadas versionadas y reversibles por
`ConfigStore`). El nonce-store se poda por expiración (no crece sin límite). La clave se
inyecta (Secrets Manager/env); NUNCA se hardcodea (CLAUDE.md §2.6). El mTLS/X.509 por
gateway (identidad de dispositivo) lo provisiona Terraform (gate AWS, T-1.15).
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from hashlib import sha256

from takab_edge.contracts import utcnow
from takab_edge.module import EdgeModule

log = logging.getLogger("takab_edge.security")


class SecurityManager(EdgeModule):
    """Verifica firmas de comandos/config y consume nonces (un solo uso, con expiración)."""

    name = "security"

    def __init__(
        self,
        hmac_key: bytes,
        command_ttl_s: float = 30.0,
        clock_skew_s: float = 5.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__()
        if not hmac_key:
            raise ValueError("hmac_key vacía: inyecta la clave desde Secrets Manager/env")
        self._key = hmac_key
        self._command_ttl_s = command_ttl_s
        self._clock_skew_s = clock_skew_s  # tolerancia de reloj hacia el futuro
        self._clock = clock or utcnow
        self._nonces: dict[str, datetime] = {}  # nonce → timestamp (para poda por expiración)

    @staticmethod
    def _frame(*parts: bytes) -> bytes:
        # Codificación canónica length-prefixed: cada campo lleva su longitud (8 bytes) antes,
        # así los límites son inequívocos y ni los dominios (command/config) ni los campos
        # (nonce/timestamp/payload) pueden aliasar por entradas patológicas con separadores.
        out = bytearray()
        for part in parts:
            out += len(part).to_bytes(8, "big") + part
        return bytes(out)

    def _hmac(self, *parts: bytes) -> str:
        return hmac.new(self._key, self._frame(*parts), sha256).hexdigest()

    @staticmethod
    def _safe_equal(expected: str, signature: str) -> bool:
        try:
            return hmac.compare_digest(expected, signature)
        except (TypeError, ValueError):
            return False  # firma malformada (no-ASCII/tipo) → rechazo, nunca excepción

    # --- Comandos remotos firmados ---
    def sign(self, payload: bytes, nonce: str, timestamp: datetime) -> str:
        """Firma sobre (dominio, nonce, timestamp, payload). La nube firma igual (T-1.23)."""
        return self._hmac(b"command", nonce.encode(), timestamp.isoformat().encode(), payload)

    def verify_command(
        self, payload: bytes, nonce: str, signature: str, timestamp: datetime
    ) -> bool:
        """True sólo si firma válida, nonce sin usar y dentro de la ventana temporal."""
        if not signature or not nonce:
            log.warning("comando rechazado: sin firma o nonce")
            return False
        now = self._clock()
        delta = (now - timestamp).total_seconds()  # >0 pasado, <0 futuro
        if delta > self._command_ttl_s or delta < -self._clock_skew_s:
            log.warning("comando rechazado: fuera de ventana (Δ=%.0fs)", delta)
            return False
        self._prune_nonces(now)
        if nonce in self._nonces:
            log.warning("comando rechazado: nonce repetido (replay)")
            return False
        if not self._safe_equal(self.sign(payload, nonce, timestamp), signature):
            log.warning("comando rechazado: firma inválida")
            return False
        self._nonces[nonce] = timestamp
        return True

    def _prune_nonces(self, now: datetime) -> None:
        # Un comando más viejo que el TTL ya se rechaza por ventana → olvidar su nonce es
        # seguro (un replay caería por ventana igual). Mantiene el store acotado.
        cutoff = now - timedelta(seconds=self._command_ttl_s)
        for nonce in [n for n, ts in self._nonces.items() if ts < cutoff]:
            del self._nonces[nonce]

    # --- Config firmada ---
    def sign_config(self, payload: bytes, version: int) -> str:
        """Firma de una config atada a su VERSIÓN (dominio separado del de comandos)."""
        return self._hmac(b"config", str(version).encode(), payload)

    def verify_config(self, payload: bytes, signature: str, version: int) -> bool:
        """True sólo si la firma cubre EXACTAMENTE (payload, version) — anti-relabeleo."""
        if not signature:
            log.warning("config rechazada: sin firma")
            return False
        return self._safe_equal(self.sign_config(payload, version), signature)

    def _on_start(self) -> None:
        log.info("gestor de seguridad activo (ventana de comando %.0fs)", self._command_ttl_s)
