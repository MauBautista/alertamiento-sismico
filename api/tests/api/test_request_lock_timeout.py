"""[T-2.130] Qué le pasa a la conexión del REQUEST con la tabla bloqueada. MEDIDO.

`T-2.121` puso tope a las conexiones de SEGUNDO PLANO (hub, poller y las dos
laterales de auditoría: 3 s). La conexión del **request** se quedó fuera a
propósito, porque cambiaba la conducta de toda la API bajo contención y eso era
una decisión de producto (`PENDIENTES-MAURICIO §1.8`). La decisión ya está
tomada: **se pone el tope**.

Lo medido contra el código anterior al arreglo (2026-08-12), con un
`LOCK TABLE incidents IN ACCESS EXCLUSIVE MODE` de un tercero:

    · Un `GET /incidents` **no vuelve nunca**. Con techo de 25 s en el test, el
      request seguía dentro del `SELECT`, encolado detrás del lock ajeno.
    · Y no es una petición la que se degrada, es **el proceso**: cada request
      encolado retiene su conexión del pool (5+5). Con las diez ocupadas,
      `GET /sites` —que no toca `incidents` ni de lejos— se queda sin conexión y
      muere con el `TimeoutError` del pool a los **30 s**.

El criterio duro que fija el número, y que estos tests anclan: **el tope del
request debe ser MENOR que el timeout del pool**. Por debajo, un bloqueo degrada
*una petición*; por encima —o sin tope— degrada *todo lo que comparte el pool*.
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
    BACKGROUND_LOCK_TIMEOUT_MS,
    REQUEST_LOCK_TIMEOUT_MS,
    LockTimeout,
    SessionCtx,
    get_tenant_conn,
)

pytestmark = pytest.mark.asyncio

_USER = "abcabcab-0000-0000-0000-0000000000c1"

#: Techo del TEST, no del producto. Por encima del tope del request (10 s) para
#: que un CI lento no invente un rojo, y por DEBAJO del timeout del pool (30 s)
#: para que un cuelgue llegue con nombre y no se confunda con el otro fallo.
_TOPE_TEST_S = 25.0

_LOCK_INCIDENTS = "LOCK TABLE incidents IN ACCESS EXCLUSIVE MODE"

#: ¿Cuántos ESPERAN el ACCESS SHARE de la tabla? Es la prueba de que el
#: escenario es real y no una simulación: los requests están encolados, no lentos.
#: Va por psycopg crudo (placeholder ``%s``, no ``:bind``) porque el vigía NO
#: puede salir del pool de la API: si saliera, mediría el pool que él mismo
#: encogió.
_ESPERANDO_LECTURA = (
    "SELECT count(*) FROM pg_locks WHERE relation = CAST(%s AS regclass) "
    "AND mode = 'AccessShareLock' AND NOT granted"
)


def _token(role: str = "soc_operator", tenant: str = au.DB_TENANT_PRIV) -> dict[str, str]:
    return au.bearer(au.make_token(role, tenant=tenant, site_scope="*", user_id=_USER))


def _raw_dsn() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


def _cupo_del_pool() -> int:
    """Conexiones simultáneas que la API puede tener abiertas (``pool_size`` + overflow)."""
    pool = get_engine().pool
    return pool.size() + pool._max_overflow  # noqa: SLF001 - no hay accesor público


async def _esperar_encolados(n: int, tabla: str = "incidents", tope_s: float = 15.0) -> None:
    """Bloquea hasta ver ``n`` backends esperando leer ``tabla`` (o falla con nombre)."""
    limite = time.monotonic() + tope_s
    visto = 0
    async with await psycopg.AsyncConnection.connect(_raw_dsn()) as vigia:
        while time.monotonic() < limite:
            cur = await vigia.execute(_ESPERANDO_LECTURA, (tabla,))
            fila = await cur.fetchone()
            visto = fila[0] if fila else 0
            if visto >= n:
                return
            await asyncio.sleep(0.05)
    pytest.fail(f"solo {visto} de {n} backends se encolaron por {tabla}: el escenario no se montó")


class _Bloqueo:
    """Tercero que toma el ACCESS EXCLUSIVE de ``incidents`` FUERA del pool de la API.

    Fuera del pool a propósito: si el bloqueo consumiera una de las 10 conexiones
    de la API, el test mediría un pool más pequeño que el de producción y el
    hallazgo del agotamiento saldría falseado.
    """

    def __init__(self) -> None:
        self._conn: psycopg.AsyncConnection | None = None

    async def __aenter__(self) -> _Bloqueo:
        self._conn = await psycopg.AsyncConnection.connect(_raw_dsn())
        await self._conn.execute(_LOCK_INCIDENTS)
        return self

    async def soltar(self) -> None:
        if self._conn is not None:
            await self._conn.rollback()
            await self._conn.close()
            self._conn = None

    async def __aexit__(self, *_exc: object) -> None:
        await self.soltar()


async def test_MEDIDO_un_request_contra_la_tabla_bloqueada_CEDE_con_nombre(
    client, make_incident
) -> None:
    """Criterios 1 y 2: hay tope, y el cliente recibe algo interpretable.

    Antes: el request se quedaba dentro del `SELECT` para siempre. Ahora cede al
    vencer la política y responde **503 + Retry-After** — que es lo que un
    cliente sabe leer; un cuelgue no se puede ni reintentar ni diagnosticar.
    """
    await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    async with _Bloqueo():
        inicio = time.monotonic()
        tarea = asyncio.create_task(client.get("/incidents", headers=_token()))
        await _esperar_encolados(1)
        try:
            resp = await asyncio.wait_for(tarea, _TOPE_TEST_S)
        except TimeoutError:
            tarea.cancel()
            pytest.fail(
                f"el request siguió esperando el lock de `incidents` tras {_TOPE_TEST_S:.0f} s. "
                "Sin tope la espera dura lo que dure el lock ajeno, y diez de estas agotan el "
                "pool y tumban también lo que no tocaba la tabla (T-2.130)."
            )
        tardanza = time.monotonic() - inicio

    assert resp.status_code == 503, resp.text
    assert resp.headers.get("Retry-After") is not None, "un 503 sin Retry-After no es accionable"
    assert "lock" in resp.json()["detail"].lower()
    assert tardanza < _TOPE_TEST_S, f"cedió en {tardanza:.1f} s: el tope no actúa"


async def test_MEDIDO_el_pool_NO_se_agota_el_request_ajeno_sigue_servido(
    client, make_incident
) -> None:
    """Criterio 3: bajo contención, lo que no toca la tabla bloqueada se sirve.

    Este es el test que justifica el número. Se llenan **todas** las conexiones
    de la API con peticiones encoladas contra la tabla bloqueada y se pide algo
    que no la toca. Antes: `TimeoutError` del pool a los 30 s — el bloqueo de UNA
    tabla dejaba sin servicio a la API entera. Ahora los ocupantes ceden al
    vencer su tope, devuelven la conexión y el request ajeno se sirve.
    """
    await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    cupo = _cupo_del_pool()
    async with _Bloqueo():
        atascados = [
            asyncio.create_task(client.get("/incidents", headers=_token())) for _ in range(cupo)
        ]
        await _esperar_encolados(cupo)

        inicio = time.monotonic()
        try:
            ajeno = await asyncio.wait_for(client.get("/sites", headers=_token()), _TOPE_TEST_S)
        except TimeoutError:
            for t in atascados:
                t.cancel()
            pytest.fail(
                f"`GET /sites` —que no toca `incidents`— no se sirvió en {_TOPE_TEST_S:.0f} s "
                f"con las {cupo} conexiones del pool encoladas. Eso es el proceso degradado, "
                "no una petición (T-2.130)."
            )
        espera_ajeno = time.monotonic() - inicio
        respuestas = await asyncio.gather(*atascados)

    assert ajeno.status_code == 200, ajeno.text
    assert espera_ajeno < _TOPE_TEST_S
    # Los que sí tocaban la tabla degradan uno a uno, con nombre y sin colgarse.
    assert {r.status_code for r in respuestas} == {503}


async def test_una_espera_por_lock_de_FILA_legitima_NO_se_corta(make_incident) -> None:
    """Criterio 4: el tope no puede romper la serialización de escrituras.

    Es la razón de que el número sea 10 s y no los 3 s del segundo plano: hay
    esperas por lock de FILA que son correctas —dos acuses del mismo incidente se
    serializan— y cortarlas convertiría una espera sana en un 503. Aquí un
    tercero retiene la fila un rato holgado por debajo del tope y el request debe
    **esperarla y ganarla**, no ceder.
    """
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    retencion_s = 2.0
    ctx = SessionCtx(tenant_id=au.DB_TENANT_PRIV, role="soc_operator", user_id=_USER)

    async with await psycopg.AsyncConnection.connect(_raw_dsn()) as tercero:
        await tercero.execute(
            "UPDATE incidents SET severity = 'critical' WHERE incident_id = %s", (iid,)
        )  # sin commit: retiene el lock de FILA

        async def _soltar_luego() -> None:
            await asyncio.sleep(retencion_s)
            await tercero.rollback()

        soltar = asyncio.create_task(_soltar_luego())
        inicio = time.monotonic()
        async with get_tenant_conn(ctx) as conn:
            fila = (
                await conn.execute(
                    text("SELECT state FROM incidents WHERE incident_id = :i FOR UPDATE"),
                    {"i": iid},
                )
            ).first()
        espera = time.monotonic() - inicio
        await soltar

    assert fila is not None, "la espera por lock de fila se cortó: el tope es demasiado corto"
    assert espera >= retencion_s * 0.8, "no llegó a esperar: el escenario no se montó"
    assert espera < REQUEST_LOCK_TIMEOUT_MS / 1000.0


async def test_la_politica_del_request_es_MENOR_que_el_timeout_del_pool() -> None:
    """El criterio duro de la ficha, anclado contra el pool REAL — no contra un número copiado.

    Si alguien sube el tope por encima del timeout del pool, un bloqueo vuelve a
    degradar el proceso entero en vez de una petición. Este candado es la única
    cosa que impide que ese cambio pase inadvertido.
    """
    pool = get_engine().pool
    timeout_pool_s = pool._timeout  # noqa: SLF001 - no hay accesor público
    assert REQUEST_LOCK_TIMEOUT_MS / 1000.0 < timeout_pool_s, (
        f"tope del request {REQUEST_LOCK_TIMEOUT_MS} ms ≥ timeout del pool {timeout_pool_s} s: "
        "diez esperas agotarían el pool y fallaría también lo que no toca la tabla bloqueada"
    )
    assert BACKGROUND_LOCK_TIMEOUT_MS < REQUEST_LOCK_TIMEOUT_MS, (
        "el segundo plano es best-effort y cede antes; el request es una persona esperando"
    )


async def test_el_tope_sale_de_UNA_politica_y_no_de_numeros_sueltos() -> None:
    """Criterio 1, segunda mitad: un solo sitio declara los milisegundos.

    Un número suelto en un módulo cualquiera es exactamente cómo derivan dos
    políticas que creían ser una. El censo es del código fuente, no de la
    memoria: cualquier `lock_timeout` literal nuevo fuera de `db/session.py`
    pone esto en rojo.
    """
    src = pathlib.Path(__file__).resolve().parents[2] / "src" / "takab_api"
    politica = src / "db" / "session.py"
    sueltos: dict[str, list[str]] = {}
    for fichero in src.rglob("*.py"):
        if fichero == politica:
            continue
        hallazgos = re.findall(r"lock_timeout\s*=\s*\d+", fichero.read_text(encoding="utf-8"))
        if hallazgos:
            sueltos[str(fichero.relative_to(src))] = hallazgos
    assert sueltos == {}, (
        f"topes de lock declarados fuera de la política única: {sueltos}. "
        "El día que el número cambie, cambia en un solo sitio o no cambia en ninguno."
    )


async def test_el_error_del_tope_sigue_siendo_un_fallo_de_BASE_para_quien_ya_lo_trataba(
    make_incident,
) -> None:
    """El `LockTimeout` es a la vez error HTTP y error de base — y las dos hacen falta.

    Cuatro sitios ya trataban el fallo de la base como best-effort y siguen
    dependiendo de ello: las dos laterales de auditoría (`audit.py`,
    `commands/rejection_audit.py`) —que se tragan el fallo para no convertir un
    403 en un 500— y el hub/poller del WS, que degradan el canal en vez de morir.
    Si el tope lanzara SOLO un `HTTPException`, se les escaparía por debajo del
    `except SQLAlchemyError` y esos tres arreglos se romperían en silencio.
    """
    from sqlalchemy.exc import SQLAlchemyError

    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    ctx = SessionCtx(tenant_id=au.DB_TENANT_PRIV, role="soc_operator", user_id=_USER)
    async with _Bloqueo():
        atrapado: Exception | None = None
        try:
            async with get_tenant_conn(ctx, lock_timeout_ms=200) as conn:
                await conn.execute(
                    text("SELECT 1 FROM incidents WHERE incident_id = :i"), {"i": iid}
                )
        except SQLAlchemyError as exc:  # el except que ya existe en los cuatro sitios
            atrapado = exc

    assert isinstance(atrapado, LockTimeout), "un `except SQLAlchemyError` debe seguir cazándolo"
    assert atrapado.status_code == 503
