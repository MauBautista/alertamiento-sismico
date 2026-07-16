# TAKAB Ailert — Modelo de Control de Acceso (RBAC)
**Versión 1.0 · Fuente de verdad de roles, permisos y superficies**

> Este documento es el contexto base para todos los prompts de autenticación, autorización,
> routing y diseño-por-perfil. Toda decisión aquí está cerrada salvo lo marcado como PENDIENTE.
> Decisiones incorporadas de las sesiones de descubrimiento y del blueprint de app móvil.

---

## 1. Roles del sistema (10)

> [PLAN-MAESTRO-01] El encabezado decía "(11)" pero esta lista canónica siempre enumeró **10**
> (2 internos + 7 de tenant + 1 gobierno) — también en el snapshot de junio. Las **identidades
> máquina** (certificado X.509 por gateway, clientes M2M `client_credentials`, rol de DB
> `takab_ingest`) son identidades de servicio, **no roles RBAC**, y viven en blueprint §8 y
> schema §0/§8. `[SUPUESTO — confirmar/override: si faltaba un 11º rol humano, añadirlo aquí.]`

### Internos de TAKAB
| Rol | Descripción | Superficie primaria |
|---|---|---|
| `takab_superadmin` | Dueño de la plataforma. Gestiona tenants. Ve todo. | Web |
| `takab_support` | Operadores técnicos de TAKAB. Mantenimiento y diagnóstico de flota. | Web |

### Por tenant (cliente)
| Rol | Descripción | Superficie primaria |
|---|---|---|
| `tenant_admin` | Administra su organización: sitios, usuarios, umbrales. | Web |
| `soc_operator` | Operador de centro de monitoreo 24/7. **Puede ser servicio TAKAB o rol del propio tenant** — mismo rol, distinto alcance según a qué tenant pertenece el usuario. | Web |
| `inspector` | Ingeniero estructural. Firma dictámenes de reingreso. | Web + Móvil |
| `building_admin` | Responsable de un edificio específico. | Web + Móvil |
| `brigadista` | Personal de respuesta en campo. | **Móvil** (web fase posterior) |
| `security_guard` | Seguridad/vigilancia del inmueble. | Móvil |
| `occupant` | Ocupante común del edificio. Rol más numeroso, menor privilegio. | **Móvil only** |

### Gobierno
| Rol | Descripción | Superficie primaria |
|---|---|---|
| `gov_operator` | Protección Civil. Visibilidad cruzada **solo** de tenants marcados `visibility = 'gov_shared'`. | Web |

---

## 2. Matriz de acceso · SOC Web

| Rol | Consola C4I | Flota Edge | Triage | Multi-Tenant | Dash Edificio | Alcance de datos |
|---|---|---|---|---|---|---|
| `takab_superadmin` | Total | Total | Total | Total | Total | Toda la plataforma |
| `takab_support` | Lectura | **Total** | Lectura | Lectura | Lectura | Todos los tenants |
| `tenant_admin` | Lectura + ack | Lectura | Lectura | Solo sus umbrales | Total | Su tenant |
| `soc_operator` | **Total** | Lectura | Lectura + crear | — | Lectura | Su tenant |
| `gov_operator` | Lectura + ack | Lectura | Lectura + export | — | Lectura | Tenants `gov_shared` |
| `inspector` | Lectura | — | **Total** (firma dictamen) | — | Lectura | Sitios asignados |
| `building_admin` | Lectura (su sitio) | — | Lectura (su sitio) | — | **Total** | Su(s) sitio(s) |
| `brigadista` | — | — | — | — | — | (móvil en MVP) |
| `security_guard` | — | — | — | — | — | (móvil) |
| `occupant` | — | — | — | — | — | (móvil only) |

**Notas:**
- "Total" en Consola C4I incluye: acuse, solicitar dictamen técnico, reubicar epicentro.
- `gov_operator`: **solo lectura + acuse**. NO puede silenciar ni probar actuadores de inmuebles
  ajenos (decisión cerrada — controlar la sirena de un tercero es inaceptable).
  [ANALISIS-00] La celda de Triage decía "Total", lo que contradecía esta misma nota (un "Total"
  en Triage implicaría crear/firmar); se corrigió a **Lectura + export** (exportar miniSEED/PDF
  de evidencia sí es coherente con coordinar respuesta). A nivel de datos, RLS solo le da
  SELECT sobre tenants `gov_shared`; su único write es el acuse vía función dedicada
  (`gov_ack_incident`, ver `db/schema.sql §8`).
- `building_admin`: **sí puede ejecutar prueba de sirena** en su sitio; cada prueba queda en
  `audit_log` con su firma (`actor = user:{uuid}`, `verb = siren_test`).
- `soc_operator`: el alcance lo determina el `tenant_id` del usuario. Un operador empleado por
  TAKAB que presta servicio a un cliente se modela como usuario perteneciente a ese tenant.
- **[DECISION 2026-07-09 · T-1.32] La celda "Total" de `takab_support` en Flota Edge es de
  LECTURA, no de escritura.** Al introducir la acción `manage_fleet` (alta/edición/retiro de
  sitios, gabinetes y sensores), soporte **no** la recibe: solo `takab_superadmin` y
  `tenant_admin`. Motivo: mover la ubicación de una estación reencuadra la ventana de asociación
  del quórum (`|Δt| ≤ dist/v_P + margen`, blueprint §4.5), y eso es un acto de dueño del tenant,
  no de soporte. La verdad ejecutable vive en `api/src/takab_api/auth/matrix.py`; el test
  `tests/auth/test_matrix.py::test_manage_fleet_excludes_takab_support` la ancla.
- **[DECISION 2026-07-10 · T-1.48] Acciones nuevas de la Consola C4I (extensión de §2,
  no listadas en la matriz original):**
  - `relocate_epicenter` (botón REUBICAR EPICENTRO) = `takab_superadmin`, `tenant_admin`,
    `soc_operator`. Reescribe un dato de RED compartido (`seismic_events.epicenter`, vía
    función SECURITY DEFINER `relocate_incident_epicenter` con el punto previo preservado en
    `meta.manual_override`): acto de operador del tenant. Ni gov (solo lectura+acuse) ni
    inspector (juzga el dictamen, no edita la física del evento).
  - `request_dictamen` (botón SOLICITAR DICTAMEN TÉCNICO) = los mismos tres. Es
    `ack_incident` MENOS `gov_operator`: la política RLS `actions_insert` le impide a gov
    insertar en `incident_actions`, y concederle la acción pintaría un botón que siempre
    da 403 (regla de oro 7).
  Anclas: `tests/auth/test_matrix.py::test_relocate_epicenter_is_tenant_operator_action` y
  `::test_request_dictamen_excludes_gov`.
- **[DECISION 2026-07-12 · T-1.57] `read_audit` (GET /audit, extensión de §2):** lectura
  PURA del audit trail = `takab_superadmin`, `takab_support` (operación de plataforma),
  `tenant_admin` (su tenant) y `gov_operator` (evidencia de protección civil). La RLS
  `audit_read` acota QUÉ filas (tenant propio o interno; `tenant_id NULL` = plataforma,
  solo internos); la acción decide QUIÉN entra al endpoint. Operadores/inspectores no la
  reciben: ellos GENERAN auditoría, no la supervisan. Escritura: inexistente por diseño
  (único escritor `takab_api.audit`, tabla append-only). Ancla:
  `tests/auth/test_matrix.py::test_read_audit_is_read_only_oversight`.
- **[DECISION 2026-07-12 · T-1.59] `self_test` (autodiagnóstico del gabinete, extensión de
  §2):** mismo círculo que `siren_test` — `takab_superadmin`, `tenant_admin`,
  `building_admin` (acción de DUEÑO del sitio: pulsa relés de gas/puertas con readback;
  la sirena jamás suena). `soc_operator` DENEGADO: opera incidentes, no mantenimiento del
  gabinete. Viaja por el MISMO envelope firmado del Command Service (canal lógico
  `system`, cruce `self_test ⇔ system` forzado por el router). Ancla:
  `tests/auth/test_matrix.py::test_self_test_is_owner_maintenance_action`.
- **[DECISION 2026-07-12 · T-1.60] `drill_start` (simulacro institucional, extensión de
  §2):** acto ADMINISTRATIVO del tenant = `takab_superadmin`, `tenant_admin` (banner
  NO-real + voceo en N sitios vía `POST /drills`; cero relés — jamás via el endpoint
  público de comandos). La LECTURA del registro (`GET /drills`) es de CONSOLA: gov lo ve
  como evidencia para Protección Civil (RLS `drills_read` con `app_gov_can_see`), sin
  escribir. Un SASMEX real o un tier ≥ restricted ABORTAN el drill en el edge. Ancla:
  `tests/auth/test_matrix.py::test_drill_start_is_institutional_admin_action`.

---

## 3. Matriz de acceso · App Móvil

| Función móvil | `occupant` | `brigadista` | `security_guard` | `inspector` | `building_admin` |
|---|---|---|---|---|---|
| Estado del edificio (verde/alerta) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Directorio emergencia / rutas evacuación | ✅ | ✅ | ✅ | ✅ | ✅ |
| Pantalla de crisis + instrucción por piso | ✅ | ✅ | ✅ | ✅ | ✅ |
| Check-in de vida (a salvo / necesito ayuda) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Dashboard táctico (salud gabinete + actuadores) | — | ✅ | ✅ | Lectura | ✅ |
| **Silenciar** sirena local | — | ✅ | ✅ | — | ✅ |
| **Activar** sirena manual (no sísmica) | ✅ *(quórum 2 ocupantes)* | ✅ *(individual)* | ✅ *(individual)* | ✅ *(individual)* | ✅ *(individual)* |
| Cámara forense (watermark PGA/GPS/hora/ID) | — | ✅ | ✅ | ✅ | — |
| Formulario de triage de daños | — | ✅ | ✅ | ✅ (firma) | — |
| Headcount / pase de lista | — | ✅ | ✅ | — | ✅ |
| Recepción de dictamen de reingreso | Solo aviso "reingreso permitido" | ✅ (PDF) | ✅ (PDF) | ✅ (lo emite) | ✅ (PDF) |

---

## 4. Reglas críticas de actuadores (seguridad)

### 4.1 Activación manual de sirena por no-sismo
- **`occupant`:** requiere **quórum de 2 ocupantes** — dos activaciones independientes en el mismo
  `site_id` dentro de una ventana de **30 s**. Evita pánico/abuso de un solo usuario.
  La primera activación queda "pendiente" y notifica; la segunda confirma y dispara.
- **`brigadista` / `security_guard` / `inspector` / `building_admin`:** **deslizar-para-activar
  individual**, sin segundo confirmante.
- Toda activación manual → `incident_actions` + `audit_log` con ID, GPS y timestamp.

### 4.2 Silenciar sirena
- Roles con permiso: `brigadista`, `security_guard`, `building_admin` (y superiores TAKAB).
- **Ruta del comando:** la app intenta **LAN primero** (`takab_local_api` del gabinete), pero
  **la nube es obligatoria como camino garantizado** — el brigadista puede estar en LTE sin
  acceso a la LAN del edificio. Flujo nube: `app → AWS IoT Core (comando firmado) → gateway`.
- **Limitación técnica documentada (ver blueprint §4.7 / FASE-0 SPOF-02 en `archive/`):** el silencio por software actúa sobre el
  **patrón de sirena que ejecuta el Pi** tras el evento (los minutos que realmente suenan).
  NO puede silenciar el pulso inicial breve de la rama de hardware paralela SASMEX→sirena
  mientras SASMEX mantenga el contacto cerrado. En la práctica esto cubre >95% del tiempo audible.

### 4.3 Endurecimiento del control de actuadores por nube ⚠️
Como ahora se permite **activar** y **silenciar** actuadores desde un teléfono por internet, este
camino es la superficie más sensible del sistema. Requisitos no negociables:
1. **Comando firmado** (HMAC/JWT corto) verificado por el gateway antes de ejecutar.
2. **MFA** obligatorio en el login de roles que pueden activar/silenciar actuadores.
   **[RESUELTO 2026-07-15 · T-2.00, decisión de Mauricio]** (era `[SUPUESTO #7 plan-maestro]`):
   `occupant` con **login simple SIN MFA obligatorio y MFA OPCIONAL** (opt-in TOTP desde la
   pantalla Cuenta de la app). Implementación: **pool de Cognito separado para ocupantes** con
   `mfa_configuration = OPTIONAL` — Cognito no permite MFA por grupo, y poner el pool único en
   OPTIONAL dejaría a un brigadista declinar su TOTP (ver `takab-docs/specs/cognito-pool-v1.md`
   §5.2). El pool táctico/web queda `ON` intacto ⇒ este requisito #2 sigue garantizado para
   todo rol con actuadores. Compensaciones del perfil sin MFA: quórum de 2, rate-limit por
   usuario y sitio, auditoría con ID (+GPS solo con consentimiento) y enrolamiento por código
   acotado al sitio. El **geofence del voto pasa a best-effort**: un voto CON GPS claramente
   fuera del radio del sitio se descarta; sin GPS (permiso denegado — LFPDPPP lo hace opcional)
   el voto cuenta, porque un gate duro por GPS sería inexigible.
3. **Rate-limit** por usuario y por sitio (evita activación repetida).
4. **Idempotencia + nonce** (un comando capturado no puede reenviarse).
5. **Confirmación de ejecución** del gateway de vuelta a la app (`ack` con estado real del relé).

---

## 5. Mapeo a AWS Cognito y claims del JWT

### 5.1 Grupos de Cognito (uno por rol)
```
takab_superadmin · takab_support · tenant_admin · soc_operator · gov_operator
inspector · building_admin · brigadista · security_guard · occupant
```

### 5.2 Claims del JWT (custom attributes + token claims)
```json
{
  "sub": "uuid-del-usuario",
  "cognito:groups": ["brigadista"],
  "custom:tenant_id": "uuid-del-tenant",
  "custom:role": "brigadista",
  "custom:site_scope": ["site-uuid-1", "site-uuid-2"],   // sitios asignados; "*" = todo el tenant
  "custom:zone_id": "zone-uuid",                          // piso del ocupante (para instrucción binaria)
  "custom:surface": "mobile"                              // 'web' | 'mobile' | 'both'
}
```

> **[ANALISIS-00] Semántica de `site_scope` corregida a default-deny:** antes decía
> "vacío = todo el tenant", es decir, un usuario creado SIN asignación heredaba acceso a todos
> los sitios (default-allow). Regla nueva: **vacío o ausente = SIN acceso a sitios**; el alcance
> de tenant completo se otorga explícitamente con `"*"` (roles admin/soc). Nota de diseño: si un
> usuario acumula muchos sitios, no inflar el JWT — resolver el alcance server-side contra
> `user_zone_assignments` y dejar `"*"`/lista corta en el claim.

### 5.3 Propagación a RLS (PostgreSQL)
Cada request de la API setea, dentro de la transacción:
```sql
SET LOCAL app.tenant_id = '{custom:tenant_id}';
SET LOCAL app.role      = '{custom:role}';
SET LOCAL app.user_id   = '{sub}';
```
Las políticas RLS (definidas en el esquema de Fase 0) usan estos valores. El rol `gov_operator`
activa la cláusula de visibilidad cruzada solo para tenants `visibility = 'gov_shared'`.

---

## 6. Tablas nuevas que exige este modelo

> [ANALISIS-00] Snippets ilustrativos — la fuente de verdad del DDL es `db/schema.sql`, que
> además añade `tenant_id` a `manual_activation_votes` y `life_checkins` (regla de oro 5), el
> índice `(site_id, created_at)` para la ventana de 30 s, y append-only en `life_checkins`.

```sql
-- Asignación usuario ↔ zona/piso (para instrucción binaria EVACÚE vs REPLIÉGUESE)
CREATE TABLE user_zone_assignments (
  user_id    uuid NOT NULL,                 -- = Cognito sub
  tenant_id  uuid NOT NULL REFERENCES tenants,
  site_id    uuid NOT NULL REFERENCES sites,
  zone_id    uuid REFERENCES zones,
  role       text NOT NULL,
  assigned_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, site_id)
);

-- Auto-registro de ocupantes por código de edificio (QR/PIN)
CREATE TABLE site_enrollment_codes (
  code        text PRIMARY KEY,             -- impreso como QR/PIN en el edificio
  tenant_id   uuid NOT NULL REFERENCES tenants,
  site_id     uuid NOT NULL REFERENCES sites,
  zone_id     uuid REFERENCES zones,        -- opcional: código por piso
  grants_role text NOT NULL DEFAULT 'occupant'
              CHECK (grants_role IN ('occupant')),  -- solo ocupantes por auto-registro
  expires_at  timestamptz,
  max_uses    int,
  uses        int NOT NULL DEFAULT 0,
  active      boolean NOT NULL DEFAULT true
);

-- Quórum de activación manual de sirena por ocupantes (ventana 30 s)
CREATE TABLE manual_activation_votes (
  vote_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id    uuid NOT NULL REFERENCES sites,
  user_id    uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  consumed   boolean NOT NULL DEFAULT false
);

-- Check-in de vida post-sismo
CREATE TABLE life_checkins (
  checkin_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid REFERENCES incidents,
  user_id    uuid NOT NULL,
  site_id    uuid NOT NULL REFERENCES sites,
  status     text NOT NULL CHECK (status IN ('safe','need_help')),
  geom       geography(Point,4326),
  zone_id    uuid REFERENCES zones,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

**Registro de ocupante (auto-registro):** el usuario escanea el QR / teclea el PIN del edificio →
la app valida contra `site_enrollment_codes` → Cognito crea el usuario en el grupo `occupant` con
`tenant_id`, `site_id` y `zone_id` heredados del código. Sin carga manual.

---

## 7. Superficies de diseño a separar (el "diseño revuelto")

Los 4 mockups web + el blueprint móvil se reorganizan en estas rutas, cada una protegida por rol:

**Web (`web/`):**
| Ruta | Página (mockup) | Roles con acceso |
|---|---|---|
| `/console` | Consola C4I (1) | superadmin, support, tenant_admin, soc_operator, gov_operator, inspector, building_admin |
| `/fleet` | Flota Edge (2) | superadmin, support, tenant_admin, soc_operator, gov_operator, building_admin |
| `/triage` | Triage (3) | superadmin, support, tenant_admin, soc_operator, gov_operator, inspector, building_admin |
| `/tenants` | Multi-Tenant (4) | superadmin, support(lectura), tenant_admin(solo suyo) |
| `/building/:siteId` | Dash Edificio | tenant_admin, building_admin, +lectura otros |

**Móvil (`mobile/` — fase posterior, ver `TASKS.md` T-1.31):**
| Stack de navegación | Pantallas | Roles |
|---|---|---|
| Ocupante | Reposo · Crisis · Check-in | `occupant` (y todos como base) |
| Táctico | Dashboard gabinete · Control Edge · Triage cámara · Headcount · Dictamen | `brigadista`, `security_guard`, `inspector`, `building_admin` |

Cada pantalla/ruta debe manejar el estado **"sin acceso"** (no solo ocultar el botón: el guard
del router bloquea la navegación directa por URL/deep-link).

---

## 8. PENDIENTES (no bloquean RBAC, sí bloquean otros prompts)

Heredados de Fase 0, siguen abiertos:
1. **T-MINUS countdown** (web y app de ocupante): el WR-1 no entrega tiempo de arribo. MVP muestra
   "ALERTA SÍSMICA · PROTÉJASE" sin número. Pendiente investigar datos enriquecidos CIRES/SSN.
2. **Magnitud preliminar "M 6.8":** mismo origen. MVP: "ALERTA SASMEX RECIBIDA" sin magnitud.
3. **Marco normativo de cumplimiento (mockup Triage decía "NOM-003-SCT"): SIGUE PENDIENTE.**
   [ANALISIS-00] La edición anterior lo daba por "confirmado por BLUEPRINT §9", pero esa
   confirmación era circular (el blueprint solo lo afirmaba) y la norma citada es de etiquetado
   de materiales peligrosos en transporte — FASE-0 ya lo había descartado. La regla operativa
   (auditoría, evidencia y dictámenes inmutables, nunca podados) es requisito TAKAB y NO cambia;
   el marco legal citable se define con el primer cliente/abogado. Ver blueprint §9 y
   `ANALISIS-ARQUITECTURA-TAKAB.md` pregunta abierta #1.
4. **Disparador del pop-up automático de waveform:** propuesta STA/LTA > 3.5 sostenido 2 s.
