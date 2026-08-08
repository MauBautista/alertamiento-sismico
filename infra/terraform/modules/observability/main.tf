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

resource "aws_sns_topic" "ops_alerts" {
  name = "takab-dev-ops-alerts"
}

# La suscripcion por email exige CONFIRMACION manual (AWS manda un correo con
# un link): el apply no termina el trabajo hasta que el humano confirma.
resource "aws_sns_topic_subscription" "ops_email" {
  topic_arn = aws_sns_topic.ops_alerts.arn
  protocol  = "email"
  endpoint  = var.ops_alert_email
}

# --- DLQ con mensajes = pipeline envenenado o roto (E3/O1) -----------------------
# La ingesta rechaza a DLQ con razon tipificada; que la DLQ tenga UN mensaje ya
# es accionable. missing=notBreaching: sin trafico no hay datapoint y no es alarma.
resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  for_each = var.dlq_names

  alarm_name          = "takab-dev-dlq-${each.key}"
  alarm_description   = "DLQ '${each.value}' con mensajes: la ingesta esta rechazando payloads (ver MessageAttributes.reason) o un consumer agoto reintentos."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = each.value }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.ops_alerts.arn]
  ok_actions          = [aws_sns_topic.ops_alerts.arn]
}

# --- La instancia EC2 (DB + nube co-locada) ---------------------------------------
# missing=breaching A PROPOSITO: una instancia parada deja de emitir metricas y
# eso DEBE avisar (incluso `make cloud-stop` deliberado: la nube caida es un
# evento operativo; SNS notifica solo la transicion, un correo por parada).
resource "aws_cloudwatch_metric_alarm" "ec2_status" {
  alarm_name          = "takab-dev-ec2-status-check"
  alarm_description   = "La instancia de la nube co-locada falla sus status checks o dejo de reportar (¿parada?): API, workers y DB viven ahi."
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

resource "aws_cloudwatch_metric_alarm" "ec2_cpu" {
  alarm_name          = "takab-dev-ec2-cpu-sostenida"
  alarm_description   = "CPU > 90% sostenida 15 min en la instancia co-locada: riesgo de lag de ingesta y OOM (leccion t4g.small)."
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  dimensions          = { InstanceId = var.instance_id }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 5
  threshold           = 90
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "breaching"
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

resource "aws_cloudwatch_metric_alarm" "iot_rule_errors" {
  alarm_name          = "takab-dev-iot-rule-errors"
  alarm_description   = "Las reglas IoT estan tirando errores al enrutar hacia SQS: mensajes del edge se estan perdiendo antes de la ingesta."
  namespace           = "Takab/Ops"
  metric_name         = "IoTRuleErrors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "breaching"
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
  alarm_description   = "El gabinete ${each.value} TIENE ENLACE pero su sismografo lleva >120 s sin entregar muestras: SIN DETECCION LOCAL, el sitio esta ciego. Revisar el Raspberry Shake (alimentacion, cable de red, puerto del switch): el Pi 5 reconecta solo en cuanto vuelva a la LAN."
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
  alarm_description   = "El gabinete ${each.value} lleva >10 min sin enviar un solo heartbeat (llegan 1/min): perdio el enlace con IoT Core, se quedo sin energia o se colgo. La proteccion local sigue (regla de oro 2), pero hay que ir a verlo. Vuelve a OK sola en cuanto reaparezcan los heartbeats."
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
  alarm_description   = "El archivado continuo de WAL lleva demasiado tiempo sin avanzar (o no se sabe cuanto): a partir de aqui, un desastre pierde todo lo escrito desde el ultimo segmento que llego a S3. Y HAY UN RELOJ MAS CORTO QUE EL DEL RPO: con el archivado atascado, Postgres NO recicla su WAL y `pg_wal` crece ~16 MiB por minuto (archive_timeout fuerza segmentos de tamaño completo) sobre el mismo volumen de 40 GiB donde viven los datos — menos de dos dias hasta llenar el disco y tumbar la DB. Lo primero es mirar el espacio libre en /data; despues `pg_stat_archiver` (last_failed_time/failed_count dicen si el archive_command falla en bucle) y /var/log/takab-pitr.log. La proteccion local del gabinete no depende de esto (reglas de oro 1 y 2); lo que esta en riesgo es la memoria de la nube y, en 48 h, la nube entera."
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

resource "aws_cloudwatch_metric_alarm" "ghost_gateways" {
  alarm_name          = "takab-dev-gateway-retirado-sigue-reportando"
  alarm_description   = "Hay gabinete(s) dados de baja en la nube que llevan >1 h enviando latidos. O el edificio sigue protegido y el retiro fue un error (restaurar), o el hardware sigue enchufado y nadie fue a desmontarlo. Mientras dure, ese sitio esta fuera del inventario y su supervision no la mira nadie."
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
