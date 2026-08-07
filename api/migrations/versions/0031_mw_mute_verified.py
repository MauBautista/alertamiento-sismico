"""T-2.71 · `maintenance_windows.mute_verified`: separar lo MEDIDO de lo SUPUESTO.

La fila guardaba `requested`/`silenced`/`missing_names` como si siempre fueran
cifras medidas. No lo son. Si AWS falla **después** del `PutAlarmMuteRule` —la
relectura de la regla, el `describe_alarms`, o la propia llamada perdida por un
timeout— las alarmas están MUDAS y el acuse no se puede leer.

El código antiguo reportaba ese caso como fracaso total (`0/N`, `mute_rule NULL`)
y producía las dos peores consecuencias a la vez: la consola afirmaba que la
vigilancia seguía viva **con la vigilancia apagada**, y el botón REABRIR
VIGILANCIA se quedaba sin el nombre de la regla, o sea sin nada que borrar,
durante hasta 4 h.

Ahora ese caso se resuelve asumiendo el estado más PELIGROSO (silenciado) y
conservando el nombre para poder deshacerlo — pero entonces las cifras dejan de
ser una medida, y una fila que no puede distinguir «medido» de «supuesto»
obligaría a la consola a pintar una suposición como un hecho. Esta columna es esa
distinción.

`DEFAULT true` porque toda fila anterior a esta migración se escribió por el
único camino que existía entonces: el que sí releía el acuse.

Columna nueva sobre tabla PREEXISTENTE (`maintenance_windows` la crea la 0030)
⇒ DDL como usuario de conexión, SIN `SET ROLE` (invariante de dueños del
proyecto). Idempotente (invariante T-1.45).

**Va en su propia revisión y no dentro de la 0030 a propósito:** la 0030 usa
`CREATE TABLE IF NOT EXISTS`, así que añadirle la columna allí no habría llegado
NUNCA a una base que ya la corrió — alembic no reejecuta una revisión aplicada, y
el `IF NOT EXISTS` se habría saltado la tabla en silencio. Habría pasado en verde
en CI (base nueva en cada corrida) y dejado sin columna toda base incremental:
la trampa de la 0028 mirando hacia el otro lado.

Revision ID: 0031_mw_mute_verified
Revises: 0030_maintenance_windows
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0031_mw_mute_verified"
down_revision: str | None = "0030_maintenance_windows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
ALTER TABLE maintenance_windows
  ADD COLUMN IF NOT EXISTS mute_verified boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN maintenance_windows.mute_verified IS
  'T-2.71: ¿silenced/missing_names se MIDIERON? false = el PutAlarmMuteRule se '
  'emitió y su acuse no se pudo leer, así que las cifras son una suposición '
  'pesimista (se asume silencio, el estado peligroso) y mute_rule es lo único '
  'que permite deshacerlo. Leer esas cifras sin mirar aquí es vender una '
  'suposición como una medida.';
"""


def upgrade() -> None:
    op.execute(_UP)


def downgrade() -> None:
    # Borrar la columna volvería a fundir «medido» con «supuesto» y dejaría a la
    # consola afirmando que una vigilancia está viva sin saberlo. Mismo criterio
    # que 0021/0022/0023/0025/0028/0029.
    pass
