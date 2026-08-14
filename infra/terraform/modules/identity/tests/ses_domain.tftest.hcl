# [T-2.78.b] La identidad de DOMINIO de SES, y las dos formas de romperla en silencio.
#
# Hasta hoy el UNICO recurso SES de toda la infraestructura era
# `aws_sesv2_email_identity` POR DIRECCION. Un `grep -rn "dkim|configuration_set|
# mail_from" infra/terraform/` devolvia cero, o sea que DKIM, SPF, el MAIL FROM
# propio y el destino de los rebotes solo podian existir a base de clics en la
# consola — y lo que se hace a clics no se vuelve a hacer igual ni se revisa en un
# diff.
#
# Este archivo blinda las dos cosas que pueden salir mal, y NINGUNA de las dos se
# nota mirando un plan:
#
#   1. QUE EL CODIGO NUEVO CAMBIE EL APPLY DE HOY. Todo cuelga de `var.ses_domain`,
#      vacia por defecto (patron del modulo `push/`: sin credenciales no se crea
#      nada). El primer bloque lo mide en vez de prometerlo.
#   2. QUE EL WORKER SE QUEDE CON AccessDenied. Una identidad VERIFICADA no
#      concede envio: son dos cosas distintas. La lista `notify_ses_identity_arns`
#      se construia iterando `ses_verified_emails`, asi que mover el remitente al
#      dominio sin tocar esa lista deja al worker `notify` sin permiso — y los
#      correos de CloudWatch (SNS, permiso propio) siguen llegando y tapan el
#      hueco. Es el fallo del 2026-07-14, calcado.
#
#      El arreglo NO es "acordarse de anadir el ARN": es que UNA sola variable
#      gobierne las dos mitades. `var.ses_domain` entra a `module.identity` (crea
#      la identidad) y a `module.database` (concede el envio). El tercer bloque
#      comprueba ese cableado leyendo el propio `envs/dev/main.tf`, porque es el
#      unico sitio donde el error puede cometerse.
#
#      Y por que el ARN NO se toma del output de `module.identity`: identity ->
#      serve -> database ya es una cadena; leerlo cerraria el ciclo. Misma razon
#      que ya esta escrita sobre esa lista en `envs/dev/main.tf`.
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
  account_id          = "000000000000"
  ses_verified_emails = ["soc@example.test"]
}

# --- 1. Sin dominio, el apply de hoy no cambia ni un recurso -------------------
#
# El criterio de la ficha es literal: "vacia ⇒ no se crea nada y el `apply` de hoy
# no cambia". Se mide con `length(...) == 0` sobre CADA recurso condicional, no
# leyendo el `count` en el codigo: lo que importa es lo que produce el plan.
run "sin_dominio_no_se_crea_ni_un_solo_recurso_de_ses_de_dominio" {
  command = plan

  # Los defaults del modulo: `ses_domain` vacia. No se declara aqui a proposito —
  # si alguien le pusiera un default no vacio, este bloque se caeria entero, que
  # es exactamente lo que tiene que pasar.

  assert {
    condition = (
      length(aws_sesv2_email_identity.domain) == 0
      && length(aws_sesv2_email_identity_mail_from_attributes.domain) == 0
      && length(aws_sesv2_configuration_set.ses) == 0
      && length(aws_sesv2_configuration_set_event_destination.ses_feedback) == 0
    )
    error_message = "Con `ses_domain` vacia, el modulo NO puede crear ninguna identidad de dominio, MAIL FROM ni configuration set. Si esto se cae, el proximo `terraform apply` en la cuenta real —que hoy no toca SES— empezaria a tocarlo, y esta ficha se escribio precisamente para poder aterrizar el codigo ANTES de tener el dominio."
  }

  assert {
    condition = (
      length(aws_sns_topic.ses_feedback) == 0
      && length(aws_sns_topic_policy.ses_feedback) == 0
      && length(aws_sns_topic_subscription.ses_feedback) == 0
    )
    error_message = "El topic de rebotes/quejas tampoco puede existir sin dominio. Un topic vacio al que nadie publica no es 'tener un proceso': la solicitud de acceso a produccion de SES exige declarar que existe, y declararlo sin tenerlo es firmar algo falso."
  }

  assert {
    condition = (
      length(aws_route53_record.ses_dkim) == 0
      && length(aws_route53_record.ses_mail_from_mx) == 0
      && length(aws_route53_record.ses_mail_from_spf) == 0
      && length(aws_route53_record.ses_dmarc) == 0
    )
    error_message = "Sin dominio no puede haber registros DNS. Y ojo: tampoco los hay con dominio pero sin `ses_route53_zone_id` — el DNS de este dominio puede no vivir en Route 53, y en ese caso los valores salen por output para publicarlos donde toque."
  }

  # El CENSO, mismo truco que la asercion 1 de `mfa.tftest.hcl`: Terraform no sabe
  # iterar "todos los recursos de tipo X", asi que las tres aserciones de arriba
  # nombran los recursos uno a uno. Esto es lo que impide que un recurso NUEVO de
  # la familia SES/DNS entre sin ninguna de ellas — o sea, sin que nadie compruebe
  # que respeta la variable vacia.
  assert {
    condition = toset(flatten(regexall(
      "(?m)^resource \"(?:aws_sesv2_[a-z_]+|aws_route53_record|aws_sns_topic[a-z_]*)\" \"([a-z0-9_]+)\"",
      file("${path.module}/main.tf")
      ))) == toset([
      "this", "domain", "ses", "ses_feedback",
      "ses_dkim", "ses_mail_from_mx", "ses_mail_from_spf", "ses_dmarc",
    ])
    error_message = "Cambio el censo de recursos SES/DNS/SNS del modulo. Las aserciones de 'con la variable vacia no se crea nada' los nombran uno a uno: un recurso nuevo entraria SIN comprobar que respeta `ses_domain` vacia, y el primer apply de la cuenta real crearia infraestructura que nadie pidio. Declaralo aqui y dale su asercion."
  }
}

# --- 2. Con dominio: DKIM, MAIL FROM y el destino de los rebotes ---------------
run "con_dominio_la_identidad_trae_dkim_mail_from_y_los_rebotes_con_destino" {
  command = plan

  variables {
    ses_domain              = "ejemplo.test"
    ses_mail_from_subdomain = "correo"
    ses_feedback_email      = "rebotes@example.test"
    ses_dmarc_rua           = "dmarc@example.test"
  }

  override_resource {
    target          = aws_sns_topic.ses_feedback[0]
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ses-feedback"
    }
  }

  # Easy DKIM (no BYODKIM): AWS genera y ROTA las llaves. Se pide RSA_2048 de
  # forma explicita porque el default de la cuenta puede ser 1024 y una llave de
  # 1024 bits ya la rechazan validadores DMARC estrictos. `domain_signing_private_key`
  # vacio es lo que distingue Easy DKIM de "traete tu llave" — y traer una llave
  # significaria que la clave privada de firma del correo vive en un tfvars.
  assert {
    condition = (
      aws_sesv2_email_identity.domain[0].email_identity == "ejemplo.test"
      && aws_sesv2_email_identity.domain[0].dkim_signing_attributes[0].next_signing_key_length == "RSA_2048_BIT"
      && try(aws_sesv2_email_identity.domain[0].dkim_signing_attributes[0].domain_signing_private_key, null) == null
    )
    error_message = "La identidad de dominio debe usar Easy DKIM con llave RSA_2048. Con `domain_signing_private_key` puesto seria BYODKIM: la llave privada con la que se firma TODO el correo saliente pasaria a vivir en un tfvars, y rotarla dejaria de ser cosa de AWS."
  }

  # MAIL FROM propio: es lo que alinea SPF con el dominio del remitente. Sin el,
  # el Return-Path es `amazonses.com` y SPF alinea con AWS, no con nosotros.
  assert {
    condition = (
      aws_sesv2_email_identity_mail_from_attributes.domain[0].mail_from_domain == "correo.ejemplo.test"
      && aws_sesv2_email_identity_mail_from_attributes.domain[0].behavior_on_mx_failure == "REJECT_MESSAGE"
    )
    error_message = "El MAIL FROM debe ser un subdominio PROPIO y fallar en REJECT_MESSAGE. `USE_DEFAULT_VALUE` es la opcion tentadora y es la peligrosa: si el MX no resuelve, SES sigue enviando con el Return-Path de amazonses.com, la alineacion SPF se pierde y el correo del inspector acaba en spam sin que nada falle. REJECT_MESSAGE convierte esa averia de DNS en un error que el worker VE y registra (T-2.75: el canal que no entrega no finge)."
  }

  # El destino de rebotes y quejas. Un event destination sobre el configuration
  # set, y el configuration set aplicado POR DEFECTO a la identidad: si no se
  # asocia, el correo sale sin pasar por el y los eventos no se publican en ningun
  # sitio (verde en el plan, cero eventos en el topic).
  assert {
    condition = (
      aws_sesv2_email_identity.domain[0].configuration_set_name == aws_sesv2_configuration_set.ses[0].configuration_set_name
      && contains(aws_sesv2_configuration_set_event_destination.ses_feedback[0].event_destination[0].matching_event_types, "BOUNCE")
      && contains(aws_sesv2_configuration_set_event_destination.ses_feedback[0].event_destination[0].matching_event_types, "COMPLAINT")
      && contains(aws_sesv2_configuration_set_event_destination.ses_feedback[0].event_destination[0].matching_event_types, "REJECT")
      && aws_sesv2_configuration_set_event_destination.ses_feedback[0].event_destination[0].enabled
    )
    error_message = "Los rebotes y las quejas tienen que tener DESTINO, y el configuration set tiene que estar asociado a la identidad. Sin la asociacion el correo sale igual y los eventos no se publican en ninguna parte: el plan queda verde y el topic vacio para siempre. La solicitud de acceso a produccion de SES exige declarar que existe un proceso para tratarlos; esto es ese proceso."
  }

  # Y que ese destino tenga un HUMANO detras. Un topic sin suscripcion es un
  # sumidero con cara de proceso.
  assert {
    condition = (
      aws_sns_topic_subscription.ses_feedback[0].protocol == "email"
      && aws_sns_topic_subscription.ses_feedback[0].endpoint == "rebotes@example.test"
    )
    error_message = "El topic de rebotes debe tener una suscripcion de correo a `ses_feedback_email`. Un topic sin suscriptor recoge los eventos y no se los cuenta a nadie: es un sumidero con cara de proceso."
  }

  # SES no puede publicar en el topic solo porque el ARN este escrito en el event
  # destination: hace falta una politica de recurso. Sin ella el destino falla en
  # tiempo de ENTREGA (no de apply), que es cuando ya nadie esta mirando.
  assert {
    condition = length([
      for s in jsondecode(aws_sns_topic_policy.ses_feedback[0].policy).Statement : s
      if try(s.Principal.Service, "") == "ses.amazonaws.com"
      && try(s.Action, "") == "SNS:Publish"
      && try(s.Condition.StringEquals["AWS:SourceAccount"], "") == "000000000000"
    ]) == 1
    error_message = "El topic de rebotes necesita una politica de RECURSO que deje publicar a `ses.amazonaws.com`, acotada por `AWS:SourceAccount`. Sin ella el event destination se crea sin error y falla al ENTREGAR el primer rebote — un fallo en tiempo de ejecucion sobre un camino que nadie mira hasta que hace falta."
  }

  # Sin zona de Route 53 no se toca DNS aunque HAYA dominio. El DNS de un dominio
  # comprado en cualquier registrador no tiene por que vivir en Route 53, y
  # `aws_route53_record` contra una zona ajena no es un error de plan: es un apply
  # que falla a mitad, con la identidad ya creada.
  assert {
    condition = (
      length(aws_route53_record.ses_dkim) == 0
      && length(aws_route53_record.ses_dmarc) == 0
    )
    error_message = "Con dominio pero SIN `ses_route53_zone_id` no se puede crear ningun registro DNS: la zona del dominio puede no estar en esta cuenta. Los valores salen por output para publicarlos donde vivan."
  }
}

# --- 3. Con zona: los tres CNAME de DKIM, el MX, el SPF y el DMARC -------------
run "con_zona_los_registros_de_dns_se_crean_y_ninguno_esta_horneado" {
  command = plan

  variables {
    ses_domain              = "ejemplo.test"
    ses_mail_from_subdomain = "correo"
    ses_feedback_email      = "rebotes@example.test"
    ses_dmarc_rua           = "dmarc@example.test"
    ses_dmarc_policy        = "quarantine"
    ses_route53_zone_id     = "Z0000000000000TEST"
  }

  override_resource {
    target          = aws_sns_topic.ses_feedback[0]
    override_during = plan
    values = {
      arn = "arn:aws:sns:us-east-2:000000000000:takab-test-ses-feedback"
    }
  }

  # Easy DKIM son TRES CNAME, ni uno menos: con dos publicados la verificacion no
  # termina nunca y la identidad se queda en `PENDING` sin que nada falle.
  assert {
    condition     = length(aws_route53_record.ses_dkim) == 3
    error_message = "Easy DKIM publica TRES CNAME. Con menos, la verificacion del dominio se queda en PENDING para siempre y ningun plan lo dice."
  }

  assert {
    condition = (
      aws_route53_record.ses_mail_from_mx[0].type == "MX"
      && aws_route53_record.ses_mail_from_mx[0].name == "correo.ejemplo.test"
      && aws_route53_record.ses_mail_from_spf[0].type == "TXT"
      && contains(aws_route53_record.ses_mail_from_spf[0].records, "v=spf1 include:amazonses.com ~all")
    )
    error_message = "El subdominio MAIL FROM necesita SU MX (para los rebotes) y SU registro SPF. Falta cualquiera de los dos y `behavior_on_mx_failure = REJECT_MESSAGE` deja de enviar correo: es el precio, consciente, de no fingir alineacion."
  }

  assert {
    condition = (
      aws_route53_record.ses_dmarc[0].name == "_dmarc.ejemplo.test"
      && aws_route53_record.ses_dmarc[0].type == "TXT"
      && contains(aws_route53_record.ses_dmarc[0].records, "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.test")
    )
    error_message = "El registro DMARC debe publicarse en `_dmarc.<dominio>` y su politica debe salir de `ses_dmarc_policy`. Cableada, subir de `none` a `quarantine` dejaria de ser una decision revisable en un diff."
  }

  # EL CRITERIO 4 DE LA FICHA, medido: los valores literales NO se hornean.
  #
  # Los tokens de DKIM los genera AWS por identidad y no existen hasta el apply;
  # el host del MX depende de la REGION. Cualquiera de los dos escrito a mano en
  # el repo es un valor que caduca en silencio: apunta al sitio equivocado, la
  # verificacion no termina y el plan sigue verde. Se comprueba sobre el TEXTO del
  # modulo porque los valores de verdad son `known after apply` y una asercion
  # sobre ellos seria inevaluable.
  assert {
    condition = (
      length(regexall("[0-9a-z]{32}\\._domainkey", file("${path.module}/main.tf"))) == 0
      && length(regexall("[0-9a-z]{32}\\._domainkey", file("${path.module}/outputs.tf"))) == 0
      && length(regexall("feedback-smtp\\.[a-z]{2}-[a-z]+-[0-9]", file("${path.module}/main.tf"))) == 0
    )
    error_message = "Hay un valor de DNS HORNEADO en el modulo: o un token de DKIM literal, o el host del MX con una region escrita a mano. Los tokens los genera AWS por identidad (no existen hasta el apply) y el host del MX cambia con la region: un literal apunta al sitio equivocado, la verificacion no termina nunca y ningun plan se pone rojo."
  }

  assert {
    condition     = length(regexall("dkim_signing_attributes\\[0\\]\\.tokens", file("${path.module}/main.tf"))) > 0
    error_message = "Los CNAME de DKIM deben salir de `dkim_signing_attributes[0].tokens`, que es la respuesta de la API. Si dejan de derivarse de ahi, salen de algun sitio que no es AWS."
  }
}

# --- 4. El hueco que MUERDE: el worker sin permiso de envio --------------------
#
# Este bloque no mira el modulo: mira el CABLEADO del entorno, que es el unico
# sitio donde este error se puede cometer. `notify_ses_identity_arns` se construye
# en `envs/dev/main.tf` iterando `ses_verified_emails`; si el dominio no entra
# ahi, el worker `notify` recibe AccessDenied al primer envio y —como los correos
# de CloudWatch los manda SNS, con permiso propio— nadie nota el hueco.
#
# La forma de cerrarlo NO es "acordarse": es que UNA sola variable alimente las
# dos mitades. Por eso lo que se comprueba es que `var.ses_domain` llegue a los
# DOS modulos.
run "el_dominio_llega_a_la_identidad_Y_al_permiso_de_envio_del_worker" {
  command = plan

  assert {
    condition     = length(regexall("(?m)^  ses_domain\\s*=\\s*var\\.ses_domain\\s*$", file("${path.module}/../../envs/dev/main.tf"))) == 1
    error_message = "`envs/dev/main.tf` dejo de pasar `var.ses_domain` a `module.identity`: la identidad de dominio no se crearia aunque la variable estuviera puesta."
  }

  assert {
    condition     = length(regexall("(?m)^  notify_ses_domain\\s*=\\s*var\\.ses_domain\\s*$", file("${path.module}/../../envs/dev/main.tf"))) == 1
    error_message = "`envs/dev/main.tf` dejo de pasar `var.ses_domain` a `module.database`. Ese es EL fallo de esta ficha: la identidad de dominio existiria y estaria verificada, y el worker `notify` recibiria AccessDenied en cada envio mientras los correos de CloudWatch (SNS, permiso propio) siguen llegando y tapan el hueco. Calcado al 2026-07-14. Una identidad VERIFICADA no concede envio: son dos cosas distintas y las gobierna la MISMA variable a proposito."
  }
}

# --- 5. No se puede declarar el dominio sin un buzon donde caigan las quejas ---
#
# La solicitud de acceso a produccion de SES exige declarar que existe un proceso
# para tratar rebotes y quejas. Se hace IMPOSIBLE declarar el dominio sin el, en
# vez de confiar en que alguien se acuerde: la validacion cruzada es la unica
# forma de que "el proceso existe" no sea una casilla marcada a mano.
run "un_dominio_sin_buzon_de_quejas_no_se_puede_aplicar" {
  command = plan

  variables {
    ses_domain         = "ejemplo.test"
    ses_feedback_email = ""
  }

  expect_failures = [var.ses_feedback_email]
}

run "una_politica_dmarc_inventada_no_se_puede_aplicar" {
  command = plan

  variables {
    ses_domain         = "ejemplo.test"
    ses_feedback_email = "rebotes@example.test"
    ses_dmarc_policy   = "bloquear"
  }

  expect_failures = [var.ses_dmarc_policy]
}
