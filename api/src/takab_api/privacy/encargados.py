"""Inventario de ENCARGADOS: quién más toca los datos personales (T-5.19).

Siete terceros tocan o tocarán datos personales de las personas que usan el
sistema, y **ninguno estaba declarado**. El aviso tampoco mencionaba la
transferencia internacional, aunque los datos viven en Ohio; el párrafo más
cercano —«SUS DATOS NO CRUZAN A OTRA ORGANIZACIÓN»— habla del aislamiento entre
clientes y es fácil de leer como una negación de ella.

QUÉ CIERRA ESTE MÓDULO Y QUÉ NO
--------------------------------
**No reabre la consulta jurídica**: `D-20` la deja esperando a que un cliente la
pida, y esta ficha no lo cambia. Lo que hace es dejar el trabajo de costura listo
para el día que llegue el texto revisado, y **que el inventario exista y esté al
día** mientras tanto.

Y anota el hecho nuevo que la consulta tendrá que traer en su lista: `D-23` y
`D-07` descansan **las dos** sobre la calificación de que TAKAB es *encargado* y
no *responsable*, y esa calificación solo está afirmada en un texto que se
declara sin revisar.

POR QUÉ ESTO SE DERIVA Y NO SE TECLEA
--------------------------------------
Un inventario de encargados escrito a mano dura hasta el primer proveedor nuevo,
y el día que se queda corto **nadie se entera**: no hay pantalla que falle ni
test que se ponga rojo. Aquí las dos poblaciones se derivan y se comparan por
igualdad contra esta declaración:

1. **Las clases proveedoras** del paquete `notify` que de verdad salen a un
   tercero (`test_encargados.py`). Una clase nueva sin declarar pone el build en
   rojo nombrándola.
2. **Los servicios de AWS** que aparecen en `infra/terraform`. Cada uno tiene que
   estar clasificado: o guarda datos personales, o no, **con su razón**.

Lo que ninguna de las dos alcanza —la cadena de compilación del móvil, que es un
tercero de tiempo de BUILD y no de ejecución— se declara a mano y lleva su razón
escrita, que es la única forma honesta de sostener una excepción.
"""

from __future__ import annotations

from dataclasses import dataclass

#: País donde el encargado trata los datos. `MX` es el único que no implica
#: transferencia internacional; todo lo demás la implica y por eso se declara.
PAIS_PROPIO = "MX"

#: País que NO se sabe porque lo elige el cliente. **No es «fuera de México»** y
#: no puede contarse como tal: eso sería afirmar una transferencia que nadie ha
#: comprobado, en un documento que existe justamente para no afirmar de más.
#: Un país que empieza por esta palabra se cuenta aparte y se declara aparte.
PAIS_DESCONOCIDO = "desconocido"


@dataclass(frozen=True)
class Encargado:
    """Un tercero que trata datos personales por cuenta del responsable."""

    key: str
    nombre: str
    #: Para qué. En prosa: acaba impreso en un documento que lee un cliente.
    finalidad: str
    #: Qué categorías de dato personal alcanza. NO «todos»: la lista concreta es
    #: lo que permite discutir si el tratamiento es proporcionado.
    datos: tuple[str, ...]
    #: País de tratamiento. Distinto de `PAIS_PROPIO` ⇒ transferencia internacional.
    pais: str
    #: Qué símbolo del código lo trae. Es el ancla que hace verificable la
    #: declaración: sin esto, «Twilio» sería una palabra en un documento.
    via: str


#: Encargados que el CÓDIGO trae, uno por clase proveedora que sale a un tercero.
#: La clave es el nombre de la clase: es lo que el censo compara por igualdad.
POR_PROVEEDOR: dict[str, Encargado] = {
    "TwilioSmsProvider": Encargado(
        key="twilio",
        nombre="Twilio Inc.",
        finalidad="entregar el aviso de emergencia por SMS",
        datos=("teléfono", "texto del aviso (sitio y severidad)"),
        pais="US",
        via="takab_api.notify.twilio.TwilioSmsProvider",
    ),
    "WhatsAppTemplateProvider": Encargado(
        key="meta",
        nombre="Meta Platforms, Inc. (WhatsApp Cloud API)",
        finalidad="entregar el aviso de emergencia por WhatsApp",
        datos=("teléfono", "variables de la plantilla aprobada"),
        pais="US",
        via="takab_api.notify.whatsapp.WhatsAppTemplateProvider",
    ),
    "SesEmailProvider": Encargado(
        key="aws-ses",
        nombre="Amazon Web Services, Inc. (SES)",
        finalidad="entregar el aviso de emergencia por correo",
        datos=("correo", "texto del aviso"),
        pais="US",
        via="takab_api.notify.providers.SesEmailProvider",
    ),
    "SnsPushProvider": Encargado(
        key="apple-google",
        nombre="Apple Inc. (APNs) y Google LLC (FCM), vía Amazon SNS",
        finalidad="despertar la app en el teléfono con el aviso de emergencia",
        datos=("identificador de dispositivo (token de push)", "texto del aviso"),
        pais="US",
        via="takab_api.notify.push.SnsPushProvider",
    ),
    "WebhookProvider": Encargado(
        key="webhook-del-cliente",
        nombre="El endpoint que el propio cliente configura",
        # El matiz importa y por eso está escrito: aquí el destino lo elige el
        # RESPONSABLE, no TAKAB. Sigue siendo un tercero que recibe el dato, y
        # omitirlo por ese matiz sería exactamente el hueco que abre la ficha.
        finalidad="entregar el aviso al sistema que el cliente designe (BMS, SOC propio)",
        datos=("sitio", "severidad", "instante del incidente"),
        pais="desconocido: lo determina el cliente al configurar la URL",
        via="takab_api.notify.providers.WebhookProvider",
    ),
}

#: Clases proveedoras que NO son un tercero, con su razón. Existe para que el
#: censo compare por igualdad en vez de por contención: una clase nueva cae en
#: ninguna de las dos listas y sale roja.
SIN_TERCERO: dict[str, str] = {
    "SimulatedProvider": (
        "no envía nada: es el canal SIN proveedor configurado. Los jobs quedan "
        "'simulated' y nadie recibe el aviso, así que no hay dato que transferir."
    ),
    "SimulatedPushProvider": (
        "el equivalente del anterior para push: sin ARN de plataforma no hay a "
        "quién empujar nada, y el job queda 'simulated' declarándolo."
    ),
}

#: El tercero que ningún censo del código puede ver, porque no corre en
#: producción: entra en tiempo de COMPILACIÓN. Se declara a mano y con su razón.
FUERA_DEL_CENSO: tuple[Encargado, ...] = (
    Encargado(
        key="cadena-de-compilacion-movil",
        nombre="El servicio de compilación y distribución de la app móvil",
        finalidad="firmar y distribuir el binario que se instala en el teléfono",
        datos=(
            "ninguno de las personas usuarias en tiempo de ejecución",
            "metadatos de la cuenta de desarrollo",
        ),
        pais="US",
        via="fuera del código de producción: cadena de build (GATE-STORE)",
    ),
)

#: Servicios de AWS que aparecen en `infra/terraform` y **guardan o transportan
#: datos personales**. La transferencia internacional que el aviso tiene que
#: declarar sale de aquí: la región es `us-east-2` (Ohio).
AWS_CON_DATOS: dict[str, str] = {
    "aws_instance": "el Postgres del despliegue vive en esta instancia",
    "aws_ebs": "el volumen de datos del Postgres",
    "aws_volume": "adjunta el volumen de datos del Postgres",
    "aws_dlm": "instantáneas del volumen: copias de los mismos datos",
    "aws_s3": "evidencia del incidente: fotografías de reportes de daño y PDFs",
    "aws_cognito": "identidades: correo y nombre para mostrar de cada persona",
    "aws_sns": "empuja el aviso al teléfono (tokens de push)",
    "aws_sqs": "la cola transporta el aviso y la evidencia antes de persistirlos",
    "aws_sesv2": "entrega el aviso por correo",
    "aws_iot": "los mensajes del gabinete pasan por aquí",
    "aws_lambda": "procesa vídeo de CCTV, que puede contener personas",
    "aws_ecr": "las imágenes traen el código que trata los datos (no los datos)",
    "aws_secretsmanager": "guarda las credenciales con las que se accede a los datos",
    "aws_kms": "las llaves con las que se cifran",
    "aws_cloudwatch": "los registros pueden contener identificadores",
    "aws_dynamodb": "estado del despliegue y candados de terraform",
}

#: …y los que NO, con su razón. El censo exige que la unión de los dos mapas sea
#: EXACTAMENTE el conjunto de servicios que terraform usa.
AWS_SIN_DATOS: dict[str, str] = {
    "aws_acm": "certificados TLS de los dominios: criptografía, no datos de personas",
    "aws_budgets": "alertas de gasto de la cuenta de AWS, sin dato de personas",
    "aws_cloudfront": "distribuye los estáticos de la consola (JS y CSS), no datos",
    "aws_eip": "una dirección IP fija de la infraestructura, no de una persona",
    "aws_iam": "permisos de máquinas y roles de servicio, no de personas usuarias",
    "aws_internet": "puerta de enlace a internet de la red privada",
    "aws_network": "listas de control de acceso de la red: reglas de puertos y rangos",
    "aws_route": "tablas de enrutamiento de la red privada",
    "aws_route53": "resuelve los nombres de dominio de la plataforma",
    "aws_security": "grupos de seguridad: qué puertos se abren y desde dónde",
    "aws_ssm": "parámetros de despliegue y acceso remoto a la instancia",
    "aws_subnet": "segmentos de la red privada del despliegue",
    "aws_vpc": "la red privada donde corre el despliegue",
}


def encargados() -> tuple[Encargado, ...]:
    """Todos los encargados declarados, en orden estable."""
    return tuple(sorted([*POR_PROVEEDOR.values(), *FUERA_DEL_CENSO], key=lambda e: e.key))


def transferencias_internacionales() -> tuple[Encargado, ...]:
    """Los que tratan fuera de México **y se sabe dónde**.

    El país desconocido NO entra: contarlo aquí afirmaría una transferencia que
    nadie ha comprobado, y este documento existe precisamente para no afirmar de
    más. Sale por `pais_sin_determinar()`, que es otra cosa y se dice aparte.
    """
    return tuple(
        e for e in encargados() if e.pais != PAIS_PROPIO and not e.pais.startswith(PAIS_DESCONOCIDO)
    )


def pais_sin_determinar() -> tuple[Encargado, ...]:
    """Aquellos cuyo país lo decide el cliente al configurarlos."""
    return tuple(e for e in encargados() if e.pais.startswith(PAIS_DESCONOCIDO))
