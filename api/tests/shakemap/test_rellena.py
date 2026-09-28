"""[T-9.50 · D-44] `python -m takab_api.shakemap.rellena`: el mapa de los sismos VIEJOS.

La pasada del worker sólo mira `incident_review_ttl_s` hacia atrás, a propósito
(un arranque en frío no puede recalcular meses bloqueando el bucle). Los incidentes
anteriores a `T-9.50` que nunca entraron en revisión se quedaron sin mapa, y los
que lo tienen no tienen superficie. Esto los rellena UNA vez, a mano, por rango.

Se corre contra la base y con el escenario de `test_pasada.py`: los incidentes
son del 19-S de 2017, muy fuera de la ventana del worker.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

from datetime import timedelta

import pytest

from takab_api.shakemap import calculo as C
from takab_api.shakemap import rellena as R
from takab_api.shakemap import servicio as S
from tests.shakemap.test_pasada import (  # noqa: F401  (fixture de pytest, por nombre)
    ABIERTO,
    PGA_CDMX,
    Escenario,
    _settings,
    esc,
)


def _dos_incidentes_viejos(esc: Escenario) -> tuple[str, str]:
    a = esc.incidente(en_revision=False, cuando=ABIERTO)
    b = esc.incidente(en_revision=False, cuando=ABIERTO + timedelta(hours=2))
    esc.mide("CDMX", PGA_CDMX, cuando=ABIERTO + timedelta(seconds=30))
    esc.mide("CDMX", PGA_CDMX, cuando=ABIERTO + timedelta(hours=2, seconds=30))
    return a, b


def test_la_pasada_del_worker_NO_los_ve(esc: Escenario) -> None:
    """La premisa: fuera de la ventana, el worker no estrena mapa."""
    _dos_incidentes_viejos(esc)
    assert esc.pasada(now=ABIERTO + timedelta(days=30)).calculados == ()


def test_el_relleno_calcula_los_dos_y_lo_dice(
    esc: Escenario, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = _dos_incidentes_viejos(esc)
    # Uno FUERA del rango pedido: no se toca.
    fuera = esc.incidente(en_revision=False, cuando=ABIERTO + timedelta(days=3))

    pasada = R.main(["--desde", "2017-09-19", "--hasta", "2017-09-20"], settings=_settings())

    assert set(pasada.calculados) == {a, b}
    assert pasada.corte is None
    assert esc.snapshot(a)["estado"] == C.ESTADO_COMPLETO
    assert esc.snapshot(b)["estado"] == C.ESTADO_COMPLETO
    assert esc.snapshot(fuera) is None
    salida = capsys.readouterr().out
    assert "2 mapas" in salida
    assert "sin corte" in salida

    # Idempotente y converge: una segunda corrida no rehace nada.
    assert R.main(["--desde", "2017-09-19", "--hasta", "2017-09-20"], settings=_settings()) == (
        S.PasadaDeShakemap()
    )


def test_el_relleno_DECLARA_el_corte_por_tope(
    esc: Escenario, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = _dos_incidentes_viejos(esc)
    pasada = R.main(["--desde", "2017-09-19", "--max", "1"], settings=_settings())
    assert pasada.calculados == (a,), "por orden de apertura"
    assert pasada.corte == S.CORTE_POR_TOPE
    assert "CORTADO POR TOPE" in capsys.readouterr().out
    # La vuelta siguiente sigue donde se quedó.
    assert R.main(["--desde", "2017-09-19", "--max", "1"], settings=_settings()).calculados == (b,)


def test_la_fecha_mal_escrita_es_un_error_de_uso() -> None:
    with pytest.raises(SystemExit):
        R.main(["--desde", "19/09/2017"], settings=_settings())
