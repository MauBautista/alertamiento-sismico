"""T-1.32 · sites.status: retiro lógico de un sitio

``gateways`` y ``sensors`` ya nacieron con ``status``; ``sites`` no. El CRUD de flota
retira un sitio en vez de borrarlo (regla de oro 11: la evidencia y la auditoría de un
incidente jamás pueden quedar huérfanas de su sitio), así que la columna es el único
DDL que falta para cerrar la mitad de escritura de US-20.

``DEFAULT 'active'`` hace que las filas existentes queden activas sin backfill.

Revision ID: 0009_site_status
Revises: 0008_cagg_secure_views
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_site_status"
down_revision: str | None = "0008_cagg_secure_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE sites ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active'")
    # CHECK aparte del ADD COLUMN: si la columna ya existía (re-run), el constraint
    # se crea igual y la migración sigue siendo idempotente.
    op.execute(
        "ALTER TABLE sites DROP CONSTRAINT IF EXISTS sites_status_check;"
        "ALTER TABLE sites ADD CONSTRAINT sites_status_check "
        "CHECK (status IN ('active','retired'))"
    )
    # El mapa y el catálogo filtran por status; el índice parcial sirve al caso común.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sites_active ON sites (tenant_id) WHERE status = 'active'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sites_active")
    op.execute("ALTER TABLE sites DROP CONSTRAINT IF EXISTS sites_status_check")
    op.execute("ALTER TABLE sites DROP COLUMN IF EXISTS status")
