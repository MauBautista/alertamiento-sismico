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
> schema §0/§8. `[RATIFICADO 2026-07-09 · T-1.45 — 10 roles; las identidades máquina no son
> roles RBAC]` (`PLAN-MAESTRO-TAKAB.md:59-65`: no existía un 11º rol humano planeado; toda la
> Fase 1 —`matrix.py`, Cognito, los E2E de T-1.30— se construyó y acreditó con 10 sin que
> faltara ninguno).

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
| `brigadista` | Personal de respuesta en campo. | **Móvil** (sin superficie web hoy) |
| `security_guard` | Seguridad/vigilancia del inmueble. | Móvil |
| `occupant` | Ocupante común del edificio. Rol más numeroso, menor privilegio. | **Móvil only** |

### Gobierno
| Rol | Descripción | Superficie primaria |
|---|---|---|
| `gov_operator` | Protección Civil. Visibilidad cruzada **solo** de tenants marcados `visibility = 'gov_shared'`. | Web |

---

## 2. Matriz de acceso · SOC Web

> **Renombrado de pestañas (T-2.39 y T-2.44).** Las columnas siguen a los rótulos que ve
> el operador: **Consola C4I → MONITOREO** (título *Monitoreo en Vivo*) y
> **Triage → EVALUACIÓN** (título *Evaluación Estructural Post-Sismo*). Las **rutas no
> cambiaron** (`/console`, `/triage`): están cableadas en `auth/matrix.py`, en los tokens
> y en las clases CSS, y renombrarlas rompería el RBAC por un cambio de etiqueta. Si
> busca "C4I" o "Triage" en el código, esos son los nombres nuevos.

| Rol | MONITOREO | Flota Edge | EVALUACIÓN | Multi-Tenant | Auditoría | Dash Edificio | Alcance de datos |
|---|---|---|---|---|---|---|---|
| `takab_superadmin` | Total | Total | Total | Total | Lectura | Total | Toda la plataforma |
| `takab_support` | Lectura | **Total** | Lectura | Lectura | Lectura | Lectura | Todos los tenants |
| `tenant_admin` | Lectura + ack | Lectura | Lectura | Solo sus umbrales | Lectura | Total | Su tenant |
| `soc_operator` | **Total** | Lectura | Lectura + crear | — | — | Lectura | Su tenant |
| `gov_operator` | Lectura + ack | Lectura | Lectura + export | — | Lectura | Lectura | Tenants `gov_shared` |
| `inspector` | Lectura | — | **Total** (firma dictamen) | — | — | Lectura | Sitios asignados |
| `building_admin` | Lectura (su sitio) | — | Lectura (su sitio) | — | — | **Total** | Su(s) sitio(s) |
| `brigadista` | — | — | — | — | — | — | (móvil en MVP) |
| `security_guard` | — | — | — | — | — | — | (móvil) |
| `occupant` | — | — | — | — | — | — | (móvil only) |

**Notas:**
- "Total" en MONITOREO incluye: acuse, solicitar dictamen técnico, reubicar epicentro.
- `gov_operator`: **solo lectura + acuse**. NO puede silenciar ni probar actuadores de inmuebles
  ajenos (decisión cerrada — controlar la sirena de un tercero es inaceptable).
  [ANALISIS-00] La celda de EVALUACIÓN decía "Total", lo que contradecía esta misma nota (un "Total"
  en EVALUACIÓN implicaría crear/firmar); se corrigió a **Lectura + export** (exportar miniSEED/PDF
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
- **[DECISION 2026-08-03 · T-2.36] Retirar una estación exige un SEGUNDO FACTOR.** Retirar
  un gabinete lo saca del config sync firmado (`commands/sync.py`) y de los comandos de
  actuación (`queries/commands.py`): deja un edificio sin protección. Además de
  `manage_fleet`, el retiro pide (a) teclear el identificador exacto del objeto —`serial`
  del gabinete, `code` del sitio; visible en pantalla, freno contra el clic en la fila
  equivocada— y (b) el **código de retiro del cliente**, que TAKAB entrega fuera de banda.
  La acción `manage_retire_code` (rotarlo) es **exclusiva de `takab_superadmin`**: si el
  propio `tenant_admin` pudiera rotar su código, el segundo factor volvería a ser el primero
  (su sesión) y la fricción sería decorativa. Fail-closed: un cliente sin código configurado
  NO puede retirar (409) — la ausencia de credencial nunca es un bypass. El hash (bcrypt vía
  `pgcrypto`) jamás sale de Postgres: se pregunta por `app_verify_retire_code`
  (SECURITY DEFINER) y `takab_app` no tiene política de lectura sobre la tabla. Cinco
  intentos fallidos por cliente en 15 min ⇒ 429, contados sobre `audit_log`. Anclado por
  `tests/auth/test_matrix.py::test_manage_retire_code_is_superadmin_only` y
  `tests/api/test_retire_code.py`.
- **[DECISION 2026-07-10 · T-1.48] Acciones nuevas de MONITOREO (extensión de §2,
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
- **[DECISION 2026-08-04 · T-2.52] La columna "Auditoría" (`/audit`) es NUEVA en esta
  tabla y no inventa ninguna frontera:** su celda es exactamente la acción `read_audit`
  de arriba. `GET /audit` existía desde T-1.57 y no tenía pantalla que lo consumiera, así
  que la ruta pasa a `auth/matrix.ROUTE_ORDER` para que la pestaña aparezca a quien ya
  podía leer el endpoint. `/audit` va **después** de Multi-Tenant y **antes** de
  `/building` en el orden: `web/src/app/landing.ts` aterriza en la primera ruta distinta
  de `/building`, y adelantarla cambiaría a dónde cae un usuario al iniciar sesión. El
  endpoint gana además `require_web_surface` (el trail lleva PII de actores y el detalle
  de cada acción sobre actuadores; un token de la app de campo no lo pagina). Ancla:
  `tests/auth/test_matrix.py::test_audit_route_matches_read_audit_action_exactly`.
- **[DECISION 2026-08-04 · T-2.54] `manage_users` (GET/POST/PATCH/DELETE `/users`,
  extensión de §2):** alta, edición y baja de identidades en Cognito =
  `takab_superadmin` y `tenant_admin` (acotado a SU tenant por el router). **NO** la
  recibe `takab_support`, pese a su "Total" en Flota Edge: `custom:tenant_id` y
  `custom:role` son los dos claims donde se ancla la RLS (§5.3), así que repartir
  identidades es repartir acceso a datos — soporte lee la plataforma, no la puebla.
  Reglas duras del endpoint: un rol de tenant no puede otorgar `takab_superadmin` ni
  `takab_support` (escalada), no puede escribir en otro cliente, y un usuario de otro
  tenant responde **404** (un 403 confirmaría que la cuenta existe). `occupant` no es
  asignable aquí: vive en el pool de ocupantes con ancla pool→rol (§5.2) y se da de alta
  con un código de enrolamiento. Toda escritura queda en `audit_log` con el diff
  (`user_create`, `user_update`, `user_password_reset`, `user_invitation_resent`,
  `user_delete`). Ninguna respuesta lleva credenciales: la contraseña temporal la genera
  y entrega Cognito por correo. Sin `TAKAB_API_COGNITO_USER_POOL_ID` el proveedor es un
  stand-in en memoria que GRITA en cada escritura (patrón `commands/keys.py`), jamás un
  fallback silencioso. Anclas: `tests/auth/test_matrix.py::test_manage_users_excludes_support`
  y `tests/api/test_users.py`.
  **Esta acción desbloquea la Fase B de T-2.45**: `custom:site_scope` ya tiene quién lo
  escriba, así que `TAKAB_API_CONSOLE_SCOPE_ENFORCED=true` deja de dejar sin datos a los
  operadores acotados — se activa cuando cada usuario web tenga su claim aprovisionado,
  no antes.
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
- **[DECISION 2026-08-06 · T-2.71] `maintenance_window` / `platform_maintenance_window`
  (ventanas de mantenimiento, extensión de §2):** abrir una ventana **silencia las alarmas
  de on-call** de un gabinete mientras dure la intervención. No mueve un relé, pero apaga la
  vigilancia de un edificio, así que se trata como acción sensible.
  - `maintenance_window` (ventana de GABINETE) = `takab_superadmin`, `tenant_admin` — el
    MISMO círculo que `drill_start`, y **deliberadamente NO el de `self_test`**. La
    diferencia importa: `building_admin` sí prueba los relés de SU inmueble, pero §2 le da
    "—" en Flota Edge y el control vive en `/fleet`; concedérsela pintaría un botón en una
    ruta que no tiene (regla de oro 7). Y lo que se apaga no es un dispositivo del edificio:
    es el correo que despierta al on-call de TAKAB. `soc_operator` DENEGADO por el mismo
    criterio que `self_test` (opera incidentes, no mantenimiento); `gov_operator` tampoco —
    lee evidencia, no apaga vigilancia ajena.
  - `platform_maintenance_window` (alarmas `ec2_*` de la instancia de la nube) = **SOLO**
    `takab_superadmin`, mismo criterio que `manage_tenants`/`manage_visibility`/
    `manage_retire_code`: vigilan la infraestructura común de TODOS los clientes, así que
    ningún tenant puede callarlas ni un rato.
  - **La frontera multi-tenant NO es la matriz, es el ORIGEN de los nombres de alarma.** Las
    alarmas de CloudWatch se identifican por nombre y no llevan `tenant_id`: el API los
    DERIVA de las filas `gateways` visibles bajo RLS y el body los tiene prohibidos
    (`extra="forbid"` → 422). Tres alarmas son intocables para cualquier rol
    (`dlq_depth`, `iot_rule_errors`, `ghost_gateways`) y la política IAM tampoco las
    concede — AWS comprueba `PutAlarmMuteRule` sobre CADA alarma apuntada.
  - La LECTURA de ventanas (`GET /maintenance-windows`) es de CONSOLA y se concede ancho
    (incluye `soc_operator`/`takab_support`) a propósito: una ventana invisible es
    exactamente el fallo que el criterio 2 existe para evitar.
  - Anclas: `tests/auth/test_matrix.py::test_maintenance_window_is_tenant_admin_action_not_a_field_role`,
    `::test_platform_maintenance_window_is_superadmin_only`,
    `::test_toda_ventana_de_mantenimiento_se_abre_desde_una_ruta_que_el_rol_tiene`.
- **[DECISION 2026-08-23 · T-2.70] `deploy_firmware` (activar una release en un gabinete o
  devolverlo a la anterior, extensión de §2):** **SOLO** `takab_superadmin`, y el criterio es
  el de `platform_maintenance_window` y **no** el de `maintenance_window`. Lo que se activa es
  el código desde el que arranca el camino de vida de un edificio: el artefacto lo puso el
  operador de TAKAB, la release la verificó su despliegue, y una versión mala deja un inmueble
  sin sirena, sin cierre de gas y sin retenedores. Un `tenant_admin` no tiene el artefacto ni
  con qué juzgar una versión, así que concederle el botón sería darle una consecuencia que no
  puede evaluar.
  - **ACTIVAR y REVERTIR van bajo la MISMA acción a propósito.** La vuelta atrás es la válvula
    de seguridad de la ida; un permiso que dejara empujar sin dejar volver sería peor que
    ninguno.
  - **El permiso NO es lo único que gobierna la actuación física.** En un gabinete cuyo dueño
    de pines siga dentro de `takab-edge`, activar cicla `GAS_VALVE` y `DOOR_RETAINER`: ahí el
    comando remoto exige además **ventana de mantenimiento declarada**, y sin ella el propio
    gabinete se niega (`bin/canary.sh`). El rol abre la puerta; el edificio sigue teniendo la
    última palabra.
  - Ancla: `tests/auth/test_matrix.py::test_deploy_firmware_is_platform_not_tenant`.
- **[DECISION 2026-08-10 · T-2.79.e] `manage_privacy_notice` (aviso de privacidad del
  cliente, extensión de §2):** publicar el aviso del tenant (`POST /privacy/notices`) y
  dejar constancia del consentimiento de un **tercero sin sesión** (un teléfono: el
  opt-in de WhatsApp de T-2.77, `POST /privacy/consents/third-party`) =
  `takab_superadmin`, `tenant_admin`. Son **una sola acción** porque son el mismo acto
  jurídico: bajo la LFPDPPP el *responsable* de los datos de los ocupantes de un inmueble
  es la organización dueña del inmueble, así que publicar su aviso —y registrar a quién
  se le enseñó qué texto— es un acto SUYO. Mismo círculo que `edit_thresholds` /
  `drill_start`.
  - **NO** la recibe `takab_support`, pese a su "Total" en §2: soporte lee la plataforma,
    no firma el aviso de privacidad de un cliente en su nombre. Misma disciplina que
    `manage_fleet` y `manage_users`.
  - **La frontera de seguridad no es esta acción, es la RLS `pn_publish`**
    (`tenant_id = app_tenant_id() AND app_role() IN ('tenant_admin','takab_superadmin')`):
    la matriz no sabe decir "y además la fila tiene que ser de TU cliente". La acción
    existe para que el 403 llegue limpio y la consola no pinte un botón que siempre
    fallaría (regla de oro 7).
  - **Consentir NO es una acción de esta matriz.** `POST /privacy/consent` y
    `POST /privacy/erasure` (ARCO) no llevan guarda de rol a propósito: son derechos del
    titular del dato, no permisos que se conceden — cualquier sesión autenticada los
    ejerce **sobre sí misma** y la RLS (`pc_self`, `app_user_id()`) los acota. Ponerles un
    rol convertiría un derecho en un privilegio.
  - **`POST /privacy/erasure` (ARCO del titular) tampoco la lleva a ella**, y desde
    T-2.80.b tampoco lleva `manage_privacy_erasure`: la puerta del responsable es otra
    ruta. Ver la decisión de abajo.
  - Esta acción cerró la última lista de roles escrita a mano fuera de `auth/matrix.py`
    (declarada como deuda en `routers/privacy.py` desde T-2.79). Anclas:
    `tests/auth/test_matrix.py::test_manage_privacy_notice_is_the_tenant_owner_circle`,
    `::test_publicar_aviso_conserva_exactamente_los_roles_que_tenia_el_router` (test
    caracterizador: prueba que mover la lista a la matriz **no movió la frontera**),
    `::test_el_router_de_privacidad_consulta_la_matriz_y_no_su_propia_lista` y
    `::test_ninguna_superficie_de_privacidad_enumera_roles_a_mano` (barrido AST de toda
    la superficie de privacidad/compliance).
- **[DECISION 2026-08-10 · T-2.80.b] `manage_privacy_erasure` (ejercer un ARCO recibido
  POR ESCRITO, extensión de §2):** registrar la constancia de una solicitud
  (`POST /privacy/erasure-requests`) y ejecutarla por cuenta del titular
  (`POST /privacy/erasure-requests/{request_id}/erasure`) = `takab_superadmin`,
  `tenant_admin`. Bajo la LFPDPPP una solicitud ARCO se le manda **al responsable del
  tratamiento** —la organización dueña del inmueble—, no a TAKAB; hasta T-2.80 solo el
  titular podía ejercerla desde la app, y eso no cubría el caso normal.
  - **NO** la recibe `takab_support`, por el mismo criterio que `manage_privacy_notice`:
    soporte lee la plataforma, no anonimiza al ocupante de un cliente en su nombre.
  - **Es una acción APARTE de `manage_privacy_notice` aunque hoy compartan roles.**
    Publicar un aviso se deshace publicando otra versión; anonimizar a una persona no se
    deshace. Fundirlas obligaría a conceder la irreversible para dar la reversible el día
    que los círculos dejen de coincidir.
  - **Ejercerlo por cuenta de otro EXIGE CONSTANCIA, y eso no lo decide esta acción.** Lo
    decide la base: `app_can_erase_subject(tenant, subject)` —"este portador tiene una
    solicitud registrada para este titular"— gatea cinco políticas RLS
    (`up_arco_on_behalf`, `pt_arco_on_behalf`, `dk_arco_on_behalf`, `lc_arco_on_behalf`,
    `pe_on_behalf`). Sin fila en `privacy_erasure_requests` el responsable no puede tocar
    **un solo dato** de esa persona, y cada política admite en su `WITH CHECK`
    exactamente la fila ANONIMIZADA: con constancia en mano, `SET display_name = 'Otro'`
    sigue siendo un error de RLS. El responsable no hereda "editar al ocupante".
  - **La garantía multi-tenant de T-2.80 no se debilita, y sigue sin ser un `if`.** La
    firma `privacy_erase_subject` **no recibe sujeto**: recibe el `request_id` de una
    constancia y resuelve el sujeto uniendo contra el padrón de `app_tenant_id()`. Y una
    constancia no puede nombrar a un titular ajeno porque lleva un FK **compuesto**
    `(tenant_id, user_sub) → user_profiles` con el `tenant_id` puesto por
    `DEFAULT app_tenant_id()`: el ARCO cruzado sigue siendo **inexpresable**, no
    rechazado. Un `request_id` de otro cliente responde 404 —el mismo que si no
    existiera—, porque para esa sesión no existe.
  - **Consentir y ejercer el ARCO PROPIO siguen sin llevar rol.** `POST /privacy/consent`
    y `POST /privacy/erasure` son derechos del titular sobre sí mismo y la RLS los acota
    (`pc_self`, `pe_self`, `app_user_id()`). Ponerles esta acción habría convertido un
    derecho en un privilegio.
  - **Lo que esta decisión NO cubre: borrar la cuenta en Cognito.** Anonimizar destruye el
    mapeo `sub → persona` en la base; dar de baja la identidad es otro sistema, con otra
    consecuencia (quien pierde la cuenta pierde el acceso a la app de emergencia del
    edificio) y necesita su propia ficha. Razonamiento completo en
    `api/src/takab_api/privacy/erasure.py`, sección «LO QUE ESTA TAREA NO HACE».
  - Anclas: `tests/auth/test_matrix.py::test_manage_privacy_erasure_is_the_responsible_circle`,
    `::test_ejercer_arco_por_otro_es_una_accion_APARTE_de_publicar_el_aviso`,
    `::test_el_derecho_del_titular_sigue_sin_llevar_rol`,
    `tests/test_privacy_erasure.py::test_una_constancia_no_puede_nombrar_a_un_titular_de_otro_tenant`,
    `::test_la_constancia_de_otro_cliente_no_existe_para_este_responsable`,
    `::test_sin_constancia_el_responsable_no_puede_tocar_un_solo_dato`,
    `::test_la_constancia_no_autoriza_a_reescribir_el_perfil`,
    `tests/api/test_privacy_erasure.py::test_el_audit_log_dice_quien_pidio_quien_ejecuto_y_con_que_prueba`.

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

> **[T-2.03] Esta matriz es EJECUTABLE:** las celdas con acción se materializan en
> `api/src/takab_api/auth/matrix.py` (`checkin_submit`, `roster_read`,
> `damage_report_submit`, `evidence_upload`, `siren_silence`, `manual_activate`,
> `enrollment_manage`, `panic_vote`, `dictamen_read`) y el parity test
> `tests/auth/test_matrix.py::test_mobile_actions_match_rbac_section_3` compara el
> código contra esta tabla celda a celda — si divergen, CI falla (misma disciplina
> que §2 para la web). El voto de pánico del occupant (quórum 2/30 s) es la acción
> `panic_vote`; su endpoint llega en T-2.13.

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
| `/console` | MONITOREO (1) | superadmin, support, tenant_admin, soc_operator, gov_operator, inspector, building_admin |
| `/fleet` | Flota Edge (2) | superadmin, support, tenant_admin, soc_operator, gov_operator, building_admin |
| `/triage` | EVALUACIÓN (3) | superadmin, support, tenant_admin, soc_operator, gov_operator, inspector, building_admin |
| `/tenants` | Multi-Tenant (4) | superadmin, support(lectura), tenant_admin(solo suyo) |
| `/audit` | Auditoría (T-2.52) | superadmin, support, tenant_admin(su tenant), gov_operator |
| `/building/:siteId` | Dash Edificio | tenant_admin, building_admin, +lectura otros |

**Sub-superficies que NO son rutas** (van dentro de una ruta existente, gateadas por
acción — añadir una ruta obliga a tocar `auth/matrix.py`, y estas ya están cubiertas):

| Sub-superficie | Vive en | Acción que la gatea |
|---|---|---|
| Administración de estaciones (T-1.36) | `/fleet` | `manage_fleet` |
| Códigos de enrolamiento (T-2.53) | `/fleet` | `enrollment_manage` |
| Visibilidad entre clientes (T-1.73) | `/tenants` | `manage_visibility` |
| Gestión de usuarios (T-2.54) | `/tenants` | `manage_users` |
| Solicitudes ARCO recibidas por escrito (T-2.80.b) | `/tenants` | `manage_privacy_erasure` |

**Móvil (`mobile/` — CONSTRUIDA Y MERGEADA en la Fase 2, T-2.00…T-2.14; `TASKS.md` T-1.31
quedó "CUBIERTA POR LA FASE 2 COMPLETA"):**
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

### Salidos de PENDIENTES (implementados; se quedan aquí para que no se vuelvan a "proponer")

4. **Disparador del pop-up de waveform — IMPLEMENTADO en T-1.27** (reconciliado 2026-08-05,
   T-2.61). La propuesta era "STA/LTA > 3.5 sostenido 2 s" y eso es exactamente lo que corre:
   `web/src/features/console/useAutoPopup.ts:11-12` define `STALTA_THRESHOLD = 3.5` y
   `STALTA_CONSECUTIVE = 2` (= 2 muestras de 1 s consecutivas = los 2 s), con **latch por
   episodio**: dispara una vez y se rearma cuando la señal baja del umbral, para que un temblor
   largo no reabra el panel en cada muestra (`:29,39-46`). Llevaba **desde el 2026-07-08**
   escrito en el repo mientras este documento lo seguía llamando "propuesta".
