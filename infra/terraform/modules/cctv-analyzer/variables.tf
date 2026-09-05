variable "image_uri" {
  description = "Imagen del Lambda en ECR, con tag inmutable (nunca `latest`)."
  type        = string
}

variable "queue_arn" {
  description = "Cola SQS que dispara el analisis (takab-dev-q-cctv)."
  type        = string
}

variable "evidence_bucket" {
  description = "Nombre del bucket de evidencia."
  type        = string
}

variable "evidence_bucket_arn" {
  description = "ARN del bucket de evidencia. El rol solo lee bajo `evidence/`."
  type        = string
}

variable "db_secret_arn" {
  description = "ARN del secreto con el DSN. Explicito, nunca `*`."
  type        = string
}

variable "database_url" {
  description = "DSN de la base. Viaja por entorno del Lambda; el rol tambien puede leer el secreto."
  type        = string
  sensitive   = true
}

variable "subnet_ids" {
  description = "Subredes de la VPC. El Lambda tiene que estar dentro para llegar a Postgres."
  type        = list(string)
}

variable "security_group_id" {
  description = "SG de workers: es el que el SG de la base acepta como origen."
  type        = string
}

variable "log_retention_days" {
  description = "Retencion de los logs del Lambda."
  type        = number
  default     = 30
}
