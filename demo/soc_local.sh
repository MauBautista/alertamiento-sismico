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

echo "→ API en :8000 (log: $LOGS/api.log)"
(cd "$ROOT/api" && exec uv run uvicorn takab_api.main:app --host 0.0.0.0 --port 8000) \
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
