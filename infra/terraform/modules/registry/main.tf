terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

resource "aws_ecr_repository" "this" {
  # takab/console (T-1.39): la consola SOC va en su propia imagen (Caddy+dist).
  # cloud-images la empuja desde T-1.37, pero el repo nunca se creó — el primer
  # push real lo destapó. Creado por CLI + terraform import (el apply lo corre
  # el humano en este entorno).
  for_each = toset(["takab/cloud", "takab/console", "takab/fleet-sim"])

  name                 = each.value
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "conservar las ultimas 10 imagenes"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
