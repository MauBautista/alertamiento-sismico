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
