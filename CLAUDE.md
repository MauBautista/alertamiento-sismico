# CLAUDE.md — TAKAB Ailert · Contexto maestro del proyecto

> Claude Code lee este archivo automáticamente al iniciar cada sesión. Es la fuente de verdad
> de identidad, reglas, stack y método de trabajo. El documento canónico de arquitectura es
> `takab-docs/BLUEPRINT-TECNICO-TAKAB.md` — ante cualquier conflicto, el blueprint gana sobre
> inferencias hechas del deck de producto o de documentos exploratorios. Si algo aquí contradice
> un prompt suelto, gana este archivo salvo que el prompt diga explícitamente "override CLAUDE.md".

---

## 0. Reglas de ejecución (prioridad máxima)

1. **Orden de trabajo = EDGE PRIMERO, luego CLOUD, luego FRONTEND.** Se construye completa la
   inteligencia del gabinete (Raspberry Pi 5) antes de tocar la nube. La nube se construye sobre
   contratos ya validados en el edge. El frontend consume la nube ya existente. Ver
   `takab-docs/BLUEPRINT-TECNICO-TAKAB.md §13`.
2. **No auto-atribución en el control de versiones.** Los commits **no** deben incluir a
   Claude/Anthropic como coautor ni footers de generación automática. Prohibido:
   - `Co-Authored-By: Claude <...>`
   - `🤖 Generated with Claude Code` (o cualquier variante)
   - Cualquier trailer, firma o mención de asistente de IA en el mensaje de commit, PR o changelog.
   El autor único de todos los commits es Mauricio. Mensajes en Conventional Commits, limpios y
   sin adornos.
3. **Estado actual: T-1.1 (fundación del monorepo) está COMPLETA.** No rehacerla; construir encima.

## 1. Qué estamos construyendo

**TAKAB Ailert** es una plataforma SaaS **multi-tenant** de **alertamiento sísmico,
monitoreo estructural y continuidad operativa post-sismo**, para Protección Civil, gobierno y
empresas (hospitales, universidades, industria, corporativos) en México.

Arquitectura **híbrida edge + cloud**:
- **Edge (gabinete por edificio):** 2 placas — un **Raspberry Shake** (sensor sísmico puro, su
  Shake OS NO se toca) + un **Raspberry Pi 5** que es el cerebro (lee SeedLink del Shake, recibe
  SASMEX por GPIO, dispara actuadores BACnet/IP —sirena, cierre de válvulas de gas, retorno de
  ascensores, retenedores de puerta—, corre reglas, sincroniza a la nube).
- **Cloud (AWS):** AWS IoT Core (MQTT/mTLS) → SQS → ECS Fargate → PostgreSQL/TimescaleDB/PostGIS
  + S3. Consola web SOC, app móvil (fase posterior), notificaciones.

**Fuentes de alertamiento (en orden):**
1. **SASMEX** vía receptor **WR-1**, salida de **contacto seco** → GPIO del Pi 5 (boolean). Canal
   primario y autoritativo.
2. **Detección local instrumental** del propio sensor (umbral PGA/PGV; tiers `normal`/`watch`/
   `restricted`/`evacuate_or_hold`/`manual_only`).
3. **Quórum colaborativo:** ≥3 estaciones con **ventana de asociación consciente de la
   distancia** entre sitios (`|Δt| ≤ dist/v_P + margen` — ver blueprint §4.5; una ventana fija
   de 2–5 s era físicamente inalcanzable a 90–110 km). Se correlaciona en la nube; no bloquea
   la actuación local autónoma.

## 2. Reglas de oro (NO negociables — esto es un sistema donde fallar cuesta vidas)

1. **El camino crítico de activación es 100% determinista.** SASMEX→actuador y umbral→actuador
   NUNCA dependen de IA, de la nube, ni de internet. La IA solo asesora/prioriza/filtra, jamás
   veta ni dispara una alerta por sí sola.
2. **El edge opera sin nube.** Si cae internet, el gabinete sigue detectando, accionando
   actuadores y guardando datos. La nube es para coordinación, no para seguridad local.
3. **Idempotencia en todo dato que cruza el edge→nube.** Nada se duplica al reconectar
   (PK naturales + `event_id`/nonce en el edge + ON CONFLICT DO NOTHING).
4. **El proceso GPIO/actuadores es mínimo y auditable.** Sin dependencias pesadas. Es lo que
   toca sirena, gas, ascensores y puertas.
5. **Multi-tenant por diseño:** `tenant_id` en toda tabla de negocio + Row-Level Security
   default-deny activa. Un test que intente cruzar tenants DEBE fallar.
6. **Nada de secretos hardcodeados.** AWS Secrets Manager / variables de entorno. Nunca en git.
7. **Estados de UI obligatorios:** todo componente maneja `loading`, `error`, `empty` y `stale`
   (dato viejo). Mostrar un dato congelado como si fuera "live" es peor que mostrar "sin datos".
8. **Control de actuadores por nube = superficie más sensible.** Comando firmado (HMAC/JWT corto)
   + MFA + rate-limit + nonce + ack de ejecución. Sin excepción.
9. **Sin streaming de forma de onda cruda.** El waveform crudo (100 sps — el RS4D muestrea a
   100, no 200 Hz) no se sube en continuo; el miniSEED crudo sube a S3 solo en eventos confirmados.
10. **Logging por evento, no por intervalo.** Registro por transición de estado + heartbeat
    periódico; nada de logging continuo para `rule_evaluations` o salud de dispositivo.
11. **Compliance como restricción dura.** Auditoría, evidencia de incidentes y dictámenes nunca
    se podan por retención (requisito propio de TAKAB, garantizado por el schema; el marco
    normativo citable está por confirmar — ver blueprint §9; la antigua cita "NOM-003-SCT" era
    una norma de transporte y no aplica).

## 3. Stack tecnológico (versiones objetivo)

| Capa | Tecnología |
|---|---|
| Backend API | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 (async) · Alembic · WebSocket nativo para live (GraphQL subscriptions: pos-MVP `[SUPUESTO plan-maestro-01 #5 — confirmar]`) |
| DB | PostgreSQL 16 · TimescaleDB 2.x · PostGIS 3.x |
| Cloud | AWS IoT Core · SQS · ECS Fargate · S3 · Cognito · KMS |
| Edge | Python 3.12 (`uv`) · ObsPy · NumPy/SciPy · aws-iot-device-sdk / paho-mqtt · BAC0/bacpypes3 (BACnet) · gpiozero/lgpio (GPIO) · systemd |
| Web | React 18 · TypeScript (estricto) · Vite · TanStack Query · zustand · MapLibre GL JS |
| Móvil | React Native (fase posterior) |
| Auth | AWS Cognito (OIDC/OAuth2 + MFA) · JWT con claims de tenant/rol/scope |
| Lint/format | Ruff (Python) · ESLint + Prettier (TS) |
| Tests | pytest (api/edge) · Vitest + Testing Library + Playwright (web) |
| IaC | Terraform |
| CI | GitHub Actions (jobs `api` + `web` + `edge`) |

## 4. Estructura del monorepo

```
takab/
├── edge/            # Raspberry Pi 5 — gateway de inteligencia (Python 3.12 · uv)
│                    #   módulos: seedlink, signal, buffer, gpio, rules, actuators,
│                    #   cloud, health, config, security, local_api, supervisor
│                    #   (gpio = WR-1 + relés + reflejo SASMEX→sirena consolidado
│                    #   [SUPUESTO plan-maestro-01 #6]; el quórum vive en la NUBE)
├── api/             # backend cloud (FastAPI; REST + WS)
├── web/             # Consola SOC (React 18 · Vite)
├── shared/
│   ├── schemas/     # contratos compartidos (Pydantic + JSON Schema → tipos TS)
│   └── sdk-ts/      # cliente TS generado del OpenAPI
├── infra/terraform/ # IaC AWS
├── db/              # schema.sql + migraciones de referencia (fuente de verdad del DDL)
├── takab-docs/
│   ├── BLUEPRINT-TECNICO-TAKAB.md   # documento canónico de arquitectura
│   ├── RBAC-TAKAB.md                # roles, permisos, matrices, Cognito, claims
│   ├── TASKS.md                     # backlog accionable (este es el que ejecutamos)
│   ├── USER-STORIES.md
│   └── prompts/
└── .github/workflows/               # CI: jobs api + web + edge
```

> El **Pi 5 se construye primero** (edge), luego la nube, luego el frontend — ver
> `takab-docs/BLUEPRINT-TECNICO-TAKAB.md §13` para el roadmap detallado por work package.

## 5. Documentos de referencia (léelos cuando la tarea lo requiera)

- **`takab-docs/BLUEPRINT-TECNICO-TAKAB.md`** — documento canónico: principios arquitectónicos,
  topología, módulos del edge, capa cloud, roadmap Edge→Cloud→Frontend. Ante cualquier
  ambigüedad de arquitectura, este documento gobierna.
- **`takab-docs/RBAC-TAKAB.md`** — 10 roles, matrices de acceso web y móvil, mapeo a Cognito,
  claims del JWT, reglas de actuadores, tablas de auth. (Las identidades máquina — X.509 de
  gateway, M2M, rol DB de ingesta — no son roles RBAC.)
- **`db/schema.sql`** — esquema de producción consolidado (aplícalo, no lo reinventes); es la
  fuente de verdad del DDL incluso donde el blueprint describa algo distinto.
- **`takab-docs/TASKS.md`** — qué construir y en qué orden, con criterios de aceptación.
- **`takab-docs/PLAN-MAESTRO-TAKAB.md`** — secuencia por fases, hitos, DoD de fase, ruta
  crítica, decision-gates y supuestos `[SUPUESTO plan-maestro-01]` pendientes de ratificar.
- **`takab-docs/ANALISIS-ARQUITECTURA-TAKAB.md`** — hallazgos del red-team, changelog de
  correcciones `[ANALISIS-00]` y preguntas abiertas.

## 6. Método de trabajo (cómo ejecutamos cada tarea)

Trabajamos **una tarea de `TASKS.md` a la vez**, en este ciclo:

1. **`/brainstorm`** (superpowers) solo si la tarea es ambigua o de diseño. Si ya está
   especificada en TASKS.md, salta al plan.
2. **`/write-plan`** — plan de implementación con TDD (tests primero).
3. **`/goal "<criterio de aceptación de la tarea>"`** — fija el objetivo medible.
4. **`/execute-plan`** dentro de un **`/loop`** — implementa, corre tests/lint/build, se
   autorrevisa y repite **hasta que TODOS los criterios de aceptación pasen en verde**.
5. **Definition of Done** (no se cierra una tarea sin esto):
   - [ ] Tests escritos primero y en verde (`pytest` / `vitest`)
   - [ ] Lint y format limpios (`ruff` / `eslint`)
   - [ ] Build pasa (`vite build` / import de la app)
   - [ ] Sin secretos en el diff
   - [ ] Criterios de aceptación de la tarea verificados explícitamente
   - [ ] Commit con mensaje convencional (`feat:`, `fix:`, `chore:`...) **sin coautoría de IA**
         (ver §0.2)

**Regla de detención:** si tras 3 iteraciones del loop un criterio no pasa, NO sigas adelante:
detente, resume el bloqueo en lenguaje claro y espera input humano. No inventes workarounds que
violen las reglas de oro.

## 7. Uso de MCPs

- **Context7:** ante CUALQUIER duda de API de una librería (FastAPI, SQLAlchemy 2 async,
  Pydantic v2, TimescaleDB, MapLibre, TanStack Query, aws-iot-device-sdk, BAC0/bacpypes3, ObsPy),
  usa Context7 para traer documentación actual. No generes código de memoria para estas librerías.
- **GitHub MCP:** para PRs, issues y estado de CI.
- **Postgres MCP:** para inspeccionar el esquema y validar queries contra la DB local.

## 8. Qué NO hacer

- No tocar Shake OS ni asumir que el Pi del Shake corre nuestro código.
- No poner ingesta SeedLink dentro del event loop de FastAPI (procesos separados).
- No usar UDP del Shake para producción (solo preview/debug).
- No meter IA en el camino de disparo de actuadores.
- No crear el T-MINUS countdown ni magnitud preliminar todavía (el WR-1 solo da un booleano —
  ver pendientes en `RBAC-TAKAB.md §8`). En MVP el banner dice "ALERTA SÍSMICA · PROTÉJASE".
- No usar `localStorage`/`sessionStorage` en componentes que se rendericen como artifacts de prueba.
- No avanzar a la siguiente tarea si la actual no cumple su Definition of Done.
- No incluir coautoría de IA ni footers de generación automática en commits/PRs (ver §0.2).
- No implementar el microservicio "mini-ShakeMap" ni streaming continuo de forma de onda cruda
  en este ciclo (ver blueprint §14).

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
