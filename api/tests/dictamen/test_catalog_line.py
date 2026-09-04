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

from takab_api.dictamen.builder import _catalog_line
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
