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

# [T-2.72] Los prefijos viajan con el bucket para que el modulo `database` acote
# su IAM y su archivador contra EXACTAMENTE los mismos literales que gobiernan la
# expiracion. Duplicarlos en el otro modulo es como se rompe una cadena PITR sin
# que ningun plan se ponga rojo.
output "db_backups_prefixes" {
  value = {
    dump_key = var.db_dump_key_prefix
    pitr     = var.pitr_prefix
    wal      = local.pitr_wal_prefix
    base     = local.pitr_base_prefix
  }
}

output "pitr_server_name" {
  value = var.pitr_server_name
}

# La retencion baja al modulo `database` porque alli es donde se programa el
# backup base y donde se comprueba la desigualdad que mantiene viva la cadena
# (`wal_days >= intervalo * margen`). Aqui solo se decide; alli se sostiene.
output "pitr_retention" {
  value = var.pitr_retention
}

# [T-2.72] La tabla de retencion, tal cual, para que `tests/lifecycle.tftest.hcl`
# pueda recorrerla ENTERA — todas las reglas de todos los buckets en una sola
# lista— en vez de comprobar una por una y quedarse ciego ante la siguiente.
#
# Se asierta sobre la tabla y no sobre `aws_s3_bucket_lifecycle_configuration.
# this[*].rule` por una razon medida: Terraform 1.15.8 REVIENTA (`panic: value
# has marks, so it cannot be serialized as JSON`) al renderizar el diagnostico de
# una asercion fallida que referencie esa lista de bloques. La asercion se ponia
# roja, si, pero en vez del mensaje salia un volcado de pila de Go — y una guardia
# que al dispararse parece un bug de Terraform es una guardia que alguien borra.
# Un escalar de dentro de la lista (`rule[0].id`) si se renderiza bien, y eso es
# lo que usa la asercion de cableado del test.
output "lifecycle_rules" {
  value = local.lifecycle_rules
}
