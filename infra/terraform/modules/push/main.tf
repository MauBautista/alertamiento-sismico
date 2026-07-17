terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# =============================================================================
# PUSH MÓVIL (T-2.04 · decisión T-2.00: SNS platform endpoints)
# CONDICIONAL a credenciales reales: sin la llave APNs (.p8 de Apple Developer,
# GATE-STORE) o el service account de FCM, el recurso NO se crea y la API opera
# con el provider simulado (que grita, patrón T-1.62). Los tokens de dispositivo
# se mapean a endpoints por la API (push_tokens.endpoint_arn).
# =============================================================================

locals {
  apns_enabled = var.apns_signing_key != ""
  fcm_enabled  = var.fcm_service_account_json != ""
}

# iOS — autenticación por TOKEN (llave .p8 + key id + team id + bundle id).
resource "aws_sns_platform_application" "apns" {
  count = local.apns_enabled ? 1 : 0

  name                     = "takab-${var.env}-apns"
  platform                 = var.apns_sandbox ? "APNS_SANDBOX" : "APNS"
  platform_credential      = var.apns_signing_key
  platform_principal       = var.apns_signing_key_id
  apple_platform_team_id   = var.apns_team_id
  apple_platform_bundle_id = var.apns_bundle_id
}

# Android — FCM v1 (service account JSON del proyecto Firebase).
resource "aws_sns_platform_application" "fcm" {
  count = local.fcm_enabled ? 1 : 0

  name                = "takab-${var.env}-fcm"
  platform            = "GCM"
  platform_credential = var.fcm_service_account_json
}

# Permisos del rol donde corre la API/worker de notify: crear endpoints por
# dispositivo y publicar. Acotado a las platform applications de este entorno
# (los endpoints heredan el prefijo del app ARN).
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  push_enabled = local.apns_enabled || local.fcm_enabled
  app_arns = concat(
    aws_sns_platform_application.apns[*].arn,
    aws_sns_platform_application.fcm[*].arn,
  )
  endpoint_arns = [
    "arn:aws:sns:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:endpoint/*/takab-${var.env}-*/*",
  ]
}

resource "aws_iam_role_policy" "push" {
  count = local.push_enabled && var.worker_role_name != "" ? 1 : 0

  name = "takab-${var.env}-push"
  role = var.worker_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "PushEndpoints"
        Effect = "Allow"
        Action = [
          "sns:CreatePlatformEndpoint",
          "sns:GetEndpointAttributes",
          "sns:SetEndpointAttributes",
          "sns:DeleteEndpoint",
        ]
        Resource = concat(local.app_arns, local.endpoint_arns)
      },
      {
        Sid      = "PushPublish"
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = local.endpoint_arns
      },
    ]
  })
}
