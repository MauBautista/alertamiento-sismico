terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

locals {
  buckets = {
    evidence   = "takab-dev-evidence-${var.account_id}"
    transfer   = "takab-dev-transfer-${var.account_id}"
    db_backups = "takab-dev-db-backups-${var.account_id}"
  }
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets

  bucket        = each.value
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = local.buckets

  bucket                  = aws_s3_bucket.this[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "tls_only" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.this[each.key].arn,
        "${aws_s3_bucket.this[each.key].arn}/*",
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.this]
}

# evidence: la inmutabilidad (Object Lock) es requisito de prod; en dev basta
# versioning + SSE-KMS.

# transfer: staging temporal edge->nube; todo el bucket expira a 30 dias.
resource "aws_s3_bucket_lifecycle_configuration" "transfer" {
  bucket = aws_s3_bucket.this["transfer"].id

  rule {
    id     = "expira-30d"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = 30
    }
  }
}

# La policy que permite a S3 publicar en la cola vive en modules/messaging
# (condicion por cuenta) para evitar un ciclo storage<->messaging.
resource "aws_s3_bucket_notification" "transfer" {
  bucket = aws_s3_bucket.this["transfer"].id

  queue {
    queue_arn     = var.backfill_queue_arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "backfill/"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "db_backups" {
  bucket = aws_s3_bucket.this["db_backups"].id

  rule {
    id     = "expira-60d"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = 60
    }
  }
}
