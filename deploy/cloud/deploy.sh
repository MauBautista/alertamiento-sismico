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
# Commit desplegado: CLOUD_TAG ya es \`git rev-parse --short HEAD\`. Se expone en
# GET /health para poder responder "que esta vivo" sin abrir una sesion SSM.
#
# [T-2.153] Y al final el script se lo pregunta a la API: que conteste, que corra
# EL COMMIT recien desplegado y que su esquema este AL DIA. Sin eso, un
# 'docker compose ps' en verde con la imagen anterior tiene el mismo aspecto
# que un despliegue bueno.
TAKAB_API_BUILD_SHA=${CLOUD_TAG}
# [T-2.60.a] El worker \`notify\` publica GhostGatewaysAlive a CloudWatch cada
# 60 s (gabinetes retirados que siguen reportando). APAGADO por defecto en el
# codigo — en local no hay CloudWatch —, se enciende SOLO aqui. Exige el permiso
# PutOpsMetrics del rol de instancia (modules/database): sin el, el worker
# registra el fallo y sigue notificando, pero la alarma se queda ciega.
TAKAB_API_OPS_METRICS_ENABLED=true
# [T-2.78.a] Topic de on-call. NO es un secreto (identificador publico de AWS) y
# NO es opcional: de este ARN salen la region del unico host al que el suscriptor
# de SNS tiene permitido salir y la comparacion que descarta un sobre firmado que
# venga de otro topic. Sin esta linea, POST /api/ops/alerts/sns responde 503 y lo
# grita en el log — y la suscripcion HTTPS de Terraform no se puede confirmar.
TAKAB_API_OPS_ALERT_TOPIC_ARN=$(tf ops_topic_arn)
# [T-2.162] El MISMO plazo que anuncia el correo de la alarma. Se DERIVA del
# terraform, no se teclea: si divergieran, el aviso prometeria un plazo que la API
# no respeta y nadie lo notaria hasta que alguien acusara "a tiempo" y el sistema
# le dijera que llego tarde.
TAKAB_API_OPS_ACK_DEADLINE_S=$(tf ops_ack_deadline_s)
TAKAB_API_AUTH_ISSUER=$(tf issuer)
# Audience = pool principal compartido por el cliente WEB y el MOVIL tactico:
# coma-separado, la API acepta el aud de cualquiera (tokens.py _parse_aud).
TAKAB_API_AUTH_AUDIENCE=$(tf client_id),$(tf mobile_tactical_client_id)
TAKAB_API_AUTH_JWKS_URL=$(tf issuer)/.well-known/jwks.json
# [T-2.99] Pool de OCUPANTES (decision #7, T-2.02): SEGUNDO issuer verificable.
# Sin estas tres lineas auth_occupants_issuer queda vacio, decode_verify_any no
# llega a mirar este pool y el id_token de cualquier ocupante muere con
# "invalid token" = 401 en /me. Estuvo asi desde el primer despliegue de la app:
# el pool existia en Terraform y la app lo apuntaba, pero la API no lo conocia.
# El ancla pool->rol (auth/deps.py) exige AMBOS pools configurados para poder
# rechazar el cruce; con uno solo, el rechazo es un accidente y no una guarda.
#
# SIN BACKTICKS, y no es estilo: este heredoc va sin comillas, asi que un
# backtick aqui es SUSTITUCION DE ORDENES y el despliegue intenta EJECUTAR lo
# que hay dentro. Pasó: tres "orden no encontrada" en el deploy del 2026-08-09.
TAKAB_API_AUTH_OCCUPANTS_ISSUER=$(tf occupants_issuer)
TAKAB_API_AUTH_OCCUPANTS_AUDIENCE=$(tf occupants_client_id)
TAKAB_API_AUTH_OCCUPANTS_JWKS_URL=$(tf occupants_issuer)/.well-known/jwks.json
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
# identidad SES verificada; el link del correo al inspector apunta a la consola
# publicada.
#
# [T-2.78.b, D-12] Remitente de DOMINIO desde 2026-08-21. El orden importa y ya
# esta cumplido, pero conviene saberlo si alguien lo vuelve a tocar: el statement
# WorkerSesSend del rol de la instancia acota Resource a los ARN de identidad
# concretos, asi que cambiar ESTA linea sin que el ARN del dominio este en el rol
# da AccessDenied en cada envio — y los correos de CloudWatch seguirian llegando
# tan campantes, porque esos son SNS y llevan permiso propio. Es el fallo del
# 2026-07-14 otra vez. Orden: identidad verificada -> ARN en el rol (ses_domain en
# tfvars lo mete solo) -> esta linea -> envio real comprobado.
#
# SIN BACKTICKS Y A PROPOSITO: esto vive dentro del heredoc SIN comillas que abre
# la linea 33, asi que un backtick aqui no es tipografia — el despliegue EJECUTA
# en la maquina lo que haya entre ellos. Lo caza
# test_ningun_heredoc_del_despliegue_ejecuta_lo_que_creia_comentar.
TAKAB_API_NOTIFY_EMAIL_FROM=alertas@takabailert.com
TAKAB_API_NOTIFY_WEB_BASE_URL=$(tf console_url)
# [T-2.158, D-22] Y que el DESTINATARIO la alcanza, que no es lo mismo. Tener URL
# no basta: hasta D-22 ese 443 admitia UNA sola IP, asi que el enlace de "Atender
# en la consola" solo lo abria el operador de esa direccion. El proceso no puede
# deducirlo —lo sabe la red—, por eso se declara. Sin esta linea el correo NO
# promete enlace: dice que hacer y se calla la URL, que es el default seguro.
#
# Si algun dia se vuelve a cerrar el 443, ESTA LINEA se apaga con el.
TAKAB_API_NOTIFY_WEB_PUBLIC=$(tf console_is_public)
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

# [T-2.153] EL GATE QUE FALTABA: hasta aquí este script levantaba contenedores y
# declaraba ✓ sin preguntarle NADA a la API. Es la misma familia de defecto que
# 'systemctl is-active' haciéndose pasar por canary — «arrancó» no es «sirve», y
# «migró» no es «la API ve el esquema que su imagen espera».
#
# Se comprueban TRES hechos, y el tercero es el que muerde en silencio:
#   1. la API contesta (si no, todo lo demás es adivinar);
#   2. corre EL COMMIT QUE ACABAMOS DE DESPLEGAR — un 'docker compose ps' en
#      verde con la imagen anterior tiene exactamente el mismo aspecto;
#   3. el esquema está AL DÍA respecto de las migraciones que esa imagen trae.
#
# El 3 es la razón de existir de esta ficha. El 2026-08-21 la nube corría
# 0038 con el repo en 0046 —OCHO migraciones— y no lo dijo ni una alarma, ni
# un health-check ni un test: se descubrió por un síntoma lateral (una alarma de
# retención atascada) tras media hora persiguiendo el script equivocado.
# La API se consulta DIRECTA en el 8000, saltándose a Caddy — que es quien monta
# el prefijo /api con handle_path y lo QUITA antes de reenviar. Por eso aquí
# la ruta es /health y no /api/health: FastAPI sirve sus rutas tal cual. Pedir
# /api/health al 8000 devuelve 404, y este gate habría puesto en rojo TODOS los
# despliegues esperando 60 s a una ruta que no existe. Lo ancla
# test_el_gate_pregunta_por_una_ruta_que_la_app_SIRVE_de_verdad.
echo "→ verificando la API recién desplegada"
SALUD=""
for _ in \$(seq 1 30); do
  SALUD="\$(curl -fsS --max-time 5 http://127.0.0.1:8000/health 2>/dev/null || true)"
  [ -n "\$SALUD" ] && break
  sleep 2
done
if [ -z "\$SALUD" ]; then
  echo "✗ la API no contesta en /api/health tras 60 s — el despliegue NO se declara bueno" >&2
  docker compose -f /opt/takab/cloud/docker-compose.yml --env-file /etc/takab/deploy.env \
    logs --tail 40 api >&2 || true
  exit 1
fi
echo "\$SALUD" | python3 -c '
import json, sys

salud = json.load(sys.stdin)
esperado = sys.argv[1]
esquema = salud.get("esquema") or {}
build = salud.get("build")
estado = esquema.get("estado")
aplicada = esquema.get("aplicada")
esperada_rev = esquema.get("esperada")
pendientes = esquema.get("pendientes")

problemas = []
if build != esperado:
    problemas.append(
        "la API corre el build " + repr(build) + " y se desplegó " + repr(esperado)
        + ": los contenedores arrancaron con la imagen ANTERIOR"
    )
if estado != "al_dia":
    problemas.append(
        "el esquema NO está al día: " + repr(estado)
        + " (aplicada=" + repr(aplicada) + ", esperada=" + repr(esperada_rev)
        + ", pendientes=" + repr(pendientes) + ")"
    )

if problemas:
    print("✗ DESPLIEGUE NO VERIFICADO:", file=sys.stderr)
    for p in problemas:
        print("  · " + p, file=sys.stderr)
    raise SystemExit(1)

print("✓ API viva en " + repr(build) + ", esquema al día (" + repr(aplicada) + ")")
' "${CLOUD_TAG}"
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
