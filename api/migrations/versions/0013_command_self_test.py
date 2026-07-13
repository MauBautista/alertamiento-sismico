"""T-1.59 · Comando ``self_test`` (canal ``system``) en el Command Service.

El autodiagnóstico del gabinete (M-2 de la auditoría) viaja por el MISMO
envelope firmado de T-1.23; lo único que cambia en la DB son los CHECKs de
``commands``: canal lógico ``system`` y acción ``self_test``. Idempotente
(DROP CONSTRAINT IF EXISTS + ADD) — invariante de T-1.45: sobre una base donde
0001 aplicó el schema.sql FINAL, re-crear los mismos CHECKs es un no-op lógico.

Revision ID: 0013_command_self_test
Revises: 0012_audit_read_index
Create Date: 2026-07-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013_command_self_test"
down_revision: str | None = "0012_audit_read_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
ALTER TABLE commands DROP CONSTRAINT IF EXISTS commands_channel_check;
ALTER TABLE commands ADD CONSTRAINT commands_channel_check
  CHECK (channel IN ('siren','strobe','gas_valve','elevator','door_retainer','system'));
ALTER TABLE commands DROP CONSTRAINT IF EXISTS commands_action_check;
ALTER TABLE commands ADD CONSTRAINT commands_action_check
  CHECK (action IN ('activate','deactivate','self_test'));
"""

# El downgrade restaura los CHECKs originales; fallaría si quedaran filas
# self_test — correcto: no se degrada un schema con datos que ya no validarían.
_DOWN = """
ALTER TABLE commands DROP CONSTRAINT IF EXISTS commands_channel_check;
ALTER TABLE commands ADD CONSTRAINT commands_channel_check
  CHECK (channel IN ('siren','strobe','gas_valve','elevator','door_retainer'));
ALTER TABLE commands DROP CONSTRAINT IF EXISTS commands_action_check;
ALTER TABLE commands ADD CONSTRAINT commands_action_check
  CHECK (action IN ('activate','deactivate'));
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
