#!/usr/bin/env bash
# Baja las credenciales de un gateway (cert mTLS + clave HMAC) desde Secrets
# Manager y las instala en local o en el dispositivo via SSH.
# Nunca imprime secretos a stdout — con UNA excepción deliberada: el PIN del
# panel LAN (T-1.43) se imprime al final porque imprimirlo ES la vía de entrega
# al responsable del edificio (no existe en Secrets Manager ni en otro canal).
#
# Uso: provision_gateway.sh <thing_name> [ssh_host]
#   sin ssh_host: escribe ./certs-<thing_name>/{cert.pem,key.pem,ca.pem,edge.env}
#   con ssh_host: instala en <ssh_host>:/etc/takab/{certs/,edge.env} (sudo)
set -euo pipefail

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "uso: $0 <thing_name> [ssh_host]" >&2
  exit 1
fi

THING="$1"
SSH_HOST="${2:-}"
PROFILE=takab-dev
REGION=us-east-2
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TF_DIR="$ROOT/infra/terraform/envs/dev"

umask 077
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Dos secretos desde T-1.38: el del certificado (cert+key mTLS, prefijo que la
# nube JAMAS puede leer) y el HMAC de comandos (prefijo gateway-hmac, el que la
# nube resuelve por gabinete en runtime).
aws secretsmanager get-secret-value \
  --secret-id "takab/dev/gateway/$THING" \
  --query SecretString --output text \
  --profile "$PROFILE" --region "$REGION" >"$TMP/secret.json"

aws secretsmanager get-secret-value \
  --secret-id "takab/dev/gateway-hmac/$THING" \
  --query SecretString --output text \
  --profile "$PROFILE" --region "$REGION" >"$TMP/hmac.json"

python3 - "$TMP" <<'PY'
import json
import pathlib
import sys

tmp = pathlib.Path(sys.argv[1])
data = json.loads((tmp / "secret.json").read_text())
(tmp / "cert.pem").write_text(data["cert_pem"])
(tmp / "key.pem").write_text(data["private_key"])
hmac = json.loads((tmp / "hmac.json").read_text())
(tmp / "hmac.key").write_text(hmac["hmac_key"])
PY

curl -fsSL https://www.amazontrust.com/repository/AmazonRootCA1.pem -o "$TMP/ca.pem"

MQTT_ENDPOINT="$(terraform -chdir="$TF_DIR" output -raw iot_endpoint)"

# PIN del panel LAN (T-1.43): 6 dígitos aleatorios. Se imprime UNA vez al final
# — es la vía de entrega al responsable del edificio; sin él, las acciones del
# panel quedan 403 fail-closed en producción.
LOCAL_PIN="$(python3 -c 'import secrets; print(f"{secrets.randbelow(10**6):06d}")')"

printf 'TAKAB_EDGE_HMAC_KEY=%s\nTAKAB_EDGE_MQTT_ENDPOINT=%s\nTAKAB_EDGE_LOCAL_API_PIN=%s\n' \
  "$(cat "$TMP/hmac.key")" "$MQTT_ENDPOINT" "$LOCAL_PIN" >"$TMP/edge.env"

if [ -z "$SSH_HOST" ]; then
  OUT_DIR="./certs-$THING"
  mkdir -p "$OUT_DIR"
  for f in cert.pem key.pem ca.pem edge.env; do
    cp "$TMP/$f" "$OUT_DIR/$f"
    chmod 600 "$OUT_DIR/$f"
  done
  echo "credenciales de $THING escritas en $OUT_DIR/ (no versionar)"
else
  ssh "$SSH_HOST" 'sudo mkdir -p /etc/takab/certs'
  for f in cert.pem key.pem ca.pem; do
    ssh "$SSH_HOST" "sudo tee /etc/takab/certs/$f >/dev/null && sudo chmod 600 /etc/takab/certs/$f" <"$TMP/$f"
  done
  ssh "$SSH_HOST" 'sudo tee /etc/takab/edge.env >/dev/null && sudo chmod 600 /etc/takab/edge.env' <"$TMP/edge.env"
  echo "credenciales de $THING instaladas en $SSH_HOST:/etc/takab"
fi

echo "PIN del panel local de $THING: $LOCAL_PIN — entrégalo al responsable del edificio"
