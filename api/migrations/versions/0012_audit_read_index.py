"""T-1.57 · Índices keyset de lectura de ``audit_log``.

``GET /audit`` pagina por ``(ts DESC, audit_id DESC)`` y hoy la tabla solo tiene
el PK: cada página sería un scan completo. Dos índices, cero cambios de datos:

1. ``(ts DESC, audit_id DESC)`` — el orden exacto del keyset (roles internos,
   que ven todo).
2. ``(tenant_id, ts DESC)`` — el acceso típico de un tenant_admin/gov (la RLS
   ``audit_read`` filtra por ``tenant_id = app_tenant_id()``).

Sin políticas nuevas: la RLS de lectura EXISTE desde el schema consolidado
(``audit_read``); esta migración es solo de índices. Idempotente
(``IF NOT EXISTS`` / ``IF EXISTS``) — invariante de T-1.45: 0001 aplica el
schema.sql FINAL, así que 0012 debe poder correr sobre una base donde los
índices ya existen.

Revision ID: 0012_audit_read_index
Revises: 0011_soc_polish
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_audit_read_index"
down_revision: str | None = "0011_soc_polish"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
CREATE INDEX IF NOT EXISTS idx_audit_log_ts_id ON audit_log (ts DESC, audit_id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_ts ON audit_log (tenant_id, ts DESC);
"""

_DOWN = """
DROP INDEX IF EXISTS idx_audit_log_tenant_ts;
DROP INDEX IF EXISTS idx_audit_log_ts_id;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
