"""[T-7.14] Los dos planes de arribos dan LO MISMO, y no de palabra.

`edge/simulators/replay.py` es una copia deliberada de
`api/src/takab_api/replay/plan.py`: el simulador corre en un portátil o en el Pi 4
con el entorno de `edge/`, sin el paquete de la nube instalado — el mismo motivo
por el que el panel del gabinete lleva su propio ATTEN-LAW.

Una copia sin esta prueba es una bomba de relojería: alguien toca una fórmula de
un lado, las dos suites siguen verdes, y el día de la demostración las estaciones
simuladas sienten la onda en un instante y el mapa la pinta en otro. Aquí el
módulo de la nube se importa **por ruta** —solo necesita la biblioteca estándar,
así que no hace falta instalar el paquete de la nube— y se comparan las dos
salidas sobre una rejilla de sismos y estaciones. No es un censo de nombres: es
la salida, número a número.

⚠️ Si el módulo de la nube no se pudiera cargar, este fichero falla en vez de
saltarse. Un `skip` aquí sería exactamente el verde que no significa nada.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
from simulators import replay as edge

_RAIZ = Path(__file__).resolve().parents[2]
_API_SRC = _RAIZ / "api/src"


def _plan_de_la_nube():
    """El módulo de la nube, importado por ruta. Solo depende de `math`."""
    assert _API_SRC.is_dir(), f"no está `api/src` en {_RAIZ}: el espejo no se puede comparar"
    if str(_API_SRC) not in sys.path:
        sys.path.insert(0, str(_API_SRC))
    from takab_api.replay import plan as nube  # noqa: PLC0415  (import por ruta, a propósito)

    return nube


NUBE = _plan_de_la_nube()

#: Rejilla: dos soluciones del 19-S (SSN y USGS, que difieren ~28 km y 9 km de
#: profundidad), una somera sin profundidad reportada, y un lejano.
SISMOS = [
    ("SSN-2017-09-19-PUE", 7.1, 18.40, -98.72, 57.0),
    ("USGS-2017-09-19-PUE", 7.1, 18.5499, -98.4887, 48.0),
    ("SIN-PROFUNDIDAD", 6.0, 19.0, -99.0, None),
    ("SSN-2017-09-08-TEHU", 8.2, 14.85, -94.11, 58.0),
]

#: Las cuatro de la demostración más una encima del epicentro (el caso de borde
#: donde la distancia epicentral es cero y solo queda la profundidad).
ESTACIONES = [
    ("s1", "site-dev", 19.05, -98.22),
    ("s2", "site-sim-101", 19.3139, -98.2404),
    ("s3", "site-sim-102", 19.4326, -99.1332),
    ("s4", "site-sim-103", 19.2826, -99.6557),
    ("s5", "encima", 18.40, -98.72),
]

VELOCIDADES = [3.6, 4.0, 4.5]


def _mismo_plan(v_s: float, sismo: tuple) -> tuple[list, list]:
    clave, mag, lat, lon, prof = sismo
    v_p_e, v_s_e = edge.velocidades(v_s)
    v_p_n, v_s_n = NUBE.velocidades(v_s)
    assert (v_p_e, v_s_e) == (v_p_n, v_s_n), "las velocidades ya divergen"

    del_edge = edge.plan_de_arribos(
        edge.Sismo(clave, mag, lat, lon, prof, v_s_e, v_p_e),
        [edge.Estacion(*e) for e in ESTACIONES],
    )
    de_la_nube = NUBE.plan_de_arribos(
        NUBE.Sismo(clave, mag, lat, lon, prof, v_s_n, v_p_n),
        [NUBE.Estacion(*e) for e in ESTACIONES],
    )
    return del_edge, de_la_nube


@pytest.mark.parametrize("v_s", VELOCIDADES)
@pytest.mark.parametrize("sismo", SISMOS, ids=[s[0] for s in SISMOS])
def test_los_dos_espejos_dan_EXACTAMENTE_lo_mismo(sismo: tuple, v_s: float) -> None:
    """Igualdad de bits, no tolerancia: son las mismas operaciones en el mismo orden."""
    del_edge, de_la_nube = _mismo_plan(v_s, sismo)
    assert len(del_edge) == len(de_la_nube) == len(ESTACIONES)
    for a, b in zip(del_edge, de_la_nube, strict=True):
        assert a.site_code == b.site_code, "el ORDEN del plan difiere entre los espejos"
        assert a.epi_km == b.epi_km
        assert a.hypo_km == b.hypo_km
        assert a.t_p_s == b.t_p_s
        assert a.t_s_s == b.t_s_s
        assert a.pga_g == b.pga_g


def test_la_razon_vp_vs_es_la_misma_constante() -> None:
    assert edge.RAZON_VP_VS == NUBE.RAZON_VP_VS == math.sqrt(3.0)


def test_los_cuatro_arribos_del_19_S_tambien_salen_en_el_EDGE() -> None:
    """La cifra de la ficha, medida contra el espejo que la va a publicar.

    El de la nube ya la comprueba en `api/tests/replay/test_plan.py`; si solo se
    comprobara allí, el simulador podría publicar la rampa en otro instante y la
    demostración saldría descoordinada sin que ninguna suite lo dijera.
    """
    v_p, v_s = edge.velocidades(4.0)
    sismo = edge.Sismo("USGS-2017-09-19-PUE", 7.1, 18.5499, -98.4887, 48.0, v_s, v_p)
    plan = {
        a.site_code: a
        for a in edge.plan_de_arribos(sismo, [edge.Estacion(*e) for e in ESTACIONES[:4]])
    }
    for code, esperado in (
        ("site-dev", 19.6),
        ("site-sim-101", 25.3),
        ("site-sim-102", 32.1),
        ("site-sim-103", 38.7),
    ):
        assert abs(plan[code].t_s_s - esperado) < 0.1, code


def test_una_velocidad_no_positiva_se_RECHAZA_en_los_dos() -> None:
    for modulo in (edge, NUBE):
        with pytest.raises(ValueError):
            modulo.velocidades(0.0)
