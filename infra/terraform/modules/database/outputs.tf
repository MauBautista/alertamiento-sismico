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
