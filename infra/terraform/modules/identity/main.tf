terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

data "aws_region" "current" {}

locals {
  # atributo custom -> longitud maxima (claims del JWT; ver takab-docs/RBAC-TAKAB.md)
  custom_attributes = {
    tenant_id  = 36
    role       = 32
    site_scope = 2048
    zone_id    = 36
    surface    = 8
  }

  groups = {
    takab_superadmin = "Plataforma TAKAB: administracion total"
    takab_support    = "Plataforma TAKAB: soporte"
    tenant_admin     = "Administrador del tenant"
    soc_operator     = "Operador SOC"
    gov_operator     = "Operador de gobierno / Proteccion Civil"
    inspector        = "Inspector estructural"
    building_admin   = "Administrador de edificio"
    brigadista       = "Brigadista"
    security_guard   = "Guardia de seguridad"
    occupant         = "Ocupante"
  }
}

resource "aws_cognito_user_pool" "this" {
  name                = "takab-dev"
  deletion_protection = "INACTIVE"

  mfa_configuration = "ON"
  software_token_mfa_configuration {
    enabled = true
  }

  password_policy {
    minimum_length    = 12
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # dev: usuarios sembrados por script, sin self-signup
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  dynamic "schema" {
    for_each = local.custom_attributes

    content {
      name                     = schema.key
      attribute_data_type      = "String"
      mutable                  = true
      developer_only_attribute = false

      string_attribute_constraints {
        min_length = 0
        max_length = schema.value
      }
    }
  }
}

resource "aws_cognito_user_group" "this" {
  for_each = local.groups

  name         = each.key
  user_pool_id = aws_cognito_user_pool.this.id
  description  = each.value
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = "takab-dev-${var.account_id}"
  user_pool_id = aws_cognito_user_pool.this.id
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "takab-web"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = concat(["http://localhost:5173/auth/callback"], var.extra_callback_urls)
  logout_urls                          = concat(["http://localhost:5173/"], var.extra_logout_urls)
  supported_identity_providers         = ["COGNITO"]

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 8

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "hours"
  }

  prevent_user_existence_errors = "ENABLED"

  # Regla de oro #5: los anchors de tenancy/rol (custom:tenant_id, custom:role,
  # custom:site_scope, custom:zone_id, custom:surface) son administrados por el
  # admin (AdminUpdateUserAttributes, que NO se rige por write_attributes), igual
  # que los grupos. Al declarar write_attributes SIN ningún custom:*, el propio
  # usuario NO puede reasignarse su tenant vía self-service UpdateUserAttributes:
  # sin esta lista, el client permitiría escribir todos los atributos mutables.
  write_attributes = ["name"]
}

# Identidades verificadas: SES en sandbox solo entrega a destinos verificados.
resource "aws_sesv2_email_identity" "this" {
  for_each = toset(var.ses_verified_emails)

  email_identity = each.value
}

# =============================================================================
# [T-2.78.b] IDENTIDAD DE DOMINIO: DKIM, MAIL FROM propio, DMARC y rebotes
#
# El recurso de arriba es una identidad POR DIRECCION. Sirve para la sandbox y no
# sirve para nada mas: no firma con DKIM, no alinea SPF, no da MAIL FROM propio y
# no publica un DMARC. Todo eso exige una identidad de DOMINIO, y hasta hoy solo
# se podia crear a clics — y lo que se hace a clics no se vuelve a hacer igual ni
# se revisa en un diff.
#
# TODO lo de esta seccion esta condicionado a `var.ses_domain`, vacia por defecto
# (patron del modulo `push/`): sin dominio, el apply de hoy NO cambia nada. Lo
# comprueba `tests/ses_domain.tftest.hcl`, que ademas lleva un CENSO — un recurso
# nuevo aqui sin su asercion de "con la variable vacia no se crea" pone el test en
# rojo, para que nadie pueda anadir infraestructura que se cree sola.
# =============================================================================

locals {
  ses_domain_enabled   = var.ses_domain != ""
  ses_dns_enabled      = var.ses_domain != "" && var.ses_route53_zone_id != ""
  ses_mail_from_domain = "${var.ses_mail_from_subdomain}.${var.ses_domain}"

  # El `rua` no se pone vacio: un `rua=mailto:` sin buzon es un registro invalido.
  # Sin rua, DMARC funciona pero a ciegas — se publica la politica y nadie ve
  # quien esta suplantando el dominio.
  ses_dmarc_value = var.ses_dmarc_rua == "" ? "v=DMARC1; p=${var.ses_dmarc_policy}" : "v=DMARC1; p=${var.ses_dmarc_policy}; rua=mailto:${var.ses_dmarc_rua}"
}

# El configuration set es lo que convierte "mandamos correo" en "sabemos que pasa
# con el correo que mandamos". Se aplica POR DEFECTO a la identidad de dominio
# (`configuration_set_name` mas abajo): sin esa asociacion, el correo sale igual y
# los eventos no se publican en ningun sitio — plan verde, topic vacio para
# siempre.
resource "aws_sesv2_configuration_set" "ses" {
  count = local.ses_domain_enabled ? 1 : 0

  configuration_set_name = "takab-dev-correo"

  delivery_options {
    # El correo de esta plataforma lleva solicitudes de dictamen y avisos de
    # incidente. `REQUIRE` prefiere no entregar a entregar en claro.
    tls_policy = "REQUIRE"
  }

  reputation_options {
    reputation_metrics_enabled = true
  }

  sending_options {
    sending_enabled = true
  }

  # La lista de supresion de la CUENTA, aplicada a este set: una direccion que
  # rebota duro deja de recibir intentos. No es cosmetica — reintentar contra una
  # direccion muerta es lo que hunde la reputacion del dominio, y con la
  # reputacion hundida deja de llegar el correo de TODOS los tenants.
  suppression_options {
    suppressed_reasons = ["BOUNCE", "COMPLAINT"]
  }
}

resource "aws_sesv2_email_identity" "domain" {
  count = local.ses_domain_enabled ? 1 : 0

  email_identity         = var.ses_domain
  configuration_set_name = aws_sesv2_configuration_set.ses[0].configuration_set_name

  # EASY DKIM, no BYODKIM. Declarar `domain_signing_private_key` aqui haria que la
  # llave privada con la que se firma TODO el correo saliente viviera en un
  # tfvars, y rotarla dejaria de ser cosa de AWS. Se pide 2048 explicitamente
  # porque el default de la cuenta puede ser 1024, y 1024 ya lo rechazan
  # validadores estrictos.
  #
  # Los TRES tokens que salen de aqui son la unica fuente de los CNAME. No se
  # hornean: no existen hasta el apply y son distintos por identidad.
  dkim_signing_attributes {
    next_signing_key_length = "RSA_2048_BIT"
  }
}

# MAIL FROM propio. Es lo que alinea SPF con NUESTRO dominio en vez de con AWS.
#
# `behavior_on_mx_failure = REJECT_MESSAGE` es la decision que muerde, y va del
# lado ruidoso a proposito. Con `USE_DEFAULT_VALUE`, si el MX del subdominio no
# resuelve, SES SIGUE ENVIANDO con el Return-Path de `amazonses.com`: la
# alineacion SPF se pierde, el correo se va a spam y nada falla — el inspector no
# recibe su solicitud de dictamen y el sistema cree que si. Con `REJECT_MESSAGE`
# esa averia de DNS se convierte en un error que el worker VE y registra. Es el
# principio de T-2.75 aplicado al correo: el canal que no entrega no finge.
resource "aws_sesv2_email_identity_mail_from_attributes" "domain" {
  count = local.ses_domain_enabled ? 1 : 0

  email_identity         = aws_sesv2_email_identity.domain[0].email_identity
  mail_from_domain       = local.ses_mail_from_domain
  behavior_on_mx_failure = "REJECT_MESSAGE"
}

# --- Rebotes y quejas CON DESTINO ---------------------------------------------
#
# "https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html" exige
# declarar que existe un proceso para tratar rebotes y quejas. Antes de esta ficha
# no habia ni topic: el proceso solo se podia declarar mintiendo. La validacion de
# `ses_feedback_email` hace imposible declarar el dominio sin buzon.
resource "aws_sns_topic" "ses_feedback" {
  count = local.ses_domain_enabled ? 1 : 0

  name = "takab-dev-ses-feedback"
}

# SES no puede publicar en el topic solo porque su ARN este escrito en el event
# destination: hace falta politica de RECURSO. Sin ella el destino se crea sin
# error y falla al ENTREGAR el primer rebote — un fallo en tiempo de ejecucion
# sobre un camino que nadie mira hasta que hace falta.
#
# `AWS:SourceAccount` acota quien puede usar este topic como destino de eventos:
# sin la condicion, el permiso es "cualquier cuenta de SES del mundo".
resource "aws_sns_topic_policy" "ses_feedback" {
  count = local.ses_domain_enabled ? 1 : 0

  arn = aws_sns_topic.ses_feedback[0].arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "SesPublishFeedback"
      Effect    = "Allow"
      Principal = { Service = "ses.amazonaws.com" }
      Action    = "SNS:Publish"
      Resource  = aws_sns_topic.ses_feedback[0].arn
      Condition = {
        StringEquals = { "AWS:SourceAccount" = var.account_id }
      }
    }]
  })
}

# La suscripcion por email exige CONFIRMACION manual, igual que la de on-call: el
# apply no termina el trabajo hasta que el humano confirma.
resource "aws_sns_topic_subscription" "ses_feedback" {
  count = local.ses_domain_enabled ? 1 : 0

  topic_arn = aws_sns_topic.ses_feedback[0].arn
  protocol  = "email"
  endpoint  = var.ses_feedback_email
}

# `REJECT` y `RENDERING_FAILURE` van con los dos obvios porque son las dos formas
# de NO enviar que no producen rebote: SES rechaza el mensaje (virus, supresion) o
# la plantilla no renderiza. Sin ellas, un correo que jamas salio es
# indistinguible de uno entregado. `DELIVERY_DELAY` avisa del caso lento, que en
# una solicitud de dictamen con reloj cuenta como fallo.
resource "aws_sesv2_configuration_set_event_destination" "ses_feedback" {
  count = local.ses_domain_enabled ? 1 : 0

  configuration_set_name = aws_sesv2_configuration_set.ses[0].configuration_set_name
  event_destination_name = "rebotes-y-quejas"

  event_destination {
    enabled              = true
    matching_event_types = ["BOUNCE", "COMPLAINT", "REJECT", "RENDERING_FAILURE", "DELIVERY_DELAY"]

    sns_destination {
      topic_arn = aws_sns_topic.ses_feedback[0].arn
    }
  }
}

# --- DNS, SOLO si la zona vive en esta cuenta ---------------------------------
#
# Los VALORES no se hornean nunca (criterio 4 de la ficha): los tres tokens de
# DKIM salen de la respuesta de la API (`dkim_signing_attributes[0].tokens`) y no
# existen hasta el apply; el host del MX se compone con la REGION del proveedor.
# Un literal en el repo apunta al sitio equivocado en cuanto cambia cualquiera de
# las dos cosas, la verificacion no termina nunca y ningun plan se pone rojo.
#
# TTL corto (1800) a proposito: durante la puesta en marcha estos registros se
# corrigen, y un TTL de un dia convierte cada correccion en una espera de un dia.
resource "aws_route53_record" "ses_dkim" {
  count = local.ses_dns_enabled ? 3 : 0

  zone_id = var.ses_route53_zone_id
  name    = "${aws_sesv2_email_identity.domain[0].dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.ses_domain}"
  type    = "CNAME"
  ttl     = 1800
  records = ["${aws_sesv2_email_identity.domain[0].dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}

# El MX del subdominio MAIL FROM es por donde vuelven los rebotes. Con
# `REJECT_MESSAGE` arriba, si este registro falta NO se envia correo: es el precio
# consciente de no fingir alineacion.
resource "aws_route53_record" "ses_mail_from_mx" {
  count = local.ses_dns_enabled ? 1 : 0

  zone_id = var.ses_route53_zone_id
  name    = local.ses_mail_from_domain
  type    = "MX"
  ttl     = 1800
  records = ["10 feedback-smtp.${data.aws_region.current.region}.amazonses.com"]
}

resource "aws_route53_record" "ses_mail_from_spf" {
  count = local.ses_dns_enabled ? 1 : 0

  zone_id = var.ses_route53_zone_id
  name    = local.ses_mail_from_domain
  type    = "TXT"
  ttl     = 1800
  records = ["v=spf1 include:amazonses.com ~all"]
}

resource "aws_route53_record" "ses_dmarc" {
  count = local.ses_dns_enabled ? 1 : 0

  zone_id = var.ses_route53_zone_id
  name    = "_dmarc.${var.ses_domain}"
  type    = "TXT"
  ttl     = 1800
  records = [local.ses_dmarc_value]
}

# =============================================================================
# POOL DE OCUPANTES (T-2.02 · decisión #7 RATIFICADA 2026-07-15)
# Cognito no permite MFA por grupo y poner el pool principal en OPTIONAL
# dejaría a un rol táctico declinar su TOTP (specs/cognito-pool-v1.md §5.2).
# Por eso el `occupant` vive en un pool SEPARADO: login simple (email+password)
# con MFA OPCIONAL (opt-in TOTP desde la app). El pool principal queda ON.
# La API valida ambos issuers y ancla pool→rol (T-2.03): un token de este pool
# solo puede portar custom:role=occupant.
# =============================================================================

resource "aws_cognito_user_pool" "occupants" {
  name                = "takab-dev-occupants"
  deletion_protection = "INACTIVE"

  # OPTIONAL (no OFF): el opt-in de TOTP desde la pantalla Cuenta debe ser posible.
  mfa_configuration = "OPTIONAL"
  software_token_mfa_configuration {
    enabled = true
  }

  password_policy {
    minimum_length    = 12
    require_uppercase = true
    require_lowercase = true
    require_numbers   = true
    require_symbols   = false
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # dev: el alta de ocupantes es administrada (enrolamiento por código en
  # T-2.03 crea la asignación de zona, no la cuenta). Self-signup: decisión futura.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Mismos custom attributes que el pool principal: claims.py trata ambos
  # issuers con el mismo parseo (custom:site_scope del occupant queda vacío —
  # el alcance móvil se resuelve server-side contra user_zone_assignments, R2).
  dynamic "schema" {
    for_each = local.custom_attributes

    content {
      name                     = schema.key
      attribute_data_type      = "String"
      mutable                  = true
      developer_only_attribute = false

      string_attribute_constraints {
        min_length = 0
        max_length = schema.value
      }
    }
  }
}

# Único grupo del pool de ocupantes: el ancla pool→rol de la API depende de esto.
resource "aws_cognito_user_group" "occupants_occupant" {
  name         = "occupant"
  user_pool_id = aws_cognito_user_pool.occupants.id
  description  = local.groups.occupant
}

resource "aws_cognito_user_pool_domain" "occupants" {
  domain       = "takab-dev-occupants-${var.account_id}"
  user_pool_id = aws_cognito_user_pool.occupants.id
}

# App client móvil del pool de ocupantes: PKCE por deep link de la app.
# Refresh de LARGA VIDA (spec móvil §8): la app debe poder alertar sin pedir
# login en plena crisis.
resource "aws_cognito_user_pool_client" "mobile_occupants" {
  name         = "takab-mobile-occupants"
  user_pool_id = aws_cognito_user_pool.occupants.id

  generate_secret = false

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = var.mobile_callback_urls
  logout_urls                          = var.mobile_logout_urls
  supported_identity_providers         = ["COGNITO"]

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 90

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"

  # Regla de oro #5: mismos anchors administrados que el client web (ver arriba).
  write_attributes = ["name"]
}

# App client móvil TÁCTICO sobre el pool principal (MFA ON intacto): mismos
# deep links; refresh corto — las acciones tácticas re-verifican token (spec §8).
resource "aws_cognito_user_pool_client" "mobile_tactical" {
  name         = "takab-mobile-tactical"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = var.mobile_callback_urls
  logout_urls                          = var.mobile_logout_urls
  supported_identity_providers         = ["COGNITO"]

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 24

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "hours"
  }

  prevent_user_existence_errors = "ENABLED"

  # Regla de oro #5 (ver client web).
  write_attributes = ["name"]
}
