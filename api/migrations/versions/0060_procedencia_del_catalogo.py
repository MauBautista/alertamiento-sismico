"""T-5.10 · el catálogo de referencia dice DE DÓNDE salió cada cifra y CUÁNDO

`reference_earthquakes` guardaba la cifra y su fuente, pero no las tres cosas que
hacen citable a una cifra ajena:

* **hora de consulta** — `created_at` es cuándo se insertó la FILA, no cuándo se le
  preguntó a la fuente. Para un sismo de 1985 sembrado en 2026 son cosas
  distintas, y para un feed vivo lo son mucho más: la diferencia entre «lo
  preguntamos hace 30 s» y «lo preguntamos anteayer» es toda la confianza.
* **estado de revisión** — los servicios sismológicos publican una solución
  automática en minutos y la revisan después. Sin este campo, una preliminar se
  imprime como definitiva y prometemos una precisión que la fuente no da.
* **identificador del proveedor** — `catalog_key` es una clave que **nos
  inventamos nosotros** (`'SSN-2017-09-19-PUE'`). No sirve para volver a
  preguntarle a la fuente por ese mismo evento, que es justo lo que hace falta
  para actualizar una preliminar a confirmada.

Los tres nacen NULL y así se quedan hasta que haya ingesta de catálogo: NULL
significa «no consta», y el estado de procedencia que la UI pinta entonces es
`sin_dato_externo` (`shared/glossary/procedencia.json`). Un default inventado
—`now()` en la hora de consulta, `'reviewed'` en el estado— sería exactamente la
mentira que esta ficha existe para impedir.

`review_status` lleva CHECK con los dos valores del glosario que pintan cifra;
un tercero mañana exige tocar la migración Y el glosario, que es la fricción
correcta.

Tabla PREEXISTENTE ⇒ DDL como usuario de conexión, SIN ``SET ROLE`` (invariante de
dueños). Idempotente: `ADD COLUMN IF NOT EXISTS` y el CHECK dentro de un `DO` que
consulta `pg_constraint`.

Revision ID: 0060_procedencia_del_catalogo
Revises: 0059_perdida_de_paquetes
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0060_procedencia_del_catalogo"
down_revision: str | None = "0059_perdida_de_paquetes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
ALTER TABLE reference_earthquakes
  ADD COLUMN IF NOT EXISTS consulted_at      timestamptz,
  ADD COLUMN IF NOT EXISTS review_status     text,
  ADD COLUMN IF NOT EXISTS provider_event_id text;

COMMENT ON COLUMN reference_earthquakes.consulted_at IS
  'Cuándo se le preguntó a la FUENTE (no cuándo se insertó la fila: eso es created_at). '
  'NULL = no consta ⇒ la UI pinta `sin_dato_externo` y NO pinta la cifra (T-5.10).';
COMMENT ON COLUMN reference_earthquakes.review_status IS
  'Lo que la fuente declara de su propia solución: preliminar o confirmada. '
  'NULL = no consta. Los valores son los de shared/glossary/procedencia.json.';
COMMENT ON COLUMN reference_earthquakes.provider_event_id IS
  'Identificador del evento EN LA FUENTE, para poder volver a preguntarle por él '
  '(actualizar una preliminar). `catalog_key` es una clave nuestra y no sirve para eso.';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'reference_earthquakes_review_status_ck'
  ) THEN
    ALTER TABLE reference_earthquakes
      ADD CONSTRAINT reference_earthquakes_review_status_ck
      CHECK (review_status IS NULL OR review_status IN ('preliminar', 'confirmado'));
  END IF;
END $$;
"""

_DOWN = """
ALTER TABLE reference_earthquakes
  DROP CONSTRAINT IF EXISTS reference_earthquakes_review_status_ck;
ALTER TABLE reference_earthquakes
  DROP COLUMN IF EXISTS consulted_at,
  DROP COLUMN IF EXISTS review_status,
  DROP COLUMN IF EXISTS provider_event_id;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWN)
