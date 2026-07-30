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

  # PRESENCIA = ausencia de heartbeat. `gateway_offline` NO puede vivir sobre `Takab/Fleet`
  # (metrica POR EVENTO: solo LWT online/offline): un desconectar+reconectar dentro de la
  # misma ventana es AMBIGUO por construccion y ninguna combinacion de statistic y
  # treat_missing_data lo resuelve. Se probaron las cuatro en produccion, en este orden:
  #
  #   notBreaching -> mintio "todo bien" en los 5 cortes de julio-2026.
  #   missing      -> INSUFFICIENT_DATA y MUDA (no retiene, pese al nombre).
  #   ignore       -> retiene... y el 30-jul se quedo TRABADA en ALARMA 4 h con el gabinete
  #                   sano: el 0 del LWT y el 1 de la reconexion cayeron en el MISMO minuto,
  #                   `Minimum` se quedo con el 0 y sin datapoints nuevos nunca se solto.
  #   breaching    -> alarmaria siempre (un gabinete sano tampoco emite entre transiciones).
  #
  # La metrica correcta ya existia: `Takab/Sensor/<gw>` se publica en CADA heartbeat (1/min,
  # regla `takab_dev_seedlink_lag_metric`). Su PRESENCIA es la senal de vida, con independencia
  # de su VALOR — que es lo que vigila `sensor_mute`. Dos alarmas sobre la misma metrica,
  # cada una mirando una cosa distinta.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].namespace == "Takab/Sensor"
      && aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].statistic == "SampleCount"
    )
    error_message = "gateway_offline debe vigilar la PRESENCIA del heartbeat (SampleCount de Takab/Sensor), no la metrica de eventos Takab/Fleet: un desconectar+reconectar en la misma ventana la traba (paso el 30-jul-2026)."
  }

  # Metrica PERIODICA cuya ausencia ES la falla ⇒ el silencio alarma. Y como la alarma
  # vuelve a OK sola en cuanto reaparecen muestras, no puede quedarse trabada.
  assert {
    condition     = aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].treat_missing_data == "breaching"
    error_message = "gateway_offline debe usar 'breaching': sobre una metrica PERIODICA la ausencia de datapoints ES la caida del gabinete."
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

  # La ventana es parte del contrato: `SampleCount < 1` durante 2 periodos de 5 min = 10 min
  # sin UN solo heartbeat, cuando llegan 1/min. Diez ausencias seguidas no son un hipo de red.
  # Se sacrifica deteccion rapida (el LWT avisaba en ~1 min) a cambio de que la alarma NO
  # pueda mentir ni trabarse. Es aceptable porque esto no esta en el camino de actuacion:
  # SASMEX->sirena es local y determinista (reglas de oro 1 y 2), esta alarma solo sirve
  # para que un humano vaya a ver el gabinete.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].comparison_operator == "LessThanThreshold"
      && aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].threshold == 1
      && aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].evaluation_periods == 2
      && aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].period == 300
    )
    error_message = "gateway_offline debe alarmar tras 2 periodos de 5 min sin ningun heartbeat (SampleCount < 1)."
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
