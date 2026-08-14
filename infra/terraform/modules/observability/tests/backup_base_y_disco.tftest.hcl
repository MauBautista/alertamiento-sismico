# [T-2.72.b · T-2.72.c] Las dos cegueras que dejo abiertas la Fase 2.6.
#
# `wal_archive_stalled` vigila la CADENA de WAL. No vigila su ANCLA ni el DISCO
# sobre el que vive todo, y las dos ausencias estaban FICHADAS en el comentario de
# esa misma alarma:
#
#   · EL ANCLA. Un WAL sin backup base no arranca. Un `barman-cloud-backup` que
#     falle cada semana no mueve `WalArchiveAgeSeconds` ni un segundo: el
#     archivado sigue perfecto y la cadena esta rota. Eso no se descubre hasta el
#     dia del restore, que es EL modo de fallo que la Fase 2.6 existe para
#     eliminar (`RUNBOOK-backup-restore-db.md:3`: "RESTORE JAMAS PROBADO").
#
#   · EL DISCO. Con el archivado atascado Postgres NO recicla su WAL: `pg_wal`
#     crece ~16 MiB/min sobre el mismo volumen de 40 GiB donde viven los datos —
#     menos de dos dias hasta llenar el disco y tumbar la DB. Hoy eso lo cubre
#     `wal_archive_stalled` POR ACCIDENTE (900 s ≪ 48 h), pero por la via
#     indirecta: mide el archivado, no el disco. Cualquier OTRA causa de disco
#     lleno —un log desbocado, un restore a base lateral, un `docker` con
#     imagenes acumuladas— sigue siendo invisible.
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

  # SENTINELAS, no los valores de produccion. Numeros que nadie escribiria a mano:
  # si el umbral estuviera cableado con una constante en vez de derivado de la
  # variable, estas aserciones se pondrian rojas. Con el valor real coincidirian
  # por casualidad y el test seria verde vacio (la leccion de `wal_archive_rpo`).
  base_backup_max_age_s = 1234567
  db_disk_used_max_pct  = 71
}

# --- 1. El ANCLA de la cadena -------------------------------------------------
run "la_alarma_del_backup_base_vigila_el_ancla_y_no_la_cadena" {
  command = plan

  override_resource {
    target          = aws_sns_topic.ops_alerts
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ops-alerts"
    }
  }

  # Contrato con el publicador, que vive en el documento SSM de
  # `modules/database` y que Terraform no puede leer desde aqui. Se blinda el otro
  # extremo del cable, igual que `ghost_gateways` con `ops/metrics.py` y
  # `wal_archive_stalled` con el script del PITR: si divergen, la alarma vigila una
  # metrica que nadie escribe y —al estar en `breaching`— grita para siempre.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.base_backup_missing.namespace == "Takab/Ops"
      && aws_cloudwatch_metric_alarm.base_backup_missing.metric_name == "BaseBackupAgeSeconds"
    )
    error_message = "base_backup_missing debe vigilar Takab/Ops/BaseBackupAgeSeconds, exactamente lo que publica el documento SSM de modules/database."
  }

  # EL UMBRAL SALE DE LAS MISMAS VARIABLES QUE GOBIERNAN LA RETENCION, que es el
  # criterio literal de la ficha. Un numero copiado se desincroniza el dia que
  # cambie la politica de retencion, y entonces la alarma vigilaria una cadena
  # distinta de la que S3 poda. El calculo (intervalo * margen * 86400) lo hace
  # `modules/database`, que es donde viven esas variables y donde se programa el
  # cron del backup base; aqui solo se comprueba que llega entero.
  assert {
    condition     = aws_cloudwatch_metric_alarm.base_backup_missing.threshold == var.base_backup_max_age_s
    error_message = "El umbral debe SER var.base_backup_max_age_s, que `modules/database` deriva de pitr.base_backup_interval_days * pitr.chain_margin. Cableado a una constante, la alarma vigila una cadena distinta de la que el lifecycle de S3 poda, y la desigualdad que mantiene viva la recuperacion se calcula sobre un numero que ya no ocurre."
  }

  # POR QUE `breaching`, y por que NO es la respuesta de `ghost_gateways`.
  #
  # En `ghost_gateways` el silencio se clasifico como `missing` porque la ausencia
  # de la metrica NO decia nada sobre fantasmas: solo que el worker que cuenta
  # estaba callado, y afirmar "hay fantasmas" habria sido afirmar lo que no se
  # sabe. Aqui hay DOS diferencias, y cada una sola ya bastaria:
  #
  #   (a) Lo que mide esta alarma no es "cuantos backups hay" sino "hasta que
  #       punto se puede recuperar". Cuando la metrica desaparece, la edad del
  #       ancla pasa a ser DESCONOCIDA — y un ancla desconocida es, operativamente,
  #       ausencia de ancla: no se puede prometer ninguna recuperacion. "No lo se"
  #       y "esta roto" son aqui la misma frase, igual que en `wal_archive_stalled`.
  #
  #   (b) El que publica y el que hace el backup son EL MISMO HOST. En
  #       `ghost_gateways` el contador podia morir con el sistema sano; aqui, si el
  #       publicador esta callado, el `barman-cloud-backup` de las 04:00 tampoco se
  #       esta ejecutando. El silencio no es solo ceguera: es tambien la averia.
  #
  # Con `notBreaching` el silencio se leeria como salud —la mentira de julio-2026
  # otra vez—; con `ignore` congelaria el ultimo veredicto; con `missing` la alarma
  # se apagaria para siempre en cuanto muriera el publicador, que es exactamente el
  # estado del sistema ANTES de esta ficha.
  assert {
    condition     = aws_cloudwatch_metric_alarm.base_backup_missing.treat_missing_data == "breaching"
    error_message = "base_backup_missing debe ser 'breaching'. La metrica es PERIODICA (un valor por minuto, tambien cuando no hay ningun backup base) y su ausencia no es ambigua: la edad del ancla pasa a ser DESCONOCIDA, y un ancla desconocida es, para un restore, lo mismo que no tener ancla. Ademas el que publica y el que respalda son el mismo host: si esto calla, el backup base tampoco se esta ejecutando."
  }

  # `Maximum` sobre el periodo: el peor minuto manda. Con `Average` un hueco
  # dentro del periodo se diluiria por debajo del umbral.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.base_backup_missing.statistic == "Maximum"
      && aws_cloudwatch_metric_alarm.base_backup_missing.comparison_operator == "GreaterThanThreshold"
      && aws_cloudwatch_metric_alarm.base_backup_missing.datapoints_to_alarm == null
    )
    error_message = "base_backup_missing debe alarmar con Maximum > umbral y N de N. Con `datapoints_to_alarm` (M de N) el peor caso de deteccion deja de ser period*evaluation_periods, y con este umbral —que ya es el ULTIMO instante util de la cadena— cualquier retraso extra se come el margen que queda."
  }

  # LOS TRES ESTADOS, y aqui el de OK es el mas importante de todos.
  #
  # Esta alarma NACE EN ALARM a proposito y no es un defecto: el dia del primer
  # apply todavia no existe ningun backup base (el primero se toma en T-2.74), asi
  # que "el ancla es demasiado vieja" es literalmente cierto. El correo de OK al
  # completarse el primer `barman-cloud-backup` es el ACUSE de que la cadena tiene
  # ancla — y es la unica senal, barata y automatica, de que el respaldo base
  # funciono ALGUNA vez. Sin `ok_actions` ese acuse no existe y el sistema vuelve a
  # la Fase 2.6: "creemos que hay respaldo".
  assert {
    condition = (
      contains(aws_cloudwatch_metric_alarm.base_backup_missing.alarm_actions, aws_sns_topic.ops_alerts.arn)
      && contains(aws_cloudwatch_metric_alarm.base_backup_missing.ok_actions, aws_sns_topic.ops_alerts.arn)
      && contains(aws_cloudwatch_metric_alarm.base_backup_missing.insufficient_data_actions, aws_sns_topic.ops_alerts.arn)
    )
    error_message = "base_backup_missing debe mandar sus TRES estados al topic de on-call. El de OK no es decoracion: esta alarma NACE en ALARM (el dia del apply no hay ningun backup base todavia) y el correo de OK al terminar el primero es el unico acuse de que la cadena consiguio un ancla."
  }
}

# El umbral SE MUEVE con su variable, o no era una derivacion.
#
# Este bloque existe por la misma razon que su gemelo en `wal_archive_rpo`: una
# igualdad comprobada con UN solo valor de entrada no distingue una funcion de una
# constante que hoy coincide. Con un segundo valor, ninguna constante puede
# satisfacer los dos bloques a la vez.
run "el_umbral_del_backup_base_se_mueve_con_su_variable" {
  command = plan

  variables {
    base_backup_max_age_s = 7654321
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.base_backup_missing.threshold == 7654321
    error_message = "El umbral no siguio a la variable: esta cableado, y el numero que gobierna la retencion en `modules/storage` deja de describir a la alarma en cuanto alguien cambie la politica."
  }
}

# --- 2. El DISCO --------------------------------------------------------------
run "la_alarma_de_disco_avisa_antes_de_que_pg_wal_tumbe_la_base" {
  command = plan

  override_resource {
    target          = aws_sns_topic.ops_alerts
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ops-alerts"
    }
  }

  # `disk_used_percent` NO existe en las metricas nativas de EC2 (AWS/EC2 solo trae
  # CPU, red, EBS y status checks: el hipervisor no ve dentro del filesystem). O se
  # instala el agente de CloudWatch o se publica desde la instancia. Se publica
  # desde la instancia, por el mismo cron que ya publica el reloj del RPO: un
  # agente mas es un demonio mas que puede morir en silencio en la maquina que
  # sostiene la DB, la API y los workers.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.db_disk_space.namespace == "Takab/Ops"
      && aws_cloudwatch_metric_alarm.db_disk_space.metric_name == "DataDiskUsedPercent"
    )
    error_message = "db_disk_space debe vigilar Takab/Ops/DataDiskUsedPercent, exactamente lo que publica el documento SSM de modules/database."
  }

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.db_disk_space.threshold == var.db_disk_used_max_pct
      && aws_cloudwatch_metric_alarm.db_disk_space.comparison_operator == "GreaterThanThreshold"
      && aws_cloudwatch_metric_alarm.db_disk_space.statistic == "Maximum"
    )
    error_message = "db_disk_space debe alarmar con Maximum > var.db_disk_used_max_pct. `Maximum` y no `Average`: el peor minuto del periodo es el que mide cuanto margen queda, y un pico que llena el disco no se promedia."
  }

  # POR QUE `missing` Y NO `breaching`, que es lo que llevan sus dos vecinas.
  #
  # Es la pregunta de `ghost_gateways`, y aqui la respuesta cae del otro lado que
  # en `base_backup_missing`. Lo que esta alarma afirma en su correo es "el disco
  # de /data paso del N %". Si la metrica no llega, eso NO se sabe: el disco puede
  # estar al 3 %. Con `breaching`, el correo AFIRMARIA una medida que nadie tomo —
  # y una alarma que afirma lo que no sabe se deja de creer, y arrastra consigo a
  # las que si saben (la leccion literal de T-2.60.a).
  #
  # Y la ceguera no queda tapada, que es lo que haria peligroso a `missing`: las
  # DOS causas posibles del silencio ya paginan por otro lado —la instancia caida
  # la coge `ec2_status` (breaching) y el cron muerto lo coge `wal_archive_stalled`
  # (breaching, mismo `/etc/cron.d/takab-pitr`, mismo `/opt/takab/bin`)—. Lo unico
  # que queda solo para esta alarma es que falle SU publicador y no los otros dos,
  # y para ese hueco esta `insufficient_data_actions`.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.db_disk_space.treat_missing_data == "missing"
      && contains(aws_cloudwatch_metric_alarm.db_disk_space.insufficient_data_actions, aws_sns_topic.ops_alerts.arn)
    )
    error_message = "db_disk_space debe ser 'missing' CON insufficient_data_actions, y las dos mitades van juntas. 'breaching' haria que el correo AFIRMARA una ocupacion de disco que nadie midio; 'notBreaching' e 'ignore' taparian la ceguera; y 'missing' SIN accion deja la alarma muda, que es exactamente como quedo gateway_offline el 29-jul-2026."
  }

  # Y los otros dos estados al topic. El de OK importa mas de lo que parece: una
  # alarma en `missing` NACE en INSUFFICIENT_DATA y `insufficient_data_actions`
  # SOLO dispara AL TRANSITAR — o sea que si la metrica no arranca NUNCA, la alarma
  # se queda aparcada ahi, sin correo y con cara de "todavia no hay datos". El
  # correo de OK al salir POR PRIMERA VEZ de ese estado es la unica senal
  # automatica de que el publicador llego a publicar; su AUSENCIA tras el apply es
  # el indicio, y por eso mirarlo una vez es un paso escrito de la ventana AWS.
  assert {
    condition = (
      contains(aws_cloudwatch_metric_alarm.db_disk_space.alarm_actions, aws_sns_topic.ops_alerts.arn)
      && contains(aws_cloudwatch_metric_alarm.db_disk_space.ok_actions, aws_sns_topic.ops_alerts.arn)
    )
    error_message = "db_disk_space debe mandar ALARM y OK al topic de on-call. Sin `ok_actions` se pierde la unica senal automatica de que la metrica llego a existir: `insufficient_data_actions` solo dispara EN TRANSICION, asi que una metrica que nunca arranca deja la alarma aparcada en INSUFFICIENT_DATA sin avisar a nadie."
  }

  # La ventana: 2 periodos de 5 min con la metrica publicandose cada minuto. No es
  # una cifra suelta — es lo que separa "el disco se esta llenando" de un pico de
  # un minuto (un dump, una imagen de docker a medio bajar). Y el margen que da el
  # umbral es lo que hace que 10 min no importen: a 16 MiB/min sobre 40 GiB, cada
  # punto porcentual son ~25 min, asi que un umbral del 80 % deja ~8 GiB ≈ 8,5 h de
  # margen antes de que Postgres se quede sin sitio.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.db_disk_space.period == 300
      && aws_cloudwatch_metric_alarm.db_disk_space.evaluation_periods == 2
    )
    error_message = "db_disk_space debe exigir 2 periodos de 5 min: con `datapoints_to_alarm = 1` o un solo periodo, un pico de un minuto (un dump, una imagen de docker bajando) paginaria de madrugada."
  }
}

run "el_umbral_de_disco_se_mueve_con_su_variable" {
  command = plan

  variables {
    db_disk_used_max_pct = 42
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.db_disk_space.threshold == 42
    error_message = "El umbral de disco no siguio a la variable: esta cableado."
  }
}

# Un umbral de disco que no deja margen no es una alarma, es un aviso de defuncion.
run "un_umbral_de_disco_sin_margen_no_se_puede_aplicar" {
  command = plan

  variables {
    db_disk_used_max_pct = 97
  }

  expect_failures = [var.db_disk_used_max_pct]
}
