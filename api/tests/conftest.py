"""Fixtures de los tests de esquema/RLS (T-1.16).

Los tests se conectan como el superusuario de la conexión (el usuario de
``DATABASE_URL``) y usan ``SET ROLE`` + ``set_config('app.*', …, is_local=true)``
por transacción para simular el contexto que la API establece en producción
(``takab_app``/``takab_ingest``/``takab_migrator`` + ``app.tenant_id``/``app.role``/
``app.user_id``). Cada test corre en una transacción que se revierte al final →
aislamiento total y sin datos residuales. Sin passwords: ``SET ROLE`` desde el
superusuario evita credenciales por rol (regla de oro 6).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

API_DIR = Path(__file__).resolve().parents[1]

DEFAULT_URL = "postgresql+psycopg://takab:takab_dev@localhost:5433/takab"

# Roles de conexión permitidos en el helper `use` (allowlist → no inyección en SET ROLE).
DB_ROLES = frozenset({"takab_app", "takab_ingest", "takab_migrator"})

# UUIDs fijos del seed (legibilidad de los asserts).
TENANT_A = "11111111-1111-1111-1111-111111111111"  # private
TENANT_B = "22222222-2222-2222-2222-222222222222"  # private
TENANT_G = "33333333-3333-3333-3333-333333333333"  # gov_shared
SITE_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SITE_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SITE_G = "cccccccc-cccc-cccc-cccc-cccccccccccc"
GW_A = "a1a1a1a1-0000-0000-0000-000000000001"
GW_B = "b1b1b1b1-0000-0000-0000-000000000002"
SENSOR_A = "a2a2a2a2-0000-0000-0000-000000000001"
SENSOR_B = "b2b2b2b2-0000-0000-0000-000000000002"
INC_A = "a3a3a3a3-0000-0000-0000-000000000001"
INC_G = "c3c3c3c3-0000-0000-0000-000000000003"
EVT_A = "a4a4a4a4-0000-0000-0000-000000000001"
EVT_G = "c4c4c4c4-0000-0000-0000-000000000003"
# tenant "de agencia" del gov_operator: distinto de A/B/G para que la visibilidad
# gov dependa SOLO de la rama gov_shared, no de tenant_id = app_tenant_id().
GOV_AGENCY = "99999999-9999-9999-9999-999999999999"

TS = "2026-07-06 10:00:00+00"


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    return url.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture(scope="session", autouse=True)
def _migrated() -> None:
    """Aplica la migración (idempotente) una vez por sesión de tests."""
    env = {**os.environ}
    env.setdefault("DATABASE_URL", DEFAULT_URL)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        check=True,
        capture_output=True,
        env=env,
    )


# --- T-2.122 · una corrida no puede heredar el veredicto de la anterior ---------

#: Única tabla de `public` que sobrevive al vaciado y que no pertenece a una
#: extensión: ``alembic_version`` **es** el estado del esquema. Vaciarla haría que
#: ``_migrated`` reaplicase todas las migraciones sobre un esquema ya creado.
TABLA_DE_ESTADO_DEL_ESQUEMA = "alembic_version"

#: Las tablas de negocio **derivadas del catálogo, no de una lista a mano**: todo lo
#: que sea tabla ordinaria o particionada en ``public`` y no lo haya creado una
#: extensión (así se excluye `spatial_ref_sys`, las 8 500 filas de referencia de
#: PostGIS, sin nombrarla). Ser dinámica es el punto: la siguiente tabla que alguien
#: añada entra sola, que es justo lo que falló hasta hoy.
SQL_TABLAS_DE_NEGOCIO = """
SELECT c.relname
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public'
   AND c.relkind IN ('r', 'p')
   AND c.relname <> %s
   AND NOT EXISTS (
         SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e')
 ORDER BY 1
"""

#: El ``TRUNCATE`` pide el ACCESS EXCLUSIVE de cada tabla. Sin tope, una transacción
#: ajena viva sobre cualquiera de ellas colgaría el arranque PARA SIEMPRE y sin decir
#: por qué — el defecto de T-2.73.c. Con tope falla en segundos y con nombre.
LOCK_TIMEOUT_ARRANQUE = "30s"


@pytest.fixture(scope="session", autouse=True)
def _base_sin_herencia(_migrated: None) -> dict[str, int]:
    """Vacía TODA tabla de negocio antes del primer test. [T-2.122]

    **Por qué esto y no "hacer autoritativa toda siembra"** (los dos caminos que
    ofrecía la ficha; se elige UNO, entero):

    Ni ``tenants``, ni ``sites``, ni ``sensors``, ni ``gateways``, ni ``zones``
    entraban en ningún ``TRUNCATE`` de teardown, así que **sobrevivían a la corrida
    entera** y la siguiente arrancaba sobre lo que dejó la anterior. Una siembra
    autoritativa (``ON CONFLICT … DO UPDATE``, T-2.115) corrige el **valor** de una
    fila que alguien vuelve a sembrar; **no puede hacer nada** contra una fila que
    **nadie siembra**. Medido: una sola fila residual en ``visibility_grants``
    —que ninguna fixture siembra— pone en rojo seis pruebas de aislamiento
    multi-tenant (regla de oro 5). Ningún ``DO UPDATE`` alcanza a esa fila.

    Y el coste del otro camino no era menor: ~60 módulos de test escriben catálogo
    por su cuenta, así que "toda siembra autoritativa" es reescribir la suite.

    Vaciar es **un** punto, cubre **toda** tabla por construcción —la lista se deriva
    del catálogo de Postgres— y cubre la siguiente que alguien olvide. Se paga con un
    ``TRUNCATE`` por sesión sobre tablas ya pequeñas.

    Devuelve el censo ``{tabla: filas}`` tomado JUSTO DESPUÉS de vaciar. Lo pide
    ``tests/test_arranque_limpio.py`` **como fixture y no importando este módulo**:
    con ``tests/__init__.py`` presente, pytest carga este conftest como
    ``tests.conftest`` y un ``import conftest`` devolvería OTRO objeto módulo, con el
    censo vacío — un candado que mide la nada y sale verde.
    """
    with psycopg.connect(_dsn()) as c:
        c.execute("RESET ROLE")
        c.execute(f"SET lock_timeout = '{LOCK_TIMEOUT_ARRANQUE}'")
        tablas = [
            fila[0]
            for fila in c.execute(SQL_TABLAS_DE_NEGOCIO, (TABLA_DE_ESTADO_DEL_ESQUEMA,)).fetchall()
        ]
        if tablas:
            c.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in tablas) + " CASCADE")
        c.commit()
        return {t: c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tablas}


@pytest.fixture
def conn() -> psycopg.Connection:
    """Conexión transaccional; se revierte al terminar el test."""
    c = psycopg.connect(_dsn(), autocommit=False)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def use(
    conn: psycopg.Connection,
    role: str,
    *,
    tenant: str | None = None,
    app_role: str | None = None,
    user_id: str | None = None,
) -> None:
    """Fija el rol de conexión + variables de sesión Postgres para RLS.

    ``role`` debe estar en DB_ROLES. ``set_config(..., true)`` es local a la
    transacción (se limpia al rollback). Emula lo que la API hace por request.
    """
    if role not in DB_ROLES:
        raise ValueError(f"rol no permitido: {role!r}")
    conn.execute("RESET ROLE")
    conn.execute(f'SET ROLE "{role}"')
    conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant or "",))
    conn.execute("SELECT set_config('app.role', %s, true)", (app_role or "",))
    conn.execute("SELECT set_config('app.user_id', %s, true)", (user_id or "",))


def reset(conn: psycopg.Connection) -> None:
    """Vuelve al superusuario base (sin rol ni contexto de app)."""
    conn.execute("RESET ROLE")


@pytest.fixture
def seeded(conn: psycopg.Connection) -> psycopg.Connection:
    """Semilla base como superusuario (bypassa RLS): 3 tenants, sitios, gateways,
    sensores, incidentes, y una fila en cada tabla append-only y de series.
    """
    conn.execute("RESET ROLE")
    conn.execute(
        "INSERT INTO tenants (tenant_id, code, name, visibility) VALUES "
        "(%s,'A','Tenant A','private'),"
        "(%s,'B','Tenant B','private'),"
        "(%s,'G','Tenant Gov','gov_shared')",
        (TENANT_A, TENANT_B, TENANT_G),
    )
    for site, tenant in ((SITE_A, TENANT_A), (SITE_B, TENANT_B), (SITE_G, TENANT_G)):
        conn.execute(
            "INSERT INTO sites (site_id, tenant_id, code, name, geom) VALUES "
            "(%s,%s,%s,'Sitio',ST_SetSRID(ST_MakePoint(-99.13,19.43),4326)::geography)",
            (site, tenant, site[:6]),
        )
    conn.execute(
        "INSERT INTO gateways (gateway_id, tenant_id, site_id, serial) VALUES "
        "(%s,%s,%s,'SER-A'),(%s,%s,%s,'SER-B')",
        (GW_A, TENANT_A, SITE_A, GW_B, TENANT_B, SITE_B),
    )
    for sid, tenant, site in ((SENSOR_A, TENANT_A, SITE_A), (SENSOR_B, TENANT_B, SITE_B)):
        conn.execute(
            "INSERT INTO sensors (sensor_id, tenant_id, site_id, kind, model) "
            "VALUES (%s,%s,%s,'ground','RS4D')",
            (sid, tenant, site),
        )
    # incidentes abiertos: uno en tenant A (private), uno en tenant G (gov_shared)
    for inc, evt, tenant, site in (
        (INC_A, EVT_A, TENANT_A, SITE_A),
        (INC_G, EVT_G, TENANT_G, SITE_G),
    ):
        conn.execute(
            "INSERT INTO incidents (incident_id, event_uuid, tenant_id, site_id, "
            "opened_at, severity, trigger) VALUES (%s,%s,%s,%s,%s,'warning','sasmex')",
            (inc, evt, tenant, site, TS),
        )
    # una fila en cada tabla append-only (para probar inmutabilidad)
    conn.execute(
        "INSERT INTO incident_actions (incident_id, tenant_id, kind, actor) "
        "VALUES (%s,%s,'siren_on','edge:A')",
        (INC_A, TENANT_A),
    )
    conn.execute(
        "INSERT INTO dictamens (tenant_id, incident_id, status, basis) "
        "VALUES (%s,%s,'normal_operation','{}')",
        (TENANT_A, INC_A),
    )
    conn.execute(
        "INSERT INTO evidence_objects (tenant_id, incident_id, kind, s3_key) "
        "VALUES (%s,%s,'log','s3://x')",
        (TENANT_A, INC_A),
    )
    conn.execute(
        "INSERT INTO life_checkins (tenant_id, incident_id, user_id, site_id, status) "
        "VALUES (%s,%s,%s,%s,'safe')",
        (TENANT_A, INC_A, GOV_AGENCY, SITE_A),
    )
    conn.execute(
        "INSERT INTO audit_log (tenant_id, actor, verb, object) "
        "VALUES (%s,'system','create','incident:x')",
        (TENANT_A,),
    )
    # series de tiempo: una fila por tenant
    for tenant, site, sensor, gw in (
        (TENANT_A, SITE_A, SENSOR_A, GW_A),
        (TENANT_B, SITE_B, SENSOR_B, GW_B),
    ):
        conn.execute(
            "INSERT INTO waveform_features_1s (ts, tenant_id, site_id, sensor_id, channel, pga_g) "
            "VALUES (%s,%s,%s,%s,'EHZ',0.1)",
            (TS, tenant, site, sensor),
        )
        conn.execute(
            "INSERT INTO device_health (ts, tenant_id, gateway_id, reason) "
            "VALUES (%s,%s,%s,'heartbeat')",
            (TS, tenant, gw),
        )
    return conn
