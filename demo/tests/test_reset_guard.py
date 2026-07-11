"""La pizarra limpia de la demo es un TRUNCATE: jamás debe alcanzar una DB remota.

Guardia de T-1.47 (purga de datos sim): la demo y el entorno desplegado comparten
convención de flota, así que un descuido de DSN apuntando al EC2 arrasaría los
incidentes reales de producción. ``reset_state`` debe negarse en seco ANTES de
ejecutar un solo statement.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from demo.run import _assert_exclusive_db, reset_state  # noqa: E402


@dataclass
class _Info:
    host: str | None


class _FakeConn:
    """Superficie mínima de ``psycopg.Connection`` que toca ``reset_state``."""

    def __init__(self, host: str | None) -> None:
        self.info = _Info(host)
        self.executed: list[str] = []
        self.committed = False

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def commit(self) -> None:
        self.committed = True


@pytest.mark.parametrize("host", ["16.58.11.196", "db.takab.internal", "10.0.0.5"])
def test_reset_state_rehusa_db_remota(host: str) -> None:
    """Host remoto ⇒ RuntimeError y CERO statements ejecutados."""
    conn = _FakeConn(host)
    with pytest.raises(RuntimeError, match="localhost"):
        reset_state(conn)  # type: ignore[arg-type]
    assert conn.executed == []
    assert conn.committed is False


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "localhost", "::1", None, "/var/run/postgresql"]
)
def test_reset_state_permite_db_local(host: str | None) -> None:
    """Loopback, socket UNIX (ruta) o host vacío ⇒ la demo procede como siempre."""
    conn = _FakeConn(host)
    reset_state(conn)  # type: ignore[arg-type]
    assert conn.committed is True
    assert any("TRUNCATE" in sql for sql in conn.executed)


# --- Guardia de exclusividad (lección A-3 de la auditoría de cierre) -----------
# Un worker residente (`make soc-local` deja `python -m takab_api.incident` vivo,
# sin puerto que lo delate) correlaciona y dispara fail-open ANTES de que C2
# consulte: 33 OK · 2 FALLOS sin pista del porqué. La demo debe abortar RUIDOSO
# si la DB tiene otros clientes, ANTES de arrancar un solo criterio.


class _FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.sql = sql

    def fetchall(self) -> list[tuple]:
        return self._rows

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeConnActivity:
    """Superficie mínima de ``psycopg.Connection`` que toca ``_assert_exclusive_db``."""

    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows)


def test_db_con_cliente_foraneo_aborta_y_lo_delata() -> None:
    """Otro 'client backend' en la DB ⇒ RuntimeError que nombra pid y proceso."""
    foraneo = (4242, "takab", "", "idle", "SELECT ... FROM incidents ...")
    with pytest.raises(RuntimeError, match="soc-local") as exc:
        _assert_exclusive_db(_FakeConnActivity([foraneo]))  # type: ignore[arg-type]
    assert "4242" in str(exc.value)


def test_db_en_exclusiva_procede() -> None:
    """Cero clientes ajenos ⇒ la acreditación arranca como siempre."""
    _assert_exclusive_db(_FakeConnActivity([]))  # type: ignore[arg-type]
