#!/bin/bash
# Orquestador del SOC local (lo invoca `make soc-local`). Levanta en segundo
# plano API + worker de incidentes + web dev server, y en primer plano el
# gabinete simulado + bridge (demo/soc_local.py). Ctrl+C apaga todo.
#
# Precondiciones (las prepara el target): DB local migrada y sembrada
# (make demo-db), .env.dev-auth generado y web/.env presente.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/.local-soc/logs"
mkdir -p "$LOGS"

# Auth de dev (JWKS inline ⇒ la API monta /dev/token; jamás en producción).
set -a
# shellcheck disable=SC1091
. "$ROOT/.env.dev-auth"
TAKAB_API_DATABASE_URL="${TAKAB_API_DATABASE_URL:-postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab}"

# [T-6.18] LA BAJADA nube→gabinete. Sin esto la API publicaba a AWS IoT Core, en
# una laptop sin credenciales: cada comando firmado moría al publicar y un
# simulacro salía con «5 SIN COMANDO EMITIDO», así que el aborto por sismo real
# no se podía ensayar en local.
#
# Las DOS mitades tienen que coincidir en dos cosas y por eso salen de aquí:
#   · el BUZÓN (`TAKAB_DEMO_DOWNLINK`): lo lee `demo/api_local.py` para publicar
#     y `demo/soc_local.py` se lo pasa al gabinete en `--downlink`;
#   · la CLAVE HMAC: el gabinete la toma de `TAKAB_EDGE_HMAC_KEY` (si falta,
#     genera una efímera y RECHAZA todo comando de la nube, en silencio para
#     quien mira la consola) y la API, del mapa inline `command_hmac_keys_json`,
#     que gana sobre Secrets Manager. Es fija a propósito: reiniciar la API sin
#     reiniciar el gabinete no puede dejar la bajada muda.
TAKAB_DEMO_DOWNLINK="${TAKAB_DEMO_DOWNLINK:-$ROOT/.local-soc/bajada}"
TAKAB_EDGE_HMAC_KEY="${TAKAB_EDGE_HMAC_KEY:-$(printf '6f%062d' 618)}"
TAKAB_API_COMMAND_HMAC_KEYS_JSON="${TAKAB_API_COMMAND_HMAC_KEYS_JSON:-{\"gw-sim-0001\":\"$TAKAB_EDGE_HMAC_KEY\"}}"
mkdir -p "$TAKAB_DEMO_DOWNLINK"

# Evidencia contra el MinIO de docker-compose: sin esto la API no tiene bucket
# y el botón DICTAMEN PDF muere en 503. El endpoint es 127.0.0.1 (no `minio`)
# porque el presigned URL lo abre el NAVEGADOR, no el contenedor.
TAKAB_API_EVIDENCE_BUCKET="${TAKAB_API_EVIDENCE_BUCKET:-takab-dev-evidence}"
TAKAB_API_S3_ENDPOINT_URL="${TAKAB_API_S3_ENDPOINT_URL:-http://127.0.0.1:9000}"
AWS_ACCESS_KEY_ID="${MINIO_ROOT_USER:-takab}"
AWS_SECRET_ACCESS_KEY="${MINIO_ROOT_PASSWORD:-takab_dev_secret}"
set +a

PIDS=()
cleanup() {
  echo ""
  echo "apagando SOC local…"
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# `PYTHONPATH=$ROOT` porque uvicorn importa `demo.api_local` y el venv de la API
# no conoce la raíz del repo; el propio módulo se añade al path DESPUÉS de que
# Python lo encuentre, que es demasiado tarde.
echo "→ API en :8000, con la bajada al gabinete (log: $LOGS/api.log)"
(cd "$ROOT/api" && PYTHONPATH="$ROOT" exec uv run uvicorn demo.api_local:app --host 0.0.0.0 --port 8000) \
  >"$LOGS/api.log" 2>&1 &
PIDS+=($!)

echo "→ worker de incidentes/dictamen (log: $LOGS/worker.log)"
(cd "$ROOT/api" && exec uv run python -m takab_api.incident) \
  >"$LOGS/worker.log" 2>&1 &
PIDS+=($!)

echo "→ web dev server en :5173 (log: $LOGS/web.log)"
(cd "$ROOT/web" && exec npm run dev) >"$LOGS/web.log" 2>&1 &
PIDS+=($!)

# Primer plano: gabinete real simulado + bridge (imprime URLs y estímulos).
cd "$ROOT/api" && exec uv run python "$ROOT/demo/soc_local.py" "$@"
