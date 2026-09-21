"""T-5.11 · La línea de correlación con el catálogo, que es la que se FIRMA.

**Por qué esta suite existe.** El defecto que la ficha `T-5.11` describe se
imprimía aquí: un sismo del catálogo elegido solo por cercanía temporal entraba
en un dictamen firmado bajo el rótulo «contraste con catálogo», con su magnitud y
su lugar. Al arreglarlo se comprobó por mutación que **la línea no tenía ninguna
prueba**: se podía volver a presentar un acierto sin epicentro propio como un
contraste, o imprimir la magnitud del catálogo sin procedencia, y las 155 pruebas
del dictamen seguían en verde. Es el mismo hallazgo que `T-5.07` hizo con los
avisos, un nivel más abajo: allí faltaba probar que el aviso llega al papel, aquí
falta probar **qué dice**.

Se prueba la función pura que compone la línea, no el PDF: lo que se está
verificando es la afirmación, y el que el `callout` llegue al documento ya lo
cubre `test_avisos_impresos.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from takab_api import procedencia as pr
from takab_api.dictamen.builder import _catalog_line
from takab_api.dictamen.model import (
    CONSULTA_EXTERNA_EN_VUELO,
    CORRELACION_EN_DISPUTA,
    ESTADO_DE_CONSULTA_NO_INTERPRETABLE,
    SIN_CONSULTA_A_FUENTE_EXTERNA,
    TS_FMT,
)
from takab_api.schemas.forensics import (
    CatalogCorrelation,
    CatalogCriterion,
    CatalogDelta,
    CatalogDiscard,
    CatalogMatch,
    ForensicsOut,
)

_T0 = datetime(2026, 9, 4, 18, 0, 0, tzinfo=UTC)
_INCIDENTE = "d0000000-0000-4000-8000-00000000d000"

#: El criterio real, con la forma en que viaja en la respuesta.
_CRITERIO = CatalogCriterion(v_s_km_s=3.6, margen_s=30.0, radio_km=1200.0, pga_minima_g=0.001)


def _forensics(
    *,
    match: CatalogMatch | None = None,
    delta: CatalogDelta | None = None,
    estado: str = "sin_dato_externo",
    verificacion: str | None = None,
    descartes: list[CatalogDiscard] | None = None,
    fuente: str | None = None,
    consultado_en: datetime | None = None,
) -> ForensicsOut:
    return ForensicsOut(
        incident_id=_INCIDENTE,
        window_from=_T0,
        window_to=_T0,
        felt_band="unknown",
        catalog=match,
        catalog_delta=delta,
        catalog_correlation=CatalogCorrelation(
            estado=estado,
            verificacion=verificacion,
            criterio=_CRITERIO,
            descartes=descartes or [],
            fuente=fuente,
            consultado_en=consultado_en,
        ),
    )


def _match(**over) -> CatalogMatch:
    campos = dict(
        catalog_key="SSN-2017-PUE",
        origin_time=_T0,
        magnitude=7.1,
        place="Axochiapan",
        depth_km=57.0,
        source="SSN",
        lat=18.40,
        lon=-98.72,
        dt_s=34.0,
        km_al_sitio=122.0,
        rumbo_al_sitio="SSE",
        pga_esperada_g=0.0417,
    )
    return CatalogMatch(**{**campos, **over})


# ---- el acierto con epicentro propio: eso SÍ es un contraste -----------------


def test_con_epicentro_propio_la_linea_declara_el_contraste() -> None:
    linea = _catalog_line(
        _forensics(
            match=_match(),
            delta=CatalogDelta(km=12.4, bearing="NE", dt_s=34.0),
            estado="confirmado",
            verificacion="contrastado",
        )
    )
    assert linea is not None
    assert "CONTRASTE 12 km NE" in linea
    assert "SSN SSN-2017-PUE" in linea
    assert "Δt 34 s" in linea


# ---- el acierto SIN epicentro propio: no es un contraste ---------------------


def test_SIN_epicentro_propio_la_linea_NO_dice_contraste() -> None:
    """La ruta del receptor —la normal— no tiene nada nuestro que contrastar.

    Decía `"… · sin epicentro propio que comparar"` bajo un rótulo que prometía
    «contraste con catálogo»: una verificación anunciada que no había ocurrido.
    """
    linea = _catalog_line(
        _forensics(
            match=_match(),
            delta=CatalogDelta(km=None, bearing=None, dt_s=34.0),
            estado="confirmado",
            verificacion="no_verificable",
        )
    )
    assert linea is not None
    assert "NO VERIFICABLE" in linea
    assert "sin epicentro propio que contrastar" in linea
    assert "CONTRASTE" not in linea, (
        "la línea vuelve a presentar como contraste un acierto que no se pudo "
        "contrastar: es exactamente el defecto que T-5.11 corrige"
    )
    # Y da la distancia que SÍ se midió, que es la que decidió la identidad.
    assert "122 km del sitio" in linea


# ---- la magnitud, gobernada por la procedencia (T-5.10) ----------------------


@pytest.mark.parametrize("estado", ["preliminar", "confirmado"])
def test_con_procedencia_la_magnitud_se_imprime(estado: str) -> None:
    linea = _catalog_line(
        _forensics(
            match=_match(),
            delta=CatalogDelta(km=12.4, bearing="NE", dt_s=34.0),
            estado=estado,
            verificacion="contrastado",
        )
    )
    assert linea is not None and "M 7.1" in linea


@pytest.mark.parametrize("estado", ["sin_dato_externo", "consultando", "sin_correlacion"])
def test_SIN_procedencia_la_magnitud_NO_se_imprime(estado: str) -> None:
    """Casar no concede procedencia (regla de `T-5.10`).

    El dictamen es el sitio donde una cifra ajena sin procedencia se lee como
    propia: lleva una firma debajo. Es además el estado de **todas** las filas
    del catálogo hoy — las trece del seed no tienen hora de consulta.
    """
    linea = _catalog_line(
        _forensics(
            match=_match(),
            delta=CatalogDelta(km=12.4, bearing="NE", dt_s=34.0),
            estado=estado,
            verificacion="contrastado",
        )
    )
    assert linea is not None
    assert "M 7.1" not in linea, "la magnitud del catálogo se imprime sin procedencia citable"
    assert "no citable" in linea, "y tampoco se calla: se dice que existe y no se puede citar"


def test_sin_magnitud_en_el_catalogo_no_se_dice_nada_de_ella() -> None:
    """Ausente no es lo mismo que «no citable»: no hay cifra de la que hablar."""
    linea = _catalog_line(
        _forensics(
            match=_match(magnitude=None),
            delta=CatalogDelta(km=12.4, bearing="NE", dt_s=34.0),
            estado="confirmado",
            verificacion="contrastado",
        )
    )
    assert linea is not None
    assert "no citable" not in linea and " M " not in linea


# ---- «hay un evento en el catálogo pero no es el nuestro» --------------------


def test_los_descartes_se_IMPRIMEN_con_su_motivo() -> None:
    """Lo que el sistema no sabía decir, y por eso dejaba un hueco.

    Un hueco en un dictamen se lee como «no pasó nada», que es lo contrario de
    «hubo un sismo publicado y no es éste».
    """
    linea = _catalog_line(
        _forensics(
            estado="sin_correlacion",
            descartes=[
                CatalogDiscard(
                    catalog_key="SSN-CHILE",
                    motivo="fuera_de_radio",
                    detalle="el epicentro está fuera del radio máximo al sitio (6389 km)",
                    km_al_sitio=6389.0,
                )
            ],
        )
    )
    assert linea is not None
    assert linea.startswith("SIN CORRELACIÓN")
    assert "ninguno es éste" in linea
    assert "SSN-CHILE" in linea
    assert "fuera del radio" in linea


def test_sin_candidatos_la_linea_es_None_y_el_papel_pone_su_aviso() -> None:
    """`None` no es un olvido: es lo que enciende `SIN_CORRELACION_EN_CATALOGO`.

    Y sólo en este estado. `sin_correlacion` significa que la fuente CONTESTÓ y
    nada suyo es éste, que es justo lo que ese aviso afirma; para los otros dos
    hechos —no se preguntó, no contestaron— la línea existe y dice otra cosa.

    Que ese aviso llegue al documento lo prueba `test_avisos_impresos.py`.
    """
    assert _catalog_line(_forensics(estado="sin_correlacion")) is None


def test_la_linea_no_se_alarga_sin_tope_con_muchos_descartes() -> None:
    """Un feed vivo puede traer varios; el papel tiene un ancho y una firma."""
    muchos = [
        CatalogDiscard(catalog_key=f"EXT-{i}", motivo="fuera_de_radio", detalle="x" * 60)
        for i in range(10)
    ]
    linea = _catalog_line(_forensics(estado="sin_correlacion", descartes=muchos))
    assert linea is not None
    assert "10 evento(s)" in linea, "el conteo total se dice aunque no se enumeren todos"
    assert linea.count("EXT-") == 3, "se enumeran los tres primeros, no los diez"


# ---- la pregunta que sigue en vuelo -----------------------------------------


def test_con_la_consulta_SIN_CONTESTAR_el_papel_no_afirma_que_no_hay_correlacion() -> None:
    """[T-7.25] ⚠️ Era la mentira más cara del documento.

    Sin acierto, esta función devolvía `None`, y el PDF imprime
    `catalog_line or SIN_CORRELACION_EN_CATALOGO`: el papel firmaba «ningún
    sismo publicado satisface el criterio de identidad con este incidente»
    mientras la pregunta a la fuente seguía sin respuesta. Una cosa es un hecho
    sobre el sismo y la otra es una pregunta abierta; la primera exonera al
    catálogo y la segunda no dice nada todavía.
    """
    linea = _catalog_line(_forensics(estado="consultando", fuente="USGS", consultado_en=_T0))
    assert linea is not None, "devolver None es lo que enciende el aviso equivocado"
    assert linea.startswith(CONSULTA_EXTERNA_EN_VUELO)
    assert "SIN CORRELACIÓN" not in linea
    # Quién y cuándo: un «en curso» sin fecha es otra forma de no decir nada.
    assert "USGS" in linea
    assert f"{_T0:{TS_FMT}}" in linea


def test_sin_hora_de_consulta_la_linea_no_se_inventa_una() -> None:
    """Degrada, nunca inventa: se dice que está en curso y se calla la fecha."""
    linea = _catalog_line(_forensics(estado="consultando"))
    assert linea.startswith(CONSULTA_EXTERNA_EN_VUELO)
    assert "la fuente externa" in linea
    assert " el " not in linea


def test_en_vuelo_con_descartes_locales_los_dice_SIN_darlos_por_concluyentes() -> None:
    """Los descartes son del catálogo YA cargado, y eso no cierra la pregunta.

    Se imprimen porque son información —el operador quiere saber qué había en
    la ventana—, pero encabezados por el «en curso»: lo que no puede pasar es
    que un descarte local se lea como la respuesta de la fuente.
    """
    descarte = CatalogDiscard(
        catalog_key="SSN-2022-MICH",
        motivo="fuera_de_ventana",
        detalle="el origen es 4 h anterior",
    )
    linea = _catalog_line(
        _forensics(estado="consultando", fuente="USGS", consultado_en=_T0, descartes=[descarte])
    )
    assert linea.startswith(CONSULTA_EXTERNA_EN_VUELO)
    assert "SSN-2022-MICH" in linea
    assert "catálogo ya cargado" in linea


# ---- la pregunta que NADIE hizo ---------------------------------------------


def test_sin_consulta_el_papel_NO_afirma_nada_sobre_el_catalogo() -> None:
    """[T-7.25] ⚠️ La otra mitad de la mentira, y la del caso NORMAL.

    Con la consulta apagada —como se despliega— ningún incidente tiene fila de
    intento, así que ninguno se preguntó. Esta función devolvía `None` y el PDF
    imprime `catalog_line or SIN_CORRELACION_EN_CATALOGO`: el papel firmaba
    «ningún sismo publicado satisface el criterio de identidad con este
    incidente» de un incidente que nadie consultó. Exonerar al catálogo sin
    haberlo interrogado es afirmar lo que no consta, y va bajo firma.
    """
    linea = _catalog_line(_forensics(estado="sin_dato_externo"))
    assert linea is not None, "devolver None es lo que enciende el aviso equivocado"
    assert linea.startswith(SIN_CONSULTA_A_FUENTE_EXTERNA)
    assert "SIN CORRELACIÓN" not in linea
    assert "ni niega" in linea, "la línea tiene que dejar la pregunta abierta"


def test_sin_consulta_los_descartes_locales_se_dicen_SIN_cerrar_la_pregunta() -> None:
    """Lo que hay en el catálogo cargado es información y no es la respuesta.

    Se imprime —el operador quiere saber qué había en la ventana— encabezado por
    el hecho que manda: que a la fuente externa no se le preguntó. Lo que no
    puede pasar es que un descarte de nuestra propia tabla se lea como el
    veredicto de la fuente.
    """
    descarte = CatalogDiscard(
        catalog_key="SSN-2022-MICH",
        motivo="fuera_de_ventana",
        detalle="el origen es 4 h anterior",
    )
    linea = _catalog_line(_forensics(estado="sin_dato_externo", descartes=[descarte]))
    assert linea.startswith(SIN_CONSULTA_A_FUENTE_EXTERNA)
    assert "SSN-2022-MICH" in linea
    assert "catálogo ya cargado" in linea
    assert "SIN CORRELACIÓN" not in linea


# ---- la consulta que SÍ correlacionó, y el criterio de aquí que no ----------


#: Los estados que sólo se alcanzan CORRELACIONANDO: son exactamente los que
#: autorizan a pintar la cifra externa (`pinta_cifra` en el glosario). Derivados
#: y no tecleados, por lo mismo que el censo de abajo: tecleados eran dos y las
#: ramas del papel eran cero.
_CORRELACIONARON = [e for e in pr.estados() if pr.pinta_cifra(e)]


@pytest.mark.parametrize("estado", _CORRELACIONARON)
def test_una_consulta_que_CORRELACIONO_no_se_firma_como_SIN_CORRELACION(estado: str) -> None:
    """[T-7.25 · 4ª vuelta] ⚠️ El CUARTO hecho, impreso como el tercero.

    Cuando el worker escribió `outcome='correlacionado'` y la fila del catálogo
    es citable, el estado derivado es `preliminar` o `confirmado`. Si el
    ensamblado forense no encuentra ese acierto entre sus candidatos —la
    ventana y el radio de la consulta no son el criterio de identidad de
    `T-5.11`, y no tienen por qué coincidir— `f.catalog` llega en `None` y la
    línea la compone esta función. Medido antes del arreglo, con este mismo
    escenario: `None`, y el PDF imprime `catalog_line or
    SIN_CORRELACION_EN_CATALOGO`, o sea «ningún sismo publicado satisface el
    criterio de identidad con este incidente» sobre un incidente que SÍ
    correlacionó. Con un descarte en la ventana era peor todavía: la misma
    afirmación escrita a mano, «SIN CORRELACIÓN · 1 evento(s) … ninguno es éste».

    Lo que el papel tiene que decir es que los dos procedimientos DISCREPAN, no
    el desenlace más tranquilizador de los dos.
    """
    linea = _catalog_line(_forensics(estado=estado, fuente="USGS", consultado_en=_T0))
    assert linea is not None, (
        "devolver None es lo que enciende SIN_CORRELACION_EN_CATALOGO: el papel "
        "exonera al catálogo de un incidente que la consulta correlacionó"
    )
    assert linea.startswith(CORRELACION_EN_DISPUTA)
    assert "SIN CORRELACIÓN" not in linea
    # Quién y cuándo contestó, igual que en los otros hechos: una discrepancia
    # sin fuente ni hora no se puede ir a comprobar.
    assert "USGS" in linea
    assert f"{_T0:{TS_FMT}}" in linea
    # Y con qué confianza lo dijo la fuente, con la palabra del glosario: una
    # discrepancia contra una solución PRELIMINAR no pesa lo que una contra una
    # que la fuente ya revisó.
    assert pr.rotulo(estado, "consola") in linea


def test_los_descartes_locales_NO_cierran_la_discrepancia() -> None:
    """Lo que hay en el catálogo cargado es información, no el veredicto.

    Es la misma trampa de los otros dos hechos abiertos: un descarte de nuestra
    tabla, puesto al frente, se lee como la respuesta de la fuente — y aquí la
    fuente ya contestó, y contestó lo contrario.
    """
    descarte = CatalogDiscard(catalog_key="EXT-1", motivo="fuera_de_radio", detalle="lejos")
    linea = _catalog_line(
        _forensics(estado="confirmado", fuente="USGS", consultado_en=_T0, descartes=[descarte])
    )
    assert linea.startswith(CORRELACION_EN_DISPUTA)
    assert "catálogo ya cargado" in linea
    assert "EXT-1" in linea
    assert not linea.startswith("SIN CORRELACIÓN")


def test_la_discrepancia_sin_hora_de_respuesta_no_se_inventa_una() -> None:
    """Degrada, nunca inventa — la misma regla que en la pregunta en vuelo.

    La ausencia se mide por el sufijo «UTC» que estampa :data:`TS_FMT`, no por
    un « el » suelto: esa frase aparece dentro del propio texto de la disputa
    —«y el criterio de identidad»— y la comprobación habría pasado siempre.
    """
    linea = _catalog_line(_forensics(estado="preliminar"))
    assert linea.startswith(CORRELACION_EN_DISPUTA)
    assert "Contestó la fuente externa y" in linea
    assert "UTC" not in linea, "el papel se inventó una hora de respuesta que no consta"


# ---- el censo de los hechos, DERIVADO del glosario --------------------------


#: Con qué tiene que EMPEZAR la línea de cada estado de procedencia. Las claves
#: se comparan contra `pr.estados()` —`shared/glossary/procedencia.json`, la
#: única lista— y por eso un sexto estado no puede entrar al glosario sin pasar
#: por aquí.
_ENCABEZADO = {
    pr.SIN_DATO_EXTERNO: SIN_CONSULTA_A_FUENTE_EXTERNA,
    pr.CONSULTANDO: CONSULTA_EXTERNA_EN_VUELO,
    pr.PRELIMINAR: CORRELACION_EN_DISPUTA,
    pr.CONFIRMADO: CORRELACION_EN_DISPUTA,
    pr.SIN_CORRELACION: "SIN CORRELACIÓN",
}


def test_CADA_hecho_alcanzable_da_una_linea_DISTINTA_y_correcta() -> None:
    """La guarda de la separación, y ahora sobre los hechos que de verdad hay.

    ⚠️ **Esta prueba enumeraba TRES estados de cinco** —no se preguntó, no
    contestaron, ninguno casa— y por eso no vio nacer el defecto de la cuarta
    vuelta: `preliminar` y `confirmado` sin acierto salían por el `else` de
    `sin_correlacion` y el papel firmaba la exoneración. Un censo que enumera a
    mano acaba divergiendo; aquí ya divergió. El conjunto se DERIVA del glosario
    compartido, que es la única lista de estados del producto.

    Con el mismo escenario —un descarte en el catálogo cargado, que es lo que
    tienta a imprimir «ninguno es éste»— los cinco tienen que salir distintos y
    encabezados por SU frase: si dos coincidieran, el papel estaría contando lo
    mismo de situaciones que no lo son.
    """
    assert set(_ENCABEZADO) == set(pr.estados()), (
        "el glosario compartido y este censo discrepan; un estado sin frase "
        "propia se imprime como el de al lado: "
        f"{set(_ENCABEZADO) ^ set(pr.estados())}"
    )

    descarte = CatalogDiscard(catalog_key="EXT-1", motivo="fuera_de_radio", detalle="lejos")
    lineas = {
        estado: _catalog_line(
            _forensics(estado=estado, fuente="USGS", consultado_en=_T0, descartes=[descarte])
        )
        for estado in pr.estados()
    }

    assert all(v is not None for v in lineas.values()), (
        f"sin línea el PDF imprime SIN_CORRELACION_EN_CATALOGO: {lineas}"
    )
    assert len(set(lineas.values())) == len(pr.estados()), (
        f"dos hechos distintos se imprimen igual: {lineas}"
    )

    for estado, linea in lineas.items():
        assert linea.startswith(_ENCABEZADO[estado]), f"{estado} encabeza con: {linea!r}"
        assert ESTADO_DE_CONSULTA_NO_INTERPRETABLE not in linea, (
            f"{estado} está en el glosario y el papel no sabe traducirlo: le falta su rama"
        )
        if estado != pr.SIN_CORRELACION:
            assert "SIN CORRELACIÓN" not in linea, (
                f"{estado} exonera al catálogo de referencia, y sólo "
                f"{pr.SIN_CORRELACION} puede hacerlo: {linea!r}"
            )


def test_un_estado_que_el_papel_no_sabe_traducir_NO_exonera_al_catalogo() -> None:
    """El suelo de la función, que antes era la afirmación más cara del bloque.

    Todo lo que no fuera `sin_dato_externo` ni `consultando` caía al final y
    salía como «SIN CORRELACIÓN». Un sexto estado en el glosario heredaría eso
    en silencio; el censo de arriba lo caza, y mientras tanto el papel declara
    que no sabe en vez de exonerar a nadie.
    """
    linea = _catalog_line(_forensics(estado="un_sexto_estado"))
    assert linea is not None
    assert linea.startswith(ESTADO_DE_CONSULTA_NO_INTERPRETABLE)
    assert "un_sexto_estado" in linea, "el estado se dice: sin él nadie sabe qué hay que traducir"
    assert "SIN CORRELACIÓN" not in linea
