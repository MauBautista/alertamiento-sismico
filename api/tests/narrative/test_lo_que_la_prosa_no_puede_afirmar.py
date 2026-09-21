"""T-7.27 · El guardrail, ampliado a lo que la IA ve desde ahora.

El guardrail descarta, no corrige: media respuesta «arreglada» es justo el dato a
medias que la regla de oro 7 prohíbe. Lo que esta ficha le añade son tres frentes que
se abren al darle a la IA la tabla por estación, el catálogo y las fotografías:

1. **Las cifras de estación.** `_allowed_measurements` solo miraba el pico del propio
   inmueble y el `basis`. Con la tabla dentro, la prosa que cita correctamente el
   `0.012 g` de la estación 2 se descartaba **por inventada** — el guardrail habría
   convertido el dato nuevo en una degradación permanente.
2. **La magnitud sin procedencia.** La magnitud NO es nuestra: viene del catálogo del
   SSN y solo existe si hay línea de catálogo. Un «M 7.1» escrito sin esa línea es un
   número inventado en un documento que se firma.
3. **Lo que se afirma sin fila**: que una estación detectó cuando no hay ninguna fila
   de estación, y que una fotografía muestra algo cuando no se adjuntó ninguna. Lo
   segundo es nuevo de esta ficha: es el modo de fallo propio de un modelo con visión.

Los controles negativos pesan tanto como las guardas: un guardrail que marca de más se
acaba desactivando, y entonces no vigila nada.
"""

from __future__ import annotations

import pytest

from takab_api.narrative.deterministic import sections_for
from takab_api.narrative.openrouter import guard
from takab_api.narrative.redact import facts_from
from tests.dictamen.test_pdf import model
from tests.narrative.test_lo_que_ve_la_ia import _con_danos
from tests.narrative.test_redact import BASIS

FACTS = facts_from(model(verdict_basis=BASIS))
BUENAS = dict(sections_for(FACTS))


def _con(texto: str, seccion: str = "Qué se midió") -> dict[str, str]:
    return {**BUENAS, seccion: texto}


# ── 1 · las cifras de estación ────────────────────────────────────────────────


def test_la_prosa_PUEDE_citar_el_pico_de_una_estacion_de_la_tabla() -> None:
    """Sin esto, el dato que esta ficha añade sería inutilizable: citarlo bien
    descartaba la respuesta entera."""
    assert FACTS.stations, "el fixture no trae tabla por estación: la guarda sería vacua"
    citando = _con("La estación 2 registró 0.012 g frente a un umbral de 0.07 g.")
    assert guard(citando, FACTS) is None


def test_una_cifra_que_NO_esta_en_ninguna_fila_sigue_siendo_inventada() -> None:
    razon = guard(_con("La estación 2 registró 0.44 g."), FACTS) or ""
    assert "mediciones que no están" in razon and "0.44" in razon


# ── 2 · la magnitud ───────────────────────────────────────────────────────────


def test_la_prosa_PUEDE_citar_la_magnitud_del_CATALOGO() -> None:
    assert "M 7.1" in (FACTS.catalog_line or ""), "el fixture ya no trae magnitud de catálogo"
    assert guard(_con("El evento corresponde al sismo M 7.1 del catálogo del SSN."), FACTS) is None


def test_una_magnitud_SIN_LINEA_DE_CATALOGO_se_descarta() -> None:
    """La magnitud no la mide TAKAB. Sin catálogo asociado no hay de dónde venga, y un
    número así en un documento firmado es lo que un perito usa para discutirlo entero."""
    sin_catalogo = facts_from(model(catalog_line=None, verdict_basis=BASIS))
    razon = guard(_con("Se trató de un sismo de magnitud 7.1.", "Qué pasó"), sin_catalogo) or ""
    assert "magnitud" in razon


def test_una_magnitud_DISTINTA_de_la_del_catalogo_se_descarta() -> None:
    razon = guard(_con("El sismo fue M 8.2 según el catálogo.", "Qué pasó"), FACTS) or ""
    assert "magnitud" in razon and "8.2" in razon


# ── 3 · lo que se afirma sin fila ─────────────────────────────────────────────


def test_no_puede_afirmar_que_una_estacion_DETECTO_si_no_hay_filas() -> None:
    sin_red = facts_from(model(estaciones=[], station_count=0, verdict_basis=BASIS))
    inventado = _con("Tres estaciones de la red detectaron el arribo.", "Qué pasó")
    razon = guard(inventado, sin_red) or ""
    assert "sin fila" in razon


def test_SI_puede_decir_que_NINGUNA_estacion_corroboro() -> None:
    """El control negativo, y no es teórico: es lo que el texto determinista escribe
    en «Limitaciones» cuando no hay red. Un guardrail que lo rechazara pondría el
    respaldo en contra del proveedor que respalda."""
    sin_red = facts_from(model(estaciones=[], station_count=0, verdict_basis=BASIS))
    assert guard(dict(sections_for(sin_red)), sin_red) is None


def test_no_puede_describir_una_FOTOGRAFIA_que_no_se_adjunto() -> None:
    """El modo de fallo propio de un modelo con visión: describir lo que no vio."""
    razon = guard(_con("En la fotografía se observa una grieta pasante.", "Qué pasó"), FACTS) or ""
    assert "sin fila" in razon and "fotograf" in razon.lower()


def test_SI_puede_describir_las_fotografias_QUE_SE_LE_ADJUNTARON() -> None:
    from takab_api.narrative.redact import imagenes_de  # noqa: PLC0415

    # Con `basis`: las secciones canónicas citan los umbrales, y sin él se
    # descartarían por «mediciones que no están» antes de llegar a lo que se mide aquí.
    m = _con_danos(verdict_basis=BASIS)
    con_fotos = facts_from(m, imagenes=imagenes_de(m))
    assert con_fotos.photos_attached == 1
    assert guard(_con("En la fotografía se observa una grieta.", "Qué pasó"), con_fotos) is None


# ── 4 · el suelo: el texto determinista pasa el guardrail ─────────────────────


def test_el_texto_DETERMINISTA_pasa_el_guardrail_ampliado() -> None:
    """La guarda de las guardas. El determinista cita cifras, la línea del catálogo y
    las ausencias de la red: si el guardrail lo rechazara, estaría marcando de más
    sobre el único texto que sabemos verdadero."""
    for m in (model(verdict_basis=BASIS), model(estaciones=[], station_count=0), _con_danos()):
        f = facts_from(m)
        assert guard(dict(sections_for(f)), f) is None, f"el determinista no pasa: {m.folio}"


# ── 5 · [T-7.27·A] lo que las tres guardas dejaban pasar, MEDIDO ─────────────
#
# Cada guarda cazaba la frase EXACTA de su propia prueba y poco más. Lo de abajo son las
# formulaciones que el escéptico midió una a una: seis de ocho magnitudes inventadas
# pasaban, las dos guardas de «sin fila» se apagaban por dos vías distintas, y una frase
# legítima —«El Módulo M 3 quedó sin revisar»— descartaba la respuesta entera.

SIN_CATALOGO = facts_from(model(catalog_line=None, verdict_basis=BASIS))
SIN_RED = facts_from(model(estaciones=[], station_count=0, verdict_basis=BASIS))
#: `station_count > 0` con la tabla VACÍA. Es alcanzable en producción —el conteo y la
#: tabla salen de dos consultas independientes del builder— y era el estado en el que la
#: guarda de estaciones se apagaba ENTERA, porque la condición era `not stations and not
#: station_count`. Es el mismo estado en que estuvo el fixture del dictamen hasta T-7.22,
#: con el papel imprimiendo «ESTACIONES QUE CORROBORARON: 4» y la §7 por el callout.
CONTEO_SIN_TABLA = facts_from(model(estaciones=[], station_count=4, verdict_basis=BASIS))


def _guard(texto: str, facts, seccion: str = "Qué pasó") -> str:
    return guard({**dict(sections_for(facts)), seccion: texto}, facts) or ""


@pytest.mark.parametrize(
    "frase",
    [
        pytest.param("Se trató de un sismo de magnitud 7.1.", id="la del test original"),
        pytest.param("Se trató de un sismo de magnitud de 7.1.", id="magnitud DE"),
        pytest.param("El evento tuvo una magnitud estimada de 7.1.", id="magnitud estimada de"),
        pytest.param("El sismo fue de Mw 7.1.", id="Mw · la notación del SSN"),
        pytest.param("El sismo alcanzó Mw7.1.", id="Mw pegado"),
        pytest.param("El evento registró una magnitud momento de 7.1 grados.", id="momento de"),
        pytest.param("El sismo fue M 7.1.", id="M suelta"),
        pytest.param("Se trató de un sismo de magnitud siete punto uno.", id="la cifra con letras"),
    ],
)
def test_NINGUNA_formulacion_de_magnitud_pasa_sin_linea_de_catalogo(frase: str) -> None:
    """Seis de estas ocho pasaban. La que más importa es `Mw`, que es la notación
    estándar del SSN y del USGS: era la forma más probable y la que escapaba entera."""
    assert "magnitud" in _guard(frase, SIN_CATALOGO).lower()


def test_una_M_que_NO_es_una_magnitud_no_descarta_la_respuesta() -> None:
    """El control negativo, y pesa tanto como la guarda: un guardrail que marca de más
    sobre prosa verdadera se acaba desactivando, y entonces no vigila nada."""
    assert _guard("El Módulo M 3 quedó sin revisar.", FACTS) == ""
    assert _guard("El eje M 4 no presenta daño.", FACTS) == ""


def test_decir_que_NO_HAY_magnitud_de_catalogo_sigue_siendo_legitimo() -> None:
    assert _guard("No hay magnitud de catálogo asociada a este incidente.", SIN_CATALOGO) == ""


@pytest.mark.parametrize(
    "frase",
    [
        pytest.param("Tres estaciones de la red detectaron el arribo.", id="la del test original"),
        pytest.param(
            "Tres estaciones de la red detectaron el arribo sin retraso.",
            id="`sin` DESPUÉS del verbo",
        ),
        pytest.param(
            "Las estaciones de la red registraron el arribo, aunque no se conservó el pico.",
            id="`no` en la subordinada",
        ),
    ],
)
def test_una_DETECCION_inventada_no_se_exime_por_llevar_una_negacion_detras(frase: str) -> None:
    """`no` y `sin` son las dos palabras más comunes del castellano: eximir la frase
    entera por contenerlas en cualquier posición dejaba la guarda apagada ante la prosa
    hedgeada, que es justo la que escribe un modelo."""
    assert "sin fila" in _guard(frase, SIN_RED)


def test_SI_puede_decir_que_NINGUNA_estacion_corroboro_con_la_negacion_DELANTE() -> None:
    """Y la negación que sí gobierna sigue eximiendo. Es la frase que escribe el texto
    determinista cuando no hay red."""
    assert _guard("Ninguna estación de la red corroboró el evento.", SIN_RED) == ""


def test_citar_una_estacion_POR_SU_ORDEN_exige_que_esa_FILA_exista() -> None:
    """El orden es lo único con lo que la prosa puede nombrar una fila; un orden que no
    está en la tabla es una fila inventada. Cubre además el estado en que la otra guarda
    se apagaba entera: conteo mayor que cero y tabla vacía."""
    assert "no están en la tabla" in _guard("La estación 7 superó su umbral.", FACTS)
    assert "no están en la tabla" in _guard("La estación 2 registró el arribo.", CONTEO_SIN_TABLA)
    # Y con la fila delante, la misma frase es legítima.
    assert FACTS.stations, "el fixture no trae tabla: la guarda sería vacua"
    assert _guard("La estación 2 registró 0.012 g frente a un umbral de 0.07 g.", FACTS) == ""


def test_con_CONTEO_y_sin_tabla_la_prosa_no_puede_inventarse_otro_numero() -> None:
    """Sin filas no hay subconjunto que citar: la única cifra sostenible es la del
    conteo. Con tabla no se aplica, porque «3 de las 4 estaciones» es legítimo."""
    assert CONTEO_SIN_TABLA.station_count == 4 and not CONTEO_SIN_TABLA.stations
    assert "no es el del conteo" in _guard("6 estaciones registraron el arribo.", CONTEO_SIN_TABLA)
    assert _guard("4 estaciones registraron el arribo.", CONTEO_SIN_TABLA) == ""


@pytest.mark.parametrize(
    "frase",
    [
        pytest.param("En la fotografía se observa una grieta pasante.", id="la del test original"),
        pytest.param(
            "En la fotografía se observa una grieta pasante sin continuidad.",
            id="`sin` DESPUÉS del verbo",
        ),
        pytest.param("Las fotografías documentan daño no estructural.", id="documentan"),
        pytest.param("En la foto del reporte 1 aparece una columna agrietada.", id="aparece"),
        pytest.param("Se adjuntan fotografías donde aparece una grieta.", id="donde aparece"),
    ],
)
def test_NINGUNA_descripcion_de_una_foto_inexistente_pasa(frase: str) -> None:
    """`aparecer` y `documentar` son los dos verbos naturales y no estaban en la lista."""
    assert FACTS.photos_attached == 0, "el fixture trae fotos: la guarda sería vacua"
    assert "sin fila" in _guard(frase, FACTS)


# ── 6 · [T-7.27·A] y lo que VUELVE, que no lo miraba nadie ───────────────────
#
# `guard` miraba secciones, veredicto ajeno, cifras y afirmaciones sin fila, y NADA de lo
# que el texto devuelto pudiera traer dentro. Es un camino de vuelta que esta ficha abre
# —el modelo ve fotografías, y en el píxel de cada una iban el `sub` del operador y las
# coordenadas del inmueble— y el texto se usa verbatim en un PDF que se firma.


def test_la_prosa_NO_puede_devolver_unas_coordenadas() -> None:
    """La forma exacta con la que `watermark.ts::fmtGps` las dibuja: dos decimales
    largos separados por coma. Ningún hecho redactado lleva nada parecido."""
    razon = _guard("El punto de referencia es 19.43260, -99.13320 en el nivel 3.", FACTS)
    assert "coordenadas" in razon and "19.43260" in razon


def test_la_prosa_NO_puede_devolver_un_identificador_que_no_esta_en_los_hechos() -> None:
    """Los ocho primeros hex del `sub` de Cognito son lo que la marca de agua imprime
    junto a «OP»."""
    razon = _guard("Lo registró el operador 9f1e4a2c en el nivel 3.", FACTS)
    assert "identificadores" in razon and "9f1e4a2c" in razon


def test_la_prosa_SI_puede_nombrar_el_FOLIO_del_documento() -> None:
    """El control negativo obligado: el folio lleva ocho hex dentro y es el nombre
    público del documento — `redact.py` lo declara y la prosa tiene que poder citarlo."""
    assert _guard(f"El presente dictamen se identifica como {FACTS.folio}.", FACTS) == ""


def test_una_FECHA_de_ocho_cifras_no_se_confunde_con_un_identificador() -> None:
    """`20260803` son ocho caracteres válidos en hexadecimal. Marcarla sería marcar de
    más sobre prosa verdadera."""
    assert _guard("El incidente se abrió el 20260803 a las 10:00 UTC.", FACTS) == ""
