#!/bin/bash
# deploy/cloud/conformidad.sh — [T-7.01] Censo de conformidad: ¿lo que está en código
# está en el sistema?
#
# SOLO LEE: el /api/health de la nube, `docker compose ps` en la instancia (por SSM,
# el mismo canal que deploy.sh, porque la instancia no tiene SSH), la cola de backfill,
# `terraform plan`, las alarmas en ALARM, la release activa del gabinete, el APK del
# Pixel y —desde T-7.26— la EXISTENCIA del secreto de la capa narrativa y el permiso
# del rol de la instancia para leerlo (`describe-secret` y la política del rol; jamás
# `get-secret-value`). No despliega, no aplica, no reinicia nada; correrlo dos veces
# da lo mismo.
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

# [T-7.26] El censo de banderas se DERIVA de deploy.sh; ver la cabecera de este
# fichero y la de banderas.sh.
# shellcheck source=banderas.sh
. "$AQUI/banderas.sh"

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

# [T-7.26] aws_medido = aws_cli, pero SEPARANDO el fallo del resultado: deja la salida
# en AWS_SALIDA, el stderr en AWS_ERROR y devuelve el rc real. Existe porque el patrón
# `$(aws_cli ... 2>/dev/null || true)` borra la diferencia entre «lo pregunté y no hay»
# y «no pude preguntarlo», y esa diferencia es un veredicto entero.
AWS_SALIDA=""
AWS_ERROR=""
aws_medido() {
  local f rc
  f="$(mktemp)"
  AWS_SALIDA="$(aws_cli "$@" 2>"$f")"
  rc=$?
  AWS_ERROR="$(cat "$f")"
  rm -f "$f"
  return "$rc"
}

# La evidencia de un NO MEDIDO, en UN solo sitio: las llamadas que pueden no contestar
# tienen que decir todas lo mismo —qué no se pudo preguntar, con qué error, y que eso
# NO es la acusación—, o acabarán diciendo cosas distintas y alguna volverá a sonar a
# culpa. No receta `make cloud-apply` a propósito: un apply no arregla unas
# credenciales caducadas ni un perfil que no puede leer IAM.
sin_medir() { # <orden> <error> -> evidencia
  printf 'no se pudo PREGUNTAR «aws %s»: %s · esto NO dice que el permiso falte, dice que no se midió → refresca las credenciales (aws sso logout && aws sso login) y comprueba que el perfil pueda LEER iam/ec2' \
    "$1" "$(printf '%s' "${2:-sin detalle}" | head -c 160)"
}
tf_out() { terraform -chdir="$TF_DEV" output -raw "$1"; }
tf_json() { terraform -chdir="$TF_DEV" output -json "$1"; }

# Gemelo de `aws_medido` para terraform, y existe por la misma razón: `tf_out` a secas
# devuelve el mismo fallo cuando la salida NO ESTÁ DECLARADA (que es una acusación
# legítima: el despliegue abortaría) que cuando terraform no pudo ni arrancar —sin
# `init`, sin estado, con el estado bloqueado o sin credenciales—, que no acusa a nadie.
# Mezclarlos es la misma falsa alarma que este fichero acaba de cerrar para IAM, un tramo
# antes: un censo que acusa de lo que no comprobó entrena a ignorar el rojo.
#
# `TF_SALIDA` trae el valor y `TF_ERROR` el stderr; el código de retorno es el de
# terraform. Quien llama decide, y para decidir mira si terraform llegó a hablar de la
# salida (la dice por su nombre) o se quedó antes.
TF_SALIDA=""
TF_ERROR=""
tf_medido() {
  local f rc
  f="$(mktemp)"
  # Pasa por `tf_out` a propósito: es la costura que el arnés de pruebas sustituye por
  # un doble. Llamar aquí a `terraform` directamente dejaría este camino sin poder
  # ejercerse, y lo que no se puede ejercer no está defendido.
  TF_SALIDA="$(tf_out "$1" 2>"$f")"
  rc=$?
  TF_ERROR="$(cat "$f")"
  rm -f "$f"
  return "$rc"
}

# ¿El fallo de `tf_medido` fue «esa salida no existe» o «no pude preguntar»? Terraform
# nombra la salida cuando la buscó y no estaba; si no llegó ahí, el mensaje habla de
# otra cosa (init, backend, lock, credenciales).
# ⚠️ En varias líneas y con la llave a columna cero A PROPÓSITO: el arnés recorta
# funciones por nombre y corta en el primer `^}$`, así que una función de una sola línea
# se lleva por delante todo lo que venga detrás hasta la siguiente llave — medido, se
# tragó el `registrar` del doble y la escena entera dejó de medir.
tf_falta_la_salida() {
  printf '%s' "$TF_ERROR" | grep -qiE "output .*not found|no outputs found"
}

# --- Contabilidad ---------------------------------------------------------------
N_VERDE=0
N_AMARILLO=0
N_ROJO=0
N_NOMEDIDO=0
FILAS=()

# registrar <VERDE|AMARILLO|ROJO|NO MEDIDO> <pieza> <evidencia>
registrar() {
  local v="$1" pieza="$2" ev
  # La evidencia se aplana Y se despinta: varias piezas citan la salida de otra
  # herramienta (pytest, terraform) que colorea cuando cree que hay terminal, y
  # esos escapes acababan CRUDOS en la tabla del informe — ilegibles en markdown
  # y capaces de romper una celda si traen el separador dentro.
  ev="$(printf '%s' "$3" | tr -s '\n\t' '  ' | sed -E 's/\x1B\[[0-9;]*[A-Za-z]//g')"
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
AWS_CUENTA=""
# La cuenta ya no se tira: es lo que hace comprobable un respaldo por etiqueta («¿la
# instancia que encontré es de ESTE entorno o de otra cuenta?»), y se pregunta igual.
if AWS_CUENTA="$(aws_cli sts get-caller-identity --query Account --output text 2>/dev/null)" &&
  [ -n "$AWS_CUENTA" ]; then
  AWS_OK=1
else
  AWS_CUENTA=""
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

# --- La instancia de la nube: se resuelve UNA vez y se dice POR QUÉ CAMINO ----------
# Dos piezas necesitan saber qué máquina mirar —`pieza_compose` y, para dar con el rol,
# `pieza_secreto_ia`— y las dos se lo preguntaban solo a terraform. Medido el
# 2026-09-22 en la máquina del operador: con la caché de SSO rancia, `terraform
# -chdir=… output -raw db_instance_id` muere con «InvalidGrantException» mientras
# `aws sts get-caller-identity` y `aws ec2 describe-instances` contestan en segundos
# con las MISMAS credenciales. Un único token caducado del proveedor de terraform
# dejaba sin medir la instancia entera y con ella las banderas: el censo pasaba de
# «18 VERDE · 1 NO MEDIDO» a «6 VERDE · 8 AMARILLO · 5 NO MEDIDO», y un instrumento
# ciego se lee como un sistema enfermo.
#
# Terraform SIGUE siendo la fuente preferente, y no por costumbre: es la única que
# sabe cuál es la instancia de ESTE entorno. El respaldo por etiqueta entra solo
# cuando terraform no contesta, y con dos condiciones que son las que impiden que
# «cómo se encuentra» cambie «qué se mide»:
#   · la etiqueta NO se teclea aquí: se lee del propio terraform que crea la instancia
#     (`tags = { Name = … }` de modules/database). Un literal en este fichero
#     divergiría el día que el módulo la renombre, y entonces mediríamos otra máquina
#     —o ninguna— sin enterarnos.
#   · si la etiqueta la llevan DOS instancias RUNNING, eso no es una elección: es un
#     NO MEDIDO con su evidencia. Quedarse con la primera sería inventar.
# Y el camino se DECLARA en la evidencia de la pieza: sin eso, quien lea el informe la
# próxima vez no puede saber si el censo midió la instancia correcta.
INSTANCIA_ID=""     # la instancia de la nube, o vacío si no se pudo resolver
INSTANCIA_ORIGEN="" # por qué camino se encontró; va en la evidencia
INSTANCIA_MOTIVO="" # por qué NO hay instancia, cuando no la hay
TF_VIVO=1           # ¿terraform llega siquiera a contestar en esta máquina? (0 = no)
TF_MOTIVO=""        # y con qué error se quedó fuera

# El nombre que terraform le pone a la instancia, leído de terraform. Vacío si el
# módulo deja de declararlo con esa forma: entonces el respaldo no adivina, se calla.
etiqueta_de_la_instancia() {
  sed -n 's/^[[:space:]]*Name[[:space:]]*=[[:space:]]*"\(takab-[a-z0-9-]*-db\)"[[:space:]]*$/\1/p' \
    infra/terraform/modules/database/main.tf 2>/dev/null | head -1
}

resolver_instancia() {
  local tag ids n razon
  if tf_medido db_instance_id; then
    if [ -n "$TF_SALIDA" ]; then
      INSTANCIA_ID="$TF_SALIDA"
      INSTANCIA_ORIGEN="terraform output db_instance_id"
      return 0
    fi
    razon="terraform publica db_instance_id VACÍO"
  elif tf_falta_la_salida; then
    razon="el terraform no publica la salida db_instance_id"
  else
    # Terraform no llegó ni a mirar la salida: init, backend, lock o credenciales. Se
    # anota UNA vez aquí para que las piezas que vienen detrás no acusen al terraform
    # de lo que no han comprobado (ver `pieza_bandera`, clase tf).
    TF_VIVO=0
    TF_MOTIVO="$(printf '%s' "${TF_ERROR:-sin detalle}" | tr -s '\n\t' '  ' | head -c 160)"
    razon="terraform no contesta en esta máquina ($TF_MOTIVO)"
  fi
  tag="$(etiqueta_de_la_instancia)"
  if [ -z "$tag" ]; then
    INSTANCIA_MOTIVO="$razon, y el respaldo por etiqueta no sabe qué buscar: infra/terraform/modules/database/main.tf ya no declara un tag Name «takab-…-db»"
    return 1
  fi
  if ! aws_medido ec2 describe-instances \
    --filters "Name=tag:Name,Values=$tag" "Name=instance-state-name,Values=running" \
    --query 'Reservations[].Instances[].InstanceId' --output text; then
    INSTANCIA_MOTIVO="$razon, y $(sin_medir "ec2 describe-instances --filters Name=tag:Name,Values=$tag" "$AWS_ERROR")"
    return 1
  fi
  ids="$(tr -s '\t\n ' ' ' <<<"$AWS_SALIDA" | sed 's/^ //; s/ $//')"
  [ "$ids" = None ] && ids=""
  n="$(wc -w <<<"$ids")"
  if [ "$n" -eq 1 ]; then
    INSTANCIA_ID="$ids"
    INSTANCIA_ORIGEN="la etiqueta Name=$tag en la cuenta ${AWS_CUENTA:-?} ($AWS_REGION), porque $razon"
    return 0
  fi
  if [ "$n" -eq 0 ]; then
    INSTANCIA_MOTIVO="$razon, y NINGUNA instancia RUNNING lleva la etiqueta Name=$tag en la cuenta ${AWS_CUENTA:-?} ($AWS_REGION)"
  else
    INSTANCIA_MOTIVO="$razon, y la etiqueta Name=$tag la llevan $n instancias RUNNING ($ids) en la cuenta ${AWS_CUENTA:-?}: elegir una sería inventar, no medir"
  fi
  return 1
}

if [ "$AWS_OK" = 1 ]; then
  resolver_instancia || true
else
  INSTANCIA_MOTIVO="$AWS_MOTIVO"
fi

# --- Estado compartido entre piezas ------------------------------------------------
SALUD=""            # /api/health de la nube (pieza 1 lo llena, pieza 2 lo lee)
SSM_OK=0            # ¿se pudo leer la instancia?
ENV_INSTANCIA=""    # una linea «NOMBRE clase huella» por TAKAB_API_* de /etc/takab/cloud.env
                    # (clase: true|false|vacio|con-valor; la huella, sha256 corto: ver pieza_compose)
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
  # Estos dos casos eran AMARILLO —y un AMARILLO devuelve SALIDA 1— hasta el
  # 2026-09-22. Decían lo contrario que el otro instrumento que hace ESTA MISMA
  # pregunta con ESTA MISMA lista de rutas: `deploy/demo/goal-presentacion.sh` (A2)
  # sourcea `rutas_que_llegan_a_la_nube` de aquí y, con el diff vacío, escribe en verde
  # «TODO lo del repositorio está en la nube». Medido con f63b38b..db6684c (la nube
  # contra HEAD): el diff sobre las rutas que viajan da rc=0, o sea A2 ✓ y esta pieza
  # 🟡 sobre el mismo hecho. No divergían las listas —se comparten a propósito—, sino
  # los VEREDICTOS, que es peor porque no hay nada que lo vigile.
  #
  # Se alinea con A2 y no al revés porque A2 contesta la pregunta que este censo se
  # hace en su primera línea: ¿lo que está en código está en el sistema? Si nada de lo
  # que la nube ejecuta cambió, la respuesta es sí. Además el amarillo era ESTRUCTURAL:
  # con un solo commit de documentos por delante de la etiqueta ya no había forma de
  # que `make cloud-conformidad` devolviera 0, y un color que nunca se puede apagar es
  # exactamente lo que enseña al operador a ignorarlo. La evidencia no se toca: sigue
  # diciendo cuántos commits de retraso hay y qué cambió. El tercer caso —cambió código
  # que la nube ejecuta— sigue ROJO.
  # shellcheck disable=SC2046  # la lista va sin comillas a propósito: son rutas
  if git diff --quiet "${build}..HEAD" -- . ':!takab-docs'; then
    registrar VERDE "$pieza" "nube $build, HEAD $head: $n commits por detrás, solo documentos (nada que la nube ejecute cambió)"
  elif git diff --quiet "${build}..HEAD" -- $(rutas_que_llegan_a_la_nube); then
    tocados="$(git diff --name-only "${build}..HEAD" -- . ':!takab-docs' | cut -d/ -f1 | sort -u | tr '\n' ' ')"
    registrar VERDE "$pieza" "nube $build, HEAD $head: $n commits por detrás; cambió ${tocados}— nada de lo que llega a la nube (ver rutas_que_llegan_a_la_nube)"
  else
    tocados="$(git diff --name-only "${build}..HEAD" -- $(rutas_que_llegan_a_la_nube) | cut -d/ -f1-2 | sort -u | head -6 | tr '\n' ' ')"
    registrar ROJO "$pieza" "nube $build, HEAD $head: $n commits por detrás y cambió código que la nube ejecuta (${tocados}) → make cloud-images && make cloud-deploy (T-7.02 despliega)"
  fi
}

# Qué cambios OBLIGAN a volver a desplegar la nube. `api/ web/ shared/ db/` los copian
# los Dockerfiles; de `deploy/cloud/` **no llega todo**, y tratarlo entero como «código
# que la nube ejecuta» pedía un despliegue por tocar este mismo censo. Eso es lo que
# entrena a ignorar un rojo: un censo que acusa de lo que no comprobó.
#
# Lo que viaja se DERIVA en vez de enumerarse —un censo a mano acaba divergiendo—:
#   · de las propias líneas `b64 deploy/cloud/…` de deploy.sh, que es literalmente lo
#     que el despliegue empuja a la instancia;
#   · de lo que la imagen de la consola nombra (`Caddyfile`, y el Dockerfile mismo);
#   · más `deploy.sh`, porque cambiar al que despliega cambia el despliegue.
# Quedan fuera `conformidad.sh`, `banderas.sh`, `medir-latencia-ia.sh` y el README, que
# corren desde la máquina del operador y no tocan la instancia.
#
# ⚠️ Con RED: si la derivación sale vacía —porque deploy.sh cambió de forma— se vuelve
# a `deploy/cloud` entero. El error caro aquí es el de MENOS (dar por inofensivo un
# cambio que sí viaja), no el de más.
rutas_que_llegan_a_la_nube() {
  local d
  d="$(
    sed -n 's#.*b64 \(deploy/cloud/[A-Za-z0-9._-]*\).*#\1#p' deploy/cloud/deploy.sh 2>/dev/null
    grep -o 'deploy/cloud/[A-Za-z0-9._-]*' deploy/cloud/console.Dockerfile 2>/dev/null
  )"
  if [ -z "$d" ]; then
    echo "api web shared db deploy/cloud"
    return
  fi
  printf '%s\n' api web shared db deploy/cloud/deploy.sh $d | sort -u | tr '\n' ' '
  # Y las EXCLUSIONES, que también se derivan. Un directorio `tests/` bajo una de
  # las raíces sólo queda fuera si NINGÚN Dockerfile lo copia — no por llamarse
  # `tests`. La diferencia es real y se mide:
  #
  #   · `api/Dockerfile` copia `api/src`, `api/migrations`, `api/pyproject.toml` y
  #     `api/alembic.ini`. **`api/tests` NO entra en la imagen**, así que tocarlo
  #     no cambia lo que la nube ejecuta y no puede pedir un despliegue.
  #   · `console.Dockerfile` hace `COPY web web` — los tests del web SÍ viajan, y
  #     además el build los typechequea, o sea que un cambio ahí puede romper la
  #     imagen. Excluirlos con un `**/tests` a lo bruto sería el error caro: el de
  #     MENOS, dar por inofensivo un cambio que sí viaja.
  local raiz copiados cand c copiado
  copiados="$(grep -hoE '^COPY[[:space:]]+[^[:space:]]+' api/Dockerfile deploy/cloud/console.Dockerfile 2>/dev/null |
    awk '{print $2}')"
  for raiz in api web shared; do
    cand="$raiz/tests"
    [ -d "$cand" ] || continue
    # ⚠️ Por ANCESTRO, no por prefijo de cadena. `COPY web web` copia `web/tests`
    # aunque no lo nombre, y una comparación ingenua (`grep "^web/tests"`) no lo ve
    # y lo excluiría. Hoy `web/tests` no existe, así que la versión ingenua acertaba
    # POR CASUALIDAD — y el día que alguien meta ahí los Playwright, el censo daría
    # por inofensivo un cambio que sí viaja en la imagen. Ése es el error caro.
    copiado=0
    while IFS= read -r c; do
      [ -n "$c" ] || continue
      c="${c%/}"
      case "$cand/" in "$c"/*) copiado=1; break ;; esac
    done <<<"$copiados"
    [ "$copiado" -eq 1 ] || printf ':!%s ' "$cand"
  done
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
  if [ -z "$INSTANCIA_ID" ]; then
    registrar "NO MEDIDO" "$pieza" "$INSTANCIA_MOTIVO"
    return
  fi
  id="$INSTANCIA_ID"
  ping="$(aws_cli ssm describe-instance-information --filters "Key=InstanceIds,Values=$id" \
    --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null || true)"
  if [ "$ping" != "Online" ]; then
    registrar "NO MEDIDO" "$pieza" "la instancia $id no está Online en SSM (PingStatus=${ping:-?}); ¿make cloud-start?"
    return
  fi
  # Lo mismo que haría un operador con el runbook (README §Operación), en una sola ida:
  # el ps de compose, el estado de cada TAKAB_API_* de cloud.env y el tag de la imagen.
  #
  # [T-7.26] De cloud.env NO vuelve ni un valor. Hasta esta ficha volvían solo los
  # NOMBRES, y eso hacía el censo ciego a lo único que importa: una bandera puesta a
  # `false` en la instancia salía tan verde como puesta a `true` — el defecto de
  # T-7.06 que este censo cita como razón de existir—, y el slug del modelo vacío
  # también. Ahora la instancia CLASIFICA cada línea y manda tres campos:
  #
  #     TAKAB_API_X true|false -          booleana: el valor literal, que no puede ser secreto
  #     TAKAB_API_X vacio      -          definida y vacía
  #     TAKAB_API_X con-valor  <12 hex>   huella sha256 del valor, nunca el valor
  #
  # La huella deja comparar con lo que declara el despliegue sin que el valor cruce
  # la red ni acabe impreso en el informe. No es paranoia de manual: la salida
  # `push_fcm_application_arn` está marcada `sensitive` en el terraform y
  # TAKAB_API_PUSH_FCM_APPLICATION_ARN sale de ella.
  #
  # Todo POSIX (sin `< <(...)`, sin `${v%$'\r'}`): el documento AWS-RunShellScript no
  # promete bash.
  cmd="$(
    cat <<'REMOTO'
cd /opt/takab/cloud && echo "::PS::" && docker compose --env-file /etc/takab/deploy.env ps -a --format json
echo "::ENV::"
tr -d '\r' < /etc/takab/cloud.env | grep -E '^TAKAB_API_[A-Z0-9_]+=' | while IFS= read -r l; do
  n=${l%%=*}
  v=${l#*=}
  case "$v" in
  true | false) printf '%s %s -\n' "$n" "$v" ;;
  '') printf '%s vacio -\n' "$n" ;;
  *) printf '%s con-valor %s\n' "$n" "$(printf '%s' "$v" | sha256sum | cut -c1-12)" ;;
  esac
done
echo "::TAG::"
sed -n 's/^TAKAB_CLOUD_IMAGE=.*://p' /etc/takab/deploy.env
REMOTO
  )"
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
    registrar VERDE "$pieza" "$n_decl/$n_decl declarados corriendo en $id (imagen :${TAG_INSTANCIA:-?})${sobran:+; en la instancia sobran:$sobran} · instancia hallada por $INSTANCIA_ORIGEN"
  else
    registrar ROJO "$pieza" "declarados en deploy/cloud/docker-compose.yml y${faltan:+ SIN CONTENEDOR en $id:$faltan}${mal:+ con estado distinto de running:$mal} (imagen :${TAG_INSTANCIA:-?}; instancia hallada por $INSTANCIA_ORIGEN) → make cloud-images && make cloud-deploy (T-7.02)"
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
  local pieza="entorno que la nube exige" requeridos origen faltan="" n err detalle
  err="$(mktemp)"
  requeridos="$(cd api && uv run python -c \
    'from takab_api.settings import REQUERIDOS_EN_PRODUCCION as R; print(" ".join(sorted(c.upper() for c in R)))' \
    2>"$err")"
  detalle="$(tr -s '\n\t' '  ' <"$err" | tail -c 160)"
  rm -f "$err"
  # Sin esa lista esta pieza NO mide lo que dice medir: se quedaba en los dos nombres
  # que trae escritos —QUEUE_URL_BACKFILL y DLQ_URL_BACKFILL— de los diez que exige la
  # nube, y aun así registraba VERDE «todo en el heredoc». Era el fallback vestido de
  # «ok» que este mismo fichero cita dos veces como su razón de existir (T-2.152), y el
  # escenario no es teórico: `uv` no existe en el runner de CI y el venv de api/ no
  # siempre está sincronizado en la máquina del operador. `pieza_test`, justo arriba,
  # ya lo hacía bien. La evidencia dice qué no se pudo leer y con qué error.
  if [ -z "$requeridos" ]; then
    registrar "NO MEDIDO" "$pieza" \
      "no se pudo LEER Settings.REQUERIDOS_EN_PRODUCCION$(command -v uv >/dev/null 2>&1 || printf ' (falta uv en el PATH)')${detalle:+: $detalle} · sin esa lista solo se habrían mirado 2 de los nombres que la nube exige, y un censo corto no falla: se calla"
    return
  fi
  origen="Settings.REQUERIDOS_EN_PRODUCCION ($(wc -w <<<"$requeridos") nombres) + QUEUE_URL_BACKFILL/DLQ_URL_BACKFILL"
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

# huella_de <valor> — los 12 primeros hex del sha256, la MISMA cuenta que hace la
# instancia en pieza_compose. Es como se compara un valor sin moverlo ni imprimirlo.
huella_de() { printf '%s' "$1" | sha256sum | cut -c1-12; }

# pieza_bandera <NOMBRE sin prefijo> <quién decide / ficha>
#
# [T-7.26] Compara VALORES, no nombres. Hasta esta ficha el veredicto salía de dos
# preguntas —¿está el nombre en deploy.sh? ¿está el nombre en la instancia?— y por
# eso daba VERDE con la bandera puesta a `false` y con el slug del modelo vacío: los
# dos casos que este censo dice vigilar. El valor esperado se DERIVA del despliegue
# (`origen_declarado`, en banderas.sh) y, cuando sale del terraform, se le pregunta
# al terraform. Lo que nunca se imprime es el valor de la instancia: solo su clase y,
# para compararlo, su huella (ver pieza_compose).
pieza_bandera() {
  local n="$1" ficha="$2" pieza="bandera TAKAB_API_$1"
  local origen clase dato esperado fuente clase_inst huella_inst

  if ! origen="$(origen_declarado deploy/cloud/deploy.sh "$n")"; then
    registrar AMARILLO "$pieza" "NO exportada en deploy.sh → la nube corre con el default de Settings ($ficha)"
    return
  fi
  clase="${origen%%$'\t'*}"
  dato="${origen#*$'\t'}"

  if [ "$SSM_OK" != 1 ]; then
    registrar AMARILLO "$pieza" "exportada en deploy.sh ($clase) · instancia no medida ($ficha)"
    return
  fi
  clase_inst="$(awk -v v="TAKAB_API_$n" '$1 == v { print $2; exit }' <<<"$ENV_INSTANCIA")"
  huella_inst="$(awk -v v="TAKAB_API_$n" '$1 == v { print $3; exit }' <<<"$ENV_INSTANCIA")"
  if [ -z "$clase_inst" ]; then
    registrar AMARILLO "$pieza" "exportada en deploy.sh · ausente en /etc/takab/cloud.env de la instancia → pendiente de desplegar ($ficha)"
    return
  fi

  # De dónde sale el valor que la instancia DEBERÍA tener.
  case "$clase" in
  literal)
    esperado="$dato"
    fuente="deploy.sh la fija a «$dato»"
    ;;
  tf)
    # Que la salida no exista no es «no sé»: es el caso que deja el despliegue
    # escribiendo un valor vacío (ver tf_obligatorio en deploy.sh). Se dice en ROJO.
    #
    # Pero `tf_out` devuelve EL MISMO fallo cuando terraform no ha podido ni arrancar
    # —init, backend, lock o unas credenciales caducadas—, y eso no acusa a nadie: es
    # la falsa alarma que este fichero ya cerró para IAM y para el secreto. Hasta hoy
    # quedaba tapada porque sin instancia no había SSM_OK y la pieza salía antes; desde
    # que la instancia se resuelve también por etiqueta, esta rama SÍ se alcanza con
    # terraform muerto, y sin esto el censo saldría acusando al terraform y recetando
    # un `make cloud-apply` que no arregla una sesión de SSO caducada.
    #
    # No se interpreta aquí el stderr: manda lo ya MEDIDO al resolver la instancia
    # (`TF_VIVO`). Con la pieza corriendo suelta —el arnés— no hay medición y el valor
    # por defecto deja el veredicto de siempre.
    if ! esperado="$(tf_out "$dato" 2>/dev/null)"; then
      if [ "${TF_VIVO:-1}" = 0 ]; then
        registrar "NO MEDIDO" "$pieza" "deploy.sh la resuelve con \$(tf $dato) y terraform no contesta en esta máquina (${TF_MOTIVO:-sin detalle}): esto NO dice que falte la salida, dice que no se midió → refresca las credenciales (aws sso logout && aws sso login) ($ficha)"
      else
        registrar ROJO "$pieza" "deploy.sh la resuelve con \$(tf $dato) y el terraform NO publica esa salida → make cloud-apply antes de desplegar"
      fi
      return
    fi
    # El valor de una salida del terraform no se imprime: `push_fcm_application_arn`
    # está marcada `sensitive`. Se nombra la salida, que es lo accionable.
    fuente="la salida «$dato» del terraform"
    ;;
  *)
    # Una sustitución compuesta (una tubería, un python3): el valor esperado no es
    # derivable. Decirlo en AMARILLO y no dar por bueno lo que haya — un fallback no
    # puede ser «ok» (T-2.152).
    registrar AMARILLO "$pieza" "deploy.sh la resuelve con una sustitución que este censo no sabe evaluar ($dato): en la instancia está $clase_inst, pero el valor esperado no es derivable ($ficha)"
    return
    ;;
  esac

  case "$esperado" in
  true | false)
    if [ "$clase_inst" = "$esperado" ]; then
      registrar VERDE "$pieza" "$fuente y la instancia la trae en $clase_inst"
    else
      registrar ROJO "$pieza" "$fuente y en la instancia está $clase_inst → lo que está en código NO está en el sistema ($ficha)"
    fi
    ;;
  "")
    if [ "$clase_inst" = vacio ]; then
      registrar VERDE "$pieza" "$fuente y viene vacía; la instancia también la trae vacía (la función que depende de ella está apagada en los dos sitios)"
    else
      registrar ROJO "$pieza" "$fuente y viene VACÍA, pero la instancia trae $clase_inst: el despliegue y el terraform no dicen lo mismo ($ficha)"
    fi
    ;;
  *)
    if [ "$clase_inst" = vacio ]; then
      registrar ROJO "$pieza" "$fuente y en la instancia está VACÍA → la nube corre degradada con la bandera puesta ($ficha)"
    elif [ "$clase_inst" != con-valor ]; then
      registrar ROJO "$pieza" "$fuente y en la instancia está $clase_inst ($ficha)"
    elif [ "$huella_inst" = "$(huella_de "$esperado")" ]; then
      registrar VERDE "$pieza" "$fuente y la instancia trae ESE valor (huella sha256 $huella_inst)"
    else
      registrar ROJO "$pieza" "$fuente y la instancia trae OTRO valor (huella ${huella_inst} ≠ $(huella_de "$esperado")) → make cloud-deploy ($ficha)"
    fi
    ;;
  esac
}

# El POR QUE de cada bandera. La LISTA ya no se escribe aqui —se deriva de
# deploy.sh, ver banderas.sh—, pero la razon de cada una no la puede inventar un
# grep. Lo que ha cambiado es que olvidarla ya no es silencioso: si una bandera
# derivada no tiene ficha, el informe lo dice, y antes de eso lo dice en ROJO
# infra/scripts/tests/test_censo_banderas.sh.
declare -A FICHA_BANDERA=(
  [OPS_METRICS_ENABLED]="métrica de gabinetes fantasma: T-2.60.a"
  [CONSOLE_SCOPE_ENFORCED]="alcance por rol: T-7.06 · D-18"
  [OPENROUTER_ENABLED]="capa narrativa del dictamen: T-7.26"
  [CATALOG_USGS_ENABLED]="consulta al catálogo externo tras el evento: T-7.25"
)

# Banderas que NO son un booleano literal y por eso no se derivan solas: llegan
# por $(tf ...), y su ausencia significa «vacío», no «false». Estas sí se
# enumeran, porque no hay nada en deploy.sh que las distinga de cualquier otro
# valor derivado del terraform.
declare -A FICHA_NO_DERIVADA=(
  [PUSH_FCM_APPLICATION_ARN]="push real por FCM: T-7.03"
  # [T-7.26] Encender la capa narrativa exige LAS TRES: bandera, modelo y secreto.
  # Con el modelo vacío o el identificador del secreto vacío, `resolve_api_key`
  # devuelve cadena vacía y la nube redacta prosa determinista CON LA BANDERA
  # ENCENDIDA — el sistema diciendo una cosa y haciendo otra, que es lo que este
  # censo existe para ver. Por eso `pieza_bandera` compara el VALOR y no el nombre:
  # con nombres, «vacío» y «puesto» tienen exactamente el mismo aspecto.
  [OPENROUTER_MODEL]="slug del modelo: T-7.26"
  [OPENROUTER_SECRET_ID]="identificador del secreto (no la clave): T-7.26"
)

pieza_banderas() {
  local lista n
  # Cero banderas no es «ninguna bandera»: es el derivador ciego (fichero movido,
  # formato cambiado). Un fallback no puede ser «ok» (T-2.152).
  if ! lista="$(banderas_declaradas "$AQUI/deploy.sh")"; then
    registrar ROJO "censo de banderas" \
      "banderas_declaradas no encontró NINGUNA en deploy/cloud/deploy.sh: el censo está ciego, no vacío"
    return
  fi
  for n in $lista; do
    pieza_bandera "$n" "${FICHA_BANDERA[$n]:-sin ficha declarada en conformidad.sh}"
  done
  # Ordenadas: las claves de un array asociativo salen en orden de hash y el
  # informe tiene que ser comparable entre dos corridas.
  for n in $(printf '%s\n' "${!FICHA_NO_DERIVADA[@]}" | sort); do
    pieza_bandera "$n" "${FICHA_NO_DERIVADA[$n]}"
  done
}

# --- 5.b · el secreto de la capa narrativa (T-7.26) ---------------------------------------
# Las banderas de arriba miden lo que hay ESCRITO en la instancia. Esta pieza mide las
# dos cosas de las que depende que la capa narrativa funcione y que ninguna otra mira:
# que el secreto EXISTA en Secrets Manager y que el rol de la instancia lo tenga
# concedido. El secreto lo crea una persona fuera del terraform (regla de oro 6: la
# clave no puede entrar en el estado), así que `terraform plan` sale limpio con o sin
# él — y sin esta pieza el censo podía devolver «todo VERDE» con la ficha entera
# inerte: GetSecretValue responde AccessDenied, `resolve_api_key` degrada y el
# dictamen sale determinista con la bandera encendida.
#
# Lo que NO hace, a propósito: `get-secret-value`. La existencia y el permiso se ven
# con `describe-secret` y con la política; leer la clave para comprobar que se puede
# leer sería traerla a esta máquina para nada.
pieza_secreto_ia() {
  local pieza="secreto de la capa narrativa" bandera id arn err inst perfil rol pol doc
  local politicas otorga concedidos r casa=0
  bandera="$(origen_declarado deploy/cloud/deploy.sh OPENROUTER_ENABLED 2>/dev/null | cut -f2)"
  if [ "$bandera" != true ]; then
    registrar VERDE "$pieza" "deploy.sh exporta TAKAB_API_OPENROUTER_ENABLED=${bandera:-<ausente>}: la capa narrativa va apagada y no hay secreto que exigir"
    return
  fi
  if [ "$AWS_OK" != 1 ]; then registrar "NO MEDIDO" "$pieza" "$AWS_MOTIVO"; return; fi

  # Los TRES desenlaces, como las cinco llamadas de abajo: la salida no está (ROJO, y el
  # despliegue abortaría), terraform no pudo contestar (NO MEDIDO, y no acusa a nadie), o
  # está y sigue la pieza.
  if ! tf_medido openrouter_secret_id; then
    if tf_falta_la_salida; then
      registrar ROJO "$pieza" "el terraform no publica openrouter_secret_id → make cloud-apply (README §4); sin esa salida deploy.sh aborta"
    else
      registrar "NO MEDIDO" "$pieza" "no se pudo PREGUNTAR «terraform output openrouter_secret_id»: $(printf '%s' "${TF_ERROR:-sin detalle}" | head -c 160) · esto NO dice que falte la salida, dice que no se midió → ¿está inicializado ${TF_DEV:-el entorno de terraform} y hay credenciales?"
    fi
    return
  fi
  id="$TF_SALIDA"
  if [ -z "$id" ]; then
    registrar ROJO "$pieza" "el terraform publica openrouter_secret_id VACÍO → make cloud-apply (README §4); sin esa salida deploy.sh aborta"
    return
  fi
  # UNA sola llamada: preguntarlo dos veces (una para el valor, otra para el error)
  # puede dar dos respuestas distintas y entonces el veredicto no es de ningún momento.
  arn=""
  err=""
  if aws_medido secretsmanager describe-secret --secret-id "$id" --query ARN --output text; then
    arn="$AWS_SALIDA"
  else
    err="$AWS_ERROR"
  fi
  if [ -z "$arn" ] || [ "$arn" = None ]; then
    case "$err" in
    *ResourceNotFoundException*)
      registrar ROJO "$pieza" "el secreto «$id» NO existe en Secrets Manager (README §4.1) → la nube redactaría prosa determinista con la bandera encendida"
      ;;
    *)
      registrar "NO MEDIDO" "$pieza" "$(sin_medir "secretsmanager describe-secret --secret-id $id" "$err") — y sin saber si el secreto existe, tampoco se mira el permiso"
      ;;
    esac
    return
  fi

  # El rol se DERIVA de la instancia, no se teclea: un literal «takab-dev-db» aquí
  # divergiría el día que el módulo lo renombre y esta pieza mediría un rol que no es.
  inst="${INSTANCIA_ID:-}"
  if [ -z "$inst" ] && [ -z "${INSTANCIA_MOTIVO:-}" ]; then
    # Nadie la resolvió antes —la pieza corre suelta, como en el arnés—: se pregunta.
    inst="$(tf_out db_instance_id 2>/dev/null || true)"
  fi
  if [ -z "$inst" ]; then
    registrar "NO MEDIDO" "$pieza" "el secreto $id existe, pero ${INSTANCIA_MOTIVO:-terraform output db_instance_id no contestó}: no sé qué rol mirar"
    return
  fi
  perfil=""
  if aws_medido ec2 describe-instances --instance-ids "$inst" \
    --query 'Reservations[0].Instances[0].IamInstanceProfile.Arn' --output text; then
    perfil="$AWS_SALIDA"
  else
    registrar "NO MEDIDO" "$pieza" "el secreto $id existe ($arn), pero $(sin_medir "ec2 describe-instances --instance-ids $inst" "$AWS_ERROR")"
    return
  fi
  rol=""
  if [ -n "$perfil" ] && [ "$perfil" != None ]; then
    if aws_medido iam get-instance-profile --instance-profile-name "${perfil##*/}" \
      --query 'InstanceProfile.Roles[0].RoleName' --output text; then
      rol="$AWS_SALIDA"
    else
      registrar "NO MEDIDO" "$pieza" "el secreto $id existe ($arn), pero $(sin_medir "iam get-instance-profile --instance-profile-name ${perfil##*/}" "$AWS_ERROR")"
      return
    fi
  fi
  if [ -z "$rol" ] || [ "$rol" = None ]; then
    registrar "NO MEDIDO" "$pieza" "el secreto $id existe ($arn), pero la instancia $inst no declara rol que mirar (perfil=${perfil:-<vacío>}): no se midió el permiso"
    return
  fi

  # Aquí estaba el defecto de este repaso, y lo había metido el arreglo anterior: el
  # bucle iba sobre `$(aws_cli iam list-role-policies ... 2>/dev/null || true)`, que se
  # traga el error y sigue. Con las credenciales caducadas, sin permiso de lectura de
  # IAM o en la región equivocada, la lista sale VACÍA —indistinguible de un rol sin
  # el permiso— y el censo acusaba en ROJO de lo que no había mirado, recetando encima
  # un `make cloud-apply` que no arregla unas credenciales. Un censo que acusa de lo
  # que no comprobó enseña al operador a ignorar el rojo. NO MEDIDO ≠ ROJO.
  if ! aws_medido iam list-role-policies --role-name "$rol" --query 'PolicyNames[]' --output text; then
    registrar "NO MEDIDO" "$pieza" "el secreto $id existe ($arn), pero $(sin_medir "iam list-role-policies --role-name $rol" "$AWS_ERROR")"
    return
  fi
  politicas="$(tr '\t\n' '  ' <<<"$AWS_SALIDA")"
  if [ "${politicas// /}" = None ]; then politicas=""; fi
  if [ -z "${politicas// /}" ]; then
    registrar ROJO "$pieza" "el secreto $id existe ($arn) y el rol $rol NO tiene NINGUNA política inline: nadie le concede secretsmanager:GetSecretValue → make cloud-apply (README §4.2)"
    return
  fi

  concedidos=""
  for pol in $politicas; do
    if ! aws_medido iam get-role-policy --role-name "$rol" --policy-name "$pol" \
      --query PolicyDocument --output json || [ -z "$AWS_SALIDA" ]; then
      registrar "NO MEDIDO" "$pieza" "el rol $rol declara la política inline «$pol» y $(sin_medir "iam get-role-policy --role-name $rol --policy-name $pol" "$AWS_ERROR")"
      return
    fi
    doc="$AWS_SALIDA"
    # Saltarse una política ilegible tampoco vale: la que no se pudo leer es
    # justamente la que podía traer el permiso.
    if ! otorga="$(jq -r '
      [ .Statement[]?
        | select((.Effect // "") == "Allow")
        | select(((if (.Action | type) == "array" then .Action else [.Action] end)
                  | any(. == "*" or . == "secretsmanager:*" or . == "secretsmanager:GetSecretValue")))
        | (if (.Resource | type) == "array" then .Resource[] else .Resource end)
      ] | .[]' <<<"$doc" 2>&1)"; then
      registrar "NO MEDIDO" "$pieza" "la política inline «$pol» del rol $rol no se pudo interpretar (jq: $(head -c 160 <<<"$otorga")): no sé si concede el permiso"
      return
    fi
    concedidos="$concedidos $(tr '\n' ' ' <<<"$otorga")"
  done
  if [ -z "${concedidos// /}" ]; then
    registrar ROJO "$pieza" "el secreto $id existe ($arn), pero NINGUNA de las políticas inline del rol $rol (${politicas// /, }) concede secretsmanager:GetSecretValue → make cloud-apply (README §4.2)"
    return
  fi
  # El ARN real trae los seis caracteres aleatorios que añade Secrets Manager; el
  # permiso los cubre con un comodín. Se casa como glob —`*` y `?` de IAM son los del
  # shell— y sin comillas a propósito: entrecomillarlo lo volvería comparación literal
  # y el `-*` no casaría nunca.
  for r in $concedidos; do
    # shellcheck disable=SC2254
    case "$arn" in $r)
      casa=1
      break
      ;;
    esac
  done
  if [ "$casa" = 1 ]; then
    registrar VERDE "$pieza" "el secreto $id existe ($arn) y la política inline del rol $rol le concede GetSecretValue${INSTANCIA_ORIGEN:+ · rol derivado de la instancia $inst, hallada por $INSTANCIA_ORIGEN}"
  else
    registrar ROJO "$pieza" "el secreto $id existe ($arn) pero el rol $rol NO lo alcanza: concede $(tr -s " " <<<"$concedidos") → make cloud-apply (README §4.2)${INSTANCIA_ORIGEN:+ · rol derivado de la instancia $inst, hallada por $INSTANCIA_ORIGEN}"
  fi
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
    # La evidencia decía SIEMPRE «sin la clave backfill», que es una acusación concreta
    # —y falsa— cuando lo que pasa es que terraform no arrancó. El veredicto no cambia
    # (los dos casos son NO MEDIDO); lo que cambia es que ahora nombra la causa que se
    # midió al resolver la instancia, en vez de inventarse una.
    if [ "${TF_VIVO:-1}" = 0 ]; then
      registrar "NO MEDIDO" "$pieza" "terraform no contesta en esta máquina (${TF_MOTIVO:-sin detalle}): no se pudieron leer queue_urls/dlq_urls · esto NO dice que falte la clave backfill, dice que no se midió"
    else
      registrar "NO MEDIDO" "$pieza" "terraform output queue_urls/dlq_urls sin la clave backfill"
    fi
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
# Respaldo POR NOMBRE, no por dirección: el Pi la coge por DHCP y cambia.
PI_IP="${PI_IP:-raspberry-cerebro.local}"
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
  # OJO: `//` de jq trata `false` como ausente y devolvía "desconocido" con el modo
  # prueba DESARMADO (medido el 2026-09-12): el caso bueno salía NO MEDIDO.
  activo="$(jq -r 'if (.test_mode.active|type) == "boolean" then (.test_mode.active|tostring) else "desconocido" end' <<<"$st")"
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
pieza_banderas
pieza_secreto_ia
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
