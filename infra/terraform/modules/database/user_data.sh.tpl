#!/bin/bash
# Aprovisiona el nodo DB (TimescaleDB en Docker). Idempotente via marker;
# cloud-init solo lo ejecuta en el primer boot de la instancia.
# Ojo: sin `set -x` para no volcar passwords a cloud-init-output.log.
set -euo pipefail

MARKER=/var/lib/takab/.provisioned
[ -f "$MARKER" ] && exit 0
mkdir -p /var/lib/takab

# cronie: AL2023 no trae crond por defecto (aws cli v2 si viene preinstalado)
dnf install -y docker cronie
systemctl enable --now docker crond

# Esperar el volumen de datos: el attachment llega despues del primer boot.
DEV=""
for _ in $(seq 1 120); do
  CAND=/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_${volume_id_nodash}
  if [ -e "$CAND" ]; then
    DEV="$(readlink -f "$CAND")"
    break
  fi
  if [ -b /dev/nvme1n1 ]; then
    DEV=/dev/nvme1n1
    break
  fi
  sleep 5
done
if [ -z "$DEV" ]; then
  echo "volumen de datos no disponible" >&2
  exit 1
fi

# Formatear solo si el volumen esta en blanco.
if ! blkid "$DEV" >/dev/null 2>&1; then
  mkfs.xfs "$DEV"
fi
mkdir -p /data
FS_UUID="$(blkid -s UUID -o value "$DEV")"
if ! grep -q "UUID=$FS_UUID" /etc/fstab; then
  echo "UUID=$FS_UUID /data xfs defaults,nofail 0 2" >>/etc/fstab
fi
mountpoint -q /data || mount /data

get_password() {
  aws secretsmanager get-secret-value \
    --secret-id "$1" \
    --region ${region} \
    --query SecretString \
    --output text |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])'
}

SU_PASS="$(get_password takab/dev/db/superuser)"

# La imagen timescaledb-ha corre como postgres (uid 1000) y su datadir es
# /home/postgres/pgdata/data.
mkdir -p /data/pgdata
chown 1000:1000 /data/pgdata

if ! docker ps -a --format '{{.Names}}' | grep -qx takab-db; then
  docker run -d --name takab-db --restart unless-stopped \
    -p 5432:5432 \
    -v /data/pgdata:/home/postgres/pgdata/data \
    -e POSTGRES_PASSWORD="$SU_PASS" \
    -e POSTGRES_DB=takab \
    timescale/timescaledb-ha:pg16
fi

for _ in $(seq 1 60); do
  if docker exec takab-db pg_isready -U postgres -d takab >/dev/null 2>&1; then
    break
  fi
  sleep 5
done
docker exec takab-db pg_isready -U postgres -d takab

# Roles de servicio: LOGIN + password (+ atributos que la migracion 0001 solo
# fija al CREAR el rol — como aqui el rol nace ANTES de migrar, BYPASSRLS debe
# ponerse aqui o takab_ingest quedaria bloqueado por RLS en T-1.17). Grants y
# ownership siguen siendo de la migracion.
init_role() {
  ROLE_NAME="$1"
  ROLE_PASS="$(get_password "$2")"
  EXTRA_ATTRS="$3"
  docker exec -i takab-db psql -U postgres -d takab -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$ROLE_NAME') THEN
    CREATE ROLE $ROLE_NAME;
  END IF;
END
\$\$;
ALTER ROLE $ROLE_NAME WITH LOGIN PASSWORD '$ROLE_PASS' $EXTRA_ATTRS;
SQL
}

init_role takab_migrator takab/dev/db/migrator ""
init_role takab_app takab/dev/db/app ""
init_role takab_ingest takab/dev/db/ingest "BYPASSRLS"

# Respaldo logico nocturno a S3 (08:00 UTC; los snapshots DLM van a las 03:00).
cat >/etc/cron.d/takab-backup <<'CRON'
0 8 * * * root docker exec takab-db pg_dump -U postgres -Fc takab | aws s3 cp - s3://${db_backups_bucket}/takab-$(date +\%F).dump --sse aws:kms --sse-kms-key-id ${kms_key_arn} --region ${region}
CRON

touch "$MARKER"
