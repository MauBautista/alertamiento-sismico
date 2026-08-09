# [T-2.72] PITR: la CADENA de recuperacion, y quien tiene permiso para romperla.
#
# Un backup base sin los WAL que le siguen no llega a ningun punto en el tiempo;
# unos WAL sin su backup base no arrancan. Eso NO se nota hasta que se intenta
# restaurar — el modo de fallo exacto que la Fase 2.6 existe para eliminar
# (`RUNBOOK-backup-restore-db.md:3`: "RESTORE JAMAS PROBADO").
#
# Este archivo blinda las tres formas conocidas de romper la cadena SIN que nada
# se ponga rojo:
#
#   1. Dos podadores sobre el mismo prefijo. El lifecycle de S3 poda por edad; si
#      ademas se configurara `barman-cloud-backup-delete`, los dos correrian a
#      ciegas uno del otro. Aqui la exclusion no es una convencion escrita en un
#      comentario: la instancia NO TIENE PERMISO de borrado sobre el prefijo, asi
#      que el segundo podador no es que no este configurado — es que no puede
#      existir. Se comprueba sobre el JSON RENDERIZADO de la politica.
#   2. Una retencion de WAL mas corta que el intervalo entre backups base. Se
#      valida por construccion (`wal_retention_days >= intervalo * margen`) y se
#      mide aqui con `expect_failures`, no comparando dos literales.
#   3. Un `archive_timeout` mayor o igual que la edad tolerada: la alarma
#      dispararia en operacion normal, y una alarma que suena siempre es una
#      alarma que alguien acaba silenciando. Tambien por validacion.
#
# Los valores de este archivo son SENTINELAS a proposito (`PITRSENT/`, `SRVSENT`,
# 11 s, 222 s...). Con los valores de produccion, una constante cableada en el
# modulo coincidiria con la variable y el test pasaria sin comprobar nada.
#
# Corre con: terraform -chdir=infra/terraform/modules/database test

provider "aws" {
  region                      = "us-east-2"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

variables {
  subnet_id   = "subnet-0000000000test000"
  sg_db_id    = "sg-0000000000test000"
  kms_key_arn = "arn:aws:kms:us-east-2:000000000000:key/00000000-0000-0000-0000-000000000000"
  db_backups_bucket = {
    name = "takab-test-db-backups"
    arn  = "arn:aws:s3:::takab-test-db-backups"
  }
  worker_queue_arns = ["arn:aws:sqs:us-east-2:000000000000:takab-test-events"]
  env               = "dev"

  wal_archive_timeout_s = 11
  wal_archive_max_age_s = 222
  pitr = {
    prefix                    = "PITRSENT/"
    server_name               = "SRVSENT"
    wal_retention_days        = 40
    base_backup_interval_days = 5
    chain_margin              = 3
  }
}

# Overrides A NIVEL DE ARCHIVO: la AMI, la subnet, la identidad y los ARN de los
# secretos no se conocen en `plan` sin credenciales, y sin fijarlos la politica
# entera queda "(known after apply)" y TODAS las aserciones sobre ella son
# inevaluables — verde vacio, el modo de fallo que esta fase persigue (ver
# mute_rules_iam).
#
# Van aqui y no dentro de un `run` porque los bloques de `expect_failures` de
# abajo TAMBIEN planifican: una validacion de variable que se espera no aborta el
# plan, lo degrada, y el plan sigue adelante hasta chocar con la API de AWS. Sin
# estos overrides esos tres bloques fallarian por credenciales y no por lo que
# miden — un rojo que no prueba nada.
override_data {
  override_during = plan
  target          = data.aws_ami.al2023_arm64
  values          = { id = "ami-00000000000test00" }
}
override_data {
  override_during = plan
  target          = data.aws_subnet.db
  values          = { availability_zone = "us-east-2a" }
}
override_data {
  override_during = plan
  target          = data.aws_caller_identity.current
  values          = { account_id = "000000000000" }
}
override_data {
  override_during = plan
  target          = data.aws_region.current
  values          = { region = "us-east-2" }
}
override_resource {
  override_during = plan
  target          = aws_secretsmanager_secret.db["superuser"]
  values          = { arn = "arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/db/superuser" }
}
override_resource {
  override_during = plan
  target          = aws_secretsmanager_secret.db["migrator"]
  values          = { arn = "arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/db/migrator" }
}
override_resource {
  override_during = plan
  target          = aws_secretsmanager_secret.db["app"]
  values          = { arn = "arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/db/app" }
}
override_resource {
  override_during = plan
  target          = aws_secretsmanager_secret.db["ingest"]
  values          = { arn = "arn:aws:secretsmanager:us-east-2:000000000000:secret:takab/dev/db/ingest" }
}

# NOTA DE METODO, aprendida por las malas en esta misma tarea. TODA asercion
# sobre una politica IAM va contra el JSON DECODIFICADO y contra el STATEMENT
# concreto, nunca con `strcontains`. Una politica es un documento con muchos
# statements: cualquier subcadena que se busque suelta —un ARN, una accion— casi
# siempre existe en OTRO statement, asi que el `strcontains` responde "si" a una
# pregunta que nadie hizo. Dos aserciones de este archivo murieron asi (el permiso
# de LECTURA del dump y el alcance de `ListBucket`): las dos pasaron en verde con
# el permiso que describian roto. Las subcadenas solo se usan aqui para lo que de
# verdad es un blob de texto sin estructura: el contenido del documento SSM.
run "la_cadena_de_pitr_no_la_puede_romper_nadie_por_accidente" {
  command = plan

  variables {
    # El centinela del prefijo del dump vive AQUI y no en el bloque de arriba: la
    # guardia del cron (mas abajo) tiene que comparar el DEFAULT real contra el
    # literal real de `user_data.sh.tpl`, y con el centinela puesto a nivel de
    # archivo esa comparacion seria imposible sin volver a teclear "takab-".
    dump_key_prefix = "DUMPSENT-"
  }

  # --- 1. UN SOLO PODADOR, y la exclusion es de PERMISO ----------------------
  #
  # El lifecycle de S3 (modules/storage) es el unico que poda. Que la instancia no
  # pueda borrar no es cosmetica: el subcomando de poda de barman esta instalado
  # en la imagen `timescale/timescaledb-ha:pg16` (verificado en la unidad real),
  # asi que sin este limite bastaria una linea de cron para poner dos podadores a
  # correr a ciegas uno del otro sobre la misma cadena.
  #
  # Se comprueba por CLASE, no por lista de nombres: cualquier statement que toque
  # el bucket de respaldos con una accion de borrado O CON UN COMODIN. La version
  # anterior enumeraba `s3:DeleteObject`, `s3:DeleteObjectVersion` y `s3:Delete*`,
  # y se la saltaba un `s3:*` — que concede borrado sin escribir la palabra.
  assert {
    condition = length([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : s
      if length([
        for r in try(tolist(s.Resource), [tostring(s.Resource)]) : r
        if startswith(r, "arn:aws:s3:::takab-test-db-backups")
      ]) > 0
      && length([
        for a in try(tolist(s.Action), [tostring(s.Action)]) : a
        if a == "*" || a == "s3:*" || startswith(a, "s3:Delete")
      ]) > 0
    ]) == 0
    error_message = "Algun statement concede borrado (o un comodin que lo incluye) sobre el bucket de respaldos. La retencion de la cadena PITR la decide UN solo podador —el lifecycle de modules/storage—; con permiso de borrado, una linea de cron bastaria para poner un segundo podador a correr a ciegas sobre los mismos objetos."
  }

  # --- 2. Escribir: PutObject acotado a los DOS prefijos, y nada mas ---------
  #
  # `PutBackups` es el permiso del que cuelga el dump nocturno. Antes de T-2.72 era
  # `${bucket}/*` y no habia nada que romper; ahora esta acotado, asi que el
  # literal del prefijo pasa a ser LOAD-BEARING para la escritura, no solo para la
  # retencion. La guardia del cron, mas abajo, cierra el otro extremo.
  assert {
    condition = length([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : s
      if try(s.Sid, "") == "PutBackups"
      && try(s.Action, "") == "s3:PutObject"
      && try(contains(tolist(s.Resource), "arn:aws:s3:::takab-test-db-backups/DUMPSENT-*"), false)
      && try(contains(tolist(s.Resource), "arn:aws:s3:::takab-test-db-backups/PITRSENT/*"), false)
    ]) == 1
    error_message = "`PutBackups` debe conceder s3:PutObject sobre EL PREFIJO DEL DUMP y sobre el de PITR. Sin el primero, el `aws s3 cp` del cron nocturno muere con AccessDenied y —como esa linea de cron no redirige salida— el error se va al correo de root de un EC2, o sea a ningun sitio."
  }

  # --- 2b. El aborto del multipart del backup base ---------------------------
  #
  # El backup base sube en multipart (barman parte el tar y llama a
  # create/upload/complete_multipart_upload; verificado leyendo
  # barman/cloud_providers/aws_s3.py en la imagen). Sin `AbortMultipartUpload`, un
  # backup base que falle a la mitad deja partes invisibles y facturadas para
  # siempre, y barman no puede limpiarlas.
  assert {
    condition = length([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : s
      if try(s.Sid, "") == "PitrAbortMultipart"
      && try(s.Action, "") == "s3:AbortMultipartUpload"
      && try(s.Resource, "") == "arn:aws:s3:::takab-test-db-backups/PITRSENT/*"
    ]) == 1
    error_message = "Falta `PitrAbortMultipart`: s3:AbortMultipartUpload acotado a <bucket>/<pitr.prefix>*."
  }

  # --- 3. LEER, que es lo que hoy NO se puede hacer ---------------------------
  #
  # Antes de T-2.72 el rol solo tenia `s3:PutObject` sobre el bucket de respaldos:
  # la instancia podia ESCRIBIR sus backups y no podia LEERLOS. Un respaldo que no
  # se puede leer desde donde hay que restaurarlo no es un respaldo. Vale para las
  # dos cadenas: la del PITR y la del dump logico.
  #
  # Esta asercion se comprueba sobre el JSON DECODIFICADO y contra el statement
  # concreto, no con `strcontains`. La primera version usaba subcadenas sueltas
  # ("existe el ARN del dump" && "existe s3:GetObject") y resulto VACUA: se borro
  # entero el permiso de lectura sobre el dump y siguio en verde, porque ese ARN
  # tambien aparece en `PutBackups` y `s3:GetObject` tambien aparece en
  # `WorkerTransferRead`. Dos hechos ciertos en sitios distintos no hacen el hecho
  # que se queria comprobar.
  assert {
    condition = length([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : s
      if try(s.Sid, "") == "GetBackups"
      # `try(...)`: si alguien deja `Resource` como una sola cadena, `tolist`
      # reventaria y el test moriria con un error de tipos en vez de decir que
      # falta el permiso. Un fallo ilegible es un fallo que se arregla mal.
      && try(contains(tolist(s.Resource), "arn:aws:s3:::takab-test-db-backups/DUMPSENT-*"), false)
      && try(contains(tolist(s.Resource), "arn:aws:s3:::takab-test-db-backups/PITRSENT/*"), false)
      && try(s.Action, "") == "s3:GetObject"
    ]) == 1
    error_message = "El rol de la instancia debe poder LEER sus propios respaldos: un statement `GetBackups` con s3:GetObject sobre el prefijo del dump Y sobre el de PITR. Sin eso el restore no se puede ejecutar donde vive la DB."
  }

  # --- 4. `s3:ListBucket` es permiso de BUCKET, no de objeto ------------------
  #
  # Se concede sobre el ARN del bucket (sin `/*`) y se acota con la condicion
  # `s3:prefix`, que es la unica llave que limita un listado. Doc de AWS
  # (userguide, "Bucket policy examples using condition keys", ejemplo 2 de
  # operaciones de bucket): *"You can use the `s3:prefix` condition key to limit
  # the response of the ListObjectsV2 API operation to key names with a specific
  # prefix."*
  #
  # Y `s3:ListBucketVersions` va al lado porque el bucket TIENE VERSIONADO. Misma
  # pagina: *"If the bucket is versioning-enabled, to list the objects in the
  # bucket, you must grant the `s3:ListBucketVersions` permission in the following
  # policies, instead of the `s3:ListBucket` permission. The
  # `s3:ListBucketVersions` permission also supports the `s3:prefix` condition
  # key."* Conceder solo uno de los dos es apostar a cual de las dos lecturas
  # aplica, y esa apuesta se pierde durante un restore.
  #
  # LO QUE COMPRUEBA ESTA ASERCION Y LA ANTERIOR NO: que el RECURSO sea el ARN del
  # bucket PELADO. La version anterior eran cinco `strcontains` y era VACUA — se
  # cambio el recurso a `${arn}/*` y los cuatro tests siguieron en verde, porque
  # las cinco subcadenas seguian existiendo. Y `ListBucket` sobre `bucket/*` no
  # autoriza NINGUN listado: `barman-cloud-backup-list` y `barman-cloud-wal-restore`
  # darian AccessDenied, y nadie se enteraria hasta ejecutar un restore. Ocho
  # lineas de comentario explicando "va sin /*" no comprueban nada; esto si.
  assert {
    condition = length([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : s
      if try(s.Sid, "") == "ListBackups"
      && try(s.Resource, "") == "arn:aws:s3:::takab-test-db-backups"
      && try(contains(tolist(s.Action), "s3:ListBucket"), false)
      && try(contains(tolist(s.Action), "s3:ListBucketVersions"), false)
      && try(contains(tolist(s.Condition.StringLike["s3:prefix"]), "PITRSENT/*"), false)
      && try(contains(tolist(s.Condition.StringLike["s3:prefix"]), "DUMPSENT-*"), false)
    ]) == 1
    error_message = "El listado debe concederse sobre el ARN del BUCKET y acotado por la condicion s3:prefix, y con ListBucketVersions al lado porque el bucket esta versionado."
  }

  # --- 5. El archivado se CONFIGURA desde aqui, no a mano en la instancia -----
  #
  # `archive_mode`/`archive_command`/`archive_timeout` viven en el documento SSM
  # que este modulo renderiza. Los sentinelas prueban que salen de las variables:
  # con un valor cableado, esto se cae.
  assert {
    condition = (
      strcontains(aws_ssm_document.pitr.content, "archive_timeout = '11s'")
      && strcontains(aws_ssm_document.pitr.content, "s3://takab-test-db-backups/PITRSENT")
      && strcontains(aws_ssm_document.pitr.content, "SRVSENT")
    )
    error_message = "El documento SSM debe derivar destino, nombre de servidor y archive_timeout de las variables del modulo: cableados, el Terraform deja de ser la fuente del archivado."
  }

  # --- 6. Y ese documento no puede traer el segundo podador -------------------
  assert {
    condition = (
      !strcontains(aws_ssm_document.pitr.content, "barman-cloud-backup-delete")
      && !strcontains(aws_ssm_document.pitr.content, "delete retain")
    )
    error_message = "El documento SSM no debe podar: la retencion de la cadena la decide el lifecycle de S3 (modules/storage) y dos podadores sobre el mismo prefijo son una carrera."
  }

  # --- 7. El otro extremo del cable de la alarma ------------------------------
  #
  # La alarma (`modules/observability`) vigila Takab/Ops/WalArchiveAgeSeconds.
  # Terraform no puede leer el script desde alli, asi que se ancla aqui: si el
  # publicador cambia de nombre o de namespace, la alarma se queda mirando una
  # metrica que nadie escribe y —al estar en `breaching`— grita para siempre.
  assert {
    condition = (
      strcontains(aws_ssm_document.pitr.content, "WalArchiveAgeSeconds")
      && strcontains(aws_ssm_document.pitr.content, "Takab/Ops")
    )
    error_message = "El publicador de la metrica debe escribir Takab/Ops/WalArchiveAgeSeconds, el mismo par que vigila la alarma de modules/observability."
  }

  # --- 8. La cadencia del backup base SALE del intervalo declarado ------------
  #
  # El intervalo no es una preferencia del cron: es un termino de la desigualdad
  # que mantiene viva la cadena. Si el cron y la desigualdad pudieran divergir, la
  # garantia de retencion se calcularia sobre un numero que no ocurre.
  assert {
    condition     = strcontains(aws_ssm_document.pitr.content, "*/5 * *")
    error_message = "La cadencia del backup base debe derivarse de pitr.base_backup_interval_days: un cron con otro periodo invalida la desigualdad de retencion que garantiza la cadena."
  }

  # --- 9. IMDSv2 con un solo salto no llega a un contenedor -------------------
  #
  # `barman-cloud-*` corre DENTRO del contenedor de Postgres (el `archive_command`
  # lo ejecuta el propio postmaster) y firma con el rol de la instancia. Doc de
  # AWS (EC2 User Guide, "Configure the Instance Metadata Service options"):
  # *"In a container environment, a hop limit of `1` can cause issues."* El default
  # de la cuenta es 1 (ejemplo 1 de esa misma pagina). Hasta hoy nada dentro del
  # contenedor de la DB necesitaba credenciales —el dump lo sube el `aws` del
  # HOST— y por eso el hueco no se habia visto.
  assert {
    condition     = aws_instance.db.metadata_options[0].http_put_response_hop_limit == 2
    error_message = "El limite de saltos de IMDSv2 debe ser 2: con 1, el contenedor de Postgres no obtiene credenciales y el archive_command falla en cada segmento."
  }
}

# --- El literal del dump: UNA cadena, TRES consumidores ------------------------
#
# `takab-` gobierna ahora tres cosas: la regla de expiracion de 60 dias
# (modules/storage), el `s3:PutObject` del rol (statement `PutBackups`) y la clave
# que escribe el cron nocturno (`user_data.sh.tpl`). Los dos primeros salen de la
# misma variable; el tercero es un literal dentro de una plantilla de shell que
# Terraform no puede parametrizar sin forzar un stop/start de la instancia.
#
# Mientras el permiso era `${bucket}/*`, esa divergencia solo costaba retencion.
# Ahora rompe la ESCRITURA: si el prefijo y la clave dejan de encajar, el
# `aws s3 cp` del cron muere con AccessDenied, esa linea de cron NO redirige
# salida (se va al correo de root de un EC2, o sea a ningun sitio) y no hay
# ninguna alarma sobre el exito del dump. El respaldo nocturno se apagaria en
# silencio.
#
# Este bloque convierte ese comentario en guardia. Corre con el DEFAULT de
# `dump_key_prefix` a proposito —el centinela vive dentro del run de arriba—
# porque lo que hay que comparar es el valor real contra el literal real.
run "el_cron_del_dump_escribe_bajo_el_prefijo_que_gobierna_su_retencion" {
  command = plan

  # `[^$]*` captura la parte CONSTANTE de la clave, la que hay antes de cualquier
  # expansion de shell. Si alguien reordena la clave a `$(date)-takab.dump`, lo
  # capturado es la cadena vacia y esto se pone rojo — que es la respuesta
  # correcta, porque entonces ningun prefijo fijo la cubre.
  assert {
    condition     = regex("db_backups_bucket\\}/([^$]*)", file("${path.module}/user_data.sh.tpl"))[0] == var.dump_key_prefix
    error_message = "La clave S3 del dump nocturno (user_data.sh.tpl) y `dump_key_prefix` han divergido. Consecuencias, las dos silenciosas: la regla de expiracion de 60 dias deja de alcanzar los dumps (se acumulan para siempre) y el `s3:PutObject` del rol deja de cubrirlos, asi que el cron muere con AccessDenied hacia el correo de root."
  }
}

# --- 10, 11, 12. Las validaciones que sostienen la cadena, MEDIDAS ------------
#
# Un `validation` que nunca se ha visto fallar no es una guardia: es un adorno.
# Cada uno de estos tres bloques rompe la configuracion a proposito y exige el
# fallo. Si alguien borra la validacion, el bloque se pone rojo por lo contrario
# (no fallo lo que tenia que fallar).

run "una_retencion_de_wal_mas_corta_que_la_cadena_no_se_puede_aplicar" {
  command = plan

  variables {
    pitr = {
      prefix                    = "PITRSENT/"
      server_name               = "SRVSENT"
      wal_retention_days        = 13 # < 7 * 2
      base_backup_interval_days = 7
      chain_margin              = 2
    }
  }

  expect_failures = [var.pitr]
}

run "un_margen_de_cadena_menor_que_dos_no_se_puede_aplicar" {
  command = plan

  variables {
    pitr = {
      prefix                    = "PITRSENT/"
      server_name               = "SRVSENT"
      wal_retention_days        = 40
      base_backup_interval_days = 7
      chain_margin              = 1 # el ultimo backup base podria expirar solo
    }
  }

  expect_failures = [var.pitr]
}

run "un_archive_timeout_por_encima_de_la_edad_tolerada_no_se_puede_aplicar" {
  command = plan

  variables {
    wal_archive_timeout_s = 900
    wal_archive_max_age_s = 600
  }

  expect_failures = [var.wal_archive_timeout_s]
}
