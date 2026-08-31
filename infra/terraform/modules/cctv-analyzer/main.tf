# El Lambda que cuenta personas en los clips de CCTV (T-3.12.b · D-24).
#
# POR QUE UN LAMBDA Y NO UN WORKER MAS EN EL ECS
# ──────────────────────────────────────────────
# El conteo es esporadico por naturaleza: se ejecuta una vez por incidente con camara, y
# eso son unas cuantas veces al ano por sitio. Un contenedor residente cobraria 24/7 por
# estar disponible para un trabajo que casi nunca llega, y ademas cargaria el runtime de
# inferencia dentro del mismo servicio que sostiene la API — que es justo lo que la
# separacion de procesos del gabinete evita en el borde, por la misma razon.
#
# LA VPC NO ES OPCIONAL AQUI
# ──────────────────────────
# El handler escribe en Postgres, que vive DENTRO de la VPC y solo acepta al SG de
# workers. Un Lambda fuera de la VPC no llega. Y al meterlo dentro pierde la salida a
# internet — que no necesita: S3 entra por el VPC endpoint que `network` ya crea, y el
# modelo va horneado en la imagen precisamente para no depender de una descarga.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

resource "aws_iam_role" "this" {
  name = "takab-dev-cctv-analyzer"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Interfaces de red en la VPC. Es la politica gestionada de AWS y NO se sustituye por una
# a medida: sus permisos son sobre `ec2:*NetworkInterface` con condiciones que cambian
# cuando AWS cambia el mecanismo, y una copia local se queda rancia en silencio.
resource "aws_iam_role_policy_attachment" "vpc" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "this" {
  name = "takab-dev-cctv-analyzer"
  role = aws_iam_role.this.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # SOLO leer. El Lambda no borra evidencia: la retencion la aplica la politica de
        # ciclo de vida del bucket, y un rol que pueda borrar clips es un rol que puede
        # borrar la prueba de un incidente.
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${var.evidence_bucket_arn}/evidence/*"
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = var.queue_arn
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.db_secret_arn
      },
    ]
  })
}

resource "aws_lambda_function" "this" {
  function_name = "takab-dev-cctv-analyzer"
  role          = aws_iam_role.this.arn
  package_type  = "Image"
  image_uri     = var.image_uri

  # 900 s es el techo del servicio. Un clip de once minutos a 0.5 fps son ~330 fotogramas
  # y ~13 ms cada uno en x86: del orden de 5 s de inferencia. El resto del presupuesto es
  # para la descarga y el goteo, que puede traer cientos de JPEG.
  timeout = 900
  # 3008 MB no es por memoria: en Lambda la CPU escala CON la memoria, y la inferencia es
  # lo que domina. Medir si baja es trabajo de la primera ejecucion real, no de aqui.
  memory_size = 3008

  vpc_config {
    subnet_ids         = var.subnet_ids
    security_group_ids = [var.security_group_id]
  }

  environment {
    variables = {
      TAKAB_CCTV_BUCKET = var.evidence_bucket
      DATABASE_URL      = var.database_url
    }
  }
}

resource "aws_lambda_event_source_mapping" "cola" {
  event_source_arn = var.queue_arn
  function_name    = aws_lambda_function.this.arn

  # De uno en uno, y es deliberado: cada clip es una unidad de trabajo cara e
  # independiente. Un lote de diez que falla en el septimo reentrega los diez, y volveria
  # a pagar la inferencia de los seis que ya estaban bien.
  batch_size = 1
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${aws_lambda_function.this.function_name}"
  retention_in_days = var.log_retention_days
}
