#!/usr/bin/env bash
# Túnel SSM → base de datos de la nube, en un solo sitio.
#
# La instancia no tiene ingreso SSH: todo va por SSM. El bloque que abre el
# reenvío de puerto, espera a que el socket conteste y mata al plugin al salir
# estaba COPIADO en `seed_mobile_users.sh` y en `seed_staging_incident.sh`, y el
# 2026-09-12 iba a copiarse una tercera vez en el guion de la demostración. Tres
# copias de un procedimiento con dos trampas dentro se separan solas.
#
# Las dos trampas, que es lo que esto guarda:
#
#   1. `aws ssm start-session` lanza `session-manager-plugin` como HIJO. Matar
#      solo al padre deja el plugin vivo con el puerto tomado, y la corrida
#      siguiente no abre el túnel — sin decir por qué.
#   2. El puerto tarda en contestar. Sin la espera, el `psql` de después falla
#      con «connection refused» y parece que la base está caída.
#
# Uso:
#
#     . "$(dirname "$0")/lib/tunel.sh"
#     abrir_tunel 5436            # exporta TUNEL_PUERTO y deja el trap puesto
#     psql -h 127.0.0.1 -p "$TUNEL_PUERTO" …
#
# Quien lo use con `set -e` y su propio `trap EXIT` debe encadenarlo: esto pone
# el suyo con `trap cerrar_tunel EXIT` y sobrescribirlo deja el plugin vivo.

# shellcheck disable=SC2034  # `TUNEL_PUERTO` lo lee QUIEN llama, no este fichero
TUNEL_PID=""
TUNEL_PUERTO=""

cerrar_tunel() {
  [ -n "$TUNEL_PID" ] || return 0
  pkill -P "$TUNEL_PID" 2>/dev/null || true
  kill "$TUNEL_PID" 2>/dev/null || true
  TUNEL_PID=""
}

# abrir_tunel [puerto_local] [region]
#
# Deriva instancia e IP privada de la base **con la CLI**, no con terraform: la
# caché de SSO de terraform caduca por su cuenta y tumbaría un guion de solo
# lectura que la CLI sí puede resolver (medido el 2026-09-12).
abrir_tunel() {
  local puerto="${1:-5436}" region="${2:-${AWS_REGION:-us-east-2}}" id ip
  read -r id ip <<<"$(aws ec2 describe-instances --region "$region" \
    --filters 'Name=tag:Name,Values=takab-dev-db' 'Name=instance-state-name,Values=running' \
    --query 'Reservations[0].Instances[0].[InstanceId,PrivateIpAddress]' --output text)"
  if [ -z "$id" ] || [ "$id" = "None" ]; then
    echo "  ✗ no hay instancia 'takab-dev-db' corriendo. ¿La encendiste? → make cloud-start" >&2
    return 1
  fi

  aws ssm start-session --region "$region" --target "$id" \
    --document-name AWS-StartPortForwardingSessionToRemoteHost \
    --parameters "{\"host\":[\"$ip\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"$puerto\"]}" \
    >/dev/null 2>&1 &
  TUNEL_PID=$!
  trap cerrar_tunel EXIT

  local _
  for _ in $(seq 1 30); do
    if (exec 3<>"/dev/tcp/127.0.0.1/$puerto") 2>/dev/null; then
      exec 3<&-
      TUNEL_PUERTO="$puerto"
      return 0
    fi
    sleep 1
  done
  echo "  ✗ el túnel no abrió en 30 s contra $id ($ip)" >&2
  cerrar_tunel
  return 1
}

# Credenciales del superusuario de la base, como las lee el resto de scripts.
credenciales_db() {
  local region="${1:-${AWS_REGION:-us-east-2}}"
  aws secretsmanager get-secret-value --secret-id takab/dev/db/superuser \
    --region "$region" --query SecretString --output text
}
