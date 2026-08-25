#!/usr/bin/env bash
# Genera los subsets woff2 de la landing y los deja en src/assets/fonts/.
# Se corre UNA vez (o al cambiar de fuentes) y el resultado se COMMITEA:
# el build de producción no descarga nada de la red (regla del presupuesto:
# cero orígenes externos en runtime).
#
# Requiere: curl, uvx (uv). fonttools+brotli se resuelven al vuelo con uvx.
#
# Fuentes (todas OFL, desde el repo oficial google/fonts):
#   - Saira Condensed 700  — display de marca (sustituta oficial de Aero)
#   - Archivo 400/600      — cuerpo (variable → instanciada a estáticas)
#   - JetBrains Mono 400   — telemetría/datos (variable → instanciada)
set -euo pipefail
cd "$(dirname "$0")/.."

DEST=src/assets/fonts
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$DEST"

GF=https://github.com/google/fonts/raw/main/ofl

# Latin básico + español MX + signos que usa el copy (« » – — · … ≥ © ®).
UNICODES='U+0020-007E,U+00A1,U+00A9,U+00AB,U+00AE,U+00B7,U+00BB,U+00BF,U+00C1,U+00C9,U+00CD,U+00D1,U+00D3,U+00DA,U+00DC,U+00E1,U+00E9,U+00ED,U+00F1,U+00F3,U+00FA,U+00FC,U+2013,U+2014,U+2018,U+2019,U+201C,U+201D,U+2026,U+2265'

subset() { # subset <ttf-entrada> <woff2-salida>
  uvx --from fonttools --with brotli pyftsubset "$1" \
    --unicodes="$UNICODES" \
    --layout-features='kern,liga,ccmp,locl,mark,mkmk' \
    --flavor=woff2 --output-file="$2"
  echo "  $(basename "$2") → $(stat -c%s "$2") bytes"
}

instance() { # instance <ttf-variable> <ttf-salida> <ejes...>
  local in=$1 out=$2; shift 2
  uvx --from fonttools --with brotli fonttools varLib.instancer -q -o "$out" "$in" "$@"
}

echo "· Saira Condensed 700 (estática)"
curl -fsSL "$GF/sairacondensed/SairaCondensed-Bold.ttf" -o "$TMP/saira.ttf"
subset "$TMP/saira.ttf" "$DEST/saira-condensed-700.woff2"

echo "· Archivo variable → 400 y 600"
curl -fsSL "$GF/archivo/Archivo%5Bwdth%2Cwght%5D.ttf" -o "$TMP/archivo-var.ttf"
instance "$TMP/archivo-var.ttf" "$TMP/archivo-400.ttf" wght=400 wdth=100
instance "$TMP/archivo-var.ttf" "$TMP/archivo-600.ttf" wght=600 wdth=100
subset "$TMP/archivo-400.ttf" "$DEST/archivo-400.woff2"
subset "$TMP/archivo-600.ttf" "$DEST/archivo-600.woff2"

echo "· JetBrains Mono variable → 400"
curl -fsSL "$GF/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf" -o "$TMP/jbmono-var.ttf"
instance "$TMP/jbmono-var.ttf" "$TMP/jbmono-400.ttf" wght=400
subset "$TMP/jbmono-400.ttf" "$DEST/jetbrains-mono-400.woff2"

echo "Listo. Total:"
du -bc "$DEST"/*.woff2 | tail -1
