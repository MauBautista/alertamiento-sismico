"""T-2.77.b · El endpoint PÚBLICO de estado de entrega, contra Postgres real.

Es la única superficie de la API que no va detrás de Cognito: la llaman Twilio y
Meta, que no tienen un token nuestro. **La firma es la única autenticación**, así
que la mitad de este fichero no habla de entregas: habla de qué pasa cuando la
firma no está, no cuadra, o no hay con qué comprobarla.

Lo que se mide, en este orden:

1. que un cuerpo sin firma válida **no toca la base** —ni para buscar el job—,
   medido con la conexión saboteada, no supuesto;
2. que un identificador desconocido y una firma mala son **indistinguibles**
   desde fuera (no se filtra qué jobs hay);
3. que un reenvío es inerte y que un callback fuera de orden no hace retroceder
   nada;
4. y solo entonces, que la entrega se escribe y que un ``failed`` tardío deja el
   job en ROJO en vez de verde para siempre.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.main import create_app
from takab_api.routers import notify_webhooks as nw

TWILIO_TOKEN = "t0k3n-de-twilio-de-mentira"
META_SECRET = "s3cr3t0-de-la-app-de-meta"
META_VERIFY = "verificame-si-puedes"
CALLBACK_URL = "https://takab.example.mx/api/notify/webhooks/twilio"

RUTA_TWILIO = "/notify/webhooks/twilio"
RUTA_META = "/notify/webhooks/meta"


# --- entorno + app -------------------------------------------------------------


@pytest.fixture(autouse=True)
def _webhook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAKAB_API_NOTIFY_SMS_AUTH_TOKEN", TWILIO_TOKEN)
    monkeypatch.setenv("TAKAB_API_NOTIFY_SMS_STATUS_CALLBACK_URL", CALLBACK_URL)
    monkeypatch.setenv("TAKAB_API_NOTIFY_WHATSAPP_APP_SECRET", META_SECRET)
    monkeypatch.setenv("TAKAB_API_NOTIFY_WHATSAPP_VERIFY_TOKEN", META_VERIFY)


@pytest.fixture
def app(_webhook_env):
    """La app REAL. Si el router no estuviera montado en ``create_app``, todo
    esto daría 404 y el endpoint no existiría en producción."""
    return create_app()


@pytest.fixture
async def client(app):
    async with au.client_for(app) as c:
        yield c


# --- firmas --------------------------------------------------------------------


def firma_twilio(params: dict[str, str], *, url: str = CALLBACK_URL, token: str = TWILIO_TOKEN):
    material = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), material.encode(), hashlib.sha1).digest())


def post_twilio(client, params: dict[str, str], *, firma: bytes | str | None = "auto"):
    cuerpo = "&".join(f"{k}={v}" for k, v in params.items())
    cabeceras = {"Content-Type": "application/x-www-form-urlencoded"}
    if firma == "auto":
        firma = firma_twilio(params)
    if firma is not None:
        cabeceras["X-Twilio-Signature"] = firma.decode() if isinstance(firma, bytes) else firma
    return client.post(RUTA_TWILIO, content=cuerpo, headers=cabeceras)


def cuerpo_meta(message_id: str, status: str, *, ts: int = 2_020_000_000) -> bytes:
    return json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "statuses": [
                                    {"id": message_id, "status": status, "timestamp": str(ts)}
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    ).encode()


def post_meta(client, cuerpo: bytes, *, secreto: str | None = META_SECRET):
    cabeceras = {"Content-Type": "application/json"}
    if secreto is not None:
        cabeceras["X-Hub-Signature-256"] = (
            "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
        )
    return client.post(RUTA_META, content=cuerpo, headers=cabeceras)


# --- el job del que hablan los callbacks ---------------------------------------


@pytest.fixture
def make_job(make_incident):
    """Un job ya ``sent`` con su identificador de proveedor persistido.

    Es el estado en el que T-2.77.b encuentra las cosas: el proveedor aceptó el
    mensaje, el job está verde y NADIE sabe todavía si llegó a un teléfono.
    """

    async def _make(*, channel: str = "sms", message_id: str, status: str = "sent") -> dict:
        incidente = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
        job_id = str(uuid.uuid4())
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO notification_jobs (job_id, tenant_id, incident_id, channel, "
                    "mode, position, status, target, due_at, sent_at, provider_message_id) "
                    "VALUES (:j, :t, :i, :c, 'cascade', 1, :st, '{}'::jsonb, now(), now(), :m)"
                ),
                {
                    "j": job_id,
                    "t": au.DB_TENANT_PRIV,
                    "i": incidente,
                    "c": channel,
                    "st": status,
                    "m": message_id,
                },
            )
        return {"job_id": job_id, "incident_id": incidente}

    return _make


async def leer_job(job_id: str) -> dict:
    engine = get_engine()
    async with engine.begin() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT status, sent_at, delivered_at, last_status, last_status_at, error "
                        "FROM notification_jobs WHERE job_id = CAST(:j AS uuid)"
                    ),
                    {"j": job_id},
                )
            )
            .mappings()
            .first()
        )
    return dict(row) if row else {}


async def acciones(incident_id: str, kind: str) -> list[dict]:
    engine = get_engine()
    async with engine.begin() as conn:
        rows = (
            (
                await conn.execute(
                    text(
                        "SELECT actor, payload FROM incident_actions "
                        "WHERE incident_id = CAST(:i AS uuid) AND kind = :k ORDER BY ts"
                    ),
                    {"i": incident_id, "k": kind},
                )
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]


# =============================================================================
# LA SEGURIDAD DE LA SUPERFICIE PÚBLICA
# =============================================================================


async def test_el_endpoint_publico_existe_en_la_app_real(app) -> None:
    """No-vacuidad de todo lo demás: si el router no estuviera montado, cada
    prueba de abajo mediría un 404 de ruta inexistente y saldría 'verde'."""
    # Por el contrato publicado y no por `app.routes`: FastAPI envuelve los
    # routers incluidos (`_IncludedRouter`) y esa lista no trae las rutas de
    # dentro — un `in` contra ella saldría falso incluso con el router montado.
    rutas = app.openapi()["paths"]
    assert RUTA_TWILIO in rutas
    assert RUTA_META in rutas
    # Y sin `security`: esta es la superficie que NO va detrás de Cognito.
    assert "security" not in rutas[RUTA_TWILIO]["post"]


async def test_un_cuerpo_SIN_FIRMA_no_toca_la_base(client, monkeypatch, make_job) -> None:
    """El candado central: sin firma válida no se abre una conexión ni para
    BUSCAR el job. Se mide saboteando la única puerta a la base — si el router la
    tocara, esto reventaría con el error de abajo en vez de contestar."""
    job = await make_job(message_id="SM" + "1" * 32)

    def _explota(*_a, **_k):
        raise AssertionError("el router tocó la base con un cuerpo sin firma válida")

    monkeypatch.setattr(nw, "delivery_conn", _explota)

    sin = await post_twilio(
        client, {"MessageSid": "SM" + "1" * 32, "MessageStatus": "delivered"}, firma=None
    )
    mala = await post_twilio(
        client,
        {"MessageSid": "SM" + "1" * 32, "MessageStatus": "delivered"},
        firma="AAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    )
    assert sin.status_code == 404
    assert mala.status_code == 404

    monkeypatch.undo()
    assert (await leer_job(job["job_id"]))["delivered_at"] is None


async def test_meta_sin_firma_valida_tampoco_toca_la_base(client, monkeypatch) -> None:
    def _explota(*_a, **_k):
        raise AssertionError("el router tocó la base con un cuerpo sin firma válida")

    monkeypatch.setattr(nw, "delivery_conn", _explota)
    cuerpo = cuerpo_meta("wamid.X", "delivered")
    assert (await post_meta(client, cuerpo, secreto=None)).status_code == 404
    assert (await post_meta(client, cuerpo, secreto="otro-secreto")).status_code == 404


async def test_la_firma_mala_y_el_id_desconocido_son_INDISTINGUIBLES(client) -> None:
    """No se filtra qué jobs hay. Un atacante con una firma inválida y otro con
    una firma válida sobre un identificador inventado reciben lo MISMO: mismo
    código y mismo cuerpo, byte a byte."""
    params = {"MessageSid": "SM" + "9" * 32, "MessageStatus": "delivered"}
    firmada_pero_desconocida = await post_twilio(client, params)
    sin_firmar = await post_twilio(client, params, firma=None)

    assert firmada_pero_desconocida.status_code == sin_firmar.status_code == 404
    assert firmada_pero_desconocida.json() == sin_firmar.json()


async def test_una_firma_capturada_en_OTRA_url_no_vale(client, make_job) -> None:
    """La URL entra en el material firmado y sale de la CONFIGURACIÓN, no de las
    cabeceras: si se reconstruyera con Host/X-Forwarded-*, quien llama
    controlaría parte de lo firmado."""
    sid = "SM" + "2" * 32
    job = await make_job(message_id=sid)
    params = {"MessageSid": sid, "MessageStatus": "delivered"}
    otra = firma_twilio(params, url="https://impostor.example.mx/hook")

    assert (await post_twilio(client, params, firma=otra)).status_code == 404
    assert (await leer_job(job["job_id"]))["delivered_at"] is None


async def test_un_parametro_manipulado_invalida_el_callback(client, make_job) -> None:
    """El ataque concreto: capturar un ``failed`` real y convertirlo en
    ``delivered``. La firma cubre los parámetros, no solo el identificador."""
    sid = "SM" + "3" * 32
    job = await make_job(message_id=sid)
    honesto = {"MessageSid": sid, "MessageStatus": "failed"}
    firma = firma_twilio(honesto)

    respuesta = await post_twilio(
        client, {"MessageSid": sid, "MessageStatus": "delivered"}, firma=firma
    )
    assert respuesta.status_code == 404
    assert (await leer_job(job["job_id"]))["delivered_at"] is None


async def test_sin_secreto_configurado_el_endpoint_se_NIEGA_y_lo_dice(client, monkeypatch) -> None:
    """Fail-closed, pero RUIDOSO. Que falte nuestro propio secreto es un error de
    configuración —no información sobre qué jobs hay—, así que aquí sí se
    distingue: 503. Lo contrario sería un canal que devuelve 404 para siempre y
    nadie sabe por qué."""
    monkeypatch.setenv("TAKAB_API_NOTIFY_SMS_AUTH_TOKEN", "")
    monkeypatch.setenv("TAKAB_API_NOTIFY_WHATSAPP_APP_SECRET", "")
    params = {"MessageSid": "SM" + "4" * 32, "MessageStatus": "delivered"}
    assert (await post_twilio(client, params)).status_code == 503
    assert (await post_meta(client, cuerpo_meta("wamid.Y", "delivered"))).status_code == 503


async def test_un_cuerpo_desmesurado_se_corta_antes_de_mirarlo(client) -> None:
    """Superficie pública: nadie puede hacernos leer megabytes en memoria para
    después comprobar que la firma no valía."""
    respuesta = await client.post(
        RUTA_META,
        content=b"x" * (nw.MAX_BODY_BYTES + 1),
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=00"},
    )
    assert respuesta.status_code == 413


async def test_el_handshake_de_meta_exige_su_verify_token(client) -> None:
    ok = await client.get(
        RUTA_META,
        params={"hub.mode": "subscribe", "hub.verify_token": META_VERIFY, "hub.challenge": "1337"},
    )
    assert ok.status_code == 200
    assert ok.text == "1337"

    mal = await client.get(
        RUTA_META,
        params={"hub.mode": "subscribe", "hub.verify_token": "adivinado", "hub.challenge": "1337"},
    )
    assert mal.status_code == 404


# =============================================================================
# EL DESENLACE TARDÍO
# =============================================================================


async def test_un_callback_bien_firmado_escribe_la_ENTREGA(client, make_job) -> None:
    """El hecho que faltaba: `sent_at` («Twilio lo encoló») y `delivered_at`
    («un humano lo tiene») son dos cosas y ahora las dos están escritas."""
    sid = "SM" + "5" * 32
    job = await make_job(message_id=sid)

    respuesta = await post_twilio(client, {"MessageSid": sid, "MessageStatus": "delivered"})
    assert respuesta.status_code == 202

    fila = await leer_job(job["job_id"])
    assert fila["delivered_at"] is not None
    assert fila["sent_at"] is not None and fila["sent_at"] <= fila["delivered_at"]
    assert fila["last_status"] == "delivered"
    assert fila["status"] == "sent"

    (evidencia,) = await acciones(job["incident_id"], "notify_delivered")
    assert evidencia["actor"].endswith(":callback")
    assert evidencia["payload"]["provider_status"] == "delivered"
    assert evidencia["payload"]["delivered_at"] is not None


async def test_notify_delivered_es_DISTINTO_de_notify_sent(client, make_job) -> None:
    """Son dos hechos y la consola tiene que poder mostrar los dos: el verbo no
    es un `notify_sent` con una bandera dentro."""
    sid = "SM" + "6" * 32
    job = await make_job(message_id=sid)
    await post_twilio(client, {"MessageSid": sid, "MessageStatus": "delivered"})

    assert len(await acciones(job["incident_id"], "notify_delivered")) == 1
    assert await acciones(job["incident_id"], "notify_sent") == []


async def test_un_REENVIO_del_mismo_callback_no_altera_nada(client, make_job) -> None:
    """Los dos proveedores reintentan. El segundo intento no puede duplicar la
    evidencia ni mover el instante de la entrega."""
    sid = "SM" + "7" * 32
    job = await make_job(message_id=sid)
    params = {"MessageSid": sid, "MessageStatus": "delivered"}

    primera = await post_twilio(client, params)
    fila1 = await leer_job(job["job_id"])
    segunda = await post_twilio(client, params)
    fila2 = await leer_job(job["job_id"])

    assert primera.status_code == segunda.status_code == 202
    assert primera.json() == segunda.json()
    assert fila1["delivered_at"] == fila2["delivered_at"]
    assert len(await acciones(job["incident_id"], "notify_delivered")) == 1


async def test_un_sent_RETRASADO_no_hace_retroceder_un_delivered(client, make_job) -> None:
    """Los callbacks no llegan en orden. Un `sent` que aterriza después de un
    `delivered` no puede borrar la entrega."""
    sid = "SM" + "8" * 32
    job = await make_job(message_id=sid)
    await post_twilio(client, {"MessageSid": sid, "MessageStatus": "delivered"})
    entregado = await leer_job(job["job_id"])

    await post_twilio(client, {"MessageSid": sid, "MessageStatus": "sent"})
    despues = await leer_job(job["job_id"])

    assert despues["delivered_at"] == entregado["delivered_at"]
    assert despues["last_status"] == "delivered"


async def test_read_asciende_sobre_delivered_sin_mover_el_instante(client, make_job) -> None:
    sid = "SM" + "a" * 32
    job = await make_job(message_id=sid)
    await post_twilio(client, {"MessageSid": sid, "MessageStatus": "delivered"})
    entregado = await leer_job(job["job_id"])
    await post_twilio(client, {"MessageSid": sid, "MessageStatus": "read"})
    leido = await leer_job(job["job_id"])

    assert leido["last_status"] == "read"
    assert leido["delivered_at"] == entregado["delivered_at"]
    assert len(await acciones(job["incident_id"], "notify_delivered")) == 1


async def test_un_job_sent_que_recibe_failed_ACABA_EN_ROJO(client, make_job) -> None:
    """El caso que hoy no se ve y el que más duele: el job se quedaba verde para
    siempre porque nadie contaba el final."""
    sid = "SM" + "b" * 32
    job = await make_job(message_id=sid)
    assert (await leer_job(job["job_id"]))["status"] == "sent"  # montaje: estaba verde

    respuesta = await post_twilio(
        client, {"MessageSid": sid, "MessageStatus": "undelivered", "ErrorCode": "30003"}
    )
    assert respuesta.status_code == 202

    fila = await leer_job(job["job_id"])
    assert fila["status"] == "failed"
    assert fila["delivered_at"] is None
    assert "30003" in (fila["error"] or "")

    (evidencia,) = await acciones(job["incident_id"], "notify_failed")
    assert evidencia["payload"]["provider_status"] == "undelivered"


async def test_un_fallo_TARDIO_no_borra_una_entrega_ya_confirmada(client, make_job) -> None:
    sid = "SM" + "c" * 32
    job = await make_job(message_id=sid)
    await post_twilio(client, {"MessageSid": sid, "MessageStatus": "delivered"})
    await post_twilio(client, {"MessageSid": sid, "MessageStatus": "failed"})

    fila = await leer_job(job["job_id"])
    assert fila["status"] == "sent"
    assert fila["delivered_at"] is not None
    assert await acciones(job["incident_id"], "notify_failed") == []


async def test_un_estado_DE_VUELO_no_cuenta_como_entrega(client, make_job) -> None:
    """`queued`, `sent` y `accepted` NO son entregas: mueven la última palabra
    del proveedor y nada más. Sin fila de evidencia (regla de oro 10)."""
    sid = "SM" + "d" * 32
    job = await make_job(message_id=sid, status="sent")
    await post_twilio(client, {"MessageSid": sid, "MessageStatus": "sent"})

    fila = await leer_job(job["job_id"])
    assert fila["last_status"] == "sent"
    assert fila["delivered_at"] is None
    assert await acciones(job["incident_id"], "notify_delivered") == []


async def test_un_estado_DESCONOCIDO_no_toca_el_desenlace(client, make_job) -> None:
    """Lo que Twilio invente mañana no puede degradar ni ascender un job."""
    sid = "SM" + "e" * 32
    job = await make_job(message_id=sid)
    respuesta = await post_twilio(client, {"MessageSid": sid, "MessageStatus": "teletransportado"})

    assert respuesta.status_code == 202
    fila = await leer_job(job["job_id"])
    assert fila["last_status"] is None
    assert fila["delivered_at"] is None


# --- el mismo trabajo, el otro proveedor --------------------------------------


async def test_meta_bien_firmado_escribe_la_entrega_del_canal_de_plantilla(
    client, make_job
) -> None:
    wa = "wamid.HBgNNTI1NTAwMDAwMDAwMBUCABEYEjc"
    job = await make_job(channel="whatsapp", message_id=wa)

    respuesta = await post_meta(client, cuerpo_meta(wa, "delivered"))
    assert respuesta.status_code == 202

    fila = await leer_job(job["job_id"])
    assert fila["delivered_at"] is not None
    assert fila["last_status"] == "delivered"
    (evidencia,) = await acciones(job["incident_id"], "notify_delivered")
    assert evidencia["payload"]["channel"] == "whatsapp"


async def test_el_identificador_de_un_canal_no_casa_con_el_job_de_otro(client, make_job) -> None:
    """La llave es (canal, identificador). Un callback de Meta con el SID de un
    SMS no puede tocar ese job — ni al revés."""
    sid = "SM" + "f" * 32
    job = await make_job(channel="sms", message_id=sid)

    respuesta = await post_meta(client, cuerpo_meta(sid, "delivered"))
    assert respuesta.status_code == 404
    assert (await leer_job(job["job_id"]))["delivered_at"] is None
