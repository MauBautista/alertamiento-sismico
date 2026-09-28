"""[T-9.51 · D-44] La MMI ESTIMADA a partir de la PGA (Wald et al., 1999).

Puntos de control calculados a mano con las dos ramas del artículo (PGA en cm/s²):
  · I < V:   Imm = 2.20·log10(PGA) + 1.00
  · V ≤ I:   Imm = 3.66·log10(PGA) − 1.66
"""

from __future__ import annotations

import math

import pytest

from takab_api.shakemap import gmice as G


@pytest.mark.parametrize(
    ("pga_g", "mmi"),
    [
        (0.01, 2.20 * math.log10(0.01 * 980.665) + 1.00),  # 3.18: rama baja
        (0.1, 3.66 * math.log10(0.1 * 980.665) - 1.66),  # 5.63: rama alta
        (0.3, 3.66 * math.log10(0.3 * 980.665) - 1.66),  # 7.38
    ],
)
def test_los_puntos_de_control_de_wald(pga_g: float, mmi: float) -> None:
    assert G.mmi_de_pga(pga_g) == pytest.approx(mmi, abs=1e-9)


def test_las_dos_ramas_se_tocan_en_V() -> None:
    """El artículo parte en I = V; a la PGA donde la rama alta vale 5, la baja casi también."""
    pga_v_cms2 = 10 ** ((5 + 1.66) / 3.66)
    baja = 2.20 * math.log10(pga_v_cms2) + 1.00
    assert baja == pytest.approx(5.0, abs=0.01)
    assert G.mmi_de_pga(pga_v_cms2 / 980.665) == pytest.approx(5.0, abs=1e-9)


def test_crece_con_la_pga() -> None:
    valores = [G.mmi_de_pga(g) for g in (0.001, 0.005, 0.02, 0.05, 0.1, 0.5, 1.5)]
    assert valores == sorted(valores)


def test_se_acota_entre_I_y_X() -> None:
    assert G.mmi_de_pga(1e-7) == 1.0
    assert G.mmi_de_pga(50.0) == 10.0


@pytest.mark.parametrize("malo", [0.0, -0.1, float("nan"), None])
def test_sin_pga_medible_no_hay_intensidad(malo) -> None:
    """Cero, negativo o nada: no se inventa una intensidad."""
    assert G.mmi_de_pga(malo) is None


@pytest.mark.parametrize(
    ("mmi", "romano"),
    [(1.0, "I"), (3.18, "III"), (5.5, "VI"), (5.49, "V"), (7.38, "VII"), (10.0, "X")],
)
def test_el_romano_redondea_al_entero_mas_cercano(mmi: float, romano: str) -> None:
    assert G.romano(mmi) == romano


def test_la_cita_viaja_con_el_dato() -> None:
    """Quien pinte la MMI tiene que poder decir de dónde sale."""
    assert "Wald" in G.CITA and "1999" in G.CITA
