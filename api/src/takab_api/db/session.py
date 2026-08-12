"""Sesión de tenant async: rol + GUCs RLS + tope de espera por lock (T-1.18, T-2.130).

Espeja ``api/tests/conftest.py::use`` para el stack async: ``SET LOCAL ROLE
takab_app`` (allowlist → sin inyección de identificador) + tres
``set_config('app.*', :v, true)`` PARAMETRIZADOS. Todo vive en la transacción:
los GUCs son locales (``is_local=true``) y el rol es ``SET LOCAL``, así que al
hacer commit/rollback la conexión vuelve limpia al pool y una request posterior
que la reutilice NO hereda el contexto de tenant (fuga cero).

[T-2.130] **Aquí vive la política ÚNICA de topes de espera por lock**, y toda
conexión que salga de ``get_tenant_conn`` la lleva puesta. Ver el bloque de
constantes de abajo para el criterio; el resumen es que sin tope un bloqueo de
UNA tabla no degrada una petición, degrada el proceso entero.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import TextClause, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.db.engine import get_engine

# Allowlist de roles de conexión (espejo de conftest.DB_ROLES): el nombre de rol
# es un identificador y no puede ir como bind param, así que se restringe aquí.
DB_ROLES = frozenset({"takab_app", "takab_ingest", "takab_migrator"})

_SET_TENANT = text("SELECT set_config('app.tenant_id', :v, true)")
_SET_ROLE = text("SELECT set_config('app.role', :v, true)")
_SET_USER = text("SELECT set_config('app.user_id', :v, true)")


# --------------------------------------------------------------------------
# POLÍTICA ÚNICA DE TOPES DE ESPERA POR LOCK (T-2.73.c · T-2.112 · T-2.121 · T-2.130)
# --------------------------------------------------------------------------
# Dos escalones, UN solo sitio donde se declaran. No es cosmética: hasta hoy el
# número del segundo plano vivía en ``audit.py`` y el del request no existía, y
# la única forma de que dos políticas no deriven es que sean una.
#
# El CRITERIO DURO, medido en T-2.121 y re-medido en T-2.130 contra la conexión
# del request: **el tope debe ser MENOR que el timeout del pool** (30 s, el
# default de SQLAlchemy que usa ``db/engine.py``). Por debajo, un bloqueo degrada
# *una petición*; por encima —o sin tope, como estaba— degrada *el proceso*,
# porque cada petición encolada retiene su conexión y con las 10 del pool
# ocupadas falla también lo que ni siquiera tocaba la tabla bloqueada.
# Medido sin tope: `GET /incidents` sin respuesta a los 25 s, y `GET /sites`
# —que no toca `incidents`— muerto con el `TimeoutError` del pool a los 30.01 s.
# Lo ancla ``tests/api/test_request_lock_timeout.py``.

#: Tope de la conexión del REQUEST. NO son los 3 s del segundo plano, y la razón
#: importa: una auditoría lateral es best-effort y se puede tirar; **un request
#: es una persona esperando**, y hay esperas por lock de FILA legítimas —dos
#: acuses del mismo incidente se serializan— que cortar a 3 s convertiría en un
#: 503 donde hoy hay una espera sana de un par de segundos.
REQUEST_LOCK_TIMEOUT_MS = 10_000

#: Tope de las conexiones de SEGUNDO PLANO (las dos laterales de auditoría, el
#: hub del WS y el poller). Ceden antes a propósito: ninguna de ellas es una
#: persona esperando y todas tienen un camino degradado ya escrito.
#: Se reexporta como ``audit.LATERAL_LOCK_TIMEOUT_MS`` por compatibilidad.
BACKGROUND_LOCK_TIMEOUT_MS = 3_000


class LockTimeout(HTTPException, SQLAlchemyError):
    """La base no concedió un lock dentro de la política. Error CON NOMBRE.

    Hereda de las DOS cosas a la vez, y las dos hacen falta:

    · ``HTTPException`` — para que el cliente reciba un **503 + Retry-After** en
      vez de un 500 pelado o, peor, un cuelgue. Un 503 se lee, se reintenta y se
      distingue de «la nube está rota».
    · ``SQLAlchemyError`` — porque cuatro sitios ya tratan el fallo de la base
      como best-effort y **siguen dependiendo de ello**: las dos laterales de
      auditoría (``audit.py``, ``commands/rejection_audit.py``), que se lo tragan
      para no convertir un 403 en un 500, y el hub y el poller del WS (T-2.121),
      que degradan el canal en vez de morir. Si esto fuera solo un
      ``HTTPException`` se les escaparía por debajo del ``except
      SQLAlchemyError`` y esos cuatro arreglos se romperían en silencio, que es
      justo la clase de regresión que no la ve nadie hasta que hay un sismo.
    """

    def __init__(self, timeout_ms: int) -> None:
        #: Escalón que pidió esta conexión. NO se mete en el ``detail`` a
        #: propósito: un llamador puede haber vuelto a fijar el `lock_timeout`
        #: por su cuenta dentro de la transacción (las dos laterales de
        #: auditoría lo hacen), y entonces el número que pusiéramos en el
        #: mensaje sería una cifra derivada y FALSA — la clase de detalle que
        #: parece inocente y luego se cita en un diagnóstico.
        self.timeout_ms = timeout_ms
        HTTPException.__init__(
            self,
            status_code=503,
            detail=(
                "la base no concedió el lock a tiempo: el recurso está ocupado por otra "
                "operación. El dato existe; vuelve a intentarlo."
            ),
            # Un 503 sin Retry-After no es accionable. 5 s: un TRUNCATE/VACUUM de
            # mantenimiento no se va en uno, y reintentar en bucle apretado sobre
            # una tabla bloqueada solo añade backends esperando.
            headers={"Retry-After": "5"},
        )


#: SQLSTATE del `lock_timeout` de PostgreSQL (``lock_not_available``). NO cubre
#: 57014 (`statement_timeout`/cancelación) ni la caída de la conexión: son fallos
#: distintos y traducirlos todos a 503 escondería una base caída detrás de un
#: «recurso ocupado».
_SQLSTATE_LOCK_TIMEOUT = "55P03"


@lru_cache(maxsize=8)
def lock_timeout_stmt(timeout_ms: int) -> TextClause:
    """``SET LOCAL lock_timeout`` para ``timeout_ms``.

    Literal entero interpolado porque ``SET LOCAL`` no admite bind params; el
    ``int()`` de la validación es lo que impide que esto sea una inyección si
    algún día el valor dejara de ser una constante del módulo.
    """
    ms = int(timeout_ms)
    if ms <= 0:
        raise ValueError(f"tope de lock no válido: {timeout_ms!r}")
    return text(f"SET LOCAL lock_timeout = {ms}")


def es_lock_timeout(exc: BaseException) -> bool:
    """True si el error es el ``lock_timeout`` de PostgreSQL y no otro fallo."""
    orig = getattr(exc, "orig", None)
    return getattr(orig, "sqlstate", None) == _SQLSTATE_LOCK_TIMEOUT


@dataclass(frozen=True, slots=True)
class SessionCtx:
    """Contexto mínimo por request para RLS (desacoplado de ``auth.claims``)."""

    tenant_id: str
    role: str
    user_id: str

    @classmethod
    def from_claims(cls, claims: object) -> SessionCtx:
        """Puente desde un objeto de claims con ``.tenant_id``/``.role``/``.sub``."""
        return cls(
            tenant_id=getattr(claims, "tenant_id", "") or "",
            role=getattr(claims, "role", "") or "",
            user_id=getattr(claims, "sub", "") or "",
        )


@asynccontextmanager
async def get_tenant_conn(
    ctx: SessionCtx,
    *,
    set_session_role: str | None = "takab_app",
    lock_timeout_ms: int = REQUEST_LOCK_TIMEOUT_MS,
) -> AsyncIterator[AsyncConnection]:
    """Conexión async dentro de una txn con rol de conexión + GUCs RLS fijados.

    Commit al salir sin excepción; rollback ante cualquier error. Uso::

        async with get_tenant_conn(ctx) as conn:
            await conn.execute(...)

    ``set_session_role`` debe estar en ``DB_ROLES`` (o ``None`` para no cambiar
    de rol: producción ya conecta como ``takab_app``).

    [T-2.130] ``lock_timeout_ms`` por defecto es el escalón del REQUEST. El
    segundo plano pasa ``BACKGROUND_LOCK_TIMEOUT_MS`` explícitamente. Alcance de
    lo que esto cubre, para que nadie le pida más de lo que hace:

    · ``SET LOCAL`` solo vive DENTRO de la transacción — por eso se fija aquí,
      donde la transacción ya está abierta, y por eso ``get_healthcheck_conn``
      (sin transacción) no lo lleva; tampoco lo necesita, ``SELECT 1`` no pide
      locks.
    · Acota **esperas por lock**, no consultas lentas: un ``SELECT`` que tarde
      una hora leyendo no lo toca esto (eso sería ``statement_timeout``, que es
      otra decisión y otro modo de fallo).
    · NO llega a los workers de ingesta/notify/config-sync: conectan por
      ``db/pool.py`` (psycopg síncrono, conexión propia por proceso) y no pasan
      por aquí. Es deliberado — ver la ficha T-2.130.
    """
    if set_session_role is not None and set_session_role not in DB_ROLES:
        raise ValueError(f"rol no permitido: {set_session_role!r}")
    stmt_tope = lock_timeout_stmt(lock_timeout_ms)  # valida ANTES de tomar conexión
    engine = get_engine()
    async with engine.connect() as conn, conn.begin():
        if set_session_role is not None:
            await conn.execute(text(f'SET LOCAL ROLE "{set_session_role}"'))
        # Después del rol, nunca antes: ``SET ROLE`` puede arrastrar ajustes por
        # rol y dejar el tope pisado sin que se note.
        await conn.execute(stmt_tope)
        await conn.execute(_SET_TENANT, {"v": ctx.tenant_id})
        await conn.execute(_SET_ROLE, {"v": ctx.role})
        await conn.execute(_SET_USER, {"v": ctx.user_id})
        try:
            yield conn
        except DBAPIError as exc:
            # El error nace en el ``execute`` de quien nos usa y pasa por este
            # ``yield``: es el único punto donde se puede traducir sin obligar a
            # cada router a saber que existe un tope.
            if es_lock_timeout(exc):
                raise LockTimeout(lock_timeout_ms) from exc
            raise


@asynccontextmanager
async def get_healthcheck_conn() -> AsyncIterator[AsyncConnection]:
    """Conexión sin rol ni GUCs para liveness/readiness (``SELECT 1``)."""
    engine = get_engine()
    async with engine.connect() as conn:
        yield conn
