# TASKS.md — Backlog ejecutable TAKAB · Fase 1 (MVP Core)

> Cómo se usa este archivo con Claude Code:
> - Ejecutamos **una tarea a la vez, en orden** (respetando `depende de`).
> - Por cada tarea: `/write-plan` → `/goal "<acceptance>"` → `/execute-plan` dentro de `/loop`
>   hasta que TODOS los criterios pasen. Ver método en `CLAUDE.md §6`.
> - Marca `[x]` la tarea solo cuando cumpla su **Definition of Done** (CLAUDE.md §6).
> - Si un criterio no pasa tras 3 iteraciones del loop: detente y reporta el bloqueo.

**Estado actual:** ▶ siguiente tarea = **T-1.1**

---

## Bloque A · Fundaciones (deben ir primero, en este orden)

### [ ] T-1.1 · Monorepo + tooling + CI
- **Componente:** infra / repo
- **Depende de:** nada
- **Objetivo:** estructura de monorepo del CLAUDE.md §4, con tooling y CI que corre en cada PR.
- **Criterios de aceptación:**
  - [ ] Estructura de carpetas `apps/{api,web,edge}`, `packages/`, `infra/`, `db/`, `docs/` creada.
  - [ ] `apps/api` arranca FastAPI con un endpoint `/health` que responde `{"status":"ok"}`.
  - [ ] `apps/web` arranca Vite + React + TS estricto con una página vacía que compila.
  - [ ] Ruff, ESLint, Prettier configurados; `make lint` y `make test` existen y pasan.
  - [ ] GitHub Actions: workflow que en cada PR corre lint + tests de api y web, en verde.
  - [ ] `README.md` raíz explica `make dev` (levanta api + web + Postgres local con Docker).
  - [ ] Los 4 documentos (`CLAUDE.md`, `FASE-0...`, `RBAC-TAKAB.md`, `TASKS.md`, `USER-STORIES.md`)
        colocados en su ruta. `db/schema.sql` presente.
- **Prompt:** `prompts/PROMPT-01-monorepo.md`

### [ ] T-1.2 · Infra base AWS con Terraform
- **Componente:** infra
- **Depende de:** T-1.1
- **Objetivo:** Terraform reproducible de la base AWS, entornos `dev` y `prod` separados.
- **Criterios de aceptación:**
  - [ ] `terraform apply` crea: VPC mínima, RDS PostgreSQL (con TimescaleDB/PostGIS habilitables),
        bucket S3 (miniSEED/evidencias), cola SQS, User Pool de Cognito, repos ECR.
  - [ ] Sin credenciales en el código; backend de estado remoto (S3 + DynamoDB lock).
  - [ ] `terraform destroy` limpio. Outputs documentados.
  - [ ] AWS IoT Core: un Thing de prueba + policy mínima creados por Terraform.

### [ ] T-1.3 · Esquema de base de datos + migraciones
- **Componente:** api / db
- **Depende de:** T-1.1
- **Prerequisito de entorno:** instalar Docker Desktop (Postgres+TimescaleDB+PostGIS vía
  `docker-compose.yml`) y fijar Python 3.12 vía `uv`. No estaban listos al cerrar T-1.1.
- **Objetivo:** aplicar `db/schema.sql` vía Alembic; RLS funcionando y probada.
- **Criterios de aceptación:**
  - [ ] Migración Alembic inicial reproduce `db/schema.sql` (extensiones, tablas, hypertables,
        índices, RLS, continuous aggregate).
  - [ ] Test: con `app.tenant_id` = A, una query a `incidents` NO devuelve filas del tenant B.
  - [ ] Test: `gov_operator` ve incidentes de tenants `gov_shared` pero no de `private`.
  - [ ] Test de idempotencia: doble insert de un feature con misma PK no duplica.

### [ ] T-1.4 · Autenticación y tenancy (Cognito + JWT + RLS)
- **Componente:** api / auth
- **Depende de:** T-1.2, T-1.3
- **Objetivo:** login OIDC contra Cognito; el backend extrae claims y setea `app.tenant_id`,
  `app.role`, `app.user_id` por request para RLS. (Ver `RBAC-TAKAB.md §5`.)
- **Criterios de aceptación:**
  - [ ] Grupos de Cognito = los 11 roles; claims custom (`tenant_id`, `role`, `site_scope`,
        `zone_id`, `surface`) presentes en el JWT.
  - [ ] Dependencia FastAPI valida JWT (firma + exp + issuer) y rechaza tokens inválidos (401).
  - [ ] Middleware setea las variables de sesión Postgres dentro de la transacción.
  - [ ] Endpoint `/me` devuelve rol, tenant y scope del usuario autenticado.
  - [ ] Tests de autorización por rol (matriz de `RBAC-TAKAB.md §2`).

### [ ] T-1.5 · Guards de routing en el frontend + shell de navegación
- **Componente:** web
- **Depende de:** T-1.4
- **Objetivo:** separar el diseño "revuelto" en rutas protegidas por rol (RBAC-TAKAB.md §7).
- **Criterios de aceptación:**
  - [ ] Rutas `/console`, `/fleet`, `/triage`, `/tenants`, `/building/:siteId` montadas.
  - [ ] Guard por rol: un usuario sin permiso es redirigido y la navegación directa por URL se
        bloquea (no basta ocultar el botón).
  - [ ] La navegación visible se arma según el rol del JWT.
  - [ ] Estado "sin acceso" implementado.
  - [ ] Login/logout con Cognito funcionando end-to-end.

---

## Bloque B · Edge (el gabinete) — se puede empezar en paralelo al Bloque C

### [ ] T-1.6 · `takab_gpio` — WR-1 (contacto seco) → relés
- **Componente:** edge · **Depende de:** T-1.1 · **Prioridad: ALTA**
- **Criterios:** cierre del contacto #2 → relé sirena <100 ms (medido); debounce 50 ms;
  botón silencio y botón prueba; fail-safe NO/NC configurable por canal; 1000 ciclos sin fallo;
  proceso mínimo, sin deps pesadas, arranca <1 s.

### [ ] T-1.7 · Ruta de hardware paralela SASMEX→sirena (SPOF-02)
- **Componente:** edge/hw · **Depende de:** T-1.6 · **Prioridad: ALTA**
- **Criterios:** con el Pi apagado, el contacto #2 sigue disparando la sirena (relé de potencia
  en paralelo). Documentado en runbook.

### [ ] T-1.8 · `takab_ingest` — SeedLink → bus local
- **Componente:** edge · **Depende de:** T-1.1
- **Criterios:** cliente SeedLink TCP al Shake; reconexión automática; lag <1 s sostenido 24 h;
  cero pérdida al reiniciar el Shake; publica ventanas en mosquitto local.

### [ ] T-1.9 · `takab_dsp` — features 1 s (PGA, PGV, RMS, STA/LTA)
- **Componente:** edge · **Depende de:** T-1.8
- **Criterios:** valores validados contra ObsPy de referencia (error <1%) en traza sintética y real.

### [ ] T-1.10 · `takab_rules` — motor determinista + máquina de estados
- **Componente:** edge · **Depende de:** T-1.6, T-1.9
- **Criterios:** tabla de verdad de tiers (normal/watch/restricted/evacuate) completa; latencia
  umbral→relé <1 s; config por archivo firmado; tests exhaustivos.

### [ ] T-1.11 · `takab_sync` — AWS IoT MQTT + cola offline
- **Componente:** edge · **Depende de:** T-1.2, T-1.9
- **Criterios:** mTLS contra IoT Core; desconectar WAN 2 h → reconectar con backoff+jitter:
  cero pérdida, cero duplicado (verificado por PK); last-will configurado.

### [ ] T-1.12 · `takab_local_api` — dashboard local del edificio
- **Componente:** edge · **Depende de:** T-1.10
- **Criterios:** accesible en LAN sin internet; muestra estado, último evento, prueba de sirena;
  recibe comando de silencio LAN.

---

## Bloque C · Cloud + Web

### [ ] T-1.13 · Pipeline de ingesta: IoT Rule → SQS → consumidor → Timescale
- **Componente:** cloud · **Depende de:** T-1.2, T-1.3
- **Criterios:** 20 sitios × 4 canales × 1 msg/s sostenido sin lag de cola; idempotente.

### [ ] T-1.14 · API REST: sites, sensors, incidents, telemetry
- **Componente:** api · **Depende de:** T-1.4
- **Criterios:** OpenAPI generado; p95 <200 ms en queries de dashboard con 90 días de datos.

### [ ] T-1.15 · WebSocket fan-out (incidentes + estado en vivo)
- **Componente:** api · **Depende de:** T-1.14
- **Criterios:** update de incidente visible en el navegador <2 s desde el edge.

### [ ] T-1.16 · Web — Consola C4I (mapa + tabla incidentes + banner)
- **Componente:** web · **Depende de:** T-1.5, T-1.15
- **Criterios:** réplica fiel del mockup 1; estados loading/error/empty/stale en todo componente;
  banner MVP "ALERTA SÍSMICA · PROTÉJASE" (sin magnitud ni T-MINUS).

### [ ] T-1.17 · Web — detalle de sitio + WaveformViewer + pop-up automático
- **Componente:** web · **Depende de:** T-1.16
- **Criterios:** carga 10 min de features <1 s; pop-up automático al detectar anomalía
  (disparador: STA/LTA > 3.5 sostenido 2 s).

### [ ] T-1.18 · Web — Flota Edge (mockup 2) con health real
- **Componente:** web · **Depende de:** T-1.16
- **Criterios:** estados operativo/degradado/sin-enlace calculados de `device_health_10s`.

### [ ] T-1.19 · Backfill por S3 (anti-thundering-herd)
- **Componente:** edge+cloud · **Depende de:** T-1.11, T-1.13
- **Criterios:** cola de 6 h se ingiere completa e idempotente vía S3 + URL pre-firmada.

### [ ] T-1.20 · Notificaciones email + push web
- **Componente:** cloud · **Depende de:** T-1.14
- **Criterios:** alerta crítica → email <10 s.

### [ ] T-1.21 · Simulador de sismo (inyector SeedLink + generador de eventos) · **ALTA**
- **Componente:** tooling · **Depende de:** T-1.8
- **Criterios:** permite demo E2E y tests de carga sin sismo real. Sin esto no se puede probar nada.

---

## Hito de salida Fase 1
Demo en vivo con 3 gabinetes: prueba SASMEX dispara sirenas y aparece en el SOC; sismo simulado
en 3 estaciones activa quórum; corte de internet no detiene la protección local.

> Fases 2 (Enterprise) y 3 (IA): backlog completo en `docs/FASE-0-AUDITORIA-Y-PLAN-TAKAB.md §5`.
