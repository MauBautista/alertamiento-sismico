#!/usr/bin/env bash
# Despliega el código del edge al Pi 5 (T-1.40). Idempotente.
#
# Hasta ahora el código llegaba a /opt/takab por un rsync manual sin versionar
# (el gap lo documentó la auditoría de Fase 1.6). Este script ES el mecanismo:
#   1. rsync de edge/ y shared/schemas/ (lo único que el gabinete ejecuta),
#      preservando el .venv del Pi y excluyendo basura;
#   2. `uv sync --extra hardware` (lgpio) dentro del Pi;
#   3. instala/refresca las unidades systemd versionadas y reinicia takab-edge;
#   4. verificación: unidad activa + últimas líneas del journal.
#
# Credenciales/identidad NO viajan por aquí: /etc/takab/{certs,edge.env} las
# instala infra/scripts/provision_gateway.sh (regla de oro 6).
#
# Uso: deploy/edge/deploy.sh [ssh_host]      (default: takab-pi5)
set -euo pipefail

HOST="${1:-takab-pi5}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "→ sincronizando edge/ y shared/schemas/ a ${HOST}:/opt/takab"
rsync -az --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '.ruff_cache' \
  "$ROOT/edge/" "$HOST:/opt/takab/edge/"
rsync -az --delete "$ROOT/shared/schemas/" "$HOST:/opt/takab/shared/schemas/"

echo "→ dependencias + unidades + reinicio en ${HOST}"
ssh "$HOST" '
set -euo pipefail
cd /opt/takab/edge
uv sync --extra hardware --quiet
sudo install -m 0644 systemd/takab-edge.service systemd/takab-gpio.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart takab-edge
sleep 3
systemctl is-active takab-edge
journalctl -u takab-edge -n 8 --no-pager | tail -8'

echo "✓ edge desplegado y takab-edge activo en ${HOST}"
