# RUNBOOK · Auditoría de cierre — Fase 1 piloto (2026-07-11)

> **Estado: EJECUTADA (2026-07-11) — 22 ítems auto-verificables resueltos · 10 gates HW/despliegue enumerados SIN marcar.**
> **Criterio global:** cada ítem auto-verificable queda **PASS/FAIL con evidencia reproducible**
> (archivo:línea, nombre de test o salida de comando); los gates de hardware/despliegue quedan
> escritos con su criterio de aceptación y **sin marcar** (simulador ≠ hardware). Regla dura
> respetada: **no se modificó código de producción** para "pasar" ningún ítem — los hallazgos
> quedan como tareas futuras (§11).

Alcance pedido: recorrido exhaustivo de la consola (botones sin funcionalidad, funciones y
cálculos faltantes), alta/baja de estaciones, envío de alerta, audio de simulacro/sismo por la
salida del Pi 5, y auditoría de los 6 bloques de riesgo (vida, botones, E2E, seguridad,
operación, CI). Decisiones de alcance ratificadas: el audio se especifica como tarea (no se
implementa); todo lo físico queda como gate; a la nube viva solo se le hicieron GETs.

---

## 0. Cómo leer este runbook

Formato de cada ítem:

- `[x]` = verificación EJECUTADA (el resultado puede ser PASS o FAIL; FAIL genera hallazgo §11).
- `[ ]` = gate de hardware/despliegue: NO ejecutado aquí; se llena presencialmente (§10).
- **Resultado:** PASS · PASS parcial · FAIL · GATE-HW · GATE-DESPLIEGUE.
- **Evidencia:** todo PASS/FAIL cita archivo:línea, nombre de test o salida de comando. Los logs
  crudos de esta ejecución quedaron en el scratchpad de la sesión (`pytest-*.log`,
  `greps-evidencia.log`, `demo-fase1*.log`, `dictamen-audit.pdf`).

## 1. Veredicto ejecutivo

**¿"Terminado Fase 1 piloto"? Sí en lo funcional, con 4 asteriscos que impiden declararla
cerrada hoy:**

1. **La rama `main` remota está en ROJO y 21 commits (toda la Fase 1.7) nunca se subieron a
   GitHub** — la nube viva (tag `2ca20fb`) corre código que jamás pasó CI (hallazgo A-1).
2. **`make demo-fase1` ya NO acredita el hito en HEAD**: 33 OK · 2 FALLOS deterministas
   (acreditado 36/36 el 2026-07-08; regresión de Fase 1.7 en los asserts intermedios de C2)
   (hallazgo A-3).
3. **Los gates #3 físicos siguen abiertos** (soak 24 h, restart del Shake, semántica del radio
   WR-1, latencia real de relé) — §10.
4. **Nadie es paginado cuando un gabinete cae**: cero alarmas CloudWatch, cero SNS (hallazgo A-4).

**Para "flota de producción" falta, en orden:** A-1 (push + CI verde), A-3 (re-acreditar el
hito), A-2 (fail-loud de la pin factory), A-4 (alarmas a humanos), A-5 (restore probado +
RPO/RTO), M-3 (SMS/WhatsApp/push reales), M-4 (LFPDPPP/residencia de datos antes del primer
cliente), M-8 (applies pendientes), más los gates físicos del §10.

Lo que SÍ está sólido y verificado hoy: suite completa en verde local (api 741 · web 525 ·
edge 273 + lint 3/3 + build), RLS negativo y audit append-only a prueba de superusuario,
HMAC/nonce/rate-limit con tests de forja y replay, quórum consciente de distancia que NO abre
incidentes de red por una estación aislada, DLQ con rechazo tipificado, CRUD de estaciones con
retiro lógico e históricos intactos (ejercitado en vivo), dictamen PDF real con sha256 cotejado
contra MinIO, config firmada con 409 anti-pisado y `config-state` honesto, y una consola sin un
solo dato fabricado (sin T-MINUS, sin magnitud preliminar, sin offsets inventados).

## 2. Cómo reproducir (entorno local)

```bash
# Prerrequisitos: docker compose up -d db minio minio-init  (DB :5433, MinIO :9000)
# Suites completas con DB de test fresca (réplica del CI):
docker compose exec -T db psql -U takab -d postgres \
  -c "DROP DATABASE IF EXISTS takab_test;" -c "CREATE DATABASE takab_test OWNER takab;"
cd api  && DATABASE_URL="postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab_test" \
  .venv/bin/pytest -q -m "not perf"          # 741 passed
cd web  && npm run test -- --run             # 525 passed  · npm run build
cd edge && GPIOZERO_PIN_FACTORY=mock uv run pytest -q   # 273 passed
# Hito y SOC interactivo:
make demo-fase1     # HOY: 33 OK · 2 FALLOS (ver A-3)
make soc-local      # SOC completo; estímulos: curl -X POST 127.0.0.1:9100/quake | /sasmex | /sasmex/clear | /wan/off
# CI remota:
gh run list --workflow ci.yml --branch main --limit 5
```

Nota de esta ejecución: `make lint` asume el venv del api en PATH; se corrió el equivalente
exacto por paquete (`api/.venv/bin/ruff`, `npm run lint && format:check`, `uv run ruff`).

---

## 3. BLOQUE 1 · Camino de vida

### [x] L1 · gpiozero usa lgpio y falla RUIDOSO (lección del commit 9361e27)
- **Cómo verificar:** `grep -rn "pin_factory\|LGPIOFactory\|MockFactory" edge/takab_edge/ deploy/ edge/systemd/`
- **Criterio:** existe prueba/instrucción de que en producción la factory es LGPIOFactory y su
  ausencia truena, sin caída silenciosa a sysfs.
- **Resultado:** **FAIL → hallazgo A-2.** No existe `Device.pin_factory = LGPIOFactory()` ni
  aserción de factory en producción: `ensure_dev_pin_factory()` solo fija `MockFactory` en dev
  (`edge/takab_edge/gpio/__init__.py:78-88`) y solo se llama con `dev_mode=True` (`:157-159`);
  en el Pi real gpiozero AUTO-SELECCIONA backend (docstring `:81-83`). El fail-loud actual es
  **indirecto**: CWD escribible (`edge/systemd/takab-edge.service:24-31`,
  `takab-gpio.service:17-18` — `WorkingDirectory=/var/lib/takab` bajo `ProtectSystem=strict`),
  `critical=True` (`gpio/__init__.py:100`) y `Restart=always`. Si lgpio fallara por OTRA causa,
  el fallback a `native` seguiría siendo silencioso.
- **Evidencia:** salida del grep (solo hits de MockFactory-dev y el comentario "cae EN SILENCIO"
  en `takab-edge.service:26`); validación del fix original solo manual con `systemd-run`
  (`takab-docs/TASKS.md:925`).
- `[ ]` **GATE-HW G-01:** reinicio en frío en cada Pi con verificación del backend activo.

### [x] L2 · SPOF-02 (SASMEX→sirena por hardware con el Pi muerto)
- **Cómo verificar:** existencia y estado de `takab-docs/runbooks/RUNBOOK-SPOF-02-ruta-hardware-sirena.md`.
- **Criterio:** el runbook existe con diseño ejecutable; su verificación es física.
- **Resultado:** **PASS documental.** Existe con diseño eléctrico completo (variante B, latido
  "Pi vivo", coexistencia con silencio/SPOF-07, BOM) y su **§8 "Registro de verificación" está
  vacío a propósito**.
- `[ ]` **GATE-HW G-02:** ejecutar §6 del runbook SPOF-02 y llenar su §8.

### [x] L3 · Tareas cerradas contra simuladores (gates #3 abiertos)
- **Cómo verificar:** `grep -n "hardware-gated\|gate #3" takab-docs/TASKS.md`
- **Resultado:** **transcritos, todos GATE-HW (G-03/G-04):** soak 24 h + reinicio físico del
  Shake (`TASKS.md:110-111`, T-1.5); semántica real del radio WR-1 — pulso vs sostenido,
  latching (`TASKS.md:1011-1017`, T-1.42 `[~]`); latencia física contacto→relé→sirena < 100 ms
  (`TASKS.md:1018`). La entrada física del WR-1 quedó validada con botón real (T-1.42 header);
  falta el radio.

### [x] L4 · Calibración: umbrales en g real, no placeholder
- **Cómo verificar:** `grep -n "calibration_source" db/seeds/prod_fleet.sql db/seeds/sim_fleet.sql` + suite.
- **Criterio:** toda estación EN PRODUCCIÓN dispara con g real.
- **Resultado:** **PASS con matiz.** La única estación de producción (`AM.R4F74`, gw-dev-0001)
  tiene calibración física real (`db/seeds/prod_fleet.sql:42-48`,
  `calibration_source='stationxml:AM.R4F74'`; sensibilidades FDSN aplicadas por
  `/etc/takab/edge.env`, validada con PGA 0.567 g — `TASKS.md:977-989`). Los 20 sensores sim
  NO traen `calibration_source` (grep exit=1 en `sim_fleet.sql`) ⇒ la UI los marca SIN CALIBRAR
  por default-deny (`web/src/features/telemetry/calibration.ts:25-32`,
  `NotCalibratedBadge.tsx:10-20`) y son exclusivos de entornos locales (T-1.47). Umbrales
  `pga_watch_g=0.040` / `pga_trip_g=0.060` en g real (`edge/takab_edge/config/settings.py:26-36`);
  defaults de sensibilidad edge declarados placeholder por docstring (`settings.py:52-71`).
- **Evidencia:** tests `tests/api/test_calibration.py` (6) en verde dentro del grupo B4 (33
  passed); alta sin fuente ⇒ `calibration_source: None` verificada en vivo (F1.c).

## 4. BLOQUE 2 · Botones reales

### [x] B1 · Inventario exhaustivo de onClick/onSubmit de producción
- **Cómo verificar:** recorrido de `web/src` excluyendo tests/mocks (hecho archivo por archivo).
- **Criterio:** cada botón (a) llama endpoint real vía `@takab/sdk` o hace acción local
  legítima, (b) cubre los 4 estados, (c) en fallo muestra el fallo.
- **Resultado:** **PASS con 1 stub deliberado y 1 gap de estados** (hallazgos M-2, M-6).

| Página | Botón | Endpoint / acción | Estado |
|---|---|---|---|
| Login | ENTRAR CON COGNITO · ENTRAR COMO ROL (dev) | OIDC redirect · POST `/dev/token` (solo dev) | OK |
| Shell | GUARDAR nombre · SALIR · REINTENTAR | PUT `/me/profile` · logout · `refreshMe()` | OK |
| Consola | fila incidente · REUBICAR EPICENTRO · SOLICITAR DICTAMEN · CONFIRMAR ACUSE | local · POST `/incidents/{id}/epicenter` · POST `…/dictamen-request` · POST `…/ack` | OK (gates RBAC) |
| Consola | expandir BMS · cerrar detalle | local (solo traza; NO comanda actuadores) | OK |
| Flota | NUEVA ESTACIÓN · EDITAR · HARDWARE · RETIRAR | POST `/sites` · PUT `/sites/{id}` (+`base_row_version`) · POST `/fleet/gateways`+`/sensors` · DELETE `/sites/{id}` | OK (F1/F2 en vivo) |
| Flota | **AUTODIAGNÓSTICO SILENCIOSO** | **ninguno — `disabled` permanente** | **STUB (M-2)** |
| Triage | facetas · fila · catálogo · EXPORTAR miniSEED · DICTAMEN PDF · FIRMAR | filtros · POST `/evidence/{id}/download` · POST `/incidents/{id}/report` · POST `…/dictamens` | OK (B3 en vivo) |
| Multi-Tenant | sliders/switches · RESTAURAR · APLICAR Y SINCRONIZAR | borrador local · reset · PUT `/rule-sets` + publish | OK (B4 en vivo) |
| Building | presets rango · PROBAR/SILENCIAR SIRENA · DESCARTAR | query params · POST `/sites/{id}/commands` (ack real del edge; 201 ≠ "sonó") | OK |
| Panel LAN (Pi) | SILENCIAR AUDIBLES · PROBAR SIRENA · CERRAR ALERTA | POST `/api/silence`·`/siren-test`·`/reset` (PIN en prod) | OK (verificado en vivo) |

  Único botón sin funcionalidad: **AUTODIAGNÓSTICO SILENCIOSO**
  (`web/src/features/fleet/SiteCard.tsx:107-114`), `disabled` con title honesto ("Requiere
  acción self_test en el Command Service"). Cero `TODO`/`noop`/`console.log` en producción.
  Gap de 4 estados: card "Relés del Gabinete" (`console/DetailPanel.tsx:322-332` +
  `useSiteRelays.ts:10-14`) colapsa error/stale al empty (M-6).

### [x] B2 · Desviaciones honestas vs mockup, verificadas en render
- **Cómo verificar:** `npx vitest run AlertBanner QuorumNodes TriagePage SirenTestPanel FleetAdmin`
  + greps de fabricaciones.
- **Resultado:** **PASS parcial (honesto).** 58 tests de render en verde (5 archivos, jsdom):
  AlertBanner muestra "ALERTA SÍSMICA · PROTÉJASE" + PGA MEDIDO, sin magnitud ni T-MINUS
  (`AlertBanner.tsx:4,23-37`); QuorumNodes pinta `delta_s` del servidor (los +0.18s/+0.39s del
  mockup fueron retirados, comentario `:25-41`); TriageDetail sin "NOM-003-SCT" (solo
  comentarios de la retirada, `TriageDetail.tsx:89`, `TriagePage.tsx:34`; blueprint §9).
  **Límites declarados:** TriageDetail no tiene spec de render propio (ningún `*.test.tsx` de
  triage lo referencia) y **Playwright NO existe en `web/`** pese a `CLAUDE.md:89` y al smoke
  citado en `TASKS.md:525` (M-7) — la verificación es jsdom + recorrido en `make soc-local`,
  no navegador automatizado reproducible.
- **Evidencia:** grep `T-MINUS|countdown` en producción = solo el comentario de AlertBanner, el
  countdown del ConfirmButton (benigno) y el comentario de DetailPanel:188; grep `playwright`
  en `web/package.json` = exit 1.

### [x] B3 · Botones que producen artefactos reales
- **Cómo verificar:** flujo vivo contra MinIO (`make soc-local`; seam
  `TAKAB_API_S3_ENDPOINT_URL` ya integrado en `demo/soc_local.sh:22-27`).
- **Criterio:** archivo real con datos y firma reales; en fallo, fallo visible.
- **Resultado:** **PASS.**
  - **DICTAMEN PDF:** POST `/incidents/{id}/report` (rol inspector) → 201; evidencia
    `report_pdf`; POST `/evidence/{id}/download` → presigned MinIO; descarga 200 de 1 679 bytes
    con magic `%PDF-1.3` y **sha256 descargado idéntico al registrado**
    (`2a74c8063dd92a57…`). Guardas honestas: 503 sin bucket (`routers/reports.py:53`,
    `routers/exports.py:58` + `test_reports.py:116`); en la web el fallo cancela la pestaña
    reservada y se muestra (`useIncidentDetail.ts:154-194`).
  - **EXPORTAR miniSEED:** mismo endpoint de descarga (verificado con el PDF). El miniSEED lo
    genera el EDGE y sube por backfill SOLO en eventos confirmados
    (`api/src/takab_api/backfill/objects.py:173`, `grants.py:66`) — en esta sesión local no se
    produjo ninguno (0 filas `kind='miniseed'`); la observación con evento real queda en G-06.
  - **EXPORTAR LOTE:** **no existe a propósito** (`TriagePage.tsx:31`; sin endpoint batch en
    api — decisión documentada, no un botón muerto).
  - **AUTODIAGNÓSTICO SILENCIOSO:** stub (ver B1/M-2) — no produce nada y no finge producirlo.
- **Evidencia adicional:** grupo B3/F1/F2 = 39 passed (`test_reports.py`, `test_exports.py`,
  `test_s3_seam.py`, `test_fleet_admin.py`).

### [x] B4 · APLICAR Y SINCRONIZAR / RESTAURAR (config firmada, T-1.23)
- **Cómo verificar:** ciclo vivo PUT→publish→config-state (comandos en §2).
- **Criterio:** la config publicada se refleja en `GET /fleet/gateways/{id}/config-state` sin
  fingir sincronía.
- **Resultado:** **PASS.** PUT `/rule-sets` con `base_version=1` → 201 versión 2; **PUT repetido
  con base_version vieja → 409** (anti lost-update); publish → **202 `pending_sync`** (el 202
  NO afirma que el gabinete la tenga); `config-state` de gw-dev-0001 → 200 honesto:
  `{version: null, in_sync: false, has_edge_config: false, is_syncable: true}` — el rule_set v1
  no trae clave `edge` (a propósito) y el gabinete no ha acusado ninguna config. RESTAURAR es
  reset local del borrador (`TenantsPage.tsx:219-227`).
- **Evidencia:** salidas HTTP citadas; tests grupo 33 passed (`test_rule_sets.py:97-238` incluye
  cruce de tenants, secret del webhook y 409).
- `[ ]` **GATE-HW G-05:** aplicar en gabinete físico y ver `in_sync: true` con fingerprint.

## 5. BLOQUE 3 · Camino edge→nube end-to-end

### [x] E1 · Cadena simulador de sismo → incidente en UI → cascada de notificación
- **Cómo verificar:** `make demo-fase1` + `make soc-local` con estímulos (§2).
- **Resultado:** **PASS parcial + regresión del hito (A-3).**
  - Cadena trazada: edge `LocalEvent` → SQS → consumer → `ingest/handlers.py:249` (UPSERT a
    `incidents`, nunca degrada severidad) → correlación `incident/engine.py:246` → cascada
    `notify/plan.py:24` (webhook→whatsapp→sms→email; crítico añade email paralelo `:105`;
    fail-open todo en paralelo `:88`).
  - En vivo (soc-local): `POST :9100/quake` → 200 y **2 incidentes `critical`/`local_threshold`
    visibles por `GET /incidents` en < 6 s**.
  - **`make demo-fase1` HOY = HITO NO ACREDITADO: 33 OK · 2 FALLOS**, deterministas (2 corridas
    idénticas). Fallan los 2 asserts INTERMEDIOS de C2 (`demo/run.py:317-321` — espera 3
    incidentes sin corroborar y obtiene `[]`; `:322-325` — `trigger == 'local_threshold'`),
    con pizarra limpia entre criterios (TRUNCATE, `run.py:134-140`); los asserts de OUTCOME del
    mismo criterio pasan (evento `local_quorum` con node_count=3, offsets +0.00/+0.10/+0.23 s,
    3 incidentes linkeados, fail-open de 7 sitios). Acreditado 36/36 el 2026-07-08
    (`RUNBOOK-demo-fase1-tres-gabinetes.md:3`) ⇒ regresión introducida por Fase 1.7.
  - Cascada: el worker `python -m takab_api.notify` NO corre en soc-local (por diseño del
    script); en la nube está declarado (`deploy/cloud/docker-compose.yml:74-79`). Canales
    REALES hoy: webhook con firma HMAC y email SES sandbox; **SMS y WhatsApp SIMULADOS**
    (`notify/providers.py:123-124`), **push inexistente** (M-3). Tests notify: 33 passed.
- `[ ]` **GATE-HW G-06:** simulacro E2E por sitio real con cascada de notificación real.

### [x] E2 · Quórum (T-1.46): una estación aislada NO abre incidente crítico de red
- **Cómo verificar:** `pytest tests/incident -v` (79 passed).
- **Resultado:** **PASS.** Ventana consciente de la distancia `|Δt| ≤ dist/v_P + margen` con tope
  duro de 60 s (`incident/quorum.py:105`, `:24`; distancia PostGIS `engine.py:112`). Tests
  nominales: `test_below_min_nodes_no_event` (2 < min_nodes=3 ⇒ sin evento, `test_engine.py:251`),
  `test_isolated_single_site_anchor_does_not_poison_window` (`:402`),
  `test_out_of_window_no_event` (`:236`),
  `test_spurious_early_out_of_window_detection_does_not_suppress_quorum` (`:379`),
  `test_correlates_distance_aware_cluster` (110 km / ~17 s SÍ asocia; `magnitude is None`,
  `:180,:205`). El falso positivo aislado queda como incidente local NO corroborado
  (`event_id IS NULL`); la nube jamás lo eleva a evento de red.

### [x] E3 · DLQ: lo malformado se rechaza tipificado; ¿alarma si crece?
- **Cómo verificar:** `pytest tests/test_ingest_consumer.py -v` (13 passed) +
  `grep -rni "alarm" infra/terraform --include='*.tf'`.
- **Resultado:** **PASS mecanismo · FAIL alarma (parte de A-4).** REJECT→DLQ con
  `MessageAttributes {reason, original_topic}` (`ingest/consumer.py:210-225,244`); redrive
  `maxReceiveCount=5` (`modules/messaging/main.tf:38-41`). Tests:
  `test_invalid_schema_lands_in_dlq_with_reason` (`:196`), `test_malformed_json_lands_in_dlq`
  (`:214`), `test_unknown_principal_lands_in_dlq` (`:225`), retry sin caer a DLQ (`:259`).
  **No existe NINGUNA alarma de profundidad**: grep de `alarm|ApproximateNumberOfMessages` en
  todo `infra/terraform` = exit 1.

## 6. BLOQUE 4 · Seguridad, multi-tenant, cumplimiento

### [x] S1 · RLS con prueba negativa (cruce de tenants) en CI
- **Cómo verificar:** `pytest tests/test_rls_isolation.py tests/api/test_rule_sets.py -v`.
- **Resultado:** **PASS.** `test_app_cannot_read_other_tenant` (`test_rls_isolation.py:36`),
  `test_app_cannot_write_other_tenant` (WITH CHECK ⇒ `InsufficientPrivilege`, `:51`),
  `test_owner_force_rls_isolates` (`:29`), vista `_secure` + REVOKE de caggs (`:62-77`); capa
  API: `test_rule_sets_cross_tenant_isolated` (`:97`) y
  `test_superadmin_cannot_write_a_rule_set_for_another_tenants_scope` (`:118`) — hardening del
  commit aa6f815. Corren en el job `api` del CI (`.github/workflows/ci.yml:53`,
  `pytest -q -m "not perf"` con servicio Timescale). Grupo ejecutado hoy: 34 passed.

### [x] S2 · Comando forjado / nonce repetido → rechazado (HMAC por gabinete, T-1.38)
- **Cómo verificar:** `pytest tests/commands tests/api/test_commands_router.py -v` (46 passed) +
  edge `tests/test_security.py tests/test_hmac_vectors.py` (dentro de 75 passed).
- **Resultado:** **PASS.** Firma HMAC por gabinete con framing length-prefixed
  (`commands/signing.py:37`); clave por `iot_thing` con **fail-closed 503 sin clave y sin fuga**
  (`routers/commands.py:122-124`, `test_commands_router.py:214`); nonce `UNIQUE`
  (`db/schema.sql:720`); rate-limit usuario+sitio / sitio (`commands.py:103-113`,
  `test_commands_router.py:154` → 429). Tests de ataque:
  `test_tampering_changes_signature` (`test_signing_vectors.py:40`),
  `test_unknown_nonce_is_rejected` (`test_ack_ingest.py:110`),
  `test_redelivery_is_idempotent` (`:118`), `test_wrong_gateway_is_rejected_with_audit` (`:95`),
  `test_each_gateway_signs_with_its_own_key` (`test_commands_router.py:236`). MFA se garantiza a
  nivel de pool Cognito (ver S4), no por endpoint. En el gabinete real los comandos de nube
  están apagados (`command_enabled=False`, `edge/takab_edge/config/settings.py:150-153`).
- `[ ]` **GATE-HW G-07:** replay real de un comando capturado contra el gabinete físico.

### [x] S3 · `audit_log` inmutable (T-1.24)
- **Cómo verificar:** `pytest tests/test_append_only.py -v` + `grep -n "forbid_update_delete" db/schema.sql`.
- **Resultado:** **PASS.** Trigger `forbid_update_delete()` (`db/schema.sql:59-62`) aplicado a
  `audit_log` (`:466`) y a `incident_actions`/`dictamens`/`life_checkins`/`rule_evaluations`/
  `evidence_objects` (`:243,:261,:314,:380,:451`). Tests con `RESET ROLE` (ni el superusuario
  puede): `test_update_blocked`, `test_delete_blocked`, `test_insert_still_allowed`
  (`test_append_only.py:27,34,40`); único escritor vetado por contract-test
  (`tests/contracts/test_audit_single_writer.py`); sin poda de compliance
  (`test_compliance_retention.py:45`).

### [x] S4 · Cognito MFA por rol (T-1.18)
- **Cómo verificar:** `grep -n "mfa_configuration" infra/terraform/modules/identity/main.tf`.
- **Resultado:** **PASS con desviación documentada (M-5).** Pool único con
  `mfa_configuration = "ON"` + TOTP obligatorio (`identity/main.tf:42-45`) — **TODOS los roles
  con MFA, occupant incluido**. La separación "occupant sin MFA" del RBAC doc NO está
  implementada: difiere explícitamente a T-1.31 (pool aparte para app móvil). Estado actual =
  MÁS estricto que el diseño, no menos. `write_attributes = ["name"]` impide auto-reasignación
  de tenant/rol.
- `[ ]` **GATE-DESPLIEGUE (en G-10):** verificación runtime por rol contra el pool real
  `us-east-2_WlAWpxvnn`.

### [x] S5 · LFPDPPP: aviso de privacidad, retención, residencia de datos
- **Cómo verificar:** `grep -rn "us-east-2" infra/terraform/envs/dev --include='*.tf'` + búsqueda
  de aviso/ARCO en docs y código.
- **Resultado:** **FAIL (estado real: aspiracional) → hallazgo M-4.** El blueprint solo
  "considera" LFPDPPP (`BLUEPRINT-TECNICO-TAKAB.md:408`); no hay aviso de privacidad, flujo de
  consentimiento, derechos ARCO ni política de retención de PII en código. **Toda la PII reside
  en us-east-2 (Ohio, EE. UU.)** (`envs/dev/providers.tf:18`, `backend.tf:5`; pool Cognito
  us-east-2; `life_checkins` guardará ubicación de personas). Marco normativo citable de
  Protección Civil sigue POR CONFIRMAR (blueprint §9; la vieja "NOM-003-SCT" fue retirada por
  errónea). Bloqueante ANTES del primer cliente con datos reales; no bloquea el piloto dev.

### [x] S6 · Los `[~]` sin desplegar (T-1.43 / T-1.44)
- **Cómo verificar:** `grep -n "T-1.43 ·\|T-1.44 ·" takab-docs/TASKS.md` + terraform.
- **Resultado:** **transcrito fielmente (M-8).**
  - **T-1.43 (PIN panel local):** `[~]` "CÓDIGO LISTO · DESPLIEGUE con T-1.40"
    (`TASKS.md:944`); es edge (viaja con el deploy del Pi, no con terraform); el propio TASKS
    documenta verificación en el Pi real (GET 200 / POST 401→200, `:960-962`). Implementación:
    `local_api/__init__.py:188-213` (compare_digest, lockout 5/60 s, fail-closed sin PIN en
    prod).
  - **T-1.44 (rol CI OIDC):** `[~]` con checkbox literal `[ ] Aplicado` (`TASKS.md:932,942`);
    el rol `takab-ci-plan` existe en `modules/ci-oidc/main.tf:23-49` (sub anclado EXACTO a
    `refs/heads/main`, ReadOnly) y el paso plan-only del CI sigue TODO (`ci.yml:155`).
  - Contexto: T-1.37 header `[~]` aunque el apply del 2026-07-09 está documentado
    (`TASKS.md:808-809`); T-1.47 purga en EC2 pendiente (`:1110-1111`); T-1.53 verificación en
    el Pi pendiente (`:1282-1288`).

## 7. BLOQUE 5 · Observabilidad y operación

### [x] O1 · Alarma a humano cuando un gabinete cae / batería baja
- **Cómo verificar:** `grep -rn "aws_cloudwatch_metric_alarm\|aws_sns_topic" infra/terraform --include='*.tf'`
- **Criterio:** existe paginado con umbral de tiempo, no solo un color en la UI.
- **Resultado:** **FAIL → hallazgo A-4.** El grep devuelve **cero recursos** (exit=1): no hay
  ninguna alarma CloudWatch ni ningún topic SNS en toda la infra. La detección existe solo como
  estado derivado para la UI (OPERATIVO/DEGRADADO/SIN ENLACE, umbral 5 min —
  `routers/fleet.py:109`) y el fail-open abre incidente sintético SOLO si un evento de quórum
  confirma sismo en rango (`incident/fail_open.py:103,174`). Un gabinete offline o con batería
  baja SIN sismo **no notifica a nadie**. El único correo automatizado es el presupuesto de
  costos (`envs/dev/budget.tf:1-20`).

### [x] O2 · Load-test de ingesta vs SLOs
- **Cómo verificar:** `takab-docs/runbooks/RUNBOOK-load-test-ingesta.md`.
- **Resultado:** **PASS documental a escala G1.** Corrida B CALIFICADA: 48 080 msgs @ 80.2 msg/s
  sostenidos, 0 errores, sin lag sostenido, DLQ limpia, con workers co-locados en el EC2
  (`RUNBOOK-load-test-ingesta.md:46-51`); p95 del dashboard 8 ms (`TASKS.md:525`).
- `[ ]` **GATE-DESPLIEGUE G-08:** repetir a escala objetivo de flota comercial contra los SLOs
  p95 del blueprint.

### [x] O3 · Backup de Timescale y restore probado (RPO/RTO)
- **Cómo verificar:** `grep -n "aws_dlm_lifecycle_policy" infra/terraform/modules/database/main.tf`.
- **Resultado:** **FAIL → hallazgo A-5.** Solo snapshots EBS por DLM: diarios 03:00 UTC,
  retención 7 (`modules/database/main.tf:268-288`; DB = Timescale en EC2 autogestionado por
  decisión `:166-167` — RDS no soporta la extensión). **Sin PITR/WAL, sin restore jamás
  probado, sin RPO/RTO declarados, sin runbook de restauración** (no existe en
  `takab-docs/runbooks/`).
- `[ ]` **GATE-DESPLIEGUE G-09:** restore real desde snapshot + medir RPO/RTO y publicarlos.

## 8. BLOQUE 6 · CI y diferidos

### [x] C1 · Lint + tests por paquete con conteos reales + CI en main
- **Cómo verificar:** §2.
- **Resultado local: PASS.**
  - Lint 3/3: api `ruff check` "All checks passed" + `format --check` 232 archivos; web
    eslint + prettier limpios; edge ruff 57 archivos.
  - **api: 741 passed, 1 skipped, 2 deselected (perf)** en 128 s — sobre `takab_test`
    **provisionada desde cero** (alembic head por el conftest ⇒ la idempotencia de migraciones
    reparada el 2026-07-11 queda demostrada en local).
  - **web: 525 passed (55 archivos)** en 18 s; `npm run build` OK (tsc + vite 5.6 s; warning de
    chunks > 500 kB — B-6).
  - **edge: 273 passed** en 65 s (coincide exacto con el baseline documentado).
- **Resultado CI remota: FAIL → hallazgo A-1.** Última corrida en `main` remota =
  run 29066872312 (commit 9361e27, 2026-07-10): job `api · ruff + pytest` **failure** —
  `alembic upgrade head` exit 1 en la DB fresca del CI ⇒ **650 errors** ("1 skipped,
  2 deselected, 650 errors in 22.73s"); los otros 4 jobs (sdk-ts, web, edge, infra) verdes.
  **`git log origin/main..main` = 21 commits sin subir** — TODA la Fase 1.7 (incluido el fix de
  idempotencia 715ee36 y el tag desplegado 2ca20fb). La nube viva corre código que nunca pasó
  CI en GitHub.
- Notas de exactitud: `make test` corre `pytest -q` SIN `-m "not perf"` — difiere del CI (B-1);
  `demo/tests/test_spool.py` no corre en `make test` ni en CI (B-2); los subconjuntos
  multi-archivo de `tests/api` no son estables por doble fixture `client`
  (`tests/api/conftest.py:281` vs `tests/_telemetry_fixtures.py:215`) — correr suite completa o
  archivos sueltos (B-3).

### [x] C2 · Diferidos rotulados: la UI viva no los fabrica
- **Cómo verificar:** greps §2 + inventario B1/B2.
- **Resultado:** **PASS.** T-MINUS/countdown: solo el comentario que afirma su AUSENCIA
  (`AlertBanner.tsx:4`, `DetailPanel.tsx:188`) y el countdown benigno del ConfirmButton.
  Magnitud: solo la de catálogo post-hoc nullable ("M x.x"/"S/D", `triage/model.ts:214-218`);
  `seismic_events.magnitude` siempre NULL (`test_engine.py:205`). App móvil: mencionada solo
  como superficie diferida T-1.31 (`MobileOnlyScreen.tsx`), no prometida. Blueprint §14
  íntegro: sin mini-ShakeMap, sin streaming crudo, sin IA en el camino de disparo.

## 9. Flujos solicitados en esta auditoría

### [x] F1 · Alta de estación (sitio → gabinete → sensor)
- **Resultado:** **PASS (ejercitado en vivo).** POST `/sites` → **201** (cae en el tenant del
  caller, `tenant_id d0000000…`); POST `/fleet/gateways` → **201 `status: provisioned`** (nunca
  nace "online"; el cert X.509 lo emite Terraform); POST `/sensors` → **201 con
  `calibration_source: None`** ⇒ SIN CALIBRAR por default-deny. Validación Pydantic elocuente
  (422 con opciones exactas: criticality low/medium/high/critical; kind structural/ground). UI:
  NUEVA ESTACIÓN/HARDWARE en `/fleet` (gate `manage_fleet`); selector de punto en mapa (T-1.36).
- **Evidencia:** salidas HTTP de esta sesión + `test_fleet_admin.py:154`
  (`test_create_site_lands_in_callers_tenant_and_audits`).

### [x] F2 · Baja de estación
- **Resultado:** **PASS (ejercitado en vivo).** DELETE `/sites/{id}` → **200 `status: retired`**
  (retiro LÓGICO); segundo DELETE → 200 **idempotente**; la fila SOBREVIVE en DB
  (`SELECT … WHERE site_id=…` → `AUD-01 | retired`); desaparece del catálogo activo (21
  visibles, AUD-01 fuera). No hay borrado físico por diseño: incidentes, dictámenes y evidencia
  lo referencian y no se podan nunca (regla de oro 11, `routers/sites.py:12`); gateways/sensores
  tienen retire+restore propios (`routers/fleet.py:243,267`, `sensors.py:152`).
- **Evidencia:** salidas de esta sesión + `test_retire_is_soft_idempotent_and_hides_from_the_catalog`
  (`test_fleet_admin.py:242`), `test_sensor_retire_keeps_the_row` (`:371`).

### [x] F3 · "Manda alerta"
- **Resultado:** **PASS del camino real + hallazgo M-1 (no hay modo simulacro).**
  - En vivo: `POST :9100/quake` → 2 incidentes `critical`/`local_threshold` por API en < 6 s;
    `POST :9100/sasmex` → panel del gabinete: `sasmex_active=true`, `siren_sounding=true`,
    `tier=evacuate_or_hold` (reflejo + enclavamiento); `/sasmex/clear` NO apaga la sirena (el
    enclavamiento retiene hasta acción del operador — comportamiento de vida correcto);
    `POST /api/reset` del panel (CERRAR ALERTA) → sirena OFF y desenclavada.
  - **No existe** disparo de alerta manual ni simulacro/drill desde la nube o la consola (grep
    exhaustivo api+web = vacío); lo único parecido es el self-test de sirena acotado (2 s,
    `gpio/__init__.py:263-285`) y la prueba desde `/building` con acuse real. La alerta real
    solo nace del camino determinista (WR-1/umbral/quórum) — correcto para la regla de oro 1,
    pero deja a Protección Civil sin herramienta de SIMULACRO end-to-end (M-1).
- `[ ]` **GATE-HW (en G-06/G-10):** sirena física + panel en el Pi real, presencial.

### [x] F4 · Audio de simulacro y de sismo por la salida del Pi 5 cerebro
- **Cómo verificar:** `grep -rniE "aplay|alsa|pyaudio|sounddevice|simpleaudio|playsound|\.wav|\.mp3|espeak|pyttsx" edge/`
- **Resultado:** **FAIL — NO EXISTE → hallazgo A-6 (funcionalidad solicitada).** El grep
  devuelve exit=1 (cero hits reales en todo el repo). No hay módulo de audio en edge (módulos:
  gpio, seedlink, signal, buffer, rules, actuators, cloud, health, security, config, dispatch,
  backfill, local_api); la "sirena" es SIEMPRE un relé seco (`ActuatorChannel.SIREN`,
  `contracts.py:54`; sirena jamás por BACnet, `actuators/__init__.py:33-34`); el blueprint no
  menciona audio/voceo. **Nota de hardware:** el Raspberry Pi 5 NO trae jack de 3.5 mm — la
  salida de audio requiere HDMI, DAC USB o HAT I2S + amplificador + bocina, nada de lo cual
  está en el BOM. Especificación de la tarea propuesta: §11 A-6.

## 10. Registro de gates HW/despliegue (llenar presencialmente — SIN marcar)

| # | Gate | Prueba | Criterio de aceptación | Medido | OK/NO | Fecha/inicial |
|---|---|---|---|---|---|---|
| G-01 | Restart en frío del Pi (L1) | `sudo reboot` en cada Pi con gabinete armado | `takab-edge` y `takab-gpio` activos; backend gpiozero = lgpio verificado en el arranque (journal); relés responden; sin caída a sysfs |  |  |  |
| G-02 | SPOF-02 ruta hardware (L2) | §6 del RUNBOOK-SPOF-02 (Pi apagado, WR-1 activo) | Sirena suena por la ruta eléctrica; llenar §8 de ese runbook |  |  |  |
| G-03 | Soak 24 h + restart físico del Shake (L3/T-1.5) | 24 h de SeedLink continuo + power-cycle del Shake | Cero huecos no recuperados (resume por seqnum); reconexión limpia |  |  |  |
| G-04 | Radio WR-1 real (L3/T-1.42) | Recepción SASMEX real o prueba CIRES | Semántica pulso/sostenido documentada; latching correcto; latencia contacto→relé→sirena < 100 ms |  |  |  |
| G-05 | Config firmada aplicada (B4) | Publish desde SOC → gabinete físico | `config-state`: `in_sync: true` + fingerprint; rollback verificado |  |  |  |
| G-06 | Simulacro E2E por sitio real (E1) | Sismo simulado en sitio + cascada real | Incidente en SOC < SLO; notificación webhook/email entregada; miniSEED backfilled descargable |  |  |  |
| G-07 | Replay HMAC en hardware (S2) | Re-emitir comando capturado al gabinete | Rechazo por nonce visto + auditoría del rechazo |  |  |  |
| G-08 | Load-test a escala objetivo (O2) | RUNBOOK-load-test con flota comercial | SLOs p95 del blueprint en verde sostenidos |  |  |  |
| G-09 | Restore de backup (O3) | Restaurar snapshot DLM en instancia limpia | DB íntegra; RPO/RTO medidos y publicados |  |  |  |
| G-10 | Panel LAN + PIN + MFA runtime (T-1.43/T-1.53/S4) | En el Pi real: GET sin PIN, POST con/sin PIN; login por rol en pool real | GET 200 público LAN; POST 401 sin PIN / 200 con PIN; lockout 5/60 s; MFA TOTP exigido por rol |  |  |  |

## 11. HALLAZGOS priorizados (tareas futuras — NO ejecutadas en esta auditoría)

### ALTO

| # | Hallazgo | Evidencia | Tarea propuesta |
|---|---|---|---|
| A-1 | **`main` remota en ROJO + 21 commits sin push**: la nube viva (2ca20fb) corre código que nunca pasó CI en GitHub; el fix de idempotencia (715ee36) solo existe local | `gh run view 29066872312` → job api failure, 650 errors por `alembic upgrade head` exit 1; `git log origin/main..main` = 21 | `git push origin main`, verificar 5 jobs verdes, y adoptar la regla "solo se despliega desde main pusheado y verde" (documentarla en el runbook de deploy) |
| A-2 | **GPIO sin fail-loud explícito**: en prod nadie fija ni asierta `LGPIOFactory`; un fallo de lgpio distinto al CWD caería en silencio a `native` | `gpio/__init__.py:78-88,157-159`; mitigación solo operacional (`takab-edge.service:24-31`, `critical=True`) | En `_on_start` de producción: `Device.pin_factory = LGPIOFactory()` explícita y `raise` ruidoso si no se puede instanciar; test unitario del contrato + verificación en G-01 |
| A-3 | **`make demo-fase1` ya no acredita el hito**: 33 OK · 2 FALLOS deterministas (era 36/36 el 2026-07-08) | asserts intermedios de C2 `demo/run.py:317-325` (sin-corroborar=[] y trigger); outcomes verdes; 2 corridas idénticas | Diagnosticar si es visibilidad transaccional post-`drain()` (carrera lectura-tras-escritura) o cambio de semántica de T-1.47/T-1.48; corregir demo o pipeline según corresponda y RE-ACREDITAR 3 corridas |
| A-4 | **Cero paginado a humanos**: sin CloudWatch alarms ni SNS; gabinete caído/batería/DLQ/5xx = solo color en la UI | grep `metric_alarm\|sns_topic` en infra = exit 1; `fail_open.py:103` solo con quórum | Terraform: SNS topic on-call + alarmas mínimas (gateway offline > 5 min por LWT/heartbeat, DLQ > 0 por 5 min, 5xx de la API, disco/CPU del EC2, batería < umbral) |
| A-5 | **Backup sin restore probado ni RPO/RTO** (solo snapshots EBS diarios, retain 7) | `database/main.tf:268-288`; sin runbook de restore en `takab-docs/runbooks/` | Runbook backup/restore + prueba real de restauración (G-09), PITR con archivado WAL (p.ej. WAL-G a S3), declarar RPO/RTO |
| A-6 | **Audio de voceo (simulacro/sismo) INEXISTENTE** — solicitado en esta auditoría; el Pi 5 ni siquiera tiene jack 3.5 mm | grep audio en repo = exit 1; sirena = relé seco (`contracts.py:54`) | Nueva tarea edge `audio`: (1) BOM: DAC USB o HAT I2S + amplificador + bocina de intemperie; (2) módulo `edge/takab_edge/audio` FUERA del camino crítico (el relé JAMÁS espera al audio); (3) assets versionados con sha256 — mensaje de SISMO claramente distinto al de SIMULACRO; (4) disparo determinista subordinado a `rules`/reflejo + botón drill en panel LAN con PIN; (5) autotest periódico de bocina con reporte al heartbeat; (6) systemd hardening igual que takab-gpio |

### MEDIO

| # | Hallazgo | Evidencia | Tarea propuesta |
|---|---|---|---|
| M-1 | No existe modo SIMULACRO end-to-end (ni endpoint, ni UI, ni programador) — solo self-test de sirena de 2 s | grep drill/simulacro api+web = vacío | Diseñar "drill mode": comando firmado `drill_start` (rotulado NO-real en todo el pipeline), banner diferenciado en SOC/panel, registro de participación para PC |
| M-2 | Botón AUTODIAGNÓSTICO SILENCIOSO es stub `disabled` | `SiteCard.tsx:107-114` | Implementar acción `self_test` en el Command Service (extensión T-1.23) + recorrido de relés sin energizar audibles |
| M-3 | Notificaciones: SMS y WhatsApp SIMULADOS; push inexistente; email en SES sandbox | `notify/providers.py:117-124` | Contratar/integrar SMS (Twilio/local), WhatsApp Business Cloud API, sacar SES de sandbox; push llega con T-1.31 |
| M-4 | LFPDPPP aspiracional; PII en us-east-2; sin aviso de privacidad/ARCO/retención de PII | blueprint `:408`; `providers.tf:18` | Antes del primer cliente: aviso de privacidad + consentimiento, política de retención de PII, evaluar región MX/localización, confirmar marco normativo citable (blueprint §9) |
| M-5 | "occupant sin MFA" del RBAC doc no implementado (pool único MFA=ON para todos — hoy MÁS estricto) | `identity/main.tf:42-45` | Decidir en T-1.31: pool aparte para occupant o ratificar MFA universal y corregir RBAC-TAKAB.md |
| M-6 | Card "Relés del Gabinete" no distingue error/stale del empty (regla de oro 7 parcial) | `console/DetailPanel.tsx:322-332` + `useSiteRelays.ts:10-14` | Propagar `error/isStale` de useFleet al card con StateFrame |
| M-7 | Playwright prometido (stack y smoke citado) pero sin setup committeado en web/ — smoke no reproducible | `CLAUDE.md:89`; `TASKS.md:525`; `web/package.json` sin playwright | Committear config Playwright + spec de smoke mínimo (login dev → 4 rutas → sin errores de consola) al CI, o corregir la documentación |
| M-8 | Pendientes de apply/ejecución: T-1.44 `[ ] Aplicado` + paso plan-only TODO; T-1.47 purga EC2; T-1.53 verificación panel en Pi | `TASKS.md:942`, `ci.yml:155`, `TASKS.md:1110-1111,1282-1288` | Ventana de cierre: terraform apply (T-1.44) + cablear el job plan-only; ejecutar runbook de purga en EC2; smoke del panel en el Pi (G-10) |

### BAJO

| # | Hallazgo | Evidencia | Tarea propuesta |
|---|---|---|---|
| B-1 | `make test` ≠ CI: corre sin `-m "not perf"` | `Makefile:73` vs `ci.yml:53` | Alinear el target o documentar la diferencia |
| B-2 | `demo/tests/test_spool.py` no corre en `make test` ni en CI (cobertura huérfana) | inspección Makefile + ci.yml | Añadirlo a un job o al target test |
| B-3 | Subconjuntos multi-archivo de `tests/api` inestables: doble fixture `client` | `tests/api/conftest.py:281` vs `tests/_telemetry_fixtures.py:215` (reproducido: 29 errors en subset, verde solo/completo) | Renombrar la fixture de telemetría o aislar el plugin |
| B-4 | Título de BuildingPage sin estados propios (los paneles sí los tienen) | `BuildingPage.tsx:38-45` | Envolver el header en StateFrame o fallback explícito |
| B-5 | `vistas_v1/` sin trackear (4 PNG de mockups; typo "Multi-Tanant.png") | `git status` | Decidir: versionar en takab-docs/ o añadir a .gitignore; corregir typo |
| B-6 | Build web con chunks > 500 kB (warning de Vite) | salida `npm run build` | manualChunks para maplibre/react cuando toque optimizar |
| B-7 | Cálculos de ingeniería ausentes: intensidad MMI, aceleración espectral Sa, deriva de entrepiso | grep en api/src (solo `felt_band`, picos PGA/PGV del edge) | Roadmap post-MVP junto al mini-ShakeMap (§14); **la magnitud NO se propone: diferida por diseño (WR-1 booleano)** |

## 12. Propuestas para "proyecto completo" (roadmap sugerido, sin ejecutar)

Además de resolver §11, para que TAKAB Ailert sea un producto comercial completo faltan:

1. **Canal humano de emergencia real** (A-4 + M-3): on-call, escalamiento, y SMS/WhatsApp/push
   reales — hoy solo webhook y email sandbox notifican de verdad.
2. **Modo simulacro institucional** (M-1): Protección Civil vive de simulacros; programación
   (calendario), ejecución rotulada, y reporte de participación/tiempos por edificio.
3. **Voceo por audio en el gabinete** (A-6): instrucciones habladas diferenciadas
   sismo/simulacro — complementa (nunca sustituye) la sirena de relé.
4. **Gestión de usuarios y roles desde la consola**: hoy el alta de operadores es manual en
   Cognito; falta UI de invitación/rol/tenant para tenant_admin.
5. **Onboarding de tenant**: no existe alta de tenant en UI (el "NUEVO tenant" del mockup se
   retiró a propósito); definir flujo comercial (contrato → tenant → sitios → gabinetes).
6. **Cumplimiento como producto** (M-4): aviso de privacidad, ARCO, retención, residencia de
   datos, y el marco normativo citable de PC (blueprint §9).
7. **Operación de flota**: actualización remota de firmware/software del edge (hoy: ssh +
   deploy.sh manual), inventario de versiones, y ventanas de mantenimiento.
8. **Backup/DR de verdad** (A-5): PITR, restore ensayado, RPO/RTO publicados.
9. **Cálculos estructurales post-MVP** (B-7 + blueprint §13/§14): MMI por sitio, Sa espectral,
   deriva de entrepiso, y el mini-ShakeMap cuando toque — insumos del dictamen de habitabilidad.
10. **App móvil (T-1.31, diferida)**: superficie de occupant/brigadas — mantener diferida hasta
    cerrar Fase 1 comercialmente.
11. **Export por lote**: decisión vigente de NO tenerlo (sin endpoint batch); reevaluar con el
    primer cliente que lo pida — hoy la descarga es objeto por objeto, correcta para evidencia.
12. **E2E de navegador committeado** (M-7): el smoke de Playwright que TASKS cita, versionado y
    en CI.

## 13. Registro de ejecución (2026-07-11)

- Lint: api ✔ (ruff check + format, 232 archivos) · web ✔ (eslint + prettier) · edge ✔ (57 archivos).
- Suites completas: **api 741 passed** (1 skipped, 2 deselected-perf; DB fresca) · **web 525
  passed** (55 archivos) + build ✔ · **edge 273 passed**.
- Suites dirigidas (nominales, logs en scratch): S1 34 · S2 46 · E2 79 · E3 13 · B4 33 ·
  notify 33 · B3/F1/F2 39 · edge-dirigido 75 · web-render 58. Todos passed.
- `make demo-fase1`: **33 OK · 2 FALLOS** (×2 corridas — A-3).
- Vivo (soc-local): F1 alta 201×3 · F2 retiro 200 idempotente+fila viva · F3 quake→2 incidentes
  critical + sasmex→sirena enclavada→CERRAR ALERTA · B3 PDF sha256 cotejado · B4 PUT 201/409 +
  publish 202 + config-state honesto.
- Nube viva (solo GET): `/` 200 HTML con HSTS, last-modified 2026-07-11 15:37 UTC;
  `/api/health` → `{"status":"ok"}`.
- CI remota main: run 29066872312 = api FAILURE (650 errors) · 4 jobs verdes · **21 commits sin
  push**.
