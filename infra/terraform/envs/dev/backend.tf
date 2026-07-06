terraform {
  backend "s3" {
    bucket  = "takab-tfstate-634882473845"
    key     = "env/dev.tfstate"
    region  = "us-east-2"
    profile = "takab-dev"
    # lockfile nativo S3 (TF >= 1.10) + tabla DynamoDB durante la transicion
    use_lockfile   = true
    dynamodb_table = "takab-tflock"
  }
}
