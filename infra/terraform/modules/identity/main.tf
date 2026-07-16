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
