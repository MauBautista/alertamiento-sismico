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
