"""T-7.24 · «El worker es el único escritor» es un PRIVILEGIO, no una costumbre.

Se mide contra la base migrada, con los roles reales. Las dos mitades importan:

* `takab_app` —la API— **sólo lee**. Y el `REVOKE` de la 0069 no es redundante:
  la `0001` aplica `db/schema.sql` y DESPUÉS concede `ALL TABLES IN SCHEMA
  public TO takab_app`, así que en una base construida desde cero la API salía
  con INSERT, UPDATE y DELETE sobre tablas que el esquema sólo le dejaba leer.
  Ese privilegio de más **aparece sólo en la nube**, que es exactamente el modo
  de fallo que ya destapó a `takab_app` con SELECT sobre hashes de credencial y
  que la 0068 midió otra vez el 2026-09-20.
* `takab_ingest` —el worker— escribe. Sin ese GRANT la pasada muere con
  `permission denied` en producción mientras en local sale verde, porque el DSN
  de los tests es el superusuario.

La RLS (`FORCE`, sin política de escritura) bloquearía igual a la API; esto es la
segunda capa, y es la que hace la afirmación comprobable. Que la política DIGA
`tenant_id = app_tenant_id()` y no `USING (true)` lo prueba cruzando tenants
`tests/test_rls_isolation.py`, que es donde este repositorio decidió por escrito
que se prueba eso.

⚠️ **ESTA SUITE ES CIEGA EN LOCAL Y MUERDE EN CI**, y conviene saberlo antes de
confiar en su verde: `takab_test_a` ya está migrada, así que `alembic upgrade
head` no vuelve a ejecutar la 0069 y borrar su `REVOKE` deja estos cuatro tests
en verde igual (medido el 2026-09-21). En CI el contenedor de Postgres nace nuevo
en cada corrida, se aplica `db/schema.sql` bajo `SET ROLE takab_migrator` y
DESPUÉS el `GRANT ... ON ALL TABLES ... TO takab_app` de la 0001 — que es
precisamente el orden que regala INSERT/UPDATE/DELETE y el que estos tests cazan.
Para medirlo en local hay que recrear la base, no basta con re-correr la suite.
"""

from __future__ import annotations

import psycopg
import pytest

TABLA = "incident_shakemap"


def _privilegios(conn: psycopg.Connection, rol: str) -> set[str]:
    filas = conn.execute(
        "SELECT privilege_type FROM information_schema.table_privileges"
        " WHERE table_name = %s AND grantee = %s",
        (TABLA, rol),
    ).fetchall()
    return {f[0] for f in filas}


def test_la_API_solo_lee_el_mapa(conn: psycopg.Connection) -> None:
    assert _privilegios(conn, "takab_app") == {"SELECT"}


def test_el_worker_escribe_el_mapa(conn: psycopg.Connection) -> None:
    assert {"SELECT", "INSERT", "UPDATE"} <= _privilegios(conn, "takab_ingest")


def test_la_API_no_puede_escribir_ni_intentandolo(conn: psycopg.Connection) -> None:
    """Y el error es de PRIVILEGIO, no de RLS: son dos capas y se prueba la de fuera."""
    conn.execute('SET ROLE "takab_app"')
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(
            f"INSERT INTO {TABLA} (incident_id, tenant_id, estado, cobertura_km,"
            " puntos, anillos) VALUES (gen_random_uuid(), gen_random_uuid(),"
            " 'sin_datos', 5.0, '[]'::jsonb, '[]'::jsonb)"
        )
    conn.rollback()
    conn.execute("RESET ROLE")


def test_la_tabla_tiene_RLS_forzada(conn: psycopg.Connection) -> None:
    """Sin `FORCE`, el dueño de la tabla se saltaría su propia política."""
    fila = conn.execute(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
        (TABLA,),
    ).fetchone()
    assert fila[0] and fila[1]
