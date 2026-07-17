"""Endpoint WebSocket ``/ws`` (T-1.22 · B4, gate #5).

Auth por PRIMER mensaje ``{"type":"auth","token":"<id jwt>"}`` en ≤
``settings.ws_auth_timeout_s``; si no llega a tiempo o el token es inválido, se
cierra con code 4401. El token NO viaja por query string (fuga en logs) ni por
subprotocolo (lo mastican los proxies) — solo en el primer frame de aplicación.
Tras auth el servidor responde ``{"type":"ready"}`` y el cliente puede
``{"type":"subscribe","topic": "incidents"|"site_state"|"features:<site_id>"}``.

La suscripción respeta el MISMO gate que el REST equivalente: solo roles con
Consola C4I (RBAC §2) ven el canal live, y ``features:<site_id>`` respeta el
``site_scope`` default-deny del token. El token se re-chequea contra su ``exp``
mientras el socket vive (un token vencido deja de recibir, como en REST).
El fan-out lo hace el hub (LISTEN/NOTIFY + re-consulta RLS por suscriptor).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from takab_api.auth import deps
from takab_api.auth.claims import Claims, scope_filter
from takab_api.auth.matrix import CONSOLE, ROLE_ROUTE_MATRIX
from takab_api.auth.tokens import AuthError, decode_verify
from takab_api.ws import protocol as p
from takab_api.ws.hub import hub

router = APIRouter()

_WS_AUTH_FAILED = 4401

# Roles con Consola C4I (RBAC §2): autorizados en el canal live desde T-1.22.
_CONSOLE_ROLES = frozenset(r for r, routes in ROLE_ROUTE_MATRIX.items() if CONSOLE in routes)

# [T-2.08] Allowlist topic×rol DEFAULT-DENY (spec móvil §5.3). Los tácticos
# móvil-only entran al canal live para el dashboard 2.1 (RBAC §3 ``panel_read``)
# con los MISMOS topics de la consola, acotados a su site_scope en la entrega
# (hub) y con surface móvil verificada. El ``occupant`` queda FUERA del WS por
# construcción (push despertador + REST verdad): su token se cierra en el
# handshake — no hay sockets ociosos esperando topics que jamás tendrán.
_TACTICAL_WS_ROLES = frozenset({"brigadista", "security_guard"})
_LIVE_ROLES = _CONSOLE_ROLES | _TACTICAL_WS_ROLES
_TOPIC_ALLOWLIST: dict[str, frozenset[str]] = {
    p.TOPIC_INCIDENTS: _LIVE_ROLES,
    p.TOPIC_SITE_STATE: _LIVE_ROLES,
    p.TOPIC_FEATURES_PREFIX: _LIVE_ROLES,
}
_MOBILE_SURFACES = frozenset({"mobile", "both"})


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    """Canal live multiplexado por topic; auth por primer frame o close 4401."""
    await websocket.accept()
    settings = deps._settings()

    try:
        first = await asyncio.wait_for(websocket.receive_text(), timeout=settings.ws_auth_timeout_s)
    except (TimeoutError, WebSocketDisconnect, KeyError):
        # KeyError = frame binario en la fase de auth (receive_text espera 'text').
        await _close(websocket, _WS_AUTH_FAILED)
        return

    authed = _authenticate(first, settings)
    if authed is None:
        await _close(websocket, _WS_AUTH_FAILED)
        return
    claims, exp = authed

    # [T-2.08] Default-deny en el handshake: un rol sin NINGÚN topic posible
    # (occupant) se cierra aquí mismo — el canal live no mantiene sockets que
    # jamás podrán suscribirse (spec §5.3: occupant = push + REST).
    if claims.role not in _LIVE_ROLES:
        await _close(websocket, _WS_AUTH_FAILED)
        return

    await websocket.send_json(p.ReadyFrame().model_dump())
    sub = hub.register(websocket, claims)
    try:
        while True:
            # El token solo se valida en el handshake; re-chequeamos su exp para
            # que un socket con token vencido deje de recibir (como el REST 401).
            remaining = exp - time.time()
            if remaining <= 0:
                await _close(websocket, _WS_AUTH_FAILED)
                break
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=remaining)
            except TimeoutError:
                # Se alcanzó el exp del token sin frame entrante: cerrar.
                await _close(websocket, _WS_AUTH_FAILED)
                break
            except WebSocketDisconnect:
                break
            except KeyError:
                # Frame binario tras auth: no cerramos, respondemos error de protocolo.
                await websocket.send_json(
                    p.ErrorFrame(detail="se esperaba un frame de texto").model_dump()
                )
                continue
            await _handle(websocket, sub, raw)
    finally:
        await hub.unregister(sub)


def _authenticate(raw: str, settings: Any) -> tuple[Claims, float] | None:
    """Valida el frame ``auth`` → ``(Claims, exp)``; ``None`` ante cualquier fallo."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("type") != "auth":
        return None
    token = data.get("token")
    if not isinstance(token, str) or not token.strip():
        return None
    try:
        verified = decode_verify(token.strip(), settings, deps._jwks())
        claims = Claims.from_verified(verified)
        exp = float(verified.get("exp") or 0.0)
        return claims, exp
    except AuthError:
        return None


async def _handle(websocket: WebSocket, sub: Any, raw: str) -> None:
    """Procesa un frame del cliente (solo ``subscribe`` por ahora)."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        await websocket.send_json(p.ErrorFrame(detail="json inválido").model_dump())
        return
    if not isinstance(data, dict) or data.get("type") != "subscribe":
        await websocket.send_json(p.ErrorFrame(detail="tipo no soportado").model_dump())
        return
    topic = data.get("topic")
    if not _valid_topic(topic):
        await websocket.send_json(p.ErrorFrame(detail="topic inválido").model_dump())
        return
    denial = _authz_denial(sub, topic)
    if denial is not None:
        await websocket.send_json(p.ErrorFrame(detail=denial).model_dump())
        return
    await hub.subscribe(sub, topic)


def _authz_denial(sub: Any, topic: str) -> str | None:
    """``None`` si la suscripción está autorizada; si no, el motivo del rechazo.

    [T-2.08] Allowlist topic×rol DEFAULT-DENY: el rol debe estar en la lista
    del topic (un topic sin entrada niega a todos). Tácticos móviles además
    exigen surface móvil. ``features:<site_id>`` respeta el ``site_scope``
    default-deny y el tope de pollers. Espeja el authz del REST.
    """
    claims: Claims = sub.claims
    family = p.TOPIC_FEATURES_PREFIX if topic.startswith(p.TOPIC_FEATURES_PREFIX) else topic
    allowed_roles = _TOPIC_ALLOWLIST.get(family, frozenset())
    if claims.role not in allowed_roles:
        return "rol sin acceso al topic"
    if claims.role in _TACTICAL_WS_ROLES and claims.surface not in _MOBILE_SURFACES:
        return "superficie sin canal live"
    if topic.startswith(p.TOPIC_FEATURES_PREFIX):
        site_id = topic[len(p.TOPIC_FEATURES_PREFIX) :]
        allowed = scope_filter(claims)  # None = ALL_SITES (sin filtro)
        if allowed is not None and site_id not in allowed:
            return "sitio fuera del alcance (site_scope)"
        if topic not in sub.topics and len(sub.pollers) >= deps._settings().ws_max_feature_pollers:
            return "límite de suscripciones de features alcanzado"
    return None


def _valid_topic(topic: Any) -> bool:
    if not isinstance(topic, str):
        return False
    if topic in (p.TOPIC_INCIDENTS, p.TOPIC_SITE_STATE):
        return True
    if topic.startswith(p.TOPIC_FEATURES_PREFIX):
        suffix = topic[len(p.TOPIC_FEATURES_PREFIX) :]
        try:
            UUID(suffix)
        except ValueError:
            return False
        return True
    return False


async def _close(websocket: WebSocket, code: int) -> None:
    if websocket.application_state != WebSocketState.DISCONNECTED:
        try:
            await websocket.close(code=code)
        except RuntimeError:
            pass
