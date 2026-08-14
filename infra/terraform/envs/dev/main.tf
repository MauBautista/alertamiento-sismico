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

  # [T-2.72] PITR. Los prefijos y la retencion los DECIDE `storage` (es el unico
  # podador de la cadena) y bajan aqui enteros: escribir literales en este punto
  # es exactamente como se parte una cadena de recuperacion sin que ningun plan
  # se ponga rojo — el archivador escribiria bajo un prefijo y la expiracion
  # gobernaria otro.
  dump_key_prefix = module.storage.db_backups_prefixes.dump_key
  pitr = {
    prefix                    = module.storage.db_backups_prefixes.pitr
    server_name               = module.storage.pitr_server_name
    wal_retention_days        = module.storage.pitr_retention.wal_days
    base_backup_interval_days = module.storage.pitr_retention.base_backup_interval_days
    chain_margin              = module.storage.pitr_retention.chain_margin
  }

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
    "arn:aws:iot:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:topic/takab/catalog/*",
  ]

  # Claves HMAC de comandos POR GABINETE (T-1.38): wildcard del prefijo
  # DEDICADO (no "*"), ver la nota de locals.gateway_hmac_prefix.
  worker_secret_arns = [
    "arn:aws:secretsmanager:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:secret:${local.gateway_hmac_prefix}/*",
  ]

  # [T-1.62] Envio de correo del worker notify (SES). El ARN se CONSTRUYE aqui en
  # vez de leerlo de module.identity a proposito: identity -> serve -> database ya
  # es una cadena, y tomar el output cerraria el ciclo. Mismo patron que los topics
  # de IoT de arriba. La identidad verificada NO concede envio: sin este grant el
  # notify recibe AccessDenied y el job del dictamen muere (visto en produccion el
  # 2026-07-14; los correos de SNS seguian llegando y tapaban el hueco).
  notify_ses_identity_arns = [
    for email in var.ses_verified_emails :
    "arn:aws:ses:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:identity/${email}"
  ]

  # [T-2.78.b] El REMITENTE DE DOMINIO, por la MISMA variable que crea la
  # identidad en `module.identity`. Esta linea es la ficha entera: la lista de
  # arriba itera `ses_verified_emails`, o sea identidades POR DIRECCION, asi que
  # mover el remitente a un dominio sin tocar esto deja al worker `notify` con
  # AccessDenied en cada envio — y los correos de CloudWatch (SNS, permiso propio)
  # siguen llegando y tapan el hueco. Es el fallo del 2026-07-14, calcado.
  #
  # Se pasa el DOMINIO y no el ARN a proposito: `modules/database` compone el ARN
  # con su propia region y cuenta, igual que hace con los topics de IoT de arriba,
  # y asi no hace falta leer un output de `module.identity` — identity -> serve ->
  # database ya es una cadena y eso cerraria el ciclo.
  #
  # Y hay un borde medido en `modules/database/tests/pitr.tftest.hcl`: el
  # statement de envio se emite si hay ALGUNA identidad, no solo si la lista de
  # direcciones no esta vacia. El dia que el remitente sea solo el dominio, vaciar
  # `ses_verified_emails` es lo natural — y con la condicion escrita sobre la
  # lista, eso borraria el permiso entero.
  notify_ses_domain = var.ses_domain
}

module "identity" {
  source = "../../modules/identity"

  account_id          = data.aws_caller_identity.current.account_id
  ses_verified_emails = var.ses_verified_emails

  # [T-2.78.b] Identidad de DOMINIO (DKIM + MAIL FROM + DMARC + rebotes con
  # destino). Vacia = no se crea nada, el apply de hoy no cambia. El mismo
  # `var.ses_domain` baja tambien a `module.database` (permiso de envio): son las
  # dos mitades de una sola decision y por eso comparten variable.
  #
  # El buzon de rebotes es el de on-call y no una variable propia: quien recibe
  # las alarmas operativas es quien tiene que enterarse de que el correo del
  # sistema esta rebotando. Un buzon distinto seria un segundo sitio que mirar.
  ses_domain              = var.ses_domain
  ses_mail_from_subdomain = var.ses_mail_from_subdomain
  ses_feedback_email      = var.ops_alert_email
  ses_dmarc_policy        = var.ses_dmarc_policy
  ses_dmarc_rua           = var.ses_dmarc_rua
  ses_route53_zone_id     = var.ses_route53_zone_id

  # El callback de localhost se conserva SIEMPRE (modules/identity): el `make dev`
  # local debe seguir funcionando aunque la consola este publicada.
  extra_callback_urls = var.serve_enabled ? ["${module.serve.console_url}/auth/callback"] : []
  extra_logout_urls   = var.serve_enabled ? ["${module.serve.console_url}/"] : []
}

# Push móvil (T-2.04): SNS platform applications APNs/FCM, condicionales a que
# existan credenciales reales (sin ellas la API queda en provider simulado).
module "push" {
  source = "../../modules/push"

  env                      = "dev"
  apns_signing_key         = var.push_apns_signing_key
  apns_signing_key_id      = var.push_apns_signing_key_id
  apns_team_id             = var.push_apns_team_id
  fcm_service_account_json = var.push_fcm_service_account_json
  worker_role_name         = module.database.instance_role_name
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

# Observabilidad hacia HUMANOS (A-4 de la auditoria de cierre): SNS on-call +
# alarmas de DLQ, instancia co-locada, errores de reglas IoT y gabinete real
# SIN ENLACE. Costo: centavos/mes (SNS email gratis; ~10 alarmas estandar).
module "observability" {
  source = "../../modules/observability"

  ops_alert_email           = var.ops_alert_email
  dlq_names                 = module.messaging.dlq_names
  instance_id               = module.database.instance_id
  iot_rule_errors_log_group = module.iot_core.rule_errors_log_group_name
  paged_gateways            = var.paged_gateways

  # [T-2.78.a] La URL se DERIVA de la consola publicada, no se teclea: es la misma
  # que sirve la API detras de Caddy, y un literal aqui apuntaria a la IP de ayer
  # el dia que la elastica cambie. Doble guarda a proposito — sin consola no hay
  # endpoint que suscribir, y la bandera propia obliga a que la API este
  # desplegada ANTES (ver la variable: la suscripcion se confirma durante el
  # apply, asi que un endpoint que todavia no existe mata el apply).
  ops_alert_https_endpoint = (
    var.serve_enabled && var.ops_alert_https_subscriber_enabled
    ? "${module.serve.console_url}/api/ops/alerts/sns"
    : ""
  )

  # [T-2.72] El umbral de la alarma de atasco del archivado SALE de la DB, que es
  # quien valida su `archive_timeout` contra el. Un literal aqui haria que la DB
  # se validara contra un numero y la alarma vigilara otro, y el RPO publicado
  # describiria a una alarma que no existe. El output `rpo_seconds` de abajo lo
  # comprueba antes de dejar terminar el apply.
  wal_archive_max_age_s = module.database.wal_archive_max_age_s

  # [T-2.72.b] Y el umbral del ANCLA de esa misma cadena, por el mismo camino y
  # por la misma razon: `modules/database` lo deriva de
  # `pitr.base_backup_interval_days * pitr.chain_margin`, que son las cifras con
  # las que `modules/storage` calcula la retencion. Escribir aqui el numero de
  # dias seria exactamente como se rompe una cadena PITR sin que ningun plan se
  # ponga rojo: la alarma vigilaria una cadena y el lifecycle podaria otra.
  base_backup_max_age_s = module.database.base_backup_max_age_s
}
