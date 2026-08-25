terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 6.0"
      configuration_aliases = [aws.us_east_1]
    }
  }
}

locals {
  on = var.enabled && var.domain != "" && var.route53_zone_id != ""
}

# --- El bucket: PRIVADO. CloudFront entra por OAC, no por web publica de S3 ----
#
# `aws_s3_bucket_website_configuration` exigiria bucket publico, y un bucket
# publico es una fuga esperando a que alguien suba algo por error. Con OAC el
# bucket no acepta a nadie mas que a ESTA distribucion, comprobado por condicion
# de ARN en la politica.
resource "aws_s3_bucket" "site" {
  count         = local.on ? 1 : 0
  bucket        = "takab-dev-site-${replace(var.domain, ".", "-")}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "site" {
  count                   = local.on ? 1 : 0
  bucket                  = aws_s3_bucket.site[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  count  = local.on ? 1 : 0
  bucket = aws_s3_bucket.site[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# [landing] El contenido ya NO lo posee Terraform: lo publica `make landing-deploy`
# (deploy/landing/deploy.sh) con `aws s3 sync` desde landing/dist, fijando
# Cache-Control por clase de fichero. Terraform posee el CONTINENTE (bucket,
# distribucion, certificado, DNS); el contenido tiene un solo dueno y es git.
# El antiguo `aws_s3_object.index` salio del estado con un `removed` block en el
# entorno, sin destruirse (transicion sin ventana rota).

# Versionado: la red de emergencia del rollback sin rebuild, y lo que hace
# reversible el `--delete` del sync. El lifecycle poda versiones viejas a 90
# dias para que la red no se convierta en una factura.
resource "aws_s3_bucket_versioning" "site" {
  count  = local.on ? 1 : 0
  bucket = aws_s3_bucket.site[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "site" {
  count  = local.on ? 1 : 0
  bucket = aws_s3_bucket.site[0].id
  # El versioning debe existir antes de podar versiones no-actuales.
  depends_on = [aws_s3_bucket_versioning.site]

  rule {
    id     = "podar-versiones-no-actuales"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
    expiration {
      expired_object_delete_marker = true
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# --- Certificado: OBLIGATORIAMENTE en us-east-1 --------------------------------
#
# CloudFront solo lee certificados de ACM de us-east-1, sin importar donde viva
# el resto. Por eso este modulo recibe un provider con alias en vez de heredar el
# de la cuenta: si se olvida, el apply falla con un error que no menciona la
# region y se diagnostica mal.
resource "aws_acm_certificate" "site" {
  count                     = local.on ? 1 : 0
  provider                  = aws.us_east_1
  domain_name               = var.domain
  subject_alternative_names = ["www.${var.domain}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# La validacion la publica Terraform en la zona: es la razon de D-12 para elegir
# Route 53 sobre el DNS del registrador, y aqui se cobra sola.
resource "aws_route53_record" "validacion" {
  for_each = local.on ? {
    for d in aws_acm_certificate.site[0].domain_validation_options : d.domain_name => d
  } : {}

  zone_id         = var.route53_zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  records         = [each.value.resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "site" {
  count                   = local.on ? 1 : 0
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.site[0].arn
  validation_record_fqdns = [for r in aws_route53_record.validacion : r.fqdn]
}

# --- CloudFront ---------------------------------------------------------------

resource "aws_cloudfront_origin_access_control" "site" {
  count                             = local.on ? 1 : 0
  name                              = "takab-dev-site-${replace(var.domain, ".", "-")}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "site" {
  count               = local.on ? 1 : 0
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  aliases             = [var.domain, "www.${var.domain}"]
  comment             = "Sitio publico de ${var.domain} (T-2.156)"
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.site[0].bucket_regional_domain_name
    origin_id                = "s3-site"
    origin_access_control_id = aws_cloudfront_origin_access_control.site[0].id
  }

  default_cache_behavior {
    target_origin_id = "s3-site"
    # HTTP se REDIRIGE, no se sirve: una pagina que declara el dominio remitente
    # de un sistema de alertamiento no puede viajar en claro.
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # CachingOptimized, gestionada por AWS.
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  # [T-2.156] Una ruta que no existe devolvia el XML de S3 con AccessDenied: feo,
  # y ademas delata que detras hay un bucket. Con OAC y sin `s3:ListBucket`, una
  # clave ausente da 403 y NO 404 —S3 no distingue "no existe" de "no puedes
  # verlo", a proposito—, asi que hay que mapear los dos.
  #
  # El codigo que se devuelve es 404 y no 200: la pagina se sirve, pero la ruta
  # de verdad no existe y decirlo importa. Un 200 sobre cualquier ruta convierte
  # el sitio en un espejo que afirma tener todo lo que le pidan.
  # [landing] La pagina de error ahora es /404.html (multi-pagina real, generada
  # por el build de landing/). El CODIGO sigue siendo 404: la decision anti-espejo
  # de T-2.156 no cambia con la landing nueva.
  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 300
  }

  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 300
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.site[0].certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

# La politica del bucket se escribe DESPUES de la distribucion porque cita su ARN:
# sin la condicion `AWS:SourceArn`, cualquier distribucion de cualquier cuenta
# podria usar este bucket como origen.
resource "aws_s3_bucket_policy" "site" {
  count  = local.on ? 1 : 0
  bucket = aws_s3_bucket.site[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "SoloEstaDistribucion"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.site[0].arn}/*"
      Condition = {
        StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.site[0].arn }
      }
    }]
  })
}

# --- DNS: el dominio deja de no resolver --------------------------------------

resource "aws_route53_record" "alias" {
  for_each = local.on ? toset([var.domain, "www.${var.domain}"]) : toset([])

  zone_id = var.route53_zone_id
  name    = each.value
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site[0].domain_name
    zone_id                = aws_cloudfront_distribution.site[0].hosted_zone_id
    evaluate_target_health = false
  }
}
