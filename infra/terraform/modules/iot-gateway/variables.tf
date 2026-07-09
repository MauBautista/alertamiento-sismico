variable "thing_name" {
  type = string
}

variable "thing_type_name" {
  type = string
}

variable "thing_group_name" {
  type = string
}

variable "fleet_policy_name" {
  type = string
}

variable "hmac_secret_prefix" {
  description = <<-EOT
    Prefijo del secreto HMAC de comandos, SEPARADO del secreto del certificado:
    IAM no filtra campos JSON y el rol de la nube solo debe poder leer claves
    HMAC, jamas claves privadas mTLS (T-1.38).
  EOT
  type        = string
}
