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

if [ ! -f "$AQUI/.env" ]; then
  echo "ERROR: falta $AQUI/.env — lo escribe 'make cloud-mobile-users'." >&2
  echo "       La fuente de verdad es el secreto takab/dev/mobile/users." >&2
  exit 1
fi

set -a; . "$AQUI/.env"; set +a

faltan=()
for v in OCCUPANT_EMAIL OCCUPANT_PASSWORD TACTICO_EMAIL TACTICO_PASSWORD SITE_CODE; do
  [ -n "${!v:-}" ] || faltan+=("$v")
done
if [ ${#faltan[@]} -gt 0 ]; then
  echo "ERROR: el .env no define: ${faltan[*]}" >&2
  exit 1
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
