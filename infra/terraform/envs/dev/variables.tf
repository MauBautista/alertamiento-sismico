variable "instance_type" {
  description = "Tipo de instancia EC2 para la DB Timescale."
  type        = string
  default     = "t4g.small"
}

variable "gateway_fleet" {
  description = "Things IoT a aprovisionar (1 gateway real + 4 simulados)."
  type        = list(string)
  default     = ["gw-dev-0001", "gw-sim-0001", "gw-sim-0002", "gw-sim-0003", "gw-sim-0004"]
}

variable "budget_email" {
  type    = string
  default = "mauriciobaujim@gmail.com"
}

variable "ses_verified_emails" {
  type    = list(string)
  default = ["mauriciobaujim@gmail.com"]
}
