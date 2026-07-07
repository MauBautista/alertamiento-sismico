terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

data "aws_iot_endpoint" "data_ats" {
  endpoint_type = "iot:Data-ATS"
}

locals {
  iot_arn = "arn:aws:iot:${var.region}:${var.account_id}"
  # variable de politica de IoT ($$ en HCL -> literal para el broker)
  thing_name = "$${iot:Connection.Thing.ThingName}"
}

resource "aws_iot_thing_type" "gateway" {
  name = "takab-gateway"
}

resource "aws_iot_thing_group" "gateways" {
  name = "takab-dev-gateways"
}

# Politica de flota unica: cada gateway queda acotado a su ThingName via
# variables de politica (exige cert adjunto al thing para conectar).
resource "aws_iot_policy" "fleet" {
  name = "takab-dev-gateway-fleet"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "iot:Connect"
        Resource = "${local.iot_arn}:client/${local.thing_name}"
        Condition = {
          Bool = { "iot:Connection.Thing.IsAttached" = "true" }
        }
      },
      {
        Effect = "Allow"
        Action = "iot:Publish"
        Resource = [
          "${local.iot_arn}:topic/takab/events",
          "${local.iot_arn}:topic/takab/features",
          "${local.iot_arn}:topic/takab/health",
          "${local.iot_arn}:topic/takab/acks",
          "${local.iot_arn}:topic/takab/status/${local.thing_name}",
          "${local.iot_arn}:topic/takab/backfill/request/${local.thing_name}",
        ]
      },
      {
        Effect = "Allow"
        Action = "iot:Subscribe"
        Resource = [
          "${local.iot_arn}:topicfilter/takab/cmd/${local.thing_name}",
          "${local.iot_arn}:topicfilter/takab/cfg/${local.thing_name}",
          "${local.iot_arn}:topicfilter/takab/backfill/grant/${local.thing_name}",
        ]
      },
      {
        Effect = "Allow"
        Action = "iot:Receive"
        Resource = [
          "${local.iot_arn}:topic/takab/cmd/${local.thing_name}",
          "${local.iot_arn}:topic/takab/cfg/${local.thing_name}",
          "${local.iot_arn}:topic/takab/backfill/grant/${local.thing_name}",
        ]
      },
    ]
  })
}

# --- Reglas de enrutado hacia SQS ----------------------------------------------

resource "aws_cloudwatch_log_group" "rule_errors" {
  name              = "/takab/dev/iot-rule-errors"
  retention_in_days = 14
}

resource "aws_iam_role" "rules" {
  name = "takab-dev-iot-rules"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "iot.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "rules" {
  name = "takab-dev-iot-rules"
  role = aws_iam_role.rules.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sqs:SendMessage"
        Resource = [
          var.events_queue.arn,
          var.telemetry_queue.arn,
          var.backfill_queue.arn,
        ]
      },
      {
        Effect = "Allow"
        Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = [
          aws_cloudwatch_log_group.rule_errors.arn,
          "${aws_cloudwatch_log_group.rule_errors.arn}:*",
        ]
      },
    ]
  })
}

locals {
  # El SQL de IoT no admite multiples topics en FROM: una regla por topic.
  rules = {
    takab_dev_events    = { topic = "takab/events", queue_url = var.events_queue.url }
    takab_dev_acks      = { topic = "takab/acks", queue_url = var.events_queue.url }
    takab_dev_status    = { topic = "takab/status/+", queue_url = var.events_queue.url }
    takab_dev_telemetry = { topic = "takab/features", queue_url = var.telemetry_queue.url }
    takab_dev_health    = { topic = "takab/health", queue_url = var.telemetry_queue.url }
    # T-1.25: requests de backfill/evidencia -> grant service (worker backfill).
    takab_dev_backfill = { topic = "takab/backfill/request/+", queue_url = var.backfill_queue.url }
  }
}

resource "aws_iot_topic_rule" "this" {
  for_each = local.rules

  name    = each.key
  enabled = true
  # Prefijo meta_ (no _): el parser SQL de IoT rechaza aliases que empiecen con
  # guion bajo. La ingesta (T-1.17) descarta las claves meta_* antes de validar
  # el payload contra shared/schemas/.
  sql         = "SELECT *, clientid() AS meta_principal, topic() AS meta_topic, timestamp() AS meta_ts_iot FROM '${each.value.topic}'"
  sql_version = "2016-03-23"

  sqs {
    queue_url  = each.value.queue_url
    role_arn   = aws_iam_role.rules.arn
    use_base64 = false
  }

  error_action {
    cloudwatch_logs {
      log_group_name = aws_cloudwatch_log_group.rule_errors.name
      role_arn       = aws_iam_role.rules.arn
    }
  }

  # IoT valida los permisos del rol al crear la regla: evita la carrera con IAM.
  depends_on = [aws_iam_role_policy.rules]
}
