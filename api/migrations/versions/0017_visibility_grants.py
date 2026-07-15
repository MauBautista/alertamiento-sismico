"""T-1.73 · Visibilidad configurable entre clientes (RLS).

El superadmin concede, por cliente (grantee), ver METADATOS (que EXISTEN las
estaciones) y/o DATOS en vivo (formas de onda, métricas, salud, incidentes) de
otro tenant o de TODOS. Default-deny: sin fila de grant, cero acceso extra.
NUNCA concede escritura (las políticas ``*_write``/``*_admin`` no se tocan).

Crux (metadata ≠ datos): las vistas ``*_secure`` aíslan por JOIN a ``sites`` y
``sites_read`` se amplía con ``app_can_view_meta`` — un grant de SOLO-metadatos
haría casar el JOIN, así que el ``WHERE`` de cada vista gatea los DATOS por su
cuenta (``app_can_view_data``). Sin él, un permiso de metadatos filtraría el crudo.

Idempotente (T-1.45): CREATE ... IF NOT EXISTS / DROP POLICY IF EXISTS + CREATE /
CREATE OR REPLACE FUNCTION|VIEW. Todo bajo ``takab_migrator`` (dueño NO-superusuario
→ el FORCE RLS de ``sites`` sujeta las vistas; los helpers SECURITY DEFINER corren
como migrator). En una cadena FRESCA la 0001 ya aplicó ``db/schema.sql`` con todo
esto; esta migración re-afirma (y re-añade el ``WHERE`` a las vistas de caggs que la
0008 recrea sin él a mitad de cadena). No necesita superusuario ni BYPASSRLS.

Revision ID: 0017_visibility_grants
Revises: 0016_notification_retry
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0017_visibility_grants"
down_revision: str | None = "0016_notification_retry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Cláusula base de las políticas de lectura (own ∪ interno ∪ gov), a la que se le
# añade la rama de visibilidad configurable. `_META`/`_DATA` = versión ampliada.
_BASE = "tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id)"

_UP = f"""
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS visibility_grants (
  grant_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  grantee_tenant_id uuid NOT NULL REFERENCES tenants ON DELETE CASCADE,
  target_tenant_id  uuid REFERENCES tenants ON DELETE CASCADE,
  target_all        boolean NOT NULL DEFAULT false,
  can_view_metadata boolean NOT NULL DEFAULT false,
  can_view_data     boolean NOT NULL DEFAULT false,
  created_by        uuid NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT vg_target_shape CHECK (
    (target_all AND target_tenant_id IS NULL) OR
    (NOT target_all AND target_tenant_id IS NOT NULL)),
  CONSTRAINT vg_no_self CHECK (target_all OR grantee_tenant_id <> target_tenant_id),
  CONSTRAINT vg_nonempty CHECK (can_view_metadata OR can_view_data)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_vg_specific
  ON visibility_grants (grantee_tenant_id, target_tenant_id) WHERE NOT target_all;
CREATE UNIQUE INDEX IF NOT EXISTS uq_vg_all
  ON visibility_grants (grantee_tenant_id) WHERE target_all;
CREATE INDEX IF NOT EXISTS idx_vg_grantee ON visibility_grants (grantee_tenant_id);

ALTER TABLE visibility_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE visibility_grants FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS vg_read  ON visibility_grants;
CREATE POLICY vg_read  ON visibility_grants FOR SELECT
  USING (grantee_tenant_id = app_tenant_id() OR app_is_takab_internal());
DROP POLICY IF EXISTS vg_admin ON visibility_grants;
CREATE POLICY vg_admin ON visibility_grants FOR ALL
  USING (app_role() = 'takab_superadmin') WITH CHECK (app_role() = 'takab_superadmin');
GRANT SELECT, INSERT, UPDATE, DELETE ON visibility_grants TO takab_app;

CREATE OR REPLACE FUNCTION app_can_view_meta(t uuid) RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
  $$ SELECT EXISTS (SELECT 1 FROM visibility_grants g
                     WHERE g.grantee_tenant_id = app_tenant_id()
                       AND (g.can_view_metadata OR g.can_view_data)
                       AND (g.target_all OR g.target_tenant_id = t)) $$;

CREATE OR REPLACE FUNCTION app_can_view_data(t uuid) RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
  $$ SELECT EXISTS (SELECT 1 FROM visibility_grants g
                     WHERE g.grantee_tenant_id = app_tenant_id()
                       AND g.can_view_data
                       AND (g.target_all OR g.target_tenant_id = t)) $$;

-- Vistas seguras: se les añade el WHERE de DATOS (crux). CREATE OR REPLACE preserva
-- owner (takab_migrator) y grants. Re-aplica el WHERE que la 0008 quita a los caggs.
CREATE OR REPLACE VIEW waveform_features_1s_secure WITH (security_barrier = true) AS
  SELECT wf.* FROM waveform_features_1s wf JOIN sites s ON s.site_id = wf.site_id
  WHERE s.tenant_id = app_tenant_id() OR app_is_takab_internal()
     OR app_gov_can_see(s.tenant_id) OR app_can_view_data(s.tenant_id);
CREATE OR REPLACE VIEW site_metrics_1m_secure WITH (security_barrier = true) AS
  SELECT m.* FROM site_metrics_1m m JOIN sites s ON s.site_id = m.site_id
  WHERE s.tenant_id = app_tenant_id() OR app_is_takab_internal()
     OR app_gov_can_see(s.tenant_id) OR app_can_view_data(s.tenant_id);
CREATE OR REPLACE VIEW site_metrics_1h_secure WITH (security_barrier = true) AS
  SELECT m.* FROM site_metrics_1h m JOIN sites s ON s.site_id = m.site_id
  WHERE s.tenant_id = app_tenant_id() OR app_is_takab_internal()
     OR app_gov_can_see(s.tenant_id) OR app_can_view_data(s.tenant_id);

-- Metadatos (existencia de estaciones): += app_can_view_meta.
DROP POLICY IF EXISTS sites_read ON sites;
CREATE POLICY sites_read ON sites FOR SELECT
  USING ({_BASE} OR app_can_view_meta(tenant_id));
DROP POLICY IF EXISTS zones_read ON zones;
CREATE POLICY zones_read ON zones FOR SELECT
  USING ({_BASE} OR app_can_view_meta(tenant_id));
DROP POLICY IF EXISTS gateways_read ON gateways;
CREATE POLICY gateways_read ON gateways FOR SELECT
  USING ({_BASE} OR app_can_view_meta(tenant_id));
DROP POLICY IF EXISTS sensors_read ON sensors;
CREATE POLICY sensors_read ON sensors FOR SELECT
  USING ({_BASE} OR app_can_view_meta(tenant_id));

-- Datos en vivo (incidentes/timeline/salud/reglas): += app_can_view_data.
DROP POLICY IF EXISTS incidents_read ON incidents;
CREATE POLICY incidents_read ON incidents FOR SELECT
  USING ({_BASE} OR app_can_view_data(tenant_id));
DROP POLICY IF EXISTS actions_read ON incident_actions;
CREATE POLICY actions_read ON incident_actions FOR SELECT
  USING ({_BASE} OR app_can_view_data(tenant_id));
DROP POLICY IF EXISTS dh_read ON device_health;
CREATE POLICY dh_read ON device_health FOR SELECT
  USING ({_BASE} OR app_can_view_data(tenant_id));
DROP POLICY IF EXISTS re_read ON rule_evaluations;
CREATE POLICY re_read ON rule_evaluations FOR SELECT
  USING ({_BASE} OR app_can_view_data(tenant_id));

-- Catálogo de tenants: += app_can_view_meta (resolver el nombre del cliente compartido).
DROP POLICY IF EXISTS tenants_read ON tenants;
CREATE POLICY tenants_read ON tenants FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR (app_role() = 'gov_operator' AND visibility = 'gov_shared')
         OR app_can_view_meta(tenant_id));

RESET ROLE;
"""

# Reverso: restaura las políticas/vistas ORIGINALES (sin las ramas nuevas), suelta
# los helpers y la tabla. El orden importa: primero se quitan las referencias a las
# funciones (políticas + vistas), luego se dropean las funciones y la tabla.
_DOWN = f"""
SET ROLE takab_migrator;

DROP POLICY IF EXISTS sites_read    ON sites;
CREATE POLICY sites_read    ON sites    FOR SELECT USING ({_BASE});
DROP POLICY IF EXISTS zones_read    ON zones;
CREATE POLICY zones_read    ON zones    FOR SELECT USING ({_BASE});
DROP POLICY IF EXISTS gateways_read ON gateways;
CREATE POLICY gateways_read ON gateways FOR SELECT USING ({_BASE});
DROP POLICY IF EXISTS sensors_read  ON sensors;
CREATE POLICY sensors_read  ON sensors  FOR SELECT USING ({_BASE});
DROP POLICY IF EXISTS incidents_read ON incidents;
CREATE POLICY incidents_read ON incidents FOR SELECT USING ({_BASE});
DROP POLICY IF EXISTS actions_read ON incident_actions;
CREATE POLICY actions_read ON incident_actions FOR SELECT USING ({_BASE});
DROP POLICY IF EXISTS dh_read ON device_health;
CREATE POLICY dh_read ON device_health FOR SELECT USING ({_BASE});
DROP POLICY IF EXISTS re_read ON rule_evaluations;
CREATE POLICY re_read ON rule_evaluations FOR SELECT USING ({_BASE});
DROP POLICY IF EXISTS tenants_read ON tenants;
CREATE POLICY tenants_read ON tenants FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR (app_role() = 'gov_operator' AND visibility = 'gov_shared'));

CREATE OR REPLACE VIEW waveform_features_1s_secure WITH (security_barrier = true) AS
  SELECT wf.* FROM waveform_features_1s wf JOIN sites s ON s.site_id = wf.site_id;
CREATE OR REPLACE VIEW site_metrics_1m_secure WITH (security_barrier = true) AS
  SELECT m.* FROM site_metrics_1m m JOIN sites s ON s.site_id = m.site_id;
CREATE OR REPLACE VIEW site_metrics_1h_secure WITH (security_barrier = true) AS
  SELECT m.* FROM site_metrics_1h m JOIN sites s ON s.site_id = m.site_id;

DROP FUNCTION IF EXISTS app_can_view_meta(uuid);
DROP FUNCTION IF EXISTS app_can_view_data(uuid);
DROP TABLE IF EXISTS visibility_grants;

RESET ROLE;
"""


def _exec(sql: str) -> None:
    """SQL por el cursor psycopg crudo (sin binding) — patrón de 0003-0008."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_UP)


def downgrade() -> None:
    _exec(_DOWN)
