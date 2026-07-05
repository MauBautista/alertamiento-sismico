> **[ARCHIVO HISTÓRICO — restaurado de `6c9b1e0:docs/prompts/PROMPT-01-monorepo.md`.]** Prompt ya
> ejecutado (T-1.1). La estructura que describe (`apps/`, `packages/`, `docs/`) fue renombrada en
> el commit `61078d6` a `api/`, `web/`, `shared/`, `takab-docs/`. Se conserva por trazabilidad.

# PROMPT 01 — Monorepo Foundation (tarea T-1.1)

> Pégalo en Claude Code dentro del directorio raíz vacío del proyecto `takab/`.
> Antes: confirma que Context7 está activo (`/mcp`) y que superpowers cargó.

---

## Contexto del proyecto

Estás iniciando **TAKAB Technology**, una plataforma SaaS multi-tenant de alertamiento sísmico
edge+cloud. Lee `CLAUDE.md` completo antes de actuar: contiene la identidad, las reglas de oro,
el stack y el método de trabajo. Lee también `docs/TASKS.md` (esta es la tarea **T-1.1**).

Esta tarea es **solo la fundación del monorepo**. NO implementes lógica de negocio, ni auth, ni
edge, ni esquema de DB todavía. Solo el esqueleto, el tooling y el CI que todo lo demás necesita.

## Stack y convenciones (de CLAUDE.md)

- Python 3.12, FastAPI, Pydantic v2, Ruff, pytest.
- TypeScript estricto, React 18, Vite, ESLint + Prettier, Vitest.
- Commits convencionales. Sin secretos en git. `.env.example` sí, `.env` no.
- Para dudas de API de FastAPI/Vite/React, usa **Context7** (no generes de memoria).

## Tarea

Crea la estructura de monorepo definida en `CLAUDE.md §4`. En concreto:

1. **Raíz:** `README.md`, `Makefile`, `.gitignore`, `.editorconfig`, `docker-compose.yml`
   (Postgres 16 + TimescaleDB + PostGIS para dev local), `.env.example`.
2. **`apps/api`** (FastAPI):
   - `pyproject.toml` con deps mínimas (fastapi, uvicorn, pydantic v2, ruff, pytest).
   - App con un router `/health` que devuelve `{"status":"ok"}`.
   - `tests/test_health.py` que verifica 200 y el cuerpo.
   - Config de Ruff.
3. **`apps/web`** (React + TS + Vite):
   - Proyecto Vite con TypeScript estricto (`strict: true`).
   - Una página raíz mínima que compila (placeholder "TAKAB").
   - ESLint + Prettier + Vitest configurados; un test trivial que pasa.
4. **`apps/edge`**, **`packages/schemas`**, **`packages/sdk-ts`**, **`infra/terraform`**:
   crea las carpetas con un `README.md` que describa su propósito (placeholders, sin código aún).
5. **`db/`**: coloca el `schema.sql` que te paso junto a este prompt (no lo apliques aún; es para T-1.3).
6. **`docs/`**: coloca `CLAUDE.md` (también en raíz), `FASE-0-AUDITORIA-Y-PLAN-TAKAB.md`,
   `RBAC-TAKAB.md`, `TASKS.md`, `USER-STORIES.md`.
7. **`Makefile`** con al menos: `make dev` (levanta compose + api + web), `make lint`
   (ruff + eslint), `make test` (pytest + vitest), `make fmt`.
8. **CI `.github/workflows/ci.yml`**: en cada PR y push a main, corre lint + tests de api y web.

## Archivos a crear (no exhaustivo)

```
README.md  Makefile  .gitignore  .editorconfig  docker-compose.yml  .env.example
apps/api/pyproject.toml  apps/api/src/takab_api/main.py  apps/api/src/takab_api/health.py
apps/api/tests/test_health.py  apps/api/ruff.toml
apps/web/package.json  apps/web/tsconfig.json  apps/web/vite.config.ts
apps/web/src/main.tsx  apps/web/src/App.tsx  apps/web/src/App.test.tsx
apps/web/.eslintrc.cjs  apps/web/.prettierrc
apps/edge/README.md  packages/schemas/README.md  packages/sdk-ts/README.md
infra/terraform/README.md  db/schema.sql
docs/CLAUDE.md  docs/FASE-0-AUDITORIA-Y-PLAN-TAKAB.md  docs/RBAC-TAKAB.md
docs/TASKS.md  docs/USER-STORIES.md
.github/workflows/ci.yml
```

## Método

```
/write-plan      # plan TDD para esta tarea (tests de /health y del web primero)
/goal "make lint y make test pasan en verde; /health responde {status:ok}; web compila; CI verde"
/loop /execute-plan   # implementa, corre, autorrevisa y repite hasta cumplir el goal
```

## Criterios de aceptación (Definition of Done)

- [ ] `make dev` levanta Postgres (compose), API y web sin error.
- [ ] `curl localhost:8000/health` → `{"status":"ok"}`.
- [ ] `apps/web` compila (`vite build`) y renderiza el placeholder.
- [ ] `make lint` limpio (ruff + eslint + prettier).
- [ ] `make test` verde (pytest + vitest).
- [ ] `ci.yml` corre lint + tests de api y web; el job pasa.
- [ ] Estructura completa de carpetas creada; documentos en su sitio; `db/schema.sql` presente.
- [ ] `.gitignore` excluye `.env`, `node_modules`, `__pycache__`, `.terraform`, artefactos.
- [ ] Commit convencional (`chore: scaffold monorepo foundation`).

## Notas

- NO implementes el esquema de DB ni auth aquí (son T-1.3 y T-1.4).
- Mantén deps al mínimo; ya las ampliaremos por tarea.
- Si algo te obliga a violar una regla de oro de `CLAUDE.md`, detente y repórtalo.
- Al terminar, deja en el chat un resumen: qué se creó, cómo correr `make dev`, y qué sigue (T-1.2).
