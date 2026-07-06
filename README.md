# TAKAB Ailert

Plataforma SaaS multi-tenant de alertamiento sísmico, monitoreo estructural y
continuidad operativa post-sismo (edge + cloud). Ver `CLAUDE.md` para contexto maestro y
`takab-docs/BLUEPRINT-TECNICO-TAKAB.md` para la arquitectura completa.

## Estructura

- `edge/` — software del Raspberry Pi 5 (gateway de inteligencia; scaffold + simuladores)
- `api/` — FastAPI (Python 3.12)
- `web/` — React 18 + TypeScript + Vite
- `shared/schemas` — contratos compartidos (placeholder)
- `shared/sdk-ts` — cliente TS generado (placeholder)
- `infra/terraform` — IaC (placeholder)
- `db/` — `schema.sql` de referencia
- `takab-docs/` — documentación maestra y planes

## Desarrollo local

Requisitos: Docker, Python 3.12, Node 20+, GNU Make y [`uv`](https://docs.astral.sh/uv/) (para `edge/`).

```bash
cp .env.example .env
make dev        # levanta Postgres (compose) + API (:8000) + web (:5173)
```

Verifica la API: `curl localhost:8000/health` → `{"status":"ok"}`

## Comandos

| Comando      | Qué hace                                  |
|--------------|-------------------------------------------|
| `make dev`   | Postgres + API + web en paralelo          |
| `make edge`  | levanta el gabinete edge (dev, simuladores) |
| `make lint`  | ruff + eslint + prettier + edge (check)   |
| `make test`  | pytest + vitest + edge (sin hardware)     |
| `make fmt`   | ruff format + prettier write + edge       |
| `make down`  | apaga el compose                          |

> El edge (`edge/`) se construye primero (EDGE→CLOUD→FRONTEND). Detalle en
> `edge/README.md` y `takab-docs/TASKS.md`.

> En Windows sin GNU Make/Docker: corre los comandos subyacentes directo
> (`cd api && pytest`, `cd web && npm run test`, etc.).
