"""T-2.32 · Ledger idempotente de comandos de actuación por quórum.

Política ratificada 2026-08-03: al confirmar quórum ≥3 la NUBE emite comandos
de actuación FIRMADOS (regla de oro 8) a los gateways miembro. La idempotencia
vive en la tabla ``commands`` misma: índice único parcial por
``(gateway_id, event_id, channel)`` restringido al actor sistema del quórum —
una pasada repetida (o dos instancias del engine) no puede duplicar el burst, y
un publish fallido reintenta en la siguiente pasada sin fila fantasma.

El UUID del actor es una constante documentada (espejo en
``takab_api/commands/quorum_actuation.py`` — cambiar uno exige cambiar el otro).

Idempotente (invariante T-1.45); DDL sobre tabla preexistente ⇒ usuario de
conexión.

Revision ID: 0023_quorum_commands_ledger
Revises: 0022_gateway_equipment
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0023_quorum_commands_ledger"
down_revision: str | None = "0022_gateway_equipment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_commands_quorum_ledger
  ON commands (gateway_id, event_id, channel)
  WHERE issued_by = '00000000-0000-4000-8000-00000000c092';
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    # El índice es el candado de idempotencia del burst de quórum: se conserva.
    pass
