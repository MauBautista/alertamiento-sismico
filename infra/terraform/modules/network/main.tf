terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

data "aws_region" "current" {}

locals {
  # Solo subredes públicas: sin NAT ni subredes privadas (costo dev).
  public_subnets = {
    "us-east-2a" = "10.20.0.0/24"
    "us-east-2b" = "10.20.1.0/24"
  }
}

resource "aws_vpc" "this" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "takab-dev" }
}

resource "aws_subnet" "public" {
  for_each = local.public_subnets

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = each.value
  map_public_ip_on_launch = true

  tags = { Name = "takab-dev-public-${each.key}" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = { Name = "takab-dev" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = { Name = "takab-dev-public" }
}

resource "aws_route" "internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

# Endpoint tipo gateway: el tráfico a S3 no sale por el IGW (gratis).
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.public.id]

  tags = { Name = "takab-dev-s3" }
}

resource "aws_security_group" "workers" {
  name        = "takab-dev-workers"
  description = "Workers (ECS/consumidores) - sin ingreso, todo egreso"
  vpc_id      = aws_vpc.this.id

  tags = { Name = "takab-dev-workers" }
}

resource "aws_vpc_security_group_egress_rule" "workers_all" {
  security_group_id = aws_security_group.workers.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_security_group" "db" {
  name        = "takab-dev-db"
  description = "DB Timescale - 5432 solo desde workers"
  vpc_id      = aws_vpc.this.id

  tags = { Name = "takab-dev-db" }
}

resource "aws_vpc_security_group_ingress_rule" "db_from_workers" {
  security_group_id            = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.workers.id
}

resource "aws_vpc_security_group_egress_rule" "db_all" {
  security_group_id = aws_security_group.db.id
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}
