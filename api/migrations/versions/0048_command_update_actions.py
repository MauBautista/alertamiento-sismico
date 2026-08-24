"""T-2.70 · Acciones ``update_activate`` / ``update_rollback`` en ``commands``.

La actualización remota viaja por el MISMO envelope firmado de T-1.23 (regla de
oro 8: HMAC por gateway + nonce UNIQUE + TTL + ack), así que lo único que cambia
en la DB es el CHECK de ``commands.action``. El canal es ``system``, que ya
estaba permitido desde 0013.

**Por qué la fila importa aquí más que en otras acciones.** ``commands`` no es
un registro decorativo: el ``nonce UNIQUE`` es lo que convierte un replay en una
violación de insert, y la fila es lo que permite responder después a «quién
ordenó estrenar esa versión en ese edificio». Sin poder escribirla, la orden no
sale — que es el comportamiento correcto y el que este CHECK gobernaba.

Idempotente (DROP CONSTRAINT IF EXISTS + ADD), invariante de T-1.45: sobre una
base donde 0001 aplicó el ``schema.sql`` FINAL, re-crear el mismo CHECK es un
no-op lógico.

Revision ID: 0048_command_update_actions
Revises: 0047_arco_sujeto_telefono
Create Date: 2026-08-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0048_command_update_actions"
down_revision: str | None = "0047_arco_sujeto_telefono"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
ALTER TABLE commands DROP CONSTRAINT IF EXISTS commands_action_check;
ALTER TABLE commands ADD CONSTRAINT commands_action_check
  CHECK (action IN ('activate','deactivate','self_test','drill_start','drill_stop',
                    'update_activate','update_rollback'));
"""

# El downgrade restaura el CHECK anterior; fallaría si quedaran filas
# `update_*` — correcto: no se degrada un schema con datos que ya no validarían,
# y menos uno cuyas filas son la evidencia de quién ordenó cambiar el código de
# un gabinete.
_DOWN = """
ALTER TABLE commands DROP CONSTRAINT IF EXISTS commands_action_check;
ALTER TABLE commands ADD CONSTRAINT commands_action_check
  CHECK (action IN ('activate','deactivate','self_test','drill_start','drill_stop'));
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
