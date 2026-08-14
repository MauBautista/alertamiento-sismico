# RUNBOOK · SES fuera de sandbox + acreditación de la cadena on-call — T-2.78

> **Estado: PREPARADO, SIN EJECUTAR (2026-08-07).** Los tres criterios de `T-2.78` son
> `HUMANO-AWS`: exigen cuenta de AWS, un dominio y **una persona con teléfono**. Este runbook
> no los cumple; los deja ejecutables y con dónde anotar lo medido.
> **Criterio de cierre:** (1) SES en producción con DKIM/SPF de dominio real; (2) una alarma
> real provocada, con los **cuatro instantes** del §3.4 anotados en el registro §3.7 —
> incluido el del acuse humano; (3) la tabla de escalamiento del §4.2 rellena y firmada.
> Hasta entonces está acreditado que **el mensaje sale**, no que **la persona llega**.

Toda cita a documentación de AWS lleva su URL pegada al dato. **No añadas ninguna sin ella:**
en esta misma rama (T-2.7x, ventanas de mantenimiento) una cita inventada de AWS sostuvo una
decisión entera hasta que se cayó. Una razón escrita que no resiste comprobación cuesta lo
mismo que el código malo.

---

## 0. Cómo leer este runbook

- Cada paso dice **quién** lo corre. Todo lo de AWS lo corre Mauricio: en Claude Code, prefijo
  `!` (el clasificador niega `terraform apply`, IAM y SES en sesión asistida).
- **[PARA]** = detente y diagnostica. No sigas "a ver si jala".
- **[HUECO]** = falta una decisión de producto o un dato que nadie ha tomado todavía. Un
  `[HUECO]` sin resolver **bloquea** el criterio que lo contiene; no se rodea.
- Los registros de verificación (§2.6, §3.7, §4.2) se llenan **al ejecutar**. Vacíos, este
  runbook no acredita nada.
- Perfil y región de todo el documento: `AWS_PROFILE=takab-dev`, `--region us-east-2`
  (`api/src/takab_api/settings.py:41`, default `aws_region = "us-east-2"`).

---

## 1. Son DOS cadenas, y solo una se acredita aquí

Esto va primero porque es el error que ya se pagó en producción. **No comparten ni una línea
de código, ni un destinatario, ni un topic, ni una tabla.**

| | Cadena de **OPERACIÓN** (on-call) | Cadena de **INCIDENTE SÍSMICO** (tenant) |
|---|---|---|
| Qué la dispara | Alarmas CloudWatch | Un incidente / una acción de incidente |
| Dónde vive | **Cero código de la app** — 100 % Terraform (`infra/terraform/modules/observability/main.tf`) | `api/src/takab_api/notify/orchestrator.py`, worker `python -m takab_api.notify` |
| Transporte | **SNS** → topic `takab-dev-ops-alerts` (`main.tf:23`) → suscripción email (`main.tf:29-33`) | **SES** (email, `notify/providers.py:88`), **Twilio** (SMS), **SNS platform endpoints** (push), **httpx+HMAC** (webhook) |
| A quién avisa | UN buzón: `var.ops_alert_email` (`envs/dev/variables.tf:56`), global, sin tenant | Destinos del tenant resueltos de `rule_sets.config` + `push_tokens` por sitio |
| Evidencia en la DB | **Ninguna** | `notification_jobs` + `incident_actions` (`notify_sent` / `notify_simulated` / `notify_failed`) |
| Permiso AWS | El propio de SNS (viene con el topic) | `ses:SendEmail` explícito (`modules/database/main.tf:235-240`) |

**La lección, ya pagada (2026-07-14, citada en `envs/dev/main.tf:75-78`):** un dictamen no
llegó al inspector porque faltaba el grant `ses:SendEmail`, y **el hueco estuvo tapado semanas
porque los correos de CloudWatch sí llegaban** — los manda SNS, con permiso propio. Ver la
cadena de operación funcionando **no dice nada** de la cadena de incidentes, ni al revés.

**Este runbook acredita la cadena de OPERACIÓN** (§3). La cadena de incidentes se acredita con
`T-2.94` (simulacro con cascada real), que espera a esta tarea por eso mismo.

---

## 2. SES fuera de sandbox

### 2.1 Qué hay hoy (verificable sin AWS)

- **La cuenta está en sandbox.** Documentado como hallazgo M-3 en
  `takab-docs/runbooks/RUNBOOK-auditoria-cierre.md:599`.
- **Solo hay identidades de DIRECCIÓN, ninguna de dominio.** El único recurso SES de toda la
  infra es `aws_sesv2_email_identity` por dirección
  (`infra/terraform/modules/identity/main.tf:139-144`), alimentado por `var.ses_verified_emails`
  (`envs/dev/variables.tf:51`, default: el gmail del mantenedor). **No existe**
  `aws_ses_domain_identity`, ni DKIM, ni MAIL FROM, ni configuration set: grep de
  `dkim|configuration_set|mail_from` sobre `infra/terraform/` devuelve cero.
- **El remitente sale de un env var**, no de terraform: `TAKAB_API_NOTIFY_EMAIL_FROM`
  (`api/src/takab_api/settings.py:38` fija `env_prefix="TAKAB_API_"`; `:235`
  `notify_email_from: str = ""`). Vacío ⇒ el canal email cae a **simulado** y grita al arrancar
  (`api/src/takab_api/notify/providers.py:170-173`).
- **Lo que el sandbox impide**, literal de AWS: *"You can only send mail **to** verified email
  addresses and domains, or to the Amazon SES mailbox simulator. You can send a maximum of 200
  messages per 24-hour period. You can send a maximum of 1 message per second."*
  — https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html

### 2.2 [HUECO] · No hay dominio, y sin dominio no hay DKIM/SPF

El criterio dice "DKIM/SPF **de dominio real**". Hoy **TAKAB no tiene dominio propio en
ninguna parte del repo**: la consola se sirve sobre `sslip.io`, elegido explícitamente
*"sin Route53 ni dominio propio"* (`infra/terraform/modules/serve/outputs.tf:9`,
`deploy/cloud/README.md:13`). El host es `<ip-con-guiones>.sslip.io`, derivado de la IP
elástica.

Consecuencias, las tres duras:

1. **DKIM de dominio es imposible sobre `sslip.io`**: hay que publicar CNAME bajo el dominio, y
   `sslip.io` no es nuestro.
2. **La solicitud de producción pide `Website URL`** (§2.4). Contestar con un host `sslip.io`
   ligado a una IP es contestar "no tengo sitio": es la clase de solicitud que AWS devuelve
   pidiendo más información.
3. **El remitente actual es un gmail personal.** Un correo de alerta sísmica firmado por un
   gmail no es un canal de producto.

**Decisiones que hay que tomar ANTES de tocar la consola de SES** (esto es el `[HUECO]`; no lo
resuelve un runbook):

| # | Decisión | Valor elegido | Fecha / quién |
|---|---|---|---|
| D-1 | Dominio raíz de TAKAB (registrar o confirmar el que ya se tenga) |  |  |
| D-2 | ¿Route 53 como DNS, o el DNS del registrador? (Route 53 permite que SES publique los registros solo) |  |  |
| D-3 | Remitente de notificaciones (p. ej. `alertas@<dominio>`) |  |  |
| D-4 | Subdominio MAIL FROM (§2.3.b) — **no puede usarse para enviar ni recibir correo** |  |  |
| D-5 | Buzón para los informes agregados de DMARC (`rua=`) |  |  |
| D-6 | ¿Se migra también `ops_alert_email` al dominio, o el on-call sigue en gmail? (§4) |  |  |

Con D-1 en blanco, el resto de este §2 no se puede ejecutar. **[PARA] si alguien propone
"lo hacemos con la dirección verificada de siempre":** eso es lo que ya hay, y es sandbox.

### 2.3 Los registros DNS que hacen falta

Los tres bloques son independientes. **DKIM es obligatorio** (es como SES verifica el dominio);
**MAIL FROM/SPF es opcional para enviar pero obligatorio si se quiere alineación SPF**; DMARC
es la política que ata los dos.

**(a) DKIM — 3 registros CNAME.** Con Easy DKIM, SES *"automatically adds a 2048-bit DKIM key to
every email that you send from that identity"*
(https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-dkim-easy.html). La
verificación exige publicar **tres** CNAME: *"From the Publish DNS records table, copy the
three CNAME records that appear in this section to be published (added) to your DNS provider"*,
cuyo valor *"is composed of the DKIM token followed by a hosted zone domain (for example,
`{{token}}.dkim.amazonses.com` or `{{token}}.{{a31d}}.dkim.{{us-west-2}}.amazonses.com`)"*
— https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html

- **Los valores literales los da la consola** (o el CSV de `Download .csv record set`, o el
  campo `SigningHostedZone` de `GetEmailIdentity`). **Cópialos de ahí, no de este runbook ni de
  memoria**: la zona varía por región y por celda.
- Trampa documentada por AWS: *"Do not add any additional underscores (`_`) at the beginning of
  the CNAME record names… Correct: `abc123._domainkey.domain.com` / Incorrect:
  `_abc123._domainkey.domain.com`"* (misma URL).
- **Plazo:** *"It can take up to 72 hours for changes to DNS settings to propagate."* (misma URL).

**(b) MAIL FROM propio — 1 MX + 1 TXT.** Solo hace falta si se quiere **alineación SPF**: los
mensajes de SES usan por defecto un subdominio de `amazonses.com` como MAIL FROM, y *"SPF
authentication successfully validates these messages because the default MAIL FROM domain
matches the application that sent the email—in this case, SES. Therefore, in SES, SPF is
implicitly set up for you"*
(https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-spf.html). Con MAIL FROM
propio hay que publicar los dos registros, y AWS avisa: *"you must publish exactly one MX record
to the DNS server of your MAIL FROM domain. If the MAIL FROM domain has multiple MX records, the
custom MAIL FROM setup with Amazon SES will fail"*
(https://docs.aws.amazon.com/ses/latest/dg/mail-from.html). El MX lleva **preferencia 10**:
*"The number 10 listed along with the MX value is the preference order for the mail server"*
(misma URL). La forma de los valores —host `feedback-smtp.<región>.amazonses.com` y
`"v=spf1 include:amazonses.com ~all"`— aparece resuelta en los hilos oficiales de AWS re:Post
(https://repost.aws/questions/QUCFyRq18sQdCWmJHLK_z2kg/custom-mail-from-domain-setup-spf-record-not-recognized-despite-correct-dns-settings),
pero **la tabla autoritativa es la de la consola**: cópiala de ahí.
Requisitos del subdominio, literales: *"The MAIL FROM domain has to be a subdomain of the parent
domain of a verified identity… shouldn't be a subdomain that you also use to send email from…
shouldn't be a subdomain that you use to receive email"* (misma URL). Estado `Pending` → SES
busca el MX **72 h**; si no lo encuentra pasa a `Failed` y hay que reiniciar la configuración
(tabla "Custom MAIL FROM domain setup states", misma URL).

**(c) DMARC — 1 TXT.** *"The name of the TXT record you create should be `_dmarc.{{example.com}}`"*
y el ejemplo de AWS es
`"v=DMARC1;p=quarantine;rua=mailto:my_dmarc_report@example.com"`
(https://docs.aws.amazon.com/ses/latest/dg/send-email-authentication-dmarc.html). **Empieza en
`p=none`**, que es lo que AWS recomienda: *"Start with a simple monitoring-mode record… A
monitoring-mode record is a DMARC TXT record that has its policy set to none `p=none`"* (misma
URL). Subir a `quarantine` y luego a `reject` cuando los informes `rua` demuestren que el
tráfico legítimo está alineado. Comprobación de alineación sin herramientas externas, tal cual
la documenta AWS: `dig TXT _dmarc.<dominio>` y mirar `aspf=` / `adkim=` (misma URL).

**Por qué los tres y no solo DKIM:** *"A message passes DMARC if one or both of the described
SPF or DKIM checks pass. A message fails DMARC if both… fail"* (misma URL). Con solo DKIM se
pasa DMARC, pero un reenvío o un intermediario que toque el cuerpo tumba la firma y no queda
red de seguridad.

### 2.4 La solicitud de acceso a producción

Se puede pedir por consola o por CLI. **El texto de la solicitud es lo que decide**, no el
método.

```bash
# Opción CLI (la de la doc de AWS, literal). Correrla SOLO con D-1..D-3 decididos.
! AWS_PROFILE=takab-dev aws sesv2 put-account-details \
    --region us-east-2 \
    --production-access-enabled \
    --mail-type TRANSACTIONAL \
    --website-url "https://<DOMINIO-D1>" \
    --additional-contact-email-addresses "<CONTACTO>" \
    --contact-language EN
```
— https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html

Qué contestar y por qué:

- **`--mail-type TRANSACTIONAL`.** Definición de AWS: *"Transactional email - Sent on a
  one-to-one basis unique to each recipient usually triggered by a user action"*. Nuestro correo
  se dispara por un incidente sísmico o por una solicitud de dictamen, uno a uno. **No es
  marketing.**
- **`--website-url`**: el `[HUECO]` D-1. Sin dominio, aquí no hay respuesta honesta.
- **Reconocimiento obligatorio** (checkbox en consola, implícito en el CLI): *"check the box
  that you agree to only send email to individuals who've explicitly requested it and confirm
  that you have a process in place for handling bounce and complaint notifications"*. **Ese
  "process in place" hoy no existe**: no hay feedback topic de bounces/complaints en ninguna
  parte del repo. Ver la ficha `T-2.78.b`.
- **Verificar el dominio ANTES de pedirlo.** AWS lo declara buena práctica que acelera la
  aprobación: *"verifying your domain with SES before requesting production access is a best
  practice that helps to get your production access request approved faster"* (misma URL).
- **Plazo:** *"The AWS Support team provides an initial response to your request within 24
  hours."* Y el matiz que hay que planificar: *"if we need to obtain additional information from
  you, it might take longer to resolve your request."* (misma URL).
- **Es por región.** *"We place all new accounts in the Amazon SES sandbox. The sandbox status
  for your account is unique per each AWS Region."* Nosotros vivimos en `us-east-2`; salir del
  sandbox en otra región no sirve de nada. Además: *"To send email from the same domain or email
  address in more than one AWS Region, you must create and verify a separate identity for each
  Region."* (https://docs.aws.amazon.com/ses/latest/dg/creating-identities.html)
- **Una vez enviada no se puede editar**: *"Once you submit a review of your account details, you
  can't edit your details until the review is complete."* Escríbela bien a la primera.

### 2.5 [PARA] · Después de salir del sandbox, el permiso IAM se rompe solo

Este paso es el que muerde. `notify_ses_identity_arns` se construye **a mano**, iterando
`var.ses_verified_emails` (`infra/terraform/envs/dev/main.tf:79-82`), y de ahí sale el
statement `WorkerSesSend` con `Resource = var.notify_ses_identity_arns`
(`modules/database/main.tf:235-240`).

Si el remitente pasa de `<gmail>` a `alertas@<dominio>` y **solo** se cambia
`TAKAB_API_NOTIFY_EMAIL_FROM` en el despliegue:

- la identidad de dominio estará verificada (SES contento),
- pero el rol de la instancia **no tendrá permiso sobre ese ARN** ⇒ `AccessDenied` en cada
  envío, el job muere, y **los correos de CloudWatch seguirán llegando tan campantes** porque
  son SNS. Es exactamente el fallo del 2026-07-14, repetido.

Orden correcto: **(1)** identidad de dominio verificada → **(2)** el ARN de la identidad de
dominio dentro de `notify_ses_identity_arns` + `terraform apply` → **(3)** cambiar
`TAKAB_API_NOTIFY_EMAIL_FROM` → **(4)** provocar un envío real y verlo llegar.
El comentario que ya avisa de esto está en `envs/dev/main.tf:75-78`: **léelo antes de tocar
nada.**

### 2.6 Registro de verificación — SES (llenar al ejecutar; SIN marcar hasta entonces)

| # | Paso | Esperado | Medido | OK/NO | Fecha/inicial |
|---|---|---|---|---|---|
| S-1 | Dominio decidido (D-1) y DNS bajo control (D-2) | — |  |  |  |
| S-2 | Identidad de dominio creada en `us-east-2` | `Identity status: Verified` |  |  |  |
| S-3 | 3 CNAME de DKIM publicados | `DKIM configuration: Successful` |  |  |  |
| S-4 | Tiempo real hasta verificación DKIM | ≤ 72 h |  |  |  |
| S-5 | MAIL FROM propio: MX (pref. 10) + TXT SPF | estado `Success` |  |  |  |
| S-6 | DMARC `_dmarc.<dominio>` con `p=none` | `dig TXT` lo devuelve |  |  |  |
| S-7 | Solicitud de producción enviada | fecha/hora de envío |  |  |  |
| S-8 | Respuesta de AWS | ≤ 24 h (declarado) |  |  |  |
| S-9 | ARN de la identidad de dominio en `notify_ses_identity_arns` + apply (§2.5) | apply limpio |  |  |  |
| S-10 | `TAKAB_API_NOTIFY_EMAIL_FROM` = remitente del dominio | arranque **sin** «email simulado» |  |  |  |
| S-11 | Envío real a una dirección **no verificada** | llega a la bandeja |  |  |  |
| S-12 | Cabeceras del correo recibido | `dkim=pass`, `spf=pass`, `dmarc=pass` |  |  |  |

**S-11 es el que prueba el criterio**, no S-8: mientras el destino esté verificado, un envío
que llega no distingue sandbox de producción.

---

## 3. Acreditar la cadena on-call, cronometrado

### 3.1 Qué alarma provocar, y por qué esa

Las siete alarmas vivas están en `infra/terraform/modules/observability/main.tf`. Criterios de
elección: **(a)** no tocar el edificio ni el gabinete, **(b)** que nada la pueda silenciar a
mitad del ensayo, **(c)** que vuelva sola a `OK` para que el ensayo cierre el círculo.

| Alarma | ¿Sirve? | Por qué |
|---|---|---|
| `takab-dev-gateway-offline-<thing>` | **No** | Es **silenciable** por una ventana de mantenimiento abierta (`api/src/takab_api/ops/muting.py:221-229`, scope `GATEWAY`). Y un correo de "gabinete caído" que resulta ser un ensayo enseña a ignorar el que no lo sea. |
| `takab-dev-sensor-mudo-<thing>` | **No** | Silenciable igual (`muting.py:230-238`). Provocarla de verdad exige tocar el Shake. |
| `takab-dev-ec2-status-check` / `-cpu-sostenida` | **No** | Silenciables en ventana de plataforma (`muting.py:240-251`). Provocarlas de verdad tumba la nube. |
| `takab-dev-gateway-retirado-sigue-reportando` | **No para el ensayo** | Intocable (`muting.py:274-285`), pero tiene su propia verificación pendiente y **distinta**: ver §3.5. |
| `takab-dev-iot-rule-errors` | Sirve, 2.ª opción | Intocable (`muting.py:264-273`). Pero su métrica es un metric filter sobre logs: si la fuerzas y no hay eventos, la vuelta a `OK` depende de `notBreaching`, igual de fiable pero menos legible. |
| **`takab-dev-dlq-backfill`** | **SÍ — la elegida** | Intocable por diseño (`muting.py:253-263`: *"es el INSTRUMENTO del canary de T-2.70"*), o sea que **ninguna ventana abierta puede tragarse el ensayo**. `period = 300`, `evaluation_periods = 1`, `treat_missing_data = "notBreaching"` (`main.tf:47-51`) ⇒ vuelve sola a `OK` en un ciclo y dispara `ok_actions`: **dos correos, ida y vuelta**. Y `backfill` es la cola menos transitada de las tres (`modules/messaging/main.tf:12-17`). |

Las tres alarmas de DLQ son `takab-dev-dlq-{events,telemetry,backfill}`
(`main.tf:41` con `for_each = var.dlq_names`; claves en `modules/messaging/main.tf:13-16`).

### 3.2 Precondiciones (verificables antes de forzar nada)

```bash
# 1. La suscripción del on-call existe y está CONFIRMADA (no "PendingConfirmation").
! AWS_PROFILE=takab-dev aws sns list-subscriptions-by-topic --region us-east-2 \
    --topic-arn "$(AWS_PROFILE=takab-dev aws sns list-topics --region us-east-2 \
      --query "Topics[?contains(TopicArn,'takab-dev-ops-alerts')].TopicArn" --output text)" \
    --query 'Subscriptions[].{Proto:Protocol,End:Endpoint,Arn:SubscriptionArn}' --output table

# 2. La alarma existe y su estado de partida (anótalo: es el t0 de la transición).
! AWS_PROFILE=takab-dev aws cloudwatch describe-alarms --region us-east-2 \
    --alarm-names takab-dev-dlq-backfill \
    --query 'MetricAlarms[0].{Estado:StateValue,Desde:StateUpdatedTimestamp,Acciones:ActionsEnabled}'

# 3. NO hay ninguna ventana de mantenimiento abierta que pueda enturbiar la lectura.
#    (la elegida es intocable, pero si hay una abierta el ensayo se hace en un entorno mudo
#     a medias y las conclusiones se contaminan)
! AWS_PROFILE=takab-dev aws cloudwatch describe-alarms --region us-east-2 \
    --alarm-names takab-dev-dlq-backfill --query 'MetricAlarms[0].ActionsEnabled'
```

**[PARA] si la suscripción sale como `PendingConfirmation`.** Nadie ha confirmado el correo, o
se cayó. AWS: *"Amazon SNS deletes all other unconfirmed subscriptions after 48 hours."*
(https://docs.aws.amazon.com/sns/latest/dg/sns-email-notifications.html). Sin confirmar, la
cadena está rota desde el primer eslabón y el ensayo no mide nada.

**[PARA] si `ActionsEnabled` es `false`.** La alarma cambiará de estado y no llamará a nadie.

**No corras el ensayo durante un despliegue de flota.** La DLQ es el criterio medible del
rollback de `T-2.70`; forzarla mientras se despliega mete ruido en el detector.

### 3.3 El comando que provoca la alarma

```bash
# --- t0: la CONDICIÓN. Anota la hora ANTES de pulsar Enter. ---
date -u +%FT%TZ            # ← este es t0

! AWS_PROFILE=takab-dev aws cloudwatch set-alarm-state --region us-east-2 \
    --alarm-name takab-dev-dlq-backfill \
    --state-value ALARM \
    --state-reason "SIMULACRO T-2.78 <YYYY-MM-DD HH:MM> - acreditacion de la cadena on-call. NO es un incidente real. Responder a este correo o avisar por <CANAL> en cuanto se lea."
```

Por qué esto vale como "alarma real", con la doc pegada:

- **Dispara las acciones de verdad.** *"When the updated state differs from the previous value,
  the action configured for the appropriate state is invoked. For example, if your alarm is
  configured to send an Amazon SNS message when an alarm is triggered, temporarily changing the
  alarm state to `ALARM` sends an SNS message."*
  — https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/set-alarm-state.html
- **Es reversible sola.** *"You can test an alarm by setting it to any state using the
  SetAlarmState API action… This temporary state change lasts only until the next alarm
  comparison occurs."*
  — https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html
  Con `period = 300`, la vuelta a `OK` llega en ≤ ~5 min y dispara `ok_actions` (`main.tf:53`).
- **Precedente en esta casa:** ya se usó `set-alarm-state` contra producción para desmontar la
  trampa de `treat_missing_data = "missing"` (`takab-docs/TASKS.md:2429`). No es un juguete
  nuevo.
- **Valores permitidos de `--state-value`:** `OK`, `ALARM`, `INSUFFICIENT_DATA`; `--state-reason`
  es **obligatorio** (máx. 1023 caracteres) — misma URL del CLI.

**Lo del `--state-reason` no es cosmético:** es el único sitio donde puedes escribir "esto es
un simulacro" y "cómo se acusa". Durante el ensayo **verifica y anota si ese texto aparece en
el cuerpo del correo** (registro §3.7, fila C-6). Si no aparece, la instrucción de acuse tiene
que viajar por otro lado y el ensayo se repite con esa corrección.

### 3.4 Los cuatro instantes (esto es lo que se cronometra)

| Instante | Qué es | Cómo se obtiene |
|---|---|---|
| **t0** | La **condición** existe | `date -u` justo antes del `set-alarm-state` |
| **t1** | La **alarma** transiciona a `ALARM` | `aws cloudwatch describe-alarm-history --alarm-name takab-dev-dlq-backfill --history-item-type StateUpdate --max-records 5` → campo `Timestamp` |
| **t2** | El **correo** aterriza en la bandeja | cabecera `Date:` / `Received:` del correo, no la hora en que lo miraste |
| **t3** | La **persona acusa** | el reloj del acuse: hora de la respuesta / del mensaje en el canal / de la llamada |

**t3 es el instante que nadie mide y es el que importa.** t0→t1→t2 lo garantiza AWS y ya
estaba acreditado desde A-4 (2026-07-13/14). Lo que `T-2.78` añade es t2→t3: **entregado no es
leído por una persona.**

Cómo se captura t1 (sin esperar al correo):

```bash
! AWS_PROFILE=takab-dev aws cloudwatch describe-alarm-history --region us-east-2 \
    --alarm-name takab-dev-dlq-backfill --history-item-type StateUpdate --max-records 5 \
    --query 'AlarmHistoryItems[].{Cuando:Timestamp,Que:HistorySummary}' --output table
```
AWS conserva ese histórico 30 días: *"CloudWatch preserves alarm history for 30 days. Each state
transition is marked with a unique timestamp."*
— https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html

**~~Qué NO se puede medir con lo que hay~~ · CERRADO POR `T-2.78.a` (software, 2026-08-14).**
Hasta esa ficha no existía ningún mecanismo de acuse para esta cadena: `POST
/incidents/{id}/ack` acusa un **incidente sísmico**, no una alarma de operación, y no había
fila donde apuntar t3. Ahora sí la hay, y **t2 y t3 dejaron de anotarse a mano**. Ver §3.8.

> **Sigue siendo cierto que AWS no puede decirte si el CORREO se entregó** (§3.6). Lo que
> `T-2.78.a` añade no es eso: es un **segundo suscriptor del mismo topic**, por HTTPS, que sí
> admite registro de entrega — y que además escribe la fila. El correo sigue siendo el canal
> que despierta a la persona; el suscriptor es el que deja constancia.

### 3.8 t2 y t3 de MÁQUINA (`T-2.78.a`)

Con `ops_alert_https_subscriber_enabled = true` (ver §3.9, y **léelo antes: el orden importa**)
cada mensaje del topic llega también a `POST /api/ops/alerts/sns`, que verifica la firma RSA
del sobre y escribe una fila en `ops_alert_notices`. Esa fila **nace sin acuse**, con su plazo
puesto — que es la respuesta a "quién escribe la fila del que no contestó": nadie, después.
La escribe la máquina que recibió el aviso, en el instante del aviso.

| Instante | De dónde sale ahora | Sustituye a |
|---|---|---|
| **t2′** | `received_at` de `v_ops_alert_chain` — el reloj de nuestro servidor, sin depender del buzón de nadie | la cabecera `Date:` del correo |
| **t3** | `acked_at` de la misma fila | la hora de la respuesta, anotada a mano |
| **t3 − t2′** | `ack_latency_s`, **calculado por la base** | una resta a mano entre dos relojes distintos |

```bash
# Todo lo del ensayo, en una consulta (desde la instancia):
docker exec takab-db psql -U postgres -d takab -c \
  "SELECT alarm_name, alarm_state, received_at, acked_at, acked_by, unacked_at, outcome,
          round(ack_latency_s) AS s_hasta_acuse
     FROM v_ops_alert_chain ORDER BY received_at DESC LIMIT 10"
```

`outcome` sale de la vista y **no es una columna que nadie pueda poner en verde**: `acusado` es
imposible sin `acked_at`. Los cinco valores: `no_requiere_acuse` (una vuelta a `OK` se registra
pero no abre plazo), `esperando_acuse`, `sin_acuse`, `acusado`, `acusado_tarde`.

**Cómo acusa la persona** — y por qué así:

1. Se le acuña UNA credencial personal, y se le enseña UNA vez:
   ```bash
   # en la instancia, dentro del contenedor de la API
   python -m takab_api.ops.oncall issue --label "Mauricio (primaria)" --days 90
   ```
   La base guarda **solo el hash**; el secreto no se puede recuperar de ningún sitio. Se pega
   en el gestor de contraseñas de la persona, con `https://<consola>/api/ops/alerts/ack`
   guardado como marcador en su teléfono.
2. A las 3 de la mañana: abrir el marcador, el gestor rellena el campo, un toque.
3. `python -m takab_api.ops.oncall revoke --contact-id <uuid>` cuando esa persona deja la
   guardia. `list` dice quién sigue vigente.

**Por qué NO es la consola con MFA:** un acuse que exija abrir el SOC y pasar MFA a las 3 de la
mañana es un acuse que no se va a dar, y entonces C-5 mediría fricción y no atención. **Por qué
no es un enlace pelado en el correo:** los escáneres de seguridad de los buzones **pulsan los
enlaces**; un acuse por `GET` lo fabricaría una máquina antes de que nadie leyera nada. Por eso
el acuse es un `POST` y la credencial no viaja nunca en el correo. **Qué acredita, dicho sin
adornos:** lo mismo que poder leer el buzón de guardia — que es el listón que ya tiene
cualquiera que reciba la alarma. Lo que añade es que el acuse queda **a nombre de una persona**,
se **revoca sin tocar el buzón** y **caduca solo**.

**Y si nadie acusa:** la fila ya existe desde el aviso, así que el silencio no depende de que
alguien lo apunte. Pasado `TAKAB_API_OPS_ACK_DEADLINE_S` (default **900 s**, y ese número lo
tiene que ratificar la pregunta P-3 del §4.3 — hoy es un default, no una política), el worker
`notify` estampa `unacked_at`: la hora en que el silencio dejó de ser espera y pasó a fallo
declarado. Es donde engancha el salto 2 del §4.2.

### 3.9 [ORDEN] Encender el suscriptor sin romper el apply

**La suscripción HTTPS se confirma DURANTE el `terraform apply`**
(`endpoint_auto_confirms = true`). Si el endpoint todavía no existe, o existe pero contesta
`503` porque le falta el ARN del topic, la confirmación falla y **el apply muere a medias**.
Orden correcto, y qué se rompe al revés:

1. **Desplegar la API** con `T-2.78.a` dentro y con `TAKAB_API_OPS_ALERT_TOPIC_ARN` puesto en
   `cloud.env` (el ARN del topic; no es secreto). Sin esa variable el endpoint es fail-closed
   **ruidoso**: `503` y un `ERROR` en el log que dice exactamente qué falta.
2. **Comprobar el endpoint desde fuera**, antes de tocar Terraform:
   ```bash
   # Un cuerpo sin firma tiene que dar 404 (y NO 503, y NO 200).
   curl -s -o /dev/null -w '%{http_code}\n' -X POST \
     https://<consola>/api/ops/alerts/sns -d '{}'
   ```
   `404` = configurado y rechazando lo que no viene firmado ⇒ seguir. `503` = falta el ARN,
   **para aquí**. `404` de nginx/Caddy con cuerpo HTML = la imagen desplegada no trae la ruta.
3. **Entonces** `ops_alert_https_subscriber_enabled = true` y `terraform apply`.
4. Comprobar que la suscripción quedó `Confirmed` y que el registro de entrega está puesto:
   ```bash
   ! AWS_PROFILE=takab-dev aws sns list-subscriptions-by-topic --region us-east-2 \
       --topic-arn "$TOPIC" --query 'Subscriptions[?Protocol==`https`]' --output table
   ! AWS_PROFILE=takab-dev aws sns get-topic-attributes --region us-east-2 \
       --topic-arn "$TOPIC" --query 'Attributes.HTTPSuccessFeedbackRoleArn'
   ```

**Al revés** (Terraform primero) el `apply` falla en el recurso de la suscripción, deja el resto
aplicado y hay que repetirlo — no destruye nada, pero convierte una ventana de diez minutos en
una tarde. Y **no lo enciendas con `serve_enabled = false`**: sin consola publicada no hay URL
que suscribir, y el módulo lo trata como apagado a propósito.

### 3.5 Engancha aquí la verificación de la alarma de fantasmas

Es **el mismo procedimiento** y por eso se hace en la misma sesión, no en otra.

`takab-dev-gateway-retirado-sigue-reportando` (`main.tf:225`) está escrita y probada pero
**todavía no aplicada** en AWS (`TASKS.md:3847-3849`). Cuando nazca, nacerá en
`INSUFFICIENT_DATA`, y ahí está la trampa:

> `insufficient_data_actions` **solo dispara EN TRANSICIÓN.** Confirmado por AWS: *"An alarm
> invokes actions only when the alarm changes state."*
> (https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html).
> Una métrica que **nunca arranca** deja la alarma aparcada en `INSUFFICIENT_DATA`: sin
> transición, sin correo, y el panel enseñando un estado que se lee como "aún no hay datos".
> Es la forma exacta que tuvo el fallo del 2026-08-05 (`count_ghosts` con `KeyError: 0`
> tragado por un `except`: no salía ni el cero).

La señal de que la métrica **sí** arrancó es un correo de `ok_actions` al salir por primera vez
de `INSUFFICIENT_DATA`, y **su ausencia tras el apply es el indicio**. Pasos, en los ~15 min
siguientes al `terraform apply`:

```bash
! AWS_PROFILE=takab-dev aws cloudwatch describe-alarms --region us-east-2 \
    --alarm-names takab-dev-gateway-retirado-sigue-reportando \
    --query 'MetricAlarms[0].StateValue'
# Sigue en INSUFFICIENT_DATA ⇒ mirar si la métrica sale del EC2:
! AWS_PROFILE=takab-dev aws cloudwatch get-metric-statistics --region us-east-2 \
    --namespace Takab/Ops --metric-name GhostGatewaysAlive --statistics Maximum \
    --period 300 --start-time <ISO8601> --end-time <ISO8601>
# cero datapoints = la métrica NO está saliendo.
```

Orden de diagnóstico de los cinco fallos que colapsan en el mismo silencio (worker `notify`
parado · `count_ghosts` lanza · `build_ghost_gauge` dejó `client=None` sin excepción · IAM sin
`PutOpsMetrics` · `TAKAB_API_OPS_METRICS_ENABLED` sin poner): `TASKS.md:3870-3880`. El
`logger.warning` del worker **no sale del EC2** (`deploy/cloud/docker-compose.yml`,
`logging: driver: json-file`, sin agente CloudWatch): es una miga forense para quien ya entró
por SSM, jamás una alerta.

### 3.6 Trampas del ensayo

- **Un rebote silencia el buzón 7 días.** AWS: *"If a subscribed email address results in a
  bounce, the address is suppressed from further deliveries for 7 days."*
  (https://docs.aws.amazon.com/sns/latest/dg/sns-email-notifications.html). Un on-call que
  rebotó una vez deja de recibir alarmas **una semana entera y sin avisar a nadie**. Si el
  ensayo no produce correo y todo lo demás está bien, sospecha de esto.
- **AWS no puede decirte si el correo se entregó.** El registro de estado de entrega de SNS
  soporta *"Amazon Data Firehose, Amazon Simple Queue Service, AWS Lambda, HTTPS, Platform
  application endpoint"* — **email y email-json no están en la lista**
  (https://docs.aws.amazon.com/sns/latest/dg/sns-topic-attributes.html). Por eso t2 se toma de
  las cabeceras del correo recibido y **no** de AWS. Es la razón de fondo de la ficha
  `T-2.78.a`.
- **Una ventana de mantenimiento abierta puede tragarse una alarma.** No la elegida (§3.1),
  pero sí `gateway-offline` y `sensor-mudo`. Si algún día se cambia la alarma del ensayo,
  revísalo primero en `api/src/takab_api/ops/muting.py:219-286`.
- **El estado forzado se deshace solo.** No lo devuelvas a mano con otro `set-alarm-state --state-value OK`:
  perderías la prueba de que la alarma **sabe volver** por su cuenta, que es la mitad útil del
  ensayo. Espera el ciclo.
- **No cuentes t3 desde que "alguien lo vio en el móvil".** Si el acuse no deja rastro con hora
  (respuesta al correo, mensaje en un canal, registro de llamada), no es un acuse: es un
  recuerdo.

### 3.7 Registro de verificación — cadena on-call (llenar al ejecutar; SIN marcar hasta entonces)

| # | Prueba | Esperado | Medido | OK/NO | Fecha/inicial |
|---|---|---|---|---|---|
| C-1 | Suscripción SNS `Confirmed` (no `PendingConfirmation`) | confirmada |  |  |  |
| C-2 | **t0** — hora de la condición | — |  |  |  |
| C-3 | **t1** — transición a `ALARM` en `describe-alarm-history` | t1 − t0 ≤ 1 min |  |  |  |
| C-4 | **t2** — cabecera `Date:` del correo | t2 − t1 ≤ 2 min |  |  |  |
| C-4′ | **t2′** — `received_at` en `v_ops_alert_chain` (§3.8) | fila presente, ≤ 2 min tras t1 |  |  |  |
| C-5 | **t3 — acuse humano, con rastro** — `acked_at`/`ack_latency_s` de la misma fila, ya NO a mano | **objetivo sin fijar — ver §4.3 P-3**; el mecanismo existe desde `T-2.78.a` |  |  |  |
| C-5′ | Con el acuse dado, `outcome` = `acusado` (o `acusado_tarde`) y `acked_by` trae el nombre | sí |  |  |  |
| C-6 | ¿El texto de `--state-reason` viaja en el cuerpo del correo? | SÍ/NO |  |  |  |
| C-7 | Vuelta sola a `OK` + correo de `ok_actions` | ≤ ~5 min tras t1 |  |  |  |
| C-8 | Repetición **fuera de horario** (02:00–05:00 local) | mismo t3 o mejor |  |  |  |
| C-9 | Ensayo con el **primer** contacto deliberadamente sin responder | escala al segundo (§4) **y la fila queda en `sin_acuse` con `unacked_at` puesto** |  |  |  |
| C-10 | Fantasmas: sale de `INSUFFICIENT_DATA` tras el apply (§3.5) | correo de `ok_actions` |  |  |  |

**C-8 no es opcional.** Una cadena que solo se ha probado a las 11 de la mañana no está probada:
el sismo del que hablamos no consulta el horario. **C-9 tampoco**: sin ejecutarlo, el
escalamiento del §4 es un párrafo, no un procedimiento.

---

## 4. Escalamiento escrito

### 4.1 [PARA] · Sobre qué canales se puede apoyar HOY

El escalamiento no puede colgar de canales que no entregan. Estado real, hoy:

| Canal | ¿Entrega hoy? | Evidencia |
|---|---|---|
| **Correo del topic SNS (operación)** | **Sí**, si la suscripción está confirmada | `modules/observability/main.tf:29-33`; A-4 cerrado 2026-07-13/14 |
| **Correo de incidente (SES)** | **Sí, pero en sandbox**: solo a destinos verificados, 200/día, 1/s | §2.1 |
| **SMS (Twilio)** | **NO.** Sin credenciales el canal cae a `simulated`: escala al correo y deja huella honesta, pero **nadie recibe un SMS** | `T-2.76.a`, `api/src/takab_api/notify/providers.py` |
| **WhatsApp** | **NO** — `T-2.77` en curso | ficha `T-2.77` |
| **Push móvil** | Depende de credenciales APNs/FCM reales | `GATE-STORE`, `RUNBOOK-cierre-fase2.md §4` |
| **Llamada telefónica** | Fuera del sistema. No hay integración de voz | — |

**Consecuencia, escrita para que nadie la descubra a las 3 de la mañana:** hoy **el único canal
que entrega de verdad al on-call es el correo**, y un correo es un canal *pull* — llega cuando
la persona mira. Cualquier escalamiento que diga "si no responde en X minutos, SMS" está
prometiendo algo que el sistema no hace. Mientras `T-2.76.a` no cierre, **el segundo salto es
humano**: alguien llama por teléfono desde su propio móvil. Escríbelo así, con esas palabras;
no lo maquilles.

Y `T-2.75` hace que esto sea *visible* en vez de mentiroso: un canal simulado marca
`notify_simulated`, jamás `sent`. **Un tablero honesto sigue siendo un tablero sin SMS.**

### 4.2 La plantilla (rellenar y firmar — es un compromiso, no una tabla)

**Rotación de guardia**

| Turno | Desde | Hasta | Primario | Secundario | Canal primario | Canal secundario |
|---|---|---|---|---|---|---|
| Laboral |  |  |  |  |  |  |
| Noche |  |  |  |  |  |  |
| Fin de semana / festivo |  |  |  |  |  |  |

**Escalamiento**

| Salto | Cuándo se activa | A quién | Por qué canal | Quién lo ejecuta |
|---|---|---|---|---|
| 1 | Llega la alarma (t2) | Primario |  | automático (SNS) |
| 2 | Sin acuse en **____ min** | Secundario |  | **[HUECO]** — hoy no hay automatismo: lo ejecuta una persona |
| 3 | Sin acuse en **____ min** | Terciario / responsable |  |  |
| 4 | Sin acuse en **____ min** | Se activa el plan de degradación (§4.4) |  |  |

**Datos de contacto** (fuera de git: regla de oro 6 — aquí solo el puntero)

| Rol | Nombre | Dónde vive el teléfono |
|---|---|---|
| Primario |  |  |
| Secundario |  |  |
| Responsable |  |  |

**Firmado por:** ____________________  **Fecha:** __________  **Revisión:** cada ______ meses.

### 4.3 Las preguntas que la plantilla obliga a contestar

- **P-1 · ¿El primario y el secundario son la misma persona?** Hoy, en la práctica, sí: los
  tres correos configurados (`budget_email`, `ses_verified_emails`, `ops_alert_email`) son **la
  misma dirección** (`infra/terraform/envs/dev/variables.tf:45-65`). Un escalamiento con un solo
  nombre no es un escalamiento; es una lista. **Si de verdad hoy no hay un segundo, escríbelo
  como riesgo aceptado con fecha de caducidad**, no lo dejes en blanco.
- **P-2 · ¿Qué cuenta como acuse?** Fija UNA forma con rastro y hora. Responder al correo es la
  más barata y la única que hoy no exige software nuevo.
- **P-3 · ¿En cuántos minutos escala?** Es el objetivo de C-5 y **nadie lo ha fijado**.
  Referencia para calibrar, no para copiar: `gateway_offline` detecta en ~10 min por diseño
  (`main.tf:179-181`, coste aceptado y razonado), y el criterio ahí es explícito — *"esta alarma
  NO está en el camino de actuación… solo sirve para que un humano vaya a ver el gabinete, y
  para eso 10 minutos son lo mismo que uno"*. El acuse humano se mide contra ese mismo rasero,
  no contra el SLA de notificación de un sismo (30 s, `settings.py:233`), que es **otra cadena**.
- **P-4 · ¿Quién ejecuta el salto 2?** Sigue sin haber automatismo, y `T-2.78.a` **no lo
  inventa**: lo que aporta es el *disparador* medible — `unacked_at` puesto y `outcome =
  'sin_acuse'` (§3.8) — y el registro de que ocurrió. Quién marca el teléfono sigue siendo una
  persona, y hay que escribir cuál. **"Ya veremos" sigue sin ser una respuesta.**
- **P-5 · ¿Y si el canal del secundario tampoco es el correo?** Ver §4.1: si la respuesta es
  "SMS", el escalamiento depende de `T-2.76.a` y **no está escrito, está prometido**.
- **P-6 · ¿Cuándo se revisa?** Una rotación sin fecha de revisión caduca en silencio: la persona
  cambia de puesto y el correo sigue apuntando a su buzón.

### 4.4 Qué pasa si nadie acusa

La pregunta que nadie escribe. Respuestas posibles, para elegir una explícitamente:

1. **Degradación declarada:** la alerta se da por no atendida y se registra como tal. La
   protección local del gabinete sigue intacta (regla de oro 2: SASMEX→sirena es 100 % local y
   no depende de nadie de esta lista). **Esto es cierto y hay que decirlo en voz alta:** que
   nadie conteste un correo no deja un edificio desprotegido; deja un fallo de infraestructura
   sin atender.
2. **Aviso al cliente:** si el gabinete afectado es de un tenant, ¿se le dice, y en cuánto?
   **[HUECO]** — hay obligación contractual solo si el documento de entrega (`T-2.86`) la
   escribe.
3. **Registro obligatorio:** todo salto sin acuse se anota. Sin eso, "nadie contestó" es una
   anécdota y no una métrica, y a la tercera vez nadie se acuerda de las dos primeras.
   **Esta tercera ya no es una opción que elegir: es automática desde `T-2.78.a`.** La fila
   nace con el aviso y nace sin acuse, así que el silencio no depende de que nadie se acuerde
   de apuntarlo; el worker le pone hora (`unacked_at`) cuando vence el plazo. Contar cuántas
   veces pasó es una consulta:

   ```sql
   SELECT date_trunc('week', received_at) AS semana,
          count(*) FILTER (WHERE outcome = 'sin_acuse')      AS sin_acuse,
          count(*) FILTER (WHERE outcome = 'acusado_tarde')  AS tarde,
          count(*) FILTER (WHERE outcome = 'acusado')        AS a_tiempo,
          round(avg(ack_latency_s) FILTER (WHERE acked_at IS NOT NULL)) AS s_medios
     FROM v_ops_alert_chain WHERE requires_ack GROUP BY 1 ORDER BY 1 DESC;
   ```

   Lo que sigue siendo decisión humana son las dos primeras (declarar la degradación y avisar
   o no al cliente). El punto 1 no cambia y conviene repetirlo: **que nadie conteste un correo
   no deja un edificio desprotegido** (regla de oro 2), deja un fallo de infraestructura sin
   atender.

Escribe cuál de las tres se adopta, y las tres si son compatibles. Un escalamiento que termina
en "…y entonces ya" no termina.

---

## 5. Lo que este runbook NO acredita

Honestidad primero, como el resto de la casa:

- **No acredita la cadena de incidentes sísmicos.** Es otra cadena (§1). La acredita `T-2.94`.
- **No acredita entrega, en ningún canal.** El techo de la evidencia del sistema es "el
  proveedor lo aceptó": SES sin excepción ⇒ `sent`; Twilio devolviendo `queued`/`accepted` ⇒
  `sent`; SNS `publish()` sin error ⇒ push contado. Ninguno significa "está en la pantalla de
  alguien". Para SNS-email, AWS ni siquiera ofrece el dato (§3.6).
- **No acredita el SMS**: hoy cae a simulado (`T-2.76.a`).
- **~~No deja el acuse medido de forma repetible~~ · resuelto (`T-2.78.a`, 2026-08-14):** t3 y
  el tiempo hasta el acuse salen ahora de `v_ops_alert_chain` (§3.8) y el silencio deja fila
  sola. Lo que este runbook **sigue** sin acreditar de eso es lo humano: que la persona de
  guardia tenga su credencial acuñada, la lleve en el teléfono y la use. Eso se mide en C-5 y
  no lo cierra ningún commit.
- **No acredita que el correo llegue a una bandeja**, ni con el suscriptor puesto: el
  suscriptor HTTPS prueba que **el topic entregó**, no que el buzón lo recibiera (§3.6 sigue
  vigente: un rebote suprime una dirección 7 días sin avisar a nadie). Son dos hechos y esto
  solo acredita el primero.
- **No cubre bounces ni quejas de SES**: no hay feedback topic (`T-2.78.b`). Y el reconocimiento
  de la solicitud de producción afirma que sí hay un proceso (§2.4).

---

## 6. Fichas abiertas que salieron de preparar esto

- **`T-2.78.a`** — acuse y evidencia de entrega de la cadena de OPERACIÓN. Hoy t3 no tiene
  dónde escribirse y AWS no reporta entrega por email.
- **`T-2.78.b`** — identidad de DOMINIO en Terraform (DKIM, MAIL FROM, DMARC, feedback de
  bounces), para que el §2 sea reproducible y no una sesión de clics.
- **`T-2.76.a`** (ya existente) — sin ella el §4 no puede apoyarse en SMS.
- **`T-2.60.a`** (ya existente) — el `terraform apply` de la alarma de fantasmas y su
  verificación, enganchada aquí en §3.5.

---

*Referencias: `takab-docs/TASKS.md` T-2.78 (y T-2.60.a `:3847-3880`, T-2.76.a, T-2.77) ·
`takab-docs/runbooks/RUNBOOK-auditoria-cierre.md` §7 O1 y hallazgos A-4/M-3 ·
`infra/terraform/modules/observability/main.tf` · `infra/terraform/modules/identity/main.tf:139` ·
`infra/terraform/envs/dev/main.tf:75-82,157-165` · `api/src/takab_api/ops/muting.py:219-286` ·
`api/src/takab_api/settings.py:226-261` · `CLAUDE.md` §2 (reglas de oro 2, 6, 7, 10).*
