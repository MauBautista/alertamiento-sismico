"""T-9.03 · la escalada RE-NOTIFICA a todo el edificio: UNA escalada por incidente

## El defecto, medido en el gabinete real (2026-09-24)

El incidente nace `local_threshold` —una estación sola, que solo ADVIERTE— y el WR-1
de SASMEX lo escala segundos después en el mismo episodio. La app ya ordenaba evacuar
al re-leer su estado, pero el teléfono dormido no se enteraba: el orquestador solo
planificaba incidentes SIN jobs, y `uq_notification_jobs_incident` (incident,
channel, mode) impedía un segundo push de incidente.

## Lo que añade esta migración

El orquestador deja en la bitácora un verbo nuevo, `alert_escalated`, y ancla a su
`action_id` el push CRISIS de la escalada (idempotente por
`uq_notification_jobs_action`). Aquí solo se pone el candado de la base: **una
escalada por incidente**. `kind` es texto libre (sin CHECK) y la tabla es
append-only, así que el único sitio donde «una sola vez» deja de ser costumbre del
worker es un índice único parcial.

Un índice hereda el dueño de su tabla (`takab_migrator`); se crea con ese rol, como
`uq_ref_eq_provider_event` en la 0068. Idempotente: `IF NOT EXISTS`.

Revision ID: 0070_escalada_avisa_a_todos
Revises: 0069_mapa_de_sacudida
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0070_escalada_avisa_a_todos"
down_revision: str | None = "0069_mapa_de_sacudida"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
SET ROLE takab_migrator;

CREATE UNIQUE INDEX IF NOT EXISTS uq_incident_actions_escalada
  ON incident_actions (incident_id) WHERE kind = 'alert_escalated';

RESET ROLE;
"""

_DOWN = """
DROP INDEX IF EXISTS uq_incident_actions_escalada;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWN)
