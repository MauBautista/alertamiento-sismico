"""T-1.17 · soporte de ingesta: índices únicos de idempotencia

SQS entrega at-least-once: los handlers de ingesta necesitan poder hacer
``INSERT ... ON CONFLICT DO NOTHING`` sobre una clave natural (regla de oro 3).

  * ``incident_actions``: un ActuatorAck re-entregado se identifica por
    (incident_id, kind, actor, ts) — mismo incidente, misma acción, mismo
    emisor, mismo instante de ejecución. Índice único ``uq_incident_actions_ack``.
  * ``evidence_objects``: dedup de evidencia por contenido — índice único
    PARCIAL ``uq_evidence_incident_sha256`` sobre (incident_id, sha256)
    WHERE sha256 IS NOT NULL (las filas sin hash no participan).

Los triggers append-only de ambas tablas solo bloquean UPDATE/DELETE: crear
índices es legal y no toca filas.

Revision ID: 0002_ingest_support
Revises: 0001_initial_schema
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_ingest_support"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Como en 0001: los objetos se crean bajo takab_migrator (dueño de las
    # tablas), de modo que `downgrade base` (DROP OWNED) también los barre.
    op.execute("SET ROLE takab_migrator")
    op.execute(
        "CREATE UNIQUE INDEX uq_incident_actions_ack "
        "ON incident_actions (incident_id, kind, actor, ts)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_evidence_incident_sha256 "
        "ON evidence_objects (incident_id, sha256) WHERE sha256 IS NOT NULL"
    )
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET ROLE takab_migrator")
    op.execute("DROP INDEX IF EXISTS uq_evidence_incident_sha256")
    op.execute("DROP INDEX IF EXISTS uq_incident_actions_ack")
    op.execute("RESET ROLE")
