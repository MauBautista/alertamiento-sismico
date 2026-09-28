"""[T-9.51 · D-44] La superficie ESTIMADA: la ley más los residuos, encogidos.

Lo que se fija, en lógica pura:

1. **No hay superficie sin su ancla.** Sin epicentro con magnitud no hay ley; sin una
   sola medida no hay mapa de la sacudida (la regla de `calculo.py`, «sin una sola
   medida no hay capa 2»); y sin un sensor CALIBRADO que la ajuste, sería puro modelo
   rotulado como estimación de lo medido.
2. **Lejos de las estaciones manda la ley.** El residuo se encoge a cero: la
   estimación no inventa una sacudida donde nadie midió.
3. **Cerca de una estación, la superficie se inclina hacia lo medido**, en la
   dirección del residuo.
4. **Un sensor sin calibrar no mueve la superficie.** Cuenta en el rótulo (N) y no
   en el ajuste (M).
5. **La zona AJUSTADA es la que está a menos de 2L de un sensor calibrado.**
6. Determinista, acotada a 96 celdas por lado, fila 0 = norte, y viaja a JSON y de
   vuelta sin perder nada.
"""

from __future__ import annotations

import math

import pytest

from takab_api.geo import haversine_km, hypo_km, pga_law_g
from takab_api.shakemap import superficie as S

#: Un M6.5 a 60 km de profundidad frente a la costa de Guerrero, y la red de Puebla.
EPI = S.EpicentroLey(lat=17.0, lon=-99.5, depth_km=60.0, magnitud=6.5)
PUEBLA = (19.05, -98.22)


def _ley_en(lat: float, lon: float) -> float:
    return pga_law_g(EPI.magnitud, hypo_km(haversine_km(EPI.lat, EPI.lon, lat, lon), EPI.depth_km))


def _est(lat: float, lon: float, factor: float | None, *, calibrado: bool = True) -> S.Estacion:
    """Una estación que midió `factor` veces lo que la ley predice en su sitio."""
    pga = None if factor is None else _ley_en(lat, lon) * factor
    return S.Estacion(lat=lat, lon=lon, pga_g=pga, calibrado=calibrado)


def _celda_mas_cercana(sup: S.Superficie, lat: float, lon: float) -> tuple[int, int]:
    mejor, dist = (0, 0), math.inf
    for i in range(sup.alto):
        for j in range(sup.ancho):
            la, lo = sup.centro(i, j)
            d = haversine_km(la, lo, lat, lon)
            if d < dist:
                mejor, dist = (i, j), d
    return mejor


# ------------------------------------------------------------------ sin ancla no hay superficie


def test_sin_epicentro_no_hay_superficie() -> None:
    sup, motivo = S.estima([_est(*PUEBLA, 2.0)], None)
    assert (sup, motivo) == (None, S.MOTIVO_SIN_EPICENTRO)


def test_sin_magnitud_tampoco() -> None:
    sin_m = S.EpicentroLey(lat=EPI.lat, lon=EPI.lon, depth_km=EPI.depth_km, magnitud=None)
    sup, motivo = S.estima([_est(*PUEBLA, 2.0)], sin_m)
    assert (sup, motivo) == (None, S.MOTIVO_SIN_EPICENTRO)


def test_sin_una_sola_medida_no_hay_superficie() -> None:
    sup, motivo = S.estima([_est(*PUEBLA, None)], EPI)
    assert (sup, motivo) == (None, S.MOTIVO_SIN_MEDIDAS)


def test_sin_un_sensor_calibrado_no_hay_superficie() -> None:
    sup, motivo = S.estima([_est(*PUEBLA, 2.0, calibrado=False)], EPI)
    assert (sup, motivo) == (None, S.MOTIVO_SIN_CALIBRADOS)


# ------------------------------------------------------------------ la forma


def test_lejos_de_toda_estacion_manda_la_ley() -> None:
    sup, _ = S.estima([_est(*PUEBLA, 4.0)], EPI)
    # La esquina más alejada de Puebla está a más de 6L: el residuo pesa e^-18.
    for i, j in ((0, 0), (0, sup.ancho - 1), (sup.alto - 1, 0), (sup.alto - 1, sup.ancho - 1)):
        la, lo = sup.centro(i, j)
        if haversine_km(la, lo, *PUEBLA) > 6 * sup.escala_km:
            assert sup.pga_g[i][j] == pytest.approx(_ley_en(la, lo), rel=1e-4)


@pytest.mark.parametrize(("factor", "sube"), [(4.0, True), (0.25, False)])
def test_cerca_de_la_estacion_se_inclina_hacia_lo_medido(factor: float, sube: bool) -> None:
    sup, _ = S.estima([_est(*PUEBLA, factor)], EPI)
    i, j = _celda_mas_cercana(sup, *PUEBLA)
    la, lo = sup.centro(i, j)
    razon = sup.pga_g[i][j] / _ley_en(la, lo)
    assert (razon > 1.5) if sube else (razon < 1 / 1.5)
    # Encogida: nunca llega del todo a lo medido.
    assert (razon < factor) if sube else (razon > factor)


def test_un_sensor_SIN_calibrar_no_mueve_la_superficie() -> None:
    base, _ = S.estima([_est(*PUEBLA, 2.0)], EPI)
    con_otro, _ = S.estima([_est(*PUEBLA, 2.0), _est(19.2, -98.0, 50.0, calibrado=False)], EPI)
    assert con_otro.pga_g == base.pga_g
    assert con_otro.ajustada == base.ajustada
    assert (con_otro.n_sensores, con_otro.n_calibrados) == (2, 1)


def test_la_zona_AJUSTADA_es_la_de_menos_de_2L() -> None:
    sup, _ = S.estima([_est(*PUEBLA, 2.0)], EPI)
    vistas = {True: 0, False: 0}
    for i in range(sup.alto):
        for j in range(sup.ancho):
            d = haversine_km(*sup.centro(i, j), *PUEBLA)
            if abs(d - 2 * sup.escala_km) < 1.0:
                continue  # el borde exacto depende del redondeo de la celda
            assert sup.ajustada[i][j] == (d < 2 * sup.escala_km)
            vistas[sup.ajustada[i][j]] += 1
    assert vistas[True] and vistas[False], "la malla no tenía las dos zonas"


# ------------------------------------------------------------------ la malla


def test_la_malla_cabe_en_96_por_lado_y_contiene_a_las_estaciones() -> None:
    lejos = _est(20.1, -96.9, 1.0)  # Veracruz, a ~180 km de Puebla
    sup, _ = S.estima([_est(*PUEBLA, 2.0), lejos], EPI)
    assert 1 <= sup.ancho <= 96 and 1 <= sup.alto <= 96
    assert max(sup.ancho, sup.alto) == 96
    for est in (PUEBLA, (20.1, -96.9)):
        assert sup.sur < est[0] < sup.norte and sup.oeste < est[1] < sup.este


def test_la_fila_cero_es_el_NORTE() -> None:
    sup, _ = S.estima([_est(*PUEBLA, 2.0)], EPI)
    assert sup.centro(0, 0)[0] > sup.centro(sup.alto - 1, 0)[0]
    assert sup.centro(0, 0)[1] < sup.centro(0, sup.ancho - 1)[1]


def test_determinista_y_de_ida_y_vuelta_a_JSON() -> None:
    estaciones = [_est(*PUEBLA, 2.0), _est(19.3, -98.4, 0.5)]
    a, _ = S.estima(estaciones, EPI)
    b, _ = S.estima(estaciones, EPI)
    assert a.to_json() == b.to_json()
    vuelta = S.Superficie.from_json(a.to_json())
    assert vuelta.to_json() == a.to_json()
    # Viaja en micro-g enteros: medio micro-g es lo que se pierde, y a propósito.
    assert vuelta.pga_g[3][5] == pytest.approx(a.pga_g[3][5], abs=5e-7)


def test_el_rotulo_lleva_lo_que_dice_D44() -> None:
    sup, _ = S.estima([_est(*PUEBLA, 2.0), _est(19.3, -98.4, None)], EPI)
    j = sup.to_json()
    assert (j["n_sensores"], j["n_calibrados"]) == (1, 1)
    assert j["ley"] == "ATTEN-LAW v1"
    assert "Wald" in j["cita_mmi"]
    assert j["escala_km"] == 15.0
