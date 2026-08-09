"""T-2.79 · Aviso de privacidad versionado + consentimiento append-only.

El criterio "cambiar el aviso no reescribe consentimientos anteriores" NO lo
cumple un `privacy_notices(version, body)` con una FK desde los consentimientos.
Basta con que alguien edite el texto de la versión 3 —una errata, una
reescritura, un `UPDATE` mal hecho— para que todos los consentimientos que
apuntaban a esa fila pasen a apuntar a un texto distinto del que se aceptó: la
FK sigue íntegra, la etiqueta sigue diciendo "3" y el registro miente.

Por eso:

* la identidad del aviso es el **digest SHA-256 de lo que la persona lee**, en
  una columna `GENERATED ... STORED` — quien inserta no puede elegir el sello;
* el consentimiento guarda una **copia** de ese digest (no un JOIN: derivarlo
  reescribiría hacia atrás lo que cada quien aceptó, que es lo prohibido);
* las dos tablas son **append-only** por el mismo `forbid_update_delete()` que
  ya protege auditoría, dictámenes y evidencia. Corregir un aviso es publicar
  otra versión; retirar un consentimiento es una fila nueva con
  `decision='withdraw'`.

El aviso de PLATAFORMA no está aquí: es un artefacto de git
(`api/src/takab_api/privacy/texts/*.json`). Esta tabla solo guarda avisos de
TENANT, y el más específico gana. Así el texto legal no queda duplicado dentro
de una migración, que es donde nadie lo revisa.

Objetos NUEVOS ⇒ `SET ROLE takab_migrator` (invariante de dueños del proyecto).
Idempotente (invariante T-1.45): `IF NOT EXISTS` en todo, `CREATE OR REPLACE`
en función y triggers, y las políticas se recrean con DROP previo.

**El REVOKE no es opcional**: el 0001 ejecuta `GRANT ... ON ALL TABLES IN SCHEMA
public` DESPUÉS de aplicar `db/schema.sql`, así que en una base NUEVA estas
tablas reciben UPDATE/DELETE aunque el schema solo conceda SELECT/INSERT.
Conceder de menos no basta; hay que revocar. Se manifiesta SOLO en base nueva
(lección de la 0028, repetida en la 0030).

Revision ID: 0033_privacy_consent
Revises: 0032_notification_simulated
Create Date: 2026-08-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0033_privacy_consent"
down_revision: str | None = "0032_notification_simulated"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# La función va SOLA y con guarda: en una base NUEVA ya existe (la creó
# `db/schema.sql` dentro del 0001) y de ella depende la columna GENERATED de
# `privacy_notices`. `CREATE OR REPLACE` sobre una función de la que cuelga una
# columna generada es justo el sitio donde PostgreSQL puede negarse, así que
# solo se crea si falta.
_FN = """
DO $do$
BEGIN
  IF to_regprocedure('privacy_notice_digest(text,text,text)') IS NULL THEN
    EXECUTE 'SET ROLE takab_migrator';
    EXECUTE $fn$
      CREATE FUNCTION privacy_notice_digest(p_locale text, p_title text, p_body text)
        RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $body$
        SELECT encode(sha256(convert_to(
          'takab.privacy-notice.v1' || E'\\n' ||
          char_length(p_locale) || ':' || p_locale || E'\\n' ||
          char_length(p_title)  || ':' || p_title  || E'\\n' ||
          char_length(p_body)   || ':' || p_body, 'UTF8')), 'hex')
        $body$
    $fn$;
    EXECUTE 'RESET ROLE';
  END IF;
END
$do$;
"""

_UP = """
SET ROLE takab_migrator;

CREATE TABLE IF NOT EXISTS privacy_notices (
  notice_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  purpose      text NOT NULL CHECK (purpose IN ('privacy_notice','whatsapp_alerts')),
  locale       text NOT NULL CHECK (locale ~ '^[a-z]{2}-[A-Z]{2}$'),
  version      text NOT NULL CHECK (char_length(btrim(version)) BETWEEN 1 AND 40),
  title        text NOT NULL CHECK (char_length(btrim(title)) BETWEEN 8 AND 200),
  body         text NOT NULL CHECK (char_length(btrim(body)) >= 40),
  digest       text GENERATED ALWAYS AS (privacy_notice_digest(locale, title, body)) STORED,
  effective_at timestamptz NOT NULL DEFAULT now(),
  -- clock_timestamp() y NO now(): now() es el instante de INICIO de la
  -- transacción y dos avisos publicados juntos empatarían.
  published_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  -- Orden TOTAL de publicación (ver db/schema.sql): sin él, "el aviso vigente"
  -- no está definido cuando dos filas comparten `effective_at`.
  seq          bigint GENERATED ALWAYS AS IDENTITY,
  published_by uuid NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_privacy_notices_digest
  ON privacy_notices (tenant_id, purpose, locale, digest);
CREATE UNIQUE INDEX IF NOT EXISTS uq_privacy_notices_version
  ON privacy_notices (tenant_id, purpose, locale, version);
CREATE INDEX IF NOT EXISTS idx_privacy_notices_vigente
  ON privacy_notices (tenant_id, purpose, locale, effective_at DESC);

CREATE TABLE IF NOT EXISTS privacy_consents (
  consent_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants(tenant_id),
  purpose        text NOT NULL CHECK (purpose IN ('privacy_notice','whatsapp_alerts')),
  subject_kind   text NOT NULL CHECK (subject_kind IN ('user','msisdn')),
  user_sub       uuid,
  subject_ref    text NOT NULL,
  decision       text NOT NULL CHECK (decision IN ('accept','withdraw')),
  notice_source  text NOT NULL CHECK (notice_source IN ('repo','tenant')),
  notice_id      uuid REFERENCES privacy_notices(notice_id),
  notice_digest  text NOT NULL CHECK (notice_digest ~ '^[0-9a-f]{64}$'),
  notice_version text NOT NULL,
  notice_locale  text NOT NULL,
  via            text NOT NULL CHECK (via IN ('mobile','web','console_admin','out_of_band')),
  actor_sub      uuid NOT NULL,
  decided_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pc_sujeto_coherente CHECK (
    (subject_kind = 'user'   AND user_sub IS NOT NULL AND subject_ref = user_sub::text) OR
    (subject_kind = 'msisdn' AND user_sub IS     NULL AND subject_ref ~ '^\\+[1-9][0-9]{7,14}$')
  ),
  CONSTRAINT pc_origen_coherente CHECK (
    (notice_source = 'repo'   AND notice_id IS     NULL) OR
    (notice_source = 'tenant' AND notice_id IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_privacy_consents_sujeto
  ON privacy_consents (tenant_id, purpose, subject_ref, decided_at DESC);
CREATE INDEX IF NOT EXISTS idx_privacy_consents_user
  ON privacy_consents (tenant_id, user_sub, decided_at DESC) WHERE user_sub IS NOT NULL;

RESET ROLE;

-- Append-only: el mismo guard que protege auditoría, dictámenes y evidencia.
-- `CREATE OR REPLACE TRIGGER` (PG14+) hace idempotente el paso en base nueva,
-- donde el trigger ya vino de `db/schema.sql`.
CREATE OR REPLACE TRIGGER trg_privacy_notices_append_only
  BEFORE UPDATE OR DELETE ON privacy_notices
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE OR REPLACE TRIGGER trg_privacy_consents_append_only
  BEFORE UPDATE OR DELETE ON privacy_consents
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

GRANT SELECT, INSERT ON privacy_notices, privacy_consents TO takab_app;
-- Ver la cabecera: sin estos REVOKE una base NUEVA acaba con UPDATE/DELETE
-- concedidos sobre un registro de cumplimiento que jamás se edita ni se poda.
REVOKE UPDATE, DELETE ON privacy_notices, privacy_consents FROM takab_app;
REVOKE ALL ON privacy_notices FROM takab_ingest;
-- El worker de notify LEE el opt-in (costura de T-2.77). Escribir un
-- consentimiento jamás es cosa de un worker.
GRANT SELECT ON privacy_consents TO takab_ingest;
REVOKE INSERT, UPDATE, DELETE ON privacy_consents FROM takab_ingest;

ALTER TABLE privacy_notices  ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_notices  FORCE  ROW LEVEL SECURITY;
ALTER TABLE privacy_consents ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_consents FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS pn_read    ON privacy_notices;
DROP POLICY IF EXISTS pn_publish ON privacy_notices;
DROP POLICY IF EXISTS pc_self          ON privacy_consents;
DROP POLICY IF EXISTS pc_admin         ON privacy_consents;
DROP POLICY IF EXISTS pc_internal_read ON privacy_consents;

CREATE POLICY pn_read ON privacy_notices FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY pn_publish ON privacy_notices FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id()
              AND app_role() IN ('tenant_admin','takab_superadmin'));

CREATE POLICY pc_self ON privacy_consents FOR ALL
  USING      (tenant_id = app_tenant_id() AND user_sub = app_user_id())
  WITH CHECK (tenant_id = app_tenant_id() AND user_sub = app_user_id());
CREATE POLICY pc_admin ON privacy_consents FOR ALL
  USING      (tenant_id = app_tenant_id()
              AND app_role() IN ('tenant_admin','takab_superadmin'))
  WITH CHECK (tenant_id = app_tenant_id()
              AND app_role() IN ('tenant_admin','takab_superadmin'));
CREATE POLICY pc_internal_read ON privacy_consents FOR SELECT
  USING (app_is_takab_internal());

COMMENT ON TABLE privacy_notices IS
  'T-2.79: aviso de TENANT, append-only. La identidad es `digest` (GENERATED), '
  'no `version`: editar el texto mueve el sello y el consentimiento de ayer queda '
  'obsoleto solo. El aviso de PLATAFORMA es un artefacto de git '
  '(api/src/takab_api/privacy/texts/*.json), no una fila.';
COMMENT ON TABLE privacy_consents IS
  'T-2.79: registro append-only del consentimiento. `notice_digest` es una COPIA '
  'sellada del contenido aceptado, no un JOIN: derivarlo reescribiría hacia atrás '
  'lo que cada quien aceptó. Retirar = fila nueva con decision=withdraw. Regla de '
  'oro 11: jamás se poda.';
"""


def upgrade() -> None:
    op.execute(_FN)
    op.execute(_UP)


def downgrade() -> None:
    # Deliberadamente NO se borran las tablas: son el registro de quién aceptó
    # qué texto y cuándo. Un downgrade que lo destruyera dejaría al sistema sin
    # poder probar un consentimiento que sí existió (regla de oro 11, el mismo
    # criterio que audit_log y que maintenance_windows).
    pass
