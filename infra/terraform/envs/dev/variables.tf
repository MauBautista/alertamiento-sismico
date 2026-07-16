variable "instance_type" {
  description = <<-EOT
    Tipo de instancia EC2 para la DB Timescale + la nube co-locada (T-1.37).

    [DECISION 2026-07-09] t4g.small (2 GiB) NO alcanza: TimescaleDB-HA + API + 2 ingest
    + motor de incidentes + notify + comandos + Caddy consumen ~1.6 GiB en reposo, y en
    un pico de ingesta el OOM-killer mata al proceso de mayor RSS, que es Postgres. En
    un sistema donde fallar cuesta vidas eso no es un riesgo aceptable.
    Delta: +$12.26/mes (us-east-2). Total del entorno dev: ~$42-47/mes, bajo el budget.
  EOT
  type        = string
  default     = "t4g.medium"
}

variable "serve_enabled" {
  description = <<-EOT
    Publica la consola SOC en internet (IP elastica + SG web + TLS por Let's Encrypt).
    `false` = nada escucha fuera de la VPC. Es el default: exponer un SOC es una
    decision explicita, no un efecto colateral de `terraform apply`.
  EOT
  type        = bool
  default     = false
}

variable "web_allowed_cidrs" {
  description = <<-EOT
    CIDRs con acceso al 443 de la consola. Vacio = inalcanzable (default seguro).
    El 80 va abierto al mundo por obligacion del desafio HTTP-01 de ACME.
  EOT
  type        = list(string)
  default     = []
}

variable "acme_email" {
  description = "Contacto de Let's Encrypt (avisos de expiracion del certificado)."
  type        = string
  default     = "mauriciobaujim@gmail.com"
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

variable "ops_alert_email" {
  description = <<-EOT
    Correo de on-call operativo (A-4): recibe las alarmas de DLQ, instancia,
    errores de reglas IoT y gabinete SIN ENLACE. La suscripcion SNS llega por
    email y hay que CONFIRMARLA manualmente tras el apply.
  EOT
  type        = string
  default     = "mauriciobaujim@gmail.com"
}

variable "paged_gateways" {
  description = <<-EOT
    Things cuyo LWT offline pagina a un humano. SOLO los gateways reales: los
    gw-sim-* viven apagados por diseno y paginarian ruido permanente.
  EOT
  type        = list(string)
  default     = ["gw-dev-0001"]
}

# --- Push móvil (T-2.04) — credenciales de las platform applications de SNS.
# Vacías ⇒ push DESHABILITADO (la API usa el provider simulado, que grita).
# La llave APNs (.p8) llega con la cuenta de Apple aprobada (GATE-STORE).
variable "push_apns_signing_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "push_apns_signing_key_id" {
  type    = string
  default = ""
}

variable "push_apns_team_id" {
  type    = string
  default = ""
}

variable "push_fcm_service_account_json" {
  type      = string
  default   = ""
  sensitive = true
}
