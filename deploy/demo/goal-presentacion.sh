#!/bin/bash
# deploy/demo/goal-presentacion.sh — [T-7.28] El GOAL de la presentación al cliente.
#
# Contesta UNA pregunta: **¿lo que voy a enseñar está de verdad en lo que corre la nube?**
#
# ---------------------------------------------------------------------------
# POR QUÉ NO SE PUEDE CONTESTAR SONDEANDO ENDPOINTS
# ---------------------------------------------------------------------------
# La API desplegada **no publica su OpenAPI**, y es deliberado: `main.py` pone
# `docs_url`, `redoc_url` y `openapi_url` a `None` cuando el perfil es público. Así que
# «confirmar que la función X está en la nube» no se hace pidiendo `/openapi.json`
# —eso devuelve el HTML de la consola, medido el 2026-09-22— sino **derivándolo de la
# etiqueta**: `/api/health` declara qué commit corre, y desde ahí se compara el árbol.
#
# Ésa es la comprobación central de este guion, y es fuerte: si el diff entre la etiqueta
# desplegada y HEAD está vacío **para las rutas que entran en las imágenes**, entonces todo
# lo que hay en el repositorio está en la nube. No hace falta enumerar funciones.
#
# ---------------------------------------------------------------------------
# TRES NIVELES, Y NO SE MEZCLAN
# ---------------------------------------------------------------------------
#   A · AUTOMÁTICO      lo que este guion mide solo, sin nadie delante.
#   B · CON SESIÓN      lo funcional: exige un token y, casi todo, el segundo factor.
#                       Aquí se DECLARA como NO MEDIDO. Nunca se pinta de verde.
#   C · NO SE PUEDE     lo que el sistema no hace (invariantes y decisiones). Se imprime
#                       para que nadie lo prometa, no para que se compruebe.
#
# **Un NO MEDIDO no es un aprobado.** Esa frase estaba escrita aquí desde el principio y
# el código no la cumplía: el veredicto miraba SÓLO los ✗, así que con la nube sana y el
# gabinete fuera de la LAN salía 0 diciendo «el nivel A está entero» sin haber medido una
# sola pieza del gabinete. Un hueco de medición no es un suspenso —el sistema puede estar
# perfecto— pero tampoco es un aprobado, y por eso no cabe ni en 1 ni en 0:
#
#   0  LISTO · todo el nivel A en verde.
#   1  NO ESTÁS LISTO · hay ✗: lo desplegado DISCREPA de lo que vas a contar.
#   2  el guion ni arrancó (no pudo entrar a la raíz del repositorio).
#   3  NO SE PUDO COMPROBAR · sin un solo ✗, pero el nivel A tiene huecos de medición:
#      lo que hay que arreglar es el INSTRUMENTO (credencial, red, gabinete), no el sistema.
#
# El nivel B se cuenta aparte y se dice en voz alta. Un fallback no puede ser «ok» (T-2.152).
set -u

CONSOLA="${TAKAB_CONSOLA_URL:-https://16-58-11-196.sslip.io}"
PANEL="${TAKAB_DEMO_PANEL_URL:-http://raspberry-cerebro.local:8080}"
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ" || exit 2

# DOS contadores de NO MEDIDO, y la diferencia es el veredicto entero. El del nivel B es
# un pendiente HUMANO declarado a propósito (hace falta una sesión viva y un segundo
# factor); el del nivel A es un hueco del INSTRUMENTO, que sí impide firmar. Estaban
# sumados en un solo entero y rotulados «B+C» —falso por los dos lados: el nivel C no
# incrementa nada, es un `cat` de texto, y el A lo incrementaba seis veces—, así que un
# panel que no contestaba se disfrazaba de «eso ya lo cubre guion.sh» y el guion salía 0.
VERDES=0 ROJOS=0 NO_MEDIDOS_A=0 NO_MEDIDOS_B=0
verde()      { printf '  \033[32m✓\033[0m %s\n' "$1"; VERDES=$((VERDES + 1)); }
rojo()       { printf '  \033[31m✗\033[0m %s\n' "$1"; ROJOS=$((ROJOS + 1)); }
no_medido_a(){ printf '  \033[33m•\033[0m NO MEDIDO (A) · %s\n' "$1"; NO_MEDIDOS_A=$((NO_MEDIDOS_A + 1)); }
no_medido_b(){ printf '  \033[33m•\033[0m NO MEDIDO · %s\n' "$1"; NO_MEDIDOS_B=$((NO_MEDIDOS_B + 1)); }
titulo()     { printf '\n\033[1m%s\033[0m\n' "$1"; }

# ───────────────────────────── A · lo que se mide solo ─────────────────────────────

titulo "A1 · La nube contesta y declara qué corre"
SALUD="$(curl -fsS --max-time 15 "$CONSOLA/api/health" 2>/dev/null)"
if [ -z "$SALUD" ]; then
  rojo "la API no contesta en $CONSOLA/api/health — sin esto no hay nada que confirmar"
  TAG=""
else
  TAG="$(printf '%s' "$SALUD" | jq -r '.build // empty')"
  ESQ="$(printf '%s' "$SALUD" | jq -r '.esquema.estado // "?"')"
  [ -n "$TAG" ] && verde "la nube corre la etiqueta $TAG" || rojo "el health no declara 'build'"
  [ "$ESQ" = "al_dia" ] &&
    verde "esquema al día ($(printf '%s' "$SALUD" | jq -r '.esquema.aplicada'))" ||
    rojo "esquema en estado '$ESQ': hay migraciones sin aplicar"
fi

titulo "A2 · PARIDAD · lo que voy a enseñar ES lo que corre"
if [ -z "$TAG" ]; then
  no_medido_a "sin etiqueta no se puede comparar"
elif ! git cat-file -e "${TAG}^{commit}" 2>/dev/null; then
  rojo "la nube corre $TAG y ese commit no está en este repositorio: despliegue desde otro árbol"
else
  # La lista de rutas que VIAJAN se deriva del propio despliegue y de los Dockerfile.
  # Se reutiliza la del censo en vez de copiarla: dos listas acaban divergiendo.
  # shellcheck source=/dev/null
  . <(sed -n '/^rutas_que_llegan_a_la_nube()/,/^}$/p' deploy/cloud/conformidad.sh)
  RUTAS="$(rutas_que_llegan_a_la_nube)"
  # shellcheck disable=SC2086  # la lista va sin comillas a propósito: son rutas
  if git diff --quiet "${TAG}..HEAD" -- $RUTAS; then
    verde "TODO lo del repositorio está en la nube (diff vacío en lo que entra en las imágenes)"
  else
    rojo "la nube NO tiene estos cambios → make cloud-images && make cloud-deploy"
    # shellcheck disable=SC2086
    git diff --name-only "${TAG}..HEAD" -- $RUTAS | sed 's/^/      /' | head -12
  fi
fi

titulo "A3 · Censo de conformidad · ni un ROJO, y lo que no sea VERDE se declara"
# El veredicto se DERIVA de los números del resumen, no de la ausencia de una línea.
# Mirando sólo `grep -q '^ROJO'`, este bloque pintaba ✓ VERDE sobre un resumen que
# decía dentro de sí mismo «8 AMARILLO · 5 NO MEDIDO» (medido el 2026-09-22): el ✓ y su
# propio texto se desmentían. Y los AMARILLO que se tragaba no son inocentes —«ausente
# en /etc/takab/cloud.env → pendiente de desplegar», «la imagen desplegada no conoce esa
# migración», «el APK instalado es ANTERIOR al último cambio de mobile/» son desajustes
# reales—, mezclados con piezas que el censo simplemente no pudo leer. Distinguirlos
# línea a línea desde aquí sería duplicar la clasificación del censo, así que no se
# colapsan: se declaran SIN MEDIR y se vuelcan para que las lea quien va a presentar.
CENSO="$(bash deploy/cloud/conformidad.sh --permitir-no-medido 2>&1)"
RC_CENSO=$?
RESUMEN_CENSO="$(printf '%s' "$CENSO" | grep '^RESUMEN:' | head -1)"
# ⚠️ FALLA CERRADO al parsear. Un `sed` que no casa devuelve la LÍNEA ENTERA, y entonces
# `[ "$A" -gt 0 ]` no es falso: es un error de bash que el `if` trata como falso y cae
# otra vez en el verde — el mismo agujero, reabierto por la puerta de atrás. Con
# `[[ =~ ]]` o hay cuatro números o no hay veredicto. El separador va como `[^0-9]*`
# a propósito: lo que el censo garantiza son los rótulos, no los bytes del `·`.
RE_CENSO='^RESUMEN: ([0-9]+) VERDE [^0-9]*([0-9]+) AMARILLO [^0-9]*([0-9]+) ROJO [^0-9]*([0-9]+) NO MEDIDO'
if [ -z "$RESUMEN_CENSO" ]; then
  no_medido_a "el censo no llegó a dar resumen (salió $RC_CENSO): sin resumen no hay nada que leer"
elif [[ ! "$RESUMEN_CENSO" =~ $RE_CENSO ]]; then
  no_medido_a "el censo dio un resumen que no sé leer: $RESUMEN_CENSO"
# El número Y la línea: si el resumen y las filas se contradicen, gana la evidencia más
# alarmante. Un ROJO que sólo aparece en una fila sigue siendo un ROJO.
elif [ "${BASH_REMATCH[3]}" -gt 0 ] || printf '%s' "$CENSO" | grep -q '^ROJO'; then
  rojo "$RESUMEN_CENSO"
  printf '%s' "$CENSO" | grep '^ROJO' | sed 's/^/      /'
elif [ "${BASH_REMATCH[2]}" -gt 0 ] || [ "${BASH_REMATCH[4]}" -gt 0 ]; then
  no_medido_a "$RESUMEN_CENSO — no es todo VERDE: lee estas líneas antes de firmar"
  printf '%s' "$CENSO" | grep -E '^(AMARILLO|NO MEDIDO)' | sed 's/^/      /'
else
  verde "$RESUMEN_CENSO"
fi

titulo "A4 · Las banderas que ESTA presentación necesita encendidas"
# Se comprueban contra la INSTANCIA (lo que el censo ya midió), no contra deploy.sh:
# lo que gobierna la demostración es lo que corre, no lo que se pretendía desplegar.
#
# ⚠️ Se clasifica por VEREDICTO + HECHO, nunca por «no empieza por VERDE». El comodín
# `*) rojo` convertía en ✗ la línea que dice literalmente «instancia no medida», o sea
# acusaba al sistema de un desajuste por una ceguera del censo: el 2026-09-22 las tres
# banderas salieron ✗ y el guion cerró con «lo que vas a contar y lo que corre no
# coinciden» mientras las tres estaban en `true` en la instancia, leídas por SSM. Eso es
# lo que entrena a ignorar un rojo. `pieza_bandera` emite AMARILLO en cuatro situaciones y
# sólo dos son cegueras: las otras dos siguen en ✗ porque son desajustes reales —«NO
# exportada en deploy.sh» (el default de Settings es `False`, o sea apagada) y «ausente en
# /etc/takab/cloud.env → pendiente de desplegar»—. Por eso se casa el TEXTO y no el color.
for b in CONSOLE_SCOPE_ENFORCED OPENROUTER_ENABLED CATALOG_USGS_ENABLED; do
  linea="$(printf '%s' "$CENSO" | grep "bandera TAKAB_API_$b" | head -1)"
  # `registrar` imprime «veredicto · pieza · evidencia»; la pieza ya es $b, así que
  # repetirla era el nombre dos veces en el mismo renglón. Dos recortes, no uno.
  ev="${linea#* · }"; ev="${ev#* · }"
  case "${linea%% · *}" in
  VERDE)
    case "$ev" in
    # Único VERDE que sirve: el censo leyó la instancia y trae «true». Un VERDE con
    # «false» o «vacía» significa que deploy.sh y la instancia coinciden en tenerla
    # APAGADA — coincidir no es lo que pide esta presentación, que necesita encendida.
    *"la instancia la trae en true"*) verde "$b encendida en la instancia" ;;
    # Clase `tf`: el censo compara por huella sha256 y NO publica el valor (hay salidas
    # marcadas `sensitive`). Coincide, pero desde aquí no se puede afirmar «encendida».
    *"trae ESE valor"*) no_medido_a "$b · el censo la compara por huella y no publica el valor: coincide, pero no puedo afirmar que esté ENCENDIDA" ;;
    *) rojo "$b · $ev — coinciden, pero NO en «true»" ;;
    esac
    ;;
  "") no_medido_a "$b · el censo no la midió (¿no está en deploy.sh? ¿no llegó a esa pieza?)" ;;
  AMARILLO)
    case "$ev" in
    *"instancia no medida"*) no_medido_a "$b · el censo NO pudo leer la instancia: esto NO dice que la bandera esté apagada" ;;
    *"no sabe evaluar"*) no_medido_a "$b · $ev" ;;
    *) rojo "$b · $ev" ;;
    esac
    ;;
  "NO MEDIDO") no_medido_a "$b · $ev" ;;
  # ROJO del censo y cualquier veredicto que no reconozca: ✗. Se falla cerrado.
  *) rojo "$b · $ev" ;;
  esac
done

titulo "A5 · La consola SERVIDA dice lo que el guion promete"
# Comprobación barata y sorprendentemente fuerte: se baja el bundle que la nube sirve HOY
# y se buscan dentro las frases que el acto 2 y el acto 3 enseñan. Si una falta, lo que
# está desplegado NO es lo que se va a contar — y eso no se ve mirando el repositorio.
IDX="$(curl -fsS --max-time 20 "$CONSOLA/" 2>/dev/null)"
JS="$(printf '%s' "$IDX" | grep -oE '/assets/index-[A-Za-z0-9_-]+\.js' | head -1)"
if [ -z "$JS" ]; then
  no_medido_a "no se pudo localizar el bundle de la consola en $CONSOLA/"
else
  BUNDLE="$(curl -fsS --max-time 40 "$CONSOLA$JS" 2>/dev/null)"
  if [ -z "$BUNDLE" ]; then
    no_medido_a "no se pudo bajar $JS"
  else
    faltan=""
    # ⚠️ CON ACENTOS, y no es un detalle: la primera versión de esta guarda los quitó
    # suponiendo que el minificador los escapaba, y dio DOS falsos rojos contra un
    # despliegue sano. Medido el 2026-09-22 sobre el bundle servido: «SIN ACTUACIÓN» y
    # «PROTÉJASE» aparecen tal cual, una vez cada una. Una guarda sobre cadenas se
    # escribe mirando el artefacto, no recordándolo.
    for frase in "UMBRAL INSTRUMENTAL" "SIN ACTUACIÓN" "PROTÉJASE" "SIN COBERTURA"; do
      printf '%s' "$BUNDLE" | grep -qF "$frase" || faltan="$faltan «$frase»"
    done
    [ -z "$faltan" ] &&
      verde "el bundle servido ($JS, $(printf '%s' "$BUNDLE" | wc -c) B) trae las frases del guion" ||
      rojo "el bundle servido NO trae:$faltan — lo desplegado no dice lo que se va a contar"
  fi
fi

titulo "A6 · El gabinete, listo para los actos 1, 2 y 3"
ESTADO="$(curl -fsS --max-time 10 "$PANEL/api/status" 2>/dev/null)"
if [ -z "$ESTADO" ]; then
  no_medido_a "el panel no contesta en $PANEL — ¿fuera de la red del gabinete?"
else
  campo() { printf '%s' "$ESTADO" | jq -r "$1 | if . == null then empty else . end" 2>/dev/null; }
  # ⚠️ `campo` aplana `null` a cadena VACÍA, y el panel usa `null` justamente para decir
  # «no se pudo medir» (local_api: «`None` = "no se pudo medir", que la UI pinta S/D»).
  # Comparar contra un valor esperado y mandar el resto al `else` imprimía la acusación
  # con la evidencia vacía dentro — «el gabinete NO está en reposo (last_tier=)» — y era
  # falsa: un gabinete recién arrancado aún no tiene ninguna decisión del motor de
  # reglas, y `last_tier` es `None` hasta la primera. Tres estados, no dos.
  # Se comprueba uno por uno porque NO todos los campos son nulables: `test_mode.active`
  # y `cloud.online` los sustituye el edge por `false` cuando no hay instantánea, así que
  # su vacío sólo puede venir de un panel que no los declara.
  tier="$(campo .last_tier)"
  case "$tier" in
  normal) verde "nivel en reposo" ;;
  "") no_medido_a "el panel no declara last_tier (S/D): el nivel del gabinete NO se midió" ;;
  *) rojo "el gabinete NO está en reposo (last_tier=$tier)" ;;
  esac
  case "$(campo .test_mode.active)" in
  false) verde "modo prueba del WR-1 DESARMADO" ;;
  true) rojo "modo prueba ARMADO: el pulso no publicaría a la nube" ;;
  *) no_medido_a "el panel no declara test_mode: no se puede saber si el pulso sería real" ;;
  esac
  latch="$(campo .alert_latched)"
  case "$latch" in
  false) verde "sin enclavado vivo" ;;
  "") no_medido_a "el panel no declara alert_latched (S/D): el enclavado NO se midió" ;;
  *) rojo "enclavado vivo: el acto 3 no se distinguiría del anterior" ;;
  esac
  rtt="$(campo .cloud.mqtt_rtt_ms | cut -c1-5)"
  case "$(campo .cloud.online)" in
  # El rtt puede venir nulo con el enlace arriba (aún sin medir un ida y vuelta): se
  # rotula S/D en vez de dejar «rtt  ms», que es un hueco disfrazado de medición.
  true) verde "el gabinete ve la nube (rtt ${rtt:-S/D} ms)" ;;
  false) rojo "el gabinete no publica: habría sirena pero no incidente" ;;
  *) no_medido_a "el panel no declara cloud.online: no se midió si el gabinete publica" ;;
  esac
  g="$(campo .seedlink.gaps)"; pk="$(campo .seedlink.packets_seen)"
  case "$g" in
  0) verde "SeedLink: $pk paquetes, 0 huecos" ;;
  # Antes: `${g:-1}` convertía el ausente en un suspenso y lo explicaba con «SeedLink
  # con ? huecos» — un ✗ cuya propia evidencia decía que no la tenía.
  "") no_medido_a "el panel no declara la sección seedlink (S/D): el flujo del sensor NO se midió" ;;
  *) rojo "SeedLink con $g huecos" ;;
  esac
  # ⚠️ UNA LISTA VACÍA NO DICE «NADA SE MOVIÓ». El edge documenta que `relays: []`
  # significaba cuatro cosas distintas bajo un solo rótulo —módulo parado, lectura
  # reventada en marcha, el DUEÑO DE LOS PINES que no contesta, o nadie sabe— y por eso
  # publica el hermano `relays_status.reason`. Contando sólo los activados, un gabinete
  # cuyo estado eléctrico no se leyó salía ✓ «relés en reposo» sobre el subsistema que
  # toca sirena, gas, ascensores y puertas. `guion.sh` ya lo lee así; esto se quedó atrás.
  act="$(printf '%s' "$ESTADO" | jq '[.relays[]? | select(.activated)] | length' 2>/dev/null)"
  motivo="$(campo .relays_status.reason)"
  if [ "${act:-1}" != 0 ]; then
    rojo "hay relés accionados ($act): el acto 2 no puede enseñar «nada se movió»"
  else
    case "$motivo" in
    ok | no_actuators_installed) verde "relés en reposo (reason=$motivo)" ;;
    # El estado eléctrico SÍ se midió: lo que falló es el perfil del sitio, así que la
    # lista va sin filtrar. El conteo de activados es fiable — es un verde legítimo.
    config_error) verde "relés en reposo; el perfil del sitio no se pudo leer y la lista va SIN filtrar" ;;
    "") rojo "el panel no declara relays_status: una lista de relés vacía NO significa reposo" ;;
    *) rojo "cadena de relés en '$motivo': la lista vacía no prueba el reposo — revísala antes de prometer una sirena" ;;
    esac
  fi
fi

# ───────────────────────── B · lo que exige una persona ─────────────────────────

titulo "B · Lo funcional · EXIGE SESIÓN, y por eso aquí NO se aprueba"
no_medido_b "dictamen con fotos, mapa de sacudida y espectrograma — generarlo pide rol inspector con MFA"
no_medido_b "firma del dictamen — sólo el rol inspector la tiene (sign_dictamen), y pide segundo factor"
no_medido_b "cierre del incidente por clasificación — pide un rol con classify_incident"
no_medido_b "aviso al teléfono con la pantalla bloqueada — pide el Pixel y el pulso del WR-1"
no_medido_b "simulacro disparado — regla de oro 8: lo dispara una persona con sesión viva, nunca una hora"
no_medido_b "acierto de catálogo USGS sobre un incidente real — pide un sismo, o la reproducción"
printf '     → los cubre \033[1mbash deploy/demo/guion.sh --full\033[0m, que cronometra los cuatro actos\n'

# ─────────────────────── C · lo que NO se puede prometer ───────────────────────

titulo "C · Lo que NO existe · imprímelo antes de hablar, no después"
cat <<'NO'
  · MAGNITUD del sismo: TAKAB no la calcula y no es un pendiente — es INVARIANTE
    (blueprint §14). Lo que sí mide es la INTENSIDAD EN EL INMUEBLE: PGA/PGV pico con
    su instante y su umbral con procedencia (§5 del dictamen). La magnitud, si aparece,
    es de CATÁLOGO EXTERNO, post-hoc, y se pinta con su fuente y su hora de consulta.
  · INTENSIDAD MACROSÍSMICA (MMI): no se reporta, a propósito, y el papel lo declara.
  · VOCEO HABLADO: no existe ni una grabación. El gabinete puede sonar por sirena y
    estrobo; el voceo por altavoz está apagado. ⚠️ Y el PDF del reporte de simulacro
    lo IMPRIME por sitio («SIN VOCEO»): desmiente por escrito lo que se prometa en voz alta.
  · TONO OFICIAL DEL SASMEX: reservado y ausente a propósito — es de CIRES y reproducirlo
    sin licencia no es un detalle estético.
  · SISMOLÓGICO NACIONAL: no se consulta para correlacionar. La atribución de sus cifras
    sigue sin cerrar (D-06 / T-2.149) y el dictamen lo declara.
  · SIRENA POR HARDWARE CON EL GABINETE APAGADO: diseñada y decidida, NO construida (G-04).
NO

# ───────────────────────────────── veredicto ─────────────────────────────────

printf '\n\033[1m── VEREDICTO ──────────────────────────────────────────────────────────\033[0m\n'
# El nivel C no se cuenta porque no se mide: es un `cat` de texto que se imprime para que
# nadie prometa lo que no existe. Rotularlo «B+C» escondía que el contador llevaba dentro
# los huecos del nivel A.
printf '  A (automático): %d ✓ · %d ✗ · %d SIN MEDIR   ·   B (exige una persona): %d NO MEDIDO\n' \
  "$VERDES" "$ROJOS" "$NO_MEDIDOS_A" "$NO_MEDIDOS_B"
if [ "$ROJOS" -eq 0 ] && [ "$NO_MEDIDOS_A" -eq 0 ]; then
  echo "  → El nivel A está entero. Lo que vas a enseñar ES lo que corre en la nube."
  echo "    Lo que falta NO lo puede medir una máquina: córrelo con"
  echo "      bash deploy/demo/guion.sh --full"
  exit 0
fi
# Con ✗ y huecos a la vez manda el ✗: la evidencia más alarmante gana, y la causa de cada
# cosa se dice por separado. La frase única de antes —«un ✗ significa que no coinciden»—
# se imprimía también cuando los ✗ venían de piezas que el censo no había podido leer, y
# entonces era FALSA: mandaba a redesplegar una nube correcta.
if [ "$ROJOS" -gt 0 ]; then
  echo "  → NO estás listo: arregla los ✗ de arriba antes de poner a nadie delante."
  echo "    Un ✗ en A: lo desplegado DISCREPA de lo que vas a contar → arregla el SISTEMA."
  if [ "$NO_MEDIDOS_A" -gt 0 ]; then
    echo "    Y además quedan $NO_MEDIDOS_A piezas del nivel A sin medir: eso no acusa a nadie,"
    echo "    pero tampoco te cubre. Míralas cuando los ✗ estén cerrados."
  fi
  exit 1
fi
#: Concuerda en número. Un veredicto que dice «1 piezas» se lee como una plantilla a medio
#: rellenar, y lo primero que se duda de una plantilla es la cifra que trae dentro.
if [ "$NO_MEDIDOS_A" -eq 1 ]; then CUANTAS="1 pieza del nivel A se quedó"; else CUANTAS="$NO_MEDIDOS_A piezas del nivel A se quedaron"; fi
echo "  → NO HE PODIDO COMPROBARLO: ni un solo ✗, pero $CUANTAS"
echo "    sin medir. Un NO MEDIDO no es un aprobado: no sé decirte que estés listo."
echo "    Lo que hay que arreglar aquí es el INSTRUMENTO, no el sistema — credencial de AWS,"
echo "    red del gabinete, panel que no contesta — y volver a correr esto."
exit 3
