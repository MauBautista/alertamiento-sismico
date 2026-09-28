"""[T-9.42 · D-48] La 0074: la tabla del informe posterior al evento.

Tres cosas que costaría caro equivocar, medidas contra la base migrada:

* **Es IDEMPOTENTE**, el invariante de todas las 0002+: `db/schema.sql` es el
  esquema final y la `0001` lo aplica antes, así que sobre una base nueva esta
  migración se encuentra su trabajo hecho. Se ejecuta el SQL REAL del módulo.
* **«El worker es el único escritor» es un PRIVILEGIO.** `takab_app` sólo lee
  (el `REVOKE` no es redundante: la `0001` concede `ALL TABLES` DESPUÉS de aplicar
  el esquema) y `takab_ingest` escribe.
* **Nunca `ok` sin evidencia**, garantizado por la base y no sólo por el worker.

⚠️ Como la suite del ShakeMap, lo del privilegio es CIEGO en una base ya migrada
y muerde en CI, donde la base nace nueva en cada corrida.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import psycopg
import pytest

_RUTA = (
    Path(__file__).resolve().parents[2] / "migrations/versions/0074_informe_posterior_al_evento.py"
)
TABLA = "post_event_reports"


def _modulo():
    spec = importlib.util.spec_from_file_location("mig_0074", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _privilegios(conn: psycopg.Connection, rol: str, tabla: str = TABLA) -> set[str]:
    filas = conn.execute(
        "SELECT privilege_type FROM information_schema.table_privileges"
        " WHERE table_name = %s AND grantee = %s",
        (tabla, rol),
    ).fetchall()
    return {f[0] for f in filas}


def test_la_cadena_de_revisiones_no_se_bifurca() -> None:
    """Cuelga de la 0073 (F3). Dos migraciones con la misma madre = cabeza doble."""
    m = _modulo()
    assert m.revision == "0074_informe_posterior_al_evento"
    assert m.down_revision == "0073_firma_y_banda_del_dictamen"


def test_el_sql_de_la_migracion_se_puede_reaplicar(conn: psycopg.Connection) -> None:
    up = _modulo()._UP  # noqa: SLF001
    conn.execute(up)
    conn.execute(up)
    fila = conn.execute(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
        (TABLA,),
    ).fetchone()
    assert fila[0] and fila[1], "reaplicarla no puede dejar la RLS apagada"
    conn.rollback()


def test_la_API_solo_lee_el_informe(conn: psycopg.Connection) -> None:
    assert _privilegios(conn, "takab_app") == {"SELECT"}


def test_el_worker_escribe_el_informe(conn: psycopg.Connection) -> None:
    assert {"SELECT", "INSERT", "UPDATE"} <= _privilegios(conn, "takab_ingest")


def test_el_worker_puede_gastar_la_cuota_de_IA(conn: psycopg.Connection) -> None:
    """[T-9.42] El informe automático redacta con la MISMA `build_narrative` que la
    consola, y esa función apunta el gasto en `ai_spend`. La 0058 sólo se lo concedió a
    `takab_app`; en la nube la `0001` no lo cubre (la tabla es posterior), así que sin
    este GRANT el worker moriría con «permission denied» al primer informe con la IA
    encendida — y en local saldría verde."""
    assert {"SELECT", "INSERT", "UPDATE"} <= _privilegios(conn, "takab_ingest", "ai_spend")


def test_el_worker_lee_quien_firmo(conn: psycopg.Connection) -> None:
    """El builder une `user_profiles` para el nombre del firmante; la 0011 sólo se la
    concedió a `takab_app`. Mismo modo de fallo que el de `ai_spend`."""
    assert "SELECT" in _privilegios(conn, "takab_ingest", "user_profiles")


def test_la_API_no_puede_escribir_ni_intentandolo(conn: psycopg.Connection) -> None:
    conn.execute('SET ROLE "takab_app"')
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(
            f"INSERT INTO {TABLA} (tenant_id, incident_id, trigger, variant)"
            " VALUES (gen_random_uuid(), gen_random_uuid(), 'plazo', 'executive')"
        )
    conn.rollback()


def test_ok_sin_evidencia_lo_rechaza_la_base(conn: psycopg.Connection) -> None:
    """El CHECK `per_ok_con_evidencia`: un `ok` sin PDF sería un informe que no existe."""
    fila = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'per_ok_con_evidencia'"
    ).fetchone()
    assert fila is not None, "falta el CHECK que impide `ok` sin evidencia"
    assert "evidence_id IS NOT NULL" in fila[0]


def test_los_vocabularios_son_cerrados(conn: psycopg.Connection) -> None:
    defs = " ".join(
        r[0]
        for r in conn.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conrelid = 'post_event_reports'::regclass AND contype = 'c'"
        ).fetchall()
    )
    for valor in ("firma", "cierre", "plazo", "pendiente", "ok", "fallido"):
        assert f"'{valor}'" in defs, f"el vocabulario cerrado no incluye {valor!r}"


def test_un_informe_por_incidente(conn: psycopg.Connection) -> None:
    """La clave natural es el incidente: `ON CONFLICT (incident_id)` la necesita."""
    fila = conn.execute(
        "SELECT count(*) FROM pg_indexes WHERE tablename = %s AND indexdef ILIKE %s",
        (TABLA, "%UNIQUE%(incident_id)%"),
    ).fetchone()
    assert fila[0] == 1


def test_la_tabla_tiene_RLS_forzada(conn: psycopg.Connection) -> None:
    fila = conn.execute(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
        (TABLA,),
    ).fetchone()
    assert fila[0] and fila[1]
