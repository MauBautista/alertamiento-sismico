# [T-8.05 · D-38] Cuanto vive un refresh token en cada app client.
#
# D-38 (2026-09-22) fija la duracion de la sesion POR ROL: brigadista e inspector
# 30 dias, ocupante 90, el resto 24 h. Cognito no puede expresarlo: la validez del
# refresh es POR APP CLIENT, y los clientes se comparten entre roles con duraciones
# distintas (el tactico lo usan brigadista, inspector, security_guard y
# building_admin; el web, los siete roles de consola). Por eso el reparto es:
#
#   - cada cliente declara el MAXIMO de los roles que lo usan (este archivo);
#   - la API impone el tope por rol contando desde `auth_time`, la hora del login
#     real, que el refresco no renueva (`api/src/takab_api/auth/session_age.py`,
#     `matrix.SESSION_MAX_AGE_S`), y responde 401 `sesion_expirada`.
#
# Lo que ancla este archivo son las dos direcciones del error:
#   - un cliente MAS CORTO que el rol mas largo que lo usa rompe D-38 en silencio:
#     el inspector volveria a teclear contraseña y codigo antes de su mes, y
#     ningun test de la API lo veria (la API solo recorta, no alarga);
#   - un cliente MAS LARGO no alarga ninguna sesion (la API corta antes), pero
#     deja refresh tokens vivos que la API rechazara siempre: basura con valor de
#     credencial. Por eso se exige igualdad y no ">= algo".
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

run "cada_cliente_declara_el_maximo_de_los_roles_que_lo_usan" {
  command = plan

  # --- 1. EL CENSO de clientes: uno nuevo no entra sin su duracion ------------
  assert {
    condition = toset(flatten(regexall(
      "resource \"aws_cognito_user_pool_client\" \"([a-z0-9_]+)\"",
      file("${path.module}/main.tf")
    ))) == toset(["web", "mobile_occupants", "mobile_tactical"])
    error_message = "Cambio el censo de app clients de Cognito. Cada cliente declara el maximo de la duracion de sesion de los roles que lo usan (D-38); uno nuevo entraria sin esa comprobacion y su refresh decidiria en silencio cuanto tarda en pedirse otra vez la contraseña y el codigo."
  }

  # --- 2. Consola web: 30 dias (el inspector; el resto lo recorta la API) -----
  assert {
    condition     = aws_cognito_user_pool_client.web.refresh_token_validity == 30 && aws_cognito_user_pool_client.web.token_validity_units[0].refresh_token == "days"
    error_message = "El refresh del cliente web dejo de ser 30 dias. Lo usa el inspector, que por D-38 no vuelve a teclear contraseña ni codigo en un mes; el tope de 24 h del resto de roles de consola lo pone la API con auth_time, no este numero."
  }

  # --- 3. Tactico movil: 30 dias (brigadista e inspector) ---------------------
  assert {
    condition     = aws_cognito_user_pool_client.mobile_tactical.refresh_token_validity == 30 && aws_cognito_user_pool_client.mobile_tactical.token_validity_units[0].refresh_token == "days"
    error_message = "El refresh del cliente tactico dejo de ser 30 dias. Brigadista e inspector lo usan y D-38 les da un mes sin volver a autenticarse; security_guard y building_admin comparten el cliente y su tope de 24 h lo impone la API."
  }

  # --- 4. Ocupantes: 90 dias, igual que su tope en la API ---------------------
  assert {
    condition     = aws_cognito_user_pool_client.mobile_occupants.refresh_token_validity == 90 && aws_cognito_user_pool_client.mobile_occupants.token_validity_units[0].refresh_token == "days"
    error_message = "El refresh del cliente de ocupantes dejo de ser 90 dias. D-38 mantuvo los 90 dias del ocupante (spec movil §8: la app debe poder alertar sin pedir login en plena crisis) y la API topa al rol occupant en el mismo valor."
  }

  # --- 5. Los tokens que viajan siguen durando una hora -----------------------
  #
  # La sesion larga la da el REFRESH; el ID token que la API verifica sigue
  # caducando a los 60 minutos. Alargarlo haria que un token robado valiera mas y
  # que una baja o un cambio de rol tardaran mas en surtir efecto.
  assert {
    condition = alltrue([
      aws_cognito_user_pool_client.web.id_token_validity == 60,
      aws_cognito_user_pool_client.mobile_tactical.id_token_validity == 60,
      aws_cognito_user_pool_client.mobile_occupants.id_token_validity == 60,
      aws_cognito_user_pool_client.web.access_token_validity == 60,
      aws_cognito_user_pool_client.mobile_tactical.access_token_validity == 60,
      aws_cognito_user_pool_client.mobile_occupants.access_token_validity == 60,
      aws_cognito_user_pool_client.web.token_validity_units[0].id_token == "minutes",
      aws_cognito_user_pool_client.mobile_tactical.token_validity_units[0].id_token == "minutes",
      aws_cognito_user_pool_client.mobile_occupants.token_validity_units[0].id_token == "minutes",
    ])
    error_message = "Un ID o access token dejo de durar 60 minutos. La sesion larga de D-38 la da el refresh token; el token que la API verifica tiene que seguir siendo corto para que una baja o un cambio de rol surtan efecto en una hora."
  }
}
