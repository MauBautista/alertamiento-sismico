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
