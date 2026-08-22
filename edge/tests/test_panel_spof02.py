"""[T-2.146 · SPOF-02] El panel distingue TRES estados de la ruta de hardware.

El latido del `K_wd` es la única forma de saber, sin un multímetro en el gabinete,
quién gobierna la sirena. Y la trampa está en que **dos de los tres estados son «no
late» y significan cosas opuestas**:

- **sin ruta** — el latido está deshabilitado porque el `K_wd` no está montado
  (`D-16` aplazó la BOM). No hay nada que gobernar: **no es una avería**.
- **habilitada** — hay ruta y NO late: el WR-1 puede sonar la sirena **solo**, y
  nadie la calla desde el panel. Es el estado que hay que ver de lejos.

Pintar los dos igual sería la regla de oro 7 en su forma más cara: un operador que
lee «no late» en un gabinete sin `K_wd` aprende a ignorar el rótulo, y lo ignorará
el día que sí importe.
"""

from __future__ import annotations

from types import SimpleNamespace

from takab_edge.local_api import LocalDashboard


def _vista(*, enabled: bool, beating: bool | None):
    """`_keepalive_view` solo lee `keepalive_beating`: se le pasa un doble mínimo."""
    panel = LocalDashboard.__new__(LocalDashboard)
    panel._keepalive_enabled = enabled
    snap = None if beating is None else SimpleNamespace(keepalive_beating=beating)
    return panel._keepalive_view(snap)


def test_sin_K_wd_montado_no_es_una_averia() -> None:
    v = _vista(enabled=False, beating=False)
    assert v["estado"] == "sin_ruta"
    assert v["estado"] != "habilitada", (
        "un gabinete sin `K_wd` no puede rotularse igual que uno cuya ruta de "
        "hardware está viva y sin gobierno: son los dos «no late» y son opuestos"
    )


def test_con_ruta_y_latiendo_el_Pi_gobierna() -> None:
    assert _vista(enabled=True, beating=True)["estado"] == "inhibida"


def test_con_ruta_y_SIN_latir_la_sirena_puede_sonar_sola() -> None:
    """El estado peligroso: el WR-1 manda y el panel no puede callar la sirena."""
    assert _vista(enabled=True, beating=False)["estado"] == "habilitada"


def test_sin_poder_leer_el_gpio_no_se_afirma_ninguno() -> None:
    """`S/D` es un estado propio: afirmar «sin ruta» sin haber podido medir sería
    tranquilizar con un dato que nadie tiene."""
    v = _vista(enabled=True, beating=None)
    assert v["estado"] == "sd"
    assert v["beating"] is None


def test_los_tres_estados_son_DISTINTOS_entre_si() -> None:
    """Si dos colapsaran al mismo rótulo, el panel volvería a mentir sin que ningún
    test de los de arriba se pusiera rojo — cada uno mira su caso por separado."""
    estados = {
        _vista(enabled=False, beating=False)["estado"],
        _vista(enabled=True, beating=True)["estado"],
        _vista(enabled=True, beating=False)["estado"],
    }
    assert len(estados) == 3, f"dos estados colapsaron al mismo rótulo: {estados}"
