# [T-2.162] El aviso tiene que decir QUE HACER y DONDE.
#
# El correo de on-call es la plantilla cruda de CloudWatch: nombra la alarma, su
# causa y sus umbrales, y no menciona el acuse ni su URL. Medido el 2026-08-22 en
# el ensayo cronometrado de T-2.78: quien lo recibio acababa de ejecutar el ensayo
# entero —habia acunado la credencial, abierto la pagina y acusado un aviso veinte
# minutos antes— y aun asi pregunto cual era "el codigo" que habia que pegar.
#
# El unico texto nuestro que viaja en ese correo es `alarm_description`. Por eso el
# arreglo va ahi y no en un canal nuevo.

# [T-2.145] El provider FALSO, que los otros seis ficheros de este directorio ya
# traían y este no. Sin él la prueba usa el perfil AWS del entorno
# (`AWS_PROFILE=takab-dev`), así que en CI pasa —allí no hay perfil— y en local
# depende de si el token SSO sigue vivo: el mismo commit da verde por la mañana y
# rojo por la tarde. Medido el 2026-08-22, con este error exacto:
#
#   Error: No valid credential sources found
#   failed to refresh cached credentials, refresh cached SSO token failed
#
# Es la familia de T-2.115 y T-2.142: el veredicto no puede depender de algo que
# no está en el test.
provider "aws" {
  region                      = "us-east-2"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

variables {
  ops_alert_email           = "ops@example.test"
  dlq_names                 = { backfill = "q-backfill-dlq" }
  instance_id               = "i-0000000000test000"
  iot_rule_errors_log_group = "/aws/iot/takab-test"
  paged_gateways            = ["gw-test-0001"]
  wal_archive_max_age_s     = 600
  base_backup_max_age_s     = 1209600
  base_backup_warn_age_s    = 608400
}

run "toda_alarma_dice_donde_acusar_cuando_hay_endpoint" {
  command = plan

  variables {
    ops_alert_https_endpoint = "https://consola.example/api/ops/alerts/sns"
    ops_ack_deadline_s       = 900
  }

  # Se comprueban DOS alarmas de familias distintas —una de cola, una de
  # plataforma— para que el sufijo no pueda estar pegado a mano en una sola.
  assert {
    condition = (
      strcontains(aws_cloudwatch_metric_alarm.dlq_depth["backfill"].alarm_description, "/ops/alerts/ack")
      && strcontains(aws_cloudwatch_metric_alarm.ec2_status.alarm_description, "/ops/alerts/ack")
    )
    error_message = "El aviso no dice DONDE acusar. `alarm_description` es el unico texto nuestro que viaja en el correo de SNS: si la URL no esta ahi, no esta en ningun sitio que el destinatario vea a las 3 de la manana."
  }

  # El plazo, y en minutos: "900 s" obliga a dividir a quien acaba de despertarse.
  assert {
    condition     = strcontains(aws_cloudwatch_metric_alarm.dlq_depth["backfill"].alarm_description, "15 min")
    error_message = "El aviso no dice CUANTO plazo hay. Saber que son quince minutos y no una hora cambia lo que hace una persona medio dormida."
  }

  # Y que el plazo SE DERIVE: con otro valor, el texto tiene que moverse.
  assert {
    condition     = !strcontains(aws_cloudwatch_metric_alarm.ec2_cpu.alarm_description, "900")
    error_message = "El plazo aparece en segundos crudos. Va en minutos, que es la unidad en la que piensa quien lo lee."
  }
}

run "el_plazo_se_deriva_y_no_esta_horneado" {
  command = plan

  variables {
    ops_alert_https_endpoint = "https://consola.example/api/ops/alerts/sns"
    ops_ack_deadline_s       = 300
  }

  # ⚠️ "5 min" NO basta: es SUBCADENA de "15 min", asi que con el plazo horneado a
  # 15 esta asercion pasaria igual. Lo comprobo el ejercicio de romper el codigo a
  # proposito — el test paso cuando debia fallar. Se exige el texto exacto Y la
  # AUSENCIA del valor viejo.
  assert {
    condition = (
      strcontains(aws_cloudwatch_metric_alarm.dlq_depth["backfill"].alarm_description, "tienes 5 min")
      && !strcontains(aws_cloudwatch_metric_alarm.dlq_depth["backfill"].alarm_description, "15 min")
    )
    error_message = "El plazo no siguio a `ops_ack_deadline_s`: es un literal disfrazado de derivacion, y el dia que se cambie el plazo el correo seguira prometiendo el viejo."
  }
}

# Sin suscriptor HTTPS no hay avisos que acusar: el endpoint no recibe nada y la
# base no registra ninguna fila. Anunciar la URL entonces seria mandar a alguien a
# una pagina donde no hay nada suyo que atender.
run "sin_suscriptor_https_no_se_anuncia_un_acuse_que_no_existe" {
  command = plan

  variables {
    ops_alert_https_endpoint = ""
    ops_ack_deadline_s       = 900
  }

  assert {
    condition     = !strcontains(aws_cloudwatch_metric_alarm.dlq_depth["backfill"].alarm_description, "/ops/alerts/ack")
    error_message = "Se anuncia el acuse sin suscriptor HTTPS. Sin el, ningun aviso llega a la base: la pagina existiria pero no habria nada que acusar, y mandar alli a alguien de guardia a las 3 a.m. es peor que no decir nada."
  }
}
