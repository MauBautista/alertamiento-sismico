# TASKS.md — Backlog ejecutable TAKAB Ailert · Fase 1 (MVP Core)

> Cómo se usa este archivo con Claude Code:
> - Ejecutamos **una tarea a la vez, en orden** (respetando `depende de`).
> - Orden de bloques = **EDGE PRIMERO, luego CLOUD, luego FRONTEND** (`BLUEPRINT-TECNICO-TAKAB.md §0.1, §13`).
> - Por cada tarea: `/write-plan` → `/goal "<acceptance>"` → `/execute-plan` dentro de `/loop`
>   hasta que TODOS los criterios pasen. Ver método en `CLAUDE.md §6`.
> - Marca `[x]` la tarea solo cuando cumpla su **Definition of Done** (`CLAUDE.md §6`).
> - Si un criterio no pasa tras 3 iteraciones del loop: detente y reporta el bloqueo.
> - Cada tarea referencia su Work Package (WP) del blueprint entre corchetes, ej. `[A2]`.

**Estado actual:** ▶ **BLOQUE EDGE (A) COMPLETO** (T-1.2…T-1.14) + **T-1.16 COMPLETO**
(migraciones DB + RLS vs Postgres local, commit `4f20cab`). Todo lo restante (T-1.15,
T-1.17+) requiere AWS.

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
        **[ANALISIS-00] Verificado en git history: `.github/workflows/` no existe en ningún
        commit (tampoco `.env.example`, que el README referencia). Este criterio se TRASLADA a
        T-1.2, que crea el workflow COMPLETO (jobs api + web + edge), no solo el job edge.**
  - [x] `README.md` raíz explica `make dev` (levanta api + web + Postgres local con Docker).
  - [x] Documentos maestros (`CLAUDE.md`, `BLUEPRINT-TECNICO-TAKAB.md`, `RBAC-TAKAB.md`,
        `TASKS.md`, `USER-STORIES.md`) en `takab-docs/`. `db/schema.sql` presente.
- **Nota:** no rehacer esta tarea; construir encima (`CLAUDE.md §0.3`). El CI completo
  se crea en **T-1.2 [A0]** (ver criterio trasladado arriba).

---

## Bloque B · EDGE (Raspberry Pi 5) — se construye PRIMERO · Blueprint Fase A

### [x] T-1.2 · Scaffolding `edge/` + simuladores — **[A0]** · COMPLETA
- **Componente:** edge · **Depende de:** T-1.1 · **Prioridad: ALTA**
- **Objetivo:** `edge/` con `uv`, `pyproject.toml`, `supervisor.py`, estructura de módulos
  (`takab_edge/{seedlink,signal,buffer,gpio,rules,actuators,cloud,health,config,security,local_api}`)
  y **simuladores** de RS4D (feed SeedLink sintético 100 sps), WR-1 (toggle GPIO) y BACnet.
  [ANALISIS-00]: se quitó `quorum` del scaffold (el quórum vive en la NUBE, T-1.19 — ver
  blueprint §4.2) y se añadió `local_api` (lo exigen RBAC §4.2 y T-1.13).
  [PLAN-MAESTRO-01]: `sasmex` → `gpio` consolidado (entrada WR-1 + relés locales + reflejo
  SASMEX→sirena in-process) `[SUPUESTO #6 — confirmar/override; un override = renombrar el módulo]`.
- **Criterios de aceptación:**
  - [x] **Workflow de CI creado desde cero** (`.github/workflows/ci.yml`): jobs `api` + `web` +
        `edge` corren lint y tests en cada PR/push a main, en verde (criterio heredado de T-1.1).
        Los 3 jobs verificados localmente igual que correrán (api: ruff+pytest; web:
        eslint+prettier+vitest+build; edge: ruff+format+pytest con `GPIOZERO_PIN_FACTORY=mock`).
  - [x] `pytest` verde en CI (job `edge`) sin hardware físico (60 tests; gpiozero MockFactory).
  - [x] Simuladores permiten levantar el edge completo en dev sin Raspberry Shake ni Pi 5
        (verificado por el entry point real `uv run takab-edge`: 11 módulos arrancan en orden
        topológico, transmiten y paran limpio).

### [x] T-1.3 · `gpio` — WR-1 (contacto seco) → relés locales — **[A4]** · COMPLETA
- **Componente:** edge · **Depende de:** T-1.2 · **Prioridad: ALTA**
- **Criterios:** cierre del contacto → reflejo SASMEX→sirena **in-process** en <100 ms (medido);
  debounce 50 ms; botón silencio y botón prueba; fail-safe NO/NC configurable por canal;
  1000 ciclos sin fallo; proceso mínimo, sin deps pesadas, arranca <1 s.
  `[SUPUESTO #6 plan-maestro]` módulo consolidado (entrada + relés en un proceso).
  **A validar con hardware (gate #3):** semántica real de contactos del WR-1 (asignación
  alerta/prueba, duración, rebote, latching) — la aceptación final se re-corre con el receptor real.
- **Cerrada contra simuladores** (gate #3 pendiente de hardware): reflejo con latencia medida
  (software ≪ presupuesto); debounce 50 ms; **modelo de estado por demandas arbitradas bajo `RLock`**
  (reflejo/rules/self-test/silencio), corregido en 2 rondas de revisión adversarial; silencio que
  apaga el audible YA y **re-suena ante alarma nueva** (NFPA-72) sin tocar el estrobo; fail-safe
  NO/NC/fail-close con `drive_all_safe` durable; 1000 ciclos; proceso mínimo `takab-gpio` (<1 s, sin
  ObsPy/NumPy). 83 tests verdes. **Pendiente pre-despliegue:** exponer cierre/re-armado y semántica de
  re-alarma cuando lleguen T-1.12/T-1.13 y el hardware (gate #3).

### [x] T-1.4 · Ruta de hardware paralela SASMEX→sirena (SPOF-02) · RUNBOOK LISTO
- **Componente:** edge/hw · **Depende de:** T-1.3 · **Prioridad: ALTA**
- **Criterios:** con el Pi apagado, el contacto sigue disparando la sirena (relé de potencia en
  paralelo). Documentado en runbook.
- **Runbook:** `takab-docs/runbooks/RUNBOOK-SPOF-02-ruta-hardware-sirena.md` — diseño eléctrico
  (variante recomendada: fallback con watchdog por **latido de liveness del reflejo**, no del
  proceso), BOM, alimentación (SPOF-04), coexistencia con el silencio de T-1.3/SPOF-07, y
  procedimiento de verificación (Pi apagado / colgado total y **parcial** / recuperación con alerta
  **sostenida** / prueba CIRES con Pi muerto). Unidad `edge/systemd/takab-gpio.service`
  (Restart=always; sin secreto en el camino de vida). **Verificación física = gate #3** (WR-1 +
  relé + sirena reales). Revisión adversarial: 4 hallazgos HIGH corregidos, incluido un **fix de
  código en T-1.3** (`_on_start` siembra el reflejo si el contacto ya está asertado al arrancar, para
  no dejar la sirena muda en el traspaso HW→software de una alerta sostenida).

### [x] T-1.5 · `seedlink` — cliente SeedLink → bus local — **[A1]** · COMPLETA
- **Componente:** edge · **Depende de:** T-1.2
- **Criterios:** cliente SeedLink TCP 18000 al Shake; reconexión con backoff y medición de lag;
  cero pérdida al reiniciar el Shake; consume feed simulado 100 sps estable ([ANALISIS-00]: el
  RS4D muestrea a 100 sps, no 200 Hz). Objetivo de lag <1 s sostenido 24 h **contra el
  simulador**; contra hardware real, MEDIR primero — la latencia real de SeedLink del Shake es
  dependencia de proveedor (blueprint §15) y puede ser de varios segundos.
- **VALIDADO CONTRA HARDWARE REAL** (`AM.R4F74`, ringserver OSOP, accesible en la LAN):
  **lag mediano ~0.4 s** (min 0.28 / max 0.61) — cierra el gate #3 de latencia y confirma que el
  presupuesto instrumental **≤2 s es alcanzable**; el fallback UDP datacast **NO hace falta**
  (pregunta abierta #3 resuelta). **100 sps confirmado**; 4 canales EHZ/ENZ/ENN/ENE. Cliente real
  vía ObsPy (`SeedLinkConnection`) con reconexión backoff+jitter, dedup por `(canal,starttime)`,
  detección de gaps y **cero-pérdida por resume de número de secuencia** (validado: el ring
  reproduce el histórico por seqnum; el resume por *tiempo* NO funciona en este ringserver).
  Transporte abstracto → `FakeTransport` prueba la lógica sin hardware; el test de hardware se
  salta si el Shake no es alcanzable (CI). El transporte real se **cablea en el supervisor de
  producción** (`dev_mode=False`); el simulador RS4D queda para dev. 92 tests verdes.
  **Pendiente hardware-gated:** soak de 24 h y validación de reinicio físico del Shake; backfill
  FDSN/S3 para huecos largos = T-1.25.

### [x] T-1.6 · `signal` — features 1 s (PGA, PGV, RMS, STA/LTA) — **[A2]** · COMPLETA
- **Componente:** edge · **Depende de:** T-1.5
- **Criterios:** features + clipping/health_score validados contra ObsPy de referencia
  (error <1%) en traza sintética y real.
- **Implementación NumPy/SciPy** (módulo sin ObsPy, ligero): `classic_sta_lta` idéntico a
  `obspy.signal.trigger.classic_sta_lta` (**5e-13**), `integrate`/`differentiate` idénticos a
  `Trace.integrate/differentiate` (**err 0.0**); PGA de aceleración, PGV de velocidad (la no-nativa
  se deriva por integración/diferenciación según canal SEED H/N); STA/LTA con **contexto rodante**
  por canal; clipping + health_score. **Validado <1% vs ObsPy en traza sintética Y traza real del
  Shake** (`AM.R4F74`; test que se salta en CI). 103 tests verdes. Revisión adversarial: corregidos
  crash con paquete <2 muestras y crecimiento sin límite del contexto por misconfig de `lta_seconds`.
- **Pendiente (diferido):** calibración física absoluta = respuesta StationXML del RS4D
  (sensibilidades hoy placeholder); STA/LTA consciente de gaps y umbrales por edificio = T-1.8.

### [x] T-1.7 · `buffer` — ring miniSEED en NVMe — **[A3]** · COMPLETA
- **Componente:** edge · **Depende de:** T-1.5
- **Criterios:** ring buffer circular en NVMe con retención 7–14 días (~0.5–4 GB reales a
  100 sps × 4 canales según compresión — [PLAN-MAESTRO-01]: el "~10–16 GB" anterior arrastraba
  la aritmética de 200 Hz; el NVMe de 64 GB da holgura ≥15×; **medir tamaño real con hardware**);
  extrae la ventana miniSEED correcta de un evento confirmado para subir a S3.
- **Ring en disco** (`edge/takab_edge/buffer`): persiste el waveform crudo como **miniSEED** en
  archivos por día y canal (`<net>.<sta>.<loc>.<cha>.<YYYYMMDD>.mseed`); **poda circular** por
  antigüedad (retención, relativa al dato más reciente) y por tamaño (`max_bytes`); **extrae la
  ventana miniSEED** [start,end] de un evento (todos los canales, cruzando medianoche) para subir a
  S3 (T-1.11/T-1.25). Verificado con roundtrip ObsPy en `tmp` (7 tests). El tamaño real en GB =
  gate #3. Config `BufferConfig` (root vacío → dir temporal en dev/tests; en el Pi, la ruta NVMe).

### [x] T-1.8 · `rules` — motor determinista tierizado — **[A5]** · COMPLETA
- **Componente:** edge · **Depende de:** T-1.3, T-1.6
- **Criterios:** tabla de verdad completa de los 5 tiers (`normal`/`watch`/`restricted`/
  `evacuate_or_hold`/`manual_only`); umbrales configurables por edificio (PGA/PGV, banda cautela
  y disparo); latencia cruce-de-umbral→decisión <200 ms (presupuestos por camino: blueprint
  §4.3); cada transición de tier queda registrada (contrato de `rule_evaluations`, P5); config
  por archivo firmado; tests exhaustivos de casos borde (clipping, saturación, dropout, doble
  disparo — SASMEX activo + umbral local del mismo sismo = UN evento, no dos).
- **Motor** (`edge/takab_edge/rules`): tabla **multi-canal** `decide()` con corroboración (≥2
  canales confiables en disparo → evacuate; 1 → restricted; ≥1 cautela → watch; ninguno → normal;
  todos muertos → manual_only). **Saturación (clipping) cuenta como DISPARO** (fail-loud: nunca
  de-escala; sólo `health<0.5` = dropout/muerto se excluye). `RuleEngine` acumula features por
  canal, **poda stale** (dropout), **dedup de episodio** por **reloj único de recepción** (SASMEX+
  umbral del mismo sismo comparten `event_id`), mide **latencia** y **loguea por transición**. La
  **escalación** WATCH→EVACUATE sale del edge (dedup del CloudConnector por `(event_id, tier)`).
- **Revisión adversarial:** 4 hallazgos corregidos (1 CRÍTICO fail-silent: la saturación de-escalaba
  el tier). **Requisito para T-1.17 (nube):** el ingest debe hacer **upsert al tier mayor** por
  `event_id` (no `ON CONFLICT DO NOTHING`), para que la escalación no se congele en el tier bajo.

### [x] T-1.9 · `actuators` — interfaz `Actuator` + driver relés + adaptador BACnet/IP — **[A6]** · COMPLETA
- **Componente:** edge · **Depende de:** T-1.8
- **Criterios:** interfaz `Actuator` única que consume `rules`; **driver primario = relés
  fail-safe del módulo `gpio`** `[SUPUESTO #4 plan-maestro — confirmar/override]`; adaptador
  BACnet/IP detrás de la misma interfaz para la secuencia extendida (cierre de válvulas de gas +
  retorno de ascensores/montacargas + liberación de retenedores de puerta), activable por
  contrato; cada acción con ACK de ejecución y timestamp (`T+0.42s`, etc.); mock de simulación
  sin hardware BACnet real. Un override del supuesto solo cambia qué driver es el primario.
- **Manager** (`edge/takab_edge/actuators`): enruta por contrato (`bacnet_channels`) — relé por
  defecto [SUPUESTO #4], BACnet para la secuencia extendida; **sirena/estrobo SIEMPRE por relé
  local** (vida audible, nunca pasarela de terceros). ACK con `T+X.XXs` relativo al `issued_at`.
  **Aislamiento de fallo:** un driver que lanza NO aborta la secuencia (ACK fallido + continuar,
  best-effort); ACKs en ventana rodante; el supervisor observa los ACKs y avisa en fallo de vida.
  Revisión adversarial lean: 3 hallazgos corregidos. Driver BACnet real (bacpypes3/BAC0) = gate
  hardware; escalación a nube del fallo de actuación = T-1.11.

### [x] T-1.10 · `health` — autodiagnóstico del gabinete — **[A7]** · COMPLETA
- **Componente:** edge · **Depende de:** T-1.2
- **Criterios:** snapshots correctos de NTP offset, lag SeedLink, packet loss, estado UPS
  (`RED ELÉCTRICA %`, `RESPALDO Xh Ym`, `EN BATERÍA`), temperatura y estado de actuadores;
  logging por transición de estado + heartbeat periódico (nunca por intervalo continuo).
- **Monitor** (`edge/takab_edge/health`): compone `HealthSnapshot` desde `HealthProbes`
  inyectables (temp del Pi vía `/sys/class/thermal` con fallback; NTP/UPS/cert = gate hardware,
  default seguro) + lag/packet-loss del `SeedLinkClient` + relés de `gpio`. **Logging por
  transición DISCRETA** (relés/UPS/umbrales de cert/temp/lag — nunca por drift continuo) +
  **heartbeat** periódico (`health_heartbeat_s`) en hilo daemon. Etiquetas UPS de UI. El
  cableado health→nube (publicar snapshots) y el parsing real del cert mTLS son **T-1.11**.

### [x] T-1.11 · `cloud` (edge-side) — MQTT mTLS + cola offline — **[A8]** · edge-side COMPLETA (runtime AWS = gate T-1.15)
- **Componente:** edge · **Depende de:** T-1.6, T-1.9, T-1.10
- **Edge-side** (`edge/takab_edge/cloud`): **cola durable en disco** (`DurableSpool`, un JSON por
  mensaje con `fsync` de archivo+dir → sobrevive corte de energía; cuarentena de archivos
  corruptos, no descarte silencioso) + **dedup por identidad lógica** (`tier`/`channel+action`/
  `sha256` → escalaciones y ACKs/evidencias distintos del mismo evento SÍ salen; cero pérdida/dup) +
  **transporte MQTT abstracto** (`MqttTransport`; `FakeMqttTransport` en tests, `AwsIotMqttTransport`
  mTLS/QoS1/last-will = gate AWS) + **reconexión backoff+jitter** en hilo. `publish()` es total:
  NUNCA lanza/bloquea la actuación (regla de oro 4.2) aun con disco lleno.
- **Contratos versionados** (`shared/schemas/*.schema.json`, [ANALISIS-00]): generados de los
  modelos Pydantic (`takab_edge.schemas`), con test anti-drift. **Evidencia** (`takab_edge.evidence`):
  ventana miniSEED→S3 idempotente por `sha256` (uploader real S3 = gate AWS; fake en tests).
- **Revisión adversarial:** 7 hallazgos corregidos (dedup que perdía ACKs/evidencia; `publish` que
  podía lanzar a la vía de actuación y envenenar el dedup; falta de `fsync`/durabilidad; cobertura).
- **Gate AWS (T-1.15):** conexión real a IoT Core, S3, provisioning mTLS. **Requisito T-1.17:** upsert
  al tier mayor por `event_id`. Cableado health/ACK→cloud en el supervisor = trivial al tener transporte.
- **Criterios:** mTLS contra AWS IoT Core (QoS 1); cola durable offline con backfill idempotente
  al reconectar; desconectar WAN 2 h → reconectar con backoff+jitter: cero pérdida, cero
  duplicado (verificado por PK/`event_id`); last-will configurado.
  **[ANALISIS-00] Contratos primero (blueprint §0.1 "la nube se construye sobre contratos ya
  validados en el edge" — ninguna tarea los producía):** los payloads de features/eventos/
  health/ACK se publican conforme a **JSON Schema versionados en `shared/schemas/`**, generados
  de los modelos Pydantic del edge; los simuladores validan contra ellos. En evento confirmado,
  la ventana miniSEED extraída por `buffer` (T-1.7) se sube a S3 (URL pre-firmada solicitada
  por MQTT/API) y se registra en `evidence_objects` con `sha256` — idempotente.

### [x] T-1.12 · `config` + `security` — sync firmada y comandos firmados — **[A9]** · edge-side COMPLETA (mTLS provisioning = gate T-1.15)
- **Componente:** edge · **Depende de:** T-1.11
- **Criterios:** store local de umbrales/reglas/tenant; sincronización desde la nube vía JWT
  firmado (≤60 s), versionada y reversible; mTLS/X.509 por gateway; verificación de comandos
  remotos firmados con nonce (anti-replay); rechaza comando no firmado o repetido.
- **security** (`edge/takab_edge/security`): comandos firmados HMAC con **nonce de un solo uso**
  (anti-replay, store podado por expiración) + **ventana temporal corta** (regla de oro 8; rechaza
  no firmado/expirado/futuro>skew) + firma canónica **length-prefixed** (dominios command/config
  separados, sin aliasing) + robustez (firma malformada → False, no excepción).
- **config** (`edge/takab_edge/config/store.py`): `apply_signed_update` **fail-closed** (sin
  verificador → rechaza), firma que **cubre la versión** (anti-relabeleo), piso **`high_water`**
  monótono (ni el rollback lo baja → una versión ya vista no se re-aplica), historial reversible.
- **Revisión adversarial:** 8 hallazgos corregidos (versión no firmada = downgrade/DoS; rollback
  reabría replay; fail-open). mTLS/X.509 provisioning + transporte de la sync = gate AWS (T-1.15).

### [x] T-1.13 · `takab_local_api` — dashboard local del edificio · COMPLETA
- **Componente:** edge · **Depende de:** T-1.8
- **Criterios:** accesible en LAN sin internet; muestra estado, último evento, prueba de sirena;
  recibe comando de silencio por LAN.
- **Servidor** (`edge/takab_edge/local_api`): HTTP mínimo con stdlib `http.server` (sin deps
  pesadas), en hilo daemon, bind LAN (`local_api_host/port`). `GET /` sirve un dashboard HTML con
  estados loading/error/**stale** (regla de oro 7) y el banner MVP "ALERTA SÍSMICA · PROTÉJASE";
  `GET /api/status`; `POST /api/silence` · `/api/siren-test` · `/api/reset`. Verificado con HTTP
  real por loopback (puerto efímero). Acceso controlado por segmentación de red (LAN física); un
  PIN/token local queda como mejora futura.

### [x] T-1.14 · Simulador de sismo + integración edge end-to-end — **[A10]** · COMPLETA · cierra Fase E
- **Componente:** tooling/edge · **Depende de:** T-1.5, T-1.8, T-1.9 · **Prioridad: ALTA**
- **Criterios:** inyector SeedLink + generador de eventos permite demo E2E y tests de carga sin
  sismo real; evento simulado → actuación autónoma completa sin nube (**test con la nube
  apagada** — cierra el hito de la Fase E, ver PLAN-MAESTRO §4). Hardware-in-the-loop:
  opcional y hardware-gated (#3), no bloquea el cierre contra simuladores.
- **Generador de sismo** (`edge/simulators/quake.py`): secuencia multi-canal ruido→P→S que corrobora
  disparo en ≥2 ejes. **E2E** (`edge/tests/test_e2e.py`, nube APAGADA): sismo instrumental →
  `evacuate_or_hold` + secuencia completa (sirena+estrobo+gas+ascensor+puerta) sin nube; reflejo
  SASMEX inmediato; latencia <200 ms; **cero explosión de duplicados** (episodio); ventana miniSEED
  extraíble para evidencia; carga de 300 paquetes de ruido sin alerta espuria. Hardware-in-the-loop
  = gate #3.

---

## Bloque C · CLOUD (AWS) — después del edge · Blueprint Fase B

### [x] T-1.15 · Infra base AWS con Terraform + IoT Core — **[B1]** ✅ (commit `55ca197`)
- **Componente:** infra · **Depende de:** T-1.1
- **Criterios:** `terraform apply` crea VPC mínima, ~~RDS PostgreSQL~~ la base Postgres
  (TimescaleDB/PostGIS habilitados), bucket S3 (miniSEED/evidencias), cola SQS, User Pool de
  Cognito, KMS por tenant, repos ECR, y un Thing de AWS IoT Core de prueba + policy mínima +
  regla IoT → SQS. Sin credenciales en el código; backend de estado remoto (S3 + DynamoDB lock);
  `terraform destroy` limpio.
  ([DECISION 2026-07-06]: **RDS no soporta la extensión `timescaledb`** — verificado contra la
  lista oficial de extensiones de RDS; y el schema exige compresión + caggs. La DB corre en
  **EC2 t4g.small con `timescale/timescaledb-ha:pg16`** (idéntico al docker-compose local),
  EBS cifrado, backups DLM + pg_dump→S3, acceso solo por SSM. "KMS por tenant" = CMK base +
  mapa `tenant_keys` reservado (KEK por tenant llega con el primer campo sensible — blueprint
  §8). Lock: tabla DynamoDB creada + `use_lockfile` nativo de S3. Entregado además: 3 colas
  standard+DLQ (events/telemetry/backfill), fleet policy IoT por thing-name, 5 reglas IoT→SQS
  con enriquecimiento `meta_principal/meta_topic/meta_ts_iot` (el prefijo `_` lo rechaza el
  parser SQL de IoT), flota `gw-dev-0001` + 4 sim con cert X.509 + HMAC por gateway en Secrets
  Manager, rol OIDC CI plan-only, presupuesto $50 con alarma, `verify_infra.sh` 20/20 PASS y
  ciclo destroy/re-apply probado.)

### [x] T-1.16 · Esquema de base de datos + migraciones — **[B3]** ✅ (commit `4f20cab`)
- **Componente:** api / db · **Depende de:** T-1.1
  ([ANALISIS-00]: antes dependía de T-1.15/Terraform — innecesario: las migraciones y los tests
  de RLS corren contra el Postgres LOCAL del `docker-compose.yml`; no provisionar AWS para esto.
  T-1.17 sí exige T-1.15 + T-1.16.)
- **Prerequisito de entorno:** Docker Desktop (Postgres+TimescaleDB+PostGIS vía
  `docker-compose.yml`) y Python 3.12 vía `uv`.
- **Criterios:** migración Alembic inicial reproduce `db/schema.sql` (extensiones, tablas,
  hypertables, índices, **RLS default-deny + FORCE en todas las tablas de negocio**, triggers
  append-only, continuous aggregates 1m/1h, función `gov_ack_incident` — ver schema §8); test de
  aislamiento cruzado de tenants (tenant A no ve filas de tenant B) **incluyendo conexión como
  owner de las tablas (FORCE)**; test de visibilidad `gov_operator` (`gov_shared` sí, `private`
  no, y NO puede escribir); test de que UPDATE/DELETE sobre `audit_log`/`dictamens`/
  `incident_actions`/`evidence_objects` falla; test de idempotencia de doble insert por PK;
  verificar en TimescaleDB real que los jobs (compresión/retención/refresh de caggs) conviven
  con RLS en las hypertables (van SIN FORCE por diseño — ver nota `[ANALISIS-00]` del schema §8).

### [x] T-1.17 · Pipeline de ingesta: IoT Rule → SQS → Timescale — **[B2]** ✅ (commit `f951403`)
- **Componente:** cloud · **Depende de:** T-1.15, T-1.16, T-1.11
- **Criterios:** 20 sitios × 4 canales × 1 msg/s sostenido sin lag de cola; idempotente por PK;
  features 1s → `waveform_features_1s`, eventos confirmados → `incidents` + S3, health →
  `device_health`; los consumidores **validan cada payload contra los JSON Schema de
  `shared/schemas/`** publicados por el edge (T-1.11) y rechazan a DLQ lo que no cumpla.
  ([DECISION 2026-07-06]: la parte "+ S3" de eventos confirmados (evidencia miniSEED) la
  entrega **T-1.25** por sus propios criterios; T-1.17 deja el handler del puntero
  `evidence_objects` fuera de alcance. Enriquecimiento de las IoT Rules = claves `meta_*`
  (el parser SQL de IoT rechaza `_`); la ingesta las descarta antes de validar. Workers
  **co-locados** en el EC2 de la DB (default dev, plan §C.1) — imagen única
  `api/Dockerfile`. Upsert al tier mayor por `event_uuid` verificado E2E real (sismo mTLS
  watch→critical = 1 incidente). Evidencia G1 en
  `takab-docs/runbooks/RUNBOOK-load-test-ingesta.md`: 48,000/48,000 features @ 80.2 msg/s
  × 600 s, colas ≈0, DLQs 0; suplantación → DLQ `unknown principal`.)

### [x] T-1.18 · Autenticación y tenancy (Cognito + JWT + RLS) — **[B8]** ✅ (commit `30cb4f2`)
- **Componente:** api / auth · **Depende de:** T-1.15, T-1.16
- **Objetivo:** login OIDC contra Cognito con MFA; el backend extrae claims y setea
  `app.tenant_id`, `app.role`, `app.user_id` por request para RLS (`RBAC-TAKAB.md §5`).
- **Criterios:** grupos de Cognito = los 10 roles de `RBAC-TAKAB.md §1` (las identidades
  máquina van aparte: X.509/M2M); MFA por grupo según supuesto #7 del PLAN-MAESTRO
  (occupant sin MFA, todo rol web con MFA); claims custom (`tenant_id`, `role`,
  `site_scope`, `zone_id`, `surface`) en el JWT; dependencia FastAPI valida firma/exp/issuer y
  rechaza tokens inválidos (401); middleware setea variables de sesión Postgres en la
  transacción; endpoint `/me`; tests de autorización por rol (`RBAC-TAKAB.md §2`).
  ([DECISION 2026-07-06]: el "middleware" es una **dependencia FastAPI** `get_tenant_conn`
  que fija los GUCs con `set_config(...,true)` DENTRO de la transacción (más limpio que
  middleware HTTP; probado no-bleed en requests async concurrentes). MFA por grupo NO es
  expresable en Cognito → pool `ON` solo-TOTP en Fase 1; `occupant` (sin MFA) se resuelve
  en T-1.31 con **pool separado**. Gate #7 ratificado. Se valida el **ID token**
  (`token_use=='id'`; Cognito solo inyecta `custom:*` ahí). Hallazgo de seguridad corregido
  [regla de oro 5]: `custom:tenant_id` era auto-escribible → `write_attributes=['name']` en
  el app client (aplicado al pool real). Verificado E2E vivo contra `us-east-2_WlAWpxvnn`
  (10 grupos, MFA+TOTP, PKCE, `/me` por rol, 401/403 correctos); suite api 228 passed.)

### [x] T-1.19 · Incident engine + quórum de red — **[B4]** ✅ (commit `9ce2297`)
- **Componente:** cloud · **Depende de:** T-1.17
- **Criterios:** correlación y deduplicación de eventos; corroboración de quórum colaborativo
  (≥3 nodos, **ventana de asociación consciente de distancia**: |Δt_ij| ≤ dist_ij/v_P + margen,
  v_P=6.5 km/s, margen 3 s, tope 30 s — [ANALISIS-00]: la ventana fija de 2–5 s era físicamente
  inalcanzable entre sitios a 90–110 km, ver blueprint §4.5) sin bloquear la actuación local ya
  ejecutada por el edge; test con tiempos de arribo realistas inter-ciudad; ciclo de vida
  completo del incidente (abierto → acusado → cerrado).
  ([DECISION 2026-07-07]: worker `python -m takab_api.incident` (LISTEN takab_live + poll 5s,
  BYPASSRLS). Escritura como takab_ingest; el engine LEE la base `waveform_features_1s` (lector
  de red cross-tenant, no la superficie de API — allowlisted en el contract-test). La revisión
  adversarial cazó un bug CRÍTICO: una detección espuria/aislada temprana enmascaraba el quórum
  de un sismo real (corregido: retirar-ancla-y-reintentar). Soft-gate #2: params (6.5/3/30)
  asocian ≥3 estaciones en 5/5 sismos SSN reales vs 0/5 con ventana fija 5s — confirma
  [ANALISIS-00]; epicentros del catálogo aproximados de memoria, verificar vs SSN oficial antes
  de calibración de producción. `in_review`/`closed` los gestiona el engine; el ack ya es de
  T-1.18. Verificado E2E vivo: worker correlaciona sismo de 4 estaciones → 1 seismic_event + 4
  votos + 4 incidentes linkeados (110km asocia a ~17s). Suite api 404 passed.)

### [x] T-1.20 · Dictamen service (inmutable) + PDF — **[B5]** ✅ (commit `5a7cad5`)
- **Componente:** cloud · **Depende de:** T-1.19
- **Criterios:** dictamen automático preliminar (`NO HABITAR · INSPECCIÓN` /
  `HABITAR · MONITOREO` / `OPERACIÓN NORMAL`) según severidad/PGA + regla de nodos; registro
  **inmutable y versionado** (`ruleSetVersion`, evidencia, notas, `signedBy`; corrección = fila
  nueva con `supersedes_dictamen_id`), nunca podado por retención ([ANALISIS-00]: la etiqueta
  "NOM-003" era una cita normativa errónea — blueprint §9); exportación PDF + miniSEED por
  incidente.
  ([DECISION 2026-07-07]: pasada en el MISMO worker `python -m takab_api.incident`, tras la
  correlación y con settle 60 s (> tope de ventana del quórum) para dictaminar ya corroborado;
  quórum aún más tardío ⇒ corrección versionada (fila nueva `supersedes`). Regla de nodos solo
  ELEVA (`normal_operation`→`inhabit_monitor`), jamás degrada; cabeza FIRMADA jamás se corrige
  sola. Umbrales PGA 0.25g/0.05g = placeholders CALIBRABLES por ingeniería (override
  `rule_sets.config.dictamen`, degradación grácil por campo). PDF con fpdf2 vía
  `POST /incidents/{id}/report` (export MENOS gov_operator: generar = INSERT de evidencia con
  tenant_id ajeno que su RLS rechaza); evidence_objects `report_pdf` + sha256 + audit +
  presigned 300 s; miniSEED ya expuesto por T-1.22. dictamen/service.py allowlisted como lector
  de red de la base `waveform_features_1s` (mismo estatus que el engine). Suite api 435 passed;
  smoke vivo del worker OK.)

### [x] T-1.21 · Notification orchestrator (cascada + fail-open) — **[B6]** ✅ (commit `d8b0636`)
- **Componente:** cloud · **Depende de:** T-1.19
- **Criterios:** cascada secuencial API Webhook (HMAC) → WhatsApp Business → SMS (≤30 s) →
  correo (DKIM/SPF); en degradado (edge `SIN ENLACE`) dispara todos los canales en paralelo
  (fail-open); alerta crítica → email <10 s.
  ([DECISION 2026-07-07]: worker propio `python -m takab_api.notify` (LISTEN takab_live +
  takab_failopen). Migración **0005_notification_jobs** (UNIQUE incident/channel/mode =
  enqueue idempotente; RLS espejo de incidents solo-lectura de tenant; target sin secretos —
  el HMAC del webhook se re-resuelve del rule_set al despachar). Cascada escalonada step 10 s
  (SMS a t0+20 ≤30 s); éxito ⇒ resto `skipped`; fallo ⇒ ADELANTA el siguiente en el mismo
  pass. **Crítico ⇒ email `parallel` inmediato deadline <10 s** (interpretación ratificada:
  secuencial puro haría el SLA imposible tras timeouts). Fail-open `trigger='quorum'` ⇒ todos
  los canales en paralelo. Destinos en `rule_sets.config.notifications`. Providers: webhook
  httpx + HMAC `X-Takab-Signature`; email **SES sandbox real** vía `NOTIFY_EMAIL_FROM`
  (DKIM/SPF = TODO de dominio real); WhatsApp/SMS **simulados** (ratificado). Evidencia SLA en
  `incident_actions kind='notify_sent'` payload {latency_s, deadline_met}, actor
  `system:notify:<canal>:<modo>`. Suite api 474 passed; smoke vivo del worker OK.)

### [x] T-1.22 · API REST + WebSocket nativo — **[B7]** ✅ (commit `4c35b16`)
- **Componente:** api · **Depende de:** T-1.18
- **Criterios:** REST (FastAPI + Pydantic) para sites/sensors/incidents/telemetry/dictámenes/
  exportación miniSEED; OpenAPI generado; p95 <200 ms en queries de dashboard con 90 días de
  datos; **WebSocket nativo** para incidentes y estado de sitio en vivo (update visible en el
  navegador <2 s desde el edge). `[SUPUESTO #5 plan-maestro — confirmar/override]`: GraphQL
  subscriptions queda pos-MVP; los endpoints de telemetría JAMÁS exponen los caggs
  `site_metrics_*` sin JOIN a `sites` (RLS — ver schema §6).
  ([DECISION 2026-07-06]: **Gate #5 ratificado — REST + WS nativo, SIN GraphQL** (retitulada).
  WS fan-out = LISTEN/NOTIFY fetch-on-notify (migración `0004_live_notify`): el hub re-consulta
  la fila con los GUCs del SUSCRIPTOR → RLS es la autoridad de tenancy; los writers de
  T-1.17/T-1.19 no requieren código. Reglas duras con contract-tests (vista `_secure` y JOIN
  sites) verificadas. sdk-ts vía `@hey-api/openapi-ts` con drift-gate en CI. Verificado E2E
  vivo: incidente commit→frame **214 ms** (<2 s), occupant rechazado por authz WS, tenant
  ajeno aislado. Revisión adversarial: 6 hallazgos WS corregidos. Suite api 330 passed. El
  frontend que consume esto es T-1.26→T-1.30.)

### [x] T-1.23 · Config sync + command service firmado — **[B9]** ✅ (commit `a3dd53c`)
- **Componente:** cloud · **Depende de:** T-1.18
- **Criterios:** publica umbrales/reglas firmados (JWT, ≤60 s) a los edges; comandos remotos de
  actuador firmados con MFA + nonce + rate-limit + ACK de ejecución obligatorio (contraparte
  cloud de **T-1.12**).
  ([DECISION 2026-07-07]: **HMAC, no JWT** — el edge (T-1.12) pinea HMAC y RBAC §4.3 acepta
  "HMAC/JWT corto". Paridad byte-idéntica por **vectores compartidos**
  (`shared/schemas/tests/hmac_vectors.json`, generados con el SecurityManager REAL del edge)
  consumidos por las suites de AMBOS lados. Contratos `command`/`command_ack`/`config_update`
  en shared/schemas. Migración **0006** (commands nonce-UNIQUE + gateway_config_state versión
  monótona + trigger NOTIFY rule_set). `POST /sites/{id}/commands`: roles = acción
  `siren_test` de la matriz (proxy Fase 1 de actuador; pánico occupant = T-1.31), MFA por pool
  (gate #7), rate-limit usuario+sitio y sitio, fail-closed sin clave; ack por `takab/acks` con
  discriminador `kind` (transición solo desde pending; sin ack ⇒ expired por TTL = ack
  obligatorio). Config sync `python -m takab_api.commands`: LISTEN rule_set + poll 30 s ⇒
  ≤60 s; payload = `rule_sets.config.edge` (EdgeSettings). Edge: `subscribe()` en
  MqttTransport + CommandDispatcher (firma/replay/ventana ANTES de tocar nada;
  `command_enabled=false` default de fábrica ⇒ ack rejected; no-autenticado sin ack). Claves
  por env/Secrets Manager; per-gateway prod = TODO. Suites api 518 / edge 223 passed.)

### [x] T-1.24 · Audit/compliance inmutable + billing/metering — **[B10]** ✅ (commit `ab398a4`)
- **Componente:** cloud · **Depende de:** T-1.16
- **Criterios:** `audit_log` inmutable sin poda por retención; medidores por tenant (sitios
  activos, mensajes, GB, incidentes) para facturación.
  ([DECISION 2026-07-07]: `takab_api.audit` = ÚNICO escritor de audit_log (front sync psycopg
  + async SQLAlchemy); contract-test single-writer lo veta en CI (cazó 3 escritores inline no
  contemplados: lifecycle, rule_sets publish, incidents_ack). Contract-test de compliance §9:
  por tabla (audit_log/incident_actions/dictamens/evidence_objects/life_checkins) no-hypertable
  + sin job retention/compression + trigger append-only presente. Migración **0007**:
  `billing_meters_daily` (PK tenant+día, tenant solo-lectura, escribe takab_ingest). Pasada
  `python -m takab_api.billing [--day]` (one-shot, default ayer UTC): active_sites = sitios con
  telemetría; messages = features + device_health + incident_actions; gb_approx = messages ×
  bytes/fila estimados (APROX row-count×avg, calibrar con pg_column_size); incidents = abiertos
  del día. UPSERT idempotente (re-run tras backfill tardío actualiza). Scheduling dev =
  cron/`make billing`; AWS = EventBridge→ECS TODO prod. El config sync ahora audita
  `config_published`. Suite api 559 passed.)

### [x] T-1.25 · Backfill por S3 (anti-thundering-herd) ✅ (commit `241b64f`)
- **Componente:** edge+cloud · **Depende de:** T-1.11, T-1.17
- **Criterios:** cola de 6 h se ingiere completa e idempotente vía S3 + URL pre-firmada;
  regla FASE-0 capa 4: cola offline >15 min de datos → ruta S3, <15 min → MQTT por lotes;
  cubre también la subida de evidencia miniSEED de eventos ocurridos durante la desconexión.
  ([DECISION 2026-07-07]: flujo request→grant→PUT — el edge pide por
  `takab/backfill/request/<thing>` (contrato `backfill_request` generado anti-drift), el grant
  service verifica principal==thing y responde presigned PUT con **key canónica de la NUBE**
  (`backfill/{thing}/{from}_{to}.ndjson.gz` transfer; `evidence/{tenant}/{event_uuid}/{sha}.mseed`
  evidence — **v1.1.0**: supersede `evidence/{event_id}/…` de T-1.11). Worker
  `python -m takab_api.backfill`: NDJSON del spool por `ingest.handlers` VERBATIM (RETRY
  intra-objeto para dependencias fuera de orden); evidencia verificada por sha256 REAL y
  linkeada por `event_uuid`. Anti-thundering-herd: jitter 0–120 s + 1 objeto/gateway + fallback
  a MQTT si grant/PUT fallan (cooldown; nada se atora; solape inocuo por dedup PK). Evidencia
  offline: pendientes durables (tier evacuate/restricted, ventana −60 s/+120 s) suben al
  reconectar. Infra: IoT rule request→q-backfill + notificación bucket evidence (validate OK;
  **gate AWS CERRADO 2026-07-08**: apply dirigido de regla+policy+notificación y smoke E2E
  real gw-sim-0001 — request MQTT mTLS→grant→presigned PUT 200→objeto `SSE aws:kms` con la
  llave del proyecto→ingesta 3/3 filas idempotentes en la DB cloud, DLQ 0. El pin
  `ignore_changes=[ami]` en modules/database evita que el drift de AMI proponga replace
  del EC2 de la DB). Criterio 6 h
  verificado literal: 86 400 features completas e idempotentes (~57 s; gate
  `TAKAB_SLOW_TESTS=1`). Suites api 535 / edge 233 passed; frontera 14:59/15:01 testeada.)

---

## Bloque D · FRONTEND — sobre la nube existente · Blueprint Fase C

> **Bloque D COMPLETO (2026-07-08)**: T-1.26 → T-1.30 en verde. Las 5 rutas del SOC
> (`/console`, `/fleet`, `/triage`, `/tenants`, `/building`) montan páginas reales; no queda
> ningún placeholder. T-1.31 (móvil) sigue diferida fuera de Fase 1.

### [x] T-1.26 · Guards de routing + shell de navegación ✅ (commits `a802e71` + `8c0ace5` + `2f9631b`)
- **Componente:** web · **Depende de:** T-1.18
- **Objetivo:** separar el diseño en rutas protegidas por rol (`RBAC-TAKAB.md §7`).
- **Criterios:** rutas `/console`, `/fleet`, `/triage`, `/tenants`, `/building/:siteId` montadas;
  guard por rol bloquea navegación directa por URL (no solo oculta el botón); navegación armada
  según el rol del JWT; estado "sin acceso" implementado; login/logout Cognito end-to-end.
  ([DECISION 2026-07-07]: guards y nav **100% server-driven** por `allowed_routes` de `/me`
  (`matrix.py` autoritativo; clave paramétrica = `/building`) — cero matriz de roles en el
  front. react-router v7 library mode; sesión zustand + oidc-client-ts (code+PKCE, silent
  renew, sessionStorage) con bypass local `POST /dev/token`; logout Cognito = redirect manual
  al `/logout` del Hosted UI (el pool no publica end_session_endpoint). Denegación IN-PLACE
  ("SIN ACCESO" con URL intacta); `allowed_routes: []` (roles móviles) ⇒ pantalla sin
  superficie web. Contrato: `MeResponse` tipado end-to-end (response_model + regen sdk-ts;
  se corrigió drift de openapi.json arrastrado desde T-1.22 — commands+report no publicados);
  `@hey-api/client-fetch` fijado en ^0.10.2 (0.11+ re-indexa TData[keyof TData] y rompe el
  tipado con openapi-ts 0.64). Dev: proxy Vite `/api`→:8000 (la API no monta CORS). Suites:
  web 96 passed (incluye matriz 10 roles × 5 URLs de bloqueo por URL directa), api 562 passed,
  E2E local dev-token→/me→guards verificado contra la API real. **Gate AWS CERRADO
  2026-07-08**: smoke del Hosted UI real en verde end-to-end — usuario dev `tenant_admin`
  (credenciales+TOTP SOLO en Secrets Manager `takab/dev/console/dev-tenant-admin`),
  enrolamiento TOTP vía `/mfa/register` Y re-login vía `/mfa`, callback code+PKCE, ID token
  aceptado por `/me` real (allowed_routes correctas), silent renew `prompt=none`, logout mata
  la sesión. Quirk documentado: tras logout Cognito clásico redirige a `/login` en vez de
  `error=login_required` (oidc-client-ts verá timeout de signinSilent ⇒ ruta a login, ya
  contemplada). **[DECISION 2026-07-08 — RATIFICADA]** Topología CORS prod: MISMO
  ORIGEN tras CloudFront (S3 estático + behavior `/api/*`→API y `/ws` WebSocket al mismo
  dominio); la API sigue SIN CORSMiddleware. Razones: el front ya llama rutas relativas
  `/api` (paridad dev/prod con el proxy Vite), cero preflights de latencia, superficie mínima
  (regla de oro: no abrir orígenes), WS same-origin y un solo dominio en los callbacks de
  Cognito. CORSMiddleware queda como plan B solo si el hosting separa dominios.)

### [x] T-1.27 · Consola C4I — Live Wall — **[C1]** ✅ (commits `bf69067` base + `9e0de5d` ws.ts + `23d0533` consola + `877234e` fix pulso)
- **Componente:** web · **Depende de:** T-1.26, T-1.22
- **Criterios:** réplica fiel del mockup 1 (mapa MapLibre con intensidad MMI, incidentes abiertos
  en vivo vía suscripción — GraphQL o WS según decisión #5 del ANALISIS, detalle de sitio con
  sismograma live y PGA/PGV/NTP offset/clipping/packet loss, actuadores con ACKs); verificación
  CCTV ONVIF **opcional — NO bloquea la tarea** ([ANALISIS-00]: el blueprint §4.1 marca CCTV
  como opcional; exigirla aquí contradecía eso); carga 10 min de features <1 s; pop-up
  automático al detectar anomalía (STA/LTA > 3.5 sostenido 2 s); banner MVP "ALERTA SÍSMICA ·
  PROTÉJASE" (sin magnitud ni T-MINUS); estados loading/error/empty/stale en todo componente.
  ([DECISION 2026-07-08 · gate #5 = WS nativo] `lib/ws.ts` LiveSocket (auth-first→ready→subscribe,
  backoff 1–30 s + re-subscribe, 4401⇒logout, staleness por topic) sobre el `/ws` de T-1.22 con
  los shapes tipados del SDK (cero shapes inventados). `features/console/`: hooks
  (useLiveIncidents REST+upsert idempotente, useMapState fetch-on-notify throttled, useSiteFeatures
  backfill 10 min + rolling 600 s, useSiteSoh, useIncidentActions, useAutoPopup con latch) +
  paneles (MapPanel MapLibre real OpenFreeMap dark con bandas MMI + pulso rAF; AlertBanner MVP;
  IncidentTable live con acuse two-step gateado por `allowed_actions.ack_incident`; DetailPanel
  con strip honesto de features 1 s + SOH real + traza de ACKs; CCTV tras `VITE_FEATURE_CCTV`,
  off en MVP). **Desviaciones ratificadas** (plan maestro §B.3): sin magnitud/T-MINUS (WR-1 es
  booleano), "FEATURES 1 s · PROCESAMIENTO EDGE" (no waveform crudo 100 sps, regla de oro 9),
  identidad real de sesión (no selector de turno), "WS · LIVE" (no GraphQL).
  **Verificación:** suite web **197** + lint + build; **E2E de cable vs API real** (dev-token +
  NOTIFY 0004 + poller + RLS): incidente commit→frame **36 ms** (< 2 s), features STA/LTA>3.5
  entregadas por el poller (dato del auto-popup), banner con severity=critical, GET features
  10 min = **8 ms** (< 1 s, 602 muestras). **Smoke de navegador real** (Playwright + chromium
  SwiftShader) 6/6: login dev → /console monta, MapLibre inicializa, banner MVP visible, 2º
  incidente aparece EN VIVO por WS sin recargar, **cero errores de runtime** — que cazó y cerró
  un bug real de MapPanel (opacidad del pulso > 1 por delta negativo del rAF, `877234e`).)

### [x] T-1.28 · Flota Edge — Gabinetes — **[C2]** ✅ (commits `bf69067` + `29814a0`)
- **Componente:** web · **Depende de:** T-1.26
- **Criterios:** inventario de gateways (MQTT lag, SeedLink lag, UPS %, actuadores armados);
  estados `OPERATIVO`/`DEGRADADO`/`SIN ENLACE` calculados de `device_health`; autodiagnóstico
  silencioso visible.
  ([DECISION 2026-07-08]: la UI pinta `derived_state` del servidor tal cual
  (`schemas.fleet.derive_fleet_state` = verdad única) y NO recalcula umbrales — por eso los
  pills MQTT/SeedLink muestran valor crudo y solo marcan crit en SIN ENLACE (el server no
  expone qué métrica degrada; exponerlo sería extensión futura de /fleet/gateways).
  **Actuadores armados**: no hay estado vivo de relays en nube — se derivan de
  `rule_sets.config.relays` (config activa site→tenant) con estado ARMADO si el enlace vive
  (el supervisor edge trata actuadores como módulo crítico fail-fast ⇒ proceso vivo = reglas
  armadas) y S/D en SIN ENLACE; nunca se inventa "FALLA"; caption "CONFIG ACTIVA · ESTADO
  DERIVADO DEL ENLACE". **Autodiagnóstico**: visible y deshabilitado — el vocabulario del
  Command Service es solo `activate|deactivate`; requiere acción `self_test` (extensión de
  T-1.23) + contrato edge. Sin autonomía de batería (battery_min_left no viaja en GatewayOut).
  Base compartida en `bf69067`: StateFrame (4 estados + banner DATOS RETENIDOS, gate
  `expectFourStates`), ConfirmButton two-step, SevTag, react-query 5 + maplibre-gl instalados,
  proxy Vite con `ws: true`. Flota: poll 30 s, stale a 90 s, empty/error/retry propios;
  /sites y /rule-sets degradan sin tumbar la página. Suites: web 145 passed; E2E local contra
  API real (dev-token tenant_admin → /fleet/gateways: OPERATIVO line/100% y DEGRADADO
  battery/72% desde device_health sembrado, RLS solo tenant propio).)

### [x] T-1.29 · Triage Estructural — Historial — **[C3]** ✅ (commits `8df2fab` + `02add96` + `faa4f73` + `fceb7f9`)
- **Componente:** web · **Depende de:** T-1.20
- **Criterios:** evidencia de cumplimiento (auditoría/dictámenes inmutables — blueprint §9;
  [ANALISIS-00]: la etiqueta "NOM-003-SCT" era errónea), historial de eventos, dictamen
  preliminar, regla de quórum con offsets por nodo, exportar miniSEED + PDF.
  ([DECISION 2026-07-08]: `features/triage/` compone `/incidents` (por sitio: PGA/PGV/
  severidad/estado) + `/events` (magnitud, epicentro, `meta.node_count`) + `/sites`; ningún
  endpoint devuelve la fila del mockup, que confundía evento con incidente. Filtro de
  severidad y búsqueda por prefijo de `event_id` los hace el SERVIDOR. Offsets por nodo =
  `quorum_votes[].delta_s` de `/events/{id}`, VERBATIM; ancla = el `delta_s` menor. Dictamen =
  cadena append-only de `/incidents/{id}/dictamens` (`signed_by IS NULL` ⇒ PRELIMINAR); firma
  con ConfirmButton. Evidencia = `/incidents/{id}/evidence` (miniSEED) + `/incidents/{id}/report`
  (PDF); bitácora visible = `incident_actions` (§9), porque `audit_log` NO tiene endpoint de
  lectura (deuda backend anotada).
  **El veredicto del quórum es un HECHO DEL SERVIDOR** (`source='local_quorum'`, que el motor
  sólo escribe al alcanzarlo), no una comparación del cliente contra `min_nodes`: el motor
  prefiere el rule_set de SITIO y usa la versión vigente en su momento, así que recalcularlo
  contradecía al propio motor sobre eventos históricos. `min_nodes` se muestra como contexto.
  **Correcciones de contrato que destapó la tarea** (`8df2fab`): `dictamens.py` hardcodeaba
  `SIGN_ROLES=(inspector,superadmin)` mientras `matrix.py` reserva la firma al inspector — el
  servidor aceptaba una firma que la consola negaba (superadmin POST ⇒ 201, ahora 403); y
  `allowed_actions.export` cubría DESCARGAR y GENERAR, así que gov_operator (export=true, sin
  permiso de report) habría visto un botón PDF condenado al 403 ⇒ se separa `generate_report`.
  `roles_with_action()` es ahora la única forma de traducir la matriz a roles.
  Además (`02add96`) `GET /fleet/gateways/{id}/config-state` hace observable el sync firmado, y
  (`faa4f73`) `COALESCE` cierra un 500 real: `NULL::jsonb ? 'edge'` es NULL, no false.
  **Desviaciones honestas:** sin cita normativa (§9 retiró NOM-003-SCT; marco citable por
  confirmar); sin traza MiniWaveform ni "CANAL Z · 200 Hz" (RS4D = 100 sps, regla de oro 9) →
  se enlaza el miniSEED archivado y sin fila `kind='miniseed'` el botón se deshabilita CON
  motivo; sin "Firmado HSM" (`signed_by` es un uuid Cognito); sin "EXPORTAR LOTE" ni selector
  de rango (`/incidents` no filtra por fecha); nodos por `sensor_id` corto (no hay resolver a
  código de estación) y epicentro en coordenadas (no hay geocodificación inversa); magnitud del
  catálogo post-hoc, jamás preliminar (§14).
  **Regla de oro 7 al extremo:** cada recurso (cadena, bitácora, evidencia, evento) lleva SU
  loading/error. Colapsarlos hacía que un panel afirmara "0 OBJETOS", "0 ACCIONES REGISTRADAS"
  o "SIN EVENTO ASOCIADO" con la petición en vuelo o fallada. Seis hallazgos así los cazó la
  revisión adversarial; todos tienen regresión.
  **Verificación:** web 283 passed (84 de triage) + lint + build; api 577 passed;
  **E2E de cable vs API real 46/46** (offsets 0.00/1.42/3.07 s, cabeza preliminar, superadmin
  firma ⇒ 403, gov PDF ⇒ 403, inspector firma ⇒ 201 y la cadena CRECE, PDF sin bucket ⇒ 503);
  **smoke de navegador 25/25** junto con T-1.30, cero errores de runtime.)

### [x] T-1.30 · Matriz Multi-Tenant — Umbrales — **[C4]** ✅ (commits `aa6f815` + `995a84a`)
- **Componente:** web · **Depende de:** T-1.23
- **Criterios:** aislamiento visible (lógico vs dedicado), umbrales por tipo de instalación,
  cascada de notificación configurable, sync firmada al edge.
  ([DECISION 2026-07-08]: aislamiento = `tenants.isolation_mode` (CHECK 'logical'|'dedicated')
  pintado tal cual; RLS decide las filas. Umbrales → `config.edge.thresholds`, la ÚNICA rama que
  el worker publica al gabinete: **cuatro** sliders (cautela + disparo × PGA/PGV), porque ése es
  el `ThresholdBand` real del edge; una clave ausente se rotula "DEFAULT DEL EDGE" (es lo que el
  gabinete aplicaría). Cascada: los canales y sus DESTINOS se configuran (`config.notifications`);
  el ORDEN (webhook→whatsapp→sms→email) y los tiempos son fijos en el servidor y se muestran, no
  se editan; canal sin destino ⇒ INCOMPLETO (justo lo que `resolve_destinations` omitiría).
  Sync firmada: `PUT` → `publish` (202 `pending_sync`) → poll de `config-state`; la consola sólo
  dice "CONFIG FIRMADA APLICADA" con esa evidencia, nunca por haber pulsado el botón.
  **Tres agujeros de seguridad/integridad que destapó la tarea** (`aa6f815`, todos sobre la config
  que ARMA sirena y gas): (1) **cruce de tenants en la escritura** — el INSERT fijaba
  `tenant_id=claims.tenant_id` y el alcance venía del cuerpo, así que un rol interno podía apagar
  los rule_sets de un tenant ajeno e insertar una fila con SU tenant y el scope del ajeno; el
  worker resuelve POR ALCANCE, así que los gabinetes del ajeno la habrían aplicado siendo
  invisible para su admin (RLS) ⇒ ahora 403/404; (2) **el `secret` del webhook viajaba al
  navegador** en `GET /rule-sets` ⇒ se redacta al leer y el servidor lo reinyecta al escribir, de
  modo que guardar un umbral no rompa la firma HMAC del cliente ni deshabilitar/re-habilitar el
  canal la destruya; (3) **lost update** — el PUT reemplaza el blob entero ⇒ `base_version` con
  409 (antes un segundo escritor revertía en silencio `relays.siren`).
  **Desviaciones honestas:** fuera "AISLAMIENTO DE DATOS" (schema por tenant / AES-256 / llaves
  KMS: afirmaciones de infra sin respaldo de API); fuera "NUEVO" (no hay `POST /tenants`) y la
  cuenta de usuarios (no hay endpoint; los sitios salen de `/sites` y sin datos se muestra S/D);
  `tenants.vertical` (texto libre, nullable) es el tipo de instalación, pero los umbrales se
  guardan por SCOPE de rule_set ⇒ las bandas §4.5 son pista estática, no agrupación; el canal
  real es `webhook`, no `api`; no se promete "≤60s firmado JWT" (es HMAC y lo entrega el worker).
  Un superadmin viendo OTRO tenant es SÓLO LECTURA con motivo visible. Se muestra la HUELLA de la
  config firmada, no `gateway_config_state.version` (cuenta ENTREGAS por gateway y no es
  comparable con `rule_sets.version`). Una publicación ajena no pisa la edición sin guardar.
  Se elimina `PlaceholderPage`: ya no queda ninguna ruta sin implementar.
  **Verificación:** web 372 passed (89 de tenants) + lint + build; api 586 passed;
  **E2E de cable vs API real 29/29** (RLS de /tenants; el secret ausente del GET pero intacto en
  la DB tras dos PUT; base_version vieja ⇒ 409 con `relays` intactos; alcance ajeno ⇒ 403;
  publish ⇒ 202; config-state PENDIENTE → SINCRONIZADO con sólo la huella sha256);
  **smoke de navegador real 25/25**, cero errores de runtime.)

### [ ] T-1.31 · App móvil (fase posterior) — **[C5]**
- **Componente:** mobile · **Depende de:** T-1.22, T-1.26 · **Diferida — no iniciar en Fase 1.**
- **Criterios (referencia futura):** acuse, escalamiento, inspección de campo con
  checklist/fotos/firma, check-in de vida, offline-first.

---

## Hito de salida Fase 1 — ✅ ACREDITADO (2026-07-08)
Demo en vivo con 3 gabinetes: prueba SASMEX dispara actuadores y aparece en el SOC; sismo
simulado en 3 estaciones activa quórum; corte de internet no detiene la protección local.

> **ACREDITADO.** `make demo-fase1` = **35/35 asserts en verde**, determinista en 5 corridas
> consecutivas. Runbook: `takab-docs/runbooks/RUNBOOK-demo-fase1-tres-gabinetes.md`.
> ([DECISION 2026-07-08]: demo LOCAL reproducible — 3 `EdgeSupervisor` REALES en procesos
> separados (`gpio`/`rules`/`actuators` de verdad, relés mock) + el `SqsConsumer` REAL + el
> `IncidentEngine` REAL + el SOC observado por el mismo `NOTIFY takab_live` del hub WS. **Único
> tramo sustituido: IoT Core + SQS** (`demo/spool.py`, con visibility-timeout y redrive a DLQ
> propios porque el consumer real depende de ellos). Evidencia medida: **C1** reflejo software
> 0.037 ms, 5/5 relés, incidente en el SOC en ~150 ms (<2 s); **C2** el motor forma
> `seismic_events source='local_quorum'` con 3 `quorum_votes` de 3 sensores distintos y offsets
> en ventana (+ fail-open real de sitios sin enlace); **C3** actuación 5/5 sin nube, `sent` no
> avanza, spool durable crece y drena al reconectar, e **idempotencia real** por RE-ENTREGA del
> `LocalEvent` archivado byte-idéntico ⇒ el handler hace `ON CONFLICT (event_uuid)` y sigue 1
> incidente. **Confirmación en HARDWARE real (Pi 5 `gw-dev-0001`)**: corte de WAN reversible
> (nft, sólo egress a tcp/8883, watchdog auto-revert) — servicio `active`, spool 0→93→0, cero
> pérdida. **Gate #3 sigue abierto**: relés MOCK; la latencia física <100 ms NO se acredita
> (no hay WR-1/relés/sirena/válvula cableados; riesgo de disparo real = nulo). Revisión
> adversarial de 4 lentes: 16 hallazgos, 12 refutados, **4 asserts tautológicos corregidos**
> para que el harness sea honesto — cada assert que pasa observa un hecho real.)

> Fuera de alcance explícito de este ciclo (T-MINUS, magnitud preliminar, streaming continuo de
> waveform, IA en ruta determinista, mini-ShakeMap, modificar Shake OS): ver
> `BLUEPRINT-TECNICO-TAKAB.md §14`.

---

# Fase 1.5 · Operabilidad (auditoría final, 2026-07-09)

> Auditoría de las tres capas contra `CLAUDE.md`, `USER-STORIES.md` y el blueprint. El mapa, el
> strip sísmico y la consola YA existían; lo que faltaba de verdad era poder **dar de alta
> estaciones**, tener el **cómputo en la nube** y no **mentir sobre la calibración**.

### [x] T-1.32 · CRUD de flota: sitios, gateways y sensores — **[C2] COMPLETA**
- **Componente:** api · **Depende de:** T-1.22, T-1.30 · Cierra la mitad de escritura de **US-20**.
- **Objetivo:** que un `tenant_admin` cree, mueva y retire estaciones desde el SOC, en vez de
  sembrarlas por SQL (`db/seeds/dev_fleet.sql`).
- **Criterios de aceptación:**
  - [x] Acción `manage_fleet` en `auth/matrix.py` → `takab_superadmin` + `tenant_admin`.
        `takab_support` **no** la recibe ([DECISION 2026-07-09]: gana el código sobre §2 del RBAC;
        soporte lee la flota, no mueve la geometría de un sitio ajeno).
  - [x] Migración `0009` añade `sites.status` (`active|retired`). `gateways`/`sensors` ya lo tienen.
  - [x] `POST/PUT/DELETE` en `/sites`, `/fleet/gateways`, `/sensors`. `DELETE` = retiro lógico.
  - [x] El `tenant_id` sale SIEMPRE de los claims; para `takab_superadmin` es explícito y validado.
        Motivo: `sites_admin` tiene `WITH CHECK (app_is_takab_internal())` **sin filtro de tenant**.
  - [x] Bloqueo optimista por `xmin::text`; `base_row_version` viejo ⇒ 409. Serial duplicado ⇒ 409.
  - [x] `audit_async` en cada mutación. Alta de gateway **sin llamadas a AWS** (`status='provisioned'`).
  - [x] Test de cruce de tenants en ESCRITURA ⇒ 403. `soc_operator` ⇒ 403.

> **COMPLETA.** api **608 passed** (baseline 586, +22), web **373 passed**, ruff/eslint/prettier
> limpios, `vite build` OK. Además del CRUD, la tarea destapó y cerró **dos fugas de tenancy que la
> DB no habría detenido**: (1) las políticas `sites_admin`/`gateways_admin`/`sensors_admin` llevan
> `WITH CHECK (app_is_takab_internal())` **sin filtro de tenant** ⇒ el `tenant_id` de un alta jamás
> se toma del cuerpo (`resolve_write_tenant`); un superadmin debe nombrarlo explícitamente o recibe
> 400. (2) Las **FK de PostgreSQL no comparan `tenant_id`** ⇒ un `site_id`/`gateway_id`/`zone_id`
> ajeno en el cuerpo habría colgado hardware de un cliente en el edificio de otro
> (`tenant_of_parent_site` + `require_same_tenant`); es el mismo patrón que cerró T-1.30 en
> `rule_sets`. **Desviaciones honestas:** el alta de gabinete **no llama a AWS** (los certs X.509 son
> de Terraform) y nace en `provisioned` con `iot_thing` nulo — sin heartbeat no se puede afirmar
> "online" (regla de oro 7); `GatewayUpdate` **no acepta `status`** porque `online/degraded/offline`
> los deriva el heartbeat, no un formulario; `restore` devuelve a `provisioned`, nunca a `online`.
> `GET /telemetry/map/state` y `GET /sites` ahora filtran `status='active'` (retirar un sitio lo
> saca del mapa; `?include_retired=true` lo recupera). También se formaliza el fix del **mapa
> invisible**: `DEV_TENANT_DEFAULT` apuntaba a un tenant SIN sitios, así que `/console` caía en el
> estado `empty`; ahora es una constante exportada y anclada por test al tenant de `dev_fleet.sql`.

### [x] T-1.33 · Honestidad de calibración PGA/PGV — **[C2/C3] COMPLETA**
- **Componente:** api + web + edge · **Depende de:** T-1.32
- **Objetivo:** dejar de presentar como `g` y `cm/s` absolutos unos números escalados con las
  sensibilidades PLACEHOLDER de `edge/takab_edge/config/settings.py` (`SignalConfig`), a la espera
  del StationXML del RS4D (T-1.6 diferido). Mostrar un dato sin calibrar como si fuera físico es
  exactamente lo que prohíbe la regla de oro 7.
- **Criterios de aceptación:**
  - [x] Migración `0010`: `sensors.calibration_source text` → `SensorOut.calibrated` derivado.
  - [x] El snapshot de features expone `calibrated` del sitio (true solo si TODOS sus sensores
        activos lo están).
  - [x] La web usa `unitsFor(calibrated)` → `g`/`cm/s` vs `rel.`, y pinta `SIN CALIBRAR`.

> **COMPLETA.** api **615 passed**, web **380 passed**, edge **239 passed**, lint/build limpios.
> **Decisión de diseño:** NO existe un booleano `calibrated` escribible — sería una afirmación que
> nadie respalda. Existe `sensors.calibration_source` (`'stationxml:AM.R4F74.2026-07-09'`) y
> `calibrated := (calibration_source IS NOT NULL)`, derivado en la DB. Para declararte calibrado
> tienes que **nombrar la procedencia de la respuesta instrumental**. Un sitio está calibrado solo
> si lo están TODOS sus sensores ACTIVOS (`bool_and`): mezclar en un mismo strip un canal anclado y
> otro sin anclar produce una cifra sin significado físico. `bool_and` sobre cero filas devuelve
> NULL ⇒ default-deny (sitio sin sensores = sin calibrar). En la web, `unitsFor(undefined)` también
> devuelve `rel.`: un backend viejo o un snapshot a medio cargar nunca inventan una `g`. El
> docstring de `SignalConfig` ahora apunta a la columna, para que quien sustituya las sensibilidades
> por las del StationXML sepa que además debe declarar la fuente o la UI seguirá —con razón—
> diciendo SIN CALIBRAR.

### [x] T-1.34 · Strip multicanal + vista histórica — **[C3] COMPLETA**
- **Componente:** api + web · **Depende de:** T-1.33 · Responde a **US-03** sin violar la regla de oro 9.
- **Criterios de aceptación:**
  - [x] `MultiChannelStrip` pinta EHZ/ENZ/ENN/ENE con eje temporal.
  - [x] `HistoryChart` sobre `site_metrics_1m`/`_1h`, presets 1h/6h/24h/7d (el preset conmuta el cagg).
  - [x] Sin waveform crudo. Sin librería de gráficas. Los 4 estados obligatorios.

> **COMPLETA.** Nuevo `GET /telemetry/sites/{id}/features/by-channel`: **una sola query** agrupada
> server-side, no cuatro requests (los canales de un sitio son 4 y cada uno costaría su propio plan
> sobre la vista segura). Decisiones: **cada traza tiene su propia escala vertical** — EHZ es el
> geófono (velocidad) y EN[ZNE] el acelerómetro; un eje común aplastaría uno de los dos. **Un canal
> sin datos NO se pinta plano**: su ausencia es la información (una línea en cero diría "todo
> tranquilo" cuando en realidad no está reportando). El historial se dibuja con **barras, no línea**:
> es el máximo por bucket, y una línea sugeriría una interpolación que el cagg no respalda. El preset
> conmuta el bucket (`7d`⇒`1h`): 7 días en buckets de 1 min serían 10.080 puntos para 600 px.
> Los helpers de escala (`svgScale.ts`) son puros y se prueban solos.

### [x] T-1.35 · Completar `/building/:siteId` — **[C5] COMPLETA**
- **Componente:** web · **Depende de:** T-1.34 · Última página placeholder del árbol.
- **Nota de alcance:** es la vista del **staff con sesión** (`building_admin`, `inspector`, roles
  SOC). **No** es la pantalla del ocupante: `occupant`/`brigadista`/`security_guard` tienen
  `allowed_routes = []` y su superficie es la app móvil (T-1.31). Según **US-05**, la interfaz del
  ocupante es la **sirena**.
- **Criterios de aceptación:**
  - [x] Estado del sitio, incidentes del sitio, strip multicanal, salud del gabinete.
  - [x] Prueba de sirena solo si `me.allowed_actions.siren_test`, y no afirma que sonó hasta
        recibir el `command_ack` del edge (regla de oro 8).

> **COMPLETA.** api 621 passed · web 423 passed · lint/build limpios. Desaparece la última página
> placeholder del árbol. **Es la primera superficie de la consola que puede disparar un actuador
> real** (`POST /sites/{id}/commands` no tenía cliente hasta ahora), así que el panel de sirena
> modela SIETE estados y jamás colapsa "el comando salió" con "el actuador se movió": `201` ⇒
> **COMANDO EMITIDO · ESPERANDO ACUSE**, y solo `status='acked'` ⇒ **SIRENA SONANDO**. Sin acuse
> dentro del TTL dice **SIN RESPUESTA DEL GABINETE · LA SIRENA NO SE ACTIVÓ** (nunca "activada").
> Confirmación en dos pasos (`ConfirmButton`, RBAC §4.3) y el sondeo se apaga en cuanto el comando
> se resuelve (regla de oro 10). El `h1` es el título de la PÁGINA, no el nombre del sitio: existe
> antes de que cargue y no cambia con los datos (lo exige `routes.guards.test`). El dictamen de
> reingreso se deja en `/triage`, que es donde vive la cadena de firmas — duplicarlo aquí habría
> creado dos caminos para un acto legal que debe tener uno solo.

### [x] T-1.36 · UI de alta de estaciones con selector de punto en el mapa — **[C5] COMPLETA**
- **Componente:** web · **Depende de:** T-1.32
- **Criterios de aceptación:**
  - [x] Sub-superficie bajo `/fleet` (no una ruta nueva ⇒ no cambia `allowed_routes`).
  - [x] `MapPointPicker` con marcador arrastrable, componente nuevo (no sobrecargar `MapPanel`).
  - [x] Los controles de escritura solo se pintan si `me.allowed_actions.manage_fleet`.

> **COMPLETA.** web **446 passed** · lint/build limpios. `FleetAdmin` va **fuera** del `StateFrame`
> de la flota: un tenant sin gabinetes cae en el estado `empty`, y es justo ahí donde hace falta
> poder crear la primera estación — enterrar el alta dentro del marco la habría hecho inalcanzable.
> La compuerta `manage_fleet` está **separada del panel**: quien no administra la flota no monta ni
> un `useQuery` (no se pide `/sites`, no existe el botón). `MapPointPicker` acepta arrastre Y clic
> (arrastrar un marcador de 20 px sobre una azotea es peor que apuntar) y no muta estado interno: la
> prop `value` manda, así que el formulario y el mapa nunca discrepan. El mapa se crea UNA vez
> (encuadre inicial en una ref): recrearlo en cada arrastre perdería el zoom del operador.
> `parseLatLonPair` acepta el orden HUMANO (`lat, lon`, el de Google Maps) y devuelve el de la
> máquina (`lon, lat`); un par invertido se **rechaza** en vez de plantar la estación en el mar. Los
> 409 llegan al operador en castellano y accionables, no como "algo salió mal". El alta de hardware
> no manda `tenant_id` (lo hereda del sitio) ni `iot_thing` (lo emite Terraform), y un sensor sin
> procedencia se crea con `calibration_source = null` — SIN CALIBRAR, que es la verdad.

### [~] T-1.37 · Desplegar API + workers + consola en el EC2 — **[B7] CÓDIGO LISTO · APPLY PENDIENTE**
- **Componente:** infra · **Depende de:** T-1.32…T-1.36
- **Objetivo:** que la nube corra en la nube. Hoy Terraform tiene DB, IoT Core, SQS, S3, Cognito,
  ECR y KMS, pero **cero cómputo**: la API, el consumer y la web corren en la laptop.
- **Criterios de aceptación:**
  - [x] `instance_type` = `t4g.medium` ([DECISION 2026-07-09]: 2 GiB no alcanzan; el OOM-killer
        mataría a Postgres. +$12.26/mes ⇒ total ~$42–47/mes, bajo el budget de $50).
  - [x] `docker-compose` en el EC2 con la imagen ECR existente + Caddy/TLS sobre sslip.io.
  - [x] La API usa el DSN `takab_app` (RLS forzada); los workers, `takab_ingest` (BYPASSRLS).
        Mezclarlos es cruce de tenants (regla de oro 5).
  - [x] Secretos de Secrets Manager a tmpfs `/run/takab/*.env`. Cero secretos en git.
  - [x] `/dev/token` apagado en la nube. SG `takab-dev-web` separado y desconectable.
  - [x] `make cloud-deploy` existe y es idempotente.
  - [ ] **`terraform apply` + `make cloud-deploy` ejecutados contra AWS.** ⟵ requiere ventana:
        cambiar `instance_type` PARA la instancia (la DB cae minutos; el gabinete acumula spool).

> **CÓDIGO LISTO, NO APLICADO.** Verificado sin tocar AWS: `terraform validate` + `fmt` OK, el
> Caddyfile pasa `caddy validate` real, el compose pasa `docker compose config`, y **la imagen se
> construyó y se ejecutó**: los 6 entrypoints (`ingest`/`incident`/`notify`/`commands`/`billing`/
> `backfill`) importan y `alembic heads` resuelve. Ejecutar la imagen destapó **dos bugs que la
> suite no podía ver**: (1) `python -m alembic -c api/alembic.ini` falla porque `script_location =
> migrations` se resuelve contra el **CWD**, no contra el `.ini` ⇒ el deploy corre con
> `--workdir /takab/api`; (2) **`notify/providers.py` importa `httpx` a nivel de módulo pero
> `httpx` vivía solo en el extra `dev`** ⇒ el worker moría con `ModuleNotFoundError` en cualquier
> despliegue real. Se movió a `[project] dependencies` y se añadió el contract-test
> `tests/contracts/test_runtime_deps.py`, que compara los imports de tercero de `src/takab_api`
> contra las dependencias declaradas: el CI se detiene en vez de la producción.
> **Desviaciones:** T-1.26 ratificó "mismo origen tras CloudFront" — Caddy conserva el invariante
> (mismo origen ⇒ sin CORS, y `wss://host/api/ws` por la misma regla) y cambia el mecanismo.
> La clave HMAC de comandos es UNA sola (`Settings.command_hmac_key`) mientras Terraform emite una
> POR gabinete: la nube carga la del real (`gw-dev-0001`) y los simulados rechazarían la firma;
> sin secreto, el servicio arranca **fail-closed** (503) en vez de con clave vacía
> **[LIMITACIÓN CERRADA en T-1.38: resolución por gabinete]**. AL2023 no trae
> el plugin `compose`: el deploy lo instala. Runbook: `deploy/cloud/README.md`.

---

# Fase 1.6 · Verdad operativa (cierre de fallos, 2026-07-09)

> Cierra TODO lo documentado como abierto que se puede cerrar con los accesos reales (Pi 5,
> Shake, AWS): los 4 GAPs del despliegue, la clave HMAC por gabinete, las sondas de salud en
> stub, la calibración física, la semántica del WR-1, el PIN del panel local, el rol CI y la
> validación del quórum contra el SSN. Lo que exige terceros (WhatsApp/SMS/SES prod, app móvil,
> relés físicos) queda documentado como diferido, no fingido.

### [x] T-1.38 · Reparar el despliegue (GAP-1..4) + clave HMAC por gabinete — **[B9/B7] COMPLETADA (2026-07-09)**
- **Componente:** api + infra + deploy · **Depende de:** T-1.37
- **Objetivo:** que el primer `cloud-deploy` real no muera al arrancar, y que la firma de un
  comando LIGUE al gabinete destino (HIGH #23 de la auditoría pre-frontend).
- **Criterios de aceptación:**
  - [x] **GAP-1:** Terraform exporta `dlq_urls` y `deploy.sh` inyecta `TAKAB_API_DLQ_URL_*`
        (los consumidores hacen `SystemExit` sin ellas — backfill incluido).
  - [x] **GAP-2:** el servicio `api` puede emitir comandos (ya no existe `command-hmac.env`;
        el prefijo del secreto viaja en `cloud.env`, que montan todos).
  - [x] **GAP-3:** el deploy siembra `db/seeds/dev_fleet.sql` en la DB de la nube (idempotente,
        superusuario por socket local del contenedor — cero secretos materializados).
  - [x] **GAP-4:** el rol EC2 puede `iot:Publish` a `takab/cmd/*` y `takab/cfg/*`
        (Sid `WorkerIotPublish`; antes solo `backfill/grant/*` ⇒ AccessDenied).
  - [x] **HMAC por gabinete:** `commands/keys.py` con `StaticKeyProvider` (dev/tests,
        `TAKAB_API_COMMAND_HMAC_KEYS_JSON`) y `SecretsManagerKeyProvider` (prod, cache TTL 300 s,
        cache negativa 30 s, transitorios sin cachear). `issue_command` y el config sync firman
        con la clave del gateway DESTINO; sin clave resoluble ⇒ 503 / skip sin quemar versión.
        `Settings.command_hmac_key` **eliminada**: no existe fallback a clave compartida.
  - [x] Secreto HMAC **separado** del secreto del certificado (`takab/dev/gateway-hmac/<thing>`):
        IAM no filtra campos JSON; el wildcard del prefijo jamás expone claves privadas mTLS.
  - [x] Tests: `test_keys.py` (cache/rotación/negativa/transitorios), router (503 por gateway sin
        clave; dos gabinetes firman con claves distintas), sync mixed-fleet. **api 636 passed.**
  - [x] `terraform validate` + `plan` limpio: 10 recursos nuevos (secreto+versión × 5), policy
        actualizada, **cero replaces** de la instancia.

> La decisión de diseño que importa: **separar el secreto**. `takab/dev/gateway/<thing>` contiene
> `cert_pem + private_key`; darle a la nube `GetSecretValue` por wildcard ahí habría regalado la
> identidad mTLS de toda la flota si la instancia se compromete. El secreto nuevo solo lleva
> `{thing_name, hmac_key}` y reutiliza la MISMA `random_password`, así que el `edge.env` ya
> instalado en `gw-dev-0001` sigue siendo válido sin re-provisionar. `provision_gateway.sh` ahora
> baja dos secretos. Rotación: la nube converge en ≤300 s (TTL del cache) sin reiniciar procesos;
> el edge sí exige re-provisión (ventana fail-visible: rejected/expired, nunca silenciosa).

### [~] T-1.40 · Salud honesta del edge — **[B4/C7] CÓDIGO LISTO · DESPLIEGUE tras T-1.39**
- **Componente:** edge + api + web · **Depende de:** T-1.10 (stubs), T-1.39 (para verificar en nube)
- **Objetivo:** que `/fleet` deje de mentir. `HostProbes` devolvía NTP=0.0, UPS «RED ELÉCTRICA
  100%» y cert=365 fijos; `mqtt_rtt_ms` era NULL en toda fila. La batería era un invento.
- **Criterios de aceptación:**
  - [x] **NTP real:** `chronyc -c tracking` con fallback `timedatectl timesync-status` (el Pi usa
        systemd-timesyncd — verificado; `show-timesync` NO expone el offset, se parsea la salida
        humana con LC_ALL=C). Sin fuente ⇒ `None`.
  - [x] **Cert real:** `openssl x509 -enddate` sobre `TAKAB_EDGE_MQTT_CERT_PATH` (el cert de AWS
        IoT vence 2049-12-31 ⇒ ~8 500 días: número grande pero HONESTO). Ilegible ⇒ `None`.
  - [x] **UPS honesta:** NUT (`upsc`) → sysfs `power_supply` → sin hardware ⇒
        `UNKNOWN + battery None` (la UI pinta «UPS · S/D» y «—», no 100%).
  - [x] **RTT MQTT real:** tiempo hasta el PUBACK QoS1 medido en `AwsIotMqttTransport.publish`
        → `CloudConnector.mqtt_rtt_ms` → snapshot → `device_health.mqtt_rtt_ms` (dejaba NULL).
  - [x] **Contrato honesto v1.1.0:** `HealthSnapshot` con ntp/battery/cert nullable +
        `mqtt_rtt_ms`; schemas compartidos regenerados; la ingesta persiste None como NULL.
  - [x] **Ninguna sonda mata el heartbeat** (backlog #28): `_safe()` por sonda + try/except en
        `_heartbeat_loop`; sondas con timeout de 2 s.
  - [x] **`degrade_reasons` server-side** (backlog de T-1.28): `fleet_degrade_reasons()` es la
        MISMA verdad que `derive_fleet_state` (que ahora la llama); pills en `SiteCard`.
        «Sin dato» JAMÁS degrada: no tener UPS no es estar en batería.
  - [x] **Deploy del edge versionado:** `deploy/edge/deploy.sh` (rsync + uv sync + unidades +
        restart + verificación) — antes era un rsync manual sin versionar.
  - [x] Suites: edge 250 · api 641 · web 448, lint/format/build limpios.
  - [ ] **Desplegado y verificado EN LA NUBE** (`/fleet` con NTP/cert/RTT reales y UPS S/D)
        ⟵ tras el `terraform apply` de T-1.39 (primero nube, después edge — el orden importa
        por el contrato).

### [~] T-1.44 · Endurecer el rol CI OIDC — **[infra] CÓDIGO LISTO · viaja en el apply de T-1.39**
- **Componente:** infra · **Cierra:** HIGH #24 de la auditoría pre-frontend
- **Objetivo:** `takab-ci-plan` era asumible desde **cualquier ref** (`repo:...:*` con
  `StringLike`) con ReadOnlyAccess + lectura del tfstate — y ningún workflow legítimo lo usa
  siquiera (el paso plan-only de `ci.yml` sigue en TODO). Superficie de exfiltración pura.
- **Criterios de aceptación:**
  - [x] Trust policy anclado EXACTO a `repo:MauBautista/alertamiento-sismico:ref:refs/heads/main`
        con `StringEquals` (sin comodines en la superficie más federada de la cuenta).
  - [x] Los jobs de PR no necesitan AWS (corren tests herméticos) — verificado en `ci.yml`.
  - [x] `terraform validate` + plan: 1 cambio in-place, cero recursos nuevos.
  - [ ] Aplicado ⟵ viaja en el `terraform apply` de la ventana de T-1.39.

### [~] T-1.43 · PIN en el panel local del gabinete — **[B8] CÓDIGO LISTO · DESPLIEGUE con T-1.40**
- **Componente:** edge · **Cierra:** #35 del backlog (local_api sin auth)
- **Objetivo:** `POST /api/{silence,siren-test,reset}` se aceptaban sin autenticar; la única
  barrera para silenciar la sirena de un edificio era estar en su LAN.
- **Criterios de aceptación:**
  - [x] Las ACCIONES exigen `X-Takab-Pin` (comparación constant-time); la LECTURA (GET) sigue
        abierta — es el panel del guardia.
  - [x] Lockout: 5 PINs erróneos ⇒ 429 por 60 s (ni el correcto entra). Header AUSENTE no
        cuenta como intento (es la página preguntando).
  - [x] Sin PIN configurado: `dev_mode` abierto (tests/demo); **producción 403 fail-closed**.
  - [x] La página pide el PIN una vez y lo retiene SOLO en memoria JS (CLAUDE.md §8: nada de
        localStorage); mensajes claros para 401/403/429.
  - [x] `provision_gateway.sh` genera un PIN de 6 dígitos, lo instala en `edge.env` y lo
        imprime UNA vez (esa impresión ES la entrega al responsable del edificio).
  - [x] Autorización ANTES de tocar GPIO; el camino físico WR-1→sirena no se toca (regla 1).
  - [x] Suite edge 256 passed (7 tests nuevos de PIN).
  - [ ] Desplegado al Pi y verificado con el navegador ⟵ va junto al deploy de T-1.40.
