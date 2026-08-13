"""Fallo TRANSITORIO de base en el worker de ingesta (T-2.132).

`T-2.130` dejó los workers **sin tope de espera por lock, a propósito**, y con
evidencia: `LockNotAvailable` es subclase de `psycopg.OperationalError`, así que
el `except` del consumidor lo trataría como **RETRY**; el mensaje vuelve a la
cola, la reentrega **quema una recepción del `maxReceiveCount`** y a la quinta
un mensaje **VÁLIDO** acaba en la **DLQ**. Esperar cuesta latencia; abortar en
bucle cuesta datos.

Aquí se construye la distinción que faltaba, **en este orden**:

1. **Fallo transitorio** — «el mensaje es bueno, la base estaba ocupada»
   (`55P03` lock, `40P01` interbloqueo, `40001` serialización). Se reintenta
   **en el sitio**, sin devolver el mensaje a la cola: la recepción ya gastada
   cubre todos los intentos, así que el `maxReceiveCount` **no se toca**. La
   palanca que lo hace posible es `ChangeMessageVisibility` — el consumidor
   tiene el `ReceiptHandle` a mano (ya lo usa para borrar) y su cliente boto3,
   así que puede alargar la invisibilidad mientras reintenta.
2. **Fallo real** — el mensaje o el mundo están rotos. Ese SÍ agota reintentos
   y acaba en la DLQ, que es donde tiene que acabar.

Y solo entonces, el tope de espera de la conexión del worker.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import boto3
import psycopg
import pytest
from moto import mock_aws

from conftest import _dsn
from takab_api.db import pool
from takab_api.db.session import WORKER_LOCK_TIMEOUT_MS
from takab_api.ingest.consumer import (
    TRANSIENT_SQLSTATES,
    SqsConsumer,
    TransientPolicy,
    es_transitorio,
)
from takab_api.settings import Settings

REGION = "us-east-2"
PRINCIPAL = "gw-sim-0001"


# ------------------------------------------------------------------- fakes


class Result:
    def __init__(self, outcome: str, reason: str = "") -> None:
        self.outcome = outcome
        self.reason = reason


class FakeConn:
    def __init__(self) -> None:
        self.closed = False
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class FakeRegistry:
    def __init__(self) -> None:
        self.ctx = object()

    def resolve(self, principal: str) -> object | None:
        return self.ctx if principal == PRINCIPAL else None


class SpySqs:
    """Cliente moto instrumentado.

    ``recepciones`` cuenta **las recepciones que realmente entregaron mensajes**
    — que es exactamente lo que incrementa ``ApproximateReceiveCount`` y, con
    ello, lo que gasta el `maxReceiveCount`. Es la cifra del criterio 1.
    """

    def __init__(self, client) -> None:
        self._client = client
        self.calls: list[str] = []
        self.recepciones = 0
        self.visibilidades: list[int] = []

    def __getattr__(self, name: str):
        real = getattr(self._client, name)

        def call(**kwargs):
            resp = real(**kwargs)
            if name == "receive_message" and resp.get("Messages"):
                self.recepciones += len(resp["Messages"])
            if name == "change_message_visibility":
                self.visibilidades.append(kwargs["VisibilityTimeout"])
            self.calls.append(name)
            return resp

        return call


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def sqs():
    with mock_aws():
        yield boto3.client("sqs", region_name=REGION)


@pytest.fixture
def queues(sqs) -> tuple[str, str]:
    """Cola + DLQ con la redrive REAL de producción (`maxReceiveCount = 5`) y
    visibilidad 0, para poder observar la reentrega sin esperar."""
    dlq = sqs.create_queue(QueueName="q-dlq")["QueueUrl"]
    arn = sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    q = sqs.create_queue(
        QueueName="q-main",
        Attributes={
            "VisibilityTimeout": "0",
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": arn, "maxReceiveCount": "5"}),
        },
    )["QueueUrl"]
    return q, dlq


def _consumer(sqs, queues, handler, *, per_message_commit=True, policy=None):
    spy = SpySqs(sqs)
    conn = FakeConn()
    kwargs = {} if policy is None else {"transient_policy": policy}
    consumer = SqsConsumer(
        queues[0],
        queues[1],
        {"feature_1s": handler},
        FakeRegistry(),
        lambda: conn,
        Settings(),
        per_message_commit,
        sqs_client=spy,
        wait_time_s=0,
        **kwargs,
    )
    return consumer, conn, spy


def _body(**overrides) -> str:
    body = {
        "station": "SIM001",
        "channel": "ENZ",
        "window_start": "2026-07-06T10:00:00+00:00",
        "pga": 0.001,
        "pgv": 0.01,
        "rms": 0.0005,
        "sta_lta": 1.1,
        "meta_principal": PRINCIPAL,
        "meta_topic": "takab/features",
        "meta_ts_iot": int(time.time() * 1000),
    }
    body.update(overrides)
    return json.dumps(body)


def _n(sqs, url: str) -> int:
    attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])
    return int(attrs["Attributes"]["ApproximateNumberOfMessages"])


def _drenar(consumer, sqs, url: str, *, vueltas: int = 12) -> list[dict]:
    """Bombea `process_once` hasta que la cola se vacía (o se agotan vueltas)."""
    stats = []
    for _ in range(vueltas):
        stats.append(consumer.process_once())
        if _n(sqs, url) == 0:
            break
    return stats


def _ocupada(sqlstate: str = "55P03") -> psycopg.OperationalError:
    """El error que lanza Postgres cuando la base está OCUPADA, no rota."""
    clase = psycopg.errors.lookup(sqlstate)
    return clase("la base está ocupada")


# ============================================================ clasificación


def test_es_transitorio_distingue_ocupada_de_rota() -> None:
    """La distinción entera de la ficha cabe en esta función.

    Los tres SQLSTATE de «ocupada» dejan la conexión VIVA y la transacción
    abortada: reintentar el MISMO mensaje es lo correcto. Una conexión caída o
    un fallo de programa no se arreglan reintentando y no deben consumir el
    presupuesto de espera.
    """
    for sqlstate in ("55P03", "40P01", "40001"):
        assert es_transitorio(_ocupada(sqlstate)), f"{sqlstate} es «base ocupada»"

    assert not es_transitorio(psycopg.OperationalError("conexión caída"))
    assert not es_transitorio(_ocupada("57P01"))  # admin_shutdown: la base se fue
    assert not es_transitorio(_ocupada("23505"))  # unique_violation: el dato es malo
    assert not es_transitorio(ValueError("ni siquiera es de la base"))


def test_el_sqlstate_del_lock_es_EL_MISMO_de_la_politica_de_session() -> None:
    """Candado contra la deriva: el 55P03 que reintenta el worker es el mismo que
    dispara el `lock_timeout` de `db/session.py`. Si allí cambiara, esto se pone
    rojo en vez de dejar dos censos que creían ser uno."""
    from takab_api.db import session as pol

    assert pol._SQLSTATE_LOCK_TIMEOUT in TRANSIENT_SQLSTATES  # noqa: SLF001


# ================================================= criterio 1 · recepciones


def test_un_fallo_transitorio_NO_gasta_ni_una_recepcion(sqs, queues) -> None:
    """**El criterio 1.** Tres bloqueos seguidos y una sola recepción gastada.

    Antes de esta ficha cada bloqueo devolvía el mensaje a la cola: cuatro
    recepciones para un mensaje que siempre fue válido, y con dos bloqueos más,
    la DLQ.
    """
    intentos = {"n": 0}

    def handler(conn, payload, meta, ctx):
        intentos["n"] += 1
        if intentos["n"] <= 3:
            raise _ocupada()
        return Result("ok")

    consumer, conn, spy = _consumer(sqs, queues, handler)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body())

    stats = consumer.process_once()

    assert intentos["n"] == 4, "el arnés no montó los tres bloqueos"
    assert stats["n_ok"] == 1 and stats["n_retry"] == 0
    assert spy.recepciones == 1, (
        f"{spy.recepciones} recepciones gastadas para UN mensaje válido: "
        "cada reentrega acerca el mensaje a la DLQ"
    )
    assert conn.commits == 1
    assert _n(sqs, queues[0]) == 0 and _n(sqs, queues[1]) == 0


def test_un_fallo_transitorio_no_manda_un_mensaje_VALIDO_a_la_DLQ(sqs, queues) -> None:
    """Cinco bloqueos = `maxReceiveCount` entero. Es el desenlace exacto que
    `T-2.130` midió y por el que no puso tope a los workers."""
    intentos = {"n": 0}

    def handler(conn, payload, meta, ctx):
        intentos["n"] += 1
        if intentos["n"] <= 5:
            raise _ocupada()
        return Result("ok")

    consumer, conn, spy = _consumer(sqs, queues, handler)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body())

    _drenar(consumer, sqs, queues[0])

    assert _n(sqs, queues[1]) == 0, "un mensaje VÁLIDO acabó en la DLQ por un lock pasajero"
    assert intentos["n"] == 6 and conn.commits == 1
    assert spy.recepciones == 1


def test_el_reintento_en_el_sitio_alarga_la_visibilidad(sqs, queues) -> None:
    """La palanca, explícita: mientras se reintenta, el mensaje sigue EN VUELO.

    Sin esto el mensaje se haría visible a mitad del reintento, otro worker lo
    tomaría —gastando la recepción que estábamos ahorrando— y los dos harían el
    mismo trabajo a la vez.
    """
    intentos = {"n": 0}

    def handler(conn, payload, meta, ctx):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise _ocupada()
        return Result("ok")

    consumer, _, spy = _consumer(sqs, queues, handler)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body())

    consumer.process_once()

    assert spy.visibilidades == [TransientPolicy().inflight_visibility_s]


def test_la_transaccion_abortada_se_tira_antes_de_reintentar(sqs, queues) -> None:
    """Detalle que no es cosmético: tras un 55P03 la transacción queda ABORTADA
    y Postgres rechaza cualquier sentencia posterior. Sin el rollback, el
    reintento fallaría por una razón distinta y el arreglo no serviría de nada."""
    intentos = {"n": 0}

    def handler(conn, payload, meta, ctx):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise _ocupada()
        return Result("ok")

    consumer, conn, _ = _consumer(sqs, queues, handler)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body())

    consumer.process_once()

    assert conn.rollbacks >= 1, "se reintentó sobre una transacción abortada"


# ======================================================= criterio 1 · falla real


def test_un_fallo_REAL_sigue_agotando_reintentos_y_acaba_en_la_DLQ(sqs, queues) -> None:
    """El control. Si TODO se reintentara en el sitio, un mensaje envenenado
    dejaría el worker girando para siempre y la DLQ dejaría de servir para nada.

    Un `OperationalError` que NO es «base ocupada» (aquí, la conexión caída) no
    consume el presupuesto de espera: se devuelve a la cola como siempre y la
    redrive policy hace su trabajo.
    """

    def handler(conn, payload, meta, ctx):
        raise psycopg.OperationalError("la base se fue")

    consumer, _, spy = _consumer(sqs, queues, handler)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body())

    _drenar(consumer, sqs, queues[0])

    assert _n(sqs, queues[1]) == 1, "un fallo REAL debe acabar en la DLQ"
    assert spy.recepciones >= 5, "el fallo real sí gasta las recepciones, y debe"
    assert spy.visibilidades == [], "un fallo real no merece alargues de visibilidad"


def test_un_bloqueo_que_NO_cede_devuelve_el_mensaje_con_respiro(sqs, queues) -> None:
    """Presupuesto agotado ⇒ ya no es «transitorio»: es un lock atascado.

    El mensaje vuelve a la cola (no se borra ni se copia a la DLQ), pero con la
    visibilidad alargada: así las cinco recepciones se reparten en minutos en
    vez de quemarse en cinco segundos contra una tabla que sigue bloqueada.
    """
    intentos = {"n": 0}

    def handler(conn, payload, meta, ctx):
        intentos["n"] += 1
        raise _ocupada()

    politica = TransientPolicy(
        budget_s=0.3, base_delay_s=0.05, max_delay_s=0.05, giveup_visibility_s=1
    )
    consumer, conn, spy = _consumer(sqs, queues, handler, policy=politica)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body())

    stats = consumer.process_once()

    assert intentos["n"] >= 2, "no llegó a reintentar: el presupuesto es demasiado corto"
    assert stats["n_retry"] == 1 and stats["n_ok"] == 0
    assert conn.commits == 0
    assert _n(sqs, queues[1]) == 0, "un lock atascado no es un mensaje inválido"
    # El respiro es observable: recién soltado no se puede recibir; al vencer, sí.
    assert spy.visibilidades[-1] == 1
    assert sqs.receive_message(QueueUrl=queues[0]).get("Messages", []) == []
    time.sleep(1.2)
    assert len(sqs.receive_message(QueueUrl=queues[0]).get("Messages", [])) == 1


# ============================================================ modo batch


def test_en_modo_batch_el_transitorio_rehace_los_pendientes(sqs, queues) -> None:
    """`q-telemetry` acumula OK sin commitear. Un 55P03 tira la transacción y con
    ella el trabajo ya hecho de esos pendientes.

    Rehacerlos en el sitio es correcto —los handlers son idempotentes por PK
    (regla de oro 3)— y es lo único que evita que un bloqueo a mitad de batch
    queme una recepción **por cada mensaje del batch**.
    """
    vistos: list[str] = []
    fallado = {"ya": False}

    def handler(conn, payload, meta, ctx):
        vistos.append(payload["channel"])
        if payload["channel"] == "ENN" and not fallado["ya"]:
            fallado["ya"] = True
            raise _ocupada()
        return Result("ok")

    consumer, conn, spy = _consumer(sqs, queues, handler, per_message_commit=False)
    for ch in ("ENZ", "ENN", "ENE"):
        sqs.send_message(QueueUrl=queues[0], MessageBody=_body(channel=ch))

    consumer.process_once()

    assert vistos == ["ENZ", "ENN", "ENZ", "ENN", "ENE"], (
        f"el pendiente no se rehízo tras el rollback: {vistos}"
    )
    assert conn.commits == 1, "sigue siendo UN commit por batch"
    assert spy.recepciones == 3, "tres mensajes, tres recepciones: ninguna extra"
    assert _n(sqs, queues[0]) == 0 and _n(sqs, queues[1]) == 0


def test_en_modo_batch_un_bloqueo_atascado_no_borra_lo_que_no_commiteo(sqs, queues) -> None:
    """La trampa del modo batch: si al rendirse se borraran los pendientes, se
    borrarían mensajes cuyo trabajo se fue en el rollback. Pérdida de datos."""

    def handler(conn, payload, meta, ctx):
        if payload["channel"] == "ENN":
            raise _ocupada()
        return Result("ok")

    politica = TransientPolicy(
        budget_s=0.2, base_delay_s=0.05, max_delay_s=0.05, giveup_visibility_s=0
    )
    consumer, conn, _ = _consumer(sqs, queues, handler, per_message_commit=False, policy=politica)
    for ch in ("ENZ", "ENN"):
        sqs.send_message(QueueUrl=queues[0], MessageBody=_body(channel=ch))

    stats = consumer.process_once()

    assert conn.commits == 0, "no había nada durable que commitear"
    assert stats["n_ok"] == 0 and stats["n_retry"] == 2
    assert _n(sqs, queues[0]) == 2, "los dos mensajes deben seguir en la cola"
    assert _n(sqs, queues[1]) == 0


def test_el_COMMIT_del_batch_tambien_esta_cubierto(sqs, queues) -> None:
    """El sitio más probable del 40001 en `q-telemetry` no es el handler: es el
    commit, que es donde aterrizan de golpe las escrituras de los diez mensajes.

    Sin red aquí, un fallo transitorio en el commit reentregaría el batch entero
    y quemaría una recepción **por cada uno de los diez**.
    """
    commits = {"n": 0}
    vistos: list[str] = []

    class ConnQueFallaAlCommitear(FakeConn):
        def commit(self) -> None:
            commits["n"] += 1
            if commits["n"] == 1:
                raise _ocupada("40001")
            super().commit()

    conn = ConnQueFallaAlCommitear()
    spy = SpySqs(sqs)

    def handler(c, payload, meta, ctx):
        vistos.append(payload["channel"])
        return Result("ok")

    consumer = SqsConsumer(
        queues[0],
        queues[1],
        {"feature_1s": handler},
        FakeRegistry(),
        lambda: conn,
        Settings(),
        False,
        sqs_client=spy,
        wait_time_s=0,
    )
    for ch in ("ENZ", "ENN"):
        sqs.send_message(QueueUrl=queues[0], MessageBody=_body(channel=ch))

    stats = consumer.process_once()

    assert vistos == ["ENZ", "ENN", "ENZ", "ENN"], f"el batch no se rehízo: {vistos}"
    assert conn.commits == 1 and commits["n"] == 2
    assert stats["n_ok"] == 2 and stats["n_retry"] == 0
    assert spy.recepciones == 2, "dos mensajes, dos recepciones: ninguna extra"
    assert _n(sqs, queues[0]) == 0 and _n(sqs, queues[1]) == 0


# =========================================== criterio 2 · tope de los workers


def test_la_conexion_del_worker_hoy_esperaria_para_siempre_sin_el_tope() -> None:
    """El estado que `T-2.130` dejó declarado, medido contra Postgres: la
    conexión que fabrica `db/pool.py` no lleva `lock_timeout` — `0` es «espera
    ilimitada»."""
    with pool.connect(_dsn()) as conn:
        assert conn.execute("SHOW lock_timeout").fetchone()["lock_timeout"] == "0"


def test_el_tope_del_worker_sale_de_la_politica_UNICA() -> None:
    """El número no se escribe en `pool.py`: se pide a `db/session.py`, donde ya
    viven el del request y el del segundo plano."""
    with pool.connect(_dsn(), lock_timeout_ms=WORKER_LOCK_TIMEOUT_MS) as conn:
        aplicado = conn.execute("SHOW lock_timeout").fetchone()["lock_timeout"]
    assert aplicado == f"{WORKER_LOCK_TIMEOUT_MS // 1000}s"


def test_el_tope_del_worker_sobrevive_a_un_rollback() -> None:
    """No es paranoia: un `SET` dentro de una transacción se DESHACE al hacer
    rollback, y el worker hace rollback en cada RETRY. Por eso el tope viaja
    como parámetro de arranque de la conexión y no como sentencia."""
    with pool.connect(_dsn(), lock_timeout_ms=WORKER_LOCK_TIMEOUT_MS) as conn:
        conn.execute("SELECT 1")
        conn.rollback()
        assert conn.execute("SHOW lock_timeout").fetchone()["lock_timeout"] != "0"


def test_el_worker_de_ingesta_arranca_con_el_tope_puesto(monkeypatch) -> None:
    """El cableado, no solo la capacidad: el proceso real lo lleva puesto."""
    from takab_api.ingest import __main__ as entry

    monkeypatch.setenv("TAKAB_API_QUEUE_URL_EVENTS", "https://sqs.test/q-events")
    monkeypatch.setenv("TAKAB_API_DLQ_URL_EVENTS", "https://sqs.test/q-events-dlq")
    monkeypatch.setenv("TAKAB_API_DATABASE_URL", _dsn())
    with mock_aws():
        consumidor = entry.build_consumer("events", Settings())
    with consumidor._conn_factory() as conn:  # noqa: SLF001 - es el punto del test
        assert conn.execute("SHOW lock_timeout").fetchone()["lock_timeout"] != "0"


def test_el_presupuesto_de_reintento_cabe_en_la_visibilidad_de_la_cola() -> None:
    """El criterio duro del escalón del worker, y NO es el del request.

    Al worker no le limita el pool —tiene conexión propia— sino el
    `VisibilityTimeout` de su cola: si los reintentos en el sitio duraran más,
    el mensaje se haría visible, otro worker lo tomaría y se gastaría justo la
    recepción que se estaba ahorrando. El número se lee del Terraform REAL, no
    de una copia en este fichero.
    """
    tf = Path(__file__).resolve().parents[2] / "infra/terraform/modules/messaging/main.tf"
    visibilidades = [
        int(m) for m in re.findall(r"visibility_timeout\s*=\s*(\d+)", tf.read_text("utf-8"))
    ]
    assert visibilidades, f"no se pudo leer la visibilidad real de {tf}"
    politica = TransientPolicy()
    assert politica.budget_s < min(visibilidades), (
        f"presupuesto {politica.budget_s} s ≥ visibilidad mínima {min(visibilidades)} s: "
        "el mensaje se haría visible a mitad del reintento"
    )
    assert politica.inflight_visibility_s > politica.budget_s, (
        "el alargue debe cubrir el presupuesto entero o el mensaje se escapa a mitad"
    )
    assert WORKER_LOCK_TIMEOUT_MS / 1000.0 < politica.budget_s, (
        "una sola espera por lock no puede agotar el presupuesto de reintentos"
    )


# ================================================== los dos criterios, juntos


@pytest.mark.parametrize("retencion_s", [4.0])
def test_un_lock_REAL_que_cede_no_cuesta_ni_un_mensaje(sqs, queues, retencion_s) -> None:
    """La ficha entera contra Postgres de verdad, sin errores fabricados.

    Un tercero retiene `gateways` en ACCESS EXCLUSIVE y el handler tiene que
    leer esa tabla, así que se bloquea de verdad: el 55P03 lo emite Postgres, no
    este fichero. Con el tope puesto, el worker CEDE a los 3 s —sin quedarse con
    una transacción abierta que pueda ser el extremo lejano de un ciclo tipo
    `T-2.73.c`—, reintenta en el sitio, y cuando el tercero suelta, el mensaje
    entra. Ni una recepción de más, DLQ vacía.
    """
    import threading

    factory = lambda: pool.connect(_dsn(), lock_timeout_ms=WORKER_LOCK_TIMEOUT_MS)  # noqa: E731
    esperas: list[float] = []

    def handler(conn, payload, meta, ctx):
        arranque = time.monotonic()
        try:
            conn.execute("SELECT 1 FROM gateways LIMIT 1")
        finally:
            esperas.append(time.monotonic() - arranque)
        return Result("ok")

    bloqueador = psycopg.connect(_dsn())
    bloqueador.execute("LOCK TABLE gateways IN ACCESS EXCLUSIVE MODE")
    # El arnés se confirma A SÍ MISMO, sin preguntarle a ninguna vista del
    # servidor (lección de T-2.131): una sonda con tope corto DEBE rebotar con
    # 55P03. Si no rebota, el bloqueo no existe y el test no probaría nada.
    with pool.connect(_dsn(), lock_timeout_ms=250) as sonda:
        with pytest.raises(psycopg.errors.LockNotAvailable):
            sonda.execute("SELECT 1 FROM gateways LIMIT 1")

    soltar = threading.Timer(retencion_s, lambda: (bloqueador.rollback(), bloqueador.close()))
    soltar.start()
    try:
        spy = SpySqs(sqs)
        consumer = SqsConsumer(
            queues[0],
            queues[1],
            {"feature_1s": handler},
            FakeRegistry(),
            factory,
            Settings(),
            per_message_commit=True,
            sqs_client=spy,
            wait_time_s=0,
        )
        sqs.send_message(QueueUrl=queues[0], MessageBody=_body())

        inicio = time.monotonic()
        stats = consumer.process_once()
        esperado = time.monotonic() - inicio
    finally:
        soltar.cancel()
        if not bloqueador.closed:
            bloqueador.rollback()
            bloqueador.close()

    assert esperado >= retencion_s * 0.8, "no llegó a esperar: el bloqueo no se montó"
    # El tope hizo su trabajo: ninguna espera individual llegó a «para siempre».
    assert esperas[0] < WORKER_LOCK_TIMEOUT_MS / 1000.0 + 1.0, (
        f"la primera espera duró {esperas[0]:.1f} s: el tope no se aplicó"
    )
    assert stats["n_ok"] == 1, f"el mensaje no entró tras soltarse el lock: {stats}"
    assert stats["n_lock_retries"] >= 1
    assert spy.recepciones == 1, "el lock real gastó recepciones"
    assert _n(sqs, queues[1]) == 0
    assert spy.visibilidades, "no se alargó la visibilidad mientras se esperaba"
