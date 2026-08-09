output "ops_topic_arn" {
  value = aws_sns_topic.ops_alerts.arn
}

# [T-2.72] El RPO, DERIVADO de la alarma que lo sostiene.
#
# No es una constante que alguien tecleo ni una promesa del runbook: se calcula de
# los atributos del propio recurso, asi que no puede quedarse desactualizado
# respecto a la vigilancia que lo garantiza. Cambiar el umbral o la ventana de
# evaluacion cambia este numero en el mismo commit.
#
#   RPO = umbral + period * evaluation_periods
#
# El primer termino es cuanto puede envejecer el archivado antes de que la alarma
# empiece a contar; el segundo es lo que tarda CloudWatch en juntar los periodos
# consecutivos que necesita para mandar el correo. Los dos son tiempo en el que se
# esta perdiendo WAL, y por eso los dos cuentan.
#
# Lo que este numero NO promete: que el archivado funcione. Promete que si deja de
# funcionar, alguien se entera antes de que la perdida potencial pase de aqui.
output "rpo_seconds" {
  description = "RPO derivado: edad maxima del archivado a la que un humano recibe el aviso."
  value = (
    aws_cloudwatch_metric_alarm.wal_archive_stalled.threshold
    + aws_cloudwatch_metric_alarm.wal_archive_stalled.period
    * aws_cloudwatch_metric_alarm.wal_archive_stalled.evaluation_periods
  )
}

# El umbral tal y como quedo EN LA ALARMA (no la variable de entrada). El entorno
# lo contrasta contra el que declara `modules/database`: si alguien cablease un
# literal al conectar los dos modulos, la DB estaria validando su
# `archive_timeout` contra un numero que no vigila nadie.
output "wal_archive_alarm_threshold_s" {
  value = aws_cloudwatch_metric_alarm.wal_archive_stalled.threshold
}
