"""T-2.78.a · La cadena de OPERACIÓN: sobre de SNS, credencial de guardia y silencio.

CloudWatch → SNS → correo **no dejaba una sola fila en TAKAB**, y AWS tampoco la
da: el registro de estado de entrega de SNS soporta Firehose, SQS, Lambda, HTTPS
y endpoints de aplicación — **``email`` y ``email-json`` no están en la lista**
(https://docs.aws.amazon.com/sns/latest/dg/sns-topic-attributes.html). Así que
"publicado" era todo lo que se podía afirmar y "leído por una persona" no se
podía afirmar jamás. `T-2.78` se puede acreditar una vez a mano; como régimen
permanente, no.

Este módulo es la mitad PURA del arreglo: canonizar y verificar el sobre de SNS,
decidir a qué URL se puede salir, leer los hechos de una alarma de CloudWatch,
acuñar y comprobar la credencial de guardia, y declarar el silencio. La mitad
sucia —el endpoint público y la escritura— vive en ``routers/ops_alerts.py``.

──────────────────────────────────────────────────────────────────────────────
POR QUÉ HTTPS Y NO LAMBDA
──────────────────────────────────────────────────────────────────────────────
La ficha permite las dos. Se eligió HTTPS por una razón y se paga un precio que
está abajo con nombre:

* **La razón.** Lo que hace útil a esta ficha no es "quede un log en algún
  sitio": es que *el tiempo hasta el acuse sea consultable* y que *el silencio
  deje fila*. Eso es una escritura en la base de TAKAB. La API ya tiene la base
  delante y ya tiene —desde `T-2.77.b`— una superficie pública probada con su
  disciplina escrita. Una Lambda tendría que llegar a una base que vive en una
  EC2 con su grupo de seguridad, o cruzar de vuelta por la API: en el primer
  caso son VPC + secreto + un segundo dueño del esquema; en el segundo, la
  Lambda es un reenviador y el endpoint público sigue existiendo igual. Se
  añadiría un runtime, un artefacto de despliegue y un segundo sitio donde el
  aviso se puede perder, para acabar en el mismo endpoint.
* **El precio.** Un endpoint HTTPS suscrito a SNS **es una SSRF esperando**, y
  eso se trata aquí abajo.

──────────────────────────────────────────────────────────────────────────────
LAS DOS URLs DEL CUERPO · la SSRF, y cómo se cierra
──────────────────────────────────────────────────────────────────────────────
En el sobre llegan dos URLs que un suscriptor ingenuo visita, **y las dos las
elige quien manda el cuerpo**. Si el servidor las sigue, cualquiera que descubra
la ruta consigue que pidamos lo que él quiera **desde dentro de la VPC** — que
es exactamente cómo se leen credenciales de instancia en ``169.254.169.254``.

1. **``SubscribeURL``** — la que hay que "visitar" para confirmar el alta.
   **Aquí no se visita NUNCA.** La confirmación se reconstruye con
   ``confirm_subscription_url()``: host y ``TopicArn`` salen de NUESTRA
   configuración y del cuerpo se toma **solo el ``Token`` opaco**. Sigue
   entrando en el texto canónico (AWS lo firma), pero como *dato firmado*, no
   como destino.
2. **``SigningCertURL``** — hay que descargarla para verificar la firma, y no
   hay forma de evitarlo: la firma de SNS **no es un HMAC con un secreto
   nuestro**, es RSA sobre un texto canónico con un certificado de AWS. Se
   descarga solo si pasa ``signing_cert_url_ok()``, que exige: ``https``, host
   **exactamente** ``sns.<región del topic>.amazonaws.com`` (sin credenciales de
   usuario, sin puerto), ruta con la forma canónica
   ``/SimpleNotificationService-<hex>.pem`` y **ni query ni fragmento**. Todo lo
   demás se rechaza **antes de abrir un socket**.

La región no se acepta del cuerpo: se deriva del ARN del topic configurado. Un
sobre de otro topic ni siquiera llega a esta puerta.

Y hay UNA sola salida a la red en todo el subsistema (``fetch_url``), a
propósito: es lo que permite que un test la sustituya por un arnés que revienta
ante cualquier host ajeno y **cuente** las salidas — que es como se mide que la
puerta cerró en vez de suponerlo.

──────────────────────────────────────────────────────────────────────────────
QUIÉN PUEDE ACUSAR · por qué no es Cognito+MFA y por qué no es un enlace pelado
──────────────────────────────────────────────────────────────────────────────
La persona de guardia recibe **un correo** a las tres de la mañana y no tiene una
sesión de consola abierta. Un acuse que exija abrir la consola y pasar MFA es un
acuse que no se va a dar, y entonces la métrica no mide atención: mide fricción.
Un enlace que cualquiera pueda pulsar no acredita nada — y peor: los escáneres
de seguridad de los buzones **pulsan los enlaces de los correos**, así que un
acuse por ``GET`` lo fabricaría una máquina antes de que nadie lo leyera.

Lo elegido: **una credencial personal de guardia**, un secreto de 256 bits
acuñado una vez (``new_ack_token``), del que la base guarda **solo el hash**
(``hash_ack_token``), con caducidad y revocación por fila. Se acusa con un
``POST`` —nunca un ``GET``— desde una página mínima que el gestor de contraseñas
del teléfono rellena sola.

Fuerza real, dicha sin adornos: **equivale a poder leer el buzón de guardia**,
que es el mismo listón que ya tiene cualquiera que reciba la alarma. Lo que
añade sobre el buzón es lo que hace acreditable el acuse: es **de una persona
nombrada**, se **revoca sin tocar el buzón** y **caduca sola**.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_pem_x509_certificate

logger = logging.getLogger("takab_api.ops")

TYPE_NOTIFICATION = "Notification"
TYPE_SUBSCRIPTION_CONFIRMATION = "SubscriptionConfirmation"
TYPE_UNSUBSCRIBE_CONFIRMATION = "UnsubscribeConfirmation"

#: Campos que entran en el texto canónico, EN ESTE ORDEN, por tipo de mensaje.
#: (https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html)
#: ``Subject`` es opcional y solo entra si viene; los demás son obligatorios y su
#: ausencia invalida el sobre — no se "rellena con vacío", que sería aceptar un
#: sobre incompleto como si estuviera firmado.
_CANONICOS: dict[str, tuple[str, ...]] = {
    TYPE_NOTIFICATION: ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"),
    TYPE_SUBSCRIPTION_CONFIRMATION: (
        "Message",
        "MessageId",
        "SubscribeURL",
        "Timestamp",
        "Token",
        "TopicArn",
        "Type",
    ),
    TYPE_UNSUBSCRIBE_CONFIRMATION: (
        "Message",
        "MessageId",
        "SubscribeURL",
        "Timestamp",
        "Token",
        "TopicArn",
        "Type",
    ),
}
_OPCIONALES = frozenset({"Subject"})

#: La ruta del certificado de SNS tiene forma canónica. Acotarla —además del
#: host— es lo que impide que un ``..`` o una query conviertan un host permitido
#: en un proxy hacia otro sitio.
_RUTA_CERT = re.compile(r"^/SimpleNotificationService-[A-Za-z0-9]{8,80}\.pem$")

#: Región de un ARN de SNS: ``arn:aws:sns:<region>:<cuenta>:<nombre>``.
_ARN = re.compile(r"^arn:aws[a-z-]*:sns:([a-z0-9-]{1,32}):(\d{12}):([A-Za-z0-9_-]{1,256})$")

#: Estados de alarma que EXIGEN que alguien conteste. ``OK`` e
#: ``INSUFFICIENT_DATA`` se registran igual —son la evidencia de que el topic
#: entrega y de que la alarma sabe volver— pero no abren un plazo: pedir acuse de
#: cada vuelta a la normalidad llenaría la métrica de silencios que no son el
#: fallo de nadie, y una métrica con ruido se deja de mirar.
ESTADOS_QUE_PIDEN_ACUSE = frozenset({"ALARM"})

#: Tope de lo que nos dejamos descargar de un certificado (uno de SNS son ~1,5 KB).
MAX_CERT_BYTES = 64 * 1024

_cert_cache: dict[str, bytes] = {}


# =============================================================================
# LA ÚNICA SALIDA A LA RED
# =============================================================================


async def fetch_url(url: str, *, timeout_s: float) -> bytes:
    """GET acotado. **Es la única salida a la red de este subsistema.**

    No valida nada: quien llama ya decidió que esa URL es admisible. Vive
    separada por eso mismo — para que un test la sustituya por un arnés que
    cuente y rechace, y el candado se mida en vez de razonarse.
    """
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=False) as cliente:
        respuesta = await cliente.get(url)
        respuesta.raise_for_status()
        return respuesta.content[:MAX_CERT_BYTES]


def reset_cert_cache() -> None:
    """Vacía la caché de certificados (rotación manual y tests)."""
    _cert_cache.clear()


# =============================================================================
# LAS PUERTAS
# =============================================================================


def region_of_topic(topic_arn: str) -> str:
    """Región del ARN del topic, o cadena vacía si no es un ARN de SNS.

    Es lo que fija la región de las DOS salidas a la red. Sale de NUESTRA
    configuración a propósito: si se leyera del cuerpo, quien llama elegiría el
    host permitido y la puerta de abajo no cerraría nada.
    """
    m = _ARN.match((topic_arn or "").strip())
    return m.group(1) if m else ""


def sns_host(region: str) -> str:
    return f"sns.{region}.amazonaws.com"


def signing_cert_url_ok(url: str, *, region: str) -> bool:
    """¿Se puede descargar ese ``SigningCertURL`` sin convertirnos en un proxy?

    Fail-closed en todo: sin región no hay host esperado y no se sale a ningún
    sitio. Se comprueba el ``hostname`` (no el ``netloc``), que es lo que
    descarta ``https://sns.<region>.amazonaws.com@evil.mx/...`` — un netloc que
    *empieza* por el host bueno y apunta a otra parte.
    """
    if not url or not region:
        return False
    try:
        partes = urlsplit(url)
    except ValueError:
        return False
    if partes.scheme != "https":
        return False
    if partes.username or partes.password:
        return False
    try:
        if partes.port is not None:
            return False
    except ValueError:
        return False
    if (partes.hostname or "") != sns_host(region):
        return False
    if partes.query or partes.fragment:
        return False
    return bool(_RUTA_CERT.match(partes.path))


def confirm_subscription_url(*, topic_arn: str, token: str) -> str:
    """La confirmación del alta, **reconstruida por nosotros**.

    Ni una pieza del ``SubscribeURL`` que llegó en el cuerpo: el host sale de la
    región del topic configurado, el ``TopicArn`` sale de esa misma
    configuración, y del cuerpo se toma **solo el ``Token``**, que es un opaco y
    va porcentaje-codificado. ``ConfirmSubscription`` se puede llamar sin firmar
    —es lo que hace un navegador al pulsar el enlace del correo—, así que esto no
    pide ningún permiso IAM nuevo ni ata este módulo a un rol.
    """
    region = region_of_topic(topic_arn)
    if not region or not token:
        return ""
    return (
        f"https://{sns_host(region)}/?Action=ConfirmSubscription"
        f"&TopicArn={quote(topic_arn, safe='')}&Token={quote(token, safe='')}"
    )


# =============================================================================
# EL SOBRE
# =============================================================================


def canonical_string(msg: Mapping[str, object]) -> bytes | None:
    """El texto que AWS firmó, o ``None`` si el sobre no da para construirlo.

    ``None`` y no una excepción: quien decide qué contestar —y qué NO contar— es
    el router, en un solo sitio, igual que en ``notify/callbacks.py``.
    """
    tipo = str(msg.get("Type") or "")
    campos = _CANONICOS.get(tipo)
    if campos is None:
        return None
    trozos: list[str] = []
    for campo in campos:
        valor = msg.get(campo)
        if valor is None:
            if campo in _OPCIONALES:
                continue
            return None
        if not isinstance(valor, str):
            return None
        trozos.append(f"{campo}\n{valor}\n")
    return "".join(trozos).encode("utf-8")


def verify_sns_signature(msg: Mapping[str, object], *, cert_pem: bytes) -> bool:
    """¿La ``Signature`` del sobre corresponde al texto canónico y a ese cert?

    No es un HMAC: es RSA-PKCS#1 v1.5 sobre el canónico. ``SignatureVersion``
    ``1`` ⇒ SHA-1 y ``2`` ⇒ SHA-256, que son las dos que AWS emite; cualquier
    otra cosa se rechaza en vez de adivinarse. Devuelve booleano y no levanta.
    """
    version = str(msg.get("SignatureVersion") or "")
    if version == "1":
        algoritmo: hashes.HashAlgorithm = hashes.SHA1()  # noqa: S303 — lo fija AWS, no nosotros
    elif version == "2":
        algoritmo = hashes.SHA256()
    else:
        return False

    canonico = canonical_string(msg)
    if canonico is None:
        return False
    firma_b64 = msg.get("Signature")
    if not isinstance(firma_b64, str) or not firma_b64:
        return False
    try:
        firma = base64.b64decode(firma_b64, validate=True)
    except (binascii.Error, ValueError):
        return False

    try:
        certificado = load_pem_x509_certificate(cert_pem)
        certificado.public_key().verify(firma, canonico, padding.PKCS1v15(), algoritmo)
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


async def signing_cert(url: str, *, timeout_s: float) -> bytes | None:
    """Certificado de firma, cacheado. Quien llama YA validó la URL."""
    cacheado = _cert_cache.get(url)
    if cacheado is not None:
        return cacheado
    try:
        pem = await fetch_url(url, timeout_s=timeout_s)
    except (httpx.HTTPError, OSError):
        logger.warning("ops[sns]: no se pudo descargar el certificado de firma", exc_info=True)
        return None
    if b"BEGIN CERTIFICATE" not in pem:
        return None
    _cert_cache[url] = pem
    return pem


# =============================================================================
# LOS HECHOS DE UNA ALARMA
# =============================================================================


@dataclass(frozen=True)
class AlarmFacts:
    """Lo que se puede afirmar del cuerpo de un mensaje de CloudWatch.

    Defensivo a propósito: por el mismo topic puede entrar cualquier cosa, y un
    cuerpo firmado pero deforme se registra igual —el hecho *"el topic entregó a
    las 03:14"* vale por sí solo— en vez de reventar. Un 500 aquí sería un
    denegado de servicio de un campo.
    """

    alarm_name: str = ""
    state: str = ""
    reason: str = ""

    @property
    def requires_ack(self) -> bool:
        return self.state in ESTADOS_QUE_PIDEN_ACUSE


def alarm_facts(message: object) -> AlarmFacts:
    """``Message`` de una alarma de CloudWatch ⇒ sus hechos (o vacíos)."""
    if not isinstance(message, str):
        return AlarmFacts()
    try:
        cuerpo = json.loads(message)
    except ValueError:
        return AlarmFacts()
    if not isinstance(cuerpo, dict):
        return AlarmFacts()
    return AlarmFacts(
        alarm_name=str(cuerpo.get("AlarmName") or "")[:200],
        state=str(cuerpo.get("NewStateValue") or "")[:32],
        reason=str(cuerpo.get("NewStateReason") or "")[:2000],
    )


# =============================================================================
# LA CREDENCIAL DE GUARDIA
# =============================================================================


def new_ack_token() -> str:
    """Secreto personal de guardia: 256 bits de entropía, url-safe.

    Se enseña UNA vez —al acuñarlo— y la base solo guarda su hash. Que sea
    largo no es cosmético: es lo que hace que la superficie pública de acuse no
    se pueda adivinar a fuerza de intentos, que es la razón por la que no lleva
    limitador de tasa propio.
    """
    return secrets.token_urlsafe(32)


def hash_ack_token(secreto: str) -> str:
    """SHA-256 hex del secreto. Es lo ÚNICO que viaja a la base.

    No es un HMAC con pimienta ni un KDF con sal, y la razón está escrita para
    que nadie lo "arregle" a medias: el material es un secreto de 256 bits
    generado por la máquina, no una contraseña humana. Contra un hash de eso no
    hay diccionario ni tabla que valga, así que un KDF lento solo añadiría coste
    a cada acuse a las tres de la mañana. La búsqueda va por igualdad del hash:
    para falsificarla haría falta una preimagen, no un prefijo — que es por lo
    que aquí no hay un problema de temporización que resolver.
    """
    return hashlib.sha256(secreto.encode("utf-8")).hexdigest()


# =============================================================================
# EL SILENCIO
# =============================================================================

_SWEEP_SQL = """
UPDATE ops_alert_notices
   SET unacked_at = now()
 WHERE requires_ack
   AND acked_at IS NULL
   AND unacked_at IS NULL
   AND ack_deadline_at IS NOT NULL
   AND now() > ack_deadline_at
"""


def sweep_unacked(conn) -> int:
    """Estampa el instante en que un aviso sin contestar pasa a fallo declarado.

    **Qué NO hace esto: escribir la fila del que no contestó.** Esa fila ya
    existe — la escribió la máquina que recibió el aviso, en el instante del
    aviso, y **nace sin acuse** con su plazo puesto. Nadie iba a llamar a un
    endpoint para decir "no contesté".

    Lo que añade el barrido es la HORA en que el silencio dejó de ser espera:
    ``unacked_at``. Sirve para dos cosas que una cuenta al vuelo no da — es
    donde engancha el salto 2 del escalamiento, y **no se mueve** aunque después
    alguien cambie el plazo de acuse en la configuración.

    Es idempotente (``unacked_at IS NULL``) y **jamás toca ``acked_at``**: un
    barrido no puede convertir un silencio en atención, ni al revés. Devuelve
    cuántos avisos declaró.
    """
    with conn.cursor() as cur:
        cur.execute(_SWEEP_SQL)
        return cur.rowcount or 0
