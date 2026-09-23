"""[T-8.12 · A-053 · A-139] Lo que una PERSONA decidió que fue el incidente, en el papel.

El papel no rotulaba la clasificación humana (`incident_classifications`). Un
golpe en la losa clasificado a mano como `reproduccion` —así se clasifican los
ensayos de `T-7.28`— salía como un incidente REAL, con veredicto y con «el
sensor midió…» en la portada.

Lo que se fija, y en este orden:

1. **Portada y ejecutivo** imprimen «CLASIFICACIÓN: …» con la etiqueta en
   castellano y cuándo se asignó; «SIN CLASIFICAR» si nadie lo ha hecho.
2. **Es ADITIVA.** La leyenda REPRODUCCIÓN se sigue derivando de
   `seismic_events.meta.reproduccion` —la misma que lee la consola— y NO de la
   clasificación: las dos se imprimen, ninguna tapa a la otra.
3. **«No legible» no es «sin clasificar».** La RLS de la tabla compara con el
   tenant de la sesión sin rama interna; el superadmin que exporta el incidente
   de un cliente NO la ve. Con el tenant vacío, además, la consulta revienta y
   abortaría la exportación: el builder no la lanza.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.db.session import SessionCtx, get_tenant_conn
from takab_api.dictamen import rotulos
from takab_api.dictamen.builder import build_model
from takab_api.dictamen.model import (
    CLASIFICACION_NO_LEGIBLE,
    REPRODUCCION_NOTE,
    SIN_CLASIFICAR,
)
from takab_api.dictamen.pdf import render
from tests.dictamen.test_pdf import model
from tests.documentos.espia import espia_del_render

_CLASIFICADA = datetime(2026, 9, 22, 18, 2, tzinfo=UTC)


def _cap(m, variante: str = "technical"):  # noqa: ANN001, ANN202
    with espia_del_render() as cap:
        render(m, variante)
    return cap


def _encabezado(cap, variante: str) -> str:  # noqa: ANN001
    """Lo que se lee ANTES del cuerpo: la portada del pericial, o lo que va antes
    de «QUÉ PASÓ» en el ejecutivo."""
    return cap.portada()


# ───────────────────────────────────────────────────────── 1. portada y ejecutivo


@pytest.mark.parametrize("variante", ["technical", "executive"])
@pytest.mark.parametrize("clasificacion", sorted(rotulos.CLASIFICACION))
def test_la_CLASIFICACION_va_en_la_portada_y_en_el_ejecutivo(
    variante: str, clasificacion: str
) -> None:
    cap = _cap(model(clasificacion=clasificacion, clasificacion_en=_CLASIFICADA), variante)
    arriba = _encabezado(cap, variante)
    assert "CLASIFICACIÓN" in arriba
    assert rotulos.CLASIFICACION[clasificacion] in arriba
    assert "2026-09-22 18:02 UTC · 12:02 hora del centro" in arriba, "sin cuándo se clasificó"
    assert SIN_CLASIFICAR not in cap.texto


@pytest.mark.parametrize("variante", ["technical", "executive"])
def test_SIN_CLASIFICAR_cuando_nadie_lo_ha_hecho(variante: str) -> None:
    arriba = _encabezado(_cap(model(), variante), variante)
    assert "CLASIFICACIÓN" in arriba
    assert SIN_CLASIFICAR in arriba


@pytest.mark.parametrize("variante", ["technical", "executive"])
def test_NO_LEGIBLE_no_se_disfraza_de_sin_clasificar(variante: str) -> None:
    cap = _cap(model(clasificacion_legible=False), variante)
    assert CLASIFICACION_NO_LEGIBLE in _encabezado(cap, variante)
    assert SIN_CLASIFICAR not in cap.texto, (
        "el papel afirma que nadie lo clasificó cuando lo que pasa es que quien "
        "exporta no puede leerlo"
    )


# ───────────────────────────────────────────── 2. aditiva: la leyenda NO cambia


def test_la_leyenda_de_REPRODUCCION_sigue_saliendo_del_EVENTO() -> None:
    """Clasificado `real` y evento de reproducción: las DOS cosas, sin taparse."""
    cap = _cap(model(reproduccion=True, clasificacion="real", clasificacion_en=_CLASIFICADA))
    assert REPRODUCCION_NOTE in cap.seccion("RED DE ESTACIONES"), "la §7 perdió su leyenda"
    assert REPRODUCCION_NOTE in cap.portada()
    assert "REAL" in cap.portada()


def test_clasificar_REPRODUCCION_no_inventa_la_leyenda_del_EVENTO() -> None:
    """La leyenda afirma algo del EVENTO (epicentro y magnitud de un sismo
    histórico). Una clasificación humana no lo convierte en eso: se imprime la
    clasificación, y la leyenda sigue dependiendo sólo de `meta.reproduccion`."""
    cap = _cap(model(reproduccion=False, clasificacion="reproduccion"))
    assert "REPRODUCCIÓN" in cap.portada()
    assert REPRODUCCION_NOTE not in cap.texto


def test_el_EJECUTIVO_lleva_la_leyenda_de_reproduccion() -> None:
    """A-139: el ejecutivo afirma «el sensor del inmueble midió un pico de…»."""
    cap = _cap(model(reproduccion=True), "executive")
    assert REPRODUCCION_NOTE in cap.portada()


def test_la_clasificacion_entra_en_la_HUELLA() -> None:
    """Cambiar lo que el papel afirma que fue el incidente tiene que mover la huella."""
    assert (
        model(clasificacion="real").content_sha256()
        != model(clasificacion="falso_positivo").content_sha256()
    )


# ─────────────────────────────────────── 3. el builder, contra la base de verdad


async def _clasifica(tenant: str, iid: str, valor: str, *, sustituye: str | None = None) -> str:
    cid = str(uuid.uuid4())
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO incident_classifications (classification_id, tenant_id, "
                "incident_id, classification, classified_by, supersedes_id) "
                "VALUES (:c, :t, :i, :v, gen_random_uuid(), CAST(:s AS uuid))"
            ),
            {"c": cid, "t": tenant, "i": iid, "v": valor, "s": sustituye},
        )
    return cid


def _ctx(role: str, tenant: str) -> SessionCtx:
    return SessionCtx(tenant_id=tenant, role=role, user_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_el_builder_lee_la_clasificacion_VIGENTE(base_data, make_incident) -> None:
    """La que nadie sustituye, aunque haya otra más antigua."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    primera = await _clasifica(au.DB_TENANT_PRIV, iid, "real")
    await _clasifica(au.DB_TENANT_PRIV, iid, "reproduccion", sustituye=primera)

    async with get_tenant_conn(_ctx("inspector", au.DB_TENANT_PRIV)) as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))
    assert m is not None
    assert m.clasificacion_legible is True
    assert m.clasificacion == "reproduccion"
    assert m.clasificacion_en is not None


@pytest.mark.asyncio
async def test_el_builder_sin_clasificacion_da_None(base_data, make_incident) -> None:
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    async with get_tenant_conn(_ctx("inspector", au.DB_TENANT_PRIV)) as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))
    assert m is not None
    assert m.clasificacion is None and m.clasificacion_legible is True


@pytest.mark.parametrize("tenant", ["", au.DB_TENANT_PRIV2], ids=["tenant vacío", "otro tenant"])
@pytest.mark.asyncio
async def test_el_SUPERADMIN_de_otro_tenant_NO_aborta_la_exportacion(
    base_data, make_incident, tenant: str
) -> None:
    """Con el tenant vacío la consulta a la tabla REVIENTA (medido): el builder no
    puede lanzarla. Y con otro tenant devuelve cero filas, que NO es «sin
    clasificar». En los dos casos: `clasificacion_legible=False` y el documento sale.
    """
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await _clasifica(au.DB_TENANT_PRIV, iid, "prueba")
    async with get_tenant_conn(_ctx("takab_superadmin", tenant)) as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))
        # La transacción sigue viva: si el builder hubiera lanzado la consulta con
        # el tenant vacío, esta línea fallaría con `InFailedSqlTransaction`.
        assert (await conn.execute(text("SELECT 1"))).scalar_one() == 1
    assert m is not None
    assert m.clasificacion_legible is False
    assert m.clasificacion is None


@pytest.mark.asyncio
async def test_la_consulta_con_tenant_VACIO_revienta_de_verdad(base_data, make_incident) -> None:
    """La premisa de la guarda de arriba, medida: sin ella, esa guarda protegería
    de un fallo imaginario. Si la política de la tabla cambia (una rama interna,
    un `nullif`), esto se pone rojo y la guarda puede simplificarse."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV)
    await _clasifica(au.DB_TENANT_PRIV, iid, "prueba")
    with pytest.raises(Exception, match="invalid input syntax for type uuid"):
        async with get_tenant_conn(_ctx("takab_superadmin", "")) as conn:
            await conn.execute(text("SELECT count(*) FROM incident_classifications"))
