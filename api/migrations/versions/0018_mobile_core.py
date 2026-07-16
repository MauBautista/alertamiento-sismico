"""T-2.03 · Núcleo DB de la superficie móvil (Fase 2, spec §5/§5.1).

Activa el DDL LATENTE que el schema traía esperando al móvil y añade lo que
faltaba:

- Deltas: ``life_checkins`` (+``ts_device``, +``via self|delegated``,
  +``verified_by`` — el check-in delegado del headcount es distinguible del
  propio), ``zones.evac_policy`` (evacuate|shelter — R1: la instrucción binaria
  de crisis por ZONA), ``user_profiles.phone`` (R4: llamada de un toque, PII con
  consentimiento), ``drills.scheduled_at`` (D4c: AGENDA informativa — un drill
  programado JAMÁS arranca solo ni deriva ``active``).
- Tablas nuevas: ``push_tokens`` (registro FCM/APNs por dispositivo),
  ``device_keys`` (llave pública respaldada por hardware — §2.1-B: el teléfono
  firma la INTENCIÓN; la verificación criptográfica e2e llega en T-2.09/T-2.10),
  ``damage_reports`` (formulario de daños → Triage; append-only: es evidencia),
  ``compliance_labels`` (strings normativos POR TENANT — §2.1-C: cero literales
  en el bundle), ``site_assets`` (rutas de evacuación / punto de reunión /
  manual, cacheables offline).
- GRANTs que FALTABAN para el DDL latente (las políticas existían pero
  ``takab_app`` no tenía privilegios): ``user_zone_assignments``,
  ``site_enrollment_codes``, ``manual_activation_votes``, ``life_checkins``.

Todas las tablas nuevas: ``tenant_id`` + ENABLE/FORCE RLS + políticas
default-deny (patrón 0017). ``push_tokens``/``device_keys`` son PII de
dispositivo: lectura/escritura SOLO de la fila propia (``app_user_id()``) +
``*_admin`` interno; sin rama gov. Idempotente (invariante T-1.45): en una
cadena fresca la 0001 ya aplicó ``db/schema.sql`` con todo esto; esta migración
re-afirma. ``CREATE POLICY`` no admite IF NOT EXISTS → DROP IF EXISTS + CREATE.

Revision ID: 0018_mobile_core
Revises: 0017_visibility_grants
Create Date: 2026-07-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018_mobile_core"
down_revision: str | None = "0017_visibility_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Lectura de datos de incidente (damage_reports): own ∪ interno ∪ gov (misma
# rama que incidents_read — el reporte de daños ES dato de protección civil).
_READ_GOV = "tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id)"
# Lectura acotada al tenant (sin rama gov): PII operativa del inmueble.
_READ_TENANT = "tenant_id = app_tenant_id() OR app_is_takab_internal()"
# Escritura del tenant (jamás gov_operator).
_WRITE_TENANT = "tenant_id = app_tenant_id() AND app_role() <> 'gov_operator'"
# Fila PROPIA del portador del token (PII de dispositivo/sesión).
_SELF = "tenant_id = app_tenant_id() AND user_sub = app_user_id()"

_UP = f"""
SET ROLE takab_migrator;

-- ---------------------------------------------------------------------------
-- push_tokens — registro FCM/APNs por dispositivo (T-2.04 lo consume)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS push_tokens (
  push_token_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants,
  user_sub      uuid NOT NULL,
  platform      text NOT NULL CHECK (platform IN ('ios','android')),
  token         text NOT NULL UNIQUE,
  site_id       uuid REFERENCES sites,
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz NOT NULL DEFAULT now(),
  revoked_at    timestamptz
);
CREATE INDEX IF NOT EXISTS idx_push_tokens_user ON push_tokens (user_sub);
CREATE INDEX IF NOT EXISTS idx_push_tokens_site
  ON push_tokens (site_id) WHERE revoked_at IS NULL;

ALTER TABLE push_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE push_tokens FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pt_self ON push_tokens;
CREATE POLICY pt_self ON push_tokens FOR ALL
  USING ({_SELF}) WITH CHECK ({_SELF});
DROP POLICY IF EXISTS pt_admin ON push_tokens;
CREATE POLICY pt_admin ON push_tokens FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());
GRANT SELECT, INSERT, UPDATE, DELETE ON push_tokens TO takab_app;
GRANT SELECT ON push_tokens TO takab_ingest;  -- el worker de notify resuelve destinos

-- ---------------------------------------------------------------------------
-- device_keys — llave pública respaldada por hardware (§2.1-B)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_keys (
  key_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants,
  user_sub    uuid NOT NULL,
  platform    text NOT NULL CHECK (platform IN ('ios','android')),
  public_key  text NOT NULL,               -- SPKI PEM (P-256 de Secure Enclave/Keystore)
  attestation jsonb NOT NULL DEFAULT '{{}}',
  created_at  timestamptz NOT NULL DEFAULT now(),
  revoked_at  timestamptz
);
CREATE INDEX IF NOT EXISTS idx_device_keys_user
  ON device_keys (user_sub) WHERE revoked_at IS NULL;

ALTER TABLE device_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE device_keys FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS dk_self ON device_keys;
CREATE POLICY dk_self ON device_keys FOR ALL
  USING ({_SELF}) WITH CHECK ({_SELF});
DROP POLICY IF EXISTS dk_admin ON device_keys;
CREATE POLICY dk_admin ON device_keys FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());
GRANT SELECT, INSERT, UPDATE ON device_keys TO takab_app;

-- ---------------------------------------------------------------------------
-- damage_reports — formulario de daños del táctico → Triage (append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS damage_reports (
  report_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants,
  incident_id      uuid NOT NULL REFERENCES incidents,
  site_id          uuid NOT NULL REFERENCES sites,
  zone_id          uuid REFERENCES zones,
  user_sub         uuid NOT NULL,
  categories       jsonb NOT NULL,          -- [{{key, severity, note?}}]
  people_at_risk   boolean NOT NULL DEFAULT false,
  notes            text,
  evidence_ids     uuid[] NOT NULL DEFAULT '{{}}',
  intent_key_id    uuid,                    -- firma de intención (verificación e2e: T-2.10)
  intent_signature text,
  ts_device        timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_damage_reports_incident
  ON damage_reports (incident_id, created_at DESC);
DROP TRIGGER IF EXISTS trg_damage_reports_append_only ON damage_reports;
CREATE TRIGGER trg_damage_reports_append_only
  BEFORE UPDATE OR DELETE ON damage_reports
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

ALTER TABLE damage_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE damage_reports FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS dr_read ON damage_reports;
CREATE POLICY dr_read ON damage_reports FOR SELECT USING ({_READ_GOV});
DROP POLICY IF EXISTS dr_insert ON damage_reports;
CREATE POLICY dr_insert ON damage_reports FOR INSERT WITH CHECK ({_WRITE_TENANT});
GRANT SELECT, INSERT ON damage_reports TO takab_app;

-- ---------------------------------------------------------------------------
-- compliance_labels — strings normativos POR TENANT (§2.1-C)
-- Escritura SOLO interna: el marco normativo citable sigue como pregunta
-- abierta #1 (GATE-LEGAL); TAKAB cura los textos hasta ratificarlo.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_labels (
  tenant_id  uuid PRIMARY KEY REFERENCES tenants,
  labels     jsonb NOT NULL DEFAULT '{{}}',
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid
);
ALTER TABLE compliance_labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_labels FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cl_read ON compliance_labels;
CREATE POLICY cl_read ON compliance_labels FOR SELECT USING ({_READ_GOV});
DROP POLICY IF EXISTS cl_admin ON compliance_labels;
CREATE POLICY cl_admin ON compliance_labels FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());
GRANT SELECT, INSERT, UPDATE ON compliance_labels TO takab_app;

-- ---------------------------------------------------------------------------
-- site_assets — rutas de evacuación / punto de reunión / manual (cacheables)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS site_assets (
  asset_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants,
  site_id      uuid NOT NULL REFERENCES sites,
  zone_id      uuid REFERENCES zones,
  kind         text NOT NULL CHECK (kind IN ('evac_route','assembly_point','manual')),
  title        text NOT NULL,
  description  text,
  s3_key       text,                        -- NULL = asset textual (p.ej. punto de reunión)
  content_type text,
  updated_at   timestamptz NOT NULL DEFAULT now(),
  updated_by   uuid
);
CREATE INDEX IF NOT EXISTS idx_site_assets_site ON site_assets (site_id, kind);

ALTER TABLE site_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_assets FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sa_read ON site_assets;
CREATE POLICY sa_read ON site_assets FOR SELECT USING ({_READ_TENANT});
DROP POLICY IF EXISTS sa_write ON site_assets;
CREATE POLICY sa_write ON site_assets FOR ALL
  USING ({_WRITE_TENANT}) WITH CHECK ({_WRITE_TENANT});
DROP POLICY IF EXISTS sa_admin ON site_assets;
CREATE POLICY sa_admin ON site_assets FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());
GRANT SELECT, INSERT, UPDATE, DELETE ON site_assets TO takab_app;

RESET ROLE;
"""

# TODO delta sobre tablas PREEXISTENTES corre como USUARIO DE CONEXIÓN (sin
# SET ROLE): el dueño histórico varía por base (en el dev local
# ``user_profiles``/``drills``/``life_checkins`` pertenecen al superusuario de
# conexión; en ``takab_test`` es ``drills``; en cadena fresca todo es de
# ``takab_migrator``). Bajo ``SET ROLE takab_migrator`` cualquier tabla que no
# le pertenezca revienta con InsufficientPrivilege. El usuario de conexión
# funciona en TODOS los casos: superusuario en local, ``takab_migrator``
# (dueño de todo) en la nube.
_UP_PREEXISTING_AS_CONNECTION_USER = """
-- Deltas sobre DDL existente
ALTER TABLE life_checkins ADD COLUMN IF NOT EXISTS ts_device   timestamptz;
ALTER TABLE life_checkins ADD COLUMN IF NOT EXISTS via         text NOT NULL DEFAULT 'self';
ALTER TABLE life_checkins ADD COLUMN IF NOT EXISTS verified_by uuid;
ALTER TABLE life_checkins DROP CONSTRAINT IF EXISTS life_checkins_via_check;
ALTER TABLE life_checkins ADD CONSTRAINT life_checkins_via_check
  CHECK (via IN ('self','delegated'));

ALTER TABLE zones ADD COLUMN IF NOT EXISTS evac_policy text;
ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_evac_policy_check;
ALTER TABLE zones ADD CONSTRAINT zones_evac_policy_check
  CHECK (evac_policy IS NULL OR evac_policy IN ('evacuate','shelter'));

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS phone text;

ALTER TABLE drills ADD COLUMN IF NOT EXISTS scheduled_at timestamptz;

-- GRANTs que faltaban para el DDL latente (política sin privilegio = inservible).
GRANT SELECT, INSERT, UPDATE, DELETE ON user_zone_assignments TO takab_app;
GRANT SELECT, INSERT, UPDATE ON site_enrollment_codes TO takab_app;
GRANT SELECT, INSERT, UPDATE ON manual_activation_votes TO takab_app;
GRANT SELECT, INSERT ON life_checkins TO takab_app;
"""

_DOWN_PREEXISTING_AS_CONNECTION_USER = """
REVOKE ALL ON user_zone_assignments FROM takab_app;
REVOKE ALL ON site_enrollment_codes FROM takab_app;
REVOKE ALL ON manual_activation_votes FROM takab_app;
REVOKE ALL ON life_checkins FROM takab_app;

ALTER TABLE drills DROP COLUMN IF EXISTS scheduled_at;

ALTER TABLE user_profiles DROP COLUMN IF EXISTS phone;
ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_evac_policy_check;
ALTER TABLE zones DROP COLUMN IF EXISTS evac_policy;
ALTER TABLE life_checkins DROP CONSTRAINT IF EXISTS life_checkins_via_check;
ALTER TABLE life_checkins DROP COLUMN IF EXISTS verified_by;
ALTER TABLE life_checkins DROP COLUMN IF EXISTS via;
ALTER TABLE life_checkins DROP COLUMN IF EXISTS ts_device;
"""

# Reverso de las tablas NUEVAS (las creó SET ROLE ⇒ las dueña takab_migrator).
_DOWN = """
SET ROLE takab_migrator;

DROP TABLE IF EXISTS site_assets;
DROP TABLE IF EXISTS compliance_labels;
DROP TABLE IF EXISTS damage_reports;
DROP TABLE IF EXISTS device_keys;
DROP TABLE IF EXISTS push_tokens;

RESET ROLE;
"""


def _exec(sql: str) -> None:
    """SQL por el cursor psycopg crudo (sin binding) — patrón de 0003-0017."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_UP_PREEXISTING_AS_CONNECTION_USER)
    _exec(_UP)


def downgrade() -> None:
    _exec(_DOWN)
    _exec(_DOWN_PREEXISTING_AS_CONNECTION_USER)
