# TASKS.md — Backlog ejecutable TAKAB Ailert · Fase 1 (MVP Core)

> Cómo se usa este archivo con Claude Code:
> - Ejecutamos **una tarea a la vez, en orden** (respetando `depende de`).
> - Orden de bloques = **EDGE PRIMERO, luego CLOUD, luego FRONTEND** (`BLUEPRINT-TECNICO-TAKAB.md §0.1, §13`).
> - Por cada tarea: `/write-plan` → `/goal "<acceptance>"` → `/execute-plan` dentro de `/loop`
>   hasta que TODOS los criterios pasen. Ver método en `CLAUDE.md §6`.
> - Marca `[x]` la tarea solo cuando cumpla su **Definition of Done** (`CLAUDE.md §6`).
> - Si un criterio no pasa tras 3 iteraciones del loop: detente y reporta el bloqueo.
> - Cada tarea referencia su Work Package (WP) del blueprint entre corchetes, ej. `[A2]`.

**Estado actual:** ▶ siguiente tarea = **T-1.2**

---

## Bloque A · Fundaciones

### [x] T-1.1 · Monorepo + tooling + CI — **COMPLETA**
- **Componente:** infra / repo
- **Depende de:** nada
- **Objetivo:** estructura de monorepo de `CLAUDE.md §4`, con tooling y CI que corre en cada PR.
- **Criterios de aceptación:**
  - [x] Estructura de carpetas `edge/`, `api/`, `web/`, `shared/{schemas,sdk-ts}`, `infra/`, `db/`,
        `takab-docs/` creada.
  - [x] `api/` arranca FastAPI con un endpoint `/health` que responde `{"status":"ok"}`.
  - [x] `web/` arranca Vite + React + TS estricto con una página vacía que compila.
  - [x] Ruff, ESLint, Prettier configurados; `make lint` y `make test` existen y pasan.
  - [ ] GitHub Actions: workflow que en cada PR corre lint + tests de `api`, `web` y `edge`, en verde.
  - [x] `README.md` raíz explica `make dev` (levanta api + web + Postgres local con Docker).
  - [x] Documentos maestros (`CLAUDE.md`, `BLUEPRINT-TECNICO-TAKAB.md`, `RBAC-TAKAB.md`,
        `TASKS.md`, `USER-STORIES.md`) en `takab-docs/`. `db/schema.sql` presente.
- **Nota:** no rehacer esta tarea; construir encima (`CLAUDE.md §0.3`). El job `edge` de CI
  todavía falta — se agrega en **T-1.2 [A0]**.

---

## Bloque B · EDGE (Raspberry Pi 5) — se construye PRIMERO · Blueprint Fase A

### [ ] T-1.2 · Scaffolding `edge/` + simuladores — **[A0]**
- **Componente:** edge · **Depende de:** T-1.1 · **Prioridad: ALTA**
- **Objetivo:** `edge/` con `uv`, `pyproject.toml`, `supervisor.py`, estructura de módulos
  (`takab_edge/{seedlink,signal,buffer,sasmex,rules,actuators,quorum,cloud,health,config,security}`)
  y **simuladores** de RS4D (feed SeedLink sintético), WR-1 (toggle GPIO) y BACnet.
- **Criterios de aceptación:**
  - [ ] `pytest` verde en CI (nuevo job `edge`) sin hardware físico.
  - [ ] Simuladores permiten levantar el edge completo en dev sin Raspberry Shake ni Pi 5.

### [ ] T-1.3 · `sasmex` — WR-1 (contacto seco) → GPIO — **[A4]**
- **Componente:** edge · **Depende de:** T-1.2 · **Prioridad: ALTA**
- **Criterios:** cierre del contacto → señal de alerta SASMEX activa en <100 ms (medido);
  debounce 50 ms; botón silencio y botón prueba; fail-safe NO/NC configurable por canal;
  1000 ciclos sin fallo; proceso mínimo, sin deps pesadas, arranca <1 s.

### [ ] T-1.4 · Ruta de hardware paralela SASMEX→sirena (SPOF-02)
- **Componente:** edge/hw · **Depende de:** T-1.3 · **Prioridad: ALTA**
- **Criterios:** con el Pi apagado, el contacto sigue disparando la sirena (relé de potencia en
  paralelo). Documentado en runbook.

### [ ] T-1.5 · `seedlink` — cliente SeedLink → bus local — **[A1]**
- **Componente:** edge · **Depende de:** T-1.2
- **Criterios:** cliente SeedLink TCP 18000 al Shake; reconexión con backoff y medición de lag;
  lag <1 s sostenido 24 h; cero pérdida al reiniciar el Shake; consume feed simulado 200 Hz estable.

### [ ] T-1.6 · `signal` — features 1 s (PGA, PGV, RMS, STA/LTA) — **[A2]**
- **Componente:** edge · **Depende de:** T-1.5
- **Criterios:** features + clipping/health_score validados contra ObsPy de referencia
  (error <1%) en traza sintética y real.

### [ ] T-1.7 · `buffer` — ring miniSEED en NVMe — **[A3]**
- **Componente:** edge · **Depende de:** T-1.5
- **Criterios:** ring buffer circular en NVMe con retención 7–14 días (~10–16 GB); extrae la
  ventana miniSEED correcta de un evento confirmado para subir a S3.

### [ ] T-1.8 · `rules` — motor determinista tierizado — **[A5]**
- **Componente:** edge · **Depende de:** T-1.3, T-1.6
- **Criterios:** tabla de verdad completa de los 5 tiers (`normal`/`watch`/`restricted`/
  `evacuate_or_hold`/`manual_only`); umbrales configurables por edificio (PGA/PGV, banda cautela
  y disparo); latencia umbral→decisión <1 s; config por archivo firmado; tests exhaustivos de
  casos borde (clipping, saturación, dropout, doble disparo).

### [ ] T-1.9 · `actuators` — adaptador BACnet/IP completo — **[A6]**
- **Componente:** edge · **Depende de:** T-1.8
- **Criterios:** secuencia sirena + cierre de válvulas de gas + retorno de ascensores/montacargas
  + liberación de retenedores de puerta, cada uno con ACK de ejecución y timestamp (`T+0.42s`, etc.);
  mock de simulación sin hardware BACnet real.

### [ ] T-1.10 · `health` — autodiagnóstico del gabinete — **[A7]**
- **Componente:** edge · **Depende de:** T-1.2
- **Criterios:** snapshots correctos de NTP offset, lag SeedLink, packet loss, estado UPS
  (`RED ELÉCTRICA %`, `RESPALDO Xh Ym`, `EN BATERÍA`), temperatura y estado de actuadores;
  logging por transición de estado + heartbeat periódico (nunca por intervalo continuo).

### [ ] T-1.11 · `cloud` (edge-side) — MQTT mTLS + cola offline — **[A8]**
- **Componente:** edge · **Depende de:** T-1.6, T-1.9, T-1.10
- **Criterios:** mTLS contra AWS IoT Core (QoS 1); cola durable offline con backfill idempotente
  al reconectar; desconectar WAN 2 h → reconectar con backoff+jitter: cero pérdida, cero
  duplicado (verificado por PK/`event_id`); last-will configurado.

### [ ] T-1.12 · `config` + `security` — sync firmada y comandos firmados — **[A9]**
- **Componente:** edge · **Depende de:** T-1.11
- **Criterios:** store local de umbrales/reglas/tenant; sincronización desde la nube vía JWT
  firmado (≤60 s), versionada y reversible; mTLS/X.509 por gateway; verificación de comandos
  remotos firmados con nonce (anti-replay); rechaza comando no firmado o repetido.

### [ ] T-1.13 · `takab_local_api` — dashboard local del edificio
- **Componente:** edge · **Depende de:** T-1.8
- **Criterios:** accesible en LAN sin internet; muestra estado, último evento, prueba de sirena;
  recibe comando de silencio por LAN.

### [ ] T-1.14 · Simulador de sismo + integración edge end-to-end — **[A10]**
- **Componente:** tooling/edge · **Depende de:** T-1.5, T-1.9 · **Prioridad: ALTA**
- **Criterios:** inyector SeedLink + generador de eventos permite demo E2E y tests de carga sin
  sismo real; evento simulado → actuación autónoma completa sin nube.

---

## Bloque C · CLOUD (AWS) — después del edge · Blueprint Fase B

### [ ] T-1.15 · Infra base AWS con Terraform + IoT Core — **[B1]**
- **Componente:** infra · **Depende de:** T-1.1
- **Criterios:** `terraform apply` crea VPC mínima, RDS PostgreSQL (TimescaleDB/PostGIS
  habilitables), bucket S3 (miniSEED/evidencias), cola SQS, User Pool de Cognito, KMS por tenant,
  repos ECR, y un Thing de AWS IoT Core de prueba + policy mínima + regla IoT → SQS. Sin
  credenciales en el código; backend de estado remoto (S3 + DynamoDB lock); `terraform destroy` limpio.

### [ ] T-1.16 · Esquema de base de datos + migraciones — **[B3]**
- **Componente:** api / db · **Depende de:** T-1.15
- **Prerequisito de entorno:** Docker Desktop (Postgres+TimescaleDB+PostGIS vía
  `docker-compose.yml`) y Python 3.12 vía `uv`.
- **Criterios:** migración Alembic inicial reproduce `db/schema.sql` (extensiones, tablas,
  hypertables, índices, RLS default-deny, continuous aggregates 1m/1h); test de aislamiento
  cruzado de tenants (tenant A no ve filas de tenant B); test de visibilidad `gov_operator`
  (`gov_shared` sí, `private` no); test de idempotencia de doble insert por PK.

### [ ] T-1.17 · Pipeline de ingesta: IoT Rule → SQS → Timescale — **[B2]**
- **Componente:** cloud · **Depende de:** T-1.15, T-1.16, T-1.11
- **Criterios:** 20 sitios × 4 canales × 1 msg/s sostenido sin lag de cola; idempotente por PK;
  features 1s → `waveform_features_1s`, eventos confirmados → `incidents` + S3, health → `device_health`.

### [ ] T-1.18 · Autenticación y tenancy (Cognito + JWT + RLS) — **[B8]**
- **Componente:** api / auth · **Depende de:** T-1.15, T-1.16
- **Objetivo:** login OIDC contra Cognito con MFA; el backend extrae claims y setea
  `app.tenant_id`, `app.role`, `app.user_id` por request para RLS (`RBAC-TAKAB.md §5`).
- **Criterios:** grupos de Cognito = los 11 roles; claims custom (`tenant_id`, `role`,
  `site_scope`, `zone_id`, `surface`) en el JWT; dependencia FastAPI valida firma/exp/issuer y
  rechaza tokens inválidos (401); middleware setea variables de sesión Postgres en la
  transacción; endpoint `/me`; tests de autorización por rol (`RBAC-TAKAB.md §2`).

### [ ] T-1.19 · Incident engine + quórum de red — **[B4]**
- **Componente:** cloud · **Depende de:** T-1.17
- **Criterios:** correlación y deduplicación de eventos; corroboración de quórum colaborativo
  (≥3 nodos, ventana 2–5 s) sin bloquear la actuación local ya ejecutada por el edge; ciclo de
  vida completo del incidente (abierto → acusado → cerrado).

### [ ] T-1.20 · Dictamen service (NOM-003) + PDF — **[B5]**
- **Componente:** cloud · **Depende de:** T-1.19
- **Criterios:** dictamen automático preliminar (`NO HABITAR · INSPECCIÓN` /
  `HABITAR · MONITOREO` / `OPERACIÓN NORMAL`) según severidad/PGA + regla de nodos; registro
  NOM-003 inmutable (`ruleSetVersion`, evidencia, notas, `signedBy`), nunca podado por retención;
  exportación PDF + miniSEED por incidente.

### [ ] T-1.21 · Notification orchestrator (cascada + fail-open) — **[B6]**
- **Componente:** cloud · **Depende de:** T-1.19
- **Criterios:** cascada secuencial API Webhook (HMAC) → WhatsApp Business → SMS (≤30 s) →
  correo (DKIM/SPF); en degradado (edge `SIN ENLACE`) dispara todos los canales en paralelo
  (fail-open); alerta crítica → email <10 s.

### [ ] T-1.22 · API REST + GraphQL subscriptions — **[B7]**
- **Componente:** api · **Depende de:** T-1.18
- **Criterios:** REST (FastAPI + Pydantic) para sites/sensors/incidents/telemetry/dictámenes/
  exportación miniSEED; OpenAPI generado; p95 <200 ms en queries de dashboard con 90 días de
  datos; GraphQL con subscriptions sobre WebSocket para incidentes y estado de sitio en vivo
  (update visible en el navegador <2 s desde el edge).

### [ ] T-1.23 · Config sync + command service firmado — **[B9]**
- **Componente:** cloud · **Depende de:** T-1.18
- **Criterios:** publica umbrales/reglas firmados (JWT, ≤60 s) a los edges; comandos remotos de
  actuador firmados con MFA + nonce + rate-limit + ACK de ejecución obligatorio (contraparte
  cloud de **T-1.12**).

### [ ] T-1.24 · Audit/compliance inmutable + billing/metering — **[B10]**
- **Componente:** cloud · **Depende de:** T-1.16
- **Criterios:** `audit_log` inmutable sin poda por retención; medidores por tenant (sitios
  activos, mensajes, GB, incidentes) para facturación.

### [ ] T-1.25 · Backfill por S3 (anti-thundering-herd)
- **Componente:** edge+cloud · **Depende de:** T-1.11, T-1.17
- **Criterios:** cola de 6 h se ingiere completa e idempotente vía S3 + URL pre-firmada.

---

## Bloque D · FRONTEND — sobre la nube existente · Blueprint Fase C

### [ ] T-1.26 · Guards de routing + shell de navegación
- **Componente:** web · **Depende de:** T-1.18
- **Objetivo:** separar el diseño en rutas protegidas por rol (`RBAC-TAKAB.md §7`).
- **Criterios:** rutas `/console`, `/fleet`, `/triage`, `/tenants`, `/building/:siteId` montadas;
  guard por rol bloquea navegación directa por URL (no solo oculta el botón); navegación armada
  según el rol del JWT; estado "sin acceso" implementado; login/logout Cognito end-to-end.

### [ ] T-1.27 · Consola C4I — Live Wall — **[C1]**
- **Componente:** web · **Depende de:** T-1.26, T-1.22
- **Criterios:** réplica fiel del mockup 1 (mapa MapLibre con intensidad MMI, incidentes abiertos
  en vivo vía GraphQL subscription, detalle de sitio con sismograma live y PGA/PGV/NTP
  offset/clipping/packet loss, actuadores BACnet con ACKs, verificación CCTV ONVIF); carga 10 min
  de features <1 s; pop-up automático al detectar anomalía (STA/LTA > 3.5 sostenido 2 s); banner
  MVP "ALERTA SÍSMICA · PROTÉJASE" (sin magnitud ni T-MINUS); estados loading/error/empty/stale
  en todo componente.

### [ ] T-1.28 · Flota Edge — Gabinetes — **[C2]**
- **Componente:** web · **Depende de:** T-1.26
- **Criterios:** inventario de gateways (MQTT lag, SeedLink lag, UPS %, actuadores armados);
  estados `OPERATIVO`/`DEGRADADO`/`SIN ENLACE` calculados de `device_health`; autodiagnóstico
  silencioso visible.

### [ ] T-1.29 · Triage Estructural — Historial — **[C3]**
- **Componente:** web · **Depende de:** T-1.20
- **Criterios:** cumplimiento NOM-003-SCT, historial de eventos, dictamen preliminar, regla de
  quórum con offsets por nodo, exportar miniSEED + PDF.

### [ ] T-1.30 · Matriz Multi-Tenant — Umbrales — **[C4]**
- **Componente:** web · **Depende de:** T-1.23
- **Criterios:** aislamiento visible (lógico vs dedicado), umbrales por tipo de instalación,
  cascada de notificación configurable, sync firmada al edge.

### [ ] T-1.31 · App móvil (fase posterior) — **[C5]**
- **Componente:** mobile · **Depende de:** T-1.22, T-1.26 · **Diferida — no iniciar en Fase 1.**
- **Criterios (referencia futura):** acuse, escalamiento, inspección de campo con
  checklist/fotos/firma, check-in de vida, offline-first.

---

## Hito de salida Fase 1
Demo en vivo con 3 gabinetes: prueba SASMEX dispara actuadores y aparece en el SOC; sismo
simulado en 3 estaciones activa quórum; corte de internet no detiene la protección local.

> Fuera de alcance explícito de este ciclo (T-MINUS, magnitud preliminar, streaming continuo de
> waveform, IA en ruta determinista, mini-ShakeMap, modificar Shake OS): ver
> `BLUEPRINT-TECNICO-TAKAB.md §14`.
