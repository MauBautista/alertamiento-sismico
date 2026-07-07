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
