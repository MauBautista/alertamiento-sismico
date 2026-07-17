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
# Subcomandos (idempotentes; imprimen la fase derivada resultante):
#   crisis    (default) abre el incidente + tier `evacuate_or_hold` ⇒ alert_active
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

# Incidente FIJO (idempotencia): re-correr `crisis` reabre el MISMO incidente.
INCIDENT_ID="${INCIDENT_ID:-d4000000-0000-0000-0000-000000000001}"
EVENT_UUID="${EVENT_UUID:-d4000000-0000-0000-0000-0000000000e1}"

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

echo "incidente=$INCIDENT_ID  sitio=$SITE_ID  zona=$ZONE_ID  subcomando=$SUB"
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

V=(-v tenant="$TENANT_ID" -v site="$SITE_ID" -v zone="$ZONE_ID" -v iid="$INCIDENT_ID" -v euuid="$EVENT_UUID")

case "$SUB" in
crisis)
  # Incidente abierto (idempotente por incident_id) + tier de crisis.
  # severity/state/trigger según CHECK de schema.sql:214-216; event_uuid NOT NULL UNIQUE.
  "${PSQL[@]}" "${V[@]}" <<'SQL'
INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, event_id,
                       opened_at, severity, state, trigger)
VALUES (:'iid'::uuid, :'euuid'::uuid, :'tenant'::uuid, :'site'::uuid, NULL,
        now(), 'warning', 'open', 'sasmex')
ON CONFLICT (incident_id) DO UPDATE SET state = 'open';

-- Tier de crisis. gateway_id es uuid NOT NULL SIN FK ⇒ cualquiera vale.
INSERT INTO rule_evaluations (ts, tenant_id, site_id, gateway_id, prev_tier, new_tier)
VALUES (now(), :'tenant'::uuid, :'site'::uuid, gen_random_uuid(), 'normal', 'evacuate_or_hold');
SQL
  ;;
conclude)
  if [[ "$("${PSQL[@]}" -tAc "SELECT count(*) FROM incidents WHERE incident_id='$INCIDENT_ID' AND state<>'closed'")" != "1" ]]; then
    echo "  ✗ no hay incidente abierto — corre 'crisis' primero" >&2
    exit 1
  fi
  "${PSQL[@]}" "${V[@]}" <<'SQL'
INSERT INTO rule_evaluations (ts, tenant_id, site_id, gateway_id, prev_tier, new_tier)
VALUES (now(), :'tenant'::uuid, :'site'::uuid, gen_random_uuid(), 'evacuate_or_hold', 'normal');
SQL
  ;;
reentry)
  if [[ "$("${PSQL[@]}" -tAc "SELECT count(*) FROM incidents WHERE incident_id='$INCIDENT_ID' AND state<>'closed'")" != "1" ]]; then
    echo "  ✗ no hay incidente abierto — corre 'crisis' primero" >&2
    exit 1
  fi
  # Dictamen FIRMADO (signed_by no nulo) + habitable (inhabit_monitor).
  # basis es jsonb NOT NULL sin default ⇒ '{}'. Append-only ⇒ fila nueva.
  "${PSQL[@]}" "${V[@]}" <<'SQL'
INSERT INTO dictamens (tenant_id, incident_id, status, basis, signed_by)
VALUES (:'tenant'::uuid, :'iid'::uuid, 'inhabit_monitor', '{}'::jsonb, gen_random_uuid());
SQL
  echo "  (nota: el push OPS real lo dispara la consola al firmar; por SQL la app"
  echo "   levanta reentry_approved en su próximo poll de mobile-state ≤ ~60 s)"
  ;;
roster)
  # Ocupantes SINTÉTICOS no reportados, para que el headcount (2.6/flujo 05)
  # tenga a quién marcar 'verificado en persona'. role sin CHECK; el roster/
  # headcount cuenta TODOS los roles (el directorio filtra, el headcount no).
  for i in $(seq 1 "$ROSTER_N"); do
    UID_N="$(printf 'd5000000-0000-0000-0000-%012d' "$i")"
    "${PSQL[@]}" "${V[@]}" -v uid="$UID_N" <<'SQL'
INSERT INTO user_zone_assignments (user_id, tenant_id, site_id, zone_id, role)
VALUES (:'uid'::uuid, :'tenant'::uuid, :'site'::uuid, :'zone'::uuid, 'occupant')
ON CONFLICT (user_id, site_id) DO NOTHING;
SQL
    echo "  ✓ ocupante sintético $UID_N (no reportado)"
  done
  ;;
reset)
  # incidents NO es append-only ⇒ cerrar por UPDATE devuelve la fase a idle.
  "${PSQL[@]}" "${V[@]}" <<'SQL'
UPDATE incidents SET state = 'closed' WHERE incident_id = :'iid'::uuid;
SQL
  ;;
status) ;;
esac

echo
echo "Fase derivada actual (réplica de mobile_site.py:152-174):"
"${PSQL[@]}" "${V[@]}" -tA <<'SQL'
SELECT 'phase=' || CASE
  WHEN NOT EXISTS (SELECT 1 FROM incidents WHERE site_id = :'site'::uuid AND state <> 'closed')
    THEN 'idle'
  WHEN (SELECT (signed_by IS NOT NULL) AND status IN ('normal_operation','inhabit_monitor')
          FROM dictamens WHERE incident_id = :'iid'::uuid ORDER BY created_at DESC LIMIT 1)
    THEN 'reentry_approved'
  WHEN (SELECT new_tier FROM rule_evaluations WHERE site_id = :'site'::uuid ORDER BY ts DESC LIMIT 1) = 'normal'
    THEN 'shaking_concluded'
  ELSE 'alert_active'
END
|| '   | tier=' || COALESCE((SELECT new_tier FROM rule_evaluations WHERE site_id = :'site'::uuid ORDER BY ts DESC LIMIT 1), '∅')
|| '   | roster=' || (SELECT count(*) FROM user_zone_assignments WHERE site_id = :'site'::uuid)::text
|| '   | no_reportados=' || (
     SELECT count(*) FROM user_zone_assignments uza
     WHERE uza.site_id = :'site'::uuid
       AND NOT EXISTS (SELECT 1 FROM life_checkins lc
                       WHERE lc.incident_id = :'iid'::uuid AND lc.user_id = uza.user_id))::text;
SQL

_kill_tunnel
trap - EXIT
unset PGPASSWORD
