#!/usr/bin/env bash
# [T-9.35 · D-43] Diagnóstico de SENSORES FANTASMA en la nube. SOLO LECTURA.
#
# Por qué existe: con el dictamen v2 un sitio sólo puede salir VERDE si TODOS sus
# sensores con `status = 'active'` están calibrados, y la PGA del dictamen es el
# máximo sobre esos mismos activos. Un sensor dado de alta que nunca reportó (un
# «fantasma») deja el sitio en AMARILLO para siempre sin que nadie vea por qué.
# Esto enseña, por sitio, cada sensor con lo que el dictamen lee de él.
#
# Qué NO hace: no da de baja nada. La baja la hace `retira_sensores_fantasma.sh`
# (la consola no ofrece la baja de sensores), que deja auditoría. Aquí todo
# corre dentro de `BEGIN READ ONLY` y además con la sesión en solo lectura, así
# que aunque se colara una escritura la rechazaría la base misma. La guarda del
# texto está en `api/tests/test_diagnostico_sensores_solo_lectura.py`.
#
# Uso:
#
#     infra/scripts/diagnostico_sensores.sh            # todos los sitios
#     infra/scripts/diagnostico_sensores.sh PUE-01     # un sitio por su código
#
# Requiere sesión AWS (perfil `takab-dev`) y la instancia `takab-dev-db` encendida.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SITIO="${1:-}"

# shellcheck source=/dev/null
. "$RAIZ/infra/scripts/lib/tunel.sh"
abrir_tunel "${TAKAB_DIAGNOSTICO_PUERTO:-5441}"

sec="$(credenciales_db)"
export PGPASSWORD
PGPASSWORD="$(jq -r .password <<<"$sec")"
# Segunda llave: la SESIÓN entera arranca en solo lectura, no sólo la transacción.
export PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=120s"
PSQL=(psql -h 127.0.0.1 -p "$TUNEL_PUERTO" -U "$(jq -r .username <<<"$sec")"
      -d "$(jq -r .dbname <<<"$sec")" -v ON_ERROR_STOP=1 -X -q -v "sitio=$SITIO")

echo "→ sensores por sitio (${SITIO:-todos}) · solo lectura"
"${PSQL[@]}" <<'SQL'
BEGIN READ ONLY;

-- Una sola pasada por la hypertable, agrupada por sensor (no una por sensor).
WITH filas AS (
  SELECT w.sensor_id,
         count(*)                                             AS filas_total,
         count(*) FILTER (WHERE w.ts > now() - interval '24 hours') AS filas_24h,
         max(w.ts)                                            AS ultima_fila
    FROM waveform_features_1s w
   GROUP BY w.sensor_id
)
-- `sites.code` se REPITE entre tenants: cada fila dice de QUIÉN es el sitio.
SELECT te.code                                    AS tenant,
       si.code                                    AS sitio,
       coalesce(se.serial, se.model)              AS sensor,
       se.kind,
       se.status,
       coalesce(nullif(btrim(se.calibration_source), ''), '— SIN CALIBRAR —') AS calibration_source,
       coalesce(f.filas_total, 0)                 AS filas_total,
       coalesce(f.filas_24h, 0)                   AS filas_24h,
       coalesce(to_char(f.ultima_fila AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS"Z"'),
                'NUNCA')                          AS ultima_fila,
       CASE
         WHEN se.status <> 'active'           THEN 'retirado: el dictamen no lo lee'
         WHEN coalesce(f.filas_total, 0) = 0  THEN 'FANTASMA: activo y sin una sola fila'
         WHEN coalesce(nullif(btrim(se.calibration_source), ''), '') = ''
                                              THEN 'activo sin calibrar: impide VERDE'
         ELSE 'ok'
       END                                        AS lectura
  FROM sensors se
  JOIN sites si ON si.site_id = se.site_id
  JOIN tenants te ON te.tenant_id = si.tenant_id
  LEFT JOIN filas f ON f.sensor_id = se.sensor_id
 WHERE :'sitio' = '' OR si.code = :'sitio'
 ORDER BY si.code, te.code, si.site_id, se.status, se.kind, sensor;

-- Resumen por sitio con el MISMO criterio que el dictamen v2: calibrado = todos
-- los activos con `calibration_source` no vacío TRAS `btrim` (bool_and). Agrupado por `site_id`
-- (no por código, que se repite entre tenants y sumaba sensores ajenos).
SELECT te.code                                                         AS tenant,
       si.code                                                         AS sitio,
       count(*) FILTER (WHERE se.status = 'active')                    AS activos,
       count(*) FILTER (WHERE se.status <> 'active')                   AS retirados,
       coalesce(bool_and(coalesce(nullif(btrim(se.calibration_source), ''), '') <> '')
                  FILTER (WHERE se.status = 'active'), false)          AS activos_calibrados,
       CASE
         WHEN count(*) FILTER (WHERE se.status = 'active') = 0
           THEN 'sin sensores activos: sin PGA ⇒ AMARILLO'
         WHEN coalesce(bool_and(coalesce(nullif(btrim(se.calibration_source), ''), '') <> '')
                  FILTER (WHERE se.status = 'active'), false)
           THEN 'puede salir VERDE'
         ELSE 'no puede salir VERDE: hay activos sin calibrar'
       END                                                             AS dictamen_v2
  FROM sites si
  JOIN tenants te ON te.tenant_id = si.tenant_id
  JOIN sensors se ON se.site_id = si.site_id
 WHERE :'sitio' = '' OR si.code = :'sitio'
 GROUP BY si.site_id, si.code, te.code
 ORDER BY si.code, te.code, si.site_id;

ROLLBACK;
SQL
