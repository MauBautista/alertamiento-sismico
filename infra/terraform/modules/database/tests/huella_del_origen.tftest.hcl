# [T-2.73.a] La huella del origen viaja junto al dump.
#
# Tres cosas se pueden romper aqui sin que nada se ponga rojo, y las tres cuestan
# la acreditacion de `G-09`:
#
#   1. Que el mecanismo se mude a `user_data.sh.tpl`. Es la via "obvia" —la linea
#      del cron vive alli— y es la que PARA Y ARRANCA la instancia en el
#      siguiente apply, con la DB dentro. El criterio 2 de la ficha existe por
#      esto, y aqui deja de ser una advertencia en prosa.
#   2. Que la huella caiga fuera del prefijo del dump. Entonces ni la regla de
#      expiracion de `modules/storage` la alcanza (se acumula para siempre) ni el
#      `s3:PutObject` del rol la cubre (el cron muere con AccessDenied contra el
#      correo de root de un EC2, o sea contra ningun sitio).
#   3. Que se anada una SEGUNDA entrada de cron en vez de sustituir la que ya
#      existe: dos volcados a las 08:00 peleando por el mismo nombre de objeto.
#
# Los valores son SENTINELAS a proposito (`DUMPSENT-`, `HUELLASENT`): con los de
# produccion, una constante cableada en el modulo coincidiria con la variable y
# el test pasaria sin comprobar nada.
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
}

# Sin credenciales no hay AMI, ni subred, ni cuenta, ni ARN de secreto — y un
# atributo "(known after apply)" hace INEVALUABLE toda asercion que dependa de
# el: verde vacio, que es el modo de fallo que esta fase persigue. Misma razon y
# mismos valores que en `pitr.tftest.hcl`; van a nivel de archivo porque el
# bloque de `expect_failures` del final tambien planifica.
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

# --- 1. El vehiculo -----------------------------------------------------------
run "la_huella_viaja_en_un_documento_ssm_y_no_en_el_user_data" {
  command = plan

  variables {
    dump_key_prefix = "DUMPSENT-"
  }

  # El documento existe y es lo que dice ser.
  assert {
    condition     = aws_ssm_document.backup.document_type == "Command"
    error_message = "El respaldo tiene que viajar en un documento SSM de tipo Command."
  }

  # Un documento sin asociacion es un script que alguien tiene que acordarse de
  # correr. Con ella, AWS reimpone el estado deseado todos los dias — que es lo
  # que repara la maquina si alguien reescribe el cron a mano.
  assert {
    condition = (
      aws_ssm_association.backup.name == aws_ssm_document.backup.name &&
      aws_ssm_association.backup.schedule_expression == "rate(1 day)"
    )
    error_message = "Sin asociacion diaria, el documento no es infraestructura declarada: es un procedimiento del runbook."
  }

  # EL CRITERIO 2, HECHO GUARDIA. `user_data` es un atributo de la instancia:
  # tocarlo la para y la arranca en el siguiente apply, con la DB dentro.
  assert {
    condition = !anytrue([
      for aguja in ["save-baseline", "fingerprint", "coordinate-with-dump", "pg_export_snapshot"] :
      strcontains(file("${path.module}/user_data.sh.tpl"), aguja)
    ])
    error_message = "El mecanismo de la huella ha aparecido en user_data.sh.tpl. Cambiar ese atributo obliga al provider a PARAR Y ARRANCAR la instancia en el siguiente apply, y la DB caeria. El vehiculo es el documento SSM."
  }
}

# --- 2. El mismo cron, y el mismo prefijo -------------------------------------
#
# Se corre con el DEFAULT de `dump_key_prefix` a proposito: lo que hay que
# comparar es el valor real contra el literal real, igual que hace la guardia
# gemela de `pitr.tftest.hcl` sobre el user_data.
run "la_huella_sustituye_la_linea_del_cron_en_vez_de_anadir_una_segunda" {
  command = plan

  # El fichero de cron y la hora se DERIVAN de `user_data.sh.tpl`, que es quien
  # los creo. Si alguien mueve el dump a otra hora o a otro fichero alli, esto se
  # pone rojo — que es la respuesta correcta: habria DOS volcados nocturnos
  # compitiendo por el mismo nombre de objeto en S3.
  assert {
    condition = strcontains(
      file("${path.module}/backup_setup.sh.tpl"),
      regex("cat >(/etc/cron\\.d/[a-z-]+)", file("${path.module}/user_data.sh.tpl"))[0]
    )
    error_message = "El script de la huella no reescribe el MISMO fichero de cron que creo user_data: quedarian dos entradas nocturnas."
  }

  assert {
    condition = strcontains(
      file("${path.module}/backup_setup.sh.tpl"),
      regex("(?m)^(\\d+ \\d+ \\* \\* \\*) root", file("${path.module}/user_data.sh.tpl"))[0]
    )
    error_message = "La hora del respaldo ha divergido de la que declara user_data.sh.tpl. Tiene que ser EL MISMO cron, no uno nuevo al lado."
  }

  # El dump conserva su clave exacta: el runbook, la regla de expiracion y el
  # permiso de escritura estan escritos contra ella.
  assert {
    condition     = strcontains(aws_ssm_document.backup.content, "s3://takab-test-db-backups/takab-$FECHA.dump")
    error_message = "La clave del dump nocturno ha cambiado de forma. El §4.2 del runbook, la expiracion de modules/storage y el s3:PutObject del rol apuntan a la anterior."
  }

  # Y la huella cae BAJO EL MISMO PREFIJO, que es el criterio 1 de la ficha.
  assert {
    condition     = strcontains(aws_ssm_document.backup.content, "s3://takab-test-db-backups/takab-$FECHA.fingerprint.json")
    error_message = "La huella no se escribe bajo el prefijo del dump: quedaria fuera de la expiracion (se acumula para siempre) y fuera del s3:PutObject del rol (AccessDenied silencioso)."
  }
}

# --- 3. El permiso ya existente cubre la huella, y hay que demostrarlo --------
#
# No se anade ningun `s3:PutObject` nuevo: la clave de la huella comparte prefijo
# con la del dump. Eso es una afirmacion sobre la POLITICA, no sobre el script, y
# por eso se comprueba contra el JSON decodificado y contra el statement concreto
# (metodo aprendido por las malas en `pitr.tftest.hcl`).
run "el_permiso_de_escritura_del_dump_alcanza_a_la_huella" {
  command = plan

  variables {
    dump_key_prefix = "DUMPSENT-"
  }

  assert {
    condition = anytrue([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : anytrue([
        for r in try(tolist(s.Resource), [tostring(s.Resource)]) :
        r == "arn:aws:s3:::takab-test-db-backups/DUMPSENT-*"
      ])
      if s.Sid == "PutBackups"
    ])
    error_message = "El statement PutBackups ya no cubre el prefijo del dump, asi que tampoco cubre la huella: el `aws s3 cp` de las 08:00 moriria con AccessDenied."
  }
}

# --- 4. El anclaje, que es lo que hace que la huella sirva de algo ------------
#
# Una huella tomada a las 08:00:00 contra un dump que termina a las 08:04 declara
# ROJO sobre un restore perfecto: `restore_check` compara los conteos fila a fila
# y la base de produccion no esta quieta. Las dos mitades del anclaje tienen que
# estar en el mismo script o no hay anclaje.
run "la_huella_y_el_dump_comparten_snapshot" {
  command = plan

  assert {
    condition = alltrue([
      for aguja in ["--coordinate-with-dump", "--snapshot=", "dump.done", "snapshot.id"] :
      strcontains(aws_ssm_document.backup.content, aguja)
    ])
    error_message = "El script no ancla la huella al snapshot del dump. Sin ancla, `row_counts` da ROJO sobre un restore correcto y el operador aprende a desconfiar del verificador."
  }

  # Fail-open para el respaldo: tiene que haber un `pg_dump` SIN `--snapshot`
  # tambien, o una coordinacion rota se llevaria por delante el respaldo que hoy
  # funciona.
  assert {
    condition     = length(regexall("pg_dump -U postgres -Fc takab", aws_ssm_document.backup.content)) > 0
    error_message = "No queda camino de respaldo sin ancla: si la coordinacion falla, la noche se quedaria SIN dump. La huella es fail-closed; el dump, fail-open."
  }

  # El superusuario, y no takab_app: con RLS forzada los conteos de la huella
  # saldrian recortados y mentiria hacia abajo sobre el origen.
  assert {
    condition     = strcontains(aws_ssm_document.backup.content, "takab/dev/db/superuser")
    error_message = "La huella no se toma como superusuario: tiene que ver exactamente lo mismo que ve el pg_dump."
  }
}

# --- 5. La incognita de la ficha, preguntada en cada pasada -------------------
run "el_documento_pregunta_si_la_imagen_desplegada_sabe_tomar_la_huella" {
  command = plan

  assert {
    condition = alltrue([
      for aguja in ["TAKAB_CLOUD_IMAGE", "takab_api.ops.restore_check --help", "make cloud-images"] :
      strcontains(aws_ssm_document.backup.content, aguja)
    ])
    error_message = "El documento ya no comprueba que la imagen desplegada acepte la invocacion de la huella. Esa era la incognita real de T-2.73.a y no puede quedar en una casilla marcada de memoria."
  }
}

# --- 6. El timeout de la coordinacion no se puede poner a ras ----------------
run "un_timeout_de_coordinacion_irrisorio_no_se_puede_aplicar" {
  command = plan

  variables {
    dump_coordination_timeout_s = 30
  }

  expect_failures = [var.dump_coordination_timeout_s]
}
