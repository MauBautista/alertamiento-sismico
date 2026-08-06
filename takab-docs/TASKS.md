# TASKS.md — Backlog ejecutable TAKAB Ailert (Fase 1 → cierre del proyecto)

> Cómo se usa este archivo con Claude Code:
> - Ejecutamos **una tarea a la vez, en orden** (respetando `depende de`).
> - Orden de bloques = **EDGE PRIMERO, luego CLOUD, luego FRONTEND** (`BLUEPRINT-TECNICO-TAKAB.md §0.1, §13`).
> - Por cada tarea: `/write-plan` → `/goal "<acceptance>"` → `/execute-plan` dentro de `/loop`
>   hasta que TODOS los criterios pasen. Ver método en `CLAUDE.md §6`.
> - Marca `[x]` la tarea solo cuando cumpla su **Definition of Done** (`CLAUDE.md §6`).
> - Si un criterio no pasa tras 3 iteraciones del loop: detente y reporta el bloqueo.
> - Cada tarea referencia su Work Package (WP) del blueprint entre corchetes, ej. `[A2]`.

## Estado actual (2026-08-05)

**Conteo de tareas:** total **196** · `[x]` **140** · `[~]` **2** · `[ ]` **54**

> ⚠️ **OBLIGACIÓN PERMANENTE — lee esto antes de cambiar el estado de una tarea.**
> Esa línea de arriba **la verifica un test**:
> `api/tests/test_docs_consistency.py::test_la_cabecera_de_tasks_declara_el_conteo_real`
> cuenta los encabezados `^### [.]` del archivo y exige que cuadren.
> **Si cierras, abres o añades una tarea, actualiza el conteo EN EL MISMO COMMIT.**
>
> No es fricción arbitraria: hasta hoy esta cabecera decía *"9 de 9 tareas en verde"* con
> **134 tareas** dentro del archivo — **36 tareas de retraso** y meses de deriva. El conteo
> declarado a mano es lo único que envejece; contarlo con una regex es lo único que no. Ese
> test, más otros cuatro, nacieron en **T-2.61** por esta razón exacta.
>
> Estados: `[x]` hecha (cumplió su DoD) · `[~]` parcial (código listo, falta un gate externo)
> · `[ ]` abierta. No hay más.

**Dónde estamos.** Todo hasta `T-2.60.a` está construido y mergeado a `main`: Bloques A/B/C/D
(T-1.1…T-1.30) + Fases 1.5…1.10 (T-1.32…T-1.73) + **Fase 2 · App móvil completa**
(T-2.00…T-2.14) + **Fase 2.1 · panel del gabinete** (T-2.15…T-2.23) + **Ciclo Nube 2.2 ·
auditoría y reforma de la consola SOC** (T-2.35…T-2.59) + T-2.60.a. Las 2 `[~]` son **T-1.42**
(semántica real del WR-1: falta transmisión real de CIRES + relé físico) y **T-1.44** (rol CI
OIDC: código listo, falta `terraform apply`) — ambas esperan a un humano, no a código.

**Qué corre en producción se le pregunta al sistema, no a este archivo** (`/api/health` para la
nube, `FW_VERSION` para el gabinete — ver README §"¿Qué está desplegado?").

**Lo que falta hacia un cliente real NO es mayormente código.** Los relés siguen en MOCK y
`G-04` (latencia contacto→relé→sirena en hardware real) **lleva abierto desde el hito de Fase 1
mientras el backlog de software avanzó 60 tareas**. La ruta completa hasta el cierre —con
etiqueta de bloqueo por tarea, ruta crítica e invariantes— está al final de este archivo:
**§"RUTA AL CIERRE DEL PROYECTO"**. Ver también §10 de `runbooks/RUNBOOK-auditoria-cierre.md`
y `runbooks/RUNBOOK-cierre-fase2.md`.

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

## Bloque B · EDGE (Raspberry Pi 4) — se construye PRIMERO · Blueprint Fase A

### [x] T-1.2 · Scaffolding `edge/` + simuladores — **[A0]** · COMPLETA
- **Componente:** edge · **Depende de:** T-1.1 · **Prioridad: ALTA**
- **Objetivo:** `edge/` con `uv`, `pyproject.toml`, `supervisor.py`, estructura de módulos
  (`takab_edge/{seedlink,signal,buffer,gpio,rules,actuators,cloud,health,config,security,local_api}`)
  y **simuladores** de RS4D (feed SeedLink sintético 100 sps), WR-1 (toggle GPIO) y BACnet.
  [ANALISIS-00]: se quitó `quorum` del scaffold (el quórum vive en la NUBE, T-1.19 — ver
  blueprint §4.2) y se añadió `local_api` (lo exigen RBAC §4.2 y T-1.13).
  [PLAN-MAESTRO-01]: `sasmex` → `gpio` consolidado (entrada WR-1 + relés locales + reflejo
  SASMEX→sirena in-process) `[RATIFICADO 2026-07-09 · T-1.45 · gate #6]` — el contrato quedó
  congelado en T-1.8 y el nombre del módulo ya no se renegocia (`PLAN-MAESTRO §3`).
- **Criterios de aceptación:**
  - [x] **Workflow de CI creado desde cero** (`.github/workflows/ci.yml`): jobs `api` + `web` +
        `edge` corren lint y tests en cada PR/push a main, en verde (criterio heredado de T-1.1).
        Los 3 jobs verificados localmente igual que correrán (api: ruff+pytest; web:
        eslint+prettier+vitest+build; edge: ruff+format+pytest con `GPIOZERO_PIN_FACTORY=mock`).
  - [x] `pytest` verde en CI (job `edge`) sin hardware físico (60 tests; gpiozero MockFactory).
  - [x] Simuladores permiten levantar el edge completo en dev sin Raspberry Shake ni Pi 4
        (verificado por el entry point real `uv run takab-edge`: 11 módulos arrancan en orden
        topológico, transmiten y paran limpio).

### [x] T-1.3 · `gpio` — WR-1 (contacto seco) → relés locales — **[A4]** · COMPLETA
- **Componente:** edge · **Depende de:** T-1.2 · **Prioridad: ALTA**
- **Criterios:** cierre del contacto → reflejo SASMEX→sirena **in-process** en <100 ms (medido);
  debounce 50 ms; botón silencio y botón prueba; fail-safe NO/NC configurable por canal;
  1000 ciclos sin fallo; proceso mínimo, sin deps pesadas, arranca <1 s.
  `[RATIFICADO 2026-07-09 · T-1.45 · gate #6]` módulo consolidado (entrada + relés en un proceso).
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
  fail-safe del módulo `gpio`** `[RATIFICADO 2026-07-09 · T-1.45 · gate #4]`; adaptador
  BACnet/IP detrás de la misma interfaz para la secuencia extendida (cierre de válvulas de gas +
  retorno de ascensores/montacargas + liberación de retenedores de puerta), activable por
  contrato; cada acción con ACK de ejecución y timestamp (`T+0.42s`, etc.); mock de simulación
  sin hardware BACnet real. El gate #4 quedó **ratificado** con este diseño, así que cuál es el
  driver primario ya no está en discusión (`PLAN-MAESTRO §3`).
- **Manager** (`edge/takab_edge/actuators`): enruta por contrato (`bacnet_channels`) — relé por
  defecto [RATIFICADO · gate #4], BACnet para la secuencia extendida; **sirena/estrobo SIEMPRE por relé
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
  navegador <2 s desde el edge). `[RATIFICADO 2026-07-06 · gate #5 — REST + WS nativo, SIN
  GraphQL]`: GraphQL subscriptions queda pos-MVP (**T-3.15**, y solo si un cliente lo pide);
  los endpoints de telemetría JAMÁS exponen los caggs
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

### [x] T-1.31 · App móvil (fase posterior) — **[C5] CUBIERTA POR LA FASE 2 COMPLETA** (reconciliado 2026-07-31; el marcador quedó atrás cuando la nota de reactivación ya lo decía)
- **Componente:** mobile · **Depende de:** T-1.22, T-1.26 · **Diferida — no iniciar en Fase 1.**
- **Criterios (referencia futura):** acuse, escalamiento, inspección de campo con
  checklist/fotos/firma, check-in de vida, offline-first.
> **REACTIVADA COMO FASE 2 (2026-07-15).** No se ejecuta como T-1.31: el alcance vive en
> `## Fase 2 · App móvil (T-2.00…T-2.14)` al final de este documento, con spec canónica
> `takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md`. Sus criterios de referencia quedan
> cubiertos por T-2.05/T-2.06 (crisis + check-in), T-2.10 (inspección de campo con
> checklist/fotos/firma) y T-2.06/T-2.11 (offline-first).

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
> incidente. **Confirmación en HARDWARE real (Pi 4 `gw-dev-0001`)**: corte de WAN reversible
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

### [x] T-1.37 · Desplegar API + workers + consola en el EC2 — **[B7] COMPLETA · aplicada en la ventana de T-1.39**
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
  - [x] **`terraform apply` + `make cloud-deploy` ejecutados contra AWS** (2026-07-09, ventana
        de T-1.39: instancia en t4g.medium, EIP `16.58.11.196`, stack completo desplegado).

> **APLICADA (2026-07-09), en la ventana de T-1.39.** El texto de abajo es el registro de la
> verificación *previa* al apply, cuando la tarea todavía estaba en `[~]`; se conserva porque
> documenta cómo se validó el stack sin tocar AWS. La nube lleva viva desde entonces.
>
> **Verificación previa, sin tocar AWS:** `terraform validate` + `fmt` OK, el
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

> Cierra TODO lo documentado como abierto que se puede cerrar con los accesos reales (Pi 4,
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

### [x] T-1.39 · Desplegar la nube al EC2 (ejecución) — **COMPLETADA (2026-07-09)**
- **Componente:** infra + deploy · **Ejecuta:** el pendiente de T-1.37 con los fixes de T-1.38
- **Resultado:** la nube corre EN LA NUBE. `https://16-58-11-196.sslip.io` con TLS real de
  Let's Encrypt (HTTP/2), consola servida, `/api/health` ok, `/dev/token` ausente (404), auth
  exigida (401). Migraciones a head `0010`, flota sembrada (5 gateways), ingesta consumiendo
  con lag ~50 ms, colas en 0, DLQs estables. Los 3 workers ad-hoc del smoke del 07-08
  (imagen `t125` — eran ELLOS quienes "vaciaban" las colas) quedaron retirados.
- **Lo que el primer deploy real destapó (todo corregido y committeado):**
  - El shorthand `--parameters commands="[json]"` del AWS CLI NO decodifica `\n` ⇒ el script
    SSM llegaba roto. Ahora va como JSON completo vía `file://`.
  - El repo ECR `takab/console` nunca existió ⇒ creado + importado al estado.
  - Las imágenes se construían en la arquitectura del host ⇒ `make cloud-images` ahora es
    `--platform linux/arm64` SIEMPRE (el EC2 es Graviton), con la etapa node de la consola en
    `$BUILDPLATFORM` (dist/ no tiene arquitectura) y `set -e` (un build roto ya no sigue al push).
  - El apply externo arrancó el SG web de la ENI (flapping `aws_network_interface_sg_attachment`
    vs `vpc_security_group_ids`) ⇒ re-adjuntado + `ignore_changes` (patrón del provider).
- **Pendiente diferido:** prueba de sirena viva `pending→acked` — el gabinete real corre con
  `command_enabled=False` (decisión del dueño); se ejerce en la sesión del WR-1 (T-1.42).

### [x] T-1.40 · Salud honesta del edge — **[B4/C7] COMPLETADA Y EN PRODUCCIÓN (2026-07-09)**
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
  - [x] **Desplegado y verificado EN LA NUBE** (heartbeat real en `device_health`:
        `ntp_offset_ms=-0.216` medido, `mqtt_rtt_ms=77.2` del PUBACK, `power_status=unknown`
        con `battery_pct=NULL` (no hay UPS y SE DICE), `cert=8575d` — el real de 2049).

> **El deploy al Pi destapó una trampa del camino de vida:** lgpio crea su FIFO `.lgd-nfy*`
> en el CWD; con `ProtectSystem=strict` y `WorkingDirectory=/opt/takab/edge` (solo lectura)
> `LGPIOFactory` fallaba al instanciarse y gpiozero caía EN SILENCIO al backend `native`
> (sysfs), que en Pi 4 muere con EINVAL ⇒ **crash-loop del supervisor**. Nunca se había visto
> porque el proceso llevaba vivo desde ANTES del endurecimiento: este fue el primer restart
> real bajo strict. Reproducido y validado con `systemd-run`; fix: `WorkingDirectory=
> /var/lib/takab` en ambas unidades (takab-gpio además carecía de `ReadWritePaths`). Segunda
> trampa: `uv sync --extra hardware` a secas PODA el extra `aws` (awsiotsdk/awscrt) — el
> primer sync lo dejó a medio borrar y el gabinete quedó offline spooleando; el deploy ahora
> sincroniza AMBOS extras y se apropia del venv (el servicio root deja `__pycache__` que
> rompía el sync del usuario). El spool (614 mensajes) drenó al reconectar: cero pérdida.

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

### [x] T-1.43 · PIN en el panel local del gabinete — **[B8] COMPLETA · desplegada y verificada en el gabinete real**
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
  - [x] Desplegado al Pi y verificado EN EL GABINETE REAL: GET 200 abierto; POST sin PIN 401,
        PIN erróneo 401, PIN correcto 200. El PIN quedó en `/etc/takab/edge.env` (entregado a
        Mauricio por el canal de la sesión).

### [x] T-1.41 · Calibración física de AM.R4F74 — **COMPLETADA (2026-07-09) · salda T-1.6**
- **Componente:** edge (env) + db + docs
- **Criterios de aceptación:**
  - [x] Sensibilidades REALES en `/etc/takab/edge.env` del Pi (del StationXML FDSN, Scale
        constante en todas las épocas): `VEL=2.5021894e-9 (m/s)/count` (EHZ 399 650 000 M/S) y
        `ACCEL=2.6007802e-6 (m/s²)/count` (EN* 384 500 M/S²). Aplicadas por APPEND idempotente
        — jamás re-corriendo provision (que SOBREESCRIBE edge.env).
  - [x] `sensors.calibration_source` declarado para R4F74 con fuente citable y la caveat de
        honestidad («sensibilidad plana @5 Hz, sin deconvolución de respuesta completa»),
        vía el DSN `takab_app` (RLS forzada) + el escritor canónico de auditoría
        (`audit_log`: `sensor_update` + `site_update` por `system:t141-calibracion`).
  - [x] Coordenadas REALES del sitio (época FDSN vigente 2026-07-05→): 19.0450, −98.1522
        (antes: centro aproximado de Puebla).
  - [x] **Validación física:** con el edificio en reposo, los canales MEMS reportan
        0.6–1.1 mg — exactamente el piso de ruido esperado del RS4D. La consola muestra
        `g`/`cm/s` SIN el badge «SIN CALIBRAR» para el sitio real; los SIM siguen sin calibrar
        (que es la verdad).
  - [x] **Prueba de excitación EJECUTADA con movimiento real** (Mauricio movió el Shake,
        2026-07-10 03:14–03:31 UTC): pico de **PGA 0.567 g en ENZ** (0.30 ENN / 0.26 ENE),
        STA/LTA saturado en 10.0 (umbral 3.5). El camino determinista completo disparó:
        tier → `evacuate_or_hold`, secuencia de actuación entera (`siren/strobe/gas_valve/
        elevator/door_retainer activate vía relay T+0.00s`, sin nube ni IA), desescalada
        limpia a `normal` al cesar el movimiento, y **4 incidentes `local_threshold`
        critical en la nube** con la cadena de acks de compliance completa
        (`incident_actions` por `edge:gw-dev-0001`). Los valores en reposo (0.6–1.1 mg) y
        en excitación (0.57 g) son físicamente coherentes: calibración VALIDADA.

> **CORRECCIÓN (confirmada por Mauricio):** el incidente `trigger=sasmex` de las 03:17 UTC
> NO fue espurio — fue su prueba DELIBERADA con un botón físico en los puertos GPIO donde
> irá el radio SASMEX. Ver T-1.42: esa pulsación validó la entrada física completa.

### [~] T-1.42 · Semántica real del WR-1 — **RADIO INSTALADO Y REFLEJO PROBADO 2× (6.65 ms hito 2026-07-14 · 4.16 ms en frío 2026-07-31); queda OBSERVAR la semántica en una transmisión REAL de CIRES + gate #3 del relé físico**
> **Reconciliación (2026-07-31):** la activación manual del WR-1 en sitio produjo 3 cierres en
> 2.5 s (4.16/0.11/0.19 ms de reflejo) — prueba el camino eléctrico, pero NO responde la
> semántica del contacto durante un broadcast real (¿sostenido o pulsos?): el Relevador 1
> (multi-riesgo) no está conectado a propósito, así que la prueba periódica de CIRES no cierra
> el Relevador 2 — solo una alerta real lo mostrará. Los 3 puntos abiertos de abajo siguen
> vigentes; el "falta el radio" del encabezado viejo ya no era verdad.
- **Componente:** edge + hardware · **Avanza:** gate #3 (parte software/entrada)
- **Lo VALIDADO con el botón físico de Mauricio en GPIO16/GND (2026-07-10 03:17 UTC,
  7 pulsaciones medidas del journal):**
  - [x] Cableado y polaridad confirmados: BCM16 (pin 36) con pull-up, activo-bajo, retorno
        a GND (pin 34). Cada cierre real registró EXACTAMENTE una activación.
  - [x] **Reflejo SASMEX→sirena in-process: 0.10–0.33 ms medidos** — el presupuesto del
        gate #3 es <100 ms; la parte software queda 300× por debajo (la latencia del RELÉ
        físico sigue pendiente de hardware).
  - [x] Debounce de 50 ms: pulsaciones humanas (~100–420 ms de cierre) pasan limpias, sin
        dobles disparos.
  - [x] E2E completo del canal primario: cierre → `tier normal → evacuate_or_hold (alerta
        SASMEX (WR-1) — canal primario)` → secuencia de actuación → **incidente
        `trigger=sasmex` en la nube** → desescalada al abrir el contacto.
  - [x] Bonus (sacudida 03:19): confirmación multi-sensor instrumental observada en vivo —
        `restricted (1 sensor)` → `evacuate_or_hold (confirmado por 2: ENE+ENN)`.
- **Lo que QUEDA (necesita el radio WR-1 real):**
  - [ ] Semántica del contacto del RADIO: ¿cierre sostenido durante toda la alerta o pulso?
        ¿separa alerta de prueba periódica CIRES? ¿duración típica?
  - [ ] **Decisión de diseño que la prueba destapó:** hoy el tier SIGUE AL NIVEL del
        contacto y desescala ~0.2 s después de abrirse. Con un cierre sostenido del WR-1
        eso es correcto; si el radio PULSA, haría falta retención mínima (latch temporal)
        del `evacuate_or_hold` — decidir con la semántica real medida.
  - [ ] Gate #3 físico: latencia contacto→RELÉ→sirena real <100 ms (necesita relés).

### [x] T-1.46 · Validación del quórum contra el catálogo oficial — **[C·G1] COMPLETADA (2026-07-09)**
- **Componente:** api (tools+tests) + docs · **Cierra:** pregunta abierta #2 de `ANALISIS §4`
- **Objetivo:** v_P=6.5 km/s, margen=3 s y tope=30 s se fijaron "de memoria". Contrastarlos con
  el catálogo OFICIAL antes de cualquier calibración de producción.
- **Criterios de aceptación:**
  - [x] Catálogo v2 (`tests/incident/fixtures/ssn_catalog.json`): 13 sismos reales con
        **procedencia por evento** — 5 con valores oficiales transcritos de Reportes Especiales
        del SSN (19S, Tehuantepec, Crucecita, Acapulco, Michoacán-22), 8 con solución USGS FDSN
        (el SSN no expone API ni reportes pre-2010), 5 intraslab bajo Puebla de 48–80 km.
  - [x] **Gemelos SSN/USGS** del 19S y Tehuantepec (difieren 28–36 km): el quórum asocia bajo
        AMBAS soluciones ⇒ robusto a la incertidumbre de localización entre catálogos.
  - [x] Barrido de velocidad de primer arribo 5.5/6.0/6.5/8.0 km/s: **13/13 sismos con quórum
        en todo el barrido** (la herramienta reusa `quorum.correlate` real, no re-implementa).
  - [x] Banda de la pregunta (≤110 km): TODA estación asocia incluso a Pg=5.5 (peor holgura
        +0.27 s). Limitación honesta documentada para pares >110 km (margen 4–5 s vía
        `rule_sets.config.quorum` si se quiere asociación por-estación garantizada).
  - [x] La estación real AM.R4F74 (coordenada FDSN exacta) entra en la geometría.
  - [x] Regresión anclada: barrido + banda ≤110 km + procedencia obligatoria (12 tests).
  - [x] Anexo `ANALISIS-ARQUITECTURA-TAKAB.md §4-bis` con metodología, números y veredicto;
        la pregunta #2 queda marcada **[RESUELTA]**. **Parámetros RATIFICADOS, sin cambios.**

### [x] T-1.45 · Higiene y reconciliación documental — **COMPLETADA (2026-07-09)**
- **Componente:** db + api(tests) + docs · **Cierra:** #25, #26, #45 y supuestos #4/#6/roles
- **Criterios de aceptación:**
  - [x] **`db/schema.sql` reconciliado a CERO drift** contra `alembic upgrade head` (diff
        sistemático de catálogos sobre DBs gemelas: columnas, índices, constraints y políticas
        RLS). Faltaban 4 tablas completas de la era 0005–0007 (`commands`,
        `gateway_config_state`, `notification_jobs`, `billing_meters_daily`) con sus RLS/GRANTs
        y 2 índices únicos de idempotencia — transcritos fieles de pg_dump.
  - [x] **Anti-drift downlink (#25):** `tests/contracts/test_downlink_contracts.py` construye
        los sobres `command`/`config_update`/`backfill_grant` EXACTAMENTE como los emite el
        código real de la nube y los valida contra los schemas publicados (que eran artesanales
        y nada pinneaba). Incluye el negativo: sin firma NO valida.
  - [x] **Artefactos de diseño (#45):** `SOC Console.html`, `SOC*.css`, `jsx/`,
        `design-system/` y `Design System/` movidos de la raíz a `takab-docs/design/` (56
        renames; README de procedencia; el `.zip` interno sigue en `.gitignore`).
  - [x] **Ratificaciones (PLAN-MAESTRO §3):** SUPUESTO **#4** (relés fail-safe primario) y
        **#6** (proceso gpio consolidado) pasan a RATIFICADOS — implementados de facto y
        acreditados en el hito; la nota **10-vs-11 roles** queda resuelta en 10 (las
        identidades máquina no son roles RBAC). El soft-gate #2 queda CERRADO por T-1.46.
  - [x] El patrón #28 (hilo del heartbeat muere por I/O) quedó cerrado en T-1.40 (`_safe()` +
        try/except del loop) — verificado ahí, no re-trabajado aquí.
  - [x] **Diferidos que exigen terceros (documentados, no fingidos):** WhatsApp/SMS reales
        (Meta Business/agregador), SES fuera de sandbox (dominio+DKIM/SPF), billing por
        EventBridge→ECS (no hay ECS), app móvil T-1.31, CCTV ONVIF, endpoint de lectura de
        `audit_log`, `self_test` de gabinete, relés/latencia física del gate #3.

---

## Fase 1.7 · Pulido SOC con datos reales + panel local del inmueble

> Origen: revisión de las 4 pantallas desplegadas (`takab-docs/design/vistas_v1/*.png`, 2026-07-10) contra el
> design system (`takab-docs/design/`). Diagnóstico y plan completo en la sesión del
> 2026-07-10. Decisiones ratificadas por Mauricio: (1) la vista del inmueble es el PANEL
> LOCAL del Pi (no una vista cloud con rol nuevo); (2) purga TOTAL del entorno desplegado
> (flota sim + TODOS los incidentes de prueba, incluidos los del botón WR-1) con arranque
> limpio del historial; `audit_log` se conserva íntegro.
>
> **Verificación local ANTES del deploy: `make soc-local`** — DB sembrada + API con
> `/dev/token` (JWKS de dev por `api/scripts/dev_auth_env.py`, gitignored) + worker de
> incidentes/dictamen + web (:5173) + UN gabinete real simulado con la identidad de la
> flota (gw-dev-0001; panel LAN en :8080) y bridge al Postgres local. Estímulos:
> `curl -X POST :9100/quake | /sasmex | /sasmex/clear | /wan/off`. Verificado E2E el
> 2026-07-10: quake → incidente crítico → backfill PGA 0.0848 g → dictamen basis v2
> (`pga_source=features`) → reubicar epicentro (EVT-MAN determinista) → dictamen-request
> 201/409 → panel LAN con 4 canales vivos y silencio por LAN.

### [x] T-1.47 · Datos reales: split de seeds, rule_set v1 y runbook de purga — **COMPLETA (código 2026-07-10; purga en la DB VIVA verificada el 2026-08-04, cerrada por T-2.57)**
- **Componente:** db + demo + deploy · **Depende de:** —
- **Objetivo:** que el entorno desplegado contenga SOLO la estación real y que ningún deploy
  futuro pueda resucitar datos sim; runbook seguro para purgar lo existente.
- **Criterios de aceptación:**
  - [x] `db/seeds/dev_fleet.sql` PARTIDO: `prod_fleet.sql` (tenant + site-dev + gw-dev-0001 +
        R4F74 con `calibration_source='stationxml:AM.R4F74'` + **rule_set v1** scope tenant,
        espejo exacto de los defaults de Settings, **sin clave `edge`** ⇒ el worker de sync
        firmada no publica nada al gabinete) y `sim_fleet.sql` (20 sitios/4 gateways/20
        sensores, EXCLUSIVO local).
  - [x] `make demo-db` aplica prod+sim (verificado: 20 sitios sim restaurados); el deploy
        (`deploy/cloud/deploy.sh`) embebe y aplica SOLO `prod_fleet.sql`.
  - [x] Guardia anti-TRUNCATE-remoto en `demo/run.py reset_state()` (`RuntimeError` si el host
        no es loopback/socket) + `demo/tests/test_reset_guard.py` (8 tests) colectados por la
        suite del api (`testpaths += ../demo/tests`).
  - [x] Runbook `db/maintenance/2026-07-10_purge_sim_fleet_and_test_incidents.sql` + README:
        transacción única superusuario con `session_replication_role=replica` (triggers
        append-only incluidos los chunks de hypertables + sin tormenta NOTIFY), guardia
        anti-flota-real, conteos y checks de orfandad embebidos, refresh de caggs + VACUUM
        post-commit, backup `pg_dump` + CSV de llaves S3 obligatorios ANTES.
  - [x] **Ensayado contra la DB local**: purga aplicada (flota sim fuera, fixtures ajenos
        intactos), re-run = 21×`DELETE 0` (idempotente), `make demo-db` restaura.
  - [x] Suite api verde tras el split (670 passed, 3 skipped) · ruff limpio.
  - [x] **Ejecución real en la DB VIVA (2026-08-04).** La cerró **T-2.57** (`:3640-3642`),
        que declara textualmente "**Cierra T-1.47**": los `site-sim-*` activos quedaron
        **retirados** con sus gabinetes propagados y auditados, y se midió
        `site-sim activos = 0`, `gabinetes fantasma = 0`. El camino real no fue el runbook de
        borrado sino el **retiro administrativo** que T-2.35 añadió después de escribir esta
        tarea — el efecto verificado es el mismo y deja rastro en `audit_log`, que para la
        regla de oro 11 es mejor que un `DELETE`. La estación de pruebas (`site-dev` +
        `gw-dev-0001`) se recuperó en la misma sesión.
- **Nota de reconciliación (2026-08-05, T-2.61):** esta tarea estuvo `[~]` cuatro días DESPUÉS
  de que T-2.57 la declarara cerrada con evidencia medida. La cabecera de T-1.47 seguía
  diciendo "los 20 `site-sim-*` SIGUEN en la DB viva" mientras la tarea que los retiró contaba
  6 y los daba en cero. Ese cruce lo vigila ahora
  `api/tests/test_docs_consistency.py::test_una_tarea_hecha_no_puede_cerrar_una_tarea_abierta`.

### [x] T-1.48 · API: migración 0011, endpoints de operador y dictamen con datos — **COMPLETADA (2026-07-10)**
- **Componente:** api + db + shared/sdk-ts · **Depende de:** — (paralelo a T-1.47)
- **Criterios de aceptación:**
  - [x] Migración `0011_soc_polish` + `db/schema.sql` a CERO drift: `app_user_id()`,
        `user_profiles` (RLS FORCE, self-write; gov edita SU nombre — excepción documentada),
        `reference_earthquakes` (global, solo lectura autenticada, sin escritura vía API),
        `relocate_incident_epicenter()` SECURITY DEFINER dueña takab_ingest (precedente
        `gov_ack_incident`; parámetros de retorno `r_*` anti-ambigüedad plpgsql).
        `upgrade head` + `downgrade -1` verificados.
  - [x] Endpoints: `GET/PUT /me/profile` (GET /me intacto, sin DB; normaliza espacios; 422
        vacío/>80; auditado); `POST /incidents/{id}/epicenter` (con evento → UPDATE epicenter
        + `meta.manual_override` con el punto previo; sin evento → `EVT-MAN-<md5[:8]>`
        determinista source='manual' magnitude NULL y linkea; re-POST no duplica) + acción
        `epicenter_relocate` en timeline + audit; `POST /incidents/{id}/dictamen-request`
        (201 IncidentActionOut, **409** con solicitud pendiente sin dictamen firmado
        posterior, re-solicitable tras la firma); `GET /catalog/earthquakes` (13 sismos
        SSN/USGS en `db/seeds/reference_earthquakes.sql`, transcripción fiel del catálogo
        ratificado T-1.46; sembrado por demo-db y deploy.sh).
  - [x] Matriz: `relocate_epicenter` y `request_dictamen` = superadmin/tenant_admin/
        soc_operator (gov e inspector fuera — anclado por tests; divergencia documentada en
        `RBAC-TAKAB.md §2 [DECISION 2026-07-10]`); `MeActions` +2 campos; espejo
        `web/src/test-utils/meFixtures.ts` sincronizado en el mismo commit.
  - [x] Dictamen con datos: ventana asimétrica (`dictamen_pga_window_pre_s=5` /
        `post_s=180` — la sacudida SASMEX llega DESPUÉS de la alerta y el ±5 s la perdía);
        **backfill monotónico** de `incidents.max_pga_g/max_pgv_cms` (GREATEST por campo,
        jamás 0 fabricado sobre NULL, UPDATE solo si mejora ⇒ sin spam NOTIFY; aplica
        incluso con cabeza firmada — la telemetría es un hecho, el juicio no se toca);
        basis v2 aditivo: `evidence.pga_source ∈ {features,incident,none}` +
        `evidence.insufficient_data`. El mapeo determinista del veredicto NO cambió
        (tests previos de rules intactos).
  - [x] OpenAPI exportado + SDK TS regenerado UNA vez (`tsc --noEmit` limpio; web 448 tests
        verdes con el SDK nuevo); **pytest api: 723 passed** (baseline 670 + 53 nuevos:
        14 de migración, 7 de dictamen, 8 perfil, 7 epicentro, 6 dictamen-request, 5
        catálogo, 2 matriz, ajustes); ruff limpio.
> **ESTADO.** El worker de incidentes gana el backfill sin tocar su ciclo; el contract-test
> del single-writer de audit_log sigue en verde (la función definer NO audita — audita el
> router). Los frames WS de reubicación/solicitud salen gratis por los triggers NOTIFY de 0004.

### [x] T-1.49 · Web: socket compartido, topbar viva y perfil de operador — **COMPLETADA (2026-07-10)**
- **Componente:** web · **Depende de:** T-1.48 (solo `/me/profile`)
- **Criterios de aceptación:**
  - [x] `web/src/live/`: `LiveSocketProvider` a nivel AppShell (conecta SOLO con idToken,
        cierra al perder sesión, idempotente en StrictMode; `LiveSocketFactoryContext`
        inyectable para tests) + `liveHealth.store` zustand (UNA suscripción a `site_state`
        → último heartbeat de device_health por gateway con hora de LLEGADA local;
        `edgeMqttView()` pura con staleness 90 s y peor-RTT multi-gabinete);
        `features/console/socket.ts` quedó como re-export — ningún hook consumidor cambió.
  - [x] Topbar viva en TODAS las páginas (también /fleet y /triage, que no tenían WS):
        `● CONECTADO/CONECTANDO…/DESCONECTADO` (icono+label, tokens semánticos) y
        `EDGE · MQTT x.xx ms` del último heartbeat o `· S/D` si stale/ausente — un heartbeat
        fresco SIN rtt medido también es S/D, jamás un 0 inventado.
  - [x] `OperatorMenu`: `display_name ?? role` (fallback honesto), edición inline con
        normalización de espacios (PUT /me/profile vía `useProfile`/`useProfileMutation`,
        caché compartido por query key), caption `role · sub8`, logout dentro del menú,
        error con `role=alert`. El pie de IncidentTable muestra el nombre (misma query).
        (El `applyMe()` planeado se volvió innecesario: el perfil vive en TanStack Query,
        no en el session store.)
  - [x] ConsolePage/BuildingPage consumen el socket del shell (dejaron de poseer el suyo);
        `renderRoutesAt` inyecta `FakeLiveSocket` por la factory (cero WebSocket reales en
        jsdom) y lo devuelve para emitir frames en tests de rutas.
  - [x] **Suite web: 467 passed** (448 + 19 nuevos: store 8, provider 4, OperatorMenu 6,
        Topbar reescrito) · tsc/eslint/prettier limpios · `vite build` OK.

### [x] T-1.50 · Web: Consola C4I completa (mapa, BMS, relés, CCTV, detalle) — **COMPLETADA (2026-07-10)**
- **Componente:** web · **Depende de:** T-1.49 (orden de merge del CSS)
- **Criterios de aceptación:**
  - [x] **Fix de layout que destraba el mapa** (causa raíz del "no hay mapa"): `StateFrame`
        con prop `className` aplicada en LOS 4 estados; la consola opta por `.soc-wall`
        (grid `minmax(0,1fr) auto` dentro del wrapper); `.soc-stateframe` base pierde
        `height:100%`; `.soc-stage{min-height:280px}` de cinturón; contrato DOM
        anti-regresión (`.soc-stateframe.soc-wall` + `.soc-stage`) — jsdom no hace layout
        y 448 tests jamás vieron el colapso.
  - [x] Mapa robusto: estilo remoto irrecuperable (solo si el inicial NUNCA cargó; un tile
        suelto mid-sesión no borra el mapa base) ⇒ `setStyle(FALLBACK_STYLE)` 100 % local
        (las capas GeoJSON de sitios SIGUEN pintando) + badge "◐ SIN MAPA BASE · SITIOS EN
        VIVO"; `style.load` re-cuelga capas (guard anti doble-add) y el pulso rAF lleva
        guard de capa; `observeMapResize` compartido (`lib/maplibre.ts`) + stub de
        ResizeObserver en vitest.setup.
  - [x] BMS agrupado por canal (último estado + hora + ×N, orden por recencia, expandible
        con aria-expanded a la traza completa auditada) — `features/console/bms.ts` puro;
        kinds desconocidos degradan sin reventar.
  - [x] Card INCIDENTE en el detalle: trigger etiquetado (SASMEX/UMBRAL LOCAL EDGE/QUÓRUM
        CLOUD/MANUAL), evento o "SIN EVENTO SÍSMICO ASOCIADO", estado+edad, PGA/PGV máx
        ("—" honesto), último acuse con actor. SIN magnitud NI countdown (anclado por test).
  - [x] Card RELÉS DEL GABINETE vía `useSiteRelays` (MISMAS queryKeys que useFleet ⇒ caché
        compartida, cero fetches extra) con estados honestos; CCTV SIEMPRE visible con
        empty-state "SIN CÁMARA CONFIGURADA · PENDIENTE DE HARDWARE"; PGA de tabla:
        `formatPga` — `<0.001g` para picos reales diminutos, `0.000g` solo si es cero MEDIDO.
> **ESTADO.** web 488 passed (+21) · tsc/eslint/prettier/build OK. Smoke visual de las 5
> páginas queda amarrado al deploy de cierre de fase (checklist del runbook).

### [x] T-1.51 · Web: botones del operador vivos (epicentro + dictamen) — **COMPLETADA (2026-07-10)**
- **Componente:** web · **Depende de:** T-1.48 (SDK) + T-1.50
- **Criterios de aceptación:**
  - [x] `components/Modal.tsx` accesible (role=dialog, aria-modal, Esc, foco inicial) —
        primer modal real del árbol — + `EpicenterModal` que REUTILIZA `MapPointPicker`
        (marcador arrastrable + clic para colocar + lat,lon manual); con evento linkeado
        inicia en su epicentro actual y anuncia "EL PUNTO PREVIO QUEDA AUDITADO"; sin
        evento avisa "SE CREARÁ UN EVENTO source=manual (SIN MAGNITUD)"; confirmación en
        dos pasos (ConfirmButton); error inline `role=alert` con el modal abierto;
        invalidaciones de incidents/mapState/events/event/actions (`useEpicenter`).
  - [x] SOLICITAR DICTAMEN TÉCNICO: two-step en el footer → POST dictamen-request →
        `navigate("/triage?incident=<id>")`; el 409 ("solicitud pendiente") se muestra tal
        cual; TriagePage preselecciona por query param UNA vez (aviso honesto "EL INCIDENTE
        SOLICITADO NO ESTÁ EN LA PÁGINA CARGADA" si el keyset de 50 no lo trae).
  - [x] Gates por `me.allowed_actions.relocate_epicenter/request_dictamen` (matriz
        server-driven, jamás roles hardcodeados); deshabilitados llevan `title` explicativo
        ("tu rol no tiene esta acción" / "selecciona un incidente").
> **ESTADO.** web 504 passed (+16: Modal 3, EpicenterModal 5, IncidentTable +4, ConsolePage
> flujo dictamen 1, TriagePage deep-link 3) · tsc/eslint/prettier/build OK. TriagePage y
> ConsolePage ahora usan hooks de router: sus tests montan MemoryRouter.

### [x] T-1.52 · Web: Triage con catálogo de referencia y tiles reales — **COMPLETADA (2026-07-10)**
- **Componente:** web · **Depende de:** T-1.48 (SDK)
- **Criterios de aceptación:**
  - [x] `CatalogPanel` bajo el historial (colapsable, colapsado por defecto): "CATÁLOGO DE
        REFERENCIA · SSN/USGS" + badge REFERENCIA + sub "NO SON INCIDENTES DEL TENANT";
        fila con M/fecha UTC/profundidad/epicentro/fuente (el `source_ref` completo va en
        el title); sin SevTag ni estados de incidente — no se disfraza; StateFrame propio
        (si falla no tumba el historial, vacío = instrucción de seed); staleTime 24 h.
        (La magnitud es dato ratificado de catálogo histórico, NO preliminar — §14 intacto.)
  - [x] `TriageDetail`: tiles PGA/PGV/DURACIÓN/PROFUNDIDAD/NODOS + QuorumNodes + evidencia
        + EXPORTAR miniSEED movidos FUERA del gate del dictamen (los hechos del incidente
        no dependen de que exista dictamen; antes un incidente sin dictamen parecía "sin
        datos"); DICTAMEN PDF ahora exige un dictamen que imprimir (title honesto); tile
        DURACIÓN = `durationOf` rotulada "DURACIÓN DEL INCIDENTE" ("EN CURSO" si abierto —
        jamás un fin inventado); rotulado basis v2: `insufficientData(head)` ⇒ "SIN
        EVIDENCIA INSTRUMENTAL — DICTAMEN POR SEVERIDAD DE ALERTA" (claves pre-v2 ⇒ false).
> **ESTADO.** web 514 passed (+10: CatalogPanel 4, useCatalog 2, model durationOf/
> insufficientData 2, TriagePage hechos/basis 2) · tsc/eslint/prettier/build OK.

### [x] T-1.53 · Edge: mini-consola local del inmueble (panel LAN del Pi) — **VERIFICADA EN EL PI REAL CON CRECES (reconciliado 2026-07-31: recorrido de navegador 44/44 + operador en sitio) y SUPERSEDIDA por la reescritura de T-2.23 (Fase 2.1)**
- **Componente:** edge (+1 docstring api) · **Depende de:** — (independiente)
- **Criterios de aceptación:**
  - [x] **Fix del bug latente**: `HealthMonitor` cachea `last_snapshot` (propiedad SIN side
        effects) y el panel NUNCA llama `snapshot()` — antes cada GET `/api/status` lanzaba
        las sondas (subprocesos chronyc/upsc/openssl) y PUBLICABA un health a la nube
        (~30/min con el poll de 2 s en vez del heartbeat de 60 s). Regresión anclada:
        `test_status_does_not_publish_health` (10 GETs ⇒ 0 publicaciones).
  - [x] `signal.live_by_channel()` (Feature1s + hora de LLEGADA por canal, bajo lock —
        window_start es reloj del Shake y no sirve para staleness; copia defensiva);
        ring de transiciones en `RuleEngine._emit` (deque 32 + lock — dos hilos escriben:
        seedlink y callback gpio; fuentes instrumental Y sasmex, con PGA solo si es
        medición); deque de acciones LAN (`silence/siren_test/reset · via lan`).
  - [x] Sonda de disco `disk_used_pct` (shutil.disk_usage sobre `health_disk_path`, None
        si falla; probes pre-T-1.53 sin el método degradan a «sin dato» vía getattr) →
        `HealthSnapshot` + schemas compartidos **1.2.0** (ADITIVO, changelog en schemas.py;
        el ingest de la nube lo ignora — docstring actualizado; suite api 723 sigue verde);
        anti-drift verde; el wheel de hatchling INCLUYE `local_api/index.html` (verificado).
  - [x] `status()` por secciones DEFENSIVAS (módulo roto ⇒ sección null y GET 200 — anclado
        por test con `last_decision`/`last_snapshot` reventando): identidad VIVA desde
        settings, now/site_name/uptime/refresh_ms, `signal` por canal con age_s y
        stale_after_s=5, `health` del cache con edad declarada, `cloud`
        {online, mqtt_rtt_ms, queued} y `events` (transiciones+acciones, desc, cap 10).
  - [x] `index.html` como recurso empaquetado (importlib.resources, cargado 1 vez, fallback
        honesto si falta; cero build, CERO recursos externos — test lo veta junto con
        countdown/T-MINUS §14): kiosk una página con tokens TAKAB en hex, pills de enlace
        nube ("SIN ENLACE — PROTECCIÓN LOCAL ACTIVA · N EN COLA") y conexión del panel
        (EN VIVO/DATO RETENIDO/SIN CONEXIÓN), tier hero clamp(40px,9vw,72px) con
        icono+label, PGA mono 4 decimales por canal + chip CLIP + "SIN SEÑAL DEL SENSOR"
        si todo está stale, relés + 3 acciones con PIN (flujo T-1.43 INTACTO — su suite es
        el guardián), salud con S/D y umbrales ámbar (cert <30 d, disco >90 %), eventos
        "DESDE EL ARRANQUE · uptime"; banner "ALERTA SÍSMICA · PROTÉJASE"; polling
        setTimeout ENCADENADO con backoff 1→2→5 s (SSE rechazado: un stream retiene un
        hilo por kiosco en ThreadingHTTPServer y no aporta a 1 Hz); keep-alive HTTP/1.1.
  - [x] Settings nuevos (`site_name`, `local_api_refresh_ms` >249, `health_disk_path`) con
        defaults anclados por test; supervisor pasa signal/cloud/gateway_id/site_name/
        refresh al panel (verificado por comportamiento); **suite edge: 273 passed**
        (256 + 17 nuevos) · ruff limpio.
  - [ ] **Verificación en el Pi real** (con Mauricio, en el cierre de fase): deploy
        (`ssh takab-pi5`: git pull + `uv sync --extra hardware --extra aws` + restart +
        `TAKAB_EDGE_SITE_NAME="Sitio Dev Puebla"` en edge.env) → `curl /api/status | jq`
        (4 canales con PGA ~piso MEMS, disco numérico, nube true) → navegador LAN: PGA
        ~1 Hz; desconectar el Shake ⇒ "SIN SEÑAL" ≤5 s; `systemctl stop/start` ⇒
        auto-recuperación; POST sin PIN = 401/403; con el panel abierto 60 s ⇒ ≤2
        publicaciones en takab/health; DevTools sin requests fuera de la LAN.

### [x] T-1.54 · Web: Flota sin solapes + Multi-Tenant editable — **COMPLETADA (2026-07-10)**
- **Componente:** web · **Depende de:** T-1.50 (mismo cambio CSS base)
- **Criterios de aceptación:**
  - [x] `.fleet{overflow-y:auto}` (la página scrollea dentro de su fila 1fr — con 20+
        tarjetas el grid desbordaba con overflow visible ENCIMA de la tabla admin: el
        solape reportado); `.fleet__admin` y `.fleet__pickermap` con stacking context
        propio (`position:relative; isolation:isolate`); `MapPointPicker` con
        `observeMapResize` compartido (el form aparece por swap y el canvas quedaba mal
        medido); contrato DOM anti-solape con 21 gabinetes (grid ANTES de admin en el
        flujo, `.soc-wall` exclusiva de la consola); flota de 1 = KPIs 1/1/0/0 y una
        tarjeta. Verificación visual 1366×768/1920×1080 amarrada al smoke del deploy.
  - [x] TenantsPage: el empty de UMBRALES solo aplica si `!canEdit`; con `edit_thresholds`
        del tenant propio y sin rule_set ⇒ editor sembrado con defaults del edge + banner
        "SIN RULE_SET ACTIVO … AJUSTA Y PUBLICA v1" (el camino `baseVersion:null` ya
        existía, estaba enterrado tras el empty); 3 casos anclados por test (support sin
        acción = empty; admin propio = banner+editor; rule_set real = sliders con valores).
> **ESTADO.** web 518 passed (+4) · tsc/eslint/prettier/build OK.

### Diferidos de la Fase 1.7 (documentados, NO fingidos)
- **CCTV ONVIF real + conteo de personas/aforo**: requiere hardware de cámara (Profile S,
  RTSP/H.264). El conteo de personas es requisito NUEVO de Mauricio (2026-07-10; no estaba
  en el blueprint) — diseñar como módulo edge futuro + bookmark por incidente. Mientras, el
  panel CCTV de la consola es una sección honesta vacía ("SIN CÁMARA CONFIGURADA").
- **Duración instrumental de sacudida** (STA/LTA sostenido sobre features): exige calibrar
  umbral con ingeniería; hoy se muestra la duración del INCIDENTE, rotulada como tal.
- **Paginación/rango de fechas del historial de incidentes** (cursor keyset previsto en el
  endpoint; la UI migraría a useInfiniteQuery).
- **Notificación al inspector en dictamen-request** (el `kind='dictamen_request'` queda
  estable desde ya; el worker de notify puede recogerlo después).

---

## Fase 1.8 · Software de operación y costo

> Origen: plan de siguientes fases (2026-07-12) sobre el inventario de pendientes
> post-auditoría. Decisiones de Mauricio: (1) toda la Fase 1.8 es software implementable
> YA (sin hardware ni terceros); (2) el batcheo de telemetría es ESCALONADO POR TIER
> (batch ~10 s en `normal`, flush inmediato + 1 Hz en `watch`+); (3) la app móvil es
> Fase 2; (4) el hardware (bocina/DAC, cámara ONVIF, relés/sirena, radio WR-1) viene en
> camino ⇒ los gates físicos son la Fase 1.9. Orden: T-1.55 → T-1.56 → T-1.57 → T-1.58 →
> T-1.59 → T-1.61 → T-1.60 (la T-1.61, independiente, se ADELANTÓ). Migraciones:
> 0012 (T-1.57) → 0013 (T-1.59) → 0014 (T-1.61) → 0015 (T-1.60), todas idempotentes y
> reflejadas en `db/schema.sql` en el mismo commit.

### [x] T-1.55 · Tooling/CI: deudas de raíz (B-3, B-1, B-2, B-5, M-7, A-1) — **COMPLETA (2026-07-12)**
- **Componente:** tooling/CI · **Depende de:** —
- **Objetivo:** estabilizar la base de tests y hacer verdaderas dos promesas viejas
  (Playwright en el stack; regla de deploy de la auditoría).
- Criterios de aceptación:
  - [x] **B-3 (raíz):** la fixture `client` de `api/tests/_telemetry_fixtures.py` se
        renombra `telemetry_client` (+ docstring del porqué) y sus 5 importadores se
        actualizan. Verificado: `pytest tests/api` (191) y archivos sueltos pasan igual
        que la suite completa; `tests/contracts` 30 ✓; `tests/perf` colecta.
  - [x] **B-1:** `make test` corre `pytest -q -m "not perf"` (paridad exacta con ci.yml).
  - [x] **B-2:** `demo/tests` (spool + guardas de reset) corre en el job api del CI y en
        `make test` con el venv de api (22 ✓; imports = takab_api + psycopg).
  - [x] **B-5:** las 4 capturas viven en `takab-docs/design/vistas_v1/` (typo
        `Multi-Tanant`→`Multi-Tenant` corregido) y están trackeadas; referencia en este
        doc actualizada.
  - [x] **M-7:** `web/playwright.config.ts` + `web/e2e/smoke.spec.ts` committeados
        (`npm run e2e`); vitest EXCLUYE `e2e/`; tsconfig los typechequea. **Smoke verificado
        EN VIVO** contra `make soc-local`: login dev superadmin + las 5 pantallas montan su
        `data-screen-label` (1 passed, 5.8 s). Sin job de CI a propósito (stack pesado);
        mejora futura anotada: job `workflow_dispatch` no-bloqueante.
  - [x] **A-1:** `deploy/cloud/README.md` §Precondiciones exige deploy SOLO desde `main`
        pusheado con CI verde (comandos de verificación incluidos).
> **ESTADO.** api 743 passed (not perf) · demo 22 · web 525 · e2e 1 · ruff/eslint/
> prettier/tsc/build OK.

### [x] T-1.56 · Batcheo escalonado por tier de features edge→nube — **DESPLEGADO Y VIVO desde la Fase 1.8 (2026-07-13, batcheo activo con ~95 % menos SQS) y re-desplegado con los redeploys de Fase 2** (reconciliado 2026-07-31; el "despliegue pendiente" del encabezado llevaba semanas vencido)
- **Componente:** edge + api + infra · **Depende de:** — · **Decisión:** escalonado por tier
- **Objetivo:** ~97% menos publishes/SQS en reposo (hoy ~178k msgs/día del gateway real)
  sin tocar jamás la detección/actuación ni el panel LAN (1 Hz in-process).
- Diseño: módulo `FeatureBatcher` (`edge/takab_edge/telemetry/`, no-crítico,
  `depends_on=("cloud",)`); supervisor llama `telemetry.submit(feature, tier)` y
  `notify_tier()` en `_on_sasmex`; topic nuevo `takab/features/batch` (contrato
  `feature_batch` v1.3.0, 1..256 features) + regla IoT propia → misma telemetry_queue;
  `handle_feature_batch` = split idempotente en la misma transacción; settings
  `cloud_features_batch_{enabled,s,max}` (kill-switch env); cota del topic derivada
  `cap // batch_max`. Secuencia de deploy OBLIGATORIA: terraform → api → edge.
- Criterios de aceptación:
  - [x] Test ancla: 40 submits en tier normal ⇒ 1 publish batch (vs 40) —
        `test_tier_normal_40_features_un_solo_publish`.
  - [x] Escalación (features O SASMEX) ⇒ flush del acumulado ANTES del primer 1 Hz
        (orden anclado en unit + wiring); des-escalación vuelve a batchear; `stop()`
        limpio ⇒ acumulado al spool durable (test offline).
  - [x] Re-entrega del mismo batch ⇒ 0 duplicados (PK ts/sensor_id/channel); batch
        parcialmente inválido ⇒ válidas commiteadas + original a DLQ + audit
        (`handler_ran=True` ⇒ commit, semántica existente del consumer).
  - [x] La nube acepta AMBOS formatos indefinidamente (feature_1s intacto, fleet sim
        sin cambios); la ruta S3/backfill ingiere batches del spool sin tocar
        objects.py (`test_ndjson_with_batch_records_ingests_their_features`).
  - [x] Kill-switch `TAKAB_EDGE_CLOUD_FEATURES_BATCH_ENABLED=false` ⇒ camino 1 Hz
        exacto (ni el timer arranca).
  - [x] Contrato 1.3.0 aditivo regenerado (9 schemas) + anti-drift verde + loader
        con topic nuevo; regla IoT `takab_dev_features_batch` en Terraform.
  - [ ] **Despliegue** (manual, EN ORDEN): 1) `terraform apply` (regla inerte),
        2) deploy api, 3) rollout edge al Pi. Verificar en CloudWatch que
        `NumberOfMessagesSent` de `takab-dev-q-telemetry` cae de ~178k/día a <10k/día.
> **ESTADO.** api 754 (+11) · demo 22 · edge 308 (+35) · ruff limpio ambos lados.

### [x] T-1.57 · API: `GET /audit` + rango de fechas en `GET /incidents` — **COMPLETA (2026-07-12)**
- **Componente:** api + db · **Depende de:** — (SDK regenerado UNA vez aquí)
- La RLS de `audit_log` YA existía (schema.sql `audit_read`); migración 0012 = solo
  índices keyset `(ts DESC, audit_id DESC)` + `(tenant_id, ts DESC)`. Acción nueva
  `read_audit` (superadmin/support/tenant_admin/gov_operator — nota en RBAC §2;
  operadores/inspectores GENERAN auditoría, no la supervisan) + campo en `MeActions` y
  `meFixtures`. `routers/audit.py` keyset patrón exacto de `list_incidents`; filtros
  actor/verb exactos, object prefijo, from/to (`parse_range_filters` en `_common`, y
  `parse_ts` movida ahí desde telemetry con alias local). `queries/audit.py` SOLO SELECT
  (single-writer intacto). `/incidents` ganó `from`/`to` semiabierto sobre `opened_at`,
  combinable con state/severity/cursor. UI de auditoría DIFERIDA (SDK listo).
- Criterios verificados: RLS por rol (tenant propio; NULL-tenant solo internos) · 403
  sin acción · 401 sin token · keyset estable ante inserciones · cursor corrupto 400 ·
  `to<=from` 422 · rango+cursor sin huecos · 0012 down/up/re-up verificado (0→2 índices,
  re-aplicable) · drift-gates verdes con UNA regeneración.
> **ESTADO.** api 766 (+12) · web 525 (fixtures read_audit) · tsc/build/ruff limpios.

### [x] T-1.58 · Web: historial con fechas + infinite scroll, M-6, B-4, B-6 — **COMPLETA (2026-07-12)**
- **Componente:** web · **Depende de:** T-1.57 (SDK)
- Historial Triage → `useInfiniteQuery` sobre `next_cursor` (primer infinite del repo;
  cambiar un filtro reinicia la paginación por queryKey) + date-pickers `from`/`to`
  (medianoche LOCAL; `to` viaja EXCLUSIVO como día+1) + botón "CARGAR MÁS" explícito que
  desaparece sin cursor. M-6: card de relés con StateFrame 4 estados — un 500 de /fleet
  pinta error+reintento (≠ "CONFIG NO VISIBLE"); rol sin /fleet queda en empty honesto
  (error null, la query ni corre); staleness "DATOS RETENIDOS". B-4: subtítulo de
  BuildingPage con estados (SITIO NO DISPONIBLE + REINTENTAR real). B-6: manualChunks
  (maplibre ~1 MB aislado y cacheable, vendor-react; app ~275 kB) ⇒ build sin warning.
- Criterios verificados por test: loadMore anexa sin duplicar con el cursor correcto ·
  fechas → RFC3339 del server · 4 estados anclados en relés y building · build limpio.
> **ESTADO.** web 535 (+10) · tsc/eslint/prettier/build OK.

### [x] T-1.59 · `self_test` de gabinete (cierra M-2; extensión de T-1.23) — **COMPLETA (2026-07-12)**
- **Componente:** edge + api + web + db · **Depende de:** T-1.56 (SCHEMA_VERSION serial)
- Canal `system` + acción `self_test` en el MISMO envelope HMAC (schemas v1.4.0 aditivo,
  `CommandAck.results` nullable; vector `cabinet_self_test` en hmac_vectors.json —
  verificado por los tests de firma de AMBOS lados; migración 0013 = CHECKs de commands,
  down/up verificado). Matriz: superadmin/tenant_admin/building_admin (mismo círculo que
  siren_test, anclado; soc_operator DENEGADO — nota en RBAC §2); el router valida el
  cruce `self_test ⇔ system` (400) y la guardia por-acción (403).
  Edge: `gpio.run_cabinet_self_test` — RECHAZA con SASMEX/demanda/safed vivos; pulsa los
  relés NO audibles con ida a estado de protección por modo y REGRESO por `_apply`
  (recálculo desde demandas), readback en ambas transiciones; la sirena SOLO lectura
  (test espía: cero llamadas eléctricas). Dispatch: rama SELF_TEST en hilo corto + ack
  `results` (relés + salud del CACHE — jamás sondas). Ingesta guarda `results` en el
  jsonb `ack`. Web: botón de SiteCard vivo (gate por matriz + sin-enlace deshabilitado
  con motivo), `useSelfTest` (POST + poll hasta resolver) y chips por relé del ack
  (GAS ✓ / ELEVATOR ✗ / SIREN LECTURA).
- Criterios verificados: E2E comando→pulso→ack→chips (api 201 + edge ack results + web
  chips) · sirena JAMÁS energizada (espía) · rechazo con alerta viva (3 casos) · matriz
  celda a celda · cruce 400/roles 403/rate-limit reutilizado · 0013 re-aplicable.
> **ESTADO.** api 776 (+10) · edge 323 (+15) · web 538 (+3) · ruff/eslint/tsc/build OK.

### [x] T-1.60 · Modo SIMULACRO institucional E2E (cierra M-1) — **COMPLETA (2026-07-12; su migración es la 0015)**
- **Componente:** api + edge + web + db · **Depende de:** T-1.59 (canal system)
- **Datos:** tablas `drills`/`drill_sites` (migración 0015, idempotente y verificada
  down/up; RLS con tenant_id; **gov LEE** el registro — evidencia para Protección Civil
  — y no escribe), JAMÁS `incidents`. Acuse por sitio DERIVADO por JOIN a `commands`;
  estado `active` derivado (sin worker de cierre). CHECK de `commands.action` ampliado
  con drill_start/drill_stop (schemas edge v1.5.0 + vector HMAC `drill_start_with_duration`
  — la firma cubre `duration_s` dentro del payload canónico).
- **Refactor regla-de-oro-8:** `issue_signed_command()` extraído a
  `commands/service.py` — /commands y /drills emiten por la MISMA superficie
  (rate-limit + clave por gateway fail-closed + nonce + TTL + publish + audit).
- **API:** `POST /drills` (matriz `drill_start` = superadmin/tenant_admin, anclada;
  emisión best-effort POR SITIO — un gabinete sin clave queda registrado con
  command_id NULL), `GET /drills` y `GET /drills/active` para roles de CONSOLA (el
  banner lo ven todos; RLS acota), `POST /drills/{id}/stop` idempotente que publica
  `drill_stop` a los sitios que recibieron el start. Los drills NO pasan por el
  endpoint público de comandos (sus acciones no están en `ACTIONS`).
- **Edge:** módulo `drill/` (`DrillController`, no-crítico, observador puro): banner
  en el panel LAN (sección `drill` del status + banner ámbar SIN parpadeo "🔶
  SIMULACRO — ESTO NO ES UNA ALERTA REAL"; la alerta real SIEMPRE pinta encima),
  voceo `play_simulacro()` solo con audio habilitado, fin por ventana/stop firmado.
  **LO REAL GANA:** rechaza el arranque con SASMEX enclavado; un SASMEX real
  (no pulso CIRES) o tier ≥ restricted lo ABORTAN visiblemente cortando el voceo —
  test ancla: la sirena del reflejo sigue sonando y CERO relés cambian por el drill.
- **Web:** `DrillBanner` en la consola (rotulado NO-real, sitios y hora de fin UTC;
  con incidente vivo se degrada a badge — precedencia visual de lo real), botón
  INICIAR/TERMINAR solo con `drill_start`; `useActiveDrill` (poll 10 s; push WS
  anotado como mejora futura).
- Criterios verificados por test: POST /drills → drill_start firmado por sitio con
  duración en el payload → registro con acuse derivado · CERO filas en
  incidents/actions/dictamens (E2E) · abort por SASMEX y por tier con reflejo intacto ·
  pulso de prueba CIRES NO aborta · roles 403 · gov lee · stop idempotente + drill_stop
  publicado · banner/badge/gates web · 0015 re-aplicable.
> **ESTADO.** api 793 (+12) · edge 340 (+17) · web 542 (+7) · demo 22 ·
> ruff/eslint/tsc/build limpios en los tres lados.

### [x] T-1.61 · Notificación al inspector en `dictamen_request` — **COMPLETA (2026-07-12; adelantada a T-1.60 ⇒ su migración es la 0014)**
- **Componente:** api · **Depende de:** — (el wake por NOTIFY de 0004 ya existía)
- **Migración 0014** (idempotente, down/up verificado): `notification_jobs.action_id`
  + 2 índices únicos parciales — la clave original `WHERE action_id IS NULL` (jobs de
  incidente; el ON CONFLICT del orquestador apunta al índice parcial) y
  `(action_id, channel)` (1 job por acción). `db/schema.sql` refleja el estado final.
- ENQUEUE nueva `_enqueue_dictamen_requests`: acciones sin job y sin dictamen firmado
  posterior (espejo de `_PENDING_REQUEST_SQL`); job `email/parallel/due_at=a.ts`.
  Destino: lista NUEVA `notifications.inspector_emails` (`resolve_inspector_emails`;
  sin lista ⇒ warning y skip). Mensaje bifurcado: headline "Solicitud de dictamen ·
  {site}", `requested_by`, `note` y link `{notify_web_base_url}/triage?incident={id}`
  (setting nuevo; vacío ⇒ sin link). Actor del timeline con sufijo `:{action_id}`.
- Criterios verificados por test: email con solicitante/nota/link (E2E provider
  simulado) · 1 job exacto por action_id ante re-runs · firmado posterior NO notifica ·
  sin inspector_emails se omite con gracia · convivencia con la cascada del MISMO
  incidente en el mismo pass (jobs + timeline sin colisión) · suite previa intacta
  (38/38) · 0014 re-aplicable.
> **ESTADO.** api 781 (+5) · ruff limpio.

---

## Fase 1.8.1 · Los tres fallos que destapó el uso real (2026-07-14)

Los tres se diagnosticaron **contra producción**, no por inspección: el correo del
inspector no llegaba, el control de simulacro se comía el mapa y el botón LOGIN DEV
mentía en la nube. Ninguno era lo que parecía.

### [x] T-1.62 · El correo sale de verdad (IAM SES + reintentos + la fuga de config) — **COMPLETA (2026-07-14)**
- **Componente:** infra · api · web · **Depende de:** T-1.61
- **Causa raíz (evidencia viva):** el job del dictamen SÍ se creaba y moría al enviarse
  con `ses: AccessDenied` — **el rol IAM de la instancia nunca tuvo `ses:SendEmail`**
  (cero `ses:` en todo el Terraform). El hueco estuvo tapado un mes porque los avisos
  que sí llegan (gabinete caído, alarmas) los manda **SNS**, con permiso propio. Además
  la identidad SES estaba **sin verificar** (el correo confirmado era el de SNS, otro
  distinto) y la cuenta sigue en **sandbox** (emisor y destinatario verificados).
- **Infra:** Sid `WorkerSesSend` en `aws_iam_role_policy.db`. El ARN se CONSTRUYE en
  `envs/dev` (no se lee de `module.identity`: `identity → serve → database` ya es una
  cadena y el output cerraría el ciclo). Lista vacía ⇒ sin statement.
- **Migración 0016** (idempotente, down/up verificado): `notification_jobs.attempts`.
  Un fallo de proveedor era una **lápida** — `failed` para siempre, re-encolado ciego al
  estado y 409 impidiendo re-pedir el dictamen: un AccessDenied dejó un incidente real
  sin correo y sin retorno. Ahora `_fail` decide por *quién queda detrás*: un salto de
  cascada CON siguiente canal muere en el acto y escala (semántica de T-1.21 intacta:
  reintentar ahí retrasaría llegar al humano); un job paralelo o el ÚLTIMO salto —la
  única voz que queda— reintenta con backoff 30 s / 2 min hasta `notify_max_attempts`.
- **Honestidad:** `build_providers` grita si cae al provider SIMULADO (marcaba los jobs
  como `sent` sin enviar nada — así se perdieron correos el 13/07 sin dejar rastro).
- **Web:** `patchChannels` reescribía `config.notifications` entero y **borraba
  `inspector_emails`** al guardar cualquier canal en Multi-Tenant: el correo se apagaba
  solo, sin rastro en la BD. Ahora preserva las claves que la pantalla no gestiona.
- Criterios verificados por test: reintento con backoff y entrega al 2º intento ·
  agotamiento ⇒ `failed` con `attempts=3` · la cascada con escalado NO reintenta · el
  último salto SÍ · `inspector_emails` sobrevive a un guardado de canales · 0016
  re-aplicable · `terraform plan` = 1 change, 0 destroy.

### [x] T-1.63 · El mapa recupera su alto (el simulacro deja de robarlo) — **COMPLETA (2026-07-14)**
- **Componente:** web · **Depende de:** T-1.60
- **Causa raíz:** `.soc-main` es `grid-template-rows: minmax(0,1fr) auto` y desde T-1.60
  tiene 3 hijos: el `DrillBanner` cayó en la fila elástica y el wall quedó en la fila
  `auto` ⇒ `.soc-stage` colapsaba a su piso `min-height: 280px`. El CSS del drill ya era
  compacto; lo roto era el layout.
- **TRAMPA:** `.soc-main` la usan DOS elementos — el `<main>` del `AppShell` (envuelve
  TODAS las rutas) y el `<main>` interno de la consola. Cambiar la regla compartida a
  flex dejó la página entera sin alto (se vio en el navegador, no en jsdom). El fix va
  acotado a `.soc-shell > .soc-main`.
- **Regresión de verdad:** el smoke Playwright mide el `boundingBox` real —
  `.soc-stage > 400 px` y la tira del drill `< 60 px`. jsdom no calcula alturas: este bug
  era invisible para vitest por construcción. Medido tras el fix: mapa 633 px, tira 34 px.

### [x] T-1.64 · Login: apagar la puerta falsa y abrir las de verdad — **COMPLETA (2026-07-14)**
- **Componente:** deploy · infra · **Depende de:** —
- **Causa raíz:** la API hace lo correcto (`/dev/token` solo se monta con `auth_jwks_json`;
  en la nube el 404 es honesto). El bug era del **build**: sin `.dockerignore`, `COPY web web`
  metía el `web/.env` LOCAL y gitignored (`VITE_DEV_TOKEN_ENABLED=true`) en la imagen de
  producción. **La imagen dependía de un archivo del laptop.** Al taparlo apareció el
  segundo: el `tsc` del web resolvía `@hey-api/client-fetch` desde el `node_modules` del
  laptop copiado con `shared/sdk-ts` — ahora el SDK instala sus deps DENTRO de la imagen.
- **Verificado en el bundle**, no de palabra: `VITE_DEV_TOKEN_ENABLED:"false"`.
- **`make cloud-users`** (`infra/scripts/seed_console_users.sh`): alta idempotente de los
  6 perfiles web en Cognito. El rol viaja en el TOKEN (no hay tabla `users`), y el paso
  que se olvida es el **grupo**: sin él `claims.py` rechaza con `role not in groups` (401)
  aunque el `custom:role` sea correcto. Contraseñas a Secrets Manager, impresas una vez.
  MFA TOTP obligatorio del pool ⇒ cada perfil enrola authenticator en su primer login.

> **ESTADO 1.8.1 — DESPLEGADA Y VERIFICADA EN PRODUCCIÓN (2026-07-14, tag `9d16056`).**
> `terraform apply` (Sid `WorkerSesSend`) + identidad SES verificada + `cloud-deploy`
> (alembic **0016**, 7 contenedores) + `cloud-users` (6 perfiles con grupo y claims).
> **El correo de dictamen que llevaba horas atascado SALIÓ de verdad** tras reencolarlo
> (`notify sent email/parallel`, `status=sent`, cero error) — la primera vez que un correo
> de la aplicación llega desde la nube. Typo de la cascada corregido en el rule_set vivo.
> El bundle servido por la consola dice `VITE_DEV_TOKEN_ENABLED:"false"`: la pantalla de
> login ya solo ofrece Cognito. api 797 · web 543 · edge 336 · e2e 2 · CI verde.
> Nuevo fichero LOCAL (gitignored) `infra/terraform/envs/dev/local.auto.tfvars`: fija
> `serve_enabled=true` y el CIDR, para que un `apply` a secas no destruya la consola.

### [x] T-1.65 · El lag de SeedLink era un dato congelado disfrazado de vivo — **COMPLETA (2026-07-14)**
- **Componente:** edge · api · web · **Depende de:** —
- **Cómo se descubrió:** verificando el despliegue de la 1.8.1 (`revisa que todo funcione`).
  El gabinete latía cada minuto y la nube lo pintaba **OPERATIVO**… pero el último feature
  en la base era de **9 horas antes**: el Raspberry Shake llevaba toda la mañana fuera de
  la red (`No route to host`, ARP INCOMPLETE) y **el sistema estaba ciego sin que nadie lo
  supiera**.
- **Causa raíz:** `SeedLinkClient._last_lag_s` se calculaba **al recibir** un paquete
  (`utcnow() - packet.endtime`) y jamás se recalculaba. Con el stream muerto, el heartbeat
  seguía publicando el último valor bueno (`1.24 s`) **para siempre**. Un dato viejo
  presentado como vivo — exactamente lo que prohíbe la regla de oro 7 — y el motivo de que
  la caída fuera invisible: `derive_fleet_state` YA sabía degradar por lag, pero recibía
  una mentira.
- **Fix:** `last_lag_s` pasa a ser la **antigüedad del dato más reciente**, calculada AL
  CONSULTAR: crece sin límite si no entran muestras (y, sin ningún paquete aún, cuenta
  desde el arranque del módulo — un gabinete que nunca vio el sensor tampoco reporta 0 s).
- **Umbrales realineados a la nueva semántica:** entre registro y registro el valor sube
  hasta la duración del propio registro miniSEED (~7 s como techo a 100 sps), así que los
  2 s de antes harían parpadear un stream SANO. `LAG_WARN_S` (edge) y
  `fleet_seedlink_lag_max_s` (nube) → **15 s**; el badge de la consola espeja ese número
  (tenía un `< 5` hardcodeado). No retrasa nada: al primer heartbeat sin datos el lag ya
  vale ≥60 s.
- Criterios verificados por test: el lag CRECE con el stream muerto (reloj inyectado: >1 h
  ⇒ >3600 s, jamás congelado en 0.5 s) · sin paquetes cuenta desde el arranque · `None`
  antes de arrancar (sin dato ≠ 0.0) · la flota degrada con lag > umbral y el espejo de
  tests de la API sigue el default.
> **ESTADO.** edge 338 (+2) · api 797 · web 543 · ruff/eslint/tsc limpios.

### [x] T-1.66 · Alarma de SENSOR MUDO: el correo que nadie recibió — **COMPLETA (2026-07-14)**
- **Componente:** infra · **Depende de:** T-1.65 (sin el lag honesto, la métrica mentiría igual)
- **El agujero:** las alarmas de A-4 vigilan la INFRA —gabinete conectado, DLQ, instancia, reglas
  IoT— pero **ninguna vigilaba que el sismógrafo tuviera datos**. Con el Shake 15 h fuera de la
  red, el Pi seguía latiendo: `gateway_offline` no disparó (había enlace), ningún incidente se
  abrió (no hay sismo que detectar cuando estás ciego) y la consola decía OPERATIVO. **La única
  forma de enterarse era mirar la pantalla y sospechar.**
- **Fix (cero código de aplicación, mismo truco que la presencia):** regla IoT
  `takab_dev_seedlink_lag_metric` — `SELECT * FROM 'takab/health'` → `cloudwatch_metric` en el
  namespace `Takab/Sensor`, `metric_name = ${clientid()}` (= nombre del thing),
  `metric_value = ${seedlink_lag_s}`. Alarma `takab-dev-sensor-mudo-<thing>` (Maximum 5 min,
  **> 120 s**) → topic SNS de on-call ya confirmado. `treat_missing_data = notBreaching`: si cae
  el gabinete ENTERO pagina `gateway_offline` — cada alarma dice UNA cosa.
- **Por qué 120 s:** el lag es la antigüedad del dato; un stream sano no pasa de ~8 s (duración
  del registro miniSEED a 100 sps). 120 s deja fuera cualquier hipo de reconexión y sigue avisando
  en minutos. La política IAM del rol de reglas se amplía al namespace nuevo (`Takab/Fleet` +
  `Takab/Sensor`) — sin esa línea, la regla escribe métricas al vacío.

---

## Fase 1.9 · Hardware — arranque del WR-1 (SASMEX)

Mauricio recibió el receptor **WR-1**. Decisión de cableado (2026-07-14): tiene 2 salidas de
relevador — **Relevador 1 = Advertencia General (multi-riesgo)** y **Relevador 2 = Alerta
Sísmica Oficial (sismos mayores)**. **Solo se conecta el Relevador 2** al pin del Pi. Eso
RESUELVE de raíz el riesgo de la prueba periódica de CIRES: los avisos multi-riesgo y el
heartbeat viven en el Relevador 1, que no se cablea, así que el contacto que entra al gabinete
solo cierra ante una alerta sísmica real. El reflejo SASMEX→sirena de T-1.3 (pin BCM 16,
enclave hasta silencio, <100 ms) es correcto para ese contacto tal cual.

### [x] T-1.67 · Prueba LOCAL de actuación (ejercitar el gabinete sin alertar al sistema) — **COMPLETA (2026-07-14)**
- **Componente:** edge · **Depende de:** —
- **Necesidad (Mauricio):** poder probar EN LOCAL, desde el gabinete, que la sirena suena y que
  gas/ascensor/puertas responden, **sin** que se dispare el sistema entero (sin incidente en la
  nube, sin cascada de notificaciones). El proyecto está en pruebas, sin estaciones reales.
- **El hueco (inventario):** existían piezas fragmentadas — `run_siren_test` (local, solo sirena),
  `run_cabinet_self_test` (gas/ascensor/puertas con readback pero **excluye la sirena** y solo por
  comando firmado de la NUBE), y `drill` (cero relés). Ninguna hacía, desde el gabinete, sonar la
  sirena Y ejercitar los actuadores sin publicar a `takab/events`.
- **Diseño:** demanda acotada nueva en `gpio` (`_actuation_test_active`, hermana de
  `_siren_test_active`). Sirena+estrobo (`REFLEX_CHANNELS`) se **SOSTIENEN** unos segundos
  (`actuation_test_hold_s=5.0`) para oírlos/verlos; gas/ascensor/puertas hacen **PULSO** de
  verificación con readback (patrón del self-test), no disruptivo. Aislamiento por construcción:
  llama al `gpio` directo, **jamás invoca los callbacks SASMEX** (que son la única vía a
  rules→cloud→incidente), así que no publica evento ni notifica. Mismo guard de rechazo que el
  self-test (alerta/protección/safe viva ⇒ rechazado) y **una alerta real a media prueba GANA**
  por recálculo del modelo de demandas.
- **Panel LAN:** botón "PROBAR ACTUADORES" (PIN, no en botón físico), endpoint
  `POST /api/actuator-test`, banner propio cian "🔧 PRUEBA DE ACTUADORES — NO ES ALERTA REAL"
  (la alerta real pinta encima), y chips de resultado por relé (SUENA/VE ✓ · PULSO ✓).
- **Aislamiento vs. cloud verificado E2E**: durante la prueba `siren_sounding=True` pero
  `sasmex_active=False` y cero publicación de evento; gas/ascensor/puertas regresan a seguro; el
  sostén vence y la sirena se apaga sola.
- Criterios por test (edge): sostiene audibles + pulsa protectores con readback · no es alerta
  fantasma · **jamás dispara callbacks SASMEX** (garantía de aislamiento) · rechazada con alerta
  viva · el fin de la prueba jamás calla una alerta real · endpoint PIN-gated · resultado en status.
> **ESTADO.** edge 351 (+8) · ruff limpio. (El test de hardware del Shake real se salta en CI.)

### [x] T-1.68 · Sirena por AUDIO (jack 3.5 mm del cerebro) — **COMPLETA (2026-07-14)**
- **Componente:** edge · **Depende de:** T-1.67 (la prueba de actuación es una de las vías que la hace sonar)
- **CORRECCIÓN DE HARDWARE:** el "cerebro" NO es un Pi 5 — es un **Raspberry Pi 4 Model B Rev 1.5**
  (verificado contra `/proc/device-tree/model`; todo el proyecto lo documentaba mal). El Pi 4 **SÍ
  trae jack 3.5 mm y funciona** (`speaker-test` reprodujo tono; jack al 96%). La petición de sacar
  la sirena por el jack es directamente viable, sin DAC ni adaptador.
- **Necesidad (Mauricio):** que el SONIDO de la sirena salga por el jack 3.5 mm del cerebro. Hoy la
  sirena es solo relé (canal `SIREN` → pin 17); el módulo `audio` (A-6) solo hacía voceo hablado.
- **Diseño:** toggle PROPIO `audio_siren_enabled`, **independiente del voceo** (`audio_enabled`, que
  aún necesita los WAVs grabados de A-6). Con el asset sintetizado empaquetado
  (`takab_edge/audio/assets/siren.wav`, hi-lo 960/770 Hz, bordes en cruce por cero → loop sin clics,
  regenerable con `edge/scripts/gen_siren.py`), se enciende SIN grabar nada. El `AudioNotifier` gana
  un backend PROPIO para la sirena (no corta el voceo; con `default`/dmix ambos se mezclan) y un hilo
  watcher que cada 50 ms concilia con **`gpio.siren_sounding`**: suena ⇒ reproduce el WAV en bucle;
  deja de sonar ⇒ para. Un solo poll cubre el reflejo SASMEX real, la prueba de sirena y la de
  actuación (T-1.67), y se calla al silenciar/resetear. Sigue ADVISORY: cae aislado, la sirena de
  RELÉ es y será la primaria; jamás toca el camino de vida.
- Criterios por test (edge): la sirena por audio sigue el estado (suena con la alerta, calla al
  silenciar) · la prueba de actuación la hace sonar · deshabilitada por default no suena · asset
  faltante + habilitada ⇒ no arranca (fail-loud) · backend roto no propaga · el watcher la levanta
  en segundo plano.
> **ESTADO.** edge 361 (+6). El asset viaja por rsync (deploy.sh no excluye .wav) y en el wheel
> (hatchling incluye los datos de `takab_edge/`). Falta: activar en el Pi (`audio_siren_enabled=true`)
> y probar en vivo por el jack. GPIO del WR-1: pin 16 (default) listo, el reflejo ya escucha ahí.

### [x] T-1.69 · Modo prueba del WR-1 (probar el contacto sin alertar a la nube) — **COMPLETA (2026-07-14)**
- **Componente:** edge · **Depende de:** —
- **Necesidad (Mauricio):** al probar el WR-1 real (cerrar el Relevador 2) el gabinete abre un
  incidente crítico en la nube y manda correos (confirmado el 2026-07-14: incidente `d438fc9d`
  trigger=sasmex + 2 correos). Para probar el WR-1 repetidamente hace falta hacerlo SIN ese ruido.
- **Diseño:** ventana corta y **auto-expirable** (`sasmex_test_window_s=120`), armable por el panel
  LAN (toggle, PIN). Durante la ventana el gabinete **protege en LOCAL exactamente igual** — el
  reflejo SASMEX suena la sirena, los actuadores actúan, el voceo/audio también — pero el supervisor
  **SUPRIME todo lo que va a la nube** (acks + evento + evidencia) en `_act_and_publish`, justo
  DESPUÉS de la actuación local y ANTES de publicar. Sin evento ⇒ sin incidente ⇒ sin notificación.
  La bandera vive en `gpio` (objeto compartido por supervisor y panel); `test_mode_active` es una
  comparación de reloj monotónico (sin hilo). **Auto-expira a propósito**: dejarlo armado silenciaría
  a la nube ante una alerta REAL — la protección local siempre queda intacta, solo la coordinación en
  la nube se calla por ≤120 s, y el panel lo grita.
- **Panel LAN:** botón toggle "MODO PRUEBA WR-1 / SALIR", banner violeta SIEMPRE visible mientras
  esté armado (aun bajo alerta real, porque el operador DEBE saber que la nube no recibe alertas) con
  cuenta atrás; `POST /api/test-mode`.
- Criterios por test: arma/activo/desarma + auto-expira · el reflejo local NO se altera (la sirena
  suena en prueba) · el supervisor NO publica evento ni acks en modo prueba · al expirar vuelve a
  publicar · endpoint toggle PIN-gated + estado en status.
> **ESTADO.** edge 362 (+7). Incidentes de prueba de hoy (`d438fc9d` sasmex, `ef2053d3` local_threshold)
> CERRADOS. **HITO: el camino primario WR-1→GPIO→reflejo→nube VALIDADO con hardware real** (reflejo
> 6.65 ms, incidente trigger=sasmex, 2 correos). Falta G-04 (latencia física contacto→relé→sirena).

## Fase 1.10 · Red multi-estación, alta de clientes y visibilidad (T-1.70…T-1.73)

> Origen: Mauricio pidió (2026-07-14) la "regla de 3 estaciones", el paso a paso de alta de una
> estación (Pi↔Shake→nube), calibración/procedencia, alta de clientes y visibilidad configurable.
> **Decisión de seguridad ratificada:** el quórum de 3 estaciones corrige el **evento regional +
> notificaciones** (nube) y se **muestra** en la consola; **jamás** gatea la sirena local (regla de
> oro §2.1/§2.2). Plan aprobado: `~/.claude/plans/ya-confirmamos-que-cuando-linear-wreath.md`.

### [x] T-1.70 · Runbook de alta de estación + realidad multi-tenant — **COMPLETA (2026-07-15)**
- **Componente:** docs
- **Entregable:** `takab-docs/RUNBOOK-ALTA-DE-ESTACION.md` — paso a paso Pi↔Shake→nube; **serial
  (inventario) ≠ iot_thing (lo que vincula a la nube, lo crea Terraform)**; quién puede
  (`manage_fleet` = superadmin+tenant_admin); calibración + **procedencia** (StationXML/RESP FDSN
  de la red AM; sensibilidades al `edge.env` + `PUT /sensors` `calibration_source`); multi-tenant
  HOY (SQL) y modelo de visibilidad ACTUAL (fijo por rol).
- **Gotcha documentado:** `provision_gateway.sh` **sobrescribía** `edge.env` (solo HMAC/endpoint/PIN
  + certs); identidad/SeedLink/calibración se **agregaban** aparte, así que re-provisionar los
  borraba (T-1.41).
  > **CORREGIDO (2026-07-30, PR #13+#14):** el script ahora **fusiona** en vez de sobrescribir
  > (`infra/scripts/merge_env.py`) y **escribe la identidad** (`TAKAB_EDGE_GATEWAY_ID`, `DEV_MODE=false`),
  > que tampoco estaba en el archivo — el gabinete se identificaba con el default horneado del
  > código. Ver el registro de hotfixes al final de este documento.
> **ESTADO.** Doc creado, sin secretos. Responde textualmente las preguntas operativas de Mauricio.

### [x] T-1.71 · Regla de 3 estaciones VISIBLE + umbral local afinable — **COMPLETA (2026-07-15)**
- **Componente:** api + web (nube, no bloqueante) · edge (umbral autónomo)
- **A (nube — ya existe → configurar + mostrar):** confirmar `min_nodes=3`; exponer la
  **corroboración por estaciones** en incidente/epicentro (de `quorum_votes`/`seismic_events`):
  "SIN corroborar · 1 estación" vs "CONFIRMADO · 3 estaciones".
- **B (edge — afinar falsos positivos CON CUIDADO):** `ThresholdBand` configurable por sitio vía
  `rule_sets.config->'edge'` (config-sync existente); guard de persistencia opcional (N ventanas 1s);
  mantener ≥2 canales para sirena. Validar vs piso de ruido (0.6–1.1 mg). **Decision-gate hardware.**
- **Invariantes:** la sirena local NUNCA espera a la nube; SASMEX intacto; sin IA en el disparo;
  `edge/tests/test_e2e.py` (autónomo, cloud off) debe seguir verde.
> **ESTADO.** `00eccf6` (edge) + `fd06733` (api,web). Edge: `ConfigStore.add_apply_listener` +
> `RuleEngine.apply_thresholds` (rebind atómico) — umbral por sitio aplicado en vivo, SASMEX inmune
> (test lo fija). Nube: `map/state` expone `meta.node_count` por epicentro → mapa "… · N est."; pill
> de triage "CONFIRMADO · N estaciones". SDK regenerado. edge 366✓ (test_seedlink_hardware se salta
> en CI), api telemetry 16✓, web 544✓, ruff/eslint/build limpios. Pendiente opcional: guard de
> persistencia (descartado por ahora — camino crítico mínimo) y G-04 (validación física de umbrales).

### [x] T-1.72 · Alta de clientes (tenants): API + UI superadmin-only — **COMPLETA (2026-07-15)**
- **Componente:** api + web
- `POST /tenants` (+ `PATCH` opcional), acción nueva `manage_tenants` **solo `takab_superadmin`**;
  extender `routers/tenants.py` (hoy solo GET) + `queries/tenants.py` + schema `TenantCreate`;
  `code` único ⇒ 409; auditar. RLS ya lo permite (`tenants_admin`, `db/schema.sql:701`).
- Web: reponer botón "NUEVO" en `TenantsPage.tsx` gated por `me.allowed_actions.manage_tenants`.
- Tests: crea (superadmin) · 403 (otros) · 409 (code dup) · parity de matriz.
> **ESTADO.** `8a65035`. Acción `manage_tenants` (solo superadmin) en matrix.py + MeActions +
> meFixtures + ancla en test_matrix. `POST /tenants` (TenantCreate; visibility/status por default;
> 409 en code dup; auditado). Web: botón "NUEVO CLIENTE" en /tenants gateado + formulario +
> `useCreateTenant`. SDK regenerado. api tenants 13✓ + matrix✓; web 548✓; ruff/eslint/build limpios.

### [x] T-1.73 · Visibilidad configurable (RLS) — **COMPLETA (2026-07-15)**
- **Componente:** db (migración `0017` idempotente) + api + web
- Tabla `visibility_grants` (grantee→target|all × {ver_metadatos, ver_datos}); helpers SECURITY
  DEFINER `app_can_view_meta/data`; ampliar políticas `*_read` (metadatos: sites/zones/gateways/
  sensors/tenants) y el **WHERE de las vistas `*_secure`** (datos) — **crux: metadata ≠ datos**.
- Acción `manage_visibility` (solo superadmin); router `visibility.py` POST/GET/DELETE; card en
  `/tenants`. Default-deny preservado; superadmin/gov sin regresión; un grant nunca da escritura.
- Tests de cruce de tenants: default-deny, metadata≠datos, revoke, sin regresión.
> **ESTADO.** `126ba06` (db) + `99e9722` (api) + `8fc2588` (web). Tabla `visibility_grants` +
> helpers SECURITY DEFINER `app_can_view_meta/data` + 9 políticas `*_read` ampliadas + vistas
> `*_secure` con WHERE de datos (crux metadata≠datos con test dedicado). Migración `0017`
> idempotente y reversible, segura para `takab_migrator`. Acción `manage_visibility` (solo
> superadmin) + router `/visibility-grants` (POST upsert/GET/DELETE, auditado). Web: `VisibilityCard`
> en /tenants gateada. db RLS 11✓ (+ base intacta), api completo 815✓ + router 12✓, web 557✓.
> **Fase 1.10 COMPLETA** (T-1.70…T-1.73). Rama `feat/fase-1.10-red-multiestacion` lista para PR.

## Fase 2 · App móvil (T-2.00…T-2.14)

> Origen: Mauricio pidió (2026-07-15) arrancar la app móvil reconciliando la spec original
> (`takab-docs/design/app/PROMPT Especificación.md`, 2026-07-11, ahora SUPERSEDED) contra la
> Fase 1.10 cerrada. **Spec canónica:** `takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md`
> (v2.0 — matriz SE QUEDA/SE CAMBIA/SE ELIMINA/SE AGREGA en §14; canvas corregido y shots
> regenerados con `takab-docs/design/app/tools/regen-shots.mjs`). Plan aprobado:
> `~/.claude/plans/vamos-a-empezar-a-enumerated-fiddle.md`.
> **Decisiones ratificadas D1–D4 (2026-07-15):** D1 nueva spec canónica (el PROMPT queda como
> histórico); D2 código en `mobile/` + tokens en `shared/design-tokens/` (sin `apps/` ni
> `packages/`, patrón `file:` del SDK); D3 canvas corregido Y ampliado (21 artboards); D4 entran
> las 4 features — pánico quórum-de-2, banner de simulacro, próximo simulacro programado (agenda
> informativa `drills.scheduled_at`, **sin auto-arranque**: "LO REAL GANA" intacto) y superficie
> móvil para inspector/building_admin (perfil táctico server-driven, sin pantallas dedicadas).
> **Gates pre-código (PLAN-MAESTRO):** decisión #7 (MFA occupant) y la solicitud del entitlement
> de Critical Alerts a Apple se resuelven en T-2.00 ANTES de escribir código de producto.
> Método (spec §12): una tarea por sesión, DoD completo por tarea.

### [x] T-2.00 · Decisiones de arranque + entitlements — `GATE-DECISIONS` — **COMPLETA (2026-07-15)**
- **Componente:** docs · **Bloquea:** todo el resto de la fase.
- Resolver y registrar: **decisión #7** del PLAN-MAESTRO (MFA de `occupant`; supuesto vigente:
  sin MFA, compensado por quórum + rate-limit + auditoría); **solicitar a Apple el entitlement
  de Critical Alerts** (lead-time de semanas; fallback `time-sensitive` ya diseñado en spec §6);
  elegir emisor push (SNS platform endpoints vs FCM/APNs directo — hoy SNS es solo alarmas de
  infraestructura); ratificar **R1–R10** (spec §14.5), en particular R2 (enrolamiento vs
  `site_scope` default-deny) y R7 (lectura del dictamen por el táctico).
- No auto-verificable en repo: registrar el resultado en la spec (§14.5) y en esta sección.
> **ESTADO.** Las 4 resoluciones registradas en spec §14.5 (+§6/§8/§11), PLAN-MAESTRO gate #7
> `[RATIFICADO]`, RBAC §4.3 nota 2 y `specs/cognito-pool-v1.md` §5.2:
> **(1) Decisión #7 — de Mauricio:** occupant con **login simple SIN MFA obligatorio y MFA
> OPCIONAL** (opt-in TOTP desde 1.8 Cuenta). Implementación: **pool de ocupantes separado**
> `mfa=OPTIONAL` (Cognito no da MFA por grupo; OPTIONAL en el pool único dejaría a un táctico
> declinar TOTP). El pool táctico (`mfa=ON`, verificado en `identity/main.tf:42`) NO se toca ⇒
> el MFA de quien toca actuadores sigue garantizado. Split en T-2.02; dual-issuer en T-2.03.
> **(2) Entitlement Critical Alerts:** solicitud **INICIADA por Mauricio ante Apple
> (2026-07-15)**; aprobación pendiente bajo `GATE-STORE`; fallback `time-sensitive` vigente.
> **(3) Emisor push: SNS platform endpoints** (payload crudo passthrough; feedback de tokens
> muertos; cláusula de reversión a FCM v1/APNs directo si el spike de T-2.04 topa un campo que
> SNS no transporte). **(4) R1–R10 ratificados** — R2=(b) scope móvil server-side contra
> `user_zone_assignments`; R7=acción `dictamen_read`; geofence del pánico = best-effort (voto
> con GPS fuera de radio se descarta, sin GPS cuenta); R3 sigue bajo `GATE-LEGAL`.

### [x] T-2.01 · `shared/design-tokens/` + reconciliación documentada — **COMPLETA (2026-07-15)**
- **Componente:** shared + web
- Extraer los tokens `--tk-*` — **idénticos** entre `web/src/styles/colors_and_type.css` y
  `takab-docs/design/app/colors_and_type.css` (verificado 2026-07-15) — a
  `shared/design-tokens/`: fuente JSON/TS → export CSS vars (consola) + objeto TS (React
  Native); consumo por `file:` como el SDK. Incluir el contrato semántico etiqueta→color
  (SevTag / STATE_PILL / severidades) para que ambas plataformas resuelvan igual.
- Crear `takab-docs/design/DESIGN-TOKENS-RECONCILIATION.md` documentando la identidad (cero
  conflictos de valor) y el mapeo 1:1.
- La consola migra por **alias sin cambio visual** (tests/Playwright existentes como guardia).
> **ESTADO.** Paquete `@takab/design-tokens` creado: `tokens.json` (96 vars, fuente única) →
> `css/tokens.css` GENERADO (`gen-css.mjs`, determinista, con `--check` como drift gate) +
> `src/index.ts` (`cssVariables` exacto, `tokens` estructurado para RN, `toNumber`, contratos
> `INCIDENT_SEVERITY`/`DERIVED_STATE_PILL`/`KIND_COLOR`; regla desconocido⇒ámbar). Consola
> migrada: dep `file:` + `fs.allow`, `main.tsx` importa el css del paquete ANTES de los estilos
> locales, `colors_and_type.css` quedó solo con fuentes + clases de tipo, y `SevTag`/`SiteCard`
> consumen el contrato del paquete (clases/labels intactos, sus tests lo fijan). Guardias:
> `web/src/designTokens.test.ts` (19 tests: paridad css≡json, drift gate, ANCLAS con los
> valores pre-migración, contratos congelados). Reconciliación documentada (identidad, cero
> conflictos): `takab-docs/design/DESIGN-TOKENS-RECONCILIATION.md`. **web 576/576 ✓ (antes
> 557) · eslint limpio · vite build OK · tokens presentes en el bundle.** La copia del canvas
> queda como artefacto congelado; un token nuevo aterriza primero en `tokens.json`.

### [x] T-2.02 · Scaffold `mobile/` (Expo prebuild + auth + SDK) — **COMPLETA (2026-07-15)**
- **Componente:** mobile
- Expo SDK con dev client/prebuild (NO Expo Go); TypeScript estricto; TanStack Query + Zustand;
  React Navigation con **perfil server-driven** por `/me` (`allowed_routes`/`allowed_actions`,
  default-deny) — cubre D4d (inspector/building_admin entran al perfil táctico) sin lógica de
  rol horneada en UI.
- Cognito Hosted UI + código + PKCE (patrón oidc de la consola); tokens en Keychain/Keystore;
  sesión de larga vida del `occupant` (spec §8). `@takab/sdk` por `file:../shared/sdk-ts`.
- **Consecuencia de la decisión #7 (T-2.00):** crear el **pool de ocupantes** (`mfa=OPTIONAL`,
  único grupo `occupant`) + app client móvil en `infra/terraform/modules/identity`; la app
  enruta el login por perfil (occupant → pool simple con MFA opt-in; tácticos → pool `ON`).
- `mobile/README.md`: módulos que exigen prebuild + entitlements pendientes (`GATE-STORE`).
> **ESTADO.** **Infra:** módulo `identity` extendido — pool `takab-dev-occupants`
> (`mfa=OPTIONAL` + TOTP, único grupo `occupant`, mismos custom attributes), domain propio,
> client `takab-mobile-occupants` (PKCE por deep link `takab://auth/callback`, refresh 90 días)
> y client `takab-mobile-tactical` sobre el pool principal intacto (refresh 24 h); outputs en
> módulo y envs/dev; `fmt`+`validate` verdes. **✅ `terraform apply` EJECUTADO por Mauricio
> (2026-07-16): 5 added / 0 changed / 0 destroyed** — pool `us-east-2_P818WYSql` VIVO
> (discovery OIDC responde); `EXPO_PUBLIC_*` reales en `mobile/.env` local (gitignored).
> **App:** `mobile/` con Expo SDK 57 (RN 0.86 · React 19), expo-router con grupos
> `(occupant)`/`(brigadista)` y guards + `denied` explícito; `gateFor(/me)` default-deny
> (tests), sesión SOLO en SecureStore con purga de payload corrupto (tests), config dual-pool
> declarativa (tests), `useAuth` PKCE + `bootstrapSession` (offline conserva sesión cacheada
> con `me=null`), SDK espejo de la consola (Bearer + solo 401 expulsa), tema desde
> `@takab/design-tokens`, 9 placeholders honestos con su tarea, Metro con watchFolders del
> monorepo, `.gitignore` CNG. **Job `mobile` en CI** (eslint+tsc+jest, patrón file: del job
> web). jest 18/18 ✓ · tsc ✓ · eslint ✓. README con envs/entitlements; AGENTS.md del árbol.

### [x] T-2.03 · DB + API móvil núcleo (migración 0018 sobre el DDL latente) — **COMPLETA (2026-07-16)**
- **Componente:** db + api + shared (SDK)
- Migración `0018` **idempotente** + `db/schema.sql` consolidado (invariante T-1.45): deltas
  `life_checkins` (+`ts_device`, +`via self|delegated`, +`verified_by`), `zones.evac_policy`
  (`evacuate|shelter` — R1), `user_profiles.phone` (R4, PII con consentimiento),
  `drills.scheduled_at` (D4c, agenda informativa), hash declarado-en-captura en
  `evidence_objects` si falta; tablas nuevas `push_tokens`, `device_keys`, `damage_reports`,
  `compliance_labels`, `site_assets` — todas con `tenant_id` + RLS default-deny (patrón 0017).
- Endpoints de la spec §5 (sin prefijo de versión): `/me/enrollment`,
  `/sites/{id}/enrollment-codes`, `/sites/{id}/mobile-state` (con `phase`, compliance_labels,
  drill activo/próximo, assets), `/incidents/{id}/checkins` (+GET `scope=me`),
  `/incidents/{id}/roster`, `/incidents/{id}/damage-reports` (+GET para Triage web),
  `/sites/{id}/assets`, `/me/push-tokens`, `/me/device-keys`, `/sites/{id}/drills`.
- Acciones nuevas en `api/src/takab_api/auth/matrix.py` (patrón `roles_with_action` + parity
  test extendido): `checkin_submit`, `roster_read`, `damage_report_submit`, `evidence_upload`,
  `siren_silence`, `manual_activate`, `enrollment_manage`, `panic_vote`, `dictamen_read` (R7).
- **Dual-issuer (decisión #7):** `claims.py` valida ambos pools y **ancla pool→rol** (token del
  pool de ocupantes ⇒ solo `occupant`; del pool táctico ⇒ nunca `occupant` en superficie móvil)
  ⇒ 401 en cruce, con tests. R2 ratificado = (b): scope móvil server-side contra
  `user_zone_assignments` (cache corto), sin escribir claims por admin API.
- Todo mutador audita vía el escritor único (`audit.py`); tests de cruce de tenants DEBEN
  fallar; SDK regenerado (drift gate verde).
> **ESTADO.** **DB:** migración `0018_mobile_core` idempotente, validada en cadena incremental
> Y fresca (la 0001 aplica el schema nuevo y la 0018 re-afirma); deltas + 5 tablas nuevas con
> RLS default-deny (`pt_self`/`dk_self` = SOLO fila propia); **GRANTs del DDL latente que
> FALTABAN** (uza/sec/mav/lc — política sin privilegio era inservible). Trampa nueva: `drills`
> es del usuario de conexión (la 0015 no usó SET ROLE) ⇒ su ALTER corre fuera del bloque
> migrator. **Auth:** dual-issuer con ancla pool→rol en `get_claims` (cruce en cualquier
> dirección ⇒ 401), retrocompatible (pool de ocupantes deshabilitado = single-issuer intacto);
> `require_mobile_surface`; `/dev/token` enruta occupant→pool de ocupantes; `/me/profile` dejó
> de ser web-only y suma `phone` (R4: darlo ES el consentimiento; null lo retira; PII fuera del
> audit). **Matriz:** 9 acciones móviles con paridad EJECUTABLE contra RBAC §3
> (`test_mobile_actions_match_rbac_section_3`, celda a celda — corrigió 2 concesiones mías:
> inspector sin roster, building_admin sin forense); MeActions + meFixtures espejados.
> **Routers:** `mobile_me` (push-tokens upsert-revive, device-keys PEM, enrolamiento atómico con
> 404 uniforme), `mobile_site` (mobile-state con `phase` derivada de datos REALES —
> incidente+`rule_evaluations`+dictamen firmado habitable—, assets presignados GET/PUT seam
> MinIO, enrollment-codes, drills por sitio), `mobile_incident` (check-ins self/delegated
> distinguibles, roster con contadores + audit de PII, damage-reports con `people_at_risk`
> derivado); drills gana AGENDA (`scheduled_at`: anuncio que JAMÁS deriva activo — LO REAL
> GANA). R2 implementada: `assert_site_access` (occupant enrolado o 404). **api 851✓ · auth
> 116✓ · mobile_core 11✓ · web 576✓ · sdk tsc✓ · mobile 18✓ · ruff limpio · SDK regenerado.** Pendiente T-2.10: verificación criptográfica de la firma de intención (hoy se
> ALMACENA, sin fingir validación).

### [x] T-2.04 · Push: infraestructura + onboarding de permisos — `GATE-STORE` — **COMPLETA (2026-07-16)**
- **Componente:** api + mobile + infra
- Registro/rotación en `/me/push-tokens`; **emisor: SNS platform endpoints (T-2.00)** — spike
  inicial de campos APNs con cláusula de reversión (spec §6); dos clases JAMÁS mezcladas:
  `CRISIS` (Critical Alerts iOS / canal `seismic_alert` IMPORTANCE_HIGH + bypass DND Android)
  y `OPS`; payload mínimo `{type, site_id, incident_id, phase}` sin datos sensibles.
- Integración con la cascada notify FAIL-OPEN existente; la push es **best-effort** — la
  protección de vida es la sirena del edge (así se comunica en onboarding, R5).
- Pantallas 0.1–0.4 (login, permisos con estado rojo imposible de ignorar, aviso de privacidad,
  enrolamiento por código). Verificación física de bypass DND/Critical Alerts = `GATE-STORE`.
> **ESTADO.** **Infra:** módulo `push/` con platform applications APNs/FCM **condicionales a
> credenciales reales** (vacías ⇒ no se crean; la .p8 llega con la aprobación de Apple —
> GATE-STORE) + política IAM SNS acotada al rol de la instancia; outputs para
> `TAKAB_API_PUSH_*_APPLICATION_ARN`; fmt+validate ✓ (**apply pendiente, sin efecto hasta tener
> credenciales**). **DB:** 0019 `push_tokens.endpoint_arn` (cache del endpoint SNS) + UPDATE a
> `takab_ingest` + el CHECK de `notification_jobs.channel` admite `'push'` (trampa: el CHECK
> viejo reventaba el INSERT). **API:** `notify/push.py` — payloads por clase (CRISIS:
> `interruption-level time-sensitive` base pre-entitlement + `sound.critical` listo, canal
> Android `seismic_alert`; OPS normal; texto visible GENÉRICO — cero PII en lockscreen);
> `SnsPushProvider` (endpoint por dispositivo con sellado de ARN; `EndpointDisabled` ⇒
> REVOCACIÓN honesta del token) + simulado que grita (patrón T-1.62). Cascada: job `push`
> **parallel** a t0 (clase CRISIS al abrir incidente), encolado SOLO si el sitio tiene
> dispositivos (nada de 'sent' vacíos), targeting FRESCO al despachar (patrón del secret del
> webhook), `incident_action notify_sent` con `devices_delivered/revoked`; 0 entregas ⇒ backoff
> (única voz push). **Móvil:** `services/push.ts` (canales Android MAX+bypassDnd, permisos con
> `allowCriticalAlerts`, token NATIVO → `/me/push-tokens`), `alertability.ts` (derivación PURA:
> blocked/degraded/ok — jamás optimismo), onboarding 0.2/0.3/0.4 cableados (permisos con rojo
> imposible de ignorar re-verificado al volver de background; privacidad con consentimiento GPS
> revocable; enrolamiento consumiendo `POST /me/enrollment`), gate en `index` + registro
> best-effort al autenticar. **api 860✓ (+9 push, moto) · mobile 30✓ (+12) · tsc/lint/ruff
> limpios · OpenAPI sin drift.** Pendiente físico `GATE-STORE`: entitlement de Apple (en
> trámite), credenciales APNs/FCM reales, bypass DND en dispositivos; push OPS de dictamen se
> cablea en T-2.12; sonido oficial empaquetado en T-2.05.

### [x] T-2.05 · Máquina de estados de crisis + pantallas 1.2/1.3
- **Componente:** mobile
- Estado único determinista (spec §4.1): la fase la sirve `mobile-state.phase`; la push
  despierta y el REST reconstruye; instrucción por `zones.evac_policy`; contador T+ ascendente;
  fuentes reales del payload (`sasmex_wr1` booleano / detección local con PGA instrumental /
  quórum "CONFIRMADO · N estaciones" con `meta.node_count`).
- **Tests de honestidad:** snapshot que FALLA si aparece magnitud/ETA con `source: sasmex_wr1`;
  flag `ALERT_SOURCE_CARRIES_ETA=false`; ningún camino local produce `REENTRY_APPROVED`.
- Test de integración: los modos de prueba del gabinete (T-1.67/T-1.69) no generan incidente ⇒
  la máquina no sale de `IDLE` (garantía server-side; cero lógica local de "modo prueba").

> **ESTADO (2026-07-16): COMPLETA.** **API:** `mobile-state.incident` ahora porta el dato
> INSTRUMENTAL real — `max_pga_g` (PGA MEDIDO del evento, jamás magnitud) + `node_count`
> (estaciones corroborantes) — mismo origen que el Triage; SDK regenerado sin drift.
> **Máquina (`mobile/src/features/alert/machine.ts`):** `deriveAlertState(phase, hasOwnCheckin)`
> PURA de 2 argumentos — `reentry_approved` SOLO puede venir de la fase del servidor (test
> recorre todos los caminos locales); `ALERT_SOURCE_CARRIES_ETA=false` (§2.1-A: el WR-1 entrega
> un booleano — el hueco de ETA ni se renderiza); `elapsedSeconds` con clamp a 0 (sesgo de reloj
> del dispositivo jamás pinta cronómetro fantasma; timestamp corrupto ⇒ 0, no NaN) y
> `formatElapsed` SIEMPRE `T+`. **Fuentes (`source.ts`):** etiqueta por `trigger` real —
> SASMEX sin números (el único dígito permitido es "WR-1"), local `PGA 0.15g MEDIDO` (mg bajo
> 0.01g — piso MEMS honesto), quórum `CONFIRMADO · N ESTACIONES`; trigger desconocido se muestra
> CRUDO. **Pantallas 1.2/1.3 (`CrisisView` + ruta `/crisis`):** takeover instruction-first
> (EVACÚE AHORA rojo / REPLIÉGUESE ámbar por `zones.evac_policy`; sin política ⇒ PROTÉJASE
> banner MVP — el teléfono NO adivina), sin gesto de regreso (`gestureEnabled:false`), la salida
> la decide la fase (`Redirect` cuando el servidor deja `alert_active`); spinner "VERIFICANDO
> ALERTA CON EL SERVIDOR…" si la push llegó antes que el REST. **Watcher (`CrisisWatcher`):**
> push CRISIS ⇒ invalida `mobile-state` y navega; polling honesto 30 s reposo / 5 s crisis.
> **Sonido:** loop `expo-audio` con `playsInSilentMode` — **placeholder `siren.wav` del edge;
> el tono SASMEX oficial requiere licenciamiento (pendiente físico, como el entitlement)**.
> **Trampa de migraciones cerrada (0018/0019 reestructuradas):** el dueño histórico de las
> tablas varía por base (en el dev local `user_profiles`/`notification_jobs`/`life_checkins`
> son del superusuario de conexión; en `takab_test` lo es `drills`) ⇒ TODO DDL sobre tablas
> PREEXISTENTES corre como USUARIO DE CONEXIÓN (superusuario local / `takab_migrator` dueño en
> nube) y `SET ROLE takab_migrator` queda SOLO para objetos nuevos; validado incremental
> (dev 0017→0019), cadena fresca y round-trip de downgrade. **Rezagos de T-2.03 saneados en
> web:** fixtures `DrillOut.scheduled_at` + las 9 acciones móviles en `MeActions` (el build de
> web estaba roto en silencio; vitest no typechequea). Check-in (1.4) llega en T-2.06 y el
> bloqueo de reingreso (1.5) en T-2.07 — `checkin_pending`/`reentry_blocked` ya derivan hoy.
> **api 860✓ · web 576✓ (build+eslint+prettier limpios) · mobile 66✓ (tsc+expo lint limpios).**

### [x] T-2.06 · Cola offline cifrada + check-in de vida (1.4)
- **Componente:** mobile + api
- SQLite cifrado (verificar el cifrado real antes de rotular "AES-256"); elementos con estado
  `{pending, uploading, synced, failed}`; nada se borra hasta `synced` + 24 h; reintentos con
  backoff + jitter; hash SHA-256 de blobs en captura (cadena de custodia, spec §4.2).
- Check-in 1.4: dos botones gigantes; `need_help` adjunta GPS **solo con consentimiento** (si
  no, zona asignada; se muestra qué se enviará); `ts_device` + `ts_server` persistidos.
- Aceptación E2E: modo avión → check-in `pending` → red → `synced` → el roster del táctico lo
  refleja vía WS en <2 s.

> **ESTADO (2026-07-16): COMPLETA.** **API idempotente ante replays (regla de oro 3):**
> `CheckinIn.checkin_id` lo genera la COLA del dispositivo; `INSERT … ON CONFLICT (checkin_id)
> DO NOTHING` + replay del MISMO portador/incidente ⇒ **200 con la fila original** (sin audit —
> es el mismo evento); un id ajeno ⇒ **409 sin fuga** (test `test_checkin_replay_offline_es_
> idempotente`); la tabla sigue append-only (jamás DO UPDATE). **Cola (`mobile/src/offline/`):**
> lógica PURA (`queue.ts`: transiciones, `isDue`, retención SOLO `synced+24h`,
> `recoverInterrupted` — un `uploading` interrumpido vuelve a `pending` al hidratar porque el
> replay es seguro); backoff exponencial ±50% jitter con techo 5 min (`backoff.ts`); huella
> SHA-256 del payload CANÓNICO al capturar (`custody.ts`); persistencia SQLite con **SQLCipher
> VERIFICADO en runtime** (`PRAGMA cipher_version` tras `PRAGMA key` con llave de 32 bytes en
> SecureStore; sin SQLCipher —p.ej. Expo Go— el estado queda `{active:false}` y JAMÁS se rotula
> AES-256 sin comprobarlo); motor `drainQueue` (candado reentrante, orden de captura, respeta
> `next_attempt_at`; 4xx de contrato ⇒ `failed` VISIBLE sin reintento; red/5xx/429/401 ⇒
> retry) + `OfflineSyncGate` (hidrata al autenticar, drena en foreground/red-recuperada/tic 15 s).
> **1.4:** dos botones gigantes con TRANSPARENCIA previa (`whatWillBeSent`: qué viaja
> exactamente); **GPS SOLO need_help+consentimiento** (`buildCheckinPayload` puro — el test
> FALLA si alguien relaja la regla; "estoy bien" jamás manda GPS ni con fix a la mano); captura
> best-effort 5 s ⇒ degrada a zona asignada declarándolo; `ts_device` sellado AL TOQUE;
> `CheckinStatusView` honesto (GUARDADO EN ESTE DISPOSITIVO ≠ RECIBIDO POR EL SERVIDOR);
> `hasOwnCheckin` = servidor ∪ cola local (`failed` NO cuenta — debe poder reintentar);
> watcher + `/crisis` enrutan `checkin_pending` → `/checkin` (takeover sin gesto de regreso).
> **E2E:** modo avión→pending→red→synced con el MISMO checkin_id cubierto en jest
> (`sync.test.ts`) y el roster lo refleja al aterrizar (tests api); el reflejo "vía WS <2 s"
> pertenece a T-2.08 (WS móvil táctico). Trampas nuevas: RTL v14 — `fireEvent` TAMBIÉN es
> async (un press sin await deja act() abierto y envenena el resto de la suite);
> `no-require-imports` ⇒ carga perezosa del módulo nativo con `import()` dinámico.
> **api 861✓ · web 576✓ · mobile 95✓ (tsc+lint limpios) · SDK sin drift.**

### [x] T-2.07 · Pantallas de ocupante: 1.1, 1.5, 1.6–1.8 + variante SIMULACRO
- **Componente:** mobile
- 1.1 reposo: estado del sitio honesto por `mobile-state` (nunca calculado local); badge
  "SASMEX ENLAZADO" solo con enlace WR-1 real; próximo simulacro (`scheduled_at`) + último
  resultado; **variante SIMULACRO** ámbar con drill activo — un drill JAMÁS dispara pantallas
  de crisis. 1.5 bloqueo: timeline por `incident_actions`; libera solo con `reentry_approved`;
  strings normativos desde `compliance_labels`. 1.6 rutas (assets S3 cacheados offline),
  1.7 directorio (llamada de un toque), 1.8 cuenta (permisos, privacidad, consentimiento GPS
  revocable, logout).
- Los 4 estados obligatorios en cada componente (contrato `StateFrame`:
  loading>error>empty>stale, banner "DATOS RETENIDOS"); "datos de hace X min" sin red.

> **ESTADO (2026-07-16): COMPLETA.** **API (+2):** `mobile-state.site_health` — el banner del
> edificio sale del MISMO derivador que Flota Edge (`derive_fleet_state`, verdad única y
> mismos umbrales de settings; con varios gabinetes gana el PEOR; sitio sin gabinete ⇒
> SIN ENLACE honesto) + `GET /sites/{id}/directory` (roster PÚBLICO: brigadista/seguridad/
> administración desde `user_zone_assignments` ⋈ `user_profiles`, occupants JAMÁS listados,
> publicación deliberada ⇒ sin audit por lectura). **Matiz de honestidad del badge SASMEX:**
> el WR-1 NO expone supervisión de línea (solo el Relevador 2 está cableado — fase 1.9) ⇒ el
> chip verificable es `has_wr1` (hardware declarado) ∧ gabinete reportando, rotulado
> "SASMEX WR-1 · GABINETE ENLAZADO"; jamás un estado del enlace que nadie mide. **Infra
> móvil:** `StateFrame` RN (prioridad loading>error>empty>contenido+stale, banner "DATOS
> RETENIDOS · hace X min" con tic interno de 30 s) + `useCachedQuery` (respuesta buena ⇒
> caché cifrada `doc_cache` en la MISMA sqlite del offline —`db.ts` compartida—; sin red ⇒
> copia con edad; sin red NI copia ⇒ error declarado, jamás spinner infinito). **1.1**
> (`HomeView`): SEGURO/DEGRADADO/SIN ENLACE, chip WR-1, zona+política, franja ámbar
> SIMULACRO sobre contenido NORMAL (test: jamás pantalla de crisis — el drill no crea
> incidente), agenda próximo/último (`sin programar`/`sin registro` — no inventa),
> brigadistas de MI zona con `tel:`. **1.5** (`ReentryBlockedView` + `reentryTimeline` pura):
> letrero rojo persistente, timeline derivada del servidor (evento→sacudida→su check-in
> [guardado≠recibido]→dictamen→reingreso; test recorre TODAS las combinaciones y "Reingreso
> autorizado" JAMÁS sale done — la liberación es solo `reentry_approved` del backend), punto
> de reunión, `compliance_labels` (vacío ⇒ NADA normativo, GATE-LEGAL); sustituye al
> `CheckinStatusView` de T-2.06 en `/checkin`. **1.6:** lista cacheada + descarga de binarios
> a documentos (`File.downloadFileAsync`, badge DISPONIBLE OFFLINE = `File.exists` verificado,
> abrir vía share sheet); sin URL ⇒ "SIN COPIA OFFLINE" declarado. **1.7:** agrupado por zona,
> LLAMAR un toque, sin teléfono ⇒ se declara (sin botón roto). **1.8:** perfil GET/PUT
> (nombre obligatorio CHECK 1-80), consentimiento GPS revocable con efecto declarado (revocar
> ⇒ el siguiente auxilio manda zona — garantizado por `buildCheckinPayload`, test T-2.06),
> fila TOTP OPCIONAL SOLO occupant (decisión #7; flujo de asociación → T-2.14), enlaces a
> permisos/privacidad/vincular, logout. Trampas nuevas: `renderHook` de RTL v14 también es
> async; react-hooks v6 `purity` veta `Date.now()` en render (⇒ tic con `useState(()=>…)` +
> interval, o `dataUpdatedAt`); el formulario de cuenta es estado DERIVADO (sin setState en
> effect); `toHaveTextContent(string)` exige match EXACTO (usar regex). Test nuevo del api con
> `gw_sandbox` (limpia gateways/device_health del sitio al entrar Y salir — los tests de
> ingest cuentan filas y un heartbeat huérfano los rompe).
> **api 863✓ · web 576✓ · mobile 125✓ (tsc+expo lint limpios) · SDK sin drift.**

### [x] T-2.08 · WS móvil (allowlist topic×rol) + dashboard táctico 2.1
- **Componente:** api + shared + mobile
- `/ws`: autorización por **allowlist topic×rol default-deny** (hoy el handshake solo admite
  roles de consola): tácticos con `site_state`, `features:<site_id>` e `incidents`, siempre
  acotados a `site_scope` + `custom:surface`; **`occupant` queda FUERA del WS** (push + REST).
  Tests de default-deny (occupant rechazado; topic no permitido rechazado).
- Extraer `LiveSocket` (reconexión backoff 1–30 s + jitter, re-subscribe, staleness por topic)
  de `web/src/lib/ws.ts` a `shared/sdk-ts`; la web migra al compartido sin cambio de conducta.
- 2.1: salud `device_health` real (UPS `unknown/null` → "S/D", jamás 0%; RTT MQTT, offset NTP,
  lag SeedLink, temperatura, cert); **features de 1 s** (pga/pgv/rms/stalta — NO waveform,
  regla de oro 9); actuadores BMS con el estado recalculado del arbitraje. Aceptación: mismo
  payload que la consola, sin transformaciones divergentes.

> **ESTADO (2026-07-16): COMPLETA.** **WS allowlist default-deny:** mapa `_TOPIC_ALLOWLIST`
> (topic-familia → roles) — consola C4I ∪ tácticos móviles (`brigadista`/`security_guard` con
> surface móvil verificada); un topic sin entrada niega a TODOS; **occupant se cierra 4401 en
> el HANDSHAKE** (sin sockets ociosos; el test viejo de "error por suscripción" se reescribió
> a este contrato). **`site_scope` en la ENTREGA:** los frames de `device_health` e
> `incident_action` ahora viajan con `site_id` (JOIN a gateways/incidents en el hub; campo
> ADITIVO en el protocolo) y `_frame_in_scope` descarta en el fan-out lo que quede fuera del
> alcance del suscriptor (default-deny: frame sin sitio para token acotado NO pasa) — también
> corrige a los tokens de consola acotados. **Acción nueva `panel_read`** (espejo EJECUTABLE de
> RBAC §3 "Dashboard táctico (salud gabinete + actuadores)": occupant "—", inspector Lectura):
> gatea `GET /incidents/{id}/actions`, que se movió a un router consola∪panel — MISMO endpoint
> y MISMA query para ambas superficies; el táctico queda acotado a su `site_scope` con el MISMO
> 404. Paridad §3 + fixtures web/mobile actualizados. **Shared:** `LiveSocket` → `@takab/sdk`
> (`live.ts`, corre en navegador y RN — WebSocket global) y `groupActions`/BMS → `bms.ts`
> (criterio 2.1: cero transformaciones divergentes); `web/lib/ws.ts` y `console/bms.ts` quedan
> como re-export (solo `liveWsUrl` sigue en web por `window`); el mock de ConsolePage pasó a
> PARCIAL (`importOriginal`). **mobile-state.site_health** ganó las métricas del heartbeat más
> reciente (RTT/lag/NTP/CPU/UPS/cert — el REST de flota/telemetría es consola-only y el WS solo
> notifica TRANSICIONES: sin esto el panel no tendría snapshot inicial honesto). **2.1
> (`(brigadista)/panel.tsx` + `features/panel/`):** salud con "S/D" (UPS unknown/null JAMÁS
> 0% — test), `applyHealthFrame` puro (solo un frame MÁS nuevo actualiza; el status NUNCA se
> recalcula local — verdad única del servidor), strip de features 1 s por canal (pga/pgv/rms/
> stalta, "ESPERANDO DATOS…" declarado, nota "sin forma de onda"), traza BMS = REST
> (`panel_read`) + frames live fusionados con `mergeAction` (dedupe por `action_id`, filtro por
> incidente) y agrupados con la `groupActions` COMPARTIDA; pill LIVE/RECONECTANDO/SIN CANAL.
> **api 866✓ · web 576✓ · mobile 133✓ (tsc+lint limpios) · SDK sin drift.**

### [x] T-2.09 · Firma respaldada por hardware + control remoto 2.2 — `GATE-HW`
- **Componente:** api + mobile
- Llave por operador en Secure Enclave / Android Keystore (no exportable), registrada vía
  `/me/device-keys`; las acciones críticas firman la **intención** `{key_id, signature, nonce
  del servidor, TTL corto}`; el backend la valida y construye el comando por el pipeline
  EXISTENTE (`POST /sites/{id}/commands`: HMAC por gateway fail-closed, nonce UNIQUE,
  rate-limit doble 60 s, ack obligatorio `pending→acked/rejected/expired`) — la nube firma el
  comando ejecutable, el teléfono jamás.
- Flujo 2 pasos: precondiciones con estado real prellenado (headcount cerrado) → deslizar para
  activar. "Silenciar" = retirada de la demanda del canal manual: si la alerta vigente mantiene
  la sirena, la UI explica el estado real del ack en vez de fingir éxito.
- Tests: replay de nonce rechazado; gating por `siren_silence`/`manual_activate`; audit con
  hash de la intención. Verificación física contra gabinete con alerta activa = `GATE-HW`.

> **ESTADO (2026-07-16): COMPLETA (código; `GATE-HW` físico pendiente).** **API
> (`commands/intent.py`):** el teléfono firma una INTENCIÓN
> `takab-intent-v1:key_id:site:channel:action:nonce`, NUNCA el comando. Nonce STATELESS
> (HMAC del servidor sobre `sub|site|exp|rand`, TTL 90 s, atado a operador+sitio) emitido por
> `POST /sites/{id}/command-nonce` justo antes del deslizamiento; su UN-SOLO-USO no necesita
> tabla porque viaja como `commands.nonce` (UNIQUE) del comando emitido ⇒ **el replay revienta
> en el INSERT (409)**. `intent_signature_valid` verifica contra `device_keys` (P-256/ECDSA y
> RSA PKCS#1v15, ambas SHA-256 — cubre Secure Enclave y Android Keystore). Ruta TÁCTICA en
> `issue_command`: quien no porta `siren_test` o es surface móvil entra por
> `manual_activate`(activate)/`siren_silence`(deactivate), **solo canal siren**, intención
> OBLIGATORIA; FAIL-CLOSED sin `command_intent_secret` (503); reusa el pipeline existente
> (HMAC por gateway, rate-limit, TTL, ack) con `nonce_override`+`audit_meta` (hash de la firma
> en `audit_log`). Acción nueva de matriz **NO** hizo falta: se apoya en `manual_activate`/
> `siren_silence` de T-2.08. **Móvil:** `security/deviceKey.ts` (react-native-biometrics:
> `createKeys` en hardware no exportable → PEM → `/me/device-keys`, `key_id` en SecureStore,
> re-genera si la llave murió en el HW; `createSignature` con prompt biométrico),
> `security/intent.ts` (canónico ESPEJO EXACTO del servidor — test de paridad),
> `features/control/service.ts` (nonce→firma→POST, traduce 409/429/503/403 a mensajes
> honestos), `ackState.ts` (silenciar con alerta vigente ⇒ "SU DEMANDA SE RETIRÓ · LA SIRENA
> SIGUE ACTIVA", jamás finge éxito), `preconditions.ts` (estado REAL prellenado, no checkbox
> ciego), `ControlSheet.tsx` (2 pasos: checklist → deslizar-para-activar) enlazada desde el
> panel táctico 2.1 gated por `allowed_actions`. **api 873 · web 576 · mobile 150 (tsc+lint
> limpios) · SDK sin drift.** TRAMPAS: `audit_log.object` (no `obj`); `gateways`/`sites` NO se
> truncan ⇒ los tests de comandos usan SITE dedicado con delete-then-insert; `cryptography`
> declarada directa + registrada en el contrato `test_runtime_deps`; jest hoisting exige
> prefijo `mock` en las refs de `jest.mock`; react-hooks/purity veta `Animated.Value`/
> `PanResponder` creados con `useRef(new …)` en render ⇒ `useState(()=>…)` + `useMemo`.
> **`GATE-HW` (físico, PENDIENTE):** verificación en dispositivo real (biometría + attestation)
> y prueba contra un gabinete con alerta activa (silenciar NO apaga; el ack trae el relé
> recalculado). El tono oficial SASMEX y credenciales store siguen en sus gates previos.

### [x] T-2.10 · Cámara forense 2.3 + formulario de daños 2.4
- **Componente:** mobile + api + web (Triage)
- Marca de agua **horneada en el pixel** (fecha-hora del dispositivo + offset NTP del último
  sync, GPS, PGA del gabinete o "PGA: pendiente de sync" — nunca inventado, ID del operador);
  sello "SHA-256"; hash calculado en captura; JSON de metadatos firmado; las fotos jamás van a
  la galería del sistema.
- 2.4: categorías con severidad; "personas atrapadas/heridas" = frente de cola + notificación
  inmediata al SOC (cascada OPS); payload firmado → `damage_reports` + evidencias por el
  pipeline presigned EXISTENTE.
- Aceptación: un reporte móvil aparece en Triage de la consola con evidencias y hashes
  verificados; alterar un byte del blob tras la captura invalida la verificación (test).

> **ESTADO (2026-07-16): COMPLETA (código; `GATE-HW` de captura física en dispositivo).**
> **API:** `POST /incidents/{id}/evidence` (evidence_upload) registra la foto en
> `evidence_objects` (kind=photo, sha256 declarado en captura, `s3_key` con prefijo por tenant)
> y devuelve un **PUT presignado** (el móvil sube sin credenciales AWS); `POST
> /evidence/{id}/verify` **re-hashea el objeto subido y lo confronta con lo declarado** —
> alterar un byte ⇒ `verified=false` (criterio de aceptación, probado con moto subiendo bytes
> reales) — táctico acotado a `site_scope`. `people_at_risk` (categoría `people_trapped`)
> escribe un `incident_action` `damage_people_at_risk` que el orchestrator OPS convierte en
> **email INMEDIATO al SOC** (nuevo pass `_enqueue_people_at_risk`, espejo del dictamen pero sin
> dedup por "atendido" — una vida en riesgo se notifica siempre; idempotente por
> `(action_id, channel)`). Cierra el diferido de T-2.03. **Móvil:** `forensic/watermark.ts`
> (PURO: líneas horneadas con "PGA: pendiente de sync" honesto cuando no hay dato del gabinete;
> sello "SHA-256", jamás siglas de HW inexistente), `forensic/fileHash.ts` (SHA-256 de los
> BYTES crudos — coincide con el server), `forensic/capture.ts` (view-shot compone la marca en
> el bitmap → archivo PRIVADO, jamás galería), `services/evidence.ts` (registro + PUT),
> `damage/categories.ts` (people_trapped = prioridad máxima, frente de cola) + `DamageForm`
> (2.4, severidad por categoría, banner urgente) + ruta `/camera` (2.3, expo-camera). **Web:**
> `StructuralTriage` en el detalle de Triage — reportes de daños ordenados (personas en riesgo
> al frente), categorías/severidad, y **verificación de hash por evidencia** bajo demanda
> (HASH VERIFICADO / HASH ALTERADO / NO SE PUDO VERIFICAR — nunca finge integridad). **api 879 ·
> web 584 · mobile 167 (tsc+lint limpios) · SDK sin drift.** TRAMPAS: `File.bytes()` es ASYNC
> en SDK 57 (await); `Crypto.digest` sobre BufferSource para bytes crudos; el mock de `@takab/
> sdk` de TriagePage no cubría los endpoints nuevos ⇒ stub de `useDamageReports`; `evidence_
> objects`/`gateways` no se truncan (los tests limpian lo suyo). **`GATE-HW`:** captura real con
> cámara + attestation en dispositivo (biometría de firma sigue en T-2.09). Offset NTP del
> último sync y adjuntar el PGA real al sincronizar ⇒ afinado en T-2.11 (sync 2.5).

### [x] T-2.11 · Sync UI 2.5 + headcount 2.6
- **Componente:** mobile + api
- 2.5: cola visible (estado por elemento, progreso, reintento manual, tamaño pendiente); solo
  contiene lo que el teléfono produce (sin miniSEED — sube edge→S3); badge de cifrado solo si
  es literalmente cierto.
- 2.6: roster (`/incidents/{id}/roster`) cruzado con check-ins vía WS (<2 s); contadores a
  salvo / ayuda / sin reporte; filtro "no reportados" + llamada de un toque
  (`user_profiles.phone`); marcación "verificado en persona" = check-in **delegado**
  (`via='delegated'`, `verified_by`) distinguible del propio; "Notificar a no reportados" =
  push OPS (no existe canal de mensajes de texto); **cierre de headcount = acción firmada**
  (precondición del paso 1 de 2.2).

> **ESTADO (2026-07-16): COMPLETA.** **API — roster live <2 s:** migración 0020 extiende
> `takab_notify()` con el tipo `checkin` + trigger AFTER INSERT en `life_checkins` (payload
> MÍNIMO sin PII `{t:'checkin',tenant,site,incident_id}`); el hub lo mapea al topic `incidents`
> y arma un `RosterSignalFrame` DIRECTO del payload (sin re-consulta — es solo invalidación, la
> PII vive en el REST gated `roster_read`); acotado por `site_scope` en la entrega (T-2.08).
> SDK ws.ts +`roster`. **Endpoints de headcount:** `POST .../headcount/close` (roster_read) =
> acción firmada `headcount_closed` — la firma de intención (§2.1-B, verificada contra
> `device_keys` sobre el canónico `takab-headcount-v1`) es OPCIONAL; devuelve el conteo de no
> reportados. `POST .../headcount/notify-unreported` (roster_read) escribe `headcount_notify` y
> el orchestrator lo convierte en **push clase OPS** (nuevo pass `_enqueue_headcount_notify`;
> `_dispatch_push` ahora es CLASS-AWARE — la clase la fija el job, default CRISIS retrocompat;
> el actor de `notify_sent` incluye `action_id` para no colisionar con el push CRISIS del mismo
> incidente en un pass). **Móvil 2.5 (`sync` tab):** cola visible con estado por elemento,
> contadores, tamaño pendiente, reintento manual (`retryFailed`+drainQueue), banner offline
> (expo-network) y **badge de cifrado honesto** (afirma AES-256 SOLO si SQLCipher se verificó);
> `syncView` puro. **Móvil 2.6 (`lista` tab):** roster + contadores del servidor, filtro "no
> reportados" por defecto + llamada de un toque, "verificado en persona" = check-in DELEGADO
> (subject_user_id ⇒ via='delegated'), refresco live por el frame `roster`/incidente del WS
> (<2 s), notificar-a-no-reportados y cerrar-headcount (habilitado solo si todos contabilizados);
> `rosterView` puro. **api 883 · web 584 · mobile 179 (tsc+lint limpios) · SDK sin drift ·
> migración validada (fresca + round-trip + incremental dev).** TRAMPA: dos push del MISMO
> incidente en un pass colisionaban en `uq_incident_actions_ack` (actor+ts) ⇒ el actor lleva
> `action_id`. La firma de hardware del cierre queda OPCIONAL en el cliente (el flujo biométrico
> completo reusa T-2.09; el gabinete físico es GATE-HW).

### [x] T-2.12 · Dictamen 2.7 + liberación de reingreso
- **Componente:** api + mobile
- Push OPS al firmarse el dictamen en consola (firma = rol `inspector`); el PDF es el artefacto
  EXISTENTE de `/incidents/{id}/report` entregado según R7 (`dictamen_read` o push+presigned) —
  no generar un PDF paralelo; folio, firmante, vigencia; cacheado offline.
- "Notificar pisos" = evento backend → fase `reentry_approved` → push de cambio de fase que
  libera las pantallas 1.5; jamás acción local.
- Aceptación en staging: consola-firma → push → PDF visible → ocupantes liberados.

> **ESTADO (2026-07-16): COMPLETA.** **API:** `sign_dictamen` (inspector) ahora, cuando la
> firma es HABITABLE (normal_operation|inhabit_monitor), deja un `incident_action`
> `dictamen_signed` (una firma restringida NO lo deja); el orchestrator lo convierte en **push
> clase OPS de cambio de fase** (`_enqueue_push_for_actions` compartido con headcount) que
> despierta la app → re-lee mobile-state (reentry_approved) → libera 1.5. `GET
> /incidents/{id}/dictamen` (R7 `dictamen_read`) devuelve el certificado (folio=dictamen_id,
> firmante, fecha, habitable) + el **MISMO** PDF presignado del `report_pdf` existente (jamás
> genera uno paralelo); sin PDF ⇒ `pdf_url=null` honesto; el occupant no tiene `dictamen_read`
> (403). **Móvil:** `certificateView` puro + `DictamenCertificate` (folio/firmante/vigencia,
> sello "FIRMA DIGITAL · INSPECTOR" — §2.1-B, sin siglas de HW; PDF cacheado offline vía
> `File.downloadFileAsync`, sin PDF se declara). Ruta `/dictamen` (táctico) enlazada desde el
> panel 2.1 cuando hay dictamen firmado. **Liberación del occupant:** banner "REINGRESO
> AUTORIZADO" en Home (1.1) cuando `phase==reentry_approved` (la salida de 1.5 ya la hacía la
> máquina de crisis de T-2.05). **api 886 · web 584 · mobile 185 (tsc+lint limpios) · SDK sin
> drift.** El flujo consola-firma→push→PDF→liberación es verificable en staging (GATE-STORE
> para el push físico; el push OPS es informativo, jamás CRISIS: reingreso aprobado no es
> alerta).

### [x] T-2.13 · Pánico de occupant por quórum-de-2 (1.9)
- **Componente:** api + mobile
- `POST /sites/{id}/manual-activation-votes` sobre la tabla LATENTE `manual_activation_votes`
  (índice `site_id+created_at DESC` ya existe); quórum = **2 votos de usuarios distintos en
  30 s** ⇒ comando de sirena por el pipeline existente + votos `consumed`; acción `panic_vote`
  (solo `occupant`); rate-limit por usuario; todo voto audita.
- UI 1.9: botón mantener-presionado + estado "1 de 2 · expira en N s"; texto claro de que NO
  es la alerta sísmica (emergencia del inmueble: incendio, intrusión…).
- Tests: 1 voto JAMÁS activa; 2 votos del MISMO usuario JAMÁS activan; 2 usuarios distintos en
  ventana ⇒ comando + audit; fuera de ventana ⇒ nada; voto CON GPS fuera del radio del sitio ⇒
  descartado (**geofence best-effort**, RBAC §4.3); voto SIN GPS ⇒ cuenta.

> **ESTADO (2026-07-17): COMPLETA.** **API** (`POST /sites/{id}/manual-activation-votes` en el
> router de comandos, gated `panic_vote` = SOLO occupant): R2 (occupant enrolado o 404) →
> rate-limit por usuario (`panic_vote_rate_per_min`) → **geofence best-effort** con
> `ST_DWithin(site.geom, punto, radio)` (True dentro/False fuera/None sin GPS): fuera ⇒
> `discarded` SIN insertar; sin GPS ⇒ cuenta → INSERT del voto → **quórum = 2 usuarios
> DISTINTOS con voto NO consumido en la ventana de 30 s** ⇒ `issue_signed_command` (sirena,
> activate, `source=panic_quorum`) por el pipeline HMAC EXISTENTE (la nube firma, el teléfono
> jamás) + `CONSUME_PANIC_VOTES` (un solo disparo). TODO voto audita. Los 7 invariantes
> probados (1 voto no activa; 2 del mismo usuario no; 2 distintos ⇒ comando+audit+consumed;
> fuera de ventana no; GPS fuera de radio descartado; sin GPS cuenta; solo occupant vota).
> **Móvil (1.9)**: ruta `/panic` (occupant) con `PanicButton` mantener-presionado (barra ~1.5 s,
> evita disparos accidentales), `panicView` puro (copy con el DISCLAIMER "NO es la alerta
> sísmica · emergencia del inmueble · requiere 2ª persona"; estados contado/activado/descartado;
> `windowRemaining` cuenta atrás), GPS adjunto solo con consentimiento; enlace desde Home (1.1).
> **api 893 · web 584 · mobile 190 (tsc+lint limpios) · SDK sin drift.**

### [x] T-2.14 · E2E + hardening + runbook de cierre de fase
- **Componente:** mobile + docs
- E2E (Maestro preferido, o Detox): crisis→check-in→sync; táctico foto→formulario→sync→Triage;
  dictamen→liberación; pánico 2/30 s; TODOS los flujos offline de la spec §4.2 en modo avión.
- Hardening: certificate pinning + rotación documentada; sin secretos en el bundle; lint/tests
  con cero warnings; sin stubs silenciosos (disciplina de auditoría de honestidad).
- Runbook de cierre con GATEs no auto-verificables: `GATE-DECISIONS`, `GATE-STORE`, `GATE-HW`
  (incluye verificar contra hardware que los modos de prueba del gabinete no alertan móviles)
  y `GATE-LEGAL` (aviso LFPDPPP + `compliance_labels` con el marco normativo correcto —
  pregunta abierta #1 del ANALISIS).

> **ESTADO (2026-07-17): COMPLETA (código+docs; los GATEs físicos quedan escritos sin marcar).**
> **E2E Maestro** (`mobile/.maestro/`): 5 flujos de los caminos §4.2 — crisis→check-in→sync,
> foto forense→daños→Triage, dictamen→liberación, pánico quórum-de-2, offline en modo avión —
> + subflujos de login (occupant/táctico) y README. Corren contra un development build en
> dispositivo (evidencia ejecutable de `GATE-HW`, incluye verificar que los modos de prueba del
> gabinete NO alertan móviles). **Hardening:** cero `<Pending>` (última cuenta táctica ahora usa
> `AccountScreen` compartida — sin fila TOTP para el táctico); `.env` gitignored y sin secretos
> en `src` (solo `EXPO_PUBLIC_*` estáticos); badge de cifrado honesto; lint/tests con CERO
> warnings; la superficie sensible jamás confía en el cliente. **Certificate pinning:** decisión
> de ingeniería documentada (pin al SPKI del intermedio Let's Encrypt + backup del root vía
> expo-build-properties, NO al leaf que rota; rotación con dos pines conviviendo; verificación
> con mitmproxy) — el pin real es `GATE-HW` (no se hornean pines de producción en el repo de
> features). **Runbook** `takab-docs/runbooks/RUNBOOK-cierre-fase2.md` con la matriz pantalla→
> tarea→evidencia y los 4 GATEs (`DECISIONS`: entitlement Apple en trámite; `STORE`: credenciales
> APNs/FCM + apply + tono SASMEX licenciado; `HW`: biometría/attestation/cámara/pinning/E2E;
> `LEGAL`: marco normativo — pregunta abierta #1 — + `compliance_labels` + aviso LFPDPPP).
> **api 893 · web 584 · mobile 190 · SDK sin drift.**

---

## Registro de hotfixes de operación continua (2026-07-25 … 2026-07-30)

> No son tareas planificadas: son fallos que destapó tener el sistema corriendo semanas seguidas, y
> se arreglaron en caliente. Se anotan aquí porque `CLAUDE.md §6` exige que nada aterrice en `main`
> sin registro, y porque varios cambian invariantes que otras tareas dan por ciertos.
>
> **Hilo conductor de casi todos:** un dato que MIENTE es peor que uno ausente (regla de oro 7).
> La alarma que decía "todo bien", la que se trabó diciendo "caído", la ficha de flota con un SHA
> que iba a quedarse obsoleto, y un test que asertaba sobre una muestra al azar — los cuatro
> presentaban como cierto algo que no habían medido.

- **[x] Un rechazo de PIN se susurraba y costó una alerta real a la nube** (PR #32). En la
  prueba del WR-1 (2026-07-31) un armado del modo prueba falló con 401 — el PIN se re-pide al
  recargar — y el único aviso era el mensajito junto al input, invisible a distancia de muro:
  el disparo salió a la nube como incidente real con correos. Doble fix de UX/contrato: (1)
  todo rechazo (401/403/429/sin-red) se **GRITA** en un banner ámbar `role=alert` con el
  NOMBRE de la orden (`ORDEN RECHAZADA · MODO PRUEBA WR-1 — PIN INCORRECTO`), se desvanece
  solo a los 10 s desde el frame loop (cero timers nuevos) y una orden aceptada lo baja; (2)
  sin PIN capturado **ya no se manda el header** — el servidor trata la ausencia como "la
  página pregunta" (401 que NO cuenta), así que sondear ya no quema intentos del lockout.
  Verificado con navegador real contra un panel con PIN: 5/5 (incluidos 6 sondeos sin header
  seguidos de un PIN correcto que entra). *La confirmación fiable de un armado remoto es
  `test_mode_on · lan` en `status().events`, no el botón.*

- **[x] `relay_states()` reventaba con KeyError si el panel preguntaba DURANTE el shutdown**
  (PR #29). Pescado en el journal en el deploy de la Fase 2.1 (2026-07-30): `_on_stop` de gpio
  vacía `_relays`/`_energized`, pero los hilos HTTP del panel son daemon y un kiosco con
  keep-alive a 1 Hz puede colar un `status()` en esa ventana ⇒ `self._energized[channel]` sobre
  el dict vaciado ⇒ 500 al kiosco. Doble fix: `relay_states()` itera el dict REAL bajo un solo
  lock (módulo detenido ⇒ **lista vacía** — los dispositivos están cerrados y su estado ya no se
  mide; inventar 5 filas sería peor, regla de oro 7) y el panel gana `_relays_section()`
  defensiva — `relays` era la ÚNICA pieza de `status()` sin cinturón. 3 tests de regresión
  (incluida la reproducción exacta: gpio detenido + GET por HTTP ⇒ 200 con `relays: []`).

- **[x] El hilo de reconexión a la nube MORÍA por desborde del backoff** (`737dd73`, PR #8).
  Tras ~1024 intentos (17 h sin WAN) el cálculo del backoff desbordaba y el hilo `cloud-reconnect`
  moría: el gabinete quedaba **sin publicar EN SILENCIO** — 41 h, 3 300 mensajes en el spool
  (2026-07-25). El spool y la protección local funcionaron; lo que falló fue volver.
  *Al diagnosticar el journal del edge, filtra `grep -v takab_edge.seedlink` o el ruido lo tapa todo.*

- **[x] La alarma de gabinete offline mandaba un "TODO BIEN" FALSO** (`ea9d549` + `5204713` +
  `d9ee0a2`, PRs #10/#11). Disparaba con el LWT y **se auto-declaraba OK ~15 min después**; pasó en
  los 5 cortes de julio-2026 (24, 27 ×2, 28) y el del 28-jul mintió >15 h.
  La causa: `Takab/Fleet/<gateway_id>` es una métrica **por evento** (1 al conectar, 0 al perder el
  enlace) y entre transiciones **no hay datapoints nunca**, así que `treat_missing_data` lo decide
  todo. El latch correcto es **`ignore`**, no `missing` — trampa del nombre: `missing` NO retiene
  (verificado en vivo con `set-alarm-state`: CloudWatch devuelve la alarma a `INSUFFICIENT_DATA` en
  ~1 min). Y aun con `ignore` hace falta `insufficient_data_actions`, o una alarma recién creada se
  queda muda para siempre: «no sé nada de este gabinete» es tan accionable como «está caído»
  (regla de oro 7). La alarma `sensor-mudo` de T-1.66 **sigue en `notBreaching` a propósito** — es
  una métrica continua, no de estado, y cada alarma dice UNA cosa.
  - [x] **Aplicado (2026-07-30)** — y el `apply` destapó que **`ignore` tampoco servía**: ver abajo.

- **[x] `ignore` se TRABÓ diciendo "caído" 4 h con el gabinete sano ⇒ la alarma de presencia NO
  puede vivir sobre una métrica por evento** (`3fa29bb`, PR #12). Al volver el gabinete el 30-jul,
  el `0` del LWT y el `1` de la reconexión cayeron **en el mismo minuto**: `Minimum` sobre la
  ventana de 5 min se quedó con el `0` y, sin datapoints nuevos, `ignore` lo congeló. La mentira
  inversa, igual de inútil — y una alarma trabada es como se aprende a ignorarlas.
  **Se agotaron los cuatro valores de `treat_missing_data` contra producción y cada uno falló
  distinto** (`notBreaching` mintió · `missing` quedó muda · `ignore` se trabó · `breaching`
  alarmaría siempre). La raíz no era el parámetro: un desconectar+reconectar dentro de una misma
  ventana es **ambiguo por construcción** y CloudWatch no sabe expresar "el último valor".
  **Fix:** `gateway_offline` pasa a vigilar la **AUSENCIA del heartbeat** — `SampleCount` de
  `Takab/Sensor` (que ya llega 1/min) con `breaching`, 2 periodos de 5 min. Sobre una métrica
  PERIÓDICA el silencio significa una sola cosa, y la alarma **vuelve a OK sola**: no puede mentir
  ni trabarse. Coste aceptado: detección en ~10 min en vez de ~1 — irrelevante, porque esto NO está
  en el camino de actuación (SASMEX→sirena es local y determinista, reglas de oro 1 y 2).
  *Verificado en vivo:* forzada a ALARMA con el gabinete sano, se curó sola en 50 s (con `ignore`
  se quedaba trabada); y el reinicio del edge del 30-jul **no la disparó**, cuando con el diseño
  por LWT habría dado un falso positivo por una operación de mantenimiento rutinaria.
  Las reglas IoT que publican `Takab/Fleet` **se conservan por su valor forense** — son el registro
  de cuándo cayó y volvió cada gabinete, y fueron lo que permitió ver que los dos datapoints
  compartían minuto.
  - **Técnica reutilizable:** `set-alarm-state` + observar 2 min verifica un latch **sin esperar al
    siguiente corte real**. Es lo que convirtió cada iteración de "creo que ya quedó" en un dato.
  - **`terraform fmt`/`validate` NO miran semántica:** una alarma mentirosa los pasa sin despeinarse.
    Por eso el PR trae los primeros **tests de terraform** del repo (`.tftest.hcl`, plan-only con
    credenciales falsas ⇒ CI sigue hermético) que fijan qué significa el silencio en cada alarma.

- **[x] `make` no cubría `mobile/` ⇒ `main` estuvo en rojo 8 días** (`398a9e4` + `b7ddf50`, PR #9).
  El timeout de jest era el **costo del primer render** (~3 s de 5), no un test colgado. Ahora
  `make test`/`make lint` cubren mobile, existe `make drift` (3 gates) y CI verifica design-tokens.
  Se descubrió además que `make test` **no corría en una máquina limpia**: usaba `pytest` pelado (no
  está en el PATH; la línea siguiente ya usaba `uv run`) y apuntaba la suite de api a `takab`, cuya
  semilla de desarrollo produce **12 failed + 90 errors FALSOS**. Nuevo target `test-db` que crea
  `takab_test`; CI nunca lo sufrió porque su Postgres nace vacío en cada corrida.

- **[x] Re-aprovisionar un gabinete le BORRABA la configuración** (`eb6cf99`, PR #13). Cierra el
  gotcha que T-1.70 solo documentaba. `provision_gateway.sh` instalaba el `edge.env` con `sudo tee`,
  que **sobrescribe el archivo entero**, y solo genera 3 claves — pero `gw-dev-0001` tenía 15: la
  estación, el host de SeedLink, las rutas de los certificados y **las dos calibraciones MEDIDAS**.
  Correrlo sobre el gabinete vivo lo habría dejado **sin sensor y sin calibración**, y el
  `RUNBOOK-ALTA-DE-ESTACION.md` manda correr justamente ese script: el arma estaba cargada dentro de
  un procedimiento documentado. Ahora **fusiona** (`infra/scripts/merge_env.py`, con tests): actualiza
  solo lo suyo, conserva el resto con comentarios y orden, y deja respaldo fechado en el dispositivo.
  Regla del merge: *no decide qué configuración es correcta; lo que no entiende, no lo toca.*
  *Verificado en seco contra el `edge.env` REAL del Pi: 15 claves antes → 15 después (3 actualizadas,
  12 conservadas por nombre). Con el comportamiento anterior habrían quedado 3.*

- **[x] La IDENTIDAD del gabinete salía de un default horneado** (`e0099e4`, PR #14).
  `TAKAB_EDGE_GATEWAY_ID` **no estaba** en el `edge.env`: el gabinete se identificaba con
  `settings.py:100` (`gateway_id: str = "gw-dev-0001"`), que coincide **por casualidad** con el
  nombre del primer gabinete real. La **segunda estación** habría arrancado publicando como la
  primera — mismo client-id MQTT (`iot_thing or gateway_id`) y telemetría atribuida al sitio y al
  **TENANT equivocados** (regla de oro 5). No se ve hasta que hay dos gabinetes, y para entonces los
  datos ya están cruzados. El aprovisionamiento ya recibía el `thing_name`; ahora lo escribe, junto
  con `DEV_MODE=false` (su default es `true`, y un gabinete de campo que lo herede corre en modo
  desarrollo sin que nadie lo note).

- **[x] `gateways.fw_version` se anotaba A MANO ⇒ iba a pudrirse en silencio** (`67d7f1d`, PR #15).
  Se llenó una vez (`737dd73`) y **desde el siguiente despliegue habría mentido**, porque nadie lo
  actualizaba. Mismo agujero que `/api/health` cerró para la nube, y se cierra igual: haciendo que
  el sistema lo **DECLARE**. `deploy/edge/deploy.sh` escribe el SHA en `edge/FW_VERSION` (después del
  rsync: `--delete` lo borraría antes; `--dirty` deliberado) → el edge lo lee en **cada** snapshot y
  lo publica → la ingesta lo persiste con `IS DISTINCT FROM` (no escribe fila si no cambió, y llega
  1/min: regla de oro 10). **Invariante: un `None` NO pisa lo conocido** — un contrato viejo o un
  deploy a medias no pueden dejar la ficha en blanco. La ingesta valida el valor (≤64): no confía en
  el dispositivo. Contrato **1.6.0 ADITIVO**. `edge/FW_VERSION` va a `.gitignore` (commitearlo haría
  que el rsync empujara un SHA viejo).
  *Verificado end-to-end contra hardware real: `737dd73` → `f3ac4fe` **solo**, sin SQL.*
  **Trampa: el ciclo necesita LAS DOS mitades desplegadas.** Con el edge en `f3ac4fe` y la nube aún
  en `8bad0b3`, el heartbeat llevaba la clave y la nube la ignoraba en silencio (aditivo ⇒ no rompe).
  Un `curl /api/health` lo destapó en una petición.

- **[x] El test de lag del Shake asertaba sobre una muestra AL AZAR** (`ee62325`, PR #16).
  `last_lag_s < 3.0` tomado justo tras conectar: el valor oscila en **diente de sierra**, así que el
  test era flaky por construcción — 0.44 s y 5.86 s en la MISMA máquina con minutos de diferencia.
  Llevaba meses sin delatarse porque el test se salta si el Shake no es alcanzable, y el sensor
  estuvo caído. La primera hipótesis (artefacto de medir por WiFi) resultó **falsa**: fallaba también
  EN el Pi. Medido antes de tocar nada, 1 muestra/s: gabinete `min 0.32 · mediana 1.31 · max 2.35`;
  laptop `min 0.27-0.49 · mediana 1.51 · max 2.95`. **El MÍNIMO es estable y casi idéntico desde
  ambos puntos** ⇒ el problema era el estadístico, no el punto de vista. Ahora se asierta el mínimo
  de una ventana de 20 s (que es lo que el gate #3 pregunta: *cuán fresco llega a estar el dato*) y
  se imprimen min/mediana/max siempre, para que un fallo futuro traiga ya la distribución.
  `health/__init__.py` ya lo sabía desde T-1.65 (`LAG_WARN_S = 15`); el test se había quedado atrás.

- **[x] Redespliegue de la nube a Fase 2** (`8bad0b3` → `f3ac4fe`, 2026-07-29/30). La nube corría
  `9d16056`/alembic `0016` del 14-jul — **82 commits y 4 migraciones atrás**: toda la Fase 1.10 y la
  superficie móvil estaban en `main` pero **no vivas** (de ahí el 401 del `/me` móvil). Aplicadas
  `0017`→`0020`. Runbook: `takab-docs/runbooks/RUNBOOK-redeploy-fase2.md`.
  **Y se cerró la razón por la que nadie lo notó:** `/api/health` ahora declara el commit desplegado
  (`TAKAB_API_BUILD_SHA`, inyectado desde `CLOUD_TAG`), así que "¿qué corre en producción?" es un
  `curl` y no una expedición por SSM. Se pagó solo el mismo día, dos veces.

---

## Fase 2.1 · Los datos que el panel del gabinete todavía no produce (T-2.15…T-2.23)

> **Origen (2026-07-29).** Mauricio pidió rediseñar la pantalla local del gabinete para que
> muestre **ondas de movimiento en vivo por canal, un mapa con la estación y su información, y
> toda la estadística de los movimientos**. La spec de diseño está en
> `takab-docs/design/edge-panel/ESPECIFICACION-PANEL-GABINETE.md` y se entrega a Claude Design;
> su §5 lista los **ocho prerrequisitos P-1…P-8** que esta fase implementa. Las tareas de abajo
> son 1:1 con esos identificadores.
>
> **El diagnóstico:** el panel actual (`edge/takab_edge/local_api/index.html`, 371 L) es 100 %
> numérico y **el backend no produce los datos** para nada de lo pedido. Verificado contra el
> código el 2026-07-29:
> - **No hay historia de muestras.** `FeatureExtractor` guarda solo el ÚLTIMO `Feature1s` por canal
>   (`_by_channel`) y un `_context` privado acotado a `nlta` (~5 s). El `RingBuffer` miniSEED
>   existe pero está **en disco** y `supervisor.py` **ni se lo pasa al `LocalDashboard`**. No hay
>   endpoint de waveform.
> - **El gabinete no sabe dónde está.** Cero `lat`/`lon` en `config/settings.py` y en
>   `contracts.py`. Tampoco conoce estaciones vecinas (el quórum vive en la nube, [ANALISIS-00]).
> - **Cinco métricas ya medidas nunca salen del proceso:** umbrales vigentes, latencia del reflejo,
>   latencia del motor de reglas, contadores de SeedLink y autonomía del UPS.
>
> **Agrupación práctica.** T-2.16, T-2.17, T-2.18 y T-2.21 son todas de la misma forma —
> *exponer en `/api/status` lo que ya vive en memoria* — y pueden aterrizar en un mismo PR con un
> solo ciclo de DoD. T-2.15, T-2.19, T-2.20 y T-2.22 sí son trabajo independiente.
>
> **Alcance de esquema.** T-2.16/17/18/21 tocan **solo `/api/status`** (contrato del panel, no
> viaja a la nube) ⇒ sin cambio en `shared/schemas`. **T-2.22 SÍ toca `HealthSnapshot`**, que es
> contrato compartido con la ingesta ⇒ cambio **ADITIVO** y bump de versión, igual que hizo
> `disk_used_pct` en T-1.53. **CORRECCIÓN al verificar el código:** el archivo es
> `shared/schemas/health_snapshot.schema.json`; y `SCHEMA_VERSION`
> (`edge/takab_edge/schemas.py`) es **global** — un bump reescribe los 9 schemas. (La nota
> original decía "va en 1.5.0" con la 1.4.0 vigente; para cuando se implementó, la vigente era
> 1.6.0 ⇒ **aterrizó como 1.7.0** — otro número escrito a mano que envejeció en silencio.)
>
> **T-2.23 cierra la fase (decisión de Mauricio, 2026-07-29).** T-2.15…T-2.22 producen datos que
> **ningún cliente consume**: sin T-2.23 la fase termina con ocho tareas verdes y cero cambio
> visible en el inmueble. El rediseño del panel entra en el alcance.
>
> **El contrato de los campos nuevos está CONGELADO** en la **§5.1 de la spec de diseño** — claves
> exactas, unidades y semántica de `null` — porque los entregables visuales los produce Claude
> Design y no puede dibujar contra un contrato inventado. Implementar con nombres distintos rompe
> el diseño: si hay que desviarse, se actualiza la §5.1 primero.
>
> **Invariantes que ninguna de estas tareas puede romper** (`CLAUDE.md §2`, blueprint §2):
> el camino de actuación sigue siendo determinista y no depende de nada de esto · `status()`
> **jamás** ejecuta sondas ni publica · toda sección nueva es **defensiva** (módulo roto ⇒ `null`
> y GET 200, nunca 500) · `null` = «sin dato» y se pinta `S/D`, jamás un valor optimista ·
> logging por evento, no por intervalo · nada de recursos externos ni `localStorage` en el panel.

### [x] T-2.15 · Ring de muestras en RAM + endpoint incremental de forma de onda — `P-1`
- **Componente:** edge · **Depende de:** — · **Habilita:** spec §6 (las ondas en vivo)
- **El hueco:** las muestras crudas (`WaveformPacket.samples: list[int]`, counts del ADC 24-bit)
  cruzan `seedlink → signal → buffer` y **nunca llegan a `local_api`**. Lo único graficable hoy
  sería un sparkline de features a 1 Hz, que es una envolvente, no un sismograma.
- **Diseño:** `WaveformRing` en `signal/`, alimentado desde el **mismo punto donde ya se decodifica
  el paquete** para calcular features (sin decodificar dos veces, sin hilo nuevo). Retiene **60 s a
  100 sps por canal**: 4 × 6 000 muestras `int32` ≈ 96 KB — irrelevante para el Pi 4. **El ring
  guarda resolución completa; la decimación se hace al servir**, no al almacenar.
- **Endpoint:** `GET /api/waveform?since=<cursor>&channels=<lista>&max_points=<n>` — **lectura
  abierta** como `/api/status` (es el panel del guardia). Devuelve por canal las muestras nuevas
  desde el cursor + el cursor siguiente + `sample_rate` efectivo y el factor de decimación
  aplicado. A 1 Hz eso son ~50 muestras × 4 canales ≈ 2 KB por petición.
- **Decimación honesta:** envolvente **min/max por bucket**, no submuestreo ingenuo — el
  submuestreo se salta el pico y dibuja un sismo más chico del que fue. La respuesta **declara**
  el factor y el `sample_rate` resultante para que la UI lo rotule (spec §6.4).
- **Hueco de cursor:** si el `since` que manda el cliente ya se cayó del ring (pestaña dormida,
  reconexión), responder la ventana completa con `reset: true` — el cliente redibuja en vez de
  empalmar dos tramos discontinuos como si fueran continuos.
- **Criterios de aceptación:**
  - [x] El ring conserva 60 s por canal y descarta lo viejo sin crecer sin límite (tope por
        muestras, no por tiempo de reloj).
  - [x] Alimentarlo **no** agrega hilos ni bloquea el camino de features (mismo lock/estructura
        que `live_by_channel()`; copia defensiva al servir).
  - [x] La decimación min/max **preserva el pico**: un test con un impulso de una sola muestra
        sigue mostrando esa amplitud tras decimar.
  - [x] Peticiones incrementales consecutivas reconstruyen la señal sin huecos ni duplicados.
  - [x] `since` caducado ⇒ ventana completa + `reset: true`.
  - [x] Módulo `signal` caído ⇒ **200** con carga vacía, nunca 500.
  - [x] El endpoint **no** publica nada a la nube ni ejecuta sondas (regresión hermana de
        `test_status_does_not_publish_health` — `test_waveform_does_not_publish_nor_probe`).
  - [x] Sin streaming continuo a la nube: esto es **solo** LAN (blueprint P6, regla de oro 9).
- **Cierre (2026-07-30):** `signal/waveform.py` — `WaveformRing` con **cursor global** por
  muestras (stateless, sin estado por cliente), buffer circular int32 dimensionado con el primer
  paquete del canal, y **marks a paquete completo**: en cuanto una muestra se sobrescribe, su
  paquete entero deja de servirse y sube el piso de reset (jamás un tramo a medias). Gap por
  `next_starttime` (tolerancia 0.6/sr); **corte honesto**: hueco a mitad del rango ⇒ se sirve
  solo el tramo posterior al último gap. Decimación min/max con **pares aplanados** (amend §5.1;
  también quedó especificada la forma degradada). `FeatureExtractor.process` alimenta el ring en
  try/except (las features jamás mueren por él). `do_GET` refactorizado a `partition("?")`;
  params ilegales ⇒ defaults (clamp [50, 6000], default 1500). 12 tests nuevos (9 ring + 3 HTTP).

### [x] T-2.16 · Exponer los umbrales vigentes y la versión de config — `P-2`
- **Componente:** edge · **Depende de:** — · **Habilita:** spec §8.1 (proximidad al disparo)
- **El hueco:** `ThresholdBand` (`pga_watch_g=0.040`, `pga_trip_g=0.060`, `pgv_watch_cms=2.0`,
  `pgv_trip_cms=4.0` por defecto, perfil hospital) vive en el gabinete y **no sale en
  `/api/status`** ⇒ hoy es imposible pintar cuánto falta para disparar, ni las líneas de umbral
  sobre las trazas de T-2.15.
- **TRAMPA (T-1.71):** los umbrales se aplican **EN VIVO** desde la nube
  (`ConfigStore.add_apply_listener` → `RuleEngine.apply_thresholds`). Hay que exponer **los que
  el motor tiene vigentes**, no los de `EdgeSettings` estáticos — si no, tras una actualización
  el panel pinta una línea de umbral que ya no es la que dispara.
- **Criterios de aceptación:**
  - [x] `/api/status` incluye los 4 umbrales vigentes + `config_version`.
  - [x] Tras un `apply_signed_update` que cambie umbrales, el siguiente GET ya refleja los nuevos.
  - [x] `rules` caído ⇒ sección `null`, GET 200.
- **Cierre (2026-07-30):** los umbrales salen del MOTOR (`rules.thresholds`, rebind vivo de
  T-1.71) y `config_version` de `ConfigStore.version`. Amend §5.1: `config_version` es
  `int|null` (null = store roto/ausente). Tests: `test_status_exposes_live_thresholds_and_
  config_version` · `test_thresholds_reflect_signed_update` (firma real por HMAC) ·
  `test_thresholds_null_when_rules_broken` (descriptor de DATOS: eclipsa al atributo de
  instancia).

### [x] T-2.17 · Exponer las latencias de la cadena crítica — `P-3`
- **Componente:** edge · **Depende de:** — · **Habilita:** spec §8.4
- **El hueco:** `gpio.last_reflex_latency_s` (latencia medida SASMEX→relé; **6.65 ms** con hardware
  real en T-1.69) y `rules.last_latency_s` **ya se miden y no se exponen**. Es el dato de oro del
  gabinete: la prueba viva de que responde.
- **Criterios de aceptación:**
  - [x] `/api/status` incluye ambas latencias, en segundos, con sus presupuestos declarados
        (reflejo p95 < 100 ms · reglas p95 < 200 ms) para que la UI las pinte **contra** el
        presupuesto, no en el vacío.
  - [x] Sin medición todavía ⇒ `null` (la UI pinta `S/D`). **Jamás un `0.0` fabricado**, que se
        leería como "instantáneo".
- **Cierre (2026-07-30):** sección `latencies` (nunca null; campos medidos sí) con presupuestos
  `_REFLEX_BUDGET_S=0.100` / `_RULES_BUDGET_S=0.200` — nacen en `local_api` (contrato del panel,
  no perilla del gabinete). Tests: `test_latencies_budgets_declared_and_null_before_measurement`
  · `test_latencies_after_measurement` (reflejo vía `simulate_sasmex`, motor vía `feed`).

### [x] T-2.18 · Exponer los contadores del flujo SeedLink — `P-4`
- **Componente:** edge · **Depende de:** — · **Habilita:** spec §8.3
- **El hueco:** `SeedLinkClient` expone `packets_seen`, `reconnects`, `duplicates` y `gaps` como
  propiedades públicas. Al panel solo llega `last_lag_s` (vía `health.seedlink_lag_s`) y `gaps`
  indirectamente dentro de `packet_loss_pct`. Un técnico en sitio no puede distinguir "el enlace
  al Shake se cae y se levanta" de "el Shake manda con huecos".
- **Contexto que lo justifica:** el sistema estuvo **15 h ciego** (T-1.65/66) con la consola
  diciendo OPERATIVO. Estos cuatro contadores son la evidencia de degradación temprana.
- **Criterios de aceptación:**
  - [x] Los 4 contadores en `/api/status`, rotulables como acumulados **DESDE EL ARRANQUE**.
  - [x] Sin cliente SeedLink (dev/simulador) ⇒ sección `null`, GET 200.
- **Cierre (2026-07-30):** `LocalDashboard` recibe el cliente por kw-only `seedlink=` (los
  posicionales quedan intactos: la fixture `pinned` construye con 3). Nota: el supervisor dev SÍ
  cablea un `SeedLinkClient` (con simulador) ⇒ la sección sale poblada; `null` es el panel
  parcial sin cliente. Tests: `test_seedlink_counters_exposed_since_boot` ·
  `test_seedlink_section_null_without_client`.

### [x] T-2.19 · Agregador rodante de sacudida — `P-5`
- **Componente:** edge · **Depende de:** — · **Habilita:** spec §8.2 (histórico de sacudida)
- **El hueco:** no existe ninguna agregación temporal en el edge. El panel no puede decir "el
  máximo de hoy fue X" ni "el ruido de fondo va subiendo".
- **Diseño:** agregador **en RAM** en `signal/`: PGA/PGV máximo por hora (24 buckets rodantes) y
  máximo de 24 h por canal, conteo de eventos por tier, y tendencia del ruido de fondo contra el
  piso conocido del sensor (**0.6–1.1 mg** medidos en T-1.41). 24 × 4 canales es trivial en
  memoria.
- **NO es logging por intervalo** (regla de oro 10): es un agregado en memoria que **no se publica
  ni se persiste**. Nada nuevo viaja a la nube — la nube ya tiene sus continuous aggregates
  (`site_metrics_1m` / `site_metrics_1h`).
- **Criterios de aceptación:**
  - [x] Máximos por hora y 24 h por canal, conteo de eventos por tier, tendencia de ruido.
  - [x] Los buckets rotan por tiempo y no crecen sin límite.
  - [x] Se pierde al reiniciar **a propósito** y se rotula **DESDE EL ARRANQUE** hasta acumular
        24 h — sin fingir una continuidad que el gabinete no tiene.
  - [x] Cero publicaciones nuevas a la nube (test de regresión).
- **Cierre (2026-07-30):** `signal/aggregate.py` — buckets horarios UTC-floor podados por el
  reloj DEL DATO (determinista); `events_by_tier` cuenta **transiciones** (arranca en `normal`:
  el primer tick no cuenta; un `watch` sostenido es UN evento) y lo alimenta un observador en el
  SUPERVISOR tras `_act_and_publish` — en AMBAS rutas, `_on_packet` y `_on_sasmex` (la escalación
  SASMEX no pasa por `_on_packet` y se habría perdido). Piso de ruido: MIN/minuto del rms→mg del
  MEMS (EH\* excluido — no es aceleración), deque 180 min, tendencia mediana 15v15 ±20%.
  Amend §5.1: `current_mg` es `float|null`. 12 tests nuevos.

### [x] T-2.20 · Coordenadas del sitio (y vecinos opcionales) — `P-6`
- **Componente:** edge (+ config sync) · **Depende de:** — · **Habilita:** spec §7 (el mapa)
- **El hueco (el más sorprendente):** **el gabinete literalmente no sabe dónde está.** No hay
  latitud ni longitud en `config/settings.py` ni en `contracts.py`. Sin esto no hay mapa de
  ninguna clase.
- **TRAMPA MORTAL (RUNBOOK-ALTA §4):** `provision_gateway.sh` **SOBRESCRIBE**
  `/etc/takab/edge.env` y solo reescribe tres líneas + certs. Coordenadas puestas a mano en
  `edge.env` **se pierden al re-aprovisionar**, igual que ya pasa con identidad, SeedLink y
  calibración.
- **Diseño CORREGIDO (verificado contra el código el 2026-07-29):** el diseño original de esta
  tarea —entregarlas *por* el sync firmado— **las borra**. `ConfigStore.apply_signed_update` hace
  `EdgeSettings.model_validate_json` (`config/store.py:77`) = **reemplazo total**, y la nube publica
  documentos **parciales por diseño** (`api/src/takab_api/commands/sync.py:14`): un sync que solo
  traiga `thresholds` deja `site_lat` en `None`. Hoy el daño está contenido solo porque el único
  listener consume `cfg.thresholds`. El diseño correcto es al revés:
  1. **Fuente de verdad = `edge.env`** (`site_lat`/`site_lon` en `EdgeSettings`), servido desde el
     objeto vivo que el dashboard ya recibe — sobrevive reinicios sin WAN gratis.
  2. **Overlay del sync firmado con merge de solo-no-nulos** («last known good»): un config parcial
     **nunca** puede poner la ubicación en `None`.
  3. **Caché en disco estrecha** (`/var/lib/takab/site_location.json`), escrita solo al aprender una
     ubicación no-nula y **leída una vez al arrancar**, jamás desde `status()`. Deliberadamente
     **no** un caché general del `ConfigStore`: persistir config firmada obligaría a persistir el
     `_high_water` (`config/store.py:36-37`) o un reinicio reabriría la ventana anti-replay — y
     cachear umbrales sí tendría impacto en la actuación. La ubicación no dispara nada.
  4. **Arreglar `provision_gateway.sh` para que preserve.** **YA HECHO antes de esta tarea (PRs
     #13/#14):** el merge idempotente vive en `infra/scripts/merge_env.py` (ruta real; el plan
     original decía `lib/`) con `test_merge_env.sh` en CI. Lo que esta tarea añadió encima:
     flags opcionales `--site-lat/--site-lon` (validados en rango, en PAR) que suman
     `TAKAB_EDGE_SITE_LAT/LON` a las claves gestionadas; sin flags, nada cambia y unas
     coordenadas puestas a mano sobreviven al re-provision (casos nuevos en el test).
- **Vecinos:** lista opcional de estaciones cercanas servida por la misma config, **puramente
  informativa**. Invariante: el quórum se correlaciona en la nube y **JAMÁS** gatea la sirena local
  (blueprint §4.5, SPOF-01, ratificado en Fase 1.10).
- **Criterios de aceptación:**
  - [x] `site_lat` / `site_lon` como `float|None` en la config del gabinete y en `/api/status`.
  - [x] Sin provisionar ⇒ `null` y el panel muestra `SIN UBICACIÓN PROVISIONADA`. **Jamás un punto
        inventado ni un centro por defecto.** (El rótulo lo pinta T-2.23; el dato ya degrada.)
  - [x] Sobreviven a un reinicio sin WAN (caché en disco).
  - [x] Un re-aprovisionamiento **no** las borra (o el runbook documenta el paso de restitución).
  - [x] Los vecinos, si existen, no participan de ninguna decisión de actuación (test).
- **Cierre (2026-07-30):** `config/location.py` — `SiteLocationCache` (objeto plano, NO
  EdgeModule): prioridad env > sync firmado (overlay SOLO-no-nulos, lat/lon en PAR) > caché
  estrecha (`site_location.json`, tmp+`os.replace` 0644, leída UNA vez al construir; `current()`
  jamás toca disco; escritura por evento solo al aprender un par DISTINTO). Vecinos con regla
  «última lista no-vacía». `provision_gateway.sh --site-lat/--site-lon` validados en rango.
  Runbook de alta actualizado (incluye el gotcha histórico ya corregido y `TAKAB_EDGE_NEIGHBORS`
  como JSON). Tests: 10 en `test_site_location.py` (incl. el crux
  `test_partial_signed_config_cannot_null_out_location` y el anti-quórum
  `test_neighbors_do_not_affect_actuation`) + 3 casos nuevos en `test_merge_env.sh`.

### [x] T-2.21 · Bandera de calibración instrumental — `P-7`
- **Componente:** edge · **Depende de:** — · **Habilita:** spec §6.4 y §8 (honestidad de unidades)
- **El hueco:** los defaults de `SignalConfig` (`vel_sensitivity_ms_per_count=1.0e-9`,
  `accel_sensitivity_ms2_per_count=1.0e-6`) son **marcadores de posición**; las reales de AM.R4F74
  son `2.5021894e-9` y `2.6007802e-6` (T-1.41). El edge **no declara** cuál está usando, así que el
  panel no puede saber si `0.15 g` es una magnitud física o un número relativo.
- **Diseño:** `calibration_source: str = ""` en `SignalConfig`, poblado en el aprovisionamiento
  junto con las sensibilidades — **espejo exacto del contrato de la nube**, donde
  `calibrated := (sensors.calibration_source IS NOT NULL)` y no existe checkbox de "calibrado".
- **Criterios de aceptación:**
  - [x] `/api/status` expone `calibrated` (bool) y su procedencia.
  - [x] Vacío ⇒ `calibrated=false` ⇒ el panel rotula **`SIN CALIBRAR`** y usa unidades relativas
        (`rel.`) en vez de `g` y `cm/s`, igual que ya hace la consola web.
  - [x] Default-deny: ausencia de procedencia **nunca** se interpreta como calibrado.
- **Cierre (2026-07-30):** `SignalConfig.calibration_source` (env
  `TAKAB_EDGE_SIGNAL__CALIBRATION_SOURCE`); `calibrated := bool(source.strip())` — puro espacio
  en blanco NO cuenta. La sección NUNCA es null: degrada a no-calibrado con sensibilidades
  `null` (amend §5.1). El rótulo `rel.` lo aplica T-2.23 (el panel); aquí queda el dato. Tests:
  `test_calibration_default_deny` · `test_calibration_with_source_is_true`.

### [x] T-2.22 · Autonomía restante del UPS en el snapshot de salud — `P-8`
- **Componente:** edge + shared/schemas · **Depende de:** — · **Habilita:** spec §8.3
- **El hueco:** `UpsReading` **ya mide** `runtime_s` (autonomía restante) y `HealthSnapshot`
  **lo pierde**: nunca llega al panel ni a la nube. Existe hasta un `ups_label()` que compone
  `EN BATERÍA · RESPALDO 1h 20m`, y solo se usa para logs.
- **Alcance de esquema:** `HealthSnapshot` es contrato **compartido** con la ingesta ⇒ el cambio es
  **ADITIVO** con bump de versión, mismo patrón que `disk_used_pct` en T-1.53. Un consumidor viejo
  no puede romperse por este campo.
- **Criterios de aceptación:**
  - [x] `ups_runtime_s: float|None` en `HealthSnapshot`, en `/api/status` y en `shared/schemas`
        (aditivo, versión bumpeada).
  - [x] UPS ausente o sin reportar autonomía ⇒ `null` ⇒ `S/D`. Nunca un número optimista.
  - [x] La ingesta de la nube acepta el campo nuevo sin romper mensajes sin él (test).
  - [x] **El dato aterriza en la nube:** `battery_min_left` deja de ser siempre `NULL`. La columna
        **ya existe** (`db/schema.sql:362`) y ya viaja `ws/hub.py:74` → `ws/protocol.py:111` →
        `sdk-ts/src/gen/types.gen.ts:1302` ⇒ **cero DDL, cero Alembic, cero regeneración de SDK**:
        son 2 líneas en `api/.../ingest/handlers.py:327-375` (`int(round(runtime/60))`) y actualizar
        `api/tests/test_ingest_handlers.py:404-418`, que hoy afirma `row[11] is None`.
- **Cierre (2026-07-30):** `SCHEMA_VERSION` → **1.7.0** (9 schemas regenerados). La conversión
  s→min guarda de `None` Y de tipos ajenos (bool incluido: subclase de int — un `true`
  manipulado no se vuelve "0 min"). Tests: edge `test_snapshot_carries_ups_runtime` ·
  `test_snapshot_ups_absent_runtime_is_null` · `test_status_health_includes_ups_runtime`; api
  happy path (4500 s → 75 min) + payload 1.6.0 sin la clave ⇒ NULL. Suites: edge 390 · api 903
  (contra `takab_test`; OJO: `DEFAULT_URL` del conftest apunta a `/takab` — exportar
  `DATABASE_URL` a `takab_test` o el seed dev da fallos falsos).

### [x] T-2.23 · Implementar el panel rediseñado — cierra la Fase 2.1
- **Componente:** edge · **Depende de:** T-2.15…T-2.22 **y de los entregables §13 de la spec**
- **Por qué existe:** es la única tarea de la fase que produce algo **visible en el inmueble**. Las
  ocho anteriores habilitan datos; esta los pinta. Sin ella, la fase cierra en verde y el guardia
  sigue viendo el mismo panel numérico de 371 líneas de T-1.53.
- **Entrada:** los 7 entregables de la §13 de
  `takab-docs/design/edge-panel/ESPECIFICACION-PANEL-GABINETE.md`, producidos por Claude Design:
  los 3 modos de densidad con sus breakpoints, los 10 estados completos, el sismograma multicanal
  con sus marcas, el mapa esquemático con degradación sin coordenadas, los 4 bloques de estadística,
  la decisión tipográfica justificada y la barra de acciones con flujo de PIN.
- **Alcance:** reescribir `edge/takab_edge/local_api/index.html` consumiendo `/api/status` y
  `/api/waveform` **según la §5.1 congelada**. Un solo archivo, sin build, sin dependencias — el
  panel se sirve desde el Pi y tiene que funcionar sin internet, para siempre.
- **Invariantes de §9 que el código NO puede renegociar:** la jerarquía de banners y su precedencia
  exacta · los rótulos de tier literales · los 4 estados obligatorios de UI (`loading`/`error`/
  `empty`/`stale`) · `null` se pinta `S/D`, nunca un valor optimista · dato retenido se rotula como
  retenido (regla de oro 7).
- **Criterios de aceptación:**
  - [x] Los 3 modos de densidad (MURO / CONSOLA / CAMPO) responden a sus breakpoints.
  - [x] Los 10 estados de §13.2 se pueden forzar y se ven íntegros, incluido **arranque en frío con
        `signal`, `health`, `shake_history` y `seedlink` en `null` simultáneamente**.
  - [x] El sismograma pinta 4 trazas con umbral, saturación, marca SASMEX y tier; `encoding:
        "minmax"` se dibuja como **banda**, no como línea; `gap_before` corta el trazo.
  - [x] `calibrated: false` ⇒ **`SIN CALIBRAR`** y unidades `rel.` en ondas, estadística y umbrales.
  - [x] `site_lat`/`site_lon` en `null` ⇒ `SIN UBICACIÓN PROVISIONADA`, sin punto inventado.
  - [x] `test_index_has_no_external_resources` extendido: sigue vetando CDN/`https://`/T-MINUS y
        **además** `localStorage`/`sessionStorage` (+`indexedDB`/`WebSocket`/`EventSource`).
  - [x] Un solo tick de polling secuencial a 1 Hz para los dos endpoints (no dos bucles paralelos:
        el servidor HTTP del Pi es de hilos y se duplicarían los hilos retenidos por pantalla).
  - [x] DevTools sin una sola petición fuera de la LAN. (Checklist manual:
        `takab-docs/design/edge-panel/VERIFICACION-T-2-23.md` — el render de canvas se valida a ojo.)
- **Cierre (2026-07-30, PR-6 de la fase):** `index.html` reescrito (142 KB, un solo archivo): des-Reactizado del
  prototipo de Claude Design (~330 L de canvas portadas: trazas min/máx, envolvente B, rosa,
  mapa equirect), DOM estático + `render(status)` imperativo, tick ÚNICO encadenado
  status→waveform (+catalog ~10 min) con backoff 1→2→5 s, buffers cliente preallocados
  min/máx (minmax ⇒ BANDA; `gap_before` ⇒ corte), conciliación §5.1 completa (umbrales/
  latencias/contadores/calibración/ubicación/UPS/shake_history + PGV sobre EHZ y desarme real
  del two-step a 5 s — defectos del prototipo corregidos), 10 escenas `?demo=` con la forma
  EXACTA de §5.1 + ribbon `DEMO · NO ES ESTADO REAL`, `?mode=muro`, accesibilidad
  (focus-ring/aria-live/sr-only/reduced-motion). **Estáticos**: `/fonts/geist.ttf` (variable,
  del entregable) + `/fonts/jbmono.woff2` (subset OFL 26 KB, `pyftsubset` documentado) por
  whitelist exacta (traversal imposible) con `max-age=86400`. **Geografía**: Natural Earth
  50m/10m (dominio público) recortada a México, DP 0.02° + cuantización ⇒ 45 KB inline
  (generador: `takab-docs/design/edge-panel/tools/gen-geografia-mexico.py`). **Catálogo**:
  `GET /api/catalog` (amend §5.1) desde `catalog_path` leído UNA vez; `provision --catalog`.
  `support.js` del entregable queda como referencia (cargaba React de unpkg — descalificado).
  7 tests nuevos + extensión del de recursos. Suite edge: **430**.

### [x] T-2.24 · Feed del catálogo SSN nube→edge, firmado — COMPLETA (2026-07-31)
- **Componente:** edge + api + infra · **Depende de:** T-2.23
- **Qué es:** hoy el catálogo del panel es una **instantánea provisionada a mano**
  (`provision_gateway.sh --catalog`; fecha de captura visible — decisión de alcance de la
  Fase 2.1). Esta tarea lo convierte en un feed **firmado** nube→edge con el mismo mecanismo
  HMAC de la config (dominio propio `b"catalog"`, topic propio `takab/catalog/<thing>`), con
  degradación al último snapshot conocido. El gabinete JAMÁS scrapea al SSN directo: no tiene
  salida a internet y el SSN no es fuente de alertamiento.
- **Criterios:**
  - [x] Archivo atómico (tmp+`os.replace`, 0644) y hot-swap en memoria.
  - [x] Verificación de firma fail-closed (sin verificador se rechaza; firma cubre
        payload+versión; versión monótona anti-replay que **SOBREVIVE reinicios** — viaja en
        el propio archivo como `feed_version`; el archivo provisionado a mano es v0).
  - [x] `captured_at` siempre visible · **sin cambio de contrato en `GET /api/catalog`**.
  - [x] Nube: `POST /gateways/{id}/catalog` (interno-only `takab_superadmin`/`takab_support`,
        auditado `catalog_published`), firma con la clave POR-GATEWAY (sin clave ⇒ 503
        fail-closed), versión monótona en `gateway_catalog_state` (0021; FK `ON DELETE
        CASCADE`), y un publish fallido NO quema versión. La periodicidad es una llamada
        programada al endpoint (ajuste sobre el borrador: push bajo demanda, no worker).
- **Cierre (2026-07-31):** dominio HMAC `catalog` anclado en los **vectores compartidos**
  (`hmac_vectors.json` regenerado con el SecurityManager real; ambos lados truenan ante
  drift). Edge: `takab_edge/catalog.py` (`CatalogStore`, espejo de la doctrina de
  `SiteLocationCache`), sobre por `dispatch.on_catalog` (kind `catalog_update`), suscripción
  en supervisor. **Terraform: `takab/catalog/<thing>` añadido a Subscribe/Receive de la
  política de flota — APLICAR ANTES de desplegar el edge** (la trampa de fase 1.8 al revés:
  una suscripción no autorizada tumba el enlace). Trampas de la ejecución: los roles
  canónicos internos son `takab_superadmin`/`takab_support` (el nombre corto pasa el guard
  propio pero el RLS interno dice no); un UUID de fixture que colisiona con el de otro
  módulo + `ON CONFLICT DO NOTHING` hereda EN SILENCIO el `iot_thing` ajeno. Tests: edge 12
  (store+E2E sobre HTTP) · api 7 (endpoint) · vectores ×2 lados. Suites: edge 446 · api 914.
- **E2E EN VIVO (2026-07-31, PR #36 desplegado: terraform → nube `0549cc5`/alembic 0021 →
  edge al Pi):** push real de una captura del RSS del SSN (15 sismos del día) → `202` v1 →
  el gabinete verificó la firma y cambió EN CALIENTE (journal: «catálogo SSN actualizado por
  feed firmado: v1»; el panel pasó de la instantánea del 17-may a la del día;
  `feed_version: 1` persistida en el archivo). Huella en nube: `gateway_catalog_state` v1 +
  `audit_log` `catalog_published` con el actor real. Enlace del gabinete estable tras la
  suscripción nueva (0 reconexiones, RTT 76 ms, spool 0).

---

### [x] T-2.26 · Cancelar alerta no liberaba UI ni actuadores — `RuleEngine.reset()` + `alert_latched` — CÓDIGO COMPLETO (2026-08-01); verificación en el Pi pendiente de deploy
- **Componente:** edge (rules + gpio + local_api + panel) · **Depende de:** —
- **El bug (observado EN VIVO el 2026-08-01):** tras una alerta instrumental real, CERRAR
  ALERTA limpiaba el GPIO pero el `RuleEngine` no tenía `reset()`: `last_tier` quedaba
  congelado en el tier del episodio (con SeedLink quieto, PARA SIEMPRE) y el banner rojo no
  se iba. Peor: cuando el tier decaía solo a `normal` con los relés AÚN enclavados (estrobo,
  gas, ascensor, retenedores — el enclave es monótono por diseño), el botón CERRAR ALERTA
  desaparecía ⇒ estado IRRECUPERABLE desde el panel. Y `doAction` repintaba con el status
  viejo (sin refetch tras un 200). SILENCIAR solo toca la sirena (NFPA-72) — eso se conserva.
- **Política ratificada (Mauricio, 2026-08-01):** el latch se CONSERVA (nada se suelta solo);
  el fix es visibilidad + reset completo. Two-step de 5 s del CERRAR ALERTA se conserva.
- **Criterios:**
  - [x] `RuleEngine.reset()`: re-arma a NORMAL con `source=manual` (enum EXISTENTE — nada
        nuevo viaja a la nube; el ring de transiciones es solo-panel), limpia features,
        TERMINA el episodio de dedup (re-disparo ⇒ `event_id` nuevo), idempotente, y NO
        puede enmascarar un sismo en curso (la siguiente ventana re-eleva) — 5 tests.
  - [x] `GpioController.alert_latched` (SASMEX latcheado o demanda de rules viva; excluye
        pruebas y `_safed`) expuesto en `/api/status` — 5 tests gpio + 3 local_api.
  - [x] `reset_alert()` = `gpio.reset()` → `rules.reset()` (orden falla-seguro ante disparo
        concurrente: los relés quedan protegidos si el sismo sigue).
  - [x] Panel: CERRAR ALERTA visible SIEMPRE que haya enclave (aunque el tier ya sea
        normal); banner ámbar «ACTUADORES ENCLAVADOS · CIERRE LA ALERTA PARA LIBERAR»
        (el rojo queda EXCLUSIVO de alerta viva); refetch one-shot del status tras un 200
        (sin tick nuevo: `setTimeout(tick` sigue apareciendo 1 vez). Hooks congelados
        nuevos: `alert_latched`, `ACTUADORES ENCLAVADOS`.
  - [x] E2E: SASMEX → protección completa → reset libera TODO → un SASMEX nuevo re-enclava.
  - [x] Suite edge 459 verde · ruff limpio · latch monótono intacto
        (`test_silence_keeps_visual_strobe` sin tocar; `commands_for` solo ACTIVATE).
  - [ ] Verificación en el Pi real (deploy + ciclo WR-1 en modo prueba → enclave → banner
        ámbar → CERRAR ALERTA con PIN ⇒ `last_tier=normal`, `alert_latched=false`).

---

### [x] T-2.25 · Brújula y sismograma saturados por offset DC — media rodante en el cliente — CÓDIGO COMPLETO (2026-08-01); verificación visual en el Pi pendiente de deploy
- **Componente:** edge (panel LAN + simulador) · **Depende de:** —
- **El bug (observado EN VIVO el 2026-08-01):** el punto de la brújula N/S/E/O vivía clavado
  al borde en un cuadrante fijo y la barra Z al 100 %. Causa: `drawRose()`/`drawWaves()`
  convierten counts CRUDOS del ring de `/api/waveform` (gravedad ≈1 g ≈ 3.77e6 counts en
  ENZ + bias MEMS en ENN/ENE) con `toPhys()` SIN restar la media, contra una escala `sc`
  derivada de umbrales que el backend calcula sobre señal DE-MEDIA (~0.069 g) ⇒
  `min(1, v/sc)` siempre 1 y `Math.sign(lastCounts())` constante. Regresión del port del
  prototipo (buffer sintético ya en g y media cero); el simulador con ruido de media CERO
  la enmascaraba en CI y en `?demo=`.
- **Criterios:**
  - [x] Fix 100 % frontend: media rodante DC por canal (EMA τ≈30 s sobre el centro
        `(min+max)/2`, sembrada con el primer tramo — sin rampa desde 0), mantenida en
        `pushSamples()` (1×/tick) y restada en `windowOf()` (solo ranuras llenas) y en
        `lastCounts()` de la rosa. `drawRose`/`drawWaves`/`toPhys` intactos.
  - [x] Contrato `/api/waveform` INTACTO: el ring sigue sirviendo counts crudos (evidencia).
  - [x] `RS4DSimulator` emite EN* con DC realista POR DEFAULT (`DEFAULT_DC_OFFSETS`; media
        cero solo explícita con `dc_offsets={}`) — el bug ya no se puede re-ocultar.
  - [x] `test_features_immune_to_dc_offset`: las features son EXACTAMENTE iguales con o sin
        offset (el backend de-media; offsets enteros ⇒ `rint` conmuta) — congela el
        contrato del que depende el fix.
  - [x] Hook de contrato en el HTML: `media rodante DC`, `- b.dc` ×≥3, `dcReady`.
  - [x] Suite edge verde · ruff limpio · escenas `?demo=` sin cambio visual (onda demo de
        media cero ⇒ EMA≈0).
  - [ ] Verificación visual en el Pi real: en reposo el punto ORBITA EL CENTRO y la barra Z
        está abajo; un golpe junto al sensor deflecta y REGRESA; sismograma centrado con
        banda de ruido visible (no pegado a los rieles).

---

### [x] T-2.27 · Panel LAN: comparativa sismo↔estación con ley de atenuación — COMPLETA (2026-08-01)
- **Componente:** edge (panel LAN) · **Depende de:** T-2.23, T-2.24
- **Qué es:** en el overlay del mapa, seleccionar un sismo del catálogo Y una estación (propia o
  vecina) y ver: distancia epicentral LINEAL con rumbo, hipocentral (con profundidad), arribo P
  teórico (v_P 6.5 espejo del quórum) y la curva PGA-vs-distancia de la ley **ATTEN-LAW v1**
  (espejo de `_plausible_pga_g`, con ancla en su docstring), con PGA MEDIDO superpuesto solo
  bajo tres candados (estación propia + bucket horario de `shake_history` con matching SSN
  UTC-6→UTC declarado + calibración). **NO es el mini-ShakeMap del blueprint §14**: cero
  interpolación espacial, cero IA, y la ley jamás toca el camino de disparo.
- **Criterios:**
  - [x] Selector de estación en `#station-rows` (botones; default propia; vecina sin dato
        medido lo declara: «SOLO LA ESTACIÓN PROPIA MIDE»).
  - [x] Cajón `#cmp-drawer` (cifras + canvas `drawCmpChart()`: X lineal km, Y log décadas,
        banda ilustrativa ×3/÷3, marcadores epicentro/estación/medido) dibujado en el frame
        loop bajo `S.overlay` — cero timers nuevos (`setTimeout(tick` sigue 1 vez).
  - [x] Rótulo maestro «ESTIMACIÓN TEÓRICA · LEY DE ATENUACIÓN SIMPLE — NO ES DATO MEDIDO» +
        marcador de paridad ATTEN-LAW v1 congelados en `test_index_comparativa_hooks` (15 hooks).
  - [x] Matching temporal declarado (`SSN_UTC_OFFSET_H = 6` → bucket UTC con caveat); fuera de
        ventana ⇒ «SIN DATO MEDIDO EN ESTA VENTANA (24 h · DESDE EL ARRANQUE)»; sin calibrar ⇒
        «PGA RELATIVO · SIN CALIBRAR — NO COMPARABLE» (jamás en el eje en g).
  - [x] La línea y el rótulo `M x.x · N km` del mapa siguen a la estación SELECCIONADA
        (vecina en verde); `close-map` resetea a propia.
  - [x] Estados vacíos honestos (sin sismo / sin ubicación / sin catálogo); sin profundidad ⇒
        «SIN PROFUNDIDAD REPORTADA» y R_hipo = epicentral.
  - [x] Cero endpoints nuevos, cero recursos externos; suite edge 464 verde + ruff limpio.
  - [x] Smoke headless (Chromium/Playwright, protocolo estilo VERIFICACION-T-2-23): overlay →
        clic sismo → cifras completas (fixture M 7.1/57 km/90 km ⇒ hipo 106 km, P ~16 s,
        0.099 g vs 0.053 g), curva pintada, candado de vecina, reset de selección, estados
        vacíos, CERO errores de consola.
  - [ ] Verificación visual presencial en el Pi (misma pantalla del gabinete).

---

### [x] T-2.28 · Consola SOC: capa de catálogo histórico + ComparePanel de atenuación — COMPLETA (2026-08-01)
- **Componente:** web · **Depende de:** T-1.48/T-1.52 (catálogo servido), T-2.27 (ley v1 ratificada)
- **Qué es:** los 13 sismos ratificados (1985–2022, gemelos SSN/USGS incluidos y AMBOS
  visibles) como capa propia del mapa del wall (◇ `#7CE7FF`, distinta del ✳ de incidentes),
  selección en DOS PASOS (clic en sismo → hint «PASO 2 · SELECCIONE UNA ESTACIÓN EN EL MAPA»
  → clic en sitio) y modal `ComparePanel` con distancia epicentral lineal + rumbo,
  hipocentral, arribo P teórico (v_P 6.5), PGA estimados (epicentro/estación) y curva SVG
  log-Y de ATTEN-LAW v1 con banda ilustrativa ×3/÷3. **Sin PGA medido y se declara**
  (retención de features 24 meses; los históricos no tienen series): nota fija «SIN PGA
  MEDIDO — EVENTO FUERA DE LA VENTANA DE DATOS». NO es el mini-ShakeMap del §14.
- **Criterios:**
  - [x] `haversineKm`/`bearing16` en `fleet/geo.ts` (espejo del panel; rosa en español) +
        `console/attenuation.ts` puro con vectores de PARIDAD en vitest
        (M 7.1/57/100 ⇒ hipo 115.1043 km · 0.04885 g estación · 0.09866 g epicentro ·
        P 17.71 s) — mismos números que el espejo edge y la fuente
        `_plausible_pga_g` (ancla ATTEN-LAW v1 en su docstring).
  - [x] Capa `catalog` en MapPanel con toggle «CATÁLOGO HISTÓRICO 1985–2022» (default OFF:
        el wall es operativo), `catalogToFeatureCollection` puro testeable, clic en ◇ emite
        `ref_id`, estados de leyenda (error ⇒ «CATÁLOGO NO DISPONIBLE», vacío ⇒ «CATÁLOGO
        VACÍO», seleccionado ⇒ hint paso 2).
  - [x] `ComparePanel` modal (patrón EpicenterModal) con select de sitio, rótulo maestro
        «ESTIMACIÓN TEÓRICA · LEY DE ATENUACIÓN SIMPLE — NO ES DATO MEDIDO», nota
        sin-medido, y estados: sin sitios ⇒ «SIN SITIOS CON COORDENADAS EN EL TENANT»;
        sin profundidad ⇒ «SIN PROFUNDIDAD REPORTADA» (hipocentral degrada a epicentral).
  - [x] El auto-popup por anomalía NUNCA cae en modo comparación (handler separado del
        clic de mapa); cerrar el modal limpia la selección de sismo.
  - [x] Cero cambios en api/db/sdk; cero dependencias nuevas (SVG a mano).
  - [x] vitest + eslint + build verdes; tests nuevos: atenuación (4), geo (5),
        ComparePanel (4), capa catálogo (4).

---

### [x] T-2.29 · Calibrador del PUNTO 0 de la brújula + sensibilidad adaptativa — COMPLETA (2026-08-01)
- **Componente:** edge (local_api + panel) · **Depende de:** T-2.25
- **Origen:** prueba de campo de Mauricio tras T-2.25: la brújula ya no satura, pero la media
  rodante ABSORBE inclinaciones sostenidas (τ≈30 s ⇒ el punto regresa al centro aunque el
  gabinete quede inclinado) y a escala de umbral (~0.07 g) el movimiento de reposo es
  invisible. Pedido: fijar el cero CON EL GABINETE YA INSTALADO Y NIVELADO y poder
  restablecerlo, y que la brújula viva a partir de ese punto 0.
- **Criterios:**
  - [x] `POST /api/rose-zero` (PIN + two-step en el panel): captura la media por canal EN*
        del ring (~ventana reciente, raw o minmax) y la persiste ATÓMICA en
        `rose_zero_path` (`/var/lib/takab/rose-zero.json`; sobrevive reinicios; sin disco
        queda en memoria y lo loguea). Re-pulsar RESTABLECE. Sin señal ⇒ **409**
        (`ActionUnavailable`) y `rose_zero` sigue null — jamás un cero inventado.
  - [x] `status().rose_zero = {channels, set_at} | null`; la brújula usa el PUNTO 0 fijo
        cuando existe y degrada a la media rodante [T-2.25] cuando no — y LO DECLARA en el
        canvas: «PUNTO ±X mg · PUNTO 0 FIJADO» vs «MEDIA RODANTE · SIN CALIBRAR».
  - [x] Sensibilidad: ganancia adaptativa del punto (pico decaído ×1.4, piso 2 mg, techo =
        escala de umbral) — vivo en reposo, comparable en sismo. La barra Z conserva la
        escala anclada a umbrales (es proximidad al disparo, otra pregunta).
  - [x] Presentación pura: cero cambios en rules/gpio/actuación; contrato de
        `/api/waveform` intacto.
  - [x] Tests: captura ≈ DC del simulador (ENZ ~3.77e6) + persistencia releída por otro
        panel (= reinicio) + 409 sin señal + 401 con PIN + hooks congelados
        (`CALIBRAR BRÚJULA`, `PUNTO 0 FIJADO`, `api/rose-zero`…). Suite edge 468 verde ·
        ruff limpio · smoke headless (botón, two-step, rose con cero fijo, 0 errores).
  - [ ] Verificación física: nivelar el gabinete, CALIBRAR BRÚJULA con PIN, inclinar ⇒ el
        punto se DESVÍA Y SE QUEDA (ya no regresa por la media rodante); restablecer.

---

### [x] T-2.30 · Verificación integral del panel + fixes responsive/solapamientos — COMPLETA (2026-08-03)
- **Componente:** edge (panel local_api) · **Depende de:** T-2.29
- **Qué es:** barrido headless del panel (Playwright scratchpad, no committeado — M-7 sigue
  abierto): 60 celdas = 12 viewports (muro/consola/campo, 1920×1080 → 360×740, incl. muro y
  consola FORZADOS en teléfono) × 10 escenas `?demo=` × overlay abierto, con detector de
  solapes/desbordes (intersección pareada, recortes, canvas sin alto, scroll de página) +
  click-through de los 7 botones contra fixture server real; fixes de lo que reventó.
- **Criterios:**
  - [x] Smoke: 0 errores de consola/página; 0 solapes entre secciones visibles; 0 scroll
        horizontal a nivel página en TODOS los modos; overlay usable en 390×844 aunque el
        operador fuerce CONSOLA (media query, no solo clase campo).
  - [x] Los 7 botones ejercitados en vivo: two-step (armado por botón reconstruido con
        rótulo CONFIRMAR + countdown), auto-desarme a los 5 s, PIN en header solo si está
        capturado (anti-lockout), refetch one-shot tras 200, y los 4 caminos de rechazo
        (401 con/sin PIN, 403, 429) gritados en el toast. Chips de modo/variante, tabs,
        filas SSN/estación y cierre del mapa incluidos.
  - [x] Fixes con hooks congelados nuevos (`test_index_responsive_overlap_fixes`):
        overlay apilado en angosto (`id="overlay-side"`, reglas campo + `@media
        (max-width:699px)`), `#cmp-drawer` acotado con clamp, bitácora `overflow:hidden
        auto`, relés `repeat(auto-fit,minmax(150px,1fr))` (pre-habilita perfiles de
        equipamiento), header con `min-height` + wrap (idéntico en 1080p), y
        `body.mode-campo #rose-wrap{min-height:240px}` — **la brújula colapsaba a 0 px y
        JAMÁS se pintaba en teléfono** (bug preexistente destapado por el detector).
  - [x] Consola@1080p reposo sin scroll vertical (spec §3); muro forzable en cualquier
        ancho sin desbordar la página.
  - [x] E2E: suite `test_e2e.py` verde + test nuevo `test_quake_event_reflected_in_panel_status`
        (sim→tier→`/api/status`: tier, latch y 5 relés activados llegan al panel).
        Suite edge 470 verde · ruff limpio.
  - [ ] Verificación física coordinada: WR-1 en modo prueba + PROBAR ACTUADORES con
        readback en el gabinete (sirena real ~2 s — avisar a ocupantes) y vista del panel
        en el monitor del gabinete y en un teléfono.
- **Nota:** 1024px exactos cae en CONSOLA por diseño (`autoMode` usa <1024): una tablet
  horizontal ve el layout de escritorio con scroll interno en `#main` — documentado, no es
  regresión.

---

### [x] T-2.31 · Perfil de equipamiento por estación (nube declara, panel/consola adaptan) — COMPLETA (2026-08-03)
- **Componente:** db + api + edge + web · **Depende de:** T-2.30
- **Qué es:** no toda estación tiene gas/ascensores/puertas. `gateways.equipment`
  (jsonb, 5 bools, default todo-true = compat retro) declara qué actuadores existen en el
  sitio; viaja al edge FUSIONADO en el doc firmado del config sync existente (cero topics,
  cero terraform: `takab/cfg/*` ya estaba en la política IoT y en WorkerIotPublish) y las
  vistas se adaptan.
- **Criterios:**
  - [x] Migración `0022_gateway_equipment` idempotente (columna + trigger que reutiliza el
        evento `t='rule_set'` de `takab_live` ⇒ el worker de sync despierta al editar,
        SLA ≤60 s, sin tocar el worker). DDL sobre tabla preexistente como usuario de
        conexión.
  - [x] Fleet API: `equipment` en Out/Create/Update (extra=forbid: clave desconocida ⇒
        422; parcial completa con true); RLS cross-tenant verificada (404). SDK TS
        regenerado (`make drift` verde).
  - [x] Config sync fusiona `rs.config->'edge' || {'equipment': g.equipment}` — una firma
        cubre config + equipamiento; editar SOLO equipamiento re-publica con versión
        monótona; `in_sync` del config-state compara contra la MISMA fusión (espejo del
        predicado del worker).
  - [x] Edge: `EquipmentProfile` en `EdgeSettings` (doc parcial ⇒ todo-true); la secuencia
        de tier comanda SOLO instalados (leyendo `config.current()`, no el settings
        congelado); comando de nube a canal no instalado ⇒ ack `rejected` honesto; el
        panel pinta SOLO instalados EN CALIENTE. gpio conserva sus 5 relés (hardware
        intocado); reflejo SASMEX intocado.
  - [x] Web: HardwareForm con 5 checkboxes (viajan en el alta); `relaysFor` oculta canales
        no instalados aunque el rule_set declare cableado y muestra instalados sin
        cableado como S/D; sin `equipment` (flota vieja) la conducta no cambia.
  - [x] Suites verdes: api 921 · edge 476 · web 606 · ruff/eslint/prettier/build ·
        `make drift`.
  - [x] Despliegue VERIFICADO (2026-08-03): nube en `698efa0` con alembic 0022; el
        config sync re-publicó v13 con `equipment` fusionado y el Pi la aplicó EN
        CALIENTE (journal «config actualizada a v13»).
- **Nota:** el equipamiento solo llega a gateways cuyo rule_set activo trae la clave
  `'edge'` (cierto para gw-dev-0001) — prerrequisito documentado de alta de estación.

---

### [x] T-2.32 · Política de actuación: instrumental = aviso visual; el quórum comanda firmado — COMPLETA (2026-08-03)
- **Componente:** edge + db + api + web + docs · **Depende de:** T-2.31
- **Qué es:** política RATIFICADA por Mauricio (2026-08-03): una sola estación moviéndose NO
  activa nada (ni sirena ni voceo) — el panel muestra AVISO; se requieren ≥3 estaciones en
  ventana consciente de la distancia. Al confirmar quórum, la NUBE emite comandos de
  actuación FIRMADOS (regla de oro 8) a los miembros. SASMEX intacto. Es una REESCRITURA
  DELIBERADA del contrato de Fase 1 (T-1.14), registrada como enmienda del blueprint.
- **Criterios:**
  - [x] Edge: `instrumental_actuation=False` de fábrica; gate en `_act_and_publish` por
        `source=THRESHOLD` — cero relés/voceo, CONSERVA LocalEvent (alimenta el quórum),
        evidencia y aborto de drill; online y offline. Opt-in por sitio restaura Fase 1.
        SASMEX y MANUAL intocados (tests previos sin modificar).
  - [x] Nube: pass `quorum_actuation` en el IncidentEngine (tras la correlación, txn
        propia): canales = evacuación ∩ equipamiento, firma per-gateway fail-closed,
        `origin=quorum` DENTRO de la firma, ledger idempotente = índice único parcial de
        `commands` (0023); publish fallido reintenta sin fila fantasma; el evento de red
        sobrevive siempre.
  - [x] Panel: ROJO exclusivo de actuación real (FUENTE SASMEX WR-1 | QUÓRUM RED); banner
        ámbar «AVISO SÍSMICO … SOLO AVISO · SIN ACTUACIÓN»; `status().network_alert` y
        CERRAR ALERTA lo cierra; escena demo `aviso` nueva (las 10 originales intactas).
  - [x] Web: badge «QUÓRUM RED · canales · acks» en el DetailPanel del incidente enfocado.
  - [x] Docs: blueprint §4.5 (A=advisory, B=actuante) + §2 P1/P2 + tabla de tiers con nota;
        CLAUDE.md §1 fuentes y §2 regla 1 enmendados.
  - [x] Suites: edge 481 · api 926 · web 606 + smoke layout (64 celdas, 0 hallazgos) ·
        ruff/eslint/prettier/build verdes.
  - [x] Despliegue VERIFICADO (2026-08-03): migración 0023 aplicada; el rol del EC2
        co-locado ya portaba `WorkerIotPublish` con `takab/cmd/*`; ciclo regla-8 validado
        EN PRODUCCIÓN — self_test ⇒ ack `rejected` (command_enabled=false de fábrica),
        habilitación por el doc firmado (v14, hot-apply) + edge.env, self_test ⇒ ack
        `acked` con readback. `command_enabled=true` OPERATIVO en gw-dev-0001.
        Hallazgo abierto (candidato T-2.34): al reiniciar, el edge arranca en config v0 y
        la nube no re-publica si el payload no cambió ⇒ umbrales/equipment/command_enabled
        regresan a defaults hasta el siguiente cambio — persistir la config firmada en
        disco como ya hace CatalogStore.
- **Nota:** con la flota real de 1 estación, la actuación instrumental queda en AVISO hasta
  que existan ≥3 estaciones (decisión consciente del usuario); el rate-limit por sitio no
  se ve afectado (el actor quórum no pasa por `issue_signed_command`).

---

### [x] T-2.33 · Gabinetes secundarios LoRa (contrato + módulo + simulador + panel) — COMPLETA (2026-08-03)
- **Componente:** edge (lora + panel) + shared/schemas + docs · **Depende de:** T-2.32
- **Qué es:** gabinetes secundarios (ESP32 + estrobos + sirena/bocina) instalados lejos del
  principal, comunicados por LoRa 915 MHz. Espejos de la protección: reciben ALARM_ACT cuando
  el principal ACTÚA (SASMEX o comando de quórum — el aviso instrumental NO propaga), CLEAR
  con CERRAR ALERTA, TEST con PROBAR ACTUADORES; su salud vive en el dashboard del Pi.
  Alcance ratificado: contrato + módulo edge + simulador AHORA; firmware ESP32 cuando exista
  hardware (`takab-docs/design/LORA-SECUNDARIOS.md` ancla la paridad).
- **Criterios:**
  - [x] Trama v1 byte-exacta (29 B, HMAC-SHA256 truncado 10 B dominio `lora-v1`) con
        VECTORES DORADOS; clave POR GABINETE derivada de la de sitio; anti-replay sin RTC
        (session+seq); forja/alteración/replay rechazados en tests.
  - [x] `LoraLink` (EdgeModule NO crítico, sin gpio): `propagate()` jamás bloquea;
        repeat-until-ack (espaciado 2 s, tope 5) con `SIN ACK` visible al agotarse;
        heartbeat ausente >3 periodos ⇒ `ENLACE PERDIDO` con log SOLO por transición
        (regla 10). Transporte Protocol + serial NDJSON (extra `lora`=pyserial, import
        perezoso) + simulador determinista (pérdida con `drop_next`, ACK firmado real).
  - [x] E2E simulado: SASMEX ⇒ secundarios activados (ack visible en status); CERRAR
        ALERTA ⇒ ALARM_CLEAR; quake instrumental (solo aviso T-2.32) NO propaga; comando
        de red QUÓRUM RED a sirena/estrobo también se espeja (flags acumulados).
  - [x] Panel: card «Gabinetes secundarios · LoRa» (enlace/RSSI/SNR/batería/estado de la
        orden) con estados honestos (SIN RADIO LORA · MÓDULO DESHABILITADO / SIN GABINETES
        SECUNDARIOS PROVISIONADOS); datos SOLO vía `/api/status` (tick único intacto);
        smoke de layout 64 celdas en 0 hallazgos (criterio 1080p sin scroll intacto).
  - [x] Contrato `SecondaryCabinetState` + schema espejo v1.8.0 (`lora_secondary_state`);
        `lora.enabled=False` default (módulo dormido sin radio); sin secretos en git
        (clave por `TAKAB_EDGE_LORA_KEY`).
  - [x] Suite edge 505 verde · ruff limpio.
  - [ ] Cuando exista hardware: firmware ESP32 (RadioLib + códec §2 validado contra los
        vectores §3), medir alcance/SF en sitio, alta de secundarios reales en
        `TAKAB_EDGE_LORA__SECONDARIES` y política del watchdog de alarma con PC.

---

### [x] T-2.34 · La config firmada sobrevive reinicios (caché re-verificada en disco) — COMPLETA (2026-08-03)
- **Componente:** edge (config store) · **Depende de:** T-2.32
- **Origen:** el corte de energía del 2026-08-03 lo demostró EN VIVO: al reiniciar, el edge
  arrancaba en config v0 y la nube no re-publica si el payload no cambió (`IS DISTINCT`
  falso) ⇒ umbrales de sitio, equipamiento y `command_enabled` REGRESABAN a defaults hasta
  el siguiente cambio de config. Además el `high_water` anti-replay moría con el proceso:
  un reboot reabría la ventana de replay de cualquier config vieja firmada.
- **Criterios:**
  - [x] `ConfigStore` persiste `{applied_version, high_water, payload, sig}` atómico en
        `config_cache_path` (`/var/lib/takab/config-cache.json`; patrón CatalogStore:
        tmp + `os.replace`, fail-soft sin disco — la config sigue en memoria).
  - [x] Al arrancar, la caché se RE-VERIFICA (la firma cubre payload+versión) y se aplica
        notificando a los listeners (umbrales→rules, location). Fail-closed a defaults ante
        alteración, clave rotada, JSON ilegible o contrato incompatible.
  - [x] El `high_water` sobrevive reinicios: el replay de un frame viejo firmado se rechaza
        también tras un reboot. El rollback persiste la versión revertida SIN bajar el
        high_water (un reboot no resucita la config mala).
  - [x] Sin `cache_path` (stores sueltos/tests) la conducta previa no cambia.
  - [x] Suite edge 513 verde · ruff limpio.
  - [x] Prueba EN VIVO en el Pi: re-seed de la config (v15) → reinicio del servicio →
        `config_version` se conserva tras el reboot (antes regresaba a 0).

---

## Ciclo Nube 2.2 · Auditoría y reforma de la consola SOC (T-2.35 … T-2.57)

Las cuatro pantallas de la consola se construyeron una a una entre T-1.15 y T-2.34,
siempre detrás del edge, y nunca se auditaron como producto. Este ciclo cierra los
huecos encontrados, añade lo que faltaba y deja preparada la capa de IA. Un solo
redespliegue al final (T-2.57).

### Bloque A · FLOTA EDGE

### [x] T-2.35 · Las estaciones fantasma no sobreviven al retiro — COMPLETA (2026-08-03)
- **Componente:** api + web · **Depende de:** T-2.34
- **Origen:** el cliente reportó estaciones duplicadas, con el mismo nombre y sin forma
  de borrarlas. `queries/fleet.py::_LIST` era la ÚNICA query del repo sin `WHERE`:
  devolvía gabinetes `retired` y gabinetes de sitios `retired` (compárese con
  `queries/sites.py:31`, `telemetry.py:192`, `commands.py:35`, `mobile.py:276`,
  `commands/sync.py:61`). Como `retire_site` tampoco tocaba `gateways`, el hardware
  quedaba huérfano, y al desaparecer el sitio de `/sites` la web perdía su nombre y lo
  rebautizaba `SITIO <8 hex>`: varios huérfanos se veían como la misma estación.
  Ninguna suite lo habría cazado — `test_fleet_admin` retiraba y nunca volvía a listar.
- **Criterios:**
  - [x] `_LIST` hace JOIN a `sites`, filtra ambos estados y acepta `?include_retired=`
        (espejo de `GET /sites?include_retired`).
  - [x] `GatewayOut` trae `site_name`/`site_code`/`site_status` del SERVIDOR; la web
        deja de cruzar contra `/sites` y no puede volver a fabricar un nombre.
  - [x] `retire_site` propaga el retiro a sus gabinetes en la misma transacción y
        audita uno por uno. `commands/sync.py` y `queries/commands.py` filtran por
        `gateways.status`: un huérfano seguía siendo candidato de config firmada y de
        comandos de actuación.
  - [x] Migración `0024` sanea los fantasmas ya presentes en la base viva. Idempotente
        y con `SET LOCAL app.role`: `gateways` lleva FORCE RLS y el dueño es el mismo
        usuario que migra en la nube, así que sin el GUC el UPDATE tocaría 0 filas EN
        SILENCIO (en local no se notaría: el superusuario ignora la RLS).
  - [x] 13 tests nuevos, empezando por el que faltaba: retirar un gabinete y volver a
        listar el inventario. Más el de la migración, su idempotencia y el que ancla el
        GUC para que no desaparezca en una limpieza futura.
  - [x] Suite api 936 verde · web 614 · drift gate verde.

---

### [x] T-2.36 · Retirar una estación exige un segundo factor — COMPLETA (2026-08-03)
- **Componente:** api + web · **Depende de:** T-2.35
- **Origen:** retirar un gabinete lo saca del config sync firmado y de los comandos de
  actuación: deja un edificio sin protección sísmica. Hasta aquí bastaba un doble clic
  armado en la consola.
- **Criterios:**
  - [x] Dos factores: teclear el identificador exacto (`serial` del gabinete, `code`
        del sitio — visible en pantalla, freno contra el clic en la fila equivocada) y
        el **código de retiro del cliente**, que TAKAB entrega fuera de banda. El
        identificador se comprueba PRIMERO: un dedazo no debe quemar un intento.
  - [x] `tenant_retire_codes` con bcrypt vía `pgcrypto` (coste 12). El hash NUNCA sale
        de Postgres: se pregunta por `app_verify_retire_code` (SECURITY DEFINER con
        `search_path` fijado) y `takab_app` no tiene política de lectura — ni el
        `tenant_admin` que usa el código ve su propio hash.
  - [x] La tabla va ENABLE **sin FORCE**, única excepción del esquema y documentada:
        FORCE sujeta también al dueño, y el dueño es quien debe poder leer desde la
        función definer (SECURITY DEFINER cambia el usuario, no los GUC).
  - [x] `manage_retire_code` = SOLO `takab_superadmin`. Si el cliente rotara su propio
        código, el segundo factor volvería a ser el primero (su sesión).
  - [x] Fail-closed: sin código configurado no se retira (409). La ausencia de
        credencial nunca es un bypass.
  - [x] Rate-limit 5 intentos / 15 min por cliente ⇒ 429, y el bloqueo tampoco deja
        pasar el código correcto (si no, agotar los intentos revelaría cuál es).
  - [x] La denegación se audita en una conexión APARTE que commitea: el request es una
        sola transacción y el rollback del 403 se habría llevado la fila por delante,
        dejando el contador inoperante. Hay test dedicado.
  - [x] `DELETE /sites/{id}` y `DELETE /fleet/gateways/{id}` → `POST …/retire`: ahora
        llevan cuerpo y un DELETE con body no atraviesa proxies de forma fiable.
  - [x] 16 tests de API + 12 de `RetireDialog` · RBAC-TAKAB.md §2 actualizado.
- **Pendiente de despliegue:** rotar el código de cada tenant tras el redeploy. Sin él
  nadie puede retirar nada (es el fail-closed funcionando).

---

### [x] T-2.37 · La consola administra el gabinete completo — COMPLETA (2026-08-03)
- **Componente:** api + web · **Depende de:** T-2.36
- **Origen:** `PUT /fleet/gateways/{id}`, `POST …/restore` y el `config-state` existían
  desde T-1.30/T-1.32 y la web no llamaba a ninguno. Un gabinete dado de alta desde la
  consola quedaba congelado para siempre.
- **Criterios:**
  - [x] El alta MANDA `iot_thing`. Sin él el worker de config sync excluye al gabinete
        y no recibe umbrales firmados nunca; no había forma de vincularlo después. El
        test que afirmaba lo contrario congelaba el defecto y se reescribió.
  - [x] Acuse tras el alta: cierra el formulario y entrega los tres UUID del
        `edge.env`. Antes no cambiaba NADA en pantalla al pulsar, el operador volvía a
        pulsar, y con un dígito distinto en el serial nacía un gabinete gemelo — el
        segundo camino de las "estaciones repetidas".
  - [x] `GatewayForm`: serial, `iot_thing`, firmware, WR-1 y EQUIPAMIENTO, con
        `base_row_version`. `status` no se edita: lo deriva el heartbeat.
  - [x] `SyncBadge` distingue PENDIENTE de NO SINCRONIZABLE y de SIN CONFIG EDGE. Los
        tres se veían igual y el operador esperaba una publicación imposible.
  - [x] Retirar y restaurar gabinete desde la tarjeta + toggle VER RETIRADOS.
  - [x] `HardwareForm` lista los gabinetes ya registrados en el sitio: freno
        anti-duplicado antes de pulsar.
  - [x] `GET /fleet/config-state` (lote) sustituye al abanico de N peticiones cada
        10 s: con 500 gabinetes eran ~50 req/s desde un navegador y, como el pie solo
        vale cuando responden todas, a esa escala habría dicho "desconocido" siempre.
  - [x] `EquipmentProfile` NO se extiende: es el conjunto de `ActuatorChannel` del
        edge, y un canal nuevo sin su pin GPIO y su secuencia de tier aparecería como
        "instalado" sin que el gabinete pueda accionarlo (dato falso).
  - [x] 27 tests nuevos · suite api 959 · web 652.

---

### [x] T-2.38 · La flota muestra reincidencia, no solo el instante — COMPLETA (2026-08-03)
- **Componente:** api + web · **Depende de:** T-2.37
- **Origen:** la pantalla decía si un gabinete está bien AHORA y nada más. Uno que se
  cae cinco veces al día se veía idéntico a uno que nunca falló — que es justo la
  diferencia entre un corte puntual y una instalación mal hecha.
- **Criterios:**
  - [x] `GET /fleet/health-history`: buckets de 24 h (p95 del RTT, no promedio — la
        cola larga es lo que importa en un enlace) y CAÍDAS derivadas del silencio
        entre latidos, con el MISMO umbral que `derive_fleet_state`.
  - [x] `Sparkline` sin dependencias: un `null` PARTE el trazo. Cualquier librería de
        charts habría unido los extremos del hueco con una recta que se lee como "todo
        estuvo bien" justo donde no hubo dato.
  - [x] Búsqueda (nombre/código/serial/iot thing), orden peor-primero y OCULTAR SIN
        ENLACE. Los KPI cuentan el TOTAL: un contador que se moviera con el filtro
        convertiría "3 SIN ENLACE" en una cifra distinta según lo tecleado. La leyenda
        MOSTRANDO n DE N dice cuánto se ve.
  - [x] El vacío por filtro se distingue del vacío por flota sin gabinetes.
  - [x] Responsive: la reja pasa de TRES columnas duras a `auto-fill minmax(340px,1fr)`
        (en 1366 px las tarjetas se estrujaban hasta partir sus pills), `flex-wrap` en
        el header y scroll propio para la tabla admin. Breakpoints 1100/640 como
        DEGRADACIÓN: el objetivo sigue siendo 1920×1080.
  - [x] Rótulo honesto COMPLETITUD DE LATIDOS, no "de datos".
  - [x] 38 tests nuevos · suite api 968 · web 683 · drift gate verde.

### Bloque B · EVALUACIÓN ESTRUCTURAL

### [x] T-2.39 · La pantalla dice el hecho medido, no un guion — COMPLETA (2026-08-04)
- **Componente:** web · **Depende de:** T-2.38
- **Origen:** la pestaña se llamaba «Triage» (término de urgencias, no de estructuras) y
  el encabezado abría con `M —` porque la magnitud es SIEMPRE null: no hay ingesta de
  catálogo. Un dictamen que abre con un guion no informa de nada.
- **Criterios:**
  - [x] Pestaña **EVALUACIÓN**, título *Evaluación Estructural Post-Sismo*. Ruta
        `/triage` y clases CSS INTACTAS: están cableadas en `matrix.py` y en la hoja
        entera, y renombrarlas rompería el RBAC por un cambio de etiqueta.
  - [x] Los reportes de daño del móvil salen del gate del dictamen: son un HECHO del
        incidente y sin dictamen no se renderizaban.
  - [x] `magnitudeOf` devuelve `S/CATÁLOGO` / `SIN EVENTO`, nunca `—`. El encabezado
        pasa a la banda `felt` MEDIDA y la magnitud baja a métrica rotulada.
  - [x] El epicentro declara si es CENTROIDE DE LA RED (no es una localización sísmica),
        reubicado por operador, o de catálogo externo.
  - [x] Nodos del quórum con nombre; uno de otra red se pinta `OTRA RED` en gris, que es
        exactamente lo que hay que decir.
  - [x] `role="grid"` y primera celda como `<button>`: el `<tr onClick>` no era accesible
        por teclado y `aria-selected` fuera de un grid es inválido.

### [x] T-2.40 · Una sola fuente de hechos para la pantalla y el dictamen — COMPLETA (2026-08-04)
- **Componente:** api + web · **Depende de:** T-2.39
- **Origen:** la pantalla y el PDF calculaban lo mismo por su cuenta. Dos caminos hacia
  el mismo número divergen, y en un dictamen eso es una contradicción firmada.
- **Criterios:**
  - [x] `GET /incidents/{id}/forensics`: picos por canal, tiempo de aviso (solo con
        `trigger='sasmex'`, con su razón cuando es nulo), estaciones, contraste con el
        catálogo SSN y calibración.
  - [x] **Usa `waveform_features_1s_secure`**: el contract-test `test_waveform_view.py`
        falla el build si un módulo bajo RLS nombra la hypertable cruda. El allowlist NO
        se amplió.
  - [x] Matriz de prioridad de inspección (ShakeCast): `felt === "unknown"` ⇒ GRIS/SIN
        MEDICIÓN, jamás verde. Encabezado literal *NO ES UN DICTAMEN*.
  - [x] Resumen post-evento, bitácora como timeline (antes solo se contaba) y
        mini-waveform rotulado ENVOLVENTE, NO la forma de onda cruda (regla de oro 9).
  - [x] Animaciones dentro de `prefers-reduced-motion`; ninguna anima un dato que cambia.

### [x] T-2.41 · Motor de PDF vectorial: dictamen técnico y ejecutivo — COMPLETA (2026-08-04)
- **Componente:** api · **Depende de:** T-2.40
- **Origen:** el PDF era texto plano latin-1 sin tablas, mapa, gráficas ni paginación —
  y Δ, ≥ y ≈ se degradaban a interrogantes en un documento de compliance.
- **Criterios:**
  - [x] `dictamen/{model,layout,plot,sketch,mseed}.py` + fuentes DejaVu empaquetadas.
  - [x] **Determinista**: `set_creation_date(opened_at)` fija `/CreationDate`; sin eso
        dos generaciones del mismo modelo daban hashes distintos y «verifique el sha256»
        habría sido una promesa falsa.
  - [x] Decodificador STEIM2 **vendorizado** (~200 líneas) validado con vectores dorados
        generados por el ObsPy del propio edge. Se rechazó ObsPy: arrastra
        matplotlib+scipy+lxml (~200 MB) a una imagen co-locada en un EC2 Graviton. Única
        dependencia añadida: `numpy` (FFT).
  - [x] Dos documentos de un mismo modelo: técnico ≥6 páginas y ejecutivo 1–2. La
        variante va en la key de S3 y en la auditoría, no en un `kind` de evidencia nuevo.
  - [x] **Prohibido inventar**: cada `None` produce un literal de ausencia con su razón.
        Hay un test que busca `"0.000 g"` con pico nulo.
  - [x] Se retira el gate «sin dictamen no hay PDF»: un incidente sin dictamen YA tiene
        hechos que reportar y el documento lo rotula preliminar.

### [x] T-2.42 · La prosa rodea al veredicto sin poder tocarlo — COMPLETA (2026-08-04)
- **Componente:** api · **Depende de:** T-2.41
- **Origen:** preparar la capa de IA sin que pueda colarse al camino determinista.
- **Criterios:**
  - [x] `Narrative` **no tiene campo de veredicto**: un proveedor no puede emitir uno
        porque no hay dónde ponerlo. Tres contract-tests, no promesas en la doc.
  - [x] `narrative/` no importa `dictamen.rules` ni `dictamen.service`: no puede ni
        invocar al motor que dictamina.
  - [x] Proveedor determinista ACTIVO con seis secciones; «por qué este veredicto» cita
        el basis literal (qué umbral, con qué valor, de qué versión de reglas).
  - [x] OpenRouter listo y **APAGADO** (gate #9 = Fase 3, shadow-mode). Fail-open total,
        sin reintentos, y un guardrail que DESCARTA la respuesta entera si menciona otro
        veredicto o cita una medición que no está en los hechos.
  - [x] Redacción por ALLOWLIST: un campo nuevo del modelo queda fuera por omisión.
  - [x] Sin tabla nueva: la narrativa se congela en el PDF y su procedencia va a
        `audit_log` (`narrative_generated`), append-only y sin poda.

### [x] T-2.43 · El botón de miniSEED explica por qué no se puede — COMPLETA (2026-08-04)
- **Componente:** web · **Depende de:** T-2.41
- **Origen:** el botón NO tenía bug —estaba bien deshabilitado— pero deshabilitado y
  mudo es indistinguible de roto para quien está operando un incidente.
- **Criterios:**
  - [x] Seis estados distinguibles. El que faltaba: **BACKFILL EN CURSO** (< 15 min, el
        crudo aún puede estar subiendo); decir «no hay» ahí es falso.
  - [x] Pasada la ventana, la nota apunta a `/fleet`: la causa probable es el enlace.
  - [x] **No se ofrece generación bajo demanda** (reglas de oro 4, 8 y 9), y hay un test
        que lo fija: además fallaría igual, porque el buffer del edge es finito.
  - [x] Se retira el gate `head === null` del botón de PDF, espejo del de la API.

### Bloque C · MONITOREO

### [x] T-2.44 · La pestaña C4I pasa a llamarse MONITOREO — COMPLETA (2026-08-04)
- **Componente:** web + docs · **Depende de:** T-2.39
- **Criterios:**
  - [x] Pestaña **MONITOREO**, título *Monitoreo en Vivo*. Ruta `/console` intacta.
  - [x] Columna §2 de `RBAC-TAKAB.md` renombrada — una docena de docstrings la citan, y
        dejar referencias a una columna inexistente habría sido peor que el nombre viejo.
  - [x] Se cierra de paso el desfase de T-2.39: la columna «Triage» pasa a EVALUACIÓN.
  - [x] Un solo docstring llega al OpenAPI: regenerado y commiteado (drift gate).

### [x] T-2.45 · La consola respeta `site_scope`, con cutover en dos fases — COMPLETA (2026-08-04)
- **Componente:** api + web · **Depende de:** T-2.44
- **Origen:** `site_scope` se aplicaba en WS, móvil, comandos y simulacros; en la consola
  no. Un `soc_operator` acotado a una estación veía el tenant entero.
- **Criterios:**
  - [x] Aplicado en mapa, features, features por canal, métricas, `/sites`,
        `/fleet/gateways` e `/incidents`. Fuera de alcance ⇒ **404, nunca 403**.
  - [x] **Fase A** (la que se despliega): el claim no está aprovisionado, así que un
        claim vacío NO filtra —filtrar dejaría a todo `soc_operator` con cero sitios— y
        se AUDITA como `scope_gap`, una fila por usuario y proceso.
  - [x] **Fase B** (`console_scope_enforced=True`): un claim vacío filtra a cero. El
        bloqueante cayó con T-2.54; falta asignar alcances antes de encenderlo.
  - [x] `/me` gana `console_scope_enforced` y la insignia declara lo que el SERVIDOR
        hace. El front NO filtra: la autoridad es el servidor.

### [x] T-2.46 · Enlace por estación en el mapa — COMPLETA (2026-08-04)
- **Componente:** api + web · **Depende de:** T-2.45
- **Origen:** el mapa coloreaba por sacudida sin decir si el gabinete seguía vivo: un
  punto verde podía ser «todo bien» o «el color es un recuerdo de hace seis horas».
- **Criterios:**
  - [x] Estado derivado de `derive_fleet_state` (verdad única, cero reimplementación).
  - [x] El enlace NO usa el canal de color —lo ocupa `felt`—: opacidad, núcleo hueco y
        glifo, con segunda leyenda `ENLACE CON LA ESTACIÓN`.
  - [x] **`SIN GABINETE` no se colapsa con `SIN ENLACE`**: «no hay hardware» y «el
        hardware calló» exigen acciones distintas.

### [x] T-2.47 · Animaciones del mapa — COMPLETA (2026-08-04)
- **Componente:** web · **Depende de:** T-2.46
- **Criterios:**
  - [x] `V_S` se DERIVA de `V_P` (Poisson, √3): una constante suelta sería una segunda
        fuente de verdad que se desincronizaría.
  - [x] Anillos P/S con radio FÍSICO en km → píxeles con el tile de **512 px** de
        MapLibre; con 256 salían al doble. Rotulados MODELO DE UNA CAPA · ESTIMACIÓN.
  - [x] Un solo rAF a 20 fps, `line-dasharray` conmutado O(1) por frame, apagado al
        cruzar los 180 s sin esperar snapshot.
  - [x] `prefers-reduced-motion` deja anillos quietos y anula los dos keyframes vivos.
  - [x] **Sin cuenta regresiva T-MINUS ni magnitud preliminar** (CLAUDE.md §8), asertado.

### [x] T-2.48 · Simulacro programado, historial y acuse — COMPLETA (2026-08-04)
- **Componente:** api + web · **Depende de:** T-2.47
- **Origen:** `POST /drills` con `scheduled_at` existía y no tenía UI; y el banner tenía
  un fallo serio.
- **Criterios:**
  - [x] **El banner ya no se calla**: si `/drills/active` fallaba con un simulacro vivo,
        DESAPARECÍA en silencio — y un simulacro que deja de anunciarse es
        indistinguible de una alerta real para quien está dentro. Degrada a DATOS
        RETENIDOS con el último dato conocido.
  - [x] **`SIN GABINETE COMANDABLE` ≠ `SIN ACUSE`**: colapsarlos haría creer que un
        sitio ignoró el simulacro cuando no había a quién mandárselo.
  - [x] `GET /drills` con keyset (desempate por id: sin él se solapaba entre una agenda y
        su ejecución creadas en el mismo ms), `POST /drills/{id}/cancel`, y la agenda
        persiste sus sitios con `command_id NULL`.
  - [x] Simulacro ARMADO: banner a T−15 min, botón precargado a T−0. **Ejecutar sigue
        siendo un clic humano; no hay temporizador en ninguna capa** (regla de oro 8).

### [x] T-2.49 · Una prueba de sirena deja de sonar como un sismo — COMPLETA (2026-08-04)
- **Componente:** edge · **Depende de:** T-2.48
- **Origen:** el voceo miraba `siren_sounding` —un booleano ELÉCTRICO— y sonaba el mismo
  `siren.wav` en todos los casos: el self-test de un operador sonaba byte a byte igual
  que un sismo real dentro de un edificio con gente. Un test lo congelaba.
- **Criterios:**
  - [x] `gpio.siren_reason` DERIVA la causa de los enclaves que ya deciden el relé; una
        alerta real durante una prueba se reporta ALERT y el altavoz conmuta.
  - [x] Sin tono de prueba, una prueba **CALLA**: caer al tono de alerta sería el bug
        otra vez, y el silencio durante una prueba no arriesga a nadie.
  - [x] `prueba.wav` original de TAKAB, auditado por sha256 al arrancar.
  - [x] **El tono oficial de SASMEX no se empaqueta**: es de CIRES, su ID queda RESERVADO
        y ausente, y «ID desconocido ⇒ conservar el anterior» impide que se cuele
        (GATE-LEGAL).
  - [x] La nube elige por ID de catálogo en `config.edge.audio`: ni binarios —el doc
        viaja firmado hacia un dispositivo que toca sirena y gas— ni rutas absolutas.

### [x] T-2.50 · Estadísticas y capas de MONITOREO — COMPLETA (2026-08-04)
- **Componente:** web · **Depende de:** T-2.47
- **Criterios:**
  - [x] Cero endpoints nuevos. Contadores por viewport, capas conmutables, orden de cola
        y KPI semáforo.
  - [x] **`OCULTAR SIN ENLACE` filtra el mapa pero NO el semáforo**: si filtrara los
        KPIs, el operador podría esconder sin darse cuenta el problema que debe atender.
  - [x] Diferido con nombre: intensidad areal interpolada (= mini-ShakeMap, blueprint
        §14) y eventos versionados New/Update.

### Bloque D · MULTI-TENANT y pantallas nuevas

### [x] T-2.51 · Multi-tenant: clipping, CSS, escala y edición — COMPLETA (2026-08-04)
- **Componente:** api + web · **Depende de:** T-2.50
- **Origen:** `.mt__list` no tenía `overflow` dentro de `body{overflow:hidden}`: con ~15
  clientes los últimos eran **físicamente inalcanzables**. Bug de accesibilidad.
- **Criterios:**
  - [x] Clipping cerrado y la invariante `flex-shrink:0` extendida a `.mt`, `.triage` y
        `.soc-main`.
  - [x] El CSS que T-1.72/T-1.73 nunca tuvieron (`.mt__new-*`, `.vis-*`, …).
  - [x] N+1 cerrado: de una query por gabinete cada 10 s (500 gabinetes ≈ 50 req/s desde
        un navegador) a una sola en lote, conservando `unknown` si falta uno.
  - [x] `PATCH /tenants/{id}` con concurrencia optimista por `xmin`, auditado. Es
        **superadmin-only**: la RLS lo exige y dárselo a `tenant_admin` habría pintado un
        botón con 403 garantizado.
  - [x] Paginación de servidor: deuda declarada hasta ~200 clientes.

### [x] T-2.52 · Pantalla de AUDITORÍA — COMPLETA (2026-08-04)
- **Componente:** api + web · **Depende de:** T-2.51
- **Origen:** `GET /audit` existía completo con filtros y keyset, y **no había ninguna
  pantalla que lo consumiera** en toda la web.
- **Criterios:**
  - [x] Ruta `/audit` en `matrix.py` para exactamente los roles con `read_audit`, tab,
        filtros actor/verbo/objeto/rango, keyset y `StateFrame` completo.
  - [x] `test_matrix.py` y RBAC §2/§7 actualizados en el mismo cambio.

### [x] T-2.53 · Códigos de enrolamiento en la web — COMPLETA (2026-08-04)
- **Componente:** web · **Depende de:** T-2.52
- **Origen:** los tres endpoints existían y **no tenían consumidor en ningún lado**. Es
  lo que desbloquea enrolar un teléfono real (GATE-HW).
- **Criterios:**
  - [x] Tarjeta por estación en `/fleet`: generar, listar con expiración y rol, revocar.
  - [x] El código se destaca una vez, sale del DOM a los 120 s, los existentes salen
        enmascarados y **nada toca `localStorage`/`sessionStorage`** (CLAUDE.md §8).

### [x] T-2.54 · Gestión de usuarios (Cognito) — COMPLETA (2026-08-04)
- **Componente:** api + web · **Depende de:** T-2.53
- **Origen:** superficie de seguridad NUEVA, y el bloqueante real de la Fase B de T-2.45:
  alguien tiene que poder escribir `custom:site_scope`.
- **Criterios:**
  - [x] Proxy del Admin API de Cognito con gate `manage_users` (superadmin +
        tenant_admin, **no** support), auditoría por escritura y jamás credenciales.
  - [x] **Escalada de privilegios cerrada**: sin `PLATFORM_ROLES` un `tenant_admin` se
        creaba un superadmin en un solo POST. `occupant` no es asignable aquí (vive en
        su propio pool con ancla pool→rol).
  - [x] Rol y grupo se mueven juntos, entrando al grupo nuevo ANTES de salir del viejo:
        `Claims.from_verified` exige `custom:role ∈ cognito:groups` y escribir solo el
        atributo crea un usuario fantasma.
  - [x] `site_scope` validado contra la DB: un UUID inventado dejaba al usuario con cero
        estaciones sin que nadie supiera por qué.
  - [x] Sin credenciales, el directorio es un stand-in que **GRITA** en cada escritura.
  - [x] **Pendiente de infra (T-2.57):** `TAKAB_API_COGNITO_USER_POOL_ID` en
        `deploy.sh` y permisos `cognito-idp:Admin*` en el rol de instancia. Sin ambos
        arranca SIMULADO.

### Bloque E · Transversal y cierre

### [x] T-2.55 · Degradación responsive, colisiones e invariantes de CSS — COMPLETA (2026-08-04)
- **Componente:** web · **Depende de:** T-2.54
- **Origen:** CERO media queries en toda la hoja, y tres overlays cayendo en la misma
  esquina del escenario.
- **Criterios:**
  - [x] 1920×1080 **no mueve un píxel**. Los breakpoints son DEGRADACIÓN: <1600 columnas
        más estrechas, <1280 una columna con el detalle como cajón, `max-height:800px`
        recorta paddings.
  - [x] Trampa documentada en la hoja: las custom properties **no funcionan dentro de
        `@media`**. Los tokens sirven al lado JS; las media queries llevan el px literal
        citando el token como fuente.
  - [x] Colisiones **por reubicación, no por z-index**: cada esquina tiene dueño y las
        dos pilas superiores se acotan al 46 % ⇒ la no-superposición es aritmética.
        Desviación deliberada: la alerta NO va dentro de MapPanel — desaparecería cada
        vez que el mapa falla, y es el elemento más crítico de la consola.
  - [x] `cssContract.test.ts` falla si un `className` usado no tiene regla. Al escribirlo
        aparecieron **siete bloques sin una sola regla**; todos arreglados escribiendo la
        regla, no relajando el test.
  - [x] **Hallazgo mayor:** `.soc-alert__grid/__num/__lbl` era el estilo de MAGNITUD
        PRELIMINAR y T-MINUS, funciones que `CLAUDE.md §8` PROHÍBE. Dejarlo vivo invitaba
        a recablearlas «porque el estilo ya existe». Eliminado.
  - [x] Guard de sanidad: un `/*` sin cerrar borra el bloque siguiente EN SILENCIO.
        Verificado por mutación, igual que el propio contrato.
  - [x] `StateFrame` completado donde faltaba; fuga `--soc-*` (prefijo inexistente, todas
        sus reglas caían al fallback) cerrada.

### [x] T-2.56 · Playwright con matriz de viewports — COMPLETA (2026-08-04)
- **Componente:** web + CI · **Depende de:** T-2.55
- **Origen:** ningún `project`, un solo viewport en un solo test y cero a11y automatizada.
- **Criterios:**
  - [x] 1280×800 / 1440×900 / 1920×1080. Specs de layout, alcance, simulacro, movimiento
        reducido y axe. 84 pruebas colectadas.
  - [x] Umbral de axe honesto: arranca en `critical` y ADJUNTA el resto con recuento.
        «Cero violaciones» el primer día produce un job rojo permanente que nadie mira, o
        un `disableRules` que lo vacía.
  - [x] Job `workflow_dispatch` **no bloqueante**.
  - [x] Trampa documentada: en Playwright 1.61 `reducedMotion` va en `contextOptions`.
        Escrito como opción de primer nivel **no falla**: se ignora, y el spec pasaría en
        verde sin emular nada. Solo `tsc` lo caza.
  - [ ] **Ejecución pendiente del deploy**: `make soc-local` invoca `make demo-db`, que
        RESIEMBRA la DB local. Los specs quedan escritos y colectados; se corren después.

### [x] T-2.57 · Redespliegue único a la nube — COMPLETA (2026-08-04)
- **Componente:** deploy · **Depende de:** T-2.56
- **Verificado en la nube VIVA:**
  - [x] PR #49 con los 6 checks en verde ⇒ merge a `main` (`c090778`). Base del PR
        verificada antes de mergear (precedente: un PR apilado aterrizó donde no era).
  - [x] Emulación arm64 comprobada ANTES de construir (`uname -m` ⇒ `aarch64`): el
        binfmt se pierde al reiniciar el host y una imagen x86 no arranca en Graviton.
  - [x] `/api/health` declara `c090778`; los 7 contenedores con ese tag.
  - [x] `alembic_version` = `0025_tenant_retire_codes`, que es el head local.
  - [x] **Gabinetes fantasma en producción: 0.** La migración de saneamiento de T-2.35
        hizo su trabajo sobre la DB viva — era el bug que abrió el ciclo.
  - [x] Endpoints nuevos vivos y pidiendo auth (401, no 500): `/audit`, `/users`,
        `/drills`, `/fleet/gateways`. El OpenAPI servido los declara.
- **Segundo redespliegue (`e4980da`, mismo día):** los arreglos de T-2.58 llegaron a la
  nube. `/api/health` ⇒ `e4980da`, 7/7 contenedores, bundle nuevo servido, y los cortes
  de compactación (1599 px, 1439 px) presentes en el CSS que sirve Caddy.
  `deployed.spec.ts` ⇒ **12/12** en los tres viewports.
- **Pendientes que NO son código y exigen intervención humana:**
  - [x] **Código de retiro rotado** para `TAKAB Dev` (2026-08-04, por SQL vía SSM con
        `crypt(…, gen_salt('bf'))` y auditado como `system:manual_rotation`). Se hizo
        por base y no por API porque el endpoint exige un ID token con MFA y no hay
        script commiteado para obtenerlo sin navegador. **1 código configurado.**
  - [x] **Los 6 `site-sim-*` activos, retirados** con sus 6 gabinetes propagados y
        auditados. Verificado: `site-sim activos = 0`, `gabinetes fantasma = 0`.
        **Cierra T-1.47.**
  - [x] **Estación de pruebas recuperada.** `site-dev` volvió a `active` y
        `gw-dev-0001` a `provisioned`. La había retirado la migración `0024` al heredar
        el retiro del sitio (hecho el 03-08 21:17, propagado el 04-08 13:22) mientras el
        Pi seguía publicando latidos. Verificado tras el arreglo: **último latido hace
        3 s, 60 latidos en la última hora**, 2 sitios activos y 2 gabinetes visibles.
        Deja al descubierto un hueco de diseño que NO se cierra aquí: un gabinete
        retirado que sigue latiendo desaparece EN SILENCIO en vez de gritar (ver
        T-2.58 §2.3).
  - [ ] **Cablear `TAKAB_API_COGNITO_USER_POOL_ID` en `deploy.sh` + permisos
        `cognito-idp:Admin*`** en el rol de instancia. Sin ambos, la gestión de usuarios
        arranca SIMULADA: grita en cada escritura, no finge. Exige `terraform apply`.
  - [ ] **`console_scope_enforced` sigue en `False`.** El bloqueante cayó con T-2.54,
        pero encenderlo antes de asignar alcances dejaría a cada `soc_operator` con cero
        estaciones. Secuencia: recorrer los `scope_gap` del `audit_log` → asignar por
        usuario → encender.
  - [ ] **Correr los e2e** contra el entorno desplegado (`npx playwright test`).

---

### [x] T-2.58 · Auditoría del panel del gabinete y su sincronía con la nube 2.2 — COMPLETA (2026-08-04)
- **Componente:** edge · **Depende de:** T-2.49, T-2.57
- **Motivo:** el ciclo 2.2 reformó la consola de la nube. El panel local del Pi —lo que
  ve un operador DE PIE frente al gabinete, sin nube y sin internet— no se había
  contrastado contra nada de eso. Es la superficie de la regla de oro 2.
- **Hallazgos corregidos:**
  - [x] **CRÍTICO · La feature congelada se pintaba como medición viva.**
        `signal.live_by_channel()` nunca desaloja: con SeedLink muerto, el último
        `Feature1s` seguía en `/api/status` con `age_s` creciendo sin límite. Los
        carriles miraban la edad; la barra de proximidad, los ejes de la brújula, el
        resumen para lector de pantalla y el punto de la rosa **no**. Reproducido con
        `age_s = 7200`: `PROXIMIDAD AL DISPARO → 0.001 g en VERDE · 2 % del disparo`.
        Es el incidente del 2026-07-14 (15 h ciego con la consola en OPERATIVO)
        trasladado al panel local, que es justo el que queda cuando no hay nube.
        Corregido con una sola puerta —`liveChannels(st)`— que consumen los cuatro:
        fuera de plazo el canal NO EXISTE (`S/D` ámbar, brújula `SIN SEÑAL DEL SENSOR`).
  - [x] **ALTO · Una prueba de sirena se leía como una alerta.** T-2.49 arregló el oído
        (`asset_for(TEST)`) y dejó la vista atrás: `siren_sounding` es un booleano
        eléctrico, así que quien llegaba a mitad de un self-test veía
        `SIRENA: SONANDO · SASMEX: NO`. Ahora `status()` publica `siren_reason` y el
        panel pinta `SIRENA: SONANDO · PRUEBA`.
  - [x] **MEDIO · Un tono rechazado dejaba al gabinete sonando otra cosa en silencio.**
        `HealthSnapshot.audio` solo viajaba a la nube, que lo DESCARTA (no hay columna en
        `device_health`); el único que puede actuar —quien está delante— no lo veía.
        Ahora `/api/status` publica el perfil (sin rutas de disco: es lectura abierta en
        la LAN) y `PROBAR SIRENA` advierte `SIN TONO DE PRUEBA: el voceo CALLA` **antes**
        del clic.
- **Cobertura nueva:** `edge/tests/panel_harness.js` (mini-DOM en Node, **cero
  dependencias** — el job `edge` del CI solo hace `uv sync`) ejecuta el `<script>` REAL
  del panel; `edge/tests/test_local_api_panel.py` con **67 tests** por `id` de zona, más
  un test de contrato que cruza el fixture contra `dashboard.status()` real. Suite edge:
  **598 passed** (+72). El CI gana un paso `node --version`: sin él, los 67 se saltarían
  EN SILENCIO por el `skipif` y el job seguiría verde cubriendo nada.
- **Huecos documentados y NO cerrados (exigen decisión de producto):**
  - [ ] **§2.3 · Un gabinete retirado no sabe que lo retiraron.** `retire_gateway` audita
        y no publica nada: el gabinete queda sin config firmada y sin comandos, y el
        panel sigue diciendo `ENLACE NUBE · CONECTADO` porque el MQTT sí vive. Ningún
        topic nube→edge transporta hoy ese aviso. **Requiere contrato nuevo.**
        → **Promovido a tarea propia: T-2.60**, donde se parte en la mitad que se puede
        hacer ya (60.a, la consola delata al fantasma vivo) y la que espera decisión de
        producto (60.b, el gabinete se entera).
  - [ ] **§2.5 ·** El catálogo SSN no declara edad ni procedencia: una instantánea de
        hace tres semanas se ve igual que una recién firmada.
  - [ ] **§2.6 ·** El panel no tiene vista de evidencia/backfill (la consola sí, T-2.43).
  - [ ] **§2.7 ·** `RELÉS · S/D · arranque en frío` colapsa tres causas distintas.

### [x] T-2.59 · Barrido visual de las 6 pantallas y cierre de la regla de oro 7 — COMPLETA (2026-08-04)
- **Componente:** web · **Depende de:** T-2.56
- **Método:** revisión visual medida (58 capturas, 3 viewports) + batería sistemática
  nueva `web/e2e/screens.spec.ts` (**114 tests** = 38 × 3 viewports).
- **Defectos REALES corregidos:**
  - [x] **G7 · `/fleet` pintaba `0 GABINETES · 0 OPERATIVOS · 0 DEGRADADOS · 0 SIN
        ENLACE` con sus colores normales mientras la API estaba caída.** La tira de KPI
        vive FUERA del `StateFrame`, así que un fallo se leía como una flota de cero
        gabinetes en perfecto estado. Reproducido en navegador con toda la API a 500.
        Ahora `S/D` **sin color semántico**; el cero legítimo sigue siendo cero.
  - [x] **G7 · `/triage` anunciaba `0 INCIDENTES CARGADOS` junto a su propio error.**
        Cero incidentes tras un sismo es la afirmación más tranquilizadora de esa
        pantalla. Ahora `SIN DATO · HISTORIAL NO DISPONIBLE`.
  - [x] **El pie de la cola de incidentes se salía de la pantalla a 1280×800.**
        `@media (max-height:800px) { .soc-incidents { max-height: 170px } }` prometía en
        su comentario que la cola "scrollea" y nunca se le dio `overflow`: 41 px fuera
        con `body` y `.soc-shell` en `overflow:hidden`, o sea **sin ninguna barra que
        sacar**. Afectaba a REUBICAR EPICENTRO / SOLICITAR DICTAMEN / CONFIRMAR ACUSE.
        Tercera reaparición de la familia (T-2.51 `.mt__list`, T-2.58 `.triage`).
  - [x] **`CONFIRMAR ACUSE` deshabilitado parecía armado**: `opacity: 1`,
        `cursor: pointer` y el cian pleno de llamada a la acción. En el botón más
        consecuente del producto eso se lee como "el sistema no responde". Ahora
        `.soc-confirm:disabled` con el idioma que ya usaba el resto del repo, y el
        `title` del envoltorio (`gateTitle`) que le faltaba solo a él desde T-1.51.
  - [x] **La atribución NATIVA de MapLibre pisaba el panel de leyendas** 2853 px²
        (357×8) en los tres viewports. Duplicaba unos créditos que el panel ya pinta en
        `.soc-map__attribution`, así que se quita el control, no el crédito — con un
        test que exige que OpenFreeMap y OpenStreetMap sigan visibles.
  - [x] **Regla CSS muerta desde T-1.54.** `soc.css` declaraba
        `@media (max-width:1100px) { .mt,.fleet,.audit,.triage { overflow-y: visible } }`
        y **nunca se aplicó**: `soc-tabs.css` se importa después (main.tsx) y declara
        `overflow-y: auto` sobre los mismos selectores sin media query; una @media no
        añade especificidad. Medido a 640/900/1100 px: `auto` en los tres. Se elimina
        documentando la verdad (el scroll interno con topbar fija es lo correcto para un
        SOC) y un test nuevo la caza si vuelve.
- **Verificado y en orden:** el **menú del operador NO se solapa** con nada (era la queja
  del usuario) — 260×142, dentro del viewport en los tres tamaños, y sus tres controles
  reciben su propio clic; el scroll de EVALUACIÓN funciona de verdad (`scrollHeight 971`
  vs `clientHeight 740`, último elemento alcanzable); cero desborde horizontal en 8 rutas
  × 3 viewports; estado de error presente en las 6 pantallas; `prefers-reduced-motion`
  apaga las dos animaciones en ambos sentidos.
- **Anotado, no corregido en su momento — CERRADO por T-2.64 (2026-08-05):**
  numeración `05` duplicada (`AuditPage` y `BuildingPage`); contraste 3.48:1 del token gris en
  rótulos de 8–10 px (AA pide 4.5) — se creía que salía de un solo token y resultaron ser
  DOS copias, la del paquete y una paleta hardcodeada en el panel del gabinete; la columna
  de detalle de `/console` reserva 320–408 px aunque esté vacía. Los tres se anclan ahí por
  tests de vitest y del edge, no por revisión visual: `axe.spec.ts` no los bloqueaba y además
  **el e2e no es gate** (`e2e.yml` es `workflow_dispatch` con `continue-on-error`).
  *Historia de esta línea, que vale más que la línea:* llegó a decir **"CERRADO por
  T-2.64"** —pretérito— **con T-2.64 todavía en `[ ] · EN CURSO`**. Es exactamente la clase
  de mentira que este ciclo vino a matar, y el regex de cierres cruzados **no la veía por
  estar en voz pasiva**. Se reescribió en presente-abierto hasta que T-2.64 cerró de verdad,
  y de paso el regex aprendió a leer la forma pasiva y los IDs entre backticks.
- **Números:** e2e **210 passed / 3 skipped** (los 3 son `deployed.spec.ts` saltándose a
  propósito la comprobación de producción en localhost) · unitarias web **1130** · api
  **1208** · edge **598** · mobile **201** · `make lint`, `make drift` y `vite build`
  limpios.

---

### [x] T-2.60 · Un gabinete retirado desaparece en silencio — DECISIÓN + CONTRATO · COMPLETA (2026-08-06)

> **Estado (2026-08-05): 60.a ENTREGADA · 60.b DECIDIDA, sin implementar.** La mitad que
> cerraba el daño operativo está en la nube. La decisión de producto que 60.b pedía se
> ratificó —opción **(A)**— y su implementación vive en `T-2.65`, que la lleva al sobre de
> config firmado. Queda en `[~]` y no en `[x]` porque el gabinete **todavía no se entera**
> de que lo retiraron: hoy sigue diciendo `ENLACE NUBE · CONECTADO` sin más.
- **Componente:** api + web (60.a) · api + edge + contrato (60.b)
- **Origen:** T-2.58 §2.3. No es una regresión: es un hueco que lleva desde T-2.35 y que
  **se cobró su primera víctima el 2026-08-04** (ver "Qué pasó de verdad", abajo).

#### El hecho, verificado en código

`retire_gateway` (`api/src/takab_api/routers/fleet.py:348-391`) hace exactamente dos cosas:
`set_gateway_status(conn, gateway_id, "retired")` y `audit_async(...)`. **No hay ninguna
llamada a `publish`.** Los únicos cuatro topics nube→edge que existen son
`takab/cmd/{thing}`, `takab/cfg/{thing}`, `takab/catalog/{thing}` y
`takab/backfill/grant/{thing}` (`edge/takab_edge/config/settings.py:265-296`), y ninguno
transporta estado administrativo. **La palabra `retired` no aparece ni una vez en
`edge/takab_edge/`**: el concepto no existe de ese lado.

Consecuencia: al retirar, el gabinete deja de ser candidato de config firmada y de
comandos, pero **sigue publicando latidos, sigue leyendo el Shake y sigue actuando la
sirena por SASMEX** — que es justo lo que las reglas de oro 1 y 2 exigen. Lo que falla no
es la actuación: es que **nadie se entera, en ninguno de los dos lados**.

- En la nube: el filtro de T-2.35 lo esconde del inventario. Correcto para un gabinete
  desmontado; **mentiroso para uno que está latiendo cada 60 s**.
- En el gabinete: el panel sigue diciendo `ENLACE NUBE · CONECTADO`, porque el MQTT
  **sí** vive. La única huella local es que `config_version` deja de subir, y el panel lo
  muestra sin edad (`config v17`), así que es invisible.

#### Qué pasó de verdad (2026-08-04)

Se retiró el sitio `site-dev` el 03-08 a las 21:17. La migración `0024` propagó ese retiro
al gabinete el 04-08 a las 13:22. Desde entonces **`gw-dev-0001` siguió publicando
latidos sin interrupción** —al restaurarlo se midió *último latido hace 3 s, 60 latidos en
la última hora*— mientras era invisible en la consola. Se detectó porque el operador
preguntó por qué no veía su estación, no porque el sistema lo dijera. **Con un cliente
real, la pregunta habría sido por qué un edificio llevaba semanas sin supervisión.**

---

#### 60.a · La consola delata al fantasma vivo — NO exige contrato nuevo ni decisión

Esta mitad se puede hacer ya y es la que cierra el daño operativo. Todo el dato necesario
ya está en la base: `gateways.status` y el último `device_health.ts`.

- [x] **HECHO (2026-08-05).** El gabinete `retired` que **sigue latiendo** sale siempre en
      `/fleet`, en sección propia con `role="alert"` y borde crítico
      (`RETIRADO · PERO SIGUE REPORTANDO`), con la fecha, quién lo retiró y la decisión
      que se le pide. **No se puede desactivar** con `include_retired`: esconder a un
      aparato que habla no es limpiar el inventario, es perder de vista un edificio.
- [x] **HECHO.** KPI `FANTASMAS` que **solo aparece cuando hay alguno** — un contador
      clavado en cero deja de leerse a las dos semanas, y este tiene que dar un salto.
      Los fantasmas se apartan ANTES de contar: no engordan `GABINETES` ni `OPERATIVOS`,
      porque están dados de baja.
- [x] **HECHO (2026-08-05, PR #52).** Alarma. Cuando se escribió lo de arriba, **nadie en
      la API publicaba métricas a CloudWatch**; ahora sí. El worker `notify` emite
      `GhostGatewaysAlive` en `Takab/Ops` cada 60 s, de gorra en su bucle (ya despierta
      cada pocos segundos con una conexión caliente; un proceso propio para publicar un
      entero por minuto sería desproporcionado).
      - **Se publica SIEMPRE, incluido el cero.** Es la lección cara de la alarma de
        gabinete mudo: si la métrica solo existe cuando hay algo que contar, la alarma
        vive en `INSUFFICIENT_DATA` y todo depende de `treat_missing_data`, que ya falló
        de cuatro maneras distintas. Con un 0 cada minuto, "sin datos" significa UNA sola
        cosa: el worker está caído.
      - Por eso esta alarma **NO usa `treat_missing_data = "breaching"`** como
        `gateway-offline`: allí la ausencia de heartbeat ES la condición vigilada, aquí la
        ausencia de métrica solo dice que nos quedamos ciegos. Queda en `"missing"` y la
        ceguera se pagina por `insufficient_data_actions` (callar nunca es seguro, G7).
      - **Nunca puede tumbar a `notify`**, que avisa de sismos: va envuelta, se estrangula
        sola y un fallo se REGISTRA. Hay test sobre el bucle real, no solo sobre la clase.
      - Umbral **1 h sostenida** (12 × 5 min): retirar un gabinete enchufado y luego ir a
        desmontarlo es legítimo; que ese estado se quede ahí, no.
      - IAM: `cloudwatch:PutMetricData` no admite ARN, así que se acota por la condición
        `cloudwatch:namespace`. **Apagada por defecto**; la enciende solo `deploy.sh`.
      - [ ] **PENDIENTE DE MAURICIO: `terraform apply`** para crear la alarma y el permiso
            `PutOpsMetrics`. Sin ellos el worker registra el fallo y sigue notificando —
            la métrica no sale, pero nada se rompe.
      - [ ] **TRAS EL APPLY (criterio de la tarea, no una cortesía): confirmar que
            `takab-dev-gateway-retirado-sigue-reportando` SALE de `INSUFFICIENT_DATA`.**
            Debe llegar el correo de `ok_actions` en los ~15 min siguientes (la métrica se
            publica cada 60 s y el periodo de la alarma es de 5 min). Sin esperar al correo:
            `aws cloudwatch describe-alarms --alarm-names
            takab-dev-gateway-retirado-sigue-reportando --query 'MetricAlarms[0].StateValue'`
            y, si sigue en `INSUFFICIENT_DATA`, `aws cloudwatch get-metric-statistics
            --namespace Takab/Ops --metric-name GhostGatewaysAlive --statistics Maximum
            --period 300 --start-time … --end-time …` (cero datapoints = la métrica no está
            saliendo del EC2).
            **Por qué esto es un paso y no un detalle:** `insufficient_data_actions` solo
            dispara EN TRANSICIÓN. Una métrica que no se publica NUNCA desde el primer día
            deja la alarma **nacida** en `INSUFFICIENT_DATA` y aparcada ahí: sin transición,
            sin correo, y el panel enseñando un estado que se lee como "aún no hay datos".
            Esta alarma protege contra una métrica que **se para**, no contra una que **nunca
            arranca** — que es exactamente la forma que tuvo el fallo del 2026-08-05
            (`count_ghosts` leía la fila por posición contra una conexión `dict_row`:
            `KeyError: 0` en cada llamada, tragado por el `except`; no salía ni el cero). La
            única señal de "nunca arrancó" es ese correo de `ok_actions` al salir por primera
            vez de `INSUFFICIENT_DATA`, y **su ausencia tras el apply es el indicio**.
      - [ ] **Si a los ~15 min no hay correo ni datapoints**, el orden de diagnóstico —el
            correo NO distingue el porqué: cinco fallos distintos colapsan en el mismo
            silencio—: 1) el worker `notify` no está corriendo; 2) `count_ghosts` lanza;
            3) `build_ghost_gauge` dejó `client=None` **sin excepción** (boto3 sin
            credenciales, `notify/worker.py:40-49`); 4) IAM sin `PutOpsMetrics` o con la
            condición `cloudwatch:namespace` mal puesta; 5) `TAKAB_API_OPS_METRICS_ENABLED`
            sin poner — es `False` por defecto (`settings.py:111`) y solo la enciende
            `deploy/cloud/deploy.sh:43`, así que un arranque manual del contenedor la deja
            apagada y todo lo demás parece sano.
            **El `logger.warning` NO sale del EC2:** `deploy/cloud/docker-compose.yml:27,115`
            usa `logging: driver: json-file`, y no hay agente CloudWatch ni log group de la
            aplicación. Ese registro es una miga forense para quien ya entró por SSM
            (`docker logs`), no una alerta — nadie se entera por él.
- [x] **HECHO.** Tests: retirar con latido fresco NO lo esconde; retirar uno mudo —o que
      nunca latió— sí lo esconde (T-2.35 intacto); el retiro por herencia del SITIO
      también lo delata (el caso REAL del 04-08); el fantasma dice cuándo y quién; un
      gabinete normal no lleva la bandera; y el tenant B no ve el fantasma del A.

**Implementación (para quien lo lea luego):**
- `is_ghost` se deriva de `derived_state != SIN ENLACE`, **no** de `age_s` suelto: "vivo"
  tiene UNA sola definición en el producto y así no puede divergir.
- El umbral viaja del router a la query (`alive_s`, sin defecto a propósito) para que la
  fila que pasa el filtro sea exactamente la que se rotula.
- `retired_at`/`retired_by` salen del `audit_log` por LATERAL — `gateways` no tiene
  `retired_at`, y añadirlo duplicaría un hecho ya escrito en una tabla append-only.
- **Migración 0026:** índice `(object, ts DESC)` en `audit_log`. Sin él eso sería un
  escaneo secuencial de la única tabla que por la regla de oro 11 no se poda jamás.

#### 60.b · El gabinete se entera — EXIGE DECISIÓN DE PRODUCTO

**La pregunta que hay que responder antes de escribir una línea:** ¿qué debe hacer un
gabinete retirado que sigue protegiendo un edificio con gente dentro?

Las reglas de oro acotan la respuesta más de lo que parece. La 1 dice que el camino
SASMEX→actuador **nunca** depende de la nube; la 2, que el edge opera sin nube. Un retiro
es un acto administrativo que viaja por la nube: **dejar que apague la protección
convertiría un clic de inventario en una desprotección física**, y eso contradice las dos.
Por eso la opción "se apaga al retirarse" se considera descartada salvo que se ratifique
explícitamente lo contrario.

- [x] **DECIDIDO (2026-08-05): opción (A)**, ratificada por Mauricio. La ficha completa de
      la decisión —con el porqué de (A), por qué (B) es peor y por qué (C) queda
      descartada— vive en `T-2.65`, que es donde se implementa. Las tres casillas de abajo
      se ejecutan **allí**, no aquí.
Las tres opciones que se evaluaron, y que quedan aquí como registro de la deliberación:

      - **(A) Sigue protegiendo y lo declara.** El retiro es administrativo. El panel
        muestra un aviso permanente e inequívoco (`DADO DE BAJA EN LA NUBE · SIGUE
        PROTEGIENDO`), y la sirena sigue actuando por SASMEX. Es lo que ya ocurre de
        facto; esto solo lo hace visible y deliberado.
      - **(B) Igual que A, pero además el gabinete deja de emitir** para no ensuciar la
        nube con datos de un sitio dado de baja. Cuidado: el silencio es indistinguible
        de una avería, y perderíamos la señal que permite detectar el error de 60.a.
      - **(C) Se apaga.** Solo si se ratifica que un retiro puede desproteger un edificio.
- [ ] Una vez decidido: añadir el estado administrativo al **sobre de config firmado**
      (`takab/cfg/{thing}`) en vez de inventar un topic — el sobre ya está firmado,
      versionado y con ack, y su camino ya está probado. Nota: el gabinete retirado **deja
      de ser candidato de config**, así que hay que publicarle el sobre del retiro **antes**
      de sacarlo de la lista, o el aviso no sale nunca. Es el detalle donde esto se rompe.
- [ ] El panel pinta el aviso con la precedencia que le corresponda entre los banners
      (nunca por encima de una alerta sísmica real).
- [ ] Test de extremo a extremo: retirar desde la consola ⇒ el aviso aparece en el panel
      del gabinete; restaurar ⇒ desaparece.

#### Nota de secuencia

**60.a no depende de 60.b.** Si la decisión de producto tarda, 60.a se entrega igual y ya
evita que vuelva a pasar lo del 04-08: el fantasma vivo deja de ser invisible en la nube,
que es donde alguien lo va a mirar.

---

# RUTA AL CIERRE DEL PROYECTO (escrita el 2026-08-05 · T-2.61)

Hasta hoy **no existía una ruta escrita hacia el cierre**. `PLAN-MAESTRO-TAKAB.md` solo
cubría la Fase 1 y está agotado; los work packages A/B/C de `BLUEPRINT §13` también; y este
archivo no tenía nada después de `T-2.60`. Lo que sigue es esa ruta, completa, hasta un
cliente con un edificio protegido y un documento firmado.

## Cómo se lee esta ruta

Cada tarea lleva **etiqueta de bloqueo**. La etiqueta no dice qué tan difícil es: dice
**quién puede desbloquearla**.

| Etiqueta | Quién | Qué significa |
|---|---|---|
| `SOFTWARE` | equipo de subagentes, hoy | no espera a nadie; se puede empezar ahora mismo |
| `HUMANO-AWS` | Mauricio con `!` | exige `terraform apply` / consola AWS / credenciales |
| `FÍSICO` | Mauricio, en sitio | exige hardware real, manos y ojos en el gabinete |
| `LEGAL` | abogado / cliente | exige un tercero que no es de ingeniería |
| `DECISIÓN` | producto | exige elegir, no construir |

**Regla de ordenación (queda escrita para que nadie la reinvente):** el carril de gates
(**Bloque III**) corre **en paralelo, con dueño humano, desde el día 1**. **Ninguna tarea de
los Bloques I o II depende de que un gate cierre para empezar.** Donde una tarea de
software produce el insumo de un gate, **la tarea se cierra con el insumo entregado y el gate
se marca aparte**. Confundir las dos cosas es lo que dejó a `G-04` abierto desde el hito de
Fase 1 mientras el backlog de software avanzaba 60 tareas.

**Las tres excepciones, escritas aquí para que la regla no se lea como universal.** La
primera edición de esta ruta (2026-08-05, el mismo día) decía *"Bloques I, II **o IV**"* y se
contradecía con el preámbulo del propio Bloque IV cuatrocientas líneas más abajo — las dos
frases en negrita, y quien planificara sacaba conclusiones opuestas según cuál leyera primero.
Corregido en T-2.61 y anclado por
`api/tests/test_docs_consistency.py::test_la_regla_de_ordenacion_no_exime_a_un_bloque_que_espera_un_gate`.

1. **El Bloque IV sí espera a `G-04`** (y al cierre del Bloque II). No es agenda: **no se le
   añaden funciones a un sistema cuya cadena de vida —contacto seco → relé → sirena— todavía
   no se midió en hardware real**. La razón completa vive en el preámbulo del Bloque IV.
2. **`T-2.94` (`G-06`, `G-08`) espera a `T-2.78`**, que es del Bloque II. Es el **único cruce
   Bloque III → Bloque II** de toda la ruta: un simulacro con *cascada de notificación real*
   no se acredita mientras SMS y WhatsApp sigan simulados (T-2.75). Las otras tres sesiones
   físicas no salen de su bloque: `T-2.92` y `T-2.93` no esperan a nada y `T-2.95` solo a
   `T-2.91`.
3. **`G-09` no se cierra en el Bloque III sino en `T-2.74`** (Fase 2.6), porque es una ventana
   AWS sobre software que sí controlamos, no una sesión con manos en el gabinete. Anotado
   también en la nota de la Fase 2.11, que es donde se va a buscar.

---

## BLOQUE I · Cerrar lo anterior

## Fase 2.3 · Higiene, paridad y deuda visual — `SOFTWARE`

**Objetivo:** dejar el repositorio **sin afirmaciones falsas sobre sí mismo** y sin caminos
donde el CI y el desarrollador local vean cosas distintas. Es la fase que hace fiables a
todas las demás: mientras un `make test` verde no signifique lo mismo que un CI verde, ningún
"está hecho" de las fases siguientes vale nada.

`T-2.60.a` (la consola delata al fantasma vivo) ya está entregada arriba, dentro de T-2.60.

### [x] T-2.61 · Reconciliación documental y ruta al cierre — `SOFTWARE` · COMPLETA (2026-08-05)
- **Componente:** docs + api/tests · **Depende de:** —
- **Defecto:** la documentación lleva meses declarando cosas que el repo desmiente, y no había
  ninguna prueba que lo cazara. Las cinco mentiras medidas:
  - la cabecera de este archivo decía *"9 de 9 tareas en verde"* con **134 tareas** dentro —
    36 tareas de retraso;
  - el marcador del **gate #5** (REST+WS vs GraphQL) seguía etiquetado *"confirmar/override"*
    **tres líneas por encima de su propia ratificación** (`T-1.22`:
    `[DECISION 2026-07-06]: Gate #5 ratificado — REST + WS nativo, SIN GraphQL`), y esa
    ratificación llevaba **un mes** sin propagarse a las etiquetas vivas;
  - T-2.57 declaraba *"Cierra T-1.47"* con evidencia medida mientras T-1.47 seguía en `[~]`;
  - `RBAC-TAKAB.md §8` listaba como PENDIENTE un disparador implementado desde T-1.27
    (`web/src/features/console/useAutoPopup.ts:11-12`);
  - la app móvil seguía siendo *"fase posterior"* en cuatro sitios con la Fase 2 mergeada.
- **Criterios de aceptación:**
  - [ ] `api/tests/test_docs_consistency.py` con 5 asserts que **fallan por separado y dicen
        por qué**: marcadores muertos, "fase posterior" en RBAC, cruce pop-up docs↔código,
        cabecera vs. conteo real de `^### [.]`, y coherencia de cierres cruzados.
  - [ ] Las 7 reconciliaciones aplicadas y citadas.
  - [ ] Esta ruta escrita, con etiquetas de bloqueo, ruta crítica e invariantes.
- **Trampa que deja escrita:** el assert del conteo **impone una obligación permanente** —
  ver "Conteo de tareas" en la cabecera de este archivo. No es fricción arbitraria: es lo
  único que impide que la cabecera vuelva a mentir 36 tareas.

### [x] T-2.62 · `make test` y el CI no corren lo mismo — `SOFTWARE` · COMPLETA (2026-08-05)
- **Componente:** repo (Makefile) · **Depende de:** —
- **Defecto:** `ci.yml:124-125` corre `npm run build` (tsc + vite) en el job `web`. `make test`
  y `make lint` **no**. Un error de tipos o de build llega a verde local y muere en el PR, que
  es el peor momento para descubrirlo y el más caro de diagnosticar.
- **Criterios de aceptación:**
  - [ ] Un test de paridad **lee `ci.yml` y el `Makefile`** y exige que todo paso de CI tenga
        su equivalente local. Comparar prosa no sirve: hay que comparar los comandos.
  - [ ] `make test` (o el target que el test declare) incluye el build de web.
  - [ ] El test falla si mañana alguien añade un paso al CI y no al `Makefile`.

### [x] T-2.63 · Skips mudos del job `edge` — `SOFTWARE` · COMPLETA (2026-08-05)
- **Componente:** edge/tests · **Depende de:** —
- **Defecto:** 5 tests de hardware se saltan **en silencio** cuando el Raspberry Shake no es
  alcanzable por socket, y el job sigue verde. Es exactamente el patrón que T-2.58 ya cazó en
  el CI con los 67 tests del panel (`node --version`): un job verde que no cubre nada.
- **Criterios de aceptación:**
  - [ ] Censo explícito: un `skipif` de alcanzabilidad de socket **sin registrar rompe el
        build** (`edge/tests/test_hardware_gates.py`).
  - [ ] El censo distingue un gate de hardware de un skip que no lo es (el `skipif` de `node`).
  - [ ] Ningún test se salta sin que el resultado del job lo **declare**.

### [x] T-2.64 · Deuda visual heredada de T-2.59 — `SOFTWARE` · COMPLETA (2026-08-05)
- **Componente:** web + edge (panel) · **Depende de:** T-2.59
- **Defecto:** T-2.59 los anotó y no los corrigió, a propósito. Son tres:
  - **numeración `05` duplicada** entre `AuditPage` y `BuildingPage` — dos pestañas con el
    mismo número en un producto que se opera diciendo números en voz alta;
  - **contraste 3.48:1** del token gris en rótulos de 8–10 px (AA pide 4.5). Sale de **un solo
    token**, y tiene una **copia hardcodeada en el panel del edge** — si se arregla solo la
    web, el gabinete se queda con el defecto justo donde no hay nube que ayude;
  - la **columna de detalle de `/console` reserva 320–408 px** aunque esté vacía.
- **Criterios de aceptación:**
  - [ ] Numeración única, verificada por test sobre los rótulos reales.
  - [ ] Contraste ≥ 4.5:1 en los dos espejos (token web **y** copia del panel del edge), con
        el test que lo bloquee — hoy `axe.spec.ts` no lo caza.
  - [ ] La columna vacía deja de reservar ancho; medido en los 3 viewports.

**DoD de la Fase 2.3:** cero afirmaciones documentales falsas (probado, no revisado a ojo);
paridad local↔CI verificada por test; ningún test se salta sin declararlo; y la consola ya no
esconde un gabinete retirado que late.

---

## Fase 2.4 · Los cuatro huecos de contrato nube↔edge — `SOFTWARE`

Cierra los cuatro `[ ]` que T-2.58 dejó documentados y **no** cerró (§2.3, §2.5, §2.6, §2.7).
Es **la pieza de ingeniería más sustancial que queda** y la única que toca un contrato entre
las dos mitades del sistema. Regla dura de la fase: **el edge no gana ni un topic nuevo**.

### [x] T-2.65 · El sobre de config firmado transporta el estado administrativo — `SOFTWARE` · COMPLETA (2026-08-06)
- **Componente:** api + edge + contrato · **Depende de:** T-2.60.a · **Cierra T-2.60.**
- **Origen:** T-2.58 §2.3, promovido a T-2.60.b.
- **`DECISIÓN` RATIFICADA (2026-08-05) — opción (A): un gabinete retirado en la nube SIGUE
  PROTEGIENDO, y lo declara.**
  - **Por qué (A):** el retiro es un **acto administrativo que viaja por la nube**. Que
    apagara la protección convertiría un clic de inventario en la **desprotección física de un
    edificio con gente dentro** — contra las reglas de oro 1 (el camino SASMEX→actuador nunca
    depende de la nube) y 2 (el edge opera sin nube).
  - **Por qué (B) es peor, no más limpio:** callar para "no ensuciar la nube" hace que el
    silencio sea **indistinguible de una avería**, y **destruiría justo la señal que T-2.60.a
    usa para detectar el error**. La única razón por la que el fantasma del 04-08 es
    detectable es que seguía latiendo.
  - **(C) descartada.** Reabrirla exige ratificar explícitamente que un retiro puede
    desproteger un edificio.
- **Criterios de aceptación:**
  - [x] **Ningún topic nuevo.** Viaja en el sobre firmado `takab/cfg/{thing}`. Corrección al
        enunciado original, medida: ese sobre **NO tiene ack** (`_handle_config` no publica
        nada, ni en éxito ni en fallo — los COMANDOS sí, la config no) y **`config_version` no
        viaja en el latido**, así que `in_sync` es nube-contra-nube, no un espejo de lo
        aplicado. Consta aquí porque de ahí cuelgan dos de los pendientes de abajo.
  - [x] **El sobre del retiro se publica ANTES de sacar al gabinete de la lista de
        candidatos.** El `WHERE` pasa a `(g.status <> 'retired' OR st.payload->>'cloud_admin_state'
        IS DISTINCT FROM 'retired')`: entra exactamente una vez y luego deja el flujo. Quitar
        `g.status <> 'retired'` a secas —lo primero que uno escribe— lo habría dejado dentro
        para siempre, republicándolo en cada edición de rule_set o de equipment.
  - [x] El panel pinta `DADO DE BAJA EN LA NUBE · SIGUE PROTEGIENDO` en la posición más baja
        de la pila de banners, con `role="status"` y no `aria-live="assertive"`: es un hecho
        administrativo, no una emergencia. Test que lo mide con una alerta sísmica simultánea.
  - [x] **La sirena sigue actuando por SASMEX con el gabinete retirado**, y el test lo MIDE
        (dispara el reflejo y lee los relés) en vez de afirmarlo. Cubre los **seis** caminos de
        actuación, no solo el reflejo: `_act_and_publish` (gas, ascensor, puertas, LoRa), el
        voceo, el traspaso HW→software de SPOF-02 y el comando firmado del quórum (T-2.32).
        El invariante fijado **no** es «ninguna config toca estos canales» —eso rompería el
        filtro de equipamiento de T-2.31— sino que **el estado administrativo no gatea
        ninguno**: se demuestra con sitio retirado **y** sin gas cableado, midiendo las dos
        mitades a la vez.
- **`[ ]` PENDIENTE DE DESPLIEGUE — no es código, y por eso la tarea se cierra sin ello**
  (mismo criterio que T-2.57: una tarea `[x]` puede tener casillas abiertas si declaran que
  esperan a un humano):
  - [ ] **E2E real: retirar desde la consola desplegada ⇒ el aviso aparece en el panel del
        Pi; restaurar ⇒ desaparece.** El camino está cubierto **tramo a tramo** por test,
        incluido el de sobre-firmado→`apply_signed_update`→`/api/status`, pero el extremo a
        extremo exige la nube desplegada y el gabinete físico. Se acredita junto a `G-05`.
  - [ ] **Migración `0027` aplicada.** Sin ella el aviso sale por el poll de respaldo del
        worker (≤30 s) en vez de al instante; nada se rompe, solo tarda.
- **Notas de implementación (medidas contra el código real, no supuestas):**
  - **Predicado elegido: "exactamente una vez".** El `WHERE` de `_CANDIDATES_SQL` pasa a
    `(g.status <> 'retired' OR st.payload->>'cloud_admin_state' IS DISTINCT FROM 'retired')`.
    Quitar el filtro a secas habría dejado al retirado DENTRO del flujo de config para
    siempre. Recibido el sobre, sale; al restaurar, vuelve a entrar y republica `active`.
  - **La base del documento lleva COALESCE de DOS ramas, jamás una tercera `'{}'`.**
    Medido: la variante de tres ramas convierte en candidatos a gabinetes **activos** que
    hoy se saltan a propósito (sin rule_set activo, o con uno sin bloque `edge`) y —al ser
    `apply_signed_update` reemplazo total— les apagaría `command_enabled` (la actuación por
    quórum) y devolvería los umbrales a la banda por defecto. Rompe además el guardarraíl
    preexistente `test_ruleset_without_edge_key_publishes_nothing`.
  - **Falso que el retiro despertara al worker.** El único trigger sobre `gateways` era el de
    `equipment` (0022). Sin la migración `0027` el aviso salía por el poll de respaldo, hasta
    30 s tarde. El `WHEN` de `0027` se acota a transiciones que entran o salen de `retired`
    porque la ingesta reescribe `gateways.status` con cada LWT.
  - **La alarma de T-2.60.a se acotó** a los que aún no recibieron su sobre: con la opción (A),
    "retirado + latiendo" es legítimo y permanente, y una alarma siempre encendida deja de
    leerse.
  - **Primera pasada tras el despliegue = republicación de TODA la flota** (el doc gana una
    clave): un bump de versión y un publish por gabinete, y la consola pinta PENDIENTE durante
    una pasada. Benigno, pero hay que anticiparlo.
  - **Orden de despliegue: la nube puede ir primero** — `EdgeSettings` usa `extra="ignore"`.
    Si alguien lo cambiara a `forbid`, este mismo cambio tumbaría la config de toda la flota.
  - **`PENDIENTE`: el sobre de `cfg` se publica SIN `retain`.** Si el Pi está apagado más que
    la sesión persistente de IoT Core, el mensaje se descarta y `gateway_config_state` ya se
    actualizó ⇒ **no se republica jamás**. Es una laguna preexistente de TODO el config sync
    (T-1.23), no creada aquí, y `CommandPublisher.publish` es el mismo Protocol que usan los
    comandos de actuación —donde un `retain` sería catastrófico—, así que arreglarlo exige un
    kwarg por llamada y su propia tarea. Anotado, no cerrado.

### [x] T-2.66 · El catálogo SSN declara edad y procedencia — `SOFTWARE` · COMPLETA (2026-08-06)
- **Componente:** edge (panel) + api · **Depende de:** T-2.24 · **Origen:** T-2.58 §2.5
- **Defecto:** una instantánea del catálogo de hace tres semanas se ve **idéntica** a una
  recién firmada. Es la regla de oro 7 (`stale`) sin cumplir en el gabinete.
- **Criterios de aceptación:**
  - [x] El panel muestra **edad** y **origen**. Corrección al enunciado: no mostraba «solo la
        versión» — no mostraba **ninguna de las tres**. `status()` no tenía sección de catálogo.
  - [x] Umbral **48 h sobre `captured_at`**, y **viaja en el payload** (`stale_after_s`), no es
        una constante escondida en JS. Qué se degrada, medido: los cuatro consumidores del
        catálogo son de pantalla y **solo dos afirmaciones se vuelven falsas** con la edad —el
        conteo de sismos (se lee «recientes», son «los que había en la captura») y el «más
        cercano»—. Pasan a ser relativas a la captura. El mapa y la comparativa **no envejecen**
        y siguen vivos: sus referencias son 8 ciudades y un sismo histórico.
  - [x] Test con catálogo envejecido. **La edad se calcula en Python**, no en el navegador: el
        arnés `panel_harness.js` expone el `Date` REAL, así que un test que dependiera de
        `new Date()` caducaría con el calendario.
- **Desviación deliberada, y no es una excepción:** aquí la doctrina de T-2.58 se cumple
  **ROTULANDO, no borrando**. Un canal fuera de plazo se borra porque **afirma ser una medición
  de ahora**; el catálogo es explícitamente una instantánea **fechada** cuyos datos no se pudren
  —la magnitud de un sismo del 31-jul sigue siendo verdad hoy—. Borrarlo habría apagado el mapa
  y la comparativa para castigar una afirmación que se arregla con un rótulo.
- **`captured_at` naive se lee como UTC, no como UTC−6.** Es la lectura conservadora: en México
  hace la instantánea 6 h **más vieja**, nunca más joven. Regla de oro 7.

### [x] T-2.67 · El panel local gana vista de evidencia/backfill — `SOFTWARE` · COMPLETA (2026-08-06)
- **Componente:** edge (panel) · **Depende de:** T-2.43 · **Origen:** T-2.58 §2.6
- **Defecto:** la consola de nube tiene vista de evidencia desde T-2.43; el panel del gabinete
  —lo único que queda **cuando no hay nube**, que es cuando importa— no.
- **Criterios de aceptación:**
  - [x] El panel lista la evidencia y el estado del backfill. **Siete desenlaces, no tres**: la
        ficha pedía pendiente/subido/fallido, pero se midió que había desenlaces que compartían
        el único bit observable («el `.json` está o no está»). El que más duele es el **DESCARTE
        POR RING VACÍO**, que borra el fichero **igual que un éxito** y perdía la evidencia en
        silencio. T-2.67 no lo repara —eso es otra tarea—: lo cuenta y lo llama `EVIDENCIA
        PERDIDA` en rojo.
  - [x] Sin waveform crudo: la vista es de **estado**. Regla de oro 9 intacta.
  - [x] Estados explícitos, y `status()` **no toca disco**: instantánea en memoria con reemplazo
        atómico, sembrada leyendo el directorio **al construir** y re-verificada al cerrar cada
        pasada. Medido por auditoría: **cero accesos a disco/red en 200 llamadas
        instrumentadas**. Un contador que arrancara en cero con el directorio lleno habría sido
        la misma mentira que esta fase persigue.
- **Campo `durable` añadido (no estaba en la ficha):** declara que sin `cloud_spool_dir` el
  pendiente vive en un directorio que **no sobrevive al reinicio**. Se DECLARA, no se arregla:
  cambiar la ruta por defecto movería el sitio donde el Pi busca sus evidencias. Ver `T-2.67.b`.
- **Hallazgo en el gabinete VIVO:** con sus datos reales la card pinta **«18 ATASCADAS DESDE
  HACE 15.3 d · FALLO DE EXTRACCIÓN · SE REINTENTA SIN PROGRESAR»**. La causa raíz es de
  `RingBuffer.extract_window`, no del panel que la delata. Ver `T-2.67.c`.

### [x] T-2.68 · `RELÉS · S/D` deja de colapsar tres causas — `SOFTWARE` · COMPLETA (2026-08-06)
- **Componente:** edge (panel + gpio) · **Depende de:** — · **Origen:** T-2.58 §2.7
- **Defecto:** `RELÉS · S/D · arranque en frío` significa hoy tres cosas distintas, y la
  reacción correcta del operador es distinta en cada una. Un solo rótulo para tres causas es
  un rótulo que no informa.
- **Criterios de aceptación:**
  - [x] Las causas se distinguen, cada una con su acción. **Corrección de fondo al enunciado:
        `arranque en frío` NO era una de las tres causas — era un rótulo que nombraba un estado
        que el gabinete NUNCA alcanza.** La ventana es de longitud cero: `gpio` es el índice 0
        del toposort y puebla sus 5 canales de forma síncrona bajo lock. El literal se **borró**
        del panel en vez de conservarse por simetría. Las causas reales son seis:
        `gpio_stopped` (módulo detenido — camino **sin excepción**, solo `running` lo delata),
        `gpio_error` (avería EN CALIENTE del proceso que toca la sirena), `config_error`
        (`ConfigStore` ilegible, que hasta hoy **se disfrazaba de gpio roto** porque el `try` era
        uno solo sobre dos módulos), `no_actuators_installed` (los cinco declarados `false`: la
        única lista vacía legítima, en ámbar), `partial` (el perfil declara relés que gpio no
        reporta — **la lista CORTA mentía igual que la vacía** y nada la disparaba) y `unknown`.
  - [x] **No toca el camino SASMEX→relé.** Diagnóstico puro sobre memoria ya viva: cero disco,
        cero red.
  - [x] Test por causa, más el cuarto caso: **`unknown` es el DEFAULT**. Sin explicación se
        asume la peor causa y se pinta ROJO, jamás una espera benigna. Un `relays_status`
        **ausente** (servidor viejo) y una razón que el panel no conoce también caen ahí.

**DoD de la Fase 2.4 — CUMPLIDO (2026-08-06):** los cuatro `[ ]` de T-2.58 cerrados con
evidencia; **el edge no ganó ni un topic nuevo**; ninguna de las cuatro tocó el camino
SASMEX→relé. Suites: edge **598 → 749**, api **1208 → 1345**, web **1130 → 1170**.

### [ ] T-2.66.b · El catálogo SSN no tiene quién lo actualice — `DECISIÓN` + `SOFTWARE`
- **Componente:** api · **Origen:** reconocimiento de T-2.66 · **Depende de:** decisión de producto
- **El hecho, medido:** `push_catalog` (`api/src/takab_api/routers/commands.py`) recibe el
  catálogo **en el cuerpo de la petición**, y su propio docstring promete que la periodicidad
  «es una llamada programada a este endpoint» — **que no existe**. Y no puede existir todavía:
  `grep` de `ssn.unam.mx` y `rss` sobre todo el repo devuelve **cero**. Nada en ninguna capa
  obtiene el catálogo del SSN; el snapshot vivo del Pi lo armó alguien **a mano**. Tampoco hay
  dónde guardarlo: en `db/schema.sql` solo existen `seismic_events`, `gateway_catalog_state`
  (espejo POR GABINETE de lo ya enviado) y `reference_earthquakes` (los 13 históricos del seed).
- **Por eso no es código pendiente sino una decisión:** un job periódico exige antes un
  **ingestor del SSN** (egress de red a un tercero, parseo de un feed cuyo formato no
  controlamos, y **aviso legal de uso de datos del SSN**) más una tabla de instantánea vigente.
- **Criterios de aceptación:**
  - [ ] **DECIDIR** si TAKAB ingiere el feed del SSN, con qué acuerdo y bajo qué atribución.
  - [ ] Si sí: ingestor + tabla de instantánea vigente + job, con la huella `catalog_published`
        distinguiendo **«republiqué lo mismo» de «llegó catálogo nuevo»** (hoy no lo distingue,
        así que un job periódico llenaría la bitácora de ruido).
  - [ ] Si no: el docstring deja de prometer una periodicidad que nadie va a construir.

### [ ] T-2.67.b · La cola «durable» del edge no sobrevive a un reinicio — `SOFTWARE`
- **Componente:** edge + aprovisionamiento · **Origen:** auditoría del bloqueante de T-2.67
- **El hecho, medido:** `provision_gateway.sh` **no escribe `TAKAB_EDGE_CLOUD_SPOOL_DIR`**, así
  que en el Pi real `cloud_spool_dir=""` y `_tmp_spool()` hace **`mkdtemp` nuevo en cada
  arranque**. La cola «durable» de `CloudConnector` **se pierde entera al reiniciar**. Roza la
  **regla de oro 3** (nada se pierde ni se duplica al reconectar) y es peor que el caso de la
  evidencia, que al menos ya lo declara con `durable:false`.
- **Agravante:** `_default_pending_dir()` cae a `/tmp/backfill-pending`, **compartido entre
  procesos y corridas**. Si el directorio no existe al arrancar, cualquier usuario puede crearlo
  primero y quedarse de dueño; el `mkdir(exist_ok=True)` del servicio lo acepta.
- **Criterios de aceptación:**
  - [ ] Ruta durable por defecto, escrita por el aprovisionamiento, con permisos propios.
  - [ ] **Migración de los pendientes existentes** del Pi vivo — cambiar la ruta sin moverlos
        abandonaría evidencia real.
  - [ ] Test que demuestre que la cola sobrevive a un reinicio del proceso.

### [ ] T-2.67.c · 18 evidencias atascadas: la extracción no progresa — `SOFTWARE`
- **Componente:** edge · **Origen:** la card de T-2.67 contra el gabinete VIVO
- **El hecho:** el Pi lleva **18 evidencias pendientes desde hace 15.3 días** con
  `FALLO DE EXTRACCIÓN · SE REINTENTA SIN PROGRESAR`. Son ventanas de sismos reales que nunca
  subieron. La causa raíz está en `RingBuffer.extract_window`
  (`edge/takab_edge/buffer/__init__.py`): hace `merge(method=1)` **sin `fill_value`** y luego
  `write(MSEED)`; con huecos, ObsPy produce salida vacía o falla, y el **descarte por ring
  vacío borra el fichero igual que un éxito**.
- **Criterios de aceptación:**
  - [ ] La extracción con huecos produce evidencia utilizable, o falla **declarándolo**.
  - [ ] **Un descarte deja de borrar la evidencia en silencio** (decisión de producto: ¿se
        conserva la ventana parcial, se marca, se reintenta?).
  - [ ] Las 18 del gabinete vivo, resueltas o explicadas una a una.
  - [ ] Test con ring con huecos que hoy reproduce el atasco.

---

## BLOQUE II · Funciones finales — `SOFTWARE`

> **No espera a ningún gate** (regla de ordenación) y **puede empezar el día 1**. Dos cosas
> que sí hay que tener escritas, porque no se deducen de ninguna ficha de tarea:
>
> 1. **`T-2.84` (matriz requisito→test) depende de las Fases 2.3–2.8**, y las Fases 2.3 y 2.4
>    son del **Bloque I**. Es el único cruce Bloque II → Bloque I y es intencional: una matriz
>    escrita antes de que existan los tests que cita documenta intenciones, no cobertura. Se
>    declaró por rango de fases y no por lista de tareas, así que **no aparece en ninguna
>    línea `Depende de: T-…`**: hasta el 2026-08-05 el cruce era invisible para el test que
>    los vigila.
> 2. **Este bloque está en la ruta crítica**, aunque el carril de gates sea el que se agenda
>    primero: `T-2.74` y la cascada `T-2.75`→`T-2.78` son suyos, y `T-2.94` (Bloque III)
>    espera a `T-2.78`. Ver "RUTA CRÍTICA" al final del archivo. Nada de esto significa que
>    el Bloque II espere a un gate: **no espera a ninguno**; es al revés.

## Fase 2.5 · Operación de flota

Hoy actualizar un gabinete es **`ssh` + `deploy.sh` a mano**. Con un gabinete es incómodo; con
veinte es imposible; con veinte y una regresión, es peligroso.

### [ ] T-2.69 · Inventario de versiones de flota — `SOFTWARE`
- **Componente:** api + web · **Depende de:** —
- **Criterios de aceptación:**
  - [ ] La consola dice **qué versión corre cada gabinete**, con edad del dato.
  - [ ] Se ve la deriva: cuántos gabinetes están atrás y cuánto.
  - [ ] `S/D` cuando no se sabe — nunca la última versión conocida pintada como actual.

### [ ] T-2.70 · Actualización remota con canary y rollback — `SOFTWARE`
- **Componente:** api + edge + deploy · **Depende de:** T-2.69
- **Criterios de aceptación:**
  - [ ] **`takab-gpio` NO se detiene durante la actualización.** Es el proceso que toca la
        sirena (regla de oro 4); una ventana de actualización no puede ser una ventana de
        desprotección.
  - [ ] Canary: primero uno, se observa, luego el resto. Un despliegue a toda la flota a la
        vez es un incidente a toda la flota a la vez.
  - [ ] **Rollback automático** ante fallo, con criterio medible de fallo (no "parece mal").
  - [ ] Comando firmado + nonce + ack (regla de oro 8).
  - [ ] Test: actualización que falla ⇒ el gabinete vuelve solo a la versión anterior.

### [ ] T-2.71 · Ventanas de mantenimiento — `SOFTWARE`
- **Componente:** api + web + edge · **Depende de:** T-2.70
- **Criterios de aceptación:**
  - [ ] Una ventana de mantenimiento **silencia alarmas de operación, jamás la actuación**.
  - [ ] La consola lo dice en pantalla mientras dure; nadie debe deducirlo.
  - [ ] Vencimiento automático: una ventana que se olvida abierta es una alarma apagada para
        siempre.

## Fase 2.6 · Backup y DR

`RUNBOOK-backup-restore-db.md:3` dice literalmente **"RESTORE JAMÁS PROBADO (gate G-09)"** y
el RTO no está medido. Mientras eso siga así, **el respaldo es una hipótesis**, no un respaldo.

### [ ] T-2.72 · PITR/WAL-G en IaC — `SOFTWARE`
- **Componente:** infra · **Depende de:** —
- **Criterios de aceptación:**
  - [ ] WAL archiving continuo declarado en Terraform (no a mano en la instancia).
  - [ ] RPO objetivo declarado y **derivable de la configuración**, no de una promesa.
  - [ ] Alarma si el archivado se atasca — extensión natural del módulo `observability`
        (`RUNBOOK-backup-restore-db.md:120`).
  - [ ] `terraform fmt/validate` verde. El `apply` es **`HUMANO-AWS`** y va en T-2.74.

### [ ] T-2.73 · Script de restore ensayable que mide su propio RTO — `SOFTWARE`
- **Componente:** db + deploy · **Depende de:** T-2.72
- **Criterios de aceptación:**
  - [ ] Un solo comando restaura a una instancia limpia y **imprime el RTO medido**.
  - [ ] Verifica la integridad de lo restaurado (no solo que el proceso terminó en 0).
  - [ ] Ensayable **contra la DB local**, para que el ensayo no dependa de la ventana AWS.
  - [ ] Guardia anti-restore-sobre-producción, del mismo estilo que
        `demo/run.py::_assert_exclusive_db`.

### [ ] T-2.74 · `G-09` · restore real, RTO medido y publicado — `HUMANO-AWS`
- **Componente:** operación · **Depende de:** T-2.73 · **Cubre `G-09`.**
- **Vive fuera del carril de gates a propósito:** es el único de los diez que **no exige manos
  en el gabinete** — se acredita con una ventana AWS sobre software que sí controlamos
  (`T-2.72`/`T-2.73`). Está anotado en la nota de la Fase 2.11 para que quien busque los diez
  gates ahí lo encuentre.
- **Criterios de aceptación:**
  - [ ] Procedimientos **A y B** ejecutados de verdad contra el entorno real.
  - [ ] RPO/RTO **medidos** y escritos en el §6 del runbook de backup.
  - [ ] `G-09` marcado en la tabla de gates de `RUNBOOK-auditoria-cierre.md`.

## Fase 2.7 · Canales reales de notificación

### [ ] T-2.75 · Un canal simulado deja de mentir — `SOFTWARE`
- **Componente:** api · **Depende de:** —
- **La más importante y la más barata de toda la ruta.** Hoy
  `api/src/takab_api/notify/providers.py:134-135` registra `SimulatedProvider("whatsapp")` y
  `SimulatedProvider("sms")`, y el simulado **marca los jobs `sent` sin enviar nada**. El
  canal email ya aprendió la lección por las malas —el 13/07 hubo correos "enviados" que nadie
  recibió, y por eso hoy grita al arrancar (`:124-131`)— pero **SMS y WhatsApp siguen
  callando**. Un tablero que dice "notificado" cuando no se notificó a nadie es peor que uno
  que no dice nada.
- **Criterios de aceptación:**
  - [ ] Un canal simulado **no puede marcar `sent`**: marca `simulated` y se ve como tal en la
        consola y en `incident_actions`.
  - [ ] En producción, un canal simulado **grita** al arrancar, como ya hace email.
  - [ ] Test: job por canal simulado ⇒ jamás aparece como entregado.

### [ ] T-2.76 · SMS real — `SOFTWARE` (+ `HUMANO-AWS` para credenciales)
- **Componente:** api + infra · **Depende de:** T-2.75
- **Criterios de aceptación:**
  - [ ] Proveedor real detrás de la misma interfaz `NotifyProvider`; el orquestador no cambia.
  - [ ] Reintentos, coste por mensaje y límite de tasa **declarados**, no descubiertos en la
        factura.
  - [ ] Evidencia de entrega en `incident_actions` con latencia y `deadline_met`, como el resto.
  - [ ] Sin secretos en git (regla de oro 6).

### [ ] T-2.77 · WhatsApp Business — `SOFTWARE` (+ `LEGAL`/`HUMANO-AWS` para el alta)
- **Componente:** api · **Depende de:** T-2.75
- **Criterios de aceptación:**
  - [ ] Plantillas aprobadas y versionadas en el repo (WhatsApp no deja improvisar texto).
  - [ ] Degradación explícita si la plantilla es rechazada: **el canal cae, no finge**.
  - [ ] Evidencia de entrega igual que los demás canales.

### [ ] T-2.78 · SES fuera de sandbox + cadena on-call acreditada — `HUMANO-AWS`
- **Componente:** infra + operación · **Depende de:** T-2.76, T-2.77
- **Criterios de aceptación:**
  - [ ] SES fuera de sandbox con DKIM/SPF de dominio real.
  - [ ] **Acreditar la cadena on-call de punta a punta**: provocar una alarma real y que
        alguien reciba el aviso, cronometrado. A-4 dejó el topic SNS aplicado y confirmado
        (2026-07-13/14); esto acredita que **la persona** llega, no solo el mensaje.
  - [ ] Escalamiento escrito: quién es el segundo si el primero no acusa.

## Fase 2.8 · Compliance como producto

El motor es `SOFTWARE`; **el texto legal es `LEGAL`**. No se bloquean entre sí: se construye
el motor con un texto provisional versionado y se sustituye el texto cuando llegue.

### [ ] T-2.79 · Aviso de privacidad versionado + consentimiento — `SOFTWARE` (texto: `LEGAL`)
- **Componente:** api + web + mobile · **Depende de:** —
- **Criterios de aceptación:**
  - [ ] El aviso es un **objeto versionado**; el consentimiento guarda **qué versión** aceptó
        cada usuario y cuándo.
  - [ ] Cambiar el aviso **no reescribe** consentimientos anteriores.
  - [ ] Registro append-only del consentimiento.

### [ ] T-2.80 · ARCO por anonimización con tombstone — `SOFTWARE`
- **Componente:** api + db · **Depende de:** T-2.79
- **Criterios de aceptación:**
  - [ ] **Jamás `DELETE`.** Anonimización + `tombstone`: el derecho ARCO se ejerce sin borrar
        una fila de auditoría, evidencia ni dictamen — **regla de oro 11**, que es restricción
        dura, no preferencia.
  - [ ] Un check-in de vida anonimizado sigue contando para el histórico del incidente.
  - [ ] Test: tras ejercer ARCO, el `audit_log` del incidente sigue íntegro y verificable.

### [ ] T-2.81 · Retención de PII con la excepción de compliance en el job — `SOFTWARE`
- **Componente:** api (job) + db · **Depende de:** T-2.80
- **Criterios de aceptación:**
  - [ ] La excepción de compliance está **codificada en el job**, no escrita en un comentario.
        Un comentario no impide que un `DELETE` mal escrito pode evidencia.
  - [ ] Test: el job intenta podar una tabla protegida ⇒ **falla ruidosamente**.
  - [ ] Simulacro (`dry-run`) obligatorio con conteos antes de podar nada.

### [ ] T-2.82 · Carga de `compliance_labels` por tenant — `SOFTWARE`
- **Componente:** api + web · **Depende de:** T-2.81
- **Criterios de aceptación:**
  - [ ] La tabla existe desde el schema (`db/schema.sql:1204`) y **nadie la carga**. Alta y
        edición por tenant desde la consola, auditada.
  - [ ] Las etiquetas se ven donde importan (dictamen, evidencia), no solo en un formulario.

### [ ] T-2.83 · Residencia de datos: evaluar región MX — `DECISIÓN` (+ `LEGAL`)
- **Componente:** infra + docs · **Depende de:** —
- **Criterios de aceptación:**
  - [ ] Documento con coste, latencia y servicios disponibles en la región MX **medidos**, no
        supuestos.
  - [ ] Recomendación explícita y su razón; si es "no migrar", queda escrito por qué, para que
        el primer cliente que pregunte tenga respuesta.

## Fase 2.9 · Trazabilidad y paquete de entrega

Va **después** de 2.3–2.8 porque **documenta lo que esas fases producen**. Escribirla antes
sería documentar intenciones.

### [ ] T-2.84 · Matriz requisito→test — `SOFTWARE`
- **Componente:** docs + tests · **Depende de:** Fases 2.3–2.8
- **Criterios de aceptación:**
  - [ ] Cada requisito enlaza al test que lo demuestra, con `archivo:línea`.
  - [ ] **Los huecos se marcan `SIN COBERTURA` explícitamente.** Una matriz sin huecos es una
        matriz que miente: el valor está justo en los huecos.
  - [ ] Un test mantiene la matriz honesta (si el test citado desaparece, la matriz rompe).

### [ ] T-2.85 · Manual de operación de cliente — `SOFTWARE`
- **Componente:** docs · **Depende de:** T-2.84
- **Criterios de aceptación:**
  - [ ] Escrito para un operador, no para un desarrollador.
  - [ ] Qué hacer **cuando cae la nube** (regla de oro 2 explicada en lenguaje de operación).
  - [ ] Qué significa cada estado del panel del gabinete y qué acción pide.

### [ ] T-2.86 · Documento de entrega y aceptación — `SOFTWARE` (firma: `LEGAL`)
- **Componente:** docs · **Depende de:** T-2.85
- **Criterios de aceptación:**
  - [ ] Dice **qué hace y qué NO hace** el sistema, con la misma claridad las dos cosas.
  - [ ] Incluye la sección de **invariantes** (abajo) como parte del alcance contratado.
  - [ ] Enlaza la matriz de T-2.84, huecos incluidos.

---

## BLOQUE III · Carril de gates (paralelo, dueño Mauricio)

> Este bloque corre **desde el día 1** y **el Bloque II no lo espera a él**. Al revés hay
> **una sola excepción declarada**: `T-2.94` (`G-06`, `G-08`) depende de `T-2.78` porque un
> simulacro con **cascada de notificación real** no se puede acreditar con canales simulados.
> Todo lo demás de este bloque depende, como mucho, de otra tarea de este mismo bloque:
> `T-2.92` y `T-2.93` —las dos sesiones que deciden si el producto es real— no esperan a nada.
> Ver la excepción 2 de la regla de ordenación.

## Fase 2.10 · Ventana AWS

### [ ] T-2.87 · Apply de Cognito — `HUMANO-AWS`
- **Componente:** infra + deploy · **Depende de:** T-2.54 · **Origen:** T-2.57, pendiente 1
- **Por qué importa:** sin `TAKAB_API_COGNITO_USER_POOL_ID` cableado en `deploy.sh` y sin
  permisos `cognito-idp:Admin*` en el rol de instancia, la **gestión de usuarios de T-2.54
  corre SIMULADA en producción**. Grita en cada escritura, no finge — pero sigue sin crear
  usuarios de verdad.
- **Criterios de aceptación:**
  - [ ] Variable cableada + permisos aplicados.
  - [ ] Crear un usuario real desde la consola y verlo en el pool.
  - [ ] El aviso de "modo simulado" **desaparece** del arranque.

### [ ] T-2.88 · Rol CI OIDC endurecido (= `T-1.44`) — `HUMANO-AWS`
- **Componente:** infra · **Depende de:** — · **Cierra T-1.44.**
- **Criterios de aceptación:**
  - [ ] `terraform apply` del rol endurecido; el job plan-only del CI cableado.
  - [ ] `T-1.44` pasa de `[~]` a `[x]` **con la cabecera de este archivo actualizada** en el
        mismo commit (ver "Conteo de tareas").

### [ ] T-2.89 · Encender `console_scope_enforced` — `HUMANO-AWS`
- **Componente:** api + operación · **Depende de:** T-2.54
- **Es la única brecha multi-tenant viva en producción.** `api/src/takab_api/settings.py:212`
  lo tiene en `False`.
- **SECUENCIA OBLIGADA** (invertirla deja a cada `soc_operator` con **cero estaciones**, que
  es una caída de servicio autoinfligida):
  1. recorrer los `scope_gap` del `audit_log` — dicen exactamente quién quedaría fuera;
  2. asignar alcance por usuario;
  3. **entonces** encender.
- **Criterios de aceptación:**
  - [ ] Cero `scope_gap` nuevos durante 24 h antes de encender.
  - [ ] Encendido con verificación por rol contra el pool real.
  - [ ] Test cross-tenant contra el entorno desplegado: un tenant no ve al otro.

### [ ] T-2.90 · e2e contra el entorno desplegado — `HUMANO-AWS`
- **Componente:** web/e2e · **Depende de:** T-2.87 · **Origen:** T-2.57, pendiente 3
- **Criterios de aceptación:**
  - [ ] `deployed.spec.ts` corrido **contra producción**, no contra localhost (hoy se salta a
        propósito ahí: son los 3 `skipped` de T-2.59).
  - [ ] Resultado registrado con fecha y commit desplegado.

### [ ] T-2.91 · Sembrar un occupant real — `HUMANO-AWS`
- **Componente:** operación + mobile · **Depende de:** T-2.87
- **Criterios de aceptación:**
  - [ ] Un `occupant` real, con **código de enrolamiento acotado a su sitio** (no lleva
        `site_scope` por claim: se enrola).
  - [ ] Login desde la app real y check-in de vida completado.

## Fase 2.11 · Gates físicos `G-01`…`G-10` — `FÍSICO`

> Agrupados por **sesión de trabajo en sitio**, no por número, para que cada viaje al gabinete
> cierre varios gates.
>
> **`G-09` no está en esta fase.** Lo cierra `T-2.74` (Fase 2.6, `HUMANO-AWS`): un restore
> real con RTO medido es una **ventana AWS sobre software que sí controlamos**, no una sesión
> con manos en el gabinete. Queda escrito aquí porque este es el sitio donde alguien va a
> buscar los diez, y un gate que no aparece donde se busca es un gate que se olvida.

### [ ] T-2.92 · Sesión de vida — `FÍSICO`
- **Componente:** edge (hardware) · **Depende de:** — · **Cubre `G-01`, `G-02`, `G-04`.**
- **Es la tarea que decide si el producto es real.**
  - **`G-01` · restart en frío:** `sudo reboot` con el gabinete armado; `takab-edge` y
    `takab-gpio` activos, backend `lgpio` verificado en el journal, relés respondiendo, sin
    caída a sysfs.
  - **`G-02` · sirena con el Pi APAGADO** (§6 de `RUNBOOK-SPOF-02`). **La mitigación más
    importante del sistema:** si la sirena solo suena cuando el Pi vive, todo el diseño
    determinista depende de un solo aparato encendido.
  - **`G-04` · radio WR-1 real:** semántica pulso/sostenido documentada contra transmisión
    real de CIRES, latching correcto, y **latencia contacto→relé→sirena < 100 ms medida**.
    Los relés siguen en **MOCK** y **este gate lleva abierto desde el hito de Fase 1**.
- **Criterios de aceptación:**
  - [ ] Los tres gates marcados en la tabla de `RUNBOOK-auditoria-cierre.md` con evidencia.
  - [ ] `T-1.42` (semántica real del WR-1) pasa de `[~]` a `[x]`, con la cabecera actualizada.

### [ ] T-2.93 · Sesión instrumental — `FÍSICO`
- **Componente:** edge (hardware) · **Depende de:** — · **Cubre `G-03`, `G-05`, `G-07`, `G-10`.**
- **Criterios de aceptación:**
  - [ ] `G-03`: soak 24 h de SeedLink + power-cycle del Shake ⇒ cero huecos no recuperados
        (resume por `seqnum`, no por tiempo).
  - [ ] `G-05`: publish desde el SOC ⇒ `config-state: in_sync: true` con fingerprint, y
        rollback verificado.
  - [ ] `G-07`: replay de un comando capturado ⇒ rechazo por nonce visto + auditoría del
        rechazo.
  - [ ] `G-10`: panel LAN en el Pi real — GET 200 público en LAN, POST 401 sin PIN / 200 con
        PIN, lockout 5/60 s, y MFA TOTP exigido por rol contra el pool real.

### [ ] T-2.94 · Sesión de sitio — `FÍSICO`
- **Componente:** operación · **Depende de:** T-2.78 · **Cubre `G-06`, `G-08`.**
- **Criterios de aceptación:**
  - [ ] `G-06`: simulacro E2E en sitio real con **cascada de notificación real** ⇒ incidente
        en el SOC dentro del SLO, notificación entregada, miniSEED backfilled descargable.
  - [ ] `G-08`: load-test a la escala objetivo de flota comercial con los SLOs p95 del
        blueprint sostenidos.

### [ ] T-2.95 · `GATE-HW` móvil + voceo — `FÍSICO`
- **Componente:** mobile + edge (audio) · **Depende de:** T-2.91
- **Criterios de aceptación:**
  - [ ] E2E móvil en **device real** (el entorno ya está preparado y verde; falta el device).
  - [ ] Voceo: DAC/ampli/bocina montados, los dos mensajes reales grabados,
        `TAKAB_EDGE_AUDIO_ENABLED=true` en el gabinete y **prueba audible presencial**.
  - [ ] El mensaje de sismo y el de simulacro son distinguibles a oído, no solo por `sha256`.

## Fase 2.12 · Legal, tienda y comercial

### [ ] T-2.96 · `GATE-LEGAL` · marco normativo citable — `LEGAL`
- **Componente:** docs · **Depende de:** —
- **Bloquea material comercial.** La cita antigua "NOM-003-SCT" era una norma de **transporte**
  (etiquetado de materiales peligrosos) y **no aplicaba**; FASE-0 ya la había descartado y la
  edición anterior de RBAC la daba por confirmada de forma circular. La regla operativa
  —auditoría, evidencia y dictámenes inmutables, jamás podados— es **requisito propio de
  TAKAB** y no cambia; lo que falta es el marco **citable**.
- **Criterios de aceptación:**
  - [ ] Marco normativo citable definido con abogado/cliente y escrito en blueprint §9.
  - [ ] `RBAC-TAKAB.md §8` punto 3 y `ANALISIS` pregunta abierta #1 actualizados a la vez.

### [ ] T-2.97 · `GATE-STORE` · APNs/FCM reales + tono SASMEX — `LEGAL` + `HUMANO-AWS`
- **Componente:** mobile + infra · **Depende de:** —
- **Criterios de aceptación:**
  - [ ] Credenciales APNs/FCM reales; `TAKAB_API_PUSH_*_APPLICATION_ARN` aplicado.
  - [ ] **Tono SASMEX licenciado con CIRES.** Usar el tono sin licencia no es un detalle
        estético: es el sonido que la población ya asocia a evacuar.
  - [ ] Push real recibido en device real, con el tono correcto.

### [ ] T-2.98 · Entitlement Critical Alerts de Apple — `LEGAL`
- **Componente:** mobile · **Depende de:** T-2.97
- **Criterios de aceptación:**
  - [ ] Solicitud presentada con la justificación de uso (alertamiento sísmico).
  - [ ] Si Apple lo niega, **queda escrita la degradación**: qué recibe el ocupante con el
        teléfono en silencio y qué no. Un "no" sin plan es un ocupante que no se entera.

---

## BLOQUE IV · Funciones futuras

> **No empieza antes de que el Bloque II esté cerrado y `G-04` acreditado.** La razón no es
> de agenda: **no se le añaden funciones a un sistema cuya cadena de vida todavía no se midió
> en hardware real.**
>
> Esta es la **excepción 1** de la regla de ordenación ("Cómo se lee esta ruta"), y está
> escrita también allá arriba: la primera edición de la ruta eximía a este bloque de esperar
> gates y se contradecía con este mismo párrafo.

## Fase 3.0 · IA en shadow-mode

Única fase futura ya nombrada en la documentación existente (decision-gate #9). El andamiaje
**ya está construido y apagado** en `api/src/takab_api/narrative/`: `Narrative`
(`narrative/base.py:74-90`) **no tiene campo donde poner un veredicto**, y un contract-test
(`api/tests/narrative/test_contract.py`) lo verifica **sobre los nombres de los campos**.
Añadir uno rompería el build antes de que pudiera llegar a un dictamen: eso es garantía **de
tipos**, no de documentación.

**Política inamovible de toda la fase: la IA jamás suprime disparos (regla de oro 1).**

### [ ] T-3.01 · Shadow-mode con registro de procedencia — `SOFTWARE`
- [ ] La IA opina en paralelo y **nada de lo que dice llega a un actuador**.
- [ ] Procedencia completa en `audit_log` (verbo `narrative_generated`): modelo, latencia,
      tokens, coste, y motivo de degradación si cayó al proveedor determinista.

### [ ] T-3.02 · Métricas de acuerdo/desacuerdo contra el determinista — `SOFTWARE`
- [ ] Se mide cuántas veces la IA habría diferido del motor determinista, y en qué dirección.
- [ ] El desacuerdo se **muestra**, no se resuelve automáticamente.

### [ ] T-3.03 · Redacción y fuga de datos — `SOFTWARE`
- [ ] Ningún dato de tenant sale sin pasar por `redact`; test de fuga cross-tenant.
- [ ] Coste por incidente acotado y visible.

### [ ] T-3.04 · Priorización asesora en el SOC — `SOFTWARE`
- [ ] La IA **ordena** una lista; no cambia severidades ni cierra incidentes.
- [ ] El operador ve siempre el orden determinista debajo.

### [ ] T-3.05 · Evaluación con incidentes históricos — `SOFTWARE`
- [ ] Corrida contra el histórico real con resultados publicados.
- [ ] **Criterio de salida escrito**: qué tendría que ocurrir para que la IA dejara el
      shadow-mode, y qué **nunca** la sacará de él (la ruta de disparo).

## Fase 3.1 · Ingeniería estructural areal

> **PRECONDICIÓN DURA.** `BLUEPRINT §14` y `CLAUDE.md §8` prohíben el mini-ShakeMap
> *"en este ciclo"*. Abrir esta fase exige **derogar explícitamente esa viñeta —la del
> mini-ShakeMap, `[DIFERIDO · mini-ShakeMap]`— y ninguna otra**, y esa derogación es el
> **primer criterio de T-3.09**. No se empieza por el código.
>
> **La viñeta vecina no se toca.** El *streaming continuo de waveform crudo* comparte
> párrafo con el mini-ShakeMap en `CLAUDE.md §8` y viñeta contigua en `BLUEPRINT §14`, pero
> es **INVARIANTE** (regla de oro 9), no diferido: ninguna tarea de esta fase lo deroga. El
> mapa se construye **de features**, no de forma de onda en vivo.

### [ ] T-3.06 · MMI instrumental — `SOFTWARE`
- [ ] Intensidad derivada de la medición, con su incertidumbre a la vista.
- [ ] Nunca sustituye al dictamen firmado por un inspector.

### [ ] T-3.07 · Sa (aceleración espectral) — `SOFTWARE`
- [ ] Periodos declarados y justificados; validado contra registros conocidos.

### [ ] T-3.08 · Deriva de entrepiso — `SOFTWARE`
- [ ] **Exige ≥ 2 sensores por edificio.** Con uno solo el número es una invención — y es
      exactamente el tipo de cifra que decide si un edificio se reocupa.
- [ ] Si el sitio no tiene dos sensores, la vista dice `SIN COBERTURA`, no un número.

### [ ] T-3.09 · Mini-ShakeMap — `SOFTWARE` + `DECISIÓN`
- [ ] **Primer criterio: derogar explícitamente la viñeta `[DIFERIDO · mini-ShakeMap]`** de
      `BLUEPRINT §14` y su mención en `CLAUDE.md §8` —**esa viñeta y ninguna otra**— en el
      mismo commit y con la razón escrita. Sin eso, esta tarea está prohibida por los
      documentos canónicos.
- [ ] **Lo que este criterio NO deroga.** Las otras cinco viñetas de `BLUEPRINT §14` están
      marcadas `[INVARIANTE · …]` (T-MINUS, magnitud preliminar, streaming crudo continuo, IA
      en la ruta de disparo, tocar el Shake OS) y son **prohibiciones, no diferidos** — ver la
      sección INVARIANTES al final de este archivo. Derogar "la §14" entera tumbaría las
      reglas de oro 1 y 9 para poder pintar un mapa. **El bullet de `CLAUDE.md §8` mezcla
      mini-ShakeMap y streaming crudo en una sola línea: hay que partirlo, no borrarlo.**
- [ ] Arquitectura escrita **antes** del código.
- [ ] La regla de oro 9 (sin streaming continuo de waveform crudo) sigue en pie: el mapa se
      construye de features, no de forma de onda en vivo.

## Fase 3.2 · CCTV ONVIF real + conteo de aforo

Requisito **nuevo de Mauricio (2026-07-10)** que **no está en el blueprint**. Toca privacidad
(**video = PII**) y **compite por CPU con el reflejo GPIO**, que es el proceso que toca la
sirena.

> **Si no cabe en el Pi 4, la respuesta correcta es hardware separado — nunca optimizar el
> proceso que toca la sirena** (regla de oro 4).

### [ ] T-3.10 · Escribir la arquitectura en el blueprint — `SOFTWARE` + `DECISIÓN`
- [ ] Sección nueva del blueprint: topología, dónde vive el proceso, y **presupuesto de CPU**.
- [ ] Tratamiento de PII de video: retención, acceso por rol, y su encaje con la Fase 2.8.
- [ ] Decisión escrita: mismo Pi o hardware separado, con la medición que la sostiene.

### [ ] T-3.11 · Cliente ONVIF — `SOFTWARE`
- [ ] Proceso **separado**, con límite de CPU explícito, que no puede degradar `takab-gpio`.
- [ ] Falla del cliente ONVIF ⇒ el resto del gabinete no se entera.

### [ ] T-3.12 · Aforo + cruce con el check-in móvil — `SOFTWARE`
- [ ] El aforo por cámara y el check-in de vida se **cruzan**, no se suman: son dos
      estimaciones distintas de la misma cosa y la diferencia es la información útil.
- [ ] La discrepancia se muestra como discrepancia, nunca promediada en un número único.

## Fase 3.3 · Feeds y superficie de datos

### [ ] T-3.13 · Feed CIRES/SSN en vivo — `SOFTWARE` (soft-gate)
- [ ] Enriquece; **jamás gatea** el camino SASMEX (decision-gate #8: "lo mejora, no lo
      bloquea").
- [ ] Caída del feed ⇒ degradación visible, no silenciosa.

### [ ] T-3.14 · Duración instrumental de la sacudida — `SOFTWARE`
- [ ] Medida, no estimada; con su definición escrita.

### [ ] T-3.15 · GraphQL subscriptions — `SOFTWARE` · **solo si un cliente lo pide**
- [ ] El gate #5 se ratificó el 2026-07-06 a favor de REST + WS nativo (`T-1.22`). Esta tarea
      **no lo reabre**: lo añade **encima**, sin tocar el edge, y solo con demanda real.
- [ ] Si nadie lo pide, esta tarea se cierra como `NO SE HACE` con esa razón escrita.

### [ ] T-3.16 · Export por lote — `SOFTWARE` · **decisión vigente: NO tenerlo**
- [ ] La descarga **objeto por objeto** es lo correcto para evidencia forense: cada descarga
      deja su propia huella auditable, y un ZIP masivo la borra.
- [ ] Esta tarea existe **para que la decisión esté escrita**, no para implementarla. Cambiarla
      exige derogar esta línea con su razón.

---

## BLOQUE V · Cierre

## Fase 4.0 · Cierre del proyecto

### [ ] T-4.01 · Auditoría de cierre final — `SOFTWARE` + `FÍSICO`
- [ ] **Toda la tabla `G-01`…`G-10` marcada, o con su razón de no aplicar escrita.** Un gate
      sin marcar y sin razón es un gate que se olvidó, no un gate que se decidió.
- [ ] Los hallazgos A-*/M-* del runbook de auditoría, todos resueltos o promovidos a backlog
      vivo con dueño.

### [ ] T-4.02 · Congelamiento de contratos — `SOFTWARE`
- [ ] `shared/schemas/` versionado y etiquetado.
- [ ] `hmac_vectors.json` **congelado**: es lo que permite verificar mañana una firma de hoy.
- [ ] `db/schema.sql` etiquetado con la versión entregada.

### [ ] T-4.03 · Traspaso operativo — `SOFTWARE` + `HUMANO-AWS`
- [ ] **Mitiga el `bus factor` = 1**, que hoy es el riesgo más grande del proyecto y no
      aparece en ninguna tabla de riesgos.
- [ ] Accesos, secretos y procedimientos documentados y **probados por alguien que no los
      escribió**.

### [ ] T-4.04 · Aceptación firmada — `LEGAL`
- [ ] El documento de T-2.86 firmado por el cliente.

### [ ] T-4.05 · Backlog vivo pos-entrega — `SOFTWARE`
- [ ] Lo que queda abierto, **con dueño y fecha de revisión**.
- [ ] **No se cierra un proyecto declarando que no queda nada; se cierra declarando quién se
      hace cargo de lo que queda.**

**DoD del proyecto:** un cliente con un edificio protegido, un operador que sabe operarlo, un
respaldo que se ha restaurado de verdad, una cadena de vida medida en hardware real, y un
documento firmado que dice exactamente qué hace y qué no hace el sistema.

---

## RUTA CRÍTICA

**Hacia "producción con un cliente real", la ruta crítica es:**

```
G-04  ∧  G-02  ∧  T-2.89  ∧  T-2.96  ∧  T-2.74  ∧  notificación real (T-2.75→T-2.78)
```

- `G-04` — latencia contacto→relé→sirena medida en hardware real (`FÍSICO`)
- `G-02` — la sirena suena con el Pi apagado (`FÍSICO`)
- `T-2.89` — `console_scope_enforced` encendido (`HUMANO-AWS`)
- `T-2.96` — marco normativo citable (`LEGAL`)
- `T-2.74` — restore real con RTO medido (`HUMANO-AWS`, sobre software que sí controlamos)
- notificación real — `T-2.75` es `SOFTWARE`; `T-2.76`–`T-2.78` necesitan credenciales

**De esos seis, el software controla uno y medio.**

**Y esto es lo que hay que mirar:** el cuello de botella hacia el primer cliente **no es
capacidad de desarrollo**. `G-04` lleva abierto **desde el hito de Fase 1** mientras el
backlog de software avanzó **60 tareas**. Meter más tareas de software en la ruta crítica no
la acorta ni un día. Lo que la acorta es una tarde con el radio, el relé y un cronómetro.

**De qué bloques cuelga esta ruta.** Los seis ítems **no viven en un solo bloque**:

| Ítem | Bloque | Por qué está en la ruta |
|---|---|---|
| `G-04`, `G-02` | **III** | cadena de vida medida en hardware real |
| `T-2.89`, `T-2.96` | **III** | ventana AWS y marco legal, dueños fuera de ingeniería |
| `T-2.74` | **II** | `G-09` se cierra aquí: restore real con RTO medido |
| `T-2.75`→`T-2.78` | **II** | sin canales reales no hay notificación que acreditar |

Corolario de planificación: **el Bloque III se agenda primero en el calendario, aunque se
ejecute en paralelo** — no porque sea el único que puede retrasar el proyecto, sino porque su
plazo lo fija un dueño humano con agenda propia y no se acorta metiendo desarrolladores.

**El Bloque II también está en la ruta crítica, y por partida doble:** cuatro de los seis
ítems de arriba son suyos (`T-2.74` y la cascada `T-2.75`→`T-2.78`), y además arrastra un
gate del Bloque III — `T-2.94` (`G-06`, `G-08`) espera a `T-2.78`, que es la excepción 2 de
la regla de ordenación. Un retraso del Bloque II retrasa el proyecto por definición. Lo que
sí es exclusivo del Bloque III es el **tipo** de retraso: el suyo no se compra con capacidad
de desarrollo.

---

## INVARIANTES — prohibiciones, no diferidos

> Esto **no es el final del backlog: está fuera del backlog**. Una tarea futura que proponga
> cualquiera de estas cosas **se rechaza sin discusión**, no se prioriza. Se escriben con su
> razón para que el rechazo no parezca capricho.

1. **T-MINUS countdown y magnitud preliminar.** El WR-1 entrega **un booleano** — contacto
   seco, nada más. Un contador o una magnitud serían **cifras inventadas** en la pantalla de
   la que depende si alguien corre o se protege. En el MVP el banner dice
   `ALERTA SÍSMICA · PROTÉJASE`, sin número. Si algún día llegan datos enriquecidos de
   CIRES/SSN, será una fuente **nueva y citable**, no una interpolación nuestra.
   (`RBAC-TAKAB.md §8` puntos 1 y 2, `CLAUDE.md §8`.)
2. **IA en la ruta determinista de disparo.** La IA asesora, prioriza y filtra; **jamás veta
   ni dispara una alerta por sí sola** (regla de oro 1). La garantía es de tipos, no de
   documentación: `Narrative` no tiene campo de veredicto y un contract-test lo defiende.
3. **Streaming continuo de forma de onda cruda.** El waveform crudo (100 sps × 4 canales) no
   sube en continuo; el miniSEED crudo va a S3 **solo en eventos confirmados** (regla de oro
   9). No es una restricción de coste: es la que mantiene el enlace disponible cuando hace
   falta.
4. **Tocar el Shake OS.** El Raspberry Shake es un sensor con su propio sistema. Nuestro
   código vive en el Pi 4. Un Shake modificado es un sensor cuyo comportamiento ya no podemos
   acreditar ante nadie.
5. **UDP datacast en producción.** Solo preview/debug. La ingesta de producción es SeedLink,
   que **resume por `seqnum`** y por eso puede demostrar que no perdió un paquete. UDP no
   puede demostrar nada.
