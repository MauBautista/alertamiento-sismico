variable "account_id" {
  type = string
}

variable "ses_verified_emails" {
  type    = list(string)
  default = ["mauriciobaujim@gmail.com"]
}
