# Blinda la decision MAS SUTIL de este modulo: que significa el SILENCIO de cada metrica.
#
# Elegir mal `treat_missing_data` no rompe el plan ni el validate — produce una alarma que
# MIENTE, que es peor que no tener alarma. Paso en produccion: `gateway_offline` estaba en
# `notBreaching` y, tras disparar con el LWT, se auto-declaraba OK ~15 min despues y mandaba
# un correo de "todo bien" con el gabinete muerto (5 cortes seguidos: 24, 27 x2 y 28-jul-2026).
#
# La regla depende de COMO se publica la metrica, no del gusto de quien la escribe:
#   metrica POR EVENTO (solo escribe en transiciones)  -> "missing"      (retiene el estado)
#   metrica PERIODICA cuya ausencia ES la falla        -> "breaching"    (el silencio alarma)
#   metrica PERIODICA cuya ausencia es normal          -> "notBreaching" (sin trafico, sin alarma)
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
}

run "el_silencio_significa_lo_correcto_en_cada_alarma" {
  command = plan

  # POR EVENTO: `Takab/Fleet/<gw>` solo escribe 1 al conectar y 0 al perder el enlace (LWT).
  # Entre transiciones NO hay datapoints, asi que ni `breaching` (alarmaria siempre, tambien
  # con el gabinete sano) ni `notBreaching` (se auto-cura y miente) sirven: debe RETENER.
  assert {
    condition     = aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].treat_missing_data == "missing"
    error_message = "gateway_offline debe usar 'missing': su metrica es POR EVENTO, y cualquier otro valor hace que el silencio se lea como un estado que nadie reporto."
  }

  # PERIODICA (~1 muestra/min con el heartbeat) y su ausencia ya la cubre `gateway_offline`:
  # cuando cae el gabinete ENTERO no debe paginar dos veces. Cada alarma dice UNA cosa.
  assert {
    condition     = aws_cloudwatch_metric_alarm.sensor_mute["gw-test-0001"].treat_missing_data == "notBreaching"
    error_message = "sensor_mute debe seguir en 'notBreaching': sin enlace no hay dato del sismografo y quien pagina es gateway_offline."
  }

  # PERIODICA de AWS: una instancia apagada deja de emitir y eso SI es la falla.
  assert {
    condition     = aws_cloudwatch_metric_alarm.ec2_status.treat_missing_data == "breaching"
    error_message = "ec2_status debe seguir en 'breaching': la ausencia de metricas ES la caida de la instancia."
  }

  # El umbral y la ventana son parte del contrato: `Minimum < 1` sobre 1 periodo de 5 min
  # es lo que convierte el 0 del LWT en una pagina inmediata.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].comparison_operator == "LessThanThreshold"
      && aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].threshold == 1
      && aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].evaluation_periods == 1
    )
    error_message = "gateway_offline debe paginar con el PRIMER 0 del LWT (Minimum < 1, 1 periodo); subir evaluation_periods la volveria ciega a la unica muestra que emite."
  }
}

# `alarm_actions`/`ok_actions` NO se asientan aqui: el ARN del topic no se conoce hasta el
# apply y `command = plan` no puede evaluarlos. Se verifican en el runbook, contra AWS real.
