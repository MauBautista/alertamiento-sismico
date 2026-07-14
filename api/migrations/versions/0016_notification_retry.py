"""T-1.62 · Reintento acotado de notificaciones (un fallo dejaba de ser final).

Un ``AccessDenied`` de SES dejó un ``dictamen_request`` REAL sin correo y sin
retorno: el job quedaba ``failed`` para siempre, el re-encolado lo daba por
atendido (``NOT EXISTS ... action_id``, sin mirar el estado) y el 409 de
``POST /incidents/{id}/dictamen-request`` impedía volver a pedirlo. Un fallo
transitorio del proveedor equivalía a silencio permanente.

``attempts`` cuenta los envíos ya intentados. El orquestador reintenta con
backoff (30 s / 2 min) SOLO cuando el job no tiene a quién escalar — los saltos
de cascada con siguiente canal siguen fallando en el acto (reintentar ahí
retrasaría llegar al humano).

Idempotente (IF NOT EXISTS / IF EXISTS) — invariante de T-1.45.

Revision ID: 0016_notification_retry
Revises: 0015_drills
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016_notification_retry"
down_revision: str | None = "0015_drills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
ALTER TABLE notification_jobs
  ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0;
"""

_DOWN = """
ALTER TABLE notification_jobs DROP COLUMN IF EXISTS attempts;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
