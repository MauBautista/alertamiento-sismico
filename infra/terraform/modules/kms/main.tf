terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

resource "aws_kms_key" "data" {
  description             = "TAKAB dev: datos (S3, EBS, Secrets Manager)"
  enable_key_rotation     = true
  deletion_window_in_days = 7
}

resource "aws_kms_alias" "data" {
  name          = "alias/${var.alias_prefix}-data"
  target_key_id = aws_kms_key.data.key_id
}

# Opcional: el bucket de estado ya usa SSE-S3 desde bootstrap; esta llave solo
# se crea si se decide migrarlo a SSE-KMS.
resource "aws_kms_key" "state" {
  count = var.create_state_key ? 1 : 0

  description             = "TAKAB dev: estado de Terraform"
  enable_key_rotation     = true
  deletion_window_in_days = 7
}

resource "aws_kms_alias" "state" {
  count = var.create_state_key ? 1 : 0

  name          = "alias/${var.alias_prefix}-state"
  target_key_id = aws_kms_key.state[0].key_id
}

# Reservado: KEKs por tenant (vacío en dev).
resource "aws_kms_key" "tenant" {
  for_each = var.tenant_keys

  description             = each.value
  enable_key_rotation     = true
  deletion_window_in_days = 7
}

resource "aws_kms_alias" "tenant" {
  for_each = var.tenant_keys

  name          = "alias/${var.alias_prefix}-tenant-${each.key}"
  target_key_id = aws_kms_key.tenant[each.key].key_id
}
