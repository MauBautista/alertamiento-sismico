#!/usr/bin/env bash
# [T-7.11] Aplica o retira la RED DE DEMOSTRACIÓN en la nube.
#
# Va APARTE de `deploy.sh` a propósito: una red de adorno que se re-siembra en
# cada despliegue acaba pareciendo inventario de verdad, y el censo de la purga
# (`T-7.10`) la conservaría sin saber qué es. Se pone antes de una demostración y
# se quita después.
#
#   infra/scripts/demo_red.sh up     # los 3 sitios + nombres presentables
#   infra/scripts/demo_red.sh down   # los retira; la estación REAL no se toca
#
# El alcance es por CONVENCIÓN de códigos, nunca por fecha, y el `down` lleva una
# guardia que aborta si la estación real cayera dentro.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ACCION="${1:-}"
case "$ACCION" in
  up)   FICHERO="$RAIZ/db/seeds/demo_red.sql" ;;
  down) FICHERO="$RAIZ/db/seeds/demo_red_down.sql" ;;
  *)    echo "uso: $(basename "$0") up|down" >&2; exit 2 ;;
esac

# shellcheck source=/dev/null
. "$RAIZ/infra/scripts/lib/tunel.sh"
abrir_tunel "${TAKAB_DEMO_RED_PUERTO:-5439}"

sec="$(credenciales_db)"
export PGPASSWORD
PGPASSWORD="$(jq -r .password <<<"$sec")"
PSQL=(psql -h 127.0.0.1 -p "$TUNEL_PUERTO" -U "$(jq -r .username <<<"$sec")" \
      -d "$(jq -r .dbname <<<"$sec")" -v ON_ERROR_STOP=1)

echo "→ $ACCION: $(basename "$FICHERO")"
"${PSQL[@]}" -f "$FICHERO"

echo
echo "→ la flota que verá /fleet:"
"${PSQL[@]}" -tA -c "
  SELECT s.code || ' · ' || s.name ||
         CASE WHEN s.code LIKE 'site-sim-%' THEN '   [DEMO]' ELSE '   [REAL]' END
  FROM sites s
  JOIN gateways g ON g.site_id = s.site_id
  ORDER BY (s.code LIKE 'site-sim-%'), s.code"
