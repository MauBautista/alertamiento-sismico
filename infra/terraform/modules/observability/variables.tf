variable "ops_alert_email" {
  description = "Correo de on-call: recibe TODAS las alarmas operativas (requiere confirmar la suscripcion SNS)."
  type        = string
}

# [T-2.78.a] Endpoint HTTPS que se suscribe al MISMO topic para dejar rastro de
# maquina de cada aviso. VACIO POR DEFECTO a proposito: sin el, el apply de hoy no
# cambia ni un recurso (mismo patron que el modulo `push/` y que la identidad de
# dominio de T-2.78.b). El valor real es la ruta publica de la API,
# `https://<consola>/api/ops/alerts/sns`.
#
# Que sea una URL de NUESTRA API no es un detalle: el correo del on-call no deja
# rastro consultable (AWS no ofrece registro de entrega para `email`), asi que la
# unica forma de saber a que hora salio un aviso —y de tener donde escribir el
# acuse y el silencio— es que el mismo mensaje llegue a un endpoint que SI lo
# admita.
variable "ops_alert_https_endpoint" {
  description = "URL https del suscriptor que registra los avisos (POST /ops/alerts/sns de la API). Vacia = no se crea la suscripcion ni el registro de entrega."
  type        = string
  default     = ""

  validation {
    # `http` a secas no vale y conviene que falle en el plan y no seis meses
    # despues: SNS acepta el protocolo `http`, y por ahi viajarian en claro el
    # nombre de cada alarma y el motivo de cada fallo de la plataforma.
    condition     = var.ops_alert_https_endpoint == "" || startswith(var.ops_alert_https_endpoint, "https://")
    error_message = "ops_alert_https_endpoint debe empezar por https:// (o quedar vacia). Con http, el nombre de cada alarma y el motivo de cada fallo de la plataforma viajarian en claro."
  }
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

# [T-2.72.b] SIN default, por la misma razon que el de arriba y con mas motivo:
# esta cifra no es una preferencia, es un TERMINO de la desigualdad que mantiene
# viva la cadena PITR (`wal_retention_days >= base_backup_interval_days *
# chain_margin`). La calcula `modules/database` a partir de las variables que
# `modules/storage` decide, y baja hasta aqui por el entorno. Un default aqui
# permitiria que la alarma vigilara una cadena distinta de la que S3 poda.
variable "base_backup_max_age_s" {
  description = "Edad maxima tolerada del ultimo backup base, en segundos (`base_backup_interval_days * chain_margin` dias). Es el umbral de la alarma del ancla de la cadena PITR."
  type        = number
}

# [T-2.141] El umbral del AVISO, y SIN default por la misma razon que su hermano:
# tampoco es una preferencia. Es `base_backup_interval_days` — el MISMO intervalo
# con el que `modules/database` programa el cron `*/N`, sin el margen. Un default
# aqui permitiria que el aviso vigilara un intervalo distinto del que produce los
# backups, y entonces avisaria en cualquier momento menos cuando falla el primero.
#
# NO se calcula aqui a partir del otro (`max / chain_margin`) a proposito: eso
# obligaria a bajar tambien `chain_margin` hasta este modulo y a que un modulo de
# vigilancia rehiciera la aritmetica de la retencion. Los dos umbrales se derivan
# donde viven las cifras y bajan ya resueltos, cada uno por su cable.
variable "base_backup_warn_age_s" {
  description = "Edad del ultimo backup base a partir de la cual se AVISA, en segundos (`base_backup_interval_days` dias). Es el umbral de la alarma temprana: caza el PRIMER backup base fallido, mientras todavia queda ventana de recuperacion."
  type        = number
}

# [T-2.72.c] Este SI lleva default, y la asimetria es deliberada: el de arriba
# tiene dueño en otro modulo (se derivaria mal si alguien lo teclea aqui); este es
# una decision de vigilancia que se toma en este modulo y en ningun otro.
variable "db_disk_used_max_pct" {
  description = <<-EOT
    Ocupacion de `/data` a partir de la cual se avisa, en porcentaje.

    El 80 % no es un numero redondo elegido por costumbre: sobre el volumen de
    40 GiB de la instancia deja ~8 GiB libres, y con `pg_wal` creciendo ~16 MiB
    por minuto (que es lo que pasa con el archivado atascado) eso son ~8,5 horas
    de margen. Cada punto porcentual vale ~25 minutos. El margen es lo unico que
    convierte un aviso en algo accionable: sin el, la alarma llega a la vez que la
    caida.
  EOT
  type        = number
  default     = 80

  validation {
    # Por encima del 90 % quedan menos de 4 GiB (~4 h) y ya no da tiempo a
    # localizar a nadie ni a liberar espacio con la base en marcha. Por debajo de
    # cero o por encima de cien, el umbral no es alcanzable y la alarma no puede
    # disparar nunca — el peor fallo posible en una alarma: existe y no vigila.
    condition     = var.db_disk_used_max_pct > 0 && var.db_disk_used_max_pct <= 90
    error_message = "db_disk_used_max_pct debe estar en (0, 90]. Por encima del 90 % sobre el volumen de 40 GiB quedan menos de 4 GiB, o sea menos de 4 h a 16 MiB/min: el aviso llegaria demasiado tarde para hacer nada. Un umbral fuera de (0,100] no es alcanzable y produce una alarma que existe y no vigila."
  }
}

variable "pii_retention_max_age_s" {
  description = <<-EOT
    [T-2.81.a] Edad maxima tolerada de la ultima corrida CORRECTA del job de
    retencion de PII. NO se teclea aqui: baja de `modules/database`, que es donde
    vive el cron que las produce y donde estan la cadencia y el margen. Un literal
    aqui haria que la alarma vigilara una periodicidad distinta de la programada.
  EOT
  type        = number
  default     = 172800 # 2 dias = cadencia diaria x margen 2

  validation {
    condition     = var.pii_retention_max_age_s > 86400
    error_message = "pii_retention_max_age_s debe superar la cadencia diaria (86400 s): un umbral igual o menor dispara en operacion normal y convierte la alarma en ruido."
  }
}

# [T-2.162] El plazo de acuse, EN SEGUNDOS y desde una sola fuente.
#
# El correo de on-call tiene que decir cuanto tiempo hay, y la API tiene que
# aplicar ese mismo numero (`TAKAB_API_OPS_ACK_DEADLINE_S`). Si cada uno lo
# declarara por su cuenta, divergirian — y el correo prometeria un plazo que el
# servidor no respeta. Esta variable es la fuente; el entorno la exporta para que
# el despliegue la derive en vez de teclearla.
variable "ops_ack_deadline_s" {
  description = "Plazo para acusar un aviso de on-call, en segundos. Alimenta el texto del correo Y `TAKAB_API_OPS_ACK_DEADLINE_S`: una sola fuente para los dos."
  type        = number
  default     = 900
}
