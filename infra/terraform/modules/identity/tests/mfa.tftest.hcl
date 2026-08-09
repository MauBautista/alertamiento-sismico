# [T-2.84.b · hueco `RO-8.c`] El segundo factor de la superficie que abre valvulas.
#
# `identity` era el UNICO de los modulos de Terraform con pruebas que no las tenia, y
# eso importaba mas aqui que en ningun otro: la regla de oro 8 exige MFA "sin
# excepcion" sobre el camino que cierra el gas y mueve los ascensores, y la API
# NO PUEDE COMPROBARLO EN EL TOKEN. Verificado contra la documentacion de AWS, no
# de memoria:
#
#   - el payload por defecto del ID token de Cognito —el que la API verifica— no
#     lleva `amr` ni `acr` (Developer Guide, "Understanding the identity (ID) token");
#     el access token tampoco ("Understanding the access token");
#   - y en la tabla "Claims and scopes reference" del disparador pre-token-generation,
#     `acr` y `amr` figuran como `Can add? No · Can modify? No · Can suppress? No`:
#     son reservados de Cognito, asi que tampoco se pueden fabricar.
#
# Conclusion: el unico sitio donde el MFA de esta plataforma esta declarado es ESTE
# ARCHIVO DE TERRAFORM. `api/src/takab_api/auth/mfa.py` exige que el token venga de
# un pool con la politica puesta; lo que garantiza que la politica siga puesta es lo
# que hay aqui abajo. Sin estas aserciones, una deriva a `OPTIONAL` —o encender los
# dispositivos recordados, que AWS documenta como un bypass legitimo del reto de
# MFA— no la habria visto nadie.
#
# Corre con: terraform -chdir=infra/terraform/modules/identity test
#
# PENDIENTE DE INTEGRACION (T-2.84.b no pudo tocar esos ficheros): este modulo hay
# que anadirlo al `Makefile` (junto a observability/database/storage) y a
# `.github/workflows/ci.yml` (job `infra · terraform fmt + validate + test`). Hasta
# entonces estas aserciones NO bloquean un merge y la matriz de trazabilidad no
# debe acreditarlas como cobertura: seria justo el falso verde de T-2.63.

provider "aws" {
  region                      = "us-east-2"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

variables {
  account_id          = "000000000000"
  ses_verified_emails = []
}

run "el_segundo_factor_del_pool_no_puede_derivar_en_silencio" {
  command = plan

  # --- 1. EL CENSO: cuantos pools hay, y que ninguno se cuele por fuera --------
  #
  # Terraform no sabe iterar sobre "todos los recursos de tipo X", asi que las
  # aserciones de politica de abajo nombran los pools uno a uno. Esto es lo que
  # impide que un pool NUEVO se quede sin ninguna de ellas: leer el `main.tf` y
  # exigir que el censo siga siendo el declarado. Mismo truco que
  # `modules/storage/tests/lifecycle.tftest.hcl` con los buckets.
  #
  # El patron no cruza con `aws_cognito_user_pool_client` ni `..._domain` porque
  # exige la comilla de cierre justo detras de `user_pool`.
  assert {
    condition = toset(flatten(regexall(
      "resource \"aws_cognito_user_pool\" \"([a-z0-9_]+)\"",
      file("${path.module}/main.tf")
    ))) == toset(["this", "occupants"])
    error_message = "Cambio el censo de pools del modulo. Las aserciones de politica de MFA nombran los pools uno a uno (Terraform no itera tipos de recurso): un pool nuevo entraria SIN ninguna comprobacion, y con el la delegacion entera del MFA al pool. Declaralo aqui y dale su asercion, o esta suite acredita menos de lo que dice."
  }

  # --- 2. TODO pool DECLARA su politica de MFA --------------------------------
  #
  # La ausencia del atributo no es neutra: `MfaConfiguration` por omision es `OFF`.
  # Un pool escrito sin la linea quedaria sin segundo factor y el plan seria verde.
  # Por eso se cuentan declaraciones contra pools, en vez de mirar solo las que hay.
  assert {
    condition = length(flatten(regexall(
      "(?m)^  mfa_configuration += \"([A-Z]+)\"",
      file("${path.module}/main.tf")
      ))) == length(flatten(regexall(
      "resource \"aws_cognito_user_pool\" \"([a-z0-9_]+)\"",
      file("${path.module}/main.tf")
    )))
    error_message = "Hay un pool sin `mfa_configuration` declarado. El valor por omision de Cognito es OFF: ese pool emitiria tokens sin segundo factor y ni el plan ni el validate dirian nada."
  }

  # --- 3. NINGUN pool en OFF, y una sola excepcion a ON -----------------------
  assert {
    condition = !contains(flatten(regexall(
      "(?m)^  mfa_configuration += \"([A-Z]+)\"",
      file("${path.module}/main.tf")
    )), "OFF")
    error_message = "Un pool de Cognito quedo en `mfa_configuration = OFF`. En OFF los usuarios ni siquiera pueden registrar un segundo factor: no es una relajacion, es apagarlo."
  }

  assert {
    condition = length([
      for v in flatten(regexall(
        "(?m)^  mfa_configuration += \"([A-Z]+)\"",
        file("${path.module}/main.tf")
      )) : v if v != "ON"
    ]) == 1
    error_message = "El numero de pools que NO exigen MFA dejo de ser uno. La unica excepcion declarada es el pool de ocupantes (asercion 5), y esta razonada: un civil puede declinar su TOTP. Cualquier otra hay que escribirla aqui con su razon antes de que exista."
  }

  # --- 4. El pool PRINCIPAL: MFA obligatoria y el factor es TOTP --------------
  #
  # Se lee del RECURSO, no del texto: es lo que comprueba que la politica llega de
  # verdad al provider. Y las dos mitades van juntas a proposito — con
  # `mfa_configuration = ON` y el TOTP apagado, Cognito exige el factor por SMS o
  # correo, que son los dos canales phishables (y el SMS, ademas, SIM-swappable).
  # "Exige MFA" sin decir cual no es una politica.
  assert {
    condition     = aws_cognito_user_pool.this.mfa_configuration == "ON"
    error_message = "El pool PRINCIPAL dejo de exigir MFA. Es el pool del que salen todos los roles que pueden comandar actuadores, y `api/src/takab_api/auth/mfa.py` da por bueno su token justo por esto: si aqui pone OPTIONAL, la API sigue aceptandolo y la regla de oro 8 se queda sin su unico control real."
  }

  assert {
    condition     = aws_cognito_user_pool.this.software_token_mfa_configuration[0].enabled
    error_message = "El TOTP dejo de estar habilitado en el pool principal. Con MFA obligatoria y TOTP apagado, el segundo factor pasa a ser SMS o correo: canales phishables, y el SMS ademas vulnerable a SIM-swap. El gate #7 ratifico solo-TOTP."
  }

  # --- 5. El pool de OCUPANTES: OPTIONAL, y ni ON ni OFF ----------------------
  #
  # Las dos direcciones importan y por eso se comprueba la igualdad, no ">= algo":
  # subirlo a ON dejaria a un civil sin poder pedir auxilio si declina el TOTP
  # (rompe el camino de vida), y bajarlo a OFF le quitaria la posibilidad de
  # activarlo desde la pantalla Cuenta. Es la decision #7, ratificada en T-2.02.
  assert {
    condition     = aws_cognito_user_pool.occupants.mfa_configuration == "OPTIONAL"
    error_message = "El pool de OCUPANTES dejo de estar en OPTIONAL. ON rompe el camino de vida (un civil que declina el TOTP no podria pedir auxilio); OFF le quita el opt-in desde la app. La excepcion al MFA de la regla de oro 8 vive aqui y esta acotada en `routers/commands.py::panic_vote`: quorum de 2 votantes distintos, geofence, rate-limit, y solo `siren/activate`."
  }

  assert {
    condition     = aws_cognito_user_pool.occupants.software_token_mfa_configuration[0].enabled
    error_message = "El TOTP opcional del pool de ocupantes esta apagado. Con `OPTIONAL` y sin ningun factor habilitado, el opt-in de la pantalla Cuenta no puede completarse: la opcion existe en la UI y no lleva a ninguna parte."
  }

  # --- 6. El ANCLA pool→rol, por el lado de Terraform -------------------------
  #
  # `auth/deps.py::get_claims` sostiene toda la delegacion sobre esto: el pool de
  # ocupantes SOLO emite `occupant`. Del lado de la API ya hay pruebas
  # (`tests/auth/test_dual_issuer.py`); del lado de la infraestructura, ninguna.
  # Si a este pool se le anadiera un grupo `brigadista`, la API lo rechazaria por
  # el ancla — pero el usuario existiria, y el dia que alguien "arregle" el 401
  # relajando el ancla, ese rol entraria desde un pool sin MFA obligatoria.
  assert {
    condition = toset(flatten(regexall(
      "resource \"aws_cognito_user_group\" \"([a-z0-9_]+)\"",
      file("${path.module}/main.tf")
    ))) == toset(["this", "occupants_occupant"])
    error_message = "Aparecio un recurso de grupo de Cognito fuera de los dos conocidos. El ancla pool→rol de la API (`auth/deps.py::get_claims`) da por hecho que el pool de ocupantes solo tiene el grupo `occupant`: un grupo nuevo ahi es un rol que podria entrar desde un pool con MFA OPTIONAL."
  }

  assert {
    condition     = aws_cognito_user_group.occupants_occupant.name == "occupant"
    error_message = "El unico grupo del pool de ocupantes dejo de llamarse `occupant`. Ese nombre es literal en `auth/deps.py::get_claims` y en `auth/mfa.py`: si cambia aqui y no alla, el ancla pool→rol deja de anclar nada."
  }

  # --- 7. Dispositivos recordados: NO -----------------------------------------
  #
  # El bypass de MFA mas facil de encender sin darse cuenta. Literal de AWS
  # ("Working with user devices in your user pool"): "After you configure a user's
  # device to be remembered, Amazon Cognito no longer requires them to submit an
  # MFA code when they sign in with the same device key". El comportamiento por
  # omision es no recordar, asi que hoy el modulo esta bien SIN ESCRIBIR NADA — y
  # por eso hace falta esta asercion: lo que protege es una ausencia, y las
  # ausencias no se revisan en un diff.
  assert {
    condition     = length(regexall("device_configuration", file("${path.module}/main.tf"))) == 0
    error_message = "Alguien declaro `device_configuration` en un pool. Un dispositivo recordado SUSTITUYE el reto de MFA por un reto de dispositivo: el token que salga de ahi sera indistinguible de uno con segundo factor, y `auth/mfa.py` lo dara por bueno. Si se enciende a proposito, hay que releer `auth/mfa.py` §4 y decidir que control lo compensa."
  }

  # --- 8. Ningun app client puede saltarse el reto ----------------------------
  #
  # El pool decide la politica, pero el CLIENTE decide por que flujo se entra. Se
  # comprueba el conjunto de flujos de TODO el archivo, asi que un client nuevo
  # entra solo en la comprobacion.
  #
  #   - `ALLOW_CUSTOM_AUTH` pone la cadena de retos en manos de los Lambda
  #     Define/Create/Verify Auth Challenge: a partir de ahi lo que se presente ya
  #     no lo gobierna `mfa_configuration`, sino codigo que no vive en este modulo;
  #   - `ALLOW_USER_PASSWORD_AUTH` / `ALLOW_ADMIN_USER_PASSWORD_AUTH` mandan la
  #     contrasena en claro al endpoint en vez de usar SRP. No saltan el reto de
  #     MFA, pero degradan el PRIMER factor de la superficie que comanda gas.
  assert {
    condition = length(setsubtract(
      toset(flatten(regexall("(ALLOW_[A-Z_]+)", file("${path.module}/main.tf")))),
      toset(["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"])
    )) == 0
    error_message = "Un app client habilito un flujo de autenticacion fuera de SRP + refresh. `ALLOW_CUSTOM_AUTH` traslada la cadena de retos a un Lambda y `mfa_configuration` deja de ser la ultima palabra; los flujos `*_PASSWORD_AUTH` mandan la contrasena en claro al endpoint. Cualquiera de los dos cambia la premisa sobre la que `auth/mfa.py` acepta un token."
  }

  # --- 9. Alta de usuarios ADMINISTRADA, en los dos pools ---------------------
  #
  # De poco sirve exigir MFA si cualquiera puede darse de alta. Se cuenta contra el
  # censo de pools por el mismo motivo que la asercion 2: la ausencia del bloque es
  # lo peligroso, no un `false` visible.
  assert {
    condition = length(flatten(regexall(
      "(?m)^    allow_admin_create_user_only += true",
      file("${path.module}/main.tf")
      ))) == length(flatten(regexall(
      "resource \"aws_cognito_user_pool\" \"([a-z0-9_]+)\"",
      file("${path.module}/main.tf")
    )))
    error_message = "Un pool dejo de tener el alta restringida a administradores (`allow_admin_create_user_only = true`). Con auto-registro, exigir MFA solo garantiza que el intruso tenga segundo factor: se apunta el solo, elige su TOTP y entra."
  }

  # --- 10. Politica de contrasenas: el PRIMER factor tambien es un factor -----
  #
  # 12 caracteres con mayuscula, minuscula y numero. Sin simbolos a proposito
  # (NIST SP 800-63B desaconseja las reglas de composicion agresivas frente a la
  # longitud), pero la LONGITUD no se toca.
  assert {
    condition = length([
      for v in flatten(regexall(
        "(?m)^    minimum_length += ([0-9]+)",
        file("${path.module}/main.tf")
      )) : v if tonumber(v) < 12
    ]) == 0
    error_message = "Un pool bajo la longitud minima de contrasena por debajo de 12. El MFA cubre el segundo factor; esto es el primero, y en esta plataforma el primer factor da acceso a la consola que comanda gabinetes."
  }

  assert {
    condition = length(flatten(regexall(
      "(?m)^    minimum_length += [0-9]+",
      file("${path.module}/main.tf")
      ))) == length(flatten(regexall(
      "resource \"aws_cognito_user_pool\" \"([a-z0-9_]+)\"",
      file("${path.module}/main.tf")
    )))
    error_message = "Hay un pool sin `password_policy.minimum_length`. El default de Cognito son 8 caracteres, y un default no es una decision."
  }

  # --- 11. `write_attributes` acotado en TODOS los clients --------------------
  #
  # Regla de oro 5, no MFA — pero entra aqui porque el unico test que lo cubria
  # (`api/tests/auth/test_cognito_write_attributes.py`) mira SOLO el client `web`, y
  # desde T-2.02 hay tres. Un `custom:` auto-escribible en el client movil valdria
  # tanto como uno en el de la consola: el usuario se reasigna el tenant y el MFA
  # que tan bien exigimos protege la cuenta equivocada.
  assert {
    condition = length(flatten(regexall(
      "(?m)^  write_attributes += \\[[^]]*\\]",
      file("${path.module}/main.tf")
      ))) == length(flatten(regexall(
      "resource \"aws_cognito_user_pool_client\" \"([a-z0-9_]+)\"",
      file("${path.module}/main.tf")
    )))
    error_message = "Hay un app client sin `write_attributes`. Sin esa lista el client permite escribir TODOS los atributos mutables via UpdateUserAttributes self-service, incluidos los `custom:` que anclan tenant y rol (regla de oro 5)."
  }

  assert {
    condition = length([
      for l in flatten(regexall(
        "(?m)^  write_attributes += \\[([^]]*)\\]",
        file("${path.module}/main.tf")
      )) : l if length(regexall("custom:", l)) > 0
    ]) == 0
    error_message = "Un app client dejo un atributo `custom:` en `write_attributes`. Los anclas de tenancy y rol los fija el admin (AdminUpdateUserAttributes, que no se rige por esta lista): si el usuario puede reescribirlos, se cambia de tenant solo."
  }

  # --- 12. Threat protection: apagado, y que encenderlo sea una DECISION ------
  #
  # AWS lo dice explicito en "Adding MFA to a user pool": "When you activate threat
  # protection and configure adaptive-authentication responses in full-function
  # mode, MFA must be optional in your user pool". O sea que encender la proteccion
  # avanzada en modo pleno OBLIGA a bajar el pool a OPTIONAL — el efecto contrario
  # al que espera quien la enciende pensando que endurece la seguridad. Se veta la
  # ausencia para que ese cambio no pueda entrar sin releer esta nota.
  assert {
    condition     = length(regexall("user_pool_add_ons", file("${path.module}/main.tf"))) == 0
    error_message = "Se declaro `user_pool_add_ons` (threat protection). Cuidado con el orden de causas: en modo full-function, la respuesta adaptativa EXIGE que el pool este en MFA OPTIONAL, asi que encender esto puede degradar el segundo factor del pool que comanda actuadores. Si se hace a proposito, la asercion 4 tiene que seguir en verde o hay que rehacer `auth/mfa.py`."
  }
}

# La politica no puede depender de que hoy nadie pase valores raros.
#
# El bloque de arriba corre con los defaults del modulo. Este mueve las variables
# que un despliegue real SI cambia (URLs de callback, correos SES) y exige que la
# postura de MFA no se mueva con ellas: es la diferencia entre "esta bien
# configurado" y "esta bien configurado por casualidad".
run "la_postura_de_MFA_no_depende_de_las_variables_del_despliegue" {
  command = plan

  variables {
    account_id           = "999999999999"
    ses_verified_emails  = ["soc@example.test"]
    extra_callback_urls  = ["https://consola.example.test/auth/callback"]
    extra_logout_urls    = ["https://consola.example.test/"]
    mobile_callback_urls = ["takab://auth/callback", "exp://127.0.0.1:8081/--/auth/callback"]
    mobile_logout_urls   = ["takab://auth/logout"]
  }

  assert {
    condition = (
      aws_cognito_user_pool.this.mfa_configuration == "ON"
      && aws_cognito_user_pool.occupants.mfa_configuration == "OPTIONAL"
      && aws_cognito_user_pool.this.software_token_mfa_configuration[0].enabled
    )
    error_message = "La politica de MFA cambio al mover variables de despliegue (URLs, correos). No deberia depender de ninguna: si algun dia se variabiliza, esta asercion es la que avisa de que el segundo factor paso a ser configurable desde un tfvars."
  }
}
