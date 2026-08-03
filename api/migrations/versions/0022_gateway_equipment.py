"""T-2.31 · Perfil de equipamiento por gateway.

``gateways.equipment``: qué actuadores están INSTALADOS físicamente en el sitio
(no toda estación tiene gas/ascensores/puertas). Columna dedicada — no dentro de
``metadata`` (bolsa libre) — porque es verdad de hardware con contrato: objeto de
5 bools, default TODO-TRUE (compat retro: la flota existente no cambia de
conducta). Viaja al edge FUSIONADA en el config sync existente
(``commands/sync.py``: ``rs.config->'edge' || {'equipment': g.equipment}``) —
cero topics ni tablas nuevas.

El trigger emite el MISMO evento ``t='rule_set'`` de ``takab_live`` que la
migración 0006: el worker de sync despierta al editar equipamiento (SLA ≤60 s)
sin tocarse una línea.

Idempotente (invariante T-1.45): ``ADD COLUMN IF NOT EXISTS`` + ``CREATE OR
REPLACE FUNCTION`` + ``DROP TRIGGER IF EXISTS``. Todo el DDL toca la tabla
PREEXISTENTE ``gateways`` ⇒ corre como usuario de conexión (patrón de dueños:
``SET ROLE takab_migrator`` es solo para objetos que nacen nuevos).

Revision ID: 0022_gateway_equipment
Revises: 0021_gateway_catalog_state
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0022_gateway_equipment"
down_revision: str | None = "0021_gateway_catalog_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
ALTER TABLE gateways ADD COLUMN IF NOT EXISTS equipment jsonb NOT NULL DEFAULT
  '{"siren":true,"strobe":true,"gas_valve":true,"elevator":true,"door_retainer":true}';

CREATE OR REPLACE FUNCTION takab_notify_gateway_equipment()
RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  -- Mismo tipo de evento que el trigger de rule_sets (0006): el worker de
  -- config sync ya escucha 't=rule_set' y el candidates SQL fusiona equipment.
  PERFORM pg_notify('takab_live', jsonb_build_object(
    't', 'rule_set', 'tenant', NEW.tenant_id, 'id', NEW.gateway_id)::text);
  RETURN NULL;
END $fn$;

DROP TRIGGER IF EXISTS trg_gateways_equipment_notify ON gateways;
CREATE TRIGGER trg_gateways_equipment_notify
  AFTER UPDATE OF equipment ON gateways
  FOR EACH ROW
  WHEN (OLD.equipment IS DISTINCT FROM NEW.equipment)
  EXECUTE FUNCTION takab_notify_gateway_equipment();
"""


def upgrade() -> None:
    # exec_driver_sql: el literal jsonb del DEFAULT contiene `":true"` y el parser
    # de binds de SQLAlchemy lo tomaría por un parámetro `:true`.
    op.get_bind().exec_driver_sql(_UP)


def downgrade() -> None:
    # La columna queda: el default todo-true es inocuo y quitarla rompería el
    # payload firmado ya publicado a los gabinetes (mismo criterio que 0021).
    pass
