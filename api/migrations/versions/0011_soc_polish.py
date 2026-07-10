"""T-1.48 · Pulido SOC: perfil de operador, catálogo de referencia y reubicación
de epicentro.

Tres piezas independientes que el SOC necesita y no existían:

1. ``app_user_id()`` + ``user_profiles`` — nombre de operador editable. La
   identidad sigue siendo Cognito (``/me`` no cambia); esto es SOLO presentación.
   RLS FORCE: lectura tenant-wide (para resolver actores en timelines), escritura
   exclusivamente de la fila PROPIA (``user_sub = app_user_id()``). Excepción
   documentada al patrón anti-gov: ``gov_operator`` también edita SU nombre —
   es dato personal, no escribe nada ajeno.

2. ``reference_earthquakes`` — catálogo GLOBAL de sismos relevantes reales
   (SSN/USGS, transcritos del catálogo ratificado en T-1.46). Excepción
   documentada a "tenant_id en toda tabla" (misma familia que seismic_events:
   dato científico público). Lectura para cualquier rol autenticado; SIN
   política de escritura — solo seeds/migrator escriben.

3. ``relocate_incident_epicenter()`` — SECURITY DEFINER dueño ``takab_ingest``
   (precedente exacto: ``gov_ack_incident``/0003). ``seismic_events`` es dato de
   RED sin tenant_id: una política RLS tenant-scoped de UPDATE abriría el evento
   compartido a cualquier tenant con un incidente linkeado; la función centraliza
   guardas (rol, tenant del incidente, rango) y preserva el punto previo en
   ``meta.manual_override``. Sin evento linkeado crea ``EVT-MAN-<md5[:8]>``
   (determinista por incidente ⇒ re-POST no duplica), ``source='manual'`` y
   ``magnitude NULL`` (jamás magnitud inventada, blueprint §14). NO audita por sí
   misma: el audit es del router vía ``audit.py`` (single-writer contract-test).

Revision ID: 0011_soc_polish
Revises: 0010_sensor_calibration
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011_soc_polish"
down_revision: str | None = "0010_sensor_calibration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APP_USER_ID = """
CREATE OR REPLACE FUNCTION app_user_id() RETURNS uuid
  LANGUAGE sql STABLE AS
  $$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$;
"""

_USER_PROFILES = """
CREATE TABLE user_profiles (
  user_sub     uuid PRIMARY KEY,
  tenant_id    uuid NOT NULL REFERENCES tenants,
  display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 80),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_user_profiles_tenant ON user_profiles (tenant_id);
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles FORCE  ROW LEVEL SECURITY;
CREATE POLICY user_profiles_read ON user_profiles FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY user_profiles_self_write ON user_profiles FOR ALL
  USING      (tenant_id = app_tenant_id() AND user_sub = app_user_id())
  WITH CHECK (tenant_id = app_tenant_id() AND user_sub = app_user_id());
CREATE POLICY user_profiles_admin ON user_profiles FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());
GRANT SELECT, INSERT, UPDATE ON user_profiles TO takab_app;
"""

_REFERENCE_EARTHQUAKES = """
CREATE TABLE reference_earthquakes (
  ref_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  catalog_key text NOT NULL UNIQUE,
  origin_time timestamptz NOT NULL,
  magnitude   numeric NOT NULL,
  place       text NOT NULL,
  epicenter   geography(Point,4326) NOT NULL,
  depth_km    numeric,
  source      text NOT NULL CHECK (source IN ('SSN','USGS')),
  source_ref  text NOT NULL,
  notes       text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_ref_eq_origin ON reference_earthquakes (origin_time DESC);
ALTER TABLE reference_earthquakes ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_earthquakes FORCE  ROW LEVEL SECURITY;
CREATE POLICY ref_eq_read ON reference_earthquakes FOR SELECT
  USING (app_role() IS NOT NULL);
GRANT SELECT ON reference_earthquakes TO takab_app;
"""

# El engine ya tiene INSERT sobre seismic_events (correlación); UPDATE es nuevo
# (la reubicación es la primera escritura post-hoc sobre un evento existente).
_GRANTS = """
GRANT SELECT, INSERT, UPDATE ON seismic_events TO takab_ingest;
GRANT SELECT, UPDATE ON incidents TO takab_ingest;
"""

# Los parámetros de retorno llevan prefijo r_ para que plpgsql no los confunda
# con columnas de incidents/seismic_events (ambigüedad variable-vs-columna).
_RELOCATE = """
CREATE OR REPLACE FUNCTION relocate_incident_epicenter(
  p_incident_id uuid, p_lon float8, p_lat float8
) RETURNS TABLE (r_event_id text, r_created_event boolean,
                 r_prev_lon float8, r_prev_lat float8)
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_incident incidents%ROWTYPE;
  v_event_id text;
  v_created  boolean := false;
  v_prev_lon float8;
  v_prev_lat float8;
BEGIN
  IF app_role() IS NULL
     OR app_role() NOT IN ('soc_operator','tenant_admin','takab_superadmin') THEN
    RAISE EXCEPTION 'relocate_epicenter: rol sin permiso (%)',
      coalesce(app_role(), 'sin-rol');
  END IF;
  IF p_lon IS NULL OR p_lat IS NULL
     OR p_lon < -180 OR p_lon > 180 OR p_lat < -90 OR p_lat > 90 THEN
    RAISE EXCEPTION 'relocate_epicenter: coordenadas fuera de rango';
  END IF;

  SELECT i.* INTO v_incident FROM incidents i
   WHERE i.incident_id = p_incident_id
     FOR UPDATE OF i;
  IF NOT FOUND
     OR (v_incident.tenant_id <> app_tenant_id() AND NOT app_is_takab_internal()) THEN
    -- Cross-tenant es INVISIBLE: mismo mensaje que inexistente (404 en la API).
    RAISE EXCEPTION 'relocate_epicenter: incidente % inexistente', p_incident_id;
  END IF;

  IF v_incident.event_id IS NOT NULL THEN
    v_event_id := v_incident.event_id;
    SELECT ST_X(e.epicenter::geometry), ST_Y(e.epicenter::geometry)
      INTO v_prev_lon, v_prev_lat
      FROM seismic_events e WHERE e.event_id = v_event_id
      FOR UPDATE;
    UPDATE seismic_events e SET
      epicenter = ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326)::geography,
      meta = e.meta || jsonb_build_object('manual_override', jsonb_build_object(
        'prev_lon', v_prev_lon, 'prev_lat', v_prev_lat,
        'by', nullif(current_setting('app.user_id', true), ''),
        'at', now()))
     WHERE e.event_id = v_event_id;
  ELSE
    v_event_id := 'EVT-MAN-' || substr(md5(p_incident_id::text), 1, 8);
    v_created := true;
    INSERT INTO seismic_events (event_id, source, magnitude, epicenter, detected_at, meta)
    VALUES (v_event_id, 'manual', NULL,
            ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326)::geography,
            v_incident.opened_at,
            jsonb_build_object(
              'via', 'relocate_incident_epicenter',
              'incident_id', p_incident_id::text,
              'by', nullif(current_setting('app.user_id', true), '')))
    ON CONFLICT (event_id) DO UPDATE
      SET epicenter = EXCLUDED.epicenter;
    UPDATE incidents i SET event_id = v_event_id
     WHERE i.incident_id = p_incident_id AND i.event_id IS NULL;
  END IF;

  RETURN QUERY SELECT v_event_id, v_created, v_prev_lon, v_prev_lat;
END $fn$;
ALTER FUNCTION relocate_incident_epicenter(uuid, float8, float8) OWNER TO takab_ingest;
"""

_DOWN = """
DROP FUNCTION IF EXISTS relocate_incident_epicenter(uuid, float8, float8);
DROP TABLE IF EXISTS reference_earthquakes;
DROP TABLE IF EXISTS user_profiles;
DROP FUNCTION IF EXISTS app_user_id();
REVOKE UPDATE ON seismic_events FROM takab_ingest;
"""


def _exec(sql: str) -> None:
    """Cursor psycopg crudo (sin binding): el cuerpo lleva ``%`` (RAISE) y ``:``
    que el binding interpretaría como placeholders — patrón de 0003."""
    dbapi = op.get_bind().connection.dbapi_connection
    with dbapi.cursor() as cur:
        cur.execute(sql)


def upgrade() -> None:
    _exec(_APP_USER_ID)
    _exec(_USER_PROFILES)
    _exec(_REFERENCE_EARTHQUAKES)
    _exec(_GRANTS)
    _exec(_RELOCATE)


def downgrade() -> None:
    _exec(_DOWN)
