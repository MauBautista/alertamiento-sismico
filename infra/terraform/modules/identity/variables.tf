variable "account_id" {
  type = string
}

variable "ses_verified_emails" {
  type    = list(string)
  default = ["mauriciobaujim@gmail.com"]
}

# URLs publicas adicionales de la consola (T-1.37). El callback de localhost se
# CONSERVA siempre: variabilizarlo sin conservarlo habria roto el `make dev` local.
variable "extra_callback_urls" {
  type    = list(string)
  default = []
}

variable "extra_logout_urls" {
  type    = list(string)
  default = []
}
