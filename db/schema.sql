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

-- [T-2.80] Guard de UPDATE para `life_checkins`. Abre UNA sola rendija: anular
-- `geom` (anonimización ARCO). El DELETE no pasa por aquí — lo sigue vetando
-- `forbid_update_delete()`, sin excepción alguna.
--
-- El ocupante tiene derecho a que su ubicación exacta desaparezca y el sistema
-- tiene la obligación de conservar el check-in, que es evidencia de incidente y
-- además el conteo del que depende una decisión de rescate. Se anonimiza a la
-- persona sin borrar el hecho.
--
-- La comparación es `to_jsonb(NEW) - 'geom'` contra `to_jsonb(OLD) - 'geom'` y no
-- una lista de columnas a mano: así el guard cubre AUTOMÁTICAMENTE toda columna
-- que se añada a la tabla en el futuro. Una lista enumerada envejece en silencio
-- y el día que envejece deja pasar una reescritura de evidencia.
CREATE FUNCTION life_checkin_arco_guard() RETURNS trigger
  LANGUAGE plpgsql AS $$
BEGIN
  -- Red de seguridad: si alguien colgara esta función del evento DELETE en vez
  -- de `forbid_update_delete()`, el borrado seguiría sin pasar.
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'tabla append-only: % no permite %', TG_TABLE_NAME, TG_OP;
  END IF;
  -- La ÚNICA mutación admitida: `geom` pasa de TENER VALOR a NULL, con el resto
  -- de la fila idéntica. Dos exigencias, y las dos importan:
  --
  --   · exigir la transición real (no basta con que NEW.geom sea NULL) deja
  --     fuera el `UPDATE ... SET c = c` que no cambia nada. Un no-op sobre una
  --     tabla de evidencia no tiene por qué aceptarse, y aceptarlo hacía que el
  --     verificador de restore (`ops/restore_check.py`, que ejerce justo ese
  --     UPDATE) leyera "la guarda no existe o está desactivada";
  --   · comparar la fila entera menos `geom` vía `to_jsonb` —y no una lista de
  --     columnas— hace que el guard cubra SOLO las columnas que hoy existen y
  --     también las que se añadan mañana, sin que nadie vuelva a tocarlo.
  --
  -- El mensaje conserva el texto de `forbid_update_delete()` a propósito: para
  -- todo lo que no sea la anonimización de ARCO, esta tabla ES append-only, y el
  -- verificador de restore reconoce la guarda por ese texto y por su SQLSTATE.
  IF NOT (OLD.geom IS NOT NULL AND NEW.geom IS NULL)
     OR (to_jsonb(NEW) - 'geom') IS DISTINCT FROM (to_jsonb(OLD) - 'geom') THEN
    RAISE EXCEPTION
      'tabla append-only: % no permite % (unica excepcion: anular geom, '
      'anonimizacion ARCO)', TG_TABLE_NAME, TG_OP;
  END IF;
  RETURN NEW;
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
  -- [T-2.03·R1] Instrucción binaria de crisis POR ZONA (spec móvil §4.1):
  -- evacuate|shelter. NULL = sin política definida (la app lo declara, no inventa).
  evac_policy text CHECK (evac_policy IS NULL OR evac_policy IN ('evacuate','shelter')),
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
  -- Qué código HAY EN EL DISCO del gabinete (lo escribe `deploy.sh` en FW_VERSION
  -- y el latido lo declara). Cambia con el `rsync`, ANTES del reinicio.
  fw_version   text,
  -- [T-2.70] Qué código EJECUTA el proceso, congelado al arrancar. Cambia SOLO
  -- con un reinicio efectivo. Son dos hechos distintos y hay que guardarlos por
  -- separado: cuando difieren, hay código escrito que nadie está corriendo — un
  -- despliegue que se quedó a medias (el `uv sync` reventó, la unidad quedó en
  -- `failed`, el restart nunca ocurrió). Fundirlos en una sola columna hacía ese
  -- estado indetectable y daba por buena una actualización no aplicada.
  fw_running   text,
  iot_thing    text UNIQUE,
  status       text NOT NULL DEFAULT 'provisioned'
               CHECK (status IN ('provisioned','online','degraded','offline','retired')),
  has_wr1      boolean NOT NULL DEFAULT true,
  installed_at timestamptz,
  metadata     jsonb NOT NULL DEFAULT '{}',
  -- [T-2.31] Actuadores INSTALADOS en el sitio (contrato de 5 bools; default
  -- todo-true = compat retro). Viaja al edge fusionado en el config sync.
  equipment    jsonb NOT NULL DEFAULT
    '{"siren":true,"strobe":true,"gas_valve":true,"elevator":true,"door_retainer":true}'
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
  -- [T-2.84.e] La lectura LITERAL de la regla de oro 5. El aislamiento ya era
  -- real antes (un `EXISTS` contra `sites`, con el cruce de tenants verificado);
  -- lo que faltaba era la columna, y con ella una exención menos en el censo.
  tenant_id        uuid NOT NULL REFERENCES tenants(tenant_id),
  distance_m       numeric,
  PRIMARY KEY (site_id, ground_sensor_id)
);

CREATE INDEX idx_site_ground_refs_tenant ON site_ground_refs (tenant_id);

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
  -- [T-2.03] ts_device viaja junto al ts del servidor (honestidad de tiempos);
  -- el check-in DELEGADO del headcount (brigadista marca "verificado en persona")
  -- es distinguible del propio: via='delegated' + verified_by = sub del táctico.
  ts_device   timestamptz,
  via         text NOT NULL DEFAULT 'self' CHECK (via IN ('self','delegated')),
  verified_by uuid,
  geom        geography(Point,4326),                 -- PII de ubicación → LFPDPPP (§9)
  zone_id     uuid REFERENCES zones,
  created_at  timestamptz NOT NULL DEFAULT now()
);
-- [ANALISIS-00] Cambios de estado = fila nueva (historial de rescate auditable).
-- [T-2.80] DOS triggers y no uno, con los eventos SEPARADOS a propósito:
--
--   · DELETE → `forbid_update_delete()`, el guard CANÓNICO, el mismo que protege
--     auditoría, dictámenes y evidencia. No hay excepción de ARCO para borrar, y
--     por eso el borrado no merece un guard propio: usa exactamente el de todos.
--   · UPDATE → `life_checkin_arco_guard()`, que abre UNA rendija (geom → NULL).
--
-- Partirlos no es cosmética. `ops/restore_check.py` DERIVA de este DDL qué tablas
-- son append-only buscando `BEFORE UPDATE OR DELETE`, y el contract-test de
-- compliance cuenta triggers cuya función es `forbid_update_delete`. Con los
-- eventos juntos, un guard propio habría dicho "esta tabla dejó de ser
-- append-only" (falso: sigue siéndolo para DELETE) y habría tapado la garantía
-- que sí se conserva. Separados, cada verificador ve la verdad exacta.
CREATE TRIGGER trg_life_checkins_append_only
  BEFORE DELETE ON life_checkins
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE TRIGGER trg_life_checkins_arco_guard
  BEFORE UPDATE ON life_checkins
  FOR EACH ROW EXECUTE FUNCTION life_checkin_arco_guard();

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
  -- [T-2.70.a·B1 · migración 0036] ¿Pudo el gabinete leer el censo de sus relés?
  -- reported = lo publicó · stopped = preguntó y no hay filas (módulo detenido)
  -- unreadable = NO PUDO PREGUNTAR: nadie contesta como dueño de los pines
  --   (`gpio_owner=gpio` con `takab-gpio` caído ⇒ sin sirena, sin cierre de gas,
  --   sin retorno de ascensores y sin retenedores, mientras `takab-edge` late
  --   perfectamente y ninguna alarma de flota se entera).
  -- NULL = el gabinete no opina (contrato ≤1.9.0 o clave ausente) ⇒ S/D.
  relays_state text CHECK (relays_state IS NULL
                           OR relays_state IN ('reported','stopped','unreadable')),
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
  meta      jsonb NOT NULL DEFAULT '{}',
  -- [T-2.138] Clave de REENTREGA (0044), solo para los verbos que se escriben por
  -- ENTREGA y no por hecho (hoy `ingest_reject`, censo en `takab_api/audit.py`).
  -- La huella dice "el mismo hecho"; la cubeta lo acota al horizonte de reentrega
  -- de SQS. La clave NO es (tenant, actor, verb, object, meta): eso colapsaría
  -- rechazos genuinamente distintos —la razón la compone el cross-check de
  -- identidad y se repite idéntica— y sería peor que duplicar uno (T-2.136).
  dedupe_digest text,
  dedupe_bucket bigint,
  -- Media clave es peor que ninguna: sin cubeta, el índice parcial no la vigila.
  CONSTRAINT audit_log_dedupe_completa
    CHECK ((dedupe_digest IS NULL) = (dedupe_bucket IS NULL))
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
-- [T-2.138] Impone la clave de reentrega Y sirve la comprobación previa (la
-- huella es la columna de la izquierda). Parcial: la bitácora normal —toda fila
-- sin huella— no entra en el índice ni paga por él.
CREATE UNIQUE INDEX idx_audit_log_dedupe ON audit_log (dedupe_digest, dedupe_bucket)
  WHERE dedupe_digest IS NOT NULL;

-- [T-2.86.a] BITÁCORA DE ACTUACIÓN DEL GABINETE — el hueco `RO-4.e`.
--
-- `audit_log` de arriba es la bitácora de la NUBE: solo sabe lo que pasó por la
-- API. El caso exacto para el que existe el gabinete —regla de oro 2, el edge
-- opera sin nube— era justo el que no dejaba rastro aquí: si el gas se cierra
-- durante un corte de internet, nadie podía decir después quién lo ordenó ni con
-- qué causa. Es lo primero que pide un perito o un seguro.
--
-- `record_id` lo pone EL GABINETE y es la PK: la subida es idempotente por él
-- (regla de oro 3). El edge no borra su copia local al subir —el perito la lee
-- meses después—, avanza una marca de agua; si esa marca se pierde, re-subir es
-- gratis gracias a `ON CONFLICT DO NOTHING`.
--
-- `online` es TRI-ESTADO: true/false/NULL = «no se pudo saber». Colapsar el NULL
-- a false sería inventar un dato en la tabla que existe para no inventarlo.
--
-- No se poda nunca (regla de oro 11). Tabla normal, no hypertable: el registro es
-- POR EVENTO (regla de oro 10), no por intervalo.
CREATE TABLE actuation_records (
  record_id   uuid PRIMARY KEY,
  tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
  site_id     uuid NOT NULL REFERENCES sites(site_id),
  gateway_id  uuid NOT NULL REFERENCES gateways(gateway_id),
  seq         bigint NOT NULL,
  occurred_at timestamptz NOT NULL,
  cause       text NOT NULL,
  actor       text NOT NULL,
  channel     text NOT NULL,
  action      text NOT NULL,
  success     boolean NOT NULL,
  detail      text NOT NULL DEFAULT '',
  event_id    text NOT NULL DEFAULT '',
  online      boolean,
  ingested_at timestamptz NOT NULL DEFAULT now()
);
-- Append-only por la misma razón que `audit_log`: es evidencia. La ingesta solo
-- hace INSERT ... ON CONFLICT DO NOTHING, así que no pierde nada.
REVOKE UPDATE, DELETE ON actuation_records FROM PUBLIC;
-- Y del rol de la API POR SU NOMBRE. `FROM PUBLIC` solo quita lo que se concede a
-- todos; un grant explícito —o uno futuro, hecho sin pensar en esto— sobrevive. Con
-- las dos líneas la protección tiene DOS capas: el privilegio y el trigger. Con una
-- sola, quitar el trigger «para una migración» dejaría la bitácora borrable sin que
-- nada más lo impidiera.
REVOKE UPDATE, DELETE ON actuation_records FROM takab_app;
CREATE TRIGGER trg_actuation_records_append_only
  BEFORE UPDATE OR DELETE ON actuation_records
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
-- La consulta del perito: «qué hizo ESTE gabinete, en orden».
CREATE INDEX idx_actuation_records_gateway_at
  ON actuation_records (gateway_id, occurred_at DESC);
-- La otra pregunta real: «¿qué se actuó a oscuras?». Parcial porque las filas con
-- enlace son la inmensa mayoría y no interesan aquí.
CREATE INDEX idx_actuation_records_offline
  ON actuation_records (tenant_id, occurred_at DESC)
  WHERE online IS NOT TRUE;

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
-- [T-2.84.e] Por COLUMNA, y con los CUATRO caminos ENUMERADOS. El `EXISTS`
-- anterior no llevaba condición de tenant: bajo RLS, ese SELECT anidado veía
-- exactamente lo que `sites_read` permite —propio tenant, TAKAB interno,
-- `gov_operator` sobre tenants `gov_shared`, y los grants de metadatos de
-- T-1.73—. Escribir `tenant_id = app_tenant_id()` a secas habría QUITADO las
-- tres últimas sin que nada se quejara: una regresión de visibilidad camuflada
-- en una migración de «sólo añadir una columna».
CREATE POLICY sgr_read ON site_ground_refs FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR app_gov_can_see(tenant_id) OR app_can_view_meta(tenant_id));
-- NO hay `sgr_admin`, y la ausencia se conserva a propósito: antes tampoco
-- existía, así que TAKAB interno LEE esta tabla pero no la ESCRIBE. Ampliar eso
-- es una decisión de permisos, no un efecto colateral de añadir una columna.
CREATE POLICY sgr_write ON site_ground_refs FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');

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
-- [T-2.80] La política de UPDATE (`lc_arco_geom`) NO va aquí: necesita
-- `app_user_id()`, que este fichero define ~300 líneas más abajo. Está en el
-- bloque de ARCO, al final.

-- [T-2.03] Privilegios del DDL latente móvil (las políticas de arriba existían,
-- pero sin GRANT takab_app no podía tocar las tablas).
GRANT SELECT, INSERT, UPDATE, DELETE ON user_zone_assignments TO takab_app;
GRANT SELECT, INSERT, UPDATE ON site_enrollment_codes TO takab_app;
GRANT SELECT, INSERT, UPDATE ON manual_activation_votes TO takab_app;
-- [T-2.80] El `UPDATE (geom)` por columna NO va aquí: se concede al final del
-- fichero, después del `REVOKE UPDATE` que lo hace efectivo (un GRANT a nivel de
-- tabla concede todas las columnas y el GRANT por columna no lo estrecha).
GRANT SELECT, INSERT ON life_checkins TO takab_app;

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE  ROW LEVEL SECURITY;
CREATE POLICY audit_read ON audit_log FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY audit_insert ON audit_log FOR INSERT
  WITH CHECK (true);   -- cualquier request autenticado registra; lectura sí restringida

-- [T-2.86.a] actuation_records: la bitácora que ESCRIBE EL GABINETE. Lectura por
-- tenant; escritura de NADIE por política — la ingesta va con BYPASSRLS y por eso
-- no aparece aquí. Que `takab_app` no tenga INSERT es la decisión: una bitácora
-- que la API pudiera escribir dejaría de ser prueba de lo que hizo el gabinete.
GRANT SELECT ON actuation_records TO takab_app;
-- La ingesta INSERTA y nada más: sin UPDATE ni DELETE, que es lo que hace de esto
-- una prueba y no un registro editable. El `ON CONFLICT DO NOTHING` de la re-subida
-- no necesita UPDATE — justamente por eso «no hacer nada» es la resolución correcta.
GRANT SELECT, INSERT ON actuation_records TO takab_ingest;
ALTER TABLE actuation_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE actuation_records FORCE  ROW LEVEL SECURITY;
CREATE POLICY actuation_records_read ON actuation_records FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());

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
  action      text NOT NULL CHECK (action IN ('activate','deactivate','self_test',
              'drill_start','drill_stop','update_activate','update_rollback')),
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
-- [T-2.32] Ledger idempotente del burst de quórum: el actor sistema (UUID
-- espejo de commands/quorum_actuation.py) no puede duplicar (gateway,evento,canal).
CREATE UNIQUE INDEX idx_commands_quorum_ledger
  ON commands (gateway_id, event_id, channel)
  WHERE issued_by = '00000000-0000-4000-8000-00000000c092';
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

-- [T-2.24] Estado del catálogo SSN firmado publicado por gateway (espejo del
-- de config): versión MONÓTONA anti-replay + huella de qué instantánea salió
-- a quién. Lo escribe la API (push interno superadmin/support), no la ingesta.
CREATE TABLE gateway_catalog_state (
  gateway_id   uuid PRIMARY KEY REFERENCES gateways(gateway_id) ON DELETE CASCADE,
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  version      integer NOT NULL,
  payload      jsonb NOT NULL,
  sig          text NOT NULL,
  published_at timestamptz NOT NULL DEFAULT now(),
  -- [T-2.148] «Miré y era el mismo catálogo». NO es `published_at`: aquél dice
  -- cuándo se publicó por última vez, y su virtud es no moverse cuando no se
  -- publica. Sin esta columna, con el job de D-06 «corre y no hay novedad» sería
  -- indistinguible de «el job murió» — el modo de fallo que esa decisión quería
  -- evitar al automatizar contra una fuente de terceros.
  -- NULL = no se ha comprobado NUNCA, que es un hecho distinto de «hace mucho».
  --
  -- ⚠️ Hasta el 2026-08-22 esta columna estaba en `gateway_config_state`, la tabla
  -- de al lado. La migración 0045 SÍ la puso aquí, así que las dos fuentes de
  -- verdad del DDL divergían: la de config era huérfana (cero lectores) y una base
  -- creada desde este fichero reventaba en `_CATALOG_TOUCH_SQL`. No se veía porque
  -- los tests arrancan por `alembic upgrade head` y nada comparaba las dos fuentes;
  -- ahora lo hace `api/tests/test_schema_espejo_de_migraciones.py`.
  last_checked_at timestamptz
);
GRANT SELECT, INSERT, UPDATE ON gateway_catalog_state TO takab_app;

ALTER TABLE gateway_catalog_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE gateway_catalog_state FORCE  ROW LEVEL SECURITY;
CREATE POLICY gateway_catalog_state_read ON gateway_catalog_state FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY gateway_catalog_state_admin ON gateway_catalog_state FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

-- [T-2.69] Registro de releases de firmware: contra QUÉ se mide la deriva de la
-- flota. `gateways.fw_version` dice qué corre cada gabinete, pero no si eso es lo
-- actual: `deploy/edge/deploy.sh` escribe `git describe --always --dirty
-- --abbrev=7` sobre un repo SIN TAGS, así que el valor es un SHA de 7 hex (a veces
-- con sufijo `-dirty`) — no es semver, no es monótono, NO ES ORDENABLE, y la única
-- relación decidible entre dos valores es la IGUALDAD. Sin esta tabla, "cuántos
-- releases atrás y cuánto tiempo" no tiene respuesta honesta y "corre una versión
-- que nadie publicó" es indetectable.
-- [EXCEPCIÓN DOCUMENTADA] a "tenant_id en toda tabla", misma familia que
-- reference_earthquakes: qué firmware existe lo decide TAKAB, no el cliente. Cada
-- tenant sigue viendo solo la deriva de SUS gabinetes porque eso lo acota la RLS
-- de `gateways`. Lectura: cualquier rol autenticado. Escritura: takab_superadmin.
-- APPEND-ONLY POR PRIVILEGIO (sin UPDATE/DELETE concedidos): reescribir la fecha
-- de un release reescribiría a posteriori la deriva de toda la flota.
CREATE TABLE fw_releases (
  release_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version      text NOT NULL UNIQUE CHECK (length(version) BETWEEN 1 AND 64),  -- = _FW_VERSION_MAX_LEN de la ingesta
  released_at  timestamptz NOT NULL DEFAULT now(),
  seq          bigint GENERATED ALWAYS AS IDENTITY,   -- desempate estable de `released_at`
  notes        text,
  published_by text
);
CREATE INDEX idx_fw_releases_order ON fw_releases (released_at DESC, seq DESC);
-- Append-only por privilegio: sin UPDATE ni DELETE. Reescribir la fecha de un
-- release reescribiría A POSTERIORI la deriva de toda la flota.
-- OJO: este GRANT por sí solo NO basta en una base nueva. La migración 0001
-- aplica ESTE archivo y después hace `GRANT ... ON ALL TABLES IN SCHEMA public
-- TO takab_app`, que devuelve UPDATE/DELETE a esta tabla. El REVOKE que cierra
-- el agujero vive en la migración 0028 (que corre en ambos caminos, nuevo e
-- incremental); ver su cabecera. Medido en una base nueva: `takab_app=arwd`.
GRANT SELECT, INSERT ON fw_releases TO takab_app;

ALTER TABLE fw_releases ENABLE ROW LEVEL SECURITY;
ALTER TABLE fw_releases FORCE  ROW LEVEL SECURITY;
CREATE POLICY fw_rel_read ON fw_releases FOR SELECT
  USING (app_role() IS NOT NULL);
CREATE POLICY fw_rel_publish ON fw_releases FOR INSERT
  WITH CHECK (app_role() = 'takab_superadmin');

-- [T-2.36] Segundo factor para RETIRAR una estación. Retirar un gabinete lo saca
-- del config sync firmado y de los comandos de actuación: deja un edificio sin
-- protección, así que exige un código que TAKAB entrega fuera de banda y solo el
-- superadmin rota. bcrypt vía pgcrypto (coste 12); el hash NUNCA sale de la base
-- —se pregunta por función SECURITY DEFINER— y no hay política de lectura para
-- roles de tenant: ni el tenant_admin que lo usa ve su propio hash.
CREATE TABLE tenant_retire_codes (
  tenant_id  uuid PRIMARY KEY REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  code_hash  text NOT NULL,
  version    integer NOT NULL DEFAULT 1,
  rotated_by uuid NOT NULL,
  rotated_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE ON tenant_retire_codes TO takab_app;

-- ENABLE sin FORCE, única excepción del esquema y deliberada: FORCE sujeta también
-- al DUEÑO, y el dueño es quien debe poder leer el hash desde las funciones
-- SECURITY DEFINER de abajo (SECURITY DEFINER cambia el USUARIO, no los GUC: con
-- FORCE, `app_role()` seguiría siendo 'tenant_admin' y verificar el código sería
-- imposible). `takab_app` NO es dueño ⇒ sigue sujeto a RLS y no tiene política de
-- lectura: la API no puede leer el hash ni queriendo.
ALTER TABLE tenant_retire_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_retire_codes NO FORCE ROW LEVEL SECURITY;
CREATE POLICY trc_admin ON tenant_retire_codes FOR ALL
  USING (app_role() = 'takab_superadmin') WITH CHECK (app_role() = 'takab_superadmin');

CREATE FUNCTION app_verify_retire_code(t uuid, candidate text)
  RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT EXISTS (
    SELECT 1 FROM tenant_retire_codes c
     WHERE c.tenant_id = t AND c.code_hash = crypt(candidate, c.code_hash)
  )
$$;

CREATE FUNCTION app_retire_code_state(t uuid)
  RETURNS TABLE (version integer, rotated_at timestamptz)
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT c.version, c.rotated_at FROM tenant_retire_codes c WHERE c.tenant_id = t
$$;

REVOKE ALL ON FUNCTION app_verify_retire_code(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app_retire_code_state(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_verify_retire_code(uuid, text) TO takab_app;
GRANT EXECUTE ON FUNCTION app_retire_code_state(uuid) TO takab_app;

-- Cascada de notificación (T-1.21 · blueprint §5.6): un job por (incidente,
-- canal, modo) — UNIQUE = idempotencia del orquestador ante re-entregas.
CREATE TABLE notification_jobs (
  job_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
  incident_id uuid NOT NULL REFERENCES incidents(incident_id) ON DELETE RESTRICT,
  -- [T-2.04] 'push' = despertador móvil (SNS platform endpoints), job paralelo.
  channel     text NOT NULL CHECK (channel IN ('webhook','whatsapp','sms','email','push')),
  mode        text NOT NULL CHECK (mode IN ('cascade','parallel')),
  position    integer NOT NULL DEFAULT 0,
  -- [T-2.75] 'simulated' = canal SIN proveedor real: nadie recibió nada. No es
  -- 'sent' (sería mentir) ni 'failed' (no hay proveedor que arreglar ni al que
  -- reintentar). Es TERMINAL y deja `sent_at` en NULL, de modo que cualquier
  -- consulta de entregados lo excluya sin tener que conocerlo.
  status      text NOT NULL DEFAULT 'pending'
              CHECK (status IN ('pending','sent','failed','skipped','simulated')),
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
  attempts    integer NOT NULL DEFAULT 0,
  -- [T-2.77.b · 0040] EL DESENLACE TARDÍO. `sent_at` significa "el proveedor lo
  -- aceptó" (SES aceptó el correo, Twilio encoló el SMS, Meta aceptó el mensaje);
  -- ninguno de los tres afirma que un humano lo tenga en la mano. Estas cuatro
  -- columnas son el sitio donde escribir "salió a las 12:00:03 y llegó a las
  -- 12:00:19", que hasta la 0040 no existía.
  --   · provider_message_id — con lo que se casa el callback (MessageSid de
  --     Twilio, id de mensaje de Meta). Sin persistirlo no hay con qué casar nada.
  --   · delivered_at        — la entrega CONFIRMADA. Solo 'delivered'/'read'.
  --   · last_status(_at)    — la última palabra del proveedor, que es lo que
  --     permite ordenar callbacks que llegan desordenados (un 'sent' retrasado
  --     no puede hacer retroceder un 'delivered').
  provider_message_id text,
  delivered_at        timestamptz,
  last_status         text,
  last_status_at      timestamptz,
  -- [T-2.77.c · 0040] La guarda de duplicados, que vivía en la memoria de UN
  -- worker. Instante hasta el que este job PUEDE tener un mensaje vivo en el
  -- proveedor (TTL = ValidityPeriod de Twilio / TTL de la plantilla de Meta):
  -- mientras no venza, un reintento NO sale y se escala en vez de duplicar.
  -- Vive aquí y no en una tabla propia porque la clave del dominio era
  -- (destino, incidente) y para los canales guardados eso ES una fila de esta
  -- tabla — con su tenant_id, su RLS y su retención ya puestos.
  inflight_until      timestamptz
);
-- [T-1.61] Unicidad dividida (0014): la clave original solo para jobs de
-- incidente; 1 job por acción y canal para los de acción (re-runs no duplican).
CREATE UNIQUE INDEX uq_notification_jobs_incident
  ON notification_jobs (incident_id, channel, mode) WHERE action_id IS NULL;
CREATE UNIQUE INDEX uq_notification_jobs_action
  ON notification_jobs (action_id, channel) WHERE action_id IS NOT NULL;
-- [T-2.77.b] Un identificador de proveedor pertenece a UN job. UNIQUE y no
-- índice a secas: atribuir una entrega al job equivocado es peor que un fallo
-- ruidoso. Es además la única llave de entrada del webhook público.
CREATE UNIQUE INDEX uq_notification_jobs_provider_msg
  ON notification_jobs (channel, provider_message_id) WHERE provider_message_id IS NOT NULL;
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

-- [T-2.77.c · 0040] La cuarentena de plantillas, que vivía en la memoria del
-- worker: al reiniciar se olvidaba y se volvía a martillear una plantilla que
-- Meta había pausado — que es exactamente lo que degrada su calificación de
-- calidad y termina costando el canal entero.
--
-- SIN `tenant_id` y con razón declarada (exención en
-- `api/tests/test_censo_multitenancy.py`): la plantilla pertenece a la cuenta de
-- negocio del DESPLIEGUE —una WABA para toda la flota—, no a un cliente. Una
-- columna de tenant aquí tendría que inventarse un dueño.
--
-- Y NADIE tiene DELETE a propósito: levantar una cuarentena es un acto humano
-- deliberado (volver a someter la plantilla y que Meta la apruebe), no el efecto
-- colateral de un reinicio. Lo hace el dueño del esquema.
CREATE TABLE notify_template_quarantine (
  channel        text NOT NULL,
  template_name  text NOT NULL,
  reason         text NOT NULL,
  quarantined_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (channel, template_name)
);
GRANT SELECT ON notify_template_quarantine TO takab_app;
GRANT SELECT, INSERT, UPDATE ON notify_template_quarantine TO takab_ingest;

ALTER TABLE notify_template_quarantine ENABLE ROW LEVEL SECURITY;
ALTER TABLE notify_template_quarantine FORCE  ROW LEVEL SECURITY;
CREATE POLICY ntq_read ON notify_template_quarantine FOR SELECT
  USING (app_role() IS NOT NULL);   -- estado de la PLATAFORMA, como seismic_events

-- [T-2.77.b · 0040] El desenlace tardío, escrito desde una superficie PÚBLICA.
--
-- El webhook de entrega no puede ir detrás de Cognito (lo llama Twilio o Meta),
-- así que no trae `app.tenant_id` ni `app.role`. La API conecta como takab_app,
-- que sobre notification_jobs solo tiene SELECT y cuya RLS es default-deny con
-- FORCE: ni con un GRANT UPDATE podría escribir. Y takab_app NO puede volverse
-- takab_ingest (no es miembro, y el DSN lo dice: "La API NUNCA usa takab_ingest").
--
-- Mismo patrón que gov_ack_incident / app_verify_retire_code: SECURITY DEFINER,
-- dueño takab_ingest (BYPASSRLS), REVOKE FROM PUBLIC + GRANT solo a takab_app, y
-- la validación DENTRO. Lo que se abre no es "escribir en notification_jobs":
-- es "mover el desenlace de UN job identificado por un id de proveedor, y solo
-- hacia adelante".
--
-- `p_outranks` = los estados que el nuevo puede pisar; la escala vive en Python
-- (`notify/callbacks.STATUS_RANK`) y esta función es mecanismo puro. Un estado
-- que no pise al que ya está escrito —incluido él mismo— no cambia NADA: de ahí
-- que un reenvío sea inerte y que un 'sent' retrasado no borre un 'delivered'.
CREATE FUNCTION app_notify_delivery(
  p_channel text, p_message_id text, p_status text, p_outranks text[],
  p_delivered boolean, p_undelivered boolean, p_at timestamptz, p_detail text
) RETURNS TABLE (o_job_id uuid, o_applied boolean, o_job_status text,
                 o_last_status text, o_delivered_at timestamptz)
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_job    notification_jobs%ROWTYPE;
  v_at     timestamptz := LEAST(coalesce(p_at, now()), now());
  v_kind   text := NULL;
  v_opened timestamptz;
BEGIN
  SELECT * INTO v_job FROM notification_jobs
   WHERE channel = p_channel AND provider_message_id = p_message_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RETURN;  -- cero filas: indistinguible de una firma mala para quien llama
  END IF;

  IF v_job.last_status IS NOT NULL AND NOT (v_job.last_status = ANY (p_outranks)) THEN
    RETURN QUERY SELECT v_job.job_id, false, v_job.status, v_job.last_status,
                        v_job.delivered_at;
    RETURN;
  END IF;

  UPDATE notification_jobs j
     SET last_status    = p_status,
         last_status_at = v_at,
         delivered_at   = CASE WHEN p_delivered AND j.delivered_at IS NULL
                               THEN v_at ELSE j.delivered_at END,
         status         = CASE WHEN p_delivered THEN 'sent'
                               WHEN p_undelivered AND j.delivered_at IS NULL THEN 'failed'
                               ELSE j.status END,
         error          = CASE WHEN p_undelivered AND j.delivered_at IS NULL
                               THEN left(coalesce(p_detail, p_status), 500) ELSE j.error END
   WHERE j.job_id = v_job.job_id
  RETURNING j.* INTO v_job;

  -- Evidencia SOLO en los dos hechos terminales (regla de oro 10).
  IF p_delivered AND v_job.delivered_at = v_at THEN
    v_kind := 'notify_delivered';
  ELSIF p_undelivered AND v_job.status = 'failed' THEN
    v_kind := 'notify_failed';
  END IF;

  IF v_kind IS NOT NULL THEN
    SELECT opened_at INTO v_opened FROM incidents WHERE incident_id = v_job.incident_id;
    INSERT INTO incident_actions (incident_id, tenant_id, kind, actor, payload)
    VALUES (v_job.incident_id, v_job.tenant_id, v_kind,
            'system:notify:' || p_channel || ':' || 'callback',
            jsonb_build_object(
              'job_id', v_job.job_id, 'channel', p_channel, 'mode', v_job.mode,
              'provider_status', p_status, 'provider_message_id', p_message_id,
              'detail', left(coalesce(p_detail, ''), 500),
              'sent_at', v_job.sent_at, 'delivered_at', v_job.delivered_at,
              'latency_s', CASE WHEN v_opened IS NOT NULL
                                THEN extract(epoch FROM (v_at - v_opened)) END,
              'deadline_met', CASE WHEN v_job.deadline_at IS NULL THEN NULL
                                   ELSE v_at <= v_job.deadline_at END))
    ON CONFLICT (incident_id, kind, actor, ts) DO NOTHING;
  END IF;

  RETURN QUERY SELECT v_job.job_id, true, v_job.status, v_job.last_status, v_job.delivered_at;
END
$fn$;
-- LA CESIÓN DE PROPIEDAD **NO VA AQUÍ**, y no es un olvido. Este cuerpo lo
-- ejecuta la 0001 bajo `SET ROLE takab_migrator`, que NO es miembro de
-- `takab_ingest`: un `ALTER FUNCTION ... OWNER TO takab_ingest` en este fichero
-- mata la migración inicial con `must be able to SET ROLE "takab_ingest"` (medido
-- contra una base vacía, 2026-08-13). El dueño lo pone la 0040 —con el usuario de
-- conexión y dentro de la ventana de privilegios que abre `deploy/cloud/deploy.sh`—
-- y ahí mismo se COMPRUEBA: sin dueño `takab_ingest` la función no ve una sola
-- fila (RLS FORCE) y el webhook contestaría «no reconozco esto» para siempre.
-- Mismo trato que `relocate_incident_epicenter` (0011).
REVOKE ALL ON FUNCTION app_notify_delivery(text,text,text,text[],boolean,boolean,
  timestamptz,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_notify_delivery(text,text,text,text[],boolean,boolean,
  timestamptz,text) TO takab_app;

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
  stop_reason  text,
  -- [T-2.03·D4c] AGENDA informativa ("próximo simulacro" de la app): una fila con
  -- scheduled_at es ANUNCIO, jamás deriva `active` ni emite comandos — LO REAL GANA.
  scheduled_at timestamptz
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

-- [T-2.70] CANARY POR COHORTES. «Un despliegue a toda la flota a la vez es un
-- incidente a toda la flota a la vez»: el gabinete ya sabe activar con remojo y
-- volver atrás solo, pero sin disciplina de ORDEN entre gabinetes el canary es
-- una buena intención que se salta quien tiene prisa.
--
-- POR TENANT a propósito. Actualizar toda la flota de golpe es justo lo que esta
-- ficha existe para impedir, así que forzar un rollout por cliente no es una
-- limitación del modelo: es la política, escrita donde no se puede saltar.
--
-- `target_fw` se GUARDA y no se deriva al leer: es el SHA que
-- `gateways.fw_running` tiene que declarar para que el canary cuente como
-- confirmado, y congelarlo evita que dos consultas discrepen sobre qué se
-- estaba esperando.
CREATE TABLE fleet_rollouts (
  rollout_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  release_id   text NOT NULL,
  target_fw    text NOT NULL,
  created_by   uuid NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  state        text NOT NULL DEFAULT 'canary'
               CHECK (state IN ('canary','desplegado','abortado')),
  finished_at  timestamptz,
  abort_reason text
);

CREATE TABLE fleet_rollout_sites (
  rollout_id   uuid NOT NULL REFERENCES fleet_rollouts(rollout_id) ON DELETE CASCADE,
  site_id      uuid NOT NULL REFERENCES sites(site_id),
  tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
  phase        text NOT NULL CHECK (phase IN ('canary','resto')),
  command_id   uuid REFERENCES commands(command_id),  -- NULL = todavía sin activar
  activated_at timestamptz,
  PRIMARY KEY (rollout_id, site_id)
);

CREATE INDEX idx_fleet_rollouts_tenant_created
  ON fleet_rollouts (tenant_id, created_at DESC);

GRANT SELECT, INSERT, UPDATE ON fleet_rollouts TO takab_app;
GRANT SELECT, INSERT, UPDATE ON fleet_rollout_sites TO takab_app;

-- NO hay política de ESCRITURA por tenant, y la ausencia es la decisión: quien
-- escribe aquí porta `deploy_firmware`, que sólo tiene `takab_superadmin` — o
-- sea `app_is_takab_internal()`. Una política por `tenant_id` abriría la tabla a
-- un `tenant_admin` cuya sesión coincidiera en tenant, que es justo el rol al
-- que la matriz le niega empujar código. La LECTURA sí es por tenant: un cliente
-- puede ver que a sus gabinetes se les está actualizando, y ocultárselo sería la
-- clase de opacidad que la regla de oro 7 persigue.
ALTER TABLE fleet_rollouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE fleet_rollouts FORCE  ROW LEVEL SECURITY;
CREATE POLICY fleet_rollouts_read ON fleet_rollouts FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY fleet_rollouts_admin ON fleet_rollouts FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

ALTER TABLE fleet_rollout_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE fleet_rollout_sites FORCE  ROW LEVEL SECURITY;
CREATE POLICY fleet_rollout_sites_read ON fleet_rollout_sites FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY fleet_rollout_sites_admin ON fleet_rollout_sites FOR ALL
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
  -- [T-2.03·R4] Teléfono para la llamada de un toque del roster (PII, con
  -- consentimiento registrado; lo cura building_admin/tenant_admin).
  phone        text,
  updated_at   timestamptz NOT NULL DEFAULT now(),
  -- [T-2.80.b] Redundante con el PK (un `sub` vive en UN solo tenant) y aun así
  -- obligatoria: es el ANCLA del FK compuesto de `privacy_erasure_requests`. Sin
  -- ella ese FK no se puede declarar, y sin ese FK una constancia de ARCO podría
  -- nombrar a un titular de otro cliente. Esta línea es lo que convierte el
  -- confinamiento por tenant en integridad referencial en vez de en un `IF`.
  CONSTRAINT uq_user_profiles_tenant_sub UNIQUE (tenant_id, user_sub)
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

-- [T-2.81.b · 0042] EL RELOJ QUE LE FALTABA AL NOMBRE Y AL TELÉFONO
--
-- `user_profiles.display_name` y `phone` son PII con caducidad y la T-2.81 los
-- dejó FUERA del plan de retención con su razón escrita: la única columna
-- temporal de la tabla era `updated_at`, y un perfil sin tocar en dos años
-- describe a un empleado ESTABLE, no a uno que se fue. Usarla como caducidad
-- habría borrado antes los nombres de quien más tiempo lleva en el edificio —
-- exactamente al revés de lo que la retención pretende.
--
-- El reloj correcto es la BAJA DE LA CUENTA, y hasta hoy no se registraba en
-- ninguna parte. Aquí se registra.
--
-- POR QUÉ UNA TABLA Y NO UNA COLUMNA EN `user_profiles`
-- ─────────────────────────────────────────────────────
-- La razón no es de estilo, es de privilegio. Quien da de baja es el
-- `tenant_admin` (acción `manage_users`), que **no** es un rol interno de
-- TAKAB: sobre `user_profiles` sus únicas políticas son "mi propia fila"
-- (`user_profiles_self_write`) e "interno" (`user_profiles_admin`). Poner el
-- reloj como columna habría exigido abrir una política de UPDATE del
-- `tenant_admin` sobre las filas de OTROS — y como `WITH CHECK` no puede
-- comparar contra la fila vieja, esa misma política le habría dejado reescribir
-- `display_name` y `phone` de cualquiera del padrón. Se habría ensanchado la
-- escritura sobre las dos columnas de PII que esta ficha existe para proteger.
--
-- Con tabla propia, la superficie de escritura de `user_profiles` **no cambia
-- ni un bit**: el administrador escribe el HECHO, no el dato personal.
--
-- Y el hecho es un acto, no un atributo: tiene instante y tiene vía. **QUIÉN lo
-- hizo no se copia aquí**: ya está en `audit_log` (`user_update`/`user_delete`,
-- escrito en la MISMA transacción), que es append-only y no se poda jamás.
-- Duplicarlo en una columna mutable sería guardar la versión peor del mismo dato.
--
-- El FK COMPUESTO contra el padrón es el mismo candado de
-- `privacy_erasure_requests` (T-2.80.b): dar de baja a alguien de otro cliente
-- no se rechaza por una comprobación, viola integridad referencial.
--
-- LA VUELTA TAMBIÉN ES UN HECHO. `PATCH {"enabled": false}` es la baja
-- REVERSIBLE que la consola ofrece primero (`routers/users.py`), así que sin
-- `reactivated_at` una persona readmitida seguiría con el reloj corriendo y la
-- retención le borraría el nombre estando en el edificio. Se para el reloj, no
-- se borra la fila: quién la dio de baja y cuándo es información de operación.
CREATE TABLE user_deactivations (
  tenant_id      uuid NOT NULL REFERENCES tenants,
  user_sub       uuid NOT NULL,
  deactivated_at timestamptz NOT NULL DEFAULT now(),
  -- Cómo dejó de estar: cuenta deshabilitada (reversible) o cuenta borrada del
  -- directorio. No se admite un tercer valor "manual" — un reloj que alguien
  -- pueda poner a mano sin dar de baja la cuenta deja de ser el reloj de la baja.
  via            text NOT NULL CHECK (via IN ('account_disabled','account_deleted')),
  reactivated_at timestamptz,
  PRIMARY KEY (tenant_id, user_sub),
  CONSTRAINT fk_baja_del_padron_del_tenant FOREIGN KEY (tenant_id, user_sub)
    REFERENCES user_profiles (tenant_id, user_sub) ON DELETE CASCADE,
  CONSTRAINT ud_la_vuelta_es_posterior
    CHECK (reactivated_at IS NULL OR reactivated_at >= deactivated_at)
);
-- El job de retención pregunta "quién lleva de baja más de N días, sin volver".
CREATE INDEX idx_user_deactivations_reloj
  ON user_deactivations (tenant_id, deactivated_at)
  WHERE reactivated_at IS NULL;

GRANT SELECT, INSERT, UPDATE ON user_deactivations TO takab_app;
-- La vuelta se ESCRIBE (`reactivated_at`), no se borra: una baja que se puede
-- hacer desaparecer es un reloj que se puede parar sin dejar rastro.
REVOKE DELETE ON user_deactivations FROM takab_app;

ALTER TABLE user_deactivations ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_deactivations FORCE  ROW LEVEL SECURITY;
-- Mismo círculo que `manage_users` en `auth/matrix.py`. La acción de matriz solo
-- hace que el 403 llegue limpio; quien confina es esto.
CREATE POLICY ud_admin ON user_deactivations FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() = 'tenant_admin')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() = 'tenant_admin');
-- Los roles internos, exactamente como en `user_profiles_admin`: el superadmin
-- da de baja en cualquier cliente (`routers/users.py` ya se lo permite) y el job
-- de retención —que corre como `takab_support`— tiene que LEER el reloj de todos
-- los tenants para poder recorrerlos.
CREATE POLICY ud_internal ON user_deactivations FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

-- ---------------------------------------------------------------------------
-- SUPERFICIE MÓVIL (T-2.03 · Fase 2, spec §5/§5.1)
-- push_tokens/device_keys = PII de dispositivo: SOLO la fila propia
-- (app_user_id()) + *_admin interno; sin rama gov. damage_reports es EVIDENCIA
-- (append-only, lectura con rama gov como incidents). compliance_labels: los
-- strings normativos se SIRVEN por tenant (§2.1-C; escritura interna hasta
-- ratificar el marco citable — GATE-LEGAL). site_assets: rutas/punto de
-- reunión/manual cacheables offline.
-- ---------------------------------------------------------------------------
CREATE TABLE push_tokens (
  push_token_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants,
  user_sub      uuid NOT NULL,
  platform      text NOT NULL CHECK (platform IN ('ios','android')),
  token         text NOT NULL UNIQUE,
  site_id       uuid REFERENCES sites,
  -- [T-2.04] Endpoint de SNS cacheado por el worker (se crea al primer envío);
  -- NULL = aún sin mapear. El worker también REVOCA (revoked_at) los endpoints
  -- que SNS reporta deshabilitados.
  endpoint_arn  text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz NOT NULL DEFAULT now(),
  revoked_at    timestamptz
);
CREATE INDEX idx_push_tokens_user ON push_tokens (user_sub);
CREATE INDEX idx_push_tokens_site ON push_tokens (site_id) WHERE revoked_at IS NULL;
GRANT SELECT, INSERT, UPDATE, DELETE ON push_tokens TO takab_app;
-- el worker de notify resuelve destinos, sella endpoint_arn y revoca muertos
GRANT SELECT, UPDATE ON push_tokens TO takab_ingest;

ALTER TABLE push_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE push_tokens FORCE  ROW LEVEL SECURITY;
CREATE POLICY pt_self ON push_tokens FOR ALL
  USING      (tenant_id = app_tenant_id() AND user_sub = app_user_id())
  WITH CHECK (tenant_id = app_tenant_id() AND user_sub = app_user_id());
CREATE POLICY pt_admin ON push_tokens FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

CREATE TABLE device_keys (
  key_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants,
  user_sub    uuid NOT NULL,
  platform    text NOT NULL CHECK (platform IN ('ios','android')),
  public_key  text NOT NULL,               -- SPKI PEM (P-256 de Secure Enclave/Keystore)
  attestation jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now(),
  revoked_at  timestamptz
);
CREATE INDEX idx_device_keys_user ON device_keys (user_sub) WHERE revoked_at IS NULL;
GRANT SELECT, INSERT, UPDATE ON device_keys TO takab_app;

ALTER TABLE device_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE device_keys FORCE  ROW LEVEL SECURITY;
CREATE POLICY dk_self ON device_keys FOR ALL
  USING      (tenant_id = app_tenant_id() AND user_sub = app_user_id())
  WITH CHECK (tenant_id = app_tenant_id() AND user_sub = app_user_id());
CREATE POLICY dk_admin ON device_keys FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

CREATE TABLE damage_reports (
  report_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants,
  incident_id      uuid NOT NULL REFERENCES incidents,
  site_id          uuid NOT NULL REFERENCES sites,
  zone_id          uuid REFERENCES zones,
  user_sub         uuid NOT NULL,
  categories       jsonb NOT NULL,          -- [{key, severity, note?}]
  people_at_risk   boolean NOT NULL DEFAULT false,
  notes            text,
  evidence_ids     uuid[] NOT NULL DEFAULT '{}',
  intent_key_id    uuid,                    -- firma de intención (verificación e2e: T-2.10)
  intent_signature text,
  ts_device        timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_damage_reports_incident ON damage_reports (incident_id, created_at DESC);
CREATE TRIGGER trg_damage_reports_append_only
  BEFORE UPDATE OR DELETE ON damage_reports
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
GRANT SELECT, INSERT ON damage_reports TO takab_app;

ALTER TABLE damage_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE damage_reports FORCE  ROW LEVEL SECURITY;
CREATE POLICY dr_read ON damage_reports FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id));
CREATE POLICY dr_insert ON damage_reports FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');

CREATE TABLE compliance_labels (
  tenant_id  uuid PRIMARY KEY REFERENCES tenants,
  labels     jsonb NOT NULL DEFAULT '{}',
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid
);
GRANT SELECT, INSERT, UPDATE ON compliance_labels TO takab_app;

ALTER TABLE compliance_labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_labels FORCE  ROW LEVEL SECURITY;
CREATE POLICY cl_read ON compliance_labels FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal() OR app_gov_can_see(tenant_id));
CREATE POLICY cl_admin ON compliance_labels FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

CREATE TABLE site_assets (
  asset_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants,
  site_id      uuid NOT NULL REFERENCES sites,
  zone_id      uuid REFERENCES zones,
  kind         text NOT NULL CHECK (kind IN ('evac_route','assembly_point','manual')),
  title        text NOT NULL,
  description  text,
  s3_key       text,                        -- NULL = asset textual (p.ej. punto de reunión)
  content_type text,
  updated_at   timestamptz NOT NULL DEFAULT now(),
  updated_by   uuid
);
CREATE INDEX idx_site_assets_site ON site_assets (site_id, kind);
GRANT SELECT, INSERT, UPDATE, DELETE ON site_assets TO takab_app;

ALTER TABLE site_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_assets FORCE  ROW LEVEL SECURITY;
CREATE POLICY sa_read ON site_assets FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY sa_write ON site_assets FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY sa_admin ON site_assets FOR ALL
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

-- [T-2.71] Ventanas de mantenimiento: silenciar alarmas de OPERACIÓN, jamás la
-- actuación. El efecto real vive en AWS (una CloudWatch alarm mute rule); esta
-- tabla es el registro de QUIÉN apagó QUÉ vigilancia, CUÁNTO y POR QUÉ.
--
-- Tres decisiones que este DDL defiende, y que no se pueden mover sin romperlo:
--
-- 1. `active` NO es una columna: es un PREDICADO derivado (`now() < starts_at +
--    duration`), calcado de `drills` — "sin worker de cierre". Una ventana no
--    puede quedarse abierta porque un job muriera, porque no hay job. Y AWS
--    aplica su propio vencimiento en paralelo (`Duration` obligatoria, tope
--    P15D): doble candado independiente. Si la DB miente, AWS cierra; si AWS no
--    se enteró, la fila expira y las alarmas nunca estuvieron mudas.
-- 2. `duration_s` tope 4 h en el CHECK, igual que `drills.duration_s BETWEEN 30
--    AND 3600`. Dentro de la ventana la alarma está muda en los TRES estados
--    (OK/ALARM/INSUFFICIENT_DATA): corta por política, no solo por AWS.
-- 3. `reason` OBLIGATORIO y no vacío. Una ventana sin motivo escrito es una
--    alarma apagada sin dueño — el modo de fallo real no es técnico: alguien
--    silencia "para que no moleste" y el edificio deja de contar que se queda
--    ciego en cada despliegue.
--
-- `starts_at` es el minuto en que la mute rule se ACTIVA (`at()` tiene
-- granularidad de minuto). La fila y AWS cuentan desde el MISMO borde, así que
-- el "TERMINA HH:MM UTC" del banner no es una aproximación.
--
-- `tenant_id`/`gateway_id` NULL = ventana de PLATAFORMA (ec2_*): no tiene dueño
-- de cliente y solo la ve/abre `takab_superadmin` (la rama `tenant_id =
-- app_tenant_id()` da NULL para esas filas, así que la RLS ya las esconde —
-- mismo mecanismo que las filas sin tenant de `audit_log`).
CREATE TABLE maintenance_windows (
  window_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid REFERENCES tenants(tenant_id),
  gateway_id   uuid REFERENCES gateways(gateway_id),
  scope        text NOT NULL CHECK (scope IN ('gateway','platform')),
  opened_by    uuid NOT NULL,
  reason       text NOT NULL CHECK (length(btrim(reason)) >= 8),
  duration_s   integer NOT NULL CHECK (duration_s BETWEEN 300 AND 14400),
  opened_at    timestamptz NOT NULL DEFAULT now(),
  starts_at    timestamptz NOT NULL,
  closed_at    timestamptz,
  -- Qué se PIDIÓ silenciar (derivado de las filas visibles, jamás del body) y
  -- qué quedó silenciado DE VERDAD tras releer la regla. Los dos números viven
  -- separados a propósito: "no había alarma que silenciar" es un hecho distinto
  -- de "no se silenció" (misma lección que `drill_sites.commandable`, T-2.48).
  alarm_names  text[] NOT NULL DEFAULT '{}',
  -- QUÉ nombre concreto no quedó mudo. Se GUARDA, no se adivina: al releer la
  -- fila no se vuelve a llamar a AWS, y reconstruir los nombres a partir de la
  -- cifra (`requested - silenced`) devolvería un dato INVENTADO que se lee como
  -- medido. Es la misma familia de mentira que esta tabla existe para no contar.
  missing_names text[] NOT NULL DEFAULT '{}',
  requested    integer NOT NULL DEFAULT 0,
  silenced     integer NOT NULL DEFAULT 0,
  mute_rule    text,
  -- ¿Las tres cifras de arriba se MIDIERON? `false` = el `PutAlarmMuteRule` se
  -- emitió y el acuse no se pudo leer, así que `silenced` es una suposición
  -- deliberadamente pesimista (se asume silencio, el estado peligroso) y
  -- `mute_rule` es lo único con lo que se puede deshacer. Sin esta columna la
  -- fila no puede distinguir "medido" de "supuesto" y la consola pintaría una
  -- suposición como un hecho.
  mute_verified boolean NOT NULL DEFAULT true,
  CONSTRAINT mw_scope_coherente CHECK (
    (scope = 'gateway'  AND tenant_id IS NOT NULL AND gateway_id IS NOT NULL) OR
    (scope = 'platform' AND tenant_id IS     NULL AND gateway_id IS     NULL)
  )
);
CREATE INDEX idx_mw_tenant ON maintenance_windows (tenant_id, starts_at DESC);
-- La consulta caliente es "¿qué ventana tapa a ESTE gabinete ahora?": el banner
-- y la tarjeta de flota la hacen en cada refresco.
CREATE INDEX idx_mw_gateway ON maintenance_windows (gateway_id, starts_at DESC)
  WHERE gateway_id IS NOT NULL;

GRANT SELECT, INSERT, UPDATE ON maintenance_windows TO takab_app;
-- El 0001 concede `... ON ALL TABLES` DESPUÉS de aplicar este archivo, así que
-- conceder de menos NO basta en una base nueva: hace falta REVOKE explícito
-- (misma trampa que reparó la 0028 para `fw_releases`).
REVOKE DELETE ON maintenance_windows FROM takab_app;
-- Los workers de ingesta no tienen nada que hacer aquí: esta superficie es de
-- consola. Y menos aún BORRAR el rastro de una vigilancia apagada.
REVOKE ALL ON maintenance_windows FROM takab_ingest;

ALTER TABLE maintenance_windows ENABLE ROW LEVEL SECURITY;
ALTER TABLE maintenance_windows FORCE  ROW LEVEL SECURITY;
CREATE POLICY mw_read ON maintenance_windows FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal()
         OR app_gov_can_see(tenant_id));
CREATE POLICY mw_write ON maintenance_windows FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY mw_admin ON maintenance_windows FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

-- ---------------------------------------------------------------------------
-- Fase 2.8 (migración 0033 · T-2.79): AVISO DE PRIVACIDAD VERSIONADO +
-- CONSENTIMIENTO APPEND-ONLY.
--
-- La trampa que este diseño evita, escrita para quien venga después: un
-- `privacy_notices(version, body)` con una FK desde los consentimientos cumple
-- "el aviso es versionado" y "se guarda qué versión aceptó cada quien", y falla
-- EN SILENCIO el tercer criterio. Basta con que alguien edite el texto de la
-- versión 3 —una errata, una reescritura, un UPDATE mal hecho— para que todos
-- los consentimientos que apuntaban a esa fila pasen a apuntar a un texto
-- distinto del que se aceptó. La FK sigue íntegra y el registro miente.
--
-- Por eso la identidad de un aviso es el DIGEST de lo que la persona lee, el
-- consentimiento guarda una COPIA de ese digest, y la columna es GENERATED:
-- quien inserta no elige el sello. Mismo candado que
-- `notify/whatsapp_templates/*.json` (T-2.77).
--
-- Y el aviso de PLATAFORMA no vive aquí: vive en `api/src/takab_api/privacy/
-- texts/*.json`, versionado en git. Aquí solo hay avisos de TENANT (un hospital
-- o una dependencia es el responsable de los datos de su propia gente y publica
-- el suyo). El más específico gana. Así el texto legal no acaba duplicado
-- dentro de una migración, y la identidad por contenido hace innecesaria la
-- fila para el caso de plataforma.
-- ---------------------------------------------------------------------------

-- Forma canónica con LONGITUD por campo. Sin los prefijos de longitud,
-- (title='A\nB', body='C') y (title='A', body='B\nC') dan la misma cadena: dos
-- avisos distintos con el mismo sello. `char_length` cuenta puntos de código,
-- igual que `len()` en Python — espejo exacto de
-- `takab_api.privacy.artifacts.notice_digest` (probado sobre 7 entradas con
-- acentos, emoji fuera del BMP y saltos de línea).
CREATE FUNCTION privacy_notice_digest(p_locale text, p_title text, p_body text)
  RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT encode(sha256(convert_to(
    'takab.privacy-notice.v1' || E'\n' ||
    char_length(p_locale) || ':' || p_locale || E'\n' ||
    char_length(p_title)  || ':' || p_title  || E'\n' ||
    char_length(p_body)   || ':' || p_body, 'UTF8')), 'hex')
$$;

CREATE TABLE privacy_notices (
  notice_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants,      -- regla de oro 5
  -- 'privacy_notice' = el aviso; 'whatsapp_alerts' = el opt-in que Meta exige
  -- antes de escribir a un número (T-2.77). Un opt-in es un consentimiento más.
  purpose      text NOT NULL CHECK (purpose IN ('privacy_notice','whatsapp_alerts')),
  locale       text NOT NULL CHECK (locale ~ '^[a-z]{2}-[A-Z]{2}$'),
  -- Etiqueta HUMANA para citar el aviso ("1.2.0", "2026-08 v2"). NO es la
  -- identidad: dos filas con la misma etiqueta y distinto texto son avisos
  -- distintos, y el digest lo dice.
  version      text NOT NULL CHECK (char_length(btrim(version)) BETWEEN 1 AND 40),
  title        text NOT NULL CHECK (char_length(btrim(title)) BETWEEN 8 AND 200),
  -- El mínimo no es cosmética: impide publicar un marcador de posición ("TODO")
  -- como si fuera el aviso de un cliente.
  body         text NOT NULL CHECK (char_length(btrim(body)) >= 40),
  digest       text GENERATED ALWAYS AS (privacy_notice_digest(locale, title, body)) STORED,
  -- `vigente` es un PREDICADO, no una columna (mismo criterio que `drills` y
  -- `maintenance_windows`): el aviso en vigor es el de mayor `effective_at` que
  -- ya pasó. Sin worker de rotación — la pregunta "¿y si el job muere?" se
  -- contesta borrando el job.
  effective_at timestamptz NOT NULL DEFAULT now(),
  -- `clock_timestamp()` y NO `now()`: `now()` devuelve el instante de INICIO de
  -- la transacción, así que dos avisos publicados en la misma transacción
  -- empatarían y "el vigente" dejaría de estar definido.
  published_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  -- Orden TOTAL de publicación. Sin él, dos filas con el mismo `effective_at`
  -- (mismo segundo, o una corrección publicada en la misma transacción) dejan
  -- "¿cuál es el aviso vigente?" sin respuesta única — y un aviso vigente
  -- ambiguo es un consentimiento que no se puede probar contra nada.
  seq          bigint GENERATED ALWAYS AS IDENTITY,
  published_by uuid NOT NULL
);
-- Republicar el MISMO texto con otra etiqueta no es una versión nueva: se
-- rechaza. Y la etiqueta no se puede reutilizar para un texto distinto.
CREATE UNIQUE INDEX uq_privacy_notices_digest
  ON privacy_notices (tenant_id, purpose, locale, digest);
CREATE UNIQUE INDEX uq_privacy_notices_version
  ON privacy_notices (tenant_id, purpose, locale, version);
CREATE INDEX idx_privacy_notices_vigente
  ON privacy_notices (tenant_id, purpose, locale, effective_at DESC);
-- Corregir un aviso publicado NO es editarlo: es publicar otra versión. El
-- trigger convierte esa frase en una garantía.
CREATE TRIGGER trg_privacy_notices_append_only
  BEFORE UPDATE OR DELETE ON privacy_notices
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

GRANT SELECT, INSERT ON privacy_notices TO takab_app;
REVOKE UPDATE, DELETE ON privacy_notices FROM takab_app;
REVOKE ALL ON privacy_notices FROM takab_ingest;

ALTER TABLE privacy_notices ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_notices FORCE  ROW LEVEL SECURITY;
-- Lee CUALQUIERA del tenant: el aviso está para mostrarse, y un ocupante tiene
-- que poder leer el que va a aceptar. Sin rama gov: el aviso de un cliente no
-- es evidencia de protección civil.
CREATE POLICY pn_read ON privacy_notices FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
-- Publicar es acto del DUEÑO del tenant, y siempre sobre su propio tenant: ni
-- soporte ni la plataforma publican el aviso de un cliente en su nombre.
CREATE POLICY pn_publish ON privacy_notices FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id()
              AND app_role() IN ('tenant_admin','takab_superadmin'));

CREATE TABLE privacy_consents (
  consent_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants,    -- regla de oro 5
  purpose        text NOT NULL CHECK (purpose IN ('privacy_notice','whatsapp_alerts')),
  -- El sujeto de un opt-in de WhatsApp es un TELÉFONO, no un usuario (T-2.77):
  -- el motor lo admite sin migración.
  subject_kind   text NOT NULL CHECK (subject_kind IN ('user','msisdn')),
  user_sub       uuid,
  subject_ref    text NOT NULL,
  -- Retirar es una FILA NUEVA, jamás un borrado: el registro tiene que poder
  -- decir que entre el día 1 y el día 2 sí había consentimiento (art. 8
  -- LFPDPPP: la revocación opera hacia adelante, no reescribe el pasado).
  decision       text NOT NULL CHECK (decision IN ('accept','withdraw')),
  notice_source  text NOT NULL CHECK (notice_source IN ('repo','tenant')),
  notice_id      uuid REFERENCES privacy_notices,
  -- LA COLUMNA QUE SOSTIENE LA TAREA: copia sellada del contenido aceptado. No
  -- se deriva por JOIN a propósito — si se derivara, editar el aviso reescribiría
  -- hacia atrás lo que cada quien aceptó, que es exactamente lo prohibido.
  notice_digest  text NOT NULL CHECK (notice_digest ~ '^[0-9a-f]{64}$'),
  notice_version text NOT NULL,
  notice_locale  text NOT NULL,
  -- Evidencia MÍNIMA defendible: por dónde se dio el acto. Distingue "la persona
  -- aceptó en su propia app" de "un administrador lo registró por ella", que es
  -- la diferencia legalmente relevante. Deliberadamente NO se guarda IP ni
  -- user-agent: el `sub` autenticado prueba más y una IP es PII adicional que
  -- habría que justificar (y geolocaliza).
  via            text NOT NULL CHECK (via IN ('mobile','web','console_admin','out_of_band')),
  actor_sub      uuid NOT NULL,   -- quién REGISTRÓ (≠ sujeto en el caso delegado)
  decided_at     timestamptz NOT NULL DEFAULT now(),
  -- [T-2.150 · D-07] El sujeto-teléfono ya NO guarda el número: guarda su ÍNDICE
  -- (HMAC de tenant+msisdn, con la pimienta FUERA de la base). El número vive
  -- sellado en `privacy_subject_secrets`, que SÍ se puede borrar — y ahí está la
  -- decisión entera: ejercer ARCO borra aquella fila y ésta no se toca.
  --
  -- [T-2.164] UNA SOLA FORMA: el índice. El CHECK admitía TAMBIÉN el número en
  -- claro «de manera PERMANENTE, no transitoria», por las filas anteriores a
  -- T-2.150 — y mientras lo admitía, **la ausencia de esas filas no se podía
  -- distinguir de que nadie las hubiera mirado**. Se contaron (2026-08-24): CERO
  -- en local, cero en `takab_test` y cero en la nube dev. Y ningún camino de
  -- código puede crearlas: `privacy/store.py` sella el sujeto antes de insertar
  -- y LANZA si faltan los secretos, en vez de caer a texto en claro.
  --
  -- La LECTURA sigue tolerando la forma vieja (`store._formas()` busca por las
  -- dos): si apareciera una fila así en un entorno que nadie censó, se
  -- encontraría igual. Lo que ya no se puede es ESCRIBIR una nueva.
  CONSTRAINT pc_sujeto_coherente CHECK (
    (subject_kind = 'user'   AND user_sub IS NOT NULL AND subject_ref = user_sub::text) OR
    (subject_kind = 'msisdn' AND user_sub IS     NULL AND subject_ref ~ '^[0-9a-f]{64}$')
  ),
  -- 'repo' = aviso de plataforma (artefacto de git, sin fila); 'tenant' = fila.
  -- Sin este CHECK, un consentimiento podría declarar un origen que no tiene.
  CONSTRAINT pc_origen_coherente CHECK (
    (notice_source = 'repo'   AND notice_id IS     NULL) OR
    (notice_source = 'tenant' AND notice_id IS NOT NULL)
  )
);
CREATE INDEX idx_privacy_consents_sujeto
  ON privacy_consents (tenant_id, purpose, subject_ref, decided_at DESC);
CREATE INDEX idx_privacy_consents_user
  ON privacy_consents (tenant_id, user_sub, decided_at DESC) WHERE user_sub IS NOT NULL;
-- [T-2.150 · D-07] EL NÚMERO, SELLADO Y EN UNA TABLA QUE SÍ SE PUEDE BORRAR.
--
-- Mutable a propósito, y ésa es la idea entera: ejercer ARCO borra una fila de
-- AQUÍ y no toca `privacy_consents`. El consentimiento queda byte a byte —su
-- digest sigue probando— y lo que desaparece es la capacidad de leer a quién.
--
-- Sin trigger append-only y sin exención de poda: es lo contrario de la
-- evidencia, aquí el objetivo es PODER BORRAR.
--
-- La clave que abre `sealed` NO está en esta base (entorno / Secrets Manager),
-- así que una copia de la base sola no revela un solo teléfono.
CREATE TABLE privacy_subject_secrets (
  tenant_id     uuid NOT NULL REFERENCES tenants,
  lookup_ref    text NOT NULL CHECK (lookup_ref ~ '^[0-9a-f]{64}$'),
  sealed        bytea NOT NULL,        -- nonce(12B) || AES-GCM
  created_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, lookup_ref)
);
-- Asimétricos a propósito: `takab_app` crea y DESTRUYE (nunca actualiza — un
-- sello no se edita); el worker solo LEE (escribir un consentimiento jamás es
-- cosa suya, mismo criterio que ya rige sobre `privacy_consents`).
GRANT SELECT, INSERT, DELETE ON privacy_subject_secrets TO takab_app;
GRANT SELECT                  ON privacy_subject_secrets TO takab_ingest;

ALTER TABLE privacy_subject_secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_subject_secrets FORCE  ROW LEVEL SECURITY;
CREATE POLICY privacy_subject_secrets_rw ON privacy_subject_secrets FOR ALL
  USING      (tenant_id = app_tenant_id() OR app_is_takab_internal())
  WITH CHECK (tenant_id = app_tenant_id() OR app_is_takab_internal());

CREATE TRIGGER trg_privacy_consents_append_only
  BEFORE UPDATE OR DELETE ON privacy_consents
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

GRANT SELECT, INSERT ON privacy_consents TO takab_app;
REVOKE UPDATE, DELETE ON privacy_consents FROM takab_app;
-- El worker de notify LEE el opt-in (costura de T-2.77: hoy lo lee del
-- `rule_set`, que no sabe quién ni cuándo). Escribir un consentimiento jamás es
-- cosa de un worker.
GRANT SELECT ON privacy_consents TO takab_ingest;
REVOKE INSERT, UPDATE, DELETE ON privacy_consents FROM takab_ingest;

ALTER TABLE privacy_consents ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_consents FORCE  ROW LEVEL SECURITY;
-- La fila propia: leerla y escribirla es del titular del dato.
CREATE POLICY pc_self ON privacy_consents FOR ALL
  USING      (tenant_id = app_tenant_id() AND user_sub = app_user_id())
  WITH CHECK (tenant_id = app_tenant_id() AND user_sub = app_user_id());
-- El dueño del tenant ve el registro de SU gente (necesidad de cumplimiento) y
-- registra el consentimiento de un tercero que no tiene sesión (un número de
-- WhatsApp de la guardia). Nunca el de otro tenant.
CREATE POLICY pc_admin ON privacy_consents FOR ALL
  USING      (tenant_id = app_tenant_id()
              AND app_role() IN ('tenant_admin','takab_superadmin'))
  WITH CHECK (tenant_id = app_tenant_id()
              AND app_role() IN ('tenant_admin','takab_superadmin'));
-- Interno: SOLO lectura. La plataforma audita el registro, no lo escribe.
CREATE POLICY pc_internal_read ON privacy_consents FOR SELECT
  USING (app_is_takab_internal());

-- ---------------------------------------------------------------------------
-- [T-2.80] ARCO POR ANONIMIZACIÓN CON TOMBSTONE
--
-- El titular tiene derecho a que sus datos personales desaparezcan; el sistema
-- tiene la obligación dura de conservar auditoría, evidencia y dictámenes
-- (regla de oro 11). No es un conflicto: el derecho es sobre la PERSONA y la
-- obligación es sobre el HECHO. Se anonimiza a la persona sin borrar el hecho.
--
-- La bisagra: `life_checkins.user_id` es un `sub` de Cognito, un UUID opaco que
-- solo es dato personal mientras exista el mapeo `sub → nombre` en
-- `user_profiles`. ARCO destruye ese mapeo y deja el UUID en pie. Por eso
-- COUNT(DISTINCT user_id) —"cuántas PERSONAS confirmaron estar bien en el piso
-- 8"— no se mueve: en un sismo ese número decide si sube o no una brigada.
-- ---------------------------------------------------------------------------

-- El sello que hace VERIFICABLE la bitácora, no solo íntegra. Length-prefixing
-- en cada campo (mismo criterio que `privacy_notice_digest`) para que un '|' o
-- un salto de línea dentro de `actor`/`object` no pueda fabricar una colisión.
-- `extract(epoch ...)` y no `ts::text`: el texto de un timestamptz depende de
-- los GUC `TimeZone`/`DateStyle` de la sesión, así que el mismo dato daría
-- digests distintos según quién pregunte — y entonces no verificaría nada.
CREATE FUNCTION privacy_audit_digest(p_tenant uuid, p_watermark bigint)
  RETURNS text LANGUAGE sql STABLE AS $$
  SELECT encode(sha256(convert_to(
    'takab.audit-chain.v1' || E'\n' ||
    coalesce(string_agg(linea, E'\n' ORDER BY audit_id), '(bitacora vacia)'),
    'UTF8')), 'hex')
  FROM (
    SELECT a.audit_id,
           'i' || a.audit_id::text ||
           '|t' || extract(epoch from a.ts)::text ||
           '|n' || char_length(coalesce(a.tenant_id::text, '')) || ':'
                || coalesce(a.tenant_id::text, '') ||
           '|a' || char_length(a.actor)  || ':' || a.actor ||
           '|v' || char_length(a.verb)   || ':' || a.verb ||
           '|o' || char_length(a.object) || ':' || a.object ||
           '|m' || char_length(a.meta::text) || ':' || a.meta::text AS linea
    FROM audit_log a
    WHERE a.tenant_id = p_tenant AND a.audit_id <= p_watermark
  ) s
$$;

-- [T-2.80.b] LA CONSTANCIA. El caso real de ARCO no es el titular pulsando un
-- botón: es una persona que manda su solicitud POR ESCRITO al responsable del
-- tratamiento, que es quien tiene que ejecutarla. Esta tabla es esa solicitud
-- convertida en fila, y es el ÚNICO modo de nombrar a un tercero en todo el
-- sistema.
--
-- POR QUÉ EL ARCO CRUZADO SIGUE SIENDO INEXPRESABLE (no "prohibido")
-- ─────────────────────────────────────────────────────────────────
-- 1. **No hay parámetro de tenant.** `tenant_id` lo pone `app_tenant_id()` por
--    DEFAULT y la RLS lo vuelve a exigir en el WITH CHECK: el cliente no lo
--    manda, ni podría.
-- 2. **El FK COMPUESTO `(tenant_id, user_sub) → user_profiles`.** Una constancia
--    solo puede nombrar a alguien del PROPIO padrón. Intentarlo con un titular
--    ajeno no se rechaza por una comprobación: viola integridad referencial.
-- 3. **`privacy_erase_subject` sigue sin recibir sujeto.** Recibe el
--    `request_id` de una constancia y RESUELVE el sujeto uniendo contra el padrón
--    de `app_tenant_id()`. Un UUID ajeno no tiene por dónde llegar a ser sujeto.
--
-- Y la PRUEBA es una columna, no una promesa: `proof_digest` (SHA-256 del
-- documento recibido) es lo que separa "hay una solicitud" de "es ESTA solicitud
-- y no otra". `proof_ref` dice DÓNDE está el documento —folio, expediente, clave
-- de objeto—, nunca su contenido: el `audit_log` no se poda jamás y una copia
-- del escrito ahí sería PII eterna.
--
-- LO QUE ESTE ACTO NO HACE: **no borra la cuenta en Cognito.** Anonimizar es
-- destruir el mapeo `sub → persona` en ESTA base; la identidad del directorio es
-- otro sistema, con otro efecto (quien pierde la cuenta pierde el acceso a la
-- app de emergencia) y otro camino. Ver `takab_api.privacy.erasure` para el
-- razonamiento completo y las otras dos cosas que quedan fuera.
CREATE TABLE privacy_erasure_requests (
  request_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Sin parámetro: el tenant de una constancia es SIEMPRE el de la sesión.
  tenant_id       uuid NOT NULL DEFAULT app_tenant_id() REFERENCES tenants,
  -- El titular que PIDIÓ. Atado al padrón del tenant por el FK compuesto de abajo.
  -- [T-2.151] NULL cuando el sujeto es un TELÉFONO: quien solo dio su número no
  -- está en el padrón, así que no tiene `sub` que poner aquí. El FK compuesto es
  -- MATCH SIMPLE, o sea que con la columna nula no se comprueba — y no hace falta:
  -- el confinamiento de ese sujeto lo da el índice del sello, derivado con el
  -- `tenant_id` de la sesión.
  user_sub        uuid,
  -- [T-2.151 · D-23] Qué clase de titular nombra esta constancia.
  subject_kind    text NOT NULL DEFAULT 'user_sub'
    CHECK (subject_kind IN ('user_sub','msisdn')),
  right_requested text NOT NULL CHECK (right_requested IN ('cancelacion','oposicion')),
  -- Cómo LLEGÓ la solicitud. No confundir con `privacy_erasures.via`, que es cómo
  -- se EJERCIÓ: son dos actos distintos y separarlos es la mitad del registro.
  channel         text NOT NULL
    CHECK (channel IN ('written','email','in_person','legal_representative')),
  received_at     timestamptz NOT NULL,
  proof_ref       text NOT NULL CHECK (char_length(proof_ref) BETWEEN 3 AND 200),
  proof_digest    text NOT NULL CHECK (proof_digest ~ '^[0-9a-f]{64}$'),
  -- Quién la REGISTRÓ (≠ quién la pidió). Confundirlos borraría la diferencia
  -- entre "la persona lo solicitó" y "un administrador lo dio por hecho".
  created_by      uuid NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT fk_per_padron_del_tenant FOREIGN KEY (tenant_id, user_sub)
    REFERENCES user_profiles (tenant_id, user_sub),
  -- Una constancia es la solicitud de OTRO. El titular que quiere ejercer su
  -- propio ARCO tiene el autoservicio; dejarle fabricarse una constancia
  -- convertiría el registro del responsable en un trámite que se firma solo.
  CONSTRAINT per_no_es_autoservicio CHECK (created_by <> user_sub),
  -- [T-2.151] El sujeto y su clase cuentan la misma historia. Sin esto una
  -- constancia podría declararse 'msisdn' y llevar un `user_sub` —o al revés— y
  -- la fila mentiría sobre a quién nombra.
  CONSTRAINT per_sujeto_coherente CHECK ((subject_kind = 'user_sub') = (user_sub IS NOT NULL))
);
CREATE INDEX idx_privacy_erasure_requests_sujeto
  ON privacy_erasure_requests (tenant_id, user_sub);
CREATE TRIGGER trg_privacy_erasure_requests_append_only
  BEFORE UPDATE OR DELETE ON privacy_erasure_requests
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

GRANT SELECT, INSERT ON privacy_erasure_requests TO takab_app;
REVOKE UPDATE, DELETE ON privacy_erasure_requests FROM takab_app;
REVOKE ALL ON privacy_erasure_requests FROM takab_ingest;

ALTER TABLE privacy_erasure_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_erasure_requests FORCE  ROW LEVEL SECURITY;
-- Registrar y leer constancias es acto del RESPONSABLE del tratamiento. Los roles
-- salen del mismo círculo que `pe_admin_read` (el dueño del cliente); la acción
-- de matriz `manage_privacy_erasure` solo hace que el 403 llegue limpio.
CREATE POLICY per_admin ON privacy_erasure_requests FOR ALL
  USING      (tenant_id = app_tenant_id()
              AND app_role() IN ('tenant_admin','takab_superadmin'))
  WITH CHECK (tenant_id = app_tenant_id()
              AND app_role() IN ('tenant_admin','takab_superadmin'));
CREATE POLICY per_internal_read ON privacy_erasure_requests FOR SELECT
  USING (app_is_takab_internal());

-- [T-2.80.b] "Este portador tiene constancia para este titular." Es el criterio 2
-- de la ficha —"ejercerlo por cuenta de otro EXIGE constancia"— convertido en un
-- privilegio de base de datos: sin fila de solicitud, las políticas de abajo no
-- dejan tocar un solo dato de esa persona. SECURITY INVOKER (el default): el
-- EXISTS corre bajo la RLS de quien pregunta, así que la constancia de otro
-- cliente no existe para él.
CREATE FUNCTION app_can_erase_subject(p_tenant uuid, p_subject uuid) RETURNS boolean
  LANGUAGE sql STABLE AS $$
  SELECT p_tenant = app_tenant_id()
     AND app_role() IN ('tenant_admin','takab_superadmin')
     AND EXISTS (
           SELECT 1 FROM privacy_erasure_requests r
            WHERE r.tenant_id = p_tenant AND r.user_sub = p_subject)
$$;

-- LA LÁPIDA. Deja constancia del acto SIN conservar el dato: qué derecho, cuándo,
-- por qué vía y CUÁNTAS filas se anonimizaron por tabla. Ni una copia del nombre,
-- del teléfono ni del token — guardar eso "para trazabilidad" convertiría la
-- anonimización en una seudonimización reversible, que es lo que no puede ser.
CREATE TABLE privacy_erasures (
  erasure_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL REFERENCES tenants,      -- regla de oro 5
  -- El sujeto NUNCA llega crudo del cliente: es `app_user_id()` (autoservicio) o
  -- se RESUELVE dentro de `privacy_erase_subject` contra el padrón del tenant de
  -- la sesión (constancia, T-2.80.b). El `sub` se conserva porque es la clave de
  -- idempotencia y, destruido el mapeo, no remonta a nadie.
  -- [T-2.151] NULL para un sujeto-TELÉFONO, que no tiene `sub` ninguno. Ahí la
  -- idempotencia no puede apoyarse en el sujeto —es justo lo que nos negamos a
  -- registrar—: la da `uq_privacy_erasures_constancia`, una constancia una lápida.
  user_sub        uuid,
  -- [T-2.151 · D-23] Qué clase de titular se olvidó.
  subject_kind    text NOT NULL DEFAULT 'user_sub'
    CHECK (subject_kind IN ('user_sub','msisdn')),
  right_exercised text NOT NULL CHECK (right_exercised IN ('cancelacion','oposicion')),
  -- Quién EJERCIÓ el acto ante el sistema: el titular (autoservicio) o el
  -- responsable que ejecuta una constancia. Quién lo PIDIÓ materialmente está en
  -- `privacy_erasure_requests.user_sub`, atado por `request_id`; en autoservicio
  -- los dos coinciden por construcción.
  requested_by    uuid NOT NULL,
  -- [T-2.80.b] La constancia que autoriza el acto, o NULL en autoservicio.
  request_id      uuid REFERENCES privacy_erasure_requests,
  via             text NOT NULL CHECK (via IN ('mobile','web','console_admin','out_of_band')),
  -- Conteos por tabla, p.ej. {"life_checkins": 3}. El CHECK de abajo impide
  -- FÍSICAMENTE meter aquí un string: sin él, este jsonb sería el sitio obvio
  -- donde alguien "guardaría el nombre por si acaso" y desharía la tarea entera.
  affected        jsonb NOT NULL DEFAULT '{}',
  -- El par que hace VERIFICABLE la bitácora: último `audit_id` del tenant en el
  -- instante del borrado, y el hash de todo lo anterior. Cualquiera puede
  -- recalcular `privacy_audit_digest(tenant_id, audit_watermark)` años después y
  -- comparar. "Íntegro" pasa a ser algo que se mide, no que se afirma.
  audit_watermark bigint NOT NULL,
  audit_digest    text NOT NULL CHECK (audit_digest ~ '^[0-9a-f]{64}$'),
  erased_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pe_afectados_son_conteos CHECK (
    NOT jsonb_path_exists(affected, '$.* ? (@.type() <> "number")')
  ),
  -- [T-2.80.b] La vía y la autoría tienen que contar la MISMA historia: una
  -- lápida "por cuenta de otro" sin constancia, o una de autoservicio marcada
  -- `console_admin`, serían un registro que miente sobre quién ejerció el
  -- derecho. Es la mitad no-negociable del criterio 2 de la ficha.
  CONSTRAINT pe_la_via_cuadra_con_la_constancia CHECK (
    (request_id IS NULL) = (via IN ('mobile','web'))
  ),
  -- Idempotencia (regla de oro 3): un titular se anonimiza UNA vez. Ejercer ARCO
  -- dos veces devuelve la MISMA lápida, testigo sellado del primer acto.
  CONSTRAINT uq_privacy_erasures_sujeto UNIQUE (tenant_id, user_sub),
  CONSTRAINT pe_sujeto_coherente CHECK ((subject_kind = 'user_sub') = (user_sub IS NOT NULL)),
  -- [T-2.151] No hay autoservicio para un sujeto-teléfono, y no es una omisión: el
  -- autoservicio se apoya en `app_user_id()`, y quien solo dio su número no tiene
  -- sesión con la que probar que es suyo. Su única vía es la constancia del
  -- responsable (D-23), así que una lápida de teléfono SIN constancia sería una
  -- que nadie autorizó.
  CONSTRAINT pe_telefono_exige_constancia CHECK (
    subject_kind <> 'msisdn' OR request_id IS NOT NULL)
);
-- [T-2.151] Una constancia, una lápida. Es la unidad de idempotencia del sujeto
-- que no se puede nombrar: dos escritos sobre el mismo número son dos actos, que
-- es lo que de verdad ocurrió.
CREATE UNIQUE INDEX uq_privacy_erasures_constancia
  ON privacy_erasures (tenant_id, request_id) WHERE subject_kind = 'msisdn';
CREATE INDEX idx_privacy_erasures_tenant ON privacy_erasures (tenant_id, erased_at DESC);
CREATE TRIGGER trg_privacy_erasures_append_only
  BEFORE UPDATE OR DELETE ON privacy_erasures
  FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

GRANT SELECT, INSERT ON privacy_erasures TO takab_app;
REVOKE UPDATE, DELETE ON privacy_erasures FROM takab_app;
REVOKE ALL ON privacy_erasures FROM takab_ingest;

ALTER TABLE privacy_erasures ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_erasures FORCE  ROW LEVEL SECURITY;
-- Ejercer ARCO y consultar la propia lápida es acto del TITULAR, igual que dar o
-- retirar el consentimiento: un derecho, no un permiso que se concede.
CREATE POLICY pe_self ON privacy_erasures FOR ALL
  USING      (tenant_id = app_tenant_id() AND user_sub = app_user_id())
  WITH CHECK (tenant_id = app_tenant_id() AND user_sub = app_user_id());
-- El responsable del tenant LEE su registro de borrados (necesidad de
-- cumplimiento).
CREATE POLICY pe_admin_read ON privacy_erasures FOR SELECT
  USING (tenant_id = app_tenant_id()
         AND app_role() IN ('tenant_admin','takab_superadmin'));
CREATE POLICY pe_internal_read ON privacy_erasures FOR SELECT
  USING (app_is_takab_internal());
-- [T-2.80.b] Y ESCRIBE una lápida por cuenta de otro SOLO con constancia. El
-- `request_id IS NOT NULL` no es decorativo: sin él, el responsable podría
-- fabricar una lápida sin solicitud registrada y el criterio 2 dependería del
-- router. Aquí depende de la base.
CREATE POLICY pe_on_behalf ON privacy_erasures FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id()
              AND request_id IS NOT NULL
              AND app_can_erase_subject(tenant_id, user_sub));
-- [T-2.151 · D-23] El gemelo para el sujeto que no está en el padrón. No puede
-- reutilizar `app_can_erase_subject`, que busca la constancia POR `user_sub`: con
-- un sujeto nulo esa comparación no encuentra nada. La exige por `request_id`, y
-- exige además que se haya registrado COMO constancia de teléfono — si no, el
-- responsable reutilizaría cualquier expediente suyo para justificar cualquier
-- borrado.
CREATE POLICY pe_phone_on_behalf ON privacy_erasures FOR INSERT
  WITH CHECK (tenant_id = app_tenant_id()
              AND subject_kind = 'msisdn'
              AND user_sub IS NULL
              AND request_id IS NOT NULL
              AND app_role() IN ('tenant_admin','takab_superadmin')
              AND EXISTS (
                    SELECT 1 FROM privacy_erasure_requests r
                     WHERE r.request_id = privacy_erasures.request_id
                       AND r.tenant_id  = privacy_erasures.tenant_id
                       AND r.subject_kind = 'msisdn'));

-- EL ACTO. **Sigue sin recibir un sujeto.** En autoservicio opera sobre
-- `app_user_id()` (T-2.80, intacto); por cuenta de otro recibe el `request_id` de
-- una CONSTANCIA y resuelve el sujeto uniendo contra el padrón de
-- `app_tenant_id()`. Nombrar a un titular ajeno —o cruzar tenants— no está
-- *prohibido*: no hay parámetro por donde formularlo. Todo ocurre en una
-- sentencia: una anonimización a medias no es un estado alcanzable. SECURITY
-- INVOKER (el default): corre bajo la RLS del request, no la esquiva.
CREATE FUNCTION privacy_erase_subject(p_right text, p_via text, p_request uuid)
  RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  v_tenant  uuid := app_tenant_id();
  v_actor   uuid := app_user_id();
  v_user    uuid;
  v_right   text := p_right;
  v_af      jsonb := '{}'::jsonb;
  v_n       integer;
  v_wm      bigint;
  v_row     privacy_erasures%ROWTYPE;
  v_created boolean := true;
BEGIN
  IF v_tenant IS NULL OR v_actor IS NULL THEN
    RAISE EXCEPTION
      'ARCO exige una sesion con portador identificado: el sujeto del borrado '
      'sale de app_user_id() o de una constancia, nunca de un parametro'
      USING ERRCODE = 'TK403';
  END IF;

  IF p_request IS NULL THEN
    -- AUTOSERVICIO. El sujeto ES la sesión: exactamente lo que hacía la T-2.80.
    v_user := v_actor;
  ELSE
    -- POR CUENTA DE OTRO. El sujeto no se acepta: se RESUELVE. El JOIN contra
    -- `user_profiles` por `app_tenant_id()` es lo que lo PRODUCE, así que el
    -- único universo del que puede salir un sujeto es el padrón del tenant de la
    -- sesión. Y la constancia se busca SIN filtro de tenant a propósito: la RLS
    -- ya hace que la de otro cliente no exista para esta sesión. Añadir aquí un
    -- `AND r.tenant_id = v_tenant` sugeriría que el confinamiento es una
    -- comprobación; no lo es, es el único universo que la sesión tiene.
    SELECT u.user_sub, r.right_requested INTO v_user, v_right
      FROM privacy_erasure_requests r
      JOIN user_profiles u
        ON u.tenant_id = app_tenant_id() AND u.user_sub = r.user_sub
     WHERE r.request_id = p_request;
    IF v_user IS NULL THEN
      RAISE EXCEPTION
        'no hay constancia de esa solicitud en este cliente: ejercer ARCO por '
        'cuenta de otro exige registrar antes la solicitud recibida'
        USING ERRCODE = 'TK404';
    END IF;
  END IF;

  -- DECISIÓN: con un incidente ABIERTO en un sitio del titular, se DIFIERE. La
  -- ubicación de un check-in es dato de rescate EN VIVO y anularla a mitad de
  -- una búsqueda es un fallo de seguridad — la clase de fallo que las reglas de
  -- oro 1 y 2 existen para impedir. El derecho no se niega: se aplaza hasta el
  -- cierre (horas), y la petición queda auditada para que el plazo legal corra.
  IF EXISTS (
    SELECT 1 FROM incidents i
     WHERE i.tenant_id = v_tenant
       AND i.state <> 'closed' AND i.closed_at IS NULL
       AND (i.site_id IN (SELECT c.site_id FROM life_checkins c
                           WHERE c.tenant_id = v_tenant AND c.user_id = v_user)
         OR i.site_id IN (SELECT z.site_id FROM user_zone_assignments z
                           WHERE z.tenant_id = v_tenant AND z.user_id = v_user))
  ) THEN
    RAISE EXCEPTION
      'hay un incidente ABIERTO en un sitio del titular: la anonimizacion se '
      'difiere hasta que cierre, porque la ubicacion de un check-in es dato '
      'de rescate en vivo'
      USING ERRCODE = 'TK409';
  END IF;

  -- El mapeo `sub → persona`. Destruirlo es lo que anonimiza todo lo demás.
  UPDATE user_profiles
     SET display_name = '(titular anonimizado)', phone = NULL, updated_at = now()
   WHERE tenant_id = v_tenant AND user_sub = v_user
     AND (display_name IS DISTINCT FROM '(titular anonimizado)' OR phone IS NOT NULL);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_af := v_af || jsonb_build_object('user_profiles', v_n);

  -- La FILA se queda (hubo un dispositivo registrado: es un hecho); muere el
  -- identificador que enruta a la persona.
  UPDATE push_tokens
     SET token = 'arco:' || push_token_id::text,
         endpoint_arn = NULL,
         revoked_at = coalesce(revoked_at, now())
   WHERE tenant_id = v_tenant AND user_sub = v_user
     AND token IS DISTINCT FROM 'arco:' || push_token_id::text;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_af := v_af || jsonb_build_object('push_tokens', v_n);

  -- Se REVOCA, no se destruye: `public_key` verifica la firma de intención de
  -- `damage_reports` (evidencia). Borrarla dejaría esa evidencia sin poder
  -- verificarse, que es podar su integridad por la puerta de atrás.
  UPDATE device_keys SET revoked_at = now()
   WHERE tenant_id = v_tenant AND user_sub = v_user AND revoked_at IS NULL;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_af := v_af || jsonb_build_object('device_keys', v_n);

  -- La ubicación GPS exacta de una persona. La FILA no se toca: por eso el
  -- check-in anonimizado sigue contando para el histórico del incidente.
  UPDATE life_checkins SET geom = NULL
   WHERE tenant_id = v_tenant AND user_id = v_user AND geom IS NOT NULL;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  v_af := v_af || jsonb_build_object('life_checkins', v_n);

  SELECT coalesce(max(audit_id), 0) INTO v_wm FROM audit_log WHERE tenant_id = v_tenant;

  INSERT INTO privacy_erasures
    (tenant_id, user_sub, right_exercised, requested_by, request_id, via,
     affected, audit_watermark, audit_digest)
  VALUES
    (v_tenant, v_user, v_right, v_actor, p_request, p_via,
     v_af, v_wm, privacy_audit_digest(v_tenant, v_wm))
  ON CONFLICT (tenant_id, user_sub) DO NOTHING
  RETURNING * INTO v_row;

  -- Repetir el acto re-barre (por si hubo un alta posterior) pero NO escribe una
  -- segunda lápida: la primera es el testigo sellado y no se reescribe.
  IF v_row.erasure_id IS NULL THEN
    v_created := false;
    SELECT * INTO v_row FROM privacy_erasures
     WHERE tenant_id = v_tenant AND user_sub = v_user;
  END IF;

  RETURN to_jsonb(v_row) || jsonb_build_object('created', v_created);
END $$;

-- [T-2.151 · D-23] EL ACTO DEL SUJETO-TELÉFONO. Registrar y ejecutar, en UNA
-- sentencia: un borrado a medias —constancia sin lápida, o lápida sin el sello
-- destruido— no es un estado alcanzable.
--
-- **No recibe el número ni su índice.** El sello lo destruye el llamador antes,
-- porque hace falta la pimienta del despliegue y ésa no está en esta base; aquí
-- solo se registra el acto. Si esta inserción falla, la transacción entera se
-- deshace y el sello vuelve: por eso el orden es destruir-y-luego-registrar.
--
-- `affected` es CONSTANTE a propósito. En el ARCO del padrón son conteos útiles;
-- aquí un {"privacy_subject_secrets": 1} frente a un 0 sería un ORÁCULO DE
-- EXISTENCIA: con una credencial de responsable se barre un rango de números y se
-- descubre cuáles constan y, con ellos, en qué edificio está quien los lleva.
CREATE FUNCTION privacy_erase_phone_subject(
  p_right text, p_channel text, p_received_at timestamptz,
  p_proof_ref text, p_proof_digest text, p_via text)
  RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
  v_tenant  uuid := app_tenant_id();
  v_actor   uuid := app_user_id();
  v_request uuid;
  v_wm      bigint;
  v_row     privacy_erasures%ROWTYPE;
BEGIN
  IF v_tenant IS NULL OR v_actor IS NULL THEN
    RAISE EXCEPTION
      'ARCO exige una sesion con portador identificado: quien ejecuta el borrado '
      'de un sujeto-telefono es el responsable del tratamiento, nunca un anonimo'
      USING ERRCODE = 'TK403';
  END IF;

  INSERT INTO privacy_erasure_requests
    (user_sub, subject_kind, right_requested, channel, received_at,
     proof_ref, proof_digest, created_by)
  VALUES
    (NULL, 'msisdn', p_right, p_channel, p_received_at,
     p_proof_ref, p_proof_digest, v_actor)
  RETURNING request_id INTO v_request;

  SELECT coalesce(max(audit_id), 0) INTO v_wm FROM audit_log WHERE tenant_id = v_tenant;

  INSERT INTO privacy_erasures
    (tenant_id, user_sub, subject_kind, right_exercised, requested_by, request_id,
     via, affected, audit_watermark, audit_digest)
  VALUES
    (v_tenant, NULL, 'msisdn', p_right, v_actor, v_request,
     p_via, '{}'::jsonb, v_wm, privacy_audit_digest(v_tenant, v_wm))
  RETURNING * INTO v_row;

  RETURN to_jsonb(v_row);
END $$;

GRANT EXECUTE ON FUNCTION privacy_erase_phone_subject(
  text, text, timestamptz, text, text, text) TO takab_app;

REVOKE ALL ON FUNCTION privacy_erase_subject(text,text,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION privacy_audit_digest(uuid,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION privacy_erase_subject(text,text,uuid) TO takab_app;
GRANT EXECUTE ON FUNCTION privacy_audit_digest(uuid,bigint) TO takab_app;
-- `app_can_erase_subject` NO se revoca de PUBLIC, y es a propósito: se evalúa
-- DENTRO de políticas RLS, y una política que llama a una función sin EXECUTE
-- hace fallar la sentencia entera del rol que la toque (incluido el worker de
-- notificaciones sobre `push_tokens`). No filtra nada: el EXISTS de dentro corre
-- bajo la RLS del que pregunta, igual que `app_role()` y compañía.

-- [T-2.80] Regla de oro 11 hecha PRIVILEGIO, no comentario. Un comentario no
-- impide un DELETE; un privilegio ausente sí. Va al final del fichero a
-- propósito: los GRANT de arriba (y el `GRANT ... ON ALL TABLES` que el 0001
-- ejecuta DESPUÉS de aplicar este schema) tienen que haber pasado ya.
REVOKE DELETE ON
  audit_log, incident_actions, dictamens, evidence_objects, damage_reports,
  life_checkins, privacy_notices, privacy_consents, user_profiles,
  push_tokens, device_keys
FROM takab_app;
-- Y el UPDATE de `life_checkins` queda SOLO a nivel de columna (`geom`).
REVOKE UPDATE ON life_checkins FROM takab_app;
GRANT UPDATE (geom) ON life_checkins TO takab_app;

-- [T-2.81.c] La lista de arriba enumeró doce tablas y se dejó fuera la única
-- otra que lleva guard `BEFORE DELETE` append-only desde el 0001:
-- `rule_evaluations`. No era explotable —su RLS solo tiene política de lectura,
-- así que el DELETE de takab_app volvía con cero filas y sin error— pero la
-- protección descansaba en la ausencia de una política, no en el guard, y una
-- política `FOR ALL` añadida mañana la habría quitado en silencio. Va en línea
-- aparte y no dentro de la lista de la T-2.80 para que se lea POR QUÉ llegó
-- tarde: la enumeró una mano, la encontró una derivación del catálogo.
REVOKE DELETE ON rule_evaluations FROM takab_app;

-- [T-2.80.b] Y la constancia de la solicitud, por el mismo criterio: es la prueba
-- de que un titular pidió, y sin ella la lápida del responsable sería su palabra.
-- Regla de oro 11: se registra, no se edita ni se poda.
REVOKE DELETE ON privacy_erasure_requests FROM takab_app;

-- Las políticas de UPDATE de `life_checkins`. Junto al GRANT por columna y al
-- trigger, la superficie TOTAL del UPDATE sobre esta tabla es "anular la
-- geometría", y nada más: quien lo limita es `life_checkin_arco_guard()`, que
-- compara la fila entera con `to_jsonb` y cubre también al dueño de la tabla.
-- Estas políticas solo deciden QUIÉN puede pedir esa única mutación.
-- Viven aquí y no junto a `lc_read`/`lc_insert` porque necesitan `app_user_id()`
-- / `app_is_takab_internal()`.
--
-- [T-2.80] A petición del TITULAR, y solo sobre sus propias filas.
CREATE POLICY lc_arco_geom ON life_checkins FOR UPDATE
  USING      (tenant_id = app_tenant_id() AND user_id = app_user_id())
  WITH CHECK (tenant_id = app_tenant_id() AND user_id = app_user_id());
-- [T-2.81] Por RELOJ: el job de retención (`ops/prune_pii`) anula la geometría
-- de los check-ins caducados. Un job no actúa en nombre de ninguna persona, así
-- que no puede usar la política de arriba. El confinamiento por tenant va DENTRO
-- de la política, no en el WHERE del job: lo impone la base (regla de oro 5).
CREATE POLICY lc_retention_geom ON life_checkins FOR UPDATE
  USING      (tenant_id = app_tenant_id() AND app_is_takab_internal())
  WITH CHECK (tenant_id = app_tenant_id() AND app_is_takab_internal());

-- ---------------------------------------------------------------------------
-- [T-2.80.b] EL RESPONSABLE EJECUTA UNA CONSTANCIA
--
-- El responsable del tratamiento no hereda "editar al ocupante". Cada política de
-- abajo abre exactamente UNA fila-destino: la ANONIMIZADA. El `USING` dice a quién
-- se puede tocar (solo a alguien con constancia registrada) y el `WITH CHECK` dice
-- en qué estado puede quedar la fila — que es el mismo que escribe
-- `privacy_erase_subject`, y ningún otro. Un `UPDATE ... SET display_name = 'Otro'`
-- con constancia en mano sigue siendo un error de RLS.
--
-- Sin constancia, `app_can_erase_subject` es falso y estas políticas no existen:
-- "exige constancia" deja de ser una condición del router y pasa a ser una
-- condición de la base.
-- ---------------------------------------------------------------------------
CREATE POLICY up_arco_on_behalf ON user_profiles FOR UPDATE
  USING      (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub))
  WITH CHECK (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub)
              AND display_name = '(titular anonimizado)' AND phone IS NULL);
CREATE POLICY pt_arco_on_behalf ON push_tokens FOR UPDATE
  USING      (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub))
  WITH CHECK (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub)
              AND token = 'arco:' || push_token_id::text
              AND endpoint_arn IS NULL AND revoked_at IS NOT NULL);
CREATE POLICY dk_arco_on_behalf ON device_keys FOR UPDATE
  USING      (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub))
  WITH CHECK (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_sub)
              AND revoked_at IS NOT NULL);
CREATE POLICY lc_arco_on_behalf ON life_checkins FOR UPDATE
  USING      (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_id))
  WITH CHECK (tenant_id = app_tenant_id() AND app_can_erase_subject(tenant_id, user_id)
              AND geom IS NULL);

-- ---------------------------------------------------------------------------
-- [T-2.78.a · 0041] LA CADENA DE OPERACIÓN (CloudWatch → SNS → on-call)
--
-- Es OTRA cadena. No comparte código, destinatario ni permiso con
-- `notification_jobs` / `notify/orchestrator.py`, y acreditar una no dice nada
-- de la otra — el hueco de `ses:SendEmail` de julio-2026 estuvo tapado
-- exactamente por confundirlas.
--
-- El hueco que cierra: la cadena de operación no dejaba UNA sola fila en TAKAB,
-- y AWS tampoco la da (el registro de estado de entrega de SNS soporta Firehose,
-- SQS, Lambda, HTTPS y endpoints de aplicación; `email` y `email-json` NO están
-- en esa lista). "Publicado" era todo lo que se podía afirmar.
--
-- TABLA PROPIA y no el camino de `incidents_ack`, por tres razones:
--   · una alarma de plataforma NO tiene tenant, y `incidents_ack` cuelga de
--     `incidents`, que sí — habría que inventarle un dueño, y peor: un cliente
--     podría VER que el on-call de TAKAB no contestó a las 3 de la mañana;
--   · son dos cadenas y un `kind` más en `incident_actions` las habría vuelto a
--     mezclar en la misma consulta y en el mismo informe;
--   · `incident_actions` es evidencia de compliance exenta de poda: engordarla
--     con ruido de operación degrada lo que existe para sostener.
--
-- SIN `tenant_id`, con exención declarada en `api/tests/test_censo_multitenancy.py`.
-- ---------------------------------------------------------------------------

-- Quién puede acusar. Un acuse que exija consola + MFA a las 3 de la mañana es
-- un acuse que no se va a dar (y la métrica mediría fricción, no atención); un
-- enlace que cualquiera pueda pulsar no acredita nada. La credencial es personal:
-- 256 bits acuñados una vez, de los que aquí vive SOLO el hash, con caducidad y
-- revocación por fila.
--
-- NADIE tiene SELECT, ni `takab_app`: los hashes no son alcanzables desde
-- ninguna sesión de la API. La única puerta es `app_ops_alert_ack`.
CREATE TABLE ops_oncall_contacts (
  contact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  label      text NOT NULL,
  token_hash text NOT NULL UNIQUE,       -- sha256 hex del secreto; el secreto NO se guarda
  issued_at  timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz
);
GRANT SELECT, INSERT, UPDATE ON ops_oncall_contacts TO takab_ingest;
-- OJO: la 0001 ejecuta este cuerpo y DESPUÉS hace `GRANT ... ON ALL TABLES ... TO
-- takab_app`, así que un REVOKE escrito aquí se desharía solo. El que de verdad
-- deja a `takab_app` sin SELECT sobre esta tabla vive en la 0041, que corre
-- después — con su medición al lado. Aquí queda dicho para que nadie lo "arregle"
-- en este fichero y crea que ha cerrado algo.
ALTER TABLE ops_oncall_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops_oncall_contacts FORCE  ROW LEVEL SECURITY;
-- La negativa va ESCRITA, y no como ausencia de políticas. Las dos cosas son
-- default-deny, pero "cero políticas" es indistinguible de "el restore se comió
-- las políticas" — que es lo que `ops/restore_check.py::rls_policies` denuncia
-- como daño. Declarada, dice que es a propósito y sigue delatando a la que se
-- cayó sola. `takab_ingest` (BYPASSRLS) es quien la lee por la función.
CREATE POLICY ops_oncall_contacts_deny ON ops_oncall_contacts FOR ALL
  USING (false) WITH CHECK (false);

-- El aviso. **La fila NACE SIN ACUSE**, y ése es el diseño: nadie va a llamar a
-- un endpoint para decir "no contesté", así que el silencio no necesita quien lo
-- escriba — lo escribe la máquina que recibió el aviso, en el instante del
-- aviso, con su plazo ya puesto. El acuse solo puede MODIFICAR una fila que ya
-- existe, y `unacked_at` solo FECHA un silencio que ya estaba ahí.
CREATE TABLE ops_alert_notices (
  notice_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Idempotencia frente a los REINTENTOS de SNS: dos entregas del mismo mensaje
  -- son UN aviso, o la métrica de "cuántas veces nadie contestó" se infla sola.
  sns_message_id   text NOT NULL UNIQUE,
  topic_arn        text NOT NULL,
  alarm_name       text,
  alarm_state      text,
  subject          text,
  state_reason     text,
  published_at     timestamptz,          -- el `Timestamp` del sobre de SNS
  received_at      timestamptz NOT NULL DEFAULT now(),  -- t2 de MÁQUINA
  requires_ack     boolean     NOT NULL DEFAULT false,
  ack_deadline_at  timestamptz,
  acked_at         timestamptz,
  acked_by         text,
  acked_contact_id uuid REFERENCES ops_oncall_contacts(contact_id),
  unacked_at       timestamptz,          -- cuándo el silencio pasó a fallo declarado
  -- EL CANDADO DEL CRITERIO 5, en la base y no en el código: no se puede nombrar
  -- a quien acusó sin la hora, ni poner la hora sin nombre. Un UPDATE a mano lo
  -- intenta y la base lo rechaza.
  CONSTRAINT ops_alert_notices_acuse_completo
    CHECK ((acked_at IS NULL) = (acked_by IS NULL)),
  CONSTRAINT ops_alert_notices_plazo_si_pide_acuse
    CHECK (NOT requires_ack OR ack_deadline_at IS NOT NULL)
);
CREATE INDEX idx_ops_alert_notices_abiertos
  ON ops_alert_notices (ack_deadline_at)
  WHERE requires_ack AND acked_at IS NULL AND unacked_at IS NULL;
CREATE INDEX idx_ops_alert_notices_recibidos ON ops_alert_notices (received_at DESC);
GRANT SELECT ON ops_alert_notices TO takab_app;
GRANT SELECT, INSERT, UPDATE ON ops_alert_notices TO takab_ingest;

ALTER TABLE ops_alert_notices ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops_alert_notices FORCE  ROW LEVEL SECURITY;
CREATE POLICY ops_alert_notices_read ON ops_alert_notices FOR SELECT
  USING (app_is_takab_internal());   -- la cadena de operación es de TAKAB

-- La consulta. `security_invoker` (PG15+) para que la RLS que se aplique sea la
-- del rol que consulta y no la del dueño de la vista: una vista sobre una tabla
-- con RLS es, si no, la forma más limpia de saltarse esa RLS sin querer.
CREATE VIEW v_ops_alert_chain WITH (security_invoker = true) AS
SELECT
  n.notice_id, n.sns_message_id, n.topic_arn, n.alarm_name, n.alarm_state,
  n.subject, n.state_reason, n.published_at, n.received_at, n.requires_ack,
  n.ack_deadline_at, n.acked_at, n.acked_by, n.unacked_at,
  -- El desenlace se CALCULA de los instantes; no hay columna de estado que
  -- alguien pueda poner en verde. 'acusado' es imposible sin `acked_at`.
  CASE
    WHEN NOT n.requires_ack                       THEN 'no_requiere_acuse'
    WHEN n.acked_at IS NOT NULL
     AND n.ack_deadline_at IS NOT NULL
     AND n.acked_at > n.ack_deadline_at           THEN 'acusado_tarde'
    WHEN n.acked_at IS NOT NULL                   THEN 'acusado'
    WHEN n.ack_deadline_at IS NOT NULL
     AND now() > n.ack_deadline_at                THEN 'sin_acuse'
    ELSE                                               'esperando_acuse'
  END AS outcome,
  -- El tiempo hasta el acuse, entre dos instantes que escribió la propia base.
  -- Ya no se reconstruye de las cabeceras de un correo.
  CASE WHEN n.acked_at IS NOT NULL
       THEN extract(epoch FROM (n.acked_at - n.received_at)) END AS ack_latency_s,
  CASE WHEN n.acked_at IS NOT NULL AND n.published_at IS NOT NULL
       THEN extract(epoch FROM (n.acked_at - n.published_at)) END AS ack_latency_publicado_s
FROM ops_alert_notices n;
GRANT SELECT ON v_ops_alert_chain TO takab_app;

-- Las dos escrituras vienen de una superficie PÚBLICA (el suscriptor HTTPS del
-- topic y el acuse humano): sin sesión no hay `app.tenant_id` ni `app.role`, y
-- la RLS de arriba es default-deny con FORCE. Mismo patrón que
-- `app_notify_delivery` / `gov_ack_incident`: SECURITY DEFINER con dueño
-- `takab_ingest` (BYPASSRLS), REVOKE FROM PUBLIC + GRANT solo a `takab_app`.
CREATE FUNCTION app_ops_alert_record(
  p_sns_message_id text, p_topic_arn text, p_alarm_name text, p_alarm_state text,
  p_subject text, p_state_reason text, p_published_at timestamptz,
  p_requires_ack boolean, p_ack_deadline_s double precision
) RETURNS TABLE (
  o_notice_id uuid, o_created boolean, o_requires_ack boolean, o_ack_deadline_at timestamptz
) LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_now   timestamptz := now();
  v_pide  boolean     := coalesce(p_requires_ack, false);
  v_plazo double precision := greatest(coalesce(p_ack_deadline_s, 900), 1);
  v_row   ops_alert_notices%ROWTYPE;
BEGIN
  INSERT INTO ops_alert_notices (
    sns_message_id, topic_arn, alarm_name, alarm_state, subject, state_reason,
    published_at, received_at, requires_ack, ack_deadline_at)
  VALUES (
    p_sns_message_id, p_topic_arn, nullif(p_alarm_name, ''), nullif(p_alarm_state, ''),
    nullif(p_subject, ''), nullif(p_state_reason, ''), p_published_at, v_now, v_pide,
    CASE WHEN v_pide THEN v_now + make_interval(secs => v_plazo) END)
  ON CONFLICT (sns_message_id) DO NOTHING
  RETURNING * INTO v_row;
  IF FOUND THEN
    RETURN QUERY SELECT v_row.notice_id, true, v_row.requires_ack, v_row.ack_deadline_at;
    RETURN;
  END IF;
  SELECT * INTO v_row FROM ops_alert_notices WHERE sns_message_id = p_sns_message_id;
  RETURN QUERY SELECT v_row.notice_id, false, v_row.requires_ack, v_row.ack_deadline_at;
END
$fn$;
-- LA CESIÓN DE PROPIEDAD **NO VA AQUÍ**, y no es un olvido — es la misma nota que
-- lleva `app_notify_delivery` unas líneas más arriba, y se volvió a medir con esta
-- ficha: este cuerpo lo ejecuta la 0001 bajo `SET ROLE takab_migrator`, que NO es
-- miembro de `takab_ingest`, así que un `ALTER FUNCTION ... OWNER TO takab_ingest`
-- en este fichero mata la migración inicial con `must be able to SET ROLE
-- "takab_ingest"` (medido contra base vacía, 2026-08-14). El dueño lo pone la 0041
-- —con el usuario de conexión, dentro de la ventana de privilegios que abre
-- `deploy/cloud/deploy.sh`— y ahí mismo se COMPRUEBA: sin dueño `takab_ingest` la
-- función no ve una sola fila (RLS FORCE) y el suscriptor no registraría ni un
-- aviso, en silencio y para siempre.
REVOKE ALL ON FUNCTION app_ops_alert_record(text,text,text,text,text,text,timestamptz,
  boolean,double precision) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_ops_alert_record(text,text,text,text,text,text,timestamptz,
  boolean,double precision) TO takab_app;

CREATE FUNCTION app_ops_alert_ack(p_token_hash text)
RETURNS TABLE (o_token_ok boolean, o_label text, o_acusados jsonb)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
  v_now      timestamptz := now();
  v_contacto ops_oncall_contacts%ROWTYPE;
  v_acusados jsonb;
BEGIN
  SELECT * INTO v_contacto FROM ops_oncall_contacts
   WHERE token_hash = p_token_hash AND revoked_at IS NULL AND expires_at > v_now;
  IF NOT FOUND THEN
    -- Credencial inventada, revocada o caducada: las tres, lo mismo.
    RETURN QUERY SELECT false, NULL::text, '[]'::jsonb;
    RETURN;
  END IF;
  -- Se acusan TODOS los avisos abiertos, no uno elegido por quien llama: quien
  -- dice "lo tengo" a las 3 de la mañana está tomando la situación entera, y
  -- pedirle que teclee un identificador desde el teléfono es como no tener
  -- acuse. Cada fila conserva SU `received_at`, así que la latencia por aviso
  -- sigue siendo la suya.
  WITH acusados AS (
    UPDATE ops_alert_notices n
       SET acked_at = v_now, acked_by = v_contacto.label,
           acked_contact_id = v_contacto.contact_id
     WHERE n.requires_ack AND n.acked_at IS NULL
    RETURNING n.notice_id, n.alarm_name, n.received_at, n.ack_deadline_at
  )
  SELECT coalesce(jsonb_agg(jsonb_build_object(
           'notice_id', a.notice_id, 'alarm_name', a.alarm_name, 'acked_at', v_now,
           'latency_s', extract(epoch FROM (v_now - a.received_at)),
           'tarde', (a.ack_deadline_at IS NOT NULL AND v_now > a.ack_deadline_at)
         )), '[]'::jsonb)
    INTO v_acusados FROM acusados a;
  RETURN QUERY SELECT true, v_contacto.label, v_acusados;
END
$fn$;
-- El dueño, otra vez, lo pone la 0041 y no este fichero (ver la nota de arriba).
REVOKE ALL ON FUNCTION app_ops_alert_ack(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_ops_alert_ack(text) TO takab_app;

-- ---------------------------------------------------------------------------
-- [T-2.81.a · 0043] LA CONSTANCIA DE CADA CORRIDA DE RETENCIÓN
--
-- El job de retención existía y era invocable, y no lo llamaba nadie. Una
-- retención que nadie ejecuta es una política escrita, no una cumplida — y la
-- diferencia importa el día que un cliente pregunta cuánto tiempo guardamos su
-- teléfono. Ahora lo llama un cron (documento SSM `takab-<env>-retencion-pii`),
-- y esta tabla es lo que hace COMPROBABLE que corrió.
--
-- SIN TENANT, como `ops_alert_notices`: una corrida recorre a todos los clientes
-- y es un hecho de la PLATAFORMA. El detalle por cliente viaja dentro de
-- `report` (el mismo JSON que imprime el simulacro), que es donde un auditor lo
-- lee sin que ningún cliente pueda ver las cifras de otro.
--
-- LA FILA SE ESCRIBE FUERA DE LA TRANSACCIÓN DEL JOB, y ése es el punto entero:
-- la corrida es UNA transacción que se revierte ENTERA si algo no cuadra
-- (`ops/prune_pii`). Escribir aquí dentro habría hecho desaparecer, con el
-- rollback, justo la constancia de la corrida que falló — la única que alguien
-- necesita leer. Por eso `ok` puede ser `false`: una corrida abortada deja fila.
--
-- El CHECK es el candado de "un fallo se ve": no se puede declarar fallo sin
-- decir por qué, ni éxito arrastrando un error. Un `UPDATE` a mano lo intenta y
-- la base lo rechaza.
CREATE TABLE pii_retention_runs (
  run_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  started_at    timestamptz NOT NULL,
  finished_at   timestamptz NOT NULL DEFAULT now(),
  -- El simulacro TAMBIÉN deja constancia. Es la corrida que no borró nada, y es
  -- exactamente la que hay que poder enseñar: prueba que el reloj se revisó.
  mode          text NOT NULL CHECK (mode IN ('simulacro','aplicado')),
  ok            boolean NOT NULL,
  total_due     bigint NOT NULL DEFAULT 0,
  total_applied bigint NOT NULL DEFAULT 0,
  report        jsonb  NOT NULL DEFAULT '{}'::jsonb,
  error         text,
  CONSTRAINT prr_el_fallo_lleva_su_razon CHECK (ok = (error IS NULL))
);
-- La consulta del publicador de la métrica: "¿cuánto hace de la última corrida
-- que SÍ terminó?". La alarma cuelga de ahí, así que el índice también.
CREATE INDEX idx_pii_retention_runs_ok ON pii_retention_runs (finished_at DESC) WHERE ok;

GRANT SELECT, INSERT ON pii_retention_runs TO takab_app;
-- Una corrida no se edita ni se borra: es el registro de que la retención se
-- ejecutó. Editarlo sería poder afirmar que se podó lo que no se podó.
REVOKE UPDATE, DELETE ON pii_retention_runs FROM takab_app;

ALTER TABLE pii_retention_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE pii_retention_runs FORCE  ROW LEVEL SECURITY;
CREATE POLICY pii_retention_runs_internal ON pii_retention_runs FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());


-- ---------------------------------------------------------------------------
-- 15. CCTV — AFORO Y EVIDENCIA DE EVACUACIÓN (T-3.11.b · blueprint §4.8)
-- ---------------------------------------------------------------------------
-- ESPEJO EXACTO de `api/migrations/versions/0053_cctv.py`, GENERADO desde ella.
-- Las dos tienen que coincidir: 0001 aplica ESTE archivo sobre base fresca y la
-- migración lo replica sobre base existente. Si divergen, «verde en local» y
-- «verde en la nube» dejan de significar lo mismo — ya pasó dos veces.
--
-- Los clips NO van en `evidence_objects`: esa tabla es COMPLIANCE_ANCHOR y queda
-- exenta de la poda, y el vídeo NO puede heredar esa exención (la regla de oro 11
-- protege auditoría y dictámenes, no imágenes de personas — blueprint §4.8/B.4).
--
-- Por eso `cctv_clips`/`cctv_stills` llevan el patrón de DOS TRIGGERS de
-- `life_checkins`, con los eventos SEPARADOS: DELETE por el guard canónico, y
-- UPDATE por una rendija que solo admite `s3_key → NULL`. Juntarlos en un
-- `BEFORE UPDATE OR DELETE` haría que `cctv_purge_guard` —que ordena ANTES que
-- `forbid_update_delete`— pasara a ser la guarda canónica de TODO el esquema
-- para `ops/restore_check.py`, cambiando en silencio qué se verifica.


-- La rendija de poda del vídeo. Genérica a propósito: sirve a cualquier tabla con
-- `s3_key` + `purged_at`, y plpgsql resuelve los campos del registro en tiempo de
-- ejecución. El mensaje CONSERVA el literal 'tabla append-only' porque el verificador de
-- restore reconoce la guarda por ese texto y por su SQLSTATE (P0001).
CREATE FUNCTION cctv_purge_guard() RETURNS trigger
  LANGUAGE plpgsql AS $$
BEGIN
  -- Red de seguridad: si alguien colgara esta función del evento DELETE en vez de
  -- `forbid_update_delete()`, el borrado seguiria sin pasar.
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'tabla append-only: % no permite %', TG_TABLE_NAME, TG_OP;
  END IF;
  -- La UNICA mutacion admitida: `s3_key` pasa de TENER VALOR a NULL, con el resto de la
  -- fila identica salvo `purged_at`. Exigir la transicion real (y no solo que NEW.s3_key
  -- sea NULL) deja fuera el `UPDATE ... SET c = c`, que es justo lo que ejerce el
  -- verificador de restore para comprobar que la guarda esta viva.
  IF NOT (OLD.s3_key IS NOT NULL AND NEW.s3_key IS NULL)
     OR (to_jsonb(NEW) - 's3_key' - 'purged_at')
        IS DISTINCT FROM (to_jsonb(OLD) - 's3_key' - 'purged_at') THEN
    RAISE EXCEPTION
      'tabla append-only: % no permite % (unica excepcion: anular s3_key, '
      'poda de retencion de video)', TG_TABLE_NAME, TG_OP;
  END IF;
  RETURN NEW;
END $$;

CREATE TABLE cameras (
  camera_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES tenants(tenant_id),
  site_id           uuid NOT NULL REFERENCES sites(site_id),
  -- El punto de reunion al que apunta. `site_assets` YA tiene kind='assembly_point'.
  assembly_asset_id uuid REFERENCES site_assets(asset_id),
  name              text NOT NULL,
  host              text NOT NULL DEFAULT '',
  onvif_port        integer NOT NULL DEFAULT 80 CHECK (onvif_port BETWEEN 1 AND 65535),
  -- SIN credencial. Ver la nota de la cabecera: una URL con usuario y clave seria una
  -- fuga que ningun detector de PII del proyecto reconoce.
  rtsp_url          text NOT NULL DEFAULT '',
  profile           text NOT NULL DEFAULT 'substream'
                    CHECK (profile IN ('substream','main')),
  enabled           boolean NOT NULL DEFAULT false,
  count_mode        text NOT NULL DEFAULT 'cloud'
                    CHECK (count_mode IN ('cloud','local','off')),
  created_at        timestamptz NOT NULL DEFAULT now(),
  created_by        uuid,
  updated_at        timestamptz NOT NULL DEFAULT now(),
  updated_by        uuid,
  UNIQUE (site_id, name)
);
CREATE INDEX idx_cameras_tenant ON cameras (tenant_id);
CREATE INDEX idx_cameras_site   ON cameras (site_id) WHERE enabled;

CREATE TABLE cctv_clips (
  clip_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES tenants(tenant_id),
  incident_id    uuid NOT NULL REFERENCES incidents(incident_id),
  camera_id      uuid REFERENCES cameras(camera_id),
  -- NULLABLE, y la nulabilidad ES la funcion: al podar, el objeto muere y la fila lo
  -- declara. El sha256 y las horas sobreviven para la cadena de custodia.
  s3_key         text,
  sha256         text,
  size_bytes     bigint,
  started_at     timestamptz NOT NULL,
  ended_at       timestamptz NOT NULL,
  -- Fraccion [0..1] de la ventana pedida que el anillo pudo cubrir de verdad. Un clip que
  -- dice cubrir T-60s sin cubrirlo es una mentira en un reporte.
  coverage       numeric,
  -- NO hay columna `analysis_state`, y su ausencia es la decision. Una columna de
  -- estado MUTABLE sobre una tabla append-only es una contradiccion: el guard de poda
  -- solo admite `s3_key -> NULL`, asi que el analizador jamas podria moverla de
  -- 'pending'. El estado se DERIVA de si existen filas en `cctv_evacuation_metrics`
  -- para ese incidente — misma doctrina que `calibrated` (derivado de la procedencia)
  -- y que `is_ghost` (derivado de `derived_state`): lo que se puede derivar no se
  -- guarda, porque guardado se desincroniza y derivado no puede.
  purged_at      timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now()
);
-- Idempotencia POR CONTENIDO, con el precedente exacto de `uq_evidence_incident_sha256`
-- (0002). Un `UNIQUE (incident_id, started_at, camera_id)` NO servia: `camera_id` es
-- nullable y en Postgres los NULL son DISTINTOS en un indice unico, asi que dos entregas
-- del mismo objeto no colisionaban y el `ON CONFLICT DO NOTHING` no hacia nada. Lo caza
-- `test_una_REENTREGA_no_dice_que_el_video_salio_dos_veces`, y lo cazo de verdad.
-- Por contenido ademas es lo correcto: la key lleva el sha256 dentro, asi que el MISMO
-- objeto produce la misma fila por construccion. El indice es PARCIAL porque el sha solo
-- falta en filas que aun no tienen objeto.
CREATE UNIQUE INDEX uq_cctv_clips_incident_sha256
  ON cctv_clips (incident_id, sha256) WHERE sha256 IS NOT NULL;
CREATE INDEX idx_cctv_clips_tenant   ON cctv_clips (tenant_id);
CREATE INDEX idx_cctv_clips_incident ON cctv_clips (incident_id, started_at DESC);

CREATE TABLE cctv_stills (
  still_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
  incident_id uuid NOT NULL REFERENCES incidents(incident_id),
  clip_id     uuid REFERENCES cctv_clips(clip_id),
  camera_id   uuid REFERENCES cameras(camera_id),
  -- `drip` es la captura periodica cruda; las otras cuatro son las que ELIGE la nube para
  -- el reporte, ya con la curva de aforo en la mano.
  role        text NOT NULL DEFAULT 'drip'
              CHECK (role IN ('pre','egress','peak','reentry','drip')),
  s3_key      text,
  sha256      text,
  captured_at timestamptz NOT NULL,
  purged_at   timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);
-- Misma razon que en `cctv_clips`: por contenido, y parcial.
CREATE UNIQUE INDEX uq_cctv_stills_incident_sha256
  ON cctv_stills (incident_id, sha256) WHERE sha256 IS NOT NULL;
CREATE INDEX idx_cctv_stills_tenant   ON cctv_stills (tenant_id);
CREATE INDEX idx_cctv_stills_incident ON cctv_stills (incident_id, captured_at);
CREATE INDEX idx_cctv_stills_reporte
  ON cctv_stills (incident_id, role) WHERE role <> 'drip';

-- La curva de aforo. NO es hypertable: es una serie ACOTADA por incidente (minutos u
-- horas, no continua), y una hypertable traeria chunks, retencion y RLS con columnstore
-- —el conflicto que ya documenta el esquema— a cambio de nada.
CREATE TABLE cctv_occupancy (
  incident_id uuid NOT NULL REFERENCES incidents(incident_id),
  camera_id   uuid NOT NULL REFERENCES cameras(camera_id),
  ts          timestamptz NOT NULL,
  -- `provenance` no es adorno: el conteo FINAL de la nube sobrescribe al preliminar del
  -- borde, y mezclarlos sin distinguirlos daria una curva con dos modelos dentro.
  provenance  text NOT NULL CHECK (provenance IN ('preliminary','final')),
  tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
  n_people    integer NOT NULL CHECK (n_people >= 0),
  PRIMARY KEY (incident_id, camera_id, ts, provenance)
);
CREATE INDEX idx_cctv_occupancy_tenant ON cctv_occupancy (tenant_id);

CREATE TABLE cctv_evacuation_metrics (
  incident_id       uuid NOT NULL REFERENCES incidents(incident_id),
  provenance        text NOT NULL CHECK (provenance IN ('preliminary','final')),
  tenant_id         uuid NOT NULL REFERENCES tenants(tenant_id),
  -- Segundos DESDE la señal. `t90_s` es «cuanto tardo en salir la mayor parte».
  t50_s             numeric,
  t90_s             numeric,
  peak_n            integer,
  peak_at           timestamptz,
  reentry_start_at  timestamptz,
  dictamen_lag_s    numeric,
  -- NEGATIVO significa que la gente reentro ANTES del dictamen firmado. Eso no es un
  -- numero: es un hallazgo de seguridad, y el reporte lo dice con palabras.
  reentry_lag_s     numeric,
  -- El otro lado del cruce de T-3.12: se muestra como DISCREPANCIA frente a `peak_n`,
  -- jamas promediado en un numero unico.
  checkin_count     integer,
  computed_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (incident_id, provenance)
);
CREATE INDEX idx_cctv_metrics_tenant ON cctv_evacuation_metrics (tenant_id);

-- Los dos triggers, con los eventos SEPARADOS (ver la nota de la cabecera).
CREATE TRIGGER trg_cctv_clips_append_only
  BEFORE DELETE ON cctv_clips FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE TRIGGER trg_cctv_clips_purge_guard
  BEFORE UPDATE ON cctv_clips FOR EACH ROW EXECUTE FUNCTION cctv_purge_guard();

CREATE TRIGGER trg_cctv_stills_append_only
  BEFORE DELETE ON cctv_stills FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE TRIGGER trg_cctv_stills_purge_guard
  BEFORE UPDATE ON cctv_stills FOR EACH ROW EXECUTE FUNCTION cctv_purge_guard();

GRANT SELECT, INSERT, UPDATE ON cameras                 TO takab_app;
GRANT SELECT, INSERT, UPDATE ON cctv_clips              TO takab_app;
GRANT SELECT, INSERT, UPDATE ON cctv_stills             TO takab_app;
GRANT SELECT, INSERT, UPDATE ON cctv_occupancy          TO takab_app;
GRANT SELECT, INSERT, UPDATE ON cctv_evacuation_metrics TO takab_app;

-- La otra capa del append-only: sin el privilegio, el guard no es la unica defensa.
-- `test_append_only_dos_capas.py` DERIVA estas dos tablas por su trigger de DELETE y
-- exige exactamente esto.
REVOKE DELETE ON cctv_clips  FROM takab_app;
REVOKE DELETE ON cctv_stills FROM takab_app;

-- El worker de backfill corre como `takab_ingest` (BYPASSRLS), NO como `takab_app`: es
-- quien registra el objeto cuando S3 avisa. Sin estas lineas el clip sube, la
-- notificacion llega y el INSERT muere con «permission denied» — verde en local y rojo
-- en la nube, que es el modo de fallo que este proyecto ya conoce. Y sin DELETE tampoco
-- para el, que el append-only no depende del rol que lo intente.
GRANT SELECT, INSERT ON cctv_clips              TO takab_ingest;
GRANT SELECT, INSERT ON cctv_stills             TO takab_ingest;
GRANT SELECT, INSERT ON cctv_occupancy          TO takab_ingest;
GRANT SELECT, INSERT, UPDATE ON cctv_evacuation_metrics TO takab_ingest;
GRANT SELECT ON cameras TO takab_ingest;

ALTER TABLE cameras                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE cameras                 FORCE  ROW LEVEL SECURITY;
ALTER TABLE cctv_clips              ENABLE ROW LEVEL SECURITY;
ALTER TABLE cctv_clips              FORCE  ROW LEVEL SECURITY;
ALTER TABLE cctv_stills             ENABLE ROW LEVEL SECURITY;
ALTER TABLE cctv_stills             FORCE  ROW LEVEL SECURITY;
ALTER TABLE cctv_occupancy          ENABLE ROW LEVEL SECURITY;
ALTER TABLE cctv_occupancy          FORCE  ROW LEVEL SECURITY;
ALTER TABLE cctv_evacuation_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE cctv_evacuation_metrics FORCE  ROW LEVEL SECURITY;

CREATE POLICY cameras_read ON cameras FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY cameras_write ON cameras FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY cameras_admin ON cameras FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

CREATE POLICY cctv_clips_read ON cctv_clips FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY cctv_clips_write ON cctv_clips FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY cctv_clips_admin ON cctv_clips FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

CREATE POLICY cctv_stills_read ON cctv_stills FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY cctv_stills_write ON cctv_stills FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY cctv_stills_admin ON cctv_stills FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

CREATE POLICY cctv_occupancy_read ON cctv_occupancy FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY cctv_occupancy_write ON cctv_occupancy FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY cctv_occupancy_admin ON cctv_occupancy FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());

CREATE POLICY cctv_evacuation_metrics_read ON cctv_evacuation_metrics FOR SELECT
  USING (tenant_id = app_tenant_id() OR app_is_takab_internal());
CREATE POLICY cctv_evacuation_metrics_write ON cctv_evacuation_metrics FOR ALL
  USING      (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator')
  WITH CHECK (tenant_id = app_tenant_id() AND app_role() <> 'gov_operator');
CREATE POLICY cctv_evacuation_metrics_admin ON cctv_evacuation_metrics FOR ALL
  USING (app_is_takab_internal()) WITH CHECK (app_is_takab_internal());
