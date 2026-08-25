output "url" {
  description = "URL publica del sitio. Es la que se declara como `Website URL` en la solicitud de SES."
  value       = local.on ? "https://${var.domain}" : ""
}

output "distribution_domain" {
  description = "Dominio de CloudFront, por si hace falta diagnosticar sin pasar por el DNS del cliente."
  value       = local.on ? aws_cloudfront_distribution.site[0].domain_name : ""
}

# [landing] Los lee deploy/landing/deploy.sh via `terraform output -raw` (mismo
# patron que db-tunnel/cloud-images): el script no teclea nombres de recursos.
output "bucket" {
  description = "Bucket S3 del sitio publico; destino del `aws s3 sync` del deploy."
  value       = local.on ? aws_s3_bucket.site[0].id : ""
}

output "distribution_id" {
  description = "ID de la distribucion CloudFront; destino de la invalidacion del deploy."
  value       = local.on ? aws_cloudfront_distribution.site[0].id : ""
}
