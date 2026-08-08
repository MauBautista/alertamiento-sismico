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
