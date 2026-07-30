#!/usr/bin/env bash
# Tests de `merge_env.py`, la pieza que impide que re-aprovisionar un gabinete
# BORRE su configuración.
#
# Por qué existe: `provision_gateway.sh` instalaba el edge.env con `sudo tee`, que
# sobrescribe el archivo ENTERO. El script solo genera 3 claves (HMAC, endpoint,
# PIN) pero un gabinete vivo tenía 15: estación, host de SeedLink, rutas de los
# certificados, la calibración MEDIDA del sensor... Correrlo sobre gw-dev-0001
# habría dejado el gabinete sin sensor y sin calibración, y el runbook de alta de
# estación te manda correr justamente ese script.
#
# Corre con: bash infra/scripts/tests/test_merge_env.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MERGE="$HERE/../merge_env.py"
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

cat >"$TMP/managed" <<'EOF'
TAKAB_EDGE_HMAC_KEY=nueva-clave
TAKAB_EDGE_MQTT_ENDPOINT=nuevo.endpoint.amazonaws.com
TAKAB_EDGE_LOCAL_API_PIN=654321
EOF

echo "== sin archivo previo: escribe solo lo gestionado =="
python3 "$MERGE" --managed "$TMP/managed" --out "$TMP/out1" 2>/dev/null
check "3 claves" "3" "$(grep -c . "$TMP/out1")"
check "el PIN nuevo está" "TAKAB_EDGE_LOCAL_API_PIN=654321" "$(grep '^TAKAB_EDGE_LOCAL_API_PIN=' "$TMP/out1")"

echo "== con archivo previo: CONSERVA lo que no gestiona y ACTUALIZA lo suyo =="
cat >"$TMP/existing" <<'EOF'
# configuración del gabinete
TAKAB_EDGE_STATION=R4F74
TAKAB_EDGE_HMAC_KEY=clave-vieja
TAKAB_EDGE_SEEDLINK_HOST=192.168.3.92
TAKAB_EDGE_SIGNAL__VEL_SENSITIVITY_MS_PER_COUNT=1.234e-09
TAKAB_EDGE_SITE_NAME="Sitio Dev Puebla"
EOF
python3 "$MERGE" --managed "$TMP/managed" --existing "$TMP/existing" --out "$TMP/out2" 2>/dev/null

check "la calibración MEDIDA sobrevive" \
  "TAKAB_EDGE_SIGNAL__VEL_SENSITIVITY_MS_PER_COUNT=1.234e-09" \
  "$(grep '^TAKAB_EDGE_SIGNAL__VEL_SENSITIVITY_MS_PER_COUNT=' "$TMP/out2")"
check "la estación sobrevive" "TAKAB_EDGE_STATION=R4F74" "$(grep '^TAKAB_EDGE_STATION=' "$TMP/out2")"
check "el nombre del sitio sobrevive (con comillas)" \
  'TAKAB_EDGE_SITE_NAME="Sitio Dev Puebla"' "$(grep '^TAKAB_EDGE_SITE_NAME=' "$TMP/out2")"
check "el comentario sobrevive" "# configuración del gabinete" "$(head -1 "$TMP/out2")"
check "la clave gestionada se ACTUALIZA" "TAKAB_EDGE_HMAC_KEY=nueva-clave" \
  "$(grep '^TAKAB_EDGE_HMAC_KEY=' "$TMP/out2")"
check "sin duplicar la clave actualizada" "1" "$(grep -c '^TAKAB_EDGE_HMAC_KEY=' "$TMP/out2")"
check "las gestionadas que faltaban se AÑADEN" \
  "nuevo.endpoint.amazonaws.com" \
  "$(grep '^TAKAB_EDGE_MQTT_ENDPOINT=' "$TMP/out2" | cut -d= -f2)"
check "no se pierde ninguna clave previa" "5" \
  "$(grep -c '^TAKAB_EDGE_' "$TMP/existing")"
check "el resultado tiene las 5 previas + 2 nuevas" "7" "$(grep -c '^TAKAB_EDGE_' "$TMP/out2")"

echo "== el orden previo se respeta (un diff debe ser mínimo y legible) =="
check "la primera clave sigue siendo la misma" "TAKAB_EDGE_STATION=R4F74" \
  "$(grep '^TAKAB_EDGE_' "$TMP/out2" | head -1)"

echo "== no filtra secretos a stdout =="
SALIDA="$(python3 "$MERGE" --managed "$TMP/managed" --existing "$TMP/existing" --out "$TMP/out3" 2>/dev/null)"
case "$SALIDA" in
*nueva-clave* | *654321*) fallo "stdout contiene un secreto" ;;
*) ok "stdout limpio de secretos" ;;
esac

echo "== el archivo resultante nace en 0600 =="
check "permisos" "600" "$(stat -c '%a' "$TMP/out3")"

echo "== el aprovisionamiento escribe la IDENTIDAD del gabinete =="
# Por qué se comprueba aquí: `gateway_id` NO estaba en el edge.env del Pi. El gabinete
# se identificaba con el DEFAULT horneado en settings.py ("gw-dev-0001"), que coincidía
# por casualidad con el nombre del primer gabinete real. La segunda estación habría
# publicado como la primera: datos atribuidos al sitio y al tenant equivocados, y
# colisión de client-id MQTT. La identidad tiene que nacer del aprovisionamiento.
PROV="$HERE/../provision_gateway.sh"
for clave in TAKAB_EDGE_GATEWAY_ID TAKAB_EDGE_DEV_MODE TAKAB_EDGE_HMAC_KEY TAKAB_EDGE_MQTT_ENDPOINT TAKAB_EDGE_LOCAL_API_PIN; do
  if grep -q "$clave=%s\|$clave=false" "$PROV"; then
    ok "provision_gateway.sh escribe $clave"
  else
    fallo "provision_gateway.sh NO escribe $clave"
  fi
done

if [ "$fallos" -ne 0 ]; then
  printf '\n%d prueba(s) FALLARON\n' "$fallos" >&2
  exit 1
fi
printf '\ntodo en verde\n'
