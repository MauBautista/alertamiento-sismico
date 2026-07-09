output "cert_arn" {
  value = aws_iot_certificate.this.arn
}

output "secret_arn" {
  value = aws_secretsmanager_secret.this.arn
}

output "hmac_secret_arn" {
  value = aws_secretsmanager_secret.hmac.arn
}
