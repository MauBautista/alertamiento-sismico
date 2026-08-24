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


def _vista(*, enabled: bool, beating: bool | None, desconocidos: frozenset[str] = frozenset()):
    """El doble mínimo que `_keepalive_view` mira.

    [T-2.165] Desde que el códec puede declarar campos que el DUEÑO no supo
    decir, la vista mira dos cosas y no una: el valor y si ese valor lo midió
    alguien. Un doble que no lleve `campos_desconocidos` deja de parecerse a una
    instantánea de verdad.
    """
    panel = LocalDashboard.__new__(LocalDashboard)
    panel._keepalive_enabled = enabled
    snap = (
        None
        if beating is None
        else SimpleNamespace(keepalive_beating=beating, campos_desconocidos=desconocidos)
    )
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


def test_un_dueno_ANTIGUO_no_se_pinta_como_una_averia_de_la_ruta() -> None:
    """[T-2.165] El cuarto estado, y por qué no puede ser ninguno de los tres.

    `keepalive_beating=False` significa «hay ruta y NADIE la gobierna» — el
    estado que hay que ver de lejos. Pero cuando el dueño de los pines corre una
    versión anterior, ese `False` no lo midió nadie: lo puso el códec para poder
    construir el objeto. Pintarlo como `habilitada` sería inventarse una avería;
    pintarlo como `sin_ruta`, esconder una ventana.
    """
    v = _vista(enabled=True, beating=False, desconocidos=frozenset({"keepalive_beating"}))
    assert v["estado"] == "dueno_antiguo"
    assert v["beating"] is None, "un valor que nadie midió no puede viajar como booleano"

    # Y la no-vacuidad: con el MISMO valor y el dueño al día, sí es la avería.
    assert _vista(enabled=True, beating=False)["estado"] == "habilitada"
