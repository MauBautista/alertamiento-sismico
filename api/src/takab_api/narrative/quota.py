"""Cuota de gasto de IA por tenant y mes (T-5.18).

Había contabilidad **por llamada** y techo de tokens **por llamada**. No había
cuota, ni contador acumulado, ni corte: encender la perilla podía costar lo que
fuera. Es lo que OWASP llama consumo de recursos sin restricción, y hoy el riesgo
está acotado **solo por que la perilla está apagada** — por eso el tope aterriza
antes del shadow-mode y no después.

LAS CUATRO DECISIONES QUE GOBIERNAN ESTE MÓDULO
----------------------------------------------

**1. Agotada la cuota, se cae al determinista y se DECLARA. Jamás se falla la
exportación.** El PDF del dictamen es una superficie de vida: alguien lo está
usando para decidir si un edificio se ocupa. Un 429 ahí convertiría un tope de
gasto en una negación de evidencia. La prosa de IA *rodea* al veredicto y el
veredicto no la necesita — el determinista produce el mismo dictamen.

**2. El corte y el aviso dejan UNA fila por periodo, no una por petición**
(regla de oro 10: registro por transición). Se resuelve con un `… WHERE
<marca> IS NULL RETURNING`, que además gana la carrera entre dos exportaciones
simultáneas: solo una de las dos ve el `RETURNING` con fila. El del corte es
además un `INSERT … ON CONFLICT`, por lo de abajo.

**3. El tope se puede rebasar por UNA llamada, y está declarado.** El coste solo
se conoce DESPUÉS de llamar al proveedor, así que la secuencia honesta es leer →
decidir → llamar → sumar. Reservar un coste estimado antes de llamar habría sido
cobrar por lo que no se sabe. El desbordamiento máximo es el coste de una
llamada, acotado a su vez por el techo de tokens que ya existía.

**4. [T-7.26] CERO significa CERO, y «sin tope» hay que pedirlo aparte.** Hasta
esta ficha `cap_usd <= 0` significaba *sin tope* —la lectura conservadora del
ajuste ausente—, y eso convertía el error de dedo más probable de todos en el
peor resultado posible: quien pone el tope a cero creyendo que apaga el gasto lo
dejaba **ilimitado**. De los dos modos de equivocarse, uno deja el sistema SIN IA
—el dictamen sale igual, con prosa determinista y declarándolo— y el otro deja la
tarjeta abierta; el defecto tiene que caer del primer lado. El modo ilimitado
sigue existiendo, pero ahora es EXPLÍCITO: un tope negativo (`SIN_TOPE`), que
nadie teclea por accidente.

⚠️ Y el corte por tope cero **deja constancia como cualquier otro corte**. No la dejaba:
la marca de transición era un `UPDATE` y con tope cero no hay fila que actualizar, así
que el caso nuevo de esta ficha era justo el único que se cortaba en silencio. Ver
`_MARCA_BLOQUEO`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

log = logging.getLogger("takab_api.narrative.quota")

#: Verbos de auditoría. El nombre dice el HECHO, no la intención: «se agotó» y
#: «se acercó», que es lo que alguien busca cuando revisa la factura.
VERB_BLOCKED = "ai_quota_exhausted"
VERB_WARNED = "ai_quota_warning"

#: Motivo que viaja al PDF cuando la cuota corta. Es prosa de cara al lector del
#: dictamen, no un código: quien lo lee no sabe qué es un tenant.
MOTIVO_AGOTADA = "cuota mensual de redacción asistida agotada; texto determinista"

#: [T-7.26] El corte por tope CERO lleva frase propia. Decir «agotada» de un mes en
#: el que no se gastó un centavo sería falso: no se agotó, es que no había. Son dos
#: hechos distintos y quien lea el dictamen tiene que poder distinguirlos — el
#: primero pide subir la cuota, el segundo pide mirar el despliegue.
MOTIVO_TOPE_CERO = "tope mensual de redacción asistida en cero; texto determinista"

#: [T-7.26] El valor que hay que escribir a conciencia para pedir gasto ILIMITADO.
#: Es negativo justamente porque nadie lo teclea sin querer: un `0` olvidado deja el
#: sistema sin IA (que es seguro), no sin tope (que no lo es).
SIN_TOPE = -1.0


def hay_tope(cap_usd: float) -> bool:
    """¿Este ajuste impone un techo? Cualquier valor ≥ 0 lo impone, **cero incluido**."""
    return cap_usd >= 0


def periodo_de(now: datetime) -> str:
    """Mes UTC `YYYY-MM`. La cuota es mensual y el reloj de referencia es UTC."""
    return now.astimezone(UTC).strftime("%Y-%m")


@dataclass(frozen=True)
class EstadoCuota:
    """Lo que se sabe del gasto del tenant en el periodo, antes de llamar."""

    period: str
    spent_usd: float
    calls: int
    cap_usd: float
    #: `True` = ya se gastó el tope: esta llamada NO sale a la red.
    exhausted: bool
    #: `True` = esta lectura es la que CRUZA el tope (la primera). Solo entonces
    #: hay que dejar fila de auditoría.
    just_blocked: bool = False

    @property
    def motivo(self) -> str | None:
        """[T-7.26] Qué imprime el PDF cuando esta lectura corta, o `None` si no corta.

        Vive aquí y no en el llamador porque la distinción —«se agotó» contra «no
        había»— sale de los mismos dos números que este objeto ya tiene, y repetirla
        en cada llamador es cómo una de las dos frases acaba diciéndose mal.
        """
        if not self.exhausted:
            return None
        return MOTIVO_TOPE_CERO if self.cap_usd == 0 else MOTIVO_AGOTADA


_SELECT = text(
    "SELECT spent_usd, calls, warned_at, blocked_at FROM ai_spend "
    "WHERE tenant_id = CAST(:tenant AS uuid) AND period = :period"
)

#: `ON CONFLICT DO UPDATE` y no un `UPDATE` a secas: la primera exportación del
#: mes no tiene fila que actualizar, y dos simultáneas no pueden crear dos.
_ACUMULA = text(
    "INSERT INTO ai_spend (tenant_id, period, spent_usd, calls, updated_at) "
    "VALUES (CAST(:tenant AS uuid), :period, :cost, 1, now()) "
    "ON CONFLICT (tenant_id, period) DO UPDATE "
    "SET spent_usd = ai_spend.spent_usd + EXCLUDED.spent_usd, "
    "    calls = ai_spend.calls + 1, updated_at = now() "
    "RETURNING spent_usd, calls"
)

#: El sello de transición. `WHERE … IS NULL` es lo que garantiza UNA fila de
#: auditoría por periodo aunque lo intenten diez peticiones a la vez.
#:
#: ⚠️ [T-7.26·2ª vuelta] `INSERT … ON CONFLICT`, y no el `UPDATE` a secas que había.
#: **El corte por tope CERO no dejaba constancia NUNCA**, y eso es la mitad del defecto
#: que esta ficha vino a cerrar: con el tope en cero no se gastó un centavo, así que no
#: hay fila de `ai_spend` que actualizar; el `UPDATE` casaba cero filas, `just_blocked`
#: salía `False` y `_auditar` no llegaba a correr. O sea que un despliegue con
#: `TAKAB_API_AI_MONTHLY_CAP_USD=0` —el error de dedo contra el que esta misma ficha
#: protege— apagaba la IA en todos los dictámenes **sin una línea en la bitácora que lo
#: explicara**. Un corte que no deja rastro es un corte que nadie puede explicar después.
#:
#: La fila que se inserta dice la verdad exacta: cero gastado, cero llamadas, bloqueado
#: a esta hora. Y `ON CONFLICT … WHERE blocked_at IS NULL` conserva las dos propiedades
#: que tenía el `UPDATE`: UNA fila de auditoría por periodo (decisión 2) y la carrera
#: ganada por una sola de dos exportaciones simultáneas — el `RETURNING` viene vacío
#: cuando el `WHERE` no casa.
_MARCA_BLOQUEO = text(
    "INSERT INTO ai_spend (tenant_id, period, blocked_at) "
    "VALUES (CAST(:tenant AS uuid), :period, now()) "
    "ON CONFLICT (tenant_id, period) DO UPDATE "
    "SET blocked_at = now(), updated_at = now() "
    "WHERE ai_spend.blocked_at IS NULL "
    "RETURNING spent_usd"
)
_MARCA_AVISO = text(
    "UPDATE ai_spend SET warned_at = now() "
    "WHERE tenant_id = CAST(:tenant AS uuid) AND period = :period AND warned_at IS NULL "
    "RETURNING spent_usd"
)


async def _auditar(
    conn: AsyncConnection, tenant_id: str, *, verb: str, actor: str | None, meta: dict
) -> None:
    """La fila del CRUCE. Vive aquí y no en el router por una razón medida.

    La primera versión auditaba desde el router releyendo el estado — y no
    escribía **nunca**: `leer_estado` CONSUME la transición al sellar
    `blocked_at`, así que la segunda lectura ya la veía consumida. Quien sella el
    hecho es quien tiene que escribirlo.

    `actor is None` = nadie pidió constancia (un llamador sin sesión, un test):
    se sella la transición igual, para que no se audite dos veces más tarde.
    """
    if actor is None:
        return
    from takab_api.audit import audit_async  # noqa: PLC0415 - evita ciclo de imports

    await audit_async(
        conn,
        tenant_id=tenant_id,
        actor=actor,
        verb=verb,
        obj=f"ai_spend:{meta['period']}",
        meta=meta,
    )


async def leer_estado(
    conn: AsyncConnection,
    tenant_id: str,
    *,
    cap_usd: float,
    now: datetime | None = None,
    actor: str | None = None,
) -> EstadoCuota:
    """Gasto acumulado del periodo y si esta llamada puede salir a la red.

    [T-7.26] **`cap_usd = 0` es tope CERO: la llamada NO sale.** Solo un tope
    negativo (`SIN_TOPE`) significa gasto ilimitado, y hay que escribirlo a
    conciencia — ver la decisión 4 en la cabecera del módulo.
    """
    period = periodo_de(now or datetime.now(tz=UTC))
    fila = (await conn.execute(_SELECT, {"tenant": tenant_id, "period": period})).mappings().first()
    gastado = float(fila["spent_usd"]) if fila else 0.0
    llamadas = int(fila["calls"]) if fila else 0

    if not hay_tope(cap_usd):
        return EstadoCuota(period, gastado, llamadas, cap_usd, exhausted=False)

    agotada = gastado >= cap_usd
    if not agotada:
        return EstadoCuota(period, gastado, llamadas, cap_usd, exhausted=False)

    # Agotada: ¿es ESTA la petición que cruza el tope? Solo entonces se audita.
    recien = (
        await conn.execute(_MARCA_BLOQUEO, {"tenant": tenant_id, "period": period})
    ).first() is not None
    if recien:
        await _auditar(
            conn,
            tenant_id,
            verb=VERB_BLOCKED,
            actor=actor,
            meta={
                "period": period,
                "spent_usd": gastado,
                "cap_usd": cap_usd,
                "calls": llamadas,
            },
        )
    return EstadoCuota(period, gastado, llamadas, cap_usd, exhausted=True, just_blocked=recien)


async def acumular(
    conn: AsyncConnection,
    tenant_id: str,
    *,
    cost_usd: float | None,
    cap_usd: float,
    warn_at: float,
    now: datetime | None = None,
    actor: str | None = None,
) -> tuple[float, bool]:
    """Suma el coste de una llamada. Devuelve `(gastado, hay_que_avisar)`.

    `cost_usd is None` **también cuenta como llamada** con coste cero: el
    proveedor puede no devolver el coste, y descartar la fila entera dejaría el
    contador de llamadas mintiendo sobre cuántas veces se salió a la red.
    """
    period = periodo_de(now or datetime.now(tz=UTC))
    fila = (
        (
            await conn.execute(
                _ACUMULA, {"tenant": tenant_id, "period": period, "cost": float(cost_usd or 0.0)}
            )
        )
        .mappings()
        .one()
    )
    gastado = float(fila["spent_usd"])

    # Sin tope no hay fracción del tope que avisar; y con el tope en CERO la llamada
    # ya venía cortada, así que un «te acercas al 80 %» sobraría. Los dos casos salen
    # por la misma puerta y por razones distintas: por eso está escrito.
    if cap_usd <= 0 or not 0 < warn_at < 1:
        return gastado, False
    if gastado < cap_usd * warn_at:
        return gastado, False
    # Igual que el corte: UNA fila por periodo, la del cruce.
    avisar = (
        await conn.execute(_MARCA_AVISO, {"tenant": tenant_id, "period": period})
    ).first() is not None
    if avisar:
        await _auditar(
            conn,
            tenant_id,
            verb=VERB_WARNED,
            actor=actor,
            meta={"period": period, "spent_usd": gastado, "cap_usd": cap_usd, "warn_at": warn_at},
        )
    return gastado, avisar
