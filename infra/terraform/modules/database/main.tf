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

data "aws_region" "current" {}

data "aws_subnet" "db" {
  id = var.subnet_id
}

locals {
  # clave logica del secreto -> nombre del rol en Postgres
  db_roles = {
    superuser = "postgres"
    migrator  = "takab_migrator"
    app       = "takab_app"
    ingest    = "takab_ingest"
  }
}

# --- Credenciales -------------------------------------------------------------

resource "random_password" "db" {
  for_each = local.db_roles

  length           = 32
  override_special = "_-" # seguro dentro de connection strings
}

resource "aws_secretsmanager_secret" "db" {
  for_each = local.db_roles

  name                    = "takab/dev/db/${each.key}"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "db" {
  for_each = local.db_roles

  secret_id = aws_secretsmanager_secret.db[each.key].id
  secret_string = jsonencode({
    username = each.value
    password = random_password.db[each.key].result
    port     = 5432
    dbname   = "takab"
  })
}

# --- IAM de la instancia --------------------------------------------------------

resource "aws_iam_role" "db" {
  name = "takab-dev-db"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "db_ssm" {
  role       = aws_iam_role.db.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "db" {
  name = "takab-dev-db"
  role = aws_iam_role.db.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadDbSecrets"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = concat([for s in aws_secretsmanager_secret.db : s.arn], var.worker_secret_arns)
      },
      {
        Sid      = "PutBackups"
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "${var.db_backups_bucket.arn}/*"
      },
      {
        Sid      = "UseDataKey"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
        Resource = var.kms_key_arn
      },
      # Workers de ingesta co-locados en esta instancia (default dev, plan §C.1):
      # consumir las colas y publicar a sus DLQ.
      {
        Sid    = "WorkerQueues"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:DeleteMessageBatch",
          "sqs:SendMessage", "sqs:GetQueueAttributes", "sqs:GetQueueUrl",
        ]
        Resource = var.worker_queue_arns
      },
      # Pull de la imagen takab/cloud desde ECR (GetAuthorizationToken exige "*").
      {
        Sid      = "EcrAuth"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid      = "EcrPull"
        Effect   = "Allow"
        Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
        Resource = var.worker_ecr_repo_arns
      },
      # Lectura del bucket transfer: builds dev por S3 hoy; backfill (T-1.25) después.
      {
        Sid      = "WorkerTransferRead"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = var.worker_s3_read_arns
      },
      # Grant service del backfill (T-1.25) co-locado: los presigned PUT se
      # firman con ESTE rol — sin s3:PutObject en los prefijos presignados el
      # edge recibe 403 al subir (el smoke local firmaba con credenciales dev
      # y ocultaba el hueco). Acotado a los prefijos canónicos del grant.
      {
        Sid      = "WorkerPresignPut"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = var.worker_s3_presign_put_arns
      },
      # Publicaciones nube→edge vía iot-data: grants de backfill, comandos de
      # actuador (takab/cmd/*) y config sync (takab/cfg/*). Sin cmd/cfg, la API
      # firmaría bien y aun así el publish daría AccessDenied (GAP-4 · T-1.38).
      {
        Sid      = "WorkerIotPublish"
        Effect   = "Allow"
        Action   = ["iot:Publish"]
        Resource = var.worker_iot_publish_topic_arns
      },
    ]
  })
}

resource "aws_iam_instance_profile" "db" {
  name = "takab-dev-db"
  role = aws_iam_role.db.name
}

# --- Instancia + volumen de datos ---------------------------------------------
# [DECISION] RDS no soporta la extension timescaledb: EC2 autogestionada con
# Docker timescale/timescaledb-ha:pg16.

data "aws_ami" "al2023_arm64" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-arm64"]
  }
}

resource "aws_ebs_volume" "data" {
  availability_zone = data.aws_subnet.db.availability_zone
  size              = 40
  type              = "gp3"
  encrypted         = true
  kms_key_id        = var.kms_key_arn

  tags = { Name = "takab-dev-db-data" }
}

resource "aws_instance" "db" {
  ami                         = data.aws_ami.al2023_arm64.id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [var.sg_db_id]
  associate_public_ip_address = true # solo salida; el SG no admite ingreso publico
  iam_instance_profile        = aws_iam_instance_profile.db.name

  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    region            = data.aws_region.current.region
    volume_id_nodash  = replace(aws_ebs_volume.data.id, "-", "")
    db_backups_bucket = var.db_backups_bucket.name
    kms_key_arn       = var.kms_key_arn
  })
  user_data_replace_on_change = false

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
    encrypted   = true
    kms_key_id  = var.kms_key_arn
  }

  tags = {
    Name      = "takab-dev-db"
    DlmBackup = "true"
  }

  # user_data lee los secretos en el primer boot: deben existir antes.
  depends_on = [aws_secretsmanager_secret_version.db]

  # La AMI most_recent solo aplica al primer boot: una AMI nueva NO debe forzar
  # replace de la instancia (destruiria la DB y los workers co-locados). Para
  # actualizar la AMI a proposito: terraform taint / -replace explicito.
  lifecycle {
    ignore_changes = [ami]
  }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/xvdf" # en instancias Nitro aparece como /dev/nvme1n1
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.db.id

  # destroy limpio aunque el filesystem este montado
  stop_instance_before_detaching = true
}

# --- Snapshots diarios (DLM) ----------------------------------------------------

resource "aws_iam_role" "dlm" {
  name = "takab-dev-dlm"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "dlm.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "dlm" {
  role       = aws_iam_role.dlm.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "db" {
  description        = "Snapshots diarios de takab-dev-db"
  execution_role_arn = aws_iam_role.dlm.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["INSTANCE"]
    target_tags    = { DlmBackup = "true" }

    schedule {
      name      = "diario-0300utc"
      copy_tags = true

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["03:00"]
      }

      retain_rule {
        count = 7
      }
    }
  }
}
