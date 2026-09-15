-- ============================================================================
-- TAKAB · Seed de la RED DE DEMOSTRACIÓN (T-7.11) — IDEMPOTENTE
--
-- Tres estaciones simuladas de tres tipos distintos, para que `/fleet` enseñe
-- una red y no un gabinete solo: gobierno, hospital e industria. Con la de
-- Puebla —que es REAL— son cuatro.
--
-- ⚠️ ESTE SEED NO VA EN `deploy.sh`. Se aplica y se retira a mano
-- (`make cloud-demo-red` / `make cloud-demo-red-down`), porque una red de
-- adorno que se re-siembra en cada despliegue acaba pareciendo inventario de
-- verdad — y el censo de la purga de `T-7.10` la conservaría sin saber qué es.
--
-- ⚠️ NO es `sim_fleet.sql`. Aquél es la flota de veinte sitios del desarrollo
-- local y JAMÁS toca la nube. Éste sí va a la nube, con tres sitios, y por eso
-- lleva su propio bloque de UUIDs (…0101..0103) que no colisiona con aquéllos.
--
-- **Los nombres son ficticios a propósito.** Ninguno nombra una institución que
-- exista: enseñarle a un cliente un «Hospital General de …» real sería atribuir
-- a un tercero un despliegue que no tiene. Los tres dicen DEMOSTRACIÓN en el
-- nombre, que es además lo que `D-31` pide pintar como cinta.
--
-- Requiere `prod_fleet.sql` aplicado antes (crea el tenant).
-- ============================================================================

BEGIN;

-- --- Los tres sitios de la red -------------------------------------------------
INSERT INTO sites (site_id, tenant_id, code, name, criticality, geom) VALUES
  ('d1000000-0000-0000-0000-000000000101', 'd0000000-0000-0000-0000-000000000001',
   'site-sim-101', 'Centro Cívico Demostración · Tlaxcala', 'high',
   ST_SetSRID(ST_MakePoint(-98.2404, 19.3139), 4326)::geography),
  ('d1000000-0000-0000-0000-000000000102', 'd0000000-0000-0000-0000-000000000001',
   'site-sim-102', 'Hospital Demostración · Ciudad de México', 'critical',
   ST_SetSRID(ST_MakePoint(-99.1332, 19.4326), 4326)::geography),
  ('d1000000-0000-0000-0000-000000000103', 'd0000000-0000-0000-0000-000000000001',
   'site-sim-103', 'Planta Demostración · Toluca', 'medium',
   ST_SetSRID(ST_MakePoint(-99.6557, 19.2826), 4326)::geography)
ON CONFLICT (site_id) DO UPDATE
  SET name = EXCLUDED.name, criticality = EXCLUDED.criticality, geom = EXCLUDED.geom;

-- --- Un gabinete por sitio -----------------------------------------------------
INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) VALUES
  ('d2000000-0000-0000-0000-000000000101', 'd0000000-0000-0000-0000-000000000001',
   'd1000000-0000-0000-0000-000000000101', 'gw-sim-0101', 'gw-sim-0101'),
  ('d2000000-0000-0000-0000-000000000102', 'd0000000-0000-0000-0000-000000000001',
   'd1000000-0000-0000-0000-000000000102', 'gw-sim-0102', 'gw-sim-0102'),
  ('d2000000-0000-0000-0000-000000000103', 'd0000000-0000-0000-0000-000000000001',
   'd1000000-0000-0000-0000-000000000103', 'gw-sim-0103', 'gw-sim-0103')
ON CONFLICT (gateway_id) DO UPDATE SET site_id = EXCLUDED.site_id;

-- --- Un sensor por gabinete, SIN calibración -----------------------------------
-- `calibration_source` se queda NULL: estas estaciones no se han calibrado nunca
-- porque no existen. El dictamen y el forense lo declaran («los valores son
-- RELATIVOS del sensor») en vez de presentar cuentas como aceleración física.
INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, model, serial) VALUES
  ('d3000000-0000-0000-0000-000000000101', 'd0000000-0000-0000-0000-000000000001',
   'd1000000-0000-0000-0000-000000000101', 'd2000000-0000-0000-0000-000000000101',
   'structural', 'RS4D', 'SIM101'),
  ('d3000000-0000-0000-0000-000000000102', 'd0000000-0000-0000-0000-000000000001',
   'd1000000-0000-0000-0000-000000000102', 'd2000000-0000-0000-0000-000000000102',
   'structural', 'RS4D', 'SIM102'),
  ('d3000000-0000-0000-0000-000000000103', 'd0000000-0000-0000-0000-000000000001',
   'd1000000-0000-0000-0000-000000000103', 'd2000000-0000-0000-0000-000000000103',
   'structural', 'RS4D', 'SIM103')
ON CONFLICT (sensor_id) DO UPDATE SET gateway_id = EXCLUDED.gateway_id;

-- --- Y que lo REAL se pueda enseñar --------------------------------------------
-- `tenant-dev` y `site-dev` se llamaban como lo que son: nombres de desarrollo.
-- En una pantalla delante de un cliente, «Sitio Dev Puebla» resta más de lo que
-- cuesta cambiarlo. El CÓDIGO no se toca — es la identidad que usan el gabinete,
-- los seeds y los tests; solo el nombre, que es lo que se pinta.
UPDATE tenants SET name = 'TAKAB Ailert · Demostración'
  WHERE tenant_id = 'd0000000-0000-0000-0000-000000000001';
UPDATE sites SET name = 'Edificio Central · Puebla'
  WHERE site_id = 'd1000000-0000-0000-0000-000000000000';

COMMIT;
