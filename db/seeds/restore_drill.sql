-- ============================================================================
-- TAKAB · Semilla del ENSAYO DE RESTORE (T-2.73) — SOLO bases de usar y tirar
--
-- ⚠️  ESTE ARCHIVO NO SE APLICA NUNCA A UNA BASE VIVA. Lo ejecuta
--     `takab_api.ops.restore_drill` sobre la base ORIGEN que él mismo acaba de
--     crear en esa corrida (nombre generado + marcador propio). Su guardia se
--     niega en redondo ante cualquier otra base.
--
-- Vive aquí, con los demás seeds, y no dentro del módulo, por dos contratos del
-- repositorio que son correctos y que este seed rompería si fuera código de la
-- API: `takab_api.audit` es el ÚNICO escritor de `audit_log`
-- (`tests/contracts/test_audit_single_writer.py`) y la superficie de LECTURA de
-- la API jamás nombra la hypertable cruda de features
-- (`tests/contracts/test_waveform_view.py`). Una semilla de datos no es la API:
-- es un dato, y los datos viven en db/seeds/.
--
-- POR QUÉ CADA PIEZA (nada aquí es decorativo):
--   · DOS tenants PRIVADOS con sitio propio → sin ellos la prueba de cruce entre
--     tenants no tiene vecino al que espiar y se declara SALTADA.
--   · UNA fila en CADA tabla append-only → el trigger es FOR EACH ROW: sobre una
--     tabla vacía la aserción negativa no se puede ejercer.
--   · Telemetría repartida en VARIOS chunks de la hypertable → el `COPY` de
--     chunk que falla en un restore mal hecho necesita más de un chunk para
--     poder fallar. El volumen lo fija `takab.drill_rows` (default 20000, unas
--     11 particiones de un día).
--
-- Uso directo (el ensayo hace esto mismo por dentro):
--   psql -d <base_de_ensayo> -c "SET takab.drill_rows = 20000" -f db/seeds/restore_drill.sql
-- ============================================================================

INSERT INTO tenants (tenant_id, code, name, visibility) VALUES
 ('11111111-1111-1111-1111-111111111111','DRILL-A','Ensayo A','private'),
 ('22222222-2222-2222-2222-222222222222','DRILL-B','Ensayo B','private');

INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES
 ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','11111111-1111-1111-1111-111111111111','SA','Sitio A',
  ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography),
 ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','22222222-2222-2222-2222-222222222222','SB','Sitio B',
  ST_SetSRID(ST_MakePoint(-99.20,19.50),4326)::geography);

INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) VALUES
 ('a1a1a1a1-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','DRILL-SER-A'),
 ('b1b1b1b1-0000-0000-0000-000000000002','22222222-2222-2222-2222-222222222222',
  'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','DRILL-SER-B');

INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) VALUES
 ('a2a2a2a2-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','ground','RS4D'),
 ('b2b2b2b2-0000-0000-0000-000000000002','22222222-2222-2222-2222-222222222222',
  'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb','ground','RS4D');

INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, opened_at, severity, trigger)
VALUES ('a3a3a3a3-0000-0000-0000-000000000001','a4a4a4a4-0000-0000-0000-000000000001',
        '11111111-1111-1111-1111-111111111111','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        now() - interval '2 hours','warning','sasmex');

-- ---- una fila por tabla append-only (compliance, regla de oro 11) ----------
INSERT INTO incident_actions (incident_id, tenant_id, kind, actor) VALUES
 ('a3a3a3a3-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',
  'siren_on','edge:DRILL-A');

INSERT INTO dictamens (tenant_id, incident_id, status, basis) VALUES
 ('11111111-1111-1111-1111-111111111111','a3a3a3a3-0000-0000-0000-000000000001',
  'normal_operation','{}');

INSERT INTO evidence_objects (tenant_id, incident_id, kind, s3_key) VALUES
 ('11111111-1111-1111-1111-111111111111','a3a3a3a3-0000-0000-0000-000000000001',
  'log','s3://ensayo/restore-drill.log');

INSERT INTO life_checkins (tenant_id, incident_id, user_id, site_id, status) VALUES
 ('11111111-1111-1111-1111-111111111111','a3a3a3a3-0000-0000-0000-000000000001',
  '99999999-9999-9999-9999-999999999999','aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','safe');

INSERT INTO damage_reports (tenant_id, incident_id, site_id, user_sub, categories, notes) VALUES
 ('11111111-1111-1111-1111-111111111111','a3a3a3a3-0000-0000-0000-000000000001',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa','99999999-9999-9999-9999-999999999999',
  '{"structural":"none"}','fila de ensayo: sin ella la guarda append-only no se ejerce');

-- El registro de auditoría lleva además una IDENTIDAD (`audit_id`): es la única
-- secuencia con dato detrás, y por tanto la que hace no vacía la comprobación de
-- secuencias por detrás del máximo.
INSERT INTO audit_log (tenant_id, actor, verb, object)
SELECT '11111111-1111-1111-1111-111111111111','drill','create','incident:'||g
FROM generate_series(1, 200) g;

-- ---- series de tiempo: las tres hypertables, con varios chunks -------------
INSERT INTO device_health (ts, tenant_id, gateway_id, reason)
SELECT now() - make_interval(secs => g * 60), '11111111-1111-1111-1111-111111111111',
       'a1a1a1a1-0000-0000-0000-000000000001', 'heartbeat'
FROM generate_series(1, 500) g;

INSERT INTO rule_evaluations (ts, tenant_id, site_id, gateway_id, prev_tier, new_tier)
SELECT now() - make_interval(secs => g * 300), '11111111-1111-1111-1111-111111111111',
       'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'a1a1a1a1-0000-0000-0000-000000000001',
       'normal', 'watch'
FROM generate_series(1, 200) g;

-- Repartida entre los DOS tenants a propósito: es el dato sobre el que la
-- comprobación de aislamiento mira si un tenant ve al vecino a través de la
-- vista security_barrier.
INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, channel, pga_g)
SELECT now() - make_interval(
         secs => g * (345600.0 / coalesce(current_setting('takab.drill_rows', true), '20000')::int)
       ),
       CASE WHEN g % 2 = 0
            THEN '11111111-1111-1111-1111-111111111111'::uuid
            ELSE '22222222-2222-2222-2222-222222222222'::uuid END,
       CASE WHEN g % 2 = 0
            THEN 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'::uuid
            ELSE 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'::uuid END,
       CASE WHEN g % 2 = 0
            THEN 'a2a2a2a2-0000-0000-0000-000000000001'::uuid
            ELSE 'b2b2b2b2-0000-0000-0000-000000000002'::uuid END,
       'EHZ', (random() * 0.05)::real
FROM generate_series(
       1, coalesce(current_setting('takab.drill_rows', true), '20000')::int
     ) g;
