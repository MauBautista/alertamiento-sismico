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

# --- 2b. [T-7.47] LA COTA DEL LOG, que solo se puede poner RECREANDO ----------
#
# `takab-db` nacio sin `--log-opt`, asi que su `LogConfig` es `json-file` con
# configuracion VACIA: sin techo. Los ocho servicios del compose si la declaran
# (`max-size 10m, max-file 3`). Medido el 2026-09-17: su log ocupaba 84 MB tras
# 73 dias, o sea ~1,16 MB/dia — el unico consumidor SIN COTA del volumen raiz, y
# el que `docker image prune` jamas toca.
#
# TRES VIAS DESCARTADAS, por escrito, para que nadie las reintente:
#
#   · `docker update` NO puede tocar `LogConfig`: su superficie son cgroups y
#     `--restart`. Sale con codigo 0 y no cambia nada — un arreglo que informa
#     exito y deja el log sin techo, que es el peor resultado posible.
#   · El default del demonio (`/etc/docker/daemon.json`) NO alcanza a un
#     contenedor YA CREADO: `LogConfig` se congela al crearlo y ni `docker
#     restart`, ni reiniciar dockerd, ni reiniciar la maquina lo re-derivan. Y
#     reiniciar dockerd aqui es parar TODO, porque no hay `live-restore` y
#     `takab-cloud.service` cuelga de `docker.service` por `Requires=`.
#   · Parar dockerd y editar `hostconfig.json` a mano: para TODO para arreglar
#     UNO, o sea estrictamente peor que recrear un solo contenedor.
#
# Asi que se recrea. Y se recrea con la MISMA guarda idempotente que el bloque de
# arriba: se mide en caliente y solo se actua si falta la cota, de modo que la
# asociacion diaria puede volver a correr sin tumbar la base cada dia. La segunda
# pasada entra por el `else` y no toca nada.
#
# QUE NO SE PIERDE AL RECREAR, y no es una suposicion: medido el 2026-09-17 con
# `docker diff takab-db` sobre el contenedor vivo — OCHO entradas, todas en
# `/run` y `/tmp` (el socket, su lock y temporales de la imagen). El datadir es un
# bind mount (`/data/pgdata`) y la configuracion anadida despues vive DENTRO de
# el (`postgresql.auto.conf`, ver el paso 1). Fuera del bind mount no hay nada.
#
# POR QUE LA COTA VIVE AQUI Y NO EN `user_data.sh.tpl`, que es donde se crea el
# contenedor. Tocar aquella plantilla cambia el atributo `user_data` de la
# INSTANCIA VIVA, y `user_data` no esta en su `lifecycle.ignore_changes`: el
# siguiente `terraform apply` —cualquiera, aunque venga a otra cosa— la PARA Y LA
# ARRANCA. Meterlo en `ignore_changes` evitaria eso, pero al precio de que un
# cambio de `user_data` deje de verse en el plan PARA SIEMPRE, que es una ceguera
# permanente a cambio de una ventana de 24 h en una instancia que se recrea casi
# nunca.
#
# Asi que manda este documento, con el precedente literal de
# `backup_setup.sh.tpl`, que reescribe `/etc/cron.d/takab-backup` —el MISMO
# fichero que creo `user_data`—. El coste declarado: una instancia NUEVA nace sin
# cota y la adquiere en la primera pasada de la asociacion, o sea en 24 h como
# mucho. Acotado y auto-curable, que es justo lo que la ceguera del plan no es.
#
# LA CONTRASENA se lee del contenedor VIEJO y viaja por env-file 0600 en tmpfs,
# nunca por linea de comando: `ps` la delataria. Es el mismo patron que
# `backup_setup.sh.tpl`. Leerla de ahi —y no de Secrets Manager— garantiza que el
# contenedor nuevo nace con EXACTAMENTE el mismo valor que el que se retira.
COTA="$(docker inspect -f '{{index .HostConfig.LogConfig.Config "max-size"}}' "$CONT" 2>/dev/null || true)"
if [ -z "$COTA" ] || [ "$COTA" = "<no value>" ]; then
  log "takab-db corre SIN cota de log: se recrea con max-size=${log_max_size} max-file=${log_max_file}"
  ENVF=/run/takab-db-recreate.env
  if (
    umask 077
    docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$CONT" \
      | grep -E '^(POSTGRES_PASSWORD|POSTGRES_DB)=' >"$ENVF"
    grep -q '^POSTGRES_PASSWORD=' "$ENVF"
  ); then
    # `stop` y no `rm -f`: Postgres cierra limpio y se ahorra la recuperacion de
    # caida en el arranque siguiente.
    docker stop "$CONT" >/dev/null
    docker rm "$CONT" >/dev/null
    docker run -d --name "$CONT" --restart unless-stopped \
      --log-opt max-size=${log_max_size} --log-opt max-file=${log_max_file} \
      -p 5432:5432 \
      -v /data/pgdata:/home/postgres/pgdata/data \
      --env-file "$ENVF" \
      timescale/timescaledb-ha:pg16 >/dev/null
    rm -f "$ENVF"
    for _ in $(seq 1 60); do
      if docker exec "$CONT" pg_isready -U postgres -d takab >/dev/null 2>&1; then
        break
      fi
      sleep 5
    done
    # Sin `|| true`: si la base no vuelve, esta asociacion TIENE que fallar
    # ruidosamente. Un `docker run` que no levanta es lo unico verdaderamente
    # caro de este bloque.
    docker exec "$CONT" pg_isready -U postgres -d takab
    log "takab-db recreado con cota de log y respondiendo"
  else
    rm -f "$ENVF"
    log "AVISO: no se pudo leer el entorno de takab-db; NO se recrea (mejor sin cota que sin base)"
  fi
else
  log "takab-db ya tiene cota de log (max-size=$COTA): no se recrea nada"
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

# [T-2.154] Y AL TERMINAR, refrescar la edad. No es cosmetica: sin esto el scan
# de las 05:00 es el unico que descubre el backup nuevo, asi que la metrica sigue
# contando la edad del ANTERIOR durante una hora entera. Como la edad cruza el
# umbral exactamente cuando arranca este backup, esa hora es una ventana de
# incumplimiento GARANTIZADA en cada ciclo — medido: la alarma temprana disparaba
# todas las semanas sin que pasara nada.
#
# El scan de las 05:00 se queda: cubre los backups hechos por otra via y repara el
# fichero si alguien lo borra. Lo que cambia es que ya no es el UNICO.
#
# `|| true` a proposito: el backup ya termino bien y su exito no puede depender de
# que la metrica se refresque. Si esto falla, el scan de las 05:00 lo arregla y la
# alarma —que vigila la ausencia— es quien tiene que hablar.
/opt/takab/bin/takab-base-backup-scan.sh || true
/opt/takab/bin/takab-base-backup-age.sh || true
EOS
chmod 0755 /opt/takab/bin/takab-base-backup.sh

# --- 4b. [T-2.72.b] La EDAD DEL ANCLA, que ninguna metrica de hoy ve ----------
#
# `WalArchiveAgeSeconds` mide la CADENA de WAL. No mide su ancla: un
# `barman-cloud-backup` que falle todas las semanas no mueve esa metrica ni un
# segundo — el archivado sigue perfecto y la cadena esta rota igual. Eso no se
# descubre hasta el dia del restore, que es EL modo de fallo que la Fase 2.6
# existe para eliminar.
#
# DOS PIEZAS, y estan separadas a proposito:
#
#   · El SCAN (diario, 05:00, una hora despues del backup base): pregunta a
#     `barman-cloud-backup-list` cual es el backup base mas reciente que de verdad
#     esta en S3 y guarda su instante. Es la parte cara —lista objetos del
#     bucket— y por eso va una vez al dia, que es lo que pide la ficha.
#
#   · La PUBLICACION (cada minuto): la EDAD es funcion del reloj, no del listado,
#     asi que se puede derivar del instante guardado sin volver a listar nada.
#
#   Y no es una preferencia: es lo que exige el `treat_missing_data = breaching`
#   de la alarma. Con una metrica publicada UNA vez al dia sobre un periodo de un
#   dia, basta que el cron se desplace un minuto para dejar una ventana de
#   CloudWatch sin ningun datapoint — y sobre `breaching` cada ventana vacia es un
#   correo afirmando que no hay respaldo. Publicar por minuto elimina esa clase
#   entera de falso positivo y deja la metrica con la misma forma que la del RPO.
#
# El parseo va en su propio fichero porque la salida de barman ha cambiado de
# forma entre versiones: se aceptan `end_time`, `begin_time` y, como ultimo
# recurso, el propio `backup_id` (que en barman ES un instante, `YYYYMMDDTHHMMSS`
# en UTC). Si NINGUNO se puede leer, no se publica nada — publicar un 0 a ciegas
# seria decir "hay ancla reciente" cuando lo unico cierto es que no se pudo
# preguntar.
cat >/opt/takab/bin/takab-base-backup-parse.py <<'PY'
import json
import re
import sys
from datetime import datetime, timezone


def a_epoch(v):
    if not isinstance(v, str):
        return None
    s = v.strip()
    if re.match(r"^\d{8}T\d{6}$", s):
        return datetime.strptime(s, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).timestamp()
    s = s.replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


datos = json.load(sys.stdin)
lista = datos.get("backups_list") or datos.get("backups") or []
if isinstance(lista, dict):
    lista = list(lista.values())

mejor = None
for b in lista:
    if not isinstance(b, dict):
        continue
    # Un backup a medias NO es un ancla. Si barman no dice el estado se acepta:
    # los que lista son los que termino.
    if str(b.get("status", "DONE")).upper() not in ("DONE", "OK", ""):
        continue
    for campo in ("end_time", "begin_time", "backup_id"):
        t = a_epoch(b.get(campo))
        if t is not None:
            if mejor is None or t > mejor:
                mejor = t
            break

if mejor is None:
    sys.exit(1)
print(int(mejor))
PY
chmod 0644 /opt/takab/bin/takab-base-backup-parse.py

cat >/opt/takab/bin/takab-base-backup-scan.sh <<EOS
#!/bin/bash
set -euo pipefail
SALIDA="\$(docker exec takab-db env AWS_DEFAULT_REGION=$REGION barman-cloud-backup-list \
  --cloud-provider aws-s3 --format json $PITR_URL $SERVER)"
EPOCH="\$(printf '%s' "\$SALIDA" | python3 /opt/takab/bin/takab-base-backup-parse.py)"
[ -n "\$EPOCH" ] || exit 1
install -d -m 0755 /var/lib/takab
printf '%s\n' "\$EPOCH" >/var/lib/takab/base-backup-last-epoch
EOS
chmod 0755 /opt/takab/bin/takab-base-backup-scan.sh

# EL ANCLA QUE NO EXISTE TODAVIA. Mientras no haya ningun backup base, la
# respuesta honesta no es "0" (no hay ancha ninguna) sino "cuanto llevamos sin
# tenerla": se mide desde que se configuro el PITR. Es el mismo truco que el
# `coalesce(last_archived_time, stats_reset)` del reloj del RPO, y es lo que hace
# que la alarma NAZCA EN ALARM el dia del primer apply — correctamente, porque
# entonces la cadena no tiene ancla.
cat >/opt/takab/bin/takab-base-backup-age.sh <<EOS
#!/bin/bash
set -euo pipefail
ANCLA=/var/lib/takab/base-backup-last-epoch
ORIGEN=/var/lib/takab/pitr-configured-epoch
if [ -s "\$ANCLA" ]; then
  DESDE="\$(cat "\$ANCLA")"
elif [ -s "\$ORIGEN" ]; then
  DESDE="\$(cat "\$ORIGEN")"
else
  exit 1
fi
EDAD=\$(( \$(date +%s) - DESDE ))
[ "\$EDAD" -ge 0 ] || EDAD=0
aws cloudwatch put-metric-data \
  --namespace ${metric_namespace} \
  --metric-name ${base_backup_metric_name} \
  --unit Seconds \
  --value "\$EDAD" \
  --region ${region}
EOS
chmod 0755 /opt/takab/bin/takab-base-backup-age.sh

# --- 4c. [T-2.72.c] El DISCO, que hasta hoy solo se vigilaba por accidente ----
#
# Con el archivado atascado Postgres NO recicla su WAL: `pg_wal` crece ~16 MiB/min
# sobre el MISMO volumen de 40 GiB donde vive el datadir. La alarma de atasco
# llega mucho antes (900 s ≪ 48 h) y por eso el riesgo estaba cubierto — pero por
# la via indirecta: mide el archivado, no el disco. Cualquier otra causa de disco
# lleno (un log desbocado, un restore a base lateral, imagenes de docker
# acumuladas) seguia siendo invisible.
#
# `disk_used_percent` NO existe en las metricas nativas de EC2: el hipervisor no
# ve dentro del filesystem. O agente de CloudWatch, o publicacion propia. Se
# publica desde aqui, por el mismo cron que el reloj del RPO: un demonio mas en la
# maquina que sostiene la DB, la API y los workers es un demonio mas que puede
# morir en silencio.
#
# LA COMPROBACION DE MONTAJE VA PRIMERO Y NO ES DEFENSIVA: si el volumen de datos
# no esta montado, `df /data` responde igual — con las cifras del volumen RAIZ, y
# esas se ven sanas. Publicar eso seria pintar un disco holgado mientras el disco
# de la base no esta. Sin dato, la alarma va a INSUFFICIENT_DATA y avisa.
cat >/opt/takab/bin/takab-disk-usage.sh <<EOS
#!/bin/bash
set -euo pipefail
mountpoint -q /data || exit 1
USADO="\$(df -P /data | awk 'NR==2 {gsub(/%/,"",\$5); print \$5}')"
[ -n "\$USADO" ] || exit 1
aws cloudwatch put-metric-data \
  --namespace ${metric_namespace} \
  --metric-name ${data_disk_metric_name} \
  --unit Percent \
  --value "\$USADO" \
  --region ${region}
EOS
chmod 0755 /opt/takab/bin/takab-disk-usage.sh

# --- 4d. [T-7.46] El volumen RAIZ, que no medía nadie -------------------------
#
# El 2026-09-16 `make cloud-deploy` murio con `no space left on device`. La raiz
# estaba al 99 % —20 GiB, 268 MB libres— con 65 imagenes de Docker y 16,23 GB,
# algunas de siete semanas: ningun despliegue habia podado nunca. El bloque de
# arriba mide `/data`; las imagenes de Docker viven en `/`.
#
# ES UN SCRIPT PROPIO Y NO UNA LINEA MAS EN EL DE ARRIBA, por una razon concreta:
# aquel empieza con `mountpoint -q /data || exit 1` bajo `set -euo pipefail`, asi
# que medir la raiz alli la dejaria detras de esa guarda. Un `/data` desmontado
# —o un `put-metric-data` de `/data` que fallara— silenciaria tambien la metrica
# de la raiz, que SIEMPRE es medible; la alarma de la raiz se iria a
# INSUFFICIENT_DATA por una causa que su propio correo no puede nombrar.
#
# SI COMPARTE EL FICHERO DE CRON, y eso tambien es deliberado: el `missing` de
# estas alarmas de disco se admite porque un cron muerto lo delata
# `wal_archive_stalled` en `breaching`, y ese argumento solo vale mientras las
# lineas vivan en el MISMO `/etc/cron.d/takab-pitr`. En un fichero propio habria
# que re-derivarlo.
#
# LA GUARDA ES DISTINTA porque el peligro es distinto: `df -P /` siempre
# contesta, asi que aqui no hay nada que comprobar antes de medir. Lo que si se
# comprueba es que la medida sea un NUMERO — si `awk` no saca el porcentaje, no
# se publica nada. Nunca un 0: un fallback no puede decir `ok`.
cat >/opt/takab/bin/takab-root-disk-usage.sh <<EOS
#!/bin/bash
set -euo pipefail
USADO="\$(df -P / | awk 'NR==2 {gsub(/%/,"",\$5); print \$5}')"
case "\$USADO" in ''|*[!0-9]*) exit 1 ;; esac
aws cloudwatch put-metric-data \
  --namespace ${metric_namespace} \
  --metric-name ${root_disk_metric_name} \
  --unit Percent \
  --value "\$USADO" \
  --region ${region}
EOS
chmod 0755 /opt/takab/bin/takab-root-disk-usage.sh

# El instante de referencia mientras no haya ningun backup base. Se escribe UNA
# vez: si se reescribiera en cada pasada diaria de la asociacion, la edad se
# reiniciaria cada 24 h y la alarma no llegaria a disparar NUNCA — un respaldo
# base roto para siempre y una metrica eternamente joven.
install -d -m 0755 /var/lib/takab
[ -s /var/lib/takab/pitr-configured-epoch ] || date +%s >/var/lib/takab/pitr-configured-epoch

# Los snapshots DLM van a las 03:00 UTC y el dump logico a las 08:00: el backup
# base se pone a las 04:00 para no solaparse con ninguno de los dos, y el scan que
# lo comprueba a las 05:00 — una hora despues, para que el dia que toca backup la
# edad se refresque el mismo dia y no al siguiente.
# [T-7.47] POR QUE ESTOS LOGS NO LLEVAN `logrotate`, con la cifra al lado.
#
# Tres crones anexan a ficheros de la raiz: este, `takab-backup.log` y
# `takab-prune-pii.log`. Medido el 2026-09-17: 0 B, 24 KB y 29 KB — **53 KB entre
# los tres** desde agosto, o sea del orden de 350 KB al ano. Los cuatro
# publicadores por minuto NO escriben ahi: van a `/dev/null`, que es lo que
# mantiene la cifra en ese orden de magnitud.
#
# `logrotate` seria un mecanismo mas que puede morir en silencio, y en este
# repositorio eso se paga. Para 350 KB/ano sobre un volumen de 20 GiB no compensa:
# tardaria SESENTA ANOS en igualar lo que una sola imagen de Docker ocupa. Si
# algun dia uno de estos scripts se vuelve locuaz, lo dira la alarma
# `takab-dev-disco-raiz-lleno` (T-7.46), que mide el volumen entero y no depende
# de que nadie se acuerde de esto.
cat >/etc/cron.d/takab-pitr <<CRON
* * * * * root /opt/takab/bin/takab-wal-age.sh >/dev/null 2>&1
* * * * * root /opt/takab/bin/takab-base-backup-age.sh >/dev/null 2>&1
* * * * * root /opt/takab/bin/takab-disk-usage.sh >/dev/null 2>&1
* * * * * root /opt/takab/bin/takab-root-disk-usage.sh >/dev/null 2>&1
0 5 * * * root /opt/takab/bin/takab-base-backup-scan.sh >>/var/log/takab-pitr.log 2>&1
0 4 ${base_backup_dom} * * root /opt/takab/bin/takab-base-backup.sh >>/var/log/takab-pitr.log 2>&1
CRON
chmod 0644 /etc/cron.d/takab-pitr

# --- 5. Una primera medida YA ------------------------------------------------
#
# La leccion de `ghost_gateways`: `insufficient_data_actions` solo dispara EN
# TRANSICION. Una alarma que nace en INSUFFICIENT_DATA porque su metrica no ha
# existido nunca se queda aparcada ahi, sin correo y con cara de "todavia no hay
# datos". Publicar una vez aqui obliga a las alarmas a pronunciarse.
#
# El scan va antes que la edad para que, si YA hay backups base, la primera medida
# publicada sea la de verdad y no la que se cuenta desde la configuracion.
/opt/takab/bin/takab-wal-age.sh || log "AVISO: no se pudo publicar la primera medida de edad de archivado"
/opt/takab/bin/takab-base-backup-scan.sh || log "AVISO: no se pudo listar el backup base (¿todavia no hay ninguno?)"
/opt/takab/bin/takab-base-backup-age.sh || log "AVISO: no se pudo publicar la primera edad del backup base"
/opt/takab/bin/takab-disk-usage.sh || log "AVISO: no se pudo publicar la primera medida de ocupacion de /data"
/opt/takab/bin/takab-root-disk-usage.sh || log "AVISO: no se pudo publicar la primera medida de ocupacion de la raiz"

log "archivado continuo configurado: $PITR_URL ($SERVER), archive_timeout=${archive_timeout_s}s"
