"""T-2.81.c · Las DOS capas del append-only, derivadas del catálogo vivo.

Una tabla append-only de este esquema se protege dos veces y a propósito:

* **privilegio ausente** — ``takab_app`` no tiene ``DELETE`` sobre ella; y
* **trigger activo** — un guard ``BEFORE DELETE FOR EACH ROW`` lo rechaza con
  ``P0001`` aunque quien lo intente sea el DUEÑO de la tabla, a quien el
  privilegio no alcanza.

Ninguna de las dos sobra. El privilegio no cubre al dueño (``takab_migrator``,
y los jobs de TimescaleDB corren como él); el trigger no cubre a la tabla que
nazca sin él. Por eso el defecto que cierra esta tarea —``rule_evaluations`` con
el ``DELETE`` todavía concedido— **no era explotable** y aun así había que
arreglarlo: la tabla descansaba en UNA capa donde sus hermanas tienen dos.

POR QUÉ EL CONJUNTO SE DERIVA Y NO SE ESCRIBE
─────────────────────────────────────────────
La lista escrita a mano es justo lo que falló: el ``REVOKE`` de la T-2.80 enumeró
doce tablas y ``rule_evaluations`` no estaba entre ellas, aunque llevaba su
trigger append-only desde el 0001. Nadie lo notó porque nada comparaba las dos
capas. Aquí el conjunto sale de ``pg_trigger``: **el que pone el trigger declara
la tabla**, y el test le exige el ``REVOKE`` sin que nadie venga a editar nada.

La derivación sola, sin embargo, se aprueba a sí misma —"todo lo que derivé está
protegido" es cierto por construcción—. Le falta un suelo, y es el mismo que usa
la precondición del job de retención: ``COMPLIANCE_ANCHOR``. Si alguien le quita
el trigger a ``audit_log``, la tabla se cae del conjunto derivado **en silencio**
y el test pasaría sin comprobar nada; con el suelo, se pone en rojo.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg import sql

from conftest import GW_A, SITE_A, TENANT_A, TS, reset, use
from takab_api.privacy.retention import (
    COMPLIANCE_ANCHOR,
    DELETE_GUARDS,
    JOB_ROLE,
    protection_report,
)

#: Bit del evento DELETE en ``pg_trigger.tgtype`` (``TRIGGER_TYPE_DELETE``,
#: ``src/include/catalog/pg_trigger.h``). Importa filtrarlo: la T-2.80 partió el
#: guard de ``life_checkins`` en dos triggers y el de ARCO dispara SOLO en
#: UPDATE. Contar "tiene un trigger de guarda" sin mirar el evento contaría como
#: protegida contra el borrado a una tabla cuyo guard no se entera del borrado.
TG_DELETE = 1 << 3

#: Tablas con un guard de borrado ACTIVO, y si al rol de la API le falta además
#: el privilegio. Todo sale de ``pg_catalog``; este fichero no nombra ni una.
_Q_DOS_CAPAS = """
SELECT c.relname,
       NOT has_table_privilege(%(role)s, c.oid, 'DELETE') AS sin_privilegio
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
  AND EXISTS (
    SELECT 1 FROM pg_trigger t
    JOIN pg_proc p ON p.oid = t.tgfoid
    WHERE t.tgrelid = c.oid
      AND NOT t.tgisinternal
      AND p.proname = ANY(%(guards)s)
      AND t.tgenabled <> 'D'
      AND (t.tgtype & %(evento)s) <> 0
  )
ORDER BY 1
"""


#: Una tabla cualquiera que hoy tenga las DOS capas, con el nombre de su trigger.
#: Se elige del catálogo y no a mano: el test de abajo prueba una propiedad del
#: mecanismo, no de una tabla concreta, y clavar un nombre sería volver a la lista.
_Q_UNA_CON_LAS_DOS = """
SELECT c.relname, t.tgname
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_trigger t ON t.tgrelid = c.oid
JOIN pg_proc p ON p.oid = t.tgfoid
WHERE n.nspname = 'public' AND c.relkind = 'r'
  AND NOT t.tgisinternal
  AND t.tgenabled <> 'D'
  AND p.proname = ANY(%(guards)s)
  AND (t.tgtype & %(evento)s) <> 0
  AND NOT has_table_privilege(%(role)s, c.oid, 'DELETE')
ORDER BY 1, 2
LIMIT 1
"""

_PARAMS = {"role": JOB_ROLE, "guards": list(DELETE_GUARDS), "evento": TG_DELETE}


def derivar_capas(conn: psycopg.Connection) -> dict[str, bool]:
    """``tabla con guard de DELETE → ¿le falta también el privilegio?``"""
    filas = conn.execute(_Q_DOS_CAPAS, _PARAMS).fetchall()
    return {nombre: sin_privilegio for nombre, sin_privilegio in filas}


@pytest.fixture
def capas(conn: psycopg.Connection) -> dict[str, bool]:
    reset(conn)
    return derivar_capas(conn)


def test_la_derivacion_no_esta_vacia(capas: dict[str, bool]) -> None:
    """El suelo. Un conjunto vacío no es "un esquema sin evidencia": es la
    derivación rota, y con ella el test de abajo pasaría sin mirar nada."""
    assert capas, (
        "la derivación de tablas con guard de borrado devolvió el conjunto vacío. "
        "Eso no es un esquema sin append-only: es que la consulta al catálogo "
        "dejó de encontrar los triggers."
    )


def test_el_suelo_de_compliance_sigue_llevando_su_trigger(capas: dict[str, bool]) -> None:
    """Lo que ya no se deriva, ya no se revisa. Las cinco tablas que la regla de
    oro 11 nombra por su nombre tienen que aparecer en el conjunto derivado: sin
    esto, quitarle el trigger a ``audit_log`` la sacaría del censo en silencio y
    el test de las dos capas seguiría verde."""
    huecos = sorted(set(COMPLIANCE_ANCHOR) - set(capas))
    assert not huecos, (
        f"{huecos} ya no tienen un guard de borrado ACTIVO en el catálogo. La "
        "regla de oro 11 las nombra explícitamente: alguien desarmó la "
        "inmutabilidad de la evidencia."
    )


def test_toda_tabla_con_guard_pierde_tambien_el_privilegio(capas: dict[str, bool]) -> None:
    """EL CRITERIO. Quien pone el trigger declara la tabla append-only; el
    ``REVOKE`` tiene que venir detrás. Este es el test que estaba en rojo antes
    de la 0037, y nombraba a ``rule_evaluations``."""
    una_sola_capa = sorted(t for t, sin_privilegio in capas.items() if not sin_privilegio)
    assert not una_sola_capa, (
        f"{una_sola_capa} llevan trigger append-only pero {JOB_ROLE} conserva el "
        "privilegio DELETE: la protección descansa en UNA capa donde el resto "
        "tiene dos. Falta un `REVOKE DELETE ... FROM " + JOB_ROLE + "` en la "
        "migración (y su espejo en db/schema.sql)."
    )


def test_un_guard_deshabilitado_deja_de_contar_como_capa(conn: psycopg.Connection) -> None:
    """Un trigger con ``tgenabled = 'D'`` sigue en el catálogo y no para nada.

    Esta propiedad la cubría ``test_privacy_retention.py`` sobre
    ``rule_evaluations`` **porque era la única tabla que dependía solo del
    trigger**. Al cerrar T-2.81.c esa tabla dejó de existir, y con ella la
    premisa de aquel test. La propiedad, sin embargo, sigue haciendo falta —y
    ahora se puede medir mejor, sobre una tabla con las dos capas: al deshabilitar
    el guard se cae UNA y queda la otra, que es exactamente la razón de tener dos.
    """
    reset(conn)
    elegida = conn.execute(_Q_UNA_CON_LAS_DOS, _PARAMS).fetchone()
    assert elegida is not None, "ninguna tabla tiene hoy las dos capas: la derivación falla"
    tabla, trigger = elegida

    assert protection_report(conn, role=JOB_ROLE)[tabla] == (
        "privilegio_ausente",
        "guard_activo",
    )
    assert tabla in derivar_capas(conn)

    # Identificadores tomados del catálogo, compuestos con `sql.Identifier`.
    conn.execute(
        sql.SQL("ALTER TABLE {} DISABLE TRIGGER {}").format(
            sql.Identifier(tabla), sql.Identifier(trigger)
        )
    )

    assert protection_report(conn, role=JOB_ROLE)[tabla] == ("privilegio_ausente",), (
        "un guard DESHABILITADO se está contando como protección: la derivación "
        "mira el catálogo pero no si el trigger está vivo"
    )
    assert tabla not in derivar_capas(conn), (
        "la derivación de este fichero tampoco puede contar un trigger apagado"
    )


# --- El caso de la ficha, medido en comportamiento y no solo en el catálogo ---
#
# El catálogo dice qué hay instalado; esto dice qué pasa cuando alguien lo
# intenta. Se hace sobre `rule_evaluations` porque es la tabla que esta tarea
# arregla: las otras cuatro que el seed puebla ya se ejercitan en
# `test_append_only.py`.


def _una_evaluacion(conn: psycopg.Connection) -> None:
    reset(conn)
    conn.execute(
        "INSERT INTO rule_evaluations (ts, tenant_id, site_id, gateway_id, prev_tier, new_tier) "
        "VALUES (%s,%s,%s,%s,'normal','watch')",
        (TS, TENANT_A, SITE_A, GW_A),
    )


def test_capa_1_la_api_ni_siquiera_tiene_el_privilegio(seeded: psycopg.Connection) -> None:
    """Antes de la 0037 esto NO levantaba nada: la RLS de ``rule_evaluations``
    solo tiene política de lectura, así que el ``DELETE`` de ``takab_app``
    afectaba a cero filas **sin error** y el trigger jamás llegaba a dispararse.
    "No es explotable hoy" era cierto y, aun así, ninguna de las dos capas de la
    ficha estaba puesta: la que paraba el borrado era la ausencia de política."""
    _una_evaluacion(seeded)
    use(seeded, "takab_app", tenant=TENANT_A, app_role="takab_superadmin")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        seeded.execute("DELETE FROM rule_evaluations")


def test_capa_2_el_trigger_para_hasta_al_rol_mas_privilegiado(
    seeded: psycopg.Connection,
) -> None:
    """La capa que el privilegio no puede dar: ni el superusuario de la conexión
    —que salta RLS y lo tiene todo concedido— borra una transición de tier."""
    _una_evaluacion(seeded)
    reset(seeded)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        seeded.execute("DELETE FROM rule_evaluations")
