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
