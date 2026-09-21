"""T-7.24 · La 0069 es IDEMPOTENTE, que es el invariante de todas las 0002+.

`db/schema.sql` es el esquema FINAL y la `0001` lo aplica antes, así que sobre
una base nueva esta migración se encuentra su propio trabajo hecho: la tabla ya
existe, la política ya existe y los GRANT ya están dados. Si no fuera
idempotente, una base nueva moriría en el despliegue — y una base existente
saldría bien, que es la asimetría que este repositorio lleva fichas cazando.

Se ejecuta el SQL REAL de la migración, leído del módulo, no una copia: una copia
aquí sería una segunda migración y la que corre en la nube seguiría sin probar.
Todo dentro de la transacción del `conn` de la suite, que se revierte.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import psycopg

_RUTA = Path(__file__).resolve().parents[2] / "migrations/versions/0069_mapa_de_sacudida.py"


def _modulo():
    spec = importlib.util.spec_from_file_location("mig_0069", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_el_sql_de_la_migracion_se_puede_reaplicar(conn: psycopg.Connection) -> None:
    """Dos veces seguidas sobre una base que YA la tiene aplicada. Sin error."""
    up = _modulo()._UP  # noqa: SLF001
    conn.execute(up)
    conn.execute(up)
    fila = conn.execute(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class"
        " WHERE relname = 'incident_shakemap'"
    ).fetchone()
    assert fila[0] and fila[1], "reaplicarla no puede dejar la RLS apagada"
    conn.rollback()


def test_la_cadena_de_revisiones_no_se_bifurca() -> None:
    """`down_revision` apunta a la 0068, que es la última que aterrizó (T-7.25).

    Dos migraciones colgando de la misma padre dan una cabeza doble, y alembic lo
    descubre en el despliegue y no aquí.
    """
    m = _modulo()
    assert m.revision == "0069_mapa_de_sacudida"
    assert m.down_revision == "0068_consulta_al_catalogo"
