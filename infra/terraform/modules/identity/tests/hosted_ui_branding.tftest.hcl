# [T-6.08 · hueco `U-19`] LA PANTALLA DONDE SE TECLEA LA CONTRASENA.
#
# El operador salta de una consola con imagotipo TAKAB al gris de fabrica de
# AWS, en ingles, y vuelve a otra pantalla TAKAB. Esta suite defiende las tres
# mitades del arreglo, y cualquiera de ellas sola es letra muerta:
#
#   1. que la hoja y el logo SE SUBAN (un pool nuevo sin personalizacion se
#      queda en gris y ningun plan se pone rojo);
#   2. que la hoja sea SALIDA DE UN GENERADOR y no doce hexes escritos a mano
#      —Cognito no acepta custom properties, asi que los literales son
#      inevitables; lo que no es inevitable es que diverjan de `tokens.json`—;
#   3. que no cite una clase que Cognito no conoce, porque `SetUICustomization`
#      rechaza la hoja ENTERA y eso se descubriria en la ventana de AWS de otra
#      persona.
#
# LA LISTA DE CLASES ESTA MEDIDA, no copiada de la documentacion: sale de la
# hoja que Cognito sirve en el propio Hosted UI de estos dos pools
# (`.../css/cognito-login.css`, leida el 2026-09-09). Son QUINCE — y dos de
# ellas (`passwordCheck-*`) se pierden con un barrido ingenuo por el guion de en
# medio, que es justo lo que paso la primera vez.
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

run "el_login_se_ve_takab_y_la_hoja_se_deriva_de_los_tokens" {
  command = plan

  # --- 1. TODO pool viste su login -------------------------------------------
  #
  # Mismo truco de censo que `mfa.tftest.hcl`: Terraform no itera tipos de
  # recurso, asi que lo que impide que un pool nuevo se quede en gris es contar
  # personalizaciones contra pools.
  assert {
    condition = length(flatten(regexall(
      "resource \"aws_cognito_user_pool_ui_customization\" \"([a-z0-9_]+)\"",
      file("${path.module}/main.tf")
      ))) == length(flatten(regexall(
      "resource \"aws_cognito_user_pool\" \"([a-z0-9_]+)\"",
      file("${path.module}/main.tf")
    )))
    error_message = "Hay un pool sin `aws_cognito_user_pool_ui_customization`. Su login se queda en el gris de fabrica de AWS y ni el plan ni el validate dicen nada."
  }

  # --- 2. Y TODO dominio declara que experiencia sirve ------------------------
  #
  # `managed_login_version` sin declarar lo decide el default de AWS. Si algun
  # dia vale 2 (`managed login`), `SetUICustomization` se ignora ENTERA y el
  # login vuelve al gris en silencio: la hoja seguiria en el repo, subida y sin
  # efecto. Se declara para que un cambio sea un cambio y no una deriva.
  assert {
    condition = length(flatten(regexall(
      "(?m)^  managed_login_version += 1$",
      file("${path.module}/main.tf")
      ))) == length(flatten(regexall(
      "resource \"aws_cognito_user_pool_domain\" \"([a-z0-9_]+)\"",
      file("${path.module}/main.tf")
    )))
    error_message = "Hay un dominio sin `managed_login_version = 1`. Con la version 2 (managed login) esta hoja no se aplica y nadie se entera: la pantalla vuelve al gris de AWS."
  }

  # --- 3. La hoja NO se escribe a mano: se deriva de tokens.json --------------
  #
  # Se cruzan los literales uno a uno contra el paquete de tokens. Un hex tecleado
  # aqui pasaria fmt, validate y plan, y solo se veria en la pantalla del cliente.
  assert {
    condition = alltrue([
      for token in [
        "--tk-surface-0", "--tk-surface-1", "--tk-fg-1", "--tk-fg-2", "--tk-fg-3",
        "--tk-cyan", "--tk-navy-900", "--tk-status-critical", "--tk-status-critical-text",
        "--tk-border-strong", "--tk-status-normal",
      ] :
      strcontains(
        file("${path.module}/cognito-hosted-ui.generated.css"),
        jsondecode(file("${path.module}/../../../../shared/design-tokens/tokens.json"))[token]
      )
    ])
    error_message = "La hoja del Hosted UI dejo de contener algun valor de `tokens.json`. Es SALIDA de `shared/design-tokens/scripts/gen-cognito-css.mjs`: regenerala con `npm run gen:cognito` (o `make drift`, que lo comprueba), no la edites."
  }

  # --- 4. Ni un color que no venga del paquete -------------------------------
  #
  # La otra direccion del cruce, que es la que caza el hex nuevo: todo `#rrggbb`
  # de la hoja tiene que existir en `tokens.json`. Sin esto, el censo de arriba
  # seguiria verde con un color propio anadido al lado de los derivados.
  assert {
    condition = alltrue([
      for color in distinct(flatten(regexall("(#[0-9A-Fa-f]{6})", file("${path.module}/cognito-hosted-ui.generated.css")))) :
      contains(values(jsondecode(file("${path.module}/../../../../shared/design-tokens/tokens.json"))), color)
    ])
    error_message = "La hoja del Hosted UI trae un color que NO esta en `tokens.json`. El login quedaria fuera del design system y cambiar la marca no lo movería."
  }

  # --- 5. Ninguna clase que Cognito no conozca -------------------------------
  #
  # `SetUICustomization` rechaza la hoja entera si cita una clase fuera de su
  # lista, y el rechazo llega en el `apply`. Las trece salen de la hoja que
  # Cognito sirve, no de un documento.
  assert {
    condition = alltrue([
      for clase in distinct(flatten(regexall("(?m)^\\.([A-Za-z][A-Za-z0-9-]*-customizable)", file("${path.module}/cognito-hosted-ui.generated.css")))) :
      contains([
        "background-customizable", "banner-customizable", "errorMessage-customizable",
        "idpButton-customizable", "idpDescription-customizable", "inputField-customizable",
        "label-customizable", "legalText-customizable", "logo-customizable",
        "passwordCheck-notValid-customizable", "passwordCheck-valid-customizable",
        "redirect-customizable", "socialButton-customizable", "submitButton-customizable",
        "textDescription-customizable",
      ], clase)
    ])
    error_message = "La hoja cita una clase que el Hosted UI clasico no define. Cognito rechaza la personalizacion ENTERA (no la regla): el login se quedaria en gris y el error llega en el apply."
  }

  # --- 6. El logo entra por el limite de la API ------------------------------
  #
  # 100 KB es tope duro de `SetUICustomization`. El fichero lo deriva
  # `shared/brand/generar.py`; lo que se vigila aqui es que siga cabiendo.
  assert {
    condition     = length(filebase64("${path.module}/logo-cognito.png")) < 100 * 1024
    error_message = "`logo-cognito.png` paso de 100 KB: `SetUICustomization` lo rechaza. Bajale el ancho en `shared/brand/generar.py`."
  }

  # --- 7. Y es el imagotipo derivado, no un PNG suelto -----------------------
  assert {
    condition     = strcontains(file("${path.module}/../../../../shared/brand/generar.py"), "identity/logo-cognito.png")
    error_message = "`logo-cognito.png` dejo de derivarse de `shared/brand/generar.py`. Un PNG suelto es el que se queda con el logotipo viejo el dia que la marca cambie."
  }
}
