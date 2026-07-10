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

from demo.run import reset_state  # noqa: E402


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
