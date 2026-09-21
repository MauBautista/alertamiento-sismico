"""[T-7.25] El censo de la purga operativa se EJECUTA, y por eso puede morder.

`db/maintenance/2026-09-14_purge_operativa_demo.sql` abre con un censo: toda
tabla de `public` tiene que estar clasificada como historial operativo
(`_purgar`) o como inventario (`_conservar`), y si alguna falta el bloque
`DO $censo$` revienta diciendo su nombre. La idea es exactamente la correcta —
sin él, una tabla nueva se conservaría **por omisión** y nadie se enteraría.

⚠️ **Pero ese censo sólo corría si alguien ejecutaba el script**, y no lo
ejecuta nadie: `grep -rln purge_operativa_demo api/tests edge/tests` no devolvía
una sola línea. O sea, la guarda existía y no mordía: entre que alguien añade la
tabla y el día del simulacro en que se corre la purga, lo único que avisaba era
que la purga fallase **en producción, delante del cliente** — o que no fallase y
se llevase por delante lo que no tocaba.

Aquí el censo se ejecuta contra la base migrada de la suite, **en una
transacción que se revierte**: no borra nada (la purga son los bloques 2 en
adelante, y no se tocan) y se entera ahora.

⚠️ El censo se LEE del fichero, no se copia: una copia aquí sería un segundo
censo, y el que corre el día de la purga seguiría sin nadie que lo mirase.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

PURGA = Path(__file__).resolve().parents[2] / "db/maintenance/2026-09-14_purge_operativa_demo.sql"

#: Los dos rótulos que delimitan el censo dentro del script. Si alguien
#: renumera las secciones, esto se pone rojo en vez de medir un trozo vacío.
_DESDE = "-- --- 0) CENSO"
_HASTA = "-- --- 1) Conteos"


def _censo() -> tuple[str, str]:
    """El censo del script, partido en (preparación, comprobación).

    La preparación son las dos tablas temporales con la clasificación; la
    comprobación es el `DO $censo$` que las cruza con el catálogo de Postgres.
    Se separan para poder volver a lanzar SOLO la comprobación.
    """
    texto = PURGA.read_text(encoding="utf-8")
    i, j = texto.find(_DESDE), texto.find(_HASTA)
    assert 0 <= i < j, f"no se encontró el censo entre {_DESDE!r} y {_HASTA!r}"
    bloque = texto[i:j]
    k = bloque.find("DO $censo$")
    assert k > 0, "el censo ya no tiene su bloque DO: esta guarda mediría la nada"
    return bloque[:k], bloque[k:]


def test_el_censo_de_la_purga_PASA_contra_la_base_migrada(conn: psycopg.Connection) -> None:
    """Ninguna tabla del esquema está sin clasificar. Ejecutado, no leído.

    Se revierte: el `conn` de la suite es transaccional y las dos tablas del
    censo son `TEMP … ON COMMIT DROP`. La purga de verdad empieza después del
    trozo que se ejecuta aquí.
    """
    prep, do = _censo()
    conn.execute(prep)
    conn.execute(do)  # revienta con el nombre de la tabla que falte

    # No-vacuidad, DERIVADA y no tecleada: que no reviente tiene que significar
    # que miró el esquema entero. Los dos números salen del catálogo de Postgres
    # y de las propias tablas del censo, así que crecen solos con el esquema.
    purgar = conn.execute("SELECT count(*) FROM _purgar").fetchone()[0]
    conservar = conn.execute("SELECT count(*) FROM _conservar").fetchone()[0]
    del_catalogo = conn.execute(
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'public' AND c.relkind IN ('r','p')"
        "   AND c.relname NOT LIKE '%\\_chunk' AND c.relname <> 'alembic_version'"
        "   AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e')"
    ).fetchone()[0]
    assert del_catalogo > 50, (
        f"la base sólo tiene {del_catalogo} tablas de negocio: el censo no está "
        "corriendo contra el esquema de verdad"
    )
    assert purgar + conservar >= del_catalogo, (
        f"el censo clasifica {purgar}+{conservar} y el esquema tiene {del_catalogo} "
        "tablas: hay menos clasificadas que tablas y el censo no se quejó"
    )


def test_el_censo_de_la_purga_NO_esta_ciego(conn: psycopg.Connection) -> None:
    """Y que pase tiene que significar algo: con una tabla nueva, revienta.

    Sin esta mitad, la de arriba pasaría en verde aunque el `DO` estuviera vacío
    o el bloque extraído fuera el trozo equivocado del fichero.
    """
    prep, do = _censo()
    conn.execute(prep)
    conn.execute("CREATE TABLE tabla_que_nadie_clasifico (x int)")
    with pytest.raises(psycopg.errors.RaiseException) as exc:
        conn.execute(do)
    assert "tabla_que_nadie_clasifico" in str(exc.value)
    assert "sin clasificar" in str(exc.value)
