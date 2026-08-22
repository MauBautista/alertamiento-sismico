output "url" {
  description = "URL publica del sitio. Es la que se declara como `Website URL` en la solicitud de SES."
  value       = local.on ? "https://${var.domain}" : ""
}

output "distribution_domain" {
  description = "Dominio de CloudFront, por si hace falta diagnosticar sin pasar por el DNS del cliente."
  value       = local.on ? aws_cloudfront_distribution.site[0].domain_name : ""
}
