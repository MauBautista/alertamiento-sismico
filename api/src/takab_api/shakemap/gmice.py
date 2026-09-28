"""[T-9.51 · D-44] La intensidad Mercalli ESTIMADA a partir de la PGA.

Módulo puro. Es una **conversión**, no una observación: la intensidad macrosísmica
se construye con efectos observados, y aquí se ESTIMA desde la aceleración con una
relación publicada. Por eso quien la pinte tiene que decir «estimada» y citar de
dónde sale (`CITA`); los documentos anteriores a `D-44` que dicen que TAKAB no
reporta intensidad siguen siendo ciertos para su fecha.

La relación es la de Wald, Quitoriano, Heaton y Kanamori (1999), la que usa el
ShakeMap del USGS para California, con la PGA en cm/s²:

* por debajo de V: ``Imm = 2.20·log10(PGA) + 1.00``
* desde V:         ``Imm = 3.66·log10(PGA) − 1.66``

Se usa sólo la rama de PGA, porque la superficie que se estima es de PGA; el
artículo recomienda la PGV para las intensidades altas, y ésa es una mejora
pendiente, no un olvido. El resultado se acota a [I, X].
"""

from __future__ import annotations

import math

#: De dónde sale el número. Viaja con la superficie y lo imprime quien la pinte.
CITA = "Wald et al. (1999), relación PGA–MMI"

#: g → cm/s².
G_A_CMS2 = 980.665

#: La PGA (cm/s²) donde la rama alta vale exactamente V: ahí se parte.
_PGA_V_CMS2 = 10 ** ((5.0 + 1.66) / 3.66)

_ROMANOS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


def mmi_de_pga(pga_g: float | None) -> float | None:
    """La MMI estimada (1–10) de una PGA en g; ``None`` si no hay PGA medible."""
    if pga_g is None or not math.isfinite(pga_g) or pga_g <= 0:
        return None
    pga = pga_g * G_A_CMS2
    if pga < _PGA_V_CMS2:
        mmi = 2.20 * math.log10(pga) + 1.00
    else:
        mmi = 3.66 * math.log10(pga) - 1.66
    return min(10.0, max(1.0, mmi))


def romano(mmi: float) -> str:
    """El grado en números romanos, redondeado al entero más cercano (5.5 → VI)."""
    grado = int(math.floor(mmi + 0.5))
    return _ROMANOS[min(10, max(1, grado)) - 1]
