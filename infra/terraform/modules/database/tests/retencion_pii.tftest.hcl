# [T-2.81.a] El job de retencion de PII existia y no lo llamaba nadie.
#
# Una retencion que nadie ejecuta es una politica escrita, no una cumplida. Esto
# blinda las tres cosas que hacen que eso deje de ser cierto, y ninguna de las
# tres es "existe un recurso": son las que, si se rompen, dejan el cron con cara
# de funcionar mientras no poda nada.
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
  # [T-2.163] El pool contra el que se reconcilian las bajas. Los tests de abajo
  # comprueban que llega hasta el env del contenedor Y que el permiso lo sigue.
  cognito_pool = {
    id  = "us-east-2_TESTPOOL"
    arn = "arn:aws:cognito-idp:us-east-2:000000000000:userpool/us-east-2_TESTPOOL"
  }

  subnet_id   = "subnet-0000000000test000"
  sg_db_id    = "sg-0000000000test000"
  kms_key_arn = "arn:aws:kms:us-east-2:000000000000:key/00000000-0000-0000-0000-000000000000"
  db_backups_bucket = {
    name = "takab-test-db-backups"
    arn  = "arn:aws:s3:::takab-test-db-backups"
  }
  instance_type   = "t3.small"
  dump_key_prefix = "dump/"
  pitr = {
    prefix                    = "pitr/"
    server_name               = "takab-test"
    wal_retention_days        = 14
    base_backup_interval_days = 7
    chain_margin              = 2
  }
}

# Los mismos overrides que `pitr.tftest.hcl`, y por la misma razon medida alli:
# sin credenciales, `plan` muere en las data sources de EC2 y los ARN de los
# secretos quedan "(known after apply)", con lo que TODA asercion sobre el
# contenido del documento SSM —que interpola el ARN del secreto de `takab_app`—
# seria inevaluable. Van fuera de los `run` porque los bloques de
# `expect_failures` de abajo tambien planifican.
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

run "el_documento_ssm_programa_la_corrida_y_publica_su_edad" {
  command = plan

  # El documento tiene que instalar LAS DOS piezas. Con solo el cron, la
  # retencion corre y nadie se entera de que dejo de correr; con solo el
  # publicador, la alarma vigila una corrida que no existe.
  assert {
    condition = (
      strcontains(aws_ssm_document.prune_pii.content, "takab-prune-pii.sh")
      && strcontains(aws_ssm_document.prune_pii.content, "takab-prune-pii-age.sh")
    )
    error_message = "el documento SSM debe instalar el job Y el publicador de su edad: con uno solo, o la retencion no corre o nadie se entera de que dejo de correr."
  }

  # El cron es la CADENCIA DECLARADA de la ficha. 06:00 UTC no es un hueco
  # cualquiera: DLM a las 03:00, backup base a las 04:00, su scan a las 05:00 y
  # el dump logico a las 08:00 — la retencion va ANTES del dump para que el
  # respaldo del dia se lleve la PII ya podada.
  assert {
    condition     = strcontains(aws_ssm_document.prune_pii.content, "0 6 * * * root /opt/takab/bin/takab-prune-pii.sh")
    error_message = "la corrida diaria debe quedar programada a las 06:00 UTC (entre el scan del backup base y el dump logico): sin linea de cron, el documento instala un script que nadie invoca."
  }

  # `--apply`, no simulacro. Y es seguro porque sin plazos configurados cada
  # regla queda deshabilitada; lo que no seria seguro es un cron que solo simula
  # eternamente y deja creyendo que la retencion se cumple.
  assert {
    condition     = strcontains(aws_ssm_document.prune_pii.content, "takab_api.ops.prune_pii --apply")
    error_message = "el cron debe invocar el job con --apply: sin el flag el job SOLO cuenta, y la retencion seguiria sin ejecutarse nunca."
  }

  # La metrica sale de la BASE (`pii_retention_runs`), no del exit code del cron.
  # Es la diferencia entre vigilar la retencion y vigilar el cron: una corrida
  # que aborta escribe `ok = false`, la edad no se refresca y la alarma sube.
  assert {
    condition = (
      strcontains(aws_ssm_document.prune_pii.content, "FROM pii_retention_runs WHERE ok")
      && strcontains(aws_ssm_document.prune_pii.content, "PiiRetentionAgeSeconds")
    )
    error_message = "el publicador debe derivar la edad de `pii_retention_runs WHERE ok`: medir el exit code del cron dejaria en verde a un job que falla todos los dias."
  }

  # La asociacion es lo que convierte esto en infraestructura declarada. Un
  # documento SSM sin asociacion es un script que alguien tiene que acordarse de
  # correr — exactamente el estado del que sale esta ficha.
  assert {
    condition = (
      aws_ssm_association.prune_pii.schedule_expression == "rate(1 day)"
      && aws_ssm_association.prune_pii.name == aws_ssm_document.prune_pii.name
    )
    error_message = "la asociacion debe reimponer el estado deseado a diario y apuntar a ESTE documento: sin ella, recrear la instancia deja la retencion sin programar y nada se pone rojo."
  }
}

run "sin_plazos_declarados_el_cron_no_poda_absolutamente_nada" {
  command = plan

  # El default es el estado de HOY (los plazos son decision legal/de negocio, no
  # del programador) y tiene que ser inerte: el job corre, deja constancia y no
  # toca una fila. Si alguna variable de plazo se colara aqui, un `apply` de
  # infraestructura empezaria a borrar datos personales sin que nadie lo decidiera.
  # Se busca la ASIGNACION (`_DAYS=`) y no el prefijo: el prefijo aparece en la
  # cabecera del script, explicando justamente que sin el no se poda nada. Buscar
  # el prefijo suelto habria dado un rojo por un comentario — el mismo error que
  # `pitr.tftest.hcl` documenta para las politicas IAM.
  assert {
    condition     = !strcontains(aws_ssm_document.prune_pii.content, "_DAYS=")
    error_message = "con `pii_retention_windows_days` vacio el documento NO debe declarar ninguna variable de plazo: el default bajo incertidumbre es no borrar nada."
  }

  assert {
    condition     = output.pii_retention.reglas_activas == 0
    error_message = "el informe del modulo debe decir que no hay ninguna regla con plazo: es lo que se lee para saber si la retencion esta configurada o solo programada."
  }
}

run "el_plazo_declarado_llega_al_job_con_el_nombre_que_el_job_lee" {
  command = plan

  variables {
    pii_retention_windows_days = {
      "push_tokens.token"      = 400
      "user_profiles.identity" = 365
    }
  }

  # La traduccion clave-de-regla -> variable de entorno es el unico punto donde
  # este modulo y el codigo Python tienen que decir lo mismo
  # (`privacy/retention.RetentionRule.env_var`). Si divergen, el job lee su
  # entorno, no encuentra el plazo y deja la regla DESHABILITADA — o sea que el
  # `apply` sale verde y la retencion sigue sin ejecutarse.
  assert {
    condition = (
      strcontains(aws_ssm_document.prune_pii.content, "TAKAB_API_RETENTION_PUSH_TOKENS_TOKEN_DAYS=400")
      && strcontains(aws_ssm_document.prune_pii.content, "TAKAB_API_RETENTION_USER_PROFILES_IDENTITY_DAYS=365")
    )
    error_message = "el plazo debe viajar con el nombre EXACTO que compone `RetentionRule.env_var` (clave en mayusculas, puntos a guiones bajos, sufijo _DAYS): con otro nombre el job no lo ve y deja la regla deshabilitada en silencio."
  }
}

run "el_umbral_de_la_alarma_se_deriva_de_la_cadencia_y_del_margen" {
  command = plan

  variables {
    pii_retention_chain_margin = 3
  }

  # Mismo criterio que `base_backup_max_age_s`: el umbral no es un numero de
  # politica escrito en la alarma, es la cadencia del cron —que vive aqui— por el
  # margen declarado. Un literal en `modules/observability` vigilaria una
  # periodicidad distinta de la programada el dia que la cadencia cambie.
  assert {
    condition     = output.pii_retention_max_age_s == 3 * 86400
    error_message = "el umbral debe salir de cadencia x margen: con un literal, cambiar la cadencia dejaria a la alarma vigilando una periodicidad que ya no ocurre."
  }
}

run "un_margen_de_uno_no_se_puede_aplicar" {
  command = plan

  variables {
    pii_retention_chain_margin = 1
  }

  expect_failures = [var.pii_retention_chain_margin]
}

run "un_plazo_de_cero_dias_no_se_puede_aplicar" {
  command = plan

  variables {
    pii_retention_windows_days = { "push_tokens.token" = 0 }
  }

  # El job trata 0 (y negativo) como "sin configurar" y deshabilita la regla. Un
  # cero aceptado aqui se leeria como "podar de inmediato" y significaria justo
  # lo contrario: la regla no corre y nadie lo nota.
  expect_failures = [var.pii_retention_windows_days]
}

run "una_clave_que_no_existe_en_el_plan_no_se_puede_aplicar" {
  command = plan

  variables {
    pii_retention_windows_days = { "push_tokens.tokens" = 400 }
  }

  # Un plural de mas. El job ignora las variables de entorno que no reconoce, asi
  # que sin esta validacion el `apply` saldria verde, el operador creeria haber
  # declarado el plazo y esa regla seguiria deshabilitada para siempre.
  expect_failures = [var.pii_retention_windows_days]
}

# [T-2.152] El publicador distingue TRES estados, no dos.
#
# El defecto: `EDAD="$(psql ...)"` bajo `set -euo pipefail`. Cuando psql FALLA, la
# asignacion devuelve distinto de cero y `set -e` mata el script ANTES del `if`
# que implementa el fallback. O sea que el fallback —escrito para que la alarma
# "nazca diciendo la verdad"— era inalcanzable justo cuando hacia falta: en un
# entorno recien desplegado, "no ha corrido nunca" y "no se puede preguntar" son
# el mismo instante.
#
# Se comprueba la SEPARACION (`|| ESTADO=`), no la ausencia de `set -e`: quitar el
# `set -e` seria peor arreglo, porque entonces cualquier fallo posterior pasaria
# desapercibido.
run "el_publicador_separa_no_se_pudo_preguntar_de_no_ha_corrido_nunca" {
  command = plan

  assert {
    condition = (
      strcontains(aws_ssm_document.prune_pii.content, "ESTADO=0") &&
      strcontains(aws_ssm_document.prune_pii.content, "|| ESTADO=")
    )
    error_message = "El publicador debe capturar el ESTADO de la consulta aparte de su salida. Sin eso, con `set -euo pipefail` un psql que falla mata el script antes del fallback, y este no puede correr precisamente en el escenario para el que existe (tabla ausente = no se puede preguntar Y no ha corrido nunca, a la vez)."
  }

  assert {
    condition     = strcontains(aws_ssm_document.prune_pii.content, "NO SE PUDO PREGUNTAR")
    error_message = "Cuando la consulta falla, el script tiene que DECIR que no se pudo preguntar y no publicar nada. Publicar el fallback ahi seria afirmar una edad que nadie midio."
  }
}

# La otra mitad: la asociacion no puede salir verde si su publicador no publico.
#
# Antes la primera medida iba con `|| log AVISO`, asi que el comando SSM terminaba
# en `Success` con la metrica sin existir. Un `Success` que convive con "no se
# pudo publicar" en su propia salida es un fallback presentandose como `ok`.
run "la_asociacion_no_reporta_exito_si_la_primera_medida_no_se_publico" {
  command = plan

  assert {
    condition = (
      !strcontains(aws_ssm_document.prune_pii.content, "takab-prune-pii-age.sh ||") &&
      strcontains(aws_ssm_document.prune_pii.content, "if ! /opt/takab/bin/takab-prune-pii-age.sh; then")
    )
    error_message = "La primera medida NO puede tragarse su fallo con `|| log`. Si no se publica, la asociacion debe salir en ROJO: en el momento de instalar esto la base tiene que estar alcanzable y el esquema al dia, y si no lo esta es deriva de despliegue que hay que ver ahora y no dentro de un mes."
  }
}


# ═══════════════════════════════════════════════════════════════════════════
# [T-2.163] La reconciliacion de bajas, desplegada y no inerte
# ═══════════════════════════════════════════════════════════════════════════
#
# T-2.143 se cerro con el codigo escrito y probado, y en produccion NO HACIA
# NADA: el job recibia un env con una sola clave (`DATABASE_URL`), asi que el
# contenedor caia al directorio SIMULADO y abortaba cada noche. El rol de
# instancia tampoco tenia un solo permiso `cognito-idp:*`.
#
# Se verifico el codigo DENTRO del contenedor y no el entorno desde el que se
# invoca. Estas aserciones son ese entorno.

run "el_job_recibe_el_pool_y_no_cae_al_directorio_simulado" {
  command = plan

  assert {
    condition     = strcontains(local.prune_pii_setup_script, "TAKAB_API_COGNITO_USER_POOL_ID=us-east-2_TESTPOOL")
    error_message = "el script del job no escribe TAKAB_API_COGNITO_USER_POOL_ID en el env del contenedor: `build_user_directory()` caeria al directorio SIMULADO y la reconciliacion de bajas quedaria desplegada e INERTE (paso en produccion el 2026-08-23)."
  }

  # La region va aparte porque el cliente de Cognito la necesita y NO viene del
  # DSN. Sin ella el fallo seria distinto —y peor de leer— que el del pool.
  assert {
    condition     = strcontains(local.prune_pii_setup_script, "AWS_REGION=us-east-2")
    error_message = "el env del job no lleva la region: el cliente de Cognito no sabria a que endpoint preguntar."
  }
}

run "el_permiso_de_cognito_existe_y_esta_acotado" {
  command = plan

  # Las DOS cosas, y en el mismo statement. Comprobar solo que el ARN aparece no
  # basta: se midio rompiendolo, y cambiar la accion a `sts:GetCallerIdentity`
  # dejaba el ARN en su sitio y el test en verde. Un permiso es un verbo SOBRE un
  # recurso; verificar la mitad no verifica nada.
  assert {
    condition = anytrue([
      for st in jsondecode(aws_iam_role_policy.db.policy).Statement :
      try(st.Sid, "") == "ReconciliarBajasListarPool"
      && try(st.Action, "") == "cognito-idp:ListUsers"
      && try(st.Resource, "") == "arn:aws:cognito-idp:us-east-2:000000000000:userpool/us-east-2_TESTPOOL"
    ])
    error_message = "el rol no concede `cognito-idp:ListUsers` SOBRE el pool declarado: el job preguntaria y AWS le diria que no. Tener la variable SIN el permiso es el tercer modo de fallo que la validacion de `cognito_pool` existe para impedir."
  }

  # SOLO listar. La reconciliacion lee quien existe y escribe en su PROPIA base;
  # un job de limpieza nocturna con `AdminDisableUser` podria dejar a alguien
  # fuera de su edificio.
  assert {
    condition = !anytrue([
      for verbo in ["AdminDisableUser", "AdminDeleteUser", "AdminUpdateUserAttributes", "cognito-idp:*"] :
      strcontains(aws_iam_role_policy.db.policy, verbo)
    ])
    error_message = "el rol ganó permisos de ESCRITURA sobre Cognito. La reconciliacion solo lee: dar de baja cuentas jamas es cosa de un job nocturno."
  }
}

run "sin_pool_declarado_no_se_concede_permiso_ninguno" {
  command = plan

  variables {
    cognito_pool = { id = "", arn = "" }
  }

  # El caso "sin reconciliacion" tiene que ser coherente consigo mismo: ni
  # variable ni permiso. Sin esto, el objeto vacio podria dejar un statement con
  # `Resource = ""` — que no es "nada", es un ARN invalido.
  assert {
    condition     = !strcontains(aws_iam_role_policy.db.policy, "cognito-idp")
    error_message = "sin pool declarado no debe quedar NINGUN statement de Cognito en la politica."
  }
  assert {
    condition     = strcontains(local.prune_pii_setup_script, "TAKAB_API_COGNITO_USER_POOL_ID=\n")
    error_message = "sin pool, la clave debe quedar VACIA y presente: asi el contenedor dice `es el simulado` en vez de heredar un valor viejo del entorno de la maquina."
  }
}
