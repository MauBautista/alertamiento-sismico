"""T-1.61 · Jobs de notificación por ACCIÓN (dictamen_request → inspector).

``notification_jobs`` solo conocía incidentes: la UNIQUE ``(incident_id,
channel, mode)`` haría colisionar el email al inspector con el email de la
cascada del MISMO incidente. Se añade ``action_id`` (FK a incident_actions) y
la unicidad se divide en dos índices PARCIALES:

- ``(incident_id, channel, mode) WHERE action_id IS NULL`` — la clave original,
  intacta para los jobs de incidente (el ON CONFLICT del orquestador apunta a
  este índice parcial).
- ``(action_id, channel) WHERE action_id IS NOT NULL`` — exactamente 1 job por
  acción y canal: re-runs del pass y re-entregas NOTIFY no duplican.

Idempotente (IF NOT EXISTS / IF EXISTS) — invariante de T-1.45.

Revision ID: 0014_notification_jobs_action
Revises: 0013_command_self_test
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014_notification_jobs_action"
down_revision: str | None = "0013_command_self_test"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
ALTER TABLE notification_jobs
  ADD COLUMN IF NOT EXISTS action_id uuid REFERENCES incident_actions(action_id);
ALTER TABLE notification_jobs
  DROP CONSTRAINT IF EXISTS notification_jobs_incident_id_channel_mode_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_jobs_incident
  ON notification_jobs (incident_id, channel, mode) WHERE action_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_notification_jobs_action
  ON notification_jobs (action_id, channel) WHERE action_id IS NOT NULL;
"""

# El downgrade restaura la UNIQUE original; fallaría con jobs de acción
# presentes — correcto: no se degrada un schema con datos que ya no caben.
_DOWN = """
DROP INDEX IF EXISTS uq_notification_jobs_action;
DROP INDEX IF EXISTS uq_notification_jobs_incident;
ALTER TABLE notification_jobs DROP COLUMN IF EXISTS action_id;
ALTER TABLE notification_jobs
  ADD CONSTRAINT notification_jobs_incident_id_channel_mode_key
  UNIQUE (incident_id, channel, mode);
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
