-- ============================================================================
-- TAKAB · Seed de flota REAL (T-1.47) — IDEMPOTENTE
--
-- Aplicar con psql como superusuario o rol BYPASSRLS (RLS FORCE en las tablas):
--   psql "$DSN" -f db/seeds/prod_fleet.sql
-- Re-aplicable N veces: todo INSERT lleva ON CONFLICT DO NOTHING (una fila ya
-- existente NUNCA se sobreescribe: la calibración/estado vivos del entorno mandan).
--
-- SOLO la flota real. La flota sim vive en db/seeds/sim_fleet.sql y es EXCLUSIVA
-- de entornos locales (demo/tests): el deploy a la nube aplica únicamente este
-- archivo — T-1.47 purgó los datos sim del entorno desplegado y este split evita
-- que un deploy los resucite.
--
-- Convención (UUIDs FIJOS, los payloads del edge la referencian):
--   tenant  : 'tenant-dev'  d0000000-0000-0000-0000-000000000001
--   sitio   : 'site-dev'    d1000000-0000-0000-0000-000000000000  (Puebla, real)
--   gateway : 'gw-dev-0001' d2000000-0000-0000-0000-000000000000  (iot_thing=serial)
--   sensor  : 'R4F74'       d3000000-0000-0000-0000-000000000000  (RS4D → AM.R4F74)
-- ============================================================================

BEGIN;

-- --- Tenant ------------------------------------------------------------------
INSERT INTO tenants (tenant_id, code, name, vertical) VALUES
  ('d0000000-0000-0000-0000-000000000001', 'tenant-dev', 'TAKAB Dev', 'dev')
ON CONFLICT DO NOTHING;

-- --- Sitio real (geom = geography(Point,4326)) --------------------------------
INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES
  ('d1000000-0000-0000-0000-000000000000', 'd0000000-0000-0000-0000-000000000001',
   'site-dev', 'Sitio Dev Puebla',
   ST_SetSRID(ST_MakePoint(-98.2063, 19.0414), 4326)::geography)
ON CONFLICT DO NOTHING;

-- --- Gateway real (el Pi 5 "cerebro" del gabinete) -----------------------------
INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing, status) VALUES
  ('d2000000-0000-0000-0000-000000000000', 'd0000000-0000-0000-0000-000000000001',
   'd1000000-0000-0000-0000-000000000000', 'gw-dev-0001', 'gw-dev-0001', 'provisioned')
ON CONFLICT DO NOTHING;

-- --- Sensor real (channels/sample_rate = defaults del DDL: {EHZ,ENZ,ENN,ENE} @ 100 sps)
-- calibration_source: respuesta instrumental REAL del StationXML FDSN (T-1.41).
-- Solo aplica en entornos frescos: si la fila ya existe, su calibración viva manda.
INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, model, serial,
                     calibration_source) VALUES
  ('d3000000-0000-0000-0000-000000000000', 'd0000000-0000-0000-0000-000000000001',
   'd1000000-0000-0000-0000-000000000000', 'd2000000-0000-0000-0000-000000000000',
   'structural', 'RS4D', 'R4F74', 'stationxml:AM.R4F74')
ON CONFLICT DO NOTHING;

-- --- Rule_set inicial (v1, scope tenant) ---------------------------------------
-- Espeja los DEFAULTS EXACTOS de la nube (api settings.py: quorum_* y dictamen_*):
-- el comportamiento del quórum/dictamen NO cambia; solo se vuelve visible y
-- editable en la Matriz Multi-Tenant (que sin rule_set activo salía vacía).
--
-- DELIBERADAMENTE SIN clave 'edge': el worker de sync firmada solo publica
-- rule_sets cuyo config contiene 'edge' (commands/sync.py `config ? 'edge'`).
-- Este seed NO empuja nada al gabinete real. El día que se quiera gobernar los
-- umbrales del edge desde la nube, el camino es editar en Multi-Tenant y publicar
-- (PUT /rule-sets añade config.edge.thresholds ⇒ sync firmada con HMAC por thing).
INSERT INTO rule_sets (rule_set_id, tenant_id, scope_type, scope_id, version,
                       is_active, config) VALUES
  ('d4000000-0000-0000-0000-000000000001',
   'd0000000-0000-0000-0000-000000000001', 'tenant',
   'd0000000-0000-0000-0000-000000000001', 1, true,
   '{"quorum":   {"min_nodes": 3, "assoc": "distance", "v_p_km_s": 6.5,
                  "margin_s": 3, "max_window_s": 30},
     "dictamen": {"pga_no_inhabit_g": 0.25, "pga_monitor_g": 0.05},
     "notifications": {"inspector_emails": ["mauriciobaujim@gmail.com"]}}'::jsonb)
ON CONFLICT DO NOTHING;

COMMIT;
