"""T-2.60.a · Métricas de operación que no dependen de que alguien mire.

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

4. **Son DOS cifras, no una** (B3, 2026-08-06). ``GhostGatewaysAlive`` pagina y
   cuenta solo el fantasma del que NO consta que se haya enterado de su baja;
   ``RetiredGatewaysAlive`` no pagina y cuenta todos los retirados que laten. Con
   una sola había que elegir entre una alarma encendida para siempre —bajo la
   opción (A) el retirado avisado sigue protegiendo a propósito— y un punto ciego
   permanente. Y "enterarse" NO puede leerse de ``gateway_config_state``, que
   registra lo que la nube publicó: ver ``_UNREACHED``, donde está escrito qué se
   aproxima, qué se pierde y cuál es el arreglo de raíz.

5. **Y desde T-5.24, TRES** (``MaxClockDriftMs``). No es un gabinete, es la HORA:
   el sello de un check-in, de un dictamen y de un acuse salen todos del reloj del
   Pi, y sin hora confiable ninguna evidencia sirve. El desfase se medía, viajaba y
   se persistía desde siempre — y aun así solo se veía si alguien tenía la pantalla
   delante: ninguna de las 13 alarmas de la nube era de reloj.

   Viaja en la MISMA ``put_metric_data`` que las otras dos, y eso decide el
   ``treat_missing_data`` de su alarma: las tres se quedan sin datos a la vez y por
   la misma causa, así que su silencio significa lo mismo. El razonamiento entero
   está en ``tests/treat_missing_data.tftest.hcl``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

logger = logging.getLogger("takab_api.ops")

#: Nombre en CloudWatch. Se lee en la alarma de Terraform: si cambia aquí, cambia allí.
#: [B3] Cuenta el fantasma URGENTE: el que late y del que NO consta que se haya
#: enterado de su baja. Ver `_UNREACHED` para qué es "constar".
METRIC_NAME = "GhostGatewaysAlive"

#: [B3] La cifra INFORMATIVA: todo retirado que late, se le haya avisado o no.
#: Es la que empata palabra por palabra con el `is_ghost` de la consola. No lleva
#: alarma a propósito (ver la nota de las DOS condiciones, más abajo).
METRIC_NAME_RETIRED_ALIVE = "RetiredGatewaysAlive"

#: [T-5.24] Desfase de reloj máximo, en ms y en valor absoluto, sobre los
#: gabinetes con latido vivo. **Sin hora confiable ninguna evidencia sirve**: el
#: sello de un check-in, de un dictamen y de un acuse salen todos de ese reloj, y
#: hasta ahora el desfase solo se veía si alguien estaba mirando una pantalla.
#:
#: Se publica el CERO cuando nadie va a la deriva —y también cuando no hay
#: gabinetes vivos—, para que la métrica exista siempre que el publicador viva.
#: Es lo que permite que su ALARMA vigile las dos cosas: el valor **y la
#: ausencia**, que aquí significa «el worker que la publica se murió» — un fallo
#: que `gateway_offline` NO ve, porque los gabinetes siguen latiendo contra otro
#: worker mientras éste está muerto.
METRIC_NAME_CLOCK_DRIFT = "MaxClockDriftMs"

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
#
# [T-2.65] …y que TODAVÍA NO LO SABE. Desde la opción (A) (ratificada 2026-08-05)
# un gabinete retirado SIGUE PROTEGIENDO a propósito, así que "retirado + latiendo"
# es un estado legítimo y PERMANENTE: contarlo dejaría esta alarma encendida para
# siempre, y una alarma que siempre suena deja de leerse (el mismo criterio que ya
# excluye al retirado mudo en T-2.35). Lo que queda vigilado es el fantasma
# INVISIBLE: el que late sin que nadie le haya entregado su sobre de baja — que es
# exactamente el estado de `gw-dev-0001` el 2026-08-04, detectado porque un
# operador preguntó por su estación y no porque el sistema lo dijera.
#
# [B3 · 2026-08-06] Esa acotación se apoyaba en la SOLA existencia del doc firmado
# en `gateway_config_state`, y esa tabla registra lo que la nube PUBLICÓ, no lo que
# el gabinete APLICÓ. Hoy no hay forma de saber lo segundo:
#
#   · no existe ack de config (los COMANDOS sí lo tienen; la config no),
#   · el sobre se publica SIN `retain`, así que a un gabinete ausente se le
#     descarta en el instante y no queda nada que entregar cuando vuelva,
#   · el latido NO carga la versión de config aplicada (`config_version` solo
#     existe en el panel LAN del propio Pi).
#
# Con "publicado ⇒ avisado" bastaba retirar un gabinete apagado para que el
# publish "tuviera éxito", el mensaje se perdiera y la alarma quedara callada PARA
# SIEMPRE sobre el mismo estado que existe para delatar. Se cambia por lo único
# que sí se puede afirmar sin tocar el contrato edge→nube:
_UNREACHED = """
      AND ( st.payload->>'cloud_admin_state' IS DISTINCT FROM 'retired'
            OR NOT EXISTS (
                SELECT 1 FROM device_health dh
                WHERE dh.gateway_id = g.gateway_id
                  AND dh.ts <= st.published_at
                  AND dh.ts > st.published_at - make_interval(secs => %(alive_s)s)
            ) )
"""
# …es decir: la baja se le publicó Y el gabinete estaba VIVO justo antes de ese
# instante (misma frontera `alive_s` de siempre, aplicada al momento del publish en
# vez de a ahora). La ventana mira hacia ATRÁS a propósito: conectarse después no
# rescata un mensaje ya descartado.
#
# LO QUE ESTA APROXIMACIÓN NO CUBRE, escrito para que nadie lo descubra en campo:
# el gabinete estaba conectado, el sobre salió, y aun así no se aplicó —sesión MQTT
# reciclada entre el ack del broker y la entrega, firma rechazada, el edge cayó
# procesándolo—. Ese residuo lo cierra el arreglo de raíz, que es que el LATIDO
# cargue la versión/huella de la config aplicada y la alarma se silencie con la
# RECEPCIÓN confirmada. Exige cambiar el contrato del edge (aditivo) y no cabía en
# este lote. Mientras tanto la contradicción no desaparece de ningún sitio: la
# cuenta total (`METRIC_NAME_RETIRED_ALIVE`) y el `is_ghost` de la consola la
# siguen mostrando; lo que se acota es a quién se despierta de madrugada.
#
# Y hay un segundo agujero, en `commands/sync.py` y por tanto fuera de este lote:
# una vez persistido el doc 'retired', el gabinete deja de ser candidato para
# siempre, así que el sobre perdido NUNCA se reintenta. Por eso esta alarma vuelve
# a encenderse cuando el fantasma resucita: no hay nadie más que lo note.
_COUNT_BASE = """
    SELECT count(*) AS ghosts
    FROM gateways g
    JOIN sites s ON s.site_id = g.site_id
    LEFT JOIN LATERAL (
        SELECT max(dh.ts) AS ts
        FROM device_health dh
        WHERE dh.gateway_id = g.gateway_id
    ) h ON true
    LEFT JOIN gateway_config_state st ON st.gateway_id = g.gateway_id
    WHERE (g.status = 'retired' OR s.status = 'retired')
      AND h.ts > now() - make_interval(secs => %(alive_s)s)
    {acotacion}
"""

# DOS CONDICIONES, DOS DESTINOS — y esto es el corazón del arreglo, no un detalle
# de despliegue. «Retirado y todavía sin avisar» es urgente y pagina: hay un
# edificio cuya supervisión nadie mira y que ni siquiera lo declara en su panel.
# «Retirado, avisado y protegiendo a propósito» es la opción (A) funcionando, pero
# NO es un estado en el que se pueda dejar la instalación: o se desmonta el
# hardware, o se restaura el gabinete (criterio 3 de T-2.60.a). Eso exige acción
# humana sin urgencia horaria, así que su destino es la cifra informativa + el
# `is_ghost` de la consola, no el correo de guardia. Fundir las dos en una sola
# métrica obliga a elegir entre una alarma encendida para siempre y un punto ciego
# permanente; las dos opciones ya nos costaron un incidente cada una.
_COUNT_SQL = _COUNT_BASE.format(acotacion=_UNREACHED)
_COUNT_RETIRED_ALIVE_SQL = _COUNT_BASE.format(acotacion="")


class _MetricClient(Protocol):
    """Lo único que se le pide a boto3; así el test no necesita AWS."""

    def put_metric_data(self, **kwargs: Any) -> Any: ...


def _count(conn: Any, sql: str, alive_s: float) -> int:
    """Ejecuta una de las dos cuentas y lee la fila POR NOMBRE, nunca por posición.

    La conexión que llega aquí en producción sale de ``db/pool.py::connect``
    —``row_factory=dict_row``— y viaja intacta hasta el bucle
    (``notify/__main__.py`` arma el ``conn_factory`` → ``worker.py`` saca de él la
    ``work_conn`` y se la pasa a ``maybe_publish``): nadie cambia el
    ``row_factory`` por el camino. Con ``row[0]`` esto lanzaba ``KeyError: 0`` en
    CADA llamada; el ``except`` de ``maybe_publish`` lo registraba y retornaba
    antes del ``put_metric_data``, así que la métrica no se publicó nunca —ni el
    cero— y la alarma de Terraform no podía sonar. Detectado por auditoría el
    2026-08-05; los tests de entonces inyectaban el contador y jamás ejecutaban
    esta función.
    """
    row = conn.execute(sql, {"alive_s": alive_s}).fetchone()
    return int(row["ghosts"]) if row else 0


def count_ghosts(conn: Any, *, alive_s: float) -> int:
    """Retirados que siguen latiendo y de los que NO CONSTA que lo sepan (B3).

    La cifra urgente: la que pagina. "No consta" = o no se le publicó la baja, o
    se le publicó cuando llevaba más de ``alive_s`` sin dar señales de vida — y
    entonces el sobre, que va sin ``retain``, se descartó sin que nadie lo note.
    """
    return _count(conn, _COUNT_SQL, alive_s)


#: `abs()` porque un reloj ADELANTADO miente igual que uno atrasado, y el
#: `MAX(...)` sobre el último latido de cada gabinete vivo: la alarma tiene que
#: sonar por el peor de la flota, no por su promedio — un gabinete a la deriva
#: entre veinte sanos desaparece de una media.
_MAX_DRIFT_SQL = """
SELECT COALESCE(MAX(ABS(h.ntp_offset_ms)), 0)::float8 AS drift_ms
FROM gateways g
JOIN LATERAL (
    SELECT dh.ntp_offset_ms, dh.ts
    FROM device_health dh
    WHERE dh.gateway_id = g.gateway_id
    ORDER BY dh.ts DESC
    LIMIT 1
) h ON true
WHERE g.status <> 'retired'
  AND h.ts > now() - make_interval(secs => %(alive_s)s)
  AND h.ntp_offset_ms IS NOT NULL
"""


def max_clock_drift_ms(conn: Any, *, alive_s: float) -> float:
    """Desfase absoluto del PEOR gabinete vivo, en ms. `0.0` si nadie va a la deriva.

    Un gabinete sin dato de reloj (`ntp_offset_ms IS NULL`) **no cuenta como
    cero**: se excluye. No saber la hora no es tenerla bien — de esa ausencia
    habla el `S/D` del panel, no esta métrica.
    """
    row = conn.execute(_MAX_DRIFT_SQL, {"alive_s": alive_s}).fetchone()
    return float(row["drift_ms"]) if row else 0.0


def count_retired_alive(conn: Any, *, alive_s: float) -> int:
    """TODOS los retirados que siguen latiendo, avisados o no (B3).

    La cifra informativa, y la única que dice el mismo número que el ``is_ghost``
    de la consola. Existe para que acotar la alarma no equivalga a borrar el
    estado: un gabinete dado de baja y enchufado sigue exigiendo una decisión
    —desmontarlo de verdad o restaurarlo— aunque ya se haya enterado de su baja.
    """
    return _count(conn, _COUNT_RETIRED_ALIVE_SQL, alive_s)


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
        total_counter: Callable[[Any], int] | None = None,
        drift_gauge: Callable[[Any], float] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._namespace = namespace
        self._every_s = every_s
        self._client = client
        self._counter = counter
        self._total_counter = total_counter
        self._drift_gauge = drift_gauge
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
            # Las dos cifras son la MISMA fotografía: si una falla no sale
            # ninguna. Publicar "0 urgentes" junto a un hueco donde va el total se
            # lee como flota sana, que es justo la mentira que esta métrica existe
            # para no contar.
            total = self._total_counter(conn) if self._total_counter is not None else None
            # [T-5.24] En la MISMA fotografía y bajo el mismo `try`: si la DB
            # falla no sale ninguna de las tres, por la razón de arriba.
            drift = self._drift_gauge(conn) if self._drift_gauge is not None else None
        except Exception:
            logger.warning("no se pudo contar los gabinetes fantasma", exc_info=True)
            return
        datos: list[dict[str, Any]] = [{"MetricName": METRIC_NAME, "Value": valor, "Unit": "Count"}]
        if total is not None:
            datos.append({"MetricName": METRIC_NAME_RETIRED_ALIVE, "Value": total, "Unit": "Count"})
        if drift is not None:
            datos.append(
                {
                    "MetricName": METRIC_NAME_CLOCK_DRIFT,
                    "Value": drift,
                    "Unit": "Milliseconds",
                }
            )
        try:
            self._client.put_metric_data(Namespace=self._namespace, MetricData=datos)
        except Exception:
            # Se registra a propósito: un fallo mudo aquí deja la alarma con cara
            # de sana mientras deja de recibir datos.
            logger.warning("no se pudo publicar la métrica de gabinetes fantasma", exc_info=True)
            return
        if valor:
            logger.warning(
                "%s gabinete(s) RETIRADO(S) siguen reportando SIN CONSTANCIA de "
                "haber recibido su baja: su panel no la declara. Hay que decidir "
                "si se restauran o se desmonta el hardware",
                valor,
            )
