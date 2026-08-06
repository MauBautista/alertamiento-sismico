"""T-2.65 · El retiro de un gabinete despierta al worker de config sync.

Sin esto, el sobre firmado que le DICE al gabinete que fue dado de baja salía por
el POLL DE RESPALDO del worker: hasta 30 s después del clic en la consola
(``commands/worker.py::poll_s``). Medido en vivo con ``LISTEN takab_live``:
``UPDATE gateways SET status='retired'`` NO emitía nada. El único trigger sobre
``gateways`` era el de la migración 0022, y solo ``AFTER UPDATE OF equipment``.

Espejo exacto de aquel, reutilizando su MISMA función (``t='rule_set'``): el
worker de config sync ya escucha ese tipo de evento y el candidates SQL ya
recalcula el documento fusionado, así que no se toca una línea de Python.

**El ``WHEN`` es más estrecho que un simple cambio de estado, a propósito.**
``gateways.status`` NO solo lo mueven ``retire``/``restore``: la ingesta lo
reescribe con cada LWT de conexión y desconexión
(``ingest/handlers.py::_STATUS_SQL``). Un trigger sobre cualquier transición
despertaría al worker de config en cada flap de MQTT de CADA gabinete de la
plataforma, para no publicar nada. Solo interesan las transiciones que ENTRAN o
SALEN de ``retired``, que son justamente las que cambian el documento firmado.

Seguro por construcción: la función es ``plpgsql`` ``SECURITY INVOKER`` y lo
único que hace es ``pg_notify``; ``ws/hub.py`` descarta los tipos que no conoce.

Idempotente (invariante T-1.45): ``DROP TRIGGER IF EXISTS`` + ``CREATE TRIGGER``.
Todo el DDL toca la tabla PREEXISTENTE ``gateways`` ⇒ corre como usuario de
conexión (patrón de dueños: ``SET ROLE takab_migrator`` es solo para objetos que
nacen nuevos).

Revision ID: 0027_gateway_status_notify
Revises: 0026_audit_log_object_index
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0027_gateway_status_notify"
down_revision: str | None = "0026_audit_log_object_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
DROP TRIGGER IF EXISTS trg_gateways_status_notify ON gateways;
CREATE TRIGGER trg_gateways_status_notify
  AFTER UPDATE OF status ON gateways
  FOR EACH ROW
  WHEN (OLD.status IS DISTINCT FROM NEW.status
        AND (OLD.status = 'retired' OR NEW.status = 'retired'))
  EXECUTE FUNCTION takab_notify_gateway_equipment();
"""

_DOWN = "DROP TRIGGER IF EXISTS trg_gateways_status_notify ON gateways;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UP)


def downgrade() -> None:
    # El trigger sí se puede quitar sin dañar nada: el worker vuelve a enterarse
    # por el poll de respaldo (≤30 s), solo que más tarde.
    op.get_bind().exec_driver_sql(_DOWN)
