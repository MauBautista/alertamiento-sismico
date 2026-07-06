output "data_key_arn" {
  value = aws_kms_key.data.arn
}

output "data_key_id" {
  value = aws_kms_key.data.key_id
}

output "tenant_key_arns" {
  value = { for k, key in aws_kms_key.tenant : k => key.arn }
}
