#!/usr/bin/env bash
# Guarda de licencias del árbol (T-3.10.b · D-24).
#
# Falla el build si aparece copyleft fuerte —GPL o AGPL— en el árbol transitivo de
# cualquier proyecto Python del repo, o si aparece por su nombre alguno de los paquetes
# explícitamente prohibidos. La lógica vive en `ci/licencias.py`; esto solo la corre donde
# hay que correrla y junta los veredictos.
#
# POR QUÉ SE CORRE UNA VEZ POR PROYECTO Y NO UNA SOLA VEZ
# Cada uno tiene su propio venv y su propio `uv.lock`, y un prohibido puede entrar en uno
# sin tocar el otro. Correrlo solo en `api/` dejaría al gabinete sin vigilar, que es
# justamente donde vive el CCTV.
#
# NO se para al primer fallo: interesa el informe COMPLETO. Enterarse de un problema por
# proyecto y por corrida convierte una revisión en tres.
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARDA="${RAIZ}/ci/licencias.py"
AVISOS="${RAIZ}/THIRD_PARTY_NOTICES.txt"
FALLO=0

echo "→ guarda de licencias (D-24: cero AGPL/GPL en el árbol)"

for PROYECTO in api edge; do
  DIR="${RAIZ}/${PROYECTO}"
  [ -d "$DIR" ] || continue
  echo "── ${PROYECTO}"
  # `--notices` solo en el último para que el archivo no se pise a medias; se resuelve
  # abajo, concatenando. Aquí cada proyecto escribe el suyo.
  ( cd "$DIR" && uv run python "$GUARDA" \
      --lock "${DIR}/uv.lock" \
      --notices "${DIR}/.notices.part" ) || FALLO=1
done

# Los pesos se revisan UNA vez sobre el repo entero: no pertenecen a ningún venv, y por eso
# ningún escáner de paquetes los ve.
echo "── pesos .onnx"
( cd "${RAIZ}/api" && uv run python "$GUARDA" --onnx-root "$RAIZ" >/dev/null ) || FALLO=1

# THIRD_PARTY_NOTICES.txt GENERADO, nunca escrito a mano.
{
  echo "TAKAB Ailert — software de terceros"
  echo "GENERADO por ci/check-licenses.sh. No editar a mano."
  echo
  for PROYECTO in api edge; do
    PARTE="${RAIZ}/${PROYECTO}/.notices.part"
    [ -f "$PARTE" ] || continue
    echo "### ${PROYECTO}"
    tail -n +5 "$PARTE"
    echo
    rm -f "$PARTE"
  done
} > "$AVISOS"
echo "── THIRD_PARTY_NOTICES.txt generado ($(wc -l < "$AVISOS") líneas)"

if [ "$FALLO" -ne 0 ]; then
  echo "✗ ABORTADO: hay licencias no permitidas en el árbol." >&2
  echo "  D-24 no admite AGPL/GPL en NINGÚN entorno, tampoco para comparar." >&2
  exit 1
fi
echo "✓ licencias en orden"
