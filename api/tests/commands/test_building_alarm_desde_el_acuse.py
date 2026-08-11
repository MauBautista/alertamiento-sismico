"""[T-2.120] `building_alarm` sale del ACUSE — y cuando no puede, lo declara.

`T-2.106` escribió, con razón para su día, que «la nube **no sabe si el relé de
la sirena está energizado ahora mismo**» y derivó la alarma del inmueble de
`commands`: la última orden que TOCÓ el relé. `T-2.116` derogó esa premisa — el
acuse trae `channel_state`, el estado del canal TRAS EL ARBITRAJE del gabinete
(`edge/takab_edge/gpio/__init__.py::_desired_energized`), persistido por
`handle_command_ack` en `commands.ack`.

Lo que estas pruebas fijan es la **epistemología** de la afirmación, porque
`building_alarm` es lo que hace sonar un teléfono (`T-2.106`, `T-2.107`):

- **Con medición**, el relé manda. Un `activate` acusado con `activated=false`
  —el gabinete lo ejecutó y el arbitraje NO dejó el canal en protección— deja de
  encender la pantalla: eso es un falso positivo que hoy despierta a un edificio
  de madrugada.
- **Sin medición**, se degrada a la inferencia de `T-2.106` **y se dice**
  (`source="order_inferred"`). El gabinete de campo `gw-dev-0001` todavía corre
  el código anterior a `T-2.116`, así que **el camino degradado es el caso de
  hoy**, no una rama de cortesía.
- **`channel_state = null` es «no pude preguntar»**, jamás «en reposo»
  (`T-2.116`). Un acuse sin el campo NO desmiente la alarma: la degrada.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from takab_api.commands.alarma_inmueble import (
    OrdenSirena,
    fase_del_sitio,
    sirena_activada,
    suena_la_alarma,
)

AHORA = datetime(2026, 8, 11, 14, 32, 0, tzinfo=UTC)
VIGENCIA_S = 1800.0
SIN_ENLACE_S = 300.0

#: El acuse tal cual lo emite el gabinete real (vector compartido de `T-2.116`,
#: `edge/tests/vectors/command_ack_siren_arbitrado.json`), con la sirena
#: TODAVÍA energizada tras el arbitraje.
CENSO_SONANDO: dict[str, Any] = {
    "channel": "siren",
    "energized": True,
    "activated": True,
    "fail_safe": "NO",
    "reason": "alert",
    "alert_latched": True,
}
CENSO_EN_REPOSO: dict[str, Any] = {
    "channel": "siren",
    "energized": False,
    "activated": False,
    "fail_safe": "NO",
    "reason": None,
    "alert_latched": False,
}


def _orden(
    action: str = "activate",
    *,
    hace_s: float = 60.0,
    relays_state: str | None = "reported",
    gateway_age_s: float | None = 30.0,
    channel_state: Any = None,
) -> OrdenSirena:
    return OrdenSirena(
        action=action,
        issued_at=AHORA - timedelta(seconds=hace_s),
        relays_state=relays_state,
        gateway_age_s=gateway_age_s,
        channel_state=channel_state,
    )


def _suena(orden: OrdenSirena | None):
    return suena_la_alarma(orden, ahora=AHORA, vigencia_s=VIGENCIA_S, sin_enlace_s=SIN_ENLACE_S)


# --- la lectura del censo: tres estados, no dos ---------------------------------


def test_el_censo_del_canal_tiene_TRES_respuestas() -> None:
    """`True`/`False` son MEDICIONES; `None` es «no pude preguntar».

    Es la distinción entera de `T-2.116` y la razón de esta ficha: colapsar
    `None` en `False` convierte «no sé» en «no suena», que es exactamente la
    mentira que la regla de oro 7 prohíbe.
    """
    assert sirena_activada(CENSO_SONANDO) is True
    assert sirena_activada(CENSO_EN_REPOSO) is False
    assert sirena_activada(None) is None


@pytest.mark.parametrize(
    "censo",
    [
        pytest.param({"channel": "gas", "activated": True}, id="otro-canal"),
        pytest.param({"activated": True}, id="sin-canal"),
        pytest.param({"channel": "siren"}, id="sin-activated"),
        pytest.param({"channel": "siren", "activated": "true"}, id="activated-no-booleano"),
        pytest.param("relay", id="el-detail-viejo"),
        pytest.param([], id="lista"),
    ],
)
def test_un_censo_que_no_habla_de_ESTA_sirena_no_es_medicion(censo: Any) -> None:
    """Default-deny en la LECTURA: si el censo no es, letra por letra, el del
    canal `siren` con un `activated` booleano, no es una medición de la sirena.
    Se degrada a «no pude preguntar» — nunca se lee el relé del gas como si
    fuera el de la sirena, ni se interpreta el `detail="relay"` de antes de
    `T-2.116` como un censo."""
    assert sirena_activada(censo) is None


# --- camino MEDIDO --------------------------------------------------------------


def test_el_acuse_que_mide_la_sirena_sostiene_la_alarma_y_lo_DECLARA() -> None:
    alarma = _suena(_orden(channel_state=CENSO_SONANDO))
    assert alarma is not None
    assert alarma.since == AHORA - timedelta(seconds=60)
    assert alarma.origen == "relay_measured"


def test_el_acuse_que_mide_la_sirena_EN_REPOSO_desmiente_la_alarma() -> None:
    """El falso positivo que esta ficha cierra.

    El gabinete acusó el `activate` con éxito —la ORDEN se ejecutó— y el
    arbitraje dejó el canal SIN protección: fail-safe, prueba en curso, o
    cualquier otra demanda que gobierne el pin. Hasta hoy la nube contaba el
    `status='acked'` como «suena» y encendía la pantalla del inmueble entero.
    """
    assert _suena(_orden(channel_state=CENSO_EN_REPOSO)) is None


def test_la_medicion_NO_exime_de_las_guardas_de_frescura() -> None:
    """La medición es de un instante PASADO, no de ahora.

    `channel_state` describe el relé en el momento del acuse. Que el gabinete
    lleve horas mudo, que ya no pueda leerse los relés o que la alarma haya
    caducado siguen desmintiendo igual: un dato medido y viejo pintado como vivo
    es la regla de oro 7 con mejor coartada, no una excepción a ella.
    """
    assert _suena(_orden(channel_state=CENSO_SONANDO, gateway_age_s=SIN_ENLACE_S + 1.0)) is None
    assert _suena(_orden(channel_state=CENSO_SONANDO, gateway_age_s=None)) is None
    assert _suena(_orden(channel_state=CENSO_SONANDO, relays_state="unreadable")) is None
    assert _suena(_orden(channel_state=CENSO_SONANDO, hace_s=VIGENCIA_S + 1.0)) is None


def test_el_silencio_EJECUTADO_manda_aunque_el_rele_siga_energizado() -> None:
    """El caso de vida de `T-2.110`, y por qué NO cambia de veredicto.

    Un `deactivate` acusado con `activated=true` es la persona retirando su
    demanda manual mientras otra —una alerta enclavada o una prueba— sostiene el
    relé. La sirena suena, sí, pero **ya no es la alarma del inmueble**: lo que
    la sostiene tiene su propia superficie (`alert_active` gana la precedencia; la
    prueba es una prueba). Anunciarla como alarma del inmueble sería atribuirle a
    una persona una sirena que la persona intentó apagar — la mentira de
    `T-2.104` en el otro sentido.

    Quien SÍ lo explica, y con las palabras del gabinete, es la hoja de mando del
    táctico (`mobile/src/features/control/ackState.ts`, `T-2.116`).
    """
    assert _suena(_orden("deactivate", channel_state=CENSO_SONANDO)) is None


# --- camino DEGRADADO: el gabinete de hoy ---------------------------------------


def test_el_gabinete_de_HOY_degrada_a_la_inferencia_y_lo_declara() -> None:
    """`gw-dev-0001` corre el código anterior a `T-2.116`: su acuse no trae censo.

    La afirmación se sostiene con la inferencia de `T-2.106` —la orden ejecutada
    más la corroboración del latido— pero sale ETIQUETADA como inferencia. La
    app no puede decir «el relé está energizado» sobre esto, porque nadie lo
    midió.
    """
    alarma = _suena(_orden(channel_state=None))
    assert alarma is not None
    assert alarma.origen == "order_inferred"


def test_un_acuse_sin_censo_JAMAS_significa_en_reposo() -> None:
    """La distinción sagrada de `T-2.116`, en la superficie que despierta gente.

    Si la ausencia del campo se leyera como «el relé está en reposo», el
    despliegue de `T-2.116` habría apagado la alarma del inmueble en TODOS los
    gabinetes que aún no se re-desplegaron — un falso negativo silencioso sobre
    la flota entera.
    """
    for censo in (None, {}, {"channel": "siren"}):
        alarma = _suena(_orden(channel_state=censo))
        assert alarma is not None, f"censo {censo!r} se leyó como «no suena»"
        assert alarma.origen == "order_inferred"


def test_las_cuatro_guardas_de_T_2_106_siguen_en_pie_sin_censo() -> None:
    """La degradación es al método de ayer COMPLETO, no a una versión relajada."""
    assert _suena(_orden("deactivate")) is None
    assert _suena(_orden(gateway_age_s=SIN_ENLACE_S + 1.0)) is None
    assert _suena(_orden(relays_state="unreadable")) is None
    assert _suena(_orden(hace_s=VIGENCIA_S + 1.0)) is None
    assert _suena(None) is None


# --- la precedencia no cambia ---------------------------------------------------


def test_lo_sismico_sigue_mandando_sobre_una_alarma_MEDIDA() -> None:
    """Medir el relé no le da a la alarma del inmueble ningún rango nuevo."""
    alarma = _suena(_orden(channel_state=CENSO_SONANDO))
    assert fase_del_sitio("alert_active", alarma) == "alert_active"
    assert fase_del_sitio("idle", alarma) == "building_alarm"
