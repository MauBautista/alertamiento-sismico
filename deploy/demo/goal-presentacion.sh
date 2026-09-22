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
# **Un NO MEDIDO no es un aprobado.** Sale 0 sólo si todo el nivel A está en verde; el
# nivel B se cuenta aparte y se dice en voz alta. Un fallback no puede ser «ok» (T-2.152).
set -u

CONSOLA="${TAKAB_CONSOLA_URL:-https://16-58-11-196.sslip.io}"
PANEL="${TAKAB_DEMO_PANEL_URL:-http://raspberry-cerebro.local:8080}"
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ" || exit 2

VERDES=0 ROJOS=0 NO_MEDIDOS=0
verde()    { printf '  \033[32m✓\033[0m %s\n' "$1"; VERDES=$((VERDES + 1)); }
rojo()     { printf '  \033[31m✗\033[0m %s\n' "$1"; ROJOS=$((ROJOS + 1)); }
no_medido(){ printf '  \033[33m•\033[0m NO MEDIDO · %s\n' "$1"; NO_MEDIDOS=$((NO_MEDIDOS + 1)); }
titulo()   { printf '\n\033[1m%s\033[0m\n' "$1"; }

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
  no_medido "sin etiqueta no se puede comparar"
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

titulo "A3 · Censo de conformidad · sin un solo ROJO"
CENSO="$(bash deploy/cloud/conformidad.sh --permitir-no-medido 2>&1)"
RESUMEN_CENSO="$(printf '%s' "$CENSO" | grep '^RESUMEN:' | head -1)"
if [ -z "$RESUMEN_CENSO" ]; then
  no_medido "el censo no llegó a dar resumen (¿sesión de AWS caducada? dura 1 hora)"
elif printf '%s' "$CENSO" | grep -q '^ROJO'; then
  rojo "$RESUMEN_CENSO"
  printf '%s' "$CENSO" | grep '^ROJO' | sed 's/^/      /'
else
  verde "$RESUMEN_CENSO"
fi

titulo "A4 · Las banderas que ESTA presentación necesita encendidas"
# Se comprueban contra la INSTANCIA (lo que el censo ya midió), no contra deploy.sh:
# lo que gobierna la demostración es lo que corre, no lo que se pretendía desplegar.
for b in CONSOLE_SCOPE_ENFORCED OPENROUTER_ENABLED CATALOG_USGS_ENABLED; do
  linea="$(printf '%s' "$CENSO" | grep "bandera TAKAB_API_$b" | head -1)"
  case "$linea" in
  VERDE*true*) verde "$b encendida en la instancia" ;;
  "") no_medido "$b · el censo no la midió (¿no está en deploy.sh? ¿sin sesión de AWS?)" ;;
  *) rojo "$b · ${linea#* · }" ;;
  esac
done

titulo "A5 · La consola SERVIDA dice lo que el guion promete"
# Comprobación barata y sorprendentemente fuerte: se baja el bundle que la nube sirve HOY
# y se buscan dentro las frases que el acto 2 y el acto 3 enseñan. Si una falta, lo que
# está desplegado NO es lo que se va a contar — y eso no se ve mirando el repositorio.
IDX="$(curl -fsS --max-time 20 "$CONSOLA/" 2>/dev/null)"
JS="$(printf '%s' "$IDX" | grep -oE '/assets/index-[A-Za-z0-9_-]+\.js' | head -1)"
if [ -z "$JS" ]; then
  no_medido "no se pudo localizar el bundle de la consola en $CONSOLA/"
else
  BUNDLE="$(curl -fsS --max-time 40 "$CONSOLA$JS" 2>/dev/null)"
  if [ -z "$BUNDLE" ]; then
    no_medido "no se pudo bajar $JS"
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
  no_medido "el panel no contesta en $PANEL — ¿fuera de la red del gabinete?"
else
  campo() { printf '%s' "$ESTADO" | jq -r "$1 | if . == null then empty else . end" 2>/dev/null; }
  [ "$(campo .last_tier)" = "normal" ] && verde "nivel en reposo" || rojo "el gabinete NO está en reposo (last_tier=$(campo .last_tier))"
  [ "$(campo .test_mode.active)" = "false" ] && verde "modo prueba del WR-1 DESARMADO" || rojo "modo prueba ARMADO: el pulso no publicaría a la nube"
  [ "$(campo .alert_latched)" = "false" ] && verde "sin enclavado vivo" || rojo "enclavado vivo: el acto 3 no se distinguiría del anterior"
  [ "$(campo .cloud.online)" = "true" ] && verde "el gabinete ve la nube (rtt $(campo .cloud.mqtt_rtt_ms | cut -c1-5) ms)" || rojo "el gabinete no publica: habría sirena pero no incidente"
  g="$(campo .seedlink.gaps)"; pk="$(campo .seedlink.packets_seen)"
  [ "${g:-1}" = "0" ] && verde "SeedLink: $pk paquetes, 0 huecos" || rojo "SeedLink con ${g:-?} huecos"
  printf '%s' "$ESTADO" | jq -e '[.relays[]? | select(.activated)] | length == 0' >/dev/null 2>&1 &&
    verde "relés en reposo" || rojo "hay relés accionados: el acto 2 no puede enseñar «nada se movió»"
fi

# ───────────────────────── B · lo que exige una persona ─────────────────────────

titulo "B · Lo funcional · EXIGE SESIÓN, y por eso aquí NO se aprueba"
no_medido "dictamen con fotos, mapa de sacudida y espectrograma — generarlo pide rol inspector con MFA"
no_medido "firma del dictamen — sólo el rol inspector la tiene (sign_dictamen), y pide segundo factor"
no_medido "cierre del incidente por clasificación — pide un rol con classify_incident"
no_medido "aviso al teléfono con la pantalla bloqueada — pide el Pixel y el pulso del WR-1"
no_medido "simulacro disparado — regla de oro 8: lo dispara una persona con sesión viva, nunca una hora"
no_medido "acierto de catálogo USGS sobre un incidente real — pide un sismo, o la reproducción"
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
printf '  A (automático): %d ✓ · %d ✗   ·   B+C: %d NO MEDIDO\n' "$VERDES" "$ROJOS" "$NO_MEDIDOS"
if [ "$ROJOS" -eq 0 ]; then
  echo "  → El nivel A está entero. Lo que vas a enseñar ES lo que corre en la nube."
  echo "    Lo que falta NO lo puede medir una máquina: córrelo con"
  echo "      bash deploy/demo/guion.sh --full"
  exit 0
fi
echo "  → NO estás listo: arregla los ✗ de arriba antes de poner a nadie delante."
echo "    Un ✗ en A significa que lo que vas a contar y lo que corre no coinciden."
exit 1
