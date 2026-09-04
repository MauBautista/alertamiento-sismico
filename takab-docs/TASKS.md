# TASKS.md — Backlog ejecutable TAKAB Ailert (Fase 1 → cierre del proyecto)

> Cómo se usa este archivo con Claude Code:
> - Ejecutamos **una tarea a la vez, en orden** (respetando `depende de`).
> - Orden de bloques = **EDGE PRIMERO, luego CLOUD, luego FRONTEND** (`BLUEPRINT-TECNICO-TAKAB.md §0.1, §13`).
> - Por cada tarea: `/write-plan` → `/goal "<acceptance>"` → `/execute-plan` dentro de `/loop`
>   hasta que TODOS los criterios pasen. Ver método en `CLAUDE.md §6`.
> - Marca `[x]` la tarea solo cuando cumpla su **Definition of Done** (`CLAUDE.md §6`).
> - Si un criterio no pasa tras 3 iteraciones del loop: detente y reporta el bloqueo.
> - Cada tarea referencia su Work Package (WP) del blueprint entre corchetes, ej. `[A2]`.

## Estado actual (2026-09-02)

****Conteo de tareas:** total **344** · `[x]` **288** · `[~]` **11** · `[ ]` **45**
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

> **Por qué el conteo de abiertas apenas se mueve, y por qué eso está bien.** El lote
> `T-2.110…T-2.116` (2026-08-10) cerró 7 y abrió 7; el lote `T-2.117…T-2.122` (2026-08-11) cerró
> 6 y abrió 5. Neto en dos días: **13 cerradas, 12 abiertas**.
>
> **No es estancamiento, y conviene no leerlo así.** Casi todas las nuevas las descubrió el propio
> trabajo **al medir cosas que antes se suponían**, y varias eran defectos vivos que nadie estaba
> contando: la deuda de cuatro estados, tres conexiones sin tope de espera, el fan-out del
> WebSocket despachando en serie, un gate de lint que cubría menos de lo que parecía. Un backlog
> que **no** crece cuando se toca código nuevo suele significar que nadie está mirando.
>
> Y el saldo real no se mide en fichas sino en lo que dejó de estar roto: en dos días se cerraron
> **cuatro superficies que mentían en verde** — el checklist de gas y puertas, la alarma del
> inmueble, la imagen de consola que no construía, y un SOC que se quedaba mudo diciendo «● LIVE».
>
> **Tercer lote (2026-08-12): 8 cerradas, 6 abiertas**, y por primera vez el neto baja (65 → 63).
> Se cerraron además **tres decisiones que llevaban semanas bloqueando software** (`PENDIENTES`
> §1.2, §1.8, §1.9), las tres con su razón escrita para poder revocarlas. Lo que se arregló de
> fondo: **la pantalla donde se firma un dictamen** ya puede declarar dato viejo en sus 8 paneles,
> **la consola arranca con la base caída** sin convertirse en puerta trasera, y **una petición
> bloqueada dejó de tumbar a las que no tocaban esa tabla**.
**Qué corre en producción se le pregunta al sistema, no a este archivo** (`/api/health` para la
nube, `FW_VERSION` para el gabinete — ver README §"¿Qué está desplegado?").

> **Lo que entró el 2026-09-02, y por qué el conteo salta 27 de golpe.** La auditoría
> V1-COMERCIAL abrió el **Bloque VI**, que ordena una ruta distinta de la de los cinco
> anteriores: no la del primer cliente, sino la de **poder enseñar el producto sin que una
> pantalla afirme lo que nadie acreditó**. Sus 27 fichas salen de 52 ítems auditados —10 verdes,
> 23 amarillos, 19 rojos— y **23 de ellas son `SOFTWARE` puro**.
>
> **El hallazgo de planificación, que merece leerse antes que la lista:** lo que hoy impide
> enseñar el producto **no está bloqueado en nadie**. La ruta crítica de V1-DEMO son cinco fichas
> y ninguna espera a un humano con agenda — al contrario que la ruta al primer cliente, donde el
> software controla uno y medio de seis. Ver
> [`INFORME-V1-COMERCIAL.md`](INFORME-V1-COMERCIAL.md) y
> [`PLAN-V1-COMERCIAL.md`](PLAN-V1-COMERCIAL.md).

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
- **Decisión:** [`D-15`](DECISIONES-MAURICIO.md#d-15) — sirena por jack ENCENDIDA en el gabinete de desarrollo.
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
  - [x] `api/tests/test_docs_consistency.py` con 5 asserts que **fallan por separado y dicen
        por qué**: marcadores muertos, "fase posterior" en RBAC, cruce pop-up docs↔código,
        cabecera vs. conteo real de `^### [.]`, y coherencia de cierres cruzados.
  - [x] Las 7 reconciliaciones aplicadas y citadas.
  - [x] Esta ruta escrita, con etiquetas de bloqueo, ruta crítica e invariantes.
- **Trampa que deja escrita:** el assert del conteo **impone una obligación permanente** —
  ver "Conteo de tareas" en la cabecera de este archivo. No es fricción arbitraria: es lo
  único que impide que la cabecera vuelva a mentir 36 tareas.

### [x] T-2.62 · `make test` y el CI no corren lo mismo — `SOFTWARE` · COMPLETA (2026-08-05)
- **Componente:** repo (Makefile) · **Depende de:** —
- **Defecto:** `ci.yml:124-125` corre `npm run build` (tsc + vite) en el job `web`. `make test`
  y `make lint` **no**. Un error de tipos o de build llega a verde local y muere en el PR, que
  es el peor momento para descubrirlo y el más caro de diagnosticar.
- **Criterios de aceptación:**
  - [x] Un test de paridad **lee `ci.yml` y el `Makefile`** y exige que todo paso de CI tenga
        su equivalente local. Comparar prosa no sirve: hay que comparar los comandos.
  - [x] `make test` (o el target que el test declare) incluye el build de web.
  - [x] El test falla si mañana alguien añade un paso al CI y no al `Makefile`.

### [x] T-2.63 · Skips mudos del job `edge` — `SOFTWARE` · COMPLETA (2026-08-05)
- **Componente:** edge/tests · **Depende de:** —
- **Defecto:** 5 tests de hardware se saltan **en silencio** cuando el Raspberry Shake no es
  alcanzable por socket, y el job sigue verde. Es exactamente el patrón que T-2.58 ya cazó en
  el CI con los 67 tests del panel (`node --version`): un job verde que no cubre nada.
- **Criterios de aceptación:**
  - [x] Censo explícito: un `skipif` de alcanzabilidad de socket **sin registrar rompe el
        build** (`edge/tests/test_hardware_gates.py`).
  - [x] El censo distingue un gate de hardware de un skip que no lo es (el `skipif` de `node`).
  - [x] Ningún test se salta sin que el resultado del job lo **declare**.

### [x] T-2.64.d · `soc.css` cita tres tokens que no existen — `SOFTWARE`
- **Componente:** web + design system · **Depende de:** T-2.64 · **Detectada por:** la guardia
  derivada que se escribió para `privacy.css` (2026-08-08)
- **Cómo apareció, que es la parte que importa.** El arreglo de `privacy.css` no se hizo
  cambiando cuatro nombres: se escribió una guardia que **cruza todas las `var(--tk-*)` de
  `web/src/styles/*.css` contra todas las variables del paquete de tokens**. Al correrla, además
  de los cuatro nombres buscados, salió sola la misma deuda en la hoja principal. Una lista de
  cuatro nombres no habría encontrado nada de esto.
- **Lo que hay, medido:** `soc.css` usa `--tk-amber` (líneas 980-981), `--tk-violet` (1749-1750,
  1771-1772) y `--tk-text-2xs` (1773). Ninguno existe en `shared/design-tokens`, así que los
  tres caen siempre a su fallback hardcodeado y **no responden al tema**.
  - `--tk-amber` es **idéntico** a `--tk-status-warning` (mismo `#FFC107`): es un renombrado.
  - `--tk-violet` y `--tk-text-2xs` **no tienen equivalente**: hay que crear el token en el
    paquete o elegir uno existente, que es una decisión de design system, no un `sed`.
- **Ya está acotada, no suelta.** Vive en `DEUDA_HEREDADA` (`web/src/designTokens.test.ts`),
  comparada por **igualdad**: si alguien la paga, el test se pone rojo y **obliga a borrar la
  línea**. Una excepción que puede crecer sola no es una excepción.
- **Criterios de aceptación:**
  - [x] Los tres nombres se resuelven contra el paquete (renombrando o creando el token).
  - [x] `DEUDA_HEREDADA` queda **vacía**, y el test sigue siendo derivado.
  - [x] Si se crea un token nuevo, se regenera `shared/design-tokens` en el MISMO commit o
        `make drift` truena.

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
  - [x] Numeración única, verificada por test sobre los rótulos reales.
  - [x] Contraste ≥ 4.5:1 en los dos espejos (token web **y** copia del panel del edge), con
        el test que lo bloquee — hoy `axe.spec.ts` no lo caza.
  - [x] La columna vacía deja de reservar ancho; medido en los 3 viewports.

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
  - [x] **DECIDIDO** ([`D-06`](DECISIONES-MAURICIO.md), 2026-08-15): **sí se automatiza**. Queda
        pendiente de la consulta de `§4.1` el **aviso legal de uso de datos del SSN** y la
        atribución — va en la misma visita al abogado, no en una segunda.
  - [x] La huella distingue **«republiqué lo mismo» de «llegó catálogo nuevo»** — `T-2.148`.
  - [ ] Ingestor + tabla de instantánea vigente + job — `T-2.149`, **bloqueada**: ver su ficha.

### [x] T-2.148 · Republicar el MISMO catálogo quema versión y despierta al gabinete — `SOFTWARE` · COMPLETA (2026-08-16)
- **Componente:** api + db · **Sale de:** [`D-06`](DECISIONES-MAURICIO.md) ·
  **Prerrequisito duro de `T-2.149`**
- **El hecho, medido en el código:** `push_catalog` incrementa la versión, **firma, PUBLICA por
  IoT**, hace upsert y escribe `catalog_published` **en cada llamada**, aunque el catálogo sea
  byte a byte el que el gabinete ya tiene. Hoy no duele porque lo llama una persona a mano; con el
  job de `D-06` cada pasada haría lo mismo.
- **Por qué es el prerrequisito y no un pulido:** las tres consecuencias son acumulativas y
  ninguna se nota de una en una — la versión monótona escala sin motivo, `audit_log` es
  **append-only y exenta de poda** (regla de oro 11: el renglón de ruido es **permanente**), y
  cada publish **despierta al gabinete** y cuesta su línea en la política de flota. Automatizar
  encima de esto multiplica el ruido por la cadencia.
- **Criterios de aceptación:**
  - [x] Un catálogo **idéntico** al vigente: **no publica, no quema versión y no audita**.
  - [x] Y sin embargo **deja constancia de que se miró** (`last_checked_at`): el silencio total
        haría indistinguible «el job corre y no hay novedad» de «el job murió». Es `D-01` aplicada
        — se declara lo que se sabe y cuándo se supo.
  - [x] La respuesta lo **dice** (`unchanged`), en vez de fingir una publicación.
  - [x] Un catálogo **distinto** sigue publicando, quemando versión y auditando, igual que hoy.
  - [x] La comparación es sobre la forma **canónica** —la misma que se firma—, no sobre el JSON
        crudo: reordenar claves o reindentar **no** es un catálogo nuevo.

### [x] T-2.150 · Cripto-borrado del teléfono del consentimiento — `SOFTWARE` · COMPLETA (2026-08-17)
- **Componente:** api + db · **Sale de:** [`D-07`](DECISIONES-MAURICIO.md) · **Cierra el hueco de
  `T-2.80.a`** · **Postura sujeta a la revisión legal de `T-2.96` (`§4.1`)**
- **El hueco, cerrado.** El `msisdn` estaba **en claro** en `privacy_consents.subject_ref`, tabla
  **append-only por trigger**: ARCO no lo alcanzaba, y anonimizarlo exigía abrir un hueco en el
  guard cuyo valor entero es no tenerlos.
- **La forma de la solución, en una frase:** el número **no entra** en el consentimiento —va su
  ÍNDICE (HMAC de tenant+teléfono, con la pimienta FUERA de la base)— y el número vive **sellado
  con AES-GCM en `privacy_subject_secrets`**, una tabla **mutable**. Ejercer ARCO **borra una fila
  de aquélla y no toca ésta**.
- **Criterios de aceptación:**
  - [x] Las tres propiedades de `D-07`, medidas **a la vez** en un solo test: `privacy_consents`
        **byte a byte** intacta, se conserva la prueba de **que** y **cuándo**, y el número deja de
        ser recuperable. Separadas no dicen nada — conservar la fila es fácil si no se borra nada.
  - [x] El índice lleva el `tenant_id` dentro (regla de oro 5): el mismo número en dos clientes da
        **índices distintos**, así que cruzar las tablas no revela que es la misma persona.
  - [x] El sellado **no es determinista** (nonce por sellado): con GCM, reutilizar (clave, nonce)
        no filtra «un poco» — rompe los dos mensajes. Y un sello determinista delataría que dos
        filas son el mismo número.
  - [x] **Fail-closed**: sin los secretos, el registro por teléfono devuelve **503**. No cae a
        texto en claro «por compatibilidad» — lo escribiría en una tabla que no se puede
        reescribir, en silencio y para siempre.
  - [x] Un volcado de la base **sin los secretos** no contiene el número ni un trozo de él.
  - [x] Las lecturas aceptan **las dos formas**. Buscar solo por el índice habría **revocado en
        silencio** el consentimiento de todo el que ya lo dio: el motor no encontraría su fila y el
        orquestador se negaría a enviarle sin que nadie hubiera retirado nada.

> ### ⚠️ Lo que este mecanismo NO hace, y hay que mirarlo de frente
>
> **No protege hacia atrás.** Cada teléfono ya escrito en claro **se queda en claro para siempre**:
> la tabla es append-only y reescribirlo sería abrir el guard. La única variable que queda es
> **cuántos más se escriben antes de desplegar esto** — la fecha de despliegue es, literalmente, la
> línea que separa los números recuperables de los que no.
>
> **Y el índice no es anónimo mientras exista la pimienta.** El espacio de teléfonos es de ~10^10:
> con la pimienta en la mano, un HMAC se invierte por fuerza bruta en nada. Lo que protege es el
> escenario **real** —una copia de la base sin los secretos del despliegue—, y eso sí lleva test.
> **Es exactamente la pregunta que `D-07` mandó al abogado**, y el código está escrito para que la
> respuesta se pueda cambiar sin rehacerlo.

### [x] T-2.151 · ARCO por teléfono: cablear el borrado al flujo de solicitudes — `SOFTWARE`
- **Componente:** api · **Depende de:** `T-2.150` (hecha)
- `store.forget_msisdn()` existe y está probada, pero **el flujo ARCO está tecleado por `user_sub`**
  y un sujeto-teléfono **no tiene ninguno**: no hay `user_profiles`, así que tampoco el FK compuesto
  que hoy impide nombrar a un titular de otro cliente.
- **Por eso no se cerró de refilón:** hace falta decidir **cómo se acredita** que quien pide el
  borrado es el dueño de ese número —y esa es una pregunta de identidad, no de código—.
- **Criterios de aceptación:**
  - [x] **Decidido y escrito** cómo se acredita la titularidad: **la acredita el cliente
        institucional** que recogió el consentimiento — [`D-23`](DECISIONES-MAURICIO.md#d-23).
        TAKAB ejecuta y audita; no verifica identidades por su cuenta ni custodia documentos.
  - [x] **La respuesta NO puede ser un oráculo de existencia.** A quien no acredita se le contesta
        **lo mismo siempre**: un «no encontrado» frente a un «borrado» convierte el endpoint en un
        buscador de personas — permitiría comprobar si un teléfono consta y, con él, en qué
        edificio. Test que lo fije comparando las dos respuestas byte a byte.
  - [x] **Nadie puede borrar el consentimiento de otro.** Sin acreditación no se ejecuta: destruir
        la prueba de la base legal de un tercero es justo lo que [`D-07`](DECISIONES-MAURICIO.md#d-07)
        construyó el cripto-borrado para impedir.
  - [x] La lápida (`privacy_erasures`) cubre al sujeto `msisdn` igual que al `sub`.
  - [x] Ni una copia del número en la lápida: guardarla «para trazabilidad» convertiría el borrado
        en una seudonimización reversible, que es justo lo que no puede ser.

> ### ✅ CERRADA el 2026-08-22 · `POST /privacy/phone-erasures` (migración `0047`)
>
> **La decisión de diseño que la ficha no anticipaba: es UN endpoint, no dos.** El ARCO por escrito
> de `T-2.80.b` separa *registrar* de *ejecutar* a propósito —dos actos, dos fechas, y de la primera
> corre el plazo legal—. Aquí van fundidos en una transacción, y la razón es material:
>
> > **Para ejecutar hay que tener el número delante.** Registrar hoy y ejecutar la semana que viene
> > obligaría a que la constancia guardase su índice — el mismo `HMAC(pimienta, tenant‖msisdn)` que
> > localiza el sello. Y `privacy_erasure_requests` es **append-only por trigger**: ese índice no se
> > podría borrar jamás, así que **sobreviviría al borrado que lo motivó**. Es determinista, o sea
> > que con la pimienta en la mano se comprueba cualquier número candidato: exactamente la
> > seudonimización reversible que el criterio 5 prohíbe, solo que un paso más allá.
>
> Las dos fechas **no se pierden**: `received_at` sale del escrito (lo pone el cliente) y `erased_at`
> lo pone la base. Lo que se pierde es poder diferir la ejecución.
>
> **`affected` es constante (`{}`), y ahí está el criterio 2.** En el ARCO del padrón son conteos
> útiles; aquí un `{"privacy_subject_secrets": 1}` frente a un `0` sería el oráculo. `forget_msisdn()`
> devuelve si había algo que destruir y **ese booleano se descarta en el router a propósito**.
>
> **La acreditación vive en la base, no en el router** — y esto se midió, no se afirmó:
> `pe_phone_on_behalf` no puede reutilizar `app_can_erase_subject`, que busca la constancia POR
> `user_sub` y con un sujeto nulo no encuentra nada; la exige por `request_id` **y** que se haya
> registrado como constancia de teléfono. `test_una_lapida_de_telefono_sin_su_constancia_no_se_puede_insertar`
> prueba las dos evasiones, incluida la interesante: una constancia REAL pero del padrón, donde el FK
> está satisfecho y la política se niega igual. Sin ese caso, el responsable reutilizaría cualquier
> expediente suyo para justificar cualquier borrado.
>
> El cruce de clientes sale gratis y sin una sola comparación de tenants: el índice se deriva con el
> `tenant_id` de la sesión, así que **el mismo teléfono es dos sujetos distintos e inalcanzables en
> dos clientes**. Medido con el número sembrado en los dos.
>
> **Cuatro sabotajes, y dos enseñaron algo:**
>
> - Devolver el conteo real ⇒ 2 rojos. Quitar la guarda de rol ⇒ 1 rojo.
> - Colar el número en claro por `proof_ref`, y colar su índice ⇒ 1 rojo cada uno… **pero los dos
>   primeros intentos pasaron en verde**, y no porque el test fallara: el parche pegaba en la
>   primera de las dos apariciones de `proof_ref=body.proof_ref`, que es el endpoint de `T-2.80.b`.
>   El sabotaje nunca tocó el código bajo prueba. *Un sabotaje que no se comprueba que muerde vale
>   lo mismo que no haberlo hecho* — segunda vez hoy (la primera, un `grep` que no casaba por los
>   códigos de color).
> - Y se predijo mal cuál de las dos guardas cazaría al `request_id` inventado: se esperaba el FK y
>   **caza antes la RLS**. Las dos están; el orden es el contrario del que uno supone.

### [x] T-2.162 · El correo de guardia no dice qué hacer ni dónde — `SOFTWARE` · COMPLETA (2026-08-22)
- **Componente:** infra (`modules/observability`) · **Hallado:** 2026-08-22, en el ensayo
  cronometrado de `T-2.78`
- **El hecho:** el aviso de on-call es la **plantilla cruda de CloudWatch**. Nombra la alarma, su
  causa y sus umbrales, y **no menciona que haya que acusar, ni dónde**. La palabra «acuse» no
  aparece; la URL de la página tampoco.
- **La evidencia, y es incómoda:** quien lo recibió **acababa de ejecutar el ensayo entero** —había
  acuñado la credencial, abierto la página y acusado un aviso veinte minutos antes— y aun así tuvo
  que preguntar **cuál era «el código» que había que pegar**. Buscó en el correo algo que el correo
  no tiene.
- **Por qué importa más de lo que parece:** el destinatario real está dormido a las 3 a.m. El
  runbook resuelve esto **suponiendo** que la persona tiene el marcador en el teléfono y sabe
  usarlo — y este ensayo **refutó esa suposición con el caso más favorable posible**.
- **Es la misma familia que [`T-2.157`](TASKS.md):** el mensaje era técnicamente correcto y **no
  comunicaba**. Allí era un volcado JSON a un inspector; aquí es una plantilla de AWS a un guardia.
  En los dos casos ninguna prueba de la lógica podía cazarlo, porque la lógica no falla.
- **Criterios de aceptación:**
  - [x] El aviso lleva **qué hacer y dónde**: `alarm_description` de **las doce alarmas** acaba en
        `ACUSA RECIBO en <url> (tu credencial de guardia; tienes N min)`.
  - [x] **Sin canal nuevo:** va en `alarm_description`, el **único texto nuestro** que viaja en el
        correo que compone SNS. Todo lo demás —nombre, umbral, dimensiones— lo pone AWS.
  - [x] El plazo va en el texto **y en minutos**: `900 s` obliga a dividir a quien acaba de
        despertarse.
  - [x] **El plazo se DERIVA, no se teclea dos veces.** `ops_ack_deadline_s` es la fuente única:
        alimenta el texto del correo **y** `TAKAB_API_OPS_ACK_DEADLINE_S` por el output del mismo
        nombre. Si divergieran, el aviso prometería un plazo que la API no respeta — y nadie lo
        notaría hasta que alguien acusara «a tiempo» y el sistema le dijera que llegó tarde.
  - [x] **Sin suscriptor HTTPS no se anuncia el acuse.** Sin él ningún aviso llega a la base: la
        página existiría y no habría nada suyo que atender. Mandar allí a alguien de guardia a las
        3 a.m. es peor que no decir nada.
  - [x] Tres tests, **verificados rompiendo el código**: quitar el sufijo de una alarma deja dos en
        rojo; hornear el plazo deja rojo el suyo.

> ### ⚠️ Y el primer intento del test negativo pasó cuando debía fallar
>
> La aserción del plazo derivado buscaba `"5 min"` con `ops_ack_deadline_s = 300`. **`"5 min"` es
> subcadena de `"15 min"`**, así que con el plazo horneado a 15 pasaba igual. Lo destapó el propio
> ejercicio de romper el código a propósito — que es exactamente para lo que existe.
>
> Corregida a texto exacto (`"tienes 5 min"`) **más la ausencia del valor viejo**. Segunda vez en
> esta sesión que un test pasa por la razón equivocada; la primera buscaba la palabra «consola»,
> que ya salía en el pie del correo.

### [x] T-2.161 · El acuse de guardia no se podía enviar desde la consola — `SOFTWARE` · COMPLETA (2026-08-22)
- **Componente:** api (`routers/ops_alerts.py`) · **Hallado:** 2026-08-22, ejecutando el ensayo
  cronometrado de `T-2.78` · **Bloqueaba:** el criterio 2 de `T-2.78` (`C-5`)
- **El hecho:** el formulario declaraba `action="/ops/alerts/ack"`, una ruta **absoluta**. La
  consola publica la API bajo `/api`, así que la página se pinta en
  `https://<consola>/api/ops/alerts/ack` —Caddy quita el prefijo al pasar— pero **al enviar** el
  navegador resuelve la ruta absoluta contra el host y va a `/ops/alerts/ack`, que ya no es la API:
  es el SPA, y contesta **405**.
- **Cómo se manifestó, y es lo que lo hacía difícil de ver:** la página **funcionaba**, el endpoint
  **funcionaba**, la credencial **era válida** — y el enlace entre los dos no existía. En el log de
  la API no aparecía ni un `POST`: solo el `GET` que sirvió el formulario.
- **El arreglo:** `action=""`, que envía a la URL que sirvió la página, con prefijo o sin él. **El
  endpoint no puede arreglarlo sabiendo su prefijo** — lo decide un proxy que vive en otro sitio;
  lo único que no depende de esa suposición es no hacerla.
- **Criterios de aceptación:**
  - [x] `action` relativo, con test que impide volver a fijar una ruta absoluta.
  - [x] El test cubre también que **siga siendo** un `post` con el campo `token` de tipo
        `password` — la guarda no puede pasar rompiendo el formulario.
  - [x] Desplegado y comprobado con un `POST` real que llega a la API.

> ### ⚠️ Y el diagnóstico costó dos correcciones, las dos mías
>
> **Primero acusé al `action`** —correctamente—, **y luego me desdije** al ver en el log un
> `POST /ops/alerts/ack` desde la IP de Mauricio. **Ese POST era mío**: un `curl` de prueba lanzado
> desde su propia máquina, que sale por la misma IP pública que su navegador. Atribuí mi petición a
> su formulario y «corregí» un diagnóstico que estaba bien.
>
> **La lección:** en un log, la IP no identifica al actor cuando el agente y la persona comparten
> salida a internet. Lo que distinguía a los dos era la **hora** y el hecho de que el mío llevaba
> `token=x`; nada de eso se miró antes de concluir.

### [x] T-2.160 · «¿Llegó ESTE correo?» no tiene respuesta: no hay historial de entrega — `SOFTWARE` · COMPLETA (2026-08-22)
- **Componente:** infra (`modules/identity`) · **Hallado:** 2026-08-22, intentando diagnosticar dos
  correos que no aparecieron
- **El hecho:** el configuration set publica **solo lo que va mal** —`BOUNCE`, `COMPLAINT`,
  `REJECT`, `RENDERING_FAILURE`, `DELIVERY_DELAY`— y a **un correo**. No incluye `SEND` ni
  `DELIVERY`, y no hay ningún destino durable (ni CloudWatch Logs, ni Firehose, ni S3).
- **Lo que costó, medido en esta sesión.** Dos correos con `MessageId` devuelto no aparecieron en el
  buzón. Al preguntar «¿qué pasó con `010f01a0280d7325`?» **no había dónde mirar**:
  - la lista de supresión no lo tenía (correcto, pero no dice nada del mensaje);
  - las métricas de CloudWatch estaban **en cero, incluida `Send`**, mientras el contador de cuota
    decía 2 — o sea, **ausencia de datos indistinguible de ausencia de eventos**;
  - los avisos de rebote van por correo: si nadie los guarda, no existen.

  Con eso se construyó una hipótesis —que Private Email descartaba el correo de su propio
  dominio— que encajaba con **todos** los datos disponibles y **era falsa**: un envío de control al
  mismo buzón llegó sin problema. **La hipótesis no falló por descuido: falló porque los datos que
  la habrían refutado no se guardaban en ninguna parte.**
- **Por qué importa más aquí que en otro producto:** esto es alertamiento sísmico. «¿La solicitud de
  dictamen le llegó al inspector?» no es una curiosidad de operación — es la pregunta que decide si
  hay que llamar por teléfono. Hoy solo se puede responder con *«SES no se quejó»*, y el propio
  `RUNBOOK-ses §1` ya advierte que eso acredita que **el mensaje sale**, no que **la persona
  llega**.
- **Criterios de aceptación:**
  - [x] Destino de eventos **durable y consultable**: los siete tipos —**`SEND` y `DELIVERY`
        incluidos**— van por EventBridge a un grupo de CloudWatch Logs. **No Firehose**: para
        responder «qué pasó con este `MessageId`» hace falta **buscar**, no almacenar; Logs
        Insights busca, un objeto en S3 hay que ir a leerlo.
  - [x] **Retención declarada** (90 días), con test que impide dejarla implícita.
  - [x] **La política de RECURSO del grupo de logs**, que es la que se olvida: EventBridge no
        escribe por tener el ARN en el target. Sin ella el destino se crea limpio y **muere en el
        primer evento**, sobre un camino que nadie mira hasta que hace falta. Mismo modo de fallo
        que ya obligó a poner `aws_sns_topic_policy` para los rebotes.
  - [x] **El `MessageId` se guarda junto al `notification_job`.**

> ### ⚠️ Corrección: la mitad de la base **ya estaba hecha**
>
> Esta ficha decía que «el job dice `sent` y no guarda con qué identificador». **Falso.**
> `notification_jobs.provider_message_id` existe y el orquestador ya lo escribe con
> `provider_message_id(provider)`, que es **genérico por diseño**: lee `.last_receipt.message_id`
> sin saber de canales.
>
> Lo que faltaba era que SES lo alimentara — y su propio comentario decía por qué:
> *«Un provider sin recibo —SES, el webhook firmado— devuelve cadena vacía [...] No hay nada que
> casar donde no hay callback.»* **Era cierto, y dejó de serlo** al publicar los eventos a un
> destino consultable. La costura estaba puesta desde `T-2.77.b` esperando a que existiera el otro
> extremo.
>
> **Y una trampa que se atajó con test:** el recibo del envío anterior **no puede sobrevivir a uno
> fallido**. Dejarlo ataría el job al identificador de **otro** mensaje —la base afirmaría que un
> correo que nunca salió tiene id—. Misma familia que el `alert_latched` de `T-2.28`: un estado que
> no se limpia contamina la lectura siguiente.

> ### ⚠️ Y el primer intento no funcionó: la lista de eventos se declaró DOS VECES
>
> La regla de EventBridge filtraba por `source` **y por `detail-type`**, duplicando la lista que el
> configuration set ya declara. Se escribieron `"Email Send"` y `"Email Delivery"`; **SES envía
> `Email Sent` y `Email Delivered`**.
>
> **Medido: `Invocations = 0`, `FailedInvocations = 0`, el grupo de logs vacío — y ni un error.**
> El fallo no fue un rechazo: fue una **ausencia**. Exactamente el modo de fallo que esta ficha
> existe para eliminar, reintroducido por su propia implementación.
>
> **El arreglo no fue corregir los nombres: fue quitar la duplicación.** El configuration set ya
> elige qué eventos salen; la regla solo tiene que recogerlos. Así, además, un tipo nuevo entra solo
> el día que se añada arriba. Con test que lo impide volver.
>
> Es la tercera vez en la misma sesión que dos declaraciones del mismo hecho divergen —después del
> enlace del correo (`T-2.158`) y del nombre del configuration set (`T-2.155`)—. Y las tres veces
> el síntoma fue el mismo: **nada falla, simplemente no ocurre.**
>
> **Verificado de extremo a extremo**, que es lo único que cierra esta ficha:
> ```
> ¿qué pasó con 010f01a02af55808-…-0466bf26efe7-000000?
>   · Email Sent      | 19:31:57Z | ['ops@takabailert.com']
>   · Email Delivered | 19:31:58Z | ['ops@takabailert.com']
> ```

> ### El censo del módulo tuvo que crecer con la familia
> `ses_domain.tftest.hcl` enumera por regex los recursos SES/DNS/SNS y exige que cada uno tenga su
> aserción de «con la variable vacía no se crea nada». **El historial entró por `aws_cloudwatch_*`,
> que su patrón no miraba**: los cuatro recursos habrían pasado sin que nadie comprobara nada.
> Patrón ampliado y verificado colando un recurso a propósito — lo caza.
>
> **Un censo automático deja de serlo en cuanto la familia crece por un lado que su patrón no
> mira.** Es la misma lección que `§1` de `PENDIENTES`, esta vez en código.

### [x] T-2.159 · Nada impide apagar el acceso del que dependen la cadena on-call y los enlaces — `SOFTWARE` · COMPLETA (2026-08-22)
- **Componente:** infra · **Hallado:** 2026-08-22, antes de encender el flag ·
  **Bloquea:** `T-2.78.a` y con ello el criterio 2 de `T-2.78` (`PENDIENTES §2.9`)
- **El hecho, medido antes de gastar un apply:**

  | Comprobación | Resultado |
  |---|---|
  | La API conoce `TAKAB_API_OPS_ALERT_TOPIC_ARN` | ✅ sí |
  | `POST /api/ops/alerts/sns` responde **404**, no 503 | ✅ el semáforo del runbook está en verde |
  | **Quién puede alcanzar ese 443** | ❌ **una sola IP** (`187.192.70.90/32`) |

  La suscripción **se confirma DURANTE el `apply`**: AWS SNS llama al endpoint desde sus propios
  rangos y ese paquete se descarta en el security group. El apply moriría a medias.
- **Por qué el aviso existente no lo cubre, y es la lección repetida:** el comentario de
  `ops_alert_https_subscriber_enabled` advierte de que la API debe estar desplegada y no contestar
  503. **Las dos cosas estaban bien.** Nadie pensó en el cortafuegos. Es la misma forma que el
  `[PARA]` de `RUNBOOK-ses §2.5`, que predijo el `AccessDenied` del ARN de la identidad y no el del
  configuration set: **un aviso correcto que envejece cubriendo media casuística se lee como
  cobertura completa.**
- **Y es el MISMO bloqueo que la segunda mitad de [`T-2.158`](TASKS.md).** Parecían dos temas —el
  enlace del correo y la cadena on-call— y son uno: **la consola no es alcanzable desde fuera**.
  Resolverlos por separado es resolver dos veces.
- **El matiz que estrecha las opciones:** para confirmar una suscripción HTTPS, **abrir «a los
  rangos de AWS» no es una salida realista**. AWS no publica prefijos por servicio para SNS; lo que
  hay es el bloque `AMAZON` de la región entera, que equivale a abrir al mundo con pasos de más. En
  la práctica el endpoint tiene que ser público.
> ### ✅ El bloqueo descrito arriba YA NO EXISTE (2026-08-22) — y el defecto cambió de forma
>
> [`D-22`](DECISIONES-MAURICIO.md#d-22) abrió la consola, así que AWS alcanza el endpoint. Medido,
> no supuesto:
>
> | | |
> |---|---|
> | Suscripción HTTPS | **confirmada** — ARN real, no `PendingConfirmation` |
> | La confirmación de AWS | `52.95.25.67 POST /ops/alerts/sns 202` |
> | Un aviso real publicado | `52.95.25.209 POST /ops/alerts/sns 202` |
> | La pata de correo | llegó a `ops@takabailert.com` |
>
> **Pero cerrar la ficha aquí sería cerrarla en falso.** El fallo no desapareció: **se dio la
> vuelta**. Antes, encender el flag con la red cerrada **mataba el apply** — ruidoso, inmediato,
> imposible de ignorar. Ahora la suscripción está viva, y **estrechar `web_allowed_cidrs` no rompe
> ningún apply**: rompe la entrega, en silencio, mientras todo el Terraform sigue verde.
>
> **Y ya no cuelga una sola cosa de esa apertura, sino dos:**
>
> - `ops_alert_https_subscriber_enabled = true` — la cadena on-call.
> - `TAKAB_API_NOTIFY_WEB_PUBLIC=true` — el enlace de cada correo ([`T-2.158`](TASKS.md)).
>
> Cerrar el 443 deja la guardia sin avisos **y** los correos prometiendo enlaces muertos. Ninguna
> de las dos cosas produce un error en ninguna parte.

- **Criterios de aceptación:**
  - [x] Decidido **con `T-2.158` a la vez**, no por separado — [`D-22`](DECISIONES-MAURICIO.md#d-22),
        con su coste escrito (de dos capas a una) y su gatillo de revocación.
  - [x] La suscripción confirmada de verdad, comprobada **desde fuera de la lista blanca**: dos
        `202` desde IP de AWS en el log de la API, no el estado que devolvió el apply.
  - [x] **Guarda que ata las piezas**, y por dos vías distintas porque el riesgo era doble:
        - **Validación** en `ops_alert_https_subscriber_enabled`: encenderlo exige
          `web_allowed_cidrs` con `0.0.0.0/0`. `0.0.0.0/0` y no una lista de rangos de AWS porque
          **esa lista no existe** — AWS no publica prefijos por servicio para SNS.
        - **El enlace del correo deja de declararse dos veces.** `deploy.sh` tecleaba
          `TAKAB_API_NOTIFY_WEB_PUBLIC=true`; ahora lo **deriva** del output `console_is_public`.
          Dos declaraciones del mismo hecho divergen, y al divergir habrían dejado los correos
          prometiendo enlaces muertos sin un error en ninguna parte. Mismo criterio que
          `ops_alert_https_endpoint`, que ya derivaba su URL: **un literal apunta a la realidad de
          ayer**.
  - [x] **Falla en el `plan`**, verificado rompiéndolo a propósito: con la lista estrechada,
        `Error: Invalid value for variable` **antes** de tocar nada; restaurada, el plan vuelve a
        salir limpio. Un aviso que llegara en tiempo de ejecución llegaría cuando la guardia ya no
        recibe alarmas.
- **Por qué una validación y no otro párrafo:** el aviso en prosa de esta misma variable ya falló
  una vez — describía puntualmente el fallo que sí se había previsto (API sin desplegar → 503) y no
  el del cortafuegos. **Un aviso correcto que cubre media casuística se lee como cobertura
  completa.** Ésa es la lección que esta ficha deja, y se repitió tres veces en la misma sesión.

### [x] T-2.158 · El enlace de los correos apunta a una consola que el destinatario no puede abrir — `SOFTWARE` · COMPLETA (2026-08-22)
- **Componente:** infra + despliegue · **Hallado:** 2026-08-22, cuando Mauricio pulsó un enlace de
  ejemplo y salió un 403 · **Muerde en:** `T-2.94` (simulacro con cascada real)
- **El hecho, medido:** `TAKAB_API_NOTIFY_WEB_BASE_URL = https://16-58-11-196.sslip.io`, y el 443
  de esa consola admite **una sola IP** (`web_allowed_cidrs`). Cada correo de solicitud de dictamen
  dice «Atender en la consola» con un enlace que **solo puede abrir el operador de esa IP**.
- **Por qué no es «solo configuración de dev»:** el código está bien —compone el enlace desde el
  `console_url` que le den— y la restricción por IP en dev es deliberada. Lo que está mal es que
  **nada lo declara**: el correo invita a pulsar y no hay ni un aviso de que el destinatario no
  llegará. Es la regla de oro 7 fuera de la UI — mostrar algo como accionable cuando no lo es.
- **Y tiene fecha:** `T-2.94` es un **simulacro con cascada de notificación real**, y depende de
  `T-2.78` a propósito. El día que se ejecute, un inspector real recibirá ese enlace. Si esto no
  está resuelto antes, el simulacro acreditará que el correo **sale**, no que la persona **pueda
  actuar** — que es justo la distinción que `RUNBOOK-ses §1` lleva advirtiendo desde que se
  escribió.
- **Lo que hay que decidir al abordarlo** (no se cierra sin esto): si la consola pasa a un nombre
  propio con acceso público tras Cognito, o si el enlace apunta a otra cosa alcanzable. **Es
  decisión de producto y de seguridad, no de código:** quitar la lista blanca expone el SOC, y
  dejarla convierte el enlace en decoración.
- **Decidido el 2026-08-22: las dos, en ese orden.** Primero el correo deja de prometer enlaces
  muertos —hecho, abajo—; la consola pública se planifica aparte con su propia decisión de
  seguridad. Así `T-2.94` no acredita un flujo roto sin forzar hoy la exposición del SOC.
- **Criterios de aceptación:**
  - [x] **El correo no promete lo que no puede cumplir.** `TAKAB_API_NOTIFY_WEB_PUBLIC` declara si
        el DESTINATARIO alcanza la base. Tener URL no es ser alcanzable, y el código no puede
        deducirlo: **lo sabe la red, no el proceso**.
  - [x] **Nace en `False`.** Al revés, cada despliegue nuevo reintroduce el defecto y no se nota
        hasta que alguien intenta pulsar, que es tarde. Y por eso **no entra en
        `REQUERIDOS_EN_PRODUCCION`**: su ausencia no es fallo silencioso — el correo omite el
        enlace **y lo dice**.
  - [x] **Sin enlace se dice qué hacer**, no se calla: quitarlo y no decir nada deja al inspector
        sabiendo que pasó algo y no que le toca actuar.
  - [x] **El corte vive en el ORQUESTADOR, no en el proveedor de correo.** El problema es idéntico
        en SMS y WhatsApp; componer el enlace para tirarlo después invita a que alguien lo reutilice
        sin saber que está muerto.
  - [x] Guarda en el orquestador: con la misma base y el flag apagado, el mensaje **no lleva
        `link`**. Más cuatro tests del cuerpo.
  - [x] **La segunda mitad, hecha el 2026-08-22:** la consola es pública y
        `TAKAB_API_NOTIFY_WEB_PUBLIC=true` se declara en el despliegue, así que el correo vuelve a
        llevar enlace — ahora uno que el destinatario abre. La decisión de seguridad está escrita
        con su coste y su gatillo de revocación en [`D-22`](DECISIONES-MAURICIO.md#d-22).
  - [x] **El acoplamiento queda escrito donde se va a leer:** el comentario junto a la línea dice
        que si algún día se vuelve a cerrar el 443, **esta línea se apaga con él**. Sin eso, cerrar
        la red dejaría el correo prometiendo enlaces muertos otra vez, y nadie lo notaría.
- **Verificado:** `api/tests/notify/` 270 en verde sobre base aislada, ruff limpio.
  > **Y una trampa que costó un diagnóstico:** la primera corrida dio **8 rojos**, de los que solo
  > 2 eran míos. Había **otro `pytest` sobre `takab_test`** (`pgrep -c pytest` lo delató, y un
  > `DeadlockDetected` lo confirmó). Base propia ⇒ el ruido desapareció. **Los 6 falsos se leían
  > igual que los 2 reales.**

### [x] T-2.156 · Sitio público del dominio — `SOFTWARE` · COMPLETA (2026-08-22)
- **Componente:** infra (`modules/site`) · **Sale de:** la denegación del caso `178737638500467`
- **La hipótesis que lo motivó, y que resultó FALSA:** al no poder leer el caso (la API de Support
  exige plan de pago) se dedujo la causa de la infraestructura: la `Website URL` declarada era la
  consola del SOC, cuyo 443 admite **una sola IP**, así que desde AWS daba timeout. **La respuesta
  de AWS no menciona el sitio**: pedía más información sobre el uso. La deducción era razonable y
  no era el motivo.
- **Por qué se hizo igual, y sigue valiendo:** `takabailert.com` **no resolvía en absoluto**, y es
  el dominio que firma los correos. Además `§4.2` lo necesita — Meta mira el dominio al verificar
  el negocio. Se habría hecho de todos modos; solo se hizo antes.
- **Lo implementado:** S3 privado + CloudFront + ACM en `us-east-1`, alias de `takabailert.com` y
  `www`, HTTP redirigido a HTTPS.
  - [x] **La consola conserva su lista blanca.** Arreglar esto no podía costar exponer el SOC: son
        dos sistemas separados y se sirven por separado.
  - [x] Bucket **privado** con Origin Access Control y política acotada por `SourceArn` a esa
        distribución. Un bucket público es una fuga esperando a que alguien suba algo por error.
  - [x] Certificado en `us-east-1` con provider aliasado: CloudFront no lee de otra región, y
        olvidarlo da un error que **no menciona la región** y se diagnostica en el sitio
        equivocado.
  - [x] **Rutas inexistentes devuelven la página con código 404**, no el XML de S3. Con OAC y sin
        `s3:ListBucket` una clave ausente da **403 y no 404** —S3 no distingue «no existe» de «no
        puedes verlo»—, así que hay que mapear los dos. El código es 404 y no 200 a propósito: un
        200 sobre cualquier ruta convierte el sitio en un espejo que afirma tener lo que le pidan.
  - [x] La página vive en `envs/dev/site/index.html`, **no dentro de una cadena de Terraform**: se
        puede abrir en un navegador y revisar en el diff. No afirma nada que el sistema no haga, y
        lleva el deslinde de que la alerta oficial la emite el SASMEX.
- **Verificado desde la instancia de AWS**, fuera de la lista blanca: el sitio da 200 con TLS
  válido y la consola da timeout. **Es la comprobación que faltó la primera vez** — entonces se
  verificó desde la máquina de Mauricio, que es el único punto privilegiado que existe.

### [x] T-2.157 · El cuerpo del correo era un volcado JSON — `SOFTWARE` · COMPLETA (2026-08-22)
- **Componente:** api (`notify/providers.py`) · **Sale de:** la respuesta de AWS al caso
  `178737638500467`, que pidió «ejemplos del correo… para asegurarnos de que es contenido de
  calidad que los destinatarios quieran recibir»
- **El hecho:** `SesEmailProvider.send()` componía el cuerpo con
  `json.dumps(message, indent=2, sort_keys=True)`. El inspector de un hospital recibía, de
  madrugada y después de un sismo, **catorce claves en orden alfabético** — y la nota que
  escribió una persona («grietas visibles en muro de escalera norte») quedaba entre dos UUID,
  en la novena posición por alfabeto.
- **Por qué es la misma familia que `T-2.104`:** allí la app tituló «ALERTA SÍSMICA SASMEX» algo
  que no lo era. Aquí el mensaje era técnicamente exacto y **no comunicaba nada**. En los dos
  casos la lógica estaba bien y lo que llegaba a la persona estaba mal — y **ninguna prueba de la
  lógica podía cazarlo**, porque la lógica no fallaba.
- **Cómo se descubrió, y merece anotarse:** no lo encontró un test ni una revisión. Lo encontró
  **tener que enseñárselo a un tercero**. Generar el ejemplo para AWS fue la primera vez que
  alguien miró el correo como lo mira quien lo recibe.
- **Lo implementado** (`cuerpo_email()`, con ocho tests propios):
  - [x] **El orden es operativo, no estético:** qué pasa, dónde, de qué origen, la nota, el
        enlace. Los identificadores **al pie**, porque no son información para decidir: son para
        quien atienda el reporte después.
  - [x] **El origen se nombra por lo que ES.** Tabla explícita `_ORIGENES`, y un `trigger`
        desconocido **cae a su propio texto en vez de a SASMEX**. Test que exige que un incidente
        de reglas locales no mencione SASMEX **y** que uno de SASMEX sí.
  - [x] **Sin enlace no se inventa uno** (regla de oro 7): test que falla si aparece un `http`
        que el mensaje no traía.
  - [x] **Guarda de raíz:** un test se pone rojo si el cuerpo vuelve a ser JSON parseable, y otro
        exige que la nota esté en la **primera mitad** del texto — que aparezca no basta, porque
        también aparecía en el volcado.
  - [x] Línea de baja: cómo deja de recibir el destinatario. Lo pide AWS y no existía.
- **Verificado:** 8 tests nuevos, `api/tests/notify/` completa en verde (265), ruff limpio.

### [x] T-2.155 · El permiso de envío omite el ARN del configuration set — `SOFTWARE` · COMPLETA (2026-08-22)
- **Componente:** infra (`modules/database`, `modules/identity`, `envs/dev`) ·
  **Hallado:** 2026-08-21, ejecutando el paso 4 de `RUNBOOK-ses §2.5` · **Sale de:** `T-2.78.b`
- **El hecho, medido desde el rol de la instancia** (no desde la CLI de un portátil, que habría
  salido verde sin tocar el rol):

  ```
  AccessDeniedException: User '.../assumed-role/takab-dev-db/i-06fa9b287707c7046'
  is not authorized to perform 'ses:SendEmail'
  on resource '.../configuration-set/takab-dev-correo'
  ```

- **La causa:** la identidad de dominio lleva `takab-dev-correo` como configuration set **por
  defecto**, así que SES lo aplica en **cada** envío sin que el emisor lo nombre — y entonces exige
  permiso sobre **los dos** recursos, identidad **y** set. `local.notify_ses_arns` solo componía
  identidades.
- **Por qué se coló, y es lo que hay que aprender:** el `[PARA]` de `RUNBOOK-ses §2.5` **sí**
  predijo este fallo, con su fecha y todo (2026-07-14) — pero lo predijo **para el ARN de la
  identidad**, que el Terraform ya resolvía solo. **El configuration set no existía cuando se
  escribió ese aviso.** Un aviso correcto envejeció hasta cubrir solo la mitad del caso, y la mitad
  que dejó fuera se comporta idéntica: `AccessDenied` en cada envío mientras **los correos de
  CloudWatch siguen llegando**, porque son SNS con permiso propio.
- **Impacto mientras no se aplique:** con el remitente ya movido a `alertas@takabailert.com`, el
  worker `notify` **no puede enviar ni un correo**. Afecta a notificación de incidente y a solicitud
  de dictamen. La cadena de operación (SNS) **no lo tapa pero tampoco lo denuncia**.
- **El arreglo, ya escrito** (falta el `apply`):
  - [x] `notify_ses_arns` compone también `configuration-set/<nombre>` cuando hay dominio.
  - [x] El nombre del set deja de estar a fuego en `modules/identity` y vive **una sola vez** en
        `envs/dev`, pasado a los dos módulos. Database no puede leerlo de un output de identity
        —cerraría el ciclo `identity -> serve -> database`—, así que una sola definición era la
        única forma de que no diverjan.
  - [x] **`terraform apply`** — hecho el 2026-08-21. `WorkerSesSend` ya lista los tres ARN
        (las dos identidades y el configuration set), verificado leyendo el rol.
  - [x] **Envío desde la instancia sin `AccessDenied`** — mismo comando que fallaba, ahora
        devuelve `MessageId`. El rol usado es
        `assumed-role/takab-dev-db/i-06fa9b287707c7046`, no una credencial de consola.
  - [x] **Cabeceras del correo recibido** (2026-08-22): `dkim=pass` con **selector propio**
        (`3r2ck3b5...`, uno de los tres de Route 53), `spf=pass` sobre `bounce.takabailert.com`,
        `dmarc=pass` y `Return-Path` en el subdominio propio. **Alineación por los DOS caminos**:
        el correo lleva también la firma de `amazonses.com`, y de haber estado sola, DKIM habría
        pasado igual **sin alinear**.
  - [x] Test de Terraform que ponga en rojo un `WorkerSesSend` sin el ARN del set cuando hay
        dominio. **Verificado rompiendo el código a propósito**: quitar el ARN del `concat` deja el
        test en rojo; restaurarlo lo devuelve a verde. Un test que solo pasa no prueba que cace
        nada.
  - [x] **Y su mitad complementaria:** sin configuration set declarado **no puede colarse** un
        `configuration-set/` vacío en la política. Un ARN sobre un recurso inexistente no da error
        de Terraform y se lee como cobertura.
- **Por qué el test anterior no bastaba, que es la lección:** ya existía uno que comprobaba el ARN
  de la identidad de dominio, y pasaba — mientras el envío real moría. Comprobaba que estuviera **lo
  que alguien pensó en su momento**, no que estuviera todo lo que SES exige. **Un test que asegura
  la presencia de X no dice nada sobre la ausencia de Y**, y aquí Y era el recurso que la propia
  identidad aplica sola.

### [x] T-2.154 · La alarma temprana del backup base grita en CADA ciclo — `SOFTWARE` · COMPLETA (2026-08-22)
- **Componente:** infra (`modules/observability`) · **Hallado:** 2026-08-21, verificando el
  redespliegue · **Alarma:** `takab-dev-backup-base-atrasado`
- **El hecho, medido** (`BaseBackupAgeSeconds`, periodo 300 s):

  ```
  22:03  605219 s  (7,00 d)
  22:18  606059 s  (7,01 d)   <- la alarma entra en ALARM
  22:23    1619 s  (0,02 d)   <- el backup programado aterriza
  ```

- **La aritmética que lo hace inevitable, y no es mala suerte:**
  - umbral = **604800 s = exactamente `base_backup_interval_days` (7 d)**;
  - la cadencia es `base_backup_dom = */7` — días 1, 8, 15, 22 y 29, o sea **el mismo intervalo**;
  - `EvaluationPeriods=2 × Period=300` ⇒ hacen falta **10 min** de incumplimiento;
  - el backup tardó **~20 min** en completarse **y ser escaneado**.

  La edad cruza el umbral **en el instante en que arranca el backup nuevo**, y sigue cruzada hasta
  que ese backup termina y el escáner lo publica. Con cualquier duración por encima de 10 minutos,
  **la alarma dispara en todos los ciclos**.
- **Por qué es un defecto y no una molestia:** vigila el **ancla de la cadena PITR** — lo que
  decide si un restore es posible. Una alarma que grita cada 7 días sin motivo enseña a ignorarla,
  y se ignorará **la semana en que el backup sí falle**. Es el criterio que ya gobernó
  [`D-05`](DECISIONES-MAURICIO.md#d-05) y [`D-10`](DECISIONES-MAURICIO.md#d-10): la credibilidad
  es lo que hace que alguien obedezca **la próxima vez**.
- **Lo que NO hay que hacer al arreglarlo:** subir el umbral hasta que deje de sonar. Su propia
  descripción dice que existe para *«cazar el PRIMER backup base fallido, mientras todavía queda
  ventana de recuperación»* — y su hermana `base_backup_max_age_s`
  (`interval × chain_margin`) ya es la última línea. Si esta se relaja hasta parecerse a aquélla,
  el proyecto se queda con dos alarmas para el mismo caso tardío y **ninguna para el temprano**.
- **La causa real, medida y distinta de la que se supuso.** No era la duración del backup: era el
  **calendario**. `04:00` backup (días 1, 8, 15, 22, 29) · `05:00` scan —lo único que descubre el
  backup nuevo— · publicador cada minuto. La edad cruza el umbral **a las 04:00** y no baja hasta
  las **05:00**: **60 minutos de incumplimiento garantizados por ciclo**, contra 10 de margen.
  Medido sobre los objetos de S3:

  | Backup | Inicio | Último objeto | Duración | Tamaño |
  |---|---|---|---|---|
  | `20260815T040002` | 04:00:02 | 04:04:44 | **4m 42s** | 276 MB |
  | `20260822T040002` | 04:00:02 | 04:05:41 | **5m 39s** | 329 MB (**+19 % en una semana**) |

- **Criterios de aceptación:**
  - [x] **Atacada la causa, no solo el síntoma:** `takab-base-backup.sh` refresca la métrica al
        terminar. La ventana pasa de **60 min a ~6**. El scan de las 05:00 se queda —cubre backups
        hechos por otra vía y repara el fichero—, pero deja de ser el único.
  - [x] **La gracia sale de medir:** 3600 s cubre los ~6 min con 10× de holgura y deja sitio al
        crecimiento, y aun así es el **0,6 % del intervalo**. Declarada en `base_backup_grace_s`,
        no horneada.
  - [x] **No es «subirlo hasta que calle»:** test que exige que entre el aviso y la última línea
        quede **al menos un intervalo completo** — el tiempo de relanzar un backup antes de que la
        cadena se rompa.
  - [x] Dos tests nuevos, **verificados rompiendo el código**: volver al umbral exacto deja 3 en
        rojo; quitar el refresco deja rojo el suyo.

> ### ⚠️ El hallazgo que no estaba en la ficha: **el defecto estaba protegido por un test**
>
> `el_umbral_del_backup_base_se_deriva_de_las_variables_de_retencion` exigía
> `base_backup_warn_age_s == interval * 86400` **exacto**. Su razonamiento era correcto en teoría
> —«el primer instante en que se puede afirmar que un backup no se completó»— y **ciego a cómo se
> produce el dato**: la métrica sigue contando la edad del backup anterior hasta que alguien
> descubre el nuevo.
>
> **Quien fuera a arreglar el umbral se habría encontrado ese test en rojo y habría podido concluir
> que su arreglo estaba mal.** Un test fija un defecto tan bien como fija un acierto.
>
> Y había una segunda: `max == warn × chain_margin`, un cociente exacto **que solo se sostenía
> porque el aviso era el intervalo pelado**. Se había elevado a invariante una coincidencia de la
> fórmula. Re-expresada por lo que de verdad importa —el aviso llega antes, y con un intervalo
> entero de ventana— en vez de por un múltiplo que no le importa a nadie.

### [x] T-2.152 · El fallback del publicador de retención de PII es código muerto — `SOFTWARE` · COMPLETA (2026-08-22)
- **Componente:** infra (`modules/database/prune_pii_setup.sh.tpl`) · **Hallado:** 2026-08-21, al
  verificar el apply de `T-2.78.b` · **Alarma afectada:** `takab-dev-retencion-pii-detenida`
- **El hecho, medido en la máquina** (`bash -x` sobre `/opt/takab/bin/takab-prune-pii-age.sh`):

  ```
  ++ docker exec takab-db psql ... | tr -d '[:space:]'
  + EDAD=
          ← el script muere AQUÍ
  ```

  El script abre con `set -euo pipefail`. Cuando psql **falla**, `pipefail` propaga el error, la
  asignación devuelve distinto de cero y `set -e` mata el script **antes** del
  `if [ -z "$EDAD" ]`. **El fallback a `pii-retention-configured-epoch` es inalcanzable.**
- **Por qué importa más que un `|| true` olvidado, y es lo que lo hace fichable:** el comentario
  del propio documento declara que ese fallback existe *«para que la alarma NAZCA diciendo la
  verdad ("no consta ninguna retención ejecutada") en vez de quedarse aparcada»*. **La mitigación
  no puede correr justo en el escenario para el que se escribió.** Es la misma forma que
  [`D-10`](DECISIONES-MAURICIO.md#d-10) describió para el `G-02`: *el fallo que la mitigación
  existe para impedir, reintroducido por la propia mitigación*.
- **El matiz que acota el alcance, y hay que respetarlo al arreglar:** el fallback cubre
  **«todavía no ha corrido ninguna»** (psql devuelve vacío con éxito ⇒ sí se alcanza) pero **no
  «no se puede preguntar»** (psql devuelve error ⇒ muere). En un entorno recién desplegado los dos
  estados coinciden, así que falla exactamente cuando más falta hace.
- **`takab-wal-age.sh` NO tiene este defecto y no se toca.** Comparte la forma pero **no la
  intención**: su comentario dice que si psql falla no se publica nada a propósito, y su
  `[ -n "$EDAD" ] || exit 1` es deliberado — *«publicar un 0 a ciegas sería decir que el respaldo
  va bien cuando lo único cierto es que no se pudo preguntar»*. Morir ahí **es** su conducta
  correcta. Cambiarlo por simetría sería introducir un defecto.
- **Criterios de aceptación:**
  - [x] **Tres estados, no dos.** El estado de la consulta se captura aparte (`|| ESTADO=$?`), así
        que el vacío deja de ser indistinguible del error:
        1. responde un número → esa es la edad;
        2. responde **vacío** (ninguna corrida correcta) → fallback al origen, para que la alarma
           nazca diciendo la verdad;
        3. **falla** (no se puede preguntar) → **no se publica nada**, y el script lo dice en
           `stderr` nombrando la causa típica (esquema por detrás del repo).
  - [x] **No se quita el `set -e`**, que habría sido el arreglo fácil y peor: cualquier fallo
        posterior pasaría desapercibido. Se separa el estado, que es lo que estaba mal.
  - [x] **La asociación deja de reportar `Success` cuando su publicador no publicó.** Era
        `|| log AVISO`; ahora falla. En el momento de instalar esto la base tiene que estar
        alcanzable y el esquema al día: si no lo está es deriva de despliegue, y hay que verla
        **en rojo, ahora**, no dentro de un mes por una alarma que nadie relacionó.
  - [x] **Dos tests, verificados rompiendo el código a propósito**: quitar la separación del estado
        deja rojo el primero; devolver el `|| log` deja rojo el segundo; restaurado, 29 en verde.
        Se asserta la **separación**, no la ausencia de `set -e` — un test escrito al revés habría
        bendecido el arreglo malo.

### [x] T-2.153 · Nada detecta que la nube va por detrás del repo en migraciones — `SOFTWARE` · COMPLETA (2026-08-25)
- **Componente:** api + observabilidad · **Hallado:** 2026-08-21, persiguiendo `T-2.152`
- **El hecho, medido:** `alembic_version` en la nube = **`0038_privacy_erasure_on_behalf`**; la
  cabeza del repo = **`0046_privacy_subject_sealing`**. **Ocho migraciones de diferencia**, y
  ninguna alarma, ningún health-check y ningún test lo dijo.
- **La consecuencia concreta que lo destapó:** `0043` crea `pii_retention_runs`. Sin ella,
  `takab-prune-pii-age.sh` no puede publicar su métrica y la alarma de retención se queda en
  `ALARM` sin poder salir — **un defecto de datos disfrazado de defecto de código**. Se perdió
  media hora de diagnóstico persiguiendo el script antes de mirar la versión del esquema.
- **Por qué NO se cierra con el redespliegue:** el redespliegue arregla *esta* deriva. Lo que hay
  que arreglar es que **la deriva sea invisible** — mañana vuelve, y volverá a descubrirse por un
  síntoma lateral. Es la doctrina de la alarma del gabinete mudo aplicada al esquema: **se vigila
  la ausencia, no el error.**
- **El agravante de contexto:** `/api/health` **ya declara el commit desplegado**, así que la
  mitad del trabajo existe. Lo que no declara es la **cabeza de migración esperada** frente a la
  aplicada, que es la que rompe cosas en silencio.
- **Criterios de aceptación:**
  - [x] `/api/health` expone **la revisión de alembic aplicada** y **la que la imagen trae**, y
        **las compara** (`ops/schema_version.py`). `status` sigue siendo `ok` pase lo que pase:
        un esquema viejo es un problema de datos, no un proceso muerto, y matar la liveness por
        él tumbaría el contenedor.
  - [x] **Gate de despliegue** cuando difieren (2026-08-24). `deploy/cloud/deploy.sh` levantaba
        contenedores y declaraba ✓ **sin preguntarle nada a la API** — la misma familia que
        `systemctl is-active` haciéndose pasar por canary. Ahora pregunta tres cosas y las dice
        JUNTAS si fallan las dos: que la API conteste, que corra **el commit recién desplegado**
        (un `docker compose ps` en verde con la imagen de ayer tiene el mismo aspecto) y que el
        esquema esté **al día**. Reintenta 60 s, porque un gate que preguntara una sola vez sería
        un falso rojo en cada despliegue.
  - [x] Test con un esquema deliberadamente atrasado — **el caso real `0038` vs `0046`, con sus
        ocho migraciones**, en los dos lados: `tests/test_health.py` (7) y
        `tests/test_gate_despliegue_nube.py` (8, aislando el veredicto del script sin desplegar
        nada). Verificado por mutación.

  - [x] **Alarma que mira SOLA** (2026-08-25) — `takab-dev-esquema-atrasado`. El gate hace
        visible la deriva **en el despliegue**; ésta la hace visible **siempre**, que es lo que de
        verdad hacía falta: la nube no se quedó atrás por un despliegue malo, sino porque **nadie
        desplegó durante días**, y un gate sólo mira cuando alguien lo invoca.

> ### Las tres decisiones que no rompen el plan si se eligen mal, y producen una alarma que MIENTE
>
> **El cero se publica.** Es la diferencia entre una alarma y un adorno:
> `takab-dev-iot-rule-errors` estuvo **catorce días en `ALARM` por estar sana y además MUDA**,
> porque su filtro no publicaba el cero — una sola transición en toda su vida, y SNS sólo
> notifica transiciones. El publicador manda el valor **cada minuto pase lo que pase**, así que
> el correo de OK es el acuse de que la nube volvió a estar al día.
>
> **`breaching`, y aquí cubre TRES ausencias que significan lo mismo**: la API que no contesta;
> un estado que no es un número (`desconocida` = no se pudo preguntar a la base, `adelantada` =
> la base va POR DELANTE de la imagen, o sea un despliegue al revés); y que **nadie haya
> desplegado desde que existe el publicador** — que es la ficha entera. Ninguno de esos casos se
> convierte en un número inventado para que encaje en el umbral.
>
> **Umbral CERO, y la tolerancia va en los periodos.** Una sola migración pendiente ya es el
> defecto; lo que hay que tolerar es la ventana del propio despliegue —entre `alembic upgrade
> head` y la API nueva contestando hay segundos de tránsito—, y avisar de eso sería un correo en
> cada despliegue: así se enseña a mandar una alarma a la papelera.
>
> El namespace de la métrica es el mismo que la condición IAM del rol de la instancia. Si
> divergieran, el publicador recibiría `AccessDenied` y **la alarma se quedaría ciega sin que
> nada pareciera roto** — hay un aserto sólo para eso.
>
> Anclado en `tests/deriva_de_esquema.tftest.hcl` (2 runs, 9 asertos), verificado por mutación.
> **Nace en `ALARM` el día del apply y está bien**: hasta el siguiente `make cloud-deploy` no hay
> quien publique.

### [ ] T-2.149 · Ingestor del catálogo SSN — `SOFTWARE` · **BLOQUEADA**
- **Componente:** api (worker) + db · **Sale de:** [`D-06`](DECISIONES-MAURICIO.md) ·
  **Depende de:** `T-2.148` (hecha)
- **Bloqueada en dos cosas, y ninguna es código:**
  1. **El formato del feed no se puede verificar.** `ssn.unam.mx` no es alcanzable desde el
     entorno de desarrollo (`ECONNREFUSED` a `132.247.71.71`) y su esquema no está documentado
     públicamente. **Escribir un parser para un formato que no se ha visto es adivinar**, y el
     fallo sería silencioso: un feed que cambia de forma deja el catálogo congelado sin un error.
  2. **El aviso legal de uso de datos del SSN y su atribución** — va en la consulta de
     [`CONSULTA-LEGAL-TAKAB.md`](CONSULTA-LEGAL-TAKAB.md).
- **⚡ 2026-08-23 · el primer bloqueo está CADUCADO y el segundo está en vías.** El feed responde
  (200, RSS 2.0 con `geo:lat`/`geo:long` y `ETag`), aunque **solo por HTTP: el 443 está cerrado**.
  Y hay conversaciones abiertas con el SSN con apoyo aparentemente concedido. Lo que hace falta
  traerse de esa reunión —endpoint programático, esquema, atribución literal, cadencia— está en
  [`REUNION-SSN-QUE-PEDIR.md`](REUNION-SSN-QUE-PEDIR.md), con las siete peticiones y qué destraba
  cada respuesta. **La ficha sigue `[ ]`: una reunión agendada no es un endpoint.**
- **Lo que `D-06` exige que traiga cuando se desbloquee**, y no se negocia:
  - [ ] **Declarar la fecha del último catálogo ingerido con éxito**, visible en la UI. Es `D-01`:
        un catálogo viejo se declara viejo, no se presenta como vivo (regla de oro 7).
  - [ ] **Alarma por AUSENCIA, no por error.** La fuente es de un tercero sin contrato: si cambia
        de formato o cae, el catálogo se congela **en silencio**. Es la misma doctrina que la
        alarma del gabinete mudo — se vigila que el latido **falte**, no que algo falle.

### [x] T-2.67.b · La cola «durable» del edge no sobrevive a un reinicio — `SOFTWARE` · COMPLETA (2026-08-09)
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
  - [x] Ruta durable por defecto (`/var/lib/takab/spool`, `SPOOL_DIR=` la cambia), escrita por
        el aprovisionamiento en el bloque GESTIONADO, con `install -d -m 0700` para el
        directorio y su hermano de pendientes. Eso cierra también el agravante: con la ruta
        cayendo a `/tmp`, cualquier usuario podía crear el directorio primero y quedarse de
        dueño, y el `mkdir(exist_ok=True)` del servicio lo aceptaba.
  - [x] **Migración de los pendientes existentes:** si el gabinete ya declara OTRA ruta, el
        aprovisionamiento **aborta** y da los `mv` exactos, en vez de moverla y dejar la
        evidencia huérfana en la ruta vieja. Es la única clave gestionada que no puede
        imponerse sola — las demás son identidad y credenciales, y ahí pisar es lo que se
        quiere. Verificado en los tres casos: gabinete nuevo, ruta distinta, ruta ya correcta.
  - [x] Test derivado (`test_el_aprovisionamiento_escribe_la_ruta_DURABLE_de_la_cola`): rojo si
        alguien quita el `printf` del bloque gestionado.
- **Nota de campo (2026-08-09):** `gw-dev-0001` **ya tenía la clave puesta a mano**
  (`/var/lib/takab/spool`, con su `backfill-pending` hermano). Por eso el defecto no se veía en
  el único gabinete que miramos: el que nacía roto era el gabinete SIGUIENTE.

### [~] T-2.67.c · 20 evidencias atascadas: **eran DOS fallos, no uno** — `SOFTWARE`
- **Componente:** edge · **Origen:** la card de T-2.67 contra el gabinete VIVO
- **El hecho, re-medido el 2026-08-09 sobre `gw-dev-0001`:** ya no son 18 sino **20**, la más
  vieja del **31-jul** y la más nueva **del mismo día del censo** — o sea que **crecen y ninguna
  drena**. Cada una es una ventana de 3 minutos de un sismo real.
- **Fallo 1 — array enmascarado (CERRADO).** Traza sacada del journal del Pi, no supuesta:
  `NotImplementedError: Masked array writing is not supported`, en
  `buffer/__init__.py:extract_window` → `stream.write(buf, format="MSEED")`. `merge(method=1)`
  sin `fill_value` deja un array enmascarado en cuanto la ventana tiene un hueco. El pendiente
  ni sube ni se descarta: **se reintenta cada ~2 min para siempre**.
  Arreglado con **`Stream.split()`** y NO con `fill_value=0`: rellenar con ceros escribe «el
  suelo estuvo quieto» justo donde no hubo medición, dentro de un fichero que es prueba
  forense. miniSEED admite tramos no contiguos del mismo canal ⇒ el hueco sigue siendo un hueco
  y no cuesta una mentira.
- **Fallo 2 — el grant, y es el grande (ABIERTO).** El censo de las 20 contra el ring real dice:
  **solo 4 fallan por el array enmascarado; las otras 16 extraen perfectamente** (155–213 KB de
  miniSEED válido cada una) y llevan igualmente 9 días sin subir. No hay una sola línea de
  grant ni de PUT en 48 h de journal, porque el `_request_grant` **desplegado devuelve `None`
  sin registrar nada**. La versión de esta rama (T-2.67) ya añadió ese `log.warning`, así que
  **el diagnóstico del fallo 2 llega solo en cuanto se redespliegue el edge**.
  ⇒ La causa raíz que esta ficha daba por única explicaba **el 20 %** del atasco.
- **Criterios de aceptación:**
  - [x] La extracción con huecos produce evidencia utilizable, o falla **declarándolo**.
  - [x] Test con ring con huecos que reproduce el atasco
        (`test_extract_window_con_hueco_produce_evidencia_utilizable`): sin el arreglo levanta
        el mismo `NotImplementedError` que el gabinete.
  - [x] Las 20 del gabinete vivo, explicadas una a una: 4 por array enmascarado, 16 por el
        grant. Censo re-derivable con el script del PR.
  - [~] **El fallo 2, ya NOMBRADO (2026-08-09, edge redesplegado a `7f1c278`):** la card de
        evidencia del gabinete declara `extract_failed_total: 0` —el arreglo de `split()`
        funciona en producción, las 20 extraen bien— y `last_result: grant_timeout`, con el
        journal repitiendo «evidencia … **sin grant a tiempo**; sigue pendiente» para las 20.
        **La nube nunca concede el grant.** Queda por determinar si el publish al topic de
        request lo deniega la política de flota de AWS IoT (trampa conocida: toda regla IoT
        nueva exige su línea o el gabinete se desconecta en cada publish), si el worker de
        nube no responde, o si el grant vuelve por un topic al que el edge no está suscrito.
  - [ ] **Un descarte deja de borrar la evidencia en silencio** (decisión de producto: ¿se
        conserva la ventana parcial, se marca, se reintenta?). Hoy **no está firing** —el censo
        dio `0 sin dato`—, así que es riesgo latente y no pérdida en curso.

---

## BLOQUE II · Funciones finales — `SOFTWARE`

> **No espera a ningún gate** (regla de ordenación) y **puede empezar el día 1**. Dos cosas
> que sí hay que tener escritas, porque no se deducen de ninguna ficha de tarea:
>
> 1. **`T-2.84` (matriz requisito→test) depende de las Fases 2.3–2.8**, y las Fases 2.3 y 2.4
>    son del **Bloque I**. Es un cruce Bloque II → Bloque I y es intencional: una matriz
>    escrita antes de que existan los tests que cita documenta intenciones, no cobertura. Se
>    declaró por rango de fases y no por lista de tareas, así que **no aparece en ninguna
>    línea `Depende de: T-…`**: hasta el 2026-08-05 el cruce era invisible para el test que
>    los vigila.
> 1.b **`T-2.164` depende de `T-2.150`**, que es del **Bloque I**. Segundo cruce
>    Bloque II → Bloque I, y también intencional: `T-2.150` selló el sujeto de los
>    consentimientos NUEVOS, y `T-2.164` es exactamente la mitad que ese sellado **no** puede
>    alcanzar —los teléfonos ya escritos en claro en una tabla append-only—. No se puede fichar
>    antes de que el sellado exista, porque hasta entonces no hay «filas viejas» que distinguir
>    de las nuevas.
> 2. **Este bloque está en la ruta crítica**, aunque el carril de gates sea el que se agenda
>    primero: `T-2.74` y la cascada `T-2.75`→`T-2.78` son suyos, y `T-2.94` (Bloque III)
>    espera a `T-2.78`. Ver "RUTA CRÍTICA" al final del archivo. Nada de esto significa que
>    el Bloque II espere a un gate: **no espera a ninguno**; es al revés.

## Fase 2.5 · Operación de flota

Hoy actualizar un gabinete es **`ssh` + `deploy.sh` a mano**. Con un gabinete es incómodo; con
veinte es imposible; con veinte y una regresión, es peligroso.

### [x] T-2.69 · Inventario de versiones de flota — `SOFTWARE` · COMPLETA (2026-08-07)
- **Componente:** api + web · **Depende de:** —
- **Criterios de aceptación:**
  - [x] La consola dice **qué versión corre cada gabinete**, con edad del dato.
  - [x] Se ve la deriva: cuántos gabinetes están atrás y cuánto.
  - [x] `S/D` cuando no se sabe — nunca la última versión conocida pintada como actual.

### [x] T-2.70 · Actualización remota con canary y rollback — COMPLETA (2026-08-24)
- **Desbloqueada por** [`D-04`](DECISIONES-MAURICIO.md#d-04) (2026-08-16): la ventana de
  mantenimiento avisada para mover al dueño de los pines.
- **Componente:** api + edge + deploy · **Depende de:** T-2.69

> ### ✅ SEGUNDO INTENTO (2026-08-23, 22:31): EL GABINETE REAL CORRE EL LAYOUT A/B
>
> Con los tres arreglos puestos, el despliegue completó **con ✓ de punta a punta**: gate del
> intérprete en verde, canary con remojo de 120 s sin una lectura enferma, ventana declarada,
> dueño de los pines reiniciado, y propiedad re-verificada. Y después el **reinicio en frío**,
> que es la prueba que anoche no llegó a hacerse:
>
> | Comprobación (`A.2`) | Medido |
> |---|---|
> | 1-2 · procesos vivos, sin pelear | `active`/`active`, `NRestarts` **0 y 0** |
> | 3 · backend GPIO real | `LGPIOFactory (lgpio)` — sin caída a sysfs/native |
> | 4 · quién sostiene los pines | `pid=740`, `unit=takab-gpio`, `flock=9` |
> | — · desde dónde arrancó | **desde el symlink**: `releases/20260824T034254Z-67de47c/edge` |
> | — · lo demás | nube `online` (RTT 75 ms, spool 0), SeedLink reconectado, **cero errores** |
>
> Reproduce exactamente la línea base del 2026-08-17 (`NRestarts` 0 y 0, `flock=9`), y esta vez
> **arrancando desde el symlink**. `G-01` queda en **4/5**: falta que los relés se muevan, que es
> la prueba AUDIBLE del panel y exige a alguien delante del gabinete.
>
> **Y un segundo hallazgo del campo, ya corregido:** la poda se llevó la release **heredada** — el
> árbol de julio, con meses de operación real detrás y la única versión de la que se sabía que ese
> edificio sobrevive a un apagón. Toda release nueva es más reciente que ella, así que una poda por
> fecha se la lleva siempre. Ancla: `test_la_poda_JAMAS_se_lleva_la_release_heredada`.
>
> **Lo que queda fichado y NO se arregló:** el layout A/B crea por diseño una ventana de versiones
> mezcladas (cliente nuevo, dueño viejo hasta la ventana declarada), y el códec de pinlink es
> estricto — un dueño más antiguo se rechaza igual que un contrato roto
> (`ProtocolError: … llegó sin ['keepalive_beating']`). Medido: durante esa ventana **el panel no
> ve los relés** (`gpio_unreachable`). La protección no se toca —el reflejo vive entero dentro de
> `takab-gpio`—, pero la observabilidad sí. El códec necesita distinguir *dueño más viejo* de
> *contrato roto*.

> ### 🔴 PRIMER INTENTO EN EL GABINETE REAL (2026-08-23): FALLÓ, y por qué eso valió la pena
>
> **El gabinete se quedó sin dueño de pines** —sin sirena, sin cierre de gas, sin retenedores—
> con las dos unidades ciclando en `203/EXEC`, hasta que se miró. Y la causa **no estaba en el
> código que se desplegaba**, que es justo por lo que `G-01` no es una formalidad:
>
> Las dos unidades declaran `ProtectHome=true`: para ellas `/home` NO EXISTE. El venv del Pi era
> UNO y se reusaba **desde julio**, con su intérprete en `/opt/takab/.python` porque alguien
> exportó `UV_PYTHON_INSTALL_DIR` **a mano** aquella vez — un hecho que vivía en un directorio y
> **en ningún archivo**. El layout A/B estrena venv por release; `uv` eligió intérprete por
> primera vez en meses y se lo puso en `$HOME`. El ejecutable existía; el que no existía **para
> systemd** era su intérprete.
>
> **Los tres gates del despliegue corren como el usuario de ssh, con `/home` entero visible**, así
> que por construcción no podían verlo: un venv «importable» aquí es `203/EXEC` allí. Y el canary
> leyó `MainPID=0` como «no pude medir» en vez de como lo que es —una unidad que systemd da por
> ACTIVA y sin proceso principal, o sea un `ExecStart` que no llegó a ejecutarse— así que **dejó
> la release puesta en lugar de revertir**, que era exactamente su trabajo.
>
> Las tres corregidas y ancladas: el gate del intérprete
> (`test_un_venv_cuyo_interprete_ProtectHome_esconde_NO_se_activa`), la declaración de dónde
> instala `uv` (`test_el_interprete_de_uv_se_instala_FUERA_de_lo_que_ProtectHome_oculta`) y la
> clasificación de `MainPID=0` (`test_una_unidad_ACTIVA_sin_proceso_principal_es_una_medicion_MALA`).
> Gabinete revertido a la release heredada y protegiendo. Bitácora en
> `runbooks/RUNBOOK-sesion-de-vida.md §A.5`.

> ### CERRADA EN SOFTWARE (2026-08-23) — lo que queda es FÍSICO
>
> **Los cinco criterios están construidos y medidos; el único que no se cierra desde aquí es
> el gate `G-01`.** El primer despliegue A/B de un gabinete real convierte `/opt/takab/edge`
> de directorio a symlink, o sea que cambia la RUTA DESDE LA QUE ARRANCA EL CAMINO DE VIDA, y
> eso no se declara bueno con tests en verde: exige un restart en frío del Pi con las dos
> unidades volviendo solas. Hasta entonces `deploy.sh` se niega a migrar sin ventana declarada.
>
> **Lo que existe y está medido.** El despliegue dejó de ser in-place: cada versión aterriza
> entera en `/opt/takab/releases/<ts>-<sha>/` **con su propio venv y sus propios contratos**, y
> `/opt/takab/edge` pasó a ser un **symlink** — el `ExecStart` de las dos unidades no cambia,
> cambia a dónde resuelve. La activación la hace `/opt/takab/bin/canary.sh`, que vive **FUERA de
> toda release**: el caso que un rollback existe para cubrir es «la versión nueva no arranca», y
> un reversor dentro de esa versión es justo el que no puede correr.
>
> **El criterio de salud, que es lo que separa esto de un `restart`.** `systemctl is-active` a
> los 3 s daba por bueno un proceso que arranca y crashea al segundo 4 (refinamiento 3 de
> `T-2.70.a`). El remojo sostiene CUATRO señales a la vez: unidad activa, **MainPID sin relevo**
> —un crash-loop se delata ahí y en ningún otro sitio—, **pines con dueño** (el mismo `flock` del
> paso 7) y **panel contestando**, que es «llegó a servir» y no sólo «arrancó».
>
> **«Medido mal» ≠ «no medido», y de eso depende que el reversor no haga daño.** Revertir es
> reiniciar y reiniciar cuesta una ventana sin sirena, así que un `flock` ilegible o un `curl`
> ausente dejan la versión puesta, salen con código propio y lo GRITAN — jamás un ✓, jamás un
> ciclo de gas por un dato que nadie leyó.
>
> **Lo que decide si se puede activar NO es el gabinete: es quién lo ordenó.** En un gabinete
> cuyo dueño de pines siga dentro de `takab-edge`, activar cicla `GAS_VALVE` y `DOOR_RETAINER`.
> Atendido (`deploy.sh`, con una persona leyendo la salida) avisa y sigue —es lo que ya hacía—;
> **remoto exige ventana declarada**, que es como llegará el comando firmado. Revertir no exige
> nada: ahí el reinicio no es el daño, es la cura.
>
> **⚠️ LA MIGRACIÓN AL LAYOUT A/B ES FÍSICA Y NO SE CIERRA CON TESTS EN VERDE.** El primer
> despliegue A/B de un gabinete convierte `/opt/takab/edge` de directorio a symlink: cambia la
> **ruta desde la que arranca el camino de vida**. `deploy.sh` se niega a hacerlo sin
> `--ventana-de-mantenimiento`, conserva el árbol heredado ENTERO como release —con su venv—
> para que exista vuelta atrás, y **exige `G-01`** (restart en frío del Pi con las dos unidades
> volviendo solas). `G-01` está SIN ACREDITAR: es la mitad de esta ficha que no se puede cerrar
> desde aquí.
>
> Anclado en `edge/tests/test_canary_sh.py` (16, el script corrido de verdad contra un gabinete
> de mentira) + `test_deploy_sh.py` (35) + `test_deploy_artifacts.py` (66). Tres mutaciones
> verificadas: quitar la comparación de MainPID, quitar la `-T` del `mv` y quitar la guarda de
> ventana ponen en rojo los tests que las vigilan.

- **Criterios de aceptación:**
  - [x] **`takab-gpio` NO se detiene durante la actualización.** Es el proceso que toca la
        sirena (regla de oro 4); una ventana de actualización no puede ser una ventana de
        desprotección. **Cerrado en software Y acreditado en el gabinete real (2026-08-24):** la activación reinicia sólo al CLIENTE, y que
        ninguna rama del reversor nombre al dueño está anclado por comportamiento y por texto
        (`test_jamas_se_reinicia_al_dueno_de_los_pines`,
        `test_el_reversor_no_reinicia_jamas_al_dueno_de_los_pines`). El reinicio del dueño sigue
        exigiendo ventana declarada y ahora va DESPUÉS del repunte — antes estrenaría la versión
        vieja y ciclaría gas y retenedores a cambio de nada.
  - [x] **El criterio de éxito que un canary necesita, y que no existía.** El latido MENTÍA
        sobre qué código corre: `fw_version()` relee el archivo `FW_VERSION` en cada snapshot
        y `deploy.sh` lo escribe ANTES de reiniciar, así que el proceso **VIEJO** publicaba la
        versión **NUEVA** — y para siempre si el restart no ocurría. Cualquier canary colgado
        de esa señal habría dado VERDE a una actualización no aplicada. Ahora el gabinete
        congela el SHA **al importar** (`running_version()`), publica los dos, la ingesta
        persiste `gateways.fw_running` y la nube deriva el estado `SIN REINICIAR`.
  - [x] Canary: primero uno, se observa, luego el resto. Un despliegue a toda la flota a la
        vez es un incidente a toda la flota a la vez. `POST /fleet/rollouts` activa **UNO** y se
        para —no hay parámetro para «actívalos todos», y esa ausencia es la ficha—;
        `/advance` se NIEGA con 409 mientras el canary no declare `fw_running` = el SHA
        esperado. **Un ack no basta y por eso no se acepta:** dice que la orden llegó, no que
        el gabinete arrancara ese código, y entre las dos cosas caben todos los fallos que
        importan. `fw_running` en `null` tampoco confirma: «no lo ha dicho» no es «está bien».
        **Lo avanza una PERSONA, no un reloj**, por el mismo criterio que los simulacros —un
        reloj sólo lee lo que se le enseñó, y el fallo que el remojo no ve (latencias raras, un
        sensor mudo, un cliente que llama) se descubre mirando—. Y **un rollout es de UN
        tenant**: actualizar varios clientes a la vez es justo lo que esto existe para impedir,
        así que la política se escribe en el modelo y no en un runbook.
  - [x] **Rollback automático** ante fallo, con criterio medible de fallo (no "parece mal"). El
        criterio son las cuatro señales del remojo, y la vuelta atrás es COMPLETA —código y
        dependencias— porque cada release lleva su venv.
  - [x] Comando firmado + nonce + ack (regla de oro 8). `POST /sites/{id}/update` y
        `.../update/rollback` emiten por `issue_signed_command` (HMAC por gateway, nonce
        UNIQUE, TTL, rate-limit, auditoría) **con MFA**, bajo la acción nueva
        `deploy_firmware` — SOLO `takab_superadmin`, con el criterio de
        `platform_maintenance_window` y no el de `maintenance_window`: el código es de TAKAB
        y un `tenant_admin` no tiene el artefacto ni con qué juzgarlo.
        **El ack dice «orden aceptada», no «funcionó», y el orden de dos líneas es el diseño:**
        activar reinicia `takab-edge` —el proceso que recibió el comando—, así que un ack
        posterior al lanzamiento no se publicaría jamás y la nube esperaría el TTL sin poder
        distinguir «rechazado» de «no contestó». El gabinete acusa ANTES y lanza el agente
        desligado de su sesión (`start_new_session`), o el `systemctl restart` se llevaría por
        delante al propio reversor. El resultado viaja por el latido (`fw_running`).
        Revertir NO acepta a qué versión volver: la sabe el gabinete, y una reversión a
        ninguna parte es peor que ninguna reversión.
  - [x] Test: actualización que falla ⇒ el gabinete vuelve solo a la versión anterior. Cubierto
        en sus cuatro formas: no arranca, arranca y CICLA, arranca y el panel no contesta, y
        arranca sin dueño de pines. Más el caso honesto: revertido y **sigue** enfermo ⇒ eso ya
        no es la actualización, es el gabinete, y sale con código propio.

> **DECISIÓN RATIFICADA (2026-08-07) — separar los procesos.** El criterio 1 no se podía
> cumplir ni incumplir: `takab-edge.service` declara `Conflicts=takab-gpio.service` porque
> ambos reclaman los mismos pines BCM, así que **no son procesos independientes, son
> excluyentes**.
>
> **Y separar NO revierte el gate #6: lo IMPLEMENTA.** El gate ratificó (`PLAN-MAESTRO §3`)
> *«un solo proceso **mínimo**: WR-1 in + relés out + reflejo SASMEX→sirena in-process
> (<100 ms)»*. Ese proceso **existe y es funcional** —`edge/takab_edge/gpio/__main__.py`, que
> NO importa `supervisor`/`seedlink`/`signal` (ObsPy/NumPy/SciPy), arranca en <1 s y sostiene
> el reflejo «aunque el resto del edge no exista»— pero **no es el que corre**. En el Pi corre
> `takab-edge`, el supervisor de 16 módulos, que instancia su propio `GpioController`
> (`supervisor.py:178`). O sea: **la sirena la toca hoy el mismo proceso que hace SeedLink,
> sincronía con la nube, backfill, audio, LoRa y la API local** — contra la regla de oro 4.
> `deploy/edge/deploy.sh:51` documenta el gate como «supervisor único», cuando su texto dice
> «proceso mínimo». Esa divergencia entre lo ratificado y lo construido es el defecto.
>
> El propio plan maestro ya había tasado el cambio (*«interfaz `Actuator` estable; `gpio`
> autocontenido; costo = driver/rename»*), pero **el acoplamiento medido es mayor**: cinco
> módulos reciben `gpio` directamente (`RelayActuator`, `AudioNotifier`, `DrillController` y
> dos más), más dos observadores `on_sasmex` y el modo prueba. Lo tranquilizador: **el reflejo
> <100 ms no cruza el IPC** —vive entero dentro de `gpio`—; lo que cruzaría es actuación
> posterior (gas, ascensor, puertas), lectura de estado para el panel, simulacro y modo prueba.
> Ninguno está en el camino crítico. Por tamaño y por tocar el camino de vida, va como fase
> propia: **`T-2.70.a`**.

### [~] T-2.70.a · El proceso que toca la sirena deja de ser el que hace todo lo demás — `SOFTWARE` CERRADO + `FÍSICO` ACREDITADO · abierta SOLO por el criterio 4 (`GATE-HW`)
- **Componente:** edge (arquitectura de procesos) · **Depende de:** — · **Desbloquea:** T-2.70

> ### D3 CERRADO EN SOFTWARE (2026-08-08) — seis criterios cumplidos, y el cuarto es de HARDWARE
>
> **Seis de siete `CUMPLE`, todos anclados y auditados adversarialmente.** El séptimo es el que
> desbloquea T-2.70 y está medido: **reiniciar `takab-edge` cuesta CERO transiciones** en los
> cinco relés, contra las 6 por pin que costaban tres ciclos antes.
>
> **El criterio 4 es `IMPOSIBLE EN SOFTWARE`, y esta ficha lo declara como tal en vez de
> fingirlo.** La ventana existe: mover el dueño cuesta **exactamente 2 transiciones por pin**, o
> sea **un ciclo eléctrico de `GAS_VALVE` y `DOOR_RETAINER`** — el gas se cierra y las puertas se
> sueltan. La causa, verificada contra el código instalado y no de memoria: `LGPIOPin.close()`
> **re-reclama la línea como ENTRADA** con el bias deshabilitado. **Es gpiozero quien
> desenergiza, no el kernel** —matiz que corrigió la auditoría: no hace falta ninguna bandera del
> uAPI para conservar un nivel, lo decide si el driver devuelve el pad a entrada al liberar.
>
> **El encuadre que convierte esto en decisión y no en bloqueo:** ese ciclo cuesta **lo mismo que
> cualquier `deploy.sh` de hoy**. La diferencia es que **este es el último**. Las dos salidas
> son: una **ventana de mantenimiento con el edificio avisado, una sola vez**; o **hardware**
> —enclavamiento del relé, o un pull-up que sostenga la bobina con la línea liberada— que
> **cambia SPOF-07**, porque entonces un Pi colgado dejaría de fail-safear gas y puertas. Eso no
> se decide desde el software. **`GATE-HW` / `G-05`.**
>
> **SPOF-02 ESTABA ROTO, y ese es el hallazgo que justifica el paso entero.**
> `_seed_from_held_contact` corría **antes** de que existiera el servidor, así que con el dueño
> en otro proceso el episodio nacía **sin `episode_id`** y el cliente lo descartaba por diseño.
> Medido: **sirena sonando en el edificio, y cero incidente, cero notificación, cero push.** Es
> el traspaso hardware→software tras un reinicio con el contacto **sostenido** — el caso de un
> sismo largo.
>
> **B2 · el despliegue mentía sobre el dueño, y la solución no fue ninguna de las dos que se
> plantearon.** Reiniciar al dueño en cada despliegue **anula el valor entero de D3**; y fallar
> siempre que no se reinició saldría rojo en **todos** los despliegues, entrenando al operador a
> ignorar el único rojo que dice si la sirena tiene dueño. Así que el gate mide **«¿corre código
> distinto del que acabamos de poner?»** —arranque desde `/proc/<pid>/stat` + `btime`, y si
> arrancó antes, comparación byte a byte de los módulos que el entry point **arrastra**, derivados
> de sus imports—. El `restart` va solo bajo `--ventana-de-mantenimiento`; `enable` y `start` van
> siempre, porque no cuestan un ciclo y sin ellos el siguiente reinicio del Pi deja al edificio
> **sin dueño de pines**.
>
> **El arnés de tests tenía dos vacuidades** que había que cerrar o no medía nada: el `systemctl`
> falso **truncaba** el registro del dueño legítimo, y **reclamaba los pines con cualquier
> unidad** — así que un `takab-gpio` que no arranca salía **verde** porque «reiniciar
> `takab-edge`» fingía tomar el GPIO.
>
> **`FDSTORE` evaluado y descartado, con el contra que decide y que no es de implementación:** un
> fd retenido **congela el último nivel sin nadie que lo gobierne**. Si el dueño muere en mitad de
> una alerta, **la sirena queda sonando** y nadie puede pedirle `silence`; hoy esa muerte cae al
> fail-safe. Va fichado aparte con su política por canal — congelar el gas puede ser correcto;
> congelar la sirena no.
>
> **Lo que queda para `GATE-HW`:** la duración real de la ventana en el Pi; la latencia del
> transporte en ARM; `TimeoutStartSec=90` con `Type=notify` contra el systemd real; el criterio 4
> físico; y el gate de código viejo, que **nunca se ha ejercitado con un intérprete de verdad**.
- **`DECISIÓN` RATIFICADA (2026-08-07): separar los procesos.** No es un override del gate #6;
  es cerrar la brecha entre lo que el gate ratificó y lo que se construyó (ver la nota de
  T-2.70). Hoy la sirena la toca el supervisor de 16 módulos.
- **Lo que hay que romper, medido:** cinco módulos reciben `gpio` directamente
  (`RelayActuator`, `AudioNotifier`, `DrillController` y dos más, `supervisor.py:178-293`),
  más dos observadores `on_sasmex` (`:321-323`) y el modo prueba (`:428-433`).
- **Lo que NO cruza el IPC, y por eso esto es viable:** el reflejo SASMEX→sirena vive **entero
  dentro de `gpio`**. Cruzarían actuación posterior (gas, ascensor, puertas), lectura de estado
  para el panel, simulacro y modo prueba. **Ninguno está en el camino crítico de <100 ms.**
- **Criterios de aceptación:**
  - [x] `takab-gpio` es el **dueño de los pines** y corre como servicio propio; `takab-edge`
        deja de instanciar su `GpioController` y le habla por IPC. **Verificado en vivo el
        2026-08-24**: el cerrojo dice `unit=takab-gpio` y el panel lee los relés a través de la
        costura.
  - [x] **`takab-gpio.service` gana su `EnvironmentFile`.** Sin él arrancaría con los defaults
        de código —incluido el mapa de pines de `GpioPins`—, que es el peor fallo imaginable de
        esta tarea: energizar el pin equivocado de un gabinete cableado.
  - [x] Se retira `Conflicts=takab-gpio.service` y un test demuestra que **ya no son
        excluyentes** (`test_las_dos_unidades_YA_NO_son_mutuamente_excluyentes`). Lo que impide
        dos dueños ya no es una promesa de systemd sino un **cerrojo del kernel**, que además
        atrapa lo que `Conflicts=` nunca vio: un `python -m takab_edge.gpio` suelto por SSH.
  - [ ] ~~**La transición no desenergiza los relés.**~~ **DECLARADO IMPOSIBLE EN SOFTWARE, y la
        ficha lo dice en vez de fingirlo.** Mover al dueño cuesta **exactamente 2 transiciones
        por pin** —un ciclo eléctrico de `GAS_VALVE` y `DOOR_RETAINER`— porque
        `LGPIOPin.close()` **re-reclama la línea como ENTRADA** con el bias deshabilitado: es
        gpiozero quien desenergiza, no el kernel. Las dos salidas son una ventana declarada (la
        que se usó el 2026-08-24) o **hardware** —enclavamiento del relé, o un pull-up que
        sostenga la bobina— que **cambiaría SPOF-07**. Eso no se decide desde el software:
        `GATE-HW` / `G-05`.
  - [x] **SPOF-02 intacto**: el traspaso hardware→software tras un reinicio con el contacto
        SOSTENIDO (`_seed_from_held_contact`) funciona con los procesos separados. **Estaba
        ROTO** —el sembrado corría antes de que existiera el servidor, así que el episodio nacía
        sin `episode_id` y el cliente lo descartaba: sirena sonando y cero incidente— y ese
        hallazgo es lo que justificó el paso entero.
  - [x] El reflejo sigue midiendo **<100 ms**, y el test lo MIDE con relés en vez de afirmarlo.
        En el gabinete real: **6.65 ms y 4.16 ms** con el WR-1 de verdad, dos órdenes de
        magnitud de margen sobre el presupuesto.
  - [x] Reiniciar `takab-edge` **NO detiene la protección** — que es lo que desbloquea T-2.70.
        **Medido el 2026-08-24 y no una vez**: el canary reinició al cliente en cada activación
        y en cada remojo, y el dueño de los pines conservó el cerrojo sin un solo relevo de PID.
  - [x] **`FÍSICO`**: acreditación en el Pi real (2026-08-24). `takab-gpio` es el dueño de
        los pines en `gw-dev-0001`, sobrevive a un reinicio en frío **desde el symlink del
        layout A/B** con `NRestarts=0`, y la prueba local de actuación mueve los **5 canales**
        con `readback_ok`. No se cerró con tests en verde: se cerró con el gabinete delante.
- **Nota de secuencia:** el plan maestro tasó este cambio como «driver/rename» porque `gpio` es
  autocontenido y la interfaz `Actuator` es estable. El acoplamiento medido dice que es más:
  va como fase, con reconocimiento, diseño del IPC y gate físico.

**Endurecimiento previo del despliegue manual (2026-08-07) — y lo que queda FICHADO aquí.**

La ficha sigue abierta: nada de esto es el canary ni el rollback automático. Lo que se cerró es el
`deploy.sh` de hoy y sus unidades, porque el criterio 1 se cumple **de forma vacía** (`takab-gpio`
no corre en producción: `Conflicts=takab-gpio.service`, gate #6 supervisor único — anclado en
`test_las_dos_unidades_siguen_siendo_mutuamente_excluyentes`), así que lo que se detiene en cada
despliegue es `takab-edge`, el proceso que toca la sirena.

Cerrado en `edge/tests/test_deploy_artifacts.py` + `edge/tests/test_deploy_sh.py`: la trampa de la
sección de systemd aplicada a **las seis** directivas y no a una (mover `RestartSteps=` a `[Unit]`
evapora el backoff ⇒ 3600 ciclos/hora de válvula de gas, y `systemd-analyze verify` sale 0 igual);
la lectura de la **última** asignación y no la primera; el mensaje de aborto que ofrecía restaurar
desde una instantánea que en el primer despliegue no existe; y el `journalctl` informativo que
tumbaba despliegues ya terminados.

FICHADO — refinamientos que NO se persiguieron, cada uno con su razón:

1. **El oráculo de systemd se salta en silencio.**
   `test_systemd_no_ignora_en_silencio_ninguna_directiva` lleva `skipif` cuando falta
   `systemd-analyze`. `ubuntu-latest` lo trae hoy, pero el job `edge` **no lo declara** como
   declara `node --version`. Añadir un paso `systemd-analyze --version` al job (misma familia que
   los 67 tests del panel que se saltaban anónimos). Sin él queda el respaldo offline
   (`_SECCION_CANONICA`), que cubre seis directivas y no todas.
2. **`systemd-analyze verify` sale 1 en cualquier máquina que no sea el Pi**, porque
   `ExecStart=/opt/takab/edge/.venv/bin/takab-edge` no existe fuera de él. El código de salida no
   distingue "unidad mal escrita" de "no es la máquina de destino", así que como gate no sirve y el
   test lee TEXTO (`Ignoring.`). **Verificar las unidades EN EL PI**, donde el `ExecStart` sí
   existe, es trabajo de `GATE-HW`/G-01.
3. **`systemctl is-active` a los 3 s no es un canary.** Un proceso que arranca y crashea al
   segundo 4 se reporta como despliegue exitoso, y con `Restart=always` el gabinete queda ciclando
   mientras el operador se va del sitio. Es exactamente el criterio 2 de esta ficha; no se
   improvisa aquí.
4. **Rollback automático: sigue sin existir.** `edge.prev` es manual, sólo fuente (no revierte el
   `.venv`) y el despliegue es in-place sobre un venv editable. Lo que lo cierra es el despliegue
   A/B con symlink descrito en la cabecera de `deploy/edge/deploy.sh` — cambia el arranque del
   camino de vida y exige acreditación en el Pi real (G-01). Criterios 3 y 5.
5. **"Gana la última" en bash, generalizado.** `_array_bash()` ya exige asignación única para
   `EDGE_EXTRAS`/`EDGE_EXTRAS_OMITIDOS`; el resto de variables del script (`PY_PREVUELO`,
   `RAIZ_REMOTA`…) se siguen leyendo con `re.search` = la primera. Con un script de 280 líneas y
   una asignación por variable es teórico; si el script crece, generalizar el parser.
6. **`TimeoutStopSec=90` sigue sin medirse en el Pi.** Está declarado y anclado, pero el número
   salió del default de systemd, no de una medición. Bajarlo exige medir `supervisor.stop()` con
   los 16 módulos y qué le pasa a los relés ante un `SIGKILL` por timeout (con `gas_valve` y
   `door_retainer` reposando energizados, un SIGKILL suelta los pines sin pasar por
   `drive_all_safe()`). `HUMANO-HW`.

**D2/P1 — la costura `GpioLink` (2026-08-07) — y la DEUDA DE CONTRATO que deja fichada.**

`edge/takab_edge/gpio_link.py`: cuatro operaciones (`snapshot`/`apply`/`action`/`subscribe`), una
sola implementación (`LocalGpioLink` = llamada directa, un proceso, ni un pin movido), y los cinco
consumidores más los dos observadores migrados a ella. El reflejo SASMEX→sirena **no** cruza —
anclado por `test_el_reflejo_sasmex_no_cruza_la_costura`, que cablea una costura MUERTA a los
cinco consumidores, dispara el pin del WR-1 y lee los cinco relés (sirena y estrobo protegen; gas,
ascensor y puertas NO, que es la no-vacuidad).

FICHADO — la deuda que D2/P1 deja declarada, con su razón:

1. **`HealthSnapshot.relays` no sabe decir «sin dato», y esto lo empeora.** `[]` significaba
   «módulo detenido»; desde D2/P1 significa además «no pude preguntar al dueño de los pines»
   (`health/__init__.py::_relay_states`). Son dos averías distintas con dos reacciones distintas y
   la nube no puede distinguirlas: es exactamente el defecto que T-2.68 cerró para el panel del
   gabinete, reabierto en el latido. Hoy la distinción sólo vive donde SÍ se puede actuar sobre
   ella —el `log.critical` del edge y el `relays_status.reason = gpio_unreachable` del panel LAN—,
   **no en el contrato**. Cerrarlo es un cambio de schema: `relays: list | None` (o un
   `relays_status` hermano del del panel) + bump de `SCHEMA_VERSION` (`edge/takab_edge/schemas.py`,
   hoy `1.9.0`) a `1.10.0`, ingest de la nube que lo lea, y la columna/vista donde aterrice. **NO
   se hizo aquí a propósito**: D2/P1 se declaró «la costura y NADA más» para que cualquier
   diferencia de comportamiento posterior fuera atribuible al IPC, y tocar el contrato edge→nube
   habría roto esa propiedad. Va **con D2/P2**, que es cuando `gpio_unreachable` deja de ser
   inalcanzable y el dato empieza a existir de verdad.

**D2/P2 — el TRANSPORTE (2026-08-07). Construido y APAGADO: `GPIO_LINK` sigue en `local`.**

`edge/takab_edge/pinlink/{codec,server,client,cli}.py`, sin dependencias nuevas (socket `AF_UNIX`
+ `json` de la stdlib; `codec` importa `pydantic` porque los contratos lo son — ver M12 abajo),
más el servidor DENTRO del dueño actual (`GpioController.arrancar_servidor_de_pines`, hilo **NO
crítico**: sin socket el reflejo vive igual) y `IpcGpioLink`, cliente **CACHÉ-FIRST** con
`critical = False`. Tampoco mueve un pin: el mismo proceso es dueño y cliente. Lo que D3 enciende
es una línea (`TAKAB_EDGE_GPIO_LINK=ipc`, dueño todavía en `takab-edge`), y su ensayo general ya
corre en `tests/test_pinlink.py::test_el_gabinete_ENTERO_funciona_hablando_por_el_socket`.

Lo que sostiene el paso, y dónde mirarlo:

- **La suite de conformidad** (`tests/test_gpio_conformance.py`): todo test del archivo corre DOS
  veces —contra `LocalGpioLink` y contra un cliente conectado a un servidor que envuelve **ese
  mismo** `GpioController`—. **Derivada, no enumerada**, por tres vías: el fixture parametrizado
  con una guarda que exige que TODO test del módulo lo pida (lista de EXCEPCIONES declaradas, no
  de miembros); los casos que salen de `GPIO_ACTIONS`, `GPIO_EVENTS` y
  `GpioSnapshot.__dataclass_fields__`; y un oráculo campo a campo probado contra una costura que
  miente en CADA campo, uno por caso. Medido con dos mutaciones: una divergencia silenciosa en
  `siren_sounding` pone en rojo 4 casos `[ipc]` y ninguno `[local]`; un servidor que traga la
  acción `silence` pone en rojo su caso derivado y ninguno más.
- **La EDAD de la instantánea** (`GpioSnapshot.age_s`): se mide en el reloj de QUIEN LEE (no viaja
  por el cable — `time.monotonic()` no es comparable entre procesos) y **fuera de plazo el dato NO
  EXISTE**: `GpioLinkUnavailable`, que es la causa que los consumidores ya tratan desde D2/P1.
- **Reconciliación por `episode_id`**: una reconexión durante un sismo NO reabre el incidente en la
  nube, y un episodio nacido con el enlace caído se entrega exactamente UNA vez.

FICHADO — lo que D2/P2 decide y lo que deja abierto:

1. **La deuda 1 de D2/P1 (`HealthSnapshot.relays` sin «sin dato») SIGUE ABIERTA**, y su razón
   cambió: se dijo «va con D2/P2, cuando `gpio_unreachable` deje de ser inalcanzable», pero D2/P2
   **no enciende el cliente** — con `GPIO_LINK=local` esa causa sigue sin poder ocurrir en
   producción. Bumpear `SCHEMA_VERSION` para un estado que aún nadie puede alcanzar sería mover el
   contrato edge→nube sin un solo caso real que lo justifique. Va **con D3**, que es el paso que lo
   vuelve alcanzable, y con el mismo alcance ya fichado (schema 1.10.0 + ingest + columna/vista).
2. **La latencia del transporte NO está medida en ARM.** El p50 de `AF_UNIX` del reconocimiento
   (0.017 ms) es de x86-64. El diseño **no depende de ese número**: las lecturas no cruzan el
   socket (caché-first) y el reflejo no lo cruza en absoluto (gate #6). Lo que sí depende es el
   coste de las ESCRITURAS —un lote de tier, una acción del panel—, anclado con una cota de orden
   de magnitud (p50 < 10 ms) en `test_una_ida_y_vuelta_por_el_socket_es_barata`. Medirlo en el Pi 4
   es trabajo de D3/`GATE-HW`.
3. **`Type=notify` en la unidad, sin poner.** `run_gpio_process` ya emite `sd_notify(READY=1)` tras
   ser dueño (cerrojo + pin factory + 5 relés + 3 botones + seed), y sin `NOTIFY_SOCKET` es un
   no-op. Cambiar `Type=simple`→`notify` en `takab-gpio.service` toca el arranque del camino de
   vida y va con D3, junto con retirar `Conflicts=`.
4. **`takab-gpioctl` INTERROGA, no acciona** (anclado por test). Una CLI capaz de comandar relés
   sería una segunda puerta a los actuadores sin PIN, sin registro de acciones y sin ack firmado.

**D2/P2 · cierre de la auditoría adversarial (2026-08-07). Dos BLOQUEANTES y siete menores.**

La auditoría RECHAZÓ el paso. Mucho de lo que fue a romper aguantó y está medido —el reflejo no
cruza el transporte (0.027 ms constante con el servidor apagado, encendido y con suscriptor), los
cinco modos de fallo del bind dejan el gabinete protegiendo, `drive_all_safe` es inalcanzable por
siete vías, y no hay caché vieja servida como fresca ni con `SIGSTOP` de 12 s—, pero lo que no
aguantó habría convertido D3 en un desastre silencioso.

**B1 · EL OBSERVADOR DE SASMEX SE AUTOBLOQUEABA.** `IpcGpioLink._avisar` despachaba los
observadores en su **único hilo lector**. `supervisor._on_sasmex` se registra ahí y ACTÚA
(`_act_and_publish` → `RelayActuator` → `link.apply`), y `apply` espera una respuesta que **sólo
ese hilo puede leer**: interbloqueo con timeout garantizado en cada sismo. Medido con un
`EdgeSupervisor` real y `simulate_sasmex`:

| | ACKs con éxito | ACKs fallidos | relés gas/elev/puertas |
|---|---|---|---|
| `GPIO_LINK=local` | 5 | 0 | `True` |
| `GPIO_LINK=ipc` (antes) | 0 | **5** | **`True`** |

Mentía en las **dos** direcciones a la vez: la nube veía la protección caída de un gabinete que
había protegido (el servidor ejecutó el lote; el cliente nunca leyó la respuesta). Daños
colaterales medidos: la caché llegaba a 1.99 s (0.14 s de `gpio_unreachable` **en pleno sismo** —
panel a `S/D`, latido con relés vacíos) y el aborto del simulacro se retrasaba 2.003 s.

*Arreglo:* los observadores corren en un hilo propio (`pinlink-observadores`), FIFO, con el orden
de registro conservado — no se prohibió la reentrada, porque prohibirla dejaría a D3 sin actuación
posterior por SASMEX, que es justo lo que el paso existe para transportar. La prohibición queda
como **cable trampa**: `ReentradaDelHiloLector` (hereda de `GpioLinkUnavailable`, así que todos los
consumidores la degradan igual) declara el defecto **en 0 ms y por su nombre** si alguien vuelve a
meter una orden en el hilo lector, en vez de en 2 s disfrazado de «el dueño no contestó» —que
apunta al dueño, y el dueño estaba perfecto.

**B1-bis · el test que decía acreditar D3 era TEATRO.**
`test_el_gabinete_ENTERO_funciona_hablando_por_el_socket` recorría ese camino exacto y pasaba,
porque sólo miraba si el evento llegó a `takab/events`; los cinco ACKs de la secuencia que la
alerta disparó no los leía nadie, y la actuación que sí verificaba se lanzaba desde el hilo
principal, donde no hay reentrada. Ahora asierta los ACKs, y la prueba que de verdad cierra D3 es
`test_un_SASMEX_actua_IGUAL_por_las_dos_costuras[local|ipc]`: mismo `EdgeSupervisor`, mismos cinco
ACKs, mismos relés, mismo evento a la nube y mismo aborto del simulacro (<1 s) por las dos vías.

**B2 · la guarda de pertenencia de la conformidad tenía DOS agujeros**, y uno evadía **pareciendo
conforme**. Infería la pertenencia de `inspect.signature(...)` sobre `vars(modulo)` filtrado por
`inspect.isfunction`: un método dentro de `class TestIntruso:` no era `isfunction` (ni se miraba),
y un `@parametrize("enlace", [...])` que **SOMBREA** el fixture tenía el nombre en la firma y
jamás instanciaba las variantes `local`/`ipc`. Con las dos coladas: 62 passed y la guarda muda.
Ahora se mide lo que pytest **colectó** (`item.callspec.params`, censado en
`conftest.pytest_itemcollected` — antes de la deselección por `-k`, así que el censo no depende de
cómo se invoque la suite), exigiendo variante `local` **y** `ipc` por ítem. Verificado poniendo las
dos evasiones en el archivo: las caza las dos, nombrando con qué se colectó cada una.

CERRADOS en el mismo paso, cada uno con su test y su mutación de no-vacuidad:

- **M7 · `TIMEOUT_ACTION_S` se justificaba con una premisa FALSA.** El *hold* de 5 s de
  `actuation_test` va en un `threading.Timer` y **no bloquea la llamada**; lo que bloquea son los
  bucles de pulsos (1.207 s y 1.606 s medidos con los tiempos de fábrica). 30 s eran ~19× el peor
  caso real. Ahora **5 s**, y el número lo ancla
  `test_el_plazo_de_las_acciones_sale_de_lo_que_TARDAN`, que MIDE cada acción de `GPIO_ACTIONS` en
  vez de creerse el comentario.
- **M3 · el rate-limit ahogaba el journal que lo diagnostica** (1 línea por petición frenada, 417
  líneas/s medidas). Autolímite a ~1/s por conexión, con el contador de las que calló — mismo
  patrón que `audio._reconcile_siren`, regla de oro 10.
- **M2 · el backoff no enganchaba nunca**: `intento = 0` se reseteaba tras un `connect()`, no tras
  una *sesión*, y en `AF_UNIX` el kernel completa el `connect` aunque el servidor cierre acto
  seguido. Con el dueño rechazando por uid: 20.6 reconexiones/s indefinidamente. Ahora sólo cuenta
  una sesión que sirvió algún mensaje. (El cap del exponente sí cumplía `737dd73`.)
- **M5 · sin cota de conexiones ni corte del ocioso**: 200 conexiones parqueadas a media trama eran
  **+400 hilos** en el proceso que toca la sirena, sostenidos indefinidamente — `listen(8)` es
  backlog, no cota. Ahora `MAX_CONEXIONES=16` y corte a los 30 s del que abre, manda medio marco y
  se calla. Un suscriptor sano y CALLADO no se corta (el flujo va del dueño al cliente): anclado
  aparte, porque ese cierre habría sido peor que el agujero.
- **M9 · `PinLinkServer._al_sasmex` es el callback #0 del reflejo y no estaba aislado.**
  `gpio._dispatch_sasmex` invocaba sin `try` y `_empujar_estado` leía el estado sin guarda: si esa
  lectura reventaba, no llegaban a correr ni `supervisor._on_sasmex` (la nube) ni
  `drill.on_sasmex` (el aborto del simulacro). Las dos defensas puestas y **probadas por
  separado** — con sólo la de `gpio`, el caso del servidor quedaba verde sin medir nada.
- **M11 · D2/P2 no estaba del todo apagado**: `gpio_serve_enabled=True` de fábrica, así que TODO
  gabinete ataba el socket y registraba `_al_sasmex` como callback #0, con un coste en el hilo del
  botón de 0.093 → 1.415 ms p50 / 2.124 ms máx (con suscriptor) que **la latencia anclada del gate
  #6 no puede ver**, porque esa medición termina antes de invocar callbacks. **Decisión: apagado
  de fábrica.** Un coste sin medir dentro del camino de vida no se despliega «porque total, nadie
  se conecta», y el paso declaraba por escrito «construye el transporte, NO lo enciende». D3 sigue
  siendo UN interruptor: la puerta se abre SOLA con `GPIO_LINK=ipc`
  (`EdgeSettings.gpio_serves_pins`, derivada) y el proceso dedicado `takab-gpio` sirve siempre — un
  dueño de pines con el que nadie puede hablar no es un traspaso, es un apagón. La perilla queda
  para forzarla abierta con `GPIO_LINK=local` y diagnosticar con `takab-gpioctl`.
- **M12 · «stdlib puro» era literalmente falso**: `codec.py` importa `pydantic`. Es inocuo (la
  allowlist lo permite y **sí caza** dependencias nuevas nombrando la cadena), pero el rótulo era
  enfático y erróneo: corregido a «ninguna dependencia NUEVA» en los cuatro sitios donde estaba.

FICHADO — lo que la auditoría dejó abierto y NO se cerró aquí, con su reproducción:

5. **M1 · `action()` esquiva el códec.** `_despachar` devuelve
   `getattr(self._gpio, metodo)(**params)` tal cual, y `enmarcar` hace `json.dumps` sin el `_a_json`
   que sí protege a la instantánea. Hoy las siete acciones declaradas devuelven `None` o `dict` de
   primitivos, así que es LATENTE. *Reproducción:* declarar en `GPIO_ACTIONS` una acción octava que
   devuelva un `Enum` o un `dataclass` ⇒ `TypeError` dentro del hilo lector del servidor en vez del
   `ProtocolError` que nombra el tipo. *Cierre:* pasar el resultado por `cd._a_json` antes de
   responder.
6. **M4 · una inundación desborda la cola de 64 con sus propios errores.** Las respuestas de error
   son `critico=True` y comparten cola con los empujes: un cliente que dispara más rápido de lo que
   drena se desahucia por las respuestas *a sus propias* peticiones frenadas. Acotado por M3+M5,
   pero la cola sigue siendo una sola. *Cierre:* cola aparte para respuestas, o descartar empujes
   antes que respuestas al llenarse.
7. **M6 · bloqueo en cabeza de línea.** Mientras una acción cuelga en el dueño, `snapshot()` sigue
   FRESCO (0.427 s medido — lo refresca el hilo emisor) y **todo `apply` muere**; y nadie lo
   detecta porque `snapshot()` es justo lo que todos usan para decidir «¿está bien gpio?». M7 acota
   el daño a 5 s; la causa (una sola conexión, una petición en vuelo) sigue ahí. *Cierre:* declarar
   en la instantánea que hay una acción en curso, o un canal aparte para las que duermen.
8. **M8 · el cliente escribe sin cerrojo.** `_pedir` hace `sock.sendall` desde el hilo del
   llamador; dos escrituras concurrentes podrían intercalar marcos. LATENTE: hoy sólo hay un
   consumidor a la vez en cada camino. *Cierre:* un `Lock` alrededor del `sendall`.
9. **M10 · `READY=1` es código muerto.** Las unidades siguen en `Type=simple`, así que
   `notificar_systemd` no avisa a nadie. Va con retirar `Conflicts=` — ya estaba fichado como
   punto 3 de D2/P2 y aquí se confirma que sigue abierto.
10. **M13 · el `0700` no se impone sobre un directorio PREEXISTENTE.** `mkdir(mode=0o700)` no toca
    los permisos de lo que ya existe, y el aislamiento del socket se apoya en ese directorio (el
    `SO_PEERCRED` sí protege, así que el fallo es de defensa en profundidad, no de acceso).
    *Reproducción:* crear el directorio con `0755` antes de arrancar ⇒ sigue en `0755`. *Cierre:*
    `chmod` explícito tras el `mkdir`.

**D1 · auditoría adversarial (2026-08-08). Las seis mutaciones reclamadas se reproducen; el
gate #3 se ejecutó de verdad; y aun así hay UN BLOQUEANTE y nueve menores.**

La lente `el-edificio` intentó refutar D1 con 14 mutaciones sobre una copia completa del árbol.
Las seis que el informe reclamaba **se reproducen literalmente**, con los mismos nombres de test
y los mismos números, y una séptima más dura (`import certifi`, dependencia *ligera* que la vieja
blacklist dejaba pasar) confirma que el cambio blacklist→allowlist **no es cosmético**. Línea
base reproducida: **997 pasan**, con `GATE #3: 5/5 EJECUTADOS contra el Shake real`. Verificado
también que el cerrojo **no añade un modo nuevo de «no arranca»**: con EROFS y ENOSPC el arranque
ya moría antes de D1, porque `LGPIOFactory` necesita su FIFO en el mismo directorio.

**BLOQUEANTE · el test que se cita como prueba de que la verificación no está anclada, no ancla
nada.** `test_la_verificacion_no_esta_anclada_al_nombre_takab_edge` sigue **verde** si se
hardcodea `systemctl is-active takab-edge` **o si se borra la línea entera**: `14 passed` en los
dos casos. La causa es el doble del `systemctl` del arnés, que responde `active` y sale 0 **para
cualquier nombre de unidad**, así que el test solo puede comprobar que la cadena «takab-gpio»
aparece en el stdout — y esa cadena la imprime otro `echo` que lee el registro. Consecuencia el
día del criterio 1 de esta misma ficha: los pines pasan a `takab-gpio`, `takab-edge` sigue activo
haciendo todo lo demás, y un `deploy.sh` anclado al nombre viejo declara ✓ **midiendo a un
proceso que ya no toca el GPIO**. Es literalmente el fallo que D1.5 dice haber cerrado.

> **CERRADO (2026-08-08), y la causa no estaba donde esta ficha la situó.** `deploy.sh:386` era
> **correcto**; lo vacío era el **doble de `systemctl` del arnés**. El arreglo va ahí.
>
> Y no se usó la denylist que proponía la auditoría, sino una **allowlist**, por una razón que
> cambia el resultado: una denylist **sigue diciendo `active` por defecto para un nombre que no
> es una unidad** — que es exactamente el caso del `python -m takab_edge.gpio` suelto por SSH,
> el escenario que esta verificación existe para delatar y que **no tenía ningún test**.
>
> **La prueba del contraste, que es lo que acredita el arreglo:** con las dos mutaciones puestas
> (hardcodear `takab-edge`, y borrar el gate entero) **los 14 tests originales siguen dando
> `14 passed`**. Solo los dos tests nuevos las matan. `bash -n` salió 0 con ambas — el análisis
> sintáctico es ciego a esta clase de defecto y el sandbox que **ejecuta** el script es lo único
> que la caza.
>
> **Los tres menores de despliegue, cerrados con él:** el `sleep 3` es ahora un **sondeo acotado**
> sobre el mismo veredicto (y el arnés ganó la capacidad de simular un arranque lento: antes
> modelaba la toma del cerrojo como instantánea, así que **ningún test podía distinguir sondeo de
> `sleep`**); un registro mudo con el cerrojo tomado **avisa y apunta al disco** en vez de
> abortar, pero se sigue abortando si `/proc` **desmiente** al registro; y quedaron ancladas las
> ramas de ilegible, `/proc` y el «gana la última».
>
> **Decisión que conviene conocer:** una unidad que systemd da por muerta **se sondea** hasta
> agotar el plazo en vez de abortar en el acto. Cuesta 45 s en un gabinete ya roto, y compra que
> un futuro `Type=notify` —unidad en `activating` mientras ya sostiene el cerrojo— no produzca un
> **aborto falso**: y un aborto falso empuja a revertir, revertir es reiniciar, y reiniciar mueve
> `GAS_VALVE` y `DOOR_RETAINER`.

**Los dos menores que hay que cerrar ANTES de la ventana en el Pi:**
1. **El `sleep 3` mide ahora algo que ocurre mucho más tarde.** La verificación pasó de «systemd
   forkeó» (t≈0) a «`gpio._on_start` corrió su primera sentencia», con el mismo plazo de un solo
   disparo y sin reintento. Reproducido: un gabinete **sano** que tarda 4 s se reporta como
   «NADIE es dueño de los pines… el gabinete NO está protegiendo». Medido exec→cerrojo en 0.60 s
   (x86, dev) y ~1.0 s con los imports de producción; **el margen en el Pi 4 no es medible sin el
   Pi**, que es justo el argumento para **sondear en vez de dormir**. El daño de segundo orden es
   el peor: entrena al operador a ignorar la única comprobación que dice si la sirena tiene dueño
   — y revertir es reiniciar, y reiniciar mueve `GAS_VALVE` y `DOOR_RETAINER`.
2. **Las dos mitades de D1 se contradicen sobre el registro.** `gpio` lo declara **informativo** y
   conserva la propiedad cuando su E/S falla (anclado por test); `deploy.sh` convierte ese mismo
   registro vacío en un **aborto** que acusa a «un `flock` suelto de una sesión SSH». Un gabinete
   con `/var/lib/takab` lleno protege perfectamente y el despliegue lo declara secuestrado,
   mandando al operador a buscar un intruso que no existe en vez de al disco.

**Menores de seguridad en el propio `gpio` (no de despliegue):**
3. El rescate del arranque fallido **suelta el cerrojo sin cerrar los relés ni pasar por
   `drive_all_safe()`**: deja el cerrojo LIBRE mientras el proceso sigue gobernando cinco pines,
   con gas y retenedores **energizados**. Es exactamente la ventana que `_on_stop` documenta y
   ordena su `finally` para evitar.
4. Si al perfil `failsafe` le falta un canal que **no** sea de los primeros, el bucle de
   construcción **ya energizó los anteriores —`GAS_VALVE` incluido—** antes de tronar, y la ruta
   de fallo no llama `drive_all_safe()` ni `close()`. El único test del caso quita `GAS_VALVE`
   (posición 3) y **solo mira ese pin**.
5. El nuevo fallo duro de `_failsafe` **no tiene guarda propia**: nada ancla
   `LOCAL_RELAY_CHANNELS ⊆ EdgeSettings.failsafe`, y `TAKAB_EDGE_FAILSAFE` **sustituye** el
   diccionario en vez de fusionarlo — o sea que una variable de entorno puede dejar un canal de
   relé sin modo declarado y tumbar el arranque.

   > **RESUELTO (2026-08-08) fusionando, no fallando al construir — y eso contradice la
   > preferencia con la que se encargó la tarea.** La razón que la cambió: `EdgeSettings` no es
   > solo el `edge.env`, es también **el documento firmado** que aplica
   > `ConfigStore.apply_signed_update` con `model_validate_json`, y `_high_water` solo sube tras
   > validar. Lanzar en la construcción tiraría el documento **entero** —umbrales,
   > `command_enabled`, `cloud_admin_state`— y se reintentaría idéntico **para siempre**: es
   > exactamente el fallo que este repo ya razonó por escrito al tipar `cloud_admin_state` como
   > `str` en vez de `Literal`. Y en el gabinete, «fallar al construir la config» y «fallar al
   > tocar un pin» tienen el **mismo desenlace físico** (`gpio` es `critical=True`): edificio sin
   > alertamiento. Fusionar es lo único que hace el fallo duro **inalcanzable por configuración**,
   > que era lo que la auditoría pedía.
   >
   > **No resucita lo que D1.2 quitó:** aquel default respondía `NORMALLY_OPEN` a **todo** —lo que
   > invertía gas y retenedores—; `DEFAULT_FAILSAFE` da a cada canal **su** modo, que es propiedad
   > del actuador, no del sitio. Anclado con un test que explota el hueco a propósito:
   > `model_copy(update=...)` **no pasa por validadores**, así que un perfil mutilado sigue siendo
   > construible y `_failsafe` sigue tronando. Nadie puede borrar el gate de D1.2 alegando que la
   > configuración ya lo garantiza.

**Menores que condicionan D3:**
6. **El cronómetro de latencia para cuando `drive_low()` retorna**, no cuando el quinto pin llega
   a su nivel de protección. Con la actuación posterior en un hilo sin `join`, el test pasa
   reportando **1.3 ms** y el guardarraíl anti-teatro no lo ve. D3 mueve justamente esa actuación
   al otro lado del socket: sería reintroducir un nivel más arriba el defecto que D1.4 existe
   para corregir.

   > **CORRECCIÓN (2026-08-08): la premisa de este punto era falsa, y medirla lo demostró.**
   > Se dio por hecho que sondear los cinco pines bastaría para cazar el hilo sin `join`.
   > **No basta:** con el hilo suelto **los cinco pines llegan igual, en 1.0 ms**, así que un
   > cronómetro honesto mide 1.0 ms y **aprueba con razón** — el hecho físico ocurrió dentro del
   > presupuesto. Lo que el fire-and-forget se lleva por delante no es la latencia: son los
   > **`ActuatorAck`**. Una actuación disparada y olvidada llega a los pines igual de rápido y
   > deja a `_act_and_publish` sin saber si un canal falló y a la nube sin acuse.
   >
   > Por eso el arreglo tiene **dos mitades**: el reloj para en el instante eléctrico de los
   > cinco pines (con `sleep(0)` en cada vuelta, cediendo el GIL **a propósito**, para que una
   > implementación en hilo o socket quede *medida y no penalizada*), y la cadena **rinde
   > cuentas**: 5 de 5 acuses, fuera del cronómetro porque encolar acuses no es §4.3.
   >
   > La alternativa —exigir que la cadena termine dentro de la llamada— **prohibiría D3 en vez
   > de medirlo**. Y con la travesía degradada a 250 ms el número sube y **lo dice**:
   > «tardó 250.7 ms, de los cuales 249.9 ocurrieron DESPUÉS de que `drive_low()` retornara».
   > Cuando D3 mueva la actuación al socket, **este test no hay que reescribirlo**.
7. **El presupuesto de dependencias solo censa el montaje de DEV.** Una dependencia de terceros
   importada en la rama de **producción** (`dev_mode=False`) es invisible para la allowlist — y
   producción es justamente el proceso que corre en el Pi.

**Menores de forma:** otras tres ramas del paso 7 y el «gana la última» del registro se pueden
borrar o invertir con los 14 tests en verde (solo las dos ramas de `flock` están ancladas); y el
docstring del cerrojo derivado afirma que dos unidades con `dev_mode` mal puesto «seguirían
colisionando», que es **falso** — `takab-edge` lleva `PrivateTmp` y `takab-gpio` no.

*Corrección factual al informe de implementación, sin consecuencia:* `_unidad_de_este_proceso()`
no lee `/proc` — lee `TAKAB_GPIO_UNIT` o `sys.argv[0]`; `/proc` solo lo usa `_proceso_vivo()`.

### [x] T-2.170 · El guardián del presupuesto del camino de vida es intermitente en CI — `SOFTWARE` · COMPLETA (2026-08-26) · **REABIERTA Y CERRADA DEL TODO (2026-08-30)**

> ### ⚠️ Estuvo marcada COMPLETA cuatro días y le faltaba la mitad
>
> El 2026-08-30 enrojeció **`test_gpio_link.py::test_el_reflejo_sasmex_no_cruza_la_costura`**
> con **161.0 ms** — contra los 165.8 ms que habían motivado esta ficha. El gemelo del gate
> #6 tenía **exactamente el mismo defecto** que se arregló aquí: una sola muestra de reloj de
> pared asertada dura contra los 100 ms. Se arregló `test_e2e.py`, se dio la ficha por
> cerrada, y nadie buscó el segundo sitio donde vivía el mismo patrón.
>
> **Y el coste ya se pagó**: el rojo se diagnosticó y se **relanzó el CI**, que es palabra por
> palabra el reflejo que esta ficha declara inaceptable («enseña a re-lanzar el CI rojo del
> camino de vida»). El diagnóstico era correcto —el mismo commit había pasado en la corrida
> anterior y el commit acusado solo añadía una bandera a una lista de argumentos, lejos del
> GPIO— pero eso es justo lo que se va a poder decir siempre.
>
> **La lección, que es más general que este test:** una ficha que arregla un patrón tiene que
> declarar **dónde más vive ese patrón**, o se cierra sobre la primera instancia. Aquí bastaba
> con buscar el otro `< 0.100`.
>
> **Lo corregido (misma receta, sin tocar el presupuesto):** mejor de `INTENTOS_DE_MEDICION`,
> premisa re-comprobada en cada intento, aviso cuando hiciera falta reintentar. Con dos
> diferencias que impone la premisa de ESE test y quedan escritas en él:
>
> * **el rearme no puede ser `local_api.reset_alert()`**, porque `_accion` es la única puerta
>   del panel hacia los pines y **cruza la costura**, que ahí está muerta a propósito. Se va al
>   mismo destino sin el tramo roto: `gpio.reset()`;
> * **las afirmaciones estructurales se mudan DENTRO del bucle.** Detrás no habría nada que
>   mirar: el rearme devuelve los cinco relés a reposo, así que un `assert ... is
>   active_energized(...)` puesto después interrogaría a un gabinete desarmado.
>
> **El presupuesto y el número de intentos se IMPORTAN de `tests/test_e2e.py`**, no se
> teclean: dos copias del 100 divergirían, que es el defecto que esta misma ficha ya dejó
> escrito para el conftest.
>
> **Test del test, otra vez por mutación en las dos direcciones:**
>
> | mutación | serie medida | veredicto |
> |---|---|---|
> | *degradación real* (60 ms por canal en `_apply`) | `143.2 / 128.3 / 127.8 / 128.5 / 128.5 ms` | **enrojece** |
> | *pico único* (150 ms una sola vez en `_dispatch_sasmex`) | `163.9 / 4.2 ms` | pasa **con aviso** |
>
> La **serie plana** es la firma de la regresión; el pico aislado, la del ruido. Y los 163.9 ms
> del pico simulado caen casi exactos sobre los **161.0 ms** que enrojecieron CI de verdad.
>
> **La segunda mutación pagó por sí sola:** la de degradación destapó un fallo *en el propio
> arreglo* — al rearmar también tras el último intento, el test enrojecía por el aserto
> equivocado (`siren NO quedó en su nivel de protección`) en vez de por la latencia. Un
> arreglo del instrumento que no se mutara habría entrado con ese defecto dentro.

- **Componente:** edge (`tests/test_e2e.py` **y `tests/test_gpio_link.py`**) + CI · **Sale de:** `main` en rojo el 2026-08-26 (run `32937425976`) por un commit que solo tocaba documentación.
- **Lo medido, no lo supuesto:** `test_latencia_contacto_wr1_a_los_cinco_reles_bajo_presupuesto` declaró **165.8 ms** contra un presupuesto de <100 ms. **El mismo commit, relanzado sin tocar una línea, pasa.** Uno de cada ocho runs recientes. Y el propio mensaje del test dice dónde estuvo el tiempo: **«0.0 ms ocurrieron DESPUÉS de que `drive_low()` retornara»** — o sea que el retraso no está en la cadena, está en el planificador del runner compartido.
- **Por qué no es un test flaky más.** Éste guarda la **regla de oro 1**: el camino SASMEX→actuador. Un guardián intermitente sobre el camino de la sirena no solo falla: **enseña a re-lanzar el CI rojo del camino de vida**, que es exactamente el reflejo que no puede existir en este proyecto. El día que la latencia se rompa de verdad, el rojo va a parecer «el de siempre».
- **⚠️ LA CORRECCIÓN PROHIBIDA:** subir el presupuesto de 100 ms. El número no sale de lo que el CI consigue, sale de `blueprint §4.3`. Un presupuesto que se ajusta al instrumento deja de ser un presupuesto. Tampoco vale saltar el test en CI: entonces nadie vigila la latencia hasta la siguiente visita al gabinete.
- **El diagnóstico del instrumento:** el reloj de pared sobre un runner compartido mide *código + planificación*, y el ruido de planificación **solo suma**. Por eso una sola medición alta no distingue «el código se degradó» de «el runner estaba ocupado», mientras que la **mejor de N** sí: si el código se degradó, ni la mejor llega.
- [x] La medición se repite hasta **`INTENTOS_DE_MEDICION = 5`** y el veredicto se da sobre el **mejor**, con `PRESUPUESTO_S = 0.100` **INTACTO**. El rearme entre intentos usa el camino que `test_manual_reset_closes_alert_end_to_end` ya acredita, y **la premisa se re-comprueba en cada intento**: si el rearme no devolvió los cinco relés a reposo, el test falla ahí en vez de medir un gabinete ya protegido y cantar 0 ms.
- [x] **La serie se imprime siempre**, también en verde, por el `pytest_terminal_summary` que ya rotula el gate #3: `CAMINO DE VIDA (§4.3, <100 ms): mejor 1.7 ms de 1 intento(s)`. El umbral **viaja con la serie** en vez de teclearse en el conftest — dos copias del 100 divergirían y el resumen acabaría declarando un umbral que no se aplicó.
- [x] Con más de un intento el test **avisa aunque pase** (`UserWarning`, visible en el resumen de CI). Un instrumento que pide reintentos es un dato sobre el instrumento.
- [x] **Test del test, por mutación en las DOS direcciones** —que es lo único que separa esto de aflojar el umbral:
  - *Degradación real* (30 ms por canal inyectados en `GpioController._apply`): los 5 intentos salen **226.9 / 219.3 / 219.0 / 219.1 / 219.0 ms** y el test **enrojece**. La serie plana es la firma de una regresión; el ruido no se repite igual.
  - *Pico único* (150 ms una sola vez en `_on_contact_closed`): **165.9 ms → 5.9 ms**, pasa con el aviso. El pico simulado cayó casi exacto sobre los **165.8 ms** que enrojecieron `main`.
- **No sustituye a la acreditación física.** La medida que vale sigue siendo la del gabinete con el WR-1 real —**6.65 ms y 4.16 ms**, dos órdenes de magnitud de margen—; esto solo evita que el guardián de CI se corroa entre visitas.

### [ ] T-2.172 · El fail-open del modo prueba **grita 24 veces** en cada ventana de mantenimiento — `SOFTWARE`
- **Componente:** edge (`supervisor.py:_modo_prueba_activo`) · **Sale de:** el despliegue con
  `--ventana-de-mantenimiento` del 2026-08-30 (release `20260830T222850Z-71ac7df`), medido en el
  gabinete real.
- **Lo medido.** Mientras `takab-gpio` se reinicia —unos 3 s— `gpio_link.snapshot()` lanza
  `GpioLinkUnavailable` y `_modo_prueba_activo` toma su camino *fail-open*. Se registró **24
  veces**, cada una con este texto y un `event_id` distinto:
  > `no se pudo leer el modo prueba del WR-1; se PUBLICA a la nube. Fail-open DELIBERADO: esto
  > puede abrir incidente y disparar la push CRISIS a los teléfonos del sitio…`
- **Y no publicó nada.** Verificado en la nube, no inferido: **`0` incidentes** abiertos en la
  ventana. La razón está tres líneas más abajo en el mismo método —`if decision.tier is
  Tier.NORMAL: return`— y el gabinete estaba en reposo, así que todas las decisiones eran
  `NORMAL` y ninguna llegó a `EVENTS_TOPIC`.
- **Por qué esto importa y no es cosmética.** El mensaje describe **el peor caso** como si
  fuera lo ocurrido, en `ERROR`, veinticuatro veces seguidas, **en cada ventana de
  mantenimiento** —que es justo cuando alguien está mirando el journal—. Es la misma patología
  que [`T-2.170`](TASKS.md) señaló para el CI: **una señal que da el grito máximo en la
  situación más rutinaria enseña a ignorarla**, y el día que el fail-open sí publique un
  evento real, esas líneas van a parecer «las de siempre».
- **⚠️ La corrección prohibida:** bajar el nivel del log o quitar el aviso. El fail-open es
  correcto —callar un sismo real es peor que un incidente de más— y **tiene que verse**.
- **Criterios de aceptación:**
  - [ ] El mensaje distingue **lo que va a pasar de verdad** de lo que podría pasar: con
        `Tier.NORMAL` no se publica nada y el texto no puede decir que sí.
  - [ ] El reinicio del dueño **no produce 24 líneas**: o se agrupan mientras dura la
        indisponibilidad, o se registra una al entrar y una al salir con el conteo.
  - [ ] **No se resuelve esperando al dueño**: `_modo_prueba_activo` no puede bloquear la
        actuación, y esa es la razón de que falle abierto en primer lugar.
  - [ ] Un test que ejerza la ventana: costura caída durante N ticks con tier `NORMAL` ⇒
        **cero publicaciones** y **una sola** línea de aviso.

### [x] T-2.171 · Nada comprueba que lo que se despliega sea lo que está en `main` — `SOFTWARE` · COMPLETA (2026-08-27)
- **Componente:** deploy (`cloud` + `edge`) + Makefile · **Sale de:** dos despliegues del 2026-08-27, medidos, no supuestos.
- **Lo que pasó, dos veces el mismo día y por la misma causa.** El árbol estaba en `feat/landing-v2-telemetria` y de ahí salieron:
  1. un `terraform apply` que **no aplicó** el topic `takab/audit` ni su regla IoT — la rama no los tenía;
  2. un `make cloud-deploy` que puso en la nube el build `abf4490` con esquema `0051`, cuando `main` estaba en `a60bc10` con la migración `0052`. La tabla no se creó y el handler no llegó.
- **Lo peor no es que pasara: es que TODO salió en verde.** Cada guardia hizo bien su trabajo y ninguna podía verlo:
  - El **gate de despliegue** (`T-2.153`) comprueba que la API conteste, que corra **el commit que se desplegó** y que su esquema esté al día. Las tres eran ciertas — del commit equivocado.
  - La **alarma de deriva de esquema** compara lo que la imagen espera contra lo que la base tiene. También coincidían: `0051` y `0051`.
  - El **plan de Terraform** compara el código contra el estado. Sin el cambio en el código, «sin cambios» es la respuesta correcta.
  - Un gate puede verificar que desplegaste **lo que pediste**; ninguno de estos puede saber que **querías otra cosa**.
- **El precedente ya está en el repo, sin aplicar donde más cuesta.** `deploy/landing/deploy.sh:37,39` ya se niega con árbol sucio y con `main` sin pushear. La landing —que sirve HTML— tiene la guardia; la nube y **el gabinete** no.
- **Criterios de aceptación:**
  - [x] **`HEAD` tiene que estar EN `main`.** ⚠️ **Corregido respecto de lo que pedía esta
        ficha**, que decía «contenido en `origin/main`, no igual» para no prohibir el rollback.
        Al implementarlo resultó que **el rollback no necesita mover `HEAD`**: se hace con
        `CLOUD_TAG=<sha-anterior>` desde `main`, porque la etiqueta es sobreescribible (`?=`) y el
        gate del despliegue compara contra ella. Así que la contención sobraba, y con ella la
        superficie de «estoy en un commit suelto que casualmente es de main». Se implementa la
        letra de A-1 —`rama == main`— que además es lo que ya hacía la landing: una regla, una
        forma.
  - [x] **`fetch` antes de juzgar**, y si falla la guardia **se niega** en vez de dar por bueno lo
        que no pudo comprobar. Y lo mismo con la mitad del CI: sin `gh` no se puede mirar, así que
        se sigue —negarse dejaría sin desplegar a una máquina sin `gh`, decisión más grande que
        esta ficha— pero **se declara en voz alta que A-1 se aplicó A MEDIAS**. Un fallback que se
        hace pasar por un OK es el defecto, no la falta de red.
  - [x] **Escotilla explícita** `--desde-esta-rama` (o `TAKAB_DEPLOY_RAMA_LIBRE=1`), que imprime
        la rama y el sha y dice que **no es un despliegue reproducible**.
  - [x] **El rechazo enumera lo que el despliegue se dejaría fuera** (`git log HEAD..origin/main`),
        no un «no estás en main». Probado contra el escenario real: la rama del 27-ago produce una
        lista que empieza por `T-2.86.a` — exactamente lo que se quedó fuera aquel día.
  - [x] **También el gabinete**, con `guarda_de_rama "edge" si`: el `si` conserva su tolerancia
        DECLARADA al árbol sucio (`--dirty`, para depurar en sitio). Rama y limpieza son dos
        preguntas distintas y solo se añadió la primera.
  - [x] **`make cloud-apply`**, con la misma guardia **y** el rechazo si falta
        `local.auto.tfvars` — el fichero gitignored sin el cual todo lo que lleva `count` evalúa a
        cero y el plan propone destruir los tres DKIM, DMARC, MAIL FROM y la consola.
  - [x] **12 tests de CONDUCTA**, no de lectura: la guardia se corre contra repos de mentira con
        su `origin`, y lo único que se juzga es su código de salida. Cubren main limpia, rama de
        trabajo, `main` sin pushear, CI en rojo, árbol sucio con y sin tolerancia, la escotilla y
        el aviso de «A MEDIAS» sin `gh`. Más un **censo**: todo `deploy/*/deploy.sh` del árbol
        tiene que pasar por la guardia — enumerar los tres a mano dejaría fuera al cuarto.
        Verificado por mutación: quitar la guardia del gabinete enrojece el censo, y aceptar
        cualquier rama enrojece dos tests de conducta.
        **Trampa medida al escribirlos:** el arnés filtraba `gh` del `PATH` quitando su
        directorio… que en esta máquina es el mismo de `bash`. Los tests morían con
        `FileNotFoundError: 'bash'`. Se construye un **PATH mínimo** con enlaces a lo que la
        guardia usa, y un `gh` de mentira cuyo veredicto decide el test.
- **Lo que NO arregla, y sigue siendo verdad:** con la escotilla puesta, equivocarse de rama sigue siendo posible. Lo que cambia es que ya no se puede hacer **sin decirlo**.
- **Y lo que se llevó por delante de paso:** la regla A-1 tenía UNA implementación en todo el repo —la de la landing, que sirve HTML— y ahora es un helper compartido (`deploy/lib/guardas.sh`) que usan los tres despliegues y el `apply`. Tres copias de la misma regla acaban divergiendo, y la que divergiría sin ruido es la que nadie mira.

### [~] T-2.71 · Ventanas de mantenimiento — `SOFTWARE` · núcleo COMPLETO, gates AWS abiertos
- **Componente:** api + web + edge · **Depende de:** T-2.70
- **Criterios de aceptación:**
  - [x] **Silencia alarmas de operación, JAMÁS la actuación.** Anclado por test que MIDE
        relés: cablear una ventana al reflejo pone en rojo dos tests que leen
        `relay_state(...).energized` de sirena y estrobo, no aserciones.
  - [x] La consola lo dice mientras dure, **y dice la verdad**: el banner afirmaba
        «ALARMAS SILENCIADAS» incondicionalmente, incluso con el servidor declarando `0/N` —
        que es el estado de TODA ventana con el default de producción. Ahora distingue
        silenciadas todas / algunas / ninguna, y además **silencio MEDIDO de silencio
        SUPUESTO** (`mute_verified`): un acuse a ciegas se pinta `SIN ACUSE: SE SUPONEN
        MUDAS, NADIE LO MIDIÓ`, no como un éxito.
  - [x] **Vencimiento por DOS candados independientes**: predicado SQL que no necesita worker
        + `Duration` que expira en AWS. Falla hacia «la ventana se cierra».
- **`[ ]` PENDIENTE — no bloquea el núcleo de seguridad, y por eso la ficha queda `[~]`:**
  - [ ] **Superficie de APERTURA en la consola.** La API existe y está probada; la web solo
        LEE y CIERRA. Falta el modal en `/fleet` con motivo obligatorio.
  - [ ] **`HUMANO-AWS`**: confirmar que `PutAlarmMuteRule` está disponible en `us-east-2` con
        las credenciales del proyecto **y su coste** (el presupuesto son $50/mes); `terraform
        apply` de los tres statements IAM; y `TAKAB_API_OPS_MUTING_ENABLED=true` en
        `deploy.sh`. **Está APAGADO por defecto a propósito**: con él apagado la ventana se
        registra y declara `0/N SILENCIADAS`, que es honesto.
  - [ ] **`HUMANO-AWS`**: medir qué pasa cuando la ventana **VENCE SOLA** — forzar `ALARM` con
        `set-alarm-state`, dejar que expire por `Duration`, y ver si llega el correo. El
        código asume que NO llega; si se confirma, hay que cerrar la ventana activamente antes
        de que expire.
- **Fuga cross-tenant CERRADA, y era peor de lo reportado** (regla de oro 5): la ventana se
  archivaba bajo el tenant del **operador**, no del gabinete intervenido. No se quedaba en «el
  dueño no la ve»: con un grant de metadatos (T-1.73), un `tenant_admin` **llegaba a silenciar
  de verdad las alarmas del edificio de otro cliente**. Anclado con el test cross-tenant que
  debe fallar.
- **Una cita inventada sostenía la decisión central.** La elección de la mute rule sobre
  `actions_enabled=false` se justificaba con una frase **atribuida a la documentación de AWS
  que no está en la documentación de AWS**. Se borró de los tres sitios y la decisión se
  re-tomó contra el **modelo de servicio del CLI instalado**, legible sin credenciales: la
  razón que sí se sostiene es que `Schedule.required == ["Expression","Duration"]`, o sea que
  **la regla no puede no vencer**. Las citas verdaderas quedan ancladas al modelo por test,
  para que la siguiente no pueda volver a ser inventada.

**Implementado (2026-08-06) — mecanismo elegido y lo que se REFUTÓ por el camino.**

`POST/GET /maintenance-windows` + `POST /maintenance-windows/{id}/close`. El silencio real lo
aplica una **CloudWatch alarm mute rule** (`api/src/takab_api/ops/muting.py`), no
`actions_enabled` ni dejar de publicar la métrica. Apagar la métrica **pagina** en dos de las tres
alarmas por gabinete (`gateway_offline` está en `breaching`, `ghost_gateways` en `missing` **con**
`insufficient_data_actions`), o sea lo contrario de lo que se busca.

**La decisión se volvió a tomar (2026-08-07)** porque la razón que la sostenía —«al terminar la
ventana CloudWatch RE-DISPARA las acciones silenciadas», entrecomillada como cita literal de la
documentación de AWS— **no está en la documentación de AWS**. Se borró de los tres sitios donde
estaba escrita. Con lo que sí se puede comprobar sin credenciales (el modelo de servicio del CLI
instalado, `ops/muting.CLI_SERVICE_MODEL`), la mute rule **sigue ganando**, por otras razones:

1. **`Schedule` declara `required = ["Expression", "Duration"]`**: una mute rule no puede existir
   sin vencimiento, y lo enforza AWS. `actions_enabled=false` no tiene vencimiento de ninguna
   clase y aquí no hay worker que lo repare (a propósito). **Es la razón decisiva.**
2. **`DeleteAlarmMuteRule`**, literal: *«any alarms that are currently being muted by that rule
   are immediately unmuted. If those alarms are in an ALARM state, their configured actions will
   trigger. This operation is idempotent.»* Cerrar a mano hace que el correo pendiente SALGA;
   volver a poner `actions_enabled=true` no promete nada equivalente.
3. **El permiso se comprueba sobre cada alarma apuntada** (ver abajo), así que IAM queda como
   segunda línea. La vía `actions_enabled` pasaría por `PutMetricAlarm`, cuyo permiso además deja
   reescribir umbral, métrica y acciones: radio de daño incomparable para lo mismo.

**El agujero que deja la cita borrada, dicho en voz alta:** qué pasa cuando la ventana **vence
sola** no está documentado en ninguna parte legible offline. Se trata como que NO re-dispara —las
acciones de CloudWatch disparan en transición, y esa transición ya ocurrió con la regla activa—,
así que una ventana dejada expirar puede perder el correo igual que `actions_enabled`. Sigue
ganando porque el daño está **acotado a 4 h** y la alarma queda visible en ALARM, mientras que
`actions_enabled=false` no tiene techo. **Consecuencia operativa: cerrar la ventana, no dejarla
expirar** — es la única vía con re-disparo documentado. Medirlo contra la cuenta real es
`HUMANO-AWS`.

Qué se puede callar, y qué no (`ALARM_CATALOG`, derivado del Terraform por test):

| Alcance | Alarmas | Rol |
|---|---|---|
| Gabinete | `gateway_offline`, `sensor_mute` **del gabinete intervenido** | `maintenance_window` (superadmin/tenant_admin) |
| Plataforma | `ec2_status`, `ec2_cpu` | `platform_maintenance_window` (**solo** superadmin) |
| **JAMÁS** | `dlq_depth`, `iot_rule_errors` (instrumento del canary de T-2.70), `ghost_gateways` (vigila al vigilante) | — |

**Tres correcciones al diseño previsto, verificadas de primera mano** en el modelo de servicio del
CLI 2.35.16 instalado (`.../botocore/data/cloudwatch/2010-08-01/service-2.json`), que se lee sin
credenciales y sin red — es el archivo del que el propio CLI saca el contrato, no una página que
lo describe:

1. `Rule.Schedule.Expression` es **OBLIGATORIA** (`required = ["Expression","Duration"]`). No se
   puede mandar solo `Duration`. Admite `cron(...)` recurrente —que **no expira jamás** sin
   `ExpireDate`— y `at(yyyy-MM-ddThh:mm)` de una sola vez. Se emite siempre un `at()` derivado del
   reloj, nunca aceptado de nadie.
2. `DeleteAlarmMuteRule` **existe** y es idempotente: desilencia en el acto y, si la alarma quedó
   en ALARM, sus acciones disparan. Por eso el cierre anticipado va por ahí — la dirección segura
   es que el correo pendiente SALGA.
3. `cloudwatch:PutAlarmMuteRule` se comprueba *«on two types of resources: the alarm mute rule
   resource itself, and each alarm that the rule targets»*. Eso convierte a IAM en segunda línea
   de defensa: las tres intocables no están en la política y AWS denegaría el intento aunque el
   código fallara (`modules/database/tests/mute_rules_iam.tftest.hcl`).

**La ventana es del edificio INTERVENIDO, no de quien interviene (regla de oro 5).** La fila se
archivaba bajo `claims.tenant_id`, o sea el del OPERADOR: el dueño del edificio cuyas alarmas
quedaban mudas **no la veía**, y un tenant ajeno **sí, y podía cerrarla**. Peor: con un grant de
metadatos (T-1.73) `gateways_read` deja VER inventario ajeno, así que un `tenant_admin` llegaba a
**silenciar de verdad las alarmas del gabinete de otro cliente**. El arreglo separa *quién opera*
de *a quién pertenece lo intervenido*: `tenant_id` sale de la fila del gabinete, el operador queda
en `opened_by` + `meta.operator_*`, y solo un rol interno (`takab_*`) cruza de tenant — que es el
caso legítimo del soporte que va físicamente al gabinete de un cliente.

**Un éxito parcial ya no se reporta como fracaso total.** Si AWS fallaba DESPUÉS del
`PutAlarmMuteRule`, las alarmas quedaban MUDAS y la fila declaraba `0/N SILENCIADAS` con
`mute_rule = NULL`: la consola afirmaba que la vigilancia seguía viva **con la vigilancia
apagada**, y REABRIR VIGILANCIA era un no-op durante hasta 4 h porque se había perdido el nombre
de la regla. Ahora, ante la duda, se asume el estado más peligroso —silenciado— y se conserva lo
necesario para deshacerlo; la columna nueva `mute_verified` (migración `0031`) marca esas cifras
como SUPUESTAS para que nadie las lea como medidas. Solo se declara `0/N` cuando está medido: sin
cliente de CloudWatch, cuando AWS **contestó** con un 4xx, o cuando la petición **ni salió de la
máquina** (ver la reauditoría de abajo). Y si lo que falla es la escritura de la FILA, el silencio
se DESHACE: alarmas mudas sin registro son peores que una ventana que no se pudo abrir.

**Vencimiento (criterio 3): DOS candados independientes y ningún job.** `active` es un predicado
SQL (`closed_at IS NULL AND now() < starts_at + duration`), calcado de `drills` —"sin worker de
cierre"— con `CHECK (duration_s BETWEEN 300 AND 14400)` en el DDL; y AWS expira la mute rule por
su `Duration`. La pregunta "¿y si el job de vencimiento muere?" se contesta borrando el job. El
tope de la casa son **4 h**, muy por debajo del P15D de AWS: dentro de la ventana la alarma está
muda en los TRES estados.

**Criterio 4 medido con RELÉS, no afirmado.** Dos vectores en `edge/tests/test_supervisor.py`: la
ventana en la config de ARRANQUE (el camino probable — `GpioController` lee `self.settings`, que
desde T-2.34 se hidrata de una caché firmada en disco) y en la config VIVA de la nube. Los dos
miden `is_activated` **y** `relay_state(...).energized` de sirena y estrobo.

**PENDIENTE `HUMANO-AWS` antes de confiar en esto en producción:** (a) confirmar que
`PutAlarmMuteRule` está disponible en us-east-2 con las credenciales del proyecto y su coste (no
verificable offline; budget $50/mes); (b) `TAKAB_API_OPS_MUTING_ENABLED=true` en
`deploy/cloud/deploy.sh` — **apagado por defecto**, y con él apagado la ventana se registra pero
declara `0/N SILENCIADAS`, que es la verdad. (c) La recomendación del reconocimiento sigue en
pie: correr el canary de T-2.70 **sin ventana** la primera vez. Los umbrales predicen que un
reinicio de `takab-edge` (segundos) no llega a disparar `sensor_mute` (>120 s) ni
`gateway_offline` (>10 min); si suenan, el hallazgo no es que falte una ventana — es que la
actualización está tumbando el camino de detección, y la ventana convertiría esa señal en
silencio. (d) **Medir qué pasa al VENCER la ventana sola** (la pregunta que dejó abierta la cita
borrada): forzar una alarma a ALARM con `set-alarm-state` estando la mute rule activa, dejarla
expirar por `Duration`, y ver si llega correo. Si no llega —que es lo que este código asume—, el
cierre explícito deja de ser cortesía y pasa a ser obligación de runbook; si llega, se puede
escribir por fin como hecho medido, con fecha, igual que se hizo con `missing` el 29-jul-2026.

**Reauditoría del 2026-08-07 · la consola pintaba la suposición como medida (lote C).** El
servidor había ganado `mute_verified` justamente para separar *silenciado medido* de *silenciado
supuesto*, y `grep -rn mute_verified web/` devolvía **CERO**: el arreglo no llegaba al operador,
que es quien decide si se fía. Tres cierres en `web/`:

- **El acuse A CIEGAS se pintaba como uno medido.** Cuando el `PutAlarmMuteRule` sale y el
  `GetAlarmMuteRule` que lo comprueba no se puede leer, el servidor rellena `silenced = requested`
  **a propósito** (asume el estado peligroso y conserva `mute_rule` para deshacerlo), así que el
  payload llega con la MISMA forma que un éxito: `2/2`, `missing 0`, regla con nombre. `MuteOutcome`
  gana el miembro `assumed`, que gana a las cifras: no imprime el molde de lo medido
  (`N/M ALARMAS SILENCIADAS`) sino `N ALARMAS PEDIDAS · SIN ACUSE: SE SUPONEN MUDAS, NADIE LO MIDIÓ`,
  y el rótulo CORTO de la tarjeta de flota queda reservado a la afirmación cierta.
- **`/fleet` se tragaba el fallo de lectura de las ventanas.** Tomaba `useMaintenanceWindows(...)`
  y usaba solo `items`: con la llamada fallando ninguna tarjeta llevaba rótulo y la pantalla
  afirmaba en silencio «aquí no hay ninguna ventana abierta» — el cero tranquilizador de T-2.59,
  reproducido en la pantalla que este mismo lote acababa de tocar. Ahora el `readError` se declara
  encima de la reja, con `REINTENTAR VENTANAS` propio (el del `StateFrame` reintenta la FLOTA, que
  no es lo que falló) y distinguiendo «no sé» de «los rótulos son el último dato conocido».
- **El «guardia de clase» de `maintenance.test.ts` era teatro:** se vendía como exhaustivo e
  iteraba **cuatro fixtures escritas a mano**, así que `assumed` entró sin que se quejara nadie.
  Se invirtió la relación —`MUTE_OUTCOMES` es el dato y `MuteOutcome = (typeof MUTE_OUTCOMES)[number]`—
  y el guardia recorre la lista con tres candados de distinta naturaleza: `Record<MuteOutcome, …>`
  (lo caza `tsc`, que no bloquea merges), las claves de esa tabla contra la lista **en ejecución**
  (vitest, que sí bloquea) y una frase propia y no vacía por miembro en las tres funciones.
  Comprobado con un miembro falso: caen 4 tests y 3 errores de tipo, dos de ellos por los `switch`
  incompletos.
- **Y un cuarto de la misma familia, encontrado al cerrar los otros tres y ANCLADO en vez de
  perseguido:** un `REABRIR VIGILANCIA` que FALLA. El banner ya pintaba el error de la mutación,
  pero no había nada que lo sujetara —borrar ese `error !== null` no ponía roja ninguna prueba—, y
  es la dirección más cara de todas: `DeleteAlarmMuteRule` es la única vía con re-disparo
  documentado, así que un fallo tragado deja al operador convencido de haber devuelto la vigilancia
  mientras el edificio sigue mudo hasta que la regla expire sola (hasta 4 h). El test comprueba
  además que la ventana NO desaparece del banner por haber intentado cerrarla.

**Reauditoría del 2026-08-07 · el sistema afirmaba como medido lo que solo suponía (lote B, en
`api/`).** Los tres primos hermanos que quedaban vivos del mismo defecto, ninguno visible desde el
lote anterior porque los tres estaban en el otro extremo del ciclo o debajo de la prosa:

- **El CIERRE que no pudo desilenciar se declaraba REABIERTO.** Simétrico exacto del bloqueante de
  la apertura: `close_window` cerraba la fila (`closed_at = now()`) y **después** intentaba el
  `DeleteAlarmMuteRule` dentro de un `try/except` que solo dejaba un `logger.warning`. La ventana
  DESAPARECÍA de la consola —`active` pasa a false— con las alarmas todavía mudas hasta que
  expirase la `Duration`: hasta **4 h de edificio sin vigilancia y sin nada en pantalla que lo
  dijera**. Y el `if client is not None` de al lado saltaba el borrado entero, así que una ventana
  abierta con `ops_muting` encendido y cerrada después de apagarlo reabría la vigilancia **solo en
  pantalla**. Ahora el cierre es una AFIRMACIÓN que se sostiene o no se escribe
  (`_reabrir_o_fallar`): borrado OK ⇒ 200; borrado fallido ⇒ **502** y la transacción se revierte,
  así que la fila sigue abierta **con su `mute_rule`** y REABRIR VIGILANCIA se reintenta (el
  borrado es idempotente); sin cliente ⇒ **503**. Contrapeso para no crear un registro incerrable:
  una ventana **ya vencida** se cierra igual —vencida la fila, vencida la regla, porque el `ends_at`
  y la `Duration` cuentan desde el mismo borde (`mute_start`)—. El rastro va con la afirmación: un
  cierre fallido **no escribe** `maintenance_window_close` en la bitácora.
- **Un fallo que se SABE que no silenció se contaba como silencio.** `aws_rechazo_definitivo`
  discriminaba por `exc.response` —o sea *«¿contestó AWS?»*— y partía el mundo en dos: contestó
  (4xx ⇒ no hay nada mudo) o no contestó (ambiguo ⇒ ante la duda, se asume mudo). Falta la
  **tercera familia**: la petición que **ni se envió** (sin credenciales, región/endpoint sin
  resolver, conexión que no llegó a abrirse, parámetro rechazado por el propio cliente). Ahí no hay
  duda ninguna, y contarlo como silencio es la inferencia inválida de esta fase **con el signo
  cambiado** —antes se daba por entregado lo publicado; aquí se daba por silenciado lo que ni
  salió—: la consola pintaría «vigilancia apagada» con las alarmas sonando, y nadie iría a mirar
  por qué no llegan correos que sí van a llegar. Nace `AWS_PREVUELO` + `peticion_nunca_salio`, con
  un criterio de entrada **estrecho y de un solo sentido**: solo el fallo anterior a escribir la
  petición en el cable. `ConnectionClosedError`, `ReadTimeoutError` y `SSLError` **quedan fuera a
  propósito** (pudieron ocurrir con la petición ya enviada) y hay un test que impide que alguien
  los meta «porque también son de red». Los nombres se comparan por FORMA —igual que
  `exc.response`, para no volverse un `ImportError` el día que falte boto3— y se **anclan contra
  `botocore.exceptions`**: un nombre inventado no filtraría nada y ese fallo volvería a contarse
  como silencio, en silencio.
- **Las citas de AWS no estaban ancladas al modelo de servicio: eran teatro.** El test comparaba el
  modelo del CLI contra su **propia copia** de la frase, no contra la que el código enseña a quien
  lo lee. Dos mutaciones lo probaron **en verde**: invertir la cita de `DeleteAlarmMuteRule` dentro
  de `delete_mute` (*«…will NOT trigger»*) o parafrasear a falso la del permiso IAM dejaba los 82
  tests pasando. Esta fase **nació de una cita inventada**, así que una cita verdadera sin anclar
  es la siguiente cita inventada esperando su turno. El ancla tiene ahora **dos eslabones y los dos
  hacen falta**: (1) toda frase de AWS del código va marcada `*"…"*` y un escáner exige que
  coincida palabra por palabra con una entrada de `AWS_CITAS` —en los **dos sentidos**: cita en
  prosa sin declarar = nunca se comprueba; entrada declarada que nadie cita = ancla amarrada a
  nada—; (2) cada entrada de `AWS_CITAS` se confronta **literal** contra su ruta dentro del
  `service-2.json` del CLI instalado. Las citas van **sin elipsis** a propósito: una cita recortada
  por el medio no se puede confrontar por máquina. Comprobado con las dos mutaciones del hallazgo:
  la de solo-prosa cae por el escáner; la que muta prosa **y** declaración a la vez cae por el
  modelo de servicio.

**Fichado a propósito, no perseguido** (un punto ciego escrito es un activo; uno perseguido hasta
el infinito es una sesión que no converge):

1. **`mute_verified` ausente se lee como MEDIDO.** El campo es opcional en el SDK porque tiene
   default en Pydantic y el servidor lo emite siempre; ausente solo puede venir de una respuesta
   anterior a la migración `0031`, y aquel servidor no tenía el camino del acuse a ciegas. Es
   cierto HOY y está **anclado con un test que lo declara** (`maintenance.test.ts`, «un payload SIN
   el campo se lee como MEDIDO»). Si el servidor pudiera algún día omitirlo sin haber medido, ese
   test es el que hay que venir a romper.
2. **El CIERRE se cree el 200 del borrado; la apertura no se cree el del PUT** *(revisado por el
   lote B: era el punto 2 «el cierre no tiene su `mute_verified`»)*. La asimetría **es deliberada y
   está en la FORMA de las dos operaciones**, no en la comodidad: el `PutAlarmMuteRule` acepta una
   LISTA de N nombres y su resultado es parcial por naturaleza —un nombre que no existe no muta
   nada—, así que «200» y «cuántas quedaron mudas» son dos hechos distintos y el segundo hay que
   medirlo; el `DeleteAlarmMuteRule` actúa sobre **UN objeto** y no tiene un `N/M` que releer. Lo
   que sigue sin cubrir: un 200 al borrar que no hubiera surtido efecto cerraría la ventana —la
   quita de pantalla— con el edificio mudo hasta que expire la `Duration`, que es el mismo daño del
   cierre tragado por otra puerta. **No se persigue** porque la comprobación exige una segunda
   llamada a AWS en el camino de cierre y **su** fallo deja la ventana atascada; cuál de los dos
   riesgos es real se mide en `HUMANO-AWS`, junto al vencimiento de la ventana. Queda **anclado con
   un test que lo declara y que se pone rojo si alguien añade la relectura sin reescribir la
   decisión** (`test_muting.test_el_cierre_CONFIA_en_el_200_del_borrado…`), y ese mismo test fija de
   antemano la forma que tendría el arreglo: `GetAlarmMuteRule` declara `ResourceNotFoundException`
   en su contrato, así que «la regla ya no está» es consultable y no habrá que inventarlo.
3. **Si el `audit_async` del cierre falla, la mute rule ya se borró.** La transacción se revierte y
   `closed_at` vuelve a `NULL`: la consola sigue pintando la ventana como ACTIVA con las alarmas ya
   sonando. Es la dirección **segura** —dice «muda» de algo que suena, no al revés— y el reintento
   del cierre es idempotente, así que se ficha en vez de perseguirlo. La dirección peligrosa (rastro
   escrito con el edificio todavía mudo) sí está cerrada y medida.
4. **`_cloudwatch()` cachea su propio fracaso** (`lru_cache(maxsize=1)`): si `boto3.client(...)`
   revienta una vez —credenciales que aún no montaban, por ejemplo—, el proceso devuelve `None`
   para siempre y **toda** ventana posterior declara `0/N SILENCIADAS`. No miente (ese `0/N` es
   verdad: no se llamó a nadie) y por eso no es bloqueante, pero convierte un fallo transitorio en
   permanente hasta el siguiente despliegue. Refinamiento de arranque.
5. **La tarjeta no dice «no sé» por gabinete** cuando la lectura de ventanas falla: lo dice la
   página entera, encima de la reja. Por gabinete sería un rótulo en cada tarjeta de la flota para
   una sola causa, y el ruido tiene su propio coste. Refinamiento.
6. **`assumed` no se distingue por COLOR**, solo por texto (`.fleet-card__maint` es violeta para
   los cinco estados; el gancho `data-mute` ya está en el DOM y los tests lo miden). Refinamiento
   de diseño visual.

## Fase 2.6 · Backup y DR

`RUNBOOK-backup-restore-db.md:3` decía literalmente **"RESTORE JAMÁS PROBADO (gate G-09)"** y
el RTO no estaba medido. Mientras eso siguiera así, **el respaldo era una hipótesis**.

> **Lo que apareció al mirar (2026-08-08).** No era solo que el restore no se hubiera probado:
> **el procedimiento que el runbook documentaba perdía datos en silencio, y el checklist de
> verificación que traía salía ENTERO EN VERDE sobre la base mutilada.** Faltaban
> `timescaledb_pre/post_restore()` (aborta el `COPY` de al menos un chunk: decenas de miles de
> filas y las 3 PRIMARY KEY de las hypertables) y sobraba `--no-owner` (traslada ~46 objetos a
> quien restaura ⇒ `takab_migrator` deja de poder migrar ⇒ **el siguiente despliegue muere**).
> Medido y reproducido de forma independiente por un segundo revisor con su propio montaje.
> Sin PK, además, muere la idempotencia del edge (regla de oro 3): un restore mal hecho no solo
> pierde filas, desarma el mecanismo que iba a reponerlas.
>
> De regalo, dos defectos vivos desde julio-2026: la regla de lifecycle `expira-60d` **nunca
> borró un byte** (sobre un bucket versionado `Expiration` solo pone un delete marker, y la
> versión anterior se queda facturándose para siempre — peor para el PITR: el delete marker
> **esconde el objeto al restaurador**), y **la instancia no podía leer sus propios respaldos**
> (`s3:PutObject` y nada más), o sea que el restore era imposible de ejecutar donde vive la DB.

### [x] T-2.72 · PITR en IaC — `SOFTWARE`
- **Componente:** infra · **Depende de:** —
- **La herramienta es `barman-cloud`, no WAL-G**, y el cambio de nombre de la tarea es
  deliberado: la imagen `timescale/timescaledb-ha:pg16` que corre en producción **ya lo trae
  instalado y no trae wal-g** (verificado contra el contenedor real). Meter wal-g exigiría
  reconstruir la imagen o montar un binario descargado dentro del contenedor: **un eslabón de
  suministro nuevo justo en el camino de recuperación**, el último sitio donde conviene tener
  uno. El diseño no dependía de la herramienta.
- **Criterios de aceptación:**
  - [x] WAL archiving continuo declarado en Terraform (no a mano en la instancia). Vía
        `aws_ssm_document` + `aws_ssm_association`, **no `user_data`**: el user_data corre una
        sola vez en el primer boot y sale antes de tiempo por su marcador, así que habría dado
        un Terraform verde que no toca la máquina que existe hoy. Coste declarado: hasta 24 h de
        convergencia (`aws ssm start-associations-once` lo fuerza).
  - [x] RPO objetivo declarado y **derivable de la configuración**, no de una promesa.
        `terraform output rpo_seconds` → **900 s**, calculado de los ATRIBUTOS del recurso de
        alarma: `umbral (600) + period (60) × evaluation_periods (5)`. El segundo término no es
        adorno — CloudWatch avisa tras N periodos seguidos por encima, y durante esos 5 minutos
        se sigue acumulando WAL que no está en S3. **El RPO real no es lo que promete la
        configuración feliz: es la edad del archivado a la que alguien SE ENTERA.**
  - [x] Alarma si el archivado se atasca: `takab-dev-wal-archivado-atascado`,
        `treat_missing_data = "breaching"` (sin eso la derivación del RPO es mentira: si el
        publicador muere, el silencio pasaría por salud), `Maximum > umbral`, 5×60 s, los TRES
        estados al topic de on-call. Clasificada **INTOCABLE** en `ALARM_CATALOG` y negada
        también por IAM.
  - [x] `terraform fmt/validate` verde, más `terraform test` en los TRES módulos. El `apply` es
        **`HUMANO-AWS`** y va en T-2.74.
- **Lo que el ejercicio de no-vacuidad enseñó, y vale más que el código:** aparecieron **tres**
  aserciones vacuas, y las tres eran del mismo par de patrones. (a) *Comparar por subcadenas*:
  un `strcontains` sobre una política IAM casi siempre encuentra su subcadena en OTRO statement,
  así que responde "sí" a una pregunta que nadie hizo — una de ellas juraba que no se concedía
  borrado enumerando `s3:DeleteObject`/`s3:Delete*` y **se la saltaba un `s3:*`**. (b)
  *Comprobar una igualdad con un solo valor de entrada*: no distingue una función de una
  constante que hoy coincide, que es literalmente la diferencia entre derivar el RPO y
  prometerlo. Quedan como método escrito en la cabecera de `pitr.tftest.hcl`.

### [x] T-2.73 · Ensayo de restore que mide su propio RTO — `SOFTWARE`
- **Componente:** db + deploy · **Depende de:** T-2.72
- **Criterios de aceptación:**
  - [x] Un solo comando (`make restore-drill`) restaura a una instancia limpia e **imprime el
        RTO medido**, desglosado por fase. El reloj para en el VERDE del verificador, no en el
        `rc=0` de `pg_restore`: una base restaurada y no verificada no es un servicio
        recuperado. Y arranca cuando el dump ya existe, porque en el incidente real lleva en S3
        desde las 08:00; fabricarlo es andamiaje y se cronometra aparte.
  - [x] Verifica la integridad de lo restaurado: **22 comprobaciones** con veredicto de tres
        estados y salida 0/1/2. Las expectativas se DERIVAN de `db/schema.sql` y del catálogo
        (extensiones, tablas append-only, RLS y su FORCE, políticas, hypertables, vistas
        barrera, roles, políticas de Timescale): ninguna tabla está escrita a mano.
  - [x] Ensayable **contra la DB local** — que corre la MISMA imagen que producción, así que el
        ensayo es fiel y no un simulacro.
  - [x] Guardia anti-restore-sobre-producción **positiva**, no lista negra: solo escribe en una
        base que él mismo creó en esta corrida, con nombre generado y marcador propio releído
        del catálogo antes de cada paso destructivo. `takab_restore` —el nombre que usaba el
        propio runbook— es rechazado como cualquier otro. No hace swap, y hay un test sobre el
        AST que lo impide.
- **Las tres cosas que la auditoría adversarial encontró y hubo que cerrar**, todas de la misma
  familia —*un verde que no significa lo que parece*—:
  1. **Sin `--baseline` el verificador decía VERDE y salía 0** con seis comprobaciones saltadas,
     sobre una base a la que le faltaba el 75 % de la telemetría y una tabla entera. Hoy eso es
     **INDETERMINADO** y salida 2: *un SKIP no es un PASS*.
  2. **`append_only_enforced` pasaba por la razón equivocada**: trataba cualquier error de
     Postgres como "la guarda lo rechazó", así que con la guarda rota y la conexión en solo
     lectura —justo como se verifica una base lateral antes del swap— daba verde. Hoy exige el
     SQLSTATE de la guarda.
  3. **Seis clases de daño real salían verdes** (job de retención desprogramado, CHECK y FK
     borradas, columna desaparecida, cagg vaciado, y un `REVOKE` que deja a `takab_app` sin
     leer `incidents`). Hoy el baseline lleva columnas, constraints, ACL y filas de cagg
     materializado.
- **Una afirmación del obrero hubo que retirarla, y conviene que quede escrita**: no es cierto
  que «el FORCE de todas las tablas de negocio nos salva de un restore con `--no-owner`».
  `FORCE ROW LEVEL SECURITY` obliga al dueño **normal**; un superusuario (o `BYPASSRLS`) se
  salta la RLS con FORCE o sin él. Lo que sí es cierto, y es otra cosa, es que el camino de la
  API sigue aislado — pero porque `takab_app` no es dueño de nada ni tiene BYPASSRLS, no por el
  FORCE. Confundir la conclusión con su causa es como esa frase acaba en un runbook.

### [x] T-2.73.a · La huella del origen viaja junto al dump — `SOFTWARE`
- **Componente:** infra + db · **Depende de:** T-2.73 · **BLOQUEA `T-2.74`.**
- El cron de las 08:00 sube el `.dump` y nada más. **Sin la huella del origen el verificador
  devuelve INDETERMINADO** y sus seis comprobaciones más fuertes (inventario, columnas,
  constraints, privilegios, propiedad, conteos) no se pueden ejercer. Intentar acreditar `G-09`
  sin esto es gastar la ventana AWS para obtener medio veredicto.
- **Criterios de aceptación:**
  - [x] El mismo cron escribe `restore_check --save-baseline` y lo sube al mismo prefijo S3.
  - [x] El vehículo es el **documento SSM**, no `user_data.sh.tpl`: tocar el user_data fuerza al
        provider a parar y arrancar la instancia en el siguiente apply, y la DB caería.
  - [x] Confirmado que el contenedor de la nube co-locada tiene el código del API para
        invocarlo (es la incógnita real de esta ficha).

### [ ] T-2.72.a · Comprobar que el WAL llegó de verdad a S3 — `SOFTWARE`
- **Componente:** infra · **Depende de:** T-2.72
- `pg_stat_archiver.last_archived_time` mide el último `archive_command` que devolvió 0, no que
  el objeto esté en el bucket. La propia doc de PostgreSQL da el contraejemplo:
  `archive_command = /bin/true` «effectively disables archiving, but also breaks the chain of
  WAL files needed for archive recovery» — y reportaría salud perfecta con cero WAL en S3.
- **Criterios de aceptación:**
  - [ ] `last_archived_wal` da el NOMBRE del segmento: un `head-object` **O(1)** contra la clave
        esperada, sin listar el prefijo (que crece sin cota).
  - [ ] Resuelto el acoplamiento con el sufijo de compresión y el layout interno de barman
        (hay que medirlo contra el bucket real, en la ventana de T-2.74).

### [x] T-2.72.b · Alarma de backup base ausente — `SOFTWARE`
- **Componente:** infra · **Depende de:** T-2.72
- `WalArchiveAgeSeconds` mide la cadena de WAL, **no su ancla**. Un backup base que falla cada
  semana es invisible hasta el día del restore, que es el modo de fallo que la Fase 2.6 existe
  para eliminar.
- **Criterios de aceptación:**
  - [x] `BaseBackupAgeSeconds` publicada a diario desde `barman-cloud-backup-list`.
        > **Desviación declarada:** el *listado* es diario; la *edad* se publica **por minuto**,
        > porque una métrica diaria sobre periodo diario deja ventanas vacías y, sobre
        > `breaching`, **cada ventana vacía es un correo falso**.
  - [x] Alarma por encima de `base_backup_interval_days × chain_margin`, derivada de las mismas
        variables que gobiernan la retención.

> **Cerrada (2026-08-13).** `treat_missing_data = breaching`, y **nace en ALARM a propósito**: el
> día del `apply` todavía no hay backup base. **El correo de OK al terminar el primero ES el
> acuse** de que la cadena consiguió ancla — si no llega, eso es el hallazgo. Razón del
> `breaching`: no mide «cuántos backups hay» sino **hasta dónde se puede recuperar**, y un ancla
> desconocida es, para un restore, **no tener ancla**. Más una razón de instrumento: **el que
> publica y el que respalda son el mismo host**, así que si ésta calla, lo más probable es que
> tampoco esté corriendo el respaldo.
>
> El umbral se deriva de `base_backup_interval_days × chain_margin`, **las mismas variables que
> gobiernan la retención**, y se probó con **dos** juegos de centinelas — con uno solo, una
> igualdad no distingue una función de una constante (la lección del literal `1077`).
>
> **⚠️ HALLAZGO SOBRE LA PROPIA FICHA: este umbral NO es un aviso temprano.** Con los valores por
> defecto, `intervalo × margen` = 7×2 = **14 días = exactamente `wal_retention_days`**: el correo
> llega **justo cuando la ventana de recuperación se cierra**. Está implementado como la ficha lo
> pide y **declarado** en el output, la alarma y el runbook. Cazar el *primer* backup base fallido
> exige una segunda alarma a `intervalo` días — `T-2.141`.

### [x] T-2.72.c · Alarma de espacio en disco de la instancia DB — `SOFTWARE`
- **Componente:** infra · **Depende de:** T-2.72
- El PITR introduce un modo de fallo nuevo: con el archivado atascado Postgres **no recicla** su
  WAL y `pg_wal` crece ~16 MiB/min sobre el mismo volumen de 40 GiB donde viven los datos —
  **menos de dos días hasta llenar el disco y tumbar la DB**. Hoy lo cubre por accidente la
  alarma de atasco (900 s ≪ 48 h) y su descripción ya nombra el reloj corto, pero **no hay
  vigilancia de disco**: `disk_used_percent` no existe en las métricas nativas de EC2.
- **Criterios de aceptación:**
  - [x] Agente CloudWatch en la instancia, o publicación propia de espacio libre en `/data`.
  - [x] Alarma con `treat_missing_data` clasificado y su entrada en `ALARM_CATALOG`.

> **Cerrada (2026-08-13), y su `treat_missing_data` es el OPUESTO al de su hermana — a
> propósito.** Aquí es **`missing`**, no `breaching`, porque **el correo de esta alarma AFIRMA UNA
> MEDIDA** («el disco pasó del 80 %») y **sin datapoint esa medida no existe**: afirmarla sería
> exactamente la falta que `T-2.60.a` rechaza por escrito. La ceguera no queda tapada — si la
> instancia cae lo dice `ec2_status`, si muere el cron lo dice `wal_archive_stalled`, y las dos
> son `breaching` sobre el mismo `/etc/cron.d/takab-pitr`.
>
> **Y el detalle que evita un falso verde:** el publicador **se niega a publicar si `/data` no
> está montado**, porque `df` respondería con el volumen raíz — **que se ve sano**. Ahí
> INSUFFICIENT_DATA significa algo **peor** que el disco lleno.
>
> Contra la trampa de que `insufficient_data_actions` **solo dispara al transitar** —una métrica
> que nunca arranca deja la alarma nacida ahí y **aparcada para siempre, sin avisar a nadie**—, el
> script **publica una primera medida en el acto**: el correo de `ok_actions` es la señal de que
> arrancó, y su ausencia es el indicio. Queda como paso escrito en el runbook.

### [x] T-2.144 · Cinco verbos reales se pintan crudos y EN VERDE, y uno dice «personas en riesgo» — `SOFTWARE`
- **Componente:** sdk + web · **Detectada por:** `T-2.133` (2026-08-14), al barrer los productores
- Hay **siete productores reales** de `incident_actions` sin rótulo en el checklist BMS:
  `fail_open`, `in_review`, `close`, `dictamen_signed`, `damage_people_at_risk`,
  `headcount_closed`, `headcount_notify`. Los dos últimos sí los rotula la bitácora; **los cinco
  primeros caen en el fallback crudo y VERDE en las dos superficies**.
- **Y uno de ellos es `damage_people_at_risk`**: la consola pinta **«DAMAGE PEOPLE AT RISK» con
  `kind: 'ok'`** — personas en riesgo, en verde, con el nombre de la constante en inglés. Es la
  misma familia que `T-2.119` (gas y puertas crudos y en verde) y que el
  `notify_no_recipients` que `T-2.133` arregló de paso.
- **Por qué el censo existente no los caza, declarado en el propio ayudante:** va **del registro
  al productor**, y el censo en dirección contraria **no se puede hacer con un barrido honesto** —
  `headcount_*` los fija un router sobre una sentencia de otro módulo, y `lifecycle.py` los saca
  de un `dict`. Un barrido que los buscara literalmente **daría falsos negativos y nadie lo
  sabría**.
- **Criterios de aceptación:**
  - [x] Los siete tienen rótulo en las dos superficies, derivado del mismo registro.
  - [x] Ninguno cae en el fallback `ok`: el que no se sepa clasificar **no se pinta en verde**.
  - [x] El fallback deja de ser `ok` **por defecto**, o queda escrito por qué es seguro que lo sea.

> **Cerrada (2026-08-14). Eran OCHO, no siete — y el octavo demuestra que esta ficha nació de un
> barrido con punto ciego.** `notify_delivered` **no lo escribe `api/src`**: lo escribe una función
> PL/pgSQL que vive en `db/schema.sql` y en la migración `0040`. **Ningún barrido de `api/src`
> podía verlo**, y la consola lo pintaba «NOTIFY DELIVERED» en verde. El barrido nuevo va sobre
> **el repo entero**: 13 ficheros productores, **16 sentencias**, **0 sin resolver, 26 kinds**.
>
> **⚠️ Y esta ficha describía `fail_open` AL REVÉS.** Decía «el gabinete decidió actuar sin poder
> confirmar». Es lo contrario: `incident/fail_open.py` abre un incidente sintético para un sitio
> **SIN ENLACE** alcanzado por un evento de red — **nadie detectó ahí, nadie accionó ahí, nadie
> sabe cómo quedó**. El rótulo lo dice así, y su severidad (`warning`) **no es opinión**: es la
> misma que el productor le pone al incidente que abre.
>
> **`damage_people_at_risk` pasa de «DAMAGE PEOPLE AT RISK» en verde a `PERSONAS EN RIESGO`,
> `critical`** — es la única línea de la familia que describe a alguien atrapado, y existe para
> que el orquestador despierte al SOC de inmediato.
>
> **El fallback dejó de ser verde:** `SIN CLASIFICAR`, `warning`. Y **no se volvió no-verde nada
> que estuviera bien**, medido antes de tocarlo y anclado con un test que recorre todo el
> registro: los 26 kinds escritos tienen entrada explícita. `warning` y no `critical` a propósito
> — **un estado desconocido pide que alguien lo mire, no que se evacúe un edificio**; lo que
> ninguno merecía era verde.
>
> Detalle de contención que evita romper otra superficie: **no se amplió la unión a un cuarto
> valor**, porque `GROUP_COLOR` de la app móvil mapea exactamente el trío y un cuarto la habría
> dejado **sin color** — otra pantalla sin saber qué pintar, en un fichero que el agente no podía
> tocar.
>
> **La pregunta de fondo —¿qué garantiza que el productor número nueve tenga rótulo?— tiene ahora
> DOS respuestas, y la segunda es la buena.** `T-2.133` acertó sobre el barrido que intentó y
> **erró sobre el problema**: el nombre no se busca, **se resuelve**. El censo estático resuelve la
> expresión de cada `INSERT` por cuatro reglas derivadas de código declarado, y **lo que ninguna
> regla resuelve deja la lista vacía y el test lo NOMBRA** — el censo no calla lo que no entiende,
> que es literalmente lo que produjo esta ficha.
>
> Y para el hueco que ningún análisis estático cubre (un kind calculado en ejecución, un productor
> fuera del repo), la garantía sale de **una propiedad del esquema**: `incident_actions` es
> append-only y **exenta de poda**, así que `SELECT DISTINCT kind` **es la lista completa de todo
> lo que se ha escrito nunca** (`api/tests/api/test_incident_action_kinds.py`). Se descartó a
> propósito la opción de «un módulo con todas las constantes»: **su completitud descansaría en una
> convención, y una convención no es una garantía**.
>
> **Ese test declara cuándo no mide.** Con la tabla vacía, `set() - registro` es `set()` y pasaría
> en verde sin haber mirado nada — **el mismo defecto que la ficha cierra, reintroducido en su
> propio test**. Así que el mecanismo se acredita con datos fabricados y la corrida contra la base
> **avisa en voz alta** cuando no tuvo nada que mirar. Su sitio de valor máximo es el simulacro de
> restauración y la base de producción.
>
> **De paso:** `drill_start`/`drill_stop` estaban **muertos en la bitácora** —son valores de
> `commands.action`, no kinds de acción— y se retiran con su razón, igual que `siren_test` en
> `T-2.133`.

### [x] T-2.164 · Los teléfonos ya escritos en claro siguen en claro para siempre — `SOFTWARE` · COMPLETA (2026-08-24)
- **Componente:** api + db · **Depende de:** T-2.150 · **Declarada por la migración `0046`**
- **El hueco, y lo escribe la propia migración.** `T-2.150` sellò el sujeto: las filas NUEVAS de
  `privacy_consents` guardan un índice de 64 hex y no el número. Las viejas **no se tocaron**, y el
  `CHECK` las sigue aceptando con este comentario literal: *«Forma VIEJA: el número en claro.
  **Permanente, no transitoria**: la tabla es append-only y estas filas NO SE PUEDEN reescribir.»*
- **Por qué no es un descuido sino una deuda:** la tabla es append-only **a propósito** —es la
  prueba de la base legal de cada envío—, así que reescribir esas filas exige exactamente la
  decisión que `T-2.80.a` planteó y que `D-23` resolvió sólo para el flujo ARCO nuevo. Un
  `UPDATE` a mano destruiría la propiedad que hace útil a la tabla.
- **Cuántas son, hoy: no se sabe, y eso es parte de la ficha.** Hay que contarlas antes de decidir
  nada — si son cero, esto se cierra midiendo; si no, hay PII en claro con nombre y apellido.
- **Criterios de aceptación:**
  - [x] **Contadas** (2026-08-24). **Cero en los tres entornos que existen**, y no había otra
        forma de saberlo que preguntándoselo a cada base:

        | Entorno | consentimientos | `msisdn` en claro | `msisdn` sellados |
        |---|---|---|---|
        | local `takab` | 0 | **0** | 0 |
        | local `takab_test` | 0 | **0** | 0 |
        | nube dev (`takab-dev-db`, por SSM) | 2 | **0** | 0 |

        Los dos de la nube son de sujeto `user`. El componente `LEGAL` de la ficha **se cae con
        el conteo**: sin filas afectadas no hay derecho de titular que ponderar contra ninguna
        prueba de base legal.
  - [x] **Sin filas, no hay nada que decidir** — y esa es la respuesta, no una evasión: la
        decisión que este criterio pedía (sellar retroactivamente a costa del append-only, o
        declararlas intocables) sólo tiene sentido con datos que ponderar.
  - [x] **El `CHECK` deja de aceptar las dos formas** (migración `0051`). Mientras aceptaba
        ambas, «no hay filas viejas» y «nadie las ha mirado» eran indistinguibles; ahora el
        invariante lo garantiza la base. Y se puede apretar sin miedo porque **ningún camino de
        código puede crear una**: `privacy/store.py` sella el sujeto antes de insertar y **LANZA**
        si faltan los secretos, en vez de caer a texto en claro.

> ### La lectura sigue tolerando la forma vieja, y eso es deliberado
>
> `store._formas()` busca por el índice **y** por el número en claro. Si algún día apareciera una
> fila así en un entorno que nadie censó, se encontraría igual: lo que ya no se puede es
> **escribir** una nueva. Apretar la escritura y relajar la lectura es la dirección correcta —al
> revés se perdería el acceso a un dato que sí existe.
>
> El pre-check de la migración no es decoración: `ADD CONSTRAINT` ya valida las filas existentes,
> pero el error de PostgreSQL nombra UNA fila y no dice cuántas hay ni que lo que falta es una
> decisión. El `DO` cuenta y lo dice.
>
> Anclado en `test_la_BASE_ya_no_acepta_un_consentimiento_con_el_numero_en_claro` y su contraparte
> `test_la_forma_SELLADA_sigue_entrando` — sin la segunda, la primera podría estar pasando porque
> el `CHECK` rechaza todo. Verificado por mutación: relajar el `CHECK` pone el primero en rojo.

### [x] T-2.165 · El layout A/B abre una ventana en la que el cliente no ve al dueño de los pines — `SOFTWARE` · COMPLETA (2026-08-24)
- **Componente:** edge (`pinlink`) · **Depende de:** T-2.70 · **Hallazgo del gabinete real (2026-08-23)**
- **El hueco, medido en `gw-dev-0001`.** El despliegue A/B actualiza al **cliente**
  (`takab-edge`) y deja al **dueño de los pines** (`takab-gpio`) con el código anterior hasta una
  ventana declarada — eso es el diseño de `T-2.70.a` y es correcto. Lo que nadie previó es que el
  códec de `pinlink` es **estricto**: el cliente nuevo exigió `keepalive_beating` y el dueño de
  julio no lo mandaba, así que rechazó la instantánea entera:
  ```
  ProtocolError: la instantánea del dueño de los pines llegó sin ['keepalive_beating']:
  es un contrato roto, no un gabinete en reposo
  ```
  Resultado medido: **el panel dijo `gpio_unreachable` y `relays: []`** durante toda la ventana.
- **La protección NO se toca, y esa distinción es el corazón de la ficha.** El reflejo
  SASMEX→sirena vive **entero dentro de `takab-gpio`** y no cruza la costura (gate #6): el
  edificio siguió protegido en todo momento. Lo que se pierde es **observabilidad** — el panel del
  guardia y la consola SOC dejan de ver los relés de un gabinete que sí está protegiendo.
- **El códec hace bien en fallar cerrado, y por eso NO se relaja.** *«No se inventa un gabinete en
  reposo: un estado sin medir no existe»* es la doctrina correcta, y rellenar el campo ausente con
  `False` sería exactamente la mentira que evita. El defecto no es la estrictez: es que **un dueño
  MÁS VIEJO se trata igual que un contrato ROTO**, y son dos cosas distintas.
- **Criterios de aceptación:**
  - [x] **El dueño DECLARA qué campos conoce** (`_campos` en la instantánea), y el cliente
        distingue «no lo mandó porque no lo conoce» de «dijo que lo mandaría y no está».
        **No es un número de versión, y se eligió así a propósito:** una versión obliga a
        mantener a mano un registro de «qué campos existían en la N» —un censo enumerado, que en
        esta casa acaba divergiendo—. La lista la deriva el dueño de su propio
        `__dataclass_fields__`: siempre dice la verdad sobre sí mismo y no hay tabla que
        actualizar.
  - [x] Un dueño ANTERIOR se lee en modo degradado **declarado**: lo que sí midió llega, y lo que
        no supo decir queda NOMBRADO en `GpioSnapshot.campos_desconocidos`. El panel gana un
        cuarto estado, `dueno_antiguo`, distinto de los tres de T-2.146 — porque el valor que
        trae un campo desconocido **no lo midió nadie**: lo puso el códec para poder construir el
        objeto, y `keepalive_beating=False` significa «hay ruta y NADIE la gobierna», que es el
        estado que hay que ver de lejos. Pintarlo así sería inventarse una avería; callarlo,
        esconder una ventana.
  - [x] Un dueño **posterior** al cliente sigue siendo error duro, y la asimetría es deliberada:
        de un dueño viejo se sabe exactamente qué falta; de uno nuevo **no se sabe qué significa
        lo que sí mandó**. Leer a medias una instantánea que no se entiende del todo es peor que
        no leerla.
  - [x] Test que reproduce la ventana del gabinete, y con su contraparte: un dueño que PROMETE un
        campo y no lo manda **sigue siendo contrato roto**. Sin ese, «tolerar al viejo» se
        convertiría en «tolerar cualquier cosa», que es como se pierden los contratos.

> ### La estrictez no se relajó: se hizo PRECISA
>
> El códec seguía teniendo razón —*«no se inventa un gabinete en reposo: un estado sin medir no
> existe»*—; lo que le faltaba era distinguir **por qué** falta un campo. Ahora hay tres
> desenlaces donde había dos, y el que se añadió es el único que ocurría de verdad.
>
> **Un dueño anterior a esta ficha no manda `_campos`**, y entonces no se le puede exigir nada:
> lo que falte se cuenta como desconocido. Es la lectura correcta —no pudo prometer campos que no
> sabía que existían— y es exactamente el caso que dejó un gabinete ciego el 2026-08-23. Cuando
> toda la flota corra esta versión, la estrictez vuelve entera sola.
>
> **Dos censos escritos a mano que este cambio destapó**, y los dos se derivaron: la lista de
> campos que el test de conformidad excluía (`{"age_s", "relays"}`) y la del oráculo del GPIO.
> `age_s` estaba a mano y `campos_desconocidos` —recalculado por la misma razón— tuvo que
> descubrirse con un rojo. Ahora salen de `CAMPOS_RECALCULADOS_AL_LLEGAR`, que ya existía y ya
> llevaba la razón escrita de cada excepción.

> ### La bifurcación, con el dato que la decide (medido 2026-08-24)
>
> La salida barata sería «un campo que falte y sea opcional se lee como `None`». **No sirve**:
> de los 13 campos de `GpioSnapshot` **sólo 2 admiten `None`** (`siren_reason`,
> `last_reflex_latency_s`), y el que rompió el gabinete —`keepalive_beating`— **no es uno de
> ellos**. Así que hay que elegir, y las dos vías cuestan cosas distintas:
>
> **(A) Convención: todo campo NUEVO del snapshot nace opcional.** Barato de implementar y
> derivable —el códec ya saca la lista del `__dataclass_fields__`—. El precio: `None` pasa a
> significar **dos cosas** en el mismo campo («el dueño es más viejo y no lo manda» y «se
> preguntó y no se pudo medir»), que es exactamente la fusión que `relays: null` costó cerrar en
> el contrato 1.10.0. Y obliga a que cada consumidor trate el `None` de campos que hoy son
> booleanos francos.
>
> **(B) El protocolo lleva versión y declara qué NO manda.** El cliente sabe *por qué* falta un
> campo, y el panel puede decir «el dueño de los pines es más antiguo: no sabe decir X» — que es
> un rótulo distinto de `S/D` y de `NO CONTESTA`, las tres distinciones que `MANUAL §6.0` lleva
> tres tareas separando. Más trabajo, y es la que respeta la doctrina de la casa.
>
> **Recomendación: (B).** El defecto que esta ficha cierra no es «falta un campo» sino «no se
> distingue un dueño VIEJO de un contrato ROTO», y (A) no distingue: sólo hace que el fallo sea
> silencioso en vez de ruidoso. Pero es una decisión de contrato del camino de vida y merece
> tomarse con la cabeza fresca, no al final de una sesión.
>
> **Mientras tanto el riesgo está acotado y conocido:** la ventana sólo existe entre la
> activación y el reinicio del dueño, la protección no se toca, y `deploy.sh` ya avisa de que el
> dueño quedó con código anterior.

### [x] T-2.163 · La reconciliación contra Cognito está desplegada y es INERTE — `SOFTWARE` + `HUMANO-AWS`
- **Componente:** infra (`modules/database`) + api · **Detectada por:** `T-2.143`, **verificando el
  despliegue** el 2026-08-23 · **Bloquea:** el criterio 1 de `T-2.143`
- **El hecho, medido en la instancia:**
  - `/opt/takab/bin/takab-prune-pii.sh` construye un env temporal con **una sola clave útil**,
    `DATABASE_URL`. No pasa `TAKAB_API_COGNITO_USER_POOL_ID` ni la región.
  - El rol `takab-dev-db` **no declara ningún permiso `cognito-idp:*`**.
- **Consecuencia:** `build_user_directory()` cae al directorio **simulado**, la corrida aborta con
  «el directorio devolvió CERO cuentas» y **ninguna baja hecha en el pool arranca su reloj**. La
  guarda hace lo correcto —negarse a actuar con una lectura vacía— pero el resultado es una
  función desplegada que no hace nada.
- **Por qué se coló:** se verificó **el código dentro del contenedor** (`import reconcile` → OK) y
  no **el entorno desde el que se invoca**. Es la misma familia que «un indicador leído sin abrir
  su contenido acredita lo que uno esperaba».
- **Criterios de aceptación:**
  - [x] El job recibe `TAKAB_API_COGNITO_USER_POOL_ID` y la región, desde el mismo output de
        terraform que los usa la API — **derivado, no tecleado**.
  - [x] El rol de instancia gana `cognito-idp:ListUsers` **acotado al pool**, y nada más.
  - [x] **El directorio SIMULADO se rechaza por su nombre.** Hoy produce el mismo mensaje que un
        pool vacío de verdad, y son dos fallos distintos con dos arreglos distintos — el mismo
        defecto que `T-2.143` ya corrigió una vez entre «caído» y «vacío». Un fallback no puede
        pasar por una lectura buena ni por una lectura vacía: tiene que decir que es un fallback.
  - [x] Test que falle si el job se invoca sin la variable del pool.
  - [x] Verificado **en la instancia**, no en el contenedor: una corrida real que arranque un reloj
        o que diga por qué no.

> ### ✅ CERRADA y APLICADA el 2026-08-23 — verificada donde falló, en la máquina
>
> ```
> Reconciliación · 8 cuentas en el directorio, 1 perfiles sin baja, 0 reloj(es) arrancado(s)
> ```
>
> Ocho cuentas **reales** leídas del pool: eso prueba a la vez la variable y el permiso, y no es
> una comprobación que pueda pasar por vacuidad (con cualquiera de los dos ausentes el número sería
> cero y el mensaje diría «SIMULADO» o «CERO cuentas»). Cero relojes arrancados es lo correcto: el
> único perfil sin baja sigue en el pool.
>
> **Cuatro sabotajes, y el que no mordió enseñó lo de siempre.** Quitar la línea del env deja dos
> aserciones en rojo; ampliar el permiso a `AdminDisableUser`, una. Pero **cambiar la acción a
> `sts:GetCallerIdentity` dejaba el test en verde**: la aserción comprobaba que el ARN del pool
> *aparecía* en la política, no que se concediera `ListUsers` **sobre** él. *Un permiso es un verbo
> SOBRE un recurso; verificar la mitad no verifica nada.* Ahora se decodifica la política y se
> exige el statement entero.
>
> **Y un defecto de la plantilla que el propio test destapó:** `printf '%s' '${pool}'` deja el
> valor en un argumento aparte, así que el literal **no aparece en el script** y la aserción
> buscaba una cadena que nunca existió. Se cambió a heredoc citado, que además es más simple.
>
> El `cognito_pool` es un objeto y no dos variables sueltas, con una validación que exige los dos
> campos o ninguno: con solo el `id` el job tendría la variable y no el permiso, y fallaría por una
> razón distinta de la que se lee en el log.

### [x] T-2.143 · Una baja hecha en Cognito no arranca el reloj de la PII — `SOFTWARE`
- **Componente:** api · **Detectada por:** `T-2.81.b` (2026-08-14), **declarada al cerrarla**
- El reloj de retención de nombre y teléfono lo escriben `PATCH {"enabled": false}` y `DELETE`
  de la API. **Una cuenta retirada directamente en el pool de Cognito no pasa por ahí**, así que
  esa persona **conserva nombre y teléfono indefinidamente**.
- **Falla en la dirección segura** —se conserva de más, nunca de menos— y por eso `T-2.81.b` se
  cerró con el hueco declarado y su query de reconciliación escrita en el runbook. Pero **una
  reconciliación que hay que acordarse de correr no es retención cumplida**, que es exactamente
  el argumento de `T-2.81.a`.
- **Criterios de aceptación:**
  - [x] La baja hecha en Cognito arranca el reloj sin que nadie corra nada a mano.
  - [x] Test de una cuenta que desaparece del pool sin pasar por la API.

> ### ⚠️ ESTUVO EN `[~]` unas horas el 2026-08-23 — desplegada y **sin hacer nada en producción**
>
> Se desplegó (`eaeb82a`) y se verificó el código dentro del contenedor. Lo que NO se verificó al
> cerrarla es **el entorno en el que corre**, y ahí está el defecto: el job recibe un `db.env`
> temporal con **una sola clave, `DATABASE_URL`**. Sin `TAKAB_API_COGNITO_USER_POOL_ID`,
> `build_user_directory()` cae al **directorio SIMULADO**, que devuelve cero cuentas — y la guarda
> aborta, correctamente, con «el directorio devolvió CERO cuentas».
>
> O sea: **la red de seguridad se niega a actuar a ciegas, que es lo que debe hacer, pero nunca
> llega a actuar.** El criterio 1 dice «sin que nadie corra nada a mano»; hoy no corre nada, ni a
> mano ni solo. Y el rol de instancia `takab-dev-db` **no tiene un solo permiso `cognito-idp:*`**,
> así que ni siquiera podría listar el pool si tuviera la variable.
>
> **Cerrado por [`T-2.163`](#) el mismo día**, y verificado en la instancia: la corrida lee ahora 8
> cuentas reales del pool. Se dejó en `[~]` mientras tanto, no en `[x]`: el software estaba escrito
> y probado, el despliegue no.
>
> ### Lo que sí quedó hecho, y sigue siendo válido
>
> El paso va **antes de la poda y en su propia transacción**: antes, para que un reloj recién
> arrancado cuente ya en esta misma corrida; aparte, para que una reconciliación que falle no se
> lleve por delante la poda. Un fallo aquí **no aborta el job** — el peor caso es que unos relojes
> arranquen una corrida más tarde, mientras que abortar dejaría sin podar lo ya vencido.
>
> **El flag `--sin-reconciliar` APAGA, no enciende.** Un paso de cumplimiento que hay que acordarse
> de pedir es el defecto que esta ficha cerraba; ponerlo detrás de un `--reconciliar` habría sido
> escribirlo otra vez con otra forma.
>
> **Lo difícil no era dar de baja: era negarse a hacerlo con una lectura a medias.** El acto es
> media línea de SQL. El riesgo está en la premisa, porque **una lectura incompleta del pool es
> indistinguible de un montón de bajas**: directorio caído, paginación que no termina, respuesta
> vacía. En los tres la lista de «usuarios que existen» encoge, y actuar sobre ella arrancaría el
> reloj del borrado del nombre de gente que está en el edificio ahora mismo. Los tres abortan
> enteros; ninguno actúa «con lo que se pudo leer».
>
> **Lo que NO sabe, escrito y no escondido:** *cuándo* se borró la cuenta. El pool no guarda fecha
> de lo que ya no está, así que el reloj arranca el día en que la reconciliación se entera. Alarga
> el plazo real —el lado seguro— y por eso esto es una red de seguridad: las bajas se hacen desde
> la consola de TAKAB. El runbook `§6` pasa de declarar el hueco a describir el mecanismo.
>
> **Cinco sabotajes, y los dos que NO mordieron enseñaron más que los tres que sí:**
>
> 1. **Tragarse la caída del directorio** dejaba la suite en verde. La red de seguridad aguantaba
>    —caía en la rama del pool vacío y nadie se dio de baja— pero **el motivo era el equivocado**, y
>    el motivo es lo que alguien lee a las 3 a.m. La aserción buscaba la palabra «directorio», que
>    sale en los DOS mensajes. Es literalmente `"5 min"` ⊂ `"15 min"` de `T-2.162`, tercera vez en
>    esta sesión. Ahora se exige el texto que los distingue **y** que los dos motivos difieran.
> 2. **Cambiar el `ON CONFLICT DO NOTHING` a `DO UPDATE SET deactivated_at = now()`** tampoco movía
>    nada: la consulta de candidatos ya excluye a quien tiene reloj, así que **el conflicto no
>    ocurre por el camino normal**. Era un cinturón que nunca se abrocha. Se prueba ahora ejecutando
>    la sentencia a mano contra alguien que ya tiene reloj, que es lo que pasaría con dos corridas
>    solapadas.
>
> **Y dos hechos del esquema que corrigieron el test, no el código:**
>
> - `user_profiles.user_sub` es **PRIMARY KEY global**: un sub pertenece a un cliente y a uno solo.
>   El primer test sembraba el mismo sub en dos tenants con `ON CONFLICT DO NOTHING` — no insertaba
>   nada y pasaba por vacuidad disfrazada de aserción.
> - Toda fila de `user_profiles` nace de un token verificado (`PUT /me/profile`), o sea de alguien
>   que **tuvo** cuenta. No existe el perfil de quien nunca la tuvo, así que «ausente del pool» no
>   puede significar otra cosa que «se la borraron» — y por eso `via = 'account_deleted'` es exacto
>   y no una aproximación cómoda.

### [x] T-2.142 · Un test renombra roles a nivel de CLÚSTER — `SOFTWARE`
- **Componente:** api (tests) · **Detectada por:** `T-2.78.a` (2026-08-14)
- `tests/ops/test_restore_check.py` hace `ALTER ROLE takab_app RENAME TO takab_app_probe`. Los
  roles **no son por base: son del clúster**, así que mientras ese test corre **ninguna otra base
  del mismo Postgres tiene un rol `takab_app`**.
- **Consecuencia medida:** no se puede verificar una migración contra base limpia mientras la
  suite corre, **aunque sea otra base**. Es de la familia de `T-2.115` y `T-2.122` —el veredicto
  depende de algo que no está en el test— pero peor: **cruza la frontera de la base**, que es
  justo la que todo el aislamiento de la suite da por buena.
- Hoy no rompe nada porque la suite es secuencial; **el día que alguien la paralelice, sí**.
- **Criterios de aceptación:**
  - [x] El test acredita lo mismo sin renombrar un rol del clúster, o **declara** que exige
        exclusividad y algo lo impone.
  - [x] Un test que falle si otro vuelve a renombrar un rol compartido.

### [x] T-2.141 · El aviso de backup base llega cuando ya no hay ventana — `SOFTWARE`
- **Componente:** infra · **Detectada por:** `T-2.72.b` (2026-08-13), **al implementarla**
- El umbral que pedía `T-2.72.b` es `base_backup_interval_days × chain_margin`. Con los valores
  por defecto eso da **7×2 = 14 días**, que es **exactamente `wal_retention_days`**: cuando el
  correo llega, **la ventana de recuperación ya se cerró**. La alarma es correcta como *última
  línea* —dice «ya no puedes recuperar»— pero **no sirve de aviso**.
- El fallo que hay que cazar es **el primer backup base que falla**, no el decimocuarto día.
- **Criterios de aceptación:**
  - [x] Una segunda alarma a `base_backup_interval_days` (sin el margen), como **aviso**, con su
        severidad distinguida de la de `T-2.72.b`.
  - [x] Las dos derivan de las mismas variables; ninguna repite un número.
  - [x] Su entrada en `ALARM_CATALOG` con la razón de por qué son dos y no una.

### [x] T-2.72.d · Derivar la guardia de `treat_missing_data`, no enumerarla — `SOFTWARE`
- **Componente:** infra + api · **Depende de:** —
- `modules/observability/tests/treat_missing_data.tftest.hcl` **enumera** las alarmas: una
  alarma nueva no obtiene automáticamente su aserción y puede nacer sin que nada lo diga. El
  patrón correcto ya existe al lado: `api/tests/ops/test_muting.py` deriva la lista del propio
  `.tf` y pone en rojo cualquier alarma sin clasificar.
- Y esa guardia derivada tiene su propio límite, que va en la misma ficha: **su ámbito es UN
  solo archivo** (`observability/main.tf`). Una alarma declarada en otro módulo nace sin
  clasificar y nada lo delata. Hoy no hay ninguna — comprobado por grep — y por eso es deuda y
  no defecto.
- **Criterios de aceptación:**
  - [x] La lista de alarmas se deriva del `.tf`; una alarma sin aserción de `treat_missing_data`
        pone el test en rojo.
  - [x] El ámbito deja de ser un solo archivo.

### [x] T-2.73.b · Higiene de RLS: `tenant_retire_codes` sin FORCE y 7 tablas con dueño superusuario — `SOFTWARE`
- **Componente:** db · **Depende de:** —
- Los sacó a la luz el verificador de T-2.73 y **no son deuda de restore**, son de esquema:
  - `tenant_retire_codes` (migración 0025) tiene RLS `ENABLE` **sin FORCE** y no es ninguna de
    las dos excepciones documentadas de Timescale. **No explotable hoy** —su dueño es
    `takab_migrator`, que no es superusuario ni tiene `BYPASSRLS`, medido `AJENAS=0`— pero el
    verificador lo avisa en cada corrida y la asimetría no tiene razón de ser.
  - 7 tablas pertenecen a `takab` (superusuario) en vez de a `takab_migrator`:
    `billing_meters_daily`, `commands`, `drills`, `drill_sites`, `gateway_config_state`,
    `notification_jobs`, `user_profiles` — migraciones posteriores a la 0001 que crean objetos
    sin `SET ROLE takab_migrator`. Riesgo **latente**: una migración futura con
    `SET ROLE takab_migrator; ALTER TABLE notification_jobs …` moriría con `must be owner`.
- **Criterios de aceptación:**
  - [x] Migración idempotente que pone FORCE y devuelve la propiedad, respetando los dos
        invariantes de `migrations-must-be-idempotent`.
  - [x] Confirmado contra la NUBE (allí el conector ya es `takab_migrator`, así que puede no
        diverger) antes de asumir que el defecto existe en producción.

> **Cerrada (2026-08-13), y el último criterio salvó la ficha: EL DEFECTO NO EXISTÍA EN
> PRODUCCIÓN.** Medido con `SET ROLE takab_migrator` —que es exactamente el conector de la nube,
> `rolsuper = f`—: una tabla creada por él **sin `SET ROLE`** ya queda a su nombre. Las 7 (más
> `reference_earthquakes`, **que la ficha no listaba**) son un **artefacto local** de migrar como
> superusuario. Y un `ALTER TABLE … OWNER TO` a ciegas **habría matado el `apply`**: sobre una
> tabla ajena da `must be owner of table`.
>
> Por eso `0039` **no transfiere a ciegas**: guarda con `pg_has_role` y degrada a `RAISE NOTICE`.
> Verificado con el conector de la nube simulado: *«0 movidas, 1 saltadas»*, **sin ERROR**. El
> alcance se deriva del catálogo, no de la lista de la ficha — que estaba corta.
>
> **⚠️ Y EL `FORCE` QUE PEDÍA ESTA FICHA HABRÍA SIDO UNA REGRESIÓN FUNCIONAL.** Medido con
> `app.role='tenant_admin'`:
>
>     app_verify_retire_code(tenant,'SECRETO-123')  SIN FORCE → t
>     ALTER TABLE tenant_retire_codes FORCE ROW LEVEL SECURITY;
>     app_verify_retire_code(tenant,'SECRETO-123')  CON FORCE → f
>
> `SECURITY DEFINER` cambia el **usuario**, no los GUC: con `FORCE`, el dueño queda sujeto a la
> única política, que exige `takab_superadmin`. Poner `FORCE` **no endurece nada — deja sin poder
> retirar un gabinete a quien tiene derecho**. La decisión ya estaba escrita en la migración 0025
> y en `db/schema.sql` (el ÚNICO `NO FORCE` explícito del esquema).
>
> El arreglo fue **al verificador**: `Expectations.no_force` se deriva del `NO FORCE` **escrito**,
> no de la ausencia de la línea de `FORCE` —que es lo que produce un olvido—, así que una tabla no
> declarada **sigue avisando**.

### [x] T-2.73.c · El cuelgue intermitente de `test_retire_code.py` — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** api (tests) · **Depende de:** —
- Reproducido **5/5** por el auditor: `test_solo_el_superadmin_rota_el_codigo` deja una conexión
  `idle in transaction` tras `app_verify_retire_code`, y el TRUNCATE del teardown se bloquea
  para siempre pidiendo el `ACCESS EXCLUSIVE` de `audit_log`. En la suite completa no se
  manifiesta, así que es una carrera, no un fallo determinista. **Misma familia que el hallazgo
  A-3** de la auditoría de cierre.
- **Criterios de aceptación:**
  - [x] La conexión lateral cierra su transacción, o el fixture la cierra por ella.
  - [x] El fichero corre en aislamiento 10 veces seguidas sin colgarse.

> **Cerrada (2026-08-10), y la ficha se equivocaba de culpable: el test era la VÍCTIMA.**
> Es un **interbloqueo a tres bandas que PostgreSQL no puede detectar**. El request lee
> `audit_log` (`retire_code.py:105`) y con eso sostiene su ACCESS SHARE toda la transacción;
> con esa transacción abierta llama a `audit_out_of_band_async`, que abre una **conexión
> LATERAL** para escribir en la misma tabla. Si entre medias alguien pide el ACCESS EXCLUSIVE
> (el `TRUNCATE` de un teardown, un `VACUUM FULL`, una migración), se encola detrás del request
> y **la lateral se encola detrás de él**. El ciclo se cierra **fuera de la base**, así que el
> detector de interbloqueos no lo ve: la conexión del request está `idle in transaction`, no
> esperando un lock.
>
> `audit_out_of_band_async` declaraba «best-effort» en su docstring y **no tenía ni tope de
> espera ni captura**: la espera era literalmente infinita. Ahora la lateral fija `lock_timeout`
> y **cede** — se pierde el contador, que queda en el log, no el 403 ni la conexión. Captura
> solo `SQLAlchemyError`: un error de Python debe seguir siendo ruidoso o el veto del
> contract-test se vuelve decorativo.
>
> **El «5/5 reproducible» tenía su propia causa:** al colgarse, el proceso pytest **sobrevive a
> la muerte de su padre** y envenena la base, así que la corrida siguiente se cuelga en el primer
> `_cleanup()` — que es el del test acusado. De ahí la atribución.
>
> Los fixtures se blindan igual (`lock_timeout` en el TRUNCATE, `dispose` en `finally`). El test
> de regresión **tiene dientes**: con el tope a 0 se cuelga para siempre.
>
> **Hermano declarado, sin revisar:** `commands/rejection_audit.py:16` dice explícitamente que
> sigue el mismo patrón de conexión lateral — ver `T-2.112`. Y la conexión **del request** sigue
> sin tope: un `lock_timeout` global en `get_tenant_conn` es decisión de producción, fichada en
> `PENDIENTES-MAURICIO.md`.

### [ ] T-2.74 · `G-09` · restore real, RTO medido y publicado — `HUMANO-AWS`
- **Componente:** operación · **Depende de:** T-2.73, **T-2.73.a** · **Cubre `G-09`.**
- **Decisión:** [`D-17`](DECISIONES-MAURICIO.md#d-17) — la ventana AWS se parte en **dos**, y esta ficha es la segunda (~3 h).
- **Vive fuera del carril de gates a propósito:** es el único de los diez que **no exige manos
  en el gabinete** — se acredita con una ventana AWS sobre software que sí controlamos
  (`T-2.72`/`T-2.73`). Está anotado en la nota de la Fase 2.11 para que quien busque los diez
  gates ahí lo encuentre.
- **No entres a la ventana sin `T-2.73.a`**: sin la huella del origen el verificador devuelve
  INDETERMINADO y la acreditación sale a medias.
- **Criterios de aceptación:**
  - [ ] Procedimientos **A, B y C (PITR)** ejecutados de verdad contra el entorno real. El C es
        nuevo y el que más sorpresas puede dar: el sufijo de compresión de los WAL y el layout
        interno de barman hay que medirlos contra el bucket real.
  - [ ] El **primer `barman-cloud-backup`** lanzado a mano y supervisado (es pesado sobre un
        `t4g.small`; el cron semanal lo tomaría en ≤7 días si nadie lo lanza).
  - [ ] Confirmado a los ~15 min que la alarma de archivado **salió de INSUFFICIENT_DATA** — la
        lección de `ghost_gateways`: una alarma nacida ahí se queda ahí para siempre, sin
        transición y sin correo.
  - [ ] RPO/RTO **medidos** y escritos en el §8 del runbook de backup.
  - [ ] `G-09` marcado en la tabla de gates de `RUNBOOK-auditoria-cierre.md`.

## Fase 2.7 · Canales reales de notificación

### [x] T-2.75 · Un canal simulado deja de mentir — `SOFTWARE`
- **Componente:** api · **Depende de:** —
- **La más importante y la más barata de toda la ruta.** Hoy
  `api/src/takab_api/notify/providers.py:134-135` registra `SimulatedProvider("whatsapp")` y
  `SimulatedProvider("sms")`, y el simulado **marca los jobs `sent` sin enviar nada**. El
  canal email ya aprendió la lección por las malas —el 13/07 hubo correos "enviados" que nadie
  recibió, y por eso hoy grita al arrancar (`:124-131`)— pero **SMS y WhatsApp siguen
  callando**. Un tablero que dice "notificado" cuando no se notificó a nadie es peor que uno
  que no dice nada.
- **Criterios de aceptación:**
  - [x] Un canal simulado **no puede marcar `sent`**: marca `simulated` y se ve como tal en la
        consola y en `incident_actions`.
  - [x] En producción, un canal simulado **grita** al arrancar, como ya hace email.
  - [x] Test: job por canal simulado ⇒ jamás aparece como entregado.

> **Cerrada (2026-08-08), y la pregunta se le hace al PROVIDER, no a una lista de canales.**
> El guard vive en `orchestrator.py:546`, **antes** de bifurcar entre push y send, y lee
> `getattr(provider, "simulated", True)` (`providers.py:46-55`): el default bajo incertidumbre
> es la peor causa — un provider que no se declara **no hereda presunción de entrega**. El
> `UPDATE` a `simulated` no toca `sent_at` ni `attempts` (`:230-237`), el dominio del CHECK se
> **amplió** en vez de relajarse (`0032_notification_simulated.py:42-59`, cuyo `downgrade`
> degrada `simulated`→`failed`, jamás a `sent`), y la cascada **no se da por satisfecha con un
> simulado**: el SQL de "ya satisfecha" exige `status='sent'`.

### [x] T-2.75.a · La consola no sabe qué canal es real, y el día que lo sea mentirá al revés — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** api + web · **Depende de:** T-2.75 · **Detectada por:** auditoría de la Fase 2.7
  (2026-08-08)
- **El defecto, medido.** `web/src/features/tenants/NotificationChannels.tsx:16-25` rotula
  WhatsApp y SMS con **«SIMULADO en el MVP» como texto ESTÁTICO**. Hoy es verdad. El día que
  `T-2.76.a`/`T-2.77.a` carguen credenciales, el canal pasará a ser real **y el rótulo seguirá
  diciendo que es simulado** — la regla de oro 7 al revés: un operador que necesita avisar por
  SMS leerá que no sirve y buscará otra vía.
- **La causa raíz no es el rótulo: es que no hay a quién preguntar.** Ningún endpoint expone el
  estado real de los providers. `build_providers()` ya lo sabe en el arranque del worker —
  incluso lo **grita** (T-2.75) — pero esa verdad muere en el log.
- **Asimetría hermana, en la otra superficie.** `shared/sdk-ts/src/bms.ts:84-85` promete en su
  comentario que «la bandera del payload MANDA sobre el mapa», y para un `kind` **conocido** el
  mapa gana: un `notify_sent` con `payload.simulated:true` se pintaría «ENVIADA». Hoy el
  orquestador nunca escribe eso, así que es latente — pero `IncidentTimeline.tsx:50-57` sí da
  prioridad a la bandera, o sea que **las dos superficies discrepan**. Se arregla con el mismo
  cambio o se queda como trampa para el siguiente.
- **Criterios de aceptación:**
  - [x] Un endpoint declara, por canal, si el provider es real o simulado — **derivado del
        registro ya construido**, jamás una lista escrita a mano en la web.
  - [x] La consola lo pinta desde ese dato. Un canal sin dato se pinta `S/D`, **nunca «real»**.
  - [x] Test: cambiar un provider de simulado a real **cambia lo que pinta la consola**, sin
        tocar la web. Es el test que hoy no puede existir.
  - [x] `bms.ts` y `IncidentTimeline.tsx` resuelven `simulated` con la misma regla, anclado por
        un test que use un `kind` conocido **con** la bandera puesta.

> **Cerrada (2026-08-10).** `GET /notify/channels` publica la verdad **derivada del registro**:
> `channel_reality()` recorre `build_providers()` y le pregunta a cada provider con el mismo
> `is_simulated` del guard de T-2.75. **Ni una lista de canales** — el sexto que alguien enchufe
> aparece solo, y con la presunción correcta (simulado) si no se declara. Se congela en
> `create_app()` porque es configuración del PROCESO: cambia con un despliegue, no entre dos
> peticiones. De paso la API hereda el grito de arranque.
>
> **El test del criterio 3 cierra la cadena por un fichero de escenarios** que la API produce
> byte a byte y la consola renderiza: mover un provider a real pone rojo el test de Python, y
> arreglarlo cambia lo que pinta la consola **sin tocar una línea de `web/`**. Un mock
> complaciente no puede ponerse rojo por un cambio en Python.
>
> **La asimetría de `bms.ts` tenía TRES superficies, no dos.** La tercera es el panel táctico
> **móvil**, que deriva de esa vista si la sirena está sonando para habilitar el preflight de
> SILENCIAR. Al hacer que la bandera gane sin excepción, esa precondición **dejó de darse por
> satisfecha sola** con una acción de simulacro. Un arreglo en la consola tapó un agujero en la
> superficie que decide si se puede silenciar una sirena.
>
> **RESERVA declarada, no defecto:** `takab_support` y `gov_operator` llegan a `/tenants` pero no
> tienen `edit_thresholds`, así que verán `S/D`. Es honesto —nunca «real»—, pero darles la verdad
> exige una **acción de lectura nueva en la matriz**, y eso es decisión de producto.

### [x] T-2.76 · SMS real — `SOFTWARE` (+ `HUMANO-AWS` para credenciales)
- **Componente:** api + infra · **Depende de:** T-2.75
- **Criterios de aceptación:**
  - [x] Proveedor real detrás de la misma interfaz `NotifyProvider`; el orquestador no cambia.
  - [x] Reintentos, coste por mensaje y límite de tasa **declarados**, no descubiertos en la
        factura.
  - [x] Evidencia de entrega en `incident_actions` con latencia y `deadline_met`, como el resto.
  - [x] Sin secretos en git (regla de oro 6).

> **Cerrada en código (2026-08-08).** El alta de la cuenta y del número mexicano NO es parte de
> esta ficha: tiene la suya, **T-2.76.a**, que sigue `[ ]`. Lo acreditado aquí: enchufe de una
> línea (`providers.py:229`) y un test que **lee la fuente del orquestador** y se pone rojo si
> aparece una rama `"sms"` dentro de él; el headroom del SLA se **deriva** de `CASCADE_ORDER` en
> vez de copiarse; el provider **no reintenta por dentro** y hay un test que cuenta las llamadas;
> la guarda de duplicados distingue *ambiguo* (5xx/timeout/2xx sin sid ⇒ recuerda y escala) de
> *rechazo explícito* (4xx ⇒ sí reintenta); y el token se **depura** de errores y logs, con un
> test que lo inyecta en un 401 y comprueba que no sale.
>
> **RESERVA declarada, no defecto:** `notify_sent` de SMS significa «aceptado por Twilio», no
> «entregado en el teléfono» — está escrito en el módulo. El `MessageSid` **no se persiste**;
> queda pendiente de `T-2.77.b`, que sigue abierta.

> **Proveedor: TWILIO** (decisión ratificada 2026-08-07). Código en
> `api/src/takab_api/notify/twilio.py`; sin credenciales el canal cae a `SimulatedProvider`
> y los jobs quedan `simulated`, jamás `sent` (T-2.75). El orquestador **no se tocó**: hay un
> test que se pone rojo si aparece una rama `"sms"` dentro de él.
>
> **Números declarados** (verificados contra la documentación de Twilio el 2026-08-07; fijados
> en `TWILIO_LIMITS` con un test que se pone rojo si cambian):
>
> | Qué | Cuánto | Fuente |
> |---|---|---|
> | Coste por **segmento** a MX (long code) | **USD 0.1819** | `twilio.com/en-us/sms/pricing/mx` |
> | Número mexicano | USD 6.50/mes (local) · 15/mes (móvil) | ídem |
> | Límite de tasa asumido | **1 segmento/s** (peor caso documentado) | `docs/messaging/guides/scaling-queueing-latency` |
> | Caducidad en cola por defecto | **10 h (36 000 s)**, luego error 30001 | `docs/messaging/guides/account-based-throughput-overview` |
> | `ValidityPeriod` que se envía | **300 s** (rango legal 1..36 000) | `docs/messaging/api/message-resource` |
>
> **El coste, que es un criterio y no un comentario.** Con el presupuesto de USD 50/mes, a
> 0.1819 el segmento, la cuenta entera compra **274 segmentos al mes**. **No se impone un tope
> duro que corte el canal**: cortar el aviso de un sismo por presupuesto es una decisión de
> producto y se toma con nombre y firma, no dentro de un provider. Lo que sí se hace es (a)
> **declarar** la cifra en el log de arranque y (b) hacer el gasto masivo **imposible por
> construcción**: `notifications.sms.to` es **un solo número** por tenant (la guardia del SOC,
> no el altavoz de los ocupantes — a los ocupantes los despierta el push, que no cuesta por
> mensaje), y el provider **rechaza** un destino con lista o comas. Un incidente = un SMS.
> Si algún día se quiere SMS masivo a ocupantes, es otra ficha y empieza por el presupuesto.
>
> **Coste oculto medido:** se cobra por SEGMENTO y **un solo acento fuera de GSM-7 pasa el SMS
> entero a UCS-2** (160 → 70 caracteres por segmento): «ALERTA SÍSMICA» (la `Í` no está en
> GSM-7; la `É` y la `Ñ` sí) **duplica** la factura, y **triplica** si el texto llenaba el
> segmento. Y como el límite de Twilio se cuenta en *segmentos* por segundo, también duplica
> el consumo del plazo. Por eso el cuerpo se pliega a GSM-7 y se acota a **un** segmento.
>
> **El plazo, contra el límite de tasa.** El plan da al SMS la ventana
> `notify_sms_deadline_s − notify_step_s × posición` = **10 s**. A 1 MPS eso son **10
> segmentos**: el SLA de 30 s es **alcanzable** mientras no coincidan más de ~10 SMS sobre el
> mismo número. Por encima queda **declarado inalcanzable** (`sms_deadline_headroom()` lo
> calcula y lo dice; no se promete en silencio). Si se llega ahí, las salidas son comprar
> throughput (short code: 100 MPS, **14 semanas** de alta) o repartir en varios números —
> ficha aparte, no un parche. Twilio **no publica** el MPS de long code en México y sí
> documenta que la entrega doméstica por long code allí es *best-effort and may be unreliable*
> (`twilio.com/en-us/guidelines/mx/sms`): de ahí el peor caso.
>
> **Reintentos.** El provider **no reintenta por dentro** (Twilio ya reintenta contra la
> operadora y el orquestador ya reintenta con backoff; una tercera capa multiplicaría
> duplicados). Twilio **no ofrece clave de idempotencia** en el recurso Message, así que la
> pone el dominio: `(destino, incidente)`. Un fallo **ambiguo** (5xx, timeout, respuesta
> ilegible) pudo haber creado el mensaje ⇒ se recuerda y el siguiente intento **escala al
> correo en vez de duplicar**; un rechazo **explícito** (4xx) demuestra que no se creó nada ⇒
> sí se reintenta. La memoria caduca con el `ValidityPeriod`.
>
> - **PENDIENTE DERIVADO — la entrega CONFIRMADA no está en esta ficha.** El `POST` devuelve
>   `queued`/`accepted`; la única palabra de Twilio que significa «llegó al teléfono» es
>   `delivered`, y **no viaja en esa respuesta**: llega por *status callback*. Por eso, hoy,
>   **un `notify_sent` de sms significa «aceptado por Twilio», no «entregado»** — igual que un
>   `notify_sent` de email significa «SES lo aceptó», no «está en la bandeja». El parámetro
>   `StatusCallback` ya viaja si hay URL configurada, para que ese día no haya que tocar el
>   provider. Lo que falta —y necesita **su propia ficha, con su conteo**— es: endpoint público
>   que reciba el callback, validación de `X-Twilio-Signature`, mapeo `MessageSid` → job y
>   dónde escribir el desenlace tardío. **`T-2.78` no puede acreditar «entrega» por SMS hasta
>   entonces**: puede acreditar que el mensaje salió y que la persona contestó, que es lo que
>   de verdad mide esa tarea, pero no puede llamar «entregado» a un `queued`.
> - **PENDIENTE `HUMANO-AWS`:** alta de la cuenta Twilio, compra del número mexicano y carga
>   de `TAKAB_API_NOTIFY_SMS_AUTH_TOKEN` en Secrets Manager. **Nunca en `deploy/cloud/deploy.sh`
>   ni en ningún archivo del repo** (regla de oro 6).

### [ ] T-2.76.a · Alta de la cuenta Twilio y del número mexicano — `HUMANO-AWS` + `LEGAL`
- **Componente:** cuenta de terceros + Secrets Manager · **Depende de:** T-2.76 (código listo)
- **Decisión:** [`D-13`](DECISIONES-MAURICIO.md#d-13) — el teléfono de soporte es un número Twilio mexicano.
- **Por qué es tarea propia y no una nota:** el código de T-2.76 está completo y probado, pero
  **sin credenciales el canal SMS cae a `simulated`** — escala al correo y deja huella honesta,
  que es lo correcto, pero significa que **hoy nadie recibe un SMS**. Mientras esto no se cierre,
  la cadena de notificación tiene un canal menos del que el tablero da por disponible.
- **Criterios de aceptación:**
  - [ ] **Alta de la cuenta Twilio** y verificación de la identidad del negocio.
  - [ ] **Compra del número mexicano.** Long code: 6.50 USD/mes local o 15 USD/mes con prefijo
        móvil. Ojo: Twilio documenta que la entrega doméstica en México por long code es
        *«best-effort and may be unreliable»* — si eso no basta para un canal de vida, la
        alternativa es **short code** (100 MPS) con **~14 semanas de alta**, y entonces esta
        ficha se convierte en un plazo de calendario, no en un trámite.
  - [ ] **`TAKAB_API_NOTIFY_SMS_AUTH_TOKEN` en Secrets Manager**, y el resto de ajustes en el
        despliegue. **Nunca en `deploy/cloud/deploy.sh` ni en ningún archivo del repo**
        (regla de oro 6).
  - [ ] **Verificar tras el alta que el canal ASCIENDE a real**: el arranque deja de gritar
        «SMS simulado» y un incidente de prueba produce `notify_sent` con su latencia, no
        `notify_simulated`. Media credencial es cero credencial y grita en ERROR — está
        anclado por test, pero hay que verlo en el entorno desplegado.
  - [ ] **Decidir el tope de gasto.** $50/mes ÷ $0.1819 por segmento = **274 segmentos al mes**.
        El código **no corta el canal por presupuesto a propósito**: cortar un canal de vida por
        dinero es una decisión con firma, no de un provider. Hoy el gasto masivo es imposible
        por construcción (`notifications.sms.to` es UN destinatario por tenant: la guardia del
        SOC, no los ocupantes), pero **si el producto quiere algún día SMS a ocupantes, esa
        aritmética cambia entera** y hay que decidir el tope antes, no en la factura.

### [~] T-2.77 · WhatsApp Business — `SOFTWARE` (+ `LEGAL`/`HUMANO-AWS` para el alta)
- **Componente:** api · **Depende de:** T-2.75
- **Criterios de aceptación:**
  - [~] Plantillas **versionadas** en el repo: sí, y con candado real (el sello es el digest
        SHA-256 del bloque `template`, y un test mueve una coma y comprueba que la plantilla se
        **desaprueba**). **APROBADAS: no**, y a propósito: la única del repo está `PENDING`
        porque nadie la ha sometido a Meta. Es lo que cierra `T-2.77.a`, y es la razón —la
        única— de que esta ficha sea `[~]` y no `[x]`.
  - [x] Degradación explícita si la plantilla es rechazada: **el canal cae, no finge**.
  - [x] Evidencia de entrega igual que los demás canales.

> **Por qué `[~]` y no `[x]` (2026-08-08).** El criterio dice literalmente «plantillas
> **APROBADAS**». Sellar ese criterio sin la aprobación de Meta sería la misma clase de mentira
> que T-2.75 existe para erradicar. El código está completo y probado; lo que falta es un gate
> externo.
>
> **Lo acreditado, que es lo fino de esta ficha:** `simulated` es una **propiedad derivada**, no
> un atributo — por eso el canal cae **en caliente** cuando Meta pausa la plantilla. Se atienden
> las dos puertas, y la segunda es la que nadie ve venir: un **HTTP 200 que dice `paused` por
> dentro**. Un `if response.is_success: return` lo habría contado como enviado. Los 4xx de
> plantilla se tratan **por rango** (132xxx), no por lista, así que un código nuevo de Meta
> tampoco se cuela. Y sin `opt_in.at` en el destino el provider **se niega a enviar** y lo deja
> escrito como `notify_failed`.
>
> **RESERVA declarada, no defecto:** `notify_sent` significa «aceptado por Meta». El `wamid`
> **no se persiste**; queda pendiente de `T-2.77.b`, que sigue abierta.

> **Decisión: WhatsApp Business Cloud API directa de Meta** (`notify/whatsapp.py`), enchufada
> donde estaba `SimulatedProvider("whatsapp")`, mismo contrato `NotifyProvider`, **cero líneas
> del orquestador** (hay un test que lee su fuente y exige que no aparezca ninguna rama
> `"whatsapp"` entrecomillada). Todo lo de abajo se verificó contra la documentación de Meta el
> **2026-08-07**, con la URL pegada a cada dato.
>
> **Lo que hace este canal distinto a todos los demás: NO SE PUEDE IMPROVISAR TEXTO.** *"Template
> messages are the only type of message that can be sent to WhatsApp users outside of a customer
> service window"* (`developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview`).
> Esa ventana la abre **el usuario**: *"When a WhatsApp user messages you or calls you, a 24-hour
> timer called a customer service window starts... When the window closes, you can only send
> pre-approved template messages"* (`.../whatsapp/messages/send-messages`). Aquí el destinatario
> es la guardia del SOC y **nunca escribe primero**, así que **la ventana está SIEMPRE cerrada**:
> este canal es 100 % plantilla, sin caso alterno. Un texto libre rebotaría con el error 131047.
>
> | Dato | Valor verificado | Fuente |
> |---|---|---|
> | Endpoint | `POST https://graph.facebook.com/{Version}/{Phone-Number-ID}/messages` | `.../reference/whatsapp-business-phone-number/message-api` |
> | Respuesta del POST | `messages[0].message_status` ∈ `accepted` \| `held_for_quality_assessment` \| `paused`; `accepted` = *"accepted by WhatsApp and is being processed"* | ídem |
> | Categorías (enum de alta) | `AUTHENTICATION`, `FREE_SERVICE`, `MARKETING`, `UTILITY` | `.../reference/whatsapp-business-account/message-template-api` |
> | Estados de plantilla (enum) | `APPROVED, ARCHIVED, DELETED, DISABLED, IN_APPEAL, LIMIT_EXCEEDED, PAUSED, PENDING, PENDING_DELETION, REJECTED` | ídem |
> | Campos de alta | `name` (*"lowercase alphanumeric and underscores only"*), `language`, `category`, `components`, `parameter_format`, `message_send_ttl_seconds` | ídem |
> | Cuerpo | *"The only required component is the body component"* · *"Maximum of 1024 characters"* | `.../whatsapp/templates/components/` |
> | TTL de una utility | default **30 días**; configurable **30 s .. 12 h**; se fija **al crear**, no al enviar | `.../whatsapp/templates/time-to-live` |
> | Facturación | **"You are only charged when a template message is delivered"**, por mensaje desde el 2025-07-01 | `.../whatsapp/pricing` |
> | Opt-in | *"You may only contact people on WhatsApp if: (a) they have given you their mobile phone number; and (b) you have received opt-in permission..."* | `whatsappbusiness.com/es-la/policy/` (301 de `business.whatsapp.com/policy`) |
> | Webhooks de estado | *"each outgoing message can have up to three separate webhooks (one for a status of sent, one for delivered, and one for read)"* | `developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components` |
>
> **NO existe una categoría de emergencia — se comprobó, no se supuso.** El enum solo admite
> `AUTHENTICATION`, `FREE_SERVICE`, `MARKETING` y `UTILITY`, y de las creables Meta dice *"Each
> template must be categorized as authentication, marketing, or utility"*. La correcta es
> **`UTILITY`**, que es donde Meta pone explícitamente lo no promocional *esencial o crítico*:
> **public safety (severe weather, crisis response)**
> (`.../whatsapp/templates/template-categorization`). **Y la categoría no es contabilidad: es
> entregabilidad.** Si la plantilla acabara en `MARKETING`, un destinatario que haya rechazado
> marketing **dejaría de recibir el aviso de un terremoto** (error 131050, *"Recipient opted out
> of marketing messages"*). Peor: Meta **recategoriza sola** — *"WhatsApp introduced a recurring
> process to identify and update approved templates that should be of a different category"*.
> Por eso el artefacto lleva `allow_category_change: false` y hay un test que se pone rojo si
> alguna plantilla de alerta deja de ser `UTILITY`.
>
> **El artefacto de plantilla: `api/src/takab_api/notify/whatsapp_templates/*.json`.** Un fichero
> por plantilla, con tres bloques: `template` —**literalmente** el cuerpo de
> `POST /<WABA_ID>/message_templates`—, `binding` —de dónde sale cada `{{n}}`, nuestro— y
> `approval` —el sello—. **JSON y no YAML ni un literal de Python justamente por eso**: si el
> fichero del repo no es *exactamente* lo que se le manda a Meta hay una traducción en medio, y
> la traducción es el sitio donde el texto aprobado y el texto del repo se separan sin que nadie
> lo note; un literal de Python, además, invita a meter f-strings dentro de lo que tiene que
> estar congelado.
>
> **El candado que hace que cambiar el texto EXIJA volver a aprobar.** Meta guarda el texto;
> nosotros solo enviamos el **nombre**. Editar el cuerpo en el repo sin volver a pasar por Meta
> **no cambia lo que lee la gente**: crea una divergencia silenciosa entre lo que el repo afirma
> y lo que llega al teléfono. Por eso el sello es el **digest SHA-256 del bloque que Meta
> revisó**: mover una coma mueve el digest y la plantilla deja de estar aprobada en el acto
> (test: `test_tocar_el_texto_de_una_plantilla_aprobada_la_DESAPRUEBA`). Dicho con honestidad:
> atrapa la deriva accidental, que es la que ocurre; no a quien reescriba el digest a propósito.
>
> **Hoy la plantilla está `PENDING` a propósito, y por eso el canal está caído.** Nadie la ha
> mandado a Meta (falta `T-2.77.a`). No se pone `APPROVED` "para probar": eso es exactamente la
> mentira que `T-2.75` erradicó. El resultado es que el criterio 2 **funciona desde el minuto
> cero**: hay credenciales o no, pero sin plantilla aprobada el canal se declara `simulated`, el
> job queda `simulated` con `sent_at` en NULL, escribe `notify_simulated` (ámbar) y **escala al
> SMS**.
>
> **Degradación DERIVADA, no enumerada.** `simulated` es una **propiedad**, no un atributo:
> vale "no hay ninguna plantilla utilizable". De ahí sale que el canal caiga **en caliente**
> cuando Meta mata la plantilla, por dos puertas distintas que hay que atender las dos:
> 1. **Un 4xx de la familia 132xxx** — `132015` *"Template paused due to low quality"*, `132016`
>    *"Template permanently disabled after repeated pauses"*, `132001` no existe o no aprobada,
>    `132007` viola la política, `132000` número de parámetros, `132012` formato
>    (`developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/`). Se cuarentena
>    **por familia, no por lista**: el 132xxx que Meta añada mañana hereda el trato solo.
> 2. **Un HTTP 200 que dice `paused` por dentro** — trampa fina de esta API: la respuesta trae
>    `message_status` y uno de sus tres valores documentados es `paused`. Un
>    `if response.is_success: return` lo habría contado como enviado.
>
> Y la distinción importa: `failed` reintenta con backoff, `simulated` no. **Martillear una
> plantilla pausada no la despausa — solo empeora su calificación de calidad en Meta.**
>
> **Publicado ≠ entregado, otra vez.** De los tres valores del POST, **ninguno significa "llegó
> al teléfono"**; el mejor, `accepted`, es literalmente *"accepted by WhatsApp and is being
> processed"*. `delivered` solo llega **después y por webhook**. La prueba más fuerte de que la
> distinción es real la da la propia facturación de Meta: **solo cobra los mensajes
> entregados**. Nuestra contabilidad no puede ser más generosa que la suya. Así que hoy un
> `notify_sent` de whatsapp significa **"aceptado por Meta"**, igual que el de sms significa
> "aceptado por Twilio" y el de email "SES lo aceptó". El `wamid` se guarda desde el minuto uno
> aunque no haya webhook: es lo único con lo que ese día se podrá casar el desenlace tardío.
> `held_for_quality_assessment` **no cuenta como envío**: Meta lo retuvo y puede salir o no —
> el default ante lo desconocido es la peor causa.
>
> **Coste: declarado hasta donde se pudo verificar, y NO más.** Meta factura por mensaje
> entregado, por categoría, desde el 2025-07-01, y las utility dentro de una ventana de servicio
> abierta son gratis — aquí la ventana está siempre cerrada, luego **siempre se paga**. La
> tarifa concreta de México (código 52) vive en un CSV/PDF descargable que **no se pudo leer**,
> así que **no se declara una cifra**: va en `T-2.77.a` junto al alta. Lo que sí está acotado por
> construcción, como en el SMS, es el volumen: `notifications.whatsapp.to` es **un** destino por
> tenant y el provider rechaza listas o comas. Un incidente = un mensaje.
>
> - **HALLAZGO DE COMPLIANCE — el opt-in, y no cabe entero aquí.** WhatsApp condiciona
>   **cualquier** contacto a un consentimiento previo, y el opt-in debe *"clearly state that a
>   person is opting in to receive communication from the business"* y *"clearly state the
>   business's name"* (`.../whatsapp/getting-opt-in`). **Hoy TAKAB no tiene modelo de
>   consentimiento**: `notifications.whatsapp.to` es un teléfono suelto en el `rule_set`, sin
>   quién, sin cuándo y sin prueba. Eso es la **Fase 2.8 llamando a la puerta** (`T-2.79`, aviso
>   versionado + consentimiento con versión aceptada y registro append-only): **el opt-in de
>   WhatsApp es un consentimiento más de ese motor**, y cuando `T-2.79` exista, este canal debe
>   leerlo de ahí en vez de del `rule_set`. Mientras tanto se exige una constancia mínima en el
>   destino (`opt_in.at`, el instante) y **sin ella el provider se niega a enviar**. No es
>   burocracia: enviar sin opt-in no rebota un mensaje — degrada la calidad del número y puede
>   **tumbar el canal para todos los tenants a la vez**. Y la fecha no es adorno: un
>   consentimiento sin instante no se puede probar anterior al mensaje, luego no es un
>   consentimiento. El fallo queda **escrito** (`notify_failed`, rojo en la consola), no en
>   silencio.
> - **HALLAZGO `LEGAL` — a quién NO le deja Meta usar esta plataforma.** *"Prohibimos que
>   organismos de las fuerzas del orden, servicios militares, organismos de inteligencia y
>   agencias de seguridad nacional usen la Plataforma de WhatsApp Business"*
>   (`whatsappbusiness.com/es-la/policy/`). El producto se vende a **"Protección Civil, gobierno
>   y empresas"** (`CLAUDE.md §1`). Protección Civil no es fuerza del orden ni servicio militar,
>   pero **la frontera la traza Meta, no nosotros**, y el coste de equivocarse no es un mensaje
>   rebotado: es la cuenta cerrada y el canal muerto para toda la flota. **Antes de vender este
>   canal a un cliente de gobierno hay que confirmarlo por escrito con Meta** — va en
>   `T-2.77.a`. Para un hospital, una universidad o un corporativo no hay duda.
> - **PENDIENTE DERIVADO — la entrega CONFIRMADA no está en esta ficha**, exactamente igual que
>   en `T-2.76` y por el mismo motivo. Lo cierra `T-2.77.b`, que unifica los dos canales.
> - **PENDIENTE `HUMANO-AWS`/`LEGAL`:** alta del WhatsApp Business Account, número, aprobación de
>   la plantilla y `TAKAB_API_NOTIFY_WHATSAPP_ACCESS_TOKEN` en Secrets Manager. **Nunca en
>   `deploy/cloud/deploy.sh` ni en ningún archivo del repo** (regla de oro 6). Lo cierra
>   `T-2.77.a`.

### [ ] T-2.77.a · Alta del WhatsApp Business Account y aprobación de la plantilla — `HUMANO-AWS` + `LEGAL`
- **Componente:** cuenta de terceros + Secrets Manager · **Depende de:** T-2.77 (código listo)
- **Por qué es tarea propia y no una nota:** el código de T-2.77 está completo y probado, pero
  **hoy el canal WhatsApp está caído por partida doble**: no hay credenciales y, aunque las
  hubiera, la plantilla del repo está `PENDING` porque nadie la ha sometido a Meta. Cae a
  `simulated`, escala al correo y deja huella honesta — que es lo correcto—, pero significa que
  **hoy nadie recibe un WhatsApp**. Y aquí el trámite no es solo administrativo: **la aprobación
  de una plantilla es revisión humana de Meta y puede tardar hasta 24 h... o ser rechazada**.
- **Criterios de aceptación:**
  - [ ] **Alta del WhatsApp Business Account** y del número asociado (Cloud API).
  - [ ] **`LEGAL` — confirmar por escrito con Meta que Protección Civil / la dependencia de
        gobierno concreta NO cae en la prohibición** de *"organismos de las fuerzas del orden,
        servicios militares, organismos de inteligencia y agencias de seguridad nacional"*
        (`whatsappbusiness.com/es-la/policy/`). Si cae, **este canal no existe para ese cliente**
        y hay que decirlo antes de venderlo, no después.
  - [ ] **Someter la plantilla del repo** (`notify/whatsapp_templates/*.json`, bloque `template`
        tal cual) y, **cuando Meta la apruebe**, escribir el sello en el bloque `approval`:
        `status: APPROVED` + `approved_digest` = el digest del bloque sometido + `meta_template_id`.
        **Si Meta la rechaza, el texto se corrige y se vuelve a someter — no se sella a mano.**
  - [ ] **Verificar la categoría con la que Meta la aprobó de verdad.** Se pide `UTILITY`; Meta
        recategoriza por su cuenta y una alerta de sismo en `MARKETING` deja de llegar a quien
        haya rechazado marketing (131050). Volver a comprobarlo periódicamente.
  - [ ] **`TAKAB_API_NOTIFY_WHATSAPP_ACCESS_TOKEN` en Secrets Manager**, más
        `..._PHONE_NUMBER_ID` y `..._GRAPH_VERSION` en el despliegue. **Nunca en
        `deploy/cloud/deploy.sh` ni en ningún archivo del repo** (regla de oro 6).
  - [ ] **Averiguar y ESCRIBIR la tarifa de una utility a México** (código 52). T-2.77 la dejó
        sin declarar a propósito porque solo está en un CSV/PDF descargable: mejor un hueco
        explícito que una cifra inventada. Con ella, la aritmética del presupuesto como en
        `T-2.76.a`.
  - [ ] **Verificar tras el alta que el canal ASCIENDE a real**: el arranque deja de gritar
        "ninguna plantilla aprobada" y un incidente de prueba produce `notify_sent` con su
        latencia, no `notify_simulated`.
  - [ ] **Registrar el opt-in de cada destinatario** antes de encender el canal para un tenant:
        sin `opt_in.at` en `notifications.whatsapp`, el provider se niega y deja `notify_failed`.

### [x] T-2.77.b · Webhooks de estado de entrega (Meta + Twilio) — `SOFTWARE` + infra
- **Componente:** api + infra · **Depende de:** T-2.76, T-2.77
- **Por qué existe:** `T-2.76` lo pidió con todas las letras ("necesita **su propia ficha, con su
  conteo**") y `T-2.77` se topó con lo mismo. Hoy **tres canales dicen `notify_sent` queriendo
  decir "el proveedor lo aceptó"**: email ("SES lo aceptó"), sms ("Twilio lo encoló") y whatsapp
  ("Meta lo aceptó"). Ninguno de los tres puede afirmar que un humano lo tenga en la mano. Es
  honesto —está escrito en los tres sitios— pero es **una tarea sin hacer**, no un estado final.
- **Es una ficha sola y no dos porque el trabajo es el mismo tres veces**: un endpoint público
  que recibe un callback, valida su firma, casa un identificador de proveedor con un job y
  escribe un desenlace **tardío** — que es lo verdaderamente nuevo: hoy `notification_jobs` no
  tiene dónde poner "salió a las 12:00:03 y llegó a las 12:00:19".
- **Criterios de aceptación:**
  - [x] Endpoint público por proveedor, con **validación de firma**: `X-Twilio-Signature` en
        Twilio; el `hub.verify_token` + firma `X-Hub-Signature-256` de Meta.
  - [x] Mapeo **`MessageSid` → job** y **`wamid` → job**: hoy el `wamid` ya se guarda en el
        recibo del provider pero **no se persiste**; sin persistirlo no hay con qué casar nada.
  - [x] Columna(s) de desenlace tardío en `notification_jobs` (`delivered_at`, `last_status`) y
        **evidencia propia**: un `notify_delivered` distinto de `notify_sent`, porque son dos
        hechos distintos y la consola tiene que poder mostrar los dos.
  - [x] **Solo `delivered`/`read` cuentan como entrega.** `queued`, `sent`, `accepted` y
        `held_for_quality_assessment` no. Ya hay `is_delivery_confirmed()` en los dos providers
        con esa regla: este endpoint la reusa, no la reinventa.
  - [x] Un webhook **no autenticado o repetido** no altera nada (idempotencia por identificador
        de proveedor).
  - [x] Test: un job `sent` que recibe `failed`/`undelivered` **acaba en rojo en la consola**, no
        se queda verde para siempre. Ese es el caso que hoy no se ve y es el que más duele.

> **Cerrada (2026-08-13). Es la primera superficie PÚBLICA de la API** —el proveedor la llama, así
> que sale del sobre de Cognito— y por eso lo que más importa aquí no es el desenlace tardío sino
> **cómo se defiende**:
> - **La firma es la única autenticación.** Twilio: base64(HMAC-SHA1(url + params ordenados));
>   Meta: HMAC-SHA256 del **cuerpo crudo**. Las dos con `compare_digest`, y hay un test que
>   **prohíbe `==` leyendo la fuente**.
> - **La URL que se firma sale de la configuración, jamás de `Host`/`X-Forwarded-*`** — si se
>   reconstruyera de la petición, **quien llama controlaría parte del material firmado**.
> - **Un cuerpo sin firma válida no abre conexión.** El test **sabotea** la conexión para
>   probarlo, y se midió en rojo moviendo la apertura antes de la verificación.
> - **Firma mala e identificador inexistente son indistinguibles** —mismo código y mismo cuerpo,
>   comparados por el test—, o el endpoint sería un oráculo de qué jobs existen.
> - El escritor es una función `SECURITY DEFINER` acotada a «mover el desenlace de UN job hacia
>   adelante»: la API corre como `takab_app`, **sin UPDATE y con RLS default-deny**.
>
> **Los estados se ordenan por RANGO, no por «gana el último»**, que es lo que hace correctos los
> reenvíos y el desorden: un estado **no se pisa a sí mismo** (reenvío inerte), un `sent`
> retrasado **no borra** un `delivered`, `read` sube pero **no mueve `delivered_at`** —manda la
> primera confirmación—, y un estado desconocido **no toca nada y grita**.
>
> **Hallazgo cazado por correr contra base limpia, y es de los que no se ven venir:** poner
> `ALTER FUNCTION … OWNER TO takab_ingest` en `db/schema.sql` **mata la 0001**, porque ese cuerpo
> corre bajo `SET ROLE takab_migrator` y ese rol **no es miembro** de `takab_ingest`. Peor aún era
> la consecuencia de que la cesión fallara en silencio: la función correría **sin BYPASSRLS**, no
> vería ni una fila por RLS FORCE, y **el webhook contestaría «no reconozco esto» para siempre**.
> Ahora revienta el despliegue en su lugar.
>
> **Para que funcione en la nube hacen falta tres secretos y abrir el 443 a Twilio/Meta** — ver
> `PENDIENTES-MAURICIO §2`. **Sin ellos el endpoint responde 503 y lo grita**: no hay degradación
> silenciosa.

### [x] T-2.77.c · La cuarentena y la guarda de duplicados viven en la memoria de UN worker — `SOFTWARE`
- **Componente:** api · **Depende de:** T-2.76, T-2.77 · **Detectada por:** auditoría de la
  Fase 2.7 (2026-08-08)
- **El defecto, medido.** La cuarentena de plantillas de WhatsApp (`whatsapp.py:456-466`) y la
  guarda de duplicados de Twilio (`providers.py:63-104`) son **estado en proceso**. Dos
  consecuencias reales, ninguna teórica:
  1. **Al reiniciar el worker se olvida la cuarentena** y se vuelve a martillear una plantilla
     que Meta pausó — que es exactamente lo que **degrada su calificación de calidad** y termina
     costando el canal entero. La degradación en caliente de T-2.77 funciona; lo que no
     sobrevive es el recuerdo de haberla sufrido.
  2. **Con más de una instancia del worker la guarda de duplicados no existe entre instancias**,
     así que un SMS o un WhatsApp duplicado sigue siendo posible. Y el orquestador **ya asume
     varias instancias**: usa `pg_advisory_xact_lock` (`orchestrator.py:312`). O sea que el
     supuesto de "un solo worker" que sostiene esta guarda ya está contradicho por el código de
     al lado.
- **Criterios de aceptación:**
  - [x] La cuarentena sobrevive al reinicio del worker (persistida, no en memoria).
  - [x] La guarda de duplicados es **compartida entre instancias**, con la misma idempotencia por
        `event_id`/nonce que ya gobierna el edge→nube (regla de oro 3).
  - [x] Test que arranque **dos** orquestadores contra la misma DB y demuestre que el mensaje
        sale **una vez**. Sin ese test esto vuelve.
  - [x] Test que reinicie el provider y demuestre que la plantilla en cuarentena **sigue** en
        cuarentena.

> **Cerrada (2026-08-13).** La cuarentena vive en `notify_template_quarantine`, **sin
> `tenant_id`** —la plantilla es de la WABA del despliegue, no de un cliente— con la exención
> declarada en el censo de multi-tenancy, RLS activa y **nadie con DELETE**: levantarla es un acto
> humano.
>
> **La guarda de duplicados no estrenó tabla, y la razón es buena:** vive en
> `notification_jobs.inflight_until`, porque la clave `(destino, incidente)` **ya es** una fila de
> job. Así hereda tenant, RLS y retención de golpe — **y no crea un sitio nuevo con teléfonos que
> alguien tendría que borrar en un ARCO**.
>
> El test de las dos instancias tiene control de no-vacuidad: la B **no envía** el que la A ya
> intentó, **y sí envía** el incidente que nadie tocó. Medido en rojo desatando el estado: 3 caen.

### [ ] T-2.78 · SES fuera de sandbox + cadena on-call acreditada — `HUMANO-AWS`
- **Componente:** infra + operación · **Depende de:** T-2.76, T-2.77
- **Decisión:** [`D-12`](DECISIONES-MAURICIO.md#d-12) — dominio raíz **`takabailert.com`** (decidido como `.mx` y enmendado el 2026-08-21) con DNS en Route 53. Es el que la solicitud de producción de SES pide como `Website URL`.
- **Criterios de aceptación:**
  - [ ] SES fuera de sandbox con DKIM/SPF de dominio real.
  - [ ] **Acreditar la cadena on-call de punta a punta**: provocar una alarma real y que
        alguien reciba el aviso, cronometrado. A-4 dejó el topic SNS aplicado y confirmado
        (2026-07-13/14); esto acredita que **la persona** llega, no solo el mensaje.
  - [ ] Escalamiento escrito: quién es el segundo si el primero no acusa.
- **Procedimiento preparado (2026-08-07):**
  `takab-docs/runbooks/RUNBOOK-ses-produccion-y-cadena-oncall.md`. Trae los registros DNS con
  la doc de AWS citada por URL, el comando que provoca la alarma
  (`set-alarm-state` sobre `takab-dev-dlq-backfill`, la única del catálogo que ninguna ventana
  de mantenimiento puede silenciar), los **cuatro instantes** a cronometrar y la plantilla del
  escalamiento con sus huecos. Engancha además la verificación pendiente de T-2.60.a: es el
  mismo procedimiento.
- **Tres cosas que el runbook dejó por escrito y conviene saber antes de empezar:**
  - ~~**No hay dominio.**~~ **CADUCADO (2026-08-21).** Lo era cuando se escribió: la consola
    vivía en `sslip.io` *"sin Route53 ni dominio propio"* (`modules/serve/outputs.tf:9`) y la
    solicitud de producción de SES pide un `Website URL`. Hoy **`takabailert.com` está verificado
    con Easy DKIM RSA-2048**, con MAIL FROM propio en `bounce.takabailert.com` (su MX y su SPF) y
    DMARC publicado. Lo que sigue abierto es la salida del sandbox, que la decide AWS — no el
    dominio. Se deja escrito en vez de borrado: el bloqueo existió y explica por qué esta ficha
    estuvo parada.
  - **No hay acuse.** `POST /incidents/{id}/ack` acusa un INCIDENTE, no una alarma de
    operación; el cuarto instante se anota a mano. Ficha propia: `T-2.78.a`.
  - **Son dos cadenas.** CloudWatch→SNS→on-call no comparte código, destinatario ni permiso
    con `notify/orchestrator.py`. Acreditar una no dice nada de la otra — el hueco de
    `ses:SendEmail` de julio-2026 estuvo tapado exactamente por eso.

### [x] T-2.78.a · Acuse y evidencia de entrega de la cadena de operación — `SOFTWARE`
- **Componente:** infra + api · **Depende de:** —
- **Por qué es tarea propia:** `T-2.78` tiene que cronometrar el instante en que **una persona
  acusa**, y hoy no hay dónde escribirlo. La cadena de operación (CloudWatch → SNS → correo)
  no deja rastro en ninguna tabla de TAKAB, y AWS tampoco lo da: el registro de estado de
  entrega de SNS soporta Firehose, SQS, Lambda, HTTPS y endpoints de aplicación — **email y
  email-json no están en la lista**
  (`https://docs.aws.amazon.com/sns/latest/dg/sns-topic-attributes.html`). Así que hoy
  "publicado" es todo lo que se puede afirmar, y "leído por una persona" no se puede afirmar
  jamás. `T-2.78` se puede acreditar una vez a mano; como régimen permanente, no.
- **Reproducción del hueco:** provocar una alarma con `aws cloudwatch set-alarm-state` y luego
  buscar en la DB, en los logs o en la consola de AWS **cuándo** la leyó alguien. No aparece en
  ningún sitio: `notification_jobs` es de la otra cadena y no tiene ninguna columna de acuse
  (`db/schema.sql:1002-1030`: `created_at`, `due_at`, `deadline_at`, `sent_at`, `attempts`,
  `error` — y nada más).
- **Criterios de aceptación:**
  - [x] **Evidencia de máquina de que el aviso salió del topic.** Suscribir al mismo topic un
        endpoint que SÍ admita registro de entrega (HTTPS o Lambda, por la lista de arriba), de
        modo que quede un rastro con hora sin depender del buzón de nadie.
  - [x] **Un acuse con hora.** Un humano confirma "lo tengo" y queda registrado. Reutilizar el
        camino de `incidents_ack` sería mezclar dos cadenas distintas (ver T-2.78): decidir
        explícitamente si es una tabla propia o un objeto de operación aparte, y escribir por
        qué.
  - [x] **El tiempo hasta el acuse es consultable**, no reconstruible a mano desde cabeceras de
        correo.
  - [x] **Si nadie acusa, eso también se registra.** Un salto sin acuse que no deja fila es una
        anécdota, no una métrica: a la tercera vez nadie recuerda las dos primeras.
  - [x] Test: un aviso sin acuse **jamás** aparece como atendido (mismo principio que T-2.75 —
        el canal que no entrega no finge).

> **Cerrada (2026-08-14).** Suscriptor **HTTPS** —no Lambda— porque lo que hace útil la ficha no
> es «que quede un log», es que **el tiempo hasta el acuse sea consultable y el silencio deje
> fila**: eso es una escritura en la base de TAKAB, y una Lambda tendría que llegar a ella o
> reenviar a la API, con lo que **el endpoint público existe igual y hay un sitio más donde perder
> el aviso**.
>
> **La SSRF se cerró mejor que validando la URL: `SubscribeURL` NO SE VISITA JAMÁS.** La llamada
> de confirmación se **reconstruye** con la región de *nuestro* ARN, el `TopicArn` de *nuestra*
> configuración, y del cuerpo solo el `Token` opaco. Ventaja lateral: `ConfirmSubscription` es
> llamable sin firmar ⇒ **cero IAM nuevo**. Sigue entrando en el texto canónico —AWS lo firma—
> pero **como dato, no como destino**.
> `SigningCertURL` sí se valida antes de abrir socket: `https`, host **exactamente**
> `sns.<región>.amazonaws.com` (por `hostname`, **no `netloc`**), sin userinfo, sin puerto, ruta
> con patrón estricto, sin query. El test hostil tiene **10 casos** —incluidos `169.254.169.254`
> (metadatos de instancia), `…amazonaws.com.evil.mx` y `…amazonaws.com@evil.mx`— sobre un arnés
> que **es la única salida a la red y revienta ante cualquier host ajeno**, y su no-vacuidad la da
> el caso legítimo.
>
> **⚠️ Y el hallazgo que decide el diseño del acuse: los escáneres de los buzones PULSAN los
> enlaces de los correos.** Un acuse por `GET` lo fabricaría **una máquina antes de que nadie
> leyera nada**, y el criterio 5 quedaría violado **desde el primer correo**. Por eso `GET` solo
> pinta el formulario y **el acuse es `POST`**, con una credencial personal de guardia (256 bits,
> la base guarda **solo el hash**, con caducidad y revocación por fila) que **nunca viaja en el
> correo**. No es consola+MFA porque un acuse que exija abrir el SOC a las 3 a.m. no se da, y
> entonces la métrica mediría **fricción, no atención**. Lo que acredita, sin adornos: **lo mismo
> que poder leer el buzón de guardia** — pero a nombre de una persona, revocable sin tocar el
> buzón, y caduca sola.
>
> **Tabla propia**, no `incidents_ack`, y la segunda razón es la que pesa: una alarma de
> plataforma **no tiene tenant**, y colgarla de `incidents` haría que **un cliente pudiera ver que
> el on-call de TAKAB no contestó**.
>
> **La fila del silencio la escribe la máquina que recibió el aviso, en el instante del aviso** —
> nace **sin acuse**, con su plazo puesto; el acuse solo puede *modificar* una fila que ya existe,
> y el barrido únicamente le **pone hora**. Así **un cambio de configuración no puede mover un
> silencio ya ocurrido**. Y el criterio 5 queda **estructural en la base**:
> `CHECK ((acked_at IS NULL) = (acked_by IS NULL))` — «acusado» es **imposible** sin hora.
>
> **Hallazgo grave, de los que solo se ven en base nueva:** la `0001` termina con
> `GRANT … ON ALL TABLES … TO takab_app`, así que **en la nube** (base nueva) `takab_app` salía
> con SELECT sobre la tabla de **hashes de credencial** y con escritura sobre los avisos; **en
> base existente, no**. **Verde local, otra cosa en producción.** Cerrado con dos `REVOKE` en la
> 0041 y anclado con test.
>
> **Deja abierta** `T-2.142`.

### [x] T-2.78.b · Identidad de DOMINIO de SES en Terraform — `SOFTWARE`
- **Componente:** infra · **Depende de:** —
- **Por qué es tarea propia:** el único recurso SES de toda la infra es
  `aws_sesv2_email_identity` **por dirección** (`modules/identity/main.tf:139-144`); grep de
  `dkim|configuration_set|mail_from` sobre `infra/terraform/` devuelve **cero**. O sea que el
  primer criterio de `T-2.78` —DKIM/SPF de dominio real— hoy solo se puede cumplir a base de
  clics en la consola, y lo que se hace a clics no se vuelve a hacer igual ni se revisa en un
  diff. El código puede escribirse YA, con el dominio como variable vacía por defecto (patrón
  del módulo `push/`: sin credenciales, el apply no crea nada).
- **Reproducción:** `grep -rn "aws_ses" infra/terraform/` → una sola línea, de dirección.
- **Criterios de aceptación:**
  - [x] Identidad de **dominio** con Easy DKIM, MAIL FROM propio y su registro DMARC,
        condicionados a una variable de dominio: vacía ⇒ no se crea nada y el `apply` de hoy no
        cambia.
  - [x] **El ARN de la identidad de dominio entra en `notify_ses_identity_arns`.** Hoy esa
        lista se construye iterando `ses_verified_emails` (`envs/dev/main.tf:79-82`): cambiar
        el remitente al dominio sin tocar esto deja al worker con `AccessDenied` mientras los
        correos de CloudWatch siguen llegando — el fallo del 2026-07-14, calcado.
  - [x] **Bounces y quejas con destino.** La solicitud de producción exige declarar que existe
        un proceso para tratarlos
        (`https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html`); hoy no hay
        ni topic de feedback. Declararlo sin tenerlo es firmar algo falso.
  - [x] Los valores literales de los registros DNS **no se hornean en el repo**: varían por
        región y celda, y la fuente es la respuesta de la API.

## Fase 2.8 · Compliance como producto

El motor es `SOFTWARE`; **el texto legal es `LEGAL`**. No se bloquean entre sí: se construye
el motor con un texto provisional versionado y se sustituye el texto cuando llegue.

> ### CERRADA EN SU ALCANCE (2026-08-08) — y con 12 deudas declaradas, no escondidas
>
> **Las cinco tareas de la fase están `[x]`:** T-2.79 (aviso versionado + consentimiento),
> T-2.80 (ARCO por anonimización), T-2.81 (retención con la excepción codificada), T-2.82
> (`compliance_labels` por tenant) y T-2.83 (residencia de datos). Cada una pasó por **auditoría
> independiente**, y dos de ellas por **dos**.
>
> **Lo que la fase demostró, en una frase:** el motor de datos aguantó todas las auditorías a la
> primera —append-only en tres capas, digest copiado y no derivado, borrado imposible por
> privilegio y no por convención—, y **lo que estaba roto era siempre lo que la persona ve**. El
> peor defecto de toda la fase no fue de compliance: fue que la pantalla de consentimiento
> **encerraba al ocupante** sin check-in de vida ni botón de pánico cuando la nube fallaba a
> medias.
>
> **Las 12 fichas abiertas de esta fase son deuda declarada durante el trabajo, no alcance sin
> hacer.** Ninguna se cierra escribiendo código a ciegas:
>
> - **Necesitan decisión humana (2):** `T-2.80.a` — `LEGAL`: si anonimizar el teléfono del
>   consentimiento destruye la prueba de la base legal del envío que autoriza. `T-2.79.d` —
>   `DECISIÓN`: qué gana entre `empty` y `stale` en el contrato de `StateFrame`, que gobierna
>   **toda** la consola y no solo un banner.
> - **Riesgo operativo real (1):** `T-2.79.a` — el opt-in de WhatsApp sale de un `rule_set`
>   editable en vez del registro que sabe decir que el consentimiento se **retiró**. Es la única
>   que puede **tumbar un canal de notificación para todos los tenants a la vez**.
> - **Deuda declarada por el propio trabajo (9):** `T-2.79.e/f`, `T-2.80.b/c`, `T-2.81.a/b/c`,
>   `T-2.82.a/b`.
>
> **Dos de ellas conviene mirarlas juntas:** `T-2.79.d` y `T-2.82.a` nacen de lo mismo —el
> contrato de `StateFrame` no dice quién gana ni de dónde sale `staleSince`—, y la segunda revela
> que **ningún panel de la pantalla donde se FIRMA un dictamen** puede declarar su dato viejo.

### [x] T-2.79 · Aviso de privacidad versionado + consentimiento — `SOFTWARE` · COMPLETA (2026-08-08)
- **Componente:** api + web + mobile · **Depende de:** —
- **Criterios de aceptación:**
  - [x] El aviso es un **objeto versionado**; el consentimiento guarda **qué versión** aceptó
        cada usuario y cuándo.
  - [x] Cambiar el aviso **no reescribe** consentimientos anteriores.
  - [x] Registro append-only del consentimiento.

> **El motor aguantó dos auditorías independientes; las superficies no, y esa es la historia
> de esta ficha.** El DDL, la RLS y el sellado se dictaminaron bien hechos a la primera:
> el digest se **copia**, no se deriva por JOIN, así que editar el aviso por detrás sigue siendo
> **detectable**; y el append-only son **tres capas** —trigger `BEFORE UPDATE OR DELETE`,
> `REVOKE UPDATE, DELETE` y RLS `ENABLE`+`FORCE`—, con los tests parametrizados sobre las dos
> tablas e incluyendo el `UPDATE` que no cambia nada.
>
> Lo que estaba roto era lo que la persona ve, y era grave: el móvil **encerraba al ocupante**
> sin check-in de vida ni botón de pánico (T-2.79.b/c), y la consola **acusaba de no haber
> consentido a quien sí consintió**. Cerrado el 2026-08-08.
>
> **Queda exactamente un hueco, y está fichado:** con `notice === null` **y** dato viejo se
> pinta una franja muda. Se recorrió el espacio de estados **completo** contra la precedencia de
> `StateFrame` para confirmar que es el único, y que en móvil **no existe** la combinación
> equivalente. Es `T-2.79.d`, y no bloquea porque no miente: no dice nada.

### [x] T-2.79.a · El opt-in de WhatsApp sigue saliendo del `rule_set`, no del consentimiento — `SOFTWARE`
- **Componente:** api · **Depende de:** T-2.79 · **Detectada por:** auditoría de la Fase 2.8
  (2026-08-08)
- **Existe porque una referencia era falsa.** Tres sitios del código
  —`notify/config.py:63`, `notify/whatsapp.py:151` y `privacy/store.py:392`— declaraban que
  este trabajo «queda fichado en `T-2.77.b`». **No lo estaba:** `T-2.77.b` son los webhooks de
  estado de entrega de Meta y Twilio, y ninguno de sus seis criterios cubre mover el opt-in al
  motor de consentimiento. La deuda estaba razonada, argumentada y **apuntando a una ficha que
  no la contenía** — que en la práctica es igual a no ficharla. Esta es la ficha real.
- **El estado, medido.** `privacy.store.whatsapp_opt_in_at()` está **implementado y probado**, y
  **solo lo llaman los tests**. El destino real lo sigue armando
  `notify/config.resolve_destinations`, una función **pura** sobre el `rule_set` sin conexión a
  la base — por eso no se enchufó de refilón, y esa decisión fue correcta: hacerlo desde ahí
  habría roto los tests de T-2.77 sin que aquella tarea lo cubriera.
- **La forma exacta del cambio ya está escrita** en el comentario `[COSTURA T-2.79]` de
  `notify/config.py`: pasar `tenant_id` y una conexión hasta ahí (o resolver el destino en el
  orquestador), sustituir la lectura de `opt_in` del `rule_set` por la llamada a
  `whatsapp_opt_in_at`, y dejar de leerlo del `rule_set`. **El provider no cambia**: sigue
  exigiendo `opt_in.at` en el destino y sigue negándose a enviar sin él.
- **Por qué importa y no es burocracia:** enviar sin opt-in no rebota un mensaje — degrada la
  calificación de calidad del número y puede **tumbar el canal para todos los tenants a la vez**.
  Hoy la constancia que autoriza ese envío vive en un `rule_set` editable, no en el registro
  append-only que sabe además decir que el consentimiento se **retiró**.
- **Criterios de aceptación:**
  - [x] El destino de WhatsApp toma `opt_in.at` del motor de consentimiento, no del `rule_set`.
  - [x] Un consentimiento **retirado** deja de autorizar el envío, sin tocar el provider.
  - [x] Test: retirar el consentimiento ⇒ el envío se niega, y lo deja **escrito**.
  - [x] Ninguna referencia del código apunta ya a una ficha que no contiene el trabajo.

### [x] T-2.79.b · El stack de onboarding no tiene guarda de sesión — `SOFTWARE`
- **Componente:** mobile · **Depende de:** — · **Detectada al arreglar el cerrojo de privacidad**
  (2026-08-08)
- **La causa raíz que el arreglo de hoy NO cerró.** `mobile/src/app/index.tsx:34` es el **único**
  punto de la app que reacciona a quedarse anónimo, y `mobile/src/app/onboarding/_layout.tsx` es
  un `Stack` pelado, **sin guarda**. Cualquier `signOut()` disparado durante el onboarding —hoy
  el 401 exento, mañana otro— deja a la persona **en la pantalla, sin token y en silencio**:
  nadie la lleva al login.
- **Lo que se hizo hoy fue tapar el disparador conocido**, no la causa: se eximió a
  `/privacy/consent` y `/privacy/notice` de cerrar sesión (`mobile/src/services/sdk.ts`). Esa
  exención es correcta —una vía de cumplimiento no debe poder expulsar a la flota— pero solo
  cubre las dos rutas que hoy sabemos que se llaman desde ahí.
- **Criterios de aceptación:**
  - [x] Quedarse anónimo dentro del onboarding **lleva al login**, desde cualquier pantalla del
        stack.
  - [x] Test que dispare `signOut()` en cada pantalla del onboarding y exija la redirección.
        Enumerar las pantallas de hoy no vale: **derívalo del stack**.
  - [x] La exención de `sdk.ts` sigue en pie y **con su test**: quitar la causa raíz no es
        excusa para devolverle a una ruta de cumplimiento el poder de expulsar.

### [x] T-2.79.c · La salida del enrolamiento se llama «Ya estoy vinculado», y para quien falla es mentira — `SOFTWARE`
- **Componente:** mobile · **Depende de:** — · **Detectada al arreglar el cerrojo de privacidad**
  (2026-08-08)
- **Medido, y menos grave de lo que parecía.** El occupant **no** marca el onboarding como hecho
  en la pantalla de privacidad: `privacidad.tsx:68` lo empuja a `/onboarding/enrolamiento` y solo
  la rama táctica llama a `markOnboardingDone()`. Para el occupant esa llamada vive en
  `enrolamiento.tsx:43`. Y como `app/index.tsx:53-55` redirige mientras `!onboarded`, la sospecha
  era un cerrojo idéntico al de privacidad, un paso más adelante.
- **No lo es: hay salida.** `enrolamiento.tsx:79` ofrece un botón que llama a `finish()` sin
  necesidad de canjear el código. **Pero se rotula «Ya estoy vinculado · continuar»**, es
  secundario (`ghostBtn`), y aparece junto al mensaje «Sin conexión con el servidor. Intente de
  nuevo.» — o sea: a la persona que la nube dejó tirada se le ofrece una salida cuyo texto
  **afirma algo falso sobre ella**, con estilo de opción descartable. Quien lee que no está
  vinculado no la pulsa. La puerta existe y está mal señalizada, que en una app de vida cuenta.
- **Criterios de aceptación:**
  - [x] Cuando el enrolamiento falla por causa de red o servidor, la salida se rotula por lo que
        hace —seguir sin vincular, y vincular después desde Cuenta—, no por una condición del
        usuario que el sistema no puede afirmar.
  - [x] Test: con el servidor caído, existe un camino visible al final del onboarding, y el texto
        del control **no afirma** que el usuario ya esté vinculado.
  - [x] Queda escrito qué pierde quien continúa sin vincular (sin sitio vigilado no hay
        check-in de zona), porque continuar a ciegas también es una forma de mentir.

> **Cerradas (2026-08-08).** La cobertura de pantallas es **derivada del directorio de rutas**,
> no una lista: expo-router enruta por ficheros, así que el directorio **es** el stack.
> Verificado creando una pantalla que nadie añadió a ninguna parte — la corrida pasó de 11 a 13
> tests, con los dos casos nombrados por el fichero nuevo. Dos tests más impiden que la
> derivación salga vacía y pase en falso.
>
> **`booting` NO expulsa**, y hay test que lo fija: sesión desconocida no es sesión muerta, o
> cada arranque en frío echaría a gente con sesión válida.
>
> **Las dos defensas se quedan:** la guarda del stack y la exención de `sdk.ts` para las rutas de
> cumplimiento. Retirar la guarda pone 4 tests en rojo.
>
> **Bug extra cerrado de paso, de la misma familia que la ficha:** un **503 se rotulaba «Código
> inválido, vencido o agotado»**, mandando a la persona a pedir un código nuevo que no arreglaba
> nada. Ahora se distingue quién falló — el código o la nube — y la salida solo se destaca cuando
> falló la nube: con un 404 lo correcto sigue siendo pedir otro código.

### [x] T-2.79.d · `StateFrame` no dice quién gana entre `empty` y `stale` — `SOFTWARE` + `DECISIÓN`
- **Componente:** web (contrato de estados) · **Depende de:** — · **Detectada al arreglar el
  banner de privacidad** (2026-08-08)
- **El síntoma concreto.** En `PrivacyConsentBanner`, con `notice === null` **y** el dato viejo,
  el `empty` exige `sereno` (que exige dato fresco), así que se pinta la franja
  `DATOS RETENIDOS · hh:mm UTC` **sin nada debajo**. No miente —y por eso no se arregló de
  refilón—, pero **no dice nada**: una banda muda en la consola de un SOC.
- **Por qué esto no es un arreglo local.** La regla de oro 7 obliga a manejar `loading`, `error`,
  `empty` y `stale`, pero **no declara la precedencia** cuando dos son ciertos a la vez. Cada
  componente la está resolviendo por su cuenta, y esa deriva es la que produce franjas mudas.
  Elegir aquí decide el comportamiento de **toda** la consola, no de un banner.
- **La pregunta a decidir, en una línea:** cuando no hay dato **y** lo poco que hay está viejo,
  ¿se dice «no hay» (arriesgando afirmar una ausencia que quizá solo es desconexión) o se dice
  «no lo sé desde las hh:mm» (que es más honesto y menos accionable)?
- **Criterios de aceptación:**
  - [x] La precedencia queda **decidida y escrita** en el contrato de `StateFrame`, con su razón.
  - [x] Ningún componente puede quedar en una combinación sin texto: un test que recorra las
        combinaciones de estados y exija contenido en todas. **Derivado del contrato**, no una
        lista de componentes.
  - [x] `PrivacyConsentBanner` deja de pintar la franja muda.

> **Cerrada (2026-08-12).** `STATE_PRECEDENCE = ["loading", "error", "stale", "empty"]` — **gana
> `stale`**, por delegación explícita de Mauricio (`PENDIENTES §1.2`, con la razón allí y en
> `StateFrame.tsx`).
>
> **La pregunta estaba mal planteada, y la solución lo demuestra.** Se formuló como binaria —o
> dices «no hay» o dices «no lo sé»— y no lo era: **el «no hay» no se pierde, se FECHA**.
> `staleEmptyText(...)` imprime la ausencia en pasado —*«SIN AVISO… — así estaba a las 10:41:30
> UTC; desde entonces no se ha podido confirmar»*—, que es exactamente lo que era verdad. Vive en
> el contrato para que ningún panel escriba su propia versión del deslinde.
>
> **Lo que impide sortear la tabla** son dos piezas mecánicas, no una convención:
> 1. **Tipo:** la tabla de activación es un `Record<(typeof STATE_PRECEDENCE)[number], …>` **sin
>    `Partial` ni `??`**. Un quinto estado **no compila** hasta que alguien diga cómo se enciende.
> 2. **Barrido:** el test enumera las **2^n** combinaciones derivadas de la tabla (16 hoy, 32 con
>    un quinto) y renderiza **con hijos nulos** —porque en `stale`+`empty` los hijos son justo lo
>    que no hay—, exigiendo texto en todas **descontada la franja de edad**: esa segunda parte es
>    la franja muda literal.
>
> Más un censo que denuncia el patrón local: un marco cuyo `empty` dependa del valor que él mismo
> pasa como `staleSince`. Medido, no teórico: al revertir la línea del banner, el censo lo nombró.
> **Componentes que sorteaban la precedencia: 1**, el banner. Pagado.
>
> **Nota de método que conviene recordar:** el analizador nació con **la dirección del tinte
> invertida** y producía **13 falsos positivos**, incluidos 7 paneles que solo comparten su
> consulta. Lo cazaron **sus propios tests sintéticos** antes de que acusara a nadie. Un censo sin
> pruebas contra fuentes fabricadas es un censo en el que no se puede confiar.

### [x] T-2.79.e · `NOTICE_ROLES` sigue a mano en el router, y su razón ya caducó — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** api (auth) · **Desbloquea:** el primer criterio de `T-2.80.b` ·
  **Detectada por:** reauditoría de la Fase 2.8 (2026-08-08)
- **La deuda estaba justificada y su justificación ya no es cierta.**
  `api/src/takab_api/routers/privacy.py:73-88` declara los roles a mano, contra la convención de
  `auth/matrix.py`, y el comentario dice que es porque «`auth/matrix.py` lo está tocando otra
  tarea en paralelo (T-2.82)». **Medido:** T-2.82 aterrizó **sin tocar** `matrix.py` —reutiliza
  `roles_with_action("manage_tenants")`— y el último commit de ese fichero es de T-2.61…T-2.71.
  La condición «mover al integrar» **ya se cumplió y nadie movió nada**.
- **Por qué esto merece ficha propia:** hasta hoy solo estaba referenciada de refilón, como línea
  de dependencia dentro de `T-2.80.b`. Es la misma lección de `T-2.79.a`: **una deuda sin ficha
  es una deuda no fichada**, por bien razonada que esté el comentario.
- **No es un agujero de seguridad hoy:** la frontera real la impone la política RLS `pn_publish`,
  no la lista del router. Es coherencia y mantenibilidad — y el bloqueo de `T-2.80.b`.
- **Criterios de aceptación:**
  - [x] La acción `manage_privacy_notice` existe en `auth/matrix.py`, con su línea en
        `RBAC-TAKAB.md`, y el router la consulta en vez de enumerar roles.
  - [x] El test de matriz (`api/tests/auth/test_matrix.py`) la cubre como a las demás.
  - [x] Ninguna superficie de privacidad enumera roles a mano.

> **Cerrada (2026-08-10).** El conjunto de roles **NO se movió** —`takab_superadmin` y
> `tenant_admin` antes y después—, y está demostrado por un **test caracterizador escrito ANTES**
> del refactor, en verde contra el código viejo. Si al derivarlo de la matriz hubiera cambiado,
> eso era decisión de RBAC y había que parar; no hizo falta.
>
> El razonamiento se **mudó del router a la matriz** (LFPDPPP: el *responsable* es la
> organización dueña del inmueble, así que publicar su aviso es acto SUYO; `takab_support` queda
> fuera a propósito, que lee la plataforma pero no firma el aviso de un cliente en su nombre). Y
> el docstring de `matrix.py` dejó de mentir: afirmaba que «ningún router vuelve a listar roles a
> mano» mientras uno lo hacía.
>
> **El barrido del criterio 3 quedó como TEST**, con la lista de ficheros **calculada** por glob
> sobre `privacy/`: un fichero nuevo de privacidad entra solo. Excepción nombrada:
> `privacy/retention.py:122` (`JOB_APP_ROLE`) es el `app.role` de una **identidad máquina**, que
> `CLAUDE.md §5` excluye de RBAC — no hay portador de token ni acción que derivar.
>
> Confirmó de paso que la excusa había caducado: `routers/compliance.py` ya estaba limpio desde
> T-2.82.

### [x] T-2.79.f · La parte de la pantalla móvil que le habla a la persona no la asserta nadie — `SOFTWARE`
- **Componente:** mobile · **Depende de:** — · **Detectada por:** reauditoría de la Fase 2.8
  (2026-08-08)
- La suite de `privacidad.tsx` cubre a fondo **los dos bloqueantes** que se cerraron el
  2026-08-08 —el cerrojo del onboarding y el falso vacío— usando el `testID` `privacy-accept`.
  Pero **nadie comprueba que se pinte el aviso servido ni su sello** (`privacy-notice`), ni el
  texto del estado en que **el aviso cambió** (`privacy-changed`).
- **Lo que queda sin cubrir es justo lo que la persona lee** antes de decidir. El criterio 2 de
  T-2.79 («cambiar el aviso no reescribe consentimientos») está probado **en el motor**, que es
  donde importa para la integridad del registro; lo que no está probado es que la pantalla se lo
  **cuente** a quien tiene que decidir.
- **Criterios de aceptación:**
  - [x] Un test asserta que el cuerpo del aviso servido y su versión/sello se pintan.
  - [x] Un test asserta el texto del estado «este aviso cambió», que es el que pide una decisión
        nueva a alguien que ya había consentido.

### [x] T-2.80 · ARCO por anonimización con tombstone — `SOFTWARE` · COMPLETA (2026-08-08)
- **Componente:** api + db · **Depende de:** T-2.79
- **Criterios de aceptación:**
  - [x] **Jamás `DELETE`.** Anonimización + `tombstone`: el derecho ARCO se ejerce sin borrar
        una fila de auditoría, evidencia ni dictamen — **regla de oro 11**, que es restricción
        dura, no preferencia.
  - [x] Un check-in de vida anonimizado sigue contando para el histórico del incidente.
  - [x] Test: tras ejercer ARCO, el `audit_log` del incidente sigue íntegro y verificable.

> **El conflicto era aparente, y ahí está toda la tarea.** El derecho es sobre la **persona**; la
> obligación de la regla de oro 11 es sobre el **hecho**. La bisagra: `life_checkins.user_id` es
> un `sub` de Cognito — un UUID **opaco**, que solo es dato personal mientras exista el mapeo
> `sub → nombre` en `user_profiles`. **ARCO destruye el mapeo y deja el UUID en pie.**
>
> Por eso **no** se sustituye el `sub` por un seudónimo: `COUNT(DISTINCT user_id)` es «cuántas
> personas confirmaron estar bien en el piso 8», y colapsarlas a un valor común **hundiría un
> número que se usa para decidir dónde buscar**. Lo que sí muere del check-in es `geom`, el GPS
> exacto de una persona, que el conteo no necesita.
>
> **Qué impide FÍSICAMENTE borrar — tres capas, ninguna es un comentario:**
> 1. **Privilegio ausente.** `REVOKE DELETE` sobre 12 tablas + `REVOKE UPDATE` en `life_checkins`
>    seguido de `GRANT UPDATE (geom)`: privilegio **por columna**. Reescribir `status` o
>    `user_id` es un error de permisos de PostgreSQL, no una convención.
> 2. **Triggers con eventos SEPARADOS.** El `DELETE` conserva el guard canónico; el `UPDATE`
>    compara la fila entera vía `to_jsonb(NEW) - 'geom'`, así que cubre las columnas de hoy **y
>    las que se añadan mañana**.
> 3. **La firma.** `privacy_erase_subject(p_right, p_via)` **no recibe sujeto**: opera sobre
>    `app_user_id()`. Ejercer ARCO sobre un tercero o cruzar tenants no está *prohibido* — es
>    **inexpresable**.
>
> **El inventario de PII es DERIVADO**, con test recíproco: un detector recorre el esquema
> **vivo** y toda columna que huela a persona debe estar clasificada; el reverso caza entradas
> muertas, porque un inventario con fantasmas miente igual que uno corto. Verificado quitando
> `user_profiles.display_name`: el detector la encuentra y **la nombra**.
>
> **Distinción que evita un desastre:** `device_keys` se **REVOCA**, no se borra. Confundirlas
> llevaría a alguien a «completar» la anonimización destruyendo la llave pública que **verifica
> la evidencia firmada**.
>
> **Decisiones fijadas por test:** ARCO durante incidente **abierto** se difiere con 409 —la
> ubicación es dato de rescate en vivo— y la petición se audita **fuera de banda** para que el
> plazo legal corra igual. Ejercerlo dos veces es idempotente, con la misma lápida.
>
> **La verificación sobre base NUEVA (cadena 0001→0034) cazó dos bugs invisibles en local:** una
> función usada 300 líneas antes de definirse, y el `GRANT ... ON ALL TABLES` de la 0001
> **re-concediendo `DELETE`** después de `schema.sql`. Por eso los `REVOKE` viven en la migración.

### [x] T-2.80.a · El teléfono en claro del consentimiento no lo alcanza ARCO — `SOFTWARE` + `LEGAL` · COMPLETA (2026-08-22)
- **Componente:** api + db · **Depende de:** T-2.80 · **Declarada por el propio T-2.80 como hueco**
- **El hueco, medido.** ARCO alcanza al titular identificado por `sub` de Cognito. Un sujeto
  identificado por **teléfono** (`msisdn`) tiene su número **en claro** en
  `privacy_consents.subject_ref` — y esa tabla es **append-only** por el motor de T-2.79.
- **Por qué no se cerró de refilón, que es lo correcto:** anonimizarlo exige **abrir un hueco en
  el guard de la tabla hermana** y decidir algo que no es técnico: si destruir el número destruye
  también **la prueba de la base legal** del envío que ese consentimiento autoriza. Hacerlo sin
  decidirlo habría cambiado el significado del registro de consentimientos por un efecto
  colateral.
- **Criterios de aceptación:**
  - [x] Queda **decidido y escrito** qué prevalece — [`D-23`](DECISIONES-MAURICIO.md#d-23): la
        titularidad del número **la acredita el cliente institucional** que recogió el
        consentimiento. TAKAB ejecuta y audita, no verifica identidades por su cuenta.
  - [x] **Resuelto por diseño, no por excepción** (migración `0046`): en vez de abrir un hueco en
        el guard append-only para poder anonimizar, las filas nuevas guardan un **índice sellado**
        (64 hex) y no el número. *«Sin UPDATE: un sello no se edita, se crea o se destruye.»* El
        `CHECK` se ensanchó para aceptar la forma sellada, no para permitir reescrituras.
  - [x] La lápida cubre al sujeto `msisdn` igual que al `sub` (`T-2.151`, criterio 4).

> ### ✅ Cerrada por `T-2.150` + `T-2.151` + [`D-23`](DECISIONES-MAURICIO.md#d-23) — y con una deuda que se lleva ficha propia
>
> Esta ficha se quedó abierta mientras otras tres la cerraban por partes, que es exactamente el
> desfase que la auditoría de decisiones existe para cazar. El criterio 2 no se cumplió como estaba
> escrito: se volvió **innecesario**, porque sellar el sujeto quita la necesidad de anonimizarlo.
>
> **Lo que NO cerró, y ahora tiene ficha: `T-2.164`.** El sellado vale para las filas NUEVAS. Los
> teléfonos ya escritos en claro **siguen en claro para siempre** — la propia migración `0046` lo
> declara: *«Forma VIEJA: el número en claro. Permanente, no transitoria: la tabla es append-only y
> estas filas NO SE PUEDEN reescribir.»*

### [x] T-2.80.b · El responsable no puede ejercer un ARCO recibido por escrito — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** api + auth · **Depende de:** T-2.80 · **Bloqueada de hecho por la deuda de
  `auth/matrix.py`** que T-2.79 dejó abierta
- **Hoy solo el titular puede ejercerlo**, y eso no cubre el caso real: una persona manda su
  solicitud ARCO **por escrito** al responsable del tratamiento, que es quien tiene que
  ejecutarla. La firma `privacy_erase_subject(p_right, p_via)` sin sujeto —que es una **virtud**
  de T-2.80, porque hace inexpresable el ARCO cruzado— es justo lo que hay que ensanchar **sin
  perder** esa garantía.
- **Criterios de aceptación:**
  - [x] Existe una acción `manage_privacy_erasure` en `auth/matrix.py` (no una lista de roles
        escrita a mano en el router — ver la deuda de `routers/privacy.py`), y su línea en
        `RBAC-TAKAB.md`.
  - [x] Ejercerlo por cuenta de otro **exige constancia** de la solicitud y queda en el
        `audit_log` con quién lo pidió, quién lo ejecutó y con qué prueba.
  - [x] **La garantía de T-2.80 no se debilita:** sigue siendo imposible alcanzar a un titular de
        otro tenant. Test cross-tenant que debe fallar.
  - [x] Queda escrito qué NO hace esta tarea: **borrar la cuenta en Cognito** no es parte del
        acto de anonimización y necesita su propio camino.

> **Cerrada (2026-08-10). La clave: el tercer parámetro NO es un sujeto, es una constancia.**
> `privacy_erase_subject(p_right, p_via)` pasa a llevar `p_request uuid` — el `request_id` de una
> solicitud registrada. **El titular no se acepta: se PRODUCE** dentro de la función, con un JOIN
> contra `user_profiles` del tenant de la sesión. Por eso el ARCO cruzado sigue siendo
> **inexpresable, no prohibido**, y ninguna de las tres piezas es un `IF`:
>
> 1. **No hay parámetro de tenant.** La tabla lo pone por `DEFAULT app_tenant_id()` y la RLS lo
>    vuelve a exigir en el `WITH CHECK`. El cliente no lo manda ni podría.
> 2. **FK COMPUESTO** `(tenant_id, user_sub) → user_profiles`: nombrar a un titular ajeno
>    **viola integridad referencial**, no una comprobación.
> 3. **La constancia se busca SIN filtro de tenant, a propósito.** La RLS ya hace que la de otro
>    cliente **no exista** para esa sesión; añadir el filtro habría sugerido que el confinamiento
>    es un chequeo. Un `request_id` ajeno da 404, indistinguible de «no existe» (regla de oro 5).
>
> **«Exige constancia» tampoco es un `if` del router: es un PRIVILEGIO.**
> `app_can_erase_subject()` gatea cinco políticas RLS, así que sin fila de solicitud el
> responsable no puede tocar **un solo dato** de esa persona — y con constancia en mano, cada
> `WITH CHECK` admite exactamente la fila anonimizada y nada más. Un CHECK impide que el
> responsable **se fabrique su propia constancia** (`created_by <> user_sub`).
>
> La constancia registra `channel` (`written|email|in_person|legal_representative`),
> `received_at` (de ahí corre el plazo legal), `proof_ref` (**dónde** está el escrito) y
> `proof_digest` (**cuál** es). `proof_ref` **no** va al `audit_log`: es texto libre y esa
> bitácora es eterna.
>
> El camino del titular queda **byte a byte** como lo dejó T-2.80, anclado por su propio test.
> Las tres capas de T-2.80 siguen intactas: no se derogó ninguna.

### [x] T-2.80.c · El verificador de restore ya no comprueba la rendija de ARCO — `SOFTWARE`
- **Componente:** api (`ops/restore_check.py`) · **Depende de:** T-2.80 · **Regresión declarada
  por el propio T-2.80**
- **Qué se perdió y por qué es correcto que se perdiera.** El verificador de DR reconocía
  «append-only» ejerciendo un `UPDATE` sobre `life_checkins` y exigiendo que fuera rechazado.
  T-2.80 abrió ahí una **rendija de una sola columna** (`geom`), así que esa tabla ya no es
  append-only puro y el verificador tuvo que dejar de tratarla como tal.
- **El riesgo que queda:** tras un restore, **nadie comprueba que la rendija siga siendo del
  tamaño que era**. Una base restaurada con el `GRANT UPDATE` a nivel de tabla en vez de por
  columna pasaría el chequeo de DR y permitiría reescribir `status` o `user_id` de un check-in de
  vida — sin que ninguna alarma lo dijera.
- **Criterios de aceptación:**
  - [x] El verificador de restore comprueba que el privilegio de `life_checkins` es **por
        columna** y que la única columna concedida es `geom`.
  - [x] Comprueba que el guard de `UPDATE` sigue rechazando cualquier otro cambio, incluido el
        `UPDATE SET c = c` que no cambia nada.
  - [x] Un `SKIP` no cuenta como `PASS` (la lección de la Fase 2.6).

> **Cerrada (2026-08-14), y la causa raíz es una función de Postgres que engaña:**
> **`has_table_privilege` devuelve `false` con un grant de COLUMNA** (medido), y `_check_privileges`
> **solo mira en la dirección de lo que falta, nunca de lo que sobra**. Por eso el origen sano y
> la base restaurada mal **se veían iguales**.
>
> La comprobación nueva exige que el conjunto de columnas con UPDATE efectivo sea **exactamente**
> el declarado, y **falla en los dos sentidos**: si creció (la rendija se ensanchó) **y si se
> cerró** (entonces ARCO deja de poder anonimizar). La expectativa se **deriva del `GRANT` de
> `db/schema.sql`** y **viaja en la huella**, porque la imagen de la nube no lleva ese fichero
> dentro.
>
> **El test de la base restaurada mal es el que lo prueba:** ensancha la rendija a nivel de tabla,
> **confirma que se ensanchó**, y exige `column_grants == FAIL` **y `privileges == PASS`** — o sea,
> deja constancia de que **la comprobación vieja seguía diciendo que todo estaba bien**.
>
> Con el verificador de ayer sobre esa misma base rota: `PASS privileges · PASS
> append_only_triggers · PASS ownership · PASS rls_policies · PASS columns`. **Cinco verdes sobre
> una base donde se podía reescribir el `status` de un check-in de vida.**
>
> **Hallazgo de paso:** `life_checkins` **no tenía expectativa declarada** de append-only —entraba
> en la comprobación solo por el catálogo—, así que **si alguien tirase el trigger de DELETE salía
> de las dos comprobaciones a la vez**. La comprobación nueva la nombra desde el `GRANT`, y tapa
> también ese hueco.

### [x] T-2.81 · Retención de PII con la excepción de compliance en el job — `SOFTWARE` · COMPLETA (2026-08-08)
- **Componente:** api (job) + db · **Depende de:** T-2.80
- **Criterios de aceptación:**
  - [x] La excepción de compliance está **codificada en el job**, no escrita en un comentario.
        Un comentario no impide que un `DELETE` mal escrito pode evidencia.
  - [x] Test: el job intenta podar una tabla protegida ⇒ **falla ruidosamente**.
  - [x] Simulacro (`dry-run`) obligatorio con conteos antes de podar nada.

> **El hallazgo que gobernó el diseño: el job NO puede heredar el rol del DSN.** El de tests —y
> el de una consola SSM de emergencia— es `takab`, que es **SUPERUSER + BYPASSRLS**: se salta el
> `REVOKE DELETE` de T-2.80, se salta la RLS y, vía `session_replication_role`, podría saltarse
> los triggers. Heredarlo habría dejado la excepción de compliance apoyada en que **nadie invoque
> el job desde la consola equivocada**.
>
> Así que **el job se degrada a sí mismo**. Antes de leer un solo dato: `SET LOCAL ROLE
> takab_app`, aborta si el rol efectivo es superusuario o tiene BYPASSRLS, y **deriva del
> catálogo vivo** qué mecanismo le niega el `DELETE` a cada tabla protegida —privilegio ausente o
> trigger activo— negándose a arrancar si falta alguna. **Correr exige demostrarle a PostgreSQL
> que no se puede podar evidencia.** No es un `if` alrededor de un `DELETE`: es el permiso de
> arranque. Si alguien revierte el `REVOKE` de T-2.80, el job deja de funcionar y lo dice.
>
> **`COMPLIANCE_ANCHOR` es el suelo, y su razón es la parte fina:** una derivación sola **se
> aprueba a sí misma**. Conceder `DELETE` sobre `audit_log` y quitarle el trigger la sacaría del
> conjunto derivado **en silencio**, y lo que ya no se deriva ya no se revisa. Cinco tablas
> nombradas, un test por cada una.
>
> **Anonimiza, no borra:** el plan despachado tiene **cero** reglas que borren filas, y hay test
> que lo fija. El modo `DELETE_ROWS` existe igualmente, y **no por simetría**: sin él «el job
> intenta podar una tabla protegida» sería **inexpresable** y el criterio 2 no probaría nada — el
> mismo defecto de test vacío que esta fase lleva cazando. La regla asesina se construye en el
> test y el job rechaza **el plan entero** antes de contar nada.
>
> **El simulacro es el modo por defecto Y es la autorización:** cuenta, ejecuta con el mismo
> predicado, y si `ROW_COUNT` no cuadra **revierte la corrida entera**. No es decorativo —
> detectó un hueco de RLS real durante el desarrollo, y hay un test que reproduce ese fallo.
>
> Sin plazo configurado la regla queda **deshabilitada** y el informe lo grita; un valor inválido
> tampoco cae a un default. **Por defecto no se borra nada.** Mutar la degradación de rol pone 23
> tests en rojo con el mensaje correcto: «el rol efectivo `takab` es SUPERUSER».

### [x] T-2.81.a · El job de retención existe y nadie lo llama — `SOFTWARE` + infra
- **Componente:** api + infra · **Depende de:** T-2.81 · **Declarada por el propio T-2.81**
- **El job es invocable** (`python -m takab_api.ops.prune_pii`), igual que `ops.restore_drill`,
  **y no hay ningún scheduler**: no existe módulo de cron, Lambda ni EventBridge en
  `infra/terraform/modules/`. Una retención que nadie ejecuta es una política escrita, no una
  cumplida — y la diferencia importa el día que un cliente pregunte cuánto tiempo guardamos su
  teléfono.
- **Segundo asunto, del mismo fichero:** la corrida entera es **una sola transacción**. Es
  correcto y atómico, pero sobre millones de filas mantiene una transacción larga, y eso **no se
  ha medido con volumen real**.
- **Criterios de aceptación:**
  - [x] El job corre solo, con su cadencia declarada, y **deja constancia** de cada corrida
        (incluido el simulacro que no borró nada).
  - [x] Un fallo del job **se ve**: alarma o registro que alguien mire, no un exit code perdido.
  - [x] El comportamiento con volumen está medido, o el lote está acotado y **declarado**.

> **Cerrada (2026-08-14). MEDIDO con 1 000 000 de filas:** commit en **38.90 s** (re-medida
> 41.80 s), transacción abierta 38.64 s vista desde `pg_stat_activity`, **~39–42 µs/fila, lineal**,
> 57 locks pico.
>
> **Se CONSERVA la transacción única**, y la razón es de producto: el conteo previo **es la
> autorización de la poda**, y **media poda con informe en verde es peor que ninguna**.
>
> **Sobre los topes, el hallazgo importa: el job no conecta ni por `db/session.py` ni por
> `db/pool.py`** —abre su propio `psycopg.connect`—, así que **ninguno** de `T-2.130`/`T-2.131`/
> `T-2.132`/`T-2.136` le aplicaba. Comprobado, no supuesto. Y el veredicto **difiere por reloj**:
> - **`statement_timeout`: NO.** Los 20 s del request o los 15 s del worker **matarían esa corrida
>   legítima a mitad** — el fallo nuevo que la ficha advertía.
> - **`lock_timeout`: SÍ, 30 s.** No mide trabajo útil, **mide espera**: sin él una fila bloqueada
>   deja al job esperando para siempre **dentro** de una transacción que ya sostiene el horizonte
>   de `xmin` — el `idle in transaction` de `T-2.73.c`. Y **30 s < 38.9 s medidos**: esperar más de
>   lo que dura el trabajo sería estar abierto **por no trabajar**.
>
> El scheduler es **documento SSM + asociación `rate(1 day)`**, el **mismo vehículo que el PITR y
> el respaldo lógico** — no EventBridge/Lambda. Corre a las **06:00 UTC**, entre el scan del backup
> base y el dump, **para que el respaldo del día se lleve la PII ya podada**. Y con el DSN de
> `takab_app`, no del superusuario: **la autodegradación pasa a ser un no-op comprobable**.
>
> **La constancia se escribe FUERA de la transacción del job, y ése es el punto entero:** escrita
> dentro, **el rollback se llevaría justo el registro de la corrida que falló**. La métrica de la
> alarma sale de `max(finished_at) WHERE ok`, **no del exit code**: un job que falla a diario **no
> refresca la edad y la alarma sube sola**.

### [x] T-2.81.b · El nombre y el teléfono no tienen reloj honesto — `SOFTWARE`
- **Componente:** api + db · **Depende de:** T-2.81 · **Declarada por el propio T-2.81**
- **Por qué se dejaron fuera, que es la parte que hay que conservar.** `user_profiles.display_name`
  y `phone` son PII con caducidad, pero **no hay ninguna columna que diga cuándo dejó de ser
  necesaria**. `updated_at` describe a un empleado **estable**, no a uno que se fue: usarla como
  reloj **borraría antes los nombres de quien más tiempo lleva en el edificio** — exactamente al
  revés de lo que la retención pretende.
- Está declarado en `SIN_RELOJ` con su razón y con test recíproco, así que no es un olvido
  silencioso. **El reloj correcto es la baja de la cuenta, y hoy no se registra en ninguna parte.**
- **Criterios de aceptación:**
  - [x] Existe el hecho «esta persona ya no está» con su instante, y se registra cuando ocurre.
  - [x] La regla de retención de nombre y teléfono cuelga de **ese** reloj, no de `updated_at`.
  - [x] `SIN_RELOJ` queda vacío para estas dos columnas, y el test recíproco lo exige.

> **Cerrada (2026-08-14).** El reloj lo escribe **el administrador del cliente, en el instante de
> la baja**, desde los **dos actos que YA existían** —`PATCH {"enabled": false}` y `DELETE`—, así
> que **no se estrena ninguna ceremonia** que alguien tenga que acordarse de hacer. Y **`PATCH
> {"enabled": true}` PARA el reloj**: sin eso, una readmisión **seguiría contando plazo y perdería
> su nombre estando en el edificio**. Se escribe en la **misma transacción** que ya dejaba la fila
> de `audit_log`: «hay bitácora» y «hay reloj» **no pueden divergir**.
>
> **Tabla propia y no una columna, y la razón es de PRIVILEGIO — es lo mejor de la ficha.** El
> `tenant_admin` no es rol interno: sobre `user_profiles` solo tiene «mi propia fila». Poner el
> reloj como columna habría exigido darle UPDATE sobre las filas de otros y, como `WITH CHECK`
> **no puede comparar contra la fila vieja**, esa misma política **le habría dejado reescribir
> `display_name` y `phone` de cualquiera** — o sea, ensanchar la escritura sobre **las dos
> columnas exactas que esta ficha existe para proteger**. Escribe el HECHO, no el dato. Y **quién**
> lo hizo no se copia: ya está en `audit_log`, que no se poda.
>
> **Rojo medido:** con `updated_at` como reloj salen **5 rojos**, incluido
> `test_el_reloj_del_roster_no_toca_a_quien_sigue_dentro` («se podó el roster de alguien que sigue
> dentro») — que es literalmente el defecto que la ficha describía.
>
> La regla se **difiere con incidente abierto**, mismo criterio que la geometría: con un incidente
> abierto **el roster es la lista con la que una brigada pregunta «¿quién falta?»**.
>
> **Hueco declarado, y se conserva de MÁS, nunca de menos:** una cuenta retirada **directamente en
> el pool de Cognito** no pasa por la API y no deja reloj — esa persona conserva nombre y
> teléfono. Query de reconciliación en el runbook; la automática queda en `T-2.143`.

### [x] T-2.81.c · `rule_evaluations` conserva el `DELETE` que sus once hermanas no tienen — `SOFTWARE`
- **Componente:** db · **Depende de:** — · **Detectada por el guard de T-2.81**, que es justo
  para lo que se escribió
- **Medido:** de las doce tablas con trigger append-only, `takab_app` conserva el privilegio
  `DELETE` sobre `rule_evaluations`. **No es explotable hoy** —el trigger lo deniega con P0001—,
  pero es la única donde falta el `REVOKE`, o sea que la protección descansa en **una** capa
  donde las demás tienen dos.
- **Vale la pena registrar cómo apareció:** no lo encontró una revisión, lo encontró el
  precondición del job de retención al derivar del catálogo vivo qué mecanismo niega el `DELETE`
  en cada tabla. Una guarda derivada delata lo que una lista escrita a mano habría dado por bueno.
- **Criterios de aceptación:**
  - [x] `REVOKE DELETE ON rule_evaluations FROM takab_app`, en migración idempotente y con su
        espejo en `db/schema.sql`.
  - [x] Un test que exija **las dos** capas —privilegio ausente **y** trigger activo— en las doce
        tablas, derivado del catálogo y no de una lista.

### [x] T-2.82 · Carga de `compliance_labels` por tenant — `SOFTWARE` · COMPLETA (2026-08-08)
- **Componente:** api + web · **Depende de:** T-2.80 *(corregido: la ficha declaraba `T-2.81`, y
  es falso. La cadena 2.82→2.81→2.80 era **temática, no técnica**: T-2.81 es el job de retención
  de PII, `compliance_labels` **no es PII**, no está en la lista de tablas protegidas, y ninguna
  de las tres superficies de esta tarea pasa por ese job. La dependencia real es T-2.80, que está
  cerrada. Dejarlo como estaba hacía que la ficha afirmara que esto se construyó sobre algo que
  todavía no existe.)*
- **Criterios de aceptación:**
  - [x] La tabla existe desde el schema (`db/schema.sql:1323`) y **nadie la carga**. Alta y
        edición por tenant desde la consola, auditada.
  - [x] Las etiquetas se ven donde importan (dictamen, evidencia), no solo en un formulario.

> **Lo que hace fiable el criterio 2 es que las tres superficies salen del MISMO
> `compliance_block`**: el dictamen PDF (§12, inmediatamente antes de la firma, y repetido en el
> ejecutivo), la pantalla de Triage donde el inspector **firma**, y el móvil del ocupante. Papel
> y pantalla no pueden divergir porque no hay dos funciones que puedan discrepar.
>
> La auditoría se hizo dos veces. La primera dictaminó `[~]` por tres defectos de la pantalla de
> firma; la segunda los re-midió tras arreglar el contrato y **corrigió a la primera** en dos
> puntos: el `empty` que afirmaba una ausencia no comprobada **ya no es alcanzable**, y la falta
> de `stale` **no es deuda de esta tarea** — `TriageDetail` clava `staleSince={null}` a mano en
> los tres paneles, o sea que **ninguno** de esa página lo tiene. Arreglarlo solo aquí sería la
> deriva por componente que denuncia T-2.79.d. Fichado aparte como `T-2.82.a`.
>
> La auditoría **verifica el texto íntegro en la bitácora**, no un «cambió», y lo archiva bajo el
> tenant **tocado**, no bajo el del operador — que es la fuga que T-2.71 ya pagó una vez.

### [x] T-2.82.a · Ningún panel de la pantalla donde se FIRMA tiene `stale` — `SOFTWARE`
- **Componente:** web · **Depende de:** — · **Hermana de `T-2.79.d`, y conviene resolverlas
  juntas** · **Detectada por:** reauditoría de la Fase 2.8 (2026-08-08)
- **Regla de oro 7, en la peor pantalla posible.** `TriageDetail.tsx` monta sus tres paneles con
  `staleSince={null}` **clavado a mano**, y `useForensics.ts` ni siquiera expone
  `dataUpdatedAt`. O sea: en la pantalla donde el inspector **firma un dictamen**, ningún panel
  puede decir que su dato está viejo. Un dato congelado se pinta como vivo, que es exactamente lo
  que la regla prohíbe.
- **No es deuda de T-2.82**, y la reauditoría corrigió a la primera auditoría en esto: no es que
  `ComplianceDeclared` se montara mal, es que **la página entera** no tiene el concepto.
  Arreglarlo solo en un componente sería la deriva que denuncia `T-2.79.d`.
- **Criterios de aceptación:**
  - [x] `useForensics` expone la edad del dato, y los paneles de `TriageDetail` la reciben.
  - [x] Un test que recorra los paneles de esa página y exija que **ninguno** clave `staleSince`
        a `null`. Derivado del árbol de la página, no una lista de tres.
  - [x] La precedencia que decida `T-2.79.d` se aplica aquí sin excepciones locales.

> **Cerrada (2026-08-12): 8 marcos de 8.** `FRESCURA_CLAVADA` queda **vacía**. La pantalla donde
> se firma un dictamen puede por fin declarar que su dato está viejo, panel a panel.
>
> **El plan que parecía obvio era falso, y de un modo que importaba.** «Una línea:
> `updatedAt: q.dataUpdatedAt`» habría expuesto la marca **cruda**, obligando a cada uno de los 4
> paneles a derivar **su propio** veredicto —su umbral y su `now`—, que es **exactamente la deriva
> que `T-2.79.d` acaba de cerrar**. `Resource<T>` lleva el **veredicto ya resuelto**, calculado
> una vez con un solo reloj. Y no era una línea: sin el guard de `dataUpdatedAt <= 0`, los paneles
> dirían **«viejo desde 1970»** mientras la consulta está en vuelo o deshabilitada.
> Igual de falso: `QuorumNodes` necesitaba **dos** edades (la del incidente y la del evento, datos
> distintos), y copiar `useForensics` en `useDamageReports` habría **triplicado** el deslinde.
>
> **El umbral se midió, no se eligió:** `queryClient` desactiva `refetchOnWindowFocus` y ninguna
> consulta del triage lleva `refetchInterval` — en esa pantalla **nada se refresca solo**, así que
> los marcos envejecen a la vez desde que se abrió el detalle. Un umbral (900 s, mayor que el
> `staleTime` más largo para que el aviso no viva encendido), con una excepción deliberada: la
> fila del incidente conserva el reloj con el que `TriagePage` ya fecha el HISTORIAL — un dato, un
> veredicto.
>
> **Dos guardas que evitan un verde falso:**
> - **No-vacuidad del censo:** una lista vacía también «cuadra» si el analizador se queda ciego,
>   así que se exige que la derivación siga viendo los **ocho** marcos por su clave.
> - La guarda heredada decía «la pieza que bloquea SIGUE faltando» y se ponía roja **al pagar la
>   deuda**; invertida a «SIGUE en su sitio», que es el riesgo nuevo — quitar la edad de
>   `Resource<T>` no rompería ninguna prueba de panel.
>
> **Falso positivo cazado en el propio analizador:** buscaba un atributo llamado literalmente
> `staleSince`, así que un panel bien cableado con otro nombre salía acusado — **presión para
> renombrar props solo para contentar al test**.
>
> **Deuda declarada:** `StructuralTriage` tiene la prueba del estado `stale` con reloj falso, no
> el barrido de los cuatro estados; forzarlos en un `render` síncrono pide reestructurar el
> ayudante. Sigue listado en `serverDataCensus` C-4, con la razón corregida.

### [x] T-2.82.b · Cuatro sitios se escribieron tipos a mano, y el SDK ya los trae — `SOFTWARE`
- **Componente:** web + mobile · **Depende de:** — · **Detectada por:** reauditoría de la
  Fase 2.8 (2026-08-08)
- **La condición para pagar esta deuda ya se cumplió.** Cada uno de esos sitios lleva un
  comentario diciendo «sustituir cuando el SDK se regenere». El SDK **se regeneró** el
  2026-08-08 y ahora publica `ComplianceDocOut`, `ComplianceLabelsOut`, `ConsentStatusOut`,
  `NoticeOut` y las funciones de `/privacy/*`, todos con sus campos **requeridos**. Los cuatro:
  `web/src/features/triage/ComplianceDeclared.tsx`, `web/src/features/tenants/useComplianceLabels.ts`,
  `web/src/features/privacy/usePrivacyConsent.ts` y `mobile/src/services/privacy.ts`.
- **Por qué importa y no es limpieza:** un tipo escrito a mano es una **segunda verdad sobre el
  mismo cable**. Ya pasó: la consola afirmaba que `provenance` siempre viene y el contrato decía
  que podía faltar. La consola tenía razón — y aun así, tener dos fuentes es lo que permitió que
  la discrepancia viviera meses sin que nadie la viera.
- **Hueco de cobertura del mismo lote:** `useComplianceLabels` y `useSaveComplianceLabels`
  **no se ejecutan en ningún test** — su único consumidor mockea el módulo entero. El mapeo de
  errores 403/404/409/422 y el umbral de 5 minutos son código de producción que **nunca ha
  corrido**.
- **Criterios de aceptación:**
  - [x] Los cuatro sitios consumen los tipos generados; cero interfaces de respuesta a mano.
  - [x] Un test ejercita `useComplianceLabels` de verdad, incluido el mapeo de errores.
  - [x] Una guardia que impida reintroducirlo: ninguna superficie declara a mano la forma de una
        respuesta que el SDK ya publica.

### [x] T-2.83 · Residencia de datos: evaluar región MX — `DECISIÓN` (+ `LEGAL`) · COMPLETA (2026-08-08)
- **Componente:** infra + docs · **Depende de:** —
- **Documento:** [`RESIDENCIA-DE-DATOS-TAKAB.md`](RESIDENCIA-DE-DATOS-TAKAB.md) — es **la
  respuesta que se le lee al cliente que pregunta**, y §2 trae el guion literal para leerlo en
  voz alta. Estuvo huérfano hasta el 2026-08-08: existía y no lo enlazaba nadie, que para un
  criterio cuya finalidad es «que el primer cliente que pregunte tenga respuesta» es casi lo
  mismo que no existir.
- **Criterios de aceptación:**
  - [x] Documento con coste, latencia y servicios disponibles en la región MX **medidos**, no
        supuestos.
  - [x] Recomendación explícita y su razón; si es "no migrar", queda escrito por qué, para que
        el primer cliente que pregunte tenga respuesta.

> **La recomendación: NO migrar a `mx-central-1` hoy.** Razón en una línea: **AWS IoT Core no
> existe en la región de México** — y es el servicio por el que entra cada latido de cada
> gabinete. El coste (+5 %) y la latencia (−48 ms, y **fuera del camino crítico**, que es local
> por diseño) no mueven la decisión ni en un sentido ni en el otro.
>
> **Un auditor independiente re-derivó las mediciones el 2026-08-08 y cuadraron cifra por
> cifra**: `iot.mx-central-1` → NXDOMAIN mientras `us-east-2` resuelve; mediana TCP 11.9 ms
> contra 59.8 ms; y los dos SKU de S3 dando exactamente +5.00 %. Eso es lo que convierte «medido»
> en algo comprobable en vez de en una palabra.
>
> **Matiz honesto sobre «medido», que el propio documento declara:** el coste es **precio de
> lista** de la Price List API, no una factura. Un coste medido de `mx-central-1` exigiría
> desplegar allí — que es justamente lo que se está decidiendo no hacer. El antónimo que pone el
> criterio es «supuesto», y aquí no hay nada supuesto.
>
> **Reserva material saneada al cerrar:** §9 citaba como evidencia cinco ficheros en `/tmp` que
> ya no existen. Los comandos que re-derivan las cifras sí viven **dentro** del documento
> versionado (§8.3) — se comprobó — así que lo que estaba mal era el puntero, no el hecho. No es
> la familia de la cita de AWS inventada que esta fase cazó en T-2.71; es más leve, y se corrige
> igual: una cita de procedencia muerta es una que nadie puede seguir.

## Fase 2.9 · Trazabilidad y paquete de entrega

Va **después** de 2.3–2.8 porque **documenta lo que esas fases producen**. Escribirla antes
sería documentar intenciones.

> ### CERRADA (2026-08-08) — y documentar resultó ser un método de auditoría
>
> **Las tres tareas están `[x]`:** T-2.84 (matriz generada), T-2.85 (manual de operación) y
> T-2.86 (entrega y aceptación). El paquete de entrega existe y **cada afirmación que contiene
> es defendible**, porque lo que no lo era se dejó fuera y se dijo por qué.
>
> **Lo que nadie esperaba de esta fase: encontró defectos que ninguna revisión de código había
> visto.** Para explicar un estado hay que ir a buscarlo, y ahí se ve lo que la pantalla **no**
> hace. Salieron así:
> - **el panel calcula el resultado de `PROBAR ACTUADORES` y nunca lo pinta** (`T-2.85.a`) — una
>   prueba que ejerce físicamente gas y ascensores y no te enseña si pasó;
> - **cinco tareas cerradas tenían sus criterios enteros sin marcar**, contadas por la matriz;
> - **una actuación con el enlace caído no deja rastro auditable en ninguna parte**
>   (`T-2.86.a`), que es el caso exacto para el que existe el gabinete.
>
> **La matriz declara 18 huecos y ése es su producto.** Tres subieron a ficha en `T-2.84.a/b/c`
> y tres más en `T-2.86.a/b/c`; el resto siguen nombrados en la matriz, que es donde se ven. Los
> tres peores, por si se lee esto y nada más: **nada impide el streaming crudo continuo**, **MFA
> no tiene una sola línea de prueba**, y **el proceso mínimo probado no es el que corre de
> fábrica**.

### [x] T-2.84 · Matriz requisito→test — `SOFTWARE` · COMPLETA (2026-08-08)
- **Componente:** docs + tests · **Depende de:** Fases 2.3–2.8
- **Documento:** [`MATRIZ-REQUISITO-TEST.md`](MATRIZ-REQUISITO-TEST.md), **generado** por
  `api/tests/test_matriz_trazabilidad.py --escribir`. No se edita a mano.
- **Criterios de aceptación:**
  - [x] Cada requisito enlaza al test que lo demuestra, con `archivo:línea`.
  - [x] **Los huecos se marcan `SIN COBERTURA` explícitamente.** Una matriz sin huecos es una
        matriz que miente: el valor está justo en los huecos.
  - [x] Un test mantiene la matriz honesta (si el test citado desaparece, la matriz rompe).

> **17 requisitos · 66 afirmaciones · 48 cubiertas · 18 huecos.** Los requisitos se **derivan** de
> tres fuentes que se parsean en cada corrida: las 11 reglas de oro de `CLAUDE.md §2`, los
> invariantes del `BLUEPRINT §14` y los 10 gates físicos del runbook de cierre. Añadir una regla
> 12ª pone el censo en rojo.
>
> **`TASKS.md` se descartó como fuente, y por una razón medida: sus casillas mienten.** De 442
> criterios bajo tareas `[x]`, 34 seguían sin marcar y **cinco tareas cerradas tenían los suyos
> enteros en `[ ]`**. Se corrigió, y ahora lo vigila un test propio.
>
> **`CUBIERTO` se calcula, nunca se teclea.** Una cita solo acredita si existe, **no puede
> saltarse**, ejercita código y corre en un job que **bloquea el merge**. De ahí dos
> consecuencias que nadie habría escrito a mano: `web/e2e` **informa pero no acredita** (es
> `workflow_dispatch` + `continue-on-error`, a propósito), y los tres tests del gate `G-03`
> salen `SIN COBERTURA` **aunque existan**, porque el `skipif` del Shake los apaga en CI.
>
> **El ancla es el nombre del test; la línea se deriva por AST.** La asimetría es deliberada:
> renombrar un test citado pone **siete** en rojo; moverlo de línea pone **uno** y te da el
> comando para regenerar. Moverse cuesta un comando, desaparecer rompe la matriz.
>
> **Punto ciego declarado, y es el que hay que tener presente:** la **semántica no se comprueba**.
> Que un test citado *demuestre* su fila es juicio humano; lo mecánico es que exista, no se
> salte, y lo corra un job bloqueante.

### [x] T-2.84.a · Nada impide el streaming crudo continuo — `SOFTWARE`
- **Componente:** edge + api · **Depende de:** — · **Hueco `RO-9.a` de la matriz** (2026-08-08)
- **El hueco más grave que destapó la matriz.** Cero asserts sobre un conjunto cerrado de topics,
  sobre volumen publicado, o sobre que un `WaveformPacket` jamás llegue a
  `CloudConnector.publish`. **Añadir hoy un publicador continuo no rompería un solo test.**
- Es **regla de oro 9** *y* **invariante permanente** —prohibición, no diferido—, escrita en tres
  documentos y **sostenida por ninguna prueba**. `CLAUDE.md §8` la mantiene en párrafo aparte del
  mini-ShakeMap justamente para que nadie se la lleve por delante de arrastre: iban pegadas en una
  sola línea, y así las dos se levantaban juntas.
- **Cómo se descubriría hoy: en la factura de AWS.**
- **Criterios de aceptación:**
  - [x] Un test que falle si un `WaveformPacket` alcanza el camino de publicación continua.
  - [x] La dirección complementaria (`RO-9.b`): el miniSEED crudo **solo** sube en eventos
        confirmados; bajar el umbral por accidente tiene que ponerse rojo.
  - [x] Derivado, no enumerado: un publicador nuevo entra solo en la comprobación.

### [x] T-2.84.b · MFA no tiene una sola línea de prueba en ninguna capa — `SOFTWARE`
- **Componente:** api + infra · **Depende de:** — · **Hueco `RO-8.c` de la matriz** (2026-08-08)
- **Regla de oro 8, sobre la superficie que abre válvulas de gas, dice «sin excepción».** No hay
  comprobación de `acr`, `amr` ni `auth_time` en ninguna capa; el router lo documenta como
  delegado al pool (`mfa_configuration = "ON"`), y el módulo `identity` es **el único de los
  cuatro sin `.tftest.hcl`**: una deriva a `OPTIONAL` no la vería nadie.
- **Criterios de aceptación:**
  - [x] Un test rechaza un token sin la constancia de MFA en el camino de comando de actuadores.
  - [x] `identity` gana su `.tftest.hcl` y `mfa_configuration` queda anclado.
  - [x] La matriz pasa `RO-8.c` a `CUBIERTO` sola, sin editarla a mano.

### [x] T-2.84.c · Nada obliga al componente número 28 a manejar los cuatro estados — `SOFTWARE`
- **Componente:** web · **Depende de:** — · **Hueco `RO-7.a` de la matriz** (2026-08-08) ·
  **Hermana de `T-2.79.d` y `T-2.82.a`**
- **Medido por la matriz:** **27 componentes usan `StateFrame`, solo 14 tienen la prueba de los
  cuatro estados, y ≥12 pintan dato de servidor fuera de `StateFrame`.** No hay censo derivado que
  obligue al siguiente. **El bug de T-2.59 fue exactamente eso**, y T-2.82.a acaba de encontrar la
  misma clase en la pantalla donde se firma un dictamen.
- **Criterios de aceptación:**
  - [x] Un censo **derivado** del árbol de componentes: quien pinte dato de servidor sin los
        cuatro estados, rojo.
  - [x] Las excepciones legítimas se **declaran** con su razón, no se omiten.
  - [x] Se resuelve junto con la precedencia que decida `T-2.79.d`.

### [x] T-2.84.d · El censo de multi-tenancy eximía justo a la tabla infractora — `SOFTWARE` · COMPLETA (2026-08-09)
- **Componente:** db + api (tests) · **Depende de:** — · **Hueco `RO-5.a` de la matriz**
- **Medido:** nadie derivaba del catálogo que toda tabla de negocio llevara `tenant_id`. El único
  cruce que existía corría **de las tablas que tienen la columna hacia su RLS**, así que una tabla
  nueva **sin** la columna **se auto-eximía**: no la tiene ⇒ no entra al censo ⇒ no se le exige
  aislamiento.
- **Criterios de aceptación:**
  - [x] Censo derivado del catálogo vivo (`api/tests/test_censo_multitenancy.py`).
  - [x] Exenciones declaradas con su razón y comparadas por **igualdad**.
  - [x] **No vacuo:** una tabla de negocio de mentira sin `tenant_id` ni RLS pone el build en rojo
        **nombrándola**, y las dos mitades disparan por separado. Creada, medida y borrada.

> **El criterio de «tabla de negocio» es INCLUSIVO a propósito, y la razón está medida.** Se
> probaron primero los criterios sustantivos —«tiene FK a `tenants`», «la crea el migrador», «tiene
> política de escritura»— y **todos reintroducen el defecto**: cualquier criterio que se apoye en
> una propiedad que la tabla infractora **no tiene** la exime justo por lo que la hace sospechosa.
> El único criterio seguro es el que una tabla nueva **no puede dejar de cumplir: existir**. La
> única resta es estructural y no falsificable por accidente —ser miembro de una extensión—, y hoy
> se lleva exactamente `spatial_ref_sys`.
>
> **Tres formas de cumplir, no una**, porque TimescaleDB no admite RLS con caggs: RLS propia, o
> vista `security_barrier` **con la base revocada al rol de la API y anclada en una tabla con
> RLS**. Las tres condiciones juntas o no cuenta — y no es sello de goma: un test devuelve el
> `SELECT` sobre la base dentro de una transacción y `waveform_features_1s` cae a «sin
> aislamiento», nombrada.
>
> **Resultado sobre el esquema real: 43 tablas de negocio, NINGUNA desprotegida.** 7 sin
> `tenant_id`, todas declaradas: seis son diseño (plataforma, dato regional compartido, grants que
> tienen **dos** tenants y una columna tendría que elegir uno y mentir sobre el otro) y **una es
> deuda** — ver `T-2.84.e`.

### [x] T-2.84.e · `site_ground_refs` aísla de verdad, pero no como la regla lo pide — `SOFTWARE` · COMPLETA (2026-08-23)
- **Componente:** db · **Depende de:** T-2.84.d · **Hallazgo del censo** (2026-08-09)
- Es dato de un cliente —el punto cero del calibrador, `ATTEN-LAW`— y **le falta la columna
  `tenant_id`** que la regla de oro 5 pide literalmente.
- **No es un agujero, y por eso no bloquea:** su aislamiento es real y está verificado cruzando
  tenants en base nueva (el tenant B ve **0** filas, el dueño ve **1**), por el `EXISTS` contra
  `sites`. Es una lectura **no literal** de la regla, no una excepción a ella.
- **Por qué merece cerrarse igual:** el censo la lleva hoy en la lista de exenciones declaradas, y
  cada exención es una línea que alguien tiene que volver a justificar. Una menos es una menos.
- **Criterios de aceptación:**
  - [x] Migración con **backfill desde `sites`** y las dos políticas correspondientes (`0050`).
  - [x] La entrada desaparece de `SIN_TENANT_ID`, y el test lo **exige** (se compara por igualdad).
  - [x] El cruce de tenants sigue dando 0/1, ahora por la columna y no por el `EXISTS`.

> ### EL BACKFILL QUE ESTA FICHA DESCRIBÍA ACTUALIZABA CERO FILAS, y está MEDIDO
>
> `site_ground_refs`, `sites` y `sensors` las **posee `takab_migrator`** y las tres llevan
> `FORCE ROW LEVEL SECURITY`, que aplica RLS **también al dueño** — y Alembic conecta como ese
> dueño. Así que el `UPDATE … FROM sites` obvio se filtra a sí mismo: `sgr_write` exigía
> `s.tenant_id = app_tenant_id()`, y en una migración `app_tenant_id()` es NULL. Medido sobre una
> fila real: **variante obvia → 0 filas; con `FORCE` levantado → 1**.
>
> En una base CON datos el `SET NOT NULL` habría abortado la migración (ruidoso, y por suerte);
> en una base sin filas de suelo habría pasado **en verde dejando el invariante sin demostrar**.
> Es la misma familia que «local migra como superusuario, la nube como `takab_migrator`».
>
> **Se levanta `FORCE` sólo en `site_ground_refs`**, la tabla que la migración está alterando, y
> se restaura dos sentencias después. Las otras dos vías se descartaron con medición: tocar
> `FORCE` en `sites` funciona pero mueve la isolación de la tabla más central del esquema;
> declarar `app.role` a secas **no basta** (abre `sites_read`, pero el que bloquea es `sgr_write`
> sobre la tabla destino) — 0 filas. Y un `DO $$` fail-closed para la migración si algo quedara
> huérfano, porque poner `NOT NULL` encima de un backfill incompleto lo esconde.
>
> **Y la regresión de visibilidad que casi entra de tapadillo:** `sgr_read` era un `EXISTS` SIN
> condición de tenant, así que bajo RLS heredaba los CUATRO caminos de `sites_read` —propio
> tenant, TAKAB interno, `gov_operator` sobre `gov_shared`, y los grants de metadatos de T-1.73—.
> Escribir `tenant_id = app_tenant_id()` a secas habría quitado los tres últimos sin que nada se
> quejara. La política nueva los enumera. Y NO se añadió `sgr_admin`: antes no existía, así que
> TAKAB interno sigue leyendo y no escribiendo — ampliar permisos no es efecto colateral de
> añadir una columna.
>
> Anclado en `test_rls_isolation.py` (cruce 0/1 por columna, el owner bajo FORCE, y el
> `WITH CHECK` que impide etiquetar una fila con el tenant del vecino).

### [x] T-2.85 · Manual de operación de cliente — `SOFTWARE` · COMPLETA (2026-08-08)
- **Componente:** docs · **Depende de:** T-2.84
- **Documento:** [`MANUAL-OPERACION-TAKAB.md`](MANUAL-OPERACION-TAKAB.md) — 642 líneas, con ficha
  de sitio rellenable y un resumen de una página para imprimir y colgar.
- **Criterios de aceptación:**
  - [x] Escrito para un operador, no para un desarrollador.
  - [x] Qué hacer **cuando cae la nube** (regla de oro 2 explicada en lenguaje de operación).
  - [x] Qué significa cada estado del panel del gabinete y qué acción pide.

> **Cada estado lleva columna «Qué haces» y urgencia `AHORA` / `HOY` / `ANOTAR`.** Un manual que
> solo traduce tokens no sirve a quien lo lee de noche con el edificio temblando: «
> `gpio_unreachable`» no le dice nada; «el gabinete no controla los relés: la sirena podría no
> sonar — avisa a soporte AHORA» sí.
>
> **§6.0 está dedicada a los tres ejes que este repo lleva tres tareas separando** (T-2.58,
> T-2.68) y que un manual descuidado habría vuelto a colapsar: `S/D` (no hay dato) ·
> `DATO RETENIDO` (el dato es viejo) · `NO CONTESTA` (la pieza está caída). **Cada una pide una
> acción distinta.** Y §5 desambigua el error que un operador cometerá una vez: confundir
> `SIN ENLACE` (Pi↔nube, ámbar, poco grave) con `SIN CONEXIÓN CON EL GABINETE` (navegador↔Pi,
> rojo, grave).
>
> Todos los estados están **derivados del panel real con `fichero:línea`**, no inventados ni
> copiados de memoria — incluidos los siete umbrales de vejez, que salen de siete sitios
> distintos del código y de Terraform.
>
> **Ocho huecos declarados en vez de rellenados con prosa tranquilizadora**, y el más incómodo es
> H-2: el manual da la orden «avisa a soporte» **36 veces** —y menciona a soporte **52** en
> total— y **ese teléfono no existe en el repo**: el runbook de on-call declara que hoy solo se
> entrega un correo y que el salto 2 es un hueco.
> Lo cierra el criterio de escalamiento de `T-2.78`. Los otros siete son de hardware sin
> acreditar (gate #3), de ajustes de instalación no fijados, o de superficie que no existe.

### [x] T-2.85.a · El panel calcula el resultado de la prueba de actuadores y no lo pinta — `SOFTWARE`
- **Componente:** edge (panel) · **Depende de:** — · **Detectada al escribir el manual**
  (2026-08-08)
- **El defecto, con las dos mitades a la vista.** `local_api/__init__.py:1106` promete por
  escrito: *«El resultado por relé aflora en `status()` para que el panel lo pinte»*. El panel
  **solo lee `actuation_test.active`** (`index.html:914`). Los `results` —`held`, `pulsed`,
  `readback_ok` por relé— viajan en el JSON y **aparecen únicamente en los datos de prueba** del
  propio HTML, nunca en un camino de render.
- **Por qué duele operativamente:** `PROBAR ACTUADORES` hace **lectura de retorno** sobre el gas
  y los ascensores —o sea, ejerce físicamente el equipamiento del edificio— **y no te enseña si
  pasó**. El manual de operación no puede decirle al operador cómo saber el resultado de la única
  prueba que puede hacer él solo. Es el hueco más accionable que destapó T-2.85.
- **Misma familia, mismo sitio:** `calibration.source` tampoco se pinta. El panel dice
  `SIN CALIBRAR`, pero cuando **sí** hay calibración nunca dice de dónde vino — y de eso depende
  que el PGA esté en `g` o sea un número relativo.
- **Criterios de aceptación:**
  - [x] El resultado por relé se pinta tras `PROBAR ACTUADORES`, con su lectura de retorno.
  - [x] Un relé que **no** confirma se distingue de uno que no se probó. Regla de oro 7.
  - [x] `calibration.source` se pinta cuando existe.
  - [x] Test que falle si un campo declarado en `status()` **no tiene camino de render** — la
        clase de defecto, no el caso.

> **Cerrada (2026-08-13), y el defecto era CUATRO VECES mayor que la ficha.** El último criterio
> —«la clase de defecto, no el caso»— se cumplió con un censo que **muta cada hoja del `status()`
> real, re-renderiza y compara el DOM**: ~170 rutas, dos mutaciones por hoja. **Rojo medido: 53
> rutas mudas**, de las que las 13 de `actuation_test.results.*` y `calibration.source` eran solo
> las que alguien había mirado. Nadie sabía el resto porque nadie había preguntado *qué más
> calcula el gabinete que no enseña*.
>
> Lo que ve el operador distingue ahora **tres cosas que antes eran una sola**:
> `PULSO · NO CONFIRMÓ EL RETORNO` / `SIN RELÉ DETRÁS · NO SE PUDO PROBAR` / `NO SE PROBÓ` — esto
> último derivado de cruzar `relays_status.installed` con las claves del resultado.
>
> **Y se añadió la FECHA de la prueba** (`finished_at` + `age_s`, derivados en el gabinete), con
> su razón: **un `RETORNO CONFIRMADO` sin fecha sobre el gas y los ascensores es dato congelado
> en verde** — el defecto del 14-jul otra vez, visto venir.
>
> Tres hallazgos del censo que se arreglaron de paso: una promesa rechazada dentro de `render()`
> **mataba el proceso del arnés en silencio**; el arnés no miraba `style.cssText`, donde el panel
> pinta el color de cada gabinete LoRa; y `events_by_tier.manual_only` se contaba y no se
> enseñaba nunca.

### [x] T-2.85.b · El panel y la consola hablan idiomas distintos del mismo estado — `SOFTWARE`
- **Componente:** edge (panel) + web · **Depende de:** — · **Detectada al escribir el manual**
  (2026-08-08)
- El panel del gabinete dice `NO CONTESTA`, `DATO RETENIDO`, `S/D`. La consola de la nube dice
  `OPERATIVO`, `DEGRADADO`, `SIN DATO` (`BLUEPRINT:105`). **Son vocabularios distintos para la
  misma realidad**, y quien opera mira las dos pantallas: primero el panel en el sitio, luego la
  consola desde el SOC — o al revés, en plena madrugada.
- No es cosmético: el manual de operación tuvo que **elegir uno** y advertir del otro. Cada
  traducción que un operador hace mentalmente bajo presión es un sitio donde se equivoca.
- **Criterios de aceptación:**
  - [x] Un glosario único, y las dos superficies salen de él.
  - [x] Donde el estado no pueda ser idéntico (el panel ve cosas que la nube no), la diferencia
        **está declarada** y el manual la explica una sola vez.
  - [x] Un test que impida que una superficie estrene un literal de estado fuera del glosario.

> **Cerrada (2026-08-13).** El glosario vive en `shared/glossary/estados.json` —JSON y no módulo
> **porque el panel no puede importar nada**: es un fichero estático de un Pi sin build, mismo
> patrón físico que `design-tokens/tokens.json`—. La consola lo deriva **en ejecución** (un test
> compara módulo↔JSON por igualdad en los dos sentidos); el panel, **en tiempo de test**.
>
> **Lo que más vale es lo que se negó a unificar.** Tres ejes quedan declarados como
> legítimamente asimétricos, con su razón escrita y un test que exige que cada lado en `null`
> traiga el porqué:
>
> | Eje | Solo en | Por qué |
> |---|---|---|
> | `OPERATIVO`, `DEGRADADO` | consola | Es un veredicto **sobre el latido**. **Un gabinete no puede afirmar de sí mismo que la nube lo ve operativo** — eso fue exactamente el fallo del 14-jul: 15 h ciego con la consola en verde. |
> | `DETENIDO` vs `AVERÍA` | panel | Distinguir «no corre» de «corre y falla al leerse» exige estar **dentro**; por el latido se ven iguales. |
> | `SIN CONEXIÓN CON EL GABINETE` | panel | La consola no habla con un gabinete, habla con la nube: el eje **no existe** al otro lado. |
>
> **El candado no enumera literales, declara raíces** (`RETENID`, `CONGELAD`, `NO RESPONDE`,
> `ILEGIBLE`, `DEGRADAD`…) y exige que toda frase en mayúsculas que toque una raíz use el término
> canónico de su eje. Probado **contra frases sintéticas antes de creerle**: 5 que debe cazar, 4
> que no debe acusar.
>
> **Deuda declarada, ya vigilada por test para que no se eternice:** `StateFrame.tsx` dice
> `DATOS RETENIDOS` donde el glosario dice `DATO RETENIDO`, y `schemas/fleet.py` dice
> `RELÉS ILEGIBLES` donde el panel dice `NO CONTESTA`. Y **el manual de operación hay que
> actualizarlo** — que es de donde salió esta ficha.

### [x] T-2.86 · Documento de entrega y aceptación — `SOFTWARE` (firma: `LEGAL`) · COMPLETA (2026-08-08)
- **Componente:** docs · **Depende de:** T-2.85
- **Documento:** [`ENTREGA-Y-ACEPTACION-TAKAB.md`](ENTREGA-Y-ACEPTACION-TAKAB.md), con campos y
  firmas **en blanco**. La firma sigue siendo `LEGAL`.
- **Criterios de aceptación:**
  - [x] Dice **qué hace y qué NO hace** el sistema, con la misma claridad las dos cosas.
  - [x] Incluye la sección de **invariantes** como parte del alcance contratado.
  - [x] Enlaza la matriz de T-2.84, huecos incluidos.

> **«Con la misma claridad las dos cosas» no se resolvió con dos listas simétricas**, porque el
> «no» **no es una sola cosa**. Se parte en cuatro clases que se leen distinto en un juzgado:
> **invariantes** (nunca lo va a hacer, con su razón en una línea de no-técnico — no se pueden
> pedir después) · **diferidos** (podría construirse) · **bloqueado fuera del software** (los 10
> gates con columna de firma, terceros, residencia, marco normativo) · **lo hace pero nadie lo
> prueba** (los 8 huecos del manual y los 18 de la matriz, dentro del documento y en lenguaje de
> cliente, no escondidos en un anexo).
>
> **Lo que NO se escribió importa tanto como lo que sí**, y quedó dicho con esas palabras:
> CCTV/ONVIF (está en el deck, el código no existe), mapa MMI, **llaves KMS por tenant** —el
> propio blueprint declara que en RDS compartida sería un over-claim—, **ECS Fargate**
> (`CLAUDE.md §3` lo nombra y en Terraform **no hay ni un recurso**), la entrega en ≤30 s por SMS,
> y cualquier cifra de RTO o disponibilidad. Ninguna se puede defender hoy.
>
> Y **«el gabinete corre el proceso mínimo y auditable» quedó como HUECO, no como capacidad**:
> el valor de fábrica es el contrario.

### [x] T-2.86.a · Una actuación con el enlace caído no deja rastro auditable en ninguna parte — `SOFTWARE` · COMPLETA (2026-08-26)
- **Componente:** edge + api · **Depende de:** — · **Hueco `RO-4.e` de la matriz** · **El de más
  peso contractual de los 18, y no tenía ficha** (2026-08-08)
- **Verificado de primera mano:** `ActuatorAck` (`edge/takab_edge/contracts.py:196`) lleva canal,
  acción, `event_id`, éxito y latencia — **pero no lleva actor**. Y **no existe ningún
  `audit_log` en todo `edge/takab_edge/`**: la bitácora vive **solo** en la nube.
- **Por qué es el peor de la lista para un contrato.** El caso exacto para el que existe el
  gabinete —regla de oro 2, el edge opera sin nube— es precisamente el que **no deja
  constancia**. Si el gas se cierra durante un corte de internet, después nadie puede decir
  **quién lo ordenó ni con qué causa**. Es lo primero que pediría un perito o un seguro, y el
  documento de entrega ha tenido que declararlo como hueco.
- Es la **mitad no construida de la regla de oro 4**: «el proceso GPIO es mínimo **y auditable**».
- **Criterios de aceptación:**
  - [x] Toda actuación deja constancia **local**, con actor y causa, sobreviva o no el enlace.
        El embudo es `ActuatorManager._record` —por donde pasan `execute` y `execute_sequence`—,
        así que es estructural y no disciplinario.
  - [x] Esa constancia **sube** cuando el enlace vuelve, sin duplicarse (regla de oro 3).
        **Cerrado el 2026-08-26 con las cuatro piezas de nube que faltaban**, por `takab/audit`:
        - **Topic autorizado** en la política del fleet. Era la pieza que bloqueaba a las otras
          tres: la política lista los topics uno a uno **sin comodines**, y publicar en uno no
          autorizado no degrada nada — el broker **corta la sesión MQTT en cada publish** y deja
          al gabinete mudo, camino de vida incluido (producción, 2026-07-12, flapping cada 10 s).
        - **Regla IoT** `takab_dev_audit` → la cola de eventos (el SQL de IoT no admite varios
          topics en `FROM`: una regla por topic).
        - **Tabla** `actuation_records` (migración `0052`), con `record_id` **del gabinete** como
          PK. Es lo que hace idempotente la re-subida: lo local **no se borra al subir** —el
          perito lo lee meses después—, se avanza una marca de agua, y si esa marca se pierde el
          `ON CONFLICT DO NOTHING` absorbe lo repetido. **Append-only por trigger**, como
          `audit_log`: es prueba, no un registro editable. Y `takab_app` **no tiene INSERT** — una
          bitácora que la API pudiera escribir dejaría de probar lo que hizo el gabinete.
        - **Ingesta** `handle_actuation_record`, que toma las tres identidades del **registro** y
          no del payload: escribir la identidad que declara el mensaje dejaría a un gabinete
          comprometido plantar evidencia en el tenant de otro cliente.
        - El `sink` publica **directo, sin spool**, y eso hace honesta la marca de agua: `drain()`
          solo la avanza sobre entrega CONFIRMADA. Por el spool avanzaría al encolar, o sea sobre
          un «ya lo mandaré» — justo la mentira que esta bitácora existe para no contar.
        - Una fila **malformada se salta en vez de bloquear**: `drain()` corta al primer fallo
          (correcto con el enlace caído, donde el orden importa), pero una fila que nunca va a
          validar sacrificaría la subida de todo lo que venga detrás. Saltarla no pierde nada —
          lo local no se borra jamás.
  - [x] **El acoplamiento que costó un despliegue ya es un test**: `takab/audit` cierra el círculo
        entre el censo de topics del edge y la política del Terraform
        (`test_todo_topic_que_el_gabinete_publica_esta_en_la_politica_del_fleet`). Vivía en un
        comentario y en la cabeza de quien lo había sufrido. Verificado por mutación: quitar la
        línea de la política enrojece.
  - [x] Test: actuar con la nube caída y demostrar que el registro existe y **nombra la causa**
        (`edge/tests/test_actuation_ledger.py`, tres tests).
  - [x] La matriz pasa `RO-4.e` a `CUBIERTO` sola — y lo hizo, con su reserva declarada.

### [x] T-2.86.b · La bitácora de los actuadores registra lo que salió bien y calla lo que se intentó — `SOFTWARE`
- **Componente:** api + edge · **Depende de:** — · **Huecos `RO-8.g` y `RO-8.k` de la matriz**
  (2026-08-08)
- Los dos juntos son un titular que un cliente de Protección Civil pregunta literalmente: **la
  superficie que abre válvulas de gas solo audita el camino feliz**.
  - `RO-8.g` — el **replay se rechaza pero no se audita**, ni en el edge ni en la nube. Un
    atacante que sondee con comandos repetidos es **invisible** en el `audit_log`.
  - `RO-8.k` — solo se audita el éxito. Lo que se **intentó** y no pasó no queda escrito.
- La regla de oro 8 llama a esto «la superficie más sensible» y exige nonce y rate-limit **sin
  excepción**; los mecanismos existen, lo que falta es que **dejen huella cuando actúan**.
- **Criterios de aceptación:**
  - [x] Un comando rechazado por replay, por rate-limit o por firma **queda auditado**, con su
        motivo.
  - [x] Test que dispare cada rechazo y exija su fila en el `audit_log`.
  - [x] `RO-8.e` de paso: el límite por sitio (`command_rate_site_per_min`) está implementado y
        **sin probar** — dos operadores coordinados agotan el presupuesto sin rojo.

### [x] T-2.86.c · No existe barrido de secretos en ningún sitio — `SOFTWARE`
- **Componente:** CI · **Depende de:** — · **Hueco `RO-6.a` de la matriz** (2026-08-08)
- **Medido:** ni test, ni paso de CI, ni pre-commit, ni `gitleaks`/`trufflehog`/`detect-secrets`.
  **La regla de oro 6 es la única que hoy se sostiene sobre la disciplina de quien escribe el
  diff.**
- Y es la clase de cosa que **un cuestionario de seguridad de hospital pregunta literalmente**,
  así que bloquea comercialmente antes que técnicamente.
- **Hermano del mismo hueco (`RO-6.c`):** `Settings` no valida el entorno y **sus defaults son
  credenciales de dev**, así que un secreto ausente en producción **cae al default en silencio**
  en vez de impedir el arranque.
- **Criterios de aceptación:**
  - [x] Un barrido de secretos corre en un job que **bloquea el merge**.
  - [x] En producción, un secreto ausente **impide arrancar**; no cae a un default de dev.
  - [x] Test que lo demuestre con un secreto retirado.

---

## BLOQUE III · Carril de gates (paralelo, dueño Mauricio)

> Este bloque corre **desde el día 1** y **el Bloque II no lo espera a él**. Al revés hay
> **una sola excepción declarada**: `T-2.94` (`G-06`, `G-08`) depende de `T-2.78` porque un
> simulacro con **cascada de notificación real** no se puede acreditar con canales simulados.
> Todo lo demás de este bloque depende, como mucho, de otra tarea de este mismo bloque:
> `T-2.92` y `T-2.93` —las dos sesiones que deciden si el producto es real— no esperan a nada.
> Ver la excepción 2 de la regla de ordenación.

## Fase 2.10 · Ventana AWS

### [x] T-2.105 · Una estación sola ordenaba evacuar a todo el edificio — `SOFTWARE` · COMPLETA (2026-08-09)
- **Componente:** api + mobile · **Depende de:** — · **Origen:** Mauricio movió el sensor con la
  mano y la app ordenó evacuar
- **La regla, ratificada el 2026-08-09** (y ya implícita en `T-2.32`): una alarma y un aviso de
  evacuación **solo** se despliegan si llega la señal del **WR-1 de SASMEX**, o si **tres o más
  inmuebles** rebasan el umbral **al mismo tiempo**. Cuando una estación individual siente
  movimiento por encima del umbral, **solo advierte al SOC y al gabinete** — pudo provocarlo un
  factor externo y no un sismo.
- **El defecto:** `mobile_state` derivaba la fase **sin mirar el origen**:
  `else: phase = "alert_active"` para cualquier incidente abierto con tier ≠ normal. Un umbral
  instrumental de un único gabinete producía **exactamente la misma toma de pantalla con
  «EVACÚE AHORA»** que SASMEX o que un cuórum de red. Medido en un Pixel 8 Pro.
- **El servidor ya tenía con qué distinguir y no lo usaba:** `incidents.trigger` ∈
  `(sasmex, local_threshold, quorum, manual)` y `quorum_min_nodes = 3`. El motor de cuórum **no
  reescribe el trigger** —solo hace `UPDATE incidents SET event_id`—, así que la corroboración
  se reconoce por el `node_count` del evento enlazado. Por eso el MISMO incidente nace
  `local_threshold` y **pasa a autorizar** cuando la red lo confirma, sin que nadie lo toque.
- **El arreglo:** `incident/autoridad.py`, función pura y default-deny, consultada por
  `mobile_state`. Un incidente que no autoriza **no se expone en absoluto**: ni fase, ni
  incidente, ni check-in de vida, ni bloqueo de reingreso. Devolver el incidente y decir `idle`
  sería pedirle al cliente que aplique la política, y **el teléfono jamás decide fases**
  (spec móvil §4.1).
- **Por qué el default-deny va en esa dirección:** equivocarse hacia «no ordeno evacuar» deja a
  la gente donde estaba; hacia el otro lado, la saca a la calle porque pasó un camión cerca del
  sensor.
- **Criterios de aceptación:**
  - [x] `sasmex` autoriza siempre; `local_threshold` sin corroborar **nunca**; con
        `node_count ≥ quorum_min_nodes`, sí. El mínimo sale de la configuración, no de un 3 a
        mano.
  - [x] Test de integración contra el endpoint real: una estación sola ⇒ `phase=idle`,
        `incident=null`, `reentry.blocked=false`. Verificado en las dos direcciones — quitar la
        regla lo pone en rojo con «una estación sola ordenó evacuar».
  - [x] El cuórum de red sí ordena evacuar, con el trigger todavía en `local_threshold`.

### [x] T-2.106 · La activación manual no tiene superficie propia en la app — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** api + mobile · **Depende de:** T-2.105 · **Decisión tomada (2026-08-09):**
  una activación manual es **alarma del inmueble, no evacuación sísmica**. Suena la sirena del
  edificio —que es su diseño— y la app debe anunciarla como tal: sin instrucción de evacuación
  sísmica y sin el contador T+ de sismo.
- **Hoy no hay regresión que arreglar, y conviene decirlo:** el pánico por quórum de 2 personas
  emite un comando `siren/activate` firmado y **NO crea incidente**, así que no llega a
  `mobile-state` en absoluto — la app no muestra nada. Y `AlertSource.MANUAL` del edge se usa
  para **cerrar** una alerta por operador (tier `normal`), no para abrirla. Es decir: esto es
  superficie NUEVA, no un defecto vivo.
- **Por qué importa igual:** la sirena suena y el ocupante no tiene en el teléfono ninguna
  explicación de por qué. Un edificio sonando sin que la app diga nada es exactamente el vacío
  que la app existe para llenar.
- **Criterios de aceptación:**
  - [x] Fase propia en el contrato (el teléfono no la infiere del `trigger`) o superficie
        equivalente, con su derivación documentada en `schemas/mobile.py`.
  - [x] La pantalla dice ALARMA DEL INMUEBLE, **no** «alerta sísmica», y no ordena evacuar.
  - [x] Un test ancla que un pánico jamás produzca `alert_active`.

> **Cerrada (2026-08-10).** Fase propia `building_alarm`; **lo sísmico gana SIEMPRE** en la
> precedencia. La señal es `commands.status = 'acked'` sobre un `siren/activate` emitido por una
> persona: el ack de ejecución que la regla de oro 8 ya exige. Se filtra por `acked` en **las dos
> direcciones**, para que mande *lo último que tocó el relé* y no lo último que alguien pidió; se
> excluye el actor del cuórum sísmico (que también emite `siren/activate`, pero llega por su
> incidente) y `channel='system'` (self-test y simulacros).
>
> **La corroboración que se planeó NO era posible, y medirlo es media tarea.** El estado real del
> relé **no existe en la nube**: la migración `0036` dice literalmente que no se persiste el censo
> canal a canal, solo **si el dato existe**. Así que lo que se puede hacer no es confirmar sino
> **DESMENTIR**: `relays_state = 'unreadable'` —el gabinete no puede ni preguntar quién gobierna
> sus pines— y la app calla. `stopped`/`NULL` no desmienten (mismo criterio que
> `fleet_degrade_reasons`). El desmentido se busca contra **el gabinete que ejecutó**, no contra
> el sitio: en un edificio de dos gabinetes, que a uno no le lean los relés no desmiente lo que
> confirmó el otro.
>
> **Caduca por cuatro salidas**, tres derivadas de dato real (un `deactivate` acked posterior; el
> gabinete que ejecutó lleva demasiado sin latir; `unreadable`) y una constante declarada de
> 30 min, justificada porque las tres alternativas no se sostienen: el `command_ttl_s` (30 s) es
> el TTL de **entrega** de la firma, el edge **no da duración** porque el relé **enclava** hasta
> que alguien lo silencie, y ese silencio suele ocurrir **en el panel del gabinete** y no vuelve
> como comando. Sin tope, un `activate` que nadie revirtió por la nube dejaría al teléfono
> anunciando una sirena **durante días**.
>
> **El texto, ámbar y con el deslinde ARRIBA** (lección de T-2.104: el texto grande manda):
> «NO ES UNA ALERTA SÍSMICA» / «ALARMA DEL INMUEBLE» / «ATIENDA A SU BRIGADA» / «TAKAB no conoce
> el motivo de la activación». No ordena evacuar, no pone contador T+ de sismo y **no reproduce
> el bucle de alerta** — sería la misma mentira en el único canal sin texto. 11 tests de la vista
> con los deberes negativos (ni `EVAC`, ni `SASMEX`, ni `SISMO`, ni `T+`).
>
> `ServerPhase` deja de transcribirse a mano en el móvil: sale de `MobileStateOut["phase"]`, así
> que una fase nueva deja el `switch` no exhaustivo y el typecheck cae.
>
> **HUECO DECLARADO:** entre el quórum y el ack la app dice `idle` **a propósito**, antes que
> afirmar una sirena que nadie confirmó. Y **el pánico no manda push** — decisión de producto
> fichada en `PENDIENTES-MAURICIO.md`; la app se entera en el sondeo (30 s en reposo, 5 s ya en
> `building_alarm`).

### [x] T-2.107 · El acuse del gabinete nunca volvía a la app — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** mobile · **Depende de:** — · **Detectada por:** auditoría de cableado
  app→API→edge (2026-08-10)
- **El defecto:** `panel.tsx` guardaba el `CommandOut` de la respuesta 201 —que siempre nace
  `pending`— y **no volvía a consultar nunca**. `GET /sites/{id}/commands` existía y estaba
  generado en el SDK, con **cero** referencias en la app; y el WS no transporta acuses. La hoja
  de control decía «ESPERANDO CONFIRMACIÓN DEL GABINETE» **para siempre**, sin poder distinguir
  «no ha acusado» de «rechazó».
- **Lo que más dolía:** las ramas `acked`/`rejected`/`expired` de `ackState.ts` eran código
  muerto, y entre ellas la frase que la spec §2.2 exige que la UI diga en vez de fingir éxito —
  «SU DEMANDA SE RETIRÓ · LA SIRENA SIGUE ACTIVA»— escrita con cuidado y jamás mostrada.
- **Criterios de aceptación:**
  - [x] La app sigue el acuse real hasta un estado terminal y lo pinta.
  - [x] La espera **tiene techo**, derivado del TTL real del comando.
  - [x] Las ramas terminales dejan de ser código muerto, con test que las alcanza **por el camino
        real de la UI**.
  - [x] Silenciar con alerta vigente ⇒ la sirena sigue sonando y la UI explica el porqué.

> **Cerrada (2026-08-10).** Se sigue por el endpoint REST y no por un canal WS nuevo, y no solo
> porque el canal no exista: `list_commands` ejecuta `EXPIRE_SITE` **antes** de listar, así que
> **preguntar** es justo lo que hace que el servidor resuelva un pendiente vencido.
>
> El techo sale de `expires_at − issued_at`, dos instantes del **mismo reloj del servidor**,
> contados desde que llegó la 201 — así el desfase teléfono/servidor no entra en la cuenta —
> más 5 s de gracia, porque el `expired` solo se escribe cuando alguien pregunta.
>
> `unconfirmed` se distingue a propósito de `expired`: uno es «el gabinete no acusó a tiempo, y
> consta»; el otro, «esta app no pudo enterarse de nada». Y lo dice sin adornos: **«NO se sabe si
> el gabinete ejecutó la orden: verifique el estado real en el sitio antes de repetir»**.
>
> Los tests **conducen la ruta real como una persona** —pulsan, pasan el paso 1 y deslizan de
> verdad el `PanResponder`— porque es lo único que alcanza el texto que se lee. Verificado a la
> inversa: con el cableado de antes, los 8 fallan.
>
> **HUECO DECLARADO ⇒ `T-2.116`:** el «estado recalculado del relé» que pide la spec **no existe
> en ningún contrato**, así que `sirenStillOn()` nunca pudo dispararse con datos reales.

### [x] T-2.108 · La cola offline prometía guardar capturas y reportes, y solo admitía check-ins — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** mobile · **Depende de:** — · **Detectada por:** auditoría de pantallas y de
  cableado (2026-08-10)
- **El defecto:** `sync.tsx` decía «sus **capturas y reportes** se guardan localmente y se
  enviarán automáticamente al recuperar la red». Era **falso**: `queue.ts` declaraba `checkin`
  como ÚNICO tipo, así que la cámara forense y el formulario de daños hacían POST directo y **sin
  red se perdían**. La pantalla que existe para dar confianza sobre la cola era la que mentía
  sobre su contenido.
- **Criterios de aceptación:**
  - [x] La cola admite fotos y reportes además de check-ins, y `headcount` entra sin reescribirla.
  - [x] Cámara y formulario **encolan**; el ciclo avión→captura→formulario→red→sync ocurre solo.
  - [x] La integridad forense sobrevive al encolado.
  - [x] «Personas atrapadas o heridas» salta al frente de la cola.
  - [x] El banner dice la verdad.
  - [x] `sync.tsx` cumple el contrato de 4 estados.

> **Cerrada (2026-08-10).** Multi-tipo por un **censo de tipos**, no por un `kind: string` suelto:
> las tres piezas que lo consumen son `Record<QueueKind, …>` y **no compilan incompletas**, así
> que añadir `headcount` es imposible de dejar a medias.
>
> **El binario no entra en la cola:** el item guarda el puntero al archivo privado —jamás la
> galería—, su tamaño y el SHA-256 sellado en captura. Y se añade la comprobación que la spec
> §2.3 pedía y no existía en cliente: **se re-hashea antes de registrar nada** y se aborta si no
> coincide. Si un byte cambió mientras la foto esperaba en el bolsillo, no se crea la fila ni se
> sube el blob.
>
> **El problema difícil, bien resuelto:** un reporte de daños **no puede** llevar `evidence_ids`
> del servidor, porque en avión no existen. Lleva `evidence_refs`, ids **locales** de items de la
> misma cola, que se resuelven al despachar — así el enlace forense sobrevive al modo avión. Un
> reporte espera a sus fotos, pero una foto `failed` **deja de retenerlo**: un JPEG roto no puede
> esconder un daño estructural.
>
> Se reutiliza `queuePriority`/`orderByPriority`, escritos desde T-2.12 con el comentario «se usa
> para ordenar el envío» y que solo tocaba su propio test.
>
> De paso, dos cuelgues silenciosos: `hydrate()` no capturaba, así que si la base local no abría
> la pantalla decía «Cargando su cola local cifrada…» **para siempre**; y `triage.tsx` dejaba
> `busy` en `true` tras un fallo de red.
>
> **HUECO DECLARADO ⇒ `T-2.113`** (idempotencia del registro de evidencia) y una reserva: `db.ts`
> gana dos columnas por `ALTER TABLE` tolerante a duplicado, y **jest nunca carga el módulo
> nativo**, así que merece una pasada en el Pixel del `GATE-HW`.

### [x] T-2.109 · El push se registraba sin inmueble — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** mobile + api · **Depende de:** — · **Detectada por:** auditoría de cableado
  (2026-08-10)
- **El defecto:** `registerDeviceForPush(siteId?)` se llamaba **sin argumento** desde
  `_layout.tsx` —el único punto de llamada de toda la app—, así que el token viajaba con
  `site_id: null`. Y el orquestador selecciona destinatarios con `WHERE site_id = %(site)s`.
  **NULL nunca iguala a un UUID.**
- **No era regresión viva, era una MINA.** Medido contra producción el 2026-08-10:
  `select count(*) from push_tokens` = **0**, porque el canal real sigue detrás de `GATE-STORE`
  (`T-2.97`). El día que ese gate aterrizara, el registro habría seguido mandando `null` y **la
  acreditación habría salido verde sin que sonara un solo teléfono**.
- **Criterios de aceptación:**
  - [x] El token se registra con el inmueble, en todo el ciclo de vida.
  - [x] Al enrolarse, se re-registra sin reinstalar ni cerrar sesión.
  - [x] No se queda apuntando al sitio anterior; `assert_site_access` intacto.
  - [x] Un sitio **sin destinatarios lo dice**, no calla.
  - [x] Test explícito de la mina, con control de no-vacuidad.

> **Cerrada (2026-08-10).** El parámetro pasa a ser **obligatorio**: volver a omitirlo no compila.
> El re-registro al enrolarse no se hace con una llamada nueva, sino haciendo que el efecto
> **dependa del sitio vigilado** — un solo punto de registro en toda la app es justo lo que
> impide que mañana alguien se quede atrás.
>
> Y el otro lado: verbo propio `notify_no_recipients` (patrón de T-2.75) tanto al encolar —donde
> el silencio era real: sin dispositivos no se encolaba y la pasada salía **verde**— como al
> despachar, donde cero dispositivos caía en la rama de fallo y reintentaba **tres veces contra
> una lista vacía** para acabar escribiendo `notify_failed`, que manda al operador a revisar SNS
> por un problema que no está en SNS.
>
> **La firma exacta de la mina** va en el payload: `tokens_sin_inmueble` distingue «nadie instaló
> la app todavía» (esperable hoy, a `info`) de «hay teléfonos registrados que no apuntan a ningún
> sitio» (la avería, a `warning`).
>
> **RESERVA declarada ⇒ `T-2.114`:** el sitio vigilado persiste en SecureStore entre sesiones y
> **no se limpia al cerrar sesión, a propósito** — borrarlo dejaría tirado al `occupant`, cuyo
> edificio no viaja en el claim de Cognito.

### [x] T-2.110 · `sirenActive` es un enclavamiento que nunca se libera — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** sdk + mobile · **Detectada por:** auditoría de cableado (2026-08-10)
- `ACTION_STATE` de `shared/sdk-ts/src/bms.ts` **no tiene `siren_off`**, así que
  `panel.tsx:144-146` deriva `sirenActive` de un `siren_on` que nunca se cancela: basta uno
  histórico para que la precondición «El gabinete reporta la sirena activa» quede `met=true` el
  **resto del incidente**, y el detalle afirme que el gabinete lo reporta **sin que nadie lo haya
  reportado**.
- T-2.75.a mitigó la mitad (una acción **simulada** ya no la satisface), pero un `siren_on` real
  sigue enclavando.
- **Criterios de aceptación:**
  - [x] El estado de sirena se **libera** cuando corresponde, derivado de dato real.
  - [x] La precondición de silenciar deja de autorizarse sola.
  - [x] Test que ancle el ciclo encender→apagar→precondición falsa.

> **Cerrada (2026-08-10), sobre el dato que le trajo `T-2.116`.** `sirenEvidence()` deriva con
> precedencia explícita: primero `payload.channel_state.activated` de la acción de sirena **más
> reciente** —el relé recalculado—, y solo si no viaja, el verbo. `null` significa **«no consta»,
> que no es «apagada»**, y el detalle solo dice «el gabinete reporta el relé…» cuando el gabinete
> lo midió de verdad.
>
> **El hallazgo que obligó a cambiar el diseño a mitad de camino:** `siren_off` en la traza es
> **la orden ejecutada, no el relé**. Un `deactivate` arbitrado escribe `siren_off` con la sirena
> sonando. Derivar del verbo —que era el arreglo obvio— habría creado **una mentira nueva en el
> caso exacto que describe la spec**. Por eso `channel_state` viaja también en el `ActuatorAck`.
>
> Conducta nueva a declarar: un `activate` cuyo acuse diga el relé en reposo ya no se pinta
> «SIRENA ACTIVADA», sino «EL COMANDO SE EJECUTÓ · LA SIRENA NO QUEDÓ ACTIVA», en tono crítico.
>
> **Deja abierta `T-2.119`:**
> `strobe_off`, `gas_open`, `elevator_released` y `door_retained` tienen el hueco idéntico.

### [x] T-2.111 · Un fallo de red cuelga botones de vida en silencio — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** mobile · **Detectada por:** auditoría de cableado (2026-08-10)
- El cliente del SDK **lanza** en error de red. `panic.tsx` (voto de pánico) y `lista.tsx`
  (check-in **delegado**) no capturan: `busy` se queda en `true` y **el dato se pierde sin decir
  nada**. (`triage.tsx` ya quedó cerrado por `T-2.108`.)
- Del mismo género: `crisis.tsx` y `checkin.tsx` caen en **spinner infinito** cuando no hay sitio
  vigilado —las dos pantallas de vida—, que es justo lo que el resto del código prohíbe.
- Y `notifyUnreported`/`closeHeadcount` no muestran resultado ni error: el táctico no puede saber
  si la notificación salió.
- **Criterios de aceptación:**
  - [x] Ningún botón queda `busy` tras un fallo de red; el desenlace se pinta.
  - [x] Sin sitio vigilado, las dos pantallas de vida declaran el estado en vez de girar.
  - [x] Existe el equivalente móvil de `expectFourStates` y las pantallas lo pasan.

> **Cerrada (2026-08-10).** El desenlace es accionable y no se traga nada: «Su voto NO se
> registró: **nadie ha sido avisado**. Revise su conexión y vuelva a mantener presionado. Si la
> emergencia es inmediata, avise en persona a la brigada.» `notifyUnreported`/`closeHeadcount`
> pasaron de `void promesa.finally(…)` a desenlace en **estado del componente** — no en variable
> local, porque `HeadcountView` se reconstruye en cada frame y en cada señal del WS.
>
> **Lo que hace que esto no se pudra no es el ayudante, es el censo.** Móvil tiene una señal
> estructural que la consola no tiene: **`expo-router` arma su tabla de rutas con
> `require.context` sobre `src/app`, así que el sistema de ficheros ES la población**. El censo
> no lleva ninguna lista de pantallas escrita a mano: recorre el árbol, deriva por cierre
> transitivo cuáles poseen dato de servidor (axioma: los hooks de LECTURA de TanStack) y compara
> sus cuatro listas **por igualdad**. Consecuencia buscada: la pantalla de vida número 12 entra
> sola en la población el día que se crea y pone el gate en rojo; y como la comparación es por
> igualdad, **arreglar una entrada sin borrar su línea también pone rojo**, así que la deuda solo
> puede bajar. El analizador tiene 9 tests contra fuentes sintéticas que le dan el código
> original de esta ficha y exigen que lo denuncie.
>
> **Un defecto tapado que salió de paso:** `lista` afirmaba «Sin incidente activo en su sitio»
> cuando lo que pasaba era que `mobile-state` estaba caído. El error del snapshot ahora gana al
> `empty`: una frase tranquilizadora ya no puede tapar un fallo.
>
> **Deja abiertas** `T-2.117`
> y `T-2.118`.

### [x] T-2.112 · `rejection_audit.py` declara seguir el patrón que causó T-2.73.c — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** api · **Detectada por:** `T-2.73.c` (2026-08-10)
- `api/src/takab_api/commands/rejection_audit.py:16` dice **explícitamente** que sigue el mismo
  patrón de conexión lateral que provocaba el interbloqueo a tres bandas. No se revisó.
- **Criterios de aceptación:**
  - [x] Medido si el defecto existe ahí también, con evidencia (no por parecido).
  - [x] Si existe, cerrado con la misma costura que `audit_out_of_band_async`.

> **Cerrada (2026-08-10). El defecto SÍ existía, y está medido, no razonado por parecido.**
> `tests/api/test_rejection_audit_deadlock.py` monta el ciclo a tres bandas completo y comprueba
> **en `pg_locks`** que el tercero está *encolado, no concedido* — es decir, el interbloqueo real
> que PostgreSQL no puede detectar, no una analogía. Antes del arreglo: 2 rojos, con la lateral
> colgada los 25 s del tope del **test** (`asyncio.wait_for`); sin ese tope la espera es infinita.
>
> **Matiz que corrige lo que decía el propio fichero:** el `except Exception` rotulado
> «best-effort» **no protegía nada aquí**, porque no hay excepción que capturar — solo espera. Un
> comentario que promete una garantía que el código no da es peor que no tenerlo.
>
> La costura es la de `audit_out_of_band_async`, y la constante se hizo **pública**
> (`LATERAL_LOCK_TIMEOUT` en `audit.py`) para que sea UNA política y no dos copias que deriven:
> el día que ese número cambie, cambia para las dos laterales.
>
> **Divergencia deliberada, escrita para que no se «arregle» por simetría:** aquí el `except`
> sigue siendo ancho, mientras que `audit.py` lo estrechó a `SQLAlchemyError`. Razón: esto se
> invoca en mitad de un rechazo, y un fallo de Python no puede convertir un 403 en un 500.
>
> **Deja abierta `T-2.121`:** hay
> dos conexiones más del mismo género, con distinto riesgo.

### [x] T-2.113 · El registro de evidencia no es idempotente, y la cola reintenta más — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** api + sdk + mobile · **Depende de:** T-2.108 · **Declarada por el propio
  T-2.108 como hueco**
- `POST /incidents/{id}/evidence` genera el `evidence_id` **en el servidor** y no acepta uno del
  cliente: si el registro va bien pero el PUT a S3 falla, el reintento crea una **fila de
  evidencia huérfana**. No es regresión —el POST directo hacía lo mismo— pero la cola reintenta
  más, así que el hueco se ve más. Roza la **regla de oro 3**.
- **Criterios de aceptación:**
  - [x] `EvidenceRegisterIn` acepta el `evidence_id` del cliente, con `ON CONFLICT DO NOTHING`.
  - [x] Test: registrar dos veces el mismo item no duplica fila.

> **Cerrada (2026-08-10). El defecto real NO era el que describía esta ficha, y era peor.**
> Medido en rojo antes de tocar nada: como `uq_evidence_incident_sha256` **ya existía**, el
> reintento de la MISMA foto no duplicaba fila — devolvía **409**. La cola lo clasificaba como
> 4xx ⇒ `markFailed`, y **la fila se quedaba en la base sin su blob en S3, con `verified=false`
> para siempre**. Ése era el huérfano: no una fila de más, sino una fila que ya no se podía
> completar nunca. Sin migración: `evidence_id` ya era PK.
>
> **La decisión que importa es qué se hace con un id ajeno**, porque aceptar un identificador del
> cliente abre superficie. La identidad forense de una foto **no es el id: es `(incidente,
> huella)`** —lo dice el índice único, no esta ficha—, así que el id del cliente es una
> *propuesta*. Si el INSERT choca, se exige que coincidan incidente + huella + (si lo propuso) su
> id; **cualquier otra cosa es 409, nunca `DO NOTHING` silencioso**, que ahí habría sido un fallo
> de aislamiento disfrazado de idempotencia:
>
> | caso | resultado |
> |---|---|
> | mismo id/incidente/huella (el reintento) | 200, misma fila, mismo `s3_key`, presignado nuevo |
> | id de OTRO incidente, mismo tenant | 409, sin fila nueva |
> | id de OTRO tenant | 409 **sin `s3_key` ni `upload_url`**; la fila ajena, intacta |
> | mismo id, OTRA huella | 409 — tabla append-only: dar un PUT ensuciaría la custodia |
> | sin id (cliente viejo), misma foto | 200 a la fila existente (antes era 409) |
>
> El `s3_key` se **deriva** del `evidence_id` para que el reintento presigne el mismo objeto, y el
> prefijo lo pone el servidor. **Y el lado cliente es el que cierra la ficha**: `sendEvidence`
> manda el id del ITEM de la cola, estable entre intentos — si el móvil generara uno nuevo por
> intento, todo lo anterior no serviría de nada.
>
> **Consecuencia forense que conviene tener escrita:** dos fotos idénticas byte a byte en el mismo
> incidente son **una sola evidencia**. Es correcto, pero significa que un reporte que enlace dos
> capturas iguales verá un solo `evidence_id`.

### [x] T-2.114 · El sitio vigilado se hereda entre usuarios del mismo teléfono — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** mobile + api · **Declarada por el propio `T-2.109`**
- `mySite.ts` persiste el `site_id` en SecureStore y **no lo limpia al cerrar sesión, a
  propósito**: borrarlo dejaría tirado a cualquier `occupant`, porque su edificio **no viaja en
  el claim de Cognito** —sale del enrolamiento— y necesitaría un código nuevo. Consecuencia: un
  usuario distinto en el mismo teléfono hereda el edificio del anterior.
- En el servidor lo frena `assert_site_access` (404/403) y el token no se crea, pero afecta
  también a `CrisisWatcher`.
- **Criterios de aceptación:**
  - [x] `/me` devuelve el sitio del `occupant`, para que el cliente no tenga que recordarlo.
  - [x] Cerrar sesión suelta el sitio sin dejar tirado a nadie.
  - [x] Test de dos usuarios distintos en el mismo dispositivo.

> **Cerrada (2026-08-10).** `GET /me` gana `enrolled_sites[]` leído de `user_zone_assignments`,
> así que **el teléfono deja de ser la única memoria del edificio de un ocupante** — que era la
> razón por la que no se podía borrar el caché al salir.
>
> El caché no se elimina: se le pone **dueño**. Lo guardado va sellado con el `sub` que lo fijó
> (clave nueva `.v2`; la `.v1` no se lee porque no dice de quién es), y la resolución tiene tres
> ramas con una razón cada una: **sin `/me`** (arranque offline con sesión en el Keychain) manda
> el caché, porque el portador es por construcción el mismo y quitarle el edificio ahí lo dejaría
> sin pantalla de crisis justo cuando no hay red (**regla de oro 2**); **con `/me` y caché de esa
> misma identidad** manda el caché, porque puede ser más fresco que el `me` del login (el
> enrolamiento recién canjeado no está allí — `T-2.103`); **caché ajeno o sin dueño** se ignora y
> decide el servidor, re-sellándolo para que el arranque sin red y el registro de push de
> `T-2.109` sigan teniendo su sitio.
>
> **Efecto colateral a conocer antes de desplegar, y no es menor:** `GET /me` **deja de ser
> claims puros y ahora abre sesión de base de datos**. Si Postgres cae, `/me` responde 5xx y **la
> consola web no arranca**, donde antes arrancaba con los claims. En móvil no hay regresión
> (`bootstrapSession` conserva la sesión con `me = null` y esa rama resuelve desde el caché). Es
> deliberado y está anotado en el docstring; queda fichado como
> `T-2.123`.

### [x] T-2.115 · El veredicto de un test depende del orden de recolección — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** api (tests) · **Detectada por:** `T-2.80.b`, confirmada en las dos direcciones
  (2026-08-10)
- `tests/auth/conftest.py:84` siembra `DB_SITE_PRIV` con code `'SA'` y `tests/api/conftest.py:116`
  con `'B2SA'`, **los dos con `ON CONFLICT DO NOTHING`**: gana quien corra primero. Correr
  `tests/auth` antes que `tests/api` pone rojo
  `test_events.py::test_los_votos_traen_el_codigo_de_la_estacion`. En orden natural, verde.
  > **Corrección medida al cerrarla:** esta ficha afirmaba además «**15 errores** en
  > `test_privacy.py`». **No se reproducen**, ni en el subconjunto ni en la corrida completa de
  > 812 tests: en DB limpia el orden malo produce **exactamente un** fallo. Los 15 venían de
  > estado residual de una corrida anterior, no de esta causa.
- **Misma familia que `T-2.73.c`:** la suite dice cosas distintas según cómo la invoques, y eso
  erosiona la confianza en todos los rojos futuros.
- **Criterios de aceptación:**
  - [x] La siembra es coherente entre familias, o cada una usa su propio sitio.
  - [x] Un test que invoque las dos familias **en el orden malo** y siga verde.

> **Cerrada (2026-08-10).** Las filas compartidas (`tenants` + `sites` con los UUID de
> `auth_utils`) ya no las escribe cada familia: viven en `api/tests/seed_shared.py` con
> `ON CONFLICT … DO UPDATE`. Son dos candados en uno — definición única (coherencia por
> construcción) y siembra **autoritativa**, así que ni el orden ni el estado residual pueden
> decidir el valor.
>
> **Y aquí está lo que esta ficha destapó de verdad, que es más grande que ella:** `tenants` y
> `sites` **no entran en ningún TRUNCATE**, así que sobreviven entre invocaciones de la suite. O
> sea que el veredicto no dependía solo del orden: dependía **del estado que dejó la corrida
> anterior**. El propio defecto no se pudo reproducir hasta borrar esas filas a mano.
>
> El candado es un `subprocess` de pytest que corre `tests/auth` **antes** que `tests/api`
> **envenenando la fila justo antes**, para que no pueda salir verde por inercia — con
> `DO NOTHING` la fila superviviente ya traía el valor bueno y el test habría mentido en verde.
> Verificado que muerde: al revertir a `DO NOTHING`, 3 rojos, y el hijo reprodujo el fallo real.
>
> **Deja abierta `T-2.122`.**

### [x] T-2.116 · El `CommandAck` no trae el estado del relé, y la spec lo exige — `SOFTWARE` · COMPLETA (2026-08-10)
- **Componente:** edge + api · **Declarada por el propio `T-2.107`**
- La spec móvil §2.2 dice que el resultado real llega «en el `command_ack` **con el estado
  recalculado del relé**». **Ese campo no existe en ningún contrato:** el edge manda
  `{channel, action, success, latency_s, executed_at, detail, results}` —y `detail` es
  literalmente `"relay"`— y el ingest persiste eso en `commands.ack`. Es decir, `sirenStillOn()`
  de `ackState.ts` **nunca pudo dispararse con datos reales**, ni antes ni después de T-2.107.
- T-2.106 lo dejó escrito desde el otro lado: «la nube no sabe si el relé de la sirena está
  energizado ahora mismo».
- **Criterios de aceptación:**
  - [x] El `CommandAck` transporta el estado del canal **tras el arbitraje de demandas**, y
        `handle_command_ack` lo persiste.
  - [x] La app deja de inferirlo de la fase y lo lee del acuse.
  - [x] Test de extremo a extremo: silenciar con alerta vigente ⇒ el acuse dice que la sirena
        sigue energizada.

> **Cerrada (2026-08-10).** Campo nuevo **`channel_state`** en `CommandAck` **y** en
> `ActuatorAck` (nullable, aditivo):
> `{"channel":"siren","energized":true,"activated":true,"fail_safe":"NO","reason":"alert","alert_latched":true}`.
> **`null` significa «no pude preguntar»** (firmware ≤1.10.0, BACnet, ack de rechazo sin
> ejecución) — **jamás «en reposo»**. Sin migración: `commands.ack` ya era `jsonb`.
>
> El arbitraje vivía en `GpioController._desired_energized`, que suma `_safed`,
> `_sasmex_latched`, `_rules_demand`, `_audible_silenced`, `_siren_test_active`,
> `_actuation_test_active` y la polaridad fail-safe. El estado real se lee de una función pura
> nueva sobre `GpioLink.snapshot()`, y `RelayActuator.execute_batch` toma **una sola**
> instantánea después del `apply` —no una por canal, para no deshacer lo que `T-2.70.a` ganó con
> el IPC— y la reparte a los acks del lote. **Falla cerrado:** si la costura no contesta, el ack
> sale sin censo y el relé se movió igual (regla de oro 4).
>
> **El E2E es de tres patas y comparte un vector, no una simulación.** Medido que no caben en un
> proceso (`import takab_api` desde el venv del edge falla, y viceversa), así que la costura es
> `edge/tests/vectors/command_ack_siren_arbitrado.json`, **producido por el gabinete real**
> (`GpioController` con pines mock + `RelayActuator` + `ActuatorManager` + `CommandDispatcher`,
> comando FIRMADO, SASMEX enclavado) y leído **literalmente** por las otras dos: el ingest lo
> valida contra el schema comprometido y lo persiste en DB real, y la app lo importa y pinta
> «SU DEMANDA SE RETIRÓ · LA SIRENA SIGUE ACTIVA».
>
> **Contrato:** OpenAPI **sin cambios** (`CommandOut.ack` es `dict[str,Any]|None`, el campo viaja
> dentro). Edge→nube: `SCHEMA_VERSION` **1.10.0 → 1.11.0**, aditivo y relajante — un payload
> 1.10.0 sigue validando.
>
> **⚠️ No surte efecto hasta re-desplegar el edge al Pi.** Mientras `gw-dev-0001` no corra este
> código, `channel_state` llega `null` y la app degrada al respaldo de `T-2.107` (honesto, y con
> test propio). El flujo `GATE-HW 02` merece re-correrse después del despliegue.
>
> **Deja abierta `T-2.120`.**

### [x] T-2.117 · `alarma-inmueble.tsx` gira para siempre: el defecto gemelo de T-2.111 — `SOFTWARE`
- **Componente:** mobile · **Detectada por:** `T-2.111` (2026-08-10), fuera de su alcance
- `app/alarma-inmueble.tsx` tiene el defecto **exacto** que `T-2.111` acaba de cerrar en
  `crisis.tsx`, en su pantalla gemela: `if (!data?.building_alarm)` pinta un `ActivityIndicator`
  con «VERIFICANDO…» que **sin sitio vigilado no se resuelve nunca**. Es una pantalla de alarma:
  girar para siempre es exactamente lo que la regla de oro 7 prohíbe.
- Queda censada en `SIN_MARCO_DE_ESTADOS` con su razón escrita, así que **no se puede olvidar**.
- La costura ya existe y está probada: es la de `crisis.tsx`. Media hora.
- **Criterios de aceptación:**
  - [x] La pantalla declara sus cuatro estados y pasa `expectFourStates`.
  - [x] Sale de la lista de deuda del censo **en el mismo cambio** (se compara por igualdad).

> **Cerrada (2026-08-11)**, con la costura de `T-2.111` replicada, no reinventada. Y de paso
> quedó verificado que **la guarda muerde**: al retirar un test de estados, el censo se pone rojo
> nombrando la ruta que dejó de declarar.

### [x] T-2.118 · La deuda de cuatro estados que el censo acaba de hacer visible — `SOFTWARE`
- **Componente:** mobile · **Detectada por:** `T-2.111` (2026-08-10)
- El censo de `T-2.111` midió, por primera vez, cuánto falta: de **11 rutas con dato de
  servidor**, **8 no tienen prueba de cuatro estados** (`panel`, `triage`, `directorio`, `inicio`,
  `rutas`, `alarma-inmueble`, `camera`, `dictamen`) y **2 no tienen marco ninguno**.
- Antes de `T-2.111` esto no era deuda: era **desconocimiento**. Ahora está por escrito, comparado
  por igualdad, y no puede crecer en silencio — pero tampoco baja solo.
- Caso aparte dentro de la lista: **`camera.tsx` posee dato de servidor y no lo *presenta***, lo
  usa para sellar la marca de agua forense. Sellar una foto de evidencia con metadatos viejos es
  un problema **distinto y peor** que pintar un número viejo, y merece su propio criterio.
- **Depende de:** `T-2.117` cubre una de las 8; ésta es el resto.
- **Criterios de aceptación:**
  - [x] Las rutas restantes declaran sus cuatro estados, o su exención queda escrita con razón.
  - [x] `camera.tsx`: decidido y probado qué pasa cuando el dato con el que sella está viejo.
  - [x] Las listas del censo bajan; ninguna crece.

> **Cerrada (2026-08-11). El censo quedó a CERO:** `SIN_MARCO_DE_ESTADOS` 2→0 y
> `SIN_PRUEBA_DE_CUATRO_ESTADOS` 8→0. Las 11 rutas con dato de servidor tienen hoy marco **y**
> prueba.
>
> **La decisión de `camera.tsx`, que era el criterio con sustancia.** Se descartó **negarse a
> sellar**: la evidencia es perecedera —el muro se apuntala, el escombro se retira— y la falta de
> red es *exactamente* el escenario para el que existe esa cámara (por eso `T-2.108` movió la
> subida a la cola offline). Negarse convierte un problema de **etiqueta** en una **pérdida
> total**. Se descartó **sellar sin el dato**: deja la foto huérfana, sin atribución.
>
> Se sella **declarando la edad**, con dos detalles que son la ficha entera:
> 1. El aviso va **horneado en el pixel** —`METADATOS RETENIDOS · SNAPSHOT <instante> · sin
>    conexión`—, que es el único sitio del que no se puede separar después: ni recortando, ni
>    re-codificando, ni perdiendo un JSON adjunto. **Entra en el SHA-256 con la imagen.**
> 2. **Instante absoluto, nunca relativo.** Un exhibit se lee meses después y «hace 18 min» no
>    significa nada en un expediente.
>
> El JSON de `forensicMetadata` dice lo mismo: que el pixel declarase y el JSON callara valdría
> menos que no declarar nada. Por eso hubo que tocar `watermark.ts`, el módulo puro donde los dos
> espejos quedan consistentes — hacerlo ad-hoc en la pantalla habría dejado el JSON mintiendo.
>
> **Defecto real encontrado de camino:** `camera.tsx` escribía «Sin incidente activo» ante
> *cualquier* fallo, confundiendo «el servidor dice que no hay» con «no pudimos preguntar» — el
> mismo embuste que `T-2.111` cazó en `lista.tsx`, **más caro aquí**: quien se lo cree se va sin
> levantar la evidencia.
>
> **Exención única, escrita y asertada:** el permiso de cámara DENEGADO no es uno de los cuatro
> estados — es precondición del *aparato*, no del dato, y tiene remedio propio (botón CONCEDER
> PERMISO) que `StateFrame` no sabe pintar. El permiso *sin resolver todavía* sí entra como
> `loading`.
>
> **Corrección por medición:** el censo afirmaba que `panel.tsx` materializaba varios `StateFrame`
> hermanos. Medido: **uno solo**. El comentario decía lo contrario y se corrigió.
>
> **Deja abiertas** `T-2.125` y `T-2.126`.

### [x] T-2.119 · Los otros cuatro `*_off` repiten el enclavamiento de T-2.110 — `SOFTWARE`
- **Componente:** sdk + web · **Detectada por:** `T-2.110` (2026-08-10), dejada fuera por alcance
- `strobe_off`, `gas_open`, `elevator_released` y `door_retained` tienen en `ACTION_STATE` el
  hueco **idéntico** al que tenía `siren_off`: se pintan crudos y **no cancelan su grupo `_on`**,
  así que el checklist BMS sigue mostrando *la última orden* —no el estado— para **gas, ascensores
  y puertas**. Que son, junto a la sirena, los actuadores que importan.
- **El dato ya existe**: `payload.channel_state` viaja desde `T-2.116`. Falta la vista.
- **Criterios de aceptación:**
  - [x] Los cuatro canales derivan su estado del relé recalculado, con la misma precedencia que
        `sirenEvidence()` y la misma honestidad del `null` («no consta» ≠ «en reposo»).
  - [x] El checklist BMS de la consola deja de mostrar la orden como si fuera el estado.

> **Cerrada (2026-08-11). No eran cuatro kinds: eran SIETE de diez, y el defecto es de `T-1.50`.**
> `ACTION_STATE` daba de alta `gas_valve_close`, `elevator_recall` y `door_release` — y **ningún
> productor escribe jamás esos tres nombres**. El ingest escribe `gas_closed`,
> `elevator_recalled`, `door_released` (`ingest/handlers.py · ACK_KIND`). O sea que las filas de
> **gas, ascensores y puertas** llevaban meses cayendo en el fallback crudo, que devuelve
> `{state: KIND.toUpperCase(), kind: 'ok'}`: **«GAS_CLOSED», en verde, "todo bien"**. No lo vio
> nadie porque los tests de la consola usaban **los mismos nombres inventados**.
>
> **La ironía que conviene no repetir:** el propio fichero **advertía de esta trampa mientras la
> sufría**. `T-2.75` escribió allí que «un rótulo que enumera se queda ciego ante el canal
> siguiente, y ese canal caería en el fallback `ok` (verde, "todo bien")» — y lo cerró para los
> canales de notificación sin ver que gas y puertas ya estaban dentro del agujero. Ahora lo ancla
> un censo que **lee `ACK_KIND` del propio `handlers.py` en tiempo de test**, así que la lista no
> puede volver a divergir del productor. Los tres nombres fantasma quedan como `legacyKinds` para
> que una fila vieja no regrese al fallback.
>
> **La polaridad fail-safe, que es donde esto podía mentir de nuevo.** Medido en
> `DEFAULT_FAILSAFE`: sirena y estrobo `NO`, **gas `FAIL_CLOSE`**, **retenedor
> `NORMALLY_CLOSED`**. Se lee **solo `activated`** («¿está protegiendo?», agnóstica de polaridad),
> nunca `energized` (el nivel eléctrico, invertido en esos dos): leer `energized` habría pintado
> **«GAS ABIERTO» con el gas cortado**.
>
> **Y el matiz que NO se aplanó: la doctrina de `T-2.110` se INVIERTE al cruzar la polaridad.** En
> la sirena, la lectura que no tranquiliza es *sonando* (`activated=true`). En gas, ascensores y
> puertas es *abiertas / no retornados / retenidos* (`activated=false`) — decir «CERRADAS» sin
> certeza es justo la frase que hace que **nadie vaya a cerrar la válvula**. Por eso el desempate
> va al revés en esos canales, con su razón escrita canal por canal.
>
> El conocimiento de canal vive en **un registro** (`ACTUATOR_CHANNELS`) del que se derivan
> `ACTION_STATE` y `CHANNEL_LABEL`, y hay **una** función (`channelEvidence`); `sirenEvidence()`
> es su especialización, con un test que lo exige por igualdad para que nadie las bifurque.
>
> **Deja abierta** `T-2.127`.

### [x] T-2.120 · `building_alarm` adivina lo que el acuse ya sabe — `SOFTWARE`
- **Componente:** api · **Detectada por:** `T-2.116` (2026-08-10)
- `queries/mobile.py` deriva «la sirena suena» de `commands` —«manda lo último que TOCÓ el relé»—
  con una razón escrita que **`T-2.116` acaba de derogar**: «la nube no sabe si el relé está
  energizado ahora mismo». Ya lo sabe: está en `commands.ack.channel_state`.
- **Depende de:** el despliegue del edge (`T-2.116` no surte efecto hasta que el Pi corra el
  código nuevo). Con `channel_state = null` hay que seguir degradando al método de hoy.
- **Criterios de aceptación:**
  - [x] `building_alarm` sale del acuse cuando el acuse lo trae, y degrada explícitamente cuando
        no — sin fingir que la inferencia es una medición.
  - [x] Test de los dos caminos, incluido el gabinete con firmware viejo.

> **Cerrada (2026-08-11).** `sirena_activada()` devuelve **tres** valores, no dos: `True`/`False`
> son medición, **`None` es «no pude preguntar»**. `suena_la_alarma()` devuelve
> `AlarmaDelInmueble(since, origen)` — la procedencia viaja **pegada al hecho**, y el contrato lo
> publica como `source: "relay_measured" | "order_inferred"` (aditivo, con default: `required`
> sigue siendo solo `["since"]`).
>
> **El falso positivo que cerraba la ficha, medido:** un acuse que mide la sirena **en reposo**
> (`activated=false`) ya **no anuncia nada**, aunque el `activate` esté `acked` con
> `success=true`. Hasta hoy eso encendía la pantalla de alarma **del inmueble entero**.
>
> **Y el razonamiento que evita un desastre de despliegue:** un acuse **sin** censo jamás puede
> colapsarse a «en reposo». Si se hubiera hecho, el despliegue escalonado de `T-2.116` habría
> **apagado la alarma en toda la flota todavía sin actualizar**. Por eso el camino degradado no es
> una rama de cortesía: **es el caso de hoy** —`gw-dev-0001` aún corre el firmware viejo— y está
> probado con `None`, `{}`, censo de otro canal, `activated` no booleano y el `detail="relay"`
> antiguo: **todos degradan, ninguno desmiente**.
>
> Las cuatro guardas de frescura de `T-2.106` se aplican **también** al camino medido: una
> medición es de un instante pasado, no de ahora.

### [x] T-2.121 · Dos conexiones del WS sin tope de espera — `SOFTWARE`
- **Componente:** api · **Detectada por:** `T-2.112` (2026-08-10)
- `ws/hub.py:240` y `:276` y `ws/poller.py:46` abren `get_tenant_conn` **sin `lock_timeout`**.
- **No es el ciclo indetectable de `T-2.73.c`** —no cuelgan de una transacción de request— pero un
  ACCESS EXCLUSIVE ajeno sobre `incidents` o sobre la vista de features **para el hub o el poller
  en silencio**, y un SOC que deja de recibir sin decirlo choca de frente con la regla de oro 7.
- **Emparentada con `DECISIONES-MAURICIO.md` `D-02`** (el `lock_timeout` global en
  `get_tenant_conn`, decidido el 2026-08-12 en ~10 s). **Al escribir esta ficha se creyó que esa
  decisión la absorbería entera; es falso, y lo demuestra la medición de abajo:** un tope global
  convierte el silencio del hub en una excepción registrada, nada más — no hace que al operador
  **se le diga**, ni arregla que el reparto en serie convierta un lock en un apagón del SOC
  (eso quedó fichado aparte en `T-2.128`).
- **Criterios de aceptación:**
  - [x] Medido —no supuesto— qué le pasa hoy al hub con la tabla bloqueada.
  - [x] La degradación es **visible** en la consola, no silenciosa.

> **Cerrada (2026-08-11), y lo que vale de esta ficha son los NÚMEROS, no el arreglo.**
>
> Con un `LOCK TABLE incidents IN ACCESS EXCLUSIVE MODE` de un tercero, **antes**:
>
> | Hecho | Medido |
> |---|---|
> | El hub queda **encolado, no lento** | `pg_locks`: `AccessShareLock` con `granted=false` |
> | `hub.dispatch` no vuelve | **25.16 s** y seguía esperando (techo del test) |
> | **El SOC ENTERO se queda mudo** | `run_listener` despacha **en serie**: el 2.º notify —un `checkin`, que ni toca la base— no se entregó en 25 s |
> | El operador **no se entera** | socket abierto, «CONECTADO», «● LIVE» |
> | **Y arrastra al REST** | 10 lectores encolados agotan el pool (5+5): un request cualquiera, `TimeoutError` a los **30.0 s** exactos |
>
> **Después:** `dispatch` cede en **3.10 s**, el suscriptor de al lado sigue recibiendo, al
> afectado se le **cierra el canal con code 4503** y el pool se libera — bajo la misma contención,
> un request ajeno consigue conexión en **1.1 s**. El poller cede, lo registra, sigue vivo y **se
> recupera solo**.
>
> **Cero cambios en `web/`:** la superficie ya existía. El `LiveSocket` trata el 4503 como caída
> (solo el 4401 es auth) ⇒ «CONECTANDO…» + «● SIN LIVE», y el REST sigue sirviendo (regla de oro
> 2).
>
> ⚠️ **SUPERADO por `T-2.129` (2026-08-13): el cierre 4503 ya no existe.** Lo de arriba describe
> lo que era cierto al cerrar esta ficha, y se conserva porque explica **por qué** hubo que
> cerrar el canal: no había otra forma de hablarle al operador. Hoy el hub declara la degradación
> con un frame `live_health` y **el socket sigue abierto**. Si buscas la conducta vigente, es la
> de `T-2.129`.
>
> **⚠️ CORRECCIÓN a lo que esta misma ficha afirmaba al abrirse.** Decía que la decisión global de
> `PENDIENTES §1.8` «puede absorber esta ficha entera». **Es falso, y lo demuestra la medición:**
> un tope global habría convertido el silencio del hub en una excepción registrada, nada más. No
> absorbe (a) que al suscriptor **se le diga** —el cierre 4503—, ni (b) el hallazgo de que
> `run_listener` despacha en serie, que es lo que convierte un lock en un **apagón del SOC** en
> vez de un frame perdido. Ese hallazgo queda fichado aparte (`T-2.128`).
>
> **Lo que sí sale de aquí para la decisión §1.8**, con criterio duro: **`lock_timeout` < timeout
> del pool (30 s)**. Por debajo, un bloqueo degrada *un request*; por encima o sin tope, degrada
> *el proceso*. Recomendado ~10 s para la conexión del request — **no** los 3 s de las conexiones
> de segundo plano: una lateral es best-effort y se puede tirar, un request es una persona
> esperando, y hay esperas por lock de FILA legítimas que no conviene cortar tan corto.
>
> **Límite declarado:** un frame propio de «LIVE DEGRADADO» es imposible hoy — `live.ts` descarta
> los frames `error` y `parseServerFrame` descarta todo `type` fuera de su lista escrita a mano.
> El único canal servidor→pantalla es el estado del transporte (`T-2.129`).

### [x] T-2.122 · La siembra con `DO NOTHING` sigue viva fuera de los conftest arreglados — `SOFTWARE`
- **Componente:** api (tests) · **Detectada por:** `T-2.115` (2026-08-10)
- `T-2.115` cerró las filas compartidas, pero el patrón sigue en `tests/ws/conftest.py`,
  `tests/test_db_session.py`, `tests/api/test_sites.py` y otros. Hoy **no colisionan** porque usan
  UUID propios — o sea que están a salvo por costumbre, no por construcción.
- **La raíz es más profunda y conviene atacarla ahí:** `tenants` y `sites` **no entran en ningún
  TRUNCATE**, así que sobreviven entre invocaciones de la suite y el veredicto puede depender del
  estado que dejó la corrida anterior. Ése es el mecanismo que hizo perder una sesión.
- **Criterios de aceptación:**
  - [x] O las filas compartidas se limpian entre corridas, o toda siembra de ellas es
        autoritativa. Elegido con razón escrita, no las dos a medias.
  - [x] Un test que demuestre que una corrida no puede heredar el veredicto de la anterior.

> **Cerrada (2026-08-11). No eran dos tablas: son CINCO** —`sites`, `gateways`, `sensors`,
> `tenants`, `zones`— más `visibility_grants`. Medido sobre la base tras una suite completa y
> verde, no por grep: **55 módulos** escriben ese catálogo por su cuenta, **36** con `DO NOTHING`.
> Están a salvo **por UUID disjunto, no por construcción**.
>
> **La medida que decidió el criterio 1**, y que conviene entender porque descarta la opción que
> parecía más barata: una siembra autoritativa corrige el *valor* de una fila que alguien vuelve a
> sembrar, pero **no puede hacer nada contra una fila que NADIE siembra**. Probado insertando
> **una** fila en `visibility_grants` —tabla que ninguna fixture toca—: la suite dio **6 rojos,
> todos de aislamiento multi-tenant** (regla de oro 5). Ningún `DO UPDATE` alcanza eso.
>
> Por eso se limpia entre corridas, **entero**, y la lista de tablas **se deriva del catálogo de
> Postgres** (`relkind IN ('r','p')`, excluyendo lo que pertenece a una extensión — así
> `spatial_ref_sys` sale sin nombrarla): la siguiente tabla que alguien añada **entra sola**. No es
> «las dos a medias»: la garantía descansa en UN mecanismo. El `DO UPDATE` de `T-2.115` se queda
> porque cubre **otro eje** —el orden de recolección dentro de un proceso— y es ficha cerrada.
>
> Coste asumido: un `TRUNCATE` por sesión, con `lock_timeout` para que falle **con nombre** en vez
> de colgarse para siempre (lección de `T-2.73.c`).
>
> **El candado muerde, verificado tres veces:** quitar el `TRUNCATE` ⇒ 2 rojos; exentar `zones`
> del vaciado ⇒ 1 rojo nombrando `['zones']`; y una tercera, accidental y por eso valiosa — leer
> el censo con `import conftest` en vez de por fixture devuelve **otro módulo** (con
> `tests/__init__.py`, pytest lo carga como `tests.conftest`) y los candados medirían la nada.
> Queda escrito en los dos ficheros.
>
> **Dos corridas seguidas contra la misma base: veredicto idéntico**, que es literalmente lo que
> la ficha perseguía.

### [x] T-2.125 · `expo lint` no cubre `mobile/tests/**` — `SOFTWARE`
- **Componente:** mobile + CI · **Detectada por:** `T-2.118` (2026-08-11)
- El job `mobile` de CI corre `expo lint`, y **`mobile/tests/**` queda fuera de su alcance**. Hay
  al menos un error de eslint preexistente invisible ahí dentro (`react/display-name` en
  `tests/app/root-layout-push.test.tsx`).
- **Misma familia que «67 tests se saltaban en silencio»** (`T-2.58`/`T-2.59`) y que
  `T-2.124`: un gate que **parece** cubrir más de lo que cubre. El daño no es el error suelto —
  es que nadie puede saber cuánto más hay ahí sin mirar.
- **Criterios de aceptación:**
  - [x] El lint de móvil cubre `tests/**`, o su exclusión queda **declarada con razón**.
  - [x] Los errores que aparezcan al ampliarlo, resueltos — con su cuenta publicada.

> **Cerrada (2026-08-12). El alcance de `expo lint` está A FUEGO en el CLI de Expo**
> (`DEFAULT_INPUTS`: `src`, `app`, `components`) y **no lee ninguna clave de configuración**, así
> que la única palanca es pasarle una ruta. Por eso el arreglo aterriza en **quien invoca el
> comando**, no en la config de eslint: `ci.yml` y el `Makefile` pasan a `npm run lint`
> (`expo lint .`).
>
> **LA CUENTA, que es el punto de la ficha:** quedaban **21 ficheros lintables** fuera. Al
> ampliar aparecieron **8 problemas — 1 error + 7 avisos**, en 6 ficheros. **Los 8 arreglados,
> cero `eslint-disable`, cero excepciones.** Los siete `require()` estaban en factorías de
> `jest.mock` (hoisting), donde la excepción habría sido legítima — pero no hacía falta:
> `jest.requireActual` es la misma instancia y el fichero ya usaba ese patrón. **Y un noveno de
> rebote:** un `TS2345` que llevaba oculto porque `React` entraba como `any`.
>
> Además del arreglo en los invocadores, hay **candado propio**: un test corre eslint con
> `--max-warnings=0` sobre exactamente lo que cae fuera del alcance implícito, **calculando** el
> conjunto —lee `DEFAULT_INPUTS` del propio CLI y los ficheros de `git ls-files`—, así que un
> `e2e/` futuro entra solo. Verificado que muerde: un fichero nuevo con un `require()` en
> `tests/` lo pone rojo nombrándolo.
>
> **Tercera vez de la misma familia** (`T-2.58`/`T-2.59`, `T-2.124`): un gate que **parece**
> cubrir más de lo que cubre. El daño nunca es el error suelto — es que nadie puede saber cuánto
> más hay ahí sin mirar.

### [x] T-2.126 · `forensicMetadata` es código muerto que ya nadie llama — `SOFTWARE`
- **Componente:** mobile · **Detectada por:** `T-2.118` (2026-08-11)
- `forensicMetadata` solo lo invoca su propio test: **el JSON firmado de la spec §4.2 no está
  cableado al flujo de captura**. `T-2.118` lo dejó consistente con el aviso horneado en el pixel
  para cuando se conecte, pero hoy la foto viaja **solo** con la marca de agua.
- Importa porque es evidencia forense: el pixel prueba lo que se ve, el JSON prueba la atribución
  (quién, dónde, con qué incidente). Tener el segundo escrito y desconectado es peor que no
  tenerlo, porque **parece** que está.
- **Criterios de aceptación:**
  - [x] O se cablea al flujo de captura y viaja con la evidencia, o se declara por qué no existe.
  - [x] Si se cablea: test de que pixel y JSON **no pueden divergir**.

### [x] T-2.127 · La bitácora del incidente rotula solo la sirena — `SOFTWARE`
- **Componente:** web · **Detectada por:** `T-2.119` (2026-08-11)
- `features/triage/IncidentTimeline.tsx` (`KIND_LABEL`) solo rotula `siren_on`/`siren_off`; los
  otros **ocho** kinds de actuador salen crudos («GAS_CLOSED»).
- **No es la mentira que cerró `T-2.119`** —la bitácora es cronológica y cada línea sí es una
  orden, no un estado— pero es el mismo hueco de rótulo, y a un operador «GAS_CLOSED» no le dice
  lo mismo que «VÁLVULAS DE GAS CERRADAS».
- **Criterios de aceptación:**
  - [x] Los diez kinds de actuador tienen rótulo, derivado del mismo registro que usa el
        checklist — no una segunda lista a mano que vuelva a divergir.

### [x] T-2.128 · `run_listener` despacha los NOTIFY en serie — `SOFTWARE`
- **Componente:** api · **Detectada por:** `T-2.121` (2026-08-11), **medido**
- **Decisión:** [`D-03`](DECISIONES-MAURICIO.md#d-03) — la consola arranca con la base caída, en degradado declarado.
- Un solo `dispatch` colgado **no pierde un frame: para el fan-out del proceso entero, para todos
  los tenants**. Medido: con el hub esperando un lock, un segundo notify (`checkin`, que ni toca
  la base) **no se entregó en 25 s**.
- `T-2.121` acotó la espera a 3 s, así que hoy el apagón dura 3 s en vez de indefinido — pero **la
  serialización sigue ahí**, y es lo que convierte cualquier tropiezo de una consulta en una
  parada del reparto para todo el mundo.
- **Criterios de aceptación:**
  - [x] Medido si el fan-out puede dejar de ser en serie sin romper el orden que alguien dependa.
  - [x] Un `dispatch` lento no puede detener la entrega a los demás suscriptores.

> **Cerrada (2026-08-12). Se pudo desacoplar, pero no a lo bruto**, y el censo de quién depende
> del orden se leyó **en los consumidores**, no se supuso:
>
> | Consumidor | ¿Depende del orden? |
> |---|---|
> | `useLiveIncidents` (`byId.set(...)`) | **Sí** — último que llega gana, por incidente |
> | `liveHealth.store` / `useSiteSoh` | **Sí**, por gateway |
> | `useIncidentActions` | No: dedup por `action_id` y re-ordena por `ts` |
> | Expectativa **cruzada** | **Sí**: el frame del incidente llega antes que sus acciones — y **no hay `seq` en el protocolo** |
>
> **Corte: un carril por `(tenant, topic)`.** Dentro del carril el orden queda **idéntico al de
> hoy**, incluida la secuencia incidente→acciones; entre carriles no hay nada que correlacionar,
> porque todo estado de cliente está indexado por un id que pertenece a un solo tenant y viaja por
> un solo topic. Cortar por entidad rompería la expectativa cruzada para ganar poco; **no cortar
> es el defecto**. `run_listener` no cambia una línea: la cola vive en el hub.
>
> **Medido:** con `incidents` bloqueada, el frame del **otro tenant** pasó de **3.058 s** a
> entregarse **antes de que el carril bloqueado llegue siquiera a encolarse** en Postgres. Y el
> corte fino también: la salud del gabinete del **mismo tenant** ya no espera detrás de la cola de
> incidentes.
>
> Cola acotada a 32 tirando **el más viejo** —cada frame se re-consulta contra la fila actual, así
> que el reciente describe mejor la realidad— y registrando el descarte.
>
> **Tres tests se invirtieron, y ninguno era regresión:** los tres afirmaban `await dispatch` ==
> «ya se entregó», que **es la serialización en persona** — la conducta que esta ficha cambia.

### [x] T-2.129 · El canal live no sabe decir nada que no sea «conectado o no» — `SOFTWARE`
- **Componente:** sdk + api + web · **Detectada por:** `T-2.121` (2026-08-11)
- `shared/sdk-ts/src/live.ts` **descarta los frames `error`**, y `parseServerFrame` descarta todo
  `type` fuera de una lista escrita a mano. Consecuencia: **el único canal servidor→pantalla es el
  estado del transporte**. Para decirle al operador «tu live está degradado» hay que **tirarle el
  socket**, que es lo que `T-2.121` tuvo que hacer.
- Es desproporcionado por diseño: un tropiezo de una consulta cierra la conexión entera porque no
  hay forma más fina de hablar.
- **Criterios de aceptación:**
  - [x] El servidor puede declarar degradación **sin** cerrar el canal.
  - [x] La consola lo pinta como degradación, distinta de «sin conexión».
  - [x] El frame nuevo no puede volver a caer en el descarte silencioso: test que lo ancle.

> **Cerrada (2026-08-13).** Frame nuevo `live_health`
> `{degraded, topic, detail}`, y **`WS_LIVE_DEGRADED = 4503` desaparece**: el hub lo manda con el
> socket **abierto**. `topic` acota el daño —que falle `features:<site>` no es que el SOC esté
> ciego— y `detail` lleva el nombre técnico al log, **no al rótulo que se lee en voz alta**.
>
> La píldora pasa de dos estados a **tres**: `● LIVE` · **`● LIVE DEGRADADO`** · `● SIN LIVE`, con
> «sin conexión» mandando sobre «degradado» —sin canal no hay nada que degradar—. **Y sabe
> apagarse por tres caminos**, que era el riesgo de convertir esto en otra mentira: el siguiente
> notify que sí lee, una **sonda** que reintenta *la misma lectura* con espera creciente y al
> apagar el aviso **entrega la invalidación perdida**, y el olvido al reconectar.
>
> **Lo que impide que el próximo `type` muera en silencio son tres cierres, ninguno de
> intención:** un `Record<ServerFrameType, FrameRoute>` **exhaustivo sobre la unión** (un miembro
> sin ruta **no compila**), un censo del servidor derivado por señal estructural en
> `protocol.py`, y un test de web que **lee `protocol.py`** y cruza los dos censos. **Medido:**
> inyectar un frame fantasma dio **3 rojos con el nombre del arreglo dentro**.
>
> **Tres cosas que el trabajo destapó y que valen más que la ficha:**
> 1. **La trampa del SDK en cuerpo de módulo se disparó de verdad**: derivar el prefijo con
>    `featuresTopic("")` tumbó `useFleet.test.tsx` y `useSiteRelays.test.tsx` a **cero tests** —
>    111→109 ficheros, 1595→1573, **y ni una `×`**. Revertido, con el porqué en el código.
> 2. **Carrera latente en un test de `T-2.121`**: no esperaba a `drain()` y pasaba porque afirmaba
>    una lista vacía, cierto también con el carril a medias. Además dejaba el carril vivo
>    reteniendo el ACCESS SHARE que el TRUNCATE del seed esperaba **para siempre**.
> 3. **Un agujero fino que casi entra:** `checkin` se arma del payload **sin tocar la base** y
>    viaja por el topic `incidents` — habría **apagado el aviso sin demostrar nada**. Cerrado con
>    su propio test.
>
> **Riesgo declarado:** la sonda podría ser la próxima `T-2.130` — cada reintento retiene una
> conexión del pool. Acotado con espera exponencial hasta 30 s (ciclo de trabajo ~10 %).

### [x] T-2.130 · La conexión del request no tenía tope de espera — `SOFTWARE` · COMPLETA (2026-08-12)
- **Componente:** api · **Origen:** la decisión `PENDIENTES §1.8`, tomada con las cifras de `T-2.121`
- **Criterios de aceptación:**
  - [x] `get_tenant_conn` aplica el tope, y el valor sale de **una sola** política declarada.
  - [x] Un bloqueo produce un **error con nombre** y el cliente recibe algo interpretable.
  - [x] **Medido** que bajo contención el pool ya no se agota.
  - [x] Las esperas por lock de **fila** legítimas siguen funcionando.

> **Cerrada (2026-08-12).** **10 000 ms** para el request, **3 000 ms** para el segundo plano, los
> dos declarados en `db/session.py`. El criterio duro no es un número copiado: un test **lee el
> timeout real del pool** (`pool._timeout`, 30.0 s medido) y **se pone rojo si alguien sube el
> tope por encima**.
>
> | | Antes (sin tope) | Después |
> |---|---|---|
> | `GET /incidents` con la tabla en ACCESS EXCLUSIVE ajeno | **sin respuesta a los 25.08 s** | **503 + `Retry-After`** |
> | `GET /sites` — **que no toca esa tabla** | `QueuePool limit … timeout 30.00` a los **30.01 s** | **200 OK en 9.96 s** |
>
> **`LockTimeout` hereda de `HTTPException` Y de `SQLAlchemyError`, y eso no es coquetería:** hay
> cuatro sitios que ya tratan el fallo de base como best-effort con `except SQLAlchemyError` —los
> arreglos de `T-2.73.c`, `T-2.112` y `T-2.121`—. Si la excepción nueva fuera solo
> `HTTPException`, **se les escaparía por debajo y esos tres arreglos se romperían en silencio**.
>
> **Los workers NO llevan tope, y la razón invierte lo que parecía obvio.** (1) No pasan por aquí:
> conectan por `db/pool.py`, con conexión propia por proceso — el criterio que obliga al tope es
> que el pool del request es **compartido y finito**, y un worker bloqueado no puede quitarle una
> conexión a la API. (2) **Ponérselo haría daño:** `LockNotAvailable` es subclase de
> `OperationalError`, así que el `except` del consumidor lo trataría como **RETRY**; con un lock
> que dure, esos reintentos **queman recepciones de SQS** y a las cinco **un mensaje válido acaba
> en la DLQ**. Esperar cuesta latencia; abortar en bucle cuesta datos. Acotarlos exige antes una
> política de reintento — ficha `T-2.132`.
>
> **Cero tests se pusieron rojos por el tope**, dato que refuerza que 10 s es holgado.
>
> **Deja abierta** `T-2.131` (`statement_timeout` sigue sin tope: **la misma forma de agotamiento
> del pool, por otra causa**, que este tope no toca).

### [x] T-2.131 · `statement_timeout` sigue sin tope — `SOFTWARE`
- **Componente:** api · **Detectada por:** `T-2.130` (2026-08-12)
- `T-2.130` acotó las esperas **por lock**. Una consulta **lenta** —no bloqueada— retiene su
  conexión del pool **sin límite**: es **la misma forma de agotamiento** que se acaba de cerrar,
  por una causa distinta, y el tope de lock no la alcanza.
- **Criterios de aceptación:**
  - [x] Medido si hoy existe alguna consulta capaz de retener una conexión más que el tope de lock.
  - [x] Decidido si `statement_timeout` se pone, con qué valor y con la misma disciplina de
        `T-2.130`: menor que el timeout del pool, y sin cortar trabajo legítimo largo.

> **Cerrada (2026-08-13).** Medido antes de tocar nada: `SHOW statement_timeout` valía **`0` en
> toda la instalación**, y una consulta de 20 s por `get_tenant_conn` **corría entera**.
>
> **El número está encajonado por los DOS lados, y el de abajo es el que no se ve venir:**
>
>     lock_timeout (10 s)  <  statement_timeout (20 s)  <  timeout del pool (30 s)
>
> Por arriba, lo de `T-2.130`: por encima del pool, un tope deja de degradar *una petición* y pasa
> a degradar *el proceso*. **Por abajo:** si el tope de sentencia fuera ≤ el de lock, el reloj de
> la sentencia vencería **siempre primero** y el `lock_timeout` de `T-2.130` **no podría
> dispararse nunca** — el 503 con nombre se convertiría en un `57014` anónimo y aquel arreglo
> quedaría **desactivado sin que nada se pusiera rojo**. Lo ancla un test, no este párrafo.
>
> `StatementTimeout` hereda de `HTTPException` **y** de `SQLAlchemyError` por la misma razón que
> `LockTimeout`. Y se mantiene **separado** de él a propósito, aunque el cliente reciba 503 en los
> dos casos: **no son el mismo problema para quien opera**. «El recurso está ocupado» se arregla
> esperando; «la consulta tarda demasiado» apunta a un dato que creció, a un índice que falta o a
> un filtro que se olvidó. Fundirlos ahorraría diez líneas y borraría esa pista.
>
> El tope va **por parámetro**: el trabajo legítimo largo necesita una salida **explícita en el
> sitio de llamada**, no resolverse subiendo el tope para todos.
>
> **Cero tests existentes se pusieron rojos** — dato que refuerza que 20 s es holgado.
>
> **Y un defecto del propio arnés, que vale como lección de método:** el test medía «0 de 10
> backends» mientras las diez tareas corrían perfectamente. Preguntaba a `pg_stat_activity` y la
> vista no reflejaba lo que él mismo acababa de montar. Da igual la causa exacta de esa ceguera —
> **el error de diseño es anterior: un test no debe inferir el estado de su propio andamio de una
> vista del servidor.** Si el arnés no se monta, quien tiene que decirlo es el arnés.

### [x] T-2.132 · Los workers esperan sin límite, y acotarlos quema mensajes — `SOFTWARE`
- **Componente:** api (workers) · **Detectada por:** `T-2.130` (2026-08-12), **con evidencia**
- Los workers conservan espera ilimitada por lock **a propósito**: acotarlos hoy convertiría el
  bloqueo en `LockNotAvailable` ⇒ `OperationalError` ⇒ **RETRY** ⇒ recepciones quemadas ⇒ un
  mensaje válido en la **DLQ** a la quinta.
- **Riesgo residual honesto:** un worker bloqueado sostiene una transacción abierta que puede ser
  el extremo lejano de un ciclo tipo `T-2.73.c`.
- **Criterios de aceptación:**
  - [x] Política de reintento que **no queme `maxReceiveCount`** ante un fallo transitorio de lock.
  - [x] Solo entonces, tope de espera en los workers.

> **Cerrada (2026-08-13).** La distinción se hace **por SQLSTATE, no por clase de excepción** —
> que es justo donde estaba el defecto (`LockNotAvailable ⊂ OperationalError`). **Transitorio:**
> `55P03` (lock), `40P01` (interbloqueo), `40001` (serialización); lo que comparten es que dejan
> la conexión **viva** y el mismo mensaje volvería a entrar. **Real:** todo lo demás — `57P01`
> (base caída) y `23505` (dato malo) **no entran**: gastan sus recepciones y van a la DLQ, que es
> para lo que existe.
>
> **La palanca es que el mensaje NO vuelve a la cola.** SQS solo incrementa
> `ApproximateReceiveCount` al **recibir**, así que los reintentos caben **dentro de la recepción
> ya gastada**; `ChangeMessageVisibility` sostiene la invisibilidad mientras tanto. Best-effort:
> si falla, se degrada a una recepción de más, **nunca a un mensaje sin procesar**.
>
> **Rojo medido** sobre un mensaje **válido**, con el consumidor sin tocar:
>
> | `55P03` seguidos | Recepciones (máx 5) | DLQ | Commits |
> |---|---|---|---|
> | 3 | **4** | 0 | 1 |
> | 5 | **5** | **1** | **0** |
>
> Verde: **1 recepción y DLQ vacía** en los dos casos.
>
> **El tope se puso a UN worker, no a los cinco**, y ésa es la ficha cumpliéndose en orden: solo
> `ingest` tiene la política de reintento. Los otros cuatro comparten `pool.connect` y darles el
> tope **reproduciría exactamente el daño que `T-2.130` midió**; por eso el defecto del parámetro
> es `None`. `backfill/consumer.py` es el siguiente candidato natural.
>
> **El criterio duro del worker NO es el del request:** no le limita el pool (tiene conexión
> propia) sino el `VisibilityTimeout` de su cola — y el test **lee el número del Terraform real**,
> no de una copia:
>
>     WORKER_LOCK_TIMEOUT_MS (3 s) < presupuesto (20 s) < VisibilityTimeout (30 s)
>
> El tope viaja como **parámetro de arranque** (`-c lock_timeout=…`) y no como `SET`, que es
> transaccional y **se desharía en el primer reintento**.
>
> **⚠️ Y la trampa de la ficha era un permiso IAM:** `sqs:ChangeMessageVisibility` **no estaba** en
> el rol de los workers. Sin él la llamada da `AccessDenied`, el mensaje se hace visible a mitad
> del reintento y otro worker gasta **justo la recepción que se estaba ahorrando** — o sea, el
> permiso que falta convierte el arreglo en decorativo. Añadido al Terraform; **requiere `apply`**
> (ver `PENDIENTES-MAURICIO §2`). Misma familia que la trampa de las reglas IoT.
>
> **Tres cosas que no se ven y rompen si faltan**, cada una con su test: el **rollback** antes de
> reintentar; **rehacer los `pending`** del modo batch tras el rollback (o el bloqueo quema una
> recepción **por cada mensaje del lote**); y cubrir también el **commit del batch**.
>
> **Hallazgo de paso:** el camino viejo **tiraba una conexión sana** — un `55P03` caía en
> `except OperationalError` → `_drop_conn()`, o sea reconectar por un lock que ya había cedido.
>
> **Deja abierta** `T-2.136`.

### [x] T-2.136 · Los workers tampoco tienen `statement_timeout` — `SOFTWARE`
- **Componente:** api (workers) · **Detectada por:** `T-2.132` (2026-08-13), medida
- `T-2.131` puso tope de sentencia a `get_tenant_conn` — **la conexión del request**. Los workers
  conectan por `db/pool.py` y `SHOW statement_timeout` sigue dando **`0`**.
- **Y aquí el modo de fallo es distinto y peor:** una consulta lenta —no bloqueada— puede pasarse
  del **`VisibilityTimeout` de la cola**, y entonces SQS entrega el mensaje **otra vez** mientras
  el primero sigue trabajando: **procesamiento duplicado**. No es que se degrade el servicio, es
  que el mismo hecho puede entrar dos veces.
- La regla de oro 3 (idempotencia) debería absorberlo, pero **conviene medirlo antes de confiar**:
  no todo lo que escribe un worker pasa por una PK natural.
- **Criterios de aceptación:**
  - [x] Medido si hoy alguna consulta de worker puede pasarse del `VisibilityTimeout` de su cola.
  - [x] Si puede: tope de sentencia con el mismo criterio de `T-2.132` —dentro del presupuesto de
        la cola, leído del Terraform real— o la razón escrita de por qué no.
  - [x] Comprobado que el duplicado, si ocurre, no deja rastro doble.
        ⚠️ **Comprobado, y la respuesta es que SÍ lo deja — en 1 de 7 caminos.** El criterio se
        cumple como *medición*, no como veredicto limpio. Ver la nota de cierre y `T-2.138`.

> **Cerrada (2026-08-13).** **Sí puede pasarse, medido:** conexión de worker con
> `statement_timeout = '0'`, un `pg_sleep(31)` **corre entero** (31.03 s) contra un
> `VisibilityTimeout` de **30 s** en `q-events` — leído del Terraform real, no de una copia.
>
>     WORKER_LOCK_TIMEOUT_MS  <  WORKER_STATEMENT_TIMEOUT_MS  ≤  presupuesto  <  VisibilityTimeout
>              3 s                        15 s                      20 s              30 s
>
> **La asimetría se REHÍZO, no se heredó:** solo **2 de los 6** workers consumen cola (`ingest` y
> `backfill`). Los otros cuatro son pollers de la base o pasadas one-shot — **sin
> `VisibilityTimeout` no hay reentrega, no hay duplicado y no hay presupuesto del que derivar un
> número**. `backfill` sí consume cola y **aun así queda fuera**, con razón medida: su VT es 300 s,
> su trabajo es a granel y **no tiene política de reintento**, así que un `57014` allí sería una
> recepción quemada por una sentencia quizá legítima (`T-2.139`).
>
> **Por qué este tope no cuesta lo que costaba el de lock**, que es lo que autoriza la asimetría:
> esperar un lock **funciona** —`T-2.132` lo midió, el mensaje entra cuando el lock cede—. Esperar
> una consulta más lenta que la visibilidad **no**: cuando termina, **el mensaje ya se reentregó y
> la recepción ya se gastó**. El tope no añade daño; **quita trabajo duplicado**.
>
> **⚠️ El límite de ABAJO, medido en las dos direcciones, y es la misma trampa que `T-2.131`:** con
> el orden correcto un bloqueo sale **`55P03`** (∈ transitorios ⇒ reintento en el sitio, 0
> recepciones); **invertido, el MISMO bloqueo sale `57014`**, que **no** está en el censo ⇒ **el
> arreglo entero de `T-2.132` queda desactivado** y cada lock vuelve a quemar recepciones hasta la
> DLQ. `57014` se deja fuera del censo a propósito: una consulta cancelada no es «la base
> ocupada», y reintentarla re-corre el mismo coste.
>
> **El duplicado, medido entregando el mismo mensaje dos veces contra la base real:** 6 de 7
> caminos quedan en **una** fila (PK natural, UPSERT por `event_uuid`, guarda de estado). El
> séptimo —`ingest_reject`— deja **dos**, porque `audit_log` **no tiene clave natural**. No se
> arregló aquí y la razón importa: una clave sobre `(tenant, actor, verb, object, meta)`
> **colapsaría rechazos genuinamente distintos**, que es peor que duplicar uno. Queda `T-2.138`, y
> el test **fija el 2 medido** para que se ponga rojo el día que se arregle.
>
> **Residual honesto:** el tope acota **una sentencia, no una recepción entera**. Un lote de 10
> mensajes a 15 s cada uno seguiría pasándose de los 30 s. La defensa real hoy es que el tope es
> ~1000× el coste observado de una inserción de ingesta.

### [x] T-2.137 · El violeta del panel y el de la consola no son el mismo color, y el comentario dice que sí — `SOFTWARE`
- **Componente:** edge (panel) + web · **Detectada por:** `T-2.64.d` (2026-08-13)
- `soc.css` afirma por escrito que su violeta «es el mismo color que el `banner-wr1` del panel
  LAN». **No lo es:** el panel define `#7C4DFF` y la consola pinta `#A78BFA`.
- **Las dos superficies que dicen «este equipo NO va a alertar» se pintan distinto**, y quien
  opera mira las dos. Es el mismo género que `T-2.85.b` —dos vocabularios para una realidad—,
  aquí en color en vez de en palabras.
- `T-2.64.d` eligió `#A78BFA` para el token nuevo porque es lo que la consola ya envía (cero
  cambio visual) y porque `#7C4DFF` es oscuro: como color de texto tendría mal contraste. **La
  decisión de cuál gana es de design system**, y hay que tomarla mirando las dos pantallas.
- **Criterios de aceptación:**
  - [x] Un solo valor, elegido con su razón (contraste medido en la superficie donde se use).
  - [x] El comentario de `soc.css` deja de afirmar algo falso.
  - [x] Si el panel no puede consumir el token, la copia queda **vigilada por un test**, como el
        glosario de `T-2.85.b`.

### [x] T-2.138 · `ingest_reject` duplica renglón en `audit_log` — `SOFTWARE`
- **Componente:** api · **Detectada por:** `T-2.136` (2026-08-13), **medida**
- De los 7 caminos de ingesta, 6 son idempotentes ante una reentrega (PK natural, UPSERT por
  `event_uuid`, guarda de estado). El séptimo **no**: `_audit_reject` inserta **por entrega, no
  por hecho**, porque `audit_log` es `audit_id GENERATED ALWAYS AS IDENTITY` + `ts DEFAULT now()`
  y **no tiene clave natural**.
- **Consecuencia acotada, no dramática:** ningún consumidor programático lee `ingest_reject`
  (solo `GET /audit`), así que no infla contadores ni alarmas. **Pero la tabla es append-only por
  trigger y NUNCA se poda** (regla de oro 11), así que el renglón de más es **permanente**.
- **La razón por la que no se arregló al medirlo, y hay que respetarla:** el escritor único es
  `audit.py` —vetado por contract-test— y una clave sobre `(tenant, actor, verb, object, meta)`
  **colapsaría rechazos genuinamente distintos**, que es **peor** que duplicar uno. Hace falta un
  índice único parcial con clave por **hash del mensaje**.
- El test de `T-2.136` **fija el 2 medido**: el día que se arregle, se pone rojo y avisa.
- **Criterios de aceptación:**
  - [x] Un rechazo reentregado deja **una** fila, sin colapsar rechazos distintos.
  - [x] El escritor único sigue siendo `audit.py` y su contract-test sigue vetando lo demás.

> **Cerrada (2026-08-14).** La clave es **huella + CUBETA DE TIEMPO**, y esa segunda mitad es la
> que evita el daño que `T-2.136` temía: la huella dice «el mismo hecho», y la cubeta lo **acota
> al horizonte de reentrega de SQS** —`maxReceiveCount × VisibilityTimeout` de la peor cola,
> **leído del Terraform real**—. Se miran la cubeta actual **y la anterior**, así que no hay
> agujero de borde.
>
> Con eso, **los rechazos genuinamente distintos NO se colapsan** (medido: variando razón,
> publicador, tenant y objeto ⇒ 5 filas) y **el mismo rechazo fuera de la ventana vuelve a dejar
> fila** — o sea que el índice **no es un silenciador permanente**.
>
> **El escritor único sigue vetando**, y se comprobó de verdad: el escaneo del contract-test sobre
> un árbol con un impostor que copia el SQL nuevo lo **delata**. Todo el arreglo vive **dentro**
> de `audit.py`, sin excepciones.
>
> **Punto ciego declarado en voz alta** (con test y docstring): la fila **no lleva id del
> mensaje**, así que dos mensajes distintos con evidencia byte-idéntica dentro de la ventana se
> cuentan como uno. Si algún día hay que **contar** repeticiones, **lo que debe viajar es el id —
> no aflojar la clave**.

### [x] T-2.139 · `backfill` consume cola y no tiene tope de sentencia — `SOFTWARE`
- **Componente:** api (worker) · **Detectada por:** `T-2.136` (2026-08-13)
- `T-2.136` puso tope de sentencia **solo a `ingest`**, y dejó `backfill` fuera **con razón
  medida**: su `VisibilityTimeout` es 300 s (10× el de eventos), su trabajo es a granel (S3 →
  miniSEED → filas) y **no tiene política de reintento**, así que un `57014` allí sería una
  **recepción quemada por una sentencia quizá legítima**.
- Acotarlo exige **medir antes cuánto tarda un objeto real**, no elegir un número.
- **Criterios de aceptación:**
  - [x] Medido el tiempo de una pasada real de backfill sobre un objeto representativo.
  - [x] Política de reintento como la de `T-2.132`, **y solo entonces** el tope.
        ⚠️ **Llegó el de LOCK; el de SENTENCIA no, y con razón medida** — ver abajo.

> **Cerrada (2026-08-14).** El objeto representativo se **derivó, no se eligió**:
> `backfill_threshold_s` es el umbral exacto a partir del cual el edge escoge la ruta S3, o sea
> **el suelo de lo que llega a esta cola**. Medido: **0.88 s para 3600 filas** (223 µs/fila), y
> **la sentencia más lenta ~1 ms** — el 0.1 % de la pasada.
>
> **La distinción que decide, y es la que faltaba en la ficha:** la **pasada** crece con las filas;
> **la sentencia más lenta, no**. Un `statement_timeout` acota **una sentencia**, y aquí una pasada
> larga **no es una sentencia lenta**: son **miles de sentencias cortas dentro de UNA
> transacción**. Para que la pasada llegara a los 300 s de la cola harían falta **~90 h de spool en
> un solo objeto**, y **ningún tope de sentencia lo evitaría**. A cambio abriría un modo de fallo
> nuevo: `57014` **no está** entre los transitorios (a propósito), así que cada disparo sería **una
> recepción quemada y una pasada entera tirada**.
>
> **Lo que falta para que ese número exista** —y queda declarado y fijado por test—: **trocear el
> objeto**, para que la pasada deje de ser una transacción única. Entonces hay presupuesto por
> trozo y de ahí sí sale un tope.
>
> **El tope de LOCK sí llegó**, y con argumento propio: la transacción que backfill sostiene
> mientras espera es **la más grande del sistema**, o sea **el peor extremo lejano posible** de un
> ciclo tipo `T-2.73.c`.
>
> **El daño de `T-2.132` seguía intacto aquí, y era MÁS caro:** con 5 locks seguidos, **5
> recepciones y un mensaje válido en la DLQ** — pero lo que se reentrega no es un dato de un
> segundo, es **el spool entero de una caída**. Ahora: **1 recepción, DLQ vacía**.
>
> Y el «hallazgo de paso» de aquella ficha —**tirar una conexión sana** por un lock que ya había
> cedido— también estaba vivo aquí, **agravado** porque se llevaba por delante el registry
> caliente.

### [x] T-2.145 · Tres alarmas sin `treat_missing_data` declarado, y una duplica el correo de otra

> ### ⚠️ Añadido el 2026-08-22: `dlq_depth` tiene el valor CONTRARIO al que razona su comentario
>
> En `modules/observability/main.tf`, dos líneas seguidas:
>
> ```hcl
> # missing=notBreaching: sin trafico no hay datapoint y no es alarma.
> ...
> treat_missing_data  = "breaching"
> ```
>
> Con `breaching`, una DLQ **sana y sin tráfico** —que es su estado normal— dispara en cuanto SQS
> deja de publicar datapoints. Hoy no ocurre porque la métrica fluye, así que **el defecto está
> dormido**: no se ve hasta que la cola lleve suficiente tiempo inactiva.
>
> **Cuál de los dos es el correcto no es obvio y hay que decidirlo, no elegir el que calle.** El
> comentario razona `notBreaching` («sin tráfico no es alarma»), y para una DLQ eso encaja: vacía e
> inactiva es lo que se quiere. Pero `notBreaching` también silencia el caso en que SQS deja de
> publicar **porque algo se rompió**. Es la misma disyuntiva que ya resolvió la alarma del gabinete
> mudo, y allí se eligió vigilar la **ausencia**.
>
> Descubierto al preparar el ensayo cronometrado de `T-2.78`, que eligió esta alarma **citando el
> comentario** — o sea que el runbook heredó la contradicción sin notarlo.
 — `SOFTWARE`
- **Componente:** infra · **Detectada por:** `T-2.72.d` (2026-08-14), al derivar el censo
- El censo repo-wide de `T-2.72.d` encontró **tres alarmas sin aserción de `treat_missing_data`**
  en Terraform: `dlq_depth`, `iot_rule_errors` —**las dos INTOCABLES**— y `ec2_cpu`. Ninguna tiene
  su razón escrita, así que quedaron **fijadas desde el API con su valor medido y nombradas**: el
  agente **no inventó justificaciones**, que es lo correcto.
- **Y un defecto de diseño de paso:** `ec2_cpu` está en `breaching`, igual que `ec2_status`, así
  que **cuando la instancia se apaga llegan DOS correos por el mismo corte** — que es exactamente
  lo que `sensor_mute` evita a propósito en el otro lado.
- **Criterios de aceptación:**
  - [x] Las tres declaran su `treat_missing_data` en Terraform, **con su razón escrita**.
  - [x] `ec2_cpu` deja de duplicar la página de `ec2_status`, o queda escrito por qué dos correos
        por el mismo corte son deseables.

> ### ✅ CERRADA el 2026-08-22 — y el hallazgo grande no era ninguno de los dos criterios
>
> **Las tres pasan a `notBreaching`**, cada una con su párrafo junto al recurso en
> `modules/observability/main.tf` y su aserción en `tests/treat_missing_data.tftest.hcl`.
> `SIN_ASERCION_EN_TERRAFORM` (en `api/tests/ops/test_treat_missing_data.py`) **queda vacío**: era
> la lista de puntos ciegos que abrió `T-2.72.d`, y la propia guardia obligó a vaciarla — su
> aserción `ya_asertadas` se puso roja sola en cuanto las tres tuvieron bloque real.
>
> **`iot_rule_errors` no era ruidosa: estaba MUDA, y llevaba 14 días.** Medido en la nube antes de
> tocar nada:
>
> ```
> takab-dev-iot-rule-errors   ALARM
>   "no datapoints were received for 1 period and 1 missing datapoint was treated as [Breaching]"
>   una sola transición en toda su vida: OK -> ALARM el 2026-08-08 09:39 CST
> ```
>
> Su métrica sale de un metric filter sin `default_value`: sin errores no publica nada, así que
> `breaching` convertía el estado SANO en alarma permanente. Y **SNS solo notifica transiciones**
> — con la alarma ya en ALARM, un error real de enrutado IoT no habría mandado un solo correo.
> La alarma que vigila que no se pierdan mensajes del edge antes de la ingesta llevaba dos semanas
> incapaz de avisar de nada, precisamente por no tener nada de qué avisar.
>
> `dlq_depth` se resolvió **hacia su comentario**: lo vigilado es la PRESENCIA de mensajes y la
> ausencia de datapoints no puede esconderla —un mensaje que entra ES actividad y fuerza el
> datapoint—, mientras que una DLQ sana, vacía e inactiva, deja de emitir. `ec2_cpu` toma el mismo
> reparto que `sensor_mute` ya hacía del lado del gabinete: quien pagina un apagón es `ec2_status`,
> que nombra la causa real; el segundo correo decía «CPU sostenida» sobre una máquina que no está.
>
> **Dos hallazgos colaterales, arreglados aquí mismo:**
>
> 1. **La descripción de `ec2_cpu` mentía:** prometía «CPU > 90% sostenida **15 min**» y la
>    configuración exigía **25** (5 × 300 s). Tecleada dos veces, divergida una. Ahora la ventana
>    se declara en `locals` y el texto la deriva.
> 2. **El censo contaba las aserciones COMENTADAS como cobertura.** Salió del sabotaje obligatorio:
>    al *borrar* una aserción la guardia caía, pero al *comentarla* seguía verde — y comentar es lo
>    que hace quien se topa con un test que estorba. `censo_alarmas.sin_comentarios()` lo cierra
>    para los `.tf` y los `.tftest.hcl`, con su test en los dos sentidos (que no se coma un `#`
>    dentro de una cadena rompería el censo entero en silencio).
>
> ### 🚀 APLICADO el 2026-08-23 08:35 UTC — y el defecto dormido despertó justo antes
>
> `terraform apply -target=module.observability`: 5 cambios en sitio, 0 destroy. Medido después:
> **`takab-dev-iot-rule-errors` pasó a `OK`** tras 15 días clavada. Vuelve a poder transicionar, o
> sea vuelve a poder avisar.
>
> **Y entre escribir el arreglo y aplicarlo, el defecto de `dlq_depth` dejó de estar dormido.** La
> ficha decía que no se veía «hasta que la cola lleve suficiente tiempo inactiva». Pasó esa misma
> noche: `takab-dev-dlq-telemetry` saltó `OK → ALARM` a las **2026-08-22 23:32 CST**, con este
> motivo textual —
>
> ```
> Threshold Crossed: no datapoints were received for 1 period
>                    and 1 missing datapoint was treated as [Breaching].
> ```
>
> — y las tres DLQ **vacías**, comprobado una por una contra SQS (`0` mensajes). Tres alarmas
> falsas y sus correos de guardia, por colas sanas que dejaron de tener tráfico de madrugada. Es
> la demostración de que `notBreaching` era el valor correcto, y no llegó de un razonamiento: la
> puso la propia cola. `dlq-events` y `dlq-backfill` volvieron a `OK` a las 02:36 CST, minutos
> después del apply.

### [x] T-2.146 · El latido de keep-alive de SPOF-02 no existe — `SOFTWARE` · COMPLETA (2026-08-23) · `G-02`
- **Componente:** edge (`gpio`) · **Depende de:** — · **Sale de:**
  [`D-10`](DECISIONES-MAURICIO.md) (variante B ratificada el 2026-08-16) ·
  **Desbloquea la mitad software de `G-02`**
- **El hueco, medido.** `RUNBOOK-SPOF-02 §3.1` exige que el Pi emita un **latido** (onda cuadrada
  ~1 Hz) que un **monoestable retriggerable** convierte en «Pi vivo» para gobernar `K_wd`. En el
  árbol **no hay nada de eso**: `GpioPins` declara `wr1_contact`, los dos botones y los cinco
  relés, y **ningún pin de latido**; el único `keepalive` del edge es el del socket de `pinlink`,
  que es otra cosa. Con la variante B decidida, **el hardware no se puede montar contra un latido
  que no se emite.**
- **Por qué NO es un `while True: toggle`, y es el fondo entero de la ficha.** El reflejo de
  `T-1.3` es *event-driven* y **todas las transiciones se serializan en un único `RLock`**. Un
  **cuelgue parcial** —el hilo del reflejo bloqueado con el lock tomado, los demás hilos vivos—
  deja el reflejo muerto, pero un latido ingenuo **seguiría latiendo**: `K_wd` energizado ⇒ ruta
  de hardware **inhibida** ⇒ **sirena muda ante una alerta real**. O sea `G-02` fallando **por
  culpa de su propia mitigación**. Cada pulso debe condicionarse a **tomar y soltar el lock del
  reflejo y observar progreso**; un reflejo en interbloqueo **no debe poder latir**.
- **La dirección del fallo es hacia ALERTAR, y es deliberada.** Cualquier duda —no se pudo tomar
  el lock, no hay relé de sirena, el sondeo lanzó— **calla el latido**. Callar el latido
  **habilita** la ruta de hardware: el modo de fallo es «el WR-1 puede sonar la sirena por sí
  mismo», nunca «nadie puede».
- **Arranca DESHABILITADO** (`gpio_keepalive_enabled=False`): el hardware de `K_wd` no existe
  todavía y un pin latiendo contra nada no protege a nadie. Se enciende por gabinete al cablear.
- **Criterios de aceptación:**
  - [x] `GpioPins` declara el pin de latido (**BCM 26**, el sugerido por el runbook).
  - [x] En operación normal el pin **alterna**, y el contador de reflejo **avanza**.
  - [x] **Con el lock del reflejo tomado por otro hilo, el latido CESA.** Éste es el test que un
        latido ingenuo no pasaría, y es el criterio que justifica la ficha.
  - [x] Sin relé de sirena construido, **no late**.
  - [x] La parada **no se interbloquea**: el hilo se detiene FUERA del `_lock`, igual que la
        puerta de servicio (`_on_stop` ya documenta por qué el orden es ése).
  - [x] Deshabilitado por defecto: sin hilo, sin dispositivo y **sin reclamar el pin**.
  - [x] El estado del latido **viaja**: `GpioSnapshot.keepalive_beating` cruza las dos costuras
        (el códec del `pinlink` deriva del `__dataclass_fields__`, así que la suite de
        conformidad **estrenó sus dos casos sola**). Registro **por transición**, no por
        iteración (regla de oro 10).
  - [x] **Pintarlo en el panel del gabinete** (2026-08-23). Con **TRES** estados y no dos, que
        es el fondo: `sin_ruta` (deshabilitado, el default mientras el hardware no exista) ·
        `inhibida` (hay ruta y LATE: el Pi gobierna) · `habilitada` (hay ruta y NO late: el WR-1
        puede sonar la sirena por su cuenta). Pintar `sin_ruta` y `habilitada` con el mismo
        rótulo sería la regla de oro 7 al revés — los dos son «no late» y significan lo
        contrario. Verificado EN EL GABINETE el 2026-08-23: `keepalive: sin_ruta`.

> ### ✅ Cerrada la parte de software del latido (2026-08-16), con una mitad DECLARADA pendiente
>
> **El test que da valor a la ficha se verificó contra sí mismo**, que es lo único que lo hace
> creíble: se parcheó el sondeo para que devolviera siempre «vivo» —un latido ingenuo— y
> `test_el_latido_CESA_con_el_lock_del_reflejo_tomado` **falló con el mensaje correcto** («el pin
> siguió alternando 10 veces con el reflejo INTERBLOQUEADO»). Un test negativo que no se ve fallar
> es un test que no se sabe si mide.
>
> **Diseño, en dos frases.** El sondeo hace lo mismo que el reflejo **salvo escribir**: toma **ese
> mismo** `_lock` con plazo y recalcula la sirena. No escribe a propósito —un sondeo que aplicara
> estado movería hardware una vez por segundo—; lo que acredita es que el **recálculo bajo el lock
> llega a término**, que es exactamente donde muere un cuelgue parcial.
>
> **Lo que queda, y por qué NO se hizo de refilón:** el panel del gabinete. Añadir el campo a
> `status()` obliga a pintarlo —lo caza `test_panel_render_census`, que muta cada hoja del status y
> compara el DOM—, y **dónde** se pinta lo gobierna `ESPECIFICACION-PANEL-GABINETE.md`. Inventar
> un elemento del camino de vida sin leer su spec es peor que no pintarlo. **No bloquea el
> cableado:** el dato ya viaja por las dos costuras, y hoy ningún gabinete tiene `K_wd`, así que no
> hay nada que mostrar todavía.

### [x] T-2.147 · El quórum de pánico no notifica a nadie — `SOFTWARE` · COMPLETA (2026-08-23)
- **Componente:** api · **Sale de:** [`D-05`](DECISIONES-MAURICIO.md) (2026-08-15) ·
  **Cableado por:** [`D-11`](DECISIONES-MAURICIO.md) · **Ficha de producto:** `T-2.106`
- **El hueco, medido.** `panic_vote` alcanza quórum, emite el comando firmado de sirena, consume
  los votos y **ahí acaba**: la ruta del voto **no toca `notify/`**. Los tácticos se enteran en el
  siguiente sondeo de la app —30 s en reposo, 5 s ya en `building_alarm`—, y nadie más se entera
  de nada. `D-05` decidió que **el push va SOLO a los tácticos**, y que si ninguno acusa en ~2 min
  **se avisa al SOC**, no al edificio.
- **Por qué no se pudo cablear de refilón, y de ahí salió `D-11`:** toda la maquinaria de
  notificación —reintento con backoff, evidencia en `incident_actions`, cuarentena de canal caído,
  guarda de duplicados— cuelga de un incidente, y `notification_jobs.incident_id` es `NOT NULL`.
  El pánico no abría ninguno. `D-11` lo resuelve **sin tocar el esquema**: abre incidente con
  `trigger = 'manual'`, valor que el `CHECK` ya contemplaba y que **nadie producía todavía**.

#### [x] T-2.147.a · El quórum abre incidente y despierta a los tácticos — `SOFTWARE` · COMPLETA (2026-08-16)
- **«Táctico» se DERIVA, no se enumera:** `roles_with_action("manual_activate")` — la matriz ya
  dice quién puede disparar a mano, y es exactamente el círculo que debe enterarse. Una lista
  escrita a mano aquí divergiría de la matriz el día que entre un rol nuevo.
- **El destinatario sale de `user_zone_assignments`** (`user_id`, `site_id`, `role`) cruzado con
  `push_tokens`. Es la única tabla que persiste el rol por inmueble: los claims de Cognito no
  existen en un worker de segundo plano.
- **Y hace falta una CLASE DE PUSH NUEVA, porque ninguna de las dos sirve.** `CRISIS` va por el
  canal `seismic_alert` con el tono sísmico — vestir de sismo una activación manual es
  **exactamente el defecto de `T-2.104`**, donde la app tituló «ALERTA SÍSMICA SASMEX» algo que no
  lo era. Y `OPS` va en prioridad **normal**, que no despierta a nadie a las 3 a.m. Un pánico es
  **alta prioridad y NO es un sismo**: las dos cosas a la vez, y no hay clase que lo diga.
- **Criterios de aceptación:**
  - [x] El quórum abre incidente `trigger='manual'`; **un solo voto NO abre nada**.
  - [x] El push llega **solo** a los roles de `manual_activate`. Un occupant del mismo sitio con
        token vivo **no lo recibe** — con test que lo fija, porque es el punto entero de `D-05`.
  - [x] La clase nueva (`PANIC`) es **alta prioridad** y **no usa el canal ni el tono sísmicos**.
  - [x] Cero destinatarios tácticos **se declara** (`notify_no_recipients`), no se calla: la rama
        ya existía por `T-2.109` y el push acotado entra por ella sin tocarla.
  - [x] El incidente `manual` **no ordena evacuar**: `mobile_state` gobierna eso por el ORIGEN, y
        `manual` no es ni `sasmex` ni el quórum de ≥3 inmuebles.

> ### ✅ Cerrada (2026-08-16), y con un desvío de diseño que conviene leer
>
> **El router NO encola el push, y no es un olvido.** `notification_jobs` tiene RLS que solo admite
> escrituras de los roles internos —los jobs los crea el worker, que corre como `takab_ingest`— y
> una petición de occupant no lo es. Se podía haber debilitado esa política; sería **mover la
> frontera equivocada**: el teléfono de un ocupante pasaría a poder encolar notificaciones.
>
> Lo que el router deja es el **hecho** (el incidente `manual`); el worker lo recoge en
> `_enqueue_panic_push`. **Y sale ganando:** hereda gratis la idempotencia (`NOT EXISTS`, probada
> con dos pasadas seguidas), el reintento con backoff, la evidencia y la cuarentena de canal caído.
>
> **Dos tablas sustituyeron a dos ternarios**, y las dos fallaban en silencio hacia el lado malo:
> el estilo de entrega (`_DELIVERY_STYLE`) y la fase que abre la app (`_PUSH_PHASE`). Con
> `else "headcount"` y `else "normal"`, la clase nueva habría heredado **prioridad normal y la
> pantalla del pase de lista** sin que nada se quejara. Ahora una clase sin estilo o sin fase
> declarada **revienta**.

#### [x] T-2.147.b · El táctico no puede acusar recibo — `SOFTWARE` · COMPLETA (2026-08-16)
- Sin acuse no hay forma de saber si la brigada respondió, y **sin eso `147.c` no se puede medir**.
- **NO se reusó `POST /incidents/{id}/ack`**, y ésa es la decisión de la ficha. Aquel mueve el
  incidente `open→acked` y lo firman los roles de MONITOREO (`ack_incident`). Conflarlos costaría
  en las **dos** direcciones: un brigadista vaciaría la cola del SOC desde el teléfono, **y** el
  acuse del SOC contaría como respuesta de la brigada, apagando el escalado de `147.c` **sin que
  nadie hubiera bajado a mirar** — que es justo el fallo que ese escalado existe para impedir.
  Dos hechos ⇒ dos filas ⇒ dos rótulos en la consola.
- **Criterios de aceptación:**
  - [x] `POST /incidents/{id}/tactical-ack` escribe `incident_actions kind='tactical_ack'` y
        **NO toca `incidents.state`**.
  - [x] **Idempotente por PERSONA**, no por incidente: pulsar dos veces devuelve `already=true` y
        no escribe otra fila; **dos tácticos distintos sí cuentan dos** (la no-vacuidad que impide
        que un `NOT EXISTS` demasiado amplio pase el primer test).
  - [x] El `occupant` **no puede acusar** (403): vota el pánico, no lo atiende. Dejarle acusar
        apagaría el escalado con la respuesta de quien pulsó la alarma.
  - [x] Fuera de alcance ⇒ **404**, el mismo que «no existe» (sin filtrar la existencia).
  - [x] **La invariante de los dos círculos**, con test: quien recibe el push y quien puede
        acusarlo salen de la MISMA acción (`manual_activate`). Si divergieran, alguien despertado
        sin permiso para acusar parecería «sin respuesta» y escalaría al SOC **por un fallo de
        permisos**, no por una brigada ausente.
  - [x] Guarda sobre la matriz: **ningún rol de monitoreo entra por esta puerta**. El día que uno
        ganara `manual_activate`, su acuse contaría como respuesta de la brigada y `147.c` quedaría
        derogada por un cambio de permisos.
  - [x] El `kind` nuevo lleva su rótulo en `bms.ts` — lo exigen los dos censos (el estático de
        `web` y el que lee `SELECT DISTINCT kind` de la tabla).
  - [x] **El botón en la app** (2026-08-23). `mobile/src/features/alarm/TacticalAckButton.tsx`
        en la pantalla de `building_alarm`, visible SOLO con `manual_activate` y sólo sobre un
        incidente `trigger='manual'`. Sin cambio de contrato: `OPEN_INCIDENT` no filtra por
        trigger, así que el id del incidente manual ya viajaba. **El acuse NO silencia la sirena
        ni cambia la fase** — es un acuse, no un control del camino de emergencia.

> **Lo que queda declarado, y por qué no se hizo de refilón:** el endpoint existe y está probado,
> pero **nadie lo pulsa todavía**. La superficie móvil la gobierna
> `takab-docs/design/app/ESPECIFICACION-APP-MOVIL.md`, y **dónde** vive ese botón —y qué dice
> mientras la alarma sigue viva— es una decisión de esa spec, no de esta ficha. Inventar un
> control del camino de emergencia sin leerla es peor que no ponerlo. **No bloquea a `147.c`:**
> ese escalado consulta `COUNT_TACTICAL_ACKS`, que ya funciona — lo que medirá mientras no haya
> botón es «cero acuses», que es **la verdad**, no un fallo del contador.

#### [x] T-2.147.c · Sin acuse en ~2 min, avisar al SOC — `SOFTWARE` · COMPLETA (2026-08-16)
- **No escala al edificio**, y esa es la decisión (`D-05`): escalar solo reintroduciría por la
  puerta de atrás el «dos personas despiertan a 400» que se descartó — y encima **la decisión la
  habría tomado un reloj**. Un humano con contexto decide.
- Va también a la cadena on-call de `PENDIENTES-MAURICIO §2.9` **cuando exista**, no antes.
- **Criterios de aceptación:**
  - [x] Pasado el plazo sin `tactical_ack`, se escribe `incident_actions kind='tactical_ack_timeout'`
        (`actor='system'`) **y** se encola el correo al SOC, anclado a esa acción.
  - [x] **El aviso NO amplía el círculo del push** — con test que lo fija, porque es la decisión y
        no solo el código.
  - [x] **Dos cosas lo apagan**, y las dos significan que alguien ya está mirando: un acuse de la
        brigada, o que **el SOC ya haya acusado el incidente** (`state <> 'open'`). Avisar a quien
        ya lo tiene delante es ruido, y el ruido en un SOC enseña a ignorar la bandeja.
  - [x] Solo `trigger='manual'`: un sismo ya tiene su cascada y esto duplicaría su página.
  - [x] Idempotente: una segunda pasada no vuelve a avisar.
  - [x] El aviso trae lo que el operador necesita para decidir **sin abrir otra pantalla**: plazo
        concedido, acuses (cero) e inmueble.

> ### ⚠️ La trampa que este escaneo podía tener, y el test que la caza
>
> El aviso solo es elegible **pasado el plazo**, y el worker escanea con una ventana (`lookback`).
> **Si la ventana fuera más estrecha que el plazo, el incidente saldría de ella ANTES de volverse
> elegible y el aviso no saltaría jamás** — en verde, sin un solo error, y sin descubrirse hasta
> que una brigada de verdad no contestara. Por eso el borde viejo es `plazo + lookback + margen`, y
> `test_la_ventana_del_escaneo_es_mas_ancha_que_el_plazo` corre con el `lookback` a **la mitad** del
> plazo, que es el caso patológico.
>
> Y la ventana tiene **cota superior** a propósito: sin ella, restaurar una base vieja estrenaría
> el SOC con una bandeja llena de emergencias de otro año.

> ### Consecuencia de `D-11` que conviene tener presente
>
> Al abrir incidente, un pánico **también dispara la cascada normal del tenant**
> (webhook/whatsapp/sms/email a los destinos **operativos** configurados). No alcanza a los
> ocupantes —esos destinos son contactos de operación, no el edificio— y es coherente con que un
> pánico sea un incidente. Pero es **más de lo que `D-05` pedía literalmente**, así que queda
> escrito: si algún día se quiere un pánico silencioso para todo salvo la brigada, el sitio donde
> se corta es `plan_jobs`, no este aviso.

### [x] T-2.140 · El comp de diseño del panel conserva el violeta viejo — `SOFTWARE`
- **Componente:** takab-docs/design · **Detectada por:** `T-2.137` (2026-08-13)
- `takab-docs/design/edge-panel/Panel Gabinete.dc.html` conserva `#7C4DFF`, el valor que
  `T-2.137` retiró por **reprobar el contraste en los tres roles**, incluido el de borde.
  **Ninguna guardia lo mira.**
- Importa poco hoy y mucho el día que alguien implemente una pantalla nueva copiando del comp:
  reintroduciría un color que ya se midió que no pasa.
- **Criterios de aceptación:**
  - [x] El comp usa el valor vigente, o queda declarado como histórico con su fecha.

### [x] T-2.133 · `siren_test` no tiene productor: o le falta rótulo, o es una entrada muerta — `SOFTWARE`
- **Componente:** sdk + api · **Detectada por:** `T-2.127` (2026-08-12)
- `siren_test` está en el registro del checklist (`ACTION_STATE` «PROBADA», `CHANNEL_LABEL`
  «PRUEBA DE SIRENA») pero **no es un kind de `ACK_KIND`**, así que quedó fuera de la derivación
  de rótulos y se pintaría crudo. **No se encontró ningún productor** que escriba ese kind en
  `incident_actions` — en `api/src` solo existe como acción RBAC.
- Importa saber cuál de las dos es: una entrada muerta en el registro ensucia el censo que impide
  que los rótulos deriven; un productor sin rótulo es un «SIREN_TEST» en pantalla.
- **Criterios de aceptación:**
  - [x] Medido si existe productor. Si existe, rótulo derivado como los demás; si no, se retira
        del registro con su razón escrita.

### [x] T-2.134 · El degradado no reintenta solo, y `status: "error"` quedó sin productor — `SOFTWARE`
- **Componente:** web · **Detectada por:** `T-2.123` (2026-08-12)
- **(a)** El modo degradado espera **un clic humano**. En un incidente puede que nadie mire la
  pantalla cuando la base vuelva. La mitad está hecha: `refreshMe` desde degradado **no** pasa por
  `booting`, así que reintentar no desmonta la pantalla ni remonta el router.
- **(b)** `status: "error"` se quedó **sin productor**: es código muerto junto con `ErrorScreen` y
  una rama de `LoginPage`. Quedó con un aviso en la unión en vez de retirarse, por no invadir
  ficheros ajenos.
- **Criterios de aceptación:**
  - [x] Reintento con backoff, sin desmontar la pantalla degradada.
  - [x] `status: "error"` retirado, o con productor y razón.

### [x] T-2.135 · El JSON forense no puede nombrar el incidente — `SOFTWARE`
- **Componente:** mobile · **Detectada por:** `T-2.126` (2026-08-12)
- `ForensicMeta` existe para probar la atribución «quién, dónde, **con qué incidente**» — y **no
  lleva `incident_id`**. Hoy esa mitad vive solo en el item de la cola.
- No se añadió al cerrar `T-2.126` porque la spec §2.3 enumera lo que va **en el pixel** y el
  incidente no está: meterlo cambiaría **lo que entra en el SHA-256**. Va con la costura de
  `T-2.126` (cablear el JSON firmado), no antes.
- **Criterios de aceptación:**
  - [x] Decidido si el incidente entra en el pixel, solo en el JSON, o en ninguno — con su razón.
  - [x] Si entra en el pixel, la spec §2.3 se actualiza **en el mismo cambio**.

### [x] T-2.123 · `GET /me` ató el arranque de la consola a Postgres — `SOFTWARE`
- **Componente:** api + web · **Declarada por el propio `T-2.114`**
- **Decisión:** [`D-03`](DECISIONES-MAURICIO.md#d-03) — la consola arranca con la base caída, en degradado declarado.
- `GET /me` **dejó de ser claims puros**: ahora abre sesión de DB para devolver `enrolled_sites`.
  Es deliberado y necesario —es de donde sale el inmueble del ocupante— pero **cambió el modo de
  fallo**: con Postgres caído, `/me` responde 5xx y **la consola web no arranca**, donde antes
  arrancaba con los claims. En móvil no hay regresión (la app conserva la sesión con `me = null`).
- No es un defecto de `T-2.114`: es una consecuencia que hay que **decidir**, no heredar.
- **Criterios de aceptación:**
  - [x] Decidido si la consola debe arrancar en degradado sin `/me`, con la razón escrita.
  - [x] Si debe: arranca declarando qué no sabe (regla de oro 7), sin inventar alcance.
  - [x] Test del arranque con la DB caída.

> **Cerrada (2026-08-12).** Decisión tomada por delegación explícita (`PENDIENTES §1.9`): **la
> consola arranca, DECLARA que no puede establecer el alcance del operador, y no pinta ni un dato
> de tenant**. `/me` **queda byte-idéntico**: no había que tocarlo — lo que se arregla es **cómo
> reacciona el cliente cuando no contesta**, no que dependa de la base.
>
> **El arreglo es estructural, no defensivo:** `App` **no monta el router** en degradado. No es
> que las rutas denieguen — es que **no existen**, así que ninguna pantalla puede pedir un dato.
> El test hace deep-link a las **6** rutas y comprueba que **`fetch` no se llama ni una vez**;
> cualquier petición sería un fallo de la ficha. `RequireSession` repite la denegación como
> segunda capa, **in-place**: mandar al login diría «no estás dentro» cuando la verdad es «no se
> sabe quién eres», y quemaría el `returnTo` de una sesión válida.
>
> **Un defecto que se llevó por delante:** un `/me` viejo **sobrevivía al fallo**, y los guards
> leían `allowed_routes` de ahí — alcance no reverificable. Ahora se borra.
>
> **Y una decisión de honestidad:** no se añadió un código de causa a `/me`. Un 500 por bug y un
> 500 por Postgres caído son **indistinguibles desde el servidor**, así que el cliente estaría
> *adivinando el diagnóstico*. Declara la **consecuencia** (regla de oro 7) y enseña el detalle
> verificable (`GET /me falló (503)`) para soporte. «No tienes alcance» sí se distingue **por
> construcción**: es un 200 con `site_scope: []`, no la ausencia de 200.
>
> **Escrito para que nadie lo «arregle» copiando móvil:** allí el caché sellado por `sub` es
> correcto —regla de oro 2, el ocupante necesita su pantalla de crisis sin red y el dato es uno y
> suyo—. Aquí «alcance» es **autorización sobre el tenant entero**, y con la base caída **tampoco
> habría a quién pedirle los datos que ese alcance abriría**: cachearlo solo compraría el riesgo
> de pintar el tenant equivocado.
>
> **Bonus:** `/auth/callback` dejó de colgarse para siempre — su rama de error solo cubría el
> fallo del intercambio OIDC, no el de `/me`.
>
> **Deja abierta** `T-2.134`.

### [x] T-2.124 · La imagen de consola llevaba semanas sin poder construirse — `SOFTWARE` · COMPLETA (2026-08-11)
- **Componente:** deploy + web · **Detectada por:** un despliegue real que murió (2026-08-11)
- **El defecto:** `T-2.75.a` añadió `shared/fixtures/notify-channels.json` —la **misma** fixture
  que leen los dos lados del contrato de canales, `api/tests/api/test_notify_channels.py` y el
  test de `NotificationChannels.tsx`— y `deploy/cloud/console.Dockerfile` copia `shared/sdk-ts` y
  `shared/design-tokens`, pero **nunca `shared/fixtures`**. El `build` de la imagen encadena
  `tsc --noEmit`, que typechequea también los `*.test.tsx`, así que la imagen dejó de compilar:
  `TS2307: Cannot find module '../../../../shared/fixtures/notify-channels.json'`.
- **Por qué vivió en verde desde `6cef7d4`:** `make lint` y el job `web` typechequean el checkout
  **completo**, donde `shared/fixtures/` existe. La imagen solo ve lo que se copia — era la única
  superficie capaz de notarlo, y la construye un comando que **nadie corre en un PR**.
- **Y arrastró el despliegue entero:** `cloud-images` construye las **dos** imágenes y empuja al
  final, así que el fallo de la consola dejó también `takab/cloud` sin subir; `cloud-deploy` fue
  detrás con `manifest unknown`. **Falló seguro**: `alembic` no llegó a correr (rc=125, docker no
  pudo arrancar el contenedor) y la API viva no se tocó — nada quedó a medias.
- **Misma familia que la trampa del bundle de móvil** (`expo-router` barriendo los `*.test.tsx` de
  `src/app`, 2026-08-08): un fichero de **prueba** rompiendo un artefacto de **producción**.
- **Criterios de aceptación:**
  - [x] La imagen de consola construye. **Verificado construyéndola**, no razonándolo.
  - [x] Existe un gate que lo caza **en el PR**, no a los cinco minutos de build de un despliegue.
  - [x] El gate se ha visto **fallar** contra el Dockerfile sin el arreglo.

> **Cerrada (2026-08-11).** Una línea de `COPY` y un censo: `web/src/consoleImageCensus.test.ts`
> deriva del árbol qué importa `web/src` desde **fuera** de `web/` y exige que el Dockerfile lo
> copie. No lleva lista escrita a mano — resuelve cada import relativo contra el disco y solo
> afirma sobre los que existen de verdad, porque de la resolución de módulos sabe `tsc` y aquí no
> se inventa. Corre en el job `web`, que **sí** bloquea el merge.
>
> **Lo que este censo NO es, y está escrito en su cabecera para que nadie se confíe:** no valida
> que la imagen construya —eso solo lo demuestra construirla—, valida la condición concreta que la
> rompió. Si mañana el fallo es una versión de node o un lock desincronizado, seguirá verde y hará
> bien.

### [x] T-2.104 · La app le atribuía a SASMEX alertas que SASMEX no dio — `SOFTWARE` · COMPLETA (2026-08-09)
- **Componente:** mobile · **Depende de:** — · **Origen:** Mauricio movió el sensor con la mano
  para ver si la app reaccionaba
- **El defecto:** `CrisisView.tsx` tenía el titular **escrito a fuego** como
  `ALERTA SÍSMICA SASMEX` para las **cuatro** fuentes. `source.ts` distingue con cuidado
  `sasmex` / `local_threshold` / `quorum` / `manual` —su cabecera dice «solo datos REALES del
  payload… jamás inventar»— y el texto **más grande de la pantalla** las aplastaba todas en el
  nombre del servicio oficial.
- **Medido, no supuesto:** al agitar el sensor, el gabinete abrió un incidente
  `trigger=local_threshold` y la app tituló **«ALERTA SÍSMICA SASMEX»** mientras la píldora
  inferior decía, correctamente, **«FUENTE · REGLAS LOCALES»**. La misma pantalla afirmaba dos
  cosas incompatibles, y la falsa en cuerpo grande.
- **Por qué es grave y no cosmético:**
  · **TAKAB no genera la alerta oficial, la recibe.** El documento de entrega deslinda
    expresamente la cobertura, la latencia y los falsos positivos de SASMEX (§6.1). Atribuirle
    una detección propia **invierte ese deslinde**: el día que el umbral local se dispare de
    más, el ocupante —y el cliente— culpan al servicio oficial.
  · **Choca con la política ratificada en `T-2.32`**, que degradó la detección instrumental de
    una sola estación a AVISO precisamente porque **una estación sola no es autoridad**. Mal
    puede ser aviso en el panel y «alerta oficial» en el teléfono.
  · Con `trigger=manual` era peor aún: una activación humana se anunciaba como alerta sísmica,
    justo lo contrario de lo que el flujo de pánico declara a gritos («NO es la alerta sísmica»).
- **El arreglo:** el titular y el antetítulo salen de `sourceLabel()`, junto a la etiqueta de
  la fuente, porque es la MISMA pregunta: de dónde viene esto. Sólo el contacto seco del WR-1
  puede llevarse el nombre del servicio oficial; la detección propia dice que es propia
  (`SISMO DETECTADO EN ESTE EDIFICIO`), el cuórum que es de la red, y la manual que la activó
  alguien — con antetítulo `● ALERTA ACTIVA`, sin «sísmica». **La instrucción no cambia con la
  fuente**: lo que hay que hacer es lo mismo; lo que cambia es a quién se le atribuye.
- **Criterios de aceptación:**
  - [x] Ningún trigger salvo `sasmex` produce un titular con la cadena `SASMEX`.
  - [x] Ancla a nivel de VISTA (`CrisisView.test.tsx`), que es donde vivía el defecto: las
        pruebas de `sourceLabel` no podían verlo porque la vista no las usaba para titular.
        Verificado en las dos direcciones — reintroducir la cadena pone el test en rojo.
  - [x] Comprobado en el Pixel 8 Pro con un incidente `local_threshold` real.

### [x] T-2.103 · Tras enrolarse, el vigilante de crisis se quedaba ciego — `SOFTWARE` · COMPLETA (2026-08-09)
- **Componente:** mobile · **Depende de:** — · **Origen:** la primera corrida del E2E `01a` en
  un Pixel 8 Pro, con un incidente REAL abierto por el gabinete
- **El defecto:** `useWatchedSiteId()` guardaba el sitio en un `useState` por instancia y solo
  releía SecureStore cuando cambiaban `status` o `me`. **Enrolarse no toca ninguno de los dos**,
  así que `setWatchedSite()` escribía el disco y ningún componente ya montado se enteraba.
- **Por qué importa, y no es una molestia de UI:** `CrisisWatcher` se monta en el layout **raíz**,
  antes del onboarding. En una instalación nueva resuelve `siteId = null` (SecureStore vacío) y
  **se queda así toda la sesión**. Sin sitio no se consulta `mobile-state`; sin fase no hay toma
  de pantalla de crisis. Un ocupante que se enrola y sufre un sismo **antes de reiniciar la app**
  no recibe la instrucción de evacuar. Y esa es, en todo edificio nuevo, la primera sesión de
  todo el mundo.
- **Medido, no supuesto (2026-08-09):** con el servidor devolviendo `phase: "alert_active"` e
  `evac_policy: "evacuate"` para ese mismo ocupante, la app mostraba **SEGURO · Monitoreo
  sísmico activo**. Un `force-stop` + arranque, sin borrar estado, pintaba de inmediato
  `ALERTA SÍSMICA SASMEX · EVACÚE AHORA · ZONA PB-A · T+391m10s`. La toma funcionaba; lo que no
  llegaba era el sitio.
- **El arreglo:** el sitio vigilado pasa a un store observable (zustand, el mismo patrón que
  `session.store`), y `setWatchedSite` **avisa** además de persistir. El disco sigue siendo la
  persistencia; lo que faltaba era la propagación. Cerrar sesión lo suelta, para que la sesión
  siguiente no herede el edificio de la anterior.
- **Criterios de aceptación:**
  - [x] Un consumidor montado ANTES del enrolamiento ve el sitio al vincular
        (`mySite.test.tsx`). Verificado en las dos direcciones: revertir la propagación pone el
        test en rojo.
  - [x] `signOut()` suelta el sitio.
  - [x] Acreditado en device: el E2E `01a` pinta la toma de crisis sin reiniciar la app.

### [x] T-2.102 · Los cinco flujos E2E no podían correr, y no era la app — `SOFTWARE` · COMPLETA (2026-08-09)
- **Componente:** mobile/e2e · **Depende de:** — · **Origen:** la primera corrida REAL de la
  suite Maestro en un Pixel 8 Pro, para `GATE-HW` móvil
- **Tres defectos, todos DE LOS FLUJOS:**
  1. **`clearState` deja al dev-client en el DevLauncher.** Todos los flujos empiezan con
     `launchApp: clearState`, que borra también la configuración del dev launcher: un
     dev-client se queda esperando a que alguien le diga a qué Metro conectarse. El fallo se
     leía como «no encuentro el botón de login», que apunta a la app en vez de al build. La
     suite exige un **APK de release**, y el README decía justo lo contrario.
  2. **Los subflujos de login buscaban `"Email"` y `"Password"`.** La Hosted UI de Cognito se
     sirve en el idioma del dispositivo: en un teléfono en español son «Correo electrónico» y
     «Contraseña». Los cinco flujos morían en el primer campo. Selectores bilingües: fijar el
     español sería cambiar un supuesto por otro.
  3. **Tras `clearState` el occupant pierde su sitio vigilado.** `routers/me.py` construye
     `site_scope` **solo** con los claims del token, y un occupant no lleva `custom:site_scope`
     — es default-deny a propósito (R2). El vínculo vive en `user_zone_assignments` **y** en
     estado local que `clearState` borra, así que reaparece el onboarding y ningún flujo lo
     contemplaba. Subflujo `shared/enrolar-sitio.yaml`, condicionado paso a paso: no hace nada
     si la app ya está vinculada.
- **Y un cuarto, de diseño:** `01` afirmaba la toma de crisis **y después** el check-in de
  vida, que solo aparece cuando el servidor concluye la sacudida. Maestro no puede pausar para
  que alguien cambie la fase del incidente, así que la segunda mitad no podía pasar nunca.
  Partido en `01a-crisis` y `01b-checkin-sync`, cada uno verde por sí solo y **declarando en su
  cabecera** qué fase necesita antes: un flujo que solo pasa si alguien ejecuta algo a mano sin
  que el archivo lo diga es un flujo que miente.
- **Cobertura retirada, y dicho:** el `01` original terminaba con `tapOn: "CUENTA"` +
  `assertVisible: "SINCRONIZACIÓN.*"`, con un «ajustar si aplica» al lado. No aplica: la
  pestaña SYNC es del BRIGADISTA y la pantalla de Cuenta del occupant no tiene sección de
  sincronización — esa aserción no podía pasar nunca. Para el occupant el estado de la cola ES
  la etiqueta «guardado en este dispositivo» / «recibido por el servidor», que sigue asertada;
  la cola vista como cola la ejercita `05`, que corre con el táctico.
- **Criterios de aceptación:**
  - [x] Los tres defectos arreglados, cada uno con su razón escrita dentro del archivo.
  - [x] README con el requisito REAL (release, arm64) y la tabla de precondiciones por flujo.
  - [x] **CUATRO de los cinco flujos acreditados en un Pixel 8 Pro real (2026-08-09):**
        · `04` — el pánico declara «NO es la alerta sísmica» y **un solo voto no dispara**
          (`1 DE 2 CONFIRMACIONES` + expiración).
        · `01a` — toma de crisis con el verbo de la zona, **sin magnitud** (`M ?[0-9]` ausente)
          y con contador **ascendente**, no cuenta regresiva.
        · `01b` — check-in de vida declarando dónde quedó el dato.
        · `02` — táctico con **MFA real**: cámara forense → «PERSONAS EN RIESGO · PRIORIDAD
          MÁXIMA» → foto → `ENVIAR REPORTE`.
        · `05a/b/c` — offline-first con la red REALMENTE cortada: declara `MODO OFFLINE`, deja
          el trabajo `PENDIENTE` y la cola drena sola al reconectar, sin fallidos.
  - [x] **Dos defectos más de los flujos, destapados por la corrida real:**
        · El login del táctico tapeaba el botón del OCUPANTE. Con la sesión de Cognito del
          occupant viva en Chrome, **entraba con el rol equivocado y en silencio** — el peor
          desenlace posible para un login.
        · `05` daba por hecho que el modo avión deja el teléfono sin red. **En Android no lo
          hace**: `wlan0` conserva su IPv4, así que la app no pintaba «MODO OFFLINE» y tenía
          razón. Ahora el WiFi lo apaga `run-offline.sh`, que además lo restaura con `trap`:
          un flujo abortado no puede dejar el teléfono incomunicado.
  - [x] **Y dos de sintaxis que impedían siquiera parsear `05`:** `setAirplaneMode` es un
        escalar (`enabled`), no un mapa; y `assertVisible` no admite `timeout` — eso es
        `extendedWaitUntil`. Llevaban ahí desde que se escribió el flujo porque nadie lo había
        corrido en un teléfono.
  - [ ] **Hueco declarado en `05c`:** el flujo acredita que la cola drena sin fallidos, **no**
        que el elemento llegara al servidor — «salió de la cola» y «lo recibió la nube» no son
        lo mismo y desde el teléfono no se distinguen. Comprobarlo exige mirar `life_checkins`
        del incidente que la app tiene abierto, que en un gabinete vivo suele ser el que abrió
        el propio equipo y no el de `seed_staging_incident.sh`.
  - [ ] `03` necesita además la firma de un inspector en la consola web (otro usuario con MFA).

### [x] T-2.101 · El despliegue al gabinete leía su identidad sin `sudo` — `SOFTWARE` · COMPLETA (2026-08-09)
- **Componente:** deploy · **Depende de:** — · **Origen:** el primer despliegue REAL del edge
  tras `T-2.70.a·D3`
- **El defecto:** el pre-vuelo de identidad (`D3·m5`) hacía `[ -r "$ENTORNO" ]` y
  `sed … "$ENTORNO"` **a pelo**. En un gabinete real `/etc/takab/edge.env` es `0600 root:root`
  —lleva la clave HMAC y el PIN del panel— y el bloque remoto corre con el usuario de
  despliegue, igual que los `sudo install` y `sudo systemctl` de más abajo. Resultado:
  `Permission denied` → «este gabinete no tiene identidad» → **abortaba TODO despliegue a un
  gabinete de verdad**. Medido contra `gw-dev-0001`.
- **El daño peor, detrás del guard:** sin él, la lectura de `TAKAB_EDGE_GPIO_OWNER` habría
  fallado igual de callada y caído al default `edge`. En un gabinete D3 eso hace que el
  despliegue **DESHABILITE `takab-gpio`** y lo deje sin dueño de pines tras el siguiente
  reinicio — el escenario (a) que D3 existe para impedir.
- **Por qué el arnés no lo vio, y por qué ahora sí:** el `sudo` falso era una allowlist de UN
  comando (`systemctl`) y todo lo demás salía `exit 0` mudo. Con eso, hasta el arreglo habría
  sido invisible: un `sudo sed` habría devuelto cadena vacía y el dueño habría caído al default
  con los tests en verde. La lista está **invertida**: se delega todo salvo `install` y `chown`,
  que son los únicos que escribirían fuera del sandbox.
- **Criterios de aceptación:**
  - [x] Identidad leída con `sudo -n`, distinguiendo «no existe» de «existe y no se puede leer
        ni con sudo» — el segundo apunta a permisos/sudoers, no a un gabinete sin provisionar.
  - [x] Ancla estática (`test_la_identidad_del_gabinete_se_lee_SIEMPRE_con_sudo`): se comprueba
        sobre el TEXTO porque en el arnés ambas formas funcionan — el sandbox no puede
        reproducir un `root:root`. Verificada en las dos direcciones.
  - [x] Despliegue real completado contra `gw-dev-0001`: `✓ pines del gabinete en poder de
        takab-edge`, y el panel pasa de 33 a 35 claves (`evidence`, `relays_status`).

### [x] T-2.100 · La app no arrancaba, y ningún gate lo veía — `SOFTWARE` · COMPLETA (2026-08-09)
- **Componente:** mobile + CI · **Depende de:** — · **Origen:** compilar el APK para el
  GATE-HW móvil, un día después de que el defecto entrara
- **El defecto:** `expo-router` construye su tabla de rutas con un `require.context` sobre
  `src/app`, que barre **todos** los ficheros de ahí. `T-2.79.b/c` (2026-08-08) añadió tres
  `*.test.tsx` dentro de `src/app/onboarding/`, que arrastraron
  `@testing-library/react-native` → el `console` de Node al bundle. React Native no trae la
  librería estándar de Node ⇒ **`Android Bundling failed`: la app no arranca en absoluto**.
- **Por qué nadie lo vio:** el job `mobile` corría eslint, tsc y jest, y **ninguno construye un
  bundle**. Los tres estaban en verde con una app que no se podía abrir. Web sí tenía su
  `vite build` desde el principio; móvil no tenía equivalente. El APK del teléfono era del
  18-jul —anterior al defecto— así que tampoco se notó al usar el dispositivo.
- **Arreglo:** los tres tests salen a `mobile/tests/app/onboarding/` (fuera de la raíz del
  router), cada uno con la razón escrita dentro para que no vuelvan. `guard.test.tsx` deriva la
  lista de pantallas del directorio del stack, así que se le declara la ruta REAL una sola vez
  y la comparten sus dos mitades — si se separan, una podría mirar a un directorio vacío y el
  `it.each` pasaría por vacuidad.
- **El gate que faltaba:** `npx expo export --platform android` en `make build` y en el job
  `mobile` de CI. La paridad CI↔make lo exigió sola: al añadirlo solo a CI,
  `test_ci_parity.sh` se puso rojo.
- **Criterios de aceptación:**
  - [x] El bundle de Android compila (1750 módulos) y la app abre en un Pixel 8 Pro real.
  - [x] jest 248/248 y `tsc` en verde tras mover los tests.
  - [x] `make build` y CI construyen el bundle; quitarlo de uno pone en rojo la paridad.

### [~] T-2.99 · El pool de ocupantes nunca llegó al despliegue — `SOFTWARE`
- **Componente:** deploy + api · **Depende de:** — · **Origen:** revisión de sincronía
  edge↔nube↔app del 2026-08-09 (nadie lo había fichado, y ningún test lo vigilaba)
- **El defecto:** `deploy/cloud/deploy.sh` cableaba `TAKAB_API_AUTH_ISSUER/AUDIENCE/JWKS_URL`
  del pool **principal** y **nunca** los tres `TAKAB_API_AUTH_OCCUPANTS_*`. Con
  `auth_occupants_issuer` vacío, `decode_verify_any` (`auth/tokens.py:117-131`) ni siquiera
  mira el segundo pool: cae al `decode_verify` del principal y **el id_token de cualquier
  ocupante muere con `invalid token` ⇒ 401 en `/me`**. El pool existía en Terraform desde
  `T-2.02` y `mobile/.env` lo apuntaba; lo único que faltaban eran tres líneas.
- **Por qué importa:** el ocupante es el usuario más numeroso del producto y **nunca ha podido
  entrar a la nube desplegada**. La app no puede decir por qué: solo enseña "no se pudo
  verificar la sesión". Además deja cojo el **ancla pool→rol** (`auth/deps.py:91-94`), que para
  rechazar el cruce necesita los DOS pools configurados: con uno solo, el rechazo del ocupante
  es un accidente de configuración, no una guarda.
- **Por qué no lo vio ningún test:** `api/tests/api/conftest.py` acuña los tokens de ambos
  pools contra el **mismo** JWKS inline, así que en la suite el dual-issuer siempre tuvo
  issuer. El hueco vivía en el camino de despliegue. Es el mismo patrón que el 401 de audience
  del táctico (2026-07-18): los tests acuñaban el token móvil con el audience del web.
- **Criterios de aceptación:**
  - [x] Los tres `TAKAB_API_AUTH_OCCUPANTS_*` cableados en `deploy.sh` desde los outputs de
        Terraform que ya existían (`occupants_issuer`, `occupants_client_id`).
  - [x] Los tres en `REQUERIDOS_EN_PRODUCCION`: en producción su ausencia **impide arrancar**
        en vez de producir un lockout silencioso.
  - [x] Test de anclaje contra el `deploy.sh` real
        (`test_el_deploy_real_habilita_el_pool_de_ocupantes`), rojo si alguien borra las líneas.
  - [ ] **Verificado contra la nube:** `GET /me` con un id_token del pool de ocupantes
        devuelve 200 (hoy 401). Falta el despliegue.
  - [ ] El cruce de pools sigue dando 401 en ambas direcciones **con ambos pools activos**.

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
- **Decisión:** [`D-18`](DECISIONES-MAURICIO.md#d-18) — `console_scope_enforced` se enciende ya.
- **Es la única brecha multi-tenant viva en producción.**
  `api/src/takab_api/settings.py · console_scope_enforced` lo tiene en `False`. (Citado por
  símbolo y no por línea a propósito: la cita `:212` llevaba meses apuntando a otra cosa.)
- **⚠️ AVISO MEDIDO (matriz `RO-5.g`, 2026-08-08): encenderlo PONDRÁ LA SUITE EN ROJO.** Dos
  tests HTTP fijan hoy la conducta **no** impuesta. No es una regresión: es que la conducta
  cambia y los tests la anclan como está. **Que no lo descubra nadie en mitad de la ventana** —
  hay que invertir esos dos tests **en el mismo cambio**, no después.
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
- **Componente:** operación + mobile · **Depende de:** T-2.87, **T-2.99**
- **⚠️ El orden no es intercambiable:** sembrar el occupant **antes** de que `T-2.99` esté
  desplegada no sirve de nada — el usuario existirá en Cognito y su token seguirá dando 401.
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
- **Decisión:** [`D-21`](DECISIONES-MAURICIO.md#d-21) — la sesión de vida se parte: `G-01` primero y solo.
- **Es la tarea que decide si el producto es real.**
- **Decisión:** [`D-16`](DECISIONES-MAURICIO.md#d-16) — la **BOM del `G-02` NO se compra todavía**. Es aplazamiento de **riesgo**, no de trámite: cada día sin esa ruta es un día en que un Pi colgado deja el edificio sin sirena.
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
- **Decisión:** [`D-20`](DECISIONES-MAURICIO.md#d-20) — la consulta legal espera a que un cliente la pida.
- **Bloquea material comercial.** La cita antigua "NOM-003-SCT" era una norma de **transporte**
  (etiquetado de materiales peligrosos) y **no aplicaba**; FASE-0 ya la había descartado y la
  edición anterior de RBAC la daba por confirmada de forma circular. La regla operativa
  —auditoría, evidencia y dictámenes inmutables, jamás podados— es **requisito propio de
  TAKAB** y no cambia; lo que falta es el marco **citable**.
- **Criterios de aceptación:**
  - [ ] Marco normativo citable definido con abogado/cliente y escrito en blueprint §9.
  - [ ] `RBAC-TAKAB.md §8` punto 3 y `ANALISIS` pregunta abierta #1 actualizados a la vez.

### [ ] T-2.97 · `GATE-STORE` · APNs/FCM reales + tono PROPIO — `HUMANO-AWS`
- **Componente:** mobile + infra · **Depende de:** —

> ### El componente `LEGAL` de esta ficha lo retiró [`D-19`](DECISIONES-MAURICIO.md#d-19) (2026-08-17)
>
> La ficha exigía **licenciar el tono del SASMEX con CIRES**, y eso ya no aplica: la app suena con
> un **tono propio de TAKAB**. Lo que queda es puro `HUMANO-AWS` —credenciales de tienda— y la
> comprobación en un teléfono real.
>
> **El tono propio YA está cableado** (2026-08-23): `alerta_sismica.wav` en el canal
> `seismic_alert_v2` de Android y como `sound` crítico en iOS, con un censo cruzado que exige que
> todo sonido declarado por el servidor exista en el plugin **y en el disco**. Lo que falta es que
> el push salga de credenciales de verdad.

- **Criterios de aceptación:**
  - [ ] Credenciales APNs/FCM reales; `TAKAB_API_PUSH_*_APPLICATION_ARN` aplicado.
  - [x] ~~Tono SASMEX licenciado con CIRES~~ — **REVOCADO por `D-19`**: el tono es propio.
        Cableado y anclado en `api/tests/notify/test_censo_canales_y_sonidos.py`.
  - [ ] Push real recibido en device real, con el tono correcto.

### [ ] T-2.98 · Entitlement Critical Alerts de Apple — `LEGAL`
- **Componente:** mobile · **Depende de:** T-2.97
- **Criterios de aceptación:**
  - [ ] Solicitud presentada con la justificación de uso (alertamiento sísmico).
  - [ ] Si Apple lo niega, **queda escrita la degradación**: qué recibe el ocupante con el
        teléfono en silencio y qué no. Un "no" sin plan es un ocupante que no se entera.

---

## Fase 2.13 · Landing pública del dominio — el reemplazo del sitio de `T-2.156`

> La página mínima de `T-2.156` cumplió su papel (evidencia del caso SES). Esta fase la
> reemplaza por la landing real en `landing/` (Astro estático, workspace autocontenido), con el
> perímetro de claims de `CONSULTA-LEGAL-TAKAB.md` convertido en test bloqueante. Decisiones de
> Mauricio (2026-08-25): contacto por correo nuevo + WhatsApp, v1 sin fotografía, **sin cifras
> medidas publicadas** (solo cualitativo, hasta la consulta de `T-2.96`), hosting en el
> S3+CloudFront existentes. Runbooks: `landing/README.md` y `deploy/landing/README.md`.

### [x] T-2.166 · La landing real: workspace `landing/` con el perímetro de claims hecho test — `SOFTWARE` · COMPLETA (2026-08-25)
- **Componente:** landing (nuevo) · **Sale de:** reemplazar el sitio mínimo de `T-2.156` por una cara pública real
- **Dirección visual fijada por brief:** industrial-brutalist «Swiss Industrial Print» — papel/tinta/rojo del dictamen, Saira Condensed + Archivo + JetBrains Mono, retícula visible. Contraste deliberado con la consola (oscura). Contrato de dirección en `landing/src/layouts/Base.astro` (sobrevive al build); verdad de producto en `landing/PRODUCT.md`.
- [x] Workspace Astro con `lint` / `format:check` / `typecheck` / `test` / `build` espejados en `make` y en el job `landing` de CI — `test_ci_parity.sh` en verde en el mismo PR que crea el workspace (la lección de mobile: nunca existe un workspace sin cobertura).
- [x] Suite de contenido bloqueante sobre `dist/` (`landing/tests/contenido.test.mjs`): deslinde SASMEX y declaración del dominio remitente OBLIGATORIOS (el sitio sigue siendo evidencia SES); cifras medidas, normas y badges de tiendas PROHIBIDOS; cero orígenes externos (fallaría hasta un Google Fonts); toda `<img>` con dimensiones; presupuestos JS < 20 KB gz y HTML < 40 KB gz.
- [x] Pieza central: esquema SVG inline + CSS puro del camino SASMEX→gabinete→actuadores con botón `[ EJECUTAR SIMULACRO ]` accesible por teclado, `aria-live`, y dos layouts (vertical/horizontal). SOLO `transform`/`opacity` (el «dibujado» es `scaleX/scaleY`, sin `stroke-dashoffset`); `prefers-reduced-motion` = esquema estático completo.
- [x] Fuentes woff2 auto-hosteadas y commiteadas (~32 KB los 4 subsets) con fallbacks de métricas (`size-adjust`/`ascent-override`); cero peticiones a terceros en runtime.
- [x] Evidencia E2E commiteada (`landing/tests/e2e/evidencia/`): capturas 360/768/1280/1920 sin scroll horizontal, axe 0 critical/serious (medido en estado final con `reducedMotion`), teclado (primer Tab = salto de contenido), variante reduced-motion.
- [x] Detector de impeccable corrido en modo completo; hallazgos reales corregidos (leyenda del banner sin uppercase corrido, anotaciones del SVG ≥9 px) y falsos del análisis estático anotados (pares de colores que no coexisten; `clamp()` sin parsear).
- **Trampa que costó dos rondas de inspección:** Astro NO añade su atributo de scope al `<svg>` raíz, así que una regla scoped sobre la clase del svg no matchea — y una scoped de más especificidad (`.esquema[cid] svg`) pisa el `display:none` del swap responsive. Las reglas del svg raíz viven en `global.css` con especificidad decisiva.

### [~] T-2.167 · El módulo `site` suelta el contenido: Terraform posee el continente, git el contenido — `SOFTWARE` listo · falta el `apply` (ventana `PENDIENTES §2.10`)
- **Componente:** infra (`modules/site`) + `deploy/landing/` · **Depende de:** `T-2.166`
- [x] `aws_s3_object.index` retirado del módulo y del estado vía `removed { destroy = false }` en `envs/dev` (Terraform ≥1.7; validate en verde) — el objeto histórico sigue sirviendo hasta que el primer sync lo pise.
- [x] `custom_error_response` 403/404 → `/404.html` **manteniendo `response_code = 404`** (la decisión anti-espejo de `T-2.156` no cambia).
- [x] Versionado del bucket + lifecycle (poda de versiones no-actuales a 90 días): rollback sin rebuild y `rm` reversibles.
- [x] Outputs `site_bucket` / `site_distribution_id` re-exportados; `deploy/landing/deploy.sh` los lee con `terraform output -raw` (no teclea nombres de recursos).
- [x] `deploy.sh` con guardas (main limpio y pusheado, CI verde, SSO vivo), sync en 4 clases de caché (woff2 con `--content-type font/woff2` + immutable; `_astro/*` immutable; HTML 300 s AL FINAL; raíz no hasheada 3600 s y jamás immutable), `deploy-info.json` con la rev, poda de huérfanos explícita y modo `--pre` para la transición.
- [ ] **Gate externo (Mauricio):** `terraform plan` debe decir `0 to destroy` con `aws_s3_object.index` saliendo del estado como no gestionado; luego `apply`. El clasificador niega `terraform apply` a agentes.

### [ ] T-2.168 · Corte a producción de la landing y verificación desde fuera
- **Componente:** deploy · **Depende de:** `T-2.167`
- [ ] Orden anti-ventana del runbook (`deploy/landing/README.md`): `deploy.sh --pre` → plan con gate `0 to destroy` → `apply` → `make landing-deploy`.
- [ ] Smoke con códigos, no con ojos: `/` 200 con `max-age=300` · `/aviso-de-privacidad.html` 200 · `/no-existe` **404** · un `_astro/*` `immutable` · `deploy-info.json` con la rev desplegada.
- [ ] Verificación desde un punto NO privilegiado (la lección de `T-2.156`: la primera vez solo se miró desde la máquina de Mauricio).
- [ ] Lighthouse contra producción dentro de presupuesto (LCP < 2.0 s en 4G emulado, CLS < 0.1) y capturas archivadas.

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
- [x] **Arquitectura escrita ANTES del código** — [`design/BLOQUE-IV-ARQUITECTURA.md`](design/BLOQUE-IV-ARQUITECTURA.md)
      parte A (`D-08`, 2026-08-16). Lo que fija, y que cambia el alcance de esta ficha:
  - [ ] **Tres capas que NO se mezclan**: observado (puntos medidos), estimado (superficie de
        `ATTEN-LAW v1`) y **residuo**. El residuo es el producto — un punto que sacude el triple de
        lo que la ley predice es lo único que el modelo no sabía, y lo que justifica el mapa.
  - [ ] Cada valor viaja con su **procedencia** (`measured`/`modeled`) y la consola las pinta
        **distinto**, con test sobre el DOM y no sobre la lógica (lección de `T-2.104`).
  - [ ] **`SIN COBERTURA` es un estado propio**, no un color pálido (misma doctrina que `T-3.08`).
  - [ ] **NO es un microservicio.** Se calcula por evento en el worker que ya existe: lo que se
        calcula no es continuo, y un servicio más es un despliegue, una alarma y un rol IAM más.
  - [ ] **Depende de [`T-2.149`]** (catálogo SSN): sin magnitud/epicentro no hay capa estimada. El
        mapa **existe degradado y lo declara**, en vez de inventar un epicentro.
- [ ] La regla de oro 9 (sin streaming continuo de waveform crudo) sigue en pie: el mapa se
      construye de features, no de forma de onda en vivo.

## Fase 3.2 · CCTV ONVIF real + conteo de aforo

Requisito **nuevo de Mauricio (2026-07-10)** que **no está en el blueprint**. Toca privacidad
(**video = PII**) y **compite por CPU con el reflejo GPIO**, que es el proceso que toca la
sirena.

> **Si no cabe en el Pi 4, la respuesta correcta es hardware separado — nunca optimizar el
> proceso que toca la sirena** (regla de oro 4).

> ### 📌 Estado de las decisiones (2026-08-29) — léelo antes de abrir cualquiera de estas fichas
>
> - [`D-24`](DECISIONES-MAURICIO.md#d-24) **enmienda** a [`D-14`](DECISIONES-MAURICIO.md#d-14): el
>   conteo autoritativo lo hace **la nube**. Sube **un clip** (`T−60 s`→`T+600 s`) y un **goteo de
>   capturas** hasta el reingreso; el operador ve y descarga. Sigue en pie de `D-14`: clips **solo
>   de evento confirmado**, retención acotada, salida de vídeo **auditada**, y la caída a **solo
>   aforo por configuración de sitio** (`cameras.count_mode`).
> - [`D-25`](DECISIONES-MAURICIO.md#d-25): el software se construye **ya**; **encenderlo en el
>   gabinete espera a `G-04` acreditado + la medición de `B.2`**. Las fichas se cierran con el
>   módulo apagado; el gatillo de encendido vive en `D-25`.
> - **Dos máquinas, y no hay que confundirlas.** El **banco** es un Pi 4 de **1 GB** (905 MB
>   totales, 654 disponibles, sin ffmpeg — medido el 2026-08-29); el **equipo de campo** será un
>   **Pi 5 de 8 GB o un Pi 4 de 8 GB**, y **está sin comprar**. Con 8 GB el detector cabe: lo que
>   mantiene el conteo en la nube no es la RAM, es que `B.2` **no se puede medir en una máquina
>   que no es la que va a ejecutar**. El conteo preliminar local está **aplazado, no descartado**
>   ([`D-24` · corrección de premisa](DECISIONES-MAURICIO.md#d-24)).

### [~] T-3.10 · Arquitectura al blueprint y política de retención de vídeo — `SOFTWARE` + `DECISIÓN`
> **Escrito el 2026-08-29** (blueprint §4.8, `D-24`, `D-25`). Sigue abierta por **dos mitades
> muy distintas**, y confundirlas es lo que la deja parada:
>
> * **El job de poda está CONSTRUIDO** (2026-09-01): `api/src/takab_api/ops/prune_cctv.py`,
>   con 26 tests y las dos mitades separadas por nombre en el informe. Ver más abajo.
> * **La medición de `B.2` sí espera**, y a algo concreto: el Pi con carga real de CCTV, que
>   llega con `G-04` por `D-25`. Fichada en
>   [`PENDIENTES-MAURICIO §3.3.d`](PENDIENTES-MAURICIO.md).
- **Diseño escrito (`D-08`, 2026-08-16):**
  [`design/BLOQUE-IV-ARQUITECTURA.md`](design/BLOQUE-IV-ARQUITECTURA.md) parte B. Lo que queda es
  llevarlo al blueprint **con la enmienda de `D-24` dentro**.
- [x] Sección nueva del blueprint: topología, dónde vive el proceso, y **presupuesto de CPU**.
      **`§14` NO se toca**: el CCTV no es invariante ni diferido, es hardware opcional de la
      topología (`§3`, `§4.1`). Tocarlo obliga a mover el número clavado en
      `api/tests/test_matriz_trazabilidad.py:2042-2059` y a citar un test real por nombre.
- [x] Tratamiento de PII de video: retención, acceso por rol, y su encaje con la Fase 2.8.
- [x] **El vídeo NO hereda la exención de poda de la evidencia** (regla de oro 11): esa exención es
      para auditoría y dictámenes, no para imágenes de personas. Retención mínima y declarada.
- [x] La poda del vídeo va en **job propio** (`api/src/takab_api/ops/prune_cctv.py`), **no** como
      `RetentionRule`.
      > **Por qué, y es la trampa cara de esta ficha:** `retention._validar_plan()` corre en el
      > import y exige que toda columna de una regla esté en `PII_INVENTORY` con `action=="erase"`;
      > eso arrastra `test_privacy_erasure.py:171-181`, que compara **por igualdad** contra
      > `ERASED_TABLES` — o sea que ARCO pasaría a tener que tocar `cctv_clips` y cambiarían las
      > claves `affected` de la constancia. Radio de explosión enorme y en la dirección equivocada.
- [x] **Las dos mitades de la poda, y las dos se reportan:** un `s3_key` en `NULL` **no borra los
      bytes**. Hace falta el `UPDATE` en Postgres **y** el borrado del objeto. Un plan que anula la
      referencia y deja la imagen es peor que ninguno, porque **se declara cumplido**.
      > ### El ORDEN resultó ser la ficha entera
      > Se borra en S3 **primero** y se anula la fila **después**. Al revés, un fallo de S3 deja la
      > base diciendo `PURGADO` con la imagen viva — el fallo literal de esta viñeta. En este
      > orden, un fallo deja **bytes muertos sin referencia**: molesto, visible, y no miente.
      > El informe separa los tres desenlaces por nombre —`completo`, `huérfano`, `fallido`—
      > porque un total único confundiría «la imagen ya no existe» con «la imagen sigue ahí».
      >
      > Y por eso la transacción es **por objeto** y no una por corrida, al revés que
      > `prune_pii`: con una sola, un fallo en el objeto 40 revertiría las 39 filas ya anuladas
      > cuyos bytes están destruidos de verdad — convertiría 39 podas correctas en 39 huérfanos.
      > Ninguna transacción de Postgres deshace un `DeleteObject`.
- [x] **La trampa que ninguna prueba habría cazado sin ejercerla: el bucket de evidencia está
      VERSIONADO.** Un `delete_object` sin `VersionId` **no borra un byte** — pone un delete
      marker y deja el cuerpo como *noncurrent*, facturándose. El objeto desaparece de un `GET`,
      así que un test de «ya no se puede leer» **pasa**, y la imagen de las personas sigue ahí.
      Es el fallo de la viñeta anterior disfrazado de éxito.
      > No es una hipótesis: ya mordió en este árbol con las reglas `Expiration` de los buckets de
      > respaldo y de transferencia, que parecían retención y eran un cambio de etiqueta
      > (`modules/storage/main.tf`). Se resuelve en `routers/_s3.delete_all_versions`, que lista
      > las versiones de ESA key —filtrando por igualdad, porque `Prefix` casaría también con
      > `clip.mp4.bak`— y borra cada una por `VersionId`, delete markers incluidos. **El control
      > negativo está en la suite**: un test comprueba que el borrado ingenuo deja el cuerpo vivo,
      > y si algún día dejara de dejarlo, `delete_all_versions` sería complejidad sin motivo.
- [x] **La precondición específica del vídeo, y es la que convierte la promesa en hecho.** El job
      comprueba en CADA corrida que `cctv_purge_guard` sigue activo en `UPDATE` (`tgenabled <>
      'D'`, porque un trigger apagado sigue en el catálogo y no para nada). Mientras lo esté, este
      job **no puede** hacerle a `cctv_clips` nada que no sea podar, aunque el código se lo
      proponga. Sin él, aborta. Es el análogo exacto del suelo de `COMPLIANCE_ANCHOR`, y se apoya
      en el mismo `harden_session` de `prune_pii` —importado, no copiado: dos comprobaciones de
      compliance que se creen la una a la otra acaban divergiendo.
- [x] **El reloj cuenta desde la GRABACIÓN, no desde el registro** (`ended_at` / `captured_at`,
      nunca `created_at`). La fila nace cuando S3 avisa, que puede ser días después: un gabinete
      sin enlace sube su clip al reconectar, y contar desde el registro le regalaría a esa imagen
      un plazo que nadie autorizó. Consecuencia incómoda, dicha en voz alta: **un clip puede
      llegar ya vencido y podarse sin que nadie lo haya visto**. Es la política funcionando.
- [ ] **La retención es GLOBAL y el blueprint la pide POR SITIO.** Hoy no hay dónde escribirla —ni
      `sites` ni `cameras` tienen columna de plazo—, así que se implementó lo expresable: una
      ventana por tabla (`TAKAB_API_RETENTION_CCTV_CLIPS_DAYS` / `..._STILLS_DAYS`), deshabilitada
      por defecto. **El hueco se declara en vez de fingir que la variable global es «por sitio».**
- [ ] **El cron y su constancia**, con el patrón de `T-2.81.a`: documento SSM diario y una fila por
      corrida de la que salga una métrica. Hoy el job existe y **hay que invocarlo a mano**; una
      poda que depende de que alguien se acuerde no es una política de retención.
- [ ] La medición de `B.2` sigue pendiente y su regla de decisión **no se reabre**:
  > **La regla de decisión ya está escrita, y a propósito ANTES de ver el número** para que no se
  > acomode al resultado: lo único que decide es la **latencia del reflejo SASMEX→relé bajo carga
  > de CCTV** contra su presupuesto de 100 ms. Si se acerca, **hardware separado, sin discusión**.
  > El sesgo del que hay que protegerse es «va justo pero cabe»: el margen actual es de **dos
  > órdenes de magnitud** (6.65 ms / 4.16 ms) y gastarlo en vídeo lo cambia por lo único que el
  > sistema no puede permitirse.
- [x] La pregunta «¿el aforo viaja como número o como imagen?» **queda respondida por `D-24`**:
      como imagen, con todo lo que eso obliga a acotar. Escrito, no implícito.

### [x] T-3.10.b · Guarda de licencias — cero AGPL/GPL en el árbol — `SOFTWARE` · **COMPLETA (2026-08-30)**
> `ci/licencias.py` + `ci/check-licenses.sh` + job `licenses` en CI, con 15 tests de los que
> la mitad son **negativos**: una guarda que nunca ha fallado es una función que nadie ha
> ejercido.
>
> El falso positivo que decidió el diseño, medido en este árbol: **matplotlib y scipy**
> vuelcan el TEXTO COMPLETO de su licencia en el metadato `License`, y ese texto menciona la
> GPL —para hablar de compatibilidad—. Un `grep GPL` marcaba las dos. Se clasifica por
> **classifiers Trove** (vocabulario controlado) y solo se cae al campo libre cuando no hay
> ninguno, con SPDX y frontera de palabra para que `LGPL-3.0` no cuente como `GPL-3.0`.
>
> **Falta un clic de Mauricio** para que el check bloquee el merge (fichado en
> `PENDIENTES-MAURICIO §1`): hasta entonces avisa, no impide.
- [x] `ci/check-licenses.sh` falla el build si aparece cualquier **prohibido**: `ultralytics`
      (AGPL-3.0 — incluye YOLOv8, YOLO11 y su RT-DETR), `deep-sort-realtime` / DeepSORT de nwojke
      (GPL-3.0), YOLOv6, YOLOv7 (GPL-3.0), YOLO-NAS (pesos no comerciales).
- [x] GPL/AGPL en el árbol **transitivo** de `api/` y `edge/`. No basta la lista de nombres: la
      deuda llega por dependencia indirecta, y por eso se revisa además el `uv.lock` de cada
      proyecto —que lista la resolución completa— sin necesidad de instalar nada.
      > **Se implementó con `importlib.metadata`, no con `pip-licenses`.** Lee los mismos
      > metadatos, es de la biblioteca estándar y no añade **una dependencia más que auditar
      > dentro de la guarda que audita dependencias**. El criterio se cumple igual.
- [x] Los `.onnx` se validan: fallar si `metadata_props` menciona AGPL/GPL. Un peso no lleva
      `setup.py`, así que ningún escáner de paquetes lo ve.
- [x] `THIRD_PARTY_NOTICES.txt` **generado** en el build, no escrito a mano.
- [x] Job `licenses` en `.github/workflows/ci.yml`, y **prueba negativa**: la guarda tiene que
      poder fallar (instalar un prohibido a propósito la pone roja).
- [x] **Un job nuevo no bloquea el merge solo.** La protección de `main` exige siete checks por
      nombre literal (`D-09`); que `licenses` bloquee es un clic de Mauricio, y va fichado en
      `PENDIENTES-MAURICIO`. Una guarda que no guarda es peor que ninguna: da confianza falsa.

### [x] T-3.11 · Cliente ONVIF y grabador en el gabinete — `SOFTWARE` · **COMPLETA (2026-08-30)**
> `takab_edge/cctv/`, unidad `takab-cctv.service`, simulador de cámara y **93 tests**.
>
> **El E2E encontró un fallo que los ocho tests unitarios no podían ver:** la poda del
> anillo se comía el material del propio clip antes de cortarlo. El clip abarca 660 s y el
> anillo dura 180, así que al llegar el momento de recortar ya faltaban los primeros ocho
> minutos — el clip salía con un **27 % de cobertura**, lo declaraba honestamente, y era un
> 27 % que nadie había pedido. Cada test unitario cortaba en un tick que aún no había
> podado tan atrás, así que los ocho pasaban. Ahora la ventana de la sesión abierta es
> intocable; subir el suelo de `ring_s` habría obligado a mantener once minutos de anillo
> las veinticuatro horas para un caso que ocurre unas veces al año.
>
> ### ⚠️ COMPLETA en software, y **no ha grabado un solo clip en el Pi**
> El extra `cctv` está en `EDGE_EXTRAS_OMITIDOS` de `deploy/edge/deploy.sh`: el gabinete real
> ni siquiera lo instala, porque encenderlo espera a `G-04` y a la medición de `B.2` (`D-25`).
> El recorte del clip y el `concat` sobre once minutos de anillo están medidos **en x86-64**,
> que es otra máquina y otro decodificador. Lo que falta para ejercerlo donde importa va en
> [`PENDIENTES-MAURICIO §3.3.d`](PENDIENTES-MAURICIO.md).
- [x] Proceso **separado** (`takab-cctv`), con límite de CPU explícito, que no puede degradar
      `takab-gpio`.
- [x] Falla del cliente ONVIF ⇒ el resto del gabinete no se entera.
      > **La dirección es lo que da la garantía, no la disciplina.** `takab-cctv` es **cliente**:
      > sondea `GET /api/status` a 1 Hz. El edge es servidor y **estructuralmente no puede**
      > depender de él. El anillo de pre-grabación hace irrelevante el ~1 s de latencia del sondeo.
- [x] **No graba si el WR-1 está en modo prueba.**
      > La trampa que esto evita, y no es teórica: el embudo del edge suprime lo que va a la nube
      > en `_modo_prueba_activo` (`edge/takab_edge/supervisor.py:630-635`). Un CCTV que no mire ese
      > flag sube a S3 **vídeo real de un edificio real** durante una prueba de banco — sin
      > incidente al que atarlo, sin base legal y con factura.
- [x] No graba en `Tier.NORMAL`; **sí graba** aunque la alerta sea `visual_only` (T-2.32), igual
      que `queue_evidence`, que está deliberadamente fuera de esa puerta.
- [x] Anillo `ffmpeg -c copy` autopurgado; **cuota de disco dura** por bytes y por clips
      pendientes. La microSD es de la que arranca el camino de vida: un clip atascado no puede
      llenarla.
- [x] **ffmpeg LGPL, como subproceso, verificado al arrancar.** El de Debian trae `--enable-gpl`;
      el guard lo rechaza **fail-closed** y dice de dónde sacar uno válido.
- [x] Unidad `takab-cctv.service` con los límites de `B.3` —`CPUQuota=`, `MemoryMax=`, `Nice=`,
      `Restart=` propio— y su test de artefacto, como `takab-gpio`.
- [x] El extra `cctv` nuevo obliga a declararlo en `deploy/edge/deploy.sh`
      (`EDGE_EXTRAS`/`EDGE_EXTRAS_OMITIDOS`): `uv sync` **poda**, así que no decidir es desinstalar.
- [x] **Acreditada contra la cámara real** (2026-08-30, `192.168.3.132`) — ver el bloque de abajo.
- [x] Simulador de cámara en `edge/simulators/`, para que el E2E corra sin hardware ni AWS.
      Modela la cámara **y la frontera de ffmpeg**, porque por separado no sirven: reconoce
      los tres comandos por su forma y escribe los ficheros que habrían salido.
      > **Lo que NO acredita, y va escrito en el propio módulo:** los segmentos no son vídeo
      > decodificable, así que nada de lo que solo un ffmpeg real puede fallar se prueba
      > aquí —keyframes del substream, recorte que empieza en gris, `concat` que rechaza la
      > lista—. Eso es `GATE-HW`. Las capturas **sí** son JPEG válidos, pero no son fotos de
      > personas: por eso la «historia» de cuánta gente hay va en un guion explícito y no
      > escondida en los píxeles.

> #### La cámara real, medida (2026-08-30) — y el fallo que solo ella podía enseñar
>
> Cámara del sitio: **LC / Dahua `IPC-S41FE`**, firmware `2.800.0000000.15.R`, ONVIF en el
> puerto **80** (`/onvif/device_service`), RTSP en el 554. Dos perfiles Profile S:
>
> | perfil | codec | resolución | fps | bitrate |
> |---|---|---|---|---|
> | `Profile000` (main, `subtype=0`) | H264 | **2560×1440** | 25 | 1536 kbps |
> | `Profile001` (sub, `subtype=1`) | H264 | **640×480** | 15 | 512 kbps |
>
> **Ofrece `GetSnapshotUri`**, que es la rama barata: el goteo es un `GET` de un JPEG ya
> codificado y no decodifica un solo fotograma.
>
> **El fallo: `descubrir()` entregaba URLs que la cámara no servía.** El módulo daba por
> hecho que una cámara ONVIF devuelve la URL con la credencial dentro. Ésta devuelve las
> tres URIs **peladas** y luego exige **Digest** en las tres (con Basic contesta `401`
> igual). Medido a mano, que es como se cerró:
>
> ```
> DESCRIBE con la URL que devolvía descubrir()  ->  RTSP/1.0 401 Unauthorized
> DESCRIBE con la credencial inyectada          ->  RTSP/1.0 200 OK  (+ pista H264)
> ```
>
> Por el camino de descubrimiento —el que se usa cuando no hay `rtsp_url` declarada— el
> gabinete no habría grabado **ni un clip ni una captura**. Y las ocho pruebas del módulo
> pasaban porque **el simulador devolvía la URL con credencial**: la misma suposición
> escrita dos veces, comprobándose a sí misma. Arreglado en `fix/cctv-camara-real`, con las
> URIs medidas fijadas en `edge/tests/test_cctv_onvif_credencial.py`.
>
> **El segundo hallazgo, y éste no lo veía ninguna prueba porque no está en el código:
> la cámara MIENTE en los píxeles.** Llegó con el huso de fábrica del fabricante
> —`GMT+08:00`— y el UTC correcto, así que rotula la imagen catorce horas por delante de la
> hora del sitio. Medido: el gabinete fechaba las **11:57 del 30 de agosto** y el fotograma
> decía **01:57 del 31**. Ese sello va quemado dentro del clip y dentro de cada captura, y
> **cuatro de esas capturas son pruebas del dictamen** (§11 del reporte, con su `sha256` y su
> cadena de custodia). Un paquete de evidencia que se contradice a sí mismo en la fecha no
> hay que impugnarlo: se impugna solo. Y `DateTimeType` viene en `Manual` —sin NTP—, así que
> el desfase solo puede crecer.
>
> De ahí la **quinta comprobación** de `takab-cctv`, que **avisa y deja grabar**: el vídeo
> está bien y nuestras horas también —salen del gabinete—; lo torcido es el rótulo, y
> negarse a grabar por eso cambiaría un rótulo torcido por un incidente sin vídeo.
- [ ] **El hallazgo del reloj todavía muere en el journal.** Hoy sale por `log.warning` al
      arrancar, y eso lo lee quien va a buscarlo. Lo que corresponde es que viaje con la
      evidencia: si el sello de una captura contradice la fecha del incidente, **el reporte
      tiene que decirlo al lado de la imagen**, que es donde alguien lo va a leer. Mismo
      argumento que el `410` del clip podado — el hecho sobrevive a la imagen.
- [x] **Poner en hora la cámara del sitio.** HECHO el 2026-08-30: huso escrito por ONVIF y
      verificado **contra el sello**, no contra la pantalla de configuración — la foto pasó de
      decir `2026-08-31 01:57` a `2026-08-30 14:03:53`, exacta al segundo.
- [ ] **El NTP de la cámara sigue abierto, y no se puede cerrar desde aquí.** `SetNTP` no
      está implementado en ella y **no tiene interfaz web** (todo el árbol HTTP devuelve
      `000`; el puerto 80 solo sirve ONVIF y la instantánea). O se hace desde su app, o **lo
      hace el gabinete** —que ya le lee el reloj y tiene credencial de escritura—, y eso
      último es una **capacidad nueva**, no un arreglo: se decide, no aparece. Mientras tanto
      el desfase es de segundos y la quinta comprobación lo canta en cada arranque.

> #### El camino de vídeo, ejercido con ffmpeg LGPL de verdad
>
> Se bajó el build que el propio guard recomienda (`BtbN/FFmpeg-Builds`, variante `lgpl`) y
> con él se cerraron tres cosas que hasta hoy solo se probaban con dobles inyectados:
>
> 1. **`verificar()` acepta un binario LGPL real.** Nunca se había ejecutado contra uno: los
>    ocho tests del guard inyectan la salida de `-version`.
> 2. **El anillo graba.** `cmd_anillo` contra el substream escribió 3 segmentos MP4 en 25 s
>    (~580 kB cada uno), con `-c copy` y sin decodificar.
> 3. **`cmd_captura` funciona contra RTSP** —substream y principal, `rc=0`—, **y falla contra
>    la instantánea HTTP con `401`**. Ese es el segundo hallazgo, y estaba escondido detrás
>    del primero.
>
> **La instantánea por ffmpeg da 401, y la causa no es la que parece.** ffmpeg sí hace
> Digest y manda una cabecera bien formada; lo que ocurre es que el analizador de la cámara
> **depende del orden de los parámetros**. Aislado en cruz sobre `opaque`, `algorithm` y el
> entrecomillado de `qop`, el orden resultó ser el único factor que decide:
>
> | orden | resultado |
> |---|---|
> | `nc=…` antes de `cnonce=…` (lo que manda urllib) | **200** |
> | `cnonce=…` antes de `nc=…` (lo que manda ffmpeg) | **401** |
>
> La RFC 7616 dice que esa lista **no** tiene orden, así que quien está mal es la cámara. Da
> igual: es la que hay. Y lo que significaba en producción es lo que lo hace grave —
> `_gotear` **prefiere** la instantánea, así que habrían fallado **todas** las capturas del
> goteo: el clip perfecto y el **reingreso sin fechar jamás**, que es lo único que solo el
> goteo puede fechar. Arreglado bajando la instantánea con `urllib`
> (`takab_edge/cctv/instantanea.py`), con caída al RTSP **anunciada**; verificado contra la
> cámara real, 5/5 capturas a ~350 ms.
>
> #### Y al cortar el clip apareció el tercero: **el anillo estaba grabando AUDIO**
>
> El clip salió `h264 + **aac**`. `cmd_anillo` usa `-c copy`, que copia lo que la cámara
> mande, y esta manda una pista de sonido junto al vídeo. **Nadie lo decidió**: no hay una
> línea del diseño que pida audio, el conteo no lo usa y el reporte no lo enseña. Entró
> porque nadie miró los streams que traía el `-c copy`.
>
> Y no es «un poco más» de lo mismo. Grabar las conversaciones de la gente en el punto de
> reunión es **distinto en especie** de grabar su imagen: cambia el marco legal aplicable
> —comunicaciones privadas, no solo datos personales— dentro de un objeto que va firmado a
> S3 y de ahí a un peritaje. Con la regla de oro 11 delante, el default solo puede ser el
> conservador. `-an` en el anillo, con la razón escrita en el propio comando y su test.
> Verificado contra la cámara real: los tres segmentos salen `h264,video` y nada más (y de
> paso pesan ~15 % menos).
- [x] **Ratificado como [`D-26`](DECISIONES-MAURICIO.md#d-26)** el 2026-08-30: el CCTV graba
      imagen y nada más. Ya no es un default elegido por la máquina ante un hallazgo, es una
      decisión con su razón escrita — y con su camino de derogación, que exige **base legal y
      aviso a los ocupantes**, no solo quitar la bandera.

> **Lo que sigue sin acreditar:** el Pi **no tiene** `/opt/takab/bin/ffmpeg` —hace falta la
> variante `linuxarm64-lgpl`—, así que el recorte del clip y el `concat` sobre once minutos
> de anillo siguen sin ejercerse **en la máquina que va a ejecutarlos**. Lo de arriba se
> midió en x86-64. Sigue siendo `GATE-HW`, pero por bastante menos de lo que era esta
> mañana.

### [x] T-3.11.b · Esquema de CCTV y la costura de subida — `SOFTWARE` · **COMPLETA (2026-08-30)**
> Migración `0053_cctv`, espejo en `db/schema.sql` **generado** desde ella y aplicado sobre
> base fresca sin un error, grant por el contrato existente, subida directa a S3 y egreso
> auditado. El guard de poda se verificó **contra Postgres**, no se razonó.
>
> Tres fallos los encontraron los tests, no la revisión, y los tres eran de producción:
> el worker corre como `takab_ingest` y la migración solo concedía a `takab_app`;
> `analysis_state` era una columna **mutable sobre una tabla append-only** —el analizador
> jamás habría podido moverla— y ahora el estado se **deriva**; y la unicidad iba por
> `(incident_id, started_at, camera_id)` con `camera_id` nullable, así que **los NULL no
> colisionan** y el `ON CONFLICT` no hacía nada: una reentrega de SQS escribía dos filas y
> dos egresos. Va por contenido, con el precedente de `uq_evidence_incident_sha256`.
- [x] Tablas `cameras`, `cctv_clips`, `cctv_stills`, `cctv_occupancy`,
      `cctv_evacuation_metrics` con `tenant_id` y RLS. **Sin rama `app_gov_can_see`**: ver vídeo no
      es ver telemetría (`B.4`); precedente de omitirla, `privacy_notices`.
- [x] Los clips **no van en `evidence_objects`**: su `CHECK` de `kind` no los admite, y esa tabla
      es `COMPLIANCE_ANCHOR` — heredarían la exención de poda que `B.4` prohíbe.
- [x] `cctv_clips` con el patrón de **dos triggers** de `life_checkins`: `forbid_update_delete()`
      solo en `DELETE`, y un `cctv_clip_purge_guard()` solo en `UPDATE` que abre una rendija
      (`s3_key → NULL` + `purged_at`).
      > **La rendija exige la TRANSICIÓN REAL**, no solo que el resto de la fila no cambie:
      > `restore_check._updatable_column` ejerce un `UPDATE ... SET c = c` y espera que el guard lo
      > **rechace**. Comparar `to_jsonb` menos dos columnas acepta ese no-op y el verificador lee
      > «ACEPTADO (la guarda no existe o está desactivada)».
- [x] `REVOKE DELETE ON cctv_clips FROM takab_app` — `test_append_only_dos_capas.py` lo exige por
      derivación, no por gusto.
- [x] **Las credenciales de la cámara NO viven en la tabla.** La URL RTSP/ONVIF lleva usuario y
      contraseña embebidos y el detector de PII **no la reconoce**: es una fuga que ningún censo
      puede ver. `cameras` guarda host, puerto y perfil; la credencial va por entorno.
- [x] La key es `evidence/{tenant_id}/{event_uuid}/cctv-{desde}_{hasta}-{sha256}.mp4` —con la
      **ventana dentro**, porque quien registra el objeto es la notificación de S3 y solo ve la
      key— y el prefijo `evidence/` **es una restricción,
      no estética**: el bucket solo notifica el prefijo `evidence/`; una key bajo `cctv/…` aterriza
      y no la ingesta nadie.
- [x] Subida por el grant que ya existe (`mode` nuevo en `BackfillRequest`), **sin topic MQTT
      nuevo**: un topic no autorizado en la política fleet desconecta al gabinete en cada publish.
- [x] El vídeo **nunca por MQTT** (el clasificador de la regla de oro 9 rechaza binario sin tope) y
      **nunca a través de `takab-edge`**: PUT presignado directo desde `takab-cctv`.
- [x] La salida de vídeo deja fila en `audit_log` **en la subida**, no solo en la descarga
      (`D-14`: auditada igual que un comando de actuador).

### [ ] T-3.11.c · El worker de backfill **no está en la nube desplegada** — `SOFTWARE` + `GATE-AWS`
> **Descubierto el 2026-09-01**, revisando qué le falta al CCTV para existir fuera de los tests.
> `deploy/cloud/docker-compose.yml` levanta siete servicios —`api`, `ingest-events`,
> `ingest-telemetry`, `incident-engine`, `notify`, `commands`, `console`— y **ninguno corre
> `python -m takab_api.backfill`**. `git log -S backfill` sobre ese fichero no devuelve nada:
> no es que se quitara, es que **nunca estuvo**. El propio módulo dice de sí mismo que «corre
> CO-LOCADO con los demás workers desde la MISMA imagen», y `deploy.sh` le exporta sus dos
> variables (`TAKAB_API_QUEUE_URL_BACKFILL`, `TAKAB_API_DLQ_URL_BACKFILL`) — o sea que hay
> **entorno preparado para un proceso que nadie arranca**, que es justo lo que hace creíble
> lo contrario.
>
> ### Lo que rompe, y es más que el CCTV
> La cola `takab-dev-q-backfill` recibe **dos** cosas distintas, y ninguna tiene consumidor:
>
> 1. **Las peticiones de grant del gabinete** (`takab/backfill/request/+` → regla IoT → cola),
>    o sea el permiso de subida. Sin él el clip no llega ni a empezar.
> 2. **La notificación de S3** del prefijo `evidence/`, que es la única que ve la key y por
>    tanto la única fuente de la ventana del clip (`T-3.11.b`).
>
> ### Y no falla: se queda quieto
> Los mensajes **no acaban en la DLQ** —nadie los recibe, así que no hay `maxReceiveCount` que
> agotar—: envejecen y expiran. La alarma `dlq_depth` vigila la DLQ, y la DLQ está vacía
> porque el camino se corta antes de llegar a ella. Es la misma familia de la alarma
> `iot-rule-errors` y del gabinete fantasma: **la ausencia no dispara nada**.
>
> ### Lo que este hallazgo NO afirma
> No dice que el backfill de evidencia nunca haya funcionado en la nube: eso no se puede saber
> sin credenciales y sin mirar la cola, y el token SSO estaba caducado al escribirlo. Dice lo
> que sí se lee en el repo — **no hay quién lo corra**, y el `docker compose up
> --remove-orphans` de `takab-cloud.service` mataría cualquier contenedor lanzado a mano.
- [ ] Servicio `backfill` en `deploy/cloud/docker-compose.yml` con
      `entrypoint: ["python", "-m", "takab_api.backfill"]` y **`db-ingest.env`, no `db-app.env`**:
      escribe filas de todos los tenants y con el DSN de `takab_app` la RLS forzada se lo negaría
      (el invariante de tenancy que el propio compose declara en su cabecera).
- [ ] **Un test que cuente consumidores, no que lea este YAML.** La regla a defender es *toda
      cola que `deploy.sh` exporta como `TAKAB_API_QUEUE_URL_*` tiene un servicio que la
      consume*. Escrita así caza también la próxima cola que se añada — que es exactamente cómo
      llegó ésta, y cómo estuvo a punto de llegar la del CCTV.
- [ ] Verificar **en la nube, no en el YAML**: `ApproximateNumberOfMessages` bajando y una fila
      nueva en `evidence_objects`. Un `docker compose ps` con el servicio arriba demuestra que
      arrancó, no que consuma.
- [ ] El redespliegue va con la ventana AWS — fichado en
      [`PENDIENTES-MAURICIO §2.11`](PENDIENTES-MAURICIO.md).

### [x] T-3.12 · Motor de conteo y analítica de evacuación — `SOFTWARE` · **COMPLETA (2026-08-30)**
> **Construido el 2026-08-30** (`analyzer/`, 48 tests, cero pesos descargados). El motor de
> métricas es aritmética pura sobre la serie de aforo y está entero.
>
> **El E2E del simulador corrigió una premisa del CLI:** `--clip` y `--stills` no son
> alternativas, **se suman**. El clip cubre la salida (`t50`/`t90`) y el goteo el reingreso,
> y cada uno por su cuenta daba cifras que *parecían* correctas — medido: con solo el goteo
> `t90` salía **600 s**, y fusionando las dos series, **180 s**. Un número que describía una
> evacuación de diez minutos cuando fue de tres.
>
> Abierta por dos cosas, y las dos a propósito: el **pre/post-proceso del backend ONNX**
> (letterbox y decodificado de salida) se fija con el modelo que gane `T-3.12.d` —fijarlo
> antes sería elegir por opinión, que es lo que la ficha prohíbe— y la **descarga desde
> MinIO** está cableada pero no ejercida: hace falta un clip y un ffmpeg LGPL, que esta
> máquina no tiene.
>
> **La curva es la medida; el cruce de línea no.** Todo lo que el reporte necesita sale del
> conteo por fotograma en la zona, que no exige seguir a nadie entre fotogramas. El conteo
> direccional daría entradas y salidas por separado y es mucho más frágil: exige un tracker
> calibrado contra ESA escena, que es exactamente lo que mide `T-3.12.d`.
- [x] El aforo por cámara y el check-in de vida se **cruzan**, no se suman: son dos
      estimaciones distintas de la misma cosa y la diferencia es la información útil.
- [x] La discrepancia se muestra como discrepancia, nunca promediada en un número único.
- [x] Métricas: `t50`/`t90` desde la señal (**`t90` es «cuánto tardó en salir la mayor parte»**),
      aforo pico, inicio del reingreso con histéresis, latencia hasta el dictamen firmado y
      latencia del reingreso.
- [x] **Una `latencia_reingreso` negativa significa que la gente reentró ANTES del dictamen.** Eso
      no es un número: es un hallazgo de seguridad, y el reporte lo dice con palabras.
- [x] «Cuánto se movió el inmueble» sale del **sismómetro** (`incidents.max_pga_g`/`max_pgv_cms`),
      no de la cámara, y se presenta al lado de `t90`.
- [x] Detector tras un adaptador `DetectorBackend`; **solo licencias permisivas** (YOLOX / D-FINE
      Apache-2.0, ByteTrack de Megvii MIT, `onnxruntime` MIT). Mismo pre/post-proceso en borde y
      nube para que los números sean comparables.
      > **Cerrado con `T-3.12.d`** (2026-08-30): el letterbox y el decodificado de la rejilla
      > viven en el adaptador COMPARTIDO, no dentro de cada backend, que es lo que hace que los
      > números del borde y de la nube sean comparables el día que el borde cuente.
- [x] **El motor vive fuera de `api/src/takab_api/`** (paquete `analyzer/`): `test_runtime_deps.py`
      obliga a que todo import de terceros bajo ese árbol entre en `[project] dependencies`, y un
      `import onnxruntime` ahí metería el runtime ONNX en la imagen de la API.
- [x] Corre en local con un backend falso y **cero descargas de pesos en CI** — por
      `--stills`, que lee el goteo del gabinete y **no necesita ffmpeg**. Ese modo no es una
      comodidad de prueba: el clip cubre once minutos y **el reingreso ocurre horas después**,
      en el goteo, así que un analizador que solo leyera vídeo no podría fecharlo nunca.
      > ### La descarga desde MinIO, EJERCIDA por primera vez el 2026-08-30 — y estaba rota
      >
      > Esta viñeta llevaba meses diciendo «cableada y **sin ejercer**: falta un clip y un
      > ffmpeg LGPL». Con las dos cosas ya en la mano —un clip real cosido de tres segmentos
      > de la cámara del sitio y el ffmpeg LGPL— se ejerció, y no estaba solo sin ejercer:
      > **estaba rota**. `boto3` **no estaba declarado en ninguna dependencia del analizador**.
      >
      > No se veía porque `capturas.descargar` lo importa de forma perezosa, así que el fallo
      > solo aparece en el único camino que nadie había recorrido. Y el Lambda no lo notaba
      > porque su Dockerfile instalaba `boto3` a mano — o sea que la imagen tapaba un hueco del
      > paquete. Ahora es el extra `s3` y el Dockerfile pide los extras **por nombre**.
      >
      > Verificado de punta a punta: `--clip s3://…` contra MinIO, 11 fotogramas decodificados,
      > YOLOX-nano real, y las métricas saliendo con sus literales de ausencia.

### [x] T-3.12.b · Lambda contenedor del conteo — `SOFTWARE` + `GATE-AWS` · **COMPLETA (2026-08-30)**
> **DESPLEGADA Y VERIFICADA EN LA NUBE el 2026-08-30.** La API corre `1e7bf0f` con esquema
> `0053_cctv`, el Lambda arranca en **477 ms** y el worker tiene la URL de `takab-dev-q-cctv`.
>
> **Verificado invocándolo, no mirando que exista:** con un `clip_id` inventado devuelve
> `AnalisisImposible: no hay clip … en la base`. Ese error —y no `UndefinedTable`, ni un
> timeout— es la prueba de que la imagen arranca, los imports cargan, la VPC y el SG dejan
> hablar con Postgres, y la consulta encuentra la tabla. Solo le falta un clip de verdad.
>
> **El default es YOLOX-nano, y es PROVISIONAL con esa palabra escrita.** No sale de una
> opinión: sale de lo medido contra la cámara real —**8–13 ms** por fotograma contra 24–38
> del `tiny`, y **11 de 12** fotogramas correctos— pero **no contra la escena definitiva**.
> `T-3.12.d` lo confirma o lo sustituye, y sustituirlo es cambiar una variable de entorno
> más la imagen; la arquitectura no depende de cuál gane.
>
> **Tres decisiones que quedan escritas porque costaron pensarlas:**
>
> 1. **El disparo NO es una notificación de S3.** El prefijo `evidence/` ya tiene una hacia
>    la cola de backfill, y S3 **rechaza filtros solapados**: colgar el Lambda de
>    `evidence/*.mp4` habría roto la ingesta del miniSEED. Dispara el worker, en el mismo
>    punto donde audita el egreso —cuando su `INSERT … RETURNING` dice que la fila es
>    NUEVA—, y así hereda gratis la idempotencia frente a las reentregas de SQS.
> 2. **El modelo y el ffmpeg van HORNEADOS en la imagen.** Un número que acaba en un
>    dictamen tiene que poder atribuirse a una versión exacta del modelo, y un peso que se
>    baja al vuelo no permite decir cuál era. El coste aceptado: imagen más pesada y
>    redesplegar para cambiar de modelo — que es justo lo que debe ser un acto deliberado.
> 3. **El Lambda va DENTRO de la VPC**, porque Postgres solo acepta al SG de workers. Al
>    entrar pierde la salida a internet, y no la necesita: S3 entra por el VPC endpoint que
>    ya existe y el modelo viaja horneado.
>
> ### ⚠️ CORRECCIÓN (2026-09-01) — «el worker tiene la URL» era verdad, y no bastaba
>
> `TAKAB_API_CCTV_QUEUE_URL` sí está en `cloud.env`, y lo lee todo servicio que lo cargue. Lo
> que no se comprobó es **quién ejecuta el código que la usa**: `_encolar_analisis` vive en
> `backfill/objects.py`, y **el worker de backfill no existe en el compose de la nube**
> (`T-3.11.c`). El Lambda está desplegado, arranca y contesta — y **nadie va a invocarlo**
> hasta que ese servicio exista.
>
> **Comprobé la variable, no el proceso.** Una variable presente en un contenedor que nunca
> entra en esa rama es exactamente tan útil como no tenerla, y se lee igual de verde.
- [x] Imagen ECR, rol IAM y acceso a la base. **El `terraform validate` pasa**; el `apply` es
      la ventana AWS de Mauricio. El módulo va detrás de `cctv_analyzer_enabled` (default
      `false`) porque la imagen tiene que existir antes: primer apply crea el repo, se
      empuja la imagen, segundo apply enciende el Lambda con un tag **inmutable**.
- [x] El bloqueo es **solo el ejecutor**: la notificación S3 ya existe y ya enruta, así que el
      camino hasta «clip subido y registrado» funciona sin tocar AWS. Un gabinete con cámara
      deja evidencia descargable antes de que exista el Lambda.
- [x] Con el análisis pendiente el reporte dice **«CLIP DISPONIBLE · ANÁLISIS PENDIENTE»**
      (ya lo traía `T-3.12.c`). **Un fallback no puede ser `ok`**, y un cero inventado es peor
      que un hueco declarado. El handler es coherente con eso: **si falta algo, LANZA** y el
      mensaje acaba en la DLQ, en vez de escribir métricas a medias que nadie podría
      distinguir de las buenas.
- [x] El peso se descarga con **`sha256` verificado** (`make cctv-modelo`) antes de entrar al
      contexto de build. Probado en las dos direcciones: acepta el peso real y **rechaza uno
      alterado en un byte**.
- [ ] **El `apply` y la primera ejecución real.** Sin ellas no hay medición de arranque en
      frío ni de coste — y esas dos cifras no se estiman aquí, se miden cuando exista.

### [x] T-3.12.c · API, sección del reporte y panel de la consola — `SOFTWARE` + `FRONTEND` · **COMPLETA (2026-08-30)**
> Endpoint, dos permisos de vídeo, sección 11 del dictamen y panel en EVALUACIÓN. Hasta hoy
> las métricas se calculaban y no las veía nadie.
>
> El `410` de un clip podado es el detalle que más se pensó: un `404` diría «nunca hubo
> nada», que es falso y **borra la cadena de custodia**. Y la guarda del bucket va DESPUÉS
> de esa comprobación, o «la retención se lo llevó» se leería como «el servicio no está
> disponible» — que manda a mirar la infraestructura en vez de la política.
- [x] Dos acciones RBAC: `cctv_read` (métricas y capturas) y `cctv_video` (**ver y descargar el
      clip**, más estrecha y auditada en cada acceso). El CRUD de cámaras reutiliza `manage_fleet`.
      Espejar en `RBAC-TAKAB.md`: el test de paridad compara **celda a celda**, y `DENY_ALL` se
      compara por igualdad.
- [x] Endpoint de lectura que sirve **el mismo objeto** a la pantalla y al PDF (disciplina de
      `routers/forensics.py`); 404 y nunca 403 fuera de alcance.
- [x] Sección nueva del reporte técnico con las **cuatro capturas** —antes de la señal, saliendo,
      aforo máximo, reingresando— y las métricas. Literal de ausencia propio: sin cámara declarada
      el reporte lo dice, no pinta un cero.
- [x] Las capturas se proyectan en la cadena de custodia conservando `sha256` y fecha **después**
      de que el objeto se pode: la fila dice `PURGADO (retención de vídeo)`. El hecho sobrevive, la
      imagen no.
- [x] **Una sola superficie de CCTV, y es la de triage.** El card de la consola
      (`DetailPanel.tsx`) es *verificación visual en vivo* y **no se toca** en esta ficha: su línea
      de deuda en `serverDataCensus` sigue siendo verdad mientras no exista vista en vivo.
- [x] El panel nuevo cablea las cuatro entradas de `StateFrame` **incluida `staleSince` de verdad**
      (`FRESCURA_CLAVADA` está vacía por igualdad) y entra en la lista de marcos de la página de
      triage, que está escrita a mano y comparada por igualdad.

### [ ] T-3.12.d · Comparativa de detectores contra la cámara real — `SOFTWARE` + `GATE-HW`
> **La cámara ya está en la red** (`192.168.3.132`, LC/Dahua `IPC-S41FE`) y su interrogatorio
> ONVIF dejó dos cifras que cambian **qué** hay que medir aquí, no solo cuándo:
>
> 1. **El conteo va a ocurrir sobre 640×480, no sobre 4 MP.** `CctvConfig.perfil` es
>    `substream` de fábrica, y el substream de esta cámara es **640×480 @ 15 fps**. El
>    razonamiento escrito en el campo —«grabar el principal multiplica por ocho el disco sin
>    mejorar un conteo que ni siquiera ocurre aquí»— da por supuesto que a 640×480 se cuenta
>    igual de bien. **Eso es precisamente lo que esta ficha tiene que medir**, y hasta que lo
>    mida es una opinión. (De paso: el múltiplo medido en esta cámara es **3×** por bitrate
>    —1536 contra 512 kbps—, no ocho.)
> 2. **El goteo está clavado a 640×480 pase lo que pase.** El endpoint de instantánea
>    devuelve 640×480 **también con `subtype=0`**: pedirle el perfil principal no sube la
>    resolución. Y el goteo no es un extra — es lo único que fecha el **reingreso**, que
>    ocurre horas después del clip. Así que la resolución del goteo **no es negociable
>    subiendo `perfil`**: si a 640×480 no se cuenta, hace falta otra vía (sacar el fotograma
>    del RTSP principal y decodificar) y eso tiene un coste que hay que medir aquí.
>
> Consecuencia práctica: la comparativa necesita **dos** columnas de resolución, 640×480 y
> 2560×1440, o su conclusión no se puede aplicar al goteo.
> ### El pipeline ya está construido y ejercido contra la cámara real (2026-08-30)
>
> Lo que estaba en `NotImplementedError` esperando a esta ficha —`_preparar` y `_a_cajas`— ya
> existe, con `imagen.py` para decodificar el JPEG **con ffmpeg por subproceso** en vez de
> añadir Pillow u OpenCV (que además empaqueta su propio FFmpeg, sin auditar por `D-24`).
>
> **La trampa que costó la tarde, y que ninguna prueba habría cazado:** el export oficial de
> YOLOX **no decodifica dentro del grafo**. Sus `xywh` salen como offsets crudos —medido, en
> rango `-2…3`— y hay que aplicar `xy=(crudo+centro)·paso`, `wh=exp(crudo)·paso`.
> Interpretarlos directamente da **cero detecciones sin un solo error**, y un cero se lee como
> un punto de reunión vacío. Por eso `numpy` se movió al **núcleo** del paquete: estas cuentas
> tienen que probarse en CI, y detrás del extra no se probaban. La frontera del job sigue
> diciendo lo mismo —sin runtime de inferencia y sin un solo peso.
>
> **Verificado de extremo a extremo** contra 12 fotogramas reales con una persona caminando:
> 11 de 12 dan exactamente 1, el `nms()` del árbol colapsa ~1100–1600 cajas crudas a una, y
> el CLI completo produce el JSON del reporte degradando con honestidad.
>
> **Y el ángulo resultó ser código, no solo instalación.** `Caja.pies` —el borde inferior—
> supone cámara frontal. Con cámara **cenital** ese borde es el hombro más lejano del centro
> óptico, no los pies, y usarlo empuja a todo el mundo hacia un lado del encuadre: un error
> **sistemático**, que es el que parece una medición. De ahí `Montaje` y `Caja.ancla()`.
- [ ] Candidatos **solo permisivos**: YOLOX-nano, YOLOX-tiny, RF-DETR nano, EfficientDet-Lite0.
      **Sin línea base de Ultralytics** en ningún entorno — tampoco «solo para comparar».
      > **Bajados y ejercidos: YOLOX-nano y YOLOX-tiny** (Apache-2.0). Los dos comen `416×416`
      > y emiten `[1,3549,85]`, así que **comparten decodificador**. Faltan RF-DETR nano y
      > EfficientDet-Lite0, que sí traen post-proceso propio.
- [x] **El coste medido, y desmiente el enunciado anterior de esta ficha.** En x86-64:
      `yolox_nano` **8–13 ms/fotograma**, `yolox_tiny` **24–38 ms**. La resolución de la
      cámara **casi no mueve el coste** porque los dos modelos comen `416×416` pase lo que
      pase. O sea que la columna de coste es **plana**: lo que cambia con la resolución no es
      el precio, es **cuántos píxeles le tocan a una persona lejana**. Las dos columnas de
      resolución siguen haciendo falta, pero para medir **precisión**.
- [x] **El primer dato de precisión, y es un falso positivo.** Con una persona caminando,
      **2 de 12 fotogramas** trajeron un fantasma: una **sudadera colgada de una silla**, con
      `0.36` contra un `CONFIANZA_MINIMA` de `0.35`. En un punto de reunión hay mochilas,
      chamarras y sillas — **ese es el modo de fallo**, no una rareza. Queda como la medición
      que tiene que repetirse en la escena real.
- [ ] **PENDIENTE MEDIR: el recall y la tasa de falsos positivos con varias personas.**
      Hoy solo hay una medición con **una** persona: 11 de 12 fotogramas correctos y **2 de 12
      con un fantasma** (una sudadera colgada de una silla, `0.36` contra un umbral de `0.35`).
      Falta lo que solo sale con gente: **cuánto baja el conteo cuando unas personas tapan a
      otras**, y si el umbral de `0.35` aguanta en una escena con mochilas y chamarras. **No
      hay forma de conseguir más personas para la prueba ahora mismo** — por eso queda
      fichado y no simulado: inventar la cifra sería peor que no tenerla. Va también a
      [`PENDIENTES-MAURICIO §3.3.d`](PENDIENTES-MAURICIO.md): lo que falta es **gente**, no
      código, y un pendiente que solo vive en el backlog de software no lo lee quien puede
      resolverlo.
- [ ] **Lo que NO se puede cerrar sin el sitio**, y por eso va al runbook de alta y no aquí:
      la precisión contra el punto de reunión, con gente y con el montaje definitivo. Ver
      [`runbooks/RUNBOOK-alta-de-camara-cctv.md`](runbooks/RUNBOOK-alta-de-camara-cctv.md),
      que es **por gabinete** y no una sola vez.
      > **Y una advertencia que sale de la decisión de producto de no entrenar por sitio:** los
      > modelos COCO aprendieron «persona» de fotos a la altura de los ojos. **El cenital es el
      > peor caso** para ellos y no se arregla con configuración. La mitigación es el montaje
      > —picado de 20°–40°—, y está escrita en el paso 1 del runbook.
- [ ] **La medición fija el default, no la opinión.** Precisión de conteo y coste, contra la cámara
      real y su escena real; una comparativa contra vídeo de internet no dice nada de este edificio.
- [ ] Medir a **640×480** (el substream y el goteo) **y** a **2560×1440** (el principal). Si el
      default `perfil=substream` no sostiene el conteo, esta ficha es la que lo deroga con la
      cifra delante — y arrastra la resolución del goteo, que no se arregla cambiando `perfil`.
- [ ] **La escena tiene que ser la del punto de reunión.** Hoy la cámara está en el banco, no
      apuntando al punto: una comparativa hecha desde donde está ahora mide el detector, no el
      edificio, y esta ficha existe para medir el edificio.

## Fase 3.3 · Feeds y superficie de datos

### [ ] T-3.13 · Feed CIRES/SSN en vivo — `SOFTWARE` (soft-gate)
- [ ] Enriquece; **jamás gatea** el camino SASMEX (decision-gate #8: "lo mejora, no lo
      bloquea").
- [ ] Caída del feed ⇒ degradación visible, no silenciosa.

### [x] T-3.14 · Duración instrumental de la sacudida — `SOFTWARE` · **COMPLETA (2026-08-30)**
> **La definición no se eligió por gusto: la eligieron los datos.** Hay dos familias y una
> queda descartada de raíz:
>
> * La **«bracketed»** —tiempo entre el primer y el último cruce de un umbral, típicamente
>   0.05 g— es la que la gente espera, y **no se puede calcular aquí**: exige unidades
>   absolutas, y lo que archivamos son **cuentas del ADC sin calibrar**. Convertirlas a `g`
>   necesita la respuesta instrumental, que este servicio no tiene — lo dice el propio
>   lector de miniSEED. Calcularla igualmente sería inventarse el umbral.
> * La **significativa D5-95** (Trifunac & Brady, 1975) es el intervalo en el que se acumula
>   del 5 % al 95 % de la **Intensidad de Arias** (`∫a²dt`). Y aquí está lo que decide:
>   **es una FRACCIÓN, y una fracción es invariante de escala** — el factor de calibración
>   se cancela al normalizar. O sea que D5-95 se mide **exacta sobre cuentas crudas**.
>
> No es el premio de consolación: es la definición estándar en ingeniería sísmica para
> «cuánto duró la parte que importa», y además la única honesta con los datos que hay.
>
> **Y la trampa que la habría hecho inútil, medida:** el waveform del RS4D trae ~3.8 millones
> de cuentas de continua. Con ese offset dentro, `∫a²dt` lo domina una constante y D5-95
> devuelve **el 90 % de la ventana sea cual sea el sismo**. Verificado sobre una traza de
> 95 s con 15 s de sacudida: **85.5 s sin quitar la media contra 13.5 s con ella**. El
> número saldría, parecería razonable, y describiría la longitud del registro.
- [x] Medida, no estimada: sale de la onda archivada del propio evento, no de una correlación
      con la magnitud ni de una tabla.
- [x] **Con su definición escrita, y pegada al número.** El reporte nunca dice «duración» a
      secas: dice `D5-95` y declara que **no es comparable con una bracketed**. Un número sin
      su definición invita a compararlo con otro medido de otra forma.
- [x] Se mide sobre el **mismo canal que el espectro** — el dominante—, no sobre el que más
      sacudió: dos figuras del mismo dictamen que describieran trazas distintas serían una
      trampa para quien las compare.
- [x] **Cuando no se puede medir devuelve ausencia, no cero.** Un `0.0 s` en un dictamen se
      lee como «no tembló», y lo que pasó fue que no hubo traza. El PDF lo dice con palabras:
      «SIN DATO · no se pudo medir sobre la onda archivada. No es cero».
- [x] Vive en la nube y no en el gabinete: la nube **ya** se baja el miniSEED del evento y
      **ya** tiene lector propio para el dictamen (`dictamen/mseed.py`, escrito para no
      arrastrar ObsPy). Cero dependencias nuevas, cero carga añadida al edge, y resolución
      completa de 100 sps en vez de la de 1 Hz de las features.

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

## BLOQUE VI · V1-DEMO — lo que hace falta para poder enseñarlo

**Por qué existe este bloque, y por qué no está en ninguno de los cinco anteriores.** Los Bloques
I a V ordenan el camino hacia **un cliente con un edificio protegido y un documento firmado**.
Este ordena otra cosa: el camino hacia **poder enseñar el producto sin que una pantalla afirme lo
que nadie acreditó**. Son rutas distintas y conviene no confundirlas — una demo no necesita que la
sirena suene con el gabinete apagado; necesita **no afirmar que lo hace**.

Sale entero de la auditoría del **2026-09-02** ([`INFORME-V1-COMERCIAL.md`](INFORME-V1-COMERCIAL.md),
plan en [`PLAN-V1-COMERCIAL.md`](PLAN-V1-COMERCIAL.md)): 52 ítems, 10 verdes, 23 amarillos, 19
rojos. Ocho de sus hallazgos **no llevan ficha nueva** porque caen sobre tareas ya abiertas; se
citan en §4 de aquel plan y se quedan donde están.

**Este bloque no espera a ningún gate para empezar**, y esa es su propiedad interesante: de sus 27
fichas, **23 son `SOFTWARE` puro**. La ruta crítica de V1-DEMO son cinco —`T-5.01`, `T-5.02`,
`T-5.03`, `T-5.04` y `T-5.05`— y **ninguna está bloqueada en una persona**.

**El único cruce a otro bloque, escrito aquí para que se vea al planificar:** `T-5.23`
(espectrograma en el dictamen pericial) **depende de `T-3.11.c`**, del Bloque IV — sin el worker
que archiva la onda cruda desplegado en la nube no hay nada que transformar. Es la razón de que
esa ficha vaya en la tercera tanda y no antes. Ninguna otra ficha del bloque sale de él.

## Fase 5.0 · V1-DEMO — que nada de lo que se enseña afirme lo que no se acreditó

> **De dónde sale esta fase.** De la auditoría del **2026-09-02**
> ([`INFORME-V1-COMERCIAL.md`](INFORME-V1-COMERCIAL.md), plan en
> [`PLAN-V1-COMERCIAL.md`](PLAN-V1-COMERCIAL.md)). 52 ítems auditados: 10 verdes, 23 amarillos,
> 19 rojos.
>
> **Qué NO es esta fase.** No es "terminar el producto". Es el conjunto mínimo para que TAKAB
> Ailert se pueda **enseñar y vender** sin que una pantalla afirme algo que nadie acreditó. La
> ruta al primer cliente sigue siendo la de §"RUTA CRÍTICA", y sigue estando en manos de humanos
> con agenda. **Esta no**: de sus 27 fichas, 23 son `SOFTWARE` puro.
>
> **La ruta crítica de V1-DEMO son cinco fichas** —`T-5.01`, `T-5.02`, `T-5.03`, `T-5.04`,
> `T-5.05`— y **ninguna espera a nadie**. Es la diferencia entre *acreditar* y *no mentir*: una
> demo no necesita que la sirena suene con el gabinete apagado, necesita **no afirmar que lo
> hace**.

### [x] T-5.01 · En modo demo los botones **mandan órdenes de verdad** — `SOFTWARE` · **CERRADA 2026-09-02**
> **Verificado abriendo el archivo, no leyendo una ficha.** `edge/takab_edge/local_api/index.html`
> — `doAction()` ejecuta `fetch(endpoint, {method:'POST', headers})` **sin comprobar `DEMO`**. El
> único `if (!DEMO)` del flujo se salta el refetch de estado, nada más. Y `renderActions()` pinta
> `PROBAR ACTUADORES` —cuyo propio subtítulo dice *"sostiene sirena+estrobo · pulso en gas,
> ascensores, puertas"*— **incondicionalmente**, además de decidir **qué** botones aparecen a
> partir del estado FALSO de la escena: con `?demo=alerta` salen `SILENCIAR AUDIBLES` y
> `CERRAR ALERTA` porque la escena sintética dice que la sirena suena.
>
> Mientras tanto, arriba, la cinta afirma `DEMO · NO ES ESTADO REAL`.
>
> **Es la familia de defecto que este proyecto ya conoce** —una superficie que dice "bien" cuando
> quiere decir "no sé"— pero llevada un paso más lejos: aquí la superficie dice *"nada de lo que
> ves es real"* al lado de un botón que sí lo es. El servidor tampoco defiende: `?demo=` es un
> parámetro del navegador y los handlers no saben de él.
>
> **Y es el escenario exacto de una exposición comercial**, que es lo que lo pone el primero de
> la lista.
- **Componente:** edge (panel LAN) · **Depende de:** nada · **Prioridad: MÁXIMA**
- **Objetivo:** que con `?demo=` puesto ninguna acción alcance al gabinete, y que la pantalla lo
  diga en el propio botón en vez de solo en la cinta.
- **Criterios de aceptación:**
  - [x] `doAction()` se niega con `DEMO` puesto: no emite `fetch`, y el mensaje de la caja del PIN
        dice por qué (algo como `MODO DEMO · LAS ÓRDENES ESTÁN INHIBIDAS`).
  - [x] `renderActions()` **no pinta** botones de actuación en demo, o los pinta visiblemente
        inertes. La decisión de cuál de las dos se toma en la ficha, se escribe con su razón.
  - [x] Un test que **cuente peticiones**, no que lea prosa: con cada escena de demo, pulsar cada
        botón produce **cero** `fetch` a `api/*`. Que el conteo esperado sea cero se declara en
        voz alta para que el test no pueda pasar por vacuidad.
  - [x] El test cubre las cinco acciones alcanzables desde una escena de demo, enumeradas
        **derivándolas de `renderActions`**, no a mano.
  - [x] Sin `?demo=` nada cambia: los mismos botones siguen mandando sus mismas órdenes (guarda
        anti-prohibir-de-más).
- **Cómo se cerró (2026-09-02).** **Decisión: se PINTAN, inertes** — no se esconden. La razón:
  `?demo=` existe para enseñar cómo se ve el panel en estados que no se pueden reproducir a
  voluntad, y un panel sin sus botones no se parece al real; esconderlos sería mentir en la otra
  dirección. La honestidad es que sigan ahí, con borde discontinuo y el subtítulo
  `INERTE EN DEMO`, y que la orden no salga.
  **Lo que midieron los tests al escribirlos primero, y agranda el hallazgo de la auditoría:**
  el defecto no era un camino teórico — **las doce escenas de demo mandaban entre 2 y 4 órdenes
  reales cada una** al gabinete que las pintaba.
  **Y lo que apareció al arreglarlo:** `doAction` es el **único** camino del panel que hace
  `POST`, en unas 2 400 líneas. Eso convierte la guarda en estructural en vez de disciplinaria,
  y hay un test que lo exige por conteo: un segundo `POST` en otro sitio la esquivaría y sale
  rojo con su número de línea.

### [x] T-5.02 · **Modo demostración de sistema** — `SOFTWARE` + `DECISIÓN` · **CERRADA 2026-09-02**
> Hoy no existe. Nada bloquea push, SMS, WhatsApp, correo, comandos firmados ni apertura de
> incidentes, y ninguna pantalla del SOC ni de la app lo declararía si existiera. Lo que hay son
> tres cosas parciales que no lo son: el `?demo=` del panel (que es un reproductor de escenas —
> ver `T-5.01`), el modo demo del SOC que **se retiró a propósito**
> (`web/src/styles/soc.css:787`: *"una consola de operación real no lleva controles de
> demostración"*, y la razón sigue siendo buena), y el estado `simulated` de notificaciones, que
> es **derivado de la ausencia de credenciales** y por tanto **desaparece justo en el entorno
> donde se haría la demo**.
>
> **Sin esto, cada exposición es un riesgo de disparar algo real o de enseñar datos falsos sin
> etiquetar.** Con las credenciales de notificación puestas —que es lo que se busca— el riesgo
> deja de ser teórico.
>
> **Lo que hay que decidir antes de construir**, y por eso la ficha lleva `DECISIÓN`: (a) el
> alcance del modo, ¿por tenant, por sesión o por despliegue?; (b) quién puede encenderlo y
> apagarlo; (c) si un incidente **real** que entra con el modo puesto lo apaga solo —que es la
> lectura coherente con *"lo real gana"* de los simulacros— o si el modo lo impide y grita.
- **Componente:** api + web + mobile + edge · **Depende de:** T-5.01 · **Prioridad: MÁXIMA**
- **Objetivo:** un estado explícito, visible y auditado, en el que el sistema no despierta a
  nadie, no cierra un relé y lo anuncia en las tres superficies.
- **Criterios de aceptación:**
  - [x] Decisión escrita en `DECISIONES-MAURICIO.md` **con su razón** antes de la primera línea de
        código, cubriendo los tres puntos de arriba.
  - [x] Con el modo activo: cero entregas por cualquier canal, cero comandos firmados emitidos,
        cero relés movidos. Cada intento **deja fila en `audit_log`** con el motivo — un modo que
        bloquea en silencio es otra superficie muda.
  - [x] Las tres superficies lo declaran de forma inconfundible y **distinta del simulacro**: el
        ámbar ya significa "simulacro sonando" y los dos no pueden confundirse.
  - [x] Encender y apagar el modo queda auditado con actor y hora.
  - [x] El bloqueo se **deriva** del registro de proveedores y de la superficie única de comandos,
        no de una lista de canales escrita a mano — un canal nuevo tiene que quedar bloqueado
        solo.
  - [x] Test de no-vacuidad: con el modo apagado, los mismos escenarios sí entregan y sí comandan.
- **Cómo se cerró (2026-09-02), y DOS criterios cambiaron al construirlos.** Las tres decisiones
  están en [`D-27`](DECISIONES-MAURICIO.md#d-27), escritas antes de la primera línea de código:
  **por cliente y con vencimiento** (máx. 8 h, el techo en el CHECK de la tabla y no en el
  código); **lo enciende el dueño de la plataforma, lo apaga él o el administrador del cliente**
  —asimétrico: difícil de volver inseguro, fácil de volver seguro—; y **lo real lo apaga**, con la
  lectura contraria rechazada sin discusión: un modo capaz de suprimir una alerta real no es un
  dispositivo de seguridad.
- **Lo que cambió (1): «cero entregas por cualquier canal» era más ancho de lo que puede ser.**
  Lo destapó un test. Como *cualquier* incidente apaga el modo antes de planificar sus avisos, el
  modo **no puede suprimir la cascada de un incidente nuevo** — y eso es correcto, no una
  limitación: si pudiera, un quórum de pánico de ocupantes reales quedaría callado. Lo que el modo
  sí suprime, y era lo importante, son los **comandos firmados** (simulacros, prueba de actuadores,
  actuación por quórum): los actos del que demuestra. La puerta de notificación se queda como
  **respaldo que no debería dispararse nunca**, y se refuerza con la otra mitad que ese mismo test
  obligó a escribir: **con un incidente abierto no se entra en el modo**. Con las dos reglas
  juntas, el modo y un evento vivo **no pueden coexistir**.
- **Lo que cambió (2): son DOS superficies, no tres, y el panel queda fuera a propósito.** La
  consola y la app lo declaran. El panel del gabinete **no**, y la razón está en `D-27`: meterlo
  exigiría que el modo viajara al gabinete, y cada dato nuevo que viaja hacia allí es superficie
  nueva hacia el camino de vida — que es justo lo que este modo no puede tocar. Además está
  medido: el seed de producción deja el conjunto de reglas sin clave `edge`, así que hoy el config
  sync no empuja nada al gabinete real; construirlo sería entorno preparado para un mensaje que
  nadie recibe. El panel no promete entrega de notificaciones: su silencio no es una mentira.
- **El bloqueo es derivado de verdad:** la puerta de notificación va **antes** de preguntar por el
  proveedor, así que ni siquiera consulta el registro — cubre hasta un canal sin proveedor
  cableado, y un canal sexto queda bloqueado el día que nazca. La de comandos vive en el embudo
  único que firma, así que simulacros y quórum la heredan sin duplicar la superficie sensible.
- **Y el color no es un detalle:** cian con borde discontinuo, **no ámbar**. En esa consola el
  ámbar ya significa «simulacro en curso» y «dato retenido», y un tercer significado en el mismo
  color vacía los tres. El discontinuo es el idioma compartido de las tres fichas de demostración
  —`T-5.01` (botones inertes), `T-5.02` y `T-5.05` (datos de demo)—: «esto no es real».

### [x] T-5.03 · El banner del SOC llama **alerta sísmica** a un botón de pánico — `SOFTWARE` · **CERRADA 2026-09-02**
> `web/src/features/console/ConsolePage.tsx:129` elige el incidente a destacar **solo por
> `severity === "critical"`**, y `AlertBanner.tsx` lleva **dos** textos escritos a fuego:
> `ALERTA SÍSMICA · PROTÉJASE` (`:23`) y `EDGE · RS4D · REGLAS LOCALES EJECUTADAS · ● AUTO`
> (`:39-41`). **Ninguno mira el `trigger`.**
>
> Ante un quórum de pánico —que abre incidente `trigger='manual'` con severidad crítica por
> `D-11`— el SOC afirma dos cosas falsas a la vez: que hubo una alerta sísmica, y que la ejecutó
> el sensor. La app móvil, para **el mismo incidente**, pinta `NO ES UNA ALERTA SÍSMICA`
> (`mobile/src/features/alarm/BuildingAlarmView.tsx:66`) y el push dice `ALARMA DEL INMUEBLE`.
> Lo mismo ocurre con el umbral instrumental, que la política de solo-aviso degradó y que el SOC
> sigue pintando como alerta porque su tier mapea a severidad crítica.
>
> **Es el defecto que ya se corrigió en móvil, reintroducido en el SOC**, y la lección de
> entonces vuelve a aplicar tal cual: *un componente presentacional puede llevar una mentira a
> fuego que ninguna prueba de la lógica alcanza*. La corrección de móvil vive en
> `mobile/src/features/alert/source.ts` y es el modelo a copiar: el titular **se deriva** de la
> fuente.
- **Componente:** web · **Depende de:** nada · **Prioridad: MÁXIMA**
- **Objetivo:** que el titular y la atribución del banner salgan del `trigger`, y que ninguna
  superficie pueda volver a divergir sin que un test lo diga.
- **Criterios de aceptación:**
  - [x] El titular y la línea de atribución se derivan del `trigger` del incidente, con las cuatro
        fuentes cubiertas por igualdad (no un `default` que absorba lo desconocido).
  - [x] Un `trigger` nuevo que nadie mapeó **no cae a "alerta sísmica"**: sale rotulado como
        desconocido y el build lo nombra.
  - [x] **Un test cross-superficie**: para cada `trigger`, el titular del SOC, el de la app y el
        del panel del gabinete son coherentes entre sí. Es el test que hoy no existe y que habría
        cazado esto.
  - [x] El glosario compartido de estados **incorpora el móvil** —hoy solo cubre panel y consola—
        y el eje de titulares de alerta, no solo el vocabulario de estado.
  - [x] La divergencia ya declarada en el glosario (`DATO RETENIDO` / `DATOS RETENIDOS`) se cierra
        o se re-declara con su razón.
- **Cómo se cerró (2026-09-02).** El titular y la atribución salen de
  `web/src/features/console/alertHeadline.ts`, espejo consciente del módulo del móvil, y los
  literales viven en `shared/glossary/estados.json` → `titulares_de_alerta`, con las tres
  superficies. El censo cruzado de `edge/tests/test_glosario_de_estados.py` ata ese eje al
  **CHECK de `incidents.trigger` por IGUALDAD**: el quinto trigger que alguien añada sale rojo
  con su nombre hasta que se decida cómo se llama en las tres pantallas. Se saboteó a propósito
  para comprobar que no pasa por vacuidad.
  **Tres cosas aparecieron al hacerlo.** (1) La prueba del invariante estaba escrita ALREDEDOR
  del defecto: su fixture traía `trigger: "local_threshold"` y aun así esperaba «PROTÉJASE»; se
  le puso el trigger que le corresponde y se conservó el nombre del test, que es el ancla de
  `INV-magnitud.a` en la matriz. (2) **El móvil tenía la misma grieta en su caso por defecto** —
  un trigger no mapeado titulaba «ALERTA SÍSMICA»—, corregida en las dos superficies.
  (3) **La divergencia se RE-DECLARA, no se cierra, y se encareció mientras estaba declarada:**
  donde T-2.137 midió diez aserciones en ocho ficheros, hoy son **veinticuatro en doce**. Sigue
  siendo un lote propio, y ahora se sabe que es más grande. Su `arreglo` ya no lista los ficheros:
  manda re-derivarlos, porque la lista anterior nació desactualizada.

### [x] T-5.04 · El perímetro de claims de la landing cubre **cifras**, no **capacidades** — `SOFTWARE` · **CERRADA 2026-09-02**
> `landing/tests/contenido.test.mjs:58` defiende un perímetro real y bien pensado: prohíbe cifras
> medidas y prohíbe citar normas. **No prohíbe afirmar una capacidad que nadie acreditó**, y por
> eso pasó en verde lo siguiente, hoy publicado:
>
> - *"acciona sirena, estrobo, **gas, ascensores y puertas** del inmueble"* — ningún gabinete
>   tiene esos tres canales cableados; el gabinete de referencia reporta **dos** relés. El
>   controlador que los haría está en la lista de materiales marcado **"Opcional"**, y
>   `ENTREGA-Y-ACEPTACION-TAKAB.md:214` dice que su driver es *"un extra no acreditado con
>   equipo"*.
> - *"**respaldo de energía**"* entre lo que se instala — el gabinete vivo reporta
>   `ups_status: "unknown"` y `battery_pct: null`.
>
> **Es exactamente el fallo que el propio repositorio ya cazó una vez** —el checklist de gas y
> puertas en verde sin gas ni puertas— reaparecido en la superficie más pública que tiene el
> proyecto. La landing es por lo demás notablemente honesta (su columna "No hace" es mejor que la
> de casi cualquier competidor), y eso hace más fácil, no más difícil, corregir la otra columna.
- **Componente:** landing · **Depende de:** nada · **Prioridad: MÁXIMA**
- **Objetivo:** que el sitio público no afirme en presente una capacidad cuyo gate está abierto,
  y que un test lo impida en adelante.
- **Criterios de aceptación:**
  - [x] Las dos afirmaciones se reformulan sin perder la venta: el alcance de diseño se dice como
        alcance de diseño y la acreditación por inmueble se dice como tal. La columna "No hace"
        **no se toca**: ya es correcta.
  - [x] El perímetro del test gana una regla de **capacidades**: una lista de afirmaciones que
        exigen un gate cerrado, **derivada** del censo de gates de
        `MATRIZ-REQUISITO-TEST.md`, no tecleada. Con el gate abierto, la afirmación en presente
        pone el test en rojo.
  - [x] La regla nombra el gate concreto en el mensaje de fallo, para que quien la dispare sepa
        qué haría falta para poder decirlo.
  - [x] Guarda anti-prohibir-de-más: las afirmaciones que **sí** están acreditadas (operar sin
        internet, evidencia inmutable, aislamiento entre clientes, sin cuenta atrás) siguen
        pasando.
- **Cómo se cerró (2026-09-02).** El perímetro gana **una regla de capacidades derivada del
  registro §10 del runbook de auditoría** — que es donde los gates se marcan presencialmente— y
  no de una lista de gates tecleada: `Object.keys(CAPACIDADES_GATEADAS)` se compara **por
  igualdad** contra los diez del registro, así que un gate nuevo obliga a decidir qué
  afirmaciones dependen de él antes de poder seguir. Lo editorial —qué frase cuelga de qué
  gate— va escrito con su nombre; lo que no puede quedar a juicio es **olvidarse** de un gate.
  **Detalle que costó una corrida:** el registro tiene una fila (`G-01`) con **una columna
  menos** que las otras nueve, así que el parseo va por CONTENIDO y no por posición — un índice
  fijo daría «abierto» a un gate acreditado, y equivocarse en esa dirección es lo caro.
  **Y una corrección al propio informe:** «respaldo de energía» **se queda**. Está en la lista de
  materiales y es lo que se instala; lo que faltaba no era quitarlo sino decir que también se
  acredita en el inmueble, y ahora lo dice.

### [x] T-5.05 · Un gabinete **simulado** se ve igual que uno real — `SOFTWARE` · **CERRADA 2026-09-02**
> La separación entre lo simulado y lo real vive en el seed (`db/seeds/sim_fleet.sql`, con su
> aviso en mayúsculas de que jamás se aplica al entorno desplegado) y en el despliegue
> (`deploy/cloud/deploy.sh` solo siembra el de producción). **No vive en la pantalla**, que es
> justo donde se hace la demo.
>
> No hay columna que marque lo simulado ni marca visual en el mapa ni en la flota: lo único que
> delata a un sitio sim es que se llama *"Sitio Sim 001 Puebla"*. Misma píldora de estado, mismo
> medidor de respaldo, mismo color. En `make soc-local` un prospecto ve 21 sitios y 5 gabinetes
> con idéntico aspecto, de los cuales **20 y 4 no existen**.
>
> **El patrón visual ya está resuelto en el otro extremo del sistema:** el panel del gabinete
> pinta su cinta `DEMO · NO ES ESTADO REAL` y el manual de operación advierte de no dejar un
> monitor de pared así. La consola no tiene equivalente.
- **Componente:** web + api · **Depende de:** nada · **Prioridad: MÁXIMA**
- **Objetivo:** que un sitio o gabinete de demostración sea inconfundible en el mapa y en la
  flota, sin ensuciar la consola de producción.
- **Criterios de aceptación:**
  - [x] La marca se **deriva** de un hecho del dato (prefijo del código/serial, o columna
        explícita), decidido y escrito en la ficha con su razón. Si es columna, migración
        idempotente y con dueño correcto.
  - [x] El mapa y la ficha de flota rotulan lo simulado de forma legible a distancia, y el rótulo
        **no se confunde** con el ámbar de simulacro ni con el de dato viejo.
  - [x] Test: con la flota mixta, todo lo sim sale marcado y **nada real sale marcado** — las dos
        mitades, comparadas por igualdad.
  - [x] Con cero sitios sim (el caso de producción) la interfaz es idéntica a hoy: la marca no
        reserva espacio ni cambia el diseño.
- **Cómo se cerró (2026-09-02).** **Decisión: la marca se deriva del PREFIJO del código/serial,
  no de una columna nueva.** La razón: la convención ya existe, está documentada en la cabecera
  del propio seed y ya la defiende un test; una columna sería una **segunda verdad** sobre el
  mismo hecho, y las dos podrían divergir. Los patrones van **anclados** (`^site-sim-\d+$`) a
  propósito: un `includes("sim")` marcaría de demostración un edificio real llamado
  `site-simon-01`, y equivocarse en esa dirección —rotular de demo un inmueble con gente
  dentro— es peor que no rotular nada. Hay un test para ese caso exacto.
  **Lo que hizo falta en el servidor:** el contrato del mapa no publicaba el código, solo el
  nombre, así que la consola no tenía con qué distinguir. Ahora publica `code` —un **hecho**—
  y no un `demo: bool`: decidir qué se rotula es de la presentación, y meter la política del
  seed en el contrato la duplicaría.
  **El color, que no es un detalle:** el rótulo va **gris con borde discontinuo, no ámbar**. En
  esta consola el ámbar ya significa «simulacro en curso» y «dato retenido»; un tercer
  significado en el mismo color vacía los tres. El discontinuo es el mismo lenguaje que
  `T-5.01` le dio a los botones inertes del panel: «esto no es real».

### [x] T-5.06 · El runbook de alta de estación **rompe la ingesta** — `SOFTWARE` · **CERRADA 2026-09-04**
> `RUNBOOK-ALTA-DE-ESTACION.md:122-124` manda escribir en el archivo de entorno del gabinete:
> `TAKAB_EDGE_TENANT_ID=<uuid del tenant>`, `TAKAB_EDGE_SITE_ID=<uuid del sitio>`,
> `TAKAB_EDGE_GATEWAY_ID=<uuid del gateway>`.
>
> **La ingesta espera lo contrario, y lo dice en su propia cabecera**
> (`api/src/takab_api/ingest/handlers.py:9-13`): los identificadores que viajan en el payload son
> los **códigos y seriales legibles**, no UUIDs. Y `:126` rechaza el resto:
> `gateway mismatch: payload=… registro=…` → la cola de descarte.
>
> **Y lo peor del paso:** `infra/scripts/provision_gateway.sh:163` ya había escrito el valor
> correcto (el nombre del dispositivo). El runbook, en el paso siguiente, manda **sobrescribirlo**.
> Resultado: una estación aprovisionada, con su certificado, conectada por mTLS — y **muda en la
> nube**, sin que ninguna pantalla explique por qué.
>
> **Hay seis divergencias más**, todas del mismo origen (el runbook lleva desde el 2026-07-30 sin
> tocarse mientras el contrato de alta cambió tres veces): manda un campo que hoy da 422;
> documenta como inexistentes el alta de clientes y los permisos de visibilidad, que llevan meses
> en producción; **omite el paso de instalar el software del edge** y el de publicar la versión;
> omite el equipamiento del sitio, con lo que la consola pinta cinco actuadores en un gabinete que
> tiene dos; y omite el conjunto de reglas, con lo que la estación nueva nunca entra al
> sincronizado firmado.
- **Componente:** takab-docs + api (tests) · **Depende de:** nada · **Prioridad: ALTA**
- **Objetivo:** que el runbook vuelva a describir lo que hace el código, y que dejar de hacerlo
  ponga el build en rojo.
- **Criterios de aceptación:**
  - [x] Las siete divergencias corregidas, cada una citando el archivo y la línea del código que
        manda.
  - [x] Añadidos los pasos que faltan: instalación del software del edge, publicación de la
        versión, equipamiento explícito del sitio y conjunto de reglas con la clave del edge.
  - [x] **Un test que ancle el runbook al código**, no a otra prosa: las variables de identidad
        que el runbook manda escribir se comparan contra las que el aprovisionador escribe y
        contra las que la ingesta acepta. Si las tres dejan de coincidir, rojo con las tres
        citadas.
  - [x] El test cubre también el cuerpo del alta de gabinete: un campo que el esquema prohíbe y el
        runbook manda, sale nombrado.
  - [x] Nota en el runbook sobre por qué el aprovisionador ya lo deja bien y no hay que tocarlo.
- **Cómo se cerró (2026-09-04).**
  **Las siete divergencias se verificaron una a una contra el código antes de tocar nada**, y las
  siete eran ciertas. La que costaba una estación muda: `handlers.py` compara `payload.tenant_id`
  contra `tenants.code`, `payload.site_id` contra `sites.code` y `payload.gateway_id` contra
  `gateways.serial`; el runbook mandaba escribir UUIDs, y encima **pisar** el
  `TAKAB_EDGE_GATEWAY_ID` que `provision_gateway.sh:163` ya había dejado con el *thing name*
  correcto. Ahora el bloque lleva códigos, la línea del gateway va **comentada** con un «no lo
  toques», y encima una tabla de las tres correspondencias con la cita del rechazo
  (`_identity_reject`, `handlers.py:118-131`) y de la cola de descarte.
  **Las otras seis:** `fw_version` fuera del alta de gabinete (da **422**, `extra="forbid"`, y la
  versión la DECLARA el aparato — `T-1.74`); `equipment` **dentro**, con sus cinco canales, porque
  su default es todo-`true` y omitirlo pinta cinco actuadores en un gabinete que tiene dos;
  `POST /tenants` y `POST /visibility-grants` documentados como lo que son desde el **2026-07-15**
  (`T-1.72`/`T-1.73`) en vez de anunciados como futuro — con la nota de que el alta por SQL a mano
  además **se salta la fila de `audit_log`**; y **tres pasos nuevos** que sencillamente no
  estaban: instalar el software (`deploy/edge/deploy.sh` — el aprovisionador deja identidad y
  certificados, **no copia el código**), publicar la versión (`POST /fleet/releases`, o la flota
  entera sale `SIN REFERENCIA`) y crear el `rule_set` con su clave `edge` (sin uno aplicable la
  estación **nunca entra al sincronizado firmado**). El checklist del apéndice pasó de 8 pasos a 11.
  **El ancla es contra CÓDIGO, no contra prosa** (`api/tests/test_runbook_alta_de_estacion.py`,
  13 tests): las variables de identidad del runbook se cruzan con las que el aprovisionador
  escribe y con la regla de identidad de la ingesta —las tres citadas si divergen—, y los campos
  de los tres `POST` se comparan **por igualdad** contra `SiteCreate`/`GatewayCreate`/
  `SensorCreate`. Las tres mutaciones comprobadas: el UUID, el pisado del gateway y el
  `fw_version`.
  **Dos afinados que el propio test destapó, y el segundo es el patrón de siempre.** (1) Leer la
  viñeta entera contaba como órdenes los campos que el runbook nombra **para advertir de ellos**
  («`fw_version` da 422»), así que el parser se ancló a la frase `Campos:` y el aviso se movió a
  su propio sub-guion. (2) El barrido del aprovisionador **casaba con el `printf` equivocado**
  —la redirección va en la línea siguiente— y devolvía `{TAKAB_EDGE_GPIO_OWNER}`: un conjunto **no
  vacío**, así que el `assert gestionadas` pasaba en verde sobre un censo que ya no vigilaba la
  variable que importa. Se caza exigiendo el nombre concreto, no la no-vacuidad.
### [x] T-5.07 · El test del **deslinde impreso** no comprueba nada — `SOFTWARE` · **CERRADA 2026-09-04**
> `api/tests/dictamen/test_pdf.py:190-195`, entero:
>
>     assert DISCLAIMER.startswith("Dictamen operativo PRELIMINAR")
>     for variant in ("technical", "executive"):
>         assert render(model(), variant).startswith(b"%PDF")
>
> Comprueba (a) que una constante empiece por una cadena y (b) que el archivo sea un PDF.
> **Borrar la llamada que imprime el deslinde dejaría el test en verde.** Y lo mismo vale para los
> otros cinco avisos del documento —el de intensidad macrosísmica, el de sin calibración, el de la
> envolvente, el del centroide y el del croquis—: ninguno tiene una prueba que verifique su
> presencia en el documento.
>
> **El deslinde impreso es lo que protege al proyecto en una reunión comercial**, y es la única
> pieza del PDF cuya desaparición nadie notaría hasta que hiciera falta.
>
> **El propio repositorio ya sabe hacerlo bien:**
> `api/tests/dictamen/test_compliance_section.py::test_las_etiquetas_cambian_los_BYTES_del_pdf`
> es exactamente el patrón que falta aquí.
- **Componente:** api (tests) · **Depende de:** nada · **Prioridad: ALTA**
- **Objetivo:** que quitar un deslinde del documento ponga la suite en rojo nombrándolo.
- **Criterios de aceptación:**
  - [x] Los seis avisos se verifican **sobre el documento generado**, no sobre la constante.
  - [x] La lista de avisos a verificar se **deriva** del módulo que los declara, no se teclea: uno
        nuevo entra solo al censo.
  - [x] Guarda de no-vacuidad: el test declara en voz alta cuántos avisos espera, y cero no es un
        número aceptable.
  - [x] Cada aviso se comprueba en la variante o variantes donde debe salir, y se comprueba que
        **no** sale donde no debe (el aviso de asistencia automatizada, sin prosa generada).
- **Cómo se cerró (2026-09-04).**
  **No eran seis avisos: son ONCE**, y salieron de derivarlos en vez de enumerarlos. La regla del
  censo —constante de módulo, en mayúsculas, que es una **frase** (≥40 caracteres con espacios)—
  separa los avisos de los rótulos cortos (`ABSENT`, `TS_FMT`, `CCTV_PURGADO`, `SIN_HASH`), que
  son celdas de tabla. Los cinco que la ficha no había contado son los tres estados del CCTV
  —significan cosas **opuestas** y se leerían igual si el documento dijera solo «sin datos»—, el
  de croquis sin geometría y el de espectro no disponible.
  **Y un duodécimo que el censo no podía ver:** el aviso de **asistencia automatizada** vivía como
  literal dentro de `pdf.py`. Se extrajo a `NARRATIVE_AI_NOTE` para que entre al censo — era
  justo el aviso con la regla más fácil de romper.
  **Las dos formas obvias de probarlo no sirven, y una de ellas PASA EN VERDE SOBRE EL DEFECTO.**
  Buscar el texto en los bytes no funciona (flujo comprimido **y** fuentes embebidas: el texto
  viaja como índices de glifo). Y el patrón que la ficha señalaba como bueno —el de
  `test_compliance_section.py`, cambiar el modelo y exigir que los bytes cambien— **no distingue
  el aviso impreso del aviso ausente**, porque la portada imprime `content_sha256()` y ese hash se
  mueve con cualquier cambio del modelo; además aquí no aplica siquiera, porque estos avisos son
  constantes y no hay campo que los encienda. *(Ese test no se toca: es de otra ficha y lo suyo sí
  depende del modelo. Pero conviene saber que mide menos de lo que parece.)*
  **Lo que sí demuestra que el aviso llegó al papel** es espiar `TakabPDF.text_of`, el punto por el
  que pasa todo el texto que se dibuja. Si el `callout` no se llama, la cadena no pasa y el test se
  pone rojo **nombrando el aviso y la variante**.
  **Cada aviso se comprueba donde debe salir y donde NO** —los cinco del pericial no pueden
  aparecer en el resumen ejecutivo, y los tres del CCTV se excluyen entre sí—, y las variantes de
  la tabla **se midieron ejecutando el render**, no se supusieron. El de asistencia automatizada
  lleva sus tres lados: sale con proveedor externo, **no** sale con el determinista, **no** sale
  sin prosa.
  **La mutación que justifica la ficha entera:** borrando el `callout` del deslinde en el
  documento ejecutivo, **el test viejo pasa en verde** y el nuevo falla nombrándolo. Segunda
  mutación comprobada con `NO_MMI`.
  **Y el test viejo se reescribió en vez de borrarse.** Se llamaba `test_ambos_llevan_el_deslinde`
  y afirmaba cubrir las dos variantes; ahora se llama por lo único que sí comprobaba —qué DICE la
  constante— y apunta a dónde vive la comprobación de verdad. Dejarlo con el nombre viejo habría
  sido dejar puesta la señal que hizo creer durante meses que esto estaba cubierto.
### [~] T-5.08 · El guion de demo sirve para CI, **no para enseñar** — `SOFTWARE` · **PARCIAL 2026-09-04**
> `demo/` es sólido en lo que hace: se levanta desde cero con dos comandos, monta tres
> supervisores reales, el consumidor real y el motor de incidentes real, y está **bien aislado de
> producción** con tres guardias que se defienden solos (host real de la conexión, exclusividad de
> la base, y un seed que declara que jamás se aplica a la nube).
>
> Pero está construido para **acreditar criterios**, no para contar una historia: imprime marcas
> de verificación en terminal, trunca entre escenas y sale con código de error. Y le faltan tres
> cosas para una exposición: **no ejercita simulacros** (cero coincidencias de la palabra en todo
> `demo/*.py`), **no rotula los datos como simulados** —al contrario, el modo interactivo usa la
> identidad de desarrollo a propósito para que *"la consola local se vea igual que la
> desplegada"*—, y el aislamiento de notificaciones es **implícito**: descansa en que el script no
> lanza el worker, no en un interruptor.
- **Componente:** demo · **Depende de:** T-5.02, T-5.05 · **Prioridad: ALTA**
- **Objetivo:** un guion recorrible de principio a fin delante de un cliente, con los datos
  etiquetados y sin posibilidad de tocar nada real.
- **Criterios de aceptación:**
  - [ ] Escena de **simulacro** completa *(BLOQUEADA: la demo no tiene bajada nube→gabinete — `T-5.29`)*: agenda, armado, disparo humano, acuse por sitio y
        reporte, en las tres superficies.
  - [x] El guion corre con el modo demostración de `T-5.02` puesto, y **falla ruidosamente** si no
        lo está.
  - [x] Los datos del guion usan la identidad simulada y la marca visual de `T-5.05`.
  - [x] Un documento corto de recorrido —qué se enseña, en qué orden, qué NO se toca— que cite
        las frases de `INFORME-V1-COMERCIAL.md §3`.
  - [x] El aislamiento de notificaciones deja de ser implícito: se **impone**, y hay un test que
        lo comprueba.
- **Cómo quedó (2026-09-04). PARCIAL: cuatro de cinco criterios, y el que falta está fichado.**
  **Lo primero que apareció no estaba en la ficha: `make demo-fase1` llevaba UN MES EN ROJO.**
  33 OK · 2 FALLOS, y nadie lo había visto porque `demo/run.py` **no entra en `make test`**. La
  causa: hasta `T-2.32` una detección instrumental de UNA estación accionaba los relés, y el
  criterio C3 lo daba por hecho; la política ratificada invirtió eso —una estación sola AVISA— así
  que el guion llevaba desde el **2026-08-03** exigiendo una conducta que el producto abandonó a
  propósito. Un guion que falla dos comprobaciones no es «no recorrible»: es que **falla delante
  del cliente**.
  **C3 ahora usa DOS estímulos, y el orden es la mitad del arreglo.** Primero el instrumental con
  los relés en reposo —comprueba que **no acciona**, que es la política vigente— y después SASMEX,
  que es la protección local determinista que el criterio promete de verdad (reglas de oro 1 y 2).
  Al revés no funciona y se descubrió ejecutándolo: el enclave de SASMEX deja los cinco relés
  encendidos y la comprobación no puede distinguir «actuó el umbral» de «sigue sonando lo
  anterior». **38 OK · 0 FALLOS.**
  **El aislamiento de notificaciones dejó de ser implícito** (`demo/aislamiento.py`). Descansaba en
  que el guion no lanza el worker —una coincidencia de arranque, no un aislamiento: con un
  `make soc-local` a medio apagar la cascada saldría hacia teléfonos reales—. Ahora la demo
  **enciende el modo demostración** de `T-5.02`, **verifica** que la ventana quedó viva con la
  misma función que consulta el worker, y **al final cuenta lo entregado**: `sent` y solo `sent`,
  porque `simulated` es lo que produce un canal sin credenciales y desaparece justo en el entorno
  donde se haría la demostración. Cinco tests, y uno fija que `enabled_by` es **uuid** — un
  `"demo:run.py"` reventaba el INSERT en mitad del guion.
  **El recorrido interactivo usa la identidad SIMULADA.** `soc_local.py` levantaba
  `gw-dev-0001 / site-dev / R4F74` a propósito «para que la consola local se vea igual que la
  desplegada», que delante de un cliente es exactamente lo que no se quiere. Con
  `gw-sim-0001 / site-sim-001 / SIM001`, `T-5.05` lo rotula **DEMO** en el mapa y en la Flota.
  **`demo/GUION.md`**: qué se enseña, en qué orden y qué no se toca, con las frases de
  `INFORME-V1-COMERCIAL.md §3` **citadas literalmente** —las prohibidas tachadas y su sustituta al
  lado—, incluida la que más sorprende (una estación sola no acciona) y la advertencia de que el
  espectrograma se ve en local pero **en la nube sale vacío siempre** hasta que `T-3.11.c` se
  despliegue.
- **LO QUE FALTA, y por qué no se hizo:** la **escena de simulacro** (criterio 1). No es una
  decisión de alcance: **el sustituto de IoT Core de la demo es solo edge→nube**. Un simulacro son
  comandos firmados nube→gabinete, uno por sitio, y ese camino **no existe en el arnés**. Se
  intentó, se midió y se fichó como **`T-5.29`**, con la mitad que sí se puede recorrer hoy
  (`make soc-local`) escrita en el guion. Forzarlo habría exigido inventar un transporte de bajada
  sin verificación de firma — que probaría lo contrario de lo que hay que probar.
### [ ] T-5.29 · La demo no tiene camino de BAJADA nube→gabinete — `SOFTWARE`
> **No sale de la auditoría: apareció ejecutándola** (al cerrar `T-5.08`, el 2026-09-04).
>
> El sustituto de IoT Core de la demo (`demo/spool.py`) es **solo edge→nube**. No hay ningún
> transporte de bajada, y por eso `demo/run.py` no puede guionizar nada que se comande desde la
> nube: **un simulacro son comandos firmados nube→gabinete, uno por sitio**, y también lo son la
> actuación por quórum y la sincronización de config firmada.
>
> Consecuencia concreta, medida al intentarlo: la escena de simulacro de `T-5.08` se quedó a
> medias. La mitad de nube (agenda, armado, disparo, acuse por sitio, reporte) se puede recorrer
> a mano en `make soc-local`, donde la API y la consola están vivas; la mitad del **gabinete**
> —que es donde se ve que el simulacro suena— no tiene por dónde llegar.
>
> **Lo que NO es esto:** un problema del producto. En producción el camino existe (AWS IoT Core,
> `commands/`, el dispatcher del edge verifica firma antes de tocar nada). Es el arnés de la demo
> el que solo tiene la mitad.
- **Componente:** demo · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que la demo pueda guionizar lo que se comanda desde la nube, con la MISMA
  verificación de firma que en producción.
- **Criterios de aceptación:**
  - [ ] Camino de bajada en `demo/spool.py` (o su hermano) que entregue al gabinete el documento
        **firmado**, y que el edge lo verifique con el dispatcher REAL — un transporte que se
        salte la firma probaría lo contrario de lo que hay que probar.
  - [ ] Escena de simulacro completa en `demo/run.py`: agenda, armado, disparo humano, acuse por
        sitio y reporte, con el gabinete acusando recibo.
  - [ ] Un comando con firma inválida se RECHAZA y queda en la bitácora, y el guion lo comprueba:
        es la mitad que hace creíble la otra.
  - [ ] Guarda de no-vacuidad: el guion declara cuántos comandos espera entregar.

### [ ] T-5.09 · Cabeceras que declaran un conteo **sin test que lo cuente** — `SOFTWARE`
> `TASKS.md` tiene el suyo desde T-2.61, y por eso su cabecera es fiable. Los otros dos censos del
> proyecto no lo tienen, y **los dos ya divergieron**:
>
> - `DECISIONES-MAURICIO.md:15` declara **23 decisiones** y última actualización **2026-08-22**.
>   El archivo tiene **26** y la última es del **2026-08-30**. Tres decisiones son invisibles para
>   quien lea la cabecera — y la bitácora existe precisamente para poder revocar con conocimiento.
> - `TRASPASO-SESION.md §0` abre con un bloque en negrita que fija la deriva de despliegue en
>   **"tres commits"** sobre un commit que hoy está **103 por detrás** de `main`. La deriva real es
>   de 13 (nube) y 25 (gabinete). Es el archivo que se manda leer al empezar una sesión.
>
> Ninguno de los 28 tests de consistencia documental los mira. **Es la doctrina que el propio
> repositorio predica, sin aplicar a dos de sus tres censos:** *un censo que enumera a mano acaba
> divergiendo*.
- **Componente:** api (tests) + takab-docs · **Depende de:** nada · **Prioridad: ALTA**
- **Objetivo:** que ninguna cabecera de un documento de gobierno pueda declarar un número que el
  archivo desmiente.
- **Criterios de aceptación:**
  - [ ] Test que cuenta las decisiones de la bitácora (filas del índice y anclas de sección, que
        además tienen que coincidir entre sí) y exige que cuadren con su cabecera.
  - [ ] Test que comprueba que la fecha de última actualización declarada **no es anterior** a la
        fecha de la última decisión del archivo.
  - [ ] El bloque de deriva de despliegue del traspaso deja de fijar un número: **se le pregunta
        al sistema** (o se declara con la fecha de la medición y un test que exija que el commit
        citado exista y esté a la distancia declarada).
  - [ ] Las dos cabeceras corregidas en el mismo commit que sus tests.
  - [ ] El mensaje de fallo dice **cómo** rehacer el conteo, como ya hace el de `TASKS.md`.

### [ ] T-5.10 · **Procedencia del evento externo**: cinco estados, tres superficies — `SOFTWARE`
> Hoy no existe ninguna máquina de estados de procedencia. Lo que hay son dos enumeraciones de
> presentación (`EpicenterKind`, la banda de magnitud) y un campo `source` con tres valores
> efectivos. Y `reference_earthquakes` no lleva **ni hora de consulta, ni bandera de
> preliminar/revisado, ni identificador estable del proveedor**: solo una clave que nos inventamos
> nosotros, la fuente y una cita textual libre.
>
> Peor: `seismic_events.magnitude` **nunca se escribe con un valor**. El único INSERT del sistema
> pone `NULL` literal, así que la rama del catálogo en la consola es **inalcanzable en
> producción** y el SOC siempre ve "sin catálogo". El enriquecimiento post-hoc que documenta el
> esquema **no existe como código**.
>
> **El estado que más falta es el de sin correlación**, y no es un adorno: su ausencia convierte
> un "no sé" en una pantalla vacía que el operador lee como "no pasó nada".
>
> **Esto no roza el invariante de la cuenta atrás, lo cumple.** Lo que aquel prohíbe es una cifra
> **derivada por nosotros** del contacto seco. Una cifra de fuente externa citada, con su hora de
> consulta y su estado, es literalmente lo que el invariante contempla como *"fuente nueva y
> citable"*. La regla que esta ficha impone es: **con procedencia, o no se pinta**.
- **Componente:** api + web + mobile + edge · **Depende de:** nada · **Prioridad: ALTA**
- **Objetivo:** que toda cifra sísmica que no midió nuestro instrumento se pinte con su fuente, su
  hora de consulta y su estado de confirmación — o no se pinte.
- **Criterios de aceptación:**
  - [ ] Cinco estados en el contrato compartido, **con el mismo nombre en las tres superficies**:
        sin dato externo, consultando, preliminar, confirmado, sin correlación.
  - [ ] El texto de la consulta dice **"consultando"**, nunca *"estimando"*: nosotros no
        estimamos, preguntamos. Anclado por test.
  - [ ] `reference_earthquakes` gana hora de consulta, estado de revisión e identificador del
        proveedor; migración idempotente, con el dueño correcto.
  - [ ] Ninguna superficie pinta magnitud, epicentro, profundidad u hora de origen **sin** su
        fuente y su hora de consulta al lado. Test por superficie que lo verifique sobre el árbol
        renderizado.
  - [ ] El estado de sin correlación **se pinta**: hay un texto para él y un test que lo exige.
  - [ ] Se declara qué pasa hoy con la magnitud que nunca se escribe: o se escribe con su
        procedencia, o el campo se retira y la interfaz deja de tener una rama inalcanzable.

### [ ] T-5.11 · La correlación con el catálogo es **solo temporal** — `SOFTWARE`
> `api/src/takab_api/forensics/__init__.py:52` fija `CATALOG_WINDOW_S = 120.0` y la consulta toma
> el evento más cercano en el tiempo dentro de esa ventana. **No hay distancia máxima. No hay
> magnitud mínima. No hay filtro geográfico.** La distancia se calcula **después** del acierto,
> solo para describirlo, y nunca para rechazar. En la ruta del receptor —que es la normal— no hay
> epicentro propio que comparar, y el PDF imprime *"sin epicentro propio que comparar"*.
>
> Hoy el riesgo está acotado por accidente: son 13 filas mexicanas de 1985 a 2022. **Con el feed
> vivo de `T-2.149` se vuelve grave**: un sismo de cualquier parte del mundo ocurrido dentro de
> ±120 s del contacto se imprimirá en un dictamen firmado bajo el rótulo *"contraste con
> catálogo"*, con su magnitud y su lugar. Y el sistema no tiene forma de decir *"hay un evento en
> el catálogo pero no es el nuestro"*.
- **Componente:** api · **Depende de:** T-5.10 · **Prioridad: ALTA**
- **Objetivo:** que el criterio de identidad entre el evento del catálogo y el que disparó el
  gabinete sea explícito, defendible y capaz de decir que no encontró nada compatible.
- **Criterios de aceptación:**
  - [ ] Criterio explícito y configurable: ventana temporal, radio máximo epicentro↔sitio y
        magnitud mínima coherente con la distancia, cada uno con su razón escrita.
  - [ ] En la ruta sin epicentro propio, el acierto **no se presenta como contraste**: se declara
        no verificable, con su texto propio.
  - [ ] Un evento fuera de radio, o de magnitud incoherente con la distancia, **no casa** — y el
        resultado es el estado de sin correlación de `T-5.10`, no un hueco.
  - [ ] Test con un caso realista de sismo lejano dentro de la ventana temporal: hoy casaría; con
        la ficha, no.

### [x] T-5.12 · **Contar falsos positivos** — `SOFTWARE` · **CERRADA 2026-09-02**
> Hoy no hay forma de contarlos, ni siquiera a mano sobre la base. `incidents.state` admite
> `open|acked|in_review|closed` y **nada más**: no hay columna de clasificación, ni de descarte,
> ni de motivo de cierre. Cerrar un incidente **no pide ni admite una razón**, y el estado
> intermedio de revisión no desemboca en ningún veredicto registrable. No existe endpoint de
> agregados ni vista que los cuente.
>
> **Es la métrica que decide si el cliente renueva** — y la ironía está documentada en el propio
> código: la app explica que el documento de entrega *"deslinda expresamente los falsos positivos
> de SASMEX"*. El sistema **se deslinda de una tasa que no mide**.
>
> Lo único adyacente que ya está bien: los simulacros viven en tabla propia, así que al menos los
> ensayos no contaminan el conteo.
- **Componente:** api + web · **Depende de:** nada · **Prioridad: ALTA**
- **Objetivo:** que cerrar un incidente registre **qué fue**, y que la tasa se pueda leer sin
  abrir la base.
- **Criterios de aceptación:**
  - [x] Clasificación al cierre con un catálogo cerrado y corto, decidido en la ficha: real,
        falso positivo, prueba/mantenimiento, indeterminado. **Indeterminado no es el default
        silencioso**: se elige y se declara.
  - [x] La clasificación queda auditada con actor y hora, y **no se puede reescribir**: una
        corrección inserta, no sustituye, como ya hace la cadena de dictámenes.
  - [x] Endpoint de agregados por tenant y ventana, con la tasa y el desglose, respetando el
        aislamiento entre clientes.
  - [x] La consola lo muestra, y **declara cuántos incidentes están sin clasificar** en vez de
        excluirlos del denominador — un porcentaje calculado sobre lo clasificado, con lo no
        clasificado escondido, es peor que no tener el número.
  - [x] Los simulacros siguen fuera del conteo, con test.
- **Cómo se cerró (2026-09-02).** Tabla propia `incident_classifications` (migración `0055`),
  **append-only con las dos capas** que ya usa la cadena de dictámenes: `REVOKE UPDATE, DELETE`
  **y** el trigger `forbid_update_delete()`. Corregir **INSERTA** una fila que apunta a la
  anterior por `supersedes_id`; la vigente es la que nadie sustituye. `GET /classification-stats`
  da la tasa por ventana, y `api/src/takab_api/incident/classification.py` fija el conjunto
  `EN_LA_TASA` **excluyendo `prueba`** — los simulacros ya vivían en tabla aparte, pero un
  incidente marcado a mano como prueba también tenía que salir del denominador.
  **Dos decisiones que no estaban en la ficha y sí en el código.**
  (1) **La tasa devuelve `null`, no `0`, cuando nadie ha clasificado nada.** Un cero afirmaría
  que no hubo falsos positivos; lo que pasa es que nadie miró. La consola lo pinta `S/D` y dice
  por qué, y hay test de que jamás sale `0.0 %` desde el vacío.
  (2) **Los sin clasificar viajan junto al porcentaje, siempre** (`4 DE 10 SIN CLASIFICAR`): la
  agregación los conserva en el total en vez de filtrarlos, porque un porcentaje sobre lo
  clasificado, con lo no clasificado escondido, es una muestra sesgada por quién tuvo tiempo.
  **Y una divergencia que apareció al hacerlo, ajena a esta ficha:** el espejo de la matriz RBAC
  en `web/src/test-utils/meFixtures.ts` **lleva 16 celdas divergentes** de
  `api/src/takab_api/auth/matrix.py` (cctv ×9, privacidad ×4, `read_audit`, `checkin_submit`,
  `panic_vote`). Aquí se corrigieron **solo las dos de `classify_incident`**; las otras dieciséis
  siguen abiertas y **nada las vigila** — el fichero pide a mano que se le actualice. Es el patrón
  que `TRASPASO-SESION.md §4` ya nombró: *un censo que enumera a mano acaba divergiendo*. Se
  deriva en tres líneas comparando los dos por igualdad; no se hizo aquí porque volver verde esas
  dieciséis celdas cambia qué botones ven seis roles en las suites existentes, y eso es un lote
  propio, no un apéndice de esta ficha. **Fichado como `T-5.28`**, con la tabla de las dieciséis
  y con lo que de verdad hay que mirar al cerrarla: nueve de ellas apagan los paneles de CCTV en
  toda la suite de web, así que la divergencia no relaja una aserción — **borra la población**.

### [ ] T-5.13 · **Plantillas de simulacro** guardadas y editables — `SOFTWARE`
> No existen: ni tabla, ni campo en el cuerpo del alta, ni endpoint, ni interfaz. El alta de un
> simulacro tiene exactamente cinco campos y ninguno es una plantilla. Lo más cercano —ejecutar
> una agenda ya creada— **la consume**, así que no se puede reutilizar.
>
> Para el macrosimulacro de septiembre hay que teclear los sitios, la duración y la nota a mano,
> cada vez. Es fricción operativa en el caso de uso más visible que tiene el producto.
- **Componente:** api + web · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que un simulacro recurrente se defina una vez y se lance en dos clics.
- **Criterios de aceptación:**
  - [ ] Plantilla con nombre, conjunto de sitios, duración y nota; CRUD completo con el mismo rol
        que hoy puede disparar un simulacro.
  - [ ] Crear un simulacro desde una plantilla **copia** sus valores; editar la plantilla después
        no reescribe simulacros ya ejecutados.
  - [ ] Una plantilla cuyos sitios ya no existen o están retirados **lo dice al usarla**, en vez
        de lanzar contra un conjunto silenciosamente más pequeño.
  - [ ] Aislamiento entre clientes: una plantilla es de su tenant, con test de cruce.

### [x] T-5.14 · El **post-simulacro** no tiene tiempos ni sale del navegador — `SOFTWARE` · **CERRADA 2026-09-02**
> Lo que hay está bien hecho: el acuse por sitio se deriva por unión con la tabla de comandos, y
> distingue honestamente *sin gabinete comandable* de *sin acuse* — dos cosas que colapsar sería
> mentir. Faltan las dos que el cliente pide:
>
> - **El tiempo.** No existe latencia de acuse por sitio en ninguna capa: ni el esquema de salida
>   ni la interfaz exponen el instante del acuse ni su diferencia contra el arranque. El dato
>   clave de un post-simulacro —*"la torre B tardó 4 min 12 s"*— **no existe**.
> - **La salida.** No hay PDF ni CSV: cero referencias a simulacros en los routers de exportación
>   y de reportes. El propio código llama a esto *"la evidencia de cumplimiento que se le entrega
>   a Protección Civil"*, y hoy se entrega **mirando una pantalla**.
- **Componente:** api + web · **Depende de:** ~~T-5.13~~ **nada** · **Prioridad: MEDIA**
  > **Corregido al ejecutarla.** La dependencia declarada era **editorial, no técnica**: se
  > escribió porque las dos fichas hablan de simulacros y quedaban juntas en el plan. Nada del
  > reporte toca las plantillas — el reporte lee `drills` + `commands`, que existen desde
  > T-2.48, y T-5.13 crea una tabla nueva que el reporte no consulta. Se cerró **sin** T-5.13.
- **Objetivo:** un documento que el cliente pueda enseñarle a Protección Civil.
- **Criterios de aceptación:**
  - [x] Instante del acuse por sitio persistido y expuesto, con su diferencia contra el arranque
        del simulacro.
  - [x] El tiempo se declara **por sitio y agregado**, y los sitios sin acuse no se cuentan como
        cero: salen aparte.
  - [x] Exportación del reporte con las mismas propiedades que el dictamen: determinista,
        hasheada, registrada como evidencia y auditada.
  - [x] El documento distingue las tres categorías (acusó / no acusó / no tenía gabinete) y dice
        cuántos sitios hay en cada una.
- **Cómo se cerró (2026-09-02).** `commands` gana `acked_at` (migración `0055`) y `DrillSiteOut`
  lo expone junto a `ack_latency_s`; `POST /drills/{id}/report` renderiza el PDF con el mismo
  camino que el dictamen —determinista, hasheado, inscrito en `evidence_objects` (que gana
  `drill_id`) y auditado—. La consola pinta `+M:SS · sello UTC` por sitio y la `MEDIANA` en el
  resumen.
  **La decisión que gobierna la ficha entera: quien no acusó NO entra como cero.** `null` viaja
  intacto del SQL al píxel, en las cuatro capas, y cada una tiene su test: la latencia del que no
  acusó es `None`, la mediana de un simulacro sin acuses es `None`, el resumen dice `MEDIANA S/D`
  y **la fila del que no acusó no pinta nada** —ni `+0:00` ni un guion—, porque los dos se leen
  como *respondió al instante*, que es lo contrario del hecho. Un cero además arrastraría la
  mediana hacia abajo justo en el simulacro que peor salió.
  **Tres cosas que aparecieron al hacerlo.**
  (1) **El discriminador de agenda es `scheduled_at`, no `started_at`.** El guard que impide
  exportar una agenda —un documento que afirmaría cero de cero— se escribió primero sobre
  `started_at`, que la fila de agenda **también** lleva. Se caza con test.
  (2) **`evidence_objects` se declara ANTES que `drills` en `db/schema.sql`**, así que la FK
  inline reventaba una carga limpia; va como `ALTER TABLE` después del bloque de `drills`.
  (3) **Generar va con `drill_start`, no con `export`**, copiando la separación que ya existe
  entre `generate_report` y `export` en el dictamen: **generar inscribe una evidencia inmutable**
  del tenant, y `gov_operator` —que existe para recogerla— la descarga después por la ruta de
  evidencia de siempre. El reporte se registra con `drill_id`, así que le llega.

### [x] T-5.15 · **Cadena de acuse**: cuánto tardó y quién recibió — `SOFTWARE` · **CERRADA 2026-09-02**
> Tres de las cuatro preguntas se contestan hoy: quién acusó (con fila en el timeline y verbo en
> la bitácora), quién no respondió (el pase de lista distingue *sin reporte* y ofrece notificar a
> los que faltan), y en qué zona. Faltan dos, y las dos son de perito:
>
> - **"¿En cuánto tiempo?"** — el sistema **sí** calcula y almacena una latencia, pero es la de
>   **despacho** de la notificación, no la del acuse. El acuse escribe su fila con el sello de la
>   transacción y **nunca lee el instante de apertura**; la bitácora del SOC imprime sellos
>   absolutos sin columna de transcurrido. El número es derivable restando a mano; nadie lo hace.
> - **"¿Quién recibió la alerta?"** — la tabla donde vive el destinatario y la confirmación de
>   entrega **no se lee desde ningún router de consulta**. Es contestable en la base y no por la
>   API ni por ninguna pantalla.
- **Componente:** api + web · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que una revisión post-incidente se pueda hacer sin abrir la base.
- **Criterios de aceptación:**
  - [x] Latencia de acuse calculada y expuesta, con la misma honestidad que la de despacho: quien
        no acusó no tiene latencia, y eso **no es un cero**.
  - [x] Endpoint de lectura de los envíos de un incidente: canal, destinatario (con el mismo
        criterio de mínimo dato que el resto), estado y confirmación de entrega.
  - [x] La bitácora del incidente muestra el transcurrido junto al sello absoluto.
  - [x] Aislamiento entre clientes con test de cruce, y el envío simulado se distingue del
        entregado, como ya hace la tabla.
- **Cómo se cerró (2026-09-02).**
  **La latencia del acuse** la escribe ahora la propia fila (`incidents_ack.py`), calculada **en
  SQL y en el mismo statement que la inserta**: así el `now()` del que sale la cifra es
  exactamente el `now()` del `ts` de la fila. Restarlo en Python daba un número plausible y falso
  en cuanto los relojes difieren un segundo. Va con la misma clave (`latency_s`) y el mismo `t0`
  (`incidents.opened_at`) que la de despacho de `notify_sent`, así que las dos se comparan sin
  traducir nada.
  **`GET /incidents/{id}/notifications`** lee lo que `notification_jobs` guardaba desde la `0040`
  y no leía nadie. Devuelve **dos latencias separadas y NO sumadas**: `dispatch_latency_s` (de la
  apertura a que el proveedor aceptó) y `delivery_latency_s` (de ahí a la confirmación). El
  segundo tramo **no depende de TAKAB** —son los tres minutos del operador móvil—, y presentarlos
  sumados se los cargaría a la plataforma. `delivered` sale de `delivered_at IS NOT NULL` **y de
  nada más**: `sent` es «el proveedor lo aceptó» y `simulated` «no había proveedor», y ninguno de
  los dos afirma que un humano lo tenga en la mano.
  **El destinatario se reduce en `notify/destino.py`, con allowlist por FORMA** — la misma
  doctrina de `narrative/redact.py`, y por el mismo motivo: con una denylist, el canal que se
  añada mañana trae un `target` que nadie previó y sale entero, con el teléfono dentro. Lo que no
  encaja **no sale y se declara** (`unrecognised`), porque un hueco se leería como «no había
  destinatario».
  **Tres cosas que aparecieron al hacerlo.**
  (1) **La URL de un webhook ES la credencial.** Un `https://…/services/T0/B0/xoxb…` autoriza a
  publicar a cualquiera que lo lea; devolver `target` en crudo habría sido una fuga de secreto por
  una pantalla de consola. Sale **el host y nada más**, con test de que la ruta no aparece.
  (2) **El prefijo de país no se deduce del largo.** La primera versión del enmascarado lo dedujo,
  acertaba con México y mentía con `+1` y con `+351`. Un prefijo inventado en una pantalla de
  evidencia es peor que un dígito menos: **se enmascara todo menos la cola**.
  (3) **`gov_ack_incident` no dejaba fila en la bitácora** (migración `0056`). Escribía solo
  `audit_log`, así que un incidente acusado por Protección Civil salía `acked` en la consola **con
  la bitácora sin un solo acuse**: la pantalla que existe para reconstruir lo ocurrido contradecía
  al estado que tenía al lado. No es un hueco, es una contradicción — y ninguna de las dos vías
  del acuse tenía test de que su fila existiera.
  (4) **El SLA no se cumple por no intentarlo.** El veredicto de plazo comparaba `sent_at <=
  deadline_at`, así que el job encolado hace media hora con plazo de 60 s **y sin enviar** salía
  sin veredicto y sin aviso: el incumplimiento más grave era el único silencioso. Se compara
  contra `sent_at` si salió y contra **ahora** si no, y el `null` queda para lo único que lo
  merece — el canal que no tenía plazo.

### [x] T-5.16 · **Umbrales por tipo de inmueble**, con rollback — `SOFTWARE` + `DECISIÓN` · **CERRADA 2026-09-02**
> `BLUEPRINT §4.5` declara tres bandas de referencia: hospitales 0.040–0.060 g, industriales
> 0.080–0.120 g, corporativos 0.100–0.150 g. **Ninguna está implementada.** `building_type` es
> texto libre sin catálogo ni restricción, y **nadie lo consulta** para resolver umbrales: los
> alcances son tenant, sitio y sensor. El propio código lo declara en la consola.
>
> Consecuencia física: el default del edge está documentado como *"Default = hospital"*, así que
> **toda la flota corre la banda de hospital**. Un industrial dado de alta hoy avisa dos veces por
> debajo de su banda.
>
> Y falta el **rollback**, que el blueprint exige por nombre (*"versionada y reversible"*) y que
> `G-05` pide explícitamente. El versionado y el conflicto por versión base están bien resueltos y
> con test; el histórico está en la base. Lo que no hay es forma de volver a una versión: hay que
> teclear los valores viejos y crear una nueva.
>
> **Lo que hay que decidir:** si la tipología es un catálogo cerrado con bandas por defecto, o una
> etiqueta que solo sugiere. La primera opción cambia el comportamiento de una estación con solo
> cambiarle el tipo, y eso **no puede pasar sin publicar y firmar**.
- **Componente:** api + web + db + edge · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que el umbral de un edificio corresponda a lo que ese edificio es, y que volver
  atrás sea un clic, no un dictado.
- **Criterios de aceptación:**
  - [x] Decisión escrita **con su razón** sobre si la tipología resuelve umbrales o solo los
        sugiere.
  - [x] Catálogo cerrado de tipos, con las tres bandas del blueprint como valores de referencia
        **derivados de un solo sitio**, no copiados en tres archivos.
  - [x] Cambiar el tipo de un sitio **nunca** cambia por sí solo lo que corre en el gabinete: hace
        falta publicar, y la publicación va firmada como hoy.
  - [x] Rollback a una versión anterior del conjunto de reglas, como operación explícita que
        **crea una versión nueva** declarando a cuál vuelve — nunca reescribiendo el histórico.
  - [x] El rollback queda auditado y respeta el conflicto por versión base.
  - [x] Test de que el default del edge deja de ser silenciosamente el de hospital: sin banda
        resuelta, el gabinete **lo declara** en vez de suponerla.
- **Cómo se cerró (2026-09-02).**
  **La decisión es `D-28`: la tipología SUGIERE, no resuelve.** La razón que la sostiene, y que
  conviene no perder: *el tipo se edita desde una pantalla de captura*. Quien abre el formulario
  de una estación va normalmente a corregir una dirección; si el tipo resolviera el umbral, ese
  guardado —administrativo, sin firma y sin publicación— **re-armaría el edificio a otra
  sensibilidad**. Es un cambio de actuación por un acto de captura, y choca con las reglas de oro
  1 y 8. Se prueba **midiendo**: `test_cambiar_el_TIPO_no_toca_el_rule_set_activo` compara el
  rule_set activo antes y después de cambiar el tipo, en vez de fiarse de un comentario.
  **El catálogo vive en `shared/schemas/tipologia_umbral.json`** y de ahí derivan, por igualdad y
  en los dos sentidos, la validación de la API, el `CHECK` de `sites.building_type` y el
  desplegable de la consola — y las tres bandas se leen **del propio blueprint** con una expresión
  regular, así que retocar una cifra en un sitio y no en el otro sale rojo con el número que
  cambió.
  **El rollback** (`POST /rule-sets/{id}/rollback`) crea una versión **más**, nunca una menos:
  `rolled_back_to` declara a cuál vuelve, queda auditado con las dos versiones y respeta el
  conflicto por versión base igual que el PUT.
  **Cinco cosas que aparecieron al hacerlo.**
  (1) **Los tipos que el producto atiende y para los que NADIE publicó banda** —universidad,
  gobierno, otro— la llevan en `null` **con su razón escrita**. Prestarles la de hospital habría
  sido repetir el defecto que abre la ficha en vez de cerrarlo.
  (2) **El rollback NO resucita un secreto rotado.** El `config` guarda el `secret` del webhook, y
  una versión vieja lo trae; puede haberse rotado justamente porque se filtró. Se restauran los
  valores de entonces con las credenciales de AHORA, reutilizando `redact_config` + `merge_secrets`
  en vez de escribir una tercera regla de secretos.
  (3) **El panel trataba «cualquier cosa que no sea `sin_resolver`» como banda publicada**, así
  que un origen desconocido se leía como decidido — un fallback pintado de `ok`. Son **tres**
  estados, y el tercero se declara. Lo cazó el censo de render del panel: mutar el campo no
  cambiaba un pixel porque todas las mutaciones caían en la misma rama.
  (4) **El origen se pinta SIEMPRE**, no solo cuando es malo: que la advertencia falte no puede
  ser la única señal de que la banda sí se eligió.
  (5) **`serverDataCensus` obligó a sacar el campo de tipología a componente propio.** Dentro del
  formulario era dato de servidor sin los cuatro estados: con la consulta caída, un desplegable
  con solo «SIN CLASIFICAR» se lee como «no hay tipos», que es lo contrario de «no se pudieron
  leer».
  **Lo que la migración `0057` hace con lo escrito antes:** `building_type` era texto libre. Se
  normaliza lo reconocible y lo que no encaja pasa a `otro` **dejando el texto original en
  `audit_log`** — perder la captura de alguien en silencio para que cuadre un `CHECK` es lo que
  prohíbe la regla de oro 11.

### [x] T-5.17 · El **sonido del simulacro** no se elige ni queda auditado — `SOFTWARE` · **CERRADA 2026-09-02**
> El selector de audio que la nube empuja cubre **dos ranuras** —sirena y tono de prueba— y el
> voceo de simulacro **no está entre ellas**: sale de un ajuste local cuyo valor por defecto es
> vacío, configurable solo tocando el archivo de entorno de cada gabinete.
>
> Y la auditabilidad tiene un hueco: el sha256 se registra **al arrancar**, no al sonar. Al
> reproducir solo se escribe la ruta en el journal local, y el botón del panel deja rastro en un
> anillo **en memoria** que no pasa por el libro de actuaciones. Si alguien pregunta qué sonó el
> 19 de septiembre en la torre B, la única respuesta está en el journal de ese gabinete.
>
> **La propiedad que hay que conservar al añadir el selector** ya está bien resuelta en el
> catálogo y no se toca: la nube elige **por identificador de catálogo**, nunca por binario ni
> ruta absoluta —ese canal va firmado a un aparato que toca gas y puertas—; un identificador
> desconocido **conserva el tono anterior** en vez de caer a otro; y el tono oficial sigue
> reservado y ausente por su gate legal.
- **Componente:** edge + api · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que se pueda elegir el sonido del simulacro desde la nube y que quede constancia
  de qué sonó exactamente.
- **Criterios de aceptación:**
  - [x] El perfil de audio gana la ranura del voceo de simulacro, con las mismas reglas que las
        dos existentes.
  - [x] El sha256 del asset **viaja en el acuse** del arranque del simulacro y queda persistido
        junto al acuse por sitio, no solo en el journal.
  - [x] El botón del panel deja constancia persistida, no en un anillo en memoria.
  - [x] Un identificador desconocido conserva el tono anterior y **lo declara**; el tono oficial
        sigue ausente del catálogo.
  - [x] Test que recorra los tres caminos: identificador válido, desconocido y reservado.
- **Cómo se cerró (2026-09-02).**
  **La ranura** `audio.simulacro` sigue las tres reglas de las otras dos, y no por copia: el bucle
  de `apply_audio_profile` recorre las tres con el mismo código, así que la cuarta que alguien
  añada hereda las reglas o no entra. El voceo de simulacro deja además de leerse de `settings` en
  cada reproducción y pasa a ser **estado del módulo**, que es lo que permite que la nube lo
  elija; el valor inicial sigue siendo el asset local del sitio.
  **El sha256 se calcula de lo que va a sonar, en el instante de sonar**, y no del asset que se
  enumeró al arrancar. La diferencia no es teórica: entre el arranque y el simulacro puede haber
  entrado una config firmada que cambió el tono, y el hash que se registraba hasta hoy podía no
  ser el del sonido que salió por la bocina. Viaja en `results.audio` del acuse —campo que ya
  existía en el contrato, así que **no se abre superficie nueva hacia el gabinete**—, se persiste
  con el acuse por sitio, se expone en `DrillSiteOut.audio` y se cita en el PDF del reporte.
  **El botón del panel** escribe en la bitácora local (`ActuationLedger`), con causa propia
  `lan_drill_voice` y con el asset y su huella en el detalle: «se voceó» sin decir qué se voceó no
  responde a un perito. Antes solo quedaba en la `deque` de `_actions`, que un reinicio borra.
  **Tres cosas que aparecieron al hacerlo.**
  (1) **Un id RESERVADO y uno inventado acababan indistinguibles.** Los dos conservan el tono
  anterior —eso está bien—, pero un tecleo y una infracción de licencia no son el mismo hecho. El
  reporte de flota gana `reserved` con la razón, para poder decir «el tono oficial de SASMEX es de
  CIRES» en vez de un «desconocido» opaco.
  (2) **`audio: null` y «no había módulo de audio» eran lo mismo para quien lee el reporte al día
  siguiente.** Ahora la evidencia **nunca es `None`**: declara la razón, porque el voceo es
  advisory y un simulacro sin él es legítimo —el banner y el registro viven igual—.
  (3) **Y un tercer estado en el documento: «NO REPORTADO».** Un gabinete con firmware anterior no
  trae el campo, y colapsarlo con «SIN VOCEO» afirmaría un silencio que nadie midió.
  **Lo que NO se cierra aquí, y conviene no leer de más:** el catálogo gana un **tono**
  (`takab-simulacro-v1`), no el mensaje hablado. El voceo grabado sigue siendo un asset local y su
  gate de hardware sigue abierto — `RUNBOOK-gate-hw-movil-y-voceo.md §C.2` pide dos grabaciones
  **distinguibles a oído** y nadie las ha hecho. El tono está construido para no confundirse con
  la sirena (carillón de tres pulsos con dos segundos de silencio: el patrón de la megafonía, no
  el de una alarma), es reproducible con `edge/scripts/gen_simulacro.py` como los otros dos, y hay
  test de que los tres binarios del catálogo son **distintos entre sí** — dos ids apuntando al
  mismo WAV sonarían igual aunque el catálogo dijera lo contrario.

### [x] T-5.18 · La IA **no tiene tope de gasto** — `SOFTWARE` · **CERRADA 2026-09-03**
> Hay contabilidad por llamada (el coste se lee de la respuesta del proveedor y se escribe en la
> bitácora) y techo de tokens por llamada. **No hay cuota, ni contador acumulado, ni corte, ni por
> tenant ni por mes.** Y el endpoint que la invocaría **no tiene límite de frecuencia**: la única
> puerta es de rol. Un usuario autenticado puede reexportar el mismo incidente sin límite.
>
> Es la categoría que OWASP llama consumo de recursos sin restricción, y está en el blueprint.
> **Hoy el riesgo está acotado solo por que la perilla está apagada** — lo que significa que el
> tope tiene que aterrizar **antes** del shadow-mode, no después.
- **Componente:** api · **Depende de:** nada · **Prioridad: ALTA (precede a `T-3.01`)**
- **Objetivo:** que encender la IA no pueda costar más de lo que alguien decidió.
- **Criterios de aceptación:**
  - [x] Tope por tenant y por mes, configurable, con valor por defecto conservador.
  - [x] Contador acumulado persistido; alcanzado el tope, **el proveedor cae al determinista** y
        lo declara — nunca falla la exportación, que es una superficie de vida.
  - [x] El corte queda auditado, y el acercarse al tope también (una fila, no una por petición).
  - [x] Límite de frecuencia en la exportación de reportes, por usuario y por sitio, con el mismo
        patrón de dos techos que ya usan los comandos.
  - [x] Test de que con la perilla apagada nada de esto cambia el comportamiento actual.
- **Cómo se cerró (2026-09-03).**
  **Tabla `ai_spend`** (migración `0058`), una fila por `(tenant, mes UTC)`. Es un **contador, no
  evidencia**: por eso se actualiza en sitio y `takab_app` tiene UPDATE, al revés que casi todo lo
  demás del esquema. Lo que sí es evidencia —cuánto costó cada llamada, cuándo se avisó y cuándo se
  cortó— sigue en `audit_log`, que es append-only y exento de poda. El tope por defecto son **5 USD
  al mes**, deliberadamente conservador: el defecto de una cuota no puede ser «el que no molesta».
  **Agotada la cuota, la exportación SALE IGUAL** con texto determinista y lo declara en el PDF. Es
  la decisión que gobierna la ficha: el dictamen es una superficie de vida —alguien lo usa para
  decidir si un edificio se ocupa— y un 429 ahí convertiría un tope de gasto en una **negación de
  evidencia**. La prosa de IA rodea al veredicto y el veredicto no la necesita.
  **El freno de la exportación** son los dos techos de los comandos: el del usuario y el del
  **edificio** (`RO-8.e`: dos operadores coordinados agotan el segundo sin que ninguno rebase el
  suyo). Se cuenta desde `audit_log`, que ya registra cada exportación y no se poda nunca — sin
  tabla nueva ni contador que se pueda perder —, y el rechazo llega **antes de renderizar**:
  rechazar después de haber gastado el PDF y la llamada de IA no protegería de nada.
  **Tres cosas que aparecieron al hacerlo.**
  (1) **La auditoría del corte no escribía nunca.** La primera versión auditaba desde el router
  releyendo el estado, y `leer_estado` **consume** la transición al sellar `blocked_at`: la
  segunda lectura ya la veía consumida. Quien sella el hecho tiene que escribirlo, así que la fila
  se mudó al módulo de cuota. Lo cazó escribir el test, no leer el código.
  (2) **`cap = 0` significa SIN TOPE, no «tope cero»**, y está declarado: es la lectura
  conservadora del ajuste ausente. Quien quiera cortar del todo apaga `openrouter_enabled`, que es
  el interruptor que ya existía.
  (3) **El tope se puede rebasar por UNA llamada, y se declara en vez de disimularse.** El coste
  solo se conoce al volver del proveedor, así que la secuencia honesta es leer → decidir → llamar →
  sumar. Reservar un estimado antes habría sido cobrar por lo que no se sabe; el desbordamiento
  máximo es una llamada, acotado a su vez por el techo de tokens que ya existía. Hay test de que
  el gasto real queda escrito **sin recortarlo al tope**.
  **Y el criterio que protege el estado de hoy:** con la perilla apagada no se cobra ni una
  llamada. `build_narrative` no toca la cuota cuando el proveedor no sale a la red — cobrarle al
  determinista llenaría el contador de ceros y el `calls` de mentiras sobre cuántas veces se salió
  a la red. Apagar la perilla **no es una degradación** y sigue sin marcar el PDF.

### [x] T-5.19 · El aviso de la plataforma no nombra a **un solo encargado** — `GATE-LEGAL` + `SOFTWARE` · **CERRADA 2026-09-03** *(la mitad de software; el texto revisado sigue esperando a `D-20`)*
> Siete terceros tocan o tocarán datos personales: AWS, Twilio, Meta, el servicio de
> notificaciones de Apple, el de Google, la cadena de compilación del móvil, y el webhook del
> propio cliente. **Ninguno está declarado.** Y el aviso **no menciona la transferencia
> internacional**: los datos viven en Ohio. El párrafo más cercano —*"SUS DATOS NO CRUZAN A OTRA
> ORGANIZACIÓN"*— habla del aislamiento entre clientes y es fácil de leer como una negación de
> ello.
>
> **El atenuante es real y hay que decirlo:** el aviso **se autodeclara provisional dentro del
> propio texto**, ese párrafo entra en la huella que sella el consentimiento, y el motor re-pide
> consentimiento al cambiar el texto. A nadie se le está diciendo algo falso; se le está diciendo
> nada. El mecanismo es definitivo; el texto no.
>
> **Choca con `D-20` y gana `D-20`:** la consulta legal espera a que un cliente la pida. Esta
> ficha **no la reabre**. Lo que sí hace es dejar el trabajo de costura listo para el día que
> llegue el texto revisado, y anotar el hecho nuevo: `D-23` y `D-07` descansan **las dos** sobre
> la calificación de que TAKAB es encargado y no responsable, y esa calificación solo está
> afirmada en un texto que se declara sin revisar.
- **Componente:** api + takab-docs · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que el día que llegue el texto revisado no falte nada de software, y que mientras
  tanto el inventario de encargados exista y esté al día.
- **Criterios de aceptación:**
  - [x] Inventario de encargados en un documento propio, **derivado** de los proveedores que el
        código construye y de los recursos de infraestructura que tocan datos personales, no
        tecleado. Un proveedor nuevo entra solo.
  - [x] Test que compare el inventario contra los proveedores registrados: uno que no esté
        declarado pone el build en rojo nombrándolo.
  - [x] El aviso gana los dos huecos que hoy no tiene —encargados y transferencia— como
        **marcadores de posición explícitos**, dentro del texto provisional y por tanto dentro de
        la huella.
  - [x] Anotado en `PENDIENTES-MAURICIO §4.1` que la calificación de encargado sostiene `D-23` y
        `D-07`, para que la consulta legal la traiga en su lista.
- **Cómo se cerró (2026-09-03).**
  **Esta ficha NO reabre `D-20`**, y conviene leerlo así: la consulta jurídica sigue esperando a
  que un cliente la pida. Lo que se cerró es el trabajo de costura, para que el día que llegue el
  texto revisado no falte nada de software.
  **`takab-docs/ENCARGADOS-TAKAB.md` se GENERA** de `privacy/encargados.py` — un documento
  tecleado a mano dura hasta el primer proveedor nuevo, y el día que se queda corto **nadie se
  entera**: no hay pantalla que falle. Dos censos lo comparan por igualdad contra el código:
  (a) las **clases proveedoras** del paquete `notify` que salen a un tercero, derivadas del árbol
  de sintaxis y no importando los módulos —`twilio`, `whatsapp` y `push` se importan tarde a
  propósito, y un censo que exigiera importarlos sería un censo de lo que se pudo importar hoy—;
  (b) los **servicios de AWS** que aparecen en `infra/terraform`, cada uno clasificado como
  «guarda datos personales» o no, **con su razón en los dos casos**.
  **El aviso gana los dos párrafos** que le faltaban, dentro del texto provisional y por tanto
  dentro de la huella: eso significa que quien ya consintió **vuelve a ver el aviso**, porque el
  motor re-pide consentimiento al cambiar el texto. Los dos se declaran como **MARCADOR DE
  POSICIÓN**: afirmar una lista completa de encargados sobre un texto sin revisión jurídica sería
  peor que el hueco que había.
  **Tres cosas que aparecieron al hacerlo.**
  (1) **El censo encontró dos clases que yo no había declarado** —`WhatsAppTemplateProvider` y
  `SimulatedPushProvider`—, y una de las dos era el proveedor REAL de WhatsApp: yo había declarado
  un `WhatsAppProvider` que no existe. Es exactamente el defecto que el censo existe para cazar, y
  lo cazó en su primera ejecución sobre su propio autor.
  (2) **El párrafo «SUS DATOS NO CRUZAN A OTRA ORGANIZACIÓN» se retituló.** Hablaba del
  aislamiento entre clientes, y junto a un aviso que callaba a siete encargados se leía como que
  nadie más los toca. Ahora dice de qué habla y remite al párrafo siguiente. Hay test de que la
  frase vieja no vuelve.
  (3) **El webhook del cliente se declara igual, con su matiz escrito**: ahí el destino lo elige el
  RESPONSABLE y no TAKAB, y su país es «desconocido: lo determina el cliente». Omitirlo por ese
  matiz habría sido exactamente el hueco que abre la ficha.
  **Y el hecho nuevo que se anotó para la consulta:** `D-23` y `D-07` descansan **las dos** sobre
  la calificación de que TAKAB es *encargado* y no *responsable*, y esa calificación solo está
  afirmada en un texto que se declara sin revisar. Si no se sostiene, las dos decisiones cambian
  de dueño y no de detalle.

### [x] T-5.20 · Firmar un dictamen **no entra en la bitácora de auditoría** — `SOFTWARE` · **CERRADA 2026-09-03**
> Firmar escribe la fila del dictamen —con quién firmó, en una tabla que no admite reescritura— y,
> **solo si el veredicto es habitable**, una acción en el timeline del incidente. **No escribe en
> `audit_log`.** El censo tiene 72 verbos, incluidos leer un dictamen y solicitarlo; no el de
> firmarlo.
>
> El hecho no se pierde. Pero el sitio donde un perito, un seguro o una auditoría van a buscar
> *"quién firmó qué y cuándo"* es la bitácora, y **el acto de mayor peso legal del sistema no está
> ahí**. Si además el veredicto firmado no es habitable, tampoco deja acción en el timeline.
- **Componente:** api · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que el acto más importante del sistema aparezca donde se busca.
- **Criterios de aceptación:**
  - [x] Verbo propio en la bitácora al firmar, con el incidente como objeto y el veredicto en el
        detalle.
  - [x] La fila se escribe **también** cuando el veredicto no es habitable.
  - [x] Un test de censo que exija que **toda transición de estado con peso legal** deje verbo:
        derivado, no una lista a mano, para que el siguiente entre solo.
  - [x] La bitácora sigue siendo escritor único: la fila entra por el módulo de auditoría, como el
        contract-test existente exige.
- **Cómo se cerró (2026-09-03).**
  `dictamen_signed`, con el incidente como objeto y en el `meta` el veredicto, si es habitable, el
  identificador del dictamen y **a quién sustituye** — la cadena se reconstruye desde la bitácora
  sin tener que leer la tabla de dictámenes. La llamada va **antes** del `if` de habitabilidad y no
  dentro, que es lo que dejaba al peor caso sin rastro en ninguno de los dos sitios: ni bitácora
  (no escribía nunca) ni timeline (solo si era habitable). Y es justo el veredicto que más pesa:
  `no_inhabit_inspect` deja a gente fuera de su casa hasta que alguien inspeccione.
  **El censo es el entregable, no el arreglo.** Arreglar la firma habría tardado diez minutos y
  habría dejado el hueco abierto para el siguiente acto, así que
  `tests/contracts/test_evidencia_deja_verbo.py` deriva **las dos poblaciones**: las tablas
  append-only salen de `db/schema.sql` contando los triggers cuya función es
  `forbid_update_delete()` —es el propio esquema el que declara qué es evidencia— y los
  manejadores salen del árbol de sintaxis de `routers/`. La exigencia se comprueba **dentro de la
  función**: un `audit_async` en el manejador de al lado no audita este acto.
  **Y la lista de excepciones quedó VACÍA**, que era el mejor resultado posible: de los doce
  manejadores que escriben evidencia, once ya dejaban verbo y el que no se arregló en vez de
  declararse excepción. El vacío tiene su propio test — una lista de excepciones que puede crecer
  sola no es una excepción.
  **Lo que costó y conviene no repetir: este censo se quedó CIEGO DOS VECES mientras se
  escribía**, y las dos veces pasó en verde justo sobre el defecto que venía a cazar. La primera,
  por leer solo las asignaciones `NOMBRE = "INSERT INTO …"` y no el SQL que los módulos de
  `queries` construyen **dentro de funciones**: veía cuatro manejadores de los doce. La segunda,
  por buscar `alias.nombre` cuando los módulos de `queries` se importan con alias
  (`from … import dictamens as q`): con la primera corregida seguía sin ver `sign_dictamen`. Un
  censo se prueba **contra el defecto que ya sabes que existe**; si no lo encuentra, el censo está
  roto, no el código.

### [x] T-5.21 · No hay **censo de dato viejo** en la app móvil — `SOFTWARE` · **CERRADA 2026-09-03**
> La consola está resuelta y bien: un censo derivado del árbol obliga al componente siguiente a
> tener su prueba de los cuatro estados o a aparecer en una lista de deuda comparada **por
> igualdad**. Fuera de la consola es muestreo.
>
> En móvil el componente de marco existe y está probado, pero **no hay censo**: tres archivos usan
> el envoltorio que conoce la frescura y **seis consultan al servidor sin él**. Y hay un caso
> concreto: la lista del pase de vida solo declara el dato viejo **si el refetch está fallando**,
> así que un pase de lista de hace diez minutos con red sana **se pinta como fresco**.
>
> Es justo la pantalla que se enseña en una demo, y justo el fallo que la regla de oro 7 existe
> para impedir.
- **Componente:** mobile · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que en el teléfono ningún número se pinte como vivo sin poder demostrarlo.
- **Criterios de aceptación:**
  - [x] Censo derivado equivalente al de la consola: quién posee dato de servidor se deriva de los
        transportes, y se cruza contra quién tiene la prueba de los cuatro estados.
        **Ya existía** (`T-2.111`); lo que faltaba, y es lo que se hizo, es el censo sobre la
        SEMÁNTICA de la frescura.
  - [x] Comparación **por igualdad** contra la deuda declarada: la pantalla siguiente escribe su
        prueba o entra en una lista a la vista.
  - [x] El caso del pase de vida corregido: la edad se declara siempre, no solo cuando falla el
        refetch.
  - [x] Guarda anti-vacuidad: el censo declara cuántas pantallas espera y cero no vale.
- **PRIMERO, LA CORRECCIÓN DE LA FICHA.** Su premisa era **falsa**: «en móvil no hay censo» — y
  sí lo había, `mobile/src/screenStateCensus.test.ts`, de `T-2.111`, derivado del sistema de
  ficheros de `expo-router` y con sus cuatro listas de deuda vacías. Existía en el commit sobre el
  que se hizo la auditoría (`df13599`), así que el hallazgo estaba mal. Lo mismo el conteo «tres
  usan el envoltorio y seis consultan sin él»: los seis que consultan y **renderizan** usan el
  marco; los otros son hooks y observadores, que no pintan nada.
- **Y AHORA LO QUE SÍ ERA CIERTO, que resultó ser mucho peor.** La tercera viñeta —«el pase de
  vida solo declara el dato viejo si el refetch está fallando»— era exacta, y no era un caso: era
  **el significado de `stale` en toda la app**. `useAlertState` lo calculaba como
  `isError && data !== undefined` y **siete pantallas lo heredaban**; `lista.tsx` y `dictamen.tsx`
  hacían lo propio con `failureCount > 0`; `AccountScreen` y `camera.tsx`, con `isError`. **Nueve
  superficies**: con red sana y un `mobile_state` de hace diez minutos, todas esas señales valen
  `false` y la pantalla afirma frescura.
  La peor de las nueve no es el pase de lista: es `camera.tsx`. Su frescura acaba **horneada en el
  píxel** de una fotografía forense y entra en el sha256, así que un «METADATOS RETENIDOS» que
  solo aparecía al fallar la consulta dejaba fotos con metadatos de hace diez minutos **sin marca
  ninguna** — y esa foto va a un dictamen.
- **Cómo se cerró (2026-09-03).**
  `src/ui/useStaleSince.ts`: la edad sale del **reloj**, y el umbral **del intervalo de poll de
  cada pantalla** — «viejo» no es una cantidad de segundos, es «ya deberíamos haber refrescado y
  no lo hicimos». Tres pollos perdidos: uno es jitter, tres son un patrón. Una pantalla que
  consulta cada 5 s y otra cada 30 envejecen a ritmos distintos, y un umbral fijo mentiría en una
  de las dos. El hook trae reloj propio: sin el tic, un dato fresco al montar seguiría pintándose
  fresco para siempre.
  **El censo gana TRES reglas nuevas**, y las tres salieron de encontrarse el defecto en tres
  formas distintas: la expresión del marco, la propiedad que un hook DEVUELVE, y una **constante
  local** con nombre de frescura (`camera.tsx` pasaba el nombre de la constante al marco y la
  señal de fallo quedaba un salto más atrás). Las dos primeras nacieron ciegas y hubo que
  corregirlas: la del productor iba dentro del bucle de rutas y el defecto vivía en `features/`;
  la del marco, lo mismo, y por eso `AccountScreen` lo encontré leyendo y no el censo.
  **Y once fixtures pasaron de un epoch clavado en 2027 a contar desde `Date.now()`.** Desde que
  la frescura sale del reloj, un `dataUpdatedAt` en el futuro sale «fresco» y el estado `stale`
  dejaba de materializarse. La razón por la que un instante futuro **sí** debe salir fresco está
  escrita en el módulo: `dataUpdatedAt` lo pone react-query con el reloj del propio dispositivo,
  el mismo que da el «ahora», así que en campo no puede haber desfase — un valor futuro solo
  aparece en un test que clava un epoch. Con él, ocho tests que simulaban «viejo» **haciendo
  fallar la consulta** estaban probando el defecto; ahora prueban el tiempo.

### [~] T-5.22 · La latencia del reflejo **solo existe como prosa** — `SOFTWARE` + `GATE-HW` · **SOFTWARE CERRADO 2026-09-03 · espera `GATE-HW`**
> Es la cifra de venta más citada del producto, medida dos veces con hardware real: **6.65 ms el
> 2026-07-14** y **4.16 ms en frío el 2026-07-31**. Y su evidencia primaria son **ocho documentos
> con el número escrito a mano**. No hay journal, ni acta, ni captura del estado del gabinete, ni
> fixture. Un cliente que pida la evidencia recibe un archivo de texto.
>
> Además el guardián de esa latencia **reporta el mejor de cinco intentos**, no un percentil, tras
> haber fallado aproximadamente una de cada ocho corridas en integración continua. Y en el
> gabinete vivo el campo de latencia del reflejo está en nulo: la medición no está viva, es
> histórica.
>
> **El p95 del tramo hacia la consola tampoco se midió nunca**: lo que se vende como *"medido 214
> ms"* es una sola observación, y una cita de percentil del tablero apunta a una línea que no lo
> contiene.
- **Componente:** edge + takab-docs · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que la cifra que se vende tenga detrás un artefacto y no una frase.
- **Criterios de aceptación:**
  - [x] La medición del reflejo se persiste como artefacto reproducible en el gabinete (captura
        fechada del estado, o registro dedicado), no solo como línea de journal.
  - [x] Los ~~ocho~~ **nueve** documentos citan **una fuente**, no nueve copias del número.
  - [x] Donde se declara un percentil, o se mide o se dice que es una observación única. La cita
        rota del tablero se corrige o se retira.
  - [ ] `GATE-HW`: la siguiente sesión presencial captura la evidencia con el procedimiento nuevo.
        **Es lo único que queda, y no lo cierra el software** — ver
        [`MEDICIONES-TAKAB.md`](MEDICIONES-TAKAB.md) §2 y el runbook §B.1.bis.
- **Cómo se cerró la mitad de software (2026-09-03).**
  **El acta** (`edge/takab_edge/audit/reflejo.py`): cada flanco del WR-1 deja una línea fechada
  con la latencia que midió el dueño de los pines **y el estado de los cinco canales en ese
  instante**. Eso es lo que convierte el número en evidencia: no «tardó 4 ms», sino «tardó 4 ms
  **y estos relés quedaron así**», que es algo que alguien puede discutir.
  **La escribe el SUPERVISOR, no el dueño de los pines**, y no es un detalle: el reflejo vive
  entero dentro de un proceso que es mínimo y auditable a propósito (regla de oro 4), y meterle
  un fichero dentro sería pagar el acta con el camino de vida. El módulo de auditoría ya dejaba
  escrito que registrar el reflejo «es tarea aparte»; **esta era esa tarea**. El acta es advisory
  de punta a punta: si el disco falla se cuenta y se sigue.
  **`MEDICIONES-TAKAB.md` es la fuente única**, y `api/tests/test_mediciones.py` la sostiene con
  una regla que no es «prohibido repetir la cifra» —hay documentos que **deben** citarla— sino
  **«quien la cite tiene que enlazar aquí»**. El día que el número cambie, un `git grep` del
  enlace da la lista exacta de quién hay que revisar; hoy esa lista no existía.
  **Tres cosas que aparecieron al hacerlo.**
  (1) **No eran ocho documentos: eran NUEVE.** El barrido encontró uno más que el informe
  (`PLAN-MAESTRO-TAKAB.md`, con el `214 ms`). Es la diferencia entre contar a mano y derivar.
  (2) **El `214 ms` se vendía como medición y se citaba como si fuera el percentil.** No lo es:
  es **una observación**, y el `p95 < 2 s` que el blueprint declara **nunca se ha medido**. Las
  tres cifras quedan rotuladas como observaciones únicas allí donde se citan.
  (3) **Y las dos cifras del reflejo se tomaron ANTES de que el acta existiera**, así que **no
  tienen artefacto** — y la tabla lo dice con todas las letras en su columna «Artefacto:
  ninguno». Cerrar la ficha entera habría exigido borrar esa fila; dejarla es lo que hace que
  `GATE-HW` siga significando algo.
  **Lo que NO se tocó, y por qué:** el guardián de CI (`test_e2e.py`) sigue reportando el mejor de
  cinco intentos. El informe lo listaba como defecto y **no lo es**: `T-2.170` lo razona como
  tolerancia **al instrumento** —un runner compartido mide código + planificación, y el ruido
  solo suma—, publica la serie completa también en verde y avisa cuando hizo falta reintentar.
  Además mide **pines simulados**: no acredita nada del hardware y ahora el documento lo dice.

### [x] T-5.23 · No existe **espectrograma** en el dictamen técnico — `SOFTWARE` · **CERRADA 2026-09-03**
> Confirmado abriendo el código: lo que hay es **un solo espectro de amplitud** de la ventana
> entera, con resta de continua y ventana de Hann. Cero coincidencias de transformada por ventanas
> en todo el árbol.
>
> **Para un cliente no técnico no aporta**: es una figura que exige formación y compite con el
> croquis y el semáforo, que son lo que decide. **Para el pericial sí**: separar la llegada de las
> dos ondas y ver si el edificio respondió en su periodo fundamental es exactamente lo que un
> espectro global promedia y esconde.
>
> Por eso va en la tanda tres, y **detrás** de que la onda cruda llegue a existir en la nube
> (`T-3.11.c`): sin registro archivado no hay nada que transformar.
- **Componente:** api · **Depende de:** T-3.11.c *(para el DATO, no para el código — ver abajo)* ·
  **Prioridad: BAJA**
- **Objetivo:** una figura tiempo-frecuencia en el documento pericial, con la misma honestidad que
  el resto.
- **Criterios de aceptación:**
  - [x] Espectrograma del canal dominante, con sus ejes rotulados y su ventana declarada.
  - [x] Sin registro archivado, **el mismo texto de ausencia** que ya usa la sección de onda cruda:
        no un hueco.
  - [x] El PDF sigue siendo determinista: mismo modelo, mismos bytes.
  - [x] La figura **no promete** una escala que no existe, como ya vigila la guarda del mapa.
- **La dependencia SE VERIFICÓ, y es real — pero no bloquea el código.** `T-3.11.c` se lee como
  «el worker de CCTV», y suena a que no tiene nada que ver. Sí lo tiene:
  `api/src/takab_api/backfill/objects.py` es **el único productor** de la fila de evidencia
  `kind='miniseed'`, y ése es el worker que no está en el compose de la nube. O sea que en
  producción **hoy no hay miniSEED archivado que transformar**, y la figura tomará siempre el
  camino de la ausencia hasta que `T-3.11.c` se despliegue. La ficha ya lo anticipaba en su
  criterio 2, y por eso el código se puede cerrar: está construido para declarar el hueco.
- **Cómo se cerró (2026-09-03).**
  `dictamen/espectrograma.py`: transformada por ventanas de Hann con solape del 50 % sobre el
  **mismo canal dominante** que el espectro y la duración — dos figuras del mismo dictamen que
  describieran trazas distintas serían una trampa para quien las compare, que es la razón que ya
  dejó escrita `T-3.14`.
  **La prueba que justifica la figura entera** es `test_SEPARA_en_el_tiempo_dos_frecuencias_que_el
  _espectro_global_promedia`: media traza a 5 Hz y media a 20 Hz. El espectro global las vería a
  las dos y no diría cuándo; el espectrograma tiene que enseñar 5 Hz al principio y 20 al final.
  Si eso falla, la figura no aporta nada y sobra.
  **Cuatro decisiones que llevan su razón escrita.**
  (1) **La escala es RELATIVA y la leyenda lo dice.** El crudo llega en cuentas del ADC y la
  calibración instrumental sigue pendiente: una barra con unidades prometería una calibración que
  nadie hizo. Es la misma guarda que vigila el mapa de sacudida.
  (2) **La continua se resta POR VENTANA.** El crudo del RS4D trae millones de cuentas de DC —el
  hallazgo de `T-2.25`—, y sin restarla cada ventana sale aplanada. Hay test con 3.77 M de cuentas
  encima.
  (3) **Una traza muerta devuelve ceros, no una figura encendida.** Normalizar dividiendo por cero
  pintaría ruido como si fuera señal: de las dos mentiras posibles, es la cara.
  (4) **Un registro largo se diezma tomando columnas equiespaciadas, no truncando.** Truncar
  dejaría fuera la coda, que es media pregunta de un peritaje.
  **Y la leyenda se extrajo a función pura** para poder probarla: el flujo de contenido de un PDF
  va comprimido, así que un test que buscara el rótulo en los bytes acabaría probando `fpdf2` en
  vez del enunciado. Junto a ella, una guarda anti-vacuidad que compara el MISMO documento con y
  sin figura — «el ejecutivo pesa menos que el técnico» habría pasado en verde aunque no se
  dibujara nada.

### [x] T-5.24 · El reloj y la pérdida de paquetes **callan cuando deberían gritar** — `SOFTWARE` · **CERRADA 2026-09-03**
> Dos huecos de la misma familia, los dos en el eje de "salud del sistema":
>
> - **El reloj.** El desfase se mide de verdad con el demonio de reloj, viaja, se persiste y
>   degrada el estado del sitio en la consola. Pero el panel del gabinete **lo pinta siempre en
>   verde**: no usa el ayudante de umbrales que todas las filas vecinas sí usan, así que un desfase
>   de cinco segundos se ve igual que uno de tres milisegundos. Y **ninguna de las 13 alarmas de la
>   nube es de reloj**: se ve solo si alguien está mirando la pantalla. Sin hora confiable, ninguna
>   evidencia sirve.
> - **La pérdida de paquetes.** Viaja a la nube y **se descarta a propósito** en la ingesta, con la
>   razón escrita. Consecuencia: el centro de operaciones **no puede ver la pérdida de paquetes de
>   ningún gabinete**; para diagnosticar un enlace degradado hay que ir al sitio o abrir el panel
>   por red local.
- **Componente:** edge + api + infra · **Depende de:** nada · **Prioridad: BAJA**
- **Objetivo:** que las dos señales que dicen si la evidencia vale se puedan ver y despierten a
  alguien.
- **Criterios de aceptación:**
  - [x] El panel usa el mismo ayudante de umbrales que sus filas vecinas para el desfase de reloj.
  - [x] Alarma de desfase en la nube, con el mismo criterio que las demás: vigila la **ausencia**
        además del valor, y publica su cero para no quedarse muda.
  - [x] La pérdida de paquetes gana columna y llega al centro de operaciones, o se declara por
        escrito **por qué** sigue siendo local — pero no las dos cosas a la vez.
  - [x] Test de que el gabinete sin dato de reloj **lo declara** en vez de pintarse en verde.
- **Cómo se cerró (2026-09-03).**
  **El reloj, en las cuatro superficies que hablan de él.** La fila del panel del gabinete usaba
  el único ternario propio de la tabla (`null ? ámbar : verde`), así que un desfase de **cinco
  segundos** se pintaba tan verde como uno de tres milisegundos; ahora usa el mismo `col()` que
  sus vecinas, sobre el **valor absoluto** —un reloj adelantado miente igual que uno atrasado, y
  el ternario viejo ni miraba el signo—, con ámbar en 100 ms y rojo en 1 s, que es donde el sello
  deja de poder ordenar dos hechos del mismo segundo.
  **Y apareció un cuarto espejo que nadie había contado:** el badge `NTP OFFSET` del SOC estaba en
  **50 ms**, o sea que se ponía rojo mientras la misma consola declaraba el sitio OPERATIVO y el
  panel del Pi lo pintaba en ámbar. Los cuatro (`Settings.fleet_ntp_offset_max_ms`, el panel, el
  badge y la alarma) los compara ahora por igualdad `api/tests/contracts/test_umbral_de_reloj.py`,
  derivándolos de sus tres lenguajes en vez de confiar en que alguien recuerde moverlos juntos.
  El censo se comprobó **contra el defecto que ya existía**: devolviendo el badge a 50 se pone
  rojo y nombra los cuatro valores.
  **La alarma de la nube: `missing`, no `breaching`, y la razón es un hecho del código.**
  `MaxClockDriftMs` sale de la **misma llamada** que `GhostGatewaysAlive` —`GhostGauge` arma las
  tres cifras bajo un solo `try` y las manda en un único `put_metric_data`—, así que las dos
  alarmas se quedan sin datos a la vez y por la misma causa. Con `breaching`, el correo afirmaría
  que un reloj se salió de rango sin que nadie haya leído un solo latido, que es exactamente la
  mentira que este módulo ya rechazó para su gemela. Va con `insufficient_data_actions`, y eso sí
  manda dos correos por una causa: es deliberado y no es el defecto de `ec2_cpu` —allí el segundo
  correo nombraba la causa **equivocada**—, sino dos que dicen la misma verdad, «no sé nada»,
  sobre dos cosas distintas. El reparto de `sensor_mute` (delegar la ausencia en otra alarma) no
  sirve aquí: el correo de fantasmas no menciona el reloj.
  **Y el repo cazó al autor:** una alarma nueva no basta con escribirla. El censo
  `test_muting.py` deriva las alarmas del Terraform y exige que cada una esté clasificada como
  silenciable o no en `ops/muting.ALARM_CATALOG` — `clock_drift` entró como **intocable**, y no
  por el default: comparte publicador con `ghost_gateways`, así que una ventana de plataforma
  mandará **dos correos de INSUFFICIENT_DATA por una sola causa**, que es un argumento real para
  callarla. No basta, porque en esa misma ventana la alarma también puede sonar **por su valor**,
  y un reloj que se sale de rango mientras se mantiene la nube es un hallazgo ajeno que la
  ventana taparía. La lista de intocables se enumera a mano **a propósito** —esa fricción es la
  decisión—, así que la razón queda escrita en los dos sitios.
  **El cero se publica**, que es lo que hace que el silencio signifique una sola cosa. La consulta
  toma el **último** latido de cada gabinete —un desfase ya corregido no puede seguir alarmando—,
  excluye al retirado (de ése habla la otra métrica) y al que lleva más que `SIN ENLACE` sin latir
  (de ése habla `gateway_offline`), y **excluye el `NULL`**: no saber la hora no es tenerla bien,
  y contarlo como cero fabricaría la buena noticia.
  **La pérdida de paquetes: se eligió el camino de exponerla, no el de justificar el hueco.** La
  ingesta la tiraba con la razón escrita —no había columna—, así que ahora la hay (`0059`), el
  handler la persiste y llega a `/fleet` y a la tarjeta de la consola, pegada al lag porque es el
  **mismo enlace** y se diagnostican juntos: un lag que sube con pérdida al 0 % es otro problema
  que uno que sube perdiendo el 12 %.
  **Y al exponerla apareció una mentira que hasta hoy moría en el gabinete:** el edge devolvía
  `0.0` tanto cuando no tenía cliente SeedLink como cuando aún no había visto un solo paquete —y
  un cero en un porcentaje de pérdida se lee «enlace perfecto», dicho por quien no ha mirado.
  Mientras la cifra se quedaba en el Pi era casi inocuo; desde que **viaja y pinta una tarjeta**,
  no. Ahora los dos casos son `None` ⇒ `s/d`, con su prueba, su esquema publicado relajado a
  `null` y el `%.1f%%` del log de transición convertido en `%s` — que es literalmente el tropiezo
  que ya dio `relays` al ganar su «no pude preguntar», y por el mismo camino. Un firmware viejo
  que siga mandando su número entra igual.
  **Lo que deliberadamente NO hace es degradar el estado del sitio.** Y la razón hay que decirla
  con precisión, porque un umbral SÍ existe: el panel del gabinete pinta ámbar al 1 % y rojo al
  10 %. Pero ése es consejo para quien está de pie delante del Pi. Degradar `derived_state`
  arrastra la pill del SOC, la app móvil y el reparto de alarmas — ese umbral de **servidor** no
  lo ha elegido nadie. Por lo mismo la pill de la consola no se tiñe: `LinkPill` ya llevaba
  escrita la regla («el semáforo fino por métrica NO existe aquí, los umbrales viven solo en el
  servidor») y es buena. El día que se decida, entra en `fleet_degrade_reasons` con su ajuste,
  como las demás.
### [x] T-5.25 · El silencio **no alcanza a los gabinetes secundarios** — `SOFTWARE` · **CERRADA 2026-09-03**
> El silencio del operador está bien resuelto en el gabinete que lo recibe: corta la sirena, corta
> el voceo, deja el estrobo, no toca gas ni puertas, y una alarma nueva vuelve a sonar. Doce tests
> lo defienden.
>
> Pero en un sitio con varios gabinetes, el principal propaga la activación a los secundarios por
> radio y **solo el cierre de alerta propaga la orden inversa**. El silencio no. El operador calla
> el suyo y **el edificio sigue sonando**.
>
> Es el mismo riesgo de credibilidad que motivó la decisión de la ruta de hardware: una sirena que
> nadie puede callar durante una falsa alarma quema la obediencia a la siguiente alerta.
- **Componente:** edge · **Depende de:** nada · **Prioridad: BAJA**
- **Objetivo:** que silenciar signifique lo mismo en todo el inmueble.
- **Criterios de aceptación:**
  - [x] El silencio se propaga a los nodos secundarios, y **solo** el silencio: la protección no
        audible de cada nodo no se toca.
  - [x] Un nodo que no confirma **se declara** en el panel: silenciar cuatro de cinco no es
        silenciar.
  - [x] Una alarma nueva vuelve a sonar en todos, como ya ocurre en el principal.
  - [x] Test con dos nodos que mida el estado eléctrico de ambos, no la orden enviada.
- **Cómo se cerró (2026-09-03).**
  **La premisa se verificó y era exacta:** `reset_alert()` propagaba `clear` y la prueba local
  propagaba `test`; `silence()` no propagaba nada.
  **Pero el enganche correcto no era el botón del panel.** `silence_audibles()` la disparan DOS
  orígenes —el panel LAN y el **pulsador físico** del gabinete— y el pulsador es el que aprieta de
  verdad quien está delante de una falsa alarma. Colgarlo del panel habría dejado el edificio
  sonando **por el camino más probable**, con un test en verde. Va por la costura de eventos
  (`gpio_link.subscribe("silence", …)`), que cubre los dos y cualquier origen futuro.
  **`SILENCE` es un tipo de mensaje propio, no un `ALARM_ACT` sin el bit de sirena**, y las dos
  razones apuntaban al mismo sitio —el peor—: (1) el contrato publicado dice que `ALARM_ACT`
  **enciende**, así que un firmware escrito contra esa frase engancha la sirena y no la suelta con
  otro `ALARM_ACT`; (2) en el emisor, dos `ALARM_ACT` seguidos **SUMAN** flags a propósito (los
  comandos de red llegan por canal separado), de modo que un silencio disfrazado de activación se
  lo tragaría el `merged |= pending["flags"]`. La ambigüedad caía del lado de «la sirena sigue
  sonando». Es **aditivo sobre v1** —el layout no cambia, `ver` sigue en `0x01`— y un firmware que
  no conozca el tipo 6 lo rechaza y **no ackea**, que es la verdad y no un silencio fingido.
  **Solo el silencio:** la orden lleva `alarm_active` y el estrobo puestos, así que la alerta sigue
  viva en cada nodo y su protección no audible no se toca. Apagar el estrobo convertiría «callar la
  sirena» en **borrar la alerta** para quien está dentro, que es peor que no poder callarla.
  **El re-armado también viaja, y solo si hay algo que re-armar.** El observador recibe un simple
  booleano; propagar una activación sin consultar el enclave encendería sirenas en otra nave a
  partir de un botón que solo dice «ya no silencio». Tiene su propio test.
  **El panel dejó de decir `SIN ACK` a secas.** Ese rótulo no distingue un test perdido —da igual—
  de un **silencio** perdido, que significa que ese nodo sigue sonando mientras el operador cree
  que calló el edificio: ahora dice `SIGUE SONANDO · SILENCIO SIN CONFIRMAR`, y `SILENCIADO` en el
  que sí confirmó. Silenciar cuatro de cinco no es silenciar.
  **El criterio 4 obligó a construir lo que faltaba.** El ESP32 simulado guardaba `flags_seen` —la
  última **orden**—, que no es el estado eléctrico: un test posterior la pisa, y una orden que
  llegó no dice qué quedó encendido. Ahora modela sus dos relés con las cuatro reglas del firmware
  (`ALARM_ACT` suma · `SILENCE` apaga lo audible · `CLEAR` apaga todo · `TEST` no toca nada), así
  que es a la vez el banco de pruebas de esta ficha y la **especificación ejecutable** del firmware
  en C. El test de dos nodos mide `siren_on` de ambos; con el enganche desactivado falla diciendo
  `SIGUE SONANDO (sirenas: True, True)`, que es el defecto textual de la ficha.
  **Y el vector dorado del silencio quedó atado al documento:** los bytes viven en
  `LORA-SECUNDARIOS.md §3` (lo que lee quien escriba el firmware) y en el test (lo que corre CI),
  y un test nuevo comprueba que son los mismos — un vector correcto en un solo sitio es peor que
  no tenerlo.
### [x] T-5.26 · La huella del PDF se imprime **a la mitad**, y la ficha de estación está partida — `SOFTWARE` · **CERRADA 2026-09-03**
> Dos defectos de superficie que se arreglan juntos porque los dos son "el dato está y no se ve":
>
> - **La huella.** La cadena de custodia imprime el sha256 truncado a **32 de 64** caracteres,
>   mientras la portada del mismo documento instruye verificarlo con la herramienta estándar. Con
>   medio hash no se puede. (El hash de contenido de la portada sí va entero; es el de cada objeto
>   de evidencia el que se corta.) Además el documento ejecutivo **no lleva huella de contenido**:
>   el que lee quien decide no trae con qué verificarse.
> - **La ficha de estación.** Modelo, versión de firmware, serial y estado del respaldo eléctrico
>   **no están en el contrato del mapa**; para verlos hay que abandonar la consola e ir a Flota,
>   que en una demo es un salto de pantalla en el peor momento. Y el panel del propio gabinete no
>   muestra su serial ni el código de estación del sensor, así que quien está de pie delante no
>   puede correlacionarlo con la consola sin abrir el archivo de entorno.
- **Componente:** api + web + edge · **Depende de:** nada · **Prioridad: BAJA**
- **Objetivo:** que un dato que el sistema ya tiene no se pierda en el último centímetro.
- **Criterios de aceptación:**
  - [x] La cadena de custodia imprime el hash completo, o la portada deja de instruir verificarlo
        — no las dos cosas.
  - [x] El documento ejecutivo lleva su huella de contenido.
  - [x] La ficha del mapa gana los campos de identidad de hardware, con el mismo criterio honesto
        que ya usa el medidor de respaldo: sin dato, lo dice.
  - [x] El panel del gabinete declara su serial y el código de estación del sensor.
  - [x] Los PDF siguen siendo deterministas.
- **Cómo se cerró (2026-09-03).**
  **La huella, y una tercera que el informe no había visto.** El sha256 de cada objeto de
  evidencia salía a **32 de 64** caracteres, y la custodia del **vídeo** a **16 de 64** con puntos
  suspensivos — honesta sobre estar cortada e igual de inútil para verificar, y son custodia
  igual que el miniSEED: lo dice esa misma sección del documento cuatro líneas más arriba. Las
  dos van enteras. No había razón de espacio: 64 hex miden **108.7 mm de los 128** que deja la
  columna, así que caben en una línea.
  **La forma obvia de probarlo PASA EN VERDE SOBRE EL DEFECTO, y se descubrió por mutación.** El
  atajo era «cambio la cola del hash y exijo que el PDF cambie»; pero cualquier cambio del modelo
  mueve el `content_sha256` que la **portada sí imprime**, así que los dos documentos salen
  distintos aunque la custodia siga cortada. Y la vía directa tampoco existe: el flujo del PDF va
  comprimido **y** con fuentes embebidas, o sea que el texto viaja como índices de glifo y el hash
  no aparece en los bytes ni entero ni cortado (comprobado). Se cierra donde se decide: la regla
  vive en una función pura (`huella_de_custodia`) y un **barrido del render** prohíbe volver a
  recortar un hash en el sitio donde se imprime, con su guarda anti-vacuidad —son DOS llamadas—
  para que el barrido no siga en verde sobre un módulo que dejó de usarla. Las dos mutaciones
  comprobadas.
  **El ejecutivo ya lleva su huella.** Es el documento que lee **quien decide** y era el único de
  los dos sin con qué verificarse. Es la MISMA huella en ambos —sale del contenido, no del
  archivo—, y eso es justo lo que permite comprobar que el resumen y el pericial hablan del mismo
  incidente sin abrirlos a la vez; el texto lo dice para que nadie la confunda con el hash del
  fichero.
  **La ficha del mapa gana la identidad del hardware:** serial, versión de firmware, modelo del
  sismógrafo y respaldo eléctrico. Dos de esos campos **ya viajaban** en la consulta del mapa
  —`power_status` y `battery_pct`, que usa `derive_fleet_state`— y se tiraban al construir la
  respuesta: el dato estaba y no se veía. El modelo sale del mismo lateral que ya barría los
  sensores activos, con `string_agg DISTINCT`: con uno sale su modelo y con dos distintos salen
  los dos, porque inventar «el» modelo de un sitio mixto sería peor que enseñar ambos. Sin dato,
  `null` ⇒ **S/D** en el panel, y `respaldoLegible(null, …)` devuelve `S/D` en vez de «LÍNEA»: un
  gabinete que no ha reportado no está enchufado a la red, es que no ha dicho nada.
  **El panel del gabinete declara su identidad correlacionable:** el nombre con el que la **nube**
  lo conoce y el **código de estación** del sismógrafo. Salen de `thing_name` y de
  `seedlink_station_code` —que ya resuelven sus propios fallbacks— y no de dos cadenas escritas
  aquí, que acabarían divergiendo. Sin configurar dice `S/D`, no un hueco.
  **Y el censo del panel cazó al autor otra vez:** añadir dos campos a `status()` sin tocar el
  fixture del render puso en rojo `test_el_fixture_del_censo_es_el_status_real_hasta_el_ultimo_
  anidado`, que compara los dos **recursivamente**. Es la guarda que impide que el panel se pruebe
  contra un contrato que ya no existe.
### [x] T-5.27 · Las **dos guardas que faltan** — `SOFTWARE` · **CERRADA 2026-09-03**
> Dos propiedades que hoy se cumplen **por construcción** y que nada impediría romper mañana:
>
> - **La cifra externa fuera del veredicto.** El desacoplamiento es genuino y estructural: el tipo
>   de entrada del veredicto tiene siete campos y **ninguno admite** magnitud ni catálogo, y el
>   módulo no importa nada de forense. Pero los catorce tests del motor afirman lo que la regla
>   **sí** hace; **ninguno afirma que el catálogo no la mueve**. Añadir el campo mañana no pondría
>   nada en rojo. Con `T-5.10` y `T-5.11` entrando, esta guarda deja de ser opcional.
> - **El folio fuera del prompt.** La lista blanca de lo que sale hacia el proveedor de prosa es
>   real y no deja pasar **ni un dato personal**: ni notas de ocupantes, ni coordenadas, ni
>   firmante, ni identificador de dispositivo. Pero el folio —que viaja entero— contiene el código
>   del sitio y los ocho primeros hex del identificador del incidente, y el docstring del módulo
>   afirma que ese identificador **nunca sale**. Y el test que lo defendería **borra el folio antes
>   de afirmar**. Es un identificador estable y correlacionable entre dictámenes, no un dato
>   personal — pero la lista blanca dice una cosa y hace otra.
- **Componente:** api (tests) · **Depende de:** nada · **Prioridad: BAJA**
- **Objetivo:** que las dos propiedades dejen de depender de que nadie las rompa.
- **Criterios de aceptación:**
  - [x] Contract-test que fije por **igualdad** los campos de la entrada del veredicto, y que
        prohíba por barrido del árbol de sintaxis que el motor de reglas o el del dictamen importen
        el módulo forense o el esquema del catálogo.
  - [x] Se decide y se escribe qué hacer con el folio: o el prompt recibe un folio recortado, o el
        docstring deja de afirmar lo que no cumple. **Lo que no puede quedarse es el test que
        esquiva el caso.**
  - [x] El test del identificador deja de borrar el folio antes de afirmar.
  - [x] Guarda de no-vacuidad en ambos: cada uno declara cuántos elementos espera.
- **Cómo se cerró (2026-09-03).**
  **La cifra externa: por igualdad Y por barrido, porque cada mitad tapa un agujero distinto.**
  `set(campos de EvalInput) == LOS_SIETE` se pone rojo al **añadir** un campo — un
  `assert "magnitude" not in campos` solo cazaría ese nombre exacto y dejaría pasar
  `catalog_magnitude` o `mag_ssn`. Y un campo no es la única puerta: el motor podría importarse
  la cifra y consultarla por su cuenta, así que el barrido del AST prohíbe los cinco módulos de
  fuente externa en los **dos** ficheros que producen el veredicto.
  **Los dos son `dictamen/rules.py` y `dictamen/service.py`, y `builder.py` NO está** — no es un
  olvido y hay que decirlo, porque el enunciado se lee como si fueran otros. `builder.py` arma el
  **documento** y sí importa forense **a propósito**: el informe enseña los hechos medidos junto
  al dictamen. Lo que no puede pasar es que esos hechos entren en la **decisión**, y la decisión se
  toma en esos dos ficheros — `service.py` es además el **único** sitio del repo que construye un
  `EvalInput`. Ese import real de `builder.py` se usa como **contraprueba del barrido**: si el
  lector de imports no lo viera, tampoco vería uno nuevo en el motor.
  **El folio: se decidió DEJARLO entero y arreglar la afirmación, no recortarlo.** Un folio es
  `TKB-<código>-<fecha>-<8 hex del incident_id>-<E|T>`, y es el **nombre público del documento**
  —`folio_of` lo dice: «se imprime y se cita por teléfono»—. Recortarlo haría que la prosa nombrara
  un documento que no existe, y quien lo teclee no encontraría nada. Lo que viaja no es un dato
  personal: es un identificador de documento, estable y correlacionable entre dictámenes del mismo
  incidente, que es justo para lo que se diseñó. Lo que sigue sin salir por ninguna vía es el
  `incident_id` **completo** ni el `event_id`. El docstring de la allowlist ya lo dice así, con las
  dos razones.
  **Y el test dejó de esquivar el caso.** Borraba el folio antes de mirar (`.replace(folio, "")`),
  o sea que quitaba de en medio **la única vía** por la que el identificador salía; encima el
  fixture traía un folio literal cuyos hex no tenían nada que ver con su `incident_id`, así que el
  caso peligroso ni siquiera estaba representado. Ahora el folio se **deriva con `folio_of`**, como
  en producción, y se afirma en positivo: el UUID entero no viaja, los 8 hex sí, y **solo dentro
  del folio** — si aparecieran por otra vía, el test lo dice.
  **No-vacuidad en los dos, con su número escrito.** El del veredicto declara 7 campos, 2
  productores y 5 fuentes prohibidas, y comprueba que el lector de imports no devuelve vacío. El
  del folio declara los 29 campos de `NarrativeFacts` —lo que cierra el hueco que el docstring no
  cubría: un campo nuevo del `ReportModel` queda fuera por omisión, pero uno **cableado en
  `facts_from`** saldría a la red en silencio— y exige que el payload serializado no esté vacío,
  porque sobre un payload vacío todos los `not in` pasan en verde.
  **Las cuatro mutaciones comprobadas:** añadir `magnitude` a `EvalInput` y colar el import del
  catálogo en `rules.py` (2 rojos); filtrar el `incident_id` completo (3 rojos) y recortar el folio
  en silencio (2 rojos).
### [x] T-5.28 · El **espejo de la matriz RBAC** en web lleva 16 celdas divergentes — `SOFTWARE` · **CERRADA 2026-09-03**
> **No sale de la auditoría: apareció ejecutándola** (al cerrar `T-5.12`, el 2026-09-02).
>
> `web/src/test-utils/meFixtures.ts` se declara a sí mismo *"espejo SOLO PARA TESTS de
> `api/src/takab_api/auth/matrix.py`"* y añade: *"Si la matriz cambia en el backend, este archivo
> debe cambiar con ella"*. **Nada lo comprueba.** Es exactamente el patrón que
> `TRASPASO-SESION.md §4` ya nombró — *un censo que enumera a mano acaba divergiendo* — y ya
> divergió **dieciséis veces**:
>
> | Acción | Roles a los que la matriz REAL se la da y el espejo no |
> |---|---|
> | `cctv_read` | superadmin, tenant_admin, soc_operator, inspector, building_admin |
> | `cctv_video` | superadmin, tenant_admin, soc_operator, building_admin |
> | `manage_privacy_notice` / `manage_privacy_erasure` | superadmin, tenant_admin |
> | ~~`read_audit`~~ | ~~takab_support~~ · **FALSA, ver el cierre** |
> | ~~`checkin_submit` / `panic_vote`~~ | ~~occupant~~ · **FALSA, ver el cierre** |
>
> **⚠️ La tabla de arriba se midió mal al ficharla: eran TRECE celdas, no dieciséis.** Se deja
> intacta —con las tres filas falsas tachadas— porque es el registro de lo que se creyó; el
> recuento correcto y cómo se obtuvo están en el cierre.
>
> **Por qué importa, y no es cosmético:** un permiso que en el espejo está en `false` hace que el
> componente que lo gatea **no se monte** en los tests. Nueve de esas celdas apagan los paneles de
> CCTV en toda la suite de web: pasan en verde porque **nadie los renderiza**. La divergencia no
> relaja una aserción, **borra la población**. Se descubrió porque `soc_operator` —el rol
> principal de la consola— no tenía el permiso que `T-5.12` necesitaba, y el panel salía vacío.
- **Componente:** web · **Depende de:** nada · **Prioridad: MEDIA**
- **Objetivo:** que el espejo no pueda divergir en silencio, y que las dieciséis celdas se
  reconcilien de una vez.
- **Criterios de aceptación:**
  - [x] Guarda que compare el espejo contra `ROLE_ACTION_MATRIX` y `ROLE_ROUTE_MATRIX` **por
        igualdad**, no por contención — como ya hacen `serverDataCensus` y `designTokens`. Vale
        derivar el fichero en vez de vigilarlo; lo que no vale es un espejo escrito a mano sin
        gate, que es lo que hay.
  - [x] Las 16 celdas se ponen al día, **y se mira qué tests cambian de veredicto al hacerlo**:
        montar nueve paneles de CCTV que hoy nadie renderiza puede destapar aserciones que nunca
        se han ejecutado. Ese es el valor de la ficha, no la sincronización en sí.
  - [x] Guarda de no-vacuidad: declara en voz alta cuántos roles y cuántas acciones compara, o un
        analizador que se quede ciego pasará en verde comparando cero contra cero.
- **Cómo se cerró (2026-09-03).**
  **Se derivó el fichero en vez de vigilarlo**, que es la opción que la propia ficha permitía y la
  única que hace la deriva *imposible* en vez de *detectable*: la tabla escrita a mano **ya no
  existe**. `api/scripts/export_rbac_matrix.py` vuelca la matriz a
  `shared/fixtures/rbac-matrix.json` —mismo patrón que `notify-channels.json`, que ya cruzaba un
  hecho de Python a los tests de la web—, `meFixtures.ts` lo consume y no enumera nada, y el
  fichero queda atado a su fuente por **dos** vías: un test que compara **celda a celda por
  igualdad** (360 celdas) y un paso de `make drift` + CI que regenera y exige `git diff --exit-code`.
  También se derivan el reparto web/móvil y la superficie, que eran otras dos listas a mano.
  **⚠️ Y hay que corregir esta ficha: eran TRECE celdas, no dieciséis.** Se midieron parseando el
  fichero viejo de git contra la matriz real, y la tabla de arriba tenía **tres filas falsas**: el
  espejo **sí** le daba `read_audit` a `takab_support` y `checkin_submit`/`panic_vote` a
  `occupant`. Las trece reales van todas en la misma dirección —la matriz concede, el espejo no— y
  son: **9 de CCTV** (`cctv_read` en superadmin, tenant_admin, soc_operator, inspector y
  building_admin; `cctv_video` en los cuatro primeros menos inspector) y **4 de privacidad**
  (`manage_privacy_notice` y `manage_privacy_erasure` en superadmin y tenant_admin).
  **El criterio 2 pedía mirar qué tests cambian de veredicto. Ninguno: los 1985 de web siguen en
  verde — y la razón importa más que el hecho.** Doce de las trece acciones **no tienen ningún
  consumidor en la web**: gatean endpoints de la API, y la consola nunca les pregunta. La
  decimotercera, `cctv_video`, gatea **un botón** dentro de `CctvPanel` — y a nivel de página
  `useCctv` está mockeado a `data: undefined` **a propósito y con la razón escrita**, así que ese
  botón no se renderizaba de todos modos; sus dos ramas ya las cubre `CctvPanel.test.tsx`
  directamente por props.
  **O sea que la alarma de esta ficha estaba mal fundada.** Decía que nueve celdas «apagan los
  paneles de CCTV en toda la suite… porque nadie los renderiza»: el panel **sí se monta siempre**
  (`TriageDetail` lo pinta sin gate), lo que estaba apagado era el botón de descarga. La
  divergencia era real y el arreglo vale —el próximo permiso que se desincronice puede gatear algo
  que sí se pinte, y ya no podrá—, pero el daño concreto que se le atribuyó **no existía**.
---

## RUTA CRÍTICA

> **Desde el 2026-09-02 hay DOS rutas, y confundirlas es un error de planificación con precio.**
> Esta sección describe la ruta hacia **un cliente real**, y sigue vigente sin cambios. La ruta
> hacia **poder enseñar el producto** es otra —el Bloque VI—, es más corta, y **no está bloqueada
> en nadie**: sus cinco ítems críticos son software. Una demo no necesita `G-04`; necesita no
> afirmar lo que `G-04` todavía no acreditó. Ver
> [`PLAN-V1-COMERCIAL.md`](PLAN-V1-COMERCIAL.md) §1.

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
