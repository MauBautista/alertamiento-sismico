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
