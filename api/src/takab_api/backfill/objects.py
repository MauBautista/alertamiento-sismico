"""Ingesta de objetos S3 del backfill (T-1.25).

- ``backfill/{thing}/….ndjson(.gz)`` (bucket transfer): cada línea es un
  registro del spool del edge ``{topic, payload, …}`` y pasa por los
  ``ingest.handlers`` **VERBATIM** (mismo validate + mismo handler + misma
  idempotencia por PK/ON CONFLICT ⇒ re-ingesta = cero deltas). La identidad es
  el ``thing`` de la key: la nube solo pre-firmó esa key para ese principal
  verificado (grant service), así que la key ES la autoridad.
- ``evidence/{tenant}/{event_uuid}/{sha256}.mseed`` (bucket evidence): se
  verifica el sha256 REAL del objeto contra la key y se registra
  ``evidence_objects`` linkeando el incidente por ``event_uuid`` (el evento
  pudo llegar por el MISMO backfill: si aún no está, RETRY vía SQS).
- ``evidence/…`` que no sea ninguno de los anteriores (T-7.05·H-2): si tiene
  autor declarado en ``_AJENOS_CONOCIDOS`` lo escribió la propia API (informes,
  reporte de simulacro, foto del ocupante) y el bucket notifica el prefijo
  entero, así que se **acusa y se descarta** con su motivo en el log. Si NO lo
  tiene, ``REJECT``: nadie decidió que eso viviera ahí y el único canal vigilado
  para «que alguien mire esto» es la cola de mensajes muertos. Ver
  ``_reconocer_ajeno``.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg
from psycopg.rows import tuple_row

from takab_api.audit import audit
from takab_api.contracts.loader import ContractError, discriminate, kind_for_topic, validate
from takab_api.contracts.meta import Meta
from takab_api.ingest.handlers import HANDLERS, Outcome
from takab_api.ingest.registry import Registry
from takab_api.settings import Settings

logger = logging.getLogger("takab_api.backfill")

#: Rondas extra para líneas RETRY dentro del MISMO objeto (p.ej. un ack que
#: precede a su incidente unas líneas más abajo). Lo no resuelto ⇒ RETRY del
#: mensaje SQS completo (idempotente).
_RETRY_ROUNDS = 3


@dataclass(frozen=True)
class ObjectResult:
    outcome: Outcome
    reason: str = ""
    ok: int = 0
    rejected: int = 0
    retried: int = 0


def process_s3_object(
    conn: psycopg.Connection,
    bucket: str,
    key: str,
    registry: Registry,
    settings: Settings,
    *,
    s3_client,
    ultimo_intento: bool = False,
) -> ObjectResult:
    """Procesa un ObjectCreated; commit al final si terminó (OK). RETRY ⇒ el
    consumer NO borra el mensaje (redelivery idempotente).

    [T-7.50] `ultimo_intento` dice que SQS no va a reentregar este mensaje otra
    vez —lo deriva el consumer de `ApproximateReceiveCount` contra el
    `maxReceiveCount` de la propia cola—. Lo que hasta ahora se iba a la DLQ en
    silencio, en ese intento se DECLARA."""
    if key.startswith("backfill/"):
        return _process_ndjson(conn, bucket, key, registry, s3_client=s3_client)
    if key.startswith("evidence/"):
        # [T-3.11.b] El CCTV comparte prefijo con el miniSEED —el bucket solo notifica
        # `evidence/`— así que aquí es donde se separan, por el nombre del objeto.
        nombre = key.rsplit("/", 1)[-1]
        if nombre.startswith(("cctv-", "still-")):
            return _process_cctv(conn, bucket, key, s3_client=s3_client)
        if nombre.endswith(".mseed"):
            return _process_evidence(
                conn, bucket, key, s3_client=s3_client, ultimo_intento=ultimo_intento
            )
        return _reconocer_ajeno(key)
    return ObjectResult(Outcome.REJECT, f"key sin ruta conocida: {key!r}")


#: Lo que la PROPIA API escribe bajo `evidence/`, por el nombre del objeto y con
#: su autor al lado: el censo de lo que alguien YA decidió que vive ahí. Es lo que
#: separa «esto lo escribió el informe del incidente» —se acusa y se borra— de
#: «esto no sé quién lo puso», que se RECHAZA y acaba en la cola de mensajes
#: muertos con su motivo (ver `_reconocer_ajeno`). Dar de alta un productor nuevo
#: es añadir su línea aquí; no hacerlo no lo esconde, lo delata.
#:
#: No se enumera a ciegas: `test_el_censo_de_ajenos_se_DERIVA_del_codigo_que_escribe`
#: barre el AST del paquete —menos `backfill/`, que es este worker— buscando las
#: keys `evidence/…` que la API construye, y exige que cada una esté cubierta
#: aquí. Un renombrado en `reports.py`, `drills.py` o `mobile_incident.py`, o un
#: productor nuevo en cualquier módulo, se cae en CI y no en la DLQ.
#:
#: `reporte.pdf` es un nombre completo y los otros dos son prefijos; `startswith`
#: sirve para los tres.
_AJENOS_CONOCIDOS: tuple[tuple[str, str], ...] = (
    # api/src/takab_api/routers/reports.py — report-{technical,executive}-{ts}.pdf
    ("report-", "informe del incidente (POST /incidents/{id}/report)"),
    # api/src/takab_api/routers/drills.py — evidence/{tenant}/drills/{id}/reporte.pdf
    ("reporte.pdf", "reporte de simulacro (POST /drills/{id}/report)"),
    # api/src/takab_api/routers/mobile_incident.py — photo-{evidence_id}.jpg
    ("photo-", "foto que sube el ocupante desde la app"),
)


def _reconocer_ajeno(key: str) -> ObjectResult:
    """Un objeto del prefijo `evidence/` que **no es de este worker** (T-7.05·H-2).

    Bajo `evidence/` escriben CINCO cosas y solo dos son suyas: el miniSEED del
    gabinete (`{sha}.mseed`) y los clips y capturas del CCTV (`cctv-`/`still-`).
    Las otras tres las escribe la propia API —el informe del incidente, el
    reporte de simulacro y la foto que sube el ocupante—, y el bucket notifica el
    prefijo ENTERO (`infra/terraform/modules/storage`, `filter_prefix`), así que
    sus `ObjectCreated` aterrizan en esta cola igual que los del gabinete.

    Hasta hoy caían en `_process_evidence`, que los llamaba *key malformada* y
    los mandaba a la cola de mensajes muertos: al desplegar el worker el
    2026-09-12 drenó 65 mensajes y **4 informes acabaron en
    `takab-dev-q-backfill-dlq`**. Nada estaba roto — el PDF era bueno, la
    notificación era buena y el destinatario simplemente era otro.

    Y el daño no es el ruido: una DLQ que se llena de objetos sanos deja de ser
    una señal. La alarma que la vigila no distingue un PDF correcto de un
    miniSEED de evidencia que se perdió de verdad, y el segundo es el que hay
    que ver. Por eso «conocido y no mío» se **acusa** (se borra de la cola) y se
    registra con su nombre, en vez de rechazarse.

    **Y por eso mismo «no sé de quién es esto» NO se acusa: `REJECT`.** El
    reconocimiento de los ajenos es por DESCARTE —todo lo que no sea `.mseed` ni
    CCTV—, así que un productor nuevo del prefijo entraría por esta misma puerta
    sin que nadie lo hubiera decidido. La primera versión de este arreglo lo
    descartaba con un `logger.warning` y devolvía `OK`, confiando en que
    «alguien se enterará». No hay nadie: en todo `infra/terraform/` existe **un
    solo** `aws_cloudwatch_log_metric_filter` (`iot_rule_errors`,
    `modules/observability/main.tf`) y no cubre a este worker, que además corre
    en docker compose sobre el EC2 (`deploy/cloud/docker-compose.yml`) — el
    WARNING se moría en `docker logs` del host. Un aviso que nadie vigila es un
    `OK` con mala conciencia, y esta ingesta ya tiene un canal desplegado,
    durable y con alarma para «que alguien mire esto»: la DLQ, que
    `takab-dev-dlq-backfill` vigila contra el tópico SNS de operación.

    El precio de la elección es simétrico y está medido: los tres autores de
    `_AJENOS_CONOCIDOS` cubren el 100 % de lo que la API escribe hoy bajo
    `evidence/` (`test_el_censo_de_ajenos_se_DERIVA_del_codigo_que_escribe`), así que la
    DLQ sigue sin recibir un PDF — que es el criterio de la ficha — y a la vez
    conserva la señal para el productor que aparezca mañana. Darlo de alta es
    una línea en el censo de arriba; hasta que alguien la escriba, su objeto se
    queda en la cola con su motivo, que es exactamente lo que se quiere.

    Lo que sigue yendo a la DLQ, y debe: un `.mseed` con la key mal formada, con
    el sha que no cuadra o con tenant ajeno. Ahí sí hay algo que mirar.
    """
    nombre = key.rsplit("/", 1)[-1]
    for marca, autor in _AJENOS_CONOCIDOS:
        if nombre.startswith(marca):
            razon = f"objeto ajeno al backfill bajo evidence/ — {autor}: {key}"
            # Rutina con autor conocido: INFO. Si esto gritara, cada informe que
            # firma el SOC dejaría un aviso y el aviso dejaría de significar algo
            # —la misma erosión que la DLQ llena de PDF, una capa más arriba—.
            logger.info("backfill descarta con acuse: %s", razon)
            return ObjectResult(Outcome.OK, razon)

    razon = f"objeto DESCONOCIDO bajo evidence/, sin autor declarado: {key}"
    # El log acompaña; lo que AVISA es la DLQ (ver docstring). Si algún día este
    # rechazo se vuelve rutina, la salida es declarar su autor en
    # `_AJENOS_CONOCIDOS`, no bajarle el volumen aquí.
    logger.warning("backfill NO reconoce el objeto y lo rechaza: %s", razon)
    return ObjectResult(Outcome.REJECT, razon)


# ------------------------------------------------------------------- NDJSON


def _process_ndjson(
    conn: psycopg.Connection, bucket: str, key: str, registry: Registry, *, s3_client
) -> ObjectResult:
    parts = key.split("/")
    if len(parts) < 3 or not parts[1]:
        return ObjectResult(Outcome.REJECT, f"key de backfill malformada: {key!r}")
    thing = parts[1]
    ctx = registry.resolve(thing)
    if ctx is None:
        return ObjectResult(Outcome.REJECT, f"unknown principal en key: {thing!r}")

    body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
    if key.endswith(".gz"):
        body = gzip.decompress(body)
    lines = [line for line in body.decode().splitlines() if line.strip()]

    ok = rejected = 0
    pending: list[tuple[int, dict]] = []
    for index, line in enumerate(lines):
        outcome, _reason = _ingest_line(conn, line, thing, ctx)
        if outcome is Outcome.OK:
            ok += 1
        elif outcome is Outcome.REJECT:
            rejected += 1
        else:
            try:
                pending.append((index, json.loads(line)))
            except ValueError:
                rejected += 1

    retried = 0
    for _round in range(_RETRY_ROUNDS):
        if not pending:
            break
        still: list[tuple[int, dict]] = []
        for index, record in pending:
            outcome, _reason = _ingest_record(conn, record, thing, ctx)
            if outcome is Outcome.OK:
                ok += 1
                retried += 1
            elif outcome is Outcome.REJECT:
                rejected += 1
            else:
                still.append((index, record))
        pending = still

    if pending:
        conn.rollback()  # nada parcial: el mensaje SQS se reentrega completo
        return ObjectResult(
            Outcome.RETRY,
            f"{len(pending)} líneas aún RETRY (p.ej. dependencias no ingeridas)",
            ok=0,
            rejected=rejected,
        )
    conn.commit()
    logger.info("backfill %s: %d ok, %d rechazadas (de %d)", key, ok, rejected, len(lines))
    return ObjectResult(Outcome.OK, ok=ok, rejected=rejected, retried=retried)


def _ingest_line(conn: psycopg.Connection, line: str, thing: str, ctx) -> tuple[Outcome, str]:
    try:
        record = json.loads(line)
    except ValueError:
        return Outcome.REJECT, "línea NDJSON inválida"
    if not isinstance(record, dict):
        return Outcome.REJECT, "línea no es objeto"
    return _ingest_record(conn, record, thing, ctx)


def _ingest_record(conn: psycopg.Connection, record: dict, thing: str, ctx) -> tuple[Outcome, str]:
    topic = record.get("topic")
    payload = record.get("payload")
    if not isinstance(topic, str) or not isinstance(payload, dict):
        return Outcome.REJECT, "registro sin topic/payload"
    try:
        kind = discriminate(kind_for_topic(topic), payload)
        validate(kind, payload)
    except ContractError as exc:
        return Outcome.REJECT, str(exc)
    handler = HANDLERS.get(kind)
    if handler is None:
        return Outcome.REJECT, f"sin handler para {kind!r}"
    meta = Meta(principal=thing, topic=topic, ts_iot=_spooled_at(record))
    result = handler(conn, payload, meta, ctx)
    return result.outcome, result.reason


def _spooled_at(record: dict) -> datetime | None:
    raw = record.get("spooled_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


# ----------------------------------------------------------------- evidencia


_INSERT_EVIDENCE_SQL = """
INSERT INTO evidence_objects (tenant_id, incident_id, kind, s3_key, sha256)
VALUES (%s, %s, 'miniseed', %s, %s)
ON CONFLICT DO NOTHING
"""


def _process_evidence(
    conn: psycopg.Connection, bucket: str, key: str, *, s3_client, ultimo_intento: bool = False
) -> ObjectResult:
    parts = key.split("/")
    if len(parts) != 4 or not parts[3].endswith(".mseed"):
        return ObjectResult(Outcome.REJECT, f"key de evidencia malformada: {key!r}")
    _prefix, tenant_id, event_uuid, filename = parts
    expected_sha = filename.removesuffix(".mseed")

    body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
    digest = hashlib.sha256(body).hexdigest()
    if digest != expected_sha:
        return ObjectResult(
            Outcome.REJECT, f"sha256 no coincide con la key ({digest[:12]}…≠{expected_sha[:12]}…)"
        )

    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT incident_id, tenant_id FROM incidents WHERE event_uuid = %s",
            (event_uuid,),
        )
        row = cur.fetchone()
    if row is None:
        conn.rollback()
        if not ultimo_intento:
            # El evento pudo venir en el MISMO backfill y aún no ingerirse: RETRY.
            return ObjectResult(Outcome.RETRY, f"incidente {event_uuid} aún no ingerido")
        # [T-7.50] Se acabaron las reentregas: «aún no ingerido» deja de ser
        # cierto. Hasta esta ficha el mensaje caía a la DLQ **en silencio** y la
        # alarma que lo vigila está muda (`T-7.41`), así que el objeto quedaba en
        # S3 sin que nada dijera por qué. La evidencia NO SE BORRA (regla de oro
        # 11): se DECLARA huérfana, con su key, en `audit_log` — que es la tabla
        # que la purga operativa conserva POR NOMBRE, al revés que
        # `evidence_objects`. Así el objeto sigue siendo encontrable para siempre
        # y el motivo también.
        logger.warning(
            "evidencia HUÉRFANA declarada: %s (incidente %s no ingerido tras agotar "
            "las reentregas de la cola)",
            key,
            event_uuid,
        )
        audit(
            conn,
            tenant_id=None,
            actor="system:backfill",
            verb="evidence_orphan_declared",
            obj=key,
            meta={
                "event_uuid": event_uuid,
                "sha256": digest,
                "bucket": bucket,
                "motivo": "el incidente no existe y la cola agotó sus reentregas",
            },
        )
        conn.commit()
        return ObjectResult(
            Outcome.REJECT,
            f"evidencia huérfana DECLARADA: el incidente {event_uuid} no existe "
            "y se agotaron las reentregas",
        )
    incident_id, incident_tenant = row
    if str(incident_tenant) != tenant_id:
        return ObjectResult(Outcome.REJECT, "tenant de la key ≠ tenant del incidente")

    conn.execute(_INSERT_EVIDENCE_SQL, (incident_tenant, incident_id, key, digest))
    conn.commit()
    logger.info("evidencia %s registrada (incidente %s)", key, incident_id)
    return ObjectResult(Outcome.OK, ok=1)


# --------------------------------------------------------------------- CCTV

#: [T-3.11.b] `ON CONFLICT DO NOTHING` sobre la restricción natural: la key lleva el
#: sha256 dentro, así que re-entregar el mismo objeto —que SQS hace, por diseño at-least-
#: once— no duplica la fila. El clip queda registrado y descargable **antes** de que exista
#: quien lo analice; que el análisis esté hecho se DERIVA de si hay métricas para su
#: incidente, no de una columna de estado que esta tabla append-only no podría mover.
_INSERT_CLIP_SQL = """
INSERT INTO cctv_clips
  (tenant_id, incident_id, s3_key, sha256, size_bytes, started_at, ended_at)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (incident_id, sha256) WHERE sha256 IS NOT NULL DO NOTHING
RETURNING clip_id
"""

_INSERT_STILL_SQL = """
INSERT INTO cctv_stills
  (tenant_id, incident_id, s3_key, sha256, captured_at, role)
VALUES (%s, %s, %s, %s, %s, 'drip')
ON CONFLICT (incident_id, sha256) WHERE sha256 IS NOT NULL DO NOTHING
RETURNING still_id
"""


def _process_cctv(conn: psycopg.Connection, bucket: str, key: str, *, s3_client) -> ObjectResult:
    """Registra un clip o una captura de CCTV recién subidos por el gabinete.

    Mismo esqueleto que `_process_evidence` y a propósito: se verifica el sha256 contra la
    key (el objeto es lo que dice ser), se resuelve el incidente por `event_uuid`, y se
    comprueba que el tenant de la key coincida con el del incidente — porque las FK de
    Postgres no comparan tenant y sin esto una key ajena alcanzaría el espacio de otro
    cliente.

    **El `RETRY` cuando el incidente aún no existe no es un detalle.** El clip tarda diez
    minutos en cortarse y puede subir ANTES de que el evento se haya ingerido si el
    gabinete estuvo sin red; devolver `REJECT` mandaría a la DLQ una evidencia buena.
    """
    parts = key.split("/")
    if len(parts) != 4:
        return ObjectResult(Outcome.REJECT, f"key de CCTV malformada: {key!r}")
    _prefix, tenant_id, event_uuid, filename = parts

    partido = _partir_nombre_cctv(filename)
    if partido is None:
        return ObjectResult(Outcome.REJECT, f"key de CCTV malformada: {key!r}")
    es_clip, inicio, fin, expected_sha = partido

    body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
    digest = hashlib.sha256(body).hexdigest()
    if digest != expected_sha:
        return ObjectResult(
            Outcome.REJECT, f"sha256 no coincide con la key ({digest[:12]}…≠{expected_sha[:12]}…)"
        )

    with conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(
            "SELECT incident_id, tenant_id FROM incidents WHERE event_uuid = %s",
            (event_uuid,),
        )
        row = cur.fetchone()
    if row is None:
        conn.rollback()
        return ObjectResult(Outcome.RETRY, f"incidente {event_uuid} aún no ingerido")
    incident_id, incident_tenant = row
    if str(incident_tenant) != tenant_id:
        return ObjectResult(Outcome.REJECT, "tenant de la key ≠ tenant del incidente")

    if es_clip:
        cur = conn.execute(
            _INSERT_CLIP_SQL,
            (incident_tenant, incident_id, key, digest, len(body), inicio, fin),
        )
    else:
        cur = conn.execute(_INSERT_STILL_SQL, (incident_tenant, incident_id, key, digest, inicio))
    creada = cur.fetchone() is not None

    if creada:
        # [T-3.11.b · D-14] «La salida de vídeo queda AUDITADA igual que un comando de
        # actuador». Es una excepción DELIBERADA a la costumbre de esta ingesta, que no
        # audita los OK (ver `_audit_reject`, regla de oro 10): un objeto de CCTV no es un
        # latido periódico, es una imagen de personas identificables saliendo del inmueble
        # del cliente. Cada una de esas salidas es un hecho que alguien puede tener que
        # justificar, y sin esta fila la única constancia sería el propio objeto — que la
        # política de retención está obligada a borrar.
        #
        # Va atado a `creada`, y por eso el INSERT lleva `RETURNING`: SQS entrega
        # at-least-once y sin esto una reentrega escribiría una segunda fila diciendo que
        # el vídeo salió dos veces. `DEDUPE_VERBS` resuelve ese mismo problema con una
        # cubeta temporal de 450 s; aquí no hace falta porque `RETURNING` es EXACTO —
        # dedupea también la reentrega que llega horas después, que la cubeta no vería.
        audit(
            conn,
            tenant_id=str(incident_tenant),
            actor="system:backfill",
            verb="cctv_egress",
            obj=key,
            meta={
                "incident_id": str(incident_id),
                "kind": "clip" if es_clip else "still",
                "sha256": digest,
                "size_bytes": len(body),
                "desde": inicio.isoformat(),
                "hasta": fin.isoformat(),
            },
        )
    conn.commit()
    if creada and es_clip:
        # [T-3.12.b] El disparo del analisis va AQUI y no en una notificacion de S3, y no
        # es una preferencia: el prefijo `evidence/` YA tiene una notificacion hacia esta
        # misma cola de backfill, y S3 rechaza configuraciones con filtros solapados.
        # Colgar el Lambda de `evidence/*.mp4` romperia la ingesta del miniSEED.
        #
        # Colgado de `creada` hereda gratis la idempotencia del `RETURNING`: SQS entrega
        # at-least-once y una reentrega no vuelve a encolar porque no vuelve a crear. Sin
        # eso, cada reentrega pagaria otra inferencia completa sobre el mismo clip.
        #
        # Y va DESPUES del commit a proposito: si el encolado falla, la fila del clip ya
        # esta puesta y el reporte dice `ANALISIS PENDIENTE`, que es verdad. Al reves
        # —encolar y luego fallar el commit— el Lambda buscaria un clip que no existe.
        _encolar_analisis(str(incident_id), key)
    logger.info("cctv: %s registrado (incidente %s)", key, incident_id)
    return ObjectResult(Outcome.OK, ok=1)


def _encolar_analisis(incident_id: str, key: str) -> None:
    """Pide el analisis del clip. **Best-effort declarado, nunca silencioso.**

    Un fallo aqui no puede tumbar la ingesta —el objeto ya esta registrado y es evidencia
    valida— pero tampoco puede pasar desapercibido: sin este mensaje el incidente se queda
    en `ANALISIS PENDIENTE` para siempre y nadie sabria por que. Por eso se registra a
    `error` y con la key, que es lo que permite re-encolarlo a mano.
    """
    import os

    url = os.environ.get("TAKAB_API_CCTV_QUEUE_URL")
    if not url:
        # Sin cola configurada no hay a quien pedirle el analisis. En local es el estado
        # normal y por eso va en `info`, una vez por objeto.
        #
        # [2026-09-01] Este comentario decia "no hay Lambda desplegado todavia (T-3.12.b
        # espera ventana AWS)" y ya es FALSO: el Lambda se desplego el 2026-08-30 y
        # `deploy/cloud/deploy.sh` exporta la variable. En la nube su ausencia ya no es el
        # estado esperado — es un despliegue que perdio la variable. No se sube a `warning`
        # porque aqui no se puede distinguir un entorno local de uno desplegado, y quien si
        # lo declara es el reporte: "CLIP DISPONIBLE · ANALISIS PENDIENTE".
        logger.info("cctv: sin TAKAB_API_CCTV_QUEUE_URL; %s queda con analisis pendiente", key)
        return
    try:
        import boto3

        boto3.client("sqs").send_message(
            QueueUrl=url,
            MessageBody=json.dumps({"incident_id": incident_id, "s3_key": key}),
        )
    except Exception:  # noqa: BLE001 — la ingesta jamas cae por el analisis
        logger.exception("cctv: no se pudo encolar el analisis de %s; queda PENDIENTE", key)


_TS_KEY = "%Y%m%dT%H%M%SZ"


def _partir_nombre_cctv(filename: str) -> tuple[bool, datetime, datetime, str] | None:
    """`(es_clip, inicio, fin, sha256)` del nombre del objeto, o `None` si no cuadra.

    Formatos, fijados por `backfill.grants.canonical_key`:

    * ``cctv-{desde}_{hasta}-{sha256}.mp4``
    * ``still-{cuando}-{sha256}.jpg``

    Se analiza aqui y no se adivina en la base porque la notificacion de S3 **solo ve la
    key**: en este camino es la unica fuente de la ventana del clip.
    """
    if filename.startswith("cctv-") and filename.endswith(".mp4"):
        ventana, _, sha = filename[len("cctv-") : -len(".mp4")].rpartition("-")
        desde, _, hasta = ventana.partition("_")
        if not hasta:
            return None
        try:
            return (
                True,
                datetime.strptime(desde, _TS_KEY).replace(tzinfo=UTC),
                datetime.strptime(hasta, _TS_KEY).replace(tzinfo=UTC),
                sha,
            )
        except ValueError:
            return None
    if filename.startswith("still-") and filename.endswith(".jpg"):
        cuando, _, sha = filename[len("still-") : -len(".jpg")].rpartition("-")
        try:
            ts = datetime.strptime(cuando, _TS_KEY).replace(tzinfo=UTC)
        except ValueError:
            return None
        return (False, ts, ts, sha)
    return None
