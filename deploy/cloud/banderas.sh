# deploy/cloud/banderas.sh — [T-7.26] De donde sale el censo de banderas.
#
# Una BANDERA es un ajuste que el DESPLIEGUE fija con un booleano literal, pisando
# el default que trae el codigo. Esa clase de linea es, por definicion, el sitio
# donde "el codigo dice una cosa y el sistema otra" — el fallo que T-7.06 encontro
# con TAKAB_API_CONSOLE_SCOPE_ENFORCED y el que el informe de conformidad existe
# para ver. Por eso el censo se DERIVA de deploy.sh en vez de enumerarse:
#
#   - Enumerado, el 2026-09-21 ya estaba corto. Llevaba desde T-2.60.a sin mirar
#     TAKAB_API_OPS_METRICS_ENABLED, de quien depende que la alarma
#     GhostGatewaysAlive tenga datos, y nadie se habia enterado porque un censo
#     corto no falla: se calla.
#   - Derivado, anadir una bandera a deploy.sh basta para que el informe la mida.
#     Lo que sigue escribiendose a mano es el POR QUE de cada una (FICHA_BANDERA
#     en conformidad.sh), y eso lo vigila infra/scripts/tests/test_censo_banderas.sh.
#
# Lo que llega por $(tf ...) NO es bandera: su ausencia significa "vacio", no
# "false", y se declara aparte (FICHA_NO_DERIVADA).
#
# Se SOURCEA; no se ejecuta.

# banderas_declaradas <ruta de deploy.sh>
#   Imprime, una por linea y ordenadas, los nombres SIN el prefijo TAKAB_API_.
#   Devuelve 1 si no encuentra ninguna: un despliegue sin banderas no existe, asi
#   que cero resultados significa que el derivador se quedo ciego (fichero movido,
#   formato cambiado) y quien llama tiene que decirlo en ROJO. Un fallback no
#   puede ser «ok» (T-2.152).
banderas_declaradas() {
  local ruta="${1:?banderas_declaradas exige la ruta de deploy.sh}" nombres
  nombres="$(grep -oE '^[[:space:]]*TAKAB_API_[A-Z0-9_]+=(true|false)[[:space:]]*$' "$ruta" |
    sed -E 's/^[[:space:]]*TAKAB_API_//; s/=(true|false)[[:space:]]*$//' | sort -u)"
  [ -n "$nombres" ] || return 1
  printf '%s\n' "$nombres"
}

# origen_declarado <ruta de deploy.sh> <NOMBRE sin prefijo>
#   De donde sale el VALOR que el despliegue escribira en /etc/takab/cloud.env.
#   Imprime dos campos separados por un TAB:
#
#     literal <valor>   el despliegue lo fija a pelo (`=true`, `=anthropic/...`)
#     tf      <salida>  sale de `$(tf <salida>)` o de `$(tf_obligatorio <salida>)`:
#                       el valor esperado hay que preguntarselo al terraform, no se
#                       puede leer del fichero
#     opaco   <texto>   cualquier otra sustitucion (una tuberia, un python3, una
#                       variable que no se asigna aqui): el valor esperado NO es
#                       derivable, y quien llame tiene que DECIRLO en vez de dar por
#                       bueno lo que haya
#
#   Devuelve 1 si el nombre no esta en el fichero.
#
#   Sigue UN nivel de indireccion dentro del mismo fichero: `TAKAB_API_X=${X}` en el
#   heredoc mas `X="$(tf_obligatorio salida)"` arriba se resuelve a `tf salida`. Esa
#   forma no es cosmetica — es la unica que aborta cuando falta la salida del
#   terraform, porque un `$(...)` que falla DENTRO del heredoc deja el hueco vacio y
#   devuelve 0 (ver la cabecera de tf_obligatorio en deploy.sh) —, asi que el
#   derivador tiene que entenderla o el censo se queda ciego justo donde mas importa.
#
#   Por que existe. Hasta T-7.26 el censo comparaba NOMBRES: una bandera puesta a
#   `false` en la instancia salia igual de verde que puesta a `true`, que es
#   exactamente el fallo de T-7.06 que el censo dice vigilar. Para comparar valores
#   hace falta saber cual es el esperado, y eso lo dice el despliegue — derivado,
#   no tecleado en una segunda lista que acabaria divergiendo.
origen_declarado() {
  local ruta="${1:?origen_declarado exige la ruta de deploy.sh}"
  local n="${2:?origen_declarado exige el NOMBRE sin prefijo}"
  _origen_de_asignacion "$ruta" "TAKAB_API_${n}" 2
}

# _origen_de_asignacion <ruta> <NOMBRE COMPLETO> <saltos de indireccion que quedan>
_origen_de_asignacion() {
  local ruta="$1" var="$2" saltos="$3" linea valor ref
  # La ULTIMA, no la primera: si hubiera dos asignaciones al mismo nombre, la que
  # acaba en cloud.env es la de abajo.
  linea="$(grep -E "^[[:space:]]*${var}=" "$ruta" | tail -1)"
  [ -n "$linea" ] || return 1
  valor="${linea#*=}"
  valor="${valor%"${valor##*[![:space:]]}"}" # sin espacios al final
  case "$valor" in
  \"*\") valor="${valor#\"}"; valor="${valor%\"}" ;;
  esac
  case "$valor" in
  '$(tf '*')' | '$(tf_obligatorio '*')')
    printf 'tf\t%s\n' "$(printf '%s' "$valor" | awk '{ gsub(/[)"]/, "", $2); print $2 }')"
    return 0
    ;;
  '${'*'}' | '$'[A-Za-z_]*)
    ref="${valor#\$}"
    ref="${ref#\{}"
    ref="${ref%\}}"
    case "$ref" in
    *[!A-Za-z0-9_]*) ;; # no es una referencia limpia: cae a opaco
    *)
      if [ "$saltos" -gt 0 ] && _origen_de_asignacion "$ruta" "$ref" "$((saltos - 1))"; then
        return 0
      fi
      ;;
    esac
    printf 'opaco\t%s\n' "$valor"
    return 0
    ;;
  *'$'* | *'`'*)
    printf 'opaco\t%s\n' "$valor"
    return 0
    ;;
  esac
  printf 'literal\t%s\n' "$valor"
}
