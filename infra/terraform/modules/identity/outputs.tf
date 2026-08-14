output "user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "user_pool_arn" {
  value = aws_cognito_user_pool.this.arn
}

output "client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "hosted_ui_domain" {
  value = "${aws_cognito_user_pool_domain.this.domain}.auth.${data.aws_region.current.region}.amazoncognito.com"
}

output "issuer" {
  value = "https://cognito-idp.${data.aws_region.current.region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
}

# --- Superficie móvil (T-2.02 · decisión #7) --------------------------------

output "mobile_tactical_client_id" {
  value = aws_cognito_user_pool_client.mobile_tactical.id
}

output "occupants_user_pool_id" {
  value = aws_cognito_user_pool.occupants.id
}

output "occupants_user_pool_arn" {
  value = aws_cognito_user_pool.occupants.arn
}

output "occupants_client_id" {
  value = aws_cognito_user_pool_client.mobile_occupants.id
}

output "occupants_hosted_ui_domain" {
  value = "${aws_cognito_user_pool_domain.occupants.domain}.auth.${data.aws_region.current.region}.amazoncognito.com"
}

output "occupants_issuer" {
  value = "https://cognito-idp.${data.aws_region.current.region}.amazonaws.com/${aws_cognito_user_pool.occupants.id}"
}

# --- [T-2.78.b] Identidad de dominio ------------------------------------------

output "ses_domain_identity_arn" {
  description = "ARN de la identidad de dominio (null si no hay dominio). INFORMATIVO: el permiso de envio del worker NO se toma de aqui — `identity -> serve -> database` ya es una cadena y leerlo cerraria el ciclo, asi que `modules/database` construye el mismo ARN desde `notify_ses_domain`, que es la MISMA variable del entorno."
  value       = local.ses_domain_enabled ? aws_sesv2_email_identity.domain[0].arn : null
}

output "ses_feedback_topic_arn" {
  description = "Topic SNS donde caen rebotes, quejas, rechazos y fallos de render (null si no hay dominio)."
  value       = local.ses_domain_enabled ? aws_sns_topic.ses_feedback[0].arn : null
}

# LOS REGISTROS QUE HAY QUE PUBLICAR, derivados de la respuesta de la API.
#
# Este output es el que hace innecesario copiar valores de la consola a mano
# cuando el DNS del dominio NO vive en Route 53 (que es el caso por defecto: la
# zona de un dominio comprado en cualquier registrador no esta en esta cuenta).
# Con `ses_route53_zone_id` puesto, los registros ya se crean solos y esto sirve
# para verificarlos.
#
# Ninguno de estos valores esta escrito en el repo: los tokens de DKIM salen de
# `dkim_signing_attributes[0].tokens` —que es literalmente lo que devolvio la API
# al crear la identidad— y el host del MX se compone con la region del proveedor.
# Por eso el output solo se puede leer DESPUES del apply, y por eso no hay ningun
# valor que pueda quedarse rancio en un fichero.
output "ses_domain_dns_records" {
  description = "Registros DNS que debe publicar el dominio para que DKIM, SPF/MAIL FROM y DMARC funcionen. Derivados de la respuesta de la API: no hay literales en el repo."
  value = local.ses_domain_enabled ? {
    dkim = [
      for t in aws_sesv2_email_identity.domain[0].dkim_signing_attributes[0].tokens : {
        name  = "${t}._domainkey.${var.ses_domain}"
        type  = "CNAME"
        value = "${t}.dkim.amazonses.com"
      }
    ]
    mail_from_mx = {
      name  = local.ses_mail_from_domain
      type  = "MX"
      value = "10 feedback-smtp.${data.aws_region.current.region}.amazonses.com"
    }
    mail_from_spf = {
      name  = local.ses_mail_from_domain
      type  = "TXT"
      value = "v=spf1 include:amazonses.com ~all"
    }
    dmarc = {
      name  = "_dmarc.${var.ses_domain}"
      type  = "TXT"
      value = local.ses_dmarc_value
    }
  } : null
}
