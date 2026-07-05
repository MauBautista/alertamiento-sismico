# TAKAB Ailert

Plataforma SaaS multi-tenant de alertamiento sísmico, monitoreo estructural y
continuidad operativa post-sismo (edge + cloud). Ver `CLAUDE.md` para contexto maestro y
`takab-docs/BLUEPRINT-TECNICO-TAKAB.md` para la arquitectura completa.

## Estructura

- `edge/` — software del Raspberry Pi 5 (gateway de inteligencia; placeholder)
- `api/` — FastAPI (Python 3.12)
- `web/` — React 18 + TypeScript + Vite
- `shared/schemas` — contratos compartidos (placeholder)
- `shared/sdk-ts` — cliente TS generado (placeholder)
- `infra/terraform` — IaC (placeholder)
- `db/` — `schema.sql` de referencia
- `takab-docs/` — documentación maestra y planes

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
> (`cd api && pytest`, `cd web && npm run test`, etc.).
