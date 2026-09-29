#!/usr/bin/env bash
# [T-9.50 · D-44] Rellena el mapa de la sacudida del HISTÓRICO, en la nube.
#
# La pasada del worker sólo mira hacia atrás `incident_review_ttl_s`: los incidentes
# de antes de T-9.50 (el mapa sólo se calculaba tras la revisión y dentro de 6 h) se
# quedaron sin snapshot, o con uno anterior a D-44 sin superficie. Esto corre UNA vez
# `python -m takab_api.shakemap.rellena` dentro del contenedor `incident-engine`: es
# el único con el DSN de `takab_ingest` que el relleno necesita (hace `SET ROLE
# takab_ingest`; desde el contenedor de la API falla con un error de permiso).
#
# Es idempotente: un incidente con su mapa al día no se recalcula, y lo que no quepa
# en `--max` sale en la siguiente corrida (el relleno lo DICE: «CORTADO POR …»).
#
# Uso (lo corre Mauricio con `!`):
#
#     infra/scripts/rellena_mapas.sh 2026-07-01
#     infra/scripts/rellena_mapas.sh 2026-07-01 2026-09-28 400
#     TF_DEV=infra/terraform/envs/dev ../otro-worktree/infra/scripts/rellena_mapas.sh 2026-07-01
#
# Mismo canal que `publish_release.sh`: SSM → `docker compose exec`.
set -euo pipefail

DESDE="${1:-}"
HASTA="${2:-}"
MAX="${3:-}"
if [ -z "$DESDE" ]; then
  echo "uso: $0 <desde AAAA-MM-DD> [hasta AAAA-MM-DD] [max]" >&2
  exit 2
fi

AWS_PROFILE="${AWS_PROFILE:-takab-dev}"
# `TF_DEV` como en el Makefile: un worktree nuevo no tiene terraform inicializado, y
# desde él `terraform output` muere con «Backend initialization required».
TF_DIR="${TF_DEV:-$(cd "$(dirname "$0")/../terraform/envs/dev" && pwd)}"
AWS_REGION="${AWS_REGION:-$(terraform -chdir="$TF_DIR" output -raw region 2>/dev/null || echo us-east-2)}"
INSTANCE_ID="$(terraform -chdir="$TF_DIR" output -raw db_instance_id)"
COMPOSE="/opt/takab/cloud/docker-compose.yml"
ENTORNO="/etc/takab/deploy.env"

REMOTO="$(printf 'docker compose -f %q --env-file %q exec -T incident-engine python -m takab_api.shakemap.rellena --desde %q' \
  "$COMPOSE" "$ENTORNO" "$DESDE")"
[ -n "$HASTA" ] && REMOTO+=" $(printf -- '--hasta %q' "$HASTA")"
[ -n "$MAX" ] && REMOTO+=" $(printf -- '--max %q' "$MAX")"

echo "→ rellenando mapas desde ${DESDE}${HASTA:+ hasta $HASTA} en ${INSTANCE_ID}"
PARAMS="$(mktemp)"
trap 'rm -f "$PARAMS"' EXIT
python3 -c 'import json,sys; print(json.dumps({"commands": [sys.stdin.read()], "executionTimeout": ["3600"]}))' \
  <<<"$REMOTO" >"$PARAMS"

CMD_ID="$(aws ssm send-command \
  --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "takab rellena mapas ${DESDE}" \
  --parameters "file://$PARAMS" \
  --query Command.CommandId --output text)"

until aws ssm get-command-invocation --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" --query Status --output text 2>/dev/null |
  grep -qE '^(Success|Failed|Cancelled|TimedOut)$'; do
  sleep 5
done

aws ssm get-command-invocation --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
  --query '{estado:Status,salida:StandardOutputContent,error:StandardErrorContent}' \
  --output text | sed '/^$/d;s/^/  /'

ESTADO="$(aws ssm get-command-invocation --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" --query Status --output text)"
if [ "$ESTADO" != Success ]; then
  echo "✗ el relleno no terminó bien (SSM: ${ESTADO})" >&2
  exit 1
fi
echo "✓ relleno terminado"
