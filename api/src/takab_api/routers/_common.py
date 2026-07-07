"""Helpers reutilizables de los routers REST (T-1.22 · fase 0).

Cimientos que comparten todos los routers por recurso:

- ``read_session``          — alias claro de ``get_session`` para rutas de solo lectura.
- ``http_error``            — construye ``HTTPException`` con cuerpo JSON consistente.
- paginación keyset         — ``encode_cursor``/``decode_cursor`` (token opaco base64url
                              de ``(campo_orden, id)``) + ``clamp_limit`` (≤100, default 50).

El cursor es opaco: el cliente lo trata como token ciego y lo devuelve tal cual. No
lleva firma —no expone datos sensibles ni concede acceso; RLS sigue filtrando cada
consulta—; solo transporta la posición ``(valor_de_orden, id)`` de la última fila.
"""

from __future__ import annotations

import base64
import binascii
import json

from fastapi import HTTPException

from takab_api.auth.deps import get_session

# Dependencia de solo lectura: misma sesión con rol takab_app + GUCs RLS del request.
read_session = get_session

# Tamaño de página keyset: default y tope duro.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


def http_error(status_code: int, detail: str) -> HTTPException:
    """Devuelve una ``HTTPException`` con cuerpo ``{"detail": ...}`` (uso: ``raise``).

    Uniforma el shape de error de toda la API; FastAPI serializa ``detail`` a JSON.
    """
    return HTTPException(status_code=status_code, detail=detail)


def clamp_limit(limit: int | None) -> int:
    """Normaliza el ``limit`` de una página a ``[1, MAX_PAGE_SIZE]`` (default 50)."""
    if limit is None:
        return DEFAULT_PAGE_SIZE
    if limit < 1:
        return 1
    return min(limit, MAX_PAGE_SIZE)


def encode_cursor(order_value: str, id_value: str) -> str:
    """Serializa la posición keyset ``(campo_orden, id)`` a un token opaco base64url."""
    raw = json.dumps([order_value, id_value], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    """Deserializa un cursor opaco → ``(campo_orden, id)``. 400 si está corrupto."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode())
        parsed = json.loads(raw)
        order_value, id_value = parsed
        if not isinstance(order_value, str) or not isinstance(id_value, str):
            raise ValueError("cursor: componentes no textuales")
    except (ValueError, binascii.Error, json.JSONDecodeError) as exc:
        raise http_error(400, "cursor inválido") from exc
    return order_value, id_value
