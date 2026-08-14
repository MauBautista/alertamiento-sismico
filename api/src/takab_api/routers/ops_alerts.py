"""[T-2.78.a] La cadena de OPERACIÓN: suscriptor de SNS, acuse humano y consulta.

Segunda superficie pública de la API, y la primera fue hace dos fichas
(`notify_webhooks.py`, T-2.77.b). **Léela antes que ésta**: la disciplina es la
misma y aquí no se reinventa — cuerpo acotado, nada de tocar la base sin
credencial válida, el rechazo siempre con la MISMA respuesta, y fail-closed
ruidoso (503) cuando lo que falta es configuración NUESTRA.

Lo que esta superficie añade sobre aquélla es el problema que aquélla no tenía:
**un endpoint HTTPS suscrito a SNS es una SSRF esperando**. El razonamiento
entero —por qué HTTPS y no Lambda, y cómo se cierran las dos URLs del cuerpo—
está en `ops/alerts.py`. En una línea: `SubscribeURL` **no se visita nunca** (la
confirmación se reconstruye con nuestro host y nuestro `TopicArn`, y del cuerpo
solo se toma el `Token`), y `SigningCertURL` pasa por
`alerts.signing_cert_url_ok` **antes de abrir un socket**.

──────────────────────────────────────────────────────────────────────────────
LAS TRES RUTAS Y POR QUÉ SON ASÍ
──────────────────────────────────────────────────────────────────────────────
* `POST /ops/alerts/sns` — lo llama AWS. Sin sesión; la firma RSA del sobre es
  la única autenticación.
* `GET  /ops/alerts/ack` — una página **mínima** con un campo y un botón. Es la
  concesión deliberada de esta ficha: la persona de guardia recibe un correo a
  las tres de la mañana y no tiene una sesión de consola abierta. Un acuse que
  exija consola + MFA es un acuse que no se va a dar, y entonces la métrica mide
  fricción y no atención.
* `POST /ops/alerts/ack` — el acuse. **POST y no GET**, y esto no es purismo
  REST: los escáneres de seguridad de los buzones **pulsan los enlaces de los
  correos**. Un acuse por `GET` lo fabricaría una máquina antes de que nadie
  leyera nada, y el criterio 5 —«un aviso sin acuse jamás aparece como
  atendido»— se violaría desde el primer correo. Sin cookies de por medio no hay
  CSRF que cerrar: la credencial viaja en el cuerpo y sólo la tiene la persona.
* `GET  /ops/alerts/chain` — la consulta, ésta SÍ detrás de Cognito y sólo para
  roles internos de TAKAB. Que el on-call de la plataforma no contestara no es
  dato de ningún cliente.
"""

from __future__ import annotations

import html
import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.auth.claims import Claims
from takab_api.auth.deps import get_session, require_roles
from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.ops import alerts as al
from takab_api.routers._common import http_error
from takab_api.schemas.ops_alerts import OpsAlertChain, OpsAlertNoticeOut
from takab_api.settings import Settings

logger = logging.getLogger("takab_api.ops")

router = APIRouter()

#: Un sobre de SNS con una alarma de CloudWatch dentro son ~4 KB. 64 KiB deja
#: margen de sobra y convierte "mándale 2 GB al endpoint sin autenticar" en un
#: 413 barato. Mismo criterio que `notify_webhooks.MAX_BODY_BYTES`.
MAX_BODY_BYTES = 64 * 1024

#: LA MISMA respuesta para "tu firma no vale", "ese topic no es el mío" y "esa
#: credencial no existe". Desde fuera no se puede averiguar nada; la diferencia
#: se escribe en el log, que es donde la lee quien opera y no quien llama.
_NO_RECONOCIDO = "no reconocido"

_ACK_OK = {"ok": True}

_RECORD_SQL = text(
    """
SELECT o_notice_id, o_created, o_requires_ack, o_ack_deadline_at
FROM app_ops_alert_record(
  :message_id, :topic_arn, :alarm_name, :alarm_state, :subject, :reason,
  CAST(:published_at AS timestamptz), :requires_ack, :deadline_s)
"""
)

_ACK_SQL = text("SELECT o_token_ok, o_label, o_acusados FROM app_ops_alert_ack(:token_hash)")

_CHAIN_SQL = text(
    """
SELECT notice_id::text AS notice_id, alarm_name, alarm_state, subject, state_reason,
       published_at, received_at, requires_ack, ack_deadline_at, acked_at, acked_by,
       unacked_at, outcome, ack_latency_s, ack_latency_publicado_s
  FROM v_ops_alert_chain
 ORDER BY received_at DESC
 LIMIT :limite
"""
)


@asynccontextmanager
async def notices_conn():
    """Conexión de esta superficie: ``takab_app`` y SIN contexto de tenant.

    No es un descuido que vaya vacía: no hay sesión de la que sacarlo. Con la RLS
    default-deny de las dos tablas, lo único que esta conexión puede hacer es
    ejecutar las dos funciones `SECURITY DEFINER` de la 0041 — un `SELECT`
    directo desde aquí no devolvería ni una fila.

    Es una función del módulo, y no una llamada en línea, para que un test pueda
    sabotearla y comprobar que un sobre sin firma válida no llega hasta aquí.
    """
    async with get_tenant_conn(
        SessionCtx(tenant_id="", role="", user_id=""), set_session_role="takab_app"
    ) as conn:
        yield conn


async def _read_body(request: Request) -> bytes:
    """Cuerpo CRUDO y acotado (esto no pide credenciales a nadie)."""
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > MAX_BODY_BYTES:
        raise http_error(413, "cuerpo demasiado grande")
    trozos: list[bytes] = []
    total = 0
    async for trozo in request.stream():
        total += len(trozo)
        if total > MAX_BODY_BYTES:
            raise http_error(413, "cuerpo demasiado grande")
        trozos.append(trozo)
    return b"".join(trozos)


def _rechazo(motivo: str) -> Exception:
    """404 idéntico para todos los rechazos; el motivo REAL va al log."""
    logger.warning("ops[alerts] rechazado: %s", motivo)
    return http_error(404, _NO_RECONOCIDO)


def _parse_ts(raw: object) -> datetime | None:
    """El ``Timestamp`` del sobre (ISO-8601 con Z). Nunca hace fallar el aviso."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


# =============================================================================
# EL SUSCRIPTOR DE SNS
# =============================================================================


@router.post("/ops/alerts/sns", status_code=202)
async def sns_endpoint(request: Request) -> dict:
    """Mensaje del topic de operación, firmado por AWS.

    El orden de las puertas importa y es de fuera hacia dentro: primero lo que
    no cuesta nada (configuración, tamaño, JSON, `TopicArn`), después la puerta
    de la URL del certificado —que es la que evita la SSRF— y solo entonces la
    salida a la red y la firma. La base se toca **la última**.
    """
    settings = Settings()
    topic_arn = (settings.ops_alert_topic_arn or "").strip()
    region = al.region_of_topic(topic_arn)
    if not region:
        # Fail-closed RUIDOSO: sin el ARN del topic no hay con qué comparar el
        # remitente ni de dónde sacar el host permitido. Que falte NUESTRA
        # configuración es un error de despliegue, no información sobre qué
        # avisos hay — contestar 404 dejaría un canal muerto para siempre sin
        # que nadie supiera por qué.
        logger.error(
            "ops[alerts]: falta TAKAB_API_OPS_ALERT_TOPIC_ARN (o no es un ARN de SNS); el "
            "endpoint responde 503 y NO hay evidencia de máquina de la cadena on-call"
        )
        raise http_error(503, "el suscriptor de operación no está configurado en este despliegue")

    cuerpo = await _read_body(request)
    try:
        sobre = json.loads(cuerpo)
    except ValueError as exc:
        raise _rechazo("cuerpo ilegible") from exc
    if not isinstance(sobre, dict):
        raise _rechazo("cuerpo que no es un sobre")

    # El remitente, ANTES de mirar nada más: un sobre de otro topic no llega ni a
    # descargar un certificado. Y la región de las salidas a la red sale de AQUÍ,
    # nunca del cuerpo.
    if sobre.get("TopicArn") != topic_arn:
        raise _rechazo("TopicArn que no es el nuestro")

    cert_url = sobre.get("SigningCertURL") or sobre.get("SigningCertUrl") or ""
    if not isinstance(cert_url, str) or not al.signing_cert_url_ok(cert_url, region=region):
        # LA PUERTA DE LA SSRF. Se cierra ANTES de abrir un socket: quien manda
        # el cuerpo elige esta URL, y un servidor que la siga es un cliente HTTP
        # a las órdenes de cualquiera desde DENTRO de la VPC.
        raise _rechazo(f"SigningCertURL fuera del host de SNS de {region}")

    cert_pem = await al.signing_cert(cert_url, timeout_s=settings.ops_sns_timeout_s)
    if cert_pem is None:
        raise _rechazo("certificado de firma no disponible")
    if not al.verify_sns_signature(sobre, cert_pem=cert_pem):
        raise _rechazo("firma no válida")

    tipo = sobre.get("Type")
    if tipo in (al.TYPE_SUBSCRIPTION_CONFIRMATION, al.TYPE_UNSUBSCRIBE_CONFIRMATION):
        await _confirmar(sobre, topic_arn=topic_arn, settings=settings)
        return _ACK_OK
    if tipo != al.TYPE_NOTIFICATION:
        raise _rechazo(f"tipo de sobre no reconocido: {tipo!r}")

    return await _registrar(sobre, topic_arn=topic_arn, settings=settings)


async def _confirmar(sobre: dict, *, topic_arn: str, settings: Settings) -> None:
    """Cierra el alta de la suscripción **sin visitar el ``SubscribeURL``**.

    El sobre trae un ``SubscribeURL`` y lo natural sería pedirlo. No se hace: esa
    URL la elige quien manda el cuerpo. Se reconstruye la llamada con el host de
    la región de NUESTRO topic y con NUESTRO ``TopicArn``, y del cuerpo se toma
    solo el ``Token`` opaco (que además va firmado, así que no es de cualquiera).
    """
    token = sobre.get("Token")
    if not isinstance(token, str) or not token:
        raise _rechazo("confirmación sin Token")
    destino = al.confirm_subscription_url(topic_arn=topic_arn, token=token)
    try:
        await al.fetch_url(destino, timeout_s=settings.ops_sns_timeout_s)
    except Exception as exc:  # noqa: BLE001 - la causa concreta va al log
        # No es 404: la firma era buena y el remitente era el nuestro. Que AWS no
        # nos conteste es un fallo NUESTRO, y un 5xx hace que SNS reintente.
        logger.error("ops[alerts]: no se pudo confirmar la suscripción", exc_info=True)
        raise http_error(503, "no se pudo confirmar la suscripción") from exc
    logger.info(
        "ops[alerts]: suscripción confirmada contra %s",
        al.sns_host(al.region_of_topic(topic_arn)),
    )


async def _registrar(sobre: dict, *, topic_arn: str, settings: Settings) -> dict:
    """La fila del aviso. **Nace sin acuse**, con su plazo puesto."""
    hechos = al.alarm_facts(sobre.get("Message"))
    message_id = sobre.get("MessageId")
    if not isinstance(message_id, str) or not message_id:
        raise _rechazo("sobre sin MessageId")
    subject = sobre.get("Subject")

    async with notices_conn() as conn:
        fila = (
            await conn.execute(
                _RECORD_SQL,
                {
                    "message_id": message_id,
                    "topic_arn": topic_arn,
                    "alarm_name": hechos.alarm_name,
                    "alarm_state": hechos.state,
                    "subject": subject if isinstance(subject, str) else "",
                    "reason": hechos.reason,
                    "published_at": (_parse_ts(sobre.get("Timestamp")) or datetime.now(UTC)),
                    "requires_ack": hechos.requires_ack,
                    "deadline_s": settings.ops_ack_deadline_s,
                },
            )
        ).first()

    if fila is None:  # pragma: no cover - la función siempre devuelve una fila
        raise _rechazo("el aviso no se pudo registrar")
    logger.info(
        "ops[alerts] aviso %s alarma %r estado %r (%s) · acuse %s",
        fila.o_notice_id,
        hechos.alarm_name,
        hechos.state,
        "nuevo" if fila.o_created else "reenvío de SNS, ya registrado",
        f"exigido antes de {fila.o_ack_deadline_at}" if fila.o_requires_ack else "no exigido",
    )
    return _ACK_OK


# =============================================================================
# EL ACUSE HUMANO
# =============================================================================

_PAGINA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TAKAB · acuse de guardia</title>
<style>
 body{{font:16px/1.5 system-ui,sans-serif;margin:0;padding:2rem 1.25rem;
      background:#10151c;color:#e7edf5}}
 main{{max-width:26rem;margin:0 auto}}
 h1{{font-size:1.15rem;letter-spacing:.02em;margin:0 0 .25rem}}
 p{{color:#9fb0c3;margin:.4rem 0 1.25rem}}
 input,button{{width:100%;box-sizing:border-box;font:inherit;padding:.85rem;
      border-radius:.5rem}}
 input{{background:#1a222c;color:#e7edf5;border:1px solid #2b3644}}
 button{{margin-top:.75rem;background:#2f7d4f;color:#fff;border:0;font-weight:600}}
 .r{{padding:.9rem;border-radius:.5rem;background:#1a222c;border:1px solid #2b3644}}
 .ko{{border-color:#7d3a3a}}
</style></head><body><main>
<h1>Acuse de guardia · TAKAB</h1>
<p>{intro}</p>
{cuerpo}
</main></body></html>
"""

_FORMULARIO = """<form method="post" action="/ops/alerts/ack">
 <input type="password" name="token" autocomplete="current-password"
        placeholder="credencial de guardia" required autofocus>
 <button type="submit">Confirmo que lo estoy atendiendo</button>
</form>"""


def _pagina(intro: str, cuerpo: str, *, status: int = 200) -> HTMLResponse:
    return HTMLResponse(_PAGINA.format(intro=html.escape(intro), cuerpo=cuerpo), status_code=status)


@router.get("/ops/alerts/ack", response_class=HTMLResponse)
async def ack_form() -> HTMLResponse:
    """La página del acuse. **No enseña ni un dato** sin credencial.

    Es un `GET` y por eso no puede acusar nada: los escáneres de los buzones
    pulsan los enlaces de los correos, y si esto acusara al abrirse, cada alarma
    llegaría ya «atendida» por una máquina.
    """
    return _pagina(
        "Pega tu credencial de guardia y confirma. Queda registrado con la hora.",
        _FORMULARIO,
    )


@router.post("/ops/alerts/ack", response_class=HTMLResponse)
async def ack_submit(request: Request) -> HTMLResponse:
    """El acuse, con hora y con nombre.

    Una credencial que no vale y «no había nada abierto» contestan LO MISMO
    (404): desde fuera no se puede saber si una credencial existe ni si hay
    avisos sin atender. Adentro sí se distinguen, en el log.

    El cuerpo se parsea a mano (``parse_qsl``) y no con ``Form``: el paquete que
    FastAPI necesita para formularios no es dependencia de esta API, y añadir uno
    para leer un campo sería pagar un despliegue por comodidad. Es además lo que
    ya hace el otro endpoint público con el formulario de Twilio.
    """
    cuerpo = await _read_body(request)
    campos = dict(parse_qsl(cuerpo.decode("utf-8", "replace"), keep_blank_values=True))
    secreto = (campos.get("token") or "").strip()
    if not secreto:
        return _pagina(
            "Sin credencial no hay acuse.", '<p class="r ko">No reconocido.</p>', status=404
        )

    async with notices_conn() as conn:
        fila = (await conn.execute(_ACK_SQL, {"token_hash": al.hash_ack_token(secreto)})).first()

    acusados = list(fila.o_acusados or []) if fila is not None else []
    if fila is None or not fila.o_token_ok:
        logger.warning(
            "ops[alerts] acuse con credencial no válida (inventada, revocada o caducada)"
        )
        return _pagina("No reconocido.", '<p class="r ko">No reconocido.</p>', status=404)
    if not acusados:
        logger.info("ops[alerts] acuse de %r sin avisos abiertos", fila.o_label)
        return _pagina("No reconocido.", '<p class="r ko">No reconocido.</p>', status=404)

    logger.info(
        "ops[alerts] ACUSE de %r sobre %d aviso(s): %s",
        fila.o_label,
        len(acusados),
        ", ".join(str(a.get("alarm_name") or a.get("notice_id")) for a in acusados),
    )
    lineas = "".join(
        f"<li>{html.escape(str(a.get('alarm_name') or 'aviso'))} — "
        f"{float(a.get('latency_s') or 0):.0f} s"
        f"{' · <b>fuera de plazo</b>' if a.get('tarde') else ''}</li>"
        for a in acusados
    )
    return _pagina(
        f"Registrado a nombre de {fila.o_label}.",
        f'<div class="r"><b>Acusado.</b><ul>{lineas}</ul></div>',
    )


# =============================================================================
# LA CONSULTA (ésta SÍ detrás de Cognito)
# =============================================================================

#: Solo roles INTERNOS de TAKAB. La RLS de `ops_alert_notices` ya lo impone por
#: debajo (`app_is_takab_internal()`), pero un 403 explícito dice por qué en vez
#: de devolver una lista vacía que parecería "no ha pasado nada".
_require_interno = require_roles("takab_superadmin", "takab_support")


@router.get("/ops/alerts/chain", response_model=OpsAlertChain)
async def read_chain(
    limit: int = 100,
    _claims: Claims = Depends(_require_interno),
    conn: AsyncConnection = Depends(get_session),
) -> OpsAlertChain:
    """Aviso → acuse → silencio, con el tiempo hasta el acuse ya calculado.

    Roles internos y nada más: la cadena de operación es de TAKAB. Que el on-call
    de la plataforma no contestara a las tres de la mañana no es dato de ningún
    cliente — y la RLS de `ops_alert_notices` lo impone por debajo aunque alguien
    se dejara esta guarda.
    """
    filas = (await conn.execute(_CHAIN_SQL, {"limite": max(1, min(limit, 500))})).mappings().all()
    return OpsAlertChain(items=[OpsAlertNoticeOut(**dict(f)) for f in filas])
