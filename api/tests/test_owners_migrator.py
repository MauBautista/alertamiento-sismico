"""Las tablas de negocio pertenecen a `takab_migrator` (T-2.73.b, migración 0039).

El riesgo que cierra la ficha es **latente y con nombre**: una migración futura
que escriba `SET ROLE takab_migrator; ALTER TABLE notification_jobs …` muere con
`must be owner of table` si la tabla quedó a nombre del superusuario con el que
se migró en local. Aquí se ejerce ese escenario exacto, no se enumera un
inventario.

Y se ejerce en los dos sentidos, porque una comprobación que nunca has visto
fallar no prueba nada: primero se monta una tabla ajena y se comprueba que el
`ALTER` **sí** revienta, y solo entonces se afirma que sobre las de verdad ya no.
"""

from __future__ import annotations

import psycopg
import pytest

#: `alembic_version` es la contabilidad de la herramienta, no una tabla de
#: negocio, y la migración 0039 la excluye a propósito: el riesgo que persigue
#: —`SET ROLE takab_migrator` seguido de DDL— no la alcanza.
_FUERA_DE_ALCANCE = frozenset({"alembic_version"})

_Q_DUEÑOS = """
SELECT c.relname, pg_get_userbyid(c.relowner), r.rolsuper
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_roles r ON r.oid = c.relowner
 WHERE n.nspname = 'public'
   AND c.relkind IN ('r', 'p')
   AND NOT EXISTS (
         SELECT 1 FROM pg_depend d
          WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e')
 ORDER BY 1
"""


def test_ninguna_tabla_de_negocio_pertenece_a_un_superusuario(conn: psycopg.Connection) -> None:
    """El censo, derivado del catálogo y no de la lista de la ficha — que se
    había quedado corta (le faltaba `reference_earthquakes`).

    Se excluyen las tablas de una extensión (`spatial_ref_sys` de PostGIS): su
    dueño lo pone quien la instaló y no es asunto del proyecto.
    """
    filas = conn.execute(_Q_DUEÑOS).fetchall()
    assert filas, "el arnés no vio ninguna tabla: la base no está migrada"
    ajenas = [(t, dueño) for t, dueño, es_super in filas if es_super and t not in _FUERA_DE_ALCANCE]
    assert ajenas == [], (
        "tablas a nombre de un superusuario; una migración futura con "
        f"`SET ROLE takab_migrator` moriría sobre ellas: {ajenas}"
    )


def test_el_ALTER_de_una_migracion_futura_muere_sobre_una_tabla_AJENA(
    conn: psycopg.Connection,
) -> None:
    """El control que hace no-vacío al test de abajo.

    `takab_migrator` no es superusuario (medido: `rolsuper = false`), así que
    sobre una tabla que no es suya el DDL es simplemente **imposible** — y ése es
    el modo de fallo entero de la ficha. También es la razón por la que la
    migración 0039 no transfiere a ciegas: ejecutada en la nube contra una tabla
    ajena, este mismo error mataría el `apply`.
    """
    conn.execute("CREATE TABLE probe_ajena (id int)")  # dueño = el conector (superusuario)
    # Savepoint: el error aborta la transacción, y sin él el `RESET ROLE` de
    # después —y el teardown del fixture— morirían con `InFailedSqlTransaction`,
    # que es un fallo del arnés disfrazado de fallo del sistema.
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc:  # noqa: PT012
        with conn.transaction():
            conn.execute("SET ROLE takab_migrator")
            conn.execute("ALTER TABLE probe_ajena ADD COLUMN sonda int")
    assert "must be owner" in str(exc.value)
    assert conn.execute("SELECT current_user").fetchone()[0] != "takab_migrator", (
        "el savepoint no devolvió el rol: el resto del test correría con otra identidad"
    )


def test_una_migracion_futura_con_SET_ROLE_ya_no_muere(conn: psycopg.Connection) -> None:
    """El escenario textual de la ficha, ejecutado.

    Se prueba sobre TODAS las tablas que la ficha nombró, no sobre una: el
    defecto venía de que sus migraciones (0005, 0006, 0007, 0011, 0015) crean sin
    `SET ROLE` y el dueño acaba siendo el usuario de la conexión — cosa que en
    local es un superusuario y en la nube es `takab_migrator`.
    """
    tablas = (
        "billing_meters_daily",
        "commands",
        "drills",
        "drill_sites",
        "gateway_config_state",
        "notification_jobs",
        "user_profiles",
    )
    conn.execute("SET ROLE takab_migrator")
    try:
        for tabla in tablas:
            conn.execute(f"ALTER TABLE {tabla} ADD COLUMN sonda_0039 int")
    finally:
        conn.execute("RESET ROLE")
