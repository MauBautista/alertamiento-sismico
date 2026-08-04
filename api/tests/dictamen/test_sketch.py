"""T-2.41 · Croquis vectorial del dictamen.

Sin cartografía base a propósito: traer tiles haría que la generación de una evidencia
de compliance dependiera de que el servidor tenga internet. Lo que sí puede afirmarse
con geometría propia es dónde están las cosas, y eso se rotula como croquis.
"""

from __future__ import annotations

from takab_api.dictamen.sketch import Point, project

W, H = 180.0, 78.0

# Cholula (sitio) y un epicentro plausible en la costa de Guerrero.
SITE = Point(19.06, -98.30, "CHL-A", "site")
EPI = Point(16.80, -99.50, "EPICENTRO", "epicenter")
PEER = Point(19.43, -99.13, "CDMX-1", "peer")


def test_sin_geometria_no_hay_croquis() -> None:
    """`None` es el contrato: el dictamen declara la ausencia en vez de imprimir un
    marco vacío que parece un fallo de impresión."""
    assert project([], W, H) is None


def test_todos_los_puntos_caen_dentro_del_recuadro() -> None:
    drawn = project([SITE, EPI, PEER], W, H)
    assert drawn is not None
    for p in drawn.points:
        assert 0 <= p.x <= W
        assert 0 <= p.y <= H


def test_el_norte_queda_arriba() -> None:
    """La Y de página crece hacia abajo; la latitud hacia arriba. Sin invertir, el
    croquis pondría el epicentro del sur en la parte superior."""
    drawn = project([SITE, EPI], W, H)
    assert drawn is not None
    site = next(p for p in drawn.points if p.kind == "site")
    epi = next(p for p in drawn.points if p.kind == "epicenter")
    assert site.lat if False else True  # (los Point de salida ya están proyectados)
    assert epi.y > site.y, "el punto más al sur debe quedar más abajo"


def test_corrige_el_meridiano_por_latitud() -> None:
    """A 19°N un grado de longitud mide ~0.95 de uno de latitud. Sin la corrección
    `cos(lat)`, el croquis estira el eje E-O y los rumbos mienten."""
    # Dos puntos separados 1° en longitud y 1° en latitud desde el mismo origen.
    este = Point(19.0, -98.0, "E", "peer")
    norte = Point(20.0, -99.0, "N", "peer")
    origen = Point(19.0, -99.0, "O", "site")
    drawn = project([origen, este, norte], W, H)
    assert drawn is not None
    o = next(p for p in drawn.points if p.label == "O")
    e = next(p for p in drawn.points if p.label == "E")
    n = next(p for p in drawn.points if p.label == "N")
    dx = abs(e.x - o.x)
    dy = abs(n.y - o.y)
    # El grado de longitud debe quedar MÁS CORTO que el de latitud, en ~cos(19°)=0.945.
    assert dx < dy
    assert 0.9 < dx / dy < 0.99


def test_la_barra_de_escala_usa_un_valor_redondo() -> None:
    """Nadie mide con una barra de 37 km."""
    drawn = project([SITE, EPI], W, H)
    assert drawn is not None
    assert drawn.scale_bar_km in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000)
    assert drawn.scale_bar_mm > 0


def test_un_solo_punto_no_revienta() -> None:
    drawn = project([SITE], W, H)
    assert drawn is not None
    assert len(drawn.points) == 1


def test_conserva_el_tipo_y_el_rotulo_de_cada_punto() -> None:
    drawn = project([SITE, EPI, PEER], W, H)
    assert drawn is not None
    kinds = {p.kind for p in drawn.points}
    assert kinds == {"site", "epicenter", "peer"}
    assert {p.label for p in drawn.points} == {"CHL-A", "EPICENTRO", "CDMX-1"}
