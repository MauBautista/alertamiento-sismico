# Cadenas vacías (no `null`) cuando `enabled = false`: Terraform evalúa AMBAS ramas de
# un condicional, así que un `null` aquí reventaría cualquier `"${...}/auth/callback"`
# aguas abajo aunque esa rama no se usara.

output "public_ip" {
  value = var.enabled ? aws_eip.web[0].public_ip : ""
}

# sslip.io resuelve `a-b-c-d.sslip.io` → a.b.c.d sin Route53 ni dominio propio, lo que
# le basta a Let's Encrypt para emitir un certificado real. Cuando haya dominio, esto
# se sustituye por el CNAME de verdad y Caddy no se entera.
output "public_host" {
  value = var.enabled ? "${replace(aws_eip.web[0].public_ip, ".", "-")}.sslip.io" : ""
}

output "console_url" {
  value = var.enabled ? "https://${replace(aws_eip.web[0].public_ip, ".", "-")}.sslip.io" : ""
}

output "security_group_id" {
  value = var.enabled ? aws_security_group.web[0].id : ""
}
