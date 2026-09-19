#!/usr/bin/env bash
# Corre un flujo de Maestro con las credenciales del `.env` de esta carpeta.
#
# POR QUÉ EXISTE, y no es azúcar: **Maestro NO hereda el entorno del shell.**
# Solo recibe variables por `-e CLAVE=valor`. Los flujos declaraban
#
#     env:
#       OCCUPANT_EMAIL: ${OCCUPANT_EMAIL}
#
# que es una AUTORREFERENCIA: Maestro la evalúa en su propio ámbito, donde la
# variable todavía no existe, y el resultado es la cadena literal "undefined".
# Eso se teclea tal cual en el formulario y Cognito responde «Nombre de usuario o
# contraseña incorrectos» — un fallo que se lee como credenciales mal sembradas y
# no lo es. Costó cuatro corridas encontrarlo el 2026-08-09, con las credenciales
# buenas todo el tiempo. Los subflujos llevan ahora un `assertTrue` que lo caza
# en el primer segundo; esto lo evita de raíz.
#
# Uso:  .maestro/run.sh 04-panico-quorum.yaml
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
[ $# -ge 1 ] || { echo "uso: $0 <flujo.yaml> [args de maestro]" >&2; exit 2; }

# [T-7.52] El fichero de entorno se elige, y por eso existe `.env.e2e`: desde
# `D-34` los flujos corren contra el SITIO DEL ARNÉS, no contra Puebla, y sus
# identidades son otras. `.env` sigue siendo el de siempre para no romper lo
# acreditado; `TAKAB_MAESTRO_ENV=.env.e2e` apunta al del arnés.
ENTORNO="${TAKAB_MAESTRO_ENV:-.env}"

if [ ! -f "$AQUI/$ENTORNO" ]; then
  echo "ERROR: falta $AQUI/$ENTORNO — lo escribe 'make cloud-mobile-users'." >&2
  echo "       La fuente de verdad es el secreto takab/dev/mobile/users." >&2
  exit 1
fi

set -a; . "$AQUI/$ENTORNO"; set +a

faltan=()
for v in OCCUPANT_EMAIL OCCUPANT_PASSWORD TACTICO_EMAIL TACTICO_PASSWORD SITE_CODE; do
  [ -n "${!v:-}" ] || faltan+=("$v")
done
if [ ${#faltan[@]} -gt 0 ]; then
  echo "ERROR: $ENTORNO no define: ${faltan[*]}" >&2
  exit 1
fi

# ⚠️ [T-7.52] Los E2E NUNCA contra el sitio del gabinete real. `site-dev` es
# Puebla, y el arnés que prepara la fase CIERRA todos los incidentes abiertos del
# sitio: correr aquí contra él es cerrar incidentes de operación. La guarda dura
# vive en `guarda.sql`; ésta sólo evita gastar una corrida para descubrirlo.
if [ "${SITE_CODE:-}" = "site-dev" ]; then
  echo "ERROR: SITE_CODE=site-dev es el sitio del gabinete REAL (Puebla)." >&2
  echo "       Los E2E van contra el sitio del arnés: usa TAKAB_MAESTRO_ENV=.env.e2e" >&2
  echo "       y siémbralo con 'make cloud-e2e-site'." >&2
  exit 1
fi

# ⚠️ [T-7.56] CERRAR LA SESIÓN DE COGNITO ANTES DE CADA FLUJO.
#
# `launchApp: clearState` limpia la app — **pero no la cookie de la Hosted UI**,
# que vive en el navegador del sistema (Custom Tabs). Medido el 2026-09-18: tras
# correr `01b` (ocupante), el `05a` (táctico) entró **como el ocupante**, porque
# `/oauth2/authorize` redirige solo con la sesión de antes. El síntoma engaña —
# «no encuentro la pestaña LISTA»— porque las pestañas se derivan del rol, así que
# parece un fallo de la app y es una identidad equivocada.
#
# El propio `login-tactico.yaml` ya avisaba del redirect, pero nada lo resolvía.
# `D-35` lo hace más probable: hay DOS identidades tácticas y la corrida de
# aceptación cambia de identidad al menos dos veces.
#
# ⚠️ Se cierra SOLO la sesión de Cognito, por su endpoint `/logout`. Nada de
# borrar los datos del navegador: estos flujos corren en un teléfono **PERSONAL**,
# y una corrida de pruebas no tiene por qué llevarse las sesiones de nadie.
if [ -n "${HOSTED_UI_LOGOUT_URL:-}" ]; then
  adb shell am start -a android.intent.action.VIEW -d "$HOSTED_UI_LOGOUT_URL" >/dev/null 2>&1 || true
  sleep 5
  adb shell input keyevent KEYCODE_HOME >/dev/null 2>&1 || true
else
  echo "AVISO: $ENTORNO no define HOSTED_UI_LOGOUT_URL." >&2
  echo "       Sin eso, un flujo que cambie de identidad entrará con la ANTERIOR:" >&2
  echo "       la cookie de Cognito sobrevive al clearState de la app (T-7.56)." >&2
fi

FLUJO="$1"; shift
case "$FLUJO" in /*) ;; *) FLUJO="$AQUI/$FLUJO" ;; esac

maestro test \
  -e OCCUPANT_EMAIL="$OCCUPANT_EMAIL" \
  -e OCCUPANT_PASSWORD="$OCCUPANT_PASSWORD" \
  -e TACTICO_EMAIL="$TACTICO_EMAIL" \
  -e TACTICO_PASSWORD="$TACTICO_PASSWORD" \
  -e SITE_CODE="$SITE_CODE" \
  "$@" "$FLUJO"
