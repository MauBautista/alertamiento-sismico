"""[T-9.53 · D-44] El builder del dictamen lleva la superficie al papel, o la calcula.

Contra la base, con el escenario de `tests/shakemap/test_pasada.py` (dos inmuebles,
el epicentro de Puebla-Morelos 2017): sembrar otra red aquí haría que dos suites
midieran cosas distintas.

1. **Con snapshot**, la superficie llega del MISMO lector que la consola
   (`lectura.leer_con_malla`), con los umbrales de banda DEL SITIO.
2. **Sin snapshot**, el builder no imprime «NO CALCULADO TODAVÍA»: calcula en
   memoria con `servicio.calcula_uno` —sin persistir— y el papel lo dice.
3. **Si ese cálculo revienta**, el dictamen sale igual y lo declara: un anexo no
   puede costar el documento que autoriza reocupar un edificio.
"""

# ruff: noqa: F811  (fixtures de pytest importadas por nombre)
from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from takab_api.dictamen import builder as builder_mod
from takab_api.dictamen.builder import build_model
from takab_api.dictamen.model import ReportModel
from takab_api.dictamen.pdf import render
from takab_api.shakemap import calculo as C
from takab_api.shakemap import superficie as SUP
from tests.shakemap.test_mapa_de_calor import _calibra
from tests.shakemap.test_pasada import (  # noqa: F401  (fixture de pytest, por nombre)
    NOW,
    PGA_CDMX,
    PGA_PUEBLA,
    Escenario,
    _settings,
    esc,
)


def _modelo(inc: str, generado: datetime = NOW) -> ReportModel | None:
    async def _corre() -> ReportModel | None:
        settings = _settings()
        motor = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with motor.begin() as conn:
                return await build_model(conn, inc, generated_at=generado, settings=settings)
        finally:
            await motor.dispose()

    return asyncio.run(_corre())


def test_con_snapshot_el_bloque_lleva_la_SUPERFICIE_y_la_banda_del_sitio(esc: Escenario) -> None:
    _calibra(esc, "CDMX")
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.mide("PUEBLA", PGA_PUEBLA)
    assert esc.pasada().calculados == (inc,)

    m = _modelo(inc)
    assert m is not None
    b = m.shakemap
    assert b.calculado_para_el_documento is False, "había snapshot: no se calculó a demanda"
    assert b.superficie is not None
    assert (b.superficie.n_sensores, b.superficie.n_calibrados) == (2, 1)
    assert b.superficie_motivo is None
    # Sin `rule_set` del sitio, los por defecto del dictamen v2: los mismos que el PNG.
    settings = _settings()
    assert (b.banda_verde_max_g, b.banda_rojo_min_g) == (
        settings.dictamen_verde_max_g,
        settings.dictamen_rojo_min_g,
    )
    assert render(m, "technical").startswith(b"%PDF")


def test_con_snapshot_SIN_superficie_llega_el_motivo(esc: Escenario) -> None:
    inc = esc.incidente()
    esc.mide("CDMX", PGA_CDMX)
    esc.pasada()
    b = _modelo(inc).shakemap
    assert b.superficie is None
    assert b.superficie_motivo == SUP.MOTIVO_SIN_CALIBRADOS


def test_SIN_snapshot_se_calcula_para_este_documento_y_no_se_persiste(esc: Escenario) -> None:
    _calibra(esc, "CDMX")
    inc = esc.incidente(en_revision=False)
    esc.mide("CDMX", PGA_CDMX)
    assert esc.snapshot(inc) is None

    m = _modelo(inc)
    b = m.shakemap
    assert b.calculado_para_el_documento is True
    assert b.estado == C.ESTADO_COMPLETO, "a demanda salió otra cosa que lo que la pasada escribe"
    assert b.superficie is not None and b.superficie.n_calibrados == 1
    assert b.calculado_en == NOW, "el instante del cálculo es el de ESTE documento"
    assert b.banda_verde_max_g is not None
    assert esc.snapshot(inc) is None, "el cálculo a demanda escribió un snapshot"


def test_si_el_calculo_a_demanda_REVIENTA_el_dictamen_sale_y_lo_declara(
    esc: Escenario, monkeypatch
) -> None:
    async def revienta(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("la vista segura de features no respondió")

    monkeypatch.setattr(builder_mod, "calcula_uno", revienta)
    inc = esc.incidente(en_revision=False)
    esc.mide("CDMX", PGA_CDMX)

    m = _modelo(inc)
    assert m is not None, "un anexo que no se pudo calcular se llevó el dictamen entero"
    assert m.shakemap.fallo_de_calculo is not None
    assert m.shakemap.fallo_de_lectura is None, "no falló la lectura: falló el cálculo"
    assert m.shakemap.estado == C.ESTADO_PENDIENTE
    assert render(m, "technical").startswith(b"%PDF")
