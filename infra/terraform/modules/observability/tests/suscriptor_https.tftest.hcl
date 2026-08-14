# [T-2.78.a] El suscriptor que SI deja rastro, y el candado de que hoy no cambia nada.
#
# El hueco: la cadena de operacion (CloudWatch → SNS → correo) no deja rastro en
# ninguna tabla de TAKAB, y AWS tampoco lo da — el registro de estado de entrega
# de SNS soporta Firehose, SQS, Lambda, HTTPS y endpoints de aplicacion, y
# `email`/`email-json` NO estan en esa lista
# (https://docs.aws.amazon.com/sns/latest/dg/sns-topic-attributes.html). Asi que
# "publicado" era todo lo que se podia afirmar.
#
# Este fichero mide tres cosas y ninguna es cosmetica:
#
#   1. con la variable VACIA no se crea ni un recurso nuevo — o sea que este
#      cambio no puede romper el apply de hoy, que es la unica forma de meter
#      infraestructura en una cuenta que sostiene alarmas vivas;
#   2. con la variable puesta, la suscripcion es `https` (no `http`) y se
#      autoconfirma, que es lo que hace que terraform pueda terminar el apply;
#   3. y el REGISTRO DE ENTREGA queda cableado al topic. Sin esos tres atributos
#      la suscripcion existiria y seguiriamos sin poder decir a que hora salio
#      nada desde el lado de AWS.
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
  dlq_names                 = { backfill = "takab-test-dlq-backfill" }
  instance_id               = "i-0000000000test000"
  iot_rule_errors_log_group = "/aws/iot/takab-test"
  paged_gateways            = ["gw-test-0001"]
  wal_archive_max_age_s     = 600
  base_backup_max_age_s     = 1209600
  base_backup_warn_age_s    = 604800
}

run "sin_endpoint_el_apply_de_hoy_no_cambia" {
  command = plan

  variables {
    ops_alert_https_endpoint = ""
  }

  assert {
    condition     = length(aws_sns_topic_subscription.ops_https) == 0
    error_message = "con la variable vacia NO puede planificarse ninguna suscripcion https: el default tiene que ser inerte."
  }

  assert {
    condition     = length(aws_iam_role.sns_delivery_logs) == 0
    error_message = "con la variable vacia NO puede planificarse el rol de registro de entrega."
  }

  assert {
    # La comprobacion de no-vacuidad del bloque de arriba: el topic y su correo
    # SIGUEN estando. Si este fichero solo midiera ausencias, un modulo entero
    # borrado por accidente tambien saldria verde.
    condition     = aws_sns_topic_subscription.ops_email.protocol == "email"
    error_message = "la suscripcion por correo del on-call desaparecio: el canal que despierta a la persona sigue siendo ese."
  }

  assert {
    condition     = aws_sns_topic.ops_alerts.http_success_feedback_role_arn == null
    error_message = "sin endpoint https no puede quedar un rol de registro de entrega cableado al topic."
  }
}

run "con_endpoint_la_suscripcion_es_https_y_deja_registro" {
  command = plan

  variables {
    ops_alert_https_endpoint = "https://consola.example.test/api/ops/alerts/sns"
  }

  assert {
    condition     = aws_sns_topic_subscription.ops_https[0].protocol == "https"
    error_message = "el suscriptor de rastro tiene que ir por https: por http viajarian en claro el nombre de cada alarma y el motivo de cada fallo."
  }

  assert {
    condition     = aws_sns_topic_subscription.ops_https[0].endpoint_auto_confirms == true
    error_message = "sin autoconfirmacion la suscripcion se queda en PendingConfirmation y el apply no termina; el endpoint confirma solo, y sin visitar el SubscribeURL del cuerpo."
  }

  assert {
    condition     = aws_sns_topic_subscription.ops_https[0].raw_message_delivery == false
    error_message = "con entrega cruda el endpoint recibiria el Message pelado, SIN Signature ni SigningCertURL: no habria nada que verificar y cualquiera podria inventarse un aviso."
  }

  # El ARN del rol no se conoce hasta despues del apply, asi que la union
  # topic→rol se mide por lo que SI se conoce en el plan: que el rol se crea, que
  # solo lo puede asumir SNS, y que el topic tomo la rama encendida (el muestreo
  # deja de ser null). Con esos tres, un `null` en el ARN es imposible.
  assert {
    condition     = length(aws_iam_role.sns_delivery_logs) == 1
    error_message = "sin rol no hay registro de entrega: la mitad de AWS de la evidencia de que el aviso salio."
  }

  assert {
    condition     = strcontains(data.aws_iam_policy_document.sns_delivery_logs_assume.json, "sns.amazonaws.com")
    error_message = "el rol del registro de entrega solo lo puede asumir SNS; cualquier otro principal seria un rol de escritura de logs regalado."
  }

  assert {
    condition     = aws_sns_topic.ops_alerts.http_success_feedback_sample_rate == 100
    error_message = "un muestreo por debajo del 100 % convierte la evidencia en estadistica: el aviso que nadie contesto puede ser justo el que no se registro."
  }
}
