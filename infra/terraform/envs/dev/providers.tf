terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
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
    }
  }
}

# [T-2.156] CloudFront SOLO lee certificados de ACM de us-east-1, viva donde viva
# el resto de la cuenta. Sin este alias el apply falla con un error que no nombra
# la region, y se diagnostica mirando el sitio equivocado.
provider "aws" {
  alias   = "us_east_1"
  profile = "takab-dev"
  region  = "us-east-1"

  default_tags {
    tags = {
      Project   = "takab"
      Env       = "dev"
      ManagedBy = "terraform"
    }
  }
}
