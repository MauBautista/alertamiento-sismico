"""T-2.35 · Saneamiento: los gabinetes de sitios retirados quedan retirados.

Hasta esta tarea ``retire_site`` solo tocaba ``sites``. El gabinete sobrevivía al
retiro de su estación: invisible en el catálogo de sitios, pero todavía candidato de
config firmada (``commands/sync.py``) y de comandos de actuación
(``queries/commands.py``), que filtran por ``gateways.status`` y NO por
``sites.status``. En la consola eso se veía como "estaciones fantasma" indelebles.

El código ya no los produce (la propagación es transaccional en ``routers/sites.py``);
esta migración limpia los que la base viva arrastra desde antes.

No borra nada: retiro LÓGICO, coherente con la regla de oro 11 (la evidencia del
gabinete —telemetría, comandos, dictámenes— sigue referenciándolo y no se poda).

Idempotente (invariante T-1.45): el ``WHERE g.status <> 'retired'`` hace que la
segunda pasada actualice 0 filas y no vuelva a auditar.

⚠️ ``SET LOCAL app.role`` NO es decorativo. ``gateways`` lleva
``FORCE ROW LEVEL SECURITY`` y el dueño de los objetos es ``takab_migrator`` (el mismo
usuario con el que la nube corre Alembic): sin el GUC, ``app_is_takab_internal()`` es
falso, la política ``gateways_admin`` no deja pasar nada y el UPDATE tocaría **0 filas
en silencio**. En local no se notaría —el superusuario ignora la RLS— y la migración
parecería verde sin haber hecho nada. Es exactamente la trampa "verde local ≠ verde en
nube" ya documentada para las migraciones de este proyecto.

DDL: ninguno. Solo datos sobre tablas preexistentes ⇒ usuario de conexión, sin
``SET ROLE takab_migrator``.

Revision ID: 0024_retire_ghost_gateways
Revises: 0023_quorum_commands_ledger
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024_retire_ghost_gateways"
down_revision: str | None = "0023_quorum_commands_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
SET LOCAL app.role = 'takab_superadmin';

WITH ghosts AS (
  UPDATE gateways g
     SET status = 'retired'
    FROM sites s
   WHERE s.site_id = g.site_id
     AND s.status = 'retired'
     AND g.status <> 'retired'
  RETURNING g.gateway_id, g.tenant_id, g.serial, s.code AS site_code
)
INSERT INTO audit_log (tenant_id, actor, verb, object, meta)
SELECT tenant_id,
       'system:migration_0024',
       'gateway_retire',
       'gateway:' || gateway_id,
       jsonb_build_object(
         'serial', serial,
         'site_code', site_code,
         'reason', 'saneamiento T-2.35: el sitio ya estaba retirado'
       )
  FROM ghosts;
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    # No hay vuelta atrás honesta: "des-retirar" adivinaría cuáles gabinetes estaban
    # activos antes, y encender hardware que toca sirena y válvulas de gas no puede
    # ser el efecto colateral de un rollback. Restaurar es un acto explícito del
    # operador (POST /fleet/gateways/{id}/restore).
    pass
