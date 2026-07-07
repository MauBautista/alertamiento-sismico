"""T-1.21 · notification_jobs: cola durable de la cascada de notificación.

Un job por (incidente, canal, modo): UNIQUE = idempotencia del enqueue (re-run
del pass ⇒ ON CONFLICT DO NOTHING). ``mode``: 'cascade' (secuencial escalonada
por ``position``/``due_at``) o 'parallel' (email crítico <10 s; fail-open de
sitio SIN ENLACE = todos los canales). ``target`` NUNCA lleva secretos (el HMAC
del webhook se re-resuelve del rule_set al despachar).

RLS espejo de ``incidents`` en LECTURA (tenant + internal + gov_shared); SIN
policy de escritura de tenant: los jobs los crea/actualiza SOLO el worker
``takab_ingest`` (BYPASSRLS). takab_app recibe SOLO SELECT (los GRANT de 0001
son "ON ALL TABLES" al momento de la 0001; las tablas nuevas los declaran).

Revision ID: 0005_notification_jobs
Revises: 0004_live_notify
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_notification_jobs"
down_revision: str | None = "0004_live_notify"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
CREATE TABLE notification_jobs (
  job_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants,
  incident_id uuid NOT NULL REFERENCES incidents ON DELETE RESTRICT,
  channel     text NOT NULL CHECK (channel IN ('webhook','whatsapp','sms','email')),
  mode        text NOT NULL CHECK (mode IN ('cascade','parallel')),
  position    int  NOT NULL DEFAULT 0,
  status      text NOT NULL DEFAULT 'pending'
              CHECK (status IN ('pending','sent','failed','skipped')),
  target      jsonb NOT NULL DEFAULT '{}',
  due_at      timestamptz NOT NULL,
  deadline_at timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now(),
  sent_at     timestamptz,
  error       text,
  UNIQUE (incident_id, channel, mode)
);

CREATE INDEX idx_notification_jobs_due
  ON notification_jobs (due_at) WHERE status = 'pending';
CREATE INDEX idx_notification_jobs_tenant
  ON notification_jobs (tenant_id, created_at DESC);

ALTER TABLE notification_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_jobs FORCE  ROW LEVEL SECURITY;
CREATE POLICY notification_jobs_read ON notification_jobs FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR app_gov_can_see(tenant_id));
CREATE POLICY notification_jobs_admin ON notification_jobs FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

GRANT SELECT ON notification_jobs TO takab_app;
GRANT SELECT, INSERT, UPDATE ON notification_jobs TO takab_ingest;
"""

_DOWN = """
DROP TABLE IF EXISTS notification_jobs;
"""


def _exec(sql: str) -> None:
    """SQL por el cursor psycopg crudo (sin binding) — patrón de 0003/0004."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_UP)


def downgrade() -> None:
    _exec(_DOWN)
