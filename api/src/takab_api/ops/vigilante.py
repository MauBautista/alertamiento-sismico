"""[T-7.41] Quién vigila a los vigilantes: la EDAD del estado de cada alarma.

**SNS sólo notifica TRANSICIONES.** Una alarma que entra en ALARM y se queda ahí
no vuelve a transicionar, así que **el siguiente suceso real no avisa a nadie** —
y la ceguera no se ve: la consola la pinta en rojo, que es justo lo que uno
espera de una alarma que ya avisó.

Dos casos medidos, no hipotéticos: `takab-dev-iot-rule-errors` pasó **14 días**
en ALARM (y encima por estar sana, `treat_missing_data` equivocado; eso se cerró
en su propia ficha), y `takab-dev-dlq-backfill` quedó clavada por UN mensaje
huérfano hasta que alguien lo purgó a mano.

## ⚠️ El campo correcto es `StateTransitionedTimestamp`

La ficha nombraba `StateUpdatedTimestamp`, y es el equivocado. Del modelo de
servicio del propio CLI —comprobable sin credenciales y sin red:

* `StateUpdatedTimestamp` — «the last update to the value of either the
  **`StateValue` or `EvaluationState`** parameters».
* `StateTransitionedTimestamp` — «the date and time that the alarm's
  **`StateValue`** most recently changed».

O sea que con el primero **una alarma clavada REJUVENECE sola** en cuanto
CloudWatch degrada su evaluación (`PARTIAL_DATA`, `EVALUATION_ERROR`,
`EVALUATION_FAILURE` — «temporary CloudWatch issues»). La de 14 días se leería de
un minuto y el detector nacería ciego y verde: el mismo defecto, una vuelta más
abajo.

Y **`StateTransitionedTimestamp` no es obligatorio** en el shape `MetricAlarm`.
Cuando falta no se inventa una edad ni se cae al otro campo: se DECLARA aparte
(`METRIC_SIN_EDAD`). Un fallback no puede ser «ok».

## Las DOS polaridades, que es lo que cierra la recursión

La pregunta «¿y quién vigila a éste?» se contesta por construcción, pero **hace
falta una métrica de cada signo**:

1. **`METRIC_EDAD`** — la que pagina. Se publica SIEMPRE, incluido el cero
   explícito. Su alarma va con `treat_missing_data = "missing"`, no `breaching`:
   si el publicador muere con la alarma **ya en ALARM**, `breaching` la deja en
   ALARM —cero transiciones, cero correo— y el detector heredaría literalmente el
   defecto que viene a cerrar. Con `missing` transiciona siempre, porque
   INSUFFICIENT_DATA es un TERCER estado distinto de OK y de ALARM (medido en
   vivo en este repo el 2026-07-29 con `set-alarm-state`).
2. **`METRIC_EXAMINADAS`** — la cobertura, vigilada AL REVÉS
   (`LessThanThreshold` + `breaching`). Sin ella, «cero alarmas clavadas» y «no
   miré ninguna» serían **el mismo byte**: un detector roto que devuelve 0
   publicaría un latido perfecto. Es la misma lección que el cero explícito de
   `MaxClockDriftMs`, aplicada a la cobertura en vez de al valor.

## Por qué NO cuelga del contador de fantasmas

`GhostGauge.maybe_publish` mete sus tres cifras bajo un mismo `try` de base de
datos, a propósito: son la misma fotografía. Éste **no toca la base** —lee
CloudWatch— y un fallo de Postgres no puede callar al que vigila a los
vigilantes. Publicación propia, `try` propio.

**El coste, aceptado por escrito:** comparte proceso con el worker `notify`, así
que si ese worker muere llegan TRES correos de INSUFFICIENT_DATA por una sola
causa. `clock_drift` ya aceptó pagar uno duplicado por esto mismo y lo dejó
razonado en `ops/muting.py`; éste es el tercero. La alternativa —un cron
independiente en la instancia— compra independencia de fallo a cambio de perder
la prueba que la ficha exige en su criterio 5: en bash la única cobertura posible
es `strcontains` sobre la plantilla, y `T-7.46` midió que eso **nace verde por
prefijo**. Un guardia que sólo se ha visto en verde no ha demostrado que sepa
ponerse rojo.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

logger = logging.getLogger("takab_api.ops")

#: La edad, en segundos, de la alarma no-OK que lleva MÁS tiempo sin transicionar.
#: Es la que pagina. Se lee en la alarma de Terraform: si cambia aquí, cambia allí.
METRIC_EDAD = "StuckAlarmMaxAgeSeconds"

#: Cuántas alarmas se llegaron a examinar. La polaridad OPUESTA: su número BAJO es
#: la señal. Distingue «no hay ninguna clavada» de «no miré nada», que sin esta
#: cifra son el mismo 0.0 en la métrica de arriba.
METRIC_EXAMINADAS = "StuckAlarmsExamined"

#: Alarmas no-OK sin `StateTransitionedTimestamp` (el campo es opcional en el
#: shape). No se les inventa edad ni se cae al campo equivocado: se declaran.
METRIC_SIN_EDAD = "StuckAlarmsUnmeasurable"


class _MetricClient(Protocol):
    def put_metric_data(self, **kwargs: Any) -> Any: ...


class _AlarmClient(Protocol):
    def describe_alarms(self, **kwargs: Any) -> Any: ...


def _ahora() -> datetime:
    return datetime.now(UTC)


class VigilanteDeAlarmas:
    """Publica la edad del estado de las alarmas. No lanza NUNCA."""

    def __init__(
        self,
        *,
        namespace: str,
        prefijo: str,
        propia: str,
        every_s: float,
        alarmas: _AlarmClient | None = None,
        metricas: _MetricClient | None = None,
        clock: Callable[[], float],
        ahora: Callable[[], datetime] = _ahora,
    ) -> None:
        self._namespace = namespace
        self._prefijo = prefijo
        #: ⚠️ El nombre de SU PROPIA alarma, que se excluye del barrido. Sin esto
        #: el vigilante se AUTO-TRABA: en cuanto salta, se cuenta a sí mismo como
        #: clavado, su edad no deja de crecer y no puede volver a OK jamás.
        self._propia = propia
        self._every_s = every_s
        self._alarmas = alarmas
        self._metricas = metricas
        self._clock = clock
        self._ahora = ahora
        self._last: float | None = None

    # -- el barrido -----------------------------------------------------------

    def _describir(self) -> list[dict[str, Any]]:
        """Todas las alarmas del prefijo, paginando.

        Paginar no es cosmético: hoy hay 18 y las alarmas POR GABINETE crecen con
        la flota. `describe_alarms` devuelve como mucho 100 por página, así que
        una flota mediana partiría el censo en silencio — y lo que no se examina
        se leería como sano.
        """
        assert self._alarmas is not None
        fuera: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"AlarmNamePrefix": self._prefijo, "MaxRecords": 100}
            if token:
                kwargs["NextToken"] = token
            resp = self._alarmas.describe_alarms(**kwargs)
            fuera.extend(resp.get("MetricAlarms", []) or [])
            fuera.extend(resp.get("CompositeAlarms", []) or [])
            token = resp.get("NextToken")
            if not token:
                return fuera

    def medir(self) -> tuple[float, int, int]:
        """`(edad_máxima_s, examinadas, sin_edad)`. Función pura sobre la lectura."""
        alarmas = self._describir()
        ahora = self._ahora()
        edad_max = 0.0
        sin_edad = 0
        examinadas = 0
        for a in alarmas:
            nombre = a.get("AlarmName") or ""
            if nombre == self._propia:
                continue  # ver `self._propia`: contarse a sí misma la auto-traba
            examinadas += 1
            if (a.get("StateValue") or "OK") == "OK":
                continue
            crudo = a.get("StateTransitionedTimestamp")
            if crudo is None:
                sin_edad += 1
                continue
            cuando = crudo if isinstance(crudo, datetime) else datetime.fromisoformat(str(crudo))
            if cuando.tzinfo is None:
                cuando = cuando.replace(tzinfo=UTC)
            edad_max = max(edad_max, (ahora - cuando).total_seconds())
        return edad_max, examinadas, sin_edad

    # -- la publicación -------------------------------------------------------

    def maybe_publish(self) -> None:
        """Publica si toca. No lanza NUNCA: la llama el bucle de un worker."""
        if self._alarmas is None or self._metricas is None:
            return
        now = self._clock()
        if self._last is not None and now - self._last < self._every_s:
            return
        # El sello ANTES de trabajar, como `GhostGauge`: un fallo persistente no
        # puede convertir el estrangulador en un bucle de reintentos.
        self._last = now
        try:
            edad, examinadas, sin_edad = self.medir()
        except Exception:
            # Se registra a propósito: si esto callara, la métrica dejaría de
            # publicarse y la alarma de cobertura es justo la que lo delata.
            logger.warning("no se pudo leer el estado de las alarmas", exc_info=True)
            return
        datos = [
            # El CERO se publica igual. Es la línea que separa una métrica de un
            # adorno: sin él, «ninguna clavada» sería indistinguible de «el que
            # mide está callado», y la vuelta a verde tampoco avisaría.
            {"MetricName": METRIC_EDAD, "Value": edad, "Unit": "Seconds"},
            {"MetricName": METRIC_EXAMINADAS, "Value": float(examinadas), "Unit": "Count"},
            {"MetricName": METRIC_SIN_EDAD, "Value": float(sin_edad), "Unit": "Count"},
        ]
        try:
            self._metricas.put_metric_data(Namespace=self._namespace, MetricData=datos)
        except Exception:
            logger.warning("no se pudo publicar la edad de las alarmas", exc_info=True)
            return
        if edad > 0:
            logger.warning(
                "hay alarma(s) sin transicionar desde hace %.0f s (%.1f días). SNS sólo "
                "notifica TRANSICIONES: mientras siga ahí, el siguiente suceso real no "
                "avisa a nadie",
                edad,
                edad / 86400,
            )
        if sin_edad:
            logger.warning(
                "%d alarma(s) no-OK sin `StateTransitionedTimestamp`: su edad NO se "
                "puede medir y no se les inventa una",
                sin_edad,
            )
