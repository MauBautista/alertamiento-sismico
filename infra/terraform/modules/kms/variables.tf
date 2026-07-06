variable "alias_prefix" {
  type    = string
  default = "takab-dev"
}

variable "create_state_key" {
  type    = bool
  default = false
}

variable "tenant_keys" {
  description = "KEKs por tenant: clave logica -> descripcion."
  type        = map(string)
  default     = {}
}
