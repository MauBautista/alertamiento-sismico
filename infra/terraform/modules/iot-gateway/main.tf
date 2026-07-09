terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

resource "aws_iot_thing" "this" {
  name            = var.thing_name
  thing_type_name = var.thing_type_name
}

resource "aws_iot_thing_group_membership" "this" {
  thing_name       = aws_iot_thing.this.name
  thing_group_name = var.thing_group_name
}

# Solo dev: AWS genera el par de claves y queda custodiado en Secrets Manager.
# En prod el dispositivo genera su clave y manda CSR.
resource "aws_iot_certificate" "this" {
  active = true
}

resource "aws_iot_policy_attachment" "fleet" {
  policy = var.fleet_policy_name
  target = aws_iot_certificate.this.arn
}

resource "aws_iot_thing_principal_attachment" "this" {
  thing     = aws_iot_thing.this.name
  principal = aws_iot_certificate.this.arn
}

resource "random_password" "hmac" {
  length  = 64
  special = false # solo alfanumerico, apto para env files
}

# Secreto del CERTIFICADO (cert mTLS + clave privada). Solo lo lee el humano
# que aprovisiona (provision_gateway.sh); la nube JAMAS recibe permiso sobre
# este prefijo — contiene claves privadas de dispositivo.
resource "aws_secretsmanager_secret" "this" {
  name                    = "takab/dev/gateway/${var.thing_name}"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "this" {
  secret_id = aws_secretsmanager_secret.this.id
  secret_string = jsonencode({
    thing_name  = var.thing_name
    cert_pem    = aws_iot_certificate.this.certificate_pem
    private_key = aws_iot_certificate.this.private_key
  })
}

# Secreto HMAC de comandos, SEPARADO del certificado (T-1.38): IAM no filtra
# campos JSON, asi que darle a la nube GetSecretValue del secreto combinado le
# regalaria la clave privada mTLS de toda la flota. Con el split, el wildcard
# del prefijo hmac concede EXACTAMENTE lo que la nube necesita. La MISMA
# random_password alimenta ambos flujos: el edge.env ya instalado sigue valido.
resource "aws_secretsmanager_secret" "hmac" {
  name                    = "${var.hmac_secret_prefix}/${var.thing_name}"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "hmac" {
  secret_id = aws_secretsmanager_secret.hmac.id
  secret_string = jsonencode({
    thing_name = var.thing_name
    hmac_key   = random_password.hmac.result
  })
}
