-- ============================================================================
-- TAKAB · Catálogo de referencia de sismos relevantes (T-1.48) — IDEMPOTENTE
--
-- TRANSCRIPCIÓN FIEL del catálogo RATIFICADO en T-1.46
-- (api/tests/incident/fixtures/ssn_catalog.json): 13 sismos REALES con
-- procedencia por evento — 5 con parámetros oficiales del SSN (Reportes
-- Especiales) y 8 con solución del catálogo FDSN de USGS (el SSN no publica
-- reportes pre-2010). Los "gemelos" del 19S y Tehuantepec (solución SSN y
-- USGS) entran como filas separadas, igual que en el catálogo fuente.
--
-- La magnitud aquí es dato de catálogo histórico OFICIAL, no "magnitud
-- preliminar" en vivo (blueprint §14 intacto). Tabla GLOBAL de solo lectura:
-- la escritura vía API no existe (RLS sin política de escritura).
--
-- Aplicar con psql como superusuario (requiere migración 0011):
--   psql "$DSN" -f db/seeds/reference_earthquakes.sql
-- ============================================================================

BEGIN;

INSERT INTO reference_earthquakes
  (catalog_key, origin_time, magnitude, place, epicenter, depth_km, source, source_ref)
VALUES
  ('SSN-2017-09-19-PUE', '2017-09-19T18:14:40Z', 7.1,
   'Puebla-Morelos 19S (intraslab)',
   ST_SetSRID(ST_MakePoint(-98.72, 18.4), 4326)::geography, 57,
   'SSN', 'SSN Reporte Especial SSNMX_rep_esp_20170919_Puebla-Morelos_M71.pdf (18.40 N, -98.72 W, prof. 57 km, 13:14:40 CDMX)'),
  ('USGS-2017-09-19-PUE', '2017-09-19T18:14:38Z', 7.1,
   'Puebla-Morelos 19S (solucion USGS, gemelo)',
   ST_SetSRID(ST_MakePoint(-98.4887, 18.5499), 4326)::geography, 48,
   'USGS', 'USGS us2000ar20 (18.5499 N, -98.4887 W, prof. 48 km) — difiere ~28 km del epicentro SSN: prueba de robustez a la incertidumbre entre catalogos'),
  ('SSN-2017-09-08-TEHU', '2017-09-08T04:49:17Z', 8.2,
   'Tehuantepec (intraplaca, campo lejano)',
   ST_SetSRID(ST_MakePoint(-94.103, 14.761), 4326)::geography, 45.9,
   'SSN', 'SSN Reporte Especial SSNMX_rep_esp_20170907_Tehuantepec_M82.pdf (14.761 N, -94.103 W, prof. 45.9 km, 04:49:17 UTC)'),
  ('USGS-2017-09-08-TEHU', '2017-09-08T04:49:19Z', 8.2,
   'Tehuantepec (solucion USGS, gemelo)',
   ST_SetSRID(ST_MakePoint(-93.8993, 15.0222), 4326)::geography, 47.4,
   'USGS', 'USGS us2000ahv0 (15.0222 N, -93.8993 W, prof. 47.4 km) — difiere ~36 km del epicentro SSN'),
  ('SSN-2020-06-23-OAX', '2020-06-23T15:29:04Z', 7.4,
   'Costa de Oaxaca (La Crucecita)',
   ST_SetSRID(ST_MakePoint(-96.12, 15.784), 4326)::geography, 22.6,
   'SSN', 'SSN Reporte Especial SSNMX_rep_esp_20200623_Oaxaca-Costa_M75.pdf (magnitud ACTUALIZADA a 7.4; 15.784 N, -96.120 W, prof. 22.6 km)'),
  ('SSN-2021-09-07-GRO', '2021-09-08T01:47:47Z', 7.1,
   'Acapulco (interplaca somero)',
   ST_SetSRID(ST_MakePoint(-99.78, 16.82), 4326)::geography, 10,
   'SSN', 'SSN Reporte Especial SSNMX_rep_esp_20210907_Guerrero_M71.pdf (16.82 N, -99.78 W, prof. 10 km, 20:47 CDMX)'),
  ('SSN-2022-09-19-MICH', '2022-09-19T18:05:09Z', 7.7,
   'Michoacan 2022 (Coalcoman)',
   ST_SetSRID(ST_MakePoint(-103.29, 18.24), 4326)::geography, 15,
   'SSN', 'SSN Reporte Especial SSNMX_rep_esp_20220919_Michoacan_M74.pdf (M 7.7; 18.24 N, -103.29 W, prof. 15 km, 13:05:09 CDMX)'),
  ('USGS-1999-06-15-TEHUACAN', '1999-06-15T20:42:05Z', 7.0,
   'Tehuacan 1999 (intraslab profundo bajo Puebla)',
   ST_SetSRID(ST_MakePoint(-97.436, 18.386), 4326)::geography, 70,
   'USGS', 'USGS (18.386 N, -97.436 W, prof. 70 km, M 7.0, 20:42:05 UTC) — el SSN no publica reporte especial pre-2010'),
  ('USGS-2000-07-21-JOLALPAN', '2000-07-21T06:13:41Z', 5.9,
   'Jolalpan 2000 (intraslab, el MAS profundo del set)',
   ST_SetSRID(ST_MakePoint(-98.916, 18.414), 4326)::geography, 80.1,
   'USGS', 'USGS (18.414 N, -98.916 W, prof. 80.1 km, M 5.9, 06:13:41 UTC)'),
  ('USGS-2011-12-11-GRO', '2011-12-11T01:47:25Z', 6.5,
   'Nuevo Balsas 2011 (intraslab Guerrero)',
   ST_SetSRID(ST_MakePoint(-99.789, 17.986), 4326)::geography, 59,
   'USGS', 'USGS (17.986 N, -99.789 W, prof. 59 km, M 6.5, 01:47:25 UTC)'),
  ('USGS-2013-06-16-GRO', '2013-06-16T05:19:00Z', 5.8,
   'Tequicuilco 2013 (intraslab moderado)',
   ST_SetSRID(ST_MakePoint(-99.203, 18.155), 4326)::geography, 52,
   'USGS', 'USGS (18.155 N, -99.203 W, prof. 52 km, M 5.8, 05:19:00 UTC)'),
  ('USGS-2018-07-19-OAX', '2018-07-19T13:31:53Z', 5.8,
   'Camotlan 2018 (intraslab moderado, borde Puebla-Oaxaca)',
   ST_SetSRID(ST_MakePoint(-97.7158, 17.9318), 4326)::geography, 48.5,
   'USGS', 'USGS (17.9318 N, -97.7158 W, prof. 48.5 km, M 5.8, 13:31:53 UTC)'),
  ('USGS-1985-09-19-MICH', '1985-09-19T13:17:47Z', 8.0,
   'Michoacan 1985 (historico, campo lejano)',
   ST_SetSRID(ST_MakePoint(-102.533, 18.19), 4326)::geography, 27.9,
   'USGS', 'USGS (18.19 N, -102.533 W, prof. 27.9 km, M 8.0, 13:17:47 UTC)')
ON CONFLICT (catalog_key) DO NOTHING;

COMMIT;
