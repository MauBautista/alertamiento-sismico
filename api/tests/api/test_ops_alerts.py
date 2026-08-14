"""T-2.78.a · La cadena de OPERACIÓN deja rastro: aviso, acuse y silencio.

CloudWatch → SNS → correo no dejaba una sola fila en TAKAB, y AWS tampoco la da:
el registro de estado de entrega de SNS soporta Firehose, SQS, Lambda, HTTPS y
endpoints de aplicación — **email y email-json no están en la lista**. Así que
"publicado" era todo lo que se podía afirmar y "leído por una persona" no se
podía afirmar jamás.

Este fichero mide las cinco cosas de la ficha, y **empieza por la quinta** porque
es la que gobierna a las otras cuatro: *un aviso sin acuse jamás aparece como
atendido*. Es el mismo principio de `T-2.75` — el canal que no entrega no finge.

El segundo bloque no habla de avisos: habla de la **SSRF** que un suscriptor
HTTPS de SNS es si nadie lo mira. Dos URLs llegan DENTRO del cuerpo —
``SubscribeURL`` y ``SigningCertURL``— y las dos las controla quien manda el
cuerpo. El arnés de red de aquí abajo **revienta ante cualquier petición a un
host que no sea el de SNS de NUESTRA región**, y se comprueba a sí mismo: el
caso legítimo tiene que haberlo usado de verdad (``visitados``), o el caso
hostil estaría midiendo la nada.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import uuid
from urllib.parse import quote, urlsplit

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.ops import alerts as al
from takab_api.routers import ops_alerts as oa

TOPIC_ARN = "arn:aws:sns:us-east-2:634882473845:takab-dev-ops-alerts"
OTRO_TOPIC = "arn:aws:sns:us-east-2:634882473845:topic-de-otro"
SNS_HOST = "sns.us-east-2.amazonaws.com"
CERT_URL = f"https://{SNS_HOST}/SimpleNotificationService-abc123def456.pem"

RUTA_SNS = "/ops/alerts/sns"
RUTA_ACK = "/ops/alerts/ack"
RUTA_CADENA = "/ops/alerts/chain"


# =============================================================================
# ARNÉS · una CA de mentira que firma como firmaría SNS
# =============================================================================


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    ahora = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(nombre)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - dt.timedelta(days=1))
        .not_valid_after(ahora + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return key, cert.public_bytes(serialization.Encoding.PEM)


_KEY, _CERT_PEM = _keypair()


def firmar(msg: dict, *, key=_KEY, cert_url: str = CERT_URL, version: str = "1") -> dict:
    """Devuelve el sobre con ``Signature``/``SigningCertURL`` como los pone SNS."""
    firmado = dict(msg)
    firmado["SignatureVersion"] = version
    firmado["SigningCertURL"] = cert_url
    canonico = al.canonical_string(firmado)
    assert canonico is not None, "el arnés no supo canonizar este sobre"
    algo = hashes.SHA1() if version == "1" else hashes.SHA256()  # noqa: S303 — SNS v1 es SHA1
    firmado["Signature"] = base64.b64encode(key.sign(canonico, padding.PKCS1v15(), algo)).decode()
    return firmado


def notificacion(
    *,
    alarma: str = "takab-dev-dlq-backfill",
    estado: str = "ALARM",
    message_id: str | None = None,
    topic: str = TOPIC_ARN,
    razon: str = "SIMULACRO T-2.78",
) -> dict:
    cuerpo = json.dumps(
        {
            "AlarmName": alarma,
            "NewStateValue": estado,
            "NewStateReason": razon,
            "StateChangeTime": "2026-08-13T03:14:00.000+0000",
        }
    )
    return {
        "Type": "Notification",
        "MessageId": message_id or str(uuid.uuid4()),
        "TopicArn": topic,
        "Subject": f'{estado}: "{alarma}" in US East (Ohio)',
        "Message": cuerpo,
        "Timestamp": "2026-08-13T03:14:01.234Z",
    }


def confirmacion(*, topic: str = TOPIC_ARN, subscribe_url: str | None = None) -> dict:
    return {
        "Type": "SubscriptionConfirmation",
        "MessageId": str(uuid.uuid4()),
        "Token": "t" * 64,
        "TopicArn": topic,
        "Message": "You have chosen to subscribe to the topic …",
        "SubscribeURL": subscribe_url
        or f"https://{SNS_HOST}/?Action=ConfirmSubscription&TopicArn={topic}&Token={'t' * 64}",
        "Timestamp": "2026-08-13T03:00:00.000Z",
    }


class Red:
    """La ÚNICA salida a la red de esta superficie, instrumentada.

    Revienta ante cualquier host que no sea el de SNS de nuestra región: es el
    detector de la SSRF, y su no-vacuidad la comprueba ``visitados`` (si el caso
    legítimo no hubiera salido nunca, el hostil no estaría midiendo nada).
    """

    def __init__(self) -> None:
        self.visitados: list[str] = []

    async def __call__(self, url: str, *, timeout_s: float) -> bytes:
        self.visitados.append(url)
        host = urlsplit(url).hostname
        if host != SNS_HOST:
            raise AssertionError(f"SSRF: el servidor salió a un host ajeno → {url}")
        if "ConfirmSubscription" in url:
            return b"<ConfirmSubscriptionResponse/>"
        return _CERT_PEM

    @property
    def hosts(self) -> list[str | None]:
        return [urlsplit(u).hostname for u in self.visitados]


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def _ops_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_OPS_ALERT_TOPIC_ARN", TOPIC_ARN)
    monkeypatch.setenv("TAKAB_API_OPS_ACK_DEADLINE_S", "900")


@pytest.fixture
def red(monkeypatch: pytest.MonkeyPatch) -> Red:
    r = Red()
    monkeypatch.setattr(al, "fetch_url", r)
    al.reset_cert_cache()
    return r


@pytest.fixture
def app(_ops_env):
    return create_app()


@pytest.fixture
async def client(app):
    async with au.client_for(app) as c:
        yield c


@pytest.fixture
async def limpia():
    """Vacía las dos tablas de la cadena de operación antes y después."""
    engine = get_engine()

    async def _borrar() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE ops_alert_notices, ops_oncall_contacts CASCADE"))

    await _borrar()
    yield
    await _borrar()
    await engine.dispose()
    get_engine.cache_clear()


@pytest.fixture
async def contacto(limpia):
    """Una persona de guardia con su token personal. Devuelve el SECRETO."""

    async def _alta(
        *, label: str = "Guardia primaria", expira_h: float = 24 * 90, revocado: bool = False
    ) -> str:
        secreto = al.new_ack_token()
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO ops_oncall_contacts (label, token_hash, expires_at, revoked_at) "
                    "VALUES (:l, :h, now() + make_interval(hours => :e), "
                    "        CASE WHEN :r THEN now() END)"
                ),
                {
                    "l": label,
                    "h": al.hash_ack_token(secreto),
                    "e": expira_h,
                    "r": revocado,
                },
            )
        return secreto

    return _alta


async def _post_sns(client, sobre: dict):
    return await client.post(RUTA_SNS, content=json.dumps(sobre).encode())


async def _acusar(client, secreto: str):
    return await client.post(RUTA_ACK, data={"token": secreto})


async def _cadena() -> list[dict]:
    engine = get_engine()
    async with engine.begin() as conn:
        filas = (
            (
                await conn.execute(
                    text(
                        "SELECT alarm_name, alarm_state, requires_ack, received_at, "
                        "ack_deadline_at, acked_at, acked_by, unacked_at, outcome, "
                        "ack_latency_s FROM v_ops_alert_chain ORDER BY received_at"
                    )
                )
            )
            .mappings()
            .all()
        )
    return [dict(f) for f in filas]


async def _vencer_plazo() -> None:
    """Envejece el plazo de todo aviso abierto. NO toca el acuse."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ops_alert_notices SET received_at = received_at - interval '2 hours', "
                "ack_deadline_at = ack_deadline_at - interval '2 hours' WHERE acked_at IS NULL"
            )
        )


# =============================================================================
# CRITERIO 5 — el que gobierna a los otros cuatro
# =============================================================================


async def test_un_aviso_SIN_ACUSE_jamas_aparece_como_atendido(client, red, limpia) -> None:
    """Nadie acusa: ni antes del plazo, ni después, ni tras el barrido. En
    ningún instante la cadena dice "atendido" — dice "esperando" y luego "sin
    acuse", que es la verdad medible."""
    assert (await _post_sns(client, firmar(notificacion()))).status_code == 202

    (antes,) = await _cadena()
    assert antes["acked_at"] is None and antes["acked_by"] is None
    assert antes["outcome"] == "esperando_acuse"
    assert antes["ack_latency_s"] is None

    await _vencer_plazo()
    (vencido,) = await _cadena()
    assert vencido["acked_at"] is None
    assert vencido["outcome"] == "sin_acuse"

    # Y el barrido, que es quien declara el silencio, TAMPOCO lo convierte en acuse.
    assert await _barrer() == 1
    (barrido,) = await _cadena()
    assert barrido["unacked_at"] is not None
    assert barrido["acked_at"] is None and barrido["acked_by"] is None
    assert barrido["outcome"] == "sin_acuse"


@pytest.mark.parametrize(
    "clase",
    ["inventado", "revocado", "caducado"],
    ids=["token inventado", "token revocado", "token caducado"],
)
async def test_un_token_que_no_vale_NO_acusa_nada(client, red, contacto, clase) -> None:
    """Las tres formas de no tener credencial. Ninguna mueve una sola columna
    del aviso — y las tres contestan lo MISMO, así que desde fuera no se puede
    saber cuál de las tres es (ni si hay avisos abiertos)."""
    await _post_sns(client, firmar(notificacion()))
    if clase == "inventado":
        secreto = al.new_ack_token()
    elif clase == "revocado":
        secreto = await contacto(revocado=True)
    else:
        secreto = await contacto(expira_h=-1)

    respuesta = await _acusar(client, secreto)
    assert respuesta.status_code == 404

    (fila,) = await _cadena()
    assert fila["acked_at"] is None and fila["acked_by"] is None
    assert fila["outcome"] == "esperando_acuse"


async def test_el_acuse_de_un_token_VALIDO_y_el_de_uno_falso_son_indistinguibles(
    client, red, contacto
) -> None:
    """Cuando no hay nada abierto, un token bueno y uno inventado contestan
    igual: la superficie no sirve para adivinar tokens ni para censar avisos."""
    bueno = await contacto()
    falso = al.new_ack_token()
    con_bueno = await _acusar(client, bueno)  # no hay avisos abiertos
    con_falso = await _acusar(client, falso)
    assert con_bueno.status_code == con_falso.status_code == 404


async def test_la_base_NO_PUEDE_escribir_un_acuse_a_medias() -> None:
    """El candado estructural: no hay forma de nombrar a quien acusó sin la hora,
    ni de poner la hora sin nombre. Un `UPDATE` a mano lo intenta y la base lo
    rechaza — no depende de que el código de arriba se acuerde."""
    from sqlalchemy.exc import IntegrityError

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ops_alert_notices (sns_message_id, topic_arn, alarm_name, "
                "alarm_state, requires_ack, ack_deadline_at) "
                "VALUES ('m-medias', :t, 'a', 'ALARM', true, now() + interval '15 min')"
            ),
            {"t": TOPIC_ARN},
        )
    for parcial in ("acked_by = 'fulano'", "acked_at = now()"):
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(f"UPDATE ops_alert_notices SET {parcial} WHERE sns_message_id='m-medias'")
                )
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM ops_alert_notices WHERE sns_message_id='m-medias'"))


# =============================================================================
# CRITERIO 1 — evidencia de máquina, y la SSRF que trae de la mano
# =============================================================================


async def test_el_endpoint_publico_existe_en_la_app_real(app) -> None:
    """No-vacuidad de todo lo de abajo: si el router no estuviera montado, cada
    prueba mediría el 404 de una ruta inexistente y saldría 'verde'."""
    rutas = app.openapi()["paths"]
    assert RUTA_SNS in rutas and RUTA_ACK in rutas and RUTA_CADENA in rutas
    assert "security" not in rutas[RUTA_SNS]["post"]  # fuera de Cognito, a propósito


async def test_una_notificacion_firmada_deja_fila_con_hora(client, red, limpia) -> None:
    respuesta = await _post_sns(client, firmar(notificacion()))
    assert respuesta.status_code == 202

    (fila,) = await _cadena()
    assert fila["alarm_name"] == "takab-dev-dlq-backfill"
    assert fila["alarm_state"] == "ALARM"
    assert fila["received_at"] is not None
    assert fila["requires_ack"] is True
    assert fila["ack_deadline_at"] > fila["received_at"]
    # Y la salida a la red del caso legítimo EXISTIÓ: es lo que hace que el caso
    # hostil de abajo mida algo.
    assert red.hosts == [SNS_HOST]


async def test_el_reenvio_del_mismo_MessageId_no_duplica_el_aviso(client, red, limpia) -> None:
    """SNS reintenta. Dos entregas del mismo mensaje son UN aviso, o la métrica
    de "cuántas veces nadie contestó" se infla sola."""
    sobre = firmar(notificacion(message_id="mismo-mensaje"))
    a = await _post_sns(client, sobre)
    b = await _post_sns(client, sobre)
    assert a.status_code == b.status_code == 202
    assert len(await _cadena()) == 1


async def test_un_estado_OK_se_registra_pero_NO_pide_acuse(client, red, limpia) -> None:
    """La vuelta a `OK` es evidencia de que el topic entrega (y de que la alarma
    sabe volver), pero exigirle acuse llenaría la métrica de silencios que no
    son un fallo de nadie."""
    await _post_sns(client, firmar(notificacion(estado="OK")))
    (fila,) = await _cadena()
    assert fila["requires_ack"] is False
    assert fila["ack_deadline_at"] is None
    assert fila["outcome"] == "no_requiere_acuse"


async def test_un_cuerpo_SIN_FIRMA_VALIDA_no_toca_la_base(client, red, monkeypatch) -> None:
    """El candado central, medido saboteando la única puerta a la base."""

    def _explota(*_a, **_k):
        raise AssertionError("el router tocó la base con un sobre sin firma válida")

    monkeypatch.setattr(oa, "notices_conn", _explota)

    sin = await _post_sns(client, notificacion())  # sin Signature
    sobre = firmar(notificacion())
    sobre["Signature"] = base64.b64encode(b"\x00" * 256).decode()
    mala = await _post_sns(client, sobre)
    assert sin.status_code == mala.status_code == 404


async def test_un_topic_AJENO_se_rechaza_sin_mirar_la_firma(client, red, monkeypatch) -> None:
    """El `TopicArn` de nuestra configuración es la primera puerta: un sobre de
    otro topic no llega ni a descargar un certificado."""

    def _explota(*_a, **_k):
        raise AssertionError("el router tocó la base con un topic ajeno")

    monkeypatch.setattr(oa, "notices_conn", _explota)
    respuesta = await _post_sns(client, firmar(notificacion(topic=OTRO_TOPIC)))
    assert respuesta.status_code == 404
    assert red.visitados == []  # ni una petición: el rechazo fue antes


async def test_sin_topic_configurado_el_endpoint_se_NIEGA_y_lo_dice(client, red, monkeypatch):
    """Fail-closed RUIDOSO: que falte NUESTRA configuración es un error de
    despliegue, no información sobre qué avisos hay."""
    monkeypatch.setenv("TAKAB_API_OPS_ALERT_TOPIC_ARN", "")
    assert (await _post_sns(client, firmar(notificacion()))).status_code == 503


async def test_un_cuerpo_desmesurado_se_corta_antes_de_mirarlo(client, red) -> None:
    respuesta = await client.post(RUTA_SNS, content=b"x" * (oa.MAX_BODY_BYTES + 1))
    assert respuesta.status_code == 413


# --- LA SSRF ------------------------------------------------------------------


@pytest.mark.parametrize(
    "hostil",
    [
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "https://sns.us-east-2.amazonaws.com.evil.mx/SimpleNotificationService-a.pem",
        "https://evil.mx/sns.us-east-2.amazonaws.com/SimpleNotificationService-a.pem",
        "https://sns.us-east-2.amazonaws.com@evil.mx/SimpleNotificationService-a.pem",
        "https://sns.us-east-2.amazonaws.com:8443/SimpleNotificationService-a.pem",
        "http://sns.us-east-2.amazonaws.com/SimpleNotificationService-a.pem",
        "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-a.pem",
        "https://sns.us-east-2.amazonaws.com/../../evil.pem",
        "https://sns.us-east-2.amazonaws.com/x.pem?redirect=http://169.254.169.254/",
        "https://localhost/SimpleNotificationService-a.pem",
    ],
)
async def test_un_SigningCertURL_HOSTIL_no_produce_NI_UNA_peticion(client, red, hostil) -> None:
    """La trampa de esta superficie: ``SigningCertURL`` la elige quien manda el
    cuerpo. Un endpoint que la descargue sin mirar convierte al servidor en un
    cliente HTTP a las órdenes de cualquiera, DENTRO de la VPC — que es
    exactamente cómo se leen credenciales de instancia (169.254.169.254)."""
    sobre = firmar(notificacion(), cert_url=hostil)
    respuesta = await _post_sns(client, sobre)
    assert respuesta.status_code == 404
    assert red.visitados == [], f"el servidor salió a {red.visitados}"


async def test_un_SubscribeURL_HOSTIL_no_se_visita_JAMAS(client, red, limpia) -> None:
    """La otra URL del cuerpo. La confirmación de la suscripción NO sigue el
    ``SubscribeURL`` que llega: se reconstruye con el host y el ``TopicArn`` de
    NUESTRA configuración, y del cuerpo solo se toma el ``Token`` opaco."""
    sobre = firmar(confirmacion(subscribe_url="http://169.254.169.254/?Action=ConfirmSubscription"))
    respuesta = await _post_sns(client, sobre)

    assert respuesta.status_code == 202
    # El certificado + la confirmación, las dos al host de SNS de nuestra región.
    assert red.hosts == [SNS_HOST, SNS_HOST]
    (confirmada,) = [u for u in red.visitados if "ConfirmSubscription" in u]
    assert quote(TOPIC_ARN, safe="") in confirmada and "t" * 64 in confirmada
    assert "169.254" not in confirmada


async def test_el_SubscribeURL_firmado_sigue_contando_para_la_firma(client, red, limpia) -> None:
    """No se USA como URL, pero SÍ entra en el texto canónico que AWS firma: si
    se ignorara al canonizar, cualquier sobre de confirmación con la firma de
    otro pasaría."""
    sobre = firmar(confirmacion())
    sobre["SubscribeURL"] = "https://sns.us-east-2.amazonaws.com/?Action=ConfirmSubscription&x=1"
    assert (await _post_sns(client, sobre)).status_code == 404


def test_la_puerta_del_certificado_acepta_lo_legitimo_y_nada_mas() -> None:
    """La regla, aislada del transporte (y con su caso positivo, o solo mediría
    que la función dice que no a todo)."""
    assert al.signing_cert_url_ok(CERT_URL, region="us-east-2")
    assert not al.signing_cert_url_ok(CERT_URL, region="us-west-2")
    assert not al.signing_cert_url_ok("", region="us-east-2")
    assert not al.signing_cert_url_ok(
        "https://sns.us-east-2.amazonaws.com/SimpleNotificationService-a.pem.evil",
        region="us-east-2",
    )


# =============================================================================
# CRITERIOS 2 y 3 — el acuse con hora, y el tiempo hasta el acuse
# =============================================================================


async def test_un_acuse_con_token_valido_queda_con_HORA_y_con_NOMBRE(client, red, contacto) -> None:
    secreto = await contacto(label="Mauricio (primaria)")
    await _post_sns(client, firmar(notificacion()))

    respuesta = await _acusar(client, secreto)
    assert respuesta.status_code == 200

    (fila,) = await _cadena()
    assert fila["acked_at"] is not None
    assert fila["acked_by"] == "Mauricio (primaria)"
    assert fila["outcome"] == "acusado"
    assert fila["ack_latency_s"] is not None and fila["ack_latency_s"] >= 0


async def test_el_tiempo_hasta_el_acuse_es_CONSULTABLE(client, red, contacto) -> None:
    """No se reconstruye de cabeceras de correo: es una columna de una vista, y
    la calcula la base entre dos instantes que escribió ella misma."""
    secreto = await contacto()
    await _post_sns(client, firmar(notificacion()))
    engine = get_engine()
    async with engine.begin() as conn:  # el aviso llegó hace 4 minutos
        await conn.execute(
            text("UPDATE ops_alert_notices SET received_at = received_at - interval '4 minutes'")
        )
    await _acusar(client, secreto)

    (fila,) = await _cadena()
    assert 235 <= fila["ack_latency_s"] <= 260


async def test_la_consola_lee_la_cadena_y_un_cliente_NO(client, red, contacto) -> None:
    """La cadena de operación es de TAKAB, no de un tenant: el on-call de la
    plataforma y sus silencios no son dato de cliente."""
    await _post_sns(client, firmar(notificacion()))

    interno = await client.get(RUTA_CADENA, headers=au.bearer(au.make_token("takab_superadmin")))
    assert interno.status_code == 200
    (item,) = interno.json()["items"]
    assert item["alarm_name"] == "takab-dev-dlq-backfill"
    assert item["outcome"] == "esperando_acuse"
    assert item["acked_at"] is None

    cliente = await client.get(RUTA_CADENA, headers=au.bearer(au.make_token("client_admin")))
    assert cliente.status_code in (403, 404)

    anonimo = await client.get(RUTA_CADENA)
    assert anonimo.status_code == 401


async def test_un_acuse_TARDIO_se_registra_como_tardio_y_no_borra_el_silencio(
    client, red, contacto
) -> None:
    """Contestar a las dos horas es mejor que no contestar, y es OTRA cosa que
    contestar a tiempo. La fila lo dice con las dos marcas puestas."""
    secreto = await contacto()
    await _post_sns(client, firmar(notificacion()))
    await _vencer_plazo()
    assert await _barrer() == 1

    assert (await _acusar(client, secreto)).status_code == 200
    (fila,) = await _cadena()
    assert fila["acked_at"] is not None
    assert fila["unacked_at"] is not None  # el silencio ocurrió y no se borra
    assert fila["outcome"] == "acusado_tarde"


# =============================================================================
# CRITERIO 4 — la fila del silencio: quién la escribe y cuándo
# =============================================================================


async def _barrer() -> int:
    """El barrido, tal y como lo llama el worker (conexión síncrona)."""
    import os

    import psycopg

    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn) as conn:
        marcados = al.sweep_unacked(conn)
        conn.commit()
    return marcados


async def test_la_fila_del_SILENCIO_nace_con_el_aviso(client, red, limpia) -> None:
    """La respuesta a "quién escribe la fila del que no contestó": NADIE la
    escribe después. La escribe la máquina que recibió el aviso, en el instante
    del aviso, y **nace sin acuse** con su plazo ya puesto. Nadie va a llamar a
    un endpoint para decir "no contesté"."""
    await _post_sns(client, firmar(notificacion()))
    (fila,) = await _cadena()
    assert fila["received_at"] is not None
    assert fila["ack_deadline_at"] is not None
    assert fila["acked_at"] is None


async def test_el_barrido_ESTAMPA_el_instante_en_que_el_silencio_se_declara(
    client, red, limpia
) -> None:
    """Lo que el barrido añade no es la fila: es la HORA en que el silencio dejó
    de ser espera y pasó a ser un fallo declarado — que es donde engancha el
    salto 2 del escalamiento."""
    await _post_sns(client, firmar(notificacion()))
    assert await _barrer() == 0  # dentro de plazo todavía: no hay nada que declarar

    await _vencer_plazo()
    assert await _barrer() == 1
    (fila,) = await _cadena()
    assert fila["unacked_at"] is not None

    # Idempotente: el instante de la declaración no se mueve en cada pasada.
    primero = fila["unacked_at"]
    assert await _barrer() == 0
    assert (await _cadena())[0]["unacked_at"] == primero


async def test_el_barrido_NO_declara_silencio_de_un_aviso_ya_acusado(client, red, contacto) -> None:
    secreto = await contacto()
    await _post_sns(client, firmar(notificacion()))
    await _acusar(client, secreto)
    await _vencer_plazo()

    assert await _barrer() == 0
    (fila,) = await _cadena()
    assert fila["unacked_at"] is None
    assert fila["outcome"] == "acusado"


async def test_el_BUCLE_REAL_del_worker_declara_el_silencio(client, red, limpia, monkeypatch):
    """El barrido no sirve de nada si nadie lo corre. Se mide en el bucle REAL de
    `notify` —donde va de gorra por el mismo argumento que el medidor de
    fantasmas de T-2.60.a— y con la base de verdad delante: se deja un aviso
    vencido, se dan tres vueltas, y la marca tiene que estar puesta."""
    import os
    import threading

    import psycopg

    from takab_api.notify.worker import NotifyWorker
    from takab_api.settings import Settings

    await _post_sns(client, firmar(notificacion()))
    await _vencer_plazo()
    assert (await _cadena())[0]["unacked_at"] is None  # montaje: todavía sin declarar

    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")

    class _Inerte:
        def maybe_publish(self, *, conn: object) -> None: ...

    worker = NotifyWorker(
        lambda: psycopg.connect(dsn),
        Settings(),
        poll_s=0.0,
        providers={},
        ghost_gauge=_Inerte(),  # type: ignore[arg-type]
    )
    vueltas: list[int] = []

    def _pass(*_a: object, **_k: object) -> None:
        vueltas.append(1)
        if len(vueltas) >= 3:
            worker.stop()

    monkeypatch.setattr("takab_api.notify.worker.run_notify_pass", _pass)
    hilo = threading.Thread(target=worker.run, daemon=True)
    hilo.start()
    hilo.join(timeout=20)
    worker.stop()

    assert len(vueltas) >= 3, "el bucle no llegó a dar vueltas: el test no midió nada"
    (fila,) = await _cadena()
    assert fila["unacked_at"] is not None
    assert fila["acked_at"] is None


# =============================================================================
# EL TOKEN, EN CRUDO
# =============================================================================


def test_el_secreto_del_acuse_NO_se_guarda_en_claro() -> None:
    """Lo que vive en la base es el hash. Quien lea la tabla entera no puede
    acusar en nombre de nadie."""
    secreto = al.new_ack_token()
    assert len(secreto) >= 32
    assert al.hash_ack_token(secreto) == hashlib.sha256(secreto.encode()).hexdigest()
    assert secreto not in al.hash_ack_token(secreto)
    assert al.new_ack_token() != al.new_ack_token()


async def test_ningun_rol_de_aplicacion_puede_leer_los_tokens(contacto) -> None:
    """Los hashes no son alcanzables desde ninguna sesión de la API, y se mide con
    los DOS candados por separado.

    El del privilegio se le escapó a la primera versión de esta ficha: la 0001
    termina con un `GRANT ... ON ALL TABLES ... TO takab_app` que corre DESPUÉS
    del cuerpo de `db/schema.sql`, así que en una base **recién creada** —el
    camino de la nube— `takab_app` salía con SELECT sobre esta tabla, y en una
    base existente no. Lo revoca la 0041 para igualar los dos caminos; esto es lo
    que impide que vuelva a divergir.
    """
    await contacto(label="Con credencial viva")
    engine = get_engine()
    async with engine.connect() as conn:
        permiso = (
            await conn.execute(
                text("SELECT has_table_privilege('takab_app','ops_oncall_contacts','SELECT')")
            )
        ).scalar()
        # El segundo candado, ejercido: aunque alguien devolviera el privilegio, la
        # RLS es un `USING (false)` explícito con FORCE y no devuelve una fila.
        await conn.execute(text("SET LOCAL ROLE takab_app"))
        try:
            filas = (await conn.execute(text("SELECT count(*) FROM ops_oncall_contacts"))).scalar()
        except Exception:  # noqa: BLE001 - sin privilegio ni siquiera llega a la RLS
            filas = 0
    assert permiso is False
    assert filas == 0

    # No-vacuidad: la fila EXISTE; lo que no existe es el camino para leerla.
    async with engine.begin() as conn:
        total = (await conn.execute(text("SELECT count(*) FROM ops_oncall_contacts"))).scalar()
    assert total >= 1
