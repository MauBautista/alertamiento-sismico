"""T-5.24 · Los CUATRO espejos del umbral de reloj, comparados por igualdad.

Tras esta ficha, el «100 ms» a partir del cual un reloj está fuera de rango vive
en cuatro sitios distintos, escrito en tres lenguajes distintos:

  1. `Settings.fleet_ntp_offset_max_ms` — con el que la NUBE degrada el estado
     del sitio en la consola y en el móvil.
  2. `col(..., 100, 1000)` del panel del gabinete — el ámbar que ve quien está
     físicamente delante del Pi.
  3. `var.clock_drift_max_ms` de `modules/observability` — el umbral de la
     alarma que PAGINA a quien esté de guardia.
  4. El badge `NTP OFFSET` del panel de detalle del SOC — el semáforo que ve el
     operador junto al mapa. Estaba en **50 ms**, o sea que se ponía rojo con el
     sitio declarado OPERATIVO por la misma consola y ámbar en el panel del Pi.

Cuatro superficies que discrepen sobre si un gabinete está sano es peor que tener
una sola: el operador ve verde en el panel, la consola lo pinta degradado y la
alarma no suena — o al revés. Y ninguno de los cuatro se entera de los otros.

Este archivo los DERIVA y los compara por igualdad, en vez de confiar en que
alguien recuerde los cuatro al mover uno. Es la doctrina del repo: un censo que
enumera a mano acaba divergiendo.

Lo que este test NO hace: opinar sobre el valor. Si mañana se decide que son
50 ms, se cambian los cuatro y sigue verde. Lo que no puede pasar es que se cambie
uno.
"""

from __future__ import annotations

import re
from pathlib import Path

from takab_api.settings import Settings

_RAIZ = Path(__file__).resolve().parents[3]
_PANEL = _RAIZ / "edge" / "takab_edge" / "local_api" / "index.html"
_VARIABLES_TF = _RAIZ / "infra" / "terraform" / "modules" / "observability" / "variables.tf"
_DETALLE_SOC = _RAIZ / "web" / "src" / "features" / "console" / "DetailPanel.tsx"


def _umbral_del_panel() -> float:
    """El ámbar de la fila 'Desfase de reloj NTP' del panel del gabinete.

    Se ancla en el nombre de la fila y no en el número: buscar `100` en un HTML de
    1 400 líneas encontraría cualquier cosa, y un censo que encuentra cualquier
    cosa no cierra ningún hueco.
    """
    fuente = _PANEL.read_text(encoding="utf-8")
    fila = re.search(r"rows\.push\(\['Desfase de reloj NTP'.*?\]\);", fuente, re.S)
    assert fila, (
        "no se encontró la fila 'Desfase de reloj NTP' en el panel del gabinete. "
        "Si se renombró, este censo dejó de vigilar el espejo que más se mira: "
        f"{_PANEL}"
    )
    umbrales = re.search(r"col\([^,]+,\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)", fila.group(0))
    assert umbrales, (
        "la fila del reloj ya no usa el ayudante `col(valor, ambar, rojo)`. Si "
        "volvió a un ternario propio, perdió los umbrales y con ellos el sentido "
        f"de este censo. Fila: {fila.group(0)}"
    )
    return float(umbrales.group(1))


def _umbral_de_la_alarma() -> float:
    """El `default` de `var.clock_drift_max_ms`, leído del propio `variables.tf`."""
    fuente = _VARIABLES_TF.read_text(encoding="utf-8")
    bloque = re.search(r'variable\s+"clock_drift_max_ms"\s*\{(.*?)\n\}', fuente, re.S)
    assert bloque, (
        "desapareció `var.clock_drift_max_ms` de `modules/observability`: la alarma "
        f"de reloj se quedó sin umbral configurable. {_VARIABLES_TF}"
    )
    default = re.search(r"default\s*=\s*([0-9.]+)", bloque.group(1))
    assert default, "`clock_drift_max_ms` sin `default`: el módulo no planificaría solo"
    return float(default.group(1))


def _umbral_del_soc() -> float:
    """El `ok=` del badge NTP OFFSET del panel de detalle de la consola."""
    fuente = _DETALLE_SOC.read_text(encoding="utf-8")
    badge = re.search(
        r'label="NTP OFFSET".*?ok=\{[^}]*?Math\.abs\(soh\.ntp_offset_ms\)\s*<\s*([0-9.]+)',
        fuente,
        re.S,
    )
    assert badge, (
        "no se encontró el umbral del badge NTP OFFSET en el panel de detalle del "
        f"SOC. Si cambió de forma, este censo dejó de vigilarlo: {_DETALLE_SOC}"
    )
    return float(badge.group(1))


def test_los_cuatro_espejos_dicen_LO_MISMO() -> None:
    espejos = {
        "nube · Settings.fleet_ntp_offset_max_ms": Settings().fleet_ntp_offset_max_ms,
        "panel del gabinete · fila 'Desfase de reloj NTP'": _umbral_del_panel(),
        "alarma · var.clock_drift_max_ms": _umbral_de_la_alarma(),
        "SOC · badge NTP OFFSET": _umbral_del_soc(),
    }

    assert len(set(espejos.values())) == 1, (
        "los espejos del umbral de reloj discrepan, así que un mismo gabinete "
        "puede estar sano en una superficie y enfermo en otra. Hay que mover los "
        f"CUATRO a la vez: {espejos}"
    )


def test_el_censo_no_esta_vacio() -> None:
    """La guarda anti-vacuidad: un censo que no encuentra nada pasa en verde.

    Declara los CUATRO en voz alta. Si mañana alguien añade un quinto espejo (el
    móvil no cuenta: recibe el umbral de la API en el payload), este número tiene
    que subir a mano — que es justo el momento de acordarse.
    """
    espejos = (
        Settings().fleet_ntp_offset_max_ms,
        _umbral_del_panel(),
        _umbral_de_la_alarma(),
        _umbral_del_soc(),
    )
    assert len(espejos) == 4, "el censo cambió de tamaño sin que nadie lo declarara"
    assert all(v > 0 for v in espejos), f"algún espejo salió en cero o negativo: {espejos}"
