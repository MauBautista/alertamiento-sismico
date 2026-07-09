variable "enabled" {
  description = "Publica la consola. `false` = no hay IP elástica ni SG web (todo cerrado)."
  type        = bool
  default     = false
}

variable "vpc_id" {
  type = string
}

variable "instance_id" {
  type = string
}

variable "network_interface_id" {
  description = "ENI primaria de la instancia; el SG web se adjunta aquí, no a la instancia."
  type        = string
}

variable "allowed_cidrs" {
  description = <<-EOT
    CIDRs con acceso al 443. El 80 va abierto al mundo por obligación de ACME.
    Una lista vacía deja la consola inalcanzable: es el default seguro, no un olvido.
    Ejemplo: ["203.0.113.7/32"].
  EOT
  type        = list(string)
  default     = []
}
