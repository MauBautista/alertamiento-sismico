variable "account_id" {
  type = string
}

variable "ses_verified_emails" {
  type    = list(string)
  default = ["mauriciobaujim@gmail.com"]
}

# --- [T-2.78.b] Identidad de DOMINIO de SES -----------------------------------
#
# Hasta esta ficha, el UNICO recurso SES de toda la infraestructura era la
# identidad POR DIRECCION de arriba: DKIM, SPF, el MAIL FROM propio y el destino
# de los rebotes solo podian existir a base de clics en la consola. Todo lo de
# abajo cuelga de `ses_domain`, VACIA por defecto — el patron del modulo `push/`:
# sin credenciales no se crea nada y el apply de hoy no cambia. Asi el codigo
# puede aterrizar y revisarse en un diff antes de que exista el dominio.

variable "ses_domain" {
  description = <<-EOT
    Dominio desde el que TAKAB envia correo (p. ej. `takab.mx`). VACIO = no se
    crea NADA de SES-dominio: ni identidad, ni DKIM, ni MAIL FROM, ni topic de
    rebotes, ni registros DNS.

    ES LA MISMA VARIABLE que alimenta el permiso de envio del worker
    (`module.database.notify_ses_domain` en el entorno), y eso es deliberado: una
    identidad VERIFICADA no concede envio —son dos cosas distintas— y separarlas
    en dos variables es como se llega a un worker con AccessDenied mientras los
    correos de CloudWatch, que van por SNS con permiso propio, siguen llegando y
    tapan el hueco. Paso el 2026-07-14.
  EOT
  type        = string
  default     = ""

  validation {
    # Sin punto no es un dominio, es un nombre de host suelto; con esquema o barra
    # es una URL pegada por costumbre. Los dos se aceptarian sin ruido y dejarian
    # la identidad en PENDING para siempre.
    condition     = var.ses_domain == "" || (length(regexall("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.ses_domain)) == 1)
    error_message = "ses_domain debe ser un nombre de dominio en minusculas y con al menos un punto (`takab.mx`), sin esquema ni barras. Un valor mal formado se acepta en el apply y deja la identidad en PENDING para siempre."
  }
}

variable "ses_mail_from_subdomain" {
  description = <<-EOT
    Subdominio del MAIL FROM propio (`<sub>.<ses_domain>`). Es lo que alinea SPF
    con NUESTRO dominio: sin el, el Return-Path es `amazonses.com` y SPF alinea
    con AWS, no con TAKAB.
  EOT
  type        = string
  default     = "correo"
}

variable "ses_feedback_email" {
  description = <<-EOT
    Buzon que recibe rebotes y quejas (via SNS). La solicitud de acceso a
    produccion de SES exige declarar que existe un proceso para tratarlos; esto es
    ese proceso, y por eso es OBLIGATORIO en cuanto hay dominio. Declarar el
    proceso sin tenerlo es firmar algo falso.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.ses_domain == "" || var.ses_feedback_email != ""
    error_message = "Con `ses_domain` puesto, `ses_feedback_email` es obligatorio: no se puede declarar un dominio de envio sin un buzon donde caigan los rebotes y las quejas. AWS exige declarar ese proceso para conceder acceso a produccion, y un topic sin suscriptor es un sumidero con cara de proceso."
  }
}

variable "ses_dmarc_policy" {
  description = <<-EOT
    Politica DMARC publicada en `_dmarc.<dominio>`. `none` = solo observar (lo
    correcto el primer dia: endurecer antes de leer un informe agregado es como se
    tira el correo legitimo de la propia organizacion). `quarantine`/`reject` son
    una DECISION posterior, y por eso viven en una variable y no en un literal.
  EOT
  type        = string
  default     = "none"

  validation {
    condition     = contains(["none", "quarantine", "reject"], var.ses_dmarc_policy)
    error_message = "ses_dmarc_policy solo admite none, quarantine o reject. Cualquier otra cosa produce un registro DMARC que los receptores IGNORAN en silencio: el TXT existe, se ve bien en un `dig`, y no protege nada."
  }
}

variable "ses_dmarc_rua" {
  description = "Buzon de informes agregados DMARC (`rua=mailto:`). Vacio = registro sin rua, o sea DMARC a ciegas: la politica se publica y nadie ve quien esta suplantando el dominio."
  type        = string
  default     = ""
}

variable "ses_route53_zone_id" {
  description = <<-EOT
    Zona de Route 53 del dominio. VACIA = no se toca DNS aunque haya dominio: la
    zona de un dominio comprado en cualquier registrador no tiene por que vivir en
    esta cuenta, y `aws_route53_record` contra una zona ajena no falla en el plan
    —falla a mitad del apply, con la identidad ya creada. Sin zona, los valores a
    publicar salen por el output `ses_domain_dns_records`.
  EOT
  type        = string
  default     = ""
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

# Deep links de la app móvil (T-2.02). El esquema `takab://` lo registra
# mobile/app.json (`scheme`); aplica igual en dev-client y en build de tienda.
variable "mobile_callback_urls" {
  type    = list(string)
  default = ["takab://auth/callback"]
}

variable "mobile_logout_urls" {
  type    = list(string)
  default = ["takab://auth/logout"]
}
