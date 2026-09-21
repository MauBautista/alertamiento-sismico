# [T-7.26] Lo que la instancia puede LEER de Secrets Manager.
#
# Por que existe. El entorno declara en `worker_secret_arns` los secretos que el
# proceso resuelve en runtime con el rol de la instancia: las claves HMAC de
# comandos (T-1.38) y, desde T-7.26, la clave de OpenRouter. Ese contrato no tenia
# ninguna prueba. Si un refactor de la politica dejara de concatenar la lista, el
# `plan` seguiria limpio y el sintoma seria mudo y tardio: GetSecretValue responde
# AccessDenied, `resolve_api_key` degrada a cadena vacia y la nube sigue
# escribiendo prosa determinista — con la bandera encendida y sin decir por que.
#
# El ARN es un CENTINELA (`SECRETOSENT`). Con un nombre de produccion, cualquier
# constante cableada en el modulo podria coincidir con la variable y el test
# pasaria sin comprobar nada.
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

  worker_secret_arns = [
    "arn:aws:secretsmanager:us-east-2:000000000000:secret:SECRETOSENT/gateway-hmac/*",
    "arn:aws:secretsmanager:us-east-2:000000000000:secret:SECRETOSENT/openrouter-*",
  ]
}

# Los mismos overrides que `pitr.tftest.hcl`, y por la misma razon medida alli: sin
# ellos la politica queda "(known after apply)" en `plan` y TODA asercion sobre ella
# es inevaluable — verde vacio.
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

run "cada_secreto_que_el_entorno_declara_llega_a_la_politica" {
  command = plan

  # Contra el STATEMENT decodificado, nunca con `strcontains`: una politica tiene
  # muchos statements y una subcadena suelta casi siempre existe en otro. Es la
  # nota de metodo de `pitr.tftest.hcl`, aprendida por las malas alli.
  assert {
    condition = length([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : s
      if try(s.Sid, "") == "ReadDbSecrets"
      && try(contains(tolist(s.Action), "secretsmanager:GetSecretValue"), try(s.Action, "") == "secretsmanager:GetSecretValue")
      && try(contains(tolist(s.Resource), "arn:aws:secretsmanager:us-east-2:000000000000:secret:SECRETOSENT/gateway-hmac/*"), false)
      && try(contains(tolist(s.Resource), "arn:aws:secretsmanager:us-east-2:000000000000:secret:SECRETOSENT/openrouter-*"), false)
    ]) == 1
    error_message = "`ReadDbSecrets` tiene que conceder GetSecretValue sobre TODOS los ARN de `worker_secret_arns`, no solo sobre los secretos de la base. Sin el de OpenRouter, desplegar con la capa narrativa encendida deja la nube escribiendo prosa determinista: AccessDenied y `resolve_api_key` degrada en silencio."
  }

  # Y el permiso sigue siendo ACOTADO. Un ARN de secreto que no venga de la lista del
  # entorno daria a la instancia las claves privadas mTLS de los gabinetes, que viven
  # en Secrets Manager y jamas debe leer la nube.
  #
  # Se comprueba por LISTA BLANCA y no prohibiendo comodines, y la diferencia no es de
  # estilo: medido el 2026-09-21, la version por lista negra —que solo rechazaba `*` y
  # `arn:aws:secretsmanager:*`— dejaba pasar en VERDE un statement con
  # `arn:aws:secretsmanager:us-east-2:<cuenta>:secret:*`, que concede TODOS los
  # secretos de la cuenta, incluidas esas claves mTLS. Era una guarda ciega justo al
  # comodin que su propio comentario decia prevenir: una lista negra solo caza las
  # formas que alguien se acordo de enumerar.
  #
  # Los permitidos se DERIVAN: los secretos de la base que el modulo crea, mas
  # `worker_secret_arns` tal y como lo declara el entorno. Un recurso de mas —de la
  # forma que sea— sobra de esa lista y se pone rojo.
  assert {
    condition = length([
      for s in jsondecode(aws_iam_role_policy.db.policy).Statement : s
      if length([
        for a in try(tolist(s.Action), [tostring(s.Action)]) : a
        if a == "*" || startswith(a, "secretsmanager:")
      ]) > 0
      && length([
        for r in try(tolist(s.Resource), [tostring(s.Resource)]) : r
        if !contains(
          concat([for x in aws_secretsmanager_secret.db : x.arn], var.worker_secret_arns),
          r
        )
      ]) > 0
    ]) == 0
    error_message = "Algun statement concede secretsmanager sobre un ARN que el entorno NO declara. El rol de la instancia solo puede leer los secretos de la base y los de `worker_secret_arns`: un comodin —incluido `...:secret:*`, que parece acotado y no lo es— le daria tambien las claves privadas mTLS de los gabinetes."
  }
}
