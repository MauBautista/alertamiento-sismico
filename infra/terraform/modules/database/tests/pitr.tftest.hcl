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

# --- [T-2.72.b] El ANCLA de la cadena, y de donde sale su umbral ---------------
#
# `WalArchiveAgeSeconds` mide la CADENA de WAL, no su ancla: un
# `barman-cloud-backup` que falle cada semana no mueve esa metrica ni un segundo y
# la cadena esta rota igual. La alarma que lo ve vive en `modules/observability`,
# pero el UMBRAL se calcula aqui a proposito — es el unico sitio donde estan las
# mismas variables que gobiernan la retencion (`pitr.base_backup_interval_days` y
# `pitr.chain_margin`, las dos de `modules/storage`) y donde se programa el cron
# que produce esos backups. Un numero copiado en la alarma se desincroniza el dia
# que cambie la politica de retencion, y entonces la vigilancia describiria una
# cadena distinta de la que S3 poda.
run "el_umbral_del_backup_base_se_deriva_de_las_variables_de_retencion" {
  command = plan

  # Centinelas del bloque de archivo: 5 dias de intervalo x margen 3 = 15 dias.
  # Ningun numero de produccion coincide con eso.
  assert {
    condition     = output.base_backup_max_age_s == 5 * 3 * 86400
    error_message = "El umbral del backup base debe ser `pitr.base_backup_interval_days * pitr.chain_margin` en SEGUNDOS. Es la misma desigualdad que mantiene viva la cadena (`wal_retention_days >= intervalo * margen`): si la alarma vigilara otro numero, se estaria comprobando una cadena que el lifecycle de S3 no poda."
  }

  # Y que se DERIVE, no que hoy coincida: la forma, contra las propias variables.
  assert {
    condition     = output.base_backup_max_age_s == var.pitr.base_backup_interval_days * var.pitr.chain_margin * 86400
    error_message = "El umbral del backup base debe derivarse de las variables de `pitr`, no de un literal."
  }

  # [T-2.141 · corregido en T-2.154] EL AVISO: el intervalo MAS la gracia.
  #
  # ⚠️ Esta asercion pedia `== 5 * 86400` EXACTO, y con eso protegia el defecto.
  # Su razonamiento era correcto en teoria —"el primer instante en que se puede
  # afirmar que un backup no se completo"— y ciego a como se produce el dato: la
  # metrica sigue contando la edad del backup ANTERIOR hasta que alguien descubre
  # el nuevo. La edad cruza el umbral cuando el backup ARRANCA, no cuando falla.
  #
  # Consecuencia medida: la alarma temprana disparaba en TODOS los ciclos. Y quien
  # fuera a arreglar el umbral se habria encontrado este test en rojo y habria
  # podido concluir que el arreglo estaba mal. Un test puede fijar un defecto tan
  # bien como fija un acierto.
  #
  # Con los centinelas (5 dias + 3600 s = 435600) sigue sin coincidir con ningun
  # valor de produccion ni con el de su hermana (15 dias), que era el motivo
  # original de elegirlos.
  assert {
    condition     = output.base_backup_warn_age_s == 5 * 86400 + 3600
    error_message = "El umbral del AVISO debe ser `pitr.base_backup_interval_days` MAS `base_backup_grace_s`. Sin la gracia iguala la cadencia, y entonces la edad lo cruza en el instante en que arranca el backup nuevo: dispara en todos los ciclos y se ignora la semana que si falla."
  }

  assert {
    condition     = output.base_backup_warn_age_s == var.pitr.base_backup_interval_days * 86400 + var.pitr.base_backup_grace_s
    error_message = "El umbral del aviso debe derivarse de las variables de `pitr`, no de un literal."
  }

  # LAS DOS DERIVAN DE LAS MISMAS VARIABLES Y NINGUNA REPITE UN NUMERO.
  #
  # ⚠️ [T-2.154] Esto pedia `max == warn * chain_margin`, un COCIENTE EXACTO. Y esa
  # razon solo se sostenia porque el aviso ERA el intervalo pelado — o sea, se
  # habia elevado a invariante lo que era una coincidencia de la formula. Al darle
  # al aviso la gracia que necesitaba para no gritar en cada ciclo, la razon dejo
  # de ser entera y este test se puso rojo por el ARREGLO, no por un defecto.
  #
  # Lo que de verdad importa se conserva y se dice mejor: el aviso llega ANTES, y
  # la ultima linea sigue derivandose del margen. La distancia entre los dos es lo
  # que da ventana de reaccion; que ademas sea un multiplo exacto no le importa a
  # nadie.
  assert {
    condition = (
      output.base_backup_warn_age_s < output.base_backup_max_age_s
      && output.base_backup_max_age_s == var.pitr.base_backup_interval_days * var.pitr.chain_margin * 86400
    )
    error_message = "O el aviso no llega antes que la ultima linea —y entonces no hay aviso, hay eco: dos correos para el mismo hecho—, o `base_backup_max_age_s` dejo de derivarse de `intervalo x margen`."
  }

  # Y la gracia no puede comerse la ventana de reaccion. Con la desigualdad de
  # arriba bastaria para que fueran distintos, pero "distinto" admite un segundo
  # de diferencia: lo que hace util al aviso es que quede al menos un ciclo entero
  # por delante para relanzar el backup.
  assert {
    condition     = output.base_backup_max_age_s - output.base_backup_warn_age_s >= var.pitr.base_backup_interval_days * 86400
    error_message = "La gracia del aviso se comio la ventana de reaccion: entre el aviso y la ultima linea tiene que quedar al menos un intervalo completo, que es el tiempo de relanzar un backup base antes de que la cadena se rompa."
  }

  # Y el aviso tiene que caber DENTRO de la ventana de WAL, o avisaria de algo que
  # ya no se puede arreglar. Con `chain_margin >= 2` (validado en variables.tf) y
  # la desigualdad de la cadena, esto se cumple siempre — pero se comprueba, que es
  # como se descubrio que el otro umbral NO cabia (es el hallazgo de T-2.72.b).
  assert {
    condition     = output.base_backup_warn_age_s < var.pitr.wal_retention_days * 86400
    error_message = "El aviso llega cuando la ventana de WAL ya se cerro: entonces no es un aviso, es otra ultima linea. Es exactamente el defecto que T-2.141 vino a arreglar."
  }
}

# La otra mitad, sin la cual lo de arriba es vacuo: una igualdad comprobada con UN
# solo juego de entradas no distingue una funcion de una constante que hoy
# coincide. Es la leccion medida de `wal_archive_rpo.tftest.hcl` (donde el literal
# `1077` pasaba los cinco tests). Con un segundo juego, ninguna constante puede
# satisfacer los dos bloques a la vez.
run "el_umbral_del_backup_base_se_mueve_con_la_politica_de_retencion" {
  command = plan

  variables {
    pitr = {
      prefix                    = "PITRSENT/"
      server_name               = "SRVSENT"
      wal_retention_days        = 40
      base_backup_interval_days = 4
      chain_margin              = 2
    }
  }

  assert {
    condition     = output.base_backup_max_age_s == 4 * 2 * 86400
    error_message = "El umbral no siguio a las variables de retencion: es una constante disfrazada de derivacion, y el dia que se alargue el intervalo entre backups base la alarma seguira vigilando el intervalo viejo."
  }

  # [T-2.141] El segundo juego de centinelas del AVISO, por lo mismo: con uno
  # solo, `5 * 86400` no distinguiria una derivacion de una constante que hoy vale
  # lo mismo. Aqui son 4 dias, y el margen cambio de 3 a 2, asi que ademas se
  # comprueba que los dos umbrales se movieron POR SEPARADO.
  # [T-2.154] Segundo juego: intervalo 4 y margen 2, con la gracia por DEFECTO
  # (este bloque no la declara), asi que ademas se comprueba que el `optional()`
  # aplica su valor y no deja el umbral sin gracia.
  assert {
    condition = (
      output.base_backup_warn_age_s == 4 * 86400 + 3600
      && output.base_backup_max_age_s == 4 * 2 * 86400
      && output.base_backup_warn_age_s < output.base_backup_max_age_s
    )
    error_message = "El umbral del aviso no siguio al intervalo, o perdio la gracia por defecto, o dejo de llegar antes que su hermana. Con el margen cambiado de 3 a 2, una constante no puede satisfacer los dos bloques."
  }
}

# --- [T-2.72.b · T-2.72.c] Los DOS publicadores que faltaban -------------------
#
# La alarma no puede inventarse el dato: alguien tiene que publicarlo. Los dos
# viven en el mismo documento SSM que el reloj del RPO, y por la misma razon que
# aquel: `user_data` corre UNA vez en el primer boot y ademas cambiarlo PARA Y
# ARRANCA la instancia en el siguiente apply.
run "el_documento_ssm_publica_el_ancla_y_el_disco" {
  command = plan

  # El otro extremo del cable de `base_backup_missing`. Terraform no puede leer el
  # script desde `modules/observability`, asi que el par namespace+metrica se ancla
  # en los dos lados: si divergen, la alarma vigila una metrica que nadie escribe
  # y —al estar en `breaching`— grita para siempre.
  assert {
    condition = (
      strcontains(aws_ssm_document.pitr.content, "BaseBackupAgeSeconds")
      && strcontains(aws_ssm_document.pitr.content, "barman-cloud-backup-list")
    )
    error_message = "El documento SSM debe publicar Takab/Ops/BaseBackupAgeSeconds a partir de `barman-cloud-backup-list`. La fuente importa: `pg_stat_archiver` no sabe nada del backup base, y un backup base que falla no mueve ninguna metrica de las que ya existen."
  }

  # El otro extremo del cable de `db_disk_space`. `disk_used_percent` no existe en
  # las metricas nativas de EC2 —el hipervisor no ve dentro del filesystem—, asi
  # que o hay agente de CloudWatch o se publica desde la instancia. Y tiene que
  # mirar `/data`, que es donde vive el datadir (`/data/pgdata`) y donde crece
  # `pg_wal`: medir el volumen raiz seria vigilar el disco equivocado.
  assert {
    condition = (
      strcontains(aws_ssm_document.pitr.content, "DataDiskUsedPercent")
      && strcontains(aws_ssm_document.pitr.content, "df -P /data")
    )
    error_message = "El documento SSM debe publicar Takab/Ops/DataDiskUsedPercent midiendo `/data`, que es donde estan `/data/pgdata` y su `pg_wal`. Medir el volumen RAIZ seria vigilar un disco de 20 GiB que no se llena, mientras el de 40 GiB que sostiene la base se acaba."
  }

  # Los dos publican POR MINUTO aunque el listado de backups sea diario. La cadencia
  # es parte del contrato con `treat_missing_data`: `base_backup_missing` esta en
  # `breaching`, asi que una metrica publicada UNA vez al dia sobre un periodo de un
  # dia produciria ventanas vacias en cuanto el cron se desplazara un minuto — y
  # cada ventana vacia es un correo afirmando que no hay respaldo. El listado
  # (`barman-cloud-backup-list`, la parte cara) sigue siendo diario; lo que se
  # publica cada minuto es la EDAD, que es funcion del reloj y no del listado.
  assert {
    condition = (
      strcontains(aws_ssm_document.pitr.content, "* * * * * root /opt/takab/bin/takab-base-backup-age.sh")
      && strcontains(aws_ssm_document.pitr.content, "* * * * * root /opt/takab/bin/takab-disk-usage.sh")
    )
    error_message = "Las dos metricas nuevas deben publicarse cada minuto. Con la cadencia diaria del LISTADO, un desplazamiento del cron dejaria ventanas de CloudWatch sin ningun datapoint, y sobre `breaching` eso es un correo diciendo que no hay respaldo cuando si lo hay."
  }

  # Y una primera medida YA, la leccion de `ghost_gateways`: una alarma cuya
  # metrica no ha existido NUNCA nace en INSUFFICIENT_DATA y se queda aparcada ahi
  # —`insufficient_data_actions` solo dispara AL TRANSITAR—, sin correo y con cara
  # de "todavia no hay datos". Publicar una vez al configurar obliga a las dos
  # alarmas a pronunciarse.
  assert {
    condition = (
      strcontains(aws_ssm_document.pitr.content, "/opt/takab/bin/takab-disk-usage.sh || log")
      && strcontains(aws_ssm_document.pitr.content, "/opt/takab/bin/takab-base-backup-age.sh || log")
    )
    error_message = "El script debe publicar una primera medida de cada metrica nueva al configurar. Sin ella las alarmas nacen en INSUFFICIENT_DATA y —como `insufficient_data_actions` solo dispara EN TRANSICION— se quedan aparcadas ahi para siempre, sin correo y con aspecto de 'aun no hay datos'."
  }

  # El scan diario NO puede ser el podador disfrazado. `barman-cloud-backup-list`
  # solo lee; que siga siendo asi es lo que impide que este documento se convierta
  # en el segundo podador de la cadena (asercion 6 de este mismo archivo).
  assert {
    condition     = !strcontains(aws_ssm_document.pitr.content, "barman-cloud-backup-delete")
    error_message = "El scan del backup base debe LISTAR, no podar. La retencion de la cadena la decide UN solo actor —el lifecycle de S3 de modules/storage— y el rol de la instancia ni siquiera tiene `s3:Delete*`."
  }
}

# --- [T-2.78.b] El remitente de DOMINIO y el permiso de envio del worker -------
#
# Una identidad SES VERIFICADA no concede envio: son dos cosas distintas, y el
# hueco estuvo tapado en produccion porque los avisos de CloudWatch los manda SNS
# (permiso propio) y SI llegaban — el fallo del 2026-07-14.
#
# Hasta hoy `notify_ses_identity_arns` se construia en el entorno iterando
# `ses_verified_emails`, o sea POR DIRECCION. Mover el remitente a un dominio sin
# tocar esa lista deja al worker con AccessDenied en cada envio. El arreglo no es
# "acordarse de anadirlo": es que la MISMA variable del entorno (`var.ses_domain`)
# alimente la creacion de la identidad y este permiso.
run "el_remitente_de_dominio_entra_en_el_permiso_de_envio" {
  command = plan

  variables {
    notify_ses_identity_arns = ["arn:aws:ses:us-east-2:000000000000:identity/soc@example.test"]
    notify_ses_domain        = "DOMSENT.test"
  }

  assert {
    condition = length([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : s
      if try(s.Sid, "") == "WorkerSesSend"
      && try(contains(tolist(s.Resource), "arn:aws:ses:us-east-2:000000000000:identity/DOMSENT.test"), false)
      && try(contains(tolist(s.Resource), "arn:aws:ses:us-east-2:000000000000:identity/soc@example.test"), false)
    ]) == 1
    error_message = "El ARN de la identidad de DOMINIO tiene que entrar en `WorkerSesSend` junto a las direcciones. Sin el, el worker `notify` recibe AccessDenied al primer envio desde el dominio y el job del dictamen muere en silencio mientras los correos de CloudWatch siguen llegando."
  }
}

# EL BORDE QUE SE COME LA MITAD DEL ARREGLO, y que hay que medir aparte: el
# statement `WorkerSesSend` solo se emite si la lista de ARNs no esta vacia (una
# `Resource` vacia es IAM invalido). El dia que el remitente pase a ser SOLO el
# dominio, lo natural es vaciar `ses_verified_emails` — y con la condicion escrita
# sobre la lista, el statement DESAPARECERIA entero llevandose tambien el permiso
# sobre el dominio. El worker se quedaria sin enviar por haber hecho lo correcto.
run "un_remitente_solo_de_dominio_no_deja_al_worker_sin_permiso" {
  command = plan

  variables {
    notify_ses_identity_arns = []
    notify_ses_domain        = "DOMSENT.test"
  }

  assert {
    condition = length([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : s
      if try(s.Sid, "") == "WorkerSesSend"
      && try(contains(tolist(s.Resource), "arn:aws:ses:us-east-2:000000000000:identity/DOMSENT.test"), false)
    ]) == 1
    error_message = "Con `ses_verified_emails` vacia y el dominio puesto, el statement `WorkerSesSend` sigue siendo obligatorio. Si la condicion mira solo a la lista de direcciones, vaciarla —que es lo que se hace al migrar al dominio— borra el statement entero y el worker se queda sin permiso justo por haber hecho lo correcto."
  }
}

# Y al reves: sin remitente de ninguna clase, NO puede haber statement. Una
# `Resource` vacia no es "sin permiso": es un documento IAM invalido que revienta
# el apply.
run "sin_ninguna_identidad_no_se_emite_el_statement_de_envio" {
  command = plan

  variables {
    notify_ses_identity_arns = []
    notify_ses_domain        = ""
  }

  assert {
    condition = length([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : s
      if try(s.Sid, "") == "WorkerSesSend"
    ]) == 0
    error_message = "Sin identidades ni dominio no debe emitirse `WorkerSesSend`: un statement con `Resource` vacia es IAM invalido y revienta el apply."
  }
}

# [T-2.155] EL CONFIGURATION SET TAMBIEN ES UN RECURSO, y sin el no se envia nada.
#
# El test de arriba —el del ARN de la identidad— existia y pasaba, y aun asi el
# envio real murio:
#
#   AccessDeniedException ... 'ses:SendEmail'
#   on resource '.../configuration-set/takab-dev-correo'
#
# La identidad de dominio lleva el configuration set POR DEFECTO, asi que SES lo
# aplica en CADA envio sin que el emisor lo nombre — y entonces exige permiso
# sobre los DOS recursos. Conceder solo la identidad deja un permiso que parece
# completo y falla en el primer correo.
#
# Por que el test anterior no bastaba, que es la leccion: comprobaba que estuviera
# lo que alguien penso en su momento, no que estuviera TODO lo que SES exige. Un
# test que asegura la presencia de X no dice nada sobre la ausencia de Y.
run "el_configuration_set_entra_en_el_permiso_de_envio" {
  command = plan

  variables {
    notify_ses_identity_arns     = ["arn:aws:ses:us-east-2:000000000000:identity/soc@example.test"]
    notify_ses_domain            = "DOMSENT.test"
    notify_ses_configuration_set = "SETDEPRUEBA"
  }

  assert {
    condition = length([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : s
      if try(s.Sid, "") == "WorkerSesSend"
      && try(contains(tolist(s.Resource), "arn:aws:ses:us-east-2:000000000000:configuration-set/SETDEPRUEBA"), false)
    ]) == 1
    error_message = "Falta el ARN del configuration set en `WorkerSesSend`. La identidad de dominio lo lleva por defecto, asi que SES lo aplica en cada envio y exige permiso sobre EL: con solo la identidad concedida, el primer correo muere con AccessDenied mientras los de CloudWatch siguen llegando (SNS, permiso propio). Medido el 2026-08-21 desde el rol de la instancia."
  }
}

# La otra mitad de la guarda: sin configuration set NO se inventa un ARN. Un
# `configuration-set/` vacio en la politica no da error de terraform y concede
# permiso sobre un recurso que no existe — ruido que se lee como cobertura.
run "sin_configuration_set_no_se_cuela_un_arn_vacio" {
  command = plan

  variables {
    notify_ses_identity_arns     = ["arn:aws:ses:us-east-2:000000000000:identity/soc@example.test"]
    notify_ses_domain            = "DOMSENT.test"
    notify_ses_configuration_set = ""
  }

  assert {
    condition = length([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : s
      if try(s.Sid, "") == "WorkerSesSend"
      && length([for r in tolist(s.Resource) : r if strcontains(r, "configuration-set/")]) > 0
    ]) == 0
    error_message = "Sin configuration set declarado no puede aparecer ningun ARN de `configuration-set/` en la politica: seria un permiso sobre un recurso inexistente, y esos se leen como cobertura."
  }
}

# [T-2.154] El umbral temprano NO puede ser el intervalo exacto.
#
# Serlo garantizaba un falso positivo por ciclo: la edad cruza el umbral en el
# instante en que ARRANCA el backup nuevo, y no baja hasta que la metrica lo
# refleja. Medido sobre los objetos de S3 el 2026-08-22: el backup tarda ~6 min y
# crecio 19% en una semana; con el scan una hora despues, la ventana era de 60.
#
# Una alarma que grita cada 7 dias sin motivo se ignora la semana que si falla, y
# esta vigila el ANCLA de la cadena PITR.
run "el_umbral_temprano_no_es_el_intervalo_exacto" {
  command = plan

  assert {
    condition     = output.base_backup_warn_age_s > var.pitr.base_backup_interval_days * 86400
    error_message = "El umbral de la alarma temprana no puede igualar la cadencia: la edad la cruza cuando arranca el backup nuevo y no baja hasta que la metrica lo refleja, asi que dispara en TODOS los ciclos. Necesita cubrir la duracion del backup."
  }

  # Y la otra mitad: la gracia no puede crecer hasta comerse a su hermana.
  assert {
    condition     = output.base_backup_warn_age_s < output.base_backup_max_age_s
    error_message = "La gracia se comio la distancia con `base_backup_max_age_s`. Si el aviso temprano se parece a la ultima linea quedan DOS alarmas para el caso tardio y NINGUNA para el temprano — que es justo lo que T-2.72.b separo."
  }
}

# La causa, no solo el sintoma: el backup refresca la metrica al terminar.
#
# Subir el umbral sin esto seria tapar una ventana de 60 minutos con margen. El
# scan de las 05:00 se queda —cubre backups hechos por otra via y repara el
# fichero—, pero deja de ser el unico que descubre el backup del dia.
run "el_backup_base_refresca_su_metrica_al_terminar" {
  command = plan

  assert {
    condition = (
      strcontains(aws_ssm_document.pitr.content, "/opt/takab/bin/takab-base-backup-scan.sh || true") &&
      strcontains(aws_ssm_document.pitr.content, "/opt/takab/bin/takab-base-backup-age.sh || true")
    )
    error_message = "`takab-base-backup.sh` debe refrescar la edad al terminar. Sin eso el unico que descubre el backup nuevo es el scan de las 05:00, y la metrica cuenta la edad del ANTERIOR durante una hora — una ventana de incumplimiento garantizada en cada ciclo."
  }
}
