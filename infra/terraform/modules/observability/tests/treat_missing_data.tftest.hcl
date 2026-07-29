# Blinda la decision MAS SUTIL de este modulo: que significa el SILENCIO de cada metrica.
#
# Elegir mal `treat_missing_data` no rompe el plan ni el validate — produce una alarma que
# MIENTE, que es peor que no tener alarma. Paso en produccion: `gateway_offline` estaba en
# `notBreaching` y, tras disparar con el LWT, se auto-declaraba OK ~15 min despues y mandaba
# un correo de "todo bien" con el gabinete muerto (5 cortes seguidos: 24, 27 x2 y 28-jul-2026).
#
# La regla depende de COMO se publica la metrica, no del gusto de quien la escribe. Segun la
# tabla oficial de AWS para "todos los datapoints ausentes":
#   metrica POR EVENTO (solo escribe en transiciones)  -> "ignore"       (RETIENE el estado)
#   metrica PERIODICA cuya ausencia ES la falla        -> "breaching"    (el silencio alarma)
#   metrica PERIODICA cuya ausencia es normal          -> "notBreaching" (sin trafico, sin alarma)
#
# OJO con `missing`: suena a "retiene" y NO lo hace — lleva a INSUFFICIENT_DATA. Se probo en
# vivo el 29-jul-2026 (se forzo ALARM con set-alarm-state y CloudWatch la devolvio a
# INSUFFICIENT_DATA en ~1 min). El que mantiene el estado es `ignore`, literal de la doc:
# "ignore - The current alarm state is maintained".
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
  # con el gabinete sano), ni `notBreaching` (se auto-cura y miente), ni `missing`
  # (INSUFFICIENT_DATA, verificado en vivo) sirven: debe RETENER, y eso es `ignore`.
  assert {
    condition     = aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].treat_missing_data == "ignore"
    error_message = "gateway_offline debe usar 'ignore', el UNICO que mantiene el estado: su metrica es POR EVENTO. 'missing' NO retiene (lleva a INSUFFICIENT_DATA) por mas que el nombre lo sugiera."
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

# Que la alarma AVISE en los TRES estados, no solo en dos.
#
# `gateway_offline` quedo en INSUFFICIENT_DATA tras el apply del 29-jul-2026 (al cambiar la
# config, CloudWatch reevalua sin estado previo que retener) y ahi se quedo MUDA: el gabinete
# llevaba 17 h caido y `insufficient_data_actions` estaba vacio. Se paso de una alarma que
# MENTIA a una que CALLA — mejor, pero igual de inutil para enterarse.
#
# Para un sistema donde fallar cuesta vidas, "no se nada de este gabinete" es tan accionable
# como "esta caido". Y no genera ruido: con `missing`, un gabinete sano retiene OK, asi que
# INSUFFICIENT_DATA solo aparece cuando de verdad no hay historia que retener.
#
# El ARN del topic no se conoce en plan (recurso nuevo), asi que se fija con `override_resource`
# — sin eso, estas aserciones son inevaluables y las acciones quedan sin blindar.
run "gateway_offline_avisa_en_los_tres_estados" {
  command = plan

  override_resource {
    target          = aws_sns_topic.ops_alerts
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ops-alerts"
    }
  }

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].alarm_actions) == 1
    error_message = "gateway_offline sin alarm_actions: cambiaria de estado sin avisar a nadie."
  }

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].ok_actions) == 1
    error_message = "gateway_offline sin ok_actions: nadie sabria que el gabinete volvio."
  }

  assert {
    condition     = try(length(aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].insufficient_data_actions), 0) == 1
    error_message = "gateway_offline sin insufficient_data_actions: la alarma puede quedarse en INSUFFICIENT_DATA con el gabinete muerto y no avisar a nadie (paso el 29-jul-2026)."
  }

  # `sensor_mute` NO debe avisar en INSUFFICIENT_DATA a proposito: sin enlace no hay dato del
  # sismografo y quien pagina es `gateway_offline`. Dos correos por el mismo corte es ruido,
  # y el ruido es como se dejan de leer las alarmas.
  assert {
    condition     = try(length(aws_cloudwatch_metric_alarm.sensor_mute["gw-test-0001"].insufficient_data_actions), 0) == 0
    error_message = "sensor_mute NO debe avisar en INSUFFICIENT_DATA: duplicaria la pagina de gateway_offline en cada corte."
  }
}
