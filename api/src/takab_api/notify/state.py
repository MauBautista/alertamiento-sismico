"""El estado del subsistema que NO puede vivir en la memoria de un worker (T-2.77.c).

Dos memorias del subsistema de notificación eran estado EN PROCESO, y las dos
consecuencias están medidas, no supuestas:

1. **Al reiniciar el worker se olvidaba la cuarentena** de una plantilla que Meta
   había pausado, y se volvía a martillear — que es exactamente lo que degrada su
   calificación de calidad y termina costando el canal entero. La degradación en
   caliente de T-2.77 funcionaba; lo que no sobrevivía era el recuerdo de haberla
   sufrido.
2. **Con más de una instancia la guarda de duplicados no existía entre
   instancias**, así que un SMS duplicado durante un sismo seguía siendo posible.
   Y el supuesto de "un solo worker" que la sostenía ya estaba contradicho por el
   código de al lado: el orquestador usa ``pg_advisory_xact_lock`` justamente
   porque asume varias.

Aquí vive el reemplazo: la misma base de datos que ya serializa las pasadas.

──────────────────────────────────────────────────────────────────────────────
POR QUÉ LA GUARDA ES UNA COLUMNA DEL JOB Y NO UNA TABLA NUEVA
──────────────────────────────────────────────────────────────────────────────
La clave del dominio era ``(destino, incidente)``. Para los dos canales con
guarda —sms y whatsapp— eso es EXACTAMENTE una fila de ``notification_jobs``:
``plan_jobs`` emite un solo job por canal e incidente (el único canal que recibe
dos, ``email``, no tiene guarda). Así que la guarda es un atributo del job,
``inflight_until``, y hereda gratis ``tenant_id``, RLS y retención — y no añade
una fila con un teléfono dentro que alguien tenga que borrar el día de un ARCO.

El ``key`` que pasa el provider se ignora **a propósito**: es el mismo hecho,
expresado dos veces. Se acepta en la firma para no obligar al provider a saber
dónde vive su guarda, que es lo que permitió que ni ``twilio.py`` ni
``whatsapp.py`` cambien su lógica de decidir CUÁNDO recordar.

──────────────────────────────────────────────────────────────────────────────
POR QUÉ SE ESCRIBE EN LA TRANSACCIÓN DE LA PASADA, Y QUÉ CUESTA
──────────────────────────────────────────────────────────────────────────────
El recuerdo se escribe con la MISMA conexión del pase, luego commitea con él.
La alternativa —una conexión aparte con autocommit— parecía más segura y es
peor: dejaría el recuerdo puesto con el desenlace del job revertido, o sea un
canal mudo hasta que venciera el TTL, sin que nada lo dijera. Así los dos hechos
—"pudo salir un mensaje" y "esto es lo que le pasó al job"— viven o mueren
juntos.

Lo que queda fuera, dicho en voz alta: si el proceso muere ENTRE el envío y el
commit, el recuerdo se pierde. Es exactamente lo que pasaba antes (la memoria
moría con el proceso), así que esto no empeora nada; y lo que sí arregla —el
reinicio y la segunda instancia— es lo que la ficha midió.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import psycopg

logger = logging.getLogger("takab_api.notify")

_SEEN_SQL = """
SELECT inflight_until FROM notification_jobs
WHERE job_id = %(job)s AND inflight_until IS NOT NULL AND inflight_until > %(now)s
"""

_REMEMBER_SQL = """
UPDATE notification_jobs SET inflight_until = GREATEST(coalesce(inflight_until, %(until)s),
                                                       %(until)s)
WHERE job_id = %(job)s
"""

_QUARANTINE_READ_SQL = """
SELECT template_name, reason FROM notify_template_quarantine WHERE channel = %(channel)s
"""

# La PRIMERA razón manda: es la que describe por qué se cayó el canal. Un
# reintento posterior contra la misma plantilla no reescribe la historia, solo
# confirma que sigue muerta.
_QUARANTINE_WRITE_SQL = """
INSERT INTO notify_template_quarantine (channel, template_name, reason)
VALUES (%(channel)s, %(name)s, %(reason)s)
ON CONFLICT (channel, template_name) DO NOTHING
"""


class PgNotifyState:
    """Cuarentena persistente + guarda de duplicados compartida, sobre la pasada.

    Se construye una por pasada del orquestador y se le entrega a los providers
    con ``providers.bind_state``. Fuera del worker —por ejemplo en la API, que
    construye el registro solo para saber qué canal es real— no hay estado
    ligado y los providers se comportan como siempre, con su memoria de proceso.
    """

    def __init__(self, conn: psycopg.Connection, *, now: datetime | None = None) -> None:
        self._conn = conn
        self._now = now or datetime.now(tz=UTC)
        self._job_id: object | None = None
        # Cache POR PASADA: la cuarentena se consulta en cada `simulated` y en
        # cada `get()`, y dentro de una pasada no puede cambiar por debajo (la
        # que ponemos nosotros se ve por la memoria local del catálogo, que se
        # fusiona encima). Sin esto habría una consulta por job y por pregunta.
        self._quarantine: dict[str, dict[str, str]] = {}

    # -- la guarda de duplicados ---------------------------------------------

    def enter_job(self, job_id: object) -> None:
        """Job cuyo despacho empieza AHORA: es él quien tiene guarda.

        Lo llama el orquestador antes de cada envío. El worker es de un solo
        hilo (bucle LISTEN + pasada secuencial), así que "el job en curso" es un
        concepto bien definido; si algún día dejara de serlo, esto tendría que
        viajar en el argumento del provider y no en el estado.
        """
        self._job_id = job_id

    def seen(self, key: tuple[str, str]) -> bool:
        """¿Este job pudo dejar un mensaje VIVO que no ha caducado todavía?"""
        del key  # el job ES la clave (destino, incidente); ver el docstring
        if self._job_id is None:
            return False
        return (
            self._conn.execute(_SEEN_SQL, {"job": self._job_id, "now": self._now}).fetchone()
            is not None
        )

    def remember(self, key: tuple[str, str], ttl_s: float) -> None:
        """Marca que este job puede tener un mensaje vivo durante ``ttl_s``."""
        del key
        if self._job_id is None:
            return
        until = self._now + timedelta(seconds=float(ttl_s))
        self._conn.execute(_REMEMBER_SQL, {"job": self._job_id, "until": until})

    # -- la cuarentena --------------------------------------------------------

    def quarantined(self, channel: str) -> Mapping[str, str]:
        """``{nombre: razón}`` de lo que este despliegue tiene en cuarentena."""
        if channel not in self._quarantine:
            rows = self._conn.execute(_QUARANTINE_READ_SQL, {"channel": channel}).fetchall()
            self._quarantine[channel] = {_col(r, 0): _col(r, 1) for r in rows}
        return self._quarantine[channel]

    def quarantine(self, channel: str, name: str, reason: str) -> None:
        """Deja escrito que con esa plantilla no se puede hablar. Sobrevive al
        reinicio: levantarla es un acto humano, no el efecto de un `restart`."""
        self._conn.execute(
            _QUARANTINE_WRITE_SQL, {"channel": channel, "name": name, "reason": reason[:500]}
        )
        self._quarantine.pop(channel, None)
        logger.error(
            "notify[%s]: %s queda en cuarentena PERSISTIDA (%s). Un reinicio ya no la "
            "levanta: hay que volver a someterla y borrar la fila.",
            channel,
            name,
            reason,
        )


def _col(row: object, index: int) -> str:
    """Una fila de psycopg, venga como tupla o como ``dict_row``.

    El worker abre su conexión sin ``row_factory`` y varios tests la abren con
    ``dict_row``; leer por posición reventaría en unos y por nombre en los
    otros. Se resuelve aquí, una vez, en vez de imponerle una fábrica de filas a
    quien nos presta la conexión.
    """
    if isinstance(row, dict):
        return str(list(row.values())[index])
    return str(row[index])  # type: ignore[index]
