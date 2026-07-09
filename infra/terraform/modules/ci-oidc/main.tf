terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

locals {
  github_repo = "MauBautista/alertamiento-sismico"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS ya no valida el thumbprint para GitHub, pero el campo es requerido.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

resource "aws_iam_role" "ci_plan" {
  name = "takab-ci-plan"

  # [T-1.44 · HIGH #24 de la auditoría] El sub se ancla EXACTO a main. Con el
  # `repo:...:*` anterior, cualquier ref —incluido el run de un PR malicioso—
  # podia asumir un rol con ReadOnlyAccess + lectura del tfstate (que contiene
  # material sensible) sin que ningun workflow legitimo lo usara siquiera: el
  # paso plan-only sigue siendo un TODO en ci.yml. Los jobs de PR corren tests
  # hermeticos y NO necesitan AWS. StringEquals, no StringLike: sin comodines
  # en la superficie mas federada de la cuenta.
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${local.github_repo}:ref:refs/heads/main"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "readonly" {
  role       = aws_iam_role.ci_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# Acceso al backend: leer estado + tomar/soltar lock (lockfile S3 y DynamoDB).
resource "aws_iam_role_policy" "state" {
  name = "tfstate-plan"
  role = aws_iam_role.ci_plan.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListStateBucket"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = var.state_bucket_arn
      },
      {
        Sid      = "ReadState"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${var.state_bucket_arn}/*"
      },
      {
        Sid      = "S3Lockfile"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:DeleteObject"]
        Resource = "${var.state_bucket_arn}/env/*.tflock"
      },
      {
        Sid      = "DynamoLock"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
        Resource = var.lock_table_arn
      },
    ]
  })
}
