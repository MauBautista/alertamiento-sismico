#!/bin/bash
# [T-2.73.a] El respaldo logico nocturno Y LA HUELLA DEL ORIGEN que viaja con el.
#
# Hasta hoy el cron de las 08:00 subia el `.dump` y nada mas. Sin la huella, seis
# de las comprobaciones mas fuertes del verificador (inventario, columnas,
# constraints, privilegios, propiedad, conteos) no se pueden ejercer y el
# veredicto es INDETERMINADO: acreditar `G-09` asi seria gastar la ventana AWS
# para obtener medio dictamen.
#
# POR QUE ESTE SCRIPT VIAJA EN UN DOCUMENTO SSM Y NO EN `user_data.sh.tpl`, que
# es donde vive hoy la linea del cron: tocar `user_data` cambia el atributo
# `user_data` de `aws_instance.db`, y el provider responde a ese cambio PARANDO Y
# ARRANCANDO la instancia en el siguiente apply. La DB caeria. Ademas `user_data`
# corre una sola vez —cloud-init, primer boot— y el propio script sale antes de
# tiempo si encuentra `/var/lib/takab/.provisioned`: escribirlo ahi habria dado un
# Terraform verde que no toca la maquina que existe hoy. La asociacion diaria, en
# cambio, impone el estado deseado y lo repara si alguien lo deshace.
#
# EL MISMO CRON, literalmente: este script reescribe `/etc/cron.d/takab-backup`,
# el MISMO fichero que creo `user_data`, con la misma hora. No se anade una
# segunda entrada — dos volcados a las 08:00 competirian por el mismo nombre de
# objeto en S3.
set -euo pipefail

log() { echo "[takab-backup-setup] $*"; }

install -d -m 0755 /opt/takab/bin

# ---------------------------------------------------------------------------
# El script del cron. Heredoc CITADO: todo lo que hay dentro ya viene sustituido
# por Terraform, y bash lo escribe tal cual (los `$VAR` de dentro son del script,
# no de aqui).
# ---------------------------------------------------------------------------
cat >/opt/takab/bin/takab-backup.sh <<'EOS'
#!/bin/bash
# [T-2.73.a] Dump logico + huella del origen, ANCLADOS AL MISMO SNAPSHOT.
#
# Lo instala el documento SSM `takab-<env>-respaldo-logico`; no se edita a mano
# en la maquina (la siguiente pasada de la asociacion lo revertiria).
#
# POR QUE UN SNAPSHOT COMPARTIDO. `restore_check` compara los conteos fila a
# fila y exige igualdad EXACTA: es la comprobacion que caza las decenas de miles
# de filas que el procedimiento viejo perdia en silencio. Pero la base de
# produccion no esta quieta —los latidos de la flota escriben cada minuto—, asi
# que una huella tomada a las 08:00:00 contra un dump que termina a las 08:04
# daria ROJO sobre un restore perfecto. Un falso rojo el dia del desastre es
# peor que un INDETERMINADO: ensena al operador a desconfiar del verificador.
#
# Por eso la huella exporta su snapshot (`pg_export_snapshot()`, transaccion
# REPEATABLE READ) y `pg_dump --snapshot=` lo consume. Coste extra sobre la
# base: ninguno — `pg_dump` ya mantiene abierta una transaccion identica durante
# todo el volcado.
#
# ASIMETRIA DELIBERADA ANTE EL FALLO:
#   - el `.dump` es FAIL-OPEN: si la coordinacion no se puede montar, el volcado
#     sale igual (sin ancla). No se sacrifica el respaldo que hoy funciona por
#     una mejora del verificador;
#   - la huella es FAIL-CLOSED: si no queda anclada, NO se sube. Sin huella el
#     veredicto es INDETERMINADO, que es la verdad; con una huella desalineada
#     seria ROJO, que es mentira.
set -euo pipefail

FECHA="$(date +%F)"
DUMP_KEY="s3://${bucket}/${dump_prefix}$FECHA.dump"
HUELLA_KEY="s3://${bucket}/${dump_prefix}$FECHA.fingerprint.json"

log() { echo "[takab-backup] $(date -Is) $*"; }

COORD=""
CID=""
SNAP=""

limpiar() {
  if [ -n "$CID" ]; then docker rm -f "$CID" >/dev/null 2>&1 || true; fi
  if [ -n "$COORD" ]; then rm -rf "$COORD" || true; fi
}
trap limpiar EXIT

# --- 1. Coordinacion: de mejor esfuerzo, y ruidosa cuando no se puede --------
#
# Quien sabe ejecutar codigo de TAKAB en esta maquina es el contenedor de la
# nube co-locada. La referencia de su imagen la deja `deploy/cloud/deploy.sh` en
# /etc/takab/deploy.env; el mismo patron que ya usa el `alembic upgrade head` del
# despliegue (`docker run --entrypoint python <imagen> -m alembic ...`).
IMAGEN="$(sed -n 's/^TAKAB_CLOUD_IMAGE=//p' /etc/takab/deploy.env 2>/dev/null | tail -1 || true)"

if [ -z "$IMAGEN" ]; then
  log "AVISO: /etc/takab/deploy.env no declara TAKAB_CLOUD_IMAGE. El dump sube SIN huella"
else
  # tmpfs (/run), permisos 0700 y borrado por trap: la contrasena del
  # superusuario no toca disco ni sobrevive a la corrida (regla de oro 6).
  COORD="$(mktemp -d /run/takab-backup.XXXXXXXX)"
  ENVF="$COORD/db.env"

  # Superusuario A PROPOSITO, y no `takab_app`/`takab_ingest`: la huella tiene
  # que ver EXACTAMENTE lo mismo que ve el `pg_dump`, que corre como `postgres`.
  # Con RLS forzada los conteos saldrian recortados y la huella mentiria hacia
  # abajo. Nunca por linea de comando (`ps` la delataria): env-file 0600.
  if (
    umask 077
    PASS="$(aws secretsmanager get-secret-value \
      --secret-id "${superuser_secret}" --region ${region} \
      --query SecretString --output text |
      python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])')"
    [ -n "$PASS" ] || exit 1
    printf 'DATABASE_URL=postgresql://postgres:%s@127.0.0.1:5432/takab\n' "$PASS" >"$ENVF"
  ); then
    CID="$(docker run -d --network host --env-file "$ENVF" -v "$COORD:/coord" \
      --entrypoint python "$IMAGEN" \
      -m takab_api.ops.restore_check \
      --database takab \
      --save-baseline /coord/huella.json \
      --coordinate-with-dump /coord \
      --coordination-timeout ${coordination_timeout_s} 2>"$COORD/docker.err" || true)"
  else
    log "AVISO: no se pudo resolver la contrasena del superusuario; el dump sube SIN huella"
  fi

  if [ -n "$CID" ]; then
    for _ in $(seq 1 120); do
      if [ -s "$COORD/snapshot.id" ]; then
        SNAP="$(tr -d '[:space:]' <"$COORD/snapshot.id")"
        break
      fi
      docker inspect -f '{{.State.Running}}' "$CID" 2>/dev/null | grep -qx true || break
      sleep 1
    done
    if [ -z "$SNAP" ]; then
      # El unico sitio donde se sabe POR QUE no hubo ancla. Sin volcarlo aqui, la
      # traza se va con el `docker rm -f` del trap y manana no queda nada que leer.
      log "AVISO: la huella no exporto snapshot; el dump sube SIN ancla. Ultimas lineas:"
      docker logs "$CID" 2>&1 | tail -20 || true
    fi
  else
    log "AVISO: no arranco el contenedor de la huella ($IMAGEN); el dump sube SIN huella"
    # `[ ... ] && cmd` como ULTIMA sentencia de una rama devolveria falso con
    # `set -e` activo y mataria el respaldo entero: la forma `if` no tiene ese filo.
    if [ -s "$COORD/docker.err" ]; then tail -5 "$COORD/docker.err"; fi
  fi
fi

# --- 2. El dump. Con ancla si la hay, sin ancla si no ------------------------
#
# `set -o pipefail` esta activo: si `pg_dump` muere, el pipeline muere, el trap
# se lleva por delante al contenedor de la huella y NUNCA se crea `dump.done`.
# Un dump fallido no puede dejar una huella suelta en el bucket.
if [ -n "$SNAP" ]; then
  log "volcando $DUMP_KEY anclado al snapshot $SNAP"
  docker exec takab-db pg_dump -U postgres -Fc --snapshot="$SNAP" takab |
    aws s3 cp - "$DUMP_KEY" --sse aws:kms --sse-kms-key-id ${kms_key_arn} --region ${region}
else
  log "volcando $DUMP_KEY SIN ancla (no habra huella para $FECHA)"
  docker exec takab-db pg_dump -U postgres -Fc takab |
    aws s3 cp - "$DUMP_KEY" --sse aws:kms --sse-kms-key-id ${kms_key_arn} --region ${region}
fi
log "dump en S3: $DUMP_KEY"

# --- 3. Con el .dump YA en S3, se libera la huella ---------------------------
#
# Este orden importa: si algo se cae entre los dos pasos, queda un dump sin
# huella (INDETERMINADO — honesto) y jamas una huella sin dump (inservible).
if [ -n "$SNAP" ]; then
  : >"$COORD/dump.done"
  RC=1
  RC="$(docker wait "$CID" 2>/dev/null)" || RC=1
  if [ "$RC" = "0" ] && [ -s "$COORD/huella.json" ]; then
    aws s3 cp "$COORD/huella.json" "$HUELLA_KEY" \
      --sse aws:kms --sse-kms-key-id ${kms_key_arn} --region ${region}
    log "huella del origen en S3: $HUELLA_KEY"
  else
    log "AVISO: la huella no se escribio (rc=$RC). El verificador dara INDETERMINADO para $FECHA"
    docker logs "$CID" 2>&1 | tail -20 || true
  fi
fi
EOS
chmod 0755 /opt/takab/bin/takab-backup.sh

# ---------------------------------------------------------------------------
# El cron. MISMO fichero y MISMA hora que los de `user_data.sh.tpl`: se
# SUSTITUYE la linea de aquel, no se anade una segunda.
#
# La salida va a un fichero y no al correo de root: en un EC2 sin MTA, el correo
# de root es ningun sitio, y esta es la traza que se lee en la ventana de T-2.74.
# ---------------------------------------------------------------------------
cat >/etc/cron.d/takab-backup <<'CRON'
0 8 * * * root /opt/takab/bin/takab-backup.sh >>/var/log/takab-backup.log 2>&1
CRON
chmod 0644 /etc/cron.d/takab-backup

# ---------------------------------------------------------------------------
# LA INCOGNITA DE LA FICHA, RESUELTA EN CADA PASADA.
#
# "Confirmado que el contenedor de la nube co-locada tiene el codigo del API
# para invocarlo" no puede quedarse en una casilla marcada de memoria: se
# pregunta aqui, todos los dias, y la respuesta queda en la salida del comando
# SSM. Asi la ventana de T-2.74 empieza sabiendolo, en vez de descubrirlo a
# mitad.
#
# Lo que se comprueba es lo unico que importa: que la imagen desplegada AHORA
# importe el modulo y acepte los flags que el cron le va a teclear. Si la
# respuesta es que no, la accion es `make cloud-images && make cloud-deploy`.
# ---------------------------------------------------------------------------
IMAGEN="$(sed -n 's/^TAKAB_CLOUD_IMAGE=//p' /etc/takab/deploy.env 2>/dev/null | tail -1 || true)"
if [ -z "$IMAGEN" ]; then
  log "AVISO: /etc/takab/deploy.env no declara TAKAB_CLOUD_IMAGE: la huella NO se podra tomar"
elif docker run --rm --entrypoint python "$IMAGEN" -m takab_api.ops.restore_check --help 2>&1 |
  grep -q -- '--coordinate-with-dump'; then
  log "OK: la imagen $IMAGEN sabe tomar la huella anclada"
else
  log "AVISO: la imagen $IMAGEN NO acepta --coordinate-with-dump (imagen anterior a T-2.73.a)."
  log "       El dump seguira subiendo, pero SIN huella. Arreglo: make cloud-images && make cloud-deploy"
fi

log "respaldo logico configurado: ${bucket}/${dump_prefix}<fecha>.dump + .fingerprint.json"
