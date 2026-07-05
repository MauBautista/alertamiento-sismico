# Monorepo Foundation (T-1.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the TAKAB monorepo skeleton (apps/api, apps/web, placeholders, db, docs, CI) per CLAUDE.md §4 with working lint/test/build and green CI — no business logic.

**Architecture:** Monorepo with `apps/{api,web,edge}`, `packages/{schemas,sdk-ts}`, `infra/terraform`, `db/`, `docs/`. API is FastAPI (Python 3.12) exposing only `/health`. Web is Vite + React 18 + strict TS with a placeholder page. A root `Makefile` orchestrates dev/lint/test/fmt. GitHub Actions runs lint+test for api and web on every PR/push to main. Existing loose docs/schema get relocated into `docs/` and `db/` via `git mv`.

**Tech Stack:** Python 3.12 · FastAPI · Pydantic v2 · Ruff · pytest · httpx · TypeScript (strict) · React 18 · Vite · ESLint · Prettier · Vitest · Docker Compose (TimescaleDB+PostGIS) · GitHub Actions.

**Scope note — what this plan does NOT touch:** the `Design System/` tree and the loose root design duplicates (`SOC Console.html`, `SOC.css`, `SOC-tabs.css`, `jsx/`, `assets/`, `design-system/`, `files/`, `files.zip`). Those feed apps/web in T-1.5, not now. Left in place.

---

## File Structure

**Relocated (git mv, tracked files):**
- `FASE-0-AUDITORIA-Y-PLAN-TAKAB.md` → `docs/FASE-0-AUDITORIA-Y-PLAN-TAKAB.md`
- `RBAC-TAKAB.md` → `docs/RBAC-TAKAB.md`
- `TASKS.md` → `docs/TASKS.md`
- `USER-STORIES.md` → `docs/USER-STORIES.md`
- `schema.sql` → `db/schema.sql`
- `PROMPT-01-monorepo.md` → `docs/prompts/PROMPT-01-monorepo.md`
- `CLAUDE.md` stays in root **and** is copied to `docs/CLAUDE.md` (per prompt §6)

**Created — root:** `README.md` (replace empty `readme.md`), `Makefile`, `.editorconfig`, `docker-compose.yml`, `.env.example`. (`.gitignore` already complete — verified, no change.)

**Created — apps/api:** `pyproject.toml`, `ruff.toml`, `src/takab_api/__init__.py`, `src/takab_api/main.py`, `src/takab_api/health.py`, `tests/__init__.py`, `tests/test_health.py`.

**Created — apps/web:** `package.json`, `tsconfig.json`, `tsconfig.node.json`, `vite.config.ts`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/App.test.tsx`, `src/vite-env.d.ts`, `eslint.config.js`, `.prettierrc`, `vitest.setup.ts`.

**Created — placeholders:** `apps/edge/README.md`, `packages/schemas/README.md`, `packages/sdk-ts/README.md`, `infra/terraform/README.md`.

**Created — CI:** `.github/workflows/ci.yml`.

---

## Task 1: Repo reorg — relocate docs and schema

**Files:**
- Move: 6 tracked files into `docs/` and `db/` (see File Structure)
- Create: `docs/CLAUDE.md` (copy of root)

- [ ] **Step 1: Create target dirs and move tracked files**

```bash
mkdir -p docs/prompts db
git mv FASE-0-AUDITORIA-Y-PLAN-TAKAB.md docs/FASE-0-AUDITORIA-Y-PLAN-TAKAB.md
git mv RBAC-TAKAB.md docs/RBAC-TAKAB.md
git mv TASKS.md docs/TASKS.md
git mv USER-STORIES.md docs/USER-STORIES.md
git mv schema.sql db/schema.sql
git mv PROMPT-01-monorepo.md docs/prompts/PROMPT-01-monorepo.md
cp CLAUDE.md docs/CLAUDE.md
```

- [ ] **Step 2: Verify**

Run: `ls docs db && git status --short`
Expected: docs/ has the 4 docs + CLAUDE.md + prompts/; db/ has schema.sql; renames staged.

---

## Task 2: Root tooling files

**Files:**
- Create: `.editorconfig`, `docker-compose.yml`, `.env.example`, `README.md`, `Makefile`

- [ ] **Step 1: `.editorconfig`**

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 2

[*.py]
indent_size = 4

[*.md]
trim_trailing_whitespace = false

[Makefile]
indent_style = tab
```

- [ ] **Step 2: `docker-compose.yml`** (Postgres 16 + TimescaleDB + PostGIS for dev; image bundles all three)

```yaml
services:
  db:
    image: timescale/timescaledb-ha:pg16
    container_name: takab-db
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-takab}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-takab_dev}
      POSTGRES_DB: ${POSTGRES_DB:-takab}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - takab_pgdata:/home/postgres/pgdata/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-takab}"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  takab_pgdata:
```

- [ ] **Step 3: `.env.example`** (no real secrets — regla de oro #6)

```bash
# ── Postgres (dev local, docker-compose) ──
POSTGRES_USER=takab
POSTGRES_PASSWORD=takab_dev
POSTGRES_DB=takab
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://takab:takab_dev@localhost:5432/takab

# ── API ──
API_HOST=0.0.0.0
API_PORT=8000

# ── Web ──
VITE_API_BASE_URL=http://localhost:8000
```

- [ ] **Step 4: `README.md`** (replace empty `readme.md`)

```markdown
# TAKAB Technology

Plataforma SaaS multi-tenant de alertamiento sísmico, monitoreo estructural y
continuidad operativa post-sismo (edge + cloud). Ver `CLAUDE.md` para contexto maestro.

## Estructura

- `apps/api` — FastAPI (Python 3.12)
- `apps/web` — React 18 + TypeScript + Vite
- `apps/edge` — software del Raspberry Pi 5 (placeholder)
- `packages/schemas` — contratos compartidos (placeholder)
- `packages/sdk-ts` — cliente TS generado (placeholder)
- `infra/terraform` — IaC (placeholder)
- `db/` — `schema.sql` de referencia
- `docs/` — documentación maestra y planes

## Desarrollo local

Requisitos: Docker, Python 3.12, Node 20+, GNU Make.

```bash
cp .env.example .env
make dev        # levanta Postgres (compose) + API (:8000) + web (:5173)
```

Verifica la API: `curl localhost:8000/health` → `{"status":"ok"}`

## Comandos

| Comando      | Qué hace                                  |
|--------------|-------------------------------------------|
| `make dev`   | Postgres + API + web en paralelo          |
| `make lint`  | ruff + eslint + prettier (check)          |
| `make test`  | pytest + vitest                           |
| `make fmt`   | ruff format + prettier write              |
| `make down`  | apaga el compose                          |
```

- [ ] **Step 5: `Makefile`** (tab-indented; `.ONESHELL` not needed)

```makefile
.PHONY: dev down lint test fmt api web db install

API_DIR := apps/api
WEB_DIR := apps/web

install:
	cd $(API_DIR) && python -m pip install -e ".[dev]"
	cd $(WEB_DIR) && npm install

db:
	docker compose up -d db

api:
	cd $(API_DIR) && uvicorn takab_api.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd $(WEB_DIR) && npm run dev

dev: db
	$(MAKE) -j2 api web

down:
	docker compose down

lint:
	cd $(API_DIR) && ruff check .
	cd $(WEB_DIR) && npm run lint && npm run format:check

test:
	cd $(API_DIR) && pytest -q
	cd $(WEB_DIR) && npm run test -- --run

fmt:
	cd $(API_DIR) && ruff format . && ruff check --fix .
	cd $(WEB_DIR) && npm run format
```

- [ ] **Step 6: Commit reorg + tooling**

```bash
git rm readme.md
git add .editorconfig docker-compose.yml .env.example README.md Makefile docs db
git commit -m "chore: relocate docs/schema and add root tooling"
```

---

## Task 3: apps/api — FastAPI with /health (TDD)

**Files:**
- Create: `apps/api/pyproject.toml`, `apps/api/ruff.toml`
- Create: `apps/api/src/takab_api/__init__.py`, `main.py`, `health.py`
- Test: `apps/api/tests/__init__.py`, `apps/api/tests/test_health.py`

- [ ] **Step 1: `pyproject.toml`** (minimal deps)

```toml
[project]
name = "takab-api"
version = "0.1.0"
description = "TAKAB API — FastAPI backend"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "httpx>=0.27",
    "ruff>=0.7",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: `ruff.toml`**

```toml
target-version = "py312"
line-length = 100
src = ["src", "tests"]

[lint]
select = ["E", "F", "I", "UP", "B", "W"]
```

- [ ] **Step 3: Write the failing test** — `apps/api/tests/test_health.py`

```python
from fastapi.testclient import TestClient

from takab_api.main import app

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

Also create empty `apps/api/tests/__init__.py`.

- [ ] **Step 4: Run test to verify it fails**

Run: `cd apps/api && python -m pip install -e ".[dev]" && pytest -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'takab_api'`.

- [ ] **Step 5: Minimal implementation**

`apps/api/src/takab_api/__init__.py`:
```python
__all__ = ["__version__"]
__version__ = "0.1.0"
```

`apps/api/src/takab_api/health.py`:
```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

`apps/api/src/takab_api/main.py`:
```python
from fastapi import FastAPI

from takab_api.health import router as health_router

app = FastAPI(title="TAKAB API", version="0.1.0")
app.include_router(health_router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd apps/api && pytest -q`
Expected: PASS (1 passed).

- [ ] **Step 7: Lint check**

Run: `cd apps/api && ruff check .`
Expected: `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add apps/api
git commit -m "feat(api): scaffold FastAPI app with /health endpoint"
```

---

## Task 4: apps/web — Vite + React + strict TS (TDD)

**Files:**
- Create: `apps/web/package.json`, `tsconfig.json`, `tsconfig.node.json`, `vite.config.ts`, `index.html`
- Create: `src/main.tsx`, `src/App.tsx`, `src/vite-env.d.ts`, `vitest.setup.ts`
- Create: `eslint.config.js`, `.prettierrc`
- Test: `src/App.test.tsx`

> **Context7:** before writing `vite.config.ts` / `vitest` config, confirm current Vite 5 + Vitest API via Context7 (CLAUDE.md §7) rather than from memory.

- [ ] **Step 1: `package.json`**

```json
{
  "name": "takab-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "eslint .",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "test": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@types/react": "^18.3.11",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.2",
    "eslint": "^9.13.0",
    "jsdom": "^25.0.1",
    "prettier": "^3.3.3",
    "typescript": "^5.6.3",
    "typescript-eslint": "^8.10.0",
    "vite": "^5.4.9",
    "vitest": "^2.1.3"
  }
}
```

- [ ] **Step 2: `tsconfig.json`** (strict)

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vitest.setup.ts"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 3: `tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noEmit": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: `vite.config.ts`** (verify against Context7)

```typescript
/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./vitest.setup.ts",
  },
});
```

- [ ] **Step 5: `vitest.setup.ts`**

```typescript
import "@testing-library/jest-dom";
```

- [ ] **Step 6: `index.html`**

```html
<!doctype html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>TAKAB</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: `src/vite-env.d.ts`**

```typescript
/// <reference types="vite/client" />
```

- [ ] **Step 8: `.prettierrc`**

```json
{
  "semi": true,
  "singleQuote": false,
  "printWidth": 100,
  "trailingComma": "all"
}
```

- [ ] **Step 9: `eslint.config.js`** (flat config, ESLint 9; verify via Context7)

```javascript
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2022, sourceType: "module" },
  },
);
```

> Note: add `@eslint/js` to devDependencies if not pulled transitively — run `npm install @eslint/js -D` in Step 11 if eslint errors on the import.

- [ ] **Step 10: Write the failing test** — `src/App.test.tsx`

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("renders the TAKAB placeholder", () => {
    render(<App />);
    expect(screen.getByText("TAKAB")).toBeInTheDocument();
  });
});
```

- [ ] **Step 11: Run test to verify it fails**

Run: `cd apps/web && npm install && npm run test -- --run`
Expected: FAIL — cannot resolve `./App` (file not created yet).

- [ ] **Step 12: Minimal implementation**

`src/App.tsx`:
```tsx
export default function App() {
  return (
    <main>
      <h1>TAKAB</h1>
    </main>
  );
}
```

`src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 13: Run test + build + lint to verify green**

Run: `cd apps/web && npm run test -- --run && npm run build && npm run lint && npm run format:check`
Expected: test PASS (1 passed); build emits `dist/`; eslint clean; prettier clean. If prettier flags files, run `npm run format` then re-check.

- [ ] **Step 14: Commit**

```bash
git add apps/web
git commit -m "feat(web): scaffold Vite + React + strict TS with placeholder page"
```

---

## Task 5: Placeholder packages

**Files:**
- Create: `apps/edge/README.md`, `packages/schemas/README.md`, `packages/sdk-ts/README.md`, `infra/terraform/README.md`

- [ ] **Step 1: Create each README**

`apps/edge/README.md`:
```markdown
# apps/edge

Software del Raspberry Pi 5 (cerebro del gabinete): `takab_ingest`, `takab_dsp`,
`takab_rules`, `takab_gpio`, `takab_sync`, `takab_local_api` + units de systemd.
Lee SeedLink del Raspberry Shake, recibe SASMEX por GPIO, dispara relés y sincroniza a la nube.
**No tocar Shake OS.** Placeholder — implementación en Bloque B.
```

`packages/schemas/README.md`:
```markdown
# packages/schemas

Contratos compartidos (Pydantic v2 + JSON Schema → tipos TS). Fuente de verdad de
los modelos que cruzan edge ↔ nube ↔ web. Placeholder.
```

`packages/sdk-ts/README.md`:
```markdown
# packages/sdk-ts

Cliente TypeScript generado del OpenAPI de `apps/api`. Placeholder.
```

`infra/terraform/README.md`:
```markdown
# infra/terraform

IaC de la base AWS (VPC, RDS, S3, SQS, Cognito, ECR, IoT Core), entornos `dev` y `prod`.
Placeholder — implementación en T-1.2.
```

- [ ] **Step 2: Commit**

```bash
git add apps/edge packages infra
git commit -m "chore: add placeholder READMEs for edge, packages, infra"
```

---

## Task 6: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: `ci.yml`** (lint+test for api and web on PR + push to main)

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  api:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/api
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -q

  web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm install
      - run: npm run lint
      - run: npm run format:check
      - run: npm run test -- --run
      - run: npm run build
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add lint+test workflow for api and web"
```

---

## Task 7: Full verification + final squash-free check

- [ ] **Step 1: Run the full local gate**

Run:
```bash
cd apps/api && ruff check . && pytest -q && cd ../..
cd apps/web && npm run lint && npm run format:check && npm run test -- --run && npm run build && cd ../..
```
Expected: ruff clean, pytest 1 passed, eslint clean, prettier clean, vitest 1 passed, vite build emits dist/.

- [ ] **Step 2: Confirm /health manually (optional, needs uvicorn running)**

Run: `cd apps/api && uvicorn takab_api.main:app --port 8000 &` then `curl localhost:8000/health`
Expected: `{"status":"ok"}`. Kill the server after.

- [ ] **Step 3: Secret scan of the diff**

Run: `git log --oneline -8 && git grep -nE "(AKIA|secret|password=)" -- ':!docs' ':!.env.example' ':!docker-compose.yml'`
Expected: no real secrets (only `.env.example` placeholders, which are excluded).

- [ ] **Step 4: Verify folder structure complete**

Run: `ls apps packages infra db docs .github/workflows`
Expected: apps/{api,web,edge}, packages/{schemas,sdk-ts}, infra/terraform, db/schema.sql, docs/*, ci.yml present.

---

## Self-Review

- **Spec coverage:** root files ✔ (T2), apps/api+/health+test ✔ (T3), apps/web strict+test ✔ (T4), placeholders ✔ (T5), db/schema.sql relocated ✔ (T1), docs relocated ✔ (T1), Makefile dev/lint/test/fmt ✔ (T2), CI ✔ (T6), .gitignore already covers .env/node_modules/__pycache__/.terraform ✔ (verified, no task needed), conventional commits ✔ (per task).
- **Note on commit message:** prompt suggests one `chore: scaffold monorepo foundation` commit; this plan uses per-task conventional commits for cleaner history. Acceptable under CLAUDE.md §6 (conventional commits). Final commit message variant is reviewer's choice.
- **Placeholder scan:** none — all code blocks complete.
- **Type consistency:** `takab_api.main:app`, `/health` → `{"status":"ok"}`, `App` default export referenced consistently across api/web/CI/Makefile.

---

## Acceptance Criteria (DoD)

- [ ] `make dev` levanta Postgres + API + web sin error
- [ ] `curl localhost:8000/health` → `{"status":"ok"}`
- [ ] `apps/web` compila (`vite build`) y renderiza placeholder "TAKAB"
- [ ] `make lint` limpio (ruff + eslint + prettier)
- [ ] `make test` verde (pytest + vitest)
- [ ] `ci.yml` corre lint+test de api y web
- [ ] Estructura completa; docs en `docs/`; `db/schema.sql` presente
- [ ] `.gitignore` excluye `.env`, `node_modules`, `__pycache__`, `.terraform`
- [ ] Commits convencionales
