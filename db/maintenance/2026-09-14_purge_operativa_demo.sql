-- ============================================================================
-- TAKAB · Purga operativa pre-demostración (T-7.10) — decisión en README.md
--
-- QUÉ HACE: retira del entorno desplegado lo RECOPILADO de julio a septiembre de
-- 2026 —los incidentes de las pruebas del WR-1, del sensor golpeado a mano y de
-- los arneses, con su familia entera, más la telemetría que los acompaña— para
-- que la demostración arranque con historial limpio y lo que se enseñe sea de
-- ese día.
--
-- QUÉ CONSERVA, y por qué cada cosa:
--   * `audit_log` y `actuation_records` ÍNTEGROS — regla de oro 11. La bitácora
--     de quién ordenó qué y la del gabinete no se podan; el respaldo preserva lo
--     demás de forma recuperable. La purga misma queda dentro, `verb='purge'`.
--   * Los `privacy_*` — avisos, consentimientos y ARCO. Es cumplimiento, no
--     historial operativo.
--   * La FLOTA entera (tenants, sitios, gateways, sensores, zonas) y la
--     configuración (`rule_sets`, equipamiento, cámaras, plantillas). Aquí está
--     la diferencia con la purga del 2026-07-10, que sí se llevó la flota sim.
--   * Usuarios, sus llaves y sus alcances.
--   * `gateway_catalog_state` y `reference_earthquakes`: el catálogo con la
--     procedencia que `T-7.12` acaba de consultar a la fuente.
--     [T-7.25] Lo que SÍ se purga es `catalog_consultations`: la consulta es
--     historial de un incidente que se va, no catálogo.
--
-- CÓMO: transacción única COMO SUPERUSUARIO con `session_replication_role =
-- replica`, que es lo único que apaga los triggers append-only COPIADOS a cada
-- chunk de las hypertables (un `ALTER TABLE ... DISABLE TRIGGER` sobre la tabla
-- padre no los cubriría) y evita la tormenta de NOTIFY al hub WS. También
-- desactiva la validación de FKs ⇒ los checks de orfandad del final son
-- OBLIGATORIOS. `SET LOCAL` se revierte solo: es imposible dejarlos apagados.
--
-- PRECONDICIONES (README.md, EN ORDEN):
--   1. `pg_dump -Fc` hecho, con su sha256, y copiado FUERA del EC2.
--   2. CSV de `s3_key` de `evidence_objects` exportado — los objetos de S3 NO se
--      tocan aquí; retirarlos es un paso posterior y aparte.
--   3. Conteos ANTES anotados (el bloque 1 los imprime).
--
-- IDEMPOTENTE: re-ejecutarlo afecta a 0 filas. La fila de `audit_log` SÍ se
-- insertaría otra vez; el runbook indica ejecutarlo UNA vez.
--
-- Editar antes de ejecutar: <SUB_DE_MAURICIO> y <NOMBRE_DEL_DUMP>.
-- ============================================================================

\set ON_ERROR_STOP on

BEGIN;
SET LOCAL session_replication_role = replica;

-- --- 0) CENSO: ninguna tabla del esquema puede quedar sin clasificar ----------
-- Si mañana nace una tabla y nadie decide si su contenido es historial operativo
-- o inventario, esta purga tomaría la decisión por omisión —conservarla— y nadie
-- se enteraría. Aquí se entera: revienta y dice el nombre.
CREATE TEMP TABLE _purgar (t text PRIMARY KEY) ON COMMIT DROP;
INSERT INTO _purgar (t) VALUES
  -- incidentes y su familia
  ('incidents'), ('incident_actions'), ('incident_classifications'), ('dictamens'),
  ('evidence_objects'), ('notification_jobs'), ('commands'),
  -- lo que los origina
  ('seismic_events'), ('quorum_votes'), ('manual_activation_votes'),
  -- telemetría
  ('waveform_features_1s'), ('device_health'), ('rule_evaluations'),
  -- simulacros ejecutados (las PLANTILLAS se conservan)
  ('drills'), ('drill_sites'),
  -- lo que la gente reportó durante las pruebas
  ('life_checkins'), ('damage_reports'),
  -- vídeo de las pruebas (los objetos de S3 se retiran aparte, con su CSV)
  ('cctv_clips'), ('cctv_stills'), ('cctv_occupancy'), ('cctv_evacuation_metrics'),
  -- ruido de operación de las pruebas
  ('ops_alert_notices'), ('notify_template_quarantine'),
  -- [T-7.25] La consulta a la fuente externa cuelga de un incidente que SÍ se
  -- purga. Su `ON DELETE CASCADE` no la salvaría: esta transacción corre con
  -- `session_replication_role = replica`, que apaga también los triggers de FK,
  -- así que sin esta línea quedarían filas apuntando a incidentes borrados. El
  -- catálogo que la consulta escribió (`reference_earthquakes`) SÍ se conserva:
  -- es dato científico citable, no historial de estas pruebas.
  ('catalog_consultations');

CREATE TEMP TABLE _conservar (t text PRIMARY KEY) ON COMMIT DROP;
INSERT INTO _conservar (t) VALUES
  -- regla de oro 11: bitácoras y cumplimiento
  ('audit_log'), ('actuation_records'), ('pii_retention_runs'),
  ('privacy_consents'), ('privacy_notices'), ('privacy_erasures'),
  ('privacy_erasure_requests'), ('privacy_subject_secrets'),
  -- flota e inventario
  ('tenants'), ('sites'), ('gateways'), ('sensors'), ('zones'), ('site_assets'),
  ('site_ground_refs'), ('cameras'), ('compliance_labels'), ('rule_sets'),
  ('gateway_config_state'), ('gateway_catalog_state'), ('maintenance_windows'),
  ('fw_releases'), ('fleet_rollouts'), ('fleet_rollout_sites'), ('demo_mode'),
  -- [T-7.14] `demo_replay` va con `demo_mode` y por lo mismo: es una VENTANA
  -- declarada, no dato de operación, y vence sola en 8 h. Esta línea la obligó
  -- el censo de abajo, que es justamente para lo que está.
  ('demo_replay'),
  -- personas y sus accesos
  ('user_profiles'), ('user_zone_assignments'), ('user_deactivations'),
  ('device_keys'), ('push_tokens'), ('site_enrollment_codes'),
  ('visibility_grants'), ('tenant_retire_codes'), ('ops_oncall_contacts'),
  -- plantillas de simulacro (lo EJECUTADO se purga, el molde no)
  ('drill_templates'), ('drill_template_sites'),
  -- el catálogo, con la procedencia que T-7.12 consultó a la fuente
  ('reference_earthquakes'),
  -- consumo acumulado: es facturación, no historial de incidentes
  ('billing_meters_daily'), ('ai_spend');

DO $censo$
DECLARE faltan text;
BEGIN
  SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO faltan
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public' AND c.relkind IN ('r','p')
    AND c.relname NOT LIKE '%\_chunk' AND c.relname <> 'alembic_version'
    AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e')
    AND c.relname NOT IN (SELECT t FROM _purgar)
    AND c.relname NOT IN (SELECT t FROM _conservar);
  IF faltan IS NOT NULL THEN
    RAISE EXCEPTION 'censo: tabla(s) sin clasificar: % — decide si su contenido es historial operativo o inventario y añádela a _purgar o a _conservar', faltan;
  END IF;
END
$censo$;

-- --- 1) Conteos ANTES (van al Registro) ---------------------------------------
SELECT 'ANTES · ' || t AS q, n FROM (
  SELECT 'incidents' t, count(*) n FROM incidents                     UNION ALL
  SELECT 'seismic_events',        count(*) FROM seismic_events        UNION ALL
  SELECT 'dictamens',             count(*) FROM dictamens             UNION ALL
  SELECT 'evidence_objects',      count(*) FROM evidence_objects      UNION ALL
  SELECT 'waveform_features_1s',  count(*) FROM waveform_features_1s  UNION ALL
  SELECT 'device_health',         count(*) FROM device_health         UNION ALL
  SELECT 'rule_evaluations',      count(*) FROM rule_evaluations      UNION ALL
  SELECT 'audit_log (SE CONSERVA)',         count(*) FROM audit_log   UNION ALL
  SELECT 'actuation_records (SE CONSERVA)', count(*) FROM actuation_records
) x ORDER BY 1;

-- --- 2) La purga, hijo→padre por legibilidad (las FKs están desactivadas) ------
DELETE FROM catalog_consultations;   -- [T-7.25] antes que `incidents`
DELETE FROM notification_jobs;
DELETE FROM notify_template_quarantine;
DELETE FROM ops_alert_notices;
DELETE FROM cctv_evacuation_metrics;
DELETE FROM cctv_occupancy;
DELETE FROM cctv_stills;
DELETE FROM cctv_clips;
DELETE FROM damage_reports;            -- append-only: lo permite replica-mode
DELETE FROM life_checkins;             -- ídem
DELETE FROM incident_classifications;
DELETE FROM incident_actions;          -- ídem
DELETE FROM dictamens;                 -- ídem
DELETE FROM evidence_objects;          -- ídem (s3_keys ya exportadas al CSV)
DELETE FROM commands;
DELETE FROM drill_sites;
DELETE FROM drills;
DELETE FROM incidents;
DELETE FROM quorum_votes;
DELETE FROM manual_activation_votes;
DELETE FROM seismic_events;
DELETE FROM waveform_features_1s;
DELETE FROM device_health;
DELETE FROM rule_evaluations;          -- ídem

-- --- 3) Evidencia de la purga (audit_log SE CONSERVA; INSERT sigue permitido) --
INSERT INTO audit_log (tenant_id, actor, verb, object, meta) VALUES (
  'd0000000-0000-0000-0000-000000000001',
  'user:<SUB_DE_MAURICIO>',
  'purge',
  'tenant:d0000000-0000-0000-0000-000000000001',
  jsonb_build_object(
    'decision', 'purga operativa pre-demostracion 2026-09-14 (T-7.10)',
    'scope',    'incidentes y familia, eventos, votos, telemetria, simulacros ejecutados, check-ins, danos y video',
    'kept',     'audit_log, actuation_records, privacy_*, flota y configuracion completas, usuarios, catalogo',
    'backup',   '<NOMBRE_DEL_DUMP>.dump'
  )
);

-- --- 4) VERIFICACIÓN (si algo difiere ⇒ ROLLBACK a mano, no COMMIT) ------------
SELECT 'DESPUES · ' || t AS q, n FROM (
  SELECT 'incidents' t, count(*) n FROM incidents                     UNION ALL
  SELECT 'seismic_events',        count(*) FROM seismic_events        UNION ALL
  SELECT 'dictamens',             count(*) FROM dictamens             UNION ALL
  SELECT 'evidence_objects',      count(*) FROM evidence_objects      UNION ALL
  SELECT 'waveform_features_1s',  count(*) FROM waveform_features_1s  UNION ALL
  SELECT 'device_health',         count(*) FROM device_health         UNION ALL
  SELECT 'rule_evaluations',      count(*) FROM rule_evaluations      UNION ALL
  SELECT 'sites (INTACTOS)',      count(*) FROM sites                 UNION ALL
  SELECT 'gateways (INTACTOS)',   count(*) FROM gateways              UNION ALL
  SELECT 'sensors (INTACTOS)',    count(*) FROM sensors               UNION ALL
  SELECT 'user_profiles (INTACTOS)',        count(*) FROM user_profiles UNION ALL
  SELECT 'reference_earthquakes (INTACTO)', count(*) FROM reference_earthquakes UNION ALL
  SELECT 'audit_log (CRECE en 1)',          count(*) FROM audit_log     UNION ALL
  SELECT 'actuation_records (INTACTO)',     count(*) FROM actuation_records
) x ORDER BY 1;

-- Orfandad (las FKs estuvieron desactivadas): TODAS deben dar 0.
SELECT 'huerfanos_' || t AS chequeo, n FROM (
  SELECT 'actions' t, count(*) n FROM incident_actions ia
    LEFT JOIN incidents i USING (incident_id) WHERE i.incident_id IS NULL     UNION ALL
  SELECT 'dictamens', count(*) FROM dictamens d
    LEFT JOIN incidents i USING (incident_id) WHERE i.incident_id IS NULL     UNION ALL
  SELECT 'evidencia', count(*) FROM evidence_objects e
    LEFT JOIN incidents i USING (incident_id) WHERE i.incident_id IS NULL     UNION ALL
  SELECT 'consultas', count(*) FROM catalog_consultations cc
    LEFT JOIN incidents i USING (incident_id) WHERE i.incident_id IS NULL     UNION ALL
  SELECT 'drill_sites', count(*) FROM drill_sites ds
    LEFT JOIN drills dr USING (drill_id) WHERE dr.drill_id IS NULL            UNION ALL
  SELECT 'zonas', count(*) FROM zones z
    LEFT JOIN sites st ON st.site_id = z.site_id WHERE st.site_id IS NULL     UNION ALL
  SELECT 'sensores', count(*) FROM sensors se
    LEFT JOIN gateways g ON g.gateway_id = se.gateway_id
    WHERE se.gateway_id IS NOT NULL AND g.gateway_id IS NULL
) x ORDER BY 1;

COMMIT;

-- ============================================================================
-- POST-COMMIT (no puede ir dentro de la transacción):
-- Los caggs materializaron lo que la cruda ya no tiene; el refresh full-range
-- los recalcula y quedan vacíos. VACUUM recupera el espacio.
-- ============================================================================
CALL refresh_continuous_aggregate('site_metrics_1m', NULL, NULL);
CALL refresh_continuous_aggregate('site_metrics_1h', NULL, NULL);
VACUUM (ANALYZE) waveform_features_1s, device_health, rule_evaluations, incidents;
