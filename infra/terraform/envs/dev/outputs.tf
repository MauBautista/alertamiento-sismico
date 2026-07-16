output "iot_endpoint" {
  value = module.iot_core.iot_endpoint
}

output "queue_urls" {
  value = { for k, q in module.messaging.queues : k => q.url }
}

output "user_pool_id" {
  value = module.identity.user_pool_id
}

output "client_id" {
  value = module.identity.client_id
}

output "hosted_ui_domain" {
  value = module.identity.hosted_ui_domain
}

output "issuer" {
  value = module.identity.issuer
}

# --- Superficie móvil (T-2.02 · decisión #7) --------------------------------

output "mobile_tactical_client_id" {
  value = module.identity.mobile_tactical_client_id
}

output "occupants_user_pool_id" {
  value = module.identity.occupants_user_pool_id
}

output "occupants_client_id" {
  value = module.identity.occupants_client_id
}

output "occupants_hosted_ui_domain" {
  value = module.identity.occupants_hosted_ui_domain
}

output "occupants_issuer" {
  value = module.identity.occupants_issuer
}

output "evidence_bucket" {
  value = module.storage.evidence_bucket.name
}

output "transfer_bucket" {
  value = module.storage.transfer_bucket.name
}

output "db_backups_bucket" {
  value = module.storage.db_backups_bucket.name
}

output "db_instance_id" {
  value = module.database.instance_id
}

output "db_private_ip" {
  value = module.database.private_ip
}

output "db_public_ip" {
  value = module.database.public_ip
}

output "db_secret_arns" {
  value = module.database.secret_arns
}

output "ecr_repo_urls" {
  value = module.registry.repository_urls
}

output "ci_role_arn" {
  value = module.ci_oidc.role_arn
}

# --- Consola SOC publicada (T-1.37) -------------------------------------------
output "console_url" {
  value = module.serve.console_url
}

output "console_public_host" {
  value = module.serve.public_host
}

output "acme_email" {
  value = var.acme_email
}

output "aws_region" {
  value = data.aws_region.current.region
}

# La nube resuelve la clave HMAC POR GABINETE contra "{prefix}/{iot_thing}"
# (T-1.38); deploy.sh lo inyecta como TAKAB_API_COMMAND_HMAC_SECRET_PREFIX.
output "command_hmac_secret_prefix" {
  value = local.gateway_hmac_prefix
}

output "dlq_urls" {
  value = module.messaging.dlq_urls
}
