"""T-2.81.a · Cuánto dura la transacción larga del job de retención. EXCLUIDA.

La ficha dice que la corrida entera es UNA transacción —correcto y atómico— pero
que sobre millones de filas eso mantiene una transacción larga **y eso no se ha
medido con volumen real**. Esto es la medición, re-ejecutable.

Requiere una DB DEDICADA ya migrada y ``TAKAB_RUN_PERF=1`` (el ``skipif`` de
módulo la salta en cualquier otro caso — nunca siembra un millón de filas en un
PR). Correr::

    createdb takab_perf_pii
    DATABASE_URL=postgresql+psycopg://takab:takab_dev@127.0.0.1:5433/takab_perf_pii \\
        uv run alembic upgrade head
    TAKAB_RUN_PERF=1 DATABASE_URL=... uv run pytest -m perf \\
        tests/perf/test_prune_pii_volumen.py -q -s

El propio test siembra (`scripts/seed_prune_pii_volume.py`) porque el `conftest`
raíz TRUNCA las tablas de negocio al empezar la sesión: una base sembrada antes
llegaría vacía y la medición saldría de cero filas creyendo que midió un millón.

MEDIDO EL 2026-08-14 (Postgres 16 local, 1 000 000 de filas de `push_tokens`,
todas caducadas, cuatro tenants):

    filas due=1000000 aplicadas=1000000
    transacción abierta (vista desde OTRA conexión, pico): 38.64 s
    tiempo hasta el commit: 38.90 s

O sea ~39 µs por fila, lineal. La cota de abajo la fija la decisión: se conserva
la transacción única —el conteo previo es la AUTORIZACIÓN de la poda y media
poda con informe en verde es peor que ninguna (`T-2.81`)— y lo que se acota es
el otro reloj, el de ESPERA POR LOCK (`db/session.JOB_LOCK_TIMEOUT_MS`), que no
mide trabajo útil y por tanto no puede matar una corrida legítima.

Este test no vigila un p95: vigila que la magnitud siga siendo la medida. Si un
día tarda 10× más por fila, algo cambió (un índice perdido, un trigger nuevo) y
el número que sostiene la decisión de arriba ha dejado de ser cierto.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import threading
import time
from pathlib import Path

import psycopg
import pytest

from takab_api.db import session
from takab_api.ops import prune_pii
from takab_api.privacy.retention import RETENTION_PLAN

_RUN = os.environ.get("TAKAB_RUN_PERF") == "1"
pytestmark = [
    pytest.mark.perf,
    pytest.mark.skipif(not _RUN, reason="perf desactivado (usa TAKAB_RUN_PERF=1 + DB dedicada)"),
]

#: Lo medido: 38.9 s / 1 000 000 filas ≈ 39 µs. El presupuesto va con holgura ×4
#: porque esto corre en máquinas distintas; lo que caza es un cambio de ORDEN DE
#: MAGNITUD, que es lo único que invalidaría la decisión de no trocear.
_PRESUPUESTO_US_POR_FILA = 160.0
_MINIMO_DE_FILAS = 100_000
#: Lo que el arnés siembra. Un millón es el volumen de la medición citada arriba.
_FILAS_A_SEMBRAR = int(os.environ.get("TAKAB_PERF_PII_FILAS", "1000000"))


def _dsn() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


class _Vigia:
    """Mide la transacción del job DESDE FUERA, que es como la ve la base.

    Cronometrar dentro del proceso mediría el tiempo de Python. Lo que importa
    aquí es cuánto rato hay una transacción ABIERTA sosteniendo el horizonte de
    `xmin` y sus locks, y eso solo lo dice `pg_stat_activity`.
    """

    def __init__(self) -> None:
        self.xact_max = 0.0
        self.locks_max = 0
        self.muestras = 0
        self._parar = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)

    def _bucle(self) -> None:
        with psycopg.connect(_dsn(), autocommit=True) as ojo:
            while not self._parar.is_set():
                fila = ojo.execute(
                    "SELECT coalesce(max(extract(epoch from now() - a.xact_start)), 0), "
                    "       coalesce(max(l.n), 0) "
                    "  FROM pg_stat_activity a "
                    "  LEFT JOIN (SELECT pid, count(*) n FROM pg_locks GROUP BY pid) l "
                    "         ON l.pid = a.pid "
                    " WHERE a.datname = current_database() AND a.pid <> pg_backend_pid() "
                    "   AND a.state <> 'idle'"
                ).fetchone()
                self.xact_max = max(self.xact_max, float(fila[0]))
                self.locks_max = max(self.locks_max, int(fila[1]))
                self.muestras += 1
                time.sleep(0.25)

    def __enter__(self) -> _Vigia:
        self._hilo.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._parar.set()
        self._hilo.join()


def _sembrar_si_hace_falta(filas: int) -> int:
    """Siembra DENTRO del test, y no antes, por una razón que costó una corrida.

    El `conftest` raíz TRUNCA todas las tablas de negocio al empezar la sesión
    (T-2.122: una corrida no puede heredar el veredicto de la anterior). Una base
    sembrada a mano por el runbook llega vacía a este punto, y el test mediría
    cero filas creyendo que midió un millón — el defecto de arnés que esta fase
    lleva cazando. Así que el arnés siembra y CONFIRMA que sembró.
    """
    seeder = _cargar_sembrador()
    with psycopg.connect(_dsn(), autocommit=False) as conn:
        seeder.sembrar(conn, tokens=filas, dias=800)
        return conn.execute("SELECT count(*) FROM push_tokens").fetchone()[0]


def _cargar_sembrador():
    ruta = Path(__file__).resolve().parents[2] / "scripts" / "seed_prune_pii_volume.py"
    spec = importlib.util.spec_from_file_location("seed_prune_pii_volume", ruta)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def test_la_transaccion_larga_esta_MEDIDA_y_sigue_siendo_lineal() -> None:
    filas = _sembrar_si_hace_falta(_FILAS_A_SEMBRAR)
    assert filas >= _MINIMO_DE_FILAS, (
        f"el arnés dejó {filas} push_tokens y esperaba ≥ {_MINIMO_DE_FILAS}: "
        "el escenario NO se montó, así que lo que siga no mide nada"
    )

    with _Vigia() as vigia, psycopg.connect(_dsn(), autocommit=False) as conn:
        t0 = time.perf_counter()
        informe = prune_pii.run(conn, apply=True, days={r.key: 30 for r in RETENTION_PLAN})
        conn.commit()
        transcurrido = time.perf_counter() - t0

    assert vigia.muestras > 0, "el vigía no tomó ni una muestra: la medición no ocurrió"
    assert informe.total_applied >= _MINIMO_DE_FILAS, (
        "la corrida no tocó el volumen sembrado: no se ha medido el caso caro"
    )

    us_por_fila = transcurrido / informe.total_applied * 1e6
    print(
        f"\n[T-2.81.a] {informe.total_applied} filas · {transcurrido:.2f}s "
        f"({us_por_fila:.1f} µs/fila) · transacción abierta vista desde fuera: "
        f"{vigia.xact_max:.2f}s · locks pico: {vigia.locks_max}"
    )

    assert us_por_fila < _PRESUPUESTO_US_POR_FILA, (
        f"{us_por_fila:.1f} µs/fila contra un presupuesto de {_PRESUPUESTO_US_POR_FILA}: "
        "la medición que sostiene 'no hace falta trocear la corrida' ha dejado de ser cierta"
    )
    assert vigia.xact_max >= transcurrido * 0.5, (
        "la transacción vista desde la base duró mucho menos que la llamada: el "
        "vigía no estaba mirando lo que cree (¿otra base? ¿otra conexión?)"
    )


def test_el_tope_de_lock_no_puede_matar_una_corrida_de_este_tamano() -> None:
    """El filo que la ficha nombra: «una transacción larga que además choque con
    un tope es un fallo nuevo, no una mejora».

    El job lleva `lock_timeout` y NO `statement_timeout`, y eso no es una
    preferencia: con cualquiera de los topes de sentencia que ya existen (request
    20 s, worker 15 s) una corrida como la medida moriría a mitad.
    """
    with psycopg.connect(_dsn(), autocommit=False) as conn, conn.transaction():
        prune_pii.harden_session(conn)
        assert conn.execute("SHOW statement_timeout").fetchone()[0] in ("0", "0ms")
        assert conn.execute("SHOW lock_timeout").fetchone()[0] == (
            f"{session.JOB_LOCK_TIMEOUT_MS // 1000}s"
        )
    assert session.REQUEST_STATEMENT_TIMEOUT_MS < 38_900, (
        "el tope de sentencia del request dejó de ser menor que la corrida medida: "
        "revisa si esta comparación sigue diciendo algo"
    )
