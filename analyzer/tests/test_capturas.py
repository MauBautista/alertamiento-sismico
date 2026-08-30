"""Los cuatro fotogramas del reporte (T-3.12)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from takab_cctv.capturas import PAPELES, elegir
from takab_cctv.metricas import Muestra, calcular

T0 = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
NORMAL = [0, 2, 8, 20, 35, 40, 40, 38, 30, 10, 4, 3, 2]


def _serie() -> list[Muestra]:
    return [
        Muestra(T0 - timedelta(seconds=40), 1),
        Muestra(T0 - timedelta(seconds=20), 1),
    ] + [Muestra(T0 + timedelta(seconds=i * 10), n) for i, n in enumerate(NORMAL)]


def _por_papel(serie, t0=T0, **kw) -> dict:
    evac = calcular(serie, t0=t0, **kw)
    return {e.papel: e for e in elegir(serie, evac, t0=t0)}


def test_salen_los_cuatro_papeles_que_pidio_Mauricio() -> None:
    elecciones = _por_papel(_serie())
    assert tuple(elecciones) == PAPELES


def test_el_antes_cae_dentro_del_pre_roll() -> None:
    assert _por_papel(_serie())["pre"].ts == T0 - timedelta(seconds=30)


def test_egress_es_el_MAYOR_FLUJO_y_no_el_punto_medio() -> None:
    """El punto medio entre la señal y el pico caería a menudo en un momento sin nadie
    moviéndose. Ésta es la foto de la evacuación OCURRIENDO."""
    # La mayor subida de NORMAL es 20→35 (+15 en 10 s), que acaba en t0+40 — más tarde que
    # el punto medio hasta el pico (t0+25), y ahí está la diferencia que este test defiende.
    assert _por_papel(_serie())["egress"].ts == T0 + timedelta(seconds=40)


def test_peak_coincide_con_el_aforo_maximo_y_lo_dice() -> None:
    e = _por_papel(_serie())["peak"]
    assert e.ts == T0 + timedelta(seconds=50)
    assert "40 personas" in e.razon


def test_reentry_es_el_inicio_del_reingreso() -> None:
    assert _por_papel(_serie())["reentry"].ts is not None


def test_sin_pre_roll_la_foto_del_antes_se_declara_ausente_con_su_razon() -> None:
    """Un hueco sin explicar se lee como un fallo del sistema."""
    sin = [Muestra(T0 + timedelta(seconds=i * 10), n) for i, n in enumerate(NORMAL)]
    e = _por_papel(sin)["pre"]
    assert e.ts is None
    assert "no cubre los segundos previos" in e.razon


def test_sin_curva_los_cuatro_papeles_existen_pero_vacios() -> None:
    """El reporte necesita las cuatro filas aunque no haya foto: una fila ausente se
    confunde con una sección que no se generó."""
    elecciones = _por_papel([])
    assert tuple(elecciones) == PAPELES
    assert all(e.ts is None and e.razon for e in elecciones.values())


def test_si_el_aforo_nunca_sube_no_se_inventa_una_foto_de_salida() -> None:
    plano = [Muestra(T0 + timedelta(seconds=i * 10), 20) for i in range(6)]
    e = _por_papel(plano)["egress"]
    assert e.ts is None
    assert "nunca subió" in e.razon


def test_si_no_se_observo_el_reingreso_se_dice() -> None:
    sin_bajada = [
        Muestra(T0 - timedelta(seconds=30), 1),
        *[Muestra(T0 + timedelta(seconds=i * 10), n) for i, n in enumerate([0, 10, 30, 40, 40])],
    ]
    e = _por_papel(sin_bajada)["reentry"]
    assert e.ts is None
    assert "no se observó" in e.razon
