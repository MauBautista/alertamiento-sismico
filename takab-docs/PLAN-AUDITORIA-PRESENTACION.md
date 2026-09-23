# Plan · Auditoría integral y puesta a punto para la presentación del **jueves 24-sep-2026**

> **De dónde sale.** Del encargo de Mauricio del **2026-09-22**, dos días antes de la presentación
> a clientes del jueves 24. Se planificó en modo plan con un descubrimiento de solo lectura (diez
> agentes) y cuatro preguntas que Mauricio contestó ese mismo día; sus respuestas son `D-38`. **Aquí
> está el diseño, el objetivo ejecutable y el calendario de cada fase; las fichas y sus criterios de
> aceptación están en el `BLOQUE IX` de [`TASKS.md`](TASKS.md).** Este plan no se reescribe: es un
> documento de decisión. El estado vivo de cada hallazgo es su ficha.

## Contexto

Mauricio pidió una auditoría de todo el sistema antes de presentarlo a clientes. El encargo tiene diez partes:

1. Revisar la UI/UX desde la vista de la página: que funcione cada botón y cada desplegable.
2. Recorrer todos los roles y todos sus flujos.
3. Revisar los permisos.
4. Ajustar la duración de sesión: **30 días sin contraseña ni MFA para brigadista e inspector**, el ocupante con la sesión larga que ya tiene, y **1 día para el resto**.
5. Comprobar que funcione cada componente.
6. Listar las funciones básicas del sistema y lo que falta.
7. Revisar el PDF.
8. Proponer mejoras para el móvil, el edge y la nube.
9. Encontrar dónde añadir animaciones, incluidas las pasivas.
10. Asegurar que todo estatus con datos se pueda ver.

El trabajo va por fases. Cada fase tiene un **Goal ejecutable** y se corre en `/loop`, con subagentes.

**Ya se hizo un descubrimiento de solo lectura**, con un workflow de 10 agentes Explore. Una dimensión por agente: web MONITOREO/EVALUACIÓN, web flota/tenants/edificio, móvil, sesiones, RBAC, PDF, estatus, animaciones, funciones básicas y edge/nube/presentación. Salieron **356 hallazgos**: 7 P0, 76 P1, el resto P2/P3. El volcado íntegro está en [`auditoria/descubrimiento-2026-09-22.json`](auditoria/descubrimiento-2026-09-22.json) y el documento que lo ordena es [`AUDITORIA-PRESENTACION-2026-09.md`](AUDITORIA-PRESENTACION-2026-09.md); las fichas, en el `BLOQUE IX` de [`TASKS.md`](TASKS.md).

**El hallazgo que más importa, verificado a mano:**
- **Web.** La consola hoy **cierra la sesión a los ~60 min**. `ws.py:88-99` cierra el socket con 4401 cuando vence el token del handshake, `live.ts:219-222` llama a `onUnauthorized` y `LiveSocketProvider.tsx:28-29` ejecuta `logout()`. El ensayo 1 duró 59 min.
- **Móvil.** La app **nunca usa el refresh token**: `useAuth.ts:48,76-81` lo guarda y ningún código lo lee. A los 60 min vuelve a pedir contraseña y TOTP.

Los refresh de 8 h, 24 h y 90 días de Cognito son hoy letra muerta.

### Decisiones tomadas en esta sesión (se registran como **D-38**)

| Tema | Decisión |
|---|---|
| Duración por rol | brigadista, inspector: **30 d** · occupant: **90 d** (se mantiene) · takab_superadmin, takab_support, tenant_admin, soc_operator, gov_operator, building_admin, security_guard: **24 h**. Es un **tope absoluto desde el login** (`auth_time`), que impone la API, porque Cognito fija la validez por *app client* y no por rol. |
| Consola web | `localStorage` + tope en el servidor; el inspector también tiene 30 d en la web. Mitigación: CSP + revocación al cerrar sesión. |
| SOC al llegar a la hora 24 | Aviso en la Topbar 60 min antes, con «RENOVAR AHORA». **Sin prórroga** durante un incidente. |
| Alcance | Auditoría + arreglos P0/P1 + mejoras curadas. Las mejoras de edge/nube pasan a fichas `T-8.xx`; solo se implementan las baratas y seguras. |
| Recorrido por rol | Primero **local** (`make soc-local` + dev-token, los 10 roles). Después, un **pase final en la nube y en el Pixel** con usuarios reales que Mauricio crea con `!`. |
| Fecha | Presentación el **jue 24-sep**. **Congelación de despliegues: miércoles 23 a las 18:00.** **El edge no se despliega antes del jueves.** |

---

## Resultado del descubrimiento

### Funciones básicas: estado (versión condensada; la completa va en el documento de auditoría)

| Dominio | Implementado ✅ | Parcial ⚠️ | Falta ❌ |
|---|---|---|---|
| Alertamiento | Reflejo SASMEX/WR-1 → sirena, sin nube; instrumental = aviso visual; cuórum con comando firmado | La consola y el teléfono se contradicen al corroborar el cuórum | Sirena con el Pi apagado (G-02, hardware) |
| Actuadores | Silenciar y activar firmados (MFA + nonce + ack); pánico por cuórum de ocupantes | — | Gas, ascensores y puertas (BACnet solo en simulador); voceo sin grabaciones |
| Monitoreo | MONITOREO: mapa, KPIs, cola WS, ficha, sismograma, epicentro, ondas, franjas | Estados con dato pero sin pantalla (ver F6) | — |
| Incidentes | Fases, acuse, clasificación y cierre (D-33) | El acuse se traga los errores; la selección va por sitio | — |
| Dictamen | Semaforizado, firmado, inmutable, PDF verificable | Primera firma; verificador con 404 para 5 roles | — |
| PDF | Informe del evento, reporte de simulacro, membrete D-36 | Las fotos pisan el pie; la clasificación no se imprime; solo UTC | Reporte mensual/SLA; exportación de auditoría |
| Móvil | 21 pantallas de la especificación, ocupante y táctico | Sesión de 60 min; dictamen después del cierre; cámara | iOS y tiendas (T-2.97/98) |
| Notificaciones | Webhook HMAC; push Android | Correo en sandbox SES | SMS y WhatsApp reales; push iOS; «prueba de canal» |
| Simulacros | Agenda, disparo armado, plantillas, reporte | Un solo clic vocea; se borra sin confirmar; el superadmin alcanza a todos los tenants | — |
| Flota | Inventario, salud, alta de sitio/gabinete/sensor | Rollouts canary sin UI; evidencia y disco siempre null | Watchdog de software |
| Tenants/RBAC | 10 roles ejecutables, RLS default-deny, gov_shared | Usuarios SIMULADOS en la nube (T-2.87); UsersCard cruza tenants | Alta de ocupantes, zonas/pisos CRUD, QR, padrón |
| Compliance | Bitácora inmutable | ARCO y aviso sin UI | Marco normativo (legal) |
| Sismología / IA | Catálogo USGS, ShakeMap, narrativa OpenRouter medida | 0 snapshots de ShakeMap en la nube | SSN (bloqueado, D-06); shadow-mode |
| Operación | Alarmas, PITR, DLM | RTO sin medir; un solo EC2 | Alarma de edad de SQS; % de disponibilidad |

### P0/P1 que se verían en la demo (identificador → ficha)

- **Sesión:** WS a 60 min (web P0); móvil sin refresh (P0); logout móvil sin revocar ni borrar el token push; `auth_time` sin medir.
- **Consola:**
  - El acuse descarta el error y pinta EJECUTADO (`ConsolePage.tsx:191-201`, `ConfirmButton.tsx:72-77`).
  - La selección va por sitio y no por incidente (`ConsolePage.tsx:90-95`).
  - El Modal roba el foco cada segundo en Reubicar, Comparativa y Simulacro (`Modal.tsx:18-28`).
  - El simulacro del superadmin sin selección alcanza a todos los tenants (`drills.py:470-528`).
  - La firma del dictamen no aparece sin un dictamen previo (`TriageDetail.tsx:479-547`).
- **Evaluación:**
  - DESCARGAR CLIP no hace nada (`TriagePage.tsx:239-265`).
  - CCTV da 403 a gov y support (`useCctv.ts:31-44`).
  - VERIFICAR HASH da 404 a 5 roles (`TriageDetail.tsx:392-400`).
  - Los comandos de cuórum dan 403 cada 15 s (`useQuorumCommands.ts:60-61`).
- **Flota, edificio y tenants:**
  - gov ve una alerta roja permanente de ventanas (`FleetPage.tsx:257-269`).
  - Tras silenciar dice «SIRENA SONANDO» (`useSirenTest.ts:48-60`).
  - UsersCard muestra usuarios de todos los clientes al superadmin (`UsersCard.tsx:84-151`).
  - `GatewayOut` descarta evidencia y disco, así que todas las tarjetas dicen «s/d · el gabinete no pudo mirar» (`fleet.py:284-353`).
  - Con el LWT offline el gabinete parece vivo (`handlers.py:927-1013`, `queries/fleet.py:58-66`).
- **Cuórum:** la consola deriva «autoriza» solo de `trigger` y el móvil de `node_count` (`AlertBanner.tsx:73` frente a `source.ts:79-80`).
- **Móvil:**
  - VER DICTAMEN lleva a «Sin incidente activo» después del cierre D-33 (`dictamen.tsx:22-24`).
  - La cámara revisa el visor en vivo y no la foto tomada (`camera.tsx:299-318`).
  - En CUENTA, con error, no hay botón de cerrar sesión (`AccountScreen.tsx:95-101`).
  - No hay feedback al pulsar: 57 `Pressable` sin `pressed`.
- **PDF:**
  - Con 1 foto o un número impar, el texto se imprime encima del pie (`pdf.py:1592-1616`).
  - Las fotos en vertical pisan el pie (`fotos.py:157-161`).
  - No se imprime la clasificación humana, así que los ensayos salen como sismo REAL.
  - El certificado móvil puede servir el PDF PRELIMINAR (`queries/mobile.py:198-202`).
  - El render bloquea el event loop (`reports.py:50-136`).
  - Salen títulos del ejecutivo como «. QUÉ PASÓ», valores en inglés, el UUID en FIRMÓ y solo UTC.
- **Presentación:**
  - `guion.sh:713` y `RUNBOOK:367` mandan `/api/reset` sin PIN, que da 401.
  - Los incidentes del ensayo 1 están sin clasificar.
  - Falta el usuario `takab_support`.
  - inspector y building_admin no pueden entrar en la app (`surface=web`).
  - gov_operator vive en un tenant privado, así que ACUSAR da 404.
  - La rama `b804039` está sin mergear.

---

## Método de ejecución (todas las fases)

- **El Goal de cada fase es un bloque de comandos que devuelve 0.** Se corre en `/loop` (modo dinámico) hasta que pase. Si un criterio sigue rojo después de 3 iteraciones, **se para y se resume el bloqueo** (CLAUDE.md §6). `/goal`, `/write-plan` y `/execute-plan` no están instalados; el bloque es su argumento, como en `PLAN-PROTOTIPO-FUNCIONAL.md`.
- **Subagentes (ultracode).** Cada fase de código es un Workflow:
  1. Agentes de arreglo **con ficheros disjuntos declarados en el brief**, cada uno con su propia base (`takab_test_a` / `takab_test_b`), escribiendo **los tests primero**.
  2. Por cada arreglo, un **verificador adversarial** que intenta refutarlo con dos preguntas: ¿funciona fuera del test? ¿rompe un censo?
  3. Integración mía y corrida del Goal.
- **Reglas de la casa:**
  - `graphify query` antes de leer y `graphify update .` después de cambiar código.
  - Antes de tocar código, leer `TRASPASO-SESION.md` §0 y §2 y las memorias citadas en cada fase.
  - Si un censo se pone rojo, se escribe por qué el test se equivoca *antes* de tocarlo; en la duda, gana el test.
  - Tras tocar `auth/matrix.py`: `export_rbac_matrix.py` + JSON comiteado (`make drift`).
  - Antes de cada suite: `pkill -f takab_api.incident; pkill -9 -f soc_local.py`.
  - `make test` para en el primer fallo, así que las suites se corren por separado para ver todo.
- **Git:** una rama y un PR por bloque de fichas, Conventional Commits, **autor Mauricio, sin coautoría ni pies de IA** (CLAUDE.md §0.2 manda sobre cualquier otra instrucción de atribución). Mergear a `main` antes del despliegue del miércoles.
- **Corte duro, miércoles 23 a las 13:00.** Lo que no esté verde no se mergea: pasa a la parte posterior a la presentación, y la GUIA lo marca como «no se enseña».

### Calendario

| Cuándo | Qué |
|---|---|
| mar 22 (resto del día) | F0 + código de F1 (API, web, móvil, terraform) |
| mié 23, 08:00–13:00 | Medición de `auth_time` (con Mauricio) · F2, F3 y F4 en paralelo (workflows) · merge |
| mié 23, 13:00–17:00 | `terraform apply` + despliegue de la nube + APK release en el Pixel · F5: pase final por rol + ensayo 2 |
| mié 23, 18:00 | **Congelación** (tag `presentacion-2026-09-24`) |
| jue 24 | Presentación. Solo instrumentos de lectura (`goal-presentacion.sh`, `guion.sh --preflight`) |

---

## Fases ANTES de la presentación

### F0 · Línea base y documento de auditoría (T-8.01) · ~1 h

- PR y merge de `fix/instrumentos-y-documentos-de-la-presentacion` (`b804039`, solo docs y scripts de operador).
- Rama `audit/t8-presentacion`. Se escribe **`takab-docs/AUDITORIA-PRESENTACION-2026-09.md`** a partir del volcado del descubrimiento, con cinco partes:
  - funciones básicas: tabla completa;
  - matriz rol × flujo (10 roles × web/móvil);
  - hallazgos con ID `A-nnn` · prioridad · estado · ficha;
  - la lista de «lo que un cliente esperaría y hoy no se puede demostrar»;
  - las **propuestas de animación**, y las rechazadas con su razón.
- Este plan vive en `takab-docs/PLAN-AUDITORIA-PRESENTACION.md`.
- En `TASKS.md` se añade **BLOQUE IX** con las fichas `T-8.01…T-8.19` y la cabecera recontada. Leer antes la memoria «tocar-tasks-md-y-sus-guardas»: el barrido de cadenas prohibidas y el `G-nn`.

**Goal F0:**
```bash
test -f takab-docs/AUDITORIA-PRESENTACION-2026-09.md && test -f takab-docs/PLAN-AUDITORIA-PRESENTACION.md
grep -c '^| A-[0-9]\{3\}' takab-docs/AUDITORIA-PRESENTACION-2026-09.md | awk '$1>=80{ok=1} END{exit !ok}'   # todos los P0/P1 volcados
cd api && uv run pytest -q tests/test_docs_consistency.py && cd ..
git log main --oneline | grep -q '(#274)'   # la PR de instrumentos, mergeada con squash
```

### F1 · Sesión por rol, extremo a extremo (T-8.02 … T-8.05) · P0

**Paso 0, antes de escribir el tope: medir `auth_time` en Cognito real.** Mauricio entra en la consola desplegada. Se le da un fragmento para DevTools que lee el `oidc.user` del almacenamiento, ejecuta `getUserManager().signinSilent()` y compara el `auth_time` de los dos ID tokens.
- Si **se conserva** (lo que exige OIDC Core), el tope se hace sobre `auth_time`.
- Si **se renueva**, se usa la alternativa: una tabla `session_origins(origin_jti PK, sub, first_seen_at)` con `ON CONFLICT DO NOTHING`, y el tope se cuenta desde `first_seen_at`. `origin_jti` no cambia al renovar.

El fragmento, para pegar en DevTools → Console de la consola desplegada con la sesión abierta. Lee
la sesión de `oidc-client-ts` (en `localStorage` desde D-38, en `sessionStorage` antes), pide un
refresco con el propio refresh token al endpoint de Cognito —lo mismo que hace la renovación
silenciosa— e imprime **solo marcas de tiempo**, ningún token:

```js
(async () => {
  let k, s;
  for (const st of [localStorage, sessionStorage]) {
    k = Object.keys(st).find((x) => x.startsWith("oidc.user:"));
    if (k) { s = st; break; }
  }
  if (!k) return console.log("No hay sesión de Cognito en esta pestaña.");
  const u = JSON.parse(s.getItem(k));
  const dec = (t) => JSON.parse(atob(t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
  const rest = k.slice("oidc.user:".length);
  const cut = rest.lastIndexOf(":");
  const authority = rest.slice(0, cut), clientId = rest.slice(cut + 1);
  const meta = await (await fetch(`${authority}/.well-known/openid-configuration`)).json();
  const r = await fetch(meta.token_endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "refresh_token", client_id: clientId, refresh_token: u.refresh_token }),
  });
  const j = await r.json();
  if (!j.id_token) return console.log("El refresco falló:", r.status, j.error);
  const a = dec(u.id_token), b = dec(j.id_token);
  console.table({
    auth_time_antes: a.auth_time, auth_time_despues: b.auth_time,
    iat_antes: a.iat, iat_despues: b.iat,
    mismo_origin_jti: a.origin_jti === b.origin_jti,
    CONSERVA_AUTH_TIME: a.auth_time === b.auth_time,
  });
})();
```

**T-8.02 · API (lote A, `api/`):**
- `auth/matrix.py`: `SESSION_MAX_AGE_S`, con un censo que exija exactamente los 10 roles; un rol desconocido = caducado.
- Nuevo `auth/session_age.py` con `session_deadline()` y `enforce_session_age()`, llamado en `deps.get_claims` después del ancla pool→rol (`deps.py:91-99`).
- 401 con `detail="sesion_expirada"` y `WWW-Authenticate: Bearer error="invalid_token", error_description="sesion_expirada"`.
- `tokens.py:76`: exigir `auth_time`. `claims.py`: campo `auth_time`.
- `routers/ws.py`: plazo = `min(exp, deadline)` y **código de cierre nuevo 4440** para sesión expirada (4401 queda para el token vencido, que se puede renovar).
- `/me` expone `session_expires_at` (`schemas/me.py`).
- `tests/auth_utils.py` y `routers/dev_token.py` emiten `auth_time`, con `auth_age_s` para simular sesiones viejas.
- `users/directory.py:382-387`: al deshabilitar un usuario, `admin_user_global_sign_out`. Es el interruptor contra sesiones de 30 d robadas.
- Tests nuevos:
  - soc_operator con 86 401 s → 401 `sesion_expirada`;
  - brigadista con 29 d → 200;
  - occupant con 89 d → 200 y con 91 d → 401;
  - token sin `auth_time` → 401;
  - WS caducado → 4440;
  - `require_mfa` intacto (`tests/api/test_command_mfa.py`).

**T-8.03 · Web (lote B, `web/src/auth`, `web/src/live`, `web/src/shell`, `shared/sdk-ts/src/live.ts`):**
- `userManager.ts`: `WebStorageStateStore({store: localStorage})` + `revokeTokensOnSignout: true`.
- `session.store.ts:154`: si `user.expired && user.refresh_token`, ejecutar `signinSilent()` antes de declarar la sesión anónima.
- `LiveSocket`: opción `renewToken`. Ante 4401, renovar una vez y reconectar. Ante 4440 → `onUnauthorized('max_age')`.
- `apiClient.ts` y `me.ts` leen `error_description` → `endedReason: 'max_age'`. `LoginPage` muestra «SU SESIÓN DE 24 H TERMINÓ».
- Topbar: aviso 60 min antes de `session_expires_at`, con botón «RENOVAR AHORA» (logout + login).
- `deploy/cloud/Caddyfile`: **CSP**. Entra *enforce* solo si el recorrido desplegado da 0 violaciones con MapLibre, las fuentes, Cognito y el WS. Si no, entra *Report-Only* y se ficha `T-8.16`.

**T-8.04 · Móvil (lote C, `mobile/src/auth`, `mobile/src/services/sdk.ts`, `mobile/src/live/socket.ts`):**
- Nuevo `auth/refresh.ts`: `refreshSession()` de vuelo único con `AuthSession.refreshAsync` contra `discoveryFor(POOLS[profile])`. Se dispara:
  - al arrancar si al token le quedan menos de 5 min;
  - en `AppState` → active;
  - antes de conectar el WS;
  - ante un 401 que no sea `sesion_expirada` (un reintento).
- Persistir el `idToken` nuevo (`secureTokens.ts` + `idTokenExp`, `authAt`).
- Logout, best-effort, en este orden: `DELETE /me/push-tokens/{id}` → `AuthSession.revokeAsync` → `/logout` de la Hosted UI → borrar SecureStore.
- Tests de jest para el vuelo único, el 401 → refresh → reintento y `sesion_expirada` → login.

**T-8.05 · Terraform, decisión y documentos (lote D, `infra/`, `takab-docs/`):**
- `identity/main.tf`: `web` 8 h → **30 d**; `mobile_tactical` 24 h → **30 d**; `mobile_occupants` 90 d (sin cambios). Actualizar los comentarios de las líneas 608-611 y 645-646.
- Nuevo `tests/sesion.tftest.hcl` que ancle los valores.
- **D-38** en `DECISIONES-MAURICIO.md`, con cabecera, índice y reparto (`test_docs_consistency.py:2060-2190`). Declara su precio: MFA una vez al mes en roles con actuadores, un teléfono robado vale 30 d salvo el interruptor, y el riesgo de XSS de `localStorage`.
- Actualizar `RBAC-TAKAB.md` (§5.4 nueva, «Duración de sesión por rol», con test gemelo de paridad), `specs/cognito-pool-v1.md` y `ESPECIFICACION-APP-MOVIL.md` §8.

**Goal F1:**
```bash
set -e
cd api && uv run pytest -q tests/auth tests/api/test_command_mfa.py tests/test_docs_consistency.py -k "session or sesion or auth or mfa or docs" && uv run pytest -q tests/ws && cd ..
(cd infra/terraform/modules/identity && terraform test)
(cd web && npx vitest run src/auth src/live src/shell src/pages)
(cd mobile && npm test -- --testPathPattern 'auth|sdk|socket' && npm run typecheck && npx expo lint)
make lint && make drift
# local: sesión dev con expires_in=120 y /console abierto 150 s ⇒ sigue dentro (e2e nuevo web/e2e/sesion.spec.ts)
(cd web && npx playwright test e2e/sesion.spec.ts)
# Después del despliegue del miércoles (se registra en la auditoría):
#   describe-user-pool-client ⇒ web 30 d, táctico 30 d, ocupantes 90 d
#   consola desplegada abierta 70 min sin logout; Pixel táctico y ocupante 70 min sin login
#   soc_operator con auth_time de más de 24 h ⇒ LoginPage «SU SESIÓN DE 24 H TERMINÓ»
```

### F2 · Recorrido de la UI web por rol + arreglos P0/P1 web (T-8.06 … T-8.10)

**T-8.06 · `web/e2e/recorrido_por_rol.spec.ts`.** Reutiliza el login dev de `web/e2e/helpers.ts` y corre sobre `make soc-local`. Para **cada uno de los 10 roles**:
1. Entra y lee `me.allowed_routes`. brigadista, security_guard y occupant deben ver `MobileOnlyScreen`.
2. Visita cada ruta, más `/building/:siteId`.
3. Recoge `pageerror`, `console.error` y **toda respuesta de 400 o más**. Ninguna está en la lista de esperadas: un 403 significa que la UI pide algo que el rol no tiene, y eso es un defecto.
4. Enumera los botones, `combobox`/`select`, `[aria-haspopup]`, `summary`, `[role=tab]` y enlaces internos.
5. Pulsa cada control **no mutante** y comprueba que cambie algo: `aria-expanded`, aparece un diálogo, cambian la URL o `aria-selected`, o hay un estado vacío declarado. Un select sin opciones debe declarar su vacío. Después `Escape`.
6. Los controles **mutantes** (por regex: ACUS|FIRM|EJECUT|INICIAR|BORR|ELIMIN|SILENCI|PROBAR|BAJA|DESHABILIT|PUBLICAR|VOLVER A v|RESTAUR|GUARDAR|CREAR|AÑADIR|APLICAR|ENVIAR|SALIR) se censan y se ejercen en specs de flujo dirigidas.
7. Captura por rol y ruta, más `takab-docs/auditoria/recorrido-web.json` y una tabla generada en el documento de auditoría.

**Lotes de arreglo** (Workflow; ficheros disjuntos; tests primero; verificador adversarial por arreglo):
- **T-8.07 Consola** (`web/src/features/console`, `web/src/components/{Modal,ConfirmButton}.tsx`, `api/src/takab_api/routers/drills.py`):
  - acuse con `useMutation`, estado pendiente y error; EJECUTADO solo tras el 200;
  - `selectedIncidentId` separado del sitio;
  - Modal con el foco inicial en un efecto `[]` y `onClose` guardado en un ref;
  - `POST /drills` exige `tenant_id` a los roles internos (`resolve_write_tenant`);
  - confirmación en BORRAR plantilla y en EJECUTAR/INICIAR AHORA;
  - columna ESTADO en la cola.
- **T-8.08 Evaluación** (`web/src/features/triage`):
  - `onDownloadClip` con `openPendingDownload` (patrón de `downloadEvidence`);
  - la firma del dictamen también sin cabeza (`TriageDetail.tsx`);
  - `useCctv`, `EvidenceVerifier` y `useQuorumCommands` quedan detrás de `allowed_actions` (no se amplían permisos: se deja de pedir lo que no se tiene).
- **T-8.09 Flota, edificio y tenants** (`web/src/features/{fleet,building,tenants}`, `api/.../routers/fleet.py`, `api/.../ingest/handlers.py`, `api/.../queries/fleet.py`):
  - aviso de ventanas solo si `!forbidden`;
  - fases de la sirena por acción (SILENCIADA · ACUSADA);
  - UsersCard filtrado por `tenant_id` y paginación `next_cursor`;
  - `GatewayOut` pasa `evidence_*` y `disk_used_pct`, y se amplía el censo a la **salida** de la API;
  - la fila LWT offline no cuenta como latido (filtrar `reason` en las lecturas del último latido);
  - confirmación en DAR DE BAJA, en el cambio de rol y en «VOLVER A vN»;
  - el faro del mapa respeta `prefers-reduced-motion` (`MapPanel.tsx:677-690`), que es barato y visible.
- **T-8.10 Cuórum coherente** (`web/src/features/console/AlertBanner.tsx`, `features/scene`): «autoriza» = `authorizes(trigger) || node_count ≥ quorum_min_nodes`, la misma regla que `mobile/src/features/alert/source.ts:79-80`.

**Goal F2:**
```bash
set -e
pkill -f takab_api.incident || true; pkill -9 -f soc_local.py || true
(cd web && npx vitest run) && (cd api && uv run pytest -q tests/api tests/ingest tests/auth)
setsid nohup make soc-local > /tmp/soc-local.log 2>&1 & disown   # interactivo (Ctrl+C apaga): se lanza desacoplado
until curl -sf localhost:5173 >/dev/null; do sleep 2; done
(cd web && npx playwright test e2e/recorrido_por_rol.spec.ts e2e/drill.spec.ts e2e/vida_del_sismo.spec.ts e2e/scope.spec.ts e2e/motion.spec.ts)
python3 - <<'EOF'   # el censo generado: cero inesperados en los 10 roles
import json,sys; r=json.load(open('takab-docs/auditoria/recorrido-web.json'))
bad=[x for x in r['hallazgos'] if x['tipo'] in ('pageerror','http_inesperado','control_sin_efecto','select_vacio_sin_estado')]
print(len(r['roles']),'roles ·',len(bad),'inesperados'); sys.exit(len(r['roles'])!=10 or bool(bad))
EOF
make lint && make drift
```

### F3 · Móvil P1 (T-8.11), en paralelo con F2

Ficheros `mobile/src/app/{dictamen,camera}.tsx`, `mobile/src/features/{account,dictamen}`, `(brigadista)/lista.tsx`, `offline/queue.ts`, `.maestro/`:
- el dictamen se resuelve por el **último incidente con dictamen firmado** (`reentry`), no por `state.incident`;
- la cámara revisa la **foto tomada** (`<Image source={{uri: photoUri}}>` dentro de `composeRef`);
- CUENTA deja siempre visibles CERRAR SESIÓN y las filas locales (solo la tarjeta PERFIL entra en error, con REINTENTAR);
- feedback al pulsar en los 57 `Pressable` (`pressed` + `android_ripple` desde los tokens; escala solo si `!reduceMotion`);
- check-in delegado con `subject_user_id` en la cola, y `05b-offline-cola.yaml` comprueba un item concreto (`testID sync-<id>`);
- flujos Maestro nuevos `recorrido-ocupante.yaml` y `recorrido-tactico.yaml`: pulsan cada pestaña y cada botón no mutante, con `takeScreenshot`.

**Goal F3:**
```bash
set -e
(cd mobile && npm test && npm run typecheck && npx expo lint)
(cd mobile/android && ./gradlew :app:assembleRelease -PreactNativeArchitectures=arm64-v8a)
adb devices | grep -q 41270DLJG000WB && adb install -r mobile/android/app/build/outputs/apk/release/app-release.apk
# En el Pixel (Mauricio conecta y teclea el TOTP en 02/05):
TAKAB_MAESTRO_ENV=.env.e2e mobile/.maestro/run.sh recorrido-ocupante.yaml
TAKAB_MAESTRO_ENV=.env.e2e mobile/.maestro/run.sh recorrido-tactico.yaml
TAKAB_MAESTRO_ENV=.env.e2e mobile/.maestro/run.sh 01a*.yaml 01b*.yaml 02*.yaml 03*.yaml
```
Nada de emuladores (memoria «nunca-emuladores-siempre-pixel-real»). Si no hay Pixel, se para y se pide.

### F4 · El PDF (T-8.12), en paralelo con F2 y F3

Ficheros `api/src/takab_api/{dictamen,documentos}/`, `drill_report.py`, `routers/{reports,drills}.py`, `queries/mobile.py`:
- **Fotos:** después de cada fila, `set_y(fondo máximo de los pies)`; retrato encajado en una caja de 88×88 mm o reserva con la altura real.
- **Portada y ejecutivo:** línea «CLASIFICACIÓN: …» tomada de `incident_classifications` (aditiva; no toca la derivación de REPRODUCCIÓN).
- **Ejecutivo:** títulos sin el «.» inicial (`membrete.py:400-405`).
- **Traducción:** mapa de valores crudos en inglés → castellano (`pdf.py:189,1545-1562,1684`).
- **FIRMÓ:** rol + `display_name` de `user_profiles`, no el UUID.
- **Hora:** local `America/Mexico_City` junto a la UTC.
- **Certificado móvil:** solo sirve un `report_pdf` con `created_at >= signed_at`; si no existe, se genera al firmar.
- **Render fuera del event loop:** `anyio.to_thread.run_sync` en `generate_report`, `drill_report` y las lecturas de S3 (patrón de `commands/service.py:118`).
- **Reporte de simulacro:** clave S3 con sello o sha, no fija.
- **Revisión visual:** el script de 10 variantes del descubrimiento → `pdftoppm -r 110` → leo cada PNG y lo registro en la auditoría. Guardas de geometría nuevas: 1 foto, fotos impares, retrato, nombres largos en el simulacro.

**Goal F4:**
```bash
set -e
(cd api && uv run pytest -q tests/dictamen tests/documentos tests/narrative tests/api/test_drill_report.py tests/api -k "report or dictamen or drill or pdf")
bash takab-docs/auditoria/render-pdfs.sh /tmp/takab-pdf   # las 10 variantes + pdftoppm; lo escribe esta fase
for f in /tmp/takab-pdf/0[1-9]-*.pdf; do pdftotext "$f" - | grep -q 'CLASIFICACI' || { echo "sin clasificación: $f"; exit 1; }; done   # 10-simulacro no lleva
! pdftotext /tmp/takab-pdf/02-ejecutivo.pdf - | grep -q '^\. QU'   # títulos del ejecutivo sin el «.» suelto
make lint && make drift
```

### F5 · Lista para presentar (T-8.13) · miércoles por la tarde

1. **Merge a `main`** de F1…F4. Despliegue:
   - Mauricio: `! aws sso logout && aws sso login --profile takab-dev`.
   - `terraform apply` desde `infra/terraform/envs/dev`, **nunca desde un worktree nuevo** (memoria «terraform-apply-comando-completo»); en el plan solo deben cambiar 3 clientes, in-place.
   - Nube con el procedimiento de la memoria «desplegar-la-nube-procedimiento»: `cloud-deploy` no construye imágenes, así que se construyen antes.
   - APK release al Pixel.
2. **Identidades para la demo** (Mauricio con `!`, porque el clasificador bloquea Cognito):
   - `seed_console_users.sh takab_support`;
   - inspector y building_admin con `surface=both` y un `site_scope` concreto;
   - un tenant «Protección Civil» para gov_operator, con el tenant cliente de la demo marcado `gov_shared`.
   - Después, `list-users` + grupos para verificar.
3. **Datos:** clasificar `d5af54e5` y `b420daaa` como `reproduccion`. Arreglar `guion.sh:713,143` y `RUNBOOK:367` para usar el botón CERRAR ALERTA con PIN.
4. **GUIA §0 «Sesión el día de la demo»:** un perfil de navegador por rol, abierto la misma mañana. Con D-38, la web aguanta 24 h o 30 d y sobrevive a cerrar la pestaña. Entrar en el Pixel con cada rol el miércoles.
5. **Pase final por rol en la nube:**
   - `deployed.spec.ts` ampliado a los 7 roles web;
   - `recorrido_por_rol.spec.ts` contra `PW_BASE_URL`, con los usuarios reales (Mauricio entra una vez por rol con TOTP; se guarda el `storageState` de Playwright en el scratchpad y no se comitea);
   - Maestro en el Pixel.
6. **Ensayo 2** (la segunda corrida de `T-7.28`, que se cierra en ella), con el reporte de daños precargado y un incidente con foto + onda + ShakeMap para el PDF.
7. **Congelación:** tag `presentacion-2026-09-24`. El jueves solo se usan instrumentos de lectura.

**Goal F5:**
```bash
set -e
TAG=$(curl -s https://16-58-11-196.sslip.io/api/health | jq -r .build); git merge-base --is-ancestor "$TAG" main
bash deploy/demo/goal-presentacion.sh                     # 0 = nivel A verde
AWS_PROFILE=takab-dev bash deploy/demo/guion.sh --preflight
(cd web && PW_BASE_URL=https://16-58-11-196.sslip.io npx playwright test e2e/deployed.spec.ts e2e/recorrido_por_rol.spec.ts)   # recorrido con sesiones Cognito reales por rol (storageState)
grep -q 'Ensayo 2' takab-docs/runbooks/RUNBOOK-demo-cliente.md && ! grep -q 'sin clasificar' takab-docs/runbooks/RUNBOOK-demo-cliente.md
! grep -n 'api/reset' deploy/demo/guion.sh | grep -v 'X-Takab-Pin'
```

---

## Fases DESPUÉS de la presentación (fichas escritas en F0; Goal por ficha)

- **F6 · Estatus visibles (T-8.14):**
  - `GET /sites/{id}/actuations` (`actuation_records`) + panel en `/building` y en Triage + sección en el PDF;
  - conteo agregado del pase de lista **sin PII** para el SOC (requiere ampliar la RBAC → D-nn);
  - `test_mode` del WR-1 y versión del dueño de los pines en el latido (contrato aditivo; es edge);
  - temperatura, UPS y días de certificado en la web;
  - nivel vigente por sitio (`rule_evaluations`);
  - UI de rollouts, de alarmas de ops y de `ai_spend`;
  - `relays_state=None` pintado como S/D.
- **F7 · Animaciones curadas (T-8.15)** — con las skills `find-animation-opportunities`, `animate`, `animate-expo` y `review-animations`, y con D-30:
  - defectos: el parpadeo del banner del panel del gabinete pasa a `::after` para que no atenúe la instrucción (es edge); el resorte de `ControlSheet` respeta reduce-motion; el decaimiento por fotograma del pico del panel;
  - transiciones: entrada y salida de modales y popovers, `:active`, región `role=status` para confirmar acciones, barra indeterminada en carga, tinte único al cambiar un KPI o al llegar una fila o un check-in, `RefreshControl`, transición de la crisis, hápticos (`expo-haptics`);
  - pasivas: cabeza de escritura que late solo con dato vivo, punto de BACKFILL EN CURSO, barra por fila en ENVIANDO;
  - rendimiento: el rAF del mapa solo cuando hay algo que animar, y las ondas del panel a 1 Hz;
  - **rechazadas**: nada en la toma de crisis más allá del halo D-30, nada de contar hacia arriba, nada de T-MINUS.
- **F8 · Nube (T-8.16):**
  - alarma `ApproximateAgeOfOldestMessage` + healthcheck por worker;
  - `docker compose pull` antes de migrar y `up -d` sin `down`;
  - CSP *enforce* si quedó en Report-Only;
  - logs a CloudWatch, comprobación externa de disponibilidad, métrica de memoria del EC2 y rate-limit genérico en Caddy;
  - checksum del plugin de compose.
- **F9 · Edge (T-8.17)**, con ventana de mantenimiento acordada:
  - `deploy.sh` 7.b + la poda que protege la release del dueño de los pines;
  - `cloud.publish` fuera del hilo de SeedLink;
  - watchdog real;
  - latido con memoria, subtensión, uptime, cola MQTT y `command_enabled`;
  - `temperature_c` = None en vez de 0.0;
  - RTC / `time-wait-sync`;
  - resume de SeedLink persistente.
- **F10 · Robustez móvil (T-8.18):**
  - estado `expired` que conserva la crisis con datos cacheados (spec 0.1);
  - caché de `/me` y de `mobile-state` para el arranque sin red;
  - cola offline y consentimiento por `sub` (teléfono compartido);
  - step-up biométrico opcional para comandos de actuador (compensación de D-38);
  - GPS y NTP en la marca forense.
- **F11 · Funciones que faltan (T-8.19)**, cada una con su decisión previa:
  - CRUD de zonas y pisos;
  - alta de ocupantes (autorregistro con código o QR, o invitación masiva) + padrón;
  - enrolamiento y autodiagnóstico del building_admin en `/building`;
  - reporte mensual y % de disponibilidad;
  - «prueba de canal»;
  - exportación de auditoría;
  - planos de evacuación;
  - 911 y Protección Civil en el directorio;
  - interruptor del modo demo en la UI;
  - ARCO y aviso en la UI;
  - T-2.87: usuarios reales, no SIMULADOS.

## Lo que solo Mauricio puede dar

| Cuándo | Qué |
|---|---|
| mié, mañana | Iniciar sesión en la consola desplegada para medir `auth_time` (fragmento de DevTools) |
| mié, 13:00 | `! aws sso logout && aws sso login --profile takab-dev` para `terraform apply` y el despliegue; Pixel por USB |
| mié, tarde | Crear los usuarios con `!` (support, inspector/building_admin `both`, gov en Protección Civil); TOTP en los flujos Maestro 02/05; entrar con cada rol en el Pixel; ensayo 2 con el gabinete y el WR-1 |
| jue | La presentación; nada de despliegues |

## Riesgos y su cinturón

- **`auth_time` se renueva al refrescar.** Alternativa `origin_jti` + `first_seen_at`, ya diseñada.
- **La CSP rompe MapLibre o Cognito.** Report-Only + ficha; nunca se despliega una CSP sin el recorrido desplegado en verde.
- **Un cambio de última hora rompe la demo.** Corte a las 13:00 del miércoles; lo que no está verde no entra, y la GUIA lo marca como «no se enseña».
- **Guardas de `TASKS.md`, `DECISIONES` y la matriz RBAC.** Leer las memorias correspondientes; `export_rbac_matrix.py`; `make drift`.
- **El worker de `soc-local` contamina las suites.** `pkill` antes de cada suite.
- **El Pixel no está conectado.** Se para y se pide; nunca emulador.

## Verificación de extremo a extremo

1. Los Goals F0…F5 devuelven 0, cada uno en una corrida limpia.
2. `recorrido-web.json`: 10 roles y 0 inesperados, en local **y** en la nube.
3. Maestro: los recorridos de ocupante y táctico, más 01a/01b/02/03, en verde en el Pixel.
4. Consola desplegada abierta más de 70 min sin logout; Pixel más de 70 min sin login; un soc_operator con `auth_age` de más de 24 h ve «SU SESIÓN DE 24 H TERMINÓ».
5. Las 10 variantes de PDF rasterizadas y revisadas: sin solapes y con clasificación, hora local y FIRMÓ con nombre.
6. `goal-presentacion.sh` = 0 y ensayo 2 registrado.
7. Al terminar: memoria de la sesión (fase, trampas nuevas) y `graphify update .`.
