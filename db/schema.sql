-- ============================================================================
-- TAKAB Technology · Esquema de producción consolidado · v1
-- PostgreSQL 16 + TimescaleDB 2.x + PostGIS 3.x
-- Fuente de verdad única. Combina núcleo (Fase 0) + tablas de auth (RBAC).
-- Aplicar vía Alembic (tarea T-1.3). NO reinventar; extender solo con migración.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- 1. MULTI-TENANT CORE
-- ---------------------------------------------------------------------------
CREATE TABLE tenants (
  tenant_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code           text NOT NULL UNIQUE,
  name           text NOT NULL,
  isolation_mode text NOT NULL DEFAULT 'logical' CHECK (isolation_mode IN ('logical','dedicated')),
  vertical       text,
  visibility     text NOT NULL DEFAULT 'private'  CHECK (visibility IN ('private','gov_shared')),
  status         text NOT NULL DEFAULT 'active'   CHECK (status IN ('trial','active','suspended')),
  plan_code      text NOT NULL DEFAULT 'mvp',
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sites (
  site_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants ON DELETE RESTRICT,
  code          text NOT NULL,
  name          text NOT NULL,
  timezone      text NOT NULL DEFAULT 'America/Mexico_City',
  criticality   text NOT NULL DEFAULT 'medium' CHECK (criticality IN ('low','medium','high','critical')),
  geom          geography(Point,4326) NOT NULL,
  address       text,
  building_type text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, code)
);
CREATE INDEX idx_sites_geom   ON sites USING GIST (geom);
CREATE INDEX idx_sites_tenant ON sites (tenant_id);

CREATE TABLE zones (
  zone_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id    uuid NOT NULL REFERENCES sites ON DELETE CASCADE,
  name       text NOT NULL,
  level_code text,
  zone_geom  geometry(Polygon,4326)
);

-- ---------------------------------------------------------------------------
-- 2. HARDWARE: GABINETES Y SENSORES
-- ---------------------------------------------------------------------------
CREATE TABLE gateways (
  gateway_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants,
  site_id      uuid NOT NULL REFERENCES sites,
  serial       text NOT NULL UNIQUE,
  fw_version   text,
  iot_thing    text UNIQUE,
  status       text NOT NULL DEFAULT 'provisioned'
               CHECK (status IN ('provisioned','online','degraded','offline','retired')),
  has_wr1      boolean NOT NULL DEFAULT true,
  installed_at timestamptz,
  metadata     jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE sensors (
  sensor_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants,
  site_id     uuid NOT NULL REFERENCES sites,
  gateway_id  uuid REFERENCES gateways,
  zone_id     uuid REFERENCES zones,
  kind        text NOT NULL CHECK (kind IN ('structural','ground')),  -- pared vs enterrado
  model       text NOT NULL,
  serial      text UNIQUE,
  channels    text[] NOT NULL DEFAULT '{EHZ}',
  sample_rate int  NOT NULL DEFAULT 100,
  mount       text CHECK (mount IN ('concrete_column','steel','floor','buried')),
  geom        geography(Point,4326),
  status      text NOT NULL DEFAULT 'active',
  metadata    jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_sensors_site ON sensors (site_id);

-- Un sitio puede referenciar el sensor de terreno de un sitio vecino
CREATE TABLE site_ground_refs (
  site_id          uuid NOT NULL REFERENCES sites ON DELETE CASCADE,
  ground_sensor_id uuid NOT NULL REFERENCES sensors,
  distance_m       numeric,
  PRIMARY KEY (site_id, ground_sensor_id)
);

-- ---------------------------------------------------------------------------
-- 3. REGLAS Y UMBRALES (versionadas)
-- ---------------------------------------------------------------------------
CREATE TABLE rule_sets (
  rule_set_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants,
  scope_type  text NOT NULL CHECK (scope_type IN ('tenant','site','sensor')),
  scope_id    uuid NOT NULL,
  version     int  NOT NULL,
  is_active   boolean NOT NULL DEFAULT false,
  config      jsonb NOT NULL,   -- {thresholds:{...}, quorum:{min:3,window_s:5}, relays:{...}}
  created_by  uuid,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (scope_type, scope_id, version)
);

-- ---------------------------------------------------------------------------
-- 4. EVENTOS, INCIDENTES, QUÓRUM, DICTÁMENES
-- ---------------------------------------------------------------------------
CREATE TABLE seismic_events (
  event_id    text PRIMARY KEY,                       -- 'EVT-20260510-0843'
  source      text NOT NULL CHECK (source IN ('sasmex','local_quorum','manual','external')),
  magnitude   numeric,
  epicenter   geography(Point,4326),
  depth_km    numeric,
  detected_at timestamptz NOT NULL,
  meta        jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE incidents (
  incident_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_uuid  uuid NOT NULL UNIQUE,                   -- UUIDv7 del edge → idempotencia
  tenant_id   uuid NOT NULL REFERENCES tenants,
  site_id     uuid NOT NULL REFERENCES sites,
  event_id    text REFERENCES seismic_events,
  opened_at   timestamptz NOT NULL,
  closed_at   timestamptz,
  severity    text NOT NULL CHECK (severity IN ('info','watch','warning','critical')),
  state       text NOT NULL DEFAULT 'open' CHECK (state IN ('open','acked','in_review','closed')),
  trigger     text NOT NULL CHECK (trigger IN ('sasmex','local_threshold','quorum','manual')),
  max_pga_g   numeric,
  max_pgv_cms numeric,
  summary     jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_incidents_site_open    ON incidents (site_id, opened_at DESC);
CREATE INDEX idx_incidents_tenant_state ON incidents (tenant_id, state) WHERE state <> 'closed';

CREATE TABLE quorum_votes (
  event_id    text NOT NULL REFERENCES seismic_events,
  sensor_id   uuid NOT NULL REFERENCES sensors,
  detected_at timestamptz NOT NULL,
  pga_g       numeric NOT NULL,
  delta_s     numeric,
  counted     boolean NOT NULL DEFAULT true,
  PRIMARY KEY (event_id, sensor_id)
);

CREATE TABLE incident_actions (
  action_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid NOT NULL REFERENCES incidents ON DELETE CASCADE,
  ts          timestamptz NOT NULL DEFAULT now(),
  kind        text NOT NULL,    -- 'siren_on','siren_test','gas_closed','ack','dictamen','notify_sent'
  actor       text NOT NULL,    -- 'edge:CHL-A' | 'user:uuid' | 'system'
  payload     jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_actions_incident ON incident_actions (incident_id, ts);

CREATE TABLE dictamens (
  dictamen_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid NOT NULL REFERENCES incidents,
  status      text NOT NULL CHECK (status IN
              ('normal_operation','inhabit_monitor','restricted','no_inhabit_inspect')),
  basis       jsonb NOT NULL,
  signed_by   uuid,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 5. AUTH / RBAC (ver RBAC-TAKAB.md)
-- ---------------------------------------------------------------------------
-- user_id = Cognito 'sub'. La identidad la gestiona Cognito; aquí guardamos asignaciones.
CREATE TABLE user_zone_assignments (
  user_id     uuid NOT NULL,
  tenant_id   uuid NOT NULL REFERENCES tenants,
  site_id     uuid NOT NULL REFERENCES sites,
  zone_id     uuid REFERENCES zones,
  role        text NOT NULL,
  assigned_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, site_id)
);

CREATE TABLE site_enrollment_codes (
  code        text PRIMARY KEY,
  tenant_id   uuid NOT NULL REFERENCES tenants,
  site_id     uuid NOT NULL REFERENCES sites,
  zone_id     uuid REFERENCES zones,
  grants_role text NOT NULL DEFAULT 'occupant' CHECK (grants_role IN ('occupant')),
  expires_at  timestamptz,
  max_uses    int,
  uses        int NOT NULL DEFAULT 0,
  active      boolean NOT NULL DEFAULT true
);

CREATE TABLE manual_activation_votes (
  vote_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id    uuid NOT NULL REFERENCES sites,
  user_id    uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  consumed   boolean NOT NULL DEFAULT false
);

CREATE TABLE life_checkins (
  checkin_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid REFERENCES incidents,
  user_id     uuid NOT NULL,
  site_id     uuid NOT NULL REFERENCES sites,
  status      text NOT NULL CHECK (status IN ('safe','need_help')),
  geom        geography(Point,4326),
  zone_id     uuid REFERENCES zones,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 6. SERIES DE TIEMPO (TimescaleDB)
-- ---------------------------------------------------------------------------
CREATE TABLE waveform_features_1s (
  ts        timestamptz NOT NULL,
  tenant_id uuid NOT NULL,
  site_id   uuid NOT NULL,
  sensor_id uuid NOT NULL,
  channel   text NOT NULL,
  pga_g real, pgv_cms real, rms real, stalta real, energy real,
  clipping  boolean NOT NULL DEFAULT false,
  PRIMARY KEY (ts, sensor_id, channel)              -- idempotencia natural
);
SELECT create_hypertable('waveform_features_1s','ts', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX idx_wf_site_ts   ON waveform_features_1s (site_id, ts DESC);
CREATE INDEX idx_wf_tenant_ts ON waveform_features_1s (tenant_id, ts DESC);
ALTER TABLE waveform_features_1s SET (timescaledb.compress,
       timescaledb.compress_segmentby = 'sensor_id,channel');
SELECT add_compression_policy('waveform_features_1s', INTERVAL '7 days');
SELECT add_retention_policy   ('waveform_features_1s', INTERVAL '24 months');

CREATE TABLE device_health_10s (
  ts timestamptz NOT NULL,
  gateway_id uuid NOT NULL,
  mqtt_rtt_ms real, seedlink_lag_s real, ntp_offset_ms real,
  cpu_temp_c real, power_status text, battery_pct real, battery_min_left int,
  cert_days_remaining int,
  PRIMARY KEY (ts, gateway_id)
);
SELECT create_hypertable('device_health_10s','ts');
SELECT add_retention_policy('device_health_10s', INTERVAL '12 months');

CREATE MATERIALIZED VIEW site_metrics_1m
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 minute', ts) AS bucket, site_id,
       max(pga_g) AS max_pga_g, max(pgv_cms) AS max_pgv_cms
FROM waveform_features_1s
GROUP BY bucket, site_id;
SELECT add_continuous_aggregate_policy('site_metrics_1m',
  start_offset => INTERVAL '10 minutes', end_offset => INTERVAL '1 minute',
  schedule_interval => INTERVAL '1 minute');

-- ---------------------------------------------------------------------------
-- 7. EVIDENCIAS (S3) + AUDIT LOG
-- ---------------------------------------------------------------------------
CREATE TABLE evidence_objects (
  evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants,
  incident_id uuid REFERENCES incidents,
  sensor_id   uuid REFERENCES sensors,
  kind        text NOT NULL CHECK (kind IN ('miniseed','photo','report_pdf','log')),
  s3_key      text NOT NULL,
  ts_from     timestamptz, ts_to timestamptz,
  sha256      text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
  audit_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ts        timestamptz NOT NULL DEFAULT now(),
  tenant_id uuid,
  actor     text NOT NULL,
  verb      text NOT NULL,
  object    text NOT NULL,
  meta      jsonb NOT NULL DEFAULT '{}'
);
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- 8. ROW-LEVEL SECURITY
--    La API setea por transacción: SET LOCAL app.tenant_id / app.role / app.user_id
-- ---------------------------------------------------------------------------
ALTER TABLE sites                ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents            ENABLE ROW LEVEL SECURITY;
ALTER TABLE waveform_features_1s ENABLE ROW LEVEL SECURITY;
-- (Replicar ENABLE RLS + política en TODAS las tablas con tenant_id.)

CREATE POLICY tenant_isolation ON incidents
  USING (
    tenant_id = current_setting('app.tenant_id', true)::uuid
    OR (
      current_setting('app.role', true) = 'gov_operator'
      AND EXISTS (SELECT 1 FROM tenants t
                  WHERE t.tenant_id = incidents.tenant_id
                    AND t.visibility = 'gov_shared')
    )
  );

-- Patrón equivalente para sites y waveform_features_1s (ajustar nombre de tabla):
CREATE POLICY tenant_isolation ON sites
  USING (
    tenant_id = current_setting('app.tenant_id', true)::uuid
    OR (current_setting('app.role', true) = 'gov_operator'
        AND visibility_of_tenant(tenant_id))
  );
-- NOTA: definir helper visibility_of_tenant() o inline EXISTS como arriba. La migración
-- T-1.3 debe materializar la política en cada tabla multi-tenant con su columna tenant_id.
