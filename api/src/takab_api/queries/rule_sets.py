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


def deactivate_scope(scope_type: str, scope_id: str) -> tuple[TextClause, dict[str, Any]]:
    """Apaga las versiones activas del alcance antes de insertar la nueva."""
    sql = (
        "UPDATE rule_sets SET is_active = false "
        "WHERE scope_type = :st AND scope_id = CAST(:sid AS uuid) AND is_active = true"
    )
    return text(sql), {"st": scope_type, "sid": scope_id}


def insert_publish_audit(
    *, tenant_id: str, actor: str, rule_set_id: str, version: int
) -> tuple[TextClause, dict[str, Any]]:
    """Deja la intención de publicación en ``audit_log`` (sync real = T-1.23)."""
    sql = (
        "INSERT INTO audit_log (tenant_id, actor, verb, object, meta) "
        "VALUES (CAST(:tenant AS uuid), :actor, 'rule_set_publish', :object, "
        "CAST(:meta AS jsonb))"
    )
    return text(sql), {
        "tenant": tenant_id,
        "actor": actor,
        "object": f"rule_set:{rule_set_id}",
        "meta": f'{{"version": {version}, "status": "pending_sync"}}',
    }


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
