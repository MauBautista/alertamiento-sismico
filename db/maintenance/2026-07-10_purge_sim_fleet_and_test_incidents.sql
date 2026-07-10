-- ============================================================================
-- TAKAB · Purga pre-producción (T-1.47) — decisión registrada en README.md
--
-- QUÉ HACE: elimina del entorno desplegado (a) la flota SIM completa
-- (site-sim-001..020, gw-sim-0001..0004, SIM001..020) con su telemetría, y
-- (b) TODOS los incidentes existentes con su familia (acciones, dictámenes,
-- eventos, votos, evidencia, comandos, jobs) — son las pruebas del botón WR-1
-- del 2026-07-10 y una de sitio sim. Decisión de Mauricio: arranque limpio del
-- historial; "ya no estamos en fase de pruebas".
--
-- QUÉ CONSERVA: la estación real (site-dev / gw-dev-0001 / R4F74) y TODA su
-- telemetría (device_health, waveform_features_1s, rule_evaluations), y el
-- audit_log ÍNTEGRO (compliance, regla de oro 11) + una fila nueva verb='purge'
-- que documenta esta excepción deliberada.
--
-- CÓMO: transacción única COMO SUPERUSUARIO con session_replication_role=replica:
--   * apaga los triggers append-only `forbid_update_delete` (incident_actions,
--     dictamens, evidence_objects, life_checkins, rule_evaluations — incluidos
--     los COPIADOS a cada chunk de las hypertables, que un ALTER ... DISABLE
--     TRIGGER sobre la tabla padre NO cubriría),
--   * apaga los triggers NOTIFY (sin tormenta de frames al hub WS),
--   * y también desactiva la VALIDACIÓN de FKs ⇒ los checks de orfandad del
--     final son OBLIGATORIOS antes de dar por buena la purga.
--   SET LOCAL se revierte solo al terminar la transacción: es imposible dejar
--   los triggers apagados.
--
-- PRECONDICIONES (runbook README.md, EN ORDEN):
--   1. El split de seeds (prod_fleet.sql) ya DESPLEGADO — deploy.sh re-siembra
--      en cada deploy y con el seed viejo resucitaría los 20 sitios sim.
--   2. Workers de ingest/engine/notify DETENIDOS (la DB y el broker siguen
--      arriba; el Pi acumula en SQS/spool sin pérdida).
--   3. pg_dump -Fc verificado y copiado FUERA del EC2.
--   4. CSV de s3_key de evidence_objects exportado (los objetos S3 no se tocan
--      aquí; borrarlos es un paso posterior opcional del runbook).
--
-- IDEMPOTENTE: los alcances se resuelven por patrón; re-ejecutar con la flota
-- ya purgada borra 0 filas. (La fila de audit SÍ se insertaría de nuevo: el
-- runbook indica ejecutar el archivo UNA vez.)
--
-- Editar antes de ejecutar: <SUB_DE_MAURICIO> y <NOMBRE_DEL_DUMP> en el paso 5.
-- ============================================================================

\set ON_ERROR_STOP on

BEGIN;
SET LOCAL session_replication_role = replica;

-- --- 0) Alcances SIM (por convención de db/seeds; JAMÁS por rango de fechas) ---
CREATE TEMP TABLE _sim_sites   ON COMMIT DROP AS
  SELECT site_id    FROM sites    WHERE code   LIKE 'site-sim-%';
CREATE TEMP TABLE _sim_gws     ON COMMIT DROP AS
  SELECT gateway_id FROM gateways WHERE serial LIKE 'gw-sim-%';
CREATE TEMP TABLE _sim_sensors ON COMMIT DROP AS
  SELECT sensor_id  FROM sensors  WHERE serial LIKE 'SIM%';

-- Guardia: la estación real NUNCA puede caer en el alcance.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM _sim_sites   WHERE site_id    = 'd1000000-0000-0000-0000-000000000000')
  OR EXISTS (SELECT 1 FROM _sim_gws     WHERE gateway_id = 'd2000000-0000-0000-0000-000000000000')
  OR EXISTS (SELECT 1 FROM _sim_sensors WHERE sensor_id  = 'd3000000-0000-0000-0000-000000000000')
  THEN
    RAISE EXCEPTION 'guardia: la flota REAL cayó en el alcance de purga — aborto';
  END IF;
END $$;

-- --- 1) Familia de incidentes: TODOS (pruebas WR-1 + sim; decisión de arranque
--        limpio). Orden hijo→padre por legibilidad (las FKs están desactivadas,
--        los checks de orfandad del final validan el resultado). --------------
DELETE FROM notification_jobs;
DELETE FROM incident_actions;      -- append-only: lo permite replica-mode
DELETE FROM dictamens;             -- ídem
DELETE FROM life_checkins;         -- ídem (hoy vacía; por completitud)
DELETE FROM evidence_objects;      -- ídem (solo evidencia de pruebas; s3_keys ya exportadas)
DELETE FROM commands;              -- actuaciones de prueba (el dump las preserva)
DELETE FROM incidents;
DELETE FROM quorum_votes;
DELETE FROM seismic_events;

-- --- 2) Telemetría SIM (la del gateway/sensor real SE CONSERVA) ----------------
DELETE FROM waveform_features_1s w USING _sim_sensors s WHERE w.sensor_id  = s.sensor_id;
DELETE FROM device_health        d USING _sim_gws     g WHERE d.gateway_id = g.gateway_id;
DELETE FROM rule_evaluations     r USING _sim_gws     g WHERE r.gateway_id = g.gateway_id;

-- --- 3) Flota SIM ---------------------------------------------------------------
DELETE FROM gateway_config_state cs USING _sim_gws g WHERE cs.gateway_id = g.gateway_id;
DELETE FROM site_ground_refs
  WHERE site_id          IN (SELECT site_id   FROM _sim_sites)
     OR ground_sensor_id IN (SELECT sensor_id FROM _sim_sensors);
DELETE FROM sensors  se USING _sim_sensors s WHERE se.sensor_id  = s.sensor_id;
DELETE FROM gateways gw USING _sim_gws     g WHERE gw.gateway_id = g.gateway_id;
DELETE FROM manual_activation_votes WHERE site_id IN (SELECT site_id FROM _sim_sites);
DELETE FROM site_enrollment_codes   WHERE site_id IN (SELECT site_id FROM _sim_sites);
DELETE FROM user_zone_assignments   WHERE site_id IN (SELECT site_id FROM _sim_sites);
DELETE FROM zones                   WHERE site_id IN (SELECT site_id FROM _sim_sites);
DELETE FROM sites st USING _sim_sites s WHERE st.site_id = s.site_id;

-- --- 4) OPCIONAL: metering interno del tenant dev (descomentar si se decide) ----
-- DELETE FROM billing_meters_daily WHERE tenant_id = 'd0000000-0000-0000-0000-000000000001';

-- --- 5) Evidencia de la purga (audit_log SE CONSERVA; INSERT sigue permitido) ---
INSERT INTO audit_log (tenant_id, actor, verb, object, meta) VALUES (
  'd0000000-0000-0000-0000-000000000001',
  'user:<SUB_DE_MAURICIO>',
  'purge',
  'tenant:d0000000-0000-0000-0000-000000000001',
  jsonb_build_object(
    'decision', 'purga pre-produccion 2026-07-10 (T-1.47)',
    'scope',    'flota sim completa + todos los incidentes de prueba (WR-1 y sim)',
    'kept',     'estacion real gw-dev-0001 con su telemetria; audit_log integro',
    'backup',   '<NOMBRE_DEL_DUMP>.dump'
  )
);

-- --- 6) VERIFICACIÓN (dentro de la txn: si algo difiere ⇒ ROLLBACK manual) ------
-- Esperado: incidents/incident_actions/dictamens/seismic_events/quorum_votes/
-- notification_jobs/commands/evidence_objects = 0; sites/gateways/sensors = 1;
-- dh_real y wf_real > 0 (telemetría real conservada).
SELECT 'incidents'          AS tabla, count(*) FROM incidents          UNION ALL
SELECT 'incident_actions',          count(*) FROM incident_actions     UNION ALL
SELECT 'dictamens',                 count(*) FROM dictamens            UNION ALL
SELECT 'seismic_events',            count(*) FROM seismic_events       UNION ALL
SELECT 'quorum_votes',              count(*) FROM quorum_votes         UNION ALL
SELECT 'notification_jobs',         count(*) FROM notification_jobs    UNION ALL
SELECT 'commands',                  count(*) FROM commands             UNION ALL
SELECT 'evidence_objects',          count(*) FROM evidence_objects     UNION ALL
SELECT 'sites',                     count(*) FROM sites                UNION ALL
SELECT 'gateways',                  count(*) FROM gateways             UNION ALL
SELECT 'sensors',                   count(*) FROM sensors              UNION ALL
SELECT 'dh_real',  count(*) FROM device_health
  WHERE gateway_id = 'd2000000-0000-0000-0000-000000000000'            UNION ALL
SELECT 'wf_real',  count(*) FROM waveform_features_1s
  WHERE sensor_id  = 'd3000000-0000-0000-0000-000000000000'
ORDER BY 1;

-- Orfandad (las FKs estuvieron desactivadas): TODAS deben dar 0.
SELECT 'huerfanos_actions'   AS chequeo, count(*) FROM incident_actions ia
  LEFT JOIN incidents i USING (incident_id) WHERE i.incident_id IS NULL  UNION ALL
SELECT 'huerfanos_dictamens', count(*) FROM dictamens d
  LEFT JOIN incidents i USING (incident_id) WHERE i.incident_id IS NULL  UNION ALL
SELECT 'huerfanos_incid_evento', count(*) FROM incidents i
  LEFT JOIN seismic_events e ON e.event_id = i.event_id
  WHERE i.event_id IS NOT NULL AND e.event_id IS NULL                    UNION ALL
SELECT 'huerfanos_sensores', count(*) FROM sensors se
  LEFT JOIN gateways g ON g.gateway_id = se.gateway_id
  WHERE se.gateway_id IS NOT NULL AND g.gateway_id IS NULL              UNION ALL
SELECT 'huerfanos_features', count(*) FROM (
  SELECT DISTINCT w.sensor_id FROM waveform_features_1s w
  LEFT JOIN sensors s ON s.sensor_id = w.sensor_id WHERE s.sensor_id IS NULL) q UNION ALL
SELECT 'huerfanos_health', count(*) FROM (
  SELECT DISTINCT d.gateway_id FROM device_health d
  LEFT JOIN gateways g ON g.gateway_id = d.gateway_id WHERE g.gateway_id IS NULL) q UNION ALL
SELECT 'huerfanos_rule_evals', count(*) FROM (
  SELECT DISTINCT r.gateway_id FROM rule_evaluations r
  LEFT JOIN gateways g ON g.gateway_id = r.gateway_id WHERE g.gateway_id IS NULL) q UNION ALL
SELECT 'huerfanos_zonas', count(*) FROM zones z
  LEFT JOIN sites st ON st.site_id = z.site_id WHERE st.site_id IS NULL
ORDER BY 1;

COMMIT;

-- ============================================================================
-- POST-COMMIT (no puede ir dentro de la transacción):
-- Los caggs materializaron datos sim aunque la cruda se borró; el refresh
-- full-range los recalcula y desaparecen. VACUUM recupera el espacio.
-- ============================================================================
CALL refresh_continuous_aggregate('site_metrics_1m', NULL, NULL);
CALL refresh_continuous_aggregate('site_metrics_1h', NULL, NULL);
VACUUM (ANALYZE) waveform_features_1s, device_health, rule_evaluations, incidents;
