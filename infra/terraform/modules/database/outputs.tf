output "instance_id" {
  value = aws_instance.db.id
}

output "private_ip" {
  value = aws_instance.db.private_ip
}

output "public_ip" {
  value = aws_instance.db.public_ip
}

output "secret_arns" {
  value = { for k, s in aws_secretsmanager_secret.db : k => s.arn }
}

output "db_endpoint" {
  value = "${aws_instance.db.private_ip}:5432"
}

# ENI primaria: el SG web (modulo `serve`) se adjunta aqui, no a la instancia, para
# poder desconectar el acceso publico sin recrear la maquina.
output "primary_network_interface_id" {
  value = aws_instance.db.primary_network_interface_id
}

# [T-2.04] Rol IAM de la instancia (la API/worker corre aquí en dev): el módulo
# `push` le adjunta los permisos de SNS platform endpoints.
output "instance_role_name" {
  value = aws_iam_role.db.name
}

# [T-2.72] La edad maxima tolerada del archivado viaja de AQUI a
# `modules/observability`, donde se convierte en el umbral de la alarma y, por
# tanto, en el termino dominante del RPO. Es una sola cifra con un solo dueño: si
# el entorno cablease un literal en la alarma, el `archive_timeout` de esta
# instancia se estaria validando contra un numero que no es el que vigila nadie.
output "wal_archive_max_age_s" {
  value = var.wal_archive_max_age_s
}

# [T-2.72.b] El umbral de la alarma del BACKUP BASE, derivado de las MISMAS
# variables que gobiernan la retencion.
#
# No es un numero de politica: es un termino de la desigualdad que mantiene viva
# la cadena (`wal_retention_days >= base_backup_interval_days * chain_margin`,
# validada en `variables.tf`). Se calcula aqui —y no en `modules/observability`—
# porque este es el unico modulo donde estan las dos cifras y donde se programa el
# cron que produce esos backups. Un literal en la alarma se desincroniza el dia
# que cambie la politica de retencion y la vigilancia pasaria a describir una
# cadena distinta de la que el lifecycle de S3 poda.
#
# LO QUE ESTE UMBRAL NO ES, y conviene tenerlo escrito: NO es un aviso temprano.
# Cuando la edad del ancla supera `intervalo * margen`, ya han fallado `margen`
# backups base SEGUIDOS, y con los valores por defecto ese producto (7 x 2 = 14
# dias) es EXACTAMENTE `wal_retention_days` — o sea que el correo llega justo
# cuando la ventana de recuperacion se esta cerrando, no antes. Es lo que pide la
# ficha (T-2.72.b) y es lo unico que se puede derivar de las variables de
# retencion; un aviso temprano de verdad seria una segunda alarma a `intervalo`
# dias, que caza el PRIMER backup base fallido. Queda fichado, no supuesto.
output "base_backup_max_age_s" {
  description = "Edad maxima tolerada del ultimo backup base, en segundos: `base_backup_interval_days * chain_margin` dias."
  value       = var.pitr.base_backup_interval_days * var.pitr.chain_margin * 86400
}

# La configuracion PITR tal y como quedo, para que el runbook pueda CITAR lo que
# produce la maquina en vez de lo que tecleo un humano.
output "pitr" {
  value = {
    prefix                    = var.pitr.prefix
    server_name               = var.pitr.server_name
    archive_timeout_s         = var.wal_archive_timeout_s
    max_archive_age_s         = var.wal_archive_max_age_s
    wal_retention_days        = var.pitr.wal_retention_days
    base_backup_interval_days = var.pitr.base_backup_interval_days
    chain_margin              = var.pitr.chain_margin
    ssm_document              = aws_ssm_document.pitr.name
  }
}

# [T-2.81.a] El umbral de la alarma de la retencion de PII, DERIVADO de la
# cadencia del cron que vive en este modulo (diaria) por el margen declarado. Un
# literal en `modules/observability` se desincronizaria el dia que la cadencia
# cambie, y la alarma pasaria a vigilar una periodicidad que no ocurre.
output "pii_retention_max_age_s" {
  description = "Edad maxima tolerada de la ultima corrida CORRECTA de retencion de PII, en segundos: cadencia diaria x `pii_retention_chain_margin`."
  value       = var.pii_retention_chain_margin * 86400
}

# Lo que produce la maquina, para que el runbook pueda CITARLO en vez de repetir
# lo que alguien tecleo.
output "pii_retention" {
  value = {
    ssm_document   = aws_ssm_document.prune_pii.name
    schedule_utc   = "06:00"
    metric_name    = local.pii_retention_metric_name
    max_age_s      = var.pii_retention_chain_margin * 86400
    windows_days   = var.pii_retention_windows_days
    reglas_activas = length(var.pii_retention_windows_days)
  }
}
