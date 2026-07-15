-- ============================================================================
-- TAKAB Technology · Esquema de producción consolidado · v1.1
-- PostgreSQL 16 + TimescaleDB 2.x + PostGIS 3.x
-- Fuente de verdad única. Combina núcleo (Fase 0) + tablas de auth (RBAC).
-- Aplicar vía Alembic (tarea T-1.16). NO reinventar; extender solo con migración.
--
-- [ANALISIS-00] v1.1 · rama analisis/arquitectura-00 — cambios respecto a v1:
--   1. Política RLS de `sites` reparada (invocaba visibility_of_tenant(), inexistente:
--      el script v1 NO aplicaba limpio).
--   2. RLS habilitada y FORZADA en TODAS las tablas de negocio (v1 solo cubría 3);
--      políticas de lectura y escritura separadas (gov_operator = solo lectura),
--      ramas para roles internos TAKAB y nota del rol de ingesta.
--   3. Inmutabilidad real de evidencia: incident_actions sin ON DELETE CASCADE,
--      triggers append-only en audit_log/incident_actions/dictamens/evidence_objects/
--      life_checkins, dictámenes versionados por fila nueva (supersedes_dictamen_id).
--   4. `device_health_10s` (logging por intervalo, violaba P5) → `device_health`
--      (por transición + heartbeat, columna `reason`).
--   5. tenant_id añadido a zones, dictamens, manual_activation_votes, life_checkins,
--      device_health, rule_evaluations (regla de oro 5). Excepción documentada:
--      seismic_events y quorum_votes son datos DE RED (multi-tenant por diseño).
--   6. Continuous aggregates con tenant_id + agregado 1h; segmentby de compresión
--      incluye tenant_id/site_id. Los caggs NO soportan RLS: nunca exponerlos a la
--      API sin JOIN a `sites` (que sí tiene RLS).
--   7. Hypertable `rule_evaluations` (por transición de tier, P5) añadida — la
--      exigía el blueprint §5.4 y no existía.
--   Detalle y razones: takab-docs/ANALISIS-ARQUITECTURA-TAKAB.md
--
-- [ANALISIS-00] v1.2 · T-1.16 — conflicto TimescaleDB RLS ↔ columnstore/caggs:
--   TimescaleDB (issue timescale/timescaledb#6827, abierto) NO permite en una misma
--   hypertable: (a) compresión/columnstore + RLS, ni (b) continuous aggregates + RLS.
--   Se descubrió al aplicar el schema en TimescaleDB 2.28 (T-1.16). Correcciones:
--     1. waveform_features_1s (tiene caggs) → SIN RLS y SIN compresión. Aislamiento
--        por tenant vía la vista security_barrier `waveform_features_1s_secure`
--        (JOIN a `sites`, que sí tiene RLS+FORCE) + REVOKE de la base a takab_app.
--     2. device_health / rule_evaluations (sin caggs) → conservan RLS pero PIERDEN
--        compresión (incompatible con RLS). Retención intacta.
--     3. El ahorro de almacenamiento se traslada del crudo a los caggs
--        (site_metrics_1m/1h), que no llevan RLS: se comprimen.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- 0. ROLES DE CONEXIÓN ESPERADOS ([ANALISIS-00] — documentación operativa)
--    · takab_migrator : dueño de los objetos; SOLO corre migraciones (Alembic).
--    · takab_app      : rol de la API. NO es dueño de tablas → FORCE RLS lo cubre.
--    · takab_ingest   : workers de ingesta (SQS→Timescale). Único rol con BYPASSRLS,
--                       sin login interactivo; escribe series de tiempo e incidentes
--                       ya etiquetados con tenant_id por el edge.
--    La API DEBE setear por transacción:
--      SET LOCAL app.tenant_id = '<uuid>'; SET LOCAL app.role = '<rol>';
--      SET LOCAL app.user_id  = '<sub>';
--    (los CREATE ROLE viven en infra/terraform + migración inicial, no aquí).
-- ---------------------------------------------------------------------------

-- Guard genérico de tablas append-only ([ANALISIS-00] inmutabilidad de evidencia/compliance)
CREATE FUNCTION forbid_update_delete() RETURNS trigger
  LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'tabla append-only: % no permite %', TG_TABLE_NAME, TG_OP;
END $$;

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
  -- [T-1.32] Retiro lógico: un sitio nunca se borra (evidencia y auditoría de sus
  -- incidentes lo referencian; regla de oro 11).
  status        text NOT NULL DEFAULT 'active' CHECK (status IN ('active','retired')),
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, code)
);
CREATE INDEX idx_sites_geom   ON sites USING GIST (geom);
CREATE INDEX idx_sites_tenant ON sites (tenant_id);
CREATE INDEX idx_sites_active ON sites (tenant_id) WHERE status = 'active';

CREATE TABLE zones (
  zone_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenants,   -- [ANALISIS-00] regla de oro 5 + RLS directa
  site_id    uuid NOT NULL REFERENCES sites ON DELETE CASCADE,
  name       text NOT NULL,
  level_code text,
  zone_geom  geometry(Polygon,4326)
);
CREATE INDEX idx_zones_site ON zones (site_id);

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
  -- [ANALISIS-00] RS4D real: EHZ (geófono) + ENZ/ENN/ENE (acelerómetro), 100 sps
  channels    text[] NOT NULL DEFAULT '{EHZ,ENZ,ENN,ENE}',
  sample_rate int  NOT NULL DEFAULT 100,
  mount       text CHECK (mount IN ('concrete_column','steel','floor','buried')),
  geom        geography(Point,4326),
  status      text NOT NULL DEFAULT 'active',
  -- [T-1.33] Procedencia de la respuesta instrumental (p.ej. 'stationxml:AM.R4F74').
  -- calibrated := (calibration_source IS NOT NULL). No hay booleano suelto que pueda
  -- mentir: para declararte calibrado tienes que nombrar la fuente. Mientras sea NULL,
  -- PGA/PGV son RELATIVOS (las sensibilidades del edge son placeholder) y la UI lo dice.
  calibration_source text,
  metadata    jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_sensors_site ON sensors (site_id);

-- Un sitio puede referenciar el sensor de terreno de un sitio vecino.
-- [ANALISIS-00] Supuesto MVP: ambos sitios pertenecen al MISMO tenant (la política
-- RLS de abajo lo asume). Compartir terreno entre tenants = decisión futura.
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
  -- [ANALISIS-00] Ejemplo de config. La ventana de quórum es CONSCIENTE DE DISTANCIA
  -- (una ventana fija de 2–5 s es físicamente inalcanzable entre sitios a 90–110 km;
  -- ver ANALISIS-ARQUITECTURA-TAKAB.md hallazgo A1):
  --   {thresholds:{...},
  --    quorum:{min_nodes:3, assoc:'distance', v_p_km_s:6.5, margin_s:3, max_window_s:30},
  --    relays:{siren:'NO', doors:'NC', gas:'fail_close'}}
  config      jsonb NOT NULL,
  created_by  uuid,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (scope_type, scope_id, version)
);

-- ---------------------------------------------------------------------------
-- 4. EVENTOS, INCIDENTES, QUÓRUM, DICTÁMENES
-- ---------------------------------------------------------------------------
-- [ANALISIS-00] EXCEPCIÓN DOCUMENTADA a la regla "tenant_id en toda tabla":
-- seismic_events y quorum_votes son datos DE RED (un evento regional cruza tenants
-- por definición del quórum colaborativo). Lectura compartida; escritura solo del
-- motor de incidentes (takab_ingest / roles internos).
CREATE TABLE seismic_events (
  event_id    text PRIMARY KEY,                       -- 'EVT-20260510-0843'
  source      text NOT NULL CHECK (source IN ('sasmex','local_quorum','manual','external')),
  -- [ANALISIS-00] magnitude = enriquecimiento POST-HOC (SSN/catálogo, minutos después).
  -- NO es "magnitud preliminar" en vivo: el WR-1 es booleano y la UI MVP no la muestra
  -- (blueprint §14). No leer esta columna como feature de alertamiento.
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

-- [ANALISIS-00] Sin ON DELETE CASCADE: borrar un incidente NO puede borrar su timeline
-- auditable (inmutabilidad de evidencia). Los incidentes no se borran; se cierran.
CREATE TABLE incident_actions (
  action_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid NOT NULL REFERENCES incidents ON DELETE RESTRICT,
  tenant_id   uuid NOT NULL REFERENCES tenants,      -- [ANALISIS-00] RLS directa sin join
  ts          timestamptz NOT NULL DEFAULT now(),
  kind        text NOT NULL,    -- 'siren_on','siren_test','gas_closed','ack','dictamen','notify_sent'
  actor       text NOT NULL,    -- 'edge:CHL-A' | 'user:uuid' | 'system'
  payload     jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_actions_incident ON incident_actions (incident_id, ts);
CREATE TRIGGER trg_incident_actions_append_only
  BEFORE UPDATE OR DELETE ON incident_actions
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

-- [ANALISIS-00] Dictámenes INMUTABLES e versionados: firmar o corregir = INSERTAR una
-- fila nueva que apunta a la anterior vía supersedes_dictamen_id. Nunca UPDATE/DELETE.
CREATE TABLE dictamens (
  dictamen_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants,      -- [ANALISIS-00] regla de oro 5
  incident_id uuid NOT NULL REFERENCES incidents,
  status      text NOT NULL CHECK (status IN
              ('normal_operation','inhabit_monitor','restricted','no_inhabit_inspect')),
  basis       jsonb NOT NULL,
  signed_by   uuid,                                  -- NULL = preliminar automático sin firma
  supersedes_dictamen_id uuid REFERENCES dictamens,  -- [ANALISIS-00] cadena de versiones
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_dictamens_incident ON dictamens (incident_id, created_at DESC);
CREATE TRIGGER trg_dictamens_append_only
  BEFORE UPDATE OR DELETE ON dictamens
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

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
  tenant_id  uuid NOT NULL REFERENCES tenants,       -- [ANALISIS-00] regla de oro 5
  site_id    uuid NOT NULL REFERENCES sites,
  user_id    uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  consumed   boolean NOT NULL DEFAULT false
);
-- [ANALISIS-00] La consulta del quórum de 2 ocupantes filtra por sitio + ventana de 30 s:
CREATE INDEX idx_manual_votes_site_ts ON manual_activation_votes (site_id, created_at DESC);

CREATE TABLE life_checkins (
  checkin_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants,      -- [ANALISIS-00] regla de oro 5
  incident_id uuid REFERENCES incidents,
  user_id     uuid NOT NULL,
  site_id     uuid NOT NULL REFERENCES sites,
  status      text NOT NULL CHECK (status IN ('safe','need_help')),
  geom        geography(Point,4326),                 -- PII de ubicación → LFPDPPP (§9)
  zone_id     uuid REFERENCES zones,
  created_at  timestamptz NOT NULL DEFAULT now()
);
-- [ANALISIS-00] Cambios de estado = fila nueva (historial de rescate auditable).
CREATE TRIGGER trg_life_checkins_append_only
  BEFORE UPDATE OR DELETE ON life_checkins
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

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
-- [ANALISIS-00 v1.2] waveform_features_1s NO lleva compresión (columnstore) NI RLS:
-- TimescaleDB prohíbe columnstore sobre una hypertable con RLS y prohíbe crear
-- continuous aggregates sobre una hypertable con RLS (timescale/timescaledb#6827);
-- esta tabla tiene ambos (caggs site_metrics_1m/1h). El aislamiento por tenant se
-- resuelve con la vista security_barrier `waveform_features_1s_secure` (más abajo);
-- el ahorro de almacenamiento se traslada a la compresión de los caggs. La retención
-- de la cruda se mantiene.
SELECT add_retention_policy   ('waveform_features_1s', INTERVAL '24 months');

-- [ANALISIS-00] device_health_10s (muestreo por intervalo de 10 s) violaba P5
-- ("logging por evento, no por intervalo") y contradecía blueprint §5.4 y TASKS
-- T-1.10/T-1.17/T-1.28. Renombrada y re-semantizada: una fila POR TRANSICIÓN de
-- estado + heartbeat periódico espaciado (reason lo distingue).
CREATE TABLE device_health (
  ts timestamptz NOT NULL,
  tenant_id  uuid NOT NULL,                          -- [ANALISIS-00] RLS sin join
  gateway_id uuid NOT NULL,
  reason     text NOT NULL CHECK (reason IN ('transition','heartbeat')),
  mqtt_rtt_ms real, seedlink_lag_s real, ntp_offset_ms real,
  cpu_temp_c real, power_status text, battery_pct real, battery_min_left int,
  cert_days_remaining int,
  PRIMARY KEY (ts, gateway_id)
);
SELECT create_hypertable('device_health','ts');
-- [ANALISIS-00 v1.2] device_health conserva RLS (no tiene caggs) pero PIERDE la
-- compresión: columnstore y RLS son incompatibles en la misma hypertable
-- (timescale/timescaledb#6827). Se prioriza el aislamiento. Retención intacta.
SELECT add_retention_policy  ('device_health', INTERVAL '12 months');

-- [ANALISIS-00] Transiciones del motor de reglas (blueprint §5.4, P5: por transición,
-- nunca por intervalo). Faltaba en v1: los cambios de tier sin incidente (p. ej.
-- normal→watch) no tenían dónde registrarse.
CREATE TABLE rule_evaluations (
  ts          timestamptz NOT NULL,
  tenant_id   uuid NOT NULL,
  site_id     uuid NOT NULL,
  gateway_id  uuid NOT NULL,
  prev_tier   text NOT NULL,
  new_tier    text NOT NULL CHECK (new_tier IN
              ('normal','watch','restricted','evacuate_or_hold','manual_only')),
  rule_set_version int,
  basis       jsonb NOT NULL DEFAULT '{}',           -- feature(s) que gatillaron
  PRIMARY KEY (ts, gateway_id)
);
SELECT create_hypertable('rule_evaluations','ts');
SELECT add_retention_policy('rule_evaluations', INTERVAL '24 months');
CREATE TRIGGER trg_rule_evaluations_append_only
  BEFORE UPDATE OR DELETE ON rule_evaluations
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

-- [ANALISIS-00] Los continuous aggregates NO soportan RLS en TimescaleDB.
-- El aislamiento por tenant lo dan las vistas `site_metrics_1{m,h}_secure` (más
-- abajo): security_barrier + JOIN a `sites` (RLS+FORCE), con SELECT concedido solo
-- sobre la vista y REVOCADO sobre el cagg base a takab_app (migración 0008). La API
-- lee por `*_secure`; el cagg base solo lo lee takab_ingest/BYPASSRLS.
CREATE MATERIALIZED VIEW site_metrics_1m
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 minute', ts) AS bucket, tenant_id, site_id,
       max(pga_g) AS max_pga_g, max(pgv_cms) AS max_pgv_cms
FROM waveform_features_1s
GROUP BY bucket, tenant_id, site_id;
SELECT add_continuous_aggregate_policy('site_metrics_1m',
  start_offset => INTERVAL '10 minutes', end_offset => INTERVAL '1 minute',
  schedule_interval => INTERVAL '1 minute');
-- [ANALISIS-00 v1.2] El ahorro de almacenamiento se traslada del crudo al cagg
-- (los caggs no llevan RLS → sí admiten columnstore).
ALTER MATERIALIZED VIEW site_metrics_1m SET (timescaledb.compress = true);
SELECT add_compression_policy('site_metrics_1m', compress_after => INTERVAL '30 days');

-- [ANALISIS-00] Agregado 1h (blueprint §5.4 lo lista; faltaba en v1) para rangos largos
-- del Triage/históricos sin escanear el crudo de 1 s.
CREATE MATERIALIZED VIEW site_metrics_1h
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', ts) AS bucket, tenant_id, site_id,
       max(pga_g) AS max_pga_g, max(pgv_cms) AS max_pgv_cms
FROM waveform_features_1s
GROUP BY bucket, tenant_id, site_id;
SELECT add_continuous_aggregate_policy('site_metrics_1h',
  start_offset => INTERVAL '3 hours', end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '30 minutes');
ALTER MATERIALIZED VIEW site_metrics_1h SET (timescaledb.compress = true);
SELECT add_compression_policy('site_metrics_1h', compress_after => INTERVAL '90 days');

-- [ANALISIS-00 v1.2] Vista de aislamiento del crudo. waveform_features_1s no puede
-- llevar RLS (tiene caggs), así que el acceso multi-tenant de la API pasa por esta
-- vista: security_barrier + JOIN a `sites` (RLS+FORCE). A takab_app se le concede
-- SELECT SOLO sobre la vista y se le REVOCA la tabla base (grants en la migración
-- T-1.16); takab_ingest escribe la base directamente (BYPASSRLS). Semántica definer:
-- aunque la ejecute el dueño de la vista, `sites` filtra por app.tenant_id de sesión
-- porque tiene FORCE. gov_operator ve el crudo de tenants gov_shared (herencia de
-- la política de `sites`), consistente con la matriz de visibilidad de §8.
CREATE VIEW waveform_features_1s_secure WITH (security_barrier = true) AS
  SELECT wf.* FROM waveform_features_1s wf JOIN sites s ON s.site_id = wf.site_id;

-- Vistas de aislamiento de los caggs (mismo patrón que el crudo): security_barrier
-- + JOIN a `sites` (RLS+FORCE). El SELECT sobre el cagg base se REVOCA a takab_app y
-- se concede solo sobre estas vistas (migración 0008). Owner takab_migrator
-- (NO-superusuario) para que el FORCE RLS de `sites` sujete la lectura.
CREATE VIEW site_metrics_1m_secure WITH (security_barrier = true) AS
  SELECT m.* FROM site_metrics_1m m JOIN sites s ON s.site_id = m.site_id;
CREATE VIEW site_metrics_1h_secure WITH (security_barrier = true) AS
  SELECT m.* FROM site_metrics_1h m JOIN sites s ON s.site_id = m.site_id;

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
CREATE TRIGGER trg_evidence_append_only
  BEFORE UPDATE OR DELETE ON evidence_objects
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

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
-- [ANALISIS-00] El REVOKE solo no basta (el owner y grants explícitos lo saltan):
CREATE TRIGGER trg_audit_log_append_only
  BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
-- [T-1.57] Lectura keyset de GET /audit (0012): orden exacto del cursor y
-- acceso por tenant (la RLS audit_read filtra por tenant_id).
CREATE INDEX idx_audit_log_ts_id ON audit_log (ts DESC, audit_id DESC);
CREATE INDEX idx_audit_log_tenant_ts ON audit_log (tenant_id, ts DESC);

-- ---------------------------------------------------------------------------
-- 8. ROW-LEVEL SECURITY ([ANALISIS-00] sección reescrita — v1 solo cubría 3 tablas,
--    invocaba un helper inexistente y su política única FOR ALL dejaba escribir a
--    gov_operator sobre tenants gov_shared)
--
--    Patrón por tabla de negocio:
--      · ENABLE + FORCE (FORCE cubre también al dueño de la tabla).
--      · Política de LECTURA:  tenant propio ∪ roles internos TAKAB ∪ (gov_operator
--        solo en tablas marcadas visibles a gobierno).
--      · Política de ESCRITURA: tenant propio Y rol ≠ gov_operator (gov = solo
--        lectura + acuse; el acuse pasa por la API con validación de transición).
--      · takab_ingest (workers) escribe con BYPASSRLS — no aparece en políticas.
-- ---------------------------------------------------------------------------

-- Helpers de sesión ([ANALISIS-00]; van aquí y no al inicio: app_gov_can_see referencia
-- `tenants` y las funciones LANGUAGE sql validan su cuerpo al crearse)
CREATE FUNCTION app_tenant_id() RETURNS uuid
  LANGUAGE sql STABLE AS
  $$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $$;

CREATE FUNCTION app_role() RETURNS text
  LANGUAGE sql STABLE AS
  $$ SELECT current_setting('app.role', true) $$;

-- Roles internos TAKAB: visibilidad total (auditada vía audit_log).
CREATE FUNCTION app_is_takab_internal() RETURNS boolean
  LANGUAGE sql STABLE AS
  $$ SELECT app_role() IN ('takab_superadmin', 'takab_support') $$;

-- gov_operator solo ve tenants con visibility = 'gov_shared' (y SOLO lectura).
-- SECURITY DEFINER (+search_path fijo): PostgreSQL verifica privilegios sobre `tenants`
-- al planear la política AUNQUE el AND no llegue a evaluarse — sin esto, todo rol que
-- consulte una tabla gov-visible necesitaría GRANT sobre tenants (hallazgo del smoke test).
CREATE FUNCTION app_gov_can_see(t uuid) RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
  $$ SELECT app_role() = 'gov_operator'
       AND EXISTS (SELECT 1 FROM tenants x
                   WHERE x.tenant_id = t AND x.visibility = 'gov_shared') $$;

-- ---------------------------------------------------------------------------
-- [T-1.73] Visibilidad configurable entre clientes.
-- El superadmin concede, por cliente (grantee), ver METADATOS (que EXISTEN las
-- estaciones) y/o DATOS en vivo (formas de onda, métricas, salud, incidentes) de
-- otro tenant (o de TODOS). Default-deny: sin fila de grant, cero acceso extra.
-- NUNCA concede escritura (las políticas *_write/*_admin no se tocan). superadmin/
-- support/gov mantienen su visibilidad; esto SOLO añade ramas de LECTURA.
-- ---------------------------------------------------------------------------
CREATE TABLE visibility_grants (
  grant_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  grantee_tenant_id uuid NOT NULL REFERENCES tenants ON DELETE CASCADE,
  target_tenant_id  uuid REFERENCES tenants ON DELETE CASCADE,  -- NULL sii target_all
  target_all        boolean NOT NULL DEFAULT false,             -- 'TODOS los clientes'
  can_view_metadata boolean NOT NULL DEFAULT false,
  can_view_data     boolean NOT NULL DEFAULT false,
  created_by        uuid NOT NULL,                              -- sub del superadmin (auditoría)
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  -- exactamente uno de {target específico, TODOS}; sin auto-grant; sin grant vacío.
  CONSTRAINT vg_target_shape CHECK (
    (target_all AND target_tenant_id IS NULL) OR
    (NOT target_all AND target_tenant_id IS NOT NULL)),
  CONSTRAINT vg_no_self CHECK (target_all OR grantee_tenant_id <> target_tenant_id),
  CONSTRAINT vg_nonempty CHECK (can_view_metadata OR can_view_data)
);
-- una fila por (grantee, target específico) y una fila TODOS por grantee (upsert).
CREATE UNIQUE INDEX uq_vg_specific ON visibility_grants (grantee_tenant_id, target_tenant_id)
  WHERE NOT target_all;
CREATE UNIQUE INDEX uq_vg_all ON visibility_grants (grantee_tenant_id) WHERE target_all;
CREATE INDEX idx_vg_grantee ON visibility_grants (grantee_tenant_id);  -- hot path de los helpers

ALTER TABLE visibility_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE visibility_grants FORCE  ROW LEVEL SECURITY;
-- El grantee ve SUS grants (qué le compartieron); los internos TAKAB ven todo.
CREATE POLICY vg_read  ON visibility_grants FOR SELECT
  USING (grantee_tenant_id = app_tenant_id() OR app_is_takab_internal());
-- Conceder/revocar es acto del DUEÑO de la plataforma (misma llave que tenants_admin).
CREATE POLICY vg_admin ON visibility_grants FOR ALL
  USING (app_role() = 'takab_superadmin') WITH CHECK (app_role() = 'takab_superadmin');
GRANT SELECT, INSERT, UPDATE, DELETE ON visibility_grants TO takab_app;

-- "el grantee puede ver que EXISTEN las estaciones de t" — implícito por CUALQUIER grant
-- (ver datos ⊇ ver que existe). SECURITY DEFINER + search_path fijo igual que
-- app_gov_can_see: Postgres valida el privilegio sobre visibility_grants al planear la
-- política aunque el OR no llegue a evaluarse. app_tenant_id() sigue siendo el de la
-- sesión (DEFINER cambia el rol, no los GUCs).
CREATE FUNCTION app_can_view_meta(t uuid) RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
  $$ SELECT EXISTS (SELECT 1 FROM visibility_grants g
                     WHERE g.grantee_tenant_id = app_tenant_id()
                       AND (g.can_view_metadata OR g.can_view_data)
                       AND (g.target_all OR g.target_tenant_id = t)) $$;

-- "el grantee puede ver los DATOS en vivo de t" — estrictamente can_view_data.
CREATE FUNCTION app_can_view_data(t uuid) RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS
  $$ SELECT EXISTS (SELECT 1 FROM visibility_grants g
                     WHERE g.grantee_tenant_id = app_tenant_id()
                       AND g.can_view_data
                       AND (g.target_all OR g.target_tenant_id = t)) $$;

-- [T-1.73] Las vistas seguras (creadas arriba SIN WHERE) se REDEFINEN aquí, ya con los
-- helpers disponibles, para gatear los DATOS por su cuenta. CLAVE (crux metadata≠datos):
-- como aíslan por JOIN sites y sites_read se amplía abajo con app_can_view_meta, un grant
-- de SOLO-metadatos haría casar el JOIN → sin este WHERE filtraría formas de onda. El
-- WHERE re-estrecha al eje de DATOS. CREATE OR REPLACE preserva owner (takab_migrator) y
-- grants; el SELECT (columnas) no cambia, solo se añade el WHERE.
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

-- ---- tablas visibles a gov_operator (C4I/Flota/Triage de tenants gov_shared) ----
-- sites, zones, gateways, sensors, incidents, incident_actions, dictamens,
-- evidence_objects, waveform_features_1s, device_health, rule_evaluations

ALTER TABLE sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE sites FORCE  ROW LEVEL SECURITY;
CREATE POLICY sites_read  ON sites FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id)
         OR app_can_view_meta(tenant_id));   -- [T-1.73] grant de metadatos
CREATE POLICY sites_write ON sites FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY sites_admin ON sites FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

ALTER TABLE zones ENABLE ROW LEVEL SECURITY;
ALTER TABLE zones FORCE  ROW LEVEL SECURITY;
CREATE POLICY zones_read  ON zones FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id)
         OR app_can_view_meta(tenant_id));   -- [T-1.73] grant de metadatos
CREATE POLICY zones_write ON zones FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY zones_admin ON zones FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

ALTER TABLE gateways ENABLE ROW LEVEL SECURITY;
ALTER TABLE gateways FORCE  ROW LEVEL SECURITY;
CREATE POLICY gateways_read  ON gateways FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id)
         OR app_can_view_meta(tenant_id));   -- [T-1.73] grant de metadatos
CREATE POLICY gateways_write ON gateways FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY gateways_admin ON gateways FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

ALTER TABLE sensors ENABLE ROW LEVEL SECURITY;
ALTER TABLE sensors FORCE  ROW LEVEL SECURITY;
CREATE POLICY sensors_read  ON sensors FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id)
         OR app_can_view_meta(tenant_id));   -- [T-1.73] grant de metadatos
CREATE POLICY sensors_write ON sensors FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY sensors_admin ON sensors FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

ALTER TABLE site_ground_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_ground_refs FORCE  ROW LEVEL SECURITY;
CREATE POLICY sgr_read ON site_ground_refs FOR SELECT
  USING (EXISTS (SELECT 1 FROM sites s WHERE s.site_id = site_ground_refs.site_id));
CREATE POLICY sgr_write ON site_ground_refs FOR ALL
  USING (EXISTS (SELECT 1 FROM sites s WHERE s.site_id = site_ground_refs.site_id
                   AND s.tenant_id = app_tenant_id()) AND app_role() <> 'gov_operator')
  WITH CHECK (EXISTS (SELECT 1 FROM sites s WHERE s.site_id = site_ground_refs.site_id
                        AND s.tenant_id = app_tenant_id()) AND app_role() <> 'gov_operator');
-- (la visibilidad de sgr_read hereda el RLS de `sites` vía el EXISTS)

ALTER TABLE rule_sets ENABLE ROW LEVEL SECURITY;
ALTER TABLE rule_sets FORCE  ROW LEVEL SECURITY;
CREATE POLICY rule_sets_read  ON rule_sets FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());   -- sin rama gov (Multi-Tenant = "—")
CREATE POLICY rule_sets_write ON rule_sets FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY rule_sets_admin ON rule_sets FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

ALTER TABLE incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents FORCE  ROW LEVEL SECURITY;
CREATE POLICY incidents_read  ON incidents FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id)
         OR app_can_view_data(tenant_id));   -- [T-1.73] grant de datos
CREATE POLICY incidents_write ON incidents FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY incidents_admin ON incidents FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());
-- [ANALISIS-00] Acuse de gov_operator: UPDATE limitado (state open→acked) se ejecuta
-- vía la API con SET LOCAL app.role='soc_operator' de servicio NO — se ejecuta como
-- función SECURITY DEFINER dedicada `gov_ack_incident(incident_id)` (migración T-1.16)
-- que valida visibility='gov_shared' + transición y escribe audit_log. Sin esa función,
-- gov NO tiene escritura alguna a nivel de fila.

ALTER TABLE incident_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_actions FORCE  ROW LEVEL SECURITY;
CREATE POLICY actions_read ON incident_actions FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id)
         OR app_can_view_data(tenant_id));   -- [T-1.73] grant de datos (timeline del incidente)
CREATE POLICY actions_insert ON incident_actions FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY actions_admin ON incident_actions FOR INSERT
  WITH CHECK (app_is_takab_internal());
-- (sin política UPDATE/DELETE: además del trigger append-only, RLS los niega por defecto)

ALTER TABLE dictamens ENABLE ROW LEVEL SECURITY;
ALTER TABLE dictamens FORCE  ROW LEVEL SECURITY;
CREATE POLICY dictamens_read ON dictamens FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id));
CREATE POLICY dictamens_insert ON dictamens FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY dictamens_admin ON dictamens FOR INSERT
  WITH CHECK (app_is_takab_internal());

ALTER TABLE evidence_objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_objects FORCE  ROW LEVEL SECURITY;
CREATE POLICY evidence_read ON evidence_objects FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id));
CREATE POLICY evidence_insert ON evidence_objects FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY evidence_admin ON evidence_objects FOR INSERT
  WITH CHECK (app_is_takab_internal());

-- [ANALISIS-00] Hypertables con RLS: ENABLE sin FORCE. Razón: los jobs de TimescaleDB
-- (retención, refresh de caggs) corren como el OWNER; con FORCE el owner queda sujeto a
-- RLS y los jobs verían 0 filas. La API sigue restringida: se conecta como `takab_app`,
-- que NUNCA es owner. T-1.16 verifica jobs + RLS en TimescaleDB real.
-- [ANALISIS-00 v1.2] waveform_features_1s NO lleva RLS: TimescaleDB prohíbe RLS en una
-- hypertable con continuous aggregates (timescale/timescaledb#6827) y esta los tiene.
-- Su aislamiento por tenant lo da la vista `waveform_features_1s_secure` (§6) + el
-- REVOKE de la tabla base a takab_app (migración). Escritura: solo takab_ingest/BYPASSRLS.

ALTER TABLE device_health ENABLE ROW LEVEL SECURITY;
CREATE POLICY dh_read ON device_health FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id)
         OR app_can_view_data(tenant_id));   -- [T-1.73] grant de datos (salud del gabinete)

ALTER TABLE rule_evaluations ENABLE ROW LEVEL SECURITY;
CREATE POLICY re_read ON rule_evaluations FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id)
         OR app_can_view_data(tenant_id));   -- [T-1.73] grant de datos

-- ---- datos de red (excepción documentada; lectura para todo usuario autenticado) ----
ALTER TABLE seismic_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE seismic_events FORCE  ROW LEVEL SECURITY;
CREATE POLICY se_read ON seismic_events FOR SELECT
  USING (app_role() IS NOT NULL);          -- evento regional = contexto compartido
-- escritura: solo motor de incidentes (takab_ingest/BYPASSRLS)

ALTER TABLE quorum_votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE quorum_votes FORCE  ROW LEVEL SECURITY;
CREATE POLICY qv_read ON quorum_votes FOR SELECT
  USING (app_role() IS NOT NULL);
-- Nota: sensor_id ajeno no es resoluble por otros tenants (RLS de `sensors` lo tapa).

-- ---- tablas de auth / PII (sin rama gov_operator) ----
ALTER TABLE user_zone_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_zone_assignments FORCE  ROW LEVEL SECURITY;
CREATE POLICY uza_read  ON user_zone_assignments FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY uza_write ON user_zone_assignments FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY uza_admin ON user_zone_assignments FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

ALTER TABLE site_enrollment_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_enrollment_codes FORCE  ROW LEVEL SECURITY;
CREATE POLICY sec_read  ON site_enrollment_codes FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY sec_write ON site_enrollment_codes FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY sec_admin ON site_enrollment_codes FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

ALTER TABLE manual_activation_votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE manual_activation_votes FORCE  ROW LEVEL SECURITY;
CREATE POLICY mav_read  ON manual_activation_votes FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY mav_write ON manual_activation_votes FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');

ALTER TABLE life_checkins ENABLE ROW LEVEL SECURITY;
ALTER TABLE life_checkins FORCE  ROW LEVEL SECURITY;
CREATE POLICY lc_read ON life_checkins FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY lc_insert ON life_checkins FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE  ROW LEVEL SECURITY;
CREATE POLICY audit_read ON audit_log FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY audit_insert ON audit_log FOR INSERT
  WITH CHECK (true);   -- cualquier request autenticado registra; lectura sí restringida

-- tenants: catálogo. Cada quien ve su propia fila; internos ven todo; gov ve las
-- filas gov_shared (necesario para resolver nombres en su consola).
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE  ROW LEVEL SECURITY;
CREATE POLICY tenants_read ON tenants FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR (app_role() = 'gov_operator' AND visibility = 'gov_shared')
         OR app_can_view_meta(tenant_id));   -- [T-1.73] resolver el nombre del cliente compartido
CREATE POLICY tenants_admin ON tenants FOR ALL
  USING (app_role() = 'takab_superadmin') WITH CHECK (app_role() = 'takab_superadmin');

-- ---------------------------------------------------------------------------
-- Fase C (migraciones 0005–0007): comandos firmados, config sync, cascada de
-- notificación y billing. [T-1.45] Reconciliación: estas tablas nacieron en
-- Alembic y este archivo —fuente de verdad del DDL— las había perdido; el
-- diff sistemático de catálogos (alembic head vs schema.sql sobre DBs
-- gemelas) volvió a CERO drift al añadirlas. DDL transcrito fiel de pg_dump.
-- ---------------------------------------------------------------------------

-- Comandos remotos de actuador (T-1.23 · regla de oro 8): la superficie más
-- sensible. pending → acked/rejected (ack del edge) o expired (TTL). El nonce
-- es UNIQUE: anti-replay del lado nube (el edge además guarda nonces vistos).
CREATE TABLE commands (
  command_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
  site_id     uuid NOT NULL REFERENCES sites(site_id),
  gateway_id  uuid NOT NULL REFERENCES gateways(gateway_id),
  issued_by   uuid NOT NULL,
  -- [T-1.59] 'system'/'self_test': autodiagnóstico del gabinete (0013). El
  -- router exige el cruce self_test ⇔ system; el edge pulsa relés NO audibles.
  -- [T-1.60] 'drill_start'/'drill_stop' (0015): simulacro institucional — SOLO
  -- se emiten vía /drills (el endpoint público de comandos no los acepta).
  channel     text NOT NULL CHECK (channel IN ('siren','strobe','gas_valve','elevator','door_retainer','system')),
  action      text NOT NULL CHECK (action IN ('activate','deactivate','self_test','drill_start','drill_stop')),
  event_id    text,
  nonce       text NOT NULL UNIQUE,
  issued_at   timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,
  status      text NOT NULL DEFAULT 'pending'
              CHECK (status IN ('pending','acked','rejected','expired')),
  ack         jsonb,
  error       text
);
CREATE INDEX idx_commands_site    ON commands (site_id, issued_at DESC);
CREATE INDEX idx_commands_rate    ON commands (issued_by, site_id, issued_at DESC);
CREATE INDEX idx_commands_pending ON commands (expires_at) WHERE status = 'pending';
GRANT SELECT, INSERT, UPDATE ON commands TO takab_app;    -- la API emite y lista
GRANT SELECT, INSERT, UPDATE ON commands TO takab_ingest; -- el ack transiciona el estado

ALTER TABLE commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE commands FORCE  ROW LEVEL SECURITY;
CREATE POLICY commands_read  ON commands FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY commands_write ON commands FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY commands_admin ON commands FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

-- Config firmada que cada gateway tiene REALMENTE (T-1.23): versión MONÓTONA
-- por gabinete; el worker de sync solo publica cuando el payload difiere.
CREATE TABLE gateway_config_state (
  gateway_id   uuid PRIMARY KEY REFERENCES gateways(gateway_id),
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  version      integer NOT NULL,
  payload      jsonb NOT NULL,
  sig          text NOT NULL,
  published_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT ON gateway_config_state TO takab_app;
GRANT SELECT, INSERT, UPDATE ON gateway_config_state TO takab_ingest;

ALTER TABLE gateway_config_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE gateway_config_state FORCE  ROW LEVEL SECURITY;
CREATE POLICY gateway_config_state_read ON gateway_config_state FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY gateway_config_state_admin ON gateway_config_state FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

-- Cascada de notificación (T-1.21 · blueprint §5.6): un job por (incidente,
-- canal, modo) — UNIQUE = idempotencia del orquestador ante re-entregas.
CREATE TABLE notification_jobs (
  job_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
  incident_id uuid NOT NULL REFERENCES incidents(incident_id) ON DELETE RESTRICT,
  channel     text NOT NULL CHECK (channel IN ('webhook','whatsapp','sms','email')),
  mode        text NOT NULL CHECK (mode IN ('cascade','parallel')),
  position    integer NOT NULL DEFAULT 0,
  status      text NOT NULL DEFAULT 'pending'
              CHECK (status IN ('pending','sent','failed','skipped')),
  target      jsonb NOT NULL DEFAULT '{}',
  due_at      timestamptz NOT NULL,
  deadline_at timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now(),
  sent_at     timestamptz,
  error       text,
  -- [T-1.61] Job disparado por una ACCIÓN (dictamen_request → inspector);
  -- NULL = job de incidente (cascada/paralelo clásicos).
  action_id   uuid REFERENCES incident_actions(action_id),
  -- [T-1.62] Envíos ya intentados. Un fallo del proveedor era una lápida
  -- (failed para siempre, sin reintento y con el 409 bloqueando la re-solicitud):
  -- un AccessDenied de SES dejó un dictamen real sin correo. Reintento con
  -- backoff SOLO para quien no tiene a quién escalar (0016).
  attempts    integer NOT NULL DEFAULT 0
);
-- [T-1.61] Unicidad dividida (0014): la clave original solo para jobs de
-- incidente; 1 job por acción y canal para los de acción (re-runs no duplican).
CREATE UNIQUE INDEX uq_notification_jobs_incident
  ON notification_jobs (incident_id, channel, mode) WHERE action_id IS NULL;
CREATE UNIQUE INDEX uq_notification_jobs_action
  ON notification_jobs (action_id, channel) WHERE action_id IS NOT NULL;
CREATE INDEX idx_notification_jobs_due    ON notification_jobs (due_at) WHERE status = 'pending';
CREATE INDEX idx_notification_jobs_tenant ON notification_jobs (tenant_id, created_at DESC);
GRANT SELECT ON notification_jobs TO takab_app;
GRANT SELECT, INSERT, UPDATE ON notification_jobs TO takab_ingest;

ALTER TABLE notification_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_jobs FORCE  ROW LEVEL SECURITY;
CREATE POLICY notification_jobs_read ON notification_jobs FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR app_gov_can_see(tenant_id));
CREATE POLICY notification_jobs_admin ON notification_jobs FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

-- [T-1.60] Simulacro institucional (0015): registro propio — un drill JAMÁS
-- toca incidents. El acuse por sitio se DERIVA por JOIN a commands; el estado
-- 'active' es derivado (stopped_at IS NULL AND now() < started_at + duration_s).
-- Gov LEE (evidencia para Protección Civil) pero no escribe.
CREATE TABLE drills (
  drill_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  initiated_by uuid NOT NULL,
  note         text,
  duration_s   integer NOT NULL CHECK (duration_s BETWEEN 30 AND 3600),
  started_at   timestamptz NOT NULL DEFAULT now(),
  stopped_at   timestamptz,
  stop_reason  text
);
CREATE INDEX idx_drills_tenant ON drills (tenant_id, started_at DESC);

CREATE TABLE drill_sites (
  drill_id   uuid NOT NULL REFERENCES drills(drill_id),
  site_id    uuid NOT NULL REFERENCES sites(site_id),
  tenant_id  uuid NOT NULL REFERENCES tenants(tenant_id),
  command_id uuid REFERENCES commands(command_id),  -- NULL = sitio sin gateway comandable
  PRIMARY KEY (drill_id, site_id)
);

GRANT SELECT, INSERT, UPDATE ON drills TO takab_app;
GRANT SELECT, INSERT ON drill_sites TO takab_app;
GRANT SELECT ON drills, drill_sites TO takab_ingest;

ALTER TABLE drills ENABLE ROW LEVEL SECURITY;
ALTER TABLE drills FORCE  ROW LEVEL SECURITY;
CREATE POLICY drills_read ON drills FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR app_gov_can_see(tenant_id));
CREATE POLICY drills_write ON drills FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY drills_admin ON drills FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

ALTER TABLE drill_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE drill_sites FORCE  ROW LEVEL SECURITY;
CREATE POLICY drill_sites_read ON drill_sites FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR app_gov_can_see(tenant_id));
CREATE POLICY drill_sites_write ON drill_sites FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY drill_sites_admin ON drill_sites FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

-- Metering diario para billing (T-1.24): agregado por tenant/día; gb_approx
-- es row-count×avg (APROXIMACIÓN documentada; calibrar con pg_column_size).
CREATE TABLE billing_meters_daily (
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  day          date NOT NULL,
  active_sites integer NOT NULL DEFAULT 0,
  messages     bigint  NOT NULL DEFAULT 0,
  gb_approx    numeric NOT NULL DEFAULT 0,
  incidents    integer NOT NULL DEFAULT 0,
  computed_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, day)
);
GRANT SELECT ON billing_meters_daily TO takab_app;
GRANT SELECT, INSERT, UPDATE ON billing_meters_daily TO takab_ingest;

ALTER TABLE billing_meters_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_meters_daily FORCE  ROW LEVEL SECURITY;
CREATE POLICY billing_meters_read ON billing_meters_daily FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY billing_meters_admin ON billing_meters_daily FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

-- Índices de idempotencia de la Fase C sobre tablas pre-existentes: el ACK de
-- actuador y la evidencia re-entregados por SQS no deben duplicar filas.
CREATE UNIQUE INDEX uq_incident_actions_ack
  ON incident_actions (incident_id, kind, actor, ts);
CREATE UNIQUE INDEX uq_evidence_incident_sha256
  ON evidence_objects (incident_id, sha256) WHERE sha256 IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Fase 1.7 (migración 0011 · T-1.48): perfil de operador, catálogo de
-- referencia y reubicación de epicentro.
-- ---------------------------------------------------------------------------

-- Sub del portador del token (GUC por transacción, lo fija la sesión API).
CREATE FUNCTION app_user_id() RETURNS uuid
  LANGUAGE sql STABLE AS
  $$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$;

-- Nombre de operador editable. La identidad sigue siendo Cognito (/me no toca
-- DB); esto es SOLO presentación. Lectura tenant-wide (resolver actores en
-- timelines); escritura EXCLUSIVA de la fila propia. Excepción documentada al
-- patrón anti-gov: gov_operator también edita SU nombre (dato personal, no
-- escribe nada ajeno).
CREATE TABLE user_profiles (
  user_sub     uuid PRIMARY KEY,                     -- Cognito sub (≡ dictamens.signed_by)
  tenant_id    uuid NOT NULL REFERENCES tenants,
  display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 80),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_user_profiles_tenant ON user_profiles (tenant_id);
GRANT SELECT, INSERT, UPDATE ON user_profiles TO takab_app;

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles FORCE  ROW LEVEL SECURITY;
CREATE POLICY user_profiles_read ON user_profiles FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY user_profiles_self_write ON user_profiles FOR ALL
  USING      (tenant_id = app_tenant_id() AND user_sub = app_user_id())
  WITH CHECK (tenant_id = app_tenant_id() AND user_sub = app_user_id());
CREATE POLICY user_profiles_admin ON user_profiles FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

-- Catálogo GLOBAL de sismos relevantes reales (SSN/USGS; transcritos del
-- catálogo ratificado T-1.46 vía db/seeds/reference_earthquakes.sql).
-- [EXCEPCIÓN DOCUMENTADA] a "tenant_id en toda tabla": dato científico público,
-- misma familia que seismic_events/quorum_votes. Lectura: cualquier rol
-- autenticado. Escritura: NADIE vía API (sin política) — solo seeds/migrator.
-- La magnitud aquí es dato de catálogo histórico oficial, NO "magnitud
-- preliminar" en vivo (blueprint §14 sigue intacto).
CREATE TABLE reference_earthquakes (
  ref_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  catalog_key text NOT NULL UNIQUE,                  -- 'SSN-2017-09-19-PUE' (idempotencia seed)
  origin_time timestamptz NOT NULL,
  magnitude   numeric NOT NULL,
  place       text NOT NULL,
  epicenter   geography(Point,4326) NOT NULL,
  depth_km    numeric,
  source      text NOT NULL CHECK (source IN ('SSN','USGS')),
  source_ref  text NOT NULL,                         -- cita textual (reporte/consulta FDSN)
  notes       text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_ref_eq_origin ON reference_earthquakes (origin_time DESC);
GRANT SELECT ON reference_earthquakes TO takab_app;

ALTER TABLE reference_earthquakes ENABLE ROW LEVEL SECURITY;
ALTER TABLE reference_earthquakes FORCE  ROW LEVEL SECURITY;
CREATE POLICY ref_eq_read ON reference_earthquakes FOR SELECT
  USING (app_role() IS NOT NULL);

-- Reubicación de epicentro: función SECURITY DEFINER
-- `relocate_incident_epicenter(incident_id, lon, lat)` (dueña takab_ingest,
-- migración 0011 — mismo precedente que gov_ack_incident: seismic_events es
-- dato de RED sin tenant_id y una política RLS tenant-scoped de UPDATE abriría
-- el evento compartido a cualquier tenant linkeado). Guardas de rol
-- (soc_operator/tenant_admin/superadmin), tenant del incidente y rango; punto
-- previo preservado en meta.manual_override; sin evento crea EVT-MAN-<md5[:8]>
-- determinista source='manual' con magnitude NULL. El audit lo escribe el
-- ROUTER vía audit.py (single-writer).
GRANT SELECT, INSERT, UPDATE ON seismic_events TO takab_ingest;
GRANT SELECT, UPDATE ON incidents TO takab_ingest;
