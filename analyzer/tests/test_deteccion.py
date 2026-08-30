"""El adaptador del detector y la curva de aforo (T-3.12).

Nada de esto descarga un peso: es un criterio literal de la ficha, y es lo que permite que
el motor entero corra en CI.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from takab_cctv.aforo import a_muestras, contar, dentro, serie_de
from takab_cctv.detector import (
    CLASE_PERSONA,
    Caja,
    DetectorBackend,
    DetectorFalso,
    filtrar,
    nms,
)

T0 = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)
CUADRO = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]


# ------------------------------------------------------------- el adaptador


def test_el_doble_cumple_el_protocolo() -> None:
    """Si `DetectorBackend` crece, este test cae antes que el pipeline."""
    assert isinstance(DetectorFalso(), DetectorBackend)


def test_solo_se_mira_la_clase_persona() -> None:
    """Menos clases es menos superficie de PII y menos que explicarle a un cliente."""
    assert CLASE_PERSONA == 0


def test_el_punto_que_decide_la_zona_son_los_PIES_y_no_el_centro() -> None:
    """Una persona de pie ocupa una caja alta y su centro cae por encima del suelo. Con el
    centro, alguien parado justo fuera del polígono se contaría dentro — y el error crece
    con lo cerca que esté de la cámara."""
    de_pie = Caja(100, 100, 140, 300, 0.9)
    assert de_pie.pies == (120.0, 300)
    assert de_pie.centro == (120.0, 200.0)


def test_nms_colapsa_la_misma_persona_detectada_dos_veces() -> None:
    a, b = Caja(0, 0, 10, 20, 0.9), Caja(1, 1, 11, 21, 0.8)
    assert len(nms([a, b])) == 1
    assert nms([a, b])[0].confianza == 0.9  # se queda la más segura


def test_nms_no_junta_a_dos_personas_distintas() -> None:
    assert len(nms([Caja(0, 0, 10, 20, 0.9), Caja(50, 50, 60, 70, 0.9)])) == 2


def test_el_umbral_de_confianza_prefiere_no_inventar_gente() -> None:
    """Un aforo inflado exagera la evacuación, y un reporte que exagera es un reporte que
    nadie vuelve a creer."""
    cajas = [Caja(0, 0, 10, 20, 0.9), Caja(50, 50, 60, 70, 0.2)]
    assert len(filtrar(cajas)) == 1


# ------------------------------------------------------------------ la zona


def test_point_in_polygon_en_los_dos_lados() -> None:
    assert dentro((0.5, 0.5), CUADRO) is True
    assert dentro((0.95, 0.5), CUADRO) is False
    assert dentro((0.5, 0.05), CUADRO) is False


def test_la_zona_deja_fuera_a_quien_pasa_por_la_calle() -> None:
    en_zona = Caja(400, 400, 440, 500, 0.9)
    en_la_calle = Caja(10, 10, 50, 60, 0.9)
    assert contar([en_zona, en_la_calle], ancho=1000, alto=1000, zona=CUADRO) == 1


def test_sin_zona_se_cuenta_TODO_el_encuadre() -> None:
    """No es lo mismo, y por eso `Conteo` lo declara: sin polígono el número incluye a los
    peatones, y un aforo inflado por la calle se leería como una evacuación multitudinaria."""
    cajas = [Caja(400, 400, 440, 500, 0.9), Caja(10, 10, 50, 60, 0.9)]
    assert contar(cajas, ancho=1000, alto=1000, zona=None) == 2


# ---------------------------------------------------------------- la pasada


def _fotogramas(cuantos: int) -> list[tuple[datetime, bytes]]:
    return [(T0 + timedelta(seconds=i * 10), b"jpeg") for i in range(cuantos)]


def test_la_curva_sale_con_su_procedencia() -> None:
    """El reporte tiene que poder declarar CON QUÉ se contó: un aforo sin decir qué modelo
    lo produjo no es auditable, y `T-3.12.d` puede cambiar el default."""
    guion = [[Caja(400, 400, 440, 500, 0.9)] * n for n in (0, 3, 7)]
    curva = serie_de(_fotogramas(3), DetectorFalso(guion), ancho=1000, alto=1000, zona=CUADRO)
    assert [c.n for c in curva] == [0, 1, 1]  # NMS colapsa cajas idénticas: son la misma
    assert all(c.detector == "falso" and c.con_zona for c in curva)


def test_la_curva_cuenta_personas_DISTINTAS() -> None:
    guion = [
        [Caja(200, 200, 240, 300, 0.9), Caja(500, 500, 540, 600, 0.9)],
        [Caja(200, 200, 240, 300, 0.9)],
    ]
    curva = serie_de(_fotogramas(2), DetectorFalso(guion), ancho=1000, alto=1000, zona=CUADRO)
    assert [c.n for c in curva] == [2, 1]


def test_un_fotograma_roto_NO_corta_la_curva() -> None:
    """El goteo viene de una cámara por red: un JPEG truncado no puede costar el incidente
    entero. Una muestra menos en una serie de cientos no mueve `t90`; un análisis abortado sí."""

    class _Frágil(DetectorFalso):
        def detectar(self, imagen: bytes) -> list[Caja]:
            self.llamadas += 1
            if self.llamadas == 2:
                raise ValueError("JPEG truncado")
            return [Caja(400, 400, 440, 500, 0.9)]

    curva = serie_de(_fotogramas(4), _Frágil(), ancho=1000, alto=1000, zona=CUADRO)
    assert len(curva) == 3  # se saltó el roto, no abortó


def test_la_curva_se_adapta_a_lo_que_consume_el_motor() -> None:
    curva = serie_de(_fotogramas(2), DetectorFalso([[], []]), ancho=100, alto=100)
    muestras = a_muestras(curva)
    assert [m.ts for m in muestras] == [c.ts for c in curva]
