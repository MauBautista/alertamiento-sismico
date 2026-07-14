#!/usr/bin/env bash
# Alta de los usuarios de CONSOLA en el pool Cognito (T-1.62).
#
# Por qué existe: el rol de un usuario viaja en el TOKEN (custom:role + grupo),
# no en la base — no hay tabla `users`. Sin usuarios sembrados solo se puede
# entrar con el único que se creó a mano, y probar la matriz RBAC en la nube era
# imposible (el panel LOGIN DEV no existe en producción: la API no monta
# /dev/token, y hacerlo sería un forjador libre de claims expuesto a internet).
#
# Dos pasos obligatorios por usuario, y el segundo es el que se olvida:
#   1. custom:role  → lo que la API lee para la matriz.
#   2. GRUPO Cognito del mismo nombre → sin él, auth/claims.py rechaza el token
#      con "role not in groups" (401) aunque el custom:role sea correcto.
#
# Las contraseñas se generan aquí, se guardan en Secrets Manager y se imprimen
# UNA vez (son la vía de entrega: no hay otro canal). El pool exige MFA TOTP:
# cada usuario enrola su authenticator en el primer login por la Hosted UI.
#
# Uso:  AWS_PROFILE=takab-dev infra/scripts/seed_console_users.sh [rol ...]
#       (sin args: los 6 roles de consola web)
set -euo pipefail

TF_DIR="$(cd "$(dirname "$0")/../terraform/envs/dev" && pwd)"
SECRET_ID="takab/dev/console/users"

# Tenant del seed de la flota real (db/seeds/prod_fleet.sql): sin este claim la
# consola entra pero el mapa sale vacío (RLS no ve ningún sitio).
TENANT_ID="d0000000-0000-0000-0000-000000000001"

# Los 6 roles con superficie WEB (RBAC-TAKAB.md §2). brigadista/security_guard/
# occupant son móviles: en la consola solo verían rutas vacías.
DEFAULT_ROLES=(takab_superadmin tenant_admin soc_operator inspector gov_operator building_admin)
ROLES=("${@:-${DEFAULT_ROLES[@]}}")

POOL_ID="$(terraform -chdir="$TF_DIR" output -raw user_pool_id)"
REGION="$(terraform -chdir="$TF_DIR" output -raw region 2>/dev/null || echo us-east-2)"
BASE_EMAIL="$(terraform -chdir="$TF_DIR" output -raw budget_email 2>/dev/null || echo mauriciobaujim@gmail.com)"
LOCAL_PART="${BASE_EMAIL%@*}"
DOMAIN="${BASE_EMAIL#*@}"

echo "pool=$POOL_ID  region=$REGION  tenant=$TENANT_ID"
echo "roles: ${ROLES[*]}"
echo

CREDS="{}"
for ROLE in "${ROLES[@]}"; do
  # Plus-addressing: todos los buzones caen en la misma bandeja real, y cada uno
  # es una identidad Cognito distinta.
  EMAIL="${LOCAL_PART}+${ROLE}@${DOMAIN}"
  # Política del pool: ≥12, mayúscula, minúscula y dígito (símbolos no exigidos).
  PASS="Takab$(openssl rand -hex 6)Aa1"

  aws cognito-idp admin-create-user \
    --user-pool-id "$POOL_ID" --region "$REGION" \
    --username "$EMAIL" \
    --message-action SUPPRESS \
    --user-attributes \
      Name=email,Value="$EMAIL" \
      Name=email_verified,Value=true \
      Name=custom:tenant_id,Value="$TENANT_ID" \
      Name=custom:role,Value="$ROLE" \
      Name=custom:site_scope,Value='*' \
      Name=custom:surface,Value=web \
    >/dev/null 2>&1 || echo "  (ya existía: $EMAIL — se actualizan atributos)"

  # Re-aplicar atributos hace el script idempotente (un rol cambiado se corrige).
  aws cognito-idp admin-update-user-attributes \
    --user-pool-id "$POOL_ID" --region "$REGION" \
    --username "$EMAIL" \
    --user-attributes \
      Name=custom:tenant_id,Value="$TENANT_ID" \
      Name=custom:role,Value="$ROLE" \
      Name=custom:site_scope,Value='*' \
      Name=custom:surface,Value=web \
    >/dev/null

  # EL PASO QUE SE OLVIDA: sin el grupo, el login termina en 401.
  aws cognito-idp admin-add-user-to-group \
    --user-pool-id "$POOL_ID" --region "$REGION" \
    --username "$EMAIL" --group-name "$ROLE" >/dev/null

  # Permanente: sin esto el primer login cae en FORCE_CHANGE_PASSWORD, que la
  # Hosted UI resuelve pero el flujo queda a medias si se automatiza.
  aws cognito-idp admin-set-user-password \
    --user-pool-id "$POOL_ID" --region "$REGION" \
    --username "$EMAIL" --password "$PASS" --permanent >/dev/null

  CREDS="$(jq -c --arg u "$EMAIL" --arg p "$PASS" --arg r "$ROLE" \
    '. + {($r): {username: $u, password: $p}}' <<<"$CREDS")"
  echo "  ✓ $ROLE  →  $EMAIL"
done

aws secretsmanager put-secret-value --secret-id "$SECRET_ID" --region "$REGION" \
  --secret-string "$CREDS" >/dev/null 2>&1 ||
  aws secretsmanager create-secret --name "$SECRET_ID" --region "$REGION" \
    --description "Usuarios de consola sembrados (T-1.62)" \
    --secret-string "$CREDS" >/dev/null

echo
echo "Credenciales guardadas en Secrets Manager ($SECRET_ID). Se imprimen UNA vez:"
jq -r 'to_entries[] | "  \(.key)\t\(.value.username)\t\(.value.password)"' <<<"$CREDS"
echo
echo "Primer login: Hosted UI → pedirá enrolar MFA TOTP (el pool lo exige a todos)."
