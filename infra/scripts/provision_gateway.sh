#!/usr/bin/env bash
# Baja las credenciales de un gateway (cert mTLS + clave HMAC) desde Secrets
# Manager y las instala en local o en el dispositivo via SSH.
# Nunca imprime secretos a stdout — con UNA excepción deliberada: el PIN del
# panel LAN (T-1.43) se imprime al final porque imprimirlo ES la vía de entrega
# al responsable del edificio (no existe en Secrets Manager ni en otro canal).
#
# Uso: provision_gateway.sh <thing_name> [ssh_host] [--site-lat LAT --site-lon LON]
#   sin ssh_host: escribe ./certs-<thing_name>/{cert.pem,key.pem,ca.pem,edge.env}
#   con ssh_host: instala en <ssh_host>:/etc/takab/{certs/,edge.env} (sudo)
#   --site-lat/--site-lon (T-2.20, JUNTOS): añade TAKAB_EDGE_SITE_LAT/LON a las
#   claves gestionadas. Sin flags NO se tocan: unas coordenadas puestas a mano
#   en edge.env sobreviven al re-aprovisionamiento (merge_env.py las preserva).
set -euo pipefail

SITE_LAT=""
SITE_LON=""
CATALOG=""
POSITIONAL=()
while [ $# -gt 0 ]; do
  case "$1" in
  --site-lat)
    SITE_LAT="${2:?--site-lat requiere un valor}"
    shift 2
    ;;
  --site-lon)
    SITE_LON="${2:?--site-lon requiere un valor}"
    shift 2
    ;;
  --catalog)
    # T-2.23: instantánea local del catálogo SSN para GET /api/catalog del panel.
    CATALOG="${2:?--catalog requiere un archivo}"
    shift 2
    ;;
  *)
    POSITIONAL+=("$1")
    shift
    ;;
  esac
done
set -- ${POSITIONAL+"${POSITIONAL[@]}"}

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "uso: $0 <thing_name> [ssh_host] [--site-lat LAT --site-lon LON] [--catalog FILE]" >&2
  exit 1
fi

if [ -n "$CATALOG" ] && [ ! -f "$CATALOG" ]; then
  echo "error: --catalog $CATALOG no existe" >&2
  exit 1
fi

# Las coordenadas van en PAR (una suelta no ubica nada) y se validan AQUÍ:
# un valor fuera de rango bricktearía el servicio al reiniciar con settings
# inválidos — mejor fallar antes de tocar el gabinete.
if [ -n "$SITE_LAT$SITE_LON" ]; then
  if [ -z "$SITE_LAT" ] || [ -z "$SITE_LON" ]; then
    echo "error: --site-lat y --site-lon van JUNTOS" >&2
    exit 1
  fi
  python3 - "$SITE_LAT" "$SITE_LON" <<'PY'
import sys

lat, lon = float(sys.argv[1]), float(sys.argv[2])
if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
    sys.exit("error: coordenadas fuera de rango (lat [-90,90], lon [-180,180])")
PY
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

# Estas son las UNICAS claves que el aprovisionamiento gobierna. Un gabinete en
# operacion tiene muchas mas (estacion, host de SeedLink, rutas de certificados,
# calibracion MEDIDA del sensor, nombre del sitio), puestas al instalarlo. Por eso
# lo de abajo FUSIONA en vez de sobrescribir: instalar con `sudo tee` a secas
# borraba esas otras claves y dejaba el gabinete sin sensor y sin calibracion.
#
# `GATEWAY_ID` es la IDENTIDAD y por eso nace aqui, no a mano: `settings.py` tiene el
# default "gw-dev-0001", que coincidia por CASUALIDAD con el nombre del primer gabinete
# real — asi que gw-dev-0001 llevaba meses funcionando sin tener la clave en su
# edge.env. La segunda estacion habria arrancado publicando como la primera: mismo
# client-id MQTT y datos atribuidos al sitio y al tenant equivocados. El thing_name ya
# lo recibe este script como argumento; escribirlo cuesta una linea.
#
# `DEV_MODE=false` por la misma razon: el default es `true` y un gabinete de campo que
# lo herede corre en modo desarrollo sin que nadie lo note. Si estamos bajando
# credenciales REALES de Secrets Manager, esto no es un entorno de desarrollo.
printf 'TAKAB_EDGE_GATEWAY_ID=%s\nTAKAB_EDGE_DEV_MODE=false\nTAKAB_EDGE_HMAC_KEY=%s\nTAKAB_EDGE_MQTT_ENDPOINT=%s\nTAKAB_EDGE_LOCAL_API_PIN=%s\n' \
  "$THING" "$(cat "$TMP/hmac.key")" "$MQTT_ENDPOINT" "$LOCAL_PIN" >"$TMP/edge.env.managed"

# T-2.20: la ubicación SOLO entra a lo gestionado si el operador la pidió con
# flags. Sin flags, merge_env.py preserva lo que el edge.env ya tenga.
if [ -n "$SITE_LAT" ]; then
  printf 'TAKAB_EDGE_SITE_LAT=%s\nTAKAB_EDGE_SITE_LON=%s\n' \
    "$SITE_LAT" "$SITE_LON" >>"$TMP/edge.env.managed"
fi

if [ -z "$SSH_HOST" ]; then
  OUT_DIR="./certs-$THING"
  mkdir -p "$OUT_DIR"
  # `--existing` puede apuntar a un archivo inexistente: merge_env.py lo trata
  # como "no hay nada previo que conservar".
  if [ -f "$OUT_DIR/edge.env" ]; then cp "$OUT_DIR/edge.env" "$TMP/edge.env.existing"; fi
  python3 "$ROOT/infra/scripts/merge_env.py" \
    --managed "$TMP/edge.env.managed" \
    --existing "$TMP/edge.env.existing" \
    --out "$TMP/edge.env"
  for f in cert.pem key.pem ca.pem edge.env; do
    cp "$TMP/$f" "$OUT_DIR/$f"
    chmod 600 "$OUT_DIR/$f"
  done
  if [ -n "$CATALOG" ]; then
    cp "$CATALOG" "$OUT_DIR/ssn-catalog.json"
    chmod 644 "$OUT_DIR/ssn-catalog.json" # lo lee el panel de a pie: no es secreto
    echo "catálogo SSN copiado a $OUT_DIR/ssn-catalog.json → instálalo en /var/lib/takab/"
    # T-2.66: el panel lo lee UNA vez al construir y rotula su EDAD y su ORIGEN
    # (aquí, ARCHIVO PROVISIONADO). Sin reiniciar, el gabinete no se entera.
    echo "  · reinicia takab-edge tras instalarlo: el panel lee el catálogo UNA vez al arrancar"
  fi
  echo "credenciales de $THING escritas en $OUT_DIR/ (no versionar)"
else
  # El edge.env que ya viva en el gabinete manda sobre todo lo que no generamos aqui.
  ssh "$SSH_HOST" 'sudo cat /etc/takab/edge.env 2>/dev/null || true' >"$TMP/edge.env.existing"
  python3 "$ROOT/infra/scripts/merge_env.py" \
    --managed "$TMP/edge.env.managed" \
    --existing "$TMP/edge.env.existing" \
    --out "$TMP/edge.env"

  ssh "$SSH_HOST" 'sudo mkdir -p /etc/takab/certs'
  for f in cert.pem key.pem ca.pem; do
    ssh "$SSH_HOST" "sudo tee /etc/takab/certs/$f >/dev/null && sudo chmod 600 /etc/takab/certs/$f" <"$TMP/$f"
  done
  # Respaldo fechado ANTES de tocar nada: si la fusion se equivoca, el estado
  # anterior sigue en el dispositivo y se restaura con un `cp`.
  ssh "$SSH_HOST" 'test -f /etc/takab/edge.env && sudo cp -a /etc/takab/edge.env "/etc/takab/edge.env.bak-$(date +%Y%m%d-%H%M%S)" || true'
  ssh "$SSH_HOST" 'sudo tee /etc/takab/edge.env >/dev/null && sudo chmod 600 /etc/takab/edge.env' <"$TMP/edge.env"
  if [ -n "$CATALOG" ]; then
    # T-2.23: la instantánea vive donde el servicio puede leerla (ReadWritePaths).
    ssh "$SSH_HOST" 'sudo mkdir -p /var/lib/takab && sudo tee /var/lib/takab/ssn-catalog.json >/dev/null && sudo chmod 644 /var/lib/takab/ssn-catalog.json' <"$CATALOG"
    echo "catálogo SSN instalado en $SSH_HOST:/var/lib/takab/ssn-catalog.json"
    # T-2.66: el panel lo lee UNA vez al construir; hasta el reinicio de abajo
    # sigue sirviendo (y rotulando la edad de) la instantánea ANTERIOR.
    echo "  · el panel lee el catálogo UNA vez al arrancar: se ve tras el restart de abajo"
  fi
  echo "credenciales de $THING instaladas en $SSH_HOST:/etc/takab"
  echo "reinicia el servicio para que tome las claves nuevas: ssh $SSH_HOST 'sudo systemctl restart takab-edge'"
fi

echo "PIN del panel local de $THING: $LOCAL_PIN — entrégalo al responsable del edificio"
