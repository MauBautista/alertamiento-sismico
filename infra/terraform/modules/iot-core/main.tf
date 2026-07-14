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
          # T-1.56: el lote de tier normal. Sin esta línea el broker DESCONECTA
          # al gabinete en cada publish del batch (política exacta, sin comodines)
          # — visto en producción el 2026-07-12: flapping cada 10 s.
          "${local.iot_arn}:topic/takab/features/batch",
          "${local.iot_arn}:topic/takab/health",
          "${local.iot_arn}:topic/takab/acks",
          "${local.iot_arn}:topic/takab/status/${local.thing_name}",
          "${local.iot_arn}:topic/takab/backfill/request/${local.thing_name}",
        ]
      },
      {
        # La presencia del gateway es RETENIDA (LWT offline + online al conectar,
        # T-1.17): un CONNECT con will retenido exige iot:RetainPublish o el broker
        # lo corta (AWS_ERROR_MQTT_UNEXPECTED_HANGUP — visto en el Pi 5 real).
        Effect   = "Allow"
        Action   = "iot:RetainPublish"
        Resource = "${local.iot_arn}:topic/takab/status/${local.thing_name}"
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
      {
        # A-4: la regla de presencia publica la metrica de flota. PutMetricData
        # no admite recurso especifico; se acota por namespace.
        # T-1.66: + Takab/Sensor (lag de SeedLink → alarma de sensor MUDO).
        Effect   = "Allow"
        Action   = "cloudwatch:PutMetricData"
        Resource = "*"
        Condition = {
          StringEquals = { "cloudwatch:namespace" = ["Takab/Fleet", "Takab/Sensor"] }
        }
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
    # T-1.56: lote de features de tier normal. El filtro exacto de takab/features
    # NO matchea el sub-topic (sin comodines): regla propia, MISMA cola.
    takab_dev_features_batch = { topic = "takab/features/batch", queue_url = var.telemetry_queue.url }
    takab_dev_health         = { topic = "takab/health", queue_url = var.telemetry_queue.url }
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

# --- Presencia -> metrica CloudWatch (A-4: gabinete SIN ENLACE pagina) -----------
# El LWT retenido en takab/status/<thing> ya viaja a SQS (regla takab_dev_status);
# estas DOS reglas ademas lo convierten en datapoints de la metrica Takab/Fleet
# (metric_name = nombre del thing) para alarmar desconexiones sin instrumentar la
# aplicacion. Dos reglas con WHERE y valor LITERAL (nada de CASE en templates):
# lo aburrido es lo que no se rompe.
locals {
  status_metric_rules = {
    takab_dev_status_metric_offline = { status = "offline", value = "0" }
    takab_dev_status_metric_online  = { status = "online", value = "1" }
  }
}

# --- Sensor MUDO -> metrica CloudWatch (T-1.66) ----------------------------------
# El caso que se nos escapo el 14/07/2026: el Raspberry Shake estuvo 15 h fuera de
# la red, el Pi siguio latiendo y la flota se veia OPERATIVA. La alarma de presencia
# NO lo cubre (el gabinete SI tenia enlace) y nadie se entero de que el sistema
# estaba ciego. El heartbeat ya trae `seedlink_lag_s` = antiguedad del dato mas
# reciente (T-1.65: crece sin limite si el stream muere), asi que se convierte en
# metrica sin instrumentar la aplicacion — mismo truco que la presencia.
# metric_name = clientid() = nombre del thing (el gateway conecta con su ThingName).
resource "aws_iot_topic_rule" "seedlink_lag_metric" {
  name        = "takab_dev_seedlink_lag_metric"
  enabled     = true
  sql         = "SELECT * FROM 'takab/health'"
  sql_version = "2016-03-23"

  cloudwatch_metric {
    metric_name      = "$${clientid()}"
    metric_namespace = "Takab/Sensor"
    metric_unit      = "Seconds"
    metric_value     = "$${seedlink_lag_s}"
    role_arn         = aws_iam_role.rules.arn
  }

  error_action {
    cloudwatch_logs {
      log_group_name = aws_cloudwatch_log_group.rule_errors.name
      role_arn       = aws_iam_role.rules.arn
    }
  }

  depends_on = [aws_iam_role_policy.rules]
}

resource "aws_iot_topic_rule" "gateway_status_metric" {
  for_each = local.status_metric_rules

  name        = each.key
  enabled     = true
  sql         = "SELECT status FROM 'takab/status/+' WHERE status = '${each.value.status}'"
  sql_version = "2016-03-23"

  cloudwatch_metric {
    metric_name      = "$${topic(3)}"
    metric_namespace = "Takab/Fleet"
    metric_unit      = "None"
    metric_value     = each.value.value
    role_arn         = aws_iam_role.rules.arn
  }

  error_action {
    cloudwatch_logs {
      log_group_name = aws_cloudwatch_log_group.rule_errors.name
      role_arn       = aws_iam_role.rules.arn
    }
  }

  depends_on = [aws_iam_role_policy.rules]
}
