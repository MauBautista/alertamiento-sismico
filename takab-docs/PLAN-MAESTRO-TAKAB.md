# PLAN MAESTRO DE EJECUCIÓN — TAKAB Ailert · Fase 1 (MVP)
**Rama `plan/maestro-01` · 2026-07-05 · post-análisis red-team (`ANALISIS-ARQUITECTURA-TAKAB.md`)**

> **Qué es este documento:** el roadmap de ejecución de la Fase 1 con fases, carriles, hitos,
> Definition of Done por fase, ruta crítica, decision-gates y riesgos.
> **Qué NO es:** un backlog. Los criterios de aceptación por tarea viven en `TASKS.md` (única
> fuente); este plan lo referencia, nunca lo copia. Jerarquía documental: el blueprint gobierna
> la arquitectura; `db/schema.sql` el DDL; `RBAC-TAKAB.md` los roles; `TASKS.md` el backlog;
> este plan, la secuencia y los gates.
> **Convención de supuestos:** toda decisión aún no ratificada por Mauricio va marcada
> `[SUPUESTO plan-maestro-01 — confirmar/override]`. Un override NO invalida el plan: cada
> supuesto está aislado (ver gates §3).

---

## 1. Veredicto: ¿empezar de cero? → **CONSERVAR y refinar. No reiniciar.**

Evidencia, no inercia:
- `db/schema.sql` v1.1 **aplica limpio y pasa 18/18** casos de RLS/inmutabilidad contra
  PostgreSQL+PostGIS real (`db/verify_rls_smoke.sh`).
- El red-team declaró la arquitectura **fundamentalmente sana**: separación edge/cloud real,
  path de actuación 100% determinista, sin fugas de features diferidas, edge-first correcto.
- T-1.1 es aprovechable: `api/` (FastAPI `/health` + tests), `web/` (React+TS estricto +
  tooling completo) funcionan; el monorepo y el Makefile están bien plantados.
- Historia git limpia y trazable: Conventional Commits, autor único, sin coautoría de IA,
  análisis enlazado a commits.

**Reinicios acotados (los únicos):**
1. **Frontend (Fase F) se implementa desde cero.** `jsx/` y `Design System/` son *referencia
   visual*, no base de código: asumen NATS JetStream (fuera de stack), Mapbox GL (el stack es
   MapLibre) y T-MINUS (diferido, blueprint §14).
2. **CI se crea desde cero en T-1.2** (nunca existió en el repo; criterio heredado de T-1.1).
3. Nada más. Reiniciar el resto destruiría verificación y trazabilidad sin comprar nada.

---

## 2. Coherencia post-análisis — residuos corregidos en esta rama

El análisis dejó ~13 residuos menores entre documentos. Esta rama los corrige (commit
`docs: coherencia post-análisis`); se listan como changelog:

| # | Dónde | Qué era | Qué es ahora |
|---|---|---|---|
| R1 | `CLAUDE.md` §1.3 | quórum "ventana de 2–5 s" | ventana consciente de distancia (blueprint §4.5) |
| R2 | `CLAUDE.md` regla 9 | "waveform 200 Hz" | waveform crudo (100 sps) |
| R3 | `CLAUDE.md` regla 11 | "(NOM-003-SCT)" | requisito TAKAB; marco citable por confirmar (blueprint §9) |
| R4 | `CLAUDE.md` §4 | módulo `quorum`; sin `local_api`; `sasmex`/`actuators` separados | módulos con `gpio` consolidado + `local_api` [SUPUESTO #6] |
| R5 | `CLAUDE.md` §5 | "11 roles" | 10 roles |
| R6 | `edge/README.md` | `quorum` + BACnet como única actuación | módulos actualizados; relés fail-safe primarios [SUPUESTO #4] |
| R7 | `TASKS.md` T-1.7 | buffer "~10–16 GB" | ~0.5–4 GB reales a 100 sps ×4 canales (NVMe 64 GB ≥15× holgura) |
| R8 | `TASKS.md` T-1.18 | "los 11 roles" | los 10 roles |
| R9 | Blueprint §8 y B8 | "11 roles" | 10 roles + identidades máquina fuera de RBAC |
| R10 | `infra/terraform/README.md` | "implementación en T-1.2" | T-1.15 |
| R11 | `jsx/*` (3 copias) | NATS/Mapbox/T-MINUS | **sin editar** — declarado referencia visual (ver §1); mover a `takab-docs/design/` = limpieza opcional |
| R12 | `ANALISIS:311` | "los 11 roles" (errata) | los roles de RBAC §1 |
| R13 | `CLAUDE.md` §3 stack | "GraphQL (subscriptions)" sin matiz | GraphQL pos-MVP; REST+WS en MVP [SUPUESTO #5] |
| R14 | Blueprint §4.1 (hardware) | NVMe "uso real ~10–16 GB" | ~0.5–4 GB a 100 sps (cazado por el grep de verificación de esta rama) |

**Reconciliación 10-vs-11 roles** `[SUPUESTO plan-maestro-01 — confirmar/override]`: la lista
canónica de `RBAC-TAKAB.md §1/§5.1` siempre enumeró 10 (2 internos TAKAB + 7 de tenant + 1
gobierno) — también en el snapshot de junio. Se corrige el conteo a 10 y se documenta que las
**identidades máquina** (certificado X.509 por gateway, M2M `client_credentials`, rol de DB
`takab_ingest`) son identidades de servicio, **no roles RBAC**. Si el 11º era un rol humano
planeado (¿auditor externo?), se añade a RBAC y se revierte el número.

---

## 3. Decisiones incorporadas y decision-gates

| Decisión (ANALISIS §4) | Estado adoptado | Gate — qué NO empieza sin cerrarla |
|---|---|---|
| #1 Marco normativo de compliance | Pregunta abierta. La inmutabilidad ya es estructural (schema §7/§8) — **no bloquea** | Soft-gate: wording final de la pantalla Triage (T-1.29) y material comercial |
| #2 Quórum en NUBE + ventana distance-aware | Adoptado y ya en docs (v_P 6.5 km/s, margen 3 s, tope 30 s, en `rule_sets.config`) | Soft-gate T-1.19: validar parámetros contra 3–5 sismos del catálogo SSN (tarea paralela; el código lee config, no constantes) |
| #3 Datos de proveedor (SeedLink real, semántica WR-1, 100 sps) | **Los simuladores desbloquean todo el edge.** Tareas marcadas "a validar con hardware" en TASKS: T-1.3, T-1.4, T-1.5, T-1.7, T-1.14 | Hard-gate SOLO para aceptación con hardware real y para congelar el SLA instrumental (§4.3). No frena ninguna implementación |
| #4 Actuadores del MVP | `[SUPUESTO]` **Relés fail-safe primero** (NO/NC/fail-close por canal); BACnet detrás de la misma interfaz `Actuator`, activable por contrato | Cerrar antes de **T-1.8/T-1.9** (contrato rules→actuador). Override tardío = cambiar driver, no motor |
| #5 API en vivo | `[SUPUESTO]` **REST + WebSocket nativo** en MVP; GraphQL subscriptions pos-MVP | Antes de **T-1.22**. No toca el edge |
| #6 Proceso `gpio` consolidado | `[SUPUESTO]` un solo proceso mínimo: WR-1 in + relés out + **reflejo SASMEX→sirena in-process** (<100 ms); `actuators` = adaptador BACnet aparte; bus local (mosquitto) SOLO telemetría | T-1.2 scaffoldea según el supuesto (un rename si hay override); el contrato se congela en **T-1.8** |
| #7 MFA del `occupant` | `[SUPUESTO]` occupant **sin MFA**, compensado con quórum de 2 + rate-limit + geofence + auditoría; MFA obligatorio para todo rol web | Decisión final antes de la fase móvil (T-1.31); T-1.18 configura MFA por grupo con este default |
| #8 Feed externo CIRES/SSN | Pregunta abierta; el fail-open ya está definido con corroboración interna de la red | Soft-gate T-1.21 (lo mejora, no lo bloquea) |
| #9 IA (Fase 3) | Política del plan: **shadow-mode only; jamás suprime disparos** (regla de oro 1 intacta) | Gate de Fase 3 — fuera de este plan |

---

## 4. Plan por fases

### Fase E — EDGE (T-1.2 → T-1.14) · todo contra simuladores

**Primer paso concreto: T-1.2** — scaffold `edge/` (módulos `seedlink, signal, buffer, gpio,
rules, actuators, cloud, health, config, security, local_api` + supervisor), simuladores RS4D
(100 sps) / WR-1 / BACnet, y **CI completo desde cero: jobs `api` + `web` + `edge`** (criterio
heredado de T-1.1).

Carriles tras T-1.2 (paralelizables):
- **Carril de vida:** T-1.3 (`gpio`: WR-1→relés, <100 ms, debounce, NO/NC) → T-1.4 (ruta de
  hardware paralela: runbook ya; verificación física queda hardware-gated).
- **Carril instrumental:** T-1.5 (`seedlink`) → T-1.6 (`signal` 1 s) → T-1.7 (`buffer` ring).
- **Transversal:** T-1.10 (`health`) en cualquier hueco.

Convergencia: **T-1.8** (`rules`; gates #4/#6 cerrados por supuesto) → **T-1.9** (interfaz
`Actuator`: driver de relés + adaptador BACnet mock) → **T-1.11** (`cloud` + **contratos
`shared/schemas` v1** — el entregable que la Fase C consume) → T-1.12 (`config`/`security`)
‖ T-1.13 (`local_api`) → **T-1.14** (integración E2E).

**DoD de Fase E (hito de cierre):** el gabinete simulado se protege solo —
1. SASMEX simulado → sirena en <100 ms (reflejo in-process).
2. Sismo sintético 100 sps → features → tier → actuación con ACK y `rule_evaluations`.
3. WAN caída 2 h → cola offline → backfill idempotente (cero pérdida/duplicado, por PK).
4. `shared/schemas` v1 publicados; simuladores validan cada payload contra ellos.
5. CI verde con los 3 jobs.
6. **Un test demuestra la actuación completa con la nube apagada** (P1/P2 probados, no declarados).

### Fase C — CLOUD (T-1.15 → T-1.25) · sobre los contratos ya validados del edge

Arranque en paralelo: **T-1.15** (Terraform base) ‖ **T-1.16** (migraciones Alembic + tests
RLS contra Postgres local — no depende de AWS; *adelantable* incluso durante la Fase E si hay
holgura, sin violar edge-first: es DDL local ya verificado por el smoke test).

Luego: T-1.17 (ingesta IoT→SQS→Timescale, valida contra `shared/schemas`, DLQ) → T-1.18
(Cognito **10 grupos** + claims + RLS E2E; MFA por grupo con supuesto #7) → en ramas:
T-1.19 (incident engine + quórum distance-aware) → T-1.20 (dictamen inmutable + PDF)
‖ T-1.21 (notificaciones + fail-open) ‖ T-1.22 (API REST + WS [SUPUESTO #5]) ‖ T-1.23
(config sync + comandos firmados) → T-1.24 (audit/billing) ‖ T-1.25 (backfill S3).

**DoD de Fase C:** ingesta E2E idempotente desde el edge simulado; test cross-tenant y
gov-read-only **en RDS real** (reusar `db/verify_rls_smoke.sh` + verificar jobs de
compresión/caggs conviviendo con RLS); incidente regional con quórum sintético de tiempos
de arribo realistas; dictamen inmutable exportado a PDF; cascada con fail-open probado;
comando remoto con replay → rechazado.

### Fase F — FRONTEND (T-1.26 → T-1.30) · jsx/ como referencia visual únicamente

T-1.26 (guards + shell por rol) → T-1.27 (Consola C4I, suscripción WS) ‖ T-1.28 (Flota Edge)
→ T-1.29 (Triage; wording de compliance espera gate #1) → T-1.30 (Matriz multi-tenant).

**DoD de Fase F:** SOC operable end-to-end contra la nube real alimentada por el simulador;
estados `loading/error/empty/stale` en todo componente; update de incidente visible <2 s;
guard bloquea navegación directa por URL.

**Móvil (T-1.31): diferido.** Gates antes de arrancarlo: decisión #7 (MFA occupant) y
solicitud del entitlement de Critical Alerts (iOS).

### Ruta crítica

```
T-1.2 → T-1.5 → T-1.6 → T-1.8 → T-1.9 → T-1.11 → T-1.12 → T-1.14
      → [T-1.15 ‖ T-1.16] → T-1.17 → T-1.18 → T-1.22 → T-1.26 → T-1.27
```
La frenan (y su antídoto): latencia SeedLink real (medir con hardware en paralelo — no bloquea
código); override tardío de #4/#6 (aislado por la interfaz `Actuator`); trámites AWS (iniciar
cuentas/credenciales **durante** la Fase E); semántica WR-1 (afecta aceptación, no implementación).

---

## 5. Riesgos de ejecución

| Riesgo | Mitigación | Se materializa en |
|---|---|---|
| Latencia SeedLink real ≫ presupuesto (≤2 s instrumental) | SASMEX es el canal primario de vida; medir con hardware al recibirlo; reevaluar UDP datacast SOLO con dato en mano y decisión explícita (hoy prohibido) | T-1.5, T-1.14, SLA §4.3 |
| Semántica WR-1 ≠ supuesto (contactos, latching, pruebas CIRES) | Simulador parametrizable; reunión CIRES; re-validar aceptación de T-1.3 con hardware | T-1.3, T-1.4 |
| Override tardío de #4 (BACnet) o #6 (gpio) | Interfaz `Actuator` estable; `gpio` autocontenido; costo del cambio = driver/rename | T-1.8, T-1.9 |
| AWS tardío (alta de cuentas, límites, budget) | Tramitar durante Fase E; Terraform `dev` mínimo primero | T-1.15 |
| Jobs de TimescaleDB (compresión/caggs) vs RLS | Hypertables sin FORCE por diseño (schema §8); test explícito del job | T-1.16 |
| Fuga cross-tenant por caggs (sin RLS posible) | Regla dura "JOIN a `sites`" + test de contrato de API que lo verifique | T-1.22 |
| Parámetros de quórum sin validar | Validación con catálogo SSN, paralela y pequeña, antes de cerrar T-1.19 | T-1.19 |
| Botón de pánico: fricción MFA vs abuso de QR | Supuesto #7 + geofence + `max_uses`/expiración/revocación; decisión final pre-móvil | T-1.31 |
| Critical Alerts iOS requiere entitlement de Apple | Solicitarlo al INICIO de la fase móvil (semanas de trámite) | T-1.31 |
| Bus factor 1 + un solo juego de hardware | Simuladores como ciudadanos de primera clase; HIL opcional; runbooks desde T-1.4 | Transversal |

---

## 6. Antes de T-1.2 — lista priorizada

- **Bloquea T-1.2: nada.** Los supuestos #4/#5/#6 adoptados desbloquean el arranque.
- **Hecho en esta rama (previo a T-1.2):** residuos R1–R13 aplicados + este plan persistido.
- **En paralelo, no bloquea (dueño: Mauricio):**
  1. Confirmar/override de los supuestos marcados (#4, #5, #6, #7, 10-roles).
  2. Marco normativo (#1) — con abogado/primer cliente.
  3. Reunión Raspberry Shake + CIRES (#3): latencia SeedLink, semántica de contactos WR-1,
     cadencia de pruebas; pico de corriente de sirena vs UPS.
  4. Validación SSN de la ventana de quórum (#2).
  5. Iniciar trámites AWS (cuenta, budget alarms, límites de servicio).
  6. Feed CIRES/SSN (#8) — exploración comercial.

**Siguiente acción tras aprobar esta rama: ejecutar T-1.2** con el ciclo de `CLAUDE.md §6`
(`/write-plan` → `/goal` → `/execute-plan` en `/loop`).
