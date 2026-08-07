# [T-2.71] Blinda la SEGUNDA linea de defensa del silenciador de alarmas.
#
# El riesgo que este archivo cierra: una ventana de mantenimiento silencia
# alarmas por NOMBRE, y las alarmas de CloudWatch no llevan dimension de tenant.
# El API deriva los nombres de filas que ya pasaron por RLS y ademas los valida
# contra `ALARM_CATALOG` (api/src/takab_api/ops/muting.py) — pero eso es UNA sola
# capa, y esta fase encontro quince mecanismos que se veian verdes sin atrapar
# nada. Si un dia esa validacion se rompe, lo unico que separa "callo mi
# gabinete" de "apago el detector de fallos de la plataforma" es esta politica.
#
# Que se puede blindar aqui y que NO:
#
#   SI  — la FORMA de la politica IAM: que las tres alarmas intocables no esten
#         entre los recursos, y que las cuatro silenciables si. Es `plan`, corre
#         offline, y falla ruidosamente si alguien anade un ARN de mas.
#   NO  — la mute rule en si. Son objetos AWS efimeros creados por API, no
#         gestionados por terraform: `treat_missing_data.tftest.hcl` no puede
#         asertar nada sobre ellas. Esa mitad vive en los tests de API
#         (derivacion bajo RLS, tope de duracion, acuse).
#
# El hecho que hace posible este archivo, y que NO se dio por supuesto: la doc de
# `put-alarm-mute-rule` (CLI 2.35.16, verificada en la maquina) dice que
# `cloudwatch:PutAlarmMuteRule` se comprueba sobre DOS tipos de recurso — la
# regla Y CADA ALARMA QUE LA REGLA APUNTA. Sin eso, la unica frontera habria
# quedado en el codigo del API.
#
# Corre con: terraform -chdir=infra/terraform/modules/database test

provider "aws" {
  region                      = "us-east-2"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

variables {
  subnet_id   = "subnet-0000000000test000"
  sg_db_id    = "sg-0000000000test000"
  kms_key_arn = "arn:aws:kms:us-east-2:000000000000:key/00000000-0000-0000-0000-000000000000"
  db_backups_bucket = {
    name = "takab-test-db-backups"
    arn  = "arn:aws:s3:::takab-test-db-backups"
  }
  worker_queue_arns = ["arn:aws:sqs:us-east-2:000000000000:takab-test-events"]
  env               = "dev"
}

run "el_silenciador_no_puede_tocar_las_alarmas_intocables" {
  command = plan

  # La AMI se resuelve contra la API de EC2 y tumbaria el plan sin credenciales:
  # se fija para que este test corra OFFLINE, como el de observability. No es un
  # atajo — un test de seguridad que exige credenciales de AWS no se corre.
  override_data {
    override_during = plan
    target          = data.aws_ami.al2023_arm64
    values = {
      id = "ami-00000000000test00"
    }
  }

  override_data {
    override_during = plan
    target          = data.aws_subnet.db
    values = {
      availability_zone = "us-east-2a"
    }
  }

  override_data {
    override_during = plan
    target          = data.aws_caller_identity.current
    values = {
      account_id = "000000000000"
    }
  }

  override_data {
    override_during = plan
    target          = data.aws_region.current
    values = {
      region = "us-east-2"
    }
  }

  # Los ARN de los secretos entran en la MISMA politica y no se conocen en
  # plan: sin fijarlos, el JSON entero queda "(known after apply)" y las
  # aserciones de abajo son INEVALUABLES — verde vacio, otra vez.
  override_resource {
    target          = aws_secretsmanager_secret.db["superuser"]
    override_during = plan
    values          = { arn = "arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/db/superuser" }
  }

  override_resource {
    target          = aws_secretsmanager_secret.db["migrator"]
    override_during = plan
    values          = { arn = "arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/db/migrator" }
  }

  override_resource {
    target          = aws_secretsmanager_secret.db["app"]
    override_during = plan
    values          = { arn = "arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/db/app" }
  }

  override_resource {
    target          = aws_secretsmanager_secret.db["ingest"]
    override_during = plan
    values          = { arn = "arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/db/ingest" }
  }

  # Las TRES que jamas se callan, por su razon escrita en ALARM_CATALOG:
  #   dlq_depth       — instrumento del canary de T-2.70: una actualizacion que
  #                     rompa el contrato de payload se manifiesta EXACTAMENTE ahi.
  #   iot_rule_errors — el otro extremo del mismo instrumento.
  #   ghost_gateways  — vigila al vigilante; su insufficient_data_actions es la
  #                     unica senal de que el worker que cuenta esta muerto.
  #
  # Se comprueba sobre el JSON RENDERIZADO de la politica, no sobre la lista de
  # una variable: es lo que de verdad se manda a IAM. Un ARN nuevo mal puesto en
  # cualquier statement pone esto en rojo, venga de donde venga.
  assert {
    condition = (
      !strcontains(aws_iam_role_policy.db.policy, "alarm:takab-dev-dlq")
      && !strcontains(aws_iam_role_policy.db.policy, "alarm:takab-dev-iot-rule-errors")
      && !strcontains(aws_iam_role_policy.db.policy, "alarm:takab-dev-gateway-retirado")
    )
    error_message = "La politica concede PutAlarmMuteRule sobre una alarma INTOCABLE. dlq_depth e iot_rule_errors son el instrumento del canary de T-2.70 (silenciarlas durante un despliegue es apagar el detector del fallo que el despliegue puede causar) y ghost_gateways vigila al vigilante. Ver ALARM_CATALOG en api/src/takab_api/ops/muting.py."
  }

  # Y que las cuatro silenciables SI esten: sin esto, la asercion de arriba
  # pasaria en verde con una politica que no concede NADA — verde vacio, que es
  # justo el modo de fallo que esta fase persigue.
  assert {
    condition = (
      strcontains(aws_iam_role_policy.db.policy, "alarm:takab-dev-gateway-offline-*")
      && strcontains(aws_iam_role_policy.db.policy, "alarm:takab-dev-sensor-mudo-*")
      && strcontains(aws_iam_role_policy.db.policy, "alarm:takab-dev-ec2-status-check")
      && strcontains(aws_iam_role_policy.db.policy, "alarm:takab-dev-ec2-cpu-sostenida")
    )
    error_message = "Faltan las alarmas SILENCIABLES en la politica: sin ellas la ventana no silencia nada y la asercion de las intocables pasaria en verde sobre una politica vacia."
  }

  # La regla solo puede gestionar SUS PROPIAS ventanas (`takab-dev-mw-<id>`): no
  # puede pisar ni borrar una mute rule abierta a mano por un humano para otra
  # cosa. `DeleteAlarmMuteRule` desilencia EN EL ACTO, asi que un comodin aqui
  # dejaria al API reabrir —o tapar— silencios que no son suyos.
  assert {
    condition = (
      strcontains(aws_iam_role_policy.db.policy, "alarm-mute-rule:takab-dev-mw-*")
      && !strcontains(aws_iam_role_policy.db.policy, "alarm-mute-rule:*")
    )
    error_message = "El alcance de las mute rules debe ser `alarm-mute-rule:takab-dev-mw-*`: con un comodin, el API podria borrar (y por tanto desilenciar, o re-silenciar) reglas creadas por humanos."
  }

  # `PutMetricData` sigue acotado por namespace (T-2.60.a). Va aqui porque los
  # dos permisos de CloudWatch de la nube conviven en la MISMA politica: separar
  # las aserciones invitaria a que alguien ensanchara una al tocar la otra.
  assert {
    condition     = strcontains(aws_iam_role_policy.db.policy, "Takab/Ops")
    error_message = "PutMetricData perdio su condicion de namespace Takab/Ops."
  }
}
