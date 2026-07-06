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
  callback_urls                        = ["http://localhost:5173/auth/callback"]
  logout_urls                          = ["http://localhost:5173/"]
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
}

# Identidades verificadas: SES en sandbox solo entrega a destinos verificados.
resource "aws_sesv2_email_identity" "this" {
  for_each = toset(var.ses_verified_emails)

  email_identity = each.value
}
