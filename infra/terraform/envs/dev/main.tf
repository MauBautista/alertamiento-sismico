data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  # Prefijo de los secretos HMAC de comandos, UNO por gabinete (T-1.38). El rol
  # de la instancia recibe GetSecretValue por WILDCARD de este prefijo: tras el
  # split cert/HMAC el prefijo contiene exactamente la clase de secretos que la
  # nube necesita (jamas claves privadas mTLS) y un gateway nuevo es comandable
  # sin re-aplicar IAM. El * final tambien cubre el sufijo aleatorio que
  # Secrets Manager anade al ARN.
  gateway_hmac_prefix = "takab/dev/gateway-hmac"
}

module "network" {
  source = "../../modules/network"
}

module "kms" {
  source = "../../modules/kms"
}

module "messaging" {
  source = "../../modules/messaging"

  account_id = data.aws_caller_identity.current.account_id
}

module "storage" {
  source = "../../modules/storage"

  account_id         = data.aws_caller_identity.current.account_id
  kms_key_arn        = module.kms.data_key_arn
  backfill_queue_arn = module.messaging.queues["backfill"].arn
}

module "database" {
  source = "../../modules/database"

  subnet_id         = module.network.subnet_ids[0]
  sg_db_id          = module.network.sg_db_id
  kms_key_arn       = module.kms.data_key_arn
  db_backups_bucket = module.storage.db_backups_bucket
  instance_type     = var.instance_type

  # Workers de ingesta co-locados en la instancia (default dev — plan §C.1).
  worker_queue_arns = concat(
    [for q in module.messaging.queues : q.arn],
    values(module.messaging.dlq_arns),
  )
  worker_ecr_repo_arns = values(module.registry.repository_arns)
  worker_s3_read_arns = [
    "${module.storage.transfer_bucket.arn}/*",
    "${module.storage.evidence_bucket.arn}/*", # ingesta de evidencia (sha256 real)
  ]
  # Grant service co-locado (T-1.25): prefijos presignables + topic del grant.
  worker_s3_presign_put_arns = [
    "${module.storage.transfer_bucket.arn}/backfill/*",
    "${module.storage.evidence_bucket.arn}/evidence/*",
  ]
  worker_iot_publish_topic_arns = [
    "arn:aws:iot:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:topic/takab/backfill/grant/*",
    "arn:aws:iot:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:topic/takab/cmd/*",
    "arn:aws:iot:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:topic/takab/cfg/*",
  ]

  # Claves HMAC de comandos POR GABINETE (T-1.38): wildcard del prefijo
  # DEDICADO (no "*"), ver la nota de locals.gateway_hmac_prefix.
  worker_secret_arns = [
    "arn:aws:secretsmanager:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:secret:${local.gateway_hmac_prefix}/*",
  ]
}

module "identity" {
  source = "../../modules/identity"

  account_id          = data.aws_caller_identity.current.account_id
  ses_verified_emails = var.ses_verified_emails

  # El callback de localhost se conserva SIEMPRE (modules/identity): el `make dev`
  # local debe seguir funcionando aunque la consola este publicada.
  extra_callback_urls = var.serve_enabled ? ["${module.serve.console_url}/auth/callback"] : []
  extra_logout_urls   = var.serve_enabled ? ["${module.serve.console_url}/"] : []
}

# Exposicion publica de la consola (T-1.37). SG separado y adjunto a la ENI: se puede
# desconectar sin recrear la instancia ni tocar la base de datos.
module "serve" {
  source = "../../modules/serve"

  enabled              = var.serve_enabled
  vpc_id               = module.network.vpc_id
  instance_id          = module.database.instance_id
  network_interface_id = module.database.primary_network_interface_id
  allowed_cidrs        = var.web_allowed_cidrs
}

module "registry" {
  source = "../../modules/registry"
}

module "iot_core" {
  source = "../../modules/iot-core"

  account_id      = data.aws_caller_identity.current.account_id
  region          = data.aws_region.current.region
  events_queue    = module.messaging.queues["events"]
  telemetry_queue = module.messaging.queues["telemetry"]
  backfill_queue  = module.messaging.queues["backfill"]
}

module "iot_gateway" {
  source   = "../../modules/iot-gateway"
  for_each = toset(var.gateway_fleet)

  thing_name         = each.value
  thing_type_name    = module.iot_core.thing_type_name
  thing_group_name   = module.iot_core.thing_group_name
  fleet_policy_name  = module.iot_core.fleet_policy_name
  hmac_secret_prefix = local.gateway_hmac_prefix
}

module "ci_oidc" {
  source = "../../modules/ci-oidc"

  state_bucket_arn = "arn:aws:s3:::takab-tfstate-${data.aws_caller_identity.current.account_id}"
  lock_table_arn   = "arn:aws:dynamodb:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:table/takab-tflock"
}
