#!/bin/bash
# [T-2.81.a] EL JOB DE RETENCION DE PII, PROGRAMADO.
#
# El job existia y era invocable (`python -m takab_api.ops.prune_pii`), igual que
# `ops.restore_drill`, y NO LO LLAMABA NADIE: no habia modulo de cron, Lambda ni
# EventBridge en `infra/terraform/modules/`. Una retencion que nadie ejecuta es
# una politica escrita, no una cumplida — y la diferencia importa el dia que un
# cliente pregunta cuanto tiempo guardamos su telefono.
#
# MISMO VEHICULO QUE EL RESPALDO Y EL PITR, y por las mismas dos razones:
# `user_data` corre UNA sola vez (primer boot de cloud-init) y ademas sale antes
# de tiempo si encuentra `/var/lib/takab/.provisioned`, asi que escribir esto
# alli habria dado un Terraform verde que no toca la maquina que existe hoy; y
# tocar `user_data` hace que el provider PARE Y ARRANQUE la instancia en el
# siguiente apply. La asociacion, en cambio, impone el estado deseado todos los
# dias y lo repara si alguien lo deshace.
#
# CON QUE ROL CORRE, y por que no con el superusuario como el respaldo: el job se
# degrada a `takab_app` el solo, y comprueba contra el catalogo que el rol
# resultante no puede podar evidencia. Darle el DSN de `takab_app` desde fuera
# hace que esa degradacion sea un no-op COMPROBABLE en vez de una red que nadie
# ejerce, y de paso la maquina no necesita la contraseña del superusuario para
# esto. (El respaldo si la necesita: `pg_dump` tiene que ver lo mismo que ve la
# huella, y con RLS forzada `takab_app` veria menos filas.)
#
# `--apply` Y ES SEGURO. Sin `TAKAB_API_RETENTION_*_DAYS` cada regla queda
# DESHABILITADA y la corrida no toca una sola fila: el default bajo incertidumbre
# es no borrar nada. O sea que este cron se despliega ANTES de que los plazos
# esten decididos (son decision de negocio y de la ficha legal, no del
# programador), y mientras tanto lo unico que hace es dejar constancia de que el
# reloj se reviso. Los plazos se declaran en `pii_retention_windows_days`.
set -euo pipefail

log() { echo "[takab-prune-pii-setup] $*"; }

install -d -m 0755 /opt/takab/bin /var/lib/takab

# ---------------------------------------------------------------------------
# 1. El job. Heredoc CITADO: lo de dentro ya viene sustituido por Terraform.
# ---------------------------------------------------------------------------
cat >/opt/takab/bin/takab-prune-pii.sh <<'EOS'
#!/bin/bash
# [T-2.81.a] Corrida diaria de retencion de PII. Lo instala el documento SSM
# `takab-<env>-retencion-pii`; no se edita a mano en la maquina (la siguiente
# pasada de la asociacion lo revertiria).
set -euo pipefail

log() { echo "[takab-prune-pii] $(date -Is) $*"; }

TMP=""
limpiar() { if [ -n "$TMP" ]; then rm -rf "$TMP" || true; fi; }
trap limpiar EXIT

IMAGEN="$(sed -n 's/^TAKAB_CLOUD_IMAGE=//p' /etc/takab/deploy.env 2>/dev/null | tail -1 || true)"
if [ -z "$IMAGEN" ]; then
  log "ERROR: /etc/takab/deploy.env no declara TAKAB_CLOUD_IMAGE; la retencion NO corre"
  exit 1
fi

# tmpfs (/run), permisos 0700 y borrado por trap: la contraseña no toca disco ni
# sobrevive a la corrida (regla de oro 6). Nunca por linea de comando — `ps` la
# delataria.
TMP="$(mktemp -d /run/takab-prune-pii.XXXXXXXX)"
ENVF="$TMP/db.env"
(
  umask 077
  PASS="$(aws secretsmanager get-secret-value \
    --secret-id "${app_secret}" --region ${region} \
    --query SecretString --output text |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])')"
  [ -n "$PASS" ] || exit 1
  printf 'DATABASE_URL=postgresql://takab_app:%s@127.0.0.1:5432/takab\n' "$PASS" >"$ENVF"
  cat >>"$ENVF" <<'PLAZOS'
${retention_env}
PLAZOS
) || { log "ERROR: no se pudo resolver la contraseña de takab_app; la retencion NO corre"; exit 1; }

log "corriendo la retencion con la imagen $IMAGEN"
docker run --rm --network host --env-file "$ENVF" \
  --entrypoint python "$IMAGEN" -m takab_api.ops.prune_pii --apply
EOS
chmod 0755 /opt/takab/bin/takab-prune-pii.sh

# ---------------------------------------------------------------------------
# 2. El PUBLICADOR de la metrica. Sale de la BASE, no del exit code del cron.
#
# `PiiRetentionAgeSeconds` = cuanto hace que termino BIEN la ultima corrida,
# leido de `pii_retention_runs` (que la escribe el propio job, FUERA de su
# transaccion, para que una corrida abortada tambien deje fila).
#
# Medir esto y no "el script salio con 0" es la diferencia entre vigilar la
# retencion y vigilar el cron: una corrida que aborta escribe `ok = false`, la
# edad sigue creciendo y la alarma suena. Con el exit code, un job que fallara
# rapido y volviera a fallar rapido no moveria ninguna aguja.
#
# El fallback mientras no exista NINGUNA corrida correcta es el mismo truco que
# el del backup base: se mide desde que se configuro esto. Asi la alarma NACE
# diciendo la verdad ("no consta ninguna retencion ejecutada") en vez de quedarse
# aparcada en INSUFFICIENT_DATA sin avisar a nadie.
#
# Si psql falla NO se publica nada: publicar un 0 a ciegas seria decir "la
# retencion va bien" cuando lo unico cierto es que no se pudo preguntar.
# ---------------------------------------------------------------------------
cat >/opt/takab/bin/takab-prune-pii-age.sh <<EOS
#!/bin/bash
set -euo pipefail
ORIGEN=/var/lib/takab/pii-retention-configured-epoch
EDAD="\$(docker exec takab-db psql -U postgres -d takab -tAc \
  "SELECT ceil(extract(epoch from now() - max(finished_at)))::bigint \
     FROM pii_retention_runs WHERE ok" 2>/dev/null | tr -d '[:space:]')"
if [ -z "\$EDAD" ]; then
  [ -s "\$ORIGEN" ] || exit 1
  EDAD=\$(( \$(date +%s) - \$(cat "\$ORIGEN") ))
fi
[ "\$EDAD" -ge 0 ] || EDAD=0
aws cloudwatch put-metric-data \
  --namespace ${metric_namespace} \
  --metric-name ${metric_name} \
  --unit Seconds \
  --value "\$EDAD" \
  --region ${region}
EOS
chmod 0755 /opt/takab/bin/takab-prune-pii-age.sh

# El instante de referencia mientras no haya ninguna corrida. Se escribe UNA vez:
# reescribirlo en cada pasada diaria de la asociacion reiniciaria la edad cada
# 24 h y la alarma no llegaria a disparar NUNCA — una retencion muerta para
# siempre con una metrica eternamente joven.
[ -s /var/lib/takab/pii-retention-configured-epoch ] ||
  date +%s >/var/lib/takab/pii-retention-configured-epoch

# ---------------------------------------------------------------------------
# 3. Los crones. Fichero PROPIO (`takab-prune-pii`) y no el del PITR: son dos
# cadenas distintas y mezclarlas haria que tocar una reescribiera la otra.
#
# 06:00 UTC: los snapshots DLM van a las 03:00, el backup base a las 04:00, su
# scan a las 05:00 y el dump logico a las 08:00. Las 06:00 es la unica franja
# libre, y ademas deja la corrida ANTES del dump — asi el respaldo del dia ya se
# lleva la PII podada en vez de la de ayer.
#
# La publicacion va por minuto, como las otras tres, y no es preferencia: la
# alarma esta en `breaching`, y con una metrica publicada una vez al dia basta
# que el cron se desplace un minuto para dejar una ventana de CloudWatch sin
# ningun datapoint — o sea un correo afirmando que la retencion no corre.
# ---------------------------------------------------------------------------
cat >/etc/cron.d/takab-prune-pii <<CRON
* * * * * root /opt/takab/bin/takab-prune-pii-age.sh >/dev/null 2>&1
0 6 * * * root /opt/takab/bin/takab-prune-pii.sh >>/var/log/takab-prune-pii.log 2>&1
CRON
chmod 0644 /etc/cron.d/takab-prune-pii

# ---------------------------------------------------------------------------
# 4. Lo que no puede quedarse en una casilla marcada de memoria: que la imagen
# DESPLEGADA sepa correr esto. Se pregunta en cada pasada y la respuesta queda en
# la salida del comando SSM; asi la ventana de T-2.74 empieza sabiendolo.
# ---------------------------------------------------------------------------
IMAGEN="$(sed -n 's/^TAKAB_CLOUD_IMAGE=//p' /etc/takab/deploy.env 2>/dev/null | tail -1 || true)"
if [ -z "$IMAGEN" ]; then
  log "AVISO: /etc/takab/deploy.env no declara TAKAB_CLOUD_IMAGE: la retencion NO podra correr"
elif docker run --rm --entrypoint python "$IMAGEN" -m takab_api.ops.prune_pii --help 2>&1 |
  grep -q -- '--apply'; then
  log "OK: la imagen $IMAGEN sabe correr la retencion de PII"
else
  log "AVISO: la imagen $IMAGEN NO expone takab_api.ops.prune_pii (imagen anterior a T-2.81)."
  log "       Arreglo: make cloud-images && make cloud-deploy"
fi

# Una primera medida YA: la leccion de `ghost_gateways`. Una alarma que nace en
# INSUFFICIENT_DATA porque su metrica no ha existido nunca se queda ahi, sin
# transicion y sin correo.
/opt/takab/bin/takab-prune-pii-age.sh ||
  log "AVISO: no se pudo publicar la primera edad de la retencion de PII"

log "retencion de PII programada: 06:00 UTC diario + publicacion por minuto de ${metric_name}"
