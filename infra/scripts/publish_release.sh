#!/usr/bin/env bash
# [T-7.64] Publica en la nube el firmware que un despliegue acaba de activar.
#
# El TRANSPORTE. La decisión de QUÉ se publica y qué no vive en
# `api/src/takab_api/ops/publish_release.py`, que es quien escribe; este script
# sólo lo alcanza. Se separan porque la regla («un `-dirty` no entra en el
# registro») tiene que valer también para quien llame al CLI a mano, y una regla
# escrita en dos sitios acaba divergiendo.
#
# POR QUÉ SSM Y NO UN `curl` AL ENDPOINT. `POST /fleet/releases` existe y está
# bien hecho, pero exige `takab_superadmin`, y ese pool es SRP + MFA TOTP
# obligatorio: no hay cliente `client_credentials` en el terraform de identidad,
# así que ninguna máquina puede presentarse. Un despliegue que dependiera de que
# alguien teclee seis dígitos publicaría tan poco como se publicaba hasta hoy:
# CERO filas en `fw_releases`, medidas el 2026-09-20.
#
# La instancia no tiene ingreso SSH —todo va por `aws ssm send-command`, igual
# que `deploy/cloud/deploy.sh`— y dentro corre el CLI en el contenedor `api`, que
# ya tiene las credenciales de la base de la aplicación montadas
# (`/run/takab/db-app.env`). Así el INSERT sigue pasando por la MISMA GRANT y la
# MISMA RLS que el endpoint: `fw_rel_publish` exige `app_role() =
# 'takab_superadmin'` y es la base quien lo impone, no este script.
#
# ⚠️ ESTO NO PUEDE TUMBAR UN DESPLIEGUE. Quien lo llama (`deploy/edge/deploy.sh`)
# lo invoca DESPUÉS de que el gabinete ya esté corriendo el código bueno y trata
# cualquier fallo como algo que se DECLARA y se reintenta, no como un despliegue
# fallido. El registro se puede rellenar después; el gabinete no se puede
# des-desplegar.
#
# Uso:
#   infra/scripts/publish_release.sh <version> [notas]
#   make cloud-publish-release VERSION=62f3f1e
set -euo pipefail

VERSION="${1:-}"
NOTAS="${2:-}"

if [ -z "$VERSION" ]; then
  echo "uso: $0 <version> [notas]" >&2
  echo "  <version> = EXACTAMENTE el FW_VERSION que el gabinete reportará." >&2
  exit 2
fi

AWS_PROFILE="${AWS_PROFILE:-takab-dev}"
TF_DIR="$(cd "$(dirname "$0")/../terraform/envs/dev" && pwd)"
AWS_REGION="${AWS_REGION:-$(terraform -chdir="$TF_DIR" output -raw region 2>/dev/null || echo us-east-2)}"
INSTANCE_ID="$(terraform -chdir="$TF_DIR" output -raw db_instance_id)"

COMPOSE="/opt/takab/cloud/docker-compose.yml"
ENTORNO="/etc/takab/deploy.env"

# El actor viaja en el entorno del CLI y no como argumento: así la fila de
# auditoría dice `deploy:<quien>@<donde>` y no `user:<uuid>`. Son dos hechos
# distintos —un despliegue y una persona en la consola— y hasta hoy sólo existía
# la segunda forma de decirlo.
ACTOR="${TAKAB_DEPLOY_ACTOR:-${USER:-desconocido}}"

# `printf %q` y no comillas a mano: la versión sale de `git describe` y las notas
# las escribe quien llama. Un argumento sin escapar aquí es una inyección de
# shell en una instancia de producción.
REMOTO="$(printf 'docker compose -f %q --env-file %q exec -T -e TAKAB_DEPLOY_ACTOR=%q api python -m takab_api.ops.publish_release %q' \
  "$COMPOSE" "$ENTORNO" "$ACTOR" "$VERSION")"
if [ -n "$NOTAS" ]; then
  REMOTO+=" $(printf -- '--notes %q' "$NOTAS")"
fi

echo "→ publicando release '${VERSION}' en ${INSTANCE_ID}"

# Los parámetros van como JSON COMPLETO vía file://: el shorthand del CLI no
# decodifica los \n y el script llega al EC2 como una sola línea. La trampa está
# medida en `deploy/cloud/deploy.sh` desde el primer despliegue real de T-1.39.
PARAMS="$(mktemp)"
trap 'rm -f "$PARAMS"' EXIT
python3 -c 'import json,sys; print(json.dumps({"commands": [sys.stdin.read()]}))' \
  <<<"$REMOTO" >"$PARAMS"

CMD_ID="$(aws ssm send-command \
  --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "takab publish release ${VERSION}" \
  --parameters "file://$PARAMS" \
  --query Command.CommandId --output text)"

until aws ssm get-command-invocation --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" --query Status --output text 2>/dev/null |
  grep -qE '^(Success|Failed|Cancelled|TimedOut)$'; do
  sleep 3
done

# Mismo `--query` con forma de objeto que `deploy/cloud/deploy.sh`, y por la
# misma razón: una sola llamada trae el estado Y lo que el CLI imprimió, que es
# donde está la razón de un rechazo (un `-dirty`, por ejemplo).
aws ssm get-command-invocation --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
  --query '{estado:Status,salida:StandardOutputContent,error:StandardErrorContent}' \
  --output text | sed '/^$/d;s/^/  /'

ESTADO="$(aws ssm get-command-invocation --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" --query Status --output text)"

if [ "$ESTADO" != Success ]; then
  echo "✗ no se pudo publicar '${VERSION}' (SSM: ${ESTADO})" >&2
  exit 1
fi

echo "✓ registro de releases al día para '${VERSION}'"
