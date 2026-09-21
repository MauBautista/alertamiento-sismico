"""[T-7.24] El papel lee el mapa por la MISMA función que la consola, y sólo mapea.

## Qué se defiende aquí

Que el dictamen **no calcula el mapa**. Lo lee ya calculado, con
`takab_api.shakemap.lectura.leer` —la función que también sirve al endpoint— y lo
único que hace de su cosecha es traducir el GeoJSON a filas de papel.

No es aseo: si el PDF consultara por su cuenta, el papel y la pantalla dibujarían
cada uno su mapa del mismo sismo, y el que discrepa lleva una firma debajo. Es el
mismo razonamiento por el que el marco normativo (`T-2.82`) y el CCTV (`T-3.12.c`)
salen del ensamblador que sirve a la pantalla.

## Por qué el mapeo se prueba como función pura

Porque lo que puede tener una mentira es la traducción: `[lon, lat]` invertido, un
residuo que pierde el signo, o un `None` convertido en cero —que diría que ese
inmueble no se movió cuando lo que pasó es que no publicó (regla de oro 7)—.
Sembrar `incident_shakemap` para comprobar eso mediría el esquema, no el mapeo.

El enganche con la base sí se mide, pero con lo que la base dice HOY de un
incidente sin snapshot: `pendiente`, que además es la condición normal.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.dictamen import builder as builder_mod
from takab_api.dictamen.builder import bloque_de_shakemap, build_model
from takab_api.dictamen.pdf import render
from takab_api.schemas.shakemap import (
    AnilloFeature,
    AnilloProps,
    AnillosOut,
    EpicentroOut,
    NivelFueraOut,
    PoligonoGeometry,
    PuntoFeature,
    PuntoGeometry,
    PuntoProps,
    PuntosOut,
    ShakemapOut,
)
from takab_api.shakemap import calculo as shk

_CALCULADO = datetime(2026, 8, 3, 10, 5, 0, tzinfo=UTC)


def _salida(**over) -> ShakemapOut:
    base = {
        "incident_id": "11111111-2222-3333-4444-555555555555",
        "estado": shk.ESTADO_COMPLETO,
        "calculado_en": _CALCULADO,
        "ley": shk.LEY,
        "cobertura_km": 25.0,
        # Siempre presente, vacío incluido: el contrato lo declara obligatorio
        # para que quien pinta no tenga que distinguir «no vino» de «vino vacío».
        "fuera_de_alcance": [],
        "epicentro": EpicentroOut(
            lat=16.80,
            lon=-99.50,
            depth_km=10.0,
            magnitud=7.1,
            fuente="SSN",
            procedencia="confirmado",
        ),
        "observado": PuntosOut(
            features=[
                PuntoFeature(
                    # ⚠️ `[lon, lat]`, que es el orden de GeoJSON y el revés del
                    # que se escribe al hablar. Invertirlo pondría los inmuebles
                    # de México en Somalia y el croquis saldría igual de bonito.
                    geometry=PuntoGeometry(coordinates=[-98.30, 19.06]),
                    properties=PuntoProps(
                        site_id="s-1",
                        site_code="CHL-A",
                        site_name="Planta Cholula",
                        pga_g=0.081,
                        pgv_cms=3.2,
                        dist_km=187.0,
                        pga_g_modelada=0.041,
                        residuo_log10=0.31,
                        hypo_km=None,
                        medido_en=None,
                        voto_contado=None,
                    ),
                ),
                PuntoFeature(
                    geometry=PuntoGeometry(coordinates=[-99.13, 19.43]),
                    properties=PuntoProps(
                        site_id="s-2",
                        site_code="CDMX-1",
                        site_name="Torre CDMX",
                        pga_g=None,
                        pgv_cms=None,
                        dist_km=112.0,
                        hypo_km=None,
                        medido_en=None,
                        voto_contado=None,
                        pga_g_modelada=None,
                        residuo_log10=None,
                    ),
                ),
                # El tercero existe SÓLO para llevar un residuo NEGATIVO: el `mudo`
                # de arriba no puede tenerlo —no midió— y sin un punto que lo
                # traiga el signo se quedaba sin vigilancia.
                PuntoFeature(
                    geometry=PuntoGeometry(coordinates=[-99.90, 18.90]),
                    properties=PuntoProps(
                        site_id="s-3",
                        site_code="HOSP-01",
                        site_name="Hospital 01",
                        pga_g=0.012,
                        pgv_cms=0.6,
                        dist_km=90.0,
                        pga_g_modelada=0.068,
                        residuo_log10=-0.75,
                        hypo_km=None,
                        medido_en=None,
                        voto_contado=None,
                    ),
                ),
            ]
        ),
        "modelado": AnillosOut(
            features=[
                AnilloFeature(
                    geometry=PoligonoGeometry(coordinates=[[[-99.5, 16.8], [-99.5, 16.8]]]),
                    properties=AnilloProps(pga_g=0.07, radio_km=40.0, umbral="pga_watch_g"),
                )
            ]
        ),
    }
    return ShakemapOut(**{**base, **over})


def test_el_mapeo_conserva_la_LATITUD_en_su_sitio() -> None:
    """El GeoJSON viene `[lon, lat]` y el croquis proyecta `(lat, lon)`.

    Invertirlo no rompe nada visible —el croquis sale igual de bonito— y sitúa los
    inmuebles en otro continente. Por eso se comprueba con dos coordenadas que no
    se pueden confundir entre sí.
    """
    b = bloque_de_shakemap(_salida(), site_code="CHL-A")
    propio = b.puntos[0]
    assert (propio.lat, propio.lon) == (19.06, -98.30)


def test_el_inmueble_del_DICTAMEN_se_marca_como_propio_y_los_demas_no() -> None:
    """Es el sujeto del documento, no un testigo, y la figura lo dibuja distinto."""
    b = bloque_de_shakemap(_salida(), site_code="CHL-A")
    assert [p.propio for p in b.puntos] == [True, False, False]
    ajeno = bloque_de_shakemap(_salida(), site_code="OTRO-1")
    assert [p.propio for p in ajeno.puntos] == [False, False, False]


def test_un_inmueble_que_NO_publico_llega_como_ausencia_y_no_como_CERO() -> None:
    """Regla de oro 7: un cero por un silencio afirmaría que no se movió."""
    b = bloque_de_shakemap(_salida(), site_code="CHL-A")
    mudo = b.puntos[1]
    assert mudo.pga_g is None
    assert mudo.pgv_cms is None
    assert mudo.residuo_log10 is None


def test_el_residuo_y_la_ley_llegan_al_bloque_tal_cual() -> None:
    """El residuo es el producto de la ficha; la ley, lo que hace auditable el modelo."""
    b = bloque_de_shakemap(_salida(), site_code="CHL-A")
    assert b.puntos[0].residuo_log10 == 0.31
    assert b.puntos[0].pga_g_modelada == 0.041
    # ⚠️ Y el NEGATIVO, que es la mitad que de verdad se puede perder: medido con
    # mutación dirigida —un `abs()` en el mapeo—, comprobar sólo el positivo
    # dejaba el signo sin vigilancia, y el signo es todo lo que el residuo dice.
    assert b.puntos[2].residuo_log10 == -0.75
    assert b.ley == shk.LEY
    assert b.calculado_en == _CALCULADO
    assert b.cobertura_km == 25.0


def test_el_epicentro_llega_con_su_FUENTE_y_su_procedencia() -> None:
    """Sin ellas, el centroide de nuestro cuórum se confunde con la solución de una agencia."""
    b = bloque_de_shakemap(_salida(), site_code="CHL-A")
    assert (b.epicentro_lat, b.epicentro_lon) == (16.80, -99.50)
    assert b.epicentro_magnitud == 7.1
    assert b.epicentro_fuente == "SSN"
    assert b.epicentro_procedencia == "confirmado"


def test_sin_capa_modelada_el_bloque_se_queda_SIN_anillos() -> None:
    """`modelado=None` significa «no se modeló», no «se modeló y salió vacío».

    Convertirlo en una lista vacía perdería la diferencia, y la sección imprime
    cosas distintas en cada caso.
    """
    b = bloque_de_shakemap(
        _salida(estado=shk.ESTADO_SOLO_OBSERVADO, ley=None, modelado=None, epicentro=None),
        site_code="CHL-A",
    )
    assert b.anillos == []
    assert b.ley is None
    assert b.epicentro_lat is None
    assert b.estado == shk.ESTADO_SOLO_OBSERVADO


def test_los_niveles_SUPRIMIDOS_llegan_al_papel_con_su_motivo() -> None:
    """[T-7.24 · 3ª vuelta] El builder los tiraba, y sin ellos el papel mentía.

    Un mapa puede modelar cada inmueble y no tener un solo anillo: si todos los
    niveles caen bajo la superficie —el M5.0 con el foco a 48 km que acredita
    `tests/shakemap/test_calculo.py`— la capa 2 se queda vacía y la capa 3 no. Sin
    este campo la sección sólo podía decir «falta la capa modelada del snapshot»,
    que es falso: no falta nada, no cabe.

    El motivo viaja como CÓDIGO del vocabulario cerrado del cálculo, no como
    frase: la frase la pone quien imprime, de `MOTIVOS_FUERA`, y así el papel y la
    consola no pueden redactar dos razones distintas para el mismo mapa.
    """
    b = bloque_de_shakemap(
        _salida(
            modelado=None,
            fuera_de_alcance=[
                NivelFueraOut(
                    umbral="pga_watch_g",
                    pga_g=0.040,
                    motivo=shk.FUERA_BAJO_LA_SUPERFICIE,
                    radio_max_km=1200.0,
                )
            ],
        ),
        site_code="CHL-A",
    )
    assert b.anillos == []
    assert [(n.umbral, n.pga_g, n.motivo) for n in b.fuera_de_alcance] == [
        ("pga_watch_g", 0.040, shk.FUERA_BAJO_LA_SUPERFICIE)
    ]
    assert b.fuera_de_alcance[0].motivo in shk.MOTIVOS_FUERA, (
        "el motivo dejó de ser del vocabulario cerrado: el papel no sabría imprimirlo"
    )


def test_sin_lectura_el_bloque_declara_PENDIENTE() -> None:
    """`None` es lo que devuelve la lectura cuando el incidente no existe para quien pide.

    El papel no puede inventarse un mapa vacío: «no lo sé» y «no sacudió» son
    afirmaciones distintas, y sólo una de las dos es cierta.
    """
    b = bloque_de_shakemap(None, site_code="CHL-A")
    assert b.estado == shk.ESTADO_PENDIENTE
    assert b.puntos == []
    assert b.anillos == []


@pytest.mark.asyncio
async def test_el_builder_ENGANCHA_la_lectura_del_snapshot(base_data, make_incident) -> None:
    """Contra la base de verdad: un incidente sin mapa calculado sale `pendiente`.

    ⚠️ **`estado == "pendiente"` NO demuestra el enganche**, y por poco se queda
    así: es exactamente lo que da el `default_factory` del bloque, así que un
    `build_model` que no llamara a la lectura pasaría igual de verde. Lo que lo
    demuestra es `cobertura_km`: el bloque por defecto lo trae en `None` y el
    LECTOR pone el radio con el que se va a calcular, que nunca es nulo ni cero —un
    cero sería un número inventado sobre un mapa que todavía no existe—.

    Se comprueba además que la tabla está vacía para este incidente: si el arnés
    dejara un snapshot, el caso dejaría de medir lo que dice medir.
    """
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    engine = get_engine()
    async with engine.begin() as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))
        hay_fila = (
            await conn.execute(
                text("SELECT count(*) FROM incident_shakemap WHERE incident_id = CAST(:i AS uuid)"),
                {"i": iid},
            )
        ).scalar_one()

    assert m is not None
    assert hay_fila == 0, "el arnés dejó un snapshot y este caso ya no mide lo que dice"
    assert m.shakemap.estado == shk.ESTADO_PENDIENTE
    # Y el `cobertura_km` del lector, que NO es cero: es el radio con el que se VA
    # a calcular. Un cero sería un número inventado sobre un mapa que no existe.
    assert m.shakemap.cobertura_km is not None
    assert m.shakemap.cobertura_km > 0


@pytest.mark.parametrize(
    "explosion",
    [
        pytest.param(
            ProgrammingError(
                "SELECT …", {}, Exception('relation "incident_shakemap" does not exist')
            ),
            id="la tabla no existe (ventana de despliegue o rollback de la 0069)",
        ),
        pytest.param(
            ValidationError.from_exception_data("PuntoProps", []),
            id="el jsonb no valida contra `PuntoProps` (`site_name` es obligatorio)",
        ),
    ],
)
@pytest.mark.asyncio
async def test_un_fallo_leyendo_el_mapa_NO_deja_al_inmueble_SIN_DICTAMEN(
    base_data, make_incident, monkeypatch, explosion: Exception
) -> None:
    """**Best-effort, como el CCTV y la onda cruda.** La lectura iba desnuda.

    La doctrina está escrita a cinco líneas de la llamada, en `_cctv_block`: «un
    fallo leyendo el CCTV no puede impedir que se genere el dictamen: el vídeo es
    un anexo y el dictamen es lo que autoriza reocupar un edificio». La del mapa
    era la única que no la seguía. Medido el 2026-09-21 renombrando
    `incident_shakemap` dentro de una transacción con rollback: `build_model`
    moría con `UndefinedTable` y el inmueble se quedaba sin dictamen.

    Se prueban las DOS puertas medidas y no una: el atenuante del orden de
    despliegue —`deploy.sh` corre `alembic upgrade head` antes de tocar la API—
    sólo cubre la primera. Un `puntos` jsonb que no valide contra `PuntoProps`
    explota igual y ese orden no lo cubre.

    Y el fallo se DECLARA en vez de degradarse a `pendiente`: «no ha corrido el
    cálculo» y «no pude leerlo» son dos hechos distintos sobre el mismo incidente.
    """

    async def revienta(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise explosion

    monkeypatch.setattr(builder_mod, "leer_shakemap", revienta)

    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    engine = get_engine()
    async with engine.begin() as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))

    assert m is not None, "un anexo ilegible se llevó por delante el dictamen entero"
    assert m.shakemap.fallo_de_lectura is not None, (
        "el bloque salió sin declarar el fallo: un mapa ilegible impreso como "
        "`pendiente` afirma sobre el incidente algo que este documento no sabe"
    )
    # Y el resto del documento sigue: el dictamen es lo que autoriza reocupar.
    assert m.folio
    assert render(m, "technical").startswith(b"%PDF")


def test_el_bloque_leido_NO_declara_fallo_de_lectura() -> None:
    """El lado negativo: un `fallo_de_lectura` que saliera siempre no informa.

    Sin esta mitad, marcar el fallo incondicionalmente dejaría verde a la de
    arriba y **todos** los dictámenes imprimirían «MAPA NO DISPONIBLE» sobre mapas
    perfectamente calculados.
    """
    assert bloque_de_shakemap(_salida(), site_code="CHL-A").fallo_de_lectura is None
    assert bloque_de_shakemap(None, site_code="CHL-A").fallo_de_lectura is None
