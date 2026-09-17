"""[T-7.41] El vigilante de los vigilantes, y la prueba de que sabe ponerse rojo.

`SNS sólo notifica TRANSICIONES`, así que una alarma clavada en ALARM está MUDA
para el siguiente suceso real. Lo que aquí se fija es lo que la ficha pide en su
criterio 5: **una prueba que falle si el detector deja de detectar.**

## ⚠️ El señuelo

Cada alarma del doble lleva `StateUpdatedTimestamp` —el campo que la ficha
nombraba, y que es el equivocado— apuntando a **hace un minuto**, mientras
`StateTransitionedTimestamp` apunta a hace días. Si alguien «simplifica» el
detector para leer el campo de la ficha, estas pruebas se ponen rojas por
construcción, sin que nadie tenga que acordarse del porqué.

Es el defecto real: `StateUpdatedTimestamp` se mueve también cuando cambia
`EvaluationState`, así que una alarma clavada **rejuvenece sola** en cuanto
CloudWatch degrada su evaluación.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from takab_api.ops.vigilante import (
    METRIC_EDAD,
    METRIC_EXAMINADAS,
    METRIC_SIN_EDAD,
    VigilanteDeAlarmas,
)

AHORA = datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)
PREFIJO = "takab-dev"
PROPIA = "takab-dev-vigilante-clavado"


def _alarma(nombre: str, estado: str, *, hace_s: float | None, sin_campo: bool = False) -> dict:
    """Una alarma como la devuelve `describe_alarms`… con el señuelo puesto."""
    a: dict[str, Any] = {
        "AlarmName": nombre,
        "StateValue": estado,
        # ⚠️ EL SEÑUELO: el campo equivocado, siempre fresco. Leerlo hace que
        # todo parezca recién transicionado y pone esta suite en rojo.
        "StateUpdatedTimestamp": AHORA - timedelta(seconds=60),
    }
    if not sin_campo and hace_s is not None:
        a["StateTransitionedTimestamp"] = AHORA - timedelta(seconds=hace_s)
    return a


class _Alarmas:
    """Doble de CloudWatch escrito a mano, con paginación de verdad."""

    def __init__(self, paginas: list[list[dict]], *, revienta: bool = False) -> None:
        self.paginas = paginas
        self.revienta = revienta
        self.llamadas: list[dict] = []

    def describe_alarms(self, **kwargs: Any) -> dict:
        if self.revienta:
            raise RuntimeError("AccessDenied simulado")
        self.llamadas.append(kwargs)
        i = int(kwargs.get("NextToken") or 0)
        pagina = self.paginas[i]
        fuera: dict[str, Any] = {"MetricAlarms": pagina}
        if i + 1 < len(self.paginas):
            fuera["NextToken"] = str(i + 1)
        return fuera


class _Metricas:
    def __init__(self, *, revienta: bool = False) -> None:
        self.revienta = revienta
        self.publicado: list[dict] = []

    def put_metric_data(self, **kwargs: Any) -> None:
        if self.revienta:
            raise RuntimeError("throttled")
        self.publicado.append(kwargs)


def _vigilante(paginas, *, metricas=None, alarmas=None, every_s=0.0) -> tuple:
    m = metricas or _Metricas()
    a = alarmas if alarmas is not None else _Alarmas(paginas)
    v = VigilanteDeAlarmas(
        namespace="Takab/Ops",
        prefijo=PREFIJO,
        propia=PROPIA,
        every_s=every_s,
        alarmas=a,
        metricas=m,
        clock=lambda: 1000.0,
        ahora=lambda: AHORA,
    )
    return v, a, m


def _valores(m: _Metricas) -> dict[str, float]:
    return {d["MetricName"]: d["Value"] for d in m.publicado[-1]["MetricData"]}


# ───────────────────────────────── lo que tiene que detectar


def test_una_alarma_CLAVADA_catorce_dias_sale_con_su_edad() -> None:
    """El caso real de `iot-rule-errors`, que estuvo 14 días sin poder avisar."""
    v, _a, m = _vigilante([[_alarma("takab-dev-iot-rule-errors", "ALARM", hace_s=14 * 86400)]])
    v.maybe_publish()
    assert _valores(m)[METRIC_EDAD] == pytest.approx(14 * 86400)


def test_una_que_ACABA_de_saltar_no_se_confunde_con_una_clavada() -> None:
    """La ficha exige distinguirlas; si no, el primer hallazgo sería ruido."""
    v, _a, m = _vigilante([[_alarma("takab-dev-dlq-events", "ALARM", hace_s=60)]])
    v.maybe_publish()
    assert _valores(m)[METRIC_EDAD] == pytest.approx(60)


def test_las_alarmas_en_OK_no_cuentan_por_viejas_que_sean() -> None:
    """Un `OK` de hace 67 días no es un vigilante muerto: es que no pasó nada.

    Medido en la nube el 2026-09-17: `ec2-status-check` llevaba 66.8 días sin
    transicionar, y está perfectamente sana.
    """
    v, _a, m = _vigilante([[_alarma("takab-dev-ec2-status-check", "OK", hace_s=67 * 86400)]])
    v.maybe_publish()
    assert _valores(m)[METRIC_EDAD] == 0.0
    assert _valores(m)[METRIC_EXAMINADAS] == 1.0


def test_el_CERO_se_publica_igual() -> None:
    """Sin el cero, «ninguna clavada» y «el que mide está callado» serían lo mismo."""
    v, _a, m = _vigilante([[_alarma("takab-dev-x", "OK", hace_s=10)]])
    v.maybe_publish()
    assert METRIC_EDAD in _valores(m) and _valores(m)[METRIC_EDAD] == 0.0


# ───────────────────── la recursión: no puede contarse a sí misma


def test_el_vigilante_NO_se_cuenta_a_si_mismo() -> None:
    """⚠️ Si lo hiciera, se AUTO-TRABA.

    En cuanto salta, se ve a sí mismo como clavado, su edad no deja de crecer y
    **no puede volver a OK jamás**: el vigilante se convertiría en el primer
    vigilante muerto.
    """
    v, _a, m = _vigilante(
        [
            [
                _alarma(PROPIA, "ALARM", hace_s=30 * 86400),
                _alarma("takab-dev-otra", "OK", hace_s=10),
            ]
        ]
    )
    v.maybe_publish()
    assert _valores(m)[METRIC_EDAD] == 0.0, "se contó a sí mismo: no podría volver a OK nunca"
    assert _valores(m)[METRIC_EXAMINADAS] == 1.0, "la propia no cuenta como cobertura"


# ──────────────── la otra polaridad: «no miré nada» ≠ «nada que mirar»


def test_la_COBERTURA_distingue_no_hay_nada_de_no_mire_nada() -> None:
    """Sin esta cifra, un detector roto publica un latido perfecto.

    «Cero clavadas» y «cero examinadas» dan el MISMO 0.0 en la métrica de edad.
    Por eso la cobertura se vigila al revés: su número bajo es la señal.
    """
    con, _a, m1 = _vigilante([[_alarma(f"takab-dev-{i}", "OK", hace_s=5) for i in range(12)]])
    con.maybe_publish()
    sin, _b, m2 = _vigilante([[]])
    sin.maybe_publish()
    assert _valores(m1)[METRIC_EDAD] == _valores(m2)[METRIC_EDAD] == 0.0
    assert _valores(m1)[METRIC_EXAMINADAS] == 12.0
    assert _valores(m2)[METRIC_EXAMINADAS] == 0.0, (
        "sin la cobertura, un barrido que no ve nada es indistinguible de uno sano"
    )


# ─────────────────────── lo que no se sabe, se DECLARA


def test_una_alarma_SIN_el_campo_no_recibe_una_edad_inventada() -> None:
    """`StateTransitionedTimestamp` es OPCIONAL en el shape `MetricAlarm`.

    Cuando falta, no se le inventa edad ni se cae al campo equivocado: se cuenta
    aparte. Un fallback no puede ser «ok».
    """
    v, _a, m = _vigilante([[_alarma("takab-dev-rara", "ALARM", hace_s=None, sin_campo=True)]])
    v.maybe_publish()
    assert _valores(m)[METRIC_SIN_EDAD] == 1.0
    assert _valores(m)[METRIC_EDAD] == 0.0, "le inventó una edad"


# ──────────────────────────────── las mutaciones: que sepa ponerse rojo


def test_el_barrido_PAGINA() -> None:
    """Hoy son 18 alarmas y las de POR GABINETE crecen con la flota.

    `describe_alarms` devuelve 100 como mucho: sin paginar, el censo se partiría
    en silencio y lo no examinado se leería como sano.
    """
    paginas = [
        [_alarma(f"takab-dev-p1-{i}", "OK", hace_s=5) for i in range(100)],
        [_alarma("takab-dev-p2-clavada", "ALARM", hace_s=9 * 86400)],
    ]
    v, a, m = _vigilante(paginas)
    v.maybe_publish()
    assert len(a.llamadas) == 2, "no paginó: se quedó con la primera página"
    assert _valores(m)[METRIC_EXAMINADAS] == 101.0
    assert _valores(m)[METRIC_EDAD] == pytest.approx(9 * 86400), (
        "la clavada estaba en la segunda página y no la vio"
    )


def test_las_alarmas_COMPUESTAS_tambien_se_miran() -> None:
    """`describe_alarms` las devuelve en otra lista, y también pueden clavarse."""
    a = _Alarmas([[]])

    def describir(**kwargs: Any) -> dict:
        a.llamadas.append(kwargs)
        return {
            "MetricAlarms": [],
            "CompositeAlarms": [_alarma("takab-dev-comp", "ALARM", hace_s=5 * 86400)],
        }

    a.describe_alarms = describir  # type: ignore[method-assign]
    v, _a, m = _vigilante([], alarmas=a)
    v.maybe_publish()
    assert _valores(m)[METRIC_EDAD] == pytest.approx(5 * 86400)


def test_si_la_LECTURA_falla_no_se_publica_un_cero_tranquilizador() -> None:
    """⚠️ La mutación que más importa.

    Un `AccessDenied` que acabara publicando `0.0` sería el peor resultado
    posible: el vigilante diría «todo en orden» precisamente porque no puede
    mirar. Se calla, y entonces habla la alarma de cobertura por ausencia.
    """
    v, _a, m = _vigilante([], alarmas=_Alarmas([], revienta=True))
    v.maybe_publish()
    assert m.publicado == [], "publicó un cero tranquilizador sin haber podido mirar"


def test_si_la_PUBLICACION_falla_no_revienta_el_worker() -> None:
    v, _a, m = _vigilante(
        [[_alarma("takab-dev-x", "OK", hace_s=5)]], metricas=_Metricas(revienta=True)
    )
    v.maybe_publish()  # no lanza


def test_el_estrangulador_respeta_su_ventana() -> None:
    v, a, _m = _vigilante([[_alarma("takab-dev-x", "OK", hace_s=5)]], every_s=300.0)
    v.maybe_publish()
    v.maybe_publish()
    assert len(a.llamadas) == 1, "publicó dos veces dentro de la misma ventana"


def test_sin_clientes_no_hace_nada() -> None:
    """En local no hay CloudWatch, y eso no puede tumbar el worker."""
    v = VigilanteDeAlarmas(
        namespace="Takab/Ops",
        prefijo=PREFIJO,
        propia=PROPIA,
        every_s=0.0,
        alarmas=None,
        metricas=None,
        clock=lambda: 0.0,
    )
    v.maybe_publish()
