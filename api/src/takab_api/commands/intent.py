"""Intención firmada del operador móvil (T-2.09 · spec §2.1-B / RBAC §4.3).

El teléfono JAMÁS firma el comando ejecutable: firma una INTENCIÓN
``{key_id, sitio, canal, acción, nonce del servidor}`` con su llave respaldada
por hardware (``device_keys``). La nube la verifica y construye el comando
HMAC por el pipeline existente (``issue_signed_command``).

El nonce es STATELESS: HMAC del servidor sobre ``sub|sitio|exp|rand`` con TTL
corto — atado al operador Y al sitio (no se puede trasplantar). Su UN SOLO USO
no necesita tabla: el nonce de la intención viaja como ``commands.nonce``
(UNIQUE) del comando emitido, así que el replay revienta en el INSERT.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.serialization import load_pem_public_key

#: Versión del string canónico — el móvil construye EXACTAMENTE este formato.
INTENT_V1 = "takab-intent-v1"


def canonical_intent(*, key_id: str, site_id: str, channel: str, action: str, nonce: str) -> bytes:
    """Mensaje firmado por el teléfono. Cambiarlo = versionar (v2), jamás mutarlo."""
    return f"{INTENT_V1}:{key_id}:{site_id}:{channel}:{action}:{nonce}".encode()


def _mac(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]


def mint_nonce(
    secret: str, *, sub: str, site_id: str, ttl_s: float, now: datetime
) -> tuple[str, datetime]:
    """Nonce de intención: se pide JUSTO antes del deslizamiento (spec 2.2)."""
    expires = now + timedelta(seconds=ttl_s)
    body = f"{sub}|{site_id}|{int(expires.timestamp())}|{secrets.token_hex(8)}"
    raw = f"{body}|{_mac(secret, body)}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("="), expires


def nonce_error(secret: str, nonce: str, *, sub: str, site_id: str, now: datetime) -> str | None:
    """``None`` si el nonce es del servidor, del MISMO operador/sitio y vigente."""
    try:
        padded = nonce + "=" * (-len(nonce) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        body, mac = raw.rsplit("|", 1)
        n_sub, n_site, n_exp, _rand = body.split("|")
    except (ValueError, UnicodeDecodeError):
        return "nonce ilegible"
    if not hmac.compare_digest(mac, _mac(secret, body)):
        return "nonce no emitido por el servidor"
    if n_sub != sub:
        return "nonce de otro operador"
    if n_site != site_id:
        return "nonce de otro sitio"
    if int(n_exp) < int(now.timestamp()):
        return "nonce vencido"
    return None


def intent_signature_valid(public_key_pem: str, signature_b64: str, message: bytes) -> bool:
    """Verifica la firma contra la llave REGISTRADA (device_keys).

    Acepta P-256/ECDSA (Secure Enclave/Keystore vía EC) y RSA PKCS#1 v1.5
    (Android Keystore vía react-native-biometrics), ambas con SHA-256.
    """
    try:
        key = load_pem_public_key(public_key_pem.encode())
        signature = base64.b64decode(signature_b64, validate=True)
    except (ValueError, TypeError):
        return False
    try:
        if isinstance(key, ec.EllipticCurvePublicKey):
            key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        elif isinstance(key, rsa.RSAPublicKey):
            key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
        else:
            return False
    except InvalidSignature:
        return False
    return True


def intent_sha256(signature_b64: str) -> str:
    """Huella de la firma de intención para el audit (spec 2.2)."""
    return hashlib.sha256(signature_b64.encode()).hexdigest()
