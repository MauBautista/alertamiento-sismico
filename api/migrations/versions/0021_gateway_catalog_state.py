"""T-2.24 · Estado del catálogo SSN firmado por gateway.

Espejo de ``gateway_config_state``: versión MONÓTONA anti-replay por gabinete y
huella de qué instantánea firmada salió a quién (compliance). La escribe la API
(push interno superadmin/support vía ``POST /gateways/{id}/catalog``), no la
ingesta — de ahí el grant a ``takab_app`` y no a ``takab_ingest``.

Idempotente (invariante T-1.45): ``CREATE TABLE IF NOT EXISTS`` + ``DROP POLICY
IF EXISTS`` antes de crear. Tabla NUEVA ⇒ corre bajo ``SET ROLE takab_migrator``
(patrón de dueños históricos: solo los objetos nuevos nacen del migrator).

Revision ID: 0021_gateway_catalog_state
Revises: 0020_checkin_notify
Create Date: 2026-07-31
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0021_gateway_catalog_state"
down_revision: str | None = "0020_checkin_notify"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS gateway_catalog_state (
  gateway_id   uuid PRIMARY KEY REFERENCES gateways(gateway_id) ON DELETE CASCADE,
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  version      integer NOT NULL,
  payload      jsonb NOT NULL,
  sig          text NOT NULL,
  published_at timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE ON gateway_catalog_state TO takab_app;

ALTER TABLE gateway_catalog_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE gateway_catalog_state FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS gateway_catalog_state_read ON gateway_catalog_state;
CREATE POLICY gateway_catalog_state_read ON gateway_catalog_state FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
DROP POLICY IF EXISTS gateway_catalog_state_admin ON gateway_catalog_state;
CREATE POLICY gateway_catalog_state_admin ON gateway_catalog_state FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

RESET ROLE;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    # La tabla es huella de compliance (qué salió firmado a qué gabinete):
    # no se borra en un downgrade — mismo criterio que el resto del proyecto.
    pass
