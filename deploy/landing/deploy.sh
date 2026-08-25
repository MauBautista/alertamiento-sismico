#!/usr/bin/env bash
# Despliegue de la landing publica (takabailert.com) a S3 + CloudFront.
# Se invoca con `make landing-deploy`. Runbook y rollback: deploy/landing/README.md.
#
# Terraform posee el continente (bucket/distribucion/cert/DNS, modules/site);
# ESTE script posee el contenido. Es la UNICA via de subida: un objeto sin
# Cache-Control se cachearia 86400 s en CloudFront (DefaultTTL de la policy
# gestionada CachingOptimized), asi que aqui se fija metadata SIEMPRE, por
# clase de fichero:
#   _astro/*.woff2  -> immutable 1 anio + content-type font/woff2 (el mimetypes
#                      del sistema puede no conocer woff2)
#   _astro/*        -> immutable 1 anio (nombres hasheados por el build)
#   raiz no-HTML    -> 1 h (robots, favicon, og, sitemap: nombre estable, NUNCA immutable)
#   *.html          -> 5 min, y se suben AL FINAL (un visitante a mitad de deploy
#                      no recibe HTML nuevo con assets ausentes)
set -euo pipefail

# --pre: modo de TRANSICION (una sola vez, antes del primer apply): sube todo
# con su metadata correcta EXCEPTO index.html (el objeto historico aun es de
# Terraform y pisarlo haria que el siguiente apply lo revirtiera por etag), y
# no poda, no invalida y no corre smoke. Ver deploy/landing/README.md.
MODO_PRE=0
[ "${1:-}" = "--pre" ] && MODO_PRE=1

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$REPO_ROOT"

AWS_PROFILE=${AWS_PROFILE:-takab-dev}
AWS_REGION=${AWS_REGION:-us-east-2}
TF_DEV=${TF_DEV:-infra/terraform/envs/dev}
export AWS_PROFILE AWS_REGION

fallo() { echo "ERROR: $*" >&2; exit 1; }

# --- Guardas (espejo de la regla A-1 de deploy/cloud/README.md) ---------------
[ "$(git branch --show-current)" = "main" ] || fallo "desplegar solo desde main (rama actual: $(git branch --show-current))"
[ -z "$(git status --porcelain)" ] || fallo "el arbol no esta limpio; commitea o descarta antes de desplegar"
git fetch -q origin main
[ -z "$(git log origin/main..main --oneline)" ] || fallo "main tiene commits sin push; el deploy debe salir de lo publicado"
if command -v gh >/dev/null; then
  ESTADO=$(gh run list --branch main -L 1 --json conclusion -q '.[0].conclusion' 2>/dev/null || echo "")
  [ "$ESTADO" = "success" ] || fallo "el ultimo CI de main no esta en verde (estado: ${ESTADO:-desconocido})"
fi
aws sts get-caller-identity >/dev/null 2>&1 \
  || fallo "sesion SSO caida: corre 'aws sso logout && aws sso login --profile $AWS_PROFILE' (el login a secas no basta con cache rancia)"

# --- Destinos desde terraform (el script no teclea nombres de recursos) -------
BUCKET=$(terraform -chdir="$TF_DEV" output -raw site_bucket)
DIST=$(terraform -chdir="$TF_DEV" output -raw site_distribution_id)
[ -n "$BUCKET" ] || fallo "site_bucket vacio: site_enabled apagado o terraform sin apply"
[ -n "$DIST" ] || fallo "site_distribution_id vacio"

REV=$(git rev-parse --short HEAD)
echo "== landing -> s3://$BUCKET (distribucion $DIST) rev $REV =="

# --- Build fresco con la REV horneada (el folio del pie la muestra) -----------
( cd landing && PUBLIC_REV="$REV" npm run build )

DIST_DIR=landing/dist

# --- Subida por clases: assets primero, HTML al final -------------------------
aws s3 sync "$DIST_DIR" "s3://$BUCKET" \
  --exclude '*' --include '_astro/*.woff2' \
  --content-type font/woff2 \
  --cache-control 'public, max-age=31536000, immutable'

aws s3 sync "$DIST_DIR" "s3://$BUCKET" \
  --exclude '*' --include '_astro/*' --exclude '_astro/*.woff2' \
  --cache-control 'public, max-age=31536000, immutable'

aws s3 sync "$DIST_DIR" "s3://$BUCKET" \
  --exclude '*.html' --exclude '_astro/*' \
  --cache-control 'public, max-age=3600'

if [ "$MODO_PRE" = "1" ]; then
  aws s3 sync "$DIST_DIR" "s3://$BUCKET" \
    --exclude '*' --include '*.html' --exclude 'index.html' \
    --content-type 'text/html; charset=utf-8' \
    --cache-control 'public, max-age=300'
  echo "== PRE-SYNC OK (index.html intacto). Siguiente paso: terraform plan/apply y luego 'make landing-deploy'. =="
  exit 0
fi

aws s3 sync "$DIST_DIR" "s3://$BUCKET" \
  --exclude '*' --include '*.html' \
  --content-type 'text/html; charset=utf-8' \
  --cache-control 'public, max-age=300'

# --- Evidencia de que commit sirve produccion ---------------------------------
printf '{"rev":"%s","fecha":"%s"}\n' "$REV" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > /tmp/deploy-info.json
aws s3 cp /tmp/deploy-info.json "s3://$BUCKET/deploy-info.json" \
  --content-type application/json --cache-control 'public, max-age=300'

# --- Poda de huerfanos, explicita y reversible (bucket versionado) ------------
# No se usa `sync --delete` para no pelear con los pases de metadata: se listan
# las claves remotas, se restan las locales y deploy-info.json, y se borra el resto.
aws s3api list-objects-v2 --bucket "$BUCKET" --query 'Contents[].Key' --output text \
  | tr '\t' '\n' | grep -v '^None$' | sort > /tmp/landing-remoto.txt || true
( cd "$DIST_DIR" && find . -type f | sed 's|^\./||' | sort ) > /tmp/landing-local.txt
echo 'deploy-info.json' >> /tmp/landing-local.txt
sort -o /tmp/landing-local.txt /tmp/landing-local.txt
HUERFANOS=$(comm -23 /tmp/landing-remoto.txt /tmp/landing-local.txt || true)
if [ -n "$HUERFANOS" ]; then
  echo "-- podando huerfanos (recuperables: bucket versionado):"
  while IFS= read -r clave; do
    [ -n "$clave" ] && aws s3 rm "s3://$BUCKET/$clave"
  done <<< "$HUERFANOS"
fi

# --- Invalidacion (1 ruta; free tier 1000/mes) --------------------------------
INV=$(aws cloudfront create-invalidation --distribution-id "$DIST" --paths '/*' \
  --query 'Invalidation.Id' --output text)
echo "-- invalidacion $INV creada"

# --- Smoke --------------------------------------------------------------------
sleep 20
CODIGO=$(curl -s -o /dev/null -w '%{http_code}' https://takabailert.com/ || echo 000)
[ "$CODIGO" = "200" ] || fallo "smoke: / devolvio $CODIGO"
NO_EXISTE=$(curl -s -o /dev/null -w '%{http_code}' https://takabailert.com/no-existe || echo 000)
[ "$NO_EXISTE" = "404" ] || fallo "smoke anti-espejo: /no-existe devolvio $NO_EXISTE (debe ser 404)"
REV_VIVA=$(curl -s https://takabailert.com/deploy-info.json | grep -o "$REV" || true)
[ -n "$REV_VIVA" ] || echo "AVISO: deploy-info.json aun no refleja $REV (cache en transito); reintenta el curl en unos segundos"

echo "== OK: https://takabailert.com sirve rev $REV =="
