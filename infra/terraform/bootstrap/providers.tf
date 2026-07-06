# Bootstrap del backend remoto de Terraform (bucket de estado + lock).
# Se aplica UNA vez con estado LOCAL (terraform.tfstate queda aquí, gitignored).
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  profile = "takab-dev"
  region  = "us-east-2"

  default_tags {
    tags = {
      Project   = "takab"
      Env       = "dev"
      ManagedBy = "terraform"
      Scope     = "bootstrap"
    }
  }
}
