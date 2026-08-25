# [T-2.153] La alarma que ve la deriva de esquema SIN que nadie la provoque.
#
# El 2026-08-21 la nube corria `0038` con el repo en `0046` —OCHO migraciones— y
# no lo dijo ni una alarma, ni un health-check ni un test. El gate del despliegue
# (`deploy/cloud/deploy.sh`) cubre la mitad: hace visible la deriva CUANDO
# alguien despliega. Pero aquello no se rompio por un despliegue malo, sino
# porque NADIE DESPLEGO durante dias — y eso solo lo ve algo que mire solo.
#
# Este archivo blinda las decisiones que no rompen el plan si se eligen mal y
# producen una alarma que MIENTE: el significado del silencio, el umbral, el
# estadistico y —la que ya costo catorce dias de alarma muda— que el estado de
# OK tambien avise.
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

  # [T-2.72] La alarma de atasco del archivado no tiene default (su dueño es
  # `modules/database`): sin este valor, el modulo entero no planifica y ESTE
  # archivo dejaria de comprobar nada. La decision sobre su `treat_missing_data`
  # —`breaching`, porque ahi la ausencia de metrica SI es la condicion vigilada—
  # se razona y se comprueba en `tests/wal_archive_rpo.tftest.hcl`, que es donde
  # vive todo lo de esa alarma. La linea de abajo lo fija tambien desde aqui para
  # que el archivo que gobierna el significado del SILENCIO no tenga un hueco.
  wal_archive_max_age_s = 600

  # [T-2.72.b] Mismo caso: su dueño es `modules/database`, que lo deriva de
  # `pitr.base_backup_interval_days * pitr.chain_margin`. Sin valor, el modulo no
  # planifica y ESTE archivo dejaria de comprobar nada.
  base_backup_max_age_s = 1209600
  # [T-2.141] Mismo caso: su dueno es `modules/database`, que la deriva de
  # `pitr.base_backup_interval_days` sin el margen. Aqui solo tiene que existir.
  base_backup_warn_age_s = 604800

  # [T-2.81.a] Y el de la retencion de PII, por lo mismo: su dueño es
  # `modules/database` (cadencia x margen). Sin valor el modulo no planifica y
  # este archivo dejaria de comprobar nada.
  pii_retention_max_age_s = 172800
}

run "la_deriva_de_esquema_avisa_por_AUSENCIA_y_publica_el_cero" {
  command = plan

  override_resource {
    target          = aws_sns_topic.ops_alerts
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ops-alerts"
    }
  }

  # `breaching` cubre TRES ausencias que significan lo mismo: la API que no
  # contesta, un estado que no es un numero (`desconocida`/`adelantada`) y —la
  # que da nombre a la ficha— que nadie haya desplegado desde que existe el
  # publicador. Con `notBreaching` la nube podria pasarse semanas atrasada en
  # silencio, que es exactamente lo que paso el 2026-08-21.
  assert {
    condition     = aws_cloudwatch_metric_alarm.schema_drift.treat_missing_data == "breaching"
    error_message = "el silencio de SchemaPendingMigrations tiene que ALARMAR: sin metrica, 'al dia' es una suposicion."
  }

  # Umbral CERO y no un margen: una sola migracion pendiente ya es el defecto.
  # La tolerancia va en los periodos, no en la cantidad.
  assert {
    condition     = aws_cloudwatch_metric_alarm.schema_drift.threshold == 0
    error_message = "el umbral no puede tolerar migraciones pendientes: una sola ya rompe cosas en silencio."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.schema_drift.comparison_operator == "GreaterThanThreshold"
    error_message = "la comparacion tiene que ser > 0: con >= la alarma estaria SIEMPRE encendida."
  }

  # `Maximum` y no `Average`: con varios datapoints en la ventana, un promedio
  # diluye la deriva —dos minutos atrasado y tres al dia dan 0.4— y la alarma
  # no llega a cruzar el umbral.
  assert {
    condition     = aws_cloudwatch_metric_alarm.schema_drift.statistic == "Maximum"
    error_message = "con Average la deriva se diluye entre los datapoints sanos de la misma ventana."
  }

  # AVISA EN LOS TRES ESTADOS. El de OK es el que convierte esto en una alarma y
  # no en un adorno: `takab-dev-iot-rule-errors` estuvo catorce dias en ALARM por
  # estar sana y ademas MUDA, porque sin publicar el cero solo tuvo UNA
  # transicion en toda su vida y SNS solo notifica transiciones.
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.schema_drift.ok_actions) == 1
    error_message = "sin ok_actions, la vuelta al dia no avisa y nadie sabe que se arreglo."
  }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.schema_drift.alarm_actions) == 1
    error_message = "una alarma sin destinatario no es una alarma."
  }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.schema_drift.insufficient_data_actions) == 1
    error_message = "INSUFFICIENT_DATA tambien tiene que avisar: es 'no se sabe', no 'esta bien'."
  }

  # La metrica sale del MISMO namespace que el permiso del rol de la instancia
  # (`cloudwatch:namespace` en modules/database). Si divergieran, el publicador
  # recibiria AccessDenied y la alarma se quedaria ciega sin que nada pareciera
  # roto — el modo de fallo mas caro de este modulo.
  assert {
    condition     = aws_cloudwatch_metric_alarm.schema_drift.namespace == "Takab/Ops"
    error_message = "el namespace tiene que coincidir con la condicion IAM del rol, o la metrica se rechaza en silencio."
  }
}

run "la_ventana_del_despliegue_no_dispara_la_alarma" {
  command = plan

  override_resource {
    target          = aws_sns_topic.ops_alerts
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ops-alerts"
    }
  }

  # Entre que `alembic upgrade head` corre y que la API nueva contesta hay
  # segundos en los que la metrica puede leer un valor de transito. Con UN solo
  # periodo, cada despliegue mandaria un correo — y una alarma que suena en
  # operacion normal se acaba filtrando a la papelera, que es como se pierde la
  # unica que avisa de verdad.
  assert {
    condition     = aws_cloudwatch_metric_alarm.schema_drift.evaluation_periods >= 2
    error_message = "con 1 periodo la ventana del propio despliegue dispara la alarma y el aviso se vuelve ruido."
  }
}
