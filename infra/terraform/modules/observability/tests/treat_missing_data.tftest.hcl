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

  # [T-2.72] La alarma de atasco del archivado no tiene default (su dueño es
  # `modules/database`): sin este valor, el modulo entero no planifica y ESTE
  # archivo dejaria de comprobar nada. La decision sobre su `treat_missing_data`
  # —`breaching`, porque ahi la ausencia de metrica SI es la condicion vigilada—
  # se razona y se comprueba en `tests/wal_archive_rpo.tftest.hcl`, que es donde
  # vive todo lo de esa alarma. La linea de abajo lo fija tambien desde aqui para
  # que el archivo que gobierna el significado del SILENCIO no tenga un hueco.
  wal_archive_max_age_s = 600
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

# --- [T-2.60.a] El gabinete retirado que sigue latiendo -----------------------
#
# Esta alarma llego el 2026-08-05 (commit 6244bb0) SIN una sola linea en este archivo, que es
# donde vive la regla de decision. Una alarma sin su asercion significa que la proxima vez se
# decide de memoria — y de memoria ya nos equivocamos cuatro veces con `gateway_offline`.
#
# Su `treat_missing_data` NO se decide con la misma pregunta que las otras tres. En
# `gateway_offline` y `ec2_status` la ausencia de datapoints ES la falla que la alarma
# describe. Aqui no: la metrica la publica el worker `notify` (`api/src/takab_api/ops/
# metrics.py`), un valor cada 60 s SIEMPRE, incluido el cero. Su silencio no dice nada sobre
# fantasmas — dice que el que cuenta esta callado, que es OTRO problema.
#
# La tabla de la cabecera, repasada contra ESTE caso:
#   notBreaching -> el silencio se declara OK. Es la mentira de julio-2026 otra vez: con el
#                   worker caido la alarma pinta verde y nadie se entera de nada.
#   breaching    -> el silencio se declara ALARMA, y el correo AFIRMA "hay gabinete(s) dados
#                   de baja enviando latidos" sin que nadie haya contado un solo gabinete.
#                   Una alarma que afirma lo que no sabe se deja de creer, y arrastra consigo
#                   a las que si saben.
#   ignore       -> retiene el ultimo veredicto. Con el worker muerto congela un OK (o un
#                   ALARMA) indefinidamente: asi se quedo `gateway_offline` trabada 4 h el
#                   30-jul-2026.
#   missing      -> el silencio lleva a INSUFFICIENT_DATA, que aqui es lo unico HONESTO que se
#                   puede decir: "no se nada de esto".
#
# VEREDICTO: el valor que eligio 6244bb0 es el correcto, y esta asercion lo fija. Pero es
# correcto SOLO emparejado con `insufficient_data_actions`. El fallo del 29-jul-2026 no fue
# `missing`: fue `missing` con las acciones de INSUFFICIENT_DATA vacias, que dejo la alarma
# MUDA. Por eso las dos aserciones van en el mismo bloque: separadas, alguien borra un dia la
# de las acciones y la otra sigue verde certificando una alarma que no habla.
#
# Y no es un ejercicio teorico. Entre el 2026-08-04 y el 2026-08-05 esta metrica no se publico
# NI UNA VEZ: `count_ghosts` leia la fila por posicion (`row[0]`) contra una conexion con
# `row_factory=dict_row` y lanzaba KeyError en cada llamada, que el worker se tragaba en un
# warning. Ni siquiera el cero salia. En ese escenario —el real— la unica senal viva era
# exactamente esta: INSUFFICIENT_DATA CON accion. Con `notBreaching` o con `ignore` el sistema
# habria dicho "todo bien" durante todo el fallo.
# LO QUE ESTA ALARMA **NO** PROTEGE — medido el 2026-08-05, y es el quinto matiz de la lista
# de arriba. Se escribe aqui porque este archivo es donde vive la regla de decision, y porque
# ninguna de las aserciones de abajo puede capturarlo: es una limitacion de CloudWatch, no del
# recurso.
#
# 1. `insufficient_data_actions` solo dispara EN TRANSICION. Una metrica que no se publica
#    NUNCA desde el primer dia deja la alarma NACIDA en INSUFFICIENT_DATA y aparcada ahi: sin
#    transicion no hay correo, y el panel muestra un estado que se lee como "todavia no hay
#    datos". Esta alarma protege contra una metrica que SE PARA, no contra una que NUNCA
#    ARRANCA — que es la forma exacta que tuvo el bug de `count_ghosts` descrito arriba. La
#    unica senal de "nunca arranco" es el correo de `ok_actions` al salir POR PRIMERA VEZ de
#    INSUFFICIENT_DATA, asi que su AUSENCIA tras el `terraform apply` es el indicio. Por eso
#    la verificacion post-apply es un paso escrito de la tarea (`takab-docs/TASKS.md`, T-2.60.a
#    60.a): confirmar a los ~15 min que la alarma SALIO de INSUFFICIENT_DATA.
#
# 2. El correo tampoco dice el PORQUE. Cinco fallos distintos colapsan en el mismo silencio:
#    worker `notify` caido · `count_ghosts` lanzando · `build_ghost_gauge` dejando
#    `client=None` SIN excepcion (boto3 sin credenciales) · IAM sin `PutOpsMetrics` (o con la
#    condicion `cloudwatch:namespace` mal puesta) · `TAKAB_API_OPS_METRICS_ENABLED` sin poner
#    (es `false` por defecto; solo la enciende `deploy/cloud/deploy.sh`). Los cinco se ven
#    identicos desde CloudWatch; se distinguen en el EC2, no aqui.
#
# 3. Y el rastro local NO viaja. El `logger.warning` del worker se queda dentro del contenedor
#    (`deploy/cloud/docker-compose.yml`: `logging: driver: json-file`, sin agente CloudWatch ni
#    log group de aplicacion). Es una miga forense para quien ya entro por SSM, no una alerta.
#
# Y no se arregla eligiendo otro `treat_missing_data`: `breaching` si mandaria correo, pero
# AFIRMANDO que hay gabinetes fantasma cuando lo unico cierto es que nadie ha contado —la
# mentira que este mismo bloque rechaza arriba—; `notBreaching` e `ignore` lo taparian. La
# contramedida no es un valor distinto: es mirar UNA vez, despues del apply, que la alarma sale
# de INSUFFICIENT_DATA.
run "ghost_gateways_no_miente_cuando_no_sabe" {
  command = plan

  override_resource {
    target          = aws_sns_topic.ops_alerts
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ops-alerts"
    }
  }

  # El par namespace+metric_name es un contrato con el codigo: `ops/metrics.py` publica
  # METRIC_NAME = "GhostGatewaysAlive" en el namespace de `ops_metrics_namespace`
  # ("Takab/Ops"). Terraform no puede leer Python, asi que lo que se blinda aqui es el otro
  # extremo del cable: si divergen, la alarma vigila una metrica que nadie escribe y se queda
  # en INSUFFICIENT_DATA para siempre sin que nada parezca roto.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.ghost_gateways.namespace == "Takab/Ops"
      && aws_cloudwatch_metric_alarm.ghost_gateways.metric_name == "GhostGatewaysAlive"
    )
    error_message = "ghost_gateways debe vigilar Takab/Ops/GhostGatewaysAlive, exactamente lo que publica api/src/takab_api/ops/metrics.py (METRIC_NAME): si divergen, la alarma vigila una metrica que nadie escribe."
  }

  # Las dos mitades de la MISMA decision, juntas a proposito (ver cabecera del bloque).
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.ghost_gateways.treat_missing_data == "missing"
      && try(length(aws_cloudwatch_metric_alarm.ghost_gateways.insufficient_data_actions), 0) == 1
    )
    error_message = "ghost_gateways debe ser 'missing' CON insufficient_data_actions: la metrica es periodica (un valor por minuto, tambien el cero), asi que su silencio no significa 'hay fantasmas' ni 'no los hay' — significa que el worker que cuenta esta callado. 'breaching' afirmaria lo que no sabe, 'notBreaching' y 'ignore' lo taparian, y 'missing' sin accion deja la alarma muda (paso el 29-jul-2026)."
  }

  # `Maximum`, no `Minimum` ni `Average`: con ~5 muestras por periodo, el peor minuto manda.
  # `Minimum` fue justamente lo que trabo `gateway_offline` el 30-jul-2026 (se quedo con el 0
  # que cayo en el mismo minuto), y `Sum` haria que el VALOR dependiera de la cadencia de
  # publicacion — 5 muestras por periodo x 1 fantasma = 5, y el numero dejaria de leerse como
  # "gabinetes". Con `Maximum` el valor del correo es la magnitud real del problema.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.ghost_gateways.statistic == "Maximum"
      && aws_cloudwatch_metric_alarm.ghost_gateways.threshold == 0
      && aws_cloudwatch_metric_alarm.ghost_gateways.comparison_operator == "GreaterThanThreshold"
    )
    error_message = "ghost_gateways debe alarmar con Maximum > 0: un solo minuto con un fantasma dentro del periodo tiene que contar, y el valor publicado debe leerse como numero de gabinetes."
  }

  # La ventana es parte del contrato y esta escrita en el alarm_description (">1 h"): 12
  # periodos de 5 min, TODOS breaching (sin `datapoints_to_alarm` es N de N). Retirar un
  # gabinete que sigue enchufado y luego ir a desmontarlo es una secuencia legitima; lo que no
  # es legitimo es que ese estado se quede ahi. Una hora separa el tramite del olvido. Poner
  # `datapoints_to_alarm = 1` convertiria el tramite normal en una pagina.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.ghost_gateways.period == 300
      && aws_cloudwatch_metric_alarm.ghost_gateways.evaluation_periods == 12
      && aws_cloudwatch_metric_alarm.ghost_gateways.datapoints_to_alarm == null
    )
    error_message = "ghost_gateways debe exigir 12 periodos de 5 min SEGUIDOS (1 h sostenida, N de N): con menos, el tramite normal de retirar y luego ir a desmontar paginaria a alguien cada vez."
  }

  # Los otros dos estados. El OK importa tanto como el ALARM: sin el, nadie sabe si el
  # fantasma se resolvio restaurando el gabinete o desmontandolo, y el correo original se
  # queda como unica version de la historia.
  assert {
    condition = (
      length(aws_cloudwatch_metric_alarm.ghost_gateways.alarm_actions) == 1
      && length(aws_cloudwatch_metric_alarm.ghost_gateways.ok_actions) == 1
    )
    error_message = "ghost_gateways sin alarm_actions/ok_actions: cambiaria de estado sin avisar a nadie, que es el modo de fallo que esta alarma existe para evitar."
  }

  # Y que los tres estados apunten AL topic de on-call, no solo que exista un destinatario.
  # El correo de `ok_actions` es la UNICA senal de que la metrica arranco (ver la cabecera de
  # este bloque: una alarma nacida en INSUFFICIENT_DATA se queda ahi para siempre, sin
  # transicion y sin correo). Si alguien enruta ese aviso a otro topic, las aserciones de
  # arriba siguen verdes —cuentan 1 accion— y la unica senal de vida se pierde en silencio.
  # Contar destinatarios no es lo mismo que comprobar que es el correcto.
  assert {
    condition = (
      contains(aws_cloudwatch_metric_alarm.ghost_gateways.alarm_actions, aws_sns_topic.ops_alerts.arn)
      && contains(aws_cloudwatch_metric_alarm.ghost_gateways.ok_actions, aws_sns_topic.ops_alerts.arn)
      && contains(aws_cloudwatch_metric_alarm.ghost_gateways.insufficient_data_actions, aws_sns_topic.ops_alerts.arn)
    )
    error_message = "ghost_gateways debe mandar sus TRES estados al topic de on-call (aws_sns_topic.ops_alerts): con un destino equivocado la alarma queda verde y muda para quien esta de guardia."
  }
}

# --- [T-2.71] Por que NINGUNA alarma cambia aqui al llegar las ventanas -------
#
# T-2.71 anade la posibilidad de SILENCIAR alarmas durante un mantenimiento. La
# tentacion obvia era implementarlo aqui —"que la alarma no dispare mientras
# tanto"— y esta medido que las tres formas de hacerlo desde este archivo son
# peores que no hacer nada:
#
#   (a) Dejar de publicar la metrica. NO silencia: PAGINA. `gateway_offline`
#       esta en `breaching`, asi que el silencio de `Takab/Sensor/<gw>` ES la
#       condicion de alarma — 10 min y correo. Y `ghost_gateways` esta en
#       `missing` CON `insufficient_data_actions`, asi que su silencio tambien
#       manda correo. De las tres alarmas por gabinete, apagar la metrica pagina
#       en DOS y calla UNA. Exactamente al reves de lo que se pretende.
#
#   (b) `actions_enabled = false`. Deja la alarma apagada SIN FECHA DE CADUCIDAD.
#       Es un atributo gestionado por terraform (apagarlo por API es drift que el
#       siguiente apply revierte, o que nadie revierte), y nada en el sistema la
#       vuelve a encender: aqui no hay worker de cierre, a proposito.
#
#   (c) Cambiar `treat_missing_data` "solo mientras dure". No existe tal cosa: es
#       configuracion permanente del recurso, y ya fallo de cuatro maneras.
#
# LA SOLUCION VIVE FUERA DE TERRAFORM: una alarm mute rule creada por API
# (api/src/takab_api/ops/muting.py). Las razones, todas comprobables SIN
# credenciales en el modelo de servicio que trae el CLI instalado
# (.../botocore/data/cloudwatch/2010-08-01/service-2.json — ver
# `ops/muting.CLI_SERVICE_MODEL`):
#
#   1. `Schedule` declara `required = ["Expression", "Duration"]`. Una mute rule
#      NO PUEDE existir sin vencimiento; `actions_enabled = false` no tiene
#      ninguno. Esa asimetria es la razon decisiva.
#   2. `DeleteAlarmMuteRule`, literal: "any alarms that are currently being muted
#      by that rule are immediately unmuted. If those alarms are in an ALARM
#      state, their configured actions will trigger. This operation is
#      idempotent." Cerrar la ventana a mano hace que el correo pendiente SALGA.
#   3. `PutAlarmMuteRule` exige el permiso "on two types of resources: the alarm
#      mute rule resource itself, and each alarm that the rule targets" — o sea
#      que IAM vigila CADA objetivo. La via `actions_enabled` pasaria por
#      `PutMetricAlarm`, cuyo permiso ademas deja reescribir umbral, metrica y
#      acciones: radio de dano incomparable para lo mismo.
#
# LO QUE NO SE PUEDE AFIRMAR, y aqui se decia como si fuera cita textual de AWS:
# que al VENCER sola la ventana CloudWatch re-dispare las acciones silenciadas.
# Esa frase no esta en el modelo de servicio ni en ninguna doc legible offline —
# lo unico documentado es el re-disparo al BORRAR la regla (punto 2). Asi que se
# trata como que NO ocurre: una ventana que se deja expirar puede dejar una
# alarma en ALARM sin correo, igual que (b), con dos diferencias que siguen
# haciendo ganar a la mute rule: el dano esta acotado a la Duration (tope de la
# casa: 4 h) y la alarma sigue visible en ALARM. Consecuencia operativa: CERRAR
# la ventana, no dejarla expirar. Medirlo contra la cuenta real es HUMANO-AWS.
#
# COSTE HONESTO de esa decision: las mute rules son objetos efimeros creados por
# API, NO gestionados por terraform, asi que este archivo no puede asertar nada
# sobre ellas. La red de seguridad se reparte en dos sitios y conviene saber
# donde mirar:
#   - `infra/terraform/modules/database/tests/mute_rules_iam.tftest.hcl` — que la
#     politica IAM NO conceda PutAlarmMuteRule sobre las tres intocables
#     (`dlq_depth`, `iot_rule_errors`, `ghost_gateways`). Es la unica mitad que
#     terraform puede blindar, y se apoya en el punto 3 de arriba.
#   - `api/tests/ops/test_muting.py` — que el catalogo de lo silenciable se
#     DERIVE de este mismo archivo: una alarma nueva aqui sin clasificar alli
#     pone ese test en rojo. Por eso anadir una alarma a este modulo obliga a
#     decidir si se puede callar; el default seguro es NUNCA.
#
# La asercion de abajo fija lo unico que este archivo puede fijar: que las cuatro
# silenciables NO tocaron su `treat_missing_data` para "ayudar" al silenciador.
run "t271_no_debilito_ninguna_alarma_para_poder_silenciarla" {
  command = plan

  assert {
    condition = (
      aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].treat_missing_data == "breaching"
      && aws_cloudwatch_metric_alarm.sensor_mute["gw-test-0001"].treat_missing_data == "notBreaching"
      && aws_cloudwatch_metric_alarm.ec2_status.treat_missing_data == "breaching"
      && aws_cloudwatch_metric_alarm.ghost_gateways.treat_missing_data == "missing"
      && aws_cloudwatch_metric_alarm.wal_archive_stalled.treat_missing_data == "breaching"
    )
    error_message = "Alguna alarma cambio su treat_missing_data. Si el motivo fue 'para que no moleste durante un mantenimiento', la respuesta es NO: eso la debilita para siempre. El silencio acotado lo da una alarm mute rule (api/src/takab_api/ops/muting.py), que no puede existir sin Duration y que al BORRARLA desilencia en el acto disparando lo que quedara en ALARM."
  }

  # Y que las alarmas por gabinete siguen llamandose como el catalogo del API
  # cree. El nombre ES la frontera: si divergen, la ventana pide silenciar algo
  # que no existe (ruidoso pero seguro) y —peor— el guardia de intocables deja de
  # reconocerlas. `test_el_catalogo_conoce_los_nombres_reales_del_terraform`
  # vigila el otro extremo del mismo cable.
  assert {
    condition = (
      aws_cloudwatch_metric_alarm.gateway_offline["gw-test-0001"].alarm_name == "takab-dev-gateway-offline-gw-test-0001"
      && aws_cloudwatch_metric_alarm.sensor_mute["gw-test-0001"].alarm_name == "takab-dev-sensor-mudo-gw-test-0001"
    )
    error_message = "Cambio el nombre de una alarma silenciable: ALARM_CATALOG (api/src/takab_api/ops/muting.py) quedaria huerfano y la ventana silenciaria un nombre inexistente."
  }
}
