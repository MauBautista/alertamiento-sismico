#!/bin/bash
# [T-2.72] Archivado continuo de WAL (PITR) en la instancia de la DB.
#
# Este script NO se escribe a mano en ningun sitio: lo renderiza Terraform con
# los valores del modulo y lo ejecuta un documento SSM asociado a la instancia.
# Por que SSM y no `user_data`: `user_data` corre UNA vez, en el primer boot de
# cloud-init, y ademas el propio script sale antes de tiempo si encuentra el
# marcador `/var/lib/takab/.provisioned`. Poner el archivado ahi habria producido
# un Terraform verde que no toca la maquina que existe hoy — un mecanismo con
# cara de funcionar que no caza nada, que es justo lo que esta fase persigue.
# La asociacion, ademas, se vuelve a ejecutar sola: si alguien recrea el
# contenedor sin archivado, la siguiente pasada lo repara.
#
# Es idempotente y REARRANCA POSTGRES SOLO SI HACE FALTA (ver el paso 2).
set -euo pipefail

CONT=takab-db
PITR_URL="s3://${bucket}/${pitr_root}"
SERVER="${server_name}"
REGION="${region}"

log() { echo "[takab-pitr] $*"; }

psql_su() { docker exec -i "$CONT" psql -U postgres -d takab -v ON_ERROR_STOP=1 "$@"; }

# --- 0. Sin contenedor no hay nada que configurar -----------------------------
# Una instancia a medio aprovisionar no es un error de este script: la siguiente
# pasada de la asociacion la encontrara lista.
if ! docker ps --format '{{.Names}}' | grep -qx "$CONT"; then
  log "el contenedor $CONT no esta corriendo; no hay nada que configurar todavia"
  exit 0
fi

# --- 1. La configuracion declarada, aplicada con ALTER SYSTEM -----------------
#
# ALTER SYSTEM escribe `postgresql.auto.conf` DENTRO del datadir, que vive en el
# volumen EBS montado: sobrevive a recrear el contenedor (que es lo que hace un
# despliegue) y a reiniciar la instancia. Un `-c` en la linea de `docker run`
# solo duraria hasta el siguiente `docker rm`.
#
# `wal_level` NO se toca: `replica` (el default) ya basta para archivar; subirlo
# a `logical` solo aumentaria el volumen de WAL sin darnos nada.
#
# El comando lleva su region delante porque el `archive_command` lo ejecuta el
# postmaster con su propio entorno, y boto3 dentro del contenedor no tiene de
# donde sacarla.
#
# No se pasan flags de cifrado a proposito: el bucket tiene cifrado por defecto
# SSE-KMS con nuestra clave (`aws_s3_bucket_server_side_encryption_configuration`
# en modules/storage), asi que TODO objeto que entre queda cifrado sin que el
# archivador tenga que acordarse. Un flag de mas en el camino critico es un modo
# de fallo de mas por cero ganancia.
ARCHIVE_CMD="AWS_DEFAULT_REGION=$REGION barman-cloud-wal-archive --cloud-provider aws-s3 --gzip $PITR_URL $SERVER %p"

psql_su <<SQL
ALTER SYSTEM SET archive_mode = 'on';
ALTER SYSTEM SET archive_command = '$ARCHIVE_CMD';
ALTER SYSTEM SET archive_timeout = '${archive_timeout_s}s';
SQL

# `archive_command` y `archive_timeout` son de contexto `sighup` (comprobado con
# `SELECT name, context FROM pg_settings` contra la propia imagen pg16): un
# reload basta y no corta ninguna conexion.
psql_su -c "SELECT pg_reload_conf();" >/dev/null
log "archive_command y archive_timeout recargados"

# --- 2. archive_mode exige REINICIO, y solo se paga si hace falta -------------
#
# `archive_mode` es de contexto `postmaster`: no hay reload que valga. Se
# comprueba el valor EN CALIENTE y solo entonces se reinicia — asi la asociacion
# puede volver a correr cada dia sin tumbar la DB cada dia.
MODO="$(docker exec "$CONT" psql -U postgres -d takab -tAc 'SHOW archive_mode' | tr -d '[:space:]')"
if [ "$MODO" != "on" ]; then
  log "archive_mode=$MODO en caliente: reiniciando $CONT (unica via, es parametro de postmaster)"
  docker restart "$CONT" >/dev/null
  for _ in $(seq 1 60); do
    if docker exec "$CONT" pg_isready -U postgres -d takab >/dev/null 2>&1; then
      break
    fi
    sleep 5
  done
  docker exec "$CONT" pg_isready -U postgres -d takab
else
  log "archive_mode ya estaba en on: no se reinicia nada"
fi

# --- 3. El reloj del RPO: edad del ultimo WAL archivado con exito -------------
#
# Se publica desde el HOST (no desde el contenedor) porque el `aws` vive aqui,
# igual que el del dump nocturno.
#
# La fuente es `pg_stat_archiver.last_archived_time`: el instante del ultimo
# `archive_command` que devolvio 0, o sea el ultimo WAL que de verdad esta en S3.
# Un `archive_command` que falla en bucle NO lo mueve —los fallos van a
# `last_failed_time`/`failed_count`—, asi que la edad crece, que es exactamente
# lo que hay que detectar.
#
# `coalesce(..., stats_reset)` tapa el unico NULL posible: aun no se ha archivado
# nada desde que se reiniciaron las estadisticas. Ahi la respuesta honesta no es
# "0" (no hay nada archivado) sino "cuanto llevamos sin archivar nada".
#
# Si psql falla, NO se publica nada. Publicar un 0 a ciegas seria decir "el
# respaldo va bien" cuando lo unico cierto es que no se pudo preguntar; el
# silencio lo recoge la alarma, que esta en `breaching`.
install -d -m 0755 /opt/takab/bin
cat >/opt/takab/bin/takab-wal-age.sh <<EOS
#!/bin/bash
set -euo pipefail
EDAD="\$(docker exec takab-db psql -U postgres -d takab -tAc \
  "SELECT ceil(extract(epoch from now() - coalesce(last_archived_time, stats_reset)))::bigint FROM pg_stat_archiver" \
  | tr -d '[:space:]')"
[ -n "\$EDAD" ] || exit 1
aws cloudwatch put-metric-data \
  --namespace ${metric_namespace} \
  --metric-name ${metric_name} \
  --unit Seconds \
  --value "\$EDAD" \
  --region ${region}
EOS
chmod 0755 /opt/takab/bin/takab-wal-age.sh

# --- 4. Backup base: la otra mitad de la cadena -------------------------------
#
# Un WAL sin su backup base no arranca. La cadencia sale de
# `pitr.base_backup_interval_days`, la MISMA cifra con la que se calcula la
# retencion: si el cron y la desigualdad pudieran divergir, la garantia de la
# cadena se estaria calculando sobre un intervalo que no ocurre.
#
# `--immediate-checkpoint` a proposito: sin el, barman espera un checkpoint
# repartido y el backup puede quedarse esperando hasta `checkpoint_timeout` antes
# de empezar. A las 04:00 UTC sobre esta base, un pico corto de E/S es preferible
# a una duracion impredecible.
#
# Aqui NO hay ningun subcomando de PODA de barman (el nombre exacto esta en
# `main.tf`, y a proposito NO se escribe en este documento: hay una asercion que
# exige que no aparezca ni citado). El unico podador de esta cadena es el
# lifecycle de S3 (modules/storage). Y no es una promesa de este comentario — el
# rol de la instancia no tiene `s3:Delete*` sobre el bucket.
cat >/opt/takab/bin/takab-base-backup.sh <<EOS
#!/bin/bash
set -euo pipefail
docker exec takab-db env AWS_DEFAULT_REGION=$REGION barman-cloud-backup \
  --cloud-provider aws-s3 --gzip --immediate-checkpoint \
  -U postgres -d takab \
  $PITR_URL $SERVER
EOS
chmod 0755 /opt/takab/bin/takab-base-backup.sh

# Los snapshots DLM van a las 03:00 UTC y el dump logico a las 08:00: el backup
# base se pone a las 04:00 para no solaparse con ninguno de los dos.
cat >/etc/cron.d/takab-pitr <<CRON
* * * * * root /opt/takab/bin/takab-wal-age.sh >/dev/null 2>&1
0 4 ${base_backup_dom} * * root /opt/takab/bin/takab-base-backup.sh >>/var/log/takab-pitr.log 2>&1
CRON
chmod 0644 /etc/cron.d/takab-pitr

# --- 5. Una primera medida YA ------------------------------------------------
#
# La leccion de `ghost_gateways`: `insufficient_data_actions` solo dispara EN
# TRANSICION. Una alarma que nace en INSUFFICIENT_DATA porque su metrica no ha
# existido nunca se queda aparcada ahi, sin correo y con cara de "todavia no hay
# datos". Publicar una vez aqui obliga a la alarma a pronunciarse.
/opt/takab/bin/takab-wal-age.sh || log "AVISO: no se pudo publicar la primera medida de edad de archivado"

log "archivado continuo configurado: $PITR_URL ($SERVER), archive_timeout=${archive_timeout_s}s"
