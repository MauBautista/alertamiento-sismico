#!/usr/bin/env bash
# Abre la consola SOC a la IP pública ACTUAL y limpia las reglas manuales viejas.
#
# Por qué existe: la IP doméstica de Mauricio es DINÁMICA y el SG `takab-dev-web`
# acota el 443 a /32. Cada rotación deja la consola inalcanzable (timeout, no 403:
# el paquete muere en el SG) y se resolvía a mano con `authorize-security-group-
# ingress`. Esas reglas manuales quedan FUERA de Terraform y son una mina: el
# siguiente `terraform apply` que gestione el mismo CIDR falla por regla duplicada.
# Pasó el 2026-07-18 (regla sgr-01634dbaf5488df25) y el comando para revocarla
# quedó "documentado en el runbook"... que no existía.
#
# Cómo distingue lo manual de lo de Terraform: el módulo `serve` escribe una
# descripción canónica, "Consola SOC (HTTPS) desde <cidr>" (modules/serve/main.tf).
# Toda regla 443 con otra descripción es manual ⇒ revocable.
#
# Uso:
#   AWS_PROFILE=takab-dev infra/scripts/allow_my_ip.sh            # asegura acceso
#   AWS_PROFILE=takab-dev infra/scripts/allow_my_ip.sh --status   # solo reporta
#   AWS_PROFILE=takab-dev infra/scripts/allow_my_ip.sh --revoke   # limpia antes de un apply
set -euo pipefail

MODE="${1:-ensure}"
case "$MODE" in
  ensure | --status | --revoke) ;;
  *)
    echo "uso: $0 [--status|--revoke]" >&2
    exit 2
    ;;
esac

: "${AWS_PROFILE:?exporta AWS_PROFILE (p. ej. takab-dev)}"
AWS_REGION="${AWS_REGION:-us-east-2}"
SG_NAME="${SG_NAME:-takab-dev-web}"
TFVARS="$(cd "$(dirname "$0")/../terraform/envs/dev" && pwd)/local.auto.tfvars"
#: Descripción que escribe Terraform. Debe coincidir EXACTO con modules/serve/main.tf.
TF_DESC_PREFIX="Consola SOC (HTTPS) desde "
MANUAL_DESC="TEMPORAL allow_my_ip.sh - reconciliar en local.auto.tfvars"

aws_() { aws --profile "$AWS_PROFILE" --region "$AWS_REGION" "$@"; }

if ! aws_ sts get-caller-identity >/dev/null 2>&1; then
  echo "ERROR: sesión AWS inválida o expirada. Corre: aws sso login --profile $AWS_PROFILE" >&2
  exit 1
fi

SG_ID="$(aws_ ec2 describe-security-groups \
  --filters "Name=group-name,Values=$SG_NAME" \
  --query 'SecurityGroups[0].GroupId' --output text)"
if [ -z "$SG_ID" ] || [ "$SG_ID" = "None" ]; then
  echo "ERROR: no existe el security group '$SG_NAME'." >&2
  echo "       ¿Aplicaste con -var serve_enabled=true? La consola no está publicada." >&2
  exit 1
fi

# Reglas 443 vigentes: id, cidr y descripción (TSV para leerlas sin jq).
RULES="$(aws_ ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=$SG_ID" \
  --query "SecurityGroupRules[?!IsEgress && FromPort==\`443\`].[SecurityGroupRuleId,CidrIpv4,Description]" \
  --output text)"

MY_IP="$(curl -fsS --max-time 10 https://checkip.amazonaws.com | tr -d '[:space:]')"
if ! printf '%s' "$MY_IP" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "ERROR: no pude determinar la IP pública (obtuve '$MY_IP')." >&2
  exit 1
fi
MY_CIDR="${MY_IP}/32"

echo "SG        : $SG_ID ($SG_NAME · $AWS_REGION)"
echo "IP actual : $MY_CIDR"
echo

manual_ids=""
allowed_now="no"
while IFS=$'\t' read -r rule_id cidr desc; do
  [ -n "${rule_id:-}" ] || continue
  origen="manual"
  case "$desc" in "${TF_DESC_PREFIX}"*) origen="terraform" ;; esac
  [ "$cidr" = "$MY_CIDR" ] && allowed_now="sí"
  printf '  %-24s %-20s %-9s %s\n' "$rule_id" "$cidr" "$origen" "$desc"
  [ "$origen" = "manual" ] && manual_ids="$manual_ids $rule_id"
done <<EOF
$RULES
EOF
echo

if [ "$MODE" = "--status" ]; then
  echo "IP actual permitida: $allowed_now"
  exit 0
fi

# Las reglas manuales SIEMPRE se van: o son de una IP muerta, o son la duplicada
# que hará fallar el próximo apply. La del IP actual se recrea abajo.
if [ -n "$manual_ids" ]; then
  # La lista de ids va sin comillas a propósito: son argumentos separados.
  # shellcheck disable=SC2086
  aws_ ec2 revoke-security-group-ingress --group-id "$SG_ID" --security-group-rule-ids $manual_ids >/dev/null
  echo "revocadas reglas manuales:$manual_ids"
  [ "$allowed_now" = "sí" ] && allowed_now="no" # si mi acceso venía de una manual, se fue con ella
else
  echo "sin reglas manuales que revocar."
fi

if [ "$MODE" = "--revoke" ]; then
  echo
  echo "Listo para 'terraform apply'. Recuerda que web_allowed_cidrs debe incluir tu IP"
  echo "o la consola quedará inalcanzable tras el apply."
  exit 0
fi

if [ "$allowed_now" = "sí" ]; then
  echo "La IP actual ya está permitida por una regla de Terraform. Nada que hacer."
else
  aws_ ec2 authorize-security-group-ingress --group-id "$SG_ID" \
    --ip-permissions "IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=$MY_CIDR,Description='$MANUAL_DESC'}]" \
    >/dev/null
  echo "autorizado $MY_CIDR en el 443."
fi

echo
echo "RECONCILIA Terraform (si no, el apply borrará tu acceso o fallará por duplicada):"
echo "  1) en $TFVARS deja:"
if [ -f "$TFVARS" ]; then
  current="$(grep -E '^web_allowed_cidrs' "$TFVARS" || true)"
  [ -n "$current" ] && echo "     (hoy: $current)"
fi
echo "     web_allowed_cidrs = [\"$MY_CIDR\"]   # + las IPs fijas que quieras conservar"
echo "  2) antes del apply:  AWS_PROFILE=$AWS_PROFILE $0 --revoke"
