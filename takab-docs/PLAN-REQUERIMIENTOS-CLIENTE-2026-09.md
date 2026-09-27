# Plan · BLOQUE X (T-9.xx) — lo que pidió el cliente tras la presentación del 24-sep-2026

> Revisado contra el código el 2026-09-27. Las fichas viven en el BLOQUE X de [`TASKS.md`](TASKS.md) y las
> decisiones en [`DECISIONES-MAURICIO.md`](DECISIONES-MAURICIO.md) (`D-39`…`D-48`).

## Contexto

La presentación salió bien y el cliente dejó observaciones. Ya se midió en el sistema real (ensayo 2 y
pruebas de latencia del 24-sep) lo que funciona y lo que no. Este plan convierte las observaciones en
fases ejecutables, cada una con su **Goal** (bloque bash que devuelve 0) trabajado en `/loop` hasta verde,
y se despliega al cerrar cada fase.

Lo que pidió el cliente (R1–R10):
- R1 · movimiento solo del inmueble ⇒ alerta únicamente al personal táctico, sin sonido para ocupantes;
- R2 · cuatro audios;
- R3 · menos roles;
- R4 · dictamen automático en 3 bandas;
- R5 · cierre del evento guiado paso a paso;
- R6 · mapa de calor de la sacudida (también en el PDF);
- R7 · mapa con relieve y zonas por tipo de suelo;
- R8 · sismos de México en la app del ocupante, con marcadores por tamaño y color;
- R9 · animaciones más vistosas con sismo confirmado;
- R10 · integrar lo útil de seismicai.com.

Además hay tres pendientes del 24-sep: PRs #280, #281 y #282 abiertos, y **cinco defectos de seguridad**
encontrados al explorar.

## Decisiones tomadas por Mauricio (se registran D-39…D-48 en `DECISIONES-MAURICIO.md`)

| Tema | Decisión |
|---|---|
| R1 umbral local | El ocupante no recibe **nada** (ni push ni pantalla). Push corto con voz a **brigadista, inspector y administrador**. Solo desde el escalón de **DISPARO** (`restricted`/`evacuate_or_hold`, dos canales); la CAUTELA (`watch`) se queda en la consola y el panel. La consola ve todo. SASMEX y el cuórum de red siguen avisando a todos. |
| R2 audios | **Tono propio parecido** al oficial, que sigue RESERVADO por CIRES (D-19). La voz del brigadista la genero yo con TTS es_MX. Simulacro: **voz «Esto es un simulacro» primero y durante**, sobre el tono atenuado. La música clásica **la entrega Mauricio** (grabación libre de derechos). |
| R3 roles 10→7 | **ADMINISTRADOR** (`tenant_admin`; absorbe `soc_operator` y `building_admin`; ve **todo** el cliente; **tiene además la app táctica completa**, es decir, todas las acciones del brigadista más las de administración), **INSPECTOR**, **BRIGADISTA** (absorbe `security_guard`; **los ex-guardias pasan a sesión de 30 d**), **OCUPANTE**, **GOBIERNO** (`gov_operator`). Internos sin cambio: `takab_superadmin` y `takab_support`. El `building_admin` de la demo migra a ADMINISTRADOR. |
| R4 dictamen | Tres bandas por PGA medida en el inmueble. **VERDE** < 0,04 g (MMI ≤ IV) y sin daño ⇒ el sistema firma SEGURO. **AMARILLO** 0,04–0,10 g o daño no estructural ⇒ el sistema dictamina y pide confirmar a un brigadista o al inspector. **ROJO** ≥ 0,10 g, o daño estructural, o personas atrapadas, o fuga de gas ⇒ inspector obligatorio. Sin calibración declarada nunca es automático. Se usa la calibración del fabricante (StationXML AM.R4F74), **que el sensor real ya tiene declarada**: lo que falta es retirar los sensores fantasma (ver hallazgos). |
| R6 mapa de calor | Superficie **ESTIMADA** rotulada («a partir de N sensores»), rojo/amarillo/verde + **MMI estimada solo post-evento** (Wald 1999). Enmienda D-08. |
| R7 suelos | Relieve con AWS Terrain Tiles. Zonas: **NTC de la CDMX** (lomas, transición, lago) + **edafología del INEGI** para el resto, con atribución. |
| R8 catálogo | **USGS ya, M ≥ 4.0**. SSN cuando se cierre D-06. Sin cuenta regresiva ni magnitud preliminar. |
| R9 animaciones | Vistosas con los 3 límites de D-30: el texto nunca se mueve, se apagan por el estado del servidor, respetan «reducir movimiento». |
| R10 SeismicAI | Sí: **reporte automático post-evento (≤ 30 min)**, **contactos de emergencia** (≤ 3 en la nube, con consentimiento y ARCO; correo ya, SMS cuando se contrate), **historial por inmueble**. No: 3 ubicaciones por ocupante. |
| Método | Desplegar **al cerrar cada fase**. Sin fecha fija: primero la seguridad. |

**Las diez decisiones que T-9.00 escribe** (cada una con su cabecera, fila en el índice y ancla, que
es lo que vigila `test_docs_consistency.py`):

| D | Qué decide | Qué enmienda |
|---|---|---|
| D-39 | Un incidente local no corroborado desde DISPARO ⇒ push MOVEMENT con voz solo a brigadista, inspector y administrador; el ocupante nada; la escalada re-notifica a todos | T-2.105 (solo ocultaba al ocupante; ahora también enruta el push) |
| D-40 | Catálogo de audio v2: tono propio «parecido, no idéntico», voz del brigadista, música de prueba con manifiesto de licencias | D-19 (la razón 1: el sonido «hecho a mano») |
| D-41 | El simulacro habla «Esto es un simulacro» antes y durante, sobre el tono atenuado | Regla T-5.17 «un simulacro nunca suena a sismo» y RUNBOOK §C.2 |
| D-42 | Roles 10→7 con etiquetas; ventana de alias y baja; `building_admin` mapeado por usuario; ex-guardias a 30 d; ADMINISTRADOR con la app completa | RBAC-TAKAB §1–4, la tabla de D-38, la nota de D-35 |
| D-43 | `dictamen-v2` en tres bandas, firma del sistema, confirmación brigadista/inspector; cierre = dictamen + clasificación, explícito, terminal o TTL | La regla v1 «SASMEX ⇒ NO HABITAR sin importar la PGA», T-1.20 y D-33 |
| D-44 | Superficie de calor ESTIMADA + MMI estimada (Wald 1999) + cartografía base embebida en el PDF | D-08, T-7.24 «sin interpolar / sin MMI», `NO_MMI`, T-2.41 «SIN CARTOGRAFÍA BASE» |
| D-45 | Relieve (terrarium) + NTC CDMX + edafología INEGI, con atribución; «tipo de suelo» no es zonificación sísmica | CSP (T-8.16) |
| D-46 | Catálogo USGS de México para el ocupante, MMI estimada solo post-evento; mapa en la app por WebView | D-06 (SSN después) |
| D-47 | Animaciones v2: toma de pantalla, ondas, borde pulsante; los límites de D-30 se conservan; arreglo del parpadeo del panel | D-30 |
| D-48 | Lo de SeismicAI: reporte automático ≤ 30 min, contactos de emergencia (PII con consentimiento), historial por inmueble | — |

## Hallazgos verificados que cambian el diseño (P0 de seguridad)

1. **El umbral local despierta a todos.** `notify/orchestrator.py::_enqueue` nunca mira el `trigger`: un
   `local_threshold` manda «ALERTA SÍSMICA» con el canal que ignora el No Molestar. Luego
   `routers/mobile_site.py:218` oculta ese incidente a **todos**, brigadistas incluidos.
2. **Un empate en la escalada oculta un SASMEX real.** Un umbral local en `evacuate_or_hold` seguido de
   SASMEX en el mismo episodio empata: `_EVENT_SQL` (`ingest/handlers.py:267`) no reescribe el `trigger`,
   así que `autoriza_evacuacion()` da falso y **el ocupante no ve la alerta**. Además, la escalada nunca
   re-notifica.
3. **Un NO HABITAR firmado caduca solo.** La firma cierra el incidente
   (`incident/lifecycle.py:207`) y `mobile-state` solo re-declara dictámenes habitables: la app vuelve a
   «en calma» y el edificio queda desbloqueado. Firmar sobre un incidente cerrado **sí está
   permitido hoy** (`routers/dictamens.py::sign_dictamen` no mira el estado): es la vía para levantar
   después un NO HABITAR.
4. **«REINGRESO AUTORIZADO» aparece en reposo.** `queries/mobile.py::REENTRY_STILL_DECLARED` no filtra
   `autoriza_evacuacion`, y `OPEN_INCIDENT` (`LIMIT 1`) deja que uno local más nuevo tape a uno autorizante.
5. **El token de push es del aparato.** La RLS `pt_self` impide que el siguiente usuario del teléfono lo
   registre. El test rojo está guardado en `git stash` como «test-token-compartido».

Otros hallazgos que condicionan el diseño:
- **El dictamen mide UN sensor cualquiera.** `dictamen/service.py:63` elige `LIMIT 1` por
  `sensor_id` **sin filtrar `status`**. Puebla tiene tres filas de sensor estructural: `R4F74`, que ya
  lleva `calibration_source = StationXML AM.R4F74` (PDF §10, aplicado el 2026-07-09), y dos «serie S/N»
  sin calibración. Por eso el PDF dice «SIN FUENTE DE CALIBRACIÓN DECLARADA». `sensors.status` admite
  `retired` y ya existe `queries/sensors.py::_RETIRE`.
- **El mapa de la sacudida** solo se calcula tras `in_review` y dentro de 6 h
  (`shakemap/servicio.py:153`); por eso hay 0 mapas en la nube. Un mapa `completo` **no se recalcula
  jamás** (`servicio.py:34`).
- **El push por rol** (T-2.147.a) se apoya en `user_zone_assignments`, y los tácticos no tienen fila ⇒ el
  rol se guarda en `push_tokens`.
- **La app solo admite como tácticos** a brigadista, security_guard, inspector y building_admin
  (`mobile/src/auth/profileGate.ts::TACTICAL_ROLES`). Para que el administrador reciba y atienda el aviso
  de movimiento, entra en esa lista y hereda las acciones de campo.
- **Las literales de rol en la RLS** solo nombran `tenant_admin`, `takab_*` y `gov_operator` ⇒ R3 no
  necesita migración de RLS si se conservan esos ids.
- **`incident_actions.kind` es texto libre** (sin CHECK): las acciones nuevas no piden migración,
  solo entran al censo `incidentActionKinds` de la web.
- **`takab_ingest` es el único rol con BYPASSRLS** (`schema.sql:49`): una función
  `SECURITY DEFINER` suya salta `pt_self`, conserva los GUC de sesión (`schema.sql:1285`), y hoy solo
  tiene `SELECT, UPDATE` sobre `push_tokens`.
- **El PDF solo es vectorial.** La API no tiene matplotlib ni scipy ⇒ la superficie se hace en numpy puro
  + Pillow, sin dependencias nuevas.
- **La app no tiene `react-native-webview` ni `expo-haptics`**; sí `expo-location`,
  `expo-audio` y Reanimated 4.5. Cualquier mapa en la app es una APK nueva.
- **No hay Git LFS.** Nada de artefactos de decenas de MB en el repo.

## Método (todas las fases)

- **Fichas.** Una por tarea (`T-9.xx`) en el **BLOQUE X** de `TASKS.md`, con criterios de aceptación.
  Recontar la cabecera en el mismo commit. Las fichas `T-8.14…T-8.19` que este bloque absorbe (T-8.15 por
  T-9.73; T-8.18 en parte por T-9.05/T-9.06) lo dicen en su texto.
- **Goal.** Cada fase lo corre en `/loop` hasta verde. Si tras **3 iteraciones** sigue rojo, se para y se
  reporta (CLAUDE.md §6).
- **TDD.** El test se escribe primero y falla por la razón correcta.
- **Subagentes.** Como mucho **2 a la vez**, con ficheros disjuntos y cada uno con su base
  (`takab_test_a` / `takab_test_b`). Un solo agente por lote crea migraciones.
- **Contratos.** Cualquier cambio de esquema Pydantic (fases, campos) ⇒ regenerar OpenAPI +
  `shared/sdk-ts` + `make drift` (que solo vale después del commit).
- **Integración.** Commits por ruta, nunca `git add -A`. `graphify update .` después de cambiar código.
  Ficheros temporales en `$CLAUDE_JOB_DIR/tmp`.
- **Git.** Conventional Commits, autor Mauricio, **sin coautoría de IA** (§0.2). Un PR por fase; se mergea
  con el CI en verde.
- **Despliegue por fase:**
  1. **APK primero** si hay fases o canales nuevos (una APK vieja no conoce las fases nuevas).
  2. Nube: `make cloud-images && make cloud-deploy`. Mauricio hace antes `! aws sso logout && aws sso login --profile takab-dev`.
  3. Edge: `deploy/edge/deploy.sh` desde `main` con el CI en verde.
- **Escrituras reales.** Cognito, terraform y la base de producción las corre **Mauricio con `!`**, con
  comandos cortos y uno por bloque (memoria «comandos-con-bang-se-parten»).
- **Antes de cada suite:** `pkill -f "[t]akab_api.incident"`, con el patrón entre corchetes para que no
  mate al propio comando. En `api/` no hay `uv run ruff`: se usa `uvx ruff@0.15.20`. En `mobile/` el CI es
  `npm test && npm run typecheck && npm run lint`; en `web/`, `npm run lint && npm run format:check && npx vitest run && npm run build`.

---

## Fases

### F0 · Pendientes + P0 de seguridad  *(bloquea todo)*

| Ficha | Qué | Archivos clave |
|---|---|---|
| T-9.00 | BLOQUE X en `TASKS.md`, `PLAN-REQUERIMIENTOS-CLIENTE-2026-09.md` y D-39…D-48 (cabecera, índice y ancla). | takab-docs/ |
| T-9.01 | Mergear #281, luego #282 y luego #280. Descartar la copia local de los 2 ficheros de `edge/` (idéntica a #282). `skills-lock.json` y `.agents/skills/*` son de las sesiones del video: **no se tocan ni se comitean aquí**. Redesplegar la nube y desplegar el edge desde `main`, lo que quita la release `-dirty`. | — |
| T-9.02 | **Precedencia de disparador.** `TRIGGER_RANK` (manual < local < quorum < sasmex) en `settings.py`, junto a `SEVERITY_RANK`. `_EVENT_SQL` reescribe el `trigger` si sube su rango y nunca degrada severidad ni nivel; `opened_trigger` no se toca. La narrativa IA recibe `opened_trigger` y `trigger`. | ingest/handlers.py, narrative/prompts.py |
| T-9.03 | **La escalada re-notifica a todo el edificio.** `_enqueue_escalations` escribe la acción `alert_escalated` y un push CRISIS anclado a esa acción (patrón `_INSERT_PUSH_ACTION_JOB_SQL`, índice `uq_notification_jobs_action`). Migración **0070** con índice único parcial sobre `incident_actions(incident_id) WHERE kind='alert_escalated'`. | notify/orchestrator.py |
| T-9.04 | **Reingreso persistente.** El incidente abierto que autoriza gana entre los ≤ 5 abiertos. Fase nueva `reentry_blocked` con `reason` = `no_habitable`, `pendiente_dictamen` o `pendiente_confirmacion`. La app ya tiene el estado `reentry_blocked` (`machine.ts`, `ReentryBlockedView`): se reutiliza; `no_habitable` pinta el bloqueo rojo y los `pendiente_*` una franja ámbar informativa. Reglas: una clasificación terminal (`falso_positivo`, `prueba`, `reproduccion`) ⇒ `idle` siempre; un NO HABITAR firmado **no caduca** y solo lo levanta un dictamen habitable firmado después sobre ese incidente; los `pendiente_*` miran 30 d hacia atrás; «REINGRESO AUTORIZADO» se muestra 8 h desde la **firma** (no desde el cierre) y solo si el incidente autorizó evacuar. `fase_del_sitio` pasa a ser una tabla explícita de precedencia. | routers/mobile_site.py, queries/mobile.py, commands/alarma_inmueble.py |
| T-9.05 | **El token es del aparato.** Migración **0071**: `push_tokens.role` + `app_claim_push_token()` SECURITY DEFINER **con dueño `takab_ingest` (BYPASSRLS) y `GRANT INSERT ON push_tokens TO takab_ingest`**; la identidad solo sale de los GUC de sesión, y si el token cambia de dueño se audita en los dos tenants. El dueño de la función se fija en la migración (test de dueños). Se saca del stash el test rojo. Los tokens ya registrados ganan `role` en cuanto la app se abre (registra en cada arranque). | routers/mobile_me.py |
| T-9.06 | La app vibra en crisis (`Vibration.vibrate`, patrón en bucle; **verificar `VIBRATE` en el manifest tras `prebuild`, `app.json` hoy solo declara `USE_BIOMETRIC`**). `machine.ts` gana `default` → `idle`. | mobile/src/features/alert |

**Tests primero:**
- `test_ingest_handlers.py`: local@evac seguido de sasmex ⇒ `trigger=sasmex`; nunca degrada.
- `notify/test_escalada_avisa_a_todos.py`.
- `api/test_reingreso_persistente.py`: un NO HABITAR sigue bloqueando a las +9 h y a los +3 d; una
  firma habitable posterior lo levanta; un incidente solo local ⇒ `idle`; uno local nuevo no tapa a un NO
  HABITAR; `reproduccion` ⇒ `idle`.
- `test_push_tokens_site.py`: el test del stash.

**Goal F0**
```bash
set -euo pipefail
for pr in 280 281 282; do test "$(gh pr view $pr --json state -q .state)" = MERGED; done
! git stash list | grep -q test-token-compartido
(cd api && uv run pytest -q tests/test_ingest_handlers.py tests/notify tests/api/test_reingreso_persistente.py \
  tests/api/test_mobile_core.py tests/api/test_push_tokens_site.py tests/narrative tests/test_schema_espejo_de_migraciones.py \
  tests/test_owners_migrator.py tests/test_rls_isolation.py tests/test_docs_consistency.py && uvx ruff@0.15.20 check . && uvx ruff@0.15.20 format --check .)
(cd mobile && npm test && npm run typecheck && npm run lint)
(cd web && npm run lint && npm run format:check && npx vitest run && npm run build)
test "$(curl -fsS https://16-58-11-196.sslip.io/api/health | jq -r .build)" = "$(git rev-parse --short origin/main)"
```

### F1 · R1 antipánico + voz del brigadista  *(D-39)*

| Ficha | Qué |
|---|---|
| T-9.10 | **Canal de audio auditable.** Carpeta `tools/audio/`: `gen_tonos.py` (numpy, determinista), `gen_voces.sh` (Piper es_MX con `uvx`, GPL aislado del repo, modelo fijado por sha256), `mezcla.py`, `normaliza.py` (pyloudnorm: −14 LUFS en el edge, −16 en el teléfono, ≤ −1 dBTP). `shared/audio/MANIFEST.json` guarda sha256, duración, LUFS, fuente y licencia; lo vigila `test_censo_audio.py`. Primer asset: `movimiento_inmueble.wav`, ≤ 4 s. |
| T-9.11 | **Clase de push MOVEMENT** con canal Android `building_movement_v1` (MAX, ignora No Molestar, sonido de voz; también en `app.json` para iOS). Acción nueva `movement_alert` para brigadista, security_guard, building_admin, inspector y tenant_admin (F2 los reduce a tres). `push_target_for(trigger, severity, autoriza)` es pura: un local sin corroborar con severidad `warning`/`critical` (DISPARO) ⇒ MOVEMENT a esos roles; un local en `watch` ⇒ **ningún push**; todo lo demás ⇒ CRISIS a todos. `_PUSH_DEVICES_BY_ROLE_SQL` usa `push_tokens.role`. `mobile-state` depende del rol: el táctico ve la fase `building_movement` y el ocupante nunca. `ws.py` deriva los roles tácticos de la matriz. **El administrador entra en la app:** `TACTICAL_ROLES += tenant_admin` y `tenant_admin` hereda en `matrix.py` las acciones de campo del brigadista. En la app, la pantalla táctica «MOVIMIENTO EN EL INMUEBLE» reutiliza `TacticalAckButton` y la entrada al reporte de daños. |

- **Tests primero:** `notify/test_movimiento_solo_brigada.py` (ocupante 0 pushes, brigadista 1; local en `watch` 0; sasmex ⇒ CRISIS; local con ≥ 3 nodos ⇒ CRISIS) y el censo `test_censo_canales_y_sonidos.py`.
- **Orden de despliegue:** APK → Pixel → nube. El administrador necesita `custom:surface=both` en Cognito para tener la app (lo pone Mauricio con `!`).

**Goal F1**
```bash
set -euo pipefail
(cd api && uv run pytest -q tests/notify tests/api/test_mobile_core.py tests/test_censo_audio.py tests/ws tests/auth && uvx ruff@0.15.20 check .)
(cd mobile && npm test && npm run typecheck && npm run lint)
(cd web && npm run lint && npm run format:check && npx vitest run && npm run build)
python3 tools/audio/verifica_manifiesto.py
```
**Verificación en el Pixel:** golpe local hasta DISPARO ⇒ el brigadista oye la voz y el ocupante nada. Se mide con `latencia/bloqueado.sh`, reutilizado.

### F2 · R3 roles 10 → 7  *(D-42)*

| Ficha | Qué |
|---|---|
| T-9.20 | **Alias heredados.** `auth/roles.py`: `CANONICAL_ROLES` (7), `ROLE_LABELS` y `LEGACY_ROLE_ALIASES` (`soc_operator` → `tenant_admin`, `security_guard` → `brigadista`, `building_admin` → `brigadista` por defecto y `tenant_admin` para el de la demo). `Claims.from_verified` comprueba el rol **crudo** contra los grupos (antifalsificación) y después lo canoniza. Tras la fecha de baja ⇒ 401 «rol retirado». El `app.role` de la base es siempre el canónico, así que la RLS no cambia. `tenant_admin` gana `generate_report`, `close_incident` y (desde F1) las acciones de campo, y **sigue sin alcance por inmueble**. Los ex-guardias pasan a **30 d** (D-42 lo declara). Se regeneran `export_rbac_matrix.py` y `shared/fixtures/rbac-matrix.json`. Web: LoginPage, UsersCard (opciones desde `GET /users/assignable-roles`), meFixtures, e2e por rol. Móvil: profileGate (táctico = brigadista, inspector, tenant_admin), DirectoryList, pestañas. Semillas a 7. Los grupos heredados de Cognito **se quedan** durante la ventana. Documentos: RBAC-TAKAB, cognito-pool-v1, GUIA, ESPECIFICACION-APP-MOVIL y CLAUDE.md «10 roles». |
| T-9.21 | **Migración de Cognito** `api/scripts/migrar_roles_7.py`: `--dry-run`, `--apply --map usuario=rol` y `--verify`. Se niega a aplicar si algún `building_admin` no tiene su mapeo. Orden: agregar el grupo nuevo → cambiar `custom:role`/`surface` → quitar el grupo viejo. Reutiliza `CognitoDirectory.update_user`. **Lo corre Mauricio con `!`** (dry-run → apply → verify). |
| T-9.22 | Censos a 7: `test_rbac_fixture_es_la_matriz`, `test_duracion_sesion_doc`, `test_matriz_trazabilidad`, `test_docs_consistency`, `test_session_age`, `test_matrix`, `test_role_matrix`, `test_rotulos`, y los de roles de web y móvil. Las filas históricas **no se reescriben**: el rol se canoniza al leerlo, `ROL_HISTORICO` etiqueta los PDF viejos y la web guarda las etiquetas viejas en un único `rolesHistoricos.ts`. |

- **Tests primero:** un token heredado `security_guard` ⇒ 200 como brigadista; un token falsificado (rol `soc_operator` con grupo brigadista) ⇒ 401; después de la baja ⇒ 401.

**Goal F2**
```bash
set -euo pipefail
(cd api && uv run pytest -q tests/auth tests/ws tests/api tests/dictamen/test_rotulos.py tests/test_matriz_trazabilidad.py tests/test_docs_consistency.py)
(cd api && uv run python scripts/export_rbac_matrix.py) && git diff --exit-code shared/fixtures/rbac-matrix.json
python3 -c "import json;assert len(json.load(open('shared/fixtures/rbac-matrix.json'))['roles'])==7"
! grep -rnE "\b(soc_operator|security_guard|building_admin)\b" web/src mobile/src --include=*.ts --include=*.tsx | grep -v "\.test\.\|rolesHistoricos"
(cd web && npm run lint && npm run format:check && npx vitest run && npm run build)
(cd mobile && npm test && npm run typecheck && npm run lint)
(cd infra/terraform/modules/identity && terraform init -backend=false -input=false >/dev/null && terraform test)
```
**Cierre:** el `--verify` de Mauricio da 0 miembros en los grupos heredados, y el recorrido web por rol
(`e2e/recorrido_por_rol.spec.ts` contra `vite preview`) pasa con los 7.

### F3 · R4 dictamen automático  *(D-43)*

| Ficha | Qué |
|---|---|
| T-9.30 | **`dictamen-v2` puro** (`dictamen/rules.py::evaluate_v2`; v1 se conserva para el historial). **ROJO**: PGA ≥ 0,10 g, o daño `structural`, `people_trapped` o `gas_leak`. **AMARILLO**: PGA entre 0,04 y 0,10 g, o daño no estructural, o **sin PGA, o algún sensor activo sin calibrar**. **VERDE**: PGA < 0,04 g, todos los sensores activos calibrados y sin reportes. Una alerta SASMEX **deja de forzar** NO HABITAR. La PGA es el máximo de **todos los sensores con `status='active'`** del sitio (hoy `LIMIT 1` sin filtro), y los umbrales vienen de `rule_sets.config.dictamen_v2`. |
| T-9.31 | **Firma del sistema y confirmación.** Migración **0072**: `dictamens.signature_kind` (`inspector`, `system` o `confirmation`) y `band`. El firmante del sistema es `SYSTEM_DICTAMEN_SIGNER_UUID`, como `QUORUM_ACTOR_UUID`. VERDE se firma solo tras volver a `normal` + 300 s de gracia. `POST …/dictamens/{id}/confirm` (acción `confirm_dictamen`, brigadista o inspector): 409 si ya no es la cabeza y 403 si la cabeza es ROJO. La prudencia sube sola y **solo baja con firma**. Un reporte de daño en las 72 h siguientes re-evalúa. |
| T-9.32 | **Cierre v2** (`lifecycle.py`): se cierra con cabeza firmada de cualquier tipo **y** clasificación, con clasificación terminal, con cierre explícito o por TTL. El TTL declara lo que faltaba. Un VERDE automático sin clasificación humana se cierra por TTL a las 6 h; el reingreso ya estaba autorizado desde la firma, porque la fase se deriva por sitio. |
| T-9.33 | **Confirmación del brigadista** en la app. Cuando sale un AMARILLO, push OPS a los tácticos (acción `dictamen_confirm_requested`), con una pantalla de checklist → CONFIRMAR o ESCALAR A INSPECTOR. |
| T-9.34 | **El papel dice quién firmó** («EMITIDO POR EL SISTEMA · regla dictamen-v2 · banda VERDE», o el nombre del brigadista/inspector). En la web, el desplegable de firma arranca en el estado de la cabeza. |
| T-9.35 | **Sensores fantasma.** Script de diagnóstico **de solo lectura** `infra/scripts/diagnostico_sensores.sh` (túnel SSM, lo corre Mauricio con `!`): lista los sensores de cada sitio con `status`, `calibration_source` y cuántas filas de `waveform_features_1s` tienen. Los dos «serie S/N» de Puebla sin datos ni calibración se **retiran** desde la consola (DAR DE BAJA, que ya usa `_RETIRE`) o, si la UI no lo ofrece, con un script de `!` que muestra antes lo que cambia. No hay que «declarar» nada en `R4F74`: ya lleva la StationXML del fabricante. |

- **Tests primero:** `dictamen/test_bandas_v2.py` (tabla de casos, incluido «un sensor retirado sin calibrar no impide el VERDE»), `api/test_confirmar_dictamen.py`, `incident/test_lifecycle_pass.py` y `api/test_reingreso_persistente.py` (VERDE ⇒ `reentry_approved`; AMARILLO sin confirmar ⇒ `reentry_blocked(pendiente_confirmacion)`).

**Goal F3**
```bash
set -euo pipefail
(cd api && uv run pytest -q tests/dictamen tests/incident tests/api/test_dictamens.py tests/api/test_confirmar_dictamen.py \
  tests/api/test_reingreso_persistente.py tests/notify tests/test_append_only.py tests/test_schema_espejo_de_migraciones.py && uvx ruff@0.15.20 check .)
(cd mobile && npm test && npm run typecheck && npm run lint) && (cd web && npx vitest run src/features/triage && npm run format:check)
```

### F4 · R5 asistente «Cierre del evento» + reporte automático  *(D-48, parte 1)*

| Ficha | Qué |
|---|---|
| T-9.40 | **Cierre explícito** `POST /incidents/{id}/close` (acción `close_incident`, administrador y superadmin), con estos requisitos: estado `acked` o `in_review`, una clasificación hecha y, si es `real` o `indeterminado`, una cabeza firmada o un motivo de ≥ 20 caracteres (auditado como `cierre_sin_dictamen`). |
| T-9.41 | **Asistente** en `web/src/features/cierre/`, ruta `/triage/:id/cierre` (bajo la guarda de `/triage`). `pasos.ts` es puro y **cada «hecho» es un hecho del servidor**. Pasos: **1 Acusar** (`useIncidentAck`) · **2 Revisar la sacudida** (métricas, mapa de calor, estaciones, CCTV: `useForensics`, `useShakemap`, `useEstaciones`) · **3 Reportes de campo** (`useDamageReports` + pase de lista) · **4 Dictamen** (explica la banda, qué es automático, quién confirma o firma; `useIncidentDetail` + `useDictamenConfirm`; **sobre un incidente cerrado con NO HABITAR ofrece al inspector LEVANTAR RESTRICCIÓN**, que es una firma habitable nueva) · **5 Clasificar** (`useClassification`, con confirmación que avisa que FALSO POSITIVO, PRUEBA y REPRODUCCIÓN cierran) · **6 Informe y cierre** (PDF + CERRAR EVENTO). Botones grandes, explicación en cada paso y «quién puede» cuando falta un rol. Entradas: una fila de la tabla de la consola, la cabecera de Evaluación y el banner en revisión. `@takab/sdk` se importa perezoso. |
| T-9.42 | **Reporte automático ≤ 30 min**, al estilo ShakeReport. Worker `informes` en compose (lo exige `test_compose_cubre_los_workers`). `routers/reports.py` se parte en un núcleo síncrono común. Se dispara con la cabeza firmada o con el cierre, lo que llegue primero; el del cierre trae ya la clasificación, y el paso 6 del asistente regenera el definitivo. Luego manda correo a los destinatarios de la cascada del sitio + push OPS al administrador y a los tácticos. Migración **0073**: `post_event_reports`, que nunca se poda (censo de purga) y en la que la app no escribe (lección de la 0069). |

- **Tests primero:** `api/test_cierre_explicito.py`, `informes/test_pasada.py` (idempotente; si falla queda `fallido`, nunca `ok`), `cierre/pasos.test.ts`, `CierreWizard.test.tsx` por rol y `e2e/cierre_del_evento.spec.ts` (contra `vite preview`, con `make soc-local` de API detrás).

**Goal F4**
```bash
set -euo pipefail
(cd api && uv run pytest -q tests/api/test_cierre_explicito.py tests/informes tests/test_compose_cubre_los_workers.py tests/test_censo_de_la_purga.py tests/incident && uvx ruff@0.15.20 check .)
(cd web && npm run lint && npm run format:check && npx vitest run && npm run build)
T=$CLAUDE_JOB_DIR/tmp; setsid nohup make soc-local >$T/soc-local.log 2>&1 & disown
until curl -sf localhost:5173 >/dev/null; do sleep 2; done
(cd web && setsid nohup npx vite preview --port 4173 >$T/preview.log 2>&1 & disown); until curl -sf localhost:4173 >/dev/null; do sleep 1; done
(cd web && PW_BASE_URL=http://localhost:4173 npx playwright test e2e/cierre_del_evento.spec.ts)
pkill -f "[v]ite preview"; pkill -f "[s]oc_local.py"; pkill -f "[t]akab_api.incident"; true
```

### F5 · R6 mapa de calor + R7 relieve y suelos  *(D-44, D-45)*

| Ficha | Qué |
|---|---|
| T-9.50 | **El mapa siempre se calcula.** El requisito `in_review` se cambia por `opened_at ≤ now − 120 s`. Como un `completo` no se recalcula jamás, el mapa **no se declara `completo` hasta que cierre la ventana del pico** (`opened_at + dictamen_pga_window_post_s`, 180 s) o el incidente entre en `in_review`; hasta entonces se rehace cada 60 s. El PDF lo calcula a demanda si no existe (`servicio.calcula_uno`). Hay un CLI de relleno para el histórico, que Mauricio corre con `!`. |
| T-9.51 | **Superficie ESTIMADA** (`shakemap/superficie.py`, numpy puro). Parte de la ley ATTEN-LAW (`geo.pga_law_g`) como base, le suma los residuales de las estaciones activas y calibradas con peso gaussiano (L = 15 km) y los encoge hacia la ley lejos de ellas. Distingue una zona AJUSTADA (< 2L) y otra MODELADA. `gmice.py` da la MMI con Wald 1999, y los colores coinciden con las bandas de R4. Se guarda como una malla de ≤ 96×96 en `incident_shakemap.superficie` (migración **0074**). `raster.py` (Pillow) hace el PNG, que se sirve en `GET /incidents/{id}/shakemap/superficie.png`. **Sin dependencias nuevas.** |
| T-9.52 | **En la consola:** capa `image` de MapLibre con los puntos medidos encima y la leyenda «ESTIMADO a partir de N sensores (M calibrados) · MMI estimada (Wald 1999), no observada». |
| T-9.53 | **En el PDF §8:** el mismo PNG sobre la cartografía base **embebida** (estados + NTC en GeoJSON dentro de `api/src/takab_api/geodatos/`, ≤ 2 MB; **declarados en `[tool.setuptools.package-data]`**, como las fuentes). `NO_MMI` sale solo si no hay superficie, y `MMI_ESTIMADA` solo si la hay. |
| T-9.54 | **Relieve + suelos.** `tools/geodatos/` (fuentes con sha256). El relieve (terrarium) va **directo desde AWS**, como ya van los teselados de openfreemap, con su host añadido a `img-src`/`connect-src` del CSP. La NTC de la CDMX como GeoJSON ≤ 1,5 MB en `web/public`. La edafología del INEGI se simplifica hasta caber en **≤ 6 MB de GeoJSON** cargado solo al activar la capa; si no cabe, se publica como PMTiles en un bucket S3 de estáticos (terraform) y **no en el repo** (no hay LFS). `shared/geodatos/atribuciones.json` es la única fuente de las atribuciones en la consola, el PDF y la app. El rótulo es «tipo de suelo», que **no es** zonificación sísmica salvo en la NTC. |

- **Tests:** `shakemap/test_superficie.py` (puntos de control de Wald, encogimiento, máscara, exclusión de sensores sin calibrar o retirados, determinismo), `test_raster.py`, `test_enganche_al_worker.py` (el paso que habla con terceros sigue último), `dictamen/test_mapa_de_la_sacudida.py`, `MapPanel.test.tsx` y `tools/geodatos/verifica.py` (atribución + sha256).

**Goal F5**
```bash
set -euo pipefail
(cd api && uv run pytest -q tests/shakemap tests/dictamen tests/test_settings_produccion.py && uvx ruff@0.15.20 check .)
(cd web && npm run lint && npm run format:check && npx vitest run src/features/console && npm run build)
python3 tools/geodatos/verifica.py
du -cb api/src/takab_api/geodatos/* | tail -1 | awk '$1<2500000{ok=1} END{exit !ok}'
```
**Revisión visual:** `render-pdfs.sh` → `pdftoppm` → leer el §8 con la superficie.

### F6 · R8 catálogo de México + mapa en la app + historial por inmueble  *(D-46, D-48 parte 2)*

| Ficha | Qué |
|---|---|
| T-9.60 | **Worker `catalog-sync`**, un servicio compose aparte, cada 600 s. Consulta USGS con la caja de México (lat 14–33,5; lon −118,5 a −86), M ≥ 4.0 y `updatedafter`. Reutiliza `catalogo/fdsn.py::parsea`. Hace upsert por `(source, provider_event_id)` y nunca pisa las filas de `seed`. Migración **0075**: `origen`, `usgs_mmi`, `usgs_url` y `catalog_sync_state` global (excepción documentada en el censo multitenancy). Si falla, se declara; nunca queda `ok`. |
| T-9.61 | **Endpoints.** `/catalog/earthquakes` de la web se pagina. `GET /mobile/catalog/earthquakes?dias=90&min_mag=4.0` es para todos los roles móviles y trae `por_sitio` (distancia, PGA y MMI **estimadas**) con la atribución «Fuente: USGS (dominio público)». |
| T-9.62 | **Pantalla SISMOS** en la app, para el ocupante y los tácticos: lista con magnitud, lugar, hora y MMI estimada en su inmueble. |
| T-9.63a/T-9.63 | **Spike medido en el Pixel** entre `react-native-webview` + MapLibre GL empaquetado (**ninguno está instalado hoy**) y `@maplibre/maplibre-react-native`, y luego la implementación que gane. Obliga a una APK nueva. |
| T-9.64 | **Una sola escala** `shared/fixtures/escala-sismos.json`: tamaño por magnitud y color por MMI estimada, que usan la consola (los ◇ del catálogo dejan de tener tamaño fijo) y la app, con un test cruzado. La leyenda dice «tamaño = magnitud». |
| T-9.65 | Superficie estimada del último evento en la app. |
| T-9.66 | **Historial por inmueble:** `GET /sites/{id}/historial-sismico` (sus incidentes + los sismos del catálogo con MMI estimada ≥ III en el sitio), en `BuildingPage` y en una tarjeta de la app. |

**Goal F6**
```bash
set -euo pipefail
(cd api && uv run pytest -q tests/catalogo tests/api/test_catalogo_movil.py tests/api/test_historial_sismico.py tests/test_compose_cubre_los_workers.py tests/test_censo_multitenancy.py tests/shakemap/test_enganche_al_worker.py)
(cd mobile && npm test && npm run typecheck && npm run lint) && (cd web && npx vitest run && npm run format:check)
TAKAB_MAESTRO_ENV=.env.e2e mobile/.maestro/run.sh catalogo-sismos.yaml   # Pixel real, nunca emulador
```

### F7 · R2 resto de audios + R9 animaciones  *(D-40, D-41, D-47)*

| Ficha | Qué |
|---|---|
| T-9.70 | **Tono propio v2** («parecido, no idéntico»). En el edge, `takab-siren-v2`, conservando v1 para volver atrás. En la app, `alerta_sismica_v2.wav` + canal **`seismic_alert_v4`** con vibración y uso de audio ALARMA; se crea v4 y se borra v3 (`_v3` lo ocupó T-9.12). Orden: APK → nube → configuración firmada por `rule_sets.config.edge.audio`. |
| T-9.71 | **Simulacro hablado** `takab-simulacro-v2`: 2,5 s solo de voz, luego voz sobre el tono a −15 dB, con la frase ≥ 4 veces. Un invariante nuevo en `edge/tests/test_audio_simulacro.py` sustituye al de «nunca suena a sismo». Se actualiza el RUNBOOK §C.2. |
| T-9.72 | **Música para probar parlantes** (las pistas las entrega Mauricio, con licencia de la GRABACIÓN en el manifiesto; **si no hay grabación libre, la alternativa es sintetizar una pieza de dominio público con numpy, sin licencia que revisar**). WAV de 22,05 kHz, ≤ 6 MB por pista y ≤ 12 MB en total (van en el repo y en la release del edge). En el edge, `start_music`/`stop_music`: bucle con tope de 30 min, cualquier alerta o simulacro la interrumpe y da 409 si hay una alerta viva. En el panel, PRUEBA DE AUDIO CONTINUA / DETENER con PIN, y el estado `audio.music` pasa por el censo de render. `test_deploy_artifacts.py` no vigila tamaños: se añade una cota nueva para `audio/assets`. |
| T-9.73 | **Animaciones v2** (absorbe T-8.15): toma de pantalla en la consola solo para alertas **autorizantes**, ondas P y S geográficas (en km) desde el epicentro (`wavefront.ts`), borde de pantalla pulsante y entrada del cartel detrás de un texto que no se mueve. En la app, anillos con Reanimated + vibración. En el panel, quitar `tk-blink` del texto (viola D-30) y pulsar un pseudo-elemento. Todo con `prefers-reduced-motion: reduce` y en `motionInvariants.test.ts`. |

**Goal F7**
```bash
set -euo pipefail
(cd edge && GPIOZERO_PIN_FACTORY=mock uv run pytest -q tests/test_audio.py tests/test_audio_simulacro.py tests/test_audio_musica.py tests/test_panel_render_census.py tests/test_local_api_panel.py tests/test_deploy_artifacts.py tests/test_cota_de_assets.py)
(cd api && uv run pytest -q tests/notify/test_censo_canales_y_sonidos.py tests/test_censo_audio.py)
(cd web && npx vitest run src/styles/motionInvariants.test.ts src/features/console && npm run format:check)
(cd mobile && npm test && npm run typecheck && npm run lint)
! grep -n "animation:tk-blink" edge/takab_edge/local_api/index.html
```
**Verificación:** escucha y aprobación de Mauricio. En el gabinete, simulacro y música por el jack (con PIN); en el Pixel, la alerta v3 con vibración.

### F8 · R10 contactos de emergencia + baja de los alias  *(D-48 parte 3)*

| Ficha | Qué |
|---|---|
| T-9.80 | **Contactos de emergencia en la nube** (≤ 3 por ocupante: nombre + correo + teléfono opcional). Migración **0076**: `emergency_contacts` **con el mismo trato que `user_profiles`** (RLS solo del propio usuario, registro PII en `privacy/erasure.py`, ARCO y retención; el cifrado es el del volumen, sin cifrado de columna) y consentimiento versionado (aviso de privacidad actualizado). Un check-in `need_help` ⇒ trabajo de notificación por **correo** a los contactos (zona + ubicación solo si la autorizó); el **SMS** entra el día que haya proveedor. En la app, CUENTA → CONTACTOS DE EMERGENCIA. |
| T-9.81 | **Baja de los alias** cuando el `--verify` da 0: se quita `LEGACY_ROLE_ALIASES` (quedan las etiquetas históricas) y los grupos viejos de `identity/main.tf` (el `apply` lo hace Mauricio). `verify_infra.sh` espera exactamente 7. |

**Goal F8**
```bash
set -euo pipefail
(cd api && uv run pytest -q tests/api/test_contactos_emergencia.py tests/test_privacy_erasure.py tests/test_censo_de_la_purga.py tests/test_censo_multitenancy.py tests/auth)
grep -q 'EXPECTED_GROUPS="brigadista gov_operator inspector occupant takab_superadmin takab_support tenant_admin"' infra/scripts/verify_infra.sh
(cd infra/terraform/modules/identity && terraform init -backend=false -input=false >/dev/null && terraform test)
(cd mobile && npm test && npm run typecheck && npm run lint) && (cd web && npx vitest run && npm run format:check)
```

---

## Trampas que se entregan a cada agente

- **Conteo de roles.** Unos 32 sitios del código, tests, infraestructura y documentos. El fixture RBAC se regenera y `make drift` solo vale después del commit.
- **Push.** `test_censo_canales_y_sonidos` exige que cada clase tenga su canal, su sonido y su fase (`_PUSH_PHASE`). Un canal Android no cambia de sonido: si cambia el sonido, cambia el id.
- **Web.** Los tipos nuevos de acción entran al censo `incidentActionKinds` (sin migración: `kind` es texto libre) y los e2e largos corren contra `vite preview`.
- **Workers y datos.**
  - `test_compose_cubre_los_workers` (`informes`, `catalog-sync`) y `test_enganche_al_worker`: el paso que habla con terceros va el último.
  - Cada migración se replica en `schema.sql`. El dueño de las funciones solo se fija en la migración.
  - Hacen falta REVOKE a `takab_app` (lección de la 0069) y respetar los censos de multitenancy, purga y append-only, además del registro de PII.
- **Guardas textuales.** `NO_MMI`, «SIN CARTOGRAFÍA» y «INTENSIDAD MMI» se ponen rojas con solo nombrarlas en un comentario: se reescriben como guardas de comportamiento.
- **Edge.** `test_panel_render_census` exige que cada campo nuevo del estado se pinte.
- **Móvil.** Ningún test dentro de `src/app/**`, ni `@takab/sdk` importado en el cuerpo de un módulo. Un `switch` sobre la fase sin `default` deja la app muda ante una fase nueva.
- **Licencias.** `ci/check-licenses.sh` rechaza GPL: Piper corre solo como herramienta aislada con `uvx`.

## Lo que solo Mauricio puede dar

| Fase | Qué |
|---|---|
| Cada despliegue | Login SSO. Pixel por USB para la APK y los flujos Maestro. |
| F1 | `custom:surface=both` al administrador que vaya a usar la app. |
| F2 | Correr `migrar_roles_7.py` (dry-run → apply → verify); el `building_admin` de la demo va a ADMINISTRADOR. |
| F3 | Correr `diagnostico_sensores.sh` y retirar los dos sensores fantasma de Puebla. |
| F5 | Correr el relleno de mapas en la instancia. |
| F7 | Las pistas de **música clásica** con su licencia de grabación (o aceptar la pieza sintetizada). Escuchar y aprobar el tono v2, la voz del brigadista y el simulacro. |
| F8 | Texto del aviso de privacidad para los contactos (si no, lo redacto y lo apruebas). `terraform apply` de la baja de grupos. |

## Riesgos y cómo se cubren

- **Un VERDE automático que libere mal un reingreso.** Se cubre con la puerta de calibración sobre sensores activos, 300 s de gracia, la re-evaluación por reportes de daño (72 h), la regla de que la prudencia solo baja con firma, y D-43 escrita con su precio.
- **La superficie leída como intensidad observada.** Se cubre con los rótulos ESTIMADO, las zonas ajustada y modelada, y un texto del PDF derivado del dato. Los PDF ya firmados con `NO_MMI` siguen siendo ciertos para su fecha.
- **Una APK vieja frente a fases o canales nuevos.** Siempre APK primero, y `machine.ts` con `default` desde F0.
- **La migración de Cognito a medias.** Los alias y un script idempotente que se puede re-correr.
- **Legal.** El tono «parecido» se revisa contra D-19 y GATE-LEGAL. Se verifica la licencia del modelo de voz para uso comercial. La música exige una grabación libre, no solo la partitura. Los contactos son datos de terceros (consentimiento + ARCO).
- **El límite de la sesión.** Nunca más de 2 subagentes a la vez.

## Verificación de extremo a extremo (al final de cada fase y del bloque)

1. El Goal de la fase devuelve 0 en una corrida limpia y el CI de `main` está en verde.
2. Desplegado:
   - `/api/health` da el build de `main`;
   - `goal-presentacion.sh` no tiene ✗;
   - el edge está en una release limpia (sin `-dirty`).
3. En el sistema real, con Pixel + gabinete:
   - **golpe local hasta DISPARO** ⇒ voz solo en tácticos, ocupante en silencio; en CAUTELA nadie;
   - **WR-1** ⇒ el ocupante suena en < 2 s con la pantalla bloqueada;
   - **escalada** ⇒ re-notifica;
   - **VERDE** ⇒ reingreso automático;
   - **AMARILLO** ⇒ confirmación del brigadista;
   - **NO HABITAR** ⇒ sigue bloqueado al día siguiente, y LEVANTAR RESTRICCIÓN lo libera.
4. PDF con el mapa de calor ESTIMADO, la cartografía embebida, la MMI estimada y el firmante correcto (revisado con `pdftoppm`).
5. Asistente de cierre recorrido de punta a punta por el ADMINISTRADOR, con la confirmación del brigadista en la app y el reporte automático que llega en ≤ 30 min.
6. Memoria de sesión con las trampas nuevas + `graphify update .`
