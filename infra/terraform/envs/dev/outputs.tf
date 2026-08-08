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

# --- [T-2.72] PITR: el RPO que produce la maquina -----------------------------
#
# Existe para que el runbook de backup pueda CITAR una cifra en vez de teclearla.
# Hasta hoy el §2 de `RUNBOOK-backup-restore-db.md` decia "RPO ≤ 24 h" y
# "objetivos PROPUESTOS: RPO ≤ 15 min" — dos numeros escritos por un humano que
# nada obligaba a seguir siendo ciertos. `terraform output rpo_seconds` sale de
# los atributos de la alarma que lo sostiene.
output "rpo_seconds" {
  value = module.observability.rpo_seconds

  # La costura entre los dos modulos es el unico sitio donde el RPO puede volver
  # a ser una promesa: si alguien pasara un literal a `observability` en vez del
  # output de `database`, cada modulo seguiria coherente consigo mismo y el
  # conjunto mentiria. Los dos tests de modulo son ciegos a esto por
  # construccion —cada uno solo ve su lado—, asi que la guardia vive aqui.
  #
  # CUANDO SE COMPRUEBA, dicho sin adornos: SOLO en el `apply`. `terraform
  # validate` no evalua preconditions, y meter un `plan` de este entorno en CI
  # choca con el `profile = "takab-dev"` cableado en `providers.tf` (exige
  # credenciales SSO). O sea que esta guardia no es vacua —se ha visto fallar a
  # mano— pero su unica ocasion real de dispararse es la ventana HUMANO-AWS de
  # T-2.74. No es un sustituto de los tests de modulo: es el ultimo filtro antes
  # de que el numero salga publicado.
  precondition {
    condition     = module.observability.wal_archive_alarm_threshold_s == module.database.wal_archive_max_age_s
    error_message = "El umbral de la alarma de archivado y la edad maxima que declara la DB han divergido: la DB estaria validando su archive_timeout contra un numero que no vigila nadie, y rpo_seconds describiria a una alarma que no existe."
  }
}

output "pitr" {
  value = module.database.pitr
}

# --- Push móvil (T-2.04) ------------------------------------------------------

output "push_apns_application_arn" {
  value     = module.push.apns_application_arn
  sensitive = true
}

output "push_fcm_application_arn" {
  value     = module.push.fcm_application_arn
  sensitive = true
}
