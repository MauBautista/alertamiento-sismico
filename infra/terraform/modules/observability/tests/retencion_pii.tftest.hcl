# [T-2.81.a] La alarma de la retencion de PII que dejo de ejecutarse.
#
# Es la clase de fallo mas silenciosa de todo el sistema: una retencion parada no
# tumba nada, no llena ningun disco, no produce un solo error 500 y no encola un
# mensaje. Simplemente los datos personales que tenian que caducar dejan de
# caducar. Sin esta alarma, eso se descubre el dia que alguien pregunta — que es
# tarde por definicion.
#
# Lo que se blinda aqui es lo que, si se rompe, deja una alarma con cara de
# funcionar: el par namespace+metrica (el otro extremo del cable esta en el
# script de `modules/database`, y terraform no puede leer bash), los tres estados
# y el hecho de que el umbral NO se teclea en este modulo.
#
# Corre con: terraform -chdir=infra/terraform/modules/observability test

provider "aws" {
  region                      = "us-east-2"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

variables {
  ops_alert_email           = "oncall@example.test"
  dlq_names                 = { telemetry = "takab-test-dlq-telemetry" }
  instance_id               = "i-0000000000test000"
  iot_rule_errors_log_group = "/aws/iot/takab-test"
  paged_gateways            = ["gw-test-0001"]
  wal_archive_max_age_s     = 600
  base_backup_max_age_s     = 1209600
  # [T-2.141] La hermana temprana; aqui solo hace falta que exista (sin default).
  base_backup_warn_age_s  = 604800
  pii_retention_max_age_s = 172800
}

run "la_alarma_vigila_la_metrica_que_la_instancia_publica_de_verdad" {
  command = plan

  override_resource {
    target          = aws_sns_topic.ops_alerts
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ops-alerts"
    }
  }

  # El par namespace+metrica es un contrato con un script de OTRO modulo
  # (`modules/database/prune_pii_setup.sh.tpl` publica `PiiRetentionAgeSeconds`
  # en `Takab/Ops`). Terraform no puede leer bash desde aqui, asi que lo que se
  # blinda es este extremo del cable: si divergen, la alarma vigila una metrica
  # que nadie escribe y se queda en INSUFFICIENT_DATA para siempre sin que nada
  # parezca roto.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.pii_retention_stalled.namespace == "Takab/Ops"
      && aws_cloudwatch_metric_alarm.pii_retention_stalled.metric_name == "PiiRetentionAgeSeconds"
    )
    error_message = "la alarma debe vigilar Takab/Ops/PiiRetentionAgeSeconds, exactamente lo que publica el cron de modules/database: si divergen, vigila una metrica que nadie escribe."
  }

  # El umbral NO se teclea aqui: baja de `modules/database`, que es donde vive la
  # cadencia del cron y el margen. Un literal en este modulo se desincronizaria
  # el dia que la cadencia cambiara, y la alarma pasaria a vigilar una
  # periodicidad que no ocurre.
  assert {
    condition     = aws_cloudwatch_metric_alarm.pii_retention_stalled.threshold == 172800
    error_message = "el umbral debe venir de fuera (modules/database: cadencia x margen), no de un literal en este modulo."
  }

  # Los TRES estados al topic de on-call. El OK importa tanto como el ALARM: esta
  # alarma NACE en ALARM el dia del apply (todavia no consta ninguna corrida), asi
  # que el correo de OK tras la primera corrida es el UNICO acuse automatico de
  # que la retencion llego a ejecutarse alguna vez.
  assert {
    condition = (
      contains(aws_cloudwatch_metric_alarm.pii_retention_stalled.alarm_actions, aws_sns_topic.ops_alerts.arn)
      && contains(aws_cloudwatch_metric_alarm.pii_retention_stalled.ok_actions, aws_sns_topic.ops_alerts.arn)
      && contains(aws_cloudwatch_metric_alarm.pii_retention_stalled.insufficient_data_actions, aws_sns_topic.ops_alerts.arn)
    )
    error_message = "la alarma debe mandar sus TRES estados al topic de on-call: sin ok_actions se pierde el unico acuse de que la retencion se ejecuto alguna vez."
  }

  # `Maximum` sobre una metrica que es una EDAD: dentro del periodo, el peor
  # minuto manda. `Average` suavizaria justo el momento en que la edad cruza el
  # umbral, y `Minimum` fue lo que trabo `gateway_offline` el 30-jul-2026.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.pii_retention_stalled.statistic == "Maximum"
      && aws_cloudwatch_metric_alarm.pii_retention_stalled.comparison_operator == "GreaterThanThreshold"
    )
    error_message = "la alarma debe comparar el Maximum de la edad contra el umbral: promediar una edad esconde el minuto en que cruza."
  }
}

run "un_umbral_por_debajo_de_la_cadencia_diaria_no_se_puede_aplicar" {
  command = plan

  variables {
    pii_retention_max_age_s = 86400
  }

  # Con el umbral igual (o menor) que la cadencia, la alarma dispara en operacion
  # NORMAL: entre corrida y corrida la edad llega a 24 h siempre. Una alarma que
  # suena todos los dias es una alarma que alguien acaba silenciando — y esta
  # esta clasificada como intocable justamente para que eso no pueda pasar.
  expect_failures = [var.pii_retention_max_age_s]
}
