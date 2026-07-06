# ANÁLISIS DE ARQUITECTURA — TAKAB Ailert
**Revisión red-team de los artefactos de diseño · rama `analisis/arquitectura-00` · 2026-07-05**

> Alcance: solo artefactos de diseño (blueprint, schema, RBAC, TASKS, user stories, FASE-0,
> PROMPT-01). Cero código de producción tocado. Corpus leído completo antes de editar nada.
> Cada hallazgo lleva **estado**: `aplicado` (corregido en esta rama, revertible),
> `requiere aprobación` (diseño intacto; decide Mauricio), `pregunta abierta` (falta dato).
> Los edits aplicados están marcados en los archivos con `[ANALISIS-00]`.

---

## 1. Resumen ejecutivo

El diseño es **fundamentalmente sano**: la separación edge/cloud es real (ningún camino de
vida depende de la nube), el determinismo del path crítico se respeta en todos los documentos
vigentes, no hay fugas de features diferidas (T-MINUS/magnitud/mini-ShakeMap aparecen solo como
prohibiciones), y la secuencia edge-first es correcta. Pero la reescritura del blueprint
(commit `61078d6`, 5-jul) **perdió decisiones de vida/seguridad de FASE-0 y reintrodujo un
error de compliance que FASE-0 ya había cazado**, y el `schema.sql` "fuente de verdad" ni
siquiera aplicaba limpio. Top de riesgos:

1. **C1 — La restricción "dura" de compliance citaba una norma de etiquetado de materiales
   peligrosos en transporte** (NOM-003-SCT/2008, verificado contra el DOF), con confirmación
   circular entre blueprint y RBAC. La regla de inmutabilidad se conserva; la cita se corrigió.
2. **C2 — Las mitigaciones SPOF de FASE-0 habían desaparecido del blueprint canónico**, incluida
   la ruta de hardware paralela SASMEX→sirena ("la mitigación más importante de todo el
   sistema": sirena que suena aunque el Pi esté muerto). Reincorporadas (§4.7).
3. **A1 — La ventana de quórum de 2–5 s era físicamente imposible** para sitios separados
   90–110 km (deltas de arribo de onda de 10–20 s): la "regla 3 nodos" del Triage jamás se
   habría cumplido con sismos reales. Corregida a ventana consciente de distancia.
4. **A2/A3/A4 — El DDL no aplicaba** (función RLS inexistente), dejaba **default-allow** en ~14
   de 17 tablas, permitía a `gov_operator` escribir sobre tenants compartidos, y el "borrado de
   incidente" arrastraba en CASCADE su timeline auditable. Todo corregido y verificado
   empíricamente: aplica limpio y pasa un smoke test de 18 casos de RLS/inmutabilidad en
   PostgreSQL+PostGIS real (§6; la pasada TimescaleDB queda lista para T-1.16).
5. **A7 — T-1.1 estaba marcada COMPLETA con su criterio de CI sin cumplir**: `.github/workflows/`
   y `.env.example` no existen en ningún commit, y el blueprint afirmaba "CI verde en el primer
   run". Corregido el relato; el CI completo es ahora criterio explícito de T-1.2.
6. **A8 — Nadie producía los contratos `shared/schemas`** sobre los que "se construye la nube".
   Añadidos como criterios de T-1.11/T-1.17.

**Recomendación: SÍ proceder** a planear/implementar T-1.2 en adelante, en este orden:
(1) Mauricio revisa esta rama y las 9 decisiones/preguntas de §4; (2) se ratifican o revierten
los edits `[ANALISIS-00]`; (3) las decisiones #4 (BACnet vs relés), #5 (GraphQL vs REST+WS) y
#6 (proceso `gpio` consolidado) conviene cerrarlas ANTES de T-1.8/T-1.9/T-1.22; el resto no
bloquea el arranque del edge. Ningún hallazgo invalida la arquitectura; todos eran corregibles
en documentos.

---

## 2. Hallazgos

Formato: descripción · evidencia · impacto · recomendación · **estado**.

### 2.1 Críticos

**C1 · Compliance anclado a norma equivocada, con confirmación circular**
- **Evidencia:** `archive/FASE-0 §Decisiones pendientes #3` (23-jun): "NOM-003-SCT: es de
  transporte; no aplica. Sustituir". Blueprint 5-jul §0.6/§9/§5.3/§5.4/§6/§7.3 la reinstauró como
  "restricción dura"; el diff de `RBAC-TAKAB.md §8.3` (zip→actual) muestra el cambio de "no
  aplica" a "confirmado como vinculante por BLUEPRINT §9" — el blueprint citándose a sí mismo.
  Verificación externa: NOM-003-SCT/2008 = "Características de las etiquetas de envases y
  embalajes, destinadas al transporte de substancias, materiales y residuos peligrosos"
  ([DOF/gob.mx](https://www.gob.mx/cms/uploads/attachment/file/680141/NOM-003-SCT-2008.pdf)).
- **Impacto:** vender "cumplimiento NOM-003-SCT" en la pantalla de Triage a Protección Civil es
  indefendible ante el primer revisor legal; erosiona credibilidad del producto completo.
- **Recomendación:** requisito propio de TAKAB (inmutabilidad/no-poda, intacto) + marco citable
  por confirmar con abogado/cliente (candidatos: Ley General de Protección Civil y reglamentos
  estatales, términos de referencia de contratos de PC, normativa local de revisión estructural
  post-sismo, LFPDPPP para PII).
- **Estado:** `aplicado` en blueprint/RBAC/TASKS (conforme a la decisión que FASE-0 ya había
  tomado) + `pregunta abierta` #1 (marco real) + `requiere aprobación` para `CLAUDE.md:71` (§5).

**C2 · Mitigaciones SPOF de vida/seguridad perdidas en la reescritura del blueprint**
- **Evidencia:** FASE-0 §1.1 (SPOF-01…07) vs blueprint §4.1–§4.6 (antes de esta rama): sin ruta
  de hardware paralela WR-1→sirena, sin watchdog HW, sin prohibición de microSD, sin overlayroot,
  sin RTC, sin fail-safe NO/NC por actuador, sin heartbeat del contacto de prueba CIRES, sin
  dimensionado UPS para pico de sirena. TASKS sí conservaba T-1.4 (ruta paralela) y NO/NC en
  T-1.3 — es decir, el backlog recordaba lo que el documento canónico ya no.
- **Impacto:** el blueprint es lo que se consulta al implementar; diseño de gabinete sin estas
  mitigaciones = sirena muda con Pi congelado (la causa #1 de muerte de Pi en campo es SD
  corrupta), puertas retenidas en falla, relojes a la deriva sin internet.
- **Recomendación/estado:** `aplicado` — nueva §4.7 del blueprint (tabla SPOF→mitigación
  obligatoria) + filas de hardware (relé paralelo, RTC) + `cert_days_remaining` en `health`.

### 2.2 Altos

**A1 · Ventana de quórum 2–5 s físicamente inalcanzable**
- **Evidencia:** blueprint §4.5, CLAUDE §1.3, FASE-0 header/tarea 2.3, `rule_sets.config`
  ejemplo (`window_s:5`), T-1.19. Sitios de referencia: Cholula↔CDMX ≈ 92 km, ↔Tehuacán ≈ 110 km,
  ↔Zacatlán ≈ 100 km, ↔Atlixco ≈ 20 km. Física: v_P ≈ 6–8 km/s ⇒ deltas de arribo entre
  estaciones de 10–20 s para epicentros regionales típicos (p. ej. costa de Guerrero); incluso el
  par más cercano (20 km) da ~3 s en el mejor caso. ≥3 estaciones dentro de 2–5 s ⇒ solo
  clústeres co-localizados; la red planeada no lo es.
- **Impacto:** la "regla 3 nodos" (feature comercial del Triage y evidencia del dictamen) nunca
  se cumpliría con sismos reales; el anti-falso-positivo colaborativo sería letra muerta. No es
  riesgo de vida (el quórum jamás bloquea actuación), pero sí de producto/credibilidad.
- **Recomendación:** asociación por pares consciente de distancia: `|Δt_ij| ≤ dist_ij/v_P + margen`
  (v_P = 6.5 km/s, margen 3 s, tope 30 s), parámetros en `rule_sets.config.quorum`.
- **Estado:** `aplicado` (blueprint §4.5, schema comentario, T-1.19) — **corrección técnica a una
  "decisión cerrada" de FASE-0; revertible si Mauricio no la ratifica** + `pregunta abierta` #2
  (validar parámetros contra catálogo del SSN).

**A2 · `db/schema.sql` no aplicaba limpio y violaba P5**
- **Evidencia:** política de `sites` invocaba `visibility_of_tenant()` **jamás definida** (el
  propio archivo lo admitía en una nota); `device_health_10s` = telemetría cada 10 s (P5:
  "logging por evento, no por intervalo") contradiciendo blueprint §5.4 y TASKS T-1.10/T-1.17/
  T-1.28 que ya usaban `device_health`; US-06 referenciaba la tabla vieja; header decía "aplicar
  vía Alembic (tarea T-1.3)" con numeración obsoleta (hoy T-1.3 = GPIO; las migraciones son T-1.16).
- **Impacto:** el criterio de aceptación de T-1.16 ("Alembic aplica limpio") habría fallado en el
  primer intento; la tabla `_10s` habría institucionalizado logging por intervalo.
- **Estado:** `aplicado` — verificado aplicando el schema (menos sentencias TimescaleDB) contra
  PostgreSQL 18 + PostGIS reales: 0 errores (§6).

**A3 · RLS: default-allow de facto, gov con escritura, sin FORCE, sin ramas de servicio**
- **Evidencia:** solo `sites`/`incidents`/`waveform_features_1s` tenían `ENABLE ROW LEVEL
  SECURITY` (el "replicar en todas" era un comentario); sin `FORCE` (el owner bypassa RLS);
  política única `FOR ALL` ⇒ `gov_operator` heredaba WITH CHECK de escritura sobre tenants
  `gov_shared` (su decisión cerrada es "solo lectura + acuse"); ninguna rama para
  `takab_superadmin`/`takab_support` ni para ingesta ⇒ con default-deny real esos flujos quedaban
  ciegos (el superadmin no vería nada).
- **Impacto:** aislamiento multi-tenant (regla de oro 5) no garantizado a nivel de datos; el
  test obligatorio "cruzar tenants DEBE fallar" habría pasado trivialmente… por ausencia de
  política, en las tablas equivocadas.
- **Estado:** `aplicado` — ENABLE en las 17 tablas de negocio, con FORCE en las relacionales
  (las 3 hypertables con jobs de TimescaleDB van sin FORCE: los jobs de compresión/caggs corren
  como owner y FORCE los dejaría viendo 0 filas — decisión documentada en schema §8; la API
  nunca es owner, así que sigue 100% sujeta a RLS); políticas de lectura y escritura separadas;
  gov = SELECT-only (su acuse va por función `SECURITY DEFINER` `gov_ack_incident`, a crear en
  T-1.16); roles internos con política propia; ingesta vía rol `takab_ingest` con BYPASSRLS
  documentado (sin login interactivo). Smoke test 18/18 en §6.

**A4 · Inmutabilidad de evidencia no garantizada por el modelo de datos**
- **Evidencia:** `incident_actions` con `ON DELETE CASCADE` desde `incidents` (borrar incidente
  = borrar timeline auditable); `dictamens`/`evidence_objects` sin protección UPDATE/DELETE;
  `audit_log` solo con `REVOKE … FROM PUBLIC` (no cubre grants explícitos ni al owner).
- **Impacto:** la promesa central de compliance ("evidencia y dictámenes nunca se podan/alteran")
  era aspiracional, no estructural.
- **Estado:** `aplicado` — FK a RESTRICT; triggers append-only en `audit_log`,
  `incident_actions`, `dictamens`, `evidence_objects`, `life_checkins`, `rule_evaluations`;
  dictámenes versionados por fila nueva (`supersedes_dictamen_id`; firmar/corregir = INSERT).

**A5 · `tenant_id` ausente en tablas de negocio (regla de oro 5)**
- **Evidencia:** `dictamens`, `life_checkins`, `manual_activation_votes`, `zones`,
  `device_health` sin `tenant_id`; `seismic_events` y `quorum_votes` tampoco lo tienen.
- **Estado:** `aplicado` — columna+FK añadidas a las cinco primeras (RLS directa sin joins);
  para `seismic_events`/`quorum_votes` se documentó la **excepción deliberada**: son datos DE
  RED (un evento regional cruza tenants por definición del quórum); lectura compartida entre
  autenticados, escritura solo del motor de incidentes. El `sensor_id` ajeno en `quorum_votes`
  no es resoluble por otros tenants (la RLS de `sensors` lo tapa).

**A6 · 200 Hz vs 100 sps (dato de proveedor falso en el doc canónico)**
- **Evidencia:** blueprint (5 menciones), T-1.5 y `CLAUDE.md:66` decían 200 Hz; schema
  (`sample_rate DEFAULT 100`) y FASE-0 decían 100. Spec oficial del RS4D: **100 sps**, canales
  EHZ + ENZ/ENN/ENE ([manual.raspberryshake.org](https://manual.raspberryshake.org/specifications.html)).
  La aritmética del buffer ("ring 7–14 días ≈ 10–16 GB") estaba inflada ~10–20× (real: ~0.5–4 GB
  según compresión).
- **Impacto:** features, filtros anti-alias, tests de referencia y presupuesto de latencia se
  habrían calibrado contra una frecuencia inexistente.
- **Estado:** `aplicado` en blueprint/TASKS/schema (default de canales corregido a los 4 del
  RS4D); `CLAUDE.md:66` = `requiere aprobación` (§5); confirmación final con proveedor en §15.

**A7 · T-1.1 "COMPLETA" sin cumplir su DoD + afirmación falsa de CI**
- **Evidencia:** `git ls-tree` de TODA la historia: `.github/` y `.env.example` jamás
  existieron; el propio checklist de T-1.1 tenía el criterio de CI sin palomear mientras el
  título decía COMPLETA; blueprint §0.8 afirmaba "CI verde en el primer run, PR #1 abierto"
  (la rama local está 2 commits adelante de origin; no hay PR en este repo); README instruye
  `cp .env.example .env` (roto); el plan de T-1.1 (superpowers) sí contemplaba ambos archivos.
- **Impacto:** viola el método (§6 CLAUDE: DoD antes de cerrar); cualquier tarea siguiente
  asumiría un CI que no existe.
- **Estado:** `aplicado` — blueprint §0.8 reescrito a la realidad; criterio trasladado
  explícitamente a T-1.2 (workflow completo api+web+edge); `.env.example` creado en esta rama.
  T-1.1 NO se reabre (respetando CLAUDE §0.3); solo se documenta el faltante.

**A8 · Ninguna tarea producía los contratos `shared/schemas`**
- **Evidencia:** principio §0.1 ("la nube se construye sobre contratos ya validados en el
  edge") + estructura `shared/schemas` en CLAUDE §4… y ni una tarea de T-1.2→T-1.31 los
  generaba; T-1.17 consumiría payloads sin contrato.
- **Estado:** `aplicado` — T-1.11 publica conforme a JSON Schema versionados en `shared/schemas/`
  (generados de los modelos Pydantic del edge; simuladores validan contra ellos); T-1.17 valida
  cada payload y manda a DLQ lo no conforme.

**A9 · Matriz RBAC: `gov_operator` con "Total" en Triage**
- **Evidencia:** `RBAC-TAKAB.md §2` fila gov vs su propia nota ("solo lectura + acuse", decisión
  cerrada) y CLAUDE/blueprint. "Total" en Triage implicaría crear/firmar dictámenes de terceros.
- **Estado:** `aplicado` — celda corregida a "Lectura + export" + nota; en datos, RLS ya solo le
  da SELECT (A3).

### 2.3 Medios

**M1 · Módulo edge `quorum` = scaffold muerto → resolución quórum edge-vs-cloud**
- El encargo pedía resolver explícitamente dónde vive el quórum. **Resolución: NUBE.** Los tres
  documentos vigentes ya coincidían (CLAUDE §1.3 "se correlaciona en la nube", blueprint §4.5,
  T-1.19); lo incoherente era un módulo edge `quorum` que ninguna tarea implementaba y que un
  gabinete con UN sensor no puede usar (nada que correlacionar localmente). Implicaciones:
  latencia irrelevante (el quórum jamás gates la actuación local — solo confianza/dictamen);
  autonomía intacta (SPOF-01 de FASE-0 ya lo blindó: SASMEX por radio + umbral local sin
  quórum); una malla edge-to-edge entre edificios de tenants distintos sería un pantano
  operativo (VPNs cruzadas, descubrimiento, seguridad) sin beneficio en MVP.
  **Estado:** `aplicado` (módulo removido de §4.2/§4.4/T-1.2 con nota de trazabilidad; correlación
  intra-sitio futura viviría en `rules`) — ratificación en decisión #2.

**M2 · `local_api` exigida por RBAC/TASKS pero ausente del blueprint**
- RBAC §4.2 (silencio por LAN) y T-1.13 la requieren; blueprint §4.2/§4.4 no la tenía (FASE-0 sí:
  `takab_local_api`). Sin ella, silenciar la sirena post-evento con la WAN caída sería imposible.
  **Estado:** `aplicado` (módulo añadido a blueprint y al scaffold de T-1.2).

**M3 · Camino crítico SASMEX cruza 3 procesos con IPC sin especificar**
- Blueprint separa `sasmex` (GPIO in) → `rules` → `actuators` (out) como servicios; el bus
  mosquitto de FASE-0 §1.2 desapareció sin sustituto; y CLAUDE regla de oro 4 habla de "el
  proceso GPIO/actuadores" EN SINGULAR (diseño FASE-0: `takab_gpio` mínimo con WR-1 + relés en
  el mismo proceso, reflejo <70 ms). Cada hop de IPC en el camino de vida añade latencia y modos
  de falla. **Recomendación:** proceso `gpio` consolidado (entrada WR-1 + relés locales +
  reflejo SASMEX→sirena hardcodeado); `actuators` queda como adaptador BACnet para secuencias
  no-reflejas; bus local solo para telemetría. **Estado:** `requiere aprobación` (decisión #6) —
  el blueprint solo lleva la nota; no construir T-1.8/T-1.9 sin cerrar esto.

**M4 · Presupuesto de latencia ambiguo y parcialmente imposible**
- "Decisión local p95 <1 s" chocaba con features agregadas a 1 s y con la latencia real de
  SeedLink del Shake (empaquetado miniSEED de 512 B ≈ varios segundos a 100 sps; el "0.2–0.5 s"
  de FASE-0 no está validado). **Estado:** `aplicado` — presupuestos POR CAMINO en §4.3
  (SASMEX <100 ms; feature→actuación <200 ms; suelo→actuación ≤2 s objetivo A VALIDAR) +
  `pregunta abierta` #3 (medir SeedLink real; evaluar UDP datacast SIN cambiar la regla que hoy
  lo prohíbe — eso lo decide Mauricio con el dato en la mano).

**M5 · Blueprint §5.4 describía un modelo de datos que no existe**
- Tablas fantasma (`buildings`, `floors`, `devices`, `device_bindings`, `integrations`…) e
  hypertables no creadas (`site_state_snapshots`). **Estado:** `aplicado` — §5.4 alineado a los
  nombres reales del DDL; `notification_jobs`/`billing_meters_daily` marcadas "pendientes por
  WP" (B6/B10); `rule_evaluations` SÍ se añadió al schema (el blueprint la exigía, P5 la
  justifica: transiciones de tier sin incidente no tenían dónde registrarse);
  `site_state_snapshots` se eliminó (derivable de `gateways.status` + agregados).

**M6 · "Schema por tenant" y "KMS por tenant" sobre-prometidos**
- §10 mezclaba "schema por tenant" con RLS (modelos distintos); "AES-256 con KMS por tenant"
  es imposible a nivel storage en una RDS compartida (una llave por instancia). **Estado:**
  `aplicado` — §10 corregido a RLS puro; §8 precisa el modelo real de llaves: llave de instancia
  RDS + envelope pgcrypto por tenant para campos sensibles + SSE-KMS por tenant en S3 + llave
  dedicada solo en despliegues `dedicated`.

**M7 · Cascada fail-open sin disparador definido**
- "Edge SIN ENLACE ⇒ disparar todos los canales" — ¿disparados por QUÉ evento, si la nube no
  tiene feed SASMEX propio? **Estado:** `aplicado` como definición (incidente regional
  corroborado por otras estaciones/fuente externa cuya geometría alcanza al sitio sin enlace;
  región entera caída ⇒ solo protección local + aviso de pérdida de visibilidad) +
  `pregunta abierta` #8 (feed CIRES/SSN de eventos como fuente externa).

**M8 · T-1.16 dependía de Terraform/AWS sin necesidad**
- Migraciones y tests RLS corren contra el Postgres del `docker-compose.yml`. Exigir T-1.15
  primero encarece y rompe el espíritu edge-first (validar contratos antes de provisionar).
  **Estado:** `aplicado` — T-1.16 depende de T-1.1; T-1.17 sí exige T-1.15+T-1.16.

**M9 · Continuous aggregates sin `tenant_id` y sin RLS posible**
- TimescaleDB no aplica RLS a caggs; `site_metrics_1m` ni siquiera traía `tenant_id`: cualquier
  endpoint que la consultara directo filtraría PGA máximos de sitios ajenos. **Estado:**
  `aplicado` — caggs 1m/1h con `tenant_id`, regla dura "jamás exponer sin JOIN a `sites`",
  y `compress_segmentby` con `tenant_id,site_id` (las políticas y queries filtran por esas
  columnas; fuera del segmentby forzaban descompresión fila a fila).

**M10 · `site_scope` vacío = "todo el tenant" (default-allow) + MFA de ocupantes**
- Un usuario sin asignación heredaba TODOS los sitios del tenant. **Estado:** `aplicado`
  (vacío/ausente = sin acceso; tenant completo = `"*"` explícito; alcances grandes se resuelven
  server-side, no inflando el JWT). Derivado sin resolver: RBAC §4.3 exige MFA a todo rol que
  pueda activar actuadores — eso incluye a `occupant` (activa vía quórum de 2), que se enrola
  por QR sin fricción. MFA universal a ocupantes probablemente mata la adopción del botón de
  pánico. `pregunta abierta` #7.

**M11 · Sobre-ingeniería para 4–8 sitios (tres frentes)**
- (a) **REST + GraphQL subscriptions en paralelo** para UN consumidor propio: dos contratos, dos
  capas de authz, infra de subscriptions en Fargate. FASE-0 había elegido WebSocket simple; la
  etiqueta del deck no es spec. Recomendación: REST+WS en MVP. **`requiere aprobación`**
  (decisión #5; stack congelado en CLAUDE §3 — nota añadida en blueprint §5.5, nada cambiado).
- (b) **Suite BACnet completa en MVP** (gas/ascensores/puertas) cuando FASE-0 la difería a "solo
  si un contrato lo exige" (2.10, Baja) y acotaba el MVP a sirena+estrobo por relés.
  Recomendación: relés fail-safe como actuación primaria; BACnet detrás de la misma interfaz
  cuando lo pida un contrato. **`requiere aprobación`** (decisión #4; T-1.9 intacta, nota en §13).
- (c) **CCTV ONVIF como criterio de aceptación de T-1.27** siendo "opcional" en §4.1.
  **`aplicado`** — marcada opcional, no bloquea la tarea.

**M12 · FASE-0 y PROMPT-01 no existían en el repo**
- Borrados de HEAD en `61078d6`; solo vivían dentro de `files.zip`… que está en `.gitignore`
  (un clon fresco no los tendría), mientras el blueprint decía "convive con FASE-0".
  **Estado:** `aplicado` — restaurados de la historia git (bit-idénticos, md5 verificado) a
  `takab-docs/archive/` con preámbulo de no-canonicidad (las secciones UI de FASE-0 muestran
  T-MINUS/magnitud: son del deck, diferidas por §14).

**M13 · IA con poder de veto latente en FASE-0 §3.1**
- El plan de Fase 3 permite "suprimir el disparo de umbral local si p(ruido)>0.9". CLAUDE regla
  de oro 1: la IA "jamás veta". Suprimir un disparo ES vetar una alerta (aunque sea el canal
  secundario). Hoy no hay IA en MVP (P4), pero el conflicto explotará al llegar Fase 3.
  Alternativas para entonces: (i) el score solo DEGRADA la notificación de `watch` (nunca toca
  `restricted`+); (ii) shadow mode permanente hasta evidencia de 12+ meses; (iii) cambiar la
  regla de oro (inaceptable sin decisión explícita). **Estado:** `pregunta abierta` #9 —
  principio intacto, nota en el preámbulo del archivo histórico.

### 2.4 Bajos (todos `aplicado` salvo indicación)

1. Header de `schema.sql` apuntaba a "tarea T-1.3" (numeración vieja) → T-1.16.
2. `sensors.channels DEFAULT '{EHZ}'` → `'{EHZ,ENZ,ENN,ENE}'` (canales reales del RS4D).
3. Blueprint §11 ubicaba `CLAUDE.md` en `takab-docs/` (vive en la raíz) → corregido; añadido
   `archive/` a la estructura y "(se crea en T-1.2)" al CI.
4. US-06/US-20 usaban numeración de FASE-0 ("fase 2.8"/"2.2") → anotada la equivalencia.
5. `manual_activation_votes` sin índice para la ventana de 30 s → `(site_id, created_at DESC)`.
6. `seismic_events.magnitude` podía leerse como "magnitud preliminar en vivo" (feature diferida)
   → comentario: es enriquecimiento POST-HOC del SSN; la UI MVP no la muestra.
7. Artefactos de diseño sueltos en la raíz (`SOC Console.html`, `SOC*.css`, `jsx/`,
   `design-system/`, `Design System/`) fuera de la estructura §11 → **solo recomendación**
   (moverlos a `takab-docs/design/` en una tarea de limpieza; no se movieron para no ensuciar
   este diff). `files.zip` local puede borrarse: su contenido ya está en `archive/`.
8. `user_zone_assignments` PK `(user_id, site_id)` impide multi-zona por sitio y `role` no tiene
   CHECK contra los roles de RBAC §1 → anotado para la fase móvil (no bloquea MVP web).
9. QR de enrolamiento estático + quórum de 2: dos fotos del QR permiten enrolar remotamente y
   disparar sirena. Mitigan: `max_uses`/`expires_at`/revocación + GPS auditado en la activación.
   Recomendación adicional: geofence del voto (GPS dentro del radio del sitio) al implementar.
10. US-09 "push que rompe silencio/No-Molestar" requiere **Critical Alerts entitlement** de
    Apple (aprobación explícita, no trivial) → riesgo de la fase móvil, documentado aquí.
11. Chequeo de fugas de features diferidas (§14): **limpio** — T-MINUS/magnitud/mini-ShakeMap/
    streaming crudo solo aparecen como prohibiciones o pendientes.
12. Consumo MQTT continuo (1 msg/s/sensor con 4 canales): ~2.6 M msgs/mes/sitio ≈ centavos en
    IoT Core/SQS para 4–8 sitios — sin problema de costo; batching opcional a futuro.

---

## 3. Changelog de cambios aplicados (esta rama)

| Archivo | Cambio | Razón (hallazgo) |
|---|---|---|
| `db/schema.sql` | Reescrito a v1.1: política `sites` reparada (inline EXISTS), helpers `app_*()` (`app_gov_can_see` con SECURITY DEFINER + search_path fijo — hallazgo del smoke test), ENABLE RLS en 17 tablas con **FORCE** en las relacionales (hypertables con jobs van sin FORCE, decisión documentada), políticas lectura/escritura separadas (gov = SELECT-only; acuse vía `gov_ack_incident` a crear en T-1.16), rol `takab_ingest` BYPASSRLS documentado, `device_health_10s`→`device_health` (+`reason`, compresión 7d), triggers append-only (audit/actions/dictamens/evidence/life_checkins/rule_evaluations), `incident_actions` FK RESTRICT, `dictamens` +`tenant_id`+`supersedes_dictamen_id`, +`tenant_id` en zones/manual_votes/life_checkins/device_health, `rule_evaluations` nueva, caggs 1m/1h con `tenant_id`, segmentby ampliado, índice ventana 30 s, defaults/comentarios (canales RS4D, T-1.16, magnitude post-hoc, quorum distance-aware) | A2, A3, A4, A5, M5, M9, bajos 1/2/5/6 |
| `db/verify_rls_smoke.sh` | Nuevo: smoke test de 18 casos (RLS default-deny, aislamiento, gov read-only, FORCE vs owner, append-only, RESTRICT) — 18/18 PASS en PG18+PostGIS; semilla de los tests de T-1.16 | A3, A4 (evidencia) |
| `takab-docs/BLUEPRINT-TECNICO-TAKAB.md` | §0.6 y §9 (norma→requisito propio, marco por confirmar), §0.8 (realidad del CI), P6/topología/§4.2/§6/A1-WP (200 Hz→100 sps y aritmética de buffer), §4.2 (sin `quorum`, +`local_api`, +cert en health, notas IPC/M3), §4.3 (presupuestos por camino), §4.4 (árbol sin quorum, +local_api), §4.5 (ventana distance-aware), **§4.7 nueva** (SPOF de FASE-0), §5.3/§5.4 (dictamen versionado; tablas alineadas al DDL + pendientes por WP), §5.5 (nota decisión GraphQL), §5.6 (disparador fail-open), §6 (niveles corregidos), §7.3 (sin cita NOM), §8 (quórum solo ocupantes; modelo real de llaves KMS), §10 (sin "schema por tenant"), §11 (CLAUDE en raíz; archive/), §13 (rango T-1.31; nota orden GPIO-first; nota decisión BACnet), §15 (SeedLink/UDP, sample rate, contactos WR-1, sirena vs UPS), header (archive + ANALISIS) | C1, C2, A1, A6, A7, M1–M7, M11, bajos 3 |
| `takab-docs/RBAC-TAKAB.md` | Matriz: gov Triage "Total"→"Lectura + export" + nota; §4.2 ref a §4.7/archive; §5.2 `site_scope` default-deny + nota anti-inflado de JWT; §6 nota de paridad con DDL; §8.3 revertido a PENDIENTE con la explicación del error circular | A9, C1, M10 |
| `takab-docs/TASKS.md` | T-1.1 criterio CI anotado como trasladado; T-1.2 (scaffold sin `quorum`, +`local_api`, workflow CI completo, feed 100 sps); T-1.5 (100 sps; lag contra simulador vs medir hardware); T-1.8 (<200 ms por camino; contrato `rule_evaluations`; doble disparo = un evento); T-1.11 (+contratos `shared/schemas`; +subida de evidencia a S3 con sha256); T-1.14 (+dep T-1.8); T-1.16 (dep T-1.1, criterios FORCE/append-only/`gov_ack_incident`); T-1.17 (+validación contra schemas + DLQ); T-1.19 (ventana distance-aware + test realista); T-1.20 (sin etiqueta NOM; versionado); T-1.25 (+regla 15 min; +evidencia); T-1.27 (CCTV opcional; suscripción según decisión #5); T-1.29 (sin cita NOM) | A1, A6, A7, A8, C1, M1, M2, M8, M11c |
| `takab-docs/USER-STORIES.md` | US-06 `device_health` + numeraciones FASE-0 anotadas (US-06/US-20) | A2, bajos 4 |
| `takab-docs/archive/` | FASE-0 y PROMPT-01 restaurados de `6c9b1e0` (md5 = snapshot original) con preámbulos de no-canonicidad | M12 |
| `.env.example` | Creado (variables del compose local, sin secretos) — el README ya instruía copiarlo | A7 |
| `takab-docs/ANALISIS-ARQUITECTURA-TAKAB.md` | Este documento | — |

Nada movido ni borrado sin nota; `main` intacto; sin merge.

---

## 4. Preguntas abiertas / decisiones para Mauricio

1. **Marco normativo de compliance (C1).** ¿Qué marco citable sustituye a "NOM-003-SCT"?
   Sugerencia: definir con abogado/primer cliente (Ley General de PC + reglamentos locales +
   términos contractuales). La inmutabilidad NO depende de esta respuesta — ya es estructural.
2. **Quórum edge-vs-cloud + ventana (M1/A1).** Ratificar: quórum en NUBE (edge solo publica
   detecciones) y ventana consciente de distancia (v_P 6.5 km/s, margen 3 s, tope 30 s).
   Validar parámetros con 3–5 sismos históricos del catálogo SSN sobre las coordenadas reales
   de los sitios.
3. **Dependencias de proveedor (Raspberry Shake / CIRES) — bloquean congelar §4.1–§4.5:**
   latencia real de SeedLink (decide si el camino instrumental ≤2 s es honesto y si se
   reconsidera el UDP datacast hoy prohibido); confirmación de 100 sps en las unidades
   compradas; semántica de contactos del WR-1 (¿alerta y prueba periódica separadas?, duración
   de cierre, rebote, latching, cadencia de pruebas CIRES para el heartbeat); pico de corriente
   de la sirena elegida vs UPS.
4. **Actuadores del MVP: ¿relés directos o suite BACnet completa?** (M11b). Recomendación:
   relés fail-safe primero, BACnet por contrato. T-1.9 queda como está hasta tu decisión.
5. **API en vivo: ¿GraphQL subscriptions o REST + WebSocket?** (M11a). Recomendación: REST+WS
   en MVP. El stack de CLAUDE §3 no se tocó.
6. **Consolidar proceso `gpio`** (M3): WR-1 + relés locales + reflejo SASMEX→sirena en UN
   proceso mínimo auditable (como FASE-0 y como sugiere la regla de oro 4), con `actuators`
   como adaptador BACnet aparte. Cierra esto antes de T-1.8/T-1.9.
7. **MFA de `occupant`** (M10): ¿se exceptúa al ocupante del MFA (compensando con quórum de 2 +
   rate-limit + geofence) o se exige MFA y se acepta la fricción en el enrolamiento por QR?
8. **Feed externo de eventos (CIRES/SSN) para la nube** (M7): sin él, el fail-open de un sitio
   sin enlace depende de que OTRAS estaciones de la red detecten el evento.
9. **Política de IA para Fase 3** (M13): decidir desde ahora que el clasificador jamás suprime
   disparos (solo degrada notificaciones `watch` o corre en shadow mode), o replantear la regla
   de oro 1 explícitamente llegado el momento.

### Propuestas que requieren tu aprobación sobre `CLAUDE.md` (no editado — fuera de mi autoridad)
- Línea 66 (regla de oro 9): "El waveform 200 Hz" → "El waveform crudo (100 sps)".
- Línea 71 (regla de oro 11): "(NOM-003-SCT)" → "(marco por confirmar — ver blueprint §9)".
- §1.3: "ventana de 2–5 s" → "ventana de asociación consciente de distancia (blueprint §4.5)".
- §4 estructura: refleja `takab-docs/archive/` y que el CI aún no existe (se crea en T-1.2).
- (Si apruebas #6) regla de oro 4: nombrar explícitamente el proceso `gpio` consolidado.

---

## 5. Secuencia edge-first y TASKS — veredicto y ajustes

**Veredicto: el orden es correcto y se conserva.** Edge (T-1.2→T-1.14) → Cloud (T-1.15→T-1.25)
→ Frontend (T-1.26→T-1.30), móvil diferido (T-1.31). El adelanto deliberado del GPIO SASMEX
(T-1.3/T-1.4) antes que SeedLink es ACERTADO (máximo valor de vida primero) y ahora está
anotado en blueprint §13 para que nadie lo "corrija" de vuelta al orden A1→A4.

Ajustes aplicados: T-1.16 desbloqueada de AWS (M8) — permite validar schema/RLS localmente en
cualquier momento tras T-1.1; contratos `shared/schemas` nacen en el edge (A8) — la nube consume
contratos ya validados, como manda §0.1; T-1.14 depende también de T-1.8 (el E2E ejercita el
motor de reglas); evidencia miniSEED con dueño claro (T-1.11 en línea, T-1.25 en backfill).

Sin cambios de numeración: ninguna tarea se movió de bloque; solo dependencias y criterios.

---

## 6. Verificación ejecutada

Entorno del análisis sin acceso a Docker (usuario fuera del grupo `docker`, sin sudo
no-interactivo), así que la verificación se hizo en dos niveles:

- **Nivel 1 — ejecutado aquí (PASS): PostgreSQL 18 + PostGIS 3.6 locales** (clúster efímero de
  usuario). Se aplicó `db/schema.sql` completo salvo las sentencias exclusivas de TimescaleDB
  (hypertables/compresión/retención/caggs, filtradas mecánicamente; `time_bucket` shimeado con
  `date_bin`): **aplica limpio** — la v1 fallaba en la política de `sites`. Encima corrió un
  **smoke test de 18 casos: 18 PASS / 0 FAIL** (guardado como `db/verify_rls_smoke.sh`, semilla
  de los tests de T-1.16): default-deny sin variables de sesión; tenant A ve/toca solo lo suyo;
  `gov_operator` lee únicamente `gov_shared`, UPDATE 0 filas e INSERT rechazado por RLS;
  `takab_superadmin` ve todo; `audit_log`/`dictamens`/`incident_actions` rechazan
  UPDATE/DELETE incluso a superusuario (triggers); borrar un incidente con timeline → RESTRICT;
  **FORCE** verificado con un owner no-superusuario (0 filas); `seismic_events` legible solo
  con `app.role` seteado.
- **La verificación misma cazó dos defectos que se corrigieron en caliente** (el valor de
  probar en real): (1) `app_gov_can_see()` necesitaba `SECURITY DEFINER` + `search_path` fijo —
  PostgreSQL valida privilegios sobre `tenants` al planear la política aunque el AND no se
  evalúe, lo que habría exigido GRANT de `tenants` a todo rol; (2) las funciones `LANGUAGE sql`
  validan su cuerpo al crearse → los helpers se movieron después de las tablas.
- **Nivel 2 — pendiente para T-1.16 (o cuando haya sudo): pasada completa con TimescaleDB.**
  Comando exacto:
  `sudo docker run -d --rm --name takab-schema-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=takab timescale/timescaledb-ha:pg16 && sleep 15 && sudo docker cp db/schema.sql takab-schema-test:/tmp/ && sudo docker exec takab-schema-test psql -U postgres -d takab -v ON_ERROR_STOP=1 -f /tmp/schema.sql`
  Además de la sintaxis, verificar que los jobs (compresión/refresh de caggs) conviven con RLS:
  por eso las 3 hypertables van con ENABLE **sin FORCE** (los jobs corren como owner; con FORCE
  verían 0 filas). Decisión documentada en el schema §8.
- **Greps de consistencia** sobre docs vigentes (excluyendo `archive/` y este análisis):
  `NOM-003` solo en contexto "errónea/por confirmar"; `200 Hz` 0 hits; `device_health_10s`
  0 hits; `visibility_of_tenant` 0 hits; T-MINUS/magnitud solo como prohibiciones. PASS
  (bitácora en la sesión).
- Diff sin secretos; `api/`, `web/`, `edge/` intactos (cero código de producción).

---

*Fuentes externas: [NOM-003-SCT/2008 (DOF)](https://www.gob.mx/cms/uploads/attachment/file/680141/NOM-003-SCT-2008.pdf) · [Especificaciones RS4D (Raspberry Shake)](https://manual.raspberryshake.org/specifications.html). Las especificaciones del WR-1 no son públicas — pregunta abierta #3.*
