"""[T-7.05 · H-2] Lo que vive bajo `evidence/` y NO es del worker de backfill.

Al desplegar el worker por primera vez (2026-09-12) drenó 65 mensajes y mandó
**4 a `takab-dev-q-backfill-dlq`**. Los cuatro eran notificaciones
`ObjectCreated:Put` legítimas de S3 por los informes que
`POST /incidents/{id}/report` escribe bajo el MISMO prefijo de evidencia.

El bucket notifica el prefijo `evidence/` entero (`filter_prefix` en
`infra/terraform/modules/storage`) y ahí escriben **cinco** cosas, no una:

  1. el gabinete — `evidence/{tenant}/{event}/{sha256}.mseed`        ← suyo
  2. el gabinete — `evidence/{tenant}/{event}/{cctv,still}-…`        ← suyo
  3. la API      — `evidence/{tenant}/{incidente}/report-…​.pdf`      ← ajeno
  4. la API      — `evidence/{tenant}/drills/{drill}/reporte.pdf`     ← ajeno
  5. la API      — `evidence/{tenant}/{incidente}/photo-….jpg`        ← ajeno

Frente a un objeto ajeno **con autor declarado**, `REJECT` es la respuesta
equivocada: no hay nada malo que reportar, y una DLQ que se llena de objetos
sanos deja de ser una señal — el día que caiga un miniSEED de verdad, nadie lo
va a distinguir de los PDF. «Conocido y no mío» se acusa, se registra el motivo
y se descarta.

**«No sé de quién es esto» es otra cosa y termina en la DLQ.** El
reconocimiento va por descarte, así que un sexto productor entraría por la
misma puerta sin que nadie lo hubiera decidido; devolverle `OK` con un
`logger.warning` sería un fallback que se declara sano apoyado en un aviso que
nadie vigila (hay UN `aws_cloudwatch_log_metric_filter` en todo el terraform y
no cubre a este worker). La cola de mensajes muertos es el único canal
desplegado, durable y con alarma para «que alguien mire esto».

Lo que este fichero NO relaja: un `.mseed` con la key mal formada, con el sha
que no cuadra o con tenant ajeno sigue yendo a la DLQ. Ahí sí hay algo roto que
alguien tiene que mirar.
"""

from __future__ import annotations

import ast
import json
import uuid
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

import takab_api
from takab_api.backfill.consumer import BackfillConsumer
from takab_api.backfill.objects import _AJENOS_CONOCIDOS, process_s3_object
from takab_api.ingest.handlers import Outcome
from takab_api.settings import Settings

REGION = "us-east-2"
BUCKET = "takab-dev-evidence"

#: De dónde se deriva el censo de autores (ver el final del fichero): TODO el
#: paquete de la API menos `backfill/`, que es el worker mismo — sus keys
#: (`{sha}.mseed`, `cctv-…`, `still-…`) las reconoce `process_s3_object` por otra
#: puerta y no necesitan autor declarado. Se barre el paquete entero y no solo
#: `routers/` a propósito: el productor que aparezca mañana no tiene por qué nacer
#: en un router.
RUTA_API = Path(takab_api.__file__).parent
RUTA_DEL_WORKER = RUTA_API / "backfill"

#: La key exacta del mensaje que quedó en `takab-dev-q-backfill-dlq`.
KEY_INFORME_DLQ = (
    "evidence/d0000000-0000-0000-0000-000000000001/"
    "9d82e7c8-19c3-4677-95d4-289237b1a89b/report-technical-20260908T224136Z.pdf"
)


class _S3QueNadieDebeLeer:
    """Si el worker descarga un objeto ajeno, ya pagó el viaje: el reconocimiento
    va por la key y solo por la key."""

    def get_object(self, Bucket: str, Key: str) -> dict:  # noqa: N803 — firma boto3
        raise AssertionError(f"el worker bajó de S3 un objeto que no es suyo: {Key!r}")


class _ConnQueNadieDebeTocar:
    """Ni una sentencia: reconocer un ajeno no abre transacción."""

    def __getattr__(self, nombre: str):
        raise AssertionError(f"el worker tocó la base por un objeto ajeno (.{nombre})")


def _procesa(key: str):
    return process_s3_object(
        _ConnQueNadieDebeTocar(),
        BUCKET,
        key,
        registry=None,
        settings=Settings(),
        s3_client=_S3QueNadieDebeLeer(),
    )


# --------------------------------------------------------- el objeto de la DLQ


def test_el_informe_pdf_de_la_api_se_acusa_y_no_va_a_la_dlq() -> None:
    resultado = _procesa(KEY_INFORME_DLQ)
    assert resultado.outcome is Outcome.OK, resultado.reason
    assert resultado.reason, "se descarta CON motivo: sin él, el drenaje es invisible"


def test_el_motivo_nombra_al_objeto_para_que_el_log_sirva() -> None:
    """Un `OK` mudo y un `OK` de un miniSEED bien ingerido serían la misma línea."""
    resultado = _procesa(KEY_INFORME_DLQ)
    assert "report-technical-20260908T224136Z.pdf" in resultado.reason


@pytest.mark.parametrize(
    "key",
    [
        # El informe del incidente, en sus dos variantes.
        "evidence/{t}/{i}/report-technical-20260908T224136Z.pdf",
        "evidence/{t}/{i}/report-executive-20260908T224136Z.pdf",
        # El reporte de simulacro: CINCO segmentos, no cuatro (`drills/` en medio).
        "evidence/{t}/drills/{i}/reporte.pdf",
        # La foto que sube el ocupante desde la app.
        "evidence/{t}/{i}/photo-3f2504e0-4f89-41d3-9a0c-0305e82c3301.jpg",
    ],
)
def test_los_demas_productores_del_prefijo_tambien_se_acusan(key: str) -> None:
    """No es un caso: es una familia. Los cuatro de la DLQ eran informes, pero el
    reporte de simulacro y la foto del ocupante caían por la misma puerta."""
    concreta = key.format(t=uuid.uuid4(), i=uuid.uuid4())
    assert _procesa(concreta).outcome is Outcome.OK, concreta


# ------------------------------------------- lo que NO se relaja al arreglarlo


@pytest.mark.parametrize(
    "key",
    [
        # Un miniSEED con la key mal formada: eso SÍ está roto.
        "evidence/{t}/{sha}.mseed",
        "evidence/{t}/{i}/de/mas/{sha}.mseed",
        # Y una key que ni siquiera cuelga de un prefijo conocido.
        "otro-prefijo/{t}/{i}/{sha}.mseed",
    ],
)
def test_una_key_rota_de_verdad_sigue_yendo_a_la_dlq(key: str) -> None:
    concreta = key.format(t=uuid.uuid4(), i=uuid.uuid4(), sha="a" * 64)
    assert _procesa(concreta).outcome is Outcome.REJECT, concreta


# ------------------------------------------------------ y la cola, de verdad


class _FakeConn:
    """El worker no llega a usarla con un objeto ajeno; existe porque el
    consumidor la pide antes de mirar la key."""

    closed = False

    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


@pytest.fixture
def colas():
    with mock_aws():
        sqs = boto3.client("sqs", region_name=REGION)
        dlq = sqs.create_queue(QueueName="takab-dev-q-backfill-dlq")["QueueUrl"]
        arn = sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])["Attributes"][
            "QueueArn"
        ]
        q = sqs.create_queue(
            QueueName="takab-dev-q-backfill",
            Attributes={
                "VisibilityTimeout": "0",
                "RedrivePolicy": json.dumps({"deadLetterTargetArn": arn, "maxReceiveCount": "5"}),
            },
        )["QueueUrl"]
        yield sqs, q, dlq


def _pendientes(sqs, url: str) -> int:
    attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])
    return int(attrs["Attributes"]["ApproximateNumberOfMessages"])


def test_la_notificacion_exacta_de_la_dlq_se_drena_sin_dejar_nada_en_la_dlq(colas) -> None:
    """El criterio tal y como está escrito: *la DLQ de backfill no vuelve a
    recibir un PDF*. Se mide en la cola, no en el valor de retorno."""
    sqs, q, dlq = colas
    notificacion = json.dumps(
        {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": BUCKET},
                        "object": {"key": KEY_INFORME_DLQ},
                    },
                }
            ]
        }
    )
    sqs.send_message(QueueUrl=q, MessageBody=notificacion)

    consumidor = BackfillConsumer(
        q,
        dlq,
        registry=None,
        conn_factory=_FakeConn,
        settings=Settings(),
        publisher=object(),
        sqs_client=sqs,
        s3_client=_S3QueNadieDebeLeer(),
        wait_time_s=0,
    )
    stats = consumidor.process_once()

    assert stats == {"n": 1, "n_ok": 1, "n_reject": 0, "n_retry": 0, "n_lock_retries": 0}
    assert _pendientes(sqs, dlq) == 0, "el PDF volvió a la cola de mensajes muertos"
    assert _pendientes(sqs, q) == 0, "el mensaje no se borró: se reentregará hasta la DLQ"


def test_la_key_viene_url_encoded_y_el_motivo_la_dice_DESESCAPADA(colas, caplog) -> None:
    """S3 manda la key con `+` por espacio y `%XX`; el consumidor la desescapa.

    Se mide en el MOTIVO, que es donde se nota: el nombre del objeto viaja al log
    y es lo que alguien pega en la consola de S3 para buscarlo. Sin desescapar,
    la línea diría `report-technical-2026+09+08.pdf`, un objeto que no existe en
    el bucket — y el acuse seguiría saliendo verde, que es lo que hace peligroso
    este fallo.
    """
    sqs, q, dlq = colas
    real = KEY_INFORME_DLQ.replace("report-technical-20260908T224136Z", "report-technical-2026 09")
    como_llega = real.replace(" ", "+")
    notificacion = json.dumps(
        {"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": como_llega}}}]}
    )
    sqs.send_message(QueueUrl=q, MessageBody=notificacion)

    with caplog.at_level("INFO", logger="takab_api.backfill"):
        assert _consumidor(sqs, q, dlq).process_once()["n_ok"] == 1
    assert _pendientes(sqs, dlq) == 0

    # El consumidor loguea además su resumen del batch: se busca la línea del acuse.
    acuses = [r.getMessage() for r in caplog.records if "descarta con acuse" in r.getMessage()]
    assert len(acuses) == 1, [r.getMessage() for r in caplog.records]
    assert "report-technical-2026 09.pdf" in acuses[0], acuses[0]
    assert "+" not in acuses[0].rsplit("/", 1)[-1], acuses[0]


def test_el_ajeno_queda_en_el_log_con_su_motivo(caplog) -> None:
    """Regla de oro 10: por evento. Si el drenaje no deja rastro, el día que el
    prefijo gane un quinto productor nadie lo verá hasta contar objetos."""
    with caplog.at_level("INFO", logger="takab_api.backfill"):
        _procesa(KEY_INFORME_DLQ)
    mensajes = [r.getMessage() for r in caplog.records]
    assert any(KEY_INFORME_DLQ in m for m in mensajes), mensajes


# ------------------------------- «conocido y no mío» ≠ «no sé de quién es esto»


def _linea(caplog) -> tuple[str, str]:
    """El (nivel, mensaje) de la única línea que deja un objeto ajeno."""
    registros = [r for r in caplog.records if r.name.startswith("takab_api.backfill")]
    assert len(registros) == 1, [r.getMessage() for r in registros]
    return registros[0].levelname, registros[0].getMessage()


@pytest.mark.parametrize(
    ("key", "autor"),
    [
        ("evidence/{t}/{i}/report-technical-20260908T224136Z.pdf", "incidente"),
        ("evidence/{t}/drills/{i}/reporte.pdf", "simulacro"),
        ("evidence/{t}/{i}/photo-3f2504e0-4f89-41d3-9a0c-0305e82c3301.jpg", "ocupante"),
    ],
)
def test_el_ajeno_CONOCIDO_se_descarta_sin_levantar_la_voz(caplog, key: str, autor: str) -> None:
    """Rutina: el objeto tiene autor declarado en el código y es sano. INFO.

    Si esto fuera WARNING, cada informe firmado dejaría un aviso en el log y el
    aviso dejaría de significar algo — la misma erosión que la DLQ llena de
    PDF, una capa más arriba.
    """
    with caplog.at_level("INFO", logger="takab_api.backfill"):
        resultado = _procesa(key.format(t=uuid.uuid4(), i=uuid.uuid4()))
    nivel, mensaje = _linea(caplog)
    assert nivel == "INFO", mensaje
    assert autor in mensaje, f"el log no dice QUIÉN lo escribió: {mensaje}"
    assert autor in resultado.reason


def _consumidor(sqs, q: str, dlq: str) -> BackfillConsumer:
    return BackfillConsumer(
        q,
        dlq,
        registry=None,
        conn_factory=_FakeConn,
        settings=Settings(),
        publisher=object(),
        sqs_client=sqs,
        s3_client=_S3QueNadieDebeLeer(),
        wait_time_s=0,
    )


#: La key de un productor que nadie ha dado de alta: ni `.mseed`, ni CCTV, ni
#: ninguno de los tres autores declarados.
KEY_SIN_AUTOR = (
    "evidence/d0000000-0000-0000-0000-000000000001/"
    "9d82e7c8-19c3-4677-95d4-289237b1a89b/lo-que-venga-manana.bin"
)


def test_un_productor_NUEVO_del_prefijo_acaba_en_la_cola_de_mensajes_muertos(colas) -> None:
    """El fallback que NO puede declararse `ok`, medido donde queda el rastro.

    Reconocer «no es mío» por descarte —todo lo que no sea `.mseed` ni CCTV— deja
    la cola limpia, pero convertiría en INVISIBLE al productor que aparezca
    mañana: su objeto se acusaría, se borraría, y su única huella sería una línea
    de log en un contenedor. **Esa huella no existe como canal**: en todo
    `infra/terraform/` hay un solo `aws_cloudwatch_log_metric_filter`
    (`iot_rule_errors`) y no cubre a este worker, que corre en docker compose
    sobre el EC2. Lo que sí existe, desplegado y con alarma, es la DLQ.

    Así que se mide ahí: el mensaje aterriza en `takab-dev-q-backfill-dlq`, con
    su motivo en `reject_reason` y nombrando la key — y se borra de la cola de
    entrada, para no volver por reentrega hasta agotar `maxReceiveCount`.
    """
    sqs, q, dlq = colas
    sqs.send_message(
        QueueUrl=q,
        MessageBody=json.dumps(
            {"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": KEY_SIN_AUTOR}}}]}
        ),
    )

    stats = _consumidor(sqs, q, dlq).process_once()

    assert stats["n_reject"] == 1, stats
    assert stats["n_ok"] == 0, "un objeto sin autor declarado se contó como procesado"
    assert _pendientes(sqs, q) == 0, "no se borró de la cola: volvería por reentrega"

    recibidos = sqs.receive_message(
        QueueUrl=dlq, MaxNumberOfMessages=10, MessageAttributeNames=["All"]
    ).get("Messages", [])
    assert len(recibidos) == 1, "el objeto sin autor no dejó rastro consultable en la DLQ"
    (muerto,) = recibidos
    razon = muerto["MessageAttributes"]["reject_reason"]["StringValue"]
    assert KEY_SIN_AUTOR in razon, razon
    assert "DESCONOCIDO" in razon, razon
    # Y el cuerpo es la notificación original: se puede re-drenar tal cual el día
    # que alguien declare su autor.
    assert KEY_SIN_AUTOR in muerto["Body"]


def test_el_ajeno_CONOCIDO_no_deja_nada_en_la_dlq_por_el_mismo_camino(colas) -> None:
    """La otra mitad del par, por el MISMO consumidor y la MISMA cola.

    Sin este test, «rechazar lo desconocido» podría haberse implementado
    rechazándolo todo y el criterio de la ficha —*la DLQ de backfill no vuelve a
    recibir un PDF*— se caería sin que nadie lo notara.
    """
    sqs, q, dlq = colas
    sqs.send_message(
        QueueUrl=q,
        MessageBody=json.dumps(
            {"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": KEY_INFORME_DLQ}}}]}
        ),
    )

    stats = _consumidor(sqs, q, dlq).process_once()

    assert stats["n_ok"] == 1 and stats["n_reject"] == 0, stats
    assert _pendientes(sqs, dlq) == 0


def test_el_rechazo_del_desconocido_tambien_GRITA_en_el_log(caplog) -> None:
    """El log acompaña al rechazo; no lo sustituye (ese era el defecto)."""
    with caplog.at_level("INFO", logger="takab_api.backfill"):
        resultado = _procesa(KEY_SIN_AUTOR)
    assert resultado.outcome is Outcome.REJECT, resultado.reason
    nivel, mensaje = _linea(caplog)
    assert nivel == "WARNING", f"el productor nuevo pasó desapercibido en {nivel}: {mensaje}"
    assert KEY_SIN_AUTOR in mensaje


# --------------------------------------- el censo de autores, derivado del árbol


def _keys_de_evidencia_que_escribe_la_api() -> dict[str, str]:
    """Plantillas `evidence/…` que construye la API, leídas del AST.

    Se deriva del árbol A PROPÓSITO. `_AJENOS_CONOCIDOS` empareja por el nombre
    del objeto, así que un renombrado inocente en `reports.py`, `drills.py` o
    `mobile_incident.py` —o un router NUEVO que empiece a escribir bajo
    `evidence/`— dejaría de casar y su objeto acabaría en la DLQ sin que nadie lo
    hubiera decidido. Enumerar los tres a mano aquí sería repetir el censo, no
    comprobarlo.

    Devuelve ``{plantilla: fichero}``; el f-string se reconstruye poniendo `{}`
    donde va una interpolación, así que la concatenación implícita de literales
    (la de `reports.py`, partida en dos líneas) llega entera: Python la funde en
    un único ``JoinedStr``.
    """
    encontradas: dict[str, str] = {}
    for fuente in sorted(RUTA_API.rglob("*.py")):
        if RUTA_DEL_WORKER in fuente.parents:
            continue
        arbol = ast.parse(fuente.read_text("utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.JoinedStr):
                continue
            plantilla = "".join(
                trozo.value if isinstance(trozo, ast.Constant) else "{}" for trozo in nodo.values
            )
            if plantilla.startswith("evidence/"):
                encontradas[plantilla] = str(fuente.relative_to(RUTA_API))
    return encontradas


def test_el_censo_de_ajenos_se_DERIVA_del_codigo_que_escribe() -> None:
    """Cada key `evidence/…` que escribe un router está declarada en el censo.

    Si esto se pone rojo hay dos salidas honestas: declarar el autor nuevo en
    `_AJENOS_CONOCIDOS`, o aceptar que su objeto irá a la cola de mensajes
    muertos. Lo que ya no puede pasar es enterarse por la DLQ en producción.
    """
    plantillas = _keys_de_evidencia_que_escribe_la_api()
    assert plantillas, (
        "no se encontró NINGUNA key `evidence/…` en los routers: el barrido dejó de "
        "mirar donde debía y este test se volvió decorativo"
    )

    marcas = [marca for marca, _autor in _AJENOS_CONOCIDOS]
    sin_declarar = {}
    for plantilla, fichero in plantillas.items():
        nombre = plantilla.rsplit("/", 1)[-1]
        if not any(nombre.startswith(marca) for marca in marcas):
            sin_declarar[plantilla] = fichero
    assert not sin_declarar, (
        "la API escribe estas keys bajo `evidence/` y el censo `_AJENOS_CONOCIDOS` no las "
        f"reconoce por el nombre del objeto: {sin_declarar}.\n"
        "  Su `ObjectCreated` llegará al worker de backfill y acabará en "
        "`takab-dev-q-backfill-dlq`. Declara su autor o asume la DLQ, pero decídelo aquí."
    )


def test_cada_autor_declarado_SIGUE_teniendo_quien_lo_escriba() -> None:
    """El censo tampoco puede envejecer al revés: una marca que ya no escribe
    nadie es una excepción que sobrevive a su motivo, y la siguiente key que
    empiece por ahí se colaría sin autor real.

    Y de paso es el candado del barrido: si `_keys_de_evidencia_que_escribe_la_api`
    dejara de encontrar nada —un cambio de layout del paquete, un f-string que pasa
    a ser `str.format`—, las tres marcas quedarían huérfanas y esto lo diría, en vez
    de que el censo se volviera decorativo en silencio."""
    plantillas = _keys_de_evidencia_que_escribe_la_api()
    nombres = [plantilla.rsplit("/", 1)[-1] for plantilla in plantillas]
    huerfanas = [
        marca
        for marca, _autor in _AJENOS_CONOCIDOS
        if not any(nombre.startswith(marca) for nombre in nombres)
    ]
    assert not huerfanas, (
        f"estas marcas del censo ya no las escribe nadie en la API: {huerfanas}. "
        "Retíralas o corrige la marca."
    )
