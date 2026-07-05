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

> En Windows sin GNU Make/Docker: corre los comandos subyacentes directo
> (`cd apps/api && pytest`, `cd apps/web && npm run test`, etc.).
