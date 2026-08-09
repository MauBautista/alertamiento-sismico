#!/bin/bash
# Materializa los secretos de Secrets Manager a tmpfs (T-1.37).
#
# Regla de oro 6: ningún secreto en git, ninguno en disco. `/run` es tmpfs en AL2023,
# así que estos archivos mueren al apagar la máquina. Corre como oneshot ANTES de
# docker-compose (ver takab-secrets.service).
#
# Sin `set -x`: volcaría las contraseñas a journalctl.
set -euo pipefail

REGION="${AWS_REGION:-us-east-2}"
RUN_DIR=/run/takab

install -d -m 0700 "$RUN_DIR"

secret_json() {
  aws secretsmanager get-secret-value \
    --secret-id "$1" --region "$REGION" \
    --query SecretString --output text
}

field() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)["'"$1"'"])'
}

write_env() {
  # umask 077 antes del redirect: el archivo nace 0600, no 0644.
  local path="$1"
  shift
  (
    umask 077
    printf '%s\n' "$@" >"$path"
  )
}

# --- DSN de la API: rol takab_app, con RLS FORZADA ------------------------------
# La API NUNCA usa takab_ingest. Ese rol tiene BYPASSRLS y serviría filas de todos
# los tenants a cualquier operador autenticado (regla de oro 5).
APP_PASS="$(secret_json takab/dev/db/app | field password)"
write_env "$RUN_DIR/db-app.env" \
  "TAKAB_API_DATABASE_URL=postgresql+psycopg://takab_app:${APP_PASS}@127.0.0.1:5432/takab"

# --- DSN de los workers: rol takab_ingest, BYPASSRLS ----------------------------
# Los consumidores escriben filas de todos los tenants (la ingesta no tiene sesión
# de usuario), así que necesitan saltarse RLS. Nunca sirven HTTP.
INGEST_PASS="$(secret_json takab/dev/db/ingest | field password)"
write_env "$RUN_DIR/db-ingest.env" \
  "TAKAB_API_DATABASE_URL=postgresql+psycopg://takab_ingest:${INGEST_PASS}@127.0.0.1:5432/takab" \
  "DATABASE_URL=postgresql://takab_ingest:${INGEST_PASS}@127.0.0.1:5432/takab"

# --- Clave HMAC de comandos: YA NO se materializa aquí (T-1.38) -----------------
# La API y el worker de comandos resuelven la clave POR GABINETE en runtime contra
# Secrets Manager ("{prefix}/{iot_thing}", rol de instancia, cache TTL). El prefijo
# no es secreto y viaja en /etc/takab/cloud.env. Ventaja extra: una rotación se ve
# en ≤300 s sin reiniciar este oneshot.

# --- Migraciones -----------------------------------------------------------------
# Alembic lee la env BARE `DATABASE_URL` y corre como takab_migrator (dueño del DDL).
MIGRATOR_PASS="$(secret_json takab/dev/db/migrator | field password)"
write_env "$RUN_DIR/db-migrator.env" \
  "DATABASE_URL=postgresql+psycopg://takab_migrator:${MIGRATOR_PASS}@127.0.0.1:5432/takab"
