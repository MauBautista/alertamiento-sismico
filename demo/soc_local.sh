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
