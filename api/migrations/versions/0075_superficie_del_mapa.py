"""T-9.51 · D-44 · la superficie ESTIMADA de la sacudida, en el snapshot del mapa

`D-44` enmienda a `D-08`: además de los puntos medidos y los anillos del modelo, el
mapa lleva una superficie **rotulada como estimación** (`shakemap/superficie.py`).
Se guarda en el MISMO snapshot que el resto del mapa, porque la consola y el PDF
tienen que pintar la misma superficie que se calculó con la misma información.

## Las columnas

* ``superficie`` jsonb — ``Superficie.to_json()``: la malla compacta (PGA en
  micro-g enteros, máscara de zona AJUSTADA como cadena de 0/1), su ``bbox``, N y
  M, la ley, el método y la cita de la relación PGA–MMI.
* ``superficie_motivo`` text — por qué NO hay superficie (``superficie.MOTIVOS``:
  ``sin_epicentro`` / ``sin_medidas`` / ``sin_calibrados``).

Tras un cálculo posterior a esta migración, exactamente una de las dos va llena.
**Las dos en NULL = snapshot calculado antes de D-44**, y así se quedan: no se
inventa nada. La pasada las rehace dentro de su ventana y el relleno
(``python -m takab_api.shakemap.rellena``) fuera de ella.

## Sin GRANT nuevo

La tabla ya concede ``SELECT, INSERT, UPDATE`` a ``takab_ingest`` y ``SELECT`` a
``takab_app`` (0069), y un privilegio de tabla cubre las columnas que se le añadan.
La pasada lee además ``sensors`` para saber qué inmueble está calibrado: esa tabla
nace en ``db/schema.sql`` y la ``0001`` concede ``SELECT … ON ALL TABLES`` a
``takab_ingest`` después de aplicarlo, también en la nube.

⚠️ **IDEMPOTENTE**, como exige el invariante de las 0002+. Sólo ``ADD COLUMN``,
ningún ``UPDATE``: las filas viejas no se tocan.

Revision ID: 0075_superficie_del_mapa
Revises: 0074_informe_posterior_al_evento
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0075_superficie_del_mapa"
down_revision: str | None = "0074_informe_posterior_al_evento"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
-- DDL sobre una tabla del migrador ⇒ `SET ROLE takab_migrator` (invariante de dueños).
SET ROLE takab_migrator;

ALTER TABLE incident_shakemap ADD COLUMN IF NOT EXISTS superficie jsonb NULL;
ALTER TABLE incident_shakemap ADD COLUMN IF NOT EXISTS superficie_motivo text NULL;

COMMENT ON COLUMN incident_shakemap.superficie IS
  '[T-9.51 · D-44] La superficie ESTIMADA (Superficie.to_json). NULL con '
  'superficie_motivo NULL = calculado antes de D-44.';
COMMENT ON COLUMN incident_shakemap.superficie_motivo IS
  '[T-9.51 · D-44] Por que NO hay superficie: sin_epicentro, sin_medidas o '
  'sin_calibrados. NULL si la hay (o si el snapshot es anterior a D-44).';

RESET ROLE;
"""

_DOWN = """
SET ROLE takab_migrator;
ALTER TABLE incident_shakemap DROP COLUMN IF EXISTS superficie_motivo;
ALTER TABLE incident_shakemap DROP COLUMN IF EXISTS superficie;
RESET ROLE;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWN)
