-- ============================================================================
-- TAKAB · Retira la RED DE DEMOSTRACIÓN (T-7.11) — IDEMPOTENTE
--
-- La contraparte de `demo_red.sql`. Existe porque una red de adorno que no se
-- sabe quitar deja de ser adorno: al mes siguiente nadie recuerda si esos tres
-- sitios son de mentira, y el censo de la purga los conserva como inventario.
--
-- Alcance por CONVENCIÓN, nunca por fecha: solo los tres códigos que el seed
-- crea. La estación real de Puebla no puede caer aquí, y hay una guardia que lo
-- comprueba antes de tocar nada.
--
-- Retira también la telemetría que las tres hayan publicado: sin ella quedarían
-- features y latidos apuntando a sensores que ya no existen.
-- ============================================================================

\set ON_ERROR_STOP on

BEGIN;
SET LOCAL session_replication_role = replica;

CREATE TEMP TABLE _demo_sitios ON COMMIT DROP AS
  SELECT site_id FROM sites WHERE code IN ('site-sim-101', 'site-sim-102', 'site-sim-103');
CREATE TEMP TABLE _demo_gws ON COMMIT DROP AS
  SELECT gateway_id FROM gateways WHERE serial IN ('gw-sim-0101', 'gw-sim-0102', 'gw-sim-0103');
CREATE TEMP TABLE _demo_sensores ON COMMIT DROP AS
  SELECT sensor_id FROM sensors WHERE serial IN ('SIM101', 'SIM102', 'SIM103');

-- Guardia: la estación REAL jamás puede caer en el alcance.
DO $guardia$
BEGIN
  IF EXISTS (SELECT 1 FROM _demo_sitios   WHERE site_id    = 'd1000000-0000-0000-0000-000000000000')
  OR EXISTS (SELECT 1 FROM _demo_gws      WHERE gateway_id = 'd2000000-0000-0000-0000-000000000000')
  OR EXISTS (SELECT 1 FROM _demo_sensores WHERE sensor_id  = 'd3000000-0000-0000-0000-000000000000')
  THEN
    RAISE EXCEPTION 'guardia: la estación REAL cayó en el alcance de la retirada — aborto';
  END IF;
END
$guardia$;

DELETE FROM waveform_features_1s w USING _demo_sensores s WHERE w.sensor_id = s.sensor_id;
DELETE FROM device_health        d USING _demo_gws      g WHERE d.gateway_id = g.gateway_id;
DELETE FROM rule_evaluations     r USING _demo_gws      g WHERE r.gateway_id = g.gateway_id;
DELETE FROM gateway_config_state c USING _demo_gws      g WHERE c.gateway_id = g.gateway_id;
DELETE FROM sensors  se USING _demo_sensores s WHERE se.sensor_id  = s.sensor_id;
DELETE FROM gateways gw USING _demo_gws      g WHERE gw.gateway_id = g.gateway_id;
DELETE FROM zones    z  USING _demo_sitios   s WHERE z.site_id     = s.site_id;
DELETE FROM sites    st USING _demo_sitios   s WHERE st.site_id    = s.site_id;

-- Verificación: los tres códigos fuera, y la estación real en pie.
SELECT 'demo_sitios_restantes' AS chequeo, count(*) AS n FROM sites
  WHERE code IN ('site-sim-101', 'site-sim-102', 'site-sim-103')
UNION ALL
SELECT 'estacion_real', count(*) FROM sites
  WHERE site_id = 'd1000000-0000-0000-0000-000000000000'
ORDER BY 1;

COMMIT;
