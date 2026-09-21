#!/usr/bin/env bash
# [T-7.26] El camino de una BANDERA: de deploy.sh a /etc/takab/cloud.env, y de ahi
# al informe de conformidad. Y, desde el segundo repaso del 2026-09-21, tambien lo
# que hay al final de ese camino: el secreto y el permiso de leerlo.
#
# Por que existe. El 2026-09-21, preparando el encendido de la capa narrativa, el
# reconocimiento midio tres huecos que ningun test veia:
#
#   1. El censo de banderas de `conformidad.sh` estaba ENUMERADO A MANO (tres
#      llamadas literales a `pieza_bandera`) y ya estaba corto: llevaba desde
#      T-2.60.a sin mirar `TAKAB_API_OPS_METRICS_ENABLED`, que es de quien depende
#      que la alarma `GhostGatewaysAlive` tenga datos. Un censo corto no falla: se
#      calla, y es peor, porque el informe dice "todo VERDE" sobre lo que si mira.
#      La doctrina del repositorio ya lo tenia escrito: un censo que enumera a mano
#      acaba divergiendo (TRASPASO-SESION.md).
#   2. Ningun test leia `conformidad.sh`. El vigilante no estaba vigilado.
#   3. El heredoc de `deploy.sh` se abre SIN comillas —tiene que expandir los
#      `$(tf ...)`— asi que una comilla invertida dentro de un comentario no es
#      tipografia: es sustitucion de ordenes, y el despliegue EJECUTA lo que haya
#      dentro. Ya paso (tres "orden no encontrada" el 2026-08-09). `api/tests`
#      lo vigila LEYENDO el texto; aqui se vigila RENDERIZANDO el bloque, que es
#      la unica forma de ver lo que acabara en /etc/takab/cloud.env.
#
# Y un segundo repaso, el mismo dia, midio cuatro mas — todos de la misma familia:
# un texto afirmando lo que el codigo no hacia.
#
#   4. El censo comparaba NOMBRES, no valores: daba VERDE con la bandera puesta a
#      `false` en la instancia y con el slug del modelo vacio, que son exactamente
#      los dos casos que dice vigilar. Se mide en «el censo compara el VALOR».
#   5. Sin `make cloud-apply`, el despliegue NO abortaba: un `$( )` que falla DENTRO
#      del heredoc deja el hueco vacio y el `cat` devuelve 0. Se mide en «sin la
#      salida del terraform, el despliegue ABORTA», ejercitando el fallo.
#   6. El comentario del tope de gasto de `deploy.sh` documentaba la semantica
#      INVERTIDA a la que implementa `narrative/quota.py`. Ningun test cruzaba los
#      dos ficheros; ahora lo hace «el comentario del tope de gasto».
#   7. Nada media que el secreto EXISTA ni que el rol pueda LEERLO, y el README
#      pedia un orden que el terraform no impone. Ultimas dos secciones.
#
# Lo que este archivo NO hace: salir a AWS. Todo se mide sobre el arbol de trabajo —
# tambien la pieza que habla con AWS, que se ejercita con dobles.
#
# Corre con: bash infra/scripts/tests/test_censo_banderas.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
DEPLOY="$ROOT/deploy/cloud/deploy.sh"
CONFORMIDAD="$ROOT/deploy/cloud/conformidad.sh"
DERIVADOR="$ROOT/deploy/cloud/banderas.sh"
TF_MAIN="$ROOT/infra/terraform/envs/dev/main.tf"
TF_OUT="$ROOT/infra/terraform/envs/dev/outputs.tf"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fallos=0
ok() { printf '  ok   %s\n' "$1"; }
fallo() { printf '  FALLO %s\n' "$1" >&2; fallos=$((fallos + 1)); }
check() { # <descripcion> <esperado> <obtenido>
  if [ "$2" = "$3" ]; then ok "$1"; else
    fallo "$1"
    printf '        esperado: %s\n        obtenido: %s\n' "$2" "$3" >&2
  fi
}

# --- Extraer trozos de conformidad.sh sin ejecutarlo -------------------------------
# conformidad.sh no se puede sourcear —arranca midiendo—, asi que las pruebas que
# EJERCITAN sus funciones las recortan. El recorte anterior iba de
# `declare -A FICHA_BANDERA=(` a la primera llave a columna cero, un rango que solo
# funcionaba porque hoy no hay ninguna funcion en medio: intercalar una dejaba
# `pieza_banderas` sin definir y el arnes se ponia rojo acusando a las banderas de
# OpenRouter, que estaban perfectas. Falla en el lado seguro, pero la evidencia
# apuntaba al sitio equivocado, y eso en este repositorio cuesta una corrida de
# depuracion. Ahora cada trozo se recorta por su nombre y, si UN TROZO sale vacio, lo
# dice de si mismo y lo dice por su nombre.
extraer_funcion() { # <fichero> <nombre>
  awk -v f="$2() {" 'index($0, f) == 1 { p = 1 } p { print } p && /^}$/ { exit }' "$1"
}
extraer_array() { # <fichero> <NOMBRE del array asociativo>
  awk -v a="declare -A $2=(" 'index($0, a) == 1 { p = 1 } p { print } p && /^\)$/ { exit }' "$1"
}
recorta() { # <destino> <fichero> <funcion|array> <nombre>...
  local destino="$1" fichero="$2" tipo="$3" n antes
  shift 3
  : >"$destino"
  for n in "$@"; do
    antes="$(wc -c <"$destino")"
    if [ "$tipo" = funcion ]; then extraer_funcion "$fichero" "$n"; else extraer_array "$fichero" "$n"; fi >>"$destino"
    # POR TROZO, no por fichero. `grep -q .` miraba el ACUMULADO, asi que el primer
    # recorte bueno tapaba a todos los siguientes: con dos nombres o mas, renombrar el
    # segundo en conformidad.sh dejaba este arnes verde midiendo media escena. El
    # comentario de arriba prometia lo contrario desde el primer dia; ahora es verdad.
    if [ "$(wc -c <"$destino")" -le "$antes" ]; then
      fallo "EL ARNES no pudo recortar $tipo $n de $(basename "$fichero"): el fallo es de esta prueba, no de lo que mide"
      return 1
    fi
  done
}

echo "== el arnes se delata a SI MISMO cuando un recorte sale vacio =="
# La guarda del parrafo de arriba. Se ejercita recorta() con un segundo nombre que no
# existe: es el caso exacto que se colaba, porque el destino ya traia el primero.
# Entre parentesis para que el `fallo` de dentro no cuente como fallo de este arnes.
recorte_malo="$( (recorta "$TMP/recorte-imposible.sh" "$CONFORMIDAD" funcion pieza_secreto_ia no_existe_esta_funcion) 2>&1 )"
rc_malo=$?
if [ "$rc_malo" = 0 ]; then
  fallo "recorta() dio por bueno un trozo VACIO: basta con que el PRIMER nombre exista para que los demas pasen sin mirarse"
elif grep -qF 'no_existe_esta_funcion' <<<"$recorte_malo"; then
  ok "un trozo vacio detras de uno bueno se delata, y se delata por SU nombre"
else
  fallo "recorta() fallo pero no dijo QUE trozo falto: $recorte_malo"
fi
recorte_bueno="$( (recorta "$TMP/recorte-posible.sh" "$CONFORMIDAD" funcion aws_medido sin_medir pieza_secreto_ia) 2>&1 )"
rc_bueno=$?
if [ "$rc_bueno" = 0 ] && [ -z "$recorte_bueno" ]; then
  ok "tres trozos que SI existen se recortan sin quejarse"
else
  fallo "recorta() se quejo de un recorte bueno (rc=$rc_bueno): $recorte_bueno"
fi

# ---------------------------------------------------------------------------
# 1. El censo de banderas se DERIVA del despliegue
# ---------------------------------------------------------------------------
echo "== el censo de banderas se DERIVA de deploy.sh =="
if [ ! -f "$DERIVADOR" ]; then
  fallo "no existe deploy/cloud/banderas.sh: el censo sigue enumerado a mano y puede quedarse corto en silencio"
else
  # shellcheck source=../../../deploy/cloud/banderas.sh
  . "$DERIVADOR"
  if ! declare -F banderas_declaradas >/dev/null; then
    fallo "banderas.sh no define banderas_declaradas"
  fi
fi

derivadas=""
if declare -F banderas_declaradas >/dev/null; then
  derivadas="$(banderas_declaradas "$DEPLOY")"
fi

# Las tres que HOY fija el despliegue con un booleano literal. Se nombran aqui a
# proposito: son el control positivo del derivador. Si alguna dejara de estar en
# deploy.sh, esto se pone rojo y hay que venir a borrarla A SABIENDAS.
for n in OPS_METRICS_ENABLED CONSOLE_SCOPE_ENFORCED OPENROUTER_ENABLED; do
  if grep -qx "$n" <<<"$derivadas"; then
    ok "el derivador ve $n"
  else
    fallo "el derivador NO ve $n (derivadas: $(tr '\n' ' ' <<<"$derivadas"))"
  fi
done

echo "== una bandera NUEVA entra en el censo sin tocar conformidad.sh =="
# Esta es la mitad que faltaba. Con el censo enumerado a mano, anadir una bandera
# a deploy.sh y olvidarse de la lista daba un informe en verde que no la miraba.
if declare -F banderas_declaradas >/dev/null; then
  cp "$DEPLOY" "$TMP/deploy-laboratorio.sh"
  printf 'TAKAB_API_BANDERA_DE_LABORATORIO=true\n' >>"$TMP/deploy-laboratorio.sh"
  if banderas_declaradas "$TMP/deploy-laboratorio.sh" | grep -qx BANDERA_DE_LABORATORIO; then
    ok "una bandera inventada aparece sola en el censo"
  else
    fallo "una bandera nueva NO aparece en el censo: el censo puede volver a quedarse corto"
  fi

  echo "== un despliegue SIN banderas es un fallo, no un censo vacio =="
  # Un fallback no puede ser «ok» (T-2.152). Si el derivador no encuentra nada
  # —fichero movido, formato cambiado— tiene que DECIRLO, no devolver la lista
  # vacia y dejar que conformidad.sh recorra cero banderas en silencio.
  : >"$TMP/vacio.sh"
  if banderas_declaradas "$TMP/vacio.sh" >/dev/null 2>&1; then
    fallo "banderas_declaradas devuelve exito con CERO banderas: el censo vacio pasaria por censo completo"
  else
    ok "cero banderas = codigo de salida distinto de cero"
  fi
fi

echo "== conformidad.sh ya no enumera las booleanas a mano =="
if ! grep -qE '^pieza_banderas([[:space:]]|$)' "$CONFORMIDAD"; then
  fallo "conformidad.sh no invoca pieza_banderas (el censo derivado)"
else
  ok "conformidad.sh invoca pieza_banderas"
fi
for n in $derivadas; do
  if grep -qE "^[[:space:]]*pieza_bandera[[:space:]]+${n}([[:space:]]|$)" "$CONFORMIDAD"; then
    fallo "conformidad.sh sigue enumerando $n a mano (dos fuentes de verdad para el mismo censo)"
  else
    ok "$n no esta enumerada a mano"
  fi
done

echo "== toda bandera derivada trae su ficha =="
# La LISTA se deriva y por tanto no puede quedarse corta. El POR QUE de cada
# bandera se sigue escribiendo a mano —ningun grep lo puede inventar—, pero ya no
# se puede olvidar en silencio: se olvida en ROJO, aqui.
fichas="$(sed -n '/^declare -A FICHA_BANDERA=(/,/^)$/p' "$CONFORMIDAD" |
  grep -oE '^[[:space:]]*\[[A-Z0-9_]+\]' | tr -d ' []' | sort -u)"
for n in $derivadas; do
  if grep -qx "$n" <<<"$fichas"; then
    ok "$n tiene ficha en FICHA_BANDERA"
  else
    fallo "$n no tiene ficha en FICHA_BANDERA de conformidad.sh (el informe diria 'sin ficha declarada')"
  fi
done


echo "== el censo EMITE una pieza por bandera (no solo la lista: la salida) =="
# Las comprobaciones de arriba leen texto. Esta EJERCITA pieza_banderas con dobles
# de `registrar` y `pieza_bandera`: sin ella, un fallo dentro del cuerpo de la
# funcion —una variable mal escrita, un bucle que no itera— dejaria el informe sin
# una sola bandera y todos los greps seguirian en verde.
recorta "$TMP/censo.sh" "$CONFORMIDAD" array FICHA_BANDERA FICHA_NO_DERIVADA
extraer_funcion "$CONFORMIDAD" pieza_banderas >>"$TMP/censo.sh"
if ! grep -q '^pieza_banderas() {' "$TMP/censo.sh"; then
  fallo "EL ARNES no pudo recortar pieza_banderas de conformidad.sh: el fallo es de esta prueba, no de lo que mide"
fi
cat >"$TMP/smoke.sh" <<'SMOKE'
set -u
cd "$ROOT" || exit 2
AQUI="$ROOT/deploy/cloud"
SSM_OK=0
. "$ROOT/deploy/cloud/banderas.sh"
registrar() { printf '%s\t%s\n' "$1" "$2"; }
pieza_bandera() { registrar AMARILLO "bandera TAKAB_API_$1"; }
# shellcheck disable=SC1090
. "$CENSO"
pieza_banderas
SMOKE
piezas="$(ROOT="$ROOT" CENSO="$TMP/censo.sh" bash "$TMP/smoke.sh" 2>"$TMP/smoke.err")"
# Las esperadas se CUENTAN de las dos listas, no se teclean: con un "+1" fijo,
# añadir una entrada a FICHA_NO_DERIVADA dejaba el numero corto y el check rojo
# sin que nada estuviera mal — o, peor, al reves.
no_derivadas="$(sed -n '/^declare -A FICHA_NO_DERIVADA=(/,/^)$/p' "$CONFORMIDAD" |
  grep -oE '^[[:space:]]*\[[A-Z0-9_]+\]' | tr -d ' []' | sort -u)"
esperadas=$(($(grep -c . <<<"$derivadas") + $(grep -c . <<<"$no_derivadas")))
check "una pieza por bandera" "$esperadas" "$(grep -c . <<<"$piezas")"
if grep -q 'ROJO' <<<"$piezas"; then
  fallo "pieza_banderas registro ROJO sobre el deploy.sh real: $(grep ROJO <<<"$piezas")"
else
  ok "ninguna pieza en ROJO con el deploy.sh real"
fi
for n in $derivadas; do
  if grep -qF "bandera TAKAB_API_$n" <<<"$piezas"; then
    ok "el censo emite la pieza de $n"
  else
    fallo "el censo NO emite la pieza de $n (salida: $(tr '\n' ' ' <<<"$piezas"))"
  fi
done

echo "== las tres piezas que deciden si la IA redacta EMITEN pieza =="
# Bandera, modelo y secreto: las tres tienen que aparecer en el informe. Que ademas
# se mida su VALOR —y no solo que el nombre exista— lo comprueba el bloque siguiente,
# que es donde estaba el agujero: hasta el 2026-09-21 este arnes concluia de aqui que
# «el informe puede verlo, no solo la booleana», y era falso.
for n in OPENROUTER_ENABLED OPENROUTER_MODEL OPENROUTER_SECRET_ID; do
  if grep -qF "bandera TAKAB_API_$n" <<<"$piezas"; then
    ok "el censo emite la pieza de $n"
  else
    fallo "el censo NO emite la pieza de $n: no saldria en el informe"
  fi
done

# ---------------------------------------------------------------------------
# 1.b El censo compara el VALOR de la bandera, no su nombre
# ---------------------------------------------------------------------------
echo "== el censo compara el VALOR que hay en la instancia, no solo el nombre =="
# El defecto que cierra esto, medido el 2026-09-21: `pieza_bandera` preguntaba «esta
# el nombre en deploy.sh?» y «esta el nombre en la instancia?», y con eso daba VERDE
# a TAKAB_API_OPENROUTER_ENABLED=false y al slug del modelo VACIO — los dos casos que
# el censo cita como razon de existir (T-7.06 y la degradacion silenciosa de la capa
# narrativa). Se ejercita la funcion de verdad, con la instancia simulada: leer el
# texto no habria distinguido una version de la otra.
recorta "$TMP/bandera.sh" "$CONFORMIDAD" funcion huella_de pieza_bandera
cat >"$TMP/escena-bandera.sh" <<'ESCENA'
set -u
cd "$ROOT" || exit 2
. "$ROOT/deploy/cloud/banderas.sh"
registrar() { printf '%s|%s
' "$1" "$3"; }
tf_out() {
  if [ -n "${TF_FALLA:-}" ]; then return 1; fi
  printf '%s' "${TF_VALOR:-}"
}
SSM_OK="${SSM_OK:-1}"
# shellcheck disable=SC1090
. "$BANDERA"
pieza_bandera "$NOMBRE" "ficha de prueba"
ESCENA
huella() { printf '%s' "$1" | sha256sum | cut -c1-12; }
escena() { # <NOMBRE> <ENV_INSTANCIA> [TF_VALOR] [TF_FALLA] -> «VEREDICTO|evidencia»
  NOMBRE="$1" ENV_INSTANCIA="$2" TF_VALOR="${3:-}" TF_FALLA="${4:-}" \
    ROOT="$ROOT" BANDERA="$TMP/bandera.sh" bash "$TMP/escena-bandera.sh" 2>&1
}
veredicto() { # <salida de escena>
  printf '%s' "${1%%|*}"
}
mide() { # <descripcion> <esperado> <salida de escena>
  if [ "$2" = "$(veredicto "$3")" ]; then ok "$1"; else
    fallo "$1"
    printf '        esperado: %s\n        obtenido: %s\n' "$2" "$3" >&2
  fi
}

mide "la bandera puesta a false en la instancia es ROJO (deploy.sh la exporta a true)" \
  ROJO "$(escena OPENROUTER_ENABLED 'TAKAB_API_OPENROUTER_ENABLED false -')"
mide "la bandera puesta a true en la instancia es VERDE" \
  VERDE "$(escena OPENROUTER_ENABLED 'TAKAB_API_OPENROUTER_ENABLED true -')"
mide "el slug del modelo VACIO en la instancia es ROJO" \
  ROJO "$(escena OPENROUTER_MODEL 'TAKAB_API_OPENROUTER_MODEL vacio -')"
mide "el slug del modelo que declara deploy.sh es VERDE" \
  VERDE "$(escena OPENROUTER_MODEL "TAKAB_API_OPENROUTER_MODEL con-valor $(huella anthropic/claude-sonnet-5)")"
mide "OTRO slug del modelo en la instancia es ROJO (desplegada, pero no esta)" \
  ROJO "$(escena OPENROUTER_MODEL "TAKAB_API_OPENROUTER_MODEL con-valor $(huella otro/modelo)")"
mide "el id del secreto VACIO en la instancia es ROJO" \
  ROJO "$(escena OPENROUTER_SECRET_ID 'TAKAB_API_OPENROUTER_SECRET_ID vacio -' takab/dev/openrouter)"
mide "el id del secreto que publica el terraform es VERDE" \
  VERDE "$(escena OPENROUTER_SECRET_ID "TAKAB_API_OPENROUTER_SECRET_ID con-valor $(huella takab/dev/openrouter)" takab/dev/openrouter)"
mide "un id de secreto DISTINTO del que publica el terraform es ROJO" \
  ROJO "$(escena OPENROUTER_SECRET_ID "TAKAB_API_OPENROUTER_SECRET_ID con-valor $(huella takab/dev/otro)" takab/dev/openrouter)"
mide "si el terraform no publica la salida, es ROJO (falta el apply)" \
  ROJO "$(escena OPENROUTER_SECRET_ID "TAKAB_API_OPENROUTER_SECRET_ID con-valor $(huella takab/dev/openrouter)" '' 1)"
mide "ausente en la instancia es AMARILLO (pendiente de desplegar)" \
  AMARILLO "$(escena OPENROUTER_ENABLED 'TAKAB_API_OTRA_COSA true -')"

# Y el valor NO viaja: el informe solo puede nombrar la clase y la huella. Lo mide
# sobre la evidencia que la pieza acaba de escribir, con un valor reconocible.
salida_secreta="$(escena OPENROUTER_SECRET_ID "TAKAB_API_OPENROUTER_SECRET_ID con-valor $(huella takab/dev/CANARIO)" takab/dev/CANARIO)"
if grep -qF 'takab/dev/CANARIO' <<<"$salida_secreta"; then
  fallo "la evidencia imprime el valor de una salida del terraform: push_fcm_application_arn esta marcada sensitive y saldria igual ($salida_secreta)"
else
  ok "la evidencia nombra la salida del terraform, nunca su valor"
fi

# ---------------------------------------------------------------------------
# 2. El heredoc RENDERIZADO: lo que de verdad acaba en /etc/takab/cloud.env
# ---------------------------------------------------------------------------
echo "== el heredoc de deploy.sh se renderiza y no ejecuta lo que cree comentar =="
# El recorte incluye lo que el heredoc NECESITA para renderizarse: tf_obligatorio y
# las salidas del terraform que deploy.sh resuelve ANTES de abrirlo. No es un
# adorno del arnes — es la forma que exige el defecto de abajo («el despliegue
# ABORTA...»): un $( ) que falla DENTRO del heredoc no aborta nada.
{
  extraer_funcion "$DEPLOY" tf_obligatorio
  grep -E '^OPENROUTER_SECRET_ID=' "$DEPLOY"
  sed -n '/^CLOUD_ENV=\$($/,/^)$/p' "$DEPLOY"
} >"$TMP/bloque.sh"
check "el bloque CLOUD_ENV se pudo extraer" "1" \
  "$(grep -c '^CLOUD_ENV=\$($' "$TMP/bloque.sh")"
check "tf_obligatorio se pudo recortar de deploy.sh (si no, el render culparia al heredoc)" "1" \
  "$(grep -c '^tf_obligatorio() {' "$TMP/bloque.sh")"

(
  # Dobles de las dos unicas ordenes que el bloque invoca. No hay red ni AWS: si
  # el bloque llamara a cualquier otra cosa, se veria en el stderr de abajo.
  AWS_REGION="us-east-2"
  CLOUD_TAG="deadbee"
  TF_DEV="infra/terraform/envs/dev"
  tf() { printf 'TF<%s>' "$1"; }
  terraform() { printf '{"events":"q-ev","telemetry":"q-te","backfill":"q-bf","cctv":"q-cc"}\n'; }
  # shellcheck disable=SC1090
  . "$TMP/bloque.sh"
  printf '%s\n' "$CLOUD_ENV"
) >"$TMP/cloud.env" 2>"$TMP/err"

if [ -s "$TMP/err" ]; then
  fallo "renderizar el heredoc escribio en stderr: $(head -3 "$TMP/err" | tr '\n' ' ')"
else
  ok "renderizar el heredoc no escribio en stderr"
fi

# El stderr solo caza la sustitucion que FALLA. Una que funcione —un $(date), o un
# backtick alrededor de una orden que existe— se ejecuta EN SILENCIO y su salida se
# cuela en el fichero. La comprobacion fuerte es esta: un COMENTARIO tiene que
# salir del render exactamente como entro, salvo por quitarle los escapes. Si
# cambia, el shell ejecuto o expandio algo dentro de el.
#
# Cubre mas que la guarda textual de api/tests/test_settings_produccion.py
# (::test_ningun_heredoc_del_despliegue_ejecuta_lo_que_creia_comentar), que busca
# backticks sin escapar: aqui caen tambien los $(...) y los ${...} que un
# comentario no deberia traer y que aquella no ve.
sed -n '/cat <<EOF$/,/^EOF$/p' "$TMP/bloque.sh" | sed '1d;$d' >"$TMP/cuerpo"
grep -n '^[[:space:]]*#' "$TMP/cuerpo" | sed -E 's/\\(.)/\1/g' >"$TMP/com-fuente"
grep -n '^[[:space:]]*#' "$TMP/cloud.env" >"$TMP/com-render"
if diferencias="$(diff "$TMP/com-fuente" "$TMP/com-render")"; then
  ok "ningun comentario del heredoc cambia al renderizarse"
else
  fallo "un comentario del heredoc CAMBIA al renderizarse (el despliegue ejecuto o expandio algo dentro): $(head -6 <<<"$diferencias" | tr '\n' ' ')"
fi

sin_resolver="$(grep -nE '\$\(' "$TMP/cloud.env" || true)"
if [ -n "$sin_resolver" ]; then
  fallo "el cloud.env renderizado trae sustituciones sin resolver: $(tr '\n' ' ' <<<"$sin_resolver")"
else
  ok "no queda ninguna sustitucion sin resolver en el cloud.env renderizado"
fi

echo "== las cuatro lineas que encienden la capa narrativa (T-7.26) =="
# Bandera, modelo, identificador del secreto y tope de gasto. Con cualquiera de
# las tres primeras ausente, resolve_api_key devuelve "" y el dictamen sale con la
# prosa determinista — que es el suelo correcto, pero silencioso.
for linea in \
  "TAKAB_API_OPENROUTER_ENABLED=true" \
  "TAKAB_API_OPENROUTER_MODEL=anthropic/claude-sonnet-5" \
  "TAKAB_API_AI_MONTHLY_CAP_USD=10"; do
  if grep -qxF "$linea" "$TMP/cloud.env"; then
    ok "cloud.env trae $linea"
  else
    fallo "cloud.env NO trae $linea"
  fi
done

# El identificador del secreto se DERIVA del terraform. Comprobarlo contra el
# doble (TF<openrouter_secret_id>) y no contra el literal "takab/dev/openrouter"
# es el punto entero: si alguien lo teclea a mano, el nombre puede divergir del
# ARN que el rol de la instancia tiene permiso de leer, y el sintoma seria un
# AccessDenied que degrada a prosa determinista.
if grep -qxF 'TAKAB_API_OPENROUTER_SECRET_ID=TF<openrouter_secret_id>' "$TMP/cloud.env"; then
  ok "el identificador del secreto se DERIVA de la salida openrouter_secret_id del terraform"
else
  fallo "TAKAB_API_OPENROUTER_SECRET_ID no sale de la salida openrouter_secret_id: $(grep -F 'OPENROUTER_SECRET_ID' "$TMP/cloud.env" || echo '<ausente>')"
fi

# ---------------------------------------------------------------------------
# 2.b El despliegue ABORTA si nadie aplico el terraform
# ---------------------------------------------------------------------------
echo "== sin la salida del terraform, el despliegue ABORTA (no escribe un id vacio) =="
# El defecto que cierra esto, medido el 2026-09-21: con `TAKAB_API_OPENROUTER_SECRET_ID=$(tf
# openrouter_secret_id)` DENTRO del heredoc, la salida que falta deja el hueco vacio,
# el `cat` devuelve 0 y el `set -euo pipefail` de deploy.sh no se entera. El
# despliegue salia rc=0 y la nube quedaba «encendida» apuntando a ningun secreto.
# Por eso se mide el COMPORTAMIENTO y no solo el texto: la forma correcta es la que
# aborta, y la unica manera de saber si aborta es hacerla fallar.
if grep -qE '^[[:space:]]*TAKAB_API_OPENROUTER_SECRET_ID=\$\(tf ' "$DEPLOY"; then
  fallo "TAKAB_API_OPENROUTER_SECRET_ID se resuelve con \$(tf ...) DENTRO del heredoc: ahi un fallo no aborta, deja el valor vacio y sale 0"
else
  ok "el id del secreto no se resuelve con un \$(tf ...) dentro del heredoc"
fi

extraer_funcion "$DEPLOY" tf_obligatorio >"$TMP/tf_obligatorio.sh"
aborta() { # <cuerpo del doble de tf>  -> imprime el rc
  cat >"$TMP/escena-tf.sh" <<ESCENA
set -euo pipefail
tf() { $1; }
. "$TMP/tf_obligatorio.sh"
V="\$(tf_obligatorio openrouter_secret_id "make cloud-apply")"
echo "NO ABORTO: [\$V]"
ESCENA
  bash "$TMP/escena-tf.sh" >"$TMP/escena-tf.out" 2>&1
  printf '%s' "$?"
}
check "si la salida no existe (rc!=0), el despliegue aborta" "1" \
  "$(aborta 'echo "Warning: Output not found" >&2; return 1')"
check "si la salida existe pero viene VACIA, el despliegue aborta" "1" \
  "$(aborta 'printf ""')"
check "con la salida puesta, sigue adelante" "0" \
  "$(aborta 'printf "takab/dev/openrouter"')"
if grep -q 'takab/dev/openrouter' "$TMP/escena-tf.out"; then
  ok "con la salida puesta, tf_obligatorio devuelve su valor"
else
  fallo "tf_obligatorio no devolvio el valor de la salida: $(cat "$TMP/escena-tf.out")"
fi

# ---------------------------------------------------------------------------
# 2.c El tope de gasto: deploy.sh y quota.py no pueden decir cosas distintas
# ---------------------------------------------------------------------------
echo "== el comentario del tope de gasto no contradice a quota.py =="
# El defecto, medido el 2026-09-21: deploy.sh documentaba que 0 seria «sin tope»
# mientras quota.py —del mismo arbol y la misma ficha— implementaba lo contrario. Un
# comentario que contradice al codigo que despliega es peor que ninguno: es el texto
# que lee quien esta editando esa linea, y le habria costado quedarse sin IA creyendo
# que pedia gasto ilimitado. Ningun test cruzaba los dos ficheros.
QUOTA="$ROOT/api/src/takab_api/narrative/quota.py"
tope_linea="$(grep -nE '^TAKAB_API_AI_MONTHLY_CAP_USD=' "$DEPLOY" | head -1)"
tope_valor="${tope_linea#*=}"
bloque_tope=""
if [ -n "$tope_linea" ]; then
  # El comentario ADJUNTO: las lineas `#` contiguas justo encima de la asignacion.
  bloque_tope="$(awk -v fin="${tope_linea%%:*}" '
    NR < fin { if ($0 ~ /^#/) buf = buf $0 "\n"; else buf = "" }
    NR == fin { printf "%s", buf }' "$DEPLOY")"
fi
sin_tope="$(grep -oE '^SIN_TOPE[[:space:]]*=[[:space:]]*-?[0-9.]+' "$QUOTA" | grep -oE '\-?[0-9.]+$')"
predicado="$(sed -n '/^def hay_tope(/,/^$/p' "$QUOTA" | grep -oE 'return cap_usd [<>=!]+ [0-9-]+')"
if [ -z "$tope_linea" ] || [ -z "$bloque_tope" ]; then
  fallo "EL ARNES no encontro TAKAB_API_AI_MONTHLY_CAP_USD ni su comentario en deploy.sh"
elif [ -z "$sin_tope" ] || [ -z "$predicado" ]; then
  fallo "EL ARNES no pudo leer la semantica del tope en quota.py (SIN_TOPE=$sin_tope, predicado='$predicado'): sin eso no puede juzgar el comentario"
else
  check "quota.py sigue diciendo que cualquier tope >= 0 es un tope" "return cap_usd >= 0" "$predicado"
  # Con ese predicado, 0 es un tope de verdad y el despliegue no puede exportarlo
  # mientras la bandera enciende la IA: seria encenderla y apagarla en dos lineas.
  bandera_ia="$(origen_declarado "$DEPLOY" OPENROUTER_ENABLED | cut -f2)"
  if [ "$bandera_ia" = true ] && [ "$tope_valor" = 0 ]; then
    fallo "deploy.sh enciende la IA (OPENROUTER_ENABLED=true) y le pone tope 0, que con hay_tope() la apaga: el despliegue se contradice a si mismo"
  else
    ok "el tope exportado ($tope_valor) no apaga la IA que la bandera enciende"
  fi
  # `-1.0` en python se escribe `-1` en un comentario: vale cualquiera de las dos
  # formas del MISMO numero, y ninguna otra. Si manana quota.py mueve el centinela,
  # esto se pone rojo y hay que venir a reescribir el comentario a sabiendas.
  sin_tope_corto="$(printf '%s' "$sin_tope" | sed -E 's/\.0+$//')"
  if grep -qF -- "$sin_tope" <<<"$bloque_tope" || grep -qF -- "$sin_tope_corto" <<<"$bloque_tope"; then
    ok "el comentario nombra el centinela de «sin tope» que define quota.py ($sin_tope)"
  else
    fallo "el comentario del tope no nombra $sin_tope_corto, que es como quota.py pide gasto ilimitado: quien lo lea no sabra pedirlo"
  fi
  # La mentira concreta que habia: una sola linea que junta el cero con «sin tope» o
  # «ilimitado». Se cuentan las lineas que lo hacen; con el comentario correcto son 0,
  # porque el cero y el ilimitado son dos hechos distintos y no caben en la misma frase.
  mentira="$(grep -iE '(^|[^0-9.-])(0|cero)([^0-9.]|$)' <<<"$bloque_tope" | grep -icE 'sin tope|ilimitad')"
  check "ninguna linea del comentario le atribuye al cero el gasto ilimitado" "0" "$mentira"
fi

echo "== la CLAVE no viaja en cloud.env =="
# TAKAB_API_OPENROUTER_API_KEY esta en PROHIBIDOS_EN_PRODUCCION (settings.py): el
# proceso la resuelve en runtime con el rol de la instancia. Regla de oro 6.
# Se busca la ASIGNACION, no la mencion: los comentarios del heredoc acaban dentro
# de cloud.env —docker compose ignora las lineas que empiezan por #— y uno de ellos
# nombra la variable justamente para explicar por que no esta. Buscar la cadena
# suelta daba rojo sobre el comentario que documenta el acierto.
# (La otra mitad, PROHIBIDOS_EN_PRODUCCION entero contra el TEXTO de deploy.sh, ya
# la cubre api/tests/test_settings_produccion.py::test_el_despliegue_de_hoy_no_lleva_credenciales_de_dev;
# aqui se mide sobre el fichero RENDERIZADO, que es lo que lee el contenedor.)
if grep -qE '^[[:space:]]*TAKAB_API_OPENROUTER_API_KEY=' "$TMP/cloud.env"; then
  fallo "cloud.env define TAKAB_API_OPENROUTER_API_KEY: la clave no puede viajar en el entorno"
else
  ok "cloud.env no define la clave inline"
fi

# ---------------------------------------------------------------------------
# 3. El permiso existe, y no puede divergir del nombre que exporta el despliegue
# ---------------------------------------------------------------------------
echo "== el rol de la instancia puede LEER el secreto de OpenRouter =="
# Sin esta linea de terraform el despliegue "enciende" la IA y la nube sigue
# escribiendo prosa determinista: GetSecretValue responde AccessDenied y
# resolve_api_key degrada. Medido el 2026-09-21: la politica solo cubria los
# secretos de la base y el comodin de gateway-hmac.
check "el nombre del secreto se define UNA sola vez en todo el terraform" "1" \
  "$(grep -rc 'takab/dev/openrouter' "$ROOT/infra/terraform" --include='*.tf' 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')"

arns="$(sed -n '/worker_secret_arns = \[/,/^  \]/p' "$TF_MAIN")"
if grep -qF 'secret:${local.openrouter_secret_id}-*' <<<"$arns"; then
  ok "worker_secret_arns concede el ARN del secreto de OpenRouter"
else
  fallo "worker_secret_arns no incluye el ARN de local.openrouter_secret_id: el rol no podra leer el secreto"
fi
# El `-*` final no es cosmetico: Secrets Manager anade seis caracteres aleatorios
# al ARN, asi que un Resource sin comodin NO casa con el secreto real.
if grep -qE 'secret:\$\{local\.openrouter_secret_id\}[^-]' <<<"$arns"; then
  fallo "el ARN del secreto no termina en '-*': no casaria con el sufijo aleatorio del ARN real"
else
  ok "el ARN cubre el sufijo aleatorio de Secrets Manager"
fi

if grep -qE 'output "openrouter_secret_id"' "$TF_OUT" &&
  sed -n '/output "openrouter_secret_id"/,/^}/p' "$TF_OUT" | grep -qF 'local.openrouter_secret_id'; then
  ok "el terraform publica openrouter_secret_id desde el MISMO local que construye el ARN"
else
  fallo "falta la salida openrouter_secret_id (o no sale de local.openrouter_secret_id): el despliegue tendria que teclear el nombre"
fi

if grep -qF 'takab/dev/openrouter' "$DEPLOY"; then
  fallo "deploy.sh teclea el nombre del secreto en vez de derivarlo del terraform"
else
  ok "deploy.sh no teclea el nombre del secreto"
fi

# ---------------------------------------------------------------------------
# 4. El censo mira el SECRETO: que exista y que el rol lo alcance
# ---------------------------------------------------------------------------
echo "== el censo ve el secreto que no existe y el permiso que no lo cubre =="
# Lo que cierra esto, medido el 2026-09-21: de las dos cosas de las que depende que
# T-7.26 funcione —que el secreto EXISTA y que el rol pueda LEERLO— no medía ninguna
# nadie. El secreto lo crea una persona fuera del terraform (regla de oro 6), asi que
# `terraform plan` sale limpio con o sin el; las banderas solo ven cloud.env; y
# /api/health no dice quien redacta. El censo podia devolver «todo VERDE» con la
# ficha entera inerte. La pieza nueva se ejercita aqui con AWS simulado: no hay red.
recorta "$TMP/secreto.sh" "$CONFORMIDAD" funcion aws_medido sin_medir tf_medido tf_falta_la_salida pieza_secreto_ia
cat >"$TMP/escena-secreto.sh" <<'ESCENA'
set -u
cd "${RAIZ:-$ROOT}" || exit 2
. "$ROOT/deploy/cloud/banderas.sh"
registrar() { printf '%s|%s
' "$1" "$3"; }
AWS_OK=1
AWS_MOTIVO="sin credenciales"
ARN_REAL="arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/openrouter-AbCdEf"
tf_out() {
  case "$1" in
  openrouter_secret_id)
    # El doble habla como terraform: cuando la salida NO ESTA DECLARADA la nombra, y
    # cuando terraform no pudo ni arrancar dice otra cosa. Esa diferencia es justo la
    # que separa una acusacion legitima de una falsa alarma.
    if [ "$CASO" = sin_salida ]; then
      echo 'Error: Output "openrouter_secret_id" not found' >&2
      return 1
    fi
    if [ "$CASO" = tf_mudo ]; then
      echo 'Error: Backend initialization required, please run "terraform init"' >&2
      return 1
    fi
    printf 'takab/dev/openrouter'
    ;;
  db_instance_id) printf 'i-00000000000000001' ;;
  *) return 1 ;;
  esac
}
aws_cli() {
  case "$1 $2" in
  "secretsmanager describe-secret")
    if [ "$CASO" = sin_secreto ]; then
      echo "An error occurred (ResourceNotFoundException) when calling the DescribeSecret operation" >&2
      return 255
    fi
    if [ "$CASO" = secreto_mudo ]; then
      echo "An error occurred (AccessDenied) when calling the DescribeSecret operation" >&2
      return 254
    fi
    printf '%s
' "$ARN_REAL"
    ;;
  "ec2 describe-instances") printf 'arn:aws:iam::000000000000:instance-profile/takab-dev-db
' ;;
  "iam get-instance-profile") printf 'takab-dev-db
' ;;
  "iam list-role-policies")
    # Los tres desenlaces de UNA lectura de IAM viven aqui: contesta, contesta que no
    # hay nada, o no contesta. El tercero NO es el segundo.
    case "$CASO" in
    iam_mudo)
      echo "An error occurred (AccessDenied) when calling the ListRolePolicies operation: User is not authorized to perform iam:ListRolePolicies" >&2
      return 254
      ;;
    sin_politicas) : ;;
    *) printf 'takab-dev-db
' ;;
    esac
    ;;
  "iam get-role-policy")
    case "$CASO" in
    politica_muda)
      echo "An error occurred (AccessDenied) when calling the GetRolePolicy operation" >&2
      return 254
      ;;
    politica_ilegible) printf 'esto no es json
' ;;
    sin_permiso) printf '{"Statement":[{"Effect":"Allow","Action":"s3:PutObject","Resource":"*"}]}
' ;;
    otro_secreto) printf '{"Statement":[{"Effect":"Allow","Action":"secretsmanager:GetSecretValue","Resource":["arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/db/app"]}]}
' ;;
    *) printf '{"Statement":[{"Effect":"Allow","Action":"secretsmanager:GetSecretValue","Resource":["arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/db/app","arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/openrouter-*"]}]}
' ;;
    esac
    ;;
  *) return 1 ;;
  esac
}
# shellcheck disable=SC1090
. "$SECRETO"
pieza_secreto_ia
ESCENA
secreto() { # <CASO> [RAIZ] -> «VEREDICTO|evidencia»
  CASO="$1" RAIZ="${2:-}" ROOT="$ROOT" SECRETO="$TMP/secreto.sh" bash "$TMP/escena-secreto.sh" 2>&1
}
mide "el secreto que NO existe es ROJO" ROJO "$(secreto sin_secreto)"
mide "el secreto que existe y el rol alcanza es VERDE" VERDE "$(secreto bien)"
mide "el rol sin ningun permiso de secretsmanager es ROJO" ROJO "$(secreto sin_permiso)"
mide "el rol que solo alcanza OTROS secretos es ROJO" ROJO "$(secreto otro_secreto)"
mide "sin la salida del terraform es ROJO (falta el apply)" ROJO "$(secreto sin_salida)"
# La MISMA falsa alarma, un tramo antes y en la misma pieza: hasta el 2026-09-21 la
# primera puerta acusaba en ROJO —«el terraform no publica openrouter_secret_id → make
# cloud-apply»— tanto si la salida faltaba como si terraform no habia podido contestar.
# Un `apply` no arregla un `init` que falta ni unas credenciales caducadas.
mide "terraform que no CONTESTA es NO MEDIDO, no ROJO" "NO MEDIDO" "$(secreto tf_mudo)"
caso_mudo="$(secreto tf_mudo)"
case "$caso_mudo" in
*"no se midió"*) ok "el NO MEDIDO del terraform dice que no se midio, y no receta un apply" ;;
*) fallo "el NO MEDIDO del terraform no se explica: $caso_mudo" ;;
esac
case "$caso_mudo" in
*"cloud-apply"*) fallo "un NO MEDIDO receta «make cloud-apply»: eso no arregla un init ni unas credenciales" ;;
*) ok "el NO MEDIDO del terraform no receta lo que no arregla" ;;
esac

# --- NO MEDIDO no es ROJO ----------------------------------------------------------
# El defecto que cierra esto, medido el 2026-09-21 y metido por el arreglo anterior:
# el bucle de las politicas iba sobre `$(aws_cli iam list-role-policies ... 2>/dev/null
# || true)`. Si la llamada fallaba —credenciales caducadas, el perfil sin permiso de
# LEER iam, la region equivocada— la lista salia vacia, que es EXACTAMENTE lo que sale
# cuando el rol no tiene el permiso. El censo acusaba en ROJO de lo que no habia
# mirado, y recetaba `make cloud-apply`, que no arregla unas credenciales. La doctrina
# del propio fichero: NO MEDIDO != ROJO (un fallback no puede ser «ok», T-2.152).
evidencia() { printf '%s' "${1#*|}"; }
no_acusa() { # <descripcion> <salida de escena> <cadena que debe aparecer>
  local ev; ev="$(evidencia "$2")"
  if ! grep -qF "$3" <<<"$ev"; then
    fallo "$1: la evidencia no dice por que no se pudo medir (falta «$3»): $ev"
  elif grep -qF 'make cloud-apply' <<<"$ev"; then
    fallo "$1: un NO MEDIDO receta «make cloud-apply», que no arregla lo que no se pudo leer: $ev"
  else
    ok "$1"
  fi
}

mide "no poder PREGUNTAR por el secreto es NO MEDIDO, no ROJO" "NO MEDIDO" "$(secreto secreto_mudo)"
no_acusa "el NO MEDIDO del secreto nombra el error y no receta un apply" \
  "$(secreto secreto_mudo)" "AccessDenied"
mide "IAM que no contesta es NO MEDIDO, no ROJO" "NO MEDIDO" "$(secreto iam_mudo)"
no_acusa "el NO MEDIDO de IAM nombra el error y no receta un apply" \
  "$(secreto iam_mudo)" "AccessDenied"
mide "una politica que no se puede LEER es NO MEDIDO (es la que podia traer el permiso)" \
  "NO MEDIDO" "$(secreto politica_muda)"
no_acusa "el NO MEDIDO de la politica ilegible la nombra" \
  "$(secreto politica_muda)" "takab-dev-db"
mide "una politica que no se puede INTERPRETAR es NO MEDIDO" "NO MEDIDO" "$(secreto politica_ilegible)"
# Y el otro lado de la misma raya: medido y vacio SI es una acusacion, con su receta.
mide "un rol SIN ninguna politica inline si es ROJO (eso si se midio)" ROJO "$(secreto sin_politicas)"
if grep -qF 'make cloud-apply' <<<"$(evidencia "$(secreto sin_politicas)")"; then
  ok "el ROJO medido si trae la receta que lo arregla"
else
  fallo "el ROJO de «el rol no tiene ninguna politica» no dice que hacer: $(secreto sin_politicas)"
fi

# Y si el despliegue NO enciende la capa narrativa, no hay secreto que exigir: el
# veredicto sale de lo que deploy.sh declara, no de una lista aparte.
mkdir -p "$TMP/apagado/deploy/cloud"
printf 'TAKAB_API_OPENROUTER_ENABLED=false\n' >"$TMP/apagado/deploy/cloud/deploy.sh"
mide "con la capa narrativa apagada en deploy.sh no se exige secreto" \
  VERDE "$(secreto sin_secreto "$TMP/apagado")"

# La LLAMADA, no la mencion: el propio conformidad.sh explica en un comentario por
# que no la hace, y buscar la cadena suelta daba rojo sobre el texto que documenta
# el acierto. Es la misma leccion que ya dejo escrita el bloque de la clave inline.
if grep -qE '^[^#]*(aws|aws_cli)[^#]*secretsmanager[[:space:]]+get-secret-value' "$CONFORMIDAD"; then
  fallo "conformidad.sh llama a get-secret-value: para saber si el secreto existe y si el rol lo alcanza no hace falta traerse la clave a esta maquina"
else
  ok "el censo no lee la clave para comprobar que se puede leer"
fi

if grep -qE '^[[:space:]]*pieza_secreto_ia[[:space:]]*$' "$CONFORMIDAD"; then
  ok "conformidad.sh invoca pieza_secreto_ia (una pieza que no se llama no mide nada)"
else
  fallo "conformidad.sh define pieza_secreto_ia pero NO la invoca: el informe no la traeria"
fi

# ---------------------------------------------------------------------------
# 5. El runbook: sus dos nombres se DERIVAN, y no promete un orden que nadie impone
# ---------------------------------------------------------------------------
echo "== el README del despliegue no puede divergir de lo que ejecuta =="
README="$ROOT/deploy/cloud/README.md"
OPENROUTER_PY="$ROOT/api/src/takab_api/narrative/openrouter.py"
# El nombre que el operador teclea en `create-secret` tiene que ser el mismo que el
# `local` del que sale el ARN del permiso. Si divergen, el rol no alcanza el secreto
# y el sintoma es prosa determinista sin explicacion.
nombre_tf="$(grep -oE 'openrouter_secret_id[[:space:]]*=[[:space:]]*"[^"]+"' "$TF_MAIN" | head -1 | sed -E 's/.*"([^"]+)"/\1/')"
nombre_readme="$(grep -oE -- '--name[[:space:]]+[A-Za-z0-9/_.-]+' "$README" | head -1 | awk '{print $2}')"
if [ -z "$nombre_tf" ]; then
  fallo "EL ARNES no encontro local.openrouter_secret_id en $TF_MAIN"
else
  check "el README crea el secreto con el nombre que declara el terraform" "$nombre_tf" "$nombre_readme"
fi
# Y el campo del JSON, con el que lee resolve_api_key.
campo_py="$(grep -oE 'payload\.get\("[a-z_]+"\)' "$OPENROUTER_PY" | head -1 | sed -E 's/.*"([a-z_]+)".*/\1/')"
if [ -z "$campo_py" ]; then
  fallo "EL ARNES no encontro el campo que lee resolve_api_key en $OPENROUTER_PY"
elif grep -qF "\"$campo_py\":" "$README"; then
  ok "el README usa el campo del JSON que lee resolve_api_key ($campo_py)"
else
  fallo "el README no usa el campo '$campo_py': un secreto con otro nombre de campo resuelve a cadena vacia y degrada sin error"
fi
# Los veredictos que el README promete tienen que ser los que la pieza puede EMITIR, y
# se derivan de conformidad.sh en vez de tecleados: si manana la pieza aprende a decir
# NO MEDIDO en un sitio mas —o deja de decirlo— esto se pone rojo y hay que venir a
# reescribir el parrafo a sabiendas. El defecto que cierra, medido el 2026-09-21: la
# pieza convertia «no pude leer IAM» en una acusacion ROJA y el README solo hablaba de
# VERDE y de ROJO, asi que el operador no tenia donde enterarse de la diferencia.
paso4_readme="$(sed -n '/\[T-7.26\] El secreto de OpenRouter/,/^## /p' "$README")"
veredictos_pieza="$(extraer_funcion "$CONFORMIDAD" pieza_secreto_ia |
  grep -oE 'registrar ("NO MEDIDO"|VERDE|AMARILLO|ROJO)' | sed -E 's/^registrar //; s/"//g' | sort -u)"
if [ -z "$paso4_readme" ] || [ -z "$veredictos_pieza" ]; then
  fallo "EL ARNES no pudo leer el paso 4 del README o los veredictos de pieza_secreto_ia"
else
  while read -r v; do
    if grep -qF "$v" <<<"$paso4_readme"; then
      ok "el README nombra el veredicto «$v», que la pieza puede dar"
    else
      fallo "pieza_secreto_ia puede responder «$v» y el paso 4 del README no lo nombra: quien lea el runbook no sabra que significa"
    fi
  done <<<"$veredictos_pieza"
fi

# El orden que el README subraye tiene que ser uno que algo imponga. El 2026-09-21
# afirmaba que crear el secreto iba ANTES del apply «y no es intercambiable», y era
# falso: el permiso es un ARN interpolado, no hay ningun data source que exija que el
# secreto exista, asi que el apply sale igual de limpio en cualquier orden.
if grep -rqE 'data[[:space:]]+"aws_secretsmanager_secret"' "$ROOT/infra/terraform" --include='*.tf'; then
  ok "el terraform SI depende de que el secreto exista (un data source lo exige): el README puede pedir ese orden"
else
  paso4="$(sed -n '/\[T-7.26\] El secreto de OpenRouter/,/^## /p' "$README")"
  if [ -z "$paso4" ]; then
    fallo "EL ARNES no encontro el paso 4 del README: no puede juzgar lo que afirma"
  else
    afirma="$(grep -icE 'existe ANTES del|el orden importa y no es intercambiable' <<<"$paso4")"
    check "el README no exige un orden entre crear el secreto y el apply que el terraform no impone" "0" "$afirma"
  fi
fi

if [ "$fallos" -ne 0 ]; then
  printf '\n%d prueba(s) FALLARON\n' "$fallos" >&2
  exit 1
fi
printf '\ntodo en verde\n'
