# ESPECIFICACIÓN CANÓNICA · App Móvil TAKAB Ailert — Fase 2

> **Versión:** 2.0 · 2026-07-15 · documento canónico de la app móvil.
> **Supersede** a `PROMPT Especificación.md` (2026-07-11), que queda como histórico. Esta versión
> reconcilia aquella spec contra el estado real del repo al cierre de la **Fase 1.10**
> (red multi-estación, alta de clientes, visibilidad RLS). La matriz completa de reconciliación
> — qué se queda, qué se cambia, qué se elimina y qué se agrega — vive en **§14**.
> **Rol del ejecutor:** este documento define QUÉ construir; el backlog accionable (criterios de
> aceptación por tarea) vive en `takab-docs/TASKS.md · ## Fase 2`. Ante contradicción entre este
> documento y el código existente: detente y repórtala, no la resuelvas en silencio.
> **Idioma:** español para comunicación/UI; inglés para identificadores de código.

**Decisiones ratificadas por Mauricio (2026-07-15):**

| # | Decisión | Resultado |
|---|---|---|
| D1 | Forma del documento | Nueva spec canónica (este archivo); el PROMPT original queda como histórico con banner |
| D2 | Estructura del monorepo | `mobile/` en la raíz + `shared/design-tokens/` (patrón `file:` ya probado con el SDK) |
| D3 | Canvas de diseño | Corregido Y ampliado con artboards nuevos; shots regenerados de forma reproducible |
| D4 | Alcance extra | Entran las 4: pánico quórum-de-2, banner de simulacro, próximo simulacro programado (agenda informativa), superficie móvil para inspector/building_admin |

---

## 0. Contexto del proyecto (estado real al 2026-07-15)

TAKAB Ailert es una plataforma SaaS multi-tenant de alertamiento sísmico temprano, monitoreo
estructural y continuidad operativa post-sismo. Lo desplegado y verificado HOY:

- **Edge (gabinete por edificio):** Raspberry Shake RS4D (**100 sps · 4 canales: EHZ geófono +
  ENZ/ENN/ENE acelerómetro MEMS**) + el cerebro del gabinete.
  **SE CAMBIA vs PROMPT:** el cerebro NO es un Raspberry Pi 5 — es un **Raspberry Pi 4 Model B
  Rev 1.5** con jack 3.5 mm funcional (corrección T-1.68, verificada contra hardware).
  Receptor SASMEX **WR-1 con SOLO el Relevador 2 (Alerta Sísmica Oficial) cableado** al GPIO;
  el Relevador 1 (multi-riesgo) queda sin conectar — la prueba periódica de CIRES no genera
  falsas alertas por construcción. Motor de reglas determinista con **umbral por sitio aplicado
  en vivo** (T-1.71, SASMEX inmune), arbitraje de demandas GPIO bajo RLock, sirena por relé
  (primaria) + **sirena por audio advisory** (jack 3.5 mm, toggle `audio_siren_enabled`),
  comandos firmados HMAC (nonce de un solo uso, TTL corto, comparación constant-time).
- **Modos de prueba del gabinete (garantía server-side para el móvil):** la prueba local de
  actuadores (T-1.67) y el MODO PRUEBA WR-1 (T-1.69, ventana 120 s auto-expirable) **suprimen
  toda publicación a la nube** → sin evento, sin incidente, sin notificación. El teléfono no
  necesita (ni debe tener) lógica para "ignorar pruebas": si hay incidente en la nube, es real.
- **Cloud (AWS):** IoT Core (mTLS X.509), SQS, ECS Fargate, PostgreSQL 16 + TimescaleDB +
  PostGIS, Cognito, S3, Terraform. **Quórum colaborativo ≥3 estaciones con ventana de
  asociación consciente de la distancia** (blueprint §4.5): corrige el evento REGIONAL y las
  notificaciones en la nube y se **muestra** en consola ("CONFIRMADO · N estaciones"), pero
  **JAMÁS gatea la sirena local** (decisión de seguridad ratificada, Fase 1.10).
  Cascada de notificaciones FAIL-OPEN operativa (correo SES real + webhook HMAC real).
- **Frontend web (Consola SOC):** React 18 + TS + Vite, TanStack Query, Zustand, MapLibre,
  SDK tipado `@takab/sdk` contra REST + WS reales. Multi-tenant con RLS default-deny
  (migraciones hasta `0017_visibility_grants`).

La app móvil es el **complemento móvil del SOC**, no un producto independiente: cada dato que
genera alimenta la consola (especialmente Triage Estructural) y cada estado que muestra proviene
de la nube. La reactivación de T-1.31 es esta Fase 2.

### 0.1 Fuentes de verdad (leer ANTES de escribir código)

1. **Design system móvil:** `takab-docs/design/app/` (canvas corregido en esta fase — los
   mockups ya NO contienen los elementos vetados de §2.1). Paleta, tipografía, espaciado,
   radios, componentes y layout por pantalla salen de ahí.
2. **Tokens web existentes:** `web/src/styles/colors_and_type.css`. Verificado 2026-07-15:
   son **idénticos** a los del diseño móvil (`--tk-*`) — la integración es extraerlos a
   `shared/design-tokens/`, no resolver conflictos (§9).
3. **`takab-docs/RBAC-TAKAB.md`** §1/§3/§4/§5: roles canónicos, matriz móvil, reglas de
   actuadores por rol, claims. **`api/src/takab_api/auth/matrix.py`** es el espejo ejecutable.
4. **`db/schema.sql`:** las tablas del móvil ya existen como DDL latente (§5.1) — reutilízalas,
   no las reinventes.
5. **`@takab/sdk`** (`shared/sdk-ts/`): la app NO duplica clientes HTTP/WS; extiende el SDK.
6. **`takab-docs/PLAN-MAESTRO-TAKAB.md`:** gates previos a la fase móvil (§11 GATE-DECISIONS).
7. Este documento gana sobre los mockups y sobre el PROMPT histórico donde contradigan.

---

## 1. Alcance de la Fase 2

**Incluye:**
- App móvil iOS + Android, dos perfiles de UI: **Ocupante** (`occupant`) y **Táctico**
  (`brigadista`, `security_guard`; `inspector` y `building_admin` entran al perfil táctico
  server-driven por `/me.allowed_actions` — D4d, sin pantallas dedicadas en v2.0).
- **21 pantallas**: las 12 del blueprint original corregidas + 4 de acceso/onboarding (0.1–0.4)
  + 3 de tabs del ocupante que el diseño original dejó sin pantalla (1.6 rutas, 1.7 directorio,
  1.8 cuenta) + 1.9 pánico por quórum (D4a) + variante SIMULACRO del modo reposo (D4b).
- Notificaciones push de alta prioridad (Critical Alerts iOS / canal high-priority Android).
- Modo crisis instruction-first, check-in de vida, bloqueo de reingreso.
- Dashboard táctico, control remoto edge con confirmación en 2 pasos, cámara forense con marca
  de agua, formulario de daños, sincronización offline-first, headcount, recepción de dictamen.
- Extensión del `@takab/sdk` (tipos + `LiveSocket` extraído a shared) y del backend: los
  endpoints de §5 sobre el DDL latente + las tablas nuevas mínimas.
- Agenda informativa de simulacros (`drills.scheduled_at`, D4c) — **sin auto-arranque**: el
  principio "LO REAL GANA" del modo simulacro queda intacto.

**NO incluye (fuera de alcance, no lo implementes):**
- IA de ningún tipo (nunca en el camino determinista; en esta fase, en ninguna parte).
- Cuenta regresiva ni magnitud preliminar en tiempo real (§2.1-A — bloqueado).
- App de escritorio, watch, widgets.
- Streaming de forma de onda cruda al teléfono: el dashboard táctico consume **features de 1 s**
  (el mismo canal WS que la consola). No existe canal de waveform hacia clientes (regla de oro 9).
- **SE ELIMINA del alcance:** envío de SMS desde la app (el canal SMS de la cascada sigue siendo
  un stub simulado en el backend; no hay proveedor contratado).
- miniSEED en el teléfono — **SE ELIMINA del mockup 2.5**: el miniSEED sube edge→S3 en eventos
  confirmados y jamás pasa por el móvil.

---

## 2. Principios no negociables (heredados y bloqueados)

Probados en producción; **no se renegocian en la app móvil**:

1. **Autonomía local total del edge.** El teléfono es un espejo y un canal de reporte; jamás es
   prerequisito de ninguna función de seguridad de vida. Con todos los teléfonos apagados, el
   sistema protege igual. Corolario Fase 1.10: el quórum multi-estación corrige el evento
   regional y las notificaciones, **jamás** la actuación local.
2. **Sin IA en el camino determinista de seguridad.**
3. **Logging orientado a eventos**, no por intervalos.
4. **Separación estricta edge/cloud.** La app habla con la nube (REST/WS vía `@takab/sdk` +
   Cognito). **Nunca habla directamente con el gabinete** (ni LAN, ni BLE). Comandos:
   app → cloud → (comando firmado HMAC con nonce/TTL) → edge. El panel LAN del gabinete es una
   superficie separada para el operador in situ, no para esta app.
5. **Evidencia de cumplimiento nunca sujeta a poda de retención:** fotos forenses, reportes de
   daño, check-ins, dictámenes y logs de acciones críticas son evidencia de incidente.
6. **Sin credenciales AWS en el bundle ni en git.** Cognito (User Pool; credenciales efímeras
   scoped si se usa Identity Pool para subida directa).

### 2.1 Correcciones de honestidad (OBLIGATORIAS — ya aplicadas al canvas)

**A. PROHIBIDO: cuenta regresiva "T-MINUS" y magnitud preliminar tipo "M 6.8 PRELIMINAR".**
El WR-1 entrega únicamente un cierre de contacto seco: un booleano. No transporta magnitud,
epicentro ni tiempo de arribo. Mostrar un cronómetro o una magnitud en una pantalla de vida o
muerte sería fabricar datos.

Diseño corregido de las pantallas de crisis (1.2 / 1.3), ya reflejado en el canvas:
- **Instruction-first:** la instrucción gigante ("EVACÚE AHORA" / "REPLIÉGUESE") ES la pantalla.
- Debajo: **T+ transcurrido** desde la recepción de la alerta (`T+04s`, ascendente) — dato real.
- Fuente del evento etiquetada según el payload real del incidente:
  - `sasmex_wr1` → "ALERTA SÍSMICA SASMEX · WR-1". Sin magnitud, sin epicentro, sin tiempo estimado.
  - `local_threshold` (detección local) → puede mostrar PGA instrumental del sitio (dato real
    del RS4D): "PGA 0.15g · REGLAS LOCALES".
  - `local_quorum` → "CONFIRMADO · N estaciones" (el mismo `meta.node_count` del evento que
    muestra el pill de Triage en consola; `corroborated` es hecho del servidor, nunca se
    re-deriva en el cliente).
- La magnitud **solo aparece post-evento** en historial/dictamen, obtenida del catálogo oficial
  vía backend (`GET /catalog/earthquakes`), etiquetada "SSN · dato oficial posterior al evento".
- El componente de crisis se estructura para que, si en el futuro una fuente transporta
  magnitud/ETA por dato (no por contacto seco), el campo se active por feature flag **sin tocar
  el layout**. Flag: `ALERT_SOURCE_CARRIES_ETA = false`, con comentario que remita a esta sección.

**B. PROHIBIDO rotular "HSM" en UI, docs o código.** Los teléfonos no tienen HSM. Lo correcto:
- Llave de firma por operador generada en **Secure Enclave (iOS) / Android Keystore (StrongBox
  si disponible)**, no exportable, registrada vía `POST /me/device-keys` (§5).
- Las acciones críticas del táctico (silenciar sirena, disparo manual, cierre de headcount,
  firma de reportes) se firman con esa llave + JWT de Cognito vigente + nonce del servidor.
  El backend valida la **intención firmada** y registra en `audit_log`.
- El comando hacia el edge sigue el pipeline existente de `POST /sites/{site_id}/commands`:
  **la nube firma el comando ejecutable** (HMAC por gateway, fail-closed) — el teléfono firma
  la intención auditada, nunca el comando.
- En UI y docs: **"firma con llave respaldada por hardware"** (abreviatura UI: "FIRMA HW").

**C. Strings de cumplimiento normativo — jamás hardcodeados.** El antecedente: una norma de
etiquetado de transporte citada por error como marco sísmico (PROHIBIDO citar NOM-003-SCT; ver
`ANALISIS-ARQUITECTURA §2.1 C1` — el marco normativo citable sigue como pregunta abierta #1 y
la consola de producción ya no cita norma alguna, con test que lo veta). Regla para la app:
**toda referencia normativa proviene de configuración del tenant servida por el backend** —
campo `compliance_labels` dentro de `GET /sites/{site_id}/mobile-state`, respaldado por la tabla
nueva `compliance_labels` (§5). Cero literales normativos en el bundle **y en los mockups**.
**SE CAMBIA vs PROMPT:** el endpoint propuesto (`GET /v1/tenants/{id}/compliance-labels`, con prefijo `/v1/`) no se crea:
el API monta en raíz y el dato viaja en `mobile-state` (menos round-trips en plena crisis);
un `GET /tenants/{tenant_id}/compliance-labels` de administración es opcional y se decide en T-2.03.

---

## 3. Stack técnico

| Capa | Decisión | Justificación |
|---|---|---|
| Framework | **React Native 0.7x + TypeScript estricto** | Reutiliza patrones React de la consola y el `@takab/sdk` |
| Toolchain | **Expo SDK (dev client / prebuild, NO Expo Go)** | Critical Alerts iOS y canales Android custom requieren código nativo |
| Estado servidor | TanStack Query (misma versión mayor que web) | Paridad con la consola |
| Estado local | Zustand | Paridad con la consola |
| Navegación | React Navigation (stack + tabs por perfil) | Estándar |
| Storage seguro | Keychain/Keystore vía `expo-secure-store` para tokens y llaves; **SQLite cifrado (SQLCipher u op-sqlite + cifrado) para la cola offline** | §2.1-B y §4.2 |
| Push | FCM (Android) + APNs (iOS); el emisor backend se decide en T-2.00 (§6) | Hoy NO existe infra push |
| Mapas | Ninguno en v2.0 — ninguna pantalla lo exige; no agregar especulativamente | Peso de bundle |
| Cámara | `expo-camera` + composición de marca de agua en pixel (§7 · 2.3) | |
| Monorepo | **`mobile/` en la raíz** (junto a `edge/`, `api/`, `web/`); tokens en **`shared/design-tokens/`**; SDK en `shared/sdk-ts/`. Consumo por dependencia `file:` (patrón ya probado web↔sdk). **SE CAMBIA vs PROMPT:** no se crean `apps/` ni `packages/` — no existen workspaces en el repo (D2) | Convención real del repo |

**Nota Expo/nativo:** documentar en `mobile/README.md` qué módulos requieren prebuild y qué
entitlements requieren aprobación de Apple (Critical Alerts = solicitud explícita: `GATE-STORE`).

---

## 4. Arquitectura de la app

```
mobile/
├── app/                        # rutas (expo-router o react-navigation)
│   ├── (occupant)/             # Perfil 1 · rol occupant
│   └── (brigadista)/           # Perfil 2 · roles brigadista/security_guard
│                               #   (+ inspector/building_admin server-driven, D4d)
├── src/
│   ├── features/
│   │   ├── alert/              # máquina de estados de crisis (§4.1)
│   │   ├── checkin/
│   │   ├── reentry/
│   │   ├── cabinet/            # dashboard táctico + control remoto
│   │   ├── forensics/          # cámara + formulario de daños
│   │   ├── syncqueue/          # cola offline-first (§4.2)
│   │   ├── headcount/
│   │   ├── dictamen/
│   │   ├── panic/              # pánico por quórum-de-2 (D4a)
│   │   └── enrollment/         # alta por código de sitio (0.4)
│   ├── services/
│   │   ├── push/               # registro de token, handlers, canales
│   │   ├── crypto/             # llaves hardware-backed, firma de intención
│   │   └── sdk/                # instancia configurada de @takab/sdk
│   ├── stores/                 # zustand
│   └── ui/                     # componentes que consumen shared/design-tokens
```

### 4.1 Máquina de estados de crisis (núcleo de la app)

Estado global único, determinista, sin IA, dirigido por eventos del backend (WS/push como
despertador + REST como verdad). Estados:

```
IDLE → ALERT_ACTIVE → SHAKING_CONCLUDED → CHECKIN_PENDING → CHECKIN_SENT
                                        ↘ REENTRY_BLOCKED → REENTRY_APPROVED → IDLE
```

Reglas:
- La transición a `ALERT_ACTIVE` toma la pantalla completa (1.2/1.3) y no puede descartarse
  mientras el backend reporte incidente abierto en el sitio del usuario.
- La fase la publica el backend en `GET /sites/{site_id}/mobile-state.phase`
  (`idle | alert_active | shaking_concluded | reentry_blocked | reentry_approved`), derivada del
  incidente y su timeline (`incident_actions`). **El teléfono nunca decide por sí mismo** que el
  movimiento terminó ni que el reingreso procede. El emisor exacto de `shaking_concluded`
  (cierre de ventana de movimiento del edge → ingesta → `incident_actions`) se implementa en
  T-2.03; el contrato del móvil es solo `mobile-state.phase`.
- Si la app estaba cerrada, la push de alta prioridad la despierta y el primer render consulta
  `GET /sites/{site_id}/mobile-state` para reconstruir el estado — la push es despertador,
  **no** fuente de verdad.
- Todo cambio de estado se registra localmente con timestamp monotónico y se sincroniza
  (evidencia de tiempos de reacción, orientado a eventos).
- La instrucción (EVACÚE / REPLIÉGUESE) se resuelve por la **zona registrada del usuario**
  (`user_zone_assignments.zone_id`) contra la política servida por backend
  (`zones.evac_policy: evacuate | shelter` — columna nueva, §5.1). Sin heurísticas locales.
- **Modo prueba = silencio garantizado:** T-1.67/T-1.69 suprimen la publicación a la nube, por
  lo que ninguna prueba de gabinete genera incidente ni push. La app NO implementa lógica de
  "modo prueba" — la garantía es server-side (test de integración en T-2.05 lo fija).

### 4.2 Cola offline-first (compartida por check-ins, reportes, fotos)

- SQLite cifrado. Cada elemento: `{id, type, payload, blobs[], created_at, state}` con
  `state ∈ {pending, uploading, synced, failed}`.
- Subida automática al recuperar conectividad (listener de red + backoff exponencial + jitter).
- Blobs (fotos) suben a S3 mediante **URL prefirmada emitida por backend** (pipeline de
  evidencia existente: `evidence_objects` + presigned; §5) — más simple de auditar que
  credenciales de Identity Pool.
- **Cadena de custodia:** SHA-256 de cada blob calculado en el dispositivo al capturar, incluido
  firmado en el payload del reporte; el backend lo verifica al recibir el blob (columna de hash
  en `evidence_objects`). Discrepancia = rechazo + `audit_log`.
- La cola es visible en UI (2.5) con estado por elemento.
- Nada se borra del dispositivo hasta confirmación `synced` + margen de 24 h.
- El badge de cifrado en UI ("AES-256") solo si es literalmente cierto en la implementación
  elegida — verificar el cifrado real de SQLCipher/alternativa antes de rotular.

---

## 5. Contratos de API (extensiones al backend + SDK)

**SE CAMBIA vs PROMPT:** aquella tabla usaba prefijo `/v1/` — el API real monta TODO en raíz
(`api/src/takab_api/main.py`); estos son los paths canónicos estilo repo. Se reutilizan los
endpoints existentes de incidentes, sitios, dictámenes, comandos, drills, evidencia y catálogo.

| Método y endpoint | Propósito | Respaldo DDL | Roles (acción `matrix.py`) | audit_log |
|---|---|---|---|---|
| `POST/GET/DELETE /me/push-tokens` | registro/rotación de token FCM/APNs ligado a usuario+dispositivo+sitio | **NUEVA** `push_tokens` | superficie móvil (self-service, sin acción de matriz) | sí |
| `POST /me/device-keys` | registro de llave pública respaldada por hardware (§2.1-B) | **NUEVA** `device_keys` | `brigadista`, `security_guard`, `inspector`, `building_admin` | sí |
| `POST /me/enrollment` `{code}` | occupant se enrola a sitio/zona por código | **LATENTE** `site_enrollment_codes` (consume `uses/max_uses/expires_at/active`) + inserta `user_zone_assignments` | autenticado móvil (ver R2) | sí |
| `POST/GET/DELETE /sites/{site_id}/enrollment-codes` | administrar códigos de alta | **LATENTE** `site_enrollment_codes` | acción **nueva `enrollment_manage`**: `building_admin`, `tenant_admin`, `takab_superadmin` | sí |
| `GET /sites/{site_id}/mobile-state` | estado consolidado: `phase`, incidente activo, instrucción por zona, punto de reunión, bloqueo de reingreso, `compliance_labels`, drill activo/próximo, enlaces de salud del sitio | `incidents` + `zones` (+`evac_policy` nueva) + **NUEVAS** `compliance_labels`, `site_assets` + `drills` | superficie móvil con `site_scope` (lectura) | no |
| `POST /incidents/{incident_id}/checkins` | check-in de vida `{status: safe\|need_help, zone_id?, geom?, ts_device}` | **LATENTE** `life_checkins` (append-only) + deltas §5.1 | acción **nueva `checkin_submit`**: `occupant`, `brigadista`, `security_guard`, `building_admin`, `inspector` | delegado sí; propio: la tabla ES la evidencia |
| `GET /incidents/{incident_id}/checkins?scope=me` | reconstruir estado propio al abrir | `life_checkins` | mismos roles (lectura propia) | no |
| `GET /incidents/{incident_id}/roster` | roster asignado + estado de check-in por persona | **LATENTES** `user_zone_assignments` + `user_profiles` (+teléfono, R4) JOIN `life_checkins` | acción **nueva `roster_read`**: `brigadista`, `security_guard`, `building_admin`, `inspector` | sí (lectura de PII) |
| `POST /incidents/{incident_id}/damage-reports` (+`GET` para Triage web) | formulario de daños ligado a evidencias | **NUEVA** `damage_reports` | acción **nueva `damage_report_submit`**: `brigadista`, `security_guard`, `inspector`, `building_admin` | sí |
| `GET /incidents/{incident_id}/evidence` + `POST /evidence/{evidence_id}/download` | **EXISTENTES** — presigned S3; se extienden a roles móviles tácticos + verificación del sha256 declarado en captura | `evidence_objects` | acción **nueva `evidence_upload`** (tácticos) | ya existente |
| `POST /sites/{site_id}/commands` | **EXISTENTE** — se agrega capa de intención: body opcional `intent {key_id, signature, nonce}` validado contra `device_keys`; el pipeline HMAC/nonce/TTL/rate-limit/ack queda INTACTO | `commands` + `device_keys` | acciones **nuevas** según RBAC §4: `siren_silence` (`brigadista`, `security_guard`, `building_admin`), `manual_activate` (`brigadista`, `security_guard`, `inspector`, `building_admin`) | ya existente + hash de intención |
| `POST /sites/{site_id}/manual-activation-votes` (D4a) | pánico occupant: quórum de 2 votos en 30 s → sirena NO-sísmica | **LATENTE** `manual_activation_votes` (índice `site_id+created_at DESC` listo; `consumed` al cumplirse) | acción **nueva `panic_vote`**: `occupant` | sí |
| `GET /sites/{site_id}/drills` | último simulacro + **próximo programado** (D4c) | `drills`/`drill_sites` existentes + columna **nueva `drills.scheduled_at`** (agenda informativa; sin auto-arranque) | superficie móvil (lectura) | no |
| `GET /sites/{site_id}/assets` | rutas de evacuación (PDF/imagen por zona) + punto de reunión + manual, S3 presigned, cacheable offline | **NUEVA** `site_assets` | lectura móvil; gestión reutiliza `manage_fleet` | gestión sí |

Notas transversales:
- `geom` en check-in de ayuda: última posición GPS **solo con permiso otorgado**; alternativa
  siempre disponible: zona asignada. Ver §8 (LFPDPPP).
- `ts_device` viaja junto al `ts_server` asignado al recibir; ambos se persisten (análisis de
  latencias, honestidad de tiempos).
- **Todos** los endpoints nuevos: `tenant_id` + RLS default-deny (patrón de `0017`), políticas
  `<t>_read/_write/_admin`, GRANT explícito a `takab_app`, y migración **idempotente** además
  del `db/schema.sql` consolidado (invariante T-1.45).
- Todo endpoint mutador audita vía el **escritor único** `audit.py` (`audit_async`) — el
  contract-test `test_audit_single_writer.py` veta cualquier otro INSERT.
- El SDK se regenera del OpenAPI (drift gate de CI sobre `src/gen/`).

### 5.1 Deltas de schema (migración `0018`, diseñada en T-2.03)

Columnas que faltan en el DDL latente (verificado contra `db/schema.sql` 2026-07-15):

| Tabla | Delta | Motivo |
|---|---|---|
| `life_checkins` | `+ ts_device timestamptz`, `+ via text CHECK (via IN ('self','delegated')) DEFAULT 'self'`, `+ verified_by uuid` | honestidad de tiempos; check-in delegado del headcount (2.6) distinguible del propio |
| `zones` | `+ evac_policy text CHECK (evac_policy IN ('evacuate','shelter'))` | política por zona para 1.2/1.3 (la zona ya tiene `level_code`; R1) |
| `user_profiles` | `+ phone text` (nullable, con consentimiento) | llamada de un toque en 1.1/2.6 (R4) |
| `drills` | `+ scheduled_at timestamptz` (nullable) | agenda informativa D4c; un drill programado NO arranca solo |
| `evidence_objects` | verificar/añadir columna de sha256 declarado-en-captura | cadena de custodia §4.2 |

Tablas nuevas: `push_tokens`, `device_keys`, `damage_reports`, `compliance_labels`,
`site_assets` — todas con `tenant_id` + RLS default-deny + append/retención según §2.5.

### 5.2 Acciones nuevas en la matriz RBAC

Extender `ACTIONS` + `ROLE_ACTION_MATRIX` en `api/src/takab_api/auth/matrix.py` (los routers
derivan con `roles_with_action()`; el parity test contra `RBAC-TAKAB.md §2` se extiende):
`checkin_submit`, `roster_read`, `damage_report_submit`, `evidence_upload`, `siren_silence`,
`manual_activate`, `enrollment_manage`, `panic_vote`, `dictamen_read` (R7). Los roles móviles
hoy tienen rutas y acciones VACÍAS (default-deny) — estas acciones son su primera superficie.

### 5.3 Estrategia live: WS para tácticos, REST + push para occupant

- **Roles tácticos** (`brigadista`, `security_guard`, `building_admin`, `inspector`) entran al
  WS único `/ws` con **allowlist topic×rol default-deny** (hoy el handshake solo autoriza roles
  de consola C4I): topics mínimos `site_state` (device_health + rule_evaluation),
  `features:<site_id>` (features 1 s) e `incidents`, siempre acotados a `custom:site_scope` y
  validando `custom:surface`. Es la única forma de cumplir la aceptación de 2.1 ("mismo payload
  que la consola, sin transformaciones divergentes") respetando la regla de oro 9.
- **`occupant` queda FUERA del WS**: push como despertador + `GET .../mobile-state` como verdad.
  Razones: escala (N ocupantes × sockets persistentes), batería, y superficie de ataque del
  socket C4I. El check-in del ocupante llega al roster del táctico vía WS (<2 s, aceptación 2.6)
  sin que el ocupante tenga socket.
- La lógica de conexión/reconexión (`LiveSocket`: backoff exponencial 1–30 s + jitter,
  re-subscribe, `lastFrameAt` por topic, cierre 4401 → re-auth) se **extrae de
  `web/src/lib/ws.ts` a `shared/sdk-ts`** para que web y móvil compartan una sola implementación.

---

## 6. Notificaciones push

**Estado real:** hoy NO existe infraestructura push (cero FCM/APNs/token en `api/src`). La
cascada de notificaciones (`python -m takab_api.notify`) es FAIL-OPEN con correo SES real y
webhook HMAC real; SNS se usa SOLO para alarmas de infraestructura (gabinete caído, sensor
mudo), no para notificar usuarios. La push móvil es infraestructura NUEVA (T-2.04) y la
elección de emisor (SNS platform endpoints vs FCM/APNs directo) se decide en T-2.00.

Diseño (se conserva del PROMPT):
- **iOS:** APNs con **Critical Alerts** (`sound.critical`) para alertas sísmicas — se salta No
  Molestar y silencio. Requiere entitlement aprobado por Apple: **`GATE-STORE`** (se solicita
  en T-2.00 por su lead-time). Fallback sin entitlement: `interruption-level: time-sensitive`.
- **Android:** canal dedicado `seismic_alert` con `IMPORTANCE_HIGH`, sonido oficial de alerta
  empaquetado, `setBypassDnd(true)` (requiere acceso a política de notificaciones concedido en
  onboarding — flujo guiado obligatorio, pantalla 0.2).
- Dos clases de push, jamás mezcladas:
  1. `CRISIS` (alerta activa, cambio de fase): máxima prioridad, sonido crítico.
  2. `OPS` (dictamen recibido, sync completada, recordatorio de simulacro, aviso a no
     reportados del headcount): prioridad normal.
- Payload mínimo `{type, site_id, incident_id, phase}` — **sin datos sensibles** (aparece en
  lockscreen). El contenido real se obtiene por API al abrir.
- **La push es best-effort y la cascada es FAIL-OPEN: la protección de vida es la sirena del
  edge, nunca la push** (R5). La app lo comunica así en onboarding — sin promesas falsas.
- Onboarding verifica y re-verifica permisos con pantalla de estado dedicada (0.2): "Su teléfono
  NO recibirá alertas" en rojo si faltan permisos. Producto de seguridad de vida: el estado
  degradado debe ser imposible de ignorar (banner persistente en 1.1/2.1 mientras falten).

---

## 7. Especificación pantalla por pantalla (21 pantallas)

El layout visual sale del canvas corregido en `takab-docs/design/app/`. Directivas heredadas:
Perfil 1 = cero carga cognitiva, un toque, textos gigantes, una decisión por pantalla.
Perfil 2 = conciencia situacional y recopilación forense. Todo componente maneja los 4 estados
obligatorios (`loading / error / empty / stale`) espejando el contrato de `StateFrame` de la
consola (precedencia loading > error > empty > stale > ready; banner "DATOS RETENIDOS · <ts>").

### ACCESO Y ONBOARDING (nuevas — SE AGREGA)

#### 0.1 Login
- Cognito Hosted UI + Authorization Code + PKCE (mismo patrón que la consola). Sesión de
  ocupante de larga vida (refresh en Keychain/Keystore): la app debe alertar sin pedir login en
  plena crisis. Acciones tácticas siempre re-verifican token vigente.
- **Aceptación:** expiración del refresh NO bloquea la pantalla de crisis si hay incidente
  activo cacheado <15 min (se muestra con marca de datos retenidos y se re-autentica al tocar).

#### 0.2 Onboarding de permisos (estado de alertabilidad)
- Checklist con estado real por permiso: notificaciones, bypass de No Molestar (Android) /
  Critical Alerts (iOS), ubicación (opcional, solo para "necesito ayuda").
- Variante degradada en rojo: "Su teléfono NO recibirá alertas" + botón que abre los ajustes.
- Re-verificación en cada arranque y al volver de background; badge persistente si degradado.
- **Aceptación:** revocar el permiso de notificaciones en ajustes del sistema → al volver a la
  app, la pantalla/banner degradado aparece sin reiniciar.

#### 0.3 Aviso de privacidad (LFPDPPP)
- Aviso servido por backend (asset del tenant), consentimiento explícito de GPS registrado
  (fecha + versión del aviso). Accesible desde 0.2 y 1.8.
- **Aceptación:** el check-in "necesito ayuda" sin consentimiento GPS envía zona, nunca `geom`.

#### 0.4 Enrolamiento por código de sitio
- Input de código (`POST /me/enrollment`): valida `site_enrollment_codes` (activo, vigencia,
  usos) y crea `user_zone_assignments` con la zona del código. Resultado: "Enrolado a
  <sitio> · Zona <nombre>".
- **Aceptación:** código expirado/agotado → error claro; código válido → 1.1 muestra el sitio
  y la zona correctos sin re-login (ver R2).

### PERFIL 1 · OCUPANTE (`occupant`)

#### 1.1 Modo reposo
- Banner de estado del edificio: `SEGURO` (verde) / `DEGRADADO` / `SIN ENLACE` — mismos tokens
  y umbrales que Flota Edge en consola; el estado viene de `mobile-state`, nunca se calcula local.
- Su zona y política (`evac_policy`) visibles ("Piso 10 · ZONA REPLIEGUE").
- Directorio de brigadistas de su zona con llamada de un toque (`tel:`) (extracto de 1.7).
- **Próximo simulacro** (`drills.scheduled_at`, D4c) + resultado del último (`GET
  /sites/{site_id}/drills`).
- Variante **SIMULACRO** (D4b): con drill activo, franja ámbar "SIMULACRO EN CURSO — ESTO NO ES
  UNA ALERTA REAL" (espejo del DrillBanner de consola; poll a `mobile-state`/push OPS). Un drill
  JAMÁS dispara las pantallas de crisis (no crea incidente, garantía server-side).
- Enlaces a ruta de evacuación y manual (`GET /sites/{site_id}/assets`, cacheados offline).
- Badge "SASMEX ENLAZADO" solo si el heartbeat del gabinete reporta el enlace WR-1 OK — dato
  real, no decorativo.
- **Aceptación:** con backend normal → verde; al matar la red → último estado conocido con
  "datos de hace X min" (patrón StateFrame), nunca finge tiempo real.

#### 1.2 Crisis · "EVACÚE AHORA" (política de zona: `evacuate`)
- Toma total de pantalla, fondo rojo, disparo por push CRISIS + verificación por API (§4.1).
- Jerarquía corregida (§2.1-A): instrucción gigante → ruta de salida asignada ("Diríjase a la
  escalera norte. No use elevadores.") → `T+` ascendente → etiqueta de fuente real del evento.
- Sonido oficial de alerta en loop mientras `ALERT_ACTIVE` (Critical Alert ya sonó al llegar).
- Sin botones descartables. Sin navegación.
- **Aceptación:** push CRISIS simulada en dev → pantalla <1 s tras despertar; con
  `source: sasmex_wr1` NO se renderiza ningún campo de magnitud/ETA (snapshot test que falla si
  aparecen); `ALERT_SOURCE_CARRIES_ETA` permanece `false`.

#### 1.3 Crisis · "REPLIÉGUESE" (política de zona: `shelter`)
- Idéntica estructura, variante ámbar. Zona de seguridad asignada + advertencia de cristales.
- La selección 1.2 vs 1.3 la hace `zones.evac_policy` del backend. Un mismo edificio puede tener
  ambas activas simultáneamente en distintas zonas.
- **Aceptación:** test parametrizado zona `evacuate`/`shelter` → instrucción correcta.

#### 1.4 Post-sismo · Check-in de vida
- Transición automática al recibir fase `shaking_concluded`.
- Exactamente dos botones gigantes: verde "ESTOY A SALVO" / rojo "NECESITO AYUDA".
- "Necesito ayuda" adjunta última ubicación GPS **si hay consentimiento**; si no, zona asignada.
  Muestra qué se enviará antes de enviar ("UBICACIÓN QUE SE ENVIARÁ").
- Encola en la cola offline (§4.2) — DEBE funcionar sin red y sincronizar después
  (`life_checkins` con `ts_device`).
- Tras enviar: confirmación mínima + paso a `REENTRY_BLOCKED` si aplica.
- **Aceptación:** check-in en modo avión queda `pending` y sincroniza al recuperar red; el
  roster del táctico (2.6) lo refleja vía WS en <2 s con red.

#### 1.5 Post-sismo · Bloqueo de reingreso
- Letrero rojo persistente "Reingreso Prohibido · Evaluación Estructural en curso" + línea de
  tiempo real del incidente (evento registrado → check-in recibido → inspección → **dictamen
  técnico · inspector** → reingreso), alimentada por `incident_actions`.
- Punto de reunión asignado visible (`site_assets`).
- Se libera **únicamente** con la fase `reentry_approved` emitida por el backend cuando el
  dictamen se firma en consola (la firma es del rol `inspector`). Sin override local.
- Strings normativos desde `compliance_labels` (§2.1-C).
- **Aceptación:** ningún camino de código local puede transicionar a `REENTRY_APPROVED` sin
  evento del backend (test).

#### 1.6 Rutas (tab Rutas — SE AGREGA)
- Lista de rutas de evacuación por zona (PDF/imagen de `site_assets`, badge "disponible
  offline") + punto de reunión + manual operativo.
- **Aceptación:** en modo avión las rutas cacheadas abren; las no cacheadas muestran estado
  claro (no spinner infinito).

#### 1.7 Directorio (tab Directorio — SE AGREGA)
- Brigadistas y contactos por zona (roster público del sitio: nombre, rol, zona, `tel:`).
- **Aceptación:** un toque llama; sin datos → estado empty honesto.

#### 1.8 Cuenta (tab Cuenta, compartida con Perfil 2 — SE AGREGA)
- `display_name` (`GET/PUT /me/profile`), rol y zona, estado de permisos (enlace a 0.2), aviso
  de privacidad (0.3), consentimiento GPS revocable, cerrar sesión.
- **Aceptación:** revocar consentimiento GPS aquí → el siguiente "necesito ayuda" envía zona.

#### 1.9 Pánico por quórum-de-2 (D4a — SE AGREGA)
- Botón grande "SOLICITAR ACTIVACIÓN DE ALARMA" (emergencia NO sísmica del edificio). Texto
  claro: requiere confirmación de una segunda persona; NO es alerta sísmica.
- `POST /sites/{site_id}/manual-activation-votes`; estado en vivo "1 de 2 confirmaciones · 30 s".
  Al cumplirse el quórum (2 votos de usuarios distintos en 30 s, RBAC §4), el backend emite el
  comando de sirena por el pipeline existente y marca los votos `consumed`.
- Rate-limit por usuario; todo voto audita.
- **Aceptación:** un solo voto JAMÁS activa (test); dos votos del MISMO usuario JAMÁS activan;
  dos usuarios en ventana → comando emitido + entrada de auditoría.

### PERFIL 2 · TÁCTICO (`brigadista`, `security_guard`; + `inspector`/`building_admin` D4d)

#### 2.1 Dashboard táctico local
- Salud del gabinete en tiempo real (WS `site_state`, frames `device_health`): batería/UPS
  (`battery_pct`, `battery_min_left`, `power_status` — **`unknown`/`null` se muestran "UPS ·
  S/D", jamás 0%**), latencia MQTT (`mqtt_rtt_ms`), offset NTP (`ntp_offset_ms`), lag RS4D
  (`seedlink_lag_s`), temperatura (`cpu_temp_c`), certificado (`cert_days_remaining`) — **los
  mismos campos y umbrales de color que Flota Edge** (paridad de tokens y de payload).
- **Actividad sísmica en vivo = features de 1 s** (`features:<site_id>`: pga_g, pgv_cms, rms,
  stalta, clipping) — la misma tira que consume la consola. **SE CAMBIA vs PROMPT:** no es un
  "sismograma" de forma de onda; no existe canal de waveform hacia clientes. Sensor rotulado
  "RS4D · 100 sps · 4 canales". Si el WS cae: congelar con "SIN ENLACE · último dato HH:MM:SS"
  (staleness 15 s, como consola).
- Checklist de actuadores BMS post-evento (sirenas, válvulas, retenedores, elevadores) con
  estados reales del edge — lo mostrado es el estado del relé recalculado por el arbitraje de
  demandas, no la última orden enviada.
- Accesos rápidos a 2.2.
- **Aceptación:** los valores provienen del mismo payload WS que consume la consola (sin
  transformaciones divergentes); UPS desconocido muestra S/D.

#### 2.2 Control remoto Edge · confirmación en 2 pasos
- Acciones: **silenciar sirena** (= `deactivate` canal `siren`) y **disparo manual**
  (= `activate`). Flujo: (paso 1) checklist de precondiciones con estado real prellenado
  (edificio evacuado, headcount completo — no checkbox ciego) → (paso 2) deslizar para activar.
- Cada acción: intención firmada con llave respaldada por hardware (§2.1-B) + JWT vigente +
  nonce solicitado al backend justo antes del deslizamiento (TTL corto). El backend valida
  contra `device_keys` y construye el comando HMAC por el pipeline existente (rate-limit doble
  60 s, nonce UNIQUE, ack obligatorio `pending→acked/rejected/expired`).
- "Silenciar sirena" es una **retirada de la demanda del canal manual** en el arbitraje del
  edge — si otra demanda activa (alerta vigente) mantiene la sirena, la UI lo explica ("La
  sirena permanece activa por alerta vigente") en lugar de fingir éxito: el resultado real llega
  en el `command_ack` con el estado recalculado del relé.
- Toda acción → `audit_log` con identidad, hash de la firma de intención y nonce.
- Solo roles con la acción correspondiente ven los controles (`siren_silence`,
  `manual_activate`); server-driven por `/me.allowed_actions`.
- **Aceptación:** replay de un nonce es rechazado por backend (test); silenciar durante alerta
  activa NO apaga la sirena y la UI comunica el porqué (ack con estado recalculado).

#### 2.3 Cámara forense integrada
- Captura con marca de agua **horneada en el pixel** (composición sobre el bitmap antes de
  persistir, no overlay de UI ni solo-EXIF): fecha-hora del dispositivo + offset NTP del último
  sync (ambos registrados), coordenadas GPS, **PGA registrado por el gabinete en ese momento**
  (consultado al backend; sin red → "PGA: pendiente de sync" y el valor real se adjunta al
  sincronizar — nunca se inventa), ID del operador táctico. Sello de integridad rotulado
  **"SHA-256"** (§2.1-B: nada de siglas de hardware inexistente).
- Hash SHA-256 del archivo final calculado en captura (§4.2) + metadatos duplicados en JSON
  firmado adjunto al reporte.
- Fotos van a la cola offline; **jamás** a la galería del sistema.
- **Aceptación:** alterar un byte del archivo tras la captura invalida la verificación de hash
  en backend.

#### 2.4 Formulario rápido de daños
- Categorías marcables (daño estructural / no estructural / fuga agua / fuga gas / daño
  eléctrico / personas atrapadas o heridas) con severidad por categoría, ligadas a evidencias
  de 2.3 (`damage_reports` + `evidence_objects`).
- "Personas atrapadas / heridas" = prioridad máxima: el reporte salta al frente de la cola y,
  con red, genera notificación inmediata al SOC (cascada OPS).
- Payload firmado (§2.1-B). Alimenta la pestaña **Triage Estructural** de la consola (T-2.03
  expone el `GET` correspondiente para la web).
- **Aceptación:** un reporte creado en móvil aparece en Triage de la consola con sus evidencias
  y hashes verificados.

#### 2.5 Sincronización asíncrona · offline-first
- UI de la cola (§4.2): elementos con estado, progreso, reintento manual, tamaño pendiente.
- Banner de modo offline con explicación tranquila ("sus capturas y reportes se guardan
  localmente cifrados…").
- **SE ELIMINA vs mockup:** la fila de miniSEED — ese artefacto sube edge→S3 y jamás pasa por
  el teléfono. La cola solo contiene lo que el teléfono produce: fotos, reportes, check-ins
  (incl. delegados), headcount.
- Badge de cifrado solo si es literalmente cierto (§4.2).
- **Aceptación:** ciclo avión→captura→formulario→red→sync automática sin intervención, con
  estados visibles en cada paso.

#### 2.6 Headcount · pase de lista
- Roster asignado (`GET /incidents/{incident_id}/roster`) cruzado con check-ins en tiempo real
  (WS). Contadores: a salvo / necesitan ayuda / no reportados. Filtro "No reportados" por
  defecto con llamada directa de un toque (requiere `user_profiles.phone`, R4).
- Marcación manual "verificado en persona" = check-in **delegado** (`via='delegated'`,
  `verified_by`=táctico), firmado, distinguible en datos del check-in propio del ocupante.
- **SE ELIMINA vs mockup:** el botón de envío masivo de mensajes de texto — no existe ese canal
  (stub simulado). Sustituido por "Notificar a no reportados" = push clase OPS.
- Cierre de headcount (todos contabilizados) es acción firmada — precondición del paso 1 de 2.2.
- **Aceptación:** check-in del ocupante (1.4) actualiza el roster vía WS en <2 s con red.

#### 2.7 Recepción de dictamen de reingreso
- Al firmarse el dictamen en consola (rol `inspector`): push OPS + pantalla con el certificado
  (PDF descargado y cacheado) "Edificio Aprobado para Reingreso", folio, firmante, vigencia.
  Sello de la UI: **"FIRMA DIGITAL · INSPECTOR"** — la magnitud, si aparece en el PDF, viene
  etiquetada "SSN · dato oficial posterior al evento" (§2.1-A).
- El PDF es el mismo artefacto que genera la consola (`POST /incidents/{incident_id}/report` →
  S3 + `evidence_objects`); hoy solo `inspector` y `takab_superadmin` pueden GENERARLO — la
  **lectura** por el táctico requiere la acción nueva `dictamen_read` o entrega por push +
  presigned (decisión R7 en T-2.03). No generes un PDF paralelo.
- Botón "Notificar pisos" dispara la liberación de las pantallas 1.5 (evento backend →
  `reentry_approved` → push CRISIS de cambio de fase; jamás acción local).
- **Aceptación:** flujo consola-firma → push → PDF visible → ocupantes liberados, verificable
  en staging.

---

## 8. Seguridad y privacidad

- **AuthN:** Cognito (mismos User Pools que la consola), Hosted UI + PKCE, refresh seguro en
  Keychain/Keystore. Sesiones de ocupante de larga vida; acciones tácticas re-verifican token.
- **AuthZ — roles canónicos (RBAC-TAKAB.md §1/§3, `matrix.py`):** superficie móvil =
  **`occupant`** (móvil-only), **`brigadista`**, **`security_guard`** (móvil), más
  **`inspector`** y **`building_admin`** (web+móvil, D4d).
  **SE CAMBIA vs PROMPT:** los identificadores `brigade` y `security_lead` que proponía NO
  existen — usar siempre los canónicos (`brigadista`, `security_guard`); romperían `matrix.py`
  y los grupos Cognito.
- **Claims reales:** `custom:role` (DEBE pertenecer a `cognito:groups`), `custom:tenant_id`,
  `custom:site_scope` (CSV o `*`; **default-deny si vacío**), `custom:zone_id`,
  `custom:surface` (`web|mobile|both`). El perfil de UI se deriva del rol; el backend re-valida
  cada acción vía la matriz (nunca confíes en la UI) y `/me` sirve `allowed_actions`.
- **Actuadores por rol (RBAC §4):** `occupant` solo puede iniciar la sirena NO-sísmica por
  **quórum de 2 en 30 s** (1.9); los tácticos usan deslizar-para-activar individual; silenciar =
  `brigadista`/`security_guard`/`building_admin`. **MFA del occupant = decisión #7 del
  PLAN-MAESTRO** (supuesto vigente: sin MFA, compensado con quórum + rate-limit + auditoría) —
  se ratifica en T-2.00 ANTES de codificar.
- **LFPDPPP:** GPS solo con consentimiento explícito registrado (0.3); el check-in de ayuda
  funciona sin GPS (zona). Roster y check-ins son datos personales: RLS estricta, sin exposición
  cross-tenant. Tensión `life_checkins` append-only vs derechos ARCO → minimización (`geom`
  solo en `need_help`), base legal de evidencia de incidente documentada, estrategia de
  pseudonimización post-retención (R3, `GATE-LEGAL`).
- **Transporte:** TLS con certificate pinning contra API/WS + mecanismo de rotación de pins
  documentado.
- **Sin secretos en el bundle.** Config remota por entorno.
- Toda acción crítica móvil → `audit_log` (escritor único): usuario, dispositivo, firma, nonce,
  resultado.

---

## 9. Design system compartido (web + móvil)

1. Crear **`shared/design-tokens/`** (D2): tokens en formato agnóstico (JSON/TS) → exportados
   como (a) CSS variables para la consola y (b) objeto TS para React Native. Consumo por
   dependencia `file:` (como `@takab/sdk`).
2. **Hallazgo que simplifica la tarea:** los tokens del diseño móvil
   (`takab-docs/design/app/colors_and_type.css`) y los de la consola
   (`web/src/styles/colors_and_type.css`) son **idénticos** (`--tk-*`: navy/cyan/semáforo,
   Geist + JetBrains Mono, escala 8pt, radios, motion). La reconciliación
   (`takab-docs/design/DESIGN-TOKENS-RECONCILIATION.md`, se crea en T-2.01) **documenta la
   identidad** — no hay conflictos que arbitrar. La consola migra a consumir el paquete solo
   mediante alias 1:1 **sin cambio visual**.
3. El mapeo etiqueta→color (OPERATIVO→ok, DEGRADADO→warn, SIN ENLACE→crit, severidades de
   incidente) vive hoy en componentes web (`SevTag.tsx`, `STATE_PILL`); el paquete de tokens
   exporta también ese contrato semántico para que ambas plataformas resuelvan igual.
4. Componentes con contrato espejo en móvil: badge de severidad (`SevTag`), pill de enlace
   (`LinkPill`), gauge UPS (`UpsGauge`, honesto con `unknown`), y **`StateFrame`** (4 estados
   obligatorios, precedencia y banner "DATOS RETENIDOS") — misma semántica, mismos umbrales.
5. Tipografía de datos técnicos: JetBrains Mono con `tabular-nums` (`tk-data*`), nunca tracked.

---

## 10. Testing

| Tipo | Alcance | Herramienta |
|---|---|---|
| Unit | Máquina de estados de crisis, cola offline, firma de intención, resolución de instrucción por zona, watermark determinista, quórum de pánico | Jest + RTL (RN) |
| Snapshot de honestidad | 1.2/1.3 con `source: sasmex_wr1` NO contienen magnitud/ETA; strings normativos nunca literales; UPS `unknown` nunca "0%" | Jest snapshot + lint rule custom |
| Autorización | Allowlist topic×rol del WS default-deny (occupant rechazado); parity test de `matrix.py` extendido con las acciones móviles; RLS cross-tenant DEBE fallar | pytest (api) |
| Integración | SDK contra backend en staging: check-ins (incl. delegado), reportes, evidencias con verificación de hash, replay de nonce rechazado, enrolamiento por código | Jest + staging |
| E2E | crisis→check-in→sync; táctico: foto→formulario→sync→consola; dictamen→liberación; pánico 2/30 s | Maestro (preferido) o Detox |
| Offline | Todos los flujos de §4.2 en modo avión | E2E + mocks de red |

Disciplina existente: ESLint+Prettier config del repo; cero warnings; tests verdes antes de
cada commit; sin stubs silenciosos (todo placeholder falla ruidosamente o se reporta).

---

## 11. Marcadores GATE (no auto-verificables en repo)

- **`GATE-DECISIONS`** (T-2.00, ANTES de codificar): decisión #7 del PLAN-MAESTRO (MFA
  occupant); solicitud del entitlement Critical Alerts a Apple (lead-time de semanas); elección
  de emisor push; ratificación de R1–R10 (§14.5).
- **`GATE-STORE`:** entitlement Critical Alerts aprobado; publicación TestFlight/Play Internal;
  bypass DND verificado en dispositivos físicos.
- **`GATE-HW`:** silenciado de sirena end-to-end contra gabinete físico con alerta activa
  (arbitraje de demandas desde móvil); latencia real push→pantalla de crisis en red celular;
  PGA del gabinete estampado en foto forense con evento real o simulado; verificación de que
  los modos de prueba del gabinete (T-1.67/T-1.69) no generan ni push ni pantalla de crisis.
- **`GATE-LEGAL`:** aviso de privacidad LFPDPPP revisado; textos de `compliance_labels`
  validados con el marco normativo correcto (pregunta abierta #1 del ANALISIS).

---

## 12. Convenciones de repo y ejecución

- **Backlog:** vive en `takab-docs/TASKS.md · ## Fase 2` (T-2.00…T-2.14) — fuente única de
  criterios de aceptación por tarea. Este documento no los duplica.
- **Una tarea por sesión** de Claude Code: plan mode → ejecución → Definition of Done (tests +
  lint + build + sin secretos + criterios verificados) antes de cerrar.
- **Commits:** Conventional Commits, autoría única de Mauricio, cero footers de co-autoría de
  IA ni anotaciones de generación automática (CLAUDE.md §0.2).
- Al terminar cada tarea: actualizar el documento de estado de fase en `takab-docs/`.

---

## 13. Qué NO hacer (resumen ejecutivo)

1. PROHIBIDO renderizar cuenta regresiva o magnitud preliminar en tiempo real. Nunca. (§2.1-A)
2. No conectar el teléfono directamente al gabinete edge por ningún canal.
3. No poner IA en ninguna parte de esta fase.
4. No hardcodear strings normativos ni etiquetas de cumplimiento (§2.1-C).
5. No duplicar cliente HTTP/WS fuera de `@takab/sdk` (LiveSocket compartido en shared).
6. No cambiar colores/tokens de la consola en producción como efecto colateral (alias 1:1).
7. No guardar fotos forenses en la galería ni perder la cadena de custodia (hash en captura).
8. PROHIBIDO enviar SMS desde la app o prometerlo en UI: el canal no existe (stub simulado).
9. No subir ni mostrar miniSEED en el teléfono — **SE ELIMINA** todo rastro del mockup 2.5.
10. No usar identificadores de rol no canónicos — **SE CAMBIA:** `brigade`→`brigadista` y `security_lead`→`security_guard`.
11. No inventar rutas con prefijo de versión — **SE CAMBIA:** el PROMPT usaba `/v1/...`; el API
    real monta en raíz (§5).
12. No dejar stubs silenciosos: todo placeholder falla ruidosamente o se reporta como hallazgo.
13. No auto-arrancar simulacros desde la agenda (`scheduled_at` es informativo; "LO REAL GANA").

---

## 14. Matriz de reconciliación vs PROMPT (2026-07-11)

### 14.1 Por sección del PROMPT

| § PROMPT | Veredicto | Detalle |
|---|---|---|
| §0 Contexto | **SE CAMBIA** | Cerebro Pi 4 (no "Pi 5"); WR-1 solo Relevador 2; estado Fase 1.9/1.10 añadido (§0) |
| §0.1 Fuentes | **SE CAMBIA** | + RBAC/matrix.py, db/schema.sql latente, PLAN-MAESTRO gates (§0.1) |
| §1 Alcance | **SE CAMBIA** | 12→21 pantallas; D4; exclusiones nuevas (§1) |
| §2 Principios | **SE QUEDA** | Intactos, + corolario quórum Fase 1.10 |
| §2.1-A/B/C | **SE QUEDA (reforzado)** | Anclados a payloads/pipeline/tablas reales (§2.1) |
| §3 Stack | **SE CAMBIA** | Fila monorepo → D2; push "por decidir" honesto (§3) |
| §4 Arquitectura | **SE CAMBIA** | `mobile/`; carpeta `(brigadista)/`; features nuevas (§4) |
| §4.1 Máquina | **SE CAMBIA** | `mobile-state.phase`; política por ZONA (`zones.evac_policy`); pruebas suprimidas server-side (§4.1) |
| §4.2 Cola | **SE QUEDA** | + anclaje a pipeline de evidencia existente |
| §5 Contratos | **SE REESCRIBE** | Paths reales sin prefijo de versión; DDL latente mapeado; acciones RBAC nuevas (§5) |
| §6 Push | **SE CAMBIA** | Diseño se queda; realidad backend añadida (no hay push hoy; cascada FAIL-OPEN; push best-effort) (§6) |
| §7 Pantallas | **SE CAMBIA** | 12 corregidas + 9 nuevas (§7; detalle en 14.2) |
| §8 Seguridad | **SE CAMBIA** | Roles canónicos; claims reales; RBAC §4; decisión #7 (§8) |
| §9 Tokens | **SE CAMBIA** | Identidad verificada (no hay conflictos); `shared/design-tokens/` (§9) |
| §10 Testing | **SE QUEDA (+)** | + autorización WS/matriz/RLS (§10) |
| §11 GATEs | **SE QUEDA (+)** | + `GATE-DECISIONS`; GATE-HW amplía modos de prueba (§11) |
| §12 Convenciones | **SE CAMBIA** | Backlog único en TASKS.md; orden T-2.00…T-2.14 (§12) |
| §13 No hacer | **SE QUEDA (+)** | + reglas 8–13 (§13) |

### 14.2 Por pantalla

| Pantalla | Veredicto | Cambio clave aplicado al canvas |
|---|---|---|
| 1.1 Reposo | **SE CAMBIA** | + zona/política, variante SIMULACRO, próximo simulacro real (`scheduled_at`), assets cacheados |
| 1.2 Crisis evacúe | **SE CAMBIA** | PROHIBIDO el cronómetro regresivo y la magnitud del mockup → instruction-first + `T+` + fuente etiquetada |
| 1.3 Crisis repliegue | **SE CAMBIA** | Ídem 1.2, variante ámbar por `evac_policy` |
| 1.4 Check-in | **SE QUEDA** | + `ts_device`; ubicación solo con consentimiento |
| 1.5 Bloqueo reingreso | **SE CAMBIA** | Paso "Dictamen técnico · inspector" (firma solo `inspector`); strings desde `compliance_labels` |
| 2.1 Dashboard | **SE CAMBIA** | Features 1 s (no "sismograma"); "100 sps · 4 canales" (SE CAMBIA la ficha "200 Hz · 3 canales"); campos device_health reales; UPS honesto S/D |
| 2.2 Control remoto | **SE CAMBIA** | PROHIBIDO el rótulo "HSM" → "FIRMA HW · NONCE VÁLIDO"; precondiciones con estado real |
| 2.3 Cámara forense | **SE CAMBIA** | PROHIBIDO el sello "HSM" → "SHA-256"; PGA "pendiente de sync" sin red |
| 2.4 Formulario daños | **SE QUEDA** | Respaldo `damage_reports` nuevo; prioridad 911 → cascada OPS |
| 2.5 Sync offline | **SE CAMBIA** | SE ELIMINA la fila miniSEED; badge de cifrado solo si es cierto |
| 2.6 Headcount | **SE CAMBIA** | SE ELIMINA el botón de mensajes de texto masivos → push OPS; check-in delegado distinguible |
| 2.7 Dictamen | **SE CAMBIA** | PROHIBIDO "sello HSM" y la cita NOM-003 del PDF de muestra → firma digital · inspector + marco del tenant; magnitud solo "SSN · posterior al evento" |
| 0.1–0.4, 1.6–1.9, variante simulacro | **SE AGREGA** | Login, permisos, privacidad, enrolamiento, rutas, directorio, cuenta, pánico, simulacro (§7) |

### 14.3 Por endpoint del §5 del PROMPT

| Endpoint PROMPT | Veredicto | Sustituto real |
|---|---|---|
| `POST /v1/mobile/push-tokens` | **SE CAMBIA** | `POST/GET/DELETE /me/push-tokens` (tabla nueva `push_tokens`) |
| `GET /v1/sites/{siteId}/mobile-state` | **SE CAMBIA** | `GET /sites/{site_id}/mobile-state` (raíz, + `phase`, `compliance_labels`, drill, assets) |
| `POST /v1/incidents/{id}/checkins` | **SE CAMBIA** | `POST /incidents/{incident_id}/checkins` sobre `life_checkins` LATENTE + deltas |
| `GET /v1/incidents/{id}/roster` | **SE CAMBIA** | `GET /incidents/{incident_id}/roster` sobre `user_zone_assignments`+`user_profiles` LATENTES |
| `POST /v1/incidents/{id}/damage-reports` | **SE CAMBIA** | `POST /incidents/{incident_id}/damage-reports` (tabla nueva) |
| `POST /v1/incidents/{id}/evidence-uploads` | **SE CAMBIA** | Reutiliza pipeline EXISTENTE de evidencia presigned (`/incidents/{incident_id}/evidence`) |
| `POST /v1/edge-commands` | **SE CAMBIA** | `POST /sites/{site_id}/commands` EXISTENTE + capa de intención `device_keys` |
| `GET /v1/tenants/{id}/compliance-labels` | **SE CAMBIA** | Campo `compliance_labels` en `mobile-state` (tabla nueva; GET admin opcional en T-2.03) |
| *(no estaba)* | **SE AGREGA** | `/me/enrollment`, `/sites/{site_id}/enrollment-codes`, `/sites/{site_id}/manual-activation-votes`, `/sites/{site_id}/drills`, `/sites/{site_id}/assets`, `/me/device-keys` |

### 14.4 Términos vetados (regla de redacción)

Los términos de esta tabla solo pueden aparecer en este documento en líneas que contengan
`PROHIBIDO`, `SE ELIMINA` o `SE CAMBIA` (el check de cierre de fase lo verifica con grep).

| Término | Dónde vivía | Resolución |
|---|---|---|
| PROHIBIDO — cronómetro "T-MINUS" / "T-Minus" | mockups 1.2/1.3, spec-doc*.html | Instruction-first + `T+` ascendente (§2.1-A); canvas corregido |
| PROHIBIDO — "M 6.8" preliminar | mockups 1.2/1.3/2.7, comentario del css de tokens | Magnitud solo post-evento "SSN · dato oficial posterior al evento" |
| PROHIBIDO — rótulo "HSM" | mockups 2.2/2.3/2.7, spec-doc*.html | "Firma con llave respaldada por hardware" / "FIRMA HW" / "SHA-256" (§2.1-B) |
| PROHIBIDO — cita "NOM-003" | PDF de muestra del mockup 2.7 | `compliance_labels` por tenant (§2.1-C); marco citable = pregunta abierta #1 |
| SE CAMBIA — "200 Hz" | mockups 2.1/2.5 | RS4D real: 100 sps × 4 canales |
| SE ELIMINA — "SMS" masivo | mockup 2.6 | Push clase OPS a no reportados (no existe canal de mensajes de texto) |
| SE ELIMINA — miniSEED en el teléfono | mockup 2.5 | Sube edge→S3 en eventos confirmados; jamás pasa por el móvil |
| SE CAMBIA — prefijo "/v1/" | §5 del PROMPT | API real monta en raíz; paths §5 de este doc |
| SE CAMBIA — roles "brigade" / "security_lead" | §4/§8 del PROMPT | Canónicos: `brigadista` / `security_guard` |
| SE CAMBIA — "Pi 5" | §0 del PROMPT (y blueprint desactualizado) | Raspberry Pi 4 Model B Rev 1.5 (T-1.68) |

### 14.5 Riesgos y decisiones abiertas (se ratifican en T-2.00 / se resuelven en T-2.03)

- **R1 · floor policy:** recomendado `zones.evac_policy` (la zona ya tiene `level_code` y está
  cableada a claims/check-ins/enrolamiento; el mockup 1.1 ya habla el idioma de zonas).
  Alternativa `building_floors` solo si una zona ≠ un piso en clientes reales.
- **R2 · enrolamiento vs site_scope default-deny:** `POST /me/enrollment` debe (a) escribir
  claims en Cognito vía admin API (poder nuevo del backend) o (b) resolver el scope efectivo
  desde `user_zone_assignments` por request para superficie móvil (sin tocar claims; diverge
  del modelo actual). Elegir explícitamente en T-2.00; la recomendación inicial es (b) con
  cache corto, porque no acopla el enrolamiento a la consistencia eventual de Cognito.
- **R3 · LFPDPPP vs append-only:** `life_checkins` prohíbe UPDATE/DELETE por trigger y `geom`
  es PII → minimización (geom solo en `need_help`), base legal de evidencia de incidente, y
  pseudonimización post-retención vía proceso de migración. `GATE-LEGAL`.
- **R4 · teléfonos del roster:** `user_profiles` no tiene teléfono; la llamada de un toque exige
  la columna nueva (PII + consentimiento) o un directorio administrado por `building_admin`.
- **R5 · push best-effort:** la cascada es FAIL-OPEN y la push no es garantía de entrega; la
  spec y el onboarding lo comunican — la vida la protege la sirena del edge.
- **R6 · WS móvil:** tokens móviles de larga vida sobre el socket C4I → allowlist topic×rol
  default-deny + check de `custom:surface` + `site_scope`; `occupant` fuera del WS.
- **R7 · lectura del dictamen por el táctico:** `export`/`generate_report` no incluyen
  `brigadista` → acción nueva `dictamen_read` o entrega push+presigned. Decidir en T-2.03.
- **R8 · spec-doc*.html:** derivan del PROMPT y ya se corrigieron; llevan banner "derivado — no
  editar a mano". Evaluar deprecarlos cuando la spec v2 tenga su propio export.
- **R9 · estructura:** decidido D2 (`mobile/` + `shared/design-tokens/`); no introducir
  workspaces en esta fase.
- **R10 · entitlement Critical Alerts:** lead-time de Apple ⇒ se solicita en T-2.00; fallback
  `time-sensitive` ya diseñado (§6).
