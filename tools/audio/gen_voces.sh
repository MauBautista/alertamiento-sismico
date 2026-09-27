#!/usr/bin/env bash
# Genera las voces del catálogo de punta a punta (T-9.10 · D-40).
#
#   1. Verifica el modelo de voz por sha256 FIJADO (no confía en la caché); si falta o
#      no cuadra, lo descarga de Hugging Face y vuelve a verificar.
#   2. Sintetiza cada voz de voces.json con Piper (semilla fija) en un entorno AISLADO
#      de uv: piper-tts es GPL y NO entra en ningún proyecto del repo.
#   3. Normaliza (−16 LUFS, ≤ −1 dBTP, cola ≤ 100 ms) y copia a sus rutas.
#   4. Reescribe shared/audio/MANIFEST.json midiendo y lo verifica.
#
# Uso:  tools/audio/gen_voces.sh
# Requiere: uv, curl, sha256sum, jq.
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAIZ="$(cd "${AQUI}/../.." && pwd)"
VOCES="${AQUI}/voces.json"
CACHE="${PIPER_VOICES_DIR:-${HOME}/.cache/piper-voices}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PIPER_PKG="$(jq -r .piper.paquete "$VOCES")"
ORT_PKG="$(jq -r .piper.onnxruntime "$VOCES")"
MODELO="$(jq -r .modelo.nombre "$VOCES")"
URL_BASE="$(jq -r .modelo.url_base "$VOCES")"
declare -A HUELLA=(
  ["${MODELO}.onnx"]="$(jq -r .modelo.onnx_sha256 "$VOCES")"
  ["${MODELO}.onnx.json"]="$(jq -r .modelo.json_sha256 "$VOCES")"
)
PY_AUDIO=(uv run --no-project --python 3.12
  --with numpy==2.5.3 --with scipy==1.18.1 --with pyloudnorm==0.2.0 python)
PY_PIPER=(uv run --no-project --python 3.12 --with "$PIPER_PKG" --with "$ORT_PKG" python)

cuadra() { [ -f "$1" ] && [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ]; }

mkdir -p "$CACHE"
for F in "${!HUELLA[@]}"; do
  if ! cuadra "${CACHE}/${F}" "${HUELLA[$F]}"; then
    echo "→ ${F}: falta o no cuadra el sha256; descargando"
    curl -fsSL --retry 3 -o "${CACHE}/${F}.part" "${URL_BASE}${F}"
    mv "${CACHE}/${F}.part" "${CACHE}/${F}"
    cuadra "${CACHE}/${F}" "${HUELLA[$F]}" || {
      echo "✗ ${F}: el sha256 descargado NO coincide con el fijado (${HUELLA[$F]})" >&2
      exit 1
    }
  fi
  echo "✓ ${F} sha256=${HUELLA[$F]}"
done

N="$(jq '.voces | length' "$VOCES")"
for ((i = 0; i < N; i++)); do
  V="$(jq -c ".voces[$i]" "$VOCES")"
  ID="$(jq -r .id <<<"$V")"
  FICHERO="$(jq -r .fichero <<<"$V")"
  echo "── ${ID}"
  "${PY_PIPER[@]}" "${AQUI}/sintetiza.py" "${CACHE}/${MODELO}.onnx" "${TMP}/crudo.wav" \
    --texto "$(jq -r .texto <<<"$V")" \
    --semilla "$(jq -r .semilla <<<"$V")" \
    --length-scale "$(jq -r .length_scale <<<"$V")" \
    --noise-scale "$(jq -r .noise_scale <<<"$V")" \
    --noise-w-scale "$(jq -r .noise_w_scale <<<"$V")"
  "${PY_AUDIO[@]}" "${AQUI}/normaliza.py" "${TMP}/crudo.wav" "${TMP}/${FICHERO}"
  MAX="$(jq -r .max_duracion_s <<<"$V")"
  "${PY_AUDIO[@]}" -c "
import sys, wave
w = wave.open(sys.argv[1]); d = w.getnframes() / w.getframerate()
sys.exit(f'✗ {sys.argv[1]}: {d:.3f} s > {sys.argv[2]} s' if d > float(sys.argv[2]) else 0)
" "${TMP}/${FICHERO}" "$MAX"
  while read -r RUTA; do
    mkdir -p "$(dirname "${RAIZ}/${RUTA}")"
    cp "${TMP}/${FICHERO}" "${RAIZ}/${RUTA}"
    echo "  → ${RUTA}"
  done < <(jq -r '.rutas[]' <<<"$V")
done

"${PY_AUDIO[@]}" "${AQUI}/manifiesto.py"
python3 "${AQUI}/verifica_manifiesto.py" "$RAIZ"
