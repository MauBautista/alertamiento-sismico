"""Banda de sacudida MEDIDA: la que pinta el mapa por edificio."""

from __future__ import annotations

import pytest

from takab_api.felt import (
    DEFAULT_THRESHOLDS,
    FELT_NORMAL,
    FELT_TRIP,
    FELT_UNKNOWN,
    FELT_WATCH,
    Thresholds,
    felt_band,
    thresholds_from_row,
)


def test_sin_medida_es_unknown_no_normal() -> None:
    """Ausencia de dato NO es "no se movió" (regla de oro 7)."""
    assert felt_band(None, None) == FELT_UNKNOWN


@pytest.mark.parametrize(
    ("pga", "esperado"),
    [
        (0.0, FELT_NORMAL),
        (0.039, FELT_NORMAL),
        (0.040, FELT_WATCH),  # == watch ⇒ cautela (límite inclusivo, como el edge)
        (0.059, FELT_WATCH),
        (0.060, FELT_TRIP),  # == trip ⇒ disparo
        (0.567, FELT_TRIP),  # el pico real medido en Sitio Dev Puebla (2026-07-10)
    ],
)
def test_bandas_por_pga_con_umbrales_default(pga: float, esperado: str) -> None:
    assert felt_band(pga, None) == esperado


def test_pgv_dispara_por_su_cuenta_aunque_el_pga_no_llegue() -> None:
    """PGA y PGV se comparan por separado: cualquiera que exceda basta."""
    assert felt_band(0.0, DEFAULT_THRESHOLDS.pgv_trip_cms) == FELT_TRIP
    assert felt_band(0.0, DEFAULT_THRESHOLDS.pgv_watch_cms) == FELT_WATCH


def test_los_umbrales_del_rule_set_mandan_sobre_el_default() -> None:
    """Un edificio con umbrales propios se colorea con LOS SUYOS, no con los del edge."""
    laxos = Thresholds(pga_watch_g=0.5, pga_trip_g=1.0, pgv_watch_cms=50.0, pgv_trip_cms=99.0)
    # 0.10 g dispararía con los default (trip=0.060) pero aquí ni llega a cautela.
    assert felt_band(0.10, None, laxos) == FELT_NORMAL
    assert felt_band(0.10, None) == FELT_TRIP


def test_thresholds_from_row_rellena_campo_a_campo() -> None:
    """Un rule_set a medias no anula los demás umbrales: cada hueco cae a su default."""
    t = thresholds_from_row(
        pga_watch_g=0.01, pga_trip_g=None, pgv_watch_cms=None, pgv_trip_cms=None
    )
    assert t.pga_watch_g == 0.01
    assert t.pga_trip_g == DEFAULT_THRESHOLDS.pga_trip_g
    assert t.pgv_watch_cms == DEFAULT_THRESHOLDS.pgv_watch_cms
    assert t.pgv_trip_cms == DEFAULT_THRESHOLDS.pgv_trip_cms


def test_los_default_son_los_del_edge() -> None:
    """Si el edge cambia su banda hospital, este test obliga a cambiarla aquí también."""
    assert (DEFAULT_THRESHOLDS.pga_watch_g, DEFAULT_THRESHOLDS.pga_trip_g) == (0.040, 0.060)
    assert (DEFAULT_THRESHOLDS.pgv_watch_cms, DEFAULT_THRESHOLDS.pgv_trip_cms) == (2.0, 4.0)
