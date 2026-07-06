output "evidence_bucket" {
  value = {
    name = aws_s3_bucket.this["evidence"].bucket
    arn  = aws_s3_bucket.this["evidence"].arn
  }
}

output "transfer_bucket" {
  value = {
    name = aws_s3_bucket.this["transfer"].bucket
    arn  = aws_s3_bucket.this["transfer"].arn
  }
}

output "db_backups_bucket" {
  value = {
    name = aws_s3_bucket.this["db_backups"].bucket
    arn  = aws_s3_bucket.this["db_backups"].arn
  }
}
