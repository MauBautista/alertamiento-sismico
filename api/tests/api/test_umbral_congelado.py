"""[T-7.37] Los umbrales del dictamen se congelan al OCURRIR, no al exportar.

`T-7.35` resuelve los umbrales del inmueble **vigentes en la apertura del
incidente**, que es lo correcto. Pero la resolución ocurre **al exportar**: si
alguien podara versiones antiguas de `rule_sets` —o simplemente si el inmueble
se reconfigura—, un PDF regenerado el año que viene clasificaría el MISMO pico
contra otra banda. Un dictamen es un documento histórico y no puede cambiar de
opinión sobre lo que ya pasó.

⚠️ **Y el arrastre tiene que recorrer la CADENA, no solo la cabeza.** Al firmar,
`sign_dictamen` inserta una fila nueva con `basis = {}` o `{"notes": …}`: mirar
solo la cabeza perdería la congelación justo en el documento que más pesa.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import text

import auth_utils as au
from takab_api.db.engine import get_engine
from takab_api.dictamen.builder import build_model
from takab_api.main import create_app
from takab_api.routers.dictamens import router as dictamens_router

pytestmark = pytest.mark.asyncio

_OPENED = datetime(2026, 8, 3, 10, 0, 0, tzinfo=UTC)
#: Lo que regía cuando tembló.
_V7 = {"pga_watch_g": 0.021, "pga_trip_g": 0.091, "pgv_watch_cms": 1.51, "pgv_trip_cms": 6.01}
#: Lo que rige HOY, después de reconfigurar el inmueble. No puede aparecer.
_V8 = {"pga_watch_g": 0.301, "pga_trip_g": 0.701, "pgv_watch_cms": 9.91, "pgv_trip_cms": 20.01}


@pytest.fixture
def app() -> FastAPI:
    application = create_app()
    application.include_router(dictamens_router)
    return application


async def _rule_set(*, version: int, umbrales: dict, cuando: datetime) -> str:
    engine = get_engine()
    rs = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO rule_sets (rule_set_id, tenant_id, scope_type, scope_id, version, "
                "is_active, config, created_at) VALUES (CAST(:r AS uuid), CAST(:t AS uuid), "
                "'site', CAST(:s AS uuid), :v, true, CAST(:c AS jsonb), :at)"
            ),
            {
                "r": rs,
                "t": au.DB_TENANT_PRIV,
                "s": au.DB_SITE_PRIV,
                "v": version,
                "c": json.dumps({"edge": {"thresholds": umbrales}}),
                "at": cuando,
            },
        )
    return rs


async def _dictamen(incident_id: str, *, basis: dict) -> str:
    """La fila que emite el servicio, con su `basis` congelado."""
    engine = get_engine()
    did = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO dictamens (dictamen_id, tenant_id, incident_id, status, basis) "
                "VALUES (CAST(:d AS uuid), CAST(:t AS uuid), CAST(:i AS uuid), "
                "'inhabit_monitor', CAST(:b AS jsonb))"
            ),
            {"d": did, "t": au.DB_TENANT_PRIV, "i": incident_id, "b": json.dumps(basis)},
        )
    return did


async def _borrar_rule_set(rule_set_id: str) -> None:
    """La poda que el ficha teme: la versión que regía deja de existir."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM rule_sets WHERE rule_set_id = CAST(:r AS uuid)"), {"r": rule_set_id}
        )


def _congelado(umbrales: dict) -> dict:
    return {**umbrales, "origen": "inmueble", "rule_set_version": 7}


async def test_el_papel_usa_el_umbral_CONGELADO_aunque_se_pode_el_rule_set(
    base_data, make_incident
) -> None:
    """EL caso de esta ficha: la versión que regía se borra y el PDF se regenera."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED)
    rs = await _rule_set(version=7, umbrales=_V7, cuando=_OPENED - timedelta(days=1))
    await _dictamen(iid, basis={"rule_set_version": "v1", "felt_thresholds": _congelado(_V7)})
    await _borrar_rule_set(rs)

    engine = get_engine()
    async with engine.begin() as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))

    assert m is not None
    assert m.felt_thresholds["pga_trip_g"] == _V7["pga_trip_g"]
    assert m.felt_thresholds["rule_set_version"] == 7
    assert m.felt_thresholds["origen"] == "inmueble", (
        "sin el congelado se cae a la banda de referencia y el papel clasifica con "
        "números que no son del inmueble"
    )


async def test_reconfigurar_el_inmueble_NO_reclasifica_un_sismo_viejo(
    base_data, make_incident
) -> None:
    """El inmueble sube sus umbrales después. El dictamen no puede cambiar de
    opinión sobre lo que ya pasó."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED)
    await _rule_set(version=7, umbrales=_V7, cuando=_OPENED - timedelta(days=1))
    await _dictamen(iid, basis={"felt_thresholds": _congelado(_V7)})
    # Una versión NUEVA, pero con `created_at` anterior a la apertura: es el caso
    # que engaña a la resolución por tiempo (un alta retroactiva, una migración
    # de datos, un reloj mal puesto).
    await _rule_set(version=8, umbrales=_V8, cuando=_OPENED - timedelta(hours=1))

    engine = get_engine()
    async with engine.begin() as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))

    assert m.felt_thresholds["pga_trip_g"] == _V7["pga_trip_g"]
    assert m.felt_thresholds["pga_trip_g"] != _V8["pga_trip_g"]


async def test_sin_congelacion_se_resuelve_COMO_ANTES(base_data, make_incident) -> None:
    """Los documentos anteriores a esta ficha no se quedan sin banda: el respaldo
    sigue siendo la resolución por tiempo de `T-7.35`."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED)
    await _rule_set(version=7, umbrales=_V7, cuando=_OPENED - timedelta(days=1))
    await _dictamen(iid, basis={"rule_set_version": "v1"})  # sin `felt_thresholds`

    engine = get_engine()
    async with engine.begin() as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))

    assert m.felt_thresholds["pga_trip_g"] == _V7["pga_trip_g"]
    assert m.felt_thresholds["rule_set_version"] == 7


async def test_la_FIRMA_arrastra_el_umbral_congelado(app, base_data, make_incident) -> None:
    """⚠️ `sign_dictamen` escribe `basis = {}` o `{"notes": …}`.

    Sin el arrastre, la fila de más peso legal del sistema nace sin la
    congelación y la cadena vuelve a depender de que nadie pode `rule_sets`.
    """
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED)
    await _rule_set(version=7, umbrales=_V7, cuando=_OPENED - timedelta(days=1))
    await _dictamen(iid, basis={"felt_thresholds": _congelado(_V7)})

    headers = au.bearer(au.make_token("inspector", tenant=au.DB_TENANT_PRIV))
    async with au.client_for(app) as client:
        r = await client.post(
            f"/incidents/{iid}/dictamens",
            headers=headers,
            json={"status": "inhabit_monitor", "notes": "revisión en sitio"},
        )
    assert r.status_code in (200, 201), r.text

    engine = get_engine()
    async with engine.begin() as conn:
        fila = (
            await conn.execute(
                text(
                    "SELECT basis FROM dictamens WHERE incident_id = CAST(:i AS uuid) "
                    "AND signed_by IS NOT NULL ORDER BY created_at DESC LIMIT 1"
                ),
                {"i": iid},
            )
        ).first()
    assert fila is not None, "no se insertó la fila firmada"
    assert fila.basis.get("felt_thresholds") == _congelado(_V7), (
        "la firma perdió la congelación de umbrales"
    )
    assert fila.basis.get("notes") == "revisión en sitio", "y se llevó por delante la nota"


async def test_el_papel_de_una_cadena_FIRMADA_sigue_teniendo_el_umbral(
    app, base_data, make_incident
) -> None:
    """La comprobación de punta a punta: firmar y exportar después de podar."""
    iid = await make_incident(au.DB_TENANT_PRIV, au.DB_SITE_PRIV, opened_at=_OPENED)
    rs = await _rule_set(version=7, umbrales=_V7, cuando=_OPENED - timedelta(days=1))
    await _dictamen(iid, basis={"felt_thresholds": _congelado(_V7)})

    headers = au.bearer(au.make_token("inspector", tenant=au.DB_TENANT_PRIV))
    async with au.client_for(app) as client:
        await client.post(
            f"/incidents/{iid}/dictamens",
            headers=headers,
            json={"status": "inhabit_monitor"},
        )
    await _borrar_rule_set(rs)

    engine = get_engine()
    async with engine.begin() as conn:
        m = await build_model(conn, iid, generated_at=datetime.now(UTC))

    assert m.verdict_signed is True, "el test no está midiendo una cadena firmada"
    assert m.felt_thresholds["pga_trip_g"] == _V7["pga_trip_g"]


async def test_las_DOS_consultas_de_umbrales_eligen_la_MISMA_fila(base_data) -> None:
    """La resolución vive en dos SQL: `queries/forensics._THRESHOLDS_IN_FORCE`
    (SQLAlchemy async, al exportar) y `dictamen/service._UMBRALES_SQL` (psycopg
    sync, al emitir). Son la misma pregunta escrita dos veces porque los dos
    caminos usan drivers distintos, y **dos consultas del mismo hecho divergen
    solas**: el que congela y el que respalda tienen que elegir la misma versión
    o el papel diría una cosa u otra según por dónde pasara.

    Se comprueba por COMPORTAMIENTO, no comparando los textos: el empate entre
    ámbito de sitio, `created_at` y `version` es justo donde se separarían.
    """
    import psycopg
    from psycopg.rows import dict_row

    from conftest import _dsn
    from takab_api.dictamen.service import _UMBRALES_SQL
    from takab_api.queries.forensics import thresholds_in_force

    # Tres candidatas: la del cliente, una del sitio anterior y la que gana.
    await _rule_set(version=3, umbrales=_V8, cuando=_OPENED - timedelta(days=30))
    await _rule_set(version=7, umbrales=_V7, cuando=_OPENED - timedelta(days=1))
    await _rule_set(version=9, umbrales=_V8, cuando=_OPENED + timedelta(days=1))  # posterior

    engine = get_engine()
    async with engine.begin() as conn:
        fila_async = await thresholds_in_force(
            conn, site_id=au.DB_SITE_PRIV, tenant_id=au.DB_TENANT_PRIV, at=_OPENED
        )
    with psycopg.connect(_dsn(), row_factory=dict_row) as raw:
        fila_sync = raw.execute(
            _UMBRALES_SQL,
            {"at": _OPENED, "site": au.DB_SITE_PRIV, "tenant": au.DB_TENANT_PRIV},
        ).fetchone()

    assert fila_async is not None and fila_sync is not None
    assert dict(fila_async._mapping) == fila_sync
    assert fila_sync["version"] == 7, "ninguna de las dos eligió la que regía"
