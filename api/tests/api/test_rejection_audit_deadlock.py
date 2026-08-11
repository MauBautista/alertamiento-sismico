"""T-2.112 · La bitácora de rechazos abría la MISMA conexión lateral que T-2.73.c.

`commands/rejection_audit.py` declaraba en su propio docstring seguir el patrón de
`audit.audit_out_of_band_async`. Lo seguía, sí — incluida la parte rota: escribía en
`audit_log` desde una conexión LATERAL **sin tope de espera**, con la transacción del
request abierta y esperando en Python.

El ciclo, que PostgreSQL **no puede** detectar:

    request  ──(ACCESS SHARE de audit_log, txn abierta)──> espera en Python a la lateral
    tercero  ──(pide ACCESS EXCLUSIVE de audit_log)──────> se encola detrás del request
    lateral  ──(pide ACCESS SHARE de audit_log)──────────> se encola detrás del tercero

El detector de interbloqueos no lo ve porque la conexión del request no está esperando
un lock: está *idle in transaction*. Sin tope, la espera es literalmente para siempre —
y el `except Exception` "best-effort" del helper nunca llega a ejecutarse, porque no hay
excepción que capturar, solo una espera infinita.

Estos tests son la evidencia MEDIDA de que el defecto existía también aquí (antes del
arreglo se cuelgan) y la no-regresión de que la lateral ahora cede.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.auth.claims import Claims
from takab_api.commands import rejection_audit as ra
from takab_api.db.engine import get_engine
from takab_api.db.session import SessionCtx, get_tenant_conn

pytestmark = pytest.mark.asyncio

SITE_DL = "7e600000-0000-0000-0000-00000000015e"
SUB_DL = "7e600000-0000-0000-0000-0000000000a1"

#: Tope del TEST, no del producto. Muy por encima del `lock_timeout` de la lateral
#: (3 s) para que un CI lento no invente un rojo, y muy por debajo de "para siempre"
#: para que el rojo llegue como fallo con nombre en vez de como un proceso colgado.
_TOPE_TEST_S = 25.0

_LOCK_EXCLUSIVO = text("LOCK TABLE audit_log IN ACCESS EXCLUSIVE MODE")
_ENCOLADOS = text(
    "SELECT count(*) FROM pg_locks "
    "WHERE relation = 'audit_log'::regclass AND mode = 'AccessExclusiveLock' AND NOT granted"
)
_CUENTA_RECHAZOS = text("SELECT count(*) FROM audit_log WHERE verb = :v")


def _claims() -> Claims:
    return Claims(
        sub=SUB_DL,
        groups=("tenant_admin",),
        tenant_id=au.DB_TENANT_PRIV,
        role="tenant_admin",
        site_scope=frozenset({SITE_DL}),
        zone_id="",
        surface="web",
    )


def _ctx() -> SessionCtx:
    return SessionCtx(tenant_id=au.DB_TENANT_PRIV, role="tenant_admin", user_id=SUB_DL)


async def _auditar_rechazo(reason: str = "intent_missing") -> None:
    await ra.audit_command_rejection(
        claims=_claims(),
        tenant_id=au.DB_TENANT_PRIV,
        site_id=SITE_DL,
        reason=reason,
        status=403,
        channel="siren",
        action="activate",
    )


async def _sin_colgarse(motivo: str) -> float:
    """Ejecuta la auditoría del rechazo con tope y devuelve cuánto tardó."""
    inicio = time.monotonic()
    try:
        await asyncio.wait_for(_auditar_rechazo(), _TOPE_TEST_S)
    except TimeoutError:
        pytest.fail(
            f"la conexión lateral de `audit_command_rejection` se colgó {_TOPE_TEST_S:.0f} s "
            f"esperando el lock de audit_log ({motivo}). Sin tope la espera es INFINITA y se "
            "lleva por delante la transacción del request (T-2.73.c / T-2.112)."
        )
    return time.monotonic() - inicio


async def _rechazos() -> int:
    engine = get_engine()
    async with engine.connect() as conn:
        return (await conn.execute(_CUENTA_RECHAZOS, {"v": ra.REJECTION_VERB})).scalar_one()


async def _esperar_encolado(tope_s: float = 15.0) -> None:
    """Bloquea hasta que el ACCESS EXCLUSIVE del tercero esté ENCOLADO (no concedido)."""
    engine = get_engine()
    limite = time.monotonic() + tope_s
    while time.monotonic() < limite:
        async with engine.connect() as vigia:
            if (await vigia.execute(_ENCOLADOS)).scalar_one():
                return
        await asyncio.sleep(0.05)
    pytest.fail("el tercero nunca se encoló por el ACCESS EXCLUSIVE de audit_log")


async def test_la_lateral_del_rechazo_cede_el_lock_en_vez_de_colgarse(base_data: None) -> None:
    """Con `audit_log` bajo ACCESS EXCLUSIVE ajeno, la lateral CIERRA su transacción.

    Se pierde el contador —queda en el log del servicio—; no se pierde ni el 403 ni la
    conexión del request, que es lo que este test fija.
    """
    engine = get_engine()
    async with engine.connect() as bloqueo:
        await bloqueo.execute(_LOCK_EXCLUSIVO)
        tardanza = await _sin_colgarse("lock exclusivo sostenido por un tercero")
        await bloqueo.rollback()

    assert tardanza < _TOPE_TEST_S, f"la lateral esperó {tardanza:.0f} s: el tope no actúa"
    assert await _rechazos() == 0, "sin lock la lateral cede la fila: es best-effort, no bloqueo"


async def test_el_ciclo_a_tres_bandas_no_cuelga_al_request(base_data: None) -> None:
    """El interbloqueo COMPLETO de T-2.73.c, reproducido sobre la ruta de rechazos.

    Es el caso que PostgreSQL no puede romper: la conexión del request sostiene el
    ACCESS SHARE de `audit_log` mientras espera en Python, así que el `deadlock_timeout`
    del servidor nunca ve un ciclo de locks. Antes del arreglo esto colgaba el proceso
    de tests entero (y envenenaba la base para la corrida siguiente).
    """
    engine = get_engine()
    async with get_tenant_conn(_ctx()) as request_conn:
        # 1) El request ya leyó audit_log: sostiene su ACCESS SHARE toda la transacción.
        await request_conn.execute(_CUENTA_RECHAZOS, {"v": ra.REJECTION_VERB})

        tercero = await engine.connect()
        encolado = asyncio.create_task(tercero.execute(_LOCK_EXCLUSIVO))
        try:
            # 2) El tercero pide el ACCESS EXCLUSIVE y se encola DETRÁS del request.
            await _esperar_encolado()
            assert not encolado.done(), "el tercero no debería tener el lock: el request lo veta"

            # 3) La lateral pide ACCESS SHARE y se encola DETRÁS del tercero: ciclo cerrado.
            tardanza = await _sin_colgarse("ciclo a tres bandas request→lateral→exclusivo")
            assert tardanza < _TOPE_TEST_S

            # Lo que de verdad importa: el request sigue vivo y puede responder su 403.
            assert (await request_conn.execute(text("SELECT 1"))).scalar_one() == 1
        finally:
            encolado.cancel()
            with contextlib.suppress(BaseException):
                await encolado
            with contextlib.suppress(BaseException):
                await tercero.close()


async def test_sin_bloqueo_el_rechazo_sigue_dejando_su_fila(base_data: None) -> None:
    """El tope no puede volverse una excusa para dejar de auditar el camino normal."""
    await _auditar_rechazo("nonce_replay")
    assert await _rechazos() == 1
