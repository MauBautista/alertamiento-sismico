"""T-7.24 · El cálculo del mini-ShakeMap: tres capas que no se mezclan.

Esta suite ejerce la lógica PURA —sin base, sin red, sin reloj— y fija lo que
costaría caro equivocar, por orden:

1. **El residuo es el producto.** `log10(medido/modelado)` por punto. Un punto
   que sacude el doble de lo que la ley predice a su distancia sale con
   `+0.301`, y ese número es la única cosa que el mapa dice y una regla no.
2. **Los niveles de los anillos son los umbrales con que este sistema decide**, y
   por eso se DERIVAN de los campos de PGA de `felt.Thresholds` en vez de
   escribirse. Una escala inventada es el pecado que esta ficha existe para no
   cometer, y `T-7.35` ya midió lo que cuesta.
3. **El campo modelado es radialmente simétrico**, porque ATTEN-LAW v1 sólo
   depende de la distancia hipocentral. Por eso se publica como ANILLOS de PGA
   constante con su radio en KILÓMETROS, y por eso el radio se despeja de la
   propia ley en vez de dibujarse.
4. **El radio tiene TOPE, y lo que no se dibuja se DECLARA.** ATTEN-LAW v1 es
   ilustrativa: un anillo de miles de kilómetros no mide nada. Por encima del
   tope el nivel sale en `fuera_de_alcance` con su motivo, nunca en silencio.
5. **Sin magnitud no hay capa 2**, y el mapa lo DECLARA (`solo_observado`) en
   vez de inventar un modelo. Sin ninguna medida, `sin_datos` — y entonces
   tampoco hay capa 2: la capa 2 sola es una regla de tres (`§A.3`).
6. **Un nivel que no corta la superficie no se publica.** Con el hipocentro a
   48 km, el nivel de 0.060 g de un M5.0 se alcanzaría a 8.35 km del hipocentro
   (`10**(0.5*5 − 2.8)/0.06`) — o sea nunca, porque el foco está más hondo que
   eso. Publicarlo como un círculo de radio 0 afirmaría que ahí arriba se llegó
   a ese valor.

Las cifras salen del Puebla-Morelos 2017 con la **solución USGS** que el
repositorio ya cita (`replay/plan.py`: 18.5499 N, −98.4887 W, 48 km, M7.1) y de
la distancia epicentro↔Ciudad de México que fija `forensics/correlacion.py`
(122 km). Ninguna es inventada aquí, y la banda y el tope no se escriben: se leen
de donde el sistema los tiene.
"""

from __future__ import annotations

import dataclasses
import math
from datetime import UTC, datetime

import pytest

from takab_api.felt import DEFAULT_THRESHOLDS, Thresholds
from takab_api.geo import hypo_km, pga_law_g
from takab_api.settings import Settings
from takab_api.shakemap import calculo as C

# --- el sismo de referencia, con su procedencia --------------------------------
M = 7.1
PROF_KM = 48.0
#: Epicentro → Ciudad de México, el número que `forensics/correlacion.py` cita.
DIST_CDMX_KM = 122.0
#: Lo que la ley predice ahí: 10**(0.5*7.1-2.8) / hypo(122, 48) = 0.0429 g.
PGA_MODELADA_CDMX = pga_law_g(M, hypo_km(DIST_CDMX_KM, PROF_KM))

#: El tope del radio, DERIVADO del mismo ajuste que usa la pasada: la distancia
#: máxima epicentro↔sitio con la que este sistema acepta que un sismo del
#: catálogo sea el que sacudió este edificio. Escribir aquí un número lo
#: desataría del código que se prueba.
TOPE_KM = Settings().correlation_max_km

T0 = datetime(2017, 9, 19, 18, 14, 40, tzinfo=UTC)

EPICENTRO = C.Epicentro(
    lat=18.5499,
    lon=-98.4887,
    depth_km=PROF_KM,
    magnitud=M,
    fuente="USGS",
    procedencia="confirmado",
    catalog_key="USGS-2017-09-19-PUE",
)

#: Los umbrales con que este sistema YA decide, DERIVADOS de la banda (el default
#: de `felt.Thresholds`, que es el del edge). Ni los nombres ni los valores se
#: teclean: si la banda cambia, estos niveles cambian con ella.
NIVELES = tuple(C.Nivel(nombre, getattr(DEFAULT_THRESHOLDS, nombre)) for nombre in C.UMBRALES)


def _medida(**over) -> C.Medida:
    base = dict(
        site_id="11111111-1111-1111-1111-111111111111",
        site_code="CDMX-01",
        site_name="Corporativo Reforma",
        lat=19.4326,
        lon=-99.1332,
        dist_km=DIST_CDMX_KM,
        pga_g=PGA_MODELADA_CDMX * 2.0,
        pgv_cms=3.2,
        medido_en=T0,
        voto_contado=True,
    )
    return C.Medida(**{**base, **over})


def _mapa(
    medidas=None,
    epicentro=EPICENTRO,
    cobertura_km=5.0,
    niveles=NIVELES,
    radio_max_km=TOPE_KM,
) -> C.Mapa:
    return C.calcula(
        medidas if medidas is not None else [_medida()],
        epicentro=epicentro,
        niveles=niveles,
        cobertura_km=cobertura_km,
        radio_max_km=radio_max_km,
    )


def _magnitud_donde_el_tope_muerde(pga_g: float, prof_km: float, tope_km: float) -> float:
    """La magnitud a la que el radio de ese nivel vale EXACTAMENTE el tope.

    Se despeja de la MISMA ley que dibuja el anillo (`R_hipo = 10**(0.5M−2.8)/PGA`
    proyectado con la profundidad), para que esta guarda siga midiendo lo que
    tiene que medir si mañana cambia el tope o la banda. Con la banda de fábrica
    (0.040 g) y el tope de hoy (1 200 km) son **M 8.96** — medido el 2026-09-21.
    """
    r_hipo = math.hypot(tope_km, prof_km)
    return 2.0 * (math.log10(r_hipo * pga_g) + 2.8)


# ------------------------------------------- los niveles: derivados, no escritos


def test_los_niveles_publicables_son_los_de_PGA_de_la_banda_del_inmueble() -> None:
    """El censo del vocabulario, DERIVADO de `felt.Thresholds`.

    Es la afirmación central de la ficha —«son los umbrales con que este sistema
    ya decide, no una escala inventada»— convertida en algo medible: los nombres
    salen de los campos en `g` de la banda que arma los actuadores del gabinete.
    Añadir un umbral de PGA a la banda y no publicarlo pone esto rojo; publicar
    un nombre que la banda no tiene, también.
    """
    de_la_banda = {f.name for f in dataclasses.fields(Thresholds) if f.name.endswith("_g")}
    assert set(C.UMBRALES) == de_la_banda
    assert {C.UMBRAL_WATCH, C.UMBRAL_TRIP} == de_la_banda, (
        "los nombres propios tienen que seguir siendo exactamente los de la banda"
    )


def test_el_piso_de_coherencia_de_la_correlacion_NO_es_un_nivel_del_mapa() -> None:
    """`correlacion_min_pga_g` (0.001 g) responde a «¿pudo notarse siquiera
    aquí?» — es el criterio de IDENTIDAD de `T-5.11`, no un umbral con el que se
    decida nada sobre el edificio. Como nivel de mapa despejaba 5 623.2 km para
    el M7.1 de referencia y 19 952.6 km para el M8.2 de Chiapas (medido el
    2026-09-21): la unidad era correcta y el significado, falso."""
    assert "correlacion_min_pga_g" not in C.UMBRALES
    assert Settings().correlation_min_pga_g not in [n.pga_g for n in NIVELES]


# --------------------------------------------------------------- capa 3: residuo


def test_el_residuo_es_log10_de_medido_entre_modelado() -> None:
    """El doble de lo predicho son +0.301 en log10. Es EL producto de la ficha."""
    punto = _mapa().puntos[0]
    assert punto.pga_g_modelada == pytest.approx(PGA_MODELADA_CDMX, rel=1e-9)
    assert punto.residuo_log10 == pytest.approx(math.log10(2.0), abs=1e-9)


def test_el_residuo_tiene_signo_y_el_signo_significa() -> None:
    """Sacudir MENOS de lo predicho es negativo. Un valor absoluto no diría nada."""
    flojo = _mapa([_medida(pga_g=PGA_MODELADA_CDMX / 10.0)]).puntos[0]
    assert flojo.residuo_log10 == pytest.approx(-1.0, abs=1e-9)


def test_sin_medida_no_hay_residuo_ni_cero() -> None:
    """Un inmueble instrumentado que no midió NO es 0 g (regla de oro 7).

    ⚠️ Con OTRO inmueble que sí midió: si no midiera ninguno no habría capa 2 en
    absoluto y este punto no tendría contra qué compararse.
    """
    mapa = _mapa([_medida(pga_g=None), _medida(site_code="CDMX-02")])
    punto = mapa.puntos[0]
    assert punto.pga_g is None
    assert punto.residuo_log10 is None
    # ...pero el modelo SÍ se puede afirmar ahí: depende sólo de la distancia.
    assert punto.pga_g_modelada == pytest.approx(PGA_MODELADA_CDMX, rel=1e-9)


def test_una_medida_de_cero_no_produce_un_residuo_infinito() -> None:
    """`log10(0)` es −inf y no es serializable a JSON: se declara ausente."""
    punto = _mapa([_medida(pga_g=0.0)]).puntos[0]
    assert punto.pga_g == 0.0
    assert punto.residuo_log10 is None


def test_la_procedencia_viaja_en_el_dato() -> None:
    """D-08 · A.3: cada valor dice si es medido o modelado, y quien pinta no adivina."""
    assert _mapa().puntos[0].procedencia == C.PROC_MEDIDO
    assert all(a.procedencia == C.PROC_MODELADO for a in _mapa().anillos)


def test_el_voto_de_cuorum_viaja_con_el_punto() -> None:
    """Lo que distingue a un inmueble que participó en el cuórum de uno que sólo
    estaba ahí — y el cuórum es lo único, con SASMEX, que puede ordenar evacuar.
    `None` NO es «no votó»: es que no hay evento de red que contar."""
    assert _mapa().puntos[0].voto_contado is True
    assert _mapa([_medida(voto_contado=False)]).puntos[0].voto_contado is False
    assert _mapa([_medida(voto_contado=None)]).puntos[0].voto_contado is None


# ------------------------------------------------------- capa 2: anillos en km


def test_el_radio_del_anillo_se_despeja_de_la_ley_y_va_en_KILOMETROS() -> None:
    """`R_hipo = 10**(0.5M - 2.8)/PGA`, proyectado a la superficie con la profundidad.

    Para el M7.1 y 0.040 g: R_hipo = 140.6 km ⇒ R_epi = √(140.6² − 48²) = 132.2 km.
    Y la comprobación que de verdad importa: la ley evaluada A ESE RADIO devuelve
    el nivel del anillo. Si no cerrara, el anillo afirmaría una PGA que el modelo
    no predice ahí.
    """
    watch = next(a for a in _mapa().anillos if a.umbral == C.UMBRAL_WATCH)
    assert watch.pga_g == DEFAULT_THRESHOLDS.pga_watch_g
    assert watch.radio_km == pytest.approx(132.2, abs=0.2)
    assert pga_law_g(M, hypo_km(watch.radio_km, PROF_KM)) == pytest.approx(watch.pga_g, rel=1e-9)


def test_los_anillos_van_del_mas_fuerte_al_mas_debil() -> None:
    """Orden declarado: PGA descendente ⇒ radio creciente. Quien pinta no reordena."""
    anillos = _mapa().anillos
    assert [a.umbral for a in anillos] == [C.UMBRAL_TRIP, C.UMBRAL_WATCH]
    assert [a.radio_km for a in anillos] == sorted(a.radio_km for a in anillos)


def test_un_anillo_que_no_corta_la_superficie_no_se_publica_pero_se_DECLARA() -> None:
    """Con el foco a 48 km, un M5.0 no alcanza la banda en NINGÚN punto de arriba.

    R_hipo(0.060) = 10**(0.5*5 − 2.8)/0.06 = 8.35 km < 48 km de profundidad. El
    anillo existiría dentro de la tierra y su radio en superficie no está
    definido; publicarlo como un círculo de radio 0 afirmaría que en el epicentro
    se llegó a ese valor, que es justo lo que el modelo NO dice.

    Pero desaparecer en silencio se lee como «ese umbral no existía», así que el
    nivel sale igual, con su motivo.
    """
    chico = dataclasses.replace(EPICENTRO, magnitud=5.0)
    mapa = _mapa(epicentro=chico)
    assert mapa.anillos == ()
    assert {n.umbral for n in mapa.fuera_de_alcance} == set(C.UMBRALES)
    assert {n.motivo for n in mapa.fuera_de_alcance} == {C.FUERA_BAJO_LA_SUPERFICIE}
    assert all(m in C.MOTIVOS_FUERA for m in (n.motivo for n in mapa.fuera_de_alcance))


def test_declarar_NIVELES_SUPRIMIDOS_implica_haber_MODELADO_cada_inmueble() -> None:
    """El invariante por el que el papel NO tiene una rama para `fuera_de_alcance`.

    `pdf._falta_para_modelar` tuvo una, con un comentario que decía que «no es
    teórica». Lo era: con la rama desactivada (`if False and b.fuera_de_alcance:`)
    `tests/dictamen/test_mapa_de_la_sacudida.py` seguía en `29 passed`, y un espía
    en esa función sobre `tests/dictamen` + `tests/documentos` enteros la contó
    **cero** veces. El porqué es esto, y no una casualidad del muestreo:
    `fuera_de_alcance` sólo se puebla si `modelable` —hubo medida, hay epicentro y
    hay magnitud—, y con eso `_punto` modela TODO inmueble que traiga distancia.
    Así que un snapshot que declara niveles suprimidos siempre trae el modelo por
    punto, y el papel lo explica por `SHAKEMAP_SIN_ANILLOS` —que además imprime el
    residuo— sin llegar nunca al aviso de DEGRADADO.

    Se mide por los DOS caminos que suprimen un nivel, porque son razones
    distintas y una podría dejar de cumplirlo sin la otra: el foco más hondo que
    el nivel (`bajo_la_superficie`) y el radio por encima del tope
    (`fuera_del_alcance`). Si esto dejara de ser cierto, el papel volvería a decir
    «no se calcula el residuo» sobre una tabla que lo imprime — y esta guarda se
    pone roja antes.
    """
    hondo = _mapa(epicentro=dataclasses.replace(EPICENTRO, magnitud=5.0))
    lejano = _mapa(
        epicentro=dataclasses.replace(
            EPICENTRO,
            magnitud=_magnitud_donde_el_tope_muerde(DEFAULT_THRESHOLDS.pga_trip_g, PROF_KM, TOPE_KM)
            + 0.05,
        ),
        radio_max_km=TOPE_KM,
    )
    for nombre, mapa in (("bajo la superficie", hondo), ("fuera del tope", lejano)):
        assert mapa.fuera_de_alcance, f"el escenario «{nombre}» dejó de suprimir ningún nivel"
        assert mapa.ley is not None, f"«{nombre}»: se declaran niveles de un modelo no aplicado"
        con_distancia = [p for p in mapa.puntos if p.dist_km is not None]
        assert con_distancia, f"«{nombre}»: el escenario se quedó sin inmuebles que modelar"
        assert all(p.pga_g_modelada is not None for p in con_distancia), (
            f"«{nombre}»: el mapa DECLARA niveles suprimidos y no modeló a ningún inmueble. "
            "Ése es exactamente el snapshot para el que el papel no tiene frase: el aviso de "
            "DEGRADADO diría «ni se calcula el residuo» sobre la tabla que lo imprime"
        )


def test_un_nivel_por_debajo_del_piso_de_la_ley_se_declara_NO_INVERTIBLE() -> None:
    """La ley usa `max(R_hipo, 1 km)`: por debajo de 1 km cualquier radio da el
    mismo valor, así que no hay radio que despejar. Pasa con un sismo pequeño —
    M3.0 y 0.060 g dan R_hipo = 0.53 km— y es una razón DISTINTA de «bajo la
    superficie», que es por lo que son dos motivos y no uno."""
    chico = dataclasses.replace(EPICENTRO, magnitud=3.0, depth_km=None)
    fuera = {n.umbral: n.motivo for n in _mapa(epicentro=chico).fuera_de_alcance}
    assert fuera[C.UMBRAL_TRIP] == C.FUERA_NO_INVERTIBLE


def test_el_anillo_que_pasa_del_TOPE_no_se_dibuja_y_dice_por_que() -> None:
    """⚠️ La guarda del hallazgo ALTO: un anillo de miles de km no mide nada.

    ATTEN-LAW v1 es ILUSTRATIVA, y a partir de cierta magnitud el radio de un
    nivel se va más allá de donde este sistema admite siquiera que un epicentro
    sea el que sacudió el edificio. La magnitud del cruce **se despeja** del tope
    y de la propia ley, para que la guarda siga midiendo si cambian; con la banda
    y el tope de hoy cae en M 8.96, que es una magnitud REAL (Tohoku 2011 fue
    M9.1). Por debajo se dibuja, por encima se declara.
    """
    cruce = _magnitud_donde_el_tope_muerde(DEFAULT_THRESHOLDS.pga_watch_g, PROF_KM, TOPE_KM)

    antes = _mapa(epicentro=dataclasses.replace(EPICENTRO, magnitud=cruce - 0.05))
    assert C.UMBRAL_WATCH in {a.umbral for a in antes.anillos}
    assert all(a.radio_km <= TOPE_KM for a in antes.anillos)

    despues = _mapa(epicentro=dataclasses.replace(EPICENTRO, magnitud=cruce + 0.05))
    assert C.UMBRAL_WATCH not in {a.umbral for a in despues.anillos}
    assert {n.umbral: n.motivo for n in despues.fuera_de_alcance} == {
        C.UMBRAL_WATCH: C.FUERA_DEL_ALCANCE
    }
    # El nivel más fuerte sigue cayendo dentro: el tope recorta un nivel, no el mapa.
    assert C.UMBRAL_TRIP in {a.umbral for a in despues.anillos}


def test_ningun_anillo_publicado_pasa_del_tope_ni_con_el_sismo_mas_grande() -> None:
    """El invariante en su forma fuerte, barriendo magnitudes reales.

    M9.5 es el mayor sismo instrumentado (Chile, 1960). Sin tope, y con la banda
    de fábrica, el nivel de 0.040 g despejaría **2 227.6 km** a M9.5 y el de
    0.060 g, 1 484.6 km (medido el 2026-09-21): los dos, más lejos de donde este
    sistema acepta atribuirle a un epicentro la sacudida de un edificio.
    """
    for mag in (5.0, 6.5, 7.1, 8.2, 9.0, 9.5):
        mapa = _mapa(epicentro=dataclasses.replace(EPICENTRO, magnitud=mag))
        assert all(a.radio_km <= TOPE_KM for a in mapa.anillos), mag
        # Y ningún nivel se pierde por el camino: dibujado o declarado, está.
        publicados = {a.umbral for a in mapa.anillos} | {n.umbral for n in mapa.fuera_de_alcance}
        assert publicados == set(C.UMBRALES), mag


def test_sin_profundidad_el_radio_epicentral_es_el_hipocentral() -> None:
    """Degrada como `geo.hypo_km`: sin profundidad reportada, hipocentral ≡ epicentral."""
    sin_prof = dataclasses.replace(EPICENTRO, depth_km=None)
    watch = next(a for a in _mapa(epicentro=sin_prof).anillos if a.umbral == C.UMBRAL_WATCH)
    assert watch.radio_km == pytest.approx(
        10 ** (0.5 * M - 2.8) / DEFAULT_THRESHOLDS.pga_watch_g, rel=1e-9
    )


# ------------------------------------------------------------------- los estados


def test_completo_exige_epicentro_magnitud_y_al_menos_una_medida() -> None:
    mapa = _mapa()
    assert mapa.estado == C.ESTADO_COMPLETO
    assert mapa.ley == C.LEY
    assert mapa.epicentro is not None


def test_sin_magnitud_el_mapa_existe_DEGRADADO_y_lo_declara() -> None:
    """A.5: «sin magnitud/epicentro el mapa existe degradado y lo declara»."""
    sin_mag = C.Epicentro(
        lat=18.5499,
        lon=-98.4887,
        depth_km=48.0,
        magnitud=None,
        fuente="local_quorum",
        procedencia="sin_dato_externo",
        catalog_key=None,
    )
    mapa = _mapa(epicentro=sin_mag)
    assert mapa.estado == C.ESTADO_SOLO_OBSERVADO
    assert mapa.anillos == ()
    assert mapa.fuera_de_alcance == (), "sin capa 2 no hay niveles que declarar"
    assert mapa.ley is None, "sin capa 2 no se puede citar la ley que no se aplicó"
    assert mapa.puntos[0].pga_g_modelada is None
    assert mapa.puntos[0].residuo_log10 is None


def test_sin_epicentro_tampoco_hay_modelo_pero_si_puntos() -> None:
    mapa = _mapa(epicentro=None)
    assert mapa.estado == C.ESTADO_SOLO_OBSERVADO
    assert mapa.epicentro is None
    assert mapa.anillos == ()
    assert len(mapa.puntos) == 1


def test_sin_ninguna_medida_NO_se_publica_la_capa_modelada() -> None:
    """⚠️ `§A.3`: «la capa 2 sola no aporta nada que no se calcule con una regla
    de tres». Con cero puntos medidos el mapa no es un mapa de la sacudida, así
    que no publica ni la ley, ni los anillos, ni la PGA modelada de cada punto —
    sólo dice que ya miró y no hay. El epicentro SÍ se queda: no es la capa 2,
    es el hecho externo que la anclaría, y con su procedencia."""
    mapa = _mapa([_medida(pga_g=None)])
    assert mapa.estado == C.ESTADO_SIN_DATOS
    assert mapa.anillos == ()
    assert mapa.fuera_de_alcance == ()
    assert mapa.ley is None
    assert mapa.puntos[0].pga_g_modelada is None
    assert mapa.puntos[0].residuo_log10 is None
    assert mapa.epicentro is EPICENTRO


def test_sin_inmuebles_tambien_es_sin_datos() -> None:
    mapa = _mapa([])
    assert mapa.estado == C.ESTADO_SIN_DATOS
    assert mapa.anillos == () and mapa.ley is None


def test_pendiente_no_es_un_estado_que_el_calculo_pueda_producir() -> None:
    """Lo pone el LECTOR cuando el worker todavía no ha pasado; el cálculo nunca."""
    assert C.ESTADO_PENDIENTE not in C.ESTADOS_PERSISTIDOS
    for mapa in (_mapa(), _mapa([]), _mapa(epicentro=None)):
        assert mapa.estado in C.ESTADOS_PERSISTIDOS


# ------------------------------------------------------- lo que no se calcula aquí


def test_el_punto_sin_distancia_no_se_modela() -> None:
    """Sin `dist_km` no hay a qué distancia evaluar la ley; y no se inventa una."""
    punto = _mapa([_medida(dist_km=None)]).puntos[0]
    assert punto.pga_g_modelada is None
    assert punto.residuo_log10 is None
    assert punto.pga_g is not None, "la medida sigue siendo válida: es un hecho"


def test_la_cobertura_viaja_en_el_mapa_y_no_recorta_nada() -> None:
    """`SIN COBERTURA` es una propiedad del ESPACIO y la declara quien pinta: el
    cálculo publica el radio y no borra puntos ni anillos con él."""
    mapa = _mapa(cobertura_km=0.5)
    assert mapa.cobertura_km == 0.5
    assert len(mapa.puntos) == 1 and mapa.anillos


def test_el_mapa_es_inmutable() -> None:
    """Molde de `forensics/correlacion.py`: frozen de verdad, y tuplas, no listas."""
    mapa = _mapa()
    with pytest.raises(dataclasses.FrozenInstanceError):
        mapa.estado = "otro"  # type: ignore[misc]
    assert isinstance(mapa.puntos, tuple)
    assert isinstance(mapa.anillos, tuple)
    assert isinstance(mapa.fuera_de_alcance, tuple)


# ------------------------------------------------------------- la forma persistida


def test_los_anillos_se_guardan_como_NUMEROS_no_como_un_dibujo() -> None:
    """§3 del contrato: la geometría del círculo la materializa quien pinta.

    Guardar vértices sería guardar un dibujo, no un modelo — y un dibujo hecho a
    una latitud no vale a otra. Las claves son UNIFORMES para dibujados y
    declarados: quien lee la fila cruda no tiene que adivinar la forma.
    """
    anillos = C.anillos_json(_mapa())
    claves = {"umbral", "pga_g", "radio_km", "motivo", "radio_max_km"}
    assert anillos and all(set(a) == claves for a in anillos)
    assert all(isinstance(a["radio_km"], float) for a in anillos)
    assert all(a["motivo"] is None for a in anillos)
    assert all(a["radio_max_km"] == TOPE_KM for a in anillos)


def test_el_censo_persistido_lleva_los_niveles_dibujados_Y_los_declarados() -> None:
    """Una sola lista, para que nadie pueda leer los anillos sin enterarse de qué
    umbral falta y por qué."""
    chico = dataclasses.replace(EPICENTRO, magnitud=5.0)
    entradas = C.anillos_json(_mapa(epicentro=chico))
    assert {e["umbral"] for e in entradas} == set(C.UMBRALES)
    assert all(e["radio_km"] is None for e in entradas)
    assert all(e["motivo"] == C.FUERA_BAJO_LA_SUPERFICIE for e in entradas)


def test_el_json_del_punto_lleva_su_procedencia_su_hora_y_su_voto() -> None:
    punto = C.puntos_json(_mapa())[0]
    assert punto["procedencia"] == C.PROC_MEDIDO
    assert punto["medido_en"] == T0.isoformat()
    assert punto["residuo_log10"] == pytest.approx(math.log10(2.0), abs=1e-9)
    assert punto["voto_contado"] is True
    assert punto["pgv_cms"] == 3.2
