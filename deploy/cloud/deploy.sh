#!/bin/bash
# Despliega la nube co-locada al EC2 por SSM (T-1.37). Idempotente.
#
# La instancia no tiene ingreso SSH: todo va por `aws ssm send-command`. Los artefactos
# (compose, unidades systemd, script de secretos) se transfieren en base64 dentro del
# propio comando — son kilobytes y así no hace falta un bucket intermedio.
#
# Lo que este script NO hace, a propósito:
#  - `terraform apply`. Cambiar `instance_type` PARA la instancia: la DB cae unos
#    minutos y el gabinete acumula spool. Es una decisión humana.
#  - Escribir secretos. Los materializa `takab-secrets.service` desde Secrets Manager
#    a tmpfs, en el arranque. Aquí no viaja ni una contraseña (regla de oro 6).
set -euo pipefail

: "${AWS_PROFILE:?}" "${AWS_REGION:?}" "${TF_DEV:?}" "${CLOUD_TAG:?}"

tf() { terraform -chdir="$TF_DEV" output -raw "$1"; }

ACCOUNT="$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)"
REGISTRY="${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
INSTANCE_ID="$(tf db_instance_id)"
PUBLIC_HOST="$(tf console_public_host)"
ACME_EMAIL="$(tf acme_email)"
HMAC_GATEWAY="$(tf command_hmac_gateway)"

if [ -z "$PUBLIC_HOST" ]; then
  echo "ERROR: la consola no está publicada. Aplica con -var serve_enabled=true" >&2
  echo "       y -var 'web_allowed_cidrs=[\"TU.IP.PU.BL/32\"]' antes de desplegar." >&2
  exit 1
fi

# Configuración NO secreta. Los secretos jamás pasan por aquí.
CLOUD_ENV=$(
  cat <<EOF
TAKAB_API_AWS_REGION=${AWS_REGION}
TAKAB_API_AUTH_ISSUER=$(tf issuer)
TAKAB_API_AUTH_AUDIENCE=$(tf client_id)
TAKAB_API_AUTH_JWKS_URL=$(tf issuer)/.well-known/jwks.json
TAKAB_API_QUEUE_URL_EVENTS=$(terraform -chdir="$TF_DEV" output -json queue_urls | python3 -c 'import json,sys;print(json.load(sys.stdin)["events"])')
TAKAB_API_QUEUE_URL_TELEMETRY=$(terraform -chdir="$TF_DEV" output -json queue_urls | python3 -c 'import json,sys;print(json.load(sys.stdin)["telemetry"])')
TAKAB_API_QUEUE_URL_BACKFILL=$(terraform -chdir="$TF_DEV" output -json queue_urls | python3 -c 'import json,sys;print(json.load(sys.stdin)["backfill"])')
TAKAB_API_EVIDENCE_BUCKET=$(tf evidence_bucket)
TAKAB_API_TRANSFER_BUCKET=$(tf transfer_bucket)
EOF
)

# `/dev/token` NO se monta: TAKAB_API_AUTH_JWKS_JSON queda ausente a propósito
# (main.create_app condiciona el router a ese valor). La nube solo acepta Cognito.

DEPLOY_ENV=$(
  cat <<EOF
TAKAB_CLOUD_IMAGE=${REGISTRY}/takab/cloud:${CLOUD_TAG}
TAKAB_CONSOLE_IMAGE=${REGISTRY}/takab/console:${CLOUD_TAG}
TAKAB_PUBLIC_HOST=${PUBLIC_HOST}
TAKAB_ACME_EMAIL=${ACME_EMAIL}
EOF
)

b64() { base64 -w0 "$1"; }

COMPOSE_VERSION="v2.32.4"

REMOTE_SCRIPT=$(
  cat <<EOF
set -euo pipefail
install -d -m 0755 /opt/takab/cloud /etc/takab

# AL2023 trae \`docker\` pero NO el plugin \`compose\` (no está en dnf). El user_data
# original solo necesitaba \`docker run\` para la DB; la topología co-locada sí lo usa.
if ! docker compose version >/dev/null 2>&1; then
  install -d -m 0755 /usr/libexec/docker/cli-plugins
  curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-aarch64" \\
    -o /usr/libexec/docker/cli-plugins/docker-compose
  chmod 0755 /usr/libexec/docker/cli-plugins/docker-compose
fi
docker compose version

echo '$(b64 deploy/cloud/docker-compose.yml)'   | base64 -d > /opt/takab/cloud/docker-compose.yml
echo '$(b64 deploy/cloud/takab-secrets.sh)'     | base64 -d > /opt/takab/cloud/takab-secrets.sh
echo '$(b64 deploy/cloud/takab-secrets.service)'| base64 -d > /etc/systemd/system/takab-secrets.service
echo '$(b64 deploy/cloud/takab-cloud.service)'  | base64 -d > /etc/systemd/system/takab-cloud.service
chmod 0755 /opt/takab/cloud/takab-secrets.sh

umask 077
cat > /etc/takab/cloud.env <<'CLOUDENV'
${CLOUD_ENV}
CLOUDENV
cat > /etc/takab/deploy.env <<'DEPLOYENV'
${DEPLOY_ENV}
DEPLOYENV
umask 022

sed -i "s|^Environment=AWS_REGION=.*|Environment=AWS_REGION=${AWS_REGION}|" /etc/systemd/system/takab-secrets.service
grep -q TAKAB_HMAC_GATEWAY /etc/systemd/system/takab-secrets.service \
  || sed -i "/^Environment=AWS_REGION=/a Environment=TAKAB_HMAC_GATEWAY=${HMAC_GATEWAY}" /etc/systemd/system/takab-secrets.service

systemctl daemon-reload
systemctl enable --now takab-secrets.service

aws ecr get-login-password --region ${AWS_REGION} \
  | docker login --username AWS --password-stdin ${REGISTRY}

# Migraciones ANTES de levantar la API: un esquema viejo con código nuevo es un 500
# en cada request. Corre como takab_migrator (dueño del DDL), no como takab_app.
#
# \`--workdir /takab/api\` NO es cosmético: alembic.ini declara \`script_location =
# migrations\`, que Alembic resuelve contra el CWD (no contra el .ini). Desde /takab
# buscaría /takab/migrations y no encontraría nada.
docker run --rm --network host --workdir /takab/api \\
  --env-file /run/takab/db-migrator.env \\
  --entrypoint python ${REGISTRY}/takab/cloud:${CLOUD_TAG} -m alembic upgrade head

systemctl enable takab-cloud.service
systemctl restart takab-cloud.service
sleep 5
docker compose -f /opt/takab/cloud/docker-compose.yml --env-file /etc/takab/deploy.env ps
EOF
)

echo "→ desplegando ${CLOUD_TAG} a ${INSTANCE_ID} (${PUBLIC_HOST})"

CMD_ID=$(aws ssm send-command \
  --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "takab cloud deploy ${CLOUD_TAG}" \
  --parameters commands="$(python3 -c 'import json,sys;print(json.dumps([sys.stdin.read()]))' <<<"$REMOTE_SCRIPT")" \
  --query Command.CommandId --output text)

echo "→ comando SSM ${CMD_ID}; esperando…"
until aws ssm get-command-invocation --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" --query Status --output text 2>/dev/null \
  | grep -qE '^(Success|Failed|Cancelled|TimedOut)$'; do
  sleep 5
done

aws ssm get-command-invocation --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
  --query '{estado:Status,salida:StandardOutputContent,error:StandardErrorContent}' --output text

STATUS=$(aws ssm get-command-invocation --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" --query Status --output text)
[ "$STATUS" = "Success" ] || { echo "despliegue FALLIDO ($STATUS)" >&2; exit 1; }

echo "✓ consola en https://${PUBLIC_HOST}"
