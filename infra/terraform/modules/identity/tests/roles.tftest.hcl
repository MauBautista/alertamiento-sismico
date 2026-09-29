# [T-9.81 · D-42] Los grupos del pool principal son los SIETE roles canonicos.
#
# `migrar_roles_7.py --verify` dio cero: nadie tiene ya rol ni grupo viejo, y la API
# responde 401 `rol_retirado` a un token con `soc_operator`, `security_guard` o
# `building_admin` (`api/src/takab_api/auth/roles.py`). Los tres grupos se borran aqui.
# Esta prueba ata el censo de grupos a la fuente de la API: si alguien reanade un
# grupo viejo (o uno que la API no conoce), el usuario que se meta en el no entraria
# nunca, y nadie lo veria hasta que llamara.
#
# Corre con: terraform -chdir=infra/terraform/modules/identity test

provider "aws" {
  region                      = "us-east-2"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

variables {
  account_id                 = "000000000000"
  ses_verified_emails        = []
  ses_configuration_set_name = "takab-test-correo"
}

run "los_grupos_son_los_siete_canonicos_de_la_api" {
  command = plan

  assert {
    condition = toset(keys(aws_cognito_user_group.this)) == toset(flatten(regexall(
      "\"([a-z_]+)\",",
      regex(
        "CANONICAL_ROLES: tuple\\[str, \\.\\.\\.\\] = \\(([^)]*)\\)",
        file("${path.module}/../../../../api/src/takab_api/auth/roles.py")
      )[0]
    )))
    error_message = "Los grupos del pool principal ya no son EXACTAMENTE los `CANONICAL_ROLES` de `api/src/takab_api/auth/roles.py`. Un grupo de mas es un rol que la API no reconoce (o uno retirado: 401 `rol_retirado`); uno de menos deja sin entrar a quien lo tenga."
  }

  assert {
    condition     = length(keys(aws_cognito_user_group.this)) == 7
    error_message = "D-42 fija siete roles; el pool principal tiene otro numero de grupos."
  }

  assert {
    condition = length(setintersection(
      toset(keys(aws_cognito_user_group.this)),
      toset(["soc_operator", "security_guard", "building_admin"])
    )) == 0
    error_message = "Volvio un grupo retirado por D-42 (T-9.81). Su token es 401 `rol_retirado` en la API: meter a alguien en el es dejarlo fuera."
  }
}
