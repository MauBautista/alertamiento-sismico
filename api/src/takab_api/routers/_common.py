"""Helpers reutilizables de los routers REST (T-1.22 · fase 0).

Cimientos que comparten todos los routers por recurso:

- ``read_session``          — alias claro de ``get_session`` para rutas de solo lectura.
- ``http_error``            — construye ``HTTPException`` con cuerpo JSON consistente.
- paginación keyset         — ``encode_cursor``/``decode_cursor`` (token opaco base64url
                              de ``(campo_orden, id)``) + ``clamp_limit`` (≤100, default 50).
- escritura con tenancy     — ``resolve_write_tenant`` / ``require_same_tenant`` /
                              ``integrity_error`` (T-1.32).

El cursor es opaco: el cliente lo trata como token ciego y lo devuelve tal cual. No
lleva firma —no expone datos sensibles ni concede acceso; RLS sigue filtrando cada
consulta—; solo transporta la posición ``(valor_de_orden, id)`` de la última fila.
"""

from __future__ import annotations

import base64
import binascii
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import TextClause, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session

# Dependencia de solo lectura: misma sesión con rol takab_app + GUCs RLS del request.
read_session = get_session

# Roles internos TAKAB: sus políticas ``*_admin`` llevan ``WITH CHECK
# (app_is_takab_internal())`` SIN filtro de tenant, así que la DB no los detendría
# al escribir en un tenant ajeno. Para ellos el ``tenant_id`` debe ser explícito.
INTERNAL_ROLES = frozenset({"takab_superadmin", "takab_support"})

_TENANT_EXISTS = text("SELECT 1 FROM tenants WHERE tenant_id = CAST(:t AS uuid)")

# Dueño de una fila referenciada por FK. Las FK de PostgreSQL NO comparan
# ``tenant_id``: sin esta comprobación un admin podría colgar un gabinete suyo del
# sitio de otro tenant (mismo patrón de fuga que cerró T-1.30 en ``rule_sets``).
_OWNER_SQL: dict[str, TextClause] = {
    "sites": text("SELECT tenant_id FROM sites WHERE site_id = CAST(:id AS uuid)"),
    "gateways": text("SELECT tenant_id FROM gateways WHERE gateway_id = CAST(:id AS uuid)"),
    "zones": text("SELECT tenant_id FROM zones WHERE zone_id = CAST(:id AS uuid)"),
}


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


# --- Escritura con tenancy (T-1.32) -------------------------------------------


async def resolve_write_tenant(
    conn: AsyncConnection, claims: Claims, body_tenant_id: UUID | None
) -> str:
    """``tenant_id`` de una fila nueva. Para roles no internos NUNCA sale del cuerpo.

    Un rol de tenant escribe siempre en el suyo (si el cuerpo pide otro ⇒ 403). Un rol
    interno TAKAB debe nombrarlo explícitamente, porque su política RLS le dejaría
    insertar en cualquiera y el default silencioso (su propio ``tenant_id`` de claims)
    crearía sitios en un tenant equivocado.
    """
    if claims.role in INTERNAL_ROLES:
        if body_tenant_id is None:
            raise http_error(400, "tenant_id es obligatorio para roles internos TAKAB")
        exists = (await conn.execute(_TENANT_EXISTS, {"t": str(body_tenant_id)})).first()
        if exists is None:
            raise http_error(404, "tenant no encontrado")
        return str(body_tenant_id)
    if body_tenant_id is not None and str(body_tenant_id) != claims.tenant_id:
        raise http_error(403, "no puedes escribir en otro tenant")
    return claims.tenant_id


async def owner_tenant(conn: AsyncConnection, *, table: str, row_id: UUID, label: str) -> str:
    """``tenant_id`` de la fila referenciada. 404 si no existe o RLS la oculta."""
    row = (await conn.execute(_OWNER_SQL[table], {"id": str(row_id)})).first()
    if row is None:
        raise http_error(404, f"{label} no encontrado")
    return str(row.tenant_id)


async def require_same_tenant(
    conn: AsyncConnection, *, table: str, row_id: UUID, tenant_id: str, label: str
) -> None:
    """404 si la fila referenciada no existe/no es visible; 403 si es de otro tenant."""
    if await owner_tenant(conn, table=table, row_id=row_id, label=label) != str(tenant_id):
        raise http_error(403, f"{label} pertenece a otro tenant")


async def tenant_of_parent_site(conn: AsyncConnection, claims: Claims, site_id: UUID) -> str:
    """Tenant que hereda un gabinete/sensor de su sitio padre.

    Nunca se toma del cuerpo: derivarlo del sitio hace imposible colgar hardware de un
    tenant en el sitio de otro. Para un rol de tenant, RLS ya oculta los sitios ajenos
    (⇒ 404); la comparación explícita es defensa en profundidad por si una política
    futura ampliara la lectura.
    """
    tenant_id = await owner_tenant(conn, table="sites", row_id=site_id, label="sitio")
    if claims.role not in INTERNAL_ROLES and tenant_id != claims.tenant_id:
        raise http_error(403, "el sitio pertenece a otro tenant")
    return tenant_id


def integrity_error(exc: IntegrityError) -> HTTPException:
    """Traduce una violación de restricción a 4xx (nunca un 500).

    Un serial repetido o un ``code`` ya usado en el tenant es un error del operador,
    no del servidor: la consola debe poder decírselo. Cualquier otra violación se
    re-lanza — un 500 honesto es mejor que un 4xx inventado.
    """
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if sqlstate == "23505":  # unique_violation
        return http_error(409, "ya existe un registro con ese identificador único")
    if sqlstate == "23503":  # foreign_key_violation
        return http_error(400, "referencia inexistente")
    if sqlstate == "23514":  # check_violation
        return http_error(400, "valor fuera del dominio permitido")
    raise exc
