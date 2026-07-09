"""T-1.33 · sensors.calibration_source: de dónde sale la respuesta instrumental

``edge/takab_edge/config/settings.py`` (``SignalConfig``) escala counts a m/s y m/s²
con sensibilidades marcadas en su propio docstring como PLACEHOLDER, a la espera del
StationXML del RS4D (T-1.6, diferida). El *algoritmo* de las features está validado
contra ObsPy (<1%); **la escala física, no**. Aun así la consola presentaba esos
números como ``g`` y ``cm/s`` absolutos.

Un dato sin anclaje físico presentado como magnitud física es exactamente lo que
prohíbe la regla de oro 7 (mostrar un dato congelado como "live" es peor que no
mostrar nada). Esta columna hace la calibración *declarable y auditable*:

    calibrated := (calibration_source IS NOT NULL)

No hay booleano ``calibrated`` que pueda mentir por su cuenta: para declararte
calibrado tienes que nombrar la fuente (p. ej. ``stationxml:AM.R4F74.2026-07-09``).
Mientras sea NULL, la UI muestra unidades relativas y una insignia SIN CALIBRAR.

Revision ID: 0010_sensor_calibration
Revises: 0009_site_status
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_sensor_calibration"
down_revision: str | None = "0009_site_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE sensors ADD COLUMN IF NOT EXISTS calibration_source text")
    op.execute(
        "COMMENT ON COLUMN sensors.calibration_source IS "
        "'Procedencia de la respuesta instrumental (p.ej. stationxml:AM.R4F74). "
        "NULL = sin calibrar: PGA/PGV son relativos, no g ni cm/s.'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sensors DROP COLUMN IF EXISTS calibration_source")
