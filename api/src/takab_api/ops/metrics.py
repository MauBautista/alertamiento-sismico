"""T-2.60.a · Métrica del gabinete retirado que sigue latiendo.

La consola ya delata la contradicción en pantalla (PR #51), pero eso solo sirve
si hay alguien mirando. El fallo del 2026-08-04 duró horas precisamente porque
nadie miraba: se supo cuando el operador preguntó por su estación.

Esto es la mitad que no depende de que haya un humano delante. Emite a
CloudWatch, cada minuto, cuántos gabinetes están dados de baja **y aun así
reportando**. La alarma vive en Terraform
(``infra/terraform/modules/observability``).

Tres decisiones que este archivo defiende:

1. **Se publica SIEMPRE, también el cero.** Es la lección cara de la alarma de
   gabinete mudo: si la métrica solo existe cuando hay algo que contar, la alarma
   pasa la vida en ``INSUFFICIENT_DATA`` y todo queda en manos de
   ``treat_missing_data`` — que ya nos falló de cuatro maneras distintas. Con un 0
   cada minuto, "sin datos" significa UNA sola cosa: el worker está caído. Que es
   otro problema, y ya tiene su propia vigilancia.

2. **Nunca puede tumbar al worker que la hospeda.** ``notify`` existe para avisar
   de incidentes sísmicos. Una métrica de inventario que reventara su bucle
   cambiaría un problema administrativo por uno de alertamiento. Todo va envuelto,
   y un fallo se REGISTRA — tragárselo en silencio sería peor que el fallo, porque
   la alarma parecería sana sin estarlo.

3. **Estrangulada.** El bucle de ``notify`` despierta cada 2 s; publicar ahí serían
   ~43 000 llamadas diarias por una cifra que CloudWatch agrega por minuto.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

logger = logging.getLogger("takab_api.ops")

#: Nombre en CloudWatch. Se lee en la alarma de Terraform: si cambia aquí, cambia allí.
METRIC_NAME = "GhostGatewaysAlive"

# Un gabinete cuenta como fantasma cuando él —o su sitio— está retirado y su
# último heartbeat sigue siendo fresco. La frontera de "fresco" es la MISMA que
# separa `SIN ENLACE` en la consola (`sin_enlace_min`), y llega por parámetro para
# que no nazca aquí una segunda definición de "vivo" que pueda divergir.
#
# Sin filtro de tenant a propósito: el worker conecta como `takab_ingest`
# (BYPASSRLS) y esta es una señal de plataforma, no de cliente. La cifra por
# tenant ya la da la consola.
#
# El alias `AS ghosts` NO es cosmético: la fila se lee por NOMBRE porque la
# conexión real del worker viene de `db/pool.py::connect`, que la abre con
# `row_factory=dict_row`. Ver la trampa completa en `count_ghosts`.
_COUNT_SQL = """
    SELECT count(*) AS ghosts
    FROM gateways g
    JOIN sites s ON s.site_id = g.site_id
    LEFT JOIN LATERAL (
        SELECT max(dh.ts) AS ts
        FROM device_health dh
        WHERE dh.gateway_id = g.gateway_id
    ) h ON true
    WHERE (g.status = 'retired' OR s.status = 'retired')
      AND h.ts > now() - make_interval(secs => %(alive_s)s)
"""


class _MetricClient(Protocol):
    """Lo único que se le pide a boto3; así el test no necesita AWS."""

    def put_metric_data(self, **kwargs: Any) -> Any: ...


def count_ghosts(conn: Any, *, alive_s: float) -> int:
    """Gabinetes retirados cuyo último latido sigue siendo fresco.

    La fila se lee por NOMBRE, nunca por posición. La conexión que llega aquí en
    producción sale de ``db/pool.py::connect`` —``row_factory=dict_row``— y viaja
    intacta hasta el bucle (``notify/__main__.py`` arma el ``conn_factory`` →
    ``worker.py`` saca de él la ``work_conn`` y se la pasa a ``maybe_publish``):
    nadie cambia el ``row_factory`` por el camino. Con ``row[0]`` esto lanzaba
    ``KeyError: 0`` en CADA llamada; el ``except`` de ``maybe_publish`` lo
    registraba y retornaba antes del ``put_metric_data``, así que la métrica no
    se publicó nunca —ni el cero— y la alarma de Terraform no podía sonar.
    Detectado por auditoría el 2026-08-05; los tests de entonces inyectaban el
    contador y jamás ejecutaban esta función.
    """
    row = conn.execute(_COUNT_SQL, {"alive_s": alive_s}).fetchone()
    return int(row["ghosts"]) if row else 0


class GhostGauge:
    """Publica ``GhostGatewaysAlive`` cada ``every_s``, sin propagar fallos.

    ``client=None`` la deja inerte: en local no hay CloudWatch y el worker tiene
    que correr igual, sin ruido y sin excepciones.
    """

    def __init__(
        self,
        *,
        namespace: str,
        every_s: float,
        client: _MetricClient | None,
        counter: Callable[[Any], int],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._namespace = namespace
        self._every_s = every_s
        self._client = client
        self._counter = counter
        self._clock = clock
        self._last: float | None = None

    def maybe_publish(self, *, conn: Any) -> None:
        """Publica si toca. No lanza NUNCA: la llama el bucle de un worker."""
        if self._client is None:
            return
        now = self._clock()
        if self._last is not None and now - self._last < self._every_s:
            return
        # El sello se pone ANTES de trabajar: si CloudWatch o la DB fallan, el
        # siguiente intento espera su turno igual que si hubiera ido bien. Sin
        # esto, un fallo persistente convertiría el estrangulador en un bucle de
        # reintentos a 2 s contra un servicio que ya está mal.
        self._last = now
        try:
            valor = self._counter(conn)
        except Exception:
            logger.warning("no se pudo contar los gabinetes fantasma", exc_info=True)
            return
        try:
            self._client.put_metric_data(
                Namespace=self._namespace,
                MetricData=[{"MetricName": METRIC_NAME, "Value": valor, "Unit": "Count"}],
            )
        except Exception:
            # Se registra a propósito: un fallo mudo aquí deja la alarma con cara
            # de sana mientras deja de recibir datos.
            logger.warning("no se pudo publicar la métrica de gabinetes fantasma", exc_info=True)
            return
        if valor:
            logger.warning(
                "%s gabinete(s) RETIRADO(S) siguen reportando: hay que decidir "
                "si se restauran o se desmonta el hardware",
                valor,
            )
