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

# [T-2.78.a] Suscribe la API al topic de on-call para que cada aviso deje una fila
# con hora (y un sitio donde escribir el acuse y el silencio). AWS no da registro
# de entrega para `email`, asi que sin esto lo unico afirmable de la cadena de
# operacion es "SNS lo publico".
#
# `false` es el default Y ES UNA PUERTA DE ORDEN, no timidez: la suscripcion se
# CONFIRMA SOLA (`endpoint_auto_confirms`), asi que AWS llama al endpoint DURANTE
# el apply. Si la API desplegada todavia no sirve `POST /api/ops/alerts/sns` —o
# no tiene `TAKAB_API_OPS_ALERT_TOPIC_ARN` puesto, y entonces contesta 503— la
# confirmacion falla y el apply muere a medias. El orden correcto es:
# desplegar la API primero, comprobar el endpoint, y solo entonces poner esto en
# `true`. Al reves se rompe.
variable "ops_alert_https_subscriber_enabled" {
  description = "Suscribe la API (POST /api/ops/alerts/sns) al topic de on-call. Exige la consola publicada y la API YA desplegada con el endpoint vivo: la suscripcion se confirma durante el apply."
  type        = bool
  default     = false

  # [T-2.159] AWS tiene que poder LLAMAR a ese endpoint, y eso depende del
  # cortafuegos, no de la API.
  #
  # El aviso en prosa de arriba ya fallo una vez: predijo el caso "la API no esta
  # desplegada, contesta 503" —que se cumplia— y no el del security group, porque
  # nadie penso en el. Un aviso correcto que cubre media casuistica se lee como
  # cobertura completa. De ahi que esto sea una validacion y no un parrafo.
  #
  # FALLA EN EL PLAN a proposito. Al principio el defecto era ruidoso: encender
  # esto con la red cerrada mataba el apply a medias. Ahora que la suscripcion
  # existe, ESTRECHAR la lista no rompe ningun apply — rompe la ENTREGA, en
  # silencio, con todo el terraform en verde. Un aviso que llega cuando la guardia
  # ya no recibe alarmas llega tarde por definicion.
  #
  # `0.0.0.0/0` y no una lista de rangos de AWS porque esa lista no existe: AWS no
  # publica prefijos por servicio para SNS, solo el bloque AMAZON de la region.
  validation {
    condition     = !var.ops_alert_https_subscriber_enabled || contains(var.web_allowed_cidrs, "0.0.0.0/0")
    error_message = "`ops_alert_https_subscriber_enabled = true` exige `web_allowed_cidrs` con \"0.0.0.0/0\": AWS SNS llama al endpoint desde sus rangos y con la lista estrechada la cadena on-call deja de entregar EN SILENCIO (ver D-22 y T-2.159)."
  }
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

# --- [T-2.78.b] Remitente de DOMINIO ------------------------------------------
#
# VACIA por defecto: sin dominio no se crea ni un recurso de SES-dominio y el
# apply de hoy no cambia (lo mide `modules/identity/tests/ses_domain.tftest.hcl`).
#
# ESTA MISMA VARIABLE alimenta DOS modulos y no es duplicacion: `module.identity`
# CREA la identidad y `module.database` CONCEDE el envio. Una identidad verificada
# no concede envio —son dos cosas distintas—, y tenerlas gobernadas por una sola
# variable es lo que impide repetir el 2026-07-14: el worker con AccessDenied
# mientras los correos de CloudWatch, que van por SNS con permiso propio, siguen
# llegando y tapan el hueco.
variable "ses_domain" {
  description = "Dominio remitente (p. ej. `takab.mx`). Vacio = SES sigue como hoy, solo identidades por direccion."
  type        = string
  default     = ""
}

variable "ses_mail_from_subdomain" {
  description = "Subdominio del MAIL FROM propio (`<sub>.<ses_domain>`): es lo que alinea SPF con nuestro dominio."
  type        = string
  default     = "correo"
}

variable "ses_dmarc_policy" {
  description = "Politica DMARC: none (observar, lo correcto el primer dia), quarantine o reject."
  type        = string
  default     = "none"
}

variable "ses_dmarc_rua" {
  description = "Buzon de informes agregados DMARC. Vacio = DMARC a ciegas: se publica la politica y nadie ve quien suplanta el dominio."
  type        = string
  default     = ""
}

variable "ses_route53_zone_id" {
  description = "Zona Route 53 del dominio. Vacia = no se toca DNS; los registros a publicar salen por el output `ses_domain_dns_records`."
  type        = string
  default     = ""
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

# --- [T-2.156] Sitio publico del dominio --------------------------------------
#
# Nace de una denegacion medida: la solicitud de salida del sandbox de SES
# (caso 178737638500467) fue rechazada porque la `Website URL` declarada apuntaba
# a la consola del SOC, cuyo 443 admite UNA sola IP. AWS vio un timeout.
#
# La consola NO se abre para arreglarlo: esto es un sitio aparte, publico y sin
# nada detras, y aquella conserva su lista blanca.
variable "site_enabled" {
  description = "Publica el sitio estatico del dominio en CloudFront. Falso = no se crea ni un recurso."
  type        = bool
  default     = false
}

# [T-2.162] Fuente unica del plazo de acuse: lo consume el texto del correo
# (`module.observability`) y el despliegue de la API, por el output del mismo
# nombre.
variable "ops_ack_deadline_s" {
  description = "Plazo para acusar un aviso de on-call, en segundos."
  type        = number
  default     = 900
}
