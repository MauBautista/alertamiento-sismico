"""Tope ABSOLUTO de sesión por rol (T-8.02 · D-38).

La sesión termina en ``auth_time + SESSION_MAX_AGE_S[role]``, pase lo que pase con
el refresco: ``auth_time`` es la hora en que la persona tecleó contraseña y código,
y Cognito la conserva al refrescar. ``iat`` NO sirve de sustituto —se renueva en
cada refresco— y con él la sesión no caducaría nunca.

Por qué vive en la API y no en Cognito: la vida del refresh token es una propiedad
del **app client**, no del rol, y el cliente web lo comparten roles de 24 h (SOC) y
de 30 d (inspector). Cognito da el techo (30 d / 90 d); la API da el tope por rol.

Contrato con los clientes (fijo entre carriles):

- REST ⇒ ``401`` · ``{"detail": "sesion_expirada"}`` · ``WWW-Authenticate: Bearer
  error="invalid_token", error_description="sesion_expirada"`` (``auth/deps.py``).
- WS ⇒ cierre ``4440`` (``routers/ws.py``). ``4401`` sigue siendo «token inválido
  o vencido» (renovable); ``4440`` NO es renovable.

Default-deny: un rol sin entrada en la tabla tiene la sesión caducada desde el
primer segundo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from takab_api.auth.matrix import SESSION_MAX_AGE_S
from takab_api.auth.tokens import AuthError

if TYPE_CHECKING:
    from takab_api.auth.claims import Claims

#: Motivo del 401 (y ``error_description`` del reto). Es contrato con web y móvil.
SESSION_EXPIRED = "sesion_expirada"


class SessionExpired(AuthError):
    """La sesión llegó a su tope. 401, NO renovable (renovar no mueve ``auth_time``)."""

    def __init__(self) -> None:
        super().__init__(SESSION_EXPIRED)


def session_max_age_s(role: str) -> int | None:
    """Edad máxima de la sesión del rol; ``None`` si el rol no está en la tabla."""
    return SESSION_MAX_AGE_S.get(role)


def session_deadline(claims: Claims) -> int | None:
    """Epoch (s) en que termina la sesión; ``None`` = rol desconocido (ya caducada)."""
    max_age = session_max_age_s(claims.role)
    if max_age is None:
        return None
    return claims.auth_time + max_age


def enforce_session_age(claims: Claims, now: float) -> None:
    """Lanza ``SessionExpired`` si ``now >= plazo`` o si el rol no tiene tope."""
    deadline = session_deadline(claims)
    if deadline is None or now >= deadline:
        raise SessionExpired()
