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
# SSH no interactivo no carga el PATH de login: uv vive en ~/.local/bin.
export PATH="$HOME/.local/bin:$PATH"
cd /opt/takab/edge
# takab-edge corre como root y deja __pycache__ de root DENTRO del venv; sin
# esto, el uv sync del usuario falla con Permission denied en cada deploy.
[ -d .venv ] && sudo chown -R "$USER":"$USER" .venv
# AMBOS extras del Pi real: `hardware` (lgpio) y `aws` (awsiotsdk/awscrt, el
# transporte mTLS a IoT Core). Sincronizar solo uno hace que uv PODE el otro:
# el primer deploy real podó awsiotsdk y dejó al gabinete offline spooleando.
uv sync --extra hardware --extra aws --quiet
sudo install -m 0644 systemd/takab-edge.service systemd/takab-gpio.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart takab-edge
sleep 3
systemctl is-active takab-edge
journalctl -u takab-edge -n 8 --no-pager | tail -8'

echo "✓ edge desplegado y takab-edge activo en ${HOST}"
