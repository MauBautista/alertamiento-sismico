variable "ops_alert_email" {
  description = "Correo de on-call: recibe TODAS las alarmas operativas (requiere confirmar la suscripcion SNS)."
  type        = string
}

variable "dlq_names" {
  description = "Nombre de cada DLQ por clave logica (events/telemetry/backfill) para alarmar profundidad > 0."
  type        = map(string)
}

variable "instance_id" {
  description = "Instancia EC2 de la nube co-locada (DB + API + workers)."
  type        = string
}

variable "iot_rule_errors_log_group" {
  description = "Log group del error_action de las reglas IoT (todo evento ahi es un error)."
  type        = string
}

variable "paged_gateways" {
  description = "Things cuyo LWT offline pagina a un humano (solo gateways REALES; los sim viven apagados)."
  type        = list(string)
}

# [T-2.72] SIN default a proposito. Esta cifra tiene UN dueño —`modules/database`,
# que la usa para validar su `archive_timeout`— y baja hasta aqui por el entorno.
# Un default aqui permitiria que la alarma vigilara un umbral distinto del que la
# DB cree tener, y el RPO publicado describiria a una alarma que no existe.
variable "wal_archive_max_age_s" {
  description = "Edad maxima tolerada del archivado de WAL, en segundos. Es el umbral de la alarma de atasco y el termino dominante del RPO."
  type        = number
}
