"""T-1.24 · billing_meters_daily: medidores por tenant para facturación.

Tabla anunciada por el blueprint §5.3 para B10. Un renglón por (tenant, día)
con los medidores del criterio: sitios activos, mensajes, GB (aprox) e
incidentes. La calcula la pasada ``python -m takab_api.billing`` (UPSERT
idempotente: re-computar un día = mismos valores, cero duplicados).

RLS: el tenant LEE solo lo suyo (pantalla de facturación futura); escribe solo
el worker ``takab_ingest`` (BYPASSRLS). NO es tabla de compliance: si algún
día se poda, no viola el §9 (la evidencia facturable primaria vive en las
tablas de negocio).

Revision ID: 0007_billing_meters
Revises: 0006_commands
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_billing_meters"
down_revision: str | None = "0006_commands"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
CREATE TABLE billing_meters_daily (
  tenant_id    uuid NOT NULL REFERENCES tenants,
  day          date NOT NULL,
  active_sites int    NOT NULL DEFAULT 0,
  messages     bigint NOT NULL DEFAULT 0,
  gb_approx    numeric NOT NULL DEFAULT 0,
  incidents    int    NOT NULL DEFAULT 0,
  computed_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, day)
);

ALTER TABLE billing_meters_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_meters_daily FORCE  ROW LEVEL SECURITY;
CREATE POLICY billing_meters_read ON billing_meters_daily FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY billing_meters_admin ON billing_meters_daily FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

GRANT SELECT ON billing_meters_daily TO takab_app;
GRANT SELECT, INSERT, UPDATE ON billing_meters_daily TO takab_ingest;
"""

_DOWN = """
DROP TABLE IF EXISTS billing_meters_daily;
"""


def _exec(sql: str) -> None:
    """SQL por el cursor psycopg crudo (sin binding) — patrón de 0003–0006."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_UP)


def downgrade() -> None:
    _exec(_DOWN)
