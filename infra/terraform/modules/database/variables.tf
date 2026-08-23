variable "subnet_id" {
  type = string
}

variable "sg_db_id" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "db_backups_bucket" {
  type = object({
    name = string
    arn  = string
  })
}

variable "instance_type" {
  type    = string
  default = "t4g.small"
}

# Workers co-locados (default dev): colas que la instancia puede consumir
# y repos ECR de los que puede hacer pull.
variable "worker_queue_arns" {
  type    = list(string)
  default = []
}

variable "worker_ecr_repo_arns" {
  type    = list(string)
  default = []
}

variable "worker_s3_read_arns" {
  type    = list(string)
  default = []
}

# Grant service del backfill (T-1.25) co-locado: keys que el rol puede
# PRE-FIRMAR para PUT (un presigned URL solo vale si el firmante tiene
# s3:PutObject al ejecutarse).
variable "worker_s3_presign_put_arns" {
  type    = list(string)
  default = []
}

# Topics MQTT que la nube publica hacia el edge: grants de backfill (T-1.25),
# comandos de actuador takab/cmd/* y config sync takab/cfg/* (T-1.38).
variable "worker_iot_publish_topic_arns" {
  type    = list(string)
  default = []
}

# Secretos ADICIONALES que la instancia puede leer (T-1.37): la clave HMAC del
# gabinete que la nube usa para firmar comandos de actuador. Acotado a ARNs
# explicitos: el rol nunca recibe secretsmanager:GetSecretValue sobre "*".
variable "worker_secret_arns" {
  type    = list(string)
  default = []
}

# Identidades SES desde las que el worker notify puede enviar correo (T-1.62).
# Vacio = sin permiso de envio (el provider de email caeria en AccessDenied).
variable "notify_ses_identity_arns" {
  type    = list(string)
  default = []
}

# [T-2.78.b] El remitente de DOMINIO. Se recibe el DOMINIO y no su ARN porque el
# ARN se compone aqui con la region y la cuenta de este modulo —igual que los
# topics de IoT—: tomarlo del output de `module.identity` cerraria el ciclo
# `identity -> serve -> database`.
#
# Es la MISMA variable del entorno que crea la identidad. Separarlas seria volver
# a permitir el estado que rompio el 2026-07-14: identidad verificada y worker sin
# permiso, con los correos de CloudWatch (SNS, permiso propio) llegando igual y
# tapando el hueco. Una identidad VERIFICADA no concede envio.
variable "notify_ses_domain" {
  description = "Dominio remitente cuyo ARN de identidad SES entra en el permiso de envio del worker notify. Vacio = solo las direcciones de `notify_ses_identity_arns`."
  type        = string
  default     = ""
}

# [T-2.71] Prefijo de entorno de los nombres de alarma de CloudWatch. El modulo
# `observability` los escribe hardcodeados como `takab-dev-...`; aqui es una
# variable porque estos ARN son la FRONTERA de qué se puede silenciar, y una
# frontera que no se puede parametrizar acaba copiándose mal al siguiente
# entorno. Default `dev` para que el env actual no cambie de comportamiento.
variable "env" {
  description = "Entorno (prefijo de los nombres de alarma: takab-<env>-...)."
  type        = string
  default     = "dev"
}

# --- [T-2.72] PITR: archivado continuo de WAL --------------------------------

variable "dump_key_prefix" {
  description = "Prefijo de clave del dump logico (espejo de `db_dump_key_prefix` en modules/storage). Aqui solo se usa para conceder LECTURA sobre ese prefijo: hasta hoy el rol podia escribir sus dumps y no podia leerlos, o sea que el restore no se podia ejecutar donde vive la DB."
  type        = string
  default     = "takab-"
}

# [T-2.73.a] Cuanto espera la huella a que el dump confirme antes de rendirse.
#
# Tiene que ser HOLGADAMENTE mayor que la duracion del `pg_dump` nocturno: si
# expira antes, la huella no se escribe (fail-closed) y ese dia el verificador
# dara INDETERMINADO. No tiene efecto sobre el `.dump`, que sube igual. La cifra
# real de produccion se conocera al medir el RTO en `T-2.74`; hasta entonces, una
# hora sobre una base de decenas de MiB es mas de un orden de magnitud de margen.
variable "dump_coordination_timeout_s" {
  description = "Segundos que la huella mantiene abierto su snapshot esperando a que el dump nocturno confirme."
  type        = number
  default     = 3600

  validation {
    # Un timeout corto no rompe el respaldo, pero apaga la huella en silencio: el
    # dump seguiria subiendo y el bucket se llenaria de dias sin acreditar.
    condition     = var.dump_coordination_timeout_s >= 600
    error_message = "Menos de 600 s no da margen a un pg_dump real: la huella expiraria casi cada noche y el bucket acumularia dumps sin huella (INDETERMINADO) sin que nada fallara."
  }
}

variable "pitr" {
  description = <<-EOT
    Cadena PITR: donde vive y cuanto dura. Los numeros los decide
    `modules/storage` (el unico podador) y bajan aqui para programar el backup
    base y para NEGARSE a configurar el archivado si la cadena no se sostiene.
  EOT
  type = object({
    prefix                    = string
    server_name               = string
    wal_retention_days        = number
    base_backup_interval_days = number
    chain_margin              = number
  })
  default = {
    prefix                    = "pitr/"
    server_name               = "takab-dev-db"
    wal_retention_days        = 14
    base_backup_interval_days = 7
    chain_margin              = 2
  }

  # La desigualdad que mantiene viva la cadena, DERIVADA de las tres cifras y no
  # comprobada contra dos literales que hoy coinciden.
  #
  # Por que >= intervalo * margen y no solo >= intervalo: justo antes de que
  # expire el backup base mas viejo, el siguiente es `intervalo` dias mas nuevo.
  # Con margen 1, en ese instante el unico base con WAL vivo es el que esta
  # expirando: la ventana de recuperacion se cierra a cero cada `intervalo` dias
  # y nadie lo nota. El margen 2 garantiza que SIEMPRE haya una cadena completa
  # (base + todos sus WAL) mientras la anterior se apaga.
  validation {
    condition     = var.pitr.chain_margin >= 2
    error_message = "pitr.chain_margin debe ser >= 2: con margen 1, el backup base mas antiguo expira junto con los WAL que lo continuan y la ventana de recuperacion se cierra a cero periodicamente sin que nada falle."
  }

  validation {
    condition     = var.pitr.wal_retention_days >= var.pitr.base_backup_interval_days * var.pitr.chain_margin
    error_message = "La retencion de WAL debe cubrir al menos `base_backup_interval_days * chain_margin` dias. Por debajo de eso, la cadena queda partida: hay backups base sin los WAL que los continuan, y eso no se nota hasta el dia del restore."
  }

  validation {
    condition     = endswith(var.pitr.prefix, "/") && length(var.pitr.prefix) > 1
    error_message = "pitr.prefix debe terminar en '/' y no puede ser la raiz del bucket: un prefijo vacio mezclaria la cadena PITR con el dump bajo la misma regla de expiracion."
  }
}

variable "wal_archive_timeout_s" {
  description = <<-EOT
    `archive_timeout` de Postgres: cada cuanto se fuerza el cierre de un segmento
    de WAL aunque no se haya llenado.

    NO es opcional, y por que no lo es esta escrito literal en la doc de
    PostgreSQL 16 (runtime-config-wal, `archive_timeout`): "The archive_command
    or archive_library is only invoked for completed WAL segments. Hence, if your
    server generates little WAL traffic (or has slack periods where it does so),
    there could be a long delay between the completion of a transaction and its
    safe recording in archive storage. To limit how old unarchived data can be,
    you can set archive_timeout to force the server to switch to a new WAL
    segment file periodically. When this parameter is greater than zero, the
    server will switch to a new segment file whenever this amount of time has
    elapsed since the last segment file switch, and there has been any database
    activity, including a single checkpoint (checkpoints are skipped if there is
    no database activity)."

    Un segmento son 16 MiB. Esta base escribe telemetria a goteo: sin
    `archive_timeout`, el ultimo segmento puede pasar HORAS a medio llenar con el
    `archive_command` "funcionando" perfectamente, y todo lo escrito desde el
    ultimo cierre se pierde en un desastre.

    Y OJO CON LA CONCLUSION FACIL, porque la primera version de este comentario la
    tenia al reves: sin `archive_timeout` el fallo NO seria silencioso. La alarma
    de atasco mide la edad del ultimo archivado, asi que un segmento tardando
    horas en llenarse la hace SONAR igual que un archivado roto — la alarma no
    sabria distinguir "el respaldo esta averiado" de "hoy se ha escrito poco", y
    una alarma que suena por el volumen de escritura se deja de leer en una
    semana. `archive_timeout` es lo que convierte esa edad en un RELOJ DE RPO en
    vez de en un proxy del trafico.

    LA CARA B, que sale de la clausula del "database activity" citada arriba: con
    la base COMPLETAMENTE ociosa no hay cambio forzado de segmento (los
    checkpoints se saltan), `last_archived_time` se congela y la alarma dispara
    aunque no haya nada roto. Es un falso positivo, no una ceguera —el error va
    hacia el lado seguro—, y aqui es poco probable porque los latidos de la flota
    escriben cada minuto. Si algun dia la nube se queda sin gabinetes conectados,
    esta es la explicacion del correo.

    Coste, tambien literal de esa doc: "Note that archived files that are closed
    early due to a forced switch are still the same length as completely full
    files. Therefore, it is unwise to use a very short archive_timeout — it will
    bloat your archive storage." Cada minuto sube 16 MiB comprimidos. Es el precio
    del RPO.
  EOT
  type        = number
  default     = 60

  validation {
    condition     = var.wal_archive_timeout_s > 0
    error_message = "wal_archive_timeout_s debe ser > 0: con 0 Postgres solo archiva segmentos LLENOS y el RPO deja de estar acotado (y el atasco es indistinguible del reposo)."
  }

  # Si el timeout alcanza la edad tolerada, la alarma dispara en operacion
  # NORMAL: el segmento se cierra justo cuando la edad ya cruzo el umbral. Una
  # alarma que suena sin que pase nada es una alarma que alguien acaba
  # silenciando — y esta es intocable a proposito, asi que lo unico que quedaria
  # es que se deje de leer.
  validation {
    condition     = var.wal_archive_timeout_s < var.wal_archive_max_age_s
    error_message = "wal_archive_timeout_s debe ser estrictamente menor que wal_archive_max_age_s: si no, la alarma de atasco dispara en operacion normal y se convierte en ruido."
  }
}

variable "wal_archive_max_age_s" {
  description = <<-EOT
    Edad maxima tolerada del archivado, en segundos. Es el umbral de la alarma de
    `modules/observability` y, por tanto, el termino dominante del RPO: el RPO no
    es lo que promete la configuracion feliz, es la edad del archivado a la que
    alguien SE ENTERA.
  EOT
  type        = number
  default     = 600

  validation {
    condition     = var.wal_archive_max_age_s > 0
    error_message = "wal_archive_max_age_s debe ser > 0."
  }
}

# --- [T-2.81.a] Retencion de PII ------------------------------------------------

variable "pii_retention_windows_days" {
  description = <<-EOT
    Plazo de cada regla de retencion de PII, en dias, con la CLAVE DE LA REGLA
    (`api/src/takab_api/privacy/retention.RETENTION_PLAN`) como llave del mapa:
    `push_tokens.token`, `life_checkins.geom`, `user_profiles.identity`.

    VACIO POR DEFECTO Y ESO ES LA DECISION, no un hueco: sin plazo la regla queda
    DESHABILITADA y la corrida no toca una sola fila. Cuanto tiempo se guarda el
    telefono de una persona no lo decide quien escribe el terraform — sale de la
    ficha legal y del contrato con cada cliente. Mientras tanto el job corre a
    diario, no poda nada, y deja constancia de que el reloj se reviso.

    Una clave que no exista en el plan no rompe nada (el job ignora las variables
    de entorno que no reconoce) pero tampoco poda nada: es un error silencioso, y
    por eso la validacion de abajo solo admite las claves del plan de hoy.
  EOT
  type        = map(number)
  default     = {}

  validation {
    condition = alltrue([
      for k in keys(var.pii_retention_windows_days) :
      contains(["push_tokens.token", "life_checkins.geom", "user_profiles.identity"], k)
    ])
    error_message = "pii_retention_windows_days solo admite claves del plan de retencion: push_tokens.token, life_checkins.geom, user_profiles.identity."
  }

  validation {
    condition     = alltrue([for d in values(var.pii_retention_windows_days) : d > 0])
    error_message = "un plazo de retencion debe ser > 0 dias: el job trata 0 o negativo como 'sin configurar' y la regla quedaria deshabilitada sin que nadie lo notara."
  }
}

variable "pii_retention_chain_margin" {
  description = <<-EOT
    Cuantas corridas diarias seguidas pueden fallar antes de que suene la alarma.
    Es el mismo criterio que `pitr.chain_margin`: el umbral de la alarma sale de
    multiplicar la cadencia por este margen, no de un numero elegido a mano.

    2 = dos dias sin una corrida correcta. Con 1 cualquier reintento tardio o un
    reinicio de la instancia a las 06:00 daria un correo; con 3 la retencion
    podria estar tres dias parada antes de que alguien se entere.
  EOT
  type        = number
  default     = 2

  validation {
    condition     = var.pii_retention_chain_margin >= 2
    error_message = "pii_retention_chain_margin debe ser >= 2: con 1, una sola corrida perdida (un reinicio a las 06:00) manda un correo y las alarmas se dejan de leer."
  }
}

# [T-2.155] Ver `notify_ses_arns` en main.tf: sin el ARN del configuration set el
# envio muere con AccessDenied aunque la identidad este concedida.
variable "notify_ses_configuration_set" {
  description = "Nombre del configuration set por defecto de la identidad de dominio. Vacio = no se concede (no hay dominio)."
  type        = string
  default     = ""
}
