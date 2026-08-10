"""[T-2.105] Quién puede ordenar evacuar, y quién solo advertir.

La regla, ratificada el 2026-08-09: una alarma y un aviso de evacuación SOLO se
despliegan con la señal del WR-1 de SASMEX, o con tres o más inmuebles moviéndose
y rebasando el umbral al mismo tiempo. Una estación individual solo advierte al
SOC y al gabinete — pudo ser un factor externo y no un sismo.

El defecto que cierra esto: `mobile_state` derivaba la fase SIN mirar el origen,
así que un umbral instrumental de un solo gabinete producía exactamente la misma
toma de pantalla con «EVACÚE AHORA» que SASMEX. Medido en un Pixel 8 Pro el
2026-08-09, moviendo el sensor con la mano.
"""

from __future__ import annotations

import pytest

from takab_api.incident.autoridad import autoriza_evacuacion

MIN = 3


def test_sasmex_autoriza_siempre() -> None:
    """El contacto seco del WR-1 es el canal primario y autoritativo."""
    assert autoriza_evacuacion("sasmex", None, MIN) is True


@pytest.mark.parametrize("nodos", [None, 0, 1, 2])
def test_una_estacion_sola_NO_autoriza(nodos: int | None) -> None:
    """Ni sin corroboración, ni con menos estaciones que el mínimo.

    `2` es el caso interesante: hay corroboración, pero no la que la política
    exige. Un umbral que se conformara con dos sacaría a la calle a un edificio
    porque pasaron dos camiones.
    """
    assert autoriza_evacuacion("local_threshold", nodos, MIN) is False


def test_el_cuorum_de_red_autoriza_sin_reescribir_el_trigger() -> None:
    """Un incidente NACE `local_threshold` y pasa a autorizar cuando la red lo
    corrobora: el motor de cuórum enlaza el evento y su `node_count`, pero NO
    reescribe el trigger. Si esta prueba se cae, el cuórum dejó de reconocerse.
    """
    assert autoriza_evacuacion("local_threshold", MIN, MIN) is True
    assert autoriza_evacuacion("local_threshold", MIN + 5, MIN) is True


def test_el_trigger_quorum_tambien_autoriza() -> None:
    """Está en el CHECK de `incidents.trigger` aunque hoy nadie lo escriba: si
    mañana el motor lo usa, no puede reabrirse el agujero en silencio."""
    assert autoriza_evacuacion("quorum", None, MIN) is True


def test_manual_y_desconocido_NO_autorizan_evacuacion_sismica() -> None:
    """Default-deny. Una activación manual es alarma del inmueble, no una orden
    de evacuación sísmica; y un origen que nadie previó tampoco manda a nadie a
    la calle. Equivocarse hacia «no ordeno evacuar» deja a la gente donde estaba.
    """
    assert autoriza_evacuacion("manual", None, MIN) is False
    assert autoriza_evacuacion("origen_del_futuro", None, MIN) is False


def test_el_minimo_sale_de_la_configuracion_y_no_de_un_3_a_mano() -> None:
    """`quorum_min_nodes` es ajustable; la regla tiene que moverse con él."""
    assert autoriza_evacuacion("local_threshold", 4, 5) is False
    assert autoriza_evacuacion("local_threshold", 5, 5) is True
