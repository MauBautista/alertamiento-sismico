"""Tope de SENTENCIA de los workers (T-2.136).

`T-2.131` acotó la consulta lenta —no bloqueada— de la conexión del REQUEST.
Los workers conectan por ``db/pool.py`` y su ``statement_timeout`` seguía en
``0``. **Y aquí el modo de fallo es distinto y peor:** una consulta que se pasa
del ``VisibilityTimeout`` de la cola hace que SQS entregue el mensaje **otra
vez** mientras el primero sigue trabajando. No es que el servicio se degrade: es
que el mismo hecho puede entrar dos veces.

Orden del fichero, que es el de la ficha:

1. **La medición** — hoy puede pasarse, y por cuánto.
2. **El encajonado** — el número, leído del Terraform real por arriba y de la
   política de `T-2.132` por abajo.
3. **Por abajo con dientes** — que el tope de sentencia por debajo del de lock
   DESACTIVA el arreglo de `T-2.132`, medido contra Postgres en vez de razonado.
4. **La asimetría** — a qué workers se le pone y a cuáles no, pinchado en el
   cableado real y no solo en un comentario.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import psycopg
import pytest
from moto import mock_aws

from conftest import _dsn
from takab_api.db import pool
from takab_api.db.session import WORKER_LOCK_TIMEOUT_MS, WORKER_STATEMENT_TIMEOUT_MS
from takab_api.ingest.consumer import TRANSIENT_SQLSTATES, TransientPolicy
from takab_api.settings import Settings

_TF = Path(__file__).resolve().parents[2] / "infra/terraform/modules/messaging/main.tf"


def _visibilidades() -> list[int]:
    """Los ``VisibilityTimeout`` REALES, del Terraform y no de una copia local."""
    valores = [
        int(m) for m in re.findall(r"visibility_timeout\s*=\s*(\d+)", _TF.read_text("utf-8"))
    ]
    assert valores, f"no se pudo leer la visibilidad real de {_TF}"
    return valores


# ============================================================== 1 · la medición


def test_sin_tope_la_sentencia_de_un_worker_no_tiene_techo() -> None:
    """El estado de partida, medido: ``0`` es «sin tope», y ``0`` no es un decir.

    Se comprueba con una consulta que dura más que un tope de referencia: sobre
    la conexión SIN tope corre entera; sobre la MISMA consulta con tope, muere.
    Sin el segundo brazo, un ``pg_sleep`` que acaba no probaría nada —también
    acabaría con un tope generoso.
    """
    with pool.connect(_dsn()) as sin_tope:
        assert sin_tope.execute("SHOW statement_timeout").fetchone()["statement_timeout"] == "0"
        arranque = time.monotonic()
        sin_tope.execute("SELECT pg_sleep(1.5)")
        duracion = time.monotonic() - arranque
    assert duracion >= 1.4, "el arnés no llegó a tardar: la consulta no midió nada"

    with pool.connect(_dsn(), statement_timeout_ms=400) as con_tope:
        with pytest.raises(psycopg.errors.QueryCanceled):
            con_tope.execute("SELECT pg_sleep(1.5)")


@pytest.mark.perf
def test_medicion_una_consulta_de_worker_SE_PASA_del_visibility_timeout() -> None:
    """El criterio 1 de la ficha, sin escalar: 31 s contra los 30 s de `q-events`.

    Marcado ``perf`` porque tarda medio minuto — la suite normal lo deselecciona.
    Medido a mano el 2026-08-13 en la conexión de worker sin tope:
    ``pg_sleep(31)`` COMPLETO en **31.03 s**, con la cola más apretada en 30 s.
    """
    peor = min(_visibilidades())
    with pool.connect(_dsn()) as conn:
        arranque = time.monotonic()
        conn.execute(f"SELECT pg_sleep({peor + 1})")
        duracion = time.monotonic() - arranque
    assert duracion > peor, (
        f"la consulta duró {duracion:.2f} s con VisibilityTimeout {peor} s: "
        "el mensaje se habría reentregado con el worker todavía trabajando"
    )


# ============================================================= 2 · el encajonado


def test_el_tope_del_worker_sale_de_la_politica_UNICA() -> None:
    """El número no se escribe en `pool.py`: se pide a `db/session.py`, donde ya
    viven el del request, el del segundo plano y el de lock del worker."""
    with pool.connect(_dsn(), statement_timeout_ms=WORKER_STATEMENT_TIMEOUT_MS) as conn:
        aplicado = conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"]
    assert aplicado == f"{WORKER_STATEMENT_TIMEOUT_MS // 1000}s"


def test_el_tope_de_sentencia_sobrevive_a_un_rollback() -> None:
    """Mismo motivo que el de lock: el worker hace `rollback()` en cada RETRY, y
    un `SET` no local se desharía justo cuando el tope hace falta."""
    with pool.connect(_dsn(), statement_timeout_ms=WORKER_STATEMENT_TIMEOUT_MS) as conn:
        conn.execute("SELECT 1")
        conn.rollback()
        assert conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"] != "0"


def test_los_dos_topes_conviven_en_la_misma_conexion() -> None:
    """`pool.connect` los pasa juntos en `options`; si uno pisara al otro, el
    worker se quedaría sin la mitad de la política y nada se pondría rojo."""
    with pool.connect(
        _dsn(),
        lock_timeout_ms=WORKER_LOCK_TIMEOUT_MS,
        statement_timeout_ms=WORKER_STATEMENT_TIMEOUT_MS,
    ) as conn:
        lock = conn.execute("SHOW lock_timeout").fetchone()["lock_timeout"]
        stmt = conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"]
    assert lock == f"{WORKER_LOCK_TIMEOUT_MS // 1000}s"
    assert stmt == f"{WORKER_STATEMENT_TIMEOUT_MS // 1000}s"


def test_el_tope_cabe_en_la_visibilidad_de_la_cola_y_en_el_presupuesto() -> None:
    """El criterio duro, con los números leídos de donde viven.

        WORKER_LOCK_TIMEOUT_MS < WORKER_STATEMENT_TIMEOUT_MS ≤ budget_s < VisibilityTimeout

    Por arriba manda el `VisibilityTimeout` del **Terraform real** (no una copia
    en este fichero): pasarse de él es exactamente el duplicado que la ficha
    persigue. Y el tope no puede sobrevivir al presupuesto de reintento que
    protege al mensaje dentro de la recepción que ya se gastó.
    """
    peor = min(_visibilidades())
    tope_s = WORKER_STATEMENT_TIMEOUT_MS / 1000.0
    assert tope_s < peor, (
        f"tope de sentencia {tope_s} s ≥ VisibilityTimeout mínimo {peor} s: "
        "una sola sentencia podría provocar la reentrega que esto evita"
    )
    assert tope_s <= TransientPolicy().budget_s, (
        "una sentencia no puede durar más que el presupuesto de reintento del mensaje"
    )
    assert WORKER_LOCK_TIMEOUT_MS < WORKER_STATEMENT_TIMEOUT_MS, (
        "ver test_por_debajo_del_tope_de_lock_el_arreglo_de_T2132_queda_desactivado"
    )


# =========================================== 3 · por abajo, medido contra Postgres


def _bloquear() -> psycopg.Connection:
    """Tercero que retiene `gateways` en ACCESS EXCLUSIVE. El arnés se confirma a
    sí mismo (lección de T-2.131): si una sonda con tope corto NO rebota, el
    bloqueo no existe y lo que venga después no probaría nada."""
    bloqueador = psycopg.connect(_dsn())
    bloqueador.execute("LOCK TABLE gateways IN ACCESS EXCLUSIVE MODE")
    with pool.connect(_dsn(), lock_timeout_ms=250) as sonda:
        with pytest.raises(psycopg.errors.LockNotAvailable):
            sonda.execute("SELECT 1 FROM gateways LIMIT 1")
    return bloqueador


def _sqlstate_de_un_bloqueo(*, lock_ms: int, stmt_ms: int) -> str | None:
    bloqueador = _bloquear()
    try:
        with pool.connect(_dsn(), lock_timeout_ms=lock_ms, statement_timeout_ms=stmt_ms) as conn:
            with pytest.raises(psycopg.Error) as exc:
                conn.execute("SELECT 1 FROM gateways LIMIT 1")
        return exc.value.sqlstate
    finally:
        bloqueador.rollback()
        bloqueador.close()


def test_con_el_orden_correcto_un_bloqueo_sigue_saliendo_como_55P03() -> None:
    """Con el tope de sentencia POR ENCIMA del de lock, una espera por lock sigue
    emitiendo `55P03` — que es el SQLSTATE que `T-2.132` reintenta en el sitio,
    sin gastar ni una recepción de SQS."""
    estado = _sqlstate_de_un_bloqueo(lock_ms=300, stmt_ms=3_000)
    assert estado == "55P03"
    assert estado in TRANSIENT_SQLSTATES, "el reintento en el sitio no se dispararía"


def test_por_debajo_del_tope_de_lock_el_arreglo_de_T2132_queda_desactivado() -> None:
    """**El límite de abajo, con dientes.** Invertido el orden, el reloj de la
    sentencia vence primero y el MISMO bloqueo sale como `57014`.

    `57014` no está en `TRANSIENT_SQLSTATES` a propósito —una consulta cancelada
    no es «la base estaba ocupada»—, así que el reintento en el sitio no se
    dispara: el mensaje vuelve a la cola, quema una recepción y a la quinta un
    mensaje VÁLIDO acaba en la DLQ. Es el daño que `T-2.130` midió y `T-2.132`
    arregló, **desactivado sin que nada más se pusiera rojo**. Este test es lo
    único que impide que alguien baje el tope de sentencia «por prudencia».
    """
    estado = _sqlstate_de_un_bloqueo(lock_ms=3_000, stmt_ms=300)
    assert estado == "57014", "el orden invertido debería haber cancelado por sentencia"
    assert estado not in TRANSIENT_SQLSTATES, (
        "si 57014 entrara en el censo de transitorios, este orden dejaría de ser peligroso "
        "y este test perdería su sentido — revísalo antes de tocarlo"
    )


# ================================================================ 4 · la asimetría


def test_el_worker_de_ingesta_arranca_con_los_DOS_topes(monkeypatch) -> None:
    """El cableado, no solo la capacidad: el proceso real los lleva puestos."""
    from takab_api.ingest import __main__ as entry

    monkeypatch.setenv("TAKAB_API_QUEUE_URL_EVENTS", "https://sqs.test/q-events")
    monkeypatch.setenv("TAKAB_API_DLQ_URL_EVENTS", "https://sqs.test/q-events-dlq")
    monkeypatch.setenv("TAKAB_API_DATABASE_URL", _dsn())
    with mock_aws():
        consumidor = entry.build_consumer("events", Settings())
    with consumidor._conn_factory() as conn:  # noqa: SLF001 - es el punto del test
        assert conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"] != "0"
        assert conn.execute("SHOW lock_timeout").fetchone()["lock_timeout"] != "0"


@pytest.mark.parametrize(
    ("modulo", "constructor"),
    [
        ("takab_api.notify.__main__", "build_worker"),
        ("takab_api.commands.__main__", "build_worker"),
    ],
)
def test_los_pollers_sin_cola_NO_llevan_tope(monkeypatch, modulo: str, constructor: str) -> None:
    """La asimetría, pinchada donde vive y no en un comentario.

    `notify` y `commands` **no consumen SQS**: son pollers de la base. Sin
    `VisibilityTimeout` no hay reentrega, no hay duplicado que evitar y no hay
    presupuesto del que derivar un número — dárselo sería inventarlo. Si algún
    día pasan a consumir cola, este test es el que hay que releer.
    """
    import importlib

    monkeypatch.setenv("TAKAB_API_DATABASE_URL", _dsn())
    entry = importlib.import_module(modulo)
    worker = getattr(entry, constructor)(Settings(), poll_s=1.0)
    with worker._conn_factory() as conn:  # noqa: SLF001 - es el punto del test
        assert conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"] == "0"


def test_backfill_no_lleva_tope_y_su_cola_dice_por_que() -> None:
    """`backfill` SÍ consume cola, así que el modo de fallo existe — y aun así se
    queda fuera, con una razón medible: su `VisibilityTimeout` es 10× el de
    eventos, su trabajo es a granel (objeto de S3 → miniSEED → filas) y **no
    tiene la política de reintento** de `ingest/consumer.py`. Un `57014` allí
    sería una recepción quemada por una sentencia que podía ser legítima.
    Ponerle tope exige medir antes cuánto tarda un objeto real: ficha aparte.
    """
    visibilidades = _visibilidades()
    assert max(visibilidades) >= 10 * min(visibilidades), (
        "si las colas dejaran de tener presupuestos tan distintos, esta asimetría "
        "se queda sin la mitad de su razón"
    )
    from takab_api.backfill import __main__ as entry

    fuente = Path(entry.__file__).read_text("utf-8")
    assert "statement_timeout_ms" not in fuente, (
        "backfill ganó el tope sin que se actualizara la razón escrita en "
        "WORKER_STATEMENT_TIMEOUT_MS ni esta prueba"
    )
