terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# Exposición pública del EC2 co-locado (T-1.37).
#
# [DECISION 2026-07-09] El security group web es SEPARADO del `sg_db`, y se adjunta a
# la ENI de la instancia en vez de a la instancia. Así se puede DESCONECTAR con un solo
# `terraform destroy -target` (o `serve_enabled = false`) para cerrar el acceso público
# al instante, sin tocar la base de datos ni recrear la máquina.
#
# El 80 va abierto al mundo porque el desafío HTTP-01 de Let's Encrypt lo exige y sale
# de IPs que no podemos enumerar. Caddy solo responde ahí el reto y redirige a 443.
# El 443 queda acotado a `allowed_cidrs`: un SOC dev no tiene por qué ser público.

resource "aws_eip" "web" {
  count = var.enabled ? 1 : 0

  instance = var.instance_id
  domain   = "vpc"

  tags = { Name = "takab-dev-web" }
}

resource "aws_security_group" "web" {
  count = var.enabled ? 1 : 0

  name        = "takab-dev-web"
  description = "Ingreso HTTPS a la consola SOC (adjuntable/desmontable sin tocar la DB)"
  vpc_id      = var.vpc_id

  tags = { Name = "takab-dev-web" }
}

# ACME HTTP-01: el validador de Let's Encrypt no tiene rango fijo.
resource "aws_vpc_security_group_ingress_rule" "acme" {
  count = var.enabled ? 1 : 0

  security_group_id = aws_security_group.web[0].id
  description       = "ACME HTTP-01 (Let's Encrypt)"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  for_each = var.enabled ? toset(var.allowed_cidrs) : toset([])

  security_group_id = aws_security_group.web[0].id
  description       = "Consola SOC (HTTPS) desde ${each.value}"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  cidr_ipv4         = each.value
}

# Adjunto a la ENI: quitar este recurso cierra el acceso sin recrear la instancia.
resource "aws_network_interface_sg_attachment" "web" {
  count = var.enabled ? 1 : 0

  security_group_id    = aws_security_group.web[0].id
  network_interface_id = var.network_interface_id
}
