"""T-1.23 · commands + gateway_config_state + NOTIFY de rule_sets.

- ``commands``: registro de comandos remotos de actuador firmados. El
  ``nonce`` UNIQUE es el anti-replay en EMISIÓN (el edge tiene el suyo en
  verificación, T-1.12); status pending→acked/rejected (por command_ack del
  edge, vía nonce) o →expired (worker, por TTL: el "ack obligatorio" se
  garantiza porque un comando sin ack NO queda pendiente para siempre).
  RLS: el tenant lee y ESCRIBE lo suyo (la API emite bajo la sesión del
  usuario, estilo incidents_write); gov_operator jamás comanda actuadores.
- ``gateway_config_state``: versión MONÓTONA por gateway de la config firmada
  publicada (el edge rechaza toda versión ya vista — T-1.12 high_water).
  Escribe solo el worker (BYPASSRLS); el tenant la lee.
- ``takab_notify_rule_set``: NOTIFY en ``takab_live`` al activar/cambiar un
  rule_set → el worker de sync publica la config firmada ≤60 s (criterio).

Revision ID: 0006_commands
Revises: 0005_notification_jobs
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_commands"
down_revision: str | None = "0005_notification_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
CREATE TABLE commands (
  command_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants,
  site_id     uuid NOT NULL REFERENCES sites,
  gateway_id  uuid NOT NULL REFERENCES gateways,
  issued_by   uuid NOT NULL,
  channel     text NOT NULL CHECK (channel IN
              ('siren','strobe','gas_valve','elevator','door_retainer')),
  action      text NOT NULL CHECK (action IN ('activate','deactivate')),
  event_id    text,
  nonce       text NOT NULL UNIQUE,
  issued_at   timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,
  status      text NOT NULL DEFAULT 'pending'
              CHECK (status IN ('pending','acked','rejected','expired')),
  ack         jsonb,
  error       text
);

CREATE INDEX idx_commands_site ON commands (site_id, issued_at DESC);
CREATE INDEX idx_commands_pending ON commands (expires_at) WHERE status = 'pending';
CREATE INDEX idx_commands_rate ON commands (issued_by, site_id, issued_at DESC);

ALTER TABLE commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE commands FORCE  ROW LEVEL SECURITY;
CREATE POLICY commands_read ON commands FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY commands_write ON commands FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY commands_admin ON commands FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

CREATE TABLE gateway_config_state (
  gateway_id   uuid PRIMARY KEY REFERENCES gateways,
  tenant_id    uuid NOT NULL REFERENCES tenants,
  version      int  NOT NULL,
  payload      jsonb NOT NULL,
  sig          text NOT NULL,
  published_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE gateway_config_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE gateway_config_state FORCE  ROW LEVEL SECURITY;
CREATE POLICY gateway_config_state_read ON gateway_config_state FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY gateway_config_state_admin ON gateway_config_state FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

GRANT SELECT, INSERT, UPDATE ON commands TO takab_app;
GRANT SELECT, INSERT, UPDATE ON commands TO takab_ingest;
GRANT SELECT ON gateway_config_state TO takab_app;
GRANT SELECT, INSERT, UPDATE ON gateway_config_state TO takab_ingest;

CREATE OR REPLACE FUNCTION takab_notify_rule_set() RETURNS trigger
  LANGUAGE plpgsql AS $fn$
BEGIN
  PERFORM pg_notify('takab_live', jsonb_build_object(
    't', 'rule_set', 'tenant', NEW.tenant_id, 'id', NEW.rule_set_id)::text);
  RETURN NULL;
END $fn$;

CREATE TRIGGER trg_rule_sets_notify
  AFTER INSERT OR UPDATE ON rule_sets
  FOR EACH ROW EXECUTE FUNCTION takab_notify_rule_set();
"""

_DOWN = """
DROP TRIGGER IF EXISTS trg_rule_sets_notify ON rule_sets;
DROP FUNCTION IF EXISTS takab_notify_rule_set();
DROP TABLE IF EXISTS gateway_config_state;
DROP TABLE IF EXISTS commands;
"""


def _exec(sql: str) -> None:
    """SQL por el cursor psycopg crudo (sin binding) — patrón de 0003–0005."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_UP)


def downgrade() -> None:
    _exec(_DOWN)
