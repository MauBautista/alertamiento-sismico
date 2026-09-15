"""[T-7.14] El plan de arribos, contra un sismo MEDIDO.

La prueba que vale es la primera: los cuatro arribos de referencia del 19-S-2017
que fija `TASKS.md`. No son un valor esperado inventado en el test —el defecto de
una prueba escrita después del código—: son la cifra que la ficha declara y a la
que están ancladas las velocidades por defecto.

Lo demás fija las propiedades que hacen que el plan se pueda mirar sin
verificarlo a mano: más lejos llega más tarde y sacude menos, la profundidad
cuenta, el orden es el de la coreografía y `v_p > v_s` siempre.
"""

from __future__ import annotations

import math

import pytest

from takab_api.replay.plan import (
    RAZON_VP_VS,
    Estacion,
    Sismo,
    arribo,
    plan_de_arribos,
    velocidades,
)

# Solución USGS del 19-S-2017 (`USGS-2017-09-19-PUE` en el catálogo).
V_P, V_S = velocidades(4.0)
DIECINUEVE_S = Sismo(
    catalog_key="USGS-2017-09-19-PUE",
    magnitude=7.1,
    lat=18.5499,
    lon=-98.4887,
    depth_km=48.0,
    v_s_km_s=V_S,
    v_p_km_s=V_P,
)

#: Las cuatro estaciones de la demostración: la real de Puebla y las tres
#: simuladas de `db/seeds/demo_red.sql`.
RED = [
    Estacion("11111111-1111-1111-1111-111111111111", "site-dev", 19.05, -98.22),
    Estacion("22222222-2222-2222-2222-222222222222", "site-sim-101", 19.3139, -98.2404),
    Estacion("33333333-3333-3333-3333-333333333333", "site-sim-102", 19.4326, -99.1332),
    Estacion("44444444-4444-4444-4444-444444444444", "site-sim-103", 19.2826, -99.6557),
]

#: Lo que declara la ficha `T-7.14`, en segundos desde el origen.
REFERENCIA_S = {
    "site-dev": 19.6,  # Puebla
    "site-sim-101": 25.3,  # Tlaxcala
    "site-sim-102": 32.1,  # CDMX
    "site-sim-103": 38.7,  # Toluca
}


def test_los_cuatro_arribos_del_19_S_SALEN():
    """±0.1 s contra la cifra de la ficha. Es la prueba de que las velocidades
    por defecto no son un número bonito: reproducen un sismo que ocurrió."""
    plan = {a.site_code: a for a in plan_de_arribos(DIECINUEVE_S, RED)}
    for code, esperado in REFERENCIA_S.items():
        obtenido = plan[code].t_s_s
        assert abs(obtenido - esperado) < 0.1, (
            f"{code}: la onda S llega a {obtenido:.2f} s y la ficha dice {esperado} s"
        )


def test_la_P_llega_ANTES_que_la_S_en_todas():
    for a in plan_de_arribos(DIECINUEVE_S, RED):
        assert a.t_p_s < a.t_s_s, a.site_code


def test_el_plan_va_ordenado_POR_ARRIBO_y_no_por_nombre():
    """Es el orden de la coreografía; alfabético obligaría a reordenar a cada
    consumidor y alguno se olvidaría."""
    plan = plan_de_arribos(DIECINUEVE_S, RED)
    assert [a.site_code for a in plan] == [
        "site-dev",
        "site-sim-101",
        "site-sim-102",
        "site-sim-103",
    ]
    assert plan == sorted(plan, key=lambda a: a.t_p_s)


def test_mas_lejos_es_mas_tarde_y_MENOS_sacudida():
    plan = plan_de_arribos(DIECINUEVE_S, RED)
    for antes, despues in zip(plan, plan[1:], strict=False):
        assert despues.hypo_km > antes.hypo_km
        assert despues.t_s_s > antes.t_s_s
        assert despues.pga_g < antes.pga_g, "la atenuación va al revés"


def test_la_PROFUNDIDAD_cuenta_y_su_ausencia_degrada_a_la_epicentral():
    """Un sismo a 48 km bajo la estación no llega instantáneamente."""
    justo_debajo = Estacion("x", "encima", DIECINUEVE_S.lat, DIECINUEVE_S.lon)
    a = arribo(DIECINUEVE_S, justo_debajo)
    assert a.epi_km < 0.001
    assert abs(a.hypo_km - 48.0) < 0.001
    assert a.t_s_s > 0

    somero = Sismo(**{**DIECINUEVE_S.__dict__, "depth_km": None})
    b = arribo(somero, justo_debajo)
    assert b.hypo_km == pytest.approx(b.epi_km), "sin profundidad no se puede inventar una"


def test_la_razon_vp_vs_es_la_de_POISSON_y_no_dos_numeros_sueltos():
    v_p, v_s = velocidades(4.0)
    assert v_s == 4.0
    assert v_p == pytest.approx(4.0 * math.sqrt(3.0))
    assert RAZON_VP_VS == pytest.approx(1.7320508, abs=1e-6)


def test_una_velocidad_no_positiva_se_RECHAZA():
    """Degradar a un default aquí produciría un plan plausible y falso."""
    for mala in (0.0, -1.0):
        with pytest.raises(ValueError):
            velocidades(mala)
