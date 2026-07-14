# Observabilidad hacia HUMANOS (hallazgo A-4 de la auditoria de cierre).
#
# Antes de este modulo NO existia ni una alarma ni un topic SNS: un gabinete
# caido, una DLQ creciendo o la nube muerta eran solo un color en la UI. Aqui
# vive el minimo honesto: un topic de on-call por email + alarmas de los
# sintomas que la infra ya emite sin instrumentar la aplicacion.
#
# Fuera de alcance (documentado en el runbook de auditoria): bateria por
# gabinete y 5xx de la API requieren publicar metricas desde la aplicacion
# (device_health/Caddy) — siguiente rebanada de A-4.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

resource "aws_sns_topic" "ops_alerts" {
  name = "takab-dev-ops-alerts"
}

# La suscripcion por email exige CONFIRMACION manual (AWS manda un correo con
# un link): el apply no termina el trabajo hasta que el humano confirma.
resource "aws_sns_topic_subscription" "ops_email" {
  topic_arn = aws_sns_topic.ops_alerts.arn
  protocol  = "email"
  endpoint  = var.ops_alert_email
}

# --- DLQ con mensajes = pipeline envenenado o roto (E3/O1) -----------------------
# La ingesta rechaza a DLQ con razon tipificada; que la DLQ tenga UN mensaje ya
# es accionable. missing=notBreaching: sin trafico no hay datapoint y no es alarma.
resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  for_each = var.dlq_names

  alarm_name          = "takab-dev-dlq-${each.key}"
  alarm_description   = "DLQ '${each.value}' con mensajes: la ingesta esta rechazando payloads (ver MessageAttributes.reason) o un consumer agoto reintentos."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = each.value }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  ok_actions          = [aws_sns_topic.ops_alerts.arn]
}

# --- La instancia EC2 (DB + nube co-locada) ---------------------------------------
# missing=breaching A PROPOSITO: una instancia parada deja de emitir metricas y
# eso DEBE avisar (incluso `make cloud-stop` deliberado: la nube caida es un
# evento operativo; SNS notifica solo la transicion, un correo por parada).
resource "aws_cloudwatch_metric_alarm" "ec2_status" {
  alarm_name          = "takab-dev-ec2-status-check"
  alarm_description   = "La instancia de la nube co-locada falla sus status checks o dejo de reportar (¿parada?): API, workers y DB viven ahi."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  dimensions          = { InstanceId = var.instance_id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  ok_actions          = [aws_sns_topic.ops_alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "ec2_cpu" {
  alarm_name          = "takab-dev-ec2-cpu-sostenida"
  alarm_description   = "CPU > 90% sostenida 15 min en la instancia co-locada: riesgo de lag de ingesta y OOM (leccion t4g.small)."
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  dimensions          = { InstanceId = var.instance_id }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 90
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  ok_actions          = [aws_sns_topic.ops_alerts.arn]
}

# --- Errores de las reglas IoT (ingesta rota antes de SQS) ------------------------
# Todo evento en ese log group ES un error de regla (es el error_action):
# patron vacio = contar cada linea.
resource "aws_cloudwatch_log_metric_filter" "iot_rule_errors" {
  name           = "takab-dev-iot-rule-errors"
  log_group_name = var.iot_rule_errors_log_group
  pattern        = ""

  metric_transformation {
    name      = "IoTRuleErrors"
    namespace = "Takab/Ops"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "iot_rule_errors" {
  alarm_name          = "takab-dev-iot-rule-errors"
  alarm_description   = "Las reglas IoT estan tirando errores al enrutar hacia SQS: mensajes del edge se estan perdiendo antes de la ingesta."
  namespace           = "Takab/Ops"
  metric_name         = "IoTRuleErrors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  ok_actions          = [aws_sns_topic.ops_alerts.arn]

  depends_on = [aws_cloudwatch_log_metric_filter.iot_rule_errors]
}

# --- Gabinete SIN ENLACE (LWT retenido -> metrica Takab/Fleet, ver iot-core) ------
# El LWT publica {"status":"offline"} al caer la conexion y "online" al volver;
# la regla takab_dev_status_metric_* lo convierte en un datapoint 0/1 con el
# nombre del thing. Son eventos ESPORADICOS (no un heartbeat de metrica):
# missing=notBreaching ⇒ la alarma pagina en la transicion a offline y vuelve a
# OK sola; el estado sostenido vive en la UI de flota (derive_fleet_state).
# Solo los gateways REALES paginan: los gw-sim-* viven apagados por diseno.
# --- Sensor MUDO: gabinete VIVO pero sin datos del sismografo (T-1.66) ------------
# El agujero que costo 15 h de ceguera el 14/07/2026: el Shake fuera de la red, el Pi
# latiendo cada minuto y la flota "OPERATIVA". `gateway_offline` no lo ve (hay enlace)
# y la UI solo lo mostraba a quien mirase la pantalla. Un sismografo mudo es la
# perdida TOTAL de la deteccion local: es exactamente lo que tiene que despertar a
# alguien de madrugada.
#
# `seedlink_lag_s` es la ANTIGUEDAD del dato mas reciente (T-1.65). Un stream sano no
# pasa de ~8 s (duracion del registro miniSEED a 100 sps), asi que 120 s es inequivoco
# y deja fuera cualquier hipo de reconexion. missing=notBreaching: si cae el gabinete
# ENTERO, quien pagina es `gateway_offline` — cada alarma dice UNA cosa.
resource "aws_cloudwatch_metric_alarm" "sensor_mute" {
  for_each = toset(var.paged_gateways)

  alarm_name          = "takab-dev-sensor-mudo-${each.value}"
  alarm_description   = "El gabinete ${each.value} TIENE ENLACE pero su sismografo lleva >120 s sin entregar muestras: SIN DETECCION LOCAL, el sitio esta ciego. Revisar el Raspberry Shake (alimentacion, cable de red, puerto del switch): el Pi 5 reconecta solo en cuanto vuelva a la LAN."
  namespace           = "Takab/Sensor"
  metric_name         = each.value
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 120
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  ok_actions          = [aws_sns_topic.ops_alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "gateway_offline" {
  for_each = toset(var.paged_gateways)

  alarm_name          = "takab-dev-gateway-offline-${each.value}"
  alarm_description   = "El gabinete ${each.value} publico su LWT (SIN ENLACE): perdio conexion con IoT Core. La proteccion local sigue (regla de oro 2), pero hay que ir a verlo."
  namespace           = "Takab/Fleet"
  metric_name         = each.value
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  ok_actions          = [aws_sns_topic.ops_alerts.arn]
}
