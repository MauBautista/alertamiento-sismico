"""La duración instrumental de la sacudida (T-3.14).

La ficha pide **medida, no estimada, con su definición escrita**. Estos tests fijan las tres
cosas: que se mide de la onda, que la definición es D5-95 sobre Intensidad de Arias, y que
cuando no se puede medir **lo dice** en vez de devolver un cero que se leería como «no
tembló».
"""

from __future__ import annotations

import math

from takab_api.dictamen.duracion import FIN, INICIO, significativa


def _ruido(n: int, amplitud: float = 100.0, semilla: int = 7) -> list[int]:
    """Ruido determinista, sin depender de `random` ni de numpy."""
    salida, x = [], semilla
    for _ in range(n):
        x = (x * 1103515245 + 12345) % 2147483648
        salida.append(int((x / 2147483648 - 0.5) * 2 * amplitud))
    return salida


def _sacudida(*, sps: float, silencio_s: float, evento_s: float, cola_s: float) -> list[int]:
    """Silencio · sacudida fuerte · silencio. La sacudida dura `evento_s`."""
    return (
        _ruido(int(silencio_s * sps), 1.0, semilla=1)
        + _ruido(int(evento_s * sps), 5000.0, semilla=2)
        + _ruido(int(cola_s * sps), 1.0, semilla=3)
    )


# ----------------------------------------------------------------- lo que mide


def test_mide_la_sacudida_y_NO_la_longitud_del_registro() -> None:
    """Es la prueba central: 120 s de registro con 20 s de sacudida en medio."""
    d = significativa(
        _sacudida(sps=100, silencio_s=50, evento_s=20, cola_s=50), sample_rate=100, canal="EHZ"
    )

    assert d is not None
    # D5-95 recorta las colas de baja energía: cae cerca de los 20 s, no de los 120.
    assert 18 <= d.segundos <= 22, d.segundos
    assert 45 <= d.desde_s <= 52
    assert d.canal == "EHZ"


def test_la_ventana_empieza_y_acaba_DENTRO_de_la_sacudida() -> None:
    d = significativa(
        _sacudida(sps=100, silencio_s=30, evento_s=10, cola_s=60), sample_rate=100, canal="EHN"
    )

    assert d is not None
    assert d.desde_s >= 29 and d.hasta_s <= 41


# ------------------------------------------------- la trampa que la haría inútil


def test_UN_OFFSET_DE_CONTINUA_NO_CAMBIA_EL_RESULTADO() -> None:
    """El waveform crudo del RS4D trae ~3.8 millones de cuentas de continua (medido en el
    gabinete el 2026-08-01). Sin quitarla, `∫a²dt` lo domina una constante, la energía se
    acumula casi lineal y D5-95 devuelve el 90 % de la ventana **sea cual sea el sismo**:
    un número que parece razonable y describe la longitud del registro."""
    limpia = _sacudida(sps=100, silencio_s=40, evento_s=15, cola_s=40)
    con_offset = [s + 3_770_000 for s in limpia]

    a = significativa(limpia, sample_rate=100, canal="EHZ")
    b = significativa(con_offset, sample_rate=100, canal="EHZ")

    assert a is not None and b is not None
    assert math.isclose(a.segundos, b.segundos, abs_tol=0.05)
    # Y la comprobación que hace que este test valga: sin quitar la media daría ~86 s.
    assert b.segundos < 30, "el offset se está colando en la medida"


def test_la_medida_es_INVARIANTE_DE_ESCALA_y_por_eso_sirve_sobre_cuentas() -> None:
    """Es lo que permite medir esto sin la respuesta instrumental: D5-95 sale de una
    FRACCIÓN de la energía, y el factor de calibración se cancela al normalizar."""
    base = _sacudida(sps=100, silencio_s=20, evento_s=10, cola_s=20)
    amplificada = [s * 37 for s in base]

    a = significativa(base, sample_rate=100, canal="EHZ")
    b = significativa(amplificada, sample_rate=100, canal="EHZ")

    assert a is not None and b is not None
    assert math.isclose(a.segundos, b.segundos, abs_tol=1e-9)
    assert (a.desde_s, a.hasta_s) == (b.desde_s, b.hasta_s)


# ------------------------------------------------- cuando NO se puede medir


def test_una_traza_plana_devuelve_None_y_no_un_cero() -> None:
    """Un `0.0 s` en un dictamen se lee como «no tembló». Lo que pasó es que no se pudo
    medir, y son cosas distintas: quien llama lo convierte en literal de ausencia."""
    assert significativa([500] * 6000, sample_rate=100, canal="EHZ") is None


def test_una_traza_demasiado_corta_devuelve_None() -> None:
    assert significativa([1], sample_rate=100, canal="EHZ") is None
    assert significativa([], sample_rate=100, canal="EHZ") is None


def test_una_frecuencia_de_muestreo_imposible_devuelve_None() -> None:
    """Un `sample_rate` de 0 vendría de un miniSEED corrupto; dividir por él reventaría."""
    assert significativa(_ruido(1000, 500.0), sample_rate=0, canal="EHZ") is None


# ------------------------------------------------------------ cómo se declara


def test_la_etiqueta_NOMBRA_la_definicion_y_nunca_dice_duracion_a_secas() -> None:
    """Comparar un D5-95 con una duración «bracketed» es comparar cosas distintas, y la
    única defensa es que el número lleve su definición pegada."""
    d = significativa(
        _sacudida(sps=100, silencio_s=5, evento_s=8, cola_s=5), sample_rate=100, canal="EHZ"
    )

    assert d is not None
    assert d.etiqueta.startswith("D5-95 · ")
    assert d.etiqueta.endswith(" s")


def test_las_fracciones_son_las_de_la_convencion() -> None:
    """5–75 % existe y da numeros sistematicamente menores. Cual se uso viaja con el dato."""
    assert (INICIO, FIN) == (0.05, 0.95)
