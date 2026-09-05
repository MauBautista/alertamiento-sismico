# Encargados — quién más toca los datos personales

> **GENERADO. No lo edites a mano.**
> `cd api && uv run python tests/test_encargados.py --escribir`
>
> La fuente es `api/src/takab_api/privacy/encargados.py`, y dos censos la
> comparan por igualdad contra el código (`api/tests/test_encargados.py`):
> un proveedor nuevo sin declarar, o un servicio de AWS sin clasificar,
> ponen el build en rojo nombrándolo.

> ⚠️ **Este inventario NO es el aviso de privacidad revisado.** El aviso sigue
> siendo provisional y lo dice dentro de su propio texto (`D-20`: la consulta
> jurídica espera a que un cliente la pida). Esto es la costura: el día que
> llegue el texto revisado, la lista ya existe y está al día.

## 1 · Encargados

| Encargado | Para qué | Qué datos | País | De dónde sale |
|---|---|---|---|---|
| **Apple Inc. (APNs) y Google LLC (FCM), vía Amazon SNS** | despertar la app en el teléfono con el aviso de emergencia | identificador de dispositivo (token de push); texto del aviso | US | `takab_api.notify.push.SnsPushProvider` |
| **Amazon Web Services, Inc. (SES)** | entregar el aviso de emergencia por correo | correo; texto del aviso | US | `takab_api.notify.providers.SesEmailProvider` |
| **El servicio de compilación y distribución de la app móvil** | firmar y distribuir el binario que se instala en el teléfono | ninguno de las personas usuarias en tiempo de ejecución; metadatos de la cuenta de desarrollo | US | `fuera del código de producción: cadena de build (GATE-STORE)` |
| **Meta Platforms, Inc. (WhatsApp Cloud API)** | entregar el aviso de emergencia por WhatsApp | teléfono; variables de la plantilla aprobada | US | `takab_api.notify.whatsapp.WhatsAppTemplateProvider` |
| **Twilio Inc.** | entregar el aviso de emergencia por SMS | teléfono; texto del aviso (sitio y severidad) | US | `takab_api.notify.twilio.TwilioSmsProvider` |
| **El endpoint que el propio cliente configura** | entregar el aviso al sistema que el cliente designe (BMS, SOC propio) | sitio; severidad; instante del incidente | desconocido: lo determina el cliente al configurar la URL | `takab_api.notify.providers.WebhookProvider` |

## 2 · Transferencia internacional

**5 de 6** encargados tratan los datos fuera de México. La región de despliegue es `us-east-2` (Ohio).

Y **1** cuyo país **no se sabe porque lo elige el cliente** al configurarlos. No se cuentan arriba: contarlos afirmaría una transferencia que nadie ha comprobado, y callarlos escondería a un tercero.

- **El endpoint que el propio cliente configura** — desconocido: lo determina el cliente al configurar la URL

Los servicios de AWS que **guardan o transportan** datos personales, derivados de
`infra/terraform`:

- `aws_cloudwatch` — los registros pueden contener identificadores
- `aws_cognito` — identidades: correo y nombre para mostrar de cada persona
- `aws_dlm` — instantáneas del volumen: copias de los mismos datos
- `aws_dynamodb` — estado del despliegue y candados de terraform
- `aws_ebs` — el volumen de datos del Postgres
- `aws_ecr` — las imágenes traen el código que trata los datos (no los datos)
- `aws_instance` — el Postgres del despliegue vive en esta instancia
- `aws_iot` — los mensajes del gabinete pasan por aquí
- `aws_kms` — las llaves con las que se cifran
- `aws_lambda` — procesa vídeo de CCTV, que puede contener personas
- `aws_s3` — evidencia del incidente: fotografías de reportes de daño y PDFs
- `aws_secretsmanager` — guarda las credenciales con las que se accede a los datos
- `aws_sesv2` — entrega el aviso por correo
- `aws_sns` — empuja el aviso al teléfono (tokens de push)
- `aws_sqs` — la cola transporta el aviso y la evidencia antes de persistirlos
- `aws_volume` — adjunta el volumen de datos del Postgres

Y los que **no**, con su razón — están aquí porque un censo que solo enumera lo que
sí es un censo que no se puede comprobar:

- `aws_acm` — certificados TLS de los dominios: criptografía, no datos de personas
- `aws_budgets` — alertas de gasto de la cuenta de AWS, sin dato de personas
- `aws_cloudfront` — distribuye los estáticos de la consola (JS y CSS), no datos
- `aws_eip` — una dirección IP fija de la infraestructura, no de una persona
- `aws_iam` — permisos de máquinas y roles de servicio, no de personas usuarias
- `aws_internet` — puerta de enlace a internet de la red privada
- `aws_network` — listas de control de acceso de la red: reglas de puertos y rangos
- `aws_route` — tablas de enrutamiento de la red privada
- `aws_route53` — resuelve los nombres de dominio de la plataforma
- `aws_security` — grupos de seguridad: qué puertos se abren y desde dónde
- `aws_ssm` — parámetros de despliegue y acceso remoto a la instancia
- `aws_subnet` — segmentos de la red privada del despliegue
- `aws_vpc` — la red privada donde corre el despliegue

## 3 · Lo que ningún censo alcanza

Terceros que no corren en producción y que por tanto ningún análisis del código
puede encontrar. Se declaran a mano y llevan su razón:

- **El servicio de compilación y distribución de la app móvil** — firmar y distribuir el binario que se instala en el teléfono · `fuera del código de producción: cadena de build (GATE-STORE)`

## 4 · Lo que esto le deja pendiente a la consulta jurídica

`D-23` y `D-07` descansan **las dos** sobre la calificación de que TAKAB es
**encargado** y no **responsable**, y esa calificación solo está afirmada en un
texto que se declara sin revisar. Es un hecho nuevo para la lista de la consulta,
no una decisión que este documento tome. Ver `PENDIENTES-MAURICIO.md §4.1`.
