"""Fallo TRANSITORIO de base en los workers de cola — la política, UNA sola.

`T-2.132` construyó esta distinción dentro de ``ingest/consumer.py`` porque
había un solo worker que la necesitaba. `T-2.139` trajo el segundo (``backfill``,
que también consume SQS) y con él la pregunta de siempre: copiarla o compartirla.
**Se comparte**, por lo mismo que los topes de `db/session.py` no se escriben en
`db/pool.py`: dos censos de SQLSTATE que creen ser uno derivan en silencio, y el
día que diverjan un worker reintentará lo que el otro manda a la DLQ.

Lo que la política dice, en una frase: **«la base estaba ocupada» no es «el
mensaje está roto»**. Devolver un mensaje a la cola **quema una recepción del
``maxReceiveCount``**, así que cinco bloqueos pasajeros mandan a la DLQ un
mensaje perfectamente válido. La palanca que lo evita es que **SQS solo
incrementa ``ApproximateReceiveCount`` al RECIBIR**: todos los reintentos caben
dentro de la recepción ya gastada, siempre que se sostenga la invisibilidad con
``ChangeMessageVisibility`` mientras duran.

Lo que NO es compartido, y por eso viaja en ``TransientPolicy`` y no aquí: el
**presupuesto**. Su techo es el ``VisibilityTimeout`` de *cada* cola, y en
`backfill` hay un segundo término que en `ingest` no existe — rehacer cuesta una
**pasada entera** (`T-2.139` la midió). Cada worker declara el suyo y un test lo
encajona contra el Terraform real.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger("takab_api.db.transient")

#: [T-2.132] SQLSTATE que significan «la base estaba OCUPADA», no «esto está
#: roto». Los tres comparten lo único que importa para decidir: dejan la conexión
#: VIVA con la transacción abortada, y **el mismo mensaje volvería a entrar** si
#: se reintenta. Nada más entra aquí — una conexión caída (57P01) o un dato malo
#: (23505) no se arreglan reintentando y deben gastar sus recepciones e irse a la
#: DLQ, que es para lo que existe.
#:
#: El 55P03 es el MISMO que dispara el ``lock_timeout`` de ``db/session.py``; lo
#: ancla un test, no este comentario.
#:
#: **``57014`` se queda fuera a propósito** y esa ausencia es estructural, no un
#: olvido: una consulta cancelada por ``statement_timeout`` no es «la base
#: ocupada», y reintentarla re-corre el mismo coste. Es también lo que hace que
#: poner un tope de sentencia a un worker sea una decisión con precio — ver
#: `WORKER_STATEMENT_TIMEOUT_MS` y el veredicto medido de `T-2.139`.
TRANSIENT_SQLSTATES = frozenset(
    {
        "55P03",  # lock_not_available — venció el tope de espera por lock
        "40P01",  # deadlock_detected — Postgres eligió a esta víctima
        "40001",  # serialization_failure — dos transacciones se pisaron
    }
)


def sqlstate_de(exc: BaseException) -> str | None:
    """SQLSTATE del error, venga crudo de psycopg o envuelto por SQLAlchemy."""
    estado = getattr(exc, "sqlstate", None)
    if estado is None:
        estado = getattr(getattr(exc, "orig", None), "sqlstate", None)
    return estado


def es_transitorio(exc: BaseException) -> bool:
    """True si el fallo es «la base está ocupada» y el mensaje sigue siendo bueno.

    Esta función ES la distinción que pedía `T-2.132`. Todo lo que devuelva False
    conserva el camino de siempre: RETRY, reentrega, y DLQ a la quinta.
    """
    return sqlstate_de(exc) in TRANSIENT_SQLSTATES


@dataclass(frozen=True, slots=True)
class TransientPolicy:
    """Presupuesto del reintento EN EL SITIO ante un fallo transitorio.

    ``budget_s`` es el techo de verdad, y no es arbitrario: tiene que caber en el
    ``VisibilityTimeout`` de la cola del worker que la use. Si los reintentos
    duraran más, el mensaje se haría visible a mitad, otro worker lo tomaría y se
    gastaría **justo la recepción que estábamos ahorrando** — además de duplicar
    el trabajo. Lo ancla un test que lee el número del Terraform real.

    ``inflight_visibility_s`` es el alargue que se pide antes de cada reintento:
    cubre el presupuesto entero, así que el mensaje no se escapa aunque los
    reintentos lleguen al final. ``giveup_visibility_s`` es distinto y sirve a
    otra cosa: cuando el bloqueo NO cede, el mensaje vuelve a la cola con un
    respiro para que las cinco recepciones se repartan en minutos en vez de
    quemarse en cinco segundos contra una tabla que sigue bloqueada.

    Los defectos son los de `ingest` (`T-2.132`, cola ``q-events``, 30 s de
    visibilidad). Un worker con otra cola declara los suyos — ver
    ``backfill.consumer.BACKFILL_TRANSIENT_POLICY``.
    """

    budget_s: float = 20.0
    base_delay_s: float = 0.1
    max_delay_s: float = 2.0
    inflight_visibility_s: int = 60
    giveup_visibility_s: int = 60


class TransitorioAgotado(Exception):
    """El bloqueo no cedió dentro del presupuesto: ya no es transitorio.

    Excepción propia y no un ``OperationalError`` más: el desenlace no es el
    mismo. Aquí se sabe que el mensaje es bueno y que la conexión está sana, así
    que **no se tira la conexión** (el camino operacional sí lo hace, y con
    razón) y lo pendiente se devuelve con respiro en vez de a martillazos.
    """

    def __init__(self, intentos: int, esperado_s: float, causa: BaseException) -> None:
        super().__init__(
            f"la base siguió ocupada tras {intentos} intentos en {esperado_s:.1f} s: {causa}"
        )
        self.intentos = intentos


def _nada() -> None:
    """Gancho vacío: el worker que no tiene pendientes que rehacer no pasa nada."""


def reintentar_en_el_sitio[T](
    accion: Callable[[], T],
    *,
    policy: TransientPolicy,
    rollback: Callable[[], None],
    prolongar: Callable[[int], None],
    rehacer: Callable[[], None] = _nada,
    anotar: Callable[[], None] = _nada,
) -> T:
    """Ejecuta ``accion`` reintentando EN EL SITIO mientras la base esté ocupada.

    La clave está en lo que NO se hace: **no se devuelve el mensaje a la cola**.
    SQS solo incrementa ``ApproximateReceiveCount`` al recibir, así que todos
    estos intentos caben dentro de la ÚNICA recepción ya gastada y el
    ``maxReceiveCount`` no se mueve. Lo que sí hay que hacer es sostener la
    invisibilidad mientras tanto (``prolongar`` → ``ChangeMessageVisibility``), o
    el mensaje se escaparía por el otro lado y otro worker gastaría justo la
    recepción que estábamos ahorrando.

    Los tres ganchos son los tres detalles que no se ven y rompen si faltan:

    · ``rollback`` **antes** de reintentar. Tras un 55P03 la transacción queda
      ABORTADA y Postgres rechaza toda sentencia posterior: sin esto, el
      siguiente intento fallaría por «current transaction is aborted» y el
      reintento no serviría de nada.
    · ``rehacer``, el trabajo que se llevó por delante ese rollback y que la
      ``accion`` no repite por sí sola (los ``pending`` del modo batch de
      ingesta). Es seguro y barato por idempotencia de PK (regla de oro 3), y es
      lo único que evita que un bloqueo a mitad de batch queme una recepción por
      CADA mensaje del batch. Los workers cuya ``accion`` ya rehace la pasada
      entera —``backfill``— no lo necesitan.
    · ``anotar``, para que el reintento sea visible en las métricas del ciclo:
      esperar cuesta LATENCIA, y eso se mira; abortar en bucle cuesta DATOS.
    """
    limite = time.monotonic() + policy.budget_s
    intentos = 0
    while True:
        try:
            if intentos:
                rehacer()
            return accion()
        except Exception as exc:
            if not es_transitorio(exc):
                raise
            intentos += 1
            rollback()
            restante = limite - time.monotonic()
            if restante <= 0:
                raise TransitorioAgotado(intentos, policy.budget_s, exc) from exc
            anotar()
            prolongar(policy.inflight_visibility_s)
            espera = min(
                policy.base_delay_s * 2 ** (intentos - 1),
                policy.max_delay_s,
                restante,
            )
            log.warning(
                "base ocupada (%s); reintento %d en el sitio en %.2fs (0 recepciones)",
                sqlstate_de(exc),
                intentos,
                espera,
            )
            time.sleep(espera)
