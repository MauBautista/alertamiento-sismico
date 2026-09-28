#!/usr/bin/env bash
# [T-9.35 · D-43] Baja de SENSORES FANTASMA en la nube, con auditoría.
#
# Un fantasma es un sensor dado de alta que NUNCA reportó: `status = 'active'`, sin
# `calibration_source` y sin una sola fila en `waveform_features_1s`. Con el dictamen
# v2 deja su sitio en AMARILLO para siempre (un activo sin calibrar impide el VERDE).
# `diagnostico_sensores.sh` los señala; esto los retira.
#
# Por qué un guion y no la consola: la consola no ofrece la baja de sensores (su DAR
# DE BAJA es de usuarios); sólo existe `DELETE /sensors/{id}`, que exige un token de
# gestión. Esto hace lo mismo que `queries/sensors.py::_RETIRE` —retiro LÓGICO: la
# fila se queda y sus features históricas siguen consultables— y deja la misma
# huella, `verb = 'sensor_retire'`, en `audit_log`, con quién lo corrió y por qué.
#
# Tres cerrojos, y los tres están en el SQL, no en la buena fe de quien lo corre:
#   1. Sin `--aplicar` todo termina en ROLLBACK: por defecto sólo ENSEÑA.
#   2. Hay que NOMBRAR los sitios: no existe «todos».
#   3. La condición de fantasma se evalúa DENTRO de la transacción que escribe: un
#      sensor que reportó una sola fila, o que tiene calibración, no se toca aunque
#      ayer fuera fantasma.
#
# Uso (lo corre Mauricio con `!`, primero sin `--aplicar`):
#
#     infra/scripts/retira_sensores_fantasma.sh site-dev pue-pruebas-01
#     infra/scripts/retira_sensores_fantasma.sh --aplicar site-dev pue-pruebas-01
#
# `--tenant CODIGO` acota si un código de sitio se repite entre tenants.
# Requiere sesión AWS (perfil `takab-dev`) y la instancia `takab-dev-db` encendida.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APLICAR=0
TENANT=""
SITIOS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --aplicar) APLICAR=1 ;;
    --tenant) TENANT="${2:?--tenant necesita un código}"; shift ;;
    -*) echo "opción desconocida: $1" >&2; exit 2 ;;
    *) SITIOS+=("$1") ;;
  esac
  shift
done
if [ ${#SITIOS[@]} -eq 0 ]; then
  echo "nombra al menos un sitio por su código (no hay «todos»): p. ej. site-dev" >&2
  exit 2
fi
LISTA="$(IFS=,; echo "${SITIOS[*]}")"
ACTOR="ops:${USER:-desconocido}@$(hostname -s)"

# shellcheck source=/dev/null
. "$RAIZ/infra/scripts/lib/tunel.sh"
abrir_tunel "${TAKAB_DIAGNOSTICO_PUERTO:-5442}"

sec="$(credenciales_db)"
export PGPASSWORD
PGPASSWORD="$(jq -r .password <<<"$sec")"
export PGOPTIONS="-c statement_timeout=180s"
PSQL=(psql -h 127.0.0.1 -p "$TUNEL_PUERTO" -U "$(jq -r .username <<<"$sec")"
      -d "$(jq -r .dbname <<<"$sec")" -v ON_ERROR_STOP=1 -X -q
      -v "sitios=$LISTA" -v "tenant=$TENANT" -v "actor=$ACTOR" -v "aplicar=$APLICAR")

if [ "$APLICAR" -eq 1 ]; then
  echo "→ BAJA de fantasmas en: $LISTA${TENANT:+ (tenant $TENANT)} · actor $ACTOR"
else
  echo "→ SIMULACIÓN (sin --aplicar no se escribe nada): $LISTA${TENANT:+ (tenant $TENANT)}"
fi

"${PSQL[@]}" <<'SQL'
BEGIN;

-- Las variables de psql no llegan a un bloque `DO` (no se sustituyen dentro de
-- `$$`): viajan como GUC LOCALES de esta transacción. `\gset` las calla.
SELECT set_config('takab.sitios', :'sitios', true) AS s,
       set_config('takab.tenant', :'tenant', true) AS t,
       set_config('takab.actor', :'actor', true) AS a \gset _

-- Un código de sitio que exista en más de un tenant sin `--tenant` es ambiguo:
-- mejor no hacer nada que retirar sensores del cliente equivocado.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM sites si JOIN tenants te ON te.tenant_id = si.tenant_id
     WHERE si.code = ANY(string_to_array(current_setting('takab.sitios'), ','))
       AND (current_setting('takab.tenant') = '' OR te.code = current_setting('takab.tenant'))
     GROUP BY si.code HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'un código de sitio se repite entre tenants: acota con --tenant';
  END IF;
END $$;

-- Los sitios nombrados y los sensores de esos sitios que tienen AL MENOS una fila.
-- Una sola pasada por la hypertable, acotada por `site_id` (su índice): no tiene
-- índice por `sensor_id`, y un `NOT EXISTS` por sensor la recorrería entera cada vez.
CREATE TEMP TABLE _sitios ON COMMIT DROP AS
SELECT si.site_id, si.code AS sitio, te.code AS tenant
  FROM sites si JOIN tenants te ON te.tenant_id = si.tenant_id
 WHERE si.code = ANY(string_to_array(current_setting('takab.sitios'), ','))
   AND (current_setting('takab.tenant') = '' OR te.code = current_setting('takab.tenant'));

CREATE TEMP TABLE _con_datos ON COMMIT DROP AS
SELECT DISTINCT w.sensor_id
  FROM waveform_features_1s w
 WHERE w.site_id IN (SELECT site_id FROM _sitios);

-- Los candidatos, evaluados AQUÍ, dentro de la transacción que escribe.
CREATE TEMP TABLE _fantasmas ON COMMIT DROP AS
SELECT se.sensor_id, se.tenant_id, s.tenant, s.sitio,
       coalesce(se.serial, se.model) AS sensor, se.model
  FROM sensors se
  JOIN _sitios s ON s.site_id = se.site_id
 WHERE se.status = 'active'
   AND coalesce(nullif(btrim(se.calibration_source), ''), '') = ''
   AND se.sensor_id NOT IN (SELECT sensor_id FROM _con_datos);

SELECT tenant, sitio, sensor, sensor_id FROM _fantasmas ORDER BY tenant, sitio, sensor;
SELECT count(*) AS fantasmas_encontrados FROM _fantasmas;

-- La baja y su huella, en la misma transacción: o las dos o ninguna. El UPDATE vuelve
-- a exigir «activo y sin calibrar» sobre la fila que BLOQUEA: si alguien lo calibró o
-- lo retiró entre la lista y aquí, no se toca.
WITH retirados AS (
  UPDATE sensors se SET status = 'retired'
    FROM _fantasmas f
   WHERE se.sensor_id = f.sensor_id
     AND se.status = 'active'
     AND coalesce(nullif(btrim(se.calibration_source), ''), '') = ''
  RETURNING se.sensor_id, f.tenant_id, f.model, f.sitio
)
INSERT INTO audit_log (tenant_id, actor, verb, object, meta)
SELECT tenant_id, current_setting('takab.actor'), 'sensor_retire', 'sensor:' || sensor_id,
       jsonb_build_object(
         'model', model,
         'sitio', sitio,
         'motivo', 'fantasma: activo, sin calibración y sin una sola fila de features',
         'via', 'infra/scripts/retira_sensores_fantasma.sh',
         'ficha', 'T-9.35')
  FROM retirados;

\if :aplicar
  COMMIT;
  \echo ✓ baja aplicada y auditada
\else
  ROLLBACK;
  \echo · simulación: ROLLBACK, no se escribió nada. Repite con --aplicar para dar de baja.
\endif
SQL
