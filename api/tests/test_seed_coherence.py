"""T-2.115 · El veredicto de un test no puede depender del ORDEN DE RECOLECCIÓN.

`tests/auth/conftest.py` y `tests/api/conftest.py` sembraban **las mismas filas** —los
UUIDs de tenant y sitio salen de ``auth_utils``— con valores distintos y
``ON CONFLICT DO NOTHING``. Ni ``tenants`` ni ``sites`` entran en el ``TRUNCATE`` de
teardown, así que la fila sobrevive a todo el proceso y a la corrida anterior: **ganaba
quien corriese primero**. Medido en las dos direcciones (2026-08-10):

    pytest -q tests/auth tests/api   ⇒ 1 failed, 811 passed
        tests/api/test_events.py::test_los_votos_traen_el_codigo_de_la_estacion
        AssertionError: assert 'SA' == 'B2SA'
    pytest -q tests/api tests/auth   ⇒ verde

Misma familia que T-2.73.c: la suite dice cosas distintas según cómo la invoques, y eso
erosiona la confianza en todos los rojos futuros.

Los tres candados de este fichero, de más barato a más caro:

1. **Estructural** — ningún conftest de familia vuelve a escribir esas filas por su
   cuenta; pasan por ``tests/seed_shared.py``, que además debe ser AUTORITATIVO
   (``DO UPDATE``). Un ``DO NOTHING`` ahí reabriría el defecto en silencio.
2. **Funcional** — con la fila envenenada, sembrar la deja en su valor canónico. Es la
   diferencia entre "el primero gana" y "el valor no depende de quién llegue".
3. **De extremo a extremo** — un pytest hijo que corre las dos familias EN EL ORDEN
   MALO, con la fila envenenada de antemano para que no pueda salir verde por inercia
   del estado que dejó la corrida anterior.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import auth_utils as au
import seed_shared

API_DIR = Path(__file__).resolve().parents[1]
_CONFTESTS = (
    API_DIR / "tests" / "auth" / "conftest.py",
    API_DIR / "tests" / "api" / "conftest.py",
)

#: Valor imposible con el que se envenena la fila compartida antes de medir. Si el
#: test sale verde con esto dentro, es porque la siembra lo corrigió — no por inercia.
VENENO = "ORDEN-MALO-T2115"

#: Las dos familias, en el orden que rompía. El nodo de `tests/api` es exactamente el
#: test que se ponía rojo; el fichero de `tests/auth` es uno que pide `base_tenants`
#: (vía `make_incident`), que es quien siembra.
ORDEN_MALO = (
    "tests/auth/test_gov_ack.py",
    "tests/api/test_events.py::test_los_votos_traen_el_codigo_de_la_estacion",
)


def _dsn() -> str | None:
    url = os.environ.get("DATABASE_URL")
    return url.replace("postgresql+psycopg://", "postgresql://") if url else None


# --- 1. Candado estructural (sin DB) -------------------------------------------


@pytest.mark.parametrize("ruta", _CONFTESTS, ids=lambda p: p.parent.name)
def test_ninguna_familia_siembra_por_su_cuenta_las_filas_compartidas(ruta: Path) -> None:
    """Las filas compartidas se escriben en UN solo sitio, no una vez por familia."""
    fuente = ruta.read_text(encoding="utf-8")
    assert "seed_shared_rows" in fuente, (
        f"{ruta.relative_to(API_DIR)} debe sembrar tenants/sitios compartidos con "
        "`seed_shared.seed_shared_rows`, no con su propia copia (T-2.115)."
    )
    for tabla in ("tenants", "sites"):
        assert f"INSERT INTO {tabla}" not in fuente, (
            f"{ruta.relative_to(API_DIR)} volvió a escribir `{tabla}` por su cuenta: es "
            "la fila que comparte con la otra familia y así el orden de recolección "
            "vuelve a decidir el veredicto (T-2.115)."
        )


def test_la_siembra_compartida_declara_ser_autoritativa() -> None:
    """`DO NOTHING` en las filas compartidas ES el defecto: queda vetado por contrato."""
    for sentencia in (seed_shared.UPSERT_TENANT, seed_shared.UPSERT_SITE):
        sql = str(sentencia).upper()
        assert "DO UPDATE" in sql, f"la siembra compartida no es autoritativa: {sentencia}"
        assert "DO NOTHING" not in sql, (
            "`ON CONFLICT DO NOTHING` sobre una fila compartida hace que gane quien "
            f"corra primero — exactamente T-2.115: {sentencia}"
        )


def test_los_codigos_compartidos_son_los_que_las_pruebas_afirman() -> None:
    """`tests/api/test_events.py` afirma `B2SA`; el valor canónico tiene que ser ese."""
    codigos = {sid: code for sid, _tid, code in seed_shared.SHARED_SITES}
    assert codigos[au.DB_SITE_PRIV] == "B2SA"


# --- 2. Candado funcional: envenenar y volver a sembrar -------------------------


async def test_la_siembra_corrige_la_fila_envenenada() -> None:
    """Con la fila en un valor ajeno, sembrar la devuelve a su valor canónico.

    Todo ocurre dentro de una transacción que se REVIERTE: la suite que rodea a este
    test no ve nada. Antes del arreglo (``DO NOTHING``) el veneno sobrevivía a la
    siembra, que es la definición operativa de "gana quien corra primero".
    """
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("sin DATABASE_URL")
    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as conn:
            txn = await conn.begin()
            try:
                await seed_shared.seed_shared_rows(conn)  # la fila existe con certeza
                await conn.execute(
                    text("UPDATE sites SET code = :veneno WHERE site_id = :sid"),
                    {"veneno": VENENO, "sid": au.DB_SITE_PRIV},
                )
                await conn.execute(
                    text("UPDATE tenants SET code = :veneno WHERE tenant_id = :tid"),
                    {"veneno": VENENO, "tid": au.DB_TENANT_PRIV},
                )

                await seed_shared.seed_shared_rows(conn)

                site_code = (
                    await conn.execute(
                        text("SELECT code FROM sites WHERE site_id = :sid"),
                        {"sid": au.DB_SITE_PRIV},
                    )
                ).scalar_one()
                tenant_code = (
                    await conn.execute(
                        text("SELECT code FROM tenants WHERE tenant_id = :tid"),
                        {"tid": au.DB_TENANT_PRIV},
                    )
                ).scalar_one()
            finally:
                await txn.rollback()
    finally:
        await engine.dispose()

    assert site_code == "B2SA", "la siembra no corrigió el sitio: sigue ganando el primero"
    assert tenant_code == "B2_A", "la siembra no corrigió el tenant: sigue ganando el primero"


# --- 3. Candado de extremo a extremo: las dos familias, en el orden malo --------


def _envenenar(dsn: str) -> None:
    """Deja la fila compartida en un valor ajeno, COMMITEADO, para el pytest hijo."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("UPDATE sites SET code = %s WHERE site_id = %s", (VENENO, au.DB_SITE_PRIV))


def _restaurar(dsn: str) -> None:
    canonico = {sid: code for sid, _t, code in seed_shared.SHARED_SITES}[au.DB_SITE_PRIV]
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "UPDATE sites SET code = %s WHERE site_id = %s AND code = %s",
            (canonico, au.DB_SITE_PRIV, VENENO),
        )


def test_el_orden_malo_de_recoleccion_sigue_verde() -> None:
    """Un pytest hijo con `tests/auth` ANTES que `tests/api`: tiene que salir verde.

    Corre en un proceso aparte porque el orden de recolección es una propiedad del
    proceso de pytest, no de un test. Se envenena la fila compartida justo antes: sin
    eso, el hijo saldría verde por lo que dejó sembrado la corrida anterior —un falso
    verde— en vez de por el arreglo.
    """
    dsn = _dsn()
    if not dsn:
        pytest.skip("sin DATABASE_URL")
    _envenenar(dsn)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--no-header",
                "-p",
                "no:randomly",
                "-p",
                "no:cacheprovider",
                *ORDEN_MALO,
            ],
            cwd=API_DIR,
            env={**os.environ},
            capture_output=True,
            text=True,
            timeout=600,
        )
    finally:
        _restaurar(dsn)
    assert proc.returncode == 0, (
        "correr `tests/auth` antes que `tests/api` volvió a cambiar el veredicto "
        f"(T-2.115).\n--- stdout ---\n{proc.stdout[-4000:]}\n--- stderr ---\n"
        f"{proc.stderr[-2000:]}"
    )
