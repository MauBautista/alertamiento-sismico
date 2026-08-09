"""T-2.75 · Un canal simulado deja de mentir: estado ``simulated``.

Los canales sin proveedor real (WhatsApp y SMS hasta T-2.76/T-2.77; email sin
SES; push sin platform application) marcaban sus jobs ``sent`` sin enviar nada.
Dos daños, no uno:

  * el tablero decía "notificado" cuando nadie había sido notificado — la misma
    lección que el email aprendió el 13/07;
  * y peor: el salto simulado SATISFACÍA la cascada, así que el orquestador
    marcaba ``skipped`` el resto y el canal REAL que venía detrás no llegaba a
    dispararse. Medido antes de este cambio, con webhook caído y whatsapp/sms
    simulados: ``webhook=failed, whatsapp=sent, sms=skipped, email=skipped`` y
    el proveedor de correo llamado CERO veces.

``simulated`` es un desenlace propio y TERMINAL: ``sent_at`` queda en NULL (una
consulta de entregados lo excluye sin conocerlo), no consume ``attempts`` —
reintentar contra un proveedor inexistente es martillear la nada— y escala al
siguiente canal igual que un fallo, porque a efectos de "¿llegó a un humano?"
un simulado es un NO ENTREGADO.

Solo amplía el dominio del CHECK: ninguna fila existente cambia de estado.

Idempotente (DROP IF EXISTS + ADD con el nombre canónico) — invariante T-1.45.
DDL sobre tabla PREEXISTENTE ⇒ como usuario de conexión, sin ``SET ROLE``.

Revision ID: 0032_notification_simulated
Revises: 0031_mw_mute_verified
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0032_notification_simulated"
down_revision: str | None = "0031_mw_mute_verified"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
ALTER TABLE notification_jobs DROP CONSTRAINT IF EXISTS notification_jobs_status_check;
ALTER TABLE notification_jobs ADD CONSTRAINT notification_jobs_status_check
  CHECK (status IN ('pending','sent','failed','skipped','simulated'));
"""

# La vuelta atrás degrada los simulados a 'failed' ANTES de estrechar el CHECK:
# es el único estado preexistente que también significa "no entregado", así que
# ninguna fila se convierte en un 'sent' que nadie recibió.
_DOWN = """
UPDATE notification_jobs
   SET status = 'failed',
       error = coalesce(error, 'canal simulado (T-2.75, revertido)')
 WHERE status = 'simulated';
ALTER TABLE notification_jobs DROP CONSTRAINT IF EXISTS notification_jobs_status_check;
ALTER TABLE notification_jobs ADD CONSTRAINT notification_jobs_status_check
  CHECK (status IN ('pending','sent','failed','skipped'));
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    op.execute(_DOWN)
