#!/usr/bin/env bash
# Siembra y CONDUCE un incidente de staging para los E2E móviles (GATE-HW).
#
# Por qué existe: 4 de los 5 flujos Maestro (01 crisis, 02 daños, 03 dictamen,
# 05 offline/headcount) exigen un incidente ACTIVO en el sitio del occupant, y
# NO hay un `POST /incidents`: los incidentes los abre el pipeline de ingesta/
# correlación (`IncidentEngine`), no una llamada directa. Esperar un sismo real
# no es reproducible; el modo de prueba del gabinete (T-1.69) a propósito NO
# publica a la nube. Este script inserta directamente en la BD de staging (por
# el MISMO patrón SSM→túnel que `seed_mobile_users.sh`) las filas EXACTAS que
# `GET /sites/{id}/mobile-state` lee para derivar la fase.
#
# La fase se deriva en `api/src/takab_api/routers/mobile_site.py` de 3 cosas:
#   1) incidente con `state <> 'closed'`               (si no ⇒ phase=idle)
#   2) última `rule_evaluations.new_tier` del sitio    (=normal ⇒ shaking_concluded)
#   3) dictamen más reciente del incidente FIRMADO+habitable ⇒ reentry_approved
# Orden de precedencia (mobile_site.py:169-174): reentry_approved > shaking_concluded > alert_active.
#
# `rule_evaluations`, `dictamens`, `life_checkins` son APPEND-ONLY (trigger
# forbid_update_delete) ⇒ para "cambiar" la fase se INSERTA una fila nueva con
# `ts`/`created_at` más reciente, jamás UPDATE. `incidents` NO es append-only
# ⇒ el reset cierra con UPDATE. Se siembra como SUPERUSUARIO (todas tienen RLS;
# igual que `db/seeds/prod_fleet.sql` y el paso 2 de `seed_mobile_users.sh`).
#
# [T-6.18] UN INCIDENTE FRESCO POR CORRIDA. El id era una constante y `crisis`
# REABRÍA el mismo incidente; en cuanto una corrida pasaba por `reentry`, ese
# incidente se quedaba con un dictamen firmado —`dictamens` es append-only— y la
# derivación, que busca el dictamen POR INCIDENTE, devolvía `reentry_approved`
# para siempre. Desde entonces `PHASE=crisis` no producía la toma de crisis y el
# flujo 01 de Maestro no podía pasar: el arnés prometía algo que ya no hacía.
# Ahora `crisis` CIERRA lo abierto del sitio y abre uno nuevo; los demás
# subcomandos trabajan sobre el incidente abierto que encuentran. Con
# `INCIDENT_ID=<uuid>` se puede volver a fijar uno concreto.
#
# El SQL vive en `infra/scripts/sql/staging-incident/*.sql` — no por estética:
# `api/tests/api/test_seed_staging_incident.py` corre ESOS MISMOS ficheros contra
# la base de tests y comprueba contra el endpoint real que la secuencia
# crisis→reentry→crisis vuelve a dar `alert_active`. Un arnés que no se ejerce
# se pudre en silencio, que es exactamente lo que pasó aquí.
#
# Subcomandos (idempotentes; imprimen la fase derivada resultante):
#   crisis    (default) CIERRA lo abierto y abre uno NUEVO + tier `evacuate_or_hold`
#   conclude  tier `normal` (ts posterior)                          ⇒ shaking_concluded
#   reentry   dictamen firmado `inhabit_monitor`                    ⇒ reentry_approved
#   roster    N ocupantes sintéticos NO reportados (headcount 2.6 / flujo 05)
#   reset     cierra el incidente                                   ⇒ idle
#   status    solo imprime la fase derivada actual (no muta nada)
#
# Uso:  AWS_PROFILE=takab-dev infra/scripts/seed_staging_incident.sh [subcomando]
#       ROSTER_N=3  → cuántos ocupantes sintéticos siembra `roster` (default 3).
set -euo pipefail

TF_DIR="$(cd "$(dirname "$0")/../terraform/envs/dev" && pwd)"

# Mismos IDs de siembra que seed_mobile_users.sh (para que el enrolamiento del
# occupant y el incidente caigan en el MISMO sitio/zona). Overridables por env.
TENANT_ID="${TENANT_ID:-d0000000-0000-0000-0000-000000000001}"
SITE_ID="${SITE_ID:-d1000000-0000-0000-0000-000000000000}"
ZONE_ID="${ZONE_ID:-d2000000-0000-0000-0000-000000000001}"

# [T-6.18] Sin valor por defecto: `crisis` genera uno nuevo y el resto resuelve
# el incidente ABIERTO del sitio. Fijarlo sigue siendo posible por entorno.
INCIDENT_ID="${INCIDENT_ID:-}"
EVENT_UUID="${EVENT_UUID:-}"
SQL_DIR="$(cd "$(dirname "$0")/sql/staging-incident" && pwd)"

ROSTER_N="${ROSTER_N:-3}"
DB_LOCAL_PORT="${DB_LOCAL_PORT:-5436}" # 5436: no choca con make db-tunnel(5434) ni el seed de usuarios(5435)

SUB="${1:-crisis}"
case "$SUB" in
crisis | conclude | reentry | roster | reset | status) ;;
*)
  echo "subcomando inválido: $SUB (usa crisis|conclude|reentry|roster|reset|status)" >&2
  exit 2
  ;;
esac

REGION="$(terraform -chdir="$TF_DIR" output -raw region 2>/dev/null || echo us-east-2)"

echo "sitio=$SITE_ID  zona=$ZONE_ID  subcomando=$SUB"
echo

# --- Túnel SSM → BD (patrón idéntico a seed_mobile_users.sh) -------------------
DB_ID="$(terraform -chdir="$TF_DIR" output -raw db_instance_id)"
DB_IP="$(terraform -chdir="$TF_DIR" output -raw db_private_ip)"
DB_SECRET="$(aws secretsmanager get-secret-value --secret-id takab/dev/db/superuser \
  --region "$REGION" --query SecretString --output text)"
DB_USER="$(jq -r .username <<<"$DB_SECRET")"
DB_PASS="$(jq -r .password <<<"$DB_SECRET")"
DB_NAME="$(jq -r .dbname <<<"$DB_SECRET")"

echo "Abriendo túnel SSM → puerto $DB_LOCAL_PORT…"
aws ssm start-session --region "$REGION" --target "$DB_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$DB_IP\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"$DB_LOCAL_PORT\"]}" \
  >/dev/null 2>&1 &
TUNNEL_PID=$!
# `aws ssm` lanza session-manager-plugin como HIJO: matar solo al padre deja el
# plugin vivo con el puerto tomado y la siguiente corrida no abre el túnel.
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

# Guard: sin el sitio, las FK fallan con un mensaje peor que este.
if [[ "$("${PSQL[@]}" -tAc "SELECT count(*) FROM sites WHERE site_id = '$SITE_ID'")" != "1" ]]; then
  echo "  ✗ el sitio $SITE_ID no existe en la nube — aplica db/seeds/prod_fleet.sql" >&2
  exit 1
fi

# --- Resolución del incidente ------------------------------------------------
# `crisis` abre uno NUEVO; el resto trabaja sobre el que esté abierto en el
# sitio. El uuid lo genera la propia base (`gen_random_uuid`) para no depender
# de `uuidgen`, que no está en todas las máquinas.
abierto() {
  "${PSQL[@]}" -tAc "SELECT incident_id FROM incidents
                      WHERE site_id = '$SITE_ID' AND state <> 'closed'
                      ORDER BY opened_at DESC LIMIT 1"
}

if [[ "$SUB" == "crisis" ]]; then
  IID="${INCIDENT_ID:-$("${PSQL[@]}" -tAc 'SELECT gen_random_uuid()')}"
  EUUID="${EVENT_UUID:-$("${PSQL[@]}" -tAc 'SELECT gen_random_uuid()')}"
else
  IID="${INCIDENT_ID:-$(abierto)}"
  EUUID="$EVENT_UUID"
  if [[ -z "$IID" && "$SUB" != "reset" && "$SUB" != "status" && "$SUB" != "roster" ]]; then
    echo "  ✗ no hay incidente abierto en $SITE_ID — corre 'crisis' primero" >&2
    exit 1
  fi
fi

V=(-v tenant="$TENANT_ID" -v site="$SITE_ID" -v zone="$ZONE_ID" -v iid="$IID" -v euuid="$EUUID")
echo "incidente=${IID:-∅}"

case "$SUB" in
crisis)
  "${PSQL[@]}" "${V[@]}" -f "$SQL_DIR/crisis.sql"
  echo "  ✓ incidente FRESCO $IID (los anteriores del sitio quedaron cerrados)"
  ;;
conclude)
  "${PSQL[@]}" "${V[@]}" -f "$SQL_DIR/conclude.sql"
  ;;
reentry)
  "${PSQL[@]}" "${V[@]}" -f "$SQL_DIR/reentry.sql"
  echo "  (nota: el push OPS real lo dispara la consola al firmar; por SQL la app"
  echo "   levanta reentry_approved en su próximo poll de mobile-state ≤ ~60 s)"
  ;;
roster)
  for i in $(seq 1 "$ROSTER_N"); do
    UID_N="$(printf 'd5000000-0000-0000-0000-%012d' "$i")"
    "${PSQL[@]}" "${V[@]}" -v uid="$UID_N" -f "$SQL_DIR/roster.sql"
    echo "  ✓ ocupante sintético $UID_N (no reportado)"
  done
  ;;
reset)
  "${PSQL[@]}" "${V[@]}" -f "$SQL_DIR/reset.sql"
  ;;
status) ;;
esac

echo
echo "Fase derivada actual (réplica de mobile_site.py; la verdad es el endpoint):"
"${PSQL[@]}" "${V[@]}" -tA -f "$SQL_DIR/phase.sql"

_kill_tunnel
trap - EXIT
unset PGPASSWORD
