# [T-2.141] El aviso de backup base llegaba cuando ya no habia ventana.
#
# `T-2.72.b` puso la alarma que pedia su ficha: `intervalo * margen`. Al
# implementarla se descubrio —y quedo declarado en su propio comentario— que con
# los valores por defecto ese producto es 7 x 2 = 14 dias, o sea EXACTAMENTE
# `wal_retention_days`. El correo llega justo cuando la ventana de recuperacion
# se cierra: es correcto como ULTIMA LINEA ("ya no puedes recuperar") y no sirve
# de AVISO.
#
# El fallo que hay que cazar es EL PRIMER backup base que falla, no el
# decimocuarto dia. Con el cron en `*/N` del dia del mes, el primer hueco de mas
# de `intervalo` dias significa exactamente eso: el primer `barman-cloud-backup`
# que no se completo. De ahi sale el umbral, y de ahi que sean DOS alarmas y no
# una — dicen cosas distintas y piden acciones distintas:
#
#   AVISO (esta)   : "fallo UN backup base; te quedan ~`intervalo` dias de
#                     ventana". Accion: mirar el log y relanzarlo a mano.
#   ULTIMA LINEA   : "han fallado `margen` seguidos; la ventana ya se cerro".
#                     Accion: asumir que no hay restore y reconstruir la cadena.
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
  db_disk_used_max_pct      = 71

  # SENTINELAS, no valores de produccion, y por la razon de siempre: con el valor
  # real una igualdad coincidiria por casualidad y no distinguiria una derivacion
  # de una constante (la leccion del literal `1077`). Aqui hacen ademas un segundo
  # trabajo: son DOS numeros distintos y en el ORDEN correcto (el aviso por
  # debajo), asi que ninguna asercion puede pasar confundiendo una alarma con la
  # otra ni con los umbrales cableados al reves.
  base_backup_max_age_s  = 8765432
  base_backup_warn_age_s = 1234567
}

# --- 1. El aviso existe, mira la MISMA metrica y NO el mismo numero ------------
run "el_aviso_vigila_la_misma_metrica_con_un_umbral_propio" {
  command = plan

  override_resource {
    target          = aws_sns_topic.ops_alerts
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ops-alerts"
    }
  }

  # MISMA metrica, mismo publicador, misma cadencia. Esto no es ahorro: es la
  # razon por la que las dos alarmas pueden convivir sin tocar la instancia. El
  # publicador de `T-2.72.b` ya emite la edad del ancla cada minuto; el aviso solo
  # necesita otro corte sobre la misma serie.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.base_backup_late.namespace == "Takab/Ops"
      && aws_cloudwatch_metric_alarm.base_backup_late.metric_name == "BaseBackupAgeSeconds"
      && aws_cloudwatch_metric_alarm.base_backup_late.metric_name == aws_cloudwatch_metric_alarm.base_backup_missing.metric_name
    )
    error_message = "El aviso dejo de mirar la misma serie que su hermana: o le hace falta un publicador nuevo (y entonces hay que tocar la instancia), o esta vigilando otra cosa."
  }

  # La misma ventana de evaluacion que su hermana, y a proposito: la serie es la
  # misma y se publica al mismo ritmo, asi que un `period` distinto solo
  # introduciria una diferencia sin causa. Lo que separa a las dos alarmas es el
  # UMBRAL, que es lo unico que las hace decir cosas distintas.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.base_backup_late.period == aws_cloudwatch_metric_alarm.base_backup_missing.period
      && aws_cloudwatch_metric_alarm.base_backup_late.evaluation_periods == aws_cloudwatch_metric_alarm.base_backup_missing.evaluation_periods
      && aws_cloudwatch_metric_alarm.base_backup_late.statistic == "Maximum"
      && aws_cloudwatch_metric_alarm.base_backup_late.comparison_operator == "GreaterThanThreshold"
      && aws_cloudwatch_metric_alarm.base_backup_late.datapoints_to_alarm == null
    )
    error_message = "El aviso y la ultima linea evaluan la misma serie con ventanas distintas: una de las dos esta describiendo una cadencia de publicacion que no existe."
  }

  # EL UMBRAL SALE DE SU VARIABLE. Es la mitad del criterio "las dos derivan de
  # las mismas variables".
  assert {
    condition     = aws_cloudwatch_metric_alarm.base_backup_late.threshold == var.base_backup_warn_age_s
    error_message = "El umbral del aviso no sale de su variable: con un literal aqui, cambiar `base_backup_interval_days` dejaria al aviso vigilando un intervalo que ya no es el del cron."
  }

  # NINGUNA REPITE UN NUMERO. Es la otra mitad, y es la que impide el modo de
  # fallo mas tonto posible: dos alarmas con el mismo umbral son una alarma
  # duplicada, dos correos por el mismo hecho y ningun aviso temprano.
  assert {
    condition     = aws_cloudwatch_metric_alarm.base_backup_late.threshold != aws_cloudwatch_metric_alarm.base_backup_missing.threshold
    error_message = "Las dos alarmas comparten umbral: entonces no hay aviso, hay eco. El aviso tiene que disparar ANTES."
  }

  # Y el orden entre ellas, que es lo unico que hace que una sea "aviso" y la otra
  # "ultima linea". Sin esto, invertir las variables por error dejaria el aviso
  # llegando DESPUES del final del mundo y nada se pondria rojo.
  assert {
    condition     = aws_cloudwatch_metric_alarm.base_backup_late.threshold < aws_cloudwatch_metric_alarm.base_backup_missing.threshold
    error_message = "El aviso dispara DESPUES que la ultima linea: eso no es un aviso, es un segundo correo tarde."
  }
}

# --- 2. La severidad, distinguida en el unico sitio donde se lee --------------
#
# Este repo NO tiene rieles de severidad: hay UN solo topic SNS y ninguna alarma
# lleva tags. Inventar un segundo topic significaria una suscripcion de correo
# mas que alguien tiene que confirmar a mano, y una alarma que no avisa hasta que
# se confirme es peor que ninguna. Asi que la severidad viaja por donde de verdad
# la lee quien esta de guardia a las 04:00: el NOMBRE de la alarma —que es el
# asunto del correo— y la primera frase de la descripcion.
run "la_severidad_se_distingue_en_el_nombre_y_en_la_primera_frase" {
  command = plan

  # El ARN del topic no se conoce hasta el apply, y las tres listas de acciones
  # dependen de el: sin este override, `length(...)` no se puede evaluar en plan.
  override_resource {
    target          = aws_sns_topic.ops_alerts
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ops-alerts"
    }
  }

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.base_backup_late.alarm_name == "takab-dev-backup-base-atrasado"
      && aws_cloudwatch_metric_alarm.base_backup_late.alarm_name != aws_cloudwatch_metric_alarm.base_backup_missing.alarm_name
    )
    error_message = "Los dos nombres son iguales o el del aviso cambio: el nombre es el asunto del correo y es lo unico que distingue 'fallo uno' de 'ya no puedes recuperar' antes de abrirlo. Si cambia, ALARM_CATALOG (api/src/takab_api/ops/muting.py) queda huerfano."
  }

  # Las dos descripciones tienen que decir cosas DISTINTAS, y en concreto el aviso
  # tiene que decir que TODAVIA HAY VENTANA. Un aviso que se lee como la ultima
  # linea provoca la reaccion de la ultima linea, que es la cara —reconstruir la
  # cadena— cuando bastaba con relanzar el backup.
  assert {
    condition = (
      strcontains(aws_cloudwatch_metric_alarm.base_backup_late.alarm_description, "AVISO")
      && strcontains(aws_cloudwatch_metric_alarm.base_backup_late.alarm_description, "todavia se puede recuperar")
      && !strcontains(aws_cloudwatch_metric_alarm.base_backup_missing.alarm_description, "AVISO")
    )
    error_message = "La descripcion del aviso no dice que aun hay ventana, o la de la ultima linea se convirtio en un aviso. Las dos llegan al mismo buzon: lo unico que las separa es lo que dicen."
  }

  # Los tres estados, como todas las de esta familia. El de OK es el que importa
  # aqui: es el acuse de que el backup base volvio a completarse a tiempo.
  assert {
    condition = (
      length(aws_cloudwatch_metric_alarm.base_backup_late.alarm_actions) == 1
      && length(aws_cloudwatch_metric_alarm.base_backup_late.ok_actions) == 1
      && length(aws_cloudwatch_metric_alarm.base_backup_late.insufficient_data_actions) == 1
    )
    error_message = "Al aviso le falta alguno de los tres estados. Sin `ok_actions` nadie se entera de que el respaldo se recupero; sin `insufficient_data_actions` la transicion al silencio no se ve."
  }
}

# --- 3. `treat_missing_data`: `missing`, y con CUAL de los dos argumentos -----
#
# Las dos hermanas eligieron valores OPUESTOS con buen criterio, y aqui hay que
# decir cual de los dos argumentos aplica:
#
#   · `base_backup_missing` = `breaching`: no mide "cuantos backups hay" sino
#     "hasta donde se puede recuperar", y un ancla DESCONOCIDA es, para un
#     restore, lo mismo que no tener ancla.
#   · `db_disk_space` = `missing`: su correo AFIRMA UNA MEDIDA ("el disco paso
#     del 80 %") y sin datapoint esa medida no existe.
#
# APLICA EL DE `db_disk_space`, y con una razon extra que solo existe en un par:
#
#   (a) el correo de ESTA alarma afirma una medida y ademas una TRANQUILIDAD:
#       "fallo un backup base, TE QUEDAN ~7 dias de ventana". Sin datapoint no
#       solo no consta el fallo: la tranquilidad seria FALSA, porque lo que no se
#       sabe podria ser mucho peor que un backup fallido.
#   (b) y la razon que ninguna hermana tiene: el silencio YA ESTA CUBIERTO, por
#       la misma metrica, el mismo publicador y el mismo host — su hermana en
#       `breaching`. Poner `breaching` aqui tambien no anadiria vigilancia: haria
#       llegar DOS correos por el mismo hecho, y el del aviso diria "te quedan 7
#       dias" mientras el de al lado dice "ya no puedes recuperar". Un aviso que
#       INFRAVALORA el silencio es peor que un aviso que calla cuando su hermana
#       ya esta gritando.
run "el_silencio_del_aviso_lo_cubre_su_hermana_y_por_eso_es_missing" {
  command = plan

  assert {
    condition     = aws_cloudwatch_metric_alarm.base_backup_late.treat_missing_data == "missing"
    error_message = "El aviso cambio su treat_missing_data. Con `breaching` mandaria un segundo correo por el mismo silencio, y ademas lo INFRAVALORARIA: diria 'te quedan dias de ventana' cuando lo que pasa es que no se sabe nada. El silencio es trabajo de su hermana."
  }

  # LA CONDICION QUE HACE SEGURO ese `missing`, comprobada y no supuesta: la
  # hermana existe, mira LA MISMA metrica y esta en `breaching`. Si alguien la
  # relajara, este `missing` se quedaria sin cobertura y habria que reabrirlo.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.base_backup_missing.treat_missing_data == "breaching"
      && aws_cloudwatch_metric_alarm.base_backup_missing.metric_name == aws_cloudwatch_metric_alarm.base_backup_late.metric_name
      && aws_cloudwatch_metric_alarm.base_backup_missing.namespace == aws_cloudwatch_metric_alarm.base_backup_late.namespace
    )
    error_message = "La hermana en `breaching` dejo de cubrir el silencio de esta metrica: entonces el `missing` del aviso deja de ser una decision y pasa a ser una ceguera. Reabrir T-2.141."
  }
}

# --- 4. El umbral se MUEVE con su variable (segundo juego de centinelas) -------
#
# Gemelo del de `wal_archive_rpo` y del de `backup_base_y_disco`: una igualdad
# comprobada con UN solo valor no distingue una funcion de una constante que hoy
# coincide. Con un segundo valor ninguna constante satisface los dos bloques.
#
# Y aqui hace falta el doble, porque son DOS umbrales: se mueven los dos a la vez
# y en direcciones distintas, de modo que ninguna constante ni ningun cableado
# cruzado (aviso leyendo la variable de la hermana) puede sobrevivir.
run "los_dos_umbrales_se_mueven_cada_uno_con_SU_variable" {
  command = plan

  variables {
    base_backup_max_age_s  = 999888
    base_backup_warn_age_s = 111222
  }

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.base_backup_late.threshold == 111222
      && aws_cloudwatch_metric_alarm.base_backup_missing.threshold == 999888
    )
    error_message = "Un umbral no siguio a SU variable: o esta cableado, o las dos alarmas leen la misma. En el segundo caso el aviso deja de avisar en cuanto cambie la politica de retencion."
  }
}
