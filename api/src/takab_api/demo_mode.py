"""Modo demostración — el interruptor que impide que una demo despierte a nadie.

[T-5.02 · D-27] Hasta esta ficha no existía ningún estado en el que el sistema no
molestara a nadie. Lo único que se llamaba «demo» era el reproductor de escenas
del panel del gabinete —cuyos botones mandaban órdenes de verdad hasta `T-5.01`—
y el ``simulated`` de las notificaciones, que **no es un modo**: es un estado
DERIVADO de la ausencia de credenciales, y por tanto desaparece justo en el
entorno donde se haría la demostración.

**Qué suprime, exactamente:** las salidas de la NUBE — entregas por cualquier
canal y comandos de actuador firmados. Nada más.

**Qué NO puede tocar, y es lo que hace aceptable lo anterior:** el gabinete. Este
estado no viaja por la config firmada, no llega al reflejo SASMEX→sirena y no
puede desarmar un relé. Regla de oro 1: el camino crítico no depende de la nube,
y tampoco de que la nube esté jugando. El día que alguien haga una demostración y
tiemble de verdad, el edificio lo protege un gabinete que nunca oyó hablar de
esto.

**Y lo real lo apaga.** Un evento real del cliente apaga el modo ANTES de que
entre a la cascada de notificación (:func:`apagar_por_evento_real`). El orden es
la parte que hace verdadera la promesa: así la ventana en la que algo real podría
quedar suprimido **no existe por construcción**, en vez de ser una ventana
estrecha que alguien tendría que medir. La lectura contraria —que el modo bloquee
el evento real— se rechazó sin discusión en `D-27`: sería un interruptor capaz de
silenciar un sismo.

**Dos frentes, un solo dueño de la pregunta.** El router y la superficie de
comandos van por SQLAlchemy async; el worker de notificación va por psycopg
síncrono y con ``takab_ingest`` (BYPASSRLS), porque despacha para todos los
clientes a la vez y no tiene un tenant en la mano. Las dos consultas viven aquí
para que no puedan divergir — mismo patrón que ``privacy/store.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from takab_api.audit import audit, audit_async

#: Techo de la ventana. El mismo número está en el CHECK de la tabla, que es
#: quien manda: un tope que solo vive en el código se salta con un INSERT a mano,
#: y este modo silencia los avisos de un edificio entero.
MAX_S = 8 * 3600
#: Por defecto, lo que dura una reunión con margen. Se puede pedir menos.
DEFAULT_S = 2 * 3600

#: Verbos de la bitácora. Encender, apagar a mano, y apagarse solo por un evento
#: real — los tres distintos a propósito: «lo apagó una persona» y «lo apagó un
#: sismo» son hechos distintos y el segundo es el que hay que poder buscar.
VERBO_ON = "demo_mode_on"
VERBO_OFF = "demo_mode_off"
VERBO_AUTO_OFF = "demo_mode_auto_off"
#: Un intento suprimido. Un modo que bloquea EN SILENCIO es otra superficie muda:
#: al día siguiente nadie sabría por qué no llegó el aviso.
VERBO_BLOQUEADO = "demo_mode_blocked"

_SELECT = """
SELECT tenant_id, enabled_by, enabled_at, expires_at, note
FROM demo_mode
WHERE tenant_id = :tenant AND expires_at > :now
"""

_SELECT_SYNC = """
SELECT tenant_id, enabled_by, enabled_at, expires_at, note
FROM demo_mode
WHERE tenant_id = %(tenant)s::uuid AND expires_at > %(now)s
"""


@dataclass(frozen=True)
class Ventana:
    """La ventana viva de un cliente. Sin fila viva, no hay ventana."""

    tenant_id: str
    enabled_by: str
    enabled_at: datetime
    expires_at: datetime
    note: str

    @property
    def restante_s(self) -> float:
        return max(0.0, (self.expires_at - datetime.now(tz=UTC)).total_seconds())


def ventana_maxima(segundos: int | None) -> int:
    """Acota lo pedido al techo. Sin petición, el defecto.

    Se acota en vez de rechazar porque el CHECK de la base ya rechaza; aquí lo
    que interesa es que la interfaz no pueda pedir una ventana imposible y
    llevarse un 500 en la cara del cliente.
    """
    if segundos is None:
        return DEFAULT_S
    return max(60, min(int(segundos), MAX_S))


async def ventana_viva(
    conn: AsyncConnection, tenant_id: str, *, now: datetime | None = None
) -> Ventana | None:
    """La ventana viva de este cliente, o ``None``.

    Vencida cuenta como apagada **sin que nadie tenga que barrer**: la hora entra
    en la consulta. Un modo que necesitara un proceso para expirar sería un modo
    que se queda encendido el día que ese proceso falle.
    """
    now = now or datetime.now(tz=UTC)
    row = (await conn.execute(text(_SELECT), {"tenant": tenant_id, "now": now})).mappings().first()
    if row is None:
        return None
    return Ventana(
        tenant_id=str(row["tenant_id"]),
        enabled_by=str(row["enabled_by"]),
        enabled_at=row["enabled_at"],
        expires_at=row["expires_at"],
        note=row["note"],
    )


def ventana_viva_sync(
    conn: psycopg.Connection, tenant_id: str, *, now: datetime | None = None
) -> Ventana | None:
    """Gemelo SÍNCRONO para el worker de notificación. Misma consulta."""
    now = now or datetime.now(tz=UTC)
    with conn.cursor() as cur:
        cur.execute(_SELECT_SYNC, {"tenant": str(tenant_id), "now": now})
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d.name for d in cur.description or ()]
    d = dict(zip(cols, row, strict=True))
    return Ventana(
        tenant_id=str(d["tenant_id"]),
        enabled_by=str(d["enabled_by"]),
        enabled_at=d["enabled_at"],
        expires_at=d["expires_at"],
        note=d["note"],
    )


class IncidenteAbierto(Exception):
    """No se entra en modo demostración con un incidente vivo."""


async def hay_incidente_abierto(conn: AsyncConnection, tenant_id: str) -> bool:
    row = (
        await conn.execute(
            text("SELECT 1 FROM incidents WHERE tenant_id = :t AND state <> 'closed' LIMIT 1"),
            {"t": tenant_id},
        )
    ).first()
    return row is not None


async def encender(
    conn: AsyncConnection,
    *,
    tenant_id: str,
    actor: str,
    segundos: int | None,
    note: str,
    now: datetime | None = None,
) -> Ventana:
    """Enciende (o re-arma) la ventana de un cliente y lo audita.

    Re-encender PISA la ventana anterior en vez de sumarse: dos ventanas del
    mismo cliente serían dos verdades sobre cuándo se apaga.

    **Con un incidente abierto NO se enciende.** Es la otra mitad de «lo real
    gana», y la descubrió un test: si un evento apaga el modo, permitir
    encenderlo con un evento vivo dejaría al operador creyendo que está
    demostrando mientras la cascada de un incidente REAL sigue en vuelo — y la
    puerta de notificación la suprimiría. Con las dos reglas juntas, el modo y un
    incidente vivo **no pueden coexistir**, así que esa supresión no puede
    ocurrir: no es que sea improbable, es que no hay estado donde ocurra.
    """
    now = now or datetime.now(tz=UTC)
    if await hay_incidente_abierto(conn, tenant_id):
        raise IncidenteAbierto
    expires = now + timedelta(seconds=ventana_maxima(segundos))
    # Re-encender es REEMPLAZAR, y se escribe como tal: borrado + alta, no
    # `ON CONFLICT DO UPDATE`. Dos razones y las dos importan. La primera es de
    # privilegio: el `DO UPDATE` exige UPDATE sobre la tabla, y darlo dejaría a la
    # API capaz de correrle la hora de vencimiento a una ventana viva sin que eso
    # sea un acto nuevo. La segunda es semántica: una ventana re-armada tiene su
    # propio `enabled_at`, porque es otra ventana.
    await conn.execute(text("DELETE FROM demo_mode WHERE tenant_id = :t"), {"t": tenant_id})
    await conn.execute(
        text(
            "INSERT INTO demo_mode (tenant_id, enabled_by, enabled_at, expires_at, note)"
            " VALUES (:t, :by, :at, :exp, :note)"
        ),
        {"t": tenant_id, "by": actor, "at": now, "exp": expires, "note": note},
    )
    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=actor,
        verb=VERBO_ON,
        obj=f"tenant:{tenant_id}",
        meta={"expires_at": expires.isoformat(), "note": note},
    )
    return Ventana(
        tenant_id=tenant_id, enabled_by=actor, enabled_at=now, expires_at=expires, note=note
    )


async def apagar(
    conn: AsyncConnection, *, tenant_id: str, actor: str, motivo: str = "manual"
) -> bool:
    """Apaga la ventana. Devuelve si había algo que apagar.

    Apagar es borrar la fila, y por eso la tabla no es append-only: un estado que
    no se puede vaciar sería un modo que no se puede apagar. El HECHO queda en
    ``audit_log``, que sí lo es.
    """
    r = await conn.execute(text("DELETE FROM demo_mode WHERE tenant_id = :t"), {"t": tenant_id})
    habia = bool(r.rowcount)
    if habia:
        await audit_async(
            conn,
            tenant_id=tenant_id,
            actor=actor,
            verb=VERBO_OFF,
            obj=f"tenant:{tenant_id}",
            meta={"motivo": motivo},
        )
    return habia


def apagar_por_evento_real_sync(conn: psycopg.Connection, *, tenant_id: str, causa: str) -> bool:
    """**Lo real gana.** Apaga el modo ANTES de procesar un evento real.

    El ORDEN es la promesa: se llama antes de encolar la cascada, no después. Así
    la ventana en la que un sismo podría quedar suprimido no existe por
    construcción. Devuelve si estaba encendido — el llamador lo necesita para
    poder gritarlo, porque quien esté demostrando tiene que enterarse de que ya
    no está demostrando.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM demo_mode WHERE tenant_id = %(t)s::uuid", {"t": str(tenant_id)})
        habia = bool(cur.rowcount)
    if habia:
        audit(
            conn,
            tenant_id=str(tenant_id),
            actor="system:incident",
            verb=VERBO_AUTO_OFF,
            obj=f"tenant:{tenant_id}",
            meta={"causa": causa},
        )
    return habia


def auditar_bloqueo_sync(
    conn: psycopg.Connection, *, tenant_id: str, obj: str, meta: dict[str, Any]
) -> None:
    """Deja constancia de UN intento suprimido por el modo.

    Sin esto el modo sería otra superficie muda: al día siguiente nadie podría
    responder por qué no llegó un aviso.
    """
    audit(
        conn,
        tenant_id=str(tenant_id),
        actor="system:demo_mode",
        verb=VERBO_BLOQUEADO,
        obj=obj,
        meta=meta,
    )
