#!/bin/bash
# deploy/cloud/conformidad.sh — [T-7.01] Censo de conformidad: ¿lo que está en código
# está en el sistema?
#
# SOLO LEE: el /api/health de la nube, `docker compose ps` en la instancia (por SSM,
# el mismo canal que deploy.sh, porque la instancia no tiene SSH), la cola de backfill,
# `terraform plan`, las alarmas en ALARM, la release activa del gabinete y el APK del
# Pixel. No despliega, no aplica, no reinicia nada; correrlo dos veces da lo mismo.
#
# Una línea por pieza:   VERDE|AMARILLO|ROJO|NO MEDIDO · <pieza> · <evidencia>
# y al final:            RESUMEN: n VERDE · n AMARILLO · n ROJO · n NO MEDIDO
#
# Sale 0 SOLO con todo VERDE. Un NO MEDIDO es un fallo —lo que no se midió no se
# aprueba; un fallback no puede ser «ok» (T-2.152)— salvo `--permitir-no-medido`, que
# lo deja fuera del código de salida pero NO lo pinta de verde. `--informe <ruta.md>`
# refresca una tabla entre `<!-- conformidad:inicio -->` y `<!-- conformidad:fin -->`
# (crea el fichero con una cabecera si no existe).
#
# Por qué `set -u` y no `-e`: cada pieza tiene que llegar a SU veredicto aunque la
# anterior haya fallado. Con `-e`, el primer tropiezo sería «no sé nada de lo demás».
set -u

uso() {
  cat <<'USO'
uso: bash deploy/cloud/conformidad.sh [--informe <ruta.md>] [--permitir-no-medido]

  --informe <ruta.md>    escribe/refresca la tabla entre los marcadores
                         <!-- conformidad:inicio --> / <!-- conformidad:fin -->
  --permitir-no-medido   un NO MEDIDO no cuenta para el código de salida (sigue
                         imprimiéndose como NO MEDIDO: no se pinta de verde)

entorno: AWS_PROFILE (takab-dev) · AWS_REGION (us-east-2) · TF_DEV (infra/terraform/envs/dev)
         TAKAB_CONSOLA_URL (por defecto, la salida `console_url` de terraform)
         TAKAB_PI_SSH_HOST (takab-pi5) · TAKAB_PI_PANEL_URL (http://<ip del host ssh>:8080)
requiere: jq aws terraform curl git · opcionales: uv ssh adb (sin ellos, NO MEDIDO)
USO
}

PWD_ORIGINAL="$PWD"
INFORME=""
PERMITIR_NO_MEDIDO=0
while [ $# -gt 0 ]; do
  case "$1" in
  --informe) INFORME="${2:?--informe exige una ruta}"; shift 2 ;;
  --informe=*) INFORME="${1#*=}"; shift ;;
  --permitir-no-medido) PERMITIR_NO_MEDIDO=1; shift ;;
  -h | --help) uso; exit 0 ;;
  *) echo "ERROR: argumento desconocido: $1" >&2; uso >&2; exit 2 ;;
  esac
done
case "$INFORME" in "" | /*) ;; *) INFORME="$PWD_ORIGINAL/$INFORME" ;; esac

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$AQUI/../.." && pwd)"
cd "$ROOT" || exit 2

for herramienta in jq aws terraform curl git; do
  command -v "$herramienta" >/dev/null 2>&1 || {
    echo "ERROR: falta '$herramienta' en el PATH; este censo no puede medir sin él." >&2
    exit 2
  }
done

AWS_PROFILE="${AWS_PROFILE:-takab-dev}"
AWS_REGION="${AWS_REGION:-us-east-2}"
TF_DEV="${TF_DEV:-infra/terraform/envs/dev}"
export AWS_PROFILE AWS_REGION

aws_cli() { aws --profile "$AWS_PROFILE" --region "$AWS_REGION" "$@"; }
tf_out() { terraform -chdir="$TF_DEV" output -raw "$1"; }
tf_json() { terraform -chdir="$TF_DEV" output -json "$1"; }

# --- Contabilidad ---------------------------------------------------------------
N_VERDE=0
N_AMARILLO=0
N_ROJO=0
N_NOMEDIDO=0
FILAS=()

# registrar <VERDE|AMARILLO|ROJO|NO MEDIDO> <pieza> <evidencia>
registrar() {
  local v="$1" pieza="$2" ev
  ev="$(printf '%s' "$3" | tr -s '\n\t' '  ')"
  case "$v" in
  VERDE) N_VERDE=$((N_VERDE + 1)) ;;
  AMARILLO) N_AMARILLO=$((N_AMARILLO + 1)) ;;
  ROJO) N_ROJO=$((N_ROJO + 1)) ;;
  "NO MEDIDO") N_NOMEDIDO=$((N_NOMEDIDO + 1)) ;;
  *) echo "BUG: veredicto desconocido '$v'" >&2; exit 3 ;;
  esac
  printf '%s · %s · %s\n' "$v" "$pieza" "$ev"
  FILAS+=("${v}"$'\t'"${pieza}"$'\t'"${ev}")
}

# --- Credenciales AWS: se comprueban UNA vez; sin ellas, las piezas de AWS son NO MEDIDO
AWS_OK=0
AWS_MOTIVO=""
if aws_cli sts get-caller-identity --query Account --output text >/dev/null 2>&1; then
  AWS_OK=1
else
  AWS_MOTIVO="sin credenciales AWS válidas para el perfil $AWS_PROFILE (aws sso logout && aws sso login --profile $AWS_PROFILE)"
fi

CONSOLA_URL="${TAKAB_CONSOLA_URL:-}"
CONSOLA_ORIGEN="TAKAB_CONSOLA_URL"
if [ -z "$CONSOLA_URL" ] && [ "$AWS_OK" = 1 ]; then
  CONSOLA_URL="$(tf_out console_url 2>/dev/null || true)"
  CONSOLA_ORIGEN="terraform output console_url"
fi
if [ -z "$CONSOLA_URL" ]; then
  # La URL del «Goal F0» del plan (PLAN-PROTOTIPO-FUNCIONAL.md §4): último recurso.
  CONSOLA_URL="https://16-58-11-196.sslip.io"
  CONSOLA_ORIGEN="valor por defecto del plan (terraform no contestó)"
fi
CONSOLA_URL="${CONSOLA_URL%/}"

# --- Estado compartido entre piezas ------------------------------------------------
SALUD=""            # /api/health de la nube (pieza 1 lo llena, pieza 2 lo lee)
SSM_OK=0            # ¿se pudo leer la instancia?
ENV_INSTANCIA=""    # nombres TAKAB_API_* presentes en /etc/takab/cloud.env de la instancia
TAG_INSTANCIA=""    # tag de TAKAB_CLOUD_IMAGE en /etc/takab/deploy.env de la instancia
BACKFILL_CORRE=0    # ¿el servicio backfill corre en la instancia?

# Servicios que el compose DEL REPO declara (awk y no `docker compose config`, que
# exigiría las variables de imagen que solo el despliegue conoce).
SERVICIOS_DECLARADOS="$(awk '
  /^services:/ { s = 1; next }
  /^[^ #]/     { s = 0 }
  s && /^  [A-Za-z0-9_.-]+:[ ]*$/ { sub(/^  /, ""); sub(/:.*/, ""); print }
' deploy/cloud/docker-compose.yml | tr '\n' ' ')"

# --- 1 · build ------------------------------------------------------------------------
pieza_build() {
  local pieza="build de la nube" url="$CONSOLA_URL/api/health" build head n tocados
  if ! SALUD="$(curl -fsS --max-time 8 "$url" 2>/dev/null)" || ! jq -e .build >/dev/null 2>&1 <<<"$SALUD"; then
    SALUD=""
    registrar "NO MEDIDO" "$pieza" "la API no contesta en $url ($CONSOLA_ORIGEN)"
    return
  fi
  build="$(jq -r .build <<<"$SALUD")"
  head="$(git rev-parse --short HEAD)"
  if [ "$build" = "$head" ]; then
    registrar VERDE "$pieza" "/api/health.build=$build == HEAD"
    return
  fi
  if ! git cat-file -e "${build}^{commit}" 2>/dev/null; then
    registrar ROJO "$pieza" "la nube corre $build y ese commit no está en este repo (HEAD $head): rama sin traer, o despliegue desde otro árbol"
    return
  fi
  n="$(git rev-list --count "${build}..HEAD")"
  if git diff --quiet "${build}..HEAD" -- . ':!takab-docs'; then
    registrar AMARILLO "$pieza" "nube $build, HEAD $head: $n commits por detrás, solo documentos (nada que la nube ejecute cambió)"
  elif git diff --quiet "${build}..HEAD" -- api web shared db deploy/cloud; then
    tocados="$(git diff --name-only "${build}..HEAD" -- . ':!takab-docs' | cut -d/ -f1 | sort -u | tr '\n' ' ')"
    registrar AMARILLO "$pieza" "nube $build, HEAD $head: $n commits por detrás; cambió ${tocados}— nada de lo que las imágenes de la nube copian (api/ web/ shared/ db/ deploy/cloud/)"
  else
    tocados="$(git diff --name-only "${build}..HEAD" -- api web shared db deploy/cloud | cut -d/ -f1-2 | sort -u | head -6 | tr '\n' ' ')"
    registrar ROJO "$pieza" "nube $build, HEAD $head: $n commits por detrás y cambió código que la nube ejecuta (${tocados}) → make cloud-images && make cloud-deploy (T-7.02 despliega)"
  fi
}

# --- 2 · esquema ---------------------------------------------------------------------
pieza_esquema() {
  local pieza="esquema de la nube" estado aplicada esperada ultima
  ultima="$(find api/migrations/versions -maxdepth 1 -name '[0-9][0-9][0-9][0-9]_*.py' -printf '%f\n' | sort | tail -1 | sed 's/\.py$//')"
  if [ -z "$SALUD" ]; then
    registrar "NO MEDIDO" "$pieza" "sin /api/health (pieza anterior); el repo espera $ultima"
    return
  fi
  estado="$(jq -r '.esquema.estado // "ausente"' <<<"$SALUD")"
  aplicada="$(jq -r '.esquema.aplicada // "?"' <<<"$SALUD")"
  esperada="$(jq -r '.esquema.esperada // "?"' <<<"$SALUD")"
  if [ "$estado" != "al_dia" ]; then
    registrar ROJO "$pieza" "estado=$estado aplicada=$aplicada esperada=$esperada (repo: $ultima) → el despliegue migra antes de levantar la API (make cloud-deploy)"
  elif [ "$esperada" != "$ultima" ]; then
    registrar AMARILLO "$pieza" "al_dia en $aplicada, pero el repo ya trae $ultima: la imagen desplegada no conoce esa migración → make cloud-images && make cloud-deploy"
  else
    registrar VERDE "$pieza" "estado=al_dia aplicada=$aplicada == última migración del repo ($ultima)"
  fi
}

# --- 3 · compose en la instancia -------------------------------------------------------
pieza_compose() {
  local pieza="servicios del compose en la instancia"
  local id ping cmd params cmd_id status="" salida ps_json corriendo estado faltan="" mal="" sobran n_decl svc
  n_decl="$(wc -w <<<"$SERVICIOS_DECLARADOS")"
  if [ "$AWS_OK" != 1 ]; then registrar "NO MEDIDO" "$pieza" "$AWS_MOTIVO"; return; fi
  if ! id="$(tf_out db_instance_id 2>/dev/null)" || [ -z "$id" ]; then
    registrar "NO MEDIDO" "$pieza" "terraform output db_instance_id no contestó"
    return
  fi
  ping="$(aws_cli ssm describe-instance-information --filters "Key=InstanceIds,Values=$id" \
    --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null || true)"
  if [ "$ping" != "Online" ]; then
    registrar "NO MEDIDO" "$pieza" "la instancia $id no está Online en SSM (PingStatus=${ping:-?}); ¿make cloud-start?"
    return
  fi
  # Lo mismo que haría un operador con el runbook (README §Operación), en una sola ida:
  # el ps de compose, los NOMBRES (no valores) de cloud.env y el tag de la imagen.
  cmd='cd /opt/takab/cloud && echo "::PS::" && docker compose --env-file /etc/takab/deploy.env ps -a --format json; echo "::ENV::"; grep -oE "^TAKAB_API_[A-Z0-9_]+=" /etc/takab/cloud.env | tr -d =; echo "::TAG::"; sed -n "s/^TAKAB_CLOUD_IMAGE=.*://p" /etc/takab/deploy.env'
  params="$(mktemp)"
  jq -n --arg c "$cmd" '{commands: [$c]}' >"$params"
  cmd_id="$(aws_cli ssm send-command --instance-ids "$id" --document-name AWS-RunShellScript \
    --comment "takab conformidad (solo lectura)" --parameters "file://$params" \
    --query Command.CommandId --output text 2>/dev/null || true)"
  rm -f "$params"
  if [ -z "$cmd_id" ]; then registrar "NO MEDIDO" "$pieza" "aws ssm send-command falló contra $id"; return; fi
  for _ in $(seq 1 20); do
    status="$(aws_cli ssm get-command-invocation --command-id "$cmd_id" --instance-id "$id" \
      --query Status --output text 2>/dev/null || true)"
    case "$status" in Success | Failed | Cancelled | TimedOut) break ;; esac
    sleep 3
  done
  if [ "$status" != "Success" ]; then
    registrar "NO MEDIDO" "$pieza" "el comando SSM $cmd_id terminó en '${status:-sin estado}'"
    return
  fi
  salida="$(aws_cli ssm get-command-invocation --command-id "$cmd_id" --instance-id "$id" \
    --query StandardOutputContent --output text)"
  SSM_OK=1
  ENV_INSTANCIA="$(awk '/^::ENV::/ { s = 1; next } /^::TAG::/ { s = 0 } s' <<<"$salida")"
  TAG_INSTANCIA="$(awk '/^::TAG::/ { s = 1; next } s' <<<"$salida" | head -1)"
  ps_json="$(awk '/^::PS::/ { s = 1; next } /^::ENV::/ { s = 0 } s' <<<"$salida")"
  # compose >= 2.21 emite un objeto JSON por línea; versiones anteriores, un array.
  corriendo="$(jq -rs '[.[] | if type == "array" then .[] else . end] | .[] | "\(.Service) \(.State)"' <<<"$ps_json" 2>/dev/null || true)"
  # shellcheck disable=SC2086  # la lista va separada por espacios a propósito
  for svc in $SERVICIOS_DECLARADOS; do
    estado="$(awk -v s="$svc" '$1 == s { print $2 }' <<<"$corriendo" | head -1)"
    if [ -z "$estado" ]; then
      faltan="$faltan $svc"
    elif [ "$estado" != "running" ]; then
      mal="$mal $svc=$estado"
    elif [ "$svc" = "backfill" ]; then
      BACKFILL_CORRE=1
    fi
  done
  sobran=""
  while read -r svc _; do
    [ -n "$svc" ] || continue
    case " $SERVICIOS_DECLARADOS" in *" $svc "*) ;; *) sobran="$sobran $svc" ;; esac
  done <<<"$corriendo"
  if [ -z "$faltan" ] && [ -z "$mal" ]; then
    registrar VERDE "$pieza" "$n_decl/$n_decl declarados corriendo (imagen :${TAG_INSTANCIA:-?})${sobran:+; en la instancia sobran:$sobran}"
  else
    registrar ROJO "$pieza" "declarados en deploy/cloud/docker-compose.yml y${faltan:+ SIN CONTENEDOR en la instancia:$faltan}${mal:+ con estado distinto de running:$mal} (imagen :${TAG_INSTANCIA:-?}) → make cloud-images && make cloud-deploy (T-7.02)"
  fi
}

# --- 4 · el test del censo --------------------------------------------------------------
pieza_test() {
  local pieza="test compose↔workers" salida rc resumen
  if ! command -v uv >/dev/null 2>&1; then registrar "NO MEDIDO" "$pieza" "falta uv"; return; fi
  # --noconftest: el conftest de api/tests aplica migraciones a un Postgres local antes
  # del primer test, y este test solo lee ficheros. Sin conftest corre en cualquier máquina.
  salida="$(cd api && timeout 180 uv run pytest -q --noconftest -p no:cacheprovider \
    tests/test_compose_cubre_los_workers.py 2>&1)"
  rc=$?
  resumen="$(tail -1 <<<"$salida")"
  if [ "$rc" -eq 0 ]; then
    registrar VERDE "$pieza" "pytest --noconftest api/tests/test_compose_cubre_los_workers.py: $resumen"
  else
    registrar ROJO "$pieza" "pytest rc=$rc: $resumen · $(grep -m2 -E '^(FAILED|ERROR)' <<<"$salida" | tr '\n' ' ')→ T-7.02"
  fi
}

# --- 5 · entorno requerido y banderas ---------------------------------------------------
pieza_env() {
  local pieza="entorno que la nube exige" requeridos origen faltan="" n
  requeridos="$(cd api && uv run python -c \
    'from takab_api.settings import REQUERIDOS_EN_PRODUCCION as R; print(" ".join(sorted(c.upper() for c in R)))' \
    2>/dev/null || true)"
  if [ -n "$requeridos" ]; then
    origen="Settings.REQUERIDOS_EN_PRODUCCION ($(wc -w <<<"$requeridos") nombres) + QUEUE_URL_BACKFILL/DLQ_URL_BACKFILL"
  else
    origen="solo QUEUE_URL_BACKFILL/DLQ_URL_BACKFILL (no se pudo importar takab_api.settings)"
  fi
  # La MISMA regla que api/tests/test_settings_produccion.py::_vars_del_despliegue —
  # sin anclar al inicio de línea—: takab-secrets.sh escribe sus nombres dentro de
  # un printf, no a columna cero. Anclado, DATABASE_URL salía en falso ROJO.
  # shellcheck disable=SC2086
  for n in $requeridos QUEUE_URL_BACKFILL DLQ_URL_BACKFILL; do
    grep -qE "TAKAB_API_${n}=" deploy/cloud/deploy.sh deploy/cloud/takab-secrets.sh || faltan="$faltan $n"
  done
  if [ -z "$faltan" ]; then
    registrar VERDE "$pieza" "todo en el heredoc de deploy.sh/takab-secrets.sh: $origen"
  else
    registrar ROJO "$pieza" "faltan en deploy.sh/takab-secrets.sh:$faltan ($origen)"
  fi
}

# pieza_bandera <NOMBRE sin prefijo> <quién decide / ficha>
pieza_bandera() {
  local n="$1" ficha="$2" pieza="bandera TAKAB_API_$1" en_deploy en_inst
  if grep -qE "TAKAB_API_${n}=" deploy/cloud/deploy.sh; then
    en_deploy="exportada en deploy.sh"
  else
    en_deploy="NO exportada en deploy.sh"
  fi
  if [ "$SSM_OK" = 1 ]; then
    if grep -qx "TAKAB_API_${n}" <<<"$ENV_INSTANCIA"; then
      en_inst="definida en /etc/takab/cloud.env de la instancia"
    else
      en_inst="ausente en /etc/takab/cloud.env de la instancia"
    fi
  else
    en_inst="instancia no medida"
  fi
  case "$en_deploy|$en_inst" in
  "exportada en deploy.sh|definida"*) registrar VERDE "$pieza" "$en_deploy · $en_inst" ;;
  "exportada en deploy.sh|ausente"*) registrar AMARILLO "$pieza" "$en_deploy · $en_inst → pendiente de desplegar" ;;
  "exportada en deploy.sh|"*) registrar AMARILLO "$pieza" "$en_deploy · $en_inst" ;;
  *) registrar AMARILLO "$pieza" "$en_deploy · $en_inst → la nube corre con el default de Settings ($ficha)" ;;
  esac
}

# --- 6 · cola de backfill ----------------------------------------------------------------
atributos_sqs() {
  aws_cli sqs get-queue-attributes --queue-url "$1" \
    --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
    --query Attributes --output json 2>/dev/null
}

pieza_cola() {
  local pieza="cola de backfill" q dlq a d visibles vuelo en_dlq
  if [ "$AWS_OK" != 1 ]; then registrar "NO MEDIDO" "$pieza" "$AWS_MOTIVO"; return; fi
  q="$(tf_json queue_urls 2>/dev/null | jq -r '.backfill // empty')"
  dlq="$(tf_json dlq_urls 2>/dev/null | jq -r '.backfill // empty')"
  if [ -z "$q" ] || [ -z "$dlq" ]; then
    registrar "NO MEDIDO" "$pieza" "terraform output queue_urls/dlq_urls sin la clave backfill"
    return
  fi
  a="$(atributos_sqs "$q")"
  d="$(atributos_sqs "$dlq")"
  if [ -z "$a" ] || [ -z "$d" ]; then registrar "NO MEDIDO" "$pieza" "sqs get-queue-attributes falló"; return; fi
  visibles="$(jq -r .ApproximateNumberOfMessages <<<"$a")"
  vuelo="$(jq -r .ApproximateNumberOfMessagesNotVisible <<<"$a")"
  en_dlq="$(jq -r .ApproximateNumberOfMessages <<<"$d")"
  if [ "$visibles" = 0 ] && [ "$en_dlq" = 0 ]; then
    registrar VERDE "$pieza" "${q##*/}: 0 visibles ($vuelo en vuelo) · ${dlq##*/}: 0"
  elif [ "$en_dlq" = 0 ] && [ "$BACKFILL_CORRE" = 1 ]; then
    registrar AMARILLO "$pieza" "${q##*/}: $visibles visibles, $vuelo en vuelo, con el consumidor ARRIBA en la instancia (drenando) · DLQ 0"
  else
    registrar ROJO "$pieza" "${q##*/}: $visibles visibles, $vuelo en vuelo · ${dlq##*/}: $en_dlq → sin consumidor hasta que el servicio backfill corra en la nube (T-7.02); si la DLQ tiene mensajes, mirarlos antes de purgar"
  fi
}

# --- 7 · terraform plan -----------------------------------------------------------------
pieza_terraform() {
  local pieza="terraform plan" salida rc linea
  if [ "$AWS_OK" != 1 ]; then registrar "NO MEDIDO" "$pieza" "$AWS_MOTIVO"; return; fi
  if [ ! -f "$TF_DEV/local.auto.tfvars" ]; then
    registrar "NO MEDIDO" "$pieza" "falta $TF_DEV/local.auto.tfvars (gitignored): sin él todo lo que lleva count evalúa a cero y el plan propondría DESTRUIR SES, DKIM, DMARC y la consola (medido el 2026-08-27); planifica desde tu árbol de siempre"
    return
  fi
  salida="$(timeout 300 terraform -chdir="$TF_DEV" plan -lock=false -detailed-exitcode -input=false -no-color -compact-warnings 2>&1)"
  rc=$?
  case "$rc" in
  0) registrar VERDE "$pieza" "sin cambios: código == estado == AWS" ;;
  2)
    linea="$(grep -m1 -E '^Plan:' <<<"$salida")"
    registrar ROJO "$pieza" "${linea:-hay cambios sin aplicar} → mirar el plan y aplicar con make cloud-apply (decisión humana, no de este script)"
    ;;
  *)
    linea="$(grep -m1 -iE 'error' <<<"$salida" | cut -c1-160)"
    registrar "NO MEDIDO" "$pieza" "terraform plan rc=$rc: ${linea:-sin detalle}"
    ;;
  esac
}

# --- 8 · alarmas -------------------------------------------------------------------------
pieza_alarmas() {
  local pieza="alarmas de CloudWatch" en_alarm
  if [ "$AWS_OK" != 1 ]; then registrar "NO MEDIDO" "$pieza" "$AWS_MOTIVO"; return; fi
  if ! en_alarm="$(aws_cli cloudwatch describe-alarms --state-value ALARM --query 'MetricAlarms[].AlarmName' --output text 2>/dev/null)"; then
    registrar "NO MEDIDO" "$pieza" "cloudwatch describe-alarms falló"
    return
  fi
  en_alarm="$(tr '\t' ' ' <<<"$en_alarm" | sed 's/^None$//')"
  if [ -z "${en_alarm// /}" ]; then
    registrar VERDE "$pieza" "ninguna alarma en ALARM"
  else
    registrar ROJO "$pieza" "en ALARM: $en_alarm → atender antes de la demo (una alarma que grita durante la demo es la que nadie mira)"
  fi
}

# --- 9 y 10 · el gabinete ------------------------------------------------------------------
PI_HOST_ALIAS="${TAKAB_PI_SSH_HOST:-takab-pi5}"
PI_IP="$(ssh -G "$PI_HOST_ALIAS" 2>/dev/null | awk '$1 == "hostname" { print $2 }')"
PI_IP="${PI_IP:-192.168.1.105}"
PI_PANEL="${TAKAB_PI_PANEL_URL:-http://$PI_IP:8080}"

pieza_pi_release() {
  local pieza="release activa del Pi" enlace id sha sucio="" head cambiados ultimo
  if ! command -v ssh >/dev/null 2>&1; then registrar "NO MEDIDO" "$pieza" "falta ssh"; return; fi
  # deploy/edge/deploy.sh + canary.sh: /opt/takab/edge es un SYMLINK a
  # /opt/takab/releases/<YYYYMMDDTHHMMSSZ>-<sha7>[-dirty]/edge; lo repunta canary.sh.
  if ! enlace="$(timeout 12 ssh -o ConnectTimeout=5 -o BatchMode=yes "$PI_HOST_ALIAS" 'readlink /opt/takab/edge' 2>/dev/null)"; then
    registrar "NO MEDIDO" "$pieza" "$PI_HOST_ALIAS ($PI_IP) inalcanzable desde $(hostname -I 2>/dev/null | awk '{ print $1 }'): equipo fuera de 192.168.1.0/24"
    return
  fi
  if [ -z "$enlace" ]; then
    registrar AMARILLO "$pieza" "/opt/takab/edge no es un symlink: el gabinete no está en el layout A/B (T-2.70); lo migra deploy/edge/deploy.sh"
    return
  fi
  id="$(basename "$(dirname "$enlace")")"
  case "$id" in
  heredada-*) registrar AMARILLO "$pieza" "release $id: árbol heredado del layout anterior, versión desconocida → bash deploy/edge/deploy.sh"; return ;;
  esac
  sha="${id#*-}"
  case "$sha" in *-dirty) sucio=" (desplegada desde un árbol SUCIO: no es un commit reproducible)"; sha="${sha%-dirty}" ;; esac
  head="$(git rev-parse --short HEAD)"
  if [ "$sha" = "$head" ] && [ -z "$sucio" ]; then
    registrar VERDE "$pieza" "release $id == HEAD"
    return
  fi
  if ! git cat-file -e "${sha}^{commit}" 2>/dev/null; then
    registrar ROJO "$pieza" "release $id: el commit $sha no está en este repo$sucio"
    return
  fi
  # Lo que el gabinete EJECUTA: el paquete, el despliegue, las unidades, sus dependencias y los
  # contratos compartidos. edge/tests no corre en el Pi: un test nuevo no hace vieja a la release.
  if git diff --quiet "${sha}..HEAD" -- edge/takab_edge deploy/edge edge/systemd edge/pyproject.toml edge/uv.lock shared/schemas shared/glossary; then
    if [ -n "$sucio" ]; then
      registrar AMARILLO "$pieza" "release $id$sucio; desde $sha no cambió nada de lo que el gabinete ejecuta"
    else
      registrar VERDE "$pieza" "release $id: nada de lo que el gabinete ejecuta cambió desde $sha (HEAD $head)"
    fi
  else
    cambiados="$(git diff --name-only "${sha}..HEAD" -- edge/takab_edge deploy/edge edge/systemd edge/pyproject.toml edge/uv.lock shared/schemas shared/glossary | wc -l)"
    ultimo="$(git log -1 --format='%h %cI' -- edge/takab_edge deploy/edge edge/systemd edge/pyproject.toml edge/uv.lock shared/schemas shared/glossary)"
    registrar ROJO "$pieza" "release $id$sucio; desde $sha cambiaron $cambiados ficheros de lo que el gabinete ejecuta (último: $ultimo) → bash deploy/edge/deploy.sh"
  fi
}

pieza_pi_status() {
  local pieza="modo prueba del Pi" st activo restante audio
  if ! st="$(curl -fsS --max-time 3 "$PI_PANEL/api/status" 2>/dev/null)" || ! jq -e . >/dev/null 2>&1 <<<"$st"; then
    registrar "NO MEDIDO" "$pieza" "$PI_PANEL/api/status no contesta (equipo fuera de la LAN del gabinete)"
    return
  fi
  activo="$(jq -r '.test_mode.active // "desconocido"' <<<"$st")"
  restante="$(jq -r '.test_mode.remaining_s // "?"' <<<"$st")"
  audio="$(jq -r 'if .audio == null then "audio: sección ausente" else "audio.profile: " + ((.audio.profile.name // .audio.profile.id // (.audio.profile | tostring)) | tostring) end' <<<"$st" 2>/dev/null || echo "audio: ilegible")"
  case "$activo" in
  false) registrar VERDE "$pieza" "test_mode.active=false · $audio" ;;
  true) registrar ROJO "$pieza" "test_mode.active=true (remaining_s=$restante) → desarmar el modo prueba en el panel antes de la demo · $audio" ;;
  *) registrar "NO MEDIDO" "$pieza" "/api/status sin test_mode.active" ;;
  esac
}

# --- 11 · el APK del Pixel ---------------------------------------------------------------
pieza_apk() {
  local pieza="APK del Pixel" estado dump ver upd ts_apk ts_mob ultimo
  if ! command -v adb >/dev/null 2>&1; then registrar "NO MEDIDO" "$pieza" "falta adb"; return; fi
  estado="$(timeout 10 adb get-state 2>/dev/null || true)"
  if [ "$estado" != "device" ]; then
    registrar "NO MEDIDO" "$pieza" "sin teléfono por USB (adb get-state: ${estado:-nada}); conecta el Pixel con depuración USB"
    return
  fi
  # SOLO estos dos comandos: el teléfono es personal. No se vuelca nada más.
  dump="$(timeout 20 adb shell dumpsys package com.takab.ailert 2>/dev/null | tr -d '\r')"
  ver="$(grep -m1 -oE 'versionName=\S+' <<<"$dump" | cut -d= -f2)"
  upd="$(grep -m1 -oE 'lastUpdateTime=.*' <<<"$dump" | cut -d= -f2-)"
  if [ -z "$upd" ]; then
    registrar ROJO "$pieza" "com.takab.ailert no está instalado en el teléfono → instalar (mobile/: npx expo run:android)"
    return
  fi
  ts_apk="$(date -d "$upd" +%s 2>/dev/null || echo 0)"
  ts_mob="$(git log -1 --format=%ct -- mobile)"
  ultimo="$(git log -1 --format='%h %cI' -- mobile)"
  # No hay sha embebido en el APK: la fecha de instalación frente al último commit de
  # mobile/ es el único proxy honesto. La hora del teléfono se lee como hora local.
  if [ "$ts_apk" -ge "$ts_mob" ]; then
    registrar VERDE "$pieza" "com.takab.ailert ${ver:-?} instalado $upd ≥ último cambio de mobile/ ($ultimo)"
  else
    registrar AMARILLO "$pieza" "APK ${ver:-?} instalado $upd es ANTERIOR al último cambio de mobile/ ($ultimo) → reconstruir e instalar en el Pixel (mobile/: npx expo run:android)"
  fi
}

# --- Informe -----------------------------------------------------------------------------
escribir_informe() {
  local ruta="$1" tmp fila v pieza ev emoji
  tmp="$(mktemp)"
  {
    echo "<!-- conformidad:inicio -->"
    echo "_Generado por \`deploy/cloud/conformidad.sh\` (\`make cloud-conformidad\`) el $(date -u +%Y-%m-%dT%H:%M:%SZ) · HEAD \`$(git rev-parse --short HEAD)\` · consola $CONSOLA_URL. Se regenera entero: no editar entre los marcadores._"
    echo
    echo "| Pieza | Veredicto | Evidencia |"
    echo "|---|---|---|"
    for fila in "${FILAS[@]}"; do
      IFS=$'\t' read -r v pieza ev <<<"$fila"
      case "$v" in VERDE) emoji="🟢" ;; AMARILLO) emoji="🟡" ;; ROJO) emoji="🔴" ;; *) emoji="⚪" ;; esac
      ev="${ev//|/\\|}"
      echo "| $pieza | $emoji $v | $ev |"
    done
    echo
    echo "**RESUMEN:** $N_VERDE VERDE · $N_AMARILLO AMARILLO · $N_ROJO ROJO · $N_NOMEDIDO NO MEDIDO"
    echo "<!-- conformidad:fin -->"
  } >"$tmp"
  if [ ! -f "$ruta" ]; then
    {
      cat <<'CAB'
# Informe de conformidad · demo TAKAB Ailert

> [T-7.01] «Lo que está en código está en el sistema». La tabla la genera
> `make cloud-conformidad` (`deploy/cloud/conformidad.sh`): cada fila sale de un
> comando, no de una lectura. 🟢 VERDE · 🟡 AMARILLO · 🔴 ROJO (nombra la ficha o el
> comando que lo cierra) · ⚪ NO MEDIDO (no se pudo preguntar; no es verde). Lo que
> hay entre los marcadores se regenera entero en cada corrida.

CAB
      cat "$tmp"
    } >"$ruta"
  elif grep -q '<!-- conformidad:inicio -->' "$ruta" && grep -q '<!-- conformidad:fin -->' "$ruta"; then
    awk -v bloque="$tmp" '
      /<!-- conformidad:inicio -->/ { while ((getline l < bloque) > 0) print l; skip = 1; next }
      /<!-- conformidad:fin -->/    { skip = 0; next }
      !skip
    ' "$ruta" >"$ruta.tmp" && mv "$ruta.tmp" "$ruta"
  else
    { echo; cat "$tmp"; } >>"$ruta"
  fi
  rm -f "$tmp"
  echo "informe: $ruta"
}

# --- Main --------------------------------------------------------------------------------
echo "conformidad · HEAD $(git rev-parse --short HEAD) · $(date -u +%Y-%m-%dT%H:%M:%SZ) · perfil $AWS_PROFILE · consola $CONSOLA_URL ($CONSOLA_ORIGEN)"
pieza_build
pieza_esquema
pieza_compose
pieza_test
pieza_env
pieza_bandera PUSH_FCM_APPLICATION_ARN "push real por FCM: T-7.03"
pieza_bandera OPENROUTER_ENABLED "decisión de la demo"
pieza_bandera CONSOLE_SCOPE_ENFORCED "alcance por rol: T-7.06"
pieza_cola
pieza_terraform
pieza_alarmas
pieza_pi_release
pieza_pi_status
pieza_apk

echo "RESUMEN: $N_VERDE VERDE · $N_AMARILLO AMARILLO · $N_ROJO ROJO · $N_NOMEDIDO NO MEDIDO"
[ -n "$INFORME" ] && escribir_informe "$INFORME"

RC=0
if [ "$N_ROJO" -ne 0 ] || [ "$N_AMARILLO" -ne 0 ]; then RC=1; fi
if [ "$N_NOMEDIDO" -ne 0 ] && [ "$PERMITIR_NO_MEDIDO" != 1 ]; then RC=1; fi
if [ "$RC" -eq 0 ]; then
  echo "SALIDA 0: todo VERDE${N_NOMEDIDO:+ }$([ "$N_NOMEDIDO" -ne 0 ] && echo "(con $N_NOMEDIDO NO MEDIDO tolerados por --permitir-no-medido)")"
else
  echo "SALIDA 1: solo todo VERDE devuelve 0$([ "$N_NOMEDIDO" -ne 0 ] && [ "$PERMITIR_NO_MEDIDO" != 1 ] && echo "; los NO MEDIDO cuentan como fallo salvo --permitir-no-medido")"
fi
exit "$RC"
