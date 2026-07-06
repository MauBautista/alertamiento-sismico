#!/usr/bin/env bash
# Verificacion de aceptacion de T-1.15 contra la cuenta dev.
# Imprime PASS/FAIL por check; exit != 0 si alguno falla.
set -euo pipefail

PROFILE=takab-dev
REGION=us-east-2
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TF_DIR="$ROOT/infra/terraform/envs/dev"

AWS=(aws --profile "$PROFILE" --region "$REGION")

FAILURES=0
pass() { echo "PASS  $1"; }
fail() {
  echo "FAIL  $1"
  FAILURES=$((FAILURES + 1))
}

tf_out() {
  terraform -chdir="$TF_DIR" output -raw "$1" 2>/dev/null
}

ACCOUNT_ID="$("${AWS[@]}" sts get-caller-identity --query Account --output text)"

# 1. Bucket de estado ---------------------------------------------------------
STATE_BUCKET="takab-tfstate-$ACCOUNT_ID"
if "${AWS[@]}" s3api head-bucket --bucket "$STATE_BUCKET" >/dev/null 2>&1; then
  pass "state bucket $STATE_BUCKET existe"
else
  fail "state bucket $STATE_BUCKET existe"
fi
if [ "$("${AWS[@]}" s3api get-bucket-versioning --bucket "$STATE_BUCKET" --query Status --output text 2>/dev/null || true)" = "Enabled" ]; then
  pass "state bucket versioning Enabled"
else
  fail "state bucket versioning Enabled"
fi
if "${AWS[@]}" s3api get-bucket-encryption --bucket "$STATE_BUCKET" >/dev/null 2>&1; then
  pass "state bucket con cifrado en reposo"
else
  fail "state bucket con cifrado en reposo"
fi

# 2. Colas SQS con redrive ------------------------------------------------------
for Q in takab-dev-q-events takab-dev-q-telemetry takab-dev-q-backfill; do
  QURL="$("${AWS[@]}" sqs get-queue-url --queue-name "$Q" --query QueueUrl --output text 2>/dev/null || true)"
  if [ -z "$QURL" ] || [ "$QURL" = "None" ]; then
    fail "cola $Q existe"
    fail "cola $Q tiene RedrivePolicy"
    continue
  fi
  pass "cola $Q existe"
  RP="$("${AWS[@]}" sqs get-queue-attributes --queue-url "$QURL" --attribute-names RedrivePolicy --query Attributes.RedrivePolicy --output text 2>/dev/null || true)"
  if [ -n "$RP" ] && [ "$RP" != "None" ]; then
    pass "cola $Q tiene RedrivePolicy"
  else
    fail "cola $Q tiene RedrivePolicy"
  fi
done

# 3. Endpoint IoT ---------------------------------------------------------------
IOT_ENDPOINT_AWS="$("${AWS[@]}" iot describe-endpoint --endpoint-type iot:Data-ATS --query endpointAddress --output text 2>/dev/null || true)"
IOT_ENDPOINT_TF="$(tf_out iot_endpoint || true)"
if [ -n "$IOT_ENDPOINT_AWS" ] && [ "$IOT_ENDPOINT_AWS" = "$IOT_ENDPOINT_TF" ]; then
  pass "endpoint IoT Data-ATS coincide con terraform output ($IOT_ENDPOINT_AWS)"
else
  fail "endpoint IoT Data-ATS coincide con terraform output (aws='$IOT_ENDPOINT_AWS' tf='$IOT_ENDPOINT_TF')"
fi

# 4. Grupos Cognito -------------------------------------------------------------
EXPECTED_GROUPS="brigadista building_admin gov_operator inspector occupant security_guard soc_operator takab_superadmin takab_support tenant_admin"
POOL_ID="$(tf_out user_pool_id || true)"
GROUPS_GOT="$("${AWS[@]}" cognito-idp list-groups --user-pool-id "$POOL_ID" --query 'Groups[].GroupName' --output text 2>/dev/null | tr '\t' '\n' | sort | xargs || true)"
if [ "$GROUPS_GOT" = "$EXPECTED_GROUPS" ]; then
  pass "cognito: exactamente los 10 grupos esperados"
else
  fail "cognito: exactamente los 10 grupos esperados (got: '$GROUPS_GOT')"
fi

# 5. Thing gw-dev-0001 ----------------------------------------------------------
THING=gw-dev-0001
if "${AWS[@]}" iot describe-thing --thing-name "$THING" >/dev/null 2>&1; then
  pass "thing $THING existe"
else
  fail "thing $THING existe"
fi
PRINCIPAL="$("${AWS[@]}" iot list-thing-principals --thing-name "$THING" --query 'principals[0]' --output text 2>/dev/null || true)"
if [ -n "$PRINCIPAL" ] && [ "$PRINCIPAL" != "None" ]; then
  pass "thing $THING tiene >=1 principal"
  CERT_ID="${PRINCIPAL##*/}"
  CERT_STATUS="$("${AWS[@]}" iot describe-certificate --certificate-id "$CERT_ID" --query certificateDescription.status --output text 2>/dev/null || true)"
  if [ "$CERT_STATUS" = "ACTIVE" ]; then
    pass "cert de $THING en estado ACTIVE"
  else
    fail "cert de $THING en estado ACTIVE (status='$CERT_STATUS')"
  fi
else
  fail "thing $THING tiene >=1 principal"
  fail "cert de $THING en estado ACTIVE (sin principal)"
fi

# 6. Instancia DB running + SSM -------------------------------------------------
DB_ID="$(tf_out db_instance_id || true)"
DB_STATE="$("${AWS[@]}" ec2 describe-instances --instance-ids "$DB_ID" --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null || true)"
if [ "$DB_STATE" = "running" ]; then
  pass "instancia DB $DB_ID running"
else
  fail "instancia DB running (id='$DB_ID' state='$DB_STATE')"
fi
SSM_SEEN="$("${AWS[@]}" ssm describe-instance-information --filters "Key=InstanceIds,Values=$DB_ID" --query 'InstanceInformationList[0].InstanceId' --output text 2>/dev/null || true)"
if [ -n "$DB_ID" ] && [ "$SSM_SEEN" = "$DB_ID" ]; then
  pass "instancia DB registrada en SSM"
else
  fail "instancia DB registrada en SSM"
fi

# 7. Smoke E2E: publish MQTT -> regla IoT -> q-events ---------------------------
SMOKE_OK=""
EVENTS_URL="$("${AWS[@]}" sqs get-queue-url --queue-name takab-dev-q-events --query QueueUrl --output text 2>/dev/null || true)"
if [ -n "$EVENTS_URL" ] && [ "$EVENTS_URL" != "None" ] && [ -n "$IOT_ENDPOINT_AWS" ]; then
  # --endpoint-url ATS: el endpoint por defecto del CLI para iot-data es el legado
  "${AWS[@]}" iot-data publish \
    --endpoint-url "https://$IOT_ENDPOINT_AWS" \
    --topic takab/events \
    --cli-binary-format raw-in-base64-out \
    --payload '{"event_id":"smoke-verify","tenant_id":"tenant-dev","site_id":"site-dev","source":"manual","tier":"watch"}' || true
  for _ in 1 2 3 4 5 6; do
    RESP="$("${AWS[@]}" sqs receive-message --queue-url "$EVENTS_URL" --wait-time-seconds 5 --max-number-of-messages 10 --output json 2>/dev/null || true)"
    HANDLE="$(python3 -c '
import json, sys
raw = sys.stdin.read().strip()
if raw:
    for m in json.loads(raw).get("Messages", []):
        body = m.get("Body", "")
        if "smoke-verify" in body and "meta_principal" in body:
            print(m["ReceiptHandle"])
            break
' <<<"$RESP")"
    if [ -n "$HANDLE" ]; then
      "${AWS[@]}" sqs delete-message --queue-url "$EVENTS_URL" --receipt-handle "$HANDLE"
      SMOKE_OK=yes
      break
    fi
  done
fi
if [ "$SMOKE_OK" = "yes" ]; then
  pass "smoke E2E: takab/events -> regla -> q-events (mensaje con meta_principal)"
else
  fail "smoke E2E: takab/events -> regla -> q-events"
fi

# 8. ECR + KMS + budget ---------------------------------------------------------
if "${AWS[@]}" ecr describe-repositories --repository-names takab/cloud takab/fleet-sim >/dev/null 2>&1; then
  pass "repos ECR takab/cloud y takab/fleet-sim existen"
else
  fail "repos ECR takab/cloud y takab/fleet-sim existen"
fi
if "${AWS[@]}" kms describe-key --key-id alias/takab-dev-data >/dev/null 2>&1; then
  pass "alias KMS takab-dev-data existe"
else
  fail "alias KMS takab-dev-data existe"
fi
if "${AWS[@]}" budgets describe-budgets --account-id "$ACCOUNT_ID" --output json 2>/dev/null | grep -q '"takab-dev-monthly"'; then
  pass "budget takab-dev-monthly existe"
else
  fail "budget takab-dev-monthly existe"
fi

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "RESULTADO: $FAILURES checks FALLARON"
  exit 1
fi
echo "RESULTADO: todos los checks PASS"
