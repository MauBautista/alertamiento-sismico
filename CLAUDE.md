# CLAUDE.md — TAKAB Technology · Contexto maestro del proyecto

> Claude Code lee este archivo automáticamente al iniciar cada sesión. Es la fuente de verdad
> de identidad, reglas, stack y método de trabajo. Si algo aquí contradice un prompt suelto,
> gana este archivo salvo que el prompt diga explícitamente "override CLAUDE.md".

---

## 1. Qué estamos construyendo

**TAKAB Technology** es una plataforma SaaS **multi-tenant** de **alertamiento sísmico,
monitoreo estructural y continuidad operativa post-sismo**, para Protección Civil, gobierno y
empresas (hospitales, universidades, industria, corporativos) en México.

Arquitectura **híbrida edge + cloud**:
- **Edge (gabinete por edificio):** 2 placas — un **Raspberry Shake** (sensor sísmico puro, su
  Shake OS NO se toca) + un **Raspberry Pi 5** que es el cerebro (lee SeedLink del Shake, recibe
  SASMEX por GPIO, dispara relés de sirena/estrobo, corre reglas, sincroniza a la nube).
- **Cloud (AWS):** AWS IoT Core (MQTT) → SQS → backend → PostgreSQL/TimescaleDB/PostGIS + S3.
  Consola web SOC, app móvil, notificaciones.

**Fuentes de alertamiento (en orden):**
1. **SASMEX** vía receptor **WR-1**, salida de **contacto seco #2** → GPIO del Pi 5. Canal primario.
2. **Detección local instrumental** del propio sensor (umbral PGA/PGV).
3. **Quórum colaborativo:** ≥3 estaciones detectando en ventana de 2–5 s (se correlaciona en la nube).

## 2. Reglas de oro (NO negociables — esto es un sistema donde fallar cuesta vidas)

1. **El camino crítico de activación es 100% determinista.** SASMEX→relé y umbral→relé NUNCA
   dependen de IA, de la nube, ni de internet. La IA solo asesora/prioriza/filtra, jamás veta
   ni dispara una alerta por sí sola.
2. **El edge opera sin nube.** Si cae internet, el gabinete sigue detectando, accionando sirenas
   y guardando datos. La nube es para coordinación, no para seguridad local.
3. **Idempotencia en todo dato que cruza el edge→nube.** Nada se duplica al reconectar
   (PK naturales + UUIDv7 en el edge + ON CONFLICT DO NOTHING).
4. **El proceso GPIO es mínimo y auditable.** Sin dependencias pesadas. Es lo que toca la sirena.
5. **Multi-tenant por diseño:** `tenant_id` en toda tabla de negocio + Row-Level Security activa.
   Un test que intente cruzar tenants DEBE fallar.
6. **Nada de secretos hardcodeados.** AWS Secrets Manager / variables de entorno. Nunca en git.
7. **Estados de UI obligatorios:** todo componente maneja `loading`, `error`, `empty` y `stale`
   (dato viejo). Mostrar un dato congelado como si fuera "live" es peor que mostrar "sin datos".
8. **Control de actuadores por nube = superficie más sensible.** Comando firmado (HMAC/JWT corto)
   + MFA + rate-limit + nonce + ack de ejecución. Sin excepción.

## 3. Stack tecnológico (versiones objetivo)

| Capa | Tecnología |
|---|---|
| Backend API | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 (async) · Alembic |
| DB | PostgreSQL 16 · TimescaleDB 2.x · PostGIS 3.x |
| Cloud | AWS IoT Core · SQS · RDS · S3 · Cognito · ECS Fargate · CloudFront |
| Edge | Python 3.12 · ObsPy · NumPy/SciPy · paho-mqtt / aws-iot-device-sdk · systemd |
| Web | React 18 · TypeScript (estricto) · Vite · TanStack Query · zustand · MapLibre GL JS |
| Móvil | React Native (fase V1) |
| Auth | AWS Cognito (OIDC/OAuth2) · JWT con claims de tenant/rol/scope |
| Lint/format | Ruff (Python) · ESLint + Prettier (TS) |
| Tests | pytest (back/edge) · Vitest + Testing Library + Playwright (web) |
| IaC | Terraform |
| CI | GitHub Actions |

## 4. Estructura del monorepo

```
takab/
├── apps/
│   ├── api/        # FastAPI monolito modular (módulos: tenants, sites, sensors, ingest,
│   │              #   incidents, rules, dictamens, notifications, telemetry, auth)
│   ├── web/        # React + TS + Vite (consola SOC + dashboard edificio)
│   ├── mobile/     # React Native (fase V1)
│   └── edge/       # software del Pi 5 (takab_ingest, takab_dsp, takab_rules,
│                  #   takab_gpio, takab_sync, takab_local_api) + systemd/
├── packages/
│   ├── schemas/    # contratos compartidos (Pydantic + JSON Schema → tipos TS)
│   └── sdk-ts/     # cliente TS generado del OpenAPI
├── infra/terraform/
├── db/             # schema.sql + migraciones de referencia
├── docs/
│   ├── FASE-0-AUDITORIA-Y-PLAN-TAKAB.md   # auditoría, arquitectura, IA, backlog completo
│   ├── RBAC-TAKAB.md                       # roles, permisos, matrices, Cognito, claims
│   ├── TASKS.md                            # backlog accionable (este es el que ejecutamos)
│   └── USER-STORIES.md
└── .github/workflows/
```

## 5. Documentos de referencia (léelos cuando la tarea lo requiera)

- **`docs/FASE-0-AUDITORIA-Y-PLAN-TAKAB.md`** — arquitectura completa, los 7 SPOF y sus
  mitigaciones, esquema SQL razonado, modelo de IA, anti-thundering-herd, backlog maestro.
- **`docs/RBAC-TAKAB.md`** — 11 roles, matrices de acceso web y móvil, mapeo a Cognito, claims
  del JWT, reglas de actuadores, tablas de auth.
- **`db/schema.sql`** — esquema de producción consolidado (aplícalo, no lo reinventes).
- **`docs/TASKS.md`** — qué construir y en qué orden, con criterios de aceptación.

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
   - [ ] Commit con mensaje convencional (`feat:`, `fix:`, `chore:`...)

**Regla de detención:** si tras 3 iteraciones del loop un criterio no pasa, NO sigas adelante:
detente, resume el bloqueo en lenguaje claro y espera input humano. No inventes workarounds que
violen las reglas de oro.

## 7. Uso de MCPs

- **Context7:** ante CUALQUIER duda de API de una librería (FastAPI, SQLAlchemy 2 async,
  Pydantic v2, TimescaleDB, MapLibre, TanStack Query, aws-iot-device-sdk), usa Context7 para
  traer documentación actual. No generes código de memoria para estas librerías.
- **GitHub MCP:** para PRs, issues y estado de CI.
- **Postgres MCP:** para inspeccionar el esquema y validar queries contra la DB local.

## 8. Qué NO hacer

- No tocar Shake OS ni asumir que el Pi del Shake corre nuestro código.
- No poner ingesta SeedLink dentro del event loop de FastAPI (procesos separados).
- No usar UDP del Shake para producción (solo preview/debug).
- No meter IA en el camino de disparo de sirena.
- No crear el T-MINUS countdown ni magnitud preliminar todavía (el WR-1 solo da un booleano —
  ver pendientes en RBAC-TAKAB.md §8). En MVP el banner dice "ALERTA SÍSMICA · PROTÉJASE".
- No usar `localStorage`/`sessionStorage` en componentes que se rendericen como artifacts de prueba.
- No avanzar a la siguiente tarea si la actual no cumple su Definition of Done.
