#!/usr/bin/env bash
# [T-7.52 · D-34] Aplica o retira el SITIO DEL ARNÉS de los E2E móviles en la nube.
#
# Va APARTE de `deploy.sh` por la misma razón que `demo_red.sh`: un sitio de
# pruebas re-sembrado en cada despliegue acaba pareciendo inventario de verdad.
#
#   infra/scripts/e2e_site.sh up     # siembra site-e2e-900 y su zona
#   infra/scripts/e2e_site.sh down   # lo retira; el sitio REAL de Puebla no se toca
#
# ⚠️ EL `down` NO BORRA POR FECHA NI POR PATRÓN LIBRE: borra exactamente el
# `site_id` del arnés. Un `DELETE … WHERE code LIKE 'site-e2e-%'` sobre la base de
# la nube es la clase de comando que un día se lleva por delante algo que no
# esperaba, y aquí sólo hay un sitio que retirar.
set -euo pipefail

SITIO="d1000000-0000-0000-0000-000000000900"

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ACCION="${1:-}"
case "$ACCION" in
  up|down) ;;
  *) echo "uso: $(basename "$0") up|down" >&2; exit 2 ;;
esac

# shellcheck source=/dev/null
. "$RAIZ/infra/scripts/lib/tunel.sh"
abrir_tunel "${TAKAB_E2E_SITE_PUERTO:-5440}"

sec="$(credenciales_db)"
export PGPASSWORD
PGPASSWORD="$(jq -r .password <<<"$sec")"
PSQL=(psql -h 127.0.0.1 -p "$TUNEL_PUERTO" -U "$(jq -r .username <<<"$sec")" \
      -d "$(jq -r .dbname <<<"$sec")" -v ON_ERROR_STOP=1)

if [[ "$ACCION" == "up" ]]; then
  echo "→ sembrando el sitio del arnés (site-e2e-900)"
  "${PSQL[@]}" -f "$RAIZ/db/seeds/e2e_harness.sql"
else
  # ⚠️ Guardia de simetría con `guarda.sql`: si alguien le hubiera puesto un
  # gabinete a este sitio, ya no es el sitio del arnés y retirarlo se llevaría
  # inventario por delante.
  gabinetes="$("${PSQL[@]}" -tAc "SELECT count(*) FROM gateways WHERE site_id = '$SITIO'")"
  if [[ "$gabinetes" != "0" ]]; then
    echo "  ✗ el sitio del arnés tiene $gabinetes gabinete(s): ya no es un sitio de arnés." >&2
    echo "    Retirarlo borraría inventario. Revísalo a mano." >&2
    exit 1
  fi
  echo "→ retirando el sitio del arnés"
  "${PSQL[@]}" -c "DELETE FROM sites WHERE site_id = '$SITIO'"
fi

echo
echo "→ sitios que verá /fleet:"
"${PSQL[@]}" -tA -c "
  SELECT s.code || ' · ' || s.name ||
         ' · gabinetes=' || (SELECT count(*) FROM gateways g WHERE g.site_id = s.site_id)
    FROM sites s ORDER BY s.code"
