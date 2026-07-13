"""T-1.60 · Modo SIMULACRO institucional (drills) — cierra M-1.

Un simulacro JAMÁS toca ``incidents`` (cero contaminación de reportes y del
incident engine): registro propio ``drills`` + participación por sitio en
``drill_sites``. El acuse de cada sitio NO se duplica — se deriva por JOIN
``drill_sites.command_id → commands.status/ack`` (el ack del ``drill_start``
transiciona por la ingesta existente). El estado ``active`` es DERIVADO
(``stopped_at IS NULL AND now() < started_at + duration_s``): sin worker de
cierre.

RLS: ``tenant_id`` en ambas tablas; **gov LEE** (``app_gov_can_see`` — el
registro es la evidencia para Protección Civil) pero no escribe. CHECKs de
``commands`` amplían las acciones con ``drill_start``/``drill_stop``.

Idempotente (IF NOT EXISTS / DROP POLICY IF EXISTS) — invariante de T-1.45.

Revision ID: 0015_drills
Revises: 0014_notification_jobs_action
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015_drills"
down_revision: str | None = "0014_notification_jobs_action"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
ALTER TABLE commands DROP CONSTRAINT IF EXISTS commands_action_check;
ALTER TABLE commands ADD CONSTRAINT commands_action_check
  CHECK (action IN ('activate','deactivate','self_test','drill_start','drill_stop'));

CREATE TABLE IF NOT EXISTS drills (
  drill_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  initiated_by uuid NOT NULL,
  note         text,
  duration_s   integer NOT NULL CHECK (duration_s BETWEEN 30 AND 3600),
  started_at   timestamptz NOT NULL DEFAULT now(),
  stopped_at   timestamptz,
  stop_reason  text
);
CREATE INDEX IF NOT EXISTS idx_drills_tenant ON drills (tenant_id, started_at DESC);

CREATE TABLE IF NOT EXISTS drill_sites (
  drill_id   uuid NOT NULL REFERENCES drills(drill_id),
  site_id    uuid NOT NULL REFERENCES sites(site_id),
  tenant_id  uuid NOT NULL REFERENCES tenants(tenant_id),
  command_id uuid REFERENCES commands(command_id),
  PRIMARY KEY (drill_id, site_id)
);

GRANT SELECT, INSERT, UPDATE ON drills TO takab_app;
GRANT SELECT, INSERT ON drill_sites TO takab_app;
GRANT SELECT ON drills, drill_sites TO takab_ingest;

ALTER TABLE drills ENABLE ROW LEVEL SECURITY;
ALTER TABLE drills FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS drills_read ON drills;
CREATE POLICY drills_read ON drills FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR app_gov_can_see(tenant_id));
DROP POLICY IF EXISTS drills_write ON drills;
CREATE POLICY drills_write ON drills FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
DROP POLICY IF EXISTS drills_admin ON drills;
CREATE POLICY drills_admin ON drills FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

ALTER TABLE drill_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE drill_sites FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS drill_sites_read ON drill_sites;
CREATE POLICY drill_sites_read ON drill_sites FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR app_gov_can_see(tenant_id));
DROP POLICY IF EXISTS drill_sites_write ON drill_sites;
CREATE POLICY drill_sites_write ON drill_sites FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
DROP POLICY IF EXISTS drill_sites_admin ON drill_sites;
CREATE POLICY drill_sites_admin ON drill_sites FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());
"""

_DOWN = """
DROP TABLE IF EXISTS drill_sites;
DROP TABLE IF EXISTS drills;
ALTER TABLE commands DROP CONSTRAINT IF EXISTS commands_action_check;
ALTER TABLE commands ADD CONSTRAINT commands_action_check
  CHECK (action IN ('activate','deactivate','self_test'));
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
