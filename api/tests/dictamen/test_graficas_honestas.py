"""[T-7.39] Las cuatro gráficas del dictamen no decían lo que parecían.

Una figura de un documento pericial se lee a ojo: nadie comprueba el eje. Las
cuatro estaban bien calculadas y describían otra cosa — que es exactamente la
familia de defectos de `T-7.38`, con números en vez de frases.

Se prueban por PROPIEDAD sobre las funciones puras, no raspando el PDF: de una
gráfica no se puede leer una cadena, y comparar bytes pasa en verde sobre
cualquier cambio porque la portada imprime `content_sha256()`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from takab_api.dictamen import sketch
from takab_api.dictamen.builder import MAX_FFT_SAMPLES, _spectrum
from takab_api.dictamen.model import NO_SPECTRUM
from takab_api.dictamen.plot import scale_of

RATE = 100.0


@dataclass
class _Traza:
    samples: list[float]


def _con_sismo_al_final(hz_ruido: float, hz_sismo: float) -> _Traza:
    """60 s de ruido tranquilo y luego 60 s de sacudida, como sube el gabinete.

    `evidence_pre_s` vale 60 s de fábrica: a 100 sps, las 6000 primeras muestras
    de la traza son EXACTAMENTE el minuto anterior al evento.
    """
    n = int(RATE * 60)
    ruido = [0.3 * math.sin(2 * math.pi * hz_ruido * i / RATE) for i in range(n)]
    sismo = [40.0 * math.sin(2 * math.pi * hz_sismo * i / RATE) for i in range(n)]
    return _Traza(samples=ruido + sismo)


def test_el_espectro_se_calcula_sobre_LA_SACUDIDA() -> None:
    """EL DEFECTO: `samples[:6000]` con `evidence_pre_s = 60` a 100 sps es, punto
    por punto, el minuto ANTERIOR al sismo. El espectro que el papel presenta como
    contenido espectral del evento se calculaba sobre el ruido de fondo previo y
    no llegaba a tocar la sacudida.
    """
    _, peak_hz = _spectrum(_con_sismo_al_final(hz_ruido=2.0, hz_sismo=11.0), RATE)
    assert peak_hz is not None
    assert abs(peak_hz - 11.0) < 0.5, (
        f"el pico salió en {peak_hz:.2f} Hz: el espectro sigue mirando el ruido previo"
    )


def test_la_ventana_del_espectro_no_se_pasa_del_tope() -> None:
    """Control: la ventana sigue acotada, o la FFT se come el request."""
    freqs, _ = _spectrum(_con_sismo_al_final(2.0, 11.0), RATE)
    assert freqs is not None
    # `rfftfreq` de N muestras da N//2+1 bins; se diezma a ~400 puntos para el papel.
    assert len(freqs) <= MAX_FFT_SAMPLES // 2 + 1


def test_una_traza_CORTA_se_usa_entera() -> None:
    """Sin más muestras que el tope no hay ventana que elegir."""
    corta = _Traza(samples=[math.sin(2 * math.pi * 7.0 * i / RATE) for i in range(1000)])
    _, peak_hz = _spectrum(corta, RATE)
    assert peak_hz is not None and abs(peak_hz - 7.0) < 0.6


# ---- la onda cruda: la continua tapaba la señal ------------------------------


def test_quitar_la_CONTINUA_deja_ver_la_senal() -> None:
    """El crudo del ADC trae un offset de millones de cuentas. La traza se escalaba
    contra él con el cero abajo: salía una línea plana bajo una etiqueta
    «±3.86e+06 cuentas» — que es el offset, no la sacudida.
    """
    dc = 3_860_000.0
    crudas = [dc + 120.0 * math.sin(i / 5.0) for i in range(900)]

    assert scale_of(crudas) > 3_000_000, "el fixture ya no reproduce el defecto"

    media = sum(crudas) / len(crudas)
    sin_dc = [v - media for v in crudas]
    assert scale_of(sin_dc) < 200, "la escala sigue dominada por la continua"
    # Y la señal ocupa ahora una fracción visible del recuadro, no el 0.003 %.
    assert scale_of(sin_dc) / scale_of(crudas) < 0.001


# ---- la barra de escala del croquis ------------------------------------------


def _puntos(km: float) -> list[sketch.Point]:
    """Dos puntos separados ~`km` en latitud, a la latitud de Puebla."""
    return [
        sketch.Point(19.0, -98.2, "A", "site"),
        sketch.Point(19.0 + km / 111.0, -98.2, "B", "peer"),
    ]


def test_la_barra_MIDE_lo_que_su_rotulo_dice() -> None:
    """EL DEFECTO: la barra se recortaba a la mitad del ancho y el rótulo conservaba
    los kilómetros SIN recortar. El croquis existe para poder medir sobre el papel,
    y quien midiera medía mal.
    """
    for km in (1.0, 5.0, 20.0, 90.0, 300.0, 1500.0):
        d = sketch.project(_puntos(km), 180.0, 70.0)
        assert d is not None
        mm_por_km = d.scale_bar_mm / d.scale_bar_km
        # La misma regla para todos los tamaños: la longitud dibujada tiene que ser
        # la que corresponde a los km del rótulo, con la escala del propio croquis.
        esperado = _mm_por_km(d, km)
        assert abs(mm_por_km - esperado) / esperado < 0.02, (
            f"a {km} km la barra dice {d.scale_bar_km:g} km y mide {d.scale_bar_mm:.2f} mm"
        )


def _mm_por_km(d, km: float) -> float:
    """Escala real del croquis, derivada de la geometría, no de la barra."""
    ys = [p.y for p in d.points]
    return abs(ys[1] - ys[0]) / km


def test_la_barra_no_se_sale_del_croquis() -> None:
    """La otra mitad: que quepa. Antes cabía a costa de mentir."""
    for km in (1.0, 90.0, 1500.0):
        d = sketch.project(_puntos(km), 180.0, 70.0)
        assert d is not None
        assert 0 < d.scale_bar_mm <= 180.0 * 0.5


def test_en_un_croquis_ESTRECHO_la_barra_sigue_sin_mentir() -> None:
    """El recorte NO estaba vivo en el formato real (180 × 78 mm): el tope son
    82 mm y la barra no pasa de ~62. Era una mentira LATENTE, que un croquis más
    estrecho activa sin que nada avise — y con el `min(...)` de antes este caso
    dibujaba 22 mm bajo un rótulo de 50 km.
    """
    d = sketch.project(_puntos(90.0), 60.0, 200.0)
    assert d is not None
    esperado = _mm_por_km(d, 90.0)
    assert abs(d.scale_bar_mm / d.scale_bar_km - esperado) / esperado < 0.02, (
        f"barra de {d.scale_bar_km:g} km dibujada a {d.scale_bar_mm:.1f} mm"
    )
    assert d.scale_bar_mm <= (60.0 - 16.0) * 0.5 + 1e-6


def test_el_formato_REAL_del_dictamen_no_activa_el_tope() -> None:
    """Lo que se acaba de medir, escrito como guarda: si un cambio de layout
    hiciera morder el tope, esto se entera antes que un perito con una regla."""
    from takab_api.dictamen.pdf import _SKETCH_H, CONTENT_W

    for km in (1.0, 5.0, 20.0, 90.0, 300.0, 1500.0):
        d = sketch.project(_puntos(km), CONTENT_W, _SKETCH_H)
        assert d is not None
        assert d.scale_bar_mm < (CONTENT_W - 16.0) * 0.5, (
            f"a {km} km la barra toca el tope: revisa que el rótulo siga siendo cierto"
        )


# ---- «100 sps» escrito a fuego ----------------------------------------------


def test_los_avisos_no_afirman_una_TASA_de_muestreo() -> None:
    """La §8 imprime la tasa DECLARADA del sensor. Un aviso que escribe «100 sps»
    a fuego contradice a esa tabla en cuanto el inventario traiga otro modelo."""
    assert "sps" not in NO_SPECTRUM
