"""[T-7.14] Cuándo llega la onda a cada estación. LÓGICA PURA.

Dado un sismo del catálogo (epicentro, profundidad, magnitud) y las estaciones de
la red, devuelve para cada una la distancia, el arribo de P, el arribo de S y la
PGA que cabe esperar. Sin base de datos, sin reloj, sin red: es una función de sus
argumentos, y por eso el simulador del edge puede llevar el mismo cálculo
(``edge/simulators/replay.py``) sin importar nada de la nube.

**Los tiempos se cuentan desde el ORIGEN del sismo**, no desde el pulso del WR-1.
Quien reproduce ancla el origen a `t0` y suma; quien compara con un sismo real
resta la hora de origen del catálogo. Mezclar los dos orígenes es el error que
haría llegar la onda antes que la alerta.

## Las dos velocidades, y por qué NO son las del cuórum

`correlation_v_s_km_s` vale 3.6 km/s y **no se toca**: allí la velocidad acota
cuán tarde puede llegar un arribo real, así que la elección conservadora es la
lenta —una velocidad alta cerraría la ventana antes de tiempo y perdería el
evento—. Aquí la pregunta es la contraria: *cuándo se espera* la onda, y la
respuesta conservadora no sirve; hace falta la mejor estimación.

Los defectos (`v_s = 4.0`, `v_p = 6.93`) están **anclados a un sismo medido**: los
cuatro arribos de referencia del 19-S-2017 que fija `TASKS.md` —Puebla +19.6 s,
Tlaxcala +25.3 s, CDMX +32.1 s, Toluca +38.7 s— salen de la solución USGS
(18.5499 N, −98.4887 W, 48 km) con distancia HIPOCENTRAL y `v_s = 4.0`, con un
error máximo de 0.08 s en las cuatro. Es un evento **intraplaca** a 48 km: la
energía viaja por la placa subducida y la velocidad aparente es mayor que los
3.5–3.6 km/s de la corteza. `v_p` se deriva con la razón √3 (4.0 × 1.7321), que es
la relación de Poisson estándar; no es un segundo número medido y por eso se
calcula en vez de escribirse.

Un `rule_set` con bloque `replay` pisa las dos por sitio (`v_p_km_s`, `v_s_km_s`):
reproducir un sismo cortical somero con la velocidad de uno intraplaca daría
arribos adelantados varios segundos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from takab_api.geo import haversine_km, hypo_km, pga_law_g

#: Razón v_p/v_s de un sólido de Poisson. `v_p` NO es un número medido aparte: es
#: éste por `v_s`. Escribir los dos a mano invita a que uno se mueva sin el otro.
RAZON_VP_VS = math.sqrt(3.0)


@dataclass(frozen=True)
class Sismo:
    """El evento del catálogo, ya resuelto. `depth_km` puede faltar."""

    catalog_key: str
    magnitude: float
    lat: float
    lon: float
    depth_km: float | None
    v_s_km_s: float
    v_p_km_s: float


@dataclass(frozen=True)
class Estacion:
    """Un sitio de la red. El código es lo que se enseña; el uuid, lo que se une."""

    site_id: str
    site_code: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Arribo:
    """Lo que le toca a una estación. Segundos DESDE EL ORIGEN del sismo."""

    site_id: str
    site_code: str
    epi_km: float
    hypo_km: float
    t_p_s: float
    t_s_s: float
    pga_g: float


def velocidades(v_s_km_s: float) -> tuple[float, float]:
    """``(v_p, v_s)`` a partir de la de corte. Un solo número de entrada."""
    if v_s_km_s <= 0:
        raise ValueError(f"v_s tiene que ser positiva: {v_s_km_s!r}")
    return v_s_km_s * RAZON_VP_VS, v_s_km_s


def arribo(sismo: Sismo, estacion: Estacion) -> Arribo:
    """El arribo en una estación. Determinista y sin estado."""
    epi = haversine_km(sismo.lat, sismo.lon, estacion.lat, estacion.lon)
    hipo = hypo_km(epi, sismo.depth_km)
    return Arribo(
        site_id=estacion.site_id,
        site_code=estacion.site_code,
        epi_km=epi,
        hypo_km=hipo,
        t_p_s=hipo / sismo.v_p_km_s,
        t_s_s=hipo / sismo.v_s_km_s,
        pga_g=pga_law_g(sismo.magnitude, hipo),
    )


def plan_de_arribos(sismo: Sismo, estaciones: list[Estacion]) -> list[Arribo]:
    """El plan entero, **ordenado por cuándo llega** y no por nombre.

    El orden es el de la coreografía: es lo que se pinta en el mapa y lo que
    publica el simulador. Ordenarlo alfabéticamente obligaría a cada consumidor a
    reordenarlo y alguno se olvidaría.
    """
    return sorted((arribo(sismo, e) for e in estaciones), key=lambda a: (a.t_p_s, a.site_code))
