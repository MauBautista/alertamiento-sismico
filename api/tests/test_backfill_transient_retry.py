"""`backfill` consume cola y no tiene ni política de reintento ni tope (T-2.139).

`T-2.132` le dio a `ingest` la política de reintento en el sitio y `T-2.136` el
tope de sentencia. **A `backfill` no le dieron ninguna de las dos**, y `T-2.136`
dejó escrita la razón de por qué el tope no podía ir primero: su
`VisibilityTimeout` es **300 s** (10× el de eventos), su trabajo es **a granel**
(objeto de S3 → NDJSON → filas) y **no tiene política de reintento**, así que un
`57014` allí sería *una recepción quemada por una sentencia quizá legítima*.

El orden de esta ficha es el de aquella, y no es un capricho:

1. **La medición** — cuánto tarda de verdad una pasada sobre un objeto
   representativo, y —lo que decide la ficha— **cuánto tarda la sentencia más
   lenta de esa pasada**, que es lo único que un `statement_timeout` acota.
2. **La política de reintento**, como la de `T-2.132`: distinción por SQLSTATE,
   reintento dentro de la recepción ya gastada, `ChangeMessageVisibility` para
   sostener la invisibilidad, `rollback` antes de reintentar y el commit
   cubierto.
3. **Y solo entonces**, los topes — cada uno con su veredicto, derivado de lo
   medido en (1) y no de un número elegido.

El objeto representativo **no se inventa**: sale de los ajustes reales del edge
(`edge/takab_edge/config/settings.py`) y las visibilidades salen del Terraform
real (`infra/terraform/modules/messaging/main.tf`), leídos aquí y no copiados.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
import psycopg
import pytest
from moto import mock_aws
from psycopg.rows import dict_row

from conftest import _dsn
from takab_api.backfill import consumer as backfill_consumer
from takab_api.backfill.consumer import BackfillConsumer
from takab_api.backfill.objects import process_s3_object
from takab_api.db.session import WORKER_LOCK_TIMEOUT_MS
from takab_api.ingest.handlers import GatewayCtx, Outcome, SensorRef
from takab_api.settings import Settings

REGION = "us-east-2"
BUCKET = "takab-dev-transfer"
TS0 = datetime(2026, 7, 7, 6, 0, 0, tzinfo=UTC)

_RAIZ = Path(__file__).resolve().parents[2]
_TF_MESSAGING = _RAIZ / "infra/terraform/modules/messaging/main.tf"
_EDGE_SETTINGS = _RAIZ / "edge/takab_edge/config/settings.py"


# ------------------------------------------------- los números, de donde viven


def _visibilidades() -> dict[str, int]:
    """`VisibilityTimeout` por cola, del Terraform REAL y no de una copia."""
    texto = _TF_MESSAGING.read_text("utf-8")
    pares = re.findall(r"(\w+)\s*=\s*\{\s*visibility_timeout\s*=\s*(\d+)\s*\}", texto)
    assert pares, f"no se pudieron leer las visibilidades de {_TF_MESSAGING}"
    return {nombre: int(v) for nombre, v in pares}


def _ajuste_edge(nombre: str) -> float:
    """Un `default=` de `EdgeSettings`, leído del fichero real del edge.

    Se lee en vez de copiarse por lo mismo que las visibilidades: el día que el
    edge cambie de cadencia o de umbral, el objeto «representativo» de este
    fichero deja de serlo **en silencio** si el número vive aquí.
    """
    texto = _EDGE_SETTINGS.read_text("utf-8")
    m = re.search(rf"^\s*{nombre}:\s*\w+\s*=\s*Field\(default=([\d.]+)", texto, re.M)
    assert m, f"no se pudo leer {nombre} de {_EDGE_SETTINGS}"
    return float(m.group(1))


def _canales_edge() -> list[str]:
    texto = _EDGE_SETTINGS.read_text("utf-8")
    m = re.search(r"^\s*seedlink_channels:\s*list\[str\]\s*=\s*\[([^\]]+)\]", texto, re.M)
    assert m, f"no se pudieron leer los canales de {_EDGE_SETTINGS}"
    return re.findall(r'"([^"]+)"', m.group(1))


# ---------------------------------------------------------------------- fakes


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.gets = 0

    def put(self, bucket: str, key: str, body: bytes) -> None:
        self.objects[(bucket, key)] = body

    def get_object(self, Bucket: str, Key: str) -> dict:  # noqa: N803 — firma boto3
        self.gets += 1
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}


class _FakeRegistry:
    def __init__(self, ctx_by_thing: dict[str, GatewayCtx]) -> None:
        self._ctx = ctx_by_thing

    def resolve(self, principal: str) -> GatewayCtx | None:
        return self._ctx.get(principal)


class FakeConn:
    """Conexión de mentira para los tests de política (los de SQS, no los de DB)."""

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


class SpySqs:
    """Cliente moto instrumentado; `recepciones` es lo que gasta el maxReceiveCount."""

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


class ConnCronometrada:
    """Proxy que cronometra **cada sentencia** de la pasada.

    Es la mitad que decide la ficha: `statement_timeout` no acota una pasada ni
    una recepción — acota **una sentencia**. Sin medir esto por separado, «la
    pasada tarda X» no dice nada sobre si el tope sirve de algo.
    """

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn
        self.sentencias = 0
        self.peor_s = 0.0
        self.total_s = 0.0

    def execute(self, *args, **kwargs):
        arranque = time.perf_counter()
        try:
            return self._conn.execute(*args, **kwargs)
        finally:
            dt = time.perf_counter() - arranque
            self.sentencias += 1
            self.total_s += dt
            self.peor_s = max(self.peor_s, dt)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


# ------------------------------------------------------------------- escenario


class _Scenario:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
        self.tenant = str(uuid.uuid4())
        self.site = str(uuid.uuid4())
        self.gateway = str(uuid.uuid4())
        self.sensor = str(uuid.uuid4())
        self.station = f"BT{uuid.uuid4().hex[:5].upper()}"
        self.thing = f"gw-bt-{self.gateway[:8]}"

    def seed(self) -> None:
        c = self.conn
        c.execute("RESET ROLE")
        c.execute(
            "INSERT INTO tenants (tenant_id, code, name) VALUES (%s,%s,'BT Test')",
            (self.tenant, self.tenant[:8]),
        )
        c.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
            "(%s,%s,%s,'S', ST_SetSRID(ST_MakePoint(-101.5,11.5),4326)::geography)",
            (self.site, self.tenant, f"BT-{self.site[:8]}"),
        )
        c.execute(
            "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial, iot_thing) "
            "VALUES (%s,%s,%s,%s,%s)",
            (self.gateway, self.tenant, self.site, self.thing, self.thing),
        )
        c.execute(
            "INSERT INTO sensors (sensor_id, tenant_id, site_id, gateway_id, kind, "
            "model, serial) VALUES (%s,%s,%s,%s,'structural','RS4D',%s)",
            (self.sensor, self.tenant, self.site, self.gateway, self.station),
        )
        c.commit()
        c.execute("SET ROLE takab_ingest")  # paridad con el worker real

    def ctx(self) -> GatewayCtx:
        return GatewayCtx(
            gateway_id=uuid.UUID(self.gateway),
            gateway_serial=self.thing,
            iot_thing=self.thing,
            tenant_id=uuid.UUID(self.tenant),
            tenant_code=self.tenant[:8],
            site_id=uuid.UUID(self.site),
            site_code="BT",
            sensors={
                self.station: SensorRef(
                    sensor_id=uuid.UUID(self.sensor),
                    site_id=uuid.UUID(self.site),
                    site_code="BT",
                )
            },
        )

    def filas(self) -> int:
        return self.conn.execute(
            "SELECT count(*) FROM waveform_features_1s WHERE tenant_id = %s", (self.tenant,)
        ).fetchone()["count"]


@pytest.fixture
def scenario() -> Iterator[_Scenario]:
    conn = psycopg.connect(_dsn(), autocommit=False, row_factory=dict_row)
    sc = _Scenario(conn)
    try:
        sc.seed()
        yield sc
    finally:
        _cleanup(conn, sc.tenant)
        conn.close()


def _cleanup(conn: psycopg.Connection, tenant: str) -> None:
    conn.rollback()
    conn.execute("RESET ROLE")
    try:
        conn.execute("SET session_replication_role = 'replica'")
        for table in (
            "waveform_features_1s",
            "sensors",
            "gateways",
            "sites",
            "tenants",
        ):
            conn.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (tenant,))  # noqa: S608
        conn.execute("SET session_replication_role = 'origin'")
        conn.commit()
    except psycopg.Error:
        conn.rollback()


# ---------------------------------------------- el objeto REPRESENTATIVO


def _objeto_representativo(
    sc: _Scenario, *, segundos: float, desde: int = 0
) -> tuple[bytes, int, int]:
    """NDJSON.gz igual al que sube el edge; devuelve (cuerpo, líneas, filas).

    La forma sale de los ajustes REALES del edge, no de una elección de este
    fichero: el batcher publica un ``feature_batch`` cada
    ``cloud_features_batch_s`` con un feature por cada canal de
    ``seedlink_channels`` y por segundo. ``segundos`` es la duración de la caída
    que se está reproduciendo.

    ``desde`` desplaza la ventana temporal: dos pasadas del MISMO test tienen que
    escribir filas distintas o la PK ``(ts, sensor_id, channel)`` las colapsa por
    ON CONFLICT y la segunda medición mediría un no-trabajo (es lo que hace que
    la re-ingesta sea segura, y aquí sería una medición vacía).
    """
    cadencia = _ajuste_edge("cloud_features_batch_s")
    canales = _canales_edge()
    por_lote = int(cadencia) * len(canales)
    origen = TS0 + timedelta(seconds=desde)
    lineas: list[str] = []
    segundo = 0
    while segundo < int(segundos):
        features = [
            {
                "station": sc.station,
                "channel": canal,
                "window_start": (origen + timedelta(seconds=segundo + i)).isoformat(),
                "pga": 0.01,
                "pgv": 0.1,
                "rms": 0.001,
                "sta_lta": 1.0,
                "clipping": False,
                "health_score": 1.0,
            }
            for i in range(int(cadencia))
            for canal in canales
        ]
        lineas.append(
            json.dumps(
                {
                    "topic": "takab/features/batch",
                    "event_id": "",
                    "payload": {
                        "gateway_id": sc.thing,
                        "features": features,
                        "batched_at": (
                            origen + timedelta(seconds=segundo + int(cadencia))
                        ).isoformat(),
                    },
                    "spooled_at": (
                        origen + timedelta(seconds=segundo + int(cadencia) + 1)
                    ).isoformat(),
                }
            )
        )
        segundo += int(cadencia)
    cuerpo = gzip.compress("\n".join(lineas).encode())
    return cuerpo, len(lineas), len(lineas) * por_lote


def _pasada(sc: _Scenario, *, segundos: float, desde: int = 0) -> dict[str, float]:
    """Corre UNA pasada real contra Postgres y devuelve sus cifras."""
    cuerpo, n_lineas, n_filas = _objeto_representativo(sc, segundos=segundos, desde=desde)
    key = f"backfill/{sc.thing}/{uuid.uuid4().hex}.ndjson.gz"
    s3 = _FakeS3()
    s3.put(BUCKET, key, cuerpo)
    reloj = ConnCronometrada(sc.conn)
    antes = sc.filas()
    arranque = time.perf_counter()
    resultado = process_s3_object(
        reloj, BUCKET, key, _FakeRegistry({sc.thing: sc.ctx()}), Settings(), s3_client=s3
    )
    duracion = time.perf_counter() - arranque
    assert resultado.outcome is Outcome.OK, resultado.reason
    escritas = sc.filas() - antes
    assert escritas == n_filas, f"la pasada escribió {escritas} filas y esperaba {n_filas}"
    return {
        "segundos_caida": float(int(segundos)),
        "lineas": float(n_lineas),
        "filas": float(n_filas),
        "pasada_s": duracion,
        "sentencias": float(reloj.sentencias),
        "peor_sentencia_s": reloj.peor_s,
        "bytes_gz": float(len(cuerpo)),
    }


# ================================================================ 1 · LA MEDICIÓN


def test_medicion_pasada_real_sobre_un_objeto_representativo(scenario, capsys) -> None:
    """**El criterio 1.** Una pasada de verdad, con las cifras impresas.

    Representativo = la caída MÍNIMA que toma la ruta S3: el edge manda el spool
    por S3 cuando acumula más de ``backfill_threshold_s`` de datos; por debajo de
    eso el spool sale por MQTT y esta cola ni se entera. O sea que este objeto no
    es «uno grande elegido a ojo»: es el **suelo** de lo que llega aquí.
    """
    umbral = _ajuste_edge("backfill_threshold_s")
    m = _pasada(scenario, segundos=umbral)
    vt = _visibilidades()["backfill"]

    with capsys.disabled():
        print(
            f"\n[T-2.139] pasada representativa ({int(umbral)} s de caída):"
            f"\n  líneas NDJSON ............ {int(m['lineas'])}"
            f"\n  filas escritas ........... {int(m['filas'])}"
            f"\n  objeto (.ndjson.gz) ...... {int(m['bytes_gz'])} B"
            f"\n  PASADA COMPLETA .......... {m['pasada_s']:.3f} s"
            f"\n  sentencias ............... {int(m['sentencias'])}"
            f"\n  SENTENCIA MÁS LENTA ...... {m['peor_sentencia_s'] * 1000:.3f} ms"
            f"\n  VisibilityTimeout backfill {vt} s"
            f"\n  margen ................... ×{vt / m['pasada_s']:.0f}"
        )

    assert m["pasada_s"] < vt, (
        f"la pasada representativa ({m['pasada_s']:.1f} s) ya no cabe en el "
        f"VisibilityTimeout de su cola ({vt} s): el mensaje se reentregaría con "
        "el worker todavía trabajando"
    )
    # El arnés midió ALGO: una pasada de 0 s no distinguiría nada.
    assert m["pasada_s"] > 0 and m["sentencias"] >= m["filas"]


def test_la_pasada_escala_con_las_filas_y_la_SENTENCIA_no(scenario, capsys) -> None:
    """**Dos juegos de centinelas**, que es lo que distingue una función de una
    constante (la lección del literal `1077`).

    Y es la medición que decide el veredicto del tope: al multiplicar el tamaño
    del objeto, **la pasada crece y la sentencia más lenta NO**. Lo que hace larga
    a una pasada de backfill no es ninguna sentencia lenta: son muchas sentencias
    cortas dentro de **una sola transacción**.
    """
    umbral = _ajuste_edge("backfill_threshold_s")
    chico = _pasada(scenario, segundos=umbral)
    grande = _pasada(scenario, segundos=umbral * 4, desde=100_000)

    factor_filas = grande["filas"] / chico["filas"]
    factor_pasada = grande["pasada_s"] / chico["pasada_s"]

    with capsys.disabled():
        print(
            f"\n[T-2.139] dos centinelas:"
            f"\n  {int(chico['filas'])} filas → {chico['pasada_s']:.3f} s "
            f"(peor sentencia {chico['peor_sentencia_s'] * 1000:.3f} ms)"
            f"\n  {int(grande['filas'])} filas → {grande['pasada_s']:.3f} s "
            f"(peor sentencia {grande['peor_sentencia_s'] * 1000:.3f} ms)"
            f"\n  ×{factor_filas:.0f} filas ⇒ ×{factor_pasada:.1f} pasada"
            f"\n  µs por fila: {chico['pasada_s'] / chico['filas'] * 1e6:.0f} → "
            f"{grande['pasada_s'] / grande['filas'] * 1e6:.0f}"
        )

    assert factor_pasada > 2.0, (
        f"×{factor_filas:.0f} filas solo multiplicó la pasada por {factor_pasada:.1f}: "
        "si la pasada no dependiera del tamaño, esta medición no mediría el trabajo"
    )
    # El punto: la sentencia individual NO crece con el objeto.
    assert grande["peor_sentencia_s"] < chico["pasada_s"], (
        "la sentencia más lenta creció hasta el orden de la pasada entera: si eso "
        "pasa de verdad, el veredicto sobre el statement_timeout hay que rehacerlo"
    )


def test_un_statement_timeout_NO_acotaria_la_pasada_de_backfill(scenario, capsys) -> None:
    """**La medición que decide el criterio 2**, y contradice la intuición.

    El modo de fallo que `T-2.136` persigue es que la pasada se pase del
    `VisibilityTimeout` y SQS reentregue el mensaje mientras el worker sigue.
    Un `statement_timeout` **no puede evitar eso** en backfill: acota una
    sentencia, y aquí ninguna sentencia se acerca a la pasada. Para que el tope
    llegara a dispararse, una sola sentencia tendría que tardar órdenes de
    magnitud más que la peor medida — o sea, ya no sería este trabajo.
    """
    umbral = _ajuste_edge("backfill_threshold_s")
    m = _pasada(scenario, segundos=umbral)
    proporcion = m["peor_sentencia_s"] / m["pasada_s"]

    with capsys.disabled():
        print(
            f"\n[T-2.139] la sentencia más lenta es el {proporcion * 100:.2f} % de la pasada "
            f"({m['peor_sentencia_s'] * 1000:.3f} ms de {m['pasada_s']:.3f} s)"
        )

    assert proporcion < 0.10, (
        f"la peor sentencia es el {proporcion * 100:.0f} % de la pasada: si una sola "
        "sentencia dominara el trabajo, un statement_timeout SÍ acotaría la pasada "
        "y el veredicto de esta ficha habría que rehacerlo"
    )


def test_la_caida_que_haria_a_la_pasada_pasarse_de_su_visibilidad(scenario, capsys) -> None:
    """El otro lado de la medición: **cuánto tendría que durar la caída** para
    que la pasada se pasara de los 300 s. Es la cifra que hay que vigilar, y la
    que un `statement_timeout` no cambia ni un segundo."""
    umbral = _ajuste_edge("backfill_threshold_s")
    m = _pasada(scenario, segundos=umbral)
    vt = _visibilidades()["backfill"]
    horas = (vt / m["pasada_s"]) * m["segundos_caida"] / 3600.0

    with capsys.disabled():
        print(
            f"\n[T-2.139] al ritmo medido, la pasada llegaría a los {vt} s de "
            f"VisibilityTimeout con una caída de ~{horas:.1f} h de spool en UN objeto"
        )

    assert horas > 1.0, (
        f"bastarían {horas:.2f} h de caída para que la pasada se pase de su "
        "visibilidad: el riesgo deja de ser teórico y la ficha necesita otro arreglo "
        "(trocear el objeto), que un statement_timeout tampoco daría"
    )


# ======================================= 2 · LA POLÍTICA DE REINTENTO (T-2.132)


@pytest.fixture
def sqs():
    with mock_aws():
        yield boto3.client("sqs", region_name=REGION)


@pytest.fixture
def queues(sqs) -> tuple[str, str]:
    """Cola + DLQ con la redrive REAL de producción (`maxReceiveCount = 5`) y
    visibilidad 0, para observar la reentrega sin esperar."""
    dlq = sqs.create_queue(QueueName="q-backfill-dlq")["QueueUrl"]
    arn = sqs.get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    q = sqs.create_queue(
        QueueName="q-backfill",
        Attributes={
            "VisibilityTimeout": "0",
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": arn, "maxReceiveCount": "5"}),
        },
    )["QueueUrl"]
    return q, dlq


def _consumer(sqs, queues, *, conn=None, policy=None):
    spy = SpySqs(sqs)
    conn = conn if conn is not None else FakeConn()
    kwargs = {} if policy is None else {"transient_policy": policy}
    consumidor = BackfillConsumer(
        queues[0],
        queues[1],
        _FakeRegistry({}),
        lambda: conn,
        Settings(),
        publisher=object(),
        sqs_client=spy,
        s3_client=_FakeS3(),
        wait_time_s=0,
        **kwargs,
    )
    return consumidor, conn, spy


def _body_s3(key: str = "backfill/gw-bt-0001/x.ndjson.gz") -> str:
    return json.dumps({"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": key}}}]})


def _n(sqs, url: str) -> int:
    attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])
    return int(attrs["Attributes"]["ApproximateNumberOfMessages"])


def _drenar(consumidor, sqs, url: str, *, vueltas: int = 12) -> list[dict]:
    stats = []
    for _ in range(vueltas):
        stats.append(consumidor.process_once())
        if _n(sqs, url) == 0:
            break
    return stats


def _ocupada(sqlstate: str = "55P03") -> psycopg.OperationalError:
    return psycopg.errors.lookup(sqlstate)("la base está ocupada")


def _fake_objeto(monkeypatch, fallos: int, sqlstate: str = "55P03") -> dict[str, int]:
    """Sustituye `process_s3_object` por uno que falla `fallos` veces y luego OK."""
    from takab_api.backfill.objects import ObjectResult

    contador = {"n": 0}

    def falso(conn, bucket, key, registry, settings, *, s3_client):
        contador["n"] += 1
        if contador["n"] <= fallos:
            raise _ocupada(sqlstate)
        conn.commit()
        return ObjectResult(Outcome.OK, ok=1)

    monkeypatch.setattr(backfill_consumer, "process_s3_object", falso)
    return contador


def test_el_censo_de_SQLSTATE_es_UNO_SOLO_para_los_dos_workers() -> None:
    """Candado contra la deriva: si `backfill` se hiciera su propia lista de
    «base ocupada», serían dos políticas creyéndose una. Es el mismo objeto."""
    from takab_api.db.transient import TRANSIENT_SQLSTATES as censo_db
    from takab_api.ingest.consumer import TRANSIENT_SQLSTATES as censo_ingest

    assert backfill_consumer.TRANSIENT_SQLSTATES is censo_db
    assert censo_ingest is censo_db
    assert censo_db == frozenset({"55P03", "40P01", "40001"})


def test_un_fallo_transitorio_NO_gasta_ni_una_recepcion(sqs, queues, monkeypatch) -> None:
    """**El criterio 2**, con la misma cifra que midió `T-2.132` en ingesta.

    Antes de esta ficha cada bloqueo caía en `except psycopg.OperationalError`
    ⇒ RETRY ⇒ el mensaje vuelve a la cola ⇒ **una recepción quemada por
    bloqueo**. Y el objeto de backfill vale más que un feature: rehacerlo cuesta
    la pasada entera medida arriba.
    """
    contador = _fake_objeto(monkeypatch, fallos=3)
    consumidor, conn, spy = _consumer(sqs, queues)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body_s3())

    stats = consumidor.process_once()

    assert contador["n"] == 4, "el arnés no montó los tres bloqueos"
    assert stats["n_ok"] == 1 and stats["n_retry"] == 0
    assert spy.recepciones == 1, (
        f"{spy.recepciones} recepciones gastadas para UN objeto válido: "
        "cada reentrega acerca el mensaje a la DLQ"
    )
    assert _n(sqs, queues[0]) == 0 and _n(sqs, queues[1]) == 0


def test_un_lock_pasajero_no_manda_a_la_DLQ_un_objeto_VALIDO(sqs, queues, monkeypatch) -> None:
    """Cinco bloqueos = `maxReceiveCount` entero. Es el desenlace exacto que
    `T-2.130` midió en ingesta y que en backfill seguía vivo — sobre un mensaje
    que arrastra el spool de una caída completa."""
    contador = _fake_objeto(monkeypatch, fallos=5)
    consumidor, _, spy = _consumer(sqs, queues)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body_s3())

    _drenar(consumidor, sqs, queues[0])

    assert _n(sqs, queues[1]) == 0, "un objeto VÁLIDO acabó en la DLQ por un lock pasajero"
    assert contador["n"] == 6
    assert spy.recepciones == 1


def test_el_reintento_en_el_sitio_alarga_la_visibilidad(sqs, queues, monkeypatch) -> None:
    """La palanca: mientras se reintenta, el mensaje sigue EN VUELO. Sin esto
    otro worker lo tomaría, gastaría la recepción que se estaba ahorrando **y
    repetiría la pasada entera** — que aquí no son milisegundos."""
    _fake_objeto(monkeypatch, fallos=1)
    consumidor, _, spy = _consumer(sqs, queues)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body_s3())

    consumidor.process_once()

    assert spy.visibilidades == [backfill_consumer.BACKFILL_TRANSIENT_POLICY.inflight_visibility_s]


def test_la_transaccion_abortada_se_tira_antes_de_reintentar(sqs, queues, monkeypatch) -> None:
    """Detalle que no es cosmético: tras un 55P03 la transacción queda ABORTADA y
    Postgres rechaza cualquier sentencia posterior. Sin el rollback, el reintento
    fallaría por otra razón y el arreglo no serviría de nada."""
    _fake_objeto(monkeypatch, fallos=1)
    consumidor, conn, _ = _consumer(sqs, queues)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body_s3())

    consumidor.process_once()

    assert conn.rollbacks >= 1, "se reintentó sobre una transacción abortada"


def test_el_camino_viejo_tiraba_una_conexion_SANA(sqs, queues, monkeypatch) -> None:
    """El hallazgo de paso de `T-2.132`, que en backfill seguía intacto: un
    `55P03` caía en `except psycopg.OperationalError` → `_drop_conn()`. O sea
    **reconectar por un lock que ya había cedido**, tirando además el registry
    caliente."""
    _fake_objeto(monkeypatch, fallos=1)
    consumidor, conn, _ = _consumer(sqs, queues)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body_s3())

    consumidor.process_once()

    assert not conn.closed, "se tiró una conexión sana por un lock pasajero"


def test_un_fallo_REAL_sigue_agotando_reintentos_y_acaba_en_la_DLQ(
    sqs, queues, monkeypatch
) -> None:
    """El control. Si TODO se reintentara en el sitio, un objeto envenenado
    dejaría el worker girando para siempre y la DLQ no serviría para nada."""

    def falso(conn, bucket, key, registry, settings, *, s3_client):
        raise psycopg.OperationalError("la base se fue")

    monkeypatch.setattr(backfill_consumer, "process_s3_object", falso)
    consumidor, conn, spy = _consumer(sqs, queues)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body_s3())

    _drenar(consumidor, sqs, queues[0])

    assert _n(sqs, queues[1]) == 1, "un fallo REAL debe acabar en la DLQ"
    assert spy.recepciones >= 5, "el fallo real sí gasta las recepciones, y debe"
    assert spy.visibilidades == [], "un fallo real no merece alargues de visibilidad"


def test_un_bloqueo_que_NO_cede_devuelve_el_mensaje_con_respiro(sqs, queues, monkeypatch) -> None:
    """Presupuesto agotado ⇒ ya no es «transitorio»: es un lock atascado. El
    mensaje vuelve a la cola (ni borrado ni DLQ) pero con la visibilidad
    alargada, para que las cinco recepciones se repartan en minutos en vez de
    quemarse contra una tabla que sigue bloqueada."""
    from takab_api.db.transient import TransientPolicy

    _fake_objeto(monkeypatch, fallos=99)
    politica = TransientPolicy(
        budget_s=0.3, base_delay_s=0.05, max_delay_s=0.05, giveup_visibility_s=1
    )
    consumidor, conn, spy = _consumer(sqs, queues, policy=politica)
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body_s3())

    stats = consumidor.process_once()

    assert stats["n_retry"] == 1 and stats["n_ok"] == 0
    assert conn.commits == 0
    assert _n(sqs, queues[1]) == 0, "un lock atascado no es un objeto inválido"
    assert spy.visibilidades[-1] == 1
    assert sqs.receive_message(QueueUrl=queues[0]).get("Messages", []) == []
    time.sleep(1.2)
    assert len(sqs.receive_message(QueueUrl=queues[0]).get("Messages", [])) == 1


def test_el_COMMIT_del_objeto_tambien_esta_cubierto(sqs, queues, monkeypatch) -> None:
    """En backfill el commit vive DENTRO de `process_s3_object`, al final de la
    pasada: es el sitio donde aterrizan de golpe las miles de filas del objeto y
    el más probable de un `40001`. Como la acción reintentada incluye la pasada
    entera, el commit queda cubierto sin un caso aparte — pero eso hay que
    medirlo, no suponerlo."""
    from takab_api.backfill.objects import ObjectResult

    intentos = {"n": 0}

    class ConnQueFallaAlCommitear(FakeConn):
        def commit(self) -> None:
            if intentos["n"] == 1:
                raise _ocupada("40001")
            super().commit()

    def falso(conn, bucket, key, registry, settings, *, s3_client):
        intentos["n"] += 1
        conn.commit()
        return ObjectResult(Outcome.OK, ok=1)

    monkeypatch.setattr(backfill_consumer, "process_s3_object", falso)
    consumidor, conn, spy = _consumer(sqs, queues, conn=ConnQueFallaAlCommitear())
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body_s3())

    stats = consumidor.process_once()

    assert intentos["n"] == 2, "el commit fallido no se rehízo"
    assert conn.commits == 1 and stats["n_ok"] == 1
    assert spy.recepciones == 1, "el fallo en el commit gastó una recepción"


def test_el_reintento_REHACE_la_pasada_entera_y_es_idempotente(scenario, sqs, queues) -> None:
    """La contrapartida honesta del reintento en el sitio: en backfill rehacer
    **cuesta la pasada entera**, no un INSERT. Se paga porque el mensaje sigue
    siendo bueno y porque la re-ingesta deja **cero deltas** (PK
    `(ts, sensor_id, channel)` + ON CONFLICT). Medido contra Postgres real: dos
    pasadas, las mismas filas."""
    cuerpo, _lineas, filas = _objeto_representativo(scenario, segundos=60)
    key = f"backfill/{scenario.thing}/{uuid.uuid4().hex}.ndjson.gz"
    s3 = _FakeS3()
    s3.put(BUCKET, key, cuerpo)

    spy = SpySqs(sqs)
    consumidor = BackfillConsumer(
        queues[0],
        queues[1],
        _FakeRegistry({scenario.thing: scenario.ctx()}),
        lambda: scenario.conn,
        Settings(),
        publisher=object(),
        sqs_client=spy,
        s3_client=s3,
        wait_time_s=0,
    )
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body_s3(key))

    consumidor.process_once()
    tras_una = scenario.filas()
    sqs.send_message(QueueUrl=queues[0], MessageBody=_body_s3(key))
    consumidor.process_once()

    assert tras_una == filas
    assert scenario.filas() == filas, "la re-ingesta del MISMO objeto duplicó filas"
    assert s3.gets == 2, "la pasada rehecha vuelve a leer el objeto de S3"


# ================================================ 3 · el presupuesto, encajonado


def test_el_presupuesto_de_backfill_cabe_en_SU_visibilidad_CON_la_pasada(scenario, capsys) -> None:
    """El criterio duro de backfill **no es el de ingesta**, y es lo que la
    medición aporta.

    En ingesta una pasada son milisegundos, así que el presupuesto ≈ el tiempo
    total. Aquí no: cuando el presupuesto vence, todavía queda por delante **una
    pasada entera** (el último intento). Lo que tiene que caber en el
    `VisibilityTimeout` es la suma::

        presupuesto + pasada_medida  <  VisibilityTimeout(backfill)

    y el alargue de visibilidad tiene que cubrir esa misma suma, o el mensaje se
    escapa por el otro lado justo cuando se le estaba ahorrando la recepción.
    """
    politica = backfill_consumer.BACKFILL_TRANSIENT_POLICY
    umbral = _ajuste_edge("backfill_threshold_s")
    m = _pasada(scenario, segundos=umbral)
    vt = _visibilidades()["backfill"]
    peor_caso = politica.budget_s + m["pasada_s"]

    with capsys.disabled():
        print(
            f"\n[T-2.139] presupuesto {politica.budget_s} s + pasada {m['pasada_s']:.2f} s "
            f"= {peor_caso:.2f} s  <  VisibilityTimeout {vt} s "
            f"(alargue en vuelo {politica.inflight_visibility_s} s)"
        )

    assert peor_caso < vt, (
        f"peor caso {peor_caso:.1f} s ≥ visibilidad {vt} s: el mensaje se haría "
        "visible con el worker aún rehaciendo la pasada"
    )
    assert politica.inflight_visibility_s > peor_caso, (
        "el alargue no cubre presupuesto + una pasada: el mensaje se escaparía a mitad"
    )
    assert politica.budget_s > WORKER_LOCK_TIMEOUT_MS / 1000.0, (
        "una sola espera por lock no puede agotar el presupuesto de reintentos"
    )


def test_el_presupuesto_de_backfill_NO_es_el_de_ingesta_por_accidente() -> None:
    """Las dos colas tienen presupuestos distintos porque tienen visibilidades
    distintas; si alguien igualara las políticas «por consistencia», backfill
    perdería el margen que necesita para rehacer su pasada."""
    from takab_api.ingest.consumer import TransientPolicy

    vis = _visibilidades()
    assert vis["backfill"] >= 10 * vis["events"], (
        "si las colas dejaran de tener presupuestos tan distintos, la asimetría de "
        "políticas se queda sin su razón"
    )
    assert backfill_consumer.BACKFILL_TRANSIENT_POLICY.budget_s > TransientPolicy().budget_s


# ====================================================== 4 · los topes, en orden


def test_backfill_arranca_CON_el_tope_de_lock(monkeypatch) -> None:
    """**El tope que la política acaba de autorizar.** `T-2.132` puso el orden:
    primero la red que hace inocuo el `55P03`, y solo entonces el tope que lo
    provoca. Con la política ya puesta, esperar un lock para siempre dejó de ser
    la opción segura: mientras espera, el worker sostiene una transacción ABIERTA
    que puede ser el extremo lejano de un ciclo que Postgres no detecta
    (`T-2.73.c`) — y en backfill esa transacción arrastra el objeto entero."""
    from takab_api.backfill import __main__ as entry

    monkeypatch.setenv("TAKAB_API_QUEUE_URL_BACKFILL", "https://sqs.test/q-backfill")
    monkeypatch.setenv("TAKAB_API_DLQ_URL_BACKFILL", "https://sqs.test/q-backfill-dlq")
    monkeypatch.setenv("TAKAB_API_DATABASE_URL", _dsn())
    with mock_aws():
        consumidor = entry.build_consumer(Settings())
    with consumidor._conn_factory() as conn:  # noqa: SLF001 - es el punto del test
        assert conn.execute("SHOW lock_timeout").fetchone()["lock_timeout"] != "0"


def test_backfill_SIGUE_SIN_tope_de_sentencia_y_la_razon_esta_medida(monkeypatch) -> None:
    """**El veredicto del criterio 2, y es «todavía no» — con cifras.**

    Un `statement_timeout` acota **una sentencia**. Los tests de la sección 1
    miden que en backfill ninguna sentencia se acerca a la pasada: lo que hace
    larga a una pasada son **miles de sentencias cortas en UNA transacción**. O
    sea que el tope **no cierra el modo de fallo** que lo motivaba —la pasada
    pasándose del `VisibilityTimeout`— y sí abre uno nuevo: `57014` **no** está
    en el censo de transitorios (a propósito: una consulta cancelada no es «la
    base ocupada»), así que cada disparo sería una recepción quemada **y una
    pasada entera tirada**.

    Lo que falta para poder ponerlo está escrito en la ficha y en
    `WORKER_STATEMENT_TIMEOUT_MS`: o `57014` deja de ser terminal aquí, o el
    objeto se trocea para que la pasada deje de ser una transacción única. Este
    test es el que se pondrá rojo el día que alguien añada el tope sin eso.

    Se comprueba **sobre la conexión que fabrica el proceso real**, no sobre el
    texto del fichero: el guardia textual de `T-2.136` se ponía rojo con solo
    NOMBRAR el parámetro en un comentario, que es justo lo que hay que hacer para
    dejar la razón escrita al lado de la decisión.
    """
    from takab_api.backfill import __main__ as entry
    from takab_api.db.transient import TRANSIENT_SQLSTATES

    monkeypatch.setenv("TAKAB_API_QUEUE_URL_BACKFILL", "https://sqs.test/q-backfill")
    monkeypatch.setenv("TAKAB_API_DLQ_URL_BACKFILL", "https://sqs.test/q-backfill-dlq")
    monkeypatch.setenv("TAKAB_API_DATABASE_URL", _dsn())
    with mock_aws():
        consumidor = entry.build_consumer(Settings())
    with consumidor._conn_factory() as conn:  # noqa: SLF001 - es el punto del test
        assert conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"] == "0", (
            "backfill ganó el tope de sentencia: si es a propósito, hay que rehacer la "
            "medición de T-2.139 (¿se trocea ya el objeto?) y reescribir esta razón"
        )
    assert "57014" not in TRANSIENT_SQLSTATES, (
        "si 57014 entrara en el censo, el tope de sentencia dejaría de quemar "
        "recepciones y este veredicto habría que rehacerlo"
    )
