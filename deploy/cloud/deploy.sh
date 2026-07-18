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
# Audience = pool principal compartido por el cliente WEB y el MÓVIL táctico:
# coma-separado ⇒ la API acepta el `aud` de cualquiera (tokens.py:_parse_aud).
TAKAB_API_AUTH_AUDIENCE=$(tf client_id),$(tf mobile_tactical_client_id)
TAKAB_API_AUTH_JWKS_URL=$(tf issuer)/.well-known/jwks.json
TAKAB_API_QUEUE_URL_EVENTS=$(terraform -chdir="$TF_DEV" output -json queue_urls | python3 -c 'import json,sys;print(json.load(sys.stdin)["events"])')
TAKAB_API_QUEUE_URL_TELEMETRY=$(terraform -chdir="$TF_DEV" output -json queue_urls | python3 -c 'import json,sys;print(json.load(sys.stdin)["telemetry"])')
TAKAB_API_QUEUE_URL_BACKFILL=$(terraform -chdir="$TF_DEV" output -json queue_urls | python3 -c 'import json,sys;print(json.load(sys.stdin)["backfill"])')
# GAP-1 (T-1.38): los consumidores EXIGEN las URLs de DLQ al arrancar (SystemExit).
TAKAB_API_DLQ_URL_EVENTS=$(terraform -chdir="$TF_DEV" output -json dlq_urls | python3 -c 'import json,sys;print(json.load(sys.stdin)["events"])')
TAKAB_API_DLQ_URL_TELEMETRY=$(terraform -chdir="$TF_DEV" output -json dlq_urls | python3 -c 'import json,sys;print(json.load(sys.stdin)["telemetry"])')
TAKAB_API_DLQ_URL_BACKFILL=$(terraform -chdir="$TF_DEV" output -json dlq_urls | python3 -c 'import json,sys;print(json.load(sys.stdin)["backfill"])')
# T-1.38: la clave HMAC de comandos se resuelve POR GABINETE en runtime; esto es
# solo el prefijo del secreto (no es secreto en sí).
TAKAB_API_COMMAND_HMAC_SECRET_PREFIX=$(tf command_hmac_secret_prefix)
TAKAB_API_EVIDENCE_BUCKET=$(tf evidence_bucket)
TAKAB_API_TRANSFER_BUCKET=$(tf transfer_bucket)
# T-1.61: sin email_from el provider de email es SIMULADO (no envía). Remitente =
# identidad SES verificada (sandbox: variables.tf ses_verified_emails); el link
# del correo al inspector apunta a la consola publicada.
TAKAB_API_NOTIFY_EMAIL_FROM=mauriciobaujim@gmail.com
TAKAB_API_NOTIFY_WEB_BASE_URL=$(tf console_url)
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
echo '$(b64 db/seeds/prod_fleet.sql)'           | base64 -d > /opt/takab/cloud/prod_fleet.sql
echo '$(b64 db/seeds/reference_earthquakes.sql)'| base64 -d > /opt/takab/cloud/reference_earthquakes.sql
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

systemctl daemon-reload
systemctl enable --now takab-secrets.service

aws ecr get-login-password --region ${AWS_REGION} \
  | docker login --username AWS --password-stdin ${REGISTRY}

# Privilegios que la 0011 necesita y que takab_migrator NO PUEDE darse a sí mismo.
# Van por el socket local como postgres — el mismo canal de superusuario que ya
# usan los seeds. Los dos son idempotentes.
#
# La 0011 cede la propiedad de la función SECURITY DEFINER
# \`relocate_incident_epicenter\` a takab_ingest, para que un operador de consola
# pueda reubicar un epicentro SIN tener permiso de escritura directo sobre
# seismic_events. Para ceder una propiedad, Postgres exige DOS cosas:
#
#   1. Ser MIEMBRO del rol destino (poder hacerle SET ROLE). takab_migrator no lo
#      era ⇒ "must be able to SET ROLE takab_ingest".
#   2. Que el NUEVO DUEÑO tenga CREATE en el esquema del objeto. takab_ingest no lo
#      tenía ⇒ "permission denied for schema public".
#
# Por eso la Fase 1.7 nunca llegó a la nube: el despliegue abortaba aquí y la base
# se quedaba en 0010. En local no se veía porque allí alembic conecta como el
# superusuario de la base y puede ceder lo que quiera — la divergencia clásica que
# solo aparece contra el modelo de roles real.
#
# El CREATE es una necesidad de la MIGRACIÓN, no del runtime: se concede para esta
# ventana y se revoca justo después (el ingestor no crea objetos en producción).
docker exec -i takab-db psql -U postgres -d takab -v ON_ERROR_STOP=1 \\
  -c "GRANT takab_ingest TO takab_migrator;" \\
  -c "GRANT CREATE ON SCHEMA public TO takab_ingest;" >/dev/null

# Migraciones ANTES de levantar la API: un esquema viejo con código nuevo es un 500
# en cada request. Corre como takab_migrator (dueño del DDL), no como takab_app.
#
# \`--workdir /takab/api\` NO es cosmético: alembic.ini declara \`script_location =
# migrations\`, que Alembic resuelve contra el CWD (no contra el .ini). Desde /takab
# buscaría /takab/migrations y no encontraría nada.
#
# El rc se captura en vez de dejar que \`set -e\` aborte: el REVOKE de abajo tiene
# que cerrarse SIEMPRE, también si la migración falla. El fallo se propaga después.
MIGRATION_RC=0
docker run --rm --network host --workdir /takab/api \\
  --env-file /run/takab/db-migrator.env \\
  --entrypoint python ${REGISTRY}/takab/cloud:${CLOUD_TAG} -m alembic upgrade head \\
  || MIGRATION_RC=\$?

# Cerrar la ventana: el ingestor vuelve a no poder crear objetos en public.
docker exec -i takab-db psql -U postgres -d takab -v ON_ERROR_STOP=1 \\
  -c "REVOKE CREATE ON SCHEMA public FROM takab_ingest;" >/dev/null

if [ "\$MIGRATION_RC" -ne 0 ]; then
  echo "alembic upgrade head FALLÓ (rc=\$MIGRATION_RC) — la API no se toca" >&2
  exit "\$MIGRATION_RC"
fi

# Flota en la DB de la nube (GAP-3 · T-1.38): sin filas en gateways/sensors la
# ingesta rechaza TODO por "unknown principal" → DLQ. El seed es idempotente
# (UUIDs fijos + ON CONFLICT DO NOTHING) y corre como superusuario POR SOCKET
# LOCAL del contenedor de la DB (auth trust interna): cero secretos
# materializados para este paso, y el superusuario ignora RLS FORCE.
# T-1.47: SOLO la flota real — la sim (db/seeds/sim_fleet.sql) es de entornos
# locales y aplicarla aquí desharía la purga de datos sim de la nube.
docker exec -i takab-db psql -U postgres -d takab -v ON_ERROR_STOP=1 \\
  </opt/takab/cloud/prod_fleet.sql >/dev/null
# Catálogo de referencia SSN/USGS (T-1.48; global, idempotente).
docker exec -i takab-db psql -U postgres -d takab -v ON_ERROR_STOP=1 \\
  </opt/takab/cloud/reference_earthquakes.sql >/dev/null

# Workers ad-hoc del smoke del 2026-07-08 (imagen takab-cloud:t125, lanzados a
# mano por SSM, sin systemd): fuera. El stack compose los sustituye; dejarlos
# vivos serían dos consumidores con CÓDIGO DISTINTO peleando por las mismas
# colas — descubierto en D0 de T-1.39 (las colas "vacías" eran ellos drenando).
docker rm -f takab-worker-events takab-worker-telemetry takab-worker-backfill 2>/dev/null || true

systemctl enable takab-cloud.service
systemctl restart takab-cloud.service
sleep 5
docker compose -f /opt/takab/cloud/docker-compose.yml --env-file /etc/takab/deploy.env ps
EOF
)

echo "→ desplegando ${CLOUD_TAG} a ${INSTANCE_ID} (${PUBLIC_HOST})"

# Los parámetros van como JSON COMPLETO vía file:// — el shorthand
# `commands="[...]"` del CLI NO decodifica los \n del JSON y el script llegaba
# al EC2 como UNA línea con \n literales (syntax error en la primera línea).
# Descubierto en el primer deploy real de T-1.39.
PARAMS_FILE="$(mktemp)"
trap 'rm -f "$PARAMS_FILE"' EXIT
python3 -c 'import json,sys; print(json.dumps({"commands": [sys.stdin.read()]}))' \
  <<<"$REMOTE_SCRIPT" >"$PARAMS_FILE"

CMD_ID=$(aws ssm send-command \
  --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "takab cloud deploy ${CLOUD_TAG}" \
  --parameters "file://$PARAMS_FILE" \
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
