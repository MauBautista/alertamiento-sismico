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
  buckets = {
    evidence   = "takab-dev-evidence-${var.account_id}"
    transfer   = "takab-dev-transfer-${var.account_id}"
    db_backups = "takab-dev-db-backups-${var.account_id}"
  }
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets

  bucket        = each.value
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = local.buckets

  bucket                  = aws_s3_bucket.this[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "tls_only" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.this[each.key].arn,
        "${aws_s3_bucket.this[each.key].arn}/*",
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })

  depends_on = [aws_s3_bucket_public_access_block.this]
}

# evidence: la inmutabilidad (Object Lock) es requisito de prod; en dev basta
# versioning + SSE-KMS.

# La policy que permite a S3 publicar en la cola vive en modules/messaging
# (condicion por cuenta) para evitar un ciclo storage<->messaging.
resource "aws_s3_bucket_notification" "transfer" {
  bucket = aws_s3_bucket.this["transfer"].id

  queue {
    queue_arn     = var.backfill_queue_arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "backfill/"
  }
}

# T-1.25: la evidencia miniSEED subida por presigned PUT se registra en
# evidence_objects via el worker de backfill (verifica sha256 y linkea el
# incidente por event_uuid). La queue policy por cuenta ya lo permite.
resource "aws_s3_bucket_notification" "evidence" {
  bucket = aws_s3_bucket.this["evidence"].id

  queue {
    queue_arn     = var.backfill_queue_arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "evidence/"
  }
}

# --- [T-2.72] LA TABLA DE RETENCION -------------------------------------------
#
# Toda la retencion de S3 del proyecto, en un solo sitio y como DATOS. Antes eran
# reglas sueltas escritas a mano en dos recursos distintos, y esa forma tenia dos
# defectos que costaron caro:
#
# 1. `Expiration` sobre un bucket VERSIONADO —los tres lo son— NO BORRA UN BYTE.
#    Pone un delete marker y deja la version anterior como noncurrent,
#    facturandose para siempre. Doc de AWS (S3 User Guide, "Examples of S3
#    Lifecycle configurations"): "Amazon S3 removes current versions 60 days after
#    they're created by adding a delete marker for each of the current object
#    versions. This process makes the current version noncurrent, and the delete
#    marker becomes the current version." Y: "The NoncurrentVersionExpiration
#    action doesn't apply to the current object versions. It removes only the
#    noncurrent versions." La regla `expira-60d` del bucket de respaldos llevaba
#    asi desde 2026-07 y `expira-30d` del de transferencia tambien: parecian una
#    politica de retencion y eran un cambio de etiqueta. Peor para el PITR: el
#    delete marker ESCONDE el objeto al restaurador aunque los bytes sigan ahi.
#    Los delete markers huerfanos los limpia S3 solo, porque estas reglas
#    especifican `Days` (misma pagina: "When you specify the Days tag, Amazon S3
#    automatically performs ExpiredObjectDeleteMarker cleanup when the delete
#    markers are old enough to satisfy the age criteria").
#
# 2. Un `prefix = ""` en el bucket de respaldos era un CAJON DE SASTRE sobre una
#    CADENA. Un dump suelto se vale por si mismo; una cadena PITR no: un backup
#    base sin sus WAL no llega a ningun punto en el tiempo y unos WAL sin su base
#    no arrancan. Una regla uniforme borra exactamente la mitad que hacia falta, y
#    eso NO SE NOTA HASTA QUE SE INTENTA RESTAURAR. S3 no sabe expresar "todo
#    menos este prefijo" —no hay negacion en un filtro—, asi que un filtro vacio
#    alcanza SIEMPRE la cadena, diga lo que diga el comentario de al lado.
#
# Como TABLA las dos cosas se vuelven comprobables de una vez y para todos los
# buckets: `tests/lifecycle.tftest.hcl` recorre esta estructura entera, asi que
# una regla nueva —del bucket que sea— tiene que pasar por las mismas guardias.
# Por eso `noncurrent_days` es un CAMPO y no algo que el `dynamic` de abajo
# rellene solo: si se derivara, la guardia no podria fallar nunca y seria un
# adorno.
#
# ESTE es el unico podador de la cadena PITR. El subcomando de poda de barman
# esta instalado en la imagen de la DB y podria podar tambien; no lo hace, y no
# por convencion: el rol de la instancia no tiene `s3:Delete*` sobre este bucket
# (`modules/database`). Dos podadores a ciegas sobre los mismos objetos son una
# carrera, y el perdedor es el restore.
#
# `evidence` no aparece aqui A PROPOSITO: la evidencia de incidentes no se poda
# por retencion (regla de oro 11).
locals {
  # `<prefijo><servidor>/wals/` y `<prefijo><servidor>/base/`: no es una
  # convencion nuestra, es donde escribe barman-cloud. Comprobado ejecutando la
  # herramienta de la propia imagen `timescale/timescaledb-ha:pg16` contra un S3
  # local: `barman-cloud-wal-archive s3://bucket/pitr <servidor> <wal>` deposito
  # `pitr/<servidor>/wals/0000000100000000/000000010000000000000001`, y
  # `barman-cloud-backup` deposito `pitr/<servidor>/base/<sello>/data.tar.gz`.
  pitr_wal_prefix  = "${var.pitr_prefix}${var.pitr_server_name}/wals/"
  pitr_base_prefix = "${var.pitr_prefix}${var.pitr_server_name}/base/"

  lifecycle_rules = {
    # Staging efimero edge->nube. Aqui el filtro vacio SI es correcto: una sola
    # clase de objeto y ninguna cadena que partir.
    transfer = [
      {
        id                   = "expira-30d"
        prefix               = ""
        expiration_days      = 30
        noncurrent_days      = 1
        abort_multipart_days = null
      },
    ]

    db_backups = [
      # El dump logico nocturno. Su prefijo es el MISMO literal que la clave que
      # escribe el cron (`modules/database/user_data.sh.tpl`) y que el
      # `s3:PutObject` del rol; hay un test que se pone rojo si divergen, porque
      # ahora esa divergencia no solo rompe la retencion: mata la escritura.
      {
        id                   = "expira-60d-dump-logico"
        prefix               = var.db_dump_key_prefix
        expiration_days      = 60
        noncurrent_days      = 1
        abort_multipart_days = null
      },
      # Las dos mitades de la CADENA, al mismo ritmo a proposito: son un solo
      # objeto logico partido en dos prefijos porque asi lo escribe la
      # herramienta, no porque tengan vidas distintas.
      {
        id                   = "pitr-wal"
        prefix               = local.pitr_wal_prefix
        expiration_days      = var.pitr_retention.wal_days
        noncurrent_days      = 1
        abort_multipart_days = null
      },
      {
        id                   = "pitr-backup-base"
        prefix               = local.pitr_base_prefix
        expiration_days      = var.pitr_retention.wal_days
        noncurrent_days      = 1
        abort_multipart_days = null
      },
      # Las partes de un multipart abortado NO son objetos: no aparecen en un
      # listado y ninguna regla de expiracion las alcanza. Se facturan
      # indefinidamente y esta es la unica forma de limpiarlas por politica.
      {
        id                   = "pitr-aborta-multipart-incompleto"
        prefix               = var.pitr_prefix
        expiration_days      = null
        noncurrent_days      = null
        abort_multipart_days = 7
      },
    ]
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = local.lifecycle_rules

  bucket = aws_s3_bucket.this[each.key].id

  dynamic "rule" {
    for_each = each.value

    content {
      id     = rule.value.id
      status = "Enabled"

      filter {
        prefix = rule.value.prefix
      }

      dynamic "expiration" {
        for_each = rule.value.expiration_days == null ? [] : [rule.value.expiration_days]
        content {
          days = expiration.value
        }
      }

      dynamic "noncurrent_version_expiration" {
        for_each = rule.value.noncurrent_days == null ? [] : [rule.value.noncurrent_days]
        content {
          noncurrent_days = noncurrent_version_expiration.value
        }
      }

      dynamic "abort_incomplete_multipart_upload" {
        for_each = rule.value.abort_multipart_days == null ? [] : [rule.value.abort_multipart_days]
        content {
          days_after_initiation = abort_incomplete_multipart_upload.value
        }
      }
    }
  }
}

# Las dos configuraciones existian como recursos con nombre propio. Sin estos
# bloques, el apply DESTRUIRIA la del bucket de transferencia para volver a
# crearla igual, y entre una cosa y otra ese bucket se quedaria sin retencion.
# `moved` hace el cambio de direccion sin tocar AWS.
moved {
  from = aws_s3_bucket_lifecycle_configuration.transfer
  to   = aws_s3_bucket_lifecycle_configuration.this["transfer"]
}

moved {
  from = aws_s3_bucket_lifecycle_configuration.db_backups
  to   = aws_s3_bucket_lifecycle_configuration.this["db_backups"]
}

