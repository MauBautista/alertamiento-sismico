# [T-2.72] Las reglas de retencion de S3.
#
# Este modulo no tenia tests. Eso significaba que el hallazgo mas caro de T-2.72
# —`Expiration` sobre un bucket VERSIONADO no borra un byte: pone un delete marker
# y deja la version anterior facturandose para siempre— se podia deshacer entero
# sin que nada se pusiera rojo. Una bomba desactivada por un comentario es una
# bomba que vuelve a armarse sola.
#
# TODO lo que se comprueba aqui va contra `output.lifecycle_rules`, la TABLA de la
# que el modulo construye las reglas, y se recorre entera: todas las reglas de
# todos los buckets. Una regla nueva —del bucket que sea, con el prefijo que sea—
# pasa por las mismas guardias sin que haya que venir a apuntarla. Lo unico que se
# mira contra el recurso es el CABLEADO (que la tabla llega al provider), y ahi se
# usan escalares por la razon que explica el comentario de `output.lifecycle_rules`
# en `outputs.tf`: referenciar la lista de bloques `rule` hace que Terraform 1.15.8
# reviente al renderizar el fallo, en vez de imprimir el mensaje.
#
# Corre con: terraform -chdir=infra/terraform/modules/storage test

provider "aws" {
  region                      = "us-east-2"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

variables {
  account_id         = "000000000000"
  kms_key_arn        = "arn:aws:kms:us-east-2:000000000000:key/00000000-0000-0000-0000-000000000000"
  backfill_queue_arn = "arn:aws:sqs:us-east-2:000000000000:takab-test-backfill"

  # Centinelas: con los valores de produccion, un literal cableado en el modulo
  # coincidiria con la variable y las aserciones de prefijo pasarian sin
  # comprobar nada.
  db_dump_key_prefix = "DUMPSENT-"
  pitr_prefix        = "PITRSENT/"
  pitr_server_name   = "SRVSENT"
  pitr_retention = {
    wal_days                  = 40
    base_backup_interval_days = 5
    chain_margin              = 3
  }
}

run "la_expiracion_de_verdad_borra_y_la_cadena_pitr_no_se_parte" {
  command = plan

  # --- 1. La PREMISA: los tres buckets estan versionados ---------------------
  #
  # Todo lo demas se apoya en esto. Si algun dia se apagara el versionado, las
  # aserciones de `noncurrent_days` seguirian verdes exigiendo algo que ya no
  # haria falta — verde vacio. Aqui queda dicho de que depende la clase.
  # Los tres se nombran uno a uno en vez de recorrer el mapa: un `for` sobre
  # `aws_s3_bucket_versioning.this` referencia el mapa ENTERO y eso hace reventar
  # el renderizado del fallo (mismo motivo que la lista `rule`; ver la cabecera).
  # Que la lista siga siendo completa lo vigila la asercion 10.
  assert {
    condition = (
      aws_s3_bucket_versioning.this["evidence"].versioning_configuration[0].status == "Enabled"
      && aws_s3_bucket_versioning.this["transfer"].versioning_configuration[0].status == "Enabled"
      && aws_s3_bucket_versioning.this["db_backups"].versioning_configuration[0].status == "Enabled"
    )
    error_message = "Algun bucket dejo de estar versionado. Toda la clase de aserciones de abajo (una expiracion sin noncurrent_days no borra nada) se apoya en esta premisa."
  }

  # --- 2. LA CLASE: expirar sin podar las noncurrent no borra un byte ---------
  #
  # Derivada sobre TODAS las reglas de TODOS los buckets de la tabla. No enumera
  # ids ni buckets: la lista la pone el modulo.
  assert {
    condition = length([
      for r in flatten(values(output.lifecycle_rules)) : r
      if r.expiration_days != null && r.noncurrent_days == null
    ]) == 0
    error_message = "Hay una regla con `expiration_days` y sin `noncurrent_days` sobre un bucket VERSIONADO. Esa regla no borra nada: pone un delete marker, la version anterior se queda como noncurrent facturandose para siempre, y —peor para el PITR— el delete marker esconde el objeto al restaurador aunque los bytes sigan ahi. Parece una politica de retencion y es un cambio de etiqueta."
  }

  # --- 3. LA CADENA PITR NO PUEDE CAER BAJO UN CAJON DE SASTRE ----------------
  #
  # Un backup base sin los WAL que le siguen no llega a ningun punto en el tiempo,
  # y unos WAL sin su base no arrancan: los objetos de esta cadena NO son
  # independientes, asi que una regla con filtro vacio puede borrar exactamente la
  # mitad que hacia falta. Y no se nota hasta que se intenta restaurar.
  #
  # Se acota al bucket que ALOJA la cadena: en `transfer` el filtro vacio es
  # correcto y esta razonado en el modulo.
  assert {
    condition = length([
      for r in output.lifecycle_rules.db_backups : r
      if r.expiration_days != null && r.prefix == ""
    ]) == 0
    error_message = "Una regla del bucket de respaldos expira con filtro VACIO. Ese bucket guarda dos cosas con vidas distintas —dumps sueltos y una CADENA de PITR— y S3 no sabe expresar `todo menos este prefijo`: un cajon de sastre alcanza SIEMPRE la cadena, diga lo que diga el comentario de al lado."
  }

  # --- 4. Los prefijos SALEN de las variables ---------------------------------
  #
  # Centinelas: si alguien cablea "pitr/" o "takab-" en el modulo, esto se cae. Es
  # lo que impide que la retencion gobierne un prefijo y el archivador escriba en
  # otro — la forma exacta en que una cadena PITR se rompe sin que ningun plan se
  # ponga rojo. Los prefijos son los REALES de barman-cloud, verificados
  # ejecutandolo.
  assert {
    condition = toset([
      for r in output.lifecycle_rules.db_backups : r.prefix
    ]) == toset(["DUMPSENT-", "PITRSENT/SRVSENT/wals/", "PITRSENT/SRVSENT/base/", "PITRSENT/"])
    error_message = "Los prefijos de las reglas del bucket de respaldos no son los derivados de las variables (`<pitr_prefix><pitr_server_name>/wals/`, `.../base/`, el del dump y la raiz PITR para el barrido de multipart). Si divergen, la retencion gobierna un sitio y el archivado escribe en otro."
  }

  # --- 5. Las dos mitades de la cadena expiran AL MISMO RITMO -----------------
  assert {
    condition = length(distinct([
      for r in output.lifecycle_rules.db_backups : r.expiration_days
      if startswith(r.prefix, "PITRSENT/") && r.expiration_days != null
    ])) == 1
    error_message = "Los WAL y los backups base de la cadena PITR expiran a ritmos distintos. Un backup base que sobreviva a sus WAL no llega a ningun punto en el tiempo, y unos WAL que sobrevivan a su base no arrancan."
  }

  # --- 6. Y esa retencion es la declarada, no otra ----------------------------
  #
  # Esta asercion SOLA no basta y esta medido: cablear `40` —el mismo numero que el
  # centinela— la deja en verde. Es el mismo agujero que tuvo la derivacion del RPO:
  # una igualdad con UN solo valor de entrada no distingue una variable de una
  # constante que hoy coincide. La otra mitad es el segundo bloque, que mueve el
  # dato.
  assert {
    condition = length([
      for r in output.lifecycle_rules.db_backups : r
      if startswith(r.prefix, "PITRSENT/") && r.expiration_days == var.pitr_retention.wal_days
    ]) == 2
    error_message = "La retencion de la cadena PITR no sale de `pitr_retention.wal_days`. Cableada, deja de cumplirse la desigualdad que `modules/database` valida (retencion >= intervalo * margen) y la cadena queda partida sin que nada falle."
  }

  # --- 7. El multipart incompleto SI se barre ---------------------------------
  assert {
    condition = length([
      for r in output.lifecycle_rules.db_backups : r
      if r.abort_multipart_days != null && r.prefix == var.pitr_prefix
    ]) == 1
    error_message = "Falta el barrido de multipart incompleto sobre la raiz del prefijo PITR. El backup base sube en multipart; si falla a la mitad, las partes quedan invisibles al listado y facturandose para siempre."
  }

  # --- 8. `evidence` NO tiene retencion, y eso es regla de oro 11 -------------
  #
  # La direccion contraria a todo lo anterior, y por eso se comprueba: la
  # evidencia de incidentes y los dictamenes no se podan JAMAS. Que este modulo
  # gane una tabla de retencion no puede convertirse en la ocasion de meter ahi el
  # bucket que no debe tenerla.
  assert {
    condition     = !contains(keys(output.lifecycle_rules), "evidence")
    error_message = "El bucket de evidencia ha entrado en la tabla de retencion. La evidencia de incidentes y los dictamenes no se podan nunca (regla de oro 11): si algun dia hace falta ciclarla, esa decision se toma fuera de aqui y con su propia justificacion."
  }

  # --- 9. CABLEADO: la tabla llega de verdad al provider ----------------------
  #
  # Todo lo de arriba comprueba la POLITICA (la tabla). Esto comprueba que el
  # `dynamic` la traduce: si alguien borrase el bloque `noncurrent_version_
  # expiration`, la tabla seguiria perfecta y ninguna asercion anterior se
  # enteraria. Se usan escalares a proposito (ver la cabecera).
  assert {
    condition = (
      try(aws_s3_bucket_lifecycle_configuration.this["db_backups"].rule[0].id, "") == output.lifecycle_rules.db_backups[0].id
      && try(aws_s3_bucket_lifecycle_configuration.this["db_backups"].rule[0].noncurrent_version_expiration[0].noncurrent_days, 0) == 1
      && try(aws_s3_bucket_lifecycle_configuration.this["db_backups"].rule[0].expiration[0].days, 0) == 60
      && try(aws_s3_bucket_lifecycle_configuration.this["transfer"].rule[0].noncurrent_version_expiration[0].noncurrent_days, 0) == 1
    )
    error_message = "La tabla de retencion no esta llegando al provider: el `dynamic` que traduce `noncurrent_days`/`expiration_days` a bloques se ha roto. La politica seria correcta sobre el papel y S3 no borraria nada."
  }

  # --- 10. Los dos censos: nadie se cuela por fuera ---------------------------
  #
  # Lo unico enumerado del archivo, declarado como tal. Terraform no sabe iterar
  # sobre "todos los recursos de tipo X", asi que esto lee el `main.tf` y exige dos
  # cosas: que la unica configuracion de lifecycle sea la que se construye desde la
  # tabla, y que los buckets del modulo sigan siendo los tres que la asercion 1
  # comprueba uno a uno. Un recurso escrito a mano al margen, o un bucket nuevo, se
  # saltarian todas las guardias anteriores; esto lo impide. Mismo truco que
  # `api/tests/ops/test_muting.py` con el catalogo de alarmas.
  assert {
    condition = toset(flatten(regexall(
      "resource \"aws_s3_bucket_lifecycle_configuration\" \"([a-z0-9_]+)\"",
      file("${path.module}/main.tf")
    ))) == toset(["this"])
    error_message = "Hay una configuracion de lifecycle escrita FUERA de la tabla `local.lifecycle_rules`. Sus reglas no pasarian por ninguna de las guardias de este archivo: metela en la tabla."
  }

  assert {
    condition = toset(flatten(regexall(
      "(?m)^    ([a-z_]+) += \"takab-dev-",
      file("${path.module}/main.tf")
    ))) == toset(["evidence", "transfer", "db_backups"])
    error_message = "Cambio el censo de buckets del modulo. La asercion 1 (todos versionados) los nombra uno a uno porque recorrer el mapa hace reventar el renderizado del fallo: un bucket nuevo quedaria sin esa comprobacion, y con el toda la premisa de la clase de aserciones de retencion."
  }
}

# La retencion SE MUEVE con la variable, o no salia de ella.
#
# Comprobar una igualdad con un solo valor de entrada no distingue una variable de
# una constante que hoy coincide: con `wal_days = 40` en el bloque de arriba, un
# `40` cableado en el modulo pasa las diez aserciones. Aqui el dato cambia, y
# ninguna constante puede satisfacer los dos bloques a la vez.
run "la_retencion_de_la_cadena_se_mueve_con_su_variable" {
  command = plan

  variables {
    pitr_retention = {
      wal_days                  = 25
      base_backup_interval_days = 5
      chain_margin              = 3
    }
  }

  assert {
    condition = length([
      for r in output.lifecycle_rules.db_backups : r
      if startswith(r.prefix, "PITRSENT/") && r.expiration_days == 25
    ]) == 2
    error_message = "La retencion de la cadena PITR no siguio a `pitr_retention.wal_days` al cambiarla: es una constante disfrazada, y la desigualdad que `modules/database` valida (retencion >= intervalo * margen) se estaria comprobando sobre un numero que no gobierna nada."
  }
}
