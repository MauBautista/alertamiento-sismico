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
data "aws_caller_identity" "current" {}

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

  # Namespace de las metricas propias. Vive en un local porque lo consumen DOS
  # sitios que tienen que decir lo mismo: la condicion de IAM que acota
  # `PutMetricData` y el publicador de la edad del archivado (T-2.72). Si
  # divergieran, la metrica se rechazaria con AccessDenied y la alarma se quedaria
  # ciega sin que nada pareciera roto.
  ops_metrics_namespace = "Takab/Ops"

  # [T-2.72] Nombre de la metrica que mide el RPO. El otro extremo del cable esta
  # en `modules/observability` (alarma `wal_archive_stalled`) y hay una asercion
  # en cada lado, porque Terraform no puede leer un script desde otro modulo.
  wal_archive_metric_name = "WalArchiveAgeSeconds"

  # [T-2.72.b] La edad del ANCLA de la cadena. `WalArchiveAgeSeconds` mide la
  # cadena de WAL y no su ancla: un `barman-cloud-backup` que falle cada semana no
  # la mueve ni un segundo y la cadena esta rota igual.
  base_backup_metric_name = "BaseBackupAgeSeconds"

  # [T-2.81.a] El reloj de la RETENCION DE PII. Mide cuanto hace que termino BIEN
  # la ultima corrida del job (`pii_retention_runs`), no si el cron salio con 0:
  # una corrida que aborta deja fila con `ok = false`, la edad sigue creciendo y
  # la alarma suena. El otro extremo del cable esta en `modules/observability`.
  pii_retention_metric_name = "PiiRetentionAgeSeconds"

  # [T-2.72.c] El disco. `disk_used_percent` NO existe en las metricas nativas de
  # EC2 (AWS/EC2 solo trae CPU, red, EBS y status checks: el hipervisor no ve
  # dentro del filesystem). Se publica desde la instancia por el mismo cron que ya
  # publica el reloj del RPO, en vez de instalar el agente de CloudWatch: un
  # demonio mas en la maquina que sostiene la DB, la API y los workers es un
  # demonio mas que puede morir en silencio.
  data_disk_metric_name = "DataDiskUsedPercent"

  # [T-2.78.b] Identidades desde las que el worker `notify` puede enviar. El ARN
  # del dominio se COMPONE aqui (no llega hecho) por la misma razon que los topics
  # de IoT: leer el output de `module.identity` cerraria el ciclo
  # `identity -> serve -> database`.
  notify_ses_arns = concat(
    var.notify_ses_identity_arns,
    var.notify_ses_domain != "" ? [
      "arn:aws:ses:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:identity/${var.notify_ses_domain}"
    ] : [],
  )

  # Raiz de la cadena PITR tal y como la espera barman-cloud: SIN barra final —
  # la herramienta compone `<url>/<servidor>/wals/...` por su cuenta (verificado
  # ejecutandola contra un S3 local desde la propia imagen de la DB).
  pitr_root = trimsuffix(var.pitr.prefix, "/")

  # [T-2.73.a] El respaldo logico nocturno + la huella del origen. Comparte con
  # el dump el bucket, el prefijo, la clave KMS y la region: si divergieran, la
  # huella caeria fuera de la regla de expiracion y fuera del `s3:PutObject` del
  # rol, y el cron moriria con AccessDenied sin que nada se pusiera rojo.
  backup_setup_script = templatefile("${path.module}/backup_setup.sh.tpl", {
    bucket      = var.db_backups_bucket.name
    dump_prefix = var.dump_key_prefix
    region      = data.aws_region.current.region
    kms_key_arn = var.kms_key_arn
    # El unico secreto que este camino necesita, y NO viaja aqui: solo su
    # identificador. Lo resuelve la instancia en tiempo de ejecucion con su
    # propio rol, igual que hace `user_data` desde el primer boot.
    superuser_secret       = aws_secretsmanager_secret.db["superuser"].arn
    coordination_timeout_s = var.dump_coordination_timeout_s
  })

  # [T-2.81.a] Los plazos de retencion, traducidos a las variables de entorno que
  # lee cada regla (`privacy/retention.RetentionRule.env_var`:
  # `push_tokens.token` -> `TAKAB_API_RETENTION_PUSH_TOKENS_TOKEN_DAYS`). La
  # traduccion se hace AQUI y no en el script para que el mapa de Terraform se
  # escriba con la clave de la regla —que es la que sale en el informe del
  # simulacro— y no con un nombre de variable de entorno que nadie reconoce.
  #
  # Vacio por defecto, y no es un descuido: sin plazo cada regla queda
  # DESHABILITADA y la corrida no toca una fila. El default bajo incertidumbre es
  # no borrar nada — una retencion inventada por quien escribio el terraform no
  # es una politica de privacidad, es perdida de datos con buena intencion.
  pii_retention_env = join("\n", [
    for clave, dias in var.pii_retention_windows_days :
    "TAKAB_API_RETENTION_${upper(replace(clave, ".", "_"))}_DAYS=${dias}"
  ])

  prune_pii_setup_script = templatefile("${path.module}/prune_pii_setup.sh.tpl", {
    region           = data.aws_region.current.region
    metric_namespace = local.ops_metrics_namespace
    metric_name      = local.pii_retention_metric_name
    # El DSN de `takab_app` y no el del superusuario: el job se degrada a ese rol
    # el solo, asi que darselo desde fuera convierte la degradacion en un no-op
    # comprobable y ademas ahorra a esta maquina un uso mas de la contraseña del
    # superusuario. Como en el respaldo, aqui solo viaja el IDENTIFICADOR del
    # secreto; la instancia lo resuelve con su propio rol en tiempo de ejecucion.
    app_secret    = aws_secretsmanager_secret.db["app"].arn
    retention_env = local.pii_retention_env
  })

  pitr_setup_script = templatefile("${path.module}/pitr_setup.sh.tpl", {
    bucket            = var.db_backups_bucket.name
    pitr_root         = local.pitr_root
    server_name       = var.pitr.server_name
    region            = data.aws_region.current.region
    archive_timeout_s = var.wal_archive_timeout_s
    metric_namespace  = local.ops_metrics_namespace
    metric_name       = local.wal_archive_metric_name

    # [T-2.72.b · T-2.72.c] Los otros dos relojes: el del ANCLA y el del DISCO.
    # Sus nombres bajan desde el mismo sitio que el del RPO para que el par
    # namespace+metrica no pueda divergir de las alarmas que los vigilan.
    base_backup_metric_name = local.base_backup_metric_name
    data_disk_metric_name   = local.data_disk_metric_name

    # La cadencia del backup base SALE del intervalo declarado, que es el mismo
    # numero con el que `modules/storage` calcula la retencion. `*/N` en el dia
    # del mes tiene un hueco maximo de exactamente N dias (en el cambio de mes el
    # hueco se acorta, nunca se alarga), asi que la desigualdad de la cadena
    # sigue siendo valida.
    base_backup_dom = "*/${var.pitr.base_backup_interval_days}"
  })
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
    Statement = concat([
      {
        Sid      = "ReadDbSecrets"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = concat([for s in aws_secretsmanager_secret.db : s.arn], var.worker_secret_arns)
      },
      # [T-2.72] Escritura de respaldos, ACOTADA A LOS DOS PREFIJOS que existen.
      # Antes era `${bucket}/*`: cualquier clave del bucket, incluida la cadena
      # PITR entera. Los prefijos son los mismos literales que gobiernan la
      # expiracion en `modules/storage` y llegan por variable justamente para que
      # no haya dos copias que puedan divergir.
      {
        Sid    = "PutBackups"
        Effect = "Allow"
        Action = "s3:PutObject"
        Resource = [
          "${var.db_backups_bucket.arn}/${var.dump_key_prefix}*",
          "${var.db_backups_bucket.arn}/${var.pitr.prefix}*",
        ]
      },
      # El backup base sube en MULTIPART (barman parte el tar y llama a
      # create/upload/complete_multipart_upload — leido en
      # `barman/cloud_providers/aws_s3.py` dentro de la imagen que corre la DB).
      # Sin el permiso de aborto, un backup que falle a la mitad deja partes
      # invisibles en el listado y facturandose, y la herramienta no puede
      # limpiarlas.
      #
      # FICHADO, y NO es regresion de T-2.72: el dump nocturno tiene el mismo
      # agujero desde que existe. `aws s3 cp - s3://...` lee de stdin, o sea que
      # el CLI no sabe el tamaño de antemano y sube en multipart obligatoriamente;
      # ese prefijo no tiene ni permiso de aborto ni regla de barrido (la de la
      # tabla de `modules/storage` cubre solo la raiz PITR). Un `pg_dump` que
      # muera a la mitad deja partes facturandose para siempre. Arreglo: un campo
      # `abort_multipart_days` en la fila del dump de esa tabla mas este mismo
      # permiso sobre `${dump_key_prefix}*`. Fuera del alcance de esta tarea a
      # proposito: toca el respaldo que hoy funciona.
      {
        Sid      = "PitrAbortMultipart"
        Effect   = "Allow"
        Action   = "s3:AbortMultipartUpload"
        Resource = "${var.db_backups_bucket.arn}/${var.pitr.prefix}*"
      },
      # [T-2.72] LEER los respaldos, que es lo que hasta hoy NO se podia hacer.
      # El rol solo tenia `s3:PutObject`: la instancia escribia sus dumps y no
      # podia recuperarlos. Un respaldo que no se puede leer desde donde hay que
      # restaurarlo no es un respaldo, es un gasto de S3.
      {
        Sid    = "GetBackups"
        Effect = "Allow"
        Action = "s3:GetObject"
        Resource = [
          "${var.db_backups_bucket.arn}/${var.dump_key_prefix}*",
          "${var.db_backups_bucket.arn}/${var.pitr.prefix}*",
        ]
      },
      # `s3:ListBucket` es permiso de BUCKET, no de objeto: se concede sobre el
      # ARN sin `/*` y se acota con `s3:prefix`, la unica llave que limita un
      # listado. Doc de AWS (S3 User Guide, "Bucket policy examples using
      # condition keys"): "You can use the s3:prefix condition key to limit the
      # response of the ListObjectsV2 API operation to key names with a specific
      # prefix."
      #
      # `s3:ListBucketVersions` va al lado porque este bucket TIENE VERSIONADO, y
      # esa misma pagina dice: "If the bucket is versioning-enabled, to list the
      # objects in the bucket, you must grant the s3:ListBucketVersions
      # permission in the following policies, instead of the s3:ListBucket
      # permission. The s3:ListBucketVersions permission also supports the
      # s3:prefix condition key." Conceder solo uno es apostar a cual de las dos
      # lecturas aplica, y esa apuesta se pierde en mitad de un restore.
      #
      # LO QUE ESTE ACOTAMIENTO DEJA FUERA, medido y no supuesto:
      # `barman-cloud-check-wal-archive` empieza con un `HeadBucket`, que se
      # autoriza contra `s3:ListBucket` SIN parametro de prefijo (doc de la API:
      # "To use this operation, you must have permissions to perform the
      # s3:ListBucket action"). Una condicion `s3:prefix` no puede satisfacerse
      # cuando la llave no viene en la peticion, asi que ESE comando recibira
      # AccessDenied. Se acepta a proposito: no lo usa ningun camino automatico, y
      # las tres operaciones que si corren (`wal-archive`, `backup`, y el
      # `backup-list`/`wal-restore` del restore) listan SIEMPRE bajo el prefijo
      # del servidor — comprobado instrumentando boto3 y leyendo los parametros
      # reales de cada llamada.
      {
        Sid      = "ListBackups"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:ListBucketVersions"]
        Resource = var.db_backups_bucket.arn
        Condition = {
          StringLike = {
            "s3:prefix" = [
              "${var.dump_key_prefix}*",
              "${var.pitr.prefix}*",
            ]
          }
        }
      },
      # NO HAY `s3:DeleteObject` EN NINGUNA PARTE, y es una decision de diseno.
      # La cadena PITR la poda UN solo actor: el lifecycle de S3
      # (`modules/storage`). `barman-cloud-backup-delete` esta instalado en la
      # imagen y podria podar tambien; dos podadores a ciegas sobre los mismos
      # objetos son una carrera cuyo perdedor es el restore. Que el segundo no
      # exista no se sostiene en un comentario: se sostiene en que AWS lo
      # deniega.
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
          # [T-2.132] El reintento EN EL SITIO sostiene la invisibilidad del
          # mensaje mientras la base esta ocupada por un lock pasajero. Sin esta
          # accion la llamada da AccessDenied: el worker no se cae (es
          # best-effort), pero el mensaje se hace visible a mitad del reintento y
          # otro worker gasta justo la recepcion que se estaba ahorrando — o sea,
          # el permiso que falta convierte el arreglo en decorativo.
          "sqs:ChangeMessageVisibility",
        ]
        Resource = var.worker_queue_arns
      },
      # [T-2.60.a] El worker `notify` publica GhostGatewaysAlive (gabinetes
      # retirados que siguen reportando) en el namespace Takab/Ops.
      # PutMetricData no admite ARN de recurso — el alcance se acota por
      # `cloudwatch:namespace`, que es la unica llave de condicion que ofrece.
      #
      # [T-2.72] Por aqui pasa tambien `WalArchiveAgeSeconds`, el reloj del RPO.
      # El namespace sale del mismo local que el publicador: si esta condicion y
      # el script dijeran cosas distintas, la metrica se rechazaria con
      # AccessDenied y la alarma se quedaria ciega sin que nada pareciera roto.
      {
        Sid      = "PutOpsMetrics"
        Effect   = "Allow"
        Action   = "cloudwatch:PutMetricData"
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = local.ops_metrics_namespace
          }
        }
      },
      # [T-2.71] Ventanas de mantenimiento: silenciar alarmas de OPERACION.
      #
      # DOS statements, y la separacion es la frontera de seguridad, no estilo.
      # Doc de AWS (verificada contra el CLI 2.35.16 instalado, no supuesta):
      # "To create or update a mute rule, you must have the
      # cloudwatch:PutAlarmMuteRule permission on TWO types of resources: the
      # alarm mute rule resource itself, AND each alarm that the rule targets."
      #
      # Eso convierte a IAM en la SEGUNDA linea de defensa. Hasta descubrirlo, la
      # unica frontera entre "silencio mi gabinete" y "apago el detector de
      # fallos de la plataforma" era el codigo de `ops/muting.py`. Ahora, si un
      # bug del API pidiera callar `takab-dev-dlq-*`, `takab-dev-iot-rule-errors`
      # o `takab-dev-gateway-retirado-sigue-reportando`, AWS lo DENIEGA: esos
      # nombres no estan aqui y ningun comodin los alcanza.
      {
        Sid    = "ManageOwnMuteRules"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutAlarmMuteRule",
          "cloudwatch:GetAlarmMuteRule",
          "cloudwatch:DeleteAlarmMuteRule",
        ]
        # Solo las reglas que crea ESTE sistema (`takab-dev-mw-<window_id>`): no
        # puede pisar ni borrar una ventana abierta a mano por un humano.
        Resource = "arn:aws:cloudwatch:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:alarm-mute-rule:takab-${var.env}-mw-*"
      },
      {
        Sid    = "MuteOnlySilenceableAlarms"
        Effect = "Allow"
        Action = "cloudwatch:PutAlarmMuteRule"
        # ENUMERACION EXPLICITA de lo silenciable, espejo de `ALARM_CATALOG` en
        # api/src/takab_api/ops/muting.py. Las tres intocables NO estan y no hay
        # comodin que las roce:
        #   - takab-dev-dlq-*                            (instrumento del canary)
        #   - takab-dev-iot-rule-errors                  (instrumento del canary)
        #   - takab-dev-gateway-retirado-sigue-reportando (vigila al vigilante)
        # El comodin de `gateway-offline-*` es por gabinete (`for_each` sobre
        # paged_gateways); NO alcanza a `gateway-retirado-...` porque el prefijo
        # completo es `gateway-offline-`.
        Resource = [
          "arn:aws:cloudwatch:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:alarm:takab-${var.env}-gateway-offline-*",
          "arn:aws:cloudwatch:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:alarm:takab-${var.env}-sensor-mudo-*",
          "arn:aws:cloudwatch:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:alarm:takab-${var.env}-ec2-status-check",
          "arn:aws:cloudwatch:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:alarm:takab-${var.env}-ec2-cpu-sostenida",
        ]
      },
      {
        Sid    = "DescribeAlarmsForMuteAck"
        Effect = "Allow"
        # El ACUSE: `PutAlarmMuteRule` con 200 NO es "silenciado" — el nombre
        # puede no existir. Se contrasta contra DescribeAlarms, que NO admite
        # nivel de recurso (es una API de listado): `*` es obligado. Es LECTURA
        # de metadatos de alarma, no capacidad de callarlas.
        Action   = "cloudwatch:DescribeAlarms"
        Resource = "*"
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
      ],
      # Worker notify co-locado (T-1.62): envio de correo por SES. Una identidad
      # VERIFICADA no concede envio — son dos cosas distintas, y el hueco estuvo
      # tapado porque los avisos de CloudWatch los manda SNS (permiso propio) y
      # SI llegaban. Sin este grant: AccessDenied, el job muere y el inspector
      # jamas recibe la solicitud de dictamen (visto en produccion el 2026-07-14).
      # Lista vacia ⇒ sin statement (una Resource vacia seria IAM invalido).
      #
      # [T-2.78.b] La condicion mira `local.notify_ses_arns`, que incluye el ARN
      # del DOMINIO, y no `var.notify_ses_identity_arns`. La diferencia no es de
      # estilo: el dia que el remitente pase a ser SOLO el dominio, lo natural es
      # vaciar `ses_verified_emails` — y escrita sobre la lista de direcciones,
      # esa limpieza borraria el statement ENTERO llevandose tambien el permiso
      # sobre el dominio. El worker se quedaria mudo por haber hecho lo correcto.
      # Medido en `tests/pitr.tftest.hcl`.
      length(local.notify_ses_arns) > 0 ? [
        {
          Sid      = "WorkerSesSend"
          Effect   = "Allow"
          Action   = ["ses:SendEmail", "ses:SendRawEmail"]
          Resource = local.notify_ses_arns
        },
    ] : [])
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

    # [T-2.72] DOS saltos, no uno. `barman-cloud-*` corre DENTRO del contenedor
    # de Postgres —el `archive_command` lo ejecuta el propio postmaster— y firma
    # sus llamadas a S3 con el rol de esta instancia. El contenedor de la DB vive
    # en la red bridge de Docker (`docker run -p 5432:5432`), asi que la
    # respuesta de IMDSv2 tiene que dar un salto mas que desde el host.
    #
    # Doc de AWS (EC2 User Guide, "Configure the Instance Metadata Service
    # options"): "In a container environment, a hop limit of 1 can cause issues."
    # El valor efectivo por defecto es 1 (ejemplo 1 de esa misma pagina), y hasta
    # hoy nadie lo habia notado porque NADA dentro del contenedor de la DB
    # necesitaba credenciales: el dump nocturno lo sube el `aws` del HOST, y la
    # nube co-locada corre con `network_mode: host` (deploy/cloud/
    # docker-compose.yml).
    #
    # Se cambia en caliente (ModifyInstanceMetadataOptions): no recrea ni para la
    # instancia.
    http_put_response_hop_limit = 2
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
  #
  # vpc_security_group_ids se IGNORA porque el modulo serve adjunta el SG web
  # por ENI (aws_network_interface_sg_attachment, para poder desconectarlo sin
  # tocar la instancia). Sin esto, cada plan "corrige" la lista de la instancia
  # y ARRANCA el SG web de la ENI — paso en el apply de T-1.39 y dejo la
  # consola sin 80/443. Es el patron documentado del propio provider: con
  # attachments por ENI, la lista de SGs de la instancia no se gestiona aqui.
  lifecycle {
    ignore_changes = [ami, vpc_security_group_ids]
  }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/xvdf" # en instancias Nitro aparece como /dev/nvme1n1
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.db.id

  # destroy limpio aunque el filesystem este montado
  stop_instance_before_detaching = true
}

# --- [T-2.72] Archivado continuo de WAL (PITR) ----------------------------------
#
# Los dos mecanismos que ya existian —snapshot EBS diario y `pg_dump` nocturno—
# dan DOS puntos de recuperacion al dia y ninguno da PITR: entre punto y punto la
# perdida es total (`RUNBOOK-backup-restore-db.md` §1). Esto anade el tercero: el
# WAL viaja a S3 de forma continua y se puede volver a cualquier instante.
#
# POR QUE barman-cloud Y NO WAL-G, que es lo que pedia el nombre de la tarea y el
# §7 del runbook: la imagen que corre la DB en produccion
# (`timescale/timescaledb-ha:pg16`) TRAE barman-cloud instalado —
# `barman-cloud-wal-archive`, `-backup`, `-restore`, `-wal-restore`,
# `-backup-list`, version 3.19.1 — y NO trae wal-g (comprobado listando
# `/usr/local/bin` dentro del contenedor real). Meter wal-g exigiria o reconstruir
# la imagen de la DB o descargar un binario y montarlo dentro del contenedor: un
# eslabon de suministro nuevo en el camino de recuperacion, que es el ultimo sitio
# donde conviene tener uno. La herramienta cambia; el diseno (archivado continuo,
# RPO derivado de la alarma, un solo podador) no depende de cual sea.
#
# El `apply` es HUMANO-AWS y va en T-2.74, junto con el primer `backup base` y el
# ensayo de restore.

resource "aws_ssm_document" "pitr" {
  name            = "takab-${var.env}-pitr-archivado"
  document_type   = "Command"
  document_format = "JSON"

  # JSON y no YAML a proposito: el script lleva comillas simples (`archive_timeout
  # = '60s'`) y el estilo simple de YAML las duplicaria, cambiando el texto que de
  # verdad se ejecuta.
  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Configura el archivado continuo de WAL (PITR) de la DB de TAKAB: archive_mode/command/timeout, cron del backup base y publicacion de la edad del archivado."
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "configurar_archivado_wal"
      inputs = {
        timeoutSeconds = "900"
        runCommand     = split("\n", local.pitr_setup_script)
      }
    }]
  })
}

# La ASOCIACION es lo que convierte esto en infraestructura declarada en vez de
# un procedimiento del runbook. Un documento SSM sin asociacion es un script que
# alguien tiene que acordarse de correr; con ella, Terraform tiene un estado
# deseado sobre la maquina y AWS lo vuelve a imponer todos los dias.
#
# `rate(1 day)` no es paranoia: recrear el contenedor de la DB es una operacion
# normal del despliegue, y un contenedor recreado sin archivado es exactamente el
# fallo silencioso que esta tarea existe para cerrar. El script solo reinicia
# Postgres si `archive_mode` NO esta en `on`, asi que la pasada diaria de una
# instancia sana no cuesta nada.
#
# LATENCIA, declarada porque de otro modo se descubre en el peor momento: cambiar
# `wal_archive_timeout_s` (o cualquier otra cifra que entre en el script) crea una
# VERSION NUEVA del documento, pero no modifica ningun atributo de la asociacion.
# Terraform informa `apply complete` sin volver a lanzarla, y el cambio aterriza
# cuando toque la siguiente pasada — hasta 24 h despues. Para que surta efecto YA:
#
#   aws ssm start-associations-once --association-ids <id>
#
# Es un paso del runbook de T-2.74, no un defecto que se pueda arreglar aqui:
# forzar la re-ejecucion desde Terraform exigiria un disparador artificial en la
# asociacion, y entonces cada `apply` reconfiguraria la DB aunque nada hubiera
# cambiado.
resource "aws_ssm_association" "pitr" {
  name                = aws_ssm_document.pitr.name
  association_name    = "takab-${var.env}-pitr-archivado"
  document_version    = "$LATEST"
  schedule_expression = "rate(1 day)"

  targets {
    key    = "InstanceIds"
    values = [aws_instance.db.id]
  }
}

# --- [T-2.73.a] La huella del origen viaja junto al dump -----------------------
#
# El cron de las 08:00 subia el `.dump` y nada mas. Sin la huella, seis de las
# comprobaciones mas fuertes del verificador no se pueden ejercer y el veredicto
# es INDETERMINADO: `T-2.74` (`G-09`) saldria a medias.
#
# EL VEHICULO ES ESTE DOCUMENTO, NO `user_data.sh.tpl`, y la razon no es de
# estilo. `user_data` es un atributo de `aws_instance.db`: cambiarlo hace que el
# provider PARE Y ARRANQUE la instancia en el siguiente apply (el atributo solo se
# puede reescribir con la maquina detenida cuando `user_data_replace_on_change`
# esta en false, que es nuestro caso). La DB caeria en un apply que nadie
# esperaba que la tocara. Ademas `user_data` corre UNA vez, en el primer boot, y
# aborta si encuentra `/var/lib/takab/.provisioned`: escribir esto alli habria
# dado un `apply complete` que no cambia nada en la maquina que existe hoy.
#
# Se aplica la misma latencia declarada en la asociacion del PITR: un cambio en
# el script crea una version nueva del documento pero NO relanza la asociacion.
# Para que surta efecto ya: `aws ssm start-associations-once --association-ids <id>`.
resource "aws_ssm_document" "backup" {
  name            = "takab-${var.env}-respaldo-logico"
  document_type   = "Command"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Instala el respaldo logico nocturno de la DB de TAKAB y la huella del origen (restore_check --save-baseline), anclados al mismo snapshot y subidos al mismo prefijo S3."
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "configurar_respaldo_y_huella"
      inputs = {
        timeoutSeconds = "900"
        runCommand     = split("\n", local.backup_setup_script)
      }
    }]
  })
}

resource "aws_ssm_association" "backup" {
  name                = aws_ssm_document.backup.name
  association_name    = "takab-${var.env}-respaldo-logico"
  document_version    = "$LATEST"
  schedule_expression = "rate(1 day)"

  targets {
    key    = "InstanceIds"
    values = [aws_instance.db.id]
  }
}

# --- [T-2.81.a] La retencion de PII, PROGRAMADA ---------------------------------
#
# El job existia y era invocable, y no lo llamaba nadie: no habia modulo de cron,
# Lambda ni EventBridge en `infra/terraform/modules/`. Una retencion que nadie
# ejecuta es una politica escrita, no una cumplida.
#
# MISMO VEHICULO que el PITR y el respaldo logico —documento SSM + asociacion— y
# por las mismas dos razones, que aqui no se heredan sino que vuelven a valer:
# `user_data` corre una sola vez y ademas aborta si encuentra el marcador
# `/var/lib/takab/.provisioned` (o sea: Terraform verde que no toca la maquina
# que existe hoy), y modificar `user_data` hace que el provider pare y arranque
# la instancia en el siguiente apply. La asociacion impone el estado deseado cada
# dia y lo repara si alguien lo deshace.
#
# LA MISMA LATENCIA DECLARADA que sus dos vecinas: cambiar
# `pii_retention_windows_days` crea una VERSION NUEVA del documento pero no
# modifica ningun atributo de la asociacion, asi que Terraform informa `apply
# complete` y el cambio aterriza cuando toque la siguiente pasada — hasta 24 h
# despues. Para que surta efecto YA:
#
#   aws ssm start-associations-once --association-ids <id>
#
# Con esta ficha eso importa mas que con las otras dos: el dia que se decidan los
# plazos, el `apply` que los declara NO empieza a podar hasta la siguiente pasada.
resource "aws_ssm_document" "prune_pii" {
  name            = "takab-${var.env}-retencion-pii"
  document_type   = "Command"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Programa la corrida diaria de retencion de PII (takab_api.ops.prune_pii) y el publicador de la edad de la ultima corrida correcta."
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "configurar_retencion_pii"
      inputs = {
        timeoutSeconds = "900"
        runCommand     = split("\n", local.prune_pii_setup_script)
      }
    }]
  })
}

resource "aws_ssm_association" "prune_pii" {
  name                = aws_ssm_document.prune_pii.name
  association_name    = "takab-${var.env}-retencion-pii"
  document_version    = "$LATEST"
  schedule_expression = "rate(1 day)"

  targets {
    key    = "InstanceIds"
    values = [aws_instance.db.id]
  }
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
