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
  queues = {
    events    = { visibility_timeout = 30 }
    telemetry = { visibility_timeout = 90 }
    backfill  = { visibility_timeout = 300 }
  }
}

resource "aws_sqs_queue" "dlq" {
  for_each = local.queues

  name                      = "takab-dev-q-${each.key}-dlq"
  message_retention_seconds = 1209600 # 14 dias
  receive_wait_time_seconds = 20
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "this" {
  for_each = local.queues

  name                       = "takab-dev-q-${each.key}"
  visibility_timeout_seconds = each.value.visibility_timeout
  message_retention_seconds  = 345600 # 4 dias
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = 5
  })
}

# S3 (bucket transfer) publica ObjectCreated aqui. Se acota por cuenta y no por
# ARN de bucket para evitar el ciclo storage<->messaging.
resource "aws_sqs_queue_policy" "backfill_from_s3" {
  queue_url = aws_sqs_queue.this["backfill"].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowS3SendMessage"
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.this["backfill"].arn
      Condition = {
        StringEquals = { "aws:SourceAccount" = var.account_id }
      }
    }]
  })
}
