"""T-9.60 · D-46 · el catálogo de México al día: `catalog_sync_state` y el ORIGEN de cada fila

El worker `catalog-sync` (``python -m takab_api.catalogo.sincroniza``) le pregunta
a USGS cada diez minutos por los sismos de M≥4 en la caja de México y los escribe
en ``reference_earthquakes``. Hasta aquí esa tabla la escribían dos: el seed y la
consulta por incidente de T-7.25. Con un tercer escritor hace falta saber QUIÉN
escribió cada fila, porque el worker no puede pisar una fila que cita un dictamen.

## Las columnas nuevas de ``reference_earthquakes``

* ``origen`` — ``seed`` (el DEFAULT: todas las filas que ya existen, sembradas o de
  la consulta anterior a esta migración), ``catalogo`` (la consulta por incidente,
  ``catalogo/consulta.py``, desde aquí) o ``catalog_sync`` (este worker). El worker
  sólo reescribe las suyas: ``ON CONFLICT … DO UPDATE … WHERE origen = 'catalog_sync'``.
* ``usgs_mmi`` — la MMI que PUBLICA USGS, si la hay. No es la nuestra estimada.
* ``usgs_url`` — la página del evento en USGS, para que la app pueda enlazarla.
* ``actualizado_en_fuente`` — el ``updated`` del evento en USGS.

## ``catalog_sync_state``

Una fila por fuente. Es lo que deja a la app decir «sin actualizar desde…»: un
catálogo congelado no puede parecer vivo (regla de oro 7). ``estado`` admite
``apagado`` además de ``nunca``/``ok``/``fallido``: con la consulta apagada por
configuración, cualquiera de los otros tres mentiría. ``pagina_desde`` y
``pagina_max_updated`` son el cursor de una puesta al día TRUNCADA por el límite: la
fuente ordena por hora de ORIGEN y no por ``updated``, así que avanzar
``ultimo_updated`` a mitad de páginas se saltaría eventos.

Global, sin tenant: excepción documentada, como ``reference_earthquakes``. Nunca se
poda (``db/maintenance/…purge_operativa_demo.sql`` la conserva).

## Permisos

``takab_ingest`` escribe las dos tablas; el GRANT va ESCRITO aquí porque en la nube
no vale el ``ALL TABLES`` de la 0001 (la tabla nace después de él). ``takab_app``
sólo lee, y el REVOKE no es redundante: en una base NUEVA la 0001 aplica
``db/schema.sql`` —que ya trae la tabla— y DESPUÉS concede ``ALL TABLES``.

⚠️ **IDEMPOTENTE**, como exige el invariante de las 0002+.

Revision ID: 0076_catalogo_de_mexico
Revises: 0075_superficie_del_mapa
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0076_catalogo_de_mexico"
down_revision: str | None = "0075_superficie_del_mapa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UP = """
-- DDL sobre tablas del migrador ⇒ `SET ROLE takab_migrator` (invariante de dueños).
SET ROLE takab_migrator;

ALTER TABLE reference_earthquakes
  ADD COLUMN IF NOT EXISTS origen text NOT NULL DEFAULT 'seed',
  ADD COLUMN IF NOT EXISTS usgs_mmi numeric NULL,
  ADD COLUMN IF NOT EXISTS usgs_url text NULL,
  ADD COLUMN IF NOT EXISTS actualizado_en_fuente timestamptz NULL;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'ck_ref_eq_origen'
                    AND conrelid = 'reference_earthquakes'::regclass) THEN
    ALTER TABLE reference_earthquakes ADD CONSTRAINT ck_ref_eq_origen
      CHECK (origen IN ('seed','catalogo','catalog_sync'));
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS catalog_sync_state (
  fuente             text PRIMARY KEY CHECK (fuente IN ('USGS')),
  estado             text NOT NULL CHECK (estado IN ('nunca','ok','fallido','apagado')),
  ultimo_updated     timestamptz NULL,
  ultima_corrida     timestamptz NULL,
  ultimo_ok          timestamptz NULL,
  n_ultima           integer NULL,
  error              text NULL,
  pagina_desde       timestamptz NULL,
  pagina_max_updated timestamptz NULL
);

ALTER TABLE catalog_sync_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalog_sync_state FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS css_read ON catalog_sync_state;
CREATE POLICY css_read ON catalog_sync_state FOR SELECT
  USING (app_role() IS NOT NULL);

RESET ROLE;

COMMENT ON COLUMN reference_earthquakes.origen IS
  '[T-9.60 · D-46] Quien escribio la fila: seed, catalogo (consulta por incidente) '
  'o catalog_sync (el worker). El worker solo reescribe las suyas.';
COMMENT ON TABLE catalog_sync_state IS
  '[T-9.60 · D-46] Como va la sincronizacion del catalogo. ultimo_ok es lo que la '
  'app pinta como "actualizado"; un catalogo congelado no puede parecer vivo.';

GRANT SELECT, INSERT, UPDATE ON reference_earthquakes TO takab_ingest;
GRANT SELECT, INSERT, UPDATE ON catalog_sync_state TO takab_ingest;
GRANT SELECT ON catalog_sync_state TO takab_app;
REVOKE INSERT, UPDATE, DELETE ON catalog_sync_state FROM takab_app;
"""

_DOWN = """
DROP TABLE IF EXISTS catalog_sync_state;
SET ROLE takab_migrator;
ALTER TABLE reference_earthquakes DROP CONSTRAINT IF EXISTS ck_ref_eq_origen;
ALTER TABLE reference_earthquakes
  DROP COLUMN IF EXISTS actualizado_en_fuente,
  DROP COLUMN IF EXISTS usgs_url,
  DROP COLUMN IF EXISTS usgs_mmi,
  DROP COLUMN IF EXISTS origen;
RESET ROLE;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UP)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWN)
