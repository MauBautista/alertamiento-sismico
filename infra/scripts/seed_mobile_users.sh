#!/usr/bin/env bash
# Alta de los usuarios MÓVILES de prueba (occupant + brigadista).
#
# Por qué existe: `seed_console_users.sh` NO sirve para la app. Hardcodea
# `custom:surface=web` y sus 6 roles son de consola; claims.py valida
# surface ∈ {web,mobile,both} y la matriz RBAC móvil vive en otros roles.
#
# DOS POOLS, y el cruce es 401 en AMBAS direcciones (ancla pool→rol en
# auth/deps.py; specs/cognito-pool-v1.md §5.2):
#   occupant   → pool de OCUPANTES (mfa OPTIONAL) — entra con email+password.
#   brigadista → pool PRINCIPAL   (mfa ON)        — enrola TOTP en el 1er login.
# Sembrar un occupant en el pool principal (o al revés) produce un usuario que
# NUNCA podrá entrar: es el error que este script existe para evitar.
#
# EL OCCUPANT NO LLEVA `site_scope` — y no es un olvido: R2 (ratificada T-2.00)
# lo deja default-deny en el claim y resuelve su alcance server-side contra
# `user_zone_assignments`. Por eso NO basta con crearlo en Cognito: sin fila de
# asignación, `assert_site_access` responde 404 y la app se queda en onboarding.
# Esa fila la crea el propio ocupante al consumir un CÓDIGO de enrolamiento
# (`POST /me/enrollment`) — el paso 2 de este script lo siembra.
#
# Por qué el código se inserta por SQL y no por la API: `POST /sites/{id}/
# enrollment-codes` exige un rol con `enrollment_manage` (superadmin/
# tenant_admin/building_admin), todos en el pool con MFA=ON ⇒ no automatizable
# sin authenticator. Y la consola web todavía no tiene pantalla para ello.
#
# Uso:  AWS_PROFILE=takab-dev infra/scripts/seed_mobile_users.sh [rol ...]
#       (sin args: occupant brigadista)
#       --skip-db  → solo Cognito, sin túnel ni código de enrolamiento.
set -euo pipefail

TF_DIR="$(cd "$(dirname "$0")/../terraform/envs/dev" && pwd)"
SECRET_ID="takab/dev/mobile/users"

# Tenant y sitio del seed de flota real (db/seeds/prod_fleet.sql). Sin estos el
# token entra pero la app no ve nada (RLS + R2 no encuentran sitio).
TENANT_ID="${TENANT_ID:-d0000000-0000-0000-0000-000000000001}"
SITE_ID="${SITE_ID:-d1000000-0000-0000-0000-000000000000}"

# Zona del enrolamiento. NO es cosmética: la máquina de crisis deriva el takeover
# de `zones.evac_policy` (spec móvil §4.1 · R1) — con zona NULL la app declara
# "sin política" y el flujo de crisis no se puede probar de punta a punta.
ZONE_ID="${ZONE_ID:-d2000000-0000-0000-0000-000000000001}"
ZONE_NAME="${ZONE_NAME:-PB-A}"
ZONE_LEVEL="${ZONE_LEVEL:-PB}"
ZONE_POLICY="${ZONE_POLICY:-evacuate}" # CHECK de DB: evacuate | shelter

SITE_CODE="${SITE_CODE:-DEV-OCUPANTE}"
CODE_MAX_USES="${CODE_MAX_USES:-100}"
CODE_TTL_DAYS="${CODE_TTL_DAYS:-90}"
DB_LOCAL_PORT="${DB_LOCAL_PORT:-5435}" # 5435 y no 5434: no choca con `make db-tunnel`

SKIP_DB=0
ARGS=()
for a in "$@"; do
  case "$a" in
  --skip-db) SKIP_DB=1 ;;
  *) ARGS+=("$a") ;;
  esac
done
DEFAULT_ROLES=(occupant brigadista)
ROLES=("${ARGS[@]:-${DEFAULT_ROLES[@]}}")

for ROLE in "${ROLES[@]}"; do
  case "$ROLE" in
  occupant | brigadista | security_guard) ;;
  *)
    echo "rol no móvil: $ROLE (usa occupant|brigadista|security_guard)" >&2
    exit 2
    ;;
  esac
done

REGION="$(terraform -chdir="$TF_DIR" output -raw region 2>/dev/null || echo us-east-2)"
MAIN_POOL="$(terraform -chdir="$TF_DIR" output -raw user_pool_id)"
OCC_POOL="$(terraform -chdir="$TF_DIR" output -raw occupants_user_pool_id)"
BASE_EMAIL="$(terraform -chdir="$TF_DIR" output -raw budget_email 2>/dev/null || echo mauriciobaujim@gmail.com)"
LOCAL_PART="${BASE_EMAIL%@*}"
DOMAIN="${BASE_EMAIL#*@}"

echo "pool principal = $MAIN_POOL   pool ocupantes = $OCC_POOL   region = $REGION"
echo "tenant = $TENANT_ID   sitio = $SITE_ID"
echo "roles: ${ROLES[*]}"
echo

CREDS="{}"
for ROLE in "${ROLES[@]}"; do
  # Plus-addressing: mismo buzón real, identidad Cognito distinta. `+occupant`
  # vive en OTRO pool que `+brigadista`, así que no colisionan entre sí ni con
  # los de consola (que no siembran roles móviles).
  EMAIL="${LOCAL_PART}+${ROLE}@${DOMAIN}"
  # Política de ambos pools: ≥12, mayúscula, minúscula y dígito (símbolos no).
  PASS="Takab$(openssl rand -hex 6)Aa1"

  if [[ "$ROLE" == occupant ]]; then
    POOL="$OCC_POOL"
  else
    POOL="$MAIN_POOL"
  fi

  ATTRS=(
    Name=email,Value="$EMAIL"
    Name=email_verified,Value=true
    Name=custom:tenant_id,Value="$TENANT_ID"
    Name=custom:role,Value="$ROLE"
    Name=custom:surface,Value=mobile
  )
  # R2: el occupant NO lleva site_scope (default-deny; su alcance sale de
  # user_zone_assignments). El resto SÍ lo necesita — vacío = no ve nada.
  [[ "$ROLE" != occupant ]] && ATTRS+=(Name=custom:site_scope,Value="$SITE_ID")

  aws cognito-idp admin-create-user \
    --user-pool-id "$POOL" --region "$REGION" \
    --username "$EMAIL" \
    --message-action SUPPRESS \
    --user-attributes "${ATTRS[@]}" \
    >/dev/null 2>&1 || echo "  (ya existía: $EMAIL — se actualizan atributos)"

  # Re-aplicar hace el script idempotente (un rol/scope cambiado se corrige).
  aws cognito-idp admin-update-user-attributes \
    --user-pool-id "$POOL" --region "$REGION" \
    --username "$EMAIL" --user-attributes "${ATTRS[@]}" >/dev/null

  # EL PASO QUE SE OLVIDA: sin el grupo, claims.py corta con "role not in
  # groups" (401) aunque custom:role sea correcto.
  aws cognito-idp admin-add-user-to-group \
    --user-pool-id "$POOL" --region "$REGION" \
    --username "$EMAIL" --group-name "$ROLE" >/dev/null

  # Permanente: sin esto el 1er login cae en FORCE_CHANGE_PASSWORD.
  aws cognito-idp admin-set-user-password \
    --user-pool-id "$POOL" --region "$REGION" \
    --username "$EMAIL" --password "$PASS" --permanent >/dev/null

  CREDS="$(jq -c --arg u "$EMAIL" --arg p "$PASS" --arg r "$ROLE" \
    '. + {($r): {username: $u, password: $p}}' <<<"$CREDS")"
  echo "  ✓ $ROLE  →  $EMAIL"
done

# --- Paso 2: zona + código de enrolamiento (solo si hay occupant) --------------

need_code=0
for ROLE in "${ROLES[@]}"; do [[ "$ROLE" == occupant ]] && need_code=1; done

if [[ "$need_code" == 1 && "$SKIP_DB" == 0 ]]; then
  echo
  echo "Sembrando zona + código de enrolamiento (túnel SSM → puerto $DB_LOCAL_PORT)…"

  DB_ID="$(terraform -chdir="$TF_DIR" output -raw db_instance_id)"
  DB_IP="$(terraform -chdir="$TF_DIR" output -raw db_private_ip)"
  DB_SECRET="$(aws secretsmanager get-secret-value --secret-id takab/dev/db/superuser \
    --region "$REGION" --query SecretString --output text)"
  DB_USER="$(jq -r .username <<<"$DB_SECRET")"
  DB_PASS="$(jq -r .password <<<"$DB_SECRET")"
  DB_NAME="$(jq -r .dbname <<<"$DB_SECRET")"

  aws ssm start-session --region "$REGION" --target "$DB_ID" \
    --document-name AWS-StartPortForwardingSessionToRemoteHost \
    --parameters "{\"host\":[\"$DB_IP\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"$DB_LOCAL_PORT\"]}" \
    >/dev/null 2>&1 &
  TUNNEL_PID=$!
  # `aws ssm` lanza a session-manager-plugin como HIJO: matar solo al padre deja
  # el plugin vivo con el puerto tomado y la siguiente corrida no abre el túnel.
  _kill_tunnel() {
    pkill -P "$TUNNEL_PID" 2>/dev/null || true
    kill "$TUNNEL_PID" 2>/dev/null || true
  }
  trap _kill_tunnel EXIT

  ready=0
  for _ in $(seq 1 30); do
    if (exec 3<>"/dev/tcp/127.0.0.1/$DB_LOCAL_PORT") 2>/dev/null; then
      exec 3<&-
      ready=1
      break
    fi
    sleep 1
  done
  if [[ "$ready" != 1 ]]; then
    echo "  ✗ el túnel no abrió. ¿La instancia está apagada? → make cloud-start" >&2
    exit 1
  fi

  export PGPASSWORD="$DB_PASS"
  PSQL=(psql -h 127.0.0.1 -p "$DB_LOCAL_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -q)

  # Guard explícito: sin el sitio, la FK falla con un mensaje peor que este.
  if [[ "$("${PSQL[@]}" -tAc "SELECT count(*) FROM sites WHERE site_id = '$SITE_ID'")" != "1" ]]; then
    echo "  ✗ el sitio $SITE_ID no existe en la nube — aplica db/seeds/prod_fleet.sql" >&2
    exit 1
  fi

  # superuser ⇒ RLS no aplica (es un seed administrativo, no tráfico de app).
  "${PSQL[@]}" \
    -v code="$SITE_CODE" -v tenant="$TENANT_ID" -v site="$SITE_ID" -v zone="$ZONE_ID" \
    -v zname="$ZONE_NAME" -v zlevel="$ZONE_LEVEL" -v zpolicy="$ZONE_POLICY" \
    -v maxuses="$CODE_MAX_USES" -v days="$CODE_TTL_DAYS" <<'SQL'
INSERT INTO zones (zone_id, tenant_id, site_id, name, level_code, evac_policy)
VALUES (:'zone'::uuid, :'tenant'::uuid, :'site'::uuid, :'zname', :'zlevel', :'zpolicy')
ON CONFLICT (zone_id) DO UPDATE
  SET name = EXCLUDED.name, level_code = EXCLUDED.level_code,
      evac_policy = EXCLUDED.evac_policy;

-- `grants_role` es 'occupant' por DEFAULT + CHECK: un código nunca otorga otro rol.
-- Re-correr REARMA el código (uses=0, active=true) — un código agotado da 404.
INSERT INTO site_enrollment_codes (code, tenant_id, site_id, zone_id, expires_at, max_uses)
VALUES (:'code', :'tenant'::uuid, :'site'::uuid, :'zone'::uuid,
        now() + (:'days' || ' days')::interval, :maxuses)
ON CONFLICT (code) DO UPDATE
  SET tenant_id = EXCLUDED.tenant_id, site_id = EXCLUDED.site_id,
      zone_id = EXCLUDED.zone_id, expires_at = EXCLUDED.expires_at,
      max_uses = EXCLUDED.max_uses, uses = 0, active = true;
SQL

  _kill_tunnel
  trap - EXIT
  unset PGPASSWORD
  echo "  ✓ zona $ZONE_NAME ($ZONE_POLICY) + código $SITE_CODE (${CODE_MAX_USES} usos, ${CODE_TTL_DAYS}d)"
fi

# --- Entrega ------------------------------------------------------------------

aws secretsmanager put-secret-value --secret-id "$SECRET_ID" --region "$REGION" \
  --secret-string "$CREDS" >/dev/null 2>&1 ||
  aws secretsmanager create-secret --name "$SECRET_ID" --region "$REGION" \
    --description "Usuarios móviles de prueba (occupant/brigadista)" \
    --secret-string "$CREDS" >/dev/null

echo
echo "Credenciales guardadas en Secrets Manager ($SECRET_ID). Se imprimen UNA vez:"
jq -r 'to_entries[] | "  \(.key)\t\(.value.username)\t\(.value.password)"' <<<"$CREDS"
echo
if [[ "$need_code" == 1 ]]; then
  echo "OCUPANTE: entra con email+password (MFA opcional) y en el onboarding"
  echo "  teclea el código de sitio:  $SITE_CODE"
fi
echo "BRIGADISTA: el pool principal exige MFA — el 1er login (Hosted UI/PKCE desde"
echo "  la app) pedirá enrolar TOTP en tu authenticator."
echo
echo "Para los E2E de Maestro, mobile/.maestro/.env (NO commitear):"
jq -r '
  (if .occupant   then "OCCUPANT_EMAIL=\(.occupant.username)\nOCCUPANT_PASSWORD=\(.occupant.password)" else empty end),
  (if .brigadista then "TACTICO_EMAIL=\(.brigadista.username)\nTACTICO_PASSWORD=\(.brigadista.password)" else empty end)
' <<<"$CREDS" | sed 's/^/  /'
# `if`, no `[[ ]] && echo`: como ÚLTIMO comando, un test falso haría salir al
# script con código 1 pese a haber sembrado todo bien (set -e).
if [[ "$need_code" == 1 ]]; then
  echo "  SITE_CODE=$SITE_CODE"
fi
