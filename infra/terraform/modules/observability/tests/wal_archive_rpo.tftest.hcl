# [T-2.72] El RPO no es una promesa de la configuracion: es una CONSECUENCIA de
# esta alarma, y aqui se blinda esa consecuencia.
#
# La derivacion tentadora es "archive_timeout = 60 s ⇒ RPO = 1 min". Es falsa. El
# `archive_timeout` describe el caso FELIZ: cada cuanto Postgres cierra un
# segmento y lo manda a archivar. No dice nada de cuanto tiempo puede estar el
# archivado ROTO sin que nadie se entere — y ese es el numero que de verdad se
# pierde en un desastre.
#
# El RPO real de un sistema es la EDAD MAXIMA DEL ARCHIVADO A LA QUE ALGUIEN SE
# ENTERA. Aqui "enterarse" es exactamente un correo de SNS, y ese correo no sale
# cuando la edad cruza el umbral: sale cuando CloudWatch ha visto
# `evaluation_periods` periodos SEGUIDOS por encima. Los dos terminos cuentan:
#
#     RPO = umbral_de_la_alarma + period * evaluation_periods
#
# Declarar `RPO = umbral` seria la misma clase de mentira que declarar
# `RPO = archive_timeout`, un escalon mas arriba: tomar el caso feliz de la
# DETECCION por el peor caso de la detección.
#
# Y toda la derivacion es MENTIRA si la alarma no esta en `treat_missing_data =
# "breaching"`. Si el publicador muere, la metrica desaparece; con
# `missing`/`notBreaching` la alarma se calla para siempre y el RPO pasa a ser
# ILIMITADO — que es justo el estado en el que esta el sistema hoy, antes de esta
# tarea. Por eso esa asercion vive PEGADA a la del RPO: separadas, alguien relaja
# una y la otra sigue certificando un numero que ya no significa nada.
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

  # SENTINELA, no el valor de produccion (600). Un numero que nadie escribiria a
  # mano: si el umbral de la alarma o el RPO estan cableados con una constante en
  # vez de derivados de esta variable, las aserciones de abajo se ponen rojas.
  # Con el valor real las dos cosas coincidirian por casualidad y el test seria
  # verde vacio.
  wal_archive_max_age_s = 777
}

run "el_rpo_sale_de_la_alarma_y_no_de_una_promesa" {
  command = plan

  override_resource {
    target          = aws_sns_topic.ops_alerts
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ops-alerts"
    }
  }

  # Contrato con el publicador. Terraform no puede leer el script que publica la
  # metrica (vive en el documento SSM de `modules/database`), asi que lo que se
  # blinda aqui es el otro extremo del cable — el mismo patron que
  # `ghost_gateways` con `ops/metrics.py`. Si divergen, la alarma vigila una
  # metrica que nadie escribe y, con `breaching`, grita para siempre.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.wal_archive_stalled.namespace == "Takab/Ops"
      && aws_cloudwatch_metric_alarm.wal_archive_stalled.metric_name == "WalArchiveAgeSeconds"
    )
    error_message = "wal_archive_stalled debe vigilar Takab/Ops/WalArchiveAgeSeconds, exactamente lo que publica el documento SSM de modules/database: si divergen, la alarma vigila una metrica que nadie escribe."
  }

  # El umbral ES la edad maxima tolerada, no un numero parecido.
  assert {
    condition     = aws_cloudwatch_metric_alarm.wal_archive_stalled.threshold == var.wal_archive_max_age_s
    error_message = "El umbral de la alarma debe SER var.wal_archive_max_age_s. Cableado a una constante, el RPO publicado deja de describir a esta alarma y vuelve a ser una promesa."
  }

  # La FORMA de la derivacion, comprobada contra los atributos del PROPIO
  # recurso: si alguien le quita el termino de deteccion, o cambia la operacion,
  # esto se cae.
  #
  # OJO: esta asercion SOLA no basta y esta medido. Sustituir el output por el
  # literal `1077` la deja EN VERDE, porque 777 + 60*5 son exactamente 1077 — un
  # literal que hoy coincide pasa por derivacion. Lo que distingue una derivacion
  # de una coincidencia no es mirarla mas fijo con el mismo dato: es cambiar el
  # dato. Esa mitad vive en el segundo bloque, y las dos van juntas.
  assert {
    condition = output.rpo_seconds == (
      aws_cloudwatch_metric_alarm.wal_archive_stalled.threshold
      + aws_cloudwatch_metric_alarm.wal_archive_stalled.period
      * aws_cloudwatch_metric_alarm.wal_archive_stalled.evaluation_periods
    )
    error_message = "rpo_seconds debe DERIVARSE de la alarma (umbral + period*evaluation_periods)."
  }

  # Y que el termino de deteccion no sea cero. `RPO = umbral` significaria creer
  # que CloudWatch avisa en el instante en que se cruza el umbral, y no lo hace:
  # necesita N periodos seguidos.
  assert {
    condition     = output.rpo_seconds > var.wal_archive_max_age_s
    error_message = "rpo_seconds no puede ser igual al umbral: entre cruzar el umbral y el correo hay period*evaluation_periods segundos en los que se sigue perdiendo WAL."
  }

  # La mitad sin la que todo lo anterior es decorado (ver cabecera).
  assert {
    condition     = aws_cloudwatch_metric_alarm.wal_archive_stalled.treat_missing_data == "breaching"
    error_message = "wal_archive_stalled debe ser 'breaching'. La metrica es PERIODICA (un valor por minuto, siempre) y su ausencia no es ambigua: o la DB no responde, o el publicador esta muerto, o la instancia esta caida — en los tres casos la edad del ultimo WAL archivado es DESCONOCIDA y el RPO deja de estar acotado. Con 'missing' o 'notBreaching' el RPO derivado seria falso."
  }

  # `Maximum` sobre el periodo: el peor minuto manda. Con `Average` un atasco de
  # 4 minutos dentro de un periodo de 5 se diluiria por debajo del umbral, y el
  # numero del correo dejaria de leerse como "segundos de datos en riesgo".
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.wal_archive_stalled.statistic == "Maximum"
      && aws_cloudwatch_metric_alarm.wal_archive_stalled.comparison_operator == "GreaterThanThreshold"
    )
    error_message = "wal_archive_stalled debe alarmar con Maximum > umbral: el peor minuto del periodo es el que mide cuanto se pierde."
  }

  # N de N, sin `datapoints_to_alarm`. Con M de N el numero de la derivacion
  # dejaria de ser el peor caso: podrian pasar mas de N periodos por encima del
  # umbral antes de juntar los M, y el RPO publicado se quedaria corto.
  assert {
    condition     = aws_cloudwatch_metric_alarm.wal_archive_stalled.datapoints_to_alarm == null
    error_message = "wal_archive_stalled no debe usar datapoints_to_alarm: con M de N, el peor caso de deteccion deja de ser period*evaluation_periods y el RPO derivado se queda corto."
  }

  # Los TRES estados al topic de on-call. El OK importa tanto como el ALARM: es
  # la unica senal de que el archivado se recupero, y —como en `ghost_gateways`—
  # el correo de OK tras el primer apply es lo unico que dice que la metrica
  # llego a publicarse alguna vez.
  assert {
    condition = (
      contains(aws_cloudwatch_metric_alarm.wal_archive_stalled.alarm_actions, aws_sns_topic.ops_alerts.arn)
      && contains(aws_cloudwatch_metric_alarm.wal_archive_stalled.ok_actions, aws_sns_topic.ops_alerts.arn)
      && contains(aws_cloudwatch_metric_alarm.wal_archive_stalled.insufficient_data_actions, aws_sns_topic.ops_alerts.arn)
    )
    error_message = "wal_archive_stalled debe mandar sus TRES estados al topic de on-call: sin ok_actions nadie sabe que el archivado volvio, y sin insufficient_data_actions la alarma puede nacer muda."
  }
}

# El RPO SE MUEVE con el umbral, o no era una derivacion.
#
# Este bloque existe porque el de arriba, solo, resulto VACUO: se sustituyo el
# output por el literal `1077` —que es exactamente 777 + 60*5, los sentinelas del
# primer bloque— y los cinco tests pasaron en verde. Una igualdad comprobada con
# UN solo valor de entrada no distingue una funcion de una constante que hoy
# coincide, y esa es literalmente la diferencia entre derivar el RPO y
# prometerlo.
#
# Con un segundo umbral, ninguna constante puede satisfacer los dos bloques a la
# vez. La aritmetica ya la comprueba el de arriba; lo que anade este es la
# VARIACION, que es lo unico que prueba dependencia.
run "el_rpo_se_mueve_cuando_se_mueve_el_umbral" {
  command = plan

  variables {
    wal_archive_max_age_s = 333
  }

  override_resource {
    target          = aws_sns_topic.ops_alerts
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ops-alerts"
    }
  }

  assert {
    condition = output.rpo_seconds == (
      aws_cloudwatch_metric_alarm.wal_archive_stalled.threshold
      + aws_cloudwatch_metric_alarm.wal_archive_stalled.period
      * aws_cloudwatch_metric_alarm.wal_archive_stalled.evaluation_periods
    )
    error_message = "rpo_seconds no siguio al umbral al cambiarlo: es una constante disfrazada de derivacion, y el numero que cite el runbook dejara de describir a la alarma en cuanto alguien toque la vigilancia."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.wal_archive_stalled.threshold == 333
    error_message = "El umbral no siguio a la variable: la alarma esta cableada y el RPO derivado describe a otra alarma."
  }
}
