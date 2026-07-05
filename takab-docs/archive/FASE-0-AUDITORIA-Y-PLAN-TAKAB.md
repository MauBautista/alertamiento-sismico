> **[ARCHIVO HISTÓRICO — restaurado de `6c9b1e0:docs/FASE-0-AUDITORIA-Y-PLAN-TAKAB.md` en la rama
> `analisis/arquitectura-00`.]** Este documento es referencia de decisiones de descubrimiento; el
> documento canónico vigente es `takab-docs/BLUEPRINT-TECNICO-TAKAB.md` y, ante conflicto, este
> archivo NO gobierna. Advertencias: las secciones de UI (Req. 4.1, p. ej. `<AlertBanner>` con
> `t_minus_s`/magnitud) reflejan el deck — T-MINUS y magnitud preliminar están DIFERIDOS
> (blueprint §14); la numeración de tareas (1.x/2.x/3.x) fue reemplazada por `TASKS.md` (T-1.x);
> la sección 3.1 (supresión por IA) queda condicionada a la regla de oro 1 de `CLAUDE.md`.
> Ver `takab-docs/ANALISIS-ARQUITECTURA-TAKAB.md`.

# TAKAB Technology — Auditoría de Arquitectura y Plan de Acción Definitivo
**Versión 1.0 · Fase 0 Foundation · Documento maestro del proyecto**

> Este documento incorpora TODAS las decisiones ya cerradas en las sesiones de descubrimiento:
> arquitectura de 2 placas (Raspberry Shake + Raspberry Pi 5), SASMEX vía WR-1 contacto seco #2,
> AWS IoT Core como plataforma cloud, regla de quórum ≥3 estaciones (ventana 2–5 s),
> estrategia híbrida de streaming (features continuos + waveform bajo demanda),
> multi-tenant con modos lógico/dedicado, y desarrollo 100% vía Claude Code dirigido por prompts.

---

# REQUERIMIENTO 1 — AUDITORÍA DE ARQUITECTURA Y RIESGOS TÉCNICOS

## 1.1 Puntos únicos de falla (SPOF) que pueden costar vidas

Ordenados por severidad real, con mitigación obligatoria:

### SPOF-01 · La regla de quórum «3 nodos» depende de la nube ⚠️ CRÍTICO
**Problema:** La detección local colaborativa (≥3 estaciones en 2–5 s) se correlaciona en la nube.
En un sismo grande, el internet regional puede caerse ANTES de que la onda S llegue a los edificios
(la onda P viaja ~6–8 km/s; la caída de infraestructura suele ser inmediata al arribo de la S en el
epicentro). Resultado: justo cuando más se necesita el quórum, no hay nube.

**Mitigación obligatoria:**
1. SASMEX (radio, independiente de internet) es y debe permanecer como el canal primario de
   activación. El quórum colaborativo es COMPLEMENTARIO, nunca sustituto.
2. El umbral local individual (PGA/PGV del propio sensor del edificio) debe poder disparar
   protocolo reducido (estrobo + notificación local, sin sirena general) aun sin quórum,
   configurable por cliente.
3. Documentar contractualmente: «la detección colaborativa requiere conectividad».

### SPOF-02 · Raspberry Pi 5 única como cerebro del gabinete
**Problema:** Si el Pi 5 se congela (kernel panic, SD corrupta, thermal throttling), el gabinete
queda mudo: no SASMEX, no sirena, no telemetría.

**Mitigación obligatoria:**
1. **Watchdog de hardware** del BCM2712 habilitado (`dtparam=watchdog=on` +
   `systemd` `RuntimeWatchdogSec=10`). Si el sistema se cuelga, reboot automático en <15 s.
2. **Boot desde NVMe o eMMC industrial**, nunca microSD consumer (la primera causa de muerte
   de Raspberry Pi en campo es corrupción de SD por cortes de energía).
3. Sistema de archivos con **overlayroot** (raíz de solo lectura) + partición de datos separada
   con `ext4 data=journal`.
4. **Ruta de hardware directa SASMEX→sirena como respaldo último:** el contacto seco #2 del WR-1
   puede, además de entrar al GPIO, cablear EN PARALELO un relé de potencia que dispare la sirena
   sin pasar por software. Si el Pi está muerto, SASMEX sigue sonando la sirena. Costo: ~$150 MXN.
   Esta es la mitigación más importante de todo el sistema.

### SPOF-03 · Receptor WR-1 único
**Problema:** receptor dañado/desconfigurado = sin alerta temprana SASMEX en ese sitio.
**Mitigación:** monitorear el contacto seco #1 (pruebas periódicas de CIRES) como heartbeat;
si no se recibe la prueba esperada en N días → alerta de mantenimiento en Flota Edge.
Verificar con CIRES la cadencia de las pruebas para calibrar N.

### SPOF-04 · Energía
**Mitigación:** UPS interna del gabinete (decisión ya tomada: 4–12 h), PERO con:
- supervisión de la UPS por el Pi (USB/HID o medición de voltaje por ADC) → métrica
  `power_status` y `battery_remaining` a la nube (ya contemplado en el mockup Flota Edge),
- apagado limpio automático al 10% de batería con last-will MQTT (`disconnected: power_loss`),
- la sirena debe poder dispararse con batería: dimensionar UPS para el pico de corriente
  de la sirena (una sirena de 30 W a 12 V = 2.5 A pico; verificar contra la UPS elegida).

### SPOF-05 · Certificados X.509 que expiran
**Problema clásico de flotas IoT:** los certificados de AWS IoT Core expiran o se revocan y toda
la flota queda muda silenciosamente.
**Mitigación:** rotación automática vía AWS IoT fleet provisioning, alarma de expiración a 30 días,
y métrica `cert_days_remaining` en el autodiagnóstico del gabinete.

### SPOF-06 · NTP
**Problema:** la correlación de quórum (ventana 2–5 s) y los sellos de tiempo de dictámenes
dependen de relojes sincronizados. Sin internet no hay NTP.
**Mitigación:** RTC de hardware en el Pi 5 (DS3231, ~$80 MXN) + `chrony` con el RTC como fallback.
Deriva del DS3231: ±2 ppm ≈ 0.17 s/día — aceptable para ventanas de 2–5 s durante horas sin red.
Métrica `ntp_offset_ms` ya contemplada en el mockup (panel de detalle del sitio).

### SPOF-07 · Relés en estado incorrecto al fallar
**Decisión de diseño obligatoria:** definir por actuador si es fail-safe o fail-secure:
- Sirena: **NO** (normalmente abierto) — una falla del Pi NO debe dejar la sirena sonando.
- Retenedores de puertas de emergencia: **NC** (normalmente cerrado) — una falla DEBE liberar
  las puertas (fail-open de evacuación).
- Válvula de gas (enterprise): fail-close.
Esto se configura por canal de relé en el perfil del sitio.

## 1.2 FastAPI + SeedLink/streams de baja latencia: cómo NO romperlo

**Regla de oro: FastAPI nunca toca SeedLink.** FastAPI es para servir HTTP. La ingesta de un
stream TCP continuo dentro del event loop de una API es un anti-patrón que produce backpressure,
timeouts y pérdida de paquetes bajo carga.

**Arquitectura correcta en el Pi 5 — procesos systemd separados:**

```
┌─────────────────────────────────────────────────────────┐
│ Raspberry Pi 5 (gateway TAKAB)                          │
│                                                         │
│  [1] takab-ingest      Python+ObsPy. Cliente SeedLink   │
│       └─ lee del Shake (TCP 18000), decodifica miniSEED,│
│          publica ventanas crudas en bus local           │
│  [2] takab-dsp         Python+NumPy/SciPy.              │
│       └─ features por ventana 1s: PGA,PGV,RMS,STA/LTA   │
│  [3] takab-rules       Motor de reglas determinista     │
│       └─ umbrales T1/T2/T3, máquina de estados          │
│  [4] takab-gpio        Único proceso con acceso a GPIO  │
│       └─ lee WR-1 (debounce 50ms), maneja relés,        │
│          botones de prueba/silencio, LEDs               │
│  [5] takab-sync        Cliente AWS IoT (MQTT+mTLS)      │
│       └─ publica features/eventos, cola offline en disco│
│  [6] takab-api         FastAPI local (dashboard edificio│
│       └─ y endpoint de diagnóstico para técnicos)       │
│                                                         │
│  Bus local entre procesos: mosquitto (localhost) con    │
│  tópicos takab/local/#  — simple, observable, desacopla │
└─────────────────────────────────────────────────────────┘
```

**Por qué procesos separados y no asyncio monolítico:**
- Aislamiento de fallas: si `takab-dsp` crashea por un paquete corrupto, `takab-gpio` sigue
  respondiendo a SASMEX. systemd reinicia el proceso caído (`Restart=always`, `WatchdogSec=`).
- GIL: la extracción de features es CPU-bound; en proceso separado usa su propio core
  (el Pi 5 tiene 4).
- El proceso GPIO debe ser mínimo, auditable y sin dependencias pesadas: ~200 líneas,
  arranca en <1 s, prioridad `nice -10`.

**Dentro de cada proceso:** asyncio donde es I/O-bound (sync, api), hilo dedicado bloqueante para
el cliente SeedLink (ObsPy `EasySeedLinkClient` es bloqueante; envolverlo en thread con cola
`janus` hacia asyncio), y NumPy vectorizado en dsp (sin hilos: una ventana de 1 s a 100 Hz son
100 muestras — trivial).

**Latencia presupuestada del camino crítico SASMEX→sirena:**
GPIO interrupt (<1 ms) + debounce (50 ms) + regla (<5 ms) + relé (<10 ms) ≈ **<70 ms**. ✅
El camino sísmico local (SeedLink→features→regla→relé) presupuesta <1 s (el lag propio de
SeedLink del Shake es ~0.2–0.5 s).

## 1.3 Thundering Herd: 100 gateways reconectando tras un sismo masivo

Escenario: sismo M7+, cae internet regional 30 min, al volver 100 gateways reconectan
simultáneamente con horas de datos en cola. Diseño anti-estampida en 5 capas:

**Capa 1 — Reconexión escalonada (cliente):** el SDK de AWS IoT Device ya implementa
exponential backoff con jitter. Configurar: base 1 s, máximo 128 s, jitter completo.
Además, retraso inicial aleatorio `hash(device_id) % 60` segundos antes del primer intento.

**Capa 2 — Prioridad de mensajes (cliente):** al reconectar, el gateway publica en este orden:
1. Estado actual (`takab/{site}/state` — retained, QoS 1): la nube recupera visión inmediata.
2. Eventos/incidentes de la cola offline (QoS 1, pocos, críticos).
3. Features históricos en lotes comprimidos: NO por MQTT — ver capa 4.

**Capa 3 — Desacople en la nube:** la regla de AWS IoT Core NO escribe directo a PostgreSQL.
Flujo: `IoT Rule → SQS (buffer elástico) → consumidor (ECS/Lambda con concurrencia limitada) →
Timescale`. SQS absorbe el pico; la DB recibe un caudal constante. Sin esto, 100 gateways
descargando colas tirarían las conexiones de Postgres.

**Capa 4 — Backfill masivo por S3, no por MQTT:** los datos históricos acumulados se suben como
archivos comprimidos (Parquet/JSONL.gz) a S3 vía URL pre-firmada solicitada por API. Un job
(Lambda/Batch) los ingiere a Timescale a su ritmo. MQTT queda libre para tiempo real.
Regla: si la cola offline > 15 min de datos → ruta S3; si < 15 min → MQTT por lotes.

**Capa 5 — Idempotencia total (servidor):** ningún dato se duplica aunque se reenvíe:
- Features: PK natural `(ts, device_id, channel)` + `INSERT ... ON CONFLICT DO NOTHING`.
- Eventos: `event_uuid` generado en el edge (UUIDv7) + índice único.
- Estado: tópicos retained = last-write-wins natural.

---

# REQUERIMIENTO 2 — MODELO DE DATOS DE PRODUCCIÓN

Script listo para producción (PostgreSQL 16 + TimescaleDB 2.x + PostGIS 3.x).
Refleja las decisiones TAKAB: dos tipos de sensor (estructural/terreno), sensor de terreno
compartible entre sitios, tenant lógico vs dedicado, quórum de 3 nodos auditable.

```sql
-- ============================================================
-- TAKAB · Esquema de producción v1
-- Requiere: CREATE EXTENSION timescaledb; postgis; pgcrypto;
-- ============================================================
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------- 1. MULTI-TENANT CORE ----------
CREATE TABLE tenants (
  tenant_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code           text NOT NULL UNIQUE,              -- 'TKB-001'
  name           text NOT NULL,
  isolation_mode text NOT NULL DEFAULT 'logical'
                 CHECK (isolation_mode IN ('logical','dedicated')),
  vertical       text,                              -- 'hospital','industrial','gobierno'...
  visibility     text NOT NULL DEFAULT 'private'
                 CHECK (visibility IN ('private','gov_shared')),
  status         text NOT NULL DEFAULT 'active'
                 CHECK (status IN ('trial','active','suspended')),
  plan_code      text NOT NULL DEFAULT 'mvp',
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sites (
  site_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants ON DELETE RESTRICT,
  code         text NOT NULL,                       -- 'CHL-A'
  name         text NOT NULL,
  timezone     text NOT NULL DEFAULT 'America/Mexico_City',
  criticality  text NOT NULL DEFAULT 'medium'
               CHECK (criticality IN ('low','medium','high','critical')),
  geom         geography(Point,4326) NOT NULL,      -- ubicación del inmueble
  address      text,
  building_type text,                               -- p/ perfiles de umbral por tipología
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, code)
);
CREATE INDEX idx_sites_geom ON sites USING GIST (geom);
CREATE INDEX idx_sites_tenant ON sites (tenant_id);

CREATE TABLE zones (                                -- pisos/zonas dentro del sitio
  zone_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id    uuid NOT NULL REFERENCES sites ON DELETE CASCADE,
  name       text NOT NULL,                         -- 'Piso 3 · Ala Norte'
  level_code text,                                  -- 'P3', 'SOT1'
  geom       geometry(Polygon, 4326)                -- croquis opcional (plano local)
);

-- ---------- 2. HARDWARE: GABINETES Y SENSORES ----------
CREATE TABLE gateways (                             -- el Pi 5 "cerebro" del gabinete
  gateway_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants,
  site_id      uuid NOT NULL REFERENCES sites,
  serial       text NOT NULL UNIQUE,
  fw_version   text,
  iot_thing    text UNIQUE,                         -- nombre del Thing en AWS IoT Core
  status       text NOT NULL DEFAULT 'provisioned'
               CHECK (status IN ('provisioned','online','degraded','offline','retired')),
  has_wr1      boolean NOT NULL DEFAULT true,       -- receptor SASMEX presente
  installed_at timestamptz,
  metadata     jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE sensors (
  sensor_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants,
  site_id      uuid NOT NULL REFERENCES sites,
  gateway_id   uuid REFERENCES gateways,
  zone_id      uuid REFERENCES zones,
  kind         text NOT NULL
               CHECK (kind IN ('structural','ground')),  -- pared vs enterrado ★ decisión TAKAB
  model        text NOT NULL,                       -- 'RS4D','RS3D','RS1D'
  serial       text UNIQUE,
  channels     text[] NOT NULL DEFAULT '{EHZ}',     -- canales SeedLink activos
  sample_rate  int  NOT NULL DEFAULT 100,
  mount        text CHECK (mount IN ('concrete_column','steel','floor','buried')),
  geom         geography(Point,4326),
  status       text NOT NULL DEFAULT 'active',
  metadata     jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_sensors_site ON sensors (site_id);

-- Un sitio puede REFERENCIAR el sensor de terreno de un sitio vecino ★ decisión TAKAB
CREATE TABLE site_ground_refs (
  site_id          uuid NOT NULL REFERENCES sites ON DELETE CASCADE,
  ground_sensor_id uuid NOT NULL REFERENCES sensors,
  distance_m       numeric,
  PRIMARY KEY (site_id, ground_sensor_id)
);

-- ---------- 3. REGLAS Y UMBRALES (versionadas) ----------
CREATE TABLE rule_sets (
  rule_set_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants,
  scope_type  text NOT NULL CHECK (scope_type IN ('tenant','site','sensor')),
  scope_id    uuid NOT NULL,
  version     int  NOT NULL,
  is_active   boolean NOT NULL DEFAULT false,
  config      jsonb NOT NULL,    -- {thresholds:{watch:{pga_g:..},..}, quorum:{min:3,window_s:5}, relays:{...}}
  created_by  uuid,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (scope_type, scope_id, version)
);

-- ---------- 4. EVENTOS, INCIDENTES Y QUÓRUM ----------
CREATE TABLE seismic_events (                       -- evento regional consolidado
  event_id    text PRIMARY KEY,                     -- 'EVT-20260510-0843'
  source      text NOT NULL CHECK (source IN ('sasmex','local_quorum','manual','external')),
  magnitude   numeric,                              -- preliminar si disponible
  epicenter   geography(Point,4326),
  depth_km    numeric,
  detected_at timestamptz NOT NULL,
  meta        jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE incidents (                            -- impacto del evento EN UN SITIO
  incident_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_uuid   uuid NOT NULL UNIQUE,                -- UUIDv7 generado en edge → idempotencia
  tenant_id    uuid NOT NULL REFERENCES tenants,
  site_id      uuid NOT NULL REFERENCES sites,
  event_id     text REFERENCES seismic_events,
  opened_at    timestamptz NOT NULL,
  closed_at    timestamptz,
  severity     text NOT NULL CHECK (severity IN ('info','watch','warning','critical')),
  state        text NOT NULL DEFAULT 'open'
               CHECK (state IN ('open','acked','in_review','closed')),
  trigger      text NOT NULL CHECK (trigger IN ('sasmex','local_threshold','quorum','manual')),
  max_pga_g    numeric,
  max_pgv_cms  numeric,
  summary      jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_incidents_site_open ON incidents (site_id, opened_at DESC);
CREATE INDEX idx_incidents_tenant_state ON incidents (tenant_id, state)
  WHERE state <> 'closed';                          -- índice parcial: lista de "abiertos" O(1)

CREATE TABLE quorum_votes (                         -- auditoría de la regla «3 nodos»
  event_id   text NOT NULL REFERENCES seismic_events,
  sensor_id  uuid NOT NULL REFERENCES sensors,
  detected_at timestamptz NOT NULL,
  pga_g      numeric NOT NULL,
  delta_s    numeric,                               -- offset vs primera estación
  counted    boolean NOT NULL DEFAULT true,
  PRIMARY KEY (event_id, sensor_id)
);

CREATE TABLE incident_actions (                     -- timeline auditable
  action_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid NOT NULL REFERENCES incidents ON DELETE CASCADE,
  ts          timestamptz NOT NULL DEFAULT now(),
  kind        text NOT NULL,    -- 'siren_on','gas_closed','ack','dictamen','notify_sent'...
  actor       text NOT NULL,    -- 'edge:CHL-A' | 'user:uuid' | 'system'
  payload     jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_actions_incident ON incident_actions (incident_id, ts);

CREATE TABLE dictamens (
  dictamen_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid NOT NULL REFERENCES incidents,
  status      text NOT NULL CHECK (status IN
              ('normal_operation','inhabit_monitor','restricted','no_inhabit_inspect')),
  basis       jsonb NOT NULL,                       -- evidencias, versión de reglas, métricas
  signed_by   uuid,                                 -- usuario; firma HSM = fase Enterprise
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------- 5. SERIES DE TIEMPO (TimescaleDB) ----------
CREATE TABLE waveform_features_1s (
  ts        timestamptz NOT NULL,
  tenant_id uuid NOT NULL,
  site_id   uuid NOT NULL,
  sensor_id uuid NOT NULL,
  channel   text NOT NULL,
  pga_g     real, pgv_cms real, rms real, stalta real, energy real,
  clipping  boolean NOT NULL DEFAULT false,
  PRIMARY KEY (ts, sensor_id, channel)              -- ★ idempotencia natural
);
SELECT create_hypertable('waveform_features_1s','ts',
       chunk_time_interval => INTERVAL '1 day');
CREATE INDEX idx_wf_site_ts   ON waveform_features_1s (site_id, ts DESC);
CREATE INDEX idx_wf_tenant_ts ON waveform_features_1s (tenant_id, ts DESC);
-- Compresión: 95%+ de ahorro pasados 7 días
ALTER TABLE waveform_features_1s SET (timescaledb.compress,
       timescaledb.compress_segmentby = 'sensor_id,channel');
SELECT add_compression_policy('waveform_features_1s', INTERVAL '7 days');
SELECT add_retention_policy('waveform_features_1s', INTERVAL '24 months');

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

-- Agregado continuo para el mapa del SOC (refresco cada minuto)
CREATE MATERIALIZED VIEW site_metrics_1m
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 minute', ts) AS bucket,
       site_id,
       max(pga_g)  AS max_pga_g,
       max(pgv_cms) AS max_pgv_cms
FROM waveform_features_1s
GROUP BY bucket, site_id;
SELECT add_continuous_aggregate_policy('site_metrics_1m',
  start_offset => INTERVAL '10 minutes', end_offset => INTERVAL '1 minute',
  schedule_interval => INTERVAL '1 minute');

-- ---------- 6. EVIDENCIAS (miniSEED en S3) ----------
CREATE TABLE evidence_objects (
  evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants,
  incident_id uuid REFERENCES incidents,
  sensor_id   uuid REFERENCES sensors,
  kind        text NOT NULL CHECK (kind IN ('miniseed','photo','report_pdf','log')),
  s3_key      text NOT NULL,
  ts_from     timestamptz, ts_to timestamptz,
  sha256      text,                                 -- integridad / cadena de custodia
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------- 7. AUDIT LOG INMUTABLE ----------
CREATE TABLE audit_log (
  audit_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ts         timestamptz NOT NULL DEFAULT now(),
  tenant_id  uuid,
  actor      text NOT NULL,
  verb       text NOT NULL,
  object     text NOT NULL,
  meta       jsonb NOT NULL DEFAULT '{}'
);
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;     -- append-only

-- ---------- 8. ROW-LEVEL SECURITY ----------
ALTER TABLE sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE waveform_features_1s ENABLE ROW LEVEL SECURITY;
-- (replicar en todas las tablas con tenant_id)

CREATE POLICY tenant_isolation ON incidents
  USING (tenant_id = current_setting('app.tenant_id')::uuid
         OR current_setting('app.role', true) = 'gov_operator'
            AND EXISTS (SELECT 1 FROM tenants t
                        WHERE t.tenant_id = incidents.tenant_id
                          AND t.visibility = 'gov_shared'));
-- Patrón: la API setea  SET app.tenant_id = '...'  por request.
-- El rol 'gov_operator' (Protección Civil) ve solo tenants con visibility='gov_shared'
-- ★ implementa el modelo privado vs gubernamental decidido.
```

**Consulta crítica del mapa SOC (lo que ve la página 1 del mockup), <50 ms con estos índices:**

```sql
SELECT s.site_id, s.code, s.name, ST_AsGeoJSON(s.geom) AS geom,
       m.max_pga_g, m.max_pgv_cms,
       i.severity AS active_severity, i.incident_id
FROM sites s
LEFT JOIN LATERAL (
  SELECT max(max_pga_g) AS max_pga_g, max(max_pgv_cms) AS max_pgv_cms
  FROM site_metrics_1m WHERE site_id = s.site_id
    AND bucket >= now() - interval '5 minutes') m ON true
LEFT JOIN LATERAL (
  SELECT incident_id, severity FROM incidents
  WHERE site_id = s.site_id AND state <> 'closed'
  ORDER BY opened_at DESC LIMIT 1) i ON true;
```

---

# REQUERIMIENTO 3 — MODELO OPERATIVO DE INTELIGENCIA ARTIFICIAL

**Principio rector (no negociable): la IA es asesora, nunca está en el camino crítico de
activación de sirenas.** El camino SASMEX→relé y umbral→relé es 100% determinista.

## 3.1 Filtrado de ruido antropogénico (evento vs ruido)

| Aspecto | Especificación |
|---|---|
| Arquitectura | **CNN 1D** (3–4 bloques conv + global pooling + dense). No LSTM (latencia y entrenamiento más frágiles), no Transformer (overkill para ventanas de 4–10 s a 100 Hz; sin datos suficientes para justificarlo) |
| Entrada | Ventana de 4 s × canales disponibles (Z, o Z+EN[ENE/ENN/ENZ] en RS4D), normalizada por z-score; opcionalmente el espectrograma log-mel como segundo canal |
| Features auxiliares | ratio STA/LTA, frecuencia dominante (FFT pico), kurtosis, relación energía 1–10 Hz vs 10–45 Hz (los camiones/maquinaria viven arriba de ~10 Hz; los sismos concentran energía abajo) |
| Salida | `p(sismo)`, `p(ruido_antropogenico)`, `p(falla_sensor)` |
| Dataset | 1) STEAD (Stanford Earthquake Dataset, ~1.2M trazas etiquetadas, público); 2) registros del SSN/FDSN de México; 3) **tu propia red**: cada disparo SASMEX confirmado = etiqueta positiva gratis; cada activación local sin SASMEX ni quórum = candidato a ruido para etiquetar |
| Runtime edge | LiteRT (TensorFlow Lite) en el Pi 5 — modelo cuantizado int8, <500 KB, inferencia <20 ms |
| Rol en reglas | El score NO veta una alerta SASMEX. Solo puede: (a) suprimir el disparo de umbral local individual si `p(ruido)>0.9`, configurable; (b) anotar el voto de quórum con su score para ponderación futura |
| Métrica | Falsas alarmas/sitio/mes (objetivo <1) y recall de eventos reales (objetivo >0.99 — preferimos falsas alarmas a sismos perdidos) |

## 3.2 Sugerencia de dictamen de reingreso (semaforizado)

| Aspecto | Especificación |
|---|---|
| Modelo | **Gradient boosting (XGBoost/LightGBM)** tabular. Interpretable (SHAP), entrenable con pocos datos, robusto. Nada de deep learning aquí: el dictamen debe ser explicable ante Protección Civil |
| Entrada | max PGA/PGV por sensor del sitio, duración de movimiento fuerte, relación estructural/terreno (si hay sensor enterrado: amplificación = PGA_pared/PGA_suelo), espectro de respuesta simplificado, metadata del edificio (tipología, año, pisos), historial de incidentes previos del sitio |
| Salida | Probabilidad por clase del semáforo: `operacion_normal` / `habitar_monitoreo` / `restringido` / `no_habitar_inspeccion` + top-5 factores SHAP en lenguaje natural |
| Dataset frío | No existe al inicio. Fase 1: el "modelo" es la tabla determinista de umbrales (FEMA P-154 / NTC-Sismo como referencia técnica). Cada dictamen manual firmado por un ingeniero se guarda con sus features → en 12–24 meses hay dataset propio para entrenar |
| Runtime | Cloud (Lambda/ECS). Corre post-evento, sin presión de latencia |
| Gobernanza | La sugerencia SIEMPRE requiere firma humana (ya modelado en `dictamens.signed_by`) |

## 3.3 Distribución Edge vs Cloud

| Componente IA | Dónde | Por qué |
|---|---|---|
| Clasificador evento/ruido | **Edge** (LiteRT, Pi 5) | Debe operar sin internet; latencia <20 ms |
| Salud anómala del sensor (drift, offset, sensor flojo) | **Cloud** (Isolation Forest sobre `device_health_10s`) | Necesita comparar entre estaciones y semanas de historia |
| Sugerencia de dictamen | **Cloud** | Post-evento, requiere contexto multi-sensor y metadata |
| Resúmenes de incidente (LLM) | **Cloud** (fase 3) | Genera el borrador del reporte PDF para Protección Civil |

---

# REQUERIMIENTO 4 — ESPECIFICACIONES PARA CLAUDE DESIGN Y CLAUDE CODE

## 4.1 Componentes UI (Claude Design ya entregó los 4 mockups — esto es el desglose a componentes)

Los mockups existentes (Consola C4I, Flota Edge, Triage, Multi-Tenant) se descomponen en esta
librería de componentes React. Cada uno con sus estados explícitos:

| Componente | Props/inputs clave | Estados que debe manejar |
|---|---|---|
| `<LiveMap>` (MapLibre GL) | sitios[], evento_activo?, capa_intensidad | normal / alerta-activa (anillos concéntricos animados) / sitio-seleccionado |
| `<AlertBanner>` | magnitud, t_minus_s, pga_max, event_id | countdown activo / expirado / sin-alerta (oculto) |
| `<IncidentTable>` | incidentes[], filtros | live (subscription) / vacío / error de conexión |
| `<WaveformViewer>` | sensor_id, canal, rango_ts, modo | live-streaming / histórico / cargando / sin-datos / pop-up modal (auto al detectar anomalía ★) |
| `<SiteDetailPanel>` | site_id | live / degradado (datos viejos >30 s, marcar "último dato hace X") / offline |
| `<GaugeMetric>` | etiqueta, valor, unidad, umbral | normal / advertencia / crítico |
| `<CabinetCard>` (Flota Edge) | gateway | operativo / degradado / sin-enlace / en-batería |
| `<RelayStatusGrid>` | relés[] | armado / activado / falla / S-D |
| `<ThresholdSlider>` | perfil, T1/T2/T3 | edición / pendiente-de-sync / sincronizado / error |
| `<NotificationCascade>` | canales[], orden | habilitado-por-canal / cascada-preview |
| `<TriageHistoryTable>` | eventos[], filtros fecha/severidad | normal / exportando |
| `<DictamenPanel>` | event_id | preliminar-auto / firmado / exportando-pdf |
| `<QuorumVotesList>` | votos[] | cuórum-cumplido / insuficiente |
| `<TenantSwitcher>` + `<TenantList>` | tenants[] | lógico / dedicado (badge) |
| `<SystemHealthHeader>` | mqtt_rtt, estado_conexión, reloj UTC/CST | conectado / degradado / desconectado |

**Regla de oro para los prompts de frontend:** cada componente debe manejar SIEMPRE sus estados
`loading`, `error`, `empty` y `stale` (dato viejo) — en un sistema de misión crítica, mostrar un
dato congelado como si fuera live es peor que mostrar "sin datos".

## 4.2 Estructura de monorepo (contexto inicial para Claude Code)

**Decisión: monolito modular** (no microservicios). Una persona + Claude Code mantiene UN
deployable de backend; los módulos internos están listos para extraerse después si hace falta.

```
takab/
├── apps/
│   ├── api/                      # FastAPI · monolito modular
│   │   ├── src/takab_api/
│   │   │   ├── main.py
│   │   │   ├── core/             # config, db, security, deps, tenancy (RLS set)
│   │   │   ├── modules/
│   │   │   │   ├── tenants/      # cada módulo: router.py, service.py,
│   │   │   │   ├── sites/        #   models.py, schemas.py, tests/
│   │   │   │   ├── sensors/
│   │   │   │   ├── ingest/       # endpoints backfill S3, presigned URLs
│   │   │   │   ├── incidents/
│   │   │   │   ├── rules/
│   │   │   │   ├── dictamens/
│   │   │   │   ├── notifications/
│   │   │   │   └── telemetry/    # consultas Timescale p/ dashboards
│   │   │   └── ws/               # WebSocket fan-out (live updates al SOC)
│   │   ├── alembic/              # migraciones
│   │   └── pyproject.toml
│   ├── web/                      # React + TypeScript + Vite
│   │   ├── src/
│   │   │   ├── components/       # librería de 4.1
│   │   │   ├── pages/            # console/ fleet/ triage/ tenants/ building/
│   │   │   ├── lib/              # api client, ws client, auth
│   │   │   ├── styles/           # design tokens de Claude Design
│   │   │   └── stores/           # zustand
│   │   └── package.json
│   ├── mobile/                   # React Native (fase V1)
│   └── edge/                     # software del Pi 5
│       ├── takab_ingest/         # cliente SeedLink → bus local
│       ├── takab_dsp/            # features 1s
│       ├── takab_rules/          # motor determinista + máquina de estados
│       ├── takab_gpio/           # WR-1 + relés + botones + LEDs (mínimo, auditable)
│       ├── takab_sync/           # AWS IoT MQTT + cola offline + backfill S3
│       ├── takab_local_api/      # FastAPI local (dashboard edificio + diagnóstico)
│       ├── systemd/              # unidades .service con watchdog
│       └── install.sh            # provisioning de un gabinete nuevo
├── packages/
│   ├── schemas/                  # contratos compartidos (pydantic + JSON Schema → TS types)
│   └── sdk-ts/                   # cliente TS generado de la API (openapi-typescript)
├── infra/
│   ├── terraform/                # IoT Core, SQS, RDS, S3, ECS, CloudFront, Cognito
│   └── docker/
├── docs/
│   ├── adr/                      # Architecture Decision Records (¡cada decisión cerrada!)
│   └── runbooks/
└── .github/workflows/            # CI: lint+test+build por app
```

**Convenciones para todos los prompts a Claude Code** (incluir siempre en el contexto):
Python 3.12, FastAPI + Pydantic v2, SQLAlchemy 2 async, Ruff (lint+format), pytest;
TypeScript estricto, React 18, Vite, TanStack Query, zustand, MapLibre GL; commits
convencionales; cada módulo con tests; ningún secreto hardcodeado (AWS Secrets Manager / .env).

---

# REQUERIMIENTO 5 — PLAN DE ACCIÓN Y BACKLOG

## Fase 1 · MVP Core (alcance: 1 tenant lógico, sirena+estrobo, sin BACnet/CCTV/HSM)

| # | Tarea | Componente | Prioridad | Criterio de aceptación técnico |
|---|---|---|---|---|
| 1.1 | Monorepo + CI + convenciones | infra | Alta | `git clone` → `make dev` levanta api+web+db locales; CI verde en PR |
| 1.2 | Terraform base AWS (IoT Core, RDS, S3, SQS, Cognito, ECS) | infra | Alta | `terraform apply` reproducible desde cero; entornos dev/prod separados |
| 1.3 | Esquema DB v1 + migraciones (script del Req. 2) | api/db | Alta | Alembic aplica limpio; RLS probado con test que intenta cruzar tenants y falla |
| 1.4 | `takab_gpio`: WR-1 contacto seco → relés (con debounce, fail-safe NO/NC por canal) | edge | **Alta** | Cierre de contacto #2 → relé sirena en <100 ms medido con osciloscopio/logic analyzer; botón silencio funciona; sobrevive 1000 ciclos de prueba |
| 1.5 | Ruta hardware paralela SASMEX→sirena (SPOF-02) | edge/hw | **Alta** | Con el Pi apagado, el contacto seco #2 sigue disparando la sirena |
| 1.6 | `takab_ingest`: cliente SeedLink → mosquitto local | edge | Alta | Reconexión automática; lag <1 s sostenido 24 h; cero pérdida en reinicio del Shake |
| 1.7 | `takab_dsp`: features 1 s (PGA, PGV, RMS, STA/LTA) | edge | Alta | Valores validados contra ObsPy de referencia (error <1%) en traza sintética y real |
| 1.8 | `takab_rules`: umbrales T1/T2/T3 + máquina de estados + disparo de relés | edge | Alta | Test de tabla de verdad completo; latencia umbral→relé <1 s; config por archivo firmado |
| 1.9 | `takab_sync`: AWS IoT MQTT + cola offline + reconexión con jitter | edge | Alta | Desconectar WAN 2 h → reconectar: cero pérdida, cero duplicado (verificado por PK) |
| 1.10 | Pipeline nube: IoT Rule → SQS → consumidor → Timescale | cloud | Alta | Ingesta sostenida 20 sitios × 4 canales × 1 msg/s sin lag de cola |
| 1.11 | API REST: sites, sensors, incidents, telemetry queries | api | Alta | OpenAPI generado; p95 <200 ms en consultas de dashboard con datos de 90 días |
| 1.12 | WebSocket fan-out de incidentes y estado | api | Alta | Update de incidente visible en navegador <2 s desde el edge |
| 1.13 | Web: Consola C4I (mapa + tabla incidentes + banner alerta) | web | Alta | Réplica fiel del mockup 1; estados loading/error/stale en todos los componentes |
| 1.14 | Web: detalle de sitio + WaveformViewer histórico | web | Alta | Carga ventana de 10 min de features <1 s; pop-up automático en anomalía |
| 1.15 | Web: Flota Edge (mockup 2) con health real | web | Media | Estados operativo/degradado/sin-enlace calculados de `device_health_10s` |
| 1.16 | Backfill S3 (Thundering Herd capa 4) | edge+cloud | Media | Cola de 6 h se ingiere completa e idempotente |
| 1.17 | Notificaciones email + push web (SNS) | cloud | Media | Alerta crítica → email <10 s |
| 1.18 | Dashboard local del edificio (`takab_local_api`) | edge | Media | Accesible en LAN sin internet; muestra estado, último evento, prueba de sirena |
| 1.19 | Provisioning de gabinete (`install.sh` + fleet provisioning) | edge/infra | Media | Gabinete nuevo operativo en <30 min desde imagen base |
| 1.20 | Simulador de sismo (inyector SeedLink + generador de eventos) | tooling | **Alta** | Permite demo E2E y tests de carga sin sismo real — sin esto no puedes probar nada |

**Hito de salida Fase 1:** demo en vivo con 3 gabinetes reales: prueba SASMEX dispara sirenas y
aparece en el SOC; sismo simulado en 3 estaciones activa quórum; corte de internet no detiene
la protección local.

## Fase 2 · Enterprise Ready

| # | Tarea | Componente | Prioridad | Criterio de aceptación |
|---|---|---|---|---|
| 2.1 | Multi-tenant completo: RLS endurecida + rol gov_operator + visibilidad cruzada | api/db | Alta | Pentest interno de cruce de tenants sin hallazgos |
| 2.2 | Web: Matriz Multi-Tenant (mockup 4) con sync de umbrales al edge firmado (JWT) | web/edge | Alta | Cambio de umbral aplicado en edge <60 s con verificación de firma |
| 2.3 | Quórum «3 nodos» en nube + página Triage (mockup 3) | cloud/web | Alta | Evento sintético en 3 estaciones <5 s → incidente regional; <3 estaciones → no dispara |
| 2.4 | App móvil RN: push FCM/APNs, acuse, estado resumido | mobile | Alta | Push <5 s post-incidente; acuse refleja en SOC |
| 2.5 | WhatsApp Business + SMS (Twilio) + cascada fail-open | cloud | Alta | Cascada API→WA→SMS ejecuta en orden con timeout por canal |
| 2.6 | Reportes PDF de dictamen + export miniSEED | cloud | Media | PDF con métricas, traza, quórum y firma del inspector |
| 2.7 | Tenant dedicado (DB aislada) para clientes que lo exijan | infra | Media | Provisioning de tenant dedicado automatizado por Terraform |
| 2.8 | Observabilidad: OpenTelemetry + CloudWatch + alarmas de flota | infra | Media | Gateway offline >5 min → alerta a operaciones TAKAB |
| 2.9 | Sensor de terreno + referencia compartida entre sitios | edge/api | Media | Relación estructural/terreno visible en detalle del sitio |
| 2.10 | BACnet/IP (actuadores BMS) | edge | Baja | Solo si un contrato lo exige |
| 2.11 | CCTV ONVIF bookmarking | cloud | Baja | Solo si un contrato lo exige |

## Fase 3 · AI Ecosystem

| # | Tarea | Componente | Prioridad | Criterio de aceptación |
|---|---|---|---|---|
| 3.1 | Pipeline de dataset: etiquetado automático SASMEX-confirmado + STEAD | ml | Alta | ≥50k ventanas etiquetadas reproducibles |
| 3.2 | CNN 1D evento/ruido → LiteRT en Pi 5 | ml/edge | Alta | Recall >0.99, falsas alarmas <1/sitio/mes en shadow mode 60 días |
| 3.3 | Health scoring de sensores (Isolation Forest) | ml/cloud | Media | Detecta sensor desacoplado/flojo en <24 h en prueba controlada |
| 3.4 | Sugerencia de dictamen (XGBoost + SHAP) | ml/cloud | Media | Concordancia >85% con dictámenes históricos firmados |
| 3.5 | Resumen LLM del incidente para reporte PDF | ml/cloud | Baja | Borrador aprobado sin edición en >70% de casos |

---

# DECISIONES PENDIENTES QUE BLOQUEAN PROMPTS (responder antes de Fase 1)

1. **T-MINUS countdown (mockup 1):** el WR-1 entrega solo cierre de contacto (booleano), NO
   magnitud ni tiempo de arribo. Opciones: (a) quitar el countdown del MVP; (b) estimarlo en nube
   cruzando el feed público del SSN con la distancia epicentro→sitio (llega tarde para EEW pero
   sirve para contexto); (c) investigar si CIRES ofrece datos enriquecidos bajo convenio.
   **Recomendación: (a) para MVP, (c) en paralelo.**
2. **Magnitud "M 6.8 PRELIMINAR" (mockup 1):** mismo problema. En MVP el banner debe decir
   «ALERTA SASMEX RECIBIDA» sin magnitud, y enriquecerse minutos después con datos del SSN.
3. **NOM-003-SCT del mockup 3:** es de transporte; no aplica. Sustituir por «Lineamientos de
   Protección Civil» genérico hasta definir el marco real con el primer cliente.
4. **Pop-up automático de waveform:** definir el disparador exacto (propuesta: STA/LTA > 3.5
   sostenido 2 s en cualquier estación) para acotar el prompt del frontend.
