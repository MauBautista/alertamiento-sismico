output "queues" {
  value = {
    for k, q in aws_sqs_queue.this : k => {
      url = q.url
      arn = q.arn
    }
  }

  # La notificacion S3 del bucket transfer valida permisos al crearse: quien
  # consuma este output debe esperar tambien a la queue policy.
  depends_on = [aws_sqs_queue_policy.backfill_from_s3]
}

output "dlq_arns" {
  value = { for k, q in aws_sqs_queue.dlq : k => q.arn }
}

# Los consumidores EXIGEN estas URLs al arrancar (ingest/__main__ hace
# SystemExit sin ellas): los REJECT explicitos se envian por URL. El redrive
# de SQS va por ARN y no depende de esto.
output "dlq_urls" {
  value = { for k, q in aws_sqs_queue.dlq : k => q.url }
}
