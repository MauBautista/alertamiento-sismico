"""La analítica de evacuación (T-3.12). Aritmética pura: ni vídeo, ni modelo, ni red."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from takab_cctv.metricas import (
    PICO_MINIMO,
    Discrepancia,
    Muestra,
    calcular,
)

T0 = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)


def _serie(valores: list[int], *, cada_s: float = 10.0, desde: datetime = T0) -> list[Muestra]:
    return [Muestra(desde + timedelta(seconds=i * cada_s), n) for i, n in enumerate(valores)]


def _con_preroll(valores: list[int]) -> list[Muestra]:
    """Serie con línea base: dos muestras antes de la señal, como el clip real."""
    return [
        Muestra(T0 - timedelta(seconds=40), 1),
        Muestra(T0 - timedelta(seconds=20), 1),
    ] + _serie(valores)


#: Una evacuación normal: sube, hace pico y se vacía.
NORMAL = [0, 2, 8, 20, 35, 40, 40, 38, 30, 10, 4, 3, 2]


# --------------------------------------------------------------- la curva


def test_t90_es_cuanto_tardo_en_salir_la_mayor_parte() -> None:
    """Es la cifra que el usuario pidió por su nombre."""
    r = calcular(_con_preroll(NORMAL), t0=T0)
    assert r.peak_n == 40
    assert r.t50_s == 30.0  # primer instante con >= 20 personas
    assert r.t90_s == 50.0  # primer instante con >= 36


def test_la_linea_base_sale_de_ANTES_de_la_señal() -> None:
    r = calcular(_con_preroll(NORMAL), t0=T0)
    assert r.baseline_n == 1


def test_sin_pre_roll_se_DECLARA_que_no_hay_linea_base() -> None:
    """Sin ella, el aforo pico no se puede leer como «gente que salió»: podría haber habido
    treinta personas ahí desde antes."""
    r = calcular(_serie(NORMAL), t0=T0)
    assert r.baseline_n is None
    assert any("SIN LÍNEA BASE" in n for n in r.notas)


def test_el_reingreso_exige_una_caida_SOSTENIDA() -> None:
    """Alguien que sale de cuadro un instante no declara iniciado el reingreso."""
    parpadeo = [0, 10, 40, 40, 1, 40, 40, 38, 5, 4, 3]
    r = calcular(_con_preroll(parpadeo), t0=T0)
    # El 1 aislado en la posición 4 no cuenta; el reingreso empieza en la caída final.
    assert r.reentry_start_at == T0 + timedelta(seconds=80)


def test_si_el_aforo_no_baja_el_reingreso_se_declara_NO_OBSERVADO() -> None:
    """Un `None` con razón, no un cero: el goteo pudo agotarse antes de que nadie volviera."""
    r = calcular(_con_preroll([0, 10, 30, 40, 40, 40]), t0=T0)
    assert r.reentry_start_at is None
    assert any("REINGRESO NO OBSERVADO" in n for n in r.notas)


# ------------------------------------------------- el hallazgo de seguridad


def test_reingresar_ANTES_del_dictamen_es_un_hallazgo_y_se_dice_con_palabras() -> None:
    """No es un número negativo en una tabla: es que el inmueble se reocupó sin que nadie
    certificara que era habitable."""
    r = calcular(_con_preroll(NORMAL), t0=T0, t_dictamen=T0 + timedelta(seconds=200))
    assert r.reingreso_antes_del_dictamen is True
    veredicto = r.veredicto_reingreso()
    assert "ANTES del dictamen" in veredicto
    assert "sin certificación de habitabilidad" in veredicto


def test_reingresar_despues_del_dictamen_es_lo_normal_y_no_alarma() -> None:
    r = calcular(_con_preroll(NORMAL), t0=T0, t_dictamen=T0 + timedelta(seconds=30))
    assert r.reingreso_antes_del_dictamen is False
    assert "ANTES" not in r.veredicto_reingreso()


def test_sin_dictamen_no_se_inventa_una_latencia() -> None:
    r = calcular(_con_preroll(NORMAL), t0=T0)
    assert r.dictamen_lag_s is None
    assert r.reentry_lag_s is None
    assert any("SIN DICTAMEN" in n for n in r.notas)
    assert "SIN DATO" in r.veredicto_reingreso()


# --------------------------------------------------------- el cruce, no la suma


def test_el_aforo_y_el_pase_de_lista_se_CRUZAN_y_no_se_promedian() -> None:
    """Criterio literal de la ficha: la diferencia ES la información."""
    r = calcular(_con_preroll(NORMAL), t0=T0, checkins=44)
    d = r.discrepancia
    assert d is not None
    assert (d.aforo_camara, d.checkins) == (40, 44)
    assert d.diferencia == -4
    # Y en ningún sitio existe el promedio (42).
    assert not hasattr(d, "promedio")


def test_la_discrepancia_se_lee_en_palabras_en_los_dos_sentidos() -> None:
    assert "MÁS en cámara" in Discrepancia(40, 30).lectura
    assert "MÁS en el pase de lista" in Discrepancia(30, 40).lectura
    assert "coinciden" in Discrepancia(40, 40).lectura


def test_sin_una_de_las_dos_estimaciones_no_hay_cruce_que_mostrar() -> None:
    assert Discrepancia(40, None).diferencia is None
    assert "SIN CRUCE" in Discrepancia(None, 12).lectura


def test_sin_checkins_no_se_fabrica_una_discrepancia() -> None:
    assert calcular(_con_preroll(NORMAL), t0=T0).discrepancia is None


# ------------------------------------------------------ ausencias honestas


def test_una_serie_vacia_no_devuelve_ceros() -> None:
    """Un cero diría «no salió nadie». Un `None` dice «no lo sabemos»."""
    r = calcular([], t0=T0)
    assert r.peak_n is None and r.t90_s is None
    assert "SIN SERIE" in r.notas[0]


def test_un_pico_ridiculo_no_produce_metricas_de_evacuacion() -> None:
    """Ruido de detección sobre una zona vacía no es una evacuación, y devolver un `t90`
    sobre dos personas sería inventar una métrica."""
    r = calcular(_con_preroll([0, 1, 2, 1, 0]), t0=T0)
    assert r.peak_n == 2 < PICO_MINIMO
    assert r.t50_s is None and r.t90_s is None
    assert any("SIN EVACUACIÓN OBSERVABLE" in n for n in r.notas)


def test_una_serie_solo_anterior_a_la_señal_lo_declara() -> None:
    r = calcular([Muestra(T0 - timedelta(seconds=30), 4)], t0=T0)
    assert any("SIN MUESTRAS POSTERIORES" in n for n in r.notas)


def test_la_serie_se_ordena_aunque_llegue_desordenada() -> None:
    """El goteo sube por su cuenta y S3 no garantiza orden de entrega."""
    desordenada = list(reversed(_con_preroll(NORMAL)))
    assert calcular(desordenada, t0=T0).t90_s == 50.0
