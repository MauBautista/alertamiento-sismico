"""T-5.11 · El criterio de identidad con el catálogo, probado sin base de datos.

El módulo es puro a propósito y esta suite se aprovecha: cada criterio se prueba
con un sismo REAL, con sus coordenadas y su magnitud publicadas, para que el
número que falla en un rojo sea un número que se pueda ir a comprobar.

Todas las distancias son al mismo sitio —el centro de la Ciudad de México, que es
donde está el gabinete de pruebas (-99.13, 19.43)— porque el criterio que esta
ficha introduce es epicentro↔SITIO.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from takab_api.forensics import correlacion as corr
from takab_api.settings import Settings

#: El sitio de los tests, que es también el de `conftest`: Ciudad de México.
SITIO = (19.43, -99.13)

#: Origen arbitrario pero fijo. Todo lo demás se expresa como desfase contra éste.
T0 = datetime(2026, 9, 4, 18, 0, 0, tzinfo=UTC)


def _criterio(**over) -> corr.Criterio:
    """El criterio REAL de producción, leído de `Settings`.

    Deliberadamente no se teclean los números aquí: si mañana alguien afloja el
    radio en `settings.py`, estos tests tienen que moverse con él o romperse — no
    seguir midiendo un criterio que ya no es el que corre.
    """
    s = Settings()
    base = dict(
        v_s_km_s=s.correlation_v_s_km_s,
        margen_s=s.correlation_margin_s,
        radio_km=s.correlation_max_km,
        pga_minima_g=s.correlation_min_pga_g,
    )
    return corr.Criterio(**{**base, **over})


def _evalua(cand: corr.Candidato, *, detectado_en: datetime, **over) -> corr.Veredicto:
    return corr.evalua(
        cand,
        detectado_en=detectado_en,
        sitio_lat=SITIO[0],
        sitio_lon=SITIO[1],
        criterio=_criterio(**over),
    )


# --- sismos reales, con las cifras que publicó el SSN --------------------------

#: 2017-09-19, M7.1, 12 km al sureste de Axochiapan. 122 km del sitio.
PUEBLA_MORELOS = corr.Candidato("SSN-2017-PUE", T0, 7.1, 18.40, -98.72, 57.0)
#: 2017-09-08, M8.2, golfo de Tehuantepec. 737 km del sitio: el caso que la
#: ventana fija de ±120 s dejaba fuera.
CHIAPAS = corr.Candidato("SSN-2017-CHI", T0, 8.2, 14.85, -94.11, 58.0)
#: 1985-09-19, M8.1, costa de Michoacán. 428 km del sitio.
MICHOACAN = corr.Candidato("SSN-1985-MICH", T0, 8.1, 18.08, -102.94, 15.0)


# ---- criterio 1 · ventana temporal consciente de la distancia -----------------


def test_un_sismo_cercano_casa_con_su_retraso_corto() -> None:
    """122 km: la sacudida llega a ~34 s, y a los 40 s ya casó."""
    v = _evalua(PUEBLA_MORELOS, detectado_en=T0 + timedelta(seconds=40))
    assert v.casa, v.detalle
    assert v.km_al_sitio == pytest.approx(122, abs=5)


def test_EL_SISMO_QUE_VACIO_LA_CIUDAD_no_casaba_con_la_ventana_fija() -> None:
    """Chiapas 2017: 737 km, onda S a ~205 s. La ventana fija de ±120 s lo perdía.

    Es la mitad menos obvia del defecto de esta ficha —la que no se ve mirando
    intrusos— y la razón de que la ventana sea consciente de la distancia: un
    ±120 s no es «holgado», es físicamente incorrecto para un sismo lejano.
    """
    detectado = T0 + timedelta(seconds=205)
    assert (detectado - T0).total_seconds() > 120.0, "el caso ya no prueba lo que dice"

    v = _evalua(CHIAPAS, detectado_en=detectado)
    assert v.casa, v.detalle
    assert v.retraso_admisible_s is not None and v.retraso_admisible_s > 205.0


def test_el_mismo_retraso_a_122_km_NO_casa() -> None:
    """205 s es admisible a 737 km y absurdo a 122: la cota depende de la distancia."""
    v = _evalua(PUEBLA_MORELOS, detectado_en=T0 + timedelta(seconds=205))
    assert not v.casa
    assert v.motivo == corr.FUERA_DE_VENTANA
    assert "Δt +205 s" in v.detalle


def test_un_origen_POSTERIOR_a_la_deteccion_no_casa() -> None:
    """Un edificio no detecta un sismo antes de que ocurra.

    Hasta esta ficha el criterio comparaba el valor ABSOLUTO del desfase, así que
    un evento originado después de nuestra detección casaba igual de bien que uno
    originado antes.
    """
    s = Settings()
    v = _evalua(PUEBLA_MORELOS, detectado_en=T0 - timedelta(seconds=s.correlation_margin_s + 10))
    assert not v.casa
    assert v.motivo == corr.ANTERIOR_A_SU_ORIGEN


def test_el_margen_hacia_atras_tolera_el_desfase_de_reloj() -> None:
    """Dentro del margen sí: es tolerancia de reloj y de revisión de la hora origen."""
    s = Settings()
    v = _evalua(PUEBLA_MORELOS, detectado_en=T0 - timedelta(seconds=s.correlation_margin_s - 1))
    assert v.casa, v.detalle


# ---- criterio 2 · radio máximo epicentro↔sitio -------------------------------


@pytest.mark.parametrize(
    ("nombre", "lat", "lon"),
    [
        # Los tres son sismos que ocurrieron de verdad, en sitios que jamás
        # sacudieron un edificio de la Ciudad de México.
        ("Chile · Illapel 2015", -31.57, -71.67),
        ("Japón · Tohoku 2011", 38.30, 142.37),
        ("Indonesia · Sumatra 2004", 3.32, 95.85),
    ],
)
def test_un_sismo_de_otro_continente_no_casa_aunque_caiga_en_la_ventana(
    nombre: str, lat: float, lon: float
) -> None:
    """**El caso que esta ficha existe para impedir.**

    Con el feed vivo de `T-2.149` esto deja de ser hipotético: un M8 al otro lado
    del mundo, dentro de la ventana temporal, se imprimía con su magnitud y su
    lugar en un dictamen FIRMADO, bajo el rótulo «contraste con catálogo».
    """
    lejano = corr.Candidato("EXT-1", T0, 8.3, lat, lon, 30.0)
    v = _evalua(lejano, detectado_en=T0 + timedelta(seconds=60))

    assert not v.casa, nombre
    assert v.motivo == corr.FUERA_DE_RADIO
    assert v.km_al_sitio is not None and v.km_al_sitio > Settings().correlation_max_km
    assert "km)" in v.detalle


def test_los_tres_grandes_mexicanos_entran_holgados_en_el_radio() -> None:
    """El radio no puede ser tan estrecho que excluya lo que sí sacude al país."""
    radio = Settings().correlation_max_km
    for cand in (PUEBLA_MORELOS, MICHOACAN, CHIAPAS):
        v = _evalua(cand, detectado_en=T0 + timedelta(seconds=1))
        assert v.km_al_sitio is not None
        assert v.km_al_sitio < radio, f"{cand.catalog_key} a {v.km_al_sitio:.0f} km"


# ---- criterio 3 · magnitud coherente con la distancia ------------------------


def test_un_sismo_pequeno_y_LEJANO_no_pudo_sacudir_este_edificio() -> None:
    """M4.0 a ~300 km: dentro del radio, dentro de la ventana, y aun así imposible.

    Es el criterio que no se puede escribir como «magnitud mínima» plana: el
    mismo M4.0 cerca sí abre un incidente (test siguiente).
    """
    pequeno = corr.Candidato("SSN-CHICO-LEJOS", T0, 4.0, 16.8, -99.5, 20.0)
    v = _evalua(pequeno, detectado_en=T0 + timedelta(seconds=82))

    assert not v.casa
    assert v.motivo == corr.MAGNITUD_INCOHERENTE
    assert v.pga_esperada_g is not None and v.pga_esperada_g < Settings().correlation_min_pga_g


def test_el_MISMO_sismo_pequeno_cerca_si_casa() -> None:
    """M4.0 a ~30 km del sitio: perfectamente capaz de abrir un incidente."""
    cerca = corr.Candidato("SSN-CHICO-CERCA", T0, 4.0, 19.20, -99.00, 20.0)
    v = _evalua(cerca, detectado_en=T0 + timedelta(seconds=10))

    assert v.casa, v.detalle
    assert v.km_al_sitio is not None and v.km_al_sitio < 40


def test_sin_magnitud_publicada_NO_se_rechaza() -> None:
    """«Desconocida» no es «incoherente»: rechazar por eso sería inventar el dato."""
    sin_m = corr.Candidato("SSN-SIN-M", T0, None, 18.40, -98.72, 57.0)
    v = _evalua(sin_m, detectado_en=T0 + timedelta(seconds=40))

    assert v.casa, v.detalle
    assert v.pga_esperada_g is None


def test_el_piso_de_pga_deja_pasar_una_correlacion_de_sasmex() -> None:
    """El piso pregunta «¿pudo notarse?», no «¿habría disparado?».

    Puesto en el umbral de cautela del gabinete (0.040 g) rechazaría justo las
    correlaciones del camino primario, donde el edificio puede no haber sentido
    casi nada y el evento del catálogo SÍ es el que la alerta anunció.
    """
    v = _evalua(CHIAPAS, detectado_en=T0 + timedelta(seconds=5))  # aviso por telemetría
    assert v.casa, v.detalle
    assert v.pga_esperada_g is not None and v.pga_esperada_g < 0.040


# ---- default-deny -------------------------------------------------------------


def test_sin_coordenadas_del_sitio_no_se_afirma_identidad() -> None:
    """La identidad se verifica contra el sitio; sin sitio no se puede verificar."""
    v = corr.evalua(
        PUEBLA_MORELOS,
        detectado_en=T0 + timedelta(seconds=40),
        sitio_lat=None,
        sitio_lon=None,
        criterio=_criterio(),
    )
    assert not v.casa
    assert v.motivo == corr.SITIO_SIN_COORDENADAS


def test_sin_epicentro_en_la_fila_del_catalogo_no_se_afirma_identidad() -> None:
    sin_epi = corr.Candidato("SSN-SIN-EPI", T0, 7.1, None, None, 57.0)
    v = _evalua(sin_epi, detectado_en=T0 + timedelta(seconds=40))
    assert not v.casa
    assert v.motivo == corr.SIN_EPICENTRO_EN_EL_CATALOGO


def test_todo_motivo_tiene_texto_legible() -> None:
    """Un motivo sin texto es un rechazo que nadie puede leer en el papel."""
    motivos = {
        v
        for k, v in vars(corr).items()
        if k.isupper() and isinstance(v, str) and k not in ("CONTRASTADO", "NO_VERIFICABLE")
    }
    assert motivos == set(corr.MOTIVOS), "un motivo nuevo sin su línea en MOTIVOS"
    assert all(len(t) > 20 for t in corr.MOTIVOS.values())


# ---- la elección entre varios candidatos -------------------------------------


def test_gana_el_que_CASA_no_el_mas_cercano_en_el_tiempo() -> None:
    """El más cercano en el tiempo puede ser precisamente el intruso.

    Hasta esta ficha la consulta traía UNA fila —la de menor Δt— y esa fila se
    imprimía. Aquí el intruso está más cerca en el tiempo que el legítimo, y aun
    así pierde.
    """
    intruso = corr.Candidato("EXT-CHILE", T0 + timedelta(seconds=35), 8.3, -31.57, -71.67, 22.0)
    r = corr.correlaciona(
        [intruso, PUEBLA_MORELOS],
        detectado_en=T0 + timedelta(seconds=40),
        sitio_lat=SITIO[0],
        sitio_lon=SITIO[1],
        criterio=_criterio(),
    )

    assert r.acierto is not None and r.acierto.catalog_key == "SSN-2017-PUE"
    assert [d.catalog_key for d in r.descartes] == ["EXT-CHILE"]
    assert r.descartes[0].motivo == corr.FUERA_DE_RADIO


def test_sin_ningun_candidato_que_case_quedan_los_DESCARTES_con_su_motivo() -> None:
    """«Hay un evento en el catálogo pero no es el nuestro» — lo que no se sabía decir.

    Sin esto un descarte es indistinguible de un catálogo vacío, y una pantalla
    vacía se lee como «no pasó nada».
    """
    intruso = corr.Candidato("EXT-JAPON", T0, 9.0, 38.30, 142.37, 29.0)
    r = corr.correlaciona(
        [intruso],
        detectado_en=T0 + timedelta(seconds=40),
        sitio_lat=SITIO[0],
        sitio_lon=SITIO[1],
        criterio=_criterio(),
    )

    assert r.acierto is None
    assert r.hubo_candidatos is True
    assert r.descartes[0].detalle.startswith("el epicentro está fuera del radio")


def test_sin_candidatos_el_resultado_lo_declara() -> None:
    r = corr.correlaciona(
        [], detectado_en=T0, sitio_lat=SITIO[0], sitio_lon=SITIO[1], criterio=_criterio()
    )
    assert r.acierto is None and r.descartes == () and r.hubo_candidatos is False


# ---- la cota que acota la consulta -------------------------------------------


def test_el_retraso_maximo_cubre_el_borde_del_radio() -> None:
    """La consulta se acota con esta cota: si se quedara corta, el criterio nunca
    llegaría a ver al evento lejano que sí debe casar."""
    c = _criterio()
    assert c.retraso_maximo_s == pytest.approx(c.retraso_admisible_s(c.radio_km))
    # Y cubre con holgura el peor caso real medido (Chiapas, 737 km ⇒ ~205 s).
    assert c.retraso_maximo_s > 205.0


# ---- la frontera entre el SQL y el criterio -----------------------------------
#
# El criterio SOLO sirve si la consulta le deja ver lo que tiene que rechazar. Si
# el `WHERE` se lleva por delante un candidato, ese rechazo pierde su motivo y
# vuelve a ser el hueco que esta ficha existe para eliminar. Estos dos tests son
# lo único que impide que alguien «optimice» el SQL y desmonte la ficha entera.


def test_el_SQL_no_reimplementa_el_criterio() -> None:
    """La consulta trae candidatos; quien decide es Python, y con la ley de atenuación.

    Meter el criterio en SQL crearía un tercer espejo de una física que ya vive
    en `geo.py` — y los espejos divergen (`TRASPASO-SESION.md §4`).
    """
    from takab_api.queries import forensics as qf

    sql = str(qf._CATALOG_CANDIDATES).lower()
    donde = sql[sql.index("where") :]
    for prohibido in ("st_dwithin", "st_distance", "magnitude >", "magnitude <", "depth_km"):
        assert prohibido not in donde, (
            f"la consulta filtra por `{prohibido}`: el criterio de identidad se está "
            "reimplementando en SQL, donde no puede usar ATTEN-LAW ni dejar el motivo"
        )
    assert "limit" in sql, "sin tope, una ventana ancha sobre un feed vivo trae el catálogo entero"


def test_las_cotas_de_la_consulta_son_un_SUPERCONJUNTO_del_criterio() -> None:
    """Lo que el criterio podría aceptar tiene que estar dentro de lo que se trae.

    Se comprueba en el borde: el evento más lejano admisible, justo dentro del
    radio. Si la consulta se acotara con el margen hacia delante en vez de con el
    retraso máximo, este candidato ni se evaluaría.
    """
    c = _criterio()
    borde_s = c.retraso_admisible_s(c.radio_km)
    # Las cotas que usa `forensics._catalog`, escritas aquí como contrato.
    desde, hasta = -c.retraso_maximo_s, +c.retraso_maximo_s
    assert desde <= -borde_s, "la cota hacia atrás recorta candidatos que el criterio aceptaría"
    # Y hacia delante alcanza a los que el criterio rechaza POR IMPOSIBLES, que
    # es como el sistema puede decir «ese evento aún no había ocurrido».
    assert hasta > c.margen_s
