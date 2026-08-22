# Observabilidad hacia HUMANOS (hallazgo A-4 de la auditoria de cierre).
#
# Antes de este modulo NO existia ni una alarma ni un topic SNS: un gabinete
# caido, una DLQ creciendo o la nube muerta eran solo un color en la UI. Aqui
# vive el minimo honesto: un topic de on-call por email + alarmas de los
# sintomas que la infra ya emite sin instrumentar la aplicacion.
#
# Fuera de alcance (documentado en el runbook de auditoria): bateria por
# gabinete y 5xx de la API requieren publicar metricas desde la aplicacion
# (device_health/Caddy) — siguiente rebanada de A-4.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# [T-2.162] LO QUE HAY QUE HACER, pegado a cada aviso.
#
# `alarm_description` es el UNICO texto nuestro que viaja en el correo que compone
# SNS. Todo lo demas —nombre, umbral, dimensiones— lo pone AWS. Asi que si el
# "acusa aqui" no esta aqui, no esta en ningun sitio que el destinatario vea.
#
# Medido el 2026-08-22 en el ensayo cronometrado de T-2.78: quien recibio el aviso
# acababa de acunar la credencial, abrir la pagina y acusar otro aviso veinte
# minutos antes, y aun asi pregunto cual era "el codigo". El runbook resolvia esto
# suponiendo que la persona tiene el marcador y sabe usarlo; el ensayo refuto esa
# suposicion con el caso mas favorable posible.
#
# VACIO SI NO HAY SUSCRIPTOR HTTPS, y no es un detalle: sin el, ningun aviso llega
# a la base. La pagina existiria y no habria nada suyo que atender. Mandar alli a
# alguien de guardia a las 3 a.m. es peor que no decir nada.
#
# El plazo va en MINUTOS: "900 s" obliga a dividir a quien acaba de despertarse.
locals {
  ack_url = var.ops_alert_https_endpoint == "" ? "" : replace(var.ops_alert_https_endpoint, "/sns", "/ack")

  ack_sufijo = var.ops_alert_https_endpoint == "" ? "" : format(
    " --- ACUSA RECIBO en %s (tu credencial de guardia; tienes %d min). Sin acuse queda constancia de que nadie lo atendio.",
    local.ack_url,
    floor(var.ops_ack_deadline_s / 60),
  )

  # [T-2.145] La ventana de `ec2_cpu` se declara UNA vez y el texto de la alarma la
  # deriva. Estaba tecleada en los dos sitios y ya habia divergido: el correo prometia
  # "15 min" y la configuracion exigia 25.
  ec2_cpu_periodo_s   = 300
  ec2_cpu_periodos    = 5
  ec2_cpu_ventana_min = local.ec2_cpu_periodo_s * local.ec2_cpu_periodos / 60
}

resource "aws_sns_topic" "ops_alerts" {
  name = "takab-dev-ops-alerts"

  # [T-2.78.a] REGISTRO DE ENTREGA. AWS solo lo ofrece para Firehose, SQS,
  # Lambda, HTTPS y endpoints de aplicacion: `email` y `email-json` NO estan en
  # esa lista (https://docs.aws.amazon.com/sns/latest/dg/sns-topic-attributes.html),
  # y por eso hasta hoy no habia forma de saber a que hora salio un aviso sin
  # mirar el buzon de alguien. Estos tres atributos son la mitad de AWS de esa
  # evidencia; la otra mitad —la fila con hora— la escribe el suscriptor HTTPS
  # en `ops_alert_notices`. Con `ops_alert_https_endpoint` vacio quedan en null y
  # el apply de hoy no cambia.
  http_success_feedback_role_arn    = local.https_enabled ? aws_iam_role.sns_delivery_logs[0].arn : null
  http_failure_feedback_role_arn    = local.https_enabled ? aws_iam_role.sns_delivery_logs[0].arn : null
  http_success_feedback_sample_rate = local.https_enabled ? 100 : null
}

# La suscripcion por email exige CONFIRMACION manual (AWS manda un correo con
# un link): el apply no termina el trabajo hasta que el humano confirma.
resource "aws_sns_topic_subscription" "ops_email" {
  topic_arn = aws_sns_topic.ops_alerts.arn
  protocol  = "email"
  endpoint  = var.ops_alert_email
}

# --- [T-2.78.a] El suscriptor que SI deja rastro ----------------------------------
#
# El correo del on-call sigue siendo el canal que despierta a la persona; esto no
# lo sustituye, lo AUDITA. El mismo mensaje llega a la API, que lo verifica y
# escribe una fila con hora — y de ahi salen el acuse humano y, sobre todo, la
# fila del silencio cuando nadie contesta.
#
# `endpoint_auto_confirms = true` porque el endpoint confirma solo. Y lo hace SIN
# visitar el `SubscribeURL` que llega en el cuerpo: reconstruye la llamada con el
# host de la region de ESTE topic y con este mismo ARN, y del cuerpo toma solo el
# `Token`. La razon esta en `api/src/takab_api/ops/alerts.py`, y no es teorica:
# un suscriptor HTTPS que sigue las URLs del cuerpo es un cliente HTTP a las
# ordenes de cualquiera desde DENTRO de la VPC.
#
# Vacio ⇒ no se crea nada y el apply de hoy no cambia (patron de `push/` y de la
# identidad de dominio de T-2.78.b).
locals {
  https_enabled = var.ops_alert_https_endpoint != ""
}

resource "aws_sns_topic_subscription" "ops_https" {
  count = local.https_enabled ? 1 : 0

  topic_arn              = aws_sns_topic.ops_alerts.arn
  protocol               = "https"
  endpoint               = var.ops_alert_https_endpoint
  endpoint_auto_confirms = true
  raw_message_delivery   = false # el sobre firmado ENTERO: sin el no hay firma que verificar
}

data "aws_iam_policy_document" "sns_delivery_logs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["sns.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sns_delivery_logs" {
  count = local.https_enabled ? 1 : 0

  name               = "takab-dev-sns-delivery-logs"
  assume_role_policy = data.aws_iam_policy_document.sns_delivery_logs_assume.json
}

# Los permisos EXACTOS que la doc de SNS pide para el registro de entrega. No es
# un `logs:*`: este rol lo asume un servicio de AWS y lo unico que tiene que
# poder hacer es escribir el registro de sus propias entregas.
resource "aws_iam_role_policy" "sns_delivery_logs" {
  count = local.https_enabled ? 1 : 0

  name = "takab-dev-sns-delivery-logs"
  role = aws_iam_role.sns_delivery_logs[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:PutMetricFilter",
        "logs:PutRetentionPolicy",
      ]
      Resource = "*"
    }]
  })
}

# --- DLQ con mensajes = pipeline envenenado o roto (E3/O1) -----------------------
# La ingesta rechaza a DLQ con razon tipificada; que la DLQ tenga UN mensaje ya
# es accionable.
#
# [T-2.145] `notBreaching`, y esta vez el codigo lo obedece: hasta el 2026-08-22 este
# comentario razonaba `notBreaching` mientras la linea de abajo decia `breaching`. Se
# resolvio HACIA EL COMENTARIO, que es el que traia el argumento:
#
#   Lo vigilado es la PRESENCIA de mensajes, y la ausencia de datapoints no puede
#   esconderla. SQS solo publica metricas de colas con actividad reciente, asi que una
#   DLQ sana —vacia e inactiva, su estado normal— deja de emitir; con `breaching` eso
#   alarmaba sobre el estado BUENO. Al reves no hay hueco: un mensaje que entra ES
#   actividad y fuerza el datapoint. No se puede tener mensajes sin metrica.
resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  for_each = var.dlq_names

  alarm_name          = "takab-dev-dlq-${each.key}"
  alarm_description   = "DLQ '${each.value}' con mensajes: la ingesta esta rechazando payloads (ver MessageAttributes.reason) o un consumer agoto reintentos.${local.ack_sufijo}"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = each.value }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  ok_actions          = [aws_sns_topic.ops_alerts.arn]
}

# --- La instancia EC2 (DB + nube co-locada) ---------------------------------------
# missing=breaching A PROPOSITO: una instancia parada deja de emitir metricas y
# eso DEBE avisar (incluso `make cloud-stop` deliberado: la nube caida es un
# evento operativo; SNS notifica solo la transicion, un correo por parada).
resource "aws_cloudwatch_metric_alarm" "ec2_status" {
  alarm_name          = "takab-dev-ec2-status-check"
  alarm_description   = "La instancia de la nube co-locada falla sus status checks o dejo de reportar (¿parada?): API, workers y DB viven ahi.${local.ack_sufijo}"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  dimensions          = { InstanceId = var.instance_id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  ok_actions          = [aws_sns_topic.ops_alerts.arn]
}

# [T-2.145] `notBreaching`: MISMA instancia y MISMA ausencia que `ec2_status`, que ya
# pagina por ella. Con `breaching` un apagon mandaba DOS correos por el mismo corte, y el
# segundo nombraba la causa EQUIVOCADA — "CPU sostenida" cuando lo que pasa es que la
# maquina no esta. Es el mismo reparto que `sensor_mute` hace del lado del gabinete: cada
# alarma dice UNA cosa. Dos correos por un corte ensenan a leer por encima, y el dia que
# lleguen dos por causas DISTINTAS nadie los distinguira.
#
# La ventana se DERIVA de los periodos: el texto decia "15 min" y la configuracion daba
# 25 (5 x 300 s). Tecleado dos veces, divergido una.
resource "aws_cloudwatch_metric_alarm" "ec2_cpu" {
  alarm_name          = "takab-dev-ec2-cpu-sostenida"
  alarm_description   = "CPU > 90% sostenida ${local.ec2_cpu_ventana_min} min en la instancia co-locada: riesgo de lag de ingesta y OOM (leccion t4g.small).${local.ack_sufijo}"
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  dimensions          = { InstanceId = var.instance_id }
  statistic           = "Average"
  period              = local.ec2_cpu_periodo_s
  evaluation_periods  = local.ec2_cpu_periodos
  threshold           = 90
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  ok_actions          = [aws_sns_topic.ops_alerts.arn]
}

# --- Errores de las reglas IoT (ingesta rota antes de SQS) ------------------------
# Todo evento en ese log group ES un error de regla (es el error_action):
# patron vacio = contar cada linea.
resource "aws_cloudwatch_log_metric_filter" "iot_rule_errors" {
  name           = "takab-dev-iot-rule-errors"
  log_group_name = var.iot_rule_errors_log_group
  pattern        = ""

  metric_transformation {
    name      = "IoTRuleErrors"
    namespace = "Takab/Ops"
    value     = "1"
  }
}

# [T-2.145] `notBreaching`. El metric filter de arriba no declara `default_value`, asi que
# SIN eventos que casen no publica NADA — que es exactamente el sistema funcionando. Con
# `breaching`, una nube sana quedaba en ALARMA permanente, y eso no es ruido: es MUDEZ.
# SNS solo notifica TRANSICIONES, y esta alarma transiciono UNA sola vez en toda su vida
# (OK->ALARM el 2026-08-08 09:39 CST) y ahi seguia clavada 14 dias despues, medido el
# 2026-08-22. Es decir: la alarma que vigila que no se pierdan mensajes del edge antes de
# la ingesta llevaba dos semanas incapaz de avisar de un error real, porque ya estaba
# gritando por no tener ninguno.
#
# Lo que `notBreaching` silencia —que las reglas dejen de correr DEL TODO— tiene su propio
# vigilante: si nada llega de los gabinetes, `gateway_offline` pagina por la ausencia del
# latido. Mismo reparto que `sensor_mute`.
resource "aws_cloudwatch_metric_alarm" "iot_rule_errors" {
  alarm_name          = "takab-dev-iot-rule-errors"
  alarm_description   = "Las reglas IoT estan tirando errores al enrutar hacia SQS: mensajes del edge se estan perdiendo antes de la ingesta.${local.ack_sufijo}"
  namespace           = "Takab/Ops"
  metric_name         = "IoTRuleErrors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  ok_actions          = [aws_sns_topic.ops_alerts.arn]

  depends_on = [aws_cloudwatch_log_metric_filter.iot_rule_errors]
}

# --- Sensor MUDO: gabinete VIVO pero sin datos del sismografo (T-1.66) ------------
# El agujero que costo 15 h de ceguera el 14/07/2026: el Shake fuera de la red, el Pi
# latiendo cada minuto y la flota "OPERATIVA". `gateway_offline` no lo ve (hay enlace)
# y la UI solo lo mostraba a quien mirase la pantalla. Un sismografo mudo es la
# perdida TOTAL de la deteccion local: es exactamente lo que tiene que despertar a
# alguien de madrugada.
#
# `seedlink_lag_s` es la ANTIGUEDAD del dato mas reciente (T-1.65). Un stream sano no
# pasa de ~8 s (duracion del registro miniSEED a 100 sps), asi que 120 s es inequivoco
# y deja fuera cualquier hipo de reconexion. missing=notBreaching: si cae el gabinete
# ENTERO, quien pagina es `gateway_offline` — cada alarma dice UNA cosa.
resource "aws_cloudwatch_metric_alarm" "sensor_mute" {
  for_each = toset(var.paged_gateways)

  alarm_name          = "takab-dev-sensor-mudo-${each.value}"
  alarm_description   = "El gabinete ${each.value} TIENE ENLACE pero su sismografo lleva >120 s sin entregar muestras: SIN DETECCION LOCAL, el sitio esta ciego. Revisar el Raspberry Shake (alimentacion, cable de red, puerto del switch): el Pi 5 reconecta solo en cuanto vuelva a la LAN.${local.ack_sufijo}"
  namespace           = "Takab/Sensor"
  metric_name         = each.value
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 120
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  ok_actions          = [aws_sns_topic.ops_alerts.arn]
}

# PRESENCIA DEL GABINETE = "¿sigue llegando su heartbeat?".
#
# Esta alarma vivio sobre `Takab/Fleet` (metrica POR EVENTO: 1 al conectar, 0 al perder el
# enlace via LWT) y NUNCA pudo funcionar bien ahi. Se agotaron los cuatro valores de
# `treat_missing_data` contra produccion, en este orden, y cada uno fallo distinto:
#
#   notBreaching -> el silencio se lee como SALUD. Disparaba con el 0 del LWT y ~15 min
#                   despues se auto-declaraba OK: correo de "todo bien" con el gabinete
#                   muerto. Los 5 cortes de julio-2026 (24, 27 x2, 28); el del 28 mintio >15 h.
#   missing      -> INSUFFICIENT_DATA y MUDA. NO retiene el estado pese al nombre
#                   (verificado: se forzo ALARM y volvio a INSUFFICIENT_DATA en ~1 min).
#   ignore       -> retiene, pero por eso mismo se TRABA: el 30-jul el 0 del LWT y el 1 de
#                   la reconexion cayeron en el MISMO minuto, `Minimum` se quedo con el 0
#                   y sin datapoints nuevos la alarma paso 4 h gritando "caido" con el
#                   gabinete sano. La mentira inversa, igual de inutil.
#   breaching    -> alarmaria SIEMPRE: un gabinete sano tampoco emite entre transiciones.
#
# La raiz no es el parametro: un desconectar+reconectar dentro de una misma ventana es
# AMBIGUO por construccion, y CloudWatch no sabe expresar "el ultimo valor".
#
# La metrica correcta ya existia. `Takab/Sensor/<gw>` se publica en CADA heartbeat (1/min,
# regla `takab_dev_seedlink_lag_metric`): su PRESENCIA es la senal de vida, con independencia
# de su VALOR — que es justo lo que vigila `sensor_mute`. Dos alarmas sobre la misma metrica,
# cada una mirando una cosa distinta. Sobre una metrica PERIODICA el silencio SI significa
# una sola cosa, `breaching` es correcto, y la alarma vuelve a OK sola en cuanto reaparecen
# muestras: no puede mentir ni trabarse.
#
# Coste aceptado: deteccion en ~10 min en vez de ~1 min. Esta alarma NO esta en el camino de
# actuacion (SASMEX->sirena es local y determinista, reglas de oro 1 y 2); solo sirve para
# que un humano vaya a ver el gabinete, y para eso 10 minutos son lo mismo que uno.
resource "aws_cloudwatch_metric_alarm" "gateway_offline" {
  for_each = toset(var.paged_gateways)

  alarm_name          = "takab-dev-gateway-offline-${each.value}"
  alarm_description   = "El gabinete ${each.value} lleva >10 min sin enviar un solo heartbeat (llegan 1/min): perdio el enlace con IoT Core, se quedo sin energia o se colgo. La proteccion local sigue (regla de oro 2), pero hay que ir a verlo. Vuelve a OK sola en cuanto reaparezcan los heartbeats.${local.ack_sufijo}"
  namespace           = "Takab/Sensor"
  metric_name         = each.value
  statistic           = "SampleCount"
  period              = 300
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"

  # `insufficient_data_actions` tambien pagina: con `breaching` este estado no deberia ser
  # de reposo, pero si alguna vez la alarma se queda ahi, "no se nada de este gabinete" es
  # tan accionable como "esta caido" (regla de oro 7). Callar nunca es la opcion segura.
  alarm_actions             = [aws_sns_topic.ops_alerts.arn]
  ok_actions                = [aws_sns_topic.ops_alerts.arn]
  insufficient_data_actions = [aws_sns_topic.ops_alerts.arn]
}

# [T-2.60.a] Un gabinete RETIRADO que sigue reportando.
#
# La contradiccion: la organizacion lo cree dado de baja y el aparato sigue
# hablando. Paso el 2026-08-04 y duro horas invisible; se supo cuando el operador
# pregunto por su estacion, no porque el sistema dijera nada. La consola ya lo
# pinta en rojo (T-2.60.a), pero eso exige que alguien mire la pantalla: esta
# alarma es la mitad que no depende de que haya un humano delante.
#
# La metrica la publica el worker `notify` cada 60 s, SIEMPRE, incluido el cero.
# Eso es deliberado y cambia el significado de "sin datos": aqui la ausencia ya
# no es ambigua, es que el worker esta caido.
#
# Por eso `treat_missing_data` NO es "breaching" como en gateway-offline. Alli la
# ausencia de heartbeat ES la condicion vigilada; aqui la ausencia de metrica no
# dice nada sobre fantasmas, solo que nos hemos quedado ciegos. Se deja en
# "missing" y la ceguera se pagina por `insufficient_data_actions`, siguiendo el
# mismo principio de la casa: callar nunca es la opcion segura (regla de oro 7).
#
# 12 periodos de 5 min = 1 h sostenida. Retirar un gabinete que sigue enchufado y
# luego ir a desmontarlo es una secuencia legitima; lo que no es legitimo es que
# ese estado se quede ahi. Una hora separa el tramite del olvido.
# --- [T-2.72] El archivado del WAL se atasco: el RPO deja de estar acotado -----
#
# Esta es la alarma de la que SE DERIVA el RPO, no una alarma sobre el RPO. La
# diferencia importa: "RPO <= 15 min" no sale de que `archive_timeout` valga 60 s
# —eso describe el caso feliz— sino de que la edad del archivado no pueda pasar de
# `wal_archive_max_age_s` sin que suene un telefono. El numero publicado
# (`output.rpo_seconds`) se calcula de los atributos de ESTE recurso:
#
#     RPO = threshold + period * evaluation_periods
#
# El segundo termino no es un detalle: CloudWatch no avisa al cruzar el umbral,
# avisa tras `evaluation_periods` periodos SEGUIDOS por encima. Durante esos
# minutos se sigue acumulando WAL que no esta en S3.
#
# QUE PUBLICA LA METRICA: un cron en la instancia (documento SSM de
# `modules/database`) que cada 60 s lee `pg_stat_archiver.last_archived_time` y
# publica su antiguedad. SIEMPRE, tambien cuando vale 0.
#
# POR QUE `breaching` Y NO `missing`, que fue lo correcto en `ghost_gateways`:
# alli la ausencia de la metrica no decia nada sobre fantasmas —solo que el que
# contaba estaba callado— y afirmar "hay fantasmas" habria sido afirmar lo que no
# se sabe. Aqui la ausencia SI es la condicion vigilada, y por una razon precisa:
# lo que esta alarma mide no es "cuanto WAL falta" sino "hasta que instante se
# puede recuperar". Cuando la metrica desaparece —DB que no responde, publicador
# muerto, instancia caida— ese instante pasa a ser DESCONOCIDO, y un RPO
# desconocido es, operativamente, un RPO ilimitado. "No lo se" y "esta roto" son
# aqui la misma frase.
#
# Con `missing` o `notBreaching` toda la derivacion de arriba seria falsa: el
# publicador muere, la metrica se apaga, la alarma calla para siempre y el RPO
# real deja de tener techo mientras el `terraform output` sigue diciendo 900.
#
# COSTE ACEPTADO: parar la instancia a proposito (`make cloud-stop`, un ensayo de
# restore, una ventana de mantenimiento) hace sonar esta alarma. Se acepta, y por
# eso esta clasificada como INTOCABLE en `api/src/takab_api/ops/muting.py` — la
# razon larga vive alli.
#
# LO QUE ESTA ALARMA VIGILA POR ACCIDENTE, y conviene saberlo: el disco. Un
# archivado atascado impide que Postgres recicle su WAL, asi que `pg_wal` crece
# ~16 MiB/min y en menos de dos dias llena el volumen de 40 GiB que comparte con
# los datos. Esta alarma llega mucho antes (900 s) y por eso el riesgo esta
# cubierto, pero lo esta por la via indirecta: mide el archivado, no el disco. La
# alarma de espacio libre DE VERDAD exige el agente de CloudWatch en la instancia
# (`disk_used_percent` no existe en las metricas nativas de EC2) y no cabia en
# esta tarea. Queda FICHADA: sin ella, cualquier otra causa de disco lleno —un log
# desbocado, una restauracion a base lateral— sigue siendo invisible.
#
# TAMPOCO vigila el BACKUP BASE. Mide la cadena de WAL, no su ancla: un
# `barman-cloud-backup` que falle cada semana no mueve esta metrica ni un segundo.
# Fichado con su forma: publicar `BaseBackupAgeSeconds` una vez al dia desde
# `barman-cloud-backup-list` y alarmar por encima de
# `base_backup_interval_days * chain_margin`.
resource "aws_cloudwatch_metric_alarm" "wal_archive_stalled" {
  alarm_name          = "takab-dev-wal-archivado-atascado"
  alarm_description   = "El archivado continuo de WAL lleva demasiado tiempo sin avanzar (o no se sabe cuanto): a partir de aqui, un desastre pierde todo lo escrito desde el ultimo segmento que llego a S3. Y HAY UN RELOJ MAS CORTO QUE EL DEL RPO: con el archivado atascado, Postgres NO recicla su WAL y `pg_wal` crece ~16 MiB por minuto (archive_timeout fuerza segmentos de tamaño completo) sobre el mismo volumen de 40 GiB donde viven los datos — menos de dos dias hasta llenar el disco y tumbar la DB. Lo primero es mirar el espacio libre en /data; despues `pg_stat_archiver` (last_failed_time/failed_count dicen si el archive_command falla en bucle) y /var/log/takab-pitr.log. La proteccion local del gabinete no depende de esto (reglas de oro 1 y 2); lo que esta en riesgo es la memoria de la nube y, en 48 h, la nube entera.${local.ack_sufijo}"
  namespace           = "Takab/Ops"
  metric_name         = "WalArchiveAgeSeconds"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 5
  threshold           = var.wal_archive_max_age_s
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "breaching"

  # Los tres estados. El OK es la unica senal de que el archivado se recupero — y,
  # tras el primer apply, la unica senal de que la metrica llego a publicarse
  # alguna vez (la leccion de `ghost_gateways`: una alarma nacida en
  # INSUFFICIENT_DATA se queda ahi sin transicion y sin correo).
  alarm_actions             = [aws_sns_topic.ops_alerts.arn]
  ok_actions                = [aws_sns_topic.ops_alerts.arn]
  insufficient_data_actions = [aws_sns_topic.ops_alerts.arn]
}

# --- [T-2.72.b] El ANCLA de la cadena: un backup base que dejo de tomarse ------
#
# Esto es lo que la alarma de arriba dejaba FICHADO en su propio comentario:
# `wal_archive_stalled` mide la cadena de WAL, no su ancla. Un `barman-cloud-backup`
# que falle todas las semanas no mueve `WalArchiveAgeSeconds` ni un segundo — el
# archivado sigue impecable — y la cadena esta rota igual, porque un WAL sin
# backup base no arranca. Eso no se descubre hasta el dia del restore, que es EL
# modo de fallo que la Fase 2.6 existe para eliminar
# (`RUNBOOK-backup-restore-db.md:3`: "RESTORE JAMAS PROBADO").
#
# EL UMBRAL SALE DE LAS VARIABLES DE RETENCION, no de un numero elegido aqui:
# `base_backup_interval_days * chain_margin` dias, calculado en `modules/database`
# (que es donde viven esas cifras y donde se programa el cron del backup base) y
# recibido entero. Es el MISMO producto que aparece en la desigualdad que mantiene
# viva la cadena, `wal_retention_days >= intervalo * margen`. Con un literal aqui,
# cambiar la politica de retencion dejaria a la alarma vigilando una cadena que ya
# no es la que S3 poda.
#
# LO QUE ESTE UMBRAL NO ES —y es un limite declarado, no un descuido—: un aviso
# TEMPRANO. Cuando la edad del ancla lo supera ya han fallado `margen` backups
# base seguidos, y con los valores por defecto ese producto (7 x 2 = 14 dias) es
# EXACTAMENTE `wal_retention_days`: el correo llega justo cuando la ventana de
# recuperacion se cierra. [T-2.141] Eso es lo que resolvio `base_backup_late`,
# aqui abajo: el aviso a `intervalo` dias. Esta alarma se queda como lo que
# siempre fue —LA ULTIMA LINEA— y su correo ya no tiene que hacer de las dos.
#
# `breaching`, Y NO ES LA RESPUESTA DE `ghost_gateways`. Alli el silencio se
# clasifico `missing` porque la ausencia de la metrica no decia nada sobre
# fantasmas. Aqui si dice, por dos razones independientes:
#   (a) lo que se mide no es "cuantos backups hay" sino "hasta que punto se puede
#       recuperar". Sin metrica, la edad del ancla es DESCONOCIDA — y un ancla
#       desconocida es, para un restore, lo mismo que no tener ancla. Igual que en
#       `wal_archive_stalled`: "no lo se" y "esta roto" son aqui la misma frase;
#   (b) el que publica y el que respalda son EL MISMO HOST. Si esto calla, el
#       `barman-cloud-backup` de las 04:00 tampoco se esta ejecutando. El silencio
#       no es solo ceguera: es tambien la averia.
#
# NACE EN ALARM, a proposito. El dia del primer apply todavia no existe ningun
# backup base (el primero se toma en T-2.74) y el publicador lo dice con la verdad:
# mide la edad desde que se configuro el PITR. Asi que la alarma dispara, y esta
# BIEN que dispare. El correo de OK al completarse el primer backup base es el
# ACUSE de que la cadena consiguio ancla — y es la unica senal automatica y barata
# de que el respaldo base funciono alguna vez.
resource "aws_cloudwatch_metric_alarm" "base_backup_missing" {
  alarm_name          = "takab-dev-backup-base-ausente"
  alarm_description   = "El ultimo backup base de la cadena PITR es demasiado viejo (o no se sabe cuanto): a partir de aqui los WAL archivados NO se pueden aplicar sobre nada y el respaldo continuo no sirve para restaurar. Han fallado varios `barman-cloud-backup` seguidos sin que nada mas lo notara — el archivado de WAL sigue impecable, por eso su alarma esta en verde. Mirar /var/log/takab-pitr.log en la instancia y ejecutar `/opt/takab/bin/takab-base-backup.sh` a mano; despues comprobar con `barman-cloud-backup-list`. Si esta alarma aparece el dia del despliegue inicial es CORRECTO: todavia no se ha tomado el primer backup base (T-2.74). La proteccion local del gabinete no depende de esto (reglas de oro 1 y 2); lo que esta en riesgo es poder recuperar la nube.${local.ack_sufijo}"
  namespace           = "Takab/Ops"
  metric_name         = "BaseBackupAgeSeconds"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.base_backup_max_age_s
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "breaching"

  alarm_actions             = [aws_sns_topic.ops_alerts.arn]
  ok_actions                = [aws_sns_topic.ops_alerts.arn]
  insufficient_data_actions = [aws_sns_topic.ops_alerts.arn]
}

# --- [T-2.141] El AVISO, que es lo que a la de arriba le faltaba ---------------
#
# La alarma de arriba dispara a `intervalo * margen`. Con los valores por defecto
# eso es 7 x 2 = 14 dias, que es EXACTAMENTE `wal_retention_days`: para cuando
# llega el correo, la ventana de recuperacion ya se cerro. Como ultima linea es
# correcta —dice "ya no puedes recuperar"— pero como aviso no sirve, y el fallo
# que hay que cazar es EL PRIMER backup base que falla, no el decimocuarto dia.
#
# EL UMBRAL ES EL MISMO INTERVALO SIN EL MARGEN, y no es una eleccion: es la
# definicion del hecho. El cron corre en `*/N` del dia del mes, asi que el hueco
# entre dos backups base nunca pasa de `N` dias. El primer instante en que la edad
# del ancla SUPERA `N` dias es, exactamente, el primer `barman-cloud-backup` que
# no se completo. Lo calcula `modules/database` (`base_backup_warn_age_s`), donde
# viven las cifras y donde se programa ese cron; aqui solo baja resuelto.
#
# POR QUE SON DOS Y NO UNA. No dicen lo mismo ni piden lo mismo:
#   AVISO (esta)  : "fallo UN backup base; quedan `intervalo * (margen - 1)` dias
#                    de ventana" —7 con los valores por defecto—. Accion: mirar el
#                    log y relanzar el backup a mano. Barato, reversible.
#   ULTIMA LINEA  : "fallaron `margen` seguidos; la ventana ya se cerro". Accion:
#                    asumir que hoy no hay restore y reconstruir la cadena entera.
# Una sola alarma solo puede decir una de las dos cosas. Fundirlas obligaria a
# elegir entre avisar tarde (lo de antes) o gritar "no puedes recuperar" cuando
# todavia se puede — que es peor, porque provoca la reaccion cara.
#
# SEVERIDAD DISTINGUIDA, por donde de verdad se lee. Este modulo tiene UN solo
# topic SNS y ninguna alarma lleva tags. Un segundo topic significaria otra
# suscripcion de correo que alguien tiene que confirmar a mano, y una alarma que
# no avisa hasta que se confirme es peor que no tenerla. Asi que la severidad
# viaja por el NOMBRE —que es el asunto del correo, "atrasado" contra "ausente"—
# y por la primera palabra de la descripcion. Lo vigila un test, no este parrafo.
#
# `missing`, Y ES EL ARGUMENTO DE `db_disk_space`, NO EL DE SU PROPIA HERMANA.
# Su hermana eligio `breaching` porque mide "hasta donde se puede recuperar" y un
# ancla desconocida es, para un restore, lo mismo que no tener ancla. Aqui aplica
# el otro: el correo de ESTA alarma AFIRMA UNA MEDIDA —"se paso el intervalo: un
# backup base fallo"— y ademas afirma una TRANQUILIDAD —"todavia quedan dias de
# ventana"—. Sin datapoint ninguna de las dos cosas existe, y la segunda seria
# ademas FALSA: lo que no se sabe puede ser mucho peor que un backup fallido.
# Y hay una razon que ninguna hermana tiene, porque solo existe en un PAR: el
# silencio de esta metrica YA ESTA CUBIERTO, por la misma serie, el mismo
# publicador y el mismo host — la alarma de arriba, en `breaching`. Poner
# `breaching` aqui tambien no anadiria ni un gramo de vigilancia; mandaria DOS
# correos por el mismo silencio y el de este INFRAVALORARIA lo que pasa. Que la
# hermana siga en `breaching` sobre la misma metrica lo comprueba un test: el dia
# que alguien la relaje, este `missing` deja de ser una decision y pasa a ser una
# ceguera.
#
# EL DIA QUE SE CREA nace en INSUFFICIENT_DATA y NO manda correo — porque
# `insufficient_data_actions` solo dispara al TRANSITAR y ese es su estado
# inicial. Aqui eso es seguro, y solo aqui: durante esa ventana su hermana en
# `breaching` esta en ALARM diciendo exactamente lo que hay que oir. El
# publicador emite la primera edad EN EL ACTO al final del `pitr_setup.sh` (la
# leccion de `T-2.72.c`), asi que en cuanto llega ese datapoint —edad medida desde
# que se configuro el PITR, o sea casi cero— la alarma TRANSITA a OK y ese correo
# de OK es el acuse de que nacio viva. Si ese correo no llega nunca, eso es el
# hallazgo: la metrica no se esta publicando.
resource "aws_cloudwatch_metric_alarm" "base_backup_late" {
  alarm_name          = "takab-dev-backup-base-atrasado"
  alarm_description   = "AVISO: se paso el intervalo del backup base sin que se completara ninguno — ha fallado el PRIMERO, y todavia se puede recuperar. Esto NO es la alarma de cadena rota (`takab-dev-backup-base-ausente`): aqui queda ventana de sobra para arreglarlo, y arreglarlo es barato. Mirar /var/log/takab-pitr.log en la instancia y ejecutar `/opt/takab/bin/takab-base-backup.sh` a mano; despues comprobar con `barman-cloud-backup-list` que el ancla se movio, y esperar el correo de OK de esta misma alarma. Si se ignora, el siguiente aviso sera el de cadena rota y para entonces la ventana de recuperacion se habra cerrado. La proteccion local del gabinete no depende de esto (reglas de oro 1 y 2); lo que esta en riesgo es poder recuperar la nube.${local.ack_sufijo}"
  namespace           = "Takab/Ops"
  metric_name         = "BaseBackupAgeSeconds"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.base_backup_warn_age_s
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "missing"

  alarm_actions             = [aws_sns_topic.ops_alerts.arn]
  ok_actions                = [aws_sns_topic.ops_alerts.arn]
  insufficient_data_actions = [aws_sns_topic.ops_alerts.arn]
}

# --- [T-2.72.c] El DISCO, que hasta hoy solo se vigilaba POR ACCIDENTE ---------
#
# El otro fichado del comentario de `wal_archive_stalled`. Con el archivado
# atascado Postgres no recicla su WAL: `pg_wal` crece ~16 MiB/min sobre el mismo
# volumen de 40 GiB donde vive el datadir, y en menos de dos dias llena el disco y
# tumba la DB. Esa via ya estaba cubierta —la alarma de atasco llega a los 900 s,
# muchisimo antes que las 48 h— pero INDIRECTAMENTE: mide el archivado, no el
# disco. Cualquier otra causa de disco lleno (un log desbocado, un restore a base
# lateral, imagenes de docker acumuladas) seguia siendo invisible.
#
# `disk_used_percent` no existe en las metricas nativas de EC2 —AWS/EC2 solo trae
# CPU, red, EBS y status checks: el hipervisor no ve dentro del filesystem—, asi
# que o se instala el agente de CloudWatch o se publica desde la instancia. Se
# publica desde la instancia, por el cron que ya existe (`/etc/cron.d/takab-pitr`,
# documento SSM de `modules/database`): un demonio mas en la maquina que sostiene
# la DB, la API y los workers es un demonio mas que puede morir en silencio.
#
# `missing` Y NO `breaching`, al reves que su vecina de arriba, y la razon es la
# de `ghost_gateways` palabra por palabra: lo que esta alarma AFIRMA en su correo
# es una medida —"el disco de /data paso del N %"—. Si no hay datapoint, esa
# medida no existe: el disco puede estar al 3 %. Una alarma que afirma lo que no
# sabe se deja de creer, y arrastra consigo a las que si saben.
#
# Y la ceguera no queda tapada, que es lo que haria peligroso a `missing`: las dos
# causas posibles del silencio ya paginan por otro lado — la instancia caida la
# coge `ec2_status` (breaching) y el cron muerto lo coge `wal_archive_stalled`
# (breaching; mismo `/etc/cron.d/takab-pitr`, mismo `/opt/takab/bin`). Lo unico
# que queda solo para esta alarma es que falle SU publicador y no los otros dos —
# el caso mas importante de todos, porque el publicador se niega a publicar
# cuando `/data` NO ESTA MONTADO (`df` responderia con las cifras del volumen
# raiz, que se ven sanas) — y para ese hueco esta `insufficient_data_actions`.
#
# EL DIA QUE SE CREA: una alarma en `missing` NACE en INSUFFICIENT_DATA, y
# `insufficient_data_actions` solo dispara AL TRANSITAR. Si la metrica no arranca
# NUNCA, la alarma se queda aparcada ahi sin avisar a nadie (la leccion de
# `ghost_gateways`, medida el 2026-08-05). Por eso el script de configuracion
# publica una primera medida en el acto: la alarma sale a OK y ese correo es el
# acuse. Su AUSENCIA tras el apply es el indicio, y comprobarlo una vez es un paso
# escrito de la ventana de T-2.74.
resource "aws_cloudwatch_metric_alarm" "db_disk_space" {
  alarm_name          = "takab-dev-disco-datos-lleno"
  alarm_description   = "El volumen /data de la instancia (40 GiB: datadir de Postgres + pg_wal) supero el umbral de ocupacion. A 16 MiB/min —el ritmo al que crece pg_wal cuando el archivado se atasca— cada punto porcentual son ~25 min, asi que al 80 % quedan ~8,5 h antes de que Postgres se quede sin sitio y la base caiga. Primero `df -h /data` y `du -sh /data/pgdata/pg_wal`; si pg_wal es lo que crece, la causa esta en el archivado (ver la alarma de atasco y /var/log/takab-pitr.log), no en el disco. Si esta alarma queda en INSUFFICIENT_DATA, el publicador esta callado o /data NO ESTA MONTADO — que es peor que el disco lleno.${local.ack_sufijo}"
  namespace           = "Takab/Ops"
  metric_name         = "DataDiskUsedPercent"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.db_disk_used_max_pct
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "missing"

  alarm_actions             = [aws_sns_topic.ops_alerts.arn]
  ok_actions                = [aws_sns_topic.ops_alerts.arn]
  insufficient_data_actions = [aws_sns_topic.ops_alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "ghost_gateways" {
  alarm_name          = "takab-dev-gateway-retirado-sigue-reportando"
  alarm_description   = "Hay gabinete(s) dados de baja en la nube que llevan >1 h enviando latidos. O el edificio sigue protegido y el retiro fue un error (restaurar), o el hardware sigue enchufado y nadie fue a desmontarlo. Mientras dure, ese sitio esta fuera del inventario y su supervision no la mira nadie.${local.ack_sufijo}"
  namespace           = "Takab/Ops"
  metric_name         = "GhostGatewaysAlive"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 12
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "missing"

  alarm_actions             = [aws_sns_topic.ops_alerts.arn]
  ok_actions                = [aws_sns_topic.ops_alerts.arn]
  insufficient_data_actions = [aws_sns_topic.ops_alerts.arn]
}

# --- [T-2.81.a] La retencion de PII que dejo de ejecutarse ----------------------
#
# El job existia y no lo llamaba nadie. Ahora lo llama un cron, y esta alarma es
# lo que impide que vuelva a pasar EN SILENCIO: una retencion que se para no
# rompe nada visible: no hay error 500, no hay cola creciendo, no hay disco
# lleno. Simplemente los datos personales que tenian que caducar dejan de
# caducar, y eso solo se descubre el dia que alguien pregunta — que es tarde.
#
# QUE MIDE, exactamente: la edad de la ultima corrida que termino BIEN, leida de
# `pii_retention_runs` por el publicador de la instancia. NO mide el exit code
# del cron, y la diferencia es el criterio 2 de la ficha: una corrida que aborta
# escribe su fila con `ok = false`, la edad NO se refresca y la alarma sube sola.
# Con el exit code, un job que fallara todos los dias no moveria ninguna aguja.
#
# `breaching`, como sus vecinas de respaldo y por las mismas dos razones:
#   (a) lo que se afirma no es una medida instantanea sino "hasta que punto se
#       esta cumpliendo la politica de retencion". Sin metrica, eso es
#       DESCONOCIDO — y una retencion desconocida es, ante un cliente que
#       pregunta, lo mismo que una retencion que no se ejecuta;
#   (b) el que publica y el que poda son EL MISMO HOST y el MISMO cron. Si esto
#       calla, la corrida de las 06:00 tampoco se esta ejecutando: el silencio no
#       es solo ceguera, es tambien la averia.
#
# NACE EN ALARM el dia del primer apply, y esta BIEN: todavia no consta ninguna
# corrida y el publicador lo dice con la verdad (mide desde que se configuro el
# cron). El correo de OK tras la primera corrida es el ACUSE de que la retencion
# se ejecuto alguna vez — la unica senal automatica y barata de que existe.
resource "aws_cloudwatch_metric_alarm" "pii_retention_stalled" {
  alarm_name          = "takab-dev-retencion-pii-detenida"
  alarm_description   = "El job de retencion de PII lleva demasiado tiempo sin completar una corrida correcta (o no se sabe cuanto). Mientras dure, los datos personales que tenian que caducar NO estan caducando: telefonos, nombres del roster de quien ya no esta y ubicaciones GPS de check-ins siguen guardados mas alla del plazo declarado al cliente. Mirar /var/log/takab-prune-pii.log en la instancia y `SELECT mode, ok, error, finished_at FROM pii_retention_runs ORDER BY finished_at DESC LIMIT 5` (una corrida abortada deja fila con su razon). Ejecutar a mano: /opt/takab/bin/takab-prune-pii.sh. Si esta alarma aparece el dia del despliegue inicial es CORRECTO: todavia no ha corrido ninguna. La proteccion local del gabinete no depende de esto (reglas de oro 1 y 2); lo que esta en riesgo es el cumplimiento de la politica de privacidad.${local.ack_sufijo}"
  namespace           = "Takab/Ops"
  metric_name         = "PiiRetentionAgeSeconds"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.pii_retention_max_age_s
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "breaching"

  alarm_actions             = [aws_sns_topic.ops_alerts.arn]
  ok_actions                = [aws_sns_topic.ops_alerts.arn]
  insufficient_data_actions = [aws_sns_topic.ops_alerts.arn]
}
