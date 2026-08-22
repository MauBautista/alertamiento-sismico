# [T-2.156] Sitio publico del dominio. Existe por una razon concreta y medida: la
# solicitud de salida del sandbox de SES se DENEGO (caso 178737638500467) porque
# la `Website URL` declarada apuntaba a la consola del SOC, cuyo puerto 443 solo
# admite UNA IP. Desde donde mira AWS, ese sitio no existia: timeout.
#
# La consola NO se abre para arreglar esto. Son dos cosas distintas y se sirven
# por separado: la consola sigue tras su lista blanca, y esto es una pagina
# publica sin nada detras.

variable "enabled" {
  description = "Falso = no se crea ni un recurso. El apply de hoy no cambia."
  type        = bool
  default     = false
}

variable "domain" {
  description = "Dominio raiz servido (p. ej. `takabailert.com`)."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Zona Route 53 del dominio: aqui se publican la validacion del certificado y los alias."
  type        = string
  default     = ""
}

variable "index_html" {
  description = "Contenido de la pagina. Se pasa desde el entorno para que el repo tenga UNA sola copia."
  type        = string
  default     = ""
}
