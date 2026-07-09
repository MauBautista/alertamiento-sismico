"""SQL de rule_sets (T-1.22 · B2). Versionado inmutable por alcance.

Un cambio de umbrales = fila NUEVA con ``version+1`` (UNIQUE por
``scope_type/scope_id/version``); la nueva queda ``is_active`` y las previas del
mismo alcance se apagan. RLS acota al tenant en cada statement.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import TextClause, text

_COLS = (
    "rule_set_id, tenant_id, scope_type, scope_id, version, is_active, config, "
    "created_by, created_at"
)


def select_rule_sets() -> tuple[TextClause, dict[str, Any]]:
    """rule_sets visibles (RLS = tenant propio): activos primero, versión desc."""
    sql = (
        f"SELECT {_COLS} FROM rule_sets ORDER BY is_active DESC, scope_type, scope_id, version DESC"
    )
    return text(sql), {}


def select_rule_set(rule_set_id: str) -> tuple[TextClause, dict[str, Any]]:
    """Un rule_set por id (RLS decide visibilidad)."""
    sql = f"SELECT {_COLS} FROM rule_sets WHERE rule_set_id = CAST(:id AS uuid)"
    return text(sql), {"id": rule_set_id}


# Tabla dueña de cada alcance: de ahí sale el tenant_id REAL del scope.
_SCOPE_OWNER = {
    "tenant": ("tenants", "tenant_id"),
    "site": ("sites", "site_id"),
    "sensor": ("sensors", "sensor_id"),
}


def select_scope_tenant(scope_type: str, scope_id: str) -> tuple[TextClause, dict[str, Any]]:
    """``tenant_id`` dueño del alcance. Sin fila ⇒ el alcance no existe (o RLS lo oculta).

    El INSERT fija ``tenant_id = claims.tenant_id`` pero el alcance lo elige el cuerpo:
    sin este chequeo una fila podía quedar con el tenant de A y el alcance de B, y el
    worker de sync (que resuelve por alcance, no por tenant) se la habría entregado a
    los gabinetes de B.
    """
    table, pk = _SCOPE_OWNER[scope_type]
    sql = f"SELECT tenant_id FROM {table} WHERE {pk} = CAST(:sid AS uuid)"
    return text(sql), {"sid": scope_id}


def select_active_scope(scope_type: str, scope_id: str) -> tuple[TextClause, dict[str, Any]]:
    """Versión ACTIVA del alcance (``version`` + ``config``). ``None`` si no hay.

    Base del control de concurrencia optimista y de la conservación de secretos:
    ``PUT`` reemplaza el blob entero, así que hay que saber contra qué se escribe.
    """
    sql = (
        "SELECT version, config FROM rule_sets "
        "WHERE scope_type = :st AND scope_id = CAST(:sid AS uuid) AND is_active = true "
        "ORDER BY version DESC LIMIT 1"
    )
    return text(sql), {"st": scope_type, "sid": scope_id}


def deactivate_scope(
    scope_type: str, scope_id: str, tenant_id: str
) -> tuple[TextClause, dict[str, Any]]:
    """Apaga las versiones activas del alcance antes de insertar la nueva.

    El filtro por ``tenant_id`` es defensa en profundidad: los roles internos
    (``rule_sets_admin``) bypasean RLS y sin él podían apagar los rule_sets activos
    de un tenant ajeno.
    """
    sql = (
        "UPDATE rule_sets SET is_active = false "
        "WHERE scope_type = :st AND scope_id = CAST(:sid AS uuid) "
        "AND tenant_id = CAST(:tenant AS uuid) AND is_active = true"
    )
    return text(sql), {"st": scope_type, "sid": scope_id, "tenant": tenant_id}


def insert_new_version(
    *,
    tenant_id: str,
    scope_type: str,
    scope_id: str,
    config: str,
    created_by: str,
) -> tuple[TextClause, dict[str, Any]]:
    """Inserta la nueva versión activa (``MAX(version)+1`` del alcance) y la devuelve."""
    sql = (
        "INSERT INTO rule_sets "
        "(tenant_id, scope_type, scope_id, version, is_active, config, created_by) "
        "SELECT CAST(:tenant AS uuid), :st, CAST(:sid AS uuid), "
        "COALESCE((SELECT MAX(version) FROM rule_sets r "
        "          WHERE r.scope_type = :st AND r.scope_id = CAST(:sid AS uuid)), 0) + 1, "
        "true, CAST(:config AS jsonb), CAST(:created_by AS uuid) "
        f"RETURNING {_COLS}"
    )
    return text(sql), {
        "tenant": tenant_id,
        "st": scope_type,
        "sid": scope_id,
        "config": config,
        "created_by": created_by,
    }
