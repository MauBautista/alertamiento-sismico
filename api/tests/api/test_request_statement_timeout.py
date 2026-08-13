"""[T-2.131] Qué le pasa a la conexión del REQUEST con una consulta LENTA. MEDIDO.

`T-2.130` acotó las esperas **por lock**. Esto es el otro extremo del mismo
agotamiento: una consulta que **no está bloqueada por nadie** —simplemente
tarda— retiene su conexión del pool sin límite, y diez de ellas dejan sin
servicio a lo que ni siquiera toca esa tabla. Misma forma de fallo, causa
distinta, y el `lock_timeout` no la alcanza: son GUCs distintos de Postgres.

Lo medido contra el código anterior al arreglo (2026-08-12):

    · Una consulta de 20 s por `get_tenant_conn` **corre entera**: no hay
      `statement_timeout` en ningún sitio (`SHOW statement_timeout` = `0`, y el
      censo del código fuente no encontró un solo literal).
    · Y con las diez conexiones del pool dentro de consultas lentas, `GET /sites`
      —que no toca nada de eso— muere con el `TimeoutError` del pool.

El criterio duro que fija el número, y que estos tests anclan, tiene DOS lados y
el de abajo es el que no se ve venir:

    lock_timeout (10 s)  <  statement_timeout  <  timeout del pool (30 s)

Por arriba, lo de siempre: por encima del pool, un tope degrada el proceso en
vez de una petición. **Por abajo es más sutil**: si el tope de sentencia fuera
menor o igual que el de lock, el reloj de la sentencia vencería SIEMPRE primero
y el `lock_timeout` de `T-2.130` no podría dispararse nunca — el 503 con nombre
se convertiría en un 57014 anónimo y aquel arreglo quedaría desactivado sin que
nada se pusiera rojo.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import re
import time

import psycopg
import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.db.session import (
    REQUEST_LOCK_TIMEOUT_MS,
    REQUEST_STATEMENT_TIMEOUT_MS,
    SessionCtx,
    StatementTimeout,
    get_tenant_conn,
)

pytestmark = pytest.mark.asyncio

_USER = "abcabcab-0000-0000-0000-0000000000c1"

#: Techo del TEST. Por debajo del timeout del pool (30 s) para que un cuelgue
#: llegue con nombre y no se confunda con el otro modo de fallo.
_TOPE_TEST_S = 25.0


def _ctx() -> SessionCtx:
    return SessionCtx(tenant_id=au.DB_TENANT_PRIV, role="soc_operator", user_id=_USER)


def _token(role: str = "soc_operator", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*", user_id=_USER))


def _raw_dsn() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


def _cupo_del_pool() -> int:
    """Conexiones simultáneas que la API puede tener abiertas (``pool_size`` + overflow)."""
    pool = get_engine().pool
    return pool.size() + pool._max_overflow  # noqa: SLF001 - no hay accesor público


async def _lenta(segundos: float, **kwargs: object) -> float:
    """Corre `pg_sleep(segundos)` por la conexión del request; devuelve lo que tardó.

    `pg_sleep` es una consulta **lenta y no bloqueada**: no pide un solo lock, así
    que el tope de `T-2.130` no la roza. Es exactamente la forma de la consulta
    que esta ficha persigue, reducida a su esqueleto.
    """
    inicio = time.monotonic()
    async with get_tenant_conn(_ctx(), **kwargs) as conn:  # type: ignore[arg-type]
        await conn.execute(text("SELECT pg_sleep(:s)"), {"s": segundos})
    return time.monotonic() - inicio


async def _ocupar_pool(n: int, segundos: float, tope_s: float = 15.0) -> list[asyncio.Task]:
    """Deja ``n`` conexiones del pool dentro de una consulta lenta, y lo CONFIRMA.

    La confirmación la dan las propias tareas —cada una avisa cuando ya tiene su
    conexión y ha lanzado la consulta—, no un vistazo a ``pg_stat_activity``.

    La primera versión de este arnés preguntaba al catálogo, y **no funcionaba**:
    daba «0 de 10» mientras las diez tareas corrían perfectamente (medido: en el
    mismo proceso, una consulta idéntica al catálogo sí las veía). Da igual cuál
    fuera la causa exacta de esa ceguera — el error de diseño es anterior: un test
    no debe inferir el estado de su propio andamio de una vista del servidor que
    puede no reflejarlo cuando él mira. Si el arnés no se monta, quien tiene que
    decirlo es el arnés.
    """
    listas: list[asyncio.Event] = [asyncio.Event() for _ in range(n)]

    async def ocupante(aviso: asyncio.Event) -> None:
        async with get_tenant_conn(_ctx()) as conn:
            espera = conn.execute(text("SELECT pg_sleep(:s)"), {"s": segundos})
            aviso.set()  # conexión TOMADA del pool; la consulta ya va en camino
            await espera

    tareas = [asyncio.create_task(ocupante(e)) for e in listas]
    try:
        await asyncio.wait_for(asyncio.gather(*(e.wait() for e in listas)), tope_s)
    except TimeoutError:
        for t in tareas:
            t.cancel()
        vivas = sum(1 for e in listas if e.is_set())
        pytest.fail(f"solo {vivas} de {n} ocupantes tomaron conexión: el arnés no se montó")
    return tareas


async def test_MEDIDO_una_consulta_lenta_NO_bloqueada_cede_con_nombre() -> None:
    """Criterio 1: hay tope de sentencia, y el error se distingue del de lock.

    Antes: la consulta corría entera —los 20 s— porque `statement_timeout` valía
    `0` en toda la instalación. Ahora cede al vencer la política, y **con un
    nombre distinto del `LockTimeout`**: no es lo mismo «el recurso está ocupado»
    (reintentable, otro lo tiene) que «esto tarda demasiado» (reintentar igual da
    igual). Confundirlos manda al cliente a reintentar en bucle una consulta que
    va a volver a tardar lo mismo.
    """
    largo = REQUEST_STATEMENT_TIMEOUT_MS / 1000.0 + 10.0
    inicio = time.monotonic()
    with pytest.raises(StatementTimeout) as exc:
        await asyncio.wait_for(_lenta(largo), _TOPE_TEST_S)
    tardanza = time.monotonic() - inicio

    assert exc.value.status_code == 503
    assert exc.value.headers.get("Retry-After") is not None
    assert tardanza < largo, (
        f"la consulta corrió {tardanza:.1f} s de los {largo:.0f} s pedidos: el tope no actúa. "
        "Sin tope, una consulta lenta retiene su conexión del pool lo que dure, y diez de "
        "estas agotan el pool igual que un lock (T-2.131)."
    )


async def test_MEDIDO_el_pool_NO_se_agota_por_consultas_lentas(client) -> None:
    """Criterio 1, la mitad que importa: es **el pool**, no una petición.

    Se llenan **todas** las conexiones de la API con consultas lentas y se pide
    algo que no tiene nada que ver. Antes: `TimeoutError` del pool a los 30 s —
    unas cuantas consultas lentas dejaban sin servicio a la API entera, igual que
    hacía un lock antes de `T-2.130`. Ahora las lentas ceden al vencer su tope,
    devuelven la conexión y el request ajeno se sirve.
    """
    cupo = _cupo_del_pool()
    largo = REQUEST_STATEMENT_TIMEOUT_MS / 1000.0 + 10.0
    atascados = await _ocupar_pool(cupo, largo)
    try:
        inicio = time.monotonic()
        try:
            ajeno = await asyncio.wait_for(client.get("/sites", headers=_token()), _TOPE_TEST_S)
        except TimeoutError:
            pytest.fail(
                f"`GET /sites` no se sirvió en {_TOPE_TEST_S:.0f} s con las {cupo} conexiones "
                "del pool dentro de consultas lentas. Eso es el proceso degradado, no una "
                "petición (T-2.131)."
            )
        espera_ajeno = time.monotonic() - inicio
    finally:
        for t in atascados:
            t.cancel()
        await asyncio.gather(*atascados, return_exceptions=True)

    assert ajeno.status_code == 200, ajeno.text
    assert espera_ajeno < _TOPE_TEST_S


async def test_el_tope_de_sentencia_va_ENTRE_el_de_lock_y_el_del_pool() -> None:
    """El criterio duro de la ficha, con sus DOS lados, contra el pool REAL.

    Por arriba es el de `T-2.130`: por encima del timeout del pool, un tope
    degrada el proceso entero en vez de una petición.

    Por abajo es el que no se ve venir: **si el tope de sentencia no fuera
    estrictamente mayor que el de lock, el `lock_timeout` no podría dispararse
    jamás**. El reloj de la sentencia corre desde que empieza, espera por lock
    incluida; si venciera primero, toda espera por lock moriría como un 57014
    anónimo y el 503 con nombre de `T-2.130` quedaría desactivado en silencio,
    sin un solo test en rojo que lo delatara.
    """
    pool = get_engine().pool
    timeout_pool_s = pool._timeout  # noqa: SLF001 - no hay accesor público
    assert REQUEST_STATEMENT_TIMEOUT_MS / 1000.0 < timeout_pool_s, (
        f"tope de sentencia {REQUEST_STATEMENT_TIMEOUT_MS} ms ≥ timeout del pool "
        f"{timeout_pool_s} s: diez consultas lentas volverían a agotar el pool"
    )
    assert REQUEST_STATEMENT_TIMEOUT_MS > REQUEST_LOCK_TIMEOUT_MS, (
        f"tope de sentencia {REQUEST_STATEMENT_TIMEOUT_MS} ms ≤ tope de lock "
        f"{REQUEST_LOCK_TIMEOUT_MS} ms: el `lock_timeout` de T-2.130 no podría dispararse nunca "
        "y su 503 con nombre se convertiría en un 57014 anónimo"
    )


async def test_el_tope_de_lock_SIGUE_ganando_cuando_lo_que_hay_es_un_lock(make_incident) -> None:
    """El lado de abajo del criterio, MEDIDO — no deducido de dos constantes.

    Lo anterior compara números; esto comprueba la consecuencia real contra la
    base: con la tabla bloqueada por un tercero, el que debe vencer es el reloj
    del lock, y el cliente debe seguir recibiendo el `LockTimeout` de `T-2.130`
    —no un `StatementTimeout`—. Es el candado que impide que el tope nuevo
    desactive al anterior sin que nada se ponga rojo.
    """
    from takab_api.db.session import LockTimeout

    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    async with await psycopg.AsyncConnection.connect(_raw_dsn()) as tercero:
        await tercero.execute("LOCK TABLE incidents IN ACCESS EXCLUSIVE MODE")
        with pytest.raises(LockTimeout):
            async with get_tenant_conn(_ctx(), lock_timeout_ms=300) as conn:
                await conn.execute(
                    text("SELECT 1 FROM incidents WHERE incident_id = :i"), {"i": iid}
                )
        await tercero.rollback()


async def test_el_trabajo_legitimo_largo_TIENE_salida_y_es_explicita() -> None:
    """Criterio 2: el tope no puede cortar trabajo legítimo largo.

    Un tope global es romo por definición: no distingue «lenta por volumen
    legítimo» de «lenta por patología». La salida NO es subir el número para
    todos —eso devuelve el agotamiento del pool— sino que quien de verdad
    necesita más lo **declare en su llamada**, donde se ve en el diff y se puede
    auditar. Aquí se comprueba que esa salida existe y funciona.
    """
    largo = REQUEST_STATEMENT_TIMEOUT_MS / 1000.0 + 2.0
    tardanza = await _lenta(2.0, statement_timeout_ms=int(largo * 1000))
    assert tardanza >= 1.5, "la consulta ni siquiera esperó: el escenario no se montó"


async def test_el_tope_sale_de_UNA_politica_y_no_de_numeros_sueltos() -> None:
    """Un solo sitio declara los milisegundos — mismo candado que `T-2.130`.

    Un número suelto en un módulo cualquiera es exactamente cómo derivan dos
    políticas que creían ser una. El censo es del código fuente, no de la
    memoria: cualquier `statement_timeout` literal nuevo fuera de
    `db/session.py` pone esto en rojo.
    """
    src = pathlib.Path(__file__).resolve().parents[2] / "src" / "takab_api"
    politica = src / "db" / "session.py"
    sueltos: dict[str, list[str]] = {}
    for fichero in src.rglob("*.py"):
        if fichero == politica:
            continue
        hallazgos = re.findall(
            r"statement_timeout\s*=\s*\d+", fichero.read_text(encoding="utf-8")
        )
        if hallazgos:
            sueltos[str(fichero.relative_to(src))] = hallazgos
    assert sueltos == {}, (
        f"topes de sentencia declarados fuera de la política única: {sueltos}. "
        "El día que el número cambie, cambia en un solo sitio o no cambia en ninguno."
    )
