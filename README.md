# TAKAB Ailert

Plataforma SaaS multi-tenant de **alertamiento sísmico, monitoreo estructural y continuidad
operativa post-sismo** (edge + cloud). Ver `CLAUDE.md` para el contexto maestro y
`takab-docs/BLUEPRINT-TECNICO-TAKAB.md` para la arquitectura completa.

El sistema está **en operación**: un gabinete real publicando a la nube, con consola web y app
móvil. El backlog vivo y el estado por tarea están en `takab-docs/TASKS.md`; este README solo
explica cómo moverse por el repo.

> **Este archivo no lleva cifras de estado a propósito** (tests que pasan, migraciones aplicadas,
> qué commit está desplegado). Un número escrito a mano se queda obsoleto en silencio y acaba
> mintiendo — que es justo el fallo que este proyecto ha ido cerrando. Para saber el estado, se le
> pregunta al sistema, no al README (ver *¿Qué está desplegado?* abajo).

## Estructura

| Directorio | Qué es |
|---|---|
| `edge/` | software del gabinete (Python 3.12 · `uv`): SeedLink, señal, reglas, GPIO, actuadores, nube, panel LAN |
| `api/` | backend cloud — FastAPI + REST/WS, ingesta SQS, motor de incidentes |
| `web/` | consola SOC — React 18 + TypeScript + Vite |
| `mobile/` | app móvil (Expo / React Native): ocupante y brigadista |
| `shared/schemas/` | contratos JSON Schema versionados edge↔nube (generados de los modelos Pydantic del edge) |
| `shared/sdk-ts/` | cliente TypeScript generado del OpenAPI |
| `shared/design-tokens/` | tokens de diseño compartidos web/móvil |
| `infra/terraform/` | IaC de AWS (IoT Core, SQS, RDS/EC2, Cognito, observabilidad…) + scripts de operación |
| `deploy/` | despliegue del edge al gabinete y de la nube al EC2 |
| `db/` | `schema.sql` consolidado (fuente de verdad del DDL) y semillas |
| `demo/` | demo de salida de Fase 1 con gabinetes simulados |
| `takab-docs/` | documentación maestra, backlog (`TASKS.md`) y runbooks |

## Desarrollo local

Requisitos: Docker, Python 3.12, Node 20+, GNU Make y [`uv`](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
make dev        # Postgres (compose) + API (:8000) + web (:5173)
```

Verificar la API: `curl localhost:8000/health` → `{"status":"ok","build":"<commit>"}`

## Comandos

| Comando | Qué hace |
|---|---|
| `make dev` | Postgres + API + web en paralelo |
| `make edge` | levanta el gabinete en dev (con simuladores de Shake, WR-1 y BACnet) |
| `make mobile` | Metro de Expo para la app móvil |
| `make test` | api · demo · web · edge · mobile · terraform · scripts de infra |
| `make lint` | ruff + eslint + prettier + expo lint + tsc |
| `make drift` | gates de deriva: OpenAPI ↔ SDK generado ↔ design-tokens |
| `make fmt` | formatea todo |
| `make down` | apaga el compose |

`make test` crea sola la base `takab_test`: la suite de api **exige** una base sin la semilla de
desarrollo, o produce fallos falsos por choque de tenants.

Operación de la nube (requieren sesión AWS: `aws sso login --profile takab-dev`):

| Comando | Qué hace |
|---|---|
| `make cloud-images` | construye y sube las imágenes **arm64** a ECR (el EC2 es Graviton) |
| `make cloud-deploy` | aplica migraciones y levanta la nube en el EC2 vía SSM |
| `make cloud-allow-my-ip` | abre la consola a tu IP pública actual (es dinámica y rota seguido) |
| `make cloud-users` · `cloud-mobile-users` | siembra usuarios de consola / móviles en Cognito |

## ¿Qué está desplegado?

Se le pregunta a cada pieza, que declara su propia versión:

```bash
curl https://<host>/api/health        # commit vivo en la nube
ssh takab-pi5 'cat /opt/takab/edge/FW_VERSION'   # commit vivo en el gabinete
```

El gabinete además publica su versión en cada heartbeat, así que la ficha de flota
(`gateways.fw_version`) se actualiza sola al desplegar. Nada de esto se anota a mano.

## Orden de construcción

**EDGE → CLOUD → FRONTEND.** La inteligencia del gabinete se construye completa antes de tocar la
nube, y la nube sobre contratos ya validados en el edge. Detalle en `edge/README.md`,
`takab-docs/TASKS.md` y el blueprint §13.

## Hardware del gabinete

Dos placas: un **Raspberry Shake RS4D** (sensor sísmico; su Shake OS no se toca) y un
**Raspberry Pi 4 Model B** que es el cerebro — lee SeedLink del Shake, recibe SASMEX por GPIO desde
el receptor **WR-1** (contacto seco), dispara actuadores y sincroniza con la nube.

> El host se llama `takab-pi5` por razones históricas; el hardware verificado es un Pi 4 Model B
> Rev 1.5. `CLAUDE.md` y el blueprint todavía dicen "Pi 5" — pendiente de reconciliar.

---

> En Windows sin GNU Make/Docker, corre los comandos subyacentes directo
> (`cd api && uv run pytest`, `cd web && npm run test`, etc.).
