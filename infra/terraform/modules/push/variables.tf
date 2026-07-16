variable "env" {
  type = string
}

# --- APNs (iOS) — llegan cuando Apple apruebe la cuenta/entitlement (GATE-STORE).
# Autenticación por token: contenido del .p8 + key id + team id + bundle id.
# Vacío ⇒ la platform application NO se crea (push iOS deshabilitado).
variable "apns_signing_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "apns_signing_key_id" {
  type    = string
  default = ""
}

variable "apns_team_id" {
  type    = string
  default = ""
}

variable "apns_bundle_id" {
  type    = string
  default = "com.takab.ailert"
}

# dev/TestFlight usan el gateway sandbox de APNs; producción el normal.
variable "apns_sandbox" {
  type    = bool
  default = true
}

# --- FCM (Android) — service account JSON del proyecto Firebase (FCM v1).
# Vacío ⇒ la platform application NO se crea (push Android deshabilitado).
variable "fcm_service_account_json" {
  type      = string
  default   = ""
  sensitive = true
}

# Rol IAM donde corre la API/worker de notify (en dev: el de la instancia EC2).
# Vacío ⇒ no se adjunta política.
variable "worker_role_name" {
  type    = string
  default = ""
}
