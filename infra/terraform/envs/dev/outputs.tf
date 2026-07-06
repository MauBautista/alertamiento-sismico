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
